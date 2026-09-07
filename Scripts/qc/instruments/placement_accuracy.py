"""placement_accuracy.py — if we transplant a cluster, how close does it land?

THE QUESTION (Kam, 2026-09-06): "Why don't we try to place it first, and see how right or
wrong we get it."

Answerable with no new labels, because the archive already holds thousands of clusters
BOTH epochs found. Hide one, place it using only its neighbours, compare where it landed
to where it actually is. Leave-one-out on known objects.

    naive   place at the donor's own coordinates — NO transform. The baseline the whole
            transform layer must beat.
    global  one median shift per epoch pair, computed leave-one-out.
    local   median shift of the K nearest matched pairs, excluding the held-out one —
            Kam's "map the local clusters to each other".

THIS FILE WAS CORRECTED AFTER AN ADVERSARIAL REVIEW (2026-09-06) that overturned the
first version's conclusions. The instrument's arithmetic was sound; the reading of it was
not, and three of the corrections are load-bearing:

  * K WAS 8, WHICH MEASURED THE ESTIMATOR, NOT THE WORLD. An 8-point median is noisy;
    error decays monotonically to a plateau at k in [32, 512]. At k = 64 `local` beats
    `global` in 6 of 7 epochs and beats the BEST POSSIBLE constant translation in 4 of 7.
    The first version's conclusion — "the displacement field does not vary spatially" —
    was an artifact of k = 8 and is now known to be backwards.
  * "NO GAIN" WAS A 3.5 VIOLATION. For the five epochs whose measured offset is <= 0.43 m
    the predicted gain from a PERFECT transform is 0.00-0.06 m, below what this metric
    resolves. Those rows are UNDETERMINED, not zero, and are now labelled so.
  * THE IoU ARM IS QUANTIZED TO THE 2 m GRID. Every measured shift is under one cell, so
    integer-cell translation rounds them all to zero and `global`'s IoU is a bit-copy of
    `naive`'s. That is not a measurement, and the columns now say so. The transplant will
    run on native-resolution masks (6.8-38 cm), where this limitation does not apply.

WHAT THE NUMBERS CANNOT SETTLE, stated because the first version overstated exactly here:
  * Every unit is a cluster BOTH epochs detected — the favourable population. The clusters
    worth transplanting are the ones an epoch MISSED, for reasons (shadow, edge, low
    contrast) that plausibly make them harder to place.
  * MATCH_RADIUS_M truncates the error distribution at 8 m by construction, so arm
    differences are compressed.
  * The residual is measured on a 2 m lattice; per-axis it is 0.94-1.6 m, i.e. under one
    cell, so raster quantization and genuine shape change are NOT separable here.
  * `local`'s advantage is estimated FROM THE MASKS. Only the global median has been
    validated against imagery (landmark_transform_gate.py). Spatially correlated matching
    noise — mergers and splits clustering in dense stands — would also lower LOO error
    without being geometry. Whether local structure is geometry or artifact is
    UNDETERMINED and needs an imagery-side gate before any build uses it. That is the
    §3 lesson of the falsified offset layer, applied to this analysis.

Output: phase4/qc/placement_accuracy.csv

Run:  py -3.12 qc/instruments/placement_accuracy.py [--reference 2021] [--k 64]
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

MIN_AREA_M2 = 28.0
MAX_AREA_M2 = 10000.0
MATCH_RADIUS_M = 8.0      # truncates the error distribution — see docstring
AREA_RATIO = (0.5, 2.0)   # admits pairs whose IoU CEILING is 0.5; reported, not hidden
AMBIGUITY = 1.5
CELL_M = 2.0
K_SWEEP = (8, 16, 32, 64, 128, 256, 512)


def _rows(p):
    if not Path(p).exists():
        return []
    body = [ln for ln in Path(p).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def clusters(mask, inside, tf):
    import numpy as np
    from scipy import ndimage
    lab, n = ndimage.label(mask & inside, structure=np.ones((3, 3), int))
    if n == 0:
        return None
    area = np.bincount(lab.ravel()) * (CELL_M ** 2)
    keep = np.where((area >= MIN_AREA_M2) & (area <= MAX_AREA_M2))[0]
    keep = keep[keep > 0]
    if keep.size == 0:
        return None
    cent = np.asarray(ndimage.center_of_mass(mask & inside, lab, keep), dtype=float)
    xy = np.column_stack([tf[2] + tf[0] * (cent[:, 1] + 0.5),
                          tf[5] + tf[4] * (cent[:, 0] + 0.5)])
    order = np.argsort(lab.ravel(), kind="stable")
    sl = lab.ravel()[order]
    s, e = np.searchsorted(sl, keep, "left"), np.searchsorted(sl, keep, "right")
    members = {int(k): order[a:b] for k, a, b in zip(keep, s, e)}
    return {"xy": xy, "area": area[keep], "labels": keep, "members": members,
            "shape": lab.shape}


def matched_pairs(ca, cb):
    import numpy as np
    from scipy.spatial import cKDTree
    pa, pb = ca["xy"], cb["xy"]
    tb, ta = cKDTree(pb), cKDTree(pa)
    d, j = tb.query(pa, k=2, distance_upper_bound=MATCH_RADIUS_M)
    _, i2 = ta.query(pb, k=1, distance_upper_bound=MATCH_RADIUS_M)
    out = []
    for i in range(len(pa)):
        if not np.isfinite(d[i, 0]) or j[i, 0] >= len(pb):
            continue
        if np.isfinite(d[i, 1]) and d[i, 1] < AMBIGUITY * max(d[i, 0], 1e-6):
            continue
        k = int(j[i, 0])
        if i2[k] != i:
            continue
        r = cb["area"][k] / ca["area"][i] if ca["area"][i] > 0 else 0
        if AREA_RATIO[0] <= r <= AREA_RATIO[1]:
            out.append((i, k))
    return out


def _cells(c, i):
    import numpy as np
    w = c["shape"][1]
    idx = c["members"][int(c["labels"][i])]
    return np.divmod(idx, w)


def iou_shift_cells(ca, i, cb, k, ci, cj):
    """IoU after translating donor by WHOLE CELLS (ci rows, cj cols). Sub-cell shifts are
    not representable on this lattice — that limitation is the point, and is reported."""
    h, w = ca["shape"]
    sr, sc = _cells(ca, i)
    sr2, sc2 = sr + ci, sc + cj
    ok = (sr2 >= 0) & (sr2 < h) & (sc2 >= 0) & (sc2 < w)
    moved = set((sr2[ok] * w + sc2[ok]).tolist())
    tr, tc = _cells(cb, k)
    tgt = set((tr * w + tc).tolist())
    if not moved or not tgt:
        return None
    inter = len(moved & tgt)
    return inter / (len(moved) + len(tgt) - inter)


def build(reference="2021", k_local=64):
    import numpy as np
    from scipy.spatial import cKDTree
    if not STACK.exists():
        return None, None, f"{STACK} not found (local mirror)"
    d = np.load(STACK)
    stack, inside, tf = d["stack"], d["inside"], d["transform"]
    years = [str(y) for y in d["years"]]
    if reference not in years:
        return None, None, f"reference {reference} not in {years}"
    coreg = {r["label"]: r for r in _rows(QC / "coregistration.csv")}

    cl = {y: clusters(stack[i] == 1, inside, tf) for i, y in enumerate(years)}
    cr = cl[reference]
    rows, sweep = [], []

    for y in years:
        if y == reference or cl[y] is None or cr is None:
            continue
        ca = cl[y]
        pairs = matched_pairs(ca, cr)
        if len(pairs) < 50:
            continue
        n = len(pairs)
        disp = np.array([cr["xy"][k] - ca["xy"][i] for i, k in pairs])
        src = np.array([ca["xy"][i] for i, _ in pairs])
        tree = cKDTree(src)
        kmax = min(max(K_SWEEP) + 1, n)
        _, nn = tree.query(src, k=kmax)

        # LEAVE-ONE-OUT global: the held-out pair excluded from its own median (fix iii).
        sx, sy = np.sort(disp[:, 0]), np.sort(disp[:, 1])

        def loo_global(t):
            m = np.ones(n, bool)
            m[t] = False
            return float(np.median(disp[m, 0])), float(np.median(disp[m, 1]))

        # k-sweep on centroid error only (cheap); the reported arm uses k_local.
        for kk in K_SWEEP:
            errs = []
            for t, (i, r_) in enumerate(pairs):
                idx = [q for q in nn[t][:kk + 1] if q != t][:kk]
                if len(idx) < 3:
                    continue
                dx, dy = float(np.median(disp[idx, 0])), float(np.median(disp[idx, 1]))
                errs.append(float(np.hypot(*(ca["xy"][i] + (dx, dy) - cr["xy"][r_]))))
            if errs:
                sweep.append({"epoch": y, "k": kk, "n": len(errs),
                              "median_err_m": round(st.median(errs), 4)})

        gmag = None
        if y in coreg and reference in coreg:
            gmag = float(np.hypot(
                float(coreg[reference]["median_dx_m"]) - float(coreg[y]["median_dx_m"]),
                float(coreg[reference]["median_dy_m"]) - float(coreg[y]["median_dy_m"])))

        for arm in ("naive", "global", "local"):
            errs, ious, ceil_iou, area_ceil = [], [], [], []
            for t, (i, r_) in enumerate(pairs):
                if arm == "naive":
                    dx = dy = 0.0
                elif arm == "global":
                    dx, dy = loo_global(t)
                else:
                    idx = [q for q in nn[t][:k_local + 1] if q != t][:k_local]
                    if len(idx) < 3:
                        continue
                    dx, dy = float(np.median(disp[idx, 0])), float(np.median(disp[idx, 1]))
                errs.append(float(np.hypot(*(ca["xy"][i] + (dx, dy) - cr["xy"][r_]))))
                v = iou_shift_cells(ca, i, cr, r_,
                                    -int(round(dy / CELL_M)), int(round(dx / CELL_M)))
                if v is not None:
                    ious.append(v)
                if arm == "naive":
                    # CEILINGS, measured: the best any whole-cell repositioning could do,
                    # and the ceiling the AREA_RATIO filter itself imposes.
                    best = max((iou_shift_cells(ca, i, cr, r_, a, b) or 0)
                               for a in (-2, -1, 0, 1, 2) for b in (-2, -1, 0, 1, 2))
                    ceil_iou.append(best)
                    aa, bb = ca["area"][i], cr["area"][r_]
                    area_ceil.append(min(aa, bb) / max(aa, bb))
            if not errs:
                continue
            errs.sort()
            rows.append({
                "epoch": y, "reference": reference, "arm": arm, "k": k_local if arm == "local" else "",
                "n_pairs": len(errs),
                "offset_mag_m": "" if gmag is None else round(gmag, 3),
                "median_err_m": round(st.median(errs), 3),
                "p90_err_m": round(errs[int(0.9 * (len(errs) - 1))], 3),
                "frac_within_1p5m": round(sum(e <= 1.5 for e in errs) / len(errs), 4),
                "frac_within_2m": round(sum(e <= 2.0 for e in errs) / len(errs), 4),
                "median_iou_cellquant": round(st.median(ious), 4) if ious else "",
                "median_iou_best_shift": round(st.median(ceil_iou), 4) if ceil_iou else "",
                "median_area_ceiling": round(st.median(area_ceil), 4) if area_ceil else "",
            })
    return rows, sweep, None


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", default="2021")
    ap.add_argument("--k", type=int, default=64, help="plateau of the k-sweep (32-128)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, sweep, err = build(a.reference, a.k)
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = ["epoch", "reference", "arm", "k", "n_pairs", "offset_mag_m",
            "median_err_m", "p90_err_m", "frac_within_1p5m", "frac_within_2m",
            "median_iou_cellquant", "median_iou_best_shift", "median_area_ceiling"]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    buf.write("# k_sweep (centroid error, metres)\n")
    for s in sweep:
        buf.write(f"# ksweep,{s['epoch']},{s['k']},{s['n']},{s['median_err_m']}\n")
    if not a.dry_run:
        (QC / "placement_accuracy.csv").write_text(buf.getvalue(), encoding="utf-8",
                                                   newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/placement_accuracy.csv "
          f"(reference {a.reference}, local k={a.k})")
    print(f"\n{'epoch':7}{'|offset|':>9}{'arm':8}{'med err':>9}{'<=1.5m':>8}"
          f"{'<=2m':>8}   resolvable?")
    for y in sorted({r["epoch"] for r in rows}):
        sel = {r["arm"]: r for r in rows if r["epoch"] == y}
        g = sel["naive"].get("offset_mag_m")
        # 3.5: below ~0.5 m of offset the predicted gain sits under this metric's
        # resolution, so the comparison is UNDETERMINED rather than null.
        note = "UNDETERMINED (offset below resolution)" if (g == "" or g < 0.5) else ""
        for arm in ("naive", "global", "local"):
            r = sel.get(arm)
            if not r:
                continue
            print(f"{y if arm == 'naive' else '':7}{(g if arm == 'naive' else ''):>9}"
                  f"{arm:8}{r['median_err_m']:>9.2f}{r['frac_within_1p5m']:>8.3f}"
                  f"{r['frac_within_2m']:>8.3f}   {note if arm == 'naive' else ''}")

    print("\nK-SWEEP (median of per-epoch median error, metres) — k=8 measures the "
          "estimator, not the world")
    for kk in K_SWEEP:
        v = [s["median_err_m"] for s in sweep if s["k"] == kk]
        if v:
            print(f"   k={kk:<4} {st.median(v):.3f}")
    for arm in ("naive", "global"):
        sel = [r for r in rows if r["arm"] == arm]
        print(f"   {arm:<6} {st.median([r['median_err_m'] for r in sel]):.3f}")

    nv = [r for r in rows if r["arm"] == "naive"]
    print(f"\nIoU CEILINGS (naive arm): observed {st.median([r['median_iou_cellquant'] for r in nv]):.3f}"
          f"  best whole-cell shift {st.median([r['median_iou_best_shift'] for r in nv]):.3f}"
          f"  area-ratio ceiling {st.median([r['median_area_ceiling'] for r in nv]):.3f}")
    print("  => most of the IoU deficit is DETECTED-EXTENT mismatch admitted by "
          "AREA_RATIO, not misplacement.")
    print("  => IoU here is quantized to whole 2 m cells; every measured shift is "
          "sub-cell, so it cannot resolve them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

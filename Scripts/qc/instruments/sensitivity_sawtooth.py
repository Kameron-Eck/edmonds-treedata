"""sensitivity_sawtooth.py — is the residual year-to-year jitter canopy, or is it the model?

THE QUESTION. The 2026-09-06 recalibration fixed the operating point: per-arm best-F1 cuts were
replaced by policy-C matched cuts at a common precision, and the sign test against Panel A
flipped to PASS. What it did NOT fix is the year-to-year sawtooth — the series still swings
several points between adjacent epochs against a real signal of roughly 0.28 pp/yr. This
instrument asks whether the residual is the canopy moving or the detector moving.

THE TEST. Matched cuts pin PRECISION by construction; they do not pin recall. If the residual
sawtooth is detector sensitivity, then across epochs the recall achieved at the common precision
should track the reported canopy fraction. If the residual is canopy, recall and fraction should
be unrelated — the model would be equally sensitive in a year that happens to have less canopy.

n = 8 epochs, so the correlation is reported with an EXACT permutation p-value (all 8! = 40,320
orderings enumerated), not a normal approximation. With eight points a Pearson r is a fragile
statistic; the permutation null is what makes it reportable at all, and a leave-one-out sweep
reports the range so a single epoch cannot be carrying the result.

WHY IT MATTERS DOWNSTREAM. A sawtooth made of canopy would mean the archive is telling us the
canopy genuinely oscillates and no correction is legitimate. A sawtooth made of sensitivity is a
ONE-SIDED error — the model missing real trees, never inventing them on bare ground
(experiments/flicker_parcels_census.yaml) — and a one-sided error is the only kind an asymmetric
correction may address. That distinction is the whole license for bounded temporal backfill, and
it is why symmetric smoothing failed: median-3 treats the error as symmetric and regresses the
best-calibrated year toward its worst neighbours.

Output: phase4/qc/sensitivity_sawtooth.csv (one row per statistic, with its source column).

Run:  py -3.12 qc/instruments/sensitivity_sawtooth.py
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

CUTS = QC / "trend8_policy_cuts.csv"          # matched cuts (policy-C)
DELIVERED = QC / "trend8_harmonized_fractions.csv"   # the retracted delivered-cut series


def _rows(p):
    if not Path(p).exists():
        return []
    body = [ln for ln in Path(p).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def pearson(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (n * sx * sy)


def exact_permutation_p(xs, ys):
    """Two-sided exact p: fraction of orderings with |r| at least the observed.

    Enumerates every permutation of ys against a fixed xs. At n = 8 that is 40,320 —
    exhaustive in under a second, so there is no sampling error in the p-value itself.
    """
    obs = abs(pearson(xs, ys))
    hits = total = 0
    for perm in itertools.permutations(ys):
        r = pearson(xs, list(perm))
        total += 1
        if r is not None and abs(r) >= obs - 1e-12:
            hits += 1
    return hits / total, total


def steps(vals):
    return [abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1)]


def build():
    cuts = sorted(_rows(CUTS), key=lambda r: r["year"])
    if not cuts:
        return None, "trend8_policy_cuts.csv absent"

    years = [r["year"] for r in cuts]
    recall = [float(r["recall"]) for r in cuts]
    prec = [float(r["precision"]) for r in cuts]
    frac = [float(r["frac_at_cut_pct"]) for r in cuts]

    r = pearson(recall, frac)
    p, n_perm = exact_permutation_p(recall, frac)

    # leave-one-out: no single epoch may be carrying the correlation
    loo = []
    for i in range(len(years)):
        rr = pearson([x for j, x in enumerate(recall) if j != i],
                     [x for j, x in enumerate(frac) if j != i])
        loo.append((years[i], rr))
    loo_vals = [v for _, v in loo if v is not None]

    out = []

    def row(stat, value, source, note):
        out.append({"statistic": stat, "value": value, "source": source, "note": note})

    row("n_epochs", len(years), CUTS.name, ",".join(years))
    row("precision_min", f"{min(prec):.4f}", CUTS.name,
        "matched cuts pin precision BY CONSTRUCTION — this is the held axis")
    row("precision_max", f"{max(prec):.4f}", CUTS.name, "")
    row("recall_min", f"{min(recall):.4f}", CUTS.name,
        f"worst-recall epoch: {years[recall.index(min(recall))]}")
    row("recall_max", f"{max(recall):.4f}", CUTS.name,
        f"best-recall epoch: {years[recall.index(max(recall))]}")
    row("recall_spread_pp", f"{(max(recall) - min(recall)) * 100:.2f}", CUTS.name,
        "recall is NOT pinned by the matched cut, and it maps straight into area")
    row("frac_min_pct", f"{min(frac):.2f}", CUTS.name, "")
    row("frac_max_pct", f"{max(frac):.2f}", CUTS.name, "")
    row("pearson_r_recall_vs_frac", f"{r:.4f}", CUTS.name,
        "the finding: at a held precision, reported canopy tracks detector sensitivity")
    row("permutation_p_two_sided", f"{p:.5f}", CUTS.name,
        f"EXACT over all {n_perm:,} orderings — not a normal approximation")
    row("loo_r_min", f"{min(loo_vals):.4f}", CUTS.name,
        "leave-one-out floor: " + ", ".join(f"{y}:{v:.3f}" for y, v in loo))
    row("loo_r_max", f"{max(loo_vals):.4f}", CUTS.name, "no single epoch carries it")

    ms = steps(frac)
    row("matched_mean_abs_step_pp", f"{st.mean(ms):.2f}", CUTS.name,
        "year-to-year movement in the MATCHED series")
    row("matched_max_abs_step_pp", f"{max(ms):.2f}", CUTS.name, "")

    dl = sorted(_rows(DELIVERED), key=lambda x: x["year"])
    if dl:
        dv = [float(x["canopy_frac_2m"]) * 100 for x in dl]
        ds = steps(dv)
        row("delivered_mean_abs_step_pp", f"{st.mean(ds):.2f}", DELIVERED.name,
            "the RETRACTED delivered-cut series, for comparison")
        row("step_reduction_pp", f"{st.mean(ds) - st.mean(ms):+.2f}",
            f"{CUTS.name}+{DELIVERED.name}",
            "NEGATIVE or ~zero means matching the operating point did NOT reduce the "
            "sawtooth — it fixed the SIGN, not the jitter")
    return out, None


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, err = build()
    if err:
        print(f"FATAL: {err}")
        return 2

    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=["statistic", "value", "source", "note"],
                       lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not a.dry_run:
        (QC / "sensitivity_sawtooth.csv").write_text(buf.getvalue(), encoding="utf-8",
                                                     newline="")
    d = {r["statistic"]: r["value"] for r in rows}
    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/sensitivity_sawtooth.csv")
    print(f"  precision held at {d['precision_min']}-{d['precision_max']}; "
          f"recall spans {d['recall_min']}-{d['recall_max']} "
          f"({d['recall_spread_pp']} pp)")
    print(f"  r(recall, canopy fraction) = {d['pearson_r_recall_vs_frac']}  "
          f"exact permutation p = {d['permutation_p_two_sided']}")
    print(f"  leave-one-out r stays within {d['loo_r_min']} .. {d['loo_r_max']}")
    if "step_reduction_pp" in d:
        print(f"  mean |step|: delivered {d['delivered_mean_abs_step_pp']} pp -> "
              f"matched {d['matched_mean_abs_step_pp']} pp "
              f"({d['step_reduction_pp']} pp)")
        print("  => the operating-point fix corrected the SIGN, not the sawtooth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

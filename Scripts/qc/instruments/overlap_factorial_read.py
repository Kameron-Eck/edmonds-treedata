"""Pre-registered overlap_floor reads (a) and (b) — at MATCHED operating points.

Per experiments/overlap_floor.yaml decision_rule and the 2026-09-06 attack
verdict: delivered per-arm best-F1 cuts are incomparable (650x eval-area
skew; two cliff-calibrated arms); the reads run at policy-C-matched cuts —
each arm cut within its own f1_plateau (F1 >= peak-0.005) at the HIGHEST
COMMON PRECISION all four plateaus support vs ccap_2021 (C-CAP as matcher,
never as level authority; the resulting LEVELS are 'harmonized-to-C-CAP').

READ (a) floor: |frac(2017 CoE) - frac(2017k King)| — same May 4-10 window,
zero real change; > 1.3pp (the C3 same-flight bound) => STOP RULE trips.
READ (b) factorial: season main effect = mean(Aug) - mean(May); grid effect
within each season; interaction; all vs the 1.3pp floor.

Output: phase4/qc/overlap_factorial_read.csv (+ stdout table).
"""
import csv
import io
from pathlib import Path

from lake import BASE

QC = BASE / "phase4" / "qc"
OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "overlap_factorial_read.csv"
ARMS = {  # tag -> (year, season, grid_label)
    "of_2017":  ("2017",  "May", "5cm"),
    "of_2017k": ("2017k", "May", "10cm"),
    "of_2017s": ("2017s", "Aug", "30cm"),
    "of_2017n": ("2017n", "Aug", "100cm"),
}
DELTA = 0.005


def load(tag, year):
    sw = QC / f"qc_indep_sweep_{year}_{tag}_ccap_2021_hires_lc.csv"
    rows = [r for r in csv.DictReader(io.open(sw, encoding="utf-8", newline=""))
            if r.get("f1", "").strip()]     # blank-f1 rows (degenerate cuts) excluded
    assert len(rows) >= 150, f"{sw.name}: only {len(rows)} usable cuts"
    # valid denominator from the run's report row (same prob, live)
    valid = None
    for r in csv.DictReader(io.open(QC / "qc_indep_report.csv", encoding="utf-8",
                                    newline="")):
        if (r["year"] == year and r.get("live") == "1" and tag in r["prob"]
                and r["canopy_def"] == "forest_wetland"):
            valid = int(r["valid"])
    assert valid, f"no live report row for {tag}"
    return rows, valid


def main():
    data = {t: load(t, y) for t, (y, _, _) in ARMS.items()}
    # per-arm plateau band (k -> row), and its precision range
    plat = {}
    for t, (rows, valid) in data.items():
        peak = max(float(r["f1"]) for r in rows)
        band = [r for r in rows if peak - float(r["f1"]) <= DELTA]
        plat[t] = band
        print(f"{t:10s} peakF1 {peak:.4f}  plateau {len(band)} cuts  "
              f"prec range {min(float(r['precision']) for r in band):.3f}-"
              f"{max(float(r['precision']) for r in band):.3f}")
    # highest common precision supported by every plateau
    p_common = min(max(float(r["precision"]) for r in plat[t]) for t in ARMS)
    print(f"\ncommon precision target: {p_common:.4f}")
    picks = {}
    for t in ARMS:
        cand = [r for r in plat[t] if float(r["precision"]) >= p_common]
        pick = min(cand, key=lambda r: float(r["precision"])) if cand else \
            max(plat[t], key=lambda r: float(r["precision"]))
        _, valid = data[t]
        frac = (int(pick["tp"]) + int(pick["fp"])) / valid
        picks[t] = dict(k=int(pick["k"]), thresh=pick["thresh"],
                        precision=float(pick["precision"]),
                        recall=float(pick["recall"]), frac=frac)
    rows_out = []
    print(f"\n{'arm':10s} {'k':>4s} {'prec':>6s} {'recall':>7s} {'frac%':>7s}")
    for t, (y, season, grid) in ARMS.items():
        p = picks[t]
        print(f"{t:10s} {p['k']:4d} {p['precision']:6.3f} {p['recall']:7.4f} "
              f"{100*p['frac']:7.2f}")
        rows_out.append(dict(tag=t, year=y, season=season, grid=grid, **p))
    f = {t: picks[t]["frac"] * 100 for t in ARMS}
    floor_gap = abs(f["of_2017"] - f["of_2017k"])
    may, aug = (f["of_2017"] + f["of_2017k"]) / 2, (f["of_2017s"] + f["of_2017n"]) / 2
    season_eff = aug - may
    grid_may = f["of_2017k"] - f["of_2017"]
    grid_aug = f["of_2017n"] - f["of_2017s"]
    quartet_spread = max(f.values()) - min(f.values())
    verdicts = [
        ("floor |CoE-King| same-window pp", round(floor_gap, 2),
         "STOP-RULE TRIPPED (>1.3)" if floor_gap > 1.3 else "PASS (<=1.3)"),
        ("season effect Aug-May pp", round(season_eff, 2), ""),
        ("grid effect May (10cm-5cm) pp", round(grid_may, 2), ""),
        ("grid effect Aug (1m-30cm) pp", round(grid_aug, 2), ""),
        ("quartet spread pp", round(quartet_spread, 2),
         "vs 10.1 delivered-cut spread"),
    ]
    print()
    for name, v, note in verdicts:
        print(f"  {name:34s} {v:+7.2f}  {note}")
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)
        fh.write("\n")
        w2 = csv.writer(fh)
        w2.writerow(["quantity", "value_pp", "note"])
        for name, v, note in verdicts:
            w2.writerow([name, v, note])
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

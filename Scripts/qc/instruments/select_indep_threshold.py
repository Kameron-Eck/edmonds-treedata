r"""select_indep_threshold.py — threshold policy C: pick the operating cut from
the INDEPENDENT dense sweep, never from circular labels.

Decided by Kam 2026-09-01 ("Let's go with C") after the recipe audit measured
the circular best-F1 selection costing 2011s 23 recall points and a 54% canopy-
area swing (Reports/RECIPE_AUDIT_2026-09-01.md). Policy, pre-registered:

  criterion   PLATEAU-HIGH: the HIGHEST k whose F1 is within PLATEAU_DELTA
              (0.005) of the curve's peak — F1 on the PRIMARY canopy definition
              (forest_wetland), raw prob (morphology measured neutral — audit
              report, variant CSV). WHY not strict argmax: both pilot curves are
              flat within 0.005 across a 3x threshold range (2011s k=28..80,
              2006s k=25..85 — at ~120M cells that plateau is metric
              indifference, not noise), and strict argmax deploys the sloppy
              recall-most edge (k=36, prec .716) when the precision-most end of
              the SAME plateau (k=80, prec .755) is indistinguishable in F1.
              Preferring precision inside the plateau also answers the C-CAP
              caveat: the reference's canopy definition is broad (gaps,
              understory), so crown-deliverable truth sits above its optimum.
  fallback    an unscorable/missing sweep -> NO row written, exit 2; the year
              deploys fixed 0.5 with a loud flag — NEVER silently circular
  deployment  postproc --infer-thresh <thresh>; k/254 round-trips to the same
              integer cut, so the selected and deployed cuts are identical

Reads  qc_indep_sweep_{year}_{arm}_{refstem}.csv   (writer: phase4_qc_indep._write_dense_sweep)
Writes phase4/qc/indep_thresholds.csv              (one row per (year, run_tag, ref); replace-by-key)

The registry row is the provenance home: comparisons must not pool arms across
threshold policy (circular-champion rows vs policy-C rows) — see docs/SCHEMAS.md.

Usage:
  py -3.12 qc/instruments/select_indep_threshold.py --year 2011s --tag hy_e3_2011s
  py -3.12 ... --year 2006s --tag hy_e3_2006s --ref-stem ccap_2016_hires_lc  (sensitivity only)
"""
import argparse
import csv
import datetime as _dt
from pathlib import Path

from lake import BASE   # installed shared module (pyproject py-modules)

QC_DIR = BASE / "phase4" / "qc"
REGISTRY = QC_DIR / "indep_thresholds.csv"
DEFAULT_REF_STEM = "ccap_2021_hires_lc"          # the deployment reference
PLATEAU_DELTA = 0.005                             # F1 indifference band (see docstring)
CRITERION = "f1_plateau_hi_d005"
EDGE_K = 5                                        # peak within 5 steps of 1/254 = suspect

FIELDS = ["year", "run_tag", "ref", "criterion", "k", "thresh", "f1", "recall",
          "precision", "edge_flag", "sweep_file", "ts"]


def pick(sweep_path):
    rows = list(csv.DictReader(open(sweep_path, encoding="utf-8")))
    if not rows:
        raise SystemExit(f"UNSELECTABLE: {sweep_path} is empty — no row written; "
                         f"deploy fixed 0.5 with a loud flag, never circular. (exit 2)")
    scored = [r for r in rows if r["f1"]]
    if not scored:
        raise SystemExit(f"UNSELECTABLE: {sweep_path} has no scorable F1 row. (exit 2)")
    peak = max(float(r["f1"]) for r in scored)
    # PLATEAU-HIGH: highest k the metric cannot distinguish from the peak.
    best = max((r for r in scored if peak - float(r["f1"]) <= PLATEAU_DELTA),
               key=lambda r: int(r["k"]))
    k = int(best["k"])
    edge = "EDGE" if (k <= EDGE_K or k >= 255 - EDGE_K) else ""
    return best, rows, edge


def main():
    ap = argparse.ArgumentParser(description="Pick the policy-C operating threshold.")
    ap.add_argument("--year", required=True)
    ap.add_argument("--tag", required=True, help="run tag (the arm), e.g. hy_e3_2011s")
    ap.add_argument("--ref-stem", default=DEFAULT_REF_STEM,
                    help="reference raster stem; non-default runs are sensitivity "
                         "checks and land in the registry under their own ref key")
    ap.add_argument("--sweep", default=None, help="explicit sweep CSV (overrides lookup)")
    args = ap.parse_args()

    sweep_path = (Path(args.sweep) if args.sweep else
                  QC_DIR / f"qc_indep_sweep_{args.year}_{args.tag}_{args.ref_stem}.csv")
    if not sweep_path.exists():
        raise SystemExit(f"UNSELECTABLE: {sweep_path} not found — run the dense sweep "
                         f"first (phase4_qc_indep --year {args.year} --prob <arm prob>). (exit 2)")

    best, rows, edge = pick(sweep_path)
    k = int(best["k"])
    print(f"[select-indep] {args.year}/{args.tag} vs {args.ref_stem}: "
          f"k={k} thresh={float(best['thresh']):.4f} f1={best['f1']} "
          f"rec={best['recall']} prec={best['precision']}"
          f"{'  ** EDGE-OF-GRID — inspect the curve **' if edge else ''}")
    by_k = {int(r["k"]): r for r in rows}
    for kk in range(max(1, k - 3), min(254, k + 3) + 1):
        r = by_k.get(kk)
        if r:
            mark = " <-- chosen" if kk == k else ""
            print(f"    k={kk:<4} thr={float(r['thresh']):.4f} f1={r['f1']:<7} "
                  f"rec={r['recall']:<7} prec={r['precision']}{mark}")

    row = dict(year=args.year, run_tag=args.tag, ref=best["ref"], criterion=CRITERION,
               # FLOOR-truncate, never round: a 6-dp round can land just ABOVE
               # k/254, and the scorer's float compare (pr >= thr*254) then cuts
               # at k+1 while production's int(round()) still cuts at k. A
               # floored value sits in (k-1, k] where BOTH cut at k. Measured
               # 2026-09-01: rounded 0.314961 scored k=81 (rec -0.0008).
               k=k, thresh=int(k / 254.0 * 1e6) / 1e6, f1=best["f1"], recall=best["recall"],
               precision=best["precision"], edge_flag=edge, sweep_file=sweep_path.name,
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    keep = []
    if REGISTRY.exists():
        keep = [r for r in csv.DictReader(open(REGISTRY, encoding="utf-8"))
                if not (r["year"] == row["year"] and r["run_tag"] == row["run_tag"]
                        and r["ref"] == row["ref"])]
    with open(REGISTRY, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in keep:
            w.writerow({c: r.get(c, "") for c in FIELDS})
        w.writerow(row)
    print(f"[select-indep] registered -> {REGISTRY}  "
          f"(deploy: --infer-thresh {row['thresh']})")


if __name__ == "__main__":
    main()

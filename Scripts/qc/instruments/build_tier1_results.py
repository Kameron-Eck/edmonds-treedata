"""Tier-1 science sample results table (experiments/tier1_science_sample.yaml).

One row per scored arm from the TEST-block dense sweeps:
  primary  = max recall among cuts with precision >= 0.75 (pre-registered)
  also: the policy-C deployed operating point (from indep_thresholds.csv,
        selection-sweep pick) evaluated on the test sweep at that exact k,
  and delta_* columns vs the same year's base arm.
Writes phase4/qc/tier1_results.csv (repo copy, tracked measured text).
"""
import csv
import sys
from pathlib import Path

BASE = Path(r"G:\My Drive\treedata")
QC = BASE / "phase4" / "qc"
OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "tier1_results.csv"
PREC_FLOOR = 0.75

def read_sweep(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def main():
    rows = []
    for sw in sorted(QC.glob("qc_indep_sweep_*_t1_*_ccap_2021_hires_lc_sample-test.csv")):
        name = sw.name[len("qc_indep_sweep_"):-len("_ccap_2021_hires_lc_sample-test.csv")]
        year, tag = name.split("_t1_", 1)
        tag = "t1_" + tag
        data = read_sweep(sw)
        if len(data) != 254:
            print(f"SKIP {sw.name}: {len(data)} cuts (want 254)", file=sys.stderr)
            continue
        # primary: max recall subject to precision >= floor
        elig = [r for r in data if float(r["precision"]) >= PREC_FLOOR]
        if elig:
            best = max(elig, key=lambda r: float(r["recall"]))
            prim_r, prim_p, prim_k = float(best["recall"]), float(best["precision"]), int(best["k"])
        else:
            prim_r = prim_p = float("nan"); prim_k = -1
        # deployed policy-C point (selection pick) on the test curve
        dep = {}
        with open(QC / "indep_thresholds.csv", newline="") as f:
            for r in csv.DictReader(f):
                if r["year"] == year and r["run_tag"] == tag:
                    dep = r
        dep_k = int(dep["k"]) if dep else -1
        dk = next((r for r in data if int(r["k"]) == dep_k), None)
        rows.append({
            "year": year, "tag": tag,
            "recall_at_p75": round(prim_r, 4), "prec_at_p75": round(prim_p, 4),
            "k_at_p75": prim_k, "n_eligible_cuts": len(elig),
            "dep_k": dep_k,
            "dep_recall": round(float(dk["recall"]), 4) if dk else "",
            "dep_precision": round(float(dk["precision"]), 4) if dk else "",
            "sweep_file": sw.name,
        })
    # deltas vs the year's base arm (replicates s2/s3 map to base)
    base = {r["year"]: r for r in rows if r["tag"].endswith("_base")}
    for r in rows:
        b = base.get(r["year"])
        if b and r is not b and isinstance(r["recall_at_p75"], float):
            r["delta_recall_at_p75"] = round(r["recall_at_p75"] - b["recall_at_p75"], 4)
        else:
            r["delta_recall_at_p75"] = ""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["year","tag","recall_at_p75","prec_at_p75","k_at_p75","n_eligible_cuts",
            "dep_k","dep_recall","dep_precision","delta_recall_at_p75","sweep_file"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} arms)")
    for r in rows:
        print(f"  {r['year']:6s} {r['tag']:22s} r@p75={r['recall_at_p75']} d={r['delta_recall_at_p75']}")

if __name__ == "__main__":
    main()

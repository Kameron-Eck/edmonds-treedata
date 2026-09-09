"""backbone_benchmark.py — the resnet101 reference table a smaller encoder must reproduce.

WHY (Kam, 2026-09-08: "create the benchmark table, and run the resnet 18 and 50
tonight"). The Tier-1 sample campaign (experiments/tier1_science_sample.yaml) measured
28 arms on resnet101, LOSO on the 33 ground blocks. Before a smaller encoder can take
over recipe search, its rankings have to be checked against those numbers — and the
numbers have to be pinned in ONE tracked file rather than re-read from a 789-row
arm_metrics.csv every time, where the same arm carries 2-3 rows per policy (one per
reference raster) and picking the wrong one is a silent 5 pp error.

WHAT IT IS. A pure PROJECTION of phase4/qc/arm_metrics.csv (harvest_arm_metrics.py):
no lake, no GPU, no new measurement. For each of the nine benchmark arms it copies the
`matched_p75` and `best_f1` rows measured on the sample-test population against the
C-CAP 2021 reference — the SAME (ref, canopy_def, eval_scope) triple that
phase4/qc/tier1_results.csv and the Tier-1 verdict were read from — VERBATIM (strings,
never re-rounded), so the table is byte-identical across runs and a checkout
regenerates it (test_backbone_benchmark.py::test_benchmark_csv_is_fresh).

THE NINE ARMS, and why these (verdict text: experiments/tier1_science_sample.yaml):
    five base arms      t1_{2006s,2011s,2016,2019n,2020}_base — one per sample year
    two seed replicates t1_2011s_base_s2 / _s3 — with 2011s base, the three-seed
                        noise floor (max pairwise |delta| in recall at precision 0.75)
    positive pair       t1_2016_in05 vs t1_2016_base — LIDAR-INPUT CONFIRMED 3/3, and
                        2016 in05 is the largest of the six (+.075 in tier1_results.csv)
    null pair           t1_2011s_cor05 vs t1_2011s_base — the corruption dose the
                        verdict recorded as flat (-.0002, inside the floor)
A small encoder that reproduces the positive as positive and the null as null, each
relative to ITS OWN three-seed floor, is licensed for recipe search
(experiments/backbone_sweep.yaml, decision_rule (c)).

NOISE-FLOOR BLOCK. Rows with arm = NOISE_FLOOR_2011s carry, per policy, the min, max
and spread (max - min) of recall / precision / f1 / pr_auc over the three 2011s seeds.
`spread` on recall at matched_p75 is the floor the Tier-1 verdict used. Derived here
from the same rows, so it cannot drift from them.

Run:  py -3.12 qc/instruments/backbone_benchmark.py            (writes the CSV)
      py -3.12 qc/instruments/backbone_benchmark.py --stdout   (print, write nothing)
"""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
ARM_METRICS = QC / "arm_metrics.csv"
OUT = QC / "backbone_benchmark.csv"

# The encoder every Tier-1 arm ran on. Read from the run manifests via
# run_passport.csv (column `encoder`) — the constant here names the reference, it does
# not measure it; test_backbone_benchmark.py checks it against the passports.
REFERENCE_ENCODER = "resnet101"

# The population every number here is read on. MUST match tier1_results.csv's basis:
# C-CAP 2021 hires, forest+wetland canopy definition, the LOSO sample-TEST blocks.
REF = "ccap_2021_hires_lc.tif"
CANOPY_DEF = "forest_wetland"
EVAL_SCOPE = "sample-test"
POLICIES = ("matched_p75", "best_f1")

# (year label, run tag) in report order. The instrument OWNS this list; the sweep
# experiment derives its arms from it (gated).
BENCHMARK_ARMS = (
    ("2006s", "t1_2006s_base"),
    ("2011s", "t1_2011s_base"),
    ("2011s", "t1_2011s_base_s2"),
    ("2011s", "t1_2011s_base_s3"),
    ("2011s", "t1_2011s_cor05"),
    ("2016", "t1_2016_base"),
    ("2016", "t1_2016_in05"),
    ("2019n", "t1_2019n_base"),
    ("2020", "t1_2020_base"),
)
NOISE_FLOOR_ARMS = ("t1_2011s_base", "t1_2011s_base_s2", "t1_2011s_base_s3")
NOISE_FLOOR_LABEL = "NOISE_FLOOR_2011s"

COLS = ["arm", "year_label", "treatment", "encoder", "policy", "population",
        "recall", "precision", "f1", "pr_auc", "thresh", "n_eligible_cuts",
        "curve_id", "source"]


def treatment_of(year, tag):
    """`t1_2011s_base_s2` -> `base_s2`; the part after the year label."""
    prefix = f"t1_{year}_"
    return tag[len(prefix):] if tag.startswith(prefix) else tag


def _rows(path):
    body = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def select(metrics, year, tag, policy):
    """The ONE arm_metrics row for (year, tag, policy) on the benchmark population.

    Zero rows is an error (the arm was never scored on this basis); more than one is
    an error too — the population key is supposed to be unique, and a silent
    first-match is how 2016's ccap_2016 row could stand in for its ccap_2021 one.
    """
    hits = [r for r in metrics
            if r["year"] == year and r["run_tag"] == tag and r["policy"] == policy
            and r["ref"] == REF and r["canopy_def"] == CANOPY_DEF
            and r["eval_scope"] == EVAL_SCOPE]
    if len(hits) != 1:
        raise SystemExit(
            f"{len(hits)} arm_metrics rows for ({year}, {tag}, {policy}) on "
            f"ref={REF} canopy_def={CANOPY_DEF} eval_scope={EVAL_SCOPE} — expected "
            f"exactly one (re-harvest: py -3.12 qc/instruments/harvest_arm_metrics.py)")
    return hits[0]


def _fmt(x):
    return f"{x:.4f}"


def build(metrics=None):
    """The table, as a list of dicts (COLS order) — deterministic for a given input."""
    metrics = _rows(ARM_METRICS) if metrics is None else metrics
    out = []
    for year, tag in BENCHMARK_ARMS:
        for pol in POLICIES:
            r = select(metrics, year, tag, pol)
            out.append({
                "arm": tag, "year_label": year, "treatment": treatment_of(year, tag),
                "encoder": REFERENCE_ENCODER, "policy": pol,
                "population": r["population"],
                "recall": r["recall"], "precision": r["precision"], "f1": r["f1"],
                "pr_auc": r["pr_auc"], "thresh": r["thresh"],
                "n_eligible_cuts": r["n_eligible_cuts"], "curve_id": r["curve_id"],
                "source": "phase4/qc/arm_metrics.csv",
            })
    # Noise-floor block: min / max / spread over the three 2011s seeds, per policy.
    for pol in POLICIES:
        seeds = [select(metrics, "2011s", t, pol) for t in NOISE_FLOOR_ARMS]
        stats = {}
        for col in ("recall", "precision", "f1", "pr_auc"):
            vals = [float(s[col]) for s in seeds]
            stats[col] = (min(vals), max(vals), max(vals) - min(vals))
        for i, stat in enumerate(("min", "max", "spread")):
            out.append({
                "arm": NOISE_FLOOR_LABEL, "year_label": "2011s", "treatment": stat,
                "encoder": REFERENCE_ENCODER, "policy": pol, "population": "",
                "recall": _fmt(stats["recall"][i]),
                "precision": _fmt(stats["precision"][i]),
                "f1": _fmt(stats["f1"][i]), "pr_auc": _fmt(stats["pr_auc"][i]),
                "thresh": "", "n_eligible_cuts": "", "curve_id": "",
                "source": "+".join(NOISE_FLOOR_ARMS),
            })
    return out


def render(rows=None):
    """CSV text: LF line ends, no trailing whitespace — byte-stable across platforms."""
    rows = build() if rows is None else rows
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    a = ap.parse_args(clean_argv() if argv is None else argv)
    text = render()
    if a.stdout:
        print(text, end="")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="")
    n_arms = len(BENCHMARK_ARMS)
    print(f"wrote {OUT.relative_to(REPO)}: {n_arms} arms x {len(POLICIES)} policies "
          f"+ {3 * len(POLICIES)} noise-floor rows")
    floor = [r for r in build() if r["arm"] == NOISE_FLOOR_LABEL
             and r["treatment"] == "spread" and r["policy"] == "matched_p75"][0]
    print(f"  noise floor (2011s three seeds, matched_p75): recall spread "
          f"{floor['recall']}, precision spread {floor['precision']}, f1 spread {floor['f1']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

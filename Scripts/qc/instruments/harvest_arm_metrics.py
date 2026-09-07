"""harvest_arm_metrics.py — precision and recall with their operating point attached.

THE RULE THIS ENFORCES. Precision and recall are not properties of a model. They are
properties of a (model, threshold, evaluation population) triple. Storing the pair
alone is what let three deliveries of ONE 2017 flight appear to disagree by 10.09 pp
of citywide canopy when, at reference-matched cuts, they disagree by 1.07 — nothing
about the imagery differed, only the cut each arm was scored at. So every row here
carries its threshold, the POLICY that chose it, the counts behind it, and the size of
the population it was measured on.

TWO TRACKED ARTIFACTS:

    phase4/qc/arm_metrics.csv       one row per (curve, policy) — tidy, queryable
    phase4/qc/curves/{id}.csv       the full PR sweep: k, thresh, tp, fn, fp,
                                    recall, precision, f1 at all 254 cuts

The curve is the primitive; every scalar anyone quotes is a projection of it. All 87
sweeps prune to 1.15 MB, so they are tracked in full rather than decimated — with the
curve in the repo, any future operating-point question is answerable from a checkout,
without the lake and without re-running a GPU.

WHY PR-AUC AND NOT AUROC. A sweep records tp/fn/fp but not tn, so AUROC is not
computable from it — and that is the right outcome anyway. Canopy scoring here runs at
roughly 650x class skew, where AUROC is dominated by the vast true-negative mass and
reads optimistically high for everything. Average precision (the area under the
precision-recall curve) is the honest threshold-free summary under skew, and it is
what `pr_auc` holds. Where a proper AUROC with confidence intervals exists, it lives
in the instrument that could compute it (phase4_chm_standalone_roc.py -> the
chm_standalone_roc_*_arms.csv family) and is not duplicated here.

THE POLICIES (closed set — `POLICIES`, gated by test_run_context.py):

    best_f1        the cut maximising F1 for THIS arm. What generally got deployed,
                   and therefore what must be recorded — but per-arm best-F1 cuts are
                   exactly what makes a uniform-recipe series sawtooth, so this is
                   never the basis for a cross-arm or cross-year comparison.
    matched_p50    the STEADY points: highest recall at precision >= 0.50 / 0.75 /
    matched_p75    0.90. One axis held constant so the other is comparable across
    matched_p90    arms and years. `n_eligible_cuts` says how many cuts were even
                   available to match at — a match found among a handful is a corner
                   artifact, not a measurement (the -.503 lesson).
    scored_live    the cut the shipped mask was actually made at, taken from the
                   live=1 rows of qc_indep_report.csv rather than from the curve.

Run:  py -3.12 qc/instruments/harvest_arm_metrics.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import math
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

CURVE_COLS = ("k", "thresh", "tp", "fn", "fp", "recall", "precision", "f1")
MATCH_LEVELS = (0.50, 0.75, 0.90)
POLICIES = ("best_f1", "matched_p50", "matched_p75", "matched_p90", "scored_live")

COLS = [
    "curve_id", "year", "run_tag", "ref", "prob", "canopy_def", "eval_scope",
    "policy", "k", "thresh", "recall", "precision", "f1",
    "tp", "fn", "fp", "population",
    "pr_auc", "n_cuts", "n_eligible_cuts", "source", "curve_file",
]


def eval_scope(sweep_name, ref):
    """The evaluation POPULATION a sweep was measured on, read off its filename.

    Sweeps are named qc_indep_sweep_{year}_{tag}_{ref-stem}[_{scope}].csv, and the
    scope suffix is what distinguishes the LOSO halves: `sample-selection` blocks vs
    `sample-test` blocks are DIFFERENT populations of the same arm. Leaving it out of
    the curve key made those two collide, and the first one written silently won —
    which is the very failure this module exists to prevent (the third leg of the
    triple is the population). Found 2026-09-06 on the first harvest: 87 sweeps were
    collapsing into 58 ids.

    Generic by construction: take whatever follows the reference's stem, so a scope
    this project has not invented yet still separates instead of colliding.
    """
    stem = Path(sweep_name).stem
    ref_stem = Path(str(ref)).stem
    if ref_stem and ref_stem in stem:
        return stem.split(ref_stem, 1)[1].lstrip("_")
    return ""


def curve_id(year, tag, ref, prob, canopy_def, scope=""):
    """Identity of ONE measured curve: the model, what scored it, and on which pixels.

    `scope` is not optional in spirit — it defaults to empty only so a citywide
    scoring (which has no scope suffix) keys naturally.
    """
    key = "|".join((year, tag, ref, prob, canopy_def, scope))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _f(v, default=None):
    """Parse a float, treating NaN/inf as ABSENT rather than as a value.

    A sweep's extreme cuts can have tp = fp = 0, where precision is 0/0 and the writer
    records `nan`. Those points carry no information; letting one through poisons the
    whole area under the curve (every pr_auc read `nan` on the first harvest).
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def average_precision(cuts):
    """Area under the precision-recall curve, trapezoid over recall.

    Sorted by ascending recall so the integral is well defined regardless of the
    order the sweep happened to be written in. Returns None if fewer than two usable
    points — an area through one point is not a measurement.
    """
    pts = sorted({(_f(c["recall"]), _f(c["precision"])) for c in cuts
                  if _f(c["recall"]) is not None and _f(c["precision"]) is not None})
    if len(pts) < 2:
        return None
    area = 0.0
    for (r0, p0), (r1, p1) in zip(pts, pts[1:]):
        area += (r1 - r0) * (p0 + p1) / 2.0
    return round(area, 4)


def pick(cuts, policy):
    """Return (cut, n_eligible) for a policy, or (None, 0).

    matched_*: among cuts meeting the precision floor, the one with the HIGHEST
    recall — the honest read of "what can this arm find while staying this clean".
    """
    if policy == "best_f1":
        usable = [c for c in cuts if _f(c["f1"]) is not None]
        return (max(usable, key=lambda c: _f(c["f1"])) if usable else None), len(usable)
    if policy.startswith("matched_p"):
        floor = int(policy.split("_p")[1]) / 100.0
        elig = [c for c in cuts if (_f(c["precision"]) or -1) >= floor]
        return (max(elig, key=lambda c: _f(c["recall"])) if elig else None), len(elig)
    raise ValueError(f"pick() does not serve policy {policy!r}")


def _sweep_dir():
    from phase4seg import config
    for cand in (Path(config.BASE) / "phase4" / "qc",
                 Path(r"G:/My Drive/treedata/phase4/qc")):
        if cand.exists():
            return cand
    return cand


def harvest_curves(sweep_dir, curves_dir, dry_run=False):
    rows, written = [], 0
    for f in sorted(Path(sweep_dir).glob("qc_indep_sweep_*.csv")):
        cuts = list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))))
        if not cuts:
            continue
        h = cuts[0]
        scope = eval_scope(f.name, h.get("ref", ""))
        cid = curve_id(h.get("year", ""), h.get("run_tag", ""), h.get("ref", ""),
                       h.get("prob", ""), h.get("canopy_def", ""), scope)
        if not dry_run:
            curves_dir.mkdir(parents=True, exist_ok=True)
            dst = curves_dir / f"{cid}.csv"
            if not dst.exists():          # immutable per (arm, ref, population)
                buf = io.StringIO(newline="")
                w = csv.writer(buf, lineterminator="\n")
                w.writerow(CURVE_COLS)
                for c in cuts:
                    w.writerow([c.get(k, "") for k in CURVE_COLS])
                dst.write_text(buf.getvalue(), encoding="utf-8", newline="")
                written += 1

        ap = average_precision(cuts)
        for policy in ("best_f1",) + tuple(f"matched_p{int(m * 100)}"
                                           for m in MATCH_LEVELS):
            cut, n_elig = pick(cuts, policy)
            if cut is None:
                continue
            tp, fn, fp = (_f(cut["tp"]), _f(cut["fn"]), _f(cut["fp"]))
            rows.append({
                "curve_id": cid, "year": h.get("year", ""),
                "run_tag": h.get("run_tag", ""), "ref": h.get("ref", ""),
                "prob": h.get("prob", ""), "canopy_def": h.get("canopy_def", ""),
                "eval_scope": scope, "policy": policy, "k": cut.get("k", ""), "thresh": cut.get("thresh", ""),
                "recall": cut.get("recall", ""), "precision": cut.get("precision", ""),
                "f1": cut.get("f1", ""), "tp": cut.get("tp", ""),
                "fn": cut.get("fn", ""), "fp": cut.get("fp", ""),
                "population": int(tp + fn + fp) if None not in (tp, fn, fp) else "",
                "pr_auc": ap if ap is not None else "",
                "n_cuts": len(cuts), "n_eligible_cuts": n_elig,
                "source": f.name, "curve_file": f"phase4/qc/curves/{cid}.csv",
            })
    return rows, written


def harvest_live_points():
    """The cut the shipped mask was actually made at — from the tracked report."""
    p = QC / "qc_indep_report.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(p.read_text(encoding="utf-8").splitlines()):
        if r.get("live", "").strip() != "1":
            continue
        tp, fn, fp = _f(r["tp"]), _f(r["fn"]), _f(r["fp"])
        prec, rec = _f(r["precision"]), _f(r["recall"])
        f1 = (round(2 * prec * rec / (prec + rec), 4)
              if prec and rec and (prec + rec) else "")
        cid = curve_id(r.get("year", ""), r.get("run_tag", ""), r.get("ref", ""),
                       r.get("prob", ""), r.get("canopy_def", ""))  # citywide: no scope
        out.append({
            "curve_id": cid, "year": r.get("year", ""),
            "run_tag": r.get("run_tag", ""), "ref": r.get("ref", ""),
            "prob": r.get("prob", ""), "canopy_def": r.get("canopy_def", ""),
            "eval_scope": "", "policy": "scored_live", "k": "", "thresh": r.get("thresh", ""),
            "recall": r.get("recall", ""), "precision": r.get("precision", ""),
            "f1": f1, "tp": r.get("tp", ""), "fn": r.get("fn", ""),
            "fp": r.get("fp", ""),
            "population": int(tp + fn + fp) if None not in (tp, fn, fp) else "",
            "pr_auc": "", "n_cuts": "", "n_eligible_cuts": "",
            "source": "qc_indep_report.csv", "curve_file": "",
        })
    return out


def main(argv=None):
    from phase4seg.names import clean_argv
    ap_ = argparse.ArgumentParser(description=__doc__)
    ap_.add_argument("--sweep-dir", default=None)
    ap_.add_argument("--dry-run", action="store_true")
    a = ap_.parse_args(clean_argv() if argv is None else argv)

    sweep_dir = Path(a.sweep_dir) if a.sweep_dir else _sweep_dir()
    curves_dir = QC / "curves"
    rows, written = ([], 0)
    if sweep_dir.exists():
        rows, written = harvest_curves(sweep_dir, curves_dir, a.dry_run)
    else:
        print(f"  ! sweeps not found at {sweep_dir} — curve policies skipped "
              f"(lake not mounted); live points still harvested")
    rows += harvest_live_points()
    rows.sort(key=lambda r: (r["year"], r["run_tag"], r["policy"], r["curve_id"]))

    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not a.dry_run:
        QC.mkdir(parents=True, exist_ok=True)
        (QC / "arm_metrics.csv").write_text(buf.getvalue(), encoding="utf-8",
                                            newline="")

    per = {}
    for r in rows:
        per[r["policy"]] = per.get(r["policy"], 0) + 1
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} operating points over "
          f"{len({r['curve_id'] for r in rows})} curves → phase4/qc/arm_metrics.csv")
    print("  " + " · ".join(f"{k} {v}" for k, v in sorted(per.items())))
    if not a.dry_run and written:
        print(f"  wrote {written} new curve file(s) under phase4/qc/curves/")
    thin = [r for r in rows if r["n_eligible_cuts"] not in ("", None)
            and int(r["n_eligible_cuts"]) < 10]
    if thin:
        print(f"  ! {len(thin)} matched point(s) found among fewer than 10 eligible "
              f"cuts — corner artifacts, not measurements")
    return 0


if __name__ == "__main__":
    sys.exit(main())

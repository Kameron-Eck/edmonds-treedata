r"""Did the pilot prove the MACHINERY? Four artifacts per year, or the 36-year run waits.

THE GATE, from the overhaul plan's Stage 5, verbatim in intent:

    Each pilot year must produce: a mask, an independently scored row, a manifest
    carrying EPOCH and architecture provenance, and a STATUS.md that updates without
    hand-editing. Gate: if any of those four is missing OR REQUIRES A MANUAL STEP, the
    machinery is not finished and the 36-year run does not start.

The second clause is the one that needs a tool. "Missing" is obvious the moment you look;
"required a manual step" is not, because a human who typed the step then sees the artifact
and reports success. This script only ever reads what the QUEUE produced — it never runs a
pipeline step itself — so an artifact that is present here is one the queue made.

WHY THIS IS NOT A pytest. It reads the data lake, which CI cannot see and which the test
suite is forbidden to touch (qc/conftest.py). It is an instrument, run against a finished
campaign, and it prints a verdict rather than asserting one.

  py -3.12 qc/pilot_gate.py
  py -3.12 qc/pilot_gate.py --queue-stem pilot_2019_fine     # one arm
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent

from phase4seg.names import status_files  # noqa: E402

_COLAB = Path("/content/drive/MyDrive/treedata")
BASE = _COLAB if _COLAB.exists() else Path(r"G:\My Drive\treedata")

MASKS = BASE / "phase4" / "masks"
RUNS = BASE / "phase4" / "runs"
QC = BASE / "phase4" / "qc"
INDEP = QC / "qc_indep_report.csv"

# The independent reference. NOT an arbitrary pick: 57 live rows already use it, including
# every prior 2019 and 2019n scoring, so the pilot's rows stay comparable with them. It is
# also the nearer vintage to a 2019 flight than ccap_2016 is, and both hires rasters cover
# the same Edmonds footprint. C-CAP is EVALUATION ONLY and never a label source.
#
# 2019s has NEVER been independently scored — it appears in no live row. The pilot will
# produce its first, which is worth knowing before reading that number as a comparison.
REF_CCAP = BASE / "Full_Image" / "Pipeline Imagery" / "ccap_2021_hires_lc.tif"

# (year label, run tag) — the three arms of pipeline/pilot_2019_*.yaml.
DEFAULT_EXPERIMENT = Path(__file__).resolve().parents[1] / "experiments" / "pilot_2019.yaml"


def load_arms(experiment_path):
    """(year, tag) pairs from an experiments/*.yaml file (schema: experiments/README.md).

    The gate generalised 2026-09-01: the checks below were never pilot-specific —
    deliverable exists, independent score present, manifest carries EPOCH, ledger
    complete — so ANY experiment can be gated with --experiment. The pilot file is
    the default for continuity with `py -3.12 qc/pilot_gate.py`."""
    import yaml
    spec = yaml.safe_load(Path(experiment_path).read_text(encoding="utf-8"))
    return [(str(a["year"]), str(a["tag"])) for a in spec["arms"]], spec


from lake import read_retry as _retry   # noqa: E402 — ONE home (lake.py); the
# mirror-blinks mechanism and the retry-the-LISTING lesson are documented there.


def _rows(p):
    def _once():
        try:
            with open(p, encoding="utf-8", newline="") as f:
                return list(csv.DictReader(f))
        except OSError:
            return []
    return _retry(_once)


def check_mask(label, tag):
    """(1) THE DELIVERABLE. A binary canopy mask GPKG, polygonised by step_postproc.

    This is the artifact the whole project exists to produce, and until U3 the queue did
    not run the step that makes it: STEPS omitted `postproc`, so `--skip-postproc` in a
    queue file was a no-op skipping a step that never ran. A pilot that produces no GPKG
    means the fix did not take.
    """
    g = MASKS / f"edmonds_canopy_mask_{label}_{tag}.gpkg"
    if _retry(lambda: g.exists() or None, tries=4):
        return True, f"{g.name} ({g.stat().st_size / 1e6:.1f} MB)"
    near = sorted(p.name for p in MASKS.glob(f"edmonds_canopy_mask_{label}*.gpkg"))
    return False, ("no GPKG for this arm" +
                   (f"; other {label} masks present: {near}" if near else ""))


def check_scored(label, tag):
    """(2) AN INDEPENDENT ROW. Scored against reference data, not against the 2020 mask
    reprojected onto this year — that comparison is CIRCULAR and real change counts as
    model error. Matched on the `prob` column, the raster THIS arm produced, for the same
    reason registry_from_manifests::honest_metrics matches on it: timestamps cannot
    arbitrate (the VM writes UTC, qc_indep writes local, measured 7 h skew).
    """
    want = f"edmonds_canopy_prob_{label}_{tag}.tif"
    live = [r for r in _rows(INDEP)
            if str(r.get("live", "")).strip() == "1"
            and str(r.get("prob", "")).replace("\\", "/").split("/")[-1] == want]
    if not live:
        # The gate's known manual dependency, so name the exact command rather than
        # leaving a reader to reconstruct it. REFERENCE CHOICE IS NOT FREE: the prior
        # 2019 and 2019n arms were scored against ccap_2021_hires_lc.tif, and using a
        # different reference would make these rows incomparable with them. 2021 is also
        # the nearer vintage to a 2019 flight than 2016 is, and both hires rasters cover
        # the same Edmonds footprint (checked 2026-08-31).
        return False, ("no live qc_indep row yet — qc_indep is a SEPARATE local step.\n"
                       "        py -3.12 qc/phase4_qc_indep.py --year " + label +
                       " --prob " + str(MASKS / f"edmonds_canopy_prob_{label}_{tag}.tif") +
                       " \\\n            --ref '" + str(REF_CCAP) + "'")
    primary = [r for r in live if str(r.get("primary", "")).strip() == "1"]
    r = (primary or live)[-1]
    return True, (f"rec {r.get('recall')} prec {r.get('precision')} vs "
                  f"{r.get('ref', '?')} ({r.get('canopy_def', '?')}"
                  f"{'' if primary else ', NON-PRIMARY def'})")


def check_manifest(label, tag):
    """(3) PROVENANCE. EPOCH is what makes the re-baseline a recorded fact rather than a
    convention: pre-overhaul results are epoch 1, this work is epoch 2, and nothing
    silently compares across the line. Architecture provenance is engine_version + the
    commit, so a number can be traced to the code that produced it.
    """
    hits = _retry(lambda: sorted(RUNS.glob(f"*_{label}_{tag}_*/manifest.json")))
    if not hits:
        return False, f"no manifest under runs/*_{label}_{tag}_*/"
    m = json.loads(hits[-1].read_text(encoding="utf-8"))
    missing = [k for k in ("epoch", "engine_version", "git_sha", "run_id") if not m.get(k)]
    if missing:
        return False, f"{hits[-1].parent.name} is missing {missing}"
    return True, (f"epoch={m['epoch']} {m['engine_version']} "
                  f"{str(m['git_sha'])[:8]}{' DIRTY' if m.get('git_dirty') else ''} "
                  f"({len(hits)} manifests for this arm)")


def check_status_rows(label, tag):
    """(4) THE LEDGER SAW IT. Every step OK, including postproc, with no hand-typed step.

    A pilot that needed someone to type `--step postproc` would look identical in the
    masks directory and would not prove the machinery. This reads the queue's own ledger,
    so it distinguishes them.
    """
    want_steps = {"labels", "tile", "train", "evaluate", "inference", "postproc"}
    # RETRY THE WHOLE ARM LOOKUP, not the listing. Retrying until the listing is non-empty
    # is the wrong predicate and it failed here: status_files() returned plenty of files
    # while the mirror hid THIS arm's file specifically, so the retry was satisfied
    # instantly and the gate still reported "no ledger rows" for an arm with eleven. What
    # matters is whether the answer we need appeared, not whether some answer did.
    def _gather():
        out = []
        for f in status_files(QC):
            out += [r for r in _rows(f)
                    if str(r.get("year")) == label and str(r.get("tag")) == tag]
        return out

    rows = _retry(_gather, tries=12)
    if not rows:
        # "I could not read the ledger" IS NOT "the queue did not run the step", and
        # printing the first as the second is the mistake this repo fixed in the state
        # vocabulary the same day: UNCHECKED belongs in neither the pass nor the fail
        # bucket. It bit here for real — the medium arm's ledger file vanished from the
        # G: mirror while its GPKG, mask, prob raster, eval row and six manifests all sat
        # there, so the queue plainly ran every step and the gate said otherwise.
        others = _retry(lambda: [p.name for p in status_files(QC)], tries=3)
        return None, (f"UNVERIFIED — no ledger file for this arm is readable "
                      f"({len(others)} other status files are). That is missing "
                      f"EVIDENCE, not a failed step; check the lake from the VM side "
                      f"before treating it as one.")
    final = {}
    for r in rows:                                  # file order is chronological
        final[str(r.get("step"))] = r
    done = {s for s in want_steps if final.get(s, {}).get("state") == "OK"}
    bad = {s: final[s].get("state") for s in want_steps
           if s in final and final[s].get("state") not in ("OK", None)}
    if bad:
        return False, f"steps not OK: {bad}"
    if done != want_steps:
        return False, f"steps still missing: {sorted(want_steps - done)}"
    return True, f"all {len(want_steps)} steps OK in the ledger"


CHECKS = [("mask GPKG (the deliverable)", check_mask),
          ("independent score", check_scored),
          ("manifest + EPOCH", check_manifest),
          ("queue ran every step", check_status_rows)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", help="only this run tag")
    ap.add_argument("--experiment", default=str(DEFAULT_EXPERIMENT),
                    help="experiments/*.yaml to gate (default: the 2019 pilot)")
    a = ap.parse_args()

    print(f"lake: {BASE}")
    if not BASE.exists():
        sys.exit(f"data lake not reachable at {BASE}")

    all_arms, spec = load_arms(a.experiment)
    print(f"experiment: {spec.get('name')} [{spec.get('status')}]")
    arms = [x for x in all_arms if not a.arm or x[1] == a.arm]
    verdicts = []
    for label, tag in arms:
        print(f"\n── {label} / {tag} " + "─" * (52 - len(label) - len(tag)))
        ok_all, unverified = True, []
        for name, fn in CHECKS:
            try:
                ok, detail = fn(label, tag)
            except Exception as e:                       # noqa: BLE001
                ok, detail = False, f"check raised: {e!r}"
            # ok is None = UNVERIFIED: the check could not answer. It is neither a pass
            # (nothing was confirmed) nor a fail (nothing was disproven), and collapsing
            # it into either is how oversight ends up confidently wrong.
            tag_ = "PASS" if ok else ("UNVR" if ok is None else "MISS")
            ok_all = ok_all and (ok is True)
            unverified.append(name) if ok is None else None
            print(f"  [{tag_}] {name:28s} {detail}")
        verdicts.append((label, tag, ok_all, unverified))

    print("\n" + "=" * 66)
    npass = sum(1 for _, _, v, _u in verdicts if v)
    for label, tag, v, unv in verdicts:
        state = "GATE PASS" if v else ("GATE UNVERIFIED" if unv else "GATE NOT MET")
        print(f"  {label:6s} {tag:20s} {state}" + (f"  ({', '.join(unv)})" if unv else ""))
    print(f"\n{npass}/{len(verdicts)} arms complete.")
    if npass != len(verdicts):
        print("The 36-year run does not start until every line above reads GATE PASS.\n"
              "A MISS is information, not a failure: it names the step of the machinery\n"
              "that still needs a human, which is exactly what the pilot was for.")
    return 0 if npass == len(verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())

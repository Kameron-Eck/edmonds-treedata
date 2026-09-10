"""LOSO scoring pass for a seven-arm warm-started phase of experiments/backbone_sweep.yaml
— the reconstruction of the Tier-1 scoring conveyor, as a tracked driver.

--prefix picks the phase: wb50 (phase 2, resnet50; the default and the original name of
this file) or wb18 (phase 3, resnet18). The seven treatment tags are identical across
phases — only the prefix moves — so the qc_indep invocation is byte-for-byte the same.

WHAT IT RUNS, in sequence, for each of the seven <prefix>_ tags:

    py -3.12 qc/phase4_qc_indep.py --year <label> --ref <ccap_2021_hires_lc.tif>
        --prob <BASE>/phase4/masks/edmonds_canopy_prob_<label>_<tag>.tif
        --aoi phase4/qc/science_sample_manifest.csv --aoi-roles test

then `py -3.12 qc/instruments/harvest_arm_metrics.py`. These are the Tier-1 arguments:
the sample-test rows of phase4/qc/qc_indep_report.csv carry ref ccap_2021_hires_lc.tif,
prob edmonds_canopy_prob_<year>_t1_*.tif and aoi sample-test, and the sweep files they
produced are named qc_indep_sweep_<year>_<tag>_ccap_2021_hires_lc_sample-test.csv —
which harvest_arm_metrics.eval_scope reads as eval_scope "sample-test". No --thresh, as
in Tier-1: qc_indep's deployed_threshold keys on (year, channels), not the tag, so the
scored_live row's cut is incidental; the pre-registered number (recall at policy
matched_p75) comes from the sweep, which is threshold-independent.

REFUSES TO START if any of the seven prob rasters, the reference or the AOI manifest is
missing — a half-scored campaign is worse than none. No subprocess timeout: the Tier-1
conveyor died at 1200 s on the 2020 arm (167M cells; CHATLOG 2026-09-03), so 2020 runs
last and unbounded.

Every command and its exit code is printed; the end-of-run summary goes to
phase4/logs/ via write_step_log. --dry-run prints the commands and exits after the
existence checks — it never writes.

Run:
  PYTHONUTF8=1 py -3.12 qc/instruments/score_wb50_loso.py --dry-run
  PYTHONUTF8=1 py -3.12 qc/instruments/score_wb50_loso.py
  PYTHONUTF8=1 py -3.12 qc/instruments/score_wb50_loso.py --prefix wb18
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent            # Scripts/qc/instruments
SCRIPTS = HERE.parents[1]                          # Scripts/
REPO = SCRIPTS.parent

# (year label, treatment tag) — experiments/backbone_sweep.yaml extra.phase2_tags /
# phase3_tags with the phase prefix dropped, in queue order
# (pipeline/queue_<prefix>_score.yaml): 2020 last, it is the slow one.
TREATMENTS = [
    ("2011s", "2011s_base"),
    ("2011s", "2011s_base_s2"),
    ("2011s", "2011s_base_s3"),
    ("2011s", "2011s_cor05"),
    ("2016", "2016_base"),
    ("2016", "2016_in05"),
    ("2020", "2020_base"),
]
PREFIXES = ("wb50", "wb18")


def arms_for(prefix):
    """The seven (year, run tag) pairs of one warm-started phase."""
    return [(y, f"{prefix}_{t}") for y, t in TREATMENTS]


ARMS = arms_for("wb50")     # the default phase; kept as a module constant
REF_NAME = "ccap_2021_hires_lc.tif"
QC_INDEP = SCRIPTS / "qc" / "phase4_qc_indep.py"
HARVEST = SCRIPTS / "qc" / "instruments" / "harvest_arm_metrics.py"
AOI_DEFAULT = REPO / "phase4" / "qc" / "science_sample_manifest.csv"


def prob_path(base, year, tag):
    return Path(base) / "phase4" / "masks" / f"edmonds_canopy_prob_{year}_{tag}.tif"


def build_commands(base, ref, aoi, python, arms=ARMS):
    """The seven qc_indep command lines (argv lists), Tier-1 shape."""
    return [[python, str(QC_INDEP), "--year", year, "--ref", str(ref),
             "--prob", str(prob_path(base, year, tag)),
             "--aoi", str(aoi), "--aoi-roles", "test"]
            for year, tag in arms]


def missing_inputs(base, ref, aoi, arms=ARMS):
    """Every input that must exist before the first command runs."""
    want = [Path(ref), Path(aoi)] + [prob_path(base, y, t) for y, t in arms]
    return [p for p in want if not p.exists()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None,
                    help="Lake root (default lake.BASE). Prob rasters are read from "
                         "<base>/phase4/masks/.")
    ap.add_argument("--ref", default=None,
                    help=f"Reference raster (default <base>/Full_Image/Pipeline Imagery/"
                         f"{REF_NAME}, the Tier-1 reference).")
    ap.add_argument("--aoi", default=str(AOI_DEFAULT),
                    help="Ground-block manifest (default the tracked "
                         "phase4/qc/science_sample_manifest.csv).")
    ap.add_argument("--prefix", default="wb50", choices=list(PREFIXES),
                    help="Which warm-started phase to score (default wb50 = phase 2, "
                         "resnet50; wb18 = phase 3, resnet18).")
    ap.add_argument("--python", default=sys.executable,
                    help="Interpreter for the subprocesses (default this one).")
    ap.add_argument("--no-harvest", action="store_true",
                    help="Skip the harvest_arm_metrics re-run at the end.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the commands after the existence checks; run nothing.")
    if argv is None:
        from phase4seg.names import clean_argv
        argv = clean_argv()
    a = ap.parse_args(argv)

    if a.base:
        base = Path(a.base)
    else:
        from lake import BASE
        base = Path(BASE)
    ref = Path(a.ref) if a.ref else base / "Full_Image" / "Pipeline Imagery" / REF_NAME
    aoi = Path(a.aoi)

    arms = arms_for(a.prefix)
    miss = missing_inputs(base, ref, aoi, arms)
    if miss:
        print("REFUSING to start — missing input(s):", file=sys.stderr)
        for p in miss:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(2)

    cmds = build_commands(base, ref, aoi, a.python, arms)
    harvest = [a.python, str(HARVEST)]
    if a.dry_run:
        print("DRY RUN — commands that would run, in order:")
        for c in cmds:
            print("  " + subprocess.list2cmdline(c))
        if not a.no_harvest:
            print("  " + subprocess.list2cmdline(harvest))
        return 0

    results = []
    for (year, tag), c in zip(arms, cmds):
        print(f"\n[{tag}] {subprocess.list2cmdline(c)}", flush=True)
        rc = subprocess.run(c).returncode          # no timeout: 2020 is 167M cells
        print(f"[{tag}] exit={rc}", flush=True)
        results.append((year, tag, rc))
    rc_h = None
    if not a.no_harvest:
        print(f"\n[harvest] {subprocess.list2cmdline(harvest)}", flush=True)
        rc_h = subprocess.run(harvest).returncode
        print(f"[harvest] exit={rc_h}", flush=True)

    failed = [t for _, t, rc in results if rc != 0]
    print(f"\nscored {len(results) - len(failed)}/{len(results)}"
          + (f"; FAILED: {failed}" if failed else "")
          + (f"; harvest exit={rc_h}" if rc_h is not None else ""))
    from pipeline_log import write_step_log
    write_step_log(f"score_{a.prefix}_loso", step="score", logs_dir=base / "phase4" / "logs",
                   scored=len(results) - len(failed), failed=",".join(failed),
                   harvest_exit="" if rc_h is None else rc_h, ref=ref.name,
                   aoi=aoi.name)
    return 1 if failed or (rc_h not in (None, 0)) else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""LOSO scoring pass for a seven-arm warm-started phase of experiments/backbone_sweep.yaml
— the reconstruction of the Tier-1 scoring conveyor, as a tracked driver.

--prefix picks the phase: wb50 (phase 2, resnet50; the default and the original name of
this file) or wb18 (phase 3, resnet18). The seven treatment tags are identical across
phases — only the prefix moves — so the qc_indep invocation is byte-for-byte the same.

--arms REPLACES the seven-tag phase list with an explicit tag list, and --refs scores every
arm against more than one reference. Both arrived 2026-09-09 for the harmonization design
(Reports/HARMONIZATION_DESIGN_2026-09-10.md), whose arms are not a backbone_sweep phase and
whose EXP-H1 secondary read requires the SAME arm scored against ccap_2021_hires_lc.tif AND
ccap_2016_hires_lc.tif — one frozen 2006s mask already swings 0.097 in recall on the
reference alone (design section 1.7), so a spread read against 2021 alone confounds detector
sensitivity with fifteen years of real canopy change. Each arm's year is parsed out of its
tag (`<prefix>_<year>_<treatment>`) and validated against config.YEAR_CATALOG — a tag
carrying no catalog label is REFUSED, never guessed. Commands run arms OUTER, refs INNER, so
with one reference the order is exactly what it was. qc/phase4_qc_indep.py names its sweep
file after the reference stem (qc_indep_sweep_{year}_{arm}_{refstem}_sample-test.csv), so the
two reads land as separate arm_metrics rows and cannot overwrite each other.

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
  PYTHONUTF8=1 py -3.12 qc/instruments/score_wb50_loso.py --dry-run \
      --arms wb18_2006s_base wb18_2006s_in16 \
      --refs ccap_2021_hires_lc.tif ccap_2016_hires_lc.tif
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
REF_2016 = "ccap_2016_hires_lc.tif"
# What --refs accepts as a bare name. Both are tracked reference products that already
# carry arm_metrics rows (design section 1.7); anything else must be given as a path.
KNOWN_REFS = (REF_NAME, REF_2016)
REF_DIR = ("Full_Image", "Pipeline Imagery")
QC_INDEP = SCRIPTS / "qc" / "phase4_qc_indep.py"
HARVEST = SCRIPTS / "qc" / "instruments" / "harvest_arm_metrics.py"
AOI_DEFAULT = REPO / "phase4" / "qc" / "science_sample_manifest.csv"


def prob_path(base, year, tag):
    return Path(base) / "phase4" / "masks" / f"edmonds_canopy_prob_{year}_{tag}.tif"


def year_of(tag):
    """The catalog label inside a run tag: `<prefix>_<year>_<treatment>`.

    Validated against config.YEAR_CATALOG, never inferred — a year label is a catalog
    key, not a calendar year (CLAUDE.md 2.2), and a mis-parsed year would score an arm
    against the wrong acquisition's AOI and deployed cut.
    """
    from phase4seg.config import YEAR_CATALOG
    labels = {str(e["label"]) for e in YEAR_CATALOG}
    hits = [p for p in str(tag).split("_")[1:] if p in labels]
    if len(hits) != 1:
        raise SystemExit(
            f"--arms {tag!r}: cannot read exactly one YEAR_CATALOG label out of it "
            f"(found {hits or 'none'}). Tags are <prefix>_<year>_<treatment>.")
    return hits[0]


def arms_from_tags(tags):
    """[(year, tag)] for an explicit --arms list, order preserved."""
    return [(year_of(t), t) for t in tags]


def resolve_refs(base, names):
    """A bare name resolves under <base>/Full_Image/Pipeline Imagery/; a path passes
    through untouched, so --refs stays usable against a local mirror."""
    out = []
    for n in names:
        q = Path(n)
        out.append(q if (q.is_absolute() or len(q.parts) > 1)
                   else Path(base).joinpath(*REF_DIR, n))
    return out


def build_commands(base, refs, aoi, python, arms=ARMS):
    """The qc_indep command lines (argv lists), Tier-1 shape — arms OUTER, refs INNER."""
    return [[python, str(QC_INDEP), "--year", year, "--ref", str(ref),
             "--prob", str(prob_path(base, year, tag)),
             "--aoi", str(aoi), "--aoi-roles", "test"]
            for year, tag in arms for ref in refs]


def missing_inputs(base, refs, aoi, arms=ARMS):
    """Every input that must exist before the first command runs."""
    want = [Path(r) for r in refs] + [Path(aoi)]
    want += [prob_path(base, y, t) for y, t in arms]
    return [p for p in want if not p.exists()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None,
                    help="Lake root (default lake.BASE). Prob rasters are read from "
                         "<base>/phase4/masks/.")
    ap.add_argument("--ref", default=None,
                    help=f"ONE reference raster, by path (the Tier-1 flag). Overrides "
                         f"--refs. Default <base>/Full_Image/Pipeline Imagery/"
                         f"{REF_NAME}.")
    ap.add_argument("--refs", nargs="+", default=[REF_NAME],
                    help=f"Reference(s) by bare name under <base>/Full_Image/Pipeline "
                         f"Imagery/ (or by path). Default {REF_NAME}; the harmonization "
                         f"design also scores {REF_2016}, so the reference-epoch share "
                         f"of a spread can be separated from detector sensitivity.")
    ap.add_argument("--arms", nargs="+", default=None,
                    help="Explicit run tags to score, replacing the --prefix phase's "
                         "seven. Each year is parsed from its tag and validated against "
                         "config.YEAR_CATALOG.")
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
    refs = [Path(a.ref)] if a.ref else resolve_refs(base, a.refs)
    aoi = Path(a.aoi)

    arms = arms_from_tags(a.arms) if a.arms else arms_for(a.prefix)
    miss = missing_inputs(base, refs, aoi, arms)
    if miss:
        print("REFUSING to start — missing input(s):", file=sys.stderr)
        for p in miss:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(2)

    cmds = build_commands(base, refs, aoi, a.python, arms)
    harvest = [a.python, str(HARVEST)]
    if a.dry_run:
        print("DRY RUN — commands that would run, in order:")
        for c in cmds:
            print("  " + subprocess.list2cmdline(c))
        if not a.no_harvest:
            print("  " + subprocess.list2cmdline(harvest))
        return 0

    results = []
    pairs = [(year, tag, ref) for year, tag in arms for ref in refs]
    for (year, tag, ref), c in zip(pairs, cmds):
        label = tag if len(refs) == 1 else f"{tag}@{Path(ref).stem}"
        print(f"\n[{label}] {subprocess.list2cmdline(c)}", flush=True)
        rc = subprocess.run(c).returncode          # no timeout: 2020 is 167M cells
        print(f"[{label}] exit={rc}", flush=True)
        results.append((year, label, rc))
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
                   harvest_exit="" if rc_h is None else rc_h,
                   ref=",".join(r.name for r in refs), aoi=aoi.name)
    return 1 if failed or (rc_h not in (None, 0)) else 0


if __name__ == "__main__":
    raise SystemExit(main())

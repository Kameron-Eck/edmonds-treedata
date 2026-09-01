"""experiment_queue.py — generate the launch queue FROM the experiment file.

The last duplication in the R&D loop: experiments/*.yaml declares the arms, and
launching still meant hand-writing a queue yaml that RESTATES year/tag/flags — the
drift class everything else here just finished killing (the pilot's rationale lived
in queue comments precisely because there was nowhere else).

    py -3.12 qc/experiment_queue.py --experiment experiments/foo.yaml
        -> writes pipeline/queue_foo.yaml (GENERATED header; commit it — the VM
           clones the repo and needs the file)

Arms may carry `extra: [--flag, ...]` (engine flags for that arm); the experiment
may carry `launch_defaults: [--flag, ...]` applied to every arm (arm extra appended
after, so arm-specific flags win by argparse last-wins). Refuses complete/tabled
experiments — there is nothing to launch.

One source of truth is enforced: qc/test_experiments.py regenerates every GENERATED
queue file in memory and fails on drift. Edit the EXPERIMENT, rerun this.
"""
import argparse
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
MARK = "# GENERATED from"


def generate(exp_path):
    exp_path = Path(exp_path)
    spec = yaml.safe_load(exp_path.read_text(encoding="utf-8"))
    if spec["status"] in ("complete", "tabled"):
        raise SystemExit(f"{spec['name']} is {spec['status']} — nothing to launch")
    defaults = [str(x) for x in (spec.get("launch_defaults") or [])]
    jobs = []
    for a in spec["arms"]:
        jobs.append({
            "id": f"{spec['name']}_{a['tag']}",
            "year": str(a["year"]),
            "tag": str(a["tag"]),
            "extra": defaults + [str(x) for x in (a.get("extra") or [])],
            "why": f"arm of experiments/{exp_path.name} — hypothesis and decision "
                   f"rule live THERE, not here.",
        })
    header = (
        f"{MARK} experiments/{exp_path.name} — DO NOT EDIT.\n"
        f"# Edit the experiment file and rerun:\n"
        f"#   py -3.12 qc/experiment_queue.py --experiment experiments/{exp_path.name}\n"
        f"# test_experiments.py::test_generated_queues_match_their_experiments fails on drift.\n"
        f"# ONE QUEUE PER RUNTIME (COLAB_AUTONOMY_SETUP.md); arms wanting parallel\n"
        f"# runtimes get split into per-arm files by hand, still generated-headered.\n")
    return header + yaml.safe_dump(jobs, sort_keys=False, allow_unicode=True), spec


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    a = ap.parse_args()
    text, spec = generate(a.experiment)
    if a.stdout:
        print(text)
        return
    out = SCRIPTS / "pipeline" / f"queue_{spec['name']}.yaml"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} — commit it, then launch per COLAB_AUTONOMY_SETUP.md")


if __name__ == "__main__":
    main()

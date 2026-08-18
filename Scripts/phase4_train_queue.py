"""
╔══════════════════════════════════════════════════════════════════════════╗
  PHASE 4 — UNATTENDED TRAIN QUEUE   (honest-measurement-overhaul)
  Edmonds Temporal Active Learning Pipeline

  Start this in ONE Colab cell and walk away. It runs a queue of full
  labels->tile->train->evaluate->inference jobs, cheapest and most
  informative first, and writes a status row to Drive after EVERY step so
  the work is auditable even if the runtime dies mid-queue.

  ── WHY THESE JOBS ────────────────────────────────────────────────────────
  2026-08-18 findings that set the queue order:
    * The best model in the project (2022n: out-of-sample AUROC .9538, NIR +
      CHM, healthy calibration) still scores honest recall .6564 — inside the
      same .51-.71 band as far weaker years. Better models do NOT close the
      gap, so the gap is SYSTEMATIC.
    * P2 showed the two references contradict each other on 16.0% of valid
      pixels, and 38.7% of the headline "miss" is therefore UNMEASURABLE.

  Two live hypotheses for the systematic part, and one job each:
    H1  the REFERENCES over-call canopy      -> needs more NIR years, because
        only NIR years can build an NDVI reference and be P2-partitioned.
        JOBS: 2019n, 2021s  (2016 and 2022n already have refs)
    H2  every model inherits ONE BLIND SPOT from the shared 2020-mask labels
        -> test by training a year on labels the 2020 mask never provided.
        JOB: 2016 with --add-canopy-mask (canopy_additions_2016.tif), scored
        against the existing 2016 baseline (recall .6844 / precision .8651).
        If the gap closes, it is a LABEL problem. If it does not, labels are
        exonerated and the references carry the story. Either way decisive.

  ── UNATTENDED BY DESIGN ─────────────────────────────────────────────────
    * A failing job does NOT stop the queue (unlike the P1 driver, which
      aborts because a human was watching). Throughput matters more here;
      every outcome is recorded instead.
    * Status is flushed to Drive after every step: phase4/qc/train_queue_status.csv
      That file is the monitoring hook — it survives the runtime dying.
    * Cheapest-first, so a runtime that dies early still delivers the most
      informative results. All queued years are COARSE (50-60cm, ~1h each);
      nothing here is a 7.5cm multi-hour job.
    * --run-tag on every job, so nothing existing is overwritten.

  ── USAGE (Colab, L4 24GB; ONE cell, then close the laptop) ──────────────
      %cd /content/drive/MyDrive/treedata/Scripts
      %run phase4_train_queue.py

      %run phase4_train_queue.py --dry-run        # print the plan, spend nothing
      %run phase4_train_queue.py --only 2019n     # a single job
      %run phase4_train_queue.py --skip 2016c     # drop one

  DO NOT append `# comments` to that line — %run passes them to argparse.
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import io
import subprocess
import sys
import threading
from pathlib import Path

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

SCRIPTS = BASE / "Scripts"
QC_DIR  = BASE / "phase4" / "qc"
MASKS   = BASE / "phase4" / "masks"
LABELS  = BASE / "phase4" / "labels_corrected"
ENGINE  = SCRIPTS / "phase4_semantic_finetune.py"
STATUS  = QC_DIR / "train_queue_status.csv"

STEPS = ["labels", "tile", "train", "evaluate", "inference"]

# Per-step wall-clock ceilings, in MINUTES. Deliberately generous — these exist
# to break a genuine hang, never to cut short a slow-but-working step. Reference
# points from real runs: 2022n full path ~55 min total; a 7.5cm inference ran
# 255 min. Coarse years are far smaller than either.
STEP_TIMEOUT_MIN = {"labels": 45, "tile": 90, "train": 240,
                    "evaluate": 60, "inference": 240}

# Cheapest / most informative first. Every entry is a COARSE year (~1h).
JOBS = [
    dict(id="2019n", year="2019n", tag="p2nir", extra=[],
         why="H1: 3rd NIR year -> 3rd independent NDVI reference for the P2 "
             "disagreement test. 60cm, cheapest job here.",
         expect="A prob raster + (later) an NDVI ref, so P2 can check whether "
                "the 16.0% reference-disagreement rate generalises."),
    dict(id="2021s", year="2021s", tag="p2nir", extra=[],
         why="H1: 4th NIR year. 50cm, still coarse.",
         expect="Same as 2019n. Two more NIR years turns P2 from one datapoint "
                "into a trend."),
    dict(id="2016c", year="2016", tag="corrected", extra=[
            "--add-canopy-mask", str(LABELS / "canopy_additions_2016.tif")],
         why="H2 THE HYPOTHESIS TEST: train 2016 on the ADD-ONLY corrected-label "
             "overlay, which injects NIR+CHM canopy the 2020 mask never taught.",
         expect="Compare honest recall vs the 2016 baseline (recall .6844 / "
                "precision .8651 vs C-CAP). Closes the gap => LABEL problem. "
                "Does not => labels exonerated, references carry the story. "
                "NOTE v043: the overlay is baked at tile time, so tiling MUST "
                "re-run; the tile signature includes --add-canopy-mask, so it "
                "auto-retiles."),
]


def _completed_steps():
    """(job_id, step) pairs already recorded OK, so a restart does not redo them.

    The engine's labels/tile steps are idempotent and train/evaluate/inference
    write tagged outputs, so skipping a previously-OK step is safe and turns a
    dead runtime into a cheap restart instead of starting from zero.
    """
    done = set()
    if not STATUS.exists():
        return done
    try:
        for r in csv.DictReader(io.open(STATUS, encoding="utf-8", newline="")):
            if r.get("state") == "OK" and r.get("step") in STEPS:
                done.add((r.get("job"), r.get("step")))
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! WARN could not read prior status ({e}); starting fresh.")
    return done


def _prior_rows():
    """Load the existing status table so a RESTART APPENDS instead of erasing.

    _status_write() rewrites the whole file, so starting from an empty list
    would destroy the record of everything the previous runtime did — exactly
    the history this file exists to preserve.
    """
    if not STATUS.exists():
        return []
    try:
        return list(csv.DictReader(io.open(STATUS, encoding="utf-8", newline="")))
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! WARN could not read prior status ({e}); starting a fresh table.")
        return []


def _hr(t=""):
    print("\n" + "=" * 74)
    if t:
        print(f"  {t}")
        print("=" * 74)


def _status_write(rows):
    """Flush the whole status table to Drive. Called after EVERY step."""
    try:
        QC_DIR.mkdir(parents=True, exist_ok=True)
        cols = ["job", "year", "tag", "step", "state", "exit", "minutes",
                "detail", "ts"]
        with io.open(STATUS, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! WARN could not write status: {e}")


def run_step(job, step, infer_batch, rows):
    y, tag = job["year"], job["tag"]
    cmd = [sys.executable, "-u", str(ENGINE), "--year", y, "--step", step,
           "--infer-batch", str(infer_batch), "--run-tag", tag, *job["extra"]]
    print(f"\n  $ {' '.join(cmd[1:])}", flush=True)

    rec = dict(job=job["id"], year=y, tag=tag, step=step, state="RUNNING",
               exit="", minutes="", detail="",
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    rows.append(rec)
    _status_write(rows)

    t0 = _dt.datetime.now()
    budget = STEP_TIMEOUT_MIN.get(step, 240)
    timed_out = {"hit": False}
    try:
        proc = subprocess.Popen(cmd, cwd=str(SCRIPTS), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                bufsize=1, errors="replace")

        # Watchdog: stdout is streamed in this thread, so a hung child would
        # block forever. Kill it past the budget so the QUEUE survives one
        # stuck step instead of stalling until the runtime dies.
        def _kill_on_timeout():
            timed_out["hit"] = True
            print(f"\n  ! TIMEOUT: {job['id']}/{step} exceeded {budget} min — killing it "
                  f"and moving on. This is a hang guard, not a normal outcome.", flush=True)
            try:
                proc.kill()
            except Exception:
                pass

        wd = threading.Timer(budget * 60, _kill_on_timeout)
        wd.daemon = True
        wd.start()
        try:
            for line in proc.stdout:
                print("    | " + line.rstrip(), flush=True)
            rc = proc.wait()
        finally:
            wd.cancel()
        if timed_out["hit"]:
            rec.update(state="TIMEOUT", exit="killed",
                       detail=f"exceeded {budget} min budget",
                       minutes=round((_dt.datetime.now()-t0).total_seconds()/60, 1))
            _status_write(rows)
            return False
    except KeyboardInterrupt:
        try:
            proc.terminate(); proc.wait(timeout=30)
        except Exception:
            pass
        rec.update(state="INTERRUPTED", exit="sigint",
                   minutes=round((_dt.datetime.now()-t0).total_seconds()/60, 1))
        _status_write(rows)
        raise
    except Exception as e:                                      # noqa: BLE001
        rec.update(state="ERROR", exit="exc", detail=f"{type(e).__name__}: {e}"[:200],
                   minutes=round((_dt.datetime.now()-t0).total_seconds()/60, 1))
        _status_write(rows)
        return False

    mins = round((_dt.datetime.now() - t0).total_seconds() / 60, 1)
    rec.update(state="OK" if rc == 0 else "FAIL", exit=str(rc), minutes=mins)
    _status_write(rows)
    print(f"  [{job['id']}/{step}] exit={rc}  elapsed {mins} min", flush=True)
    return rc == 0


def verify(job, rows):
    """Record what the job actually produced. Never raises — this is unattended."""
    out = MASKS / f"edmonds_canopy_prob_{job['year']}_{job['tag']}.tif"
    rec = dict(job=job["id"], year=job["year"], tag=job["tag"], step="VERIFY",
               state="", exit="", minutes="", detail="",
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        if not out.exists():
            rec.update(state="MISSING", detail=f"no raster at {out.name}")
        else:
            mb = out.stat().st_size / 1e6
            import rasterio
            from rasterio.enums import Resampling
            import numpy as np
            with rasterio.open(out) as s:
                h = min(1200, s.height)
                w = max(1, int(s.width * h / s.height))
                a = s.read(1, out_shape=(h, w), resampling=Resampling.nearest)
                nd = 255 if s.nodata is None else s.nodata
            v = a != nd
            vf = float(v.mean())
            mx = float(a[v].max()) / 254.0 if v.any() else float("nan")
            state = "OK"
            if mb == 0 or not v.any():
                state = "EMPTY"
            elif vf < 0.05:
                state = "MOSTLY_NODATA"
            elif mx < 0.50:
                state = "NO_CONFIDENCE"
            elif mx < 0.75:
                state = "WEAK_CALIBRATION"
            rec.update(state=state,
                       detail=f"{mb:.0f}MB valid={vf:.1%} maxprob={mx:.3f}")
    except Exception as e:                                      # noqa: BLE001
        rec.update(state="UNCHECKED", detail=f"{type(e).__name__}: {e}"[:200])
    rows.append(rec)
    _status_write(rows)
    print(f"  VERIFY {job['id']}: {rec['state']}  {rec['detail']}")


def main():
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a.startswith("#"):
            argv = argv[:i]
            break
    filtered = [a for a in argv if not (a == "-f" or a.endswith(".json"))]

    ap = argparse.ArgumentParser(description="Unattended Phase-4 training queue.")
    ap.add_argument("--infer-batch", type=int, default=32)
    ap.add_argument("--only", default=None, help="Run just this job id.")
    ap.add_argument("--skip", default="", help="Comma-separated job ids to skip.")
    ap.add_argument("--no-resume", action="store_true",
                    help="Re-run every step even if a prior run recorded it OK.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan and the exact commands; spend nothing.")
    args = ap.parse_args(filtered)

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    todo = [j for j in JOBS if j["id"] not in skip
            and (args.only is None or j["id"] == args.only)]

    _hr("PHASE 4 — UNATTENDED TRAIN QUEUE")
    print(f"  BASE   : {BASE}")
    print(f"  status : {STATUS}   (flushed after EVERY step)")
    print(f"  jobs   : {len(todo)} of {len(JOBS)}")
    for j in todo:
        print(f"\n  [{j['id']}] year={j['year']} tag={j['tag']}")
        print(f"      why    : {j['why']}")
        print(f"      expect : {j['expect']}")
        if j["extra"]:
            print(f"      extra  : {' '.join(j['extra'])}")

    missing = [j["id"] for j in todo for k, v in [(0, 0)]
               if j["extra"] and not Path(j["extra"][-1]).exists()]
    if missing:
        print(f"\n  ! MISSING INPUT for {missing} — that job will fail. Fix or --skip it.")

    if args.dry_run:
        print("\n  DRY RUN — nothing executed. Commands that would run:")
        for j in todo:
            for st in STEPS:
                print(f"    --year {j['year']} --step {st} --run-tag {j['tag']} "
                      f"{' '.join(j['extra'])}".rstrip())
        return

    if not ENGINE.exists():
        raise SystemExit(f"engine missing: {ENGINE}")

    rows = _prior_rows()
    done = set() if args.no_resume else _completed_steps()
    if done:
        print(f"\n  RESUME: {len(done)} step(s) already OK in {STATUS.name} will be SKIPPED.")
        print(f"          (pass --no-resume to force everything to re-run)")
    t_all = _dt.datetime.now()
    for j in todo:
        _hr(f"JOB {j['id']}  (year {j['year']}, tag {j['tag']})")
        print(f"  {j['why']}")
        ok = True
        for st in STEPS:
            if (j["id"], st) in done:
                print(f"  - skip {j['id']}/{st} (already OK)")
                continue
            if not run_step(j, st, args.infer_batch, rows):
                print(f"  ! {j['id']} failed at step '{st}'. "
                      f"Recording and moving to the NEXT JOB (queue is unattended).")
                ok = False
                break
        if ok:
            verify(j, rows)

    _hr("QUEUE DONE")
    mins = (_dt.datetime.now() - t_all).total_seconds() / 60
    print(f"  total {mins:.1f} min")
    for r in rows:
        if r["step"] == "VERIFY" or r["state"] in ("FAIL", "ERROR", "INTERRUPTED"):
            print(f"    {r['job']:<7} {r['step']:<10} {r['state']:<16} {r['detail']}")
    print(f"\n  Status table: {STATUS}")
    print("  Scoring happens LOCALLY afterwards (no GPU): phase4_qc_indep.py,")
    print("  then phase4_ref_agreement.py for the NIR years.")


if __name__ == "__main__":
    main()

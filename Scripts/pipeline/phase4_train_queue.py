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

  ── USAGE (Colab, L4 24GB) ───────────────────────────────────────────────
  Code is CLONED from GitHub since 2026-08-20 (see pipeline/colab_launch.ipynb —
  that notebook is the standing cockpit; the recipe below is what it runs).
  LAUNCH DETACHED. This is the important part for an unattended run:

      %cd /content/repo/Scripts/pipeline
      !nohup python -u phase4_train_queue.py > /content/drive/MyDrive/treedata/phase4/logs/train_queue_nohup.log 2>&1 &

  With %run the queue lives INSIDE the notebook kernel, so anything that
  interrupts the cell kills it — and Colab sends SIGINT to the kernel whenever
  the websocket drops. On 2026-08-18 that killed the queue 18 s in while the
  user was nowhere near the stop button. Launched with nohup it is a separate
  process: cell interrupts, browser close and connection blips cannot touch it,
  and it dies only when the RUNTIME itself dies.

  Watch it (either from a Colab cell or from the synced Drive copy):
      !tail -f /content/drive/MyDrive/treedata/phase4/logs/train_queue_nohup.log
      phase4/qc/train_queue_status.csv          <- one row per step, on Drive

  Foreground (only when you are actually watching):
      %run phase4_train_queue.py --dry-run        print the plan, spend nothing
      %run phase4_train_queue.py --only 2019n     a single job
      %run phase4_train_queue.py --skip 2016c     drop one

  Restarting is cheap and safe: steps a previous run recorded OK are SKIPPED
  (--no-resume forces a full re-run), and the status table is appended to, not
  overwritten. A stray interrupt retries (--retries, default 2); two interrupts
  within 20 s stop the queue deliberately.

  DO NOT append `# comments` to a %run line — %run passes them to argparse.
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

SCRIPTS = Path(__file__).resolve().parent  # the CODE dir (repo pipeline/), NOT a Drive path
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

# Two interrupts inside this window = a human really wants out.
DOUBLE_INT_SEC = 20
_INT_STATE = {"last": None}

# Cheapest / most informative first. Every entry is a COARSE year (~1h).
# ── QUEUE 2, 2026-08-18: COMPLETE THE SERIES ON ONE RECIPE ────────────────
# Queue 1 (2019n · 2021s · 2016c) is DONE — all three have prob rasters and
# their results are in CHATLOG STATE. This queue fills the six catalog years
# that have imagery on Drive but NO model, so the temporal series stops having
# holes in it.
#
# EVERY JOB USES --force-citywide. Two reasons, both load-bearing:
#   1. It avoids polygons/. Those crown polygons are the ones CLAUDE.md records
#      as overwritten with accept-all test data, and fine/medium years would
#      otherwise train on them. Training on labels we know are bad is worse
#      than not training.
#   2. It puts these years on the SAME recipe as 2000/2002/2013/2015 (the
#      _citywide_rgb family). STATE result (7b) measured why that matters: a
#      recipe change moved 2013's deep-miss share by 22 POINTS, so cross-year
#      comparisons are only meaningful within one recipe.
#
# Cheapest first. The three King 20 cm years are the smallest rasters; 2024 is
# City-of-Edmonds 5 cm and by far the most expensive, so it sits last and can
# be dropped with --skip 2024 without affecting the others.
# ── QUEUE 3, 2026-08-19: THE LAST THREE YEARS OFF-RECIPE ──────────────────
# Swap JOBS to QUEUE3 below once queue 2 finishes. Rationale: 2026-08-19
# measured that recipe changes recall by 5.6-12.7 pp with the SIGN VARYING BY
# YEAR, so any table mixing recipes is uninterpretable. After queue 2 the only
# catalog years still lacking a citywide-recipe raster are 2017, 2019 and 2022.
# Running these three completes a fully recipe-matched 18-year series — the
# thing every cross-year claim in this project has been missing.
#
# Note which years do NOT need re-running: every coarse-tier year (2000, 2002,
# 2016, 2019n, 2021s, 2022n) already trains on the citywide 2020-mask path by
# default, so their existing rasters ARE recipe-matched. Only fine/medium years
# ever needed the flag.
#
# 2017 and 2022 are City-of-Edmonds 5 cm — the most expensive jobs in the
# project. Run 2019 first (King 10 cm, ~2013-sized) so a short runtime still
# delivers something.
QUEUE3 = [
    dict(id="2019", year="2019", tag="citywide_rgb", extra=["--force-citywide"],
         why="King 10 cm. Cheapest of the three and pairs with 2019n (NAIP 60.7 cm) "
             "as a second same-year cross-sensor pair.",
         expect="prob raster; completes the 10 cm tier alongside 2013/2015/2021/2023."),
    dict(id="2017", year="2017", tag="citywide_rgb", extra=["--force-citywide"],
         why="City of Edmonds 5 cm. Currently scored off-recipe (_xsensor_train), and it "
             "is the series recall high (.7986), so its recipe matters to any claim.",
         expect="prob raster on the shared recipe, making the .7986 comparable."),
    dict(id="2022", year="2022", tag="citywide_rgb", extra=["--force-citywide"],
         why="City of Edmonds 5 cm. Last year off-recipe; pairs with 2022n (NAIP).",
         expect="prob raster; completes the recipe-matched series."),
]

JOBS = [
    dict(id="2005", year="2005", tag="citywide_rgb", extra=["--force-citywide"],
         why="Fills a hole in the series. 20.1 cm true GSD (config said 29.9 "
             "before the 2026-08-18 units fix), medium tier forced to citywide.",
         expect="prob + mask raster, scorable against C-CAP with qc_indep."),
    dict(id="2007", year="2007", tag="citywide_rgb", extra=["--force-citywide"],
         why="As 2005. Same sensor family, so it also extends the King-County "
             "radiometric series the forest-miss work characterised.",
         expect="As 2005."),
    dict(id="2009", year="2009", tag="citywide_rgb", extra=["--force-citywide"],
         why="As 2005. Completes the 2005-2009 King 20 cm block.",
         expect="As 2005."),
    dict(id="2021k", year="2021", tag="citywide_rgb", extra=["--force-citywide"],
         why="King 10 cm. Pairs with 2021s (Snohomish, same calendar year) — a "
             "SAME-YEAR CROSS-SENSOR pair, which is the cleanest possible test "
             "of the sensor effect because real canopy change is ~zero.",
         expect="prob raster. The 2021k-vs-2021s comparison isolates sensor and "
                "resolution from change — nothing else in the series does."),
    dict(id="2023", year="2023", tag="citywide_rgb", extra=["--force-citywide"],
         why="King 10 cm, most recent King year. Extends the series forward.",
         expect="prob raster."),
    dict(id="2024", year="2024", tag="citywide_rgb", extra=["--force-citywide"],
         why="City of Edmonds 5 cm — the finest imagery in the project and the "
             "most expensive job here. LAST on purpose.",
         expect="prob raster. Skip with --skip 2024 if the runtime is short."),
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
        # An UNATTENDED queue must survive a STRAY interrupt. Colab sends SIGINT
        # to the kernel when the websocket blips, and on 2026-08-18 that killed
        # the queue 18s in with the user nowhere near the stop button. So: a
        # single interrupt is recorded and RETRIED; two within DOUBLE_INT_SEC
        # means a human really is holding Ctrl-C, and we abort.
        try:
            proc.terminate(); proc.wait(timeout=30)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        now = _dt.datetime.now()
        elapsed = round((now - t0).total_seconds() / 60, 1)
        prev = _INT_STATE.get("last")
        _INT_STATE["last"] = now
        if prev is not None and (now - prev).total_seconds() <= DOUBLE_INT_SEC:
            rec.update(state="ABORTED", exit="sigint x2",
                       detail="two interrupts close together — treating as human stop",
                       minutes=elapsed)
            _status_write(rows)
            print("\n  Two interrupts in quick succession — stopping the whole queue.")
            raise
        rec.update(state="INTERRUPTED", exit="sigint", minutes=elapsed,
                   detail="stray SIGINT (likely a dropped Colab websocket); will retry")
        _status_write(rows)
        print(f"\n  ! {job['id']}/{step} got a stray interrupt after {elapsed} min. "
              f"Interrupt AGAIN within {DOUBLE_INT_SEC}s to stop the queue; "
              f"otherwise it retries.", flush=True)
        return "RETRY"
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


def _check_prob_raster(out):
    """Decimated sanity read of a prob raster → (state, detail)."""
    if not out.exists():
        return "MISSING", f"no raster at {out.name}"
    mb = out.stat().st_size / 1e6
    import rasterio
    from rasterio.enums import Resampling
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
    return state, f"{mb:.0f}MB valid={vf:.1%} maxprob={mx:.3f}"


# P4.3: states that mean "the artifact this step just paid for is broken" —
# the queue must stop spending on this job, not sail into the next GPU hour.
_VERIFY_HARD_FAIL = {"MISSING", "EMPTY", "MOSTLY_NODATA", "NO_CONFIDENCE",
                     "BAD_CKPT", "NO_TILES", "BAD_INDEX"}


def verify_step(job, step, rows):
    """P4.3: per-step artifact check, recorded as a VERIFY:{step} row.

    The old job-end-only VERIFY let a broken artifact license every later step
    (the 2024 stub trained+evaluated fine and then died at inference; 2017's
    bad raster was only caught by a human a day later). Never raises; returns
    False on a hard failure so the caller aborts the job.
    """
    y, tag = job["year"], job["tag"]
    state, detail = "OK", ""
    try:
        if step == "labels":
            if "--force-citywide" in job.get("extra", []):
                detail = "citywide: labels step is skipped by design"
            else:
                site_dir = BASE / "phase4" / "sites" / y
                n = len(list(site_dir.glob("*_mask.tif"))) if site_dir.exists() else 0
                state, detail = ("OK", f"{n} site masks") if n else \
                                ("MISSING", f"no site masks in {site_dir}")
        elif step == "tile":
            import pandas as pd
            idx = BASE / "phase4" / "tiles" / y / f"tile_index_{y}.csv"
            if not idx.exists():
                state, detail = "MISSING", f"no {idx.name}"
            else:
                df = pd.read_csv(idx)
                if not len(df):
                    state, detail = "NO_TILES", "index has 0 rows"
                else:
                    probe = pd.concat([df.head(10), df.tail(10)])
                    n_miss = sum(1 for p in probe["img_path"]
                                 if not Path(str(p)).exists())
                    state = "BAD_INDEX" if n_miss else "OK"
                    detail = (f"{len(df)} tiles indexed; probed {len(probe)} "
                              f"paths, {n_miss} missing")
        elif step == "train":
            import zipfile
            ck = BASE / "phase4" / "models" / f"sem_best_{y}_{tag}.pt"
            if not ck.exists():
                state, detail = "MISSING", f"no {ck.name}"
            else:
                mb = ck.stat().st_size / 1e6
                if mb < 50:
                    state, detail = "BAD_CKPT", f"{mb:.0f}MB — truncated?"
                elif not zipfile.is_zipfile(ck):
                    state, detail = "BAD_CKPT", f"{mb:.0f}MB, not a zip archive"
                else:
                    state, detail = "OK", f"{mb:.0f}MB, zip magic ok"
        elif step == "evaluate":
            import pandas as pd
            rep = BASE / "phase4" / "eval" / "semantic_eval_report.csv"
            if not rep.exists():
                state, detail = "MISSING", f"no {rep.name}"
            else:
                df = pd.read_csv(rep)
                n = int((df["year"].astype(str) == str(y)).sum())
                state = "OK" if n else "MISSING"
                detail = f"{n} rows for year {y} in {rep.name}"
        elif step == "inference":
            out = MASKS / f"edmonds_canopy_prob_{y}_{tag}.tif"
            state, detail = _check_prob_raster(out)
    except Exception as e:                                      # noqa: BLE001
        state, detail = "UNCHECKED", f"{type(e).__name__}: {e}"[:200]
    rec = dict(job=job["id"], year=y, tag=tag, step=f"VERIFY:{step}",
               state=state, exit="", minutes="", detail=detail,
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    rows.append(rec)
    _status_write(rows)
    print(f"  VERIFY:{step} {job['id']}: {state}  {detail}")
    return state not in _VERIFY_HARD_FAIL


def verify(job, rows):
    """Job-end raster check (the historical VERIFY row scoring flows expect).
    Never raises — this is unattended."""
    out = MASKS / f"edmonds_canopy_prob_{job['year']}_{job['tag']}.tif"
    rec = dict(job=job["id"], year=job["year"], tag=job["tag"], step="VERIFY",
               state="", exit="", minutes="", detail="",
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        state, detail = _check_prob_raster(out)
        rec.update(state=state, detail=detail)
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
    ap.add_argument("--retries", type=int, default=2,
                    help="Retries after a STRAY interrupt (default 2). Two interrupts "
                         "within 20s always stop the queue.")
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

    # only path-valued extras (e.g. --add-canopy-mask <file>) are checkable;
    # bare flags like --force-citywide used to trip a false MISSING warning here
    missing = [j["id"] for j in todo
               if j["extra"] and not j["extra"][-1].startswith("-")
               and not Path(j["extra"][-1]).exists()]
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
            res = run_step(j, st, args.infer_batch, rows)
            tries = 0
            while res == "RETRY" and tries < args.retries:
                tries += 1
                print(f"  retrying {j['id']}/{st}  (attempt {tries+1}/{args.retries+1})")
                res = run_step(j, st, args.infer_batch, rows)
            if res == "RETRY":
                print(f"  ! {j['id']}/{st} kept getting interrupted; giving up on this job.")
                res = False
            if not res:
                print(f"  ! {j['id']} failed at step '{st}'. "
                      f"Recording and moving to the NEXT JOB (queue is unattended).")
                ok = False
                break
            if not verify_step(j, st, rows):
                print(f"  ! {j['id']} step '{st}' exited 0 but its ARTIFACT failed "
                      f"verification. Stopping this job before spending more GPU.")
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

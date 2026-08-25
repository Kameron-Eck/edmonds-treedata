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
    * The best model in the project (2023n: out-of-sample AUROC .9538, NIR +
      CHM, healthy calibration) still scores honest recall .6564 — inside the
      same .51-.71 band as far weaker years. Better models do NOT close the
      gap, so the gap is SYSTEMATIC.
    * P2 showed the two references contradict each other on 16.0% of valid
      pixels, and 38.7% of the headline "miss" is therefore UNMEASURABLE.

  Two live hypotheses for the systematic part, and one job each:
    H1  the REFERENCES over-call canopy      -> needs more NIR years, because
        only NIR years can build an NDVI reference and be P2-partitioned.
        JOBS: 2019n, 2021s  (2016 and 2023n already have refs)
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
    * Status is flushed to Drive after every step, to THIS launch's own file
      phase4/qc/train_queue_status_{queue}_{launchts}.csv (P11.1: concurrent
      queues never clobber each other; readers merge all train_queue_status*.csv).
      That file is the monitoring hook — it survives the runtime dying.
    * Cheapest-first, so a runtime that dies early still delivers the most
      informative results. (Queues 1-2 were coarse ~1 h jobs; the P11.4 queues
      carry 5 cm CoE years whose inference alone runs ~4.5 h — see the ceilings.)
    * --run-tag on every job, so nothing existing is overwritten.

  ── USAGE (Colab; P11.5: A100 40 GB for real runs, L4/T4 for canaries) ──
  Code is CLONED from GitHub since 2026-08-20 (see pipeline/colab_launch.ipynb —
  that notebook is the standing cockpit; the recipe below is what it runs).
  LAUNCH DETACHED. This is the important part for an unattended run:

      %cd /content/repo/Scripts/pipeline
      !nohup python -u phase4_train_queue.py --queue QUEUE.yaml > /content/drive/MyDrive/treedata/phase4/logs/train_queue_nohup_QUEUE_TS.log 2>&1 &
      (one log per queue launch — a shared path was truncated by a second
       runtime's `>` on 2026-08-22 and queue3's stdout was lost; cell 3 of the
       cockpit builds the name from the queue stem + UTC launch timestamp)

  With %run the queue lives INSIDE the notebook kernel, so anything that
  interrupts the cell kills it — and Colab sends SIGINT to the kernel whenever
  the websocket drops. On 2026-08-18 that killed the queue 18 s in while the
  user was nowhere near the stop button. Launched with nohup it is a separate
  process: cell interrupts, browser close and connection blips cannot touch it,
  and it dies only when the RUNTIME itself dies.

  Watch it (either from a Colab cell or from the synced Drive copy):
      !tail -f "$(ls -t /content/drive/MyDrive/treedata/phase4/logs/train_queue_nohup*.log | head -1)"
      phase4/qc/train_queue_status_{queue}_{launchts}.csv   <- one row per step, on
                                     Drive; readers merge every train_queue_status*.csv

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
import socket
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
# points from real runs: 2023n full path ~55 min total; the 2017 CoE-grid
# inference ran 254.9 min on L4 — the old 240-min inference ceiling would have
# killed 2024/2017/2022 fifteen minutes short (found 2026-08-22). Since P11.4
# a step may also WAIT for another runtime's bulk copy (the Drive staging lock,
# phase4seg/common.py, which gives up after STAGE_LOCK_MAX_WAIT_MIN = 60 and
# proceeds unlocked). Invariant, per step that takes the lock once:
#   ceiling > STAGE_LOCK_MAX_WAIT_MIN + own staging + largest observed work
#   labels 120 > 60 + 26 + 27 (non-citywide only: it stages the native ortho, up to
#   48 GB; every --force-citywide job skips it) · tile 180 > 60 + 26 + 24 ·
#   train 300 > 60 + 60 (tile sets are 0.2-0.7 GiB, below the lock's floor, so the
#   wait term is slack) · inference 480 > 60 + 26 + 255 + verified copy.
STEP_TIMEOUT_MIN = {"labels": 120, "tile": 180, "train": 300,
                    "evaluate": 60, "inference": 480}

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
# 2016, 2019n, 2021s, 2023n) already trains on the citywide 2020-mask path by
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
         why="City of Edmonds 5 cm. Last year off-recipe; pairs with 2023n (NAIP).",
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


# P11.1 concurrency-safe status: each queue LAUNCH writes its own file
# (train_queue_status_{queue}_{launchts}.csv) and never touches anyone else's.
# The old single-file rewrite made two concurrent queues clobber each other's
# rows (observed 2026-08-22 01:00-01:03Z). Readers — resume here, and the
# pipeline_status/watch_queue tools — merge ALL status files, so history is the
# union. The legacy train_queue_status.csv remains as read-only history.
STATUS_OUT = None    # set per launch in main()


def _status_files():
    """Every status file, legacy single-file first, then per-launch files."""
    files = sorted(QC_DIR.glob("train_queue_status*.csv"))
    return files


def _merged_rows():
    """Union of all status files' rows, sorted by ts (UTC, lexically sortable)."""
    rows = []
    for f in _status_files():
        try:
            rows.extend(csv.DictReader(io.open(f, encoding="utf-8", newline="")))
        except Exception as e:                                  # noqa: BLE001
            print(f"  ! WARN could not read {f.name} ({e}); skipping it.")
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def _completed_steps():
    """(job_id, step) pairs already recorded OK — across ALL status files — so a
    restart does not redo them, even when the prior attempt ran as a different
    queue launch.

    The engine's labels/tile steps are idempotent and train/evaluate/inference
    write tagged outputs, so skipping a previously-OK step is safe and turns a
    dead runtime into a cheap restart instead of starting from zero.
    """
    done, bad = set(), set()
    for r in _merged_rows():                       # sorted by ts: later rows win
        job, step, state = r.get("job"), str(r.get("step", "")), r.get("state")
        key = (job, step)
        if step in STEPS:
            if state == "OK":
                done.add(key)
                bad.discard(key)                   # a fresh OK supersedes an old fail
            elif state in ("FAIL", "ERROR", "TIMEOUT", "INTERRUPTED", "RUNNING"):
                # a LATER attempt that failed, or started and never reported (the
                # runtime died; a mid-copy kill can leave a partial artifact),
                # revokes an earlier OK — re-running an idempotent step is cheap.
                bad.add(key)
        elif step.startswith("VERIFY:") and step[7:] in STEPS:
            # A step can exit 0 without its artifact (e.g. step_tile's "no tiles"
            # early return) — its OK row must not license a skip if VERIFY:{step}
            # then hard-failed. Pre-P4.3 history has no VERIFY:{step} rows and is
            # unaffected. (Audit finding 2026-08-22.)
            if state in _VERIFY_HARD_FAIL:
                bad.add((job, step[7:]))
            else:
                bad.discard((job, step[7:]))
        elif step == "VERIFY" and state in _VERIFY_HARD_FAIL:
            bad.add((job, "inference"))          # job-end raster check failed
    return done - bad


def _hr(t=""):
    print("\n" + "=" * 74)
    if t:
        print(f"  {t}")
        print("=" * 74)


def _status_write(rows):
    """Flush THIS LAUNCH's rows to its own status file. Called after EVERY step.

    Rewriting only our per-launch file means concurrent queues can never erase
    each other's records (P11.1); readers merge across files.
    """
    try:
        QC_DIR.mkdir(parents=True, exist_ok=True)
        out = STATUS_OUT if STATUS_OUT is not None else STATUS
        cols = ["job", "year", "tag", "step", "state", "exit", "minutes",
                "detail", "ts"]
        with io.open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! WARN could not write status: {e}")


def _gpu_line():
    """P11.5: name the GPU tier in the queue header (tier attribution for cost and
    timing; the ceilings were sized on L4). Torch-free, best-effort."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                            "--format=csv,noheader"], capture_output=True, text=True,
                           timeout=20)
        q = r.stdout.strip()
        if r.returncode != 0 or not q:       # a CPU runtime prints a driver banner + rc!=0
            return "none (CPU runtime or no driver)"
        return q.splitlines()[0]
    except Exception:                                           # noqa: BLE001
        return "unknown (nvidia-smi unavailable)"


def _sweep_child_claims(pid):
    """Best-effort: remove the staging-lock claim(s) an engine we just KILLED left on
    Drive (its heartbeat died with it; __exit__ never ran). Call only after the
    child is reaped, so no re-stamp can land after the unlink. Without this a
    cross-VM peer waits STAGE_LOCK_STALE_MIN for a claim we know is dead."""
    try:
        for p in (BASE / "phase4" / "locks").glob(f"staging.{socket.gethostname()}.{pid}.*"):
            try:
                p.unlink()
                print(f"  swept dead staging claim {p.name}", flush=True)
            except OSError:
                pass
    except OSError:
        pass


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
            _sweep_child_claims(proc.pid)          # child is reaped (proc.wait above)
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
        try:
            proc.wait(timeout=10)                  # reap before sweeping its claim
        except Exception:
            pass
        _sweep_child_claims(proc.pid)
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


# Sanity-read budget in PIXELS, not rows. A fixed row count made the check
# resolution-dependent: 1200 rows is ~1:45 of a 10 cm raster but ~1:177 of a 5 cm CoE
# raster (211,968 rows), so the 5 cm years sampled ~15x more sparsely and missed their
# rare high-confidence pixels. 2022 measured max 0.728 at 1200 rows and 1.000 at 4800
# rows or a full pass — a WEAK_CALIBRATION false alarm that 2024 and 2017 would have
# repeated. A fixed pixel budget keeps the sampling density comparable across tiers.
_PROB_SAMPLE_PX = 4_000_000


def _check_prob_raster(out):
    """Decimated sanity read of a prob raster → (state, detail)."""
    if not out.exists():
        return "MISSING", f"no raster at {out.name}"
    mb = out.stat().st_size / 1e6
    import rasterio
    from rasterio.enums import Resampling
    with rasterio.open(out) as s:
        scale = min(1.0, (_PROB_SAMPLE_PX / float(s.width * s.height)) ** 0.5)
        h = max(1200, min(s.height, int(s.height * scale)))
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
    # p99.9 travels with the state: max is one pixel and says nothing about the shape of
    # the tail. 2022 read max 1.000 but p99.9 0.665 with only 0.014% of pixels above 0.7 —
    # a compressed upper tail the max alone would have hidden from the scoring step.
    import numpy as _np
    p999 = float(_np.percentile(a[v], 99.9)) / 254.0 if v.any() else float("nan")
    return state, (f"{mb:.0f}MB valid={vf:.1%} maxprob={mx:.3f} p99.9={p999:.3f} "
                   f"[{h}x{w} sample]")


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


def _load_queue(path):
    """P6.3 queue-as-data: load the job list from a YAML file.

    Ends the pick-jobs-by-editing-source era: a queue is a reviewable artifact
    (id, year, tag, extra, why, expect per job), and the launch line names it.
    """
    import yaml
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p     # queue files live beside the code
    with open(p, encoding="utf-8") as f:
        jobs = yaml.safe_load(f)
    if not isinstance(jobs, list) or not jobs:
        sys.exit(f"queue file {p} must be a non-empty YAML list of jobs")
    for i, j in enumerate(jobs):
        missing = [k for k in ("id", "year", "tag") if not j.get(k)]
        if missing:
            sys.exit(f"queue file {p}: job #{i} missing {missing}")
        j.setdefault("extra", [])
        j.setdefault("why", "")
        j.setdefault("expect", "")
        j["year"] = str(j["year"])
        j["id"] = str(j["id"])
    return jobs


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
    # Colab injects `-f /root/.local/.../kernel-XXX.json` into argv; strip THE PAIR,
    # not every .json-suffixed value — the old any-.json filter silently ate the
    # --infer-aoi value (aoi/sectors_v1.json), found 2026-08-25 on the first VM dry-run.
    filtered, _skip = [], False
    for a in argv:
        if _skip:
            _skip = False
            continue
        if a == "-f":
            _skip = True
            continue
        if a.endswith(".json") and (not filtered or not filtered[-1].startswith("--")):
            continue          # a bare kernel-json with no owning flag (belt and braces)
        filtered.append(a)


    ap = argparse.ArgumentParser(description="Unattended Phase-4 training queue.")
    ap.add_argument("--infer-batch", type=int, default=32)
    ap.add_argument("--queue", default=None,
                    help="P6.3 queue-as-data: YAML file of jobs (id, year, tag, "
                         "extra, why, expect). Replaces editing JOBS in source. "
                         "e.g. --queue queue3.yaml")
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

    jobs = _load_queue(args.queue) if args.queue else JOBS

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    todo = [j for j in jobs if j["id"] not in skip
            and (args.only is None or j["id"] == args.only)]

    _hr("PHASE 4 — UNATTENDED TRAIN QUEUE")
    print(f"  BASE   : {BASE}")
    print(f"  GPU    : {_gpu_line()}   (ceilings sized on L4; P11.5 default = A100 for real runs)")
    print(f"  queue  : {args.queue or 'JOBS (in-source)'}")
    print(f"  status : {QC_DIR}\\train_queue_status_*.csv   "
          f"(per-launch file, flushed after EVERY step; readers merge all)")
    print(f"  jobs   : {len(todo)} of {len(jobs)}")
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

    global STATUS_OUT
    _stem = Path(args.queue).stem if args.queue else "jobs"
    _launch_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    STATUS_OUT = QC_DIR / f"train_queue_status_{_stem}_{_launch_ts}.csv"
    if _COLAB_BASE.exists():            # P11.4: the staging-lock dir must pre-exist —
        (BASE / "phase4" / "locks").mkdir(parents=True, exist_ok=True)   # never let two VMs race to create it
    print(f"  writing status to {STATUS_OUT.name}  (readers merge all "
          f"train_queue_status*.csv)")

    rows = []                       # per-launch file holds only THIS launch's rows
    done = set() if args.no_resume else _completed_steps()
    if done:
        print(f"\n  RESUME: {len(done)} step(s) already OK across all status files "
              f"will be SKIPPED.")
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
    print(f"\n  Status table: {STATUS_OUT if STATUS_OUT is not None else STATUS}"
          "  (readers merge all train_queue_status*.csv)")
    print("  Scoring happens LOCALLY afterwards (no GPU): phase4_qc_indep.py,")
    print("  then phase4_ref_agreement.py for the NIR years.")


if __name__ == "__main__":
    main()

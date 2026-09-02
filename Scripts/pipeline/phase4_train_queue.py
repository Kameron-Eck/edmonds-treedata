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
import datetime as _dt
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from phase4seg.names import (
    clean_argv,
    VERIFY_HARD_FAIL, pid_alive, sanitize_tag, status_out_name, tile_dir_name,
)

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE, COLAB_BASE as _COLAB_BASE  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent  # the CODE dir (repo pipeline/), NOT a Drive path
QC_DIR  = BASE / "phase4" / "qc"
MASKS   = BASE / "phase4" / "masks"
LABELS  = BASE / "phase4" / "labels_corrected"
ENGINE  = SCRIPTS / "phase4_semantic_finetune.py"
STATUS  = QC_DIR / "train_queue_status.csv"

# postproc IS in this list as of 2026-08-30, and its absence was a real defect:
# step_postproc polygonises the probability raster into the binary canopy mask +
# GPKG — THE deliverable — and config.PER_YEAR_STEPS has always included it. But the
# queue passes an explicit --step (see run_step), cli.py sets per_year=[args.step],
# so cli.py's `if "postproc" in per_year` was never true under the queue. The step
# ran only from a hand-typed command, and --skip-postproc in a queue file was a no-op
# because it skipped something that never ran.
STEPS = ["labels", "tile", "train", "evaluate", "inference", "postproc"]

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
                    "evaluate": 60, "inference": 480, "postproc": 120}

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




# ── Who and where (D13) ───────────────────────────────────────────────────────
# NO ARTIFACT ANSWERED "what is running where, under which tag". The status CSV
# named the job and the tag but never the machine, so with several runtimes
# writing into one lake directory, a row could not be attributed to a VM at all —
# and the 2026-08-29 post-mortem had to infer which VM produced which checkpoint
# from timestamps. Every row now carries host and session.
#
# The session name is the Colab CLI's handle for this runtime, which the VM itself
# has no API to ask for: the bootstrap knows it and hands it down, via COLAB_SESSION
# in the environment and /content/session.txt on local disk. The file exists because
# each `colab exec` is a fresh shell that does not inherit the bootstrap's env —
# only the processes the bootstrap itself spawned do.




# Files _merged_rows could not read on its last pass. Not decoration: a dropped
# status file silently REWRITES HISTORY (see _merged_rows), so callers that make
# decisions from the merge have to be able to ask whether the merge was complete.











def _hr(t=""):
    print("\n" + "=" * 74)
    if t:
        print(f"  {t}")
        print("=" * 74)






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
               exit="", minutes="", detail="", **_ident(),
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




# P4.3: states that mean "the artifact this step just paid for is broken" —
# the queue must stop spending on this job, not sail into the next GPU hour.
# One home for the vocabulary (phase4seg/names.py). It used to live here and be
# hand-copied into watch_queue.BAD and sector_campaign_loop.HARD_FAIL, and those two
# copies were each MISSING states this file really writes — so a run that died on
# UNREADABLE, STALE_EVAL or SIZE_CHANGED made runtime_health print ALL_OK.
_VERIFY_HARD_FAIL = VERIFY_HARD_FAIL

# D7 (2026-08-29): states that mean "THIS CHECK COULD NOT ANSWER" — which is not
# the same as "the artifact is fine", and used to be recorded as if it were.
#
# Every exception inside verify_step landed on UNCHECKED, UNCHECKED was not in
# _VERIFY_HARD_FAIL, and everything downstream treats not-hard-fail as a pass: the
# job continued, and _completed_steps positively DISCARDED the step's bad marker,
# so a later relaunch skipped a step whose artifact had never been looked at. A
# check that throws was therefore indistinguishable from a check that succeeded —
# the exact defect class that let an epoch-7 checkpoint be deployed as epoch 24.
#
# These states now: (a) print as a warning, (b) never license a silent skip — the
# step keeps its OK credit but is RE-VERIFIED on the next launch, which is cheap,
# rather than re-run, which is GPU spend nobody approved, and (c) survive into the
# status CSV as themselves so the end-of-queue summary can show them.
_VERIFY_UNVERIFIED = {"UNCHECKED", "UNVERIFIED"}


_SA_REMOTE = "treedata-sa"                       # gen_vm_bootstrap.py's VERIFIER remote
_DRIVE_MOUNT_PREFIX = "/content/drive/MyDrive/treedata/"












# ── the status ledger lives in queue_ledger.py since 2026-09-01 ──────────────
# Same facade contract: module attributes here, paths resolved back through here.
import io   # noqa: F401 — facade surface: the never-truncate test patches q.io.open
            # (module-object patch, so queue_ledger's io.open sees it too)
from queue_ledger import (      # noqa: E402,F401
    _MERGE_DEFECTS, _completed_steps, _ident, _job_key, _merged_rows,
    _read_status_file, _replace_absent, _status_files, _status_write,
)
# _MERGE_DEFECTS is mutated IN PLACE (clear/append, never rebound), so this binding
# shares the one list — q._MERGE_DEFECTS stays truthful, and the test that reads it
# after forcing an unreadable file keeps working.

# ── artifact verification lives in queue_verify.py since 2026-09-01 ──────────
# Facade contract: tests and callers reach these as module attributes here, and the
# moved code reads paths/state THROUGH this module so monkeypatches keep working.
from queue_verify import (      # noqa: E402,F401
    _check_prob_raster, _drive_matches_mount, _md5_of, _mb_from_verdict,
    _parse_utc, _recheck_skipped_verify, _verify_ckpt_identity, _verify_eval_rows,
    verify_step,
)


def _sanitize_tag(tag):
    """The run-tag sanitiser. NO LONGER A TWIN — shared with the engine via
    phase4seg.names, which is stdlib-only, so importing it does not drag rasterio
    and friends into the orchestrator. Kept as a name here because callers and one
    test refer to it."""
    return sanitize_tag(tag)


def _tagged_tile_index(y, tag):
    """Where THIS ARM's tile index lives. The directory RULE is shared with the
    engine (phase4seg.names.tile_dir_name); only the root differs, which is the
    entire reason the twin existed."""
    return BASE / "phase4" / "tiles" / tile_dir_name(y, tag) / f"tile_index_{y}.csv"




def _assert_label_source_declared(job, queue_path):
    """A job must SAY where its training labels come from. Refuse if it does not.

    THE HAZARD. `polygons/` was overwritten with accept-all test data and the
    14,476-crown human review was never finished, so the per-site crown-polygon label
    path trains on labels nobody has validated. Every one of the 32 queue files passes
    --force-citywide, which avoids it — but the queue does NOT inject that flag (see
    run_step: it adds only --year/--step/--infer-batch/--run-tag). It arrives from the
    YAML alone.

    So the protection against training on known-bad labels was one omitted line in a
    hand-written file, with no error if the line went missing: cli.py would compute
    `citywide = (tier == "coarse" or force_citywide)`, get False on a fine/medium year,
    and quietly take the polygon path. Nothing downstream would look wrong.

    This makes the guard structural. Coarse-tier years are exempt because the tier
    ALREADY forces citywide — requiring a redundant flag there would train people to
    add flags that do nothing, which is its own hazard.

    The escape hatches are the real opt-ins, not a bypass: --anchor-labels selects the
    third label source (the 2020 probability raster), and --coarse-site-tiling is the
    explicit "yes, I mean the site path" switch. Either one is a declaration.
    """
    from phase4seg import config as _cfg      # stdlib-only import (see names.py)

    extra = [str(x) for x in job.get("extra", [])]
    if any(f in extra for f in ("--force-citywide", "--anchor-labels",
                                "--coarse-site-tiling")):
        return
    # Look the entry up directly rather than via common.entry_for — common.py carries
    # the heavy imports this module exists to avoid, and config.py is stdlib-only.
    # (The first version called config.entry_for, which does not exist; the lookup
    # raised, tier fell to None, and the coarse exemption below became dead code. It
    # went unnoticed because every shipped queue carries a flag, so the lookup never
    # ran. A test for the exemption is what surfaced it.)
    entry = next((e for e in _cfg.YEAR_CATALOG
                  if str(e.get("label")) == str(job["year"])), None)
    tier = _cfg.tier_for(entry) if entry else None
    if tier == "coarse":
        return                            # the tier already forces citywide
    sys.exit(chr(10).join([
        f"queue file {queue_path}: job {job['id']!r} (year {job['year']}, tier "
        f"{tier or 'unknown'}) does not declare a label source.",
        "  Without --force-citywide a fine/medium year takes the PER-SITE CROWN POLYGON",
        "  path, and `polygons/` was overwritten with accept-all test data — the",
        "  14,476-crown review was never finished.",
        "  Add one of: --force-citywide (the citywide 2020 mask, what every existing",
        "  queue uses) | --anchor-labels (the 2020 probability raster) |",
        "  --coarse-site-tiling (yes, I really mean the site polygons).",
    ]))



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
        # Optional per-job step subset (Tier 1, 2026-09-02): lets one queue run
        # labels..evaluate under --sample-manifest while a second runs inference
        # under --infer-aoi — per-step FLAGS stay impossible (one cmd shape per
        # job), per-job STEP LISTS are enough. Must be a subset of STEPS in
        # engine order; verify_step is already per-step so nothing else changes.
        if "steps" in j:
            bad = [s for s in j["steps"] if s not in STEPS]
            if bad:
                sys.exit(f"queue file {p}: job {j['id']} has unknown steps {bad}")
            j["steps"] = [s for s in STEPS if s in set(j["steps"])]
        _assert_label_source_declared(j, p)
    return jobs


def verify(job, rows):
    """Job-end raster check (the historical VERIFY row scoring flows expect).
    Never raises — this is unattended. False on a hard failure.

    A job with a STEPS SUBSET that never reaches inference has no prob raster
    to check — demanding one flagged all 7 of t1stageA's staged jobs as
    'did NOT complete and verify' after 130 clean minutes (measured
    2026-09-02, the steps feature's first real run). The tile step's own
    verify_step already covered what those jobs produced; the job-end check
    applies only when the job's steps actually make the raster."""
    if "steps" in job and "inference" not in job["steps"]:
        rec = dict(job=job["id"], year=job["year"], tag=job["tag"], step="VERIFY",
                   state="OK", exit="", minutes="",
                   detail=f"steps subset {job['steps']} — no prob raster expected; "
                          f"per-step verifies are the record", **_ident(),
                   ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        rows.append(rec)
        _status_write(rows)
        print(f"  VERIFY {job['id']}: OK  {rec['detail']}")
        return True
    out = MASKS / f"edmonds_canopy_prob_{job['year']}_{job['tag']}.tif"
    rec = dict(job=job["id"], year=job["year"], tag=job["tag"], step="VERIFY",
               state="", exit="", minutes="", detail="", **_ident(),
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        state, detail = _check_prob_raster(out)
        rec.update(state=state, detail=detail)
    except Exception as e:                                      # noqa: BLE001
        rec.update(state="UNCHECKED", detail=f"{type(e).__name__}: {e}"[:200])
    rows.append(rec)
    _status_write(rows)
    print(f"  VERIFY {job['id']}: {rec['state']}  {rec['detail']}")
    # Same contract as verify_step and _recheck_skipped_verify. This one returned
    # None, so the job-end raster check — the MOST COMMON verify path — was the one
    # the new exit code did not see: a job could end with its raster EMPTY and the
    # queue still exited 0.
    return rec["state"] not in _VERIFY_HARD_FAIL






TAGS_FILE = Path("/content/queue_tags.json")     # read by vm_heartbeat.run_tags


def _declare_run_tags(todo, queue_name, job="", step=""):
    """Tell this VM's beacon which run tags this queue owns (D11).

    The beacon republishes this to the lake every 60 s, which is what gives the
    cross-VM guard a FRESH answer during a multi-hour step. The queue could not
    provide that itself: between its own writes there can be four hours of
    training, far past any staleness window a guard could use.

    LOCAL disk, never the lake: it describes this process, and the beacon — which
    checks the pid is still live — is what turns it into a claim others can see.
    Best-effort; a declaration that cannot be written must not stop a run (the
    guard then reports itself unprotected, which is the honest outcome).
    """
    if not _COLAB_BASE.exists():
        return                                   # not a VM; nothing reads this
    try:
        TAGS_FILE.write_text(json.dumps({
            "pid": os.getpid(), "queue": str(queue_name), "job": job, "step": step,
            "tags": sorted({str(j["tag"]) for j in todo}),
            "ts_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **_ident(),
        }), encoding="utf-8")
    except OSError as e:
        print(f"  [dup-guard] could not declare run tags ({e}) — peers will fall back "
              f"to reading this VM's engine cmdline, which is blank between steps")


def _pid_alive(pid):
    """Is this pid running on this host? Shared with the engine via phase4seg.names.

    These were twins and they DID diverge: this copy was added on 2026-08-30 WITHOUT
    the `os.name != "posix"` guard the engine's copy has carried all along, so on
    Windows it would have called TerminateProcess instead of probing. That is the
    argument for one implementation, made concrete.
    """
    return pid_alive(pid)


def _tag_owners(want, max_age_s=300):
    """Which OTHER live runtimes hold a tag in `want`.

    → (clashes, scanned, blind): clashes is [(vm, tag, how)], scanned counts LIVE
    beacons read, and `blind` is a sentence explaining why the scan proves nothing
    (None when it was sound).

    Prefers each beacon's DECLARED `run_tags` (D11) and falls back to the old
    cmdline regex for beacons from an older build. The regex is why this guard was
    weak: it reads the ENGINE's cmdline, which is absent between engine steps and
    truncated to the last 200 characters, so a queue that owned a tag continuously
    appeared to hold it only in bursts.
    """
    logs = BASE / "phase4" / "logs"
    me = _ident()
    me_pid = str(os.getpid())
    clashes, scanned, files = [], 0, []
    try:
        files = list(logs.glob("heartbeat_*.json"))
    except OSError as e:
        return [], 0, f"could not list {logs} ({type(e).__name__}: {e})"
    for hb in files:
        try:
            if time.time() - hb.stat().st_mtime > max_age_s:
                continue                          # stale beacon = dead VM
            d = json.loads(hb.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scanned += 1
        # IS THIS BEACON PUBLISHING US? Two ways to tell, and BOTH are needed.
        # run_tags_pid only exists in post-D11 beacons, and the beacon is NOT
        # restarted when a queue is relaunched on a fix/ branch (P11.5) — the VM
        # pulls and reruns the queue while the old beacon keeps running. On such a
        # VM our own heartbeat carries no run_tags, falls through to the cmdline
        # fallback below, and matches OUR OWN engine's --run-tag: every job after
        # the first would skip itself as TAG_IN_USE, since a whole queue shares one
        # tag. The same happens on a new beacon whenever the declaration could not
        # be written. queue_proc has been published since long before D11 and on
        # our own host that pid is us.
        # No protection is lost: this guard is documented as cross-VM only —
        # same-VM duplicates are the launch-script interlock's job.
        if d.get("host") == me["host"] and me_pid in {
                str(d.get("run_tags_pid") or ""), str(d.get("queue_proc") or "")}:
            continue
        # SAME HOST, DIFFERENT PID — this is the relaunch case, and it used to be
        # fatal. The beacon SURVIVES a queue relaunch (comment above), so after a
        # crash it keeps publishing the DEAD queue's pid, fresh, under our own tag.
        # Self-recognition compares pids, ours is new, so the guard read its own
        # corpse as a live peer and the relaunch died on REFUSING TO START — the
        # exact crash-fix-rerun loop P11.5 exists to allow. A pid on OUR host we
        # can simply ask about; a pid on another host means nothing and is left
        # alone, so the cross-VM protection this guard is actually for is intact.
        if d.get("host") == me["host"]:
            _pid = str(d.get("run_tags_pid") or d.get("queue_proc") or "")
            if _pid.isdigit() and not _pid_alive(int(_pid)):
                print(f"  [dup-guard] {hb.name} still claims tag(s) for pid {_pid} "
                      f"on this host, but that process is gone — stale beacon, "
                      f"not a live peer. Ignoring.")
                continue
        vm = d.get("session") or hb.stem.replace("heartbeat_", "")
        declared = d.get("run_tags")
        if isinstance(declared, list) and declared:
            for t in declared:
                if str(t) in want:
                    clashes.append((vm, str(t), "declared"))
        else:
            m = re.search(r"--run-tag (\S+)", d.get("engine_proc") or "")
            if m and m.group(1) in want:
                clashes.append((vm, m.group(1), "engine cmdline"))
    blind = None
    if scanned == 0:
        blind = (f"no live beacons in {logs} "
                 f"({len(files)} heartbeat file(s), all stale or unreadable)")
    return clashes, scanned, blind


def _guard_row(rows, job, state, detail):
    rec = dict(job=job.get("id", "(launch)"), year=job.get("year", ""),
               tag=job.get("tag", ""), step="GUARD:runtag", state=state,
               exit="", minutes="", detail=str(detail)[:200], **_ident(),
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    rows.append(rec)
    _status_write(rows)


def _duplicate_tag_guard(todo, rows, at_launch=True, max_age_s=300):
    """Refuse to run work whose run tag another LIVE VM already holds. → bool ok.

    WHY (2026-08-29). The smoothing arm was found running on TWO VMs at once, both
    mid-tile under `--run-tag smooth5`. A shared run tag means a shared per-arm tile
    directory, a shared sem_best_*.pt and a shared output raster — the same
    concurrent race that corrupted the groves B-vs-C comparison and forced a public
    retraction. Nothing had reached the lake that time; the next one might.

    D11 fixed three ways this could not do its job:

      1. IT RAN ONCE, AT LAUNCH. A queue holds its tags for hours; a peer that
         starts five minutes later was never looked for. It now also runs before
         every job — and a clash there SKIPS THAT JOB, rather than killing a queue
         that has already produced good work.
      2. IT READ THE ENGINE'S CMDLINE. See _tag_owners: absent between steps,
         truncated at 200 chars. Tags are now declared by the queue itself.
      3. IT FAILED OPEN TWICE, IN PRINT ONLY. An unreadable lake and a zero-beacon
         scan both printed a warning to a log nobody reads and proceeded as if
         guarded. Both now also write a GUARD_UNVERIFIED row to the status CSV, so
         "this run was never protected" is a fact in the audit trail rather than a
         line in scrollback.

    Still fails OPEN — a heartbeat that cannot be read must not block a legitimate
    run — but it can no longer fail SILENTLY, which is the difference that matters.
    """
    want = {str(j["tag"]) for j in todo}
    if not want:
        return True
    clashes, scanned, blind = _tag_owners(want, max_age_s)
    if clashes:
        lines = "; ".join(f"{vm} already running tag {tag} [{how}]"
                          for vm, tag, how in clashes)
        _guard_row(rows, {} if at_launch else todo[0], "TAG_IN_USE", lines)
        if at_launch:
            raise SystemExit(
                "REFUSING TO START: another live runtime is already using a run tag "
                f"from this queue ({lines}). Two runs sharing a tag share the tile "
                "dir, the checkpoint and the output raster, which silently corrupts "
                "both. Stop the other runtime, or launch under a different tag.")
        print(f"  ! SKIPPING {todo[0]['id']}: {lines}. Two runs sharing a tag "
              f"corrupt each other's tile dir, checkpoint and raster. The rest of "
              f"the queue continues.", flush=True)
        return False
    if blind:
        print(f"  [dup-guard] WARNING: {blind} — this run is NOT PROTECTED against a "
              f"duplicate tag. Proceeding; recorded as GUARD_UNVERIFIED.")
        _guard_row(rows, {} if at_launch else todo[0], "GUARD_UNVERIFIED", blind)
        return True
    if at_launch:
        print(f"  [dup-guard] scanned {scanned} live beacon(s); no runtime is using "
              f"{sorted(want)} — safe to start")
    return True


def main():
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a.startswith("#"):
            argv = argv[:i]
            break
    # Colab injects `-f /root/.local/.../kernel-XXX.json` into argv; strip THE PAIR,
    # not every .json-suffixed value — the old any-.json filter silently ate the
    # --infer-aoi value (aoi/sectors_v1.json), found 2026-08-25 on the first VM dry-run.
    # Colab -f/.json injection: the ONE pair filter (names.clean_argv). The
    # hand-rolled version here carried a "bare .json with no owning flag" clause
    # that ATE the equals form (--aoi=x.json fell back to default, silently).
    filtered = clean_argv()


    ap = argparse.ArgumentParser(description="Unattended Phase-4 training queue.")
    ap.add_argument("--infer-batch", type=int, default=32)
    ap.add_argument("--queue", default=None,
                    help="P6.3 queue-as-data: YAML file of jobs (id, year, tag, "
                         "extra, why, expect). Replaces editing JOBS in source. "
                         "e.g. --queue pilot_2019_fine.yaml")
    ap.add_argument("--only", default=None,
                    help="Run just these job id(s) — comma-separated. The CPU "
                         "fan-out rule needs multi-job splits (Tier 1, 2026-09-02); "
                         "a single id behaves exactly as before.")
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
    only = ({s.strip() for s in args.only.split(",") if s.strip()}
            if args.only else None)
    todo = [j for j in jobs if j["id"] not in skip
            and (only is None or j["id"] in only)]

    # NB: the duplicate-tag guard used to run HERE, and that was wrong twice over.
    # It ran before the --dry-run return, so a dry run — which spends nothing and
    # touches nothing — could be refused outright by a peer holding a tag. And it
    # ran before STATUS_OUT was set, so any status row it wrote would have landed
    # in the LEGACY SHARED train_queue_status.csv: exactly the cross-queue clobber
    # P11.1 split the files to prevent. It now runs below, after both.

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
            for st in j.get("steps", STEPS):
                print(f"    --year {j['year']} --step {st} --run-tag {j['tag']} "
                      f"{' '.join(j['extra'])}".rstrip())
        return

    if not ENGINE.exists():
        raise SystemExit(f"engine missing: {ENGINE}")

    global STATUS_OUT
    _stem = Path(args.queue).stem if args.queue else "jobs"
    _launch_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    STATUS_OUT = QC_DIR / status_out_name(_stem, _launch_ts)
    if _COLAB_BASE.exists():            # P11.4: the staging-lock dir must pre-exist —
        (BASE / "phase4" / "locks").mkdir(parents=True, exist_ok=True)   # never let two VMs race to create it
    print(f"  writing status to {STATUS_OUT.name}  (readers merge all "
          f"train_queue_status*.csv)")

    rows = []                       # per-launch file holds only THIS launch's rows
    # Guard BEFORE any spend, but after STATUS_OUT exists so its row lands in this
    # launch's own file, and after the dry-run return so a free plan is never
    # refused. Declaring our tags only once the guard has passed keeps a queue from
    # ever colliding with its own claim.
    _duplicate_tag_guard(todo, rows, at_launch=True)
    _declare_run_tags(todo, args.queue or "JOBS")

    done, reverify, verdicts = ((set(), set(), {}) if args.no_resume
                                else _completed_steps())
    if done:
        print(f"\n  RESUME: {len(done)} step(s) already OK across all status files "
              f"will be SKIPPED.")
        print(f"          (pass --no-resume to force everything to re-run)")
    if reverify:
        print(f"  RESUME: {len(reverify)} of those were last left UNVERIFIED — "
              f"skipped but RE-CHECKED, not trusted.")
    unconfirmed = []
    t_all = _dt.datetime.now()
    for j in todo:
        _hr(f"JOB {j['id']}  (year {j['year']}, tag {j['tag']})")
        print(f"  {j['why']}")
        # D11: re-check per job, not only at launch. A peer that started after us
        # holds its tag from then on, and the launch-time scan could not have seen
        # it. A clash here costs this ONE job, not the queue.
        if not _duplicate_tag_guard([j], rows, at_launch=False):
            # skipped, not completed: it belongs in the exit code too
            unconfirmed.append(j["id"])
            continue
        _declare_run_tags(todo, args.queue or "JOBS", job=j["id"])
        ok = True
        ran_any = False
        for st in j.get("steps", STEPS):
            _k = _job_key(j["id"], j["year"], j["tag"], st)
            if _k in done:
                if _k in reverify:
                    # D7: last time, the check itself failed — so this step is
                    # recorded OK on no evidence. Re-CHECK it (seconds, no GPU);
                    # do not re-RUN it (hours, and spend nobody approved).
                    print(f"  - {j['id']}/{st} was left UNVERIFIED — re-checking "
                          f"before trusting the skip")
                    if not verify_step(j, st, rows, step_start=None, reverify=True):
                        print(f"  ! {j['id']} skipped step '{st}' and its artifact "
                              f"FAILED verification. Stopping this job.")
                        ok = False
                        break
                else:
                    print(f"  - skip {j['id']}/{st} (already OK)")
                continue
            ran_any = True
            _declare_run_tags(todo, args.queue or "JOBS", job=j["id"], step=st)
            _t_step0 = time.time()
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
            if not verify_step(j, st, rows, step_start=_t_step0):
                print(f"  ! {j['id']} step '{st}' exited 0 but its ARTIFACT failed "
                      f"verification. Stopping this job before spending more GPU.")
                ok = False
                break
        _vkey = _job_key(j["id"], j["year"], j["tag"], "VERIFY")
        if ok and not ran_any and _vkey in done:
            # Fully-skipped job with a recorded job-level VERIFY OK: do NOT
            # re-read its raster through the FUSE mount — a relaunch re-verify
            # hung the queue in uninterruptible disk sleep on a 146MB read
            # (2018s_fx, 2026-08-27). But do not declare it verified on no
            # evidence either (D9): stat it, and record OK_CACHED, not OK.
            # The return was DISCARDED here. _recheck_skipped_verify exists to
            # notice that a fully-skipped job's raster is now GONE or a different
            # size than the verdict measured - and both of those are hard failures
            # that changed nothing: the queue printed the row and carried on as if
            # the job were complete. Captured now, and it decides the exit code.
            if not _recheck_skipped_verify(j, rows, verdicts.get(_vkey)):
                ok = False
        elif ok:
            if not verify(j, rows):
                ok = False
        if not ok:
            unconfirmed.append(j['id'])

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
    # The queue used to exit 0 no matter what: a job could fail every step, or have
    # its artifact confirmed missing, and the launcher saw success. For an
    # UNATTENDED queue the exit code is the only signal that reaches anything
    # outside the status CSV, so it now reports whether the work actually landed.
    if unconfirmed:
        print("")
        print(f"  {len(unconfirmed)} job(s) did NOT complete and verify: "
              f"{', '.join(unconfirmed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

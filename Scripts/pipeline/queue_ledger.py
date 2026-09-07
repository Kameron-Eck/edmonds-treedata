"""queue_ledger.py — the status-ledger layer, split from phase4_train_queue.py
(2026-09-01; same contract as queue_verify.py).

Discovery (names.status_files), the row key (names.job_key), merge semantics
(latest-wins, defects COUNTED not dropped), resume credit (_completed_steps:
D7/D9/D10), and the atomic status write. Path globals and the STEPS list resolve
through the queue module at call time (`q = _q()`) because test_queue_verify
patches q.QC_DIR / q.STATUS_OUT / q.STATUS / q._status_write — a from-import here
would freeze what the tests redirect. _IDENT / _MERGE_DEFECTS / _STATUS_KEY_COLS
move WITH the cluster; _MERGE_DEFECTS is re-exported (a test reads it, and
in-place mutation keeps the shared binding truthful).

publish_phase_marker / clear_phase_marker are the ONE exception to the `_q()` rule,
and deliberately: they read no queue global at all — the path comes from
phase4seg.names::hw_step_marker_path and the pid from the process — so there is
nothing for `_q()` to resolve and nothing for a test to patch on the queue module.
They live here rather than in phase4_train_queue.py because queue_verify.py needs
them too and this is the module both already import.
"""
import csv
import datetime as _dt
import io
import json
import os
import secrets
import socket
import sys
import time
from pathlib import Path

from phase4seg.names import hw_step_marker_path, job_key, status_files

_QUEUE_FILE = "phase4_train_queue.py"


def _q():
    """The queue module as runtime context — lazy to avoid the import cycle.

    `sys.modules["__main__"]` is consulted FIRST, and that ordering is the whole
    point. In production the queue is started as a SCRIPT — `nohup python -u
    phase4_train_queue.py --queue …` (pipeline/vm_ops.py::launch_queue) — so the
    running module is registered under the name `__main__` and under no other.
    A bare `import phase4_train_queue` therefore does not find it: it EXECUTES
    THE FILE A SECOND TIME under a second name and hands back that second module
    object, whose globals are all import-time defaults.

    Every constant matches between the two copies, so the substitution is
    invisible — except for the one global `main()` assigns at RUNTIME. STATUS_OUT
    stayed None on the copy, so queue_ledger.py::_status_write took its
    `else STATUS` branch and rewrote the SHARED train_queue_status.csv, with only
    this launch's rows, after every step. Launches announced a per-launch file and
    erased the shared ledger instead, from the split that introduced this helper
    (4c546a7, 2026-09-01 03:30 UTC) until 2026-09-07. Measured on the lake that
    day: the newest per-launch file's launch stamp is 20260831T034500Z — the last
    one before the split — and 21 orphaned `.part.*` temps sit beside a shared
    ledger holding four rows of a single session.

    Under pytest `__main__` is pytest's own entry point, so the fallback runs and
    returns the module the tests import and patch — the identity they rely on.
    """
    m = sys.modules.get("__main__")
    if Path(getattr(m, "__file__", "") or "").name == _QUEUE_FILE:
        return m
    import phase4_train_queue
    return phase4_train_queue


_IDENT = None
_MERGE_DEFECTS = []
_STATUS_KEY_COLS = ("job", "year", "tag", "step", "state", "ts")


def _status_files():
    """Every status file, legacy single-file first, then per-launch files."""
    q = _q()
    # ONE discovery rule, shared with every other reader (phase4seg/names.py).
    # The bare glob admitted a test-contaminated file that had been "quarantined"
    # by renaming — see names.py for why a rename alone does not quarantine.
    files = status_files(q.QC_DIR)
    return files

def _ident():
    """{"host": …, "session": …} for this runtime. Resolved once, never raises."""
    q = _q()
    global _IDENT
    if _IDENT is None:
        try:
            host = socket.gethostname()
        except Exception:                                       # noqa: BLE001
            host = ""
        sess = os.environ.get("COLAB_SESSION") or ""
        if not sess:
            try:
                p = Path("/content/session.txt")
                if p.exists():
                    sess = p.read_text(encoding="utf-8").strip()[:64]
            except OSError:
                pass
        _IDENT = {"host": host, "session": sess}
    return _IDENT


# ── the "what is the QUEUE doing right now" marker ───────────────────────────
# The engine publishes its own marker from pipeline_log.py::StepLogger._write_marker
# while a step is open. Everything the queue does AROUND a step — spawning the
# engine and waiting for its imports/bootstrap/staging, and the post-step VERIFY —
# happened with no marker on disk at all, so vm_hwlogger stamped those samples
# blank and qc/instruments/harvest_hw_attribution.py bucketed them as "(between)":
# attributable to nothing. Measured 2026-09-07 on the CPU pilot: 17 min at 44%
# iowait in "(between)" before the first step marker opened — 7 min of it the
# labels VERIFY, 9 min the tile engine process before StepLogger got control.
#
# These two write the SAME object shape as StepLogger plus the `phase` key whose
# vocabulary is owned by phase4seg/names.py::hw_step_marker_path ("launching",
# "verifying"; StepLogger writes none and absent reads as "open"). Deliberately
# NOT via pipeline_log: this module is the orchestrator's, and importing an engine
# module here would pull the engine's dependency tree into the process whose job is
# to keep running when that tree is broken (the _replace_absent twin's reasoning).
#
# Neither raises. A marker that can kill the queue is worse than no marker — the
# same standard pipeline_log.py's docstring sets for its own copy.

def publish_phase_marker(step, year, tag, phase):
    """Publish "the queue is in <phase> around <step>_<year>" for vm_hwlogger.

    `step` is joined to `year` because that is the vocabulary the ENGINE already
    writes (phase4seg/cli.py opens its StepLogger as f"{step}_{lab}"), and the
    harvest's norm_step strips the year suffix off both alike. So a queue marker
    lands in the same step row as the engine's, separated only by its phase.

    THE PID IS OURS, never the engine's. vm_hwlogger.read_marker discards a marker
    whose pid is not alive, so a "verifying" marker carrying the exited engine's pid
    would blank the very phase it exists to record (names.py says so explicitly).

    The two guards are StepLogger's, for its measured reasons: the built-in default
    is the POSIX path /content/hw_step_marker.json, which on Windows resolves
    DRIVE-RELATIVE to a "content" directory that exists on the code-plane box — so
    an existence check alone is not enough off-posix, and an explicit HW_STEP_MARKER
    (tests) is always honoured. The parent must already exist; never mkdir.

    Published temp-then-os.replace, into a pid-suffixed temp, because vm_hwlogger
    opens this file from another process every 5 s and must never read half an
    object. The temp is removed if anything fails, so no `{path}.{pid}.tmp` orphan
    outlives the run.
    """
    tmp = None
    try:
        if os.name != "posix" and not os.environ.get("HW_STEP_MARKER"):
            return
        path = hw_step_marker_path()
        parent = os.path.dirname(path) or "."
        if not os.path.isdir(parent):
            return
        payload = {
            "script": "phase4_train_queue",
            "step": f"{step}_{year}",
            "run_tag": str(tag or ""),
            "pid": os.getpid(),
            "started_utc": _dt.datetime.now(
                _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "phase": str(phase),
        }
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except Exception:                       # noqa: BLE001 — must never break the queue
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def clear_phase_marker():
    """Remove the marker ONLY if it is still OURS. Absence reads as "no step open".

    The ownership check is the whole point. Between our publish and this call the
    engine's StepLogger will normally have OVERWRITTEN the file with its own marker
    (same path, one home per VM) — deleting that would blank every sample of a
    running engine step and hand it back to "(between)", which is the bucket this
    whole mechanism exists to empty.

    An unreadable marker is likewise left alone: it may be the engine's, mid-write.
    Only a marker that names our pid is ours to delete.
    """
    try:
        if os.name != "posix" and not os.environ.get("HW_STEP_MARKER"):
            return                          # we never wrote one; nothing is ours
        path = hw_step_marker_path()
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("pid") != os.getpid():
            return                          # the engine's, or a stale foreign one
        os.remove(path)
    except Exception:                       # noqa: BLE001 — already gone is fine
        pass


def _read_status_file(f, attempts=3, backoff_s=2):
    """One status file's rows → (rows, problem). `problem` is None when clean.

    Retried, because these live on the FUSE mount where a transient EIO is
    documented, and header-checked, because csv.DictReader does NOT raise on a
    torn or truncated file — it happily yields rows with missing keys. A file
    whose header lacks the columns the resume ledger keys on cannot be
    interpreted, and saying so is the only honest answer.
    """
    q = _q()
    last = None
    for i in range(attempts):
        try:
            with io.open(f, encoding="utf-8", newline="") as fh:
                rd = csv.DictReader(fh)
                names = rd.fieldnames or []
                missing = [c for c in _STATUS_KEY_COLS if c not in names]
                if missing:
                    return [], f"header lacks {missing} — rows cannot be interpreted"
                return list(rd), None
        except Exception as e:                                  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(backoff_s * (i + 1))
    return [], f"{type(last).__name__}: {last}"

def _merged_rows():
    """Union of all status files' rows, sorted by ts (UTC, lexically sortable).

    D10 (2026-08-29): this used to `print` a warning and drop an unreadable file's
    rows on the floor. Dropping rows is not a neutral loss of information — it
    REWRITES HISTORY IN THE UNSAFE DIRECTION. Rows are merged latest-wins, so if
    file A holds a step's `OK` and file B holds the LATER `FAIL` that revoked it,
    losing B leaves the OK standing and the next launch skips a step that failed.
    The queue then builds on an artifact that was never produced.

    So the drops are now COUNTED and published in _MERGE_DEFECTS, and
    _completed_steps refuses to grant resume credit from an incomplete ledger.
    """
    q = _q()
    rows = []
    _MERGE_DEFECTS.clear()
    for f in _status_files():
        got, problem = _read_status_file(f)
        if problem:
            _MERGE_DEFECTS.append((f.name, problem))
            print(f"  ! WARN unreadable status file {f.name}: {problem}")
        rows.extend(got)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows

def _job_key(job_id, year, tag, step):
    """The identity a resume decision must key on: (job, year, tag, step).

    Delegates to names.py::job_key, which carries the D8 record of why the old
    (job_id, step) key was wrong and which two READERS still had it. Kept as a
    module-level name because tests and call sites reference it.
    """
    q = _q()
    return job_key(job_id, year, tag, step)

def _completed_steps():
    """→ (done, reverify, verdicts): steps already recorded OK across ALL status
    files, the subset whose last verification COULD NOT CHECK them, and the newest
    recorded VERIFY verdict text per key (D9 re-checks against it).

    The engine's labels/tile steps are idempotent and train/evaluate/inference
    write tagged outputs, so skipping a previously-OK step is safe and turns a
    dead runtime into a cheap restart instead of starting from zero.

    `reverify` is D7 (2026-08-29). An UNCHECKED/UNVERIFIED verdict used to call
    `bad.discard(...)` — it actively CLEARED the step's failure marker, so "the
    checker crashed" left a stronger resume credit than "the checker never ran".
    Such a step now keeps its OK credit (re-running it is GPU spend, and a
    checker that threw is no evidence the artifact is bad) but is re-VERIFIED on
    the next launch instead of skipped in silence. Only hard states force a re-run.
    """
    q = _q()
    done, bad, reverify, verdicts = set(), set(), set(), {}
    for r in _merged_rows():                       # sorted by ts: later rows win
        job, step, state = r.get("job"), str(r.get("step", "")), r.get("state")
        year, tag = r.get("year"), r.get("tag")
        key = _job_key(job, year, tag, step)
        if step in ("VERIFY",) or step.startswith("VERIFY:"):
            # keep the newest verdict TEXT, not just the pass/fail — D9 re-checks a
            # skipped job's raster against the size the verdict actually measured
            verdicts[key] = (state, r.get("detail", ""), r.get("ts", ""))
        if step in q.STEPS:
            if state == "OK":
                done.add(key)
                bad.discard(key)                   # a fresh OK supersedes an old fail
            elif state in ("FAIL", "ERROR", "TIMEOUT", "INTERRUPTED", "RUNNING"):
                # a LATER attempt that failed, or started and never reported (the
                # runtime died; a mid-copy kill can leave a partial artifact),
                # revokes an earlier OK — re-running an idempotent step is cheap.
                bad.add(key)
        elif step.startswith("VERIFY:") and step[7:] in q.STEPS:
            # A step can exit 0 without its artifact (e.g. step_tile's "no tiles"
            # early return) — its OK row must not license a skip if VERIFY:{step}
            # then hard-failed. Pre-P4.3 history has no VERIFY:{step} rows and is
            # unaffected. (Audit finding 2026-08-22.)
            k = _job_key(job, year, tag, step[7:])
            if state in q._VERIFY_HARD_FAIL:
                bad.add(k)
                reverify.discard(k)
            elif state in q._VERIFY_UNVERIFIED:
                reverify.add(k)                    # keep the credit, re-check it
            else:
                bad.discard(k)
                reverify.discard(k)
        elif step == "VERIFY":
            if state == "OK":
                # record the job-level verdict so a relaunch can SKIP re-reading
                # the raster (the b44a6a8 skip guard keys on (job, "VERIFY") —
                # without this branch that pair never entered `done` and the
                # guard was dead code; found when gpu4 re-verified and hung,
                # 2026-08-27).
                done.add(key)
                bad.discard(key)
            elif state in q._VERIFY_HARD_FAIL:
                # job-end raster check failed
                bad.add(_job_key(job, year, tag, "inference"))
                bad.add(key)
    if _MERGE_DEFECTS:
        # An incomplete ledger cannot justify a skip (D10). The rows we could not
        # read may be exactly the FAIL that revoked an OK we did read, and the
        # merge is latest-wins, so proceeding would skip a step that failed.
        # Resume is an optimisation; not re-running work that never happened is
        # not. This costs re-running steps in a rare case, which is the safe
        # direction — and it is repairable: fix or delete the named file.
        print("\n  ! RESUME DISABLED — the status history is INCOMPLETE:")
        for name, why in _MERGE_DEFECTS:
            print(f"      {name}: {why}")
        print("    Rows that could not be read may include the failure that "
              "revoked an earlier OK, so no step can be trusted as done.")
        print("    Repair or delete the file(s) above to restore resume.")
        return set(), set(), verdicts
    return done - bad, reverify - bad, verdicts

def _replace_absent(tmp, dest):
    """os.replace `tmp` onto `dest` with the destination guaranteed ABSENT (D4).

    A near-twin of phase4seg/common.py's `_publish_replace`, and it stays a separate
    copy on purpose: this module is an ORCHESTRATOR that must keep running when the
    engine's environment is broken, so it imports no engine module and no third
    party at import time. Importing common.py here would pull geopandas, rasterio,
    shapely, fiona and sklearn into the process whose whole job is to survive them.
    NO LONGER BYTE-IDENTICAL as of the aside-rename fix below; common.py still
    carries the old FileNotFoundError-only guard.

    Same reasoning as there: the mount canary only ever proved the
    absent-destination case of os.replace, and the aside suffix goes AFTER the
    extension so extension-anchored readers cannot see it.

    THE ASIDE RENAME'S ERROR IS NOT ALWAYS FileNotFoundError. It was guarded against
    that alone, which reads "dest vanished under us, so there is no aside" — true for
    ENOENT and false for everything else. On this rclone FUSE mount a transient EIO
    is documented (_check_prob_raster retries for it), and an EIO can be raised AFTER
    the rename has already landed: dest is then gone, `aside` is set to None by the
    old code as if nothing had moved, and the publish proceeds with the previous
    table stranded under a `.prev.<hex>` name that nothing ever unlinks and no reader
    globs. That is the mechanism behind the three orphaned `.prev.*` files found on
    the lake 2026-09-07 (e499355's closing note), and if the publish then failed too,
    the restore never ran and the destination stayed EMPTY.

    So: catch OSError, then RE-PROBE the filesystem rather than trust the exception's
    type. dest still there means the rename did not land — re-raise without
    publishing, because publishing over an existing destination is the unproven
    os.replace case this function exists to avoid; _status_write's caller prints a
    WARN, drops its temp, and the next step's flush retries against an intact table.
    dest gone AND the aside present means the rename DID complete: the aside is
    authoritative, and the publish (with its restore-on-failure path) must proceed.
    dest gone and no aside is the original ENOENT reading.
    """
    q = _q()
    aside = None
    if dest.exists():
        aside = dest.with_name(dest.name + f".prev.{secrets.token_hex(3)}")
        try:
            os.replace(dest, aside)
        except OSError:
            if dest.exists():
                # the rename did not happen; the previous table is still published.
                # If a copy of it landed anyway, dest is the authoritative name and
                # the aside would be exactly the orphan this branch exists to avoid.
                try:
                    aside.unlink()
                except OSError:
                    pass
                raise
            if not aside.exists():
                aside = None               # dest vanished under us — nothing to keep
            # else: the rename completed and THEN failed. Fall through: `aside` holds
            # the only copy of the previous table, and the publish below restores it
            # if it cannot land the new one.
    try:
        os.replace(tmp, dest)
    except OSError:
        if aside is not None:
            try:
                os.replace(aside, dest)
            except OSError:
                print(f"  ! could not restore the previous {dest.name}; it is at "
                      f"{aside.name}")
        raise
    if aside is not None:
        try:
            aside.unlink()
        except OSError:
            pass

def _status_write(rows):
    """Flush THIS LAUNCH's rows to its own status file. Called after EVERY step.

    Rewriting only our per-launch file means concurrent queues can never erase
    each other's records (P11.1); readers merge across files. That sentence was
    FALSE for six days and is worth keeping as the caution it earned: the flush
    writes only THIS launch's `rows`, so the moment `out` resolves to the shared
    STATUS instead of a per-launch file — which is exactly what the `__main__`
    defect in ::_q did from 2026-09-01 — every flush replaces the whole ledger
    with one launch's rows. Not a race: unconditional, and every other launch's
    history is gone. `out` being per-launch is what makes the claim true.

    D10 (2026-08-29): the flush was `open(out, "w")` straight onto the Drive
    mount — the file was TRUNCATED first and refilled afterwards, so every step
    boundary opened a window in which this launch's entire history was a
    zero-length file on the lake. Anything reading in that window (the resume
    ledger, watch_queue, runtime_health, cost_report) sees a queue that has done
    nothing. Write to a temp beside it, then publish with an absent-destination
    replace, so the canonical name only ever holds a complete table.
    """
    q = _q()
    tmp = None
    try:
        q.QC_DIR.mkdir(parents=True, exist_ok=True)
        out = q.STATUS_OUT if q.STATUS_OUT is not None else q.STATUS
        cols = ["job", "year", "tag", "step", "state", "exit", "minutes",
                "detail", "ts", "host", "session"]
        tmp = out.with_name(out.name + f".part.{os.getpid()}{secrets.token_hex(3)}")
        with io.open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})
        _replace_absent(tmp, out)
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! WARN could not write status: {e}")
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass

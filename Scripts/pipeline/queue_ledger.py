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
"""
import csv
import io
import os
import secrets
import socket
import time
from pathlib import Path

from phase4seg.names import job_key, status_files


def _q():
    """The queue module as runtime context — lazy to avoid the import cycle."""
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

    A deliberate 15-line twin of phase4seg/common.py's `_publish_replace`, and it
    stays a twin: this module is an ORCHESTRATOR that must keep running when the
    engine's environment is broken, so it imports no engine module and no third
    party at import time. Importing common.py here would pull geopandas, rasterio,
    shapely, fiona and sklearn into the process whose whole job is to survive them.

    Same reasoning as there: the mount canary only ever proved the
    absent-destination case of os.replace, and the aside suffix goes AFTER the
    extension so extension-anchored readers cannot see it.
    """
    q = _q()
    aside = None
    if dest.exists():
        aside = dest.with_name(dest.name + f".prev.{secrets.token_hex(3)}")
        try:
            os.replace(dest, aside)
        except FileNotFoundError:
            aside = None
    try:
        os.replace(tmp, dest)
    except OSError:
        if aside is not None:
            try:
                os.replace(aside, dest)
            except OSError:
                pass
        raise
    if aside is not None:
        try:
            aside.unlink()
        except OSError:
            pass

def _status_write(rows):
    """Flush THIS LAUNCH's rows to its own status file. Called after EVERY step.

    Rewriting only our per-launch file means concurrent queues can never erase
    each other's records (P11.1); readers merge across files.

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

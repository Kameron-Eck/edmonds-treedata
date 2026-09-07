#!/usr/bin/env python3
r"""rebuild_queue_ledger.py — rebuild the 2026-09-01..09-07 queue ledger from the
surviving primary evidence, INTO THE REPO. Physically cannot write to the lake.

WHY THIS EXISTS. Commit e499355 explains the defect: from the queue/ledger split
(4c546a7, 2026-09-01) until 2026-09-07, `queue_ledger.py::_q` resolved a SECOND
import of the queue module instead of the running `__main__`, so `STATUS_OUT` was
None on the copy and `queue_ledger.py::_status_write` fell through to the shared
`train_queue_status.csv`. A flush rewrites the whole file from THIS launch's
in-memory rows, so every launch replaced six days of ledger with its own rows.
What survived are 25 orphaned `.part.*`/`.prev.*` temps (copied into
`phase4/qc/ledger_recovery/`), the queue's nohup logs, and the engine's step logs.

WHAT IT PRODUCES. One candidate ledger CSV with the ledger's exact 11 columns, so
that IF a human copies it to the lake every reader merges it unchanged
(`phase4seg/names.py::status_files` admits the filename), plus a sidecar report.
It is a CANDIDATE: this instrument never touches `G:\My Drive\treedata`.

THE TWO SOURCES, AND WHAT EACH ONE CAN HONESTLY SAY
---------------------------------------------------
* SNAPSHOTS (`train_queue_status.csv.part.*` / `.prev.*`) are queue-written rows.
  They are copied through byte-for-byte — no prefix, no rewrite. Where the same
  (job, year, tag, step) appears with different states or timestamps, ALL rows are
  kept: the ledger is append-style and readers take the latest ts. Dropping the
  older row would be the D10 mistake in reverse.

* LOGS. A nohup log prints, at exactly two leading spaces, the launch header, each
  `$ … --year Y --step S --run-tag T` command, the queue's own outcome line
  `[job/step] exit=N  elapsed M min`, and every VERIFY verdict. The engine's stdout
  is indented `    | `, which is what keeps a line like
  "VERIFY:train/inference is what proves it landed" out of the parse.
  A row is SYNTHESISED from those lines only when no snapshot row covers
  (year, tag, step), and its `detail` is prefixed RECOVERED-FROM-LOGS: so no reader
  can mistake it for a queue-written row.

TWO PLACES WHERE THE EVIDENCE CONTRADICTS THE OBVIOUS RECONSTRUCTION
--------------------------------------------------------------------
1. `ts` IS THE STEP START IN A QUEUE-WRITTEN ROW, NOT THE END.
   `phase4_train_queue.py::run_step` builds one `rec` with `ts=now()` before
   launching the child and then MUTATES that same dict on completion without
   touching `ts`. Measured: snapshot row `hy_e3_2011s/labels OK 5.4 min` carries
   ts 2026-09-01 21:21:39, and the step log for that run starts at 21:26:59 —
   5.4 minutes later, the queue-side start plus the pip bootstrap.
   Recovered rows carry the engine's `completed:` instead (the nohup log has no
   timestamps of its own), so a recovered ts sits up to `minutes` LATER than the
   queue would have written. Harmless here — synthesis happens only for keys with
   no queue-written row, so latest-wins never compares the two for one key — but
   it is a real semantic difference and is stated in the report and in `detail`.

2. `minutes` IS NOT THE STEP LOG'S `elapsed`.
   That field is a formatted string whose UNIT varies with magnitude —
   `pipeline_log.py::StepLogger._write` emits `0.0s`, `1.1min` or `1.10h` — and it
   spans the ENGINE's own `started:`→`completed:`, while the queue's clock also
   covers spawning the child, its pip bootstrap and its imports. Measured on the
   window: labels/2011s reads `0.0s` against the queue's 5.4 min (the step is
   skipped by design under --force-citywide, so the engine timed nothing), and
   postproc/2017 reads `1.10h` against the queue's 66.6 min. `cost_report` sums
   the queue's column, so the step log's elapsed is NEVER written here — the only
   source is the queue's own number on the nohup outcome line. A TIMEOUT prints no
   minutes, so a recovered TIMEOUT row leaves `minutes` blank rather than guessing.

JOIN KEY: THE STEP-LOG PATH THE ENGINE PRINTS. Each command block ends with
`    |   ✓ log → …/phase4_semantic_finetune_<step>_<year>_<ts>.log`, which names
the exact file — exact, and unlike `run_id` it survives the block where the run
manifest failed to write (measured: 2017/postproc, 2026-09-05, Errno 5). Measured
on the window: 173 of 173 blocks that reported an outcome name a step log, all 173
exist and all carry `started:`/`completed:`.

WHAT IS DELIBERATELY NOT SYNTHESISED
  · a `$` block with no outcome line — the VM died mid-step; the queue never
    recorded a terminal state and neither will this.
  · `- skip job/step (already OK)` — a resume skip writes no row.
  · a VERIFY line with no step block to anchor its timestamp (a fully-skipped
    job's `_recheck_skipped_verify` row, or a D7 re-verify).
  · GUARD:runtag rows — not step outcomes, and the nohup log carries no timestamp
    for them. The snapshots already hold 19.
  · any verdict the log did not print. VERIFY states and their verdict text are
    quoted verbatim from the log or the row is refused.

CONSEQUENCE OF THE PREFIX, RECORDED HONESTLY: `queue_verify.py::_mb_from_verdict`
anchors `(\d+)MB` at the START of a VERIFY detail, so a prefixed detail parses as
"no size recorded" and a later fully-skipped-job re-check degrades from
OK_CACHED/SIZE_CHANGED to UNVERIFIED ("existence only"). That is the safe
direction — the step keeps its resume credit and is re-verified — and it can never
produce a false OK.

Usage
    py -3.12 qc/instruments/rebuild_queue_ledger.py            # defaults, repo-only
    py -3.12 qc/instruments/rebuild_queue_ledger.py --logs-dir <dir> --out <path>
"""
import argparse
import csv
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import lake
from phase4seg.names import VERIFY_HARD_FAIL, clean_argv, is_status_file

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
REC_DIR = REPO / "phase4" / "qc" / "ledger_recovery"

# The ledger's columns, in the order queue_ledger.py::_status_write writes them.
# Eleven, exactly: a twelfth "provenance" column would make every reader's
# DictReader see a schema it does not know, so provenance lives in `detail` and
# in the sidecar report instead.
COLS = ["job", "year", "tag", "step", "state", "exit", "minutes",
        "detail", "ts", "host", "session"]

# Contains no `\d+MB`-shaped token, so it cannot be mistaken for a size by
# queue_verify.py::_mb_from_verdict (which would then read a wrong number rather
# than none — the one failure mode worse than losing the parse).
PREFIX = "RECOVERED-FROM-LOGS: "

SHARED_MARK = "SHARED_AS_OF"
SNAPSHOT_GLOB = "train_queue_status.csv.*"

DEFAULT_SINCE = "20260901"
DEFAULT_UNTIL = "20260907"
DEFAULT_OUT = REC_DIR / "train_queue_status_recovered_20260901_20260907.csv"
DEFAULT_REPORT = REC_DIR / "recovery_report.md"

# ── queue-level lines. The two-space anchor is load-bearing: engine stdout is
# re-printed at `    | ` and contains the substring "VERIFY:" in prose.
RX_JOB = re.compile(r"^ {2}JOB (?P<job>\S+) {2}\(year (?P<year>\S+), tag (?P<tag>\S+)\)$")
RX_CMD = re.compile(r"^ {2}\$ (?P<cmd>.*)$")
RX_OUT = re.compile(r"^ {2}\[(?P<job>.+)/(?P<step>[a-z]+)\] exit=(?P<rc>\S+) {2}"
                    r"elapsed (?P<min>[\d.]+) min\s*$")
RX_TIMEOUT = re.compile(r"^ {2}! TIMEOUT: (?P<job>.+)/(?P<step>\S+) exceeded "
                        r"(?P<budget>\d+) min")
RX_INTERRUPT = re.compile(r"^ {2}! (?P<job>\S+)/(?P<step>\S+) got a stray interrupt "
                          r"after (?P<min>[\d.]+) min")
RX_SKIP = re.compile(r"^ {2}- skip (?P<job>.+)/(?P<step>\S+) \(already OK\)\s*$")
RX_REVERIFY = re.compile(r"^ {2}- (?P<job>\S+)/(?P<step>\S+) was left UNVERIFIED")
RX_VERIFY = re.compile(r"^ {2}VERIFY(?::(?P<vstep>\S+))? (?P<job>\S+): (?P<rest>.*)$")
RX_QUEUE = re.compile(r"^ {2}queue {2}: (?P<queue>\S+)\s*$")
# ── engine echo, inside a block
RX_ENGINE_LOG = re.compile(r"^ {4}\|\s+\u2713 log \u2192 (?P<path>\S+)\s*$")
RX_ENGINE_RUNID = re.compile(r"^ {4}\|\s+run_id: (?P<run_id>\S+)")

RX_NOHUP_NAME = re.compile(r"^train_queue_nohup_(?P<stem>.+)_"
                           r"(?P<ts>\d{8}T\d{6}Z)\.log$")
RX_STATE_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]*$")

# verify_step's "could not check" print interpolates the state, then this banner,
# then two spaces, then the verdict text (queue_verify.py::verify_step).
UNPROVEN = " \u2014 COULD NOT CHECK THIS ARTIFACT, continuing UNPROVEN."


# ─────────────────────────────────────────────────────────────────────────────
# the write guard
# ─────────────────────────────────────────────────────────────────────────────

def lake_roots():
    """Every path that is the data lake, on either plane. Deduplicated, ordered.

    `lake.BASE` is whichever of the two the strict probe resolved on this host, and
    both literals are listed as well so the guard holds when the instrument runs on
    the plane that is NOT currently mounted.
    """
    seen, out = set(), []
    for r in (lake.BASE, lake.COLAB_BASE, lake.LOCAL_BASE):
        p = Path(r)
        if str(p) not in seen:
            seen.add(str(p))
            out.append(p)
    return tuple(out)


def assert_not_lake(path, roots=None):
    """→ the resolved path, or SystemExit if it is inside the data lake.

    This instrument reads the lake and must be incapable of writing to it. The
    check runs on the RESOLVED path so `…/qc/../../../My Drive/treedata/x` cannot
    slip past, and against both the resolved and the literal form of each root so a
    root that does not exist on this host (the Colab path, from Windows) still
    blocks. Roots are a parameter so a test can point it at a fake BASE.
    """
    p = Path(path).expanduser()
    p = (p if p.is_absolute() else Path.cwd() / p).resolve()
    for root in (lake_roots() if roots is None else roots):
        forms = {Path(root)}
        try:
            forms.add(Path(root).resolve())
        except OSError:                                         # pragma: no cover
            pass
        for r in forms:
            if p == r or p.is_relative_to(r):
                raise SystemExit(
                    f"REFUSING TO WRITE INSIDE THE DATA LAKE: {p}\n"
                    f"  (it is under {r})\n"
                    "  rebuild_queue_ledger.py produces a CANDIDATE ledger in the "
                    "REPO. Restoring it to the lake changes the resume ledger and "
                    "the audit trail for every reader, and is a human's call.")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# source 1 — the snapshots
# ─────────────────────────────────────────────────────────────────────────────

def snapshot_files(rec_dir, include_shared=False):
    """The orphan snapshots in `rec_dir`, sorted. README and the recovered output
    are excluded by the glob shape; the shared copy is excluded by name unless
    asked for, because it is the CLOBBERED file, not an orphan of a launch."""
    files = sorted(Path(rec_dir).glob(SNAPSHOT_GLOB))
    if not include_shared:
        files = [f for f in files if SHARED_MARK not in f.name]
    return files


def load_snapshots(rec_dir, include_shared=False):
    """→ (rows, per_file). Rows carry a private `_src` (dropped before writing).

    Values are passed through untouched. A snapshot is a queue-written table and
    editing one — even to add provenance — would make it something else.
    """
    rows, per_file = [], {}
    for f in snapshot_files(rec_dir, include_shared):
        with io.open(f, encoding="utf-8", newline="") as fh:
            got = list(csv.DictReader(fh))
        per_file[f.name] = len(got)
        for r in got:
            rec = {c: (r.get(c) or "") for c in COLS}
            rec["_src"] = f.name
            rows.append(rec)
    return rows, per_file


# ─────────────────────────────────────────────────────────────────────────────
# source 2 — the logs
# ─────────────────────────────────────────────────────────────────────────────

def nohup_logs(logs_dir, since=DEFAULT_SINCE, until=DEFAULT_UNTIL):
    """→ [(path, queue_stem, launch_ts)] for launches inside the window, sorted.

    The window is read off the FILENAME's launch stamp, which the launcher writes
    and nothing later edits. `train_queue_nohup.log` — the unstamped pre-P11 name —
    carries no launch stamp and is therefore never in any window.
    """
    out = []
    for p in sorted(Path(logs_dir).glob("train_queue_nohup_*.log")):
        m = RX_NOHUP_NAME.match(p.name)
        if not m:
            continue
        day = m.group("ts")[:8]
        if since <= day <= until:
            out.append((p, m.group("stem"), m.group("ts")))
    return out


def read_step_log(path):
    """→ {"started", "completed", "run_id"} from an engine step log's header.

    The header is written by pipeline_log.py::StepLogger._write at the END of the
    step, so a step log existing at all is evidence the step reached its own
    completion hook. Only the header is read — the loop stops at the `--- stdout
    ---` divider, because the captured stdout below it is the engine talking, not
    an outcome the queue printed.
    """
    got = {"started": "", "completed": "", "run_id": ""}
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("--- stdout ---"):
                break
            if line.startswith("started:"):
                got["started"] = line.split(None, 1)[1].strip()
            elif line.startswith("completed:"):
                got["completed"] = line.split(None, 1)[1].strip()
            elif line.startswith("run id"):
                parts = line.split(None, 2)
                got["run_id"] = parts[2].strip() if len(parts) > 2 else ""
    return got


def _queue_ts(iso):
    """`2026-09-07T21:58:43.137755` → `2026-09-07 21:58:43`, the ledger's format.

    A format change, not a value change: the engine and the queue stamp the same
    clock (UTC on a Colab VM). Sub-second precision is dropped because the ledger
    has never carried it and a reader sorting lexically must see the same shape.
    """
    s = str(iso or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", s)
    return f"{m.group(1)} {m.group(2)}" if m else ""


def _split_verdict(rest):
    """A VERIFY print's tail → (state, verdict_text). ("", "") when unparseable.

    Two shapes, both from queue_verify.py::verify_step / phase4_train_queue.py::
    verify: `{state}  {detail}` and, for the D7 states, `{state} — COULD NOT CHECK
    THIS ARTIFACT, continuing UNPROVEN.  {detail}`. The state must be a bare
    upper-case token or this refuses to guess.
    """
    if UNPROVEN in rest:
        state, _, detail = rest.partition(UNPROVEN)
    else:
        state, _, detail = rest.partition("  ")
    state = state.strip()
    if not RX_STATE_TOKEN.match(state):
        return "", ""
    return state, detail.strip()


def parse_nohup(path):
    """One nohup log → (events, notes). Pure text; opens nothing else.

    An event is a dict with `kind` in {step, verify} plus everything the log said
    about it. `notes` collects the things this file shows that CANNOT become rows —
    they are the report's refusal list, and they are as much a finding as the rows.
    """
    events, notes = [], []
    name = Path(path).name
    job = {"job": "", "year": "", "tag": ""}
    block = None
    queue = ""
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\r\n")

            m = RX_QUEUE.match(line)
            if m:
                queue = m.group("queue")
                continue

            m = RX_JOB.match(line)
            if m:
                if block is not None and block["outcome"] is None:
                    notes.append(dict(kind="block_without_outcome", src=name,
                                      line=block["line"], detail=block["cmdline"]))
                job = m.groupdict()
                block = None
                continue

            m = RX_CMD.match(line)
            if m:
                if block is not None and block["outcome"] is None:
                    notes.append(dict(kind="block_without_outcome", src=name,
                                      line=block["line"], detail=block["cmdline"]))
                cmd = m.group("cmd")
                block = dict(line=lineno, cmdline=cmd, outcome=None,
                             step_logs=[], run_id="",
                             year=_flag(cmd, "--year"), step=_flag(cmd, "--step"),
                             tag=_flag(cmd, "--run-tag"))
                continue

            if block is not None:
                m = RX_ENGINE_LOG.match(line)
                if m:
                    block["step_logs"].append(Path(m.group("path")).name)
                    continue
                m = RX_ENGINE_RUNID.match(line)
                if m and not block["run_id"]:
                    block["run_id"] = m.group("run_id")
                    continue

            m = RX_SKIP.match(line)
            if m:
                notes.append(dict(kind="resume_skip", src=name, line=lineno,
                                  detail=f"{m.group('job')}/{m.group('step')}"))
                continue

            m = RX_REVERIFY.match(line)
            if m:
                notes.append(dict(kind="reverify_of_skipped_step", src=name,
                                  line=lineno,
                                  detail=f"{m.group('job')}/{m.group('step')}"))
                continue

            m = RX_OUT.match(line)
            if m:
                if block is None:
                    notes.append(dict(kind="outcome_without_block", src=name,
                                      line=lineno, detail=line.strip()))
                    continue
                block["outcome"] = "exit"
                events.append(dict(
                    kind="step", src=name, queue=queue, line=lineno,
                    job=m.group("job"), year=block["year"], tag=block["tag"],
                    step=m.group("step"),
                    state="OK" if m.group("rc") == "0" else "FAIL",
                    exit=m.group("rc"), minutes=m.group("min"),
                    quoted=line.strip(), block=block, job_hdr=dict(job)))
                continue

            m = RX_TIMEOUT.match(line)
            if m:
                if block is None:
                    notes.append(dict(kind="outcome_without_block", src=name,
                                      line=lineno, detail=line.strip()))
                    continue
                block["outcome"] = "timeout"
                events.append(dict(
                    kind="step", src=name, queue=queue, line=lineno,
                    job=m.group("job"), year=block["year"], tag=block["tag"],
                    step=m.group("step"), state="TIMEOUT", exit="killed",
                    minutes="", quoted=line.strip(), block=block,
                    job_hdr=dict(job)))
                continue

            m = RX_INTERRUPT.match(line)
            if m:
                if block is None:
                    notes.append(dict(kind="outcome_without_block", src=name,
                                      line=lineno, detail=line.strip()))
                    continue
                block["outcome"] = "interrupt"
                events.append(dict(
                    kind="step", src=name, queue=queue, line=lineno,
                    job=m.group("job"), year=block["year"], tag=block["tag"],
                    step=m.group("step"), state="INTERRUPTED", exit="sigint",
                    minutes=m.group("min"), quoted=line.strip(), block=block,
                    job_hdr=dict(job)))
                continue

            m = RX_VERIFY.match(line)
            if m:
                state, verdict = _split_verdict(m.group("rest"))
                step = "VERIFY" + (f":{m.group('vstep')}" if m.group("vstep") else "")
                if not state:
                    notes.append(dict(kind="verify_unparseable", src=name,
                                      line=lineno, detail=line.strip()))
                    continue
                events.append(dict(
                    kind="verify", src=name, queue=queue, line=lineno,
                    job=m.group("job"), year=job.get("year", ""),
                    tag=job.get("tag", ""), step=step, state=state,
                    exit="", minutes="", verdict=verdict, quoted=line.strip(),
                    block=block, job_hdr=dict(job)))
                continue

    if block is not None and block["outcome"] is None:
        notes.append(dict(kind="block_without_outcome", src=name,
                          line=block["line"], detail=block["cmdline"]))
    return events, notes


def _flag(cmdline, flag):
    m = re.search(rf"{re.escape(flag)}[= ](\S+)", cmdline)
    return m.group(1) if m else ""


# ─────────────────────────────────────────────────────────────────────────────
# synthesis
# ─────────────────────────────────────────────────────────────────────────────

def _anchor_ts(event, logs_dir, cache):
    """→ (ts, steplog_name, why_not). The engine `completed:` for this event's block.

    A VERIFY event anchors on the block it follows — verify_step runs immediately
    after the step it checks — and only when that block ran the SAME step, so a
    re-verify of a skipped step (which has no block of its own) cannot borrow
    another step's clock. No anchor means no timestamp, and no timestamp means the
    row is refused rather than written with a blank the readers would sort first.
    """
    block = event.get("block")
    if not block or block.get("outcome") is None:
        return "", "", "no command block reported an outcome before this line"
    if event["kind"] == "verify" and event["step"].startswith("VERIFY:"):
        if event["step"][len("VERIFY:"):] != block.get("step"):
            return "", "", (f"the preceding block ran step {block.get('step')!r}, "
                            f"not {event['step'][len('VERIFY:'):]!r}")
    names = sorted(set(block.get("step_logs") or []))
    if not names:
        return "", "", "the block printed no step-log path"
    if len(names) > 1:
        return "", "", f"the block named {len(names)} step logs: {', '.join(names)}"
    name = names[0]
    if name not in cache:
        p = Path(logs_dir) / name
        cache[name] = read_step_log(p) if p.exists() else None
    got = cache[name]
    if got is None:
        return "", name, f"step log {name} is not on the lake"
    ts = _queue_ts(got.get("completed"))
    if not ts:
        return "", name, f"step log {name} has no parseable `completed:`"
    return ts, name, ""


def synthesise(events, logs_dir, covered, cache=None):
    """→ (rows, refusals, suppressed). One row per log event that is not covered.

    `covered` is the set of (year, tag, step) the snapshots already hold. That key
    is deliberately COARSER than the ledger's own (job, year, tag, step): if a
    queue-written row exists for the same work under any job nickname, the log adds
    nothing a reader should weigh, and a synthesised row could only compete with it
    on latest-wins. Refusing is the safe direction.
    """
    cache = {} if cache is None else cache
    rows, refusals, suppressed = [], [], []
    for ev in events:
        key = (ev["year"], ev["tag"], ev["step"])
        if not ev["year"] or not ev["tag"]:
            refusals.append(dict(ev_key=key, src=ev["src"], line=ev["line"],
                                 quoted=ev["quoted"],
                                 why="the log does not name this event's year/tag"))
            continue
        if key in covered:
            suppressed.append(dict(ev_key=key, src=ev["src"], line=ev["line"],
                                   state=ev["state"], kind=ev["kind"]))
            continue
        ts, steplog, why = _anchor_ts(ev, logs_dir, cache)
        if not ts:
            refusals.append(dict(ev_key=key, src=ev["src"], line=ev["line"],
                                 quoted=ev["quoted"], why=why))
            continue
        if ev["kind"] == "verify":
            detail = (f'{PREFIX}{ev["src"]} verdict verbatim: "{ev["verdict"]}"; '
                      f"ts=engine-completed@{steplog}")
        else:
            detail = (f'{PREFIX}{ev["src"]} outcome verbatim: "{ev["quoted"]}"; '
                      f"ts=engine-completed@{steplog}")
        rows.append({"job": ev["job"], "year": ev["year"], "tag": ev["tag"],
                     "step": ev["step"], "state": ev["state"], "exit": ev["exit"],
                     "minutes": ev["minutes"], "detail": detail, "ts": ts,
                     "host": "", "session": "", "_src": ev["src"]})
    return rows, refusals, suppressed


def later_hard_outcomes(events, snapshot_rows, logs_dir, cache=None):
    """Covered keys whose LOG shows a hard state newer than any snapshot row.

    Not synthesised — the suppression rule stands — but it is the exact shape of
    the D10 hazard `queue_ledger.py::_merged_rows` was hardened against: a later
    FAIL that revokes an earlier OK. If one of these is real, the surviving ledger
    grants resume credit for a step that failed. Kam sees the list; nothing acts
    on it.
    """
    cache = {} if cache is None else cache
    newest = defaultdict(str)
    for r in snapshot_rows:
        k = (r["year"], r["tag"], r["step"])
        newest[k] = max(newest[k], r["ts"])
    hard = set(VERIFY_HARD_FAIL) | {"FAIL", "TIMEOUT", "ERROR", "INTERRUPTED"}
    out = []
    for ev in events:
        k = (ev["year"], ev["tag"], ev["step"])
        if k not in newest or ev["state"] not in hard:
            continue
        ts, steplog, _why = _anchor_ts(ev, logs_dir, cache)
        if ts and ts > newest[k]:
            out.append(dict(key=k, ts=ts, state=ev["state"], src=ev["src"],
                            line=ev["line"], quoted=ev["quoted"],
                            newest_snapshot_ts=newest[k], steplog=steplog,
                            superseded=_later_state_in_logs(
                                events, k, ts, logs_dir, cache)))
    return sorted(out, key=lambda d: (d["ts"], d["key"], d["line"]))


def _later_state_in_logs(events, key, after_ts, logs_dir, cache):
    """The newest state ANY log shows for `key` after `after_ts`, or "".

    Without this a hard state reads as the standing verdict, and it usually is not:
    the measured case (2017k/of_2017k VERIFY:tile MISSING) was followed twenty
    minutes later by a relaunch that re-tiled and verified OK. Both of those rows
    are suppressed — the key is snapshot-covered — so the log is the only place the
    recovery is visible at all.
    """
    best = ("", "")
    for ev in events:
        if (ev["year"], ev["tag"], ev["step"]) != key:
            continue
        ts, _sl, _why = _anchor_ts(ev, logs_dir, cache)
        if ts and ts > after_ts and ts > best[0]:
            best = (ts, ev["state"])
    return f"{best[1]} @ {best[0]}" if best[0] else ""


def stale_running_coverage(events, snapshot_rows, logs_dir, cache=None):
    """Keys whose newest SURVIVING snapshot row is non-terminal, while a log shows
    a terminal outcome that the suppression rule then withholds.

    Same mechanism as the twins above, without the twin: the orphan that survived
    was flushed mid-step, so the ledger's last word on that step is `RUNNING` —
    which `queue_ledger.py::_completed_steps` counts as a revocation, not as
    progress. The candidate therefore still says "re-run this", and the evidence
    that it finished sits only in the nohup log.
    """
    cache = {} if cache is None else cache
    # Ties break TOWARDS the terminal state, the same way _sort_key breaks them for
    # the reader. Without that, a key whose RUNNING and OK both survived at one
    # timestamp would be reported here as still mid-step — which the row order this
    # file writes has already settled the other way.
    newest = {}
    for r in snapshot_rows:
        k = (r["year"], r["tag"], r["step"])
        rank = (r["ts"], 0 if r["state"] in _NON_TERMINAL else 1)
        if k not in newest or rank >= newest[k][0]:
            newest[k] = (rank, r["state"])
    newest = {k: (rank[0], state) for k, (rank, state) in newest.items()}
    out = []
    for ev in events:
        k = (ev["year"], ev["tag"], ev["step"])
        got = newest.get(k)
        if not got or got[1] not in _NON_TERMINAL or ev["state"] in _NON_TERMINAL:
            continue
        ts, _sl, _why = _anchor_ts(ev, logs_dir, cache)
        if ts and ts >= got[0]:
            out.append(dict(key=k, snapshot_state=got[1], snapshot_ts=got[0],
                            log_state=ev["state"], log_ts=ts, src=ev["src"],
                            line=ev["line"]))
    return sorted(out, key=lambda d: (d["log_ts"], d["key"], d["line"]))


def join_integrity(events, notes, logs_dir):
    """→ how many command blocks could be dated, measured on THIS run's inputs.

    The whole synthesis rests on `✓ log → …` naming a step log that exists and
    carries a `completed:`. That is a property of the archive, not of this code, so
    it is re-measured every run and published rather than asserted once in a
    docstring.
    """
    steps = [e for e in events if e["kind"] == "step"]
    no_outcome = sum(1 for n in notes if n["kind"] == "block_without_outcome")
    named = [e for e in steps if len(set(e["block"]["step_logs"] or [])) == 1]
    found = [e for e in named
             if (Path(logs_dir) / sorted(set(e["block"]["step_logs"]))[0]).exists()]
    return dict(blocks=len(steps) + no_outcome, with_outcome=len(steps),
                naming_one_step_log=len(named), step_log_on_lake=len(found),
                blocks_without_outcome=no_outcome)


# ─────────────────────────────────────────────────────────────────────────────
# merge + write
# ─────────────────────────────────────────────────────────────────────────────

# The only state `run_step` writes BEFORE an outcome exists: it appends the row as
# RUNNING, flushes, then mutates that same dict in place. So a snapshot taken
# mid-step and a later one from the same launch hold the SAME row twice, with the
# same `ts`, in two different states — and both are real history.
_NON_TERMINAL = ("RUNNING",)


def _sort_key(row):
    """The row order the ledger's readers need, and it is not the plain 11-tuple.

    `queue_ledger.py::_merged_rows` sorts by `ts` ALONE and Python's sort is
    stable, so rows sharing a timestamp are consumed in FILE order, and
    `_completed_steps` gives the last one seen the final word. A step's RUNNING row
    and its terminal row carry the same `ts` (see _NON_TERMINAL), so sorting on the
    plain tuple would put `OK` before `RUNNING` — alphabetically — and the reader
    would consume RUNNING last, `bad.add` the key, and re-run a step that had
    finished. A per-launch file never had that problem: it holds ONE mutated row
    per step. So non-terminal states are ordered FIRST within an equal
    (ts, job, year, tag, step) group, which reproduces what the queue's own file
    would have shown the reader.
    """
    return (row["ts"], row["job"], row["year"], row["tag"], row["step"],
            0 if row["state"] in _NON_TERMINAL else 1,
            row["state"], row["exit"], row["minutes"], row["detail"],
            row["host"], row["session"])


def merge_rows(snapshot_rows, synth_rows):
    """→ (rows, provenance). Deduplicated on the FULL 11-tuple, ordered by _sort_key.

    Deduplication is on the whole row, so two snapshots holding the same flush of
    the same row collapse to one, while the same (job, year, tag, step) recorded
    twice with different states or timestamps stays TWO rows — that is the ledger's
    history, and `_completed_steps` needs both to apply latest-wins.

    The ordering is total (every column participates), so two runs on the same
    inputs are byte-identical.
    """
    prov = defaultdict(set)
    for r in snapshot_rows + synth_rows:
        prov[tuple(r[c] for c in COLS)].add(r.get("_src", ""))
    rows = sorted((dict(zip(COLS, k)) for k in prov), key=_sort_key)
    return rows, {k: sorted(v) for k, v in prov.items()}


def equal_ts_state_twins(rows):
    """Keys carrying two states at ONE timestamp — the mid-step-snapshot artefact.

    Reported because their outcome depends on row ORDER rather than on `ts`, which
    is the one place this candidate's merge semantics differ from a real per-launch
    file's. `_sort_key` decides them; this counts them so the decision is visible.
    """
    by = defaultdict(set)
    for r in rows:
        by[(r["job"], r["year"], r["tag"], r["step"], r["ts"])].add(r["state"])
    return sorted((k, sorted(v)) for k, v in by.items() if len(v) > 1)


def write_csv(rows, out, roots=None):
    """Write the candidate ledger. Guarded, and the NAME is checked too.

    `phase4seg/names.py::is_status_file` is the one discovery rule every reader
    uses; a candidate a reader would not merge is not a candidate, so a name that
    fails it is an error here rather than a surprise on the lake later.
    """
    out = assert_not_lake(out, roots)
    if not is_status_file(out.name):
        raise SystemExit(
            f"{out.name} does not satisfy phase4seg.names.is_status_file — no "
            "reader would merge it. Name it train_queue_status_<something>.csv.")
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    return out


# Why a parsed line became nothing. `resume_skip` and `reverify_of_skipped_step`
# are NOT here: they are normal queue behaviour that writes no row, and they are
# counted in the report's prose instead of listed as if something were missing.
_WHY_NOTE = {
    "block_without_outcome":
        "the queue never printed a terminal outcome for this step — the runtime "
        "died mid-step; no state to record",
    "outcome_without_block":
        "an outcome line with no preceding `$` command block — cannot resolve "
        "year/tag",
    "verify_unparseable":
        "a VERIFY line whose state is not a bare upper-case token — refusing to "
        "guess a verdict",
}


def _md_table(header, body_rows):
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for r in body_rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def build_report(ctx):
    """The sidecar. Deterministic: no wall clock anywhere in it."""
    o = []
    a = o.append
    a("# Queue-ledger recovery, 2026-09-01 .. 2026-09-07 — CANDIDATE")
    a("")
    a(f"Writer: `qc/instruments/rebuild_queue_ledger.py::main`  ·  "
      f"output `{ctx['out'].name}`")
    a("")
    a("**NOTHING WAS WRITTEN TO THE DATA LAKE.** Both output paths are checked "
      "against every lake root (`lake.BASE`, `lake.COLAB_BASE`, `lake.LOCAL_BASE`) "
      "by `rebuild_queue_ledger.py::assert_not_lake` before a byte is written; the "
      "lake is opened read-only, for the nohup and step logs. This CSV is a "
      "CANDIDATE and is **not part of any ledger** until a human copies it beside "
      "the others on the lake — at which point every reader "
      "(`phase4seg/names.py::status_files`) merges it.")
    a("")
    a("## What the rows are")
    a("")
    a(f"- **{ctx['n_snapshot']} snapshot-native rows** — copied byte-for-byte from "
      f"the orphaned `.part.*`/`.prev.*` temps. No prefix, no rewrite.")
    a(f"- **{ctx['n_synth']} rows synthesised from logs** — `detail` begins "
      f"`{PREFIX.strip()}` and quotes the line that is the evidence. Synthesis "
      f"happens only where NO snapshot row covers `(year, tag, step)`.")
    a(f"- **{ctx['n_rows']} rows total** after de-duplication on the full 11-tuple.")
    a("")
    a("## Two things a reader must know about the synthesised rows")
    a("")
    a("1. **`ts` means something slightly different.** A queue-written row carries "
      "the step's START (`phase4_train_queue.py::run_step` stamps `ts` before "
      "launching the child and mutates the same dict on completion). The nohup log "
      "has no timestamps, so a recovered row carries the engine step log's "
      "`completed:` — up to `minutes` LATER than the queue would have written. "
      "Because synthesis only fills keys with no queue-written row, no reader's "
      "latest-wins ever compares the two for one key.")
    a("2. **`minutes` is the queue's own number, never the step log's `elapsed`.** "
      "That field is a formatted string whose unit varies with magnitude "
      "(`pipeline_log.py::StepLogger._write` emits `0.0s`, `1.1min` or `1.10h`) "
      "and it spans the ENGINE's `started:`→`completed:`, while the queue's clock "
      "also covers spawning the child, its pip bootstrap and its imports. "
      "Measured: labels/2011s reads `0.0s` against the queue's `5.4`, and "
      "postproc/2017 reads `1.10h` against the queue's `66.6`. `cost_report` sums "
      "this column, so a `TIMEOUT` row — which prints no minutes — is left blank "
      "rather than filled from the step log.")
    a("")
    a("Consequence of the `detail` prefix, recorded rather than hidden: "
      "`queue_verify.py::_mb_from_verdict` anchors `(\\d+)MB` at the START of a "
      "VERIFY detail, so a prefixed detail reads as \"no size recorded\" and a "
      "later fully-skipped-job re-check degrades from `OK_CACHED`/`SIZE_CHANGED` "
      "to `UNVERIFIED` (existence only). That keeps the resume credit and forces a "
      "re-verify; it can never produce a false OK.")
    a("")
    a("## Rows per source")
    a("")
    a("### Snapshots")
    a("")
    a(_md_table(["snapshot file", "rows"],
                [[k, v] for k, v in sorted(ctx["per_snapshot"].items())]))
    a("")
    a(f"Raw snapshot rows read: **{ctx['n_snapshot_raw']}**; distinct on the full "
      f"11-tuple: **{ctx['n_snapshot']}**, of which **{ctx['n_shared_rows']}** "
      f"appear in more than one snapshot (a launch flushes its whole table after "
      f"every step, so its earlier rows are re-written into every later orphan). "
      + ("The shared `train_queue_status.csv` copy is EXCLUDED (it is the "
         "clobbered file, not a launch orphan); including it with "
         "`--include-shared` adds its single row, which is where the "
         "README's 252 and a naive 253 differ."
         if not ctx["include_shared"] else
         "The shared `train_queue_status.csv` copy is INCLUDED "
         "(`--include-shared`)."))
    a("")
    a("### Nohup logs (queue-level lines)")
    a("")
    a(_md_table(["nohup log", "queue", "step outcomes", "VERIFY lines",
                 "blocks w/o outcome"],
                ctx["per_nohup"]))
    a("")
    ji = ctx["join"]
    a(f"**Join integrity, re-measured this run.** {ji['blocks']} `$` command "
      f"blocks; {ji['with_outcome']} closed with a queue outcome line "
      f"({ji['blocks_without_outcome']} did not); {ji['naming_one_step_log']} "
      f"of those name exactly one step log through the `✓ log → …` "
      f"path the engine prints, and {ji['step_log_on_lake']} of those step logs "
      f"are present on the lake. That path is the join key rather than `run_id`, "
      f"because it survives the block whose run manifest failed to write "
      f"(measured: 2017/postproc, 2026-09-05, `[Errno 5]`). Step logs actually "
      f"opened for a timestamp: **{ctx['n_steplogs']}** — only an uncovered "
      f"event needs dating.")
    a("")
    if ctx["unstamped_note"]:
        a(ctx["unstamped_note"])
        a("")
    a("## Coverage by tag")
    a("")
    a("`snapshot` / `recovered` name where each step's row came from; `—` means no "
      "row exists in either source. A `—` is not proof the step never ran: a job "
      "may declare a steps SUBSET, and a resume skip writes no row at all. "
      f"Launch-level `GUARD:runtag` rows ({ctx['n_guard_snapshot']} of them) carry "
      "no year or tag and form no arm, so they appear in no line here.")
    a("")
    a(_md_table(["tag", "year", "campaign (queue file)"] + ctx["step_cols"]
                + ["VERIFY"], ctx["coverage"]))
    a("")
    a("## Refused — evidence present, but not enough to write a row")
    a("")
    body = [[r["src"], r["line"], "/".join(r["ev_key"]), r["why"],
             "`" + r["quoted"].replace("|", "\\|") + "`"]
            for r in ctx["refusals"]]
    body += [[n["src"], n["line"], "—", _WHY_NOTE.get(n["kind"], n["kind"]),
              "`" + str(n["detail"]).replace("|", "\\|") + "`"]
             for n in ctx["notes"]
             if n["kind"] in _WHY_NOTE]
    if body:
        a(_md_table(["source", "line", "year/tag/step", "why", "evidence"],
                    sorted(body, key=lambda r: (str(r[0]), int(r[1])))))
    else:
        a("None.")
    a("")
    a("Also not synthesised, by design: `GUARD:runtag` rows (not step outcomes, "
      "and the nohup log carries no timestamp for them — the snapshots already "
      f"hold {ctx['n_guard_snapshot']}); resume skips "
      f"(`- skip job/step (already OK)`, {ctx['n_skip']} in the window); D7 "
      f"re-verifies of skipped steps ({ctx['n_reverify']} in the window).")
    a("")
    a("## Diagnostic — a later hard outcome the log shows and the ledger may not")
    a("")
    a("Keys the snapshots DO cover, where a nohup log shows a hard state newer "
      "than the newest surviving snapshot row. Nothing is written for these (the "
      "suppression rule stands); they are listed because this is exactly the D10 "
      "hazard — a later FAIL that revoked an earlier OK — and a ledger missing one "
      "grants resume credit for a step that failed.")
    a("")
    a("Both diagnostics below are computed over the SNAPSHOT rows only. A "
      "synthesised row can never be the newest for one of these keys — synthesis "
      "happens exclusively where no snapshot row exists — so merging cannot move "
      "either answer.")
    a("")
    a("`later in the logs` is what any log shows for the SAME key afterwards — a "
      "hard state with a later OK behind it was already recovered by a relaunch "
      "and is not a standing failure. Both of those rows are suppressed here "
      "(the key is snapshot-covered), so the log is the only place that recovery "
      "is visible at all.")
    a("")
    if ctx["later_hard"]:
        a(_md_table(["year/tag/step", "log state", "log ts", "newest snapshot ts",
                     "later in the logs", "source", "line"],
                    [["/".join(d["key"]), d["state"], d["ts"],
                      d["newest_snapshot_ts"], d["superseded"] or "none",
                      d["src"], d["line"]]
                     for d in ctx["later_hard"]]))
    else:
        a("None found.")
    a("")
    a("### And the mirror case: a surviving row that is still mid-step")
    a("")
    a("`phase4_train_queue.py::run_step` appends its row as `RUNNING`, flushes, "
      "then mutates that SAME dict on completion. An orphan snapshotted between "
      "those two flushes preserves the `RUNNING`, and if it is the newest "
      "surviving row for that key the ledger's last word is a state "
      "`queue_ledger.py::_completed_steps` counts as a REVOCATION — so the step is "
      "marked for re-run even though the log says it finished. Suppression keeps "
      "the log's terminal row out (the key is covered), so these are listed "
      "instead.")
    a("")
    if ctx["stale_running"]:
        a(_md_table(["year/tag/step", "newest snapshot", "at", "log says", "at",
                     "source", "line"],
                    [["/".join(d["key"]), d["snapshot_state"], d["snapshot_ts"],
                      d["log_state"], d["log_ts"], d["src"], d["line"]]
                     for d in ctx["stale_running"]]))
    else:
        a("None found.")
    a("")
    a("### Rows that share a timestamp and disagree on state")
    a("")
    a(f"**{len(ctx['twins'])} key(s)** carry two states at ONE timestamp — the same "
      "mid-step artefact, both halves surviving. `_merged_rows` sorts by `ts` alone "
      "and its sort is stable, so which one a reader consumes LAST is decided by "
      "ROW ORDER, not by the timestamp. `rebuild_queue_ledger.py::_sort_key` puts "
      "the non-terminal row FIRST within such a group, so the terminal row has the "
      "final word — which is what the queue's own per-launch file (one mutated row "
      "per step) would have shown.")
    a("")
    if ctx["twins"]:
        a(_md_table(["job/year/tag/step", "ts", "states"],
                    [["/".join(k[:4]), k[4], ", ".join(v)]
                     for k, v in ctx["twins"]]))
    a("")
    a("## What to do with this file")
    a("")
    a("Nothing, until Kam decides. Restoring means copying "
      f"`{ctx['out'].name}` into `phase4/qc/` **on the lake**, after which "
      "resume credit, `cost_report`, `registry_from_manifests` and `pilot_gate` "
      "all merge it. That changes the audit trail and is not an autonomous action "
      "(`phase4/qc/ledger_recovery/README.md`).")
    a("")
    return "\n".join(o) + "\n"


# ─────────────────────────────────────────────────────────────────────────────

def _coverage(rows, tag_campaign, step_cols):
    """One line per (tag, year): where each step's row came from."""
    src_of = defaultdict(set)
    for r in rows:
        origin = "recovered" if r["detail"].startswith(PREFIX) else "snapshot"
        src_of[(r["tag"], r["year"], r["step"])].add(origin)
    # Launch-level GUARD:runtag rows carry no year and no tag by construction
    # (phase4_train_queue.py::_guard_row passes an empty job at launch), so they
    # form no arm and would render as an all-dash line that means nothing.
    pairs = sorted({(r["tag"], r["year"]) for r in rows if r["tag"] or r["year"]})
    body = []
    for tag, year in pairs:
        cells = []
        for st in step_cols:
            got = src_of.get((tag, year, st), set())
            cells.append("+".join(sorted(got)) if got else "—")
        v = src_of.get((tag, year, "VERIFY"), set())
        body.append([tag or "(none)", year or "(none)",
                     tag_campaign.get(tag, "—")]
                    + cells + ["+".join(sorted(v)) if v else "—"])
    return body


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--recovery-dir", default=str(REC_DIR),
                    help="directory holding the orphaned snapshots (repo)")
    ap.add_argument("--logs-dir", default=str(lake.LOGS_DIR),
                    help="phase4/logs to READ nohup + step logs from")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--since", default=DEFAULT_SINCE, help="YYYYMMDD, inclusive")
    ap.add_argument("--until", default=DEFAULT_UNTIL, help="YYYYMMDD, inclusive")
    ap.add_argument("--include-shared", action="store_true",
                    help="also ingest the clobbered shared train_queue_status.csv copy")
    args = ap.parse_args(clean_argv())

    out = assert_not_lake(args.out)
    report_path = assert_not_lake(args.report)
    rec_dir, logs_dir = Path(args.recovery_dir), Path(args.logs_dir)

    snap_rows, per_snapshot = load_snapshots(rec_dir, args.include_shared)
    covered = {(r["year"], r["tag"], r["step"]) for r in snap_rows}

    events, notes, per_nohup, cache = [], [], [], {}
    tag_campaign = {}
    logs = nohup_logs(logs_dir, args.since, args.until)
    for path, stem, _ts in logs:
        ev, nt = parse_nohup(path)
        events.extend(ev)
        notes.extend(nt)
        for e in ev:
            if e["tag"]:
                tag_campaign.setdefault(e["tag"], stem)
        per_nohup.append([path.name, stem,
                          sum(1 for e in ev if e["kind"] == "step"),
                          sum(1 for e in ev if e["kind"] == "verify"),
                          sum(1 for n in nt
                              if n["kind"] == "block_without_outcome")])

    synth_rows, refusals, _suppressed = synthesise(events, logs_dir, covered, cache)
    later_hard = later_hard_outcomes(events, snap_rows, logs_dir, cache)
    stale_running = stale_running_coverage(events, snap_rows, logs_dir, cache)
    rows, prov = merge_rows(snap_rows, synth_rows)

    write_csv(rows, out)

    # The one other nohup log on the mount. Its content is MEASURED here rather
    # than described, because a sentence about another file's contents rots the
    # moment that file changes — the failure mode CLAUDE.md's own header records.
    unstamped = logs_dir / "train_queue_nohup.log"
    note = ""
    if unstamped.exists():
        u_ev, u_nt = parse_nohup(unstamped)
        u_q = ""
        for line in io.open(unstamped, encoding="utf-8", errors="replace"):
            m = RX_QUEUE.match(line.rstrip("\r\n"))
            if m:
                u_q = m.group("queue")
                break
        note = (f"Also on the mount: the unstamped `train_queue_nohup.log` — the "
                f"pre-P11 default name, which carries no launch stamp, so no "
                f"window can admit it. Measured, not assumed: it names queue "
                f"`{u_q or '(none)'}` and holds {len(u_ev)} queue-level event(s) "
                f"plus {len(u_nt)} line(s) that write no row (resume skips and "
                f"unclosed blocks). Not read into this candidate.")

    n_snapshot = len({tuple(r[c] for c in COLS) for r in snap_rows})
    step_cols = ["labels", "tile", "train", "evaluate", "inference", "postproc"]
    ctx = dict(
        out=out, per_snapshot=per_snapshot, per_nohup=per_nohup,
        n_snapshot_raw=len(snap_rows), n_snapshot=n_snapshot,
        n_synth=len(synth_rows), n_rows=len(rows),
        n_steplogs=len([k for k, v in cache.items() if v]),
        include_shared=args.include_shared, refusals=refusals, notes=notes,
        later_hard=later_hard, unstamped_note=note, step_cols=step_cols,
        stale_running=stale_running, twins=equal_ts_state_twins(rows),
        join=join_integrity(events, notes, logs_dir),
        coverage=_coverage(rows, tag_campaign, step_cols),
        n_guard_snapshot=sum(1 for r in snap_rows if r["step"] == "GUARD:runtag"),
        n_skip=sum(1 for n in notes if n["kind"] == "resume_skip"),
        n_reverify=sum(1 for n in notes
                       if n["kind"] == "reverify_of_skipped_step"),
        n_shared_rows=sum(1 for v in prov.values() if len(v) > 1),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(report_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(build_report(ctx))

    kinds = Counter(n["kind"] for n in notes)
    print(f"  snapshots      : {len(per_snapshot)} files, "
          f"{len(snap_rows)} raw rows, {n_snapshot} distinct")
    print(f"  nohup logs     : {len(logs)} in {args.since}..{args.until}, "
          f"{len(events)} queue-level events")
    print(f"  synthesised    : {len(synth_rows)} rows  "
          f"(refused {len(refusals)}; {dict(kinds)})")
    print(f"  diagnostics    : {len(later_hard)} later-hard, "
          f"{len(stale_running)} stale-RUNNING, "
          f"{len(ctx['twins'])} equal-ts state twin(s)")
    print(f"  merged ledger  : {len(rows)} rows  \u2192 {out}")
    print(f"  report         : {report_path}")
    print("  NOTHING WAS WRITTEN TO THE LAKE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

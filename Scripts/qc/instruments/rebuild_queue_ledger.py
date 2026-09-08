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
  (year, tag, step, LAUNCH), and its `detail` is prefixed RECOVERED-FROM-LOGS(…):
  so no reader can mistake it for a queue-written row.

SUPPRESSION IS PER LAUNCH, NOT PER KEY (fixed 2026-09-07; see §L1 below)
-----------------------------------------------------------------------
The first version keyed suppression on (year, tag, step) alone, and that erased
the very thing this instrument exists to recover. `of_2017k` ran THREE times: ofB
(09-05, VERIFY:tile MISSING), of2017k (09-06 00:22, died on a missing lake file)
and of2017k2 (09-06 01:40→03:33, the full successful pipeline). ofB's and
of2017k's rows survived in orphans; of2017k2's were erased. Because the earlier,
FAILED launches held `labels` and `tile` rows under the same key, of2017k2's
labels (2.3 min) and tile (21.1 min) were suppressed — even though its nohup log
prints both outcomes. A reused run-tag is normal (a relaunch keeps the tag), so
the key must carry WHICH LAUNCH the row came from.

The log side of that key is free: an event's launch IS its nohup file. The
snapshot side is not, because a row names only its `session` — and no nohup log
prints a session. So sessions are attributed to launches by evidence, in
`attribute_launches`: candidate launches are those whose window contains the
session's earliest surviving row, and the winner is the one whose printed step
outcomes EXACTLY match that session's rows on (job, year, tag, step, state,
minutes) / (…, verdict) for a VERIFY. Zero matches ⇒ the session is left
UNATTRIBUTED and covers nothing, which is the safe direction: it can only add
rows the log proves, never withhold them. Measured on the window: 13 sessions,
10 attributed with 1–147 exact matches each, 3 unattributed (t1gpuA, t1gpuB,
t1stageC) — and the per-session heartbeats independently name a nohup log for
all three that IS NOT ON THE LAKE, i.e. their launches' logs are gone, so there
are no events of theirs to duplicate. That cross-check is published, not
trusted: `newest_nohup` is "the newest log at heartbeat time", and under parallel
runtimes it names the OTHER VM's log (measured: trend8B2's heartbeat names
trend8A2's log), which is exactly why it cannot drive the map.

TWO PLACES WHERE THE EVIDENCE CONTRADICTS THE OBVIOUS RECONSTRUCTION
--------------------------------------------------------------------
1. `ts` IS THE STEP START IN A QUEUE-WRITTEN ROW, NOT THE END.
   `phase4_train_queue.py::run_step` builds one `rec` with `ts=now()` before
   launching the child and then MUTATES that same dict on completion without
   touching `ts`. A recovered row carrying the engine's `completed:` therefore
   sits up to `minutes` LATER than the queue would have written, and any reader
   computing a span from ledger rows sees the session start late: of2017k2's
   A100 span read 41.7 min from the first version's rows against the 113.0 the
   queue itself printed (`total 113.1 min`).

   So `ts` is now reconstructed as the step START, by a three-rung ladder, and
   which rung was used is IN THE PREFIX (`RECOVERED-FROM-LOGS(ts=start)` etc.):

     ts=start              the block's own `run_id: 20260906T014036Z_…` stamp —
                           the engine mints it at startup and the queue prints it
                           inside the block, so it is a timestamp the LOG carries
                           for that command. Sanity-gated: it must lie inside
                           [completed − minutes − 60 s, completed + 60 s], or the
                           rung is refused (a run_id from a differently-zoned
                           clock cannot pass itself off as a start).
     ts=completed-minutes  no usable run_id: the step log's `completed:` minus the
                           queue's own elapsed. The queue's clock starts one line
                           before `t0`, so this reconstructs the same interval.
     ts=completed          neither — the step log's `completed:`, unchanged. This
                           is also what every VERIFY row gets: `verify_step`
                           stamps its row when the check ENDS and the log prints
                           no duration for it, so a recovered VERIFY carries the
                           moment the check BEGAN (measured on the CPU pilot, a
                           labels VERIFY ran seven minutes).

   Which rung is right is MEASURED EVERY RUN and published, not asserted here:
   `ts_rung_accuracy` scores all three against the surviving queue-written rows
   themselves, wherever one content fingerprint identifies exactly one row and one
   event, and the report's rung table carries n, median and max. (The ordering
   that measurement produced when the ladder was built: run_id ≪ completed−minutes
   ≪ bare completed, the first by an order of magnitude.)

   The engine's `started:` is NOT one of the rungs: StepLogger opens the step only
   after footprint discovery and staging. Measured on `hy_e3_2011s/labels`, the
   queue's row says 21:21:39, the block's run_id says 21:21:45, and the step log
   says `started: 21:26:59` — five minutes of engine work later.

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
import datetime as dt
import io
import json
import re
import statistics
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
# queue_verify.py::_mb_from_verdict (which anchors `(\d+)MB` at the START of the
# string and would then read a wrong number rather than none — the one failure
# mode worse than losing the parse). The STEM is the constant every reader and
# test matches on; `_prefix` appends the ts rung actually used, so the mode is
# visible in the row itself and not only in the report.
PREFIX = "RECOVERED-FROM-LOGS"

# The three rungs of the ts ladder, in the order `_anchor` tries them. Their names
# ARE the text in the prefix, so a row says how its timestamp was derived.
TS_START = "ts=start"                       # the block's run_id stamp
TS_COMPLETED_MINUTES = "ts=completed-minutes"
TS_COMPLETED = "ts=completed"

# How far the engine's run_id stamp may sit outside the step's own window before
# the rung is refused. The measured spread is +1…+7 s (the engine minting after
# the queue stamped its row); 60 s is two orders of magnitude of slack and still
# rejects a stamp from a clock that is not this VM's.
RUNID_TOLERANCE_S = 60


def _prefix(mode):
    """`RECOVERED-FROM-LOGS(ts=start): ` — the stem, the rung, then the text.

    Still opens with a letter, so `_mb_from_verdict` reads no size from it (see
    PREFIX), and still `startswith(PREFIX)` for every reader that only wants to
    know whether the row is queue-written.
    """
    return f"{PREFIX}({mode}): "

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
# The engine's run_id opens with its own start stamp — phase4seg mints it at
# startup and the queue echoes the whole line into the nohup log, which is what
# makes a per-step START recoverable from a log that prints no timestamps.
RX_RUNID_STAMP = re.compile(r"^(?P<stamp>\d{8}T\d{6})Z")
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


def _to_dt(ledger_ts):
    """`2026-09-06 01:42:44` → datetime, or None. The ledger's own format only.

    Arithmetic on timestamps happens HERE and nowhere else, so there is one place
    where a malformed value turns into None instead of into a wrong answer.
    """
    try:
        return dt.datetime.strptime(str(ledger_ts or "").strip(),
                                    "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _from_dt(when):
    """datetime → the ledger's format, TRUNCATED, never rounded.

    `run_step` formats `datetime.now()` with strftime, which drops the fraction;
    a recovered value that rounded up could land one second after a real row it
    should precede.
    """
    return when.strftime("%Y-%m-%d %H:%M:%S")


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
    """→ (completed, steplog_name, why_not). The engine `completed:` for the block.

    A VERIFY event anchors on the block it follows — verify_step runs immediately
    after the step it checks — and only when that block ran the SAME step, so a
    re-verify of a skipped step (which has no block of its own) cannot borrow
    another step's clock. No anchor means no timestamp, and no timestamp means the
    row is refused rather than written with a blank the readers would sort first.

    This is the END of the step, and it is what the DIAGNOSTICS compare against a
    surviving row ("the log shows this finished after the ledger's last word").
    The row's own `ts` is a different question — `_anchor` reconstructs the START.
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


def _anchor(event, logs_dir, cache):
    """→ (anchor, why). `anchor` = {"ts", "mode", "completed", "steplog"} or None.

    `ts` is the STEP START, because that is what a queue-written `ts` is
    (`run_step` stamps the row before spawning the child and never updates it).
    The rung used is in `mode` and travels into the row's own prefix, so nobody
    has to come back here to find out what a recovered timestamp means:

      TS_START             the block's `run_id: 20260906T014036Z_…` stamp, gated
                           to lie inside the step's own window. Measured median
                           +1 s against the queue's row on 83 matched events.
      TS_COMPLETED_MINUTES `completed:` − the queue's own `elapsed`, when no
                           run_id passed. Same interval the queue timed.
      TS_COMPLETED         `completed:` itself — the last resort, and the ONLY
                           rung a VERIFY event may use: verify_step stamps its
                           row when the check ENDS, the log prints no duration
                           for it, so the honest value is when the check BEGAN.
    """
    completed, steplog, why = _anchor_ts(event, logs_dir, cache)
    if not completed:
        return None, why
    base = dict(completed=completed, steplog=steplog)
    end = _to_dt(completed)
    mins = None
    try:
        mins = float(event.get("minutes")) if event.get("minutes") else None
    except ValueError:                                          # pragma: no cover
        mins = None
    if event["kind"] == "step" and end is not None:
        m = RX_RUNID_STAMP.match(str((event.get("block") or {}).get("run_id") or ""))
        if m:
            start = dt.datetime.strptime(m.group("stamp"), "%Y%m%dT%H%M%S")
            hi = end + dt.timedelta(seconds=RUNID_TOLERANCE_S)
            lo = (end - dt.timedelta(minutes=mins,
                                     seconds=RUNID_TOLERANCE_S)
                  if mins is not None else None)
            if start <= hi and (lo is None or start >= lo):
                return dict(base, ts=_from_dt(start), mode=TS_START), ""
        if mins is not None:
            return dict(base, ts=_from_dt(end - dt.timedelta(minutes=mins)),
                        mode=TS_COMPLETED_MINUTES), ""
    return dict(base, ts=completed, mode=TS_COMPLETED), ""


def _ts_source(anchor):
    """What `detail` says the timestamp came from. One phrase per rung."""
    if anchor["mode"] == TS_START:
        return "run_id-stamp"
    if anchor["mode"] == TS_COMPLETED_MINUTES:
        return "engine-completed-minus-minutes"
    return "engine-completed"


def _stamp_to_ts(stamp):
    """`20260906T014007Z` → `2026-09-06 01:40:07`. The launcher's clock is the
    VM's clock (both UTC on Colab), measured: a launch's first surviving row sits
    2–8 s after its stamp."""
    s = str(stamp)
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[9:11]}:{s[11:13]}:{s[13:15]}"


def _row_fp(row):
    """A snapshot row → the tuple a nohup log must print to be the SAME run.

    `minutes` is the fingerprint for a step (0.1-min resolution over a queue that
    ran for hours) and the verdict TEXT for a VERIFY, because that is what the log
    quotes. A `RUNNING` row fingerprints to nothing any log prints — no outcome
    line ever says RUNNING — which is deliberate: a launch whose only surviving
    row is mid-step should NOT be able to suppress its own terminal outcome.
    """
    if row["step"].startswith("VERIFY"):
        return (row["job"], row["year"], row["tag"], row["step"], row["state"],
                row["detail"])
    return (row["job"], row["year"], row["tag"], row["step"], row["state"],
            row["minutes"])


def _event_fp(ev):
    """The same tuple, from the log side."""
    if ev["kind"] == "verify":
        return (ev["job"], ev["year"], ev["tag"], ev["step"], ev["state"],
                ev["verdict"])
    return (ev["job"], ev["year"], ev["tag"], ev["step"], ev["state"],
            ev["minutes"])


def launch_spans(logs, events, logs_dir, cache=None):
    """→ {nohup name: (start, end)} — when each launch could have written rows.

    START is the launch stamp in the filename, which the launcher writes and
    nothing later edits. END is the newest `completed:` the launch's own blocks
    anchor to; a launch that printed no datable block spans a single instant. No
    padding either side: the window is only used to REJECT candidates, and a
    generous one would re-admit the mis-map it exists to prevent (measured:
    t1gpuA's first row is 3.3 h after the previous launch's last block).
    """
    cache = {} if cache is None else cache
    ends = defaultdict(str)
    for ev in events:
        completed, _sl, _why = _anchor_ts(ev, logs_dir, cache)
        if completed:
            ends[ev["src"]] = max(ends[ev["src"]], completed)
    out = {}
    for path, _stem, stamp in logs:
        start = _stamp_to_ts(stamp)
        out[path.name] = (start, max(start, ends.get(path.name, "")))
    return out


def attribute_launches(snap_rows, events, spans):
    """→ (launch_of, table). WHICH LAUNCH each surviving session's rows came from.

    This is the (year, tag, step, LAUNCH) key's snapshot half, and it has to be
    derived because a row names only its `session` while no nohup log prints one.
    Two pieces of evidence, in this order:

      1. the launch WINDOW must contain the session's earliest surviving row —
         which rules out a launch that had already finished (t1gpuA's first row is
         3.3 h after the previous launch's last block);
      2. among the survivors, the launch whose printed outcomes EXACTLY match this
         session's rows (`_row_fp`) wins, by count.

    Time alone is not enough: hardyear4's rows exactly match one outcome line in a
    launch that ended three minutes before its first row — a relaunch of the same
    job re-printing the same rounded `minutes`. Content alone is not enough
    either, for the same reason. Both together are unambiguous on the whole
    window.

    ZERO matches leaves the session UNATTRIBUTED, and an unattributed session
    covers nothing. That is the safe direction here: the worst it can do is
    synthesise a row the log proves, beside a queue-written row that says the same
    thing; the alternative — guessing a launch — silently withholds an entire
    launch's history, which is the defect this instrument exists to undo.
    """
    groups = defaultdict(list)
    for r in snap_rows:
        groups[(r["host"], r["session"])].append(r)
    printed = defaultdict(set)
    for ev in events:
        printed[ev["src"]].add(_event_fp(ev))
    launch_of, table = {}, []
    for key in sorted(groups):
        rows = groups[key]
        first = min(r["ts"] for r in rows)
        scored = sorted((sum(1 for r in rows if _row_fp(r) in printed.get(src, ())),
                         start, src)
                        for src, (start, end) in spans.items()
                        if start <= first <= end)
        best = scored[-1] if scored and scored[-1][0] > 0 else None
        launch_of[key] = best[2] if best else None
        tied = [s for s in scored if best and s[0] == best[0]]
        table.append(dict(host=key[0], session=key[1], n_rows=len(rows),
                          first_ts=first, launch=best[2] if best else "",
                          matches=best[0] if best else 0,
                          n_candidates=len(scored), n_tied=len(tied)))
    return launch_of, table


def ts_rung_accuracy(snap_rows, events, logs_dir, cache=None):
    """→ {rung: {n, median_abs_s, max_abs_s}} — how far each rung lands from a
    queue-written `ts`, measured on THIS run's inputs.

    The ladder's order is a claim about the archive, so it is re-measured rather
    than asserted. The ruler is the surviving rows themselves: where one content
    fingerprint identifies exactly ONE snapshot row and exactly ONE log event, the
    row's `ts` is the queue's own answer for that execution and every rung can be
    scored against it. Uniqueness on BOTH sides is what keeps a relaunch that
    re-printed the same rounded `minutes` from being paired with the wrong row —
    without it the tails are hours, and they are not the estimator's fault.

    STEP EVENTS ONLY. A VERIFY verdict is often a constant — "citywide: labels
    step is skipped by design" is printed by every launch of every citywide job —
    so its fingerprint identifies a step, not an execution, and pairing on it
    measures nothing. (It is also the wrong ruler: a VERIFY row's `ts` is when the
    check ENDED, which no rung claims to reproduce.)

    Every rung is scored on the same matched events, minus the ones where that
    rung has nothing to work with (a block with no run_id cannot score TS_START),
    so the numbers say which order the ladder belongs in rather than only how the
    chosen rung did. The per-rung `n` is therefore comparable but not identical.
    """
    cache = {} if cache is None else cache
    rows_by, evs_by = defaultdict(list), defaultdict(list)
    for r in snap_rows:
        if not r["step"].startswith("VERIFY"):
            rows_by[_row_fp(r)].append(r)
    for ev in events:
        if ev["kind"] == "step":
            evs_by[_event_fp(ev)].append(ev)
    deltas = defaultdict(list)
    for fp, evs in evs_by.items():
        got = rows_by.get(fp) or []
        if len(evs) != 1 or len({r["ts"] for r in got}) != 1:
            continue
        truth, ev = _to_dt(got[0]["ts"]), evs[0]
        completed, _sl, _why = _anchor_ts(ev, logs_dir, cache)
        end = _to_dt(completed)
        if truth is None or end is None:
            continue
        anchor, _why = _anchor(ev, logs_dir, cache)
        if anchor and anchor["mode"] == TS_START:
            deltas[TS_START].append(
                abs((_to_dt(anchor["ts"]) - truth).total_seconds()))
        mins = float(ev["minutes"]) if ev["minutes"] else None
        if mins is not None:
            deltas[TS_COMPLETED_MINUTES].append(
                abs((end - dt.timedelta(minutes=mins) - truth).total_seconds()))
        deltas[TS_COMPLETED].append(abs((end - truth).total_seconds()))
    return {k: dict(n=len(v), median_abs_s=statistics.median(v),
                    max_abs_s=max(v))
            for k, v in sorted(deltas.items()) if v}


def heartbeat_launches(logs_dir, sessions):
    """→ [dict] — what each session's OWN beacon says the newest nohup log was.

    A CROSS-CHECK, never an input to `attribute_launches`. `vm_heartbeat` records
    the newest nohup log on the shared mount at beacon time, so with two runtimes
    up it names the OTHER VM's file (measured: trend8B2's beacon names trend8A2's
    log). What it CANNOT get wrong is a name that is not on the lake at all: that
    says the session's own log is gone, which is the claim being cross-checked for
    every session this instrument could not attribute.
    """
    out = []
    for sess in sorted({s for s in sessions if s}):
        p = Path(logs_dir) / f"heartbeat_{sess}.json"
        if not p.exists():
            out.append(dict(session=sess, present=False, named="", exists=False))
            continue
        try:
            with io.open(p, encoding="utf-8", errors="replace") as fh:
                got = json.load(fh)
        except (OSError, ValueError):                           # pragma: no cover
            out.append(dict(session=sess, present=False, named="", exists=False))
            continue
        named = str(((got.get("newest_nohup") or {}).get("name")) or "")
        out.append(dict(session=sess, present=True, named=named,
                        exists=bool(named) and (Path(logs_dir) / named).exists()))
    return out


def synthesise(events, logs_dir, covered, cache=None):
    """→ (rows, refusals, suppressed). One row per log event that is not covered.

    `covered` is the set of (year, tag, step, LAUNCH) the snapshots already hold,
    where the launch is the nohup file `attribute_launches` traced the row's
    session to. Keying it on (year, tag, step) alone — the first version — meant a
    row surviving from ANY launch silenced every other launch's outcome for the
    same work, and of_2017k ran three times under one tag: the two failed runs'
    rows survived and erased the successful one's (of2017k2, 09-06 01:40→03:33).

    The job nickname stays OUT of the key on purpose: one launch cannot run the
    same (year, tag, step) under two job ids, so adding `job` could only ever
    fail to suppress a row that is genuinely the same run.
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
        if key + (ev["src"],) in covered:
            suppressed.append(dict(ev_key=key, src=ev["src"], line=ev["line"],
                                   state=ev["state"], kind=ev["kind"], ev=ev))
            continue
        anchor, why = _anchor(ev, logs_dir, cache)
        if anchor is None:
            refusals.append(dict(ev_key=key, src=ev["src"], line=ev["line"],
                                 quoted=ev["quoted"], why=why))
            continue
        said = "verdict" if ev["kind"] == "verify" else "outcome"
        quoted = ev["verdict"] if ev["kind"] == "verify" else ev["quoted"]
        detail = (f'{_prefix(anchor["mode"])}{ev["src"]} {said} verbatim: '
                  f'"{quoted}"; ts={_ts_source(anchor)}@{anchor["steplog"]}')
        rows.append({"job": ev["job"], "year": ev["year"], "tag": ev["tag"],
                     "step": ev["step"], "state": ev["state"], "exit": ev["exit"],
                     "minutes": ev["minutes"], "detail": detail,
                     "ts": anchor["ts"], "host": "", "session": "",
                     "_src": ev["src"]})
    return rows, refusals, suppressed


def later_hard_outcomes(events, snapshot_rows, logs_dir, cache=None,
                        all_events=None):
    """SUPPRESSED events whose log shows a hard state newer than any snapshot row.

    Not synthesised — the suppression rule stands for these — but it is the exact
    shape of the D10 hazard `queue_ledger.py::_merged_rows` was hardened against: a
    later FAIL that revokes an earlier OK. If one of these is real, the surviving
    ledger grants resume credit for a step that failed. Kam sees the list; nothing
    acts on it.

    `events` is the SUPPRESSED subset — an event that became a row is in the
    candidate and needs no diagnostic. `all_events` is everything the logs hold,
    because `_later_state_in_logs` has to look past the suppression to find the
    relaunch that already fixed the failure.
    """
    cache = {} if cache is None else cache
    all_events = events if all_events is None else all_events
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
                                all_events, k, ts, logs_dir, cache)))
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
    """Keys whose newest SURVIVING snapshot row is non-terminal, while a
    SUPPRESSED log event shows a terminal outcome.

    Same mechanism as the twins above, without the twin: the orphan that survived
    was flushed mid-step, so the ledger's last word on that step is `RUNNING` —
    which `queue_ledger.py::_completed_steps` counts as a revocation, not as
    progress. The candidate therefore still says "re-run this", and the evidence
    that it finished sits only in the nohup log.

    Launch-keyed suppression narrowed this but did not close it. A session whose
    surviving rows include ANY exact content match is attributed to its launch, so
    its own mid-step RUNNING row still covers that launch's terminal outcome
    (measured: trend8_2024/postproc). Only a session with NO match at all —
    nothing but RUNNING rows — is left unattributed, and there the terminal row is
    now recovered instead of listed here. The remaining cases are reported and
    fixed by nothing: they are a human's call, exactly as before.
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


def same_run_suspects(rows, seconds=120):
    """Recovered rows that may describe the SAME execution as a queue-written one.

    This is the one hazard launch-keyed suppression introduces, and it is measured
    rather than argued about. If a session were attributed to the wrong launch — or
    left unattributed while its log IS on the lake — that launch's outcome would be
    synthesised beside the surviving row for the same execution. Two rows for one
    run is not a merge error (latest-wins takes the later, and they agree), but it
    is the signature of a broken attribution.

    `seconds` is wide on purpose: the reconstruction lands within a handful of
    seconds of the queue's own `ts`, while two real executions of one arm are hours
    apart, so anything inside two minutes is a duplicate and not a relaunch.
    """
    native = defaultdict(list)
    for r in rows:
        if not r["detail"].startswith(PREFIX):
            native[(r["year"], r["tag"], r["step"])].append(r)
    out = []
    for r in rows:
        if not r["detail"].startswith(PREFIX):
            continue
        mine = _to_dt(r["ts"])
        for n in native.get((r["year"], r["tag"], r["step"]), ()):
            theirs = _to_dt(n["ts"])
            if mine and theirs and abs((mine - theirs).total_seconds()) <= seconds:
                out.append(dict(key=(r["year"], r["tag"], r["step"]),
                                recovered_state=r["state"], recovered_ts=r["ts"],
                                snapshot_state=n["state"], snapshot_ts=n["ts"],
                                session=n["session"]))
    return sorted(out, key=lambda d: (d["recovered_ts"], d["key"]))


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
      "(`phase4seg/names.py::status_files`) merges it. Whether a file of this "
      "name is ALREADY there, and what copying this one over it would change, is "
      "measured at the end of this report.")
    a("")
    a("## What the rows are")
    a("")
    a(f"- **{ctx['n_snapshot']} snapshot-native rows** — copied byte-for-byte from "
      f"the orphaned `.part.*`/`.prev.*` temps. No prefix, no rewrite.")
    a(f"- **{ctx['n_synth']} rows synthesised from logs** — `detail` begins "
      f"`{PREFIX}(…)` and quotes the line that is the evidence. Synthesis happens "
      f"only where NO snapshot row from THE SAME LAUNCH covers "
      f"`(year, tag, step)`; {ctx['n_suppressed']} log event(s) were suppressed by "
      f"a surviving row of their own launch.")
    a(f"- **{ctx['n_rows']} rows total** after de-duplication on the full 11-tuple.")
    a("")
    a("## Two things a reader must know about the synthesised rows")
    a("")
    a("1. **`ts` is the step's START, reconstructed — and the row says how.** A "
      "queue-written row carries the start (`phase4_train_queue.py::run_step` "
      "stamps `ts` before launching the child and mutates the same dict on "
      "completion), so a recovered row carrying the engine's `completed:` made "
      "every recovered session look like it started late — of2017k2's 113-minute "
      "A100 span read 41.7 minutes. The prefix now names the rung used:")
    a("")
    acc = ctx["rung_accuracy"]

    def _acc(rung):
        got = acc.get(rung)
        return (f"n={got['n']}, median {got['median_abs_s']:.0f} s, "
                f"max {got['max_abs_s']:.0f} s" if got else "not measurable here")

    # NOT "|Δ|": a pipe inside a cell or a header ends the markdown column.
    a(_md_table(["rung", "what it is", "rows",
                 "gap from a queue-written `ts`"],
                [[f"`{TS_START}`",
                  "the block's own `run_id: 20260906T014036Z_…` stamp, gated to "
                  "lie inside the step's window",
                  ctx["ts_modes"].get(TS_START, 0), _acc(TS_START)],
                 [f"`{TS_COMPLETED_MINUTES}`",
                  "no usable run_id: `completed:` minus the queue's own elapsed",
                  ctx["ts_modes"].get(TS_COMPLETED_MINUTES, 0),
                  _acc(TS_COMPLETED_MINUTES)],
                 [f"`{TS_COMPLETED}`",
                  "`completed:` unchanged — the last resort, and the only rung a "
                  "VERIFY row may use (`verify_step` stamps its row when the check "
                  "ENDS and the log prints no duration, so the row carries when "
                  "the check BEGAN)",
                  ctx["ts_modes"].get(TS_COMPLETED, 0), _acc(TS_COMPLETED)]]))
    a("")
    a("The last column is the ladder's justification, re-measured on this run's "
      "inputs by `rebuild_queue_ledger.py::ts_rung_accuracy` rather than quoted: "
      "every rung is scored on the SAME step events — those where one content "
      "fingerprint identifies exactly one surviving row and exactly one log "
      "event, so the row's own `ts` is the queue's answer for that execution. "
      "VERIFY events are excluded because their verdict text is frequently a "
      "constant (\"citywide: labels step is skipped by design\"), which "
      "fingerprints a step rather than a run.")
    a("")
    a("Because suppression is now per LAUNCH, a key CAN carry both a "
      "queue-written and a recovered row — the two failed of_2017k launches and "
      "the successful one, for instance. That is why the rung matters: both "
      "timestamps are step starts on the same clock, so latest-wins compares like "
      "with like. `same-run suspects` below is the check that the two never "
      "describe the SAME execution.")
    a("")
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
    a("## Which launch each surviving session's rows came from")
    a("")
    a("Suppression keys on `(year, tag, step, LAUNCH)`. The log side of that key "
      "is free — an event's launch is its nohup file — but a snapshot row names "
      "only its `session`, and no nohup log prints one. "
      "`rebuild_queue_ledger.py::attribute_launches` derives it from two pieces of "
      "evidence: the launch's window must contain the session's earliest surviving "
      "row, and among those survivors the launch whose printed outcomes EXACTLY "
      "match this session's rows on `(job, year, tag, step, state, minutes)` — the "
      "verdict text for a VERIFY — wins by count. Neither alone is enough: one "
      "session's rows content-match a single outcome line in a launch that had "
      "already ended (a relaunch re-printing the same rounded `minutes`), and of "
      "two launches started 69 s apart the earlier one's window contains the "
      "later one's first row.")
    a("")
    a("A session with ZERO matches is left **unattributed** and covers nothing. "
      "That is the safe direction: the worst it can do is add a row the log "
      "proves next to a queue-written row saying the same thing (counted below as "
      "a same-run suspect), while guessing a launch withholds a whole launch's "
      "history — the defect this instrument exists to undo.")
    a("")
    a(_md_table(["session", "host", "surviving rows (raw, across orphans)",
                 "earliest row", "attributed to", "exact matches",
                 "candidate launches"],
                [[d["session"] or "(none)", d["host"] or "(none)", d["n_rows"],
                  d["first_ts"], d["launch"] or "**unattributed**",
                  d["matches"], d["n_candidates"]]
                 for d in ctx["attribution"]]))
    a("")
    n_tied = sum(1 for d in ctx["attribution"] if d["n_tied"] > 1)
    a(f"Rows are RAW here — a launch re-flushes its whole table after every step, "
      f"so one row appears in each of its later orphans; the campaign table below "
      f"counts them distinct. **{n_tied} session(s)** had two or more candidate "
      f"launches tied on the winning match count, which `attribute_launches` "
      f"settles towards the LATER launch; a tie is a weaker claim than the rest of "
      f"this table and is counted here so it cannot pass unseen.")
    a("")
    a("### Cross-check: what each session's own beacon says")
    a("")
    a("Independent of everything above. `vm_heartbeat` records the newest nohup "
      "log on the shared mount at beacon time, so with two runtimes up it names "
      "the OTHER VM's file — which is exactly why it cannot drive the map. What it "
      "cannot get wrong is a name that is **not on the lake at all**: that says "
      "the session's own log is gone, and therefore that there are no events of "
      "that launch for its rows to have suppressed.")
    a("")
    if ctx["heartbeats"]:
        a(_md_table(["session", "beacon on the lake", "names nohup log",
                     "that log exists"],
                    [[d["session"], "yes" if d["present"] else "no",
                      d["named"] or "—", "yes" if d["exists"] else "**no**"]
                     for d in ctx["heartbeats"]]))
    else:
        a("No beacons for these sessions.")
    a("")
    a("### Same-run suspects — the check on the attribution")
    a("")
    a("A recovered row within two minutes of a queue-written row for the same "
      "`(year, tag, step)`. Two real executions of one arm are hours apart and the "
      "reconstruction lands within seconds, so anything here is one execution "
      "recorded twice — the signature of a launch attributed wrongly. Latest-wins "
      "would still answer correctly (the two agree), but the list is measured "
      "every run rather than argued about.")
    a("")
    if ctx["suspects"]:
        a(_md_table(["year/tag/step", "recovered", "at", "queue-written", "at",
                     "session"],
                    [["/".join(d["key"]), d["recovered_state"], d["recovered_ts"],
                      d["snapshot_state"], d["snapshot_ts"], d["session"]]
                     for d in ctx["suspects"]]))
    else:
        a("None.")
    a("")
    a("## Rows by campaign")
    a("")
    a("Where the candidate's rows come from, one line per queue file. A campaign "
      "with no snapshot rows is a launch whose orphans did not survive at all — "
      "its whole ledger is reconstructed.")
    a("")
    a(_md_table(["campaign (queue file)", "snapshot", "recovered", "total"],
                ctx["campaigns"]))
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
    a("Events the suppression rule WITHHELD — a row of their own launch survived — "
      "where the log nonetheless shows a hard state newer than the newest "
      "surviving snapshot row for that key. Nothing is written for these; they are "
      "listed because this is exactly the D10 hazard — a later FAIL that revoked "
      "an earlier OK — and a ledger missing one grants resume credit for a step "
      "that failed.")
    a("")
    a("Both diagnostics below run over the SUPPRESSED events only, against the "
      "snapshot rows. An event that became a row is already in the candidate and "
      "needs no diagnostic; the timestamp compared is the block's `completed:` "
      "(when the step ENDED), not the reconstructed start, so \"newer than the "
      "ledger's last word\" means what it says.")
    a("")
    a("`later in the logs` is what any log shows for the SAME key afterwards — a "
      "hard state with a later OK behind it was already recovered by a relaunch "
      "and is not a standing failure. It is searched across ALL events, suppressed "
      "or not, because the relaunch that fixed a failure is frequently a different "
      "launch whose rows this candidate now carries.")
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
      "the log's terminal row out (a row of that launch survived), so these are "
      "listed instead. Launch-keying narrowed this and did not close it: a session "
      "is attributed on ANY exact content match, so its own mid-step `RUNNING` "
      "still covers its launch's terminal outcome. Only a session with nothing but "
      "`RUNNING` rows is unattributed, and there the terminal row is recovered "
      "rather than listed.")
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
    a(ctx["on_lake_note"])
    a("")
    return "\n".join(o) + "\n"


# ─────────────────────────────────────────────────────────────────────────────

# Reads the rung back off a written row, so the mode table in the report is
# counted from the CSV's own text rather than from a variable that could drift
# away from what `_prefix` actually wrote.
RX_MODE = re.compile(r"^" + re.escape(PREFIX) + r"\((?P<mode>[^)]+)\)")


def _campaign_counts(snap_rows, synth_rows, launch_of, launch_campaign,
                     tag_campaign):
    """→ [[campaign, snapshot rows, recovered rows, total]], one line per queue.

    A recovered row's campaign is the queue its nohup log ran; a snapshot row's is
    the campaign of the launch it was attributed to, falling back to its tag's when
    the session could not be attributed (the rows are real either way — only their
    launch is unknown). Distinct on the full 11-tuple, so a row re-flushed into
    several orphans of one launch is counted once.
    """
    got = defaultdict(lambda: [set(), set()])
    for r in snap_rows:
        launch = launch_of.get((r["host"], r["session"]))
        camp = (launch_campaign.get(launch) if launch
                else tag_campaign.get(r["tag"])) or "(launch unknown)"
        got[camp][0].add(tuple(r[c] for c in COLS))
    for r in synth_rows:
        camp = launch_campaign.get(r.get("_src"), "(launch unknown)")
        got[camp][1].add(tuple(r[c] for c in COLS))
    return [[c, len(a), len(b), len(a) + len(b)]
            for c, (a, b) in sorted(got.items())]


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

    events, notes, per_nohup, cache = [], [], [], {}
    tag_campaign, launch_campaign = {}, {}
    logs = nohup_logs(logs_dir, args.since, args.until)
    for path, stem, _ts in logs:
        ev, nt = parse_nohup(path)
        events.extend(ev)
        notes.extend(nt)
        launch_campaign[path.name] = stem
        for e in ev:
            if e["tag"]:
                tag_campaign.setdefault(e["tag"], stem)
        per_nohup.append([path.name, stem,
                          sum(1 for e in ev if e["kind"] == "step"),
                          sum(1 for e in ev if e["kind"] == "verify"),
                          sum(1 for n in nt
                              if n["kind"] == "block_without_outcome")])

    # THE KEY, IN THREE LINES: a snapshot row covers a log event only when both
    # came from the SAME launch. `attribute_launches` is where that is derived and
    # where the reasoning lives.
    spans = launch_spans(logs, events, logs_dir, cache)
    launch_of, attribution = attribute_launches(snap_rows, events, spans)
    covered = {(r["year"], r["tag"], r["step"],
                launch_of[(r["host"], r["session"])])
               for r in snap_rows if launch_of.get((r["host"], r["session"]))}

    synth_rows, refusals, suppressed = synthesise(events, logs_dir, covered, cache)
    supp_events = [s["ev"] for s in suppressed]
    later_hard = later_hard_outcomes(supp_events, snap_rows, logs_dir, cache,
                                     all_events=events)
    stale_running = stale_running_coverage(supp_events, snap_rows, logs_dir, cache)
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

    # Is a file of this name ALREADY merged by every reader? Measured, not
    # assumed: an earlier candidate was copied to the lake on 2026-09-07 (commit
    # 86673788), so this one does not arrive on an empty slot — it would REPLACE a
    # live ledger file, which is a bigger decision than the first copy was.
    live = lake.BASE / "phase4" / "qc" / out.name
    if live.exists():
        with io.open(live, encoding="utf-8", newline="") as fh:
            n_live = len(list(csv.DictReader(fh)))
        on_lake_note = (
            f"**A file of this name is ALREADY on the lake** ({live}), holding "
            f"{n_live} rows against this candidate's {len(rows)}. Every reader "
            f"merges it today. Copying this one over it is a REPLACEMENT of live "
            f"ledger content, not an addition — the delta is what the "
            f"launch-keyed suppression recovered, and the `ts` of every recovered "
            f"row moves from the step's end to its start.")
    else:
        on_lake_note = ("No file of this name is on the lake; this candidate "
                        "would be an addition, not a replacement.")

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
        attribution=attribution, spans=spans, launch_campaign=launch_campaign,
        heartbeats=heartbeat_launches(
            logs_dir, {r["session"] for r in snap_rows}),
        ts_modes=Counter(m.group("mode") for m in
                         (RX_MODE.match(r["detail"]) for r in synth_rows)
                         if m),
        campaigns=_campaign_counts(snap_rows, synth_rows, launch_of,
                                   launch_campaign, tag_campaign),
        suspects=same_run_suspects(rows),
        n_suppressed=len(suppressed), on_lake_note=on_lake_note,
        rung_accuracy=ts_rung_accuracy(snap_rows, events, logs_dir, cache),
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
    print(f"  launches       : {len(spans)} in window; sessions "
          f"{sum(1 for d in attribution if d['launch'])} attributed, "
          f"{sum(1 for d in attribution if not d['launch'])} unattributed")
    print(f"  synthesised    : {len(synth_rows)} rows  "
          f"(suppressed {len(suppressed)}; refused {len(refusals)}; "
          f"{dict(kinds)})")
    print(f"  ts rungs       : {dict(sorted(ctx['ts_modes'].items()))}")
    print(f"  diagnostics    : {len(later_hard)} later-hard, "
          f"{len(stale_running)} stale-RUNNING, "
          f"{len(ctx['twins'])} equal-ts state twin(s), "
          f"{len(ctx['suspects'])} same-run suspect(s)")
    print(f"  merged ledger  : {len(rows)} rows  \u2192 {out}")
    print(f"  report         : {report_path}")
    print("  NOTHING WAS WRITTEN TO THE LAKE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

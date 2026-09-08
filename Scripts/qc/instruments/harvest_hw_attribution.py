"""harvest_hw_attribution.py — WHICH STEP was running while the hardware sat idle.

`vm_hwlogger.py::main` writes a 5-second hardware sample to `phase4/logs/hw_{session}.csv`
on every runtime. Raw, that file answers "was the GPU busy at 02:14:35Z" and nothing
else. The question anyone actually asks — *which step is wasting the paid GPU, and would
it run just as well on a free CPU runtime* — needs the samples attributed to the engine
step that was executing, and that join was done AD HOC IN CHAT for
`Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md`. It had to be redone twice: once because
the first pass matched samples against step intervals from ALL concurrently-running VMs
first-hit-wins (the sessions overlap heavily, so a `train` sample could be labelled
`tile` by another VM's log), and once because the dead-sample test read `net_rx_mb_s` and
never `net_tx_mb_s`, counting checkpoint uploads as "nothing happening". A number that
takes two corrections in one afternoon belongs in a script whose output is a tracked CSV
(CLAUDE.md 3.4b), not in a chat transcript.

TWO ATTRIBUTION BASES, and the CSV says which one produced every row. The basis is
decided PER FILE, and a row is keyed `(session, step, basis)` — see `build_rows`.

    marker      The hw CSV carries its own `step` column (schema v2) AND at least one
                row has a non-blank value in it: the sampler read the step marker file
                the engine writes at StepLogger.start() and deletes at finish(). Each
                sample names its OWN step, on its OWN machine. No cross-VM ambiguity is
                possible. This is the basis to trust.

                THE NON-BLANK TEST IS NOT PEDANTRY. Until 2026-09-07 the basis was
                chosen on the mere PRESENCE of the column, and a v2 file whose every
                `step` cell is blank would then publish as 100% `(between)` — "this
                machine ran no engine step at all" — on the TRUSTED tier. Blank cells
                have two causes and the column cannot tell them apart: the VM really was
                between steps, or `pipeline_log.py::StepLogger` never managed to publish
                a marker there (an unwritable directory returns silently, by design).
                A file that never once carried a marker is a file that has demonstrated
                nothing about the marker mechanism, so it drops to `interval` and says
                so in `source_file`. Live example on the day the rule was written:
                `hw_spdc1.csv`, v2 header, 24 samples, every step cell empty.

    interval    Legacy hw CSVs (every file written before the marker landed) have no step
                column, so the only join available is TIME against the step logs — and
                the step LOGS carry no session or host field, so a sample cannot be told
                which VM's step it belongs to. The one archive that DOES pair a session
                with a step — the queue-status ledger, `phase4/qc/*queue_status*.csv`
                (named here, never read: discovery of those files has exactly one home,
                `phase4seg.names.status_files`) — has a populated `session` for only 1
                of the 18 archived hw sessions (of2017k2, 13 rows; the 9 repo-tracked
                copies carry none — measured 2026-09-07). So it cannot rescue the legacy
                archive, but that one session IS an independent per-machine record this
                rule could be validated against. The rule here is deliberately
                conservative: a sample is attributed to step S only when EVERY step
                interval open at that instant normalises to S. When they DISAGREE the
                sample is DROPPED and counted in `ambiguous_dropped` — the correction
                that the first ad-hoc pass lacked. Measured 2026-09-07: 8,304 of the
                29,001 samples in the 12 GPU-bearing sessions drop this way (28.6%;
                19.1% of all 43,453 archived samples). A row on this basis is
                indicative, never verified — see the reader rule below.

READER RULE FOR `interval` ROWS. What survives the ambiguity drop can still belong to
another machine: the six CPU-only sessions in the archive carry 1.9 h of `train` and
0.8 h of `inference` with zero ambiguous drops, because at those instants exactly one
step interval was open — on some OTHER VM. A CPU runtime cannot run torch, so those
labels are provably not that machine's work. The marker basis is what removes this
whole class of error; until a session is logged on v2, its per-step split is a
population-level indication, not a per-machine measurement.

THREE DENOMINATORS, all on the row, because two of them are missing time. The `ALL` row
pools ATTRIBUTED samples only: `samples_parsed` = `ALL.samples` + `ambiguous_dropped`,
so ALL.hours is NOT the session's wall clock and must never be summed as "VM time".
`hours` is SAMPLED time — samples x the file's own measured cadence — so a stalled
logger under-counts it; `span_hours` (last `ts_utc` − first, over that (session, basis)
GROUP's parsed rows — not over the session, which may own two groups) is the covered wall
clock, and `span_hours − hours` is time the logger did not sample at all. Measured 2026-09-07 over
the 18 archived sessions, the three sum to 72.63 h covered / 60.35 h sampled / 48.82 h
attributed: 17% lost to logger gaps, a further 19% of samples to ambiguity. Reading
ALL.hours as the campaign's VM time is therefore a third low.

WHERE THE 17% WENT, and why the number describes the ARCHIVE rather than the writer.
Until 2026-09-08 `vm_hwlogger.py::main` appended to Drive from inside the sampling loop,
so a slow FUSE write stalled sampling: measured on the live pilots the day it was fixed,
hw_spdg.csv had 22.3 min of a 75.1 min span with no samples in it and hw_spdc1.csv 9.6
of 49.9, in gaps one flush-cadence long. The logger now spools locally and mirrors on
its own thread, so files written after that date should show `span_hours` ≈ `hours`;
every file already on the lake still carries the gaps. If the stalls fell in quiet
periods then `nothing_frac` is biased LOW for those files — this instrument would
understate the very effect it measures. Same defect, second symptom: a flush that failed
part way left a TORN row, which `read_hw` now counts and reports as
`rows_dropped_malformed` instead of skipping in silence.

ASSUMPTION, stated because it is not verified: step-log `started:` / `completed:`
timestamps are naive local time on the VM that wrote them, while hw `ts_utc` is stamped
`...Z`. The two are treated as THE SAME CLOCK here, exactly as the existing analysis did.
Colab runtimes run UTC, and the empirical check is that attribution lands sensibly (a
minority of samples fall between steps) rather than degenerating to all-`(between)`,
which is what a multi-hour offset would produce. It is not proof.

WHAT "NOTHING" MEANS, and why it is the finding. `nothing_frac` counts samples where the
GPU is under 5%, the CPU under 15%, local disk under 5 MB/s and BOTH network directions
under 1 MB/s at once. That is not idleness — it is a process blocked on Drive FUSE
per-file latency: `vm_hwlogger.py::cpu_ticks` folds iowait into idle, so blocked-on-I/O
reads as an idle CPU, and the cost is round-trips rather than bytes, so no bandwidth
counter registers it. Schema v2 adds `cpu_iowait_pct` precisely so that blindness is
measurable going forward; `iowait10_frac` is blank for every legacy file, which is
honest, not missing data.

CPU-ONLY SESSIONS ARE KEPT. They log blank GPU columns and would vanish under any
"GPU-bearing sessions only" filter — but they are the offload TARGET, so their cost
profile is exactly what the offload decision needs.

THE `phase` COLUMN (appended 2026-09-07, last position, so no existing column moved).
`(between)` is this table's residual and it is one of the largest buckets §7 reports —
attributable to nothing at all. Some of it is the QUEUE, not an idle machine: this
file's own `spdc1,(between),marker` row is a CPU runtime reading cpu50_frac at zero with
iowait10_frac dominant, which is a machine BLOCKED ON I/O — input staging, before its
first step marker ever opened. That session is live; read the row for the fractions. The marker can now carry a `phase` (`open` / `launching` /
`verifying`; vocabulary owned by `phase4seg/names.py::hw_step_marker_path`), the logger
stamps the cell as `<step>#<phase>`, and `split_step` lands it in its own column. So the
row key is `(session, step, basis, phase)` — one step may legitimately appear on several
rows. Bare steps read `open`; `(between)` and `ALL` rows carry blank, because neither
names a step whose phase could be reported. Nothing writes a non-`open` phase yet: every
row in the current harvest is `open` or blank, and that is a fact about the writers, not
about this reader.

Run:  py -3.12 qc/instruments/harvest_hw_attribution.py [--dry-run]
      py -3.12 qc/instruments/harvest_hw_attribution.py --logs-dir DIR --out FILE
Output: phase4/qc/hw_step_attribution.csv  (schema: docs/SCHEMAS.md)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import heapq
import io
import re
import statistics
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

COLS = ["session", "step", "basis", "gpu_present", "samples", "hours",
        "gpu_busy_frac", "gpu_util_mean", "cpu50_frac", "iowait10_frac",
        "tx1_frac", "rx1_frac", "disk5_frac", "nothing_frac",
        "ambiguous_dropped", "samples_parsed", "span_hours", "source_file",
        "phase"]

BETWEEN = "(between)"
ALL = "ALL"
PHASE_OPEN = "open"

# The logger's cadence (vm_hwlogger.py --interval default). Used only when a file is too
# short to measure its own spacing; every archived file measures 5.0 s exactly.
DEFAULT_SAMPLE_SECONDS = 5.0
MAX_SAMPLE_SECONDS = 300.0        # a longer gap is a stall, not the cadence

# Thresholds. These are the ones §7 of the speedup report was recomputed with; changing
# one changes the meaning of every historical row, so they live here as named constants.
GPU_BUSY_PCT = 5.0
CPU_BUSY_PCT = 50.0
CPU_QUIET_PCT = 15.0
IOWAIT_PCT = 10.0
NET_MB_S = 1.0
DISK_MB_S = 5.0

# `train_2017`, `evaluate_2006s`, `postproc_2019n` -> the step. Year labels are four
# digits plus an optional delivery letter (`2006s`, `2017k`, `2019n`), never bare words,
# so this cannot eat a step name.
_YEAR_SUFFIX = re.compile(r"_\d{4}[a-z0-9]*$")

_STEP_HEAD = re.compile(r"^=== \S+ --step (\S+) ===")
_STARTED = re.compile(r"^started:\s+(\S+)", re.M)
_COMPLETED = re.compile(r"^completed:\s+(\S+)", re.M)


def norm_step(name):
    """Strip the phase suffix and the trailing year label. Blank -> the between bucket.

    The "#phase" comes off FIRST: `train_2017#verifying` must normalise to `train`, and
    the year regex is anchored at the end of the string, so a suffix left in place would
    protect the year label from it and split one step across two rows.
    """
    s = (name or "").strip().split("#", 1)[0].strip()
    if not s:
        return BETWEEN
    return _YEAR_SUFFIX.sub("", s) or BETWEEN


def split_step(name):
    """A marker cell -> (step, phase). See phase4seg/names.py::hw_step_marker_path.

    `vm_hwlogger.py::read_marker` writes the cell as `<step>#<phase>` for any phase but
    `open`, so the step column stays exactly what it always was for engine steps and the
    queue's own time around them is separable rather than pooled into `(between)`.

      train_2017              -> ("train", "open")      an engine step, StepLogger open
      train_2017#launching    -> ("train", "launching") spawned, StepLogger not open yet
      train_2017#verifying    -> ("train", "verifying") engine exited, queue VERIFYing
      "" / "#launching"       -> ("(between)", "")      no step named: no phase to claim

    An unrecognised phase passes through unchanged — this instrument reports what the
    marker said, and a vocabulary check here would silently retire a phase the queue
    had started writing.
    """
    step = norm_step(name)
    if step == BETWEEN:
        return BETWEEN, ""
    _base, _sep, phase = (name or "").strip().partition("#")
    return step, (phase.strip() or PHASE_OPEN)


def _num(v):
    """A hw cell as float, or None. BLANK IS NOT ZERO: the logger writes an empty cell
    when a sampler failed that tick (and for every GPU column on a CPU runtime), and
    reading those as 0 would manufacture idleness that was never measured."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ts(v):
    try:
        return dt.datetime.strptime(str(v).strip(), "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


def session_of(path):
    """hw_{session}.csv -> session; a `_v2` suffix is the schema, not the session."""
    stem = Path(path).name
    if stem.startswith("hw_"):
        stem = stem[3:]
    if stem.endswith(".csv"):
        stem = stem[:-4]
    if stem.endswith("_v2"):
        stem = stem[:-3]
    return stem


def read_hw(path):
    """-> (rows, has_step_column, dropped_malformed).

    TORN ROWS ARE COUNTED, NOT JUST SKIPPED. Until 2026-09-08 the logger's flush ran on
    its sampling thread and could land PART of an append, so the archive carries lines
    that are fragments of a sample: hw_spdg.csv holds one whose `ts_utc` cell reads
    `200.5` and whose `gpu_mem_util_pct` cell reads `train_2017k`. Those are read errors,
    and a silent `continue` reported them as no error at all — 147 of them across the
    lake's hw files, measured 2026-09-08 with this counter's first run.

    Three shapes, all dropped and all counted. A row with MORE cells than the header
    lands its extras under the key None (DictReader's restkey); a SHORT row gets None
    for the fields the line never reached (restval); and a row whose ts_utc is not a
    timestamp cannot be attributed on either basis. Only the third was handled before,
    and the over-long shape is the dangerous one: a fragment followed by a whole row
    carries a perfectly valid ts_utc and used to SURVIVE, contributing a sample whose
    every other reading is another row's cell or a blank.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    rdr = csv.DictReader(text.splitlines())
    has_step = "step" in (rdr.fieldnames or [])
    rows = []
    dropped = 0
    for r in rdr:
        if None in r or any(v is None for v in r.values()):
            dropped += 1                  # wrong arity: a spliced or truncated line
            continue
        t = _ts(r.get("ts_utc"))
        if t is None:
            dropped += 1
            continue
        rows.append({
            "ts": t,
            "gpu": _num(r.get("gpu_util_pct")),
            "cpu": _num(r.get("cpu_pct")),
            "iowait": _num(r.get("cpu_iowait_pct")),
            "dr": _num(r.get("disk_read_mb_s")),
            "dw": _num(r.get("disk_write_mb_s")),
            "rx": _num(r.get("net_rx_mb_s")),
            "tx": _num(r.get("net_tx_mb_s")),
            "step": r.get("step"),
        })
    return rows, has_step, dropped


def read_step_logs(logs_dir):
    """Every completed engine step as (start, end, normalised_step).

    A log with no `completed:` line is a step that died or is still running; it has no
    closed interval, so it contributes nothing rather than an open-ended one that would
    swallow every later sample.
    """
    out = []
    for p in sorted(Path(logs_dir).glob("phase4_semantic_finetune_*.log")):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                head = f.read(4096)
        except OSError:
            continue
        m = _STEP_HEAD.match(head.splitlines()[0] if head else "")
        s, e = _STARTED.search(head), _COMPLETED.search(head)
        if not (m and s and e):
            continue
        try:
            t0 = dt.datetime.fromisoformat(s.group(1))
            t1 = dt.datetime.fromisoformat(e.group(1))
        except ValueError:
            continue
        if t1 < t0:
            continue
        out.append((t0, t1, norm_step(m.group(1))))
    out.sort()
    return out


def attribute_interval(rows, intervals):
    """Sweep the samples against the (global, cross-VM) step intervals.

    -> (list of step-or-None per row, ambiguous_dropped). None = dropped because the
    intervals open at that instant name different steps and the step logs carry no
    session field to break the tie.
    """
    order = sorted(range(len(rows)), key=lambda i: rows[i]["ts"])
    labels = [None] * len(rows)
    active = []                      # heap of (end, step), all with start <= t
    i, dropped = 0, 0
    for idx in order:
        t = rows[idx]["ts"]
        while i < len(intervals) and intervals[i][0] <= t:
            heapq.heappush(active, (intervals[i][1], intervals[i][2]))
            i += 1
        while active and active[0][0] < t:
            heapq.heappop(active)
        names = {step for _end, step in active}
        if not names:
            labels[idx] = BETWEEN
        elif len(names) == 1:
            labels[idx] = names.pop()
        else:
            dropped += 1             # labels[idx] stays None
    return labels, dropped


def _sample_seconds(rows):
    """The file's own cadence, measured. Median of consecutive deltas, ignoring stalls."""
    ts = sorted(r["ts"] for r in rows)
    d = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    d = [x for x in d if 0 < x <= MAX_SAMPLE_SECONDS]
    return statistics.median(d) if d else DEFAULT_SAMPLE_SECONDS


def _f(x):
    return f"{x:.4f}"


def summarise(session, step, basis, rows, secs, dropped, parsed, span_hours,
              source, has_iowait, phase=""):
    """One output row. `rows` may be EMPTY — a session every one of whose samples was
    ambiguity-dropped, or whose file parsed to no samples at all, still gets its ALL
    row, with zero samples and blank fractions, because a table that accounts for paid
    VM time must not silently omit a machine. `hours` is then 0.0000 and `span_hours`
    0.0000: measured zero, not missing."""
    n = len(rows)
    gpu = [r["gpu"] for r in rows if r["gpu"] is not None]
    busy = sum(1 for g in gpu if g > GPU_BUSY_PCT)

    def frac(pred):
        return sum(1 for r in rows if pred(r)) / n

    def nothing(r):
        # The GPU may be BLANK here (a CPU runtime has no readings at all) — that is the
        # one column where absence is informative. Every other counter must have an
        # actual reading before this row can claim nothing was happening; a blank cell
        # is a failed sampler, and unknown is not idle.
        if r["gpu"] is not None and r["gpu"] >= GPU_BUSY_PCT:
            return False
        vals = (r["cpu"], r["dr"], r["dw"], r["rx"], r["tx"])
        if any(v is None for v in vals):
            return False
        return (r["cpu"] < CPU_QUIET_PCT and r["dr"] + r["dw"] < DISK_MB_S
                and r["rx"] < NET_MB_S and r["tx"] < NET_MB_S)

    def pf(pred):
        # No samples -> no fraction. Blank, never 0.0000: an empty row measured nothing.
        return _f(frac(pred)) if n else ""

    return {
        "session": session, "step": step, "basis": basis,
        "gpu_present": _f(len(gpu) / n) if n else "",
        "samples": n,
        "hours": _f(n * secs / 3600.0),
        "gpu_busy_frac": _f(busy / len(gpu)) if gpu else "",
        "gpu_util_mean": _f(sum(gpu) / len(gpu)) if gpu else "",
        "cpu50_frac": pf(lambda r: r["cpu"] is not None and r["cpu"] > CPU_BUSY_PCT),
        "iowait10_frac": (pf(lambda r: r["iowait"] is not None
                              and r["iowait"] > IOWAIT_PCT)
                          if has_iowait else ""),
        "tx1_frac": pf(lambda r: r["tx"] is not None and r["tx"] > NET_MB_S),
        "rx1_frac": pf(lambda r: r["rx"] is not None and r["rx"] > NET_MB_S),
        "disk5_frac": pf(lambda r: r["dr"] is not None and r["dw"] is not None
                         and r["dr"] + r["dw"] > DISK_MB_S),
        "nothing_frac": pf(nothing),
        "ambiguous_dropped": dropped,
        "samples_parsed": parsed,
        "span_hours": _f(span_hours),
        "source_file": source,
        # Last column, appended 2026-09-07: every pre-existing column keeps its index,
        # so a positional reader of the old schema still reads the old fields.
        "phase": phase,
    }


def build_rows(logs_dir, hw_files=None, stats=None):
    """One row per (session, step, BASIS, phase).

    `stats`, when a dict is passed in, is FILLED with counts that belong to the harvest
    rather than to any one row — today just `rows_dropped_malformed`, the torn lines
    read_hw refused. It is an out-parameter and not a column because the number is a
    fact about the reading, not about a machine's step: a session's own accounting is
    already closed by `samples_parsed` = `ALL.samples` + `ambiguous_dropped`, and adding
    a column would move every existing reader's field indices.

    Each FILE is attributed on its own basis. A session that owns both a legacy and a
    v2 file (the logger forks `hw_{s}_v2.csv` rather than append a wider row, so a
    reused session name produces exactly that) emits two independent sets of rows —
    the v2 samples keep their per-machine `step` markers instead of being re-guessed
    by time against another VM's step log, which is what pooling to the weaker basis
    did. `basis` therefore never covers two attribution qualities at once.
    """
    logs_dir = Path(logs_dir)
    files = sorted(hw_files) if hw_files else sorted(logs_dir.glob("hw_*.csv"))
    intervals = None

    groups = {}
    malformed = 0
    for p in files:
        rows, has_step, torn = read_hw(p)
        malformed += torn
        # The column must be present AND used at least once — see the module docstring.
        # A v2 file with nothing but blanks in it has proved nothing about the marker,
        # so it is demoted rather than published as an all-`(between)` machine.
        has_marker = has_step and any((r["step"] or "").strip() for r in rows)
        g = groups.setdefault((session_of(p), "marker" if has_marker else "interval"),
                              {"rows": [], "files": [], "demoted": []})
        g["rows"] += rows
        g["files"].append(Path(p).name)
        if has_step and not has_marker:
            g["demoted"].append(Path(p).name)

    out = []
    for session, basis in sorted(groups):
        g = groups[(session, basis)]
        rows = g["rows"]
        source = ";".join(sorted(g["files"]))
        if g["demoted"]:
            # There is no free-text column on this row, so the demotion rides on
            # source_file — the one cell that already names files. A reader who slices
            # on `basis` alone still gets the right (weaker) tier; this says WHY.
            source += (" [v2 step column present but blank -> interval basis: "
                       + ";".join(sorted(g["demoted"])) + "]")
        secs = _sample_seconds(rows)
        has_iowait = any(r["iowait"] is not None for r in rows)
        ts = [r["ts"] for r in rows]
        # No parseable sample -> no span. max() over an empty sequence raises, and this
        # group is reached precisely because the group is NOT skipped any more.
        span_h = (max(ts) - min(ts)).total_seconds() / 3600.0 if ts else 0.0
        parsed = len(rows)

        if not rows:
            # An unreadable / header-only / all-bad-timestamp file. It gets its ALL row
            # anyway — same rule as the all-ambiguity-dropped case below, for the same
            # reason: a machine that ran is never absent from the table, and "0 samples
            # parsed" is a finding about the logger, not an absence of one. Guarded here
            # rather than inside attribute_interval so an empty group does not pay for a
            # scan of every step log in the lake.
            labels, dropped = [], 0
        elif basis == "marker":
            labels = [split_step(r["step"]) for r in rows]
            dropped = 0
        else:
            if intervals is None:
                intervals = read_step_logs(logs_dir)
            labels, dropped = attribute_interval(rows, intervals)
            # A step LOG records a step that ran, i.e. a StepLogger that opened, so the
            # interval basis can only ever see `open` — the queue's launching/verifying
            # time is precisely what leaves no step log and lands in `(between)` here.
            labels = [lab if lab is None else
                      (lab, "" if lab == BETWEEN else PHASE_OPEN) for lab in labels]

        by_step = {}
        kept = []
        for lab, r in zip(labels, rows):
            if lab is None:
                continue
            by_step.setdefault(lab, []).append(r)
            kept.append(r)
        # Keyed by (step, phase) since 2026-09-07: one step can hold several phases, and
        # pooling them would re-create the blend the phase column exists to separate.
        for step, phase in sorted(by_step):
            out.append(summarise(session, step, basis, by_step[(step, phase)], secs,
                                 dropped, parsed, span_h, source, has_iowait, phase))
        # UNCONDITIONAL. A session whose every sample was ambiguity-dropped has no step
        # rows at all; without this its samples, its drop count and the fact that the
        # machine ran would vanish from the table entirely. Since 2026-09-07 that also
        # covers the zero-PARSED case (`samples_parsed` = 0), which used to `continue`
        # out of the loop above and delete the session from the table outright — the
        # exact omission the ambiguity branch was written to prevent, reached by the
        # other road.
        # The ALL row pools every phase, so it carries none: a blank `phase` on ALL is
        # "not a phase-specific row", the same way its `step` is not a step.
        out.append(summarise(session, ALL, basis, kept, secs, dropped, parsed,
                             span_h, source, has_iowait))
    out.sort(key=lambda r: (r["session"], r["step"], r["basis"], r["phase"]))
    if stats is not None:
        stats["rows_dropped_malformed"] = malformed
    return out


def _logs_dir(explicit=None):
    if explicit:
        return Path(explicit)
    from phase4seg import config
    for cand in (Path(config.BASE) / "phase4" / "logs",
                 Path(r"G:/My Drive/treedata/phase4/logs")):
        if cand.exists():
            return cand
    return cand


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--logs-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    logs_dir = _logs_dir(a.logs_dir)
    if not logs_dir.exists():
        print(f"FATAL: logs not found: {logs_dir}\n"
              f"       this instrument reads the lake — mount it, or pass --logs-dir")
        return 2

    stats = {}
    rows = build_rows(logs_dir, stats=stats)
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    out = Path(a.out) if a.out else (QC / "hw_step_attribution.csv")
    if not a.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(buf.getvalue(), encoding="utf-8", newline="")

    alls = [r for r in rows if r["step"] == ALL]
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} rows over {len(alls)} "
          f"(session, basis) groups → {out.name}")
    # Not a column: a torn line belongs to no session's step. Printed because a rising
    # count is the signature of the writer defect fixed 2026-09-08 (vm_hwlogger.py
    # ::mirror_once) coming back, and a silent skip is how it stayed invisible.
    print(f"  rows_dropped_malformed {stats.get('rows_dropped_malformed', 0)}")
    print(f"  {'session':12} {'basis':9} {'hours':>7} {'span_h':>7} {'gpu?':>6} "
          f"{'nothing':>8} {'ambig':>7}")
    for r in alls:
        print(f"  {r['session']:12} {r['basis']:9} {r['hours']:>7} "
              f"{r['span_hours']:>7} {r['gpu_present']:>6} {r['nothing_frac']:>8} "
              f"{r['ambiguous_dropped']:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

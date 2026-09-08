"""offload_pilot_compare.py — the offload pilot's verdict, read from a file.

WHAT THIS IS FOR. `experiments/offload_pilot_2017k.yaml` pre-registers a decision rule
(2026-09-07, before any launch) that re-runs ONE already-run acquisition — 2017k, tag
`of_2017k`, the whole pipeline on one A100 — as `spd_2017k` split across three Colab
runtimes: CPU-1 does labels+tile, an A100 does train+evaluate+inference, CPU-2 does
postproc. Every READ in that rule (R1 A100-bearing span, R2 checkpoint size, R3 postproc
elapsed, R4 per-step hardware attribution, R5 evaluate AP/AUROC) and both KILL criteria
(K1 a step fails on a CPU runtime, K2 the tile set changes) are numbers that live in five
different homes. This instrument joins them into ONE tracked CSV so the verdict is
written FROM A FILE and not from chat (CLAUDE.md 3.4b).

LONG FORMAT, BASELINE AND PILOT SIDE BY SIDE: one row per (metric, step), the two arms in
two columns, each with its own source column naming the file the number came from.

A TAG IS NOT AN ARM — PIN THE SESSION. The first cut selected an arm's queue rows by
(year, tag) alone. That was true on 2026-09-06 and false on 2026-09-07: after the ledger
recovery (`qc/instruments/rebuild_queue_ledger.py`, whose candidate file every reader now
merges via `names.status_files`), the tag `of_2017k` resolves to rows from THREE launches
— the pre-registered baseline session `of2017k2` (2026-09-06 01:40-03:33, the run that
completed), an earlier 09-06 00:22 launch (`of2017k`) that died on a missing lake file,
and the 09-05 overlap-floor session (`ofB`) where the same arm failed at VERIFY:tile. The
run before this pin landed published tile 9.0 min, labels 6.4 min and a100_span 11.5 min
— every one of them from a FAILED attempt. So each arm carries a PIN:

  --baseline-session / --pilot-sessions   the session id(s) that ARE the arm.
  --baseline-window  / --pilot-window     `START..END`, the fallback for rows whose
                                          `session` column is BLANK.

The window is not belt-and-braces. `rebuild_queue_ledger.py::synthesise` writes
`"session": ""` on every row it reconstructs from a nohup log, and of2017k2's own rows
were erased from the shared `train_queue_status.csv` by a later launch — so today the
baseline exists ONLY as blank-session recovered rows and a session-only pin would select
nothing. A row is admitted when its session matches the pin, OR its session is blank and
its `ts` falls inside the window; `baseline_source`/`pilot_source` say which rule matched
(`session=of2017k2` vs `blank-session, in-window`). Rows the pin refuses are counted and
printed, never dropped silently.

TWO THINGS THE PIN CANNOT REPAIR, both reported rather than papered over:

  · of2017k2's `labels` and `tile` queue rows exist NOWHERE today. The recovery
    synthesises a row only for a (year, tag, step) key that NO snapshot row covers, and
    the failed ofB / of2017k launches had already written `labels` and `tile` rows under
    this tag — so those two were suppressed. Their queue minutes (2.3 / 21.1, in the
    nohup log at `train_queue_nohup_queue_overlap_floor_20260906T014007Z.log`) are
    pre-registered in the yaml and are NOT re-derivable from the ledger. Blank, with the
    mechanism in `note`.
  · A RECOVERED row's `ts` is the engine's `completed:`, not the queue-side start
    (`rebuild_queue_ledger.py`, "TWO PLACES WHERE THE EVIDENCE CONTRADICTS…" §1). The
    span rows below are built on the opposite premise, so when either ENDPOINT of a span
    is a recovered row the span is published BLANK and `note` carries both the mechanism
    and the number it would otherwise have printed. Publishing 41.7 min next to the
    pilot's 67.3 would invert R1 for anyone who read only the value column.

A BLANK PILOT CELL MEANS NOT-YET-MEASURED, NEVER ZERO. Every row is emitted whether or
not the pilot has run; that is the point of running this before the launch as well as
after. The one case a blank would be dishonest is a step that RAN AND FAILED — K1 — so
when a (tag, step) has queue rows but no OK row, the value stays blank and `note` carries
the latest state (`latest state FAIL`). Otherwise K1 would read exactly like "not run".

WHERE EACH NUMBER COMES FROM, and why that home and not another:

  step_minutes      the queue ledger's own `minutes` (state OK), merged across every
                    admissible train_queue_status*.csv via names.status_files, then
                    filtered to the arm's PIN. This is WALL CLOCK as the orchestrator saw
                    it — it includes the engine process's start-up and the queue's own
                    overhead.
  step_elapsed_log  the engine's `elapsed:` line from
                    phase4/logs/phase4_semantic_finetune_<step>_<year>_*.log, matched by
                    the `--run-tag` on its `command:` line and normalised to minutes
                    ("46.4min", "59.2s" and "1.02h" are all written by
                    pipeline_log.StepLogger._write). This is ENGINE time and is the
                    number the yaml's decision rule quotes. The two differ by ~1-3 min
                    per step and neither is wrong; they measure different brackets.
                    THE RUN-TAG IS NOT ENOUGH: the failed 09-05 and 09-06-00:22 attempts
                    also wrote 2017k step logs carrying `--run-tag of_2017k`, so the
                    candidate set is additionally pinned by the log's own `started:`
                    falling inside the arm's window.
  postproc reads    from the pinned postproc step log's stdout, because the verdict needs
                    to know the two arms segmented the SAME CITY and not just at the same
                    speed: `operating_threshold` (the `threshold=0.594 [best_f1_thresh…]`
                    line — the two arms pick their own cut from their own eval report, so
                    this is never assumed equal), `canopy_ha` + `canopy_pct` from the
                    `Canopy: … = 1373.1 ha true (19.1% of imaged area)` line, and
                    `n_polygons` from the GeoPackage line. Two timings come off the ⏱
                    ticks: `polygonize_s`, and `stage_prob_s` — BLANK on the baseline,
                    which had no staging line at all, because staging the probability
                    raster to local scratch is the P4.3 change the pilot runs with.
  machine           WHICH RUNTIME RAN THE STEP — the whole point of the pilot, and the
                    queue does NOT record it. `phase4_train_queue._gpu_line()` prints the
                    tier into the launch HEADER on stdout; the status CSV's columns are
                    job,year,tag,step,state,exit,minutes,detail,ts,host,session — `host`
                    is a container hostname and says nothing about a GPU. So the most
                    reliable field is the RUN MANIFEST's `gpu`, which cli.py fills from
                    nvidia-smi ON THE MACHINE THAT RAN THE STEP and leaves null on a CPU
                    runtime; its tracked view is phase4/qc/run_passport.csv. Two
                    fallbacks, because that view is harvested and will lag the pilot:
                    the per-session heartbeat JSON in the logs dir (`gpu.name`), then the
                    train log's own `Device: cuda  GPU: ...` line. Every row says in
                    `note` which of the three answered.
  a100_span_min     the money lever (R1): first queue ts to last VERIFY* ts over the rows
                    of the GPU-bearing session(s). The queue rewrites a step's row in
                    place RUNNING -> OK keeping the START timestamp
                    (registry_from_manifests.py), so a row's `ts` IS the step's start and
                    no RUNNING row survives a completed run — EXCEPT on a recovered row,
                    where `ts` is the engine's `completed:`. See the endpoint guard above.
  artifact sizes    stat on the lake. MB is decimal (bytes / 1e6), which is what the
                    yaml's 1113.2 / 2368.4 figures and the queue's VERIFY details are.
  tileset_id        phase4/qc/tileset_registry.csv. K2: a CPU-tiled set that does not
                    reproduce a36d6772e88b is a different experiment, not a cheaper one.
  eval_ap/auroc     the arm's OVERALL row of phase4/eval/semantic_eval_report.csv — AND
                    of semantic_eval_report_superseded.csv, which is not optional here:
                    step_evaluate's replace key is (year, channels) and NOT run_tag
                    (core.py, deliberately), so the moment spd_2017k evaluates 2017k/rgb
                    it DISPLACES the of_2017k rows into the superseded file. Reading only
                    the live report would blank the baseline at exactly the moment the
                    comparison became possible.
  hw_* fracs        phase4/qc/hw_step_attribution.csv (harvest_hw_attribution.py). That
                    file keys on (session, step, basis) and carries no run_tag, so the
                    sessions come from the arm's PIN first and the admitted queue rows
                    second. Pin first is load-bearing: every admitted baseline row today
                    has a blank session, so a row-derived session set would be empty and
                    R4 would go blank for the arm whose hardware profile the yaml gates
                    on. Absent file is reported as absent, not as zero.

Run:  py -3.12 qc/instruments/offload_pilot_compare.py [--dry-run]
      py -3.12 qc/instruments/offload_pilot_compare.py --pilot-tag spd_2017k --out FILE
      py -3.12 qc/instruments/offload_pilot_compare.py --baseline-session of2017k2 \
          --baseline-window 2026-09-06T01:40:00..2026-09-06T03:34:00
Output: phase4/qc/offload_pilot_2017k.csv   (schema: docs/SCHEMAS.md)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

COLS = ["metric", "step", "baseline", "pilot", "unit",
        "baseline_source", "pilot_source", "note"]

# The engine's steps, in pipeline order. The order rows are emitted in, too.
STEPS = ["labels", "tile", "train", "evaluate", "inference", "postproc"]

# THE PRE-REGISTERED ARMS, as defaults so the tracked CSV regenerates with no arguments.
# `of2017k2` is the launch experiments/offload_pilot_2017k.yaml pre-registered on
# 2026-09-06 (nohup train_queue_nohup_queue_overlap_floor_20260906T014007Z.log); the
# window brackets it, 01:40:30 -> 03:33:31, with a few seconds of slack either side.
BASELINE_SESSION = "of2017k2"
BASELINE_WINDOW = "2026-09-06T01:40:00..2026-09-06T03:34:00"
# CPU-1 (labels+tile), the A100 (train+evaluate+inference), CPU-2 (postproc).
PILOT_SESSIONS = "spdc1,spdg,spdc2"

_ELAPSED = re.compile(r"^elapsed:\s+([0-9.]+)\s*(min|s|h)\s*$", re.M)
_STARTED = re.compile(r"^started:\s+(\S+)", re.M)
_COMMAND = re.compile(r"^command:\s+(.*)$", re.M)
_RUN_TAG = re.compile(r"--run-tag[=\s]+(\S+)")
# `Device: cuda  GPU: NVIDIA A100-SXM4-40GB` — only step_train prints it.
_DEVICE = re.compile(r"^\s*Device:\s*(\S+)", re.M)

# postproc stdout, anchored on the LABEL and never on the ⏱ glyph: `Polygonizing…` and
# `(vectorized shapely 2.x polygonize)` both contain the word, and only the tick line
# carries the colon-then-seconds.
_THRESHOLD = re.compile(r"threshold=([0-9.]+)")
_CANOPY = re.compile(r"=\s*([0-9.]+)\s*ha true\s*\(\s*([0-9.]+)\s*%\s*of imaged area\s*\)")
_NPOLY = re.compile(r"\(\s*([\d,]+)\s+polygons\s*\)")
_POLYGONIZE_S = re.compile(r"polygonize:\s*([0-9.]+)\s*s\b")
_STAGE_PROB_S = re.compile(r"stage\s+edmonds_canopy_prob_\S+:\s*([0-9.]+)\s*s\b")

_TS = "%Y-%m-%d %H:%M:%S"
# `20260906T014036Z` — run_passport.ts_utc and every run_id's leading field.
_COMPACT_TS = re.compile(r"^(\d{8})T(\d{6})Z?$")
WINDOW_SEP = ".."

# `rebuild_queue_ledger.py::PREFIX`, verbatim. A row carrying it was reconstructed from a
# nohup log and its `ts` is the engine's `completed:`, not the queue-side start.
RECOVERED_PREFIX = "RECOVERED-FROM-LOGS: "


# ── formatting ────────────────────────────────────────────────────────────────

def _f(v, nd):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return ""


def _mb(path):
    """Decimal MB, one decimal — the unit the queue's VERIFY details and the yaml use."""
    try:
        return f"{path.stat().st_size / 1e6:.1f}"
    except OSError:
        return ""


def _elapsed_min(text):
    """`elapsed:` as minutes. StepLogger writes s / min / h and all three appear."""
    m = _ELAPSED.search(text or "")
    if not m:
        return ""
    v, unit = float(m.group(1)), m.group(2)
    if unit == "s":
        v = v / 60.0
    elif unit == "h":
        v = v * 60.0
    return f"{v:.2f}"


# ── the pin ───────────────────────────────────────────────────────────────────

def _dtparse(s):
    """A timestamp from any of the THREE stamp shapes this file joins across.

      ledger `ts`            2026-09-06 02:50:58        (queue_ledger._status_write)
      step log `started:`    2026-09-06T02:04:35.961159 (pipeline_log.StepLogger._write)
      passport `ts_utc`      20260906T014036Z           (the run_id's leading field)

    All three are UTC on the same clock — measured: run_id 20260906T014036Z_…_labels and
    ledger row `labels … 2026-09-06 01:40:30` are the same step — so one window compares
    against all three. Returns None on anything it cannot read; every caller treats that
    as "not in the window" rather than guessing.
    """
    t = str(s or "").strip()
    if not t:
        return None
    m = _COMPACT_TS.match(t)
    if m:
        try:
            return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            return None
    try:
        return dt.datetime.strptime(t.replace("T", " ")[:19], _TS)
    except (TypeError, ValueError):
        return None


def parse_window(spec):
    """`START..END` -> (datetime, datetime), inclusive at both ends. None for blank."""
    t = str(spec or "").strip()
    if not t:
        return None
    if WINDOW_SEP not in t:
        raise SystemExit(f"--*-window wants START{WINDOW_SEP}END, got {spec!r}")
    lo, hi = (x.strip() for x in t.split(WINDOW_SEP, 1))
    a, b = _dtparse(lo), _dtparse(hi)
    if a is None or b is None:
        raise SystemExit(f"--*-window: unreadable timestamp in {spec!r}")
    if b < a:
        raise SystemExit(f"--*-window: END is before START in {spec!r}")
    return a, b


class Pin:
    """WHICH ROWS OF A TAG ARE THIS ARM — a session set plus a blank-session window.

    A tag is not an arm (see the module docstring): `of_2017k` names three launches, two
    of which failed. The pin is what separates them, and it has to survive the shape the
    ledger is actually in — recovered rows carry `session=""`
    (`rebuild_queue_ledger.py::synthesise`), so a session-only pin would select nothing
    for the very arm the yaml pre-registered.

    admits(row) -> (bool, rule). The RULE is carried into `baseline_source` /
    `pilot_source` so a reader can see which of the two tests let a row in, and the
    refusals are counted so a pin that is too tight is visible rather than silent.

    An EMPTY pin (no sessions, no window) admits everything — that is the pre-pin
    behaviour, kept so `--baseline-session ""` is a real escape hatch.
    """

    def __init__(self, sessions=(), window=None):
        seen, keep = set(), []
        for s in sessions:
            s = str(s).strip()
            if s and s not in seen:
                seen.add(s)
                keep.append(s)
        self.sessions = tuple(keep)
        self.window = window

    @property
    def empty(self):
        return not self.sessions and self.window is None

    def describe(self):
        bits = []
        if self.sessions:
            bits.append("session" + ("s" if len(self.sessions) > 1 else "")
                        + "=" + ",".join(self.sessions))
        if self.window:
            bits.append("window=" + WINDOW_SEP.join(
                t.strftime("%Y-%m-%dT%H:%M:%S") for t in self.window))
        return " ".join(bits) if bits else "none (every row of the tag)"

    def in_window(self, stamp):
        """True when `stamp` (any of the three shapes) falls inside the window."""
        if self.window is None:
            return False
        t = _dtparse(stamp)
        return t is not None and self.window[0] <= t <= self.window[1]

    def admits(self, row):
        sess = str(row.get("session") or "").strip()
        if sess:
            if not self.sessions or sess in self.sessions:
                return True, f"session={sess}"
            return False, f"session={sess} is not this arm"
        if self.window is None:
            # An empty pin keeps the pre-pin behaviour exactly, blank rule and all, so
            # `--baseline-session ""` reproduces what this file published before.
            return ((True, "") if self.empty
                    else (False, "blank session and no window to fall back on"))
        if _dtparse(row.get("ts")) is None:
            return False, "blank session and an unreadable ts"
        if self.in_window(row.get("ts")):
            return True, "blank-session, in-window"
        return False, "blank session, ts outside the window"


# ── the homes ─────────────────────────────────────────────────────────────────

def _lake(explicit, attr):
    """A lake directory: the override, else lake.py — THE one home for lake paths."""
    if explicit:
        return Path(explicit)
    import lake

    return getattr(lake, attr)


def queue_rows(status_dir, year, tag, pin=None):
    """(admitted rows, refusals by rule, refusals by step) for (year, tag), PIN-filtered.

    Discovery goes through names.status_files, never a raw glob: a renamed-aside file
    escapes the underscore pattern but not the naive one (names.py records the 2026-08-29
    case where a "quarantined" fixture kept being ingested by five readers).

    (year, tag) is the DISCOVERY key and the pin is the IDENTITY key. Keeping them apart
    is the whole point: the merge has to read every file that might hold the arm's rows,
    and then it has to throw away the two failed launches that share the arm's tag.

    The by-STEP refusal count is what lets a blank cell say WHICH kind of blank it is.
    "No admitted row and none refused either" is a step that never ran; "no admitted row
    but three refused" is a step whose only surviving rows belong to another launch —
    which is exactly the state of the baseline's `labels` and `tile` today.
    """
    from phase4seg.names import status_files

    pin = pin if pin is not None else Pin()
    out, refused, refused_steps = [], Counter(), Counter()
    for p in status_files(status_dir):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, r in enumerate(csv.DictReader(text.splitlines())):
            if str(r.get("year") or "") != str(year):
                continue
            if str(r.get("tag") or "") != str(tag):
                continue
            ok, rule = pin.admits(r)
            if not ok:
                refused[rule] += 1
                refused_steps[str(r.get("step") or "")] += 1
                continue
            r["_file"], r["_idx"], r["_rule"] = p.name, i, rule
            out.append(r)
    out.sort(key=lambda r: (str(r.get("ts") or ""), r["_file"], r["_idx"]))
    return out, refused, refused_steps


def _is_recovered(row):
    """A row `rebuild_queue_ledger.py` reconstructed from a nohup log, by its own marker.

    Matters because such a row's `ts` is the engine's `completed:` and the span rows are
    built on `ts` being the queue-side START.
    """
    return str(row.get("detail") or "").startswith(RECOVERED_PREFIX)


def _src(row):
    """`<file> <the pin rule that admitted it>` — never just the file.

    Which rule matched is the difference between "this is the pre-registered session" and
    "this is a blank-session row I took on trust from a time window", and a reader of the
    CSV alone has no other way to tell.
    """
    rule = str(row.get("_rule") or "").strip()
    if not rule:
        sess = str(row.get("session") or "").strip()
        rule = f"session={sess}" if sess else ""
    return f"{row['_file']} {rule}".strip()


def _base_step(row):
    """`VERIFY:train` -> `train`; a bare `VERIFY` closes the JOB, not a step."""
    s = str(row.get("step") or "")
    if s.startswith("VERIFY:"):
        return s.split(":", 1)[1]
    return "" if s == "VERIFY" else s


def step_minutes(rows, step, refused_steps=None):
    """(value, source, note) — the LATEST OK row's `minutes`, or a blank that says why.

    THREE KINDS OF BLANK, and the note is the only thing that separates them:
      · K1 — the step ran and FAILED: `latest state FAIL`.
      · the step's only rows belong to ANOTHER LAUNCH under the same tag, so the pin
        refused them and this arm's own row does not survive. Measured on the baseline's
        labels/tile: the ledger recovery synthesises a row only for a key NO snapshot row
        covers, and the two failed launches had already written rows under those keys, so
        of2017k2's were suppressed. Their minutes (2.3 / 21.1) live in the nohup log and
        in the yaml, and are not re-derivable from the ledger.
      · nothing at all — the step never ran.
    """
    hits = [r for r in rows if str(r.get("step") or "") == step]
    ok = [r for r in hits if str(r.get("state") or "") == "OK"
          and str(r.get("minutes") or "").strip()]
    if ok:
        return _f(ok[-1].get("minutes"), 1), _src(ok[-1]), ""
    if hits:
        return "", _src(hits[-1]), f"latest state {hits[-1].get('state') or '?'}"
    n = (refused_steps or {}).get(step, 0)
    if n:
        return "", "", (f"NO SURVIVING ROW under this arm's pin — {n} row(s) for this "
                        "step carry the tag but belong to another launch and were "
                        "refused; the step is not known to have been skipped")
    return "", "", ""


def step_logs(logs_dir, year, tag, pin=None):
    """{step: (name, text)} — the LATEST log per step whose `--run-tag` equals `tag` AND
    whose `started:` falls inside the pin's window.

    Equality, not `in`, on the tag: `of_2017k` must not match a hypothetical `of_2017k_b`.

    THE TAG ALONE PICKS THE WRONG LOG. The two failed attempts under this tag wrote their
    own 2017k step logs with the same `--run-tag of_2017k` — measured, 09-05T15-08/15-13
    and 09-06T00-37 — so "latest by started:" is only right by accident and stops being
    right the moment a later failed retry lands. The window is the same one that pins the
    queue rows, applied to the log's OWN clock. (The FILENAME stamp is `completed:`, not
    `started:` — measured: `…train_2017k_2026-09-06T02-50.log` started 02:04:35 — so the
    `started:` line is read, never the name.)
    """
    pin = pin if pin is not None else Pin()
    out = {}
    for step in STEPS:
        cands = []
        for p in sorted(Path(logs_dir).glob(
                f"phase4_semantic_finetune_{step}_{year}_*.log")):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            cmd = _COMMAND.search(text)
            m = _RUN_TAG.search(cmd.group(1)) if cmd else None
            if not m or m.group(1) != str(tag):
                continue
            st = _STARTED.search(text)
            started = st.group(1) if st else ""
            if pin.window is not None and not pin.in_window(started):
                continue
            cands.append((started, p.name, text))
        if cands:
            cands.sort(key=lambda c: (c[0], c[1]))
            out[step] = (cands[-1][1], cands[-1][2])
    return out


def postproc_metrics(text):
    """{name: value} the postproc step log printed. Missing keys stay OUT of the dict.

    Anchored on the label text, never on the ⏱ glyph: `Polygonizing…` and
    `(vectorized shapely 2.x polygonize)` both carry the word `polygonize` and neither is
    a measurement. `n_polygons` arrives thousands-separated (`45,532 polygons`) and is
    stored bare so the column is arithmetic. `stage_prob_s` is absent by design on an arm
    that read the probability raster straight off FUSE, which is what BLANK means here.
    """
    out = {}
    t = text or ""
    m = _THRESHOLD.search(t)
    if m:
        out["operating_threshold"] = m.group(1)
    m = _CANOPY.search(t)
    if m:
        out["canopy_ha"], out["canopy_pct"] = m.group(1), m.group(2)
    m = _NPOLY.search(t)
    if m:
        out["n_polygons"] = m.group(1).replace(",", "")
    m = _POLYGONIZE_S.search(t)
    if m:
        out["polygonize_s"] = m.group(1)
    m = _STAGE_PROB_S.search(t)
    if m:
        out["stage_prob_s"] = m.group(1)
    return out


def passport_gpu(passport_csv, tag, pin=None):
    """{step: (gpu, run_id)} from the tracked run_passport view of the run manifests.

    Window-pinned on `ts_utc` for the same reason the step logs are: the failed launches
    wrote manifests under this tag too (measured: 20260905T150242Z and 20260906T002902Z
    sit in run_passport.csv alongside the baseline's). Latest-ts-wins happens to pick the
    right row today; it would stop doing so the first time a failed retry ran last.
    """
    p = Path(passport_csv)
    if not p.exists():
        return {}
    pin = pin if pin is not None else Pin()
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    best = {}
    for r in csv.DictReader(text.splitlines()):
        if str(r.get("run_tag") or "") != str(tag):
            continue
        if pin.window is not None and not pin.in_window(r.get("ts_utc")):
            continue
        step = str(r.get("step") or "")
        key = (str(r.get("ts_utc") or ""), str(r.get("run_id") or ""))
        if step not in best or key > best[step][0]:
            best[step] = (key, str(r.get("gpu") or "").strip(),
                          str(r.get("run_id") or ""))
    return {s: (v[1], v[2]) for s, v in best.items()}


def heartbeat_gpu(logs_dir):
    """{session: gpu_name} from phase4/logs/heartbeat_<session>.json.

    Per VM by construction, which is what makes it the fallback that populates BEFORE
    the tracked run_passport view has been re-harvested.
    """
    out = {}
    for p in sorted(Path(logs_dir).glob("heartbeat_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        sess = str(d.get("session") or p.stem[len("heartbeat_"):])
        gpu = d.get("gpu")
        name = (gpu or {}).get("name") if isinstance(gpu, dict) else gpu
        out[sess] = str(name or "").strip()
    return out


def _is_gpu(name):
    """A CUDA device by name. Blank / `none (CPU runtime...)` is a CPU runtime."""
    n = str(name or "").strip().lower()
    return bool(n) and not n.startswith("none") and not n.startswith("unknown")


def step_session(rows, step, pin=None):
    """The session that ran this step — from its rows, else from the PIN.

    The fallback is not cosmetic: every admitted baseline row today carries a blank
    session, so without it the heartbeat basis (the one that populates before
    run_passport.csv is re-harvested) would have no session to look up and the machine
    column would go blank on the arm the pin exists to name. Only usable when the pin
    names ONE session — with three, which one ran a given step is exactly the unknown.
    """
    hits = [r for r in rows
            if _base_step(r) == step and str(r.get("session") or "").strip()]
    if hits:
        return str(hits[-1].get("session")).strip()
    if pin is not None and len(pin.sessions) == 1:
        return pin.sessions[0]
    return ""


def machine(step, rows, passport, hearts, logs, pin=None):
    """(value, source, note) — GPU or CPU, and which field answered."""
    if step in passport:
        gpu, run_id = passport[step]
        return ("GPU" if _is_gpu(gpu) else "CPU",
                f"run_passport.csv {run_id}",
                f"basis run_passport.gpu={gpu or '(null)'}")
    sess = step_session(rows, step, pin)
    if sess and sess in hearts:
        return ("GPU" if _is_gpu(hearts[sess]) else "CPU",
                f"heartbeat_{sess}.json",
                f"basis heartbeat gpu.name={hearts[sess] or '(blank)'}")
    if step in logs:
        m = _DEVICE.search(logs[step][1])
        if m:
            dev = m.group(1)
            return ("GPU" if dev.lower().startswith("cuda") else "CPU",
                    logs[step][0], f"basis step log Device: {dev}")
    return "", "", ""


def _span_of(slice_):
    """(minutes, note_tail, start_row, end_row) over `[(row, ts), …]`, VERIFY* preferred
    as the closing stamp — the one place both span rows agree on their arithmetic."""
    start_row, start = min(slice_, key=lambda rt: rt[1])
    verify = [(r, t) for r, t in slice_ if str(r.get("step") or "").startswith("VERIFY")]
    end_row, end = max(verify or slice_, key=lambda rt: rt[1])
    tail = ("first ts to last VERIFY* ts" if verify else "no VERIFY row — last ts used")
    return (end - start).total_seconds() / 60.0, tail, start_row, end_row


def _endpoint_guard(minutes, tail, start_row, end_row, n_recovered):
    """('' or the value, note) — a span whose ENDPOINT is a recovered row is not published.

    A recovered row's `ts` is the engine's `completed:`, not the queue-side start
    (`rebuild_queue_ledger.py`, §1 of "TWO PLACES WHERE THE EVIDENCE CONTRADICTS…"), so a
    span that opens or closes on one measures something other than what its name says.
    Measured on the baseline: the surviving rows give 02:50:58→03:32:42 = 41.7 min, where
    the session itself ran 01:40:30→03:33:31 = 113.0 — off by a factor of 2.7, and in the
    direction that would make the pilot's 67.3 look like a REGRESSION rather than a win.
    The would-be number stays in `note`, because hiding it entirely just invites someone
    to recompute it by hand from the same rows.
    """
    bad = [w for w, r in (("opens", start_row), ("closes", end_row)) if _is_recovered(r)]
    if not bad:
        note = tail
        if n_recovered:
            note += (f"; {n_recovered} interior row(s) are RECOVERED-FROM-LOGS "
                     "(ts=engine-completed) but neither endpoint is")
        return _f(minutes, 1), note
    return "", (
        f"NOT PUBLISHED: the span {' and '.join(bad)} on a RECOVERED-FROM-LOGS row, whose "
        f"ts is the engine's `completed:` and not the queue-side start "
        f"(rebuild_queue_ledger.py) — {tail} over the surviving rows would read "
        f"{_f(minutes, 1)} min, which is a LOWER BOUND on the real span, not the span")


def spans(rows, machines, pin=None):
    """(a100_span, a100_source, a100_note, total_span, total_source, total_note).

    The GPU slice is chosen at SESSION level when the rows name a session — that is what
    the pilot's split IS, one runtime per slice — falls back to the PIN's sessions when
    the rows are blank-session recovered ones, and to the per-step machine after that.
    """
    stamped = [(r, _dtparse(r.get("ts"))) for r in rows]
    stamped = [(r, t) for r, t in stamped if t]
    if not stamped:
        return "", "", "", "", "", ""
    # The TOTAL is plain first-ts to last-ts over every admitted row — no VERIFY
    # preference, because it is the arm's whole wall clock and not a step bracket.
    n_rec = sum(1 for r, _ in stamped if _is_recovered(r))
    tstart, t0 = min(stamped, key=lambda rt: rt[1])
    tend, t1 = max(stamped, key=lambda rt: rt[1])
    total, total_note = _endpoint_guard((t1 - t0).total_seconds() / 60.0,
                                        "first ts to last ts", tstart, tend, n_rec)
    total_src = f"{len(stamped)} rows, {stamped[0][0]['_file']}"

    gpu_steps = {s for s in STEPS if machines.get(s) == "GPU"}
    if not gpu_steps:
        return "", "", "no step resolved to a GPU runtime", total, total_src, total_note
    sessions = sorted({str(r.get("session") or "").strip() for r, _ in stamped
                       if _base_step(r) in gpu_steps
                       and str(r.get("session") or "").strip()})
    if sessions:
        slice_ = [(r, t) for r, t in stamped
                  if str(r.get("session") or "").strip() in sessions]
        who = "session " + ",".join(sessions)
    elif pin is not None and len(pin.sessions) == 1:
        slice_ = [(r, t) for r, t in stamped if _base_step(r) in gpu_steps]
        who = (f"session {pin.sessions[0]} (pinned; the admitted rows carry no session "
               "of their own)")
    else:
        slice_ = [(r, t) for r, t in stamped if _base_step(r) in gpu_steps]
        who = "steps " + ",".join(sorted(gpu_steps)) + " (rows carry no session)"
    if not slice_:
        return "", "", "no rows in the GPU slice", total, total_src, total_note
    smin, stail, sstart, send = _span_of(slice_)
    n_rec_slice = sum(1 for r, _ in slice_ if _is_recovered(r))
    value, note = _endpoint_guard(smin, stail, sstart, send, n_rec_slice)
    note = f"{who}; {note}"
    if any(str(r.get("state") or "") == "RUNNING" for r, _ in slice_):
        note += "; a row is still RUNNING — in progress"
    return (value, f"{len(slice_)} rows, {slice_[0][0]['_file']}", note,
            total, total_src, total_note)


def tileset(registry_csv, year, tag):
    """(tileset_id, n_tiles, source) from the tracked tile-set registry."""
    p = Path(registry_csv)
    if not p.exists():
        return "", "", ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", "", ""
    hits = [r for r in csv.DictReader(text.splitlines())
            if str(r.get("label") or "") == str(year)
            and str(r.get("run_tag") or "") == str(tag)]
    if not hits:
        return "", "", ""
    return (str(hits[-1].get("tileset_id") or ""),
            str(hits[-1].get("n_tiles") or ""), p.name)


def eval_row(eval_csv, year, tag):
    """(row, source) — the arm's OVERALL eval row, live report OR superseded archive.

    Both, because step_evaluate's replace key is (year, channels): the pilot evaluating
    2017k/rgb moves the baseline's rows into the archive.
    """
    live = Path(eval_csv)
    cands = []
    for p in (live, live.with_name("semantic_eval_report_superseded.csv")):
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for r in csv.DictReader(text.splitlines()):
            if (str(r.get("year") or "") == str(year)
                    and str(r.get("scope") or "") == "OVERALL"
                    and str(r.get("run_tag") or "").strip() == str(tag)):
                cands.append((str(r.get("written_utc") or ""), p.name, r))
    if not cands:
        return None, ""
    cands.sort(key=lambda c: (c[0], c[1]))
    return cands[-1][2], cands[-1][1]


def hw_rows(hw_csv, sessions):
    """{step: row} for the sessions this tag ran on. Marker basis wins over interval.

    None (not {}) when the file is absent, so the caller can say "absent" rather than
    publishing a blank that reads like a measured zero.

    NO SESSIONS MEANS NO ROWS, never every row. The first cut wrote
    `if sessions and session not in sessions`, so an arm that had not run — empty session
    set — matched EVERY session in the archive and the pilot column came back full of
    another campaign's numbers while the pilot had zero queue rows. A blank pilot cell is
    the whole contract of this file.

    ONLY ENGINE-STEP ROWS. Since the marker gained a `phase`, that file is one row per
    (session, step, basis, phase) — one step legitimately owns several rows, and
    harvest_hw_attribution.py::build_rows sorts them launching < open < verifying. This
    dict keys on the step alone and keeps the LAST row at equal basis rank, so without
    the filter below a one-sample VERIFY window would be published as the step's
    hardware profile. A row with no `phase` column at all reads as "" and is kept, so
    the pre-phase files still parse.
    """
    p = Path(hw_csv)
    if not p.exists():
        return None
    if not sessions:
        return {}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rank = {"marker": 2, "interval": 1}
    out = {}
    for r in csv.DictReader(text.splitlines()):
        if str(r.get("session") or "") not in sessions:
            continue
        if str(r.get("phase") or "") not in ("open", ""):
            continue
        key = str(r.get("step") or "")
        prev = out.get(key)
        if prev is None or (rank.get(str(r.get("basis")), 0)
                            >= rank.get(str(prev.get("basis")), 0)):
            out[key] = r
    return out


# ── the table ─────────────────────────────────────────────────────────────────

class Arm:
    """Everything one tag's side of the comparison needs, read once."""

    def __init__(self, year, tag, status_dir, logs_dir, models_dir, masks_dir,
                 registry_csv, eval_csv, passport_csv, hw_csv, pin=None):
        self.tag = tag
        self.pin = pin if pin is not None else Pin()
        self.rows, self.refused, self.refused_steps = queue_rows(
            status_dir, year, tag, self.pin)
        self.logs = step_logs(logs_dir, year, tag, self.pin)
        self.post = postproc_metrics(
            self.logs["postproc"][1] if "postproc" in self.logs else "")
        self.post_src = self.logs["postproc"][0] if "postproc" in self.logs else ""
        self.passport = passport_gpu(passport_csv, tag, self.pin)
        self.hearts = heartbeat_gpu(logs_dir)
        self.machines, self.machine_src, self.machine_note = {}, {}, {}
        for s in STEPS:
            v, src, note = machine(s, self.rows, self.passport, self.hearts, self.logs,
                                   self.pin)
            self.machines[s], self.machine_src[s], self.machine_note[s] = v, src, note
        (self.a100_span, self.a100_src, self.a100_note,
         self.total_span, self.total_src, self.total_note) = spans(
            self.rows, self.machines, self.pin)
        self.sizes = {
            "sem_best_mb": Path(models_dir) / f"sem_best_{year}_{tag}.pt",
            "prob_raster_mb": Path(masks_dir) / f"edmonds_canopy_prob_{year}_{tag}.tif",
            "mask_mb": Path(masks_dir) / f"edmonds_canopy_mask_{year}_{tag}.tif",
            "gpkg_mb": Path(masks_dir) / f"edmonds_canopy_mask_{year}_{tag}.gpkg",
        }
        self.tileset_id, self.n_tiles, self.tileset_src = tileset(
            registry_csv, year, tag)
        self.eval, self.eval_src = eval_row(eval_csv, year, tag)
        # PIN FIRST, rows second — but ONLY for an arm that has queue rows at all.
        # Pin first, because every admitted baseline row carries a blank session today,
        # so a row-derived set would be empty and hw_rows would return {}: R4 blank for
        # the arm the yaml gates on, with nothing on the face of the file to say why.
        # Gated on `self.rows`, because a pin is an assertion about an arm and an arm
        # with ZERO admitted rows has not run — letting its named sessions through would
        # rebuild exactly the leak hw_rows' docstring records, this time via the pin.
        seen = [s for s in sorted({str(r.get("session") or "").strip()
                                   for r in self.rows}) if s]
        self.sessions = ([] if not self.rows else
                         list(self.pin.sessions)
                         + [s for s in seen if s not in self.pin.sessions])
        self.hw = hw_rows(hw_csv, set(self.sessions))


def _both(base_note, pilot_note):
    return "; ".join(x for x in (f"baseline {base_note}" if base_note else "",
                                 f"pilot {pilot_note}" if pilot_note else "") if x)


def build_rows(base, pilot):
    """The long table. Every row is emitted for both arms, blank where unmeasured."""
    out = []

    def add(metric, step, b, p, unit, bsrc="", psrc="", note=""):
        out.append({"metric": metric, "step": step, "baseline": b, "pilot": p,
                    "unit": unit, "baseline_source": bsrc, "pilot_source": psrc,
                    "note": note})

    # 1 — the orchestrator's wall clock per step
    for s in STEPS:
        bv, bsrc, bnote = step_minutes(base.rows, s, base.refused_steps)
        pv, psrc, pnote = step_minutes(pilot.rows, s, pilot.refused_steps)
        add("step_minutes", s, bv, pv, "min", bsrc, psrc, _both(bnote, pnote))

    # 2 — the engine's own elapsed, which is what the decision rule quotes
    for s in STEPS:
        add("step_elapsed_log", s,
            _elapsed_min(base.logs[s][1]) if s in base.logs else "",
            _elapsed_min(pilot.logs[s][1]) if s in pilot.logs else "",
            "min",
            base.logs[s][0] if s in base.logs else "",
            pilot.logs[s][0] if s in pilot.logs else "",
            "engine time, `elapsed:` normalised to minutes")

    # 3 — which runtime ran it
    for s in STEPS:
        add("machine", s, base.machines[s], pilot.machines[s], "GPU|CPU",
            base.machine_src[s], pilot.machine_src[s],
            _both(base.machine_note[s], pilot.machine_note[s]))

    # 4 — R1, the money lever, and the wall clock the yaml says will get worse
    add("a100_span_min", "", base.a100_span, pilot.a100_span, "min",
        base.a100_src, pilot.a100_src, _both(base.a100_note, pilot.a100_note))
    add("total_span_min", "", base.total_span, pilot.total_span, "min",
        base.total_src, pilot.total_src,
        "all admitted rows of the arm; the pilot's is EXPECTED to exceed the "
        "baseline's (three bootstraps in sequence) — see the yaml. "
        + _both(base.total_note, pilot.total_note))

    # 5 — R2 and R3's artifacts
    for metric, step in (("sem_best_mb", "train"), ("prob_raster_mb", "inference"),
                         ("mask_mb", "postproc"), ("gpkg_mb", "postproc")):
        bp, pp = base.sizes[metric], pilot.sizes[metric]
        add(metric, step, _mb(bp), _mb(pp), "MB (bytes/1e6)", bp.name, pp.name,
            "stat on the lake; blank = the file is not there")

    # 5b — WHAT POSTPROC ACTUALLY PRODUCED. R3 is an elapsed time, but a cheaper postproc
    # that segmented a different city is not a win, and the two arms pick their operating
    # threshold independently (each from its OWN eval report) — so the cut, the canopy it
    # produced and the polygon count are read, not assumed equal.
    for metric, unit, note in (
            ("operating_threshold", "prob",
             "each arm's own best_f1_thresh, read from ITS eval report — never assumed "
             "equal across arms"),
            ("canopy_pct", "% of imaged area", "of the imaged area, as postproc printed"),
            ("canopy_ha", "ha", "true-area hectares, as postproc printed"),
            ("n_polygons", "polygons", "the GeoPackage's polygon count"),
            ("polygonize_s", "s", "the ⏱ polygonize tick"),
            ("stage_prob_s", "s",
             "the ⏱ tick for staging the probability raster to local scratch — BLANK "
             "means the arm printed no staging line at all (it read the raster over "
             "FUSE), which is the P4.3 difference between these two arms, not a "
             "missing measurement")):
        add(metric, "postproc", base.post.get(metric, ""), pilot.post.get(metric, ""),
            unit, base.post_src, pilot.post_src, note)

    # 6 — K2
    add("tileset_id", "tile", base.tileset_id, pilot.tileset_id, "id",
        base.tileset_src, pilot.tileset_src, "")
    add("n_tiles", "tile", base.n_tiles, pilot.n_tiles, "tiles",
        base.tileset_src, pilot.tileset_src, "")
    if base.tileset_id and pilot.tileset_id:
        note = ("MATCH — K2 satisfied: CPU tiling reproduced the GPU-tiled set"
                if base.tileset_id == pilot.tileset_id else
                "DIFF — K2 FIRES: the pilot tiled a different set, which is a different "
                "experiment and not a cheaper one")
    else:
        note = ("pilot not tiled yet — or tileset_registry.csv has not been "
                "re-harvested (qc/instruments/harvest_tilesets.py)")
    add("tileset_id_match", "tile", base.tileset_id, pilot.tileset_id, "id",
        base.tileset_src, pilot.tileset_src, note)

    # 7 — R5, reported and NOT gated
    for metric, col in (("eval_ap", "ap"), ("eval_auroc", "auroc")):
        add(metric, "evaluate",
            _f((base.eval or {}).get(col), 4) if base.eval else "",
            _f((pilot.eval or {}).get(col), 4) if pilot.eval else "",
            "fraction (4dp)", base.eval_src, pilot.eval_src,
            "OVERALL row, held-out test; R5 is REPORTED, not gated")

    # 8 — R4, the first marker-basis attribution
    absent = base.hw is None and pilot.hw is None
    for metric, col in (("hw_nothing_frac", "nothing_frac"),
                        ("hw_gpu_busy_frac", "gpu_busy_frac")):
        for s in STEPS:
            br = (base.hw or {}).get(s)
            pr = (pilot.hw or {}).get(s)
            add(metric, s,
                str(br.get(col) or "") if br else "",
                str(pr.get(col) or "") if pr else "",
                "fraction",
                f"{br.get('source_file')} basis={br.get('basis')}" if br else "",
                f"{pr.get('source_file')} basis={pr.get('basis')}" if pr else "",
                "hw_step_attribution.csv absent" if absent
                else "sessions from the arm's PIN first, then its admitted queue rows "
                     "(the file carries no run_tag); every admitted baseline row has a "
                     "blank session, so the pin is what supplies the join key")
    return out


def _table(rows, base_tag, pilot_tag):
    wm = max(len(r["metric"]) for r in rows)
    ws = max(len(r["step"]) for r in rows)
    wb = max(len(base_tag), max(len(r["baseline"]) for r in rows))
    wp = max(len(pilot_tag), max(len(r["pilot"]) for r in rows))
    head = (f"  {'metric':<{wm}}  {'step':<{ws}}  {base_tag:>{wb}}  "
            f"{pilot_tag:>{wp}}  unit")
    lines = [head, "  " + "-" * (len(head) - 2)]
    for r in rows:
        lines.append(f"  {r['metric']:<{wm}}  {r['step']:<{ws}}  "
                     f"{r['baseline']:>{wb}}  {r['pilot']:>{wp}}  {r['unit']}")
    return "\n".join(lines)


def main(argv=None):
    from phase4seg.names import clean_argv

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", default="2017k")
    ap.add_argument("--baseline-tag", default="of_2017k")
    ap.add_argument("--pilot-tag", default="spd_2017k")
    ap.add_argument("--baseline-session", default=BASELINE_SESSION,
                    help="the session id that IS the baseline arm; the tag alone names "
                         "three launches, two of which failed. '' disables the pin.")
    ap.add_argument("--pilot-sessions", default=PILOT_SESSIONS,
                    help="comma-separated; the pilot is one arm across three runtimes")
    ap.add_argument("--baseline-window", default=BASELINE_WINDOW,
                    help="START..END; admits rows whose `session` column is BLANK, which "
                         "is every row rebuild_queue_ledger.py reconstructed. '' "
                         "disables the fallback.")
    ap.add_argument("--pilot-window", default="",
                    help="START..END; same fallback for the pilot. Empty by default: the "
                         "pilot's rows were written by the queue and carry their own "
                         "session, so nothing is guessed unless asked for.")
    ap.add_argument("--out", default=None)
    ap.add_argument("--status-dir", default=None, help="lake phase4/qc (the ledger)")
    ap.add_argument("--logs-dir", default=None, help="lake phase4/logs")
    ap.add_argument("--models-dir", default=None, help="lake phase4/models")
    ap.add_argument("--masks-dir", default=None, help="lake phase4/masks")
    ap.add_argument("--tileset-registry", default=None,
                    help="default phase4/qc/tileset_registry.csv (tracked)")
    ap.add_argument("--eval-report", default=None,
                    help="default lake phase4/eval/semantic_eval_report.csv")
    ap.add_argument("--run-passport", default=None,
                    help="default phase4/qc/run_passport.csv (tracked)")
    ap.add_argument("--hw-attribution", default=None,
                    help="default phase4/qc/hw_step_attribution.csv (tracked)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    status_dir = _lake(a.status_dir, "QC_DIR")
    logs_dir = _lake(a.logs_dir, "LOGS_DIR")
    models_dir = _lake(a.models_dir, "MODELS_DIR")
    masks_dir = _lake(a.masks_dir, "MASKS_DIR")
    eval_csv = (Path(a.eval_report) if a.eval_report
                else _lake(None, "EVAL_DIR") / "semantic_eval_report.csv")
    registry = Path(a.tileset_registry or (QC / "tileset_registry.csv"))
    passport = Path(a.run_passport or (QC / "run_passport.csv"))
    hw = Path(a.hw_attribution or (QC / "hw_step_attribution.csv"))
    out = Path(a.out) if a.out else (QC / f"offload_pilot_{a.year}.csv")

    if not Path(status_dir).exists():
        print(f"FATAL: status dir not found: {status_dir}\n"
              f"       this instrument reads the lake — mount it, or pass --status-dir")
        return 2

    base_pin = Pin([a.baseline_session], parse_window(a.baseline_window))
    pilot_pin = Pin(str(a.pilot_sessions or "").split(","),
                    parse_window(a.pilot_window))

    def arm(tag, pin):
        return Arm(a.year, tag, status_dir, logs_dir, models_dir, masks_dir,
                   registry, eval_csv, passport, hw, pin)

    base, pilot = arm(a.baseline_tag, base_pin), arm(a.pilot_tag, pilot_pin)
    rows = build_rows(base, pilot)

    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not a.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(buf.getvalue(), encoding="utf-8", newline="")

    shown = out.relative_to(REPO) if out.is_relative_to(REPO) else out
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} rows → {shown}")
    for who, tag, arm_ in (("baseline", a.baseline_tag, base),
                           ("pilot", a.pilot_tag, pilot)):
        print(f"  {a.year} {who} {tag}: pin {arm_.pin.describe()} — "
              f"{len(arm_.rows)} queue row(s) admitted, sessions "
              f"{','.join(arm_.sessions) or '-'}")
        # Every refusal is named. A pin that is too tight has to be VISIBLE: the whole
        # reason this argument exists is that rows from the wrong launch were being
        # published silently, and a silent over-tight pin is the same defect mirrored.
        for rule, n in sorted(arm_.refused.items()):
            print(f"      refused {n} row(s): {rule}")
    if not pilot.rows:
        print("  the pilot has not run: every pilot cell is blank = NOT MEASURED, not 0")
    if not hw.exists():
        print("  hw_step_attribution.csv absent — R4 rows are blank by design")
    print(_table(rows, a.baseline_tag, a.pilot_tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())

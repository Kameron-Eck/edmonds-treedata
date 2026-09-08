"""harvest_runtime_sessions.py — ONE ROW PER RUNTIME: when it woke, when its queue
stopped, and how long the machine stayed alive afterwards doing nothing.

WHY. §6 of `Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md` counted 5.0 h of
`(between steps)` hardware samples and could not say what they were. Two very different
costs are pooled in that number and only one is fixable by editing the pipeline:

    START-UP     the VM is up, billed, and the queue has not yet written its first row —
                 bootstrap, pip, repo clone, mount. Fixable by a faster bootstrap.
    IDLE TAIL    the queue has written its LAST row and the machine is still alive.
                 Nothing is running. Fixable only by stopping the runtime, which is
                 exactly what CLAUDE.md 3.4 already calls a defect ("an idle runtime is
                 a defect") — but nobody had ever measured how much of it there is.

`hw_step_attribution.csv` cannot split them: it is keyed on the STEP, and both halves
of the waste carry the same `(between)` label. Splitting them needs a per-SESSION
timeline instead — the machine's own clock (hw samples, heartbeats) against the queue's
own clock (status rows) — which is what this file builds.

FOUR SOURCES OF A SESSION NAME, and every row says which of them it was seen in
(`sources`). A session is a Colab runtime as named by `vm_ops.py`; each source is
written by a different process on that runtime, so a session in only one of them is a
finding about the missing writer, not a reason to drop the row.

    hw_{session}.csv          `vm_hwlogger.py::main` — 5 s hardware samples. The `_v2`
                              suffix is the SCHEMA, not part of the session name (same
                              rule as `harvest_hw_attribution.py::session_of`), and a
                              trailing ` (N)` is DRIVE: two objects may share one name
                              in one folder (rclone.org/drive, "Duplicated files") and
                              `hw_healA (1).csv` sat on the lake 2026-09-08. Read
                              literally it is an extra runtime on this table, `sources`
                              reading `hw` and nothing else — the shape of a machine
                              whose beacon and queue both failed. Stripped in
                              `session_of_hw`; the surviving row says
                              `hw_drive_duplicate(<file>)`.
                              `hw_hours` is the SPAN of those stamps (last − first), NOT
                              sampled time: a stalled logger leaves a gap inside the
                              span, and the split between the two is the sibling
                              table's business (`hw_step_attribution.span_hours` vs
                              its `hours`), not repeated here.
    hw_meta_{session}.json    `vm_hwlogger.py::runtime_facts` — the runtime's fixed
                              facts (GPU model, vCPUs, RAM, and since 2026-09-08 the
                              CPU identity), written ONCE at start. TWO sessions on
                              the lake have one: `spdvc1` and `spdvg`, both 2026-09-08.
                              `gpu_name` / `vcpus` / `ram_gb` are blank on every earlier
                              row because the file did not exist, never because there
                              was no GPU — read `gpu_present`, which is measured from
                              the samples.

                              `cpu_model` / `cpu_mhz` / `bogomips` are blank on EVERY
                              row today, those two included: both metas were written
                              before those keys existed, and a VM clones the code at
                              launch, so no existing session gains them. They are here
                              because `spdc1` and `spdvc1`, both CPU runtimes, ran the
                              identical 632-tile
                              `tile` step over the same ortho in 21.0 vs 39.1 sampled
                              minutes at a median `cpu_pct` of 28.9 vs 21.3 (the
                              `tile_2017k` rows of each `hw_{session}.csv`; the ledger's
                              own `minutes` reads 34.1 vs 53.6). A slower host core is
                              the obvious explanation and no tracked file could confirm
                              or refute it: hw_meta's eleven original keys SIZE the
                              machine and never name it.
    heartbeat_*.json          `vm_heartbeat.py::write_atomic`. The SESSION FIELD is
                              read, never the filename: a name collision publishes to
                              `heartbeat_{s}__conflict-{id}.json` and a failed publish
                              can leave `heartbeat_{s}.json.prev.{tok}.json` behind, and
                              both of those are real samples of the same session.
    status rows               `queue_ledger.py::_status_write` stamps `host` and
                              `session` onto every row. Discovery of those files has
                              exactly one home: `phase4seg.names.status_files`.

`train_queue_nohup_{queue}_{ts}.log` filenames carry NO session — the launcher
(`vm_ops.py::launch_queue`) names them after the QUEUE FILE — so they contribute the
`queue` column and nothing else.

HOW `queue` IS RESOLVED, and why it is often blank. THREE links, in precedence order:

  1. the heartbeat's OWN DECLARATION — `queue_file`, the `--queue` argument the queue
     process publishes about itself through `vm_heartbeat.py::run_tags` (D11). Basename
     taken, `.yaml` stripped; some records carry an absolute path. This is the only
     link that cannot name another VM's queue, so it WINS whenever it is present.
  2. `heartbeat.newest_nohup.name`, only for the pre-D11 records that declare no
     `queue_file`, and then only from a record whose `queue_proc` is non-null.
     `vm_heartbeat.py::_newest` filters the nohup glob to this VM's own queue stem —
     and that filter is CONDITIONAL on having found a queue process to read the stem
     from (`if stem and …`). With no live queue the beacon reports the newest nohup log
     on the whole lake, which on a shared mount is routinely another VM's. Measured
     2026-09-07: 26 of 74 heartbeat records qualify.

     A LIVE `queue_proc` IS NECESSARY BUT NOT SUFFICIENT, and this file published a
     wrong queue for one runtime before the guard below existed. That filter matches by
     SUBSTRING (`("_" + stem + "_") in name`), so a stem which is a strict PREFIX of
     another queue's stem matches the LONGER queue's log: `hardyear` declared
     `queue_hard_year_pilot` and its `newest_nohup` named
     `queue_hard_year_pilot_only2006s`. Two such colliding pairs exist among the 38
     nohup stems on the lake — the other is `queue_noise_2021s` / `queue_noise_2021s_b`,
     the same collision `phase4seg/names.py::status_files_for_stem` documents defending
     against. So a stem reached this way is DROPPED when some other nohup stem on the
     lake is a prefix of it, and `sources` carries
     `queue_prefix_collision(shorter,longer)`.
  3. the status FILE's own stem, for rows carrying this session — and only from a file
     that represents a LAUNCH (`names.parse_status_name` returns a non-None ts, the
     test that module already defines). A `_seed` file records steps declared
     already-done, and the ledger-recovery CANDIDATE under `phase4/qc/ledger_recovery/`
     is a filename artifact; neither names the queue a paid runtime was serving.

All three are used. They agree or the cell is BLANK and `sources` says
`queue_ambiguous`: picking one would publish a guess about which queue a paid runtime
was serving.

THE MIRROR BLINKS, AND A BLINK MUST NOT SILENTLY DEGRADE A ROW. Reproduced against the
live lake 2026-09-07: one `LOGS_DIR.glob("heartbeat_*")` returned 143 entries with the
session `spdg` absent, and `heartbeat_spdg.json` had been read from that same directory
minutes before and read again after — the harvest in between published `queue`, both
heartbeat stamps and `idle_tail_min` blank for a live runtime, with nothing recording
the loss. Two mechanisms, and they need different answers. An EMPTY listing is
`lake.py::read_retry`'s case and every listing here goes through it. A NON-EMPTY listing
missing one file is not — `read_retry` retries only while the answer is falsy — and
`vm_heartbeat.py::write_atomic` guarantees such a window every 60 s, because it renames
the live file aside BEFORE replacing it. So every session known to another writer but
absent from the heartbeat listing is RE-PROBED by name (its own `heartbeat_{s}*` paths,
including the bare `.json.prev.{tok}` aside, which is the only copy that exists inside
that window). Still nothing: `sources` says `heartbeat_not_listed`, which reads as "no
beacon record was found for a session other writers know about" — the honest state for
the pre-beacon sessions too, and never a silently blank row.

THE CLOCKS. `hw` `ts_utc` and heartbeat `ts_utc` are stamped `...Z` (UTC). Status-row
`ts` is `_dt.datetime.now()` on the VM — NAIVE LOCAL TIME (phase4_train_queue.py
::run_step). They are treated as the same clock here because Colab runtimes run UTC.
That is an ASSUMPTION, not a verified fact; a runtime in another zone would show up as
a whole-hour `startup_min` or `idle_tail_min`, which is the check a reader should make
before believing a large value.

`queue_last_row_ts` IS THE LAST STEP'S START, NOT ITS END. `run_step` stamps `ts` when
it appends the row in state `RUNNING` and never re-stamps it; the completion `rec.update`
changes `state`/`minutes` and leaves `ts` alone. So `idle_tail_min` as defined here —
alive_end minus that stamp — INCLUDES the final step's own run time whenever the last
row is a step row. It does not when the last row is a `VERIFY:{step}` row, and the reason
is the STAMP, not the ordering: `queue_verify.py::verify_step` builds its record — `ts`
included — after the check has finished, so that cell is a completion time. (The job-end
`VERIFY` row is the other way round: `phase4_train_queue.py::verify` stamps `ts` before
`_check_prob_raster`, so it is a start stamp, of an interval that begins after the last
step ended.)

HOW LONG A VERIFY TAKES WAS UNRECORDED UNTIL 2026-09-07, and this docstring used to
assert "takes seconds" with nothing behind it. All 246 VERIFY rows in
`phase4/qc/ledger_recovery/train_queue_status_recovered_20260901_20260907.csv` carry a
BLANK `minutes`; the only bound the archive gives is the adjacent stamps on session
`spdc1` — `labels` stamped 21:51:58 with `minutes` 6.8 (so it ended 21:58:46),
`VERIFY:labels` stamped 21:58:49, and the next step's row on that same second. Seconds,
there. Commit c5dc91c now stamps `minutes` on all four VERIFY write sites, so the
question is answered on the row instead of assumed: the first rows to carry it read 0.0
and 0.0 (session `spdc2`, in the LAKE copy of
`train_queue_status_pilot_offload_2017k_cpu2_20260907T235535Z.csv` — live and untracked,
read 2026-09-08). Read `idle_tail_min` as an UPPER BOUND on the idle
tail; the `minutes` column of that last row is the correction, and joining it is still
deliberately left out of this table rather than half-done.

NOR IS IT A TAIL WHERE THE LEDGER STOPPED NAMING THE SESSION. `queue_last_row_ts` is
the last row that says `session=<s>`, which is the last row of the RUN only while every
row is attributed. It stopped being so on 2026-09-07, when the ledger-recovery candidate
(`phase4/qc/ledger_recovery/`, `rebuild_queue_ledger.py`) was copied onto the lake and
every reader began merging it as `names.status_files` promises: its 252 snapshot-native
rows carry a `session`, its 198 log-synthesised rows carry an EMPTY one, and the
synthesised rows are precisely the events no snapshot captured — the later ones. So a
session's ledger now ends where its ATTRIBUTION ends. Measured on `ofB`: last
session-stamped row `evaluate` 16:33:53, rows for the same run tag continuing to
18:58:23, and a published "idle tail" of 351.6 min over hours of work. Any blank-session
row bearing one of this session's tags and dated after its last row raises
`later_rows_unattributed(tag)`, and those rows leave the headline sum — without it the
summary read 1826.3 min of idleness across 13 sessions. THE GUARD IS NECESSARY, NOT
SUFFICIENT: it can only see tags the session already has an attributed row for, so a
ledger that cut before its next tag began — every later row on a tag this session never
claimed — passes unflagged. Absence of the flag is not proof the ledger is complete.

AND IT IS NOT A TAIL AT ALL WHILE THE QUEUE IS STILL RUNNING. `run_step` appends its
row in state `RUNNING`; a session whose newest row is `RUNNING` has an `idle_tail_min`
that grows with the current step. `sources` carries `queue_last_row_RUNNING` for those,
and the run summary excludes them from the headline sum.

`heartbeat_first_utc` IS A CEILING, NOT A START. The beacon OVERWRITES one file per
session every 60 s, so what survives is the last cycle plus whatever `prev_ts_utc` it
carried plus any stranded `.prev.` file that still ends in `.json`. The earliest of
those is the earliest stamp that still EXISTS — at or after the beacon's real start.

BLANK IS NEVER ZERO on this table. A session with no status rows has a blank
`n_queue_rows`, not 0: "this runtime's ledger rows are not on the lake" and "this
runtime ran no steps" are different claims and the table must not merge them. Measured
2026-09-07, that distinction is most of the table — see the reader rule in
docs/SCHEMAS.md for the ledger loss that caused it.

Run:  py -3.12 qc/instruments/harvest_runtime_sessions.py [--dry-run]
      py -3.12 qc/instruments/harvest_runtime_sessions.py --logs-dir DIR --qc-dir DIR
Output: phase4/qc/runtime_sessions.csv  (schema: docs/SCHEMAS.md)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

COLS = ["session", "queue", "gpu_name", "vcpus", "ram_gb",
        "hw_first_utc", "hw_last_utc", "hw_hours", "gpu_present",
        "heartbeat_first_utc", "heartbeat_last_utc",
        "queue_first_row_ts", "queue_last_row_ts", "n_queue_rows",
        "startup_min", "idle_tail_min", "sources",
        # THE CPU IDENTITY, appended 2026-09-08 (vm_hwlogger.py::runtime_facts). Last,
        # so every reader keyed on a column POSITION in the seventeen above still reads
        # what it read. Blank for every session whose hw_meta predates those keys.
        "cpu_model", "cpu_mhz", "bogomips"]

# vm_ops.py::launch_queue writes train_queue_nohup_{queue_stem}_{launch_ts}.log. The
# stem itself contains underscores (`queue_tier1_science_sample`), so the split is
# anchored on the TIMESTAMP, never on the last underscore.
_NOHUP = re.compile(r"^train_queue_nohup_(.+)_(\d{8}T\d{6}Z)\.log$")

# ` (1)`, ` (2)` … — Drive's rendering of a SECOND object with the same name in the same
# folder. Matched with `.csv` already stripped and anchored at the end, so a session
# genuinely spelled `foo (1)bar` is untouched. See `session_of_hw`.
_DRIVE_TWIN = re.compile(r" \(\d+\)$")

# Every LISTING this instrument makes goes through `lake.py::read_retry` with these:
# the Drive/FUSE mirror hands back an empty listing for a directory that is plainly
# populated a second later, and an empty listing here does not raise — it silently
# publishes a table with a whole source missing. `tries=3` rather than read_retry's
# default 10, for the same reason `harvest_timing_events.py::read_retry_logs` chose it:
# a genuinely empty directory must not cost ten seconds of sleep. `_RETRY_PAUSE` is a
# module constant so a test can zero it; retries against a fixture tree measure nothing.
_RETRY_TRIES = 3
_RETRY_PAUSE = 1.0


def _listing(fn, tries=_RETRY_TRIES):
    """`fn()`'s listing, retried while it comes back EMPTY. See `_RETRY_TRIES`.

    Covers only the empty-listing blink. A listing that returns 143 entries with one
    file missing is non-empty, so `read_retry` accepts it on the first try — that case
    is `reprobe_heartbeat`'s, and the module docstring records why it needed to exist.
    """
    try:
        from lake import read_retry
    except ImportError:                                          # pragma: no cover
        return fn()
    return read_retry(fn, tries=tries, pause=_RETRY_PAUSE) or []


def nohup_stems(logs_dir):
    """Every queue stem that appears in a `train_queue_nohup_*.log` name on the lake.

    The census `_prefix_owner` needs: a stem can only be shown to be a mis-hit of
    `vm_heartbeat.py::_newest`'s substring filter by naming the SHORTER stem it could
    have been matched from, and that stem is only knowable from the directory.
    """
    def _glob():
        return sorted(Path(logs_dir).glob("train_queue_nohup_*.log"))
    out = set()
    for p in _listing(_glob):
        m = _NOHUP.match(Path(p).name)
        if m:
            out.add(m.group(1))
    return out


def _prefix_owner(stem, stems):
    """The other stem `stem` could have been mis-matched FROM, or None.

    `vm_heartbeat.py::_newest` keeps a filename when `("_" + T + "_")` is a substring of
    it, so a beacon looking for T can return the log of any longer stem beginning
    `T + "_"`. Only a LONGER parsed stem can be a mis-hit — a short filename cannot
    contain a long stem — so short stems stay resolved and this guard cannot blank them.
    """
    for t in sorted(stems):
        if t != stem and stem.startswith(t + "_"):
            return t
    return None


def declared_queue_stem(beat):
    """The queue stem this beacon DECLARED about itself, or "".

    `vm_heartbeat.py::sample` writes `queue_file` from `run_tags`, i.e. from the queue
    process's own `--queue` argument, so it names this VM's queue and no other. Some
    records carry an absolute path (`/content/repo/Scripts/pipeline/pilot_2019_coarse
    .yaml`), hence the basename; both separators are handled because the field is
    written on the VM and read here on Windows.
    """
    raw = str(beat.get("queue_file") or "").strip()
    if not raw:
        return ""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-5] if name.endswith(".yaml") else name


def session_of_hw(path):
    """hw_{session}.csv -> session; `_v2` is the schema and ` (N)` is Drive, not names.

    A deliberate re-implementation of `harvest_hw_attribution.py::session_of` rather
    than an import: instruments are run by path and must not depend on each other's
    load order. One rule, two homes, and both are covered by their own tests — so when
    one changes, so must the other.

    A TRAILING ` (N)` IS DRIVE. Two objects may carry one name in one Drive folder
    (rclone.org/drive, "Duplicated files") and the desktop client renders the second as
    `hw_healA (1).csv`. Read literally that is a whole extra runtime on this table —
    `healA (1)`, with `sources` reading `hw`, no beacon, no queue rows and a spurious
    `heartbeat_not_listed`, which is exactly the shape of a machine whose telemetry
    failed. Strip order is `.csv` -> ` (N)` -> `_v2`: Drive appends its suffix to the
    whole name, so `hw_x_v2 (1).csv` is session `x`.

    This table needs no row-level merge, unlike the sibling one. Its hw columns are
    min / max / any over the session's files, and those are already union operations:
    a twin is a prefix or an overlap, and either way it can only re-state a bound the
    longer file already sets or widen it correctly.
    """
    stem = Path(path).name
    if stem.startswith("hw_"):
        stem = stem[3:]
    if stem.endswith(".csv"):
        stem = stem[:-4]
    stem = _DRIVE_TWIN.sub("", stem)
    if stem.endswith("_v2"):
        stem = stem[:-3]
    return stem


def parse_ts(v):
    """A timestamp from any of the three writers, or None.

    `2026-09-05T03:04:05Z` (hw + heartbeat, UTC) and `2026-09-05 03:04:05` (status rows,
    naive VM-local) are both accepted and returned as NAIVE datetimes — see the module
    docstring for why they are treated as one clock.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def _iso(t):
    """A datetime back to the table's text form, or blank. Never a guessed zone."""
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t is not None else ""


def _hours(a, b):
    return "" if (a is None or b is None) else f"{(b - a).total_seconds() / 3600.0:.4f}"


def _minutes(a, b):
    """b − a in minutes. Blank when either side is missing — never 0, which would read
    as a measured "no gap"."""
    return "" if (a is None or b is None) else f"{(b - a).total_seconds() / 60.0:.1f}"


def _is_heartbeat(name):
    """A real heartbeat publication?

    Admits the conflict copy (`heartbeat_x__conflict-ab12cd.json`) and a stranded
    predecessor THAT STILL ENDS IN `.json` (`heartbeat_x.json.prev.ab12cd.json`) — both
    hold a genuine sample of the session, and the session is read from the FIELD, so
    neither can be misfiled. Rejects `write_atomic`'s in-flight `…json.tmp.{pid}`, which
    has no `.json` suffix precisely so that readers filtering on one skip it. The bare
    form `…json.prev.ab12cd` is rejected by that same rule during the LISTING pass;
    following the writer's stated reader contract is deliberate there — the alternative
    is a reader that admits files the writer promised were invisible.

    `reprobe_heartbeat` deliberately does NOT apply this rule. That path fires only for
    a session another writer knows about and the listing did not show, and inside
    `write_atomic`'s rename window the bare aside is the ONLY copy of the beacon that
    exists. It is admitted there because the session is read from the FIELD, so no
    filename can misfile it — the suffix contract protects readers that key on names,
    and this one does not.
    """
    return (name.startswith("heartbeat_") and name.endswith(".json")
            and ".tmp." not in name)


def read_hw(path):
    """-> (first_ts, last_ts, gpu_present) for one hw CSV.

    `gpu_present` is True when ANY sample carries a non-blank `gpu_util_pct`. A CPU
    runtime's logger writes every GPU column empty, so absence of readings is the
    reading — that is the one column where blank is informative (same rule as
    `harvest_hw_attribution.py::summarise`).
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None, None
    lo = hi = None
    gpu = False
    seen = False
    for r in csv.DictReader(text.splitlines()):
        t = parse_ts(r.get("ts_utc"))
        if t is None:
            continue
        seen = True
        lo = t if lo is None or t < lo else lo
        hi = t if hi is None or t > hi else hi
        if str(r.get("gpu_util_pct") or "").strip():
            gpu = True
    return lo, hi, (gpu if seen else None)


def read_meta(path):
    """One hw_meta_{session}.json -> its dict, or {} if it cannot be read.

    Never raises: this file is written best-effort by the logger, and an unreadable one
    must cost the runtime's row its three fixed-fact columns, not the whole harvest.
    """
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _load_beat(path):
    """One heartbeat file -> its dict, or None if it is not a readable JSON object."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _absorb_beat(out, d, stems_fn):
    """Fold one heartbeat record into `out`. Returns the session, or "".

    `stems_fn` is called at most once per harvest and only on the pre-D11 fallback
    path — the nohup census costs a directory listing and most records never need it.
    """
    sess = str(d.get("session") or "").strip()
    if not sess:
        return ""
    g = out.setdefault(sess, {"stamps": [], "queues": set(), "flags": set()})
    for key in ("ts_utc", "prev_ts_utc"):
        t = parse_ts(d.get(key))
        if t is not None:
            g["stamps"].append(t)

    declared = declared_queue_stem(d)
    if declared:
        g["queues"].add(declared)                 # the queue's own claim wins outright
    elif d.get("queue_proc"):
        m = _NOHUP.match(str((d.get("newest_nohup") or {}).get("name") or ""))
        if m:
            stem = m.group(1)
            owner = _prefix_owner(stem, stems_fn())
            if owner:
                g["flags"].add(f"queue_prefix_collision({owner},{stem})")
            else:
                g["queues"].add(stem)
    return sess


def read_heartbeats(logs_dir):
    """session -> {"stamps": [datetime, …], "queues": {stem, …}, "flags": {str, …}}.

    `stamps` pools `ts_utc` and `prev_ts_utc` from every surviving record — both are
    real beacon cycles, and prev is the only evidence left of the cycle before the
    overwrite. `queues` takes the record's DECLARED `queue_file` when it has one and
    falls back to the newest-nohup link, guarded, only when it does not; see the module
    docstring for why the fallback needs a guard at all.
    """
    logs_dir = Path(logs_dir)
    cache = {}

    def stems_fn():
        if "s" not in cache:
            cache["s"] = nohup_stems(logs_dir)
        return cache["s"]

    def _glob():
        return sorted(logs_dir.glob("heartbeat_*"))

    out = {}
    for p in _listing(_glob):
        if not _is_heartbeat(Path(p).name):
            continue
        d = _load_beat(p)
        if d is not None:
            _absorb_beat(out, d, stems_fn)
    return out


def reprobe_heartbeat(logs_dir, session):
    """This ONE session's beacon records, found by name rather than by listing.

    The listing said the session has no heartbeat. That is not evidence: see the module
    docstring's mirror-blink paragraph, and note that `write_atomic` renames the live
    file aside for a window every 60 s, so the canonical name genuinely does not exist
    then. Probe the session's own paths — canonical, `__conflict-` copy, and the bare
    `.json.prev.{tok}` aside, which is the only copy inside that window — and admit
    whatever names THIS session in its `session` field. Returns the same per-session
    dict shape as `read_heartbeats`, or None when nothing was found.
    """
    logs_dir = Path(logs_dir)

    def _glob():
        try:
            return sorted(logs_dir.glob(f"heartbeat_{session}*"))
        except (OSError, ValueError):        # a session name that is not a valid glob
            return []

    out = {}
    cache = {}

    def stems_fn():
        if "s" not in cache:
            cache["s"] = nohup_stems(logs_dir)
        return cache["s"]

    for p in _listing(_glob):
        if ".tmp." in Path(p).name:          # in-flight, and the writer says so
            continue
        d = _load_beat(p)
        if d is not None:
            _absorb_beat(out, d, stems_fn)   # a neighbour's file lands under ITS name
    return out.get(session)                  # …and is dropped here, by the field


def read_queue_rows(qc_dir):
    """-> (by_session, unattributed) where
    by_session[session] = {"stamps": [datetime, …], "n": int, "queues": {stem, …},
    "tags": {tag, …}, "last": datetime, "last_state": str}
    and unattributed[tag] = the LATEST ts of a row carrying that tag and NO session.

    Rows whose `session` cell is blank contribute nothing TO A SESSION: every archived
    status file written before `queue_ledger.py` added the column has no session at all,
    and inventing one would attach another runtime's ledger to this row.

    They are not discarded either, and `unattributed` is why. A blank-session row dated
    AFTER a session's last row, carrying a run tag that session was working on, is
    evidence that the session's ledger is TRUNCATED rather than finished — the work went
    on, and only the attribution was lost. Measured 2026-09-07, once the ledger-recovery
    candidate reached the lake: all 198 of its synthesised rows carry an empty `session`
    (only the 252 snapshot-native rows have one), and for `ofB` the last session-stamped
    row is `evaluate` at 16:33:53 while rows for the SAME tag run on to 18:58:23. Without
    this, that session publishes a 351.6 min "idle tail" over hours of measured work.

    `last_state` is the `state` of the row bearing the LATEST `ts` — the one
    `queue_last_row_ts` comes from. It exists for one reason: a row still in state
    `RUNNING` means the queue has not finished, so the gap after it is work in
    progress and not an idle tail at all. Ties on `ts` are broken by file-then-row
    order, so the answer is deterministic.

    A file's stem becomes a `queue` candidate ONLY when that file represents a LAUNCH —
    `parse_status_name` returning a non-None ts, the test `phase4seg.names` already
    defines and documents. Its ROWS still count either way; it is the NAME that is not
    evidence. Two kinds of admissible file are not launches and both are on the lake:
    the 25 `_seed.csv` files, whose stem would collide with the same queue's launches
    and blank the cell through `queue_ambiguous`, and the ledger-recovery CANDIDATE
    `train_queue_status_recovered_20260901_20260907.csv`, whose stem is a filename
    artifact — reproduced 2026-09-07 by running this instrument over the lake's status
    files plus that candidate: `t1gpuE`, `t1gpuF`, `trend8A2` and `trend8B2` published
    `queue = recovered_20260901_20260907`, a queue that has never existed.
    """
    from phase4seg.names import parse_status_name, status_files

    out = {}
    unattributed = {}
    for f in _listing(lambda: status_files(qc_dir)):
        parsed = parse_status_name(Path(f).name)
        stem = parsed[0] if (parsed and parsed[1] is not None) else ""
        try:
            text = Path(f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for r in csv.DictReader(text.splitlines()):
            sess = str(r.get("session") or "").strip()
            tag = str(r.get("tag") or "").strip()
            t = parse_ts(r.get("ts"))
            if not sess:
                if tag and t is not None:
                    prev = unattributed.get(tag)
                    if prev is None or t > prev:
                        unattributed[tag] = t
                continue
            g = out.setdefault(sess, {"stamps": [], "n": 0, "queues": set(),
                                      "tags": set(), "last": None, "last_state": ""})
            g["n"] += 1
            if tag:
                g["tags"].add(tag)
            if t is not None:
                g["stamps"].append(t)
                if g["last"] is None or t >= g["last"]:
                    g["last"] = t
                    g["last_state"] = str(r.get("state") or "").strip()
            if stem:
                g["queues"].add(stem)
    return out, unattributed


def build_rows(logs_dir, qc_dir):
    """One row per session, sorted by session. See the module docstring for the joins."""
    logs_dir, qc_dir = Path(logs_dir), Path(qc_dir)

    hw = {}
    for p in _listing(lambda: sorted(logs_dir.glob("hw_*.csv"))):
        s = session_of_hw(p)
        if not s:
            continue
        lo, hi, gpu = read_hw(p)
        g = hw.setdefault(s, {"lo": None, "hi": None, "gpu": None, "twins": []})
        # Named on the row, not silently absorbed: a duplicate Drive object is a fact
        # about the lake this session's operator may want to act on (deleting one is
        # Kam's call, never a harvest's), and it is the only place a reader can see
        # that this row was assembled from more than one file.
        if _DRIVE_TWIN.search(Path(p).stem):
            g["twins"].append(Path(p).name)
        if lo is not None:
            g["lo"] = lo if g["lo"] is None or lo < g["lo"] else g["lo"]
        if hi is not None:
            g["hi"] = hi if g["hi"] is None or hi > g["hi"] else g["hi"]
        if gpu is not None:
            g["gpu"] = bool(g["gpu"]) or gpu

    meta = {}
    for p in _listing(lambda: sorted(logs_dir.glob("hw_meta_*.json"))):
        d = read_meta(p)
        s = str(d.get("session") or "").strip()
        if not s:                       # fall back to the filename only when the file
            s = Path(p).name[len("hw_meta_"):-len(".json")]  # failed to name itself
        if s:
            meta[s] = d

    beats = read_heartbeats(logs_dir)
    qrows, unattributed = read_queue_rows(qc_dir)

    # THE LISTING IS NOT EVIDENCE OF ABSENCE. For every session another writer knows
    # about and the heartbeat listing did not show, probe that session's own paths
    # before publishing a row with its beacon columns blank — the mirror drops single
    # entries from a non-empty listing, and `write_atomic` opens a window every cycle
    # where the canonical name does not exist. Still nothing: say so in `sources`.
    missing_beat = set()
    for sess in sorted((set(hw) | set(meta) | set(qrows)) - set(beats)):
        found = reprobe_heartbeat(logs_dir, sess)
        if found:
            beats[sess] = found
        else:
            missing_beat.add(sess)

    rows = []
    for sess in sorted(set(hw) | set(meta) | set(beats) | set(qrows)):
        h = hw.get(sess) or {}
        m = meta.get(sess) or {}
        b = beats.get(sess) or {}
        q = qrows.get(sess) or {}

        src = []
        if sess in hw:
            src.append("hw")
            for t in sorted(h.get("twins") or ()):
                src.append(f"hw_drive_duplicate({t})")
        if sess in meta:
            src.append("hw_meta")
        if sess in beats:
            src.append("heartbeat")
        if sess in qrows:
            src.append("queue_rows")
        if sess in missing_beat:
            src.append("heartbeat_not_listed")
        # A nohup stem dropped because a shorter stem on the lake could have produced
        # it. The cell is blank rather than wrong; the flag says which two names were
        # confusable, so the queue is still recoverable by hand.
        src.extend(sorted(b.get("flags") or ()))

        stems = set(b.get("queues") or ()) | set(q.get("queues") or ())
        if len(stems) == 1:
            queue = next(iter(stems))
        else:
            queue = ""
            if len(stems) > 1:
                src.append("queue_ambiguous(" + ",".join(sorted(stems)) + ")")

        hb = sorted(b.get("stamps") or ())
        qs = sorted(q.get("stamps") or ())
        hw_lo, hw_hi = h.get("lo"), h.get("hi")
        hb_lo = hb[0] if hb else None
        hb_hi = hb[-1] if hb else None
        q_lo = qs[0] if qs else None
        q_hi = qs[-1] if qs else None

        # The last moment the machine is KNOWN to have been alive: whichever of its two
        # independent beacons stamped later. Either may be missing on its own.
        alive_end = max([t for t in (hw_hi, hb_hi) if t is not None], default=None)

        # A NEGATIVE idle tail is not an arithmetic slip and is not clipped to zero: it
        # says the machine's last surviving liveness stamp PRECEDES the queue's last
        # ledger row — the beacon stopped publishing while the queue kept writing rows.
        # Measured 2026-09-07 on `pilotcoarse`: the heartbeat's last stamp is 42.8 min
        # before the queue's last row and sits INSIDE the queue's own span, so it is not
        # a clock offset (an offset would push the stamp outside the span, by a whole
        # hour); and `pilotcoarse2` reports a DIFFERENT `host` and a different GPU, so it
        # is not the same runtime re-bootstrapped under a new session name either. WHY
        # the beacon stopped is not established here. Flagged because a reader summing
        # this column must drop those rows: telemetry failure, not idle time.
        if alive_end is not None and q_hi is not None and alive_end < q_hi:
            src.append("beacon_ended_before_queue")

        # The queue's newest row is still RUNNING, so `idle_tail_min` is not an idle
        # tail: it is the elapsed time of a step that has not finished. Measured on the
        # live campaign 2026-09-07 — `spdg` read 4.4 min, then 10.4 min six minutes
        # later, off the same unchanged row. Without this flag the ONE GPU number the
        # table can currently produce would be read as measured idleness.
        if str(q.get("last_state") or "").upper() == "RUNNING":
            src.append("queue_last_row_RUNNING")

        # THE LEDGER STOPS NAMING THIS SESSION BEFORE THE WORK STOPS. Ledger rows for a
        # tag this session was running, dated after its own last row but carrying NO
        # session, say the attribution was lost — not that the machine went idle. The
        # gap after `queue_last_row_ts` is then mostly WORK. Measured 2026-09-07 with
        # the recovery candidate on the lake: 12 of the 13 sessions with a tail are in
        # this state, and the unflagged sum reads 1826.3 min of "idle".
        late = sorted(t for t in (q.get("tags") or ())
                      if q_hi is not None and (unattributed.get(t) or q_hi) > q_hi)
        if late:
            src.append("later_rows_unattributed(" + ",".join(late) + ")")

        rows.append({
            "session": sess,
            "queue": queue,
            "gpu_name": str(m.get("gpu_name") or ""),
            "vcpus": str(m.get("vcpus") if m.get("vcpus") is not None else ""),
            "ram_gb": str(m.get("ram_gb") if m.get("ram_gb") is not None else ""),
            "hw_first_utc": _iso(hw_lo),
            "hw_last_utc": _iso(hw_hi),
            "hw_hours": _hours(hw_lo, hw_hi),
            # 1 / 0 / blank. Blank = no hw samples parsed for this session at all, which
            # is not evidence either way about the hardware it was given.
            "gpu_present": "" if h.get("gpu") is None else ("1" if h["gpu"] else "0"),
            "heartbeat_first_utc": _iso(hb_lo),
            "heartbeat_last_utc": _iso(hb_hi),
            "queue_first_row_ts": _iso(q_lo),
            "queue_last_row_ts": _iso(q_hi),
            "n_queue_rows": str(q["n"]) if q.get("n") else "",
            "startup_min": _minutes(hw_lo, q_lo),
            "idle_tail_min": _minutes(q_hi, alive_end),
            "sources": ";".join(src),
            # Read from hw_meta ONLY, and blank when the key is not there — which is
            # every session logged before 2026-09-08, and any runtime whose /proc could
            # not be read. `is not None` rather than `or ""` for the same reason as
            # `vcpus`: a 0.0 MHz reading would be a measurement, and falsiness would
            # erase it.
            "cpu_model": str(m.get("cpu_model") or ""),
            "cpu_mhz": str(m.get("cpu_mhz") if m.get("cpu_mhz") is not None else ""),
            "bogomips": str(m.get("bogomips") if m.get("bogomips") is not None else ""),
        })
    return rows


def _default_dirs(logs=None, qc=None):
    from lake import LOGS_DIR, QC_DIR
    return (Path(logs) if logs else LOGS_DIR), (Path(qc) if qc else QC_DIR)


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--logs-dir", default=None)
    ap.add_argument("--qc-dir", default=None,
                    help="where train_queue_status*.csv live (lake phase4/qc)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    logs_dir, qc_dir = _default_dirs(a.logs_dir, a.qc_dir)
    if not logs_dir.exists():
        print(f"FATAL: logs not found: {logs_dir}\n"
              f"       this instrument reads the lake — mount it, or pass --logs-dir")
        return 2

    rows = build_rows(logs_dir, qc_dir)
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    out = Path(a.out) if a.out else (QC / "runtime_sessions.csv")
    if not a.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(buf.getvalue(), encoding="utf-8", newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} session(s) → {out.name}")
    print(f"  {'session':14} {'queue':34} {'gpu':>4} {'hw_h':>7} "
          f"{'start_m':>8} {'idle_m':>8}")
    for r in rows:
        print(f"  {r['session']:14} {r['queue'][:34]:34} {r['gpu_present']:>4} "
              f"{r['hw_hours']:>7} {r['startup_min']:>8} {r['idle_tail_min']:>8}")
    # The headline. THREE exclusions, all from build_rows and none cosmetic: a NEGATIVE
    # tail records a beacon that stopped before the work did (telemetry failure, not
    # paid idleness); a `RUNNING` last row records a step still executing (work in
    # progress, not a tail); and `later_rows_unattributed` records a ledger that stopped
    # NAMING this session while rows for its own tags kept arriving (lost attribution,
    # so the gap is mostly work).
    def usable(r):
        return (r["idle_tail_min"] and float(r["idle_tail_min"]) >= 0
                and "queue_last_row_RUNNING" not in r["sources"]
                and "later_rows_unattributed" not in r["sources"])

    # TWO SUMS, because the GPU filter and the tail filter answer to different
    # evidence and the narrower one alone is misleading. `gpu_present` is hw-derived,
    # and the two sessions that DO have a usable tail (pilotfine, pilotmed) wrote no
    # hw CSV at all — their A100s are named only in their heartbeats. Printing the
    # GPU-confirmed line by itself would report UNMEASURED over a measured 13.4 min.
    tails = [(r["session"], float(r["idle_tail_min"])) for r in rows if usable(r)]
    gpu_tails = [t for t in tails
                 if next(r for r in rows if r["session"] == t[0])["gpu_present"] == "1"]
    n_gpu = sum(1 for r in rows if r["gpu_present"] == "1")
    if tails:
        print(f"  idle tail, {len(tails)} session(s) with a usable tail: "
              f"{sum(v for _s, v in tails):.1f} min "
              f"({', '.join(f'{s} {v:.1f}' for s, v in tails)})")
    else:
        print("  idle tail: UNMEASURED — no session has both a machine-side stamp "
              "and a finished, session-stamped queue row")
    print(f"  of which GPU-CONFIRMED FROM HW SAMPLES ({n_gpu} such session(s)): "
          f"{sum(v for _s, v in gpu_tails):.1f} min over {len(gpu_tails)} — "
          f"a blank gpu_present is 'no hw CSV', not 'no GPU'")
    n_neg = sum(1 for r in rows if "beacon_ended_before_queue" in r["sources"])
    if n_neg:
        print(f"  {n_neg} session(s) flagged beacon_ended_before_queue "
              f"(negative tail = the beacon stopped first; excluded above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

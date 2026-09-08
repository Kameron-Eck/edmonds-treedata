r"""vm_hwlogger.py — raw hardware telemetry, one CSV per session, mirrored to Drive.

Kam, 2026-09-02: "We should be tracking GPU utilization, CPU utilization,
read/write speed, and virtual disk space." This is that tracker: a stdlib
VM-side sampler (5 s cadence, one Drive write a minute) publishing

    {DRIVE}/phase4/logs/hw_{session}.csv
    ts_utc, gpu_util_pct, gpu_mem_util_pct, gpu_mem_used_mb, gpu_power_w,
    cpu_pct, disk_read_mb_s, disk_write_mb_s, net_rx_mb_s, net_tx_mb_s,
    disk_used_gb, disk_free_gb, cpu_iowait_pct, step, run_tag

Sources are the kernel's own counters — /proc/stat, /proc/diskstats,
/proc/net/dev, statvfs — plus one nvidia-smi query per sample. No pipeline
code in the measurement path; the numbers are what Linux and NVIDIA say, which
is the point ("hard for me to know what to trust"). Net rx/tx IS the Drive
FUSE traffic (rclone speaks HTTPS), so read/write speed to the lake shows up
there; disk_* is the local NVMe. Launched by the bootstrap next to the beacon;
CPU runtimes just log blank GPU columns. Never crashes the host: every sampler
is try/except-blank.

LOCAL FIRST, MIRRORED SECOND (2026-09-08) — the sampling thread never touches Drive.

Until now the loop did its own `open(out, "a"); f.writelines(rows)` onto the FUSE mount
every 60 s, on the sampling thread, so a slow append stopped the clock it was measuring.
Measured on the two live pilot sessions (read 2026-09-08; both files were still growing,
so these counts date themselves — the durable home for the same quantity is
`span_hours - hours` per (session, basis) in phase4/qc/hw_step_attribution.csv):

  hw_spdg.csv    693 rows, 689 with a readable ts_utc, 4 unusable. 75.1 min spanned,
                 57.4 min sampled: 22 gaps > 12 s totalling 22.3 min — 30% of the
                 session unsampled, each gap 13-127 s, i.e. one flush cadence or a few,
                 and the longest alongside checkpoint upload bursts.
  hw_spdc1.csv   495 rows, 492 readable, 3 unusable. 49.9 min spanned, 41.0 min
                 sampled: 9 gaps totalling 9.6 min (19%), 20-123 s each.

The unusable rows are the same defect's other half. An append onto the mount can land
PART OF a `writelines` — and the old flush then kept the whole buffer for its next
attempt, so a partial write is followed by a re-write of rows already on disk. What is
actually IN the two files is the first symptom: fragments. hw_spdg.csv holds a line whose
`ts_utc` cell reads `200.5` and whose `gpu_mem_util_pct` cell reads `train_2017k` — the
last four cells of one sample, standing alone under another row's column names — and
hw_spdc1.csv holds three of the same shape. (No line is repeated verbatim in either file,
so the re-write half of the mechanism is read from the code, not observed here.)

So the sample is written to `{local_dir}/hw_{session}.local.csv` and flushed on the spot
— local NVMe, no FUSE, one line per write — and a daemon thread publishes the WHOLE
local file to Drive every --flush-every samples: write `{out}.part.{pid}`, os.replace it
onto `out`. That publish is atomic (a reader sees the old file or the new one, never a
torn line), idempotent (a failed mirror retries on the next tick — nothing is buffered,
so nothing can be half-written twice) and cut at the last complete line, so a half-
written local row cannot reach Drive even in principle. The local file is the session's
source of truth until the process ends; SIGTERM and normal exit both run one last mirror.
`out`'s existing bytes SEED the local file at startup (_open_local), so a restarted
logger publishes a superset instead of erasing the session — and if they cannot be read,
this falls back to appending rather than publishing a shorter file over a longer one.
If the local directory is unusable at all, the old append-to-Drive path runs and says so
on stderr: degraded telemetry beats none.

v2 (2026-09-07) — the last three columns:

  cpu_iowait_pct   Time blocked on I/O, as its own reading. v1 folded iowait
                   INTO idle (`idle = vals[3] + vals[4]`), so a process stalled
                   on Drive FUSE latency looked exactly like a machine with
                   nothing to do — the one distinction the speedup analysis
                   most needed — see §7.1 of
                   Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md, which quotes
                   this file's own `idle = vals[3] + vals[4]` as the cause.
                   cpu_pct keeps its ORIGINAL arithmetic (busy = total - idle -
                   iowait) so every v1 file stays comparable; iowait is added
                   beside it, not folded into it.
  step, run_tag    Read each sample from the marker file that
                   pipeline_log.StepLogger publishes (see
                   phase4seg.names.hw_step_marker_path — which owns the `phase`
                   vocabulary this reader honours). Blank when no step is
                   open — and also when the marker's writer pid is gone, so a
                   SIGKILLed step cannot keep claiming samples it is not running
                   (read_marker). This is what makes attribution EXACT: §7 had to join hw
                   timestamps to the step logs of every VM at once, and dropped
                   8,304 of 28,999 samples (29%) where concurrently-open
                   intervals disagreed — nothing recorded which step ran on
                   which machine. The marker is per-machine by construction.

                   Since 2026-09-07 a marker may also carry a `phase`, and the
                   cell then reads `<step>#<phase>` — see read_marker. The CSV
                   HEADER IS UNCHANGED: the phase rides inside the existing step
                   cell precisely so v2 files written before and after this stay
                   one schema.

Schema safety: if hw_{session}.csv already exists with the v1 12-column header,
this writes hw_{session}_v2.csv instead (resolve_out). Two schemas in one file
would break every DictReader that touches it, and a half-v1/half-v2 file cannot
be repaired after the fact.

Beside the samples, ONE file of runtime facts (runtime_facts / write_meta):

    {DRIVE}/phase4/logs/hw_meta_{session}.json
    session, started_utc, hostname, vcpus, ram_gb, disk_total_gb, gpu_name,
    gpu_mem_mb, kernel, python, marker_path

Written once at start and never rewritten. Every per-sample column says what the
machine was DOING; nothing in the archive says what the machine WAS, so a session
reading 0% GPU could not be told apart from a session with no GPU, and hours could
not be priced (an A100 hour and a CPU hour are not the same money). These are
constants of the runtime, so a row per sample would be 43,000 copies of one fact.
Best-effort in every field: blank beats a guess, and this must never be able to
stop the sampling loop it runs before.
"""
import argparse
import atexit
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

DRIVE = "/content/drive/MyDrive/treedata"
LOCAL_DIR = "/content"          # last resort for the spool; the marker's dir wins

# The literal is the fallback for BOTH sides of the marker contract; the import is
# the one home. Guarded because this logger's whole promise is that it keeps sampling
# when the engine's environment is broken — the bootstrap launches it with
# cwd=/content/repo/Scripts/pipeline (phase4seg is an importable subdirectory there,
# and stdlib-only per names.py), but a guard costs nothing and removes the dependency.
DEFAULT_MARKER = "/content/hw_step_marker.json"
try:
    from phase4seg.names import hw_step_marker_path as _marker_path
    from phase4seg.names import pid_alive
except Exception:                                 # noqa: BLE001
    def _marker_path():
        return os.environ.get("HW_STEP_MARKER") or DEFAULT_MARKER

    def pid_alive(_pid):
        """Fallback: assume live. Degrades to pre-pid behaviour, never to a bare
        os.kill — names.pid_alive documents that os.kill(pid, 0) TERMINATES the
        target on Windows, so this must not be re-implemented here."""
        return True

HEADER = ("ts_utc,gpu_util_pct,gpu_mem_util_pct,gpu_mem_used_mb,gpu_power_w,"
          "cpu_pct,disk_read_mb_s,disk_write_mb_s,net_rx_mb_s,net_tx_mb_s,"
          "disk_used_gb,disk_free_gb,cpu_iowait_pct,step,run_tag\n")


def cpu_ticks():
    """(total, idle_incl_iowait, iowait) ticks since boot.

    Three values, not two: `idle` stays idle+iowait so cpu_pct's arithmetic — and
    therefore every v1 row already on Drive — is unchanged, while iowait is also
    returned on its own so it can be reported as a first-class reading.
    """
    with open("/proc/stat") as f:
        p = f.readline().split()[1:]
    vals = [int(x) for x in p[:8]]
    idle = vals[3] + vals[4]                     # idle + iowait
    return sum(vals), idle, vals[4]


def cpu_pct(prev, cur):
    dt_, didle = cur[0] - prev[0], cur[1] - prev[1]
    return round(100.0 * (dt_ - didle) / dt_, 1) if dt_ > 0 else ""


def cpu_iowait_pct(prev, cur):
    """Share of the interval the CPU spent blocked on I/O. Blank on a zero interval.

    Deliberately NOT subtracted from cpu_pct: "busy" and "blocked" are different
    facts about the same seconds, and a step that reads 3% cpu_pct with 40%
    cpu_iowait_pct is starving on the mount, not idle.
    """
    dt_ = cur[0] - prev[0]
    dio = cur[2] - prev[2]
    return round(100.0 * dio / dt_, 1) if dt_ > 0 else ""


PHASE_OPEN = "open"          # the default when a marker carries no `phase` key at all


def read_marker(path):
    """(step_cell, run_tag) from the marker, or ("", "") for "no step open".

    THE PHASE SUFFIX. A marker may carry `phase` — the vocabulary is owned by
    phase4seg.names.hw_step_marker_path: "open" (a StepLogger step is running; also
    what an absent key means, because StepLogger writes no phase), "launching" (the
    queue has spawned the engine but StepLogger has not opened yet) and "verifying"
    (the queue's post-step VERIFY). Anything but open is appended to the step as
    `<step>#<phase>`, so the sample is still attributed to its step AND the harvest
    can separate engine time from queue time (harvest_hw_attribution.py::norm_step
    splits on the "#"). Nothing here writes a phase; this side only reads one.

    Why it is worth a suffix rather than a new column: the queue's own work around a
    step has no marker at all, so it lands in the harvest as `(between)` —
    indistinguishable from a machine doing nothing. Read the `spdc1,(between),marker`
    row of phase4/qc/hw_step_attribution.csv: a CPU runtime with cpu50_frac at zero
    and iowait10_frac dominant, i.e. that time was spent BLOCKED ON I/O, not idling.
    That session is live, so read the row for the fractions rather than this sentence.
    Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §7 makes the same point at scale:
    `(between steps)` is the second-largest bucket in the table and none of it is
    attributable to anything today.

    An unknown phase value passes through unaltered — the harvest reports what it
    reads. A phase with no step is not a reading about a step, so it is ignored.

    Every failure mode collapses to the same blank pair on purpose: absent (between
    steps — the normal case), unreadable, truncated, or not JSON at all. The reader
    of a telemetry file must never be the thing that stops telemetry, and a blank
    step is honestly "we do not know", which is what the harvest reports as
    "(between)".

    A STALE marker is the fifth failure mode, and the only one that would be worse
    than blank. _clear_marker() runs from finish() and nowhere else — no atexit hook,
    no signal handler — so a step killed with SIGKILL (phase4_train_queue.py's
    _kill_on_timeout does proc.kill(); so do OOM kills and preemption) leaves its
    marker behind with the engine gone. Without a liveness check every later sample
    would be stamped with the dead step: the VERIFY, the checkpoint drain, and the
    self-stop watchdog's idle minutes all billed to a train that already ended, on the
    `basis=marker` tier the harvest treats as exact. So the pid the writer records is
    read, not just stored. Presence-gated: an older marker with no pid keeps the old
    behaviour rather than being discarded.
    """
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        pid = d.get("pid")
        if pid is not None and not pid_alive(pid):
            return "", ""                         # writer is gone; its step is over
        step = str(d.get("step", "") or "")
        phase = str(d.get("phase", "") or "")
        if step and phase and phase != PHASE_OPEN:
            step = f"{step}#{phase}"
        return step, str(d.get("run_tag", "") or "")
    except Exception:                             # noqa: BLE001
        return "", ""


def resolve_out(out_path, header=HEADER):
    """Where to write, given what is already there. Never mixes two schemas in one file.

    A v1 file (12 columns) that suddenly gained 15-column rows would be unreadable by
    both the old arity check and any DictReader — and unrepairable, because nothing in
    the file says where the schema changed. So: same path when the file is absent,
    empty, or already carries THIS header; `{stem}_v2.csv` otherwise.

    Empty counts as absent — a logger that died before its first flush leaves a 0-byte
    file, and forking a _v2 for that would split one session across two files for no
    reason.
    """
    try:
        with open(out_path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        return out_path                           # absent (or unreadable): write here
    if not first.strip():
        return out_path                           # 0-byte / header-less stub
    if first.rstrip("\r\n") == header.rstrip("\r\n"):
        return out_path
    base = out_path[:-4] if out_path.endswith(".csv") else out_path
    return base + "_v2.csv"


def _csv_safe(s):
    """One malformed cell poisons every row after it for a naive reader — cheap guard."""
    return str(s).replace(",", " ").replace("\n", " ").replace("\r", " ")


def disk_bytes():
    rd = wr = 0
    with open("/proc/diskstats") as f:
        for ln in f:
            p = ln.split()
            if len(p) < 10 or p[2].startswith(("loop", "ram", "dm-")):
                continue
            if p[2][-1].isdigit() and not p[2].startswith("nvme"):
                continue                          # skip partitions of sdX (whole-disk row counts)
            rd += int(p[5]) * 512
            wr += int(p[9]) * 512
    return rd, wr


def net_bytes():
    rx = tx = 0
    with open("/proc/net/dev") as f:
        for ln in f.readlines()[2:]:
            name, rest = ln.split(":", 1)
            if name.strip() == "lo":
                continue
            p = rest.split()
            rx += int(p[0])
            tx += int(p[8])
    return rx, tx


def rate_mb(prev, cur, secs):
    return round((cur - prev) / secs / 1e6, 2) if secs > 0 and cur >= prev else ""


def gpu_row():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,"
             "memory.used,power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        p = [x.strip() for x in out.split(",")]
        return p[0], p[1], p[2], p[3]
    except Exception:                             # noqa: BLE001
        return "", "", "", ""


def gpu_identity():
    """(name, total_mem_mb) — WHAT the GPU is, asked once, not what it is doing.

    First line only: nvidia-smi prints one row per device and every Colab runtime this
    pipeline uses is single-GPU, so a second row would be news rather than data. Blank
    pair on a CPU runtime, where the binary is absent and the call raises.
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        p = [x.strip() for x in out.splitlines()[0].split(",")]
        return p[0], p[1]
    except Exception:                             # noqa: BLE001
        return "", ""


def _best_effort(fn, default=""):
    """Any field may be missing; NO field may raise. The exception surface here is wider
    than OSError on purpose — os.uname and os.statvfs do not EXIST off posix, so the
    Windows failure is AttributeError, and this helper runs on the code-plane box in
    tests."""
    try:
        v = fn()
    except Exception:                             # noqa: BLE001
        return default
    return default if v is None else v


def _meminfo_gb(path):
    """MemTotal from /proc/meminfo, in GB. Kernel reports kB; blank when unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("MemTotal:"):
                    return round(int(ln.split()[1]) * 1024 / 1e9, 1)
    except Exception:                             # noqa: BLE001
        pass
    return ""


def _disk_total_gb(mount):
    st = os.statvfs(mount)                        # AttributeError off posix — see caller
    return round(st.f_frsize * st.f_blocks / 1e9, 1)


def runtime_facts(session, marker, mount="/content", meminfo="/proc/meminfo"):
    """What this machine IS — the constants a per-sample row cannot carry.

    Every column of hw_{session}.csv says what the runtime was doing; nothing anywhere
    says what it was. So a session that reads 0% GPU for six hours cannot be told from
    a session that had no GPU (`gpu_present` in the harvest infers it from blank cells,
    which is an inference, not a reading), and hours cannot be priced, because an A100
    hour and a free CPU hour are the same number and different money.

    Every field is independently best-effort and blank on failure: this runs immediately
    before the sampling loop, and a logger that dies gathering metadata has thrown away
    the measurement it exists for. Off posix, /proc and statvfs are simply absent and
    the dict comes back mostly blank — which is the correct reading, not an error.
    """
    name, mem = gpu_identity()
    return {
        "session": session,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": _best_effort(socket.gethostname),
        "vcpus": _best_effort(os.cpu_count),
        "ram_gb": _meminfo_gb(meminfo),
        "disk_total_gb": _best_effort(lambda: _disk_total_gb(mount)),
        "gpu_name": name,
        "gpu_mem_mb": mem,
        "kernel": _best_effort(lambda: os.uname().release),
        "python": sys.version.split()[0],
        "marker_path": marker,
    }


def write_meta(path, facts):
    """Write the runtime facts ONCE. Existing file wins; nothing here ever rewrites it.

    Write-once because these are start-of-life constants: a rewrite could only move
    `started_utc` forward, and a session whose logger was restarted mid-run would lose
    the timestamp that dates its first sample.

    Temp + os.replace, the same publish StepLogger uses for the marker: a Drive blink
    halfway through a direct write leaves a truncated JSON that the write-once rule
    would then protect forever. Returns True if it wrote.
    """
    tmp = ""                                      # bound before the try: the except path
    try:                                          # reads it, and os.path.exists can raise
        if os.path.exists(path):
            return False
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(facts, f, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception:                             # noqa: BLE001
        try:
            if tmp:
                os.remove(tmp)                    # no orphan beside the meta file
        except Exception:                         # noqa: BLE001
            pass
        return False


def _write_bytes(path, data):
    """The one place bytes reach the mount. Its own function so the mid-write failure
    can be FIRED in a test (qc/test_vm_hwlogger.py patches it to write half and raise),
    which is the only way to show that `out` survives a blink intact."""
    with open(path, "wb") as f:
        f.write(data)


def mirror_once(local, out):
    """Publish the WHOLE local spool onto `out`, atomically. True if it landed.

    Whole-file, not incremental, and that is the entire design. An append can fail HALF
    DONE — the old flush did, and hw_spdg.csv carries the fragment it left behind —
    whereas a temp-plus-os.replace either happens or does not: `out` is
    the previous complete file until the instant it is the new complete file. Nothing is
    buffered here, so a failure needs no recovery: the next tick republishes the same
    local file, one minute newer.

    CUT AT THE LAST NEWLINE. The sampler flushes each row as it writes it, so the spool
    can be read mid-row; publishing those bytes would put a torn line on Drive by a
    different road than the one this replaced. The partial row lands next tick, whole.

    The temp carries the pid, and every failure removes it, because publishes DO fail
    here: `phase4/qc/ledger_recovery/` holds 22 orphaned `*.csv.part.*` files left by
    the queue's own temp-plus-replace on this same mount. Routine, must not collide
    between processes, must not accumulate.
    """
    part = f"{out}.part.{os.getpid()}"
    try:
        with open(local, "rb") as f:
            data = f.read()
        _write_bytes(part, data[:data.rfind(b"\n") + 1])
        os.replace(part, out)
        return True
    except Exception:                             # noqa: BLE001
        try:
            os.remove(part)
        except OSError:
            pass
        return False


def _mirror_worker(local, out, tick, lock):
    """The Drive side of the logger, on its OWN thread, so a 60 s FUSE stall costs
    telemetry timeliness and never a single sample.

    Waits on an Event the sampler SETS and this clears — a flag, not a queue: a mirror
    that outlasts several ticks runs once more when it finishes rather than working
    through a backlog of identical requests, because every tick asks for the same thing
    (publish the file as it now stands).
    """
    while True:
        tick.wait()
        tick.clear()
        with lock:
            mirror_once(local, out)


def _final_mirror(local, out, lock, timeout=30.0):
    """One last publish on the way out, so the final minute is not lost.

    Under the lock, because the worker may be mid-publish and two writers would share a
    `.part.{pid}` name. If the worker holds it past `timeout` it is itself publishing a
    spool at most one tick old, so this gives up rather than delaying the exit.
    """
    if lock.acquire(timeout=timeout):
        try:
            mirror_once(local, out)
        finally:
            lock.release()


def _install_exit_mirror(local, out, lock):
    """SIGTERM -> SystemExit -> atexit -> one final mirror.

    The handler only exits: SystemExit is a BaseException, so it passes straight through
    the sampling loop's `except Exception` guard instead of being swallowed as one more
    bad sample, and atexit then runs the publish on the main thread with the loop stopped.
    """
    atexit.register(_final_mirror, local, out, lock)
    try:
        signal.signal(signal.SIGTERM, lambda *_a: sys.exit(0))
    except (ValueError, OSError, AttributeError):  # not the main thread / no SIGTERM
        pass


def _open_local(local, out):
    """Open the session's local spool, SEEDED with what Drive already holds.

    Seeding is what makes a whole-file mirror safe. `out` may already carry this
    session's earlier samples — a logger relaunched under the same session name, whether
    by hand or by a supervisor — and a spool that began at the header would erase them.
    So: `out` absent -> the spool starts with HEADER; `out` present -> its bytes are the
    spool's first bytes, cut at the last newline in case the OLD appender left a torn
    tail there. resolve_out has already guaranteed `out` is either absent, empty, or
    this exact schema, so the seed is never another schema's rows.

    PRESENT-BUT-UNREADABLE FALLS BACK, and that distinction is the whole point of using
    os.stat rather than os.path.exists (which reports a mount blink as "absent"): only
    FileNotFoundError means there is nothing to preserve. Any other OSError leaves the
    caller appending to Drive the old way, which cannot shorten a file it did not read.

    Returns an append handle, or None (with a stderr note) if this VM cannot give us a
    spool at all. Never creates the directory: same rule as the step marker — a logger
    that invents a path writes telemetry where nothing will look for it.
    """
    try:
        d = os.path.dirname(local) or "."
        if not os.path.isdir(d):
            raise OSError(f"no such directory: {d}")
        try:
            present = os.stat(out).st_size > 0
        except FileNotFoundError:
            present = False
        if present:
            with open(out, "rb") as f:
                seed = f.read()
            seed = seed[:seed.rfind(b"\n") + 1]
            if not seed.strip():
                seed = HEADER.encode("utf-8")
        else:
            seed = HEADER.encode("utf-8")
        _write_bytes(local, seed)
        return open(local, "a", encoding="utf-8", newline="")
    except OSError as e:                          # unusable spool, not a dead logger
        print(f"vm_hwlogger: no local spool ({e}); appending straight to {out}",
              file=sys.stderr, flush=True)
        return None


def _local_sink(fh):
    """Every sample, on the spot, flushed. One line per write is what lets the mirror
    read a consistent file at any moment; the except is because a full local disk — or a
    handle already closed on the way out — must cost samples, not the process. ValueError
    is in there deliberately: that, not OSError, is what a closed file raises."""
    def sink(row):
        try:
            fh.write(row)
            fh.flush()
        except (OSError, ValueError):
            pass
    return sink


def _drive_appender(out, need_header):
    """The pre-2026-09-08 path, kept for the VM that cannot spool locally: buffer the
    rows and append them to Drive. It is the behaviour this file's own docstring
    measures the cost of — sampling stops for the length of the append — so it runs only
    when the alternative is no telemetry at all."""
    buf = [HEADER] if need_header else []

    def flush():
        if not buf:
            return
        try:
            with open(out, "a") as f:
                f.writelines(buf)
            buf.clear()
        except OSError:
            pass                                  # Drive blink: keep rows, retry next tick
    return buf.append, flush


def sample_loop(sink, marker, interval=5.0, flush_every=12, flush=None, max_samples=None):
    """Read the counters every `interval` s, hand each finished row to `sink`, and call
    `flush` every `flush_every` samples. NOTHING here knows about Drive.

    That is the fix: `sink` is a local write and `flush` is `Event.set` in the normal
    path, so neither can block on the mount. The split is also what makes the loop
    testable off-VM — the blocking test drives it with a mirror that never returns and
    watches the rows keep coming (qc/test_vm_hwlogger.py).

    `max_samples` exists for those tests. In production it is None and this never returns.

    THE PRIMING READ IS BEST-EFFORT TOO. Rates are deltas, so the first read only seeds
    them; if /proc is unreadable at that instant (or absent entirely, as off posix) the
    loop must still start and let the first successful sample become the seed, rather
    than dying before the session's first row.
    """
    try:
        pc, pd, pn, pt = cpu_ticks(), disk_bytes(), net_bytes(), time.time()
    except Exception:                             # noqa: BLE001
        pc = pd = pn = None
        pt = time.time()
    n = 0
    while max_samples is None or n < max_samples:
        time.sleep(interval)
        n += 1
        try:
            cc, cd, cn, ct = cpu_ticks(), disk_bytes(), net_bytes(), time.time()
            secs = ct - pt
            g = gpu_row()
            try:
                du = shutil.disk_usage("/content")
                used = round(du.used / 1e9, 1)
                free = round(du.free / 1e9, 1)
            except OSError:
                used = free = ""
            step, run_tag = read_marker(marker)
            if pc is not None:                    # no previous read -> no deltas yet
                sink(",".join(str(x) for x in (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    g[0], g[1], g[2], g[3], cpu_pct(pc, cc),
                    rate_mb(pd[0], cd[0], secs), rate_mb(pd[1], cd[1], secs),
                    rate_mb(pn[0], cn[0], secs), rate_mb(pn[1], cn[1], secs),
                    used, free, cpu_iowait_pct(pc, cc),
                    _csv_safe(step), _csv_safe(run_tag))) + "\n")
            pc, pd, pn, pt = cc, cd, cn, ct
        except Exception:                         # noqa: BLE001
            pass                                  # a bad sample must never kill the logger
        if flush is not None and n % flush_every == 0:
            flush()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--flush-every", type=int, default=12,
                    help="samples between Drive publishes (12 x 5 s = one a minute)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--local-dir", default=None,
                    help="where the spool lives (default: the marker's own directory, "
                         f"else {LOCAL_DIR}). Local disk — never the FUSE mount")
    ap.add_argument("--marker", default=None,
                    help="open-step marker JSON (default: phase4seg.names."
                         "hw_step_marker_path(), i.e. $HW_STEP_MARKER or "
                         f"{DEFAULT_MARKER})")
    a = ap.parse_args()
    marker = a.marker or _marker_path()
    out = resolve_out(a.out or f"{DRIVE}/phase4/logs/hw_{a.session}.csv")

    # Beside the samples, never inside them. Derived from `out`'s directory rather than
    # DRIVE so a local `--out` run stays local — on the VM the two are the same path.
    # Its schema fork does not apply: hw_meta is a new name, so it has only ever had one.
    write_meta(os.path.join(os.path.dirname(out) or ".", f"hw_meta_{a.session}.json"),
               runtime_facts(a.session, marker))

    # The spool sits where the marker does — /content on the VM, the test's tmp_path
    # locally — because that directory is already known-writable local disk on the one
    # machine this runs on for real.
    local = os.path.join(a.local_dir or os.path.dirname(marker) or LOCAL_DIR,
                         f"hw_{a.session}.local.csv")
    fh = _open_local(local, out)
    if fh is None:
        try:
            need_header = os.path.getsize(out) == 0    # absent OR the 0-byte stub
        except OSError:
            need_header = True
        sink, flush = _drive_appender(out, need_header)
        sample_loop(sink, marker, a.interval, a.flush_every, flush)
        return

    tick, lock = threading.Event(), threading.Lock()
    threading.Thread(target=_mirror_worker, args=(local, out, tick, lock),
                     daemon=True).start()
    _install_exit_mirror(local, out, lock)
    try:
        sample_loop(_local_sink(fh), marker, a.interval, a.flush_every, tick.set)
    finally:
        # CLOSED BEFORE THE ATEXIT MIRROR RUNS, which is the only reason this is a
        # try/finally and not a bare call. Interpreter teardown would otherwise flush
        # this handle AFTER the final publish had already read the spool, and the last
        # row would live only in a buffer nobody had written yet.
        fh.close()


if __name__ == "__main__":
    main()

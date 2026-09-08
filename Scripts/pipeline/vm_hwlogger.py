r"""vm_hwlogger.py — raw hardware telemetry, one CSV per session, straight to Drive.

Kam, 2026-09-02: "We should be tracking GPU utilization, CPU utilization,
read/write speed, and virtual disk space." This is that tracker: a stdlib
VM-side sampler (5 s cadence, 60 s buffered flush so the mount is written once
a minute, not 12 times) appending

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
is try/except-blank, and a failed flush keeps rows for the next flush.

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
import json
import os
import shutil
import socket
import subprocess
import sys
import time

DRIVE = "/content/drive/MyDrive/treedata"

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--flush-every", type=int, default=12)
    ap.add_argument("--out", default=None)
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

    rows = []
    try:
        need_header = os.path.getsize(out) == 0    # absent OR the 0-byte stub
    except OSError:
        need_header = True
    if need_header:
        rows.append(HEADER)
    pc, pd, pn, pt = cpu_ticks(), disk_bytes(), net_bytes(), time.time()
    n = 0
    while True:
        time.sleep(a.interval)
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
            rows.append(",".join(str(x) for x in (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                g[0], g[1], g[2], g[3], cpu_pct(pc, cc),
                rate_mb(pd[0], cd[0], secs), rate_mb(pd[1], cd[1], secs),
                rate_mb(pn[0], cn[0], secs), rate_mb(pn[1], cn[1], secs),
                used, free, cpu_iowait_pct(pc, cc),
                _csv_safe(step), _csv_safe(run_tag))) + "\n")
            pc, pd, pn, pt = cc, cd, cn, ct
        except Exception:                         # noqa: BLE001
            pass                                  # a bad sample must never kill the logger
        if len(rows) and n % a.flush_every == 0:
            try:
                with open(out, "a") as f:
                    f.writelines(rows)
                rows = []
            except OSError:
                pass                              # Drive blink: keep rows, retry next flush


if __name__ == "__main__":
    main()

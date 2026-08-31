r"""vm_heartbeat.py — VM-side liveness beacon for the headless Colab runtimes.

WHY: checking on a runtime used to cost a `colab exec` round-trip (slow, and
token-heavy whenever Claude drives it). This flips the direction: the VM PUSHES a
tiny state file to the data lake every 60 s, and the local, near-free
`qc/runtime_health.py` reads it. `colab exec` probing is then reserved for
DIAGNOSIS after a health flag fires, not for routine "is it alive?" checks.

Runs ON THE VM under nohup, launched by the bootstrap (pipeline/gen_vm_bootstrap.py)
right after BOOTSTRAP_READY:

    nohup python -u /content/repo/Scripts/pipeline/vm_heartbeat.py --session <name> \
        > /content/vm_heartbeat.log 2>&1 &

Writes (OVERWRITE, atomic tmp+os.replace, < 2 KB) every --interval seconds:

    {BASE}/phase4/logs/heartbeat_{session}.json

STDLIB ONLY and never imports torch / rasterio / the engine: the beacon must survive
anything the queue does to the environment, and must never be the reason a run dies.
It reads state, it never acts on it: no killing, no restarting, no writing anywhere
except its own heartbeat file. Reader-side rules live in qc/runtime_health.py.

Prior samples are carried IN the JSON (`newest_nohup.prev_size`, `prev_scratch_gb`,
`prev_vfs_dirty_gb`, `prev_ts_utc`) so the local reader can judge "stalled", "idle
GPU" and "uploads not draining" from ONE file, with no local state to keep and
nothing to poll twice. They are null on the first cycle after a (re)start — readers
must no-op then, or every restart reads as a stall.

Data-flow fields (2026-08-26): `cpu_pct` (two-sample /proc/stat delta over the cycle),
`vfs_cache_gb` (total rclone write cache) and `vfs_dirty_gb` (the UPLOAD BACKLOG —
bytes written through the mount that have NOT reached Drive). See `_vfs_bytes` for why
those two are different numbers; the difference is what keeps runtime_health's
UPLOAD_BACKLOG_STUCK from crying wolf after every clean drain.

Multi-VM safety: both runtimes (cap 2) write nohup logs and status CSVs into the
SAME Drive dirs, so a plain newest-by-mtime glob can latch onto the OTHER session's
files. The globs are therefore filtered by this VM's own queue stem, taken from its
`--queue` argument (basename minus .yaml — queues may run from outside the repo).

Local validation without a VM (documented override; proves the JSON shape):
    py -3.12 pipeline/vm_heartbeat.py --session test --once \
        --base <scratch>\lake --scratch <scratch>\scratch
On Windows `ps`/`nvidia-smi`/the mount are absent or empty — every affected field
degrades to null rather than raising.
"""
from phase4seg.names import clean_argv
import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time

MOUNT = "/content/drive/MyDrive/treedata"     # the exact path every script expects
SCRATCH = "/content/phase4_scratch"
TAGS_FILE = "/content/queue_tags.json"        # the queue's own tag declaration (D11)
VFS_CACHE = "/root/.cache/rclone"             # rclone's write cache (see _vfs_bytes)
BREADCRUMB = "/content"                       # LOCAL disk: survives a lost mount
MAXCHARS = 200                                # cap on every free-text field (2 KB budget)
QUEUE_RE = re.compile(r"--queue\s+(\S+)")

# D12 (2026-08-29): SESSION NAMES WERE SELF-ASSERTED AND UNENFORCED.
# The beacon writes heartbeat_{session}.json, with `session` taken verbatim from
# --session. Nothing checked that two VMs were not handed the same name, and the
# writes are plain overwrites, so a duplicate name means two runtimes take turns
# stamping ONE file. Every reader — runtime_health, the dashboard, the dup-tag
# guard — then sees a single blended "session" that is alternately one VM and the
# other: fresh when either is alive, and mount_ok/queue_proc/gpu belonging to
# whichever wrote last. Neither VM can be found, and neither looks dead.
#
# A name cannot be made unique from inside the VM (the Colab CLI hands it down),
# so instead the beacon proves WHO it is and refuses to overwrite someone else:
# INSTANCE_ID is unique per beacon process, it goes into every heartbeat, and a
# beacon that finds a FRESH heartbeat carrying a different instance moves to
# heartbeat_{session}__conflict-{id}.json rather than clobbering it. That name is
# deliberately visible: runtime_health flags a heartbeat with no CLI session entry
# as ORPHAN_HEARTBEAT, which is exactly the alarm a name collision deserves.
INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}-{secrets.token_hex(3)}"
CLAIM_STALE_SEC = 300                         # older than this = the other beacon is dead


def _run(cmd, timeout=15):
    """List-form (never shell=True) so the shell's own cmdline cannot match the
    pattern we are grepping for. Any failure -> '' (Windows has no ps/pgrep)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _procs():
    """[(pid, args)] for the queue/engine processes, this beacon excluded."""
    me = str(os.getpid())
    out = []
    for ln in _run(["ps", "-eo", "pid,args"]).splitlines():
        parts = ln.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue                                   # header line
        pid, args = parts
        if pid == me or "vm_heartbeat" in args:
            continue
        if "phase4_train_queue" in args or "phase4_semantic_finetune" in args:
            out.append((pid, args))
    return out


def _gpu(nsamp=3, sleep=1.0):
    """nvidia-smi -> {name, util_pct, util_max_pct, mem_used_mb}, or None on a CPU
    runtime. util is the MEAN of nsamp samples, never one reading: utilization.gpu
    is instantaneous and inference is input-bound, so a single sample reads 0 most
    of the time even at full tilt (measured; same lesson as the dashboard probe)."""
    g = _run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used",
              "--format=csv,noheader,nounits"], timeout=20).strip().splitlines()
    if not g or "," not in g[0]:
        return None
    name, util, mem = [x.strip() for x in g[0].split(",")[:3]]
    vals = [int(util)] if util.isdigit() else []
    for _ in range(max(0, nsamp - 1)):
        time.sleep(sleep)
        v = _run(["nvidia-smi", "--query-gpu=utilization.gpu",
                  "--format=csv,noheader,nounits"], timeout=10).strip().splitlines()
        if v and v[0].strip().isdigit():
            vals.append(int(v[0].strip()))
    return {"name": name[:MAXCHARS],
            "util_pct": round(sum(vals) / len(vals)) if vals else None,
            "util_max_pct": max(vals) if vals else None,
            "mem_used_mb": int(mem) if mem.isdigit() else None,
            "util_n": len(vals)}


def _dir_bytes(root, cap=50000):
    """Cheap recursive size via os.scandir (no hashing, no du subprocess). The entry
    cap keeps a runaway tile dir from turning the beacon into a disk crawler."""
    total = seen = 0
    stack = [root]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    seen += 1
                    if seen > cap:
                        return total
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def _cpu_snap():
    """(busy+idle jiffies, idle+iowait jiffies) from /proc/stat's aggregate line.

    None off Linux (the documented local-test override runs on Windows) — the caller
    then reports cpu_pct null rather than raising, per the module's degrade promise."""
    try:
        with open("/proc/stat") as f:
            p = f.readline().split()
        if p and p[0] == "cpu" and len(p) > 5:
            v = [int(x) for x in p[1:11]]
            return sum(v), v[3] + v[4]
    except (OSError, ValueError, IndexError):
        pass
    return None


def _cpu_pct(a, b):
    """Overall busy percent between two _cpu_snap() readings (None if either failed)."""
    if not a or not b or b[0] <= a[0]:
        return None
    return round(100.0 * (1.0 - (b[1] - a[1]) / float(b[0] - a[0])), 1)


def _vfs_bytes(root=VFS_CACHE, cap=4000):
    """(cache_bytes, dirty_bytes|None) for the rclone write cache.

    The lake is an rclone FUSE mount run with `--vfs-cache-mode writes`, so every write
    lands in this cache first and is uploaded asynchronously. TOTAL cache size is NOT
    the upload backlog: an item that has finished uploading STAYS cached, with
    `"Dirty": false` in its vfsMeta JSON, for the retention window. The backlog is the
    sum of `Size` over the vfsMeta items whose JSON says `Dirty: true` (field layout
    read off the live A100, 2026-08-26).

    dirty is None when the meta tree is unreadable or the entry cap is hit — readers
    must no-op on None, never guess. A drivefs VM (or Windows) has no such dir -> (0,0).
    """
    if not os.path.isdir(root):
        return 0, 0
    cache = _dir_bytes(root)
    meta = os.path.join(root, "vfsMeta")
    if not os.path.isdir(meta):
        return cache, 0
    dirty = n = 0
    ok = True
    stack = [meta]
    while stack and ok:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                            continue
                    except OSError:
                        continue
                    n += 1
                    if n > cap:
                        ok = False
                        break
                    try:
                        with open(e.path) as fh:
                            j = json.load(fh)
                        if j.get("Dirty"):
                            dirty += int(j.get("Size") or 0)
                    except (OSError, ValueError, TypeError):
                        pass
        except OSError:
            pass
    return cache, (dirty if ok else None)


def _is_status_name(name):
    """Is this a real run-outcome ledger file? A DELIBERATE TWIN of
    phase4seg.names.is_status_file, kept local because this beacon must keep running when
    the engine package is unimportable — it is the liveness signal, and a failed import
    here costs the ability to see any VM at all.

    A twin is only safe while it is proven equivalent, so
    qc/test_status_discovery.py::test_vm_heartbeat_agrees_with_the_shared_rule checks both
    against the same corpus. Edit one, the test fails.

    WHY IT WAS NEEDED (2026-08-31): _newest's stem filter below is CONDITIONAL. When the
    queue-process regex finds nothing, stem is None, the filter is skipped entirely, and
    every `train_queue_status*.csv` on the lake is a candidate — including
    `train_queue_status.CONTAMINATED-BY-TEST-20260829.csv`, which is still sitting there.
    The exemption that excused this file from the shared rule claimed the rename "breaks
    the _{stem}_ match it requires"; on the stem=None path there is no such match to break.
    """
    if not (name.startswith("train_queue_status") and name.endswith(".csv")):
        return False
    rest = name[len("train_queue_status"):-len(".csv")]
    if rest and not rest.startswith("_"):
        return False                      # a dot-suffixed rename, e.g. ".CONTAMINATED-..."
    return all(c.isalnum() or c in "._-" for c in rest)


def _newest(dirpath, prefix, suffix, stem):
    """Newest file matching prefix*suffix, filtered to THIS VM's queue stem when we
    know it (see the multi-VM note in the module docstring)."""
    best = None
    try:
        with os.scandir(dirpath) as it:
            for e in it:
                n = e.name
                if not (n.startswith(prefix) and n.endswith(suffix)):
                    continue
                # Reject a file renamed aside even when stem is None (the filter below
                # is conditional and would otherwise let it through). Status family only.
                if prefix == "train_queue_status" and not _is_status_name(n):
                    continue
                if stem and ("_" + stem + "_") not in n and not n.endswith("_" + stem + suffix):
                    continue
                try:
                    st = e.stat()
                except OSError:
                    continue
                if best is None or st.st_mtime > best[0]:
                    best = (st.st_mtime, n, st.st_size, e.path)
    except OSError:
        return None
    if best is None:
        return None
    return {"name": best[1], "size": best[2], "_path": best[3]}


def _last_line(path, size, nbytes=4000):
    """Last non-empty line of a file, read from the tail only."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, size - nbytes))
            chunk = f.read()
    except OSError:
        return None
    for raw in reversed(re.split(rb"[\r\n]+", chunk)):
        if raw.strip():
            return raw.decode("utf-8", "replace")[:MAXCHARS]
    return None


def run_tags(queue_pid, path=TAGS_FILE):
    """The run tags the queue on THIS VM declares it owns, or None.

    D11 (2026-08-29). The cross-VM duplicate-tag guard used to infer a tag by
    regexing `--run-tag (\\S+)` out of the ENGINE's cmdline, as captured in this
    beacon's `engine_proc` field — which is:

      * None whenever no engine is running. That is every gap BETWEEN steps, and
        the whole of the labels/evaluate work. The queue owns the tag continuously;
        the engine only exists in bursts. A guard that reads the engine sees an
        unowned tag most of the time.
      * truncated to the LAST 200 characters of the cmdline (MAXCHARS), so whether
        the tag is visible at all depends on how many flags follow it.

    So the queue now DECLARES its tags to a local file and the beacon republishes
    them on its own 60 s cadence — a stable answer for the whole life of the queue,
    with a freshness guarantee the queue's file cannot give on its own (a train
    step can run for hours between the queue's own writes).

    Published ONLY when the recorded pid is the live queue process this beacon can
    see in /proc. A queue that died leaves its declaration behind, and a dead run
    must never go on holding a tag.
    """
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not queue_pid or str(d.get("pid")) != str(queue_pid):
        return None
    return d


def sample(base, scratch, session, prev, vfs_cache=VFS_CACHE, tags_file=TAGS_FILE):
    """One heartbeat dict. `prev` carries the previous cycle's samples (or {})."""
    c0, t0 = _cpu_snap(), time.time()      # the CPU window spans this whole cycle
    logs = os.path.join(base, "phase4", "logs")
    qc = os.path.join(base, "phase4", "qc")
    mount_ok = os.path.isdir(os.path.join(base, "phase4"))

    procs = _procs()
    queue_proc = engine_proc = stem = None
    for pid, args in procs:
        if "phase4_train_queue" in args:
            queue_proc = pid
            m = QUEUE_RE.search(args)
            if m:
                q = os.path.basename(m.group(1))       # queues may run from outside the repo
                stem = q[:-5] if q.endswith(".yaml") else q
        elif "phase4_semantic_finetune" in args:
            engine_proc = args[-MAXCHARS:]

    nohup = _newest(logs, "train_queue_nohup_", ".log", stem) if mount_ok else None
    status = _newest(qc, "train_queue_status", ".csv", stem) if mount_ok else None
    if status:
        status["last_line"] = _last_line(status.pop("_path"), status["size"])
    if nohup:
        nohup.pop("_path", None)
        nohup["prev_size"] = prev.get("nohup_size")

    decl = run_tags(queue_proc, tags_file) or {}
    sc = _dir_bytes(scratch) if os.path.isdir(scratch) else 0
    gpu = _gpu()                                    # sleeps ~2 s: the CPU window
    cache, dirty = _vfs_bytes(vfs_cache)
    if time.time() - t0 < 0.3:                      # CPU runtime: _gpu() returned at once
        time.sleep(0.5)
    return {
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session": session,
        "mount_ok": mount_ok,
        "gpu": gpu,
        "cpu_pct": _cpu_pct(c0, _cpu_snap()),
        "queue_proc": queue_proc,
        "engine_proc": engine_proc,
        # D11: what this VM is working on, DECLARED by the queue rather than
        # scraped out of a truncated engine cmdline. Null when no live queue
        # declares anything — never a stale claim from a dead run.
        "run_tags": decl.get("tags"),
        "run_tags_pid": decl.get("pid"),
        "queue_file": str(decl.get("queue") or "")[:MAXCHARS] or None,
        "queue_job": str(decl.get("job") or "")[:MAXCHARS] or None,
        "queue_step": str(decl.get("step") or "")[:MAXCHARS] or None,
        "newest_nohup": nohup,
        "newest_status": status,
        "scratch_gb": round(sc / 1e9, 3),
        "prev_scratch_gb": prev.get("scratch_gb"),
        # vfs_cache_gb = the whole rclone write cache; vfs_dirty_gb = the UPLOAD
        # BACKLOG (written, not yet on Drive). Different numbers — see _vfs_bytes.
        "vfs_cache_gb": round(cache / 1e9, 3),
        "vfs_dirty_gb": None if dirty is None else round(dirty / 1e9, 3),
        "prev_vfs_dirty_gb": prev.get("vfs_dirty_gb"),
        "prev_ts_utc": prev.get("ts_utc"),
        "beacon_pid": os.getpid(),
        # D12/D13: WHO and WHERE. instance_id is what lets a second beacon detect
        # that this session name is already taken instead of overwriting it, and
        # what lets a reader tell two runtimes apart when they were.
        "instance_id": INSTANCE_ID,
        "host": socket.gethostname(),
    }


def write_atomic(path, obj):
    """tmp + os.replace in the SAME dir: a reader never sees a half-written file, and
    the reader-side staleness rule never trips on a torn read.

    D4 (2026-08-29): the replace landed on an EXISTING destination every cycle
    after the first, on the rclone FUSE mount — the case the mount canary never
    proved (core.py::_deploy_smoothed_keeping_raw concedes it). The old file is
    renamed aside first so both
    renames have an absent destination, and it is restored if the publish fails,
    so a beacon can never leave NO heartbeat behind.

    Both staging suffixes go AFTER the extension. Every reader of these files
    filters on a `.json` suffix, so `.json.tmp.<pid>` and `.json.prev.<token>`
    match nothing — a `.tmp.json` would be read as a heartbeat of its own.
    """
    tmp = f"{path}.tmp.{os.getpid()}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=True, separators=(",", ":"))
    aside = None
    if os.path.exists(path):
        aside = f"{path}.prev.{secrets.token_hex(3)}"
        try:
            os.replace(path, aside)
        except FileNotFoundError:
            aside = None
    try:
        os.replace(tmp, path)
    except OSError:
        if aside is not None:
            try:
                os.replace(aside, path)
            except OSError:
                pass
        raise
    if aside is not None:
        try:
            os.remove(aside)
        except OSError:
            pass


def name_is_ours(path, instance, stale_sec=CLAIM_STALE_SEC):
    """May this beacon write `path`? → (True, None) or (False, why).

    False only when the file holds a heartbeat from a DIFFERENT, RECENTLY ALIVE
    beacon — i.e. two runtimes were handed the same --session. Absent, unreadable,
    ours, stale, or written by a pre-D12 build all answer True: this must never be
    the reason oversight stops, and refusing on a file we cannot interpret would
    silence a beacon over a bad byte.
    """
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return True, None
    other = d.get("instance_id")
    if not other or other == instance:
        return True, None
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return True, None
    if age > stale_sec:
        return True, None
    return False, (f"session name already held by a live beacon "
                   f"({str(other)[:60]}, {int(age)}s old)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="colab CLI session name")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true", help="one cycle, then exit (local test)")
    ap.add_argument("--cycles", type=int, default=0, help="stop after N cycles (0 = forever)")
    ap.add_argument("--base", default=MOUNT, help="data lake root (override for local tests)")
    ap.add_argument("--scratch", default=SCRATCH)
    ap.add_argument("--vfs-cache", default=VFS_CACHE,
                    help="rclone write-cache dir (override for local tests)")
    ap.add_argument("--tags-file", default=TAGS_FILE,
                    help="the queue's run-tag declaration (override for local tests)")
    ap.add_argument("--breadcrumb", default=BREADCRUMB,
                    help="LOCAL dir for the final mount_ok=false heartbeat")
    a = ap.parse_args(clean_argv())   # Colab %run injection

    name = f"heartbeat_{a.session}.json"
    out = os.path.join(a.base, "phase4", "logs", name)
    prev, n = {}, 0
    conflict = None                 # set once, then permanent: never flap names
    print(f"vm_heartbeat session={a.session} -> {out} every {a.interval}s "
          f"(pid {os.getpid()}, instance {INSTANCE_ID})", flush=True)
    while True:
        hb = sample(a.base, a.scratch, a.session, prev, a.vfs_cache, a.tags_file)
        try:
            if not hb["mount_ok"]:
                raise OSError("mount gone: " + a.base)
            if conflict is None:
                ok, why = name_is_ours(out, INSTANCE_ID)
                if not ok:
                    # D12: two runtimes were handed the same --session. Do NOT
                    # overwrite the other beacon — that is what made both VMs
                    # invisible. Take a distinct name and make the collision loud;
                    # runtime_health will flag it as an ORPHAN_HEARTBEAT, which is
                    # the right alarm.
                    conflict = why
                    name = f"heartbeat_{a.session}__conflict-{INSTANCE_ID[-6:]}.json"
                    out = os.path.join(a.base, "phase4", "logs", name)
                    print(f"vm_heartbeat: SESSION NAME COLLISION — {why}. "
                          f"Publishing to {name} instead. TWO RUNTIMES SHARE THE "
                          f"NAME {a.session!r}; one of them is not the VM you "
                          f"think it is.", flush=True)
            if conflict:
                hb["session_requested"] = a.session
                hb["session_conflict"] = conflict[:MAXCHARS]
            write_atomic(out, hb)
        except OSError as e:
            # The mount vanished (or went read-only). Leave a breadcrumb on LOCAL disk
            # so a later `colab exec` can prove the VM outlived its mount, and stop:
            # a beacon spinning against a dead mount only makes noise.
            hb["mount_ok"] = False
            hb["exit_reason"] = f"{type(e).__name__}: {e}"[:MAXCHARS]
            try:
                write_atomic(os.path.join(a.breadcrumb, name), hb)
            except OSError:
                pass
            print(f"vm_heartbeat: mount unusable ({e}) -> breadcrumb in {a.breadcrumb}; exit",
                  flush=True)
            return 0
        n += 1
        prev = {"nohup_size": (hb["newest_nohup"] or {}).get("size"),
                "scratch_gb": hb["scratch_gb"], "vfs_dirty_gb": hb["vfs_dirty_gb"],
                "ts_utc": hb["ts_utc"]}
        if a.once or (a.cycles and n >= a.cycles):
            print(f"vm_heartbeat: {n} cycle(s) written, exit", flush=True)
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())

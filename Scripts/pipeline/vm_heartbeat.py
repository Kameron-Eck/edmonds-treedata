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

Two prior samples are carried IN the JSON (`newest_nohup.prev_size`,
`prev_scratch_gb`, `prev_ts_utc`) so the local reader can judge "stalled" and
"idle GPU" from ONE file, with no local state to keep and nothing to poll twice.
They are null on the first cycle after a (re)start — readers must no-op then,
or every restart reads as a stall.

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
import argparse
import json
import os
import re
import subprocess
import sys
import time

MOUNT = "/content/drive/MyDrive/treedata"     # the exact path every script expects
SCRATCH = "/content/phase4_scratch"
BREADCRUMB = "/content"                       # LOCAL disk: survives a lost mount
MAXCHARS = 200                                # cap on every free-text field (2 KB budget)
QUEUE_RE = re.compile(r"--queue\s+(\S+)")


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


def sample(base, scratch, session, prev):
    """One heartbeat dict. `prev` carries the previous cycle's samples (or {})."""
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

    sc = _dir_bytes(scratch) if os.path.isdir(scratch) else 0
    return {
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session": session,
        "mount_ok": mount_ok,
        "gpu": _gpu(),
        "queue_proc": queue_proc,
        "engine_proc": engine_proc,
        "newest_nohup": nohup,
        "newest_status": status,
        "scratch_gb": round(sc / 1e9, 3),
        "prev_scratch_gb": prev.get("scratch_gb"),
        "prev_ts_utc": prev.get("ts_utc"),
        "beacon_pid": os.getpid(),
    }


def write_atomic(path, obj):
    """tmp + os.replace in the SAME dir: a reader never sees a half-written file, and
    the reader-side staleness rule never trips on a torn read."""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=True, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="colab CLI session name")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true", help="one cycle, then exit (local test)")
    ap.add_argument("--cycles", type=int, default=0, help="stop after N cycles (0 = forever)")
    ap.add_argument("--base", default=MOUNT, help="data lake root (override for local tests)")
    ap.add_argument("--scratch", default=SCRATCH)
    ap.add_argument("--breadcrumb", default=BREADCRUMB,
                    help="LOCAL dir for the final mount_ok=false heartbeat")
    a = ap.parse_args([x for x in sys.argv[1:]
                       if not (x == "-f" or x.endswith(".json"))])   # Colab %run injection

    name = f"heartbeat_{a.session}.json"
    out = os.path.join(a.base, "phase4", "logs", name)
    prev, n = {}, 0
    print(f"vm_heartbeat session={a.session} -> {out} every {a.interval}s (pid {os.getpid()})",
          flush=True)
    while True:
        hb = sample(a.base, a.scratch, a.session, prev)
        try:
            if not hb["mount_ok"]:
                raise OSError("mount gone: " + a.base)
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
                "scratch_gb": hb["scratch_gb"], "ts_utc": hb["ts_utc"]}
        if a.once or (a.cycles and n >= a.cycles):
            print(f"vm_heartbeat: {n} cycle(s) written, exit", flush=True)
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())

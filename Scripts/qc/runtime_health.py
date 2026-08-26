r"""runtime_health.py — ONE local command that answers "are the runtimes healthy?".

The oversight contract (COLAB_AUTONOMY_SETUP.md, "Oversight"): routine checking is
this script — it reads only local files (the G: Drive mirror + the colab CLI's own
session store), costs no `colab exec`, no GPU, no billing, and a handful of output
tokens. `colab exec` probing is reserved for DIAGNOSIS *after* a flag fires here.

    py -3.12 qc/runtime_health.py            # one line per session + exit code
    py -3.12 qc/runtime_health.py --json     # machine-readable
    py -3.12 qc/runtime_health.py --watch 60 # poll locally, still zero colab exec

Exit code:  0 = all OK   1 = warnings   2 = critical.

Inputs:
  * {BASE}/phase4/logs/heartbeat_{session}.json — pushed every 60 s by the VM-side
    beacon (pipeline/vm_heartbeat.py), launched by the bootstrap. It carries its own
    previous samples (prev_size / prev_scratch_gb), which is what makes the stall and
    idle-GPU rules STATELESS here: one file read, no local history, no double poll.
  * {BASE}/phase4/qc/train_queue_status*.csv — merged via watch_queue._rows (one home
    for that merge, same as runtime_dashboard).
  * ~/.config/colab-cli/sessions.json — READ, never `colab sessions`: that command
    prunes sessions as a side effect and has orphaned a live billing VM (2026-08-22).

Deterministic rules (each prints its NAME when it fires — the name is the finding):
  HEARTBEAT_STALE   crit  ts_utc older than --stale-min (default 5) for a session the
                          CLI still knows: VM dead, beacon dead, or the mount broke.
                          NOTE: the G: mirror adds its own lag, so confirm with
                          `colab exec` before acting on this one.
  OLD_HEARTBEAT     ok    stale beat for a session the CLI no longer lists = the file a
                          deliberately stopped VM left behind. Quiet by design.
  MOUNT_LOST        crit  a heartbeat that says mount_ok=false.
  QUEUE_DEAD        crit  heartbeat FRESH but no queue process, while its status file
                          still shows RUNNING steps -> the queue died under nohup.
  STALL             warn  engine process alive but its nohup log has not grown since
                          the previous sample (no-ops when prev_size is null).
  GPU_IDLE_IN_TRAIN warn  util < --idle-pct during `--step train` AND scratch stable
                          (stable scratch = not staging, so idle is not just I/O).
  UPLOAD_BACKLOG_STUCK warn  vfs_dirty_gb > --backlog-gb, UNCHANGED since the previous
                          beat, and no queue/engine process: bytes were written through
                          the rclone mount and have not reached Drive, and nothing is
                          still producing them. Stopping that VM discards the outputs —
                          the 2026-08-26 failure. Keyed on DIRTY bytes, never on total
                          cache size: with `--vfs-cache-mode writes` an uploaded file
                          stays cached (`Dirty:false`) for the retention window, so
                          total size would WARN after every clean drain. No-ops when
                          the field is absent (a beacon older than 2026-08-26) or null.
  NO_HEARTBEAT      warn  a live CLI session with no heartbeat file (pre-beacon VM, or
                          the bootstrap's nohup line never ran). Degrade, never crash:
                          the status CSVs are still summarized.
  ORPHAN_HEARTBEAT  warn  a FRESH heartbeat with no CLI session entry = the 2026-08-22
                          prune failure (a billing VM the CLI forgot). qc/colab_readopt.py.
  TERMINAL          ok    every job in the launch has its job-end VERIFY row; prints the
                          verdict. Exit 1 (not 0) if any job's verdict is a BAD state.

Timestamps: heartbeat ts_utc is real UTC; status-CSV `ts` is the queue's naive
`datetime.now()` on a VM whose clock is UTC, so it is read as UTC (documented
assumption — it is what makes row ages comparable to heartbeat ages).
"""
import argparse
import csv
import datetime as _dt
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import watch_queue                                                   # noqa: E402
from watch_queue import _rows as merged_status_rows, BAD as BAD_STATES  # noqa: E402

SESSIONS_JSON = Path(os.path.expanduser("~/.config/colab-cli/sessions.json"))
CRIT, WARN, OK = 2, 1, 0
UTC = _dt.timezone.utc


def _now():
    return _dt.datetime.now(UTC)


def _age_s(ts, fmt):
    """Age in seconds of a timestamp string, or None if unparseable."""
    try:
        t = _dt.datetime.strptime(ts, fmt).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None
    return (_now() - t).total_seconds()


def _hms(sec):
    if sec is None:
        return "?"
    sec = int(sec)
    if sec < 90:
        return f"{sec}s"
    if sec < 5400:
        return f"{sec / 60:.1f}m"
    return f"{sec / 3600:.1f}h"


def _gb(n):
    return "?" if n is None else f"{n:.1f}GB"


# ── inputs ─────────────────────────────────────────────────────────────────────
def cli_sessions(path=None):
    """Session names from the CLI's store FILE (no side effects — see module docstring)."""
    try:
        data = json.loads(Path(path or SESSIONS_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: {"hardware": v.get("accelerator"), "variant": v.get("variant"),
                "keep_alive_pid": v.get("keep_alive_pid")} for k, v in data.items()}


def heartbeats(logs_dir):
    """{session: {"hb": dict} | {"error": str}} from heartbeat_*.json."""
    out = {}
    try:
        names = sorted(p for p in os.listdir(logs_dir)
                       if p.startswith("heartbeat_") and p.endswith(".json"))
    except OSError:
        return out
    for n in names:
        sess = n[len("heartbeat_"):-len(".json")]
        try:
            hb = json.loads(Path(logs_dir, n).read_text(encoding="utf-8"))
            out[sess] = {"hb": hb} if isinstance(hb, dict) else {"error": "not a JSON object"}
        except (OSError, ValueError) as e:
            out[sess] = {"error": f"{type(e).__name__}: {e}"[:120]}
    return out


def launches(qc_dir):
    """Per-launch view of the status CSVs: {filename: {...}}. Launch-scoped (not the
    merged view) because a crashed launch leaves RUNNING rows in ITS file forever —
    scoping is what stops those from flagging QUEUE_DEAD for all eternity."""
    out = {}
    try:
        files = sorted(Path(qc_dir).glob("train_queue_status*.csv"))
    except OSError:
        return out
    for f in files:
        try:
            with open(f, encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            continue
        if not rows:
            continue
        jobs = {r.get("job", "") for r in rows if r.get("job")}
        ended = {r["job"] for r in rows if r.get("step") == "VERIFY" and r.get("job")}
        bad = sorted({r["job"] for r in rows
                      if r.get("state") in BAD_STATES and r.get("job")})
        running = [r for r in rows if r.get("state") == "RUNNING"]
        last = max((r.get("ts", "") for r in rows), default="")
        out[f.name] = {
            "file": f.name,
            "stem": f.name[len("train_queue_status_"):-len(".csv")]
                    if f.name.startswith("train_queue_status_") else f.name,
            "jobs": len(jobs), "done": len(ended & jobs), "bad_jobs": bad,
            "running": [f"{r.get('job','')}/{r.get('step','')}" for r in running],
            "terminal": bool(jobs) and jobs <= ended,
            "last_ts": last, "last_age_s": _age_s(last, "%Y-%m-%d %H:%M:%S"),
        }
    return out


# ── rules ──────────────────────────────────────────────────────────────────────
def judge(sess, entry, meta, lch, args):
    """Apply every rule to one session. Returns (severity, flags, dict)."""
    flags, sev = [], OK
    d = {"session": sess, "hardware": (meta or {}).get("hardware"),
         "known_to_cli": meta is not None}

    if entry is None:
        flags.append("NO_HEARTBEAT")
        return WARN, flags, d
    if "error" in entry:
        flags.append("HEARTBEAT_UNREADABLE")
        d["error"] = entry["error"]
        return WARN, flags, d

    hb = entry["hb"]
    age = _age_s(hb.get("ts_utc", ""), "%Y-%m-%dT%H:%M:%SZ")
    gpu = hb.get("gpu") or {}
    engine = hb.get("engine_proc")
    nohup = hb.get("newest_nohup") or {}
    d.update(hb_age_s=None if age is None else round(age), gpu=gpu or None,
             queue_proc=hb.get("queue_proc"), engine_proc=engine,
             scratch_gb=hb.get("scratch_gb"), mount_ok=hb.get("mount_ok"),
             cpu_pct=hb.get("cpu_pct"), vfs_cache_gb=hb.get("vfs_cache_gb"),
             vfs_dirty_gb=hb.get("vfs_dirty_gb"),
             nohup=nohup.get("name"), nohup_size=nohup.get("size"),
             nohup_prev_size=nohup.get("prev_size"))

    stale = age is None or age > args.stale_min * 60
    if meta is None:
        # Not in the CLI store. `colab stop` DELETES the entry (state.store.remove, in
        # the CLI's commands/session.py) but nothing deletes the heartbeat FILE — so a
        # stale beat with no entry is the ordinary leftover of a deliberately stopped
        # VM. Under "STOP: always autonomous" that is the state after EVERY normal run,
        # so it must read OK: a routine tick that returns CRITICAL all night after a
        # clean shutdown would destroy the exit-code contract and send us straight back
        # to `colab exec` probing. Only a FRESH orphan is a finding.
        if stale:
            flags.append(f"OLD_HEARTBEAT({_hms(age)}, stopped-session leftover)")
            return OK, flags, d
        flags.append("ORPHAN_HEARTBEAT")           # fresh VM the CLI store forgot
        sev = max(sev, WARN)
    if stale:
        flags.append(f"HEARTBEAT_STALE({_hms(age)})")
        return max(sev, CRIT), flags, d            # everything below needs a fresh beat
    if hb.get("mount_ok") is False:
        flags.append("MOUNT_LOST")
        sev = max(sev, CRIT)

    # the launch this VM is actually writing (never another runtime's file)
    named = (hb.get("newest_status") or {}).get("name")
    launch = lch.get(named) if named else None
    d["launch"] = launch["stem"] if launch else None

    if hb.get("queue_proc") is None and launch and launch["running"]:
        flags.append("QUEUE_DEAD(" + ",".join(launch["running"][:2]) + ")")
        sev = max(sev, CRIT)

    prev = nohup.get("prev_size")
    if engine and prev is not None and nohup.get("size") == prev:
        flags.append(f"STALL(log flat at {nohup.get('size')}B)")
        sev = max(sev, WARN)

    # Written-but-not-uploaded bytes, going nowhere, with nothing left to produce them.
    # Every clause is required: `is not None` on both samples (an older beacon has no
    # such field, and the first beat after a restart has no prev — either must no-op,
    # not guess), unchanged (draining is healthy, however large), and no producer
    # (a running engine legitimately keeps the cache full).
    dirty, pdirty = hb.get("vfs_dirty_gb"), hb.get("prev_vfs_dirty_gb")
    if (dirty is not None and pdirty is not None and dirty > args.backlog_gb
            and dirty == pdirty and not hb.get("queue_proc") and not engine):
        flags.append(f"UPLOAD_BACKLOG_STUCK({dirty:.1f}GB written, not uploaded)")
        sev = max(sev, WARN)

    util, pscr = gpu.get("util_pct"), hb.get("prev_scratch_gb")
    if (util is not None and util < args.idle_pct and engine and "--step train" in engine
            and pscr is not None and pscr == hb.get("scratch_gb")):
        flags.append(f"GPU_IDLE_IN_TRAIN({util}%)")
        sev = max(sev, WARN)

    if launch and launch["terminal"]:
        verdict = "ALL_OK" if not launch["bad_jobs"] else "FAILED:" + ",".join(launch["bad_jobs"])
        flags.append(f"TERMINAL[{launch['jobs']} jobs {verdict}]")
        if launch["bad_jobs"]:
            sev = max(sev, WARN)
    return sev, flags, d


def line(sess, sev, flags, d):
    """The one line per session."""
    tag = {OK: "OK  ", WARN: "WARN", CRIT: "CRIT"}[sev]
    bits = [f"[{sess:<8}] {tag}"]
    bits.append(" ".join(flags) if flags else "healthy")
    if d.get("hb_age_s") is not None:
        bits.append(f"hb {_hms(d['hb_age_s'])}")
    g = d.get("gpu")
    if g:
        bits.append(f"{g.get('name','gpu')} util {g.get('util_pct')}%"
                    f"/max {g.get('util_max_pct')}% mem {g.get('mem_used_mb')}MB")
    elif d.get("hb_age_s") is not None:
        bits.append("cpu-runtime")
    if d.get("cpu_pct") is not None:
        bits.append(f"cpu {d['cpu_pct']:.0f}%")
    if d.get("queue_proc"):
        bits.append(f"queue pid {d['queue_proc']}")
    if d.get("engine_proc"):
        e = d["engine_proc"]
        i = e.find(" --")            # the flags, not a tail slice cutting mid-word
        bits.append("engine " + (e[i + 1:i + 61] if i >= 0 else e[-60:]).strip())
    if d.get("nohup_size") is not None and d.get("nohup_prev_size") is not None:
        bits.append(f"log +{d['nohup_size'] - d['nohup_prev_size']}B")
    if d.get("scratch_gb") is not None:
        bits.append(f"scratch {_gb(d['scratch_gb'])}")
    if d.get("vfs_dirty_gb") is not None:
        bits.append(f"backlog {_gb(d['vfs_dirty_gb'])}")   # written, not yet on Drive
    if d.get("launch"):
        bits.append(d["launch"])
    if d.get("error"):
        bits.append(d["error"])
    return " | ".join(bits)


def report(args):
    base = Path(args.base) if args.base else watch_queue.BASE
    if args.base:                      # keep the merged reader pointed at the same lake
        watch_queue.STATUS = base / "phase4" / "qc" / "train_queue_status.csv"
    logs, qc = base / "phase4" / "logs", base / "phase4" / "qc"
    hbs, cli, lch = heartbeats(logs), cli_sessions(args.sessions_json), launches(qc)

    out, worst = [], OK
    for sess in sorted(set(cli) | set(hbs)):
        sev, flags, d = judge(sess, hbs.get(sess), cli.get(sess), lch, args)
        worst = max(worst, sev)
        out.append({"severity": sev, "flags": flags, **d})

    merged = merged_status_rows()
    recent = sorted((l for l in lch.values()
                     if l["last_age_s"] is not None
                     and l["last_age_s"] <= args.recent_hours * 3600),
                    key=lambda l: l["last_ts"])
    queues = {"merged_rows": len(merged), "files": len(lch),
              "newest_row_ts": merged[-1].get("ts") if merged else None,
              "recent": recent[-args.max_launches:]}
    return worst, out, queues, base


def render(worst, sessions, queues, base):
    print(f"runtime_health {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}  lake={base}")
    if not sessions:
        print("[sessions] none — no CLI session entries and no heartbeat files")
    for s in sessions:
        print(line(s["session"], s["severity"], s["flags"], s))
    for l in queues["recent"]:
        state = ("TERMINAL " + ("ALL_OK" if not l["bad_jobs"] else "FAILED:" + ",".join(l["bad_jobs"]))
                 if l["terminal"] else
                 ("RUNNING " + ",".join(l["running"][:2]) if l["running"]
                  else f"{l['done']}/{l['jobs']} jobs done"))
        print(f"[queues  ] {l['stem']}: {l['jobs']} jobs, {state}, "
              f"last row {l['last_ts']} ({_hms(l['last_age_s'])} ago)")
    print(f"[queues  ] merged: {queues['merged_rows']} rows / {queues['files']} status files"
          f"  newest {queues['newest_row_ts']}")
    if any("UPLOAD_BACKLOG_STUCK" in f for s in sessions for f in s["flags"]):
        print("note: do NOT stop that runtime — those bytes exist ONLY in its rclone write "
              "cache, on the VM's local disk, and die with the VM. Wait for the backlog to "
              "reach 0 before stopping. If it will not drain, copy the affected outputs out "
              "by another route (`rclone copy` from the VM) rather than stopping and hoping.")
    if any(("HEARTBEAT_STALE" in f or "QUEUE_DEAD" in f)
           for s in sessions for f in s["flags"]):
        print("note: the G: mirror lags the VM. Confirm with `colab exec` before acting — "
              "a CRIT that clears on the next tick was mirror lag, not a dead runtime "
              "(QUEUE_DEAD also fires briefly when a queue exits before its final rows sync).")
    print(f"exit {worst} ({ {0:'all OK', 1:'warnings', 2:'CRITICAL'}[worst] })")


def main():
    ap = argparse.ArgumentParser(description="local health of the Colab runtimes (no colab exec)")
    ap.add_argument("--stale-min", type=float, default=5.0,
                    help="heartbeat older than this many minutes = HEARTBEAT_STALE")
    ap.add_argument("--idle-pct", type=int, default=5, help="GPU_IDLE_IN_TRAIN threshold")
    ap.add_argument("--backlog-gb", type=float, default=0.5,
                    help="UPLOAD_BACKLOG_STUCK threshold on undrained (Dirty) rclone bytes")
    ap.add_argument("--recent-hours", type=float, default=48.0,
                    help="status launches newer than this are summarized")
    ap.add_argument("--max-launches", type=int, default=3)
    ap.add_argument("--base", default=None, help="data lake root override (tests)")
    ap.add_argument("--sessions-json", default=None,
                    help="colab CLI session store override (tests)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--watch", type=int, default=0, metavar="N",
                    help="re-check every N seconds (local reads only; Ctrl-C to stop)")
    # Colab's injected `-f <json>` (rule 4), dropped as a PAIR rather than by the usual
    # "any token ending in .json" test: this script owns a `--json` flag AND a
    # `--sessions-json <path.json>` option, and the blunt filter silently ate the
    # option's VALUE (measured, not theorised). Pairing on -f keeps both safe.
    argv, keep, prev = sys.argv[1:], [], ""
    for a in argv:
        if a == "-f" or (prev == "-f" and a.endswith(".json")):
            prev = a
            continue
        keep.append(a)
        prev = a
    args = ap.parse_args(keep)

    while True:
        worst, sessions, queues, base = report(args)
        if args.json:
            print(json.dumps({"exit": worst, "generated_utc": _now().isoformat(),
                              "lake": str(base), "sessions": sessions, "queues": queues},
                             ensure_ascii=True, indent=1))
        else:
            render(worst, sessions, queues, base)
        if not args.watch:
            return worst
        try:
            sys.stdout.flush()      # watch mode is often piped to a file: block
            time.sleep(args.watch)  # buffering would hide every cycle until exit
            print()
        except KeyboardInterrupt:
            print("stopped.")
            return worst


if __name__ == "__main__":
    sys.exit(main())

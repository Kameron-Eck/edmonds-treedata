r"""runtime_dashboard.py — local progress dashboard for the headless Colab queues (overhaul P11.6).

One browser page (http://127.0.0.1:8765; Tabler CSS + Chart.js from jsDelivr for the
chrome — the page still renders plain without internet) with a card per Colab CLI session: GPU
tier + utilisation, the queue it runs, per-job step chips (OK / RUNNING / FAIL …
from the merged status CSVs), the live tqdm progress bar of the current step with
ETA, elapsed vs the step ceiling (`phase4_train_queue.STEP_TIMEOUT_MIN`), staging /
lock lines, the scratch directory (the ortho growing), and the log tail. Flags
anything a human should look at: hard-fail rows, "two bulk copies" lock WARNINGs,
a stale log, a step past its ceiling, no queue process.

Read-only. Two data paths, because they have different freshness:
  * per VM, a tiny probe run through `colab exec` (ps, nvidia-smi, the scratch
    dir, the VM's OWN nohup log tail) — the only fresh source for tqdm lines: the
    Drive desktop mirror on G: lags minutes behind a file that is being appended;
  * local reads of the Drive mirror for the status CSVs, run manifests and the
    lock dir (small files; near-real-time).
No torch on the VM side, no GPU touched, no cells of the queue disturbed (the
queue runs under nohup; the probe shares the idle kernel).

Run it in a spare terminal during a Colab window (never a billed daemon):

    py -3.12 qc/runtime_dashboard.py                      # sessions from `colab sessions`
    py -3.12 qc/runtime_dashboard.py --sessions A,B --port 8765 --open
    py -3.12 qc/runtime_dashboard.py --once               # one JSON snapshot, no server
    py -3.12 qc/runtime_dashboard.py --no-exec            # G:-only (no colab exec)

The colab executable: $COLAB_EXE, else `colab` on PATH, else the uv tool shim.
"""
import argparse
import csv
import datetime as _dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))
sys.path.insert(0, str(HERE))
from phase4_train_queue import STEPS, STEP_TIMEOUT_MIN, BASE, QC_DIR  # noqa: E402  (one home)
from watch_queue import _rows as merged_status_rows, BAD as BAD_STATES  # noqa: E402

COLAB = (os.environ.get("COLAB_EXE") or shutil.which("colab")
         or os.path.expanduser(r"~\.local\bin\colab.exe"))
LOGS = BASE / "phase4" / "logs"
RUNS = BASE / "phase4" / "runs"
LOCKS = BASE / "phase4" / "locks"
QUEUE_DIR = SCRIPTS / "pipeline"

TQDM_RE = re.compile(r"(Inference|Writing tiles|Eval|City-wide scan|Threshold|Polygonize):\s+"
                     r"(\d+)%\|[^|]*\|\s*(\d+)/(\d+)\s+\[([\d:]+)<([\d:?]+),\s*([\d.]+)\s*([A-Za-z/]+)\]")
STEP_RE = re.compile(r"\[(\w+)\] Step (\d+): (.+?) ──")
EXIT_RE = re.compile(r"\[(\w+)/(\w+)\] exit=(-?\d+)\s+elapsed ([\d.]+) min")
LOCK_RE = re.compile(r"\b(staging|lock)\b")          # word-bounded: "blocked" must not match
SESS_RE = re.compile(r"^\[(.+?)\]\s+(\S+)\s+\|\s+Hardware:\s+(\S+)\s+\|\s+Variant:\s+(\S+)")
FLAG_WORDS = ("two bulk copies", "WARNING", "Traceback", "FAIL", "ERROR", "TIMEOUT",
              "DRYRUN_FAIL", "mount failed")

# VM-side probe: ASCII-only JSON on one line (colab.exe's stdout is cp1252 on Windows).
PROBE = r'''
import glob, json, os, re, subprocess, time
def sh(c, t=20):
    try:
        return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t).stdout
    except Exception as e:
        return "ERR %r" % (e,)
out = {"host": sh("hostname").strip(), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
procs = []
for ln in sh("ps -eo pid,etimes,pcpu,pmem,args").splitlines():
    if ("phase4_train_queue" in ln or "phase4_semantic_finetune" in ln) and "grep" not in ln:
        parts = ln.split(None, 4)
        if len(parts) == 5:
            procs.append({"pid": parts[0], "etimes": int(parts[1]), "cpu": parts[2], "mem": parts[3],
                          "args": parts[4][:300]})
out["procs"] = procs
g = sh("nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total "
       "--format=csv,noheader,nounits").strip()
out["gpu"] = [x.strip() for x in g.split(",")] if g and not g.startswith("ERR") and "," in g else None
# utilization.gpu is an INSTANTANEOUS sample: inference is input-bound (a 32-tile
# forward pass, then a wait while the next window is read off the ortho), so a single
# reading is 0 most of the time even at full tilt. Sample ~3 s and report mean/max.
if out["gpu"]:
    vals = []                       # -l/-lms are rejected alongside --query-gpu here: loop instead
    for _ in range(12):
        v = sh("nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits", t=8).strip()
        if v.isdigit():
            vals.append(int(v))
        time.sleep(0.25)
    if vals:
        out["gpu_util_mean"] = round(sum(vals) / len(vals))
        out["gpu_util_max"] = max(vals)
        out["gpu_util_n"] = len(vals)
sc = []
for p in sorted(glob.glob("/content/phase4_scratch/*")):
    try:
        st = os.stat(p); sc.append({"name": os.path.basename(p), "size": st.st_size, "mtime": int(st.st_mtime)})
    except OSError:
        pass
out["scratch"] = sc
queue = None
for p in procs:
    m = re.search(r"--queue\s+(\S+)", p["args"])
    if m:
        queue = m.group(1)
out["queue"] = queue
stem = queue[:-5] if queue and queue.endswith(".yaml") else None
logs = []
for lg in glob.glob("/content/drive/MyDrive/treedata/phase4/logs/train_queue_nohup_*.log"):
    if stem and ("_" + stem + "_") not in os.path.basename(lg):
        continue
    try:
        st = os.stat(lg)
    except OSError:
        continue
    logs.append((st.st_mtime, lg, st.st_size))
logs.sort()
if logs:
    mt, lg, size = logs[-1]
    with open(lg, "rb") as f:
        f.seek(max(0, size - 6000)); tail = f.read().decode("utf-8", "replace")
    # the tqdm flood pushes the step header out of the tail: scan the whole file
    # (tens of KB .. a few MB) for the last step header / staging-lock line
    last_step = last_lock = None
    try:
        with open(lg, "rb") as f:
            for raw in re.split(rb"[\r\n]+", f.read()):
                if b"] Step " in raw:
                    last_step = raw.decode("utf-8", "replace")[:200]
                    last_lock = None                      # lock lines belong to the current step only
                elif re.search(rb"\b(staging|lock)\b", raw):
                    last_lock = raw.decode("utf-8", "replace")[:200]
    except OSError:
        pass
    out["log"] = {"path": lg, "size": size, "mtime": int(mt), "age_s": int(time.time() - mt), "tail": tail,
                  "last_step": last_step, "last_lock": last_lock}
else:
    out["log"] = None
print("DASH_JSON " + json.dumps(out, ensure_ascii=True))
'''


# ── colab CLI ──────────────────────────────────────────────────────────────────
def run_colab(args, timeout=90):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run([COLAB, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=env)
    return r.returncode, r.stdout or "", r.stderr or ""


SESSIONS_JSON = Path(os.path.expanduser("~/.config/colab-cli/sessions.json"))


def colab_sessions():
    """Session names from the CLI's own store file — deliberately NOT `colab sessions`.

    That command runs sync_sessions(), which PRUNES any local session whose endpoint
    is missing from the current list_assignments() response; one partial list (the VMs
    are in different regions) permanently orphans a running, billing VM. Observed
    2026-08-22 mid-run: session A vanished from the store while its A100 kept working.
    Recover such a VM with qc/colab_readopt.py. Reading the file has no side effects.
    """
    try:
        data = json.loads(SESSIONS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [], f"sessions.json unreadable: {e}"
    rows = [{"name": k, "endpoint": v.get("endpoint"), "hardware": v.get("accelerator"),
             "variant": v.get("variant"), "keep_alive_pid": v.get("keep_alive_pid")}
            for k, v in sorted(data.items())]
    return rows, ""


TOOL_PY = os.environ.get("COLAB_TOOL_PY") or os.path.expanduser(
    r"~\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe")
READOPT = HERE / "colab_readopt.py"
ASSIGN_RE = re.compile(r"^\s*(\S+)\s+(\S+)\s+(\S+)\s+\[(.+?)\]\s*$")


def heal_sessions():
    """Run colab_readopt --heal: re-adopt orphans, refresh tokens before their 1 h
    expiry, respawn dead keep-alive daemons. Returns the list of actions taken.

    This is the safety net for the failure that cost three A100s on 2026-08-22: the
    CLI prunes a session on any transient error (a 404 from /api/kernels sufficed),
    which deletes the entry AND kills the heartbeat, and Colab then reclaims the
    still-computing VM ~15-25 min later. Healing on a schedule closes that window.
    """
    if not (Path(TOOL_PY).exists() and READOPT.exists()):
        return [], "colab_readopt.py or the CLI interpreter not found"
    try:
        r = subprocess.run([TOOL_PY, str(READOPT), "--heal"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        return [], f"heal: {e}"
    acted = [ln[len("HEAL "):] for ln in (r.stdout or "").splitlines()
             if ln.startswith("HEAL ") and not ln.startswith("HEAL nothing")]
    return acted, ("" if r.returncode == 0 else (r.stderr or "")[-200:])


def live_assignments():
    """Every live server-side assignment + whether it has a local name.

    Uses qc/colab_readopt.py --list on the CLI's own interpreter: it calls
    list_assignments() directly, so unlike `colab sessions` it never prunes the
    store. An assignment with no local name is a VM that BILLS but cannot be
    stopped by name — the dashboard flags it loudly; recover it with colab_readopt.
    """
    if not (Path(TOOL_PY).exists() and READOPT.exists()):
        return [], ""
    try:
        r = subprocess.run([TOOL_PY, str(READOPT), "--list"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90)
    except (OSError, subprocess.SubprocessError) as e:
        return [], f"list_assignments: {e}"
    rows = []
    for ln in (r.stdout or "").splitlines():
        m = ASSIGN_RE.match(ln)
        if m and m.group(1) != "live":
            rows.append({"endpoint": m.group(1), "accelerator": m.group(2), "variant": m.group(3),
                         "name": None if m.group(4).startswith("ORPHAN") else m.group(4)})
    return rows, ("" if rows else (r.stderr or "")[-200:])


_PROBE_PATH = None


def probe_session(name):
    global _PROBE_PATH
    if _PROBE_PATH is None:
        d = Path(tempfile.gettempdir()) / "edmonds_runtime_dashboard"
        d.mkdir(exist_ok=True)
        _PROBE_PATH = d / "probe.py"
        _PROBE_PATH.write_text(PROBE, encoding="utf-8")
    rc, out, err = run_colab(["exec", "-s", name, "-f", str(_PROBE_PATH), "--timeout", "60"], timeout=120)
    for ln in out.splitlines():
        if ln.startswith("DASH_JSON "):
            return json.loads(ln[len("DASH_JSON "):]), None
    return None, (err.strip() or out.strip() or "no DASH_JSON line")[-400:]


# ── local artifacts (Drive mirror) ─────────────────────────────────────────────
def read_queue_yaml(queue_file):
    try:
        import yaml
        with open(QUEUE_DIR / queue_file, encoding="utf-8") as f:
            jobs = yaml.safe_load(f) or []
        return [{"id": str(j.get("id")), "year": str(j.get("year")), "tag": j.get("tag", ""),
                 "expect": (j.get("expect") or "").strip()} for j in jobs if isinstance(j, dict)]
    except Exception as e:  # noqa: BLE001
        return [{"id": "?", "year": "?", "tag": "", "expect": f"queue yaml unreadable: {e}"}]


def status_rows_for(stem):
    """Rows from this queue's per-launch files, newest launch last."""
    rows = []
    for f in sorted(QC_DIR.glob(f"train_queue_status_{stem}_*.csv")):
        try:
            with open(f, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    r["_file"] = f.name
                    rows.append(r)
        except OSError:
            pass
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def latest_by_key(rows):
    out = {}
    for r in rows:
        out[(r.get("job"), r.get("step"))] = r
    return out


def parse_ts(s):
    try:
        return _dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=_dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def read_manifests(limit=10):
    out = []
    try:
        dirs = sorted([p for p in RUNS.iterdir() if p.is_dir()], key=lambda p: p.name)[-limit:]
    except OSError:
        return out
    for d in dirs:
        mf = d / "manifest.json"
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            out.append({"run_id": m.get("run_id"), "step": m.get("step"), "tag": m.get("run_tag"),
                        "branch": m.get("git_branch"), "sha": (m.get("git_sha") or "")[:7],
                        "gpu": m.get("gpu"), "years": list((m.get("years") or {}).keys())})
        except Exception:  # noqa: BLE001
            continue
    return out


def read_locks():
    try:
        return sorted(p.name for p in LOCKS.iterdir())
    except OSError:
        return []


# ── log parsing ────────────────────────────────────────────────────────────────
def parse_log_tail(tail):
    lines = [ln for ln in re.split(r"[\r\n]+", tail or "") if ln.strip()]
    step = None
    progress = None
    staging = None
    flags = []
    exits = []
    for ln in lines:
        m = STEP_RE.search(ln)
        if m:
            step = {"job": m.group(1), "n": int(m.group(2)), "title": m.group(3).strip()}
            progress = None
        m = TQDM_RE.search(ln)
        if m:
            progress = {"desc": m.group(1), "pct": int(m.group(2)), "n": int(m.group(3)),
                        "total": int(m.group(4)), "elapsed": m.group(5), "eta": m.group(6),
                        "rate": f"{m.group(7)} {m.group(8)}"}
        if LOCK_RE.search(ln):
            staging = ln.strip()[:200]
        m = EXIT_RE.search(ln)
        if m:
            exits.append({"job": m.group(1), "step": m.group(2), "rc": int(m.group(3)),
                          "min": float(m.group(4))})
        for w in FLAG_WORDS:
            if w in ln and "expect :" not in ln and "why    :" not in ln:
                flags.append(ln.strip()[:200])
                break
    # display tail: last 30 lines, tqdm lines collapsed to the last one
    shown = []
    for ln in lines:
        if TQDM_RE.search(ln):
            if shown and TQDM_RE.search(shown[-1]):
                shown[-1] = ln
            else:
                shown.append(ln)
        else:
            shown.append(ln)
    return {"step": step, "progress": progress, "staging": staging, "flags": flags[-5:],
            "exits": exits[-5:], "tail": [s[:220] for s in shown[-30:]]}


# ── assemble one session card ──────────────────────────────────────────────────
def build_card(sess, probe, probe_err, merged_latest, now):
    card = {"name": sess["name"], "endpoint": sess.get("endpoint"), "hardware": sess.get("hardware"),
            "probe_err": probe_err, "flags": []}
    if probe is None:
        card["flags"].append(f"probe failed: {probe_err}")
        return card
    card.update(host=probe.get("host"), vm_utc=probe.get("utc"), procs=probe.get("procs", []),
                scratch=probe.get("scratch", []), queue=probe.get("queue"))
    g = probe.get("gpu")
    if g and len(g) >= 4:
        card["gpu"] = {"name": g[0], "util": g[1], "mem_used": g[2], "mem_total": g[3],
                       "util_mean": probe.get("gpu_util_mean"), "util_max": probe.get("gpu_util_max"),
                       "util_n": probe.get("gpu_util_n")}
    else:
        card["gpu"] = None
    if not card["procs"]:
        card["flags"].append("no queue/engine process on the VM")
    ka = sess.get("keep_alive_pid")
    if keepalive_alive(ka) is False:
        card["flags"].append(f"KEEP-ALIVE DAEMON DEAD (pid {ka or 'none'}) — Colab reclaims an "
                             f"unheartbeated VM in ~15-25 min even mid-run; re-adopt with "
                             f"qc/colab_readopt.py to respawn it")
    card["keep_alive_pid"] = ka
    queue = card["queue"]
    stem = queue[:-5] if queue and queue.endswith(".yaml") else None
    # jobs + step chips
    jobs = read_queue_yaml(queue) if queue else []
    qrows = status_rows_for(stem) if stem else []
    qlatest = latest_by_key(qrows)
    running = None
    for j in jobs:
        chips = []
        for st in STEPS:
            r = qlatest.get((j["id"], st)) or merged_latest.get((j["id"], st))
            src = "this" if (j["id"], st) in qlatest else ("prior" if r else None)
            v = qlatest.get((j["id"], f"VERIFY:{st}")) or merged_latest.get((j["id"], f"VERIFY:{st}"))
            chips.append({"step": st, "state": (r or {}).get("state"), "minutes": (r or {}).get("minutes"),
                          "ts": (r or {}).get("ts"), "src": src, "verify": (v or {}).get("state")})
            if r and r.get("state") == "RUNNING" and src == "this":
                running = {"job": j["id"], "step": st, "ts": r.get("ts")}
        jend = qlatest.get((j["id"], "VERIFY")) or merged_latest.get((j["id"], "VERIFY"))
        j["steps"] = chips
        j["job_end"] = {"state": (jend or {}).get("state"), "detail": (jend or {}).get("detail")} if jend else None
    card["jobs"] = jobs
    # hard-fail rows in this queue's files
    cur_file = None                 # the status file of the launch that is running NOW
    if card["procs"] and qrows:
        cur_file = qrows[-1].get("_file")
    for r in qrows:
        if r.get("_file") != cur_file:
            continue                # a previous launch's failures are history, not this run's
        if r.get("state") in BAD_STATES or r.get("state") == "INTERRUPTED":
            card["flags"].append(f"{r.get('job')}/{r.get('step')} {r.get('state')} "
                                 f"{str(r.get('detail') or '')[:120]}")
    # current step: elapsed vs ceiling, progress
    lg = probe.get("log")
    parsed = parse_log_tail(lg["tail"]) if lg else parse_log_tail("")
    title = (parsed["step"] or {}).get("title")
    if title is None and lg and lg.get("last_step"):
        m = STEP_RE.search(lg["last_step"])
        title = m.group(3).strip() if m else None
    staging = parsed["staging"]
    if staging is None and lg and lg.get("last_lock") and not parsed["progress"]:
        staging = lg["last_lock"].strip()[:200]
    cur = None
    if running:
        t0 = parse_ts(running["ts"])
        el = (now - t0).total_seconds() / 60 if t0 else None
        ceil = STEP_TIMEOUT_MIN.get(running["step"])
        cur = {"job": running["job"], "step": running["step"], "started": running["ts"],
               "elapsed_min": round(el, 1) if el is not None else None, "ceiling_min": ceil,
               "title": title, "progress": parsed["progress"], "staging": staging}
        if el is not None and ceil and el > ceil:
            card["flags"].append(f"{running['job']}/{running['step']} past its {ceil}-min ceiling ({el:.0f} min)")
        # engine proc for this step?
        if not any("phase4_semantic_finetune" in p["args"] for p in card["procs"]):
            card["flags"].append("queue RUNNING row but no engine process on the VM")
    # What the step is actually DOING right now — "inference RUNNING" with an idle GPU is
    # normal during staging and model load; only the tile loop is GPU work (and even then it
    # is input-bound and bursty). Spell it out so an idle GPU is not read as a stall.
    if cur:
        if cur.get("progress"):
            cur["phase"] = "computing — GPU bursts between tile reads (input-bound, 0% is normal between batches)"
        elif cur.get("staging"):
            cur["phase"] = "waiting on the cross-runtime staging lock"
        else:
            fresh = [f for f in card.get("scratch", [])
                     if probe.get("utc") and f.get("mtime") and
                     (time.time() - f["mtime"]) < 180 and f.get("size", 0) > 1e8]
            memmb = 0
            try:
                memmb = int((card.get("gpu") or {}).get("mem_used") or 0)
            except ValueError:
                pass
            if fresh:
                f = max(fresh, key=lambda x: x["size"])
                cur["phase"] = (f"staging {f['name']} ({f['size'] / 1e9:.1f} GB copied) — disk I/O, "
                                f"GPU idle by design")
            elif memmb > 1000:
                cur["phase"] = f"model loaded ({memmb / 1024:.1f} GB VRAM) — tile loop starting"
            else:
                cur["phase"] = "starting up (no GPU work yet)"
    card["current"] = cur
    if lg:
        card["log"] = {"path": lg["path"], "size": lg["size"], "age_s": lg["age_s"], "tail": parsed["tail"],
                       "exits": parsed["exits"]}
        quiet_ok = 1200 if (cur or {}).get("step") == "train" else 600   # train prints per epoch
        if lg["age_s"] > quiet_ok and cur and cur.get("step") in ("train", "inference", "tile"):
            card["flags"].append(f"log silent for {lg['age_s'] // 60} min")
    else:
        card["log"] = None
        card["flags"].append("no nohup log for this queue on the VM")
    card["flags"].extend(parsed["flags"])
    # GPU idle during GPU steps — nvidia-smi is an instantaneous sample (0% between
    # batches is normal), so require two consecutive zero samples before flagging
    if card["gpu"] and cur and cur["step"] in ("train", "inference") and not cur.get("staging"):
        try:
            gg = card["gpu"]
            zero = (gg.get("util_max") == 0 if gg.get("util_max") is not None else int(gg["util"]) == 0)
            prev = _LAST_UTIL_ZERO.get(sess["name"], False)
            if zero and prev and cur.get("progress"):
                card["flags"].append("note: GPU idle across two full sampling windows while progress "
                                     "advances (input-bound step, or a stall if the bar stops moving)")
            _LAST_UTIL_ZERO[sess["name"]] = zero
        except ValueError:
            pass
    return card


_LAST_UTIL_ZERO = {}     # session name -> was the previous probe's GPU util 0%


def keepalive_alive(pid):
    """Is this session's keep-alive daemon still running?

    That daemon is the ONLY thing refreshing Colab's idle timer for the assignment;
    prune_session() kills it, and a session without it is reclaimed by Colab ~15-25
    min later even mid-computation (measured twice, 2026-08-22 — two lost inferences).
    Restore it with qc/colab_readopt.py, which re-adopts AND respawns the daemon.
    """
    if not pid:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                             capture_output=True, text=True, timeout=20).stdout
        return str(pid) in out
    except (OSError, ValueError, subprocess.SubprocessError):
        return None          # unknown — do not cry wolf


def hours_since_launch(card):
    """Hours since this queue's first status row (≈ VM billing minus ~3 min of bootstrap)."""
    q = card.get("queue")
    stem = q[:-5] if q and q.endswith(".yaml") else None
    if not stem:
        return None
    rows = status_rows_for(stem)
    t0 = parse_ts(rows[0]["ts"]) if rows else None
    if not t0:
        return None
    return round((_dt.datetime.now(_dt.timezone.utc) - t0).total_seconds() / 3600, 2)


# ── collector thread ───────────────────────────────────────────────────────────
class Collector(threading.Thread):
    def __init__(self, sessions, exec_interval, local_interval, no_exec):
        super().__init__(daemon=True)
        self.sessions = sessions
        self.exec_interval = exec_interval
        self.local_interval = local_interval
        self.no_exec = no_exec
        self.state = {"generated": None, "sessions": [], "errors": ["starting"]}
        self._probes = {}        # name -> (probe, err, ts)
        self._sess_rows = []
        self._sess_err = ""
        self._lock = threading.Lock()
        self._hist = {}          # session -> deque of {t, util, mem, n, total, rate}
        self._assign = []        # live server-side assignments (orphan detection)
        self._assign_err = ""
        self._heal_log = []      # recent self-healing actions (token/daemon/orphan)
        self._hist_json = "{}"

    def snapshot(self):
        with self._lock:
            return json.dumps(self.state)

    def history(self):
        with self._lock:
            return self._hist_json

    def _record_history(self, card, now):
        from collections import deque
        name = card.get("name")
        if not name or card.get("probe_err") or card.get("probe_age_s") is None:
            return
        d = self._hist.setdefault(name, deque(maxlen=720))      # 12 h at 60 s
        g = card.get("gpu") or {}
        pr = ((card.get("current") or {}).get("progress")) or {}
        rate = None
        if pr.get("rate"):
            try:
                rate = float(pr["rate"].split()[0])
            except ValueError:
                rate = None
        try:
            util = (g.get("util_mean") if g and g.get("util_mean") is not None
                    else (int(g.get("util")) if g else None))
            mem = int(g.get("mem_used")) if g else None
        except ValueError:
            util = mem = None
        pt = {"t": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "util": util, "mem": mem,
              "n": pr.get("n"), "total": pr.get("total"), "rate": rate}
        if d and d[-1]["t"] == pt["t"]:
            return
        if d and (pt["util"], pt["n"]) == (d[-1]["util"], d[-1]["n"]) and card.get("probe_age_s", 0) > 5:
            return                                           # same probe, nothing new
        d.append(pt)

    def refresh_sessions(self):
        try:
            self._sess_rows, self._sess_err = colab_sessions()
        except Exception as e:  # noqa: BLE001
            self._sess_err = repr(e)
        if not self.sessions:
            self.sessions = [r["name"] for r in self._sess_rows if r["name"] != "?"]

    def probe_all(self):
        for name in list(self.sessions):
            try:
                p, err = probe_session(name)
            except Exception as e:  # noqa: BLE001
                p, err = None, repr(e)
            self._probes[name] = (p, err, time.time())

    def assemble(self):
        now = _dt.datetime.now(_dt.timezone.utc)
        errors = []
        if self._sess_err:
            errors.append(f"colab sessions: {self._sess_err}")
        try:
            merged_latest = latest_by_key(merged_status_rows())
        except Exception as e:  # noqa: BLE001
            merged_latest, _ = {}, errors.append(f"status csv: {e!r}")
        by_name = {r["name"]: r for r in self._sess_rows}
        cards = []
        for name in self.sessions:
            sess = by_name.get(name, {"name": name})
            p, err, ts = self._probes.get(name, (None, "not probed yet", None))
            try:
                card = build_card(sess, p, err, merged_latest, now)
            except Exception as e:  # noqa: BLE001
                card = {"name": name, "flags": [f"card build error: {e!r}"]}
            card["probe_age_s"] = int(time.time() - ts) if ts else None
            card["hours_billed"] = hours_since_launch(card)
            self._record_history(card, now)
            cards.append(card)
        orphans = [a for a in self._assign if not a.get("name")]
        if orphans:
            errors.append(f"{len(orphans)} live assignment(s) with NO local name — billing but not "
                          f"stoppable by name; recover with qc/colab_readopt.py")
        if self._assign_err:
            errors.append(self._assign_err)
        state = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "sessions": cards,
                 "colab_sessions": self._sess_rows, "assignments": self._assign, "orphans": orphans,
                 "heal_log": self._heal_log,
                 "locks": read_locks(), "manifests": read_manifests(),
                 "errors": errors, "exec_interval": self.exec_interval, "no_exec": self.no_exec,
                 "base": str(BASE)}
        hist_json = json.dumps({k: list(v) for k, v in self._hist.items()})
        with self._lock:
            self.state = state
            self._hist_json = hist_json

    def run(self):
        last_exec = 0.0
        last_sess = 0.0
        while True:
            t = time.time()
            try:
                if t - last_sess >= 120:
                    if not self.no_exec:
                        acted, herr = heal_sessions()   # BEFORE reading the store
                        if acted:
                            self._heal_log = (self._heal_log + acted)[-10:]
                        if herr:
                            self._assign_err = herr
                    self.refresh_sessions()
                    self._assign, self._assign_err = live_assignments()
                    last_sess = t
                if not self.no_exec and t - last_exec >= self.exec_interval:
                    self.probe_all(); last_exec = time.time()
                self.assemble()
            except Exception as e:  # noqa: BLE001
                with self._lock:
                    self.state.setdefault("errors", []).append(f"collector: {e!r}")
            time.sleep(self.local_interval)


# ── HTTP ───────────────────────────────────────────────────────────────────────
HTML = r"""<!doctype html><html lang="en" data-bs-theme="dark"><head><meta charset="utf-8"><title>Edmonds runtimes</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0/dist/css/tabler.min.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
body{background:#0f1419}.card{background:#151c26;border-color:#24303f}.card-header{background:#121a23;border-color:#24303f}
.mono{font-family:ui-monospace,Consolas,monospace}.logbox{background:#0a0e13;border:1px solid #24303f;border-radius:6px;padding:10px;font-size:11.5px;max-height:280px;overflow:auto;white-space:pre-wrap;word-break:break-all;color:#b8c2d0}
/* Chart.js with maintainAspectRatio:false must live in a fixed-height, position:relative
   box with the canvas taken OUT of flow — otherwise each resize grows the parent, which
   resizes the canvas again: the page scrolls away downwards forever. */
.chartbox{position:relative;height:80px;width:100%;overflow:hidden}
.chartbox>canvas{position:absolute!important;top:0;left:0;width:100%!important;height:100%!important;display:block}.steps .step-item{font-size:12px}.chip{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;margin:2px 4px 2px 0;background:#24303f;color:#9fb0c5}
.chip.OK{background:#0f3d24;color:#7ee2a3}.chip.RUNNING{background:#15325a;color:#8fc3ff;animation:pulse 1.6s infinite}.chip.FAIL,.chip.ERROR,.chip.TIMEOUT,.chip.INTERRUPTED{background:#4a1a1a;color:#ffb0b0}.chip.prior{opacity:.65}
@keyframes pulse{50%{opacity:.55}}.kv dt{color:#8696ab;font-weight:500}.muted{color:#8696ab}
</style></head><body>
<div class="page">
<header class="navbar navbar-expand-md d-print-none" style="background:#121a23;border-bottom:1px solid #24303f">
 <div class="container-xl">
  <h1 class="navbar-brand mb-0"><span class="text-primary">●</span>&nbsp;Edmonds Colab runtimes</h1>
  <div class="ms-auto d-flex align-items-center gap-3 small">
   <span id="gen" class="muted"></span>
   <span id="errs" class="badge bg-red-lt" style="display:none"></span>
   <label class="muted">window&nbsp;<select id="win" class="form-select form-select-sm d-inline-block" style="width:84px"><option value="60">1 h</option><option value="120">2 h</option><option value="360">6 h</option><option value="720">12 h</option></select></label>
   <label class="muted">rate&nbsp;<input id="rate" class="form-control form-control-sm d-inline-block" style="width:90px" placeholder="CU or $ /h"></label>
  </div>
 </div>
</header>
<div class="page-body"><div class="container-xl">
 <div class="row row-cards" id="cards"></div>
 <div class="card mt-3"><div class="card-header"><h3 class="card-title">Sessions · locks · manifests</h3></div><div class="card-body" id="extra"></div></div>
</div></div></div>
<script>
const fmtB=b=>b>=1e9?(b/1e9).toFixed(2)+' GB':b>=1e6?(b/1e6).toFixed(1)+' MB':b+' B';
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const charts={};
const rateEl=document.getElementById('rate');try{rateEl.value=localStorage.getItem('edm_rate')||''}catch(e){}
rateEl.addEventListener('change',()=>{try{localStorage.setItem('edm_rate',rateEl.value)}catch(e){};tick();});
function stepsHtml(j){return (j.steps||[]).map(st=>{const cls=(st.state||'')+(st.src==='prior'?' prior':'');
 return `<span class="chip ${cls}" title="${esc(st.ts||'')}${st.verify?' · VERIFY '+esc(st.verify):''}">${esc(st.step)}${st.state?' · '+esc(st.state):''}${st.minutes?' · '+esc(st.minutes)+'m':''}${st.verify&&st.verify!=='OK'?' ⚠':''}</span>`}).join('');}
function card(s){
 const g=s.gpu,c=s.current,util=g?(g.util_mean!=null?g.util_mean:+g.util):0,mem=g?100*g.mem_used/g.mem_total:0;
 const hours=s.hours_billed??null,rate=parseFloat(rateEl.value);
 let h=`<div class="col-lg-6"><div class="card">
 <div class="card-header"><div><h3 class="card-title mb-0">Session ${esc(s.name)} <span class="muted fw-normal">· ${esc(s.queue||'no queue process')}</span></h3>
 <div class="muted small">host ${esc(s.host||'?')} · probe ${s.probe_age_s??'?'}s ago${hours!=null?` · ${hours.toFixed(2)} h billed${rate?` ≈ ${(hours*rate).toFixed(1)}`:''}`:''}</div></div>
 <div class="card-actions"><span class="badge bg-azure-lt">${esc(g?g.name:(s.hardware||'?'))}</span></div></div>
 <div class="card-body">`;
 if(s.flags&&s.flags.length)h+=s.flags.map(f=>`<div class="alert ${f.startsWith('note:')?'alert-info':'alert-danger'} py-2 mb-2">${esc(f)}</div>`).join('');
 h+=`<div class="row g-3"><div class="col-6"><div class="d-flex justify-content-between small"><span class="muted">${c&&c.phase&&!c.progress?'GPU util <span class="text-warning" title="the step is not in its GPU loop yet">(idle: '+esc(c.phase.split(' — ')[0])+')</span>':'GPU util'}${g&&g.util_n?' <span title="mean / peak over the sampling window — inference is input-bound, so a single reading is 0 most of the time">(mean/peak)</span>':''}</span><span>${g?(g.util_mean!=null?`${g.util_mean}% / ${g.util_max}%`:esc(g.util)+'%'):'–'}</span></div><div class="progress progress-sm"><div class="progress-bar bg-green" style="width:${util}%"></div><div class="progress-bar bg-green-lt" style="width:${Math.max(0,(g&&g.util_max!=null?g.util_max:util)-util)}%"></div></div></div>
 <div class="col-6"><div class="d-flex justify-content-between small"><span class="muted">GPU memory</span><span>${g?`${(g.mem_used/1024).toFixed(1)} / ${(g.mem_total/1024).toFixed(0)} GB`:'–'}</span></div><div class="progress progress-sm"><div class="progress-bar bg-azure" style="width:${mem}%"></div></div></div></div>`;
 if(c){const p=c.progress,pct=p?p.pct:(c.elapsed_min&&c.ceiling_min?Math.min(100,100*c.elapsed_min/c.ceiling_min):0);
  h+=`<div class="mt-3"><div class="d-flex justify-content-between"><div><strong>${esc(c.job)} / ${esc(c.step)}</strong> <span class="muted">${esc(c.title||'')}</span></div><div class="muted small">${c.elapsed_min??'?'} / ${c.ceiling_min??'?'} min</div></div>
  <div class="progress mt-1" style="height:16px"><div class="progress-bar ${p?'bg-primary':'bg-secondary'}" style="width:${pct.toFixed(0)}%">${p?pct+'%':''}</div></div>
  <div class="small muted mt-1">${p?`${esc(p.desc)} ${p.n.toLocaleString()} / ${p.total.toLocaleString()} · ${esc(p.elapsed)} elapsed · ETA ${esc(p.eta)} · ${esc(p.rate)}`:(c.phase?esc(c.phase):'no progress bar for this step (train prints per epoch) — bar = elapsed vs ceiling')}</div></div>`;}
 h+=`<div class="row mt-3"><div class="col-6"><div class="muted small">GPU util % (sampled mean) · fixed 0–100, minutes before now</div><div class="chartbox"><canvas id="u_${esc(s.name)}"></canvas></div></div><div class="col-6"><div class="muted small">throughput tiles/s · fixed 0–100</div><div class="chartbox"><canvas id="r_${esc(s.name)}"></canvas></div></div></div>`;
 (s.jobs||[]).forEach(j=>{h+=`<div class="mt-3"><strong>${esc(j.id)}</strong> <span class="muted small">${esc(j.tag)}</span>${j.job_end?` <span class="chip ${esc(j.job_end.state)}">job-end VERIFY ${esc(j.job_end.state)}</span>`:''}<div>${stepsHtml(j)}</div></div>`;});
 if(s.scratch&&s.scratch.length)h+=`<div class="muted small mt-3">scratch: ${s.scratch.map(f=>`${esc(f.name)} ${fmtB(f.size)}`).join(' · ')}</div>`;
 if(s.procs&&s.procs.length)h+=`<div class="muted small mono">${s.procs.map(p=>`${p.pid} ${Math.floor(p.etimes/60)}m ${esc(p.args.replace(/.*phase4_/,'phase4_').slice(0,80))}`).join('<br>')}</div>`;
 if(s.log)h+=`<details class="mt-2"><summary class="muted small">log ${esc(s.log.path.split('/').pop())} · ${fmtB(s.log.size)} · ${s.log.age_s}s old</summary><div class="logbox mono mt-1">${esc(s.log.tail.join('\n'))}</div></details>`;
 return h+`</div></div></div>`;}
const winEl=document.getElementById('win');try{winEl.value=localStorage.getItem('edm_win')||'120'}catch(e){}
winEl.addEventListener('change',()=>{try{localStorage.setItem('edm_win',winEl.value)}catch(e){};tick();});
// stationary axes: x = minutes before now over a fixed window (constant tick spacing), y = fixed 0..ymax
function spark(id,pts,color,ymax,win){const el=document.getElementById(id);if(!el||!window.Chart)return;
 if(charts[id]){const ch=charts[id];ch.data.datasets[0].data=pts;ch.options.scales.x.min=-win;ch.options.scales.x.ticks.stepSize=win/4;ch.update('none');return;}
 charts[id]=new Chart(el,{type:'line',data:{datasets:[{data:pts,borderColor:color,borderWidth:1.5,pointRadius:0,fill:true,backgroundColor:color+'22',tension:0}]},
  options:{animation:false,responsive:true,maintainAspectRatio:false,resizeDelay:200,parsing:false,normalized:true,
   plugins:{legend:{display:false},tooltip:{callbacks:{title:i=>`${(-i[0].parsed.x).toFixed(0)} min ago`}}},
   scales:{x:{type:'linear',min:-win,max:0,ticks:{stepSize:win/4,color:'#8696ab',font:{size:10},callback:v=>v===0?'now':`${-v}m`},grid:{color:'#24303f'}},
           y:{min:0,max:ymax,ticks:{stepSize:ymax/4,color:'#8696ab',font:{size:10}},grid:{color:'#24303f'}}}}});}
let lastHtml='';
async function tick(){try{const [st,hi]=await Promise.all([fetch('/api/state',{cache:'no-store'}).then(r=>r.json()),fetch('/api/history',{cache:'no-store'}).then(r=>r.json())]);
 document.getElementById('gen').textContent=`${st.generated||'…'} · probes every ${st.exec_interval}s${st.no_exec?' (exec OFF)':''}`;
 const e=document.getElementById('errs');e.textContent=(st.errors||[]).join(' · ');e.style.display=st.errors&&st.errors.length?'':'none';
 const html=(st.sessions||[]).map(card).join('')||'<div class="muted p-3">no sessions yet</div>';
 if(html!==lastHtml){document.getElementById('cards').innerHTML=html;lastHtml=html;Object.keys(charts).forEach(k=>{charts[k].destroy();delete charts[k]});}
 const win=+(winEl.value||120),now=Date.now(),px=p=>(Date.parse(p.t)-now)/60000;
 (st.sessions||[]).forEach(s=>{const H=(hi[s.name]||[]).filter(p=>px(p)>=-win);
  spark('u_'+s.name,H.filter(p=>p.util!=null).map(p=>({x:px(p),y:p.util})),'#2fb344',100,win);
  spark('r_'+s.name,H.filter(p=>p.rate!=null).map(p=>({x:px(p),y:Math.min(p.rate,100)})),'#4299e1',100,win);});
 let x=`<div class="row"><div class="col-md-4"><table class="table table-sm"><thead><tr><th>session</th><th>endpoint</th><th>hw</th></tr></thead><tbody>${(st.colab_sessions||[]).map(s=>`<tr><td>${esc(s.name)}</td><td class="mono small">${esc(s.endpoint)}</td><td>${esc(s.hardware)}</td></tr>`).join('')}</tbody></table>
 <div class="small muted">locks: ${(st.locks||[]).map(esc).join(', ')||'(none)'}</div>
 <table class="table table-sm mt-2"><thead><tr><th>live assignment</th><th>acc</th><th>name</th></tr></thead><tbody>${(st.assignments||[]).map(x=>`<tr class="${x.name?'':'text-danger'}"><td class="mono small">${esc(x.endpoint)}</td><td>${esc(x.accelerator)}</td><td>${x.name?esc(x.name):'ORPHAN — billing, no name'}</td></tr>`).join('')}</tbody></table></div>
 <div class="col-md-8"><table class="table table-sm"><thead><tr><th>run</th><th>step</th><th>branch@sha</th><th>gpu</th></tr></thead><tbody>${(st.manifests||[]).slice().reverse().map(m=>`<tr><td class="mono small">${esc(m.run_id)}</td><td>${esc(m.step)}</td><td class="mono small">${esc(m.branch)}@${esc(m.sha)}</td><td class="small">${esc(m.gpu)}</td></tr>`).join('')}</tbody></table></div></div>`;
 document.getElementById('extra').innerHTML=x;}catch(err){const e=document.getElementById('errs');e.textContent='fetch failed: '+err;e.style.display='';}}
tick();setInterval(tick,15000);
</script></body></html>"""


def make_handler(collector):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = collector.snapshot().encode("utf-8")
                ctype = "application/json"
            elif self.path.startswith("/api/history"):
                body = collector.history().encode("utf-8")
                ctype = "application/json"
            else:
                body = HTML.encode("utf-8")
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default=None, help="comma list, e.g. A,B (default: named `colab sessions`)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--exec-interval", type=int, default=60, help="seconds between per-VM probes")
    ap.add_argument("--local-interval", type=int, default=15, help="seconds between local (G:) reads")
    ap.add_argument("--no-exec", action="store_true", help="never call colab exec (G:-only view)")
    ap.add_argument("--once", action="store_true", help="print one JSON snapshot and exit")
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = ap.parse_args([a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))])
    sessions = [s.strip() for s in args.sessions.split(",") if s.strip()] if args.sessions else []
    col = Collector(sessions, args.exec_interval, args.local_interval, args.no_exec)
    if args.once:
        col.refresh_sessions()
        col._assign, col._assign_err = live_assignments()
        if not args.no_exec:
            col.probe_all()
        col.assemble()
        print(col.snapshot())
        return 0
    try:                      # bind BEFORE any probing, so a busy port costs nothing
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(col))
    except OSError as e:
        # An older dashboard still holding the port serves ITS baked-in HTML, so edits to
        # this file appear to do nothing in the browser. Say so instead of dying quietly.
        sys.exit(f"cannot bind 127.0.0.1:{args.port} — {e}\n"
                 f"An earlier dashboard is probably still running and serving the OLD page.\n"
                 f"Stop it (Ctrl-C in its terminal, or: taskkill /F /IM python.exe on the right PID) "
                 f"or start this one with --port {args.port + 1}.")
    col.start()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"runtime dashboard: {url}   sessions={sessions or 'auto'}  probes every {args.exec_interval}s  "
          f"(Ctrl-C to stop; read-only)")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())

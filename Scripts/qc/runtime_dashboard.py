r"""runtime_dashboard.py — local progress dashboard for the headless Colab queues (overhaul P11.6).

One browser page (http://127.0.0.1:8765) with a card per Colab CLI session: GPU
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


def colab_sessions():
    rc, out, err = run_colab(["sessions"], timeout=60)
    rows = []
    for ln in out.splitlines():
        m = SESS_RE.match(ln.strip())
        if m:
            rows.append({"name": m.group(1), "endpoint": m.group(2), "hardware": m.group(3),
                         "variant": m.group(4)})
    return rows, (err.strip() if rc else "")


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
        card["gpu"] = {"name": g[0], "util": g[1], "mem_used": g[2], "mem_total": g[3]}
    else:
        card["gpu"] = None
    if not card["procs"]:
        card["flags"].append("no queue/engine process on the VM")
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
    for r in qrows:
        if r.get("state") in BAD_STATES or r.get("state") in ("INTERRUPTED",):
            card["flags"].append(f"{r.get('job')}/{r.get('step')} {r.get('state')} {str(r.get('detail') or '')[:120]}")
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
    # GPU idle during GPU steps
    if card["gpu"] and cur and cur["step"] in ("train", "inference") and not cur.get("staging"):
        try:
            if int(card["gpu"]["util"]) == 0 and cur.get("progress"):
                card["flags"].append("GPU 0% while a GPU step reports progress")
        except ValueError:
            pass
    return card


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

    def snapshot(self):
        with self._lock:
            return json.dumps(self.state)

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
            cards.append(card)
        state = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "sessions": cards,
                 "colab_sessions": self._sess_rows, "locks": read_locks(), "manifests": read_manifests(),
                 "errors": errors, "exec_interval": self.exec_interval, "no_exec": self.no_exec,
                 "base": str(BASE)}
        with self._lock:
            self.state = state

    def run(self):
        last_exec = 0.0
        last_sess = 0.0
        while True:
            t = time.time()
            try:
                if t - last_sess >= 120:
                    self.refresh_sessions(); last_sess = t
                if not self.no_exec and t - last_exec >= self.exec_interval:
                    self.probe_all(); last_exec = time.time()
                self.assemble()
            except Exception as e:  # noqa: BLE001
                with self._lock:
                    self.state.setdefault("errors", []).append(f"collector: {e!r}")
            time.sleep(self.local_interval)


# ── HTTP ───────────────────────────────────────────────────────────────────────
HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>Edmonds runtimes</title>
<style>
body{margin:0;background:#0f1115;color:#e6e6e6;font:14px/1.4 system-ui,Segoe UI,sans-serif}
header{padding:10px 16px;background:#161a22;border-bottom:1px solid #262b36;display:flex;gap:16px;align-items:baseline}
header h1{font-size:16px;margin:0}.muted{color:#8b93a7}.err{color:#ff6b6b}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:14px;padding:14px}
.card{background:#161a22;border:1px solid #262b36;border-radius:10px;padding:14px}
.card h2{margin:0 0 6px;font-size:18px;display:flex;justify-content:space-between;align-items:center}
.badge{font-size:12px;padding:2px 8px;border-radius:999px;background:#262b36;color:#c8cfdd}
.flags{margin:6px 0}.flag{background:#3a1d1d;border:1px solid #7a2e2e;color:#ffb3b3;border-radius:6px;padding:4px 8px;margin:3px 0;font-size:12px}
.job{margin:8px 0;padding:8px;background:#111419;border-radius:8px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.chip{padding:2px 8px;border-radius:6px;font-size:12px;background:#262b36;color:#aab2c5}
.chip.OK{background:#173d26;color:#8fe3a8}.chip.RUNNING{background:#1d2f4d;color:#9cc4ff;animation:pulse 1.6s infinite}
.chip.FAIL,.chip.ERROR,.chip.TIMEOUT,.chip.INTERRUPTED{background:#4d1d1d;color:#ffb3b3}.chip.prior{opacity:.7}
@keyframes pulse{50%{opacity:.6}}
.bar{height:14px;background:#262b36;border-radius:7px;overflow:hidden;margin:6px 0}
.bar>div{height:100%;background:linear-gradient(90deg,#3b82f6,#22c55e)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:2px 10px;font-size:13px}
pre{background:#0b0d11;border:1px solid #262b36;border-radius:8px;padding:8px;font-size:11.5px;max-height:260px;overflow:auto;white-space:pre-wrap;word-break:break-all}
details summary{cursor:pointer;color:#8b93a7}
table{border-collapse:collapse;font-size:12px}td,th{padding:2px 8px;border-bottom:1px solid #262b36;text-align:left}
</style></head><body>
<header><h1>Edmonds Colab runtimes</h1><span id="gen" class="muted"></span><span id="errs" class="err"></span></header>
<main id="main"></main>
<section style="padding:0 14px 20px"><details><summary>sessions · locks · manifests</summary><div id="extra"></div></details></section>
<script>
const fmtB=b=>b>=1e9?(b/1e9).toFixed(2)+' GB':b>=1e6?(b/1e6).toFixed(1)+' MB':b+' B';
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function card(s){
 let h=`<div class="card"><h2><span>${esc(s.name)} <span class="muted">${esc(s.queue||'')}</span></span><span class="badge">${esc(s.gpu?s.gpu.name:(s.hardware||'?'))}</span></h2>`;
 h+=`<div class="muted">host ${esc(s.host||'?')} · VM ${esc(s.vm_utc||'')} · probe ${s.probe_age_s??'?'}s ago${s.gpu?` · GPU ${esc(s.gpu.util)}% ${esc(s.gpu.mem_used)}/${esc(s.gpu.mem_total)} MiB`:''}</div>`;
 if(s.flags&&s.flags.length)h+=`<div class="flags">`+s.flags.map(f=>`<div class="flag">${esc(f)}</div>`).join('')+`</div>`;
 const c=s.current;
 if(c){h+=`<div class="job"><b>${esc(c.job)} / ${esc(c.step)}</b> <span class="muted">${esc(c.title||'')}</span>`;
  h+=`<div class="kv"><span>elapsed</span><span>${c.elapsed_min??'?'} min of ${c.ceiling_min??'?'} ceiling (started ${esc(c.started||'')})</span>`;
  if(c.staging)h+=`<span>staging</span><span>${esc(c.staging)}</span>`;
  if(c.progress){const p=c.progress;h+=`<span>${esc(p.desc)}</span><span>${p.n.toLocaleString()} / ${p.total.toLocaleString()} · ${esc(p.elapsed)} elapsed · ETA ${esc(p.eta)} · ${esc(p.rate)}</span>`;}
  h+=`</div>`;
  if(c.progress)h+=`<div class="bar"><div style="width:${c.progress.pct}%"></div></div><div class="muted">${c.progress.pct}%</div>`;
  else{const pct=c.elapsed_min&&c.ceiling_min?Math.min(100,100*c.elapsed_min/c.ceiling_min):0;h+=`<div class="bar" title="elapsed vs ceiling"><div style="width:${pct.toFixed(0)}%;background:#555f73"></div></div>`;}
  h+=`</div>`;}
 (s.jobs||[]).forEach(j=>{h+=`<div class="job"><b>${esc(j.id)}</b> <span class="muted">${esc(j.tag)}</span>${j.job_end?` <span class="chip ${esc(j.job_end.state)}">job-end VERIFY ${esc(j.job_end.state)}</span>`:''}<div class="chips">`;
  (j.steps||[]).forEach(st=>{const cls=(st.state||'')+(st.src==='prior'?' prior':'');h+=`<span class="chip ${cls}" title="${esc(st.ts||'')}${st.verify?' · VERIFY '+esc(st.verify):''}">${esc(st.step)}${st.state?' '+esc(st.state):''}${st.minutes?' '+esc(st.minutes)+'m':''}${st.verify&&st.verify!=='OK'?' ⚠':''}</span>`;});
  h+=`</div></div>`;});
 if(s.scratch&&s.scratch.length)h+=`<div class="muted">scratch: `+s.scratch.map(f=>`${esc(f.name)} ${fmtB(f.size)}`).join(' · ')+`</div>`;
 if(s.procs&&s.procs.length)h+=`<div class="muted">procs: `+s.procs.map(p=>`${p.pid} ${Math.floor(p.etimes/60)}m ${esc(p.args.replace(/.*phase4_/,'phase4_').slice(0,90))}`).join(' | ')+`</div>`;
 if(s.log)h+=`<details open><summary>log ${esc(s.log.path.split('/').pop())} · ${fmtB(s.log.size)} · ${s.log.age_s}s old</summary><pre>${esc(s.log.tail.join('\n'))}</pre></details>`;
 return h+`</div>`;}
async function tick(){try{const r=await fetch('/api/state',{cache:'no-store'});const st=await r.json();
 document.getElementById('gen').textContent=`generated ${st.generated||'…'} · probes every ${st.exec_interval}s${st.no_exec?' (exec OFF)':''} · ${st.base||''}`;
 document.getElementById('errs').textContent=(st.errors||[]).join(' · ');
 document.getElementById('main').innerHTML=(st.sessions||[]).map(card).join('')||'<div class="muted" style="padding:20px">no sessions yet</div>';
 let x=`<table><tr><th>session</th><th>endpoint</th><th>hw</th></tr>`+(st.colab_sessions||[]).map(s=>`<tr><td>${esc(s.name)}</td><td>${esc(s.endpoint)}</td><td>${esc(s.hardware)}</td></tr>`).join('')+`</table>`;
 x+=`<p>locks: ${(st.locks||[]).map(esc).join(', ')||'(none)'}</p>`;
 x+=`<table><tr><th>run</th><th>step</th><th>branch@sha</th><th>gpu</th></tr>`+(st.manifests||[]).slice().reverse().map(m=>`<tr><td>${esc(m.run_id)}</td><td>${esc(m.step)}</td><td>${esc(m.branch)}@${esc(m.sha)}</td><td>${esc(m.gpu)}</td></tr>`).join('')+`</table>`;
 document.getElementById('extra').innerHTML=x;}catch(e){document.getElementById('errs').textContent='fetch failed: '+e;}}
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
        if not args.no_exec:
            col.probe_all()
        col.assemble()
        print(col.snapshot())
        return 0
    col.start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(col))
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

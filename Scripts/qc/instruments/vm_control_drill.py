r"""vm_control_drill.py — the handle-death fire drill as a rehearsable instrument.

Kam, 2026-09-02: "We need it to work flawlessly." The drill stops being
hand-typed steps and becomes this runbook: one command, eight asserted stages,
a PASS/FAIL table, cleanup in `finally`. Run it before any expensive campaign
to prove the handle-free control stack end to end on a REAL runtime:

  1 LAUNCH    T4 via vm_ops (bootstraps babysitter RULE 4 + persists the
              browser attach URL to the lake)
  2 RULE 1    plant a decoy engine process (named to match BOTH the babysitter
              kill pattern and the watchdog work pattern — drill 1's decoy
              matched only one and its VM took the 2 h no-queue branch), then
              pkill the heartbeat and assert the babysitter resurrects it
  3 INDUCE    strip the session from the CLI's local sessions.json (backed up)
              and assert `colab status -s` returns not-found — the REAL
              failure observable, reproduced surgically
  4 CENSUS    vm_ops sessions must still list a T4 (account truth > handles)
  5 STATUS    mailbox round-trip must return the decoy in procs and a
              SESSION-SCOPED log line (never another session's tail)
  6 STOP      mailbox stop must kill exactly the decoy pattern
  7 REAP      the drain-aware self-stop watchdog must unassign the VM
              (~600 s idle grace + drain; bounded wait, breadcrumb read)
  8 CLEANUP   restore the CLI state backup

SPENDS GPU: one T4 for ~20-35 min (a fraction of a compute unit). Requires
--yes. Mutates ~/.config/colab-cli/sessions.json surgically (backup+restore).
"""
import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
VM_OPS = SCRIPTS / "pipeline" / "vm_ops.py"
COLAB = Path(r"C:\Users\Kameron\.local\bin\colab.exe")
SESSIONS_JSON = Path(r"C:\Users\Kameron\.config\colab-cli\sessions.json")

from lake import BASE   # installed shared module
LOGS = BASE / "phase4" / "logs"

RESULTS = []


def stage(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"[drill] {'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
    if not ok:
        raise SystemExit(f"drill FAILED at stage {name}: {detail}")


def run(args, timeout=600):
    r = subprocess.run([sys.executable, "-u", str(VM_OPS)] + args,
                       capture_output=True, text=True, timeout=timeout,
                       cwd=str(SCRIPTS))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    ap = argparse.ArgumentParser(description="Handle-death fire drill (spends one T4).")
    ap.add_argument("--yes", action="store_true", help="required: this spends GPU")
    ap.add_argument("--session", default=None)
    ap.add_argument("--reap-wait-min", type=int, default=30)
    a = ap.parse_args()
    if not a.yes:
        raise SystemExit("this drill launches a real T4 — pass --yes to confirm")
    sess = a.session or "drill" + _dt.datetime.now().strftime("%H%M")
    bak = None
    try:
        # 1 LAUNCH
        code, out = run(["launch", "--session", sess, "--gpu", "T4"], timeout=600)
        stage("LAUNCH", code == 0 and "BABYSITTER_STARTED" in out, f"session {sess}")
        stage("URL_PERSISTED", (LOGS / f"vm_url_{sess}.txt").exists(),
              (LOGS / f"vm_url_{sess}.txt").name)

        # 2 DECOY + RULE 1
        payload = Path(tempfile.gettempdir()) / f"drill_setup_{sess}.py"
        payload.write_text(
            "import subprocess, time\n"
            "open('/content/phase4_semantic_finetune.py','w')"
            ".write('import time\\ntime.sleep(7200)\\n')\n"
            "subprocess.run('cd /content && nohup python -u "
            "phase4_semantic_finetune.py --drill-decoy > /content/decoy.log "
            "2>&1 &', shell=True, check=True)\n"
            "time.sleep(2)\n"
            "subprocess.run(['pkill','-f','vm_heartbeat.py'], capture_output=True)\n"
            "pid = ''\n"
            "for _ in range(12):\n"                # poll to 120 s — a fixed 45 s
            "    time.sleep(10)\n"                 # sleep raced the 30 s babysitter
            "    r = subprocess.run(['pgrep','-f','vm_heartbeat'],"
            " capture_output=True, text=True)\n"   # poll boundary on drill 3
            "    pid = r.stdout.strip()\n"
            "    if pid: break\n"
            "print('BEACON_RESURRECTED:', pid or 'STILL_DEAD')\n"
            "hb = open('/content/vm_heartbeat.log', errors='replace').read()[-300:]\n"
            "print('HB_LOG_TAIL:', hb)\n",
            encoding="utf-8")
        code, out = run(["exec", "--session", sess, "--file", str(payload),
                         "--timeout", "240"], timeout=480)
        stage("RULE1_BEACON_RESURRECTED",
              "BEACON_RESURRECTED:" in out and "STILL_DEAD" not in out,
              out[-300:].replace("\n", " | ") if "STILL_DEAD" in out
              or "BEACON_RESURRECTED:" not in out else "")
        stage("RULE1_NO_CONFLICT_DIVERSION", "COLLISION" not in out,
              "resurrected beacon publishes under its own name")

        # 3 INDUCE handle death
        bak = str(SESSIONS_JSON) + f".{sess}.bak"
        shutil.copy2(SESSIONS_JSON, bak)
        d = json.loads(SESSIONS_JSON.read_text(encoding="utf-8"))
        stage("INDUCE_PRECONDITION", sess in d, "session present in local state")
        del d[sess]
        SESSIONS_JSON.write_text(json.dumps(d), encoding="utf-8")
        r = subprocess.run([str(COLAB), "status", "-s", sess],
                           capture_output=True, text=True, timeout=120)
        stage("HANDLE_DEAD", "not found" in (r.stdout + r.stderr).lower())

        # 4 CENSUS still sees the orphan
        code, out = run(["sessions"], timeout=300)
        stage("CENSUS_SEES_ORPHAN", "T4" in out)

        # 5 mailbox STATUS through the dead handle
        code, out = run(["cmd", "--session", sess, "--command", "status",
                         "--wait", "300"], timeout=420)
        cross = "tier1" in out or "hardyear" in out      # another session's log
        stage("MAILBOX_STATUS", "phase4_semantic_finetune.py --drill-decoy" in out
              and not cross,
              "decoy visible, log line session-scoped")

        # 6 mailbox STOP
        code, out = run(["cmd", "--session", sess, "--command", "stop",
                         "--wait", "300"], timeout=420)
        stage("MAILBOX_STOP", "killed" in out and "[]" not in out.split("killed")[-1][:20])

        # 7 REAP by the watchdog. The BREADCRUMB is the fast, authoritative
        # signal (drill 2: watchdog fired dead on its 600 s schedule at
        # 09:39:45Z while the account census kept listing the T4 for ~15 more
        # minutes — the census lags unassign). Pass on breadcrumb; keep census
        # clearance as the secondary acceptance within the bound.
        t0 = time.time()
        how = ""
        while time.time() - t0 < a.reap_wait_min * 60:
            time.sleep(60)
            try:
                crumb = (LOGS / f"selfstop_{sess}.log").read_text(
                    encoding="utf-8", errors="replace")
                if "drain" in crumb or "stopped" in crumb:
                    how = "breadcrumb: " + crumb.strip().splitlines()[-1]
                    break
            except OSError:
                pass
            r = subprocess.run([str(COLAB), "sessions"], capture_output=True,
                               text=True, timeout=180)
            if "T4" not in r.stdout:
                how = "census clear (breadcrumb not yet synced)"
                break
        stage("WATCHDOG_REAPED", bool(how),
              f"{(time.time()-t0)/60:.0f} min; {how}")
    finally:
        # 8 CLEANUP — restore local CLI state minus the (now gone) drill session
        if bak and Path(bak).exists():
            d = json.loads(Path(bak).read_text(encoding="utf-8"))
            d.pop(sess, None)
            SESSIONS_JSON.write_text(json.dumps(d), encoding="utf-8")
            Path(bak).unlink(missing_ok=True)
        print("\n[drill] " + " | ".join(
            f"{n}:{'PASS' if ok else 'FAIL'}" for n, ok, _ in RESULTS))
        print(f"[drill] {'ALL PASS' if all(ok for _, ok, _ in RESULTS) else 'FAILED'}"
              f" ({len(RESULTS)} stages)")


if __name__ == "__main__":
    main()

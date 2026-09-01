"""vm_ops.py — the Colab VM lifecycle as CODE, not choreography.

Every rule here was learned expensively and lived only in COLAB_AUTONOMY_SETUP.md
prose + session memory until 2026-09-01:

  * ONE CLI CALL AT A TIME — a `colab exec` against a dying session SIGTERM'd a
    sibling launcher mid-bootstrap (2026-08-29, exit 15, unbootstrapped VM billing).
    Enforced with a cross-process lockfile, not discipline.
  * GREP FAILURE SIGNATURES, NOT SUCCESS — "a chain that greps only LAUNCHED exits 0
    having launched nothing" (also 2026-08-29). Bootstrap output is checked against
    BOTH signature sets; missing success + missing failure = UNVERIFIED, loudly.
  * TOKEN SCRIPTS DIE AFTER USE — gen_vm_bootstrap embeds live credentials; the
    emitted file is deleted in a finally block, success or not.
  * `colab new` BACKS OFF on Precondition Failed (A100 scarcity; 240 s cadence).
  * `stop` treats "Not Found" as ALREADY STOPPED (the self-stop watchdog usually
    wins the race — canary3b did exactly this).

Permission stays human: CLAUDE.md 3.4 (first launch of a queue asks Kam; A100
concurrency cap 2) is policy, not mechanics — this tool prints the reminders and
executes the mechanics.

    py -3.12 pipeline/vm_ops.py launch --session s1 --gpu L4 [--queue pipeline/queue_x.yaml]
    py -3.12 pipeline/vm_ops.py exec   --session s1 --file payload.py [--timeout 900]
    py -3.12 pipeline/vm_ops.py status --session s1
    py -3.12 pipeline/vm_ops.py stop   --session s1

Stdlib only (lake imported for status). VM-side scripts stay in gen_vm_bootstrap.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLAB = Path(r"C:\Users\Kameron\.local\bin\colab.exe")
SCRATCH = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "sector_campaign_vm"
LOCK = SCRATCH / "colab_cli.lock"

BOOT_OK = ("WRITE_CANARY PASS", "EDITABLE_INSTALL OK", "BOOTSTRAP_READY",
           "HEARTBEAT_STARTED")
BOOT_FAIL = ("BOOTSTRAP FAIL", "MOUNT_FAILED", "WRITE_CANARY FAIL",
             "EDITABLE_INSTALL FAIL", "Traceback (most recent call last)")


class CliLock:
    """One colab CLI call at a time, across PROCESSES. O_EXCL lockfile with the
    holder's pid; a lock whose pid is dead is stale and reclaimed."""

    def __enter__(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        pid = 0
        for _ in range(1200):                       # up to ~20 min behind a long exec
            try:
                fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    pid = int(LOCK.read_text() or "0")
                except (OSError, ValueError):
                    pid = 0
                if pid and not _pid_alive(pid):
                    print(f"  (stale CLI lock from dead pid {pid} — reclaiming)")
                    LOCK.unlink(missing_ok=True)
                    continue
                time.sleep(1.0)
        raise SystemExit(f"colab CLI lock held too long by pid {pid} — investigate; "
                         f"NEVER delete {LOCK} while its exec is alive")

    def __exit__(self, *exc):
        LOCK.unlink(missing_ok=True)


def _pid_alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                       capture_output=True, text=True)
    return str(pid) in (r.stdout or "")


def _cli(args, timeout):
    with CliLock():
        r = subprocess.run([str(COLAB)] + args, capture_output=True, text=True,
                           timeout=timeout + 120, errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out


def verify_output(out, ok_sigs, fail_sigs, what):
    """Three-state: OK (all ok_sigs present, no fail_sigs), FAILED (a fail sig),
    UNVERIFIED (neither conclusive). Never silent."""
    hit_fail = [s for s in fail_sigs if s in out]
    missing = [s for s in ok_sigs if s not in out]
    if hit_fail:
        return "FAILED", f"{what}: failure signature(s) {hit_fail}"
    if missing:
        return "UNVERIFIED", f"{what}: missing success signature(s) {missing}"
    return "OK", f"{what}: all {len(ok_sigs)} success signatures present"


def new_session(session, gpu, tries=6, backoff=240):
    for i in range(tries):
        code, out = _cli(["new", "-s", session, "--gpu", gpu], timeout=300)
        if "Session READY" in out:
            print(f"  VM READY: {session} ({gpu})")
            return
        if "Precondition Failed" in out or "TooManyAssignments" in out:
            print(f"  {gpu} unavailable (attempt {i + 1}/{tries}) — "
                  f"backing off {backoff}s: {out.strip().splitlines()[-1][:90]}")
            time.sleep(backoff)
            continue
        raise SystemExit(f"colab new failed (rc={code}):\n{out[-500:]}")
    raise SystemExit(f"{gpu} never became available after {tries} tries")


def bootstrap(session, branch=None):
    gen = [sys.executable, str(HERE / "gen_vm_bootstrap.py"), "--session", session]
    if branch:
        gen += ["--branch", branch]
    r = subprocess.run(gen, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("gen_vm_bootstrap failed:\n" + (r.stderr or r.stdout)[-400:])
    script = SCRATCH / f"vm_bootstrap_{session}.py"
    try:
        code, out = _cli(["exec", "-s", session, "-f", str(script),
                          "--timeout", "900"], timeout=900)
        state, msg = verify_output(out, BOOT_OK, BOOT_FAIL, "bootstrap")
        print("  " + msg)
        for ln in out.splitlines():
            if any(s in ln for s in BOOT_OK + BOOT_FAIL):
                print("    " + ln.strip()[:110])
        if state != "OK":
            raise SystemExit(f"bootstrap {state} — do NOT run work on this VM")
    finally:
        script.unlink(missing_ok=True)          # token-bearing: dies success or not
        print(f"  token script deleted: {script.name}")


def exec_file(session, file, timeout):
    code, out = _cli(["exec", "-s", session, "-f", str(file),
                      "--timeout", str(timeout)], timeout=timeout)
    print(out[-2000:])
    return code, out


def launch_queue(session, queue_yaml):
    """The production start form (phase4_train_queue.py header, line ~50):
    nohup-detached so the queue survives the exec handle."""
    q = Path(queue_yaml)
    if not q.exists():
        raise SystemExit(f"queue file missing: {q}")
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = SCRATCH / f"vm_start_{session}.py"
    log = ("/content/drive/MyDrive/treedata/phase4/logs/"
           f"train_queue_nohup_{q.stem}_{ts}.log")
    body = (
        "import subprocess, time\n"
        f"log = {log!r}\n"
        f"cmd = 'cd /content/repo/Scripts/pipeline && nohup python -u "
        f"phase4_train_queue.py --queue {q.name} > ' + log + ' 2>&1 &'\n"
        "subprocess.run(cmd, shell=True, check=True)\n"
        "time.sleep(5)\n"
        "r = subprocess.run(['pgrep', '-f', 'phase4_train_queue'],"
        " capture_output=True, text=True)\n"
        "print('QUEUE_LAUNCHED pid', r.stdout.strip() or 'MISSING')\n")
    payload.write_text(body, encoding="utf-8")
    try:
        code, out = exec_file(session, payload, 120)
        state, msg = verify_output(out, ("QUEUE_LAUNCHED pid",), ("MISSING",),
                                   "queue launch")
        print("  " + msg)
        if state != "OK":
            raise SystemExit("queue launch " + state)
        print(f"  nohup log: {log}")
    finally:
        payload.unlink(missing_ok=True)


def status(session):
    from lake import BASE, read_retry   # installed module — no path hack
    hb = BASE / "phase4" / "logs" / f"heartbeat_{session}.json"
    data = read_retry(lambda: hb.read_text(encoding="utf-8") if hb.exists() else "")
    if not data:
        print(f"no heartbeat for {session} at {hb}")
        return
    d = json.loads(data)
    print(f"session {session}: beat {d.get('ts_utc')}  gpu {d.get('gpu', {}).get('name')} "
          f"util {d.get('gpu', {}).get('util_pct')}%  queue_step {d.get('queue_step')}  "
          f"dirty {d.get('vfs_dirty_gb')} GB")


def stop(session):
    code, out = _cli(["stop", "-s", session], timeout=180)
    if "Not Found" in out or "404" in out:
        print(f"  {session}: already gone (self-stop won the race — normal)")
    elif code == 0:
        print(f"  {session}: stopped")
    else:
        raise SystemExit(f"stop failed:\n{out[-300:]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    L = sub.add_parser("launch")
    L.add_argument("--session", required=True)
    L.add_argument("--gpu", default="T4", choices=["T4", "L4", "G4", "A100", "H100"])
    L.add_argument("--queue", default=None)
    L.add_argument("--branch", default=None)
    E = sub.add_parser("exec")
    E.add_argument("--session", required=True)
    E.add_argument("--file", required=True)
    E.add_argument("--timeout", type=int, default=900)
    S = sub.add_parser("status")
    S.add_argument("--session", required=True)
    X = sub.add_parser("stop")
    X.add_argument("--session", required=True)
    a = ap.parse_args()

    if a.cmd == "launch":
        if a.gpu == "A100":
            print("REMINDER (CLAUDE.md 3.4): A100 concurrency cap is 2 on this account; "
                  "first launch of a NEW queue needs Kam's yes.")
        new_session(a.session, a.gpu)
        bootstrap(a.session, a.branch)
        if a.queue:
            launch_queue(a.session, a.queue)
        print(f"launch complete: {a.session}")
    elif a.cmd == "exec":
        code, _ = exec_file(a.session, a.file, a.timeout)
        sys.exit(code)
    elif a.cmd == "status":
        status(a.session)
    elif a.cmd == "stop":
        stop(a.session)


if __name__ == "__main__":
    main()

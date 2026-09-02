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
           "HEARTBEAT_STARTED", "BABYSITTER_STARTED")
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
    args = ["new", "-s", session] + ([] if gpu == "CPU" else ["--gpu", gpu])
    for i in range(tries):
        code, out = _cli(args, timeout=300)
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


def launch_queue(session, queue_yaml, queue_args=""):
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
        f"phase4_train_queue.py --queue {q.name} {queue_args} > ' + log + ' 2>&1 &'\n"
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


def sessions():
    """ACCOUNT-LEVEL runtime census — the oversight that survives handle death.

    Handles die permanently (colab-cli discipline), and on 2026-09-02 all three
    Tier-1 staging handles died mid-flight while the VMs kept working; the only
    live view was the browser's Manage-sessions dialog until this subcommand
    wrapped `colab sessions` (which queries the ACCOUNT, not local state — it
    listed both surviving VMs and pruned 11 stale local records on first use).

    Cross-references Drive heartbeats to label what it can. HONEST LIMITS,
    measured before writing this: an orphaned session (dead handle) is VISIBLE
    here but NOT addressable — `colab status/stop -s <raw id>` returns 'not
    found' (name-keyed local state). Orphans end via their self-stop watchdog,
    or manually in the browser dialog. This census answers 'is anything
    running, and how many' — pair it with heartbeat ages for 'is it healthy'."""
    code, out = _cli(["sessions"], timeout=180)
    if code != 0:
        raise SystemExit(f"colab sessions failed:\n{out[-300:]}")
    live = [ln.strip() for ln in out.splitlines() if "Hardware:" in ln]
    print(f"{len(live)} active runtime(s) on the account:")
    for ln in live:
        print(f"  {ln}")
    try:
        from lake import BASE
        import datetime as _dt2
        now = _dt2.datetime.now(_dt2.timezone.utc)
        beats = []
        for hb in sorted((BASE / "phase4" / "logs").glob("heartbeat_*.json")):
            if "__conflict" in hb.stem:
                continue    # Drive conflict copies (a beacon killed mid-write
                            # left one on the 2026-09-02 drill) are sync debris,
                            # not sessions — listing them miscounts the fleet
            try:
                d = json.loads(hb.read_text(encoding="utf-8"))
                ts = _dt2.datetime.fromisoformat(
                    d.get("ts_utc", "").replace("Z", "+00:00"))
                age = (now - ts).total_seconds() / 60
                if age < 20:
                    beats.append((hb.stem.replace("heartbeat_", ""), round(age)))
            except Exception:                                    # noqa: BLE001
                continue
        if beats:
            print("fresh heartbeats (<20 min; Drive-mirror lag can hide some):")
            for name, age in beats:
                print(f"  {name}: {age} min old")
        else:
            print("no fresh heartbeats visible (mirror lag, or none beating)")
    except Exception as e:                                       # noqa: BLE001
        print(f"(heartbeat cross-reference unavailable: {e})")


def cmd(session, command, wait_s=240):
    """Handle-free control: write the Drive mailbox the babysitter polls (RULE 4)
    and wait for its reply file. Works on any VM whose babysitter is from
    2026-09-02 or later, regardless of CLI-handle state. Vocabulary: status, stop.
    Round-trip = local->Drive sync + 30 s babysitter poll + Drive->local sync —
    minutes under mirror lag, not seconds; that is the price of handle-freedom."""
    import time as _t
    from lake import BASE, read_retry
    logs = BASE / "phase4" / "logs"
    import datetime as _dt
    nonce = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (logs / f"cmd_{session}.json").write_text(
        json.dumps({"cmd": command, "nonce": nonce}), encoding="utf-8")
    print(f"  mailbox written: cmd={command} nonce={nonce}; waiting for reply "
          f"(up to {wait_s}s)")
    rp = logs / f"cmd_reply_{session}.json"
    t0 = _t.time()
    while _t.time() - t0 < wait_s:
        _t.sleep(15)
        data = read_retry(lambda: rp.read_text(encoding="utf-8") if rp.exists() else "")
        if data:
            try:
                r = json.loads(data)
            except ValueError:
                continue
            if r.get("nonce") == nonce:
                for k, v in r.items():
                    print(f"  {k}: {v if not isinstance(v, str) or len(v) < 200 else v[:200] + '…'}")
                if "nohup_tail" in r:
                    print("  --- nohup tail ---")
                    print(r["nohup_tail"])
                return
    print(f"  no reply within {wait_s}s — mirror lag, a pre-mailbox babysitter, "
          f"or a dead VM; check `vm_ops sessions` for existence")


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
    L.add_argument("--gpu", default="T4",
                   choices=["CPU", "T4", "L4", "G4", "A100", "H100"],
                   help="CPU = no accelerator flag: zero compute units (the one "
                        "MEASURED-free tier in colab_rates.csv) — right for postproc")
    L.add_argument("--queue", default=None)
    L.add_argument("--queue-args", default="",
                   help="extra phase4_train_queue args, e.g. '--only JOB_ID' to "
                        "split one queue across parallel runtimes")
    L.add_argument("--branch", default=None)
    E = sub.add_parser("exec")
    E.add_argument("--session", required=True)
    E.add_argument("--file", required=True)
    E.add_argument("--timeout", type=int, default=900)
    S = sub.add_parser("status")
    S.add_argument("--session", required=True)
    X = sub.add_parser("stop")
    X.add_argument("--session", required=True)
    sub.add_parser("sessions", help="account-level runtime census "
                                    "(survives dead handles) + fresh heartbeats")
    C = sub.add_parser("cmd", help="handle-free control via the Drive mailbox "
                                   "(babysitter RULE 4): status | stop")
    C.add_argument("--session", required=True)
    C.add_argument("--command", required=True, choices=["status", "stop"])
    C.add_argument("--wait", type=int, default=240)
    a = ap.parse_args()

    if a.cmd == "launch":
        if a.gpu == "A100":
            print("REMINDER (CLAUDE.md 3.4): A100 concurrency cap is 2 on this account; "
                  "first launch of a NEW queue needs Kam's yes.")
        new_session(a.session, a.gpu)
        bootstrap(a.session, a.branch)
        # Persist the BROWSER attach URL to the lake NOW: the CLI handle can die
        # permanently mid-run (all three Tier-1 staging handles did, 2026-09-02),
        # and this URL is the manual reattach lever that outlives it.
        try:
            _c2, _u = _cli(["url", "-s", a.session], timeout=120)
            _url = next((ln.strip() for ln in _u.splitlines()
                         if ln.strip().startswith("http")), "")
            if _url:
                from lake import BASE as _B
                (_B / "phase4" / "logs" / f"vm_url_{a.session}.txt").write_text(
                    _url + "\n", encoding="utf-8")
                print(f"  browser attach URL (persisted to lake): {_url}")
        except Exception as _e:                                  # noqa: BLE001
            print(f"  (url capture skipped: {_e})")
        if a.queue:
            launch_queue(a.session, a.queue, a.queue_args)
        print(f"launch complete: {a.session}")
    elif a.cmd == "exec":
        code, _ = exec_file(a.session, a.file, a.timeout)
        sys.exit(code)
    elif a.cmd == "status":
        status(a.session)
    elif a.cmd == "stop":
        stop(a.session)
    elif a.cmd == "sessions":
        sessions()
    elif a.cmd == "cmd":
        cmd(a.session, a.command, a.wait)


if __name__ == "__main__":
    main()

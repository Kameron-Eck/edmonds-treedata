r"""vm_babysitter.py — deterministic on-VM supervisor. NO model, by decision
(Kam, 2026-09-01: "Build tier 1 and don't implement an AI oversight model").

WHY: the hard-year pilot's failures were all recoverable but needed a HUMAN-side
round-trip through a blinking mirror and losable CLI handles to notice. This runs
ON the runtime, reacts in seconds, and cannot lose its own handle. Every rule
below maps to a failure measured on 2026-09-01:

  RULE 1  the heartbeat beacon died mid-run on THREE VMs (hardyear, hardyear4,
          epoch-era) while the queue kept working — oversight went blind.
          -> supervise vm_heartbeat; restart it when dead. Logged.
  RULE 2  evaluate crashed reading a tile MID-UPLOAD (RasterioIOError "not
          recognized as being in a supported file format"; the file was valid
          seconds later) — a FUSE race, transient by nature.
          -> when the queue exits with FAIL rows whose step log matches a KNOWN
          TRANSIENT signature, relaunch the queue --only that job, ONCE. Resume
          credit makes the retry cost one step, not one arm.
  RULE 3  anything not on the known-transient list is NOT retried. It is written
          to the babysitter log as ESCALATE with the log excerpt, and the VM's
          own self-stop watchdog is left to end the runtime. Unknown failures
          are a human's to read — by design, not limitation.
  RULE 4  DRIVE COMMAND MAILBOX (2026-09-02). All three Tier-1 staging handles
          died mid-flight while their VMs kept working — CLI handles die
          permanently, so the control plane must not live in them. Each poll,
          read {LOGS}/cmd_{session}.json; a tiny fixed vocabulary, one nonce
          processed once (ledger in the state file), reply written to
          {LOGS}/cmd_reply_{session}.json:
            status  -> process table + newest queue-nohup tail (the deep probe
                       exec used to provide)
            stop    -> SIGTERM the queue + engine processes and nothing else;
                       the EXISTING self-stop watchdog then ends the idle VM
                       through its measured drain-aware path — this rule never
                       reimplements unassign.
          Unknown commands get an error reply, never execution. There is
          deliberately no run-arbitrary-code command.

Launched by the emitted bootstrap (nohup, like vm_heartbeat). Stdlib only — this
is a VM twin: no lake.py, no phase4seg, paths spelled directly.

State: /content/babysitter_state.json (retry ledger — dies with the VM, which is
correct: a NEW vm gets a fresh retry budget). Log (append-only, on Drive):
    phase4/logs/babysitter_{session}.log
"""
import json
import subprocess
import sys
import time

DRIVE = "/content/drive/MyDrive/treedata"
LOGS = DRIVE + "/phase4/logs"
STATE = "/content/babysitter_state.json"
POLL_S = 30
BOOT_TS = time.time()             # mailbox status only reports logs from THIS boot
KNOWN_TRANSIENT = (
    "not recognized as being in a supported file format",   # FUSE mid-upload read
    "Transport endpoint is not connected",                   # mount dropped
    "Input/output error",                                    # FUSE hiccup
    "CURL error",                                            # Drive backend blip
)


def log(session, msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line, flush=True)
    try:
        with open(f"{LOGS}/babysitter_{session}.log", "a") as f:
            f.write(line + "\n")
    except OSError:
        pass                                   # Drive blink; stdout still has it


def load_state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {"retried": []}


def save_state(st):
    try:
        json.dump(st, open(STATE, "w"))
    except OSError:
        pass


def pids(pattern):
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [p for p in r.stdout.split() if p.strip()]


def queue_cmdline():
    """The live queue's argv (queue file + --only), read from /proc."""
    for pid in pids("phase4_train_queue.py"):
        try:
            raw = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
            argv = [a for a in raw.split("\0") if a]
            if any("phase4_train_queue" in a for a in argv):
                return argv
        except OSError:
            continue
    return None


def parse_queue_args(argv):
    q, only = None, None
    for i, a in enumerate(argv):
        if a == "--queue" and i + 1 < len(argv):
            q = argv[i + 1]
        elif a == "--only" and i + 1 < len(argv):
            only = argv[i + 1]
    return q, only


def restart_heartbeat(session):
    subprocess.Popen(
        "cd /content/repo/Scripts/pipeline && nohup python -u vm_heartbeat.py"
        f" --session {session} > /content/vm_heartbeat.log 2>&1 &", shell=True)


def _is_status_name(name):
    """A DELIBERATE TWIN of phase4seg.names.is_status_file, kept local because this
    supervisor must run when the engine package is unimportable (same rationale and
    same body as vm_heartbeat's twin). Equivalence is gated:
    qc/test_vm_babysitter.py::test_twin_agrees_with_the_shared_rule. Without this
    filter a bare glob reads seeds and the CONTAMINATED rename as ledger truth —
    the exact bug the discovery-rule gate caught in this file's first draft."""
    if not (name.startswith("train_queue_status") and name.endswith(".csv")):
        return False
    rest = name[len("train_queue_status"):-len(".csv")]
    if rest and not rest.startswith("_"):
        return False
    return all(c.isalnum() or c in "._-" for c in rest)


def failed_jobs_this_session(session):
    """(job_id, step) pairs whose LATEST row in this session's status files is a
    hard failure. Session attribution via the ledger's own `session` column."""
    import csv
    import glob
    latest = {}
    cands = [p for p in sorted(glob.glob(DRIVE + "/phase4/qc/train_queue_status*.csv"))
             if _is_status_name(p.replace(chr(92), "/").rsplit("/", 1)[-1])]
    for p in cands:
        try:
            for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
                if r.get("session") != session:
                    continue
                step = str(r.get("step", ""))
                if step.startswith("VERIFY") or not step:
                    continue
                latest[(r.get("job"), step)] = r.get("state")
        except OSError:
            continue
    return [(j, s) for (j, s), state in latest.items()
            if state in ("FAIL", "ERROR", "TIMEOUT")]


def failure_is_known_transient(year, step):
    """Read the newest engine step log for (year-ish, step) and match signatures."""
    import glob
    cands = sorted(glob.glob(f"{LOGS}/phase4_semantic_finetune_{step}_*"))
    for p in reversed(cands[-3:]):
        try:
            tail = open(p, errors="replace").read()[-4000:]
        except OSError:
            continue
        for sig in KNOWN_TRANSIENT:
            if sig in tail:
                return sig, p.split("/")[-1]
    return None, None


def check_mailbox(session, st):
    """RULE 4 — one command per nonce, tiny vocabulary, reply file always written."""
    import glob
    p = f"{LOGS}/cmd_{session}.json"
    try:
        d = json.load(open(p))
    except (OSError, ValueError):
        return
    nonce = str(d.get("nonce", ""))
    if not nonce or nonce in st.setdefault("nonces", []):
        return
    st["nonces"].append(nonce)
    save_state(st)                      # ledger FIRST: a crash mid-command must
    cmd = str(d.get("cmd", ""))         # not replay it on restart
    reply = {"nonce": nonce, "cmd": cmd, "session": session,
             "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if cmd == "status":
        r = subprocess.run(["pgrep", "-af",
                            "phase4_train_queue|phase4_semantic|vm_heartbeat"],
                           capture_output=True, text=True)
        reply["procs"] = (r.stdout or "").strip()[:1500]
        # Only logs written since THIS VM booted: the logs dir is shared across
        # runtimes and a bare newest-glob latched onto ANOTHER session's queue
        # log on the drill's first live status (2026-09-02) — the exact hazard
        # vm_heartbeat's header documents for its own globs.
        import os as _os
        logs = [p for p in sorted(glob.glob(f"{LOGS}/train_queue_nohup_*.log"))
                if _os.path.getmtime(p) >= BOOT_TS - 60]
        if logs:
            try:
                reply["nohup"] = logs[-1].rsplit("/", 1)[-1]
                reply["nohup_tail"] = open(logs[-1], errors="replace").read()[-1500:]
            except OSError:
                pass
        else:
            reply["nohup"] = "(no queue log newer than this VM's boot)"
    elif cmd == "stop":
        r = subprocess.run(["pgrep", "-f", "phase4_train_queue|phase4_semantic"],
                           capture_output=True, text=True)
        pids = [x for x in r.stdout.split() if x.strip()]
        for pid in pids:
            subprocess.run(["kill", pid], capture_output=True)
        reply["killed"] = pids
        reply["note"] = ("queue+engine SIGTERMed; the self-stop watchdog ends "
                         "this idle VM via its drain-aware path")
    else:
        reply["error"] = f"unknown cmd {cmd!r} — vocabulary: status, stop"
    try:
        with open(f"{LOGS}/cmd_reply_{session}.json", "w") as f:
            json.dump(reply, f)
    except OSError:
        pass                            # Drive blink; the log line still records it
    log(session, f"MAILBOX {cmd or '?'} nonce={nonce} processed "
                 f"({'ERROR' if 'error' in reply else 'ok'})")


def relaunch(queue_file, job_id, session):
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    lg = f"{LOGS}/train_queue_nohup_babysitter_retry_{job_id}_{ts}.log"
    cmd = ("cd /content/repo/Scripts/pipeline && nohup python -u "
           f"phase4_train_queue.py --queue {queue_file} --only {job_id} > {lg} 2>&1 &")
    subprocess.run(cmd, shell=True, check=True)
    log(session, f"RETRY LAUNCHED {job_id} (resume credit skips verified steps) -> {lg}")


def main():
    session = sys.argv[sys.argv.index("--session") + 1] if "--session" in sys.argv else "unknown"
    log(session, f"BABYSITTER UP poll={POLL_S}s rules=beacon-restart,transient-retry-once,escalate")
    st = load_state()
    queue_file = None
    queue_seen = False
    while True:
        time.sleep(POLL_S)
        # RULE 4 — the Drive mailbox is checked every cycle, queue alive or not
        check_mailbox(session, st)
        # RULE 1 — the beacon must not die silently
        if not pids("vm_heartbeat.py"):
            log(session, "BEACON DEAD -> restarting vm_heartbeat")
            restart_heartbeat(session)
        # remember the queue's identity while it lives
        argv = queue_cmdline()
        if argv:
            queue_seen = True
            qf, _ = parse_queue_args(argv)
            if qf:
                queue_file = qf
            continue                            # queue alive: nothing to judge yet
        if not queue_seen:
            continue                            # queue not launched yet
        # queue has EXITED — judge its session-attributed terminal rows, once
        queue_seen = False
        for job, step in failed_jobs_this_session(session):
            key = f"{job}:{step}"
            if key in st["retried"]:
                log(session, f"ESCALATE {job}/{step}: already retried once — leaving "
                             f"for a human; the self-stop watchdog will end this VM")
                continue
            year = (job.rsplit("_", 1)[-1] or "")
            sig, logname = failure_is_known_transient(year, step)
            if sig and queue_file:
                log(session, f"KNOWN TRANSIENT {job}/{step}: '{sig}' in {logname}")
                st["retried"].append(key)
                save_state(st)
                relaunch(queue_file, job, session)
            else:
                excerpt = f"(step log matched no known-transient signature)"
                log(session, f"ESCALATE {job}/{step}: {excerpt} — no model consulted "
                             f"by design; a human reads this")


if __name__ == "__main__":
    main()

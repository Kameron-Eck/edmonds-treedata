"""vm_babysitter: the deterministic rules, unit-tested without a VM.

The design decision under test (Kam, 2026-09-01): NO model. Every action is an
if-then a human can audit: beacon restart, ONE retry per (job, step) on a KNOWN
transient signature, ESCALATE-and-touch-nothing for everything else.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
import vm_babysitter as bb  # noqa: E402


def test_known_transient_signatures_cover_the_measured_failures():
    """Each signature maps to a failure measured on 2026-09-01 or earlier; the
    mid-upload tile read is the one that cost the pilot an evaluate step."""
    assert "not recognized as being in a supported file format" in bb.KNOWN_TRANSIENT
    assert "Transport endpoint is not connected" in bb.KNOWN_TRANSIENT


def test_queue_args_parsing():
    argv = ["python", "-u", "phase4_train_queue.py", "--queue",
            "queue_hard_year_pilot.yaml", "--only", "hard_year_pilot_hy_e3_2011s"]
    q, only = bb.parse_queue_args(argv)
    assert q == "queue_hard_year_pilot.yaml"
    assert only == "hard_year_pilot_hy_e3_2011s"
    q2, only2 = bb.parse_queue_args(["python", "x.py"])
    assert q2 is None and only2 is None


def test_failed_jobs_reads_only_this_sessions_latest_rows(tmp_path, monkeypatch):
    """Latest-wins within the session; other sessions' failures are not ours to
    retry; VERIFY rows are judgements, not steps."""
    d = tmp_path / "phase4" / "qc"
    d.mkdir(parents=True)
    (d / "train_queue_status_a.csv").write_text(
        "job,year,tag,step,state,exit,minutes,detail,host,session,ts\n"
        "j1,2011s,t,train,FAIL,,,x,h,mysess,2026-09-01 01:00\n"
        "j1,2011s,t,train,OK,,,x,h,mysess,2026-09-01 02:00\n"     # later OK wins
        "j1,2011s,t,evaluate,FAIL,,,x,h,mysess,2026-09-01 03:00\n"
        "j2,2006s,t,train,FAIL,,,x,h,OTHERSESS,2026-09-01 03:00\n"
        "j1,2011s,t,VERIFY:evaluate,FAIL,,,x,h,mysess,2026-09-01 03:01\n",
        encoding="utf-8")
    monkeypatch.setattr(bb, "DRIVE", str(tmp_path))
    got = bb.failed_jobs_this_session("mysess")
    assert got == [("j1", "evaluate")], got


def test_retry_ledger_is_once_per_job_step(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "STATE", str(tmp_path / "state.json"))
    st = bb.load_state()
    assert st == {"retried": []}
    st["retried"].append("j1:evaluate")
    bb.save_state(st)
    assert "j1:evaluate" in bb.load_state()["retried"]


def test_emitted_bootstrap_launches_the_babysitter():
    """The wiring gate: gen_vm_bootstrap's emitted body must start vm_babysitter
    and print the signature vm_ops now requires."""
    src = (SCRIPTS / "pipeline" / "gen_vm_bootstrap.py").read_text(encoding="utf-8")
    assert "vm_babysitter.py" in src
    assert "BABYSITTER_STARTED" in src
    import vm_ops
    assert "BABYSITTER_STARTED" in vm_ops.BOOT_OK


def test_twin_agrees_with_the_shared_rule():
    """The twin is only safe while proven equivalent (the vm_heartbeat precedent).
    Edit one, this fails."""
    from phase4seg.names import is_status_file
    corpus = ["train_queue_status_pilot_20260901T000000Z.csv",
              "train_queue_status.CONTAMINATED-BY-TEST-20260829.csv",
              "train_queue_status.csv",
              "train_queue_status_seed.csv",
              "not_a_ledger.csv",
              "train_queue_status_a b.csv"]
    for name in corpus:
        assert bb._is_status_name(name) == is_status_file(name), name


def test_mailbox_nonce_processed_once(tmp_path, monkeypatch):
    """RULE 4: a command nonce executes exactly once — a crash between ledger
    write and reply must not replay a stop on restart (ledger-first order)."""
    import json
    monkeypatch.setattr(bb, "LOGS", str(tmp_path))
    monkeypatch.setattr(bb, "STATE", str(tmp_path / "state.json"))
    calls = []
    monkeypatch.setattr(bb.subprocess, "run",
                        lambda *a, **k: (calls.append(a[0]),
                                         type("R", (), {"stdout": ""})())[1])
    (tmp_path / "cmd_s1.json").write_text(json.dumps({"cmd": "status", "nonce": "n1"}))
    st = {"retried": []}
    bb.check_mailbox("s1", st)
    assert "n1" in st["nonces"]
    reply = json.loads((tmp_path / "cmd_reply_s1.json").read_text())
    assert reply["nonce"] == "n1" and reply["cmd"] == "status"
    n_first = len(calls)
    bb.check_mailbox("s1", st)              # same nonce again -> no re-execution
    assert len(calls) == n_first


def test_mailbox_unknown_command_replies_error_and_runs_nothing(tmp_path, monkeypatch):
    """No run-arbitrary-code channel: anything outside the vocabulary gets an
    error reply and zero subprocess activity."""
    import json
    monkeypatch.setattr(bb, "LOGS", str(tmp_path))
    monkeypatch.setattr(bb, "STATE", str(tmp_path / "state.json"))
    calls = []
    monkeypatch.setattr(bb.subprocess, "run",
                        lambda *a, **k: (calls.append(a[0]),
                                         type("R", (), {"stdout": ""})())[1])
    (tmp_path / "cmd_s1.json").write_text(
        json.dumps({"cmd": "exec_anything", "nonce": "n2"}))
    bb.check_mailbox("s1", {"retried": []})
    reply = json.loads((tmp_path / "cmd_reply_s1.json").read_text())
    assert "error" in reply and not calls


def test_mailbox_stop_kills_only_queue_and_engine(tmp_path, monkeypatch):
    """stop SIGTERMs the queue/engine pattern and nothing else; ending the VM
    stays the self-stop watchdog's job (the reply says so)."""
    import json
    monkeypatch.setattr(bb, "LOGS", str(tmp_path))
    monkeypatch.setattr(bb, "STATE", str(tmp_path / "state.json"))
    calls = []

    def fake_run(argv, **k):
        calls.append(argv)
        out = "111\n222\n" if argv[0] == "pgrep" else ""
        return type("R", (), {"stdout": out})()
    monkeypatch.setattr(bb.subprocess, "run", fake_run)
    (tmp_path / "cmd_s1.json").write_text(json.dumps({"cmd": "stop", "nonce": "n3"}))
    bb.check_mailbox("s1", {"retried": []})
    kills = [a for a in calls if a[0] == "kill"]
    assert sorted(a[1] for a in kills) == ["111", "222"]
    pg = next(a for a in calls if a[0] == "pgrep")
    assert "phase4_train_queue|phase4_semantic" in pg[-1]
    reply = json.loads((tmp_path / "cmd_reply_s1.json").read_text())
    assert reply["killed"] == ["111", "222"] and "watchdog" in reply["note"]

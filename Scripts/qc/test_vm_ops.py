"""vm_ops: the lifecycle rules, unit-tested without a VM. The live path is proven
by an actual launch (billable, Kam-granted 2026-09-01)."""
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
import vm_ops  # noqa: E402


def test_verify_requires_every_success_signature():
    out = "WRITE_CANARY PASS\nEDITABLE_INSTALL OK\nBOOTSTRAP_READY abc\n"
    state, msg = vm_ops.verify_output(out, vm_ops.BOOT_OK, vm_ops.BOOT_FAIL, "b")
    assert state == "UNVERIFIED" and "HEARTBEAT_STARTED" in msg


def test_verify_failure_signature_beats_success_ones():
    out = "\n".join(vm_ops.BOOT_OK) + "\nWRITE_CANARY FAIL: upload never verified\n"
    state, _ = vm_ops.verify_output(out, vm_ops.BOOT_OK, vm_ops.BOOT_FAIL, "b")
    assert state == "FAILED", "a failure signature must beat a full success set"


def test_verify_all_green():
    out = "\n".join(vm_ops.BOOT_OK)
    state, _ = vm_ops.verify_output(out, vm_ops.BOOT_OK, vm_ops.BOOT_FAIL, "b")
    assert state == "OK"


def test_traceback_is_a_bootstrap_failure():
    """The v1 canary wrapper printed OK over a swallowed traceback (2026-09-01);
    the signature set makes that class impossible here."""
    out = "\n".join(vm_ops.BOOT_OK) + "\nTraceback (most recent call last):\n  boom"
    state, _ = vm_ops.verify_output(out, vm_ops.BOOT_OK, vm_ops.BOOT_FAIL, "b")
    assert state == "FAILED"


def test_cli_lock_is_exclusive_and_stale_reclaimable(tmp_path, monkeypatch):
    monkeypatch.setattr(vm_ops, "SCRATCH", tmp_path)
    monkeypatch.setattr(vm_ops, "LOCK", tmp_path / "colab_cli.lock")
    with vm_ops.CliLock():
        assert (tmp_path / "colab_cli.lock").exists()
        assert int((tmp_path / "colab_cli.lock").read_text()) == os.getpid()
    assert not (tmp_path / "colab_cli.lock").exists(), "lock must release on exit"
    # a stale lock from a dead pid is reclaimed, not waited on
    (tmp_path / "colab_cli.lock").write_text("999999999")
    with vm_ops.CliLock():
        pass
    assert not (tmp_path / "colab_cli.lock").exists()


def test_queue_payload_greps_failure_not_just_success(tmp_path, monkeypatch):
    """'A chain that greps only LAUNCHED exits 0 having launched nothing' — the
    generated payload must print a MISSING marker when pgrep finds no queue."""
    monkeypatch.setattr(vm_ops, "SCRATCH", tmp_path)
    calls = {}

    def fake_exec(session, file, timeout):
        calls["body"] = Path(file).read_text(encoding="utf-8")
        return 0, "QUEUE_LAUNCHED pid 1234"
    monkeypatch.setattr(vm_ops, "exec_file", fake_exec)
    q = tmp_path / "queue_x.yaml"
    q.write_text("- id: j1\n", encoding="utf-8")
    vm_ops.launch_queue("s", q)
    assert "MISSING" in calls["body"], "payload must expose the launched-nothing case"
    assert "nohup python -u phase4_train_queue.py" in calls["body"]
    assert not list(tmp_path.glob("vm_start_*.py")), "payload must be cleaned up"

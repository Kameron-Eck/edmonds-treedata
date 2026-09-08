"""vm_ops: the lifecycle rules, unit-tested without a VM. The live path is proven
by an actual launch (billable, Kam-granted 2026-09-01)."""
import ast
import os
import sys
import types
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


# ══ `launch --env`: the only route to the ENGINE's environment ════════════════
#
# staging.py::_bundle_enabled reads PHASE4SEG_TILE_BUNDLE from os.environ at
# import; the engine is a grandchild of the launch (vm_ops → nohup'd queue →
# phase4_train_queue.py::run_step's Popen, which passes no `env=`), so a shell
# assignment on the queue reaches it and a bootstrap-time export does not.

_LOG = ("/content/drive/MyDrive/treedata/phase4/logs/"
        "train_queue_nohup_queue_x_19700101T000000Z.log")

# CAPTURED FROM THE PRE-CHANGE CODE, before --env existed, with the clock frozen —
# not re-derived from the edited launch_queue, which would pin nothing. Every
# character is load-bearing, including the DOUBLE SPACE left where an empty
# --queue-args interpolates.
PIN_NO_ENV = "\n".join([
    "import subprocess, time",
    f"log = {_LOG!r}",
    "cmd = 'cd /content/repo/Scripts/pipeline && nohup python -u "
    "phase4_train_queue.py --queue queue_x.yaml  > ' + log + ' 2>&1 &'",
    "subprocess.run(cmd, shell=True, check=True)",
    "time.sleep(5)",
    "r = subprocess.run(['pgrep', '-f', 'phase4_train_queue'],"
    " capture_output=True, text=True)",
    "print('QUEUE_LAUNCHED pid', r.stdout.strip() or 'MISSING')",
]) + "\n"

PIN_WITH_ENV = "\n".join([
    "import subprocess, time",
    f"log = {_LOG!r}",
    "queue_env = ['PHASE4SEG_TILE_BUNDLE=1']",
    "for _e in queue_env:",
    "    print('QUEUE_ENV ' + _e)",
    "with open(log, 'w', encoding='utf-8') as _fh:",
    r"    _fh.writelines('QUEUE_ENV ' + _e + '\n' for _e in queue_env)",
    "cmd = 'cd /content/repo/Scripts/pipeline && PHASE4SEG_TILE_BUNDLE=1 "
    "nohup python -u phase4_train_queue.py --queue queue_x.yaml  >> ' + log + "
    "' 2>&1 &'",
    "subprocess.run(cmd, shell=True, check=True)",
    "time.sleep(5)",
    "r = subprocess.run(['pgrep', '-f', 'phase4_train_queue'],"
    " capture_output=True, text=True)",
    "print('QUEUE_LAUNCHED pid', r.stdout.strip() or 'MISSING')",
]) + "\n"


def _payload_for(tmp_path, monkeypatch, env=(), queue_args=""):
    """Run launch_queue with the clock frozen and the VM stubbed → payload text."""
    monkeypatch.setattr(vm_ops, "SCRATCH", tmp_path)
    monkeypatch.setattr(vm_ops, "time", types.SimpleNamespace(
        strftime=lambda fmt, t=None: "19700101T000000Z",
        gmtime=lambda *a: None, sleep=lambda s: None))
    grab = {}

    def fake_exec(session, file, timeout):
        grab["body"] = Path(file).read_text(encoding="utf-8")
        return 0, "QUEUE_LAUNCHED pid 1234"
    monkeypatch.setattr(vm_ops, "exec_file", fake_exec)
    q = tmp_path / "queue_x.yaml"
    q.write_text("- id: j1\n", encoding="utf-8")
    vm_ops.launch_queue("s", q, queue_args, env)
    return grab["body"]


def test_payload_without_env_is_byte_identical(tmp_path, monkeypatch):
    """The default path is PROVABLY unchanged. A live campaign launches through
    this function; --env must be additive or it is not shippable."""
    assert _payload_for(tmp_path, monkeypatch) == PIN_NO_ENV


def test_env_payload_matches_its_pin(tmp_path, monkeypatch):
    body = _payload_for(tmp_path, monkeypatch, ["PHASE4SEG_TILE_BUNDLE=1"])
    assert body == PIN_WITH_ENV


def test_env_reaches_the_shell_through_two_quoting_levels(tmp_path, monkeypatch):
    """The prefix is written into a single-quoted PYTHON literal that is then
    handed to `sh -c`. Asserting on the payload TEXT only proves level one, so
    this evaluates the `cmd` expression the way the VM's interpreter will and
    checks the SHELL string that comes out."""
    body = _payload_for(tmp_path, monkeypatch,
                        ["PHASE4SEG_TILE_BUNDLE=1", "FOO_BAR="], "--only J1")
    compile(body, "vm_start.py", "exec")          # the VM must be able to run it
    node = next(n for n in ast.parse(body).body
                if isinstance(n, ast.Assign) and n.targets[0].id == "cmd")
    shell = eval(compile(ast.Expression(node.value), "<cmd>", "eval"),  # noqa: S307
                 {"__builtins__": {}}, {"log": "LOG"})
    assert shell == ("cd /content/repo/Scripts/pipeline && "
                     "PHASE4SEG_TILE_BUNDLE=1 FOO_BAR= "
                     "nohup python -u phase4_train_queue.py --queue queue_x.yaml "
                     "--only J1 >> LOG 2>&1 &")
    # the assignments sit BEFORE nohup, so they scope to the queue process tree
    assert shell.index("PHASE4SEG_TILE_BUNDLE=1") < shell.index("nohup")


def test_env_is_recorded_on_both_evidence_channels(tmp_path, monkeypatch, capsys):
    """The payload's stdout is the EXEC channel, not the nohup log, so the env is
    written into the log's head as well — and printed locally, because exec_file
    echoes only the last 2000 chars of the exec output."""
    body = _payload_for(tmp_path, monkeypatch, ["PHASE4SEG_TILE_BUNDLE=1"])
    assert "print('QUEUE_ENV ' + _e)" in body                    # exec channel
    assert "open(log, 'w', encoding='utf-8')" in body            # nohup log head
    assert body.index("open(log, 'w'") < body.index("subprocess.run(cmd")
    assert "QUEUE_ENV PHASE4SEG_TILE_BUNDLE=1" in capsys.readouterr().out


def test_launch_verification_survives_env(tmp_path, monkeypatch):
    """--env must not disturb the QUEUE_LAUNCHED/MISSING contract."""
    body = _payload_for(tmp_path, monkeypatch, ["PHASE4SEG_TILE_BUNDLE=1"])
    assert "print('QUEUE_LAUNCHED pid', r.stdout.strip() or 'MISSING')" in body
    assert not list(tmp_path.glob("vm_start_*.py")), "payload must be cleaned up"


@pytest.mark.parametrize("bad, why", [
    ("lower_case=1", "key must be UPPER_SNAKE"),
    ("2LEADING=1", "key may not start with a digit"),
    ("HAS-DASH=1", "dash is not a shell-safe name char"),
    ("NOEQUALS", "KEY=VALUE or nothing"),
    ("K='; rm -rf /; '", "single quote"),
    ('K="x"', "double quote"),
    ("K=a\nb", "newline"),
    ("K=$(id)", "command substitution"),
    ("K=a`id`", "backtick"),
    ("K=a;id", "semicolon"),
    ("K=a|id", "pipe"),
    ("K=a&", "background operator"),
    ("K=a b", "word split"),
    ("K=a>f", "redirect"),
    ("K=a*", "glob"),
])
def test_parse_env_refuses_unsafe_input(bad, why):
    with pytest.raises(SystemExit):
        vm_ops.parse_env([bad])


def test_parse_env_accepts_the_shapes_we_actually_use():
    assert vm_ops.parse_env(["PHASE4SEG_TILE_BUNDLE=1"]) == [
        ("PHASE4SEG_TILE_BUNDLE", "1")]
    assert vm_ops.parse_env(["A=1", "B_2=/content/x.json", "C="]) == [
        ("A", "1"), ("B_2", "/content/x.json"), ("C", "")]
    assert vm_ops.parse_env(None) == [] and vm_ops.parse_env([]) == []


def test_parse_env_refuses_a_repeated_key():
    with pytest.raises(SystemExit):
        vm_ops.parse_env(["K=1", "K=2"])


def test_parse_env_refuses_the_launch_failure_signature():
    """MISSING is the pgrep-found-nothing sentinel that launch_queue greps the
    exec output for. The payload now echoes the env back on that same channel, so
    `PHASE4SEG_ALLOW_MISSING=1` — a plausible name — would flip a SUCCESSFUL
    launch to FAILED with the queue already running unattended. The verifier is
    left intact and the input is refused instead."""
    for item in ("PHASE4SEG_ALLOW_MISSING=1", "K=MISSING"):
        with pytest.raises(SystemExit) as e:
            vm_ops.parse_env([item])
        assert "MISSING" in str(e.value)


def test_the_two_level_quoting_gate_fires():
    """_env_shell_prefix's guard is unreachable through parse_env — so prove it
    works by calling it directly with what parse_env would have rejected. A gate
    never shown to fire is not known to be a gate (CLAUDE.md 3.4c)."""
    assert vm_ops._env_shell_prefix([("K", "1"), ("E", "")]) == "K=1 E= "
    with pytest.raises(SystemExit):
        vm_ops._env_shell_prefix([("K", "a b")])


def _run_main(monkeypatch, argv):
    """vm_ops.main() with EVERY colab call armed to explode, so anything that
    reaches the CLI fails loudly instead of quietly billing a runtime."""
    def boom(*a, **k):
        raise AssertionError("colab CLI was called")
    monkeypatch.setattr(vm_ops, "_cli", boom)
    monkeypatch.setattr(vm_ops, "new_session", boom)
    monkeypatch.setattr(vm_ops, "bootstrap", boom)
    monkeypatch.setattr(vm_ops, "launch_queue", boom)
    monkeypatch.setattr(sys, "argv", ["vm_ops.py"] + argv)
    vm_ops.main()


@pytest.mark.parametrize("bad", ["lower=1", "K='x'", "K=a;id", "NOEQUALS"])
def test_bad_env_is_refused_before_any_cli_call(tmp_path, monkeypatch, bad):
    q = tmp_path / "queue_x.yaml"
    q.write_text("- id: j1\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        _run_main(monkeypatch, ["launch", "--session", "s", "--queue", str(q),
                                "--env", bad])


def test_a_good_env_actually_reaches_launch_queue(tmp_path, monkeypatch):
    """The refusal tests above only prove BAD input stops. Without this, dropping
    the argument at the call site would pass every other test in this file while
    launching the queue with the feature quietly off."""
    q = tmp_path / "queue_x.yaml"
    q.write_text("- id: j1\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(vm_ops, "new_session", lambda *a, **k: None)
    monkeypatch.setattr(vm_ops, "bootstrap", lambda *a, **k: None)
    # _cli stays armed: main()'s url capture swallows the AssertionError itself,
    # which is also what keeps this test off the lake.
    monkeypatch.setattr(vm_ops, "_cli", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("colab CLI was called")))
    monkeypatch.setattr(vm_ops, "launch_queue",
                        lambda s, qy, qa="", env=(): seen.update(env=list(env)))
    monkeypatch.setattr(sys, "argv", [
        "vm_ops.py", "launch", "--session", "s", "--queue", str(q),
        "--env", "PHASE4SEG_TILE_BUNDLE=1", "--env", "OTHER=2"])
    vm_ops.main()
    assert seen["env"] == ["PHASE4SEG_TILE_BUNDLE=1", "OTHER=2"]


def test_env_without_a_queue_is_refused_not_dropped(tmp_path, monkeypatch):
    """A silently ignored --env is the failure mode this whole flag exists to fix:
    the queue would run with the feature OFF and look like a clean negative."""
    with pytest.raises(SystemExit) as e:
        _run_main(monkeypatch, ["launch", "--session", "s",
                                "--env", "PHASE4SEG_TILE_BUNDLE=1"])
    assert "--queue" in str(e.value)


def test_bench_reference_is_present_and_coherent():
    """Integration gate for the micro-benchmark: the reference exists, parses, and
    records the environment it was made in — a bench whose reference silently
    vanished would make `check.py --bench` a first-run no-op instead of a guard."""
    import json
    ref = SCRIPTS / "qc" / "bench_reference.json"
    assert ref.exists(), "qc/bench_reference.json missing — run: py -3.12 qc/bench.py --update"
    d = json.loads(ref.read_text(encoding="utf-8"))
    assert d.get("metrics") and d.get("torch") and d.get("seed") == 1337
    assert {"e1_loss", "val_loss", "postproc_canopy_px"} <= set(d["metrics"])

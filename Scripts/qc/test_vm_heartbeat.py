"""VM beacon gates (D4/D12, 2026-08-29).

The beacon is the ONLY thing that answers "is that runtime alive, and what is it
doing" without spending a `colab exec`. Two ways it could lie:

  D12  session names are handed down by the Colab CLI and were written verbatim,
       unchecked. Two runtimes given the same --session took turns overwriting ONE
       heartbeat file, so every reader saw a single blended "session" that was
       fresh whenever either VM was alive, with mount/queue/gpu fields belonging to
       whichever wrote last. Neither runtime could be found; neither looked dead.
  D4   the publish was os.replace over an existing destination on the rclone FUSE
       mount, every cycle after the first — the case
       select.py::_deploy_smoothed_keeping_raw concedes the mount canary never proved.

vm_heartbeat.py is STDLIB ONLY by design (it must survive anything the queue does
to the environment), and so is this file: no Drive, no torch, no geo stack.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_vm_heartbeat.py -q
"""
import json
import os
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]

vh = pytest.importorskip("vm_heartbeat")


def _beat(path, instance, session="test"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"session": session, "instance_id": instance,
                                "ts_utc": "2026-08-29T00:00:00Z"}), encoding="utf-8")
    return path


# ── D12: a beacon must not overwrite another live beacon's file ──────────────

def test_a_live_peer_holds_the_name(tmp_path):
    p = _beat(tmp_path / "heartbeat_test.json", "vm-a-111")
    ok, why = vh.name_is_ours(str(p), "vm-b-222")
    assert ok is False and "live beacon" in why


def test_our_own_file_is_ours(tmp_path):
    """The common case, every cycle after the first — it must not self-conflict."""
    p = _beat(tmp_path / "heartbeat_test.json", "vm-a-111")
    assert vh.name_is_ours(str(p), "vm-a-111") == (True, None)


def test_a_stale_peer_is_a_dead_vm_and_the_name_is_reclaimed(tmp_path):
    """A restarted runtime gets its own name back — otherwise every restart would
    permanently rename itself and oversight would drift away from the CLI's names."""
    p = _beat(tmp_path / "heartbeat_test.json", "vm-a-111")
    os.utime(p, (0, 0))
    assert vh.name_is_ours(str(p), "vm-b-222") == (True, None)


def test_nothing_unreadable_is_ever_a_reason_to_stop_beaconing(tmp_path):
    """Absent, corrupt, or written by a pre-D12 build: all yield the name. Refusing
    on a file we cannot interpret would silence oversight over a bad byte, which is
    a worse failure than the one being prevented."""
    missing = tmp_path / "heartbeat_absent.json"
    assert vh.name_is_ours(str(missing), "vm-b-222") == (True, None)
    corrupt = tmp_path / "heartbeat_corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert vh.name_is_ours(str(corrupt), "vm-b-222") == (True, None)
    old = tmp_path / "heartbeat_old.json"
    old.write_text(json.dumps({"session": "test"}), encoding="utf-8")  # no instance_id
    assert vh.name_is_ours(str(old), "vm-b-222") == (True, None)


def test_instance_id_is_unique_per_process():
    assert vh.INSTANCE_ID and str(os.getpid()) in vh.INSTANCE_ID


# ── D4: the publish never lands on an existing destination ───────────────────

def test_write_atomic_never_replaces_over_an_existing_file(tmp_path, monkeypatch):
    out = str(tmp_path / "heartbeat_test.json")
    vh.write_atomic(out, {"n": 1})
    seen = []
    real = os.replace

    def _spy(a, b):
        seen.append((os.path.basename(b), os.path.exists(b)))
        return real(a, b)

    monkeypatch.setattr(vh.os, "replace", _spy)
    vh.write_atomic(out, {"n": 2})                 # destination now EXISTS
    assert json.loads(Path(out).read_text(encoding="utf-8"))["n"] == 2
    assert seen, "no os.replace happened at all"
    assert not any(existed for _, existed in seen), \
        f"replaced over an existing destination on the mount: {seen}"


def test_write_atomic_leaves_no_staging_files(tmp_path):
    out = str(tmp_path / "heartbeat_test.json")
    vh.write_atomic(out, {"n": 1})
    vh.write_atomic(out, {"n": 2})
    assert [p.name for p in tmp_path.iterdir()] == ["heartbeat_test.json"]


def test_staging_suffixes_are_invisible_to_the_readers_glob(tmp_path):
    """runtime_health and the dashboard select on a `.json` suffix. A `.tmp.json`
    or `.prev.json` would be read as a heartbeat in its own right; `.json.tmp.<pid>`
    and `.json.prev.<token>` match nothing."""
    out = tmp_path / "heartbeat_test.json"
    for staged in (f"{out}.tmp.{os.getpid()}", f"{out}.prev.a1b2c3"):
        name = os.path.basename(staged)
        assert not (name.startswith("heartbeat_") and name.endswith(".json")), name


def test_a_failed_publish_restores_the_previous_heartbeat(tmp_path, monkeypatch):
    """A beacon must never leave NO heartbeat behind — an absent file reads as a
    dead VM and would page a human about a runtime that is fine."""
    out = str(tmp_path / "heartbeat_test.json")
    vh.write_atomic(out, {"n": 1})
    real = os.replace
    calls = {"n": 0}

    def _fail_second(a, b):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(5, "Input/output error")
        return real(a, b)

    monkeypatch.setattr(vh.os, "replace", _fail_second)
    with pytest.raises(OSError):
        vh.write_atomic(out, {"n": 2})
    assert json.loads(Path(out).read_text(encoding="utf-8"))["n"] == 1


# ── the watchdog must inherit this VM's identity ──────────────────────────────
def test_colab_session_is_set_before_the_watchdog_is_spawned():
    """A child process inherits the environment its parent had AT SPAWN TIME.

    The D14 change moved the watchdog spawn ABOVE the fallible bootstrap steps so
    a failed bootstrap could not leave a billing VM with nothing watching it. That
    was right, but it carried the spawn past the point where COLAB_SESSION is set:
    the watchdog then resolved its log name to the 'vm' default, every VM appended
    to one shared selfstop_vm.log, and the per-VM identity D12 exists to establish
    was gone. Both orderings look correct read on their own; only their ORDER is
    wrong, so this test is about position in the file and nothing else.
    """
    src = (Path(__file__).resolve().parents[1]
           / "pipeline" / "gen_vm_bootstrap.py").read_text(encoding="utf-8")
    set_at = src.index('os.environ["COLAB_SESSION"] = SESSION')
    spawn_at = src.index("nohup python -u /content/vm_selfstop.py")
    assert set_at < spawn_at, (
        "COLAB_SESSION is set AFTER the watchdog is spawned — the watchdog cannot "
        "see it, so every VM writes one shared selfstop_vm.log")
    # ...and before the beacon, further down, for the same reason. (Written first
    # as `set_at < beacon_at or beacon_at < set_at`, which is true whenever the two
    # differ — a check that cannot fail, inside the commit closing checks that
    # cannot fail. Recorded because that is exactly how the class hides.)
    # ANCHOR ON THE SPAWN, not the name: the first "vm_heartbeat" in this file is a
    # comment inside the watchdog's own embedded source, ~230 lines above the beacon,
    # so matching the bare name compared the env-var line against the wrong thing and
    # failed on correct code.
    beacon_at = src.index("nohup python -u vm_heartbeat.py")
    assert set_at < beacon_at, "the beacon cannot see COLAB_SESSION either"
    # (it is also passed --session explicitly on that command line, so the beacon
    # does not depend on the environment the way the watchdog does)

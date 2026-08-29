"""Verified-write gates (D1/D4, 2026-08-29).

What went wrong, in one sentence: every write was verified by reading it back
through the SAME rclone mount that wrote it, so "✓ verified write" attested only
that bytes had reached a cache on the machine doing the writing — and on
2026-08-29 the log reported deploying epoch B24 while every checkpoint on Drive
was B7, with VERIFY:train passing.

These tests hold the two claims that fix rests on:

  1. The success line NAMES WHAT IT PROVED. "verified write" appears only when the
     Drive API confirmed the md5. Cache-only and not-yet-drained writes say
     "staged write" and say why. This is the assertion that would have failed on
     the old code, and it is the whole point.
  2. os.replace never runs over an existing destination on the mount (D4). The
     mount canary only ever proved the ABSENT-destination case; the hot loop ran
     the other one once per improving epoch.

Plus the invariants that make a failure recoverable: a failed publish restores
the previous artifact, and a server-side mismatch NEVER raises or re-copies (it
is an undrained upload far more often than corruption).

No Drive, no rclone, no torch, no GPU: the remote is monkeypatched, so these run
anywhere the geo stack does.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_verified_write.py -q
"""
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))

common = pytest.importorskip("phase4seg.common")


@pytest.fixture(autouse=True)
def _no_real_rclone(monkeypatch):
    """Default every test to "no SA remote on this host" so nothing shells out."""
    monkeypatch.setattr(common, "_sa_remote_probe", False, raising=False)
    monkeypatch.setattr(common, "_sa_remote_ready", lambda: False)


def _write(p, data=b"payload"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# ── 1. the message names what it proved ───────────────────────────────────────

def test_cache_only_write_does_not_claim_verified(tmp_path, capsys):
    """No server-side channel available ⇒ the words "verified write" must NOT
    appear. This is the exact sentence the old code printed for a write it could
    not actually attest, and printing it is how an epoch-7 corpse looked fine."""
    src = _write(tmp_path / "local" / "sem_best_2009_x.pt")
    dst = tmp_path / "drive" / "sem_best_2009_x.pt"
    common._copy_to_drive(src, dst)
    out = capsys.readouterr().out
    assert dst.read_bytes() == b"payload"
    assert "verified write" not in out
    assert "staged write" in out and "LOCAL CACHE ONLY" in out


def test_server_confirmed_write_says_verified(tmp_path, monkeypatch, capsys):
    src = _write(tmp_path / "local" / "a.tif", b"abc123")
    dst = tmp_path / "drive" / "a.tif"
    monkeypatch.setattr(common, "_sa_remote_ready", lambda: True)
    monkeypatch.setattr(common, "_drive_rel", lambda p: "phase4/masks/" + Path(p).name)
    monkeypatch.setattr(common, "_remote_md5",
                        lambda p, timeout=120: common._digests(src, ("md5",))["md5"])
    common._copy_to_drive(src, dst)
    out = capsys.readouterr().out
    assert "✓ verified write" in out and "drive md5" in out
    assert "staged write" not in out


def test_undrained_upload_is_pending_not_verified_and_never_raises(
        tmp_path, monkeypatch, capsys):
    """The server answering with the PREVIOUS file's md5 is the normal state for a
    while after any write. It must read as 'not confirmed yet', never as a pass and
    never as a failure — treating it as corruption would abort good runs on every
    large checkpoint."""
    src = _write(tmp_path / "local" / "b.pt", b"new-bytes")
    dst = tmp_path / "drive" / "b.pt"
    monkeypatch.setattr(common, "_sa_remote_ready", lambda: True)
    monkeypatch.setattr(common, "_drive_rel", lambda p: "phase4/models/" + Path(p).name)
    monkeypatch.setattr(common, "_remote_md5", lambda p, timeout=120: "0" * 32)
    common._copy_to_drive(src, dst)                    # must not raise
    out = capsys.readouterr().out
    assert "staged write" in out and "Drive NOT CONFIRMED" in out
    assert "✓ verified write" not in out
    assert dst.read_bytes() == b"new-bytes"            # the copy still happened


# The mount path as the VM sees it. Kept as a STRING: on Windows
# str(WindowsPath("/content/drive/…")) comes back backslashed, so a Path built
# here would not match the prefix — which is itself a load-bearing property (it
# is what keeps local QC out of the rclone branch entirely, the same guard
# tiling.py documents). test_local_windows_paths_are_never_treated_as_drive holds
# that separately; these tests exercise the posix mapping the VM actually runs.
MOUNTED = common._DRIVE_MOUNT_PREFIX + "phase4/models/x.pt"


def test_verify_on_drive_states(monkeypatch):
    monkeypatch.setattr(common, "_sa_remote_ready", lambda: True)
    monkeypatch.setattr(common, "_remote_md5", lambda q, timeout=120: "a" * 32)
    assert common.verify_on_drive(MOUNTED, "a" * 32)[0] == "ok"
    assert common.verify_on_drive(MOUNTED, "b" * 32)[0] == "pending"
    monkeypatch.setattr(common, "_sa_remote_ready", lambda: False)
    assert common.verify_on_drive(MOUNTED, "a" * 32)[0] == "unavailable"
    # a path outside the mount can never be checked, whatever rclone says
    monkeypatch.setattr(common, "_sa_remote_ready", lambda: True)
    assert common.verify_on_drive("/tmp/x.pt", "a" * 32)[0] == "unavailable"
    # and no local md5 to compare means nothing was proven, not a pass
    assert common.verify_on_drive(MOUNTED, None)[0] == "unavailable"


def test_verify_on_drive_does_not_sleep_at_zero_wait(monkeypatch):
    """wait_s=0 is what the per-epoch checkpoint write uses; a sleep there would
    tax every improving epoch."""
    monkeypatch.setattr(common, "_sa_remote_ready", lambda: True)
    monkeypatch.setattr(common, "_remote_md5", lambda q, timeout=120: "b" * 32)
    monkeypatch.setattr(common.time, "sleep",
                        lambda s: pytest.fail(f"slept {s}s at wait_s=0"))
    assert common.verify_on_drive(MOUNTED, "a" * 32, wait_s=0.0)[0] == "pending"


def test_drive_rel_maps_mount_to_sa_remote_path():
    """treedata-sa:'s root_folder_id IS the treedata folder, so the mapping is 1:1."""
    assert common._drive_rel(MOUNTED) == "phase4/models/x.pt"
    assert common._drive_rel("/content/scratch/s.pt") is None
    assert common._drive_rel("/content/drive/MyDrive/other/s.pt") is None


def test_local_windows_paths_are_never_treated_as_drive():
    """A local QC/smoke run must not enter the rclone branch even in principle."""
    assert common._drive_rel(Path.cwd() / "x.pt") is None
    if os.name != "posix":
        assert common._drive_rel(
            Path("/content/drive/MyDrive/treedata/phase4/models/s.pt")) is None


# ── 2. os.replace never sees an existing destination (D4) ─────────────────────

def test_publish_never_replaces_over_an_existing_file(tmp_path, monkeypatch):
    """The invariant, asserted at the syscall: every os.replace this path performs
    has an ABSENT destination — the only case the rclone mount canary ever
    proved."""
    seen = []
    real = os.replace

    def _spy(a, b):
        seen.append((str(a), str(b), Path(b).exists()))
        return real(a, b)

    monkeypatch.setattr(common.os, "replace", _spy)
    dst = _write(tmp_path / "d" / "art.pt", b"old")
    part = _write(tmp_path / "d" / "art.pt.part.123", b"new")
    common._publish_replace(part, dst)
    assert dst.read_bytes() == b"new"
    assert seen, "no os.replace happened at all"
    assert not any(existed for _, _, existed in seen), \
        f"replaced over an existing destination: {seen}"
    assert not list(dst.parent.glob("*.prev.*")), "aside file left behind"


def test_publish_restores_the_previous_artifact_when_it_fails(tmp_path, monkeypatch):
    """A failed publish must leave the OLD artifact in place. Unlink-then-replace
    would have destroyed it; rename-aside can put it back."""
    dst = _write(tmp_path / "d" / "art.pt", b"old")
    part = _write(tmp_path / "d" / "art.pt.part.123", b"new")
    real = os.replace
    calls = {"n": 0}

    def _fail_second(a, b):
        calls["n"] += 1
        if calls["n"] == 2:                            # the part -> dest publish
            raise OSError(5, "Input/output error")
        return real(a, b)

    monkeypatch.setattr(common.os, "replace", _fail_second)
    with pytest.raises(OSError):
        common._publish_replace(part, dst)
    assert dst.exists() and dst.read_bytes() == b"old"


def test_copy_to_drive_overwrites_an_existing_destination(tmp_path, monkeypatch):
    """THE HOT LOOP, end to end: the checkpoint already exists and is replaced,
    once per improving epoch, on the mount.

    Spying here and not only on _publish_replace is deliberate — an earlier version
    of this file tested the helper in isolation, and a probe that reinstated the raw
    `os.replace(part, drive_path)` inside _copy_to_drive passed the whole suite. A
    unit test of the helper proves nothing about whether the caller uses it.
    """
    src = _write(tmp_path / "l" / "c.pt", b"epoch24")
    dst = _write(tmp_path / "d" / "c.pt", b"epoch7")
    seen = []
    real = os.replace

    def _spy(a, b):
        seen.append((Path(a).name, Path(b).name, Path(b).exists()))
        return real(a, b)

    monkeypatch.setattr(common.os, "replace", _spy)
    common._copy_to_drive(src, dst)
    assert dst.read_bytes() == b"epoch24"
    assert seen, "no os.replace happened at all"
    assert not any(existed for _, _, existed in seen), \
        f"replaced over an existing destination on the mount: {seen}"
    assert not list(dst.parent.glob("*.part.*"))
    assert not list(dst.parent.glob("*.prev.*"))


def test_copy_to_drive_still_raises_on_a_corrupt_copy(tmp_path, monkeypatch):
    """The local size/sha check is the one that RAISES, and it must keep doing so:
    softening it is how a truncated artifact reaches a scoring run."""
    src = _write(tmp_path / "l" / "d.tif", b"0123456789")
    dst = tmp_path / "d" / "d.tif"

    def _short(a, b):                                  # every copy lands truncated
        Path(b).parent.mkdir(parents=True, exist_ok=True)
        Path(b).write_bytes(b"012")

    monkeypatch.setattr(common.shutil, "copyfile", _short)
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="verified write failed"):
        common._copy_to_drive(src, dst, retries=1)
    assert not dst.exists()                            # never published


def test_sweep_removes_stale_prev_asides(tmp_path):
    """A publish that died between the two renames leaks a .prev. aside; it is
    swept on the same age gate as .part., and never while it could be live."""
    old = _write(tmp_path / "art.pt.prev.aa11bb", b"x")
    fresh = _write(tmp_path / "art.pt.prev.cc22dd", b"x")
    os.utime(old, (0, 0))
    common._sweep_part_orphans(tmp_path)
    assert not old.exists()
    assert fresh.exists()


def test_aside_and_part_suffixes_sort_after_the_extension():
    """Every artifact glob in the repo is extension-anchored, so the staging
    suffixes must come AFTER the extension or readers will pick them up (a
    `status.prev.csv` would be merged and double-count rows)."""
    for name in ("sem_best_2009_x.pt", "edmonds_canopy_prob_2009_x.tif",
                 "train_queue_status_q_20260829T000000Z.csv"):
        p = Path("/d") / name
        aside = p.with_name(p.name + ".prev.a1b2c3")
        part = p.with_name(p.name + ".part.999abc")
        for staged in (aside, part):
            assert not staged.name.endswith(p.suffix), staged.name

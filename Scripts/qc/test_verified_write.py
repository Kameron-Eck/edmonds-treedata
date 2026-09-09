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
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]

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


# ── the aside rename's error is not always FileNotFoundError ─────────────────
# Ported from queue_ledger.py::_replace_absent (c5dc91c), which met this first on
# the STATUS table. _publish_replace renamed the destination aside guarded ONLY
# against FileNotFoundError — which reads "dest vanished under us, so there is no
# aside". True for ENOENT and false for everything else. On this rclone FUSE mount
# a transient EIO is documented (queue_verify.py::_check_prob_raster retries
# for it), and an EIO can be raised AFTER the rename has already landed. The old
# code let that OSError propagate with the destination GONE and the only copy of
# the checkpoint stranded under a `.prev.<hex>` name no reader globs (they are all
# extension-anchored) and only common.py::_sweep_part_orphans reclaims, past its
# 24 h age gate — unreachable for a day, then deleted. The three `.prev.*` orphans
# found on the lake 2026-09-07 (e499355's
# closing note) were STATUS TABLES, not checkpoints — the same mechanism, on the
# path that met it first; this one carried the identical guard.

def _eio():
    import errno
    return OSError(errno.EIO, "input/output error")


def _replace_spy(monkeypatch, script):
    """Patch os.replace with a scripted sequence. Each entry is 'ok', 'eio_after'
    (perform the rename, THEN raise EIO — the case the old guard could not see), or
    'eio_before' (raise without renaming). Returns the call log, which records
    whether the destination EXISTED at each call so the D4 syscall invariant can be
    asserted on the same evidence."""
    real = common.os.replace
    calls = []

    def _spy(a, b):
        act = script[len(calls)] if len(calls) < len(script) else "ok"
        calls.append((Path(a).name, Path(b).name, Path(b).exists(), act))
        if act == "eio_before":
            raise _eio()
        real(a, b)
        if act == "eio_after":
            raise _eio()

    monkeypatch.setattr(common.os, "replace", _spy)
    return calls


def _seed_publish(tmp_path):
    dst = _write(tmp_path / "d" / "sem_best_2009_x.pt", b"old")
    part = _write(tmp_path / "d" / "sem_best_2009_x.pt.part.123", b"new")
    return part, dst


def test_an_eio_after_the_aside_rename_does_not_lose_the_checkpoint(
        tmp_path, monkeypatch):
    """THE ORPHAN'S MECHANISM. The rename landed and then reported EIO. The old
    guard caught only FileNotFoundError, so this escaped _publish_replace entirely
    with the destination GONE — a scoring run would find no checkpoint at all.
    Re-probing the filesystem — dest absent, aside present — says the rename
    completed, so the publish must proceed."""
    part, dst = _seed_publish(tmp_path)
    calls = _replace_spy(monkeypatch, ["eio_after"])
    common._publish_replace(part, dst)
    assert dst.exists(), "the destination was lost to an EIO that had already renamed it"
    assert dst.read_bytes() == b"new"
    assert not list(dst.parent.glob("*.prev.*")), "the previous checkpoint was orphaned"
    assert not list(dst.parent.glob("*.part.*"))
    assert not any(existed for _, _, existed, _ in calls), \
        f"replaced over an existing destination: {calls}"


def test_an_eio_on_both_renames_restores_the_previous_checkpoint(
        tmp_path, monkeypatch):
    """Aside rename completes-then-EIOs, and the publish fails too. The aside is the
    only copy of the checkpoint, so it goes back where it came from — the
    destination still holds the PREVIOUS artifact and no `.prev.*` is left behind."""
    part, dst = _seed_publish(tmp_path)
    _replace_spy(monkeypatch, ["eio_after", "eio_before"])
    with pytest.raises(OSError):
        common._publish_replace(part, dst)
    assert dst.exists()
    assert dst.read_bytes() == b"old", "the previous checkpoint was not restored"
    assert not list(dst.parent.glob("*.prev.*"))


def test_an_eio_that_did_not_rename_never_publishes_over_the_destination(
        tmp_path, monkeypatch):
    """The other half of the re-probe: dest is STILL THERE, so the rename did not
    land. Publishing now would run os.replace over an existing destination on this
    mount — the unproven case D4 exists to avoid — so it re-raises instead. The
    raise leaves _copy_to_drive (whose retry loop covers the copy, not the publish)
    and what stays on Drive is the previous checkpoint, intact."""
    part, dst = _seed_publish(tmp_path)
    calls = _replace_spy(monkeypatch, ["eio_before"])
    with pytest.raises(OSError):
        common._publish_replace(part, dst)
    assert dst.read_bytes() == b"old"
    assert len(calls) == 1, f"published over an existing destination: {calls}"
    assert not list(dst.parent.glob("*.prev.*"))


# ── the same completes-then-fails shape, one line lower ──────────────────────
# The two tests below cover the PUBLISH rename and the aside-that-landed-anyway.
# Both were written against the restore path, which used to act on the exception
# alone: `os.replace(aside, dest)` on any OSError, and `aside.unlink()` whenever
# dest re-probed present. Each destroys data in exactly the case the probe is
# what is wrong, and the first of them also runs the D4-forbidden replace.

def test_a_landed_publish_is_never_reverted_by_the_restore(tmp_path, monkeypatch):
    """The publish rename lands and THEN reports EIO. Restoring the aside now would
    (a) run os.replace over an EXISTING destination — the case this whole function
    exists to avoid — and (b) revert a good new checkpoint to the previous one while
    the caller is told the publish failed. The probe stops both; the aside stays for
    _sweep_part_orphans, because deleting it is only ever safe if the probe is
    honest, and the probe is the thing in doubt."""
    part, dst = _seed_publish(tmp_path)
    calls = _replace_spy(monkeypatch, ["ok", "eio_after"])
    with pytest.raises(OSError):
        common._publish_replace(part, dst)
    assert dst.read_bytes() == b"new", "a landed checkpoint was reverted"
    assert not any(existed for _, _, existed, _ in calls), \
        f"replaced over an existing destination: {calls}"
    asides = list(dst.parent.glob("*.prev.*"))
    assert len(asides) == 1 and asides[0].read_bytes() == b"old", \
        f"the previous checkpoint was not kept: {asides}"


def test_an_aside_that_landed_anyway_keeps_the_last_copy(tmp_path, monkeypatch):
    """The aside rename lands, reports EIO, and dest then re-probes PRESENT — the
    one reading under which the old code unlinked the aside. If that probe is right
    the unlink drops a duplicate the sweep would collect anyway; if it is wrong it
    drops the only copy of the checkpoint, because the caller's `finally` takes the
    `.part.*` with it. So the aside survives, and nothing is published."""
    part, dst = _seed_publish(tmp_path)
    calls = _replace_spy(monkeypatch, ["eio_after"])
    real_exists = Path.exists

    def _lie(self):
        # only after the rename has moved dest, and only for dest itself
        if calls and self.name == dst.name:
            return True
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", _lie)
    with pytest.raises(OSError):
        common._publish_replace(part, dst)
    asides = list(dst.parent.glob("*.prev.*"))
    assert len(asides) == 1 and asides[0].read_bytes() == b"old", \
        f"the last copy of the checkpoint was unlinked: {asides}"
    assert part.read_bytes() == b"new", "the staged copy was touched"
    assert len(calls) == 1, f"published while the destination read present: {calls}"


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


# ── D18: local staging keyed on the FULL destination, not the basename ───────

def test_same_basename_different_destination_gets_its_own_scratch_file():
    """THE D18 CORE. LOCAL_SCRATCH is shared by every process on the VM and the
    scratch name was the basename alone, so two different Drive destinations
    ending in the same filename mapped to ONE local file — each publishing the
    other's bytes."""
    a = common._scratch_name("/content/drive/MyDrive/treedata/phase4/eval/report.csv")
    b = common._scratch_name("/content/drive/MyDrive/treedata/phase4/qc/report.csv")
    assert a != b, (a, b)


def test_scratch_name_keeps_the_extension():
    """GDAL picks its driver from the extension; losing it breaks every writer."""
    assert common._scratch_name(
        "/content/drive/MyDrive/treedata/phase4/models/sem_best_2009_x.pt"
    ).endswith(".pt")
    # a .tif/.gpkg pair shares a stem — both must stay distinguishable AND typed
    t = common._scratch_name("/content/drive/x/edmonds_canopy_mask_2009.tif")
    g = common._scratch_name("/content/drive/x/edmonds_canopy_mask_2009.gpkg")
    assert t.endswith(".tif") and g.endswith(".gpkg") and t != g


def test_scratch_name_is_deterministic():
    """No pid, no token: a retry after a crash must REUSE and overwrite the same
    staging file. A unique name per attempt would leak multi-GB rasters onto a
    scratch disk nothing sweeps."""
    p = "/content/drive/MyDrive/treedata/phase4/masks/edmonds_canopy_prob_2013_x.tif"
    assert common._scratch_name(p) == common._scratch_name(p)


def test_local_paths_are_not_staged_at_all():
    assert common._local_artifact_path(Path("/tmp/x.tif")) == Path("/tmp/x.tif")


def test_gpkg_layer_name_is_pinned_not_inherited_from_the_filename():
    """WHY postproc now passes layer= explicitly. The GPKG driver names the layer
    after the FILE BASENAME, and that file is written under a staging name — so
    the staging name was leaking into the published artifact's internal metadata.
    Both halves measured here, not assumed."""
    fiona = pytest.importorskip("fiona")
    import tempfile
    schema = {"geometry": "Point", "properties": {}}
    with tempfile.TemporaryDirectory() as d:
        staged = Path(d) / "edmonds_canopy_mask_2009_x__3f2a9c01.gpkg"
        # the defect: no layer= ⇒ the layer is named after the staging file
        with fiona.open(staged, "w", driver="GPKG", schema=schema, crs="EPSG:4326"):
            pass
        assert fiona.listlayers(staged) == ["edmonds_canopy_mask_2009_x__3f2a9c01"]
        staged.unlink()
        # the fix: pinned to the FINAL stem, which is exactly today's value
        with fiona.open(staged, "w", driver="GPKG", schema=schema, crs="EPSG:4326",
                        layer="edmonds_canopy_mask_2009_x"):
            pass
        assert fiona.listlayers(staged) == ["edmonds_canopy_mask_2009_x"]


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


# ── an EIO on a STAT is not a verdict about the checkpoint (2026-09-09) ──────
# bb50_2011s_cor05 died at epoch A17 inside _publish_replace's very first line,
# `dest.exists()`, with `OSError: [Errno 5] Input/output error`
# (phase4/logs/phase4_semantic_finetune_train_2011s_2026-09-09T09-03.log). The copy
# had succeeded and the checkpoint was on local NVMe; one metadata call the mount
# answered with EIO ended the train step. The probes now retry EIO/ENOTCONN,
# bounded — and NOTHING ELSE, which the third test is there to prove.

def _flaky_exists(monkeypatch, name, exc, times):
    """Path.exists raises `exc` the first `times` calls for `name`, then answers
    honestly. Returns the call log (one entry per probe of `name`)."""
    real = Path.exists
    calls = []

    def _probe(self):
        if self.name == name:
            calls.append(len(calls))
            if len(calls) <= times:
                raise exc
        return real(self)

    monkeypatch.setattr(Path, "exists", _probe)
    return calls


def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(common.time, "sleep", lambda s: slept.append(s))
    return slept


def test_an_eio_on_the_publish_probe_is_retried_and_the_publish_completes(
        tmp_path, monkeypatch, capsys):
    """THE 2011s_cor05 SHAPE: exists() raises EIO twice, then answers. The publish
    must complete, and each retry must be logged so the mount hiccup is visible in
    the step log rather than silently absorbed."""
    part, dst = _seed_publish(tmp_path)
    calls = _flaky_exists(monkeypatch, dst.name, _eio(), times=2)
    slept = _no_sleep(monkeypatch)
    common._publish_replace(part, dst)
    assert dst.read_bytes() == b"new", "the publish did not land"
    assert not list(dst.parent.glob("*.prev.*")) and not part.exists()
    assert len(calls) >= 3, f"the probe was not retried: {calls}"
    assert slept == [2, 4], f"backoff 2 s then 4 s expected, slept {slept}"
    out = capsys.readouterr().out
    assert out.count("retrying in") == 2, out


def test_a_mount_that_keeps_raising_eio_still_kills_the_step(tmp_path, monkeypatch):
    """Bounded: six EIOs in a row exceed the five tries, and the ORIGINAL OSError
    propagates (errno 5 intact, so known_failures.yaml's 'Errno 5' match still
    fires). A mount refusing for a minute is dead; hanging would be worse."""
    part, dst = _seed_publish(tmp_path)
    calls = _flaky_exists(monkeypatch, dst.name, _eio(), times=6)
    slept = _no_sleep(monkeypatch)
    with pytest.raises(OSError) as ei:
        common._publish_replace(part, dst)
    assert ei.value.errno == 5
    assert len(calls) == 5, f"expected exactly 5 tries, saw {len(calls)}"
    assert slept == [2, 4, 8, 16], slept
    assert dst.read_bytes() == b"old", "the previous checkpoint was touched"


def test_only_eio_and_enotconn_are_retried(tmp_path, monkeypatch):
    """THE GATE ON THE MASK. A PermissionError (errno 13) is a real answer about the
    path, not a mount hiccup: it must propagate on the FIRST probe, with no sleep.
    Widening the retry to every OSError would hide exactly the failures this
    module exists to surface."""
    import errno as _errno
    part, dst = _seed_publish(tmp_path)
    calls = _flaky_exists(monkeypatch, dst.name,
                          PermissionError(_errno.EACCES, "denied"), times=1)
    slept = _no_sleep(monkeypatch)
    with pytest.raises(PermissionError):
        common._publish_replace(part, dst)
    assert len(calls) == 1 and slept == [], (calls, slept)
    # ...and ENOTCONN (transport endpoint not connected — a dropped FUSE mount) IS
    # in the retried set, on the same bounded terms as EIO.
    part2, dst2 = _seed_publish(tmp_path / "b")
    calls2 = _flaky_exists(monkeypatch, dst2.name,
                           OSError(_errno.ENOTCONN, "not connected"), times=1)
    common._publish_replace(part2, dst2)
    assert dst2.read_bytes() == b"new" and len(calls2) >= 2


def test_copy_to_drive_survives_an_eio_on_the_part_stat(tmp_path, monkeypatch):
    """The other probe on the publish path: `part.stat()` right after the copy. One
    EIO there used to fall through _copy_to_drive's retry loop as an unhandled
    exception (the loop catches the COPY's OSError, not the stat's)."""
    import errno as _errno
    src = _write(tmp_path / "local" / "sem_best_2009_x.pt", b"payload")
    dst = tmp_path / "drive" / "sem_best_2009_x.pt"
    real_stat = Path.stat
    n = {"raised": 0}

    def _stat(self, *a, **k):
        if ".part." in self.name and n["raised"] < 1:
            n["raised"] += 1
            raise OSError(_errno.EIO, "input/output error")
        return real_stat(self, *a, **k)

    monkeypatch.setattr(Path, "stat", _stat)
    slept = _no_sleep(monkeypatch)
    common._copy_to_drive(src, dst)
    assert dst.read_bytes() == b"payload" and n["raised"] == 1 and slept == [2]

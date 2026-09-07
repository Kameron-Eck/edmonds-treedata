"""postproc's probability-raster SOURCE decision (P4.3, 2026-09-07).

WHAT THIS GUARDS. step_postproc reads the per-year probability raster in 4096-row
windows. When that file sits on the Colab Drive FUSE mount, those windows become
thousands of small latency-bound range reads: 96% of postproc samples showed no GPU,
no CPU, no disk and no network activity at once
(Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §7) while one sequential file reads
at ~40 MB/s (§1). That postproc's elapsed time tracks the raster's SIZE — how strongly
and over how many runs — is recorded once, at core.py::step_inference, and is not
restated here. Commit 5096b03 read a local copy only when inference had left one in the
same process, and otherwise fell back to the Drive path — which is the pathology itself,
not a fallback away from it.

`phase4seg.postproc._resolve_prob_source` is that decision, factored out so it can be
exercised without a Drive mount and without Colab. These tests pin its outcomes plus the
two invariants that matter operationally:

  * it NEVER raises, because a staging problem must cost speed, not the run; and
  * it never hands step_postproc a scratch file whose size disagrees with the Drive
    original. common.py::_stage_imagery_local copies with a bare shutil.copy2 (no
    atomic rename, no post-copy verify) and swallows its own failures, so a killed copy
    leaves a truncated multi-GB file that nothing sweeps. Both guards against that —
    the pre-check on an inherited copy and the post-check on one we made — are SHOWN
    here to FIRE on a known-bad input, per CLAUDE.md §3.4c.

Everything is monkeypatched (`_local_artifact_path`, `_stage_imagery_local`,
`_unstage_imagery_local`, `_is_drive_path`, `shutil.disk_usage`,
`postproc.LOCAL_SCRATCH`) and every real path lives under tmp_path — no lake write, no
/content, no multi-GB copy (the fake staging moves the fixture's 4 KB so the size checks
have something real to compare).

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_postproc_source.py -q
"""
import errno
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

postproc = pytest.importorskip("phase4seg.postproc")

GB = 1_000_000_000
SRC_BYTES = 4096


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A fake Drive-vs-scratch world: real files under tmp_path, fake mount test.

    `calls` records every _stage_imagery_local invocation, so a test can assert that
    NO copy was even attempted (the cheap-path cases), not merely that none happened
    to succeed. `unstaged` records every release, which is how the discard guards are
    shown to fire.

    The fake staging really writes the destination: the size the helper re-checks after
    copying has to come from a file that exists. `stage_partial` installs a truncating
    variant — the interrupted-copy failure mode.
    """
    scratch = tmp_path / "scratch"
    drive = tmp_path / "drive"
    drive.mkdir()
    monkeypatch.setattr(postproc, "LOCAL_SCRATCH", scratch)
    # Default: the destination is treated as on-Drive, so _local_artifact_path maps it
    # into scratch exactly as common.py::_local_artifact_path does on Colab.
    monkeypatch.setattr(postproc, "_is_drive_path", lambda p: Path(p).parent == drive)
    monkeypatch.setattr(postproc, "_local_artifact_path",
                        lambda f: scratch / Path(f).name)

    calls, unstaged = [], []

    def _make_stage(keep_bytes=None):
        def _stage(src):
            src = Path(src)
            calls.append(src)
            dst = scratch / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            data = src.read_bytes()
            dst.write_bytes(data if keep_bytes is None else data[:keep_bytes])
            return dst
        return _stage

    monkeypatch.setattr(postproc, "_stage_imagery_local", _make_stage())

    def _unstage(p):
        # common.py::_unstage_imagery_local guards on the star-imported LOCAL_SCRATCH
        # bound in ITS OWN module, which monkeypatching postproc.LOCAL_SCRATCH does not
        # move — the real helper would silently no-op here and the discard guards would
        # never be shown to fire. This fake applies the same guard against the patched
        # scratch dir, records the call, and (like the real one) never raises.
        p = Path(p)
        assert p.parent == scratch, f"unstage escaped the scratch dir: {p}"
        unstaged.append(p)
        try:
            p.unlink()
        except OSError:
            pass

    monkeypatch.setattr(postproc, "_unstage_imagery_local", _unstage)
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda p: SimpleNamespace(total=0, used=0, free=100 * GB))
    prob_final = drive / "edmonds_canopy_prob_2013.tif"
    prob_final.write_bytes(b"x" * SRC_BYTES)

    def stage_partial(keep_bytes):
        monkeypatch.setattr(postproc, "_stage_imagery_local", _make_stage(keep_bytes))

    return SimpleNamespace(tmp=tmp_path, scratch=scratch, drive=drive,
                           prob_final=prob_final, calls=calls, unstaged=unstaged,
                           stage_partial=stage_partial, monkeypatch=monkeypatch)


def _write_local(env, nbytes):
    """Put a scratch-side copy of `nbytes` where _local_artifact_path will find it."""
    env.scratch.mkdir(exist_ok=True)
    local = env.scratch / env.prob_final.name
    local.write_bytes(b"y" * nbytes)
    return local


def test_inference_copy_is_used_and_nothing_is_staged(env):
    """(i) The copy step_inference left behind wins, and no copy is attempted.

    The SIZE here is load-bearing, not incidental: it matches the Drive original, which
    is now the condition for trusting it (see the truncation test below).
    """
    local = _write_local(env, SRC_BYTES)

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert out == local
    assert staged_here is False        # that copy belongs to step_inference, not us
    assert env.calls == []
    assert env.unstaged == []


def test_short_local_copy_is_discarded_and_restaged(env):
    """THE FIRST GUARD, fired. A truncated scratch file — what an interrupted staging
    copy leaves, since _stage_imagery_local catches its own failure and the run then
    completes over FUSE — must NOT be handed to rasterio. The old `.exists()`-only test
    returned it, and because its TIFF header still reports the full height/width the
    step set up normally and then died mid-window on every retry, forever, until the
    scratch dir was cleared by hand. Discard it and re-stage."""
    local = _write_local(env, 100)

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.unstaged == [local]                 # the guard fired
    assert env.calls == [env.prob_final]           # and it re-staged rather than giving up
    assert out == env.scratch / env.prob_final.name
    assert out.stat().st_size == SRC_BYTES
    assert staged_here is True


def test_short_staged_copy_is_discarded(env):
    """THE SECOND GUARD, fired. _stage_imagery_local verifies size only BEFORE its
    copy (common.py::_stage_imagery_local), so a copy2 that returns short — or one this
    process is killed partway through and retried — is reported as success. Re-check
    after copying: drop it and read over FUSE rather than publish a mask built from a
    stump."""
    env.stage_partial(100)

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.calls == [env.prob_final]
    assert env.unstaged == [env.scratch / env.prob_final.name]
    assert not (env.scratch / env.prob_final.name).exists()
    assert out == env.prob_final
    assert staged_here is False


def test_drive_path_with_room_is_staged(env):
    """(ii) No inference copy + on Drive + scratch has room → stage it, own it."""
    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.calls == [env.prob_final]
    assert out == env.scratch / env.prob_final.name
    assert out != env.prob_final
    assert staged_here is True
    assert env.unstaged == []


def test_staging_failure_returns_the_drive_path(env):
    """(iii) common.py::_stage_imagery_local returns its SOURCE path on failure;
    postproc must then read the Drive path, and must not claim it staged anything."""
    env.monkeypatch.setattr(postproc, "_stage_imagery_local",
                            lambda src: env.calls.append(Path(src)) or Path(src))

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.calls == [env.prob_final]
    assert out == env.prob_final
    assert staged_here is False


def test_insufficient_scratch_space_skips_staging(env):
    """(iv) Free space below STAGE_FREE_MARGIN x size → do not even try the copy.

    Filling the scratch disk mid-copy would strand a partial multi-GB file AND break
    the mask/gpkg writes that follow, which land in the same scratch directory.
    """
    size = env.prob_final.stat().st_size
    tight = int(postproc.STAGE_FREE_MARGIN * size) - 1
    env.monkeypatch.setattr(shutil, "disk_usage",
                            lambda p: SimpleNamespace(total=0, used=0, free=tight))

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.calls == []
    assert out == env.prob_final
    assert staged_here is False


def test_non_drive_path_skips_staging(env):
    """(v) Already on local disk → nothing to stage; copying it onto itself would be
    pure loss. This is the local-run and the mounted-elsewhere case."""
    env.monkeypatch.setattr(postproc, "_is_drive_path", lambda p: False)
    env.monkeypatch.setattr(postproc, "_local_artifact_path", lambda f: Path(f))

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.calls == []
    assert out == env.prob_final
    assert staged_here is False


def test_helper_never_raises_when_staging_throws(env):
    """(vi) THE operational invariant: an exception anywhere in the staging attempt
    degrades to the Drive path. Slow beats dead — postproc still produces the mask."""
    def _boom(src):
        env.calls.append(Path(src))
        raise OSError(errno.EIO, "Input/output error")   # drivefs EIO, the realistic one

    env.monkeypatch.setattr(postproc, "_stage_imagery_local", _boom)

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.calls == [env.prob_final]
    assert out == env.prob_final
    assert staged_here is False


def test_helper_never_raises_when_exists_throws(env):
    """The same invariant on the OTHER leg, which the staging test cannot reach.
    `Path.exists()` is not exception-free: CPython's pathlib swallows only
    ENOENT/ENOTDIR/EBADF/ELOOP and re-raises everything else — including the EIO a
    wedged drivefs mount returns, which is exactly the failure this helper exists to
    survive. So the existence probe has to be inside the try, not before it."""
    real_exists = Path.exists

    def _exists(self, **kw):
        if Path(self).parent == env.drive:
            raise OSError(errno.EIO, "Input/output error")
        return real_exists(self, **kw)

    env.monkeypatch.setattr(Path, "exists", _exists)

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert out == env.prob_final
    assert staged_here is False
    assert env.calls == []


def test_missing_probability_raster_is_not_staged(env):
    """A missing source returns unchanged so step_postproc's own ERROR line — which
    names the path it actually looked for — is what the operator sees."""
    env.prob_final.unlink()

    out, staged_here = postproc._resolve_prob_source(env.prob_final)

    assert env.calls == []
    assert out == env.prob_final
    assert staged_here is False


def test_dry_run_does_not_stage(env):
    """--dry-run prints a threshold and returns without reading the raster; it must
    not pay for a 6.7 GB sequential copy on the way to that. An inference copy that
    ALREADY exists is still used (it costs nothing) — only the copy is gated."""
    out, staged_here = postproc._resolve_prob_source(env.prob_final,
                                                     allow_stage=False)

    assert env.calls == []
    assert out == env.prob_final
    assert staged_here is False

    local = _write_local(env, SRC_BYTES)
    out2, staged2 = postproc._resolve_prob_source(env.prob_final, allow_stage=False)
    assert out2 == local and staged2 is False and env.calls == []


def test_dry_run_discards_a_short_local_copy_but_stages_nothing(env):
    """The size guard runs even under --dry-run, so a stump is dropped (a side effect
    on the dry-run path, deliberately: leaving it would poison the next real run) and
    the Drive path is returned — without a copy, which is what --dry-run is protected
    from."""
    local = _write_local(env, 100)

    out, staged_here = postproc._resolve_prob_source(env.prob_final,
                                                     allow_stage=False)

    assert env.unstaged == [local]
    assert env.calls == []
    assert out == env.prob_final
    assert staged_here is False


def test_is_drive_path_matches_the_test_core_uses():
    """_is_drive_path exists only to be patchable; its rule must stay the one
    core.py::step_train applies to MODELS_DIR (str().startswith('/content/drive')).
    Uses PurePosixPath so the check is meaningful on Windows, where a WindowsPath of
    the same string is backslashed and could never match."""
    from pathlib import PurePosixPath
    assert postproc._is_drive_path(
        PurePosixPath("/content/drive/MyDrive/treedata/phase4/masks/p.tif")) is True
    assert postproc._is_drive_path(PurePosixPath("/content/phase4_scratch/p.tif")) is False


def test_staged_raster_is_released_when_postproc_raises(env, tmp_path):
    """THE LEAK GUARD, fired. step_postproc used to release the staged raster only on
    its success path, so any raise between the resolve and the end — a read error in
    the threshold loop, ENOSPC on the mask write, OOM in the strip polygonize, a
    _copy_to_drive size/sha mismatch — left 3-6.7 GB in LOCAL_SCRATCH. Nothing sweeps
    that name (common.py::_sweep_part_orphans takes only *.part.* / *.prev.*), so a
    multi-year queue leaked one file per failed year until free space fell under
    STAGE_FREE_MARGIN and _resolve_prob_source quietly stopped staging at all — the
    optimization reverting to the pathology, logged as a normal capacity decision.
    The release now lives in a `finally`.

    Only path construction touches MASKS_DIR here; the read dies at the first
    rasterio.open, before anything is written anywhere.
    """
    staged = tmp_path / "staged_prob.tif"
    staged.write_bytes(b"z" * 64)
    env.monkeypatch.setattr(postproc, "_resolve_prob_source",
                            lambda p, allow_stage=True: (staged, True))
    env.monkeypatch.setattr(postproc, "_local_artifact_path",
                            lambda f: tmp_path / Path(f).name)

    def _boom(*a, **kw):
        raise RuntimeError("rasterio open failed")

    env.monkeypatch.setattr(postproc.rasterio, "open", _boom)
    env.monkeypatch.setattr(postproc, "_unstage_imagery_local",
                            lambda p: env.unstaged.append(Path(p)))

    with pytest.raises(RuntimeError):
        postproc.step_postproc("2013")

    assert env.unstaged == [staged]

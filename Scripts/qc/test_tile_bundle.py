"""Tile-bundle gates (2026-09-07) — the transport cache that must never be believed.

WHAT THE BUNDLE IS. Staging a tile set from Drive to local NVMe was measured on the
live pilot at 228.2 s for 1264 files / 0.51 GB — 2.2 MB/s, ~5.5 files/s, with net rx
~0, disk ~0, CPU 1-4%, iowait 0. The A100 was not moving bytes; it was waiting on
per-file Drive API latency. One big sequential file moves at ~40 MB/s on that mount.
So `tiling.py::step_tile` publishes ONE tar beside the tiles and
`staging.py::_stage_from_bundle` reads it in one open.

WHAT MAKES IT SAFE, and what these tests hold. The per-file tile directory stays
CANONICAL and COMPLETE; the bundle is ADVISORY. Nothing is ever readable only from a
bundle, and a bundle that is absent, stale, mismatched, truncated or unreadable is a
cheaper path not taken, never an error — the ladder falls back to today's rclone bulk
copy and then to the per-file loop.

Which means every gate here is a KILL CRITERION, and CLAUDE.md 3.4c says a kill
criterion must be SHOWN TO FIRE on a known-bad input before it counts. Each mutation
below asserts BOTH that the bundle was refused AND that nothing it carried reached the
scratch directory the fallback is about to inherit — because the fallback's own reuse
test is exists+size, which cannot tell a stale same-name same-size tile from the right
one.

THE TEST THAT THE WHOLE DECISION TURNS ON is
`test_same_id_retile_without_the_sweep_serves_the_previous_tilings_bytes`. A re-tile
under an UNCHANGED signature rewrites tiles, index and meta under the SAME id, and
GDAL/LZW output is not guaranteed byte-stable, so a surviving bundle would hand a
trainer the previous tiling's bytes at the right names and the right sizes. It proves
both directions: with `_sweep_bundles` the reader refuses, and WITHOUT it the reader
serves the stale bytes.

No Drive, no rclone, no torch, no GPU, no lake: `_stage_from_bundle` and
`_publish_bundle` take no mount checks, so the whole path is reachable from tmp_path
on Windows. `qc/conftest.py` fails any test that touches the real lake.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_tile_bundle.py -q
"""
import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]

pd = pytest.importorskip("pandas")
staging = pytest.importorskip("phase4seg.staging")
tiling = pytest.importorskip("phase4seg.tiling")
common = pytest.importorskip("phase4seg.common")

KINDS = {"img_path": "images", "mask_path": "masks", "height_path": "heights"}


# ── fixture: a fake tile dir + its local staging mirror ───────────────────────

def _tile_bytes(split, kind, i, salt=b""):
    """Distinguishable, SAME-LENGTH-per-(split,kind,i) payloads. Same length matters:
    the stale-bytes test must not be rescued by a size check."""
    body = f"{split}|{kind}|{i:04d}|".encode() + salt
    return (body * 8)[:512]


def build_tiles(tmp_path, label="2017k", tag="pilot", n=9, heights=False, salt=b"a"):
    """A Drive-side tile dir + the local staging tree the bulk-upload branch holds."""
    src = tmp_path / "tiles" / f"{label}__{tag}"
    stage = tmp_path / "tileout" / str(label)
    rows = []
    for i in range(n):
        split = ("train", "val", "test")[i % 3]
        name = f"t{i:04d}.tif"
        row = {"tile_name": name, "site": "city", "split": split,
               "canopy_frac": round(i / n, 3), "split_mode": "blocked"}
        kinds = [("images", "img_path"), ("masks", "mask_path")]
        if heights and i % 2 == 0:
            kinds.append(("heights", "height_path"))
        for kind, col in kinds:
            data = _tile_bytes(split, kind, i, salt)
            for root in (src, stage):
                q = root / split / kind / name
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(data)
            row[col] = str(src / split / kind / name)
        row.setdefault("height_path", "")
        rows.append(row)
    index_path = src / f"tile_index_{label}.csv"
    pd.DataFrame(rows).to_csv(index_path, index=False)
    meta_path = src / f"tile_index_{label}.meta.json"
    meta_path.write_text(json.dumps({
        "label": label, "citywide": True, "stride": 256, "max_tiles": None,
        "tile_size": 512, "random_seed": 42, "use_hillshade": False,
        "split_status": {"mode": "blocked_spatial", "degraded": False},
    }))
    return SimpleNamespace(src=src, stage=stage, index_path=index_path,
                           meta_path=meta_path, label=label, tag=tag)


def read_index(fx):
    """The index as core.py hands it to staging — read back from the CSV, so empty
    height_path cells arrive as NaN exactly as they do live."""
    df = pd.read_csv(fx.index_path)
    cols = [c for c in KINDS if c in df.columns]
    return df, cols


@pytest.fixture
def copy_counter(monkeypatch):
    """Counts every whole-file transfer staging makes — 'did it move 0.5 GB?'

    BOTH transports, and the second one is not optional. Since the bounded read
    (2026-09-08) the bundle's own 0.5 GB transfer is no longer a `shutil.copyfile`; it
    is `staging._bounded_copy`'s chunk loop. Counting only copyfile would leave the
    three "refused BEFORE any copy" assertions below asserting nothing whatsoever.
    """
    calls = []
    real = shutil.copyfile
    real_bounded = staging._bounded_copy

    def counted(src, dst, **kw):
        calls.append((str(src), str(dst)))
        return real(src, dst, **kw)

    def counted_bounded(src, dst, *a, **kw):
        calls.append((str(src), str(dst)))
        return real_bounded(src, dst, *a, **kw)
    monkeypatch.setattr(staging.shutil, "copyfile", counted)
    monkeypatch.setattr(staging, "_bounded_copy", counted_bounded)
    return calls


def publish(fx, tmp_path, monkeypatch, copy_to_drive=None):
    """Publish the bundle with `_copy_to_drive` replaced by a plain local copy."""
    def fake(local, drive, **kw):
        Path(drive).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, drive)
        return Path(drive)
    monkeypatch.setattr(common, "_copy_to_drive", copy_to_drive or fake)
    tsid = tiling.tileset_id_from_meta(fx.meta_path)
    ok = staging._publish_bundle(fx.stage, fx.src, fx.label, fx.index_path, tsid,
                                 run_tag=fx.tag, tar_dir=tmp_path / "bundleout")
    return tsid, ok


def stage(fx, tmp_path, idx=None, cols=None, dst=None):
    if idx is None:
        idx, cols = read_index(fx)
    dst = dst or (tmp_path / "scratch" / f"{fx.label}__{fx.tag}")
    return staging._stage_from_bundle(fx.src, dst, idx, cols, KINDS, fx.label,
                                      tar_dir=tmp_path / "bundles"), dst


def sidecar_path(fx, tsid):
    return fx.src / staging._bundle_names(tsid)[1]


def tar_path(fx, tsid):
    return fx.src / staging._bundle_names(tsid)[0]


def assert_nothing_staged(dst):
    """The state the fallback must inherit: no tile bytes at all."""
    if not Path(dst).exists():
        return
    stray = [p for p in Path(dst).rglob("*") if p.is_file()]
    assert not stray, f"refusal left {len(stray)} file(s) under {dst}: {stray[:3]}"


# ══ round trip and reuse ══════════════════════════════════════════════════════

def test_round_trip_rewrites_every_path_and_copies_every_byte(tmp_path, monkeypatch):
    fx = build_tiles(tmp_path)
    tsid, ok = publish(fx, tmp_path, monkeypatch)
    assert ok and tsid and tar_path(fx, tsid).exists()

    idx, cols = read_index(fx)
    new_cols, dst = stage(fx, tmp_path, idx, cols)
    assert new_cols is not None

    for c in cols:
        for old, new in zip(idx[c], new_cols[c]):
            if not (isinstance(old, str) and old):
                continue
            assert str(new).startswith(str(dst)), f"{c} not rewritten: {new}"
            assert Path(new).read_bytes() == Path(old).read_bytes()
    done = dst / staging._bundle_names(tsid)[2]
    assert json.loads(done.read_text())["tileset_id"] == tsid
    # The local tar is not left behind — scratch must not carry the set twice.
    assert not list((tmp_path / "bundles").glob("*.tar"))


def test_second_call_copies_nothing_and_still_rewrites(tmp_path, monkeypatch,
                                                       copy_counter):
    fx = build_tiles(tmp_path)
    publish(fx, tmp_path, monkeypatch)
    idx, cols = read_index(fx)
    first, dst = stage(fx, tmp_path, idx, cols)
    assert first is not None
    n_after_first = len(copy_counter)

    second, _ = stage(fx, tmp_path, idx, cols, dst=dst)
    assert second is not None
    assert len(copy_counter) == n_after_first, "reuse copied bytes it did not need to"
    assert second["img_path"] == first["img_path"]


def test_aux_height_sidecars_ride_along_and_empty_cells_are_tolerated(
        tmp_path, monkeypatch):
    fx = build_tiles(tmp_path, heights=True)
    publish(fx, tmp_path, monkeypatch)
    idx, cols = read_index(fx)
    assert "height_path" in cols
    new_cols, dst = stage(fx, tmp_path, idx, cols)
    assert new_cols is not None

    n_h = 0
    for old, new in zip(idx["height_path"], new_cols["height_path"]):
        if isinstance(old, str) and old:
            n_h += 1
            assert Path(new).read_bytes() == Path(old).read_bytes()
            assert "/heights/" in Path(new).as_posix()
        else:
            assert not (isinstance(new, str) and str(new).startswith(str(dst)))
    assert n_h > 0, "fixture wrote no height sidecars — the test proves nothing"


# ══ mutations: each must FIRE ═════════════════════════════════════════════════

def test_changed_signature_makes_the_old_bundle_unreachable(tmp_path, monkeypatch,
                                                            copy_counter):
    """THE HEADLINE GUARD. A re-signature gives a new id; the reader derives the id
    it wants from the CURRENT meta, so a stale bundle is unreachable by name."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    meta = json.loads(fx.meta_path.read_text())
    meta["stride"] = 128                        # a real _tile_signature key
    fx.meta_path.write_text(json.dumps(meta))
    assert tiling.tileset_id_from_meta(fx.meta_path) != tsid

    n0 = len(copy_counter)
    out, dst = stage(fx, tmp_path)
    assert out is None
    assert len(copy_counter) == n0, "refused, but still copied the tar"
    assert_nothing_staged(dst)


def test_a_stale_bundle_renamed_to_the_new_id_is_still_refused(tmp_path, monkeypatch):
    """The scenario the filename ALONE cannot catch, and the reason the sidecar
    records its own tileset_id redundantly."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    meta = json.loads(fx.meta_path.read_text())
    meta["stride"] = 128
    fx.meta_path.write_text(json.dumps(meta))
    new_id = tiling.tileset_id_from_meta(fx.meta_path)

    tar_path(fx, tsid).rename(fx.src / staging._bundle_names(new_id)[0])
    sidecar_path(fx, tsid).rename(fx.src / staging._bundle_names(new_id)[1])

    out, dst = stage(fx, tmp_path)
    assert out is None
    assert_nothing_staged(dst)


def test_a_rewritten_index_under_an_unchanged_signature_is_refused(tmp_path,
                                                                   monkeypatch):
    fx = build_tiles(tmp_path)
    publish(fx, tmp_path, monkeypatch)
    with open(fx.index_path, "a", encoding="utf-8") as fh:
        fh.write("tX.tif,city,train,0.5,blocked,/x/i.tif,/x/m.tif,\n")
    out, dst = stage(fx, tmp_path)
    assert out is None
    assert_nothing_staged(dst)


def test_a_manifest_that_misses_one_index_tile_is_refused_before_any_copy(
        tmp_path, monkeypatch, copy_counter):
    """The ID-INDEPENDENT guard: a matching id is not enough."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    sc = json.loads(sidecar_path(fx, tsid).read_text())
    dropped = sc["files"].pop(0)
    sidecar_path(fx, tsid).write_text(json.dumps(sc))

    n0 = len(copy_counter)
    out, dst = stage(fx, tmp_path)
    assert out is None
    assert len(copy_counter) == n0, (
        f"refused only after copying the tar; {dropped['rel']} should have been "
        f"caught by the manifest cross-check, before any bulk transfer")
    assert_nothing_staged(dst)


def test_a_flipped_byte_inside_the_tar_is_refused(tmp_path, monkeypatch):
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    tp = tar_path(fx, tsid)
    raw = bytearray(tp.read_bytes())
    off = len(raw) // 2
    raw[off] ^= 0xFF
    tp.write_bytes(bytes(raw))

    out, dst = stage(fx, tmp_path)
    assert out is None
    assert_nothing_staged(dst)
    assert not list((tmp_path / "bundles").glob("*.tar")), "local tar not unlinked"


def test_a_truncated_tar_is_refused(tmp_path, monkeypatch):
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    tp = tar_path(fx, tsid)
    tp.write_bytes(tp.read_bytes()[:-1])
    out, dst = stage(fx, tmp_path)
    assert out is None
    assert_nothing_staged(dst)


def test_a_tar_orphaned_by_a_mid_publish_death_is_inert(tmp_path, monkeypatch):
    """A death between the tar publish and the sidecar write leaves a .tar with no
    .json. The reader requires the sidecar, so it is inert rather than dangerous."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    sidecar_path(fx, tsid).unlink()
    assert tar_path(fx, tsid).exists()
    out, dst = stage(fx, tmp_path)
    assert out is None
    assert_nothing_staged(dst)


@pytest.mark.parametrize("evil", ["../evil.tif", "/etc/evil.tif",
                                  "train/../../evil.tif", "sneaky/images/evil.tif"])
def test_a_tar_member_outside_the_tile_layout_is_refused(tmp_path, monkeypatch, evil):
    """MUST hold on the tmp_path TREE, not just on the return value: an assertion on
    the return alone would not catch a traversal that had already written."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    tp = tar_path(fx, tsid)
    payload = tmp_path / "payload.tif"
    payload.write_bytes(b"pwned")
    with tarfile.open(tp, "a") as tf:
        tf.add(payload, arcname=evil, recursive=False)
    sc = json.loads(sidecar_path(fx, tsid).read_text())
    sc["tar_size"] = tp.stat().st_size
    sc["tar_sha256"] = staging._sha256_file(tp)
    sidecar_path(fx, tsid).write_text(json.dumps(sc))

    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    out, dst = stage(fx, tmp_path)
    assert out is None
    assert_nothing_staged(dst)
    after = {p for p in tmp_path.rglob("*") if p.is_file()}
    strays = [p for p in after - before if not p.is_relative_to(dst)]
    assert not strays, f"a rejected member wrote outside {dst}: {strays}"
    assert not any(p.read_bytes() == b"pwned" for p in after - before)


def test_a_symlink_member_is_refused(tmp_path, monkeypatch):
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    tp = tar_path(fx, tsid)
    with tarfile.open(tp, "a") as tf:
        ti = tarfile.TarInfo("train/images/link.tif")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/etc/passwd"
        tf.addfile(ti)
    sc = json.loads(sidecar_path(fx, tsid).read_text())
    sc["files"].append({"rel": "train/images/link.tif", "size": 0})
    sc["tar_size"] = tp.stat().st_size
    sc["tar_sha256"] = staging._sha256_file(tp)
    sidecar_path(fx, tsid).write_text(json.dumps(sc))

    out, dst = stage(fx, tmp_path)
    assert out is None
    assert_nothing_staged(dst)


def test_a_manifest_entry_outside_the_tile_layout_is_refused_up_front(
        tmp_path, monkeypatch, copy_counter):
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    sc = json.loads(sidecar_path(fx, tsid).read_text())
    sc["files"].append({"rel": "../../evil.tif", "size": 5})
    sidecar_path(fx, tsid).write_text(json.dumps(sc))

    n0 = len(copy_counter)
    out, dst = stage(fx, tmp_path)
    assert out is None
    assert len(copy_counter) == n0
    assert_nothing_staged(dst)


def test_a_done_marker_from_another_tileset_is_rmtreed_not_extracted_over(
        tmp_path, monkeypatch):
    """The one scenario that defeats the fallback's exists+size reuse test: stale
    same-name SAME-SIZE tiles under a marker from a different id."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    idx, cols = read_index(fx)
    dst = tmp_path / "scratch" / f"{fx.label}__{fx.tag}"

    stale = {}
    for _, row in idx.iterrows():
        for c in ("img_path", "mask_path"):
            q = dst / row["split"] / KINDS[c] / row["tile_name"]
            q.parent.mkdir(parents=True, exist_ok=True)
            good = Path(row[c]).read_bytes()
            q.write_bytes(b"X" * len(good))          # same size, wrong bytes
            stale[q] = good
    (dst / staging._bundle_names("deadbeef1234")[2]).write_text(json.dumps(
        {"tileset_id": "deadbeef1234", "index_sha256": "x", "n_files": 99}))

    out, _ = stage(fx, tmp_path, idx, cols, dst=dst)
    assert out is not None, "a foreign marker must not make the bundle unusable"
    assert not (dst / staging._bundle_names("deadbeef1234")[2]).exists(), \
        "the foreign marker survived — dst_root was not rmtree'd"
    for q, good in stale.items():
        assert q.read_bytes() == good, f"stale bytes survived at {q}"


# ══ the sweep: the same-id re-tile ════════════════════════════════════════════

def test_same_id_retile_without_the_sweep_serves_the_previous_tilings_bytes(
        tmp_path, monkeypatch):
    """THE TEST THE WHOLE DECISION TURNS ON, proved in BOTH directions.

    A re-tile under an unchanged signature rewrites tiles + index + meta under the
    SAME id. Tile names are positional, GDAL/LZW output is not guaranteed byte-stable
    across runs, and a deterministic re-sample writes a byte-IDENTICAL index CSV — so
    neither the id nor `index_sha256` nor the manifest's sizes can tell the two
    tilings apart. Only unlinking the bundle before the re-tile can.
    """
    fx = build_tiles(tmp_path, salt=b"OLD")
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    old_index = fx.index_path.read_bytes()

    # RE-TILE: same names, same sizes, same index bytes, same meta — different bytes.
    fx2 = build_tiles(tmp_path, salt=b"NEW")
    assert fx2.src == fx.src and fx2.index_path.read_bytes() == old_index
    assert tiling.tileset_id_from_meta(fx.meta_path) == tsid
    fresh = (fx.src / "train" / "images" / "t0000.tif").read_bytes()

    # (a) WITHOUT the sweep the stale bundle is accepted and serves the OLD bytes.
    out_a, dst_a = stage(fx, tmp_path, dst=tmp_path / "scratch_nosweep")
    assert out_a is not None
    served = (dst_a / "train" / "images" / "t0000.tif").read_bytes()
    assert served != fresh, (
        "the demonstration failed to reproduce the hazard — without the sweep the "
        "reader is supposed to serve the PREVIOUS tiling's bytes")

    # (b) WITH the sweep — which step_tile runs before the first tile is written —
    #     there is no bundle to select and the reader falls back.
    gone = tiling._sweep_bundles(fx.src)
    assert sorted(gone) == sorted(staging._bundle_names(tsid)[:2])
    out_b, dst_b = stage(fx, tmp_path, dst=tmp_path / "scratch_swept")
    assert out_b is None
    assert_nothing_staged(dst_b)


def test_a_same_id_retile_is_not_served_from_the_local_done_marker(tmp_path,
                                                                   monkeypatch):
    """THE SCRATCH-SIDE HALF of the same-id hazard, and it reaches through the local
    cache rather than through Drive.

    One VM: train stages bundle A and writes a `.done`. `--force-retile` on the same
    arm sweeps the Drive bundle, rewrites the tiles with DIFFERENT bytes at identical
    names and sizes, writes a byte-identical index (deterministic re-sample) and an
    unchanged meta — so the republished bundle is id A again. On the next train, id,
    index_sha256, n_files and every LOCAL size still match the marker the previous
    tiling left. Only the tar's sha256 separates the two tilings.
    """
    fx = build_tiles(tmp_path, salt=b"OLD")
    publish(fx, tmp_path, monkeypatch)
    dst = tmp_path / "scratch" / f"{fx.label}__{fx.tag}"
    first, _ = stage(fx, tmp_path, dst=dst)
    assert first is not None
    old_bytes = (dst / "train" / "images" / "t0000.tif").read_bytes()

    tsid_before = tiling.tileset_id_from_meta(fx.meta_path)
    fx2 = build_tiles(tmp_path, salt=b"NEW")            # same dir, same names/sizes
    assert fx2.src == fx.src
    tiling._sweep_bundles(fx.src)
    tsid_after, _ = publish(fx2, tmp_path, monkeypatch)
    assert tsid_after == tsid_before, "the fixture failed to reproduce a same-id retile"
    new_bytes = (fx.src / "train" / "images" / "t0000.tif").read_bytes()
    assert len(new_bytes) == len(old_bytes) and new_bytes != old_bytes

    second, _ = stage(fx2, tmp_path, dst=dst)
    assert second is not None
    served = (dst / "train" / "images" / "t0000.tif").read_bytes()
    assert served == new_bytes, (
        "the local .done marker served the PREVIOUS tiling's bytes — the reuse test "
        "must compare the tar's sha256, not just id + index_sha256 + sizes")


def test_a_stale_local_tree_is_cleared_even_when_the_bundle_then_refuses(
        tmp_path, monkeypatch):
    """THE HALF THE MARKER CHECK LEFT OPEN, and the one place the code already knew
    the answer and threw it away.

    Detecting a stale `.done` is not enough, because detection is not the last thing
    that can happen. Steps 8-9 can still refuse AFTER it, for three reasons — the
    cross-VM async-upload race on a --vfs-cache-mode writes mount, which
    `_publish_bundle`'s own docstring calls the EXPECTED outcome; a transient mount
    EIO during the 0.5 GB read, which `common._copy_to_drive` already retries for;
    and a peer's `_sweep_bundles` unlinking the tar mid-copy. Unlinking only the marker
    then handed the rclone fallback the PREVIOUS tiling's tiles — same names, same
    sizes — and its exists+size test copied nothing at all.

    Here: stage tiling OLD from its bundle, re-tile to NEW under the same id, and
    truncate the republished tar so the size gate fires. The refusal must leave the
    fallback an EMPTY directory, not the old set.
    """
    fx = build_tiles(tmp_path, salt=b"OLD")
    publish(fx, tmp_path, monkeypatch)
    dst = tmp_path / "scratch" / f"{fx.label}__{fx.tag}"
    first, _ = stage(fx, tmp_path, dst=dst)
    assert first is not None
    old_bytes = (dst / "train" / "images" / "t0000.tif").read_bytes()

    fx2 = build_tiles(tmp_path, salt=b"NEW")          # same dir, names, sizes, index
    tiling._sweep_bundles(fx.src)
    tsid, _ = publish(fx2, tmp_path, monkeypatch)
    tp = tar_path(fx2, tsid)
    tp.write_bytes(tp.read_bytes()[:-4096])           # the peer read it mid-upload

    out, _ = stage(fx2, tmp_path, dst=dst)
    assert out is None, "a truncated tar must be refused"
    assert not (dst / staging._bundle_names(tsid)[2]).exists(), "marker survived"
    assert_nothing_staged(dst)
    # named explicitly, because this is the byte sequence that would have been trained
    # on: the fallback must not find the OLD tiling sitting there at the right size.
    survivor = dst / "train" / "images" / "t0000.tif"
    assert not survivor.exists(), (
        f"the refusal left the PREVIOUS tiling's tile at {survivor} — the rclone "
        f"fallback's exists+size test will copy nothing and train on {old_bytes[:16]!r}")


def test_the_sweep_removes_only_bundle_files(tmp_path):
    d = tmp_path / "tiles" / "2017k__pilot"
    (d / "train" / "images").mkdir(parents=True)
    keep = [d / "tile_index_2017k.csv", d / "tile_index_2017k.meta.json",
            d / "train" / "images" / "t0.tif"]
    for q in keep:
        q.write_bytes(b"keep")
    kill = [d / "_bundle_deadbeef1234.tar", d / "_bundle_deadbeef1234.json",
            d / "_bundle_deadbeef1234.tar.part.99abc"]
    for q in kill:
        q.write_bytes(b"kill")

    gone = tiling._sweep_bundles(d)
    assert sorted(gone) == sorted(q.name for q in kill)
    assert all(q.exists() for q in keep)
    assert not any(q.exists() for q in kill)


def test_the_sweep_is_placed_after_both_dry_run_returns_and_before_the_write_loop():
    """A source-order pin, because `step_tile` needs a real ortho to drive.

    Placed wrongly (the design's original "before the split mkdirs"), a `--dry-run`
    would unlink a valid 0.5 GB bundle and force the next train to fall back for
    nothing. Placed after the write loop, a same-id re-tile keeps its stale bundle.
    """
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    body = src[src.index("def step_tile("):]
    sweep = body.index("_sweep_bundles(out_tile_dir)")
    write_loop = body.index('for rec in tqdm(all_records, desc="  Writing tiles")')
    bail = body.index("no tiles for")
    dry_runs = [m.start() for m in re.finditer(r"Dry run — not writing tiles", body)]
    assert len(dry_runs) == 2, "step_tile no longer has exactly two dry-run returns"
    assert sweep > max(dry_runs), "the sweep would delete a bundle on --dry-run"
    assert sweep > bail, "the sweep runs even when there are no tiles to write"
    assert sweep < write_loop, "the sweep runs after Drive-side tiles are mutated"
    assert body.index("_bulk_upload_tiles(stage_root") > sweep


def test_the_sweep_is_not_gated_on_the_bundle_flag():
    """With publishing off, a same-id re-tile that skipped the sweep would leave a
    stale bundle in the dir, and the moment the flag was turned on a reader would
    consume the previous tiling's bytes."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    body = src[src.index("def step_tile("):]
    sweep_line = next(ln for ln in body.splitlines()
                      if "_sweep_bundles(out_tile_dir)" in ln)
    assert "_bundle_enabled" not in sweep_line
    # and it is not nested under a flag check either
    before = body[:body.index("_sweep_bundles(out_tile_dir)")]
    assert "_bundle_enabled" not in before.rsplit("\n\n", 1)[-1]


# ══ publish side: never raises, never blocks the canonical write ══════════════

def test_publish_swallows_a_failing_copy_and_leaves_the_tile_set_valid(
        tmp_path, monkeypatch, capsys):
    fx = build_tiles(tmp_path)

    def boom(local, drive, **kw):
        raise OSError(5, "Input/output error")
    tsid, ok = publish(fx, tmp_path, monkeypatch, copy_to_drive=boom)
    assert ok is False
    out = capsys.readouterr().out
    assert "tile bundle NOT published" in out

    assert fx.index_path.exists() and fx.meta_path.exists()
    assert tiling.tileset_id_from_meta(fx.meta_path) == tsid
    assert not list(fx.src.glob("_bundle_*")), "a failed publish left debris on Drive"
    assert not list((tmp_path / "bundleout").glob("*.tar")), "local tar not unlinked"
    # the staging tree is untouched, so a re-run still resumes cheaply
    assert (fx.stage / "train" / "images" / "t0000.tif").exists()
    # and the reader refuses cleanly rather than erroring
    assert stage(fx, tmp_path)[0] is None


def test_publish_refuses_a_staging_root_that_is_not_a_tile_layout(tmp_path,
                                                                  monkeypatch):
    fx = build_tiles(tmp_path)
    (fx.stage / "stray.txt").write_bytes(b"x")
    _, ok = publish(fx, tmp_path, monkeypatch)
    assert ok is False
    assert not list(fx.src.glob("_bundle_*"))


def test_publish_without_a_tileset_id_is_a_no_op(tmp_path, monkeypatch, capsys):
    """6-site tiling writes no meta, so there is no id and no bundle."""
    fx = build_tiles(tmp_path)
    monkeypatch.setattr(common, "_copy_to_drive", lambda *a, **k: pytest.fail(
        "publish copied something without a tile-set id"))
    assert staging._publish_bundle(fx.stage, fx.src, fx.label, fx.index_path, None,
                                   tar_dir=tmp_path / "bundleout") is False
    assert "no tile-set id" in capsys.readouterr().out
    assert not list(fx.src.glob("_bundle_*"))


def test_the_staging_root_rmtree_moved_out_of_the_upload_and_after_the_publish():
    """`_bulk_upload_fail` still raises BEFORE the new rmtree site, so its promise
    that "the LOCAL staging copy is KEPT so a re-run resumes cheaply" holds."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    upload = src[src.index("def _bulk_upload_tiles("):src.index("def step_tile(")]
    assert "rmtree(stage_root" not in upload, \
        "the staging tree is still removed inside the upload — the bundle would " \
        "have nothing verified to build from"
    body = src[src.index("def step_tile("):]
    # rindex: the FIRST rmtree(stage_root) in step_tile is the top-of-run cleanup of
    # a leftover staging tree from an earlier, differently-sampled run.
    assert body.index("_publish_bundle(") < body.rindex("rmtree(stage_root")


# ══ the timing event the live validation is read from ════════════════════════

def test_a_reuse_hit_and_a_real_extract_report_whether_bytes_moved(tmp_path,
                                                                   monkeypatch):
    """`report["copied"]` is the bit the caller needs and cannot otherwise get: the
    two success returns are indistinguishable from the outside — both hand back the
    same rewritten columns — but one moved 0.5 GB and the other moved nothing."""
    fx = build_tiles(tmp_path)
    publish(fx, tmp_path, monkeypatch)
    idx, cols = read_index(fx)
    dst = tmp_path / "scratch" / f"{fx.label}__{fx.tag}"

    r1 = {}
    assert staging._stage_from_bundle(fx.src, dst, idx, cols, KINDS, fx.label,
                                      tar_dir=tmp_path / "bundles",
                                      report=r1) is not None
    assert r1 == {"copied": True}

    r2 = {}
    assert staging._stage_from_bundle(fx.src, dst, idx, cols, KINDS, fx.label,
                                      tar_dir=tmp_path / "bundles",
                                      report=r2) is not None
    assert r2 == {"copied": False}, "the reuse hit claimed it copied the set"


def _drive_index(tmp_path, label="2017k", n=6):
    """An index whose paths are the baked /content/drive strings staging keys on."""
    root = f"/content/drive/MyDrive/treedata/phase4/tiles/{label}__pilot"
    rows = []
    for i in range(n):
        split = ("train", "val", "test")[i % 3]
        name = f"t{i:04d}.tif"
        rows.append({"tile_name": name, "split": split,
                     "img_path": f"{root}/{split}/images/{name}",
                     "mask_path": f"{root}/{split}/masks/{name}"})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("copied,want_event", [(True, True), (False, False)])
def test_the_stage_tiles_event_is_published_only_when_bytes_moved(
        tmp_path, monkeypatch, capsys, copied, want_event):
    """THE MEASUREMENT APPARATUS, protected from the change it is measuring.

    CLAUDE.md 3.4c makes a live "⏱ stage tiles {label}" — read against the pilot's
    228.2 s — the acceptance gate for the bundle, and the event name was deliberately
    kept identical so the comparison is like-for-like. That makes a FABRICATED event
    of that name the one defect that could pass the gate on its own: a train+evaluate
    pair on one VM would log a real duration and then a 0.0 s reuse hit, and a scorer
    reading the second row (or harvest_timing_events.py averaging the series) sees a
    ~228x win that never happened. Today's staging in that same situation emits
    NOTHING — the legacy tick/tock sit inside `if todo:` — so the reuse path must too.
    """
    idx = _drive_index(tmp_path)
    cols = ["img_path", "mask_path"]
    label = "2017k"

    def stub(src_root, dst_root, idx_df, cols_, kinds, lbl, tar_dir=None, report=None):
        if report is not None:
            report["copied"] = copied
        return {c: [str(Path(dst_root) / r["split"] / KINDS[c] / r["tile_name"])
                    for _, r in idx_df.iterrows()] for c in cols_}

    monkeypatch.setattr(staging, "_bundle_enabled", lambda: True)
    monkeypatch.setattr(staging, "_stage_from_bundle", stub)
    monkeypatch.setattr(staging, "LOCAL_SCRATCH", tmp_path / "scratch")
    monkeypatch.setattr(staging.config, "RUN_TAG", "pilot", raising=False)
    common._timers.pop(f"stage tiles {label}", None)

    out = staging._stage_tiles_local(idx, label)
    assert list(out["img_path"]) != list(idx["img_path"]), "paths were not rewritten"
    assert all(str(p).startswith(str(tmp_path)) for p in out["img_path"])

    saw = "⏱ stage tiles" in capsys.readouterr().out
    assert saw is want_event, (
        f"copied={copied} emitted the timing event: {saw} (wanted {want_event}) — a "
        f"no-copy reuse must not put a ~0 s row under the name the live validation "
        f"of this change is read from")
    # untick, not a leaked timer: an unclosed one is reported by common.timer_summary
    # and would look like a crashed step.
    assert f"stage tiles {label}" not in common._timers


# ══ the bounded read ═════════════════════════════════════════════════════════
#
# WHY THE READ IS BOUNDED AT ALL. `experiments/bundle_validation_2017k.yaml` R1 FAIL:
# the live A100 spent 119.2 s reading the 512,112,640 B tar (4.30 MB/s) with ≥86 s of
# ZERO traffic on every channel, and the read was a bare `shutil.copyfile` with no
# timeout, no throughput floor and no slow-path escape — unbounded, where the rclone
# transport it replaces carries rclone's own retries. The follow-up probe
# (`phase4/qc/probe_bundle_read_20260908T052818Z.txt`) then read the SAME object at
# 48.3 MB/s hours later (PASS A) and hit a 33.3 s stall on a re-read minutes after that
# (PASS B). So stalls on this mount are INTERMITTENT and can hit any single read: the
# gate has to tolerate the 33.3 s one and refuse the ≥86 s one.
#
# WHAT THE GATES CANNOT DO, stated because a gate believed to do more than it does is
# worse than none: both checks run at CHUNK BOUNDARIES. A read blocked inside one
# chunk is not interrupted, so on the measured failure the abort lands at ~101 s and
# the rclone fallback then costs its own ~228 s — SLOWER than the 119.2 s it replaced.
# The bound buys protection against the stall that never returns.
#
# HOW THESE TESTS DRIVE IT. `staging._now` is monkeypatched with `_Clock`, so a 90 s
# stall costs no wall time. The fixtures are KB-scale, so the tests that exercise the
# BUDGET scale `FLOOR_MBPS`/`MIN_BUDGET_S` to the fixture and the SHIPPED constants are
# pinned separately, by arithmetic, against the five measured numbers above.


class _Clock:
    """`staging._now` driven by a script instead of by the wall clock.

    `_bounded_copy` calls `_now()` once before the copy and once after each chunk read,
    so call k ≥ 1 is the END of chunk k. `per_chunk` is the default advance; `script`
    maps a 1-based chunk index to its own.
    """

    def __init__(self, per_chunk=0.0, script=None):
        self.per_chunk, self.script = per_chunk, dict(script or {})
        self.t, self.n = 0.0, 0

    def __call__(self):
        if self.n:
            self.t += self.script.get(self.n, self.per_chunk)
        self.n += 1
        return self.t


def _n_chunks(nbytes, chunk):
    """Chunk reads `_bounded_copy` makes for a file this size: the data chunks plus the
    final empty read that ends the loop."""
    return -(-nbytes // chunk) + 1


def _scale_budget_to(fx, tsid, monkeypatch, seconds, chunk=512):
    """Make this fixture's tar have a `seconds`-long budget, and return its chunk count.

    The size term for a ~10 KB fixture is ~1 ms, so `MIN_BUDGET_S` would otherwise be
    the only thing in play and the FLOOR would never be what the test exercises.
    """
    size = tar_path(fx, tsid).stat().st_size
    monkeypatch.setattr(staging, "MIN_BUDGET_S", 0.0)
    monkeypatch.setattr(staging, "FLOOR_MBPS", (size / 1e6) / seconds)
    monkeypatch.setattr(staging, "_BUNDLE_READ_CHUNK", chunk)
    return _n_chunks(size, chunk)


# The five measured numbers the shipped constants are chosen against. Each names its
# tracked file; none is a preference.
MEASURED_TAR_BYTES = 512112640          # sidecar tar_size (probe log, INPUTS block)
MEASURED_FAIL_S = 119.2                 # timing_events.csv `bundle copy 2017k`
MEASURED_PROBE_S = 10.6                 # probe PASS A, same object, fresh runtime
MEASURED_OK_STALL_S = 33.3              # probe PASS B, one chunk at 120 MiB
MEASURED_BAD_STALL_S = 86.0             # yaml R1 / hw_spdvg.csv zero-traffic window
MEASURED_HEALTHY_DIP_S = 3.0            # probe PASS A longest zero-growth run
# Every one of those is a frozen property of ONE run and cannot move. The p10 the floor
# is picked under is NOT — it is a population statistic that shifts with each harvest
# (n=82 at the verdict, 94 today) — so it is re-derived below rather than pinned here.


def _stage_rates_in_the_bundle_size_class():
    """`mb_per_s` of every `stage` event moving 0.10–0.33 GB, from the tracked CSV.

    THE BAND IS THE ONE THAT REPRODUCES. `experiments/bundle_validation_2017k.yaml`
    reports these as the "0.01–0.33 GB" figures (n=82, p10 7.5, median 48.0); on
    today's CSV the 0.01 lower bound gives p10 2.63 and the 0.10 bound gives 7.50 /
    median 48.8, so 0.10 is what the verdict's numbers were computed over. Not fixed
    in the yaml — that file is a decided experiment record, not this change's to edit.
    """
    csv_path = (Path(__file__).resolve().parents[2] / "phase4" / "qc"
                / "timing_events.csv")
    if not csv_path.exists():
        pytest.skip("timing_events.csv is harvested from the lake; absent here")
    rates = []
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("label") or "").startswith("stage "):
                continue
            try:
                if 0.10e9 <= int(row["bytes"]) <= 0.33e9:
                    rates.append(float(row["mb_per_s"]))
            except (TypeError, ValueError, KeyError):
                continue
    return sorted(rates)


def test_the_floor_stays_below_the_p10_of_the_population_it_was_drawn_from():
    """THE ONE CONSTANT WHOSE BASIS MOVES, so it is READ and not restated (CLAUDE.md
    §2.2). FLOOR_MBPS was set at p5.3 of this population. If a re-harvest drags the
    p10 under 6.0 MB/s this fires — and the correct response is to revisit the
    constant, not the test: a floor above its own population's p10 refuses one read in
    ten that today's unbounded path completes."""
    rates = _stage_rates_in_the_bundle_size_class()
    assert len(rates) >= 50, f"population too small to speak for a p10: n={len(rates)}"
    p10 = rates[max(0, int(0.10 * (len(rates) - 1)))]
    assert staging.FLOOR_MBPS < p10, (
        f"FLOOR_MBPS={staging.FLOOR_MBPS} is at or above the p10 ({p10:.2f} MB/s, "
        f"n={len(rates)}) of the 0.10–0.33 GB `stage` population it was drawn from")
    # and the budget it gives the live tar still sits between the p10 pace and the
    # 119.2 s that failed — the interval the constant was chosen to land in.
    budget = staging._bundle_budget_s(MEASURED_TAR_BYTES)
    assert MEASURED_TAR_BYTES / 1e6 / p10 < budget < MEASURED_FAIL_S


def test_the_shipped_constants_trip_the_measured_failure_and_pass_the_measured_normals():
    """THE CONSTANTS GATE, and it touches no disk on purpose.

    Every other test here scales the constants to a KB fixture. This one asserts the
    values that actually ship, against the five numbers in the tracked files, at the
    one size the archive has measured this object at.
    """
    budget = staging._bundle_budget_s(MEASURED_TAR_BYTES)
    mb = MEASURED_TAR_BYTES / 1e6

    # (a) the throughput floor: the measured failure trips, both measured normals pass.
    assert MEASURED_FAIL_S > budget, (
        f"the validation's own 119.2 s bundle copy ({mb / MEASURED_FAIL_S:.2f} MB/s) "
        f"does not trip a {budget:.1f}s budget — the gate has never fired")
    assert MEASURED_PROBE_S < budget, "the probe's 48.3 MB/s read would be refused"
    # The p10 half of the floor's basis moves with each harvest and is asserted against
    # the tracked CSV in test_the_floor_stays_below_the_p10_of_the_population_*.

    # (b) the stall ceiling brackets the two measured stalls, one of each kind.
    assert MEASURED_OK_STALL_S < staging.MAX_STALL_S <= MEASURED_BAD_STALL_S
    # and one tolerated stall inside an otherwise probe-speed read stays in budget, or
    # gate (a) would fire on the case gate (b) is written to allow.
    assert MEASURED_PROBE_S + MEASURED_OK_STALL_S < budget

    # (c) the LOGGING threshold: silent on the healthy read's VFS-boundary dip, loud on
    # the stall that matters.
    assert MEASURED_HEALTHY_DIP_S < staging.STALL_S < MEASURED_OK_STALL_S


def test_a_healthy_bounded_read_stages_the_set_with_one_tick_and_no_stall_line(
        tmp_path, monkeypatch, capsys):
    """(i) The normal case: every byte arrives, one `⏱ bundle copy` row, no stall row,
    no refusal, and nothing left in the scratch tar dir."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    monkeypatch.setattr(staging, "_BUNDLE_READ_CHUNK", 512)
    monkeypatch.setattr(staging, "_now", _Clock(per_chunk=0.05))
    capsys.readouterr()

    new_cols, dst = stage(fx, tmp_path)
    assert new_cols is not None
    idx, cols = read_index(fx)
    for old, new in zip(idx["img_path"], new_cols["img_path"]):
        assert Path(new).read_bytes() == Path(old).read_bytes()

    out = capsys.readouterr().out
    assert out.count("⏱ bundle copy") == 1, "the whole copy must publish ONE row"
    assert "bundle stall" not in out
    assert "tile bundle not used" not in out
    assert not list((tmp_path / "bundles").iterdir()), "scratch tar dir not cleaned"


def test_a_read_at_half_the_floor_rate_aborts_and_hands_the_fallback_an_empty_tree(
        tmp_path, monkeypatch, capsys):
    """(ii) The floor fires, and (v) the partial `.part` is gone.

    "The fallback is invoked" is proved the way every other refusal test here proves
    it — by the None return, which IS the ladder contract, plus the `_bundle_refuse`
    line naming the rclone path. The caller-side half is a source pin
    (`test_an_unexpected_bundle_error_falls_through_to_the_rclone_path`); rclone itself
    does not run on Windows QC.
    """
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    n = _scale_budget_to(fx, tsid, monkeypatch, seconds=4.0)
    # exactly half the floor rate: the whole tar in 8.0 s against a 4.0 s budget,
    # spread evenly so no single chunk is anywhere near MAX_STALL_S.
    monkeypatch.setattr(staging, "_now", _Clock(per_chunk=8.0 / n))
    capsys.readouterr()

    out, dst = stage(fx, tmp_path)
    assert out is None
    text = capsys.readouterr().out
    assert "tile bundle not used" in text and "staging takes the rclone path" in text
    assert "MB/s floor" in text and "budget" in text, \
        f"the refusal must name the rate and the budget: {text!r}"
    assert_nothing_staged(dst)
    assert not list((tmp_path / "bundles").iterdir()), \
        "the partial read survived in the scratch tar dir"


def test_the_partial_is_released_on_abort_and_never_reaches_the_canonical_name(
        tmp_path, monkeypatch, capsys):
    """(v), proved rather than inferred. A partial read must never be published under
    the name step 9 hashes: `os.replace` is the only publish, and an aborted read must
    not reach it."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    n = _scale_budget_to(fx, tsid, monkeypatch, seconds=4.0)
    monkeypatch.setattr(staging, "_now", _Clock(per_chunk=8.0 / n))
    monkeypatch.setattr(staging.os, "replace", lambda *a, **k: pytest.fail(
        "an aborted read was published under the canonical local tar name"))

    out, dst = stage(fx, tmp_path)
    assert out is None
    assert not list((tmp_path / "bundles").glob("*.part*"))
    assert not list((tmp_path / "bundles").glob("*.tar"))


def test_one_33s_stall_inside_a_full_speed_read_is_tolerated(tmp_path, monkeypatch,
                                                             capsys):
    """(iii) THE MEASURED NORMAL CASE, reproduced at fixture scale: probe PASS B's one
    33.3 s stall inside a read that is otherwise PASS A's 10.6 s, against PASS A's own
    85.4 s budget. It must stage, and it must SAY it stalled."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    n = _scale_budget_to(fx, tsid, monkeypatch, seconds=85.4)
    monkeypatch.setattr(staging, "_now",
                        _Clock(per_chunk=MEASURED_PROBE_S / n,
                               script={n // 2: MEASURED_OK_STALL_S}))
    capsys.readouterr()

    out, dst = stage(fx, tmp_path)
    assert out is not None, (
        "the intermittent stall the probe measured on a read that FINISHED was "
        "refused — the ceiling is below the measured normal case")
    text = capsys.readouterr().out
    assert text.count("⏱ bundle stall") == 1
    assert text.count("⏱ bundle copy") == 1
    assert "tile bundle not used" not in text


def test_a_stall_over_the_ceiling_aborts_with_the_budget_untouched(tmp_path,
                                                                   monkeypatch, capsys):
    """(iv) Gate (b) alone. The budget is set far out of reach, so only the stall
    ceiling can produce this refusal — the two gates are independently live."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    monkeypatch.setattr(staging, "MIN_BUDGET_S", 1000.0)
    monkeypatch.setattr(staging, "_BUNDLE_READ_CHUNK", 512)
    n = _n_chunks(tar_path(fx, tsid).stat().st_size, 512)
    monkeypatch.setattr(staging, "_now",
                        _Clock(per_chunk=0.05, script={n // 2: 90.0}))
    capsys.readouterr()

    out, dst = stage(fx, tmp_path)
    assert out is None
    text = capsys.readouterr().out
    assert "stalled 90.0s" in text and "ceiling" in text, text
    assert "floor" not in text, "the budget fired too — this test proves nothing"
    assert_nothing_staged(dst)
    assert not list((tmp_path / "bundles").iterdir())


def test_the_budget_does_not_abort_after_the_last_byte_has_arrived(tmp_path,
                                                                   monkeypatch, capsys):
    """THE BOUNDARY THAT WOULD HAVE COST THE MOST. A read that crosses the budget on
    its FINAL chunk has the whole tar on local disk; deleting it to re-fetch the same
    bytes over rclone (~228 s on the pilot) is pure loss. `done < size` is what stops
    that, and a gate is only a gate once its boundary is pinned."""
    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    n = _scale_budget_to(fx, tsid, monkeypatch, seconds=4.0)
    # every chunk but the last inside the budget; the last one lands at ~5.0 s.
    monkeypatch.setattr(staging, "_now",
                        _Clock(per_chunk=3.0 / (n - 1), script={n - 1: 2.0}))
    capsys.readouterr()

    out, dst = stage(fx, tmp_path)
    assert out is not None, (
        "the budget fired after every byte was already local — the fallback now "
        "re-downloads a tar that was sitting on NVMe")
    assert "tile bundle not used" not in capsys.readouterr().out


def test_the_bundle_timing_labels_parse_with_the_harvesters_own_regex(tmp_path,
                                                                      monkeypatch,
                                                                      capsys):
    """(vi) A row nobody can harvest is a print statement. Parsed with the SHIPPED
    regex, imported — not restated — so a change to either side fails here.

    The offset lives in the LABEL (`bundle stall 2017k@0.0MiB`) and not after the
    seconds because `_EVENT` anchors on the line ENDING in `<N>s`; trailing text would
    silently drop the row.
    """
    from instruments.harvest_timing_events import _EVENT

    fx = build_tiles(tmp_path)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    n = _scale_budget_to(fx, tsid, monkeypatch, seconds=85.4)
    monkeypatch.setattr(staging, "_now",
                        _Clock(per_chunk=MEASURED_PROBE_S / n,
                               script={n // 2: MEASURED_OK_STALL_S}))
    capsys.readouterr()
    assert stage(fx, tmp_path)[0] is not None

    events = {}
    for line in capsys.readouterr().out.splitlines():
        m = _EVENT.search(line)
        if m:
            events[m.group(1).strip()] = float(m.group(2))
    assert f"bundle copy {fx.label}" in events, \
        f"harvest_timing_events._EVENT did not parse the copy row: {events}"
    stalls = [k for k in events if k.startswith(f"bundle stall {fx.label}@")]
    assert len(stalls) == 1, f"expected one stall row, got {sorted(events)}"
    assert stalls[0].endswith("MiB"), "the offset is not in the label"
    assert events[stalls[0]] == pytest.approx(MEASURED_OK_STALL_S, abs=0.05)
    # and it must NOT be joined to a file size: `size_for` only sizes stage/copy labels
    from instruments.harvest_timing_events import size_for
    assert size_for(stalls[0], {"2017k": 1}) is None


# ══ the flag ══════════════════════════════════════════════════════════════════

def _imported_flag(env_value):
    """`_BUNDLE_ENABLED` as a FRESH interpreter binds it, under a chosen environment.

    A subprocess, not an ambient read: the constant is bound at import of
    phase4seg.staging (see its module body), so `assert staging._BUNDLE_ENABLED is
    False` in this process asserted a property of the SHELL, not of the code — and
    went red in the one shell that matters, the one where someone had exported
    PHASE4SEG_TILE_BUNDLE=1 to turn the path on. `qc/check.py` is the definition of
    done; it must not fail on the switch it is meant to be pinning.
    """
    env = os.environ.copy()                    # full copy: Windows needs SYSTEMROOT
    env.pop("PHASE4SEG_TILE_BUNDLE", None)
    if env_value is not None:
        env["PHASE4SEG_TILE_BUNDLE"] = env_value
    env["PYTHONUTF8"] = "1"
    r = subprocess.run(
        [sys.executable, "-c",
         "from phase4seg.staging import _BUNDLE_ENABLED; print(_BUNDLE_ENABLED)"],
        capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, f"import failed: {r.stderr[-400:]}"
    return r.stdout.strip().splitlines()[-1]


def test_the_bundle_is_off_by_default_and_both_call_sites_are_gated(monkeypatch):
    # THE DEFAULT, as a derivation from the environment rather than as whatever this
    # shell happens to hold. Unset and every non-"1" value must be off; only the
    # documented switch turns it on.
    assert _imported_flag(None) == "False", \
        "PHASE4SEG_TILE_BUNDLE must default off — a live campaign runs this branch"
    assert _imported_flag("") == "False"
    assert _imported_flag("0") == "False"
    assert _imported_flag("true") == "False", "only the exact string '1' arms it"
    assert _imported_flag("1") == "True", "the documented switch does not arm it"

    # and the gate function tracks the constant in BOTH directions, without reading
    # its ambient value.
    monkeypatch.setattr(staging, "_BUNDLE_ENABLED", False)
    assert staging._bundle_enabled() is False
    monkeypatch.setattr(staging, "_BUNDLE_ENABLED", True)
    assert staging._bundle_enabled() is True

    stg = (SCRIPTS / "pipeline" / "phase4seg" / "staging.py").read_text(encoding="utf-8")
    reader = stg[stg.index("def _stage_tiles_local("):]
    assert reader.index("_bundle_enabled()") < reader.index("_stage_from_bundle(")
    tl = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    writer = tl[tl.index("def step_tile("):]
    assert writer.index("_bundle_enabled()") < writer.index("_publish_bundle(")


def test_an_unexpected_bundle_error_falls_through_to_the_rclone_path():
    """Source pin. An exception inside `_stage_from_bundle` must be caught AT the
    bundle call, not by `_stage_tiles_local`'s outer handler — that one returns the
    original index, which hands training the Drive paths and re-reads every tile
    every epoch. The whole point of P4.2 was to stop doing that."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "staging.py").read_text(encoding="utf-8")
    fn = src[src.index("def _stage_tiles_local("):]
    block = fn[fn.index("_stage_from_bundle("):fn.index("new_cols = {c: [] for c in cols}")]
    assert "except Exception" in block
    assert "untick(" in block, "a refused attempt must not emit a second timing event"


def test_the_fallback_rclone_never_downloads_the_bundle():
    """Without this the bundle's own sweep — which guarantees fallbacks during any
    re-tile — would make every fallback download the 0.5 GB tar on top of the tiles
    it actually needs, roughly doubling the transfer it fell back to."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "staging.py").read_text(encoding="utf-8")
    fn = src[src.index("def _bulk_stage_tiles("):src.index("def _stage_tiles_local(")]
    assert '"--exclude", "_bundle_*"' in fn
    # the completeness check must still be computed from `todo`, not a dir listing
    assert "missing = [d for _s, d in todo" in fn


# ══ non-interference ══════════════════════════════════════════════════════════

def _harvest_module():
    p = SCRIPTS / "qc" / "instruments" / "harvest_tilesets.py"
    spec = importlib.util.spec_from_file_location("_harvest_tilesets", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_harvest_tilesets_is_immune_to_bundle_files(tmp_path, monkeypatch):
    """Source-verified (it iterates DIRECTORIES then globs `tile_index_*.csv` /
    `tile_index_*.meta.json`, neither of which `_bundle_*` matches), pinned here so a
    future glob change cannot silently fold bundles into the tracked registry."""
    h = _harvest_module()
    fx = build_tiles(tmp_path)
    tiles_root = fx.src.parent

    before, _, _ = h.harvest(tiles_root, tmp_path / "o1", tmp_path / "l1",
                             dry_run=True)
    publish(fx, tmp_path, monkeypatch)
    assert list(fx.src.glob("_bundle_*")), "fixture published no bundle"
    after, _, _ = h.harvest(tiles_root, tmp_path / "o2", tmp_path / "l2",
                            dry_run=True)

    assert before == after
    assert [r["tileset_id"] for r in after] == [tiling.tileset_id_from_meta(fx.meta_path)]


def test_tileset_id_wrapper_is_a_pure_move(tmp_path, monkeypatch):
    """`tileset_id(label)` must stay exactly `tileset_id_from_meta(_meta_path(label))`
    — one home for the hash, so the engine, the bundle and
    harvest_tilesets.py::tileset_id can never disagree about what an ID is."""
    fx = build_tiles(tmp_path)
    monkeypatch.setattr(tiling, "_meta_path", lambda label: fx.meta_path)
    assert tiling.tileset_id(fx.label) == tiling.tileset_id_from_meta(fx.meta_path)

    # and it agrees with the harvest's dict-taking variant, which is the tracked
    # registry's definition (test_run_context pins that pair independently).
    h = _harvest_module()
    from phase4seg.config import META_NONSIG_KEYS
    tsid, _ = h.tileset_id(json.loads(fx.meta_path.read_text()), META_NONSIG_KEYS)
    assert tsid == tiling.tileset_id_from_meta(fx.meta_path)

    monkeypatch.setattr(tiling, "_meta_path", lambda label: tmp_path / "nope.json")
    assert tiling.tileset_id(fx.label) is None


def test_no_signature_key_was_added(tmp_path):
    """The bundle must invalidate nothing. `qc/test_tile_signature_scope.py` is the
    authority; this is the cheap local restatement of its consequence."""
    fx = build_tiles(tmp_path)
    before = tiling.tileset_id_from_meta(fx.meta_path)
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    sig = src[src.index("def _tile_signature("):src.index("def _meta_path(")]
    assert "bundle" not in sig.lower()
    assert before == tiling.tileset_id_from_meta(fx.meta_path)


def test_the_tar_is_uncompressed_and_costs_about_a_fifth_of_a_percent(tmp_path,
                                                                      monkeypatch):
    """Justified from source, not preference: tiling writes every tile with
    `compress: "lzw"`, so the payload is already entropy-coded and zstd would buy
    single-digit percent on a transfer that is seconds — while `zstandard` is not in
    requirements-colab.txt. Headers cost ~768 B/member."""
    fx = build_tiles(tmp_path, n=30)
    tsid, _ = publish(fx, tmp_path, monkeypatch)
    sc = json.loads(sidecar_path(fx, tsid).read_text())
    payload = sum(e["size"] for e in sc["files"])
    n = len(sc["files"])
    overhead = sc["tar_size"] - payload
    # Structural, not proportional: the fixture's tiles are bytes, a real one's are
    # ~400 KB. Per member tar costs one 512 B header plus 512 B block padding, and
    # the archive ends with a 10240 B trailer. On the live set (1264 tiles, 0.51 GB)
    # that is ~+0.2%; the MEASURED figure is reported separately, not asserted here.
    assert 0 < overhead <= 1024 * n + 10240 + 1024
    with tarfile.open(tar_path(fx, tsid), "r:") as tf:      # r: = uncompressed only
        assert len(tf.getmembers()) == len(sc["files"])

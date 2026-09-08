"""staging.py — bulk tile staging from the Drive mount to local disk.

Split out of core.py 2026-09-01 (plan item 1 / 3.5 continuation — the losses.py
precedent). core.py re-exports every name here with a facade import, so call sites
and test monkeypatches that reach them as core.X keep working unchanged. Torch-free
by design: this cluster never touches the names _ensure_torch injects.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path, PurePosixPath

from phase4seg import config
from phase4seg import scratchcache
from phase4seg.config import LOCAL_SCRATCH
from phase4seg.common import (_sha256, _StagingLock, STAGE_LOCK_MIN_BYTES,
                              tick, tock, untick)

_STAGE_RCLONE_REMOTE = "treedata-user"     # gen_vm_bootstrap.py's WRITER remote
_STAGE_MOUNT_PREFIX  = "/content/drive/MyDrive/treedata/"
_stage_rclone_probe = None

# ══════════════════════════════════════════════════════════════════════════════
#  TILE BUNDLE — one sequential file in place of N Drive API round-trips
# ══════════════════════════════════════════════════════════════════════════════
#  MEASURED, live pilot 2026-09-07 22:44Z (A100 train step log): "bulk-staged 1264
#  tiles via rclone", "⏱ stage tiles 2017k: 228.2s", "1264 files copied (0.51 GB)"
#  → 2.2 MB/s, ~5.5 files/s, with net rx ≈ 0, disk ≈ 0, CPU 1-4%, iowait 0. The
#  process was waiting on PER-FILE API LATENCY, not moving bytes. One big sequential
#  file moves at ~40 MB/s on this mount (Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07
#  §1), so the same 0.51 GB as ONE file should take ~13 s. That arithmetic is an
#  EXTRAPOLATION from two tracked measurements and is UNVALIDATED until a live run
#  measures the bundle path itself (CLAUDE.md 3.4c).
#
#  THE ONE INVARIANT EVERYTHING FOLLOWS FROM: the per-file tile directory on Drive
#  stays CANONICAL and COMPLETE; the bundle is an ADVISORY TRANSPORT CACHE. Every
#  tile byte still lands individually and is verified server-side by
#  tiling.py::_bulk_upload_tiles. Nothing is ever readable only from a bundle. A
#  bundle that is absent, stale, mismatched, truncated or unreadable is not an
#  error — it is a cheaper path not taken, and the ladder falls back:
#
#      bundle  →  rclone bulk dir copy (_bulk_stage_tiles)  →  per-file copy2
#
#  PLAIN TAR, NOT tar.zst: tiling.py writes every tile `compress: "lzw"`, so the
#  payload is already entropy-coded; `zstandard` is not in requirements-colab.txt and
#  `compression.zstd` is 3.14 stdlib. A new dependency to shave seconds off a
#  non-bottleneck is not worth it. Tar headers cost ~768 B/member ≈ +0.2% at 1264.
#
#  OFF BY DEFAULT. A live Colab campaign runs tiling.py from this branch; with the
#  flag off the writer is a no-op and the reader falls through, so the campaign is
#  byte-for-byte unaffected until someone exports PHASE4SEG_TILE_BUNDLE=1.
#  (The bundle SWEEP in tiling.py is deliberately NOT gated — see its comment.)
_BUNDLE_ENABLED  = os.environ.get("PHASE4SEG_TILE_BUNDLE", "") == "1"
_BUNDLE_PREFIX   = "_bundle_"
_BUNDLE_SPLITS   = ("train", "val", "test")
_BUNDLE_KINDS    = ("images", "masks", "heights")
_BUNDLE_CHUNK    = 1 << 20

# ── THE BOUNDED READ (2026-09-08) ─────────────────────────────────────────────
#  Step 8 below used to be a bare `shutil.copyfile(src_root / tar_name, local_tar)`
#  over the mount: no timeout, no throughput floor, no slow-path escape. The transport
#  it replaces — `_bulk_stage_tiles`'s `rclone copy … --transfers 16 --checkers 16
#  --checksum` — carries rclone's own retries, so the bundle path's worst case was
#  UNBOUNDED where the rung below it is not. Named as a design gap by the validation's
#  own referee: experiments/bundle_validation_2017k.yaml, verdict R1.
#
#  WHAT IT CANNOT DO, said plainly. The checks below run at CHUNK BOUNDARIES, because
#  a blocking read() on a FUSE mount cannot be interrupted without a watchdog thread.
#  A read that blocks forever still blocks forever inside one chunk. What this bounds
#  is how much MORE time the path spends after a stall returns, and — on the measured
#  failure — it does not make that case faster: the validation's ≥86 s stall would be
#  seen at ~101 s and the rclone fallback then costs its own ~228 s (pilot). The bound
#  buys protection against the stall that never ends, not a saving on the one measured.
#
#  EVERY RATE BELOW IS bytes/1e6/seconds — the unit of phase4/qc/timing_events.csv's
#  `mb_per_s` column, so the floor and the distribution it is drawn from are one unit.
#
#    4.30 MB/s  THE FAILURE. timing_events.csv `bundle copy 2017k` = 119.2 s over the
#               sidecar's 512,112,640 B tar (run_tag spdv_2017k). MUST trip.
#    7.50 MB/s  p10 of the comparable population: `stage` events moving 0.10–0.33 GB
#               in timing_events.csv (n=94, median 48.8, 17 below 10 MB/s). MUST NOT
#               trip. NOTE: the yaml verdict quotes these figures as the "0.01–0.33 GB"
#               band (n=82, p10 7.5, median 48.0). On today's CSV the 0.01 lower bound
#               does NOT reproduce them (p10 2.63) and 0.10 does, so the band that
#               reproduces is the one named here; the yaml is not this file's to edit.
#   48.31 MB/s  the SAME object read again hours later on a fresh runtime —
#               phase4/qc/probe_bundle_read_20260908T052818Z.txt PASS A, 10.6 s.
#               MUST NOT trip.
#
#  6.0 is the only round number inside (4.30, 7.50). It sits at p5.3 of that population
#  (5 of 94 below), so ~95% of measured reads of this size class clear it, and it gives
#  the live 512 MB tar an 85.4 s budget — above the 68.3 s a p10 read takes, below the
#  119.2 s that failed.
FLOOR_MBPS = 6.0

#  MAX_STALL_S brackets two MEASURED stalls, one of each kind:
#    33.3 s  probe PASS B — one chunk at offset 120 MiB on a re-read of the SAME file
#            that had just read clean minutes earlier. Intermittent, and the read still
#            finished. MUST NOT abort on its own.
#    ≥86 s   the validation A100's zero-traffic window (yaml verdict R1, from
#            hw_spdvg.csv: net rx ~0 on every channel, iowait pinned at 8.4% = one of
#            twelve vCPUs in D-state). SHOULD abort.
#  60 s is the midpoint of the only interval where those two disagree.
MAX_STALL_S = 60.0

#  STALL_S is a LOGGING threshold, not a gate: any chunk at or above it publishes a
#  `⏱ bundle stall <label>@<MiB>` row, so the next slow read is diagnosable from the
#  harvested series instead of from a live hardware trace. Why 10 and not the probe's
#  own 2.0 s threshold: at 2 s the HEALTHY PASS A read would have logged its 384 MiB
#  VFS range-boundary dip (2–3 s), and a threshold that fires on the healthy case
#  teaches nothing. 10 s is still well under the 33.3 s stall it must catch.
STALL_S = 10.0

#  Live tile sets are 0.2–0.7 GB, so the size term alone gives them 33–117 s and this
#  floor never binds on Colab. It exists for the KB-scale fixtures in
#  qc/test_tile_bundle.py, whose size term is ~1 ms: without it every existing
#  round-trip test would be racing a budget against the real clock.
MIN_BUDGET_S = 10.0

#  8 MiB — the buffer probe_bundle_read.py measured this mount with (PASS B and C). On
#  the live 488 MiB tar that is 62 chunks, i.e. a budget/stall check about every 0.17 s
#  at the probe's 48 MB/s: fine granularity, and far too few syscalls to matter.
_BUNDLE_READ_CHUNK = 8 << 20


def _now():
    """The bounded read's clock, read through a function for exactly the reason
    `_bundle_enabled` is: qc/test_tile_bundle.py drives a 33.3 s and a 90 s stall, and
    a test that really slept them would cost two minutes."""
    return time.monotonic()


def _bundle_budget_s(nbytes):
    """Wall-clock seconds a mount read of ``nbytes`` is allowed to take."""
    return max(MIN_BUDGET_S, (nbytes or 0) / 1e6 / FLOOR_MBPS)


def _bounded_copy(src, dst, label, size_hint=0):
    """Chunked mount read of ``src`` into ``dst``, floored and stall-capped.

    Returns **None** on success, or the refusal reason. NEVER RAISES, and never leaves
    ``dst`` behind on a non-success return — the caller's next rung is the rclone
    transport, which must inherit nothing partial.

    THE BUDGET IS NOT CHECKED ONCE THE LAST BYTE IS IN. `done < size` guards it, and
    that is not tidiness: without it a read that crosses the budget on its FINAL chunk
    would delete a complete local tar and pay rclone (~228 s on the pilot) to fetch
    back what was already on disk. The budget exists to stop spending MORE time, and
    once every byte has arrived there is none left to spend. With the size unknown
    (fstat failed and the sidecar carried none) the guard cannot apply and the check
    runs unconditionally.
    """
    reason = None
    done = 0
    t0 = prev = _now()
    try:
        # buffering=0 → one raw read per chunk, so `dt` times the MOUNT and not
        # python's buffer-refill schedule. `t0` is taken BEFORE the open on purpose:
        # an open() that blocks is the same failure as a read() that blocks, and it
        # should be caught by the same two gates.
        with open(src, "rb", buffering=0) as fh:
            try:
                size = os.fstat(fh.fileno()).st_size or int(size_hint or 0)
            except OSError:
                size = int(size_hint or 0)
            budget = _bundle_budget_s(size)
            with open(dst, "wb") as out:
                while True:
                    buf = fh.read(_BUNDLE_READ_CHUNK)
                    now = _now()
                    dt, prev = now - prev, now
                    if dt >= STALL_S:
                        # Harvestable by qc/instruments/harvest_timing_events.py::_EVENT
                        # — the offset is in the LABEL, not after the seconds, because
                        # that regex anchors on the line ending in `<N>s`.
                        print(f"  ⏱ bundle stall {label}@{done / (1 << 20):.1f}MiB: "
                              f"{dt:.1f}s")
                    if dt > MAX_STALL_S:
                        reason = (f"one chunk at {done / (1 << 20):.1f} MiB stalled "
                                  f"{dt:.1f}s, over the {MAX_STALL_S:.0f}s ceiling")
                        break
                    if not buf:
                        break
                    out.write(buf)
                    done += len(buf)
                    el = now - t0
                    if el > budget and (not size or done < size):
                        rate = done / 1e6 / el if el > 0 else 0.0
                        reason = (f"read {done / 1e6:.1f} of {size / 1e6:.1f} MB in "
                                  f"{el:.1f}s = {rate:.2f} MB/s, under the "
                                  f"{FLOOR_MBPS:.1f} MB/s floor (budget {budget:.1f}s)")
                        break
    except Exception as e:                             # noqa: BLE001 — never raise
        reason = f"tar copy failed ({type(e).__name__}: {e})"
    if reason:
        try:
            Path(dst).unlink()
        except OSError:
            pass
    return reason


def _bundle_enabled():
    """Module-level gate, read through a function so tests can monkeypatch it."""
    return bool(_BUNDLE_ENABLED)


def _bundle_names(tsid):
    """``(tar, sidecar json, local done-marker)`` names for a tile-set ID."""
    return (f"{_BUNDLE_PREFIX}{tsid}.tar",
            f"{_BUNDLE_PREFIX}{tsid}.json",
            f"{_BUNDLE_PREFIX}{tsid}.done")


def _sha256_file(path):
    """The tar's sha256. A thin alias for `common._sha256` on purpose — it is the
    SAME hash `_copy_to_drive` computes over the SAME file on the write side, and a
    second implementation of it here would be a second home for the one number this
    whole path trusts."""
    return _sha256(path)


def _bundle_rel_ok(rel):
    """True iff ``rel`` is a legal in-bundle tile path: exactly
    ``{train|val|test}/{images|masks|heights}/{name}``, relative, no traversal.

    THE PRIMARY member guard. It does not depend on `tarfile.data_filter` (3.12+,
    and Colab's runtime is not something to infer from a version string) — that is
    probed and applied as a second layer where it exists, never relied on.
    """
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel:
        return False
    parts = PurePosixPath(rel).parts
    if len(parts) != 3:
        return False
    if parts[0] not in _BUNDLE_SPLITS or parts[1] not in _BUNDLE_KINDS:
        return False
    return parts[2] not in ("", ".", "..")


def _bulk_stage_ok(src_root):
    """True iff a bulk `rclone copy` can replace the per-file staging read.

    Deliberately narrow — same activation discipline as tiling.py's bulk WRITE:
    posix, the path really is under the Drive mount, rclone is on PATH, and the
    writer remote exists. Anywhere else (Windows QC, a dry run, a VM without
    rclone) this answers False and the historical per-file loop runs unchanged.
    """
    global _stage_rclone_probe
    if os.name != "posix" or not str(src_root).startswith(_STAGE_MOUNT_PREFIX):
        return False
    if _stage_rclone_probe is None:
        _stage_rclone_probe = False
        try:
            if shutil.which("rclone"):
                r = subprocess.run(["rclone", "listremotes"], capture_output=True,
                                   text=True, timeout=60)
                _stage_rclone_probe = (r.returncode == 0 and
                                       f"{_STAGE_RCLONE_REMOTE}:" in (r.stdout or "").split())
        except Exception:                              # noqa: BLE001 — any failure = no
            _stage_rclone_probe = False
    return _stage_rclone_probe


def _bulk_stage_tiles(src_root, dst_root, todo):
    """One server-side-listed bulk copy of a tile dir. Returns files copied, or 0.

    0 means "did not work, use the per-file loop" — never a silent partial. The
    caller re-copies everything on 0, which is safe because --checksum makes the
    bulk pass idempotent and the per-file pass skips size-matched files.
    """
    rel = str(src_root)[len(_STAGE_MOUNT_PREFIX):].strip("/")
    try:
        dst_root.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            # --exclude "_bundle_*": this copies the WHOLE tile directory, which now
            # may also hold a ~0.5 GB tile bundle (and, briefly, its .part orphans).
            # Downloading it here would roughly DOUBLE the transfer of the very
            # fallback the bundle path failed over into. rclone's `*` does not cross
            # "/", so the pattern matches only the dir-root bundle files and never a
            # tile. Safe against the completeness check below, which is computed from
            # `todo` alone — index-referenced tiles only, never a directory listing.
            ["rclone", "copy", f"{_STAGE_RCLONE_REMOTE}:{rel}", str(dst_root),
             "--transfers", "16", "--checkers", "16", "--checksum",
             "--exclude", "_bundle_*"],
            capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            print(f"  (bulk stage rc={r.returncode}, falling back to per-file: "
                  f"{(r.stderr or '')[-160:]})")
            return 0
        # THE COMPLETENESS CHECK COMPARED INCOMPATIBLE THINGS. `got` counted every
        # .tif already under dst_root, `n_expected` was len(todo) — the number of
        # files found MISSING or size-mismatched. On any resume that is 1800 vs 5,
        # so the guard could not fire, and a bulk copy that silently dropped files
        # returned success. Ask the real question instead: is every file we asked
        # for now here, at the source's size? These are local NVMe stats.
        missing = [d for _s, d in todo
                   if not d.exists() or d.stat().st_size != _s.stat().st_size]
        if missing:
            print(f"  (bulk stage short: {len(missing)} of {len(todo)} requested "
                  f"files absent or wrong size — per-file fallback)")
            return 0
        got = len(todo)
        print(f"  ✓ bulk-staged {got} tiles via rclone (was N FUSE opens)")
        return got
    except Exception as e:                             # noqa: BLE001
        print(f"  (bulk stage raised {type(e).__name__}: {e} — per-file fallback)")
        return 0


@contextlib.contextmanager
def _extract_lock(dst_root):
    """Serialise two SAME-VM processes extracting into one scratch dir. flock on
    posix, a no-op elsewhere (Windows QC never reaches the bundle path live, and the
    tests drive these functions one at a time)."""
    if os.name != "posix":
        yield
        return
    import fcntl
    lp = Path(str(dst_root) + ".lock")
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _bundle_plan(idx_df, dst_root, cols, kinds):
    """``(new column values, ordered in-bundle rel paths)`` for this index.

    THE POINT OF DOING IT HERE: it never stats a source file. Today's staging loop
    stats every tile over FUSE (2528+ stats for a 1264-tile set) just to decide what
    to copy, and that loop sits OUTSIDE tick/tock so it has never been timed. On the
    bundle path it does not run. HONESTLY NAMED CONSEQUENCE: those stats were also
    the only thing incidentally proving Drive still holds each tile at staging time.
    The bundle path no longer proves that; what it proves instead is a sha256 it
    computed itself over the bytes it actually read. Canonical completeness is
    checked where it belongs — tiling.py::_existing_tiles_valid and the queue's
    VERIFY:tile, both unchanged.
    """
    new_cols = {c: [] for c in cols}
    rels = []
    for _, row in idx_df.iterrows():
        for c in cols:
            v = row[c]
            if not (isinstance(v, str) and v):
                new_cols[c].append(v)
                continue
            rel = f"{row['split']}/{kinds[c]}/{row['tile_name']}"
            rels.append(rel)
            new_cols[c].append(str(dst_root / str(row["split"]) / kinds[c]
                                   / str(row["tile_name"])))
    return new_cols, rels


def _bundle_refuse(why, dst_root=None, local_tar=None):
    """One exit for every refusal: say why, leave scratch in a state the fallback can
    safely inherit (untouched, or fully removed), return None."""
    if dst_root is not None:
        shutil.rmtree(dst_root, ignore_errors=True)
    if local_tar is not None:
        try:
            Path(local_tar).unlink()
        except OSError:
            pass
    print(f"  (tile bundle not used: {why} — staging takes the rclone path)")
    return None


def _manifest_on_disk(dst_root, manifest):
    """Every manifest entry present under ``dst_root`` at its recorded size. LOCAL
    NVMe stats — cheap, and the only completeness claim the bundle path makes."""
    for rel, size in manifest.items():
        q = Path(dst_root) / rel
        try:
            if q.stat().st_size != size:
                return False
        except OSError:
            return False
    return True


def _stage_from_bundle(src_root, dst_root, idx_df, cols, kinds, label,
                       tar_dir=None, report=None):
    """Try to stage this tile set from its bundle. Returns the rewritten column
    values on success, or **None** — "refused, run the next rung of the ladder".

    NO MOUNT CHECKS INSIDE, deliberately: `_stage_tiles_local`'s /content/drive gate
    stays where it is, so this whole body is reachable from a tmp_path test on
    Windows. Every numbered step below is a refusal point, and the cheap ones come
    first — nothing costing 0.5 GB happens until steps 1-7 have all passed.

    ``report``, if given, is filled with ``{"copied": bool}`` — True when bytes
    actually moved (step 13), False on the step-7 reuse hit. It is an out-param
    rather than a second return value ON PURPOSE: the None/new_cols contract is what
    every caller reads, and widening it to a tuple would have rewritten every gate
    assertion in qc/test_tile_bundle.py that reads that return, to carry one bit. The
    caller needs that bit to decide whether to publish a timing event at all — see
    `_stage_tiles_local`.
    """
    from phase4seg.tiling import tileset_id_from_meta   # core already imports tiling
    src_root, dst_root = Path(src_root), Path(dst_root)

    # 1-2. The ID comes from the meta BESIDE THE INDEX BEING CONSUMED, never from
    #      whichever _bundle_* files happen to be lying in the directory. A changed
    #      signature therefore makes an old bundle unreachable rather than unlikely.
    want = tileset_id_from_meta(src_root / f"tile_index_{label}.meta.json")
    if not want:
        return _bundle_refuse(f"no tile-set id for {label} (6-site or legacy dir)")
    tar_name, json_name, done_name = _bundle_names(want)

    # 3-4. Sidecar. The recorded id is compared to the one in the FILENAME as well,
    #      which is redundant on purpose: a stale bundle COPIED under a new name
    #      cannot pass both.
    try:
        sidecar = json.loads((src_root / json_name).read_text())
    except Exception as e:                                 # noqa: BLE001
        return _bundle_refuse(f"sidecar {json_name} unreadable ({type(e).__name__})")
    if sidecar.get("tileset_id") != want:
        return _bundle_refuse(f"sidecar records id {sidecar.get('tileset_id')!r}, "
                              f"name says {want!r}")

    # 5. The index bytes ACTUALLY BEING CONSUMED. Hashed from the FILE, not from the
    #    DataFrame — a pandas round-trip does not reproduce the CSV bytes, so hashing
    #    a re-serialised frame would make this guard a no-op.
    index_path = src_root / f"tile_index_{label}.csv"
    try:
        if sidecar.get("index_sha256") != hashlib.sha256(
                index_path.read_bytes()).hexdigest():
            return _bundle_refuse("index_sha256 mismatch (index rewritten under an "
                                  "unchanged signature)")
    except OSError as e:
        return _bundle_refuse(f"index unreadable ({e})")

    # 6. MANIFEST <-> INDEX, the ID-INDEPENDENT guard: a bundle whose id matches is
    #    still refused unless it actually contains this index's tiles. Still before
    #    any bulk copy, so a mismatch costs one small read.
    try:
        manifest = {str(e["rel"]): int(e["size"]) for e in sidecar["files"]}
    except Exception as e:                                 # noqa: BLE001
        return _bundle_refuse(f"sidecar manifest malformed ({type(e).__name__})")
    bad = [r for r in manifest if not _bundle_rel_ok(r)]
    if bad:
        return _bundle_refuse(f"manifest holds {len(bad)} illegal path(s), first "
                              f"{bad[0]!r}")
    new_cols, rels = _bundle_plan(idx_df, dst_root, cols, kinds)
    missing = [r for r in rels if r not in manifest]
    if missing:
        return _bundle_refuse(f"manifest does not cover {len(missing)} index "
                              f"tile(s), first {missing[0]!r}")

    # 7. Local reuse. ANY marker that does not match — a different id, or this id
    #    under a different tar — is RMTREE'd, not extracted over and not merely
    #    unlinked: the fallback's reuse test is exists+size, which cannot tell a stale
    #    same-name same-size tile from the right one, so it must never be handed one.
    dst_root.mkdir(parents=True, exist_ok=True)
    for m in sorted(dst_root.glob(_BUNDLE_PREFIX + "*.done")):
        try:
            rec = json.loads(m.read_text())
        except Exception:                                  # noqa: BLE001
            rec = {}
        if rec.get("tileset_id") != want:
            print(f"  tile bundle: scratch holds a set from id "
                  f"{rec.get('tileset_id')!r}, wanted {want!r} — clearing {dst_root}")
            shutil.rmtree(dst_root, ignore_errors=True)
            dst_root.mkdir(parents=True, exist_ok=True)
            break
    done_path = dst_root / done_name
    if done_path.exists():
        try:
            rec = json.loads(done_path.read_text())
        except Exception:                                  # noqa: BLE001
            rec = {}
        # tar_sha256 IS LOAD-BEARING HERE, not belt-and-braces. Without it the
        # same-id re-tile reaches straight through the local cache: --force-retile
        # rewrites the tiles with different bytes at identical names and sizes, a
        # deterministic re-sample writes a byte-identical index, and the meta is
        # unchanged — so id, index_sha256, n_files and every local size still match
        # the marker the PREVIOUS tiling left, and this branch would return "already
        # staged" having copied nothing and trained on the old bytes. The republished
        # tar always differs (different bytes; and even identical bytes carry fresh
        # mtimes in the GNU headers), so hashing it is what separates the two
        # tilings. The Drive-side half of this hazard is closed by
        # tiling.py::_sweep_bundles; this is the scratch-side half.
        same = (rec.get("tileset_id") == want
                and rec.get("index_sha256") == sidecar.get("index_sha256")
                and rec.get("tar_sha256") == sidecar.get("tar_sha256")
                and rec.get("n_files") == sidecar.get("n_files"))
        if same and _manifest_on_disk(dst_root, manifest):
            print(f"  Tiles already staged from bundle {want}: {len(manifest)} "
                  f"files -> {dst_root} (nothing copied)")
            if report is not None:
                report["copied"] = False
            return new_cols
        # UNLINKING THE MARKER ALONE WAS THE BUG. Reaching here means this function
        # has just PROVED the local tree belongs to a different tiling (or is an
        # incomplete one) — and then steps 8-9 can still refuse, for three reasons
        # the referee named, one of which _publish_bundle's own docstring calls the
        # EXPECTED outcome: the cross-VM async-upload race on a --vfs-cache-mode
        # writes mount (that one), a transient mount EIO during the 0.5 GB read (what
        # common._copy_to_drive already retries for), and a peer's _sweep_bundles
        # unlinking the tar mid-copy. Every one of those refusals handed the rclone
        # fallback the stale tree, whose exists+size
        # test then found every file present at the right size and copied NOTHING —
        # training on the previous tiling's bytes, silently. So clear it here, at the
        # point the knowledge exists, rather than at each refusal site: on the success
        # path extraction was going to overwrite every manifest member anyway (cost:
        # one local delete), and on the refusal path the fallback re-downloads a set
        # it would otherwise have skipped. Pinned by
        # test_a_stale_local_tree_is_cleared_even_when_the_bundle_then_refuses.
        shutil.rmtree(dst_root, ignore_errors=True)
        dst_root.mkdir(parents=True, exist_ok=True)

    # 8. THE WHOLE POINT: one sequential open instead of N. Far under
    #    STAGE_LOCK_MIN_BYTES (4 GiB), so it takes no Drive staging lock — same as
    #    today's tile staging. tick/tock so it lands in the timing events. BOUNDED
    #    since 2026-09-08 (see the THE BOUNDED READ block at the top): a throughput
    #    floor and a stall ceiling, and an abort here is a refusal like any other —
    #    the ladder falls to rclone exactly as an absent bundle would.
    tar_dir = Path(tar_dir) if tar_dir else (LOCAL_SCRATCH / "bundles")
    tar_dir.mkdir(parents=True, exist_ok=True)
    local_tar = tar_dir / f"{dst_root.name}__{want}.tar"
    # THE SCRATCH CACHE COMPETES WITH THIS WRITER FOR THE SAME DISK. Until now the big
    # writers into LOCAL_SCRATCH found room only BECAUSE every step deleted its ortho on
    # exit; with a cache holding those orthos that accident is gone, so ask for the room
    # explicitly. 2x tar_size because the tar and the tree it extracts coexist until the
    # `finally` below unlinks the tar. The answer is ADVISORY and deliberately not
    # gated on: today's path checks free space nowhere at all, and refusing a bundle
    # where today would have copied one would be a regression, not a guard.
    scratchcache.reserve(2 * int(sidecar.get("tar_size") or 0))
    # THE PART FILE, same discipline as common._copy_to_drive's Drive-side write: the
    # canonical local name never exists holding a partial read, and two same-VM
    # processes cannot interleave into one file. Published with os.replace only after
    # the bounded read returns clean.
    part = tar_dir / f"{local_tar.name}.part.{os.getpid()}"
    tick(f"bundle copy {label}")
    why = _bounded_copy(src_root / tar_name, part, label,
                        size_hint=int(sidecar.get("tar_size") or 0))
    # ONE ROW PER COPY, on BOTH outcomes. An aborted read really did spend those
    # seconds and the row is the evidence; what says it is an abort is the refusal line
    # printed immediately after it and the `bundle stall` rows above it. Contrast
    # `stage tiles`, which unticks its no-copy returns — there the hazard is a
    # FABRICATED FAST row under the name the saving is measured from, and a slow row
    # cannot inflate a saving.
    tock(f"bundle copy {label}")
    if why:
        return _bundle_refuse(why, local_tar=part)
    try:
        os.replace(part, local_tar)
    except OSError as e:
        return _bundle_refuse(f"tar publish to scratch failed ({e})", local_tar=part)

    # 9. The ONLY thing that proves the bytes arrived intact. This is also what makes
    #    the write side's "Drive NOT CONFIRMED" tolerable (see _publish_bundle): the
    #    reader never acts on the sidecar's existence, only on a hash it computed
    #    itself over bytes it read.
    got_size = local_tar.stat().st_size
    if got_size != sidecar.get("tar_size"):
        return _bundle_refuse(f"tar size {got_size} != {sidecar.get('tar_size')}",
                              local_tar=local_tar)
    if _sha256_file(local_tar) != sidecar.get("tar_sha256"):
        return _bundle_refuse("tar sha256 mismatch (partial or superseded upload)",
                              local_tar=local_tar)

    # 10-11. Extraction, member by member. `extractall` is NOT used: every member is
    #        allowlisted by _bundle_rel_ok and written to a path this function built
    #        from validated components, so path traversal is unreachable whether or
    #        not this runtime's tarfile has a data filter.
    _has_filter = getattr(tarfile, "data_filter", None) is not None
    err = None
    try:
        with _extract_lock(dst_root), tarfile.open(local_tar, "r") as tf:
            for m in tf:
                if not (m.isfile() and _bundle_rel_ok(m.name)):
                    err = (f"tar member {m.name!r} rejected by the path allowlist"
                           f"{'' if _has_filter else ' (no stdlib data filter here)'}")
                    break
                if m.name not in manifest:
                    err = f"tar member {m.name!r} is not in the manifest"
                    break
                sp, kind, name = PurePosixPath(m.name).parts
                out = dst_root / sp / kind / name
                out.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    err = f"tar member {m.name!r} has no payload"
                    break
                with src, open(out, "wb") as fh:
                    shutil.copyfileobj(src, fh, _BUNDLE_CHUNK)
    except (tarfile.TarError, OSError) as e:
        err = f"extraction failed ({type(e).__name__}: {e})"
    # The refusal happens OUTSIDE the `with`, never inside it. Returning from inside
    # left the tarfile open while _bundle_refuse tried to unlink it, and on Windows
    # that unlink fails silently — the local tar then survived a rejected extraction
    # and doubled scratch. Caught by test_a_tar_member_outside_the_tile_layout_*.
    if err:
        return _bundle_refuse(err, dst_root=dst_root, local_tar=local_tar)
    if not _manifest_on_disk(dst_root, manifest):
        return _bundle_refuse("post-extract size check failed", dst_root=dst_root,
                              local_tar=local_tar)

    # 12-13. The marker is the atomic gate and is written LAST: a death anywhere in
    #        8-11 leaves none, and the next attempt re-extracts or falls back. Then
    #        the tar goes, or scratch carries the set twice.
    done_path.write_text(json.dumps({
        "tileset_id": want, "index_sha256": sidecar.get("index_sha256"),
        "tar_sha256": sidecar.get("tar_sha256"),
        "n_files": sidecar.get("n_files"), "label": str(label)}))
    try:
        local_tar.unlink()
    except OSError:
        pass
    print(f"  OK tiles staged from bundle {want}: {len(manifest)} files "
          f"({sidecar.get('tar_size', 0) / 1e9:.2f} GB, ONE sequential read) "
          f"-> {dst_root}")
    if report is not None:
        report["copied"] = True
    return new_cols


def _publish_bundle(stage_root, out_tile_dir, label, index_path, tsid,
                    run_tag="", tar_dir=None):
    """Build and publish the tile bundle from the VERIFIED local staging tree.

    NEVER RAISES. One try/except that prints and continues — deliberately unlike
    tiling.py::_bulk_upload_fail, which unlinks the meta and raises because the
    CANONICAL store is at stake. Here it is not: the tiles, the index and the meta
    are already on Drive, so a failed bundle leaves a complete, valid, reusable tile
    set that simply stages the slow way.

    WHY common._copy_to_drive AND NOT rclone: it is the repo's sanctioned
    local-then-copy write (CLAUDE.md 3.9). It stages to `<name>.part.{pid}{token}`
    and publishes with os.replace INSIDE the Drive directory, so the canonical name
    never exists truncated and two runtimes cannot collide on the part name; its
    `_sweep_part_orphans` call already clears `_bundle_*.tar.part.*` at 24 h, so no
    new sweeper is needed.

    WHAT IT CANNOT PROVE, plainly: on a --vfs-cache-mode writes mount it writes to
    this VM's cache and the Drive upload is async, so it will often print "staged
    write ... Drive NOT CONFIRMED", and the upload ORDER of tar vs sidecar is not
    guaranteed — a peer VM can see the sidecar before the tar. That is tolerable
    only because the reader gates on a sha256 it computes itself (step 9 there); a
    peer that reads early fails that gate and falls back, costing one partial read.
    """
    from phase4seg.common import _copy_to_drive
    from phase4seg.tiling import _staged_files
    stage_root, out_tile_dir = Path(stage_root), Path(out_tile_dir)
    local_tar = None
    if not tsid:
        print("  (tile bundle not published: no tile-set id — 6-site or no meta)")
        return False
    try:
        files = _staged_files(stage_root)      # {rel posix: size} — IS the manifest
        bad = [r for r in files if not _bundle_rel_ok(r)]
        if bad or not files:
            print(f"  (tile bundle not published: staging root holds {len(files)} "
                  f"file(s), {len(bad)} outside the tile layout)")
            return False
        tar_dir = Path(tar_dir) if tar_dir else (LOCAL_SCRATCH / "bundleout")
        tar_dir.mkdir(parents=True, exist_ok=True)
        tag = f"__{run_tag}" if run_tag else ""
        local_tar = tar_dir / f"{label}{tag}__{tsid}.tar"
        tar_name, json_name, _ = _bundle_names(tsid)
        tick(f"bundle build {label}")
        try:
            # GNU_FORMAT, not the 3.12 default PAX. PAX writes a 1024 B extended
            # header per member purely to carry sub-second mtime — MEASURED here as
            # 2048 B/member instead of 1024, i.e. it would have DOUBLED the tar's
            # overhead (~+0.4% instead of ~+0.2% on a 1264-tile set) to record a
            # timestamp nothing reads. GNU also carries long names, which USTAR
            # would cap at 100 chars.
            with tarfile.open(local_tar, "w", format=tarfile.GNU_FORMAT) as tf:
                for rel in sorted(files):
                    tf.add(stage_root / rel, arcname=rel, recursive=False)
        finally:
            tock(f"bundle build {label}")
        sidecar = {
            "tileset_id": tsid, "label": str(label), "run_tag": str(run_tag or ""),
            "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(
                timespec="seconds"),
            "tar_size": local_tar.stat().st_size,
            "tar_sha256": _sha256_file(local_tar),
            "index_sha256": hashlib.sha256(Path(index_path).read_bytes()).hexdigest(),
            "n_files": len(files),
            "files": [{"rel": r, "size": int(files[r])} for r in sorted(files)],
        }
        _copy_to_drive(local_tar, out_tile_dir / tar_name, checksum=True)
        # Sidecar last and small: a death between the two leaves a .tar with no
        # .json, which is inert (the reader requires the sidecar) and is removed by
        # tiling.py::_sweep_bundles at the next tiling of this directory.
        (out_tile_dir / json_name).write_text(json.dumps(sidecar))
        print(f"  OK tile bundle published: {tar_name} "
              f"({sidecar['tar_size'] / 1e9:.2f} GB, {len(files)} tiles) — advisory "
              f"transport cache; the per-file tile dir stays canonical")
        return True
    except Exception as e:                                 # noqa: BLE001 — never raise
        print(f"  (tile bundle NOT published: {type(e).__name__}: {e}. The tile set "
              f"on Drive is complete and valid; staging takes the rclone path.)")
        return False
    finally:
        if local_tar is not None:
            try:
                local_tar.unlink()
            except OSError:
                pass


def _stage_tiles_local(idx_df, label):
    """P4.2: stage the year's tile set to local NVMe at train start.

    Training used to re-read every tile over the Drive FUSE mount EVERY EPOCH.
    Copy the set once (0.2-0.7 GB measured per year — same pattern as
    _stage_imagery_local), rewrite the index's baked-absolute paths (see
    tiling.py: they are written as /content/drive/... strings), and let the
    epochs read NVMe. Any failure falls back to the original Drive paths, unchanged.
    P11.4: the exists/size pass runs OUTSIDE the staging lock (thousands of FUSE
    stats, nothing copied on a resume); only a >= STAGE_LOCK_MIN_BYTES (1 GiB)
    copy set takes the lock — no existing tile set reaches that, so today this
    copy runs unlocked by design of the floor; tick/tock wrap the copy alone.
    """
    first = str(idx_df.iloc[0]["img_path"]) if len(idx_df) else ""
    if not first.startswith("/content/drive"):
        return idx_df                       # already local (or not on Colab)
    kinds = {"img_path": "images", "mask_path": "masks", "height_path": "heights"}
    cols = [c for c in kinds if c in idx_df.columns]
    # SAME ARM-COLLISION AS THE LAKE-SIDE TILE DIR, one layer down. tile_dir_for()
    # gives each arm its own tiles/{year}__{tag}/ on Drive, but the LOCAL staging
    # copy keyed on the year alone. Two arms on one year, run in sequence on one VM,
    # therefore share tiles/{year}/ on scratch — and the reuse test is exists+size,
    # which two different overlays' tiles pass routinely. The second arm then trains
    # on the first arm's tiles with nothing logged. Mirror the tagged name here.
    _tag = getattr(config, "RUN_TAG", "") or ""
    dst_root = LOCAL_SCRATCH / "tiles" / (f"{label}__{_tag}" if _tag else str(label))
    try:
        # RUNG ONE OF THE LADDER: the tile bundle — ONE sequential read in place of
        # N Drive API round-trips (see the TILE BUNDLE block at the top of this
        # file). Returns None for "refused", having left scratch either untouched or
        # fully removed, so the rclone/per-file chain below inherits nothing partial
        # and behaves byte-for-byte as it does today.
        if _bundle_enabled():
            _src_root = Path(str(idx_df.iloc[0]["img_path"])).parents[2]
            # SAME TIMER LABEL as the rclone path, deliberately: the live validation
            # of this change is "⏱ stage tiles {label}" read against the 228.2 s the
            # pilot measured, and a renamed event would not be comparable. Today's
            # timer wraps the COPY ALONE (the P11.4 note below), and the bundle path
            # has no FUSE stat pass at all, so this figure is if anything
            # conservative — it also contains the sha256 and the extract.
            _report = {}
            tick(f"stage tiles {label}")
            try:
                _from_bundle = _stage_from_bundle(_src_root, dst_root, idx_df, cols,
                                                  kinds, label, report=_report)
            except Exception as e:              # noqa: BLE001 — never abandon staging
                # An UNEXPECTED failure in the new path must fall through to the old
                # one, not out to _stage_tiles_local's outer handler, which would
                # hand training the Drive paths and re-read every tile every epoch.
                print(f"  (tile bundle raised {type(e).__name__}: {e} — "
                      f"staging takes the rclone path)")
                _from_bundle = None
            if _from_bundle is None:
                untick(f"stage tiles {label}")   # refused: the rclone path times itself
            else:
                # THE EVENT IS PUBLISHED ONLY WHEN BYTES MOVED. A step-7 reuse hit
                # copies nothing, and today's staging in that same situation emits no
                # timing event at all (the legacy tick/tock sit inside `if todo:`, and
                # on a reuse `todo` is empty). Emitting "⏱ stage tiles {label}: 0.0s"
                # there would put a fabricated ~0 s row under the EXACT event name
                # this change's live validation is read from — 228.2 s on the pilot —
                # and an independent scorer reading the evaluate leg, or
                # harvest_timing_events.py averaging the series, would see a ~228x win
                # that never happened. untick is the same discipline the refusal path
                # already uses, applied to the other no-copy return.
                if _report.get("copied"):
                    tock(f"stage tiles {label}")
                else:
                    untick(f"stage tiles {label}")
                out = idx_df.copy()
                for c in cols:
                    out[c] = _from_bundle[c]
                return out
        new_cols = {c: [] for c in cols}
        todo, todo_bytes = [], 0
        for _, row in idx_df.iterrows():
            for c in cols:
                p = row[c]
                if not (isinstance(p, str) and p):
                    new_cols[c].append(p)
                    continue
                src = Path(p)
                dst = dst_root / str(row["split"]) / kinds[c] / str(row["tile_name"])
                src_size = src.stat().st_size
                if not dst.exists() or dst.stat().st_size != src_size:
                    todo.append((src, dst))
                    todo_bytes += src_size
                new_cols[c].append(str(dst))
        n_copied = 0
        if todo:
            lock = (_StagingLock(f"tiles {label}") if todo_bytes >= STAGE_LOCK_MIN_BYTES
                    else contextlib.nullcontext())
            with lock:                      # P11.4: one bulk Drive copy at a time
                tick(f"stage tiles {label}")
                # BULK READ (2026-08-29). The per-file loop below reads each tile
                # individually over the FUSE mount. Measured on this night's run:
                # 613 tiles took 55+ min with the GPU at 0% and 6 MB allocated —
                # an A100 sitting idle moving files. A tile set is ~0.65 GB, under
                # STAGE_LOCK_MIN_BYTES, so nothing even serialises two arms doing
                # it at once. tiling.py already solved the WRITE direction this way
                # (78-138 s for the same volume); the READ direction never got it.
                # ONE `rclone copy` of the arm's tile dir replaces N FUSE opens.
                # Falls through to the per-file loop on ANY failure, so the slow
                # path stays the safety net rather than being deleted.
                src_root = Path(str(idx_df.iloc[0]["img_path"])).parents[2]
                if _bulk_stage_ok(src_root):
                    n_copied = _bulk_stage_tiles(src_root, dst_root, todo)
                if not n_copied:
                    for src, dst in todo:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        n_copied += 1
                tock(f"stage tiles {label}")
        out = idx_df.copy()
        for c in cols:
            out[c] = new_cols[c]
        print(f"  Tiles staged local: {n_copied} files copied ({todo_bytes / 1e9:.2f} GB) → {dst_root}")
        return out
    except Exception as e:
        print(f"  WARNING: tile staging failed ({e}); training reads from Drive")
        return idx_df

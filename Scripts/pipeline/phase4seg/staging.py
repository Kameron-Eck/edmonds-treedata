"""staging.py — bulk tile staging from the Drive mount to local disk.

Split out of core.py 2026-09-01 (plan item 1 / 3.5 continuation — the losses.py
precedent). core.py re-exports every name here with a facade import, so call sites
and test monkeypatches that reach them as core.X keep working unchanged. Torch-free
by design: this cluster never touches the names _ensure_torch injects.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from pathlib import Path

from phase4seg import config
from phase4seg.config import LOCAL_SCRATCH
from phase4seg.common import _StagingLock, STAGE_LOCK_MIN_BYTES, tick, tock

_STAGE_RCLONE_REMOTE = "treedata-user"     # gen_vm_bootstrap.py's WRITER remote
_STAGE_MOUNT_PREFIX  = "/content/drive/MyDrive/treedata/"
_stage_rclone_probe = None


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
            ["rclone", "copy", f"{_STAGE_RCLONE_REMOTE}:{rel}", str(dst_root),
             "--transfers", "16", "--checkers", "16", "--checksum"],
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

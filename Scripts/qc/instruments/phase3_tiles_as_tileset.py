"""phase3_tiles_as_tileset.py — the Phase-3 crown tiles, materialized as a phase4 tile set.

THE QUESTION THIS SERVES (Kam, 2026-09-09): train a ResNet-50 base and a ResNet-18 base
from the SAME tiles the Phase-3 2020 base (phase3/sem_best_2020.pt, resnet101) was
trained on, so the backbone sweep can compare encoders with a same-trained start. The
phase4 engine (core.step_train / step_evaluate) reads exactly one thing: the tile
index at tile_dir_for(label)/tile_index_{label}.csv, i.e. phase4/tiles/2020__{tag}/.
The Phase-3 tiles live at phase3/tiles/{train,test}/{images,masks} with their own
index, in a column shape the engine no longer writes. This instrument copies the
tiles the Phase-3 INDEX names into a tagged phase4 tile directory and writes the
index + meta sidecar in the engine's current shape, so `--step train --step evaluate
--run-tag {tag}` consume them with no engine change.

WHAT IS COPIED — the index rows, not the directory. phase3/tiles/tile_index_semantic.csv
has 748 rows (598 train / 150 test, measured 2026-09-09) while the directories hold
670 / 221 files: 141 tiles on disk are in no index row. Phase-3 train AND evaluate
(pipeline/frozen/phase3_semantic_dev.py, `index_path = TILE_DIR / "tile_index_semantic.csv"`)
read the index — but the index on the lake today is 13 h NEWER than the Phase-3
checkpoint and every indexed tile was re-cut after that training, so WHICH tiles the
checkpoint actually saw is UNVERIFIABLE from the lake (referee, 2026-09-09). What is
copied is the current index's 748; the orphan count is recorded in the meta's
split_status so the discrepancy is visible, not silently resolved either way.

WHAT THE META IS FOR. Nothing in train/evaluate REQUIRES the sidecar: staging.py's
bundle path refuses gracefully without one and falls to the per-file copy, and the
index alone drives the split. It is read by three things: cli._record_tilesets (stamps
the run manifest with tileset_id), qc/instruments/harvest_tilesets.py (the tracked
registry row), and tiling._existing_tiles_valid — which is the HAZARD, see below.

THE ID RULE — same tiles, same id. `tileset_id_from_meta` hashes every key except
config.META_NONSIG_KEYS ("split_status"). Two tags materialized from the same source
hold byte-identical tiles, and the registry contract (docs/SCHEMAS.md) is that one id
means one tile set — that is exactly what makes "base50 and base18 trained on the same
tiles" checkable later. So the HASHED part is content-determined only (source index,
its sha256, the row counts, the label rasters by name+size, the tile geometry) and
everything per-run — materialized_utc, run_tag — rides under `split_status`, the one
key the hasher strips. An idempotent re-run keeps the ORIGINAL materialized_utc.

HAZARD — NEVER RUN `--step tile` (or --force-retile) UNDER THESE TAGS. The meta written
here can never equal a live tiling._tile_signature (it carries keys the engine never
writes), so step_tile would judge the cache invalid and RE-TILE the citywide 2020-mask
recipe INTO this directory, over the crown tiles, with nothing logged but a retile.
Queue jobs for these tags stop at steps [train, evaluate].

Mask values: the Phase-3 masks are 0/1 uint8 with nodata 255 (measured on two real
tiles 2026-09-09), which is the engine's own 0 / 1 / 255=IGNORE contract. Every mask is
checked on the local copy and the run REFUSES on any value outside {0, 1, 255} — a
0/255 mask would train with all canopy as IGNORE and nothing would raise.

THIS INSTRUMENT WRITES TO THE LAKE — the one sanctioned exception to qc/instruments/
CLAUDE.md's "instruments never write to the data lake" (Kam, 2026-09-09): it creates a
NEW tagged tile directory and never touches an existing one (a differing index in the
target refuses; an identical one resumes). Under pytest the conftest lake guard still
applies; the tests run it against a synthetic root in tmp_path only.

Local-then-copy (CLAUDE.md 3.9): each tile is read from the lake once, written to a
local scratch file, verified (size; masks by value set; images by band count and
size), then copied to the lake directory and size-verified there. A destination file
whose size already equals the source is skipped, so a re-run is a resume.

Run:  py -3.12 qc/instruments/phase3_tiles_as_tileset.py --tag base50
      py -3.12 qc/instruments/phase3_tiles_as_tileset.py --tag base50 --dry-run
      then: py -3.12 qc/instruments/harvest_tilesets.py   (the registry row)
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath

LABEL = "2020"                       # the Phase-3 anchor year; config.ANCHOR_LABEL
SOURCE_INDEX_REL = "phase3/tiles/tile_index_semantic.csv"
SOURCE_LABELS_REL = "phase3/labels"
SOURCE_DESC = "phase3/tiles hand-traced crowns"
MATERIALIZER = "phase3_tiles_as_tileset"

# The engine's index shape — tiling.py's index_rows dict, verbatim key order.
# qc/test_phase3_tiles_as_tileset.py::test_index_columns_match_the_engine reads the
# engine source and fails if this list drifts from it.
INDEX_COLS = ["tile_name", "site", "split", "row_off", "col_off", "canopy_frac",
              "block", "split_mode", "img_path", "mask_path", "height_path"]
SOURCE_COLS = ["tile_name", "site", "split", "row_off", "col_off", "canopy_frac",
               "img_path", "mask_path"]
KINDS = {"img_path": "images", "mask_path": "masks"}


def _lake_root():
    from phase4seg import config
    for cand in (Path(config.BASE), Path(r"G:/My Drive/treedata")):
        if cand.exists():
            return cand
    return None


def _colab_base():
    """The Colab-absolute lake prefix the engine bakes into every index path."""
    from phase4seg import config
    return config.BASE.as_posix()


def _rewrite_to_root(colab_path, root):
    """A Colab-absolute lake path -> the same file under `root`."""
    base = _colab_base()
    s = str(colab_path).replace("\\", "/")
    if not s.startswith(base + "/"):
        raise SystemExit(f"source index path is not Colab-absolute under {base}: {s}")
    return Path(root) / s[len(base) + 1:]


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _measure_stride(rows):
    """Smallest positive offset step within a site, over both axes — the tile stride
    the source was cut at. None when no site has two tiles on one axis."""
    best = None
    by_site = {}
    for r in rows:
        by_site.setdefault(r["site"], []).append((int(r["row_off"]), int(r["col_off"])))
    for offs in by_site.values():
        for axis in (0, 1):
            vals = sorted({o[axis] for o in offs})
            for a, b in zip(vals, vals[1:]):
                d = b - a
                if d > 0 and (best is None or d < best):
                    best = d
    return best


def _check_tile(local_path, kind, tile_size, ignore_label):
    """Validate a LOCAL copy: geometry for both kinds, the value set for masks.
    Returns the set of mask values (empty for images)."""
    import numpy as np
    import rasterio
    with rasterio.open(local_path) as s:
        if (s.width, s.height) != (tile_size, tile_size):
            raise SystemExit(f"{local_path.name}: {s.width}x{s.height}, expected "
                             f"{tile_size}x{tile_size} (config.TILE_SIZE)")
        if kind == "images":
            if s.count != 3:
                raise SystemExit(f"{local_path.name}: {s.count} bands, expected 3 (RGB)")
            return set()
        if s.count != 1:
            raise SystemExit(f"{local_path.name}: mask has {s.count} bands, expected 1")
        vals = set(int(v) for v in np.unique(s.read(1)))
    bad = vals - {0, 1, ignore_label}
    if bad:
        raise SystemExit(
            f"{local_path.name}: mask carries values {sorted(bad)} — the engine's "
            f"contract is 0 background / 1 canopy / {ignore_label} IGNORE. A 0/255 "
            f"mask would train with every canopy pixel as IGNORE. Refusing.")
    return vals


def build_index_text(rows, tag, split_mode):
    """The engine-shaped index CSV for these rows, as text. Pure: no I/O."""
    from phase4seg.names import tile_dir_name
    out_dir = PurePosixPath(_colab_base()) / "phase4" / "tiles" / tile_dir_name(LABEL, tag)
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=INDEX_COLS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({
            "tile_name": r["tile_name"], "site": r["site"], "split": r["split"],
            "row_off": r["row_off"], "col_off": r["col_off"],
            "canopy_frac": r["canopy_frac"],
            "block": "", "split_mode": split_mode,
            "img_path": str(out_dir / r["split"] / "images" / r["tile_name"]),
            "mask_path": str(out_dir / r["split"] / "masks" / r["tile_name"]),
            "height_path": "",
        })
    return buf.getvalue()


def _read_source(root):
    src_index = Path(root) / SOURCE_INDEX_REL
    if not src_index.exists():
        raise SystemExit(f"source index not found: {src_index}")
    raw = src_index.read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    if not rows:
        raise SystemExit(f"source index is empty: {src_index}")
    missing = [c for c in SOURCE_COLS if c not in rows[0]]
    if missing:
        raise SystemExit(f"source index lacks columns {missing}: {src_index}")
    bad_split = sorted({r["split"] for r in rows} - {"train", "test"})
    if bad_split:
        raise SystemExit(f"source index carries splits {bad_split}; expected train/test only")
    names = [r["tile_name"] for r in rows]
    if len(set(names)) != len(names):
        raise SystemExit("source index has duplicate tile_name rows")
    return src_index, raw, rows


def _orphan_count(root, rows):
    """TILES on disk under phase3/tiles that no index row names — a tile is one
    (split, name) whether its image, its mask or both are present; desktop.ini and
    other non-.tif files are excluded."""
    named = {(r["split"], r["tile_name"]) for r in rows}
    orphan = set()
    for split in ("train", "test"):
        for kind in ("images", "masks"):
            d = Path(root) / "phase3" / "tiles" / split / kind
            if not d.exists():
                continue
            for f in os.listdir(d):
                if f.lower().endswith(".tif") and (split, f) not in named:
                    orphan.add((split, f))
    return len(orphan)


def _label_masks(root):
    d = Path(root) / SOURCE_LABELS_REL
    if not d.exists():
        return []
    return [{"name": p.name, "size": int(p.stat().st_size)}
            for p in sorted(d.glob("*_canopy_mask.tif"))]


def materialize(root, tag, scratch, dry_run=False, keep_scratch=False, log=print):
    from phase4seg import config
    from phase4seg.names import sanitize_tag, tile_dir_name
    from phase4seg.tiling import tileset_id_from_meta

    root = Path(root)
    clean = sanitize_tag(tag)
    if clean != tag:
        raise SystemExit(f"--tag {tag!r} is not filename-safe; use {clean!r}")
    src_index, raw, rows = _read_source(root)
    n_train = sum(r["split"] == "train" for r in rows)
    n_test = sum(r["split"] == "test" for r in rows)
    stride = _measure_stride(rows)
    tile_size = int(config.TILE_SIZE)
    split_mode = config.SPLIT_MODE_SITEWISE       # a stratified-random test split, by site
    target = root / "phase4" / "tiles" / tile_dir_name(LABEL, tag)
    index_path = target / f"tile_index_{LABEL}.csv"
    meta_path = target / f"tile_index_{LABEL}.meta.json"
    index_text = build_index_text(rows, tag, split_mode)

    # Refuse to touch a directory that holds a DIFFERENT index; an identical one is
    # a resume. A directory with tiles but no index (an interrupted first run) is
    # also a resume — the index is written last, so its absence is the marker.
    if index_path.exists():
        have = index_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if have != index_text:
            raise SystemExit(
                f"{index_path} exists and differs from the index this run would write "
                f"— the directory holds another tile set (or an older materialization). "
                f"Refusing to overwrite. Pick another --tag, or remove the directory "
                f"yourself if you are sure it is expendable.")

    orphans = _orphan_count(root, rows)
    label_masks = _label_masks(root)
    sig = {
        "label": LABEL, "materializer": MATERIALIZER,
        "citywide": False, "stride": stride, "max_tiles": None, "tile_size": tile_size,
        "use_hillshade": False, "hs_source": "", "use_vi": False,
        "label_masks": label_masks,
        "provenance": {
            "source": SOURCE_DESC,
            "source_index": SOURCE_INDEX_REL,
            "source_index_sha256": _sha256_bytes(raw),
            "source_imagery": "photos/{site}_rgb.tif (Phase-3 site photos, EPSG:3857)",
            "source_labels": SOURCE_LABELS_REL + "/{site}_canopy_mask.tif",
            "n_train": n_train, "n_test": n_test,
        },
    }
    prior_utc = None
    if meta_path.exists():
        try:
            prior_utc = (json.loads(meta_path.read_text(encoding="utf-8"))
                         .get("split_status", {}).get("materialized_utc"))
        except Exception:
            prior_utc = None
    now = prior_utc or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    split_status = {
        "mode": split_mode, "degraded": False,
        "stride": stride, "tile_size": tile_size,
        "overlapping": (stride is not None and stride < tile_size),
        "test_frac": round(n_test / len(rows), 4),
        "train": n_train, "val": 0, "test": n_test, "dropped": 0,
        "materialized_utc": now, "materialized_by": MATERIALIZER, "run_tag": tag,
        "orphan_tiles_not_indexed": orphans,
    }
    meta = {**sig, "split_status": split_status}
    meta_text = json.dumps(meta)

    log(f"source : {src_index}  ({len(rows)} rows: train {n_train} / test {n_test}; "
        f"{orphans} tile files on disk in no row)")
    log(f"target : {target}")
    log(f"stride : {stride}px  tile {tile_size}px  split_mode={split_mode}  "
        f"label rasters: {len(label_masks)}")
    if dry_run:
        # tileset_id needs a file to hash; hash the text through a scratch-free path.
        tmp = Path(tempfile.mkdtemp(prefix="p3ts_dry_")) / "m.json"
        tmp.write_text(meta_text, encoding="utf-8")
        tsid = tileset_id_from_meta(tmp)
        shutil.rmtree(tmp.parent, ignore_errors=True)
        log(f"DRY RUN — nothing written. tileset_id would be {tsid}")
        return {"copied": 0, "skipped": 0, "bytes": 0, "tileset_id": tsid,
                "n_train": n_train, "n_test": n_test, "orphans": orphans,
                "target": target, "dry_run": True}

    scratch = Path(scratch)
    copied = skipped = 0
    nbytes = 0
    mask_vals = set()
    for split in ("train", "test"):
        for kind in KINDS.values():
            (target / split / kind).mkdir(parents=True, exist_ok=True)
            (scratch / split / kind).mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(rows, 1):
        for col, kind in KINDS.items():
            src = _rewrite_to_root(r[col], root)
            dst = target / r["split"] / kind / r["tile_name"]
            loc = scratch / r["split"] / kind / r["tile_name"]
            if not src.exists():
                raise SystemExit(f"source tile missing: {src}")
            src_size = src.stat().st_size
            if dst.exists() and dst.stat().st_size == src_size:
                skipped += 1
                continue
            data = src.read_bytes()
            if len(data) != src_size:
                raise SystemExit(f"short read on {src} ({len(data)} of {src_size} bytes)")
            loc.write_bytes(data)
            if loc.stat().st_size != src_size:
                raise SystemExit(f"scratch write mismatch for {loc}")
            mask_vals |= _check_tile(loc, kind, tile_size, int(config.IGNORE_LABEL))
            shutil.copyfile(loc, dst)
            if dst.stat().st_size != src_size:
                raise SystemExit(f"lake copy mismatch for {dst}")
            copied += 1
            nbytes += src_size
        if i % 100 == 0:
            log(f"  {i}/{len(rows)} rows  (copied {copied}, skipped {skipped}, "
                f"{nbytes / 1e6:.1f} MB)")

    # Index, then meta — meta LAST, as the engine does, so an interrupted run never
    # leaves a sidecar over an incomplete directory.
    index_path.write_text(index_text, encoding="utf-8", newline="")
    meta_path.write_text(meta_text, encoding="utf-8")
    tsid = tileset_id_from_meta(meta_path)
    if not keep_scratch:
        shutil.rmtree(scratch, ignore_errors=True)
    log(f"done   : copied {copied} files ({nbytes / 1e6:.1f} MB), skipped {skipped} "
        f"already present; mask values seen on copied tiles: {sorted(mask_vals) or '-'}")
    log(f"index  : {index_path.name}  ({len(rows)} rows)")
    log(f"meta   : {meta_path.name}  tileset_id={tsid}")
    return {"copied": copied, "skipped": skipped, "bytes": nbytes, "tileset_id": tsid,
            "n_train": n_train, "n_test": n_test, "orphans": orphans,
            "target": target, "mask_values": sorted(mask_vals), "dry_run": False}


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", required=True,
                    help="run tag; the tiles land in phase4/tiles/2020__{tag}/")
    ap.add_argument("--root", default=None,
                    help="lake root (default: config.BASE, else G:/My Drive/treedata)")
    ap.add_argument("--scratch", default=None,
                    help="local scratch dir for the local-then-copy hop "
                         "(default: a fresh temp dir)")
    ap.add_argument("--keep-scratch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    root = Path(a.root) if a.root else _lake_root()
    if root is None or not root.exists():
        print(f"FATAL: lake root not found ({root}) — mount it, or pass --root")
        return 2
    scratch = Path(a.scratch) if a.scratch else Path(tempfile.mkdtemp(prefix="p3ts_"))
    materialize(root, a.tag, scratch, dry_run=a.dry_run, keep_scratch=a.keep_scratch)
    return 0


if __name__ == "__main__":
    sys.exit(main())

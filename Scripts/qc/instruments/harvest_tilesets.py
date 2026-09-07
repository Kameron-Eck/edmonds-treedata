"""harvest_tilesets.py — give every tile set a stable ID, and track which tiles it holds.

THE QUESTION THIS ANSWERS: "we ran the model on 10 years of imagery for the same
tiles — which set was that, and which tiles were in it?" (Kam, 2026-09-06).

The engine already DEFINES tile-set identity: `tiling._tile_signature()` returns the
dict that decides whether a cached tile set may be reused, and it is stored beside the
tiles as `tile_index_{label}.meta.json`. What never existed is an ID anyone can quote,
join on, or put in a CSV. This instrument hashes that stored dict into `tileset_id` and
writes two tracked artifacts:

    phase4/qc/tileset_registry.csv        one row per tile set — the ID, its knobs,
                                          its counts, its split, its ortho and labels
    phase4/qc/tilesets/{tileset_id}.csv   the tile list: row_off, col_off, split, block

The per-set list is written ONCE and never rewritten: a tile set is defined by its
content, so a re-tile produces a different signature, a different ID, and a new file.
The old one stays as the record of what the older runs actually trained on. Pruned to
the four columns that are provenance (the lake-absolute img/mask paths are dropped —
they say where bytes live today, not what the set IS): 41,856 tiles across 81 sets is
1.1 MB, which is why the lists are tracked rather than pointed at.

HASHING RULE — hash the dict AS STORED, canonicalised with sort_keys. It is tempting
to re-derive the signature from live config instead, but the stored dict is the only
record of what the tiles were actually cut under, and `_existing_tiles_valid` itself
grandfathers legacy caches by REMOVING keys (`ortho` pre-P6.6, `mask_2020`/`label_masks`
pre-2026-09-03). So two eras can hold engine-identical tile sets under different dicts.
Those get different IDs, and `sig_keys` in the registry says exactly why — an honest
difference beats a hash that pretends the eras were the same.

`split_status` is stripped by name via `config.META_NONSIG_KEYS`, the same way the
engine strips it: it records what the split turned out to be, not what was requested.
Its contents are reported in their own registry columns instead.

Run:  py -3.12 qc/instruments/harvest_tilesets.py            (needs the lake mounted)
      py -3.12 qc/instruments/harvest_tilesets.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent

# The four columns that make a tile list provenance rather than a path listing.
TILE_COLS = ("row_off", "col_off", "split", "block")

REGISTRY_COLS = [
    "tileset_id", "label", "run_tag", "tile_dir",
    "n_tiles", "n_train", "n_val", "n_test", "n_drop",
    "split_mode", "blocks", "block_px", "split_degraded",
    "citywide", "stride", "max_tiles", "tile_size", "random_seed",
    "use_hillshade", "hs_source", "use_vi", "aux_height",
    "coarse_val_frac", "coarse_test_frac", "spatial_block_size_m",
    "canopy_autocorr_m", "hard_neg_fraction", "background_budget_fraction",
    "green_grvi_threshold", "citywide_tiles",
    "ortho_name", "ortho_size", "label_source", "label_source_size",
    "add_canopy_mask", "sample_manifest",
    "sig_keys", "id_basis", "tile_list", "note",
]


def tileset_id(stored_meta, nonsig_keys):
    """The tile set's ID: sha256 of the stored signature, split_status stripped.

    Canonical JSON (sorted keys, no whitespace drift) so the same dict always hashes
    the same, on any platform. 12 hex chars — 48 bits over a population of order 100
    tile sets, which is collision-free by a wide margin and still eyeball-comparable.
    """
    sig = {k: v for k, v in stored_meta.items() if k not in nonsig_keys}
    canon = json.dumps(sig, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12], sig


def _prune_tile_list(index_path):
    """Return (csv_text, counts) for the tile list, keeping only TILE_COLS."""
    rows = list(csv.DictReader(io.StringIO(index_path.read_text(encoding="utf-8"))))
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(TILE_COLS)
    counts = {"n_tiles": len(rows), "n_train": 0, "n_val": 0, "n_test": 0, "n_drop": 0}
    for r in rows:
        w.writerow([r.get(c, "") for c in TILE_COLS])
        key = f"n_{str(r.get('split', '')).strip()}"
        if key in counts:
            counts[key] += 1
    return buf.getvalue(), counts


def _flat(sig, key, sub=None, default=""):
    v = sig.get(key, default)
    if sub is not None and isinstance(v, dict):
        return v.get(sub, "")
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, separators=(",", ":"))
    return "" if v is None else v


def harvest(tiles_root, out_dir, lists_dir, dry_run=False):
    from phase4seg.config import META_NONSIG_KEYS

    rows, written_lists, skipped = [], 0, []
    for d in sorted(p for p in Path(tiles_root).iterdir() if p.is_dir()):
        label, _, run_tag = d.name.partition("__")
        idx = sorted(d.glob("tile_index_*.csv"))
        meta = sorted(d.glob("tile_index_*.meta.json"))
        if not idx:
            skipped.append((d.name, "no tile_index CSV"))
            continue
        try:
            listing, counts = _prune_tile_list(idx[0])
        except Exception as e:                                   # unreadable index
            skipped.append((d.name, f"index unreadable: {e}"))
            continue

        if meta:
            # The 6-site path writes no sidecar, and pre-tag legacy dirs may lack one.
            # No sidecar means no signature means NO ID — never a fabricated one.
            stored = json.loads(meta[0].read_text(encoding="utf-8"))
            tsid, sig = tileset_id(stored, META_NONSIG_KEYS)
            status = stored.get("split_status") or {}
            id_basis, note = "meta.json", ""
        else:
            tsid, sig, status = "", {}, {}
            id_basis = "none"
            note = ("no meta.json sidecar — 6-site path or pre-tag legacy dir; "
                    "tiles are recorded, identity is not derivable")

        if tsid and not dry_run:
            lists_dir.mkdir(parents=True, exist_ok=True)
            dst = lists_dir / f"{tsid}.csv"
            if not dst.exists():          # immutable: a re-tile makes a NEW id/file
                dst.write_text(listing, encoding="utf-8", newline="")
                written_lists += 1

        rows.append({
            "tileset_id": tsid, "label": label, "run_tag": run_tag,
            "tile_dir": d.name, **counts,
            "split_mode": status.get("mode", ""),
            "blocks": status.get("blocks", ""),
            "block_px": status.get("block_px", ""),
            "split_degraded": status.get("degraded", ""),
            "citywide": _flat(sig, "citywide"), "stride": _flat(sig, "stride"),
            "max_tiles": _flat(sig, "max_tiles"), "tile_size": _flat(sig, "tile_size"),
            "random_seed": _flat(sig, "random_seed"),
            "use_hillshade": _flat(sig, "use_hillshade"),
            "hs_source": _flat(sig, "hs_source"), "use_vi": _flat(sig, "use_vi"),
            "aux_height": _flat(sig, "aux_height"),
            "coarse_val_frac": _flat(sig, "coarse_val_frac"),
            "coarse_test_frac": _flat(sig, "coarse_test_frac"),
            "spatial_block_size_m": _flat(sig, "spatial_block_size_m"),
            "canopy_autocorr_m": _flat(sig, "canopy_autocorr_m"),
            "hard_neg_fraction": _flat(sig, "hard_neg_fraction"),
            "background_budget_fraction": _flat(sig, "background_budget_fraction"),
            "green_grvi_threshold": _flat(sig, "green_grvi_threshold"),
            "citywide_tiles": _flat(sig, "citywide_tiles"),
            "ortho_name": _flat(sig, "ortho", "name"),
            "ortho_size": _flat(sig, "ortho", "size"),
            "label_source": (_flat(sig, "mask_2020", "name")
                             or _flat(sig, "label_masks")),
            "label_source_size": _flat(sig, "mask_2020", "size"),
            "add_canopy_mask": _flat(sig, "add_canopy_mask"),
            "sample_manifest": _flat(sig, "sample_manifest"),
            "sig_keys": ",".join(sorted(sig)) if sig else "",
            "id_basis": id_basis,
            "tile_list": f"phase4/qc/tilesets/{tsid}.csv" if tsid else "",
            "note": note,
        })

    rows.sort(key=lambda r: (r["label"], r["run_tag"], r["tileset_id"]))
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=REGISTRY_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "tileset_registry.csv").write_text(buf.getvalue(),
                                                      encoding="utf-8", newline="")
    return rows, written_lists, skipped


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tiles-root", default=None,
                    help="tiles directory (default: BASE/phase4/tiles)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    if a.tiles_root:
        tiles_root = Path(a.tiles_root)
    else:
        from phase4seg import config
        # config.BASE is the Colab mount; off-Colab the same lake is the Drive
        # letter. Same two-root fallback the other lake-reading instruments use.
        for cand in (Path(config.BASE) / "phase4" / "tiles",
                     Path(r"G:/My Drive/treedata/phase4/tiles")):
            tiles_root = cand
            if cand.exists():
                break
    if not tiles_root.exists():
        print(f"FATAL: tiles root not found: {tiles_root}\n"
              f"       this instrument reads the lake — mount it, or pass --tiles-root")
        return 2

    out_dir = REPO / "phase4" / "qc"
    lists_dir = out_dir / "tilesets"
    rows, n_lists, skipped = harvest(tiles_root, out_dir, lists_dir, a.dry_run)

    ided = [r for r in rows if r["tileset_id"]]
    uniq = {r["tileset_id"] for r in ided}
    shared = sum(1 for t in uniq
                 if sum(1 for r in ided if r["tileset_id"] == t) > 1)
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} tile dirs "
          f"→ {len(uniq)} distinct tile sets ({len(rows) - len(ided)} without identity)")
    print(f"  tiles indexed: {sum(int(r['n_tiles']) for r in rows):,}  "
          f"(train {sum(int(r['n_train']) for r in rows):,} / "
          f"val {sum(int(r['n_val']) for r in rows):,} / "
          f"test {sum(int(r['n_test']) for r in rows):,})")
    if shared:
        print(f"  {shared} tile set(s) shared by more than one arm — the reuse "
              f"Kam asked to be able to see")
    if not a.dry_run:
        print(f"  wrote phase4/qc/tileset_registry.csv and {n_lists} new tile list(s)")
    for name, why in skipped:
        print(f"  ! skipped {name}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

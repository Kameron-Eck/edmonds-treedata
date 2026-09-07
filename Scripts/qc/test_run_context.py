"""Gates for the run-context layer: tile sets, run passports, arm metrics.

WHY THESE GATES ARE STRUCTURAL, NOT FRESHNESS. `experiments/INDEX.md` is byte-compared
against a regeneration because every home it joins is tracked. This layer is harvested
from the LAKE, which CI does not mount, so "re-run the harvester and diff" is not a
check that can pass here. What CAN be checked without the lake is that the harvested
artifacts are internally coherent and that their joins resolve — which is what fails
when a harvest is stale, partial, or hand-edited.

Repo-only by construction, like qc/test_experiments.py.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
TILESET_REGISTRY = QC / "tileset_registry.csv"
TILESET_LISTS = QC / "tilesets"

ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _rows(path):
    if not path.exists():
        return []
    body = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _tilesets():
    rows = _rows(TILESET_REGISTRY)
    if not rows:
        pytest.skip("tileset_registry.csv absent — run "
                    "qc/instruments/harvest_tilesets.py with the lake mounted")
    return rows


# ------------------------------------------------------------------ identity

def test_tileset_ids_are_well_formed():
    """An ID is 12 lowercase hex, or empty when the sidecar that defines it is absent.

    Empty is legitimate (the 6-site path writes no meta.json) and MUST stay
    distinguishable from a fabricated one — hence the paired id_basis check.
    """
    for r in _tilesets():
        tsid, basis = r["tileset_id"], r["id_basis"]
        if tsid:
            assert ID_RE.match(tsid), f"{r['tile_dir']}: malformed tileset_id {tsid!r}"
            assert basis == "meta.json", (
                f"{r['tile_dir']}: has an id but id_basis is {basis!r} — an ID may "
                f"only come from a stored signature")
        else:
            assert basis == "none" and r["note"], (
                f"{r['tile_dir']}: no tileset_id but no stated reason — a missing "
                f"identity must say why it is missing")


def test_one_id_means_one_tile_set():
    """The whole point of the ID: same ID => same tiles, same split, same counts.

    If two arms share an ID, they trained on the SAME tile set — that is the reuse
    claim the registry exists to make, and a mismatch here would make it a lie.
    """
    by_id = {}
    for r in _tilesets():
        if not r["tileset_id"]:
            continue
        key = (r["n_tiles"], r["n_train"], r["n_val"], r["n_test"], r["n_drop"],
               r["ortho_name"], r["tile_size"])
        prev = by_id.setdefault(r["tileset_id"], (r["tile_dir"], key))
        assert prev[1] == key, (
            f"tileset_id {r['tileset_id']} describes two different tile sets: "
            f"{prev[0]} vs {r['tile_dir']}")


def test_counts_are_internally_consistent():
    for r in _tilesets():
        parts = sum(int(r[c]) for c in ("n_train", "n_val", "n_test", "n_drop"))
        assert parts == int(r["n_tiles"]), (
            f"{r['tile_dir']}: splits sum to {parts} but n_tiles is {r['n_tiles']}")


# ------------------------------------------------------------------ the lists

def test_every_id_has_its_tile_list():
    """`which tiles were used for training` is the deliverable — the file must be there."""
    for r in _tilesets():
        if not r["tileset_id"]:
            assert not r["tile_list"], f"{r['tile_dir']}: tile_list without an id"
            continue
        p = REPO / r["tile_list"]
        assert p.exists(), (
            f"{r['tile_dir']}: tile list {r['tile_list']} missing — the ID promises it")


def test_tile_lists_match_their_registry_row():
    """Row count and split counts in the list must equal the registry's."""
    seen = set()
    for r in _tilesets():
        tsid = r["tileset_id"]
        if not tsid or tsid in seen:
            continue
        seen.add(tsid)
        rows = _rows(REPO / r["tile_list"])
        assert len(rows) == int(r["n_tiles"]), (
            f"{tsid}: tile list has {len(rows)} rows, registry says {r['n_tiles']}")
        n_train = sum(1 for x in rows if x["split"] == "train")
        assert n_train == int(r["n_train"]), (
            f"{tsid}: tile list has {n_train} train tiles, registry says {r['n_train']}")


def test_tile_lists_carry_provenance_not_paths():
    """Lists hold the four provenance columns and NO lake-absolute paths.

    A path says where bytes live today; it is not what the tile set IS, and a tracked
    path rots the moment the lake is reorganised.
    """
    from instruments.harvest_tilesets import TILE_COLS
    for p in sorted(TILESET_LISTS.glob("*.csv"))[:12]:
        header = p.read_text(encoding="utf-8").splitlines()[0]
        assert header == ",".join(TILE_COLS), f"{p.name}: unexpected columns {header!r}"


def test_no_orphan_tile_lists():
    """Every tracked list belongs to a registry row — no files nothing points at."""
    known = {r["tileset_id"] for r in _tilesets() if r["tileset_id"]}
    orphans = [p.name for p in TILESET_LISTS.glob("*.csv") if p.stem not in known]
    assert not orphans, f"tile lists with no registry row: {orphans}"

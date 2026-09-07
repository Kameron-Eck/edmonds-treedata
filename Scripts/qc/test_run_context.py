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


# ------------------------------------------------------------------ passports

RUN_PASSPORT = QC / "run_passport.csv"
# A manifest-era run_id is timestamped `YYYYMMDDTHHMMSSZ_…`. Runs from before P6.1
# added run manifests use `YYYYMMDD_…` and legitimately have no passport — the format
# IS the discriminator, so no hand-maintained exception list can rot here.
MANIFEST_ERA = re.compile(r"^\d{8}T\d{6}Z_")
JOIN_BASES = {"manifest", "inferred_current", "none"}


def _passports():
    rows = _rows(RUN_PASSPORT)
    if not rows:
        pytest.skip("run_passport.csv absent — run "
                    "qc/instruments/harvest_run_passport.py with the lake mounted")
    return rows


def test_run_ids_are_unique():
    seen = set()
    for r in _passports():
        assert r["run_id"] not in seen, f"duplicate passport row {r['run_id']}"
        seen.add(r["run_id"])


def test_every_manifest_era_registry_row_has_a_passport():
    """run_registry.csv is the thin view; the passport is the wide one.

    Any manifest-era run in the registry without a passport row means the harvest is
    stale or a manifest went missing — either way the wide record no longer covers
    the ledger it is supposed to explain.
    """
    have = {r["run_id"] for r in _passports()}
    reg = SCRIPTS / "run_registry.csv"
    missing = [r["run_id"] for r in _rows(reg)
               if MANIFEST_ERA.match(r["run_id"]) and r["run_id"] not in have]
    assert not missing, (
        f"{len(missing)} manifest-era registry runs have no passport row "
        f"(re-run harvest_run_passport.py): {missing[:5]}")


def test_join_basis_is_declared_and_honest():
    """A tileset_id must be accompanied by how it was obtained — and resolve.

    `inferred_current` is a weaker claim than `manifest`: it reads the tile dir as it
    stands TODAY, and a dir re-tiles in place. Blurring the two would let a run claim
    tiles it never saw.
    """
    known = {r["tileset_id"] for r in _tilesets() if r["tileset_id"]}
    for r in _passports():
        basis, tsid = r["join_basis"], r["tileset_id"]
        assert basis in JOIN_BASES, f"{r['run_id']}: unknown join_basis {basis!r}"
        if basis == "none":
            assert not tsid, f"{r['run_id']}: join_basis none but carries a tileset_id"
        else:
            assert tsid, f"{r['run_id']}: join_basis {basis} without a tileset_id"
            assert tsid in known, (
                f"{r['run_id']}: tileset_id {tsid} is not in tileset_registry.csv")


# ------------------------------------------------------------------ arm metrics

ARM_METRICS = QC / "arm_metrics.csv"
CURVES = QC / "curves"


def _metrics():
    rows = _rows(ARM_METRICS)
    if not rows:
        pytest.skip("arm_metrics.csv absent — run "
                    "qc/instruments/harvest_arm_metrics.py")
    return rows


def test_policy_is_a_closed_set():
    """The policy names the RULE that chose the threshold, and it is not free text.

    "per-arm best F1" and "matched at precision 0.75" are different claims about the
    same arm; a typo'd or invented policy silently mixes them back together, which is
    the 10.09-vs-1.07 pp failure.
    """
    from instruments.harvest_arm_metrics import POLICIES
    for r in _metrics():
        assert r["policy"] in POLICIES, (
            f"{r['curve_id']}: unknown policy {r['policy']!r} — allowed: {POLICIES}")


def test_every_point_carries_its_operating_point():
    """No bare precision/recall pair: a threshold and a population, every row."""
    for r in _metrics():
        assert r["thresh"], f"{r['curve_id']}/{r['policy']}: precision and recall with no threshold"
        assert r["population"], f"{r['curve_id']}/{r['policy']}: no evaluation population size"


def test_counts_agree_with_the_ratios():
    """precision = tp/(tp+fp) and recall = tp/(tp+fn), recomputed from the counts.

    Storing counts is what makes the ratios auditable; this is the audit.
    """
    for r in _metrics():
        tp, fn, fp = (float(r["tp"]), float(r["fn"]), float(r["fp"]))
        if tp + fp:
            assert abs(tp / (tp + fp) - float(r["precision"])) < 5e-4, (
                f"{r['curve_id']}/{r['policy']}: precision disagrees with tp/fp")
        if tp + fn:
            assert abs(tp / (tp + fn) - float(r["recall"])) < 5e-4, (
                f"{r['curve_id']}/{r['policy']}: recall disagrees with tp/fn")


def test_matched_points_actually_meet_their_floor():
    """A `matched_p75` row whose precision is below 0.75 would be a lie in the name."""
    for r in _metrics():
        if r["policy"].startswith("matched_p"):
            floor = int(r["policy"].split("_p")[1]) / 100.0
            assert float(r["precision"]) >= floor - 5e-4, (
                f"{r['curve_id']}: {r['policy']} has precision {r['precision']}")


def test_curve_files_resolve_and_are_shaped_right():
    from instruments.harvest_arm_metrics import CURVE_COLS
    seen = set()
    for r in _metrics():
        if not r["curve_file"] or r["curve_id"] in seen:
            continue
        seen.add(r["curve_id"])
        p = REPO / r["curve_file"]
        assert p.exists(), f"{r['curve_id']}: curve file {r['curve_file']} missing"
        lines = p.read_text(encoding="utf-8").splitlines()
        assert lines[0] == ",".join(CURVE_COLS), f"{p.name}: unexpected columns"
        assert len(lines) - 1 == int(r["n_cuts"]), (
            f"{p.name}: {len(lines) - 1} cuts, row says {r['n_cuts']}")


def test_one_curve_id_means_one_population():
    """Same id => same arm, same reference, same pixels.

    The bug this pins: the first harvest keyed on (year, tag, ref, prob, def) and the
    LOSO `sample-selection` and `sample-test` halves — genuinely different populations
    — collided into one id, silently discarding one of them. 87 sweeps became 58.
    """
    by = {}
    for r in _metrics():
        if not r["curve_file"]:
            continue
        prev = by.setdefault(r["curve_id"], (r["eval_scope"], r["population"]))
        assert prev[0] == r["eval_scope"], (
            f"curve_id {r['curve_id']} spans scopes {prev[0]!r} and {r['eval_scope']!r}")

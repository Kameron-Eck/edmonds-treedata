"""qc/instruments/phase3_tiles_as_tileset.py — the Phase-3 crown tiles as a phase4 tile set.

Everything runs against a synthetic lake in tmp_path (qc/conftest.py forbids the real
one). Synthetic tiles test the CODE — layout, column shape, path rewriting, value
pass-through, idempotence, refusal — not the claim that the real set trains a fair
base; that is the real run's job and its counts are reported, never asserted here.
"""
import ast
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
yaml = pytest.importorskip("yaml")

SCRIPTS = Path(__file__).resolve().parents[1]
INSTRUMENT = SCRIPTS / "qc" / "instruments" / "phase3_tiles_as_tileset.py"
TILING = SCRIPTS / "pipeline" / "phase4seg" / "tiling.py"


def _load():
    spec = importlib.util.spec_from_file_location("p3ts", INSTRUMENT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


P3 = _load()
COLAB = "/content/drive/MyDrive/treedata"


def _write_tif(path, arr, nodata=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 1 if arr.ndim == 2 else arr.shape[0]
    prof = {"driver": "GTiff", "dtype": "uint8", "count": count,
            "width": arr.shape[-1], "height": arr.shape[-2], "compress": "lzw",
            "crs": "EPSG:3857",
            "transform": rasterio.transform.from_origin(0, 0, 0.05, 0.05)}
    if nodata is not None:
        prof["nodata"] = nodata
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr if arr.ndim == 3 else arr[None])


def build_source(root, n=512, mask_values=(0, 1, 255), extra_orphan=True):
    """A miniature phase3/tiles: 4 train + 2 test rows over two sites, Colab paths."""
    from phase4seg import config
    root = Path(root)
    tiles = root / "phase3" / "tiles"
    rows = []
    spec = [("forest_1", "Forest_1", "train", 0, 0), ("forest_1", "Forest_1", "train", 0, n),
            ("forest_1", "Forest_1", "train", n, 0), ("negative_water", "Negative_Water",
                                                     "train", 0, 0),
            ("forest_1", "Forest_1", "test", n, n), ("negative_water", "Negative_Water",
                                                    "test", 0, n)]
    rng = np.random.RandomState(0)
    for i, (stem, site, split, ro, co) in enumerate(spec):
        name = f"{stem}_r{ro:05d}_c{co:05d}.tif"
        img = rng.randint(0, 255, size=(3, n, n), dtype=np.uint8)
        mask = np.zeros((n, n), dtype=np.uint8)
        vals = list(mask_values)
        mask[: n // 2] = vals[min(1, len(vals) - 1)]
        mask[-8:, -8:] = vals[-1]
        _write_tif(tiles / split / "images" / name, img)
        _write_tif(tiles / split / "masks" / name, mask, nodata=int(config.IGNORE_LABEL))
        rows.append(f"{name},{site},{split},{ro},{co},{0.5 if 'forest' in stem else 0.0},"
                    f"{COLAB}/phase3/tiles/{split}/images/{name},"
                    f"{COLAB}/phase3/tiles/{split}/masks/{name}")
    if extra_orphan:      # on disk, in no row — the real lake has 143 of these
        _write_tif(tiles / "train" / "images" / "forest_9_r00000_c00000.tif",
                   np.zeros((3, n, n), dtype=np.uint8))
        _write_tif(tiles / "train" / "masks" / "forest_9_r00000_c00000.tif",
                   np.zeros((n, n), dtype=np.uint8))
        (tiles / "train" / "images" / "desktop.ini").write_text("x")
    (tiles / "tile_index_semantic.csv").write_text(
        "tile_name,site,split,row_off,col_off,canopy_frac,img_path,mask_path\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    labels = root / "phase3" / "labels"
    labels.mkdir(parents=True)
    (labels / "forest_1_canopy_mask.tif").write_bytes(b"\0" * 100)
    (labels / "negative_water_canopy_mask.tif").write_bytes(b"\0" * 50)
    return root


def _run(root, tag, tmp_path, dry_run=False):
    scratch = tmp_path / f"scratch_{tag}"
    out = []
    res = P3.materialize(root, tag, scratch, dry_run=dry_run, log=out.append)
    return res, "\n".join(out)


def _index_rows(target):
    import csv
    with open(target / "tile_index_2020.csv", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def _engine_index_keys():
    """The keys tiling.py writes per index row — read from the SOURCE, not retyped."""
    tree = ast.parse(TILING.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "index_rows" and node.args
                and isinstance(node.args[0], ast.Dict)):
            return [k.value for k in node.args[0].keys if isinstance(k, ast.Constant)]
    raise AssertionError("tiling.py: index_rows.append({...}) not found")


# ── the shape the engine reads ──────────────────────────────────────────────────
def test_index_columns_match_the_engine():
    assert P3.INDEX_COLS == _engine_index_keys()


def test_layout_index_and_meta(tmp_path):
    from phase4seg import config
    from phase4seg.tiling import tileset_id_from_meta
    root = build_source(tmp_path / "lake")
    res, log = _run(root, "base50", tmp_path)
    target = root / "phase4" / "tiles" / "2020__base50"
    assert res["target"] == target and target.is_dir()
    for split, n in (("train", 4), ("test", 2)):
        assert len(list((target / split / "images").glob("*.tif"))) == n
        assert len(list((target / split / "masks").glob("*.tif"))) == n
    assert not list(target.rglob("forest_9_*")), "orphan files must NOT be copied"
    assert res["copied"] == 12 and res["skipped"] == 0
    assert res["orphans"] == 1 and res["n_train"] == 4 and res["n_test"] == 2

    cols, rows = _index_rows(target)
    assert cols == P3.INDEX_COLS
    assert len(rows) == 6
    for r in rows:
        assert r["img_path"] == f"{COLAB}/phase4/tiles/2020__base50/{r['split']}/images/{r['tile_name']}"
        assert r["mask_path"] == f"{COLAB}/phase4/tiles/2020__base50/{r['split']}/masks/{r['tile_name']}"
        assert r["block"] == "" and r["height_path"] == ""
        assert r["split_mode"] == config.SPLIT_MODE_SITEWISE
        assert r["split"] in ("train", "test")
    # source columns pass through untouched — the fine-tier buffer split and the
    # per-site sampler read site/row_off/col_off from here
    assert [r["row_off"] for r in rows] == ["0", "0", "512", "0", "512", "0"]
    assert {r["site"] for r in rows} == {"Forest_1", "Negative_Water"}

    meta = json.loads((target / "tile_index_2020.meta.json").read_text())
    st = meta["split_status"]
    assert st["mode"] == config.SPLIT_MODE_SITEWISE and st["degraded"] is False
    assert st["train"] == 4 and st["test"] == 2 and st["val"] == 0
    assert st["test_frac"] == round(2 / 6, 4)
    assert st["stride"] == 512 and st["overlapping"] is False
    assert st["orphan_tiles_not_indexed"] == 1 and st["run_tag"] == "base50"
    assert st["materialized_utc"].endswith("Z")
    prov = meta["provenance"]
    assert prov["source"] == "phase3/tiles hand-traced crowns"
    assert prov["source_index"] == "phase3/tiles/tile_index_semantic.csv"
    assert prov["n_train"] == 4 and prov["n_test"] == 2
    assert len(prov["source_index_sha256"]) == 64
    assert meta["label_masks"] == [{"name": "forest_1_canopy_mask.tif", "size": 100},
                                   {"name": "negative_water_canopy_mask.tif", "size": 50}]
    assert meta["citywide"] is False and meta["use_hillshade"] is False
    for k in config.META_NONSIG_KEYS:
        assert k in meta                      # the harvest strips it by name
    tsid = tileset_id_from_meta(target / "tile_index_2020.meta.json")
    assert res["tileset_id"] == tsid and len(tsid) == 12
    assert "tileset_id=" + tsid in log


def test_mask_values_pass_through(tmp_path):
    root = build_source(tmp_path / "lake")
    _run(root, "t", tmp_path)
    src = root / "phase3" / "tiles" / "train" / "masks" / "forest_1_r00000_c00000.tif"
    dst = root / "phase4" / "tiles" / "2020__t" / "train" / "masks" / "forest_1_r00000_c00000.tif"
    with rasterio.open(src) as a, rasterio.open(dst) as b:
        assert np.array_equal(a.read(1), b.read(1))
        assert set(np.unique(b.read(1)).tolist()) == {0, 1, 255}
        assert b.nodata == 255
    assert src.stat().st_size == dst.stat().st_size


def test_images_are_three_band_tile_size(tmp_path):
    from phase4seg import config
    root = build_source(tmp_path / "lake")
    _run(root, "t", tmp_path)
    p = root / "phase4" / "tiles" / "2020__t" / "test" / "images" / "forest_1_r00512_c00512.tif"
    with rasterio.open(p) as s:
        assert s.count == 3 and (s.width, s.height) == (config.TILE_SIZE, config.TILE_SIZE)


# ── idempotence + the id rule ───────────────────────────────────────────────────
def test_rerun_is_a_resume_and_keeps_the_original_timestamp(tmp_path):
    root = build_source(tmp_path / "lake")
    r1, _ = _run(root, "t", tmp_path)
    target = root / "phase4" / "tiles" / "2020__t"
    idx1 = (target / "tile_index_2020.csv").read_bytes()
    meta1 = json.loads((target / "tile_index_2020.meta.json").read_text())
    meta1["split_status"]["materialized_utc"] = "2000-01-01T00:00:00Z"
    (target / "tile_index_2020.meta.json").write_text(json.dumps(meta1))
    # lose one lake file: the re-run must restore it and touch nothing else
    (target / "train" / "images" / "forest_1_r00000_c00000.tif").unlink()
    r2, _ = _run(root, "t", tmp_path)
    assert r2["copied"] == 1 and r2["skipped"] == 11
    assert (target / "tile_index_2020.csv").read_bytes() == idx1
    meta2 = json.loads((target / "tile_index_2020.meta.json").read_text())
    assert meta2["split_status"]["materialized_utc"] == "2000-01-01T00:00:00Z"
    assert r2["tileset_id"] == r1["tileset_id"]


def test_two_tags_from_one_source_share_one_tileset_id(tmp_path):
    """Same tiles, same id — the registry contract that makes 'base50 and base18
    trained on the same tiles' checkable. Per-run fields ride under split_status."""
    root = build_source(tmp_path / "lake")
    a, _ = _run(root, "base50", tmp_path)
    b, _ = _run(root, "base18", tmp_path)
    assert a["tileset_id"] == b["tileset_id"]
    ia = (root / "phase4/tiles/2020__base50/tile_index_2020.csv").read_text()
    ib = (root / "phase4/tiles/2020__base18/tile_index_2020.csv").read_text()
    assert ia != ib and ia.replace("2020__base50", "2020__base18") == ib


# ── refusals ────────────────────────────────────────────────────────────────────
def test_refuses_a_directory_holding_a_different_index(tmp_path):
    root = build_source(tmp_path / "lake")
    target = root / "phase4" / "tiles" / "2020__t"
    target.mkdir(parents=True)
    (target / "tile_index_2020.csv").write_text("tile_name,site\nx.tif,S\n")
    with pytest.raises(SystemExit) as e:
        _run(root, "t", tmp_path)
    assert "Refusing to overwrite" in str(e.value)
    assert not (target / "train").exists()


def test_refuses_mask_values_outside_the_contract(tmp_path):
    """A 0/255 (or 0/7) mask would train with every canopy pixel as IGNORE."""
    root = build_source(tmp_path / "lake", mask_values=(0, 7, 255))
    with pytest.raises(SystemExit) as e:
        _run(root, "t", tmp_path)
    assert "IGNORE" in str(e.value) and "[7]" in str(e.value)
    assert not (root / "phase4" / "tiles" / "2020__t" / "tile_index_2020.csv").exists()


def test_refuses_an_unsafe_tag(tmp_path):
    root = build_source(tmp_path / "lake")
    with pytest.raises(SystemExit):
        _run(root, "base 50", tmp_path)


def test_dry_run_writes_nothing(tmp_path):
    root = build_source(tmp_path / "lake")
    res, log = _run(root, "t", tmp_path, dry_run=True)
    assert res["dry_run"] and len(res["tileset_id"]) == 12
    assert not (root / "phase4").exists()
    assert "DRY RUN" in log


# ── the queue files that consume the real set ───────────────────────────────────
def test_hand_split_encoder_base_queues_match_the_generated_queue():
    """pipeline/queue_base50.yaml / queue_base18.yaml are HAND-SPLIT one-job files;
    each job must equal its job in the in-memory regeneration of
    experiments/encoder_bases.yaml, and the two must cover every arm."""
    spec = importlib.util.spec_from_file_location(
        "experiment_queue", SCRIPTS / "qc" / "experiment_queue.py")
    eq = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("experiment_queue", eq)
    spec.loader.exec_module(eq)
    text, _ = eq.generate(SCRIPTS / "experiments" / "encoder_bases.yaml")
    gen = {j["id"]: j for j in yaml.safe_load(text)}
    covered = set()
    for name in ("queue_base50.yaml", "queue_base18.yaml"):
        q = SCRIPTS / "pipeline" / name
        head = q.read_text(encoding="utf-8")
        assert head.startswith("# HAND-SPLIT from experiments/encoder_bases.yaml"), name
        jobs = yaml.safe_load(head)
        assert len(jobs) == 1, f"{name}: one job per A100"
        j = jobs[0]
        g = gen.get(j["id"])
        assert g, f"{name}: job {j['id']} is not in the generated queue"
        for k in ("year", "tag", "extra", "steps"):
            assert j[k] == g[k], (name, k, j[k], g[k])
        assert j["steps"] == ["train", "evaluate"], "tile must NEVER run under these tags"
        assert j["extra"][-1].startswith("-"), \
            "the queue tests a non-flag final extra as a path (phase4_train_queue.py)"
        covered.add(j["id"])
    assert covered == set(gen)

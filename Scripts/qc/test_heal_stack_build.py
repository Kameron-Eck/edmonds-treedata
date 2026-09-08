"""Gates for the N-epoch stack builder — chiefly, that it cannot touch the published 8.

`trend8_stack_2m.npz` is the cache every tracked heal_* CSV was regenerated from. The
builder's whole reason to exist is to make a WIDER stack somewhere else, so the one gate
that matters is the name refusal, and CLAUDE.md 3.4c says a gate that has never fired is
not known to work: it is fired here, with and without --force, on a pre-seeded file whose
bytes are then shown unchanged. The rest pins the contract the consumers read (the four
npz keys, dtypes, shape), the warp semantics against tiny GeoTIFFs written into tmp_path,
the chronological order with an 's' label, campaign-mask discovery with its duplicate-year
refusal, --dry-run writing nothing, --force semantics, and the parity gate firing on a
reference whose shared layer differs.

No shapefile: the lattice is a pre-built (tf, w, h, inside) passed to `build`, or read
from a tiny npz via --grid-from. The lake is never touched (qc/conftest.py); every path
here is under tmp_path except the read-only fingerprint of the published cache.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_heal_stack_build.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]

np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")
from affine import Affine  # noqa: E402


def _load():
    """By path, not by sys.path insert (ledger: test_status_discovery)."""
    p = SCRIPTS / "qc" / "instruments" / "heal_stack_build.py"
    spec = importlib.util.spec_from_file_location("_hsb_under_test", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load()

EPSG = 26910
X0, Y0 = 500000.0, 5300000.0          # 1 m source pixels, 40 x 40
SRC_N = 40
CELL = 2.0                            # the lattice: 20 x 20
GW = GH = SRC_N // 2
TF = Affine(CELL, 0, X0, 0, -CELL, Y0)
NO_REF = ["--reference", ""]          # keep the real published cache out of every CLI test


def _grid():
    return TF, GW, GH, np.ones((GH, GW), dtype=bool)


def _write_tif(path, arr):
    with rasterio.open(path, "w", driver="GTiff", width=SRC_N, height=SRC_N, count=1,
                       dtype="uint8", crs=f"EPSG:{EPSG}",
                       transform=Affine(1.0, 0, X0, 0, -1.0, Y0), nodata=255) as dst:
        dst.write(arr.astype(np.uint8), 1)


def _mask_array(seed, fill=None):
    """A 40x40 0/1/255 source. `fill` fixes the whole raster; else pseudo-random."""
    if fill is not None:
        return np.full((SRC_N, SRC_N), fill, np.uint8)
    rng = np.random.default_rng(seed)
    return rng.choice([0, 1, 255], size=(SRC_N, SRC_N), p=[0.5, 0.4, 0.1]).astype(np.uint8)


def _masks_dir(tmp_path, pairs, arrays=None):
    d = tmp_path / "masks"
    d.mkdir(exist_ok=True)
    for i, (y, t) in enumerate(pairs):
        arr = (arrays or {}).get(y, _mask_array(i))
        _write_tif(M.mask_path(d, y, t), arr)
    return d


def _grid_npz(tmp_path):
    p = tmp_path / "grid.npz"
    tf, w, h, inside = _grid()
    np.savez(p, inside=inside, transform=np.array(tf)[:6], years=np.array(["x"]),
             stack=np.zeros((1, h, w), np.uint8))
    return p


def _fingerprint(p):
    try:
        st = p.stat()
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


# ---- (a) the contract the consumers read --------------------------------------------

def test_npz_carries_the_four_consumer_keys_plus_provenance(tmp_path):
    pairs = [("2009", "trend8_2009"), ("2013", "trend8_2013"), ("2017", "heal_2017")]
    d = _masks_dir(tmp_path, pairs)
    out = tmp_path / "s.npz"
    rc = M.main(["--epochs", "2009:trend8_2009,2013:trend8_2013,2017:heal_2017",
                 "--masks-dir", str(d), "--out", str(out),
                 "--grid-from", str(_grid_npz(tmp_path))] + NO_REF)
    assert rc == 0 and out.exists()
    z = np.load(out, allow_pickle=False)
    assert set(z.files) >= {"stack", "inside", "years", "transform", "tags", "sources"}
    assert z["stack"].dtype == np.uint8 and z["stack"].shape == (3, GH, GW)
    assert set(np.unique(z["stack"])) <= {0, 1, 255}
    assert z["inside"].dtype == bool and z["inside"].shape == (GH, GW)
    assert z["years"].dtype.kind == "U" and list(z["years"]) == ["2009", "2013", "2017"]
    assert list(z["tags"]) == ["trend8_2009", "trend8_2013", "heal_2017"]
    assert list(z["sources"]) == [M.mask_path(d, y, t).name for y, t in pairs]
    assert z["transform"].shape == (6,) and np.allclose(z["transform"], np.array(TF)[:6])


def test_warp_is_the_census_majority_rule(tmp_path):
    """4 source px per cell: 3/4 -> 1, 1/4 -> 0, 2/4 -> 1 (>= 0.5), all-nodata -> 255,
    and nodata is EXCLUDED from the average rather than counted as 0."""
    src = np.zeros((SRC_N, SRC_N), np.uint8)
    src[0:2, 0:2] = [[1, 1], [1, 0]]              # cell (0,0): 0.75 -> 1
    src[0:2, 2:4] = [[1, 0], [0, 0]]              # cell (0,1): 0.25 -> 0
    src[0:2, 4:6] = [[1, 1], [0, 0]]              # cell (0,2): 0.50 -> 1
    src[0:2, 6:8] = 255                           # cell (0,3): no data -> 255
    src[0:2, 8:10] = [[1, 255], [255, 255]]       # cell (0,4): one valid px, 1 -> 1
    src[2:4, 0:2] = [[0, 255], [255, 255]]        # cell (1,0): one valid px, 0 -> 0
    p = tmp_path / "m.tif"
    _write_tif(p, src)
    tf, w, h, _ = _grid()
    tc = M._sibling("trend8_transition_census")
    lay = tc.warp_mask(p, tf, w, h, epsg=EPSG)
    assert lay.dtype == np.uint8 and lay.shape == (GH, GW)
    assert [int(lay[0, c]) for c in range(5)] == [1, 0, 1, 255, 1]
    assert int(lay[1, 0]) == 0
    assert int(lay[5, 5]) == 0                    # untouched background stays 0


# ---- (b) ordering ---------------------------------------------------------------------

def test_epochs_order_chronologically_with_s_labels_after_their_year():
    got = M.resolve_epochs("2013:trend8_2013,2009:trend8_2009,2011s:trend8_2011s,"
                           "2011:heal_2011,2024:trend8_2024,2017:heal_2017")
    assert [y for y, _ in got] == ["2009", "2011", "2011s", "2013", "2017", "2024"]
    assert dict(got)["2011s"] == "trend8_2011s"


def test_parse_epochs_rejects_a_bare_label():
    with pytest.raises(ValueError):
        M.parse_epochs("2009:trend8_2009,2017")


# ---- (c) discovery and the duplicate-year refusal ------------------------------------

def test_discovery_finds_campaign_masks_and_ignores_their_siblings(tmp_path):
    d = tmp_path / "masks"
    d.mkdir()
    for name in ("edmonds_canopy_mask_2017_heal_2017.tif",
                 "edmonds_canopy_mask_2020_heal_2020.tif",
                 "edmonds_canopy_mask_2017_heal_2017.gpkg",       # vector twin
                 "edmonds_canopy_prob_2017_heal_2017.tif",        # probability raster
                 "edmonds_canopy_mask_2017_heal_2017b.tif",       # tag != label
                 "edmonds_canopy_mask_2009_trend8_2009.tif"):
        (d / name).write_bytes(b"")
    assert M.discover_heal(d) == [("2017", "heal_2017"), ("2020", "heal_2020")]
    got = M.resolve_epochs(None, d)
    assert [y for y, _ in got] == ["2009", "2011s", "2013", "2015", "2016", "2017",
                                   "2019", "2020", "2021", "2024"]
    assert dict(got)["2017"] == "heal_2017" and dict(got)["2019"] == "trend8_2019"


def test_a_heal_epoch_on_a_trend8_year_is_refused_by_name(tmp_path):
    d = tmp_path / "masks"
    d.mkdir()
    (d / "edmonds_canopy_mask_2019_heal_2019.tif").write_bytes(b"")
    with pytest.raises(ValueError) as e:
        M.resolve_epochs(None, d)
    assert "2019" in str(e.value) and "trend8_2019" in str(e.value)
    out = tmp_path / "s.npz"
    rc = M.main(["--masks-dir", str(d), "--out", str(out), "--dry-run"] + NO_REF)
    assert rc == 2 and not out.exists()


def test_duplicate_labels_in_an_override_are_refused():
    with pytest.raises(ValueError):
        M.resolve_epochs("2009:trend8_2009,2009:heal_2009")


# ---- (d) THE HARD GATE fires ---------------------------------------------------------

def test_refuses_to_write_the_published_cache_name_even_with_force(tmp_path):
    """Pre-seed bytes under the forbidden name, ask for it with and without --force, and
    show exit 2 with the bytes unchanged. The real cache is fingerprinted too."""
    pairs = [("2009", "trend8_2009"), ("2013", "trend8_2013"), ("2017", "heal_2017")]
    d = _masks_dir(tmp_path, pairs)
    forbidden = tmp_path / "trend8_stack_2m.npz"
    forbidden.write_bytes(b"published-eight-epoch-cache")
    real_before = _fingerprint(M.PUBLISHED_CACHE)
    for extra in ([], ["--force"]):
        rc = M.main(["--epochs", "2009:trend8_2009,2013:trend8_2013,2017:heal_2017",
                     "--masks-dir", str(d), "--out", str(forbidden),
                     "--grid-from", str(_grid_npz(tmp_path))] + NO_REF + extra)
        assert rc == 2, "the name gate did not fire"
        assert forbidden.read_bytes() == b"published-eight-epoch-cache"
    assert M.refuse_name(Path("TREND8_STACK_2M.NPZ"))
    assert not M.refuse_name(Path("heal_stack_2m.npz"))
    assert _fingerprint(M.PUBLISHED_CACHE) == real_before


# ---- (e) --dry-run writes nothing ----------------------------------------------------

def test_dry_run_prints_the_table_and_writes_nothing(tmp_path, capsys):
    d = _masks_dir(tmp_path, [("2009", "trend8_2009")])
    out = tmp_path / "s.npz"
    rc = M.main(["--epochs", "2009:trend8_2009,2017:heal_2017", "--masks-dir", str(d),
                 "--out", str(out), "--dry-run"] + NO_REF)
    assert rc == 0 and not out.exists()
    txt = capsys.readouterr().out
    assert "DRY RUN" in txt and "2 epochs" in txt
    lines = [ln for ln in txt.splitlines() if "trend8_2009" in ln or "heal_2017" in ln]
    assert any("True" in ln for ln in lines if "trend8_2009" in ln)
    assert any("False" in ln for ln in lines if "heal_2017" in ln)


def test_a_missing_mask_is_fatal_not_skipped(tmp_path):
    d = _masks_dir(tmp_path, [("2009", "trend8_2009")])
    out = tmp_path / "s.npz"
    rc = M.main(["--epochs", "2009:trend8_2009,2017:heal_2017", "--masks-dir", str(d),
                 "--out", str(out), "--grid-from", str(_grid_npz(tmp_path))] + NO_REF)
    assert rc == 2 and not out.exists()


# ---- (f) --force ---------------------------------------------------------------------

def test_existing_out_needs_force(tmp_path):
    pairs = [("2009", "trend8_2009"), ("2013", "trend8_2013")]
    d = _masks_dir(tmp_path, pairs)
    out = tmp_path / "s.npz"
    base = ["--masks-dir", str(d), "--out", str(out),
            "--grid-from", str(_grid_npz(tmp_path))] + NO_REF
    assert M.main(["--epochs", "2009:trend8_2009"] + base) == 0
    first = out.read_bytes()
    assert M.main(["--epochs", "2009:trend8_2009,2013:trend8_2013"] + base) == 2
    assert out.read_bytes() == first, "an existing stack was overwritten without --force"
    assert M.main(["--epochs", "2009:trend8_2009,2013:trend8_2013", "--force"] + base) == 0
    assert list(np.load(out)["years"]) == ["2009", "2013"]


# ---- the parity gate fires ------------------------------------------------------------

def test_parity_gate_fires_when_a_shared_epoch_differs(tmp_path):
    pairs = [("2009", "trend8_2009"), ("2013", "trend8_2013")]
    d = _masks_dir(tmp_path, pairs)
    arrays = M.build(pairs, d, _grid(), log=lambda *_: None)

    same = tmp_path / "ref_same.npz"
    np.savez(same, **arrays)
    assert M.parity(arrays, same) == (2, [], "")

    diff = tmp_path / "ref_diff.npz"
    mutated = dict(arrays)
    mutated["stack"] = arrays["stack"].copy()
    mutated["stack"][1, 3, 3] = 1 - int(mutated["stack"][1, 3, 3] == 1)
    np.savez(diff, **mutated)
    n, bad, note = M.parity(arrays, diff)
    assert (n, bad) == (2, ["2013"]) and note == ""

    out = tmp_path / "s.npz"
    base = ["--epochs", "2009:trend8_2009,2013:trend8_2013", "--masks-dir", str(d),
            "--out", str(out), "--grid-from", str(_grid_npz(tmp_path))]
    assert M.main(base + ["--reference", str(diff)]) == 3
    assert M.main(base + ["--reference", str(same), "--force"]) == 0


def test_parity_reports_a_lattice_mismatch_rather_than_indexing_into_it(tmp_path):
    pairs = [("2009", "trend8_2009")]
    d = _masks_dir(tmp_path, pairs)
    arrays = M.build(pairs, d, _grid(), log=lambda *_: None)
    other = dict(arrays)
    other["stack"] = np.zeros((1, GH + 1, GW), np.uint8)
    other["inside"] = np.ones((GH + 1, GW), bool)
    ref = tmp_path / "ref.npz"
    np.savez(ref, **other)
    n, bad, note = M.parity(arrays, ref)
    assert bad == ["2009"] and note == "lattice differs"


# ---- defaults are the published locations, and not the forbidden one -----------------

def test_defaults_point_beside_the_published_cache_never_at_it():
    a = M._parser().parse_args([])
    assert a.out == str(M.DEFAULT_OUT)
    assert Path(a.out).name != M.FORBIDDEN_NAME
    assert Path(a.out).parent == M.PUBLISHED_CACHE.parent
    assert a.reference == str(M.PUBLISHED_CACHE)
    assert M.PUBLISHED_CACHE.name == M.FORBIDDEN_NAME
    assert not a.dry_run and not a.force and a.epochs is None and a.grid_from is None

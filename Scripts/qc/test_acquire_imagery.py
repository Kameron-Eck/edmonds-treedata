"""Offline tests for pipeline/acquire_imagery.py (no network): an injected fetcher serves windows of a
synthetic 4-band GeoTIFF exactly as an ArcGIS exportImage would, with failure injection.
Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_acquire_imagery.py -q
"""
import hashlib, io, json, sys
from pathlib import Path
import numpy as np, pytest, rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acquire_imagery as ai
import imagery_measure as im

EPSG, PX = 2285, 1.0
OX, OY = 1254000.0, 320000.0          # synthetic service lattice origin (xmin / ymax)
W, H = 700, 530                        # synthetic source size in px


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    rng = np.random.default_rng(7)
    base = rng.integers(0, 256, size=(4, H, W), dtype=np.uint8)
    base[3] = (rng.random((H, W)) * 120 + 100).astype(np.uint8)          # a varying "NIR"
    p = tmp_path_factory.mktemp("src") / "src.tif"
    with rasterio.open(p, "w", driver="GTiff", width=W, height=H, count=4, dtype="uint8", crs=f"EPSG:{EPSG}",
                       transform=from_origin(OX, OY, PX, PX)) as ds:
        ds.write(base)
    return p, base


def make_fetcher(source_path, fail: dict | None = None):
    """fail = {"truncate_once": key, "http500_once": key, "bands": 3, "never": key}"""
    fail = dict(fail or {}); seen = {}

    def fetcher(params):
        x0, y0, x1, y1 = map(float, params["bbox"].split(","))
        w, h = map(int, params["size"].split(","))
        with rasterio.open(source_path) as src:
            win = rasterio.windows.from_bounds(x0, y0, x1, y1, transform=src.transform).round_offsets().round_lengths()
            arr = src.read(window=win)
            tr = src.window_transform(win)
        key = f"{x0:.0f}_{y1:.0f}"
        if fail.get("bands"):
            arr = arr[: fail["bands"]]
        with MemoryFile() as mf:
            with mf.open(driver="GTiff", width=w, height=h, count=arr.shape[0], dtype="uint8", crs=f"EPSG:{EPSG}", transform=tr) as ds:
                ds.write(arr)
            body = mf.read()
        n = seen.get(key, 0); seen[key] = n + 1
        if fail.get("never") == key:
            return 500, {"content-type": "text/plain", "content-length": "5"}, b"error"
        if fail.get("http500_once") == key and n == 0:
            return 500, {"content-type": "text/html"}, b"<html>busy</html>"
        if fail.get("truncate_once") == key and n == 0:
            return 200, {"content-type": "image/tiff", "content-length": str(len(body))}, body[: len(body) // 2]
        return 200, {"content-type": "image/tiff", "content-length": str(len(body))}, body
    return fetcher


def gs_for(bands=4, core=128, ov=16):
    x0, y1, w, h = ai.snap_grid((OX + 100.4, OY - 400.6, OX + 500.2, OY - 80.3), PX, OX, OY)
    return {"x0": x0, "y1": y1, "px": PX, "W": w, "H": h, "core_w": core, "core_h": core, "overlap": ov, "epsg": EPSG,
            "bands": bands, "pixel_type": "U8", "compression": None, "rendering": "default",
            "profile": {"max_retry": 3, "backoff_base": 1.0, "backoff_cap": 0.01, "timeout": 5, "cooldown": 0}}


def test_snap_grid_is_on_lattice():
    x0, y1, w, h = ai.snap_grid((OX + 100.4, OY - 400.6, OX + 500.2, OY - 80.3), PX, OX, OY)
    assert (x0 - OX) % PX == 0 and (OY - y1) % PX == 0
    assert x0 <= OX + 100.4 and x0 + w * PX >= OX + 500.2 and y1 >= OY - 80.3 and y1 - h * PX <= OY - 400.6


def test_build_grid_counts_and_clipping():
    g = ai.build_grid(1000, 530, 256, 256, 32)
    assert len(g) == 4 * 3
    last = g[-1]
    assert last.c0 + last.w == 1000 and last.r0 + last.h == 530
    assert last.rc0 == last.c0 - 32 and last.rc0 + last.rw == 1000     # overlap clipped at the grid edge
    assert g[0].rc0 == 0 and g[0].rr0 == 0 and g[0].rw == 256 + 32


def test_four_corner_bbox_is_envelope():
    m = {"extent_3857": [-13625876.424, 6068463.621, -13614805.955, 6084271.153]}
    b = ai.study_bbox(m, 2285)
    assert b[0] < 1254400 and b[2] > 1279400 and b[1] < 283900 and b[3] > 319100   # measured envelope 1254356..1279472 x 283859..319118


def test_fetch_and_assemble_byte_equal(source, tmp_path):
    src, base = source
    gs = gs_for(); grid = ai.build_grid(gs["W"], gs["H"], gs["core_w"], gs["core_h"], gs["overlap"])
    lim = ai.RateLimiter(0); cd = tmp_path / "chunks"
    recs = [ai.fetch_chunk("http://x", gs, c, gs["profile"], lim, cd / f"{c.key}.tif", fetcher=make_fetcher(src)) for c in grid]
    assert all(r["status"] == "ok" for r in recs) and all(r["attempts"] == 1 for r in recs)
    # stitch the cores and compare to the source window
    out = np.zeros((4, gs["H"], gs["W"]), dtype=np.uint8)
    for c in grid:
        with rasterio.open(cd / f"{c.key}.tif") as s:
            out[:, c.r0:c.r0 + c.h, c.c0:c.c0 + c.w] = s.read()
    c0 = int((gs["x0"] - OX) / PX); r0 = int((OY - gs["y1"]) / PX)
    assert np.array_equal(out, base[:, r0:r0 + gs["H"], c0:c0 + gs["W"]])
    rep = ai.gap_report(grid, recs, cd)
    assert rep["ok"] == len(grid) and not rep["failed"]


def test_truncated_then_ok(source, tmp_path):
    src, _ = source
    gs = gs_for(); grid = ai.build_grid(gs["W"], gs["H"], gs["core_w"], gs["core_h"], gs["overlap"])
    c = grid[0]; p, bbox = ai.export_params(gs, c); key = f"{bbox[0]:.0f}_{bbox[3]:.0f}"
    r = ai.fetch_chunk("http://x", gs, c, gs["profile"], ai.RateLimiter(0), tmp_path / "c.tif", fetcher=make_fetcher(src, {"truncate_once": key}))
    assert r["status"] == "ok" and r["attempts"] == 2


def test_http500_then_ok(source, tmp_path):
    src, _ = source
    gs = gs_for(); c = ai.build_grid(gs["W"], gs["H"], gs["core_w"], gs["core_h"], gs["overlap"])[0]
    p, bbox = ai.export_params(gs, c); key = f"{bbox[0]:.0f}_{bbox[3]:.0f}"
    r = ai.fetch_chunk("http://x", gs, c, gs["profile"], ai.RateLimiter(0), tmp_path / "c.tif", fetcher=make_fetcher(src, {"http500_once": key}))
    assert r["status"] == "ok" and r["attempts"] == 2


def test_never_succeeds_is_reported_not_hidden(source, tmp_path):
    src, _ = source
    gs = gs_for(); grid = ai.build_grid(gs["W"], gs["H"], gs["core_w"], gs["core_h"], gs["overlap"])
    c = grid[3]; p, bbox = ai.export_params(gs, c); key = f"{bbox[0]:.0f}_{bbox[3]:.0f}"
    cd = tmp_path / "chunks"
    recs = [ai.fetch_chunk("http://x", gs, ch, gs["profile"], ai.RateLimiter(0), cd / f"{ch.key}.tif", fetcher=make_fetcher(src, {"never": key})) for ch in grid]
    rep = ai.gap_report(grid, recs, cd)
    assert len(rep["failed"]) == 1 and rep["failed"][0]["key"] == c.key and rep["failed"][0]["attempts"] == 3
    assert not (cd / f"{c.key}.tif").exists()


def test_fewer_bands_is_fatal(source, tmp_path):
    src, _ = source
    gs = gs_for(bands=4); c = ai.build_grid(gs["W"], gs["H"], gs["core_w"], gs["core_h"], gs["overlap"])[0]
    with pytest.raises(ai.Fatal):
        ai.fetch_chunk("http://x", gs, c, gs["profile"], ai.RateLimiter(0), tmp_path / "c.tif", fetcher=make_fetcher(src, {"bands": 3}))


def test_band_verdict_alpha_vs_nir():
    rng = np.random.default_rng(1)
    rgb = rng.integers(0, 256, size=(3, 256, 256), dtype=np.uint8)
    alpha = np.concatenate([rgb, np.full((1, 256, 256), 255, np.uint8)])
    assert im.band_verdict_array(alpha)["band4"]["verdict"] == "ALPHA"
    nir = np.concatenate([rgb, (rng.random((1, 256, 256)) * 150 + 100).astype(np.uint8)])
    assert im.band_verdict_array(nir)["band4"]["verdict"] == "NIR"


def test_jpeg_block_score_detects_block_grid():
    rng = np.random.default_rng(3)
    smooth = rng.normal(0, 1, (256, 256)).cumsum(axis=1).cumsum(axis=0); smooth = ((smooth - smooth.min()) / np.ptp(smooth) * 255).astype(np.float32)
    assert not im.jpeg_block_score(smooth)["signature"]
    # JPEG quantisation: each 8x8 block gets its own DC offset -> steps only AT block boundaries
    offs = rng.normal(0, 6, (32, 32)).repeat(8, axis=0).repeat(8, axis=1)
    blocky = smooth + offs
    assert im.jpeg_block_score(blocky)["signature"]


def test_manifest_both_formats(tmp_path):
    import mirror_sync
    d = tmp_path / "m"; d.mkdir(); (d / "a.bin").write_bytes(b"hello"); (d / "b.bin").write_bytes(b"world!")
    mirror_sync.write_manifest(d)
    assert mirror_sync.verify(d, sizes_only=False) == 0
    # sha256sum form must parse (size check skipped) and verify
    sha = hashlib.sha256(b"hello").hexdigest()
    (d / "MANIFEST.sha256").write_text(f"{sha}  a.bin\n", encoding="utf-8")
    assert mirror_sync.verify(d) == 0
    (d / "a.bin").write_bytes(b"HELLO")
    assert mirror_sync.verify(d) == 1


def test_decide_replace_vs_complement():
    t = {"id": "S16", "replaces": "old.tif", "licence": "ASK", "test": {"coverage_min_pct": 99, "nir": "required", "effective_max_cm": 38.9}}
    meas = {"bands": 4, "study_coverage_pct": 99.5, "effective_cm": 33.0, "band_verdict": {"band4": {"verdict": "NIR"}}, "jpeg_block": {"signature": False},
            "registration": {"blue_vs_green_px": 0.05},
            "held": {"bands": 4, "study_coverage_pct": 53.4, "effective_cm": 35.4, "jpeg_block": {"signature": False}, "registration": {"blue_vs_green_px": 0.22}}}
    assert im.decide(t, meas)["verdict"] == "REPLACE"
    meas2 = dict(meas, band_verdict={"band4": {"verdict": "ALPHA"}})
    assert im.decide(t, meas2)["verdict"] == "REJECT"
    # softer on a common grid (HF ratio < 0.9) is a loss -> COMPLEMENT even though coverage wins
    meas3 = dict(meas, compare_to_held={"hf_ratio_new_over_held": 0.8, "effective_cm_common_new": 45.0, "effective_cm_common_held": 35.0})
    assert im.decide(dict(t, test={}), meas3)["verdict"] == "COMPLEMENT"
    # the S16 pilot case: native-grid rise reads worse (41 vs 34) but the common grid says sharper -> still REPLACE
    meas4 = dict(meas, effective_cm=41.1, compare_to_held={"hf_ratio_new_over_held": 1.18, "effective_cm_common_new": 33.0, "effective_cm_common_held": 34.0})
    assert im.decide(t, meas4)["verdict"] == "REPLACE"

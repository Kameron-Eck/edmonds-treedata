"""litkb formula shards, the Colab worker's packing rules, and the local ingest's refusals.

Report: Reports/LITKB_COLAB_L4_FORMULA_2026-09-15.md. Design constraint:
decisions.yaml::litkb-p0-foundation — the corpus stays local, so what crosses to Colab is
page-region PNG crops of equation regions and a manifest, never a PDF.

  gate                                          test                                   kill
  a corrupted result archive is refused         test_ingest_accepts_a_good_archive     test_kill_a_corrupted_archive_is_refused
  a result with no done marker is refused       "                                      test_kill_a_missing_done_marker_is_refused
  a tampered done marker is refused             "                                      test_kill_a_tampered_done_marker_is_refused
  the crop set must match the shard             "                                      test_kill_a_short_result_is_refused
  empty LaTeX is never an enriched region       test_empty_latex_is_recorded_failed    test_kill_empty_latex_claimed_ok_is_refused
  a shard already ingested is skipped           test_kill_a_reuploaded_shard_is_skipped_by_sha256
  a shard carries crops ONLY                    test_a_shard_contains_only_crops_and_a_manifest
  server-side md5 is what is trusted            test_kill_a_stale_local_copy_is_refused

WHICH KILLS FIRED ON REAL DATA, said plainly (CLAUDE.md §3.4c). The archive-level kills here
fire against archives built by the REAL worker packing code (`process_shard`'s writer and
`done_marker`), then damaged — that is real bytes, not a mock. The EMPTY-LATEX kill is
different: making CodeFormula return an empty string on purpose needs the model, so the
worker-side half of it is exercised with a stub engine and is **UNVALIDATED on real data
here**. It is not unvalidated in the project: the same fail-closed rule, one level up, was
fired on a real CUDA out-of-memory in Reports/LITKB_DOCLING_A_REFEREE_2026-09-15.md §4,
where docling reported SUCCESS and returned empty strings for all five regions.
"""
import json
import os
import zipfile

import pytest

from litkb.extract import formula_shards as fs
from litkb.extract.colab_formula_worker import (DONE_NAME, RESULTS_NAME, WORKER_NAME,
                                                done_marker, process_shard)
from litkb.extract.formula_ingest import (ResultRefused, ingest, ingested_shard_hashes,
                                          verify_result)

PNG = {}


def _png(seed):
    """A tiny but REAL png. Kept deterministic so the crop id is the content hash."""
    if seed in PNG:
        return PNG[seed]
    import struct
    import zlib
    w = h = 4
    raw = b"".join(b"\x00" + bytes([(seed + x) % 256] * 3 * w) for _ in range(h) for x in [0])

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))
    PNG[seed] = body
    return body


@pytest.fixture()
def shard(tmp_path):
    """A real shard archive, packed by the real packer, over three synthetic crops."""
    crop_dir = tmp_path / "crops"
    crop_dir.mkdir()
    crops = []
    for i in range(3):
        png = _png(i)
        cid = fs.sha256_bytes(png)
        (crop_dir / (cid + ".png")).write_bytes(png)
        crops.append({"crop_id": cid, "file": "Paper_1999.pdf", "file_sha256": "f" * 64,
                      "page": 3 + i, "self_ref": f"#/texts/{i}", "label": "formula",
                      "native_text": "ðxÞ", "bbox_raw": {"l": 1, "t": 9, "r": 5, "b": 2,
                                                         "coord_origin": "BOTTOMLEFT"},
                      "page_height": 10.0, "bbox_canonical": [1.0, 1.0, 5.0, 8.0],
                      "png_bytes": len(png), "width": 4, "height": 4})
    z = str(tmp_path / "shard_t.zip")
    man = fs.write_shard(crops, str(crop_dir), z, shard_id="t")
    return z, man


class _StubModel:
    """Stands in for CodeFormulaVlmModel: returns whatever it is told, in order."""

    def __init__(self, outputs):
        self.outputs = list(outputs)

    def __call__(self, doc, els):
        for el in els:
            el.item.text = self.outputs.pop(0)
            yield el.item


def _run(shard_zip, out_zip, outputs, monkeypatch):
    from litkb.extract import colab_formula_worker as cw
    monkeypatch.setattr(cw, "decode_batch",
                        lambda model, images: [outputs.pop(0) for _ in images])
    monkeypatch.setattr(cw, "_vram", lambda: {})
    return process_shard(shard_zip, out_zip, device="cpu", batch_size=2,
                         _model=(_StubModel([]), 5))


# ── the shard ───────────────────────────────────────────────────────────────────────────

def test_a_shard_contains_only_crops_and_a_manifest(shard):
    z, man = shard
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert names[0] == "manifest.json"           # written first, so it streams first
    assert all(n.startswith("crops/") and n.endswith(".png") for n in names[1:])
    # The constraint, asserted rather than trusted: nothing in a shard is a PDF or a page.
    assert not any(n.lower().endswith(".pdf") for n in names)
    assert man["n_crops"] == 3
    assert man["shard_sha256"] == fs.sha256_file(z)


def test_every_crop_id_is_the_sha256_of_its_own_bytes(shard):
    z, man = shard
    with zipfile.ZipFile(z) as zf:
        for cid in man["crop_ids"]:
            assert fs.sha256_bytes(zf.read("crops/" + cid + ".png")) == cid


def test_packing_is_deterministic(tmp_path, shard):
    z, man = shard
    again = str(tmp_path / "again.zip")
    man2 = fs.write_shard(man["crops"], str(tmp_path / "crops"), again, shard_id="t")
    # The created_utc differs by design; the ARCHIVE of crops must not.
    with zipfile.ZipFile(z) as a, zipfile.ZipFile(again) as b:
        assert {n: a.read(n) for n in a.namelist() if n != "manifest.json"} == \
               {n: b.read(n) for n in b.namelist() if n != "manifest.json"}
    assert man2["crop_ids"] == man["crop_ids"]


def test_kill_a_packed_crop_whose_bytes_moved_is_refused(tmp_path, shard):
    _, man = shard
    crop_dir = tmp_path / "crops"
    p = crop_dir / (man["crop_ids"][0] + ".png")
    p.write_bytes(_png(99))                      # same name, different bytes
    with pytest.raises(ValueError, match="does not hash to its id"):
        fs.write_shard(man["crops"], str(crop_dir), str(tmp_path / "bad.zip"))


def test_plan_shards_skips_what_is_already_done(shard):
    _, man = shard
    assert len(fs.plan_shards(man["crops"], size=2)) == 2
    assert fs.plan_shards(man["crops"], done_ids=man["crop_ids"]) == []


# ── the worker's fail-closed rule ───────────────────────────────────────────────────────

def test_empty_latex_is_recorded_failed(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    rec = _run(z, out, ["x^2", "", "y_1"], monkeypatch)
    with zipfile.ZipFile(out) as zf:
        rows = [json.loads(ln) for ln in zf.read(RESULTS_NAME).decode().splitlines()]
    by = {r["crop_id"]: r for r in rows}
    bad = [r for r in rows if r["status"] == "failed"]
    assert rec["ok"] == 2 and rec["failed"] == 1
    assert len(bad) == 1 and bad[0]["latex"] is None and bad[0]["error"]
    # never an empty string sitting in a latex field as though it were a decode
    assert all(r["latex"] is None or r["latex"].strip() for r in by.values())


def test_confidence_is_null_with_its_reason(tmp_path, shard, monkeypatch):
    z, _ = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    with zipfile.ZipFile(out) as zf:
        rows = [json.loads(ln) for ln in zf.read(RESULTS_NAME).decode().splitlines()]
    assert all(r["confidence"] is None for r in rows)
    assert all("reads only output.text" in r["confidence_basis"] for r in rows)


def test_the_done_marker_is_written_last(tmp_path, shard, monkeypatch):
    z, _ = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist()[-1] == DONE_NAME


# ── the ingest's refusals ───────────────────────────────────────────────────────────────

def test_ingest_accepts_a_good_archive(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["x^2", "y", "z"], monkeypatch)
    metrics = str(tmp_path / "m.jsonl")
    latex = str(tmp_path / "latex.jsonl")
    row = ingest(out, man, metrics, latex)
    assert row["latex_rows_written"] == 3
    rows = [json.loads(ln) for ln in open(latex, encoding="utf-8")]
    assert {r["latex"] for r in rows} == {"x^2", "y", "z"}
    # the join key merge_formula_latex uses travels with the LaTeX
    assert all(r["bbox_canonical"] == [1.0, 1.0, 5.0, 8.0] for r in rows)
    assert all(r["self_ref"] and r["page"] for r in rows)
    assert ingested_shard_hashes(metrics) == {man["shard_sha256"]}


def test_kill_a_corrupted_archive_is_refused(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    data = bytearray(open(out, "rb").read())
    data[len(data) // 2] ^= 0xFF                 # one flipped byte in the middle
    open(out, "wb").write(bytes(data))
    with pytest.raises(ResultRefused, match="corrupt or truncated"):
        verify_result(out, man)


def test_kill_a_truncated_archive_with_no_sidecar_is_refused(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    os.remove(out + ".sha256")                   # no hash to compare against
    data = open(out, "rb").read()
    open(out, "wb").write(data[:len(data) // 2])
    with pytest.raises(ResultRefused):           # zipfile itself refuses it
        verify_result(out, man)


def test_kill_a_missing_done_marker_is_refused(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    repacked = str(tmp_path / "nodone.zip")
    with zipfile.ZipFile(out) as src, zipfile.ZipFile(repacked, "w") as dst:
        for n in src.namelist():
            if n != DONE_NAME:
                dst.writestr(n, src.read(n))
    with pytest.raises(ResultRefused, match="no DONE marker"):
        verify_result(repacked, man)


def test_kill_a_tampered_done_marker_is_refused(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    repacked = str(tmp_path / "tampered.zip")
    with zipfile.ZipFile(out) as src, zipfile.ZipFile(repacked, "w") as dst:
        rows = src.read(RESULTS_NAME).replace(b'"a"', b'"NOT a"')
        dst.writestr(RESULTS_NAME, rows)         # members changed, marker not recomputed
        dst.writestr(WORKER_NAME, src.read(WORKER_NAME))
        dst.writestr(DONE_NAME, src.read(DONE_NAME))
    with pytest.raises(ResultRefused, match="does not match the members"):
        verify_result(repacked, man)


def test_kill_a_short_result_is_refused(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    short = str(tmp_path / "short.zip")
    with zipfile.ZipFile(out) as src:
        rows = src.read(RESULTS_NAME).splitlines()[:2]
        rb = b"\n".join(rows) + b"\n"
        wb = src.read(WORKER_NAME)
    with zipfile.ZipFile(short, "w") as dst:
        dst.writestr(RESULTS_NAME, rb)
        dst.writestr(WORKER_NAME, wb)
        dst.writestr(DONE_NAME, done_marker(rb, wb))   # a CONSISTENT but incomplete archive
    with pytest.raises(ResultRefused, match="2 crops returned against 3"):
        verify_result(short, man)


def test_kill_empty_latex_claimed_ok_is_refused(tmp_path, shard, monkeypatch):
    """The belt to the worker's suspenders: a forged ok row with no LaTeX fails ingest."""
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    forged = str(tmp_path / "forged.zip")
    with zipfile.ZipFile(out) as src:
        rows = [json.loads(ln) for ln in src.read(RESULTS_NAME).decode().splitlines()]
        wb = src.read(WORKER_NAME)
    rows[1]["latex"] = ""
    rb = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode()
    with zipfile.ZipFile(forged, "w") as dst:
        dst.writestr(RESULTS_NAME, rb)
        dst.writestr(WORKER_NAME, wb)
        dst.writestr(DONE_NAME, done_marker(rb, wb))
    with pytest.raises(ResultRefused, match="claim status=ok with no LaTeX"):
        verify_result(forged, man)


def test_kill_a_reuploaded_shard_is_skipped_by_sha256(tmp_path, shard, monkeypatch):
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    metrics, latex = str(tmp_path / "m.jsonl"), str(tmp_path / "l.jsonl")
    ingest(out, man, metrics, latex)
    n = sum(1 for _ in open(latex, encoding="utf-8"))
    again = ingest(out, man, metrics, latex, seen_shards=ingested_shard_hashes(metrics))
    assert again["status"] == "skipped"
    assert sum(1 for _ in open(latex, encoding="utf-8")) == n      # nothing written twice


def test_kill_a_stale_local_copy_is_refused(tmp_path, shard, monkeypatch):
    """Server-side md5 is what is trusted — a local FUSE read proves nothing about Drive."""
    z, man = shard
    out = str(tmp_path / "r.zip")
    _run(z, out, ["a", "b", "c"], monkeypatch)
    from litkb.extract import formula_ingest as fi
    monkeypatch.setattr(fi, "server_md5", lambda remote, rclone="rclone": "0" * 32)
    with pytest.raises(ResultRefused, match="server-side md5"):
        verify_result(out, man, remote="treedata-sa:phase4/x.zip")
    monkeypatch.setattr(fi, "server_md5", lambda remote, rclone="rclone": None)
    with pytest.raises(ResultRefused, match="no server-side md5"):
        verify_result(out, man, remote="treedata-sa:phase4/x.zip")

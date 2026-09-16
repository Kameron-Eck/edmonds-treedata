"""The three guards P5's bulk driver adds, each pinned by a test that FAILS without it.

`qc/instruments/litkb_p5_bulk.py` is the only place these three live, and none of them is
covered by `litkb_p2_mutations.py`: that harness enumerates call sites under
`Scripts/pipeline/litkb`, and an instrument under `qc/instruments/` is outside its reach.
So the guards get tests here instead, written the way a mutation row would be — each one
states the mutation it would apply and asserts the behaviour that mutation destroys.

1. **`load_latex` admits `ok` rows only.** The L4 full pass held **323 rows** (132 `unstable`,
   191 `degenerate`) out of the LaTeX corpus deliberately: an `unstable` row is a decode that
   did not reproduce and a `degenerate` one is a repetition loop. Delete the status filter and
   both land in `equations.latex`, where a reader takes them for the equation. Nothing else
   would notice — the join succeeds, the counts go UP, and the report reads better.

2. **`attach_latex` shifts the formula box by the page's cropbox offset.** `bbox_canonical` is
   in the CROPBOX frame; a canonical block has been through `to_mediabox`. Measured on
   `Conley_1999` (shift 40, 37): 138 of 138 attach with the shift and **0 of 138** without it.
   This test is the fixture version of that measurement, so the pin does not need the corpus.

3. **`_artifact_ok` is what makes "resumable" checkable** — §14 P5 kill (b), an artifact whose
   bytes no longer match the sha256 recorded beside them. Without it a half-written TEI or
   DoclingDocument is silently reused as a finished one.

Nothing here touches the database, the lake, `Literture\\`, or the real derived directory.
"""
import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def p5():
    """The driver by path. It imports `litkb.extract.*`, which needs `pipeline` importable —
    the instrument's own path bootstrap, ledgered in `test_status_discovery.py`, does that.

    (That ledger greps for the call's SPELLING, so this docstring must not write it out: a
    mention in prose would put this file on a list of files that insert a path, which it is
    not. The ladder caught exactly that, 2026-09-16.)"""
    spec = importlib.util.spec_from_file_location(
        "litkb_p5_bulk", SCRIPTS / "qc" / "instruments" / "litkb_p5_bulk.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows(tmp_path, *rows):
    p = tmp_path / "latex.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _eq_block(p5, page, box, frame="mediabox"):
    return p5.R.Canonical(page=page, x0=box[0], y0=box[1], x1=box[2], y1=box[3],
                          kind="equation", reading_order=1, text="", latex=None,
                          frame=frame)


# ── guard 1: `ok` rows only ────────────────────────────────────────────────────────────────

def test_a_held_row_never_reaches_the_latex_corpus(p5, tmp_path):
    """MUTATION: drop the `status` filter in `load_latex`.

    The two held rows carry a bbox that WOULD match — that is the point. If the filter is the
    only thing keeping them out, removing it puts a decode that did not reproduce, and a
    repetition loop, into `equations.latex`.
    """
    good = {"file_sha256": "a" * 64, "page": 1, "bbox_canonical": [10, 10, 100, 40],
            "latex": "x^2", "status": "ok", "crop_id": "g"}
    unstable = {"file_sha256": "a" * 64, "page": 1, "bbox_canonical": [10, 60, 100, 90],
                "latex": "y^2", "latex_redecode": "y^3", "status": "unstable", "crop_id": "u"}
    degenerate = {"file_sha256": "a" * 64, "page": 1, "bbox_canonical": [10, 110, 100, 140],
                  "latex": " \\, \\, \\, \\, \\,", "status": "degenerate", "crop_id": "d"}
    path = _rows(tmp_path, good, unstable, degenerate)
    verify = tmp_path / "verify.jsonl"
    verify.write_text(json.dumps(unstable) + "\n" + json.dumps(degenerate) + "\n",
                      encoding="utf-8")

    ok, held = p5.load_latex(path=str(path), verify=str(verify))
    assert [r["crop_id"] for r in ok["a" * 64]] == ["g"], \
        "a non-ok row reached the LaTeX corpus"
    assert held["a" * 64] == 2

    frames = {1: {"dx": 0.0, "dy": 0.0, "rotation": 0}}
    blocks = [_eq_block(p5, 1, b) for b in ([10, 10, 100, 40], [10, 60, 100, 90],
                                            [10, 110, 100, 140])]
    out, n, unmatched = p5.attach_latex(blocks, ok["a" * 64], frames)
    assert n == 1 and unmatched == []
    assert [b.latex for b in out] == ["x^2", None, None], \
        "the held rows' boxes match perfectly — only the status filter keeps them out"


def test_an_ok_row_with_no_latex_is_not_attached(p5, tmp_path):
    """A row the worker called `ok` with an empty string is still not text. Docling returns
    empty strings on an engine error and reports success (DOCLING_LOCAL §8.2); this is the
    belt to formula_ingest's suspenders, on the ingest side."""
    path = _rows(tmp_path, {"file_sha256": "b" * 64, "page": 1,
                            "bbox_canonical": [1, 1, 2, 2], "latex": "  ", "status": "ok"})
    ok, _ = p5.load_latex(path=str(path), verify=str(tmp_path / "absent.jsonl"))
    assert ok == {}


# ── guard 2: the cropbox shift ─────────────────────────────────────────────────────────────

def test_the_formula_box_is_shifted_into_the_blocks_frame(p5):
    """MUTATION: compare `bbox_canonical` to the block's box without adding (dx, dy).

    The fixture is `Conley_1999`'s measured shape — one uniform (40, 37) offset — at the
    sizes the real boxes have, so the failure it pins is the real one: at a 2 pt tolerance
    the unshifted comparison matches NOTHING.
    """
    dx, dy = 40.0, 37.0
    frames = {3: {"dx": dx, "dy": dy, "rotation": 0}}
    zeroed = {3: {"dx": 0.0, "dy": 0.0, "rotation": 0}}
    crop_box = [112.5, 499.0, 401.7, 677.3]
    block = _eq_block(p5, 3, [crop_box[0] + dx, crop_box[1] + dy,
                              crop_box[2] + dx, crop_box[3] + dy])
    row = {"file_sha256": "c" * 64, "page": 3, "bbox_canonical": crop_box,
           "latex": "\\int f", "status": "ok", "crop_id": "c1"}

    out, n, unmatched = p5.attach_latex([block], [row], frames)
    assert (n, out[0].latex) == (1, "\\int f")
    assert out[0].extractor["latex"] == "codeformula-l4"

    out0, n0, un0 = p5.attach_latex([block], [row], zeroed)
    assert n0 == 0 and out0[0].latex is None, \
        "the unshifted comparison matched — the cropbox shift is not doing anything"
    assert un0[0]["nearest_pt"] == pytest.approx(max(dx, dy))


def test_a_page_the_adapters_refused_is_compared_unshifted(p5):
    """A rotated page keeps `frame="cropbox"`: the block never moved, so neither may the row.
    Shifting it there would be the same bug in the opposite direction."""
    frames = {12: {"dx": 2.0, "dy": 1.0, "rotation": 2}}
    box = [50.0, 50.0, 150.0, 80.0]
    block = _eq_block(p5, 12, box, frame="cropbox")
    row = {"file_sha256": "d" * 64, "page": 12, "bbox_canonical": box,
           "latex": "\\alpha", "status": "ok", "crop_id": "r1"}
    out, n, _ = p5.attach_latex([block], [row], frames)
    assert (n, out[0].latex) == (1, "\\alpha")


def test_one_latex_row_never_claims_two_blocks(p5):
    """Greedy nearest, one-to-one: two rows over one block leave the second unmatched rather
    than overwriting the first, which is how a duplicate would enter silently."""
    frames = {1: {"dx": 0.0, "dy": 0.0, "rotation": 0}}
    block = _eq_block(p5, 1, [10.0, 10.0, 100.0, 40.0])
    rows = [{"file_sha256": "e" * 64, "page": 1, "bbox_canonical": [10, 10, 100, 40],
             "latex": "first", "status": "ok", "crop_id": "1"},
            {"file_sha256": "e" * 64, "page": 1, "bbox_canonical": [10, 10, 100, 40],
             "latex": "second", "status": "ok", "crop_id": "2"}]
    out, n, unmatched = p5.attach_latex([block], rows, frames)
    assert (n, out[0].latex, len(unmatched)) == (1, "first", 1)


# ── guard 3: the artifact sidecar — §14 P5 kill (b) ────────────────────────────────────────

def test_an_artifact_whose_bytes_moved_is_refused(p5, tmp_path):
    """MUTATION: make `_artifact_ok` return `os.path.exists(path)`.

    This is §14 P5's kill (b) — "an artifact whose bytes no longer match the job's recorded
    sha256 fails ingest verification" — at the checkpoint that decides whether a stage is
    resumed or re-run. A flipped byte is a truncated download, a killed writer, or a disk
    error, and reusing it would put a half-file's blocks in the database under an `ok` run.
    """
    art = tmp_path / "x.tei.xml"
    p5._write_atomic(str(art), b"<TEI><text>hello</text></TEI>", mode="wb")
    assert (tmp_path / "x.tei.xml.sha256").exists()
    assert p5._artifact_ok(str(art)) is True

    data = bytearray(art.read_bytes())
    data[10] ^= 0x01
    art.write_bytes(bytes(data))
    assert p5._artifact_ok(str(art)) is False, \
        "an artifact whose bytes moved was accepted as finished"


def test_an_artifact_with_no_sidecar_is_refused(p5, tmp_path):
    """The other half of the same rule: bytes on disk with nothing to check them against are
    a killed writer's leftovers, not a finished artifact."""
    art = tmp_path / "y.json"
    art.write_text("{}", encoding="utf-8")
    assert p5._artifact_ok(str(art)) is False
    (tmp_path / "y.json.sha256").write_text("", encoding="utf-8")
    assert p5._artifact_ok(str(art)) is False


def test_write_atomic_leaves_no_partial_behind(p5, tmp_path):
    """`.partial` -> fsync -> rename (CLAUDE.md §3.9), so a reader never sees a half file."""
    art = tmp_path / "z.json"
    p5._write_atomic(str(art), '{"a": 1}')
    assert not (tmp_path / "z.json.partial").exists()
    assert json.loads(art.read_text(encoding="utf-8")) == {"a": 1}
    assert p5._artifact_ok(str(art))


def test_the_ocr_batch_runs_in_short_converter_processes(p5):
    """Guard 4, added 2026-09-16: the VRAM cap that reaches the 20 % headroom rule.

    Measured over this driver's own batch B (15 documents, 312 pages, `ocr=on`, CUDA, 1 Hz
    nvidia-smi, idle 387 MiB): **3,873 MiB / 94.6 % at 15 documents in one converter process,
    2,619 MiB / 63.9 % at 4** — because torch's caching allocator never returns a block, so the
    reserved pool becomes a high-water mark over every document that process converted
    (3,344 MiB reserved; 468 MiB after an `empty_cache`). `settings.perf.page_batch_size`, the
    knob docling names for this job, is FLAT: 3,873 / 3,842 / 3,893 at 4 / 2 / 1.

    The mutation this stands against is `chunk = a.chunk` — the OCR batch back in one long
    process, at 94.6 % of a card that also drives the display. Batch A is asserted in the same
    test because capping both would cost rate for nothing: `ocr=off` peaked at 2,317 MiB /
    56.6 %, inside the rule already."""
    from litkb.extract import docling as D

    assert p5.docling_chunk(30, D.OCR_CHUNK, True) == D.OCR_CHUNK
    assert p5.docling_chunk(30, D.OCR_CHUNK, False) == 30
    # a caller asking for a SMALLER chunk than the cap still gets theirs, on both batches
    assert p5.docling_chunk(2, D.OCR_CHUNK, True) == 2
    assert p5.docling_chunk(2, D.OCR_CHUNK, False) == 2
    assert D.OCR_CHUNK < 15, "the cap must sit below the batch size that measured 94.6 %"


def test_the_canonical_block_is_replaced_not_mutated(p5):
    """`Canonical` is a frozen dataclass; `attach_latex` must return a new list and leave the
    caller's blocks alone, or a retry would re-attach onto already-attached blocks."""
    frames = {1: {"dx": 0.0, "dy": 0.0, "rotation": 0}}
    block = _eq_block(p5, 1, [10.0, 10.0, 100.0, 40.0])
    rows = [{"file_sha256": "f" * 64, "page": 1, "bbox_canonical": [10, 10, 100, 40],
             "latex": "q", "status": "ok", "crop_id": "1"}]
    out, _, _ = p5.attach_latex([block], rows, frames)
    assert dataclasses.is_dataclass(block) and block.latex is None
    assert out[0] is not block and out[0].latex == "q"

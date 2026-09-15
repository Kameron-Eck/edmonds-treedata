"""litkb stage 5 — the unified frame reader, reconciliation, and the P5 ingest.

Three groups:

* **the frame** — the one reader (design §7.1), on the three pages that used to separate the
  three copies: a CROPPED page (Alwan p2), a ROTATED and cropped page (Hall p12, which the
  adapters refuse), and a page that INHERITS its ``/MediaBox`` from the page tree, where the
  copy without the fallback died with a ``TypeError``. The corpus page for the third is real
  (``Platanios_2014``, 16 of its pages), not synthetic;
* **reconciliation** — matching, kind mapping, reading order, coverage. Pure functions on
  hand-built blocks wherever a PDF is not the thing under test, so the whole group runs on a
  machine with neither GROBID nor Docling installed;
* **ingest** — against ``litkb_test``: idempotence, the mid-file kill, the role rules and the
  new checked writers of migration 0017.
"""
import pathlib
import sys
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))  # noqa: E402

from litkb.extract import reconcile as R  # noqa: E402

from test_litkb_p1 import _PG  # noqa: E402 - the P1 harness class, not its fixture

pg_only = pytest.mark.requires_litkb_pg


@pytest.fixture(scope="session")
def _s5(litkb_pg_base):
    """Our own session fixture over the shared base, as the P2 suite does. Importing P1's `pg`
    fixture instead would shadow it in every test signature here (ruff F811)."""
    psycopg, conn, ran = litkb_pg_base
    yield _PG(psycopg, conn, ran)


@pytest.fixture
def pg(_s5):
    yield _s5
    while _s5.opened:
        _s5.opened.pop().close()

CORPUS = pathlib.Path(r"D:\edmonds-pipeline\Literture")
ALWAN = CORPUS / "Validation" / "Alwan_1988_time-series-modeling-statistical-process.pdf"
HALL = CORPUS / "Validation" / "Hall_1985_resampling-coverage-pattern.pdf"
#: The corpus's inherited-/MediaBox files. Measured 2026-09-15 by sweeping the raw pdfium
#: getter over 224 PDFs under Literture\ (excluding _quarantine): it returns 0 — no box of the
#: page's own — on **16 pages in two files**, all 10 of Platanios_2014 and 6 of Vincent_1993.
#: So this case is REAL corpus data, not a synthetic fixture: Docling's pre-unification copy
#: would have raised TypeError on every one of them.
INHERITED = CORPUS / "Validation" / "Platanios_2014_estimating-accuracy-unlabeled-data.pdf"
INHERITED_PAGES = 10
INHERITED_2 = CORPUS / "Validation" / "Vincent_1993_grayscale-area-openings-closings.pdf"

needs = pytest.mark.skipif(not ALWAN.exists(), reason="the corpus is not on this machine")


# ── the frame: one reader, three adapters ───────────────────────────────────────────────

@needs
def test_the_three_adapters_return_one_frame():
    """The unification's whole point: same dict, not merely same arithmetic."""
    pytest.importorskip("pypdfium2")
    from litkb.extract import docling as D
    from litkb.extract import grobid as G
    from litkb.extract import inventory as I

    assert G.page_frames(str(ALWAN)) == D.page_frames(str(ALWAN)) == I.page_frames(str(ALWAN))


@needs
def test_both_adapters_go_through_the_one_reader(monkeypatch):
    """A second copy re-appearing would pass the equality test above and fail this one."""
    from litkb.extract import docling as D
    from litkb.extract import grobid as G
    from litkb.extract import inventory as I

    calls = []

    def fake(path, error=None):
        calls.append(error)
        return {1: {"mediabox": [0, 0, 1, 1], "cropbox": [0, 0, 1, 1], "rotation": 0,
                    "dx": 0.0, "dy": 0.0}}

    monkeypatch.setattr(I, "page_frames", fake)
    G.page_frames("x.pdf")
    D.page_frames("x.pdf")
    assert calls == [G.GrobidError, D.DoclingError]


@needs
def test_the_cropped_page_keeps_the_referees_numbers():
    """Alwan p2's measured cropbox and shift — the numbers both referee reports quote."""
    pytest.importorskip("pypdfium2")
    from litkb.extract import grobid as G

    frames = G.page_frames(str(ALWAN))
    assert frames[1]["cropbox"] == pytest.approx(frames[1]["mediabox"], abs=0.01)
    assert frames[2]["cropbox"] == pytest.approx([10.345, 10.777, 603.441, 782.948], abs=0.01)
    assert frames[2]["dx"] == pytest.approx(10.345, abs=0.01)
    assert frames[2]["dy"] == pytest.approx(9.052, abs=0.01)


@pytest.mark.skipif(not HALL.exists(), reason="the Hall PDF is not on this machine")
def test_the_rotated_page_is_still_refused_by_both_adapters():
    """§7.1: rotation + cropbox is a REFLECTION, not this translation. Both adapters refuse."""
    pytest.importorskip("pypdfium2")
    from litkb.extract import docling as D
    from litkb.extract import grobid as G

    frames = G.page_frames(str(HALL))
    assert frames[12]["rotation"] != 0
    assert frames[12]["cropbox"] != frames[12]["mediabox"]
    for mod in (G, D):
        b = mod.Block(page=12, x0=10, y0=10, x1=20, y1=20, kind="p")
        out = mod.to_mediabox([b], frames)
        assert out[0].frame == "cropbox" and out[0].x0 == 10


@pytest.mark.skipif(not INHERITED.exists(), reason="the Platanios PDF is not on this machine")
def test_a_page_that_inherits_its_mediabox_resolves_in_every_adapter():
    """THE MUTATION TARGET. Delete the inherited-MediaBox fallback in inventory._frame and the
    raw getter's 0 becomes a None mediabox: inventory and GROBID raise their own error, and
    Docling — which before the unification had no guard at all — died with a TypeError in the
    subtraction. All 16 pages of this file are that page; it is a corpus file, not a fixture.
    """
    pytest.importorskip("pypdfium2")
    from litkb.extract import docling as D
    from litkb.extract import grobid as G
    from litkb.extract import inventory as I

    for mod in (I, G, D):
        frames = mod.page_frames(str(INHERITED))
        assert len(frames) == INHERITED_PAGES
        for page, f in frames.items():
            assert f["mediabox"] is not None, page
            assert f["mediabox"][2] > 0 and f["mediabox"][3] > 0, page
            assert f["dx"] is not None and f["dy"] is not None, page
    # the second file, so the case is not one document's quirk
    if INHERITED_2.exists():
        assert len(D.page_frames(str(INHERITED_2))) > 0


# ── matching ────────────────────────────────────────────────────────────────────────────

def _b(page, x0, y0, x1, y1, kind="p", text="", order=0):
    from litkb.extract import grobid as G

    return G.Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind=kind, text=text, frame="mediabox")


def _d(page, x0, y0, x1, y1, kind="text", text="", order=0):
    from litkb.extract import docling as D

    return D.Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind=kind, text=text,
                   frame="mediabox", order_index=order)


def test_iou_is_zero_for_disjoint_and_one_for_identical():
    assert R.iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert R.iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert R.iou((0, 0, 10, 10), (0, 0, 10, 5)) == pytest.approx(0.5)


def test_matching_is_one_to_one_and_takes_the_best_pair_first():
    left = [_b(1, 0, 0, 10, 10), _b(1, 0, 0, 10, 9)]
    right = [_d(1, 0, 0, 10, 10)]
    pairs, l_only, r_only, touching = R.match_by_iou(left, right)
    assert len(pairs) == 1 and pairs[0][0] is left[0]
    assert l_only == [left[1]] and r_only == []


def test_two_tools_boxing_the_same_paragraph_slightly_differently_still_match():
    """The threshold has to admit real agreement, not only identity. Two tools rarely put the
    same paragraph's box within a point of each other; at IoU 0.79 they still mean one region,
    and a threshold raised past that turns every matched region into two single-tool ones."""
    pairs, l_only, r_only, _ = R.match_by_iou([_b(1, 0, 0, 100, 100)], [_d(1, 5, 5, 95, 92)])
    assert len(pairs) == 1 and l_only == [] and r_only == []
    assert R.IOU_MATCH <= pairs[0][2] < 0.85


def test_a_partial_overlap_is_a_disagreement_not_a_match():
    """A paragraph one tool merges across a column and the other splits overlaps, but not
    enough to be one region. It must not be silently matched."""
    pairs, _, _, touching = R.match_by_iou([_b(1, 0, 0, 10, 10)], [_d(1, 0, 0, 10, 3)])
    assert pairs == [] and len(touching) == 1
    assert touching[0][2] < R.IOU_MATCH


def test_an_elements_per_line_boxes_are_unioned_into_one_region():
    """MEASURED: GROBID gives a `<p>` one box per LINE and Docling one prov per column
    fragment. Reading only the first box matches a paragraph's first LINE against the other
    tool's whole paragraph — on Alwan_1988 that read 8 matched regions where the union reads
    84. A page break is NOT unioned across: a box is a box on a page."""
    lines = [_b(1, 0, 0, 100, 10), _b(1, 0, 10, 100, 20), _b(1, 0, 20, 100, 30)]
    lines = [type(lines[0])(**{**vars(b), "box_index": i, "box_count": 3})
             for i, b in enumerate(lines)]
    out = R.union_boxes(lines)
    assert len(out) == 1
    assert (out[0].x0, out[0].y0, out[0].x1, out[0].y1) == (0, 0, 100, 30)

    spanning = [_b(1, 0, 700, 100, 780), _b(2, 0, 50, 100, 120)]
    spanning = [type(spanning[0])(**{**vars(b), "box_index": i, "box_count": 2})
                for i, b in enumerate(spanning)]
    assert len(R.union_boxes(spanning)) == 2


def test_pages_never_match_across_each_other():
    pairs, l_only, r_only, _ = R.match_by_iou([_b(1, 0, 0, 10, 10)], [_d(2, 0, 0, 10, 10)])
    assert pairs == [] and len(l_only) == 1 and len(r_only) == 1


# ── the kind vocabulary ─────────────────────────────────────────────────────────────────

def test_every_mapped_kind_is_a_canonical_kind():
    assert set(R.DOCLING_KIND.values()) <= set(R.KINDS)
    assert set(R.GROBID_KIND.values()) <= set(R.KINDS)
    assert set(R.DB_TYPE) == set(R.KINDS)


def test_every_db_type_is_one_migration_0002_admits():
    """The `blocks.type` CHECK is the authority; a kind that maps outside it fails at insert
    time, in the lake, instead of here."""
    allowed = {"title", "author", "affiliation", "abstract", "heading", "paragraph", "list_item",
               "footnote", "caption", "table", "figure", "equation", "reference", "page_header",
               "page_footer", "page_number", "sidebar", "other"}
    assert set(R.DB_TYPE.values()) <= allowed
    for sub in ("page_header", "page_footer", "page_number", ""):
        c = R.Canonical(page=1, x0=0, y0=0, x1=1, y1=1, kind="furniture", reading_order=0,
                        subkind=sub)
        assert c.db_type() in allowed


def test_grobid_sentences_are_not_regions():
    """With segmentSentences=1 every paragraph also emits its `<s>` boxes; counting those as
    regions would match one paragraph three or four times."""
    assert "s" not in R.GROBID_REGIONS and "s" not in R.GROBID_KIND
    assert "ref" not in R.GROBID_REGIONS and "persName" not in R.GROBID_REGIONS


# ── reading order ───────────────────────────────────────────────────────────────────────

def _canon(texts):
    return [R.Canonical(page=1, x0=0, y0=i * 10, x1=100, y1=i * 10 + 9, kind="paragraph",
                        reading_order=i, text=t) for i, t in enumerate(texts)]


def test_reading_order_accepts_the_right_sequence():
    c = _canon(["left one", "left two", "right one", "right two"])
    assert R.order_violations(c, ["left one", "left two", "right one"]) == []


def test_an_interleaved_reading_order_fails():
    """THE INTERLEAVE KILL (§14 P4). A two-column page read across the gutter — left line 1,
    right line 1, left line 2 — puts the gold sequence out of order and this must see it."""
    c = _canon(["left one", "right one", "left two", "right two"])
    bad = R.order_violations(c, ["left one", "left two", "right one", "right two"])
    assert bad, "an interleaved order was accepted"
    assert [i for i, _ in bad] == [2]


def _two_column():
    """A two-column page as the tools see it: the layout model's order runs down the LEFT column
    and then down the right, while geometry (y then x) interleaves them."""
    spec = [("L1", 0, 50, 0), ("L2", 0, 300, 1), ("R1", 300, 50, 2), ("R2", 300, 300, 3)]
    return [R.Canonical(page=1, x0=x, y0=y, x1=x + 250, y1=y + 200, kind="paragraph",
                        reading_order=-1, text=t, tool_order=o) for t, x, y, o in spec]


def test_assign_order_keeps_doclings_order_across_two_columns():
    """THE WRITER'S interleave test, not the checker's. `_assign_order` must SORT by the layout
    model's sequence, never re-derive it from geometry — a version that anchored every block to
    `max(order_index)` over the blocks above it put 21 of 23 body snippets on Benedek_2015 pp2-3
    out of Docling's order, because the right column's top block is 'above' the whole left one."""
    out = R._assign_order(_two_column())
    assert [c.text for c in sorted(out, key=lambda c: c.reading_order)] == ["L1", "L2", "R1", "R2"]
    assert R.order_violations(out, ["L1", "L2", "R1", "R2"]) == []


def test_a_region_only_grobid_saw_anchors_inside_its_own_column():
    """The anchor requires horizontal overlap. Without it a left-column block takes the right
    column's order and lands in the wrong half of the page."""
    from litkb.extract import docling as D

    d = [D.Block(page=1, x0=x, y0=y, x1=x + 250, y1=y + 200, kind="text", text=t,
                 frame="mediabox", order_index=o)
         for t, x, y, o in [("L1", 0, 50, 0), ("R1", 300, 50, 2)]]
    by_page = {1: d}
    left_lower = _b(1, 0, 300, 250, 500)
    assert R._anchor(left_lower, by_page) == 0, "anchored to the right column"
    right_lower = _b(1, 300, 300, 550, 500)
    assert R._anchor(right_lower, by_page) == 2


def test_text_the_order_lost_is_a_violation_too():
    c = _canon(["left one", "left two"])
    assert R.order_violations(c, ["left one", "a line nobody kept"]) == [(1, "a line nobody kept")]


# ── coverage ────────────────────────────────────────────────────────────────────────────

class _Rec:
    """A fake native layer: characters at known points, no PDF needed."""

    def __init__(self, pts):
        self.pts = pts


def test_native_text_is_a_slice_of_the_page_and_keeps_its_spaces():
    """A space has no usable box, so it is not in `pts`. Joining the ink alone gives
    'onetwo' — text no quote can be verified against and no chunker can use. The slice between
    the first and last inside-character keeps the page's own spacing."""
    layer = {"text": "one two far", "pts": [("o", 5, 5, 0), ("n", 6, 5, 1), ("e", 7, 5, 2),
                                            ("t", 5, 15, 4), ("w", 6, 15, 5), ("o", 7, 15, 6),
                                            ("f", 500, 500, 8)]}
    assert R.native_text_in(layer, (0, 0, 10, 20)) == "one two"
    assert R.native_text_in(layer, (900, 900, 910, 920)) == ""


def test_a_page_with_no_native_layer_reports_none_not_zero():
    """An image-only scan has no denominator. 0 % would say the reconciliation missed a page it
    never read, 100 % would say it covered one."""
    cov = {1: {"chars": 0, "covered": 0, "share": None, "page_class": "image-only"}}
    assert R.coverage_failures(cov) == []
    assert R.coverage_by_page_type(cov)["image-only"]["share"] is None


def test_coverage_falls_below_the_floor_when_the_catch_all_block_is_removed():
    """THE COVERAGE KILL. A page whose blocks cover everything passes; remove the one block that
    holds the body and the share drops through the floor and the gate names the page."""
    chars = [("x", 5, y) for y in range(0, 200, 2)]          # 100 characters down the page
    full = [(0, 0, 10, 200)]
    stripped = [(0, 0, 10, 20)]                              # only the first 10 characters

    def share(boxes):
        covered = sum(1 for _, x, y in chars if any(R._in_box(x, y, b) for b in boxes))
        return covered / len(chars)

    assert share(full) == 1.0
    cov_ok = {1: {"chars": 100, "covered": 100, "share": share(full), "page_class": "text"}}
    cov_bad = {1: {"chars": 100, "covered": int(share(stripped) * 100),
                   "share": share(stripped), "page_class": "text"}}
    assert R.coverage_failures(cov_ok) == []
    assert R.coverage_failures(cov_bad) == [(1, pytest.approx(0.11, abs=0.01))]


# ── ingest, against litkb_test ──────────────────────────────────────────────────────────

def _file_row(pg):
    """A work and a file, as the P1 harness builds them."""
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    file_id, _ = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, "
        "%s, NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         pg.Jsonb({"work_id": str(work_id), "rel_path": "Validation/Test_2020_x-paper.pdf",
                   "status": "active"}), ws))
    return file_id


def _blocks(n=5, with_table=False):
    out = [R.Canonical(page=1, x0=0, y0=i * 10, x1=100, y1=i * 10 + 9, kind="paragraph",
                       reading_order=i, text=f"paragraph {i}", source="both", confidence=0.9,
                       extractor={"bbox": "docling", "text": "native-layer"},
                       text_source="native") for i in range(n)]
    if with_table:
        out.append(R.Canonical(
            page=1, x0=0, y0=500, x1=100, y1=600, kind="table", reading_order=n, source="docling",
            extractor={"bbox": "docling", "cells": "docling"},
            payload={"n_rows": 1, "n_cols": 2, "caption": "Table 1",
                     "cells": [{"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "a",
                                "x0": 0.0, "y0": 500.0, "x1": 50.0, "y1": 600.0,
                                "column_header": True, "row_header": False},
                               {"row": 0, "col": 1, "row_span": 1, "col_span": 1, "text": "b",
                                "x0": 50.0, "y0": 500.0, "x1": 100.0, "y1": 600.0,
                                "column_header": False, "row_header": False}]}))
    return out


def _dis(n=2):
    return [R.Disagreement(page=1, kind="kind_conflict", detail=f"d{i}", iou=0.6,
                           grobid_kind="heading", docling_kind="paragraph",
                           grobid_text="g", docling_text="d", bbox=(0, 0, 1, 1))
            for i in range(n)]


def _ingest(pg, file_id, blocks=None, dis=None, **kw):
    from litkb.extract import ingest as ing

    conn = pg.session("litkb_ingest")
    return ing.ingest_file(conn, file_id, blocks if blocks is not None else _blocks(),
                           dis if dis is not None else _dis(), {"note": "test"},
                           pages=[{"page_no": 1, "page_class": "text", "native_chars": 100,
                                   "covered_chars": 95, "coverage_share": 0.95}], **kw), conn


@pg_only
def test_ingest_writes_blocks_and_moves_the_pointer_last(pg):
    file_id = _file_row(pg)
    res, _ = _ingest(pg, file_id, _blocks(with_table=True))
    assert res["inserted"] and res["blocks"] == 6 and res["disagreements"] == 2
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (res["run_id"],))[0] == 6
    assert pg.one("SELECT count(*) FROM litkb.table_cells")[0] >= 2
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0] == res["run_id"]
    # the pointer's history row, written inside set_current_run (0017)
    assert pg.one("SELECT run_id, version_no FROM litkb.file_current_run WHERE file_id = %s",
                  (file_id,)) == (res["run_id"], 1)


@pg_only
def test_kill_a_duplicate_ingest_inserts_nothing(pg):
    """§14 P5: zero duplicate runs. The second call is idempotent by (file sha256, pipeline
    version) and does not touch a row."""
    file_id = _file_row(pg)
    first, _ = _ingest(pg, file_id)
    before = pg.one("SELECT count(*) FROM litkb.blocks")[0]
    second, _ = _ingest(pg, file_id)
    assert second["run_id"] == first["run_id"] and second["inserted"] is False
    assert pg.one("SELECT count(*) FROM litkb.blocks")[0] == before
    assert pg.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s "
                  "AND stage = '5-reconcile'", (file_id,))[0] == 1


@pg_only
def test_kill_a_worker_killed_mid_file_leaves_no_duplicate_blocks(pg):
    """§14 P5 (a), simulated: the worker dies after the blocks are written and before the run is
    finished. On resume the file completes with exactly the control run's block count."""
    control_file = _file_row(pg)
    control, _ = _ingest(pg, control_file)
    control_n = control["blocks"]

    file_id = _file_row(pg)

    class Killed(RuntimeError):
        pass

    def die(conn, run_id):
        raise Killed("worker killed mid-file")

    with pytest.raises(Killed):
        _ingest(pg, file_id, _after_blocks=die)
    assert pg.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s "
                  "AND stage = '5-reconcile'", (file_id,))[0] == 0
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE file_id = %s", (file_id,))[0] == 0

    res, _ = _ingest(pg, file_id)
    assert res["inserted"] and res["blocks"] == control_n
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE file_id = %s", (file_id,))[0] == control_n


@pg_only
def test_kill_text_rows_are_invisible_until_the_run_commits(pg):
    """§14 P5: the kill fires when ingest is mutated to commit text rows outside the run's
    transaction. A second connection must see NOTHING while the file is in flight."""
    file_id = _file_row(pg)
    watcher = pg.session("litkb_ingest")
    seen = {}

    def look(conn, run_id):
        seen["blocks"] = watcher.execute(
            "SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (run_id,)).fetchone()[0]
        seen["runs"] = watcher.execute(
            "SELECT count(*) FROM litkb.extraction_runs WHERE id = %s", (run_id,)).fetchone()[0]

    _ingest(pg, file_id, _after_blocks=look)
    assert seen == {"blocks": 0, "runs": 0}, (
        "another session saw a half-written file: the rows are committed outside the run's "
        "transaction")


@pg_only
def test_kill_a_partial_run_left_by_a_kill_is_cleared_not_appended_to(pg):
    """The other half of the resume rule: a run row that survived a crash (status not ok) has
    its rows REMOVED in the resuming transaction. With that removal gone, resume appends and
    the file ends with two sets of blocks."""
    from litkb.extract import ingest as ing

    file_id = _file_row(pg)
    conn = pg.session("litkb_ingest")
    # plant exactly what a crashed worker leaves: the run row and half its blocks
    k = ing.run_key(file_id)
    run_id = conn.execute(
        "SELECT litkb.open_extraction_run(%(file_id)s, %(stage)s, %(tool)s, %(tool_version)s, "
        "%(params_hash)s, %(pipeline_version)s, 'local', 'failed', NULL, '{}'::jsonb)",
        k).fetchone()[0]
    for i in range(3):
        conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                     "VALUES (%s, %s, 1, 'paragraph', %s)", (file_id, run_id, f"stale {i}"))
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (run_id,))[0] == 3

    res, _ = _ingest(pg, file_id)
    assert res["run_id"] == run_id
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (run_id,))[0] == res["blocks"]
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s AND text LIKE 'stale%%'",
                  (run_id,))[0] == 0


@pg_only
def test_kill_the_writer_role_cannot_insert_a_block_or_a_disagreement(pg):
    """§4.7: the extraction tables are the ingest login's. A writer that could insert a block
    could forge the text any quote verifies against."""
    file_id = _file_row(pg)
    res, _ = _ingest(pg, file_id)
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                       "VALUES (%s, %s, 1, 'paragraph', 'forged')", (file_id, res["run_id"]))
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute("SELECT litkb.add_disagreement(%s, %s, 1, 'kind_conflict', 'x', NULL, NULL, "
                       "'grobid', NULL, '', 'docling', NULL, '', NULL)", (file_id, res["run_id"]))


@pg_only
def test_kill_nobody_inserts_into_the_new_tables_directly(pg):
    """0017's three tables grant INSERT to NO role: the checked function is the only path, so
    its checks are not optional. The ingest login included."""
    ingest = pg.session("litkb_ingest")
    for table in ("litkb.table_cells", "litkb.extraction_disagreements", "litkb.file_current_run"):
        assert pg.one("SELECT has_table_privilege('litkb_ingest', %s, 'INSERT')", (table,))[0] is False
        assert pg.one("SELECT has_table_privilege('litkb_writer', %s, 'INSERT')", (table,))[0] is False
    with pytest.raises(pg.errors.InsufficientPrivilege):
        ingest.execute("INSERT INTO litkb.file_current_run (file_id, version_no, run_id) "
                       "VALUES (%s, 1, %s)", (uuid.uuid4(), uuid.uuid4()))


@pg_only
def test_kill_set_current_run_refuses_a_failed_run(pg):
    """The P1 rule, re-proved on the stage-5 path: an `ok` run of the SAME file, or nothing."""
    file_id = _file_row(pg)
    res, conn = _ingest(pg, file_id)
    failed = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, '5-reconcile', 'x', '0', %s, 'v0', 'local', "
        "'failed') RETURNING id", (file_id, uuid.uuid4().hex)).fetchone()[0]
    with pytest.raises(pg.errors.InvalidParameterValue, match="not an ok extraction run"):
        conn.execute("SELECT litkb.set_current_run(%s, %s, %s)", (file_id, res["run_id"], failed))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0] == res["run_id"]
    # and no history row was written for the refused move
    assert pg.one("SELECT count(*) FROM litkb.file_current_run WHERE file_id = %s", (file_id,))[0] == 1


@pg_only
def test_kill_an_ok_runs_text_rows_can_never_be_cleared(pg):
    """The resume path deletes a killed worker's rows. That same privilege must not be able to
    empty a LIVE run — the evidence rows point into it."""
    file_id = _file_row(pg)
    res, conn = _ingest(pg, file_id)
    with pytest.raises(pg.errors.InvalidParameterValue, match="immutable"):
        conn.execute("SELECT litkb.clear_extraction_rows(%s)", (res["run_id"],))
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (res["run_id"],))[0] == res["blocks"]


@pg_only
def test_kill_a_reconciliation_run_with_no_blocks_cannot_be_ok(pg):
    from litkb.extract import ingest as ing

    file_id = _file_row(pg)
    conn = pg.session("litkb_ingest")
    run_id = conn.execute(
        "SELECT litkb.open_extraction_run(%(file_id)s, %(stage)s, %(tool)s, %(tool_version)s, "
        "%(params_hash)s, %(pipeline_version)s, 'local', 'failed', NULL, '{}'::jsonb)",
        ing.run_key(file_id)).fetchone()[0]
    with pytest.raises(pg.errors.InvalidParameterValue, match="no blocks"):
        conn.execute("SELECT litkb.finish_extraction_run(%s, 'ok', NULL)", (run_id,))


@pg_only
def test_kill_the_retired_tables_cells_json_is_refused(pg):
    """One fact, one home: a table's cells are rows in table_cells, never a JSON copy beside
    them."""
    file_id = _file_row(pg)
    res, conn = _ingest(pg, file_id)
    # a second table block, so the insert below is the first `tables` row for it
    block = conn.execute(
        "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
        "VALUES (%s, %s, 1, 'table', '') RETURNING id", (file_id, res["run_id"])).fetchone()[0]
    with pytest.raises(pg.errors.InvalidParameterValue, match="retired"):
        conn.execute("INSERT INTO litkb.tables (block_id, cells) VALUES (%s, '[]'::jsonb)", (block,))
    # the control: the same insert with no JSON cells is accepted, and the rows go to table_cells
    conn.execute("INSERT INTO litkb.tables (block_id, n_rows, n_cols) VALUES (%s, 1, 1)", (block,))
    conn.execute("SELECT litkb.add_table_cell(%s, 0, 0, 1, 1, 'a', NULL, false, false)", (block,))
    assert pg.one("SELECT count(*) FROM litkb.table_cells WHERE block_id = %s", (block,))[0] == 1


@pg_only
def test_kill_a_cell_cannot_hang_below_a_paragraph(pg):
    file_id = _file_row(pg)
    res, conn = _ingest(pg, file_id)
    para = pg.one("SELECT id FROM litkb.blocks WHERE run_id = %s AND type = 'paragraph' LIMIT 1",
                  (res["run_id"],))[0]
    with pytest.raises(pg.errors.InvalidParameterValue, match="not a table block"):
        conn.execute("SELECT litkb.add_table_cell(%s, 0, 0, 1, 1, 'x', NULL, false, false)", (para,))


@pg_only
def test_kill_a_block_cannot_name_another_files_run(pg):
    """The trigger holds on the DIRECT insert too, which is the path 0010 left open."""
    a, b = _file_row(pg), _file_row(pg)
    res, conn = _ingest(pg, a)
    with pytest.raises(pg.errors.CheckViolation, match="is not a run of file"):
        conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                     "VALUES (%s, %s, 1, 'paragraph', 'x')", (b, res["run_id"]))


@pg_only
def test_kill_a_canonical_block_cannot_have_a_null_reading_order(pg):
    """A canonical set with a NULL order cannot be read back in order, and stage 7's chunks are
    built from that order. The CHECK holds on the direct-INSERT path too."""
    file_id = _file_row(pg)
    res, conn = _ingest(pg, file_id)
    with pytest.raises(pg.errors.CheckViolation, match="blocks_canonical_has_order"):
        conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text, canonical) "
                     "VALUES (%s, %s, 1, 'paragraph', 'orderless', true)", (file_id, res["run_id"]))
    # the control: a NON-canonical block may have none (that is what a tool's raw block is)
    conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                 "VALUES (%s, %s, 1, 'paragraph', 'raw')", (file_id, res["run_id"]))


@pg_only
def test_two_canonical_blocks_cannot_share_a_reading_order(pg):
    file_id = _file_row(pg)
    dup = _blocks(3)
    dup[2] = R.Canonical(page=1, x0=0, y0=0, x1=1, y1=1, kind="paragraph", reading_order=1,
                         text="collides")
    with pytest.raises(pg.errors.UniqueViolation):
        _ingest(pg, file_id, dup)

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
import json
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


# ── the four thresholds, pinned at ±20 % by a GOLD-DERIVED boundary case ─────────────────
#
# The referee of 2026-09-15 moved every one of the four by a fifth in both directions and the
# whole suite passed eight times out of eight: "pinned by tests" was true only at the extremes
# R53/R54/R55 use. Each case below sits between the constant and its ±20 % move, at an IoU or a
# ratio MEASURED on the corpus (referee §5, "the corpus pages nearest each cut"), so a move of a
# fifth in either direction fails a named test here.

def _iou_pair(v):
    """Two boxes whose IoU is exactly `v`: (0,0,100,100) against (0,0,100,100v)."""
    return [_b(1, 0, 0, 100, 100)], [_d(1, 0, 0, 100, 100 * v)]


def test_iou_match_is_pinned_below_at_the_corpus_pair_just_inside_it():
    """Benedek_2015 p7's nearest candidate pair sits at IoU 0.5334 — just inside IOU_MATCH. It
    must be ONE region; at IOU_MATCH 0.6 (+20 %) it becomes two single-tool blocks."""
    pairs, l_only, r_only, touching = R.match_by_iou(*_iou_pair(0.5334))
    assert len(pairs) == 1 and touching == [] and l_only == [] and r_only == []


def test_iou_match_is_pinned_above_at_the_corpus_pair_just_outside_it():
    """Benedek_2015 p9's, at 0.4559 — just outside. It is a partial overlap, and a disagreement
    in its own right; at IOU_MATCH 0.4 (−20 %) the two tools' different regioning is silently
    merged and the disagreement is lost."""
    pairs, _, _, touching = R.match_by_iou(*_iou_pair(0.4559))
    assert pairs == [] and len(touching) == 1


def test_iou_touch_is_pinned_below_at_the_corpus_pair_just_inside_it():
    """Benedek_2015 p5 at 0.1029, Alwan p8 at 0.1003, Almon p5 at 0.1020 — the corpus's nearest
    pairs to IOU_TOUCH. They must be RECORDED as touching; at 0.12 (+20 %) they vanish from the
    disagreement table altogether, which is the failure mode nobody can see from the counts."""
    pairs, _, _, touching = R.match_by_iou(*_iou_pair(0.1029))
    assert pairs == [] and len(touching) == 1


def test_iou_touch_is_pinned_above_by_a_pair_that_must_not_touch():
    """Just below the cut: two boxes at IoU 0.09 are not the same region and do not overlap
    enough to be a disagreement about one. At IOU_TOUCH 0.08 (−20 %) they become one."""
    pairs, l_only, r_only, touching = R.match_by_iou(*_iou_pair(0.09))
    assert pairs == [] and touching == [] and len(l_only) == 1 and len(r_only) == 1


#: Gold-derived TEXT_AGREE cases. The referee measured the corpus pages nearest the 0.90 cut —
#: Benedek p9 at 0.9015 (just agreeing), Almon p4 at 0.8932 (just not). These two strings
#: reproduce that shape without a PDF: one pair above the cut, one below.
_AGREE = ("the multilayer segmentation models can overcome the before mentioned limitations",
          "the multilayer segmentation models can overcome the before-mentioned limitation")
_DISAGREE = ("as implemented by shewhart and his colleagues and successors in industry",
             "as implemented by shewhart and his colleagues, and successors in a running record")


def test_text_agree_is_pinned_below_by_two_readings_that_do_agree():
    """Above the cut, as Benedek p9's 0.9015 is. At TEXT_AGREE 0.99 (+20 %) a real agreement is
    recorded as a text_conflict and every matched region's confidence drops to 0.7."""
    assert R.TEXT_AGREE <= R.text_ratio(*_AGREE) < 0.99
    assert R.text_agrees(*_AGREE)


def test_text_agree_is_pinned_above_by_two_readings_that_do_not():
    """Below the cut, as Almon p4's 0.8932 is. At TEXT_AGREE 0.72 (−20 %) two tools reading the
    region differently is recorded as agreement and the conflict is never written down."""
    assert 0.72 <= R.text_ratio(*_DISAGREE) < R.TEXT_AGREE
    assert not R.text_agrees(*_DISAGREE)


def test_the_coverage_floor_is_pinned_in_both_directions():
    """The referee's finding stands — no page of the gate set is within 0.19 of this floor, so it
    is a CATASTROPHE DETECTOR, not an operating-point gate (§5: minimum shares 0.9989, 0.9918,
    1.0000; failing pages 0/0/0 at floors 0.64, 0.80 and 0.96 alike). It is pinned anyway: a page
    at 0.70 must fail (it passes at 0.64) and one at 0.90 must pass (it fails at 0.96)."""
    bad = {1: {"chars": 100, "covered": 70, "share": 0.70, "page_class": "text"}}
    ok = {2: {"chars": 100, "covered": 90, "share": 0.90, "page_class": "text"}}
    assert R.coverage_failures(bad) == [(1, 0.70)]
    assert R.coverage_failures(ok) == []


# ── NUL bytes and U+FFFE: one boundary, one helper ──────────────────────────────────────

def test_a_nul_byte_never_leaves_the_reconcile_boundary():
    """THE BLOCKER (referee §4(0)). Docling's own string for a region with no usable native
    layer carries \\x00 — 6 canonical blocks and 10 disagreement rows on Benedek_2015 — and
    Postgres text refuses it, so the file's whole transaction aborted and it landed NOTHING.
    Every text field is cleaned in ONE place, `_sanitize`, through the shared `jsonb_safe`."""
    c = R.Canonical(page=1, x0=0, y0=0, x1=1, y1=1, kind="table", reading_order=0,
                    text="a\x00b", latex="x\x00y",
                    payload={"caption": "cap\x00tion",
                             "cells": [{"text": "cell\x00text"}]})
    d = R.Disagreement(page=1, kind="text_conflict", detail="d\x00", grobid_text="g\x00",
                       docling_text="do\x00")
    blocks, dis = R._sanitize([c], [d])
    assert blocks[0].text == "ab" and blocks[0].latex == "xy"
    assert blocks[0].payload["caption"] == "caption"
    assert blocks[0].payload["cells"][0]["text"] == "celltext"
    assert (dis[0].detail, dis[0].grobid_text, dis[0].docling_text) == ("d", "g", "do")


def test_the_hyphen_noncharacter_is_removed_not_kept():
    """U+FFFE (referee §4(d)): pypdfium2 emits it at every line-break hyphen — 24 of them on
    Alwan p3 alone — and it reached blocks.text, where stage 6's quote verification and stage 7's
    chunking would fail on every hyphenated line. It is REMOVED, because the native slice already
    carries the two halves adjacent: 'spe\\ufffecial' -> 'special', the word as printed. A hyphen
    would give 'spe-cial', which matches no gold quote and no printed word."""
    c = R.Canonical(page=1, x0=0, y0=0, x1=1, y1=1, kind="paragraph", reading_order=0,
                    text="detect any spe￾cial causes")
    assert R._sanitize([c], [])[0][0].text == "detect any special causes"


# ── figures: ONE canonical block per real figure ────────────────────────────────────────

def _fig(page, box, conf=0.8, caption=""):
    return R.Canonical(page=page, x0=box[0], y0=box[1], x1=box[2], y1=box[3], kind="figure",
                       reading_order=-1, confidence=conf,
                       payload={"caption": caption} if caption else {})


def test_two_figure_blocks_over_one_figure_become_one():
    """Referee §4(b): a figure entered twice — once as a GROBID <figure> body region, once
    through the figure pass — put 4 litkb.figures rows in the database for the 2 figures on
    Benedek p4. Two figure blocks on a page that agree at IOU_MATCH are ONE figure, and the
    survivor is the richer block (the one carrying the caption)."""
    keep = _fig(4, (76, 66, 505, 371), conf=0.8, caption="Fig. 1. Structure of the L3MRF model")
    drop = _fig(4, (78, 68, 503, 369), conf=0.5)
    out = R._dedupe_figures([drop, keep])
    assert len(out) == 1 and out[0].payload.get("caption").startswith("Fig. 1.")


def test_two_different_figures_on_one_page_are_not_deduped():
    """The control. Benedek p4 really does hold two figures; the dedupe must keep both."""
    a = _fig(4, (76, 66, 505, 371), caption="Fig. 1.")
    b = _fig(4, (48, 443, 533, 722), caption="Fig. 2.")
    assert len(R._dedupe_figures([a, b])) == 2


def test_grobid_figure_regions_are_not_body_regions():
    """The root cause, fixed the way Docling's pictures and tables already were: the body matcher
    does not read <figure>, because the figure pass claims that region. GROBID's figure regions
    are still read — `_grobid_figures` supplies them to the caption match."""
    assert "figure" in R.GROBID_REGIONS
    assert "figure" not in R.GROBID_BODY_REGIONS
    assert set(R.GROBID_BODY_REGIONS) == {"p", "head", "note", "formula"}


# ── a GROBID element that crosses the column gutter ─────────────────────────────────────

def test_an_element_that_crosses_the_gutter_is_split_into_per_column_boxes():
    """Referee §4(a). On Alwan p3 a <p> whose last two lines fall in the right column unioned
    into [14, 245, 561, 728] — the whole page width — which `_anchor` then placed ahead of the
    entire left column. A column break is split exactly as a page break is."""
    xs = [(55, 291)] * 13 + [(313, 545)] * 2
    lines = [_b(3, x0, 570 + 12 * i if i < 13 else 60 + 12 * (i - 13), x1,
                580 + 12 * i if i < 13 else 70 + 12 * (i - 13))
             for i, (x0, x1) in enumerate(xs)]
    lines = [type(lines[0])(**{**vars(b), "box_index": i, "box_count": len(lines)})
             for i, b in enumerate(lines)]
    out = R.union_boxes(lines)
    assert len(out) == 2, "the gutter-crossing element was unioned into one page-wide box"
    assert out[0].x1 <= 291 and out[1].x0 >= 313
    assert out[0].x0 >= 55, "the left column's box must not reach across the gutter"


def test_a_column_is_not_split_by_a_short_line_or_a_stray_fragment():
    """The control, and why the rule is a CONNECTED COMPONENT of the lines' x-ranges rather than
    'no overlap with the line before'. Measured on Alwan p3: the pairwise rule splits a paragraph
    at a short last line followed by an indented one, and at a 4-point superscript fragment,
    neither of which is a column. Here a short line, then a fragment far to the right that a
    later full-width line bridges, stay ONE region."""
    spec = [(55, 291), (56, 65), (240, 289), (55, 291)]
    lines = [_b(3, x0, 100 + 12 * i, x1, 110 + 12 * i) for i, (x0, x1) in enumerate(spec)]
    lines = [type(lines[0])(**{**vars(b), "box_index": i, "box_count": len(lines)})
             for i, b in enumerate(lines)]
    assert len(R.union_boxes(lines)) == 1


def test_two_fragments_of_one_element_read_left_column_first():
    """The other half of the fix. Split, the two fragments carry the SAME tool_order (they match
    or anchor to one Docling region), and the tie was then broken by y0 — which puts the RIGHT
    column's fragment, at the top of the page, ahead of the left column's. That was the one
    remaining out-of-order pair on Alwan p3 and on Benedek p2."""
    left = R.Canonical(page=3, x0=67, y0=580, x1=305, y1=728, kind="paragraph", reading_order=-1,
                       text="the plan of the article", tool_order=43)
    right = R.Canonical(page=3, x0=324, y0=69, x1=558, y1=90, kind="paragraph", reading_order=-1,
                        text="systematic variation through time", tool_order=43)
    out = sorted(R._assign_order([right, left]), key=lambda c: c.reading_order)
    assert [c.x0 for c in out] == [67, 324]


# ── coverage metric C: per-region recall ────────────────────────────────────────────────

GOLD_PATH = pathlib.Path(__file__).resolve().parents[2] / "Reports" / "gold" / "stage5_gold_2026-09-15.json"


def _gold_page(file_stem, page):
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    return next(p for p in gold["pages"] if p["file"].startswith(file_stem) and p["page"] == page)


def _gold_text_regions(page):
    """The gold's TEXT-bearing regions, as (n, snippet). The bracketed placeholders — a figure,
    a table, a display equation — carry no printed words and no block can begin at them."""
    return [(b["n"], b["snippet"]) for b in page["body_order"] if not b["snippet"].startswith("[")]


def test_the_character_share_misses_a_lost_region_and_per_region_recall_does_not():
    """THE PLANTED LOST REGION (referee §6), as a test rather than a one-off measurement.

    A page's blocks OVERLAP, and the shipped metric asks only whether SOME block is responsible
    for each character. Remove a whole region whose ink also lies inside two surviving blocks and
    the covered share does not move by ONE character — the §14 gate sees nothing. Per-region
    recall falls by exactly one and NAMES the region. That is why the gate is now recall."""
    regions = [("kept", "the use of time-series models requires"),
               ("planted", "in the light of the widespread use of arima models")]
    wide = R.Canonical(page=3, x0=60, y0=180, x1=310, y1=540, kind="paragraph", reading_order=0,
                       text="cepts in process control, the thrust of these applications "
                            "in the light of the widespread use of arima models in other fields "
                            "the use of time-series models requires more statistical skill")
    own = R.Canonical(page=3, x0=65, y0=187, x1=302, y1=370, kind="paragraph", reading_order=1,
                      text="In the light of the widespread use of ARIMA models in other fields")
    kept = R.Canonical(page=3, x0=66, y0=373, x1=303, y1=532, kind="paragraph", reading_order=2,
                       text="The use of time-series models requires more statistical skill")

    # the character share: every character of `own` also lies inside `wide`, so dropping it
    # changes nothing at all
    pts = [("x", 100.0, y, i) for i, y in enumerate(range(190, 365, 5))]
    before = sum(1 for _c, x, y, _i in pts
                 if any(R._in_box(x, y, b.bbox) for b in (wide, own, kept)))
    after = sum(1 for _c, x, y, _i in pts if any(R._in_box(x, y, b.bbox) for b in (wide, kept)))
    assert before == after == len(pts), "the plant must be invisible to the character share"

    hits, total, missing = R.region_recall([wide, own, kept], regions)
    assert (hits, total, missing) == (2, 2, [])
    hits, total, missing = R.region_recall([wide, kept], regions)
    assert (hits, total, missing) == (1, 2, ["planted"]), "the lost region was not named"


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
        out.append(R.Canonical(
            page=1, x0=0, y0=620, x1=100, y1=700, kind="figure", reading_order=n + 1,
            text="Fig. 1. A caption, which is the BLOCK's text.", source="both",
            payload={"caption": "Fig. 1. A caption, which is the BLOCK's text."}))
        out.append(R.Canonical(
            page=1, x0=0, y0=710, x1=100, y1=740, kind="equation", reading_order=n + 2,
            text="x = y + 1", latex=None, source="docling"))
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
    assert res["inserted"] and res["blocks"] == 8 and res["disagreements"] == 2
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (res["run_id"],))[0] == 8
    assert pg.one("SELECT count(*) FROM litkb.table_cells")[0] >= 2
    # the figure's caption is the BLOCK's text; figures.description is stage 8's vision field
    fig = pg.one("SELECT b.text, f.description, f.description_model FROM litkb.figures f "
                 "JOIN litkb.blocks b ON b.id = f.block_id WHERE b.run_id = %s", (res["run_id"],))
    assert fig[0].startswith("Fig. 1.") and fig[1] is None and fig[2] is None
    # the equation is a region; its latex stays NULL until stage 4 fills it
    assert pg.one("SELECT e.latex FROM litkb.equations e JOIN litkb.blocks b ON b.id = e.block_id "
                  "WHERE b.run_id = %s", (res["run_id"],)) == (None,)
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0] == res["run_id"]
    # the pointer's history row, written inside set_current_run (0017)
    assert pg.one("SELECT run_id, version_no FROM litkb.file_current_run WHERE file_id = %s",
                  (file_id,)) == (res["run_id"], 1)


TEI_DIR = pathlib.Path(r"D:\edmonds-pipeline\_tmp\litkb_tei")
DOC_DIR = pathlib.Path(r"D:\edmonds-pipeline\_tmp\litkb_docling")
BENEDEK = CORPUS / "Validation" / "Benedek_2015_multilayer-markov-random-field-models.pdf"
_REAL = [("Alwan", ALWAN, TEI_DIR / "Alwan.tei.xml", DOC_DIR / "Alwan_1988__cpu-t4.docling.json"),
         ("Anderson", CORPUS / "Validation" / "Anderson_1957_statistical-inference-about-markov.pdf",
          None, DOC_DIR / "Anderson_1957__ocr-t4.docling.json"),
         # THE NUL FILE (referee §4(0)): Docling's text for 6 of its regions carries \x00, and
         # before the reconcile-boundary strip this file could not be ingested AT ALL — the
         # transaction aborted on the first such block and it landed nothing. It is in this
         # parametrisation, not a test of its own, because the assertion that matters is the
         # ordinary one: the reconciliation lands whole.
         ("Benedek", BENEDEK, TEI_DIR / "Benedek.tei.xml",
          DOC_DIR / "Benedek_2015__cpu-t4.docling.json")]


def _reconcile_real(pdf, tei_path, doc_path):
    from litkb.extract import docling as D
    from litkb.extract import inventory as I

    record = I.probe_file(str(pdf))
    doc = D.load(str(doc_path))
    tei = tei_path.read_bytes() if tei_path is not None else None
    return R.reconcile(str(pdf), tei, doc, record, ocr_pages=record.get("ocr_pages") or ()), record


_real_gold = pytest.mark.skipif(
    not (BENEDEK.exists() and (DOC_DIR / "Benedek_2015__cpu-t4.docling.json").exists()
         and (TEI_DIR / "Benedek.tei.xml").exists()),
    reason="the stage-5 artifacts are not on this machine")


@_real_gold
def test_the_gold_page_holds_exactly_two_figures():
    """Scored on the REAL file against the frozen gold: Benedek p4 carries two full-width
    figures and two captions, and the referee measured SIX blocks for them — 4 litkb.figures rows
    for 2 figures. Exactly two figure blocks now, so the ingest is idempotent per figure."""
    (canonical, _dis, _stats), _ = _reconcile_real(
        BENEDEK, TEI_DIR / "Benedek.tei.xml", DOC_DIR / "Benedek_2015__cpu-t4.docling.json")
    page = _gold_page("Benedek_2015", 4)
    assert len([c for c in canonical if c.page == 4 and c.kind == "figure"]) == 2
    assert len(page["captions"]) == 2


@_real_gold
def test_a_figure_docling_reports_twice_still_enters_once():
    """THE DEDUPE'S OWN CALL SITE, on a real file with a PLANTED duplicate.

    `test_two_figure_blocks_over_one_figure_become_one` proves the helper; it cannot prove that
    `reconcile()` still CALLS it, and the harness caught exactly that (`R532` removed the call
    and nothing failed). The GROBID-figure exclusion masks it on the untouched artifact, so the
    duplicate is planted here: every picture item of Benedek p4 is copied inside the Docling
    document, which is what a tool emitting one region twice looks like. Without the call the
    page carries 4 figure blocks and `litkb.figures` would hold 4 rows for 2 figures.
    """
    import copy

    from litkb.extract import docling as D
    from litkb.extract import inventory as I

    doc = copy.deepcopy(D.load(str(DOC_DIR / "Benedek_2015__cpu-t4.docling.json")))
    planted = 0
    for item in list(doc.get("pictures") or []):
        if not any(int(p.get("page_no", 0)) == 4 for p in (item.get("prov") or [])):
            continue
        twin = copy.deepcopy(item)
        idx = len(doc["pictures"])
        twin["self_ref"] = f"#/pictures/{idx}"
        doc["pictures"].append(twin)
        # reachable from the body tree, which is how `iter_items` walks the document — a twin
        # only appended to the `pictures` list is never yielded and plants nothing
        doc["body"]["children"].append({"$ref": twin["self_ref"]})
        planted += 1
    assert planted == 2, "the plant needs p4's two pictures"
    assert len(D.figures(doc)) == 12, "the plant did not reach the reading order"

    record = I.probe_file(str(BENEDEK))
    canonical, _dis, _stats = R.reconcile(
        str(BENEDEK), (TEI_DIR / "Benedek.tei.xml").read_bytes(), doc, record,
        ocr_pages=record.get("ocr_pages") or ())
    assert len([c for c in canonical if c.page == 4 and c.kind == "figure"]) == 2


@_real_gold
def test_no_canonical_text_of_the_nul_file_carries_a_nul_or_the_hyphen_noncharacter():
    (canonical, dis, _stats), _ = _reconcile_real(
        BENEDEK, TEI_DIR / "Benedek.tei.xml", DOC_DIR / "Benedek_2015__cpu-t4.docling.json")
    bad = [c.page for c in canonical if "\x00" in (c.text or "") or "￾" in (c.text or "")]
    assert bad == []
    assert [d.page for d in dis
            if "\x00" in (d.grobid_text + d.docling_text + d.detail)] == []


@pytest.mark.skipif(not (ALWAN.exists() and (TEI_DIR / "Alwan.tei.xml").exists()
                         and (DOC_DIR / "Alwan_1988__cpu-t4.docling.json").exists()),
                    reason="the stage-5 artifacts are not on this machine")
def test_alwan_p3_has_no_out_of_order_pair_against_the_referees_gold():
    """THE CROSS-COLUMN FIX, scored against the gold the referee authored from the rendered page
    BEFORE any tool ran on it. It was 10 of 66 ordered pairs out of order, all of them the one
    page-wide GROBID block; it is 0 of 66 now. The comparator is here, not
    `order_violations` — a checker that shares a bug with the producer passes both."""
    (canonical, _dis, _stats), _ = _reconcile_real(
        ALWAN, TEI_DIR / "Alwan.tei.xml", DOC_DIR / "Alwan_1988__cpu-t4.docling.json")
    page = _gold_page("Alwan_1988", 3)
    on3 = [c for c in canonical if c.page == 3]
    pos = []
    for n, snip in _gold_text_regions(page):
        want = R._norm(snip)
        pos.append((n, next((c.reading_order for c in on3 if want in R._norm(c.text)), None)))
    found = [(n, p) for n, p in pos if p is not None]
    # gold region 8 is the one known miss and it is NOT stage 5's: the PDF's own text layer
    # reads "DEFINITBON" for the printed "DEFINITION" (referee §4, last paragraph).
    assert [n for n, p in pos if p is None] == [8]
    bad = [(found[i][0], found[j][0]) for i in range(len(found))
           for j in range(i + 1, len(found)) if found[j][1] < found[i][1]]
    assert bad == [], f"out of order against the gold: {bad}"
    assert len(found) * (len(found) - 1) // 2 == 66


@pg_only
@pytest.mark.parametrize("tag,pdf,tei_path,doc_path", _REAL, ids=[r[0] for r in _REAL])
def test_a_real_files_reconciliation_lands_whole(pg, tag, pdf, tei_path, doc_path):
    """END TO END on a REAL file, because every other ingest test here uses hand-built blocks and
    real output has shapes they do not: a table Docling gives no `prov` (page 0, which the
    `page_no >= 1` CHECK refuses), reference blocks renumbered after the body, and — on Anderson,
    which has no TEI at all — image-only pages whose coverage share is NULL rather than a number.
    Skipped where the artifacts are not on this machine; nothing here re-runs either tool."""
    if not pdf.exists() or not doc_path.exists() or (tei_path is not None and not tei_path.exists()):
        pytest.skip(f"{tag}: the stage-5 artifacts are not on this machine")
    from litkb.extract import docling as D
    from litkb.extract import inventory as I

    record = I.probe_file(str(pdf))
    doc = D.load(str(doc_path))
    tei = tei_path.read_bytes() if tei_path is not None else None
    canonical, dis, stats = R.reconcile(str(pdf), tei, doc, record,
                                        ocr_pages=record.get("ocr_pages") or ())
    classes = {i + 1: d.get("scan", "unknown") for i, d in enumerate(record["page_detail"])}
    cov = R.coverage(str(pdf), canonical, classes)
    pages = [{"page_no": p, "page_class": r["page_class"], "native_chars": r["chars"],
              "covered_chars": r["covered"], "coverage_share": r["share"]}
             for p, r in sorted(cov.items())]

    file_id = _file_row(pg)
    from litkb.extract import ingest as ing

    conn = pg.session("litkb_ingest")
    res = ing.ingest_file(conn, file_id, canonical, dis, stats, pages=pages,
                          artifact_path=str(doc_path))
    assert res["inserted"]
    assert res["blocks"] == stats["blocks"] == len(canonical)
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s",
                  (res["run_id"],))[0] == len(canonical)
    assert pg.one("SELECT count(*) FROM litkb.extraction_disagreements WHERE run_id = %s",
                  (res["run_id"],))[0] == len(dis)
    assert pg.one("SELECT count(*) FROM litkb.pages WHERE run_id = %s",
                  (res["run_id"],))[0] == len(pages)
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s",
                  (file_id,))[0] == res["run_id"]
    # a page with no native layer keeps a NULL share, never 0 or 1
    na = [p for p in pages if p["coverage_share"] is None]
    if na:
        assert pg.one("SELECT count(*) FROM litkb.pages WHERE run_id = %s AND coverage_share IS NULL",
                      (res["run_id"],))[0] == len(na)
    # and a second ingest of the same file writes nothing
    again = ing.ingest_file(conn, file_id, canonical, dis, stats, pages=pages)
    assert again["inserted"] is False and again["run_id"] == res["run_id"]


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

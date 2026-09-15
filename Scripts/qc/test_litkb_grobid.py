"""GROBID adapter tests (litkb stage 2, design §7.1).

The bulk of this module needs no GROBID: it runs against a saved TEI fixture trimmed from a
real 0.9.1 CRF run. The few tests that need the live service carry @pytest.mark.litkb_live
and skip unless LITKB_LIVE=1, so the ladder never depends on a running JVM.

The mutation tests below are the point of the file. §7.1 requires that the adapter test FAIL
when an adapter's y-flip or page offset is removed; GROBID needs no y-flip, so the equivalent
mutations for this tool are (a) dropping the "x1 = x + w" addition and (b) dropping the ";"
multi-box split. Both are exercised.
"""
import os
import pathlib

import pytest

from litkb.extract import grobid

FIXTURE = pathlib.Path(__file__).with_name("fixtures") / "grobid_sample.tei.xml"
LIVE = os.environ.get("LITKB_LIVE") == "1"


@pytest.fixture(scope="module")
def tei():
    return FIXTURE.read_bytes()


# ── parse_coords: the §7.1 adapter itself ───────────────────────────────────────────────

def test_single_box_becomes_x1_y1():
    """GROBID's page,x,y,w,h -> canonical (page, x0, y0, x1, y1)."""
    assert grobid.parse_coords("1,42.63,505.74,60.13,7.53") == [
        (1, 42.63, 505.74, 42.63 + 60.13, 505.74 + 7.53)]


def test_multi_box_coords_are_split_on_semicolon():
    """A wrapped title carries one box per line; both must survive."""
    boxes = grobid.parse_coords(
        "1,42.63,178.96,449.03,12.71;1,42.52,196.19,143.98,12.71")
    assert len(boxes) == 2
    assert boxes[0][0] == 1 and boxes[1][0] == 1
    assert boxes[0][3] == pytest.approx(42.63 + 449.03)
    assert boxes[1][4] == pytest.approx(196.19 + 12.71)


def test_pages_are_one_indexed_and_not_offset():
    assert grobid.parse_coords("4,32.71,382.07,520.06,6.66")[0][0] == 4


def test_malformed_groups_are_skipped_not_guessed():
    assert grobid.parse_coords("1,2,3") == []
    assert grobid.parse_coords("") == []
    assert grobid.parse_coords("1,a,b,c,d") == []
    # a good box beside a bad one still comes through
    assert len(grobid.parse_coords("1,2,3,4,5;nonsense")) == 1


# ── mutation tests: the adapter must not pass with its arithmetic removed ────────────────

def _mutant_no_width_add(value):
    """The y-flip-equivalent mutation for GROBID: forget that w,h are a SIZE, not a corner."""
    out = []
    for group in value.split(";"):
        p = group.split(",")
        if len(p) == 5:
            out.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4])))
    return out


def _mutant_first_box_only(value):
    return grobid.parse_coords(value)[:1]


def test_mutation_dropping_the_width_add_changes_the_boxes():
    v = "1,42.63,505.74,60.13,7.53"
    assert _mutant_no_width_add(v) != grobid.parse_coords(v)


def test_mutation_taking_only_the_first_box_loses_regions():
    v = "4,32.71,382.07,520.06,6.66;4,32.71,390.63,377.92,6.66;4,78.07,67.92,425.20,303.70"
    assert len(_mutant_first_box_only(v)) == 1
    assert len(grobid.parse_coords(v)) == 3


def test_containment_fails_under_the_no_width_add_mutation(tei):
    """A point inside the figure's graphic box is contained by the real adapter's box and
    NOT by the mutant's, which is what makes the mutation detectable on real geometry."""
    graphic = grobid.parse_coords("4,78.07,67.92,425.20,303.70")[0]
    # a point in the far quarter of the real box: the mutant treats w,h as the far corner,
    # so its box stops short of this point while the real box still contains it.
    px = graphic[1] + 0.95 * (graphic[3] - graphic[1])
    py = graphic[2] + 0.95 * (graphic[4] - graphic[2])
    assert graphic[1] <= px <= graphic[3] and graphic[2] <= py <= graphic[4]
    mx = _mutant_no_width_add("4,78.07,67.92,425.20,303.70")[0]
    assert not (mx[1] <= px <= mx[3] and mx[2] <= py <= mx[4])


# ── the block model over the fixture ─────────────────────────────────────────────────────

def test_blocks_carry_the_design_fields(tei):
    blocks = grobid.blocks(tei)
    assert blocks, "fixture produced no blocks"
    b = blocks[0]
    assert b.extractor == "grobid-0.9.1-crf"
    assert b.confidence is None          # GROBID TEI carries none; not invented
    assert b.page >= 1
    assert b.x1 >= b.x0 and b.y1 >= b.y0


def test_expected_kinds_are_present(tei):
    kinds = {b.kind for b in grobid.blocks(tei)}
    for k in ("title", "persName", "head", "ref", "figure", "s", "biblStruct"):
        assert k in kinds, f"no {k} block in the fixture"


def test_figure_yields_one_block_per_box(tei):
    figs = [b for b in grobid.blocks(tei) if b.kind == "figure"]
    assert len(figs) == 3                      # two caption lines + the graphic
    assert {f.box_index for f in figs} == {0, 1, 2}
    assert all(f.box_count == 3 for f in figs)
    assert all(f.element_id == "fig_0" for f in figs)


def test_kind_filter(tei):
    assert {b.kind for b in grobid.blocks(tei, kinds=("head",))} == {"head"}


def test_page_sizes_from_facsimile(tei):
    sizes = grobid.page_sizes(tei)
    assert sizes[1] == pytest.approx((595.276, 793.701))
    assert set(sizes) == {1, 2, 3, 4, 5, 6, 7, 8, 9}


def test_every_fixture_box_sits_inside_its_page(tei):
    assert grobid.implausible_blocks(tei) == []


def test_implausible_blocks_flags_an_escaping_box():
    """The box check must actually fire, or it is not a gate."""
    bad = FIXTURE.read_text(encoding="utf-8").replace(
        'coords="1,42.63,505.74,60.13,7.53"', 'coords="1,42.63,505.74,9000,7.53"')
    flagged = grobid.implausible_blocks(bad.encode("utf-8"))
    assert any("outside page" in reason for _, reason in flagged)


def test_implausible_blocks_flags_a_page_with_no_surface():
    bad = FIXTURE.read_text(encoding="utf-8").replace(
        'coords="1,42.63,505.74,60.13,7.53"', 'coords="97,42.63,505.74,60.13,7.53"')
    flagged = grobid.implausible_blocks(bad.encode("utf-8"))
    assert any("no <surface>" in reason for _, reason in flagged)


# ── header and references ────────────────────────────────────────────────────────────────

def test_header_title(tei):
    assert grobid.header_title(tei).startswith("Multilayer Markov Random Field models")


def test_bibl_structs_present(tei):
    assert len(grobid.bibl_structs(tei)) >= 1


def test_title_matches_registry_uses_the_project_rule(tei):
    ok, ratio = grobid.title_matches_registry(
        tei, "Multilayer Markov Random Field models for change detection "
             "in optical remote sensing images")
    assert ok and ratio >= 0.85


def test_title_match_rejects_a_different_title(tei):
    ok, ratio = grobid.title_matches_registry(tei, "Total variation flow in R^N")
    assert not ok and ratio < 0.85


# ── errors ───────────────────────────────────────────────────────────────────────────────

def test_grobid_error_carries_status_and_body():
    e = grobid.GrobidError("boom", 500, b"[BAD_INPUT_DATA] ...")
    assert e.status == 500 and b"BAD_INPUT_DATA" in e.body


def test_process_pdf_raises_when_unreachable(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(grobid.GrobidError):
        grobid.process_pdf(str(p), url="http://localhost:1", timeout=5)


# ── live service ─────────────────────────────────────────────────────────────────────────

pytestmark_live = pytest.mark.skipif(not LIVE, reason="litkb_live: set LITKB_LIVE=1 and start GROBID")


@pytest.fixture(scope="module")
def live_service():
    """Bring the service up AND hold the WSL distro open for the whole module.

    Without the hold, WSL tears the distro down between calls and the service vanishes
    mid-suite — the failure looks like a flaky 500 or a dropped connection, not a
    lifecycle problem (measured 2026-09-14).
    """
    if not grobid.start(wait=300):
        pytest.skip("GROBID did not come up")
    yield
    grobid.release_distro()


@pytest.mark.litkb_live
@pytestmark_live
def test_service_is_alive_and_is_0_9_1(live_service):
    assert grobid.health(), "GROBID is not answering /api/isalive"
    assert '"0.9.1"' in grobid.version()


@pytest.mark.litkb_live
@pytestmark_live
def test_live_paper_returns_tei_with_coordinates(live_service):
    pdf = os.environ.get("LITKB_LIVE_PDF")
    if not pdf or not os.path.exists(pdf):
        pytest.skip("set LITKB_LIVE_PDF to a real PDF on this machine")
    tei = grobid.process_pdf(pdf)
    assert grobid.header_title(tei)
    assert grobid.bibl_structs(tei)
    assert grobid.blocks(tei, kinds=("ref",))
    assert grobid.implausible_blocks(tei) == []


@pytest.mark.litkb_live
@pytestmark_live
def test_live_corrupted_pdf_errors_rather_than_returning_empty_tei(live_service, tmp_path):
    bad = tmp_path / "garbage.pdf"
    bad.write_bytes(b"this is not a pdf at all\n")
    with pytest.raises(grobid.GrobidError) as ei:
        grobid.process_pdf(str(bad), timeout=120)
    assert ei.value.status != 200

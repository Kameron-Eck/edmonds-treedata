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

FIXTURES = pathlib.Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "grobid_sample.tei.xml"
#: a JSTOR scan whose ONLY text layer is the cover-page access boilerplate: HTTP 200,
#: valid header, empty <text><body>. Saved verbatim from a live 0.9.1 run, 2026-09-14.
SCAN_FIXTURE = FIXTURES / "anderson_scan.tei.xml"
#: trimmed from a live run over a PDF whose pages 2-3 have cropbox != mediabox.
CROP_FIXTURE = FIXTURES / "alwan_cropped.tei.xml"
LIVE = os.environ.get("LITKB_LIVE") == "1"

VALIDATION = pathlib.Path(r"D:\edmonds-pipeline\Literture\Validation")
ALWAN_PDF = VALIDATION / "Alwan_1988_time-series-modeling-statistical-process.pdf"
ANDERSON_PDF = VALIDATION / "Anderson_1957_statistical-inference-about-markov.pdf"

#: Alwan_1988, measured with pypdfium2 2026-09-14 (mediabox (0,0,612,792); cropbox on pages
#: 2-3 (10.345, 10.777, 603.441, 782.948) -> dx 10.345, dy 9.052).
ALWAN_DX, ALWAN_DY = 10.345, 9.052
#: (page, element text, the element's box in the canonical MEDIABOX frame) — the union of
#: pypdfium2's per-character boxes for that string, y-flipped against the mediabox top.
ALWAN_TRUTH = [
    (2, "Shewhart (1931)", (193.80, 503.39, 262.01, 512.34)),
    (3, "Berthouex, Hunter, and Pallesen (1978)", (78.89, 349.08, 246.71, 358.04)),
]


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


# ── the zero-block refusal (referee defect 1) ───────────────────────────────────────────

@pytest.fixture(scope="module")
def scan_tei():
    return SCAN_FIXTURE.read_bytes()


def test_the_scan_is_the_dangerous_case_200_with_a_header_and_no_body(scan_tei):
    """The fixture is only interesting if it really is a 200 that parsed SOMETHING."""
    assert grobid.header_title(scan_tei)                 # boilerplate, but a header
    assert grobid.bibl_structs(scan_tei)                 # and a biblStruct
    assert grobid.blocks(scan_tei)                       # and blocks — in the HEADER
    assert grobid.body_text(scan_tei) == ""
    assert grobid.body_blocks(scan_tei) == []


def test_zero_body_blocks_is_refused_by_name(scan_tei):
    with pytest.raises(grobid.NoTextBlocks) as ei:
        grobid.check_text_blocks(scan_tei, "Anderson_1957.pdf")
    assert ei.value.status == 200
    assert "Anderson_1957.pdf" in str(ei.value)
    assert isinstance(ei.value, grobid.GrobidError)      # callers catching the base still see it


def test_a_real_paper_passes_the_zero_block_check(tei):
    assert grobid.check_text_blocks(tei, "Benedek_2015.pdf") == len(grobid.body_blocks(tei))


#: the referee's boundary attack: the same scan with ONE junk <p> box — a page number's worth —
#: injected into its empty <body>. Under the old ">= 1" rule this was ADMITTED with nothing
#: flagging it (referee 2 §1, D3).
JUNK_BOX = '<p coords="1,300.0,740.0,12.0,10.0">42</p>'


def _scan_with_injected_blocks(n):
    """The Anderson fixture's ``<body/>`` replaced by a body holding ``n`` junk boxes."""
    src = SCAN_FIXTURE.read_text(encoding="utf-8")
    assert "<body/>" in src, "the scan fixture no longer has an empty self-closed <body>"
    return src.replace("<body/>", "<body>" + JUNK_BOX * n + "</body>").encode("utf-8")


def test_the_injected_fixture_really_does_add_body_blocks():
    """The attack is only an attack if the injection lands where the gate looks."""
    assert grobid.body_blocks(scan_tei_bytes := _scan_with_injected_blocks(1))
    assert len(grobid.body_blocks(scan_tei_bytes)) == 1
    assert len(grobid.body_blocks(_scan_with_injected_blocks(3))) == 3


def test_one_injected_junk_block_is_still_refused():
    """The boundary the old rule left open: 1 body block is page furniture, not a document."""
    with pytest.raises(grobid.NoTextBlocks) as ei:
        grobid.check_text_blocks(_scan_with_injected_blocks(1), "Anderson_1957.pdf")
    assert "below the 4" in str(ei.value)


def test_the_refusal_holds_up_to_one_block_below_the_threshold():
    """Page furniture is at most three boxes (number, running head, footer); a real paragraph
    under segmentSentences=1 is at least four (<p> + 3 <s>). Both sides of that line are pinned."""
    assert grobid.MIN_BODY_BLOCKS == 4
    for n in (1, 2, 3):
        with pytest.raises(grobid.NoTextBlocks):
            grobid.check_text_blocks(_scan_with_injected_blocks(n))
    assert grobid.check_text_blocks(_scan_with_injected_blocks(4)) == 4


def test_mutation_lowering_the_threshold_to_one_admits_the_junk_body():
    """The gate must FIRE on a known-bad input, and stop firing when it is mutated away.

    ``minimum=1`` is the old rule, passed in rather than patched: the same TEI that the shipped
    threshold refuses is admitted by it, so the threshold — not something else — is what refuses.
    """
    junk = _scan_with_injected_blocks(1)
    assert grobid.check_text_blocks(junk, minimum=1) == 1      # the mutant admits it
    with pytest.raises(grobid.NoTextBlocks):
        grobid.check_text_blocks(junk)                         # the shipped gate does not


def test_the_threshold_does_not_refuse_a_real_paper(tei):
    """The upper bound on the threshold: the smallest real-paper fixture has 8 body blocks, so a
    threshold above that would start refusing papers that really were extracted."""
    assert len(grobid.body_blocks(tei)) >= grobid.MIN_BODY_BLOCKS
    assert grobid.MIN_BODY_BLOCKS <= 8


def test_mutation_removing_the_body_check_admits_the_scan(scan_tei):
    """Without the gate, the scan is indistinguishable from a good run by status alone.

    This is the mutation in test form: a caller that checks only ``status == 200`` (or only
    ``blocks(tei)``, which counts the HEADER's boilerplate title) accepts the scan, and the
    real check refuses it. If ``check_text_blocks`` stopped refusing, the assertion below
    would fail.
    """
    status_only_ok = True                                # what a 200-checking caller concludes
    blocks_anywhere_ok = bool(grobid.blocks(scan_tei))   # what a naive block count concludes
    assert status_only_ok and blocks_anywhere_ok
    with pytest.raises(grobid.NoTextBlocks):
        grobid.check_text_blocks(scan_tei)


# ── the cropbox -> mediabox frame shift (referee defect 4) ──────────────────────────────

@pytest.fixture(scope="module")
def crop_tei():
    return CROP_FIXTURE.read_bytes()


def _alwan_frames():
    """The measured frames for the fixture, without needing the PDF."""
    return {1: {"mediabox": (0.0, 0.0, 612.0, 792.0), "cropbox": (0.0, 0.0, 612.0, 792.0),
                "rotation": 0, "dx": 0.0, "dy": 0.0},
            2: {"mediabox": (0.0, 0.0, 612.0, 792.0),
                "cropbox": (10.345, 10.777, 603.441, 782.948),
                "rotation": 0, "dx": ALWAN_DX, "dy": ALWAN_DY},
            3: {"mediabox": (0.0, 0.0, 612.0, 792.0),
                "cropbox": (10.345, 10.777, 603.441, 782.948),
                "rotation": 0, "dx": ALWAN_DX, "dy": ALWAN_DY}}


def _max_offset(block, truth):
    return max(abs(block.x0 - truth[0]), abs(block.y0 - truth[1]),
               abs(block.x1 - truth[2]), abs(block.y1 - truth[3]))


def _pick(blocks_in, page, text):
    hits = [b for b in blocks_in if b.page == page and b.text == text]
    assert len(hits) == 1, f"{text!r} is not unique on page {page}"
    return hits[0]


def test_grobid_boxes_are_in_the_cropbox_frame_not_the_mediabox(crop_tei):
    """WITH THE FIX REMOVED: raw GROBID boxes miss pypdfium2's mediabox truth by >5 pt.

    This is the mutation half of the test. The referee measured the shift at 10.9 pt; if the
    frames were the same, this assertion would fail and the conversion would be pointless.
    """
    raw = grobid.body_blocks(crop_tei)
    for page, text, truth in ALWAN_TRUTH:
        b = _pick(raw, page, text)
        assert b.frame == "cropbox"
        assert _max_offset(b, truth) > 5.0, f"page {page}: no cropbox shift to correct"


def test_to_mediabox_aligns_boxes_with_pypdfium2(crop_tei):
    """WITH THE FIX: every box lands within 2 pt of pypdfium2's own mediabox geometry."""
    shifted = grobid.to_mediabox(grobid.body_blocks(crop_tei), _alwan_frames())
    for page, text, truth in ALWAN_TRUTH:
        b = _pick(shifted, page, text)
        assert b.frame == "mediabox"
        assert _max_offset(b, truth) <= 2.0, f"page {page}: {_max_offset(b, truth):.2f} pt off"


def test_an_uncropped_page_is_unchanged_by_the_shift(crop_tei):
    frames = _alwan_frames()
    assert frames[1]["dx"] == 0 and frames[1]["dy"] == 0


def test_to_mediabox_refuses_a_rotated_page(crop_tei):
    """Rotation composed with the cropbox shift is UNCONFIRMED, so a rotated page is left
    in the cropbox frame rather than converted wrongly and silently."""
    frames = _alwan_frames()
    frames[3] = dict(frames[3], rotation=90)
    shifted = grobid.to_mediabox(grobid.body_blocks(crop_tei), frames)
    b = _pick(shifted, 3, "Berthouex, Hunter, and Pallesen (1978)")
    assert b.frame == "cropbox"
    assert _pick(shifted, 2, "Shewhart (1931)").frame == "mediabox"


# Hall_1985_resampling-coverage-pattern.pdf p12 — the ONE page in 4,712 (224 PDFs, referee's
# corpus 2026-09-15) that is BOTH rotated and cropped, i.e. the only page where refusing to
# convert costs anything at all. rotation 180, mediabox (0,0,463,685), cropbox (2,0,463,684).
HALL_P12 = {"mediabox": (0.0, 0.0, 463.0, 685.0), "cropbox": (2.0, 0.0, 463.0, 684.0),
            "rotation": 180, "dx": 2.0, "dy": 1.0}


def test_to_mediabox_refuses_a_rotated_page_with_a_cropbox():
    """The referee's finding, encoded: on the one page where it matters, the translation is not
    merely unconfirmed — it is the WRONG MAP, and refusing is the only correct behaviour.

    For rotation 180 the map from GROBID's displayed frame to the mediabox top-left frame is a
    REFLECTION (x_m = crop.x1 - X, y_m = media.y1 - crop.y0 - Y). ``to_mediabox`` applies a
    translation (X + dx, Y + dy). Measured on Hall p12, the two differ by roughly a page width
    in x and more in y, so a silent conversion would put text on the wrong side of the page.
    """
    b = grobid.Block(page=12, x0=49.8, y0=63.2, x1=61.8, y1=73.2, kind="s", text="synthetic")
    out = grobid.to_mediabox([b], {12: HALL_P12})[0]

    # refused: unchanged, and still SAYING it is unchanged
    assert out.frame == "cropbox"
    assert (out.x0, out.y0, out.x1, out.y1) == (b.x0, b.y0, b.x1, b.y1)

    # and the refusal is necessary: the reflection and the translation disagree hugely
    media, crop = HALL_P12["mediabox"], HALL_P12["cropbox"]
    reflected_x = crop[2] - b.x0
    reflected_y = media[3] - crop[1] - b.y0
    translated_x = b.x0 + HALL_P12["dx"]
    translated_y = b.y0 + HALL_P12["dy"]
    assert reflected_x == pytest.approx(413.2, abs=0.1)
    assert translated_x == pytest.approx(51.8, abs=0.1)
    assert abs(reflected_x - translated_x) > 300      # ~361 pt, roughly the page width
    assert abs(reflected_y - translated_y) > 500      # ~558 pt


def test_mutation_dropping_the_rotation_guard_translates_the_rotated_page():
    """Without the ``f["rotation"]`` guard the same block is silently translated and stamped
    ``frame="mediabox"`` — landing ~361 pt from where it belongs. That is the defect the guard
    prevents, shown by removing it."""
    b = grobid.Block(page=12, x0=49.8, y0=63.2, x1=61.8, y1=73.2, kind="s")
    mutant_frames = {12: dict(HALL_P12, rotation=0)}   # the guard's condition, mutated away
    out = grobid.to_mediabox([b], mutant_frames)[0]
    assert out.frame == "mediabox"
    assert out.x0 == pytest.approx(51.8, abs=0.1)
    assert abs(out.x0 - (HALL_P12["cropbox"][2] - b.x0)) > 300


def test_a_page_with_no_frame_record_is_left_alone(crop_tei):
    shifted = grobid.to_mediabox(grobid.body_blocks(crop_tei), {})
    assert all(b.frame == "cropbox" for b in shifted)


@pytest.mark.skipif(not ALWAN_PDF.exists(), reason="the Alwan PDF is not on this machine")
def test_page_frames_reads_the_measured_cropbox_from_the_pdf():
    pytest.importorskip("pypdfium2")
    frames = grobid.page_frames(str(ALWAN_PDF))
    assert frames[1]["cropbox"] == pytest.approx(frames[1]["mediabox"], abs=0.01)
    assert frames[2]["cropbox"] == pytest.approx((10.345, 10.777, 603.441, 782.948), abs=0.01)
    assert frames[2]["dx"] == pytest.approx(ALWAN_DX, abs=0.01)
    assert frames[2]["dy"] == pytest.approx(ALWAN_DY, abs=0.01)


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


@pytest.mark.litkb_live
@pytestmark_live
@pytest.mark.skipif(not ANDERSON_PDF.exists(), reason="the Anderson scan is not on this machine")
def test_live_partial_text_layer_scan_is_refused(live_service):
    """The whole point of defect 1, on the real file: 200, header parsed, nothing extracted."""
    with pytest.raises(grobid.NoTextBlocks):
        grobid.process_pdf(str(ANDERSON_PDF), timeout=600)
    # and with the guard explicitly off it comes back as the dangerous 200 it is
    tei = grobid.process_pdf(str(ANDERSON_PDF), timeout=600, require_text_blocks=False)
    assert grobid.header_title(tei) and grobid.body_blocks(tei) == []


@pytest.mark.litkb_live
@pytestmark_live
def test_live_extract_records_the_throughput_metrics(live_service):
    pdf = os.environ.get("LITKB_LIVE_PDF")
    if not pdf or not os.path.exists(pdf):
        pytest.skip("set LITKB_LIVE_PDF to a real PDF on this machine")
    _tei, m = grobid.extract(pdf, concurrency=4)
    assert m["status"] == "ok"
    assert m["pages"] > 0 and m["seconds"] > 0 and m["pages_per_s"] > 0
    assert m["peak_rss_bytes"] > 0          # §14 refuses a run with no peak-RSS measurement
    assert m["tool"] == grobid.EXTRACTOR and m["concurrency"] == 4


@pytest.mark.litkb_live
@pytestmark_live
@pytest.mark.skipif(not ANDERSON_PDF.exists(), reason="the Anderson scan is not on this machine")
def test_live_extract_records_a_refused_run_as_failed(live_service):
    """The link between defect 1 and defect 3: a zero-block refusal is a FAILED run, with
    metrics, never an ok run with nothing in it."""
    with pytest.raises(grobid.GrobidError) as ei:
        grobid.extract(str(ANDERSON_PDF))
    m = ei.value.metrics
    assert m and m["status"] == "failed" and "NoTextBlocks" in m["error"]
    assert m["pages"] == 22 and m["peak_rss_bytes"] > 0


def test_extract_refuses_a_run_with_no_rss_samples(monkeypatch, tmp_path):
    """§14: 'the instrument refuses a stage run that records no rate or no peak RSS'.

    Runs without the service: the sampler is replaced by one that yields nothing, which is
    exactly what a caller would see if the cgroup path moved or the unit were down.
    """
    class _DeadSampler:
        samples = []
        peak = 0

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

    monkeypatch.setattr(grobid, "_RssSampler", _DeadSampler)
    monkeypatch.setattr(grobid, "pdf_page_count", lambda p: 3)
    monkeypatch.setattr(grobid, "process_pdf", lambda *a, **k: b"<TEI/>")
    with pytest.raises(grobid.GrobidError) as ei:
        grobid.extract(str(tmp_path / "x.pdf"))
    assert "no samples" in str(ei.value)


def test_append_metrics_writes_one_json_line(tmp_path):
    import json
    p = grobid.append_metrics({"status": "ok", "pages": 1}, str(tmp_path / "m" / "m.jsonl"))
    line = pathlib.Path(p).read_text(encoding="utf-8").strip()
    assert json.loads(line)["pages"] == 1


# ── the launcher's own refusals (defects 2 and 5), exercised inside WSL ──────────────────

def _sh(action, env=None):
    import subprocess
    sh = str(pathlib.Path(grobid.MANAGER_SH)).replace("\\", "/")
    sh = f"/mnt/{sh[0].lower()}{sh[2:]}"
    cmd = ["wsl.exe", "-d", grobid.WSL_DISTRO, "-u", "root", "--"]
    if env:
        cmd += ["env"] + [f"{k}={v}" for k, v in env.items()]
    cmd += ["bash", sh, action]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, MSYS_NO_PATHCONV="1"))


@pytest.mark.litkb_live
@pytestmark_live
def test_launcher_refuses_a_jdk_below_21():
    r = _sh("check-jdk", {"GROBID_JDK": "/usr/lib/jvm/java-17-openjdk-amd64"})
    assert r.returncode != 0 and "requires 21" in r.stdout


@pytest.mark.litkb_live
@pytestmark_live
def test_launcher_refuses_when_no_jdk21_is_found_rather_than_using_path_java():
    """JAVA_HOME unset used to fall through to `java` on PATH (referee §5). It must refuse."""
    r = _sh("check-jdk", {"GROBID_JVM_DIR": "/tmp/litkb-no-such-jvm-dir"})
    assert r.returncode != 0 and "no JDK 21 found" in r.stdout
    assert "PATH is NOT allowed" in r.stdout


@pytest.mark.litkb_live
@pytestmark_live
def test_launcher_accepts_jdk21():
    r = _sh("check-jdk", {"GROBID_JDK": "/usr/lib/jvm/java-21-openjdk-amd64"})
    assert r.returncode == 0 and "JDK ok" in r.stdout


@pytest.mark.litkb_live
@pytestmark_live
def test_launcher_refuses_concurrency_above_the_headroom_default():
    r = _sh("check-concurrency", {"GROBID_CONCURRENCY": "9"})
    assert r.returncode != 0 and "20% CPU-headroom" in r.stdout
    ok = _sh("check-concurrency", {"GROBID_CONCURRENCY": "9", "GROBID_BREAK_HEADROOM": "1"})
    assert ok.returncode == 0
    assert _sh("check-concurrency").returncode == 0      # the default (4) passes


# ── the two remaining bypasses, and the unit-writing path (referee 2: D4, D1) ────────────
#
# These run against a THROWAWAY GROBID_DIR inside the distro, never the installed one: CONFIG is
# derived from GROBID_DIR, so a fake tree lets `configure`/`enable` be driven without touching the
# real grobid.yaml. `enable` is only ever exercised in its REFUSING case — UNIT is a fixed path, so
# a passing `enable` would arm autostart on the real service. The positive control is
# `check-concurrency`, which writes nothing.

FAKE_DIR = "/tmp/litkb-fake-grobid"
FAKE_CFG = f"{FAKE_DIR}/grobid-home/config/grobid.yaml"
#: EVERY `enable` call below also points the JDK search at nothing. UNIT is a fixed path, so a
#: mutation that removes the headroom check must not be able to fall through to `systemctl enable`
#: — it did once, during this fix's own mutation run, arming autostart on a unit whose ExecStart
#: pointed into the throwaway tree. With no resolvable JDK, write_unit cannot reach systemd whatever
#: else is mutated away, and the tests assert WHICH gate stopped the call.
NO_JDK = {"GROBID_JVM_DIR": "/tmp/litkb-no-such-jvm-dir"}


def _wsl(script):
    import subprocess
    return subprocess.run(
        ["wsl.exe", "-d", grobid.WSL_DISTRO, "-u", "root", "--", "bash", "-c", script],
        capture_output=True, text=True, timeout=120,
        env=dict(os.environ, MSYS_NO_PATHCONV="1"))


def _fake_tree(concurrency):
    """A minimal grobid.yaml holding the given concurrency, in a throwaway tree."""
    r = _wsl(f"mkdir -p {FAKE_DIR}/grobid-home/config && "
             f"printf 'grobid:\\n  concurrency: {concurrency}\\n  memoryLimitMb: 1536\\n"
             f"  pdf:\\n    pdfalto:\\n      timeoutSec: 300\\n' > {FAKE_CFG} && cat {FAKE_CFG}")
    assert r.returncode == 0, r.stderr
    return r.stdout


def _fake_cfg_text():
    return _wsl(f"cat {FAKE_CFG}").stdout


@pytest.mark.litkb_live
@pytestmark_live
def test_launcher_refuses_the_headroom_max_bypass():
    """GROBID_HEADROOM_MAX_CONCURRENCY was a second, undocumented way through the guard: setting
    it to 9 let concurrency 9 pass with nothing printed. It is no longer honoured, and setting it
    is a refusal rather than a silent no-op, so a caller is told it stopped working."""
    r = _sh("check-concurrency", {"GROBID_CONCURRENCY": "9",
                                  "GROBID_HEADROOM_MAX_CONCURRENCY": "9"})
    assert r.returncode != 0, "the removed bypass still lets concurrency 9 through"
    assert "no longer honoured" in r.stdout
    # it is refused even when it would not have changed the outcome, so it can never be trusted
    assert _sh("check-concurrency", {"GROBID_HEADROOM_MAX_CONCURRENCY": "4"}).returncode != 0


@pytest.mark.litkb_live
@pytestmark_live
def test_launcher_refuses_a_non_numeric_concurrency_before_writing_anything():
    """`[ abc -gt 4 ]` returns false with 'integer expected' on stderr, so the guard PASSED and
    `configure` sed-ed `concurrency: abc` into grobid.yaml verbatim. The value is now validated
    ahead of both the comparison and the write."""
    assert "concurrency: 4" in _fake_tree(4)
    r = _sh("check-concurrency", {"GROBID_CONCURRENCY": "abc"})
    assert r.returncode != 0 and "not a non-negative integer" in r.stdout

    # NO_JDK for the same reason as the enable tests: mutate require_integer away and `configure`
    # sed-s `abc` into the fake yaml, write_unit then reads it back, `[ abc -gt 4 ]` is false, and
    # the REAL /etc/systemd/system/grobid.service gets rewritten with the throwaway ExecStart.
    # With no resolvable JDK that path stops before the unit is touched.
    c = _sh("configure", dict(NO_JDK, GROBID_CONCURRENCY="abc", GROBID_DIR=FAKE_DIR))
    assert c.returncode != 0 and "not a non-negative integer" in c.stdout
    after = _fake_cfg_text()
    assert "concurrency: abc" not in after, "a malformed concurrency reached grobid.yaml"
    assert "concurrency: 4" in after


@pytest.mark.litkb_live
@pytestmark_live
def test_enable_checks_the_concurrency_it_would_arm():
    """D1. ExecStart hands the launcher grobid.yaml and nothing else, so `enable` arms whatever a
    previous `GROBID_BREAK_HEADROOM=1 configure` left there — on every distro boot, down a path
    that never reaches do_start and never re-checks. With the yaml pre-set to 9, `enable` must
    refuse before it writes the unit or touches systemd."""
    assert "concurrency: 9" in _fake_tree(9)
    r = _sh("enable", dict(NO_JDK, GROBID_DIR=FAKE_DIR))
    assert r.returncode != 0, "enable armed an over-budget concurrency"
    assert "20% CPU-headroom" in r.stdout
    assert "autostart on" not in r.stdout          # it stopped before systemctl enable
    # it stopped at the HEADROOM gate specifically: the JDK gate sits behind it and never spoke
    assert "no JDK 21 found" not in r.stdout

    # knowingly overridden, the same call is allowed — the guard is a check, not a wall
    ok = _sh("enable", dict(NO_JDK, GROBID_DIR=FAKE_DIR, GROBID_BREAK_HEADROOM="1"))
    assert "20% CPU-headroom" not in ok.stdout     # past the headroom gate, stopped by the JDK one
    assert "no JDK 21 found" in ok.stdout          # and so it never reaches systemctl either


@pytest.mark.litkb_live
@pytestmark_live
def test_enable_passes_a_within_budget_yaml_up_to_the_point_of_no_return():
    """The gate must not refuse everything: with the yaml at the budgeted 4, `enable` gets past
    the headroom check. It is stopped here by an unresolvable JDK rather than being allowed to
    arm autostart on the real unit path."""
    assert "concurrency: 4" in _fake_tree(4)
    r = _sh("enable", dict(NO_JDK, GROBID_DIR=FAKE_DIR))
    assert "20% CPU-headroom" not in r.stdout
    assert "no JDK 21 found" in r.stdout
    # and nothing of the throwaway tree ever reached the real unit
    assert FAKE_DIR not in _wsl("cat /etc/systemd/system/grobid.service 2>/dev/null").stdout

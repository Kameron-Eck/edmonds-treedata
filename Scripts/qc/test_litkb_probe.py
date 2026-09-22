"""`litkb.extract.probe` — the page facts S4's queue, classifier and bind path share.

Real files are COPIED from the corpus into a tmp dir (the corpus is read-only to tests); a test whose
real file is absent on this machine skips, it does not pass. The corrupt PDF is CONSTRUCTED, and says
so in its name.
"""

import shutil
from pathlib import Path

import pytest

from litkb.extract import probe

LIT = Path(r"D:\edmonds-pipeline\Literture")
SCAN = LIT / "Validation" / "Anderson_1957_statistical-inference-about-markov.pdf"   # JSTOR page2pdf scan
NATIVE = LIT / "Validation" / "Efron_1986_how-biased-apparent-error-rate.pdf"           # native, 11 pp
PAGE1_ONLY_FALSE = LIT / "_litkb_staging" / "incoming" / "t286_Crowder_2017_bernoulli-cusum.download"
ALL_SCAN = LIT / "Validation" / "Ogata_1998_space-time-point-process-models.pdf"         # 0 chars, every page
FIGURE_PAGE = LIT / "Validation" / "Pauls_2025_capturing-temporal-dynamics-large-scale.pdf"  # p16 = figure + caption


def _copy(src, tmp_path):
    if not src.exists():
        pytest.skip(f"real corpus file absent on this machine: {src}")
    dst = tmp_path / src.name
    shutil.copyfile(src, dst)
    return dst


def test_a_native_file_counts_its_pages_and_has_no_image_page(tmp_path):
    p = _copy(NATIVE, tmp_path)
    assert probe.is_pdf_magic(p)
    assert probe.probe_pages(p) == 11
    chars = probe.page_text_chars(p)
    assert len(chars) == 11 and probe.image_page_numbers(p) == []


def test_a_scan_is_image_pages_throughout_apart_from_its_cover_sheet(tmp_path):
    """Anderson 1957 is a JSTOR page2pdf scan: page 1 is JSTOR's cover sheet (native text, ~160
    characters) and every page after it has no text layer and one page-sized raster image —
    decision D13's image pages are exactly pages 2..n."""
    p = _copy(SCAN, tmp_path)
    n = probe.probe_pages(p)
    assert probe.page_text_chars(p)[0] > 0
    assert probe.image_page_numbers(p) == list(range(2, n + 1))


def test_an_all_scan_document_is_image_pages_everywhere(tmp_path):
    """Ogata 1998: 0 native characters and tiled raster images on all 24 pages."""
    p = _copy(ALL_SCAN, tmp_path)
    assert probe.image_page_numbers(p) == list(range(1, probe.probe_pages(p) + 1))


def test_a_figure_page_with_its_caption_is_not_an_image_page(tmp_path):
    """Decision D13's reason. Pauls_2025 p16 is a figure page: 156 native characters (its caption)
    and one raster image — under the binding's 200, so the first rule routed a native paper to OCR.
    A short page is not a scan page. MUTATION (recorded in the S4 report): the rule reverted to
    `chars < MIN_PAGE_TEXT_CHARS` -> p16 comes back -> red."""
    p = _copy(FIGURE_PAGE, tmp_path)
    chars, images = probe.page_text_chars(p), probe.page_raster_images(p)
    assert 0 < chars[15] < probe.MIN_PAGE_TEXT_CHARS and images[15] >= 1, (chars[15], images[15])
    assert probe.image_page_numbers(p) == []


def test_image_pages_refuses_lists_of_two_documents():
    with pytest.raises(probe.ProbeError):
        probe.image_pages([0, 0], [1])


def test_the_stored_page1_flag_is_not_the_per_page_fact(tmp_path):
    """Crowder_2017 is stored `has_text_layer=false` (the binding reads page 1 only) yet carries a
    text layer after page 1: the per-page probe must see text pages, or OCR would be routed to a
    native document."""
    p = _copy(PAGE1_ONLY_FALSE, tmp_path)
    chars = probe.page_text_chars(p)
    assert probe.image_page_numbers(p) == [], chars


def test_constructed_corrupt_pdf_raises_probe_error_not_a_count(tmp_path):
    """CONSTRUCTED: the PDF signature followed by garbage. The magic check passes; the page count
    must RAISE — a probe that returned 0 or None here is the defect `probe-error` exists to close."""
    bad = tmp_path / "CONSTRUCTED_corrupt_signature_only.pdf"
    bad.write_bytes(b"%PDF-1.7\n" + b"\x00garbage, no xref, no trailer\n" * 40)
    assert probe.is_pdf_magic(bad)
    with pytest.raises(probe.ProbeError):
        probe.probe_pages(bad)
    with pytest.raises(probe.ProbeError):
        probe.page_text_chars(bad)


def test_a_failed_probe_leaves_the_file_free_to_move(tmp_path):
    """CONSTRUCTED: a %PDF- header and %%EOF trailer around a catalog whose /Pages is not a
    dictionary. The probe must raise AND release the file: the bind path quarantines exactly this
    file by MOVING it, and on Windows a handle pdfium kept after the failed load made that move fail
    with WinError 32 (builder-B, S4 run 3)."""
    import os

    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"(not a dict)"]
    body, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(body))
        body += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(body)
    body += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    body += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    bad = tmp_path / "CONSTRUCTED_unopenable_catalog.pdf"
    bad.write_bytes(bytes(body))
    assert probe.is_pdf_magic(bad)
    for fn in (probe.probe_pages, probe.page_text_chars):
        with pytest.raises(probe.ProbeError):
            fn(bad)
        moved = bad.with_name(bad.stem + ".moved.pdf")
        os.rename(bad, moved)
        os.rename(moved, bad)


def test_a_missing_file_raises_and_is_not_pdf(tmp_path):
    missing = tmp_path / "nothing_here.pdf"
    assert not probe.is_pdf_magic(missing)
    with pytest.raises(probe.ProbeError):
        probe.probe_pages(missing)


def test_the_cap_is_the_binding_ceiling_until_ruled_otherwise():
    """S4 run 3 decision D1 names its source; if the ruling changes the value, this test changes
    with it — the point is that the cap is one named constant, not a literal at each site."""
    from litkb.admit import binding
    assert probe.EXTRACT_PAGE_CAP == binding.OCR_BIND_MAX_PAGES
    assert probe.MIN_PAGE_TEXT_CHARS == binding.MIN_TEXT_CHARS

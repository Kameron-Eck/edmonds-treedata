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
    assert len(chars) == 11 and probe.image_pages(chars) == []


def test_a_scan_is_image_pages_throughout_apart_from_a_cover_stamp(tmp_path):
    """Anderson 1957 is a JSTOR page2pdf scan: a cover stamp on page 1 (~150-170 characters,
    data survey D1) and no text layer after it — every page is under the page threshold."""
    p = _copy(SCAN, tmp_path)
    chars = probe.page_text_chars(p)
    assert len(chars) == probe.probe_pages(p)
    assert probe.image_pages(chars) == list(range(1, len(chars) + 1)), chars


def test_the_stored_page1_flag_is_not_the_per_page_fact(tmp_path):
    """Crowder_2017 is stored `has_text_layer=false` (the binding reads page 1 only) yet carries a
    text layer after page 1: the per-page probe must see text pages, or OCR would be routed to a
    native document."""
    p = _copy(PAGE1_ONLY_FALSE, tmp_path)
    chars = probe.page_text_chars(p)
    assert len(probe.image_pages(chars)) < len(chars), chars


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

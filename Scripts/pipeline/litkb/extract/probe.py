"""What a PDF's pages ARE, read without extracting anything — the one home S4's queue, its
readability classifier and the acquisition bind path share (LITKB_WORKPLAN.md "### S4").

Two facts, both read by pypdfium2 (the library `docling_worker._page_count` already counts pages
with, pinned in requirements-litkb.txt):

- **how many pages** — :func:`probe_pages`. It RAISES :class:`ProbeError` when the document cannot
  be opened or counted. That is the fail-closed half the plan's `probe-error` class needs:
  `binding.pdf_info` never raises — a failing `pdfinfo` returns ``{}`` and the file binds with
  `pages` NULL (S4 run 3 code survey C8) — so "the page count could not be read" had no way to
  become a refusal.
- **how much native text each page carries, and whether it carries a raster image** —
  :func:`page_text_chars` (normalised the way the binding's page-1 rule normalises,
  `resolver._norm_text`) and :func:`page_raster_images`. The binding rule reads PAGE 1 ONLY
  (`binding.py` `bind`, the `text_layer` line), which is why `Crowder_2017` and `Abdulkader_2020`
  are stored `has_text_layer=false` while carrying full text layers after their first page (S4 run 3
  data survey D2); the per-page facts here, not the stored page-1 flag, are what route a file to OCR.

**An IMAGE page is a page with ZERO native characters that carries at least one raster image**
(:func:`image_pages`; S4 run 3 decision D13). Not "under the binding's 200": a SHORT page is not a
scan page. Measured 2026-09-22 (orchestrator, read-only): every scan page after its cover — Anderson
1957, Hudson 1978, Hwang 1982 pages 2+, all 24 of Ogata 1998 — has 0 characters and 1-18 raster
images covering 0.5-1.0 of the page; the JSTOR cover sheets have 147-160 characters (text, not a
scan of the article); and the figure pages the 200 rule wrongly routed to OCR — Pauls_2025 p16 (156),
Pesonen_2026 p20 (126), Guo_2019 p6 (135) — carry their captions as native text. The rule's stated
limit: a scan that stamps a line of native text on EVERY page is not routed by it; the corpus holds
none today. A zero-character page with no raster image (blank, or text drawn as vector paths) is
not an image page either — OCR over a bitmap region would find nothing to read on it.

The text here is pdfium's, not pdftotext's (the binding reads page 1 with `pdftotext -layout`), so
a page-1 count here can differ from the stored flag's.
"""

from litkb.admit.binding import MIN_TEXT_CHARS
from litkb.admit.resolver import _norm_text

#: The extraction page cap (plan "### S4": "an enforced, fail-closed extraction page cap"). A file
#: with more pages than this is never started: it is classed `over-page-cap`. SOURCE — the ruling
#: `litkb-extract-page-cap` (Kam, 2026-09-22): no extraction cap value existed in code or docs (S4
#: run 3 code survey C4); this is the one reasoned page ceiling the code already holds,
#: `binding.OCR_BIND_MAX_PAGES` ("a book is not a cover sheet"). The corpus's longest active file is
#: 101 pages (data survey D3), so the cap refuses book-sized volumes only.
EXTRACT_PAGE_CAP = 400

#: The binding's page-1 threshold (normalised characters), kept here for REPORTING short pages; it
#: does NOT decide an image page — decision D13, see the module docstring.
MIN_PAGE_TEXT_CHARS = MIN_TEXT_CHARS

#: How far into the file the PDF signature may sit. Readers tolerate leading bytes before `%PDF-`;
#: 1,024 is the window the PDF reference's implementation note gives for that tolerance.
_MAGIC_WINDOW = 1024


class ProbeError(Exception):
    """The page count (or a page's text) could not be read. Fail closed: never bind, never extract."""


def is_pdf_magic(path):
    """True when `%PDF-` appears in the first 1,024 bytes. False for a missing or unreadable file."""
    try:
        with open(path, "rb") as fh:
            return b"%PDF-" in fh.read(_MAGIC_WINDOW)
    except OSError:
        return False


def _open(path):
    """The document, opened on a file handle THIS function owns (S4 run 3, builder-B): handed a path,
    pypdfium2 5.13.0 leaves the file open after a FAILED load, and on Windows the file then cannot be
    renamed for the life of the process (measured: `os.rename` -> WinError 32, also after
    `gc.collect()`), so a bind-path refusal could not move the bytes to `_quarantine/`. Handed a
    handle, it holds nothing after a failure, and `autoclose` closes the handle with the document."""
    import pypdfium2 as pdfium
    try:
        fh = open(path, "rb")
    except OSError as exc:    # a missing or unreadable path
        raise ProbeError(f"{type(exc).__name__}: {exc}") from exc
    try:
        return pdfium.PdfDocument(fh, autoclose=True)
    except Exception as exc:  # pdfium raises PdfiumError
        fh.close()
        raise ProbeError(f"{type(exc).__name__}: {exc}") from exc


def probe_pages(path):
    """The page count. Raises :class:`ProbeError` — never returns None, 0 or a guess."""
    doc = _open(path)
    try:
        n = len(doc)
    except Exception as exc:
        raise ProbeError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        doc.close()
    if n < 1:
        raise ProbeError("the document reports no pages")
    return n


def page_text_chars(path):
    """Normalised native-text characters on each page, in page order (index 0 = page 1).

    Raises :class:`ProbeError` when the document or any page cannot be read; a page whose text
    layer is simply empty is 0, not an error."""
    doc = _open(path)
    out = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            try:
                tp = page.get_textpage()
                try:
                    out.append(len(_norm_text(tp.get_text_range())))
                finally:
                    tp.close()
            finally:
                page.close()
    except ProbeError:
        raise
    except Exception as exc:
        raise ProbeError(f"page {len(out) + 1}: {type(exc).__name__}: {exc}") from exc
    finally:
        doc.close()
    if not out:
        raise ProbeError("the document reports no pages")
    return out


def page_raster_images(path):
    """Raster image objects on each page, in page order (index 0 = page 1), counted through form
    XObjects (``max_depth=2``). Raises :class:`ProbeError` like the other probes."""
    import pypdfium2.raw as pdfium_c
    doc = _open(path)
    out = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            try:
                out.append(sum(1 for _ in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE],
                                                           max_depth=2)))
            finally:
                page.close()
    except ProbeError:
        raise
    except Exception as exc:
        raise ProbeError(f"page {len(out) + 1}: {type(exc).__name__}: {exc}") from exc
    finally:
        doc.close()
    if not out:
        raise ProbeError("the document reports no pages")
    return out


def image_pages(chars, images):
    """1-based numbers of the IMAGE pages (decision D13): zero native characters AND at least one
    raster image, from a :func:`page_text_chars` list and a :func:`page_raster_images` list of the
    same document."""
    if len(chars) != len(images):
        raise ProbeError(f"page lists disagree: {len(chars)} text counts, {len(images)} image counts")
    return [i + 1 for i, (n, k) in enumerate(zip(chars, images)) if n == 0 and k > 0]


def image_page_numbers(path):
    """:func:`image_pages` of the file at ``path`` — the one call routing and classification make."""
    return image_pages(page_text_chars(path), page_raster_images(path))

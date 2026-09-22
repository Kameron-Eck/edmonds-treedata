"""What a PDF's pages ARE, read without extracting anything — the one home S4's queue, its
readability classifier and the acquisition bind path share (LITKB_WORKPLAN.md "### S4").

Two facts, both read by pypdfium2 (the library `docling_worker._page_count` already counts pages
with, pinned in requirements-litkb.txt):

- **how many pages** — :func:`probe_pages`. It RAISES :class:`ProbeError` when the document cannot
  be opened or counted. That is the fail-closed half the plan's `probe-error` class needs:
  `binding.pdf_info` never raises — a failing `pdfinfo` returns ``{}`` and the file binds with
  `pages` NULL (S4 run 3 code survey C8) — so "the page count could not be read" had no way to
  become a refusal.
- **how much native text each page carries** — :func:`page_text_chars`, normalised the way the
  binding's page-1 rule normalises (`resolver._norm_text`) and judged against the same threshold
  (`binding.MIN_TEXT_CHARS`). The binding rule reads PAGE 1 ONLY (`binding.py` `bind`, the
  `text_layer` line), which is why `Crowder_2017` and `Abdulkader_2020` are stored
  `has_text_layer=false` while carrying full text layers after their first page (S4 run 3 data
  survey D2). A page under the threshold here is an IMAGE page — every page of a scan, or the odd
  page of a mixed document — and that, not the stored page-1 flag, is what routes a file to OCR.

The text here is pdfium's, not pdftotext's (the binding reads page 1 with `pdftotext -layout`), so
a page-1 count here can differ from the stored flag's; the threshold is the same number either way.
"""

from litkb.admit.binding import MIN_TEXT_CHARS
from litkb.admit.resolver import _norm_text

#: The extraction page cap (plan "### S4": "an enforced, fail-closed extraction page cap"). A file
#: with more pages than this is never started: it is classed `over-page-cap`. SOURCE — S4 run 3
#: decision D1, PROVISIONAL pending Kam under his away-mode rule: no extraction cap value existed in
#: code or docs (code survey C4); this is the one reasoned page ceiling the code already holds,
#: `binding.OCR_BIND_MAX_PAGES` ("a book is not a cover sheet"). The corpus's longest active file is
#: 101 pages (data survey D3), so the cap refuses book-sized volumes only.
EXTRACT_PAGE_CAP = 400

#: Normalised characters under which a page has no usable text layer — the binding's page-1
#: threshold, applied to every page.
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
    import pypdfium2 as pdfium
    try:
        return pdfium.PdfDocument(str(path))
    except Exception as exc:  # pdfium raises PdfiumError; a missing path raises FileNotFoundError
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


def image_pages(chars):
    """1-based numbers of the pages under :data:`MIN_PAGE_TEXT_CHARS` in a :func:`page_text_chars` list."""
    return [i + 1 for i, n in enumerate(chars) if n < MIN_PAGE_TEXT_CHARS]

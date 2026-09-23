"""Docling stage-3 adapter — DoclingDocument JSON -> the canonical §7.1 block model.

Stage 3 of the design's extraction pipeline (§7): layout, reading order, table structure,
figure regions, OCR for scans, and — with enrichment on — LaTeX for formula regions.
Docling itself never runs in this process: :func:`run` launches
:mod:`litkb.extract.docling_worker` in the extraction venv and this module maps the JSON it
writes. So the project's environment needs nothing but the standard library (and pypdfium2
for the mediabox shift), which is what keeps ``qc/check.py`` free of a 2.5 GB dependency (venv 1.4 GB + models 1.1 GB, measured 2026-09-15)
(design referee M9).

MEASURED FACTS ABOUT DOCLING'S OUTPUT (docling 2.127.0, docling-core 2.96.0, 2026-09-15;
every one of them read off a real conversion of a real paper, none assumed):

* ``pages`` is keyed by a STRING page number, 1-indexed, each with ``size.width/height``.
* item boxes live in ``prov[].bbox`` as ``{l, t, r, b, coord_origin}`` with
  ``coord_origin = "BOTTOMLEFT"`` — so ``t > b`` and the y axis runs UP. The canonical frame
  runs DOWN from the top, so the adapter flips: ``y0 = H - t``, ``y1 = H - b``.
* TABLE CELL boxes in the same document carry ``coord_origin = "TOPLEFT"`` and are ALREADY
  in the canonical sense. The two origins coexist inside one JSON file, so the adapter
  branches on the field and never on the container. Flipping a cell box as if it were an
  item box puts it at the wrong end of the page.
* ``pages[n].size`` is the CROPBOX, not the mediabox: on ``Alwan_1988`` (mediabox
  ``(0,0,612,792)``, cropbox ``(10.345,10.777,603.441,782.948)``) Docling reports
  ``593.096 x 772.171``. That is the same frame GROBID reports, and the same trap: a box
  compared against a mediabox-based one is out by the cropbox origin (10.3 pt in x, 9.0 pt
  in y here). :func:`page_frames` reads both boxes from the PDF and :func:`to_mediabox`
  shifts; every :class:`Block` states which frame it is in through ``Block.frame``.
* reading order is the ``body`` child order, depth-first through ``groups``; it is NOT the
  order of the ``texts`` array and NOT geometric. ``content_layer`` separates ``body`` from
  ``furniture`` (running heads, folios).
* labels seen on the gate papers: ``text``, ``section_header``, ``list_item``, ``caption``,
  ``footnote``, ``page_header``, ``page_footer``, ``formula``, ``picture``, ``table``.

CONFIDENCE: the exported DoclingDocument carries no per-item confidence. Docling reports a
per-page and per-document confidence GRADE (layout / OCR / parse scores) on the CONVERSION
RESULT, which the worker records into ``metrics["confidence"]`` alongside the conversion
status; :attr:`Block.confidence` is therefore None here rather than a made-up number, and the
document-level grade travels with the run, not with the block. The exact shape of that grade
object is whatever ``ConversionResult.confidence`` dumps — read it from a metrics row, do not
assume it.

ZERO-BLOCK REFUSAL (the defect the GROBID referee found, built in here from the start): a
conversion that "succeeds" and yields no body text is a failure, not an empty-but-fine run.
:func:`check_text_blocks` raises :class:`NoTextBlocks`, and :func:`extract` records such a
run as ``status="failed"`` — never as an ok run with zero blocks.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import sys
import time

#: The extraction venv (design M9). Overridable for a machine that puts it elsewhere.
VENV_PYTHON = os.environ.get(
    "LITKB_EXTRACT_PYTHON", r"D:\edmonds-pipeline\venv-docling\Scripts\python.exe")

#: The CUDA build of the same venv (same docling pins, torch cu130; S4 run 3 data survey D8). The
#: bulk pass and the bench already name it explicitly; :func:`device_pair` is what makes every
#: other caller reach it when it asks for `cuda`.
CUDA_VENV_PYTHON = os.environ.get(
    "LITKB_EXTRACT_CUDA_PYTHON", r"D:\edmonds-pipeline\venv-docling-cuda\Scripts\python.exe")

#: The devices :func:`device_pair` accepts. `auto` means "cuda if the interpreter can serve it".
DEVICES = ("auto", "cuda", "cpu")

_HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(_HERE, "docling_worker.py")

#: Filled in from the run's metrics; the fixture tests pin the version they were made with.
EXTRACTOR = "docling-2.127.0"

#: Item labels that carry document text, in the sense stage 5 means by "a block".
TEXT_LABELS = ("text", "section_header", "list_item", "caption", "footnote", "title",
               "formula", "code", "paragraph", "checkbox_selected", "checkbox_unselected",
               "reference")

#: Labels that are page furniture rather than document body.
FURNITURE_LABELS = ("page_header", "page_footer")


class DoclingError(RuntimeError):
    """The worker failed, or the conversion did."""

    def __init__(self, message, metrics=None, stderr=""):
        super().__init__(message)
        self.metrics = metrics
        self.stderr = stderr


class DeviceUnavailable(DoclingError):
    """A device was asked for that the chosen interpreter cannot serve.

    Raised by :func:`device_pair` BEFORE any conversion runs. The failure it replaces was silent:
    `device=cuda` under the CPU venv (torch `+cpu`) reached docling, which wrote a FAILED metrics
    row (`AcceleratorDeviceNotAvailableError`) and no artifact, and S2's Maiti_2022 was ingested
    GROBID-only with nothing saying why (S4 run 3 code survey, headline 1)."""


class NoTextBlocks(DoclingError):
    """The conversion returned a document with no body text block.

    An image-only scan converted with OCR off produces exactly this: pages, page sizes, a
    picture or two, and nothing to read. Recording it as an ok run would put a silently
    unextracted file into the lake with zero blocks and no error.
    """


@dataclasses.dataclass(frozen=True)
class Block:
    """One coordinate-bearing region, in the canonical §7.1 frame.

    Field names match :class:`litkb.extract.grobid.Block` deliberately — stage 5 reconciles
    the two tools' blocks and cannot do that across two different vocabularies. The two
    fields GROBID has no use for are here because Docling's whole contribution is order:
    ``order_index`` is the position in the document's reading order, and ``content_layer``
    says whether the block is body or furniture.
    """

    page: int           # 1-indexed
    x0: float           # PDF points, origin TOP-LEFT of the page as displayed
    y0: float
    x1: float
    y1: float
    kind: str           # docling label: text, section_header, caption, formula, table, ...
    text: str = ""
    extractor: str = EXTRACTOR
    confidence: float | None = None   # docling exports none per item (see module docstring)
    element_id: str | None = None     # the item's self_ref, e.g. "#/texts/12"
    box_index: int = 0                # position within a multi-prov item
    box_count: int = 1
    frame: str = "cropbox"            # "cropbox" as docling emits it; "mediabox" after to_mediabox()
    order_index: int = -1             # position in the document's reading order
    content_layer: str = "body"
    #: THIS box's own share of the element's ``text`` — the slice Docling's ``charspan`` names
    #: for this ``prov`` entry (:func:`prov_pieces`) — or None where the spans cannot be read
    #: back exactly. ``text`` stays the WHOLE element's: matching compares the two tools' whole
    #: readings of one element, and only a fragment's STORED text is cut to its own box.
    piece: str | None = None

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0

    def contains(self, x, y, tol=0.0):
        return (self.x0 - tol) <= x <= (self.x1 + tol) and (self.y0 - tol) <= y <= (self.y1 + tol)


@dataclasses.dataclass(frozen=True)
class Cell:
    """One table cell, with its grid position and its span."""

    row: int
    col: int
    row_span: int
    col_span: int
    text: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    column_header: bool = False
    row_header: bool = False
    frame: str = "cropbox"


@dataclasses.dataclass(frozen=True)
class Table:
    """A table as a cell grid — never as rendered text."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    num_rows: int
    num_cols: int
    cells: tuple
    element_id: str | None = None
    caption: str = ""
    order_index: int = -1
    frame: str = "cropbox"

    def at(self, row, col):
        """The cell occupying (row, col), span-aware; None where the grid has a hole."""
        for c in self.cells:
            if (c.row <= row < c.row + c.row_span) and (c.col <= col < c.col + c.col_span):
                return c
        return None

    def grid(self):
        """[[text, ...], ...] — a span-filled dense grid, for eyeballing and for diffs."""
        return [[(self.at(r, c).text if self.at(r, c) else None) for c in range(self.num_cols)]
                for r in range(self.num_rows)]


@dataclasses.dataclass(frozen=True)
class Figure:
    """A figure as a PAGE-REGION REFERENCE — page plus box, no pixels.

    The design stores figures as regions (§7 stage 5); the crop is produced on demand from
    the PDF, so nothing in the lake holds a second copy of the image.
    """

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    element_id: str | None = None
    caption: str = ""
    order_index: int = -1
    frame: str = "cropbox"


# ── the §7.1 adapter ────────────────────────────────────────────────────────────────────

def page_size(doc, page_no):
    """(width, height) of a page, from the document's own page census."""
    pages = doc.get("pages") or {}
    p = pages.get(str(page_no)) or pages.get(page_no)
    if not p:
        return None
    size = p.get("size") or {}
    return (float(size["width"]), float(size["height"]))


def to_canonical(bbox, page_height):
    """docling bbox dict -> (x0, y0, x1, y1) with the origin at the page's TOP-LEFT.

    ``coord_origin`` is read from the box itself. BOTTOMLEFT boxes (every ``prov`` box) are
    flipped against the page height; TOPLEFT boxes (every table cell box) are already in the
    canonical sense and are only normalised so that y0 <= y1. Guessing the origin from the
    kind of item instead of reading the field is the bug this function exists to prevent.
    """
    left, right = float(bbox["l"]), float(bbox["r"])
    top, bottom = float(bbox["t"]), float(bbox["b"])
    origin = (bbox.get("coord_origin") or "BOTTOMLEFT").upper()
    if origin.endswith("BOTTOMLEFT"):
        if page_height is None:
            raise DoclingError("a BOTTOMLEFT box cannot be flipped without the page height")
        y0, y1 = page_height - top, page_height - bottom
    else:
        y0, y1 = top, bottom
    if y0 > y1:
        y0, y1 = y1, y0
    if left > right:
        left, right = right, left
    return (left, y0, right, y1)


def _ref_target(doc, ref):
    """Resolve a ``{"$ref": "#/texts/3"}`` pointer into (kind, index, item)."""
    path = ref["$ref"] if isinstance(ref, dict) else ref
    parts = path.lstrip("#/").split("/")
    if len(parts) == 1:                       # "#/body", "#/furniture"
        return parts[0], None, doc.get(parts[0])
    kind, idx = parts[0], int(parts[1])
    arr = doc.get(kind) or []
    if idx >= len(arr):
        return kind, idx, None
    return kind, idx, arr[idx]


def iter_items(doc, root="body"):
    """Yield (order_index, kind, item) in READING ORDER — the body tree's child order.

    Groups are walked in place, so a list's items keep their position in the flow rather
    than being appended after it. An item reachable twice is yielded once (the first time),
    which is what keeps a malformed tree from looping.
    """
    seen = set()
    order = 0
    stack = list(reversed((doc.get(root) or {}).get("children") or []))
    while stack:
        ref = stack.pop()
        kind, idx, item = _ref_target(doc, ref)
        if item is None:
            continue
        sref = item.get("self_ref")
        if sref in seen:
            continue
        seen.add(sref)
        if kind == "groups":
            stack.extend(reversed(item.get("children") or []))
            continue
        yield order, kind, item
        order += 1
        if item.get("children"):
            stack.extend(reversed(item["children"]))


def iter_blocks(doc, kinds=None, body_only=False):
    """A :class:`Block` per prov box of every text-bearing item, in reading order.

    An item with several ``prov`` entries (a paragraph broken across a column or a page)
    yields one block per entry, with ``box_index`` / ``box_count`` set — the same rule the
    GROBID adapter applies to a ``;``-separated coords value. Collapsing them to the first
    box silently drops the rest of the region.
    """
    wanted = set(kinds) if kinds else None
    for order, kind, item in iter_items(doc):
        if kind not in ("texts", "tables", "pictures"):
            continue
        label = item.get("label") or kind
        if wanted is not None and label not in wanted:
            continue
        layer = item.get("content_layer") or "body"
        if body_only and layer != "body":
            continue
        provs = item.get("prov") or []
        text = item.get("text") or ""
        pieces = prov_pieces(item) if len(provs) > 1 else None
        for i, prov in enumerate(provs):
            page = int(prov["page_no"])
            h = page_size(doc, page)
            x0, y0, x1, y1 = to_canonical(prov["bbox"], h[1] if h else None)
            yield Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind=label, text=text,
                        element_id=item.get("self_ref"), box_index=i, box_count=len(provs),
                        order_index=order, content_layer=layer,
                        piece=pieces[i] if pieces is not None else None)


def prov_pieces(item):
    """-> [str per ``prov`` entry] that TILE ``item["text"]`` exactly, or None.

    What the tool records, read rather than assumed. Docling joins the pieces of one element
    that its reading-order model merged across a page or column break in
    ``ReadingOrderModel._merge_elements`` (docling 2.127.0,
    module ``docling.models.stages.reading_order.readingorder_model``, read 2026-09-22 in
    ``venv-docling``): the first piece's prov gets ``charspan (0, len(its text))``; each merged
    piece gets ``(len(text so far) + 1, len(text so far) + 1 + len(piece))`` — computed BEFORE the
    join — and is then appended either after ONE space or, when the text so far ends with a soft
    hyphen or with a hyphen before a lower-case continuation, onto the text with that last
    character removed and no space. So a merged piece's ``charspan[0]`` is exact after a space
    join and two characters too far after a hyphen join, and WHICH join happened is read off the
    length the text had afterwards: the NEXT piece's ``charspan[0] - 1``, or the final text's
    length for the last piece — ``charspan[1]`` after a space join, ``charspan[1] - 2`` after a
    hyphen join.

    MEASURED on the 260 stored Docling artifacts under ``litkb_derived`` (2026-09-22, builder-D2
    report): ``charspan`` is populated on every ``prov`` of every text item; 1,956 items carry
    more than one ``prov``, 1,358 of them on more than one page; on 1,845 the last span ends at
    ``len(text)`` and on the other 111 two characters past it — the hyphen join.

    The first piece's own ``charspan[1]`` is NOT used: a list item's text is re-written by the
    list-item processor after that span is taken (it equals ``len(orig)``, not ``len(text)``, on
    12,066 single-prov items of the same 260 files), so piece 0 simply ends where piece 1
    begins. The space a join inserted stays at the END of the earlier piece, which is what makes
    the pieces tile the text; ``"".join(pieces) == item["text"]`` is checked before returning.
    Anything that does not read back exactly returns None, and the caller keeps the element's
    whole text for that element — the old behaviour, never a guessed cut.
    """
    provs = item.get("prov") or []
    text = item.get("text") or ""
    try:
        spans = [(int(p["charspan"][0]), int(p["charspan"][1])) for p in provs]
    except (KeyError, TypeError, IndexError, ValueError):
        return None
    if len(spans) < 2 or spans[0][0] != 0:
        return None
    starts = [0]
    for k in range(1, len(spans)):
        s, e = spans[k]
        after = spans[k + 1][0] - 1 if k + 1 < len(spans) else len(text)
        if after == e:                                   # appended after one space
            if s < 1 or s > len(text) or text[s - 1] != " ":
                return None
            starts.append(s)
        elif after == e - 2:                             # appended onto a removed hyphen
            starts.append(s - 2)
        else:
            return None
    starts.append(len(text))
    if any(b <= a for a, b in zip(starts, starts[1:])):
        return None
    pieces = [text[a:b] for a, b in zip(starts, starts[1:])]
    return pieces if "".join(pieces) == text else None


def blocks(doc, kinds=None, body_only=False):
    return list(iter_blocks(doc, kinds, body_only))


def body_blocks(doc):
    """Text-bearing body blocks only — the document, not the running heads."""
    return [b for b in iter_blocks(doc, body_only=True) if b.kind in TEXT_LABELS and b.text]


def body_text(doc):
    return " ".join(" ".join(b.text.split()) for b in body_blocks(doc))


def check_text_blocks(doc, name=""):
    """Raise :class:`NoTextBlocks` when a conversion produced no readable body.

    Block-based, not byte-based, for the same reason as the GROBID adapter: a document whose
    only content is a picture and a page number was not extracted, however cleanly the tool
    exited.
    """
    n = len(body_blocks(doc))
    if n:
        return n
    what = name or doc.get("name") or "document"
    raise NoTextBlocks(
        f"docling returned a document for {what} with no body text block "
        f"({len(doc.get('pages') or {})} pages, {len(doc.get('texts') or [])} text items, "
        f"{len(doc.get('pictures') or [])} pictures) — refusing to record an empty extraction")


def _caption_text(doc, item):
    out = []
    for ref in item.get("captions") or []:
        _, _, cap = _ref_target(doc, ref)
        if cap and cap.get("text"):
            out.append(cap["text"])
    return " ".join(out)


def tables(doc):
    """Every table as a cell grid, spans preserved, in reading order."""
    out = []
    for order, kind, item in iter_items(doc):
        if kind != "tables":
            continue
        prov = (item.get("prov") or [{}])[0]
        page = int(prov.get("page_no", 0)) if prov else 0
        h = page_size(doc, page)
        box = to_canonical(prov["bbox"], h[1] if h else None) if prov.get("bbox") else (0, 0, 0, 0)
        data = item.get("data") or {}
        cells = []
        for c in data.get("table_cells") or []:
            cb = c.get("bbox")
            cx = to_canonical(cb, h[1] if h else None) if cb else (0.0, 0.0, 0.0, 0.0)
            cells.append(Cell(
                row=int(c["start_row_offset_idx"]), col=int(c["start_col_offset_idx"]),
                row_span=int(c.get("row_span") or 1), col_span=int(c.get("col_span") or 1),
                text=(c.get("text") or "").strip(), page=page,
                x0=cx[0], y0=cx[1], x1=cx[2], y1=cx[3],
                column_header=bool(c.get("column_header")), row_header=bool(c.get("row_header"))))
        out.append(Table(page=page, x0=box[0], y0=box[1], x1=box[2], y1=box[3],
                         num_rows=int(data.get("num_rows") or 0),
                         num_cols=int(data.get("num_cols") or 0),
                         cells=tuple(cells), element_id=item.get("self_ref"),
                         caption=_caption_text(doc, item), order_index=order))
    return out


def figures(doc):
    """Every picture as a page-region reference, in reading order."""
    out = []
    for order, kind, item in iter_items(doc):
        if kind != "pictures":
            continue
        for prov in item.get("prov") or []:
            page = int(prov["page_no"])
            h = page_size(doc, page)
            x0, y0, x1, y1 = to_canonical(prov["bbox"], h[1] if h else None)
            out.append(Figure(page=page, x0=x0, y0=y0, x1=x1, y1=y1,
                              element_id=item.get("self_ref"),
                              caption=_caption_text(doc, item), order_index=order))
    return out


def equations(doc):
    """(order_index, page, latex) for every formula region.

    ``text`` holds LaTeX only when the worker ran with formula enrichment on; without it the
    region is still located but its text is whatever the native layer gave, which is not
    LaTeX. The caller is told which by the run's ``metrics["formula"]``.
    """
    return [(b.order_index, b.page, b.text) for b in iter_blocks(doc, kinds=("formula",))]


# ── the equation-density gate (Kam's decision A, 2026-09-15) ────────────────────────────
#
# Formula enrichment is 160x slower than layout (referee §3), so it runs on EQUATION-DENSE
# PAGES ONLY. The density is read from pypdfium2's text layer — the same layer stage 0's
# inventory will later carry per page, at which point this computation moves there and this
# function becomes the reference implementation of the number.

#: Characters that are unambiguously mathematical wherever they appear.
MATH_CHARS = frozenset(
    "=+<>±×·÷≤≥≠≈≡∑∫∮∂∇√∞→←↔∈∉∋⊂⊆⊃⊇∪∩∅∀∃∄¬∧∨⊕⊗⊙∏∐∼∝∥⟨⟩⌈⌉⌊⌋†‡°′″∠⊥≪≫⇒⇔≜≝∓∖")

#: Sub/superscript markers: the Unicode forms, and the TeX-ish ASCII carets that survive
#: extraction from a math font.
SUPSUB_CHARS = frozenset("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓ^_")

#: A digit welded to a letter ("x2", "2n") — subscript structure flattened by the extractor.
#: Counted as TWO math characters, which is what it is.
_DIGIT_ADJ = re.compile(r"[A-Za-z]\d|\d[A-Za-z]")

#: An equation NUMBER at the end of a line: "(3)", "(12a)". Capped at three digits on
#: purpose — "(2003)" ending a reference-list line is a year, not an equation. ``ð6Þ`` is the
#: same pattern seen through a broken math font; see :func:`equation_density`.
_EQ_NUMBER = re.compile(r"[(ð]\s?\d{1,3}[a-z]?\s?[)Þ]\s*$")

#: A line this short, in a page's text layer, is a DISPLAY-MATH FRAGMENT: the extractor
#: breaks a centred equation into one line per run (numerator, bar, denominator, limits).
#: Measured 2026-09-15 on Bellettini p4, where one display equation comes out as the lines
#: ``[``, ``k``, ``j¼1``, ``Cij``, ``();``.
DISPLAY_FRAGMENT_CHARS = 12

#: **0.05, and how it was chosen.** The corpus histogram (4,655 pages, 219 PDFs — the census
#: is ``qc/instruments/litkb_equation_density.py`` -> ``Reports/litkb_equation_density_2026-09-15.csv``)
#: has NO antimode: academic maths is a continuum, not two populations, so the cut cannot be
#: read off a valley. It was chosen instead against an INDEPENDENT target — docling's own
#: layout pass, which labels ``formula`` regions in the cheap pass and knows nothing about
#: the text layer this function reads (CLAUDE.md §3.4c: the proposer does not score itself).
#: Scored per page over the four text-layer gate papers (177 pages, 655 formula regions),
#: 0.05 is the LARGEST cut holding recall >= 0.80 and precision >= 0.95 against those labels:
#: **recall 0.804, precision 0.974, 33.75% of the corpus selected**. The whole
#: recall/precision/cost curve is in the report, because this is a policy choice about hours
#: and a reader may want a different point on it; the rule was fixed after seeing the curve,
#: which is stated rather than hidden.
EQUATION_DENSITY_CUT = 0.05


def _is_math_char(c):
    if c in MATH_CHARS or c in SUPSUB_CHARS:
        return True
    o = ord(c)
    if 0x370 <= o <= 0x3FF or 0x1F00 <= o <= 0x1FFF:      # Greek and Coptic, Greek Extended
        return True
    if 0x2100 <= o <= 0x214F or 0x1D400 <= o <= 0x1D7FF:  # letterlike, math alphanumerics
        return True
    import unicodedata
    return unicodedata.category(c) == "Sm"


def equation_density(page_text, page_chars=None):
    """Fraction of a page's text layer that is attributable to mathematics. -> 0.0 … 1.0

    THE FORMULA, stated once so the threshold can be argued with. Every non-space character
    of the page is attributed AT MOST ONCE, so the result is a genuine fraction:

    * a line that ends in an equation number (``_EQ_NUMBER``) contributes ALL its characters;
    * a non-empty line no longer than :data:`DISPLAY_FRAGMENT_CHARS` contributes all of its
      characters — it is a broken-up display equation, not prose;
    * on every remaining line, each math-class character contributes itself
      (:func:`_is_math_char`), plus two per digit-adjacent-to-letter pair.

    ``density = attributed / page_chars``, where ``page_chars`` defaults to the count of
    non-whitespace characters on the page.

    **WHY THE LINE TERMS ARE NOT OPTIONAL.** A pure math-character ratio does not work on
    this corpus. Bellettini 2002 — the equation paper — uses a Type-1 math font with no
    usable ToUnicode map: ``=`` extracts as ``¼``, ``(x)`` as ``ðxÞ``, ``Σ`` as ``X``, ``χ``
    as ``w`` (measured 2026-09-15 on pp. 3–4). Its math-CHARACTER ratio is 0.005–0.014,
    the same band as Benedek's PROSE. What survives a broken encoding is the LAYOUT of
    display maths, and that is what the two line terms read.

    A page with no text layer at all (an image-only scan: every page of Anderson 1957)
    returns **0.0** and is therefore never selected. That is deliberate and it is a stated
    hole: an equation on a scan is invisible to this gate until OCR has run. Stage 0's
    text-layer census is what flags such a file (referee §5.1), not this function.
    """
    text = (page_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n")]
    total = page_chars if page_chars is not None else sum(
        1 for c in text if not c.isspace())
    if not total:
        return 0.0
    attributed = 0
    for ln in lines:
        if not ln:
            continue
        n = sum(1 for c in ln if not c.isspace())
        if _EQ_NUMBER.search(ln) or len(ln) <= DISPLAY_FRAGMENT_CHARS:
            attributed += n
            continue
        attributed += sum(1 for c in ln if not c.isspace() and _is_math_char(c))
        attributed += 2 * len(_DIGIT_ADJ.findall(ln))
    return min(1.0, attributed / total)


def page_densities(pdf_path):
    """[(page_no, density, page_chars)] for every page of a PDF, 1-indexed."""
    import pypdfium2 as pdfium

    out = []
    doc = pdfium.PdfDocument(pdf_path)
    try:
        for i in range(len(doc)):
            t = doc[i].get_textpage().get_text_range() or ""
            n = sum(1 for c in t if not c.isspace())
            out.append((i + 1, equation_density(t, n), n))
    finally:
        doc.close()
    return out


def dense_pages(pdf_path, cut=None, pages=None):
    """Page numbers whose equation density is STRICTLY ABOVE the cut.

    ``pages`` optionally restricts the census to a ``[lo, hi]`` range, so a job that converts
    part of a book does not enrich pages it never extracted.
    """
    cut = EQUATION_DENSITY_CUT if cut is None else cut
    lo, hi = (pages or [1, 10 ** 9])
    return [p for p, d, _ in page_densities(pdf_path) if d > cut and lo <= p <= hi]


def page_runs(pages):
    """[1,2,3,7,9,10] -> [[1,3],[7,7],[9,10]] — contiguous ranges, for a worker page range."""
    runs = []
    for p in sorted(set(pages)):
        if runs and p == runs[-1][1] + 1:
            runs[-1][1] = p
        else:
            runs.append([p, p])
    return runs


class FormulaEnrichmentFailed(DoclingError):
    """An enriched page came back with a formula region carrying no LaTeX.

    THE FAIL-CLOSED RULE. CodeFormulaV2 is 611 MB and autoregressive; on a 4 GB card it can
    run out of memory. Docling's enrichment does NOT re-raise per element — a formula item
    the model could not decode keeps the text the native layer gave it, and the conversion
    still reports status SUCCESS. A caller that trusted that status would write the PDF's
    mojibake into a ``latex`` column. So the adapter compares the enriched text against the
    base pass's text for the same region and refuses a page where nothing moved.
    """


def merge_formula_latex(base_doc, enriched_docs, pages=None):
    """Copy LaTeX from enrichment-pass documents onto the base document's formula items.

    ``auto`` converts twice — once cheaply over the whole file, once with enrichment over the
    dense page runs only — because ``do_formula_enrichment`` is a CONVERTER-wide option in
    docling 2.127.0 (``PdfPipelineOptions.do_formula_enrichment``). Read in the INSTALLED
    package — ``docling/models/stages/code_formula/code_formula_model.py``, the
    ``is_processable`` method — it filters on the item's LABEL and on the option, and never
    on the page. There is no per-page switch to set. (That path is inside the extraction
    venv, not this repo, which is why it is not written as a resolvable citation.)

    Matching is by ``(page, bbox rounded to 1 pt)``, not by index: the enrichment pass
    converts a page RANGE, so its item indices and its ``order_index`` are its own.

    -> ``(patched, missing)``, where ``missing`` is [(page, element_id)] for every formula
    region on an enriched page whose LaTeX did not arrive. :func:`extract` turns a non-empty
    ``missing`` into :class:`FormulaEnrichmentFailed`.
    """
    def key(page, box):
        return (page, round(box[0], 1), round(box[1], 1), round(box[2], 1), round(box[3], 1))

    latex = {}
    for ed in enriched_docs:
        for b in iter_blocks(ed, kinds=("formula",)):
            latex[key(b.page, (b.x0, b.y0, b.x1, b.y1))] = b.text
    want = set(pages) if pages is not None else None
    patched, missing = 0, []
    for item in base_doc.get("texts") or []:
        if (item.get("label") or "") != "formula":
            continue
        for i, prov in enumerate(item.get("prov") or []):
            page = int(prov["page_no"])
            if want is not None and page not in want:
                continue
            h = page_size(base_doc, page)
            box = to_canonical(prov["bbox"], h[1] if h else None)
            new = latex.get(key(page, box))
            if new and new.strip() and new != item.get("text"):
                if i == 0:
                    item["text"] = new
                patched += 1
            else:
                missing.append((page, item.get("self_ref")))
    return patched, missing


# ── the cropbox -> mediabox frame shift (shared rule with the GROBID adapter) ────────────

def page_frames(pdf_path):
    """{page: {mediabox, cropbox, rotation, dx, dy}} read from the PDF with pypdfium2.

    The DoclingDocument carries the cropbox's SIZE only, never its origin, so the offset
    cannot be recovered from the JSON alone. ``dx = crop.x0 - media.x0`` and
    ``dy = media.y1 - crop.y1`` are what :func:`to_mediabox` adds.

    ONE HOME (2026-09-15): the body is :func:`litkb.extract.inventory.page_frames`, whose
    docstring owns the rule. This copy used to be the WEAKEST of the three — it had neither
    the inherited-``/MediaBox`` fallback nor a missing-mediabox raise, so on a page that
    inherits its box from the page tree it returned ``None`` and died with a ``TypeError``
    inside the subtraction above. Collapsing the three before stage 5 is design §7.1's open
    item; a page with no mediabox now raises :class:`DoclingError`.
    """
    from litkb.extract import inventory

    return inventory.page_frames(pdf_path, error=DoclingError)


def to_mediabox(items, frames):
    """Shift blocks/cells/figures from the cropbox frame into the canonical mediabox frame.

    A rotated page is left alone and keeps ``frame="cropbox"``: docling reports it in the
    displayed frame and how that composes with the cropbox shift is UNCONFIRMED, exactly as
    in the GROBID adapter. A caller can see which ones were skipped from ``frame``.
    """
    out = []
    for b in items:
        f = frames.get(b.page)
        if f is None or f["rotation"]:
            out.append(b)
            continue
        dx, dy = f["dx"], f["dy"]
        out.append(dataclasses.replace(b, x0=b.x0 + dx, y0=b.y0 + dy,
                                       x1=b.x1 + dx, y1=b.y1 + dy, frame="mediabox"))
    return out


def implausible_blocks(items, doc, tol=1.0):
    """[(item, reason)] for every box that escapes its page — the gate's box check."""
    bad = []
    for b in items:
        if b.page < 1:
            bad.append((b, f"page {b.page} is not 1-indexed"))
            continue
        size = page_size(doc, b.page)
        if size is None:
            bad.append((b, f"page {b.page} is not in the page census"))
            continue
        w, h = size
        if b.x1 < b.x0 or b.y1 < b.y0:
            bad.append((b, "inverted box"))
        elif b.x0 < -tol or b.y0 < -tol or b.x1 > w + tol or b.y1 > h + tol:
            bad.append((b, f"box outside page {w}x{h}"))
    return bad


# ── the §7.1 alignment check against pypdfium2's own character boxes ────────────────────

def charbox_union(pdf_path, page_no, needle, frame="cropbox"):
    """Union of pypdfium2's per-character boxes for ``needle`` on one page.

    -> (x0, y0, x1, y1) in the canonical TOP-LEFT frame, expressed on the cropbox (the frame
    docling reports) or the mediabox, or None when the string is absent. A string that
    occurs MORE THAN ONCE returns None: an ambiguous match cannot test a box.

    pypdfium2 reports ``get_charbox`` as (left, bottom, right, top) in the mediabox's
    bottom-left user space — a different origin AND a different box from docling's. Getting
    either wrong moves the answer by the page height or by the cropbox offset, which is
    exactly the error this function is here to catch, so both conversions are explicit.
    """
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_path)
    try:
        page = doc[page_no - 1]
        tp = page.get_textpage()
        text = tp.get_text_range()
        flat = " ".join(text.split())
        if flat.count(" ".join(needle.split())) != 1:
            return None
        # map the flattened offset back to the raw offset
        raw = text
        target = " ".join(needle.split())
        pos, seen = -1, 0
        norm_chars = []
        for i, ch in enumerate(raw):
            if ch.isspace():
                if norm_chars and norm_chars[-1][0] != " ":
                    norm_chars.append((" ", i))
            else:
                norm_chars.append((ch, i))
        joined = "".join(c for c, _ in norm_chars)
        pos = joined.find(target)
        if pos < 0:
            return None
        start = norm_chars[pos][1]
        end = norm_chars[pos + len(target) - 1][1]
        boxes = []
        for i in range(start, end + 1):
            if raw[i].isspace():
                continue
            try:
                cb = tp.get_charbox(i, loose=False)
            except Exception:  # noqa: BLE001 - a missing glyph box is not a frame error
                continue
            # DEGENERATE BOXES ARE DROPPED. pypdfium2 reports a zero-area box for the first
            # character of a text run, positioned at the END of the previous run — measured
            # 2026-09-15 on Benedek p1, where the "1" of "1. Introduction" comes back as
            # (561.0, 326.6, 561.0, 326.6), the right edge of the line above. Unioned in, it
            # inflates the string's box by 458 pt and the alignment check reports a frame
            # error that does not exist.
            if cb[2] - cb[0] <= 0 or cb[3] - cb[1] <= 0:
                continue
            boxes.append(cb)
        seen = len(boxes)
        if not seen:
            return None
        left = min(b[0] for b in boxes)
        bottom = min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        top = max(b[3] for b in boxes)
        frames = page_frames(pdf_path)[page_no]
        media = frames["mediabox"]
        # mediabox bottom-left -> mediabox top-left
        y0 = media[3] - top
        y1 = media[3] - bottom
        x0, x1 = left - media[0], right - media[0]
        if frame == "cropbox":
            x0, x1 = x0 - frames["dx"], x1 - frames["dx"]
            y0, y1 = y0 - frames["dy"], y1 - frames["dy"]
        return (x0, y0, x1, y1)
    finally:
        doc.close()


def alignment_offsets(pdf_path, doc, cases, tol=3.0):
    """[(page, needle, offset, contained)] — the §7.1 test, as the GROBID referee ran it.

    ``cases`` is [(page, needle)]. For each, pypdfium2's character-box union for the needle
    is compared with the docling block that carries it:

    * ``contained`` — the block's box contains the string's box within ``tol``. This holds
      for ANY needle, including one word inside a paragraph, and is the property §7.1
      actually asks for ("every adapter's box for the region containing that word must
      contain it").
    * ``offset`` — the largest of the four |component| differences, reported ONLY when the
      needle IS the whole block (a heading, a caption). For a word inside a paragraph the
      two boxes are legitimately different sizes and a component difference would mean
      nothing, so it comes back None.

    A needle that is not unique on the page, or that no block carries, yields
    ``(page, needle, None, None)`` — never a silent pass.
    """
    out = []
    bs = blocks(doc)
    for page, needle in cases:
        want = charbox_union(pdf_path, page, needle, frame="cropbox")
        got = None
        for b in bs:
            if b.page == page and _norm(needle) in _norm(b.text):
                if got is None or (b.width * b.height) < (got.width * got.height):
                    got = b
        if want is None or got is None:
            out.append((page, needle, None, None))
            continue
        contained = (got.x0 - tol <= want[0] and got.y0 - tol <= want[1]
                     and got.x1 + tol >= want[2] and got.y1 + tol >= want[3])
        off = None
        if _norm(got.text) == _norm(needle):
            off = max(abs(got.x0 - want[0]), abs(got.y0 - want[1]),
                      abs(got.x1 - want[2]), abs(got.y1 - want[3]))
        out.append((page, needle, off, contained))
    return out


# ── the reading-order gate ──────────────────────────────────────────────────────────────

def _norm(s):
    return " ".join((s or "").split()).lower()


def find_in_order(items, snippets, page=None):
    """[order_index] of the first block containing each snippet (-1 when absent).

    The gate's primitive: on a two-column page the gold is three snippets known to sit in
    left-top, left-bottom and right-top position, and a correct reading order returns them
    strictly increasing. A geometric top-to-bottom sort returns the right column's snippet
    in the middle, which is the interleaving this check exists to catch.
    """
    found = []
    for snip in snippets:
        n = _norm(snip)
        hit = -1
        for b in items:
            if page is not None and b.page != page:
                continue
            if n in _norm(b.text):
                hit = b.order_index
                break
        found.append(hit)
    return found


def reading_order_violations(items, snippets, page=None):
    """[] when the snippets appear in the given order; the offending pairs otherwise.

    A snippet that is not found at all is a violation in its own right — a check that
    silently passes when it matched nothing is not a check.
    """
    idx = find_in_order(items, snippets, page=page)
    bad = []
    for i, v in enumerate(idx):
        if v < 0:
            bad.append((i, snippets[i], "not found"))
    for i in range(len(idx) - 1):
        if idx[i] >= 0 and idx[i + 1] >= 0 and idx[i] >= idx[i + 1]:
            bad.append((i, snippets[i], f"order {idx[i]} >= {idx[i + 1]} for the next snippet"))
    return bad


def geometric_order(items):
    """The same blocks, re-indexed by a naive (page, top, left) sort — THE KILL INPUT.

    This is what a layout-blind extractor produces: on a two-column page it interleaves the
    columns. :func:`reading_order_violations` must fail on it, and a test asserts that it
    does. A gate that has never been shown to fire is not a gate (CLAUDE.md §3.4c).
    """
    ordered = sorted(items, key=lambda b: (b.page, round(b.y0, 1), round(b.x0, 1)))
    return [dataclasses.replace(b, order_index=i) for i, b in enumerate(ordered)]


def shuffled_table(table, seed=7):
    """The same table with its cell TEXTS permuted across positions — THE KILL INPUT.

    Geometry and spans are untouched, so a check that only counts cells or compares the
    grid's shape passes it. Only a check that reads values at stated positions fails.
    """
    import random
    rng = random.Random(seed)
    texts = [c.text for c in table.cells]
    rng.shuffle(texts)
    cells = tuple(dataclasses.replace(c, text=t) for c, t in zip(table.cells, texts))
    return dataclasses.replace(table, cells=cells)


def table_cell_errors(table, gold):
    """[(row, col, expected, got)] for every gold cell whose value does not match.

    ``gold`` is {(row, col): text}. Comparison is whitespace- and case-normalised; nothing
    else is forgiven, because the point of the check is the value.
    """
    bad = []
    for (r, c), want in sorted(gold.items()):
        cell = table.at(r, c)
        got = cell.text if cell else None
        if _norm(got) != _norm(want):
            bad.append((r, c, want, got))
    return bad


# ── running the tool ────────────────────────────────────────────────────────────────────

def worker_available(python=None):
    return os.path.exists(python or VENV_PYTHON) and os.path.exists(WORKER)


# ── the device and the interpreter, chosen as ONE pair ────────────────────────────────────
#
# S4 run 3 decision D4. Before this, the device came from a flag (hunt's default `cuda`) and the
# interpreter from another (`VENV_PYTHON`, whose torch is `+cpu`), each defaulted independently,
# and the pair they made could not run: docling raised inside the worker, the worker wrote a failed
# metrics row, and the caller carried on with GROBID alone. Now one function picks both, asks the
# INTERPRETER whether it can serve CUDA, and refuses a pair it cannot serve by name.

_CUDA_ANSWERS = {}


def interpreter_has_cuda(python):
    """True when `python`'s torch reports `cuda.is_available()`. Asked once per interpreter path.

    Asked in a subprocess — the extraction venv is never imported here (design M9). An interpreter
    with no torch, or one that fails to start, answers False: it cannot serve CUDA."""
    key = os.path.normcase(os.path.abspath(python))
    if key not in _CUDA_ANSWERS:
        import tempfile

        try:
            # -P and a neutral cwd: the secrets-shadow hazard of docling_worker's docstring applies
            # to any `-c` run of the venv from the pipeline tree
            proc = subprocess.run(
                [python, "-P", "-c",
                 "import sys, torch; sys.stdout.write('1' if torch.cuda.is_available() else '0')"],
                capture_output=True, text=True, timeout=180, cwd=tempfile.gettempdir())
            _CUDA_ANSWERS[key] = proc.returncode == 0 and proc.stdout.strip() == "1"
        except (OSError, subprocess.TimeoutExpired):
            _CUDA_ANSWERS[key] = False
    return _CUDA_ANSWERS[key]


def device_pair(device="auto", python=None):
    """-> (device, python): the Docling device and the interpreter that runs it, chosen together.

    * ``python`` given: that interpreter, and ``device`` is checked against it.
    * ``python`` omitted: ``cpu`` runs :data:`VENV_PYTHON`; ``cuda`` and ``auto`` run
      :data:`CUDA_VENV_PYTHON` when it exists, else :data:`VENV_PYTHON`.
    * ``auto`` resolves to ``cuda`` when the interpreter can serve it, else ``cpu``.
    * ``cuda`` on an interpreter that cannot serve it raises :class:`DeviceUnavailable` — FAIL
      CLOSED, before anything is converted, never a failed metrics row.
    """
    if device not in DEVICES:
        raise DoclingError(f"device must be one of {DEVICES}, not {device!r}")
    if python is None:
        python = VENV_PYTHON if device == "cpu" else (
            CUDA_VENV_PYTHON if os.path.exists(CUDA_VENV_PYTHON) else VENV_PYTHON)
    if not os.path.exists(python):
        raise DoclingError(
            f"the extraction venv python is not at {python}; docling is deliberately NOT "
            f"installed in the project environment (design M9). Set LITKB_EXTRACT_PYTHON "
            f"or LITKB_EXTRACT_CUDA_PYTHON.")
    if device == "cpu":
        return "cpu", python
    cuda = interpreter_has_cuda(python)
    # BEGIN guard: a cuda request the interpreter cannot serve fails closed
    if device == "cuda" and not cuda:
        raise DeviceUnavailable(
            f"device=cuda was requested, but {python} cannot serve it (its torch reports "
            f"cuda.is_available() False, or it has no torch). Use --device cpu, or point "
            f"LITKB_EXTRACT_CUDA_PYTHON / --docling-python at a CUDA build.")
    # END guard: a cuda request the interpreter cannot serve fails closed
    return ("cuda" if cuda else "cpu"), python


# ── the VRAM knobs, and which of them the measurement kept ────────────────────────────────
#
# THE PROBLEM. The 20 % headroom rule (design §12) means <= 3,277 MiB of the T2000's 4,096. P5's
# bulk pass measured **3,881 MiB, 94.8 %** on its OCR batch (Reports/LITKB_P5_BULK_2026-09-16.md
# §7) — 215 MiB free on a card that also drives the display, within 40 MiB of the 178 MiB
# LITKB_DOCLING_LOCAL §8.3 measured for the formula pass and called the finding. It did not fail;
# it was one open application away from failing.
#
# Re-measured here over P5's own batch B (15 documents, 312 pages, `ocr=on`, CUDA), 1 Hz
# `nvidia-smi`, idle 387 MiB. Every number below is a run, not an argument:
#
#   page_batch_size 4 (docling's default)  3,873 MiB  94.6 %   445.1 s   <- P5's 3,881 reproduces
#   page_batch_size 2                      3,842 MiB  93.8 %   431.9 s
#   page_batch_size 1                      3,893 MiB  95.0 %   440.6 s
#   free_cache between documents           3,475 MiB  84.8 %   436.4 s
#   4 documents per converter PROCESS      2,619 MiB  63.9 %   483.7 s   <- inside the rule
#
# **`page_batch_size` does not move the peak** — the knob named for this job, measured three
# times, is flat inside noise. What dominates is not the per-page activations it governs: it is
# the resident models plus torch's CACHED POOL, which the allocator never returns on its own, so
# in a batch process the reserved pool is a high-water mark over every document that process has
# converted (measured: 3,344 MiB reserved, 468 MiB after a free). That is why returning the pool
# between documents buys 398 MiB, and why ending the PROCESS buys 1,254: a process exit returns
# the models too.
#
# So the cap that lands under the rule is a cap on DOCUMENTS PER CONVERTER PROCESS, and it costs
# 9.7 % of the rate in converter rebuilds. `page_batch` stays available and is recorded on every
# metrics row, because a peak with no setting beside it cannot be compared with another run's —
# but it is NOT applied by default, on the measurement above.
#
# One more thing the measurement changed: on a real SCAN (Anderson 1957, 22 image-only pages, the
# input the fix was asked for) the OCR pass peaks at **1,806 MiB / 44.1 %** — inside the rule
# without any knob at all. The breach is a property of a LONG BATCH, not of OCR on scans.

#: Applied when `ocr=True` and nothing was asked for. 0 = leave docling's own default of 4, which
#: is what the three rows above say makes no difference.
OCR_PAGE_BATCH = 0

#: Applied when `ocr=True`: return torch's cached pool between documents. 398 MiB, at no cost in
#: rate (436.4 s vs 445.1 s, inside run-to-run noise), and nothing in the pool is live between
#: documents so it changes no result.
OCR_FREE_CACHE = True

#: Documents per converter PROCESS on the OCR pass — the cap that actually reaches the headroom
#: rule (2,619 MiB, 63.9 %). Read by the bulk driver's OCR batch; the layout batch keeps its own
#: larger chunk, because batch A peaked at 2,317 MiB / 56.6 % and is inside the rule already.
OCR_CHUNK = 4


def run(jobs, metrics_path, python=None, warmup=None, warmup_pages=1, ocr=False,
        ocr_engine=None, ocr_backend=None, tables_on=True, formula=False, threads=4,
        device="cpu", timeout=7200, cwd=None, page_batch=None, free_cache=None):
    """Run the worker over a job list in the extraction venv. -> [metrics dict].

    ``jobs`` is ``[{"pdf":…, "out":…, "pages":[lo,hi]}, …]``; the worker writes one
    DoclingDocument JSON per job and appends one metrics row per job to ``metrics_path``.

    ``page_batch`` and ``free_cache`` are the two VRAM knobs; the block above them measures what
    each is worth. Leaving either ``None`` with ``ocr=True`` applies :data:`OCR_PAGE_BATCH` and
    :data:`OCR_FREE_CACHE` — the headroom breach is a property of the OCR pass, not of a caller
    remembering to ask. Passing ``0``/``False`` opts out explicitly, which is what the
    measurement that fixed the constants had to do: a constant no run can be made without is a
    constant nobody can re-derive.

    ``cwd`` defaults to the directory holding the metrics file, NOT to the caller's — see
    the worker's docstring: a ``secrets`` directory on ``sys.path[0]`` breaks numpy's import
    and the failure looks nothing like its cause.
    """
    py = python or VENV_PYTHON
    if not os.path.exists(py):
        raise DoclingError(
            f"the extraction venv python is not at {py}; docling is deliberately NOT "
            f"installed in the project environment (design M9). Set LITKB_EXTRACT_PYTHON.")
    work = cwd or os.path.dirname(os.path.abspath(metrics_path)) or os.getcwd()
    jobs_file = os.path.join(work, f"_docling_jobs_{int(time.time() * 1000)}.json")
    os.makedirs(work, exist_ok=True)
    with open(jobs_file, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(jobs, fh)
    # -P: do not prepend the script's directory (which holds THIS module, named docling.py
    # and therefore a shadow of the real package) or the cwd to the worker's sys.path.
    cmd = [py, "-P", WORKER, "--jobs", jobs_file, "--metrics", os.path.abspath(metrics_path),
           "--threads", str(threads), "--device", device]
    if warmup:
        cmd += ["--warmup", warmup, "--warmup-pages", str(warmup_pages)]
    if ocr:
        cmd.append("--ocr")
        if ocr_engine:
            cmd += ["--ocr-engine", ocr_engine]
        if ocr_backend:
            cmd += ["--ocr-backend", ocr_backend]
    # BEGIN guard: the OCR pass runs under the measured VRAM knobs
    # `is None` and not falsy: 0 / False are the deliberate opt-outs that let the measurement run
    # at the tool's own defaults, and `if not page_batch` would silently turn that into the cap.
    if page_batch is None and ocr:
        page_batch = OCR_PAGE_BATCH
    if free_cache is None and ocr:
        free_cache = OCR_FREE_CACHE
    if page_batch:
        cmd += ["--page-batch", str(int(page_batch))]
    if free_cache:
        cmd.append("--free-cache")
    # END guard: the OCR pass runs under the measured VRAM knobs
    if not tables_on:
        cmd.append("--no-tables")
    if formula:
        cmd.append("--formula")
    before = _count_lines(metrics_path)
    try:
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        # A worker that outlives its timeout is a FAILED conversion, reported the way every other
        # one is. Uncaught, the TimeoutExpired reached the caller as a bare traceback (hunt would
        # crash; the queue would lose the reason). subprocess.run has already killed the child.
        raise DoclingError(f"the docling worker ran past its {timeout} s timeout",
                           stderr=(e.stderr or "")[-4000:] if isinstance(e.stderr, str) else "") from e
    rows = _read_metrics(metrics_path)[before:]
    try:
        os.remove(jobs_file)
    except OSError:
        pass
    if proc.returncode != 0 and not rows:
        raise DoclingError(f"the docling worker exited {proc.returncode}",
                           stderr=(proc.stderr or "")[-4000:])
    return rows


def _count_lines(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def _read_metrics(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load(path):
    """Read a DoclingDocument JSON the worker wrote."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def extract(pdf, out_json, metrics_path, require_text_blocks=True, formulas=None,
            density_cut=None, **kw):
    """Run one file and return ``(doc, metrics)`` — the §14 record for that run.

    The refusals are the same two the GROBID adapter learned the hard way: a run with no
    peak-RSS measurement is not a measured run, and a conversion with no body block is a
    FAILED run, not an ok one with zero blocks. Both raise, and the metrics dict travels on
    the exception so the failure is still recorded.

    ``formulas`` is Kam's decision A (2026-09-15):

    * ``"off"`` (default) — no enrichment, one pass. Formula regions are located, not read.
    * ``"all"`` — enrichment over every page, one pass. 160x slower than layout; this is the
      setting the report measured and the one nobody should run on a corpus.
    * ``"auto"`` — TWO passes: the cheap one over the whole file, then enrichment over the
      contiguous runs of pages whose :func:`equation_density` exceeds ``density_cut``
      (default :data:`EQUATION_DENSITY_CUT`), merged back by :func:`merge_formula_latex`. A
      file with no dense page runs exactly one pass and records ``formula_pages = []``.

    The legacy ``formula=True/False`` keyword still works and maps to ``all`` / ``off``, so
    the instrument and the tests written before decision A do not move.
    """
    pages = kw.pop("pages", None)
    legacy = kw.pop("formula", None)
    if formulas is None:
        formulas = "all" if legacy else "off"
    if formulas not in ("auto", "all", "off"):
        raise ValueError(f"formulas must be auto|all|off, not {formulas!r}")
    if formulas == "auto":
        return _extract_auto(pdf, out_json, metrics_path, pages, density_cut,
                             require_text_blocks, kw)
    rows = run([{"pdf": pdf, "out": out_json, "pages": pages}],
               metrics_path, formula=(formulas == "all"), **kw)
    if not rows:
        raise DoclingError(f"the worker recorded no metrics row for {pdf}")
    m = rows[0]
    if m.get("status") != "ok":
        raise DoclingError(f"{pdf}: {m.get('error')}", metrics=m)
    # Docling does not always raise: a file it cannot parse can come back as a RESULT whose
    # status is FAILURE, with a document that has no pages. A caller that watched only for an
    # exception would record that as an ok run, which is the same defect as trusting a 200.
    cs = (m.get("convert_status") or "").upper()
    if "FAILURE" in cs or "SKIPPED" in cs:
        m["status"], m["error"] = "failed", f"docling conversion status {cs}"
        raise DoclingError(f"{pdf}: docling conversion status {cs}", metrics=m)
    if not m.get("peak_rss_bytes"):
        raise DoclingError(
            "the RSS sampler produced no peak — a run with no peak-RSS measurement is not a "
            "measured run (design §14 refuses it)", metrics=m)
    doc = load(out_json)
    if require_text_blocks:
        try:
            check_text_blocks(doc, os.path.basename(pdf))
        except NoTextBlocks as e:
            m["status"], m["error"] = "failed", f"NoTextBlocks: {e}"
            e.metrics = m
            raise
    m["body_blocks"] = len(body_blocks(doc))
    m["tables_found"] = len(tables(doc))
    m["figures_found"] = len(figures(doc))
    m.setdefault("formula_mode", formulas)
    return doc, m


def _extract_auto(pdf, out_json, metrics_path, pages, density_cut, require_text_blocks, kw):
    """The two-pass ``formulas="auto"`` path — see :func:`extract`."""
    cut = EQUATION_DENSITY_CUT if density_cut is None else density_cut
    doc, m = extract(pdf, out_json, metrics_path, require_text_blocks=require_text_blocks,
                     formulas="off", pages=pages, **kw)
    dense = dense_pages(pdf, cut, pages)
    m["formula_mode"] = "auto"
    m["formula_density_cut"] = cut
    m["formula_pages"] = dense
    m["formula_pages_n"] = len(dense)
    m["formula_seconds"] = 0.0
    if not dense:
        m["formula_patched"] = 0
        return doc, m
    enriched = []
    t0 = time.time()
    for lo, hi in page_runs(dense):
        part = f"{out_json}.formula_{lo}-{hi}.json"
        rows = run([{"pdf": pdf, "out": part, "pages": [lo, hi]}], metrics_path,
                   formula=True, **kw)
        if not rows or rows[0].get("status") != "ok":
            m["status"], m["error"] = "failed", "the enrichment pass failed"
            raise FormulaEnrichmentFailed(
                f"{pdf}: the enrichment pass over pages {lo}-{hi} failed: "
                f"{(rows[0].get('error') if rows else 'no metrics row')}", metrics=m)
        enriched.append(load(part))
    m["formula_seconds"] = round(time.time() - t0, 3)
    patched, missing = merge_formula_latex(doc, enriched, pages=set(dense))
    m["formula_patched"] = patched
    m["formula_missing"] = len(missing)
    if missing:
        # FAIL CLOSED. An out-of-memory CodeFormula leaves the native text in place and the
        # conversion still says SUCCESS; recording that as an enriched run would put the
        # PDF's mojibake into a latex column (see FormulaEnrichmentFailed).
        m["status"], m["error"] = "failed", f"{len(missing)} formula regions without LaTeX"
        raise FormulaEnrichmentFailed(
            f"{pdf}: {len(missing)} of {patched + len(missing)} formula regions on enriched "
            f"pages came back with no LaTeX — refusing to record a half-enriched run "
            f"(first: page {missing[0][0]}, {missing[0][1]})", metrics=m)
    with open(out_json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False)
    return doc, m


def append_metrics(metrics, path):
    """Park one metrics dict as JSONL until P5's ingest writes it to ``extraction_runs``."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(metrics, sort_keys=True) + "\n")
    return path


if __name__ == "__main__":   # a hand loop, not an entry point: `python -m` stays with litkb
    src, out = sys.argv[1], sys.argv[2]
    d, met = extract(src, out, out + ".metrics.jsonl")
    print(json.dumps(met, indent=1, sort_keys=True))

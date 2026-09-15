"""Docling stage-3 adapter — DoclingDocument JSON -> the canonical §7.1 block model.

Stage 3 of the design's extraction pipeline (§7): layout, reading order, table structure,
figure regions, OCR for scans, and — with enrichment on — LaTeX for formula regions.
Docling itself never runs in this process: :func:`run` launches
:mod:`litkb.extract.docling_worker` in the extraction venv and this module maps the JSON it
writes. So the project's environment needs nothing but the standard library (and pypdfium2
for the mediabox shift), which is what keeps ``qc/check.py`` free of a 3.7 GB dependency
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
per-page and per-document confidence GRADE (layout / OCR / parse scores) on the conversion
result object, which the worker records into the metrics; :attr:`Block.confidence` is
therefore None here rather than a made-up number, and the document-level grade travels with
the run, not with the block.

ZERO-BLOCK REFUSAL (the defect the GROBID referee found, built in here from the start): a
conversion that "succeeds" and yields no body text is a failure, not an empty-but-fine run.
:func:`check_text_blocks` raises :class:`NoTextBlocks`, and :func:`extract` records such a
run as ``status="failed"`` — never as an ok run with zero blocks.
"""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import time

#: The extraction venv (design M9). Overridable for a machine that puts it elsewhere.
VENV_PYTHON = os.environ.get(
    "LITKB_EXTRACT_PYTHON", r"D:\edmonds-pipeline\venv-docling\Scripts\python.exe")

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
        for i, prov in enumerate(provs):
            page = int(prov["page_no"])
            h = page_size(doc, page)
            x0, y0, x1, y1 = to_canonical(prov["bbox"], h[1] if h else None)
            yield Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind=label, text=text,
                        element_id=item.get("self_ref"), box_index=i, box_count=len(provs),
                        order_index=order, content_layer=layer)


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


# ── the cropbox -> mediabox frame shift (shared rule with the GROBID adapter) ────────────

def page_frames(pdf_path):
    """{page: {mediabox, cropbox, rotation, dx, dy}} read from the PDF with pypdfium2.

    The DoclingDocument carries the cropbox's SIZE only, never its origin, so the offset
    cannot be recovered from the JSON alone. ``dx = crop.x0 - media.x0`` and
    ``dy = media.y1 - crop.y1`` are what :func:`to_mediabox` adds.
    """
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as praw

    def _box(fn, page):
        vals = [ctypes.c_float() for _ in range(4)]
        ok = fn(page.raw, *[ctypes.byref(v) for v in vals])
        return tuple(v.value for v in vals) if ok else None

    frames = {}
    doc = pdfium.PdfDocument(pdf_path)
    try:
        for i in range(len(doc)):
            page = doc[i]
            media = _box(praw.FPDFPage_GetMediaBox, page)
            crop = _box(praw.FPDFPage_GetCropBox, page) or media
            rot = int(praw.FPDFPage_GetRotation(page.raw))
            frames[i + 1] = {"mediabox": media, "cropbox": crop, "rotation": rot,
                             "dx": crop[0] - media[0], "dy": media[3] - crop[3]}
    finally:
        doc.close()
    return frames


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


def run(jobs, metrics_path, python=None, warmup=None, warmup_pages=1, ocr=False,
        ocr_engine=None, tables_on=True, formula=False, threads=4, device="cpu",
        timeout=7200, cwd=None):
    """Run the worker over a job list in the extraction venv. -> [metrics dict].

    ``jobs`` is ``[{"pdf":…, "out":…, "pages":[lo,hi]}, …]``; the worker writes one
    DoclingDocument JSON per job and appends one metrics row per job to ``metrics_path``.

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
    if not tables_on:
        cmd.append("--no-tables")
    if formula:
        cmd.append("--formula")
    before = _count_lines(metrics_path)
    proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout)
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


def extract(pdf, out_json, metrics_path, require_text_blocks=True, **kw):
    """Run one file and return ``(doc, metrics)`` — the §14 record for that run.

    The refusals are the same two the GROBID adapter learned the hard way: a run with no
    peak-RSS measurement is not a measured run, and a conversion with no body block is a
    FAILED run, not an ok one with zero blocks. Both raise, and the metrics dict travels on
    the exception so the failure is still recorded.
    """
    rows = run([{"pdf": pdf, "out": out_json, "pages": kw.pop("pages", None)}],
               metrics_path, **kw)
    if not rows:
        raise DoclingError(f"the worker recorded no metrics row for {pdf}")
    m = rows[0]
    if m.get("status") != "ok":
        raise DoclingError(f"{pdf}: {m.get('error')}", metrics=m)
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

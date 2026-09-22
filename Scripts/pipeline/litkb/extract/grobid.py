"""GROBID 0.9.1 (CRF) adapter — service control, one-file processing, and the §7.1 bbox adapter.

The service itself runs under WSL2 Ubuntu and is managed by ``grobid.sh`` beside this file;
see ``LITKB_GROBID_LOCAL_2026-09-14.md`` for the install layout and the measured numbers.

CANONICAL FRAME (design §7.1): PDF points, page numbers 1-indexed, origin at the TOP-LEFT of
the page as displayed, box = (x0, y0, x1, y1), measured on the **mediabox**.

WHAT GROBID EMITS: ``coords="page,x,y,w,h"`` — page 1-indexed, PDF units, origin upper-left
(measured against the ``<facsimile>`` surfaces, 2026-09-14). So the adapter is
``x1 = x + w, y1 = y + h`` with NO page offset and NO y-flip.

WHICH BOX THE ORIGIN SITS ON — the cropbox, NOT the mediabox. ``<surface>`` carries the
CROPBOX's size and every coord is measured from the cropbox's upper-left corner. Measured
2026-09-14 on ``Alwan_1988`` p2/p3 (mediabox ``(0,0,612,792)``, cropbox
``(10.345,10.777,603.441,782.948)``, ``<surface>`` 593.096 x 772.171 = the cropbox): a whole
``<ref>`` element's box agrees with pypdfium2 to **0.39-0.91 pt** once the cropbox origin is
added back, and is off by **10.5-10.9 pt** if it is not. 223 pages of the 216-PDF corpus have
cropbox != mediabox, so this is not a corner case. :func:`page_frames` reads the two boxes
from the PDF and :func:`to_mediabox` shifts blocks into the canonical mediabox frame; every
:class:`Block` states which frame it is in via ``Block.frame``.

Rotation IS applied by GROBID (a ``/Rotate 90`` page gets a landscape ``<surface>``), and
:func:`to_mediabox` **refuses** to convert a rotated page, leaving those blocks in the cropbox
frame. That refusal is no longer a precaution: measured 2026-09-15 on the one page in the corpus
where it can cost anything, the translation `to_mediabox` applies is simply the WRONG MAP there —
for 180° the correct map is a REFLECTION. See :func:`to_mediabox`.

ZERO-BLOCK REFUSAL: a 200 is not success. A PDF with a text layer on only some pages — a
JSTOR scan whose cover page carries the access boilerplate — returns HTTP 200 with a valid
header and an EMPTY ``<text><body>`` (measured on ``Anderson_1957``: 3,659 B, 4 blocks, all
of them the boilerplate title in the header, ``<body>`` text ``''``). A caller checking only
the status code records that as a successful extraction. :func:`process_pdf` therefore refuses
any TEI with fewer than :data:`MIN_BODY_BLOCKS` coordinate-bearing blocks inside
``<text><body>``, raising :class:`NoTextBlocks`. The threshold is 4, not 1: one injected junk
box was enough to walk through the original rule — see :data:`MIN_BODY_BLOCKS`.

Two properties of the real output the adapter must honour, both measured rather than assumed:

  * a single ``coords`` value may hold SEVERAL boxes separated by ``;`` — one per line for a
    span that wraps, and for a figure, one per caption line plus one for the graphic. Each is
    emitted as its own block; collapsing them to the first box silently drops most of a
    multi-line region.
  * ``<s>`` sentence coordinates only appear when the request carries ``segmentSentences=1``.

CONFIDENCE: GROBID's TEI carries no per-element confidence for these elements, so
``Block.confidence`` is None here rather than a made-up number. UNCONFIRMED whether any
0.9.1 endpoint can emit one.
"""
from __future__ import annotations

import dataclasses
import http.client
import mimetypes
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET

TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"t": TEI_NS}

EXTRACTOR = "grobid-0.9.1-crf"
DEFAULT_URL = os.environ.get("GROBID_URL", "http://localhost:8070")

#: The elements the design asks to be coordinate-bearing (§14 P4, §16 GROBID row).
COORD_ELEMENTS = ("ref", "biblStruct", "persName", "figure", "formula",
                  "head", "s", "p", "note", "title")

#: Path to the WSL manager script that installs/starts/stops the service.
_HERE = os.path.dirname(os.path.abspath(__file__))
MANAGER_SH = os.path.join(_HERE, "grobid.sh")

#: The distro the service runs in. The manager script is invoked as root.
WSL_DISTRO = os.environ.get("GROBID_WSL_DISTRO", "Ubuntu")


class GrobidError(RuntimeError):
    """The service refused a document, or was unreachable.

    A non-200 response is ALWAYS an error here, 204 included: GROBID answers 204 No Content
    for a PDF it can extract nothing from, and treating that as "empty but fine" would let a
    silently unextracted file into the lake as a zero-block run.
    """

    def __init__(self, message, status=None, body=b"", metrics=None):
        super().__init__(message)
        self.status = status
        self.body = body
        #: the §14 metrics dict for a failed run, when the error came from :func:`extract`
        self.metrics = metrics


class NoTextBlocks(GrobidError):
    """HTTP 200, valid TEI, and NOTHING extracted from the document body.

    The partial-text-layer case (§8.3 of the builder's report, narrowed by the referee): a
    file with no text layer AT ALL is refused by the service itself with a 500
    ``[NO_BLOCKS]``, but a scan whose cover page carries a text layer comes back 200 with a
    header parsed from the boilerplate and an empty ``<text><body>``. This is the error that
    keeps such a run out of the lake as anything but a failure.
    """


@dataclasses.dataclass(frozen=True)
class Block:
    """One coordinate-bearing region in the canonical §7.1 frame."""

    page: int           # 1-indexed
    x0: float           # PDF points, origin top-left of the page as displayed
    y0: float
    x1: float
    y1: float
    kind: str           # TEI local name: ref, head, figure, s, p, note, title, ...
    text: str = ""
    extractor: str = EXTRACTOR
    confidence: float | None = None   # GROBID TEI carries none for these elements
    element_id: str | None = None     # xml:id where the element has one
    box_index: int = 0                # position within a multi-box ";" coords value
    box_count: int = 1
    frame: str = "cropbox"            # "cropbox" as GROBID emits it; "mediabox" after to_mediabox()
    #: The part of the element's text that BEGINS on this line box, read from the element's
    #: ``<s>`` children (:func:`sentence_pieces`), or None where they cannot say. Same field, same
    #: rule as :attr:`litkb.extract.docling.Block.piece`: ``text`` stays the whole element's.
    piece: str | None = None

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0

    def contains(self, x, y, tol=0.0):
        return (self.x0 - tol) <= x <= (self.x1 + tol) and (self.y0 - tol) <= y <= (self.y1 + tol)


# ── the §7.1 adapter ────────────────────────────────────────────────────────────────────

def parse_coords(value):
    """``"page,x,y,w,h[;page,x,y,w,h...]"`` -> [(page, x0, y0, x1, y1), ...].

    The ";" split is load-bearing: a wrapped title or a captioned figure carries one box per
    line. Malformed groups are skipped rather than guessed at.
    """
    boxes = []
    for group in (value or "").split(";"):
        parts = group.strip().split(",")
        if len(parts) != 5:
            continue
        try:
            page = int(float(parts[0]))
            x, y, w, h = (float(p) for p in parts[1:])
        except ValueError:
            continue
        # x1 = x + w, y1 = y + h — GROBID's origin already matches the canonical frame,
        # so there is no y-flip and no page renumbering.
        boxes.append((page, x, y, x + w, y + h))
    return boxes


def page_sizes(tei):
    """{page: (width, height)} from ``<facsimile><surface>``; the TEI's own page census."""
    root = _root(tei)
    sizes = {}
    for surface in root.iterfind(".//t:facsimile/t:surface", NS):
        try:
            n = int(surface.get("n"))
            sizes[n] = (float(surface.get("lrx")) - float(surface.get("ulx")),
                        float(surface.get("lry")) - float(surface.get("uly")))
        except (TypeError, ValueError):
            continue
    return sizes


def iter_blocks(tei, kinds=None, subtree=None):
    """Yield a :class:`Block` for every box on every coordinate-bearing element.

    ``subtree`` is an ElementPath evaluated from the TEI root; only elements below the first
    match are walked (``".//t:text/t:body"`` for :func:`body_blocks`). Nothing matching means
    nothing is yielded — which is the whole point of the zero-block gate.
    """
    root = _root(tei)
    if subtree is not None:
        root = root.find(subtree, NS)
        if root is None:
            return
    wanted = set(kinds) if kinds else None
    for el in root.iter():
        coords = el.get("coords")
        if not coords:
            continue
        kind = el.tag.split("}")[-1]
        if wanted is not None and kind not in wanted:
            continue
        boxes = parse_coords(coords)
        text = " ".join("".join(el.itertext()).split())
        eid = el.get("{http://www.w3.org/XML/1998/namespace}id")
        pieces = sentence_pieces(el, boxes) if len(boxes) > 1 else None
        for i, (page, x0, y0, x1, y1) in enumerate(boxes):
            yield Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind=kind, text=text,
                        element_id=eid, box_index=i, box_count=len(boxes),
                        piece=pieces[i] if pieces is not None else None)


def sentence_pieces(el, boxes):
    """-> [raw str per box of ``boxes``] that TILE ``"".join(el.itertext())``, or None.

    GROBID records NO text per line: an element's ``coords`` is one box per line and its text is
    one string. What it does record, with ``segmentSentences=1`` (the default here), is a
    ``coords`` value on every ``<s>`` child — so the text can be cut, at SENTENCE granularity, by
    the line box each sentence begins in. A sentence whose lines cross the page break is kept
    WHOLE on the page where it BEGINS: the tool gives no position inside a sentence, and a cut
    there would be a guess. MEASURED on the 229 stored P5 TEIs (2026-09-22, builder-D2 report):
    1,870 ``<p>`` elements have line boxes on more than one page; 351 break between sentences and
    1,519 inside one, so on most cross-page paragraphs the page-N fragment ends with the whole
    sentence that runs over the break, and page N+1's begins with the next one. This function
    reads back 1,869 of the 1,870 (the one left: a sentence whose first box shares no line with
    any of the element's line boxes). The 4 cross-page ``<head>`` / ``<note>`` have no ``<s>``
    at all and keep their whole text.

    A fragment in whose lines NO sentence begins gets an EMPTY piece — its words are stored
    under the page where their sentence begins. Its box is kept: coverage and reading order are
    read from boxes, and the region is still printed there.

    Each direct child (a sentence, or anything else, with its ``tail``) is a chunk of the raw
    string; the element's leading text goes with the first chunk, a child with no coords of its
    own goes with the chunk before it. A sentence is placed in the line box, on the page of its
    FIRST box, that overlaps that box horizontally and most vertically. The chunks must land in
    non-decreasing box order, or the cut would reorder the text, and every chunk must land — any
    failure returns None and the caller keeps the element's whole text (the old behaviour).
    """
    kids = list(el)
    if not any(k.tag.split("}")[-1] == "s" for k in kids):
        return None
    chunks = []          # [box_index | None, raw text]
    lead = el.text or ""
    for k in kids:
        raw = "".join(k.itertext()) + (k.tail or "")
        where = None
        if k.tag.split("}")[-1] == "s":
            sb = parse_coords(k.get("coords") or "")
            if not sb:
                return None
            where = _line_of(sb[0], boxes)
            if where is None:
                return None
        chunks.append([where, raw])
    # a child with no position of its own rides with the chunk before it; the leading text and
    # anything before the first sentence ride with the first sentence
    first = next(c[0] for c in chunks if c[0] is not None)
    last = first
    for c in chunks:
        if c[0] is None:
            c[0] = last
        last = c[0]
    order = [c[0] for c in chunks]
    if order != sorted(order):
        return None
    pieces = [""] * len(boxes)
    pieces[first] = lead
    for where, raw in chunks:
        pieces[where] += raw
    return pieces if "".join(pieces) == "".join(el.itertext()) else None


def _line_of(box, boxes):
    """Index of the line box in ``boxes`` that holds ``box``, or None.

    Same page and overlapping vertically; among those, one that also overlaps in x wins, then the
    larger vertical overlap, then the nearer in x. The x fallback is not slack, it is measured: an
    element's ``coords`` leave OUT the inline ``<ref>`` spans, so a line reads as two boxes with a
    gap where a citation sits, and a sentence that BEGINS with a citation ("Dai and Khorram
    (1997) used ...") begins in that gap — 80 sentences of 60 cross-page ``<p>`` in the 229 P5
    TEIs (2026-09-22) had no x-overlapping line box, every one of them in such a gap.
    """
    page, x0, y0, x1, y1 = box
    best, best_key = None, None
    for i, (p, a0, b0, a1, b1) in enumerate(boxes):
        v = min(y1, b1) - max(y0, b0)
        if p != page or v <= 0:
            continue
        xo = min(x1, a1) - max(x0, a0)
        key = (xo > 0, v, -max(0.0, -xo))
        if best_key is None or key > best_key:
            best, best_key = i, key
    return best


def blocks(tei, kinds=None):
    return list(iter_blocks(tei, kinds))


BODY_PATH = ".//t:text/t:body"


def body_blocks(tei, kinds=None):
    """Coordinate-bearing blocks from ``<text><body>`` only — the document, not the header.

    The header alone is not extraction: a JSTOR cover page's access boilerplate parses into a
    header title and nothing else (measured on ``Anderson_1957``, 2026-09-14).
    """
    return list(iter_blocks(tei, kinds, subtree=BODY_PATH))


#: Where the header's three assignable kinds live in a TEI, and what each is called in the
#: canonical vocabulary. ``title`` and ``persName`` are in :data:`COORD_ELEMENTS`, so both come
#: back as real boxes; ``affiliation`` is NOT, and comes back as strings only.
HEADER_PATH = ".//t:teiHeader"


def header_regions(tei):
    """-> ``{"title": [Block], "author": [Block], "affiliation": [str]}`` from ``<teiHeader>``.

    The three kinds stage 5 can put on a block that no BODY matcher can name: a paper's own
    title, its author line and its affiliation footer (final referee §2 — 8 of the 18 block types
    were never assigned, and these are the three the header can fix). Boxes are in GROBID's own
    CROPBOX frame, like everything else this module returns; the caller converts.

    Only the ``<titleStmt>``'s ``level="a"`` title is taken. A ``<monogr>`` title is the JOURNAL's
    name, which is furniture on the page, not the paper's title, and taking it would re-kind the
    running head.
    """
    root = _root(tei)
    head = root.find(HEADER_PATH, NS)
    out = {"title": [], "author": [], "affiliation": []}
    if head is None:
        return out
    for el in head.iterfind(".//t:titleStmt/t:title", NS):
        if el.get("level") not in (None, "a"):
            continue
        text = " ".join("".join(el.itertext()).split())
        for i, (page, x0, y0, x1, y1) in enumerate(parse_coords(el.get("coords") or "")):
            out["title"].append(Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind="title",
                                      text=text, box_index=i))
    for author in head.iterfind(".//t:sourceDesc//t:author", NS):
        for el in author.iterfind("t:persName", NS):
            text = " ".join("".join(el.itertext()).split())
            for i, (page, x0, y0, x1, y1) in enumerate(parse_coords(el.get("coords") or "")):
                out["author"].append(Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind="author",
                                           text=text, box_index=i))
        for aff in author.iterfind("t:affiliation", NS):
            for org in aff.iterfind(".//t:orgName", NS):
                s = " ".join("".join(org.itertext()).split())
                if s and s.lower() != "unknown":
                    out["affiliation"].append(s)
    return out


def body_text(tei):
    """Whitespace-normalised text of ``<text><body>`` ('' when there is no body at all)."""
    el = _root(tei).find(BODY_PATH, NS)
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


#: The minimum number of ``<text><body>`` boxes that counts as an extracted document.
#:
#: The rule was ``>= 1`` and was untested at 1 (referee 2, D3): injecting ONE junk ``<p>`` box —
#: a page number's worth — into the Anderson scan's empty body took it from refused to admitted
#: with nothing downstream flagging it. The referee could not get GROBID to EMIT such a body from
#: four synthetic PDFs, so this is a gap in the gate, not a demonstrated hole; a real scan with one
#: stray extracted line would walk through it.
#:
#: Why 4, from the mechanism rather than a round number. Requests go out with
#: ``segmentSentences=1`` (the default here), so ONE genuine paragraph of three sentences already
#: yields four boxes — the ``<p>`` plus three ``<s>``. Page furniture on a scan's text-layer page
#: is at most three: page number, running head, footer. Four is therefore the lowest value that
#: separates the two by mechanism, and the highest the evidence supports: the trimmed
#: ``grobid_sample`` fixture carries 8 body blocks, so anything above 8 would start refusing a
#: paper that really was extracted. (Live Benedek has 3,300; the bound that matters here is the
#: fixture's 8, not the live number.)
#:
#: PROVISIONAL. The honest form of "is 4 right" is a per-PDF body-block census over the corpus —
#: the stage-2 empirical question the referee named. What is settled is that 0 was wrong and that
#: 1 was undefended. A caller that lowers this to 1 re-opens D3.
MIN_BODY_BLOCKS = 4


def check_text_blocks(tei, name="", minimum=MIN_BODY_BLOCKS):
    """Raise :class:`NoTextBlocks` when a 200 carried no extracted document body.

    The rule is BLOCK-BASED, not byte-based: a body with text but no coordinates would mean
    the request forgot ``teiCoordinates`` (which is a caller bug, and is reported as one),
    while a body with neither is a document that was not extracted. Both are refusals. The
    threshold is :data:`MIN_BODY_BLOCKS`, not 1 — see its note.
    """
    n_blocks = len(body_blocks(tei))
    if n_blocks >= minimum:
        return n_blocks
    what = name or "document"
    raise NoTextBlocks(
        f"GROBID returned 200 for {what} but its <text><body> yields {n_blocks} "
        f"coordinate-bearing block(s), below the {minimum} that distinguishes an extracted "
        f"document from page furniture (body text {len(body_text(tei))} chars, header title "
        f"{header_title(tei)[:60]!r}) — refusing to record an empty extraction",
        200, tei if isinstance(tei, bytes) else b"")


def header_title(tei):
    """The header's main title, whitespace-normalised ('' when absent)."""
    root = _root(tei)
    el = root.find(".//t:teiHeader//t:titleStmt/t:title", NS)
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def bibl_structs(tei):
    """Parsed bibliographic entries (the reference list plus the header's own analytic)."""
    return _root(tei).findall(".//t:biblStruct", NS)


def implausible_blocks(tei, tol=1.0):
    """Blocks whose page is unknown or whose box escapes the page — the gate's box check.

    Returns a list of (block, reason); empty means every box sits inside its page.
    """
    sizes = page_sizes(tei)
    bad = []
    for b in iter_blocks(tei):
        if b.page < 1:
            bad.append((b, f"page {b.page} is not 1-indexed"))
            continue
        if b.page not in sizes:
            bad.append((b, f"page {b.page} has no <surface>"))
            continue
        w, h = sizes[b.page]
        if b.x1 < b.x0 or b.y1 < b.y0:
            bad.append((b, "inverted box"))
        elif b.x0 < -tol or b.y0 < -tol or b.x1 > w + tol or b.y1 > h + tol:
            bad.append((b, f"box outside page {w}x{h}"))
    return bad


# ── the cropbox -> mediabox frame shift ─────────────────────────────────────────────────

def page_frames(pdf_path):
    """{page: dict} — each page's mediabox, cropbox, rotation and the GROBID->mediabox shift.

    Read from the PDF with pypdfium2 (the TEI carries only the cropbox's SIZE, never its
    origin, so the offset cannot be recovered from the TEI alone). ``dx``/``dy`` are what
    :func:`to_mediabox` adds: dx = crop.x0 - media.x0, dy = media.y1 - crop.y1, i.e. the
    cropbox's upper-left corner expressed in the mediabox's upper-left frame.

    ONE HOME (2026-09-15): the body is :func:`litkb.extract.inventory.page_frames`, whose
    docstring owns the rule. This wrapper exists because three modules kept three copies with
    three different guards, and design §7.1 required them collapsed before stage 5 was
    written. The only thing the wrapper adds is the exception class: a page with no mediabox
    raises :class:`GrobidError` here, as it did before.
    """
    from litkb.extract import inventory

    return inventory.page_frames(pdf_path, error=GrobidError)


def to_mediabox(blocks_in, frames):
    """Shift blocks from GROBID's cropbox-relative frame into the canonical mediabox frame.

    A page with ``rotation != 0`` is NOT converted. GROBID reports it in the displayed
    (rotated) frame — confirmed, not assumed — and the translation below is the wrong map for
    such a page, so those blocks come back unchanged, still carrying ``frame="cropbox"``, and a
    caller can see exactly which ones were skipped. A page with no frame record is likewise
    left alone.

    MEASURED 2026-09-15 (referee 2 §4). Rotation only costs anything where the page ALSO has
    cropbox != mediabox, and across 224 PDFs / 4,712 pages that intersection is **exactly one
    page**: ``Hall_1985_resampling-coverage-pattern.pdf`` p12, rotation 180, mediabox
    ``(0,0,463,685)``, cropbox ``(2,0,463,684)``. (The 90° page used earlier, ``Guo_2019`` p6,
    has cropbox == mediabox, so dx = dy = 0 and the refusal is a no-op there.) On Hall p12,
    reading GROBID's 551 body blocks in the rot-180 displayed frame matches pypdfium2 to
    **2.04 pt**, against 10.99 pt read unrotated.

    And the correct map for 180° is a REFLECTION, not this translation::

        x_m = crop.x1 - X                       # not X + dx
        y_m = media.y1 - crop.y0 - Y            # not Y + dy

    On Hall p12 the two agree nowhere: a block at displayed x = 49.8 belongs at x_m = 413.2 and
    the translation would put it at 51.8 — a **361.4 pt** error, roughly the page width; in y a
    block at displayed y = 63.2 belongs at 621.8 and would land at 64.2, a **557.6 pt** error.
    For 90°/270° the axes swap as well. Implementing the per-rotation maps is FUTURE WORK
    (one page of the present corpus); until then refusing is the only correct behaviour
    available, and ``test_to_mediabox_refuses_a_rotated_page*`` pins it.
    """
    out = []
    for b in blocks_in:
        f = frames.get(b.page)
        if f is None or f["rotation"]:
            out.append(b)
            continue
        dx, dy = f["dx"], f["dy"]
        out.append(dataclasses.replace(
            b, x0=b.x0 + dx, y0=b.y0 + dy, x1=b.x1 + dx, y1=b.y1 + dy, frame="mediabox"))
    return out


def title_matches_registry(tei, registry_title):
    """-> (ok, ratio). Uses the project's ONE title rule (litkb.admit.resolver)."""
    from litkb.admit.resolver import RESOLVE_TITLE_RATIO, title_match_ratio
    ratio = title_match_ratio(header_title(tei), registry_title or "")
    return ratio >= RESOLVE_TITLE_RATIO, ratio


def _root(tei):
    if isinstance(tei, ET.Element):
        return tei
    if isinstance(tei, bytes):
        return ET.fromstring(tei)
    return ET.fromstring(tei.encode("utf-8") if isinstance(tei, str) else tei)


# ── the service ─────────────────────────────────────────────────────────────────────────

def _manager(action, timeout=1800):
    """Run grobid.sh inside WSL. One wsl.exe invocation per batch: when the last session
    exits, WSL begins shutting the distro down and systemd stops every unit (measured
    2026-09-14 as status=143/SIGTERM), so a service started by one call may be gone by the
    next. Callers that need it up should call start() at the head of the same batch."""
    sh = MANAGER_SH.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", sh):  # Windows path -> /mnt/<drive>/...
        sh = f"/mnt/{sh[0].lower()}{sh[2:]}"
    cmd = ["wsl.exe", "-d", WSL_DISTRO, "-u", "root", "--", "bash", sh, action]
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


_KEEPALIVE = None


def hold_distro():
    """Hold the WSL distro open for as long as THIS Python process lives.

    Measured 2026-09-14: when the last wsl.exe client exits, WSL starts shutting the distro
    down and systemd SIGTERMs every unit. A caller on the Windows side that merely runs
    `grobid.sh start` in one wsl.exe call and then posts from Python sees the service accept
    one request, drop it mid-flight, and refuse every request after — the service is not
    crashing, the distro is going away underneath it.

    Holding one long-lived `sleep infinity` client keeps the distro up. The child is killed
    at interpreter exit, so nothing is left running. The alternative — setting
    vmIdleTimeout in the user's %UserProfile%\\.wslconfig — is a machine-wide change to
    Kam's config and is deliberately NOT made here.
    """
    global _KEEPALIVE
    if _KEEPALIVE is not None and _KEEPALIVE.poll() is None:
        return _KEEPALIVE
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    _KEEPALIVE = subprocess.Popen(
        ["wsl.exe", "-d", WSL_DISTRO, "-u", "root", "--", "sleep", "infinity"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env)
    import atexit
    atexit.register(release_distro)
    return _KEEPALIVE


def release_distro():
    global _KEEPALIVE
    if _KEEPALIVE is not None:
        try:
            _KEEPALIVE.terminate()
            _KEEPALIVE.wait(timeout=10)
        except Exception:
            pass
        _KEEPALIVE = None


def health(url=DEFAULT_URL, timeout=5):
    try:
        with urllib.request.urlopen(f"{url}/api/isalive", timeout=timeout) as r:
            return r.read().decode().strip() == "true"
    except Exception:
        return False


def version(url=DEFAULT_URL, timeout=5):
    with urllib.request.urlopen(f"{url}/api/version", timeout=timeout) as r:
        return r.read().decode().strip()


def start(url=DEFAULT_URL, wait=240, hold=True):
    """Idempotent: returns at once when already alive.

    ``hold`` keeps the distro open for this process's lifetime (see :func:`hold_distro`);
    without it a Windows-side caller's service disappears as soon as the launching
    wsl.exe call returns.
    """
    if hold:
        hold_distro()
    if health(url):
        return True
    _manager("start")
    deadline = time.time() + wait
    while time.time() < deadline:
        if health(url):
            return True
        time.sleep(2)
    return False


def stop():
    _manager("stop", timeout=120)


def process_pdf(path, url=DEFAULT_URL, coord_elements=COORD_ELEMENTS,
                segment_sentences=True, consolidate_header=False,
                consolidate_citations=False, timeout=3600, require_text_blocks=True,
                include_raw_citations=False):
    """POST one PDF to processFulltextDocument -> TEI bytes.

    ``teiCoordinates`` is a REPEATED form field, one element name per field. Passing the
    list as a single comma-joined value is accepted but yields almost no coordinates
    (measured 2026-09-14: 7 coords across a four-paper set, none on refs, heads or figures).

    Consolidation is off by default: it reaches Crossref over the network, and the design
    keeps stage 2 offline unless a caller opts in.

    ``require_text_blocks`` (default ON) applies :func:`check_text_blocks`, so a 200 that
    extracted nothing raises :class:`NoTextBlocks` instead of returning. Turning it off is
    only for callers that want to INSPECT such a TEI; no ingest path may.
    """
    fields = [("consolidateHeader", "1" if consolidate_header else "0"),
              ("consolidateCitations", "1" if consolidate_citations else "0")]
    if segment_sentences:
        fields.append(("segmentSentences", "1"))
    # includeRawCitations=1 is what makes GROBID emit <note type="raw_reference"> inside each
    # <biblStruct> — the reference string AS PRINTED, which stage 6 stores as references.raw
    # (design §4.4). It is OFF by default so P4's measured runs keep their exact params hash;
    # stage 6 opts in, and gets a new params hash for doing so.
    if include_raw_citations:
        fields.append(("includeRawCitations", "1"))
    fields += [("teiCoordinates", e) for e in coord_elements]

    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n').encode()
    with open(path, "rb") as fh:
        data = fh.read()
    ctype = mimetypes.guess_type(path)[0] or "application/pdf"
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="input"; '
             f'filename="{os.path.basename(path)}"\r\nContent-Type: {ctype}\r\n\r\n').encode()
    body += data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{url}/api/processFulltextDocument", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Accept": "application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                raise GrobidError(f"GROBID returned {r.status} for {os.path.basename(path)}",
                                  r.status, r.read())
            tei = r.read()
        if require_text_blocks:
            check_text_blocks(tei, os.path.basename(path))
        return tei
    except urllib.error.HTTPError as e:
        raise GrobidError(f"GROBID returned {e.code} for {os.path.basename(path)}",
                          e.code, e.read()) from e
    except urllib.error.URLError as e:
        raise GrobidError(f"GROBID unreachable at {url}: {e.reason}") from e
    except (http.client.HTTPException, OSError) as e:
        # The JVM can drop the connection mid-upload — under WSL this happens when the
        # distro starts shutting down and systemd SIGTERMs the unit while a request is in
        # flight (measured 2026-09-14). http.client.RemoteDisconnected is NOT wrapped by
        # urllib, so without this arm it escapes as a bare exception and a caller's
        # "except GrobidError" misses it entirely.
        raise GrobidError(f"GROBID dropped the connection for "
                          f"{os.path.basename(path)}: {e!r}") from e


# ── the §14 throughput record ───────────────────────────────────────────────────────────

CGROUP_MEMORY = "/sys/fs/cgroup/system.slice/grobid.service/memory.current"


class _RssSampler:
    """Peak memory of the GROBID unit, sampled from its cgroup while a request is in flight.

    ONE long-lived ``wsl.exe`` child prints ``memory.current`` on a loop; a per-sample
    ``wsl.exe`` costs ~200 ms and would sample the sampler. ``memory.current`` is read rather
    than ``memory.peak``/``VmHWM`` because those are LIFETIME high-water marks and would
    report the largest request the service ever served, not this one.

    THIS IS NOT A PER-WORKER FIGURE. GROBID serves its whole pool from one JVM, so the
    cgroup covers every worker plus pdfalto; per-worker memory can only be DERIVED from the
    slope across pool sizes (measured 2026-09-14: ~689 MiB per added worker).
    """

    def __init__(self, interval=0.5):
        self.interval = interval
        self._proc = None
        self.samples = []

    def __enter__(self):
        env = dict(os.environ, MSYS_NO_PATHCONV="1")
        self._proc = subprocess.Popen(
            ["wsl.exe", "-d", WSL_DISTRO, "-u", "root", "--", "bash", "-c",
             f"while :; do cat {CGROUP_MEMORY} 2>/dev/null || echo 0; sleep {self.interval}; done"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, text=True)
        return self

    def __exit__(self, *exc):
        if self._proc is None:
            return False
        self._proc.terminate()
        try:
            out, _ = self._proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            out, _ = self._proc.communicate()
        self.samples = [int(ln) for ln in (out or "").split() if ln.strip().isdigit()]
        self._proc = None
        return False

    @property
    def peak(self):
        return max(self.samples) if self.samples else 0


def pdf_page_count(path):
    """Page count from the PDF itself — the denominator of pages/s must not come from the TEI,
    which only lists the pages GROBID managed to lay out."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        return len(doc)
    finally:
        doc.close()


def extract(path, url=DEFAULT_URL, concurrency=None, sample_rss=True, **kw):
    """Run one file and return ``(tei, metrics)`` — the §14 throughput record for that run.

    ``metrics`` is the dict the design's ``extraction_runs.metrics`` column (§4.3, JSON:
    seconds, pages/s, peak RSS, coverage) is specified to hold. **The row itself is not
    written here:** ``extraction_runs`` requires a ``files`` row and the ``litkb_ingest``
    login, both of which belong to the P3/P5 ingest path; this function produces the dict
    that P5's ingest persists into ``extraction_runs.metrics`` verbatim, and
    :func:`append_metrics` parks it as JSONL until then.

    A failed run still returns a metrics dict (through the raised error's ``metrics``
    attribute) with ``status="failed"`` — a :class:`NoTextBlocks` refusal is recorded as a
    FAILED run, never as an ok one with zero blocks.
    """
    pages = pdf_page_count(path)
    sampler = _RssSampler() if sample_rss else None
    started = time.time()
    ctx = sampler if sampler is not None else _null_ctx()
    status, err, tei = "ok", None, None
    with ctx:
        t0 = time.time()
        try:
            tei = process_pdf(path, url=url, **kw)
        except GrobidError as e:
            status, err = "failed", f"{type(e).__name__}: {e}"
        seconds = time.time() - t0
    peak = sampler.peak if sampler is not None else None
    if sampler is not None and not sampler.samples:
        raise GrobidError(
            "the RSS sampler produced no samples — a run with no peak-RSS measurement is not "
            "a measured run (§14 refuses it); is the grobid unit up under WSL?")
    metrics = {
        "tool": EXTRACTOR,
        "stage": "2-structure",
        "status": status,
        "error": err,
        "file": os.path.basename(path),
        "pages": pages,
        "seconds": round(seconds, 3),
        "pages_per_s": round(pages / seconds, 3) if seconds > 0 else None,
        "peak_rss_bytes": peak,
        "peak_rss_scope": "grobid.service cgroup (whole JVM pool + pdfalto), NOT per worker",
        "concurrency": concurrency,
        "frame": "cropbox",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(started)),
        "host": "local-wsl2",
    }
    if status == "failed":
        raise GrobidError(f"{path}: {err}", metrics=metrics)
    metrics["body_blocks"] = len(body_blocks(tei))
    return tei, metrics


def append_metrics(metrics, path):
    """Park one metrics dict as JSONL until P5's ingest writes it to ``extraction_runs``."""
    import json
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(metrics, sort_keys=True) + "\n")
    return path


class _null_ctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

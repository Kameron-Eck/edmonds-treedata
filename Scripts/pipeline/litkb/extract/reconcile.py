"""Stage 5 — reconciliation: two tools' boxes into ONE set of canonical blocks (design §7 stage 5).

The inputs are ARTIFACTS, never tools: a GROBID TEI tree, a DoclingDocument dict and stage 0's
inventory record for the same file. Nothing here imports GROBID or Docling's runtime — the
adapters are pure parsers once the artifact exists (design referee M9), so this module runs on a
laptop with neither installed.

What it does, in the order the design gives:

1. **One frame.** Both tools measure from the CROPBOX; the canonical frame is the MEDIABOX
   (§7.1). Every box is put through its adapter's ``to_mediabox`` with frames read by the ONE
   frame reader, :func:`litkb.extract.inventory.page_frames`. A page the adapters refuse
   (rotated **and** cropped) keeps ``frame="cropbox"`` and is EXCLUDED from matching rather than
   matched in the wrong frame — :data:`SKIPPED_ROTATED` counts them.
2. **Match** by page and box IoU, one-to-one, greedy from the highest IoU down.
3. **Choose**, per field, with the rule §7.1 states: the native text layer wins the TEXT (OCR only
   where stage 0's routing says the page has no native layer), Docling wins ORDER and TABLE
   STRUCTURE, GROBID wins REFERENCES. Every choice is recorded per field in ``extractor``.
4. **Keep disagreements.** Where the two tools conflict — a different kind for the same region, or
   text that does not agree — the conflict is written down as a row and BOTH readings are kept.
   Nothing is silently resolved; §7 says a disputed region is stage 8's problem, not stage 5's.

THRESHOLDS ARE PROVISIONAL. §14 requires gold authored by a referee and committed before the
measurement; no such gold exists for reading order or coverage (the P4 merge report records that
as unverified). :data:`IOU_MATCH`, :data:`IOU_TOUCH`, :data:`TEXT_AGREE` and
:data:`COVERAGE_FLOOR` are therefore **author-chosen and UNVALIDATED against gold** — they are
pinned by tests so they cannot drift unnoticed, which is a different and weaker thing.
"""
import dataclasses
import difflib
import re

from litkb.textnorm import jsonb_safe

#: U+FFFE, the noncharacter pypdfium2 emits at a line-break hyphen in some native layers
#: (measured on Alwan_1988 p3: 24 of them on that page alone, "detect any spe￾cial causes").
#: It is REMOVED, not turned into "-": the native slice already carries the two halves of the word
#: adjacent, so removing it gives "special" — the word as printed — while a hyphen would give
#: "spe-cial", which no quote in the gold or in any later stage can be verified against.
HYPHEN_NONCHAR = "￾"

#: IoU at or above which two tools' boxes are the SAME region. Provisional (see the module
#: docstring): 0.5 is the value at which one box cannot be matched to two disjoint others.
IOU_MATCH = 0.5

#: IoU below IOU_MATCH but at or above this: the boxes touch but do not agree. A partial overlap
#: is a disagreement in its own right — it is how a merged two-column paragraph shows up.
IOU_TOUCH = 0.1

#: difflib ratio at or above which two tools' text for one region counts as the same text.
TEXT_AGREE = 0.90

#: Share of a page's native-layer characters that must land inside some canonical block for the
#: page to pass the coverage gate (§7.1 "coverage metric per file", §14 P5). Provisional.
COVERAGE_FLOOR = 0.80

#: The canonical kinds. Everything either maps into this vocabulary or the block is refused.
KINDS = ("paragraph", "heading", "caption", "footnote", "reference",
         "table", "figure", "equation", "furniture")

#: canonical kind -> the `blocks.type` value migration 0002 admits.
DB_TYPE = {"paragraph": "paragraph", "heading": "heading", "caption": "caption",
           "footnote": "footnote", "reference": "reference", "table": "table",
           "figure": "figure", "equation": "equation", "furniture": "other"}

#: Docling's label -> canonical kind. `title` is a heading: the DB keeps a separate `title` type
#: for the paper's own title, which is the HEADER's business (stage 2), not a body region's.
DOCLING_KIND = {
    "text": "paragraph", "paragraph": "paragraph", "list_item": "paragraph",
    "section_header": "heading", "title": "heading",
    "caption": "caption", "footnote": "footnote",
    "table": "table", "picture": "figure", "figure": "figure",
    "formula": "equation", "code": "paragraph",
    "page_header": "furniture", "page_footer": "furniture", "page_number": "furniture",
}

#: GROBID TEI local name -> canonical kind. `s` (a sentence) is deliberately absent: with
#: segmentSentences=1 every paragraph also emits its sentences, and matching those against
#: Docling's paragraph items would count one region three or four times.
GROBID_KIND = {"p": "paragraph", "head": "heading", "note": "footnote",
               "figure": "figure", "formula": "equation", "title": "heading",
               "biblStruct": "reference"}

#: The TEI elements stage 5 reads as REGIONS. `ref` and `persName` are inline spans inside a
#: paragraph, not regions, and `s` is a sentence — none of the three is a canonical block.
GROBID_REGIONS = ("p", "head", "note", "figure", "formula")

#: The TEI elements the BODY matcher reads. ``figure`` is deliberately absent, for the same
#: reason Docling's pictures and tables are absent from :func:`_docling_regions`: the figure pass
#: below claims that region, and leaving GROBID's ``<figure>`` in here as well entered every
#: figure TWICE — measured 2026-09-15, 24 figure blocks for the 8 figures of ``Benedek_2015``,
#: and 4 ``litkb.figures`` rows for the 2 figures on its p4. GROBID's figure regions are still
#: read: :func:`_grobid_figures` supplies them to the caption match.
GROBID_BODY_REGIONS = tuple(k for k in GROBID_REGIONS if k != "figure")

#: Bumped from "stage5-1" on 2026-09-15, with the referee's four fixes: the NUL/U+FFFE strip,
#: one block per figure, the per-column split and its tie-break all change the ROWS a file
#: produces. `ingest.py`'s identity is (file sha256, pipeline version), so a file already
#: recorded at stage5-1 would otherwise be skipped as already-ingested and keep the old blocks.
PIPELINE_VERSION = "stage5-2"


class ReconcileError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Canonical:
    """One canonical block: the reconciled region, with per-field provenance.

    ``extractor`` is a dict, not a string, because the design's rule chooses different tools for
    different FIELDS of the same region — the native layer's characters with Docling's order and
    GROBID's kind is an ordinary outcome, and a single `extractor` column would have to lie about
    one of them. The DB column keeps the summary (`both`, `docling`, `grobid`) and the dict goes
    to `blocks.section_path`-adjacent JSON on the run.
    """

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str
    reading_order: int
    text: str = ""
    latex: str | None = None
    extractor: dict = dataclasses.field(default_factory=dict)
    confidence: float = 0.5
    source: str = "docling"          # docling | grobid | both
    subkind: str = ""                # the tool label behind `furniture`, kept for the DB type
    element_id: str | None = None
    frame: str = "mediabox"
    text_source: str = "tool"        # native | ocr | tool
    payload: dict = dataclasses.field(default_factory=dict)   # table cells, figure caption, ...
    #: The LAYOUT MODEL's own sequence number for this region (Docling's `order_index`), or the
    #: anchored one derived for a region only GROBID saw. This is what reading order is built
    #: from; see :func:`_assign_order` for why it is carried rather than re-derived.
    tool_order: int = -1
    anchored: bool = False           # True when tool_order was inferred, not read off the tool

    @property
    def bbox(self):
        return (self.x0, self.y0, self.x1, self.y1)

    def db_type(self):
        if self.kind == "furniture":
            return {"page_header": "page_header", "page_footer": "page_footer",
                    "page_number": "page_number"}.get(self.subkind, "other")
        return DB_TYPE[self.kind]


@dataclasses.dataclass(frozen=True)
class Disagreement:
    """A conflict between the two tools, kept rather than resolved (§7 stage 5)."""

    page: int
    kind: str                # kind_conflict | text_conflict | partial_overlap | grobid_only | docling_only
    detail: str
    iou: float | None = None
    grobid_kind: str | None = None
    docling_kind: str | None = None
    grobid_text: str = ""
    docling_text: str = ""
    bbox: tuple | None = None


# ── geometry ───────────────────────────────────────────────────────────────────────────────

def iou(a, b):
    """Intersection over union of two (x0, y0, x1, y1) boxes in ONE frame."""
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def match_by_iou(left, right, threshold=IOU_MATCH, touch=IOU_TOUCH):
    """-> (pairs, left_only, right_only, touching).

    Greedy one-to-one from the highest IoU down, per page. `touching` holds pairs that overlap at
    all (>= `touch`) but not enough to be one region: those are disagreements, not matches, and
    they are the shape a two-column paragraph merged by one tool and split by the other takes.
    """
    scored = []
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            if a.page != b.page:
                continue
            v = iou((a.x0, a.y0, a.x1, a.y1), (b.x0, b.y0, b.x1, b.y1))
            if v >= touch:
                scored.append((v, i, j))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_l, used_r, pairs, touching = set(), set(), [], []
    for v, i, j in scored:
        if i in used_l or j in used_r:
            continue
        used_l.add(i)
        used_r.add(j)
        (pairs if v >= threshold else touching).append((left[i], right[j], v))
    return (pairs,
            [a for i, a in enumerate(left) if i not in used_l],
            [b for j, b in enumerate(right) if j not in used_r],
            touching)


# ── the native text layer (the denominator of coverage, and the preferred text) ─────────────

def native_chars(pdf_path, page_no, frames=None):
    """The page's native text layer: ``{"text": the page's own string, "pts": [(char, x, y, i)]}``.

    ``pts`` holds one entry per NON-SPACE character that has a usable box, positioned in the
    MEDIABOX top-left frame, with ``i`` its index into ``text``. Both are needed, for different
    things: ``pts`` is coverage's denominator (a space is not a character a block can be
    responsible for), and ``text`` is what :func:`native_text_in` slices, because a space has no
    box to test and a join of the ink alone comes back with none of them.

    The conversion is the one :func:`litkb.extract.docling.charbox_union` documents: pypdfium2
    reports (left, bottom, right, top) in the mediabox's BOTTOM-LEFT user space, so y flips
    against the mediabox top and x shifts by the mediabox origin. The point returned is the box's
    CENTRE, which is what decides whether the character lies inside a block.
    """
    import pypdfium2 as pdfium

    from litkb.extract import inventory

    if frames is None:
        frames = inventory.page_frames(pdf_path)
    media = frames[page_no]["mediabox"]
    out = []
    doc = pdfium.PdfDocument(pdf_path)
    try:
        tp = doc[page_no - 1].get_textpage()
        text = tp.get_text_range()
        for i, ch in enumerate(text):
            if ch.isspace():
                continue
            try:
                cb = tp.get_charbox(i, loose=False)
            except Exception:  # noqa: BLE001 - a glyph with no box is not a frame error
                cb = None
            if cb is not None and (cb[2] - cb[0] <= 0 or cb[3] - cb[1] <= 0):
                cb = None         # the degenerate first-of-run box, see charbox_union
            if cb is None:
                # KEPT, with no position yet. pypdfium2 reports a zero-area box for the first
                # character of a text run, placed at the END of the previous run; dropping such
                # a character outright made native_text_in's slice start one or two characters
                # late ("ntents lists available" for "Contents lists available"). It inherits
                # the next positioned character's point below, which is where it actually sits.
                out.append([ch, None, None, i])
                continue
            cx = ((cb[0] + cb[2]) / 2.0) - media[0]
            cy = media[3] - ((cb[1] + cb[3]) / 2.0)
            out.append([ch, cx, cy, i])
    finally:
        doc.close()
    nx = ny = None
    for rec in reversed(out):
        if rec[1] is None:
            rec[1], rec[2] = nx, ny
        else:
            nx, ny = rec[1], rec[2]
    return {"text": text, "pts": [tuple(r) for r in out if r[1] is not None]}


def _in_box(x, y, b, tol=1.0):
    return (b[0] - tol) <= x <= (b[2] + tol) and (b[1] - tol) <= y <= (b[3] + tol)


def native_text_in(layer, box, tol=1.0):
    """The native layer's text inside `box` — a SLICE of the page's own string.

    Not a join of the characters that fall inside. pypdfium2 reports no usable box for a space,
    so `native_chars` carries only the ink, and joining those gives
    ``"Theoptimismidentityholds"`` — text that no quote can be verified against and that no
    later stage can chunk. Taking the span between the first and last inside-character keeps the
    PDF's own spacing, which is the thing §7.1 means by "the native layer's characters win".
    """
    inside = [i for _c, x, y, i in layer["pts"] if _in_box(x, y, box, tol)]
    if not inside:
        return ""
    return layer["text"][min(inside):max(inside) + 1]


# ── coverage (§7.1 "coverage metric per file", split by stage 0's page class) ────────────────

def coverage(pdf_path, canonical, page_classes, frames=None):
    """-> {page: {"chars": n, "covered": n, "share": float|None, "page_class": str}}.

    ``share`` is **None**, never 0.0 and never 1.0, on a page whose native layer holds no
    characters: an image-only scan has no denominator, and reporting 100 % there would say the
    reconciliation covered a page it never read. N/A is the honest value.
    """
    from litkb.extract import inventory

    if frames is None:
        frames = inventory.page_frames(pdf_path)
    by_page = {}
    for c in canonical:
        by_page.setdefault(c.page, []).append(c.bbox)
    out = {}
    for page in sorted(frames):
        layer = native_chars(pdf_path, page, frames)
        pts = layer["pts"]
        boxes = by_page.get(page, [])
        covered = sum(1 for _c, x, y, _i in pts if any(_in_box(x, y, b) for b in boxes))
        out[page] = {
            "chars": len(pts), "covered": covered,
            "share": (covered / len(pts)) if pts else None,
            "page_class": page_classes.get(page, "unknown"),
        }
    return out


def coverage_by_page_type(cov):
    """-> {page_class: {"pages": n, "chars": n, "covered": n, "share": float|None}}."""
    agg = {}
    for rec in cov.values():
        a = agg.setdefault(rec["page_class"], {"pages": 0, "chars": 0, "covered": 0})
        a["pages"] += 1
        a["chars"] += rec["chars"]
        a["covered"] += rec["covered"]
    for a in agg.values():
        a["share"] = (a["covered"] / a["chars"]) if a["chars"] else None
    return agg


def coverage_failures(cov, floor=COVERAGE_FLOOR):
    """Pages with a native layer whose covered share is below the floor. The gate's own row."""
    return [(p, r["share"]) for p, r in sorted(cov.items())
            if r["share"] is not None and r["share"] < floor]


# ── reading order ───────────────────────────────────────────────────────────────────────────

def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def text_ratio(a, b):
    """difflib's ratio of two tools' text for one region, whitespace-collapsed and cased down."""
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def text_agrees(a, b):
    """Do the two tools' readings of one region count as the SAME text? The :data:`TEXT_AGREE`
    decision, in one place so a test can sit on the threshold rather than around it."""
    return text_ratio(a, b) >= TEXT_AGREE


def order_violations(canonical, snippets):
    """[(i, snippet)] for every snippet that does not appear in increasing reading order.

    The interleave kill (§14 P4): a column extraction that reads left-column line 1, right-column
    line 1, left-column line 2 … puts the snippets out of order and this returns them. A snippet
    that is not found at all is a violation too — a reading order that lost the text is not a
    reading order that kept it.
    """
    order = []
    for snip in snippets:
        want = _norm(snip)
        hit = next((c.reading_order for c in canonical if want and want in _norm(c.text)), None)
        order.append(hit)
    bad, last = [], -1
    for i, (hit, snip) in enumerate(zip(order, snippets)):
        if hit is None or hit < last:
            bad.append((i, snip))
        else:
            last = hit
    return bad


# ── the reconciliation itself ───────────────────────────────────────────────────────────────

def union_boxes(blocks_in):
    """One box per ELEMENT per page, from the per-line boxes both tools emit.

    Measured 2026-09-15, and the reason this function exists: GROBID gives a ``<p>`` one box per
    LINE (``box_index``/``box_count``), and Docling gives an item one ``prov`` per column
    fragment. Taking the first box of each — which is what a naive reader does — matches a
    paragraph's FIRST LINE against the other tool's whole paragraph, and the IoU is then a few
    per cent. On ``Alwan_1988`` that read 8 matched regions out of 176; unioning per element and
    page reads them as the regions they are.

    An element that genuinely spans two pages stays TWO regions, one per page: a box is a box on
    a page, and a union across a page break is not a rectangle on either. **And the same is true
    of a COLUMN break** (referee 2026-09-15 §4(a)): on ``Alwan_1988`` p3 a GROBID ``<p>`` whose
    last two lines fall in the right column unioned into ``[14, 245, 561, 728]`` — the whole page
    width, gutter and rotated margin stamp included — which ``_anchor`` then placed ahead of the
    entire left column, 10 of that page's 66 gold-ordered pairs out of order. Lines on one page
    are therefore split into COLUMNS first, by :func:`_column_groups`.
    """
    groups, cur = [], None
    for b in blocks_in:
        if b.box_index == 0 or cur is None:
            cur = []
            groups.append(cur)
        cur.append(b)
    out = []
    for g in groups:
        by_page = {}
        for b in g:
            by_page.setdefault(b.page, []).append(b)
        for page, bs in by_page.items():
            for col in _column_groups(bs):
                out.append(dataclasses.replace(
                    col[0], page=page, x0=min(b.x0 for b in col), y0=min(b.y0 for b in col),
                    x1=max(b.x1 for b in col), y1=max(b.y1 for b in col),
                    box_index=0, box_count=1))
    return out


def _column_groups(lines):
    """`lines` (one element, one page) partitioned into COLUMNS, in first-line order.

    A column is a connected component of the lines' HORIZONTAL intervals: two lines are in the
    same column when their x-ranges overlap, directly or through another line. The component
    rule, not "no overlap with the line before", is what makes it safe — measured on the same
    Alwan p3 element set, the pairwise rule splits a paragraph at every short last line followed
    by an indented one, and at a stray 4-point superscript fragment, while the component rule
    splits only where NO line bridges the gutter. On that page it makes exactly the one split the
    defect is about.
    """
    parent = list(range(len(lines)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(lines):
        for j in range(i + 1, len(lines)):
            b = lines[j]
            if min(a.x1, b.x1) - max(a.x0, b.x0) > 0:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb
    order, by_root = [], {}
    for i, b in enumerate(lines):
        r = find(i)
        if r not in by_root:
            by_root[r] = []
            order.append(r)
        by_root[r].append(b)
    return [by_root[r] for r in order]


def _grobid_regions(tei):
    from litkb.extract import grobid as G

    return union_boxes(G.body_blocks(tei, kinds=GROBID_BODY_REGIONS))


def _grobid_figures(tei):
    """GROBID's ``<figure>`` regions — for the caption match only, never as body blocks."""
    from litkb.extract import grobid as G

    return union_boxes(G.body_blocks(tei, kinds=("figure",)))


def _docling_regions(doc):
    """Docling's text-bearing and furniture items — NOT its tables or pictures.

    Those two get their own passes below (a cell grid, and a region with a caption), and
    leaving their items in here as well would put the same table on the page twice: once as a
    block with no cells and once as the table.
    """
    from litkb.extract import docling as D

    wanted = set(D.TEXT_LABELS) | set(D.FURNITURE_LABELS)
    return union_boxes([b for b in D.blocks(doc) if b.kind in wanted])


def reconcile(pdf_path, tei=None, doc=None, record=None, ocr_pages=(), frames=None):
    """-> (canonical, disagreements, stats) for ONE file.

    `record` is stage 0's inventory record for the same file (it supplies the per-page class and
    the route); `ocr_pages` names the pages whose text must come from the tool because the page
    has no native layer to prefer. Either tool's artifact may be None — a scan has no TEI at all,
    because GROBID refuses it — and the reconciliation then runs on the one that exists, with
    every block marked single-source and confidence 0.5.
    """
    from litkb.extract import docling as D
    from litkb.extract import grobid as G
    from litkb.extract import inventory as I

    if tei is None and doc is None:
        raise ReconcileError("stage 5 needs at least one tool's artifact")
    if frames is None:
        frames = I.page_frames(pdf_path)

    g_all = G.to_mediabox(_grobid_regions(tei), frames) if tei is not None else []
    d_all = D.to_mediabox(_docling_regions(doc), frames) if doc is not None else []
    # A page the adapters refuse (rotated AND cropped) is left in the cropbox frame. Matching it
    # against the other tool would overlap boxes measured from two different origins, which is
    # exactly the silent error §7.1 refuses; it is dropped and counted instead.
    skipped = [b for b in g_all + d_all if b.frame != "mediabox"]
    g_blocks = [b for b in g_all if b.frame == "mediabox"]
    d_blocks = [b for b in d_all if b.frame == "mediabox"]

    page_classes = {}
    for i, det in enumerate(((record or {}).get("page_detail") or []), 1):
        # stage 0 names the class `scan` in its page_detail records (inventory._page_measure)
        page_classes[i] = det.get("scan", "unknown")

    chars_by_page = {}

    def chars(page):
        if page not in chars_by_page:
            try:
                chars_by_page[page] = native_chars(pdf_path, page, frames)
            except Exception:  # noqa: BLE001 - a page pdfium cannot read has no native layer
                chars_by_page[page] = {"text": "", "pts": []}
        return chars_by_page[page]

    pairs, g_only, d_only, touching = match_by_iou(g_blocks, d_blocks)
    by_page_d = {}
    for b in d_blocks:
        by_page_d.setdefault(b.page, []).append(b)
    canonical, dis = [], []

    def text_for(page, box, tool_text):
        """§7.1: the native layer's characters win, OCR only where the routing says so."""
        if page in set(ocr_pages):
            return tool_text, "ocr"
        native = native_text_in(chars(page), box)
        if len(_norm(native)) >= 0.5 * len(_norm(tool_text or "")) and _norm(native):
            return native, "native"
        return tool_text, "tool"

    def add(page, box, kind, subkind, source, text, tool_text, conf, element_id, extractor,
            payload=None, latex=None, tool_order=-1, anchored=False):
        chosen, how = text_for(page, box, text)
        canonical.append(Canonical(
            page=page, x0=box[0], y0=box[1], x1=box[2], y1=box[3], kind=kind, reading_order=-1,
            text=chosen, latex=latex, extractor=dict(extractor, text=("native-layer" if how == "native"
                                                                      else extractor.get("text", source))),
            confidence=conf, source=source, subkind=subkind, element_id=element_id,
            text_source=how, payload=payload or {}, tool_order=tool_order, anchored=anchored))
        return canonical[-1]

    seen_d = set()
    for gb, db, v in pairs:
        gk = GROBID_KIND.get(gb.kind, "paragraph")
        dk = DOCLING_KIND.get(db.kind, "paragraph")
        seen_d.add(id(db))
        agree = gk == dk
        if not agree:
            dis.append(Disagreement(page=db.page, kind="kind_conflict", iou=v,
                                    grobid_kind=gk, docling_kind=dk,
                                    grobid_text=gb.text, docling_text=db.text,
                                    bbox=(db.x0, db.y0, db.x1, db.y1),
                                    detail=f"GROBID reads {gk}, Docling reads {dk}; Docling's kept, "
                                           "both readings recorded"))
        ratio = text_ratio(gb.text, db.text)
        if not text_agrees(gb.text, db.text):
            dis.append(Disagreement(page=db.page, kind="text_conflict", iou=v,
                                    grobid_kind=gk, docling_kind=dk,
                                    grobid_text=gb.text, docling_text=db.text,
                                    bbox=(db.x0, db.y0, db.x1, db.y1),
                                    detail=f"text agreement {ratio:.2f} < {TEXT_AGREE}"))
        add(db.page, (db.x0, db.y0, db.x1, db.y1), dk,
            db.kind if dk == "furniture" else "", "both", db.text, db.text,
            0.95 if agree and text_agrees(gb.text, db.text) else 0.7, db.element_id,
            {"bbox": "docling", "kind": "docling", "order": "docling",
             "kind_alt": "grobid", "text": "docling"}, tool_order=db.order_index)

    for gb, db, v in touching:
        dis.append(Disagreement(page=db.page, kind="partial_overlap", iou=v,
                                grobid_kind=GROBID_KIND.get(gb.kind), docling_kind=DOCLING_KIND.get(db.kind),
                                grobid_text=gb.text, docling_text=db.text,
                                bbox=(db.x0, db.y0, db.x1, db.y1),
                                detail=f"boxes overlap at IoU {v:.2f}, below {IOU_MATCH}: the two tools "
                                       "region this differently (a split or merged column)"))
        if id(db) not in seen_d:
            seen_d.add(id(db))
            add(db.page, (db.x0, db.y0, db.x1, db.y1), DOCLING_KIND.get(db.kind, "paragraph"),
                db.kind if DOCLING_KIND.get(db.kind) == "furniture" else "", "docling",
                db.text, db.text, 0.5, db.element_id,
                {"bbox": "docling", "kind": "docling", "order": "docling", "text": "docling"},
                tool_order=db.order_index)
        add(gb.page, (gb.x0, gb.y0, gb.x1, gb.y1), GROBID_KIND.get(gb.kind, "paragraph"), "",
            "grobid", gb.text, gb.text, 0.5, gb.element_id,
            {"bbox": "grobid", "kind": "grobid", "order": "anchored-to-docling", "text": "grobid"},
            tool_order=_anchor(gb, by_page_d), anchored=True)

    # A single-tool file (a scan has no TEI at all: GROBID refuses it) has nothing to disagree
    # WITH. Recording "the other tool has no box here" for every block of such a file would fill
    # the table with the absence of a tool, which is a fact about the run, not about a region.
    both_ran = bool(g_blocks) and bool(d_blocks)

    for db in d_only:
        if id(db) in seen_d:
            continue
        if both_ran:
            dis.append(Disagreement(page=db.page, kind="docling_only",
                                    docling_kind=DOCLING_KIND.get(db.kind), docling_text=db.text,
                                    bbox=(db.x0, db.y0, db.x1, db.y1),
                                    detail="Docling regions this, GROBID has no box here"))
        add(db.page, (db.x0, db.y0, db.x1, db.y1), DOCLING_KIND.get(db.kind, "paragraph"),
            db.kind if DOCLING_KIND.get(db.kind) == "furniture" else "", "docling",
            db.text, db.text, 0.6, db.element_id,
            {"bbox": "docling", "kind": "docling", "order": "docling", "text": "docling"},
            tool_order=db.order_index)

    for gb in g_only:
        if both_ran:
            dis.append(Disagreement(page=gb.page, kind="grobid_only",
                                    grobid_kind=GROBID_KIND.get(gb.kind), grobid_text=gb.text,
                                    bbox=(gb.x0, gb.y0, gb.x1, gb.y1),
                                    detail="GROBID regions this, Docling has no box here"))
        add(gb.page, (gb.x0, gb.y0, gb.x1, gb.y1), GROBID_KIND.get(gb.kind, "paragraph"), "",
            "grobid", gb.text, gb.text, 0.6, gb.element_id,
            {"bbox": "grobid", "kind": "grobid", "order": "anchored-to-docling", "text": "grobid"},
            tool_order=_anchor(gb, by_page_d), anchored=True)

    # tables: Docling's cell grid wins outright (§7.1). The block's box is the table's region and
    # the grid travels with it; nothing renders a table to text here.
    tables = D.to_mediabox(D.tables(doc), frames) if doc is not None else []
    for t in tables:
        if t.frame != "mediabox":
            continue
        canonical.append(Canonical(
            page=t.page, x0=t.x0, y0=t.y0, x1=t.x1, y1=t.y1, kind="table", reading_order=-1,
            text="", extractor={"bbox": "docling", "cells": "docling", "order": "docling"},
            confidence=0.8, source="docling", element_id=t.element_id, text_source="tool",
            tool_order=t.order_index,
            payload={"n_rows": t.num_rows, "n_cols": t.num_cols, "caption": t.caption,
                     "cells": [dataclasses.asdict(c) for c in t.cells]}))

    # figures: the region is Docling's, the caption is GROBID's where GROBID has one for that
    # region (§7.1 gives captions to GROBID on path A).
    figures = D.to_mediabox(D.figures(doc), frames) if doc is not None else []
    g_figs = [b for b in (G.to_mediabox(_grobid_figures(tei), frames) if tei is not None else [])
              if b.frame == "mediabox"]
    for f in figures:
        if f.frame != "mediabox":
            continue
        best, best_v = None, 0.0
        for gf in g_figs:
            if gf.page != f.page:
                continue
            v = iou((f.x0, f.y0, f.x1, f.y1), (gf.x0, gf.y0, gf.x1, gf.y1))
            if v > best_v:
                best, best_v = gf, v
        cap = (best.text if best is not None and best_v >= IOU_TOUCH and best.text else f.caption)
        canonical.append(Canonical(
            page=f.page, x0=f.x0, y0=f.y0, x1=f.x1, y1=f.y1, kind="figure", reading_order=-1,
            # The caption is the figure block's TEXT. `figures.description` is §4.4's stage-8
            # vision field, paired with description_model, and writing a caption there would
            # read later as a model's description of the picture.
            text=cap, extractor={"bbox": "docling", "order": "docling",
                                "caption": "grobid" if cap and best is not None and best_v >= IOU_TOUCH
                                else "docling"},
            confidence=0.8, source="both" if best is not None else "docling",
            element_id=f.element_id, text_source="tool", tool_order=f.order_index,
            payload={"caption": cap, "caption_iou": round(best_v, 3)}))

    # EQUATIONS are not a separate pass: Docling's `formula` items are already in
    # _docling_regions, so a formula region reaches `canonical` through the ordinary match with
    # GROBID's `<formula>` and comes out kind="equation" with `latex` None. LaTeX stays EMPTY
    # until the formula stage (§7 stage 4) fills it — putting the region's plain text in a field
    # named `latex` would look like LaTeX and be false.

    # references: GROBID's order and GROBID's parse, appended after the body (§7.1).
    refs = []
    if tei is not None:
        rb = G.to_mediabox(union_boxes(G.blocks(tei, kinds=("biblStruct",))), frames)
        for b in rb:
            if b.frame != "mediabox":
                continue
            refs.append(Canonical(
                page=b.page, x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1, kind="reference",
                reading_order=-1, text=b.text,
                extractor={"bbox": "grobid", "kind": "grobid", "order": "grobid", "text": "grobid"},
                confidence=0.8, source="grobid", element_id=b.element_id, text_source="tool"))

    canonical = _dedupe_figures(canonical)
    canonical = _assign_order(canonical) + _renumber(refs, start=len(canonical))
    canonical, dis = _sanitize(canonical, dis)
    stats = {
        "pipeline_version": PIPELINE_VERSION,
        "grobid_regions": len(g_blocks), "docling_regions": len(d_blocks),
        "matched": len(pairs), "touching": len(touching),
        "grobid_only": len(g_only), "docling_only": len(d_only),
        "skipped_rotated": len(skipped),
        "blocks": len(canonical), "disagreements": len(dis),
        "by_kind": _count(canonical),
    }
    return canonical, dis, stats


def _dedupe_figures(blocks_in):
    """ONE canonical block per real figure (referee 2026-09-15 §4(b)).

    A figure reaches ``canonical`` twice: once as a GROBID ``<figure>`` region through the body
    matcher, and once through the dedicated figure pass that pairs Docling's picture with
    GROBID's caption. ``ingest.py`` writes one ``litkb.figures`` row per figure block, so the
    database held **4 rows for the 2 figures on Benedek_2015 p4** — and 24 figure blocks for the
    file's 8 figures. Two figure blocks on one page whose boxes agree at :data:`IOU_MATCH` are
    ONE figure; the survivor is the richer block (a caption in its payload, then the higher
    confidence, then the earlier one), which is always the figure pass's.

    Only ``figure`` blocks are touched: two paragraphs at the same box are a genuine
    disagreement between the tools and stage 5 does not resolve those.
    """
    figs = [(i, c) for i, c in enumerate(blocks_in) if c.kind == "figure"]
    drop = set()
    for a in range(len(figs)):
        ia, ca = figs[a]
        if ia in drop:
            continue
        for b in range(a + 1, len(figs)):
            ib, cb = figs[b]
            if ib in drop or ca.page != cb.page:
                continue
            if iou(ca.bbox, cb.bbox) < IOU_MATCH:
                continue
            rank = lambda c: (bool((c.payload or {}).get("caption")), c.confidence)  # noqa: E731
            drop.add(ib if rank(ca) >= rank(cb) else ia)
            if ia in drop:
                break
    return [c for i, c in enumerate(blocks_in) if i not in drop]


def _clean(s):
    """One string, safe for the database and for a quote check: no NUL, no U+FFFE.

    THE ONE PLACE (referee 2026-09-15 §4(0) and §4(d)). Docling's own string for a region with
    no usable native layer carries ``\\x00`` — 6 canonical blocks and 10 disagreement rows on
    ``Benedek_2015`` — and Postgres text refuses it, so the whole file's transaction aborted and
    the file landed NOTHING. The NUL strip is :func:`litkb.textnorm.jsonb_safe`, the same helper
    every other litkb string goes through; U+FFFE is removed beside it because it comes from the
    same boundary and would otherwise reach ``blocks.text``.
    """
    return jsonb_safe(s).replace(HYPHEN_NONCHAR, "") if isinstance(s, str) else jsonb_safe(s)


def _sanitize(canonical, dis):
    """Every text field of the reconciliation put through :func:`_clean`, once, at the boundary.

    Blocks (text, latex, payload — which carries table CELL text and a figure's caption) and
    both sides of every disagreement. Nothing downstream re-cleans: this is the boundary the
    design's "one fact, one home" rule names for it.
    """
    canonical = [dataclasses.replace(c, text=_clean(c.text), latex=_clean(c.latex),
                                     payload=_clean(c.payload)) for c in canonical]
    dis = [dataclasses.replace(d, detail=_clean(d.detail), grobid_text=_clean(d.grobid_text),
                               docling_text=_clean(d.docling_text)) for d in dis]
    return canonical, dis


def region_recall(canonical, regions, lead=16):
    """-> (hits, total, missing): per-REGION recall, the referee's coverage metric C.

    ``regions`` is an iterable of ``(label, snippet)``; a region is a HIT when some canonical
    block's text BEGINS at it — its normalised text starts with the normalised snippet, or
    carries it within the first ``lead`` characters (a block that opens with a page number or a
    run-in label still begins at the region). A block that merely CONTAINS the snippet somewhere
    in its middle is not a hit: that is the case the character share already passes.

    **Why this exists beside the character share.** The shipped metric asks whether some block is
    responsible for each character, and canonical blocks OVERLAP: on Alwan_1988 p3 the referee
    removed the whole of gold region 3 — 885 characters — and the covered share did not move by
    one character (1.0000 before, 1.0000 after), because every character of it also lies inside
    two surviving blocks. Per-region recall fell 10/13 -> 9/13 and NAMED the lost region. The
    §14 page gate is this number; the share stays as the catastrophe detector it measurably is.
    """
    regions = list(regions)
    texts = [_norm(c.text) for c in canonical]
    hits, missing = 0, []
    for label, snip in regions:
        want = _norm(snip)
        if want and any(t.startswith(want) or want in t[:len(want) + lead] for t in texts):
            hits += 1
        else:
            missing.append(label)
    return hits, len(regions), missing


def _anchor(block, by_page_d):
    """The Docling order a region only GROBID saw should take.

    The nearest Docling block ABOVE it **in its own column** — horizontal overlap is required,
    which is the whole point. Without it, a left-column block on a two-column page anchors to the
    right column's top block (small ``y0``, high ``order_index``) and is dragged to the wrong
    half of the page.
    """
    best, best_y = -1, None
    for b in by_page_d.get(block.page, []):
        if b.y0 > block.y0 + 1:
            continue
        if min(b.x1, block.x1) - max(b.x0, block.x0) <= 0:
            continue          # a different column: not above this block in reading terms
        if best_y is None or b.y0 > best_y or (b.y0 == best_y and b.order_index > best):
            best, best_y = b.order_index, b.y0
    return best


def _assign_order(blocks_in):
    """Reading order = the LAYOUT MODEL's sequence (§7.1: the layout model wins order).

    Each canonical block already carries the order Docling gave its region (``tool_order``); a
    region only GROBID saw carries the anchored one from :func:`_anchor`. This function only
    SORTS by it and renumbers 0..n-1. It does not re-derive anything.

    **Why it is written this way, measured 2026-09-15.** The first version derived the order here
    instead, taking ``max(order_index)`` over every Docling block on the page with
    ``y0 <= c.y0``. On a two-column page that anchor set contains the RIGHT column's top blocks
    for every left-column block below them, so the sort collapsed to geometry across the gutter —
    precisely the interleaved order §14's kill exists to catch. On ``Benedek_2015`` pp2-3 it put
    **21 of 23** body snippets out of Docling's order. The producer had the defect the checker
    tests for, and no test caught it because the order test ran on hand-built blocks.
    `test_assign_order_keeps_doclings_order_across_two_columns` is the one that would have.
    """
    keyed = [((c.tool_order if c.tool_order >= 0 else 1 << 30), c.anchored, c.page,
              _column_bucket(c.x0), c.y0, c.x0, i, c)
             for i, c in enumerate(blocks_in)]
    keyed.sort(key=lambda t: t[:7])
    return [dataclasses.replace(t[-1], reading_order=i) for i, t in enumerate(keyed)]


#: A column gutter is tens of points wide and a two-column body column is ~240 pt, so a 100 pt
#: bucket on a block's LEFT edge separates the columns and never splits one.
COLUMN_BUCKET_PT = 100.0


def _column_bucket(x0):
    """Which COLUMN a block's left edge is in, coarsely — the tie-break inside :func:`_assign_order`.

    Measured 2026-09-15, the second half of the cross-column defect. Once a GROBID element that
    crosses the gutter is split into per-column boxes, the two fragments carry the SAME
    ``tool_order`` (they match, or anchor to, one Docling region), and the tie was then broken by
    ``y0`` — which puts the RIGHT column's fragment, sitting at the top of the page, ahead of the
    left column's, which is the very inversion the split was made to remove. On Alwan_1988 p3 and
    Benedek_2015 p2 that was the one remaining out-of-order pair on each page. Left before right,
    then top before bottom, is the reading order of a column layout.
    """
    return int(x0 // COLUMN_BUCKET_PT)


def _renumber(blocks_in, start):
    return [dataclasses.replace(c, reading_order=start + i) for i, c in enumerate(blocks_in)]


def _count(blocks_in):
    out = {}
    for b in blocks_in:
        out[b.kind] = out.get(b.kind, 0) + 1
    return dict(sorted(out.items()))

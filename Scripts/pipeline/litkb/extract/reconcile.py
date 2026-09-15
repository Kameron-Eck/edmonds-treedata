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

PIPELINE_VERSION = "stage5-1"


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
    """[(char, x, y)] for every non-space character on the page, in the MEDIABOX top-left frame.

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
                continue
            if cb[2] - cb[0] <= 0 or cb[3] - cb[1] <= 0:
                continue          # the degenerate first-of-run box, see charbox_union
            cx = ((cb[0] + cb[2]) / 2.0) - media[0]
            cy = media[3] - ((cb[1] + cb[3]) / 2.0)
            out.append((ch, cx, cy))
    finally:
        doc.close()
    return out


def _in_box(x, y, b, tol=1.0):
    return (b[0] - tol) <= x <= (b[2] + tol) and (b[1] - tol) <= y <= (b[3] + tol)


def native_text_in(chars, box, tol=1.0):
    """The native layer's characters inside `box`, in the PDF's own order."""
    return "".join(c for c, x, y in chars if _in_box(x, y, box, tol))


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
        chars = native_chars(pdf_path, page, frames)
        boxes = by_page.get(page, [])
        covered = sum(1 for _, x, y in chars if any(_in_box(x, y, b) for b in boxes))
        out[page] = {
            "chars": len(chars), "covered": covered,
            "share": (covered / len(chars)) if chars else None,
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
    a page, and a union across a page break is not a rectangle on either.
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
            out.append(dataclasses.replace(
                bs[0], page=page, x0=min(b.x0 for b in bs), y0=min(b.y0 for b in bs),
                x1=max(b.x1 for b in bs), y1=max(b.y1 for b in bs),
                box_index=0, box_count=1))
    return out


def _grobid_regions(tei):
    from litkb.extract import grobid as G

    return union_boxes(G.body_blocks(tei, kinds=GROBID_REGIONS))


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
                chars_by_page[page] = []
        return chars_by_page[page]

    pairs, g_only, d_only, touching = match_by_iou(g_blocks, d_blocks)
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
            payload=None, latex=None):
        chosen, how = text_for(page, box, text)
        canonical.append(Canonical(
            page=page, x0=box[0], y0=box[1], x1=box[2], y1=box[3], kind=kind, reading_order=-1,
            text=chosen, latex=latex, extractor=dict(extractor, text=("native-layer" if how == "native"
                                                                      else extractor.get("text", source))),
            confidence=conf, source=source, subkind=subkind, element_id=element_id,
            text_source=how, payload=payload or {}))
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
        ratio = difflib.SequenceMatcher(None, _norm(gb.text), _norm(db.text)).ratio()
        if ratio < TEXT_AGREE:
            dis.append(Disagreement(page=db.page, kind="text_conflict", iou=v,
                                    grobid_kind=gk, docling_kind=dk,
                                    grobid_text=gb.text, docling_text=db.text,
                                    bbox=(db.x0, db.y0, db.x1, db.y1),
                                    detail=f"text agreement {ratio:.2f} < {TEXT_AGREE}"))
        add(db.page, (db.x0, db.y0, db.x1, db.y1), dk,
            db.kind if dk == "furniture" else "", "both", db.text, db.text,
            0.95 if agree and ratio >= TEXT_AGREE else 0.7, db.element_id,
            {"bbox": "docling", "kind": "docling", "order": "docling",
             "kind_alt": "grobid", "text": "docling"})

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
                {"bbox": "docling", "kind": "docling", "order": "docling", "text": "docling"})
        add(gb.page, (gb.x0, gb.y0, gb.x1, gb.y1), GROBID_KIND.get(gb.kind, "paragraph"), "",
            "grobid", gb.text, gb.text, 0.5, gb.element_id,
            {"bbox": "grobid", "kind": "grobid", "order": "grobid", "text": "grobid"})

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
            {"bbox": "docling", "kind": "docling", "order": "docling", "text": "docling"})

    for gb in g_only:
        if both_ran:
            dis.append(Disagreement(page=gb.page, kind="grobid_only",
                                    grobid_kind=GROBID_KIND.get(gb.kind), grobid_text=gb.text,
                                    bbox=(gb.x0, gb.y0, gb.x1, gb.y1),
                                    detail="GROBID regions this, Docling has no box here"))
        add(gb.page, (gb.x0, gb.y0, gb.x1, gb.y1), GROBID_KIND.get(gb.kind, "paragraph"), "",
            "grobid", gb.text, gb.text, 0.6, gb.element_id,
            {"bbox": "grobid", "kind": "grobid", "order": "grobid", "text": "grobid"})

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
            payload={"n_rows": t.num_rows, "n_cols": t.num_cols, "caption": t.caption,
                     "cells": [dataclasses.asdict(c) for c in t.cells]}))

    # figures: the region is Docling's, the caption is GROBID's where GROBID has one for that
    # region (§7.1 gives captions to GROBID on path A).
    figures = D.to_mediabox(D.figures(doc), frames) if doc is not None else []
    g_figs = [b for b in g_blocks if b.kind == "figure"]
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
            text="", extractor={"bbox": "docling", "order": "docling",
                                "caption": "grobid" if cap and best is not None and best_v >= IOU_TOUCH
                                else "docling"},
            confidence=0.8, source="both" if best is not None else "docling",
            element_id=f.element_id, text_source="tool",
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

    canonical = _assign_order(canonical, d_blocks) + _renumber(refs, start=len(canonical))
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


def _assign_order(blocks_in, d_blocks):
    """Docling's reading order for the body (§7.1: the layout model wins order).

    Docling's ``order_index`` is the document's own sequence. A block Docling never saw gets the
    order of the nearest Docling block above it on the same page, so a GROBID-only paragraph
    lands where it reads rather than at the end.
    """
    by_page = {}
    for b in d_blocks:
        by_page.setdefault(b.page, []).append(b)
    out = []
    for c in blocks_in:
        anchors = [b for b in by_page.get(c.page, []) if b.y0 <= c.y0 + 1]
        idx = max((b.order_index for b in anchors), default=-1)
        out.append((c.page, idx, c.y0, c.x0, c))
    out.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return [dataclasses.replace(c, reading_order=i) for i, (_, _, _, _, c) in enumerate(out)]


def _renumber(blocks_in, start):
    return [dataclasses.replace(c, reading_order=start + i) for i, c in enumerate(blocks_in)]


def _count(blocks_in):
    out = {}
    for b in blocks_in:
        out[b.kind] = out.get(b.kind, 0) + 1
    return dict(sorted(out.items()))

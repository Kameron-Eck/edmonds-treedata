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
4. **Keep disagreements — as ROWS, not as two blocks.** Where the two tools conflict — a different
   kind for the same region, text that does not agree, one tool merging what the other segmented —
   the conflict is written down as a ``Disagreement`` row carrying both readings, and ONE canonical
   block is emitted. Nothing is silently resolved; §7 says a disputed region is stage 8's problem,
   not stage 5's. Until 2026-09-16 "both readings are kept" meant two BLOCKS, and the final
   referee measured what that costs: 3,120 duplicate-text rows in 205 of 229 files, 6,309 blocks
   that are a substring of another on their own page, a search returning one region twice in a
   ten-row list, and a quote whose character offsets can land in either copy.
   :func:`_merge_regions` is where the one block is chosen and the other reading is written down.

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

#: Share of the SMALLER box that must lie inside the larger for the two to be candidates for ONE
#: canonical region even though their IoU is below :data:`IOU_MATCH` (the final referee's
#: "contained" class, Reports/LITKB_P5_FINAL_REFEREE_2026-09-16.md §4: 6,309 blocks in 224 of 229
#: runs whose text is a proper substring of another block's on the same page). Containment alone
#: is NOT enough — :func:`_merge_regions` also requires the text to agree, because a table cell's
#: box lies inside its table's box and the two are genuinely different regions.
CONTAIN_MATCH = 0.80

#: How many contained-and-agreeing children a block must have before it is read as one tool's
#: OVER-MERGE of a region the other tool segmented (the Pengra p7 case: one GROBID ``<p>`` of
#: 3,392 characters holding the page's two table captions and its body text, each of which is
#: also its own block). Two is the lowest count that cannot be a one-to-one disagreement.
OVERMERGE_CHILDREN = 2

#: Share of the container's normalised characters its children must account for before the
#: container is dropped as an over-merge. Below it the container carries text nothing else does
#: and dropping it would LOSE words, which no de-duplication may do.
OVERMERGE_COVER = 0.60

#: Share of a page's native-layer characters that must land inside some canonical block for the
#: page to pass the coverage gate (§7.1 "coverage metric per file", §14 P5). Provisional.
COVERAGE_FLOOR = 0.80

#: The canonical kinds. Everything either maps into this vocabulary or the block is refused.
#: ``title``, ``author`` and ``affiliation`` are the three the final referee found NEVER assigned
#: (§2: "Only 10 of the 18 block types are ever used"). They are not body regions and no body
#: matcher can produce them — they come from GROBID's ``<teiHeader>``, through
#: :func:`_kind_from_header`, as a re-kinding of the block the body pass already made.
KINDS = ("paragraph", "heading", "caption", "footnote", "reference",
         "table", "figure", "equation", "furniture",
         "title", "author", "affiliation")

#: canonical kind -> the `blocks.type` value migration 0002 admits.
DB_TYPE = {"paragraph": "paragraph", "heading": "heading", "caption": "caption",
           "footnote": "footnote", "reference": "reference", "table": "table",
           "figure": "figure", "equation": "equation", "furniture": "other",
           "title": "title", "author": "author", "affiliation": "affiliation"}

#: Kinds the reconciliation takes from GROBID even when the surviving block is Docling's. §7.1
#: gives GROBID the REFERENCES, and the header kinds exist nowhere else; everything not in here
#: keeps the survivor's own kind, which is Docling's by the same §7.1 rule.
GROBID_KIND_WINS = ("reference", "title", "author", "affiliation")

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
#:
#: Bumped to "stage5-3" on 2026-09-16 with the final referee's canonical-block fixes: ONE block
#: per region (:func:`_merge_regions`), a page fragment's own text rather than its element's
#: (:func:`reconcile`'s ``text_for``), and the three header kinds. Every one of those changes the
#: rows a file produces, so the identity has to move with them.
PIPELINE_VERSION = "stage5-3"


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
    #: What is KNOWN about ``latex`` — one of ``stable`` / ``contaminated`` / ``unstable`` /
    #: ``degenerate`` / ``unverified``, or None where no formula pass has run at all (migration
    #: 0022 carries the definitions). Stage 5 never sets it: LaTeX arrives from the formula stage
    #: and so does the word for it. None and ``unverified`` are different facts — "no formula
    #: pass has looked at this corpus" against "the pass ran and produced nothing for this
    #: equation" — which is why the column is nullable and the reconciler leaves it alone.
    latex_status: str | None = None
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


def choose_text(native, tool_text, fragment=False):
    """-> (text, ``"native"`` | ``"tool"``). §7.1's rule, in ONE place so a test can sit on it.

    The native layer's characters win where there are enough of them. "Enough" is half the tool's
    own reading: a native slice much SHORTER than what the tool read for the same region means
    the box is in the wrong frame or the page has no usable layer, and falling back to the tool
    is the honest answer there.

    ``fragment`` turns that floor off, and it is the final referee's G7 fix. A block that is one
    FRAGMENT of a multi-page or multi-column element carries its ELEMENT's whole ``text`` (see
    :func:`union_boxes`), so the floor is being applied against the wrong denominator: the
    fragment's honest short slice is compared with every page and every column of the element it
    belongs to, fails, and the block is stored with words that are printed somewhere else. That
    is exactly the G7 finding — 872 characters under ``page_no = 12`` of which the first ~700 are
    printed on page 11 — and, on a page whose columns one tool merged, it is the same string
    stored once per column (Pengra p8: 14 times). For a fragment the native slice IS the answer:
    the characters printed inside this box, on this page, which is what a citation has to name.
    The fallback still applies when the page has no native layer at all.
    """
    n = _norm(native)
    if fragment and n:
        return native, "native"
    if n and len(n) >= 0.5 * len(_norm(tool_text or "")):
        return native, "native"
    return tool_text, "tool"


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


def _letters(s):
    """Lower-cased alphanumerics only — the ONE comparison that survives a TEI's own spacing.

    ``"".join(el.itertext())`` over ``<persName><forename>Bruce</forename><forename
    type="middle">W</forename><surname>Pengra</surname></persName>`` is ``BruceWPengra``: the
    element boundaries carry no whitespace, so GROBID's reading of a name has no spaces and the
    page's has both spaces and an initial's full stop. Measured on Pengra_2020 and Ploton_2020,
    2026-09-16 — under a whitespace-collapsing comparison the author line matched NOTHING and the
    ``author`` kind was never assigned on any document.
    """
    return re.sub(r"[^0-9a-z]+", "", (s or "").lower())


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

    **The output's ``box_index``/``box_count`` are the FRAGMENT's index and the element's fragment
    COUNT**, not the line's (a line index is meaningless once the lines are unioned). They are the
    only record that a region is a piece of a larger element, and the caller needs it for two
    things the final referee measured, both of which come from one mistake — a fragment inherits
    ``col[0]``'s ``text``, which is the WHOLE element's:

      * a paragraph crossing a PAGE break was stored under one page number with both pages' words
        in it (§2, G7: 872 characters under ``page_no = 12``, the first ~700 printed on page 11),
        so a quote's citation page could be wrong by one;
      * an element crossing many COLUMNS stored its whole text once per column (Pengra p8: one
        ``<p>`` split across 14 table columns, all 14 carrying the same 600 characters), which is
        the largest single contributor to §4's 3,120 duplicate-text rows.

    :func:`reconcile` reads ``box_count > 1`` and takes the fragment's own native-layer slice.
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
        frags = []
        for page, bs in by_page.items():
            for col in _column_groups(bs):
                frags.append(dataclasses.replace(
                    col[0], page=page, x0=min(b.x0 for b in col), y0=min(b.y0 for b in col),
                    x1=max(b.x1 for b in col), y1=max(b.y1 for b in col)))
        out.extend(dataclasses.replace(f, box_index=i, box_count=len(frags))
                   for i, f in enumerate(frags))
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
    # Which blocks are FRAGMENTS of one element, and what page the neighbouring fragment is on.
    # Computed on the unfiltered lists and keyed by object identity, which is what `reconcile`
    # carries everywhere else (`seen_d` is keyed the same way): the list comprehensions below
    # filter the same objects, they do not copy them.
    frag = _fragment_info(g_all)
    frag.update(_fragment_info(d_all))
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

    def text_for(page, box, tool_text, fragment=False):
        """§7.1: the native layer's characters win, OCR only where the routing says so."""
        if page in set(ocr_pages):
            return tool_text, "ocr"
        return choose_text(native_text_in(chars(page), box), tool_text, fragment)

    def add(page, box, kind, subkind, source, text, tool_text, conf, element_id, extractor,
            payload=None, latex=None, tool_order=-1, anchored=False, of=None):
        info = frag.get(id(of)) if of is not None else None
        chosen, how = text_for(page, box, text, fragment=bool(info))
        if info:
            # `continues_from` / `continues_to` name the PAGE the neighbouring fragment of this
            # element is printed on, so a reader holding a quote that runs off the bottom of the
            # page can find the rest of it without re-deriving the split.
            extractor = dict(extractor, fragment={"index": info["index"], "count": info["count"]})
            if info["prev_page"] is not None:
                extractor["continues_from"] = {"page": info["prev_page"]}
            if info["next_page"] is not None:
                extractor["continues_to"] = {"page": info["next_page"]}
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
             "kind_alt": "grobid", "text": "docling"}, tool_order=db.order_index, of=db)

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
                tool_order=db.order_index, of=db)
        add(gb.page, (gb.x0, gb.y0, gb.x1, gb.y1), GROBID_KIND.get(gb.kind, "paragraph"), "",
            "grobid", gb.text, gb.text, 0.5, gb.element_id,
            {"bbox": "grobid", "kind": "grobid", "order": "anchored-to-docling", "text": "grobid"},
            tool_order=_anchor(gb, by_page_d), anchored=True, of=gb)

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
            tool_order=db.order_index, of=db)

    for gb in g_only:
        if both_ran:
            dis.append(Disagreement(page=gb.page, kind="grobid_only",
                                    grobid_kind=GROBID_KIND.get(gb.kind), grobid_text=gb.text,
                                    bbox=(gb.x0, gb.y0, gb.x1, gb.y1),
                                    detail="GROBID regions this, Docling has no box here"))
        add(gb.page, (gb.x0, gb.y0, gb.x1, gb.y1), GROBID_KIND.get(gb.kind, "paragraph"), "",
            "grobid", gb.text, gb.text, 0.6, gb.element_id,
            {"bbox": "grobid", "kind": "grobid", "order": "anchored-to-docling", "text": "grobid"},
            tool_order=_anchor(gb, by_page_d), anchored=True, of=gb)

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
    canonical, refs, merged = _merge_regions(canonical, refs, dis)
    canonical, captioned = _caption_once(canonical)
    canonical, headered = _kind_from_header(canonical, tei, frames)
    canonical = _assign_order(canonical) + _renumber(refs, start=len(canonical))
    canonical, dis = _sanitize(canonical, dis)
    stats = {
        "pipeline_version": PIPELINE_VERSION,
        "grobid_regions": len(g_blocks), "docling_regions": len(d_blocks),
        "matched": len(pairs), "touching": len(touching),
        "grobid_only": len(g_only), "docling_only": len(d_only),
        "skipped_rotated": len(skipped),
        "merged_regions": merged["merged"], "dropped_overmerges": merged["overmerge"],
        "references_merged_into_body": merged["reference_kind"],
        "captions_unduplicated": captioned, "header_kinds": headered,
        "blocks": len(canonical), "disagreements": len(dis),
        "by_kind": _count(canonical),
    }
    return canonical, dis, stats


def _fragment_info(blocks_in):
    """``{id(block): {"index", "count", "prev_page", "next_page"}}`` for multi-fragment elements.

    :func:`union_boxes` leaves an element's fragments CONTIGUOUS in its output, numbered
    ``box_index`` 0..n-1 with ``box_count`` n, so a run is read back by scanning for the zeros.
    ``prev_page`` / ``next_page`` are set only when the neighbouring fragment is on a DIFFERENT
    page — a column break inside one page is a fragment too, but it is not a continuation a
    citation has to care about.
    """
    info = {}

    def flush(run):
        if len(run) < 2:
            return
        pages = [b.page for b in run]
        for i, b in enumerate(run):
            prev_p = pages[i - 1] if i > 0 and pages[i - 1] != b.page else None
            next_p = pages[i + 1] if i + 1 < len(pages) and pages[i + 1] != b.page else None
            info[id(b)] = {"index": i, "count": len(run),
                           "prev_page": prev_p, "next_page": next_p}

    run = []
    for b in blocks_in:
        if b.box_index == 0 and run:
            flush(run)
            run = []
        run.append(b)
    flush(run)
    return info


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


def containment(a, b):
    """Share of the SMALLER of two boxes that lies inside the other. 1.0 when one encloses it.

    IoU cannot see this relationship at all: a 100-point caption inside a 3,300-point paragraph
    has an IoU of 0.03 and a containment of 1.0, and it is the second number that says the two
    tools are describing one region of the page differently.
    """
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    small = min(area_a, area_b)
    return inter / small if small > 0 else 0.0


def band_containment(small, big):
    """Share of ``small``'s HEIGHT that lies in ``big``'s vertical band, 0 if they never meet in x.

    Area containment is the wrong measure for one tool's over-merge of another's segmentation,
    and Conway_2022 p4 is why, measured 2026-09-16: GROBID's ``<p>`` unions its own lines into
    ``[78.0, 321.0, 413.6, 755.2]`` — 336 points wide because its widest line is — while the
    Docling paragraphs whose words it holds run to x = 569. Only 30 % of each child's AREA is
    inside, so an area test reads them as unrelated; they are stacked one under another in the
    same band of the same page, which is what "this block holds those blocks" means on a page.
    """
    if min(small[2], big[2]) - max(small[0], big[0]) <= 0:
        return 0.0
    h = small[3] - small[1]
    if h <= 0:
        return 0.0
    return max(0.0, min(small[3], big[3]) - max(small[1], big[1])) / h


def _covered_share(whole, parts):
    """Share of ``whole``'s characters covered by the parts that occur in it, spans unioned.

    Summing the parts' lengths would double-count two children that overlap, and a container is
    only dropped when its children really do account for it.
    """
    spans = []
    for p in parts:
        i = whole.find(p)
        if i >= 0:
            spans.append((i, i + len(p)))
    spans.sort()
    total, end = 0, -1
    for s, e in spans:
        if s > end:
            total += e - s
            end = e
        elif e > end:
            total += e - end
            end = e
    return total / len(whole) if whole else 0.0


def _text_same(a, b):
    """Do two readings of one region carry the SAME words? The merge's text test.

    Not :func:`text_agrees` alone. difflib's ratio between a 130-character caption and the
    3,300-character paragraph that swallowed it is near zero however completely one contains the
    other, and containment is the relationship the final referee's 6,309 blocks are in. So the
    shorter reading being a substring of the longer counts, and the ratio is kept for the case
    the substring test cannot see: two readings of one region that differ in a glyph.
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return not na and not nb
    lo, hi = (na, nb) if len(na) <= len(nb) else (nb, na)
    return lo in hi or text_agrees(na, nb)


#: Structural kinds carry a payload nothing else can rebuild — a table's cell grid, a figure's
#: caption pairing — so they survive a merge against a prose reading of the same rectangle
#: whatever the text says. Everything else ranks by the fields below it in :func:`_survivor_key`.
_STRUCTURE_RANK = {"table": 4, "figure": 3, "equation": 2}


def _survivor_key(c, i):
    """Which of two readings of ONE region becomes the canonical block (higher wins).

    In §7.1's order: structure first (a grid cannot be rebuilt from prose), then the native text
    layer over a tool's own string, then a region both tools saw, then Docling's box — §7.1 gives
    Docling the bbox and the order — then the longer reading, then the earlier block, so the
    choice is deterministic for a fixed artifact pair.
    """
    return (_STRUCTURE_RANK.get(c.kind, 0),
            1 if c.text_source == "native" else 0,
            1 if c.source == "both" else 0,
            1 if c.extractor.get("bbox") == "docling" else 0,
            len(_norm(c.text)),
            -i)


def _merge_regions(canonical, refs, dis):
    """ONE canonical block per region — the final referee's §4, and blocker 2 of its §11.

    -> ``(canonical, leftover_refs, stats)``. Disagreement rows are APPENDED to ``dis``: nothing
    is thrown away, which is what makes this a merge rather than a deletion. §7 says a disputed
    region is stage 8's problem; it never said the dispute has to be stored as two blocks that a
    search then returns twice and a quote's character offsets can land in either of.

    The referee measured three shapes of one defect, and this function answers each:

      * **exact** — 63 groups at an identical ``(page, bbox)``, mostly two Docling items over one
        chart. IoU 1.0, so the pairwise pass below takes them.
      * **near** — 1,635 groups of equal normalised text on one page. Most were the fragment bug
        :func:`union_boxes` now records and ``text_for`` now fixes; what survives that is a real
        pair of readings and the pairwise pass takes it.
      * **contained** — 6,309 blocks that are a proper substring of another on the same page.
        Two different relationships wear that shape, and they need opposite answers: one tool
        SEGMENTING a region the other MERGED (Pengra p7's 3,392-character GROBID ``<p>`` holding
        the page's captions and body) is an over-merge and the container goes, because §7.1 gives
        Docling the segmentation; a single small reading inside a single large one is one region
        seen twice and the richer reading stays.

    ``refs`` — GROBID's parsed bibliography — takes part in the merge and is the reason the
    ``reference`` kind starts appearing on blocks a reader can actually find. Before this, a
    printed reference entry was stored TWICE (§2: Conway p11 held 29 ``paragraph`` blocks at
    reading order 200-228 and 28 ``reference`` blocks at 418-445), and the copy a search returned
    first was the one typed ``paragraph``, because a region only GROBID saw sorts at ``1 << 30``.
    A ``biblStruct`` that lands on a body block now RE-KINDS it: the surviving block keeps the
    native text, the real box and the real reading order, and carries GROBID's kind.
    """
    marked = [(c, False) for c in canonical] + [(c, True) for c in (refs or [])]
    blocks = [c for c, _r in marked]
    is_ref = [r for _c, r in marked]
    by_page = {}
    for i, c in enumerate(blocks):
        by_page.setdefault(c.page, []).append(i)

    drop = _overmerge_drop(blocks, by_page, dis)
    keep = [i for i in range(len(blocks)) if i not in drop]
    blocks, merged, upgraded = _pairwise_merge(blocks, keep, by_page, dis)
    survivors = [i for i in keep if i not in merged]
    return ([blocks[i] for i in survivors if not is_ref[i]],
            [blocks[i] for i in survivors if is_ref[i]],
            {"merged": len(merged), "overmerge": len(drop), "reference_kind": upgraded})


def _overmerge_drop(blocks, by_page, dis):
    """Indices of blocks that are one tool's MERGE of a region the other tool segmented.

    A block is an over-merge when at least :data:`OVERMERGE_CHILDREN` other blocks on its page
    are boxed inside it (at :data:`CONTAIN_MATCH`) with their text a substring of its own, and
    those children together account for at least :data:`OVERMERGE_COVER` of its characters. Both
    conditions are needed: the count alone would drop a section that happens to enclose two
    captions, and the coverage alone would drop a paragraph one of whose sentences is repeated.
    """
    drop = set()
    for page, idxs in by_page.items():
        for i in idxs:
            big = blocks[i]
            nb = _norm(big.text)
            if len(nb) < 200:
                continue
            kids = []
            for j in idxs:
                if j == i:
                    continue
                ns = _norm(blocks[j].text)
                if len(ns) < 20 or len(ns) >= len(nb):
                    continue
                if ns not in nb:
                    continue
                if max(containment(blocks[j].bbox, big.bbox),
                       band_containment(blocks[j].bbox, big.bbox)) < CONTAIN_MATCH:
                    continue
                kids.append(ns)
            if len(kids) < OVERMERGE_CHILDREN:
                continue
            share = _covered_share(nb, kids)
            if share < OVERMERGE_COVER:
                continue
            drop.add(i)
            dis.append(Disagreement(
                page=big.page, kind="superset_region", bbox=big.bbox,
                grobid_kind=big.kind if big.source == "grobid" else None,
                docling_kind=big.kind if big.source != "grobid" else None,
                grobid_text=big.text if big.source == "grobid" else "",
                docling_text=big.text if big.source != "grobid" else "",
                detail=f"{big.source} merges a region the other tool segments: {len(kids)} blocks "
                       f"on this page are boxed inside it and cover {share:.2f} of its text; the "
                       f"segmented blocks are canonical and this reading is kept here "
                       f"(element {big.element_id or 'unnamed'})"))
    return drop


def _pairwise_merge(blocks, keep, by_page, dis):
    """-> (blocks, merged_away, kind_upgrades). One survivor per group of readings of one region.

    Groups are connected components of "these two are one region": IoU at :data:`IOU_MATCH`, or
    one box :data:`CONTAIN_MATCH` inside the other with :func:`_text_same`. The survivor is
    :func:`_survivor_key`'s maximum, and **a reading is only dropped when the survivor's text
    still carries its words** — a merge that loses characters is a worse defect than the
    duplicate it repairs, so a group whose survivor does not cover a member keeps that member and
    records the pair instead.
    """
    kept = set(keep)
    parent = {i: i for i in kept}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for page, idxs in by_page.items():
        here = [i for i in idxs if i in kept]
        for a in range(len(here)):
            i = here[a]
            for b in range(a + 1, len(here)):
                j = here[b]
                ci, cj = blocks[i], blocks[j]
                v = iou(ci.bbox, cj.bbox)
                same = v >= IOU_MATCH
                if not same and containment(ci.bbox, cj.bbox) >= CONTAIN_MATCH:
                    same = _norm(ci.text) and _norm(cj.text) and _text_same(ci.text, cj.text)
                if not same:
                    continue
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups = {}
    for i in kept:
        groups.setdefault(find(i), []).append(i)

    out = list(blocks)
    merged, upgrades = set(), 0
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort()
        win = max(members, key=lambda i: _survivor_key(blocks[i], i))
        survivor, kind = blocks[win], blocks[win].kind
        alt = []
        for i in members:
            if i == win:
                continue
            other = blocks[i]
            # THE NO-TEXT-LOSS GUARD, and the one place it does NOT apply. Two boxes that agree
            # at IOU_MATCH are the SAME RECTANGLE, and §7's rule for that case is already settled
            # and already shipped: the matched-pair branch above keeps Docling's reading and
            # records GROBID's. A reference is the case that proves it — GROBID's re-serialised
            # `biblStruct` string ("Factors influencing long-term street tree survival in
            # Milwaukee AKoese…") is a DIFFERENT RENDERING of the printed entry, never a
            # substring of it, so a text test would refuse the very merge the referee's §2 asks
            # for. Below IOU_MATCH the boxes are only nested, and there the guard stands: a
            # container may carry words its child does not.
            if iou(survivor.bbox, other.bbox) < IOU_MATCH and (
                    not _text_same(survivor.text, other.text)
                    or len(_norm(other.text)) > len(_norm(survivor.text))):
                dis.append(Disagreement(
                    page=other.page, kind="partial_overlap", bbox=other.bbox,
                    iou=round(iou(survivor.bbox, other.bbox), 3),
                    grobid_text=other.text if other.source == "grobid" else "",
                    docling_text=other.text if other.source != "grobid" else "",
                    detail="one region, two readings, and the survivor does not carry this one's "
                           "words: both are kept rather than losing text to a de-duplication"))
                continue
            merged.add(i)
            alt.append(other)
            if other.kind in GROBID_KIND_WINS and other.extractor.get("kind") == "grobid":
                kind = other.kind
                upgrades += 1
        if not alt:
            continue
        ex = dict(survivor.extractor)
        # ``element_id`` is not decoration. Stage 6 stores a parsed reference with the BLOCK it
        # came from (``litkb.references.block_id``), and after the merge the block a `biblStruct`
        # became is Docling's, carrying Docling's `#/texts/N`. Without GROBID's own id recorded
        # here there is no way back from a TEI element to the block that now holds it, and a
        # stage-6 re-run against this pipeline version would have nothing to join on.
        ex["merged"] = [{"kind": o.kind, "source": o.source, "bbox": [round(v, 2) for v in o.bbox],
                         "text_source": o.text_source, "element_id": o.element_id} for o in alt]
        if kind != survivor.kind:
            ex["kind"] = "grobid"
            ex["kind_alt"] = survivor.extractor.get("kind", survivor.source)
        out[win] = dataclasses.replace(survivor, kind=kind, extractor=ex,
                                       source="both" if survivor.source != "both"
                                              and any(o.source != survivor.source for o in alt)
                                       else survivor.source)
        for o in alt:
            dis.append(Disagreement(
                page=o.page, kind="duplicate_region", bbox=o.bbox,
                iou=round(iou(survivor.bbox, o.bbox), 3),
                grobid_kind=o.kind if o.source == "grobid" else survivor.kind,
                docling_kind=o.kind if o.source != "grobid" else survivor.kind,
                grobid_text=o.text if o.source == "grobid" else survivor.text,
                docling_text=o.text if o.source != "grobid" else survivor.text,
                detail="one region described twice; ONE canonical block is emitted and this "
                       "reading is kept here (design §7: a disputed region is not resolved, it "
                       "is recorded)"))
    return out, merged, upgrades


def _caption_once(blocks_in):
    """A caption's words live in ONE block. -> (blocks, n).

    ``reconcile`` puts the caption in the figure block's ``text`` (that is what a figure block
    says), and Docling also emits the caption as its own ``caption`` item, so the same sentence
    is stored twice with no geometric relationship between the two boxes at all — 219 of the
    final referee's duplicate groups (§4), and invisible to :func:`_merge_regions`, which is a
    geometry pass. The figure keeps the caption in its ``payload``, where the pairing lives; the
    ``caption`` block keeps the text, which is where a search should find it.
    """
    n = 0
    caps = {}
    for c in blocks_in:
        if c.kind == "caption" and _norm(c.text):
            caps.setdefault(c.page, []).append(_norm(c.text))
    out = []
    for c in blocks_in:
        t = _norm(c.text)
        if c.kind == "figure" and t and any(t in o or o in t for o in caps.get(c.page, [])):
            payload = dict(c.payload or {})
            payload.setdefault("caption", c.text)
            payload["caption_stored_on"] = "caption block"
            out.append(dataclasses.replace(c, text="", payload=payload))
            n += 1
            continue
        out.append(c)
    return out, n


def _kind_from_header(blocks_in, tei, frames):
    """The three kinds nothing else can assign: ``title``, ``author``, ``affiliation``. -> (blocks, n).

    The final referee's §2: "Only 10 of the 18 block types are ever used… On the Ploton title page
    the paper's title is a ``heading``, its author list and its affiliation footer are both
    ``paragraph``." No BODY matcher can do better — none of the three is a body region, and
    Docling's vocabulary has no word for any of them. GROBID's ``<teiHeader>`` does, and two of
    the three are coordinate-bearing (``title`` and ``persName`` are in
    :data:`litkb.extract.grobid.COORD_ELEMENTS`), so those two are assigned by GEOMETRY and
    checked against the text. ``<affiliation>`` carries no coordinates at all, so it is assigned
    by TEXT ONLY — the block must hold two of the header's own institution strings — and that is
    a weaker rule, stated here rather than hidden: a document whose affiliations GROBID did not
    parse simply keeps ``paragraph``, which is what it has today.
    """
    if tei is None:
        return blocks_in, 0
    from litkb.extract import grobid as G

    try:
        head = G.header_regions(tei)
    except Exception:  # noqa: BLE001 - a TEI with no parseable header is not an error here
        return blocks_in, 0
    # The header's boxes come back in GROBID's cropbox frame, like every other box this adapter
    # returns; a page the adapter refuses keeps frame="cropbox" and is dropped, exactly as the
    # body pass drops it, rather than compared across two origins.
    titles = [b for b in G.to_mediabox(head["title"], frames) if b.frame == "mediabox"]
    authors = [b for b in G.to_mediabox(head["author"], frames) if b.frame == "mediabox"]
    out, n = list(blocks_in), 0

    def claim(i, kind, how):
        nonlocal n
        c = out[i]
        if c.kind in ("table", "figure", "equation", "furniture") or c.kind == kind:
            return False
        out[i] = dataclasses.replace(
            c, kind=kind, extractor=dict(c.extractor, kind="grobid", kind_alt=c.kind,
                                         kind_basis=f"teiHeader/{how}"))
        n += 1
        return True

    claimed = set()
    for t in titles:
        best, best_v = None, 0.0
        for i, c in enumerate(out):
            if i in claimed or c.page != t.page:
                continue
            v = max(iou(c.bbox, (t.x0, t.y0, t.x1, t.y1)),
                    containment((t.x0, t.y0, t.x1, t.y1), c.bbox))
            if v > best_v and _text_same(c.text, t.text):
                best, best_v = i, v
        if best is not None and best_v >= CONTAIN_MATCH and claim(best, "title", "titleStmt/title"):
            claimed.add(best)

    for p in authors:
        for i, c in enumerate(out):
            if i in claimed or c.page != p.page or len(_norm(c.text)) > 800:
                continue
            if containment((p.x0, p.y0, p.x1, p.y1), c.bbox) < CONTAIN_MATCH:
                continue
            if len(_letters(p.text)) < 4 or _letters(p.text) not in _letters(c.text):
                continue
            if claim(i, "author", "sourceDesc/persName"):
                claimed.add(i)
            break

    orgs = [_norm(o) for o in head.get("affiliation", []) if len(_norm(o)) >= 5]
    if orgs:
        for i, c in enumerate(out):
            if i in claimed or c.page != 1 or not (0 < len(_norm(c.text)) <= 2000):
                continue
            t = _norm(c.text)
            if len({o for o in orgs if o in t}) < 2:
                continue
            if claim(i, "affiliation", "sourceDesc/affiliation"):
                claimed.add(i)
    return out, n


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

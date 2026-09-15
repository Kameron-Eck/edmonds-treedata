"""Stage 0 — Inventory (design §7, §7.1, §12).

What it is for. Every later stage reads this one: stage 1 needs the page frames, stage 3
needs to know which pages have no text to read, stage 5 needs one coordinate frame to
reconcile into, and the P5 projection needs the page count and the OCR page count, which
are the two numbers the backlog is priced in. Stage 0 measures the PDF and decides nothing
else.

What it writes, per file, as one JSONL record:

* identity — ``sha256``, ``md5``, ``bytes``, ``path``;
* the document — ``pages``, the PDF ``/Info`` dictionary (NUL-stripped through
  :func:`litkb.textnorm.jsonb_safe`, because Acrobat Capture files carry NULs in their
  metadata and Postgres ``jsonb`` refuses ``\\u0000`` — Bell 1977, D-nul), ``producer``,
  ``creator``, ``pdf_version``, ``encrypted``;
* per page — ``mediabox``, ``cropbox``, ``rotation``, ``dx``/``dy`` (the §7.1 frame shift),
  ``chars`` (non-whitespace characters in the text layer), ``images``, ``image_frac``, and
  a ``scan`` class;
* the routing decision for the file, and the explicit list of pages that need OCR.

The JSONL is the artifact; **P5's ingest persists it** into the design's ``files`` and
``pages`` tables (§7 stage 0 output column) under the run key below. Nothing here touches
the database, and nothing here writes inside ``Literture\\`` — the corpus is opened
read-only (§6: litkb holds no delete permission there).

Run key (§12.4): ``(sha256, stage=0, tool="pypdfium2@<version>", params_hash)`` where
``params_hash`` is a digest of the thresholds below, so moving a threshold makes a new key
and the sweep re-runs the file instead of silently mixing two definitions.

--------------------------------------------------------------------------------------
The thresholds, and the census they were read off
--------------------------------------------------------------------------------------

MEASURED 2026-09-15 over every PDF under ``D:\\edmonds-pipeline\\Literture`` (241 files,
5,038 pages; 224 files / 4,712 pages excluding ``_quarantine``). The thresholds were
chosen from that census BEFORE the hand-inspection gate was written
(Reports/LITKB_INVENTORY_2026-09-15.md §2).

``CHARS_TRACE = 100`` — non-whitespace characters. The character axis is sharply bimodal
only at zero: 89 pages carry no text at all, exactly one page carries 25 (Reynolds 2000
p14), and the next IMAGE-COVERED page carries 117 (Guo 2019 p6). 100 sits in that gap.
Below it a page's text layer is a stamp or a stray line, not content.

The 111 this paragraph used to name is Pesonen 2026 p20, whose ``image_frac`` is 0.1527 —
a page carrying images, not an image-covered one, so ``CHARS_TRACE`` cannot reclass it and
it never belonged in this gap. Both ends of the gap are now pinned in ``BOUNDARY_PINS``
(``qc/test_litkb_inventory.py``), which is the one home; this sentence points at it.

``CHARS_BODY = 400`` — above it a page carries body text. Among image-covered pages, 594
are above 400 (whole scans re-covered by an OCR text layer, e.g. Lahiri 2003, Besag 1974 —
a complete layer, so nothing to re-OCR) and only 14 fall in 100..400.

``IMAGE_COVER = 0.25`` — image area ÷ cropbox area. Every page in the corpus with no text
at all has image coverage ≥ 0.2764, and that floor is a SINGLE page: Ogata 1998 p24, a
half-filled references page whose scan is cut into 18 image strips. The next zero-character
page sits at 0.5069. The margin above the threshold is therefore 10.6 %, not a comfortable
gap (Reports/LITKB_INVENTORY_REFEREE_2026-09-15.md §3, §7). A page below this has no
full-page raster, so OCR has nothing to read and the native layer is all there is.

``COVER_MAX_CHARS = 200`` — a page-1 text layer that is boilerplate and nothing else.
Taken from an already-committed measurement, not invented here:
Reports/LITKB_EDGE_PRE1990_2026-09-14.md P-2, "On IMS–JSTOR 'collaborating with JSTOR'
covers (Hudson, Hwang, Anderson), page 1 has under 200 characters". (P-2's second clause,
"the paper starts on page 2", does NOT hold — see §4 of this stage's report.)

``SCAN_FILE_FRAC = 0.5`` — at or above this share of OCR-needing pages the file is priced
as a scan rather than as a native document with scanned inserts.

--------------------------------------------------------------------------------------
Page classes (descriptive) and file routing (a decision)
--------------------------------------------------------------------------------------

A page class states what the measurement found; it does not on its own decide anything::

    image_frac >= IMAGE_COVER and chars <  CHARS_TRACE   -> "image-only"
    image_frac >= IMAGE_COVER and chars <  CHARS_BODY    -> "partial"
    chars == 0 and image_frac <  IMAGE_COVER             -> "empty"
    otherwise                                            -> "text"

``text`` means "the native text layer is the best source available for this page", NOT
"this page is full of text". A 58-character chapter opener with no raster on it is
``text`` because OCR cannot improve it. A fully OCR-covered scan page is ``text`` for the
same reason: its layer is already complete.

``empty`` is 0 characters and no raster — a blank or vector-only page. The present corpus
contains none; the class exists so that such a page is never mistaken for ``image-only``
and sent to an OCR engine that would return nothing.

Routing is per file, single-valued, and its precedence is fixed::

    unreadable > scan > mixed > cover-sheet > native

``unreadable``  the document will not open (encrypted with a user password, or corrupt).
``scan``        ``len(ocr_pages) / pages >= SCAN_FILE_FRAC``.
``mixed``       some pages need OCR, below that share.
``cover-sheet`` page 1 is a standalone publisher cover page (:func:`is_cover_sheet`) and
                the document starts on page 2; no page needs OCR.
``native``      no page needs OCR.

Because the precedence is single-valued, ``cover_sheet``, ``cover_stamp`` and
``title_page`` are emitted as their own fields on every record, whatever the route says. A
reader that wants "where is the title" reads ``title_page`` (``None`` when no page's text
layer carries it and only OCR will); a reader that wants "what does this file cost" reads
``route`` and ``ocr_pages``. Without that split the scan count and the cover-sheet count
contradict each other.

**Encrypted is not unreadable.** An owner-password-only PDF opens with no password and
extracts normally; ``encrypted`` records the security handler, and only a document that
refuses to open is routed ``unreadable``, with pdfium's own last-error name as the reason.

--------------------------------------------------------------------------------------
What stage 0 does NOT see (referee 2026-09-15, §9 of the phase report)
--------------------------------------------------------------------------------------

Each of these was probed by an independent referee, each was MEASURED to have no live
instance in the present corpus, and each is therefore a limitation to state rather than a
defect to fix. None is guarded by a test that fires, because there is nothing here to fire
on; if a future corpus adds one, the symptom is written out below so it is recognisable.

1. **Invisible text is invisible to the probe.** :func:`classify_page` reads a character
   COUNT. A text layer drawn white-on-white, or placed off the page, counts as ``chars``
   just like ink, so such a page classes ``text`` and routes ``native`` — no OCR, and a
   downstream reader gets a layer no human can see on the render. §9.1's Kingman case is a
   *wrong* layer; this is an *unrenderable* one, and the probe cannot tell them apart.
   **Measured:** the referee scanned all 5,038 pages with pdfminer for characters ≥90 %
   white-filled or ≥90 % outside the cropbox. 55 flags, 7 files, and every one inspected
   resolved to a Separation/ICC colour space where ``1.0`` is full ink, or to a mediabox
   with ``y0 = 51``. **Zero real instances.** (Referee §4, kill K1 — DID NOT FIRE.)

2. **A front matter deeper than the detector is not fully skipped.** :func:`is_cover_sheet`
   and :func:`is_cover_stamp` are applied to each LEADING page in turn, so a publisher cover
   page followed by a second page that is itself a cover page or a boilerplate stamp is
   skipped and ``title_page`` advances past both. A second front page that is boilerplate
   but carries NEITHER a host marker NOR the cover's bibliographic fields — an unbranded
   terms-of-use continuation, say — is not recognised, and ``title_page`` then points at it
   rather than at the article. The ROUTE is unaffected either way.
   **Measured:** no corpus file has a second front page at all. (Referee §4, kill K2.)

3. **``mixed`` is over-inclusive, in the safe direction.** A born-digital figure page —
   a raster over a quarter of the page with only a caption in the text layer — is
   ``partial`` by definition, which nominates it for OCR even though its words are already
   in the layer and OCR would return only the figure's baked-in tick labels. The referee
   inspected four such pages across three ``mixed`` files (Cardille p12, MacFaden p1,
   Pauls p14/16/17) and found 4 of 4 to be native figure pages, not scanned inserts. The
   cost is a wasted OCR page; the alternative error — dropping a scanned insert from the
   queue — is the expensive one, so the class stays as defined. (Referee §2.)
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import pathlib
import statistics
import sys
import time

TOOL = "pypdfium2"
STAGE = 0

# ── the frozen thresholds (see the module docstring for the census behind each) ─────────
CHARS_TRACE = 100        # below: the text layer is a stamp, not content
CHARS_BODY = 400         # at or above: the page carries body text
IMAGE_COVER = 0.25       # image area / cropbox area: the page carries a full-page raster
COVER_MAX_CHARS = 200    # a boilerplate-only page-1 text layer (EDGE_PRE1990 P-2)
SCAN_FILE_FRAC = 0.5     # share of OCR-needing pages at which a file is priced as a scan
COVER_MIN_FIELDS = 2     # cover-sheet fields required on page 1 alongside a host marker

#: Two different things carry JSTOR/IMS boilerplate, and only one of them is a cover sheet.
#: MEASURED 2026-09-15 by rendering page 1 of each and looking at it:
#:
#: * a **standalone cover page** — a masthead, then ``Author(s):`` / ``Source:`` /
#:   ``Published by:`` / ``Stable URL:``, then the terms-of-use paragraph, and nothing else.
#:   The article starts on page 2. Almon 1965, Page 1954, Begg 1983, Cabo 1995, Dawid 1979,
#:   Hui 1980, Satten 1996: 8 records, every one carrying all FOUR field markers and ~850–1,080
#:   characters. This is ``cover-sheet``.
#: * a **stamp on the article's own first page** — the IMS notice printed into the bottom
#:   margin of a scan. Anderson 1957, Hudson 1978, Hwang 1982, Politis 1994: the whole
#:   page-1 text layer is 130–142 characters of that notice, ZERO field markers, and the
#:   rendered page shows the article's title and opening paragraphs as image. This is NOT a
#:   cover sheet; those files are scans and their title is in the raster.
#:
#: The two separate perfectly on the field-marker count (4 vs 0) across the whole corpus,
#: which is why the rule counts fields rather than capping characters.
COVER_FIELD_MARKERS = ("author(s):", "stable url:", "published by:", "source:")
COVER_HOST_MARKERS = (
    "jstor",
    "is collaborating with",
    "your use of the jstor archive indicates your acceptance",
)

PAGE_CLASSES = ("text", "partial", "image-only", "empty")
ROUTES = ("native", "mixed", "scan", "cover-sheet", "unreadable")


def tool_version():
    import importlib.metadata as md
    return md.version("pypdfium2")


def params_hash():
    """Digest of every threshold that can change a class. Part of the §12.4 run key."""
    payload = json.dumps({
        "CHARS_TRACE": CHARS_TRACE, "CHARS_BODY": CHARS_BODY,
        "IMAGE_COVER": IMAGE_COVER, "COVER_MAX_CHARS": COVER_MAX_CHARS,
        "SCAN_FILE_FRAC": SCAN_FILE_FRAC, "COVER_MIN_FIELDS": COVER_MIN_FIELDS,
        "COVER_FIELD_MARKERS": list(COVER_FIELD_MARKERS),
        "COVER_HOST_MARKERS": list(COVER_HOST_MARKERS),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class InventoryError(RuntimeError):
    pass


# ── §7.1 page frames ───────────────────────────────────────────────────────────────────

def page_frames(pdf_path, error=None):
    """``{page: {mediabox, cropbox, rotation, dx, dy}}`` — the §7.1 frame of every page.

    ``rotation`` is pdfium's quarter turns (0..3), not degrees. ``dx``/``dy`` express the
    cropbox's upper-left corner in the mediabox's upper-left frame; they are what a
    cropbox-relative tool's coordinates must be shifted by to reach the canonical frame.

    This is the ONE frame reader, and since 2026-09-15 it is the only BODY: the GROBID and
    Docling adapters' ``page_frames`` now call this one and differ only in the exception
    class raised on a page with no mediabox, which is what ``error`` names (default
    :class:`InventoryError`). Before that there were three copies with the same arithmetic
    and different guards — Docling's had neither the inherited-``/MediaBox`` fallback nor
    the missing-mediabox raise, so on such a page it returned ``None`` boxes and died with a
    ``TypeError`` inside the shift. §7.1 carried that as the item to close before stage 5,
    stage 5 being the first place where two readers of one fact produce wrong boxes rather
    than merely duplicate code (CLAUDE.md §3.3).

    A rotated page is reported, never converted: for rotation 2 the map from a displayed
    frame to the mediabox frame is a reflection, not this translation, and applying the
    translation there is a ~361 pt error in x (measured on
    ``Hall_1985_resampling-coverage-pattern.pdf`` p12, the corpus's ONLY page that is both
    rotated and cropped — Reports/LITKB_GROBID_LOCAL_REFEREE2_2026-09-15.md §4).
    """
    import pypdfium2 as pdfium
    import pypdfium2.raw as praw

    frames = {}
    doc = pdfium.PdfDocument(pdf_path)
    try:
        for i in range(len(doc)):
            frames[i + 1] = _frame(doc[i], praw, os.path.basename(str(pdf_path)), i + 1,
                                   error=error)
    finally:
        doc.close()
    return frames


def _raw_box(fn, page, fallback):
    # A page that inherits /MediaBox from the page tree has no box of its own and the raw
    # getter returns 0; pypdfium2's high-level accessor resolves the inherited default, so
    # it is the fallback rather than a None that would crash the arithmetic.
    vals = [ctypes.c_float() for _ in range(4)]
    if fn(page.raw, *[ctypes.byref(v) for v in vals]):
        return tuple(round(v.value, 4) for v in vals)
    try:
        return tuple(round(float(v), 4) for v in fallback())
    except Exception:  # noqa: BLE001
        return None


def _frame(page, praw, name, number, error=None):
    # BEGIN guard: inherited MediaBox fallback
    media = _raw_box(praw.FPDFPage_GetMediaBox, page, page.get_mediabox)
    crop = _raw_box(praw.FPDFPage_GetCropBox, page, page.get_cropbox) or media
    # END guard: inherited MediaBox fallback
    if media is None:
        raise (error or InventoryError)(f"{name} page {number} has no mediabox; "
                                        "the §7.1 frame cannot be established")
    return {
        "mediabox": list(media), "cropbox": list(crop),
        "rotation": int(praw.FPDFPage_GetRotation(page.raw)),
        "dx": round(crop[0] - media[0], 4), "dy": round(media[3] - crop[3], 4),
    }


# ── classification ─────────────────────────────────────────────────────────────────────

def classify_page(chars, image_frac):
    """-> one of :data:`PAGE_CLASSES`. Pure; the gate's mutation target."""
    if image_frac >= IMAGE_COVER:
        if chars < CHARS_TRACE:
            return "image-only"
        if chars < CHARS_BODY:
            return "partial"
        return "text"
    if chars == 0:
        return "empty"
    return "text"


def needs_ocr(page_class):
    return page_class in ("image-only", "partial")


def is_cover_sheet(page_one_text):
    """True when page 1 is a STANDALONE publisher cover page (title expected on page 2).

    Requires both a host marker and at least :data:`COVER_MIN_FIELDS` of the cover's own
    bibliographic fields, which is what separates a cover page from the same publisher's
    one-line stamp on an article's first page (see :data:`COVER_FIELD_MARKERS`).
    """
    low = (page_one_text or "").lower()
    if not any(m in low for m in COVER_HOST_MARKERS):
        return False
    return sum(1 for m in COVER_FIELD_MARKERS if m in low) >= COVER_MIN_FIELDS


def is_cover_stamp(page_one_text, chars):
    """True when page 1's whole text layer is publisher boilerplate over a scanned page."""
    if chars >= COVER_MAX_CHARS:
        return False
    low = (page_one_text or "").lower()
    return (any(m in low for m in COVER_HOST_MARKERS)
            and not any(m in low for m in COVER_FIELD_MARKERS))


def route_file(pages, cover_sheet, unreadable=False):
    """-> one of :data:`ROUTES`. Precedence: unreadable > scan > mixed > cover-sheet > native."""
    if unreadable:
        return "unreadable"
    if not pages:
        return "unreadable"
    ocr = sum(1 for p in pages if needs_ocr(p["scan"]))
    if ocr and ocr / len(pages) >= SCAN_FILE_FRAC:
        return "scan"
    if ocr:
        return "mixed"
    if cover_sheet:
        return "cover-sheet"
    return "native"


# ── the probe ──────────────────────────────────────────────────────────────────────────

def digests(path, chunk=1 << 20):
    """(sha256, md5, bytes) in one pass. Read-only; ``Literture\\`` is never written."""
    s, m, n = hashlib.sha256(), hashlib.md5(), 0
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            s.update(b)
            m.update(b)
            n += len(b)
    return s.hexdigest(), m.hexdigest(), n


def _page_measure(page, praw, name, number):
    frame = _frame(page, praw, name, number)
    textpage = page.get_textpage()
    try:
        n = textpage.count_chars()
        text = textpage.get_text_range(0, n) if n else ""
    finally:
        textpage.close()
    chars = sum(1 for c in text if not c.isspace())
    images, area = 0, 0.0
    # max_depth reaches images nested inside form XObjects, which is where a scanned page
    # placed by some producers actually lives; without it such a page reads as image-free.
    for obj in page.get_objects(filter=[praw.FPDF_PAGEOBJ_IMAGE], max_depth=8):
        images += 1
        x0, y0, x1, y1 = obj.get_bounds()
        area += abs(x1 - x0) * abs(y1 - y0)
    crop = frame["cropbox"]
    page_area = abs(crop[2] - crop[0]) * abs(crop[3] - crop[1]) or 1.0
    frac = round(area / page_area, 4)
    rec = dict(frame)
    rec.update(page=number, chars=chars, images=images, image_frac=frac,
               scan=classify_page(chars, frac))
    return rec, text


def probe_file(path):
    """-> the JSONL record for one PDF. Never raises for a bad PDF: it routes ``unreadable``."""
    from litkb.textnorm import jsonb_safe

    import pypdfium2 as pdfium
    import pypdfium2.raw as praw

    path = pathlib.Path(path)
    sha, md5, nbytes = digests(path)
    t0 = time.monotonic()
    rec = {
        "path": str(path), "name": path.name, "sha256": sha, "md5": md5, "bytes": nbytes,
        "stage": STAGE, "tool": f"{TOOL}@{tool_version()}", "params_hash": params_hash(),
    }
    try:
        doc = pdfium.PdfDocument(path)
    except Exception as exc:  # noqa: BLE001
        rec.update(pages=0, page_detail=[], route="unreadable",
                   unreadable_reason=_last_error(praw), error=repr(exc),
                   cover_sheet=False, cover_stamp=False, title_page=None, ocr_pages=[],
                   encrypted=None,
                   seconds=round(time.monotonic() - t0, 3))
        return rec

    name = path.name
    try:
        rec["encrypted"] = int(praw.FPDF_GetSecurityHandlerRevision(doc.raw)) != -1
        try:
            rec["pdf_version"] = doc.get_version()
        except Exception:  # noqa: BLE001
            rec["pdf_version"] = None
        info = {}
        try:
            info = doc.get_metadata_dict() or {}
        except Exception:  # noqa: BLE001
            info = {}
        rec["info"] = jsonb_safe(dict(info))
        rec["producer"] = jsonb_safe(info.get("Producer") or "") or None
        rec["creator"] = jsonb_safe(info.get("Creator") or "") or None
        rec["title_meta"] = jsonb_safe(info.get("Title") or "") or None

        detail, first_text = [], ""
        # How many LEADING pages are publisher front matter rather than the document.
        # Advanced one page at a time and only while every page so far has been front
        # matter, so a cover page followed by a second cover page or a boilerplate stamp
        # leaves title_page pointing at the article rather than at the second cover. Uses
        # only the existing COVER_* constants on purpose: no new threshold means no new
        # params_hash, so this cannot silently re-price a corpus already probed.
        lead_boiler = 0
        for i in range(len(doc)):
            page = doc[i]
            try:
                one, text = _page_measure(page, praw, name, i + 1)
            except Exception as exc:  # noqa: BLE001
                rec.update(pages=len(doc), page_detail=detail, route="unreadable",
                           unreadable_reason="page", error=repr(exc), cover_sheet=False,
                           cover_stamp=False, title_page=None, ocr_pages=[],
                           seconds=round(time.monotonic() - t0, 3))
                return rec
            if i == 0:
                first_text = text
            if i == lead_boiler and (is_cover_sheet(text)
                                     or is_cover_stamp(text, one["chars"])):
                lead_boiler = i + 1
            detail.append(one)
    finally:
        doc.close()

    cover = bool(detail) and is_cover_sheet(first_text)
    stamp = bool(detail) and is_cover_stamp(first_text, detail[0]["chars"])
    rec.update(
        pages=len(detail),
        page_detail=detail,
        cover_sheet=cover,
        cover_stamp=stamp,
        title_page=_title_page(detail, lead_boiler),
        ocr_pages=[p["page"] for p in detail if needs_ocr(p["scan"])],
        route=route_file(detail, cover),
        rotated_pages=[p["page"] for p in detail if p["rotation"]],
        cropped_pages=[p["page"] for p in detail if p["cropbox"] != p["mediabox"]],
        median_chars=int(statistics.median([p["chars"] for p in detail])) if detail else 0,
        seconds=round(time.monotonic() - t0, 3),
    )
    return rec


def _title_page(detail, lead_boiler=0):
    """The page whose TEXT LAYER should carry the title, or None when no page does.

    *lead_boiler* is the count of leading publisher front-matter pages to step over — 0 for
    a document that starts on page 1, 1 for a single cover page or stamp, and more when the
    front matter is deeper (see the module docstring's limitation 2 for what that detector
    does and does not recognise).

    None is the answer for a scan: the title is in the raster and only OCR will produce it.
    That is the honest reading of Anderson/Hudson/Hwang/Politis, whose every page after the
    boilerplate stamp holds zero characters (Reports/LITKB_INVENTORY_2026-09-15.md §4).
    """
    for p in detail[lead_boiler:]:
        if p["chars"] >= CHARS_TRACE:
            return p["page"]
    return None


def _last_error(praw):
    codes = {0: "SUCCESS", 1: "UNKNOWN", 2: "FILE", 3: "FORMAT", 4: "PASSWORD",
             5: "SECURITY", 6: "PAGE"}
    try:
        return codes.get(int(praw.FPDF_GetLastError()), "UNKNOWN")
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


# ── the run ────────────────────────────────────────────────────────────────────────────

def find_pdfs(root):
    return sorted(p for p in pathlib.Path(root).rglob("*") if p.suffix.lower() == ".pdf")


def resume_key(sha256, path, ph):
    """The identity a re-run skips on. ONE definition, used by both sides of the resume.

    Keyed on the PATH as well as the hash on purpose: two copies of one file are two
    records, so ``--force``-free re-runs still report duplicates by sha256 instead of
    silently dropping every copy after the first. Writing the tuple out at each of the two
    call sites instead of here is how a guard gets weakened at one site only — the lesson
    the P2 harness's per-call-site rule was written for.
    """
    return (sha256, str(path), ph)


def load_done(jsonl):
    """-> ({resume_key(...)} already recorded, the records themselves)."""
    done, keep = set(), []
    p = pathlib.Path(jsonl)
    if not p.exists():
        return done, keep
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add(resume_key(r.get("sha256"), r.get("path"), r.get("params_hash")))
            keep.append(r)
    return done, keep


def run(root, out_jsonl, csv_path=None, force=False, progress=False):
    """Probe every PDF under *root*, resumably. -> (records, seconds)."""
    out_jsonl = pathlib.Path(out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    ph = params_hash()
    done, existing = (set(), []) if force else load_done(out_jsonl)
    by_key = {resume_key(r.get("sha256"), r.get("path"), r.get("params_hash")): r
              for r in existing}

    pdfs = find_pdfs(root)
    t0 = time.monotonic()
    records = []
    for k, path in enumerate(pdfs, 1):
        sha, _, _ = digests(path)
        key = resume_key(sha, path, ph)
        if key in done:
            records.append(by_key[key])
            if progress:
                print(f"{k}/{len(pdfs)} skip {path.name}", flush=True)
            continue
        rec = probe_file(path)
        records.append(rec)
        if progress:
            print(f"{k}/{len(pdfs)} {rec['route']:<11} {path.name}", flush=True)
    seconds = time.monotonic() - t0

    _write_atomic(out_jsonl, "".join(json.dumps(r, ensure_ascii=False) + "\n"
                                     for r in records))
    if csv_path:
        write_summary_csv(records, csv_path)
    return records, seconds


def _write_atomic(path, text):
    """`.partial` -> fsync -> rename, the pattern ``litkb.ops.nightly_dump`` already uses."""
    path = pathlib.Path(path)
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


CSV_COLUMNS = ("name", "relpath", "sha256", "bytes", "pages", "route", "cover_sheet",
               "cover_stamp", "title_page", "ocr_page_count", "image_only_pages", "partial_pages",
               "empty_pages", "text_pages", "rotated_pages", "cropped_pages", "encrypted",
               "pdf_version", "producer", "creator", "median_chars", "seconds")


def write_summary_csv(records, csv_path, root=None):
    """One row per file — the tracked measured text (CLAUDE.md §3.4b)."""
    root = pathlib.Path(root) if root else None
    rows = []
    for r in sorted(records, key=lambda x: x["path"]):
        detail = r.get("page_detail") or []
        counts = {c: sum(1 for p in detail if p["scan"] == c) for c in PAGE_CLASSES}
        rel = r["path"]
        if root:
            try:
                rel = str(pathlib.Path(r["path"]).relative_to(root))
            except ValueError:
                pass
        rows.append({
            "name": r["name"], "relpath": rel, "sha256": r["sha256"],
            "bytes": r["bytes"], "pages": r.get("pages", 0), "route": r["route"],
            "cover_sheet": r.get("cover_sheet"), "cover_stamp": r.get("cover_stamp"),
            "title_page": r.get("title_page"),
            "ocr_page_count": len(r.get("ocr_pages") or []),
            "image_only_pages": counts.get("image-only", 0),
            "partial_pages": counts.get("partial", 0),
            "empty_pages": counts.get("empty", 0), "text_pages": counts.get("text", 0),
            "rotated_pages": len(r.get("rotated_pages") or []),
            "cropped_pages": len(r.get("cropped_pages") or []),
            "encrypted": r.get("encrypted"), "pdf_version": r.get("pdf_version"),
            "producer": (r.get("producer") or "").replace("\n", " "),
            "creator": (r.get("creator") or "").replace("\n", " "),
            "median_chars": r.get("median_chars", 0), "seconds": r.get("seconds"),
        })
    path = pathlib.Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS))
        w.writeheader()
        w.writerows(rows)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return rows


def summarise(records):
    """-> the counts the phase report quotes. Derived, never hand-typed."""
    from collections import Counter
    routes = Counter(r["route"] for r in records)
    pages = sum(r.get("pages", 0) for r in records)
    detail = [(r, p) for r in records for p in (r.get("page_detail") or [])]
    classes = Counter(p["scan"] for _, p in detail)
    sha = Counter(r["sha256"] for r in records)
    return {
        "files": len(records), "pages": pages,
        "routes": dict(sorted(routes.items())),
        "page_classes": dict(sorted(classes.items())),
        "rotated_pages": [(r["name"], p["page"], p["rotation"]) for r, p in detail
                          if p["rotation"]],
        "cropped_pages": sum(1 for _, p in detail if p["cropbox"] != p["mediabox"]),
        "cropped_files": len({r["name"] for r, p in detail
                              if p["cropbox"] != p["mediabox"]}),
        "rotated_and_cropped": [(r["name"], p["page"]) for r, p in detail
                                if p["rotation"] and p["cropbox"] != p["mediabox"]],
        "encrypted": [r["name"] for r in records if r.get("encrypted")],
        "unreadable": [r["name"] for r in records if r["route"] == "unreadable"],
        "scans": sorted(r["name"] for r in records if r["route"] == "scan"),
        "cover_sheets": sorted(r["name"] for r in records if r.get("cover_sheet")),
        "cover_stamps": sorted(r["name"] for r in records if r.get("cover_stamp")),
        "no_title_page": sorted(r["name"] for r in records if r.get("title_page") is None),
        "duplicate_sha256": {h: sorted(r["name"] for r in records if r["sha256"] == h)
                             for h, n in sha.items() if n > 1},
        "ocr_pages": sum(len(r.get("ocr_pages") or []) for r in records),
    }


DEFAULT_ROOT = pathlib.Path(r"D:\edmonds-pipeline\Literture")


def repo_root():
    return pathlib.Path(__file__).resolve().parents[4]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="litkb-inventory", description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--jsonl", default=None,
                    help="default: <repo>/phase4/qc/litkb_inventory.jsonl")
    ap.add_argument("--csv", default=None,
                    help="default: <repo>/phase4/qc/litkb_inventory.csv")
    ap.add_argument("--force", action="store_true", help="re-probe every file")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    qc = repo_root() / "phase4" / "qc"
    jsonl = pathlib.Path(args.jsonl) if args.jsonl else qc / "litkb_inventory.jsonl"
    csv_out = pathlib.Path(args.csv) if args.csv else qc / "litkb_inventory.csv"

    records, seconds = run(args.root, jsonl, csv_path=None, force=args.force,
                           progress=not args.quiet)
    write_summary_csv(records, csv_out, root=args.root)
    s = summarise(records)
    print(json.dumps({k: v for k, v in s.items()
                      if k not in ("rotated_pages", "scans", "cover_sheets",
                                     "cover_stamps", "no_title_page")},
                     indent=1))
    print(f"wall_clock_seconds {seconds:.1f} for {s['files']} files / {s['pages']} pages")
    print(f"jsonl {jsonl}")
    print(f"csv   {csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

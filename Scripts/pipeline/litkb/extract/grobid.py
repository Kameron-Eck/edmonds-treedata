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

Rotation IS applied by GROBID (a ``/Rotate 90`` page gets a landscape ``<surface>``), but the
composition of rotation with the cropbox shift is **UNCONFIRMED**, so :func:`to_mediabox`
refuses to convert a rotated page and leaves those blocks in the cropbox frame.

ZERO-BLOCK REFUSAL: a 200 is not success. A PDF with a text layer on only some pages — a
JSTOR scan whose cover page carries the access boilerplate — returns HTTP 200 with a valid
header and an EMPTY ``<text><body>`` (measured on ``Anderson_1957``: 3,659 B, 4 blocks, all
of them the boilerplate title in the header, ``<body>`` text ``''``). A caller checking only
the status code records that as a successful extraction. :func:`process_pdf` therefore refuses
any TEI with no coordinate-bearing block inside ``<text><body>``, raising :class:`NoTextBlocks`.

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
        for i, (page, x0, y0, x1, y1) in enumerate(boxes):
            yield Block(page=page, x0=x0, y0=y0, x1=x1, y1=y1, kind=kind, text=text,
                        element_id=eid, box_index=i, box_count=len(boxes))


def blocks(tei, kinds=None):
    return list(iter_blocks(tei, kinds))


BODY_PATH = ".//t:text/t:body"


def body_blocks(tei, kinds=None):
    """Coordinate-bearing blocks from ``<text><body>`` only — the document, not the header.

    The header alone is not extraction: a JSTOR cover page's access boilerplate parses into a
    header title and nothing else (measured on ``Anderson_1957``, 2026-09-14).
    """
    return list(iter_blocks(tei, kinds, subtree=BODY_PATH))


def body_text(tei):
    """Whitespace-normalised text of ``<text><body>`` ('' when there is no body at all)."""
    el = _root(tei).find(BODY_PATH, NS)
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def check_text_blocks(tei, name=""):
    """Raise :class:`NoTextBlocks` when a 200 carried no extracted document body.

    The rule is BLOCK-BASED, not byte-based: a body with text but no coordinates would mean
    the request forgot ``teiCoordinates`` (which is a caller bug, and is reported as one),
    while a body with neither is a document that was not extracted. Both are refusals.
    """
    n_blocks = len(body_blocks(tei))
    if n_blocks:
        return n_blocks
    what = name or "document"
    raise NoTextBlocks(
        f"GROBID returned 200 for {what} but its <text><body> yields no coordinate-bearing "
        f"blocks (body text {len(body_text(tei))} chars, header title "
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
    """
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as praw

    def _box(fn, page, fallback):
        # A page that inherits its /MediaBox from the page tree has no box of its own and the
        # raw getter returns 0; pypdfium2's high-level accessor resolves the inherited default,
        # so it is the fallback rather than a None that would crash the arithmetic below.
        vals = [ctypes.c_float() for _ in range(4)]
        if fn(page.raw, *[ctypes.byref(v) for v in vals]):
            return tuple(v.value for v in vals)
        try:
            return tuple(fallback())
        except Exception:
            return None

    frames = {}
    doc = pdfium.PdfDocument(pdf_path)
    try:
        for i in range(len(doc)):
            page = doc[i]
            media = _box(praw.FPDFPage_GetMediaBox, page, page.get_mediabox)
            crop = _box(praw.FPDFPage_GetCropBox, page, page.get_cropbox) or media
            if media is None:
                raise GrobidError(f"{os.path.basename(pdf_path)} page {i + 1} has no mediabox; "
                                  "the §7.1 frame cannot be established")
            rot = int(praw.FPDFPage_GetRotation(page.raw))
            frames[i + 1] = {
                "mediabox": media, "cropbox": crop, "rotation": rot,
                "dx": crop[0] - media[0], "dy": media[3] - crop[3],
            }
    finally:
        doc.close()
    return frames


def to_mediabox(blocks_in, frames):
    """Shift blocks from GROBID's cropbox-relative frame into the canonical mediabox frame.

    A page with ``rotation != 0`` is NOT converted: GROBID already reports it in the
    displayed (rotated) frame, and how the cropbox shift composes with that rotation is
    UNCONFIRMED (7 rotated pages in the 216-PDF corpus). Those blocks come back unchanged,
    still carrying ``frame="cropbox"``, so a caller can see which ones were skipped. A page
    with no frame record is likewise left alone.
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
                consolidate_citations=False, timeout=3600, require_text_blocks=True):
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

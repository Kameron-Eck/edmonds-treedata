"""GROBID 0.9.1 (CRF) adapter — service control, one-file processing, and the §7.1 bbox adapter.

The service itself runs under WSL2 Ubuntu and is managed by ``grobid.sh`` beside this file;
see ``LITKB_GROBID_LOCAL_2026-09-14.md`` for the install layout and the measured numbers.

CANONICAL FRAME (design §7.1): PDF points, page numbers 1-indexed, origin at the TOP-LEFT of
the page as displayed, box = (x0, y0, x1, y1).

WHAT GROBID EMITS: ``coords="page,x,y,w,h"`` — page 1-indexed, PDF units, origin upper-left
(measured against the ``<facsimile>`` surfaces, 2026-09-14). So the adapter is
``x1 = x + w, y1 = y + h`` with NO page offset and NO y-flip. Two properties of the real
output the adapter must honour, both measured rather than assumed:

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

    def __init__(self, message, status=None, body=b""):
        super().__init__(message)
        self.status = status
        self.body = body


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


def iter_blocks(tei, kinds=None):
    """Yield a :class:`Block` for every box on every coordinate-bearing element."""
    root = _root(tei)
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
                consolidate_citations=False, timeout=3600):
    """POST one PDF to processFulltextDocument -> TEI bytes.

    ``teiCoordinates`` is a REPEATED form field, one element name per field. Passing the
    list as a single comma-joined value is accepted but yields almost no coordinates
    (measured 2026-09-14: 7 coords across a four-paper set, none on refs, heads or figures).

    Consolidation is off by default: it reaches Crossref over the network, and the design
    keeps stage 2 offline unless a caller opts in.
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
            return r.read()
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

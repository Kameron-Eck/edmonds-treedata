"""THE ACCEPTANCE TEST: are these bytes a whole PDF of the work they were fetched for?
(LITKB_WORKPLAN.md "### S4.5" item 5, the acceptance-test sentences; guard 18.)

    from litkb.acquire import accept as A
    v = A.accept(data, headers=..., url=..., terminal_url=..., doi=..., record_pages=...)
    v.verdict        "accept" | "refuse"
    v.sub_status     None, or ONE `bad-file` sub-status of the S4.5 vocabulary (SUB_STATUSES)
    v.pdf            the bytes to land (unwrapped from gzip/tar, header repaired), or None
    v.facts          what was measured: pages, chars, words, the stub signals, the landing-page pointers ...
    v.summary()      the JSON-safe record of all of it (never the bytes)
    A.quick_magic(data)      the header rule alone, for a route module's early sniff (ONE home)
    A.offer_to_bind(...)     the acceptance test, then the real bind (`run.land_and_attach`) on the bytes it accepted

WHY. Until S4.5 the whole test was `store.pdf_shape`: a `%PDF-` prefix and a `%%EOF` in the last 4 KiB. It
refused a valid PDF that starts with a byte-order mark, took a 1 KB publisher stub, a first-page TDM response,
a 47-page publisher preview of a book and a 60-page proceedings volume as "the paper", and could not say WHY a
refused download was refused beyond "not a PDF". The plan replaces it with the steps below, in this order, and
the refusal names ONE sub-status the ledger stores (the vocabulary's Python home is builder-C1a's; this module
only RETURNS values from it — `SUB_STATUSES` is the subset it can return and a test holds it inside the
CONTRACTS list).

THE ORDER, and where each rule comes from (Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md §1 Stage C; every rule
is VERIFIED-in-source there and NONE is calibrated on litkb's rows — a RELAYED design, UNVALIDATED until an
independent referee scores it, CLAUDE.md §3.4c):

  1  unwrap   gzip / tar (and a tar inside gzip) — C18. The plan lists decompression after the MIME check, but a
              wrapped PDF fails every header step before it, and C18 itself says "BEFORE the %PDF- check": the
              sniff that recognises the wrapper is what decides to unwrap, so unwrapping comes first. A wrapper
              holding no PDF, or several, is `compressed_or_archived_payload`. zip is recognised and refused the
              same way, never unwrapped (the plan names gzip and tar only).
  2  repair   `%PDF-` found at an offset > 0 inside the first REPAIR_WINDOW bytes: the bytes are taken from that
              offset (C14). BEFORE the magic check, deliberately (survey-design "Item 5", the BOM caveat):
              `bytes.lstrip()` strips ASCII whitespace only, so a BOM-prefixed PDF reaches a bare lstrip check
              as `missing_pdf_header`. A prefix that looks like HTML is never "repaired" — an HTML page that
              quotes a PDF header is a page, not a PDF.
  3  magic    `data[:32].lstrip().startswith(b"%PDF")` (C1-RG a). Failing it: an HTML body is `html_response`
              (with the landing-page pointers it carries, which Stage C reads), anything under the floor
              `too_small`, anything else `missing_pdf_header`.
  4  header   the version after `%PDF-` must read `d.d`, and the first MOJIBAKE_WINDOW bytes must not hold
              U+FFFD — the mark a binary PDF leaves after a text decode (C1-RG c, "mojibake test on the
              first 64 bytes"; the survey names the test, not its predicate: this predicate is this module's
              reading of it) -> `corrupt_pdf_header`.
  5  floor    MIN_PDF_BYTES (C1-RG b) -> `too_small`.
  6  mime     libmagic's MIME type (C21). python-magic is NOT importable on this machine (measured
              2026-09-23: ModuleNotFoundError) and the survey names no fallback, so the fallback here is this
              module's own signature sniff (`sniff`), labelled `mime_source="fallback-sniff"` in the facts: after
              step 3 passed it can only answer application/pdf, so without libmagic this step adds nothing.
  7  eof      `%%EOF` within EOF_TAIL of the end (C1-RG d) -> `early_eof_with_trailing_payload`.
  8  qpdf     `qpdf --check`: exit 0 clean, 3 recoverable (accepted, recorded), 2 damaged -> `corrupt_pdf_header`
              (the vocabulary's nearest value; the mapping is this module's choice). The `--is-encrypted`
              exit codes mean something else and are never read here. The qpdf CLI is NOT on PATH on this
              machine (measured 2026-09-23), so the checker is libqpdf through pikepdf (S4.5 decision D14,
              Kam 2026-09-23: `pikepdf.Pdf.check_pdf_syntax()`) — libqpdf's own check, NOT the literal
              `qpdf --check` command line; `libqpdf_check` says how its answers map to the three outcomes. The
              CLI is used only when pikepdf is not importable; with neither, the step reports
              `qpdf-unavailable` — never `clean` — and the verdict's `complete` is False.
  9  text     pdfium page count, per-page text and per-page raster images (bytes in memory; nothing
              written; the images counted the way `litkb.extract.probe.page_raster_images` counts them). A document pdfium
              cannot open is NOT refused here: the bind's probe (`litkb.extract.probe`) refuses it
              `probe-error`, and one refusal has one home.
 10  stub     any stub signal -> `stub_not_article` (C16 + H2-RG + C19):
                chars_no_refs  fewer than STUB_MAX_CHARS characters of text and no reference-section heading —
                               ASKED ONLY OF A DOCUMENT WITH NO IMAGE PAGE. An image page (decision D13's one
                               rule, `litkb.extract.probe.image_pages`: zero native characters AND a raster
                               image) carries its words as pixels, so the character count is a lower bound that
                               proves nothing: a scanned article is not a stub for having no text layer
                               (auditor-C1b F1, MEASURED on live: Anderson_1957, Hudson_1978, Hwang_1982 and
                               Ogata_1998 — the four scans P2 made bind on OCR — read 0-163 characters). The
                               rule then abstains and the facts say so (`image_pages`). ITS STATED LIMIT
                               (auditor-C1b round 2, F1): the abstention covers ANY document holding at least
                               one image page, not only a scan — a short text stub followed by one image-only
                               page (a cover, an advertisement, a full-page figure) is not judged by this
                               signal either (qc/test_litkb_accept.py pins it on a CONSTRUCTED 2,189-character
                               first page plus one image page: ACCEPTED). The other two signals still apply to
                               it. MEASURED on live by auditor-C1b round 2: of the 263 bound files, only the four
                               scans hold an image page. Narrowing the abstention (say, to documents whose
                               image pages are the majority) is a design change needing a sourced constant —
                               the stub referee's to rule, not this module's to guess.
                x_els_status   an `X-ELS-Status` response header whose value is not OK (H2-RG: Elsevier
                               announces a first-page-only TDM PDF ONLY in that header; `OK` is the value
                               phase4/qc/litkb_acq_probe_elsevier_key.csv MEASURED on a normal 200)
                preview_url    "preview" in the path of the requested or the terminal URL, or in the
                               Content-Disposition (C19's shape, widened by the head probe's measured token:
                               qc/instruments/litkb_acq_probe_head.py found E20's `.../relatedobjects/preview.pdf`)
 11  volume   page count >= VOLUME_PAGES against a record page range (an `a-b` digit form ONLY) spanning
              fewer -> `volume_not_article` (C17). An unparseable range is neither hit nor pass: the fact says
              `unparsed` (the `page_ranges_unparsed` count).
 12  cited    the requested DOI printed ONLY after the first DOI_PAGES pages -> `cited_document_not_this_article`
              (guard 4 / T14: a bibliography must not supply the DOI match).
 13  identity the record page range as an identity signal (T15): `match` / `short` / `long` — RECORDED, never a
              refusal here (a preprint of a journal article is legitimately shorter than the typeset range).

GUARD 18 (never a verdict resting on metadata that could not be fetched): steps 11 and 12 read the RECORD, and
when the caller says the record could not be fetched they abstain — `unfetched`, never a refusal — whatever
stale page range or DOI came along.

Nothing here writes a file (step 8 reads the bytes in memory through pikepdf; only the CLI fallback writes them
to a temporary directory OUTSIDE the literature store, create-only, for qpdf to read). `offer_to_bind` writes
only through the Store, via `run.quarantine_bytes` and `run.land_and_attach`.
"""
import hashlib
import io
import re
import shutil
import subprocess
import tarfile
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from litkb.acquire import ledger as _ledger
from litkb.acquire import policy as _policy

#: The `bad-file` sub-statuses this module can return — the S4.5 CONTRACTS list, in its order. It IS the
#: vocabulary's ONE home, builder-C1a's `litkb.acquire.policy.BAD_FILE_SUBS` (seam integrator-w1: on C1b's
#: branch this was a copy of it); qc/test_litkb_accept.py holds it equal to the CONTRACTS list.
SUB_STATUSES = _policy.BAD_FILE_SUBS

#: `%PDF-` may sit this far into the bytes and still be repaired (C14, `ZimoLiao/scholaraio@c3a4b265`,
#: VERIFIED in the survey). The same window `litkb.extract.probe` reads for its signature check (the PDF
#: reference's implementation note on leading bytes), so the probe and this test agree on what a PDF is.
REPAIR_WINDOW = 1024
#: C1-RG (a): `body[:32].lstrip().startswith(b"%PDF")` (instsci / CiteClaw / scholaraio, VERIFIED).
MAGIC_WINDOW = 32
#: C1-RG (b): "minimum 5,000 bytes, not 128" (VERIFIED in three implementations; uncalibrated on litkb).
MIN_PDF_BYTES = 5000
#: C1-RG (c): the mojibake test's window, "the first 64 bytes".
MOJIBAKE_WINDOW = 64
#: C1-RG (d): "`%%EOF` within the last 8 KiB".
EOF_TAIL = 8192
#: C16 (`drpwchen/paper-fetch@85ecdf81`): a stub has "< 3000 chars" and no reference section.
STUB_MAX_CHARS = 3000
#: C17 (`drpwchen/paper-fetch@85ecdf81`): `VOLUME_PAGES = 60`.
VOLUME_PAGES = 60
#: guard 4 / T14 (fetchpdf): `DOI_PAGES=3` — the requested DOI counts as identity only on the first three pages.
DOI_PAGES = 3
#: T15 (fetchpdf): `PAGE_COUNT_SLACK=2`, `PAGE_COUNT_MIN_SPAN=2` — the page-range identity signal.
PAGE_COUNT_SLACK = 2
PAGE_COUNT_MIN_SPAN = 2
#: `qpdf --check` exit codes (plan item 5; survey Stage C: 0 clean, 3 recoverable, 2 damaged).
QPDF_EXIT = {0: "clean", 3: "recoverable", 2: "damaged"}
#: The ceiling `Store.extract` already gives pdftotext on one file (seconds); qpdf reads the same file once.
QPDF_TIMEOUT_S = 300
#: The most an unwrapped payload may inflate to. MEASURED 2026-09-23 (builder-C1b): the largest PDF under the
#: literature root is 96,437,706 bytes (other/remotesensing.1029.pdf); rounded up to the next power of two. A
#: wrapper that inflates past every paper the corpus holds is refused, never inflated further (a zip bomb).
UNWRAP_MAX_BYTES = 128 * 1024 * 1024
#: The X-ELS-Status value phase4/qc/litkb_acq_probe_elsevier_key.csv MEASURED on a normal HTTP 200.
ELS_STATUS_OK = "OK"
#: C19's URL shape (`/previewpdf/`, `/preview-pdf/`, `previewpdf?` — `fetchpdf@82a4c474`) all contain this
#: token, and qc/instruments/litkb_acq_probe_head.py's rule (MEASURED on E20, 2026-09-22) is the token itself.
#: The head probe's second token, "sample", is NOT taken: it names real work in real URL paths.
PREVIEW_TOKEN = "preview"
#: A reference-section heading on a line of its own (C16 says "no reference section"; the heading words are
#: this module's choice, and a numbered heading "7. References" counts).
_REF_HEADING = re.compile(r"(?im)^\s*(?:\d{1,2}\.?\s+|[ivx]{1,4}\.\s+)?"
                          r"(references|bibliography|literature cited|works cited|reference list)\s*:?\s*$")
_VERSION = re.compile(rb"%PDF-\d\.\d")
_RANGE = re.compile(r"\s*(\d+)-(\d+)\s*")       # the `a-b` digit form ONLY (plan item 5 / (b))

ARCHIVE_KINDS = ("gzip", "tar", "zip")


@dataclass
class Verdict:
    verdict: str = "accept"
    sub_status: str = None
    reason: str = ""
    pdf: bytes = None
    steps: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def step(self, name, outcome):
        self.steps.append((name, outcome))

    def refuse(self, step, sub_status, reason):
        self.step(step, "fail")
        self.verdict, self.sub_status, self.reason, self.pdf = "refuse", sub_status, reason, None
        return self

    @property
    def complete(self):
        """True only when every step that should have run did run (qpdf unavailable or unable to open -> False)."""
        return not any(o in ("qpdf-unavailable", "unreadable", "encrypted") or str(o).startswith("qpdf-error")
                       for _n, o in self.steps)

    def summary(self):
        """JSON-safe: the verdict, the sub-status, the steps and the facts — never the bytes."""
        return {"verdict": self.verdict, "sub_status": self.sub_status, "reason": self.reason,
                "complete": self.complete, "steps": [list(s) for s in self.steps], "facts": dict(self.facts)}


# ── the byte rules (each one home) ──────────────────────────────────────────────────────────

def _looks_like_html(data):
    # ONE home for "do these bytes open as HTML" (store.pdf_shape's docstring says why); `acquire` must not
    # import `extract` at module scope, so it is imported here.
    from litkb.extract.text_snapshot import looks_like_html

    return looks_like_html(data)


def repair_offset(data):
    """The offset of a `%PDF-` found AFTER leading bytes inside REPAIR_WINDOW, else 0 (C14). A prefix that
    looks like HTML is never repaired."""
    data = data or b""
    off = data.find(b"%PDF-", 0, REPAIR_WINDOW)
    if off <= 0:
        return 0
    return 0 if _looks_like_html(data[:off]) else off


def magic_ok(data):
    """C1-RG (a): the PDF magic after ASCII whitespace."""
    return (data or b"")[:MAGIC_WINDOW].lstrip().startswith(b"%PDF")


def quick_magic(data):
    """The header rule alone, for a route module's early sniff: would the acceptance test's repair and magic
    steps (2 and 3) call these bytes a PDF? ONE home for "does this start like a PDF" — a route that still
    writes `startswith(b"%PDF-")` disagrees with the gate about a BOM-prefixed file."""
    data = data or b""
    return magic_ok(data[repair_offset(data):])


def eof_in_tail(data):
    """C1-RG (d): `%%EOF` within EOF_TAIL of the end."""
    return b"%%EOF" in (data or b"")[-EOF_TAIL:]


def header_corrupt(data):
    """C1-RG (c), this module's reading: a `%PDF-` with no `d.d` version, or U+FFFD in the first bytes."""
    head = (data or b"").lstrip()[:MOJIBAKE_WINDOW]
    return (not _VERSION.match(head)) or (b"\xef\xbf\xbd" in head)


def sniff(data):
    """What the leading bytes ARE: pdf / gzip / tar / zip / html / json / text / empty / binary."""
    data = data or b""
    if not data:
        return "empty"
    if data[:2] == b"\x1f\x8b":
        return "gzip"
    if data[257:262] == b"ustar":
        return "tar"
    if data[:4] == b"PK\x03\x04":
        return "zip"
    if quick_magic(data):
        return "pdf"
    if _looks_like_html(data):
        return "html"
    head = data[:512].lstrip()
    if head[:1] in (b"{", b"["):
        return "json"
    try:
        head.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


_FALLBACK_MIME = {"pdf": "application/pdf", "gzip": "application/gzip", "tar": "application/x-tar",
                  "zip": "application/zip", "html": "text/html", "json": "application/json",
                  "text": "text/plain", "empty": "application/x-empty", "binary": "application/octet-stream"}


def mime_of(data):
    """(mime, source): libmagic when it is importable, else this module's sniff (labelled)."""
    try:
        import magic    # python-magic; NOT importable on the machine this was written on (2026-09-23)
    except ImportError:
        return _FALLBACK_MIME[sniff(data)], "fallback-sniff"
    return magic.from_buffer((data or b"")[:1 << 20], mime=True), "libmagic"


def unwrap(data):
    """(inner PDF bytes, how) for a gzip / tar / tar-in-gzip payload holding exactly ONE PDF, else (None, why)."""
    how = []
    for _depth in range(2):                          # gzip, then a tar inside it: C18's PMC `.tar.gz`
        kind = sniff(data)
        if kind == "gzip":
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            try:
                inner = d.decompress(data, UNWRAP_MAX_BYTES + 1)
            except zlib.error as e:
                return None, f"a gzip payload that does not decompress ({e})"
            if len(inner) > UNWRAP_MAX_BYTES:
                return None, f"a gzip payload that inflates past {UNWRAP_MAX_BYTES} bytes"
            data = inner
            how.append("gzip")
            continue
        if kind == "tar":
            try:
                tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
                pdfs = []
                for m in tf.getmembers():
                    if not m.isfile() or m.size > UNWRAP_MAX_BYTES:
                        continue
                    body = tf.extractfile(m).read()          # read in memory; nothing is extracted to disk
                    if quick_magic(body):
                        pdfs.append((m.name, body))
            except (tarfile.TarError, OSError) as e:
                return None, f"a tar payload that does not read ({type(e).__name__})"
            if len(pdfs) != 1:
                return None, f"a tar payload holding {len(pdfs)} PDFs (exactly one is required)"
            how.append(f"tar:{pdfs[0][0]}")
            data = pdfs[0][1]
            continue
        if kind == "zip":
            return None, "a zip payload (recognised, never unwrapped: the plan names gzip and tar)"
        break
    if not quick_magic(data):
        return None, f"a {'+'.join(how) or 'wrapped'} payload with no PDF inside"
    return data, "+".join(how)


def libqpdf_check(data, notes=None):
    """libqpdf's check through pikepdf (S4.5 decision D14): `pikepdf.Pdf.check_pdf_syntax()` on the bytes in
    memory. -> clean / recoverable / damaged / encrypted / qpdf-error:<type>, or None when pikepdf is not
    importable. How it answers — READ in its source (`pikepdf._methods`, `Pdf.check_pdf_syntax`, pikepdf
    10.13.0.post1): it decodes every stream and parses every page's content, RAISING on an error, and returns
    only qpdf's warnings, each as "WARNING: ...". MEASURED side by side with the `qpdf --check` job
    (`pikepdf.Job`) by builder-C1b on CONSTRUCTED damage, 2026-09-23 (libqpdf 12.3.2; never calibrated on
    litkb's rows):
      damaged      the document does not open, or the check raises `pikepdf.PdfError` — a body with no trailer
                   dictionary; a content stream that fails to decode. The job failed on both (its exit 2).
      recoverable  the check returns warnings — a broken `startxref` whose xref qpdf reconstructs; an unexpected
                   token in a content stream; a page with no Resources. The job exited 3 on each. An entry that
                   is NOT a warning cannot come back from that source; if one ever does it is read as damaged
                   (the conservative direction).
      clean        the check returns nothing (the job's exit 0).
      encrypted    the document needs a password to open (`pikepdf.PasswordError`, deliberately not a
                   PdfError): the check could not run, so the verdict is incomplete, never refused here — the
                   bind's probe refuses a document it cannot open, and one refusal has one home.
    `notes`, when a list, receives what pikepdf said it could NOT check (its UserWarning when a specialised
    decoder such as jbig2dec is missing: those streams were not decoded). `check_pdf_syntax` does not check
    linearization (pikepdf's own docstring), which this test never asks.
    NOT THREAD-SAFE in one respect (auditor-C1b round 2, F9): `warnings.catch_warnings` swaps the PROCESS-wide
    warnings state, so two threads judging bytes at once race on it. On the merged ladder every judgement runs
    on its main thread (auditor-C1b round 2 read it: the rung calls run in a thread pool, the landing that
    judges does not); a rung that judged bytes inside its worker thread could lose or cross `notes` — never a
    verdict, which reads only the check's return."""
    try:
        import pikepdf
    except ImportError:
        return None
    import warnings

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pikepdf.open(io.BytesIO(data)) as pdf:
                problems = [str(p) for p in pdf.check_pdf_syntax()]
    except pikepdf.PasswordError:
        return "encrypted"
    except pikepdf.PdfError:
        return "damaged"
    except Exception as e:                        # noqa: BLE001 — anything else is recorded, never a verdict
        return f"qpdf-error:{type(e).__name__}"
    if notes is not None:
        notes.extend(sorted({str(w.message)[:200] for w in caught}))
    if not problems:
        return "clean"
    return "recoverable" if all(p.startswith("WARNING") for p in problems) else "damaged"


def qpdf_checker():
    """Which checker step 8 runs here: libqpdf through pikepdf, the qpdf CLI, or none (a recorded fact)."""
    try:
        import pikepdf
        return f"libqpdf {pikepdf.__libqpdf_version__} via pikepdf {pikepdf.__version__}"
    except ImportError:
        exe = shutil.which("qpdf")
        return f"qpdf-cli {exe}" if exe else "none"


def qpdf_check(data, runner=None, notes=None):
    """Step 8 on the bytes. -> clean / recoverable / damaged / encrypted / qpdf-unavailable / qpdf-error:<why>.
    libqpdf through pikepdf first (`libqpdf_check`, decision D14), else `qpdf --check` when the CLI is on PATH,
    else `qpdf-unavailable`. `runner(path) -> qpdf exit code` replaces both (the tests' seam); `notes` is
    `libqpdf_check`'s."""
    if runner is None:
        via_pikepdf = libqpdf_check(data, notes)
        if via_pikepdf is not None:
            return via_pikepdf
        exe = shutil.which("qpdf")
        if exe is None:
            return "qpdf-unavailable"

        def runner(path):
            return subprocess.run([exe, "--check", str(path)], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=QPDF_TIMEOUT_S, check=False).returncode
    with tempfile.TemporaryDirectory(prefix="litkb-accept-") as tmp:   # outside the literature store
        p = Path(tmp) / "candidate.pdf"
        with open(p, "xb") as fh:
            fh.write(data)
        try:
            code = runner(p)
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"qpdf-error:{type(e).__name__}"
    return QPDF_EXIT.get(code, f"qpdf-error:{code}")


def page_facts(data):
    """(per-page text list, per-page raster image counts, None) read by pdfium from the bytes in memory, or
    (None, None, error). The images are counted the way `litkb.extract.probe.page_raster_images` counts them
    (image objects, through form XObjects, `max_depth=2`); that function reads a path, and this test reads
    bytes it has not written anywhere."""
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as pdfium_c
        doc = pdfium.PdfDocument(data)
    except Exception as e:                        # noqa: BLE001 — pdfium raises PdfiumError; the fact is recorded
        return None, None, f"{type(e).__name__}: {str(e)[:200]}"
    out, images = [], []
    try:
        for i in range(len(doc)):
            page = doc[i]
            try:
                tp = page.get_textpage()
                try:
                    out.append(tp.get_text_range() or "")
                finally:
                    tp.close()
                images.append(sum(1 for _ in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=2)))
            finally:
                page.close()
    except Exception as e:                        # noqa: BLE001
        return None, None, f"page {len(out) + 1}: {type(e).__name__}: {str(e)[:200]}"
    finally:
        doc.close()
    return out, images, None


def page_texts(data):
    """(per-page text list, None) read by pdfium from the bytes in memory, or (None, error)."""
    texts, _images, err = page_facts(data)
    return texts, err


def image_pages_of(texts, images):
    """1-based numbers of the IMAGE pages: decision D13's one rule (`litkb.extract.probe.image_pages`: zero
    native characters, normalised the way that probe normalises them, AND at least one raster image). [] when
    the image counts were not read."""
    if images is None:
        return []
    from litkb.admit.resolver import _norm_text
    from litkb.extract.probe import image_pages

    return image_pages([len(_norm_text(t)) for t in texts], images)


def text_facts(texts):
    """chars (whitespace runs collapsed), words, and whether a reference-section heading appears. `words` is
    counted by the ledger's ONE word rule (`litkb.acquire.ledger.word_count_of`, the rule that writes
    `file_versions.word_count` from a landing's text extract; seam integrator-w1)."""
    chars = sum(len(" ".join(t.split())) for t in texts)
    words = sum(_ledger.word_count_of(t) for t in texts)
    return {"chars": chars, "words": words, "has_reference_section": any(_REF_HEADING.search(t) for t in texts)}


def _header(headers, name):
    for k, v in (headers or {}).items():
        if str(k).lower() == name.lower():
            return str(v)
    return None


def stub_signals(texts, *, headers=None, urls=(), images=None):
    """The stub detector (step 10): the list of signals that say "a valid PDF that is not the article".
    `images` are the per-page raster image counts (`page_facts`); with them, a document holding ANY image page
    is never read as a stub for its short text (the module docstring, step 10, states that limit)."""
    sig = []
    tf = text_facts(texts)
    counted = True                    # the unguarded default: every character count is taken as the document's
    # BEGIN guard: a document with image pages is never called a stub for its missing text layer
    counted = not image_pages_of(texts, images)
    # END guard: a document with image pages is never called a stub for its missing text layer
    if tf["chars"] < STUB_MAX_CHARS and not tf["has_reference_section"]:
        if counted:
            sig.append("chars_no_refs")
    return sig + evidence_signals(headers=headers, urls=urls)


def evidence_signals(*, headers=None, urls=()):
    """The stub signals read from the landing's EVIDENCE alone — the served headers and the URLs — which need no
    bytes: `x_els_status`, `preview_url`. `stub_signals` asks them after the text signal; the `stubs_bound`
    counter asks them alone of a bound file it cannot read from disk (auditor-C1b round 2, F11)."""
    sig = []
    els = _header(headers, "X-ELS-Status")
    if els is not None and not els.strip().upper().startswith(ELS_STATUS_OK):
        sig.append("x_els_status")
    paths = [urlsplit(u).path.lower() for u in urls if u]
    disp = (_header(headers, "Content-Disposition") or "").lower()
    if any(PREVIEW_TOKEN in p for p in paths) or PREVIEW_TOKEN in disp:
        sig.append("preview_url")
    return sig


def parse_page_range(pages):
    """(first, last) from an `a-b` digit form ONLY; "absent" for nothing; "unparsed" for anything else."""
    if pages is None or not str(pages).strip():
        return "absent"
    m = _RANGE.fullmatch(str(pages))
    if not m or int(m.group(2)) < int(m.group(1)):
        return "unparsed"
    return int(m.group(1)), int(m.group(2))


def volume_check(page_count, record_pages):
    """Step 11: volume / article / unparsed / absent / no-page-count."""
    rng = parse_page_range(record_pages)
    if isinstance(rng, str):
        return rng
    if page_count is None:
        return "no-page-count"
    span = rng[1] - rng[0] + 1
    return "volume" if (page_count >= VOLUME_PAGES and span < VOLUME_PAGES) else "article"


def page_range_identity(page_count, record_pages):
    """Step 13 (T15): match / short / long, or why it could not be read. A fact, never a refusal."""
    rng = parse_page_range(record_pages)
    if isinstance(rng, str) or page_count is None:
        return rng if isinstance(rng, str) else "no-page-count"
    span = rng[1] - rng[0] + 1
    if span < PAGE_COUNT_MIN_SPAN:
        return "span-too-small"
    if page_count < span - PAGE_COUNT_SLACK:
        return "short"
    if page_count > span + PAGE_COUNT_SLACK:
        return "long"
    return "match"


def doi_position(texts, doi):
    """Step 12: first-pages / only-after / absent / no-doi — where the requested DOI is printed."""
    if not doi:
        return "no-doi"
    needle = re.sub(r"\s+", "", str(doi).strip().lower())
    hits = [i for i, t in enumerate(texts) if needle in re.sub(r"\s+", "", t.lower())]
    if not hits:
        return "absent"
    return "first-pages" if min(hits) < DOI_PAGES else "only-after"


_META = re.compile(rb"<meta\b[^>]*>", re.I)
_LINK = re.compile(rb"<link\b[^>]*>", re.I)
_ATTR = re.compile(rb"""([a-zA-Z_:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def _attrs(tag):
    return {m.group(1).lower(): (m.group(2) or m.group(3) or m.group(4) or b"") for m in _ATTR.finditer(tag)}


def landing_signals(data):
    """Does an HTML body carry a PDF pointer Stage C reads? `citation_pdf_url` by suffix, in `name` OR
    `property`, anywhere in the document (C2 / C2-RG), which also catches `bepress_citation_pdf_url` and
    `eprints.citation_pdf_url`; `eprints.document_url`; `link rel=alternate type=application/pdf`. Detection
    only — Stage C's extractor (builder-C2b) resolves the URL."""
    out = {"citation_pdf_url": False, "bepress": False, "eprints": False, "link_alternate_pdf": False}
    for tag in _META.findall(data or b""):
        a = _attrs(tag)
        key = (a.get(b"name") or a.get(b"property") or b"").decode("latin-1").lower()
        if not a.get(b"content"):
            continue
        if key.endswith("citation_pdf_url"):
            out["citation_pdf_url"] = True
            out["bepress"] = out["bepress"] or key.startswith("bepress_")
            out["eprints"] = out["eprints"] or key.startswith("eprints.")
        if key == "eprints.document_url":
            out["eprints"] = True
    for tag in _LINK.findall(data or b""):
        a = _attrs(tag)
        if b"alternate" in (a.get(b"rel") or b"").lower() and (a.get(b"type") or b"").lower() == b"application/pdf":
            out["link_alternate_pdf"] = True
    out["pdf_pointer"] = any(out.values())
    return out


def _strip_query(u):
    """A URL reduced to scheme, host, port and path: a terminal URL is often a SIGNED one (E20's carries an AWS
    session token), and the evidence is written to the ledger. No query and no fragment; no userinfo
    (`user:secret@host`) and no path parameter (`;jsessionid=...`) either — auditor-C1b round 3 F4, integrator-w2:
    each carried a planted secret through. The path is all the evidence signals read (`evidence_signals`)."""
    if not u:
        return u
    s = urlsplit(u)
    path = re.sub(r";[^/]*", "", s.path)
    if not s.scheme:
        return path
    host = s.hostname or ""
    host = f"[{host}]" if ":" in host else host
    try:
        port = f":{s.port}" if s.port else ""
    except ValueError:                  # a malformed port is not evidence
        port = ""
    return f"{s.scheme}://{host}{port}{path}"


#: The response headers the stub rules read (`x_els_status`; a preview named in Content-Disposition) and the two that
#: say what a body is and how long it claims to be — the four S4.5 decision D22 names. ONE home: the acceptance test's
#: evidence keeps them, and the LADDER records them itself on every attempt that was served bytes
#: (`run._record_result`, `detail.served_headers`), independent of this test (seam integrator-w2).
STUB_HEADERS = ("x-els-status", "content-disposition", "content-type", "content-length")


def served_headers(headers):
    """{lower-case name: value} of the STUB_HEADERS a response carried (absent ones left out)."""
    return {k: _header(headers, k) for k in STUB_HEADERS if _header(headers, k) is not None}


def evidence_of(headers, url, terminal_url):
    """What the stub detector read, in the shape the ledger keeps (the counters re-read it). Both URLs reduced by
    `_strip_query` (the requested one too: auditor-C1b round 3 F4)."""
    return {"headers": served_headers(headers), "url": _strip_query(url) or "",
            "terminal_url": _strip_query(terminal_url) or ""}


# ── the test ──────────────────────────────────────────────────────────────────────────────

def accept(data, *, headers=None, url=None, terminal_url=None, doi=None, record_pages=None,
           metadata_fetched=True, qpdf_runner=None):
    """The acceptance test, steps 1-13 of the module docstring. -> Verdict (never raises on bad bytes)."""
    v = Verdict()
    data = data or b""
    v.facts.update(served_bytes=len(data), served_sha256=hashlib.sha256(data).hexdigest(),
                   evidence=evidence_of(headers, url, terminal_url))
    # 1 unwrap (C18)
    if sniff(data) in ARCHIVE_KINDS:
        inner, how = unwrap(data)
        if inner is None:
            return v.refuse("unwrap", "compressed_or_archived_payload", how)
        data = inner
        v.facts["unwrapped"] = how
        v.step("unwrap", how)
    else:
        v.step("unwrap", "not-applicable")
    # 2 repair (C14) — BEFORE the magic: lstrip does not strip a byte-order mark
    off = 0
    # BEGIN guard: a PDF signature after leading bytes is repaired before the magic check
    off = repair_offset(data)
    # END guard: a PDF signature after leading bytes is repaired before the magic check
    if off:
        data = data[off:]
        v.facts["repaired_offset"] = off
    v.step("repair", f"offset {off}" if off else "none")
    # 3 magic (C1-RG a)
    # BEGIN guard: bytes without the PDF magic are refused with what they are
    if not magic_ok(data):
        if _looks_like_html(data):
            v.facts["landing"] = landing_signals(data)
            return v.refuse("magic", "html_response",
                            f"the {len(data)} bytes are an HTML page"
                            + ("; it carries a PDF pointer Stage C can follow" if v.facts["landing"]["pdf_pointer"]
                               else ""))
        if len(data) < MIN_PDF_BYTES:
            return v.refuse("magic", "too_small", f"{len(data)} bytes with no PDF magic, under the "
                                                  f"{MIN_PDF_BYTES}-byte floor")
        return v.refuse("magic", "missing_pdf_header", f"the {len(data)} bytes carry no %PDF magic "
                                                       f"in their first {REPAIR_WINDOW} bytes")
    # END guard: bytes without the PDF magic are refused with what they are
    v.step("magic", "pass")
    # 4 header (C1-RG c)
    if header_corrupt(data):
        return v.refuse("header", "corrupt_pdf_header", "the %PDF header has no d.d version or carries U+FFFD "
                                                        "(a binary file passed through a text decode)")
    v.step("header", "pass")
    # 5 floor (C1-RG b)
    # BEGIN guard: a PDF under the byte floor is refused too_small
    if len(data) < MIN_PDF_BYTES:
        return v.refuse("floor", "too_small", f"{len(data)} bytes, under the {MIN_PDF_BYTES}-byte floor")
    # END guard: a PDF under the byte floor is refused too_small
    v.step("floor", "pass")
    # 6 mime (C21)
    mime, source = mime_of(data)
    v.facts.update(mime=mime, mime_source=source)
    if mime != "application/pdf":
        return v.refuse("mime", "html_response" if mime == "text/html" else "missing_pdf_header",
                        f"{source} reads the bytes as {mime}")
    v.step("mime", f"pass ({source})")
    # 7 eof (C1-RG d)
    # BEGIN guard: a PDF with no %%EOF near its end is refused early_eof_with_trailing_payload
    if not eof_in_tail(data):
        return v.refuse("eof", "early_eof_with_trailing_payload",
                        f"no %%EOF in the last {EOF_TAIL} bytes of {len(data)}: the transfer stopped before the "
                        f"trailer, or a payload follows it")
    # END guard: a PDF with no %%EOF near its end is refused early_eof_with_trailing_payload
    v.step("eof", "pass")
    # 8 qpdf
    qnotes = []
    q = qpdf_check(data, qpdf_runner, qnotes)
    v.facts["qpdf"] = q
    v.facts["qpdf_checker"] = "injected runner" if qpdf_runner is not None else qpdf_checker()
    if qnotes:
        v.facts["qpdf_unchecked"] = qnotes
    if q == "damaged":
        return v.refuse("qpdf", "corrupt_pdf_header", "qpdf's check (exit 2): the file is damaged")
    v.step("qpdf", q)
    v.pdf = data
    v.facts["bytes"] = len(data)
    v.facts["sha256"] = hashlib.sha256(data).hexdigest()
    # 9 text
    texts, images, err = page_facts(data)
    if texts is None:
        v.facts["text_error"] = err
        v.step("text", "unreadable")
        return v
    v.facts["pages"] = len(texts)
    v.facts.update(text_facts(texts))
    v.facts["image_pages"] = len(image_pages_of(texts, images))
    v.step("text", "pass")
    # 10 stub (C16 + H2-RG + C19)
    sig = stub_signals(texts, headers=headers, urls=(url, terminal_url), images=images)
    v.facts["stub_signals"] = sig
    if sig:
        return v.refuse("stub", "stub_not_article", "a valid PDF that is not the article: " + ", ".join(sig))
    v.step("stub", "pass")
    v.facts["rests_on_metadata"] = False
    # BEGIN guard: a verdict never rests on metadata that could not be fetched
    # (guard 18: fetchpdf re-judged 706 good PDFs with metadata unavailable and destroyed 8, every DataCite-only
    # DOI among them — "no record" read as "wrong paper")
    if not metadata_fetched:
        v.facts["metadata"] = "unfetched"
        v.step("volume", "unfetched")
        v.step("cited", "unfetched")
        return v
    # END guard: a verdict never rests on metadata that could not be fetched
    v.facts["metadata"] = "fetched"
    # 11 volume (C17)
    vol = volume_check(len(texts), record_pages)
    v.facts["volume"] = vol
    if vol == "volume":
        v.facts["rests_on_metadata"] = True
        return v.refuse("volume", "volume_not_article",
                        f"{len(texts)} pages against a record page range of {record_pages}")
    v.step("volume", vol)
    # 12 cited (guard 4 / T14)
    pos = doi_position(texts, doi)
    v.facts["doi_position"] = pos
    if pos == "only-after":
        v.facts["rests_on_metadata"] = True
        return v.refuse("cited", "cited_document_not_this_article",
                        f"the requested DOI is printed only after page {DOI_PAGES}: a document that cites it")
    v.step("cited", pos)
    # 13 identity (T15) — recorded, never a refusal
    v.facts["page_range_identity"] = page_range_identity(len(texts), record_pages)
    v.step("identity", v.facts["page_range_identity"])
    return v


# ── store.pdf_shape's contract, and the quarantine label ──────────────────────────────────

def shape(data):
    """`store.pdf_shape` for its existing callers: the acceptance test's HEADER and TRAILER rules only (steps
    2, 3 and 7), answering in the old vocabulary. -> (shape, reason), shape in pdf / not-a-pdf / truncated-pdf.

    Only those rules, deliberately: the byte floor, the stub rule and the rest read things `pdf_shape`'s
    callers do not hand it (headers, the record), and the suite's one-page constructed PDFs are ~1.5 KB with
    no reference section — the floor and the stub rule would refuse every one of them. The full test runs
    where a caller can give it its context: `offer_to_bind`. The reason never quotes the bytes (a served
    error page can echo a request URL, key and all)."""
    data = data or b""
    if not quick_magic(data):
        return "not-a-pdf", (f"the {len(data)} bytes served do not begin with %PDF- (nor carry it after leading "
                             f"bytes in their first {REPAIR_WINDOW})"
                             + ("; they look like HTML" if _looks_like_html(data) else ""))
    if not eof_in_tail(data):
        return "truncated-pdf", (f"a %PDF- header and no %%EOF in the last {EOF_TAIL} bytes of {len(data)}: "
                                 f"the transfer stopped before the trailer")
    return "pdf", ""


def quarantine_label(sub_status):
    """The label a refused payload's quarantine NAME carries (a `quarantine.REASONS` word: the 0030 CHECK
    holds that list, and a new word would need a migration). The sub-status itself goes in the sidecar."""
    if sub_status == "early_eof_with_trailing_payload":
        return "truncated-pdf"
    if sub_status in ("html_response", "too_small", "missing_pdf_header", "corrupt_pdf_header",
                      "compressed_or_archived_payload"):
        return "not-a-pdf"
    return "bad-file"


#: The steps whose refusal is a HARD BYTE FAILURE — the bytes are not a PDF, are a corrupt one, or are an archive
#: holding none (S4.5 decision D17: "refusing only on hard byte failures (not a PDF, corrupt,
#: compressed-with-no-PDF)"). The floor, stub, volume and cited steps judge a PDF that opened; on the operator's
#: `--from-file` their refusal is RECORDED on the proposal for the second-session approver, not enforced (D17: "the
#: operator's judgement on identity is the approver's to confirm, not the test's to override"). Integrator-w2.
HARD_STEPS = ("unwrap", "magic", "header", "mime", "eof", "qpdf")


def failed_step(verdict):
    """-> the step a refusal failed at (the last step recorded `fail`), or None for an accepted verdict."""
    return next((name for name, outcome in reversed(verdict.steps) if outcome == "fail"), None)


def hard_byte_failure(verdict):
    """Is this verdict a refusal at one of HARD_STEPS?"""
    return verdict.verdict == "refuse" and failed_step(verdict) in HARD_STEPS


# ── the acceptance test, then the real bind ──────────────────────────────────────────────

def record_pages_of(conn, work_id):
    """The record's page string for a work (main first, else its latest version)."""
    row = conn.execute("SELECT pages FROM litkb.main_works WHERE work_id = %s", (work_id,)).fetchone()
    if row is None:
        row = conn.execute("SELECT pages FROM litkb.work_versions WHERE work_id = %s "
                           "ORDER BY created_at DESC LIMIT 1", (work_id,)).fetchone()
    return row[0] if row else None


def offer_to_bind(conn, ws, token, work, data, *, route, source_url, store, index, agent, session,
                  headers=None, terminal_url=None, record_pages=None, metadata_fetched=True, qpdf_runner=None,
                  copy_kind=None):
    """The ladder's landing: the acceptance test on the served bytes, then — only for bytes it accepted — the
    real bind path (`run.land_and_attach`) on the bytes it returned (unwrapped, header repaired). Refused bytes
    are KEPT: `run.quarantine_bytes` writes them into _quarantine/ with the sub-status in the sidecar.
    -> (status, detail); detail["acceptance"] is the verdict's summary (evidence included), which the caller
    records on the attempt row: the `stubs_bound` counter re-reads it. `copy_kind` is the article version the
    route knew, handed to the bind as it is (`run.land_and_attach`; seam integrator-w1: the ladder's landing
    is this function since the merge)."""
    from litkb.acquire import run

    if record_pages is None and work.get("work_id"):
        record_pages = record_pages_of(conn, work["work_id"])
    v = accept(data, headers=headers, url=source_url, terminal_url=terminal_url, doi=work.get("doi"),
               record_pages=record_pages, metadata_fetched=metadata_fetched, qpdf_runner=qpdf_runner)
    summ = v.summary()
    if v.verdict != "accept":
        label = quarantine_label(v.sub_status)
        detail = run.quarantine_bytes(store, work, data, label=label, status="bad-file", shape=label,
                                      reason=v.reason, route=route, source_url=source_url,
                                      sub_status=v.sub_status, acceptance=summ)
        detail.update(sub_status=v.sub_status, acceptance=summ)
        return "bad-file", detail
    status, detail = run.land_and_attach(conn, ws, token, work, v.pdf, route=route, source_url=source_url,
                                         store=store, index=index, agent=agent, session=session,
                                         copy_kind=copy_kind)
    detail["acceptance"] = summ
    return status, detail

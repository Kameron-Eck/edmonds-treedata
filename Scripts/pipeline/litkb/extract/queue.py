"""The extraction queue — lease, resume, guards (design §12.3-12.5; LITKB_WORKPLAN.md "### S4").

    litkb queue sweep   enqueue one stage-5 job per active file with no current run
    litkb queue work    claim -> heartbeat -> extract -> ingest + finish_job, ONE transaction
    litkb queue status  counts by state and refusal

The table and its functions are migration 0029 (``extraction_jobs``, ``extraction_job_leases``);
everything here runs as ``litkb_ingest`` through those functions.

THE OWNERSHIP GATE. A claim returns a lease TOKEN (only its hash is stored). The ingest transaction
ends with ``finish_job(job, token, …)``, which raises SQLSTATE ``LKL01`` unless that token is the
job's current, unsuperseded lease — so a worker that stalled past its lease and woke after another
worker reclaimed the job rolls its blocks back and lands nothing (:class:`LeaseLost`).

THE GUARDS (:func:`guard_file`), each FAIL-CLOSED into a ``refused`` job that is never claimable,
checked at ENQUEUE (``sweep``) and again at CLAIM (a job enqueued before a guard changed is still
refused): ``book`` (litkb-book-policy, also decided in SQL), ``bad-file`` (missing on disk, no
``%PDF-`` signature, sha256 ≠ ``files.sha256``), ``probe-error`` (the page count cannot be read),
``over-page-cap`` (more than ``probe.EXTRACT_PAGE_CAP`` pages, Kam ruling litkb-extract-page-cap) and
``scan-needs-ocr`` (an image page with OCR switched off).

SCAN ROUTING is per page: ANY image page makes the file OCR-routed — an image page being S4 run 3
decision D13's, ZERO native characters AND at least one raster image (``probe.image_pages``; its
docstring holds the measured basis) — never the stored page-1 ``has_text_layer`` flag (code survey
C8, data survey D2). An OCR-routed file is split into page-range jobs of at most :data:`OCR_CHUNK_PAGES`;
each range stores its own artifact, and the LAST range to finish assembles all of them into ONE run
in ONE transaction (design §12.5). Measured 2026-09-22 on a copy of Anderson 1957 (OCR, CUDA,
``pages=[3,5]``): Docling emits ABSOLUTE page numbers for a range — ``pages`` keys 3, 4, 5 and every
``prov.page_no`` in 3..5 — so the offset back to the file's own numbering is zero, and
:func:`assemble` REFUSES a range whose pages fall outside it rather than assuming that holds.

THE SCAN POST-CONDITION (:func:`scan_postcondition`): an OCR-routed file whose image pages ALL come
back with no text (:func:`ocr_read_nothing`) is refused ``scan-needs-ocr``, never finished ok —
WHEN IT IS A SCAN: its image pages outnumber its native-text pages (:func:`is_scan`, the orchestrator's
ruling on builder-A Q1, a definition rather than a tuned number). Measured on Anderson 1957's
recorded Docling artifacts (reconciled here, CPU): OCR off, its image pages (2-22 — page 1 is the
JSTOR cover, 160 native characters, a text page) carry 0 characters; OCR on, 40,923. A file that is
NOT a scan — a native paper whose one image page is a caption-less picture — is not refused: the run
finishes and its textless image pages are REPORTED in the run's metrics (``textless_image_pages``).
``scans_ocr_unrouted`` counts by the same :func:`is_scan`.

A DEAD JOB LEAVES A RECORD. At ``dead`` (``fail_job`` at the ceiling, or ``claim_jobs`` finding every
lease expired) migration 0029's ``_job_dead_run`` writes a ``failed`` extraction run at the job's own
run key, through 0017's ``open_extraction_run`` / ``finish_extraction_run``, with the job's last error
in its metrics (design §12.3; builder-A Q2). An extraction that produced no block fails as
:class:`ZeroContent`, by name, so the classifier can tell ``zero-content`` from an extractor error.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

from litkb.extract import ingest as ING
from litkb.extract import probe as P

STAGE = ING.STAGE
TOOL = ING.TOOL

#: Page-range size of an OCR job. SOURCE — S4 run 3 decision D3: the longest single OCR pass
#: MEASURED inside the 20 % VRAM rule is Anderson 1957, 22 image-only pages, 1,806 MiB / 44.1 %
#: (the VRAM table in ``litkb.extract.docling``); a longer range is unmeasured.
OCR_CHUNK_PAGES = 22

#: Lease length in seconds. SOURCE — the longest single-job wall-clock in the existing Docling and
#: GROBID metrics JSONL (code survey C5's files), measured 2026-09-22 by reading all four:
#: ``D:\\edmonds-pipeline\\litkb_derived\\hunt\\metrics_docling.jsonl`` line 2, Ouyang_2024, 32
#: pages, OCR on CPU, ``seconds`` 374.588 (the next longest anywhere is 76.54 s, the P5 bulk
#: Docling file, line 182). Rounded UP to the whole second. The heartbeat renews at half of it.
LEASE_SECONDS = 375

#: Every closed vocabulary here equals migration 0029's CHECK (qc/test_litkb_queue.py pins both).
STATES = ("queued", "leased", "staged", "done", "dead", "refused")
REFUSALS = ("over-page-cap", "book", "probe-error", "bad-file", "scan-needs-ocr")

#: SQLSTATE of a refused lease (migration 0029, ``_job_lease_current``).
LEASE_REFUSED = "LKL01"

#: ``LITKB_QUEUE_NO_OCR=1`` is ``--no-ocr``: an OCR-routed file is refused `scan-needs-ocr`.
NO_OCR_ENV = "LITKB_QUEUE_NO_OCR"
#: A directory the worker appends one JSON line per event to (``queue-trace.jsonl``): claim,
#: extract-start, commit, stage, refuse, fail. Read-only for everything else; the kill test waits on
#: it to kill the worker MID-BATCH instead of at a guessed moment.
TRACE_ENV = "LITKB_QUEUE_TRACE_DIR"


#: A TEST SEAM, honoured only against a worker database (``litkb_test*``) and refused against any
#: other: ``synthetic`` makes ``litkb queue work`` use ``queue_fire.SyntheticExtractor`` instead of
#: GROBID + Docling, so the kill test can kill a real subprocess mid-batch without a GPU.
TEST_EXTRACTOR_ENV = "LITKB_QUEUE_TEST_EXTRACTOR"


class LeaseLost(RuntimeError):
    """The database refused this worker's token (SQLSTATE LKL01): the lease is no longer its own."""


class AssemblyError(RuntimeError):
    """The page ranges of a file do not fit together into one document."""


class ExtractError(RuntimeError):
    """A tool failed on a job; the job goes back to the queue (``fail_job``)."""


class ZeroContent(ExtractError):
    """The extraction produced NO block at all. The job fails like any other (retried, ``dead`` at the
    ceiling — each retry reuses the recorded artifact, so it costs a reconcile, not a tool run), but
    its ``last_error`` begins with :data:`ZERO_CONTENT_ERROR`, which is how the readability classifier
    tells a file that produced no text (``zero-content``) from one an extractor failed on (which it
    leaves UNCLASSIFIED — S4 run 3, orchestrator ruling on builder-C item 1c)."""


#: The prefix ``work`` writes into ``last_error`` for :class:`ZeroContent` (``f"{type(e).__name__}: {e}"``).
ZERO_CONTENT_ERROR = "ZeroContent:"


# ── small shared pieces ─────────────────────────────────────────────────────────────────

def ocr_enabled(no_ocr=False):
    return not (no_ocr or os.environ.get(NO_OCR_ENV) == "1")


def run_key(file_id):
    """The stage-5 run key — hunt's and the bulk pass's, so an ok run either wrote is found here."""
    from litkb.extract import reconcile as R

    return ING.run_key(file_id, R.PIPELINE_VERSION, ING.CORPUS_PARAMS)


def literature_root(root=None):
    from litkb.acquire.store import LITERATURE_ROOT

    return Path(root or os.environ.get("LITKB_LITERATURE_ROOT") or LITERATURE_ROOT)


def derived_root(derived=None):
    """Where job artifacts go: ``references.DERIVED_ROOT`` (design §6's ``_derived``; §15.6 Open)."""
    from litkb.extract.references import DERIVED_ROOT

    return Path(derived or DERIVED_ROOT)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def write_atomic(path, data):
    """``.partial``, fsync, rename (design §12.4; the nightly-dump pattern). A leftover .partial is
    overwritten by the retry at the same path — never deleted by litkb."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def _sql(conn, query, params=()):
    """Execute, translating the lease refusal into :class:`LeaseLost`."""
    try:
        return conn.execute(query, params)
    except Exception as e:  # psycopg has no class for a custom SQLSTATE; read the code itself
        if getattr(e, "sqlstate", None) == LEASE_REFUSED:
            raise LeaseLost(str(e).splitlines()[0]) from e
        raise


def seam_extractor(dbname):
    """The :data:`TEST_EXTRACTOR_ENV` seam. -> an extractor, or None when the variable is unset.
    Raises when it is set against a database that is not a worker database."""
    spec = os.environ.get(TEST_EXTRACTOR_ENV)
    if not spec:
        return None
    from litkb.db import connect as c

    if not c.is_test_db(dbname or c.DB_MAIN):
        raise RuntimeError(f"{TEST_EXTRACTOR_ENV} is a test seam and is refused against {dbname or c.DB_MAIN!r}")
    from litkb.extract import queue_fire as F

    return F.extractor_from_spec(spec)


def connect(dbname=None):
    """The ingest connection: ``litkb`` through ``litkb.ingest.connect``, a worker database through
    its owner login + ``SET ROLE litkb_ingest`` — ONE rule, ``references_ingest.connect``'s."""
    from litkb.extract.references_ingest import connect as _connect

    return _connect(dbname)


def _trace(event, **kw):
    d = os.environ.get(TRACE_ENV)
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    line = json.dumps({"event": event, "at": time.time(), "pid": os.getpid(), **kw},
                      default=str, sort_keys=True)
    with open(os.path.join(d, "queue-trace.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


# ── the content digest (docs/SCHEMAS.md "litkb.extraction_jobs.blocks_digest") ──────────

def blocks_digest(rows):
    """sha256 over ``(page_no, reading_order, type, text)`` of every block, ordered by
    (page_no, reading_order): each block one line, ``json.dumps([page_no, reading_order, type,
    text or ""], ensure_ascii=False, separators=(",", ":"))``, lines joined by ``\\n``, UTF-8.
    JSON escaping makes the line boundary unambiguous whatever the text holds."""
    rows = sorted(((int(p), int(o), t, x or "") for p, o, t, x in rows), key=lambda r: (r[0], r[1]))
    body = "\n".join(json.dumps(list(r), ensure_ascii=False, separators=(",", ":")) for r in rows)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def run_rows(conn, run_id):
    return conn.execute("SELECT page_no, reading_order, type, text FROM litkb.blocks "
                        "WHERE run_id = %s", (run_id,)).fetchall()


def canonical_rows(canonical):
    return [(c.page, c.reading_order, c.db_type(), c.text) for c in canonical]


# ── the guards ──────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Facts:
    """What a guard decided about one file, with the probe facts it read."""

    refusal: str | None = None
    error: str | None = None
    pages: int | None = None
    page_chars: list | None = None
    route: str | None = None
    image_pages: list | None = None


def guard_file(path, sha256, work_type, *, ocr):
    """-> :class:`Facts`. FAIL CLOSED: anything that cannot be established is a refusal.

    Called at ENQUEUE (:func:`sweep`) and again at CLAIM (:func:`_recheck`). Order: the database
    fact first (no disk read for a book), then the bytes, then the probe, then the cap, then OCR."""
    # BEGIN guard: a book's file is never extracted
    if work_type == "book":
        return Facts("book", "the work is a book (litkb-book-policy: S4 never extracts a book)")
    # END guard: a book's file is never extracted
    # BEGIN guard: the bytes on disk are the bound file
    if not os.path.isfile(path):
        return Facts("bad-file", f"the bound file is not on disk at {path}")
    if not P.is_pdf_magic(path):
        return Facts("bad-file", "no %PDF- signature in the first 1,024 bytes")
    on_disk = sha256_file(path)
    if on_disk != sha256:
        return Facts("bad-file", f"sha256 on disk {on_disk[:12]}… is not files.sha256 {sha256[:12]}…")
    # END guard: the bytes on disk are the bound file
    try:
        pages, chars, probe_error = P.probe_pages(path), P.page_text_chars(path), None
        images = P.image_pages(chars, P.page_raster_images(path))
    except P.ProbeError as e:
        pages, chars, images, probe_error = None, None, None, str(e)
    # BEGIN guard: a page count that cannot be read is probe-error
    if probe_error is not None:
        return Facts("probe-error", f"the page probe failed: {probe_error}")
    # END guard: a page count that cannot be read is probe-error
    route = "ocr" if images else "native"
    facts = Facts(None, None, pages, chars, route, images or [])
    # BEGIN guard: a file over the extraction page cap is never started
    if pages is not None and pages > P.EXTRACT_PAGE_CAP:
        facts.refusal = "over-page-cap"
        facts.error = f"{pages} pages > EXTRACT_PAGE_CAP {P.EXTRACT_PAGE_CAP} (litkb-extract-page-cap)"
        return facts
    # END guard: a file over the extraction page cap is never started
    # BEGIN guard: an OCR-routed file with OCR off is refused, never started
    if route == "ocr" and not ocr:
        facts.refusal = "scan-needs-ocr"
        facts.error = (f"{len(facts.image_pages)} of {pages} pages are image pages (no native "
                       f"text, a raster image) and OCR is off")
        return facts
    # END guard: an OCR-routed file with OCR off is refused, never started
    return facts


def chunk_ranges(pages, size=OCR_CHUNK_PAGES):
    """[(1, 22), (23, 44), …] covering 1..pages."""
    return [(lo, min(lo + size - 1, pages)) for lo in range(1, pages + 1, size)]


def ocr_chars(image_pages, rows):
    """Normalised characters the extraction put on the IMAGE pages. ``rows`` are ``(page_no, text)``.
    An image page has no native text (decision D13), so every character here is OCR's."""
    from litkb.admit.resolver import _norm_text

    img = set(image_pages or [])
    return sum(len(_norm_text(t or "")) for p, t in rows if p in img)


def ocr_read_nothing(image_pages, rows):
    """True when the file HAS image pages and the extraction put no text on any of them. The scan
    post-condition refuses that — for a SCAN (:func:`is_scan`); ``scans_ocr_unrouted`` counts it."""
    return bool(image_pages) and ocr_chars(image_pages, rows) == 0


def native_text_pages(page_chars):
    """How many pages carry native text (more than zero native characters, ``probe.page_text_chars``)."""
    return sum(1 for n in (page_chars or []) if (n or 0) > 0)


def is_scan(page_chars, image_pages):
    """THE SCAN DEFINITION (S4 run 3, orchestrator ruling on builder-A Q1): a file is a scan when its
    image pages OUTNUMBER its native-text pages — a scan by the majority of its pages. A definition,
    not a tuned number: nothing here was fitted to a file. A native paper with one caption-less
    picture page (1 image page against its text pages) is NOT a scan; Anderson 1957 (21 image pages,
    1 native-text JSTOR cover) is. Blank pages (no text, no raster) count on neither side.
    The scan post-condition and ``scans_ocr_unrouted`` both read it, so the two cannot disagree."""
    return len(image_pages or []) > native_text_pages(page_chars)


def textless_image_pages(image_pages, rows):
    """The image pages the extraction put no text on, in page order. ``rows`` are ``(page_no, text)``."""
    from litkb.admit.resolver import _norm_text

    covered = {p for p, t in rows if _norm_text(t or "")}
    return [p for p in (image_pages or []) if p not in covered]


def scan_postcondition(route, image_pages, canonical, page_chars=None):
    """-> (refusal, detail) or (None, None).

    Refuses when OCR returned no text on ANY image page AND the file is a scan (:func:`is_scan`).
    A file that is not a scan finishes: its textless image pages are REPORTED in the run's metrics
    (``textless_image_pages``), never a refusal of the whole file."""
    if route != "ocr":
        return None, None
    if not ocr_read_nothing(image_pages, [(c.page, c.text) for c in canonical]):
        return None, None
    # BEGIN guard: only a SCAN is refused — image pages outnumber the native-text pages
    # Without this clause a native paper whose one image page is a caption-less picture would be
    # refused whole because OCR found nothing on that picture (builder-A Q1).
    if not is_scan(page_chars, image_pages):
        return None, None
    # END guard: only a SCAN is refused — image pages outnumber the native-text pages
    return ("scan-needs-ocr",
            f"OCR-routed, a scan ({len(image_pages)} image pages > {native_text_pages(page_chars)} "
            f"native-text pages), and its image pages came back with no text")


# ── the population and the sweep ───────────────────────────────────────────────────────

_MAIN_POP = """
SELECT f.file_id, f.sha256, f.rel_path, w.type
  FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id = f.work_id
 WHERE f.status = 'active' AND f.current_run_id IS NULL"""

_WS_POP = """
SELECT f.file_id, f.sha256, f.rel_path, w.type
  FROM litkb.ws_files f JOIN litkb.ws_works w
    ON w.work_id = f.work_id AND w.view_workstream_id = f.view_workstream_id
 WHERE f.view_workstream_id = %s AND f.status = 'active' AND f.current_run_id IS NULL"""


def _workstream_id(conn, ws):
    row = conn.execute("SELECT id FROM litkb.workstreams WHERE id::text = %s OR slug = %s",
                       (str(ws), str(ws))).fetchone()
    if row is None:
        raise ValueError(f"no workstream {ws!r}")
    return row[0]


#: `--redo` (S2's Maiti_2022): the named files whose CURRENT run sits at a key that is not the stage-5
#: run key of today — their current run is not the extraction the queue would make now.
_REDO_POP = """
SELECT f.file_id, f.sha256, f.rel_path, w.type, r.stage, r.tool, r.tool_version, r.params_hash,
       r.pipeline_version
  FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id = f.work_id
  JOIN litkb.extraction_runs r ON r.id = f.current_run_id
 WHERE f.status = 'active' AND f.file_id = ANY (%s::uuid[])"""


def at_current_key(key, stage, tool, tool_version, params_hash, pipeline_version):
    return (key["stage"], key["tool"], key["tool_version"], key["params_hash"],
            key["pipeline_version"]) == (stage, tool, tool_version, params_hash, pipeline_version)


def population(conn, workstreams=(), files=None, redo=False):
    """Active files with no current run: main's, plus each named workstream's view. One row per
    file; ``files`` (file ids) keeps only those. ``redo`` adds the named ``files`` whose current
    run is at an OLDER key — never one whose current run is at today's key."""
    rows = {r[0]: r for r in conn.execute(_MAIN_POP).fetchall()}
    if redo:
        if not files:
            raise ValueError("--redo re-extracts NAMED files only: pass --file")
        for fid, sha, rel, typ, *run in conn.execute(_REDO_POP, ([str(f) for f in files],)).fetchall():
            # BEGIN guard: --redo never re-extracts a file whose current run is at today's key
            if at_current_key(run_key(fid), *run):
                continue
            # END guard: --redo never re-extracts a file whose current run is at today's key
            rows.setdefault(fid, (fid, sha, rel, typ))
    for ws in workstreams:
        for r in conn.execute(_WS_POP, (_workstream_id(conn, ws),)).fetchall():
            rows.setdefault(r[0], r)
    if files is not None:
        keep = {str(f) for f in files}
        rows = {k: v for k, v in rows.items() if str(k) in keep}
    return sorted(rows.values(), key=lambda r: r[2])


def _jobs_at_key(conn, file_id, key):
    return conn.execute(
        "SELECT page_start, state, refusal FROM litkb.extraction_jobs WHERE file_id = %(file_id)s "
        "AND stage = %(stage)s AND tool = %(tool)s AND tool_version = %(tool_version)s "
        "AND params_hash = %(params_hash)s AND pipeline_version = %(pipeline_version)s", key).fetchall()


_ENQUEUE = ("SELECT job_id, inserted FROM litkb.enqueue_extraction(%s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s)")


def enqueue(conn, file_id, lo, hi, facts, refusal=None, error=None):
    k = run_key(file_id)
    return conn.execute(_ENQUEUE, (file_id, k["stage"], k["tool"], k["tool_version"],
                                   k["params_hash"], k["pipeline_version"], lo, hi, facts.route,
                                   facts.pages, facts.page_chars, facts.image_pages, refusal,
                                   error)).fetchone()


def sweep(conn, root=None, *, workstreams=(), ocr=None, files=None, redo=False, actor=None):
    """Enqueue every file of :func:`population` that has no job at the stage-5 run key.

    Idempotent: the UNIQUE key makes a second sweep insert nothing.

    REOPEN (auditor-A F1). A file whose every job at the key is ``refused`` — at ENQUEUE or at CLAIM,
    never on the RESULT — is guarded again, now. When the guard passes, the refusal no longer holds:
    each refused job whose range the file still needs goes back to ``queued`` through
    ``litkb.reopen_job`` (one audit row each: ``actor``, when, why), and a range with no job at all
    (a file refused whole-file with OCR off, now OCR-routed into ranges) is enqueued. A refusal the
    guard still gives is left alone, and so is any file with a job in any other state or a refusal
    made on the result (the scan post-condition: OCR ran and read nothing).

    ``redo`` (with ``files``): see :func:`population`."""
    ocr = ocr_enabled() if ocr is None else ocr
    root = literature_root(root)
    actor = actor or f"sweep@{socket.gethostname()}:{os.getpid()}"
    out = {"files": 0, "enqueued": 0, "refused": {}, "already": 0, "reopened": 0, "ocr": ocr,
           "redo": bool(redo)}
    for file_id, sha, rel_path, work_type in population(conn, workstreams, files, redo):
        out["files"] += 1
        existing = _refused_at_key(conn, file_id, run_key(file_id))
        # BEGIN guard: only a file whose EVERY job was refused before a result is re-guarded
        reopenable = bool(existing) and all(st == "refused" and stage in ("enqueue", "claim")
                                            for _id, _lo, _hi, st, _rf, stage in existing)
        # END guard: only a file whose EVERY job was refused before a result is re-guarded
        if existing and not reopenable:
            out["already"] += 1
            continue
        facts = guard_file(root / rel_path.replace("\\", "/"), sha, work_type, ocr=ocr)
        refusal, error = facts.refusal, facts.error
        ranges = (chunk_ranges(facts.pages) if refusal is None and facts.route == "ocr"
                  else [(None, None)])
        if existing:
            # BEGIN guard: a refusal that still holds is never reopened
            if refusal is not None:
                out["already"] += 1
                continue
            # END guard: a refusal that still holds is never reopened
            with conn.transaction():
                have = {(lo, hi): (jid, rf) for jid, lo, hi, _st, rf, _stage in existing}
                for lo, hi in ranges:
                    if (lo, hi) in have:
                        jid, rf = have[(lo, hi)]
                        why = (f"the sweep's guard now passes (ocr={'on' if ocr else 'off'}, "
                               f"route {facts.route}, {facts.pages} pages): {rf} no longer holds")
                        if conn.execute("SELECT litkb.reopen_job(%s, %s, %s, %s, %s, %s, %s, %s)",
                                        (jid, rf, actor, why, facts.route, facts.pages,
                                         facts.page_chars, facts.image_pages)).fetchone()[0]:
                            out["reopened"] += 1
                    else:
                        _job, inserted = enqueue(conn, file_id, lo, hi, facts)
                        out["enqueued"] += int(bool(inserted))
            continue
        with conn.transaction():          # a file's ranges land together or not at all
            for lo, hi in ranges:
                _job, inserted = enqueue(conn, file_id, lo, hi, facts, refusal, error)
                if inserted:
                    out["enqueued"] += 1
        if refusal:
            out["refused"][refusal] = out["refused"].get(refusal, 0) + 1
    return out


def _refused_at_key(conn, file_id, key):
    """Every job of the file at ``key``: (id, page_start, page_end, state, refusal, refusal_stage)."""
    return conn.execute(
        "SELECT id, page_start, page_end, state, refusal, refusal_stage FROM litkb.extraction_jobs "
        "WHERE file_id = %(file_id)s AND stage = %(stage)s AND tool = %(tool)s "
        "AND tool_version = %(tool_version)s AND params_hash = %(params_hash)s "
        "AND pipeline_version = %(pipeline_version)s ORDER BY page_start NULLS FIRST", key).fetchall()


# ── claiming, and the heartbeat ─────────────────────────────────────────────────────────

@dataclasses.dataclass
class Claim:
    job_id: object
    token: str
    lease_seq: int
    file_id: object
    page_start: int | None
    page_end: int | None
    attempts: int
    route: str | None
    pages: int | None
    page_chars: list | None
    image_pages: list | None
    lease_expires_at: object

    @property
    def label(self):
        return "whole" if self.page_start is None else f"p{self.page_start:03d}-{self.page_end:03d}"


def claim(conn, worker, n=1, lease=LEASE_SECONDS, files=None):
    rows = conn.execute("SELECT * FROM litkb.claim_jobs(%s, %s, %s, %s)",
                        (worker, n, lease, list(files) if files else None)).fetchall()
    return [Claim(*r) for r in rows]


def renew(conn, c):
    return _sql(conn, "SELECT litkb.renew_lease(%s, %s)", (c.job_id, c.token)).fetchone()[0]


class Heartbeat(threading.Thread):
    """Renews the lease at half its length on its OWN connection, for as long as the job runs.

    A refused renewal (LKL01) sets :attr:`lost` and stops: the lease is someone else's now, and the
    finish that follows will be refused by the same check."""

    def __init__(self, connect_fn, c, lease):
        super().__init__(daemon=True)
        self.connect_fn, self.c, self.interval = connect_fn, c, max(lease / 2.0, 0.5)
        self._stop_ev = threading.Event()
        self.lost = False
        self.renewals = 0
        self.errors = []

    def run(self):
        try:
            conn = self.connect_fn()
        except Exception as e:  # noqa: BLE001 — a heartbeat that cannot connect is reported, not fatal
            self.errors.append(f"{type(e).__name__}: {e}")
            return
        try:
            while not self._stop_ev.wait(self.interval):
                try:
                    renew(conn, self.c)
                    self.renewals += 1
                except LeaseLost:
                    self.lost = True
                    return
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"{type(e).__name__}: {e}")
        finally:
            conn.close()

    def stop(self):
        self._stop_ev.set()
        self.join(timeout=30)


# ── artifacts ───────────────────────────────────────────────────────────────────────────

def artifact_dir(sha256, derived=None, file_id=None, key=None):
    """``<derived>/<sha256>/<stage>/<tool>@<version>_<params>/`` (design §12.4)."""
    k = key or run_key(file_id)
    return derived_root(derived) / sha256 / STAGE / f"{k['tool']}@{k['tool_version']}_{k['params_hash']}"


def write_manifest(out_dir, prefix, files, meta):
    """The job's artifact: a manifest naming each tool output and its sha256. -> (path, sha256)."""
    doc = dict(meta, files={name: (None if p is None else {"name": Path(p).name, "sha256": sha256_file(p)})
                            for name, p in files.items()})
    data = json.dumps(doc, indent=1, sort_keys=True, default=str).encode("utf-8")
    path = write_atomic(Path(out_dir) / f"{prefix}.manifest.json", data)
    return str(path), hashlib.sha256(data).hexdigest()


def read_manifest(path, sha256):
    """The manifest at ``path`` iff its bytes and every file it names still hash as recorded, else None."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if hashlib.sha256(data).hexdigest() != sha256:
        return None
    m = json.loads(data)
    base = Path(path).parent
    for name, f in (m.get("files") or {}).items():
        if f is None:
            continue
        p = base / f["name"]
        if not p.is_file() or sha256_file(p) != f["sha256"]:
            return None
        f["path"] = str(p)
    return m


def load_artifacts(manifest):
    """-> (tei bytes or None, docling dict or None) from a verified manifest."""
    from litkb.extract import docling as D

    files = manifest.get("files") or {}
    tei = Path(files["tei"]["path"]).read_bytes() if files.get("tei") else None
    doc = D.load(files["docling"]["path"]) if files.get("docling") else None
    return tei, doc


# ── assembling page ranges into one document ────────────────────────────────────────────

_ARRAYS = ("texts", "tables", "pictures", "groups", "key_value_items", "form_items")
_REF = re.compile(r"^#/(%s)/(\d+)$" % "|".join(_ARRAYS))


def _prov_pages(doc):
    out = set()
    for arr in _ARRAYS:
        for item in doc.get(arr) or []:
            for p in item.get("prov") or []:
                out.add(int(p["page_no"]))
    return out


def assemble(parts, pages):
    """[(lo, hi, docling_doc)] -> ONE docling document for the whole file (design §12.5).

    Refuses (:class:`AssemblyError`) unless the ranges tile 1..pages exactly, in order, and every
    page a range's document names lies inside that range. Items are appended range by range; every
    internal ``#/<array>/<i>`` pointer is shifted by the items already appended; body and furniture
    children are concatenated in page order. Page numbers are NOT shifted: Docling emits absolute
    page numbers for a page range (measured, module docstring)."""
    parts = sorted(parts, key=lambda t: t[0])
    # BEGIN guard: page ranges assemble only when they tile the file and stay inside themselves
    expect = 1
    for lo, hi, doc in parts:
        if lo != expect:
            raise AssemblyError(f"page ranges do not tile the file: expected a range from {expect}, got {lo}-{hi}")
        stray = sorted(p for p in (_prov_pages(doc) | {int(k) for k in (doc.get("pages") or {})})
                       if not lo <= p <= hi)
        if stray:
            raise AssemblyError(f"range {lo}-{hi} names pages outside itself: {stray[:5]}")
        expect = hi + 1
    if expect != pages + 1:
        raise AssemblyError(f"page ranges end at {expect - 1}, the file has {pages} pages")
    # END guard: page ranges assemble only when they tile the file and stay inside themselves
    out = copy.deepcopy(parts[0][2])
    for arr in _ARRAYS:
        out[arr] = []
    out["pages"] = {}
    for root in ("body", "furniture"):
        if isinstance(out.get(root), dict):
            out[root]["children"] = []

    for _lo, _hi, doc in parts:
        offs = {arr: len(out[arr]) for arr in _ARRAYS}

        def shift(o):
            if isinstance(o, dict):
                return {k: shift(v) for k, v in o.items()}
            if isinstance(o, list):
                return [shift(v) for v in o]
            if isinstance(o, str):
                m = _REF.match(o)
                if m:
                    return f"#/{m.group(1)}/{int(m.group(2)) + offs[m.group(1)]}"
            return o

        for arr in _ARRAYS:
            out[arr].extend(shift(copy.deepcopy(doc.get(arr) or [])))
        for root in ("body", "furniture"):
            if isinstance(doc.get(root), dict) and isinstance(out.get(root), dict):
                out[root]["children"].extend(shift(copy.deepcopy(doc[root].get("children") or [])))
        out["pages"].update(copy.deepcopy(doc.get("pages") or {}))
    return out


# ── the extractors ──────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Job:
    """What an extractor is handed for one claim."""

    pdf: str
    out_dir: Path
    prefix: str                  # "<label>.s<lease_seq>" — a stale worker never overwrites a live one's files
    page_range: tuple | None     # (lo, hi) or None for the whole file
    route: str


class _VramSampler(threading.Thread):
    """Whole-card VRAM in use, 1 Hz from `nvidia-smi` — the method P5 measured the 20 % rule with
    (docling.py's VRAM table: "1 Hz nvidia-smi"). The rule is written against the card, so the card
    is what is sampled, display included; the idle baseline is recorded beside the peak."""

    def __init__(self, interval=1.0):
        super().__init__(daemon=True)
        self.interval = interval
        self._stop_ev = threading.Event()
        self.baseline = self.read()
        self.peak = self.baseline

    @staticmethod
    def read():
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout
            return int(out.strip().splitlines()[0])
        except Exception:  # noqa: BLE001 — no card, no driver: no measurement, never a guess
            return None

    def run(self):
        while not self._stop_ev.wait(self.interval):
            v = self.read()
            if v is not None and (self.peak is None or v > self.peak):
                self.peak = v

    def stop(self):
        self._stop_ev.set()
        self.join(timeout=15)
        v = self.read()
        if v is not None and (self.peak is None or v > self.peak):
            self.peak = v
        return self.peak


class ToolExtractor:
    """GROBID (native files only) + Docling, for one job. GROBID is started once, lazily, held up
    for the whole batch, and NEVER stopped here: hunt stops it after every file (code survey C2), a
    queue must not, and this worker never stops a GROBID it did not start — nor one it did."""

    def __init__(self, device, python, *, ocr, grobid=True):
        self.device, self.python, self.ocr, self.grobid = device, python, ocr, grobid
        self._grobid_up = None
        self.grobid_error = None

    def _ensure_grobid(self):
        if self._grobid_up is None:
            from litkb.extract import grobid as G

            try:
                # the ONE ownership rule (G.GrobidHold): a unit systemd says is running is waited
                # for, never (re)started under its owner; and this worker never closes the hold,
                # so it stops no GROBID at all
                self._grobid_up = bool(G.GrobidHold(wait=300).ensure())
            except Exception as e:  # noqa: BLE001 — GrobidUnavailable included
                self._grobid_up, self.grobid_error = False, f"{type(e).__name__}: {e}"
            if not self._grobid_up and not self.grobid_error:
                self.grobid_error = "GROBID did not come up under WSL"
        return self._grobid_up

    def __call__(self, job):
        from litkb.extract import docling as D
        from litkb.extract import grobid as G

        m = {"device": self.device, "interpreter": self.python}
        files = {"tei": None, "docling": None}
        # scans skip GROBID (hunt's rule): a page-range job is an OCR file's range
        if job.route == "native" and self.grobid:
            t0 = time.monotonic()
            if self._ensure_grobid():
                try:
                    tei, _gm = G.extract(job.pdf, concurrency=1, sample_rss=False)
                    tei = tei if isinstance(tei, bytes) else str(tei).encode("utf-8")
                    files["tei"] = str(write_atomic(job.out_dir / f"{job.prefix}.tei.xml", tei))
                except G.GrobidError as e:
                    m["grobid_error"] = f"{type(e).__name__}: {e}"[:300]
            else:
                m["grobid_error"] = self.grobid_error
            m["grobid_seconds"] = round(time.monotonic() - t0, 3)
        run_ocr = bool(self.ocr and job.route == "ocr")
        out = job.out_dir / f"{job.prefix}.docling.json"
        sampler = _VramSampler() if self.device == "cuda" else None
        if sampler is not None:
            sampler.start()
        try:
            rows = D.run([{"pdf": job.pdf, "out": str(out),
                           "pages": list(job.page_range) if job.page_range else None}],
                         str(job.out_dir / "metrics_docling.jsonl"), python=self.python,
                         ocr=run_ocr, formula=False, device=self.device, cwd=worker_cwd())
        finally:
            peak = sampler.stop() if sampler is not None else None
        row = rows[0] if rows else {}
        m.update(ocr=run_ocr, ocr_engine=row.get("ocr_engine"), docling_seconds=row.get("seconds"),
                 peak_rss_bytes=row.get("peak_rss_bytes"), pages=row.get("pages"),
                 converter_build_seconds=row.get("converter_build_seconds"),
                 docling_status=row.get("status"),
                 peak_vram_mib=peak, vram_baseline_mib=sampler.baseline if sampler else None)
        if row.get("status") != "ok" or not out.is_file():
            raise ExtractError(f"docling produced no artifact: {row.get('error') or 'no metrics row'}")
        files["docling"] = str(out)
        return files, m


def worker_cwd():
    """A SHORT working directory for the Docling worker process (auditor-A F3).

    The artifact directory — ``<derived>/<sha256>/5-reconcile/<tool>@<version>_<params>`` — was the
    cwd, and under a long ``--derived`` root it passed the Windows current-directory limit: every job
    died ``NotADirectoryError: [WinError 267]`` and went dead. The worker needs no cwd of its own
    (every path it is handed is absolute), only a NEUTRAL one: ``docling_worker``'s CWD IS
    LOAD-BEARING note — no ``secrets`` directory may shadow the stdlib on its path. So a dedicated
    empty directory under the system temp: short, and holding nothing but the worker's jobs file."""
    import tempfile

    d = os.path.join(tempfile.gettempdir(), "litkb-docling-cwd")
    os.makedirs(d, exist_ok=True)
    return d


# ── the worker ──────────────────────────────────────────────────────────────────────────

def _file_row(conn, file_id):
    """(sha256, rel_path, work type) — main's version when there is one, else the latest proposal."""
    row = conn.execute(
        "SELECT f.sha256, f.rel_path, w.type FROM litkb.main_files f "
        "JOIN litkb.main_works w ON w.work_id = f.work_id WHERE f.file_id = %s", (file_id,)).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT f.sha256, fv.rel_path, (SELECT wv.type FROM litkb.work_versions wv "
        "  WHERE wv.work_id = fv.work_id ORDER BY wv.version_no DESC LIMIT 1) "
        "FROM litkb.files f JOIN litkb.file_versions fv ON fv.file_id = f.id "
        "WHERE f.id = %s ORDER BY fv.version_no DESC LIMIT 1", (file_id,)).fetchone()


def _job_row(conn, job_id):
    return conn.execute("SELECT artifact_path, artifact_sha256, metrics FROM litkb.extraction_jobs "
                        "WHERE id = %s", (job_id,)).fetchone()


def _recheck(conn, c, pdf, sha, work_type, ocr):
    """The CLAIM-time guard: the same checks as the sweep, on the file as it is now."""
    facts = guard_file(pdf, sha, work_type, ocr=ocr)
    why, detail = facts.refusal, facts.error
    if why:
        _sql(conn, "SELECT litkb.refuse_job(%s, %s, %s, %s, 'claim')", (c.job_id, c.token, why, detail))
        _trace("refuse", job=c.job_id, refusal=why, at_claim=True)
        return why
    return None


def _finish_hook(c, job_metrics):
    def hook(conn, run_id):
        digest = blocks_digest(run_rows(conn, run_id))
        from psycopg.types.json import Jsonb

        _sql(conn, "SELECT litkb.finish_job(%s, %s, %s, %s, %s)",
             (c.job_id, c.token, run_id, digest, Jsonb(job_metrics)))
    return hook


def _run_metrics(parts, prep_seconds, pages, jobs):
    secs = sum(float(p.get("extract_seconds") or 0) for p in parts) + prep_seconds
    rss = [p.get("peak_rss_bytes") for p in parts if p.get("peak_rss_bytes")]
    vram = [p.get("peak_vram_mib") for p in parts if p.get("peak_vram_mib") is not None]
    base = [p.get("vram_baseline_mib") for p in parts if p.get("vram_baseline_mib") is not None]
    first = parts[0] if parts else {}
    return {"seconds": round(secs, 3), "pages": pages,
            "pages_per_s": round(pages / secs, 4) if secs > 0 and pages else None,
            "peak_rss_bytes": max(rss) if rss else None,
            "peak_vram_mib": max(vram) if vram else None,
            "vram_baseline_mib": min(base) if base else None,
            "device": first.get("device"), "interpreter": first.get("interpreter"),
            "ocr": any(p.get("ocr") for p in parts),
            "ocr_engine": next((p.get("ocr_engine") for p in parts if p.get("ocr_engine")), None),
            "grobid_error": next((p.get("grobid_error") for p in parts if p.get("grobid_error")), None),
            "reconcile_seconds": round(prep_seconds, 3),
            "jobs": jobs, "attempts": sum(j["attempts"] for j in jobs),
            "chunks": [[j["page_start"], j["page_end"]] for j in jobs if j["page_start"] is not None],
            "queue": "litkb.extract.queue"}


def _ingest(conn, c, file_id, pdf, tei, doc, parts, jobs, route, image_pages, pages):
    """Reconcile, check the scan post-condition, ingest + finish_job in ONE transaction."""
    t0 = time.monotonic()
    prep = ING.prepare(pdf, tei, doc)
    prep_s = time.monotonic() - t0
    # BEGIN guard: an OCR-routed file whose image pages come back empty is never finished ok
    why, detail = scan_postcondition(route, image_pages, prep["canonical"], c.page_chars)
    if why:
        _sql(conn, "SELECT litkb.refuse_job(%s, %s, %s, %s, 'result')", (c.job_id, c.token, why, detail))
        _trace("refuse", job=c.job_id, refusal=why, at_claim=False)
        return "refused"
    # END guard: an OCR-routed file whose image pages come back empty is never finished ok
    # BEGIN guard: an extraction that produced no block fails as ZeroContent, by name
    # Without it ingest_file raises 0017's "has no blocks and cannot be ok" and the job dies on an
    # anonymous error, which the classifier must leave UNCLASSIFIED; named, the dead job is the
    # evidence for `zero-content` (litkb.readability's queue step).
    if not prep["canonical"]:
        raise ZeroContent(f"zero-content: the extraction produced no block on any of {pages} pages")
    # END guard: an extraction that produced no block fails as ZeroContent, by name
    from litkb.extract import reconcile as R

    stats = dict(prep["stats"])
    stats.update(_run_metrics(parts, prep_s, pages, jobs))
    rows = [(x.page, x.text) for x in prep["canonical"]]
    stats.update(image_pages=len(image_pages or []),
                 ocr_chars_on_image_pages=ocr_chars(image_pages, rows),
                 # REPORTED, never a refusal: the image pages of a file that is not a scan that came
                 # back with no text (scan_postcondition's rule, S4 run 3 builder-C item 1a)
                 textless_image_pages=textless_image_pages(image_pages, rows))
    res = ING.ingest_file(conn, file_id, prep["canonical"], prep["disagreements"], stats,
                          pages=prep["pages"], artifact_path=parts[-1].get("artifact_path"),
                          host="local", pipeline_version=R.PIPELINE_VERSION,
                          params=ING.CORPUS_PARAMS,
                          before_commit=_finish_hook(c, {"lease_seq": c.lease_seq,
                                                         "attempts": c.attempts}))
    if not res["inserted"]:
        # an ok run appeared at the key between the claim's check and this ingest
        return _finish_existing(conn, c, res["run_id"])
    return "done"


def _finish_existing(conn, c, run_id):
    from psycopg.types.json import Jsonb

    _sql(conn, "SELECT litkb.finish_job(%s, %s, %s, %s, %s)",
         (c.job_id, c.token, run_id, blocks_digest(run_rows(conn, run_id)),
          Jsonb({"skipped": "an ok run already stood at the run key", "lease_seq": c.lease_seq})))
    return "done-existing"


def _extract_or_reuse(conn, c, pdf, sha, extractor, derived, file_id):
    """The job's verified manifest: reused when recorded and intact (§12.4), else produced now."""
    from psycopg.types.json import Jsonb

    path, recorded, _m = _job_row(conn, c.job_id)
    if path and recorded:
        man = read_manifest(path, recorded)
        if man is not None:
            man["artifact_path"] = path
            return man, True
    out_dir = artifact_dir(sha, derived, file_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    job = Job(pdf=str(pdf), out_dir=out_dir, prefix=f"{c.label}.s{c.lease_seq}",
              page_range=(c.page_start, c.page_end) if c.page_start is not None else None,
              route=c.route or "native")
    _trace("extract-start", job=c.job_id, label=c.label, lease_seq=c.lease_seq)
    t0 = time.monotonic()
    files, m = extractor(job)
    m["extract_seconds"] = round(time.monotonic() - t0, 3)
    meta = {"file_sha256": sha, "file_id": str(file_id), "range": list(job.page_range) if job.page_range else None,
            "lease_seq": c.lease_seq, "job_id": str(c.job_id), "metrics": m}
    mpath, msha = write_manifest(out_dir, job.prefix, files, meta)
    _sql(conn, "SELECT litkb.record_artifact(%s, %s, %s, %s, %s)",
         (c.job_id, c.token, mpath, msha, Jsonb(m)))
    man = read_manifest(mpath, msha)
    man["artifact_path"] = mpath
    return man, False


def _chunk_parts(conn, file_id, key):
    """Every range of the file with its recorded, VERIFIED manifest, in page order."""
    rows = conn.execute(
        "SELECT id, page_start, page_end, attempts, artifact_path, artifact_sha256 FROM litkb.extraction_jobs "
        "WHERE file_id = %(file_id)s AND stage = %(stage)s AND tool = %(tool)s "
        "AND tool_version = %(tool_version)s AND params_hash = %(params_hash)s "
        "AND pipeline_version = %(pipeline_version)s AND page_start IS NOT NULL ORDER BY page_start",
        dict(key, file_id=file_id)).fetchall()
    out = []
    for jid, lo, hi, att, path, sha in rows:
        man = read_manifest(path, sha) if path and sha else None
        if man is None:
            raise AssemblyError(f"range {lo}-{hi} (job {jid}) has no intact recorded artifact")
        man["artifact_path"] = path
        out.append((jid, lo, hi, att, man))
    return out


def run_job(conn, c, *, root, extractor, derived, ocr):
    """One claimed job, start to finish. -> outcome word."""
    sha, rel_path, work_type = _file_row(conn, c.file_id)
    pdf = literature_root(root) / rel_path.replace("\\", "/")
    if _recheck(conn, c, pdf, sha, work_type, ocr):
        return "refused"
    existing, status = ING.already_ingested(conn, c.file_id, key=run_key(c.file_id))
    if existing and status == "ok":
        return _finish_existing(conn, c, existing)
    man, _reused = _extract_or_reuse(conn, c, pdf, sha, extractor, derived, c.file_id)
    job_entry = {"job_id": str(c.job_id), "page_start": c.page_start, "page_end": c.page_end,
                 "attempts": c.attempts, "lease_seq": c.lease_seq}
    if c.page_start is None:
        tei, doc = load_artifacts(man)
        part = dict(man.get("metrics") or {}, artifact_path=man["artifact_path"])
        return _ingest(conn, c, c.file_id, str(pdf), tei, doc, [part], [job_entry],
                       c.route, c.image_pages, c.pages)
    last = _sql(conn, "SELECT litkb.stage_chunk(%s, %s)", (c.job_id, c.token)).fetchone()[0]
    if not last:
        _trace("stage", job=c.job_id, label=c.label)
        return "staged"
    ranges = _chunk_parts(conn, c.file_id, run_key(c.file_id))
    docs = [(lo, hi, load_artifacts(m)[1]) for _j, lo, hi, _a, m in ranges]
    doc = assemble(docs, c.pages)
    parts = [dict(m.get("metrics") or {}, artifact_path=m["artifact_path"]) for *_r, m in ranges]
    jobs = [{"job_id": str(j), "page_start": lo, "page_end": hi, "attempts": a,
             "extract_seconds": (m.get("metrics") or {}).get("extract_seconds"),
             "peak_vram_mib": (m.get("metrics") or {}).get("peak_vram_mib")}
            for j, lo, hi, a, m in ranges]
    return _ingest(conn, c, c.file_id, str(pdf), None, doc, parts, jobs, c.route, c.image_pages, c.pages)


def work(connect_fn, root=None, *, worker=None, max_jobs=None, lease=LEASE_SECONDS, ocr=None,
         extractor=None, device="auto", python=None, derived=None, files=None):
    """Claim -> heartbeat -> extract -> ingest + finish, one job at a time, until the queue is empty
    or ``max_jobs`` claims were made. ``connect_fn()`` opens an ingest connection (the heartbeat
    takes its own). -> the report dict.

    The device and interpreter are resolved ONCE, before anything is claimed (S4 run 3 decision
    D4): a pair that cannot run raises ``DeviceUnavailable`` and no job is touched."""
    ocr = ocr_enabled() if ocr is None else ocr
    if extractor is None:
        from litkb.extract import docling as D

        dev, py = D.device_pair(device, python)
        extractor = ToolExtractor(dev, py, ocr=ocr)
    worker = worker or f"{socket.gethostname()}:{os.getpid()}"
    report = {"worker": worker, "claimed": 0, "outcomes": {}, "jobs": [], "ocr": ocr, "lease": lease,
              "device": getattr(extractor, "device", None), "interpreter": getattr(extractor, "python", None)}
    conn = connect_fn()
    try:
        while max_jobs is None or report["claimed"] < max_jobs:
            got = claim(conn, worker, 1, lease, files)
            if not got:
                break
            c = got[0]
            report["claimed"] += 1
            _trace("claim", job=c.job_id, label=c.label, attempts=c.attempts, lease_seq=c.lease_seq)
            hb = Heartbeat(connect_fn, c, lease)
            hb.start()
            error = None
            try:
                outcome = run_job(conn, c, root=root, extractor=extractor, derived=derived, ocr=ocr)
            except LeaseLost as e:
                outcome, error = "lease-lost", str(e)
            except Exception as e:  # noqa: BLE001 — a failed job is recorded and the batch goes on
                error = f"{type(e).__name__}: {e}"[:2000]
                try:
                    outcome = "failed:" + _sql(conn, "SELECT litkb.fail_job(%s, %s, %s)",
                                               (c.job_id, c.token, error)).fetchone()[0]
                except LeaseLost:
                    outcome = "lease-lost"
            finally:
                hb.stop()
            if outcome in ("done", "done-existing", "staged"):
                _trace("commit", job=c.job_id, outcome=outcome)
            elif outcome.startswith("failed") or outcome == "lease-lost":
                _trace("fail", job=c.job_id, outcome=outcome, error=error)
            report["outcomes"][outcome] = report["outcomes"].get(outcome, 0) + 1
            report["jobs"].append({"job_id": str(c.job_id), "range": c.label, "attempts": c.attempts,
                                   "outcome": outcome, "error": error, "renewals": hb.renewals,
                                   "heartbeat_lost": hb.lost})
    finally:
        conn.close()
    return report


# ── visibility ──────────────────────────────────────────────────────────────────────────

def status(conn):
    """Counts by state and refusal, and pages still to do (a range counts its own pages)."""
    by_state = dict(conn.execute("SELECT state, count(*) FROM litkb.extraction_jobs GROUP BY 1").fetchall())
    by_refusal = dict(conn.execute("SELECT refusal, count(*) FROM litkb.extraction_jobs "
                                   "WHERE state = 'refused' GROUP BY 1").fetchall())
    remaining = conn.execute(
        "SELECT coalesce(sum(CASE WHEN page_start IS NULL THEN pages ELSE page_end - page_start + 1 END), 0) "
        "FROM litkb.extraction_jobs WHERE state IN ('queued', 'leased', 'staged')").fetchone()[0]
    return {"by_state": {s: by_state.get(s, 0) for s in STATES},
            "by_refusal": {r: by_refusal.get(r, 0) for r in REFUSALS},
            "pages_remaining": int(remaining), "files": conn.execute(
                "SELECT count(DISTINCT file_id) FROM litkb.extraction_jobs").fetchone()[0]}


# ── the S4 counters (plan "### S4" (b)); every one reads the database, a reader login suffices ──

def stale_leases(conn):
    """Leased jobs whose lease expired and that nobody reclaimed."""
    return conn.execute("SELECT count(*) FROM litkb.extraction_jobs "
                        "WHERE state = 'leased' AND lease_expires_at < clock_timestamp()").fetchone()[0]


def mutated_leases_accepted(conn):
    """Done jobs finished by a claim that was not their current one: a `finished` lease row that was
    SUPERSEDED (a reclaim, or a refusal of the whole file while it was leased — the book guard at
    claim, refuse_job's siblings), or that a LATER CLAIM of the same job followed. The ownership gate
    keeps this 0.

    Both clauses are LOAD-BEARING, each with its own known-bad in qc/test_litkb_queue.py. The
    later-claim clause is what c2 fires (a reclaimed lease). The `superseded_at` clause alone sees a
    job that DIED at the attempt ceiling: claim_jobs supersedes its expired lease and marks it `dead`
    with NO later claim and no refusal, so a stale holder's finish — were the gate gone — lands on it
    with nothing else to show (auditor-C re-check, measured on w3; my round-2 claim that the clause
    was unreachable was wrong: the refusal CHECK only covers a sibling cut off by a whole-file
    refusal). `reopen_job` gives it a second such path. The former third clause,
    ``l.seq <> j.lease_seq``, was removed: ``lease_seq`` only moves in claim_jobs, which inserts that
    claim's lease row in the same statement, and the history is append-only, so ``lease_seq > l.seq``
    IS a later row."""
    return conn.execute(
        "SELECT count(DISTINCT j.id) FROM litkb.extraction_jobs j "
        "JOIN litkb.extraction_job_leases l ON l.job_id = j.id AND l.outcome = 'finished' "
        "WHERE j.state = 'done' AND (l.superseded_at IS NOT NULL "
        "  OR EXISTS (SELECT 1 FROM litkb.extraction_job_leases l2 WHERE l2.job_id = j.id AND l2.seq > l.seq))"
    ).fetchone()[0]


def books_extracted(conn, workstreams=()):
    """FILES of a `type='book'` work carrying at least one block, in any run. A work is a book by
    main's version OR by its version in any of ``workstreams`` (the plan's (b): "all workstreams in
    the manifest, not main only"; auditor-C N5) — a workstream-only book is still a book."""
    return conn.execute(
        "WITH books AS (SELECT work_id FROM litkb.main_works WHERE type = 'book' "
        # BEGIN guard: a book in a manifest workstream counts as a book
        "  UNION SELECT work_id FROM litkb.ws_works "
        "   WHERE view_workstream_id = ANY (%s::uuid[]) AND type = 'book'"
        # END guard: a book in a manifest workstream counts as a book
        ") SELECT count(DISTINCT fv.file_id) FROM books w "
        "JOIN litkb.file_versions fv ON fv.work_id = w.work_id "
        "WHERE EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id = fv.file_id)",
        ([str(w) for w in workstreams],)).fetchone()[0]


def over_cap_bound(conn):
    """FILES with more pages than ``probe.EXTRACT_PAGE_CAP`` — by the bind's ``file_versions.pages``
    or the queue's probe (``extraction_jobs.pages``), whichever says so — carrying any block."""
    return conn.execute(
        "SELECT count(*) FROM litkb.files f WHERE EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id = f.id) "
        "AND greatest((SELECT max(fv.pages) FROM litkb.file_versions fv WHERE fv.file_id = f.id), "
        "             (SELECT max(j.pages) FROM litkb.extraction_jobs j WHERE j.file_id = f.id)) > %s",
        (P.EXTRACT_PAGE_CAP,)).fetchone()[0]


def scans_ocr_unrouted(conn):
    """OCR-routed FILES (a stage-5 job with route `ocr`) that are SCANS (:func:`is_scan`, the scan
    post-condition's own definition, from the job's recorded ``page_chars`` and ``image_pages``) whose
    CURRENT run carries no text on any of their image pages (:func:`ocr_read_nothing`)."""
    n = 0
    files = conn.execute(
        "SELECT DISTINCT ON (j.file_id) j.file_id, j.image_pages, j.page_chars, f.current_run_id "
        "FROM litkb.extraction_jobs j JOIN litkb.files f ON f.id = j.file_id "
        "WHERE j.route = 'ocr' AND j.image_pages IS NOT NULL AND f.current_run_id IS NOT NULL "
        "ORDER BY j.file_id, j.enqueued_at").fetchall()
    for _fid, images, chars, run in files:
        # BEGIN guard: scans_ocr_unrouted counts only a SCAN, by the post-condition's own definition
        if not is_scan(list(chars or []), list(images)):
            continue
        # END guard: scans_ocr_unrouted counts only a SCAN, by the post-condition's own definition
        rows = conn.execute("SELECT page_no, text FROM litkb.blocks WHERE run_id = %s", (run,)).fetchall()
        if ocr_read_nothing(list(images), rows):
            n += 1
    return n


def _done_runs(conn, resumed_only):
    """{run_id: (file_id, [job rows])} for current runs the queue finished."""
    rows = conn.execute(
        "SELECT j.run_id, j.file_id, j.id, j.page_start, j.page_end, j.attempts, j.artifact_path, "
        "j.artifact_sha256, j.blocks_digest FROM litkb.extraction_jobs j "
        "JOIN litkb.files f ON f.id = j.file_id AND f.current_run_id = j.run_id "
        "WHERE j.state = 'done' ORDER BY j.run_id, j.page_start NULLS FIRST").fetchall()
    runs = {}
    for r in rows:
        runs.setdefault(r[0], (r[1], []))[1].append(r)
    if resumed_only:
        runs = {k: v for k, v in runs.items() if any(j[5] > 1 for j in v[1])}
    return runs


def reference_blocks(conn, run_id, root=None):
    """The blocks a CLEAN run produces from the stored artifacts of ``run_id``'s jobs — reconcile
    again, on the CPU, no GPU, no tool run (the cold-session reference of
    ``resumed_content_hash_mismatches``). -> [(page_no, reading_order, type, text)], or None when an
    artifact is missing or no longer hashes as recorded."""
    fid, jobs = _done_runs(conn, False).get(run_id, (None, []))
    if not jobs:
        return None
    sha, rel_path, _t = _file_row(conn, fid)
    pdf = literature_root(root) / rel_path.replace("\\", "/")
    if not pdf.is_file() or sha256_file(pdf) != sha:
        return None
    mans = []
    for j in jobs:
        m = read_manifest(j[6], j[7]) if j[6] and j[7] else None
        if m is None:
            return None
        mans.append((j[3], j[4], m))
    if mans[0][0] is None:
        tei, doc = load_artifacts(mans[0][2])
    else:
        tei, doc = None, assemble([(lo, hi, load_artifacts(m)[1]) for lo, hi, m in mans], mans[-1][1])
    return canonical_rows(ING.prepare(str(pdf), tei, doc)["canonical"])


def resumed_content_hash_mismatches(conn, root=None):
    """Runs finished by a job with attempts > 1 whose committed ``blocks_digest`` differs from the
    digest of (a) the blocks the database holds for the run, or (b) the reference recomputed from
    the stored artifacts (:func:`reference_blocks`); an unrecomputable reference counts as a
    mismatch — a resumed run nobody can check is not a checked one."""
    n = 0
    for run_id, (_fid, jobs) in _done_runs(conn, True).items():
        recorded = {j[8] for j in jobs}
        ref = reference_blocks(conn, run_id, root)
        if (len(recorded) != 1 or ref is None or blocks_digest(ref) not in recorded
                or blocks_digest(run_rows(conn, run_id)) not in recorded):
            n += 1
    return n


def duplicate_blocks(conn, root=None):
    """Blocks of the queue's current runs that should not be there. Two legs:

    1. every run: blocks beyond the first at one (page_no, reading_order) — a position held twice;
    2. runs a RESUMED job finished (attempts > 1): for each (page_no, text), the blocks beyond the
       count the clean reference produces (:func:`reference_blocks`) — a region re-ingested.

    Why leg 2 is measured against the reference and not as a bare (page_no, text) repeat: the live
    corpus's current runs legitimately repeat a string on a page 16,295 times (4,619 groups over 169
    runs, mostly 1-4 character table cells and labels; read 2026-09-22 as litkb_reader), so a bare
    repeat count would be nonzero on correct extractions and could never be held at 0."""
    runs = _done_runs(conn, False)
    n = 0
    for run_id in runs:
        n += conn.execute("SELECT count(*) - count(DISTINCT (page_no, reading_order)) FROM litkb.blocks "
                          "WHERE run_id = %s", (run_id,)).fetchone()[0]
    for run_id in _done_runs(conn, True):
        ref = reference_blocks(conn, run_id, root)
        if ref is None:
            continue           # counted by resumed_content_hash_mismatches, not here
        want = {}
        for p, _o, _t, x in ref:
            want[(p, x or "")] = want.get((p, x or ""), 0) + 1
        got = {}
        for p, _o, _t, x in run_rows(conn, run_id):
            got[(p, x or "")] = got.get((p, x or ""), 0) + 1
        n += sum(max(0, v - want.get(k, 0)) for k, v in got.items())
    return n


def counters(conn, root=None, workstreams=()):
    """The gated S4 queue counters. ``workstreams`` (the manifest's) reach every counter that reads a
    WORK's version (only books_extracted does: the others read files, jobs and runs, which are
    workstream-agnostic identity rows)."""
    return {"stale_leases": stale_leases(conn), "duplicate_blocks": duplicate_blocks(conn, root),
            "resumed_content_hash_mismatches": resumed_content_hash_mismatches(conn, root),
            "books_extracted": books_extracted(conn, workstreams), "over_cap_bound": over_cap_bound(conn),
            "scans_ocr_unrouted": scans_ocr_unrouted(conn),
            "mutated_leases_accepted": mutated_leases_accepted(conn)}

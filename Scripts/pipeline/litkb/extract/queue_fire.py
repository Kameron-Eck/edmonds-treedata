"""Known-bad fixtures and FIRE functions for the extraction queue's S4 counters. WORKER DATABASES ONLY.

CLAUDE.md §3.4c: a gate counts only once it has been shown to FIRE on a known-bad input. Each
``fire_*`` below runs its known-bad twice on a worker database (``litkb_test*`` — the live ``litkb``
is refused before anything is written):

* ``guarded`` — with every guard in place; the counter it names must read 0;
* ``mutated`` — with that guard switched off IN THIS PROCESS (the Python guard wrapped, the SQL guard
  block removed by ``CREATE OR REPLACE`` from ``pg_get_functiondef`` and restored from the same text
  afterwards); the counter must read 1.

Every one takes ``conn`` — the worker database's OWNER login (``litkb_test``: it writes the
fixture works and files, and it is the only login that may replace a function) — and ``workdir``,
a scratch directory that becomes the literature root AND the artifact root, so nothing is written
under ``Literture\\`` or ``litkb_derived\\``. They return plain dicts; ``qc/test_litkb_queue.py``
asserts them, and the acceptance's ``readability`` subcommand is meant to re-fire them cold.

The fixtures are labelled: CONSTRUCTED (a hand-written PDF, or a synthetic Docling document) or
REAL (a copy of a corpus PDF, a recorded Docling artifact). Nothing here reads the corpus except by
copying a named file.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from litkb.extract import probe as P
from litkb.extract import queue as Q

CORPUS = Path(os.environ.get("LITKB_LITERATURE_ROOT") or r"D:\edmonds-pipeline\Literture")
#: REAL: the 1957 scan the plan names for the OCR-off known-bad (c5), and its recorded Docling
#: artifacts (2026-09-15, `D:\edmonds-pipeline\_tmp\litkb_docling`): layout WITHOUT OCR on CUDA
#: (`__gpu-t4`) and WITH OCR on CUDA (`__gpu-ocr`), both over pages 1-22.
ANDERSON = CORPUS / "Validation" / "Anderson_1957_statistical-inference-about-markov.pdf"
DOCLING_TMP = Path(r"D:\edmonds-pipeline\_tmp\litkb_docling")
ANDERSON_NO_OCR = DOCLING_TMP / "Anderson_1957__gpu-t4.docling.json"
ANDERSON_OCR = DOCLING_TMP / "Anderson_1957__gpu-ocr.docling.json"


# ── CONSTRUCTED PDFs ────────────────────────────────────────────────────────────────────

_LINE = "The quick brown fox jumps over the lazy dog while the queue keeps its lease."


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def constructed_pdf(path, pages, *, text=True, raster=None, note="", scan_pages=()):
    """CONSTRUCTED: a hand-written PDF of ``pages`` US-letter pages, Helvetica, one xref.

    ``text=True`` puts four lines of prose on every page (the file routes ``native``).
    ``text=False`` leaves the text layer empty; with ``raster`` (default: ``not text``) each page
    also draws one 8x8 grey raster image over the whole page — an IMAGE page by decision D13 (zero
    native characters AND a raster image), so the file routes ``ocr``; ``raster=False`` makes the
    pages truly BLANK (neither), which D13 does NOT route to OCR. ``scan_pages`` (1-based) turns
    those pages of a text file into image pages — a mixed document. ``note`` goes into a trailing
    comment, so two otherwise identical fixtures have different bytes and different file rows."""
    raster = (not text) if raster is None else raster
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            4: (b"<< /Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceGray "
                b"/BitsPerComponent 8 /Length 64 >>\nstream\n" + bytes(range(64, 128)) + b"\nendstream")}
    kids = []
    for i in range(pages):
        pn, cn = 5 + 2 * i, 6 + 2 * i
        kids.append(f"{pn} 0 R")
        scan = (i + 1) in scan_pages or (not text and raster)
        if text and (i + 1) not in scan_pages:
            lines = [f"Page {i + 1}. {_LINE}"] * 4
            body = "BT /F1 10 Tf 72 720 Td 14 TL " + " ".join(f"({_esc(ln)}) Tj T*" for ln in lines) + " ET"
        elif scan:
            body = "q 612 0 0 792 0 0 cm /Im1 Do Q"
        else:
            body = ""
        data = body.encode("latin-1")
        objs[pn] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    b"/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 4 0 R >> >> /Contents "
                    + f"{cn} 0 R".encode() + b" >>")
        objs[cn] = b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream"
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>".encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for n in sorted(objs):
        offsets[n] = len(out)
        out += f"{n} 0 obj\n".encode() + objs[n] + b"\nendobj\n"
    xref = len(out)
    size = max(objs) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for n in range(1, size):
        out += f"{offsets[n]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    if note:
        out += f"% {note}\n".encode()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(bytes(out))
    return Path(path)


def corrupt_pdf(path, note=""):
    """CONSTRUCTED: a ``%PDF-1.4`` signature over 2 KB of deterministic noise — the shape
    ``docling_worker._page_count`` was measured to refuse (2026-09-15). The page probe cannot open it."""
    noise = b"".join(hashlib.sha256(f"{note}:{i}".encode()).digest() for i in range(64))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(b"%PDF-1.4\n" + noise)
    return Path(path)


def real_copy(src, dest, note=""):
    """REAL: a byte copy of a corpus PDF. ``note`` appends one PDF comment line after ``%%EOF`` — the
    pages are untouched, but the bytes (so the file row) differ; used where a known-bad needs the
    same real document twice in one database."""
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    if note:
        with open(dest, "ab") as fh:
            fh.write(f"\n% {note}\n".encode())
    return Path(dest)


# ── extractors that are not GROBID + Docling ────────────────────────────────────────────

def _page_sizes(pdf):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        out = []
        # each page closed before the next is opened: a page left for the garbage collector
        # can be finalised while doc.close() iterates the document's kids, and pypdfium2 5.13
        # then raises 'Set changed size during iteration' (seen once, 2026-09-22)
        for i in range(len(doc)):
            page = doc[i]
            try:
                out.append(page.get_size())
            finally:
                page.close()
        return out
    finally:
        doc.close()


def synthetic_doc(pdf, page_range=None):
    """CONSTRUCTED: a Docling-shaped document with ONE body text item per page of the range, in
    Docling's own conventions (BOTTOMLEFT boxes, absolute page numbers, ``#/texts/<i>`` refs)."""
    sizes = _page_sizes(pdf)
    lo, hi = page_range or (1, len(sizes))
    texts, pages = [], {}
    for p in range(lo, hi + 1):
        w, h = sizes[p - 1]
        t = f"Synthetic region on page {p}: a deterministic stand-in for a tool's reading."
        i = len(texts)
        texts.append({"self_ref": f"#/texts/{i}", "parent": {"$ref": "#/body"}, "children": [],
                      "content_layer": "body", "label": "text", "orig": t, "text": t,
                      "prov": [{"page_no": p, "charspan": [0, len(t)],
                                "bbox": {"l": 72.0, "t": h - 60.0, "r": w - 72.0, "b": h - 200.0,
                                         "coord_origin": "BOTTOMLEFT"}}]})
        pages[str(p)] = {"page_no": p, "size": {"width": w, "height": h}}
    return {"schema_name": "DoclingDocument", "version": "1.5.0", "name": Path(pdf).stem,
            "body": {"self_ref": "#/body", "children": [{"$ref": t["self_ref"]} for t in texts],
                     "content_layer": "body", "name": "_root_", "label": "unspecified"},
            "furniture": {"self_ref": "#/furniture", "children": [], "content_layer": "furniture",
                          "name": "_root_", "label": "unspecified"},
            "groups": [], "texts": texts, "pictures": [], "tables": [], "key_value_items": [],
            "form_items": [], "pages": pages}


class SyntheticExtractor:
    """CONSTRUCTED. Writes :func:`synthetic_doc` as the job's Docling artifact; no GROBID, no GPU.
    ``delay`` seconds of sleep per job give the kill test a window in which to kill a worker;
    ``silent_pages`` are pages the tool reads NOTHING on (an OCR pass that found no text)."""

    device, python = "synthetic", None

    def __init__(self, delay=0.0, silent_pages=()):
        self.delay = float(delay)
        self.silent_pages = set(silent_pages)

    def __call__(self, job):
        if self.delay:
            time.sleep(self.delay)
        out = job.out_dir / f"{job.prefix}.docling.json"
        doc = synthetic_doc(job.pdf, job.page_range)
        if self.silent_pages:
            keep = [t for t in doc["texts"] if t["prov"][0]["page_no"] not in self.silent_pages]
            for i, t in enumerate(keep):
                t["self_ref"] = f"#/texts/{i}"
            doc["texts"] = keep
            doc["body"]["children"] = [{"$ref": t["self_ref"]} for t in keep]
        Q.write_atomic(out, json.dumps(doc, sort_keys=True).encode("utf-8"))
        return {"tei": None, "docling": str(out)}, {"device": "synthetic", "interpreter": None,
                                                    "ocr": job.route == "ocr", "ocr_engine": None}


class ReplayExtractor:
    """REAL artifacts, replayed: ``paths`` maps a page range (``(lo, hi)``, or ``None`` for the
    whole file) to a Docling JSON a real run recorded. ``ocr`` says whether that run used OCR."""

    python = None

    def __init__(self, paths, *, ocr, device="replay"):
        self.paths, self.ocr, self.device = paths, ocr, device

    def __call__(self, job):
        src = self.paths[tuple(job.page_range) if job.page_range else None]
        out = Q.write_atomic(job.out_dir / f"{job.prefix}.docling.json", Path(src).read_bytes())
        return {"tei": None, "docling": str(out)}, {"device": self.device, "interpreter": None,
                                                    "ocr": self.ocr, "replayed_from": str(src)}


def extractor_from_spec(spec):
    """``synthetic`` or ``synthetic:delay=<seconds>`` (the :data:`queue.TEST_EXTRACTOR_ENV` seam)."""
    name, _, arg = spec.partition(":")
    if name != "synthetic":
        raise ValueError(f"unknown test extractor {spec!r}")
    kw = dict(a.split("=", 1) for a in arg.split(",") if a)
    return SyntheticExtractor(delay=float(kw.get("delay", 0)))


# ── fixture rows (the P1 harness's own writes, as the owner login) ──────────────────────

def refuse_live(conn):
    db = conn.execute("SELECT current_database()").fetchone()[0]
    from litkb.db import connect as c

    if not c.is_test_db(db):
        raise RuntimeError(f"queue_fire runs on a worker database only, never on {db!r}")
    return db


def open_ws(conn):
    return conn.execute(
        "SELECT workstream_id FROM litkb.open_workstream(%s, 'work/test', NULL, 'queue fire', NULL)",
        (f"qf-{uuid.uuid4().hex[:12]}",)).fetchone()[0]


def add_work(conn, ws, work_type="article"):
    from psycopg.types.json import Jsonb

    key = f"Queue_2020_{uuid.uuid4().hex[:8]}-fixture"
    return conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, "
        "'setup', 'setup')",
        (Jsonb({"key": key}),
         Jsonb({"type": work_type, "title": f"Queue fixture {uuid.uuid4().hex}", "authors": []}),
         ws)).fetchone()[0]


def add_file(conn, ws, work_id, pdf, root, pages=None):
    """A main file row for ``pdf`` (which must lie under ``root``), sha256 from its bytes."""
    from psycopg.types.json import Jsonb

    rel = Path(pdf).resolve().relative_to(Path(root).resolve()).as_posix()
    fields = {"work_id": str(work_id), "rel_path": rel, "status": "active"}
    if pages is not None:
        fields["pages"] = pages
    return conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, "
        "'setup', 'setup')", (Jsonb({"sha256": Q.sha256_file(pdf)}), Jsonb(fields), ws)).fetchone()[0]


def ingest_conn(conn):
    return Q.connect(refuse_live(conn))


def file_jobs(conn, file_id):
    return conn.execute("SELECT state, refusal, attempts, page_start, run_id FROM litkb.extraction_jobs "
                        "WHERE file_id = %s ORDER BY page_start NULLS FIRST", (file_id,)).fetchall()


def blocks_of(conn, file_id):
    return conn.execute("SELECT count(*) FROM litkb.blocks WHERE file_id = %s", (file_id,)).fetchone()[0]


def sweep_and_work(conn, root, files, *, ocr=True, extractor=None, lease=Q.LEASE_SECONDS):
    k = ingest_conn(conn)
    try:
        swept = Q.sweep(k, root, ocr=ocr, files=files)
    finally:
        k.close()
    db = refuse_live(conn)
    worked = Q.work(lambda: Q.connect(db), root, ocr=ocr, extractor=extractor or SyntheticExtractor(),
                    derived=Path(root) / "_derived", lease=lease, files=files)
    return swept, worked


# ── switching a guard off, in this process only ─────────────────────────────────────────

@contextlib.contextmanager
def python_guard_off(*refusals):
    """``queue.guard_file`` with the named refusals dropped (the facts it read are kept)."""
    original = Q.guard_file

    def wrapped(*a, **kw):
        facts = original(*a, **kw)
        if facts.refusal in refusals:
            facts.refusal, facts.error = None, None
        return facts

    Q.guard_file = wrapped
    try:
        yield
    finally:
        Q.guard_file = original


@contextlib.contextmanager
def attr_off(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def function_source(conn, signature):
    return conn.execute("SELECT pg_get_functiondef(%s::regprocedure)", (signature,)).fetchone()[0]


def without_block(src, marker):
    """``src`` with the lines strictly between ``-- BEGIN <marker>`` and ``-- END <marker>`` removed."""
    lines = src.splitlines(keepends=True)
    bi = [i for i, ln in enumerate(lines) if f"BEGIN {marker}" in ln]
    ei = [i for i, ln in enumerate(lines) if f"END {marker}" in ln]
    if len(bi) != 1 or len(ei) != 1 or ei[0] <= bi[0] + 1:
        raise RuntimeError(f"guard markers {marker!r} not found exactly once")
    return "".join(lines[:bi[0] + 1] + lines[ei[0]:])


@contextlib.contextmanager
def sql_guard_off(conn, signature, marker):
    """``CREATE OR REPLACE`` ``signature`` without its guard block; the original text is restored on
    exit, and the restore is checked against the text read before."""
    refuse_live(conn)
    src = function_source(conn, signature)
    conn.execute(without_block(src, marker))
    try:
        yield
    finally:
        conn.execute(src)
        if function_source(conn, signature) != src:
            raise RuntimeError(f"{signature} was not restored byte-for-byte")


def _salt():
    """A per-call salt for a CONSTRUCTED fixture's trailing comment (and a REAL copy's): `files.sha256` is
    UNIQUE, so a fire whose bytes were the same on every call could run ONCE per database — a second
    `--fire` in the same worker database collided on `files_sha256_key` (measured 2026-09-22, builder-C).
    The comment follows `%%EOF`: no page, no text and no count changes."""
    return uuid.uuid4().hex


# ── the fire functions ──────────────────────────────────────────────────────────────────

def fire_cap(conn, workdir):
    """(c3) CONSTRUCTED: ``EXTRACT_PAGE_CAP + 1`` blank pages (no text, no raster: under decision D13
    a native file, so the mutated arm is ONE whole-file job). Guarded -> refused `over-page-cap`,
    never claimed; the cap guard off -> it is extracted -> ``over_cap_bound`` 1."""
    refuse_live(conn)
    root = Path(workdir)
    ws = open_ws(conn)
    out = {"baseline": {"over_cap_bound": Q.over_cap_bound(conn)}}
    for arm in ("guarded", "mutated"):
        pdf = constructed_pdf(root / "Validation" / f"Cap_{arm}.pdf", P.EXTRACT_PAGE_CAP + 1,
                              text=False, raster=False, note=f"fire_cap {arm} {_salt()}")
        fid = add_file(conn, ws, add_work(conn, ws), pdf, root)
        guard = python_guard_off("over-page-cap") if arm == "mutated" else contextlib.nullcontext()
        with guard:
            swept, worked = sweep_and_work(conn, root, [fid])
        out[arm] = {"jobs": file_jobs(conn, fid), "claimed": worked["claimed"],
                    "blocks": blocks_of(conn, fid), "over_cap_bound": Q.over_cap_bound(conn)}
    return out


def fire_book(conn, workdir):
    """(c6) a ``type='book'`` work with a file (CONSTRUCTED native PDF). Guarded -> refused `book`;
    every book guard off (Python, and both SQL blocks) -> a block lands -> ``books_extracted`` 1."""
    refuse_live(conn)
    root = Path(workdir)
    ws = open_ws(conn)
    out = {"baseline": {"books_extracted": Q.books_extracted(conn)}}
    for arm in ("guarded", "mutated"):
        pdf = constructed_pdf(root / "Validation" / f"Book_{arm}.pdf", 3, note=f"fire_book {arm} {_salt()}")
        fid = add_file(conn, ws, add_work(conn, ws, "book"), pdf, root)
        with contextlib.ExitStack() as stack:
            if arm == "mutated":
                stack.enter_context(python_guard_off("book"))
                stack.enter_context(sql_guard_off(
                    conn, "litkb.enqueue_extraction(uuid, text, text, text, text, text, integer, "
                          "integer, text, integer, integer[], integer[], text, text)",
                    "guard: enqueue_extraction refuses a book's file"))
                stack.enter_context(sql_guard_off(
                    conn, "litkb.claim_jobs(text, integer, integer, uuid[])",
                    "guard: claim_jobs never hands out a book's job"))
            sweep_and_work(conn, root, [fid])
        out[arm] = {"jobs": file_jobs(conn, fid), "blocks": blocks_of(conn, fid),
                    "books_extracted": Q.books_extracted(conn)}
    return out


def fire_scan(conn, workdir):
    """(c5) REAL: a copy of Anderson 1957 with OCR OFF. Guarded -> refused `scan-needs-ocr`, never an
    ok run; the refusal AND the post-condition off -> it lands on its recorded no-OCR Docling
    artifact -> ``scans_ocr_unrouted`` 1. Needs the corpus file and the recorded artifact."""
    refuse_live(conn)
    if not (ANDERSON.is_file() and ANDERSON_NO_OCR.is_file()):
        raise FileNotFoundError(f"fire_scan needs {ANDERSON} and {ANDERSON_NO_OCR}")
    root = Path(workdir)
    ws = open_ws(conn)
    out = {"baseline": {"scans_ocr_unrouted": Q.scans_ocr_unrouted(conn)}}
    replay = ReplayExtractor({(1, 22): ANDERSON_NO_OCR}, ocr=False)
    for arm in ("guarded", "mutated"):
        pdf = real_copy(ANDERSON, root / "Validation" / f"Anderson_1957_{arm}.pdf",
                        note=f"fire_scan {arm} {_salt()}")
        fid = add_file(conn, ws, add_work(conn, ws), pdf, root)
        with contextlib.ExitStack() as stack:
            if arm == "mutated":
                stack.enter_context(python_guard_off("scan-needs-ocr"))
                stack.enter_context(attr_off(Q, "scan_postcondition", lambda *a, **k: (None, None)))
            sweep_and_work(conn, root, [fid], ocr=False, extractor=replay)
        out[arm] = {"jobs": file_jobs(conn, fid), "blocks": blocks_of(conn, fid),
                    "runs_ok": conn.execute("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s "
                                            "AND status = 'ok'", (fid,)).fetchone()[0],
                    "scans_ocr_unrouted": Q.scans_ocr_unrouted(conn)}
    return out


def fire_lease(conn, workdir, lease=1):
    """(c2) claim (T1) with a short lease, record T1's artifact, let the lease expire, reclaim (T2);
    T1 then ingests and finishes. Guarded -> LeaseLost, nothing lands, ``mutated_leases_accepted`` 0;
    finish_job's token check removed (CREATE OR REPLACE) -> the stale finish lands -> 1."""
    db = refuse_live(conn)
    root = Path(workdir)
    ws = open_ws(conn)
    out = {"baseline": {"mutated_leases_accepted": Q.mutated_leases_accepted(conn)}}
    for arm in ("guarded", "mutated"):
        pdf = constructed_pdf(root / "Validation" / f"Lease_{arm}.pdf", 2, note=f"fire_lease {arm} {_salt()}")
        fid = add_file(conn, ws, add_work(conn, ws), pdf, root)
        k = Q.connect(db)
        try:
            Q.sweep(k, root, files=[fid])
            (t1,) = Q.claim(k, "worker-T1", 1, lease, [fid])
            sha, rel, _typ = Q._file_row(k, fid)
            man, _ = Q._extract_or_reuse(k, t1, root / rel, sha, SyntheticExtractor(),
                                         root / "_derived", fid)
            time.sleep(lease + 0.5)                       # T1 stalls past its lease
            (t2,) = Q.claim(k, "worker-T2", 1, 60, [fid])
            tei, doc = Q.load_artifacts(man)
            part = dict(man.get("metrics") or {}, artifact_path=man["artifact_path"])
            entry = {"job_id": str(t1.job_id), "page_start": None, "page_end": None,
                     "attempts": t1.attempts, "lease_seq": t1.lease_seq}
            guard = (sql_guard_off(conn, "litkb.finish_job(uuid, text, uuid, text, jsonb)",
                                   "guard: finish_job accepts only the job's current, unsuperseded lease")
                     if arm == "mutated" else contextlib.nullcontext())
            raised = None
            with guard:
                try:
                    Q._ingest(k, t1, fid, str(pdf), tei, doc, [part], [entry], t1.route,
                              t1.image_pages, t1.pages)
                except Q.LeaseLost as e:
                    raised = str(e)
            blocks_after_t1 = blocks_of(conn, fid)
            accepted = Q.mutated_leases_accepted(conn)
            t2_outcome = None
            if arm == "guarded":
                # the rightful holder finishes, so the fixture leaves no live lease behind
                t2_outcome = Q.run_job(k, t2, root=root, extractor=SyntheticExtractor(),
                                       derived=root / "_derived", ocr=True)
        finally:
            k.close()
        out[arm] = {"t1_seq": t1.lease_seq, "t2_seq": t2.lease_seq, "raised": raised,
                    "blocks_after_t1": blocks_after_t1, "t2_outcome": t2_outcome,
                    "blocks": blocks_of(conn, fid), "jobs": file_jobs(conn, fid),
                    "mutated_leases_accepted": accepted}
    return out


def _kill_tree(pid):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)


def _read_trace(d):
    p = Path(d) / "queue-trace.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def worker_command(db, root, *, lease, extra=()):
    return [sys.executable, "-m", "litkb", "--db", db, "queue", "work", "--root", str(root),
            "--derived", str(Path(root) / "_derived"), "--lease", str(lease), *extra]


def fire_kill(conn, workdir, pdfs, *, synthetic_delay=None, lease=8, extra=(), timeout=1800,
              reference=None):
    """(c1) KILL MID-BATCH, RERUN. ``pdfs`` (already under ``workdir``) become file rows; ``litkb queue
    work`` runs as a SUBPROCESS and its whole process tree is killed after the first job commits and
    the next job's extraction starts (read from the worker's own trace); the lease is let expire and
    the command is run again to completion. ``synthetic_delay`` set -> the synthetic extractor seam
    (no GPU); None -> the real GROBID + Docling path. ``reference(pdf) -> [(page, order, type,
    text)]`` is an UNINTERRUPTED run of the same file on the same path; its digest must equal the
    committed one. -> dict with the counters, the digests and the timeline."""
    db = refuse_live(conn)
    root = Path(workdir)
    ws = open_ws(conn)
    baseline = {"stale_leases": Q.stale_leases(conn), "duplicate_blocks": Q.duplicate_blocks(conn, root),
                "resumed_content_hash_mismatches": Q.resumed_content_hash_mismatches(conn, root),
                "mutated_leases_accepted": Q.mutated_leases_accepted(conn)}
    fids = [add_file(conn, ws, add_work(conn, ws), p, root) for p in pdfs]
    k = Q.connect(db)
    try:
        swept = Q.sweep(k, root, files=fids)
    finally:
        k.close()
    trace = root / "_trace"
    env = dict(os.environ, PYTHONUTF8="1", **{Q.TRACE_ENV: str(trace)})
    env["PYTHONPATH"] = str(Path(Q.__file__).resolve().parents[2])
    if synthetic_delay is not None:
        env[Q.TEST_EXTRACTOR_ENV] = f"synthetic:delay={synthetic_delay}"
    files_args = [a for f in fids for a in ("--file", str(f))]
    t0 = time.monotonic()
    log1 = open(root / "worker1.log", "w", encoding="utf-8")
    proc = subprocess.Popen(worker_command(db, root, lease=lease, extra=(*files_args, *extra)),
                            env=env, stdout=log1, stderr=subprocess.STDOUT, cwd=str(root))
    killed_at, state = None, "waiting"
    while proc.poll() is None and time.monotonic() - t0 < timeout:
        ev = _read_trace(trace)
        commits = [e for e in ev if e["event"] == "commit"]
        if commits:
            after = [e for e in ev if e["event"] == "extract-start" and e["at"] > commits[0]["at"]]
            if after:
                time.sleep(1.0)                      # inside the next job's extraction
                _kill_tree(proc.pid)
                killed_at, state = time.monotonic() - t0, "killed"
                break
        time.sleep(0.25)
    proc.wait(timeout=120)
    log1.close()
    before = {"jobs": [file_jobs(conn, f) for f in fids], "stale_leases_now": Q.stale_leases(conn)}
    time.sleep(lease + 1.0)                          # the killed worker's lease runs out
    before["stale_leases_after_expiry"] = Q.stale_leases(conn)
    log2 = open(root / "worker2.log", "w", encoding="utf-8")
    rerun = subprocess.run(worker_command(db, root, lease=Q.LEASE_SECONDS, extra=(*files_args, *extra)),
                           env=env, stdout=log2, stderr=subprocess.STDOUT, cwd=str(root), timeout=timeout)
    log2.close()
    committed, refs = [], []
    for f, pdf in zip(fids, pdfs):
        run = conn.execute("SELECT current_run_id FROM litkb.files WHERE id = %s", (f,)).fetchone()[0]
        digest = Q.blocks_digest(Q.run_rows(conn, run)) if run else None
        recorded = {r[0] for r in conn.execute(
            "SELECT blocks_digest FROM litkb.extraction_jobs WHERE file_id = %s", (f,)).fetchall()}
        ref = Q.blocks_digest(reference(pdf)) if reference else None
        committed.append({"file": Path(pdf).name, "db_digest": digest, "job_digests": sorted(map(str, recorded)),
                          "reference_digest": ref, "equal": digest is not None and digest == ref
                          and recorded == {digest}})
    return {"baseline": baseline, "swept": swept, "state": state, "killed_after_s": killed_at, "worker1_exit": proc.returncode,
            "rerun_exit": rerun.returncode, "before_rerun": before,
            "jobs": [file_jobs(conn, f) for f in fids], "digests": committed,
            "trace": _read_trace(trace),
            "counters": {"stale_leases": Q.stale_leases(conn),
                         "duplicate_blocks": Q.duplicate_blocks(conn, root),
                         "resumed_content_hash_mismatches": Q.resumed_content_hash_mismatches(conn, root),
                         "mutated_leases_accepted": Q.mutated_leases_accepted(conn)}}


def synthetic_reference(pdf):
    """The UNINTERRUPTED reference for the synthetic path: the same documents, reconciled once."""
    from litkb.extract import ingest as ING

    route = "ocr" if P.image_page_numbers(pdf) else "native"
    pages = P.probe_pages(pdf)
    if route == "native":
        doc = synthetic_doc(pdf)
    else:
        doc = Q.assemble([(lo, hi, synthetic_doc(pdf, (lo, hi))) for lo, hi in Q.chunk_ranges(pages)], pages)
    return Q.canonical_rows(ING.prepare(str(pdf), None, doc)["canonical"])

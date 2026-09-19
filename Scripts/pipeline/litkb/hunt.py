"""`litkb hunt` — one unattended call from a reference to searchable text.

    py -3.12 -m litkb hunt <doi-or-url> [--title T] [--author A] [--year Y]
    litkb_hunt(ref=…)                                   (the MCP tool; it shells out to the CLI)

WHAT IT IS. The five steps the convention's hunt protocol names — resolve, admit, acquire,
extract, ingest — run end to end with no operator between them, and the result says which rung
of the four-state ladder the work reached (``absent`` / ``held`` / ``bound-unextracted`` /
``extracted``), what it cost per stage, and everything it REFUSED to do and why. Nothing here
is new machinery: every step is the function that already owns it (``admit.front``,
``acquire.store``, ``extract.grobid``, ``extract.docling``, ``extract.reconcile``,
``extract.ingest``). What is new is that a session no longer has to drive seven of them in
order and diagnose the gap when one is skipped.

IDEMPOTENCE IS THE DATABASE'S, NOT A CACHE'S. Step 0 asks what the knowledge base already holds
for this reference — through the workstream's OWN view, not main's, because a manual proposal is
invisible to main until Kam merges — and an already-extracted work returns its run with nothing
fetched, converted or written. Below that, ``extract.ingest.already_ingested`` refuses a second
run at the same key. A hunt run twice therefore costs one round trip the second time.

THE WEB SOURCE, AND THE THING THAT DOES NOT WORK. A reference with no DOI is a web source:
``Scripts/docs/LITERATURE_CONVENTION.md`` records it as a manual proposal carrying the URL and
the retrieval date, and a manual proposal is signed off by a SECOND session. That approval is
what a hunt cannot do for itself, and it has a consequence nothing in the design says out loud:
``litkb.attach_file`` (migration 0013) refuses a work that is not admitted in MAIN, so the
"admit the proposal, then bind the PDF with acquire" sequence CANNOT complete for a web source.
The file has to arrive with the admission or not at all. So it does: :func:`litkb.admit.front.admit_web`
takes ``pdf_path``, check 3 binds the claimed title against the PDF's own first page — stronger
evidence than the saved page text, not weaker — and the page text is kept beside it as the
snapshot the convention asks for. The work stays a PROPOSAL, invisible to ``litkb_search``,
until a second session approves it; every result says so in those words.

WHERE THE BYTES GO. Download → ``_litkb_staging/incoming/<key>.download`` (create-only, through
the store's one guarded write path). Then the shape check: bytes that are not a whole PDF move
to ``_quarantine/`` with a ``.reason.json`` beside them and the hunt is refused — nothing
acquisition receives is ever discarded (``acquire/store.py``). Bytes that ARE a PDF move to
``_litkb_staging/filed/<key>.pdf`` with their ``pdftotext -layout`` extract, which is where
``land_and_attach`` files a bound download and what every later stage reads.

*Why the extension changes, when the operational note says not to rename.* That note is about
``acquire --from-file``: its disk dedupe hashed every ``*.pdf`` under the literature root, found
the hand-fetched file's own hash, and answered ``duplicate-held`` before binding ever ran — so
the field workaround was to hand it a ``.download``. `hunt` never calls ``acquire`` and never
builds that index, so the reason is gone; what remains is that GROBID, pypdfium2 and Docling are
each handed a path, and only one of the three is documented to ignore the extension.
"""
import datetime
import os
import time
from pathlib import Path

#: Tool artifacts (TEI, DoclingDocument) for the files hunt extracts. OUTSIDE the repository, and
#: a directory of its own: the P5 bulk driver's `LITKB_P5_DERIVED` tree is that pass's resumable
#: checkpoint, with a sha256 sidecar per artifact and a `plan.json` naming the population it was
#: built for. Hunt's resumption is the database's run key, so it has no sidecar to keep in step
#: and nothing to contribute to that plan.
DERIVED = os.environ.get("LITKB_HUNT_DERIVED", r"D:\edmonds-pipeline\litkb_derived\hunt")

#: The four states a hunted reference can end in, in ladder order.
STATES = ("absent", "held", "bound-unextracted", "extracted")

#: Block types that read as a heading when the result shows what the document turned out to be.
HEADING_KINDS = ("title", "heading")

#: The work is admitted, no PDF is bound, and acquisition could not even be ATTEMPTED for it (it is
#: not yet in main, or the work record could not be read back) — a structural gap, not a choice.
NO_FILE = ("the work is admitted and no PDF is bound to it, and this hunt could not attempt "
           "acquisition for it (the work is not yet visible in main). Run "
           "`litkb acquire --key <key>` (open access, then the archive, then Sci-Hub) or "
           "`--from-file <PDF>`, then hunt the reference again — the second hunt picks up at the "
           "bound file.")

#: SPEND RULE (Kam, 2026-09-16 night; decisions.yaml litkb-p0-foundation): a hunt proceeds to
#: acquisition — open access, then the archive by DOI — BY DEFAULT. `--no-spend` / `spend=False`
#: is the explicit exception, and it is recorded as a distinct, DELIBERATE stop — never the same
#: symptom as the six DOI hunts that died stuck at `held` on 2026-09-16 for lack of this rule.
NO_SPEND = ("the work is admitted and no PDF is bound to it. This hunt was told not to spend "
            "(--no-spend / spend=False): no open-access fetch and no archive call were attempted. "
            "Run `litkb acquire --key <key>` or hunt again without --no-spend — the default hunt "
            "spends.")

#: Every automated route was tried (open access, then the archive, then Sci-Hub) and none of them
#: landed a file. `acquisition.attempts` names what each route answered.
SPEND_EXHAUSTED = ("hunt spent by default (open access, then the archive, then Sci-Hub) and none "
                   "of them landed a file; see `acquisition.attempts`. "
                   "`litkb acquire --key <key> --from-file <PDF>` is the manual route.")


class HuntRefused(Exception):
    """A refusal is a RESULT (mcp/server.py's rule): the caller must be able to read what was
    refused, why, and what to do — never a traceback."""

    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def ref_kind(ref):
    """``'url'`` or ``'doi'`` for a reference as a session types it.

    A DOI is anything else, deliberately: ``normalize_doi`` is what decides whether the rest of
    the string IS one, and it is called by the admission that stores it, not twice."""
    r = (ref or "").strip()
    low = r.lower()
    if low.startswith(("http://", "https://")) and "doi.org/" not in low:
        return "url"
    return "doi"


def _role(kind):
    return os.environ.get(f"LITKB_{kind.upper()}_ROLE") or f"litkb_{kind}"


def _reader(db, role=None):
    from litkb.db import connect as c

    return c.connect(db, role or _role("reader"), autocommit=True)


def load_workstream(worktree):
    """(workstream_id, token) for the worktree, or a refusal naming the tool that opens one."""
    from litkb import workstream

    try:
        return workstream.load(worktree)
    except FileNotFoundError:
        raise HuntRefused("no-workstream",
                          f"no {workstream.TOKEN_FILE} in {worktree}: a hunt admits, binds and "
                          "ingests, and every one of those names an open workstream and presents "
                          "its token. Open one with `litkb ws open <slug>` (or litkb_ws_open) "
                          "first.", worktree=str(worktree)) from None
    except (ValueError, KeyError):
        raise HuntRefused("bad-workstream-file",
                          f"{Path(worktree) / workstream.TOKEN_FILE} is not readable as "
                          "{workstream_id, token}") from None


# ── step 0: what does the knowledge base already hold for this reference ───────────────────

def look_up(conn, ws_id, ref, kind):
    """The four-state ladder for one reference, read through the WORKSTREAM's view.

    ``main_*`` is the wrong view here and the difference is the whole point: a web source is a
    manual PROPOSAL, so its work, its identifier and its file live in ``ws_heads`` and main holds
    nothing at all. A ladder read off main would call a work this very session admitted ``absent``
    and hunt it again — admission's check 2 would then refuse the second one as a duplicate, and
    the session would be told its own work was somebody else's.

    -> None when nothing is held, else {state, work_id, key, file_id, …}.
    """
    row = conn.execute(
        "SELECT wi.work_id::text FROM litkb.ws_identifiers wi "
        " WHERE wi.view_workstream_id = %s AND wi.scheme = %s AND wi.status = 'active' "
        "   AND wi.value_norm = litkb.norm_identifier(%s, %s) LIMIT 1",
        (ws_id, kind, kind, ref)).fetchone()
    if not row:
        return None
    work_id = row[0]
    w = conn.execute("SELECT key, title, year, type FROM litkb.ws_works "
                     "WHERE view_workstream_id = %s AND work_id = %s", (ws_id, work_id)).fetchone()
    files = conn.execute(
        "SELECT file_id::text, sha256, rel_path, pages, current_run_id::text, status "
        "  FROM litkb.ws_files WHERE view_workstream_id = %s AND work_id = %s AND status = 'active' "
        " ORDER BY rel_path", (ws_id, work_id)).fetchall()
    ids = conn.execute(
        "SELECT scheme, value, verified_by FROM litkb.ws_identifiers "
        " WHERE view_workstream_id = %s AND work_id = %s AND status = 'active' ORDER BY scheme, value",
        (ws_id, work_id)).fetchall()
    in_main = bool(conn.execute("SELECT 1 FROM litkb.main_works WHERE work_id = %s",
                                (work_id,)).fetchone())
    # A file with a current run may still hold zero blocks — "the extractor ran and found
    # nothing" and "the extractor never ran" are different problems, and only the second is
    # fixed by running it (the distinction litkb_work's ladder already makes).
    if not files:
        state = "held"
    elif not any(f[4] for f in files):
        state = "bound-unextracted"
    else:
        state = "extracted"
    run_id = next((f[4] for f in files if f[4]), None)
    blocks = 0
    if run_id:
        blocks = conn.execute("SELECT count(*) FROM litkb.blocks WHERE run_id = %s",
                              (run_id,)).fetchone()[0]
    return {"state": state, "work_id": work_id, "key": w[0] if w else None,
            "title": w[1] if w else None, "year": w[2] if w else None,
            "in_main": in_main, "run_id": run_id, "blocks": blocks,
            "files": [dict(zip(("file_id", "sha256", "rel_path", "pages", "current_run_id",
                                "status"), f)) for f in files],
            "identifiers": [dict(zip(("scheme", "value", "verified_by"), i)) for i in ids]}


# ── step 1: the document itself ────────────────────────────────────────────────────────────

def _default_fetch(url, timeout=180):
    """-> (status, bytes). Never raises; a dead URL is a refusal, not a traceback."""
    from litkb.netutil import Client

    st, _hd, body = Client(base="").get(url, accept="application/pdf", timeout=timeout)
    return st, body or b""


def page1(pdf_path):
    """(the PDF's page-1 text, its /Info dictionary) — read through the ONE binder's readers."""
    from litkb.admit import binding as _binding

    return _binding.first_page_text(pdf_path) or "", _binding.pdf_info(pdf_path)


def guess_fields(text, info, title=None, author=None, year=None):
    """Title, author and year for a document no registry can confirm. -> (title, author, year, how)

    DELIBERATELY WEAK, and it says which fields it could not fill rather than inventing them. The
    PDF's ``/Title`` is whatever the tool that wrote it was pointed at — this document's is
    "Hardware Documentation", which names the file and not the work — and no rule over a cover
    page's line breaks tells an author from a course number. Both are overridable, and the
    refusal for a missing author names the flag.
    """
    how = {}
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    t = (title or "").strip()
    if not t:
        meta = (info.get("Title") or "").strip()
        # the metadata title is used only when the page's own opening lines do not run longer:
        # a cover page that prints the work's name in display type beats a producer's file label
        head = " ".join(lines[:4])
        t = head if len(head) > len(meta) else meta
        how["title"] = "page-1 text" if t == head else "/Title metadata"
    else:
        how["title"] = "--title"
    a = (author or "").strip()
    if not a:
        a = (info.get("Author") or "").strip()
        how["author"] = "/Author metadata" if a else "NOT FOUND"
    else:
        how["author"] = "--author"
    y = year
    if not y:
        import re
        m = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", info.get("CreationDate") or "")
        y = int(m.group(1)) if m else None
        how["year"] = "/CreationDate" if y else "NOT FOUND"
    else:
        how["year"] = "--year"
    return t, a, y, how


def land_download(store, stem, data):
    """Bytes → ``_litkb_staging/incoming/<stem>.download``, then the shape check.

    -> (the .download path, sha256). Raises HuntRefused('not-a-pdf'/'truncated-pdf') with the
    quarantined path, never a deletion: the store holds no delete call at all.

    It stops at ``.download`` because the work's KEY is not known yet — it is derived from the
    document's own first page, which is on the other side of this function. Nothing reads a PDF
    by its extension between here and :func:`file_under_key`: pypdfium2 is handed a path.
    """
    import hashlib

    from litkb.acquire.store import pdf_shape

    sha = hashlib.sha256(data).hexdigest()
    dl = store.write_new(store.free_name(store.incoming, stem, ".download"), data)
    # BEGIN guard: a hunted download that is not a whole PDF is quarantined, never admitted
    # The 2026-09-15 incident in one line: 295,657 bytes of HTML written under a .pdf name and
    # admitted as a paper. The check is on the BYTES, before anything reads them as a document,
    # and the refusal keeps them — under a name that says what is wrong with them — because a
    # deletion is what made that incident unrecoverable rather than merely wrong.
    shape, why = pdf_shape(data)
    if shape != "pdf":
        qpdf, _qtxt = store.to_quarantine(dl, None, stem, shape, sha)
        qwhy = store.write_reason(qpdf, {
            "status": "bad-file", "shape": shape, "reason": why, "route": "hunt",
            "sha256": sha, "bytes": len(data), "moved_from": store.rel(dl),
            "at": _now().isoformat()})
        raise HuntRefused("not-a-pdf" if shape == "not-a-pdf" else shape, why,
                          quarantined=store.rel(qpdf), quarantine_reason=store.rel(qwhy),
                          sha256=sha, bytes=len(data))
    # END guard: a hunted download that is not a whole PDF is quarantined, never admitted
    return dl, sha


def file_under_key(store, key, download):
    """``incoming/<stem>.download`` → ``_litkb_staging/filed/<key>.pdf``, with its text extract.

    Where ``land_and_attach`` files a download that bound, under the name the work is keyed by,
    and with the ``pdftotext -layout`` extract the convention asks for beside it. The rename is
    what the operational note warns against for ``acquire --from-file`` — its disk dedupe hashes
    every ``*.pdf`` under the literature root, so a hand-fetched PDF found its own hash and came
    back ``duplicate-held`` before binding ever ran. Hunt calls no part of that path and builds no
    such index; what it has instead is three tools that are each handed a path, only one of which
    is documented to ignore the extension. -> (pdf, txt|None)
    """
    pdf = store.move_new(download, store.free_name(store.filed, key))
    return pdf, store.extract(pdf)


# ── steps 2-3: extract and ingest, the P5 per-file path ────────────────────────────────────

def extract_and_ingest(db, file_id, pdf_path, *, timing, derived=None, device="cuda",
                       docling_python=None, grobid=True):
    """GROBID → Docling → reconcile → ingest → set current run, for ONE file.

    The same stages, the same order and the same run key as the bulk pass
    (``qc/instruments/litkb_p5_bulk.py``): ``reconcile.PIPELINE_VERSION`` and
    ``extract.ingest.CORPUS_PARAMS``, so a later bulk pass over this file finds its run already
    ``ok`` and does nothing. -> the ingest result, plus the reconciliation's own numbers.

    NO FORMULA LaTeX. The corpus's LaTeX comes from the L4 CodeFormula pass over crops the
    formula census selected; a document hunted today has no rows in it. Every equation block
    therefore carries ``latex_status = 'unverified'`` — migration 0022's word for "the pass ran
    over the corpus and produced nothing for this equation", which is a different fact from the
    NULL that means no pass has looked at all.
    """
    import dataclasses

    from litkb import ingest as ingest_login
    from litkb.extract import docling as D
    from litkb.extract import grobid as G
    from litkb.extract import ingest as ing
    from litkb.extract import inventory as I
    from litkb.extract import reconcile as R

    derived = derived or DERIVED
    os.makedirs(derived, exist_ok=True)
    rec = I.probe_file(pdf_path)
    tei = None
    if grobid and rec["route"] in ("native", "mixed", "cover-sheet"):
        t0 = time.monotonic()
        started = G.start(wait=300, hold=True)
        try:
            if not started:
                raise G.GrobidError("GROBID did not come up under WSL")
            tei, _m = G.extract(pdf_path, concurrency=1, sample_rss=False)
        except G.GrobidError as e:
            timing["grobid_error"] = f"{type(e).__name__}: {e}"[:300]
        finally:
            if started:
                G.stop()
        timing["grobid"] = round(time.monotonic() - t0, 2)

    t0 = time.monotonic()
    doc_json = os.path.join(derived, rec["sha256"] + ".docling.json")
    wants_ocr = rec["route"] == "scan" or (rec["route"] == "mixed" and rec.get("ocr_pages"))
    D.run([{"pdf": str(pdf_path), "out": doc_json}],
          os.path.join(derived, "metrics_docling.jsonl"), python=docling_python,
          ocr=bool(wants_ocr), formula=False, device=device, cwd=derived)
    doc = D.load(doc_json) if os.path.exists(doc_json) else None
    timing["docling"] = round(time.monotonic() - t0, 2)
    if tei is None and doc is None:
        raise HuntRefused("no-artifact",
                          "neither GROBID nor Docling produced an artifact for this file, so "
                          "there is nothing to reconcile.", route=rec["route"],
                          grobid_error=timing.get("grobid_error"))

    t0 = time.monotonic()
    frames = I.page_frames(pdf_path)
    canonical, dis, stats = R.reconcile(pdf_path, tei, doc, rec,
                                        ocr_pages=rec.get("ocr_pages") or (), frames=frames)
    # the word for an equation no formula pass produced a row for (migration 0022)
    canonical = [dataclasses.replace(c, latex_status="unverified")
                 if c.kind == "equation" and c.latex_status is None else c
                 for c in canonical]
    classes = {i + 1: d.get("scan", "unknown")
               for i, d in enumerate(rec.get("page_detail") or [])}
    cov = R.coverage(pdf_path, canonical, classes, frames=frames)
    timing["reconcile"] = round(time.monotonic() - t0, 2)

    t0 = time.monotonic()
    pages = [{"page_no": p, "page_class": r["page_class"], "native_chars": r["chars"],
              "covered_chars": r["covered"], "coverage_share": r["share"]}
             for p, r in sorted(cov.items())]
    conn = ingest_login.connect(db)
    try:
        res = ing.ingest_file(conn, file_id, canonical, dis, stats, pages=pages,
                              artifact_path=doc_json, host="local",
                              pipeline_version=R.PIPELINE_VERSION, params=ing.CORPUS_PARAMS)
    finally:
        conn.close()
    timing["ingest"] = round(time.monotonic() - t0, 2)
    return res, {"record": rec, "stats": stats, "coverage": cov, "tei": tei is not None,
                 "docling": doc is not None, "canonical": canonical}


def _coverage_summary(cov):
    """Character share, and the sentence that stops it being read as recall.

    ``reconcile.coverage`` asks which of a page's native characters lie inside SOME canonical
    block. Per-region recall — did the extraction find each region a referee marked — exists only
    on the six gold pages the stage-5 referee authored and is not computable over a document
    nobody has marked up (Reports/LITKB_P5_BULK_2026-09-16.md §6)."""
    from litkb.extract import reconcile as R

    shares = [v["share"] for v in cov.values() if v["share"] is not None]
    return {"metric": "character share: native characters lying inside some canonical block",
            "not_recall": "per-region recall needs referee-authored regions per page and is NOT "
                          "computed here; this is the catastrophe floor, not an operating point",
            "floor": R.COVERAGE_FLOOR,
            "by_page_type": {k: (None if v["share"] is None else round(v["share"], 4))
                             for k, v in sorted(R.coverage_by_page_type(cov).items())},
            "min_share": min(shares) if shares else None,
            "pages_below_floor": len(R.coverage_failures(cov)), "pages": len(cov)}


# ── the hunt ───────────────────────────────────────────────────────────────────────────────

def hunt(ref, *, db=None, worktree=None, agent=None, session=None, title=None, author=None,
         year=None, source_note=None, key=None, work_type="report", retrieved=None,
         fetch=None, store=None, reader_role=None, writer_role=None, extract=True,
         device="cuda", docling_python=None, derived=None, registry_client=None,
         spend=True, acquirer=None, hunt_request_id=None):
    """Resolve → admit → bind → extract → ingest, for one reference. -> the result dict.

    ``spend`` (default True, SPEND RULE 2026-09-16, decisions.yaml litkb-p0-foundation): a
    reference that resolves to `held` (admitted, no PDF) proceeds to acquisition — open access,
    then the archive by DOI, then Sci-Hub — unless the caller passes ``spend=False``
    (``--no-spend`` at the CLI, ``spend=False`` from an MCP tool), which stops at `held` and
    records that stop as a distinct, deliberate outcome (``held-no-spend``), never the silent
    stall six DOI hunts died at on 2026-09-16. ``acquirer`` overrides the acquisition call for
    tests: ``acquirer(conn, ws_id, token, work, *, store, agent, session) -> {"outcome", ...}``.

    ``hunt_request_id`` (migration 0023, litkb/hunt_request.py): a review agent's drop-off this
    hunt is following up. As soon as this reference resolves to a work — whatever rung of the
    ladder it reaches, cached or fresh — the request is linked to it (``litkb.link_hunt_request``,
    idempotent). Naming a request requires ``agent``/``session`` even for an otherwise label-less
    cached lookup, because linking is a write.

    Never raises for a refusal: a caller reads ``ok``, ``refused`` and ``refusals``.
    """
    t_start = time.monotonic()
    timing, refusals = {}, []
    out = {"ref": ref, "ref_kind": ref_kind(ref), "at": _now().isoformat()}
    try:
        return _hunt(ref, out, timing, refusals, db=db, worktree=worktree, agent=agent,
                     session=session, title=title, author=author, year=year,
                     source_note=source_note, key=key, work_type=work_type, retrieved=retrieved,
                     fetch=fetch, store=store, reader_role=reader_role, writer_role=writer_role,
                     extract=extract, device=device, docling_python=docling_python,
                     derived=derived, registry_client=registry_client, spend=spend,
                     acquirer=acquirer, hunt_request_id=hunt_request_id)
    except HuntRefused as e:
        refusals.append({"code": e.code, "message": e.message} | e.extra)
        return out | {"ok": False, "refused": e.code, "message": e.message,
                      "refusals": refusals, "seconds": timing} | e.extra
    except Exception as e:                       # noqa: BLE001 — the boundary is the point
        refusals.append({"code": "error", "message": f"{type(e).__name__}: {e}"})
        return out | {"ok": False, "refused": "error", "message": f"{type(e).__name__}: {e}",
                      "refusals": refusals, "seconds": timing}
    finally:
        timing["total"] = round(time.monotonic() - t_start, 2)


def _hunt(ref, out, timing, refusals, *, db, worktree, agent, session, title, author, year,
          source_note, key, work_type, retrieved, fetch, store, reader_role, writer_role,
          extract, device, docling_python, derived, registry_client, spend, acquirer,
          hunt_request_id=None):
    from litkb.acquire.store import Store
    from litkb.admit import front
    from litkb.db import connect as c
    from litkb.textnorm import norm_label

    db = db or os.environ.get("LITKB_DB") or c.DB_MAIN
    worktree = Path(worktree or os.environ.get("LITKB_WORKTREE") or os.getcwd()).resolve()
    # the ONE invisible-character normaliser (migration 0014, D7), applied where the write is
    # decided: a label of zero-width joiners is truthy, so an un-normalised check passes it
    # through and the admission is signed by a session the approval rule cannot compare
    agent = norm_label(agent or os.environ.get("LITKB_AGENT") or "")
    session = norm_label(session or os.environ.get("LITKB_SESSION") or "")
    kind = out["ref_kind"]

    # BEGIN guard: hunt refuses outside a worktree that holds a workstream
    ws_id, token = load_workstream(worktree)
    # END guard: hunt refuses outside a worktree that holds a workstream

    # BEGIN guard: naming a hunt_request always requires labels, even on an otherwise cached hunt
    # look_up's cache hits (extracted/held/bound-unextracted, below) normally need no agent/session
    # at all — a repeated lookup writes nothing. Linking a drop-off is a write regardless of which
    # rung the ladder answers at, so it cannot ride on that label-less path.
    if hunt_request_id and (not agent or not session):
        raise HuntRefused("no-labels",
                          "linking a hunt_request (migration 0023) is a write: every write records "
                          "which agent and which session made it. Set LITKB_AGENT and "
                          "LITKB_SESSION, or pass --agent/--session.")
    # END guard: naming a hunt_request always requires labels, even on an otherwise cached hunt

    t0 = time.monotonic()
    reader = _reader(db, reader_role)
    try:
        held = look_up(reader, ws_id, ref, kind)
    finally:
        reader.close()
    timing["resolve"] = round(time.monotonic() - t0, 2)
    # BEGIN call site: hunt_request linked from the cache (look_up already resolved a work_id)
    if held and hunt_request_id:
        _link_hunt_request(db, ws_id, token, hunt_request_id, held["work_id"], agent, session,
                           writer_role, out)
    # END call site: hunt_request linked from the cache (look_up already resolved a work_id)
    # BEGIN guard: hunt answers from the database before it fetches anything
    # A hunt is one call an agent may make twice — after a crash, in a retry, or simply because
    # it forgot. The second call must cost a round trip and write nothing: fetching the bytes
    # again would land a duplicate under a freed name, and admitting again would be refused by
    # check 2 with a message about somebody else's work. `already_ingested` guards the run, but
    # only after the download and the admission have already happened.
    if held and held["state"] == "extracted":
        return out | {"ok": True, "state": "extracted", "outcome": "already-extracted",
                      "refusals": refusals, "seconds": timing,
                      "note": "held and extracted already; nothing was fetched, converted or "
                              "written."} | _report(db, ws_id, held, reader_role)
    # `held` — admitted with no bound file — stops here for the same reason, and it is the rung
    # that is easiest to get wrong: falling through would re-admit a work this knowledge base
    # already holds, and check 2 would refuse it with a message about a DUPLICATE, so a second
    # hunt of a DOI would report a collision instead of the state it is in.
    if held and held["state"] == "held":
        return _spend_on_held(db, ws_id, token, ref, kind, held, out, timing, refusals,
                              spend=spend, agent=agent, session=session, store=store,
                              reader_role=reader_role, writer_role=writer_role, extract=extract,
                              device=device, docling_python=docling_python, derived=derived,
                              acquirer=acquirer, in_main=held.get("in_main"))
    # END guard: hunt answers from the database before it fetches anything

    if held and held["state"] == "bound-unextracted" and extract:
        f = held["files"][0]
        return _finish(db, ws_id, held, f, out, timing, refusals, reader_role=reader_role,
                       device=device, docling_python=docling_python, derived=derived,
                       root=(store.root if store else None))

    if held and not extract:
        return out | {"ok": True, "state": held["state"], "outcome": "held",
                      "refusals": refusals, "seconds": timing} | _report(db, ws_id, held,
                                                                        reader_role)

    if not agent or not session:
        raise HuntRefused("no-labels",
                          "every write records which agent and which session made it: set "
                          "LITKB_AGENT and LITKB_SESSION, or pass --agent/--session.")

    store = store or Store()
    writer = c.connect(db, writer_role or _role("writer"), autocommit=True)
    try:
        if kind == "doi":
            t0 = time.monotonic()
            claimed = {k: v for k, v in (("title", title), ("authors", author),
                                         ("year", year)) if v}
            res = front.admit_registry(writer, ws_id, token, doi=ref, claimed=claimed or None,
                                       key=key, agent=agent, session=session,
                                       client=registry_client)
            timing["admit"] = round(time.monotonic() - t0, 2)
            if res.get("outcome") != "admitted":
                raise HuntRefused("admission-refused",
                                  "the DOI was not admitted; the checks say why.",
                                  admission=_thin(res))
            out["admission"] = _thin(res)
            # BEGIN call site: hunt_request linked from a fresh DOI admission
            if hunt_request_id:
                _link_hunt_request(db, ws_id, token, hunt_request_id, res["work_id"], agent,
                                   session, writer_role, out, conn=writer)
            # END call site: hunt_request linked from a fresh DOI admission
            # A DOI with no bound file reaches the SPEND decision HERE, and a refusal says so as a
            # STATE rather than an error: the work is admitted, which is progress. `litkb acquire`
            # (or `_spend_on_held`'s own call into the same acquisition code) owns the route
            # decision and records every attempt.
            return _spend_on_held(db, ws_id, token, ref, kind, {"work_id": str(res["work_id"])},
                                  out, timing, refusals, spend=spend, agent=agent,
                                  session=session, store=store, reader_role=reader_role,
                                  writer_role=writer_role, extract=extract, device=device,
                                  docling_python=docling_python, derived=derived, writer=writer,
                                  acquirer=acquirer, in_main=True)

        # ── a web source ───────────────────────────────────────────────────────────────────
        t0 = time.monotonic()
        status, data = (fetch or _default_fetch)(ref)
        timing["download"] = round(time.monotonic() - t0, 2)
        if status != 200 or not data:
            raise HuntRefused("fetch-failed",
                              f"the URL answered {status} with {len(data)} bytes", status=status)
        retrieved = retrieved or _now().date().isoformat()
        stem = key or f"hunt-{_now().strftime('%Y%m%dT%H%M%S')}"
        dl, sha = land_download(store, stem, data)
        out["downloaded"] = {"bytes": len(data), "sha256": sha, "rel_path": store.rel(dl),
                             "http_status": status}

        text, info = page1(dl)
        t, a, y, how = guess_fields(text, info, title, author, year)
        out["fields"] = {"title": t, "author": a, "year": y, "from": how,
                         "page1_chars": len(text)}
        if not (t and a and y):
            raise HuntRefused("incomplete-record",
                              "a work no registry can confirm is admitted on a claimed title, "
                              "author and year, and the PDF's first page did not supply all "
                              "three: pass --title / --author / --year.",
                              fields=out["fields"], landed=store.rel(dl))
        stem = key or front.make_key(front.first_author_of(a), y, t)
        pdf, _txt = file_under_key(store, stem, dl)
        out["downloaded"]["filed"] = store.rel(pdf)
        snap = Path(derived or DERIVED) / f"{stem}.page1.txt"
        snap.parent.mkdir(parents=True, exist_ok=True)
        # The DERIVED directory is outside the literature root: `admit_web` lands the durable copy
        # under `_litkb_staging/web/` through the store's own guarded write, and this is only the
        # scratch file handed to it. Nothing in the store is touched by this line.
        snap.write_text(  # store-scan: allow (outside the literature root; see above)
            text, encoding="utf-8", newline="\n")

        t0 = time.monotonic()
        res = front.admit_web(writer, ws_id, token, title=t, authors=a, year=y, url=ref,
                              retrieved=retrieved, snapshot_path=str(snap),
                              source_note=source_note or f"hunted from {ref} on {retrieved}",
                              work_type=work_type, key=key, agent=agent, session=session,
                              pdf_path=str(pdf), root=store.root, store=store)
        timing["admit"] = round(time.monotonic() - t0, 2)
        if res.get("outcome") != "proposed":
            raise HuntRefused("admission-refused",
                              "the web source was not admitted; the checks say why.",
                              admission=_thin(res), landed=store.rel(pdf))
        out["admission"] = _thin(res)
        # BEGIN call site: hunt_request linked from a fresh web-source admission
        if hunt_request_id:
            _link_hunt_request(db, ws_id, token, hunt_request_id, res["work_id"], agent, session,
                               writer_role, out, conn=writer)
        # END call site: hunt_request linked from a fresh web-source admission
    finally:
        writer.close()

    held = {"work_id": str(res["work_id"]), "state": "bound-unextracted",
            "files": [{"file_id": str(res["file_id"])}]}
    if not extract:
        return out | {"ok": True, "state": "bound-unextracted", "outcome": "bound",
                      "refusals": refusals, "seconds": timing} | _report(db, ws_id, held,
                                                                        reader_role)
    return _finish(db, ws_id, held, {"file_id": str(res["file_id"]), "rel_path": store.rel(pdf)},
                   out, timing, refusals, reader_role=reader_role, device=device,
                   docling_python=docling_python, derived=derived, root=store.root,
                   pdf_path=str(pdf))


def _default_acquire(conn, ws_id, token, work, *, store, agent, session):
    """The acquisition `_spend_on_held` calls by default: the same `litkb acquire` route logic
    (open access, then Anna's Archive by DOI, then Sci-Hub by DOI), at its own defaults. A test
    passes `acquirer=` to stub this without opening a socket."""
    from litkb.acquire.run import acquire

    return acquire(conn, ws_id, token, work, store=store, agent=agent, session=session)


def _spend_on_held(db, ws_id, token, ref, kind, held, out, timing, refusals, *, spend, agent,
                   session, store, reader_role, writer_role, extract, device, docling_python,
                   derived, writer=None, acquirer=None, in_main=None):
    """The rung a hunt reaches when a work is admitted with no PDF bound — read through the DB
    lookup (``held`` from :func:`look_up`, carrying ``in_main``) or straight off a fresh DOI
    admission (``held={"work_id": ...}``, always in main: ``admit_registry`` lands there directly).

    SPEND RULE (Kam, 2026-09-16 night; decisions.yaml litkb-p0-foundation): a hunt proceeds to
    acquisition BY DEFAULT (``spend=True``). ``spend=False`` is the explicit exception and stops
    here as a DELIBERATE, distinct outcome (``held-no-spend``) — never the silent stall six DOI
    hunts died at on 2026-09-16 for lack of this rule. A spend that lands nothing is ALSO distinct
    (``held-spend-exhausted``) from both: every automated route was tried and none of it is
    ``held``'s fault.
    """
    work_id = held["work_id"]
    if not spend:
        # BEGIN guard: spend=False stops a hunt at held before any acquisition is attempted
        refusals.append({"code": "no-spend", "message": NO_SPEND})
        return out | {"ok": True, "state": "held", "outcome": "held-no-spend",
                      "refusals": refusals, "seconds": timing} | _report(db, ws_id, held,
                                                                         reader_role)
        # END guard: spend=False stops a hunt at held before any acquisition is attempted
    if in_main is False:
        # a proposal not yet in main has no litkb.main_works row: acquire()'s work_record() reads
        # exactly that table, so spending here would be reading a work that is not there yet
        refusals.append({"code": "no-file", "message": NO_FILE})
        return out | {"ok": True, "state": "held", "outcome": "held",
                      "refusals": refusals, "seconds": timing} | _report(db, ws_id, held,
                                                                         reader_role)
    if not agent or not session:
        raise HuntRefused("no-labels",
                          "every write records which agent and which session made it: set "
                          "LITKB_AGENT and LITKB_SESSION, or pass --agent/--session.")
    from litkb.acquire.run import work_record
    from litkb.acquire.store import Store
    from litkb.db import connect as c

    store = store or Store()
    acquire_fn = acquirer or _default_acquire
    own_writer = writer is None
    conn = writer or c.connect(db, writer_role or _role("writer"), autocommit=True)
    try:
        t0 = time.monotonic()
        work = work_record(conn, work_id=work_id)
        if work is None:
            timing["acquire"] = round(time.monotonic() - t0, 2)
            refusals.append({"code": "no-file", "message": NO_FILE})
            return out | {"ok": True, "state": "held", "outcome": "held",
                          "refusals": refusals, "seconds": timing} | _report(
                              db, ws_id, held, reader_role)
        acq = acquire_fn(conn, ws_id, token, work, store=store, agent=agent, session=session)
        timing["acquire"] = round(time.monotonic() - t0, 2)
    finally:
        if own_writer:
            conn.close()
    out["acquisition"] = {"outcome": acq.get("outcome"), "attempts": acq.get("attempts", [])}

    reader = _reader(db, reader_role)
    try:
        fresh = look_up(reader, ws_id, ref, kind)
    finally:
        reader.close()

    if fresh and fresh["state"] == "extracted":
        return out | {"ok": True, "state": "extracted", "outcome": "already-extracted",
                      "refusals": refusals, "seconds": timing,
                      "note": "the acquisition landed a file already extracted under another "
                              "work's copy (sha256 dedupe)."} | _report(db, ws_id, fresh,
                                                                        reader_role)
    if fresh and fresh["state"] == "bound-unextracted":
        if not extract:
            return out | {"ok": True, "state": "bound-unextracted", "outcome": "bound",
                          "refusals": refusals, "seconds": timing} | _report(db, ws_id, fresh,
                                                                             reader_role)
        return _finish(db, ws_id, fresh, fresh["files"][0], out, timing, refusals,
                       reader_role=reader_role, device=device, docling_python=docling_python,
                       derived=derived, root=(store.root if store else None))

    refusals.append({"code": "not-acquired", "message": SPEND_EXHAUSTED})
    return out | {"ok": True, "state": "held", "outcome": "held-spend-exhausted",
                  "refusals": refusals, "seconds": timing} | _report(db, ws_id, held, reader_role)


def _finish(db, ws_id, held, f, out, timing, refusals, *, reader_role, device, docling_python,
            derived, root=None, pdf_path=None):
    """Extract and ingest a bound file, then report the ladder rung it reached."""
    from litkb.acquire.store import LITERATURE_ROOT

    path = pdf_path or str(Path(root or LITERATURE_ROOT) / f["rel_path"].replace("/", os.sep))
    if not os.path.exists(path):
        raise HuntRefused("file-missing", f"the file bound to this work is not at {path}",
                          rel_path=f.get("rel_path"))
    res, detail = extract_and_ingest(db, f["file_id"], path, timing=timing, derived=derived,
                                     device=device, docling_python=docling_python)
    out["extraction"] = {"run_id": str(res["run_id"]), "inserted": res["inserted"],
                         "blocks": res["blocks"], "disagreements": res["disagreements"],
                         "grobid_tei": detail["tei"], "docling": detail["docling"],
                         "route": detail["record"]["route"],
                         "pages": detail["record"]["pages"],
                         "by_kind": detail["stats"]["by_kind"],
                         "matched": detail["stats"]["matched"]}
    out["coverage"] = _coverage_summary(detail["coverage"])
    if timing.get("grobid_error"):
        refusals.append({"code": "grobid", "message": timing["grobid_error"],
                         "effect": "the reconciliation ran on Docling alone"})
    return out | {"ok": True, "state": "extracted", "outcome": "extracted",
                  "refusals": refusals, "seconds": timing} | _report(db, ws_id, held, reader_role)


def _link_hunt_request(db, ws_id, token, hunt_request_id, work_id, agent, session, writer_role,
                       out, conn=None):
    """litkb.link_hunt_request, called at every point in `_hunt` where a work_id becomes known
    (the cache hit, a fresh DOI admission, a fresh web admission — three call sites, migration
    0023). Idempotent: re-linking the same work is a no-op success. Opens its own writer
    connection when the caller has none open already (the cache-hit call site); reuses the
    admission's own connection otherwise, so a hunt that already opened a writer does not open a
    second one for this alone.

    Never raises: a link that fails (the request belongs to another workstream, or is already
    linked to a DIFFERENT work) is recorded in ``out['hunt_request']`` as a refusal, the same way
    every other rung of this ladder reports a problem without stopping the hunt that reached a
    real state."""
    from litkb import hunt_request
    from litkb.db import connect as c

    own = conn is None
    conn = conn or c.connect(db, writer_role or _role("writer"), autocommit=True)
    try:
        hunt_request.link(conn, ws_id, token, hunt_request_id, work_id=work_id, agent=agent,
                          session=session)
        out["hunt_request"] = {"id": hunt_request_id, "linked_to": work_id, "ok": True}
    except Exception as e:                    # noqa: BLE001 — a link failure never fails the hunt
        out["hunt_request"] = {"id": hunt_request_id, "ok": False,
                               "error": f"{type(e).__name__}: {e}"}
    finally:
        if own:
            conn.close()


def _thin(res):
    """An admission result without the whole check payload: what a reader acts on."""
    return {k: res.get(k) for k in ("outcome", "admission_id", "work_id", "file_id", "refused_at",
                                    "constraint", "title_discrepancy") if res.get(k) is not None}


def _report(db, ws_id, held, reader_role=None):
    """The work as the workstream now sees it: identity, files, blocks by kind, headings."""
    conn = _reader(db, reader_role)
    try:
        work_id = held["work_id"]
        w = conn.execute("SELECT key, title, year, type FROM litkb.ws_works "
                         "WHERE view_workstream_id = %s AND work_id = %s",
                         (ws_id, work_id)).fetchone()
        ids = conn.execute(
            "SELECT scheme, value, verified_by FROM litkb.ws_identifiers "
            " WHERE view_workstream_id = %s AND work_id = %s AND status = 'active' "
            " ORDER BY scheme, value", (ws_id, work_id)).fetchall()
        files = conn.execute(
            "SELECT file_id::text, sha256, rel_path, pages, current_run_id::text "
            "  FROM litkb.ws_files WHERE view_workstream_id = %s AND work_id = %s "
            "   AND status = 'active' ORDER BY rel_path", (ws_id, work_id)).fetchall()
        run = next((f[4] for f in files if f[4]), None)
        kinds, heads, npages = {}, [], None
        if run:
            kinds = dict(conn.execute(
                "SELECT type, count(*) FROM litkb.blocks WHERE run_id = %s GROUP BY 1 ORDER BY 1",
                (run,)).fetchall())
            npages = conn.execute("SELECT count(*) FROM litkb.pages WHERE run_id = %s",
                                  (run,)).fetchone()[0]
            heads = [dict(zip(("page", "kind", "text"), r)) for r in conn.execute(
                "SELECT page_no, type, left(text, 120) FROM litkb.blocks "
                " WHERE run_id = %s AND type = ANY(%s) AND coalesce(text, '') <> '' "
                " ORDER BY page_no, reading_order LIMIT 3", (run, list(HEADING_KINDS))).fetchall()]
        in_main = bool(conn.execute("SELECT 1 FROM litkb.main_works WHERE work_id = %s",
                                    (work_id,)).fetchone())
    finally:
        conn.close()
    return {
        "work_id": work_id, "work_key": w[0] if w else None,
        "work": dict(zip(("key", "title", "year", "type"), w)) if w else None,
        "identifiers": [dict(zip(("scheme", "value", "verified_by"), i)) for i in ids],
        "files": [dict(zip(("file_id", "sha256", "rel_path", "pages", "current_run_id"), f))
                  for f in files],
        "run_id": run, "pages": npages, "blocks": sum(kinds.values()) if kinds else 0,
        "blocks_by_kind": kinds, "headings": heads,
        "in_main": in_main,
        "visible_to_search": in_main,
        "what_next": (
            "the work is in main's view: litkb_search reaches its blocks."
            if in_main else
            "this is a manual PROPOSAL. Its blocks are real and ingested, and litkb_search — "
            "which joins litkb.main_files — returns none of them until a SECOND session approves "
            "the admission (`litkb approve <admission-id>`) and Kam merges the branch. Quote it "
            "through its block_id, which litkb_record_use accepts."),
    }

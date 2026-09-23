"""The Python front of admission (design §4.6): registries and the PDF on this side, one database call.

    cand = add_candidate(conn, ws, token, source="manual", title=..., authors=..., year=..., ids={...})
    res  = admit_registry(conn, ws, token, doi="10.4171/jems/179", claimed={...}, file_path=..., ...)
    res  = admit_manual(conn, ws, token, title=..., authors=..., year=..., file_path=..., source_note=...)
    res  = approve(conn, approver_ws, approver_token, admission_id, agent, session)

Every call binds the token as a query parameter, never in the SQL text (workstream.py, third referee F-8).
litkb.admit() in the database does checks 1-5 in one transaction and records a refusal as a refused
admission row; this module never pre-decides a duplicate or a refusal on the database's behalf.

THE ONE EXCEPTION, and it decides nothing (S3): when every registry call for the identifier
answered TRANSIENTLY (`registry.is_transient` — a timeout, 406, 408, 429, 5xx) and no record came
back, `admit_registry` returns `outcome='registry-transient'` without calling litkb.admit() at all.
That is not a verdict pre-empted; it is a verdict the database could only get wrong, because check
1 cannot see the difference between "no registry holds this identifier" and "the registry was down
for four minutes" and would write the first as a terminal refusal.

A file admitted IN PLACE (an existing corpus file under the literature root) is only read: its binding is
measured, its path recorded. Nothing here moves, renames or writes a file.
"""
import datetime
import re
from pathlib import Path

from litkb.acquire.store import LITERATURE_ROOT, file_facts
from litkb.admit import binding as _binding
from litkb.admit import registry as _registry
from litkb.admit.resolver import _ascii_fold
from litkb.textnorm import norm_label, normalize_doi

_STOP = {"a", "an", "the", "of", "on", "in", "for", "and", "or", "to", "with", "by", "from", "at", "as", "into",
         "via", "using", "its", "is", "are", "be", "under", "over", "between", "towards", "toward"}


class AdmissionError(RuntimeError):
    pass


class BindProbeError(AdmissionError):
    """A file offered for binding whose PAGE COUNT could not be read (`litkb.extract.probe.probe_pages`
    raised). Fail closed: the file is never attached (LITKB_WORKPLAN.md "### S4": "a PDF whose
    page-count probe ERRORS → classed `probe-error` ... and never bound").

    It carries what a quarantine row needs — the path relative to the literature root, the sha256 and
    the byte count of the refused file — so each caller can record the refusal in the place it knows
    about: `admit_registry`/`admit_manual` against the file where it lies (admission never moves a
    file), `acquire.run.attach_in_place` the same way, and `hunt` after moving its own download."""

    def __init__(self, message, *, rel_path, sha256, nbytes, probe_error):
        super().__init__(message)
        self.rel_path, self.sha256, self.nbytes, self.probe_error = rel_path, sha256, nbytes, probe_error
        self.quarantine_row = None


def _jsonb(v):
    from psycopg.types.json import Jsonb

    from litkb.textnorm import jsonb_safe

    return Jsonb(jsonb_safe(v))


def first_author_of(authors):
    """'Averkov, G. & Bianchi, G.' -> 'Averkov'; a JSON author list -> its first family name."""
    if isinstance(authors, list):
        a = authors[0] if authors else {}
        return (a.get("family") or a.get("name") or "") if isinstance(a, dict) else str(a)
    first = re.split(r"&|;| and |, et al\.?| et al\.?", authors or "")[0].strip()
    if "," in first:
        return first.split(",")[0].strip()
    parts = first.replace(".", " ").split()
    return parts[-1] if parts else ""


def make_key(first_author, year, title):
    """Surname_Year_slug (Scripts/docs/LITERATURE_CONVENTION.md): ASCII surname parts joined and capitalised,
    4-digit year, 2-5 lowercase title words with stopwords dropped, under 60 characters."""
    parts = re.findall(r"[A-Za-z]+", _ascii_fold(first_author or ""))
    # a registry that prints the surname in capitals ('PAGE', 'HAWKES') gives the convention's 'Page'; mixed-case
    # parts ('DelaCruz', 'McRoberts') are kept as printed
    surname = "".join(p[0].upper() + (p[1:].lower() if p.isupper() else p[1:]) for p in parts) or "Anon"
    words = re.findall(r"[a-z0-9]+", _ascii_fold(title or "").lower())
    kept = [w for w in words if w not in _STOP] or words
    if len(kept) < 2:
        kept = (kept + [w for w in words if w not in kept] + ["work", "record"])[:2]
    slug_words = kept[:4]
    key = f"{surname}_{int(year):04d}_{'-'.join(slug_words)}"
    while len(key) >= 60 and len(slug_words) > 2:
        slug_words = slug_words[:-1]
        key = f"{surname}_{int(year):04d}_{'-'.join(slug_words)}"
    return key[:59]


def add_candidate(conn, ws, token, *, source="manual", source_detail=None, query=None, raw=None, title=None,
                  authors=None, year=None, ids=None):
    return conn.execute(
        "SELECT litkb.add_candidate(%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)",
        (ws, token, source, source_detail, query, _jsonb(raw) if raw is not None else None, title,
         _jsonb(authors) if authors is not None else None, int(year) if year else None,
         _jsonb(ids) if ids is not None else None)).fetchone()[0]


def file_evidence(file_path, registry_title, first_author, *, root=None, source_route=None, source_url=None,
                  title_forms=()):
    """The p_file JSON for a file admitted in place. Read-only.

    `title_forms`: the other forms the registry published for this title (registry.title_forms()).
    The work is stored under the joined "title: subtitle" form since migration 0020, but the PDF's
    first page prints whichever form its publisher chose, so the binder tries all of them and records
    which one matched (binding.bind_any).
    """
    root = Path(root or LITERATURE_ROOT).resolve()
    p = Path(file_path).resolve()
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        raise AdmissionError(f"{p} is not under the literature root {root}") from None
    facts = file_facts(p)
    # The default is the unguarded one: removing the guard below leaves code that RUNS and binds with
    # `pages` NULL, rather than a NameError the harness reports as DID NOT FIRE.
    pages = None
    # BEGIN guard: a file whose page count cannot be read is never bound (admission)
    # `binding.pdf_info` never raises (S4 run 3 code survey C8), so until S4 a file whose page count
    # could not be read bound with `pages` NULL. The count now comes from the probe that CAN fail.
    from litkb.extract import probe as _probe
    try:
        pages = _probe.probe_pages(p)
    except _probe.ProbeError as e:
        raise BindProbeError(f"{rel}: the page count could not be read ({e}); the file is not bound",
                             rel_path=rel, sha256=facts["sha256"], nbytes=facts["bytes"],
                             probe_error=str(e)[:300]) from e
    # END guard: a file whose page count cannot be read is never bound (admission)
    info = _binding.pdf_info(p)
    # OCR only where the first page has no text layer to read: bind_any_with_ocr re-binds a
    # `binding-pending` and leaves every other verdict exactly as bind_any returned it.
    b = _binding.bind_any_with_ocr(p, [registry_title, *title_forms], first_author, info=info)
    txt = p.with_suffix(".txt")
    out = {"sha256": facts["sha256"], "md5": facts["md5"], "bytes": facts["bytes"], "rel_path": rel,
           "has_text_layer": b["text_layer"], "binding": b,
           "pdf_metadata": {k: v for k, v in info.items() if k in ("Title", "Author", "Subject", "Creator",
                                                                    "Producer", "CreationDate", "PDF version",
                                                                    "Encrypted", "Pages")}}
    if pages is not None:
        out["pages"] = pages
    if txt.exists():
        out["txt_extract_path"] = txt.relative_to(root).as_posix()
    if source_route:
        out["source_route"] = source_route
    if source_url:
        out["source_url"] = source_url
    return out


def _probe_refused(conn, ws, token, err):
    """Record an admission's probe refusal against the file WHERE IT LIES (admission never moves a
    file): the quarantine row IS the state (migration 0030, origin `bind-refusal`). Best-effort, like
    every quarantine row — the result rides on the exception, which the caller re-raises."""
    from litkb import quarantine as Q

    err.quarantine_row = Q.try_record(Q.record, conn, ws, token, rel_path=err.rel_path, sha256=err.sha256,
                                      nbytes=err.nbytes, reason="probe-error", origin="bind-refusal",
                                      detail={"via": "admission", "probe_error": err.probe_error})
    return err


def _labels(agent, session):
    """Agent and session labels with every invisible character removed (referee fix D7): 'sess ' is 'sess'."""
    a, s = norm_label(agent or ""), norm_label(session or "")
    if not a or not s:
        raise AdmissionError("an agent and a session label are required (invisible characters do not count)")
    return a, s


def _call_admit(conn, ws, token, candidate, route, key, work, identifiers, file_json, checks, agent, session):
    agent, session = _labels(agent, session)
    return conn.execute(
        "SELECT litkb.admit(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (ws, token, candidate, route, key, _jsonb(work), _jsonb(identifiers),
         _jsonb(file_json) if file_json is not None else None, _jsonb(checks), agent, session)).fetchone()[0]


def admit_registry(conn, ws, token, *, doi=None, arxiv=None, claimed=None, key=None, file_path=None, root=None,
                   agent, session, client=None, pacer=None, candidate_id=None, source="manual",
                   source_detail=None, extra_identifiers=()):
    """Check 1 on the registry, check 3 on the file, then litkb.admit(). -> the database's result dict."""
    if client is None:
        from litkb.netutil import Client
        client = Client()
    if pacer is None:
        from litkb.admit.resolver import REGISTRY_BACKOFF, REGISTRY_MIN_INTERVAL
        from litkb.netutil import Pacer
        pacer = Pacer(interval=REGISTRY_MIN_INTERVAL, backoff=REGISTRY_BACKOFF)
    claimed = dict(claimed or {})
    if claimed.get("authors") and not claimed.get("first_author"):
        claimed["first_author"] = first_author_of(claimed["authors"])
    # The default is the strict one, and the guard below is what relaxes it — that order matters for a
    # reason beyond taste: a mutation that deletes the guard must leave code that RUNS and behaves
    # worse, not code that raises NameError. A guard whose removal errors is reported DID NOT FIRE by
    # the harness, because the tests error instead of failing (Reports/LITKB_P3_REPORT_2026-09-15.md,
    # row P8f).
    registry_only = False
    # BEGIN guard: an admission with no claim and no file says it is registry-only
    # §8.5 of the linkage review: three DOIs were refused at check 1 with "no claimed record to
    # compare with the registry and no bound file", and the remedy was not in the message. The rule
    # is a rule about a CLAIM — a claimed first author that contradicts the registry's is exactly
    # what caught Papadakis-for-Mandilaras in that same session, and it still fires. What was
    # missing is the case where the admitter claims nothing and takes the registry record as the
    # identity. That is now sayable, and the saying is RECORDED on the identifier's evidence
    # (migration 0020, check 1) so an admission made on the registry record alone can be told apart
    # from one that was compared with something, forever after.
    registry_only = not file_path and not any(claimed.get(k) for k in ("title", "authors", "year", "first_author"))
    # END guard: an admission with no claim and no file says it is registry-only
    identifiers, checks, rec = [], {"registry_calls": [], "claimed": claimed or None,
                                    "registry_only": registry_only}, None
    if doi:
        # the canonical DOI is what is confirmed, compared and STORED (referee fix D1); the database normalises
        # it again with litkb.norm_identifier, its twin
        d = normalize_doi(doi)
        if not d:
            raise AdmissionError(f"{doi!r} is not a DOI (no '10.' prefix)")
        r, tried = _registry.confirm_doi(client, d, pacer)
        checks["registry_calls"] += [{"identifier": d, "registry": n, "status": s} for n, s in tried]
        identifiers.append({"scheme": "doi", "value": d, "verified_by": r["registry"] if r else None,
                            "evidence": _registry.evidence(r, claimed) if r else {"registry_calls": tried}})
        rec = rec or r
    if arxiv:
        r, st = _registry.arxiv_record(client, arxiv, pacer)
        checks["registry_calls"].append({"identifier": arxiv, "registry": "arxiv", "status": st})
        identifiers.append({"scheme": "arxiv", "value": arxiv.strip(), "verified_by": "arxiv" if r else None,
                            "evidence": _registry.evidence(r, claimed) if r else {"registry_calls": [("arxiv", st)]}})
        rec = rec or r
    # BEGIN guard: a registry that answered transiently is a RETRY, not a refused admission
    # Check 1 confirms the identifier against its registry, and with no record it refuses: "no doi,
    # arxiv or isbn identifier was confirmed by a registry". That sentence is TRUE of a DOI no
    # registry holds and equally true of a registry that was down for four minutes, and the
    # admission row it writes is terminal either way — 2026-09-20, arXiv 2412.05728, refused twice
    # on a 406 and admitted on the third call 4m17s later. The two are told apart by the STATUS the
    # registry answered with (`registry.is_transient`), which is the only evidence there is, and
    # the transient one writes NOTHING: no admission row, no refusal, no candidate consumed. The
    # caller is handed a result whose outcome names it, so every existing caller (hunt, the CLI,
    # the migrate passes) reads it exactly where it already reads a non-`admitted` outcome.
    if rec is None and (doi or arxiv):
        transient = [c for c in checks["registry_calls"] if _registry.is_transient(c["status"])]
        if transient:
            return {"outcome": "registry-transient", "registry_calls": checks["registry_calls"],
                    "transient": transient, "retryable": True,
                    "identifier": str(doi or arxiv),
                    "message": ("the registry answered "
                                + ", ".join(f"{c['registry']} {c['status']}" for c in transient)
                                + f" for {doi or arxiv} — a transient answer, not a verdict on the "
                                  "record. Nothing was admitted and nothing was written; hunt the "
                                  "reference again.")}
    # END guard: a registry that answered transiently is a RETRY, not a refused admission
    if registry_only:
        for i in identifiers:
            if i.get("verified_by"):
                i["evidence"] = dict(i.get("evidence") or {}) | {"registry_only": True}
    identifiers.extend(extra_identifiers)
    if rec:
        work = _registry.work_fields(rec)
        first = rec["first_author"]
        forms = _registry.title_forms(rec)
    else:
        work = {"type": "article", "title": claimed.get("title") or "(no registry record)",
                "year": int(claimed["year"]) if str(claimed.get("year") or "").isdigit() else None}
        first = claimed.get("first_author") or ""
        forms = []
    year = work.get("year") or claimed.get("year") or 0
    key = key or make_key(first, year, work["title"])
    file_json = None
    if file_path:
        try:
            file_json = file_evidence(file_path, work["title"], first, root=root, title_forms=forms)
        except BindProbeError as e:
            # BEGIN call site: a registry admission's probe refusal gets its database row
            raise _probe_refused(conn, ws, token, e)
            # END call site: a registry admission's probe refusal gets its database row
    if candidate_id is None:
        candidate_id = add_candidate(
            conn, ws, token, source=source, source_detail=source_detail, title=claimed.get("title") or work["title"],
            authors=claimed.get("authors") if isinstance(claimed.get("authors"), (list, dict)) else
            ([claimed["authors"]] if claimed.get("authors") else None),
            year=claimed.get("year") or work.get("year"),
            ids={k: v for k, v in (("doi", doi), ("arxiv", arxiv)) if v})
    checks["measured_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    res = _call_admit(conn, ws, token, candidate_id, "registry", key, work, identifiers, file_json, checks,
                      agent, session)
    # BEGIN guard: a claim that lacks the subtitle is a discrepancy, not a refusal
    d = _registry.subtitle_discrepancy(rec, claimed) if rec else None
    if d:
        row = str(doi or arxiv or key)
        try:
            d["id"] = record_discrepancy(conn, ws, token, source="admission", source_row=row, agent=agent,
                                         session=session, work_id=res.get("work_id"), candidate_id=candidate_id, **d)
        except Exception as e:                  # a discrepancy is review material; it never fails an admission
            d["not_recorded"] = f"{type(e).__name__}: {e}"
        res = dict(res) | {"title_discrepancy": d}
    # END guard: a claim that lacks the subtitle is a discrepancy, not a refusal
    return res


def record_discrepancy(conn, ws, token, *, source, source_row, field, claimed, registry, agent, session,
                       ratio=None, detail=None, work_id=None, candidate_id=None):
    """litkb.record_discrepancy (migration 0015): a disagreement kept, never a correction.

    `source` is 'tracker', 'manifest' or — since migration 0020 — 'admission', for a disagreement
    between what an ADMISSION claimed and the registry record it was admitted as.
    """
    # %s::numeric on the ratio: a Python float binds as double precision and there is no implicit
    # double -> numeric resolution, so the unqualified call finds no function at all.
    return conn.execute(
        "SELECT litkb.record_discrepancy(%s, %s, %s, %s, %s, %s, %s, %s::numeric, %s, %s, %s, %s, %s)",
        (ws, token, source, source_row, field, claimed, registry, ratio,
         _jsonb(detail or {}), work_id, candidate_id, agent, session)).fetchone()[0]


def admit_manual(conn, ws, token, *, title, authors, year, file_path, source_note, work_type="report", key=None,
                 identifiers=(), root=None, agent, session, candidate_id=None):
    """A work no registry can confirm (older proceedings, reports): a PROPOSAL until another session approves.
    The held file must carry the title on its first page (check 3 against the claimed title)."""
    first = first_author_of(authors)
    fam_list = authors if isinstance(authors, list) else [
        {"family": first_author_of(a.strip()), "given": ""} for a in re.split(r"&|;| and ", authors or "") if a.strip()]
    work = {"type": work_type, "title": title, "authors": fam_list, "year": int(year) if year else None}
    ids = [{"scheme": i["scheme"], "value": i["value"], "verified_by": "manual",
            "evidence": {"source": source_note}} for i in identifiers]
    try:
        file_json = file_evidence(file_path, title, first, root=root) if file_path else None
    except BindProbeError as e:
        # BEGIN call site: a manual admission's probe refusal gets its database row
        raise _probe_refused(conn, ws, token, e)
        # END call site: a manual admission's probe refusal gets its database row
    if candidate_id is None:
        candidate_id = add_candidate(conn, ws, token, source="manual", source_detail=source_note, title=title,
                                     authors=fam_list, year=year)
    return _call_admit(conn, ws, token, candidate_id, "manual", key or make_key(first, year or 0, title), work, ids,
                       file_json, {"manual_source": source_note}, agent, session)


WEB_SNAPSHOT_DIR = "web"        # under <root>/_litkb_staging/


def web_snapshot_evidence(snapshot_path, title, first_author, *, url, retrieved, root=None, store=None,
                          title_forms=(), stem=None):
    """The p_file JSON for a source whose evidence is a saved TEXT snapshot, not a PDF.

    `Scripts/docs/LITERATURE_CONVENTION.md`: "Where a source has no DOI (blog posts, docs), record it
    as a manual proposal with the URL and retrieval date." Measured against the machinery
    (`Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8.4), that was not possible: `admit --manual`
    requires `--file`, and check 3 binds the claimed title against the first page of a PDF TEXT
    LAYER, so the Crossref relationships page — saved as HTML — came back
    `refused at check4_manual: "no text layer on the first page and no PDF title match"`. Six sources
    that review depends on therefore have no KB record, which is the thing the KB exists to prevent.
    The reviewer explicitly did NOT work around it by generating a PDF from the page text, and that
    was right: fabricating a document to satisfy the binder defeats the check rather than passing it.

    So the snapshot is the file. It is the admitter's own saved text of the page, it lands under
    `_litkb_staging/web/` through the store's one guarded write path, and check 3 runs against it
    exactly as it runs against a PDF's first page — same binder, same 0.85, same author-near-title
    rule. Nothing in the database is relaxed: `_check_binding` only ever read `binding.text_layer`
    and the ratio, and a text snapshot has both honestly.

    The URL is `source_url`, the retrieval date is `obtained_at`, and `copy_kind` is `'web snapshot'`
    (migration 0020) so a snapshot can never be mistaken for a publisher PDF. The admission remains a
    MANUAL proposal: a second session must approve it (check 4, unchanged).
    """
    from litkb.acquire.store import Store

    store = store or Store(root=root)
    src = Path(snapshot_path).resolve()
    if not src.exists():
        raise AdmissionError(f"no snapshot at {src}")
    if src.suffix.lower() != ".txt":
        raise AdmissionError(f"a web snapshot is the saved TEXT of the page, not {src.suffix or 'a directory'}: "
                             "save the page's text as .txt and pass that")
    data = src.read_bytes()
    text = data.decode("utf-8", "replace")
    webdir = store.staging / WEB_SNAPSHOT_DIR
    if store._inside(src, webdir):
        landed = src
    else:
        landed = store.write_new(store.free_name(webdir, stem or src.stem, ".txt"), data)
    facts = file_facts(landed)
    b = _binding.bind_any(landed, [title, *title_forms], first_author, page_text=text, info={})
    rel = store.rel(landed)
    return {"sha256": facts["sha256"], "md5": facts["md5"], "bytes": facts["bytes"], "rel_path": rel,
            "has_text_layer": b["text_layer"], "binding": b, "copy_kind": "web snapshot",
            "source_route": "web", "source_url": url, "obtained_at": retrieved,
            "txt_extract_path": rel, "pages": None}


def web_pdf_evidence(pdf_path, title, first_author, *, url, retrieved, root=None, title_forms=()):
    """The p_file JSON for a web source whose document IS a PDF — the file bound with the admission.

    Why this exists rather than `acquire --from-file` after the admission, which is the sequence
    the hunt protocol reads as though it worked: a web source is a MANUAL admission, so its work
    is a proposal and `works.current_version_id` stays NULL until a second session approves it —
    and `litkb.attach_file` (migration 0013) opens with "a file attaches only to an admitted work"
    and RAISES on exactly that. The file therefore has to arrive WITH the admission or not at all,
    and the admission is the one path that writes a file version for a work in proposal mode.

    The binding is the ordinary one, against the PDF's own first page: check 3 reads a real text
    layer here, which is stronger evidence than :func:`web_snapshot_evidence`'s saved page text,
    not weaker. What the URL contributes is provenance — `source_route`, `source_url` and the
    retrieval date as `obtained_at` — because a page changes under a citation.

    `copy_kind` is deliberately left unset. 0020's vocabulary is publisher / author manuscript /
    preprint / scan / web snapshot, and a PDF served from a project's own repository is none of
    them; inventing a sixth value would need a migration, and claiming one of the five would be a
    claim nothing measured.
    """
    out = file_evidence(pdf_path, title, first_author, root=root, source_route="web",
                        source_url=str(url), title_forms=title_forms)
    out["obtained_at"] = str(retrieved)
    return out


def admit_web(conn, ws, token, *, title, authors, year, url, retrieved, snapshot_path, source_note,
              work_type="report", key=None, identifiers=(), root=None, store=None, agent, session,
              candidate_id=None, pdf_path=None):
    """A documentation page, blog post or standard with no DOI: a manual PROPOSAL bound to its saved
    text snapshot. Second-session approval still applies — this is `admit --manual` with a different
    kind of evidence, not a different kind of admission.

    `pdf_path` (added 2026-09-16 with `litkb hunt`): the source is a DOCUMENT at that URL, not a
    page. The PDF is then the bound evidence (`web_pdf_evidence`) and the snapshot — the document's
    own first-page text — is still landed under `_litkb_staging/web/` and recorded on the
    admission's checks, so the convention's "URL, retrieval date and a saved snapshot" is satisfied
    by a record that also carries the file itself."""
    if not url or not str(url).lower().startswith(("http://", "https://")):
        raise AdmissionError("a web source needs its URL (http:// or https://)")
    if not retrieved:
        raise AdmissionError("a web source needs the date it was retrieved (the page can change under the citation)")
    first = first_author_of(authors)
    fam_list = authors if isinstance(authors, list) else [
        {"family": first_author_of(a.strip()), "given": ""} for a in re.split(r"&|;| and ", authors or "") if a.strip()]
    work = {"type": work_type, "title": title, "authors": fam_list, "year": int(year) if year else None,
            "publisher": None}
    ids = [{"scheme": i["scheme"], "value": i["value"], "verified_by": "manual",
            "evidence": {"source": source_note}} for i in identifiers]
    ids.append({"scheme": "url", "value": str(url), "verified_by": "manual",
                "evidence": {"source": source_note, "retrieved": str(retrieved)}})
    k = key or make_key(first, year or 0, title)
    snap = web_snapshot_evidence(snapshot_path, title, first, url=url, retrieved=retrieved, root=root,
                                 store=store, stem=k)
    # the PDF is the evidence when there is one; the snapshot is landed either way, and the checks
    # record where it went so the page's own words stay findable beside the file
    file_json = (web_pdf_evidence(pdf_path, title, first, url=url, retrieved=retrieved, root=root)
                 if pdf_path else snap)
    web = {"url": str(url), "retrieved": str(retrieved), "snapshot": snap["rel_path"],
           "snapshot_binding": snap["binding"]["verdict"]}
    if pdf_path:
        web["document"] = file_json["rel_path"]
    if candidate_id is None:
        candidate_id = add_candidate(conn, ws, token, source="manual", source_detail=source_note, title=title,
                                     authors=fam_list, year=year, ids={"url": str(url)})
    return _call_admit(conn, ws, token, candidate_id, "manual", k, work, ids, file_json,
                       {"manual_source": source_note, "web": web}, agent, session)


def approve(conn, ws, token, admission_id, agent, session):
    """The approver's labels are compared with the admitter's after invisible characters are removed, here and
    again by the database (admissions_second_session_signs_off, migration 0014)."""
    agent, session = _labels(agent, session)
    row = conn.execute("SELECT admitter_session FROM litkb.admissions WHERE id = %s", (admission_id,)).fetchone()
    # BEGIN guard: approve compares labels without invisible characters (Python)
    if row and norm_label(row[0]) == session:
        raise AdmissionError("the admitter's own session cannot approve its admission (invisible characters ignored)")
    # END guard: approve compares labels without invisible characters (Python)
    return conn.execute("SELECT litkb.approve_admission(%s, %s, %s, %s, %s)",
                        (ws, token, admission_id, agent, session)).fetchone()[0]

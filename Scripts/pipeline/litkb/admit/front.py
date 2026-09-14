"""The Python front of admission (design §4.6): registries and the PDF on this side, one database call.

    cand = add_candidate(conn, ws, token, source="manual", title=..., authors=..., year=..., ids={...})
    res  = admit_registry(conn, ws, token, doi="10.4171/jems/179", claimed={...}, file_path=..., ...)
    res  = admit_manual(conn, ws, token, title=..., authors=..., year=..., file_path=..., source_note=...)
    res  = approve(conn, approver_ws, approver_token, admission_id, agent, session)

Every call binds the token as a query parameter, never in the SQL text (workstream.py, third referee F-8).
litkb.admit() in the database does checks 1-5 in one transaction and records a refusal as a refused
admission row; this module never pre-decides a duplicate or a refusal on the database's behalf.

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


def _jsonb(v):
    from psycopg.types.json import Jsonb

    return Jsonb(v)


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
    surname = "".join(p[0].upper() + p[1:] for p in parts) or "Anon"
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


def file_evidence(file_path, registry_title, first_author, *, root=None, source_route=None, source_url=None):
    """The p_file JSON for a file admitted in place. Read-only."""
    root = Path(root or LITERATURE_ROOT).resolve()
    p = Path(file_path).resolve()
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        raise AdmissionError(f"{p} is not under the literature root {root}") from None
    facts = file_facts(p)
    info = _binding.pdf_info(p)
    b = _binding.bind(p, registry_title, first_author, info=info)
    txt = p.with_suffix(".txt")
    out = {"sha256": facts["sha256"], "md5": facts["md5"], "bytes": facts["bytes"], "rel_path": rel,
           "has_text_layer": b["text_layer"], "binding": b,
           "pdf_metadata": {k: v for k, v in info.items() if k in ("Title", "Author", "Subject", "Creator",
                                                                    "Producer", "CreationDate", "PDF version",
                                                                    "Encrypted", "Pages")}}
    if (info.get("Pages") or "").isdigit():
        out["pages"] = int(info["Pages"])
    if txt.exists():
        out["txt_extract_path"] = txt.relative_to(root).as_posix()
    if source_route:
        out["source_route"] = source_route
    if source_url:
        out["source_url"] = source_url
    return out


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
    identifiers, checks, rec = [], {"registry_calls": [], "claimed": claimed or None}, None
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
    identifiers.extend(extra_identifiers)
    if rec:
        work = _registry.work_fields(rec)
        first = rec["first_author"]
    else:
        work = {"type": "article", "title": claimed.get("title") or "(no registry record)",
                "year": int(claimed["year"]) if str(claimed.get("year") or "").isdigit() else None}
        first = claimed.get("first_author") or ""
    year = work.get("year") or claimed.get("year") or 0
    key = key or make_key(first, year, work["title"])
    file_json = None
    if file_path:
        file_json = file_evidence(file_path, work["title"], first, root=root)
    if candidate_id is None:
        candidate_id = add_candidate(
            conn, ws, token, source=source, source_detail=source_detail, title=claimed.get("title") or work["title"],
            authors=claimed.get("authors") if isinstance(claimed.get("authors"), (list, dict)) else
            ([claimed["authors"]] if claimed.get("authors") else None),
            year=claimed.get("year") or work.get("year"),
            ids={k: v for k, v in (("doi", doi), ("arxiv", arxiv)) if v})
    checks["measured_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return _call_admit(conn, ws, token, candidate_id, "registry", key, work, identifiers, file_json, checks,
                       agent, session)


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
    file_json = file_evidence(file_path, title, first, root=root) if file_path else None
    if candidate_id is None:
        candidate_id = add_candidate(conn, ws, token, source="manual", source_detail=source_note, title=title,
                                     authors=fam_list, year=year)
    return _call_admit(conn, ws, token, candidate_id, "manual", key or make_key(first, year or 0, title), work, ids,
                       file_json, {"manual_source": source_note}, agent, session)


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

"""Acquire a file for an admitted work, route by route, and record every attempt (design §10, §14 P2).

    out = acquire(conn, ws, token, work, store=Store(), routes=("open_access", "annas", "scihub"),
                  agent=..., session=..., budget=Budget(max_archive_downloads=5, quota_margin=50))

Route order is the convention's: open access, then Anna's Archive by DOI, then Sci-Hub by DOI; the browser is
last and is not automated: when nothing else lands a file, a `browser` attempt with status `manual-step` says
how to hand the file in (`py -3.12 -m litkb acquire --key K --from-file PATH`).

For every downloaded byte string, in this order:
  1. sha256 against the database's files      -> `duplicate-held`, nothing written
  2. sha256 against every PDF on disk         -> `duplicate-held`, nothing written
  3. land in _litkb_staging/incoming + .txt extract at once
  4. bind against the work's registry title and first author (check 3)
       fails -> moved to _quarantine (`binding-failed` / `binding-pending`)
  5. litkb.attach_file() (the database re-checks binding and sha256), then the file moves to
     _litkb_staging/filed/<stem>.pdf inside the same transaction -> `ok`

Dead routes are not retried blindly: a route whose earlier attempt for this work ended in a terminal miss
(DEAD_STATUSES) is skipped unless retry_dead. Anna's Archive's rolling quota: every download's downloads_left is
recorded; once it is at or below the safety margin, or this run's cap on archive downloads is reached, the
archive route stops and records `quota-stop`.
"""
import datetime
from dataclasses import dataclass, field
from pathlib import Path

from litkb.acquire.store import Store, file_facts
from litkb.admit import binding as _binding
from litkb.netutil import Pacer, add_secret, redact

ROUTES = ("open_access", "annas", "scihub")
DEAD_STATUSES = {"open_access": {"no-oa-copy"}, "annas": {"not-in-archive", "record-mismatch", "unresolved"},
                 "scihub": {"not-in-archive"}}


@dataclass
class Budget:
    max_archive_downloads: int = 5
    quota_margin: int = 50
    used: int = 0
    stopped: str = ""
    downloads_left: list = field(default_factory=list)


def _jsonb(v):
    from psycopg.types.json import Jsonb

    return Jsonb(v)


def work_record(conn, *, key=None, doi=None, work_id=None):
    """Main's view of an admitted work: id, key, title, year, first author, doi, arxiv, active file."""
    if work_id is None and key:
        row = conn.execute("SELECT id FROM litkb.works WHERE key = %s", (key,)).fetchone()
        work_id = row[0] if row else None
    if work_id is None and doi:
        row = conn.execute("SELECT work_id FROM litkb.main_identifiers WHERE scheme = 'doi' AND active "
                           "AND value_norm = litkb.norm_identifier('doi', %s)", (doi,)).fetchone()
        work_id = row[0] if row else None
    if work_id is None:
        return None
    w = conn.execute("SELECT work_id, key, title, year, authors FROM litkb.main_works WHERE work_id = %s",
                     (work_id,)).fetchone()
    if not w:
        return None
    ids = dict(conn.execute("SELECT scheme, value FROM litkb.main_identifiers WHERE work_id = %s AND active "
                            "AND scheme IN ('doi', 'arxiv')", (work_id,)).fetchall())
    held = conn.execute("SELECT count(*) FROM litkb.main_files WHERE work_id = %s AND status = 'active'",
                        (work_id,)).fetchone()[0]
    authors = w[4] or []
    first = (authors[0].get("family") or authors[0].get("name") or "") if authors and isinstance(authors[0], dict) else ""
    return {"work_id": w[0], "key": w[1], "title": w[2], "year": w[3], "first_author": first,
            "doi": ids.get("doi"), "arxiv": ids.get("arxiv"), "held_files": held}


def prior_attempts(conn, work_id):
    return conn.execute("SELECT route, status, identifier_used, at FROM litkb.acquisition_attempts "
                        "WHERE work_id = %s ORDER BY at", (work_id,)).fetchall()


def record_attempt(conn, ws, token, work_id, route, identifier, status, detail, codes=None):
    return conn.execute(
        "SELECT litkb.record_acquisition_attempt(%s, %s, %s, NULL, %s, %s, %s, %s, %s)",
        (ws, token, work_id, route, identifier, status, _jsonb(_redacted(detail)),
         [int(c) for c in (codes or [])] or None)).fetchone()[0]


def _redacted(obj):
    # BEGIN guard: attempt details are redacted
    if isinstance(obj, dict):
        return {k: _redacted(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redacted(v) for v in obj]
    return redact(obj) if isinstance(obj, str) else obj
    # END guard: attempt details are redacted


def land_and_attach(conn, ws, token, work, data, *, route, source_url, store, index, agent, session):
    """Steps 1-5 of the module docstring. -> (status, detail)."""
    facts = {"sha256": __import__("hashlib").sha256(data).hexdigest(),
             "md5": __import__("hashlib").md5(data).hexdigest(), "bytes": len(data)}
    sha = facts["sha256"]
    # BEGIN guard: acquisition sha256 dedupe against the database
    row = conn.execute("SELECT f.id, fv.work_id, fv.rel_path FROM litkb.files f "
                       "LEFT JOIN litkb.file_versions fv ON fv.version_id = f.current_version_id "
                       "WHERE f.sha256 = %s", (sha,)).fetchone()
    if row:
        return "duplicate-held", {"sha256": sha, "held_as_file": str(row[0]), "held_for_work": str(row[1]),
                                  "rel_path": row[2], "note": "already in the database; nothing written"}
    # END guard: acquisition sha256 dedupe against the database
    # BEGIN guard: acquisition sha256 dedupe against the disk
    if sha in index["sha256"]:
        return "duplicate-held", {"sha256": sha, "on_disk": index["sha256"][sha],
                                  "note": "already on disk; nothing written"}
    # END guard: acquisition sha256 dedupe against the disk
    pdf, txt = store.land(data, work["key"], sha)
    info = _binding.pdf_info(pdf)
    b = _binding.bind(pdf, work["title"], work["first_author"], info=info)
    detail = {"sha256": sha, "md5": facts["md5"], "bytes": facts["bytes"], "binding": b, "source_url": source_url}
    # BEGIN guard: a file that does not bind is quarantined
    if b["verdict"] != "bound":
        qpdf, _qtxt = store.to_quarantine(pdf, txt, work["key"], b["verdict"], sha)
        detail["quarantined"] = store.rel(qpdf)
        return b["verdict"], detail
    # END guard: a file that does not bind is quarantined
    final = store.free_name(store.filed, work["key"])
    fjson = {"sha256": sha, "md5": facts["md5"], "bytes": facts["bytes"], "rel_path": store.rel(final),
             "has_text_layer": b["text_layer"], "binding": b, "source_route": route, "source_url": source_url,
             "obtained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "pdf_metadata": {k: v for k, v in info.items() if k in ("Title", "Author", "Subject", "Creator",
                                                                      "Producer", "PDF version", "Pages")}}
    if (info.get("Pages") or "").isdigit():
        fjson["pages"] = int(info["Pages"])
    if txt:
        fjson["txt_extract_path"] = store.rel(final.with_suffix(".txt"))
    with conn.transaction():
        res = conn.execute("SELECT litkb.attach_file(%s, %s, %s, %s, %s, %s)",
                           (ws, token, work["work_id"], _jsonb(fjson), agent, session)).fetchone()[0]
        detail["attach"] = {k: v for k, v in res.items() if k != "binding"}
        if res["outcome"] == "attached":
            moved, _t = store.to_filed(pdf, txt, work["key"])
            if moved != final:
                raise RuntimeError(f"filed as {moved}, recorded as {final}")
            detail["filed"] = store.rel(moved)
            return "ok", detail
    status = "duplicate-held" if res["outcome"] == "duplicate-file" else "binding-failed"
    qpdf, _qtxt = store.to_quarantine(pdf, txt, work["key"], status, sha)
    detail["quarantined"] = store.rel(qpdf)
    return status, detail


def acquire(conn, ws, token, work, *, store=None, routes=ROUTES, agent, session, budget=None, retry_dead=False,
            clients=None, pacer=None, annas_session=None, annas_pacer=None, printer=print, from_file=None):
    """-> {"outcome": ..., "attempts": [(route, status), ...]}"""
    from litkb.acquire import annas as _annas
    from litkb.acquire import open_access as _oa
    from litkb.acquire import scihub as _sh

    store = store or Store()
    budget = budget or Budget()
    clients = clients or {}
    pacer = pacer or Pacer(interval=3.0)
    attempts = []
    if work["held_files"] and from_file is None:
        return {"outcome": "already-held", "attempts": attempts}
    index = store.disk_index()
    wid = work["work_id"]

    if from_file is not None:
        data = Path(from_file).read_bytes()
        if not data.startswith(b"%PDF-"):
            status, detail = "bad-file", {"from_file": str(from_file), "note": "not a PDF"}
        else:
            status, detail = land_and_attach(conn, ws, token, work, data, route="browser",
                                             source_url=f"manual file {Path(from_file).name}", store=store,
                                             index=index, agent=agent, session=session)
        record_attempt(conn, ws, token, wid, "browser", work.get("doi") or work.get("arxiv"), status, detail)
        attempts.append(("browser", status))
        return {"outcome": status, "attempts": attempts}

    prior = prior_attempts(conn, wid)
    for route in routes:
        ident = work.get("doi") if route != "open_access" else (work.get("doi") or work.get("arxiv"))
        # BEGIN guard: dead routes are not retried blindly
        dead = [p for p in prior if p[0] == route and p[1] in DEAD_STATUSES.get(route, ())]
        if dead and not retry_dead:
            printer(f"  {route}: skipped, attempt of {dead[-1][3]:%Y-%m-%d} ended {dead[-1][1]} (--retry-dead to try again)")
            continue
        # END guard: dead routes are not retried blindly
        if route in ("annas", "scihub") and not work.get("doi"):
            printer(f"  {route}: skipped, by DOI only and the work has no DOI")
            continue
        codes = []
        if route == "open_access":
            r = _oa.fetch_open_access(work.get("doi"), work.get("arxiv"), pacer, client=clients.get("open_access"))
        elif route == "scihub":
            r = _sh.fetch_scihub(work["doi"], pacer, client=clients.get("scihub"))
        elif route == "annas":
            # BEGIN guard: the archive route stops at the quota margin or the run cap
            if budget.stopped or budget.used >= budget.max_archive_downloads:
                reason = budget.stopped or f"this run's cap of {budget.max_archive_downloads} archive downloads is used"
                record_attempt(conn, ws, token, wid, "annas", ident, "quota-stop", {"reason": reason})
                attempts.append(("annas", "quota-stop"))
                continue
            # END guard: the archive route stops at the quota margin or the run cap
            if annas_session is None:
                annas_session = _annas.open_session()
            aclient, key = annas_session
            add_secret(key)             # an injected session's key is redacted like open_session()'s
            if aclient is None:
                record_attempt(conn, ws, token, wid, "annas", ident, "api-error", {"reason": "login failed"})
                attempts.append(("annas", "api-error"))
                continue
            r = _annas.fetch_for_litkb(aclient, key, work["doi"], annas_pacer or Pacer(), known_md5=index["md5"].keys())
            if r["downloads_left"] not in ("", None):
                budget.downloads_left.append(r["downloads_left"])
                if str(r["downloads_left"]).isdigit() and int(r["downloads_left"]) <= budget.quota_margin:
                    budget.stopped = (f"downloads_left {r['downloads_left']} is at or below the safety margin "
                                      f"{budget.quota_margin}")
            # BEGIN guard: an issued download URL spends the run cap
            # the archive counts a download when it issues the URL, so a partner 404 or a bad file spends one too
            if r.get("url_issued"):
                budget.used += 1
            # END guard: an issued download URL spends the run cap
        else:
            raise ValueError(f"unknown route {route!r}")
        codes = r.get("http_codes") or []
        detail = {k: r.get(k) for k in ("detail", "tried", "via", "md5", "record_doi", "title_best",
                                        "downloads_left", "rec_size") if r.get(k) not in (None, "", [])}
        if r["status"] == "downloaded":
            status, landed = land_and_attach(conn, ws, token, work, r["pdf"], route=route,
                                             source_url=redact(r.get("source_url") or
                                                               (f"annas md5:{r['md5']}" if route == "annas" else "")),
                                             store=store, index=index, agent=agent, session=session)
            detail.update(landed)
        elif r["status"] == "hash-mismatch" and r.get("pdf"):
            sha = __import__("hashlib").sha256(r["pdf"]).hexdigest()
            pdf, txt = store.land(r["pdf"], work["key"], sha)
            qpdf, _ = store.to_quarantine(pdf, txt, work["key"], "hash-mismatch", sha)
            status, detail["quarantined"] = "hash-mismatch", store.rel(qpdf)
        else:
            status = r["status"]
        record_attempt(conn, ws, token, wid, route, ident, status, detail, codes)
        attempts.append((route, status))
        printer(f"  {route}: {status}")
        if status == "ok":
            return {"outcome": "ok", "attempts": attempts, "detail": detail}
        if status == "duplicate-held":
            return {"outcome": "duplicate-held", "attempts": attempts, "detail": detail}
    if not any(p[0] == "browser" and p[1] == "manual-step" for p in prior) or retry_dead:
        record_attempt(conn, ws, token, wid, "browser", work.get("doi"), "manual-step",
                       {"instruction": "no automated route landed a file; fetch it in one browser session, then "
                                       f"py -3.12 -m litkb acquire --key {work['key']} --from-file <path>"})
        attempts.append(("browser", "manual-step"))
    return {"outcome": "not-acquired", "attempts": attempts}


def file_from_path_facts(path):
    return file_facts(path)

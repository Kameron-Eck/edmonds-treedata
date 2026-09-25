"""Acquire a file for an admitted work, route by route, and record every attempt (design §10, §14 P2).

    out = acquire(conn, ws, token, work, store=Store(), routes=("open_access", "annas", "scihub"),
                  agent=..., session=..., budget=Budget(max_archive_downloads=5, quota_margin=50))

Route order is the convention's: open access, then Anna's Archive by DOI, then Sci-Hub by DOI; the browser is
last and is not automated: when nothing else lands a file, a `browser` attempt with status `manual-step` says
how to hand the file in (`py -3.12 -m litkb acquire --key K --from-file PATH`).

For every downloaded byte string, in this order (a rung's bytes meet the ACCEPTANCE TEST first, `_land` ->
litkb.acquire.accept.offer_to_bind, which refuses into _quarantine with its sub-status and hands on what it accepts):
  0. shape: %PDF- header, %%EOF near the end   -> neither: straight to _quarantine with a .reason.json (`bad-file`)
  1. sha256 against the database's files      -> `duplicate-held`, nothing written
  2. sha256 against every PDF on disk         -> a copy NO files row holds is not a duplicate: named on the
                                                 attempt (`unowned_on_disk`), left where it lies (FX-B)
  3. land in _litkb_staging/incoming + .txt extract at once
  4. bind against the work's registry title and first author (check 3)
       fails -> moved to _quarantine (`binding-failed` / `binding-pending`)
  5. litkb.attach_file() (the database re-checks binding and sha256), then the file moves to
     _litkb_staging/filed/<stem>.pdf inside the same transaction -> `ok`

NOTHING DOWNLOADED IS DISCARDED (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9). Bytes a route refused - an
HTML error page served as a .pdf, a bot challenge, a partner error, a file whose md5 is not the record's - come
back in the route's `rejected` (or `pdf`, for hash-mismatch) and are written into _quarantine/ with a
<name>.reason.json beside them. Acquisition holds no delete path at all, so a bad download is kept and named
instead of being removed to free the name; qc/test_litkb_p2.py scans these modules for one.

Dead routes are not retried blindly: a route whose earlier attempt for this work ended in a terminal miss
(DEAD_STATUSES) is skipped unless retry_dead — unless that attempt's own `retriable` fact says asking again
could change the answer (guard 15; fix round 2). Anna's Archive's rolling quota (Budget): the account-wide counter on
the account page is read before every download request and is the authority; the route records `quota-stop` and
requests no download URL when the counter is at limit - margin or cannot be read. This run's cap on issued download
URLs, and the API's downloads_left against the same margin, stay as second, local guards.

THE RUNG REGISTRY (S4.5 items 1-2, builder C1a). The routes are RUNGS in an ordered, staged registry (`RUNGS`;
stages in `litkb.acquire.policy.STAGES` order: A, B, C, E, the shadow tier LAST), so a new rung is a module that
registers itself and never an edit of the loop. The rung interface is one line:

    rung.fn(work, ctx) -> route dict   (the keys are listed on `Rung`; a rung never touches the database)

and the loop does everything around it, for every rung alike:
  * a skip is an attempt with a reason, never silence (guard 14): `skipped` with `no_identifier`,
    `dead_route` (DEAD_STATUSES), `dead_in_run` (`blocked` is dead for a route within a run — the
    workstream — plan item 2), `backoff_window` (the persisted per-(route, work) refusal ladder,
    litkb.acquire.backoff) or `policy_refused` (the pre-fetch PolicyDecision, guard 21);
  * the declarative ladder budget (guard 12) is checked between every stage and rung, and runs out as a
    `budget-stop` row on route `ladder`;
  * Stage B's rungs run concurrently (wall-clock = the slowest), bounded by the budget's concurrency; every
    database write stays on this thread, in registry order;
  * a transient answer gets ONE scheduled in-run retry (rungs that opt in), recorded with `retry_of`;
  * THE IN-RUN COOL-DOWN (S4.5 decisions D41, D44, D45; litkb.acquire.backoff): a HOST that answered 429 or 503
    (never a 403, guard 29; never a bot challenge) cools for the rest of its wait, for EVERY route: every rung call
    runs under a request gate (`backoff.Gate` as `netutil.REQUEST_GATE`) that sends no request to that host until
    cool_until, while other hosts are asked (a multi-host rung skips the one URL and records it —
    `detail.cooldown_skipped` — and its row is retriable); a rung stopped by it before asking anything is
    `skipped/backoff_window` with `detail.cooldown` naming the host and the route whose answer cooled it — for a
    single-host rung the whole rung. No row sits out a long wait (a scheduled retry's or a pacing wait over
    `backoff.IN_ROW_WAIT_MAX_S`): the host cools instead. The state is the run's `backoff.HostCooldowns`, kept in
    `pacing` under `backoff.HOSTS_KEY` — in a live process `PACING`, which the run driver's hunt and measure rows
    share, so it survives across works in one process; a new process starts cold;
  * the served bytes' sha256 is checked against the refused-bytes record BEFORE anything is written
    (the rejected-hash lookup): a match is never landed or quarantined again (`known-bad`);
  * every rung's bytes go through THE ACCEPTANCE TEST (litkb.acquire.accept, S4.5 item 5: "the bytes
    through the same acceptance test as every route") before they bind — `accept.offer_to_bind` is the
    landing — and a `bad-file` row's sub-status is that test's own word (seam integrator-w1);
  * every attempt row carries its sub-status, served sha256, terminal facts, retriable and kind (0033);
  * MEASURE mode (S4.5 decision D9; `measure`, the run driver's hook): every rung is asked — a work's
    earlier terminal misses do not skip one — every answer recorded and judged by the acceptance test,
    and nothing is landed or quarantined; the run driver uses it for works that already hold a file.
"""
import datetime
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from litkb import config as _config
from litkb.acquire import accept as _accept
# seam builder-C2a: Stage A (zero network) prepares every work before its first rung (acquire, below)
from litkb.acquire import stage_a as _stage_a
from litkb.acquire import backoff as _backoff
from litkb.acquire import ledger as _ledger
from litkb.acquire import policy as _policy
from litkb.acquire import recovery as _recovery
from litkb.acquire.store import QUARANTINE, STAGING, Store, file_facts, pdf_shape, reason_path
from litkb.admit import binding as _binding
from litkb import netutil as _netutil
from litkb.netutil import Pacer, add_secret, redact

ROUTES = ("open_access", "annas", "scihub")
DEAD_STATUSES = {"open_access": {"no-oa-copy"}, "annas": {"not-in-archive", "record-mismatch", "unresolved"},
                 "scihub": {"not-in-archive"}}
#: plan item 2: `blocked` is DEAD for a route within a run (the 2026-09-22 Sci-Hub diagnosis: every blocked
#: DOI was retried until sci-hub.ru's rate gate). A run is the workstream; across runs the back-off governs.
DEAD_IN_RUN_STATUSES = {"blocked"}
MODES = ("acquire", "measure")


@dataclass
class Budget:
    """The archive's spending limits for one run of acquire() calls.

    quota_margin (default 50): the AUTHORITY is the account-wide counter on GET /account/ ("Fast downloads used
    (last 18 hours): N / M", annas.read_quota). Before every download request the counter is read, and no download
    URL is requested when N >= M - quota_margin, or when the counter cannot be read (fail closed). 50 of the
    account's 1000 is head-room for downloads spent in the same 18-hour window by the browser or another session
    between the read and the request, and for the counter itself lagging a spend. The same margin also stops the
    route once the API's own downloads_left falls to it.
    max_archive_downloads (default 5): a LOCAL second guard, counted on download URLs issued in this run."""
    max_archive_downloads: int = 5
    quota_margin: int = 50
    used: int = 0
    stopped: str = ""
    downloads_left: list = field(default_factory=list)
    counter: list = field(default_factory=list)      # one {used_before, used_after, limit, margin} per archive attempt


def _jsonb(v):
    from psycopg.types.json import Jsonb

    from litkb.textnorm import jsonb_safe

    return Jsonb(jsonb_safe(v))


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
    # seam builder-C2b: venue / volume / issue / pages and the `pii` identifier are what Stage C's per-publisher URL
    # rules read (litkb.acquire.landing: MDPI's CDN path, Elsevier's PII -> pdfft; the pii from builder B1's harvest)
    w = conn.execute("SELECT work_id, key, title, year, authors, subtitle, venue, volume, issue, pages "
                     "FROM litkb.main_works WHERE work_id = %s", (work_id,)).fetchone()
    if not w:
        return None
    rows = conn.execute("SELECT scheme, value FROM litkb.main_identifiers WHERE work_id = %s AND active "
                        "AND scheme IN ('doi', 'arxiv', 'pii') ORDER BY scheme, value", (work_id,)).fetchall()
    ids, dois = {}, [v for s, v in rows if s == "doi"]
    for scheme, value in rows:
        ids.setdefault(scheme, value)
    # BEGIN guard: a work reached by one of its DOIs is acquired by that DOI
    # (Page 1954 carries an OUP and a JSTOR DOI; --doi <one of them> must not query the archive with the other)
    if doi:
        from litkb.textnorm import normalize_doi
        want = normalize_doi(doi)
        ids["doi"] = next((v for v in dois if normalize_doi(v) == want), ids.get("doi"))
    # END guard: a work reached by one of its DOIs is acquired by that DOI
    held = conn.execute("SELECT count(*) FROM litkb.main_files WHERE work_id = %s AND status = 'active'",
                        (work_id,)).fetchone()[0]
    authors = w[4] or []
    first = (authors[0].get("family") or authors[0].get("name") or "") if authors and isinstance(authors[0], dict) else ""
    return {"work_id": w[0], "key": w[1], "title": w[2], "year": w[3], "first_author": first,
            "subtitle": w[5], "title_forms": _title_forms(w[2], w[5]),
            "doi": ids.get("doi"), "dois": dois, "arxiv": ids.get("arxiv"), "held_files": held,
            "pii": ids.get("pii"), "venue": w[6], "volume": w[7], "issue": w[8], "pages": w[9]}


def _title_forms(title, subtitle):
    """The forms of a work's title a first page might print, the work's OWN title first.

    Since migration 0020 a work is stored under the registry title joined with its subtitle ("Magellan: toward
    building entity matching management systems"), while the publisher prints whichever form it chose - often the
    bare one. Both are the same paper, so the binder tries both (admit/binding.py::bind_any, the rule
    judge_candidate has always used on the registry side) and records which one matched. forms[0] stays the work's
    stored title, because that is what the database's _check_binding compares a binding's registry_title against.

    This INVERTS admit/registry.py::work_title, which JOINS a registry record's title and subtitle into the form a
    work is stored under: acquisition holds no registry record, only the stored work, so it splits that form back
    into the two a page might print. Same rule, opposite direction, one home each."""
    title, sub = (title or "").strip(), (subtitle or "").strip()
    forms = [title] if title else []
    if title and sub and title.lower().endswith(sub.lower()):
        bare = title[:-len(sub)].strip().rstrip(":-–—").strip()   # registry.work_title joins with ": "
        if bare and bare not in forms:
            forms.append(bare)
    return forms


def _forms(work):
    """The title forms to bind a file for `work` against (work_record fills them; a bare dict still works)."""
    return work.get("title_forms") or [work["title"]]


def prior_attempts(conn, work_id):
    """-> [(route, status, identifier_used, at, workstream_id, retriable), ...] for the work, all time, oldest
    first. `retriable` (0033; NULL on every row written before it) is what the dead checks read (guard 15)."""
    return conn.execute("SELECT route, status, identifier_used, at, workstream_id, retriable "
                        "FROM litkb.acquisition_attempts WHERE work_id = %s ORDER BY at", (work_id,)).fetchall()


def _ts(v):
    """An ISO timestamp string (a route's `terminal.at`) -> datetime; a datetime passes; else None."""
    if v is None or isinstance(v, datetime.datetime):
        return v
    try:
        return datetime.datetime.fromisoformat(str(v))
    except ValueError:
        return None


def record_attempt(conn, ws, token, work_id, route, identifier, status, detail, codes=None, *, sub_status=None,
                   served_sha256=None, terminal=None, retriable=None, kind=None, retry_of=None):
    """ONE writer of `acquisition_attempts` (0033's record_acquisition_attempt). `terminal` is a route's
    {"url", "status_code", "at"}: its URL is redacted here like the detail (the one redaction point of a row)."""
    t = terminal or {}
    return conn.execute(
        "SELECT litkb.record_acquisition_attempt(%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s)",
        (ws, token, work_id, route, identifier, status, _jsonb(_redacted(detail)),
         [int(c) for c in (codes or [])] or None, sub_status, served_sha256,
         _redacted(t.get("url")) or None, t.get("status_code"), _ts(t.get("at")), retriable, kind,
         retry_of)).fetchone()[0]


def _redacted(obj):
    # BEGIN guard: attempt details are redacted
    if isinstance(obj, dict):
        return {k: _redacted(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redacted(v) for v in obj]
    return redact(obj) if isinstance(obj, str) else obj
    # END guard: attempt details are redacted


def _reason(work, *, status, label, shape, reason, route, source_url, sha, nbytes, **extra):
    """What a quarantined file's .reason.json says. One composer, so every path writes the same fields.

    `status` is the attempt status the database holds (its vocabulary, 0013_admission.sql); `label` is the word in
    the file's own name; `shape` is what the bytes are (store.pdf_shape). `source_url` arrives REDACTED from the
    caller: this module adds no redaction site of its own (the routes redact what they return, and acquire()
    redacts the URL it hands on), and a reason file is written to disk, where an unredacted key would outlive the
    run."""
    return {"status": status, "label": label, "shape": shape, "reason": reason, "route": route,
            "source_url": source_url or "", "sha256": sha, "bytes": nbytes, "work_key": work["key"],
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra}


def quarantine_bytes(store, work, data, *, label, status, shape, reason, route, source_url, **extra):
    """Bytes acquisition received and cannot use, KEPT: written into _quarantine/ with the reason beside them.

    The rule (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9): acquisition never discards a download. A file that
    is not a PDF, one that stopped mid-transfer, one whose bytes are not the record's - each is written down with
    what was wrong with it, so that nobody has to delete one to carry on. -> the detail fields to record."""
    sha = hashlib.sha256(data).hexdigest()
    why = _reason(work, status=status, label=label, shape=shape, reason=reason, route=route, source_url=source_url,
                  sha=sha, nbytes=len(data), **extra)
    qpdf, _qtxt, qwhy = store.quarantine_new(data, work["key"], label, sha, why)
    return {"sha256": sha, "bytes": len(data), "note": reason, "quarantined": store.rel(qpdf),
            "quarantine_reason": store.rel(qwhy)}


def land_and_attach(conn, ws, token, work, data, *, route, source_url, store, index, agent, session, copy_kind=None,
                    acceptance=None):
    """Steps 0-5 of the module docstring. -> (status, detail). `copy_kind` is the article version the route
    knew (guard 23; `policy.COPY_KIND_OF_VERSION`), written on the file version; the text extract's word
    count is written beside the page count (0033 `file_versions.word_count`). `acceptance` is the acceptance
    test's verdict summary for an operator's file (`--from-file`, S4.5 decision D17): written on the file
    version's `binding` so the PROPOSAL carries it to the second-session approver (integrator-w2)."""
    # BEGIN guard: a download that is not a whole PDF is quarantined, never discarded
    # Before the dedupe, deliberately: a re-download truncated the same way twice would otherwise read as
    # `duplicate-held` against a byte-identical copy filed earlier, and duplicate-held STOPS the route loop - so a
    # broken transfer would end the fetch instead of moving on to the next route.
    shape, why = pdf_shape(data)
    if shape != "pdf":
        return "bad-file", quarantine_bytes(store, work, data, label=shape, status="bad-file", shape=shape,
                                            reason=why, route=route, source_url=source_url)
    # END guard: a download that is not a whole PDF is quarantined, never discarded
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
    # the unguarded default: a copy anywhere on disk is a duplicate — the rule that refused Kats_2019's own arXiv bytes
    on_disk = list(index["sha256"].get(sha) or [])
    unowned = []
    # BEGIN guard: bytes on disk that no files row holds are not a duplicate
    # (S4.5 fix wave FX-B; referee-stage-b N3.) ONLY BYTES A `files` ROW HOLDS MAKE A DUPLICATE, and the database
    # dedupe above has already answered for every one of them. A copy the disk index still finds here is one no `files`
    # row holds — a hand-placed file in a topic folder, a legacy manifest's copy, an orphan in filed/ — and it made the
    # ladder answer `duplicate-held`, which STOPS the ladder, while the work stayed without a file: on the ladder-1 run
    # the arXiv rung reached Kats_2019's own PDF (L005, register E03) and refused it against
    # `Validation/Kats_2019b_soft-staple-algorithm-combined.pdf`, a copy the database does not own. The bytes now land
    # and bind like any others; the unowned copy is named on the attempt (`unowned_on_disk`) and left exactly where it
    # lies (acquisition never moves or deletes a file it did not create).
    unowned, on_disk = on_disk, []
    # END guard: bytes on disk that no files row holds are not a duplicate
    if on_disk:
        return "duplicate-held", {"sha256": sha, "on_disk": on_disk, "note": "already on disk; nothing written"}
    pdf, txt = store.land(data, work["key"], sha)
    # The default is the unguarded one, so removing the guard below leaves code that RUNS and binds
    # with `pages` NULL — the mutation the S4 known-bad `fire_probe` makes — rather than a NameError
    # the harness would report as DID NOT FIRE (Reports/LITKB_P3_REPORT_2026-09-15.md, row P8f).
    pages = None
    # BEGIN guard: a landed file whose page count cannot be read is never bound
    # `binding.pdf_info` never raises: a failing `pdfinfo` returns {} and the file bound with `pages`
    # NULL (S4 run 3 code survey C8). The page count now comes from the one probe that CAN fail
    # (litkb.extract.probe, the same count the extraction queue and the readability classifier read),
    # and when it fails the file is quarantined `probe-error` and never offered to attach_file.
    from litkb.extract import probe as _probe
    try:
        pages = _probe.probe_pages(pdf)
    except _probe.ProbeError as e:
        why = "the page count could not be read; never bound (fail closed)"
        qpdf, _qtxt = store.to_quarantine(pdf, txt, work["key"], "probe-error", sha, reason=_reason(
            work, status="bad-file", label="probe-error", shape="pdf", reason=why, route=route,
            source_url=source_url, sha=sha, nbytes=facts["bytes"], probe_error=str(e)[:300]))
        return "bad-file", {"sha256": sha, "md5": facts["md5"], "bytes": facts["bytes"],
                            "source_url": source_url, "probe_error": str(e)[:300], "note": why,
                            "quarantined": store.rel(qpdf), "quarantine_reason": store.rel(reason_path(qpdf)),
                            **({"unowned_on_disk": unowned} if unowned else {})}
    # END guard: a landed file whose page count cannot be read is never bound
    info = _binding.pdf_info(pdf)
    # every title form, not only the work's stored one (_title_forms): the page prints the publisher's choice
    # ... and, where the landed page has no text layer at all, again on Docling's OCR of it
    b = _binding.bind_any_with_ocr(pdf, _forms(work), work["first_author"], info=info)
    detail = {"sha256": sha, "md5": facts["md5"], "bytes": facts["bytes"], "binding": b, "source_url": source_url}
    if unowned:
        detail["unowned_on_disk"] = unowned         # S4.5 fix wave FX-B: the copy no files row holds, left where it lies
    # BEGIN guard: a file that does not bind is quarantined
    if b["verdict"] != "bound":
        qpdf, _qtxt = store.to_quarantine(pdf, txt, work["key"], b["verdict"], sha, reason=_reason(
            work, status=b["verdict"], label=b["verdict"], shape="pdf", route=route, source_url=source_url,
            sha=sha, nbytes=facts["bytes"], binding=b,
            reason="the file's first page does not bind to the work's title and first author"))
        detail["quarantined"] = store.rel(qpdf)
        detail["quarantine_reason"] = store.rel(reason_path(qpdf))
        return b["verdict"], detail
    # END guard: a file that does not bind is quarantined
    final = store.free_name(store.filed, work["key"])
    fjson = {"sha256": sha, "md5": facts["md5"], "bytes": facts["bytes"], "rel_path": store.rel(final),
             "has_text_layer": b["text_layer"], "binding": b, "source_route": route, "source_url": source_url,
             "obtained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "pdf_metadata": {k: v for k, v in info.items() if k in ("Title", "Author", "Subject", "Creator",
                                                                      "Producer", "PDF version", "Pages")}}
    if pages is not None:
        fjson["pages"] = pages
    if txt:
        fjson["txt_extract_path"] = store.rel(final.with_suffix(".txt"))
        words = _ledger.word_count_of_file(txt)
        if words is not None:
            fjson["word_count"] = words
    if copy_kind:
        fjson["copy_kind"] = copy_kind
    if acceptance is not None:
        fjson["binding"] = {**b, "acceptance": acceptance}
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
    qpdf, _qtxt = store.to_quarantine(pdf, txt, work["key"], status, sha, reason=_reason(
        work, status=status, label=status, shape="pdf", route=route, source_url=source_url, sha=sha,
        nbytes=facts["bytes"], attach=detail["attach"],
        reason=f"the database refused the file: attach_file answered {res['outcome']}"))
    detail["quarantined"] = store.rel(qpdf)
    detail["quarantine_reason"] = store.rel(reason_path(qpdf))
    return status, detail


def _in_topic_folder(store, path):
    """Under the literature root, outside staging and quarantine: a file acquisition did not create."""
    p = Path(path).resolve()
    return store._inside(p, store.root) and not store._inside(p, store.staging) and not store._inside(p, store.quarantine)


def index_of_held(store, index):
    """The disk hash index with incoming/ and _quarantine/ dropped. -> a new index, the argument untouched.

    The disk dedupe answers ONE question: does the corpus already hold this paper? Two folders under the
    literature root are not holdings, and counting them cost two works their file:

      * _litkb_staging/incoming/ is a LANDING area - a file there belongs to nobody yet. `acquire --from-file
        _litkb_staging/incoming/X.pdf` used to hash the bytes, find their own hash in the index, answer
        `duplicate-held` and never run binding, so the work could never get its file; the workaround in the field
        was to rename the file to `.download`, which is how workarounds become folklore (live, 2026-09-15).
      * _quarantine/ holds exactly the files that are NOT held: a paper quarantined for a wrong or missing
        registry record was "already on disk" for ever afterwards, so correcting the record could never let the
        same bytes bind (Konda_2016, Kopcke_2010 and Enamorado_2019 were locked this way in the live store).
        Re-binding one is now just `acquire --from-file <the quarantined path>`: it lands a fresh copy, binds it
        and files it, and the quarantined copy and its .reason.json stay exactly where they are as the record of
        what happened - acquisition still deletes nothing.

    The guard that protects the corpus is untouched: the same sha256 held in the DATABASE is still `duplicate-held`
    (a copy filed elsewhere under the literature root that no files row holds is named, not a duplicate: S4.5 fix
    wave FX-B, `land_and_attach`). So is the archive's own quota short-circuit, which
    asks the FULL index a different question - do we have these bytes at all - and so still refuses to spend a
    download for bytes that are sitting in quarantine."""
    skip = (f"{STAGING}/incoming/", f"{QUARANTINE}/")
    out = {}
    for algo, by_hash in index.items():
        kept = {h: [r for r in rels if not r.startswith(skip)] for h, rels in by_hash.items()}
        out[algo] = {h: rels for h, rels in kept.items() if rels}
    return out


def from_file_not_a_pdf(store, work, from_file, data, shape, why):
    """`--from-file` was pointed at something that is not a whole PDF. -> the detail fields to record.

    A file acquisition did NOT create is never moved and never copied: the refusal is recorded and the file stays
    exactly where it lies (store.move_new refuses it in any case). A file already under _litkb_staging IS
    acquisition's own tree - it is where a hand fetch lands, and the file of §8.9 was one - so it moves into
    _quarantine with a reason beside it, under the work's key, with its own name recorded in the reason. That is
    the whole answer to the incident: the name is freed for the re-fetch without deleting anything."""
    sha = hashlib.sha256(data).hexdigest()
    detail = {"from_file": str(from_file), "shape": shape, "sha256": sha, "bytes": len(data), "note": why}
    if not store._inside(Path(from_file), store.staging):
        detail["note"] = (f"{why}; left exactly where it lies: acquisition never moves or copies a file it did "
                          f"not create")
        return detail
    was = store.rel(from_file)                      # the name it came in under, before the move takes it away
    txt = Path(from_file).with_suffix(".txt")
    why_json = _reason(work, status="bad-file", label=shape, shape=shape, reason=why, route="browser",
                       source_url=f"manual file {Path(from_file).name}", sha=sha, nbytes=len(data), moved_from=was)
    qpdf, _qtxt = store.to_quarantine(from_file, txt if txt.exists() else None, work["key"], shape, sha, reason=why_json)
    qwhy = reason_path(qpdf)                        # to_quarantine wrote it (S4.5 item 8)
    detail["moved_from"] = was
    detail["quarantined"], detail["quarantine_reason"] = store.rel(qpdf), store.rel(qwhy)
    return detail


def attach_in_place(conn, ws, token, work, path, *, store, agent, session, acceptance=None):
    """A file already held in a topic folder (Validation/, ...) and held by no work: hashed and bound where it lies,
    then litkb.attach_file() with rel_path = its own path. Never copied, moved or written (front.file_evidence only
    reads it); a file that does not bind is left where it lies. -> (status, detail). `acceptance`: as
    `land_and_attach`'s (S4.5 decision D17, integrator-w2)."""
    from litkb.admit import front

    rel = store.rel(path)
    try:
        fjson = front.file_evidence(path, work["title"], work["first_author"], root=store.root,
                                    source_route="held-in-place", source_url=f"in place {rel}",
                                    title_forms=_forms(work)[1:])
    except front.BindProbeError as e:
        # the probe guard lives in front.file_evidence; here the refusal becomes an attempt, and the
        # file (which acquisition did not create) stays exactly where it lies. acquire() records the
        # quarantine state against this path: for a file refused in place the row IS the state.
        return "bad-file", {"sha256": e.sha256, "bytes": e.nbytes, "probe_error": e.probe_error,
                            "in_place": rel,
                            "note": "the page count could not be read; not bound, left where it lies"}
    b = fjson["binding"]
    detail = {"sha256": fjson["sha256"], "md5": fjson["md5"], "bytes": fjson["bytes"], "binding": b, "in_place": rel}
    if b["verdict"] != "bound":
        detail["note"] = "not bound; left where it lies (acquisition never moves a file it did not create)"
        return b["verdict"], detail
    fjson["obtained_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if acceptance is not None:
        fjson["binding"] = {**b, "acceptance": acceptance}
    with conn.transaction():
        res = conn.execute("SELECT litkb.attach_file(%s, %s, %s, %s, %s, %s)",
                           (ws, token, work["work_id"], _jsonb(fjson), agent, session)).fetchone()[0]
    detail["attach"] = {k: v for k, v in res.items() if k != "binding"}
    if res["outcome"] == "attached":
        detail["filed"] = rel
        return "ok", detail
    return ("duplicate-held" if res["outcome"] == "duplicate-file" else "binding-failed"), detail


def quarantine_state(conn, ws, token, work, status, route, detail, attempt_id):
    """The database row for what one attempt quarantined (migration 0030). -> None when the attempt
    quarantined nothing, else `quarantine.try_record`'s result, which NEVER raises: the bytes have
    already moved, and a missing row is exactly what `quarantine.quarantined_without_db_state` counts.

    Called once per attempt, AFTER `record_attempt`, so the row links the attempt that refused the
    bytes. Every quarantine this module makes leaves `detail["quarantined"]` (the moved path), whose
    NAME carries the label `Store.to_quarantine`/`quarantine_new` gave it; that label is the reason,
    read back from the one place it was written. `detail["in_place"]` with `probe_error` is the
    refusal of a topic-folder file that is never moved (`attach_in_place`)."""
    from litkb import quarantine as Q

    rel = detail.get("quarantined")
    if rel:
        parsed = Q.parse_name(Path(rel).name)
        reason = parsed["label"] if parsed else None
        origin = Q.origin_of_label(reason)
    elif detail.get("probe_error") and detail.get("in_place"):
        rel, reason, origin = detail["in_place"], "probe-error", "bind-refusal"
    else:
        return None
    return Q.try_record(Q.record, conn, ws, token, rel_path=rel, sha256=detail.get("sha256"),
                        nbytes=detail.get("bytes") or 0, reason=reason, origin=origin,
                        work_id=work["work_id"], attempt_id=attempt_id,
                        detail={"attempt_status": status, "route": route,
                                "note": detail.get("probe_error") or detail.get("note") or ""})


# ── the rung registry ────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Rung:
    """One rung of the acquisition ladder. THE RUNG INTERFACE:

        fn(work, ctx) -> dict           (a rung never touches the database: the loop records)

    `work` is `work_record`'s dict; `ctx` is the `RungContext`. The dict a rung returns:
        status       `downloaded`, or an attempt status (no-oa-copy, bad-file, blocked, not-in-archive,
                     quota-stop, api-error, ...: 0013 + 0033)
        pdf          the PDF bytes when downloaded (or a real PDF that is not the record's: hash-mismatch)
        rejected     bytes the rung was SERVED and refused, with `rejected_url` — kept, never dropped
        source_url, tried (the rung's own tokens), http_codes (every status it saw, in order), detail (a note)
        terminal     {"url", "status_code", "at", "headers"} of the response that decided the attempt
        optional     sub_status (the rung's own typing; else litkb.acquire.ledger types it), kind,
                     version (submittedVersion / acceptedVersion / publishedVersion), retriable,
                     policy (the per-host PolicyDecisions it made), reason, and the archive's keys
                     (via, md5, record_doi, title_best, downloads_left, rec_size, quota)
    `needs`: the identifiers of which the work must hold at least ONE (else a `skipped/no_identifier`
    row); `concurrent`: runs beside the other concurrent rungs of its stage; `retry_transient`: a
    transient answer gets one scheduled in-run retry (a rung with its own retries says False)."""
    route: str
    fn: object = field(repr=False, compare=False)
    needs: tuple = ("doi",)
    concurrent: bool = False
    retry_transient: bool = False
    #: seam builder-C2a: a rung that yields identifiers, never a file (OpenCitations META, the NCBI converter):
    #: its measure is `identifiers: <route>=<works gaining>/<asked>`, not a yield line (S4.5 decision D19)
    metadata_only: bool = False
    #: seam builder-C2a: a rung asked only under a stated condition (the closure rule's Wave 2: a DataCite prefix, a
    #: held PMCID ...; litkb.acquire.stage_b.ASK_CONDITIONS); skipped by it on every row it reached, its report line
    #: is `not-asked: <route> <works> <condition>` (auditor-C2a round 2 F3). '' = asks every row that reaches it
    ask_condition: str = ""
    #: S4.5 fix wave FX-B: a rung whose answer carries a harvest (litkb.acquire.stage_b.HARVESTS) — after the ladder has
    #: landed the file it is still asked, in HARVEST-ONLY mode (`RungContext.harvest_only`), if the ladder had not
    #: reached it: the identifier waves complete (referee-stage-b N2), the file rungs stop at the first landing
    harvests: bool = False

    @property
    def stage(self):
        return _policy.STAGE_OF[self.route]


@dataclass
class RungContext:
    """What a rung is handed. Nothing here is a database connection."""
    clients: dict
    pacer: object
    budget: Budget
    index: dict
    printer: object
    mode: str = "acquire"
    #: seam builder-C2c: the dead URLs Stage E is asked about (litkb.acquire.recovery) — the ledger's, read by the
    #: loop before the first rung, then this run's, added as each answer is recorded: {url, route, status, origin}
    recovery_urls: list = field(default_factory=list)
    annas_session: object = None
    annas_pacer: object = None
    legit_hit: bool = False           # a legitimate rung has answered a hit in this ladder run
    #: seam builder-C2a: the work's class by Stage A's router (A2; litkb.acquire.stage_a) — `decide` consults it
    work_class: str = ""
    landed: bool = False              # a rung has landed the file (acquire mode)
    decisions: dict = field(default_factory=dict)   # route -> the PolicyDecision taken BEFORE it was asked
    #: seam builder-C2b: every non-PDF page a rung of THIS ladder run was served ({route, url, status, headers,
    #: body}), in the order met — Stage C's leads (litkb.acquire.landing follows the pointers they carry)
    leads: list = field(default_factory=list)
    #: S4.5 fix wave FX-B: the ladder's post-landing identifier pass is running — a rung makes its identifier call and
    #: asks no file candidate (litkb.acquire.stage_b.fetch_candidates)
    harvest_only: bool = False

    def decide(self, route, host="*"):
        # seam builder-C2a: the work-class router refuses a shadow line for a preprint / book / HTML-only work
        return _stage_a.routed(_policy.decide(route, host, legit_hit=self.legit_hit), self.work_class)


def _rung_open_access(work, ctx):
    from litkb.acquire import open_access as _oa
    return _oa.fetch_open_access(work.get("doi"), work.get("arxiv"), ctx.pacer, client=ctx.clients.get("open_access"))


def _rung_scihub(work, ctx):
    from litkb.acquire import scihub as _sh
    decisions = [ctx.decide("scihub", _host(m)) for m in _config.SCIHUB_MIRRORS]
    mirrors = tuple(m for m, d in zip(_config.SCIHUB_MIRRORS, decisions) if d.allowed)
    if not mirrors:
        return {"status": "skipped", "sub_status": "policy_refused",
                "policy": [d.as_detail() for d in decisions]}
    r = _sh.fetch_scihub(work["doi"], ctx.pacer, client=ctx.clients.get("scihub"), mirrors=mirrors)
    r["policy"] = [d.as_detail() for d in decisions]
    codes = r.get("http_codes") or []
    r.setdefault("terminal", {"url": r.get("rejected_url") or r.get("source_url") or "",
                              "status_code": codes[-1] if codes else None,
                              "at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return r


def _rung_annas(work, ctx):
    from litkb.acquire import annas as _annas
    budget = ctx.budget
    # BEGIN guard: the archive route stops at the quota margin or the run cap
    if budget.stopped or budget.used >= budget.max_archive_downloads:
        reason = budget.stopped or f"this run's cap of {budget.max_archive_downloads} archive downloads is used"
        return {"status": "quota-stop", "reason": reason}
    # END guard: the archive route stops at the quota margin or the run cap
    if ctx.annas_session is None:
        ctx.annas_session = _annas.open_session()
    aclient, key = ctx.annas_session
    add_secret(key)             # an injected session's key is redacted like open_session()'s
    if aclient is None:
        return {"status": "api-error", "reason": "login failed"}
    r = _annas.fetch_for_litkb(aclient, key, work["doi"], ctx.annas_pacer or Pacer(), known_md5=ctx.index["md5"].keys(),
                               quota_margin=budget.quota_margin)
    if r.get("quota"):
        budget.counter.append(r["quota"])
    if r["status"] == "quota-stop":
        budget.stopped = r["detail"]
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
    codes = r.get("http_codes") or []
    r.setdefault("terminal", {"url": "", "status_code": codes[-1] if codes else None,
                              "at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return r


def _host(url):
    import urllib.parse
    return urllib.parse.urlparse(url).netloc or url


#: The registry: today's three routes, in the order the convention gives them, now as rungs. A new rung
#: (Stage A/B/C/E, bban) is appended by its own module (`register`), never by editing the loop.
RUNGS = [
    Rung("open_access", _rung_open_access, needs=("doi", "arxiv"), concurrent=True, retry_transient=True),
    # the archive route retries inside itself (annas.download_pdf's domain ladder, resolve's 429 retry)
    Rung("annas", _rung_annas, needs=("doi",)),
    # Sci-Hub's mirrors are its own retries; one sweep per run (decisions.yaml litkb-scihub-parked)
    Rung("scihub", _rung_scihub, needs=("doi",)),
]


def register(rung, rungs=None, *, policy_lines=()):
    """Append a rung to the registry (RUNGS by default). Its route must be in the 0033 route vocabulary and
    staged, and a route is registered once. `policy_lines` are the rung's OWN pre-fetch lines
    (`policy.PolicyLine`, one per host it asks — guard 21), declared in the rung's module beside the rung and
    added to the one `policy.POLICY` here (`policy.add_lines` checks each: its route is this rung's, its tier
    is its stage's, no (route, host) twice). A rung that ends up with no line is REFUSED here, at import:
    `decide` refuses a route no line names, so such a rung would be `skipped/policy_refused` on every work —
    recorded, but a zero-yield rung nobody asked for (auditor-C1a F4)."""
    rungs = RUNGS if rungs is None else rungs
    if rung.route not in _policy.ROUTES_ALL or rung.route not in _policy.STAGE_OF:
        raise ValueError(f"{rung.route!r} is not a staged route of litkb.acquire.policy.ROUTES_ALL")
    if any(r.route == rung.route for r in rungs):
        raise ValueError(f"a rung for {rung.route!r} is already registered")
    _policy.add_lines(policy_lines, route=rung.route)
    # BEGIN guard: a registered rung has its pre-fetch policy line
    if _policy.line_for(rung.route)[1] is None:
        raise ValueError(f"no litkb.acquire.policy.POLICY line names {rung.route!r}: pass the rung's own "
                         f"policy_lines to register(), or every work would skip it as policy_refused")
    # END guard: a registered rung has its pre-fetch policy line
    rungs.append(rung)
    return rung


def ladder_rungs(routes, rungs=None):
    """The rungs to run for `routes`, in stage order and then registry order. An unknown route raises."""
    rungs = RUNGS if rungs is None else rungs
    by_route = {r.route: r for r in rungs}
    for route in routes:
        if route not in by_route:
            raise ValueError(f"unknown route {route!r}")
    order = {s: i for i, s in enumerate(_policy.STAGES)}
    chosen = [r for r in rungs if r.route in set(routes)]
    return sorted(chosen, key=lambda r: (order[r.stage], rungs.index(r)))


def ladder_routes(rungs=None):
    """EVERY route the registry holds, in stage order and then registry order: the whole ladder, as `hunt` and the
    run driver's MEASURE hook ask it (seam integrator-w2; S4.5 decision D19: a rung that registers is reached by
    `hunt`, not only by a caller that names it). `ROUTES` stays today's three for the callers that read it as
    that set (`litkb acquire`'s default `--routes`, the S4 readability grade)."""
    rungs = RUNGS if rungs is None else rungs
    return tuple(r.route for r in ladder_rungs([r.route for r in rungs], rungs))


#: In-run AIMD pacing per route (litkb.acquire.backoff.Aimd), shared by every acquire() in this process —
#: a run's pacing state. Not persisted (guard 3's "not persisted" and the module docstring of backoff).
#: It also carries the run's IN-RUN COOL-DOWNS, per host and shared by every route (S4.5 decisions D41, D44, D45:
#: `backoff.HostCooldowns` under `backoff.HOSTS_KEY`): the ladder-1 run driver
#: (`qc/instruments/litkb_ladder_run.py`) runs every row in ONE process — its hunt rows through
#: `hunt._default_acquire`, its measure rows through `measure`, both passing no `pacing` — so a host cooled by
#: one work stays cooled for the works after it until its cool_until. A new process starts cold (this dict is
#: empty at import); the skip rows in the ledger say what the previous process knew.
PACING = {}


def _identifier(rung, work):
    """The identifier the rung is asked with, or None when the work holds none of the ones it needs."""
    for scheme in rung.needs:
        if work.get(scheme):
            return work[scheme]
    return None


def _skip_reason(conn, rung, work, prior, ws, retry_dead, ctx, bo):
    """-> (sub_status, detail) when this rung must NOT be asked now, else None. Checked in order: the work
    holds no identifier the rung needs; a dead route; `blocked` earlier in this run; the refusal ladder's
    window; the pre-fetch policy. (The in-run cool-down of a HOST is not a skip here: it is the request gate's,
    `_call_rung` — S4.5 decision D44.)"""
    route = rung.route
    if _identifier(rung, work) is None:
        return "no_identifier", {"needs": list(rung.needs)}
    # BEGIN guard: dead-ness is a per-attempt retriable fact, never the status word alone
    # (plan item 1, guard 15.) An attempt whose own `retriable` is true said that asking again soon could change
    # the answer, so it is never evidence that the route is dead for this work — whatever its status word
    # (auditor-C1a F1: a transient Unpaywall failure booked a dead `no-oa-copy` and retired open access for
    # ever). Rows written before 0033 carry NULL and keep the status rule; a `blocked` row is never retriable
    # (backoff.classify: a challenge is never transient), so `dead_in_run` is unchanged.
    prior = [p for p in prior if p[5] is not True]
    # END guard: dead-ness is a per-attempt retriable fact, never the status word alone
    # BEGIN guard: dead routes are not retried blindly
    # (MEASURE mode asks a route whose earlier answer was a terminal MISS: the measurement IS the question —
    # S4.5 decision D9, "every rung is asked"; the run driver's hook contract. A refusal is not a miss:
    # `blocked` in the run and the back-off window below still hold in MEASURE mode. Seam integrator-w1.)
    dead = [p for p in prior if p[0] == route and p[1] in DEAD_STATUSES.get(route, ())]
    if dead and not retry_dead and ctx.mode != "measure":
        return "dead_route", {"prior_status": dead[-1][1], "prior_at": str(dead[-1][3])}
    # END guard: dead routes are not retried blindly
    # BEGIN guard: blocked is dead for a route within a run
    in_run = [p for p in prior if p[0] == route and p[1] in DEAD_IN_RUN_STATUSES and str(p[4]) == str(ws)]
    if in_run and not retry_dead:
        return "dead_in_run", {"prior_status": in_run[-1][1], "prior_at": str(in_run[-1][3])}
    # END guard: blocked is dead for a route within a run
    # BEGIN guard: a route inside its back-off window is skipped
    state = _backoff.load(conn, route, work["work_id"])
    until = _backoff.in_window(state, _backoff.db_now(conn))
    if until is not None and not retry_dead:
        return "backoff_window", {"next_allowed_at": str(until), "refusals": state["refusals"]}
    # END guard: a route inside its back-off window is skipped
    d = ctx.decide(route)
    if ctx.mode == "measure":
        # S4.5 decision D18 (seam integrator-w2): MEASURE mode asks the legitimate tiers only — a work that holds a
        # file never spends an archive download or asks the shadow stage (litkb.acquire.policy.measure_decision)
        d = _policy.measure_decision(d)
    ctx.decisions[route] = d.as_detail()        # recorded on the attempt row that follows it
    # BEGIN guard: a rung the policy refuses is recorded and never asked
    if not d.allowed:
        return "policy_refused", {"policy": d.as_detail()}
    # END guard: a rung the policy refuses is recorded and never asked
    return None


class _GatedClient:
    """S4.5 decision D44: an INJECTED client (a test's stub, a replay's) seen through the same request gate
    `netutil.Client.get` consults — so a cooling host is never asked through it either, and its answers tell the
    gate which host said what. Every other attribute is the client's own."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def get(self, url, *a, **k):
        gate = _netutil.REQUEST_GATE.get()
        if gate is not None:
            gate.before(url)
        st, hd, body = self._inner.get(url, *a, **k)
        if gate is not None:
            gate.after(url, st, hd, body)
        return st, hd, body


def _gated(clients):
    """The injected clients as the rungs will see them: through the request gate (a `netutil.Client` consults it
    itself and is handed on as it is)."""
    out = dict(clients or {})
    # BEGIN guard: an injected client is seen through the request gate
    out = {k: (v if (v is None or isinstance(v, _netutil.Client)) else _GatedClient(v)) for k, v in out.items()}
    # END guard: an injected client is seen through the request gate
    return out


def _cooled_answer(e, gate):
    """S4.5 decision D44: a rung stopped by the request gate (`netutil.HostCooling`: its next request was to a host
    cooling down in this run) -> the route dict. Nothing asked yet: `skipped/backoff_window` naming the host — for a
    single-host rung that is the whole rung, as D41 had it. Something asked first: those answers are the row's
    (`api-error`, retriable: asking after the cool-down can change it), never dropped."""
    obs = list(gate.observed) if gate is not None else []
    if not obs:
        return {"status": "skipped", "sub_status": "backoff_window", "cooldown": e.facts}
    last = obs[-1]
    return {"status": "api-error", "retriable": True, "http_codes": [o["status"] for o in obs],
            "terminal": {"url": last["url"], "status_code": last["status"],
                         "at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            "cooldown": e.facts,
            "detail": f"stopped before asking {e.host}: it is cooling down in this run until "
                      f"{e.facts.get('cool_until')} (S4.5 decision D44)"}


def _call_rung(rung, work, ctx, gate=None):
    """-> (route dict, exception or None). THE ROUTE BOUNDARY: a rung that raises is an api-error attempt. The call
    runs under `gate` (S4.5 decision D44: `netutil.REQUEST_GATE` for this call, in this thread's context), whose
    record rides on the route dict as `cooldown_gate`."""
    token = _netutil.REQUEST_GATE.set(gate)
    try:
        r, exc = _call_rung_gated(rung, work, ctx, gate)
    finally:
        _netutil.REQUEST_GATE.reset(token)
    if gate is not None:
        r["cooldown_gate"] = gate.summary()
    return r, exc


def _call_rung_gated(rung, work, ctx, gate):
    # BEGIN guard: a route that RAISES is a recorded api-error attempt, never a hunt-wide traceback
    # Until S3 an exception out of any route call — a socket reset the client did not model, a parser that
    # met a shape it did not expect, an archive page that changed — propagated out of acquire(), out of
    # hunt._spend_on_held, and into hunt()'s generic boundary, which answered `refused: "error"`. TWO things
    # were lost there: the attempt row (so `acquisition_attempts` held no trace that the route was ever
    # tried), and the ladder — one route raising ended the others. The row is the point: it is what
    # DEAD_STATUSES, the held queue and every later "what has this work been through" question read.
    try:
        return rung.fn(work, ctx), None
    except _netutil.HostCooling as e:       # D44: the request gate stopped the rung before a cooling host
        return _cooled_answer(e, gate), None
    except Exception as e:                  # noqa: BLE001 — the route boundary is the point
        return {"status": "api-error"}, e
    # END guard: a route that RAISES is a recorded api-error attempt, never a hunt-wide traceback


def _known_bad(conn, sha):
    """The rejected-hash lookup (item 1): -> the refused-bytes record the served sha matches, or None."""
    match = None
    # BEGIN guard: bytes already refused are never landed or quarantined again
    match = _ledger.rejected_match(conn, sha)
    # END guard: bytes already refused are never landed or quarantined again
    return match


def _challenge_of(route, served, terminal, verdict=None):
    """-> the challenge family of bytes a rung was served and refused, or '' (S4.5 decision D24, integrator-w3).
    THE one detector (`netutil.Client.challenge_cause`) — through the acceptance test's own verdict when it judged
    the bytes (`verdict.challenge`), else asked directly with the terminal response's status, URL and headers.
    Never for a Stage E route (`policy.STAGE_OF`): an archive replaying a challenge page it once captured did not
    refuse this client — the capture is the bad file."""
    if _policy.STAGE_OF.get(route) == "E":
        return ""
    if verdict is not None:
        return verdict.challenge
    from litkb.netutil import Client

    terminal = terminal or {}
    return Client.challenge_cause(terminal.get("status_code"), terminal.get("url"), served, terminal.get("headers"))


def _type_attempt(status, route, codes, served, headers, tried, rung_sub=None):
    """-> (sub_status, cause) for the row about to be written. A rung that typed its own answer wins; a
    `bad-file` that kept no byte is typed from its terminal response (S4.5 decision D15)."""
    sub, cause = None, ""
    # BEGIN guard: every attempt is typed
    if rung_sub and rung_sub in _policy.SUB_STATUSES.get(status, ()):
        sub = rung_sub
    else:
        sub, cause = _ledger.sub_status_for(status, route, codes, served, headers, tried)
    # END guard: every attempt is typed
    # BEGIN guard: a bad-file with no bytes kept is typed from its terminal response
    # (S4.5 decision D15: "A `bad-file` row is ALWAYS typed at write time. With no bytes kept, the route types
    # from the terminal response". The byte classifier answers None for an empty answer — no byte-level word
    # describes nothing — so without this rule such a row climbs the gated all-time `bad_file_untyped`: open
    # access when every location answered an empty body, the archive when no partner host served one, any rung
    # registered later. One rule for every rung, here, where every row is typed. fix round 3, auditor-C1a r2 F1.)
    if status == "bad-file" and sub is None and not served:
        sub, cause = _ledger.no_byte_bad_file_sub(headers)
    # END guard: a bad-file with no bytes kept is typed from its terminal response
    return sub, cause


def _land(conn, ws, token, work, data, *, route, source_url, store, index, agent, session, terminal, copy_kind):
    """The ladder's landing of the bytes a rung DOWNLOADED. -> (status, detail).

    THE ACCEPTANCE TEST comes first (`accept.offer_to_bind`: unwrap, repair, magic, floor, trailer, qpdf,
    the stub / volume / cited rules against the work's record), then the bind (`land_and_attach`) on the
    bytes it accepted; refused bytes are kept in _quarantine/ with the verdict in the sidecar. The plan's
    item 5b: "the bytes through the same acceptance test as every route". Until the merge the ladder landed
    through `land_and_attach` alone, whose own first step is only the header-and-trailer shape (seam
    integrator-w1, C1a x C1b). The served headers and terminal URL are what the stub rule reads."""
    judge = None                      # the unguarded default: the bind alone, as the ladder had it before
    # BEGIN guard: a rung's bytes bind only through the acceptance test
    judge = _accept.offer_to_bind
    # END guard: a rung's bytes bind only through the acceptance test
    if judge is None:
        return land_and_attach(conn, ws, token, work, data, route=route, source_url=source_url, store=store,
                               index=index, agent=agent, session=session, copy_kind=copy_kind)
    return judge(conn, ws, token, work, data, route=route, source_url=source_url, store=store, index=index,
                 agent=agent, session=session, headers=terminal.get("headers"),
                 terminal_url=terminal.get("url"), copy_kind=copy_kind)


#: the route-dict keys copied into an attempt's detail (the pre-0033 set, plus `reason`, `policy`, `version`)
DETAIL_KEYS = ("detail", "tried", "via", "md5", "record_doi", "title_best", "downloads_left", "rec_size", "quota",
               "reason", "policy", "version",
               # seam builder-C2b: Stage C's evidence (landing page, rules and their freshness, every candidate)
               "landing",
               # S4.5 decision D44: the host cool-down that stopped the rung (`_cooled_answer`)
               "cooldown",
               # S4.5 fix wave FX-B: a post-landing identifier call's file candidates it did not ask
               "harvest_only")


def _pass_stamp(ctx, detail):
    """S4.5 fix wave FX-B: `detail`, stamped `harvest_only` when the ladder's post-landing identifier pass wrote it
    (`RungContext.harvest_only`) — an answer, a skip or a budget-stop (auditor-FX-B N7: a budget-stop of the pass could
    not be told from the loop's own). A rung's own `harvest_only` (its unasked candidates) is kept. -> `detail`."""
    # BEGIN guard: every row of the post-landing identifier pass says so
    if ctx.harvest_only:
        detail.setdefault("harvest_only", {"not_asked": [], "why": _stage_b.HARVEST_ONLY_WHY})
    # END guard: every row of the post-landing identifier pass says so
    return detail


def _record_result(conn, ws, token, work, rung, r, exc, ctx, *, store, dedupe, agent, session, retry_of=None,
                   ladder=None):
    """Land (or quarantine, or measure) what one rung answered, and write its attempt row. `ladder` is the
    ladder's state when the rung was LAUNCHED ({elapsed_s, spent_before, budget}), recorded so a launch past
    the budget is visible in the ledger. -> the row's facts: {"id", "status", "sub_status", "codes",
    "detail", "quarantine", "exception", "retriable"}."""
    route, wid = rung.route, work["work_id"]
    ident = _identifier(rung, work)
    codes = [int(c) for c in (r.get("http_codes") or []) if str(c).lstrip("-").isdigit()]
    if exc is not None:
        # 200 characters of the message: the class name is what says WHAT went wrong, and a stack-shaped
        # repr in a jsonb column is the traceback the route boundary removed
        detail = {"exception": type(exc).__name__, "message": str(exc)[:200]}
    else:
        detail = {k: r.get(k) for k in DETAIL_KEYS if r.get(k) not in (None, "", [])}
    if "policy" not in detail and route in ctx.decisions:
        detail["policy"] = [ctx.decisions[route]]
    _pass_stamp(ctx, detail)        # S4.5 fix wave FX-B: a row of the post-landing pass says so, whatever it answered
    # S4.5 decision D44: every URL this rung call did not ask because its host was cooling down is on its row
    untried = (r.get("cooldown_gate") or {}).get("refused") or []
    # BEGIN guard: a URL the request gate did not ask is recorded on the row
    if untried:
        detail["cooldown_skipped"] = untried
    # END guard: a URL the request gate did not ask is recorded on the row
    if ladder:
        detail["ladder"] = ladder
    src = redact(r.get("source_url") or r.get("rejected_url") or
                 (f"annas md5:{r['md5']}" if route == "annas" and r.get("md5") else ""))
    served = r.get("pdf") or r.get("rejected")
    sha = hashlib.sha256(served).hexdigest() if served else None
    terminal = r.get("terminal") or {}
    status = r.get("status") or "api-error"
    # seam integrator-w2 (S4.5 decision D22): the stub-relevant response headers go on EVERY attempt that was served
    # bytes, written by the ladder itself and independent of the acceptance test — so `stubs_bound` can re-read a
    # landing the test did not judge (a header-only stub bound with the test switched off left no evidence at all)
    # BEGIN guard: every attempt that was served bytes records the stub-relevant headers itself
    if served:
        detail["served_headers"] = _accept.served_headers(terminal.get("headers"))
    # END guard: every attempt that was served bytes records the stub-relevant headers itself
    #: the acceptance test's own sub-status when it judged these bytes here (a refusal's word, stored as is)
    judged = None
    # seam builder-C2b: a page this rung was served is a lead for Stage C (litkb.acquire.landing) — read BEFORE the
    # rejected-hash lookup, so a page served again (a stable landing page quarantined in an earlier run) still is one
    # BEGIN guard: a page a rung was served is a lead for Stage C
    if r.get("rejected") and not _accept.quick_magic(r["rejected"]):
        ctx.leads.append({"route": route, "url": r.get("rejected_url") or r.get("source_url") or "",
                          "status": terminal.get("status_code"), "headers": terminal.get("headers") or {},
                          "body": r["rejected"]})
    # END guard: a page a rung was served is a lead for Stage C
    known = _known_bad(conn, sha) if sha else None
    # BEGIN guard: bytes the corpus holds are a hit, never known-bad
    # (auditor-C1a F3.) A payload refused once and bound later is never cleared (0030: a moved payload stays
    # refused — five such rows on live, each the ACTIVE file of its work), so the lookup matches it for ever. A
    # rung that DOWNLOADS those bytes has found the file the corpus holds: in acquire mode the dedupe answers
    # `duplicate-held` and stops the ladder; in MEASURE mode it is `measured`, a legitimate hit, and the shadow
    # tier stays refused (litkb-shadow-hosts: "only after every legitimate rung has missed"). Bytes a route
    # REFUSED stay named by the lookup whatever the corpus holds: they are never re-quarantined. Held FOR THIS
    # WORK's purposes (ledger.held_file): bytes refused for this very work stay known-bad although another work
    # holds them (fix round 3, auditor-C1a r2 F3).
    if known and status == "downloaded" and _ledger.held_file(conn, sha, wid):
        known = None
    # END guard: bytes the corpus holds are a hit, never known-bad
    if known:
        # the same bytes were refused before: named, never written again (not landed, not re-quarantined)
        detail["known_bad"] = known
        detail["sha256"] = sha
        if status == "downloaded":
            status = "known-bad"
        # S4.5 decision D24 (integrator-w3): a challenge page served AGAIN is still the host's refusal — the one
        # detector is asked directly here, because refused bytes met again are never re-judged by the acceptance
        # test (they are neither landed nor quarantined again). Stage E excepted, as below.
        # BEGIN guard: a live host's bot challenge served again is booked blocked, never a bad file
        elif status == "bad-file" and served:
            cause = _challenge_of(route, served, terminal)
            if cause:
                status, judged = "blocked", "challenge_or_bot_check"
                detail["challenge"] = cause
        # END guard: a live host's bot challenge served again is booked blocked, never a bad file
    elif status == "downloaded":
        if ctx.mode == "measure" or ctx.landed:
            # a hit that is not landed is still JUDGED: MEASURE mode records what the acceptance test would say
            v = _accept.accept(served, headers=terminal.get("headers"), url=src, terminal_url=terminal.get("url"),
                               doi=work.get("doi"), record_pages=_accept.record_pages_of(conn, wid))
            status, judged = ("measured", None) if v.verdict == "accept" else ("bad-file", v.sub_status)
            detail.update({"sha256": sha, "bytes": len(served), "source_url": src, "acceptance": v.summary(),
                           "not_landed": "measure mode" if ctx.mode == "measure" else "another rung landed first"})
            if v.reason:
                detail["note"] = v.reason
        else:
            status, landed = _land(conn, ws, token, work, served, route=route, source_url=src, store=store,
                                   index=dedupe, agent=agent, session=session, terminal=terminal,
                                   copy_kind=_policy.COPY_KIND_OF_VERSION.get(r.get("version")))
            detail.update(landed)
            judged = landed.get("sub_status")
    # BEGIN guard: bytes a route refused are quarantined, never discarded
    # `pdf` on a non-downloaded status is a real PDF that is not the record's (hash-mismatch); `rejected` is
    # what a download URL served instead of a file. Either way the bytes stay, under the route's own status
    # as their name - the status vocabulary is the database's (0013_admission.sql) and does not change here.
    elif r.get("pdf") or r.get("rejected"):
        refused = r.get("pdf") or r["rejected"]
        shape, why = pdf_shape(refused)
        status = r["status"]
        if status == "bad-file":
            # typed by THE acceptance test (the ledger's one byte classifier), and what it read is kept
            v = _ledger.bad_file_verdict(refused, headers=terminal.get("headers"), url=src,
                                         terminal_url=terminal.get("url"), status=terminal.get("status_code"))
            if v is not None:
                detail["acceptance"] = v.summary()
                judged = v.sub_status
                # S4.5 decision D24 (integrator-w3): bytes THE one challenge detector calls a bot challenge are a
                # refusal by the host, not a bad file — "an Akamai 'Access Denied' 403 (MDPI) is blocked /
                # challenge_or_bot_check, never bad-file/html_response". Not for a Stage E answer: an archive
                # replaying a challenge page it once captured did not refuse this client; the capture is the bad
                # file (policy.STAGE_OF). The acceptance test's own word stays in detail.acceptance.
                # BEGIN guard: a live host's bot challenge is booked blocked, never a bad file
                cause = _challenge_of(route, refused, terminal, verdict=v)
                if cause:
                    status, judged = "blocked", "challenge_or_bot_check"
                    detail["challenge"] = cause
                # END guard: a live host's bot challenge is booked blocked, never a bad file
        if ctx.mode == "measure":
            detail.update({"sha256": sha, "bytes": len(refused), "not_quarantined": "measure mode"})
        else:
            detail.update(quarantine_bytes(store, work, refused, label=status, status=status, shape=shape,
                                           reason=why or r.get("detail") or f"the {route} route refused it",
                                           route=route, source_url=src))
    # END guard: bytes a route refused are quarantined, never discarded
    else:
        status = r.get("status") or "api-error"
        # BEGIN guard: an attempt whose every request was a transport failure is api-error, never a bad file
        # (S4.5 decision D15: "An attempt where EVERY request was a transport failure (status 0) is NOT `bad-file`:
        # book it `api-error`, `retriable` true"; auditor-C1a F2, integrator-w1 Q1.) A rung that books `bad-file`
        # with no bytes handed back and every HTTP code 0 (the client's own transport failure) met the network,
        # not a file. Only status 0: a server that ANSWERED — 404, 403, even an empty 503 — gave a response the
        # typing rule reads (`_type_attempt`, D15), and its own codes decide `retriable`. For every rung.
        if status == "bad-file" and codes and all(c == 0 for c in codes):
            status = "api-error"
            detail["no_byte_served"] = f"booked bad-file by the rung; every request a transport failure: {codes}"
        # END guard: an attempt whose every request was a transport failure is api-error, never a bad file
    sub, cause = _type_attempt(status, route, codes, served, terminal.get("headers"), r.get("tried"),
                               judged or r.get("sub_status"))
    if cause:
        detail["sub_status_cause"] = cause
    forced = True if detail.get("no_byte_served") else None     # D15: "book it `api-error`, `retriable` true"
    # BEGIN guard: a blocked row is never retriable, whatever the rung says
    # (auditor-C1a r2 F5.) The dead-in-run check drops every prior row whose `retriable` is true (guard 15), so a
    # rung that answered `blocked` with `retriable: True` escaped `dead_in_run` and was asked again in the same
    # run. A challenge is a refusal before its code is read (guard 3; backoff.classify) — whoever says otherwise.
    if status == "blocked":
        forced = False
    # END guard: a blocked row is never retriable, whatever the rung says
    retriable = r.get("retriable") if forced is None else forced
    if retriable is None:
        retriable = _backoff.retriable(status, codes, exc)
    # (S4.5 decision D45.) A row whose rung left a URL UNTRIED because its host was cooling keeps the status the
    # answering host(s) gave — B's `blocked/not_found` stays that — but is never a permanent miss: asking again after
    # the cool-down can change it. Overrides the blocked-row rule above (the coordinator's ruling); never a success.
    # BEGIN guard: a row with a URL untried for a cooling host is retriable, whatever the answering hosts said
    if untried and status not in _backoff.SUCCESS_STATUSES:
        retriable = True
    # END guard: a row with a URL untried for a cooling host is retriable, whatever the answering hosts said
    # seam builder-C2a: the identifiers a rung read are written with their provenance through B1's one write path, on
    # the attempt that read them (S4.5 decision D2; litkb.acquire.stage_b.write_harvest — never raises); Stage A's
    # record rides on the ladder's first row for the work (litkb.acquire.stage_a.onto_first_row; auditor-C2a F1)
    harvested = None
    # BEGIN guard: a rung's harvested identifiers are written, with provenance, on the attempt that read them
    harvested = _stage_b.write_harvest(conn, ws, token, work, route, r, agent=agent, session=session)
    # END guard: a rung's harvested identifiers are written, with provenance, on the attempt that read them
    if harvested:
        detail["harvest"] = harvested
    if r.get("stage_b"):
        detail["stage_b"] = r["stage_b"]
    _stage_a.onto_first_row(work, detail)
    kind = r.get("kind") or ("pdf" if served and _accept.quick_magic(served) else None)
    # seam builder-C2c: a URL this answer asked and did not succeed on is a Stage E candidate
    # BEGIN guard: a dead URL a rung met in this run reaches Stage E
    ctx.recovery_urls.extend(_recovery.urls_of(route, r, status, sub_status=sub))
    # END guard: a dead URL a rung met in this run reaches Stage E
    aid = record_attempt(conn, ws, token, wid, route, ident, status, detail, codes, sub_status=sub,
                         served_sha256=sha, terminal=terminal, retriable=retriable, kind=kind, retry_of=retry_of)
    # BEGIN call site: a route's quarantine gets its database row
    q = quarantine_state(conn, ws, token, work, status, route, detail, aid)
    # END call site: a route's quarantine gets its database row
    return {"id": aid, "status": status, "sub_status": sub, "codes": codes, "detail": detail, "quarantine": q,
            "exception": type(exc).__name__ if exc is not None else "", "retriable": retriable}


def _cool_after(route, row, r, aimd, hosts, bo, clock):
    """S4.5 decisions D41, D44: after ONE recorded answer (an original or its retry), cool every HOST that answered
    it a 429 / 503 (the request gate's `observed`, each with its own Retry-After; a bot challenge never), and — when
    the answer itself is transient and its next wait is longer than a row sits out — the host that gave the terminal
    answer. The route's AIMD delay has already been moved by this answer. The cool-downs go in the RUN's host table
    `hosts` (S4.5 decision D45: every route asking a cooled host is gated, and the facts name the route whose answer
    started it). -> [the facts of each cool-down started].
    `clock` is the ladder's pacer clock (the one its waits are measured on)."""
    started = []
    now = datetime.datetime.now(datetime.timezone.utc)

    def cool(host, code, cause, ra):
        seconds, source = _backoff.cooldown_seconds(ra, aimd.delay_s, bo)
        started.append(hosts.cool(clock, seconds, {
            "trigger_route": route, "host": host, "trigger_attempt_id": str(row["id"]), "trigger_status": row["status"],
            "status_code": code, "cause": cause, "wait_s": seconds, "wait_source": source, "retry_after_s": ra,
            "cooled_at": now.isoformat(), "cool_until": (now + datetime.timedelta(seconds=seconds)).isoformat(),
            "ruling": "S4.5 decisions D41, D44, D45"}, host))

    observed = (r.get("cooldown_gate") or {}).get("observed") or []
    for o in observed:
        if o.get("host") and _backoff.is_rate_limit(o.get("status"), o.get("challenge")):
            cool(o["host"], o["status"], "rate-limit", o.get("retry_after_s"))
    term = r.get("terminal") or {}
    ra = _backoff.retry_after_s(term.get("headers"))
    if _backoff.long_wait(row["status"], row["codes"], max(aimd.delay_s, ra or 0.0), bo):
        # the gate's own record of the terminal answer (the URL the rung asked, the code it got): the host that GAVE it
        # — the end of a followed redirect chain, never the redirector (auditor-fix7 F1) — and whether it was a bot
        # challenge (auditor-fix7 F2)
        match = next((o for o in reversed(observed) if not o.get("hop") and o.get("asked") == _backoff._bare(
            term.get("url")) and o.get("status") == term.get("status_code")), None)
        host = match["host"] if match else (_backoff.host_of(term.get("url")) or
                                            (observed[-1]["host"] if observed else ""))
        # BEGIN guard: a challenge never cools a host, by the long-wait cause either
        # (guard 3 and D41: a bot challenge at any code is a refusal of this client, never a rate; auditor-fix7 F2 — a
        # rung that books its challenge `api-error` (Wayback, IA, a Stage B service) made it a transient long wait)
        if match is not None and match.get("challenge"):
            host = ""
        # END guard: a challenge never cools a host, by the long-wait cause either
        if host:
            cool(host, row["codes"][-1], "long-wait", ra)
    return started


def _move_backoff(conn, ws, token, work, route, row, bo):
    """The chain's FINAL row moves the persisted refusal ladder (litkb.acquire.backoff.BackoffPolicy.step)."""
    at = conn.execute("SELECT at FROM litkb.acquisition_attempts WHERE id = %s", (row["id"],)).fetchone()[0]
    before = _backoff.load(conn, route, work["work_id"])
    after = bo.step(before, row["status"], row["codes"], at)
    if (before or {}).get("refusals", 0) or after.get("refusals"):
        _backoff.save(conn, ws, token, row["id"], after)


def acquire(conn, ws, token, work, *, store=None, routes=ROUTES, agent, session, budget=None, retry_dead=False,
            clients=None, pacer=None, annas_session=None, annas_pacer=None, printer=print, from_file=None,
            mode="acquire", ladder_budget=None, backoff=None, rungs=None, pacing=None):
    """-> {"outcome": ..., "attempts": [(route, status), ...], "route_detail": [...], "quarantine_rows": [...]}

    `mode` "measure" asks every rung and lands nothing (S4.5 decision D9); `ladder_budget` is the whole
    ladder's `policy.LadderBudget` (default: the declared one, attempts and concurrency derived from the
    registry); `backoff` the `backoff.BackoffPolicy` this run applies; `rungs` a registry other than RUNGS;
    `pacing` the run's per-route AIMD state (default: this process's PACING)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    store = store or Store()
    budget = budget or Budget()
    clients = clients or {}
    pacer = pacer or Pacer(interval=3.0)
    attempts = []
    #: `attempts` is the (route, status) pair callers already read and its shape does not change.
    #: `route_detail` is the same list with what the CALLER needs to classify a ladder that landed
    #: nothing: the HTTP codes (403 is a host refusing, a challenge is not) and the exception class
    #: when the route raised. `litkb.hunt` reads it for the precedence rule that decides between
    #: `blocked`, `api-error` and `held` (docs/SCHEMAS.md, the hunt's terminal states).
    route_detail = []
    #: One entry per quarantine this call made: `quarantine.try_record`'s {"ok", "id"|"error", "rel_path"}.
    #: A caller that finds `ok: False` reports it (hunt: the `quarantine-state-failed` refusal).
    qrows = []
    if work["held_files"] and from_file is None and mode == "acquire":
        return {"outcome": "already-held", "attempts": attempts, "route_detail": route_detail}
    index = store.disk_index()
    dedupe = index                  # (the whole index, if the line below is ever removed: see index_of_held)
    # BEGIN guard: the dedupe asks what the corpus HOLDS, and staging and quarantine hold nothing
    dedupe = index_of_held(store, index)
    # END guard: the dedupe asks what the corpus HOLDS, and staging and quarantine hold nothing
    wid = work["work_id"]

    if from_file is not None:
        data = Path(from_file).read_bytes()
        # S4.5 decision D17 (seam integrator-w2): the operator's file RUNS the acceptance test (plan 5b, "the same
        # acceptance test as every route") and its verdict is recorded on the PROPOSAL the bind writes
        # (`file_versions.binding.acceptance`, read by `front.pending_file_proposals`) and on the attempt row. Only a
        # HARD byte failure refuses the file (`accept.hard_byte_failure`: not a PDF, corrupt, an archive holding
        # none); a stub, volume or cited-document verdict is the second-session approver's to weigh, not the test's
        # to enforce against the operator's judgement. Bytes the test accepted after unwrapping or a header repair
        # land as the PDF it found.
        verdict = None
        # BEGIN guard: a hand-fetched file runs the acceptance test and its verdict rides on the proposal
        verdict = _accept.accept(data, url=f"manual file {Path(from_file).name}", doi=work.get("doi"),
                                 record_pages=_accept.record_pages_of(conn, wid))
        # END guard: a hand-fetched file runs the acceptance test and its verdict rides on the proposal
        verdict_summary = verdict.summary() if verdict is not None else None
        payload = verdict.pdf if verdict is not None and verdict.verdict == "accept" and verdict.pdf else data
        shape, why = pdf_shape(payload)
        hard = verdict is not None and _accept.hard_byte_failure(verdict)
        if hard:
            shape, why = _accept.quarantine_label(verdict.sub_status), verdict.reason
        status = None
        # BEGIN guard: a hand-fetched file that is not a whole PDF is quarantined or refused, never deleted
        if shape != "pdf":
            status, detail = "bad-file", from_file_not_a_pdf(store, work, from_file, data, shape, why)
        # END guard: a hand-fetched file that is not a whole PDF is quarantined or refused, never deleted
        if status is None:
            # BEGIN guard: acquire from a file already in a topic folder binds it in place
            # (landing a copy would only dedupe against the file itself on disk: the work could never get it)
            if _in_topic_folder(store, from_file):
                status, detail = attach_in_place(conn, ws, token, work, from_file, store=store, agent=agent,
                                                 session=session, acceptance=verdict_summary)
            # END guard: acquire from a file already in a topic folder binds it in place
            if status is None:
                status, detail = land_and_attach(conn, ws, token, work, payload, route="browser",
                                                 source_url=f"manual file {Path(from_file).name}", store=store,
                                                 index=dedupe, agent=agent, session=session,
                                                 acceptance=verdict_summary)
        if verdict_summary is not None:
            detail["acceptance"] = verdict_summary
        sub, _cause = _type_attempt(status, "browser", [], data, None, None, verdict.sub_status if hard else None)
        aid = record_attempt(conn, ws, token, wid, "browser", work.get("doi") or work.get("arxiv"), status,
                             detail, sub_status=sub, served_sha256=hashlib.sha256(data).hexdigest(),
                             kind="pdf" if shape == "pdf" else None)
        # BEGIN call site: a hand-fetched file's quarantine gets its database row
        q = quarantine_state(conn, ws, token, work, status, "browser", detail, aid)
        # END call site: a hand-fetched file's quarantine gets its database row
        if q is not None:
            qrows.append(q)
        attempts.append(("browser", status))
        route_detail.append({"route": "browser", "status": status, "codes": [], "exception": ""})
        return {"outcome": status, "attempts": attempts, "route_detail": route_detail, "quarantine_rows": qrows}

    chosen = ladder_rungs(routes, rungs)
    lb = (ladder_budget or _policy.LadderBudget()).resolved(chosen)
    bo = backoff or _backoff.BackoffPolicy()
    pacing = PACING if pacing is None else pacing
    #: the clock the ladder's waits are measured on (the pacer's; S4.5 decisions D41/D44's cool-downs read it)
    clock = getattr(pacer, "clock", None) or time.monotonic

    def hosts_for(route):
        """The host table this route's calls read and write: the RUN's one table (S4.5 decision D45)."""
        key = ("hosts", route)   # the unguarded default: a table per route (D44's key)
        # BEGIN guard: one host table for the whole run, shared by every route
        key = _backoff.HOSTS_KEY
        # END guard: one host table for the whole run, shared by every route
        return pacing.setdefault(key, _backoff.HostCooldowns())

    def gate_for(route, exempt=()):
        """ONE rung call's request gate over the run's per-host cool-downs (S4.5 decisions D44, D45)."""
        return _backoff.Gate(route, hosts_for(route), clock, exempt)
    # seam builder-C2a: Stage A, once, before any rung (litkb.acquire.stage_a.prepare): the A2 class the pre-fetch
    # policy consults, the A1-canonical identifiers and edition-edge targets the rungs ask with, the Wave-0 rows
    # BEGIN call site: Stage A prepares the work before its first rung
    _stage_a.prepare(conn, ws, token, work, None, agent=agent, session=session)
    # END call site: Stage A prepares the work before its first rung
    ctx = RungContext(clients=_gated(clients), pacer=pacer, budget=budget, index=index, printer=printer, mode=mode,
                      annas_session=annas_session, annas_pacer=annas_pacer, work_class=work.get("class", ""))
    prior = prior_attempts(conn, wid)
    # seam builder-C2c: the dead URLs earlier attempts recorded are Stage E's input (a rung never reads the database)
    # BEGIN guard: a dead URL an earlier attempt recorded reaches Stage E
    if any(g.route in _recovery.ROUTES for g in chosen):
        ctx.recovery_urls.extend(_recovery.ledger_urls(conn, wid))
    # END guard: a dead URL an earlier attempt recorded reaches Stage E
    started, spent = lb.clock(), 0
    outcome = None

    def note(route, row):
        attempts.append((route, row["status"]))
        route_detail.append({"route": route, "status": row["status"], "sub_status": row.get("sub_status"),
                             "codes": [int(c) for c in row.get("codes") or []], "exception": row.get("exception", "")})
        if row.get("quarantine") is not None:
            qrows.append(row["quarantine"])

    def skip(route, sub, detail, ident=None):
        detail = _stage_a.onto_first_row(work, dict(detail or {}))      # seam builder-C2a (auditor-C2a F1)
        _pass_stamp(ctx, detail)                                         # S4.5 fix wave FX-B: the post-landing pass
        # BEGIN guard: a skip is an attempt with a reason, never silence
        aid = record_attempt(conn, ws, token, wid, route, ident, "skipped", detail, sub_status=sub)
        note(route, {"id": aid, "status": "skipped", "sub_status": sub, "codes": []})
        # END guard: a skip is an attempt with a reason, never silence
        printer(f"  {route}: skipped ({sub})")

    def stop_for_budget(why, not_asked):
        aid = record_attempt(conn, ws, token, wid, "ladder", None, "budget-stop", _stage_a.onto_first_row(
                             work, _pass_stamp(ctx, {"budget": lb.spec(), "spent": spent,     # FX-B: the pass's stamp
                                                     "elapsed_s": round(lb.clock() - started, 3),
                                                     "not_asked": not_asked})), sub_status=why)  # seam builder-C2a (F1)
        note("ladder", {"id": aid, "status": "budget-stop", "sub_status": why, "codes": []})
        printer(f"  ladder: budget-stop ({why})")

    def launch(offset=0):
        """The ladder's state as a rung is launched (recorded on its attempt row)."""
        return {"elapsed_s": round(lb.clock() - started, 3), "spent_before": spent + offset, "budget": lb.spec()}

    def settle(rung, r, exc, at_launch, unsettled=()):
        """Record one answer (and its one scheduled retry), move the back-off, update the ladder's state.
        `unsettled`: the (answer, exception) pairs of the siblings launched beside this rung in a concurrent
        stage and settled after it — their requests are already spent."""
        nonlocal spent, outcome
        if exc is None and r.get("status") == "skipped":
            # a rung that refused itself on policy (every host line it would ask refused): a skip, not a spend
            # (seam builder-C2c: and the rung's own note on why, e.g. a Stage E rung that was named no dead URL)
            skip(rung.route, r.get("sub_status") or "policy_refused",
                 {"policy": r.get("policy"), **({"detail": r["detail"]} if r.get("detail") else {}),
                  # S4.5 decision D44: a rung the request gate stopped before it asked anything names the host
                  **({"cooldown": r["cooldown"]} if r.get("cooldown") else {}),
                  **({"cooldown_skipped": r["cooldown_gate"]["refused"]}
                     if (r.get("cooldown_gate") or {}).get("refused") else {})},
                 _identifier(rung, work))
            return
        row = _record_result(conn, ws, token, work, rung, r, exc, ctx, store=store, dedupe=dedupe, agent=agent,
                             session=session, ladder=at_launch)
        spent += 0 if row["status"] in _backoff.NON_SPEND_STATUSES else 1
        note(rung.route, row)
        printer(f"  {rung.route}: {row['status']}")
        aimd = pacing.setdefault(rung.route, _backoff.Aimd(policy=bo))
        aimd.on_answer(row["status"], row["codes"])
        # (S4.5 decisions D41, D44.) A host that answered 429 / 503 — or gave a transient answer whose next wait is
        # longer than a row sits out — is not asked again by this route in the run until its cool_until (the request
        # gate, `_call_rung`); a 403 never cools a host (guard 29), nor does a bot challenge.
        cooled_now = []                 # the unguarded default: no host cools
        # BEGIN guard: a rate-limit answer cools its host for the rest of the run
        cooled_now = _cool_after(rung.route, row, r, aimd, hosts_for(rung.route), bo, clock)
        # END guard: a rate-limit answer cools its host for the rest of the run
        pending = 0                     # the unguarded default: only the rows already settled count as spent
        # BEGIN guard: a concurrent stage's retry counts the siblings launched beside it
        # (auditor-C1a r2 F2.) A concurrent stage's rungs are all asked before any is settled, so when this rung's
        # retry is weighed its siblings have ALREADY spent their requests but are not yet in `spent`: counted
        # alone, a retry went out past an explicit attempts budget and recorded a `spent_before` under it, where
        # budget_exceeded_silently could not see it. A sibling that spent nothing (a self-refusal on policy, a
        # quota stop) is not counted; one that raised is (an api-error attempt).
        pending = sum(1 for (r_, e_) in unsettled
                      if e_ is not None or (r_ or {}).get("status") not in _backoff.NON_SPEND_STATUSES)
        # END guard: a concurrent stage's retry counts the siblings launched beside it
        # BEGIN guard: a transient answer gets one scheduled retry, named as one
        if (rung.retry_transient and exc is None and _backoff.classify(row["status"], row["codes"]) == "transient"
                and lb.exhausted(started, spent + pending) is None):
            wait = max(aimd.delay_s, _backoff.retry_after_s((r.get("terminal") or {}).get("headers")) or 0.0)
            sit_out = True                  # the unguarded default: the row waits out whatever the wait is
            # BEGIN guard: an in-row retry never sits out a long wait
            # (S4.5 decision D41. The live ladder-1 run, 2026-09-24: archive.org's 429s doubled the AIMD delay to its
            # 300 s ceiling and each row waited it out before a retry the budget then refused — ~10 min a row. A
            # wait over `in_row_wait_max_s` is not scheduled: the original stays `retriable` and unretried, and the
            # host is cooling instead (`_cool_after`, above), so no later work asks it until the wait has passed.)
            sit_out = min(wait, bo.aimd_ceiling_s) <= bo.in_row_wait_max_s
            # END guard: an in-row retry never sits out a long wait
            if sit_out:
                waited = min(wait, bo.aimd_ceiling_s)
                pacer.sleep(waited)
                retry_now = True            # the unguarded default: the retry follows its wait unconditionally
                # BEGIN guard: the ladder budget is checked again after a scheduled retry's wait
                # (the wait is Retry-After or the AIMD delay, up to the in-row threshold: a retry launched after the
                # wait crossed `seconds` is a launch past the budget — the silent overrun `budget_exceeded_silently`
                # counts. Not asked: the original row stays `retriable` and unretried, and the next stage or rung
                # meets the spent budget and writes the `budget-stop` row. Fix round 2.)
                retry_now = lb.exhausted(started, spent + pending) is None
                # END guard: the ladder budget is checked again after a scheduled retry's wait
                if retry_now:
                    again = launch(pending)
                    exempt = ()
                    # BEGIN guard: a scheduled retry is never refused the host whose answer it waited for
                    # (the retry comes after `waited`, which is at least every cool-down this answer started that is
                    # no longer than it — Retry-After, else the same AIMD delay: its host is asked again, as scheduled)
                    exempt = {f["host"] for f in cooled_now if f.get("wait_s", 0) <= waited}
                    # END guard: a scheduled retry is never refused the host whose answer it waited for
                    r2, exc2 = _call_rung(rung, work, ctx, gate_for(rung.route, exempt))
                    row = _record_result(conn, ws, token, work, rung, r2, exc2, ctx, store=store, dedupe=dedupe,
                                         agent=agent, session=session, retry_of=row["id"], ladder=again)
                    spent += 1
                    note(rung.route, row)
                    printer(f"  {rung.route}: {row['status']} (scheduled retry)")
                    aimd.on_answer(row["status"], row["codes"])
                    # BEGIN guard: a retry's rate-limit answer cools the route too
                    _cool_after(rung.route, row, r2, aimd, hosts_for(rung.route), bo, clock)
                    # END guard: a retry's rate-limit answer cools the route too
        # END guard: a transient answer gets one scheduled retry, named as one
        _move_backoff(conn, ws, token, work, rung.route, row, bo)
        if row["status"] in ("ok", "measured") and _policy.decide(rung.route).tier == _policy.LEGITIMATE:
            ctx.legit_hit = True
        if row["status"] == "ok" and outcome is None:
            ctx.landed, outcome = True, ("ok", row["detail"])
        elif row["status"] == "duplicate-held" and outcome is None and ctx.mode == "acquire":
            outcome = ("duplicate-held", row["detail"])

    def refused(g):
        """True when a skip reason stops rung `g` now (`_skip_reason`: no identifier, a dead route, `blocked` earlier
        in this run, the back-off window, the pre-fetch policy) — its `skipped` row is written; else False."""
        s = None                # the unguarded default: every rung is asked, whatever stands against asking it
        # BEGIN guard: a rung a skip reason stops is recorded and never asked
        s = _skip_reason(conn, g, work, prior, ws, retry_dead, ctx, bo)
        # END guard: a rung a skip reason stops is recorded and never asked
        if s:
            skip(g.route, s[0], s[1], _identifier(g, work))
        return bool(s)

    def run_stages(rungs, stop_at_outcome):
        """THE STAGE LOOP: ONE code path for the ladder and for its post-landing identifier pass (S4.5 fix wave FX-B;
        auditor-FX-B F2 — the pass was first a ~50-line copy of this loop, and no test reached its skip, budget or
        stop branches, so a copy could drift from the loop unseen). `rungs` in stage and registry order. Per stage:
        the budget, then the concurrent rungs asked together, then the sequential ones one by one — each under its
        skip reasons (`refused`), the budget, pacing and the request gate, and settled (`settle`: one scheduled
        retry, the back-off, the landing). `stop_at_outcome`: the ladder stops at its first landing (or its
        `duplicate-held` stop); the post-landing pass runs with that outcome already set and does not stop on it."""
        def stopped():
            return stop_at_outcome and outcome is not None

        for stage in _policy.STAGES:
            stage_rungs = [g for g in rungs if g.stage == stage]
            if not stage_rungs or stopped():
                continue
            # the budget, between stages (its guard is LadderBudget.exhausted's own block, policy.py)
            why = lb.exhausted(started, spent)
            if why:
                here = _policy.STAGES.index(stage)
                stop_for_budget(why, [g.route for g in rungs if _policy.STAGES.index(g.stage) >= here])
                return
            together = [g for g in stage_rungs if g.concurrent]
            alone = [g for g in stage_rungs if not g.concurrent]
            askable = [g for g in together if not refused(g)]
            if askable:
                room = max(0, (lb.attempts or len(askable)) - spent)
                asked, left = askable[:room], askable[room:]
                for g in asked:
                    _pace(pacing, g.route, pacer, bo)
                launches = [launch(i) for i in range(len(asked))]
                if len(asked) > 1:
                    with ThreadPoolExecutor(max_workers=max(1, min(lb.concurrency or 1, len(asked)))) as ex:
                        gates = {g.route: gate_for(g.route) for g in asked}
                        answers = list(ex.map(lambda g: _call_rung(g, work, ctx, gates[g.route]), asked))
                else:
                    answers = [_call_rung(g, work, ctx, gate_for(g.route)) for g in asked]
                for i, (g, (r, exc), at_launch) in enumerate(zip(asked, answers, launches)):
                    settle(g, r, exc, at_launch, answers[i + 1:])
                if left and not stopped():
                    stop_for_budget("budget_attempts", [g.route for g in left])
                    return
            for g in alone:
                if stopped():
                    return
                why = lb.exhausted(started, spent)
                if why:
                    stop_for_budget(why, [x.route for x in alone[alone.index(g):]])
                    return
                if refused(g):
                    continue
                _pace(pacing, g.route, pacer, bo)
                at_launch = launch()
                r, exc = _call_rung(g, work, ctx, gate_for(g.route))
                settle(g, r, exc, at_launch)

    run_stages(chosen, stop_at_outcome=True)

    # S4.5 fix wave FX-B (referee-stage-b N2): THE POST-LANDING IDENTIFIER PASS. The loop above stops at the first
    # landing (and at a `duplicate-held` stop): right for every rung that fetches a file — "PDF-fetching rungs still stop
    # at the first landing" — and wrong for the identifier waves, which the plan's closure rule pursues until a pass
    # adds nothing (LINKAGE §2.3). MEASURED on the ladder-1 run: all 17 crosswalk rows still without their arXiv sibling
    # had landed at Wave 1 and never asked Semantic Scholar. So every `Rung.harvests` rung the loop had not reached is
    # asked now, through the SAME stage loop (`run_stages`: the concurrent ones together, then the sequential ones,
    # under the same budget, skip reasons, pacing and scheduled retry), with `ctx.harvest_only` set: its identifier
    # call is made and its harvest written; its file candidates are named on the row and never asked
    # (litkb.acquire.stage_b.fetch_candidates); every row it writes says so (`_pass_stamp`). A rung the loop reached —
    # asked or skipped — is never asked twice. The `duplicate-held` stop starts the pass too: the bytes another work
    # holds are exactly the case whose identifiers the adjudication needs (builder-FX-B's choice, disclosed; N3).
    post = []                   # the unguarded default: the first landing stops the identifier waves too
    # BEGIN guard: identifier harvesting completes its waves after a landing
    if outcome is not None and mode == "acquire":
        reached = {route for route, _status in attempts}
        post = [g for g in chosen if g.harvests and g.route not in reached]
    # END guard: identifier harvesting completes its waves after a landing
    if post:
        ctx.harvest_only = True
        run_stages(post, stop_at_outcome=False)
        ctx.harvest_only = False

    if outcome is not None:
        kind, detail = outcome
        return {"outcome": kind, "attempts": attempts, "detail": detail, "route_detail": route_detail,
                "quarantine_rows": qrows, "stage_a": work.get("stage_a")}
    if mode == "measure":
        return {"outcome": "measured", "attempts": attempts, "route_detail": route_detail, "quarantine_rows": qrows,
                "stage_a": work.get("stage_a")}
    if not any(p[0] == "browser" and p[1] == "manual-step" for p in prior) or retry_dead:
        record_attempt(conn, ws, token, wid, "browser", work.get("doi"), "manual-step", _stage_a.onto_first_row(
                       work, {"instruction": "no automated route landed a file; fetch it in one browser session, "
                                             f"then py -3.12 -m litkb acquire --key {work['key']} --from-file <path>"}))
        attempts.append(("browser", "manual-step"))
    # seam builder-C2a: acquire()'s answer carries Stage A's record (stage_a.prepare's summary; auditor-C2a F1)
    return {"outcome": "not-acquired", "attempts": attempts, "route_detail": route_detail,
            "quarantine_rows": qrows, "stage_a": work.get("stage_a")}


def measure(conn, ws, token, work, *, store, agent, session, **kw):
    """THE MEASURE HOOK the ladder-1 run driver calls for a work that already holds a file
    (`qc/instruments/litkb_ladder_run.py` MEASURE_HOOK and MEASURE_CONTRACT; S4.5 decision D9): `acquire` in
    MEASURE mode — every rung asked (a route's earlier terminal miss does not skip it; `blocked` in the run
    and the back-off window still do), every answer recorded as an attempt row in `ws` and judged by the
    acceptance test, nothing landed, bound or quarantined, whatever the work already holds.
    -> acquire()'s dict, outcome `measured`. Seam integrator-w1 (A x C1a).

    Its default `routes` is the WHOLE ladder (`ladder_routes`, seam integrator-w2): the run driver passes none,
    and today's three routes would leave every Stage B, C and E rung unmeasured. The shadow tier among them is
    refused in MEASURE mode by `policy.measure_decision` (S4.5 decision D18)."""
    kw.setdefault("routes", ladder_routes())
    return acquire(conn, ws, token, work, store=store, agent=agent, session=session, mode="measure", **kw)


# seam builder-C2a: the Stage A and Stage B rungs register themselves when litkb.acquire.stage_b is imported
# (its RUNG_TABLE, in the wave order); importing it HERE makes them visible wherever the ladder is (S4.5 decision
# D19: a rung registered by import but never imported is invisible to `hunt` — fail closed). `_stage_b` is also
# the harvest's writer, `_record_result` above. A route still runs only when the caller's `routes` names it.
from litkb.acquire import stage_b as _stage_b  # noqa: E402


def _pace(pacing, route, pacer, bo=None):
    """Wait out the route's in-run AIMD delay before asking it (0 until the route answers transiently) — never
    longer than a row sits out (S4.5 decision D41): a longer delay is carried by its host's cool-down instead,
    which refused that host to every work until the delay had passed (`_cool_after`, the request gate)."""
    aimd = pacing.get(route)
    if aimd is not None and aimd.delay_s > 0:
        wait = aimd.delay_s             # the unguarded default: the whole AIMD delay, up to its 300 s ceiling
        # BEGIN guard: a pacing wait is never sat out past the in-row threshold
        # (the live ladder-1 run, 2026-09-24: after archive.org's 429s every later wayback ask first slept the AIMD
        # delay — 16, 64, 63 ... 224, 300 s — whether or not the host still refused; `detail.ladder.elapsed_s`)
        wait = min(wait, (bo or aimd.policy).in_row_wait_max_s)
        # END guard: a pacing wait is never sat out past the in-row threshold
        pacer.sleep(wait)


# seam builder-C2c: Stage E's rung modules register themselves at import (E1 Wayback, E3 Internet Archive, E5 Common
# Crawl, in that order); importing them HERE makes them visible wherever the ladder is (S4.5 decision D19). A route
# still runs only when the caller's `routes` names it.
from litkb.acquire import wayback as _wayback  # noqa: E402,F401
from litkb.acquire import ia as _ia  # noqa: E402,F401
from litkb.acquire import commoncrawl as _commoncrawl  # noqa: E402,F401


def file_from_path_facts(path):
    return file_facts(path)


# seam builder-C2b: the rung modules register themselves at import; importing them HERE is what makes every rung
# visible wherever the ladder is (S4.5 decision D19: a rung that registers by import but is never imported is
# invisible to `hunt`). A route still runs only when the caller's `routes` names it.
from litkb.acquire import landing as _landing  # noqa: E402,F401

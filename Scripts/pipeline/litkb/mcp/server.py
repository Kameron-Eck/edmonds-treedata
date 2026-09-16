"""The litkb MCP server — the agents' path into the literature knowledge base (design §9, §9.1).

    py -3.12 -m litkb.mcp.server            # stdio, one MCP session per process

Nine tools. Everything an agent may do to literature goes through them; everything an agent may
NOT do is absent, not merely discouraged:

    read    litkb_search  litkb_work  litkb_candidates  litkb_ws_status
    write   litkb_ws_open  litkb_admit  litkb_acquire  litkb_record_use
    offer   litkb_propose_promotion        (prepare ONLY; commit is not a tool)

Four rules this module keeps, each because something else cannot:

1. **The workstream token is never a tool parameter.** A parameter is written into the model's
   transcript, and a transcript is a sink. The token is read from `<worktree>/.litkb-workstream`
   (`litkb.workstream.load`), where `worktree` is LITKB_WORKTREE or the process's cwd, and is then
   passed to the database as a BOUND QUERY PARAMETER by the functions in `litkb.admit`,
   `litkb.acquire` and below — never formatted into SQL (design §5; third P1 referee F-8). A write
   tool called from a directory with no token file is REFUSED with `no-workstream`, and names the
   tool that opens one. `_session()` also registers the token with `netutil.add_secret()`, so if it
   ever reached a string this server returns, `_out()` would replace it with `<KEY>`.

2. **One output boundary.** Every tool returns `_out(...)`, whose single `redact()` call is the one
   thing between a route's own words (an archive URL carrying `key=`, a driver error echoing a
   conninfo) and the model's context. It is one call site so that the harness's per-call-site rule
   (`qc/instruments/litkb_p2_mutations.py`, rows X1/X2) can cover it, and so that a reader can check
   it by reading one function. This module has no `print` and writes to no stream: on stdio, stdout
   IS the protocol.

3. **The server holds no promoter and no ingest credential** (design §4.7, §9). `litkb_propose_promotion`
   runs `py -3.12 -m litkb promote prepare` as a SUBPROCESS, so the promoter's passfile is opened by
   a process that exits; this server's own connections are only `litkb_reader` and `litkb_writer`.
   `promote commit` is not exposed at all — it is Kam's step after his merge — and neither is
   `approve`, which §15.13 gives to a SECOND session (a server tool would make it the same one).

4. **Read tools read; write tools write.** `_conn("reader")` for search/work/candidates/status,
   `_conn("writer")` for the rest. The writer holds no direct INSERT on any workstream-owned table
   (design §4.7), so no tool here can write round the token even if this file were wrong.

Environment: LITKB_DB (default `litkb`), LITKB_WORKTREE, LITKB_AGENT / LITKB_SESSION (the labels
every write records; a write tool refuses without both), LITKB_READER_ROLE / LITKB_WRITER_ROLE (the
gate points them at `litkb_test` against a throwaway database), LITKB_REGISTRY_CACHE (a JSON file of
recorded registry responses — an admission that must not reach the network reads it and nothing
else), LITKB_VECTOR_SEARCH (the vector leg, off until P7 lands the embeddings).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = "0.1.0"
SERVER_NAME = "litkb"
SCRIPTS = Path(__file__).resolve().parents[3]

#: the vector leg is WIRED, not live: P7 builds the embeddings and the referee's paraphrased query
#: set that scores them (design §8, §14 P7). Until then `litkb_search` is lexical, and says so in
#: every result rather than letting a caller assume semantic recall it is not getting.
VECTOR_ENABLED = os.environ.get("LITKB_VECTOR_SEARCH") == "1"


# ── the output boundary ───────────────────────────────────────────────────────────────────

def _out(obj):
    """THE one way a tool returns. JSON, then redact.

    Mutation row X1 strips the redact() here; `test_planted_secret_is_redacted_in_a_tool_result`
    is what answers it. Nothing else in this package writes to a stream."""
    from litkb.netutil import redact

    return redact(json.dumps(obj, indent=1, default=str, ensure_ascii=False))


def _refuse(code, message, **extra):
    """A refusal is a RESULT, not an exception: the model must be able to read why and what to do.
    `code` is stable and machine-checkable; the gate asserts on it, not on the prose."""
    return _out({"ok": False, "refused": code, "message": message} | extra)


def _ok(**fields):
    return _out({"ok": True} | fields)


# ── connections, worktree, labels ─────────────────────────────────────────────────────────

def _db():
    from litkb.db import connect as c

    return os.environ.get("LITKB_DB") or c.DB_MAIN


def _role(kind):
    return os.environ.get(f"LITKB_{kind.upper()}_ROLE") or f"litkb_{kind}"


def _conn(kind):
    from litkb.db import connect as c

    return c.connect(_db(), _role(kind), autocommit=True)


def _worktree():
    return Path(os.environ.get("LITKB_WORKTREE") or os.getcwd()).resolve()


class Refusal(Exception):
    """Raised by _session()/_labels() and turned into a refusal result by the tool wrapper."""

    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


def _session():
    """(workstream_id, token) for the worktree this server runs in, with the token ARMED for
    redaction. No tool takes the token; there is no code path here that accepts one from a caller."""
    from litkb import workstream
    from litkb.netutil import add_secret

    try:
        ws_id, token = workstream.load(_worktree())
    except FileNotFoundError:
        raise Refusal("no-workstream",
                      f"no {workstream.TOKEN_FILE} in {_worktree()}: every write names an open "
                      "workstream and presents its token. Open one with litkb_ws_open first.",
                      worktree=str(_worktree())) from None
    except (ValueError, KeyError):
        raise Refusal("bad-workstream-file",
                      f"{_worktree() / workstream.TOKEN_FILE} is not readable as "
                      "{workstream_id, token}") from None
    # Mutation row X2 strips this call. It ARMS redact() for this process: without it every later
    # _out() is a redactor with nothing registered, and a token echoed back by a driver error would
    # reach the model verbatim.
    add_secret(token)
    return ws_id, token


def _labels(agent=None, session=None):
    from litkb.textnorm import norm_label

    a = norm_label(agent or os.environ.get("LITKB_AGENT") or "")
    s = norm_label(session or os.environ.get("LITKB_SESSION") or "")
    if not a or not s:
        raise Refusal("no-labels",
                      "every write records which agent and which session made it: set LITKB_AGENT "
                      "and LITKB_SESSION in the server's environment, or pass agent= and session=.")
    return a, s


def _registry_client():
    """The admission's registry client. With LITKB_REGISTRY_CACHE set, a recorded-response client
    that never opens a socket — which is how the P8 gate admits a REAL DOI offline. Without it, the
    ordinary paced HTTP client."""
    from litkb.netutil import Client

    path = os.environ.get("LITKB_REGISTRY_CACHE")
    if not path:
        return None
    records = json.loads(Path(path).read_text(encoding="utf-8"))

    class CachedRegistry(Client):
        """Recorded Crossref `/works/<doi>` responses; every other URL is a 404. It subclasses
        Client so it is the same shape the resolver expects, and overrides get() so nothing it is
        handed can leave the machine."""

        base = ""

        def __init__(self):
            self.records = {k.lower(): v for k, v in records.items()}
            self.calls = []

        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            import urllib.parse

            self.calls.append(url)
            if "api.crossref.org/works/" in url:
                doi = urllib.parse.unquote(url.split("/works/", 1)[1]).lower()
                rec = self.records.get(doi)
                if rec is not None:
                    return 200, {}, json.dumps({"message": rec}).encode()
            return 404, {}, b""

    return CachedRegistry()


# ── read tools ────────────────────────────────────────────────────────────────────────────

_SEARCH_BLOCKS = """
SELECT b.id::text, w.key, b.page_no, b.type, b.section_path, b.text, f.id::text,
       ts_rank(to_tsvector('english', coalesce(b.text, '')), plainto_tsquery('english', %(q)s)) AS lex,
       similarity(coalesce(b.text, ''), %(q)s) AS trg
  FROM litkb.blocks b
  JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id
  JOIN litkb.main_files mf ON mf.version_id = f.current_version_id
  JOIN litkb.main_works w ON w.work_id = mf.work_id
 WHERE to_tsvector('english', coalesce(b.text, '')) @@ plainto_tsquery('english', %(q)s)
    OR coalesce(b.text, '') %% %(q)s
 ORDER BY lex DESC, trg DESC
 LIMIT %(n)s
"""

_SEARCH_USES = """
SELECT u.version_id::text, w.key, g.slug, u.statement, u.kind, u.status, u.feeds, u.state,
       ts_rank(to_tsvector('english', u.statement), plainto_tsquery('english', %(q)s)) AS lex,
       similarity(u.statement, %(q)s) AS trg
  FROM litkb.main_uses u
  JOIN litkb.main_works w ON w.work_id = u.work_id
  LEFT JOIN litkb.gaps g ON g.id = u.gap_id
 WHERE to_tsvector('english', u.statement) @@ plainto_tsquery('english', %(q)s)
    OR u.statement %% %(q)s
 ORDER BY lex DESC, trg DESC
 LIMIT %(n)s
"""


def _rrf(*legs, k=60):
    """Reciprocal-rank fusion (design §8). Each leg is a list of (id, payload) already in its own
    rank order; the score of an id is the sum of 1/(k + rank) over the legs that returned it. One
    leg fuses to the same ORDER as that leg, which is why the vector leg can be added without
    changing the shape here."""
    score, payload = {}, {}
    for leg in legs:
        for rank, (key, item) in enumerate(leg, start=1):
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank)
            payload.setdefault(key, item)
    return [payload[key] | {"score": round(score[key], 6)}
            for key in sorted(score, key=lambda i: (-score[i], str(i)))]


def _search(query, limit, scope):
    with _conn("reader") as conn:
        hits = {"blocks": [], "uses": []}
        if scope in ("all", "blocks"):
            rows = conn.execute(_SEARCH_BLOCKS, {"q": query, "n": limit}).fetchall()
            lex = [(r[0], {"block_id": r[0], "work_key": r[1], "page": r[2], "block_type": r[3],
                           "section_path": r[4], "text": r[5], "file_id": r[6]}) for r in rows]
            trg = [(r[0], {}) for r in sorted(rows, key=lambda r: -(r[8] or 0))]
            hits["blocks"] = _rrf(lex, trg)[:limit]
        if scope in ("all", "uses"):
            rows = conn.execute(_SEARCH_USES, {"q": query, "n": limit}).fetchall()
            lex = [(r[0], {"use_version_id": r[0], "work_key": r[1], "gap": r[2], "statement": r[3],
                           "kind": r[4], "status": r[5], "feeds": r[6], "state": r[7]}) for r in rows]
            trg = [(r[0], {}) for r in sorted(rows, key=lambda r: -(r[9] or 0))]
            hits["uses"] = _rrf(lex, trg)[:limit]
    return _ok(query=query, scope=scope, legs=(["lexical", "trigram", "vector"] if VECTOR_ENABLED
                                               else ["lexical", "trigram"]),
               vector_leg="enabled" if VECTOR_ENABLED else
                          "OFF until P7 lands embeddings: these hits are lexical, so a paraphrase "
                          "that shares no words with the text will NOT be found",
               **hits)


def _work(doi=None, key=None):
    # the DOI is normalised by litkb.norm_identifier IN the statement — the database's own twin of
    # litkb.textnorm.normalize_doi (migration 0014, D1), driven against it over doi_forms.csv. A
    # Python call here would be the same transformation applied immediately before its twin, so it
    # is not made: one normaliser, at the place the comparison happens.
    with _conn("reader") as conn:
        if doi:
            row = conn.execute(
                "SELECT w.key, w.work_id::text FROM litkb.main_works w "
                "JOIN litkb.main_identifiers i ON i.work_id = w.work_id "
                "WHERE i.scheme = 'doi' AND i.value_norm = litkb.norm_identifier('doi', %s)",
                (doi,)).fetchone()
        elif key:
            row = conn.execute("SELECT key, work_id::text FROM litkb.main_works WHERE key = %s",
                               (key,)).fetchone()
        else:
            return _refuse("no-selector", "litkb_work takes a doi or a key")
        if not row:
            return _ok(found=False, doi=doi, key=key,
                       hint="the work is not admitted in main's view. litkb_admit admits it; a work "
                            "admitted in another open workstream is not visible here until Kam merges "
                            "its promotion.")
        key, work_id = row
        w = conn.execute("SELECT type, title, authors, year, container, publisher, work_id::text "
                         "FROM litkb.main_works WHERE key = %s", (key,)).fetchone()
        ids = conn.execute("SELECT scheme, value_norm, verified_by, active FROM litkb.main_identifiers "
                           "WHERE work_id = %s ORDER BY scheme, value_norm", (work_id,)).fetchall()
        files = conn.execute(
            "SELECT f.sha256, v.path, v.bytes, v.pages, f.current_run_id::text "
            "FROM litkb.main_files v JOIN litkb.files f ON f.current_version_id = v.version_id "
            "WHERE v.work_id = %s ORDER BY v.path", (work_id,)).fetchall()
        uses = conn.execute(
            "SELECT u.version_id::text, g.slug, u.statement, u.kind, u.status, u.feeds "
            "FROM litkb.main_uses u LEFT JOIN litkb.gaps g ON g.id = u.gap_id "
            "WHERE u.work_id = %s ORDER BY u.created_at", (work_id,)).fetchall()
        disc = conn.execute(
            "SELECT source, source_row, field, claimed_value, registry_value, ratio "
            "FROM litkb.discrepancies WHERE work_id = %s ORDER BY source, field", (work_id,)).fetchall()
    return _ok(found=True, key=key, work_id=work_id,
               work=dict(zip(("type", "title", "authors", "year", "container", "publisher", "work_id"), w)),
               identifiers=[dict(zip(("scheme", "value", "verified_by", "active"), r)) for r in ids],
               files=[dict(zip(("sha256", "path", "bytes", "pages", "current_run_id"), r)) for r in files],
               uses=[dict(zip(("use_version_id", "gap", "statement", "kind", "status", "feeds"), r))
                     for r in uses],
               discrepancies=[dict(zip(("source", "source_row", "field", "claimed", "registry", "ratio"), r))
                              for r in disc])


def _candidates(limit, state=None):
    ws_id, _token = _session()
    with _conn("reader") as conn:
        rows = conn.execute(
            "SELECT id::text, state, source, source_detail, title, year, identifiers, admitted_work_id::text "
            "FROM litkb.candidates WHERE workstream_id = %s "
            "AND (%s::text IS NULL OR state = %s) ORDER BY created_at DESC LIMIT %s",
            (ws_id, state, state, limit)).fetchall()
    return _ok(workstream_id=str(ws_id), candidates=[
        dict(zip(("candidate_id", "state", "source", "source_detail", "title", "year",
                  "identifiers", "admitted_work_id"), r)) for r in rows])


def _ws_status():
    ws_id, _token = _session()
    with _conn("reader") as conn:
        row = conn.execute("SELECT slug, git_branch, state, opened_at, purpose FROM litkb.workstreams "
                           "WHERE id = %s", (ws_id,)).fetchone()
        if not row:
            return _refuse("unknown-workstream",
                           f"workstream {ws_id} is not in database {_db()}: the token file names a "
                           "workstream this database does not have (wrong LITKB_DB?)")
        counts = {t: dict(conn.execute(
            f"SELECT state, count(*) FROM litkb.{t} WHERE workstream_id = %s GROUP BY 1 ORDER BY 1",
            (ws_id,)).fetchall()) for t in ("candidates", "admissions")}
        attempts = conn.execute(
            "SELECT route, status, count(*) FROM litkb.acquisition_attempts WHERE workstream_id = %s "
            "GROUP BY 1, 2 ORDER BY 1, 2", (ws_id,)).fetchall()
        heads = dict(conn.execute("SELECT entity, count(*) FROM litkb.ws_heads WHERE workstream_id = %s "
                                  "GROUP BY 1 ORDER BY 1", (ws_id,)).fetchall())
        prom = conn.execute("SELECT id::text, state, prepared_at FROM litkb.promotions "
                            "WHERE workstream_id = %s ORDER BY prepared_at DESC", (ws_id,)).fetchall()
    return _ok(workstream_id=str(ws_id), slug=row[0], branch=row[1], state=row[2], opened_at=row[3],
               purpose=row[4], candidates=counts["candidates"], admissions=counts["admissions"],
               attempts=[list(a) for a in attempts], proposed_versions=heads,
               promotions=[dict(zip(("promotion_id", "state", "prepared_at"), p)) for p in prom])


# ── write tools ───────────────────────────────────────────────────────────────────────────

def _ws_open(slug, purpose, branch=None, brief=None):
    from litkb import workstream

    wt = _worktree()
    if (wt / workstream.TOKEN_FILE).exists():
        return _refuse("workstream-exists",
                       f"{wt / workstream.TOKEN_FILE} already exists: finish or abandon that "
                       "workstream before opening another in this worktree.")
    if not branch:
        r = subprocess.run(["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True)
        branch = r.stdout.strip() if r.returncode == 0 else "unknown"
    with _conn("writer") as conn:
        ws_id = workstream.open_workstream(conn, slug, branch, purpose, directory=wt, brief_path=brief)
    # the ID, never the token: open_workstream returns the token once, into the file, and nothing
    # here reads it back out.
    return _ok(workstream_id=str(ws_id), slug=slug, branch=branch, worktree=str(wt),
               note="the token was written to .litkb-workstream and is never printed or returned")


def _admit(doi=None, arxiv=None, title=None, authors=None, year=None, key=None, file=None,
           agent=None, session=None):
    from litkb.admit import front

    ws_id, token = _session()
    a, s = _labels(agent, session)
    if not (doi or arxiv):
        return _refuse("no-identifier",
                       "litkb_admit takes a DOI or an arXiv id — identity comes from the registry "
                       "record plus the verified file (the DOI-first rule). A work no registry can "
                       "confirm is a MANUAL admission, which is a proposal a second session signs "
                       "off: run `py -3.12 -m litkb admit --manual ...` at the CLI. No MCP tool "
                       "admits or approves one, because the approval must not come from this session.")
    claimed = {k: v for k, v in (("title", title), ("authors", authors), ("year", year)) if v}
    with _conn("writer") as conn:
        res = front.admit_registry(conn, ws_id, token, doi=doi, arxiv=arxiv, claimed=claimed or None,
                                   key=key, file_path=file, agent=a, session=s,
                                   client=_registry_client())
    return _out({"ok": res.get("outcome") == "admitted"} | res)


def _acquire(key=None, doi=None, routes="open_access", from_file=None, max_archive_downloads=0,
             agent=None, session=None):
    from litkb.acquire import run

    ws_id, token = _session()
    a, s = _labels(agent, session)
    with _conn("writer") as conn:
        work = run.work_record(conn, key=key, doi=doi)
        if not work:
            return _refuse("not-admitted",
                           "no admitted work with that key or DOI. A PDF is never fetched for a work "
                           "the knowledge base does not hold: admit it first (litkb_admit).")
        budget = run.Budget(max_archive_downloads=max_archive_downloads)
        out = run.acquire(conn, ws_id, token, work,
                          routes=tuple(r.strip() for r in routes.split(",") if r.strip()),
                          agent=a, session=s, budget=budget, from_file=from_file)
    out = {k: v for k, v in out.items() if k != "detail"}
    return _out({"ok": out.get("outcome") in ("ok", "already-held"), "key": work["key"],
                 "archive_downloads_used": budget.used} | out)


def _record_use(statement, kind, quote, block_id, gap, work_key=None, doi=None, gap_question=None,
                feeds=None, stance="supports", page=None, rationale=None,
                char_start=None, char_end=None, agent=None, session=None):
    """A use and its evidence, in one call. The QUOTE is located in the block's own text here, so
    the offsets the database checks are the ones the quote actually occupies — and a quote that is
    not in that block is refused BEFORE anything is written (`quote-not-in-block`).

    `quote_verified` itself is never this server's word: the database recomputes it from the block
    text at [char_start, char_end) in a trigger the writer role cannot name (migration 0007/0010,
    P1 kill M3). What comes back below is what the database stored.

    char_start/char_end are accepted only to let a test record a DELIBERATELY unverifiable quote —
    the P8 kill needs one to reach `promote prepare` and be refused there."""
    from psycopg.types.json import Jsonb

    ws_id, token = _session()
    a, s = _labels(agent, session)
    if kind not in ("method", "theorem", "parameter", "empirical evidence", "negative result",
                    "context", "contradiction"):
        return _refuse("bad-kind", f"kind must be one of the seven use kinds, got {kind!r}")
    with _conn("writer") as conn:
        blk = conn.execute(
            "SELECT b.text, b.page_no, b.run_id::text, f.current_run_id::text, mw.key, mf.work_id::text "
            "FROM litkb.blocks b JOIN litkb.files f ON f.id = b.file_id "
            "JOIN litkb.main_files mf ON mf.version_id = f.current_version_id "
            "JOIN litkb.main_works mw ON mw.work_id = mf.work_id WHERE b.id = %s", (block_id,)).fetchone()
        if not blk:
            return _refuse("unknown-block",
                           f"no block {block_id}. Evidence points at a block of the file's CURRENT "
                           "extraction run — take the block_id from litkb_search.")
        text, block_page, run_id, current_run, blk_key, work_id = blk
        if run_id != current_run:
            return _refuse("stale-run",
                           "that block belongs to a superseded extraction run; its evidence could "
                           "never be promoted (design §4.5). Search again for the current run's block.")
        if char_start is None or char_end is None:
            i = (text or "").find(quote)
            if i < 0:
                return _refuse("quote-not-in-block",
                               "the quote is not in that block's text. A use is evidenced by a quote "
                               "the database can find at the offsets recorded — paraphrase in the "
                               "statement, never in the quote.", block_id=block_id, work_key=blk_key)
            char_start, char_end = i, i + len(quote)
        if work_key and work_key != blk_key:
            return _refuse("work-mismatch",
                           f"the block belongs to {blk_key}, not {work_key}: evidence must come from "
                           "the work the use is about.")
        if doi or work_key:
            sel = conn.execute(
                "SELECT w.work_id::text FROM litkb.main_works w "
                "LEFT JOIN litkb.main_identifiers i ON i.work_id = w.work_id AND i.scheme = 'doi' "
                "WHERE w.key = %s OR i.value_norm = litkb.norm_identifier('doi', %s)",
                (work_key, doi)).fetchone()
            if sel and sel[0] != work_id:
                return _refuse("work-mismatch", "the block's work is not the work named")
        gap_id = conn.execute("SELECT id::text FROM litkb.gaps WHERE slug = %s", (gap,)).fetchone()
        if not gap_id:
            if not gap_question:
                return _refuse("unknown-gap",
                               f"no gap {gap!r}. A use answers a question: pass gap_question to open "
                               "the gap in this workstream, or name one that exists.")
            g = conn.execute(
                "SELECT * FROM litkb.write_proposal('gap', NULL, %s, NULL, %s, %s, %s, %s, %s, %s)",
                (Jsonb({"slug": gap}), Jsonb({"question": gap_question, "gap_state": "open"}),
                 None, ws_id, token, a, s)).fetchone()
            gap_id = (str(g[0]),)
        use = conn.execute(
            "SELECT * FROM litkb.write_proposal('use', NULL, %s, NULL, %s, %s, %s, %s, %s, %s)",
            (Jsonb({"work_id": work_id, "gap_id": gap_id[0]}),
             Jsonb({"statement": statement, "kind": kind, "status": "proposed",
                    "feeds": list(feeds or []), "rationale": rationale}),
             None, ws_id, token, a, s)).fetchone()
        use_id, use_version = str(use[0]), str(use[1])
        ev = conn.execute("SELECT * FROM litkb.add_evidence(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (ws_id, token, use_version, block_id, run_id,
                           page if page is not None else block_page, quote, char_start, char_end,
                           stance)).fetchone()
        evidence_id, verified = str(ev[0]), bool(ev[1])
    return _out({"ok": verified, "use_id": use_id, "use_version_id": use_version,
                 "evidence_id": evidence_id, "quote_verified": verified, "work_key": blk_key,
                 "gap": gap, "char_start": char_start, "char_end": char_end,
                 "note": ("the database verified the quote against the block text"
                          if verified else
                          "the database could NOT verify this quote at those offsets. It is stored, "
                          "but promote prepare will refuse the chain until it is corrected.")})


def _propose_promotion(report_path=None, repo=None):
    """`promote prepare`, run as a SUBPROCESS of the CLI.

    Not an import: `promote_prepare` may be executed only by `litkb_promoter` (design §4.7), and
    this server must never hold that credential — §9 puts prepare outside the MCP surface for
    exactly that reason. Running the CLI keeps the passfile in a process that exits, and keeps this
    server's own logins to reader and writer. `promote commit` has no tool at all: it runs after
    Kam's merge, from a session that can see the merge commit."""
    ws_id, _token = _session()
    wt = Path(repo) if repo else _worktree()
    cmd = [sys.executable, "-m", "litkb", "--db", _db(), "--dir", str(wt), "promote", "prepare"]
    if report_path:
        cmd += ["--report", report_path]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(SCRIPTS / "pipeline"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(wt), env=env)
    try:
        payload = json.loads(r.stdout)
    except ValueError:
        payload = {"stdout": r.stdout[-4000:]}
    return _out({"ok": r.returncode == 0, "workstream_id": str(ws_id), "returncode": r.returncode,
                 "stderr": r.stderr[-4000:]} | payload)


# ── the MCP surface ───────────────────────────────────────────────────────────────────────

def _guarded(fn):
    """Turn a Refusal into a refusal RESULT, and any other exception into one too: a tool that
    raises through the protocol tells the model nothing it can act on, and an unredacted traceback
    is exactly the shape a leaked credential travels in."""
    def call(**kw):
        try:
            return fn(**kw)
        except Refusal as e:
            return _refuse(e.code, e.message, **e.extra)
        except Exception as e:                       # noqa: BLE001 — the boundary is the point
            return _refuse("error", f"{type(e).__name__}: {e}", tool=fn.__name__)
    call.__name__ = fn.__name__
    return call


def build_server():
    """The MCPServer with the nine tools bound. `mcp` is imported HERE, never at module top."""
    from mcp.server.mcpserver import MCPServer

    srv = MCPServer(name=SERVER_NAME, version=VERSION, instructions=(
        "The Edmonds project's literature knowledge base. Search it BEFORE any web or paper-search "
        "route: a work the project relies on is admitted, acquired and cited here. Writes need an "
        "open workstream in this worktree (litkb_ws_open); the token is never passed to a tool. "
        "promote commit and approve are deliberately absent — they belong to Kam's merge and to a "
        "second session."))

    @srv.tool(name="litkb_search", description=(
        "Hybrid lexical search over extracted blocks and recorded uses. Returns work key, page, "
        "section path and block_id (the block_id is what litkb_record_use quotes from). The vector "
        "leg is off until P7, so a paraphrase sharing no words with the text will not be found."))
    def litkb_search(query: str, limit: int = 10, scope: str = "all") -> str:
        return _guarded(_search)(query=query, limit=min(max(int(limit), 1), 50), scope=scope)

    @srv.tool(name="litkb_work", description=(
        "One work by DOI or key: its registry-confirmed fields, identifiers, held files, recorded "
        "uses, and any discrepancies between what a legacy record claimed and what the registry says."))
    def litkb_work(doi: str = "", key: str = "") -> str:
        return _guarded(_work)(doi=doi or None, key=key or None)

    @srv.tool(name="litkb_candidates", description=(
        "Candidates recorded in this worktree's workstream — what was found, what was admitted, "
        "what was not."))
    def litkb_candidates(limit: int = 25, state: str = "") -> str:
        return _guarded(_candidates)(limit=min(max(int(limit), 1), 200), state=state or None)

    @srv.tool(name="litkb_ws_open", description=(
        "Open a literature workstream for this worktree. Returns the workstream id; the secret "
        "token is written to .litkb-workstream and is never returned or printed."))
    def litkb_ws_open(slug: str, purpose: str, branch: str = "", brief: str = "") -> str:
        return _guarded(_ws_open)(slug=slug, purpose=purpose, branch=branch or None, brief=brief or None)

    @srv.tool(name="litkb_ws_status", description=(
        "This worktree's workstream: state, candidates, admissions, acquisition attempts, proposed "
        "versions and any prepared promotion."))
    def litkb_ws_status() -> str:
        return _guarded(_ws_status)()

    @srv.tool(name="litkb_admit", description=(
        "Admit a work by DOI or arXiv id, optionally binding a PDF already on disk. Identity is the "
        "registry record plus the verified file; the five admission checks run in one transaction. "
        "A work no registry can confirm is a manual admission at the CLI, signed off by a SECOND "
        "session — not by any tool here."))
    def litkb_admit(doi: str = "", arxiv: str = "", title: str = "", authors: str = "",
                    year: str = "", key: str = "", file: str = "") -> str:
        return _guarded(_admit)(doi=doi or None, arxiv=arxiv or None, title=title or None,
                                authors=authors or None, year=year or None, key=key or None,
                                file=file or None)

    @srv.tool(name="litkb_acquire", description=(
        "Fetch an admitted work's PDF: open access first, then the archive, then Sci-Hub. Every "
        "attempt is logged whether it succeeds or not. Never fetch a PDF outside a workstream."))
    def litkb_acquire(key: str = "", doi: str = "", routes: str = "open_access",
                      from_file: str = "", max_archive_downloads: int = 0) -> str:
        return _guarded(_acquire)(key=key or None, doi=doi or None, routes=routes,
                                  from_file=from_file or None,
                                  max_archive_downloads=int(max_archive_downloads))

    @srv.tool(name="litkb_record_use", description=(
        "Record what a work supplies to a question (a gap), with a verbatim quote from a block of "
        "the file's current extraction run. The quote's offsets are located here and VERIFIED by the "
        "database; an unverified quote is stored but its chain is refused at promote prepare."))
    def litkb_record_use(statement: str, kind: str, quote: str, block_id: str, gap: str,
                         gap_question: str = "", work_key: str = "", doi: str = "",
                         feeds: str = "", stance: str = "supports", page: int = 0,
                         rationale: str = "", char_start: int = -1, char_end: int = -1) -> str:
        return _guarded(_record_use)(
            statement=statement, kind=kind, quote=quote, block_id=block_id, gap=gap,
            gap_question=gap_question or None, work_key=work_key or None, doi=doi or None,
            feeds=[f.strip() for f in feeds.split(";") if f.strip()], stance=stance,
            page=page or None, rationale=rationale or None,
            char_start=None if char_start < 0 else char_start,
            char_end=None if char_end < 0 else char_end)

    @srv.tool(name="litkb_propose_promotion", description=(
        "Offer this workstream's proposed versions to main: group them into chains, re-run the "
        "checks, and write the promotion report onto the work branch for Kam to review inside the "
        "merge. PREPARE ONLY — committing the promotion happens after Kam merges, and is not a tool."))
    def litkb_propose_promotion(report_path: str = "", repo: str = "") -> str:
        return _guarded(_propose_promotion)(report_path=report_path or None, repo=repo or None)

    return srv


def main(argv=None):
    srv = build_server()
    srv.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())

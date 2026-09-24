"""The litkb MCP server — the agents' path into the literature knowledge base (design §9, §9.1).

    py -3.12 -m litkb.mcp.server            # stdio, one MCP session per process

Thirteen tools. Everything an agent may do to literature goes through them; everything an agent may
NOT do is absent, not merely discouraged:

    read    litkb_search  litkb_work  litkb_candidates  litkb_ws_status  litkb_my_uses
            litkb_brief
    write   litkb_ws_open  litkb_admit  litkb_acquire  litkb_record_use  litkb_hunt
            litkb_hunt_request_add
    offer   litkb_propose_promotion        (prepare ONLY; commit is not a tool)

`litkb_brief` is the thirteenth, added 2026-09-18 (Task B, the same delta as
`litkb_hunt_request_add`): the per-workstream export a managing agent reads instead of the raw
tables — every hunt_request marked EXPECTED (an unverified prior) and every promotable quote
marked VERIFIED (work key, page, block id), never dropping an unconfirmed or contradicted
expectation. `litkb/brief.py` is the whole mechanism; this tool is a thin read wrapper, like
`litkb_my_uses`.

`litkb_hunt_request_add` is the twelfth, added 2026-09-18 (migration 0023): a review agent's
drop-off — the claim it expects a paper to support, why, and the unverified abstract passage it
reasoned from — written before the paper is even hunted, so a later verified use can be checked
against the expectation that motivated the hunt.

`litkb_hunt` is the eleventh, added 2026-09-16: the five steps of the hunt protocol driven end to
end from one reference, so a session stops driving seven tools in order and diagnosing the gap
when one is skipped. Like `litkb_propose_promotion` it runs the CLI as a subprocess, because it
INGESTS and the ingest login must not be held by a long-lived server (§4.7).

`litkb_my_uses` is the tenth, added 2026-09-16: the operational test found that recording a use and
reading it back were different systems — `litkb_ws_status` answered `{"gap": 6, "use": 6}` and
`litkb_work` reads main's view, which holds none of a session's own proposals, so a session could
not see its own work at all before the promotion report.

Four rules this module keeps, each because something else cannot:

1. **The workstream token is never a tool parameter.** A parameter is written into the model's
   transcript, and a transcript is a sink. The token is read from `<worktree>/.litkb-workstream`
   (`litkb.workstream.load`), where `worktree` is LITKB_WORKTREE or the process's cwd, and is then
   passed to the database as a BOUND QUERY PARAMETER by the functions in `litkb.admit`,
   `litkb.acquire` and below — never formatted into SQL (design §5; third P1 referee F-8). A write
   tool called from a directory with no token file is REFUSED with `no-workstream`, and names the
   tool that opens one. `_session()` also registers the token with `netutil.add_secret()`, so if it
   ever reached a string this server returns, `_out()` would replace it with `<KEY>`. The READ tools
   that answer about a workstream — `litkb_candidates`, `litkb_ws_status`, `litkb_my_uses`, `litkb_brief` — present
   that token to the database too (`_require_token`, migration 0018): the token file is the only place a token can
   come from, and a file naming a real workstream with a WRONG token gets `bad-token` and nothing
   else (P8 referee F-1; before that fix a forged token read a workstream's whole status).

2. **One output boundary, two redactors.** Every tool returns `_out(...)`: `redact_shapes()` over the
   object, then `redact()` over the JSON. The first masks credential SHAPES this process never held
   (a pgpass line in a block's text, a URL's `key=`, a PEM block); the second replaces the strings
   `add_secret()` armed. Two call sites, both in one function, so the harness's per-call-site rule
   (`qc/instruments/litkb_p2_mutations.py`, rows X1/X2/X7) covers each and a reader can check both by
   reading one function. This module has no `print` and writes to no stream: on stdio, stdout IS the
   protocol.

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

from litkb import visibility

VERSION = "0.1.0"
SERVER_NAME = "litkb"
SCRIPTS = Path(__file__).resolve().parents[3]

#: the vector leg is WIRED, not live: P7 builds the embeddings and the referee's paraphrased query
#: set that scores them (design §8, §14 P7). Until then `litkb_search` is lexical, and says so in
#: every result rather than letting a caller assume semantic recall it is not getting.
VECTOR_ENABLED = os.environ.get("LITKB_VECTOR_SEARCH") == "1"


# ── the output boundary ───────────────────────────────────────────────────────────────────

def _out(obj):
    """THE one way a tool returns. Shapes, then JSON, then registered secrets.

    TWO redactors, in that order, because they catch different things and only one of them can be
    armed in advance:

      `redact_shapes(obj)` runs on the OBJECT, before json.dumps. It masks credential SHAPES —
      a pgpass line, a URL's `key=`, a `password:` field, a PEM block — including ones this process
      never held and could not have registered. It must run before the dump: by then a block's text
      is a single JSON string with `\\n` escapes, and the line-anchored pgpass rule can never match
      inside it. That is exactly how the P8 referee got `localhost:5433:litkb:litkb_writer:<pw>`
      back out of a search result verbatim (F-4).

      `redact(...)` runs on the JSON TEXT and replaces the strings `netutil.add_secret` was given —
      the workstream token armed by `_session()`, an archive key armed by the acquisition route.

    Mutation rows X1 (redact) and X7 (redact_shapes) strip one each; the two planted-secret tests
    answer them. Nothing else in this package writes to a stream."""
    from litkb.netutil import redact, redact_shapes

    return redact(json.dumps(redact_shapes(obj), indent=1, default=str, ensure_ascii=False))


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
    """Where `.litkb-workstream` lives, resolved the SAME way the CLI resolves it.

    A registered stdio server's cwd is wherever Claude Code launched it — `Scripts\\` at best, the
    user's home at worst — so `os.getcwd()` alone would have `litkb_ws_open` write the token file
    somewhere `py -3.12 -m litkb` never looks, and the two halves of the access layer would each
    believe the other had no workstream. So the order is the CLI's (`commands._worktree`): an
    explicit LITKB_WORKTREE, else git's top level from the cwd, else the cwd itself."""
    named = os.environ.get("LITKB_WORKTREE")
    if named:
        return Path(named).resolve()
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    top = r.stdout.strip() if r.returncode == 0 else ""
    return Path(top or os.getcwd()).resolve()


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


def _require_token(conn, ws_id, token):
    """The READ tools' token check (P8 referee F-1). Refuses before a single workstream row is read.

    The referee wrote a `.litkb-workstream` naming the REAL workstream id with 64 zeros as its
    token, and `litkb_ws_status` answered `ok: true` with the whole status. Workstream ids are not
    secret — a tracked report prints one, and `litkb_ws_open` returns one by design — so that attack
    needed no secret at all. The writes were safe only because the DATABASE presents the token on
    every write function; the reads presented nothing and queried `WHERE workstream_id = %s`.

    `litkb.check_ws_token` (migration 0018) is a SECURITY DEFINER boolean: no agent role may read
    litkb.workstream_tokens, and `_require_ws_token` RAISEs, which is the wrong shape for a tool that
    must refuse having written nothing. A database without 0018 fails CLOSED here — the refusal says
    which migration is missing rather than answering with the workstream's internals."""
    import psycopg

    try:
        ok = conn.execute("SELECT litkb.check_ws_token(%s, %s)", (ws_id, token)).fetchone()[0]
    except psycopg.errors.UndefinedFunction:
        raise Refusal("no-token-check",
                      "this database has no litkb.check_ws_token: migration 0018 has not been "
                      "applied, so the workstream token cannot be verified and no workstream "
                      "internals are returned.") from None
    if not ok:
        raise Refusal("bad-token", BAD_TOKEN_MESSAGE)


def _require_open(conn, ws_id):
    """Refuse a tool that reads or writes THIS workstream's own proposals when it is no longer open.

    The counterpart of `_caller_workstream`'s state check, for the tools where narrowing to main is
    not a sensible answer: `litkb_brief` and `litkb_record_use` are ABOUT one workstream, so a
    merged or abandoned one must be told so rather than handed a main-only view of somebody else's
    material. The database already refuses the WRITE on state (`_write_version`, 0007:39-44) — with
    an InvalidParameterValue that `_guarded` turns into an opaque `error`; this makes the refusal
    the read path's own, before a row is read or a gap is proposed.

    Every call site runs this AFTER `_require_token`, so a workstream's state is told to nobody who
    has not presented its token. That was not true of `_record_use` when this function was written —
    it checked no token itself and left that to the database's own check on the write — and the
    fix was to give `_record_use` the token check rather than to accept the disclosure."""
    if not visibility.is_open(conn, ws_id):
        row = conn.execute("SELECT state FROM litkb.workstreams WHERE id = %s", (ws_id,)).fetchone()
        raise Refusal("workstream-not-open",
                      f"this worktree's workstream is {row[0] if row else 'not in this database'}, "
                      "not open: a merged or abandoned workstream neither reads back its own "
                      "unapproved proposals nor records new uses. Its .litkb-workstream outlived "
                      "it — remove that file, or open a new workstream here with litkb_ws_open.",
                      state=row[0] if row else None)


#: one sentence for a refused token, wherever it is refused — here for the read tools, and in
#: `_guarded` for the write tools, where it arrives as the database's InsufficientPrivilege. It
#: names NOTHING about the workstream: not its slug, not its state, not whether it exists.
BAD_TOKEN_MESSAGE = (
    "the token in this worktree's .litkb-workstream is not this workstream's token. Nothing about "
    "the workstream is returned to a caller that cannot present it. If the file was copied from "
    "another worktree, delete it and open a workstream here with litkb_ws_open.")


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

# Both legs read the text and the query through litkb.norm_search_text (migration 0018, body
# replaced by 0025): U+FFFD and soft hyphens dropped, line-break hyphenation joined, whitespace
# collapsed; since 0025 a C0 control byte inside a word (an extracted ff/fi/fl ligature of unknown
# identity) has its alternative spellings PREPENDED to the text, the 0018 output following them
# byte for byte, so the index gains `floating` beside `<1d>oating` and loses nothing (measured on
# every block of the 2026-09-19 dump: 0 lexemes lost). The P8 referee's Q3 is
# what this is for — the block holds `misclassi<FFFD>cation` and `this overesti- mate increases`
# because that is what the PDF's text layer renders, so the gold passage was reachable only by a
# caller who already knew how the extractor had mangled the word (§2.4). The normaliser is ONE SQL
# function applied to both sides in the same statement: a Python query normaliser beside a SQL text
# normaliser is the twin-drift migration 0014 D1 was written against. The blocks still STORE what
# the PDF said; this repairs retrieval, and the real repair belongs upstream in P4/P5.
# THREE legs, each its own statement, each with its own LIMIT. That is the change of shape: before,
# one statement selected the all-terms matches and re-sorted them by trigram similarity, so what the
# result called two legs was one candidate set ordered twice (P8 referee §3.5) and a block only
# trigram could find, below the lexical cut, was never retrieved at all.
#: `visibility.FILE_JOIN` replaced the `main_files`/`main_works` join here on 2026-09-20
#: (decisions.yaml litkb-web-source-gate): the caller's OWN workstream also sees the files it has
#: proposed and a second session has not yet approved. With no open workstream this is the same
#: join it was; the module's docstring is the one home for why, and for what promotion still holds.
_BLOCK_FROM = f"""
  FROM litkb.blocks b
  JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id
  {visibility.FILE_JOIN}
 WHERE b.type = ANY(%(kinds)s)
"""
_BLOCK_COLS = "SELECT b.id::text, w.key, b.page_no, b.type, b.section_path, b.text, f.id::text"

#: What a search is FOR: the passage that answers a question. The final referee's §7 measured what
#: happens without this clause — two cold questions, 8 of 20 top-ten hits were `page_header` or
#: title blocks, ONE running head ("CONSTRAINED MONTE CARLO MAXIMUM LIKELIHOOD", 42 characters)
#: returned five times in one ten-row list from five different pages of Geyer_1992, and the second
#: question surfaced no answering body passage at all. Furniture is not a passage: a running head
#: is the same string on every page of a paper, so it matches a topical query once per page and
#: crowds out the one block that says something.
#:
#: `reference` is excluded on the same rule and for a different reason: a bibliography entry names
#: a paper, it does not state a finding, and after the canonical-block merge the ~9,300 printed
#: reference entries carry the `reference` type instead of hiding as `paragraph` — so excluding
#: them by default is only possible NOW, and was the other half of what crowded the referee's
#: ten-row lists.
#:
#: `title`, `author` and `affiliation` STAY IN, which is a judgment and is written down as one: a
#: title is the most compressed statement a paper makes about itself and a session searching for a
#: paper by its subject should find it. They exist as types at all only since the header pass.
DEFAULT_KINDS = ("title", "author", "affiliation", "abstract", "heading", "paragraph",
                 "list_item", "footnote", "caption", "table", "figure", "equation", "sidebar")

#: Everything migration 0002's CHECK admits — what `kinds="all"` means.
ALL_KINDS = DEFAULT_KINDS + ("reference", "page_header", "page_footer", "page_number", "other")


def _kinds(spec):
    """-> (the block types to search, a sentence saying what was left out).

    `spec` is empty for the default, "all" for everything, or a comma-separated list of block
    types. An unknown name is REFUSED rather than dropped: a caller who mistypes `page-header`
    should be told, not handed a silently different result set.
    """
    spec = (spec or "").strip().lower()
    if not spec:
        return list(DEFAULT_KINDS), (
            "block types page_header, page_footer, page_number, other and reference are NOT "
            "searched by default (running heads and bibliography entries crowd out passages). "
            "Pass kinds=\"all\", or a comma-separated list of types, to include them.")
    if spec == "all":
        return list(ALL_KINDS), "every block type is searched, furniture and references included."
    want = [k.strip() for k in spec.split(",") if k.strip()]
    bad = [k for k in want if k not in ALL_KINDS]
    if bad:
        raise Refusal("bad-kinds", f"not a block type: {', '.join(bad)}. The types are: "
                                   f"{', '.join(sorted(ALL_KINDS))}.", kinds=spec)
    return want, f"only these block types were searched: {', '.join(want)}."

#: leg 1 — every term present. Precision: the hits this leg returns are the ones that answer the
#: whole question, and RRF keeps them above the looser legs.
_SEARCH_BLOCKS_ALL = f"""
{_BLOCK_COLS}{_BLOCK_FROM}
   AND to_tsvector('english', litkb.norm_search_text(b.text))
       @@ plainto_tsquery('english', litkb.norm_search_text(%(q)s))
 ORDER BY ts_rank(to_tsvector('english', litkb.norm_search_text(b.text)),
                  plainto_tsquery('english', litkb.norm_search_text(%(q)s))) DESC, b.id
 LIMIT %(n)s
"""

#: leg 2 — ANY term, ranked by how much of the question the block answers. This is what recovers the
#: referee's Q3 (§2.4): its gold passage says "NEs" where the question says "naive estimators", and
#: the PDF's text layer ate the ligature in "misclassification", so under all-terms matching it was
#: unreachable by anything but a caller who already knew how the extractor had mangled it.
_SEARCH_BLOCKS_ANY = f"""
{_BLOCK_COLS}{_BLOCK_FROM}
   AND to_tsvector('english', litkb.norm_search_text(b.text)) @@ litkb.any_term_query(%(q)s)
 ORDER BY ts_rank(to_tsvector('english', litkb.norm_search_text(b.text)),
                  litkb.any_term_query(%(q)s)) DESC, b.id
 LIMIT %(n)s
"""

#: leg 3 — trigram, now a leg of its OWN: its own WHERE, its own ORDER BY, its own LIMIT. It finds
#: what neither lexical leg can — a misspelling, a mangled word, a query that shares no whole token
#: with the text.
_SEARCH_BLOCKS_TRGM = f"""
{_BLOCK_COLS}{_BLOCK_FROM}
   AND litkb.norm_search_text(b.text) %% litkb.norm_search_text(%(q)s)
 ORDER BY similarity(litkb.norm_search_text(b.text), litkb.norm_search_text(%(q)s)) DESC, b.id
 LIMIT %(n)s
"""

_USE_COLS = ("SELECT u.version_id::text, w.key, g.slug, u.statement, u.kind, u.status, u.feeds, "
             "u.state")
_USE_FROM = """
  FROM litkb.main_uses u
  JOIN litkb.main_works w ON w.work_id = u.work_id
  LEFT JOIN litkb.gaps g ON g.id = u.gap_id
"""

_SEARCH_USES_ALL = f"""
{_USE_COLS}{_USE_FROM}
 WHERE to_tsvector('english', litkb.norm_search_text(u.statement))
       @@ plainto_tsquery('english', litkb.norm_search_text(%(q)s))
 ORDER BY ts_rank(to_tsvector('english', litkb.norm_search_text(u.statement)),
                  plainto_tsquery('english', litkb.norm_search_text(%(q)s))) DESC, u.version_id
 LIMIT %(n)s
"""

_SEARCH_USES_ANY = f"""
{_USE_COLS}{_USE_FROM}
 WHERE to_tsvector('english', litkb.norm_search_text(u.statement)) @@ litkb.any_term_query(%(q)s)
 ORDER BY ts_rank(to_tsvector('english', litkb.norm_search_text(u.statement)),
                  litkb.any_term_query(%(q)s)) DESC, u.version_id
 LIMIT %(n)s
"""

_SEARCH_USES_TRGM = f"""
{_USE_COLS}{_USE_FROM}
 WHERE litkb.norm_search_text(u.statement) %% litkb.norm_search_text(%(q)s)
 ORDER BY similarity(litkb.norm_search_text(u.statement),
                     litkb.norm_search_text(%(q)s)) DESC, u.version_id
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


def _leg(conn, sql, query, limit, shape, kinds=None, ws=None):
    """One retrieval leg: run its own statement, return [(id, payload)] in its own rank order."""
    args = {"q": query, "n": limit}
    if kinds is not None:
        args["kinds"] = kinds
        args["ws"] = ws          # only the block legs carry visibility.FILE_JOIN
    return [(r[0], shape(r)) for r in conn.execute(sql, args).fetchall()]


#: what `litkb_search` says about the two visibilities, and about the third case — a token file that
#: names a workstream which is no longer open. A result that widened and one that did not must not
#: read the same, or an unattended loop cannot tell "nothing found" from "nothing searched".
_PROPOSALS_MAIN_ONLY = ("this worktree has no open workstream, so only APPROVED material was "
                        "searched")
_PROPOSALS_NOT_OPEN = (
    "this worktree's {file} names a workstream that is no longer open ({state}), so only APPROVED "
    "material was searched — a merged or abandoned workstream's proposals are not searched, and "
    "nothing it proposed and did not get approved is readable here. Remove that file, or open a "
    "new workstream with litkb_ws_open.")
_PROPOSALS_WIDENED = ("blocks of files THIS workstream proposed and no second session has approved "
                      "are searched too, and are invisible to every other workstream. A quote from "
                      "one is recordable, and its use is HELD at promote prepare until the "
                      "admission is approved (decision litkb-web-source-gate).")

#: the tail the SEARCH path adds to a refused token. `BAD_TOKEN_MESSAGE` names nothing about the
#: workstream and must not start; what this adds is about the FILE and about this tool: a stale or
#: copied `.litkb-workstream` is a configuration error, and search FAILS CLOSED on it rather than
#: quietly narrowing to main, which would read as an empty corpus (audit §7.1).
_STALE_TOKEN_TAIL = ("litkb_search is REFUSED in this worktree until {file} is removed — the tree "
                     "then searches approved material only — or the workstream it names is opened "
                     "again with its own token.")


def _caller_workstream(conn):
    """(workstream id or None, the sentence the result carries) — what `visibility.FILE_JOIN`
    binds as `ws`, and why.

    A READ tool that is about to widen what it returns must present the token, for the reason the
    P8 referee's F-1 gives: a workstream id is not a secret (a tracked report prints one), so a
    `.litkb-workstream` naming a real workstream with a forged token would otherwise read the
    proposals of the session that owns it. Here that check is the DIFFERENCE between the two
    visibilities, so it is exactly where it belongs.

    No token file is not an error — it is the other half of the decision. A tree with no open
    workstream searches main, which is what every tree did before this change.

    A file naming a workstream that is no longer OPEN is the third case (audit item 4): the token
    still checks out — `litkb.check_ws_token` reads only `workstream_tokens` — so without
    `visibility.is_open` a merged or abandoned worktree would go on searching proposals that never
    entered main. It narrows to main and SAYS so; it is not refused, because a merged workstream is
    a finished one, not a misconfigured one. The state is read only after the token is presented."""
    from litkb import workstream as _ws

    try:
        ws_id, token = _session()
    except Refusal as e:
        if e.code in ("no-workstream", "bad-workstream-file"):
            return None, _PROPOSALS_MAIN_ONLY
        raise
    tok_file = _worktree() / _ws.TOKEN_FILE
    try:
        # BEGIN guard: proposal visibility presents the workstream token
        _require_token(conn, ws_id, token)
        # END guard: proposal visibility presents the workstream token
    except Refusal as e:
        if e.code != "bad-token":
            raise
        raise Refusal(e.code, e.message + " " + _STALE_TOKEN_TAIL.format(file=tok_file),
                      **e.extra) from None
    # BEGIN guard: proposal visibility requires an OPEN workstream
    if not visibility.is_open(conn, ws_id):
        state = conn.execute("SELECT state FROM litkb.workstreams WHERE id = %s",
                             (ws_id,)).fetchone()
        return None, _PROPOSALS_NOT_OPEN.format(
            file=tok_file, state=state[0] if state else "no such workstream in this database")
    # END guard: proposal visibility requires an OPEN workstream
    return ws_id, _PROPOSALS_WIDENED


def _search(query, limit, scope, kinds=""):
    def block(r):
        return {"block_id": r[0], "work_key": r[1], "page": r[2], "block_type": r[3],
                "section_path": r[4], "text": r[5], "file_id": r[6]}

    def use(r):
        return {"use_version_id": r[0], "work_key": r[1], "gap": r[2], "statement": r[3],
                "kind": r[4], "status": r[5], "feeds": r[6], "state": r[7]}

    want, kinds_note = _kinds(kinds)
    with _conn("reader") as conn:
        ws, proposals = _caller_workstream(conn)
        hits = {"blocks": [], "uses": []}
        if scope in ("all", "blocks"):
            hits["blocks"] = _rrf(
                _leg(conn, _SEARCH_BLOCKS_ALL, query, limit, block, want, ws),
                _leg(conn, _SEARCH_BLOCKS_ANY, query, limit, block, want, ws),
                _leg(conn, _SEARCH_BLOCKS_TRGM, query, limit, block, want, ws))[:limit]
        if scope in ("all", "uses"):
            hits["uses"] = _rrf(
                _leg(conn, _SEARCH_USES_ALL, query, limit, use),
                _leg(conn, _SEARCH_USES_ANY, query, limit, use),
                _leg(conn, _SEARCH_USES_TRGM, query, limit, use))[:limit]
        # The vector leg is WIRED, not live. Setting LITKB_VECTOR_SEARCH=1 must not make the result
        # CLAIM a leg that did not run: the flag is checked against the embeddings table, and what
        # comes back says which of the three states this search was in.
        n_vec = (conn.execute("SELECT count(*) FROM litkb.embeddings").fetchone()[0]
                 if VECTOR_ENABLED else None)
    return _ok(query=query, scope=scope, kinds=kinds_note, proposals=proposals,
               legs=["lexical (all terms)", "lexical (any term)", "trigram"],
               normalisation="the text and the query are both read through litkb.norm_search_text: "
                             "U+FFFD and soft hyphens dropped, line-break hyphenation joined, and a "
                             "C0 control byte inside a word (an extracted ff/fi/fl ligature) is "
                             "searchable under its ligature spellings (migration 0025). The "
                             "blocks still store what the PDF's text layer rendered.",
               vector_leg=("OFF (LITKB_VECTOR_SEARCH is not set): these hits are lexical, so a "
                           "paraphrase sharing no words with the text will NOT be found"
                           if not VECTOR_ENABLED else
                           f"REQUESTED but NOT RUN: the embeddings table holds {n_vec} rows and the "
                           "vector leg lands with P7. These hits are lexical."),
               **hits)


#: what `litkb_work` answers, and why it is a LADDER rather than a boolean. `SKILL.md` step 0 asks
#: "is this work absent, or just not extracted yet?", and before the operational referee this tool
#: could not answer it at all: it named two columns the schema does not have (`container` for
#: `venue`, `v.path` for `v.rel_path`), so every work the database HELD crashed it and only the miss
#: path answered — which is why it read as alive (LITKB_OPERATIONAL_REFEREE_2026-09-16.md §5, R-1).
#: The four states are the three live cases §4 of that referee found plus the miss, and each one has
#: a DIFFERENT next move, which is the whole reason a session must be able to tell them apart.
_WORK_STATES = {
    "absent": "no work with that identifier is admitted in main's view. Which KIND of absent is "
              "`absent_kind` below — never-admitted, in-this-workstream or in-another-workstream — "
              "and the three have three different next moves, so read that before acting: only the "
              "first of them is a work litkb_admit or litkb_hunt should be given.",
    "held": "the work is admitted and NO file is bound to it, so there is nothing for search to "
            "reach and nothing for an extraction run to target. If the PDF is already on disk, "
            "litkb_acquire(key=…, from_file=…) binds it; otherwise litkb_acquire fetches it.",
    "bound-unextracted": "a file is bound but it has no current extraction run, so litkb_search "
                         "cannot see one word of it. The work is HELD, not absent — do not fetch "
                         "it again. Extraction is the P5 bulk path, not an MCP tool.",
    "extracted": "the current extraction run's blocks are searchable: litkb_search will find them, "
                 "and a block_id from that search is what litkb_record_use quotes.",
}


#: `absent` was ONE answer to three different questions, and only one of them is answered by
#: "admit it". A work this very worktree proposed an hour ago and a work nobody has ever heard of
#: came back identically, because the miss rung was a single SELECT against `main_*` — and a
#: session told to admit the first of those gets check 2's duplicate-identifier refusal, which
#: reads as "that is somebody else's work". So the miss carries `absent_kind` from this closed set.
#: The prose of the old `absent` text already NAMED the third case (S3 survey §3.1); what it could
#: not do was say which of the three this call was.
_ABSENT_KINDS = {
    "never-admitted":
        "no identifier like that is admitted in main's view, and this worktree's own workstream "
        "does not hold it either. This is the only one of the three kinds where fetching is the "
        "right move: litkb_admit admits it (title, authors and year with the DOI — a bare DOI is "
        "refused), or litkb_hunt resolves, admits, binds and extracts it in one call.",
    "in-this-workstream":
        "THIS worktree's own workstream already holds it as an unapproved proposal, so main "
        "cannot see it and a main-only ladder calls it absent. Do NOT admit or hunt it again — "
        "admission's check 2 refuses the second one as a duplicate identifier. `ws_state` is the "
        "rung it has reached inside this workstream (held, bound-unextracted or extracted); act "
        "on that rung, and its blocks are reachable from litkb_search in this worktree.",
    "in-another-workstream":
        "another workstream holds this identifier; not visible here until Kam merges its "
        "promotion. Nothing of it is readable from this worktree — not its key, not its files, "
        "not its blocks — and admitting it here would be refused as a duplicate identifier "
        "whatever that workstream's state (check 2 is blind to it). `holder_state` is the "
        "holding workstream's state: `open` → wait for that promotion or ask Kam which branch "
        "carries it; anything else (abandoned, merged without promotion) → the proposal is "
        "stranded and only Kam can promote or retire it.",
}

#: The caller's OWN workstream view, by each selector. Same view and same `status = 'active'`
#: predicate `litkb.hunt.look_up` reads, so the two entry points cannot drift on what "this
#: workstream holds it" means; the ws id is `_caller_workstream`'s, never a caller's claim.
_WS_BY_DOI = ("SELECT wi.work_id::text FROM litkb.ws_identifiers wi "
              " WHERE wi.view_workstream_id = %s AND wi.scheme = 'doi' AND wi.status = 'active' "
              "   AND wi.value_norm = litkb.norm_identifier('doi', %s) LIMIT 1")
_WS_BY_KEY = ("SELECT work_id::text FROM litkb.ws_works "
              " WHERE view_workstream_id = %s AND key = %s LIMIT 1")
_WS_FILES = ("SELECT current_run_id FROM litkb.ws_files "
             " WHERE view_workstream_id = %s AND work_id = %s AND status = 'active'")

#: The third bucket, and the only read here that leaves the caller's view. It answers ONE bit —
#: does some OTHER open workstream hold this identifier — and returns no slug, no key and no file:
#: an unapproved proposal is invisible across workstreams by design (decision litkb-web-source-gate)
#: and this must not become a back door to reading one. `litkb_reader` holds SELECT on both version
#: tables and on `workstreams` (measured 2026-09-21 against the live cluster: `relacl` carries
#: `litkb_reader=r/litkb_owner` on identifier_versions, work_versions, identifiers, works and
#: workstreams, and none of them has row-level security), so no grant is missing and the honest
#: wording is the literal one.
#: The holder's workstream STATE is read, not filtered on. Admission's check 2
#: (0014_referee_p2_fixes.sql, "check 2 identifier lookup") refuses a re-admission on ANY
#: `iv.state = 'proposed'` row, blind to whether the holding workstream is open, merged or
#: abandoned — so a tool that answered `never-admitted` for an abandoned holder would send the
#: caller to an admission that then refuses it as a duplicate (found by the S3 phase-1 audit).
#: The kind therefore matches check 2 exactly, and `holder_state` says whose problem it is.
_OTHER_WS_BY_DOI = ("SELECT w.state FROM litkb.identifier_versions v "
                    "  JOIN litkb.identifiers i ON i.id = v.identifier_id "
                    "  JOIN litkb.workstreams w ON w.id = v.workstream_id "
                    " WHERE i.scheme = 'doi' AND i.value_norm = litkb.norm_identifier('doi', %s) "
                    "   AND v.state = 'proposed' AND v.status = 'active' "
                    "   AND (%s::uuid IS NULL OR v.workstream_id <> %s::uuid) "
                    " ORDER BY (w.state = 'open') DESC LIMIT 1")
_OTHER_WS_BY_KEY = ("SELECT w.state FROM litkb.work_versions v "
                    "  JOIN litkb.works k ON k.id = v.work_id "
                    "  JOIN litkb.workstreams w ON w.id = v.workstream_id "
                    " WHERE k.key = %s AND v.state = 'proposed' "
                    "   AND (%s::uuid IS NULL OR v.workstream_id <> %s::uuid) "
                    " ORDER BY (w.state = 'open') DESC LIMIT 1")


def _absent_kind(conn, doi=None, key=None):
    """-> (kind, extra fields) for a work `main_*` does not hold. One of `_ABSENT_KINDS`.

    The caller's workstream is resolved by `_caller_workstream`, which presents the token and
    refuses a forged one (row W5) and narrows a merged workstream to main. A REFUSAL there is
    caught and read as "no view": this tool has never refused on a token and a read that widens
    nothing must not start, but the caller's own proposals are not shown on a token that did not
    check out either — a forged token then gets `in-another-workstream` at best, which discloses
    the single bit the third bucket discloses anyway and nothing more.
    """
    try:
        ws_id, _note = _caller_workstream(conn)
    except Refusal:
        ws_id = None
    # BEGIN guard: a work the caller's OWN workstream holds is in-this-workstream
    if ws_id:
        row = (conn.execute(_WS_BY_DOI, (ws_id, doi)).fetchone() if doi
               else conn.execute(_WS_BY_KEY, (ws_id, key)).fetchone())
        if row:
            files = conn.execute(_WS_FILES, (ws_id, row[0])).fetchall()
            # the same three-branch rule as the main ladder below and as hunt.look_up: a file with
            # a current run may still hold zero blocks, and "the extractor ran and found nothing"
            # is not "the extractor never ran".
            ws_state = ("held" if not files
                        else "bound-unextracted" if not any(f[0] for f in files)
                        else "extracted")
            return "in-this-workstream", {"ws_state": ws_state, "ws_files": len(files)}
    # END guard: a work the caller's OWN workstream holds is in-this-workstream
    # BEGIN guard: an identifier another workstream holds is in-another-workstream
    other = (conn.execute(_OTHER_WS_BY_DOI, (doi, ws_id, ws_id)).fetchone() if doi
             else conn.execute(_OTHER_WS_BY_KEY, (key, ws_id, ws_id)).fetchone())
    if other:
        return "in-another-workstream", {"holder_state": other[0]}
    # END guard: an identifier another workstream holds is in-another-workstream
    return "never-admitted", {}


def _readability_of(conn, work_id, file_ids):
    """Each current file's readability class (litkb.readability, S4) and every quarantine row that
    names this work or one of its files (litkb.quarantine_payloads, migration 0030) — so a REFUSED file
    is no longer invisible to litkb_work, and a work holding an extracted file beside a residue one reads
    `mixed`, not `extracted`. The four-state ladder above is unchanged; these are keys beside it.

    Never raises: the classifier reads the disk (the per-page probe, the sha256), and a file it cannot
    read must not take the whole work view down with it — the error is returned in its place. A
    database that has not applied 0030 answers `quarantine: null` with the reason."""
    from litkb import quarantine as Q
    from litkb import readability as R

    try:
        per_file, rollup = R.classify_work_files(conn, work_id)
        per_file = {fid: {k: v for k, v in d.items() if k in ("class", "reason", "evidence")}
                    for fid, d in per_file.items()}
    except Exception as e:              # noqa: BLE001 — a disk read never takes the work view down
        per_file, rollup = {}, {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    if not Q.table_present(conn):
        return per_file, rollup, None
    rows = conn.execute(
        "SELECT id::text, rel_path, sha256, bytes, reason, origin, file_id::text, attempt_id::text, recorded_at, "
        "       cleared_at "
        "  FROM litkb.quarantine_payloads WHERE work_id = %s OR file_id = ANY(%s::uuid[]) "
        " ORDER BY recorded_at, id", (work_id, [f for f in file_ids if f])).fetchall()
    # CURRENT rows only: a classifier row the classifier cleared (the file was re-classed extracted)
    # is history, not state (orchestrator ruling on builder-B's question 6)
    return per_file, rollup, [dict(zip(("id", "rel_path", "sha256", "bytes", "reason", "origin", "file_id",
                                        "attempt_id", "recorded_at"), r)) for r in rows if r[9] is None]


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
            kind, extra = _absent_kind(conn, doi=doi, key=key)
            return _ok(found=False, state="absent", absent_kind=kind, doi=doi, key=key,
                       what_next=_ABSENT_KINDS[kind], state_note=_WORK_STATES["absent"],
                       absent_kinds=sorted(_ABSENT_KINDS), **extra)
        key, work_id = row
        # `venue`, not `container`, and main_files' own columns rather than a join to litkb.files:
        # `litkb.main_files` already IS files JOIN file_versions (it carries sha256 and
        # current_run_id), so the join the broken statement made was the view's own, spelled again
        # and spelled wrong. One name for one column, read from the view that defines it.
        w = conn.execute("SELECT type, title, authors, year, venue, publisher, work_id::text "
                         "FROM litkb.main_works WHERE key = %s", (key,)).fetchone()
        ids = conn.execute("SELECT scheme, value_norm, verified_by, active FROM litkb.main_identifiers "
                           "WHERE work_id = %s ORDER BY scheme, value_norm", (work_id,)).fetchall()
        files = conn.execute(
            "SELECT sha256, rel_path, bytes, pages, current_run_id::text, status, file_id::text "
            "FROM litkb.main_files WHERE work_id = %s ORDER BY rel_path", (work_id,)).fetchall()
        # Blocks of the CURRENT run only — the same join litkb_search makes, so this count is the
        # number of blocks a search can actually return for this work, not the number ever stored.
        blocks = conn.execute(
            "SELECT count(*) FROM litkb.blocks b "
            "JOIN litkb.main_files mf ON mf.file_id = b.file_id AND mf.current_run_id = b.run_id "
            "WHERE mf.work_id = %s", (work_id,)).fetchone()[0]
        uses = conn.execute(
            "SELECT u.version_id::text, g.slug, u.statement, u.kind, u.status, u.feeds "
            "FROM litkb.main_uses u LEFT JOIN litkb.gaps g ON g.id = u.gap_id "
            "WHERE u.work_id = %s ORDER BY u.created_at", (work_id,)).fetchall()
        disc = conn.execute(
            "SELECT source, source_row, field, claimed_value, registry_value, ratio "
            "FROM litkb.discrepancies WHERE work_id = %s ORDER BY source, field", (work_id,)).fetchall()
        readable, rollup, quarantine = _readability_of(conn, work_id, [f[6] for f in files])
    # BEGIN guard: the four states of a work
    # A file with no current_run_id is bound and unread; a file with one may still hold zero blocks
    # (a run that produced nothing), and that is reported as extracted with blocks: 0 rather than
    # silently demoted — "the extractor ran and found nothing" and "the extractor never ran" are
    # different problems and only the second one is fixed by running it.
    if not files:
        state = "held"
    elif not any(f[4] for f in files):
        state = "bound-unextracted"
    else:
        state = "extracted"
    # END guard: the four states of a work
    return _ok(found=True, state=state, what_next=_WORK_STATES[state], key=key, work_id=work_id,
               blocks=blocks, use_count=len(uses),
               file_stems=[Path(f[1]).stem for f in files],
               work=dict(zip(("type", "title", "authors", "year", "venue", "publisher", "work_id"), w)),
               identifiers=[dict(zip(("scheme", "value", "verified_by", "active"), r)) for r in ids],
               files=[dict(zip(("sha256", "path", "bytes", "pages", "current_run_id", "status"), r))
                      | {"stem": Path(r[1]).stem, "file_id": r[6],
                         "readability": readable.get(r[6]) or {"class": None, "reason": None,
                                                                "evidence": "not classified"}}
                      for r in files],
               readability=rollup, quarantine=quarantine,
               uses=[dict(zip(("use_version_id", "gap", "statement", "kind", "status", "feeds"), r))
                     for r in uses],
               discrepancies=[dict(zip(("source", "source_row", "field", "claimed", "registry", "ratio"), r))
                              for r in disc])


def _my_uses(limit=50):
    """What THIS workstream has recorded — the read-back the operational test could not make.

    Friction item 2 of `LITKB_OPERATIONAL_TEST_2026-09-16.md`: `litkb_ws_status` returns
    `{"gap": 6, "use": 6}` and nothing else, and `litkb_work` reads `litkb.main_uses`, which holds
    NONE of a session's own uses — they stay `proposed` until Kam merges and `promote commit` runs.
    So the only place a session's own work was legible was the promotion report file it wrote, and
    a session could not check its own quote before offering it.

    Reads `litkb.ws_heads` — the workstream's CURRENT version of each entity, which is exactly what
    `promote prepare` will chain — rather than every version ever written, so what comes back is
    what would be offered. The token is required for the same reason the other read tools require
    it (P8 referee F-1): a workstream id is not a secret."""
    ws_id, token = _session()
    with _conn("reader") as conn:
        _require_token(conn, ws_id, token)
        # BEGIN guard: my_uses reads an OPEN workstream
        _require_open(conn, ws_id)
        # END guard: my_uses reads an OPEN workstream
        rows = conn.execute(
            "SELECT uv.version_id::text, u.id::text, w.key, g.slug, uv.statement, uv.kind, "
            "       uv.status, uv.state, uv.feeds, uv.created_at, "
            "       (SELECT count(*) FROM litkb.use_evidence e "
            "         WHERE e.use_version_id = uv.version_id) AS n_evidence, "
            "       (SELECT count(*) FROM litkb.use_evidence e "
            "         WHERE e.use_version_id = uv.version_id AND e.quote_verified) AS n_verified "
            "  FROM litkb.ws_heads h "
            "  JOIN litkb.use_versions uv ON uv.version_id = h.version_id "
            "  JOIN litkb.uses u ON u.id = h.entity_id "
            "  JOIN litkb.works w ON w.id = u.work_id "
            "  LEFT JOIN litkb.gaps g ON g.id = u.gap_id "
            " WHERE h.workstream_id = %s AND h.entity = 'use' "
            " ORDER BY uv.created_at DESC LIMIT %s", (ws_id, limit)).fetchall()
        gaps = conn.execute("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s "
                            "AND entity = 'gap'", (ws_id,)).fetchone()[0]
    uses = [dict(zip(("use_version_id", "use_id", "work_key", "gap", "statement", "kind", "status",
                      "state", "feeds", "created_at", "evidence_rows", "verified_rows"), r))
            | {"quote_status": _QUOTE_STATUS[bool(r[10]), bool(r[11])]} for r in rows]
    return _ok(workstream_id=str(ws_id), gaps=gaps, uses=uses,
               promotable=sum(1 for u in uses if u["verified_rows"]),
               note="these are this workstream's CURRENT proposed versions — what promote prepare "
                    "would chain. They are invisible to litkb_search's use leg and to litkb_work "
                    "until Kam merges the branch and promote commit runs.")


#: (has any evidence, has a VERIFIED row) -> what promote prepare will do with the chain. The
#: middle case is the one the skill warns about and the one a session could not see: a stored quote
#: the database could not find at its offsets.
_QUOTE_STATUS = {
    (False, False): "NO EVIDENCE — held at promote prepare (no-verified-evidence, migration 0019)",
    (True, False): "UNVERIFIED — the database could not find the quote at the offsets stored; the "
                   "chain is refused at promote prepare until it is corrected",
    (True, True): "verified — the database found the quote in the block at the offsets stored",
}


def _candidates(limit, state=None):
    ws_id, token = _session()
    with _conn("reader") as conn:
        _require_token(conn, ws_id, token)
        # BEGIN guard: candidates reads an OPEN workstream
        _require_open(conn, ws_id)
        # END guard: candidates reads an OPEN workstream
        # `ids`, not `identifiers`: that is the column 0001_core.sql defines, and this statement
        # named the wrong one from the day it was written. It never showed, because the P8 gate's
        # only candidates test is the one that refuses WITHOUT a workstream — with a real
        # workstream the tool raised UndefinedColumn and `_guarded` turned it into a generic
        # `error`, which reads like an empty answer. The referee wrote that _candidates leaks "by
        # construction", from reading; running it is what found this.
        rows = conn.execute(
            "SELECT id::text, state, source, source_detail, title, year, ids, admitted_work_id::text "
            "FROM litkb.candidates WHERE workstream_id = %s "
            "AND (%s::text IS NULL OR state = %s) ORDER BY created_at DESC LIMIT %s",
            (ws_id, state, state, limit)).fetchall()
    return _ok(workstream_id=str(ws_id), candidates=[
        dict(zip(("candidate_id", "state", "source", "source_detail", "title", "year",
                  "identifiers", "admitted_work_id"), r)) for r in rows])


def _ws_status():
    ws_id, token = _session()
    with _conn("reader") as conn:
        _require_token(conn, ws_id, token)
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

#: The cap on a use's `statement`, CHOSEN FROM A MEASUREMENT rather than picked: over the 391 rows
#: of `litkb.use_versions` in live `litkb` on 2026-09-16 the longest statement is 798 characters
#: (p95 653, mean 375). 2000 is comfortably above the longest thing anyone has written, so no
#: existing use becomes retroactively invalid, and far below the length at which a "statement" is
#: really a paragraph of argument that the quote beside it cannot support. Re-derive:
#:   SELECT count(*), max(length(statement)) FROM litkb.use_versions;
STATEMENT_MAX = 2000


def _bad_feeds(conn, feeds):
    """The feeds tokens the database's validator refuses — [] if all pass, None if it has none.

    One round trip over the whole array rather than one per token, and `unnest` so the validator
    sees each token exactly as it will be stored."""
    import psycopg

    tokens = [t for t in (feeds or [])]
    if not tokens:
        return []
    try:
        return [r[0] for r in conn.execute(
            "SELECT t FROM unnest(%s::text[]) AS t WHERE NOT litkb._feeds_token_ok(t)",
            (tokens,)).fetchall()]
    except psycopg.errors.UndefinedFunction:
        return None


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
                                   client=_registry_client(),
                                   # S4.5 decision D25: the caller's file is a proposal (migration 0035)
                                   operator_file=bool(file))
        note = front.operator_file_note(conn, res)
    return _out({"ok": res.get("outcome") == "admitted"} | res | note)


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
        # The database's own clock, not this process's: `at` is written by
        # litkb.record_acquisition_attempt server-side, and a client clock a second fast would
        # select none of the rows it is about to ask for (the S2 freeze lesson).
        t0 = conn.execute("SELECT now()").fetchone()[0]
        out = run.acquire(conn, ws_id, token, work,
                          routes=tuple(r.strip() for r in routes.split(",") if r.strip()),
                          agent=a, session=s, budget=budget, from_file=from_file)
        # BEGIN guard: litkb_acquire returns the per-route attempt detail the run recorded
        # `out["attempts"]` is (route, status) pairs — acquire/run.py writes the per-attempt
        # `detail` to litkb.acquisition_attempts and never returns it, so "acquisition.attempts
        # names what each route answered" was route and status and nothing else. These are that
        # work's own rows, in this workstream, written during this call; `_out`'s two redactors
        # run over them exactly as they run over everything else this server returns.
        rows = conn.execute(
            "SELECT route, status, detail, at FROM litkb.acquisition_attempts "
            " WHERE work_id = %s AND at >= %s ORDER BY at", (work["work_id"], t0)).fetchall()
        # END guard: litkb_acquire returns the per-route attempt detail the run recorded
    # `out` is returned WHOLE: the comprehension that used to sit here stripped `detail`, which
    # run.acquire sets on exactly the two outcomes that have one (ok, duplicate-held), so the
    # sha256, the byte count, the binding verdict, the source URL and the filed path — the whole
    # landing record — were dropped on the two calls that landed a file (S3 survey §3.2).
    return _out({"ok": out.get("outcome") in ("ok", "already-held"), "key": work["key"],
                 "archive_downloads_used": budget.used,
                 "attempts_detail": [dict(zip(("route", "status", "detail", "at"), r))
                                     for r in rows]} | out)


def _record_use(statement, kind, quote, block_id, gap, work_key=None, doi=None, gap_question=None,
                feeds=None, stance="supports", page=None, rationale=None,
                char_start=None, char_end=None, agent=None, session=None, hunt_request_id=None):
    """A use and its evidence, in one call. The QUOTE is located in the block's own text here, so
    the offsets the database checks are the ones the quote actually occupies — and a quote that is
    not in that block is refused BEFORE anything is written (`quote-not-in-block`).

    Located by `use.locate_in_text`, which compares CANONICAL LINE ENDINGS: a `\\r\\n` in the
    stored block and a `\\n` in the caller's quote are the same break, and nothing else is
    normalised. That is not a convenience — it is what makes a multi-line quote recordable at all
    from an LLM writing JSON, and until 2026-09-20 it was missing here while the grader already
    had it, so the proving run's review quoted fragments (see `use.locate_in_text`).

    `quote_verified` itself is never this server's word: the database recomputes it from the block
    text at [char_start, char_end) in a trigger the writer role cannot name (migration 0007/0010,
    P1 kill M3; 0026 made its comparison canonical too, so the two ends agree). What comes back
    below is what the database stored.

    char_start/char_end are accepted only to let a test record a DELIBERATELY unverifiable quote —
    the P8 kill needs one to reach `promote prepare` and be refused there.

    `hunt_request_id` (migration 0023): the drop-off this use circles back to, if any — the
    "closed loop" step (WORKPLAN.md "Next phase"). Set once, at creation; `_create_identity`
    refuses one belonging to another workstream, and it is never accepted on an EXISTING use
    (identity is immutable)."""
    from psycopg.types.json import Jsonb

    from litkb import use as _use
    from litkb.textnorm import norm_label

    ws_id, token = _session()
    a, s = _labels(agent, session)
    kinds = ("method", "theorem", "parameter", "empirical evidence", "negative result",
             "context", "contradiction")
    if kind not in kinds:
        # The set is NAMED in the refusal (S2, 2026-09-21): the first live record_use of the
        # session was refused with "one of the seven use kinds" and had to go looking for the
        # seven, while `bad-feeds` beside it lists its vocabulary. A refusal that names the set
        # costs one line; one that does not costs a search.
        return _refuse("bad-kind", f"kind must be one of the seven use kinds "
                                   f"({', '.join(kinds)}), got {kind!r}")
    # BEGIN guard: the statement is a statement
    # R-5/R-6 of the operational referee: the statement is what a reader of the promotion report
    # sees, and it was completely ungated here. The database's own CHECK is `statement <> ''`, which
    # a single space satisfies — so a use could carry a blank claim and a verified quote and promote
    # clean. `norm_label` (the ONE invisible-character normaliser, migration 0014 D7's twin) is what
    # decides "blank": a statement of zero-width joiners is blank in exactly the way a label of them
    # is. The text STORED is what the caller wrote; only the emptiness test is normalised.
    if not norm_label(statement or "").strip():
        return _refuse("bad-statement",
                       "statement is empty. A use records what the work SUPPLIES to the question, "
                       "in your words — it is the sentence a reader of the promotion report sees "
                       "beside the quote. (A statement of invisible characters is empty too.)")
    if len(statement) > STATEMENT_MAX:
        return _refuse("bad-statement",
                       f"statement is {len(statement)} characters; the cap is {STATEMENT_MAX}. A "
                       "use states what this work supplies to one question. If it needs more than "
                       "that, it is more than one use — record them separately, each with its own "
                       "quote.", length=len(statement), cap=STATEMENT_MAX)
    # END guard: the statement is a statement
    with _conn("writer") as conn:
        # BEGIN guard: the quote path presents the workstream token before it widens
        # The P8 referee's F-1 rule at this function, which did not have it. Until 2026-09-20 the
        # block lookup below joined `main_files`, so an unverified workstream id bought nothing and
        # presenting the token could be left to the DATABASE on the write. The web-source decision
        # changed that: the lookup now binds this id into `visibility.FILE_JOIN`, and a workstream
        # id is not a secret — a tracked report prints one. So a `.litkb-workstream` naming a real
        # workstream with a wrong token reached that workstream's unapproved proposals here. The
        # write was still refused, but the refusals BUILT FROM THE BLOCK leak: `quote-not-in-block`
        # returns `work_key`, and `stale-run` and `work-mismatch` are facts about a source no second
        # session has approved. Refused here, before the block is resolved.
        _require_token(conn, ws_id, token)
        # END guard: the quote path presents the workstream token before it widens
        # BEGIN guard: a use is recorded into an OPEN workstream
        # Before the block lookup, for the same reason: that lookup is the half this decision
        # WIDENED, and a merged or abandoned workstream may not read its unapproved proposals back
        # (audit item 4). The database refuses the write itself (`_write_version`, 0007:41-44) with
        # an InvalidParameterValue that `_guarded` turns into an opaque `error`; this makes the
        # refusal legible, and makes it happen before a row is read or a gap is proposed. It runs
        # AFTER the token check above, so the state is told to nobody who has not presented it.
        _require_open(conn, ws_id)
        # END guard: a use is recorded into an OPEN workstream
        # BEGIN guard: every feeds token is in the convention's vocabulary
        # Shape-checked by the DATABASE's own validator, not by a regex here: `litkb._feeds_token_ok`
        # (migration 0021) is the one definition of the convention's seven forms, and a second copy
        # in Python is the twin-drift that 0018-vs-0020 already cost a migration to undo. Checked
        # BEFORE the gap proposal, which is the first write this function makes, so a refused call
        # leaves nothing behind. What this does NOT check is whether the section, gate or row a
        # token names EXISTS — 0018's own comment says so, and the operational referee's R-5 is an
        # instance: `gap row 6` passed while pointing at the wrong row.
        bad = _bad_feeds(conn, feeds)
        if bad is None:
            return _refuse("no-feeds-check",
                           "this database has no litkb._feeds_token_ok: migration 0020/0021 has "
                           "not been applied, so a feeds token cannot be validated and none is "
                           "stored unvalidated.")
        if bad:
            return _refuse("bad-feeds",
                           f"these feeds tokens are not in the convention's vocabulary: {bad}. The "
                           "seven doc-qualified forms are in Scripts/docs/LITERATURE_CONVENTION.md "
                           "— each names a document AND a place in it (framework §N[.N], "
                           "narrative §N, gated-plan gate N, review §N[.N…], gap row N, "
                           "decision <slug>, report <FILE>.md#§<loc>). A bare §N is not one.",
                           bad_feeds=bad)
        # END guard: every feeds token is in the convention's vocabulary
        # visibility.FILE_JOIN, not main_files: a quote may come from a file THIS workstream
        # proposed (decisions.yaml litkb-web-source-gate). The use is written and its quote is
        # verified exactly as any other; what the proposal cannot do is reach main, which
        # `promote prepare` holds on the work's admission chain.
        blk = conn.execute(
            "SELECT b.text, b.page_no, b.run_id::text, f.current_run_id::text, w.key, fv.work_id::text "
            "FROM litkb.blocks b JOIN litkb.files f ON f.id = b.file_id "
            + visibility.FILE_JOIN
            + " WHERE b.id = %(block_id)s", {"block_id": block_id, "ws": ws_id}).fetchone()
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
            # BEGIN guard: the quote is located by the ONE locator, on canonical line endings
            # `use.locate_in_text`, not a `find` of its own: this function and `use.locate_quote`
            # are the MCP and the CLI halves of "where does this quote live", and until 2026-09-20
            # each had its own — both comparing raw bytes, which is the defect. 48.9 % of
            # current-run blocks store `\r\n`, an LLM writer emits `\n`, so every quote crossing a
            # stored line break was refused here as "not in that block", and the proving run's
            # writer answered by quoting single lines (33 characters at the longest inside a real
            # verified span). The offsets this returns are the STORED text's own, so the verify
            # trigger cuts the same characters and every existing row keeps its meaning.
            span = _use.locate_in_text(text, quote)
            if span is None:
                return _refuse("quote-not-in-block",
                               "the quote is not in that block's text. A use is evidenced by a quote "
                               "the database can find at the offsets recorded — paraphrase in the "
                               "statement, never in the quote. (A line break may be written either "
                               "way: only its ENCODING is normalised, never a character, and never "
                               "the number or the position of the breaks.)",
                               block_id=block_id, work_key=blk_key)
            char_start, char_end = span
            # END guard: the quote is located by the ONE locator, on canonical line endings
            # BEGIN guard: a quote located by canonical newlines needs the trigger that verifies them
            # The pre-0026 trap, and why this is a refusal rather than a note in the result: with
            # the locator above and the OLD trigger, a quote differing from the stored span only in
            # its line endings is LOCATED and then written with `quote_verified = false` — an
            # unverified row where the old code refused cleanly, which is worse than the defect
            # being fixed. Asked of the database, like `_bad_feeds` above, because a client can be
            # newer than the schema it is pointed at.
            if text[char_start:char_end] != quote and not _use.newline_canon_available(conn):
                return _refuse("no-newline-canon",
                               "this database has no litkb.canonical_newlines: migration 0026 has "
                               "not been applied, so the trigger that sets quote_verified still "
                               "compares raw bytes and would store this quote unverified. Apply "
                               "the migrations, or send the quote with the block's own line "
                               "endings.", block_id=block_id)
            # END guard: a quote located by canonical newlines needs the trigger that verifies them
        # BEGIN guard: evidence comes from the work the use is about
        # The strongest single property here and, until now, the one with no mutation row (P8
        # referee §6.1): the use's work is DERIVED from the block and never taken from the caller,
        # so there is no path by which a quote from B evidences a claim about A. What these two
        # checks add is the refusal — a caller who names a work is told the block belongs to
        # another one, instead of silently recording the use against the block's work.
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
        # END guard: evidence comes from the work the use is about
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
            (Jsonb({"work_id": work_id, "gap_id": gap_id[0], "hunt_request_id": hunt_request_id}),
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

    The CLI writes the promotion report as part of preparing (`promote.write_report`, F-5): with no
    `report_path` it lands at `_derived/promotions/<promotion_id>.md` in the worktree, and the path
    comes back as `report_written`. The chains it prepared and the chains it HELD, with the
    database's own reason for each, are in the result as `prepared` and `held`.

    Not an import: `promote_prepare` may be executed only by `litkb_promoter` (design §4.7), and
    this server must never hold that credential — §9 puts prepare outside the MCP surface for
    exactly that reason. Running the CLI keeps the passfile in a process that exits, and keeps this
    server's own logins to reader and writer. `promote commit` has no tool at all: it runs after
    Kam's merge, from a session that can see the merge commit."""
    ws_id, token = _session()
    # The offer tool needs the SAME check the read tools now make, and needs it more: `promote
    # prepare` takes no token — `litkb.promote_prepare(ws, branch_head, report_path)` is authorised
    # by the PROMOTER credential, not by the workstream's — so without this a crafted
    # `.litkb-workstream` naming a published workstream id would prepare ANOTHER workstream's
    # proposals, write its chain report into this worktree, and (promotions_one_prepared_per_ws)
    # block its owner's own prepare. The referee tested the two read tools and the write path; this
    # one was neither. Refused BEFORE the subprocess runs, so nothing is written at all.
    with _conn("reader") as conn:
        _require_token(conn, ws_id, token)
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


def _hunt(ref, title=None, author=None, year=None, key=None, source_note=None, extract=True,
          agent=None, session=None, spend=True, hunt_request_id=None, ref_scheme=None):
    """`litkb hunt`, run as a SUBPROCESS of the CLI — for the reason `_propose_promotion` runs one.

    A hunt INGESTS, and ingesting is the `litkb_ingest` login (design §4.7, §9): the writer holds
    no INSERT on any extraction table, which is what stops an agent installing a run of its own
    and forging a block whose text matches a quote it wants to cite. Importing `litkb.hunt` here
    would put that credential inside a long-lived server for the length of every conversation;
    running the CLI keeps it in a process that exits when the document is in.

    The refusal for a missing token is made HERE, before the subprocess: `_session()` is also what
    arms the redactor, and a hunt that ran and then failed to find a workstream would have spent a
    download and a GPU conversion to say so.

    The LABEL check is deliberately NOT repeated here. `litkb.hunt` normalises and refuses them
    itself, before it opens a store or touches the network, and it has to — the CLI is an entry
    point of its own. A second copy in this wrapper would be a second place the rule is written,
    and the harness would have to test the copy rather than the guard (`_labels` is on the
    per-call-site rule for exactly that reason).

    SPEND is likewise threaded, not re-decided: `spend=True` (the default, SPEND RULE 2026-09-16,
    decisions.yaml litkb-p0-foundation) is the CLI's own default and needs no flag; `spend=False`
    becomes `--no-spend`, so an MCP caller gets the same distinct `held-no-spend` outcome the CLI
    does rather than a second copy of the stop.

    `hunt_request_id` (migration 0023) becomes `--hunt-request <id>`: the CLI does the actual
    linking (litkb.hunt._link_hunt_request), inside the same subprocess that already holds the
    writer connection for the admission.

    `ref_scheme` (S1, 2026-09-20) becomes `--ref-scheme <s>` and is likewise THREADED, not
    re-decided: `litkb.hunt.validate_ref` owns the vocabulary check, the shape check and the
    precedence against a hunt_request's own scheme, and a copy of any of the three here would be
    a second place the rule is written (the reason the LABEL check is not repeated in this
    wrapper either)."""
    ws_id, _token = _session()
    wt = _worktree()
    cmd = [sys.executable, "-m", "litkb", "--db", _db(), "--dir", str(wt)]
    if agent:
        cmd += ["--agent", agent]
    if session:
        cmd += ["--session", session]
    cmd += ["hunt", ref]
    for flag, value in (("--title", title), ("--author", author), ("--key", key),
                        ("--source-note", source_note), ("--hunt-request", hunt_request_id),
                        ("--ref-scheme", ref_scheme)):
        if value:
            cmd += [flag, str(value)]
    if year:
        cmd += ["--year", str(int(year))]
    if not extract:
        cmd.append("--no-extract")
    # BEGIN guard: the MCP tool's spend=False threads through as --no-spend; the default spends
    if not spend:
        cmd.append("--no-spend")
    # END guard: the MCP tool's spend=False threads through as --no-spend; the default spends
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(SCRIPTS / "pipeline"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
        LITKB_WORKTREE=str(wt))
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(wt), env=env)
    try:
        payload = json.loads(r.stdout)
    except ValueError:
        payload = {"stdout": r.stdout[-4000:]}
    return _out({"ok": r.returncode == 0, "workstream_id": str(ws_id),
                 "returncode": r.returncode, "stderr": r.stderr[-4000:]} | payload)


def _hunt_request_add(ref, ref_scheme, expected_claim, why_relevant, abstract_passage=None,
                      claimed_title=None, claimed_authors=None, claimed_year=None, gap=None,
                      agent=None, session=None):
    """The review agent's drop-off (migration 0023): identifiers, the claim it expects the paper
    to support, why it is relevant, and the abstract passage it reasoned from — written BEFORE the
    full text exists, so a later verified use can be checked against the expectation that
    motivated the hunt. `ref_scheme` is the database's own vocabulary
    (`litkb.hunt_request.REF_SCHEMES`, held equal to the table's CHECK by
    qc/test_litkb_hunt_request.py). It is checked HERE, before the write, so an unrecognised one
    comes back as the named `unknown-ref-scheme` refusal carrying the vocabulary — until
    2026-09-20 it reached the table's CHECK and surfaced as the ordinary `error` shape with a raw
    PL/pgSQL sentence, which is exactly what an unattended scout cannot act on. The CHECK is
    still what ENFORCES it; this is what a caller READS.

    `gap`, if given, is the gap SLUG this drop-off is meant to help answer; it is stored as
    `gap_id` and must already exist (litkb_record_use opens one on demand — this tool does not,
    because a drop-off is not itself a claim about a gap being answered)."""
    from litkb import hunt_request

    ws_id, token = _session()
    a, s = _labels(agent, session)
    # BEGIN guard: the MCP drop-off's ref_scheme is in the vocabulary before the write is attempted
    if ref_scheme not in hunt_request.REF_SCHEMES:
        return _refuse("unknown-ref-scheme",
                       f"{ref_scheme!r} is not one of litkb's reference schemes: "
                       f"{', '.join(hunt_request.REF_SCHEMES)}. A find with no identifier at all "
                       f"is 'title' (and the drop-off should carry claimed_title, "
                       f"claimed_authors and claimed_year so a hunt can resolve it).")
    # END guard: the MCP drop-off's ref_scheme is in the vocabulary before the write is attempted
    gap_id = None
    if gap:
        with _conn("reader") as conn:
            row = conn.execute("SELECT id::text FROM litkb.gaps WHERE slug = %s", (gap,)).fetchone()
        if not row:
            return _refuse("unknown-gap", f"no gap {gap!r}. Open one first (litkb_record_use with "
                                          "gap_question does this on demand; this tool does not).")
        gap_id = row[0]
    with _conn("writer") as conn:
        # BEGIN guard: the drop-off presents the workstream token
        # Above the state check, so that check tells a caller who cannot present the token nothing
        # about the workstream — the same order as `_record_use` and `_brief`.
        _require_token(conn, ws_id, token)
        # END guard: the drop-off presents the workstream token
        # BEGIN guard: a drop-off is recorded into an OPEN workstream
        # `litkb.record_hunt_request` refuses a non-open workstream with a PL/pgSQL RAISE, which
        # `_guarded` turns into `refused: error` carrying the database's raw sentence — the shape
        # the operational referee's R-1 is about, and the one an unattended loop cannot act on.
        # The RAISE stays where it is: it is the enforcement. This is the refusal a caller reads.
        _require_open(conn, ws_id)
        # END guard: a drop-off is recorded into an OPEN workstream
        hr_id = hunt_request.record(conn, ws_id, token, ref=ref, ref_scheme=ref_scheme,
                                    expected_claim=expected_claim, why_relevant=why_relevant,
                                    abstract_passage=abstract_passage or None,
                                    claimed_title=claimed_title or None,
                                    claimed_authors=claimed_authors or None,
                                    claimed_year=claimed_year or None, gap_id=gap_id,
                                    agent=a, session=s)
    return _out({"ok": True, "hunt_request_id": str(hr_id), "ref": ref, "resolution_state": "open",
                 "what_next": "litkb_hunt(ref=..., hunt_request=hunt_request_id) links the work "
                             "this resolves to; a later litkb_record_use(hunt_request=...) is what "
                             "can ever move this past 'open'/'unconfirmed'."})


def _brief(limit=200):
    """This workstream's per-study BRIEF (Task B, delta 2026-09-18; `litkb/brief.py`): every
    hunt_request it holds, marked EXPECTED, and every promotable quote it can see, marked
    VERIFIED — never a filtered view of either (litkb/brief.py's own two gates). Read-only; this
    tool writes no file — `litkb brief` (the CLI) writes the same content as markdown under
    `_derived/briefs/` for a session that wants it on disk."""
    from litkb import brief as _br

    ws_id, token = _session()
    with _conn("reader") as conn:
        _require_token(conn, ws_id, token)
        # BEGIN guard: the brief is a brief of an OPEN workstream
        _require_open(conn, ws_id)
        # END guard: the brief is a brief of an OPEN workstream
        expected, verified = _br.build(conn, ws_id)
    return _ok(workstream_id=str(ws_id), expected=expected[:limit], verified=verified[:limit],
               n_expected=len(expected), n_verified=len(verified))


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
            # The one refusal the design most wants stated well used to arrive as an opaque
            # `error` carrying a raw psycopg message and a `CONTEXT: PL/pgSQL function
            # _require_ws_token(uuid,text) line 1` (P8 referee §3.2). It is matched on the
            # database's own sentence, not on SQLSTATE alone: 42501 is also what a missing GRANT
            # raises, and calling that a bad token would send a reader hunting the wrong thing.
            if "workstream token refused" in str(e):
                return _refuse("bad-token", BAD_TOKEN_MESSAGE, tool=fn.__name__)
            return _refuse("error", f"{type(e).__name__}: {e}", tool=fn.__name__)
    call.__name__ = fn.__name__
    return call


def build_server():
    """The MCPServer with the twelve tools bound. `mcp` is imported HERE, never at module top."""
    from mcp.server.mcpserver import MCPServer

    srv = MCPServer(name=SERVER_NAME, version=VERSION, instructions=(
        "The Edmonds project's literature knowledge base. Search it BEFORE any web or paper-search "
        "route: a work the project relies on is admitted, acquired and cited here. Writes need an "
        "open workstream in this worktree (litkb_ws_open); the token is never passed to a tool. "
        "promote commit and approve are deliberately absent — they belong to Kam's merge and to a "
        "second session."))

    @srv.tool(name="litkb_search", description=(
        "Hybrid lexical search over extracted blocks and recorded uses: three legs — all terms, any "
        "term, trigram — fused by reciprocal rank. Returns work key, page, section path and "
        "block_id (the block_id is what litkb_record_use quotes from). Running heads, page "
        "numbers, footers and bibliography entries are NOT searched by default — they are the same "
        "string on every page and crowd out the passage that answers the question; pass "
        "kinds=\"all\" or a comma-separated list of block types (e.g. kinds=\"reference\") to "
        "include them. The vector leg is off until P7, so a paraphrase sharing no words with the "
        "text will not be found."))
    def litkb_search(query: str, limit: int = 10, scope: str = "all", kinds: str = "") -> str:
        return _guarded(_search)(query=query, limit=min(max(int(limit), 1), 50), scope=scope,
                                 kinds=kinds)

    @srv.tool(name="litkb_work", description=(
        "One work by DOI or key, and WHICH OF FOUR STATES it is in: absent (no such work), held "
        "(admitted, no file bound), bound-unextracted (a PDF is bound but never extracted, so "
        "search cannot see it), or extracted (N blocks searchable). Also its registry-confirmed "
        "fields, identifiers, file stems, recorded uses and any registry discrepancies. Ask this "
        "before concluding a work is absent: 'litkb_search found nothing' means three "
        "different things and only this tool tells them apart. `absent` is itself three answers, "
        "and `absent_kind` says which: never-admitted (fetch it), in-this-workstream (this "
        "worktree's own unapproved proposal already holds it — `ws_state` is the rung it reached; "
        "admitting it again is refused as a duplicate), in-another-workstream (another workstream "
        "holds this identifier; not visible here until Kam merges its promotion)."))
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

    @srv.tool(name="litkb_my_uses", description=(
        "The uses THIS workstream has recorded, in full: work key, gap, statement, kind, feeds, and "
        "whether the database verified each quote. litkb_work cannot show them — they stay proposed "
        "until Kam merges — so this is the only way to read back your own work before offering it."))
    def litkb_my_uses(limit: int = 50) -> str:
        return _guarded(_my_uses)(limit=min(max(int(limit), 1), 200))

    @srv.tool(name="litkb_admit", description=(
        "Admit a work by DOI or arXiv id, optionally binding a PDF already on disk. Identity is the "
        "registry record plus the verified file; the five admission checks run in one transaction. "
        "A file you hand in lands as a PROPOSAL a second session approves (never main's version). "
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
        "database; an unverified quote is stored but its chain is refused at promote prepare. THE "
        "QUOTE MAY SPAN LINES: write the breaks as plain \\n — about half of all stored blocks "
        "carry \\r\\n and only the ENCODING of a break is normalised, never a character, never the "
        "number or the position of the breaks. So quote the whole sentence that carries the claim, "
        "not the fragment that fits on one stored line. Pass "
        "hunt_request to link this use back to a drop-off litkb_hunt_request_add recorded — that is "
        "how a hunt_request's resolution_state can ever become confirmed or contradicted."))
    def litkb_record_use(statement: str, kind: str, quote: str, block_id: str, gap: str,
                         gap_question: str = "", work_key: str = "", doi: str = "",
                         feeds: str = "", stance: str = "supports", page: int = 0,
                         rationale: str = "", char_start: int = -1, char_end: int = -1,
                         hunt_request: str = "") -> str:
        return _guarded(_record_use)(
            statement=statement, kind=kind, quote=quote, block_id=block_id, gap=gap,
            gap_question=gap_question or None, work_key=work_key or None, doi=doi or None,
            feeds=[f.strip() for f in feeds.split(";") if f.strip()], stance=stance,
            page=page or None, rationale=rationale or None,
            char_start=None if char_start < 0 else char_start,
            char_end=None if char_end < 0 else char_end,
            hunt_request_id=hunt_request or None)

    @srv.tool(name="litkb_propose_promotion", description=(
        "Offer this workstream's proposed versions to main: group them into chains, re-run the "
        "checks, and write the promotion report (`_derived/promotions/<id>.md` by default) into the "
        "worktree for Kam to review inside the merge — commit it with the branch. The result lists "
        "the chains prepared and the chains HELD with the reason for each. PREPARE ONLY — "
        "committing the promotion happens after Kam merges, and is not a tool."))
    def litkb_propose_promotion(report_path: str = "", repo: str = "") -> str:
        return _guarded(_propose_promotion)(report_path=report_path or None, repo=repo or None)

    @srv.tool(name="litkb_hunt_request_add", description=(
        "Drop off a paper worth hunting, BEFORE the full text exists: the reference as given, the "
        "CLAIM you expect it to support, WHY it is relevant, and the abstract passage you reasoned "
        "from. This is your unverified prior, recorded so a later verified use can be checked "
        "against it — it is never itself evidence and never searched by litkb_search. Returns a "
        "hunt_request_id: pass it to litkb_hunt to link the work this resolves to, and to a later "
        "litkb_record_use to let this request's resolution move past open/unconfirmed."))
    def litkb_hunt_request_add(ref: str, ref_scheme: str, expected_claim: str, why_relevant: str,
                               abstract_passage: str = "", claimed_title: str = "",
                               claimed_authors: str = "", claimed_year: int = 0,
                               gap: str = "") -> str:
        return _guarded(_hunt_request_add)(
            ref=ref, ref_scheme=ref_scheme, expected_claim=expected_claim,
            why_relevant=why_relevant, abstract_passage=abstract_passage or None,
            claimed_title=claimed_title or None, claimed_authors=claimed_authors or None,
            claimed_year=claimed_year or None, gap=gap or None)

    @srv.tool(name="litkb_brief", description=(
        "This workstream's per-study BRIEF: every hunt_request it holds, marked EXPECTED (an "
        "agent's unverified prior — expected claim, why it's relevant, the abstract passage it "
        "came from, and its resolution state open/unconfirmed/confirmed/contradicted, never "
        "dropped even when nothing has confirmed it yet), and every promotable quote it can see, "
        "marked VERIFIED (work key, page, block id, the claim it supports, its kind and "
        "stance). The CLI (`litkb brief`) writes the same content as markdown under "
        "_derived/briefs/ (untracked); this tool returns it structured and writes nothing."))
    def litkb_brief(limit: int = 200) -> str:
        return _guarded(_brief)(limit=min(max(int(limit), 1), 1000))

    @srv.tool(name="litkb_hunt", description=(
        "ONE call from a reference to searchable text: resolve a DOI or a document URL, admit it, "
        "bind the PDF, extract it (GROBID + Docling, reconciled) and ingest it. Answers from the "
        "database first — a reference already extracted comes back with its run and nothing is "
        "fetched or written. Returns the work's state (absent / held / bound-unextracted / "
        "extracted), blocks by kind, coverage, the first headings, per-stage seconds and every "
        "refusal with its reason. A URL source is a manual PROPOSAL: litkb_search reaches its "
        "blocks from THIS workstream and from no other, and any use built on them is HELD at "
        "promote prepare until a SECOND session approves the admission. Pass title "
        "and author for a URL — there is no registry to ask, and a PDF's own metadata usually "
        "names the file rather than the work. A reference that resolves to `held` (admitted, no "
        "PDF) SPENDS by default: open access, then the archive, then Sci-Hub. Pass spend=False "
        "to stop at `held` instead — a distinct, deliberate outcome, not an error. Pass "
        "hunt_request (an id from litkb_hunt_request_add) to link the drop-off to whatever work "
        "this reference resolves to — cached or fresh, any rung of the ladder. "
        "ref_scheme says what the reference IS (doi | arxiv | url | title are the ones a hunt "
        "can follow; the rest of litkb's vocabulary is recordable as a drop-off and refused here "
        "as unsupported-ref-scheme). Omitted, the scheme is inferred from the shape and a shape "
        "nothing matches is refused malformed-ref — never treated as a DOI. ref_scheme='title' "
        "resolves title + author + year through the registries and needs BOTH author and year. "
        "With hunt_request, that drop-off's own scheme wins and a disagreeing ref_scheme is "
        "refused ref-scheme-mismatch."))
    def litkb_hunt(ref: str, title: str = "", author: str = "", year: int = 0, key: str = "",
                   source_note: str = "", extract: bool = True, spend: bool = True,
                   hunt_request: str = "", ref_scheme: str = "") -> str:
        return _guarded(_hunt)(ref=ref, title=title or None, author=author or None,
                               year=year or None, key=key or None,
                               source_note=source_note or None, extract=bool(extract),
                               spend=bool(spend), hunt_request_id=hunt_request or None,
                               ref_scheme=ref_scheme or None)

    return srv


def main(argv=None):
    srv = build_server()
    srv.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())

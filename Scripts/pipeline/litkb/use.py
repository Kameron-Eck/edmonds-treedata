"""Step 4 of the hunt protocol — recording a use — as something the tool can actually do.

    ok = feeds_refused(conn, ["framework §13.1", "report X.md#§5"])       # [] when every token is valid
    uid, vid = write_use(conn, ws, token, work_id=…, statement=…, kind="context", feeds=[…], …)
    ev = attach_quote(conn, ws, token, vid, work_id=…, quote="…", page=7, stance="supports")

`Scripts/docs/LITERATURE_CONVENTION.md` documents five steps and `litkb --help` listed commands for
three of them. Measured on the first session that tried to follow the convention end to end
(`Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8.1): steps 4 and 5 had no CLI, so the reviewer wrote
15 uses through `psycopg` by copying `migrate_legacy/run.py::record_use` — "the procedure the
convention documents cannot be followed with the tool the convention names", and a session that had
not gone reading the SQL would have invented a different shape or skipped the step. This module is
step 4; step 5 is `promote prepare`, which is a different credential and belongs to the CLI.

THE THREE THINGS IT DOES THAT A HAND-WRITTEN INSERT DID NOT:

* **The feeds tokens are checked BEFORE the write**, against the database's own
  `litkb._feeds_token_ok` — the same regex `_ws_chains` uses at prepare, so there is one home for the
  rule and no second copy here to drift from it. §8.6 of that review: the validator accepted three of
  the seven forms the convention documents, so a use that fed a REPORT could carry no valid token at
  all, and all 15 uses were written with an EMPTY feeds array — "the KB records that these works were
  used and does not record what they were used for". Migration 0020 widened the validator to the
  convention's seven; this refuses a bad token at the command instead of holding the chain at prepare,
  where the reviewer would have found out much later.
* **A quote is anchored in an extracted block, or it is not written.** §8.3: `use_evidence` needs a
  `block_id` and a `run_id`, there was no path from "I just acquired this PDF" to "this quote is
  verified against its block", and so the quotes went into `rationale` as free text, which the
  database does not check. Here the quote is LOCATED — the work's active file, its current extraction
  run, the blocks of the page named — and `char_start`/`char_end` come from that block's own text. If
  no block carries the quote, the command REFUSES. It does not fall back to free text, because a
  quote in `rationale` is exactly the unverified record §8.3 is about.
* **`quote_verified` is the database's**. `add_evidence` inserts, the 0007 trigger re-reads the block
  at `[char_start, char_end)` and sets the column, and no role but the owner may write it (0006). What
  this module reports is what the database computed, never what it hoped.

A use with NO quote is still writable, and is reported as carrying no evidence. Whether prepare
should hold such a use is an open question with two coherent answers and it is Kam's
(`Reports/LITKB_P8_REFEREE_2026-09-15.md` §4.2); nothing here decides it.
"""


def feeds_refused(conn, tokens):
    """The tokens `litkb._feeds_token_ok` does not accept. [] means prepare will not hold on feeds.

    Asked of the DATABASE, never re-implemented here: the validator is one regex in one migration and
    a Python copy of it would be the second home that goes stale (CLAUDE.md 3.3). It is also the
    live server's answer, so a client running against a database that has not had 0020 applied learns
    that from the refusal instead of from a passing local check.
    """
    toks = [t for t in tokens or [] if t]
    if not toks:
        return []
    rows = conn.execute("SELECT t FROM unnest(%s::text[]) t WHERE NOT litkb._feeds_token_ok(t)", (toks,)).fetchall()
    return [r[0] for r in rows]


def work_by(conn, *, key=None, doi=None, work_id=None):
    """Main's view of an admitted work -> {work_id, key, title, year} or None."""
    if work_id is None and key:
        r = conn.execute("SELECT work_id FROM litkb.main_works WHERE key = %s", (key,)).fetchone()
        work_id = r[0] if r else None
    if work_id is None and doi:
        r = conn.execute("SELECT work_id FROM litkb.main_identifiers WHERE scheme = 'doi' AND active "
                         "AND value_norm = litkb.norm_identifier('doi', %s)", (doi,)).fetchone()
        work_id = r[0] if r else None
    if work_id is None:
        return None
    r = conn.execute("SELECT work_id, key, title, year FROM litkb.main_works WHERE work_id = %s",
                     (work_id,)).fetchone()
    return {"work_id": r[0], "key": r[1], "title": r[2], "year": r[3]} if r else None


def locate_quote(conn, work_id, quote, page=None, ws=None):
    """Where the quote sits in the work's extracted text -> list of candidate anchors.

    The search is over the CURRENT run of the work's active files only (`files.current_run_id`), for
    the same reason `use_evidence_status.promotable` compares against it: evidence recorded against a
    superseded run is evidence about text that is no longer the file's answer.

    Matching is exact on the block text. A quote that is right but reflowed differently from the
    extraction is NOT silently accepted here — the caller is told nothing matched, and what the
    database would verify is the extraction's own characters, so an approximate match would produce
    `quote_verified = false` rows and call them evidence.

    `ws` is the caller's open workstream, or None (decisions.yaml litkb-web-source-gate). With it,
    a file THIS workstream proposed is searched as well as main's — the same widening
    `litkb_search` and `_record_use` make, from the same one definition in `litkb.visibility`, so
    the CLI cannot end up able to find a quote the MCP path cannot or the other way round.
    """
    from litkb import visibility

    sql = ("SELECT b.id, b.run_id, b.page_no, b.text FROM litkb.blocks b "
           "  JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id "
           + visibility.FILE_JOIN +
           " WHERE fv.work_id = %(work_id)s AND fv.status = 'active' "
           "   AND b.text IS NOT NULL AND position(%(quote)s in b.text) > 0")
    args = {"work_id": work_id, "quote": quote, "ws": ws}
    if page is not None:
        sql += " AND b.page_no = %(page)s"
        args["page"] = page
    out = []
    for bid, run, pno, text in conn.execute(sql + " ORDER BY b.page_no, b.reading_order NULLS LAST", args).fetchall():
        start = text.index(quote)
        out.append({"block_id": bid, "run_id": run, "page": pno, "char_start": start,
                    "char_end": start + len(quote)})
    return out


def write_use(conn, ws, token, *, work_id, statement, kind, agent, session, gap_id=None, status="proposed",
              feeds=(), confidence=None, rationale=None, change_reason=None, based_on=None, use_id=None,
              hunt_request_id=None):
    """litkb.write_proposal('use', …) -> (use_id, version_id). The token is bound as a parameter.

    `front._jsonb` is the project's one JSON adapter and it runs `textnorm.jsonb_safe` on the way in
    — a NUL in a statement or a rationale is what it exists to strip. A local wrapper here would be a
    second copy of that guard, which is exactly the shape the mutation harness caught in E3f.

    `hunt_request_id` (migration 0023): which drop-off, if any, this use circles back to. Identity,
    like work_id/gap_id — set only when the use is CREATED (`use_id` is None); `_create_identity`
    refuses one from another workstream.
    """
    from litkb.admit.front import _jsonb

    fields = {"statement": statement, "kind": kind, "status": status, "feeds": list(feeds or []),
              "confidence": confidence, "rationale": rationale}
    row = conn.execute(
        "SELECT * FROM litkb.write_proposal(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("use", use_id, _jsonb({"work_id": str(work_id), "gap_id": str(gap_id) if gap_id else None,
                                "hunt_request_id": str(hunt_request_id) if hunt_request_id else None}),
         based_on, _jsonb(fields), change_reason, ws, token, agent, session)).fetchone()
    return row[0], row[1]


def attach_quote(conn, ws, token, version_id, anchor, quote, *, stance="supports"):
    """litkb.add_evidence -> {"evidence_id": …, "quote_verified": …}. The verdict is the database's."""
    res = conn.execute(
        "SELECT * FROM litkb.add_evidence(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (ws, token, version_id, anchor["block_id"], anchor["run_id"], anchor["page"], quote,
         anchor["char_start"], anchor["char_end"], stance)).fetchone()
    return {"evidence_id": res[0], "quote_verified": res[1]}

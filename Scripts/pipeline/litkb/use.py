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
* **`quote_verified` is the database's**. `add_evidence` inserts, the verify trigger (0007, and
  0026 for the comparison) re-reads the block at `[char_start, char_end)` and sets the column, and no
  role but the owner may write it (0006). What this module reports is what the database computed,
  never what it hoped. Since 0026 the comparison is on CANONICAL LINE ENDINGS — the quote stored is
  still the caller's own string, and the database still decides whether it is the block's span, so
  the verdict has not moved to this side of the wire; what moved is that `\r\n` and `\n` stopped
  counting as different text. `locate_in_text` applies the same rule when it chooses the offsets.

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


def locate_in_text(text, quote):
    """Where `quote` sits in `text` -> `(char_start, char_end)` into TEXT'S OWN characters, or None.

    THE ONE PYTHON LOCATOR. `mcp/server.py::_record_use` and `locate_quote` below both call it, so
    the MCP path and the CLI path cannot come to different answers about where a quote is — which
    they did until 2026-09-20, when each had its own `find`.

    The comparison is on CANONICAL LINE ENDINGS (`textnorm.canonical_newlines`), the rule the
    grader already applied to both sides of its own comparison and the recording path did not.
    MEASURED on the 2026-09-19 corpus: 48.9 % of current-run blocks store `\\r\\n` and 7 of the 8
    verified spans the project holds cross one, while the writer is an LLM emitting JSON — the
    transport carries `\\r\\n` perfectly well (json.dumps/loads round-trips it), but no LLM has
    been observed producing a raw CR, so every quote that reached this path was LF-only and every
    quote crossing a stored CRLF was refused as "not in that block". The operational proving run
    (2026-09-20) therefore recorded single-line FRAGMENTS — the longest newline-free run inside a
    real verified span is 33 characters — and an adversarial reviewer found half the resulting
    sentences overreaching them.

    THE OFFSETS RETURNED ARE RAW. `[char_start, char_end)` indexes `text` exactly as stored, so
    `substring(b.text …)` in migration 0026's trigger cuts the same characters, the D-7 bound is
    still `length(b.text)`, and the 8 existing verified rows keep both their offsets and their
    meaning. Canonicalisation decides WHETHER the quote is there; it never moves a byte.

    THE REVERSE GUARANTEE. `canonical_newlines` rewrites line ENDINGS and nothing else: every
    non-newline character, their order, and the NUMBER of breaks survive. So a match here means
    the quote and that span agree on every character and every break POSITION, and differ only in
    how a break is written. One changed character, one dropped word, one blank line dropped to
    join two paragraphs — each still returns None, and `qc/test_litkb_first_use.py` holds a row
    for each.

    A quote whose canonical form BEGINS OR ENDS with a break is refused outright: see the guard
    below for why its offsets would not be unique.
    """
    from litkb.textnorm import canonical_newlines

    if text is None or not quote:
        return None
    canon_text, canon_quote = canonical_newlines(text), canonical_newlines(quote)
    # BEGIN guard: the quote does not begin or end with a line break, so its offsets are unique
    # Canonicalising the equality pins a span's CONTENT and, for a quote whose first and last
    # characters are ordinary, its OFFSETS too: each has exactly one raw index. A break at either
    # END breaks that, because `\r\n` is two raw characters and one canonical one, so the span may
    # start after the `\r` or before it. MEASURED on `abc\r\ndef` (migration 0026's header): the
    # quote `abc\n` satisfies the database's comparison at raw [0,4) AND at raw [0,5), while the
    # interior `bc\nde` satisfies it at [1,7) only. The offsets are what says WHICH words anyone
    # checked, so an ambiguous pair is a hole; refusing costs a quoter nothing, since a quote that
    # opens or closes on a line break carries no word at that end. The 0026 trigger refuses the
    # same shape, for the caller that supplies char_start/char_end itself and never comes here.
    if canon_quote.startswith("\n") or canon_quote.endswith("\n"):
        return None
    # END guard: the quote does not begin or end with a line break, so its offsets are unique
    # BEGIN guard: a quote is located on canonical line endings, at the stored text's own offsets
    i = canon_text.find(canon_quote)
    if i < 0:
        return None
    # raw_at[k] is where canonical character k begins in `text`; a `\r\n` is ONE canonical
    # character and TWO stored ones, which is the whole of the arithmetic. The final entry is
    # len(text), so a span ending at the last character needs no special case.
    raw_at, j = [], 0
    while j < len(text):
        raw_at.append(j)
        j += 2 if text.startswith("\r\n", j) else 1
    raw_at.append(len(text))
    start, end = raw_at[i], raw_at[i + len(canon_quote)]
    # END guard: a quote is located on canonical line endings, at the stored text's own offsets
    if canonical_newlines(text[start:end]) != canon_quote:      # pragma: no cover - arithmetic bug
        raise AssertionError(f"litkb: newline offset mapping is wrong at [{start}, {end})")
    return start, end


def newline_canon_available(conn):
    """True when this database has migration 0026's `litkb.canonical_newlines(text)`.

    Asked rather than assumed for the reason `_bad_feeds` asks about `litkb._feeds_token_ok`: a
    client can run against a database whose migrations are older than its code, and the honest
    answer there is a REFUSAL naming the missing migration. It matters more here than for feeds,
    because the failure would otherwise be silent in the worst direction: with the new locator and
    the OLD trigger, a quote that crosses a stored CRLF would be LOCATED and then written with
    `quote_verified = false` — an unverified row where the old code refused cleanly, which is
    strictly worse than the defect being fixed.
    """
    return bool(conn.execute(
        "SELECT to_regprocedure('litkb.canonical_newlines(text)') IS NOT NULL").fetchone()[0])


def locate_quote(conn, work_id, quote, page=None, ws=None):
    """Where the quote sits in the work's extracted text -> list of candidate anchors.

    The search is over the CURRENT run of the work's active files only (`files.current_run_id`), for
    the same reason `use_evidence_status.promotable` compares against it: evidence recorded against a
    superseded run is evidence about text that is no longer the file's answer. Since S4 that join
    is spelled ONCE, in `litkb.readability.current_run_join`, and it also requires `b.canonical` —
    a run migration 0030's `litkb.retire_run` has retired is not quotable.

    Matching is exact on the block text, up to the ENCODING of a line ending and nothing else
    (`locate_in_text` above, and `litkb.canonical_newlines` on the block side — migration 0026, the
    same function the verify trigger uses, so this cannot find a quote the database would then
    refuse to verify). A quote that is right but REFLOWED differently from the extraction is still
    NOT accepted: the caller is told nothing matched, because what the database verifies is the
    extraction's own characters and an approximate match would produce `quote_verified = false`
    rows and call them evidence.

    `ws` is the caller's open workstream, or None (decisions.yaml litkb-web-source-gate). With it,
    a file THIS workstream proposed is searched as well as main's — the same widening
    `litkb_search` and `_record_use` make, from the same one definition in `litkb.visibility`, so
    the CLI cannot end up able to find a quote the MCP path cannot or the other way round.
    """
    from litkb import readability, visibility
    from litkb.textnorm import canonical_newlines, sql_canonical_newlines

    if not newline_canon_available(conn):
        raise RuntimeError(
            "litkb: this database has no litkb.canonical_newlines — migration 0026 has not been "
            "applied, so a quote cannot be located by the same rule the verify trigger uses. "
            "Apply the migrations (py -3.12 -m litkb.db.migrate --db <db>) before recording uses.")
    sql = ("SELECT b.id, b.run_id, b.page_no, b.text FROM litkb.blocks b "
           + readability.current_run_join()
           + visibility.FILE_JOIN +
           " WHERE fv.work_id = %(work_id)s AND fv.status = 'active' "
           "   AND b.text IS NOT NULL AND position(%(quote)s in "
           + sql_canonical_newlines("b.text") + ") > 0")
    args = {"work_id": work_id, "quote": canonical_newlines(quote), "ws": ws}
    if page is not None:
        sql += " AND b.page_no = %(page)s"
        args["page"] = page
    out = []
    for bid, run, pno, text in conn.execute(sql + " ORDER BY b.page_no, b.reading_order NULLS LAST", args).fetchall():
        span = locate_in_text(text, quote)
        if span is None:                                        # pragma: no cover - SQL said yes
            continue
        out.append({"block_id": bid, "run_id": run, "page": pno, "char_start": span[0],
                    "char_end": span[1]})
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

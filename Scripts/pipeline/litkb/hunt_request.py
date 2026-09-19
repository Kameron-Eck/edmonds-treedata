"""The drop-off record (migration 0023) — a review agent's unverified prior about a paper it has
not hunted yet, written before the full text exists.

    hr_id = record(conn, ws, token, ref="10.1145/...", ref_scheme="doi",
                   expected_claim="…", why_relevant="…", abstract_passage="…", agent=…, session=…)
    link(conn, ws, token, hr_id, work_id=…, agent=…, session=…)     # called from hunt.py
    status(conn, hr_id)                                             # -> the resolution ladder

THE GOVERNING CONSTRAINT (delta, 2026-09-18): a hunt_request holds the OPPOSITE of what litkb
otherwise treats as evidence — an agent's expectation, not a verified quote. Everything here is a
thin wrapper around the two SECURITY DEFINER functions the database enforces this with
(`litkb.record_hunt_request`, `litkb.link_hunt_request`) and the view that derives resolution
state (`litkb.hunt_request_status`, migration 0023) — there is no Python-side copy of any check:
CLAUDE.md 3.3, one fact one home. In particular `status()` below reads a view; it does not compute
a state itself, so there is nothing here for a caller to get wrong in the way the database already
refuses.

Neither function normalises agent/session (unlike `use.py`'s callers, which go through
`textnorm.norm_label` before reaching here) — callers pass already-normalised labels, exactly like
`front.admit_registry` expects. That is deliberate: normalising twice is how E3f-class drift starts
(CLAUDE.md 3.3), and every caller of this module already normalises once (hunt.py's `_hunt`,
commands.py's `_labels`, mcp/server.py's `_labels`).
"""


def record(conn, ws, token, *, ref, ref_scheme, expected_claim, why_relevant, agent, session,
           abstract_passage=None, claimed_title=None, claimed_authors=None, claimed_year=None,
           gap_id=None):
    """The review agent's write. -> hunt_request_id.

    `ref_scheme` is the database's own vocabulary (doi, arxiv, jstor, isbn, pmid, pmcid, openalex,
    s2, handle, url, tracker, legacy_stem, other) — a value outside it is refused by the table's
    own CHECK, not re-validated here.
    """
    row = conn.execute(
        "SELECT litkb.record_hunt_request(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (ws, token, ref, ref_scheme, expected_claim, why_relevant, abstract_passage, claimed_title,
         claimed_authors, claimed_year, gap_id, agent, session)).fetchone()
    return row[0]


def link(conn, ws, token, hunt_request_id, *, work_id, agent, session):
    """Record which work a drop-off resolved to. -> True, or raises the database's refusal
    (already linked to a DIFFERENT work; the work is not this workstream's; not this workstream's
    request). Idempotent: linking the SAME work twice succeeds and changes nothing.
    """
    row = conn.execute("SELECT litkb.link_hunt_request(%s, %s, %s, %s, %s, %s)",
                       (ws, token, hunt_request_id, work_id, agent, session)).fetchone()
    return bool(row[0])


def status(conn, hunt_request_id):
    """One row of `litkb.hunt_request_status`, or None. `resolution_state` is the database's own
    derivation (open/unconfirmed/confirmed/contradicted) — never recomputed here."""
    row = conn.execute(
        "SELECT id, workstream_id, ref, ref_scheme, expected_claim, why_relevant, "
        "       abstract_passage, claimed_title, claimed_authors, claimed_year, gap_id, work_id, "
        "       agent, session_id, created_at, linked_at, n_confirming, n_contradicting, "
        "       resolution_state "
        "  FROM litkb.hunt_request_status WHERE id = %s", (hunt_request_id,)).fetchone()
    if not row:
        return None
    cols = ("id", "workstream_id", "ref", "ref_scheme", "expected_claim", "why_relevant",
            "abstract_passage", "claimed_title", "claimed_authors", "claimed_year", "gap_id",
            "work_id", "agent", "session_id", "created_at", "linked_at", "n_confirming",
            "n_contradicting", "resolution_state")
    return dict(zip(cols, row))


def list_for_workstream(conn, ws, *, state=None, limit=50):
    """This workstream's drop-offs, newest first, optionally filtered on resolution_state."""
    sql = ("SELECT id, ref, ref_scheme, expected_claim, resolution_state, n_confirming, "
           "       n_contradicting, work_id, created_at "
           "  FROM litkb.hunt_request_status WHERE workstream_id = %s")
    args = [ws]
    if state:
        sql += " AND resolution_state = %s"
        args.append(state)
    sql += " ORDER BY created_at DESC LIMIT %s"
    args.append(limit)
    cols = ("id", "ref", "ref_scheme", "expected_claim", "resolution_state", "n_confirming",
            "n_contradicting", "work_id", "created_at")
    return [dict(zip(cols, r)) for r in conn.execute(sql, args).fetchall()]

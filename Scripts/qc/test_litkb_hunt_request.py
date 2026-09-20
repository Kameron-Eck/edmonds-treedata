"""litkb hunt_request (migration 0023) — the drop-off record, WORKPLAN.md "Next phase" missing
piece 1. Delta 2026-09-18: three gates, enforced as database/derivation properties rather than
convention.

  gate                                                              test
  resolution_state is DERIVED (no column exists to write directly) test_a_fresh_drop_off_is_open
                                                                     test_linking_moves_open_to_unconfirmed
                                                                     test_a_verified_supporting_use_confirms_the_request
                                                                     test_a_verified_refuting_use_contradicts_and_wins
                                                                     test_confirmation_requires_the_JOIN_not_just_any_promotable_use
                                                                     test_confirmation_requires_a_PROMOTABLE_row_not_any_quote_verified_row
  the evidence path never reads expected_claim / abstract_passage  test_evidence_path_sources_never_reference_hunt_request_columns
                                                                     test_the_scan_itself_catches_a_spliced_in_reference
  abstract_passage is unverified by construction (COMMENT)         test_abstract_passage_column_is_documented_as_unverified
  a use may not name another workstream's hunt_request             test_a_use_cannot_name_another_workstreams_hunt_request
  link_hunt_request: narrow, idempotent, workstream-scoped          test_link_hunt_request_is_idempotent_on_the_same_work
                                                                     test_link_hunt_request_refuses_a_different_work_once_linked
                                                                     test_link_hunt_request_refuses_a_work_this_workstream_cannot_see
  the writer holds no direct write on hunt_requests                 test_the_writer_holds_no_direct_write_on_hunt_requests
  record_hunt_request needs the workstream token                    test_record_hunt_request_needs_the_workstream_token
  cmd_hunt_request refuses without labels (site HR1)                test_cmd_hunt_request_refuses_without_labels

The database-level mutation campaign (break each -- BEGIN guard -- block, show this file plus
qc/test_litkb_p2.py/test_litkb_annas.py fail, restore, sha256-verify) lives in
qc/instruments/litkb_p2_mutations.py rows H1-H6, HR1, HR2 (2026-09-18 delta report). This file is
what those rows run.

Discrepancies (0015) vs hunt_request (0023), in one sentence (the delta asked for exactly one):
discrepancies reconciles two records of the SAME kind of fact (a legacy tracker/manifest field vs
the admitted registry record) by a comparator ratio the P3 loader computes, while a hunt_request's
contradiction is an agent's PRIOR checked against a verified quote's stance on the paper's own
extracted text -- different subjects, different resolvers, and reusing discrepancies would put
expectation text on `_work`'s existing discrepancies read path, which gate 2 forbids.
"""
import uuid

import pytest

import test_litkb_p1 as _p1mod
from test_litkb_p1 import _add_evidence, _evidence_world

# the P1 suite's session fixtures, reused so this file shares ONE reset of litkb_test rather than
# opening a second one (two modules each holding the suite lock on their own connection deadlock —
# same reason test_litkb_p3.py binds test_litkb_p2's `pg` this way, by assignment rather than
# `from ... import pg`, which ruff's F811 misreads as an unused redefinition against every
# `def test_x(pg):` parameter below).
_pg_session = _p1mod._pg_session
pg = _p1mod.pg

pg_only = pytest.mark.requires_litkb_pg

# ── gate 1: resolution_state is derived ─────────────────────────────────────────────────────


def _record(pg, ws, *, ref="10.1/x", ref_scheme="doi", expected_claim="claim", why_relevant="why",
           abstract_passage="an abstract snippet", gap=None):
    return pg.one(
        "SELECT litkb.record_hunt_request(%s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, "
        "'agentA', 'sessA')",
        (ws, pg.tokens[ws], ref, ref_scheme, expected_claim, why_relevant, abstract_passage,
         gap))[0]


def _link(pg, ws, hr, work_id, *, agent="agentA", session="sessA"):
    return pg.one("SELECT litkb.link_hunt_request(%s, %s, %s, %s, %s, %s)",
                  (ws, pg.tokens[ws], hr, work_id, agent, session))[0]


def _status(pg, hr):
    row = pg.one(
        "SELECT resolution_state, n_confirming, n_contradicting, work_id "
        "  FROM litkb.hunt_request_status WHERE id = %s", (hr,))
    return {"resolution_state": row[0], "n_confirming": row[1], "n_contradicting": row[2],
            "work_id": row[3]}


@pg_only
def test_a_fresh_drop_off_is_open(pg):
    ws = pg.ws()
    hr = _record(pg, ws)
    st = _status(pg, hr)
    assert st == {"resolution_state": "open", "n_confirming": 0, "n_contradicting": 0,
                  "work_id": None}, st


@pg_only
def test_linking_moves_open_to_unconfirmed(pg):
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    hr = _record(pg, ws)
    assert _link(pg, ws, hr, work_id) is True
    st = _status(pg, hr)
    assert st["resolution_state"] == "unconfirmed", st
    assert st["work_id"] == work_id


@pg_only
def test_a_verified_supporting_use_confirms_the_request(pg):
    """The only path to `confirmed`: a use naming this hunt_request (identity, set at creation)
    with a use_evidence row that is PROMOTABLE (verified AND anchored in the current run) and
    stance='supports'. Gate 1's mutation target: drop the `ues.promotable` term from the view and
    a use with a deliberately unverifiable quote (wrong offsets) must flip this to `confirmed`."""
    ws = pg.ws()
    w = _evidence_world(pg)                        # its own use/work; unrelated to hr
    hr = _record(pg, w["ws"])
    _link(pg, w["ws"], hr, w["work"])
    use_id, uv = pg.proposal(pg.conn, "use", None,
                             {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                             {"statement": "confirms it", "kind": "empirical evidence",
                              "status": "supported"}, None, w["ws"])
    assert _status(pg, hr)["resolution_state"] == "unconfirmed", "no evidence yet: still unconfirmed"
    # an UNVERIFIED quote (wrong offsets: 0:3 is not w["text"][4:20]) must NOT confirm anything —
    # this is the live instance of gate 1's mutation (drop `promotable`, this assertion is what fails)
    _add_evidence(pg, pg.conn, w, w["ws"], uv, "not at these offsets", 10, 30, stance="supports")
    assert _status(pg, hr)["resolution_state"] == "unconfirmed", (
        "an unverified quote must never confirm a hunt_request")
    _add_evidence(pg, pg.conn, w, w["ws"], uv, w["text"][4:20], 4, 20, stance="supports")
    st = _status(pg, hr)
    assert st["resolution_state"] == "confirmed", st
    assert st["n_confirming"] == 1 and st["n_contradicting"] == 0, st


@pg_only
def test_a_verified_refuting_use_contradicts_and_wins(pg):
    w = _evidence_world(pg)
    hr = _record(pg, w["ws"])
    _link(pg, w["ws"], hr, w["work"])
    use_id, uv = pg.proposal(pg.conn, "use", None,
                             {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                             {"statement": "refutes it", "kind": "contradiction",
                              "status": "refuted"}, None, w["ws"])
    _add_evidence(pg, pg.conn, w, w["ws"], uv, w["text"][0:3], 0, 3, stance="refutes")
    st = _status(pg, hr)
    assert st["resolution_state"] == "contradicted", st
    assert st["n_confirming"] == 0 and st["n_contradicting"] == 1, st
    # a SECOND use, supporting, must not overrule the contradiction (contradicted wins, like a
    # discrepancy: a conflict between two verified uses is recorded, never silently dropped)
    use2_id, uv2 = pg.proposal(pg.conn, "use", None,
                               {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                               {"statement": "also supports", "kind": "context",
                                "status": "supported"}, None, w["ws"])
    _add_evidence(pg, pg.conn, w, w["ws"], uv2, w["text"][21:40], 21, 40, stance="supports")
    st = _status(pg, hr)
    assert st["resolution_state"] == "contradicted", st
    assert st["n_confirming"] == 1 and st["n_contradicting"] == 1, st


@pg_only
def test_confirmation_requires_the_JOIN_not_just_any_promotable_use(pg):
    """Gate 1's SECOND mutation target: drop `u.hunt_request_id = hr.id` from the view's lateral
    join. Two requests in one world, only one linked to a use with promotable evidence -- the
    OTHER request must stay unconfirmed."""
    w = _evidence_world(pg)                         # w["uv"] already exists, unlinked to any hr
    hr_linked = _record(pg, w["ws"], ref="10.1/linked")
    hr_unlinked = _record(pg, w["ws"], ref="10.1/unlinked")
    _link(pg, w["ws"], hr_linked, w["work"])
    _link(pg, w["ws"], hr_unlinked, w["work"])
    use_id, uv = pg.proposal(pg.conn, "use", None,
                             {"work_id": str(w["work"]), "hunt_request_id": str(hr_linked)}, None,
                             {"statement": "confirms hr_linked only", "kind": "empirical evidence",
                              "status": "supported"}, None, w["ws"])
    _add_evidence(pg, pg.conn, w, w["ws"], uv, w["text"][4:20], 4, 20, stance="supports")
    assert _status(pg, hr_linked)["resolution_state"] == "confirmed"
    assert _status(pg, hr_unlinked)["resolution_state"] == "unconfirmed", (
        "a use linked to ANOTHER request must not confirm this one")


@pg_only
def test_confirmation_requires_a_PROMOTABLE_row_not_any_quote_verified_row(pg):
    """`use_evidence_status.promotable` also requires the evidence's run to be the file's CURRENT
    run (§4.5) -- not merely `quote_verified`. A superseded run's verified quote must not confirm."""
    w = _evidence_world(pg)
    hr = _record(pg, w["ws"])
    _link(pg, w["ws"], hr, w["work"])
    use_id, uv = pg.proposal(pg.conn, "use", None,
                             {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                             {"statement": "s", "kind": "context", "status": "supported"}, None,
                             w["ws"])
    _add_evidence(pg, pg.conn, w, w["ws"], uv, w["text"][4:20], 4, 20, stance="supports")
    assert _status(pg, hr)["resolution_state"] == "confirmed"
    # move the file's current run to a NEW run: the old evidence is verified but no longer current
    new_run = pg.one(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'test2', '0', 'p', 'v0', 'local', "
        "'ok') RETURNING id", (w["file"],))[0]
    pg.conn.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], new_run))
    assert _status(pg, hr)["resolution_state"] == "unconfirmed", (
        "evidence anchored in a superseded run must not confirm a hunt_request")


# ── gate 2: the evidence path never reads expected_claim / abstract_passage ────────────────

_FORBIDDEN = ("expected_claim", "abstract_passage")


def _scan(*texts):
    """The forbidden columns, found in any of the given SQL/source texts."""
    return [c for t in texts for c in _FORBIDDEN if c in t]


def test_evidence_path_sources_never_reference_hunt_request_columns():
    """The named evidence-path sources (delta's list): litkb_search's six queries, the block SELECT
    `_record_use` anchors evidence against, and `use.py::locate_quote`. A hunt_request join has no
    business in any of them -- evidence comes from ingested block bytes, never from an agent's
    prior."""
    from litkb.mcp import server
    from litkb import use as use_mod
    import inspect

    sources = [server._SEARCH_BLOCKS_ALL, server._SEARCH_BLOCKS_ANY, server._SEARCH_BLOCKS_TRGM,
               server._SEARCH_USES_ALL, server._SEARCH_USES_ANY, server._SEARCH_USES_TRGM,
               inspect.getsource(use_mod.locate_quote), inspect.getsource(server._record_use)]
    hits = _scan(*sources)
    assert hits == [], f"the evidence path references hunt_request columns: {hits}"


def test_the_scan_itself_catches_a_spliced_in_reference():
    """The kill for the scan above: a live join (not a comment -- CLAUDE.md 3.4c, a comment-only
    edit is a planted equivalent, not a mutation) spliced into a copy of one leg must be caught.
    The real mutation, on the real file, is litkb_p2_mutations.py row H5/H6."""
    from litkb.mcp import server

    spliced = server._SEARCH_BLOCKS_ALL + (
        "\n  LEFT JOIN litkb.hunt_requests hr ON hr.expected_claim <> ''  -- spliced, not a comment")
    assert _scan(spliced) == ["expected_claim"], "the scan failed to catch a spliced-in reference"
    assert _scan(server._SEARCH_BLOCKS_ALL) == [], "the UNMUTATED constant must still scan clean"


def test_abstract_passage_column_is_documented_as_unverified(pg):
    comment = pg.one(
        "SELECT col_description('litkb.hunt_requests'::regclass, "
        "(SELECT attnum FROM pg_attribute WHERE attrelid = 'litkb.hunt_requests'::regclass "
        "AND attname = 'abstract_passage'))")[0]
    assert comment and "UNVERIFIED" in comment and "never quotable" in comment.lower(), comment


# ── use.hunt_request_id: identity, ownership-checked ────────────────────────────────────────


@pg_only
def test_a_use_cannot_name_another_workstreams_hunt_request(pg):
    ws_a = pg.ws()
    ws_b = pg.ws()
    work_id, _ = pg.work(ws_a)
    hr_a = _record(pg, ws_a)
    with pytest.raises(pg.errors.InsufficientPrivilege):
        pg.proposal(pg.conn, "use", None,
                   {"work_id": str(work_id), "hunt_request_id": str(hr_a)}, None,
                   {"statement": "s", "kind": "context", "status": "proposed"}, None, ws_b)


# ── link_hunt_request: narrow, idempotent, workstream-scoped ────────────────────────────────


@pg_only
def test_link_hunt_request_is_idempotent_on_the_same_work(pg):
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    hr = _record(pg, ws)
    assert _link(pg, ws, hr, work_id) is True
    assert _link(pg, ws, hr, work_id) is True     # same work again: no-op success


@pg_only
def test_link_hunt_request_refuses_a_different_work_once_linked(pg):
    ws = pg.ws()
    w1, _ = pg.work(ws)
    w2, _ = pg.work(ws)
    hr = _record(pg, ws)
    _link(pg, ws, hr, w1)
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="already linked"):
        _link(pg, ws, hr, w2)


@pg_only
def test_link_hunt_request_refuses_a_work_this_workstream_cannot_see(pg):
    """`pg.work()` writes a FACT (mode='fact'): it lands in main immediately and is then visible
    to every workstream's `ws_works` (main's pointer is the fallback when a workstream has no head
    of its own). A genuine PROPOSAL — the shape a web-source admission actually produces (hunt.py:
    'the work stays a PROPOSAL ... until a SECOND session approves') — is scoped to its creating
    workstream until promoted, which is the case this guard exists for."""
    ws_a = pg.ws()
    ws_b = pg.ws()
    key = f"Test_2020_{uuid.uuid4().hex[:8]}-paper"
    # `write_proposal` (the PUBLIC entry point) refuses 'work' by name (only gap/use are
    # proposals through it); a work-as-proposal is what admit_web produces, calling
    # `_write_version` directly. As the schema OWNER (pg.conn), that call is available for setup.
    work_id, _ = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('proposal', 'work', NULL, %s, "
        "NULL, %s, NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"key": key}),
         pg.Jsonb({"type": "article", "title": "A proposed work", "authors": []}), ws_a))
    hr_b = _record(pg, ws_b)
    with pytest.raises(pg.errors.InsufficientPrivilege):
        _link(pg, ws_b, hr_b, work_id)


# ── the guarded relation ─────────────────────────────────────────────────────────────────────


@pg_only
def test_the_writer_holds_no_direct_write_on_hunt_requests(pg):
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(
            "INSERT INTO litkb.hunt_requests (workstream_id, ref, ref_scheme, expected_claim, "
            "why_relevant, agent, session_id) VALUES (gen_random_uuid(), 'x', 'doi', 'c', 'w', "
            "'a', 's')")


@pg_only
def test_record_hunt_request_needs_the_workstream_token(pg):
    ws = pg.ws()
    with pytest.raises(pg.errors.InsufficientPrivilege):
        pg.one("SELECT litkb.record_hunt_request(%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, "
              "NULL, 'a', 's')", (ws, "not-the-token", "10.1/x", "doi", "c", "w"))


@pg_only
def test_link_hunt_request_needs_the_workstream_token(pg):
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    hr = _record(pg, ws)
    with pytest.raises(pg.errors.InsufficientPrivilege):
        pg.one("SELECT litkb.link_hunt_request(%s, %s, %s, %s, 'a', 's')",
              (ws, "not-the-token", hr, work_id))


@pg_only
def test_link_hunt_request_needs_an_agent_and_a_session(pg):
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    hr = _record(pg, ws)
    with pytest.raises(pg.errors.InvalidParameterValue, match="agent and a session"):
        _link(pg, ws, hr, work_id, agent="", session="s")


@pg_only
def test_record_hunt_request_writes_only_into_an_open_workstream(pg):
    ws = pg.ws()
    pg.conn.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws, pg.tokens[ws]))
    with pytest.raises(pg.errors.InvalidParameterValue) as ei:
        _record(pg, ws)
    assert "is not open" in str(ei.value)


# ── row HR1: cmd_hunt_request refuses without labels ────────────────────────────────────────


def test_cmd_hunt_request_refuses_without_labels(tmp_path, monkeypatch):
    """Row HR1 (qc/instruments/litkb_p2_mutations.py): `cmd_hunt_request` reaches `_labels(args)`
    like `cmd_use`/`cmd_admit`/`cmd_acquire` do, and a drop-off with no recorded agent/session is
    an unattributed write (CLAUDE.md 3.1). A real `.litkb-workstream` is planted so `_ws(args)`
    succeeds and the SystemExit below can only come from the labels guard, not from a missing
    workstream — no database round trip is made either way."""
    import argparse
    import json
    import uuid

    from litkb import commands

    monkeypatch.delenv("LITKB_AGENT", raising=False)
    monkeypatch.delenv("LITKB_SESSION", raising=False)
    (tmp_path / ".litkb-workstream").write_text(
        json.dumps({"workstream_id": str(uuid.uuid4()), "token": "t"}), encoding="utf-8")
    args = argparse.Namespace(dir=str(tmp_path), agent=None, session=None,
                              hunt_request_cmd="add", ref="10.1/x", ref_scheme="doi",
                              expected_claim="c", why_relevant="w", abstract_passage=None,
                              claimed_title=None, claimed_authors=None, claimed_year=None, gap=None)
    with pytest.raises(SystemExit, match="agent and a session"):
        commands.cmd_hunt_request(args, commands._NoConn())


# ── the table's own CHECKs: a drop-off with no expectation is not a drop-off ────────────────

@pg_only
@pytest.mark.parametrize("field", ["expected_claim", "why_relevant"])
def test_a_drop_off_with_an_empty_expectation_is_refused(pg, field):
    """A hunt_request exists to record WHAT an agent expected and WHY, so a later verified use can
    be checked against it. A row with either field empty records nothing checkable, and
    `hunt_request_status` would still walk it open -> unconfirmed -> confirmed as though it did.

    The CHECK is the table's own (`hunt_requests_expected_claim_check`, migration 0023); mutation
    row HQ9 removes it and shows this test go red. Written 2026-09-20 alongside S1's migration
    0027, which DROPs and re-ADDs the ref_scheme CHECK on this same table: a constraint rebuild is
    exactly the moment the OTHER constraints on a table want covering, and nothing covered these."""
    ws = pg.ws()
    with pytest.raises(pg.errors.CheckViolation, match=field):
        _record(pg, ws, **{field: ""})


@pg_only
def test_the_ref_scheme_check_survived_its_rebuild_and_now_admits_title(pg):
    """Migration 0027 DROPs and re-ADDs `hunt_requests_ref_scheme_check` under the same name. Both
    halves are asserted: `title` is accepted (it was not before 0027), and a scheme outside the
    vocabulary is still refused BY THE DATABASE — the Python-side checks at the CLI and the MCP
    entry point are what a caller READS, never what enforces."""
    ws = pg.ws()
    hr = _record(pg, ws, ref="A Title With No Identifier", ref_scheme="title")
    assert pg.one("SELECT ref_scheme FROM litkb.hunt_requests WHERE id = %s", (hr,))[0] == "title"
    with pytest.raises(pg.errors.CheckViolation, match="ref_scheme"):
        _record(pg, ws, ref="x", ref_scheme="bibtex")


def test_the_sql_check_and_the_python_vocabulary_agree():
    """ONE ref-scheme vocabulary (CLAUDE.md §3.3). The SQL CHECK is what ENFORCES it; the Python
    constant `litkb.hunt_request.REF_SCHEMES` is what the CLI and the MCP tool refuse against
    BEFORE the write, so a caller reads a named refusal instead of a raw PL/pgSQL sentence. A
    stale copy in Python would refuse, at the MCP layer, a scheme the database accepts — which is
    exactly how the lit-scout's first `title` drop-off would have died.

    The HIGHEST-numbered migration that states the CHECK is the live one: reading only 0023 would
    compare against the list 0027 replaced, and the test would pass while the two disagreed. No
    database — this reads the migration FILES, so it holds on a machine with no Postgres."""
    import pathlib
    import re as _re

    from litkb.hunt_request import REF_SCHEMES

    mig = (pathlib.Path(__file__).resolve().parents[1] / "pipeline" / "litkb" / "db"
           / "migrations")
    pat = _re.compile(r"ref_scheme\s+IN\s*\((?P<body>[^)]*)\)", _re.S | _re.I)
    found = []
    for p in sorted(mig.glob("0*.sql")):
        m = pat.search(p.read_text(encoding="utf-8"))
        if m:
            found.append((p.name, tuple(_re.findall(r"'([a-z0-9_]+)'", m.group("body")))))
    assert found, "no migration states the hunt_requests.ref_scheme CHECK any more"
    live_file, live = found[-1]
    assert set(live) == set(REF_SCHEMES), (live_file, sorted(live), sorted(REF_SCHEMES))
    assert "title" in live, live_file

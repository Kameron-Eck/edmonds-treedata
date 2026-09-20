"""litkb brief (litkb/brief.py, Task B delta 2026-09-18) -- the per-workstream BRIEF export the
managing agent reads instead of the raw tables. Read-side only: no new stored state, no
migration. Two independent queries -- litkb.hunt_request_status for EXPECTED (an agent's
unverified prior), litkb.use_evidence_status for VERIFIED (a quote checked against ingested
block bytes) -- and the two gates that keep them from being confusable or lossy.

  gate (delta's governing constraint)                                test
  HB1 a VERIFIED line always carries work key/page/block id          test_verified_line_missing_location_fails_the_gate
                                                                       test_verified_lines_carry_full_location_end_to_end
  HB2 every hunt_request the workstream holds appears, no state      test_dropped_hunt_request_fails_the_gate
      filter (never silently dropped)                                 test_expected_lines_include_every_resolution_state
  HB3 the VERIFIED path never reads expected_claim/abstract_passage  test_verified_sql_never_references_hunt_request_columns
                                                                       test_the_scan_itself_catches_a_spliced_in_reference
  abstract_passage renders only under EXPECTED, never as a quote     test_render_never_puts_abstract_passage_in_a_verified_block
  a use with no promotable evidence contributes no VERIFIED line     test_verified_lines_exclude_non_promotable_evidence
  `litkb brief` writes both sections to a file                       test_cmd_brief_writes_expected_and_verified

The mutation campaign (break each -- BEGIN guard -- block or splice a live reference, show this
file fails, restore, sha256-verify) is qc/instruments/litkb_p2_mutations.py rows HB1-HB3.
"""
import argparse
import inspect

import pytest

import test_litkb_hunt_request as _hrmod
import test_litkb_p1 as _p1mod
from test_litkb_p1 import _add_evidence, _evidence_world

# the P1 suite's session fixtures, reused so this file shares ONE reset of litkb_test rather than
# opening a second one -- the same reason test_litkb_hunt_request.py binds them this way.
_pg_session = _p1mod._pg_session
pg = _p1mod.pg

pg_only = pytest.mark.requires_litkb_pg


# ── gate HB1: a VERIFIED line always carries its own location ──────────────────────────────


def test_verified_line_missing_location_fails_the_gate():
    from litkb import brief

    for missing in ("work_key", "page", "block_id"):
        line = {"work_key": "K_2020_x", "page": 1, "block_id": "b1", "statement": "s"}
        line[missing] = None
        with pytest.raises(brief.BriefInvariantError, match=missing):
            brief._require_location(line)


def test_verified_line_with_full_location_passes():
    from litkb import brief

    brief._require_location({"work_key": "K_2020_x", "page": 1, "block_id": "b1", "statement": "s"})


@pg_only
def test_verified_lines_carry_full_location_end_to_end(pg):
    from litkb import brief

    w = _evidence_world(pg)
    _add_evidence(pg, pg.conn, w, w["ws"], w["uv"], w["text"][4:20], 4, 20, stance="supports")
    lines = brief.verified_lines(pg.conn, w["ws"])
    assert len(lines) == 1, lines
    v = lines[0]
    key = pg.one("SELECT key FROM litkb.works WHERE id = %s", (w["work"],))[0]
    assert v["marker"] == "VERIFIED"
    assert v["work_key"] == key
    assert v["page"] == 1
    assert v["block_id"] == str(w["block"])
    assert v["quote"] == w["text"][4:20]
    assert v["kind"] == "theorem"
    assert v["statement"] == "supplies the optimism identity"
    assert v["stance"] == "supports"


@pg_only
def test_build_hands_the_MCP_WRITER_a_quote_with_canonical_line_endings(pg):
    """G2, on the path the writer actually walks. The agent's whole input is the MCP tool
    `litkb_brief`, which returns `build()`'s dicts verbatim (`mcp/server.py::_brief`) and never
    touches `render` -- so canonicalising the markdown alone would have fixed the path nobody
    walks. The stored block keeps its `\\r\\n`; the exported quote does not."""
    from litkb import brief

    w = _evidence_world(pg)
    text = "A canopy line\r\nand its second half, stored as the extractor wrote it."
    span = "A canopy line\r\nand its second half"
    block = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                   "(%s, %s, 1, 'paragraph', %s) RETURNING id", (w["file"], w["run"], text))[0]
    _add_evidence(pg, pg.conn, dict(w, block=block), w["ws"], w["uv"], span, 0, len(span))

    stored = pg.one("SELECT quote FROM litkb.use_evidence WHERE block_id = %s", (block,))[0]
    assert "\r\n" in stored, "the database must still hold the extractor's own bytes"

    _expected, verified = brief.build(pg.conn, w["ws"])
    assert len(verified) == 1, verified
    quote = verified[0]["quote"]
    assert "\r" not in quote, repr(quote)
    assert quote == stored.replace("\r\n", "\n")


@pg_only
def test_the_MCP_route_round_trips_a_crlf_span_into_a_passing_review(pg, tmp_path):
    """The whole path, end to end, on a block stored with `\\r\\n`: `build()`'s quote -- the exact
    string `litkb_brief` hands the agent -- pasted into an LF-only review file, graded by
    `review_check.check`. Before G2 this string carried a CR the writer had to reproduce."""
    from litkb import brief, review_check

    w = _evidence_world(pg)
    key = pg.one("SELECT key FROM litkb.works WHERE id = %s", (w["work"],))[0]
    text = ("Canopy cover fell by eleven percent between 2000 and 2020.\r\n"
            "The decline was concentrated in the northern parcels.")
    span = text[:len(text)]
    block = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                   "(%s, %s, 1, 'paragraph', %s) RETURNING id", (w["file"], w["run"], text))[0]
    _add_evidence(pg, pg.conn, dict(w, block=block), w["ws"], w["uv"], span, 0, len(span))
    hr = _hrmod._record(pg, w["ws"], ref="10.1/contradicted", expected_claim="the opposite")
    _hrmod._link(pg, w["ws"], hr, w["work"])
    _use, uv2 = pg.proposal(pg.conn, "use", None,
                            {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                            {"statement": "refutes it", "kind": "contradiction",
                             "status": "refuted"}, None, w["ws"])
    _add_evidence(pg, pg.conn, dict(w, block=block), w["ws"], uv2, text[:58], 0, 58,
                  stance="refutes")

    _expected, verified = brief.build(pg.conn, w["ws"])
    # the canonical quote is ONE character shorter than the span the database stores, which is
    # the whole point: the CRLF became an LF
    quote = max((v["quote"] for v in verified), key=len)
    assert "\r" not in quote and len(quote) == len(span) - 1

    review = (f"<!-- litkb-review workstream={w['ws']} -->\n\n# R\n"
              "\n## Scope\nOne quote, copied out of what litkb_brief returned.\n"
              "\n## Findings\n"
              f'The work states it: "{quote}" [{key} p.1 #{block}].\n'
              f"\n## Expectations not supported\n- hunt_request `{hr}` came back contradicted.\n"
              f"\n## Sources\n\n| work | key | pages |\n|---|---|---|\n| w | `{key}` | 1 |\n")
    path = tmp_path / "mcp_route.md"
    path.write_bytes(review.encode("utf-8"))
    assert b"\r" not in path.read_bytes()
    assert review_check.check(pg.conn, str(path)) == []


@pg_only
def test_verified_lines_exclude_non_promotable_evidence(pg):
    """A use with no PROMOTABLE quote contributes no VERIFIED line -- the exporter never invents a
    location-carrying line for evidence the database itself would not promote."""
    from litkb import brief

    w = _evidence_world(pg)
    assert brief.verified_lines(pg.conn, w["ws"]) == []
    # an UNVERIFIED quote (wrong offsets): still no VERIFIED line
    _add_evidence(pg, pg.conn, w, w["ws"], w["uv"], "not at these offsets", 10, 30, stance="supports")
    assert brief.verified_lines(pg.conn, w["ws"]) == [], (
        "an unverified quote must not print as a VERIFIED line")


# ── gate HB2: every hunt_request the workstream holds appears, no state filter ──────────────


@pg_only
def test_dropped_hunt_request_fails_the_gate(pg):
    from litkb import brief

    ws = pg.ws()
    _hrmod._record(pg, ws, ref="10.1/a")
    _hrmod._record(pg, ws, ref="10.1/b")
    full = brief.expected_lines(pg.conn, ws)
    assert len(full) == 2
    with pytest.raises(brief.BriefInvariantError, match="dropped"):
        brief._require_every_hunt_request(pg.conn, ws, full[:1])
    brief._require_every_hunt_request(pg.conn, ws, full)      # must not raise


@pg_only
def test_expected_lines_include_every_resolution_state(pg):
    """open, unconfirmed, confirmed, contradicted -- none filtered out of expected_lines(), each
    carrying the database's own resolution_state verbatim (never recomputed here)."""
    from litkb import brief

    w = _evidence_world(pg)
    ws = w["ws"]
    hr_open = _hrmod._record(pg, ws, ref="10.1/open")
    hr_unconfirmed = _hrmod._record(pg, ws, ref="10.1/unconfirmed")
    _hrmod._link(pg, ws, hr_unconfirmed, w["work"])
    hr_confirmed = _hrmod._record(pg, ws, ref="10.1/confirmed")
    _hrmod._link(pg, ws, hr_confirmed, w["work"])
    _use_id, uv = pg.proposal(pg.conn, "use", None,
                              {"work_id": str(w["work"]), "hunt_request_id": str(hr_confirmed)}, None,
                              {"statement": "confirms it", "kind": "empirical evidence",
                               "status": "supported"}, None, ws)
    _add_evidence(pg, pg.conn, w, ws, uv, w["text"][4:20], 4, 20, stance="supports")
    hr_contradicted = _hrmod._record(pg, ws, ref="10.1/contradicted")
    _hrmod._link(pg, ws, hr_contradicted, w["work"])
    _use2_id, uv2 = pg.proposal(pg.conn, "use", None,
                               {"work_id": str(w["work"]), "hunt_request_id": str(hr_contradicted)},
                               None, {"statement": "refutes it", "kind": "contradiction",
                                     "status": "refuted"}, None, ws)
    _add_evidence(pg, pg.conn, w, ws, uv2, w["text"][21:40], 21, 40, stance="refutes")

    lines = brief.expected_lines(pg.conn, ws)
    brief._require_every_hunt_request(pg.conn, ws, lines)     # nothing dropped
    by_id = {L["hunt_request_id"]: L for L in lines}
    assert by_id[str(hr_open)]["resolution_state"] == "open"
    assert by_id[str(hr_unconfirmed)]["resolution_state"] == "unconfirmed"
    assert by_id[str(hr_confirmed)]["resolution_state"] == "confirmed"
    assert by_id[str(hr_contradicted)]["resolution_state"] == "contradicted"


# ── gate HB3: the VERIFIED path never reads expected_claim / abstract_passage ───────────────

_FORBIDDEN = ("expected_claim", "abstract_passage")


def _scan(*texts):
    return [c for t in texts for c in _FORBIDDEN if c in t]


def test_verified_sql_never_references_hunt_request_columns():
    """The brief's own VERIFIED call site (added after qc/test_litkb_hunt_request.py's gate 2,
    hence its own scan rather than an extension of that file's list): `_VERIFIED_SQL` and
    `verified_lines`'s own source must never name a hunt_request column."""
    from litkb import brief

    hits = _scan(brief._VERIFIED_SQL, inspect.getsource(brief.verified_lines))
    assert hits == [], f"the VERIFIED path references hunt_request columns: {hits}"


def test_the_scan_itself_catches_a_spliced_in_reference():
    """The kill for the scan above: a live join (not a comment) spliced into a copy of the
    constant must be caught. The real mutation, on the real file, is litkb_p2_mutations.py HB3."""
    from litkb import brief

    spliced = brief._VERIFIED_SQL + (
        "\n  LEFT JOIN litkb.hunt_requests hr ON hr.expected_claim <> ''  -- spliced, not a comment")
    assert _scan(spliced) == ["expected_claim"], "the scan failed to catch a spliced-in reference"
    assert _scan(brief._VERIFIED_SQL) == [], "the UNMUTATED constant must still scan clean"


# ── marking: EXPECTED vs VERIFIED never mix in the rendered text ────────────────────────────


def test_render_never_puts_abstract_passage_in_a_verified_block():
    from litkb import brief

    ws_row = {"id": "ws1", "slug": "s", "state": "open", "purpose": "p"}
    expected = [{"marker": "EXPECTED", "ref": "10.1/x", "ref_scheme": "doi", "claimed_title": None,
                "claimed_authors": None, "claimed_year": None, "expected_claim": "claim text",
                "why_relevant": "why text", "abstract_passage": "SECRET PASSAGE TEXT",
                "work_key": None, "resolution_state": "open"}]
    verified = [{"marker": "VERIFIED", "work_key": "K_2020_x", "statement": "s", "kind": "method",
                "rationale": None, "quote": "the verified quote", "stance": "supports", "page": 3,
                "block_id": "b1"}]
    md = brief.render(ws_row, expected, verified)
    assert "SECRET PASSAGE TEXT" in md
    assert "SECRET PASSAGE TEXT" not in md.split("## Verified", 1)[1]
    assert "UNVERIFIED, never quotable" in md
    assert "OPEN" in md


def test_render_flags_unconfirmed_and_contradicted_explicitly():
    from litkb import brief

    ws_row = {"id": "ws1", "slug": "s", "state": "open", "purpose": "p"}
    base = {"marker": "EXPECTED", "ref_scheme": "doi", "claimed_title": None, "claimed_authors": None,
            "claimed_year": None, "expected_claim": "c", "why_relevant": "w",
            "abstract_passage": None, "work_key": "K"}
    expected = [base | {"ref": "10.1/u", "resolution_state": "unconfirmed"},
                base | {"ref": "10.1/c", "resolution_state": "contradicted"}]
    md = brief.render(ws_row, expected, [])
    assert "UNCONFIRMED" in md
    assert "CONTRADICTED" in md


def test_a_crlf_quote_is_rendered_and_WRITTEN_in_its_canonical_form(tmp_path):
    """G2, and it is the other half of a round trip whose reading half was fixed first.

    Grammar §3's one instruction to a writer is "copy the quote out of the brief". `write` below
    is `write_text`, i.e. universal newline translation on the way OUT, so on Windows every `\\n`
    became `\\r\\n` -- and a quote that already held `\\r\\n` came out as `\\r\\r\\n`. Measured on
    a real brief of `improve-review-1`: 3 occurrences (auditor-3b-stage8-fixes.md §5.4). The
    quote is rendered canonical, so whatever the platform then does to the line endings of the
    FILE, the bytes a writer copies are bytes `review-check` accepts."""
    from litkb import brief
    from litkb.textnorm import canonical_newlines

    quote = "Tent reduces generalization error\r\nfor image classification on corrupted ImageNet"
    ws_row = {"id": "ws1", "slug": "s", "state": "open", "purpose": "p"}
    verified = [{"marker": "VERIFIED", "work_key": "K_2020_x", "statement": "s", "kind": "method",
                 "rationale": None, "quote": quote, "stance": "supports", "page": 3,
                 "block_id": "b1"}]
    assert "\r" not in brief.render(ws_row, [], verified)

    path = brief.write(tmp_path / "b.md", ws_row, [], verified)
    raw = path.read_bytes()
    assert b"\r\r\n" not in raw
    # and what a writer copies out of the file is what the grader canonicalises to
    assert canonical_newlines(quote) in canonical_newlines(raw.decode("utf-8"))


# ── end to end: the CLI command ──────────────────────────────────────────────────────────────


@pg_only
def test_cmd_brief_writes_expected_and_verified(pg, tmp_path):
    from litkb import commands

    w = _evidence_world(pg)
    ws = w["ws"]
    hr = _hrmod._record(pg, ws, ref="10.1/e2e")
    _hrmod._link(pg, ws, hr, w["work"])
    _add_evidence(pg, pg.conn, w, ws, w["uv"], w["text"][4:20], 4, 20, stance="supports")
    out = tmp_path / "brief.md"
    args = argparse.Namespace(workstream=str(ws), out=str(out), dir=str(tmp_path), db="litkb_test")
    rc = commands.cmd_brief(args, pg.conn)
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "EXPECTED" in text and "VERIFIED" in text
    assert "CONFIRMED" in text, "the linked hunt_request has a promotable supporting quote"


@pg_only
def test_cmd_brief_accepts_a_slug(pg, tmp_path):
    from litkb import commands

    ws = pg.ws()
    slug = pg.one("SELECT slug FROM litkb.workstreams WHERE id = %s", (ws,))[0]
    out = tmp_path / "brief.md"
    args = argparse.Namespace(workstream=slug, out=str(out), dir=str(tmp_path), db="litkb_test")
    rc = commands.cmd_brief(args, pg.conn)
    assert rc == 0
    assert out.exists()


@pg_only
def test_cmd_brief_refuses_an_unknown_workstream(pg, tmp_path):
    from litkb import commands

    args = argparse.Namespace(workstream="no-such-workstream", out=str(tmp_path / "b.md"),
                              dir=str(tmp_path), db="litkb_test")
    with pytest.raises(SystemExit, match="no workstream"):
        commands.cmd_brief(args, pg.conn)

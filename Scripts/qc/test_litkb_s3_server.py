"""S3 — the two MCP-server results a caller could not act on: `absent`, and `litkb_acquire`'s detail.

What each group establishes:

  absent_kind    `litkb_work`'s miss rung was ONE answer to three different questions — a work
                 nobody has heard of, a work this very worktree proposed an hour ago, and a work
                 another open workstream is carrying. All three came back `absent` with "admit it"
                 as the next move, and for the second and third of those admitting it again is
                 refused by check 2 as a duplicate identifier. The three are asserted TOGETHER,
                 because the split is only meaningful as a split: the kill is that a work admitted
                 in workstream X, asked from workstream Y, is `in-another-workstream` and never
                 `never-admitted`.
  acquire detail the tool stripped `detail` from what `run.acquire` returned — on exactly the two
                 outcomes that have one — and the per-ROUTE detail was never returned at all,
                 because `attempts` is (route, status) pairs. Both are asserted against a stubbed
                 `acquire` that writes a real attempt row: no network, no file, no route.

These call the server functions directly rather than through an MCP session. The envelope, the
redactors and the tool list are qc/test_litkb_p8.py's subject; what is under test here is the
ladder inside `_work` and `_acquire`, and a round trip would only add a transport to the failure
surface.

Run:
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w8 py -3.12 -m pytest \
        qc/test_litkb_s3_server.py
"""
import json
import uuid
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg


def _jsonb(obj):
    from psycopg.types.json import Jsonb

    return Jsonb(obj)


@pytest.fixture
def env(tmp_path, monkeypatch, litkb_pg_base):
    """A worktree and a literature root under tmp_path, with the throwaway database.

    `litkb_test` stands in for reader and writer — it is a member of both WITH INHERIT FALSE, the
    way the P1, P8 and hunt suites already exercise the roles — so nothing here reaches `litkb`."""
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt),
                 "LITKB_READER_ROLE": "litkb_test", "LITKB_WRITER_ROLE": "litkb_test",
                 "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "s3-server", "LITKB_SESSION": f"s3-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    return {"conn": conn, "wt": wt, "root": root, "tmp": tmp_path}


def _become(conn, wt, slug):
    """Open a workstream and make it THIS worktree's — the token file is rewritten, which is how a
    caller moves from one workstream to another. Returns its id."""
    from litkb import workstream

    p = Path(wt) / workstream.TOKEN_FILE
    if p.exists():
        p.unlink()
    return str(workstream.open_workstream(conn, slug, "test", "S3 absent-kind", directory=wt))


def _call(name, **kw):
    """One server function, its JSON parsed. `_out` has already run both redactors over it."""
    from litkb.mcp import server

    return json.loads(getattr(server, name)(**kw))


def _seed(conn, ws_id, mode, *, doi=None, bind=False):
    """A work (and optionally a DOI identifier and a bound file) in `ws_id`.

    `mode='proposal'` leaves `works.current_version_id` NULL, so main_works does not hold it and
    only that workstream's view does — which is the state every one of the 15 manual proposals on
    live is in (S3 data survey §3). `mode='fact'` promotes it into main."""
    key = f"Seeded_2026_s3-{uuid.uuid4().hex[:8]}"
    work_id, _v = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version(%s, 'work', NULL, %s, NULL, %s, "
        "NULL, %s, 's3-seed', 's3-seed')",
        (mode, _jsonb({"key": key}),
         _jsonb({"type": "article", "title": "A seeded S3 work", "authors": [], "year": 2026,
                 "venue": "Journal of Seeded Works"}), ws_id)).fetchone()
    out = {"key": key, "work_id": str(work_id), "doi": doi}
    if doi:
        conn.execute(
            "SELECT entity_id FROM litkb._write_version(%s, 'identifier', NULL, %s, NULL, %s, "
            "NULL, %s, 's3-seed', 's3-seed')",
            (mode, _jsonb({"scheme": "doi"}),
             _jsonb({"work_id": str(work_id), "value": doi, "verified_by": "manual",
                     "evidence": {}, "status": "active"}), ws_id))
    if bind:
        file_id, _fv = conn.execute(
            "SELECT entity_id, version_id FROM litkb._write_version(%s, 'file', NULL, %s, NULL, "
            "%s, NULL, %s, 's3-seed', 's3-seed')",
            (mode, _jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
             _jsonb({"work_id": str(work_id), "status": "active",
                     "rel_path": "Validation/seeded.pdf", "bytes": 2048, "pages": 3}),
             ws_id)).fetchone()
        out["file_id"] = str(file_id)
    return out


# ── litkb_work: absent, split three ways ──────────────────────────────────────────────────

@pg_only
def test_absent_is_three_answers_and_the_tool_says_which(env):
    """The kill: a work proposed in workstream X, asked from workstream Y, must come back
    `in-another-workstream`. Before the split it came back `never-admitted` with "litkb_admit
    admits it" as the next move — and admission's check 2 then refuses that admission as a
    duplicate identifier, so the caller is told its own knowledge base holds somebody else's work.

    The three kinds are asserted in one test because each is only meaningful against the others:
    the same absent work, read from two different workstreams, has to answer differently."""
    conn = env["conn"]
    ws_x = _become(conn, env["wt"], f"s3-x-{uuid.uuid4().hex[:6]}")
    doi = f"10.5555/s3-{uuid.uuid4().hex[:10]}"
    seeded = _seed(conn, ws_x, "proposal", doi=doi, bind=True)

    mine = _call("_work", key=seeded["key"])
    assert mine["ok"] and mine["found"] is False and mine["state"] == "absent", mine
    assert mine["absent_kind"] == "in-this-workstream", mine
    assert mine["ws_state"] == "bound-unextracted", mine
    assert "check 2" in mine["what_next"], mine

    by_doi = _call("_work", doi=f"https://doi.org/{doi.upper()}")
    assert by_doi["absent_kind"] == "in-this-workstream", by_doi
    assert by_doi["ws_state"] == "bound-unextracted", by_doi

    # the same two questions from a DIFFERENT open workstream
    _become(conn, env["wt"], f"s3-y-{uuid.uuid4().hex[:6]}")
    theirs = _call("_work", key=seeded["key"])
    assert theirs["absent_kind"] == "in-another-workstream", theirs
    assert "ws_state" not in theirs, "another workstream's rung is not readable from here"
    assert ("another workstream holds this identifier; not visible here until Kam merges its "
            "promotion") in theirs["what_next"], theirs
    theirs_doi = _call("_work", doi=doi)
    assert theirs_doi["absent_kind"] == "in-another-workstream", theirs_doi

    never = _call("_work", key=f"Nobody_1999_no-such-work-{uuid.uuid4().hex[:8]}")
    assert never["absent_kind"] == "never-admitted", never
    assert "litkb_admit" in never["what_next"], never
    never_doi = _call("_work", doi=f"10.5555/nothing-{uuid.uuid4().hex[:10]}")
    assert never_doi["absent_kind"] == "never-admitted", never_doi


@pg_only
def test_a_work_main_holds_is_not_absent_at_all(env):
    """The ladder above the miss is untouched: a promoted work still answers `held`, and the miss
    machinery must not reclassify it. Without this the split could be 'right' by making every
    answer a kind of absent."""
    conn = env["conn"]
    ws = _become(conn, env["wt"], f"s3-main-{uuid.uuid4().hex[:6]}")
    seeded = _seed(conn, ws, "fact")
    res = _call("_work", key=seeded["key"])
    assert res["ok"] and res["found"] is True and res["state"] == "held", res
    assert "absent_kind" not in res, res


@pg_only
def test_the_kinds_the_tool_can_answer_are_a_closed_set(env):
    """`absent_kind` is something a caller branches on, so the vocabulary is returned with every
    miss and pinned here: a kind added to the module without a next-move text, or a text without a
    kind, is a caller reading `what_next` for a kind it has never seen."""
    from litkb.mcp import server

    conn = env["conn"]
    _become(conn, env["wt"], f"s3-vocab-{uuid.uuid4().hex[:6]}")
    res = _call("_work", key=f"Nobody_1999_vocab-{uuid.uuid4().hex[:8]}")
    assert set(server._ABSENT_KINDS) == {"never-admitted", "in-this-workstream",
                                         "in-another-workstream"}
    assert res["absent_kinds"] == sorted(server._ABSENT_KINDS), res
    assert all(server._ABSENT_KINDS[k].strip() for k in server._ABSENT_KINDS)


# ── litkb_acquire: the landing detail, and the per-route attempt rows ──────────────────────

@pg_only
def test_acquire_returns_the_landing_detail_and_every_attempt_row(env, monkeypatch):
    """`out = {k: v for k, v in out.items() if k != "detail"}` sat immediately before the return,
    and `run.acquire` sets `detail` on exactly the two outcomes that HAVE one — so the sha256, the
    byte count, the binding verdict, the source URL and the filed path were dropped on the two
    calls that landed a file. The per-ROUTE detail was lost a second way: `attempts` is
    (route, status) pairs and the dict each attempt wrote went only to the database.

    `run.acquire` is stubbed — it writes one real attempt row through the same
    `record_acquisition_attempt` the routes use, and returns the shape the real one returns. No
    route runs, nothing is fetched and no file is written."""
    from litkb.acquire import run

    conn = env["conn"]
    ws = _become(conn, env["wt"], f"s3-acq-{uuid.uuid4().hex[:6]}")
    seeded = _seed(conn, ws, "fact")
    landed = {"sha256": "a" * 64, "bytes": 12345, "binding": "bound",
              "source_url": "https://example.invalid/paper.pdf", "filed": "filed/seeded.pdf"}

    def fake_acquire(c, ws_id, token, work, **kw):
        run.record_attempt(c, ws_id, token, work["work_id"], "open_access",
                           work.get("doi") or work["key"], "no-oa-copy",
                           {"why": "no open-access copy at the registry", "checked": 2})
        run.record_attempt(c, ws_id, token, work["work_id"], "scihub",
                           work.get("doi") or work["key"], "ok", landed)
        return {"outcome": "ok", "attempts": [("open_access", "no-oa-copy"), ("scihub", "ok")],
                "detail": landed}

    monkeypatch.setattr(run, "acquire", fake_acquire)
    res = _call("_acquire", key=seeded["key"])
    assert res["ok"] and res["outcome"] == "ok", res
    assert res["detail"] == landed, "the landing detail is returned whole"
    routes = [(a["route"], a["status"]) for a in res["attempts_detail"]]
    assert routes == [("open_access", "no-oa-copy"), ("scihub", "ok")], res
    assert res["attempts_detail"][0]["detail"]["why"] == "no open-access copy at the registry", res
    assert res["attempts_detail"][1]["detail"]["sha256"] == "a" * 64, res
    assert all(a["at"] for a in res["attempts_detail"]), res


@pg_only
def test_the_attempt_rows_returned_are_this_calls_own(env, monkeypatch):
    """`attempts_detail` is bounded by the DATABASE's clock, read just before the run — not by the
    client's, and not by 'every row this work ever had'. A work with an older attempt must come
    back with the new one only, or the tool reports a route it did not try."""
    from litkb.acquire import run

    conn = env["conn"]
    ws = _become(conn, env["wt"], f"s3-acq2-{uuid.uuid4().hex[:6]}")
    seeded = _seed(conn, ws, "fact")
    from litkb import workstream

    _wsid, token = workstream.load(env["wt"])
    run.record_attempt(conn, ws, token, seeded["work_id"], "annas", seeded["key"],
                       "not-in-archive", {"why": "an attempt from an earlier session"})

    def fake_acquire(c, ws_id, tok, work, **kw):
        run.record_attempt(c, ws_id, tok, work["work_id"], "scihub", work["key"], "blocked",
                           {"why": "a challenge page"})
        return {"outcome": "not-acquired", "attempts": [("scihub", "blocked")]}

    monkeypatch.setattr(run, "acquire", fake_acquire)
    res = _call("_acquire", key=seeded["key"])
    assert [a["route"] for a in res["attempts_detail"]] == ["scihub"], res
    assert res["ok"] is False and res["outcome"] == "not-acquired", res

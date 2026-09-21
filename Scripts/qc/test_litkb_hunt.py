"""`litkb hunt` — the four kills the one-shot entry point has to survive.

TARGETED, AND SAID SO. This is not the P5/P8 treatment: there is no gate here, no round trip
through a real MCP session, and no end-to-end hunt of a real document in the suite. Four things
are asserted, each one a guard that has a mutation row beside it
(`qc/instruments/litkb_p2_mutations.py`, rows H1-H3):

  1. a URL that serves HTML is refused `not-a-pdf`, and the bytes are KEPT in `_quarantine/`
     with a `.reason.json` beside them — never deleted, which is what made the 2026-09-15
     incident unrecoverable rather than merely wrong;
  2. a second hunt of the same URL answers `already-extracted` from the database, having
     fetched nothing: the injected fetch RAISES, so a hunt that reached it fails the test;
  3. a hunt in a worktree with no `.litkb-workstream` is refused before any connection opens;
  4. a DOI hunt for a work that is already extracted returns `extracted` with no new run.

2 and 4 are the same guard read through the two kinds of reference, and they are separate tests
because the identifier LOOKUP is the part that differs — `norm_identifier` treats a DOI and a URL
differently, and a ladder that worked for one and not the other would look like a working ladder.

Run:
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w1 py -3.12 -m pytest qc/test_litkb_hunt.py
"""
import json
import re
import uuid
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

HTML = (b"<!DOCTYPE html>\n<html><head><title>Sign in</title></head>"
        b"<body>You must sign in to download this file.</body></html>\n" + b"x" * 400)


def _jsonb(obj):
    from psycopg.types.json import Jsonb
    return Jsonb(obj)


@pytest.fixture
def env(tmp_path, monkeypatch, litkb_pg_base):
    """A literature root, a worktree with a real workstream, and the throwaway database.

    The `litkb_test` login stands in for reader, writer and ingest — it is a member of all three
    WITH INHERIT FALSE, which is how the P1 and P8 suites already exercise every role without a
    second set of credentials — so nothing here can reach `litkb`."""
    from litkb import workstream
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws_id = workstream.open_workstream(conn, f"hunt-{uuid.uuid4().hex[:8]}", "test", "hunt tests",
                                       directory=wt)
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt),
                 "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "hunt-test", "LITKB_SESSION": f"hunt-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    return {"conn": conn, "root": root, "wt": wt, "ws_id": str(ws_id), "db": c.DB_TEST,
            "tmp": tmp_path}


def _store(env):
    from litkb.acquire.store import Store

    return Store(root=env["root"], index_cache=env["tmp"] / "index.json")


def _hunt(env, ref, **kw):
    from litkb import hunt as H

    return H.hunt(ref, db=env["db"], worktree=env["wt"], agent="hunt-test",
                  session="hunt-test-session", reader_role="litkb_test",
                  writer_role="litkb_test", store=_store(env), derived=str(env["tmp"] / "derived"),
                  **kw)


def seed_extracted(conn, ws_id, scheme, value, *, text="A seeded block.", state="extracted"):
    """A work with an identifier, and — at `state="extracted"` — a bound file, an `ok` run and one
    block. `state="held"` stops after the identifier, which is the rung a DOI reaches when it is
    admitted and no PDF has been found for it.

    Written as FACTS through `_write_version`, the way `qc/test_litkb_p8.py::_seed_work_state`
    does: admission is one work per identifier across the whole knowledge base, and a test that
    admitted its way to this state would be testing admission, not the ladder."""
    key = f"Seeded_2026_hunt-{uuid.uuid4().hex[:8]}"
    work_id, _v = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, "
        "NULL, %s, 'hunt-seed', 'hunt-seed')",
        (_jsonb({"key": key}),
         _jsonb({"type": "report", "title": "A seeded hunt target", "authors": [], "year": 2026}),
         ws_id)).fetchone()
    conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, "
        "NULL, %s, 'hunt-seed', 'hunt-seed')",
        (_jsonb({"scheme": scheme}),
         _jsonb({"work_id": str(work_id), "value": value, "verified_by": "manual",
                 "evidence": {}, "status": "active"}), ws_id))
    if state == "held":
        return {"key": key, "work_id": str(work_id), "file_id": None, "run_id": None}
    file_id, _fv = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, "
        "NULL, %s, 'hunt-seed', 'hunt-seed')",
        (_jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         _jsonb({"work_id": str(work_id), "status": "active", "rel_path": "Validation/seeded.pdf",
                 "bytes": 2048, "pages": 3}), ws_id)).fetchone()
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, '5-reconcile', 'hunt-seed', '0', %s, 'v0', "
        "'local', 'ok') RETURNING id", (file_id, uuid.uuid4().hex[:16])).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                 "VALUES (%s, %s, 1, 'heading', %s)", (file_id, run_id, text))
    return {"key": key, "work_id": str(work_id), "file_id": str(file_id), "run_id": str(run_id)}


def _runs(conn):
    return conn.execute("SELECT count(*) FROM litkb.extraction_runs").fetchone()[0]


# ── kill 1: bytes that are not a PDF ──────────────────────────────────────────────────────

@pg_only
def test_a_url_that_serves_html_is_refused_and_the_bytes_are_quarantined(env):
    """Row H1. The shape check is on the BYTES, before anything reads them as a document.

    Without it the HTML lands under a PDF's name and the admission's check 3 tries to bind a
    title against a first page that does not exist — the 2026-09-15 incident, where 295,657 bytes
    of an error page were written as `IFLA_2017_library-reference-model.pdf` and then `rm -f`'d to
    free the name. Nothing is deleted here: the refusal names where the bytes went and why."""
    url = f"https://example.org/{uuid.uuid4().hex}.pdf"
    # BEFORE/after, never an absolute count: `litkb_test` is reset once per pytest SESSION and every
    # module in it shares the database, so `extraction_runs` is not empty when this test starts and
    # asserting it is measures the module order, not the guard.
    before = _runs(env["conn"])
    res = _hunt(env, url, fetch=lambda u, timeout=180: (200, HTML), key="Html_2026_not-a-paper")
    assert res["ok"] is False and res["refused"] == "not-a-pdf", res
    q = env["root"] / "_quarantine"
    kept = sorted(p.name for p in q.glob("Html_2026_not-a-paper__not-a-pdf__*"))
    assert len(kept) == 2, kept                       # the bytes, and the reason beside them
    why = json.loads(next(q.glob("*.reason.json")).read_text(encoding="utf-8"))
    assert why["shape"] == "not-a-pdf" and why["route"] == "hunt", why
    assert "they look like HTML" in why["reason"], why
    # nothing landed under a name a later pass would read as a paper
    assert not list((env["root"] / "_litkb_staging" / "filed").glob("*")), "an HTML body was filed"
    assert _runs(env["conn"]) == before


# ── kill 2 and 4: the database answers before anything is fetched ─────────────────────────

def _explode(url, timeout=180):
    raise AssertionError(f"a second hunt fetched {url}: the ladder did not short-circuit")


class _NoNet:
    """A registry client that opens no socket, so the mutation that removes the ladder's
    short-circuit (row H2) fails this test OFFLINE instead of querying Crossref for a made-up DOI.
    A mutation harness that reaches the network measures the network."""

    base = ""

    def get(self, url, *a, **kw):
        return 404, {}, b""


@pg_only
def test_a_second_hunt_of_the_same_url_is_already_extracted_and_fetches_nothing(env):
    """Row H2, through a URL. The injected fetch RAISES, so "no new run" is not the whole
    assertion: a hunt that got as far as the network fails outright."""
    url = f"https://example.org/{uuid.uuid4().hex}/doc.pdf"
    seeded = seed_extracted(env["conn"], env["ws_id"], "url", url, text="1 Architecture")
    before = _runs(env["conn"])
    res = _hunt(env, url, fetch=_explode)
    assert res["ok"] is True, res
    assert res["state"] == "extracted" and res["outcome"] == "already-extracted", res
    assert res["work_key"] == seeded["key"] and res["run_id"] == seeded["run_id"], res
    assert res["blocks"] == 1 and res["blocks_by_kind"] == {"heading": 1}, res
    assert res["headings"][0]["text"] == "1 Architecture", res
    assert _runs(env["conn"]) == before, "a second hunt opened an extraction run"


@pg_only
def test_a_doi_hunt_for_an_extracted_work_returns_extracted_with_no_new_run(env):
    """Row H2, through a DOI — the other half of the same guard. The lookup normalises through
    `litkb.norm_identifier`, so the hunted form may differ from the stored one (here a doi.org URL
    against a bare DOI) and still reach the same work."""
    doi = f"10.9999/hunt.{uuid.uuid4().hex[:10]}"
    seeded = seed_extracted(env["conn"], env["ws_id"], "doi", doi)
    before = _runs(env["conn"])
    res = _hunt(env, f"https://doi.org/{doi.upper()}", fetch=_explode, registry_client=_NoNet())
    assert res["ok"] is True and res["state"] == "extracted", res
    assert res["outcome"] == "already-extracted" and res["work_key"] == seeded["key"], res
    assert _runs(env["conn"]) == before


@pg_only
def test_a_doi_hunt_for_a_work_already_held_stops_at_held_and_admits_nothing_again(env):
    """The same guard's third rung, and the one that bites hardest if it is missing: a DOI that is
    ADMITTED with no bound file. Falling through re-admits a work the knowledge base already holds,
    and check 2 refuses it as a DUPLICATE — so a session that hunts the same DOI twice would be
    told, on the second call, that its own work belongs to somebody else. The right answer is the
    state it is in, with the next move (`litkb acquire`) in `refusals`.

    Passes spend=False: this row is about the DUPLICATE-ADMISSION guard, not the spend gate (rows
    below cover that), and a default-spending hunt with no acquirer stub would open a socket."""
    doi = f"10.9999/held.{uuid.uuid4().hex[:10]}"
    seeded = seed_extracted(env["conn"], env["ws_id"], "doi", doi, state="held")
    n = lambda: env["conn"].execute("SELECT count(*) FROM litkb.admissions").fetchone()[0]  # noqa: E731
    before = n()
    res = _hunt(env, doi, fetch=_explode, registry_client=_NoNet(), spend=False)
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-no-spend", res
    assert res["work_key"] == seeded["key"] and res["files"] == [], res
    assert [r["code"] for r in res["refusals"]] == ["no-spend"], res
    assert "--no-spend" in res["refusals"][0]["message"], res
    assert n() == before, "a hunt of an already-held DOI admitted it a second time"


# ── the spend rule (Kam, 2026-09-16 night; decisions.yaml litkb-p0-foundation): a hunt that ─────
# reaches `held` proceeds to acquisition BY DEFAULT; --no-spend / spend=False is the explicit
# exception. Row H5 (qc/instruments/litkb_p2_mutations.py): six DOI hunts died stuck at `held` on
# 2026-09-16 for lack of this rule, and it must fire both ways — a hunt told not to spend must
# never call acquisition, and a hunt that says nothing about it must.

def _acquire_explodes(conn, ws_id, token, work, *, store, agent, session):
    raise AssertionError("acquisition was attempted although spend=False")


def _acquire_recording(calls, outcome="not-acquired", attempts=None):
    def _acquire(conn, ws_id, token, work, *, store, agent, session):
        calls.append({"work_id": work["work_id"], "doi": work.get("doi"), "agent": agent,
                      "session": session})
        return {"outcome": outcome,
                "attempts": attempts or [("open_access", "no-oa-copy"),
                                         ("annas", "not-in-archive"),
                                         ("scihub", "not-in-archive")]}
    return _acquire


@pg_only
def test_no_spend_stops_at_held_and_never_calls_acquisition(env):
    """spend=False is a DELIBERATE, distinct stop: `held-no-spend`, code `no-spend` — never the
    same `held`/`no-file` symptom the six stuck 2026-09-16 hunts left behind, and the acquirer is
    never invoked (it would raise if it were)."""
    doi = f"10.9999/nospend.{uuid.uuid4().hex[:10]}"
    seed_extracted(env["conn"], env["ws_id"], "doi", doi, state="held")
    res = _hunt(env, doi, fetch=_explode, registry_client=_NoNet(), spend=False,
               acquirer=_acquire_explodes)
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-no-spend", res
    assert [r["code"] for r in res["refusals"]] == ["no-spend"], res
    assert "acquisition" not in res, res


@pg_only
def test_default_hunt_spends_by_calling_acquisition(env):
    """The DEFAULT (no `spend` kwarg at all — the CLI's own default): a `held` DOI proceeds to
    acquisition without being asked. The stub records that it was called and reports
    `not-acquired`, so the ladder's next rung (`held-spend-exhausted`) is also asserted."""
    doi = f"10.9999/spend.{uuid.uuid4().hex[:10]}"
    seed_extracted(env["conn"], env["ws_id"], "doi", doi, state="held")
    calls = []
    res = _hunt(env, doi, fetch=_explode, registry_client=_NoNet(),
               acquirer=_acquire_recording(calls))
    assert len(calls) == 1, "the default hunt did not spend: acquisition was never called"
    assert calls[0]["doi"] == doi, calls
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-spend-exhausted", res
    assert [r["code"] for r in res["refusals"]] == ["not-acquired"], res
    assert res["acquisition"]["outcome"] == "not-acquired", res
    assert res["acquisition"]["attempts"], res


def _p2_module():
    """qc/test_litkb_p2.py, loaded by path (it is not a package): `RegistryStub` and `_synthetic`
    build a Crossref-shaped record with no network, exactly as the existing web-source test above
    already does for `front`."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_p2", Path(__file__).with_name("test_litkb_p2.py"))
    p2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p2)
    return p2


@pg_only
def test_a_fresh_doi_admission_with_no_file_also_spends_by_default(env):
    """The OTHER place a hunt reaches `held` with no file: a DOI admitted for the FIRST time by
    this very call (not found already-held in the database). Same guard, the other call site."""
    p2 = _p2_module()
    doi, _title, rec = p2._synthetic()
    stub = p2.RegistryStub({doi: rec})
    calls = []
    res = _hunt(env, doi, fetch=_explode, registry_client=stub,
               acquirer=_acquire_recording(calls))
    assert res.get("admission", {}).get("outcome") == "admitted", res
    assert len(calls) == 1, "a freshly-admitted DOI with no file did not spend"
    assert calls[0]["doi"] == doi, calls
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-spend-exhausted", res


def test_the_cli_default_spends_and_no_spend_threads_through(monkeypatch):
    """Row H6: the CLI's own default. No Postgres, no network — `commands.cmd_hunt` is exercised
    directly with `litkb.hunt.hunt` monkeypatched to capture the `spend` kwarg it was called
    with, so this is a fast unit test rather than a duplicate of the rows above."""
    from litkb import commands as C
    from litkb import hunt as H

    captured = []

    def fake_hunt(ref, **kw):
        captured.append(kw.get("spend"))
        return {"ok": True, "state": "held", "outcome": "held-spend-exhausted", "refusals": []}

    monkeypatch.setattr(H, "hunt", fake_hunt)
    rc1 = C.main(["hunt", "10.1/x"], connect=lambda db: C._NoConn())
    rc2 = C.main(["hunt", "10.1/x", "--no-spend"], connect=lambda db: C._NoConn())
    assert rc1 == 0 and rc2 == 0, (rc1, rc2)
    assert captured == [True, False], captured


def test_the_mcp_wrapper_threads_spend_to_no_spend_and_omits_it_by_default(tmp_path, monkeypatch):
    """Row H7: the MCP tool never re-decides spend, it threads it to the CLI subprocess it shells
    out to. No Postgres — `.litkb-workstream` is a plain JSON file `_session()` reads off disk,
    and `subprocess.run` is monkeypatched so nothing is ever actually launched."""
    from litkb.mcp import server as S

    # the token is armed process-wide by `_session()` -> `add_secret()` (netutil._SECRETS is a
    # module-level list nothing ever clears): a short, common token like "t" redacts every "t" in
    # EVERY later test's output for the rest of the pytest session, not just this test's. A
    # UUID-length token never collides with ordinary text.
    (tmp_path / ".litkb-workstream").write_text(
        json.dumps({"workstream_id": str(uuid.uuid4()), "token": uuid.uuid4().hex}),
        encoding="utf-8")
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = "{}"
            stderr = ""
        return R()

    monkeypatch.setattr(S.subprocess, "run", fake_run)
    S._hunt(ref="10.1/x")
    S._hunt(ref="10.1/x", spend=False)
    assert "--no-spend" not in calls[0], calls[0]
    assert "--no-spend" in calls[1], calls[1]


# ── the acquisition-event contract (S2): one provenance shape, one verifier ───────────────
#
# The URL path lands files through its own function and used to record NOTHING, so a file bound
# that way carried no row saying where it came from. `litkb/acquire/events.py` gives it the route
# path's shape and `bound_without_event` is the verifier both S2 and S5 read. Two rows, and the
# second is the KILL: a gate that has never been shown to fire is not a gate (CLAUDE.md 3.4c).


def _url_hunt(env, *, record=True, monkeypatch=None, title=None, author="Doe", url=None):
    """One clean web-source hunt of a real small PDF, stopping before GROBID/Docling.

    `record=False` makes the event write a no-op for the duration — the known-bad. The no-op goes
    on `hunt._record_acquisition_event`, the OUTER call, so the landing, the binding and the
    admission all happen exactly as before and ONLY the event is lost. That is the end state a
    code path that forgot to record leaves behind, which is what the verifier has to catch.

    The title carries a random suffix because the work KEY is derived from it
    (`front.make_key`): two rows hunting "A Hunted Document" would collide on admission's check 2
    and the second would be refused as a duplicate, which is a different test's subject."""
    p2 = _p2_module()
    p2._need_pdftotext()
    title = title or f"A Hunted Document {uuid.uuid4().hex[:8]}"
    pdf = p2.paper_pdf(title, author)
    if not record:
        from litkb import hunt as H
        monkeypatch.setattr(H, "_record_acquisition_event", lambda *a, **k: None)
    url = url or f"https://example.org/{uuid.uuid4().hex}/paper.pdf"
    res = _hunt(env, url, fetch=lambda u, timeout=180: (200, pdf), extract=False,
                title=title, author=author, year=2020, registry_client=_NoNet())
    return url, res


def _db_now(conn):
    """The freeze instant read off the SERVER, because `file_versions.created_at` defaults to the
    server's `now()`: a Python clock a few microseconds ahead would put the file BEFORE the freeze
    and the verifier would answer about nothing."""
    return conn.execute("SELECT now()").fetchone()[0]


@pg_only
def test_a_url_hunt_records_an_acquisition_event_and_the_verifier_is_clean(env):
    """The contract's good input. A web source lands, binds and is admitted — and afterwards it
    has a row in `litkb.acquisition_attempts` under route `hunt-url` carrying the six documented
    detail keys, and `bound_without_event` for this workstream is EMPTY."""
    from litkb.acquire import events

    since = _db_now(env["conn"])
    url, res = _url_hunt(env)
    assert res["ok"] is True and res["state"] == "bound-unextracted", res
    assert res["acquisition_event"]["ok"] is True, res["acquisition_event"]
    assert res["acquisition_event"]["route"] == "hunt-url", res["acquisition_event"]

    row = env["conn"].execute(
        "SELECT route, identifier_used, status, detail, http_codes, work_id::text "
        "  FROM litkb.acquisition_attempts WHERE id = %s",
        (res["acquisition_event"]["attempt_id"],)).fetchone()
    route, identifier, status, detail, codes, work_id = row
    assert (route, status) == ("hunt-url", "ok"), row
    assert identifier == url and detail["source_url"] == url, row
    assert codes == [200] and detail["http_status"] == 200, row
    assert set(events.DETAIL_KEYS) <= set(detail), sorted(detail)
    assert detail["sha256"] == res["downloaded"]["sha256"], detail
    assert detail["bytes"] == res["downloaded"]["bytes"], detail
    assert re.fullmatch(r"[0-9a-f]{32}", detail["md5"]), detail
    assert detail["filed"] == res["downloaded"]["filed"], detail
    assert work_id == str(res["admission"]["work_id"]), row

    assert events.bound_without_event(env["conn"], env["ws_id"], since) == []


@pg_only
def test_a_url_landing_with_no_acquisition_event_makes_the_verifier_go_red(env, monkeypatch):
    """THE KILL (workplan S2 (c), second clause). The same hunt with the event write removed binds
    exactly the same file — and `bound_without_event` returns that file and only that file.

    The offence names what a reader needs to act: the file, the work it is bound to and the sha256
    no attempt accounts for."""
    from litkb.acquire import events

    since = _db_now(env["conn"])
    _url, res = _url_hunt(env, record=False, monkeypatch=monkeypatch)
    assert res["ok"] is True and res["state"] == "bound-unextracted", res
    assert "acquisition_event" not in res, res

    offences = events.bound_without_event(env["conn"], env["ws_id"], since)
    assert len(offences) == 1, offences
    assert offences[0]["file_id"] == str(res["admission"]["file_id"]), offences
    assert offences[0]["work_id"] == str(res["admission"]["work_id"]), offences
    assert offences[0]["sha256"] == res["downloaded"]["sha256"], offences
    # the file IS bound and IS a web source — the offence is the missing event, nothing else
    assert offences[0]["source_route"] == "web", offences


@pg_only
def test_the_url_of_an_acquisition_event_is_redacted_in_both_columns(env):
    """Row RD19, the redaction family's call site in `events.record_url_landing`.

    `record_attempt` redacts the DETAIL (rows RD14/RD16) and does NOT redact `identifier_used` —
    on the route path that column holds a DOI, which carries no secret. On this path it holds a
    URL, so the redaction happens at the one call site, and this is what makes it fire: a key
    planted in the URL's query string must not reach the column.

    The planted key is 64 random characters. `netutil.add_secret` arms redaction PROCESS-WIDE for
    the rest of the pytest session and nothing ever clears it, so a short or common string would
    mask itself out of every later test's output."""
    from litkb.netutil import add_secret

    secret = "k" + uuid.uuid4().hex + uuid.uuid4().hex
    add_secret(secret)
    url, res = _url_hunt(env, url=f"https://example.org/{uuid.uuid4().hex}/p.pdf?key={secret}")
    assert res["acquisition_event"]["ok"] is True, res.get("acquisition_event")
    identifier, detail = env["conn"].execute(
        "SELECT identifier_used, detail FROM litkb.acquisition_attempts WHERE id = %s",
        (res["acquisition_event"]["attempt_id"],)).fetchone()
    assert secret in url, "the test planted no key"
    assert secret not in identifier and "<KEY>" in identifier, identifier
    assert secret not in json.dumps(detail), detail


@pg_only
def test_a_file_bound_by_hand_with_no_event_is_also_an_offence(env):
    """The other door into the same defect, and the one S5 will see most: a file written straight
    into `file_versions` (here through `_write_version`, as every seed in this module does) with
    no acquisition attempt anywhere. The verifier is about the FILE's provenance, not about which
    function bound it."""
    from litkb.acquire import events

    since = _db_now(env["conn"])
    seeded = seed_extracted(env["conn"], env["ws_id"], "doi",
                            f"10.9999/noevent.{uuid.uuid4().hex[:10]}")
    offences = events.bound_without_event(env["conn"], env["ws_id"], since)
    assert [o["file_id"] for o in offences] == [seeded["file_id"]], offences


# ── kill 3: no workstream token ───────────────────────────────────────────────────────────

def test_a_hunt_with_no_workstream_token_is_refused_before_anything_opens(tmp_path):
    """Row H3. A hunt admits, binds and INGESTS, and all three name an open workstream and present
    its token. The refusal is made before the database, the network and the GPU are touched — the
    order matters, because the other two writes in this package are cheap and this one is not."""
    from litkb import hunt as H

    res = H.hunt("https://example.org/x.pdf", worktree=tmp_path, agent="a", session="s",
                 fetch=_explode, db="litkb_test")
    assert res["ok"] is False and res["refused"] == "no-workstream", res
    assert "ws open" in res["message"], res


@pg_only
@pytest.mark.parametrize("label", ["​​", "﻿", "  ⁠"],
                         ids=["zero_width", "bom", "nbsp_word_joiner"])
def test_a_label_of_invisible_characters_only_is_blank_and_the_hunt_is_refused(env, label):
    """Row H4. Every write records WHICH agent and WHICH session made it, and the manual-admission
    sign-off compares those labels — a web source is exactly such an admission. A label of
    invisible characters is TRUTHY, so a raw check passes it and two sessions can be spelled to
    look like one. The refusal lands before the store, the network and the GPU."""
    from litkb import hunt as H

    res = H.hunt(f"https://example.org/{uuid.uuid4().hex}.pdf", db=env["db"], worktree=env["wt"],
                 agent=label, session=label, reader_role="litkb_test", writer_role="litkb_test",
                 store=_store(env), fetch=_explode)
    assert res["ok"] is False and res["refused"] == "no-labels", res


def test_the_reference_kinds_are_told_apart_by_scheme():
    """A doi.org URL is a DOI, not a web source: the registry can confirm it, and admitting it as a
    manual proposal would put a registry-confirmable work behind a second session's sign-off.

    CHANGED 2026-09-20 (S1): `ref_kind` INFERS and may return None, where it used to CLASSIFY and
    returned 'doi' for anything that was not an http URL. The assertion that moved is
    `http://dx.doi.org/10.1/x`, which this test used to require to be a DOI: `10.1/x` has a
    one-digit registrant prefix and is not a DOI's shape (`^10.\\d{4,9}/\\S+` after normalisation).
    Nothing in the knowledge base carries such a form — it was a stand-in written short. The real
    doi.org form above is asserted unchanged, and the strict shape is what makes `malformed-ref`
    reachable at all."""
    from litkb import hunt as H

    assert H.ref_kind("10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("https://doi.org/10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("http://dx.doi.org/10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("https://raw.githubusercontent.com/a/b/Doc.pdf") == "url"
    assert H.ref_kind("arXiv:2106.15928v2") == "arxiv"
    assert H.ref_kind("math.GT/0309136") == "arxiv"
    assert H.ref_kind("http://dx.doi.org/10.1/x") is None
    assert H.ref_kind("see the attached spreadsheet, row 14") is None


def test_a_web_source_with_a_pdf_binds_the_pdf_and_keeps_the_snapshot(tmp_path):
    """`admit_web(pdf_path=…)` binds the DOCUMENT, not the saved page text.

    The evidence has to arrive with the admission: a manual admission is a proposal, main's
    pointer stays NULL until a second session approves it, and `litkb.attach_file` refuses a work
    that is not in main — so "admit the proposal, then acquire --from-file" cannot complete for a
    web source. This checks the Python half of that (the file JSON the admission is handed); the
    database half is migration 0013's own text."""
    import importlib.util

    from litkb.admit import front

    spec = importlib.util.spec_from_file_location("_p2", Path(__file__).with_name("test_litkb_p2.py"))
    p2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p2)
    root = tmp_path / "Literture"
    (root / "_litkb_staging" / "filed").mkdir(parents=True)
    pdf = root / "_litkb_staging" / "filed" / "Doe_2020_a-hunted-document.pdf"
    pdf.write_bytes(p2.paper_pdf("A Hunted Document", "Doe"))
    ev = front.web_pdf_evidence(pdf, "A Hunted Document", "Doe", url="https://example.org/d.pdf",
                                retrieved="2026-09-16", root=root)
    assert ev["binding"]["verdict"] == "bound", ev["binding"]
    assert ev["has_text_layer"] is True and ev["source_route"] == "web"
    assert ev["source_url"] == "https://example.org/d.pdf"
    assert ev["obtained_at"] == "2026-09-16"
    assert ev["rel_path"].endswith("Doe_2020_a-hunted-document.pdf")
    # 0020's copy_kind vocabulary is publisher / author manuscript / preprint / scan /
    # web snapshot; a PDF served from a project's own repository is none of them, and claiming
    # one would be a claim nothing measured
    assert "copy_kind" not in ev, ev


# ── the reference SHAPES (S1, 2026-09-20): every drop-off ends in a named result ───────────
#
# `ref_kind` used to CLASSIFY — http was a URL, anything else was a DOI — so a title, an ISBN and
# a typo were all handed to `admit_registry` and died at `AdmissionError("… is not a DOI")` or at
# a registry call for a string nobody meant as an identifier. A lit-scout drops off every one of
# those shapes. It now VALIDATES, and `qc/fixtures/litkb_ref_shapes.json` is the table of what
# each shape must end in. Rows HS1-HS6 of qc/instruments/litkb_p2_mutations.py mutate the guards
# these drive.
#
# NOTHING HERE OPENS A SOCKET: `fetch`, `registry_client` and the title resolver's client are all
# injected, and the `explode` fetch fails the test outright if a row reaches the network.

def _fixture(name):
    return json.loads((Path(__file__).with_name("fixtures") / name).read_text(encoding="utf-8"))


def _shapes():
    return _fixture("litkb_ref_shapes.json")["rows"]


def _title_gate():
    return _fixture("litkb_title_gate_wrong_work.json")


class _CrossrefSearchStub:
    """The frozen Crossref SEARCH response for `query.bibliographic`, and 404 for everything else.

    Semantic Scholar and arXiv therefore return no candidates at all, which is what makes an
    assertion about the frozen Crossref candidate an assertion about THAT candidate."""

    base = ""

    def __init__(self, body):
        self.body = body
        self.calls = []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        if "api.crossref.org/works?" in url:
            return 200, {}, self.body
        return 404, {}, b""


def _no_wait_pacer():
    from litkb.netutil import Pacer

    return Pacer(interval=0, sleep=lambda s: None)


def _token(env):
    return json.loads((env["wt"] / ".litkb-workstream").read_text(encoding="utf-8"))["token"]


@pg_only
@pytest.mark.parametrize("row", _shapes(), ids=[r["id"] for r in _shapes()])
def test_ref_shapes_each_end_in_a_named_result(env, row):
    """One row of qc/fixtures/litkb_ref_shapes.json, driven through `hunt()`.

    The fixture's `why` field says what each row protects; it is not repeated here, because a
    restated reason is a reason that rots (CLAUDE.md §3.3)."""
    kw = dict(row.get("inputs") or {})
    if row.get("seed"):
        s = row["seed"]
        # SEED ONLY IF ABSENT. `title` and `title-by-request-id` resolve to the SAME DOI —
        # deliberately, because they are two routes to one work — and admission is one work per
        # identifier across the whole knowledge base, so seeding it twice hits
        # `identifiers_active_scheme_value`. The check also keeps either row runnable ALONE: it
        # seeds when nothing is there and reuses when the other row already ran.
        exists = env["conn"].execute(
            "SELECT 1 FROM litkb.ws_identifiers WHERE view_workstream_id = %s AND scheme = %s "
            "  AND status = 'active' AND value_norm = litkb.norm_identifier(%s, %s)",
            (env["ws_id"], s["scheme"], s["scheme"], s["value"])).fetchone()
        if not exists:
            seed_extracted(env["conn"], env["ws_id"], s["scheme"], s["value"], state=s["state"])
    if row["fetch"] == "explode":
        kw["fetch"] = _explode
    elif row["fetch"] == "html":
        kw["fetch"] = lambda u, timeout=180: (200, HTML)
    else:
        p2 = _p2_module()
        p2._need_pdftotext()
        pdf = p2.paper_pdf(kw.get("title") or "A Hunted Document", kw.get("author") or "Doe")
        kw["fetch"] = lambda u, timeout=180: (200, pdf)
    if row["registry"] == "title_gate":
        kw["registry_client"] = _CrossrefSearchStub(
            json.dumps(_title_gate()["crossref_search_body"]).encode("utf-8"))
        kw["pacer"] = _no_wait_pacer()
    else:
        kw["registry_client"] = _NoNet()
    if row.get("hunt_request"):
        from litkb import hunt_request as HR
        hr = row["hunt_request"]
        kw["hunt_request_id"] = str(HR.record(
            env["conn"], env["ws_id"], _token(env), ref=row["ref"],
            ref_scheme=hr["ref_scheme"], expected_claim="a drop-off hunted by its id",
            why_relevant=row["id"], claimed_title=hr.get("claimed_title"),
            claimed_authors=hr.get("claimed_authors"), claimed_year=hr.get("claimed_year"),
            agent="hunt-test", session="hunt-test-session"))

    res = _hunt(env, row["ref"], ref_scheme=row["ref_scheme"], **kw)

    want = row["expect"]
    assert res["ok"] is want["ok"], res
    assert res["ref_kind"] == want["ref_kind"], res
    if want.get("filled"):
        assert res["from_hunt_request"]["filled"] == want["filled"], res
    if want.get("first_author"):
        assert res["from_hunt_request"]["first_author"] == want["first_author"], res
    if want["ok"]:
        assert res["state"] == want["state"], res
        assert res["outcome"] == want["outcome"], res
        if want.get("resolved_doi"):
            assert res["resolved"]["doi"] == want["resolved_doi"], res
    else:
        assert res["refused"] == want["refused"], res
        assert res["message"], res
        if want.get("message_names"):
            assert want["message_names"] in res["message"], res
        if want.get("ref_scheme"):
            assert res.get("ref_scheme") == want["ref_scheme"], res


@pg_only
def test_ref_shapes_a_garbage_reference_is_malformed_ref_and_never_a_doi(env):
    """(c) item 1, asserted on its own rather than only inside the table above, because what it
    rules out is SILENT: the old code produced a perfectly ordinary-looking result whose
    `ref_kind` read `doi` for a sentence out of a spreadsheet."""
    from litkb import hunt as H

    res = _hunt(env, "see the attached spreadsheet, row 14", fetch=_explode,
                registry_client=_NoNet())
    assert res["ok"] is False and res["refused"] == "malformed-ref", res
    assert res["ref_kind"] is None and res["ref_kind"] != "doi", res
    assert H.ref_kind("see the attached spreadsheet, row 14") is None


@pg_only
def test_ref_shapes_an_isbn_is_unsupported_and_never_a_traceback(env):
    """(c) item 2. `isbn` is IN the recordable vocabulary (a scout may drop one off) and is not a
    scheme a hunt can follow; those are different facts, and the refusal says which."""
    res = _hunt(env, "978-0-13-110362-7", ref_scheme="isbn", fetch=_explode,
                registry_client=_NoNet())
    assert res["ok"] is False and res["refused"] == "unsupported-ref-scheme", res
    assert res["refused"] != "error", "an unsupported scheme became a traceback"
    assert "S3" in res["message"], res


def test_ref_shapes_a_scheme_outside_the_vocabulary_is_named_not_guessed():
    """`unknown-ref-scheme` and `unsupported-ref-scheme` answer different questions: "no such
    scheme" and "a scheme litkb records but cannot chase". No database, no network."""
    from litkb import hunt as H
    from litkb.hunt_request import REF_SCHEMES

    with pytest.raises(H.HuntRefused) as e:
        H.validate_ref("x", "bibtex")
    assert e.value.code == "unknown-ref-scheme", e.value.code
    assert all(s in e.value.message for s in ("doi", "title", "isbn")), e.value.message
    assert set(H.HUNTABLE) < set(REF_SCHEMES), (H.HUNTABLE, REF_SCHEMES)


# ── the identity gate: a WRONG work scoring just under the ratio (S1 done-state (c) item 3) ──

def test_a_wrong_work_scoring_just_under_the_ratio_is_refused():
    """A frozen, real Crossref response whose top candidate scores 0.83 against the title being
    resolved — a WRONG work, a sibling volume — is refused by gate 0.

    THE PROOF IS THE TEST BELOW. A gate that has never been shown to fire is not known to work
    (CLAUDE.md §3.4c): with `RESOLVE_TITLE_RATIO` lowered from 0.85 to 0.80 the identical call
    returns that wrong work's DOI, so this test goes RED.

    THE RATIO IS ISOLATED, deliberately. `judge_candidate` refuses on the title ratio OR the
    first-author family name OR the year, so the surname and year passed in are taken from the
    CANDIDATE'S OWN record (Plackett / 1975): both of those checks PASS and the ratio is the only
    check that can refuse. Without that, lowering the ratio would change nothing and this would
    be a test of the year rule wearing the ratio's name.

    THE SENT STRING AND THE RESOLVED STRING ARE THE SAME STRING, which is what makes the capture
    usable as evidence at all: `qc/fixtures/litkb_title_gate_wrong_work.json` freezes the exact
    request URL, the verbatim response, its sha256 and the fetch time, and its `resolved_title`
    IS its `_provenance.query_sent`. A fixture whose query differed from the title under test
    would record an interaction that never happened. No network here: the frozen body is served
    for Crossref and 404 for Semantic Scholar and arXiv."""
    from litkb.admit import resolver as R

    fx = _title_gate()
    stub = _CrossrefSearchStub(json.dumps(fx["crossref_search_body"]).encode("utf-8"))
    doi, source, evidence = R.resolve_doi(fx["resolved_title"], fx["surname"], fx["year"],
                                          stub, _no_wait_pacer())
    assert doi is None, f"a wrong work scoring under the ratio was admitted: {doi} ({evidence})"
    assert source is None, (source, evidence)
    assert evidence == fx["expected"]["at_ratio_0_85"]["reason"], evidence


def test_every_refusal_code_this_module_raises_is_listed():
    """The closed vocabulary is enforced against the SOURCE, not maintained by memory: every
    string literal handed to `HuntRefused(...)` in hunt.py must be in REF_REFUSALS or
    HUNT_REFUSALS, and the two dynamic sites (the title code, the pdf shape) are accounted for by
    name. The first scout run scored a legitimate `admission-refused` as `unknown_states` because
    nothing listed it (2026-09-20)."""
    import ast
    import pathlib

    from litkb import hunt as H

    src = pathlib.Path(H.__file__).read_text(encoding="utf-8")
    listed = set(H.REF_REFUSALS) | set(H.HUNT_REFUSALS)
    assert not (set(H.REF_REFUSALS) & set(H.HUNT_REFUSALS))
    literals, dynamic = set(), []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "HuntRefused" and n.args:
            a = n.args[0]
            if isinstance(a, ast.Constant):
                literals.add(a.value)
            else:
                dynamic.append(ast.unparse(a))
    assert literals <= listed, sorted(literals - listed)
    # the two dynamic sites: `code` (unresolved-title / ambiguous-title) and the pdf shape
    assert sorted(dynamic) == sorted(["code", "'not-a-pdf' if shape == 'not-a-pdf' else shape"]), dynamic
    assert {"unresolved-title", "ambiguous-title", "not-a-pdf", "truncated-pdf"} <= listed


def test_the_frozen_body_matches_its_recorded_hash():
    """The fixture's provenance is ENFORCED, not narrated. The S1 audit (2026-09-20) found the
    original `response_sha256` was of the raw wire bytes, which the file does not store, so no
    test could ever check it; `stored_body_sha256` hashes what the file holds, by the rule the
    fixture states, and the identity the docstring above relies on (sent == resolved) is asserted
    here rather than read off by an auditor."""
    import hashlib

    fx = _title_gate()
    pv = fx["_provenance"]
    assert fx["resolved_title"] == pv["query_sent"]
    canon = json.dumps(fx["crossref_search_body"], sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")
    assert hashlib.sha256(canon).hexdigest() == pv["stored_body_sha256"]


def test_the_same_wrong_work_is_admitted_once_the_ratio_is_lowered(monkeypatch):
    """The kill for the test above. If this ever stops holding, that assertion is passing for a
    reason that is not the ratio gate and its RED proof is void."""
    from litkb.admit import resolver as R

    fx = _title_gate()
    monkeypatch.setattr(R, "RESOLVE_TITLE_RATIO", 0.80)
    stub = _CrossrefSearchStub(json.dumps(fx["crossref_search_body"]).encode("utf-8"))
    doi, source, _ev = R.resolve_doi(fx["resolved_title"], fx["surname"], fx["year"],
                                     stub, _no_wait_pacer())
    assert doi == fx["expected"]["at_ratio_0_80"]["doi"], doi
    assert source == fx["expected"]["at_ratio_0_80"]["source"], source


# ── hunt_request precedence: the drop-off's own scheme outranks an explicit one ────────────

@pg_only
def test_the_drop_offs_own_scheme_wins_and_a_disagreeing_one_is_refused(env):
    """A hunt following up a drop-off takes the scheme from the ROW. An explicit `ref_scheme` that
    disagrees is `ref-scheme-mismatch` rather than a silent override: the drop-off is the record
    of what the scout meant, and linking a work to an expectation written about a DIFFERENT
    reference is the one thing migration 0023 exists to prevent."""
    from litkb import hunt_request as HR

    doi = f"10.9999/precedence.{uuid.uuid4().hex[:10]}"
    seeded = seed_extracted(env["conn"], env["ws_id"], "doi", doi)
    hr = HR.record(env["conn"], env["ws_id"], _token(env), ref=doi, ref_scheme="doi",
                   expected_claim="the precedence rule holds", why_relevant="row HS3",
                   agent="hunt-test", session="hunt-test-session")
    bad = _hunt(env, doi, hunt_request_id=str(hr), ref_scheme="url", fetch=_explode,
                registry_client=_NoNet())
    assert bad["ok"] is False and bad["refused"] == "ref-scheme-mismatch", bad
    assert bad["request_ref_scheme"] == "doi" and bad["given_ref_scheme"] == "url", bad

    ok = _hunt(env, doi, hunt_request_id=str(hr), fetch=_explode, registry_client=_NoNet())
    assert ok["ok"] is True and ok["ref_kind"] == "doi", ok
    assert ok["work_key"] == seeded["key"], ok
    assert ok["hunt_request"]["ok"] is True, ok


@pg_only
def test_ref_shapes_an_explicit_argument_beats_the_drop_offs_claimed_fields(env):
    """Row HS5c, the other side of the fill rule. The ROW fills what the caller left EMPTY; it
    never overrides what the caller said. A scout mis-types a surname and a year, a session
    corrects them on the command line — and the correction has to be reachable.

    The proof is not "the result mentions the right surname": it is that the hunt RESOLVES at all.
    Gate 0 refuses on the first-author family name, so with the precedence inverted the row's
    `Nobodyson` / 1902 reach `judge_candidate`, every candidate is refused on author and year, and
    the hunt comes back `ambiguous-title` instead of reaching the seeded work."""
    from litkb import hunt_request as HR

    fx = _title_gate()
    title = fx["expected"]["top_candidate_title"]
    hr = HR.record(env["conn"], env["ws_id"], _token(env), ref=title, ref_scheme="title",
                   expected_claim="an explicit argument beats the row",
                   why_relevant="row HS5c", claimed_authors="Nobodyson, Q.",
                   claimed_year=1902, agent="hunt-test", session="hunt-test-session")
    exists = env["conn"].execute(
        "SELECT 1 FROM litkb.ws_identifiers WHERE view_workstream_id = %s AND scheme = 'doi' "
        "  AND status = 'active' AND value_norm = litkb.norm_identifier('doi', %s)",
        (env["ws_id"], fx["expected"]["top_candidate_doi"])).fetchone()
    if not exists:
        seed_extracted(env["conn"], env["ws_id"], "doi", fx["expected"]["top_candidate_doi"])
    res = _hunt(env, title, hunt_request_id=str(hr), author=fx["surname"], year=fx["year"],
                fetch=_explode, pacer=_no_wait_pacer(),
                registry_client=_CrossrefSearchStub(
                    json.dumps(fx["crossref_search_body"]).encode("utf-8")))
    assert res["ok"] is True, res
    assert res["resolved"]["doi"] == fx["expected"]["top_candidate_doi"], res
    # the row filled NOTHING: both fields the caller gave explicitly
    assert "from_hunt_request" not in res or res["from_hunt_request"]["filled"] == [], res


@pg_only
def test_the_mcp_drop_off_names_an_unknown_scheme_instead_of_raising_the_database_at_the_caller(
        env, monkeypatch):
    """Row HS8. Until 2026-09-20 an unrecognised `ref_scheme` reached the table's CHECK and came
    back as the ordinary `error` shape carrying a raw PL/pgSQL constraint sentence — which an
    unattended scout cannot act on, and which does not say what the vocabulary IS.

    The second half is the half that would rot: the scheme migration 0027 ADDED must be accepted
    here. A Python constant left behind would refuse `title` at the MCP layer against a database
    that accepts it, and the scout's first title drop-off would die of a stale list."""
    from litkb.mcp import server as S

    monkeypatch.setattr(S, "_role", lambda kind: "litkb_test", raising=False)
    res = json.loads(S._hunt_request_add(ref="x", ref_scheme="bibtex", expected_claim="c",
                                         why_relevant="w"))
    assert res["ok"] is False and res["refused"] == "unknown-ref-scheme", res
    assert "title" in res["message"] and "doi" in res["message"], res
    ok = json.loads(S._hunt_request_add(ref="A Title", ref_scheme="title", expected_claim="c",
                                        why_relevant="w"))
    # `ok is True`, not merely "not refused for THIS reason": the weaker assertion would pass on
    # any other refusal, a database error included, and would be green for the wrong reason
    assert ok["ok"] is True, ok
    assert ok["resolution_state"] == "open", ok


@pg_only
def test_the_cli_drop_off_names_an_unknown_scheme_before_it_writes(env):
    """Row HS9, the other entry point. `commands.main` is driven with a `_NoConn`, so the refusal
    must land before anything touches the connection — a scheme that reached `_hr.record` would
    raise RuntimeError from that stub instead of SystemExit."""
    from litkb import commands as C

    with pytest.raises(SystemExit) as e:
        C.main(["--dir", str(env["wt"]), "hunt-request", "add", "--ref", "x",
                "--ref-scheme", "bibtex", "--expected-claim", "c", "--why-relevant", "w"],
               connect=lambda db: C._NoConn())
    assert "bibtex" in str(e.value) and "title" in str(e.value), str(e.value)

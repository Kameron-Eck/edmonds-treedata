"""S4.5 builder C1a — the acquisition ledger's vocabulary and substrate (migration 0033; LITKB_WORKPLAN.md
"### S4.5" items 1 and 2).

  vocabulary   0033's CHECKs are exactly litkb.acquire.policy's tuples (one Python home); a sub-status belongs
               to its status; a skip or a budget stop always says why; a live row's basis is `live`
  writers      record_route_backoff needs the token and the caller's own attempt, and an older attempt never
               rolls the ladder back; a retry names an attempt of the same work, route and workstream
  the ladder   a skip is an attempt with a reason (guard 14); `blocked` is dead within a run and the persisted
               refusal ladder governs across runs (guard 2) — never per host (guard 29); a transient answer gets
               one scheduled retry named as one; the budget stops the ladder with a row (guard 12); the
               policy is one switch and the shadow tier waits for every legitimate miss (guard 21); Stage B runs
               concurrently; MEASURE mode lands nothing (S4.5 decision D9); the rejected-hash lookup matches by
               content; a challenge page is one at ANY status; every attempt carries its served sha, terminal
               facts, retriable and kind; Unpaywall goes through the client and its email never reaches the ledger
  typing       the blocked classifier on E13's REAL recorded page; the reviewed backfills (dry run by default,
               fill-null only, one decision-log row)
  fires        every C1a fire in qc/instruments/litkb_hardening_c1a.py FIRES, control inside the bound and the
               known-bad outside it (the same run functions builder A's `hardening` loads by path)

No test touches the network: every route is a stub client; the Unpaywall email is a constructed address.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w7 py -3.12 -m pytest qc/test_litkb_ledger.py -q
"""
import csv
import datetime
import hashlib
import importlib.util
import json
import re
import time
import urllib.parse
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
pg_only = pytest.mark.requires_litkb_pg
E13_PAGE = SCRIPTS / "qc" / "fixtures" / "litkb_e13_challenge_b65a33b17354.html"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2M = _load("_litkb_p2_for_ledger", SCRIPTS / "qc" / "test_litkb_p2.py")
C1A = _load("_litkb_hardening_c1a", SCRIPTS / "qc" / "instruments" / "litkb_hardening_c1a.py")


@pytest.fixture
def pg(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    h = P2M.P2(psycopg, conn)
    yield h
    while h.opened:
        h.opened.pop().close()


@pytest.fixture(autouse=True)
def _no_email(monkeypatch):
    """No test reads Kam's Unpaywall email: every lookup is asked with a constructed address."""
    from litkb.acquire import open_access
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "c1a-test@example.invalid")


def _store(tmp_path):
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def _acq(pg, w, ws, work, store, clients, **kw):
    from litkb.acquire import run
    kw.setdefault("pacing", {})
    return run.acquire(w, ws, pg.tokens[ws], work, store=store, agent="c1a", session="c1a-1", clients=clients,
                       pacer=P2M._nopace(), printer=lambda *a, **k: None, **kw)


def _rows(pg, wid):
    return pg.conn.execute(
        "SELECT id::text, route, status, sub_status, sub_status_basis, served_sha256, terminal_url, "
        "terminal_status_code, terminal_dt, retriable, kind, retry_of::text, detail, http_codes, workstream_id::text "
        "FROM litkb.acquisition_attempts WHERE work_id = %s ORDER BY at, id", (wid,)).fetchall()


def _unpaywall(*urls, version=None):
    loc = [{"url": u, "host_type": "publisher", **({"version": version} if version else {})} for u in urls]
    return 200, {}, json.dumps({"is_oa": True, "oa_status": "bronze", "best_oa_location": loc[0] if loc else None,
                                "oa_locations": loc}).encode()


def _e13():
    data = E13_PAGE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == C1A.E13_SHA256, "the recorded E13 page is not the bytes served"
    return data


# ── vocabulary ───────────────────────────────────────────────────────────────────────────────────
def _check_words(pg, table, name):
    d = pg.one("SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c WHERE c.conname = %s "
               "AND c.conrelid = %s::regclass", (name, f"litkb.{table}"))[0]
    return set(re.findall(r"'([^']+)'", d))


@pg_only
def test_the_0033_checks_are_the_python_vocabularies(pg):
    from litkb.acquire import policy as P

    assert _check_words(pg, "acquisition_attempts", "acquisition_attempts_route_check") == set(P.ROUTES_ALL)
    assert _check_words(pg, "route_backoff", "route_backoff_route_check") == set(P.ROUTES_ALL)
    assert set(P.NEW_STATUSES) <= _check_words(pg, "acquisition_attempts", "acquisition_attempts_status_check")
    subs = {s for v in P.SUB_STATUSES.values() for s in v}
    assert _check_words(pg, "acquisition_attempts", "acquisition_attempts_sub_status_check") == subs | set(P.SUB_STATUSES)
    assert _check_words(pg, "acquisition_attempts", "acquisition_attempts_kind_check") == set(P.KINDS)
    assert _check_words(pg, "acquisition_attempts", "acquisition_attempts_sub_status_basis_check") == set(P.SUB_STATUS_BASES)
    assert set(P.STAGE_OF) <= set(P.ROUTES_ALL) and set(P.STAGE_OF.values()) == set(P.STAGES)
    # the CONTRACTS lists, verbatim (S4.5 brief-CONTRACTS.md)
    assert P.BAD_FILE_SUBS == ("html_response", "too_small", "missing_pdf_header", "corrupt_pdf_header",
                               "early_eof_with_trailing_payload", "stub_not_article", "volume_not_article",
                               "cited_document_not_this_article", "compressed_or_archived_payload")
    assert P.BLOCKED_SUBS == ("identity_required", "challenge_or_bot_check", "not_found", "html_or_reader")
    assert P.NOT_IN_ARCHIVE_SUBS == ("not_in_corpus", "no_pdf_link")


@pg_only
def test_a_sub_status_belongs_to_its_status_and_a_skip_says_why(pg):
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    tok, wid = pg.tokens[ws], work["work_id"]
    for status, sub, route in (("bad-file", "challenge_or_bot_check", "open_access"), ("skipped", None, "annas"),
                               ("ok", None, "ladder"), ("blocked", "not_in_corpus", "scihub"),
                               ("ok", "html_response", "open_access")):
        with pytest.raises(pg.errors.CheckViolation):
            run.record_attempt(w, ws, tok, wid, route, None, status, {}, sub_status=sub)
    with pytest.raises(pg.errors.CheckViolation):
        run.record_attempt(w, ws, tok, wid, "open_access", None, "blocked", {}, served_sha256="XYZ")
    aid = run.record_attempt(w, ws, tok, wid, "scihub", None, "blocked", {}, sub_status="challenge_or_bot_check")
    assert pg.one("SELECT sub_status, sub_status_basis FROM litkb.acquisition_attempts WHERE id = %s",
                  (aid,)) == ("challenge_or_bot_check", "live")


@pg_only
def test_a_retry_names_an_attempt_of_the_same_work_route_and_workstream(pg):
    from litkb.acquire import run

    ws, other, w = pg.ws(), pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    first = run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", None, "bad-file", {}, [503])
    for bad in ((ws, "scihub"), (other, "open_access")):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            run.record_attempt(w, bad[0], pg.tokens[bad[0]], work["work_id"], bad[1], None, "bad-file", {}, [503],
                               retry_of=first)
    again = run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", None, "bad-file", {}, [503],
                               retry_of=first)
    assert pg.one("SELECT retry_of::text FROM litkb.acquisition_attempts WHERE id = %s", (again,))[0] == str(first)


@pg_only
def test_record_route_backoff_needs_the_token_and_the_callers_own_attempt(pg):
    from litkb.acquire import backoff as B
    from litkb.acquire import run

    ws, other, w = pg.ws(), pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    aid = run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", None, "blocked", {}, [403],
                             sub_status="challenge_or_bot_check")
    at = pg.one("SELECT at FROM litkb.acquisition_attempts WHERE id = %s", (aid,))[0]
    state = B.BackoffPolicy().step(None, "blocked", [403], at)
    for tok in (None, "", pg.tokens[other]):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            B.save(w, ws, tok, aid, state)
    with pytest.raises(pg.errors.InsufficientPrivilege):          # an attempt of ANOTHER workstream
        B.save(w, other, pg.tokens[other], aid, state)
    B.save(w, ws, pg.tokens[ws], aid, state)
    assert B.load(w, "open_access", work["work_id"])["refusals"] == 1
    later = run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", None, "blocked", {}, [403],
                               sub_status="challenge_or_bot_check")
    at2 = pg.one("SELECT at FROM litkb.acquisition_attempts WHERE id = %s", (later,))[0]
    B.save(w, ws, pg.tokens[ws], later, B.BackoffPolicy().step(state, "blocked", [403], at2))
    B.save(w, ws, pg.tokens[ws], aid, state)                        # the OLDER attempt: never rolls it back
    assert B.load(w, "open_access", work["work_id"])["refusals"] == 2


# ── the ladder ───────────────────────────────────────────────────────────────────────────────────
@pg_only
def test_a_skip_is_an_attempt_with_a_reason(pg, tmp_path):
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = dict(P2M._admitted(pg, w, ws), doi=None, arxiv=None)
    out = _acq(pg, w, ws, work, _store(tmp_path), {})
    rows = _rows(pg, work["work_id"])
    assert [(r[1], r[2], r[3]) for r in rows] == [
        ("open_access", "skipped", "no_identifier"), ("annas", "skipped", "no_identifier"),
        ("scihub", "skipped", "no_identifier"), ("browser", "manual-step", None)], rows
    assert out["outcome"] == "not-acquired"
    assert [d["status"] for d in out["route_detail"]] == ["skipped", "skipped", "skipped"]


def _e13_clients():
    """E13's two answers: open access -> doi.org 403 with E13's REAL recorded Cloudflare page; every Sci-Hub
    mirror -> a 403 whose body is a CONSTRUCTED minimal "Just a moment..." page (the challenge's title, not a
    recording)."""
    return {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://doi.org/10.1145/x"),
                                          "doi.org/": (403, {}, _e13())}),
            "scihub": P2M.RouteStub({"sci-hub": (403, {}, b"<html><title>Just a moment...</title></html>")})}


@pg_only
def test_blocked_is_dead_within_a_run_and_the_backoff_governs_across_runs(pg, tmp_path):
    from litkb.acquire import backoff as B

    ws1, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws1)
    store = _store(tmp_path)
    _acq(pg, w, ws1, work, store, _e13_clients(), routes=("scihub",))
    _acq(pg, w, ws1, work, store, _e13_clients(), routes=("scihub",))          # the same run
    ws2 = pg.ws()
    _acq(pg, w, ws2, work, store, _e13_clients(), routes=("scihub",))          # the next run
    ws3 = pg.ws()
    _acq(pg, w, ws3, work, store, _e13_clients(), routes=("scihub",), retry_dead=True)   # forced
    got = [(r[1], r[2], r[3]) for r in _rows(pg, work["work_id"]) if r[1] == "scihub"]
    assert got == [("scihub", "blocked", "challenge_or_bot_check"), ("scihub", "skipped", "dead_in_run"),
                   ("scihub", "skipped", "backoff_window"), ("scihub", "blocked", "challenge_or_bot_check")], got
    state = B.load(pg.conn, "scihub", work["work_id"])
    assert state["refusals"] == 2, state
    gap = (state["next_allowed_at"] - pg.one("SELECT max(at) FROM litkb.acquisition_attempts WHERE work_id = %s "
                                               "AND status = 'blocked'", (work["work_id"],))[0]).total_seconds()
    assert gap == B.REFUSAL_LADDER_S[1], gap          # the second refusal inside the window: the 6 h rung


@pg_only
def test_one_403_never_suppresses_the_host_for_another_work(pg, tmp_path):
    """Guard 29: MDPI answers 403 PER ARTICLE. Work A's refusal on a host leaves work B's attempt on the same
    host and route free to be asked. The Akamai "Access Denied" page is CONSTRUCTED in the shape of the four MDPI
    pages kept on the live store (not a recording)."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    a, b = P2M._admitted(pg, w, ws), P2M._admitted(pg, w, ws)
    akamai = (b"<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY>You don't have permission to access "
              b"\"http://www.mdpi.com/x/pdf\" on this server.<P>Reference #18.1 <P>https://errors.edgesuite.net/"
              + uuid.uuid4().hex.encode() + b"</BODY></HTML>")
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://www.mdpi.com/x/pdf"),
                                          "www.mdpi.com": (403, {}, akamai)})}
    _acq(pg, w, ws, a, _store(tmp_path), stub, routes=("open_access",))
    _acq(pg, w, ws, b, _store(tmp_path), stub, routes=("open_access",))
    ra, rb = _rows(pg, a["work_id"])[0], _rows(pg, b["work_id"])[0]
    assert (ra[2], rb[2]) == ("bad-file", "bad-file") and rb[1] == "open_access", (ra, rb)
    assert rb[7] == 403 and "skipped" not in {ra[2], rb[2]}


@pg_only
def test_a_transient_answer_gets_one_scheduled_retry_named_as_one(pg, tmp_path):
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    slept = []
    pacer = P2M._nopace()
    pacer.sleep = slept.append
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                          "oa.example": (503, {"Retry-After": "7"}, b"")})}
    frozen = pg.one("SELECT clock_timestamp()")[0]
    run.acquire(w, ws, pg.tokens[ws], work, store=_store(tmp_path), agent="c1a", session="c1a-1", clients=stub,
                pacer=pacer, printer=lambda *a, **k: None, routes=("open_access",), pacing={})
    rows = _rows(pg, work["work_id"])
    oa = [r for r in rows if r[1] == "open_access"]
    assert len(oa) == 2 and oa[1][11] == oa[0][0] and oa[0][11] is None, oa
    assert oa[0][9] is True and oa[0][7] == 503, oa[0]          # retriable, terminal 503
    assert slept and slept[0] == 7.0, slept                       # Retry-After honoured over the 2 s AIMD step
    m = {"frozen_at": frozen, "run_workstream_ids": [ws]}
    assert C1A.rehunt_route_spends(pg.conn, m) == 0              # the scheduled retry is not a re-spend
    assert C1A.transient_rows_unretried(pg.conn, m) == 0         # retried once; the retry is never re-retried


@pg_only
def test_a_status_zero_body_is_the_clients_own_error_and_never_quarantined(pg, tmp_path):
    """The client's own transport-error text (E13's 58-byte string, reproduced) is never served bytes: no sha,
    no quarantine, and — every request a transport failure, no byte served — `api-error`, `retriable`, never an
    untyped `bad-file` (S4.5 decision D15; auditor-C1a F2), with its one scheduled retry."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    store = _store(tmp_path)
    err = b"URLError: <urlopen error [Errno 11002] getaddrinfo failed>"
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                          "oa.example": (0, {}, err)})}
    before = C1A.bad_file_untyped(pg.conn, {})
    _acq(pg, w, ws, work, store, stub, routes=("open_access",))
    oa = [r for r in _rows(pg, work["work_id"]) if r[1] == "open_access"]
    assert [(r[2], r[3], r[5]) for r in oa] == [("api-error", None, None)] * 2, oa    # no served sha
    assert all(r[9] is True for r in oa) and oa[1][11] == oa[0][0], oa                 # retriable; one retry
    assert "getaddrinfo" in oa[0][12]["detail"] and "quarantined" not in oa[0][12], oa[0][12]
    assert oa[0][12]["no_byte_served"].startswith("booked bad-file by the rung"), oa[0][12]
    assert C1A.bad_file_untyped(pg.conn, {}) - before == 0
    assert not P2M._files_under(store.quarantine)


# ── fix round 2 (auditor-C1a F1-F6): dead-ness, no-byte answers, held bytes, the registry's policy seam ──────────
@pg_only
@pytest.mark.parametrize("lookup", [0, 429, 503, 422, "no email"])
def test_an_unpaywall_lookup_that_did_not_answer_never_retires_open_access(pg, tmp_path, monkeypatch, lookup):
    """auditor-C1a F1 (plan item 1, guard 15), on CONSTRUCTED lookup answers: an Unpaywall lookup that did not
    answer about the DOI — a transport failure, a 429 or 503, a rejected email, no email at all — was booked the
    DEAD `no-oa-copy`, so the next run skipped open access for the work for ever. It is `api-error` carrying the
    lookup's own code: `retriable` (and retried once in the run) when that code is transient, and never dead —
    the next run asks again, or waits out the refusal ladder when the code was a refusal (429/503, guard 2)."""
    from litkb.acquire import open_access

    if lookup == "no email":
        monkeypatch.setattr(open_access, "unpaywall_email", lambda: "")
        stub, code = P2M.RouteStub({}), None                   # nothing may be asked
    else:
        stub, code = P2M.RouteStub({"api.unpaywall.org": (lookup, {}, b"")}), lookup
    transient = code in (0, 429, 503)
    ws1, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws1)
    _acq(pg, w, ws1, work, _store(tmp_path), {"open_access": stub}, routes=("open_access",))
    first = [r for r in _rows(pg, work["work_id"]) if r[1] == "open_access"]
    assert [(r[2], r[13], r[9]) for r in first] == [("api-error", [code] if code is not None else None, transient)] * (
        2 if transient else 1), first
    if transient:
        assert first[1][11] == first[0][0]                     # the one scheduled retry names the original
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "c1a-test@example.invalid")
    ws2 = pg.ws()
    _acq(pg, w, ws2, work, _store(tmp_path), {"open_access": P2M.RouteStub({"api.unpaywall.org": (404, {}, b"")})},
         routes=("open_access",))
    nxt = [(r[2], r[3]) for r in _rows(pg, work["work_id"]) if r[1] == "open_access" and r[14] == str(ws2)]
    assert nxt == [("skipped", "backoff_window") if code in (429, 503) else ("no-oa-copy", None)], nxt


@pg_only
def test_a_retriable_attempt_is_never_evidence_that_a_route_is_dead(pg, tmp_path):
    """Guard 15 at the dead check itself, on CONSTRUCTED prior rows (today's open access no longer writes a
    retriable `no-oa-copy`; a rung registered later may answer a dead word with `retriable` true): a prior dead
    word whose row says `retriable` does not skip the route; the same word without it still does."""
    from litkb.acquire import run

    ws1, w = pg.ws(), pg.session("litkb_writer")
    a, b = P2M._admitted(pg, w, ws1), P2M._admitted(pg, w, ws1)
    for work, retriable in ((a, True), (b, False)):
        run.record_attempt(w, ws1, pg.tokens[ws1], work["work_id"], "open_access", work["doi"], "no-oa-copy",
                           {"note": "CONSTRUCTED prior row"}, [503] if retriable else None, retriable=retriable)
    ws2 = pg.ws()
    for work in (a, b):
        _acq(pg, w, ws2, work, _store(tmp_path), {"open_access": P2M.RouteStub({"api.unpaywall.org": (404, {}, b"")})},
             routes=("open_access",))
    got = {k: [(r[2], r[3]) for r in _rows(pg, x["work_id"]) if r[1] == "open_access" and r[14] == str(ws2)]
           for k, x in (("retriable", a), ("not retriable", b))}
    assert got == {"retriable": [("no-oa-copy", None)], "not retriable": [("skipped", "dead_route")]}, got


@pg_only
def test_a_challenge_is_never_transient_whatever_its_code(pg, tmp_path):
    """Guard 3 beside guard 15: a Cloudflare challenge served at 503 (a CONSTRUCTED "Just a moment..." page) is
    `blocked`, a refusal — not `retriable`, no in-run retry, and so still dead within the run."""
    from litkb.acquire import backoff as B

    assert B.classify("blocked", [503]) == "refusal" and B.retriable("blocked", [503]) is False
    assert B.classify("api-error", [503]) == "transient"
    page = b"<html><head><title>Just a moment...</title></head><body>" + uuid.uuid4().hex.encode() + b"</body></html>"
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://cf.example/p.pdf"),
                                          "cf.example": (503, {}, page)})}
    _acq(pg, w, ws, work, _store(tmp_path), stub, routes=("open_access",))
    oa = [r for r in _rows(pg, work["work_id"]) if r[1] == "open_access"]
    assert [(r[2], r[3], r[7], r[9]) for r in oa] == [("blocked", "challenge_or_bot_check", 503, False)], oa


@pg_only
@pytest.mark.parametrize("answer,want", [
    ((0, {}, b"URLError: <urlopen error [Errno 11001] getaddrinfo failed>"), ("api-error", None, True, 2)),
    ((503, {}, b""), ("bad-file", "too_small", True, 2)),
    ((404, {}, b""), ("bad-file", "too_small", False, 1)),
    ((403, {}, b""), ("bad-file", "too_small", False, 1)),
    ((200, {}, b""), ("bad-file", "too_small", False, 1)),
    ((404, {"Content-Length": "0"}, b""), ("bad-file", "too_small", False, 1)),
    ((404, {"Content-Type": "text/html; charset=utf-8"}, b""), ("bad-file", "html_response", False, 1)),
])
def test_an_answer_that_served_no_byte_is_never_an_untyped_bad_file(pg, tmp_path, answer, want):
    """S4.5 decision D15 (auditor-C1a F2 and round-2 F1), on CONSTRUCTED answers: every location answered with a
    transport failure or an EMPTY body. Nothing was served, and no byte classifier can type nothing, so as an
    untyped `bad-file` each row climbed the gated all-time `bad_file_untyped`. Every request a transport failure
    (status 0) -> `api-error`, retriable, one retry. Any server answer -> `bad-file`, typed from the TERMINAL
    response: a Content-Type naming html -> `html_response`; 0 bytes (a Content-Length of 0, or none declared)
    -> `too_small`; basis `live`; `retriable` from its own codes (an empty 503 is transient: retried once). No
    sha, no quarantine, no untyped row."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    store = _store(tmp_path)
    before = C1A.bad_file_untyped(pg.conn, {})
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                          "oa.example": answer})}
    _acq(pg, w, ws, work, store, stub, routes=("open_access",))
    oa = [r for r in _rows(pg, work["work_id"]) if r[1] == "open_access"]
    assert [(r[2], r[3], r[9]) for r in oa] == [want[:3]] * want[3], oa
    assert all(r[5] is None and r[7] == answer[0] for r in oa), oa
    assert all(r[4] == ("live" if want[1] else None) for r in oa), oa
    if want[0] == "bad-file":
        assert "(D15)" in oa[0][12]["sub_status_cause"], oa[0][12]
    assert C1A.bad_file_untyped(pg.conn, {}) - before == 0
    assert not P2M._files_under(store.quarantine)


@pg_only
@pytest.mark.parametrize("codes,want", [([0, 404], ("bad-file", "too_small", False, 1)),
                                        ([503, 404], ("bad-file", "too_small", False, 1)),
                                        ([404, 0], ("bad-file", "too_small", True, 2)),
                                        ([0, 0], ("api-error", None, True, 2))])
def test_mixed_no_byte_answers_are_a_bad_file_unless_every_request_failed_in_transport(pg, tmp_path, codes, want):
    """D15's line between the two rules, on CONSTRUCTED two-location answers (auditor-C1a r2 F4: mutations R4/R5 of
    the round-2 rules survived because no test mixed codes): ONE server answer among transport failures makes the
    attempt a `bad-file` typed from its terminal (the last location asked); only an attempt whose EVERY request
    failed in transport is `api-error`. `retriable` follows the terminal code ([404, 0]: the last answer was the
    transport's, so retried once)."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    store = _store(tmp_path)
    before = C1A.bad_file_untyped(pg.conn, {})
    err = b"URLError: <urlopen error [Errno 11001] getaddrinfo failed>"
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://a.example/p.pdf",
                                                                          "https://b.example/p.pdf"),
                                          "a.example": (codes[0], {}, err if codes[0] == 0 else b""),
                                          "b.example": (codes[1], {}, err if codes[1] == 0 else b"")})}
    _acq(pg, w, ws, work, store, stub, routes=("open_access",))
    oa = [r for r in _rows(pg, work["work_id"]) if r[1] == "open_access"]
    assert [(r[2], r[3], r[9]) for r in oa] == [want[:3]] * want[3], oa
    assert all(r[13] == codes for r in oa) and all(r[5] is None for r in oa), oa
    assert C1A.bad_file_untyped(pg.conn, {}) - before == 0
    assert not P2M._files_under(store.quarantine)


@pg_only
@pytest.mark.parametrize("answer,want,untyped", [
    ({"http_codes": [0, 0], "retriable": False}, ("api-error", None, True), 0),     # D15 forces retriable true
    ({"http_codes": [0, 503]}, ("bad-file", "too_small", True), 0),
    ({"http_codes": [404, 0]}, ("bad-file", "too_small", True), 0),
    ({"http_codes": [404], "headers": {"content-type": "text/html"}}, ("bad-file", "html_response", False), 0),
    ({"http_codes": [200], "headers": {"Content-Length": "48213", "Content-Type": "application/pdf"}},
     ("bad-file", None, False), 1),
])
def test_the_ladder_types_every_rungs_no_byte_answer_by_d15(pg, tmp_path, monkeypatch, answer, want, untyped):
    """The no-byte rules are the LADDER's (run._record_result, run._type_attempt), not open access's: a CONSTRUCTED
    rung (route `osf`, a stub body — no module of it exists yet) that books `bad-file` and hands back no byte.
    Every request a transport failure -> `api-error`, `retriable` TRUE even when the rung said false (D15); else
    typed from the terminal response's headers. The one untyped answer, by design and COUNTED (fail closed): the
    terminal DECLARED 48213 bytes the rung never handed back — typing it would need the acceptance test's floor."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    monkeypatch.setattr(P, "POLICY", P.POLICY + (P.PolicyLine("osf", "*", "legitimate", "CONSTRUCTED test line"),))
    codes = answer["http_codes"]

    def fn(work, ctx):
        return {"status": "bad-file", **{k: v for k, v in answer.items() if k != "headers"},
                "tried": [f"osf.example:{c}" for c in codes],
                "terminal": {"url": "https://osf.example/x", "status_code": codes[-1], "headers": answer.get("headers"),
                             "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}}

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    before = C1A.bad_file_untyped(pg.conn, {})
    _acq(pg, w, ws, work, _store(tmp_path), {}, routes=("osf",), rungs=[run.Rung("osf", fn, concurrent=True)])
    r = [x for x in _rows(pg, work["work_id"]) if x[1] == "osf"]
    assert [(x[2], x[3], x[9]) for x in r] == [want], r
    if want[0] == "api-error":
        assert "every request a transport failure" in r[0][12]["no_byte_served"], r[0][12]
    if untyped:
        assert "declared 48213 bytes" in r[0][12]["sub_status_cause"], r[0][12]
    assert C1A.bad_file_untyped(pg.conn, {}) - before == untyped


def _held_world(pg, tmp_path):
    """CONSTRUCTED: work W1 lands a paper through open access. -> (w, ws, W1, store, pdf, sha, clients, refuse),
    where `refuse(reason, work_id)` records an uncleared legacy quarantine row for the same bytes, refused FOR
    `work_id` (the live shape: 0030 never clears a moved payload)."""
    P2M._need_pdftotext()
    from litkb.db import connect as c
    from litkb.quarantine import ingest_connect

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    store = _store(tmp_path)
    pdf = P2M.paper_pdf(work["title"], "T. Tester")
    sha = hashlib.sha256(pdf).hexdigest()

    def clients():
        return {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                              "oa.example": (200, {}, pdf)})}

    assert _acq(pg, w, ws, work, store, clients(), routes=("open_access",))["outcome"] == "ok"

    def refuse(reason, work_id):
        rec = ingest_connect(c.DB_TEST)
        try:
            rec.execute("SELECT litkb.record_quarantine_system(%s, %s, %s, %s, 'legacy-backfill', %s, NULL, NULL, "
                        "'{}'::jsonb)", (f"_quarantine/Held_{uuid.uuid4().hex[:8]}__{reason}__{sha[:12]}.pdf", sha,
                                         len(pdf), reason, work_id))
        finally:
            rec.close()

    return w, ws, work, store, pdf, sha, clients, refuse


@pg_only
def test_bytes_the_corpus_holds_are_a_hit_never_known_bad(pg, tmp_path):
    """auditor-C1a F3, on the LIVE shape (five payloads refused once and bound later, each the active file of ITS
    OWN work; 0030 never clears a moved payload), CONSTRUCTED here: a work lands a paper, then a legacy quarantine
    row refusing the same sha FOR THAT WORK is recorded. The lookup matches those bytes — but the corpus HOLDS them
    for that work: in MEASURE mode the holding work's legitimate rung books them `measured` and the shadow rung
    stays refused (litkb-shadow-hosts); in acquire mode another work, which nothing refused them for, is served them
    and gets `duplicate-held`, and the ladder stops."""
    from litkb.acquire import ledger as L
    from litkb.acquire import run

    w, ws, work, store, pdf, sha, clients, refuse = _held_world(pg, tmp_path)
    refuse("binding-failed", work["work_id"])
    assert L.rejected_match(pg.conn, sha) is not None and L.held_file(pg.conn, sha, work["work_id"])
    archive = {"annas_session": (P2M.RouteStub({}), "KEY-c1a"), "annas_pacer": P2M._nopace()}   # asked = raises
    ws2 = pg.ws()
    out = _acq(pg, w, ws2, run.work_record(w, work_id=work["work_id"]), store, clients(),
               routes=("open_access", "annas"), mode="measure", **archive)
    got = [(r[1], r[2], r[3]) for r in _rows(pg, work["work_id"]) if r[14] == str(ws2)]
    assert got == [("open_access", "measured", None), ("annas", "skipped", "policy_refused")], got
    assert out["outcome"] == "measured"
    other = P2M._admitted(pg, w, ws2)
    assert L.held_file(pg.conn, sha, other["work_id"])
    out = _acq(pg, w, ws2, other, store, clients(), routes=("open_access", "annas"), **archive)
    assert out["outcome"] == "duplicate-held", out
    assert [(r[1], r[2]) for r in _rows(pg, other["work_id"])] == [("open_access", "duplicate-held")]


@pg_only
def test_bytes_refused_for_this_work_stay_known_bad_whoever_holds_them(pg, tmp_path):
    """auditor-C1a r2 F3, CONSTRUCTED: W1 holds a paper; the same bytes were refused FOR W2 (`content-mismatch`: the
    ledger knows they are not W2's paper). Served to W2 they stay `known-bad` — in MEASURE mode (not `measured`, so
    no legitimate hit is claimed for W2) and in acquire mode (not `duplicate-held`) — and nothing is quarantined
    again. Round 2's held rule was global: W1's holding made them a hit for W2."""
    from litkb.acquire import ledger as L

    w, ws, _w1, store, pdf, sha, clients, refuse = _held_world(pg, tmp_path)
    w2 = P2M._admitted(pg, w, ws)
    refuse("content-mismatch", w2["work_id"])
    assert not L.held_file(pg.conn, sha, w2["work_id"])
    ws2 = pg.ws()
    for mode in ("measure", "acquire"):
        _acq(pg, w, ws2, w2, store, clients(), routes=("open_access",), mode=mode)
    got = [(r[2], r[12].get("known_bad", {}).get("reason")) for r in _rows(pg, w2["work_id"]) if r[1] == "open_access"]
    assert got == [("known-bad", "content-mismatch")] * 2, got
    assert not P2M._files_under(store.quarantine)


@pg_only
def test_held_bytes_a_route_refused_keep_their_known_bad_name_and_are_never_quarantined_again(pg, tmp_path,
                                                                                               monkeypatch):
    """auditor-C1a r2 F4 (its mutation R2 survived): the held-bytes rule clears a DOWNLOADED match only. A CONSTRUCTED
    rung (route `osf`, stub body) answers `hash-mismatch` handing back W1's held PDF for another work that nothing
    refused them for — a route REFUSING bytes. The row keeps its status and names the match; nothing is quarantined
    again (no file under _quarantine/, no new quarantine_payloads row)."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    monkeypatch.setattr(P, "POLICY", P.POLICY + (P.PolicyLine("osf", "*", "legitimate", "CONSTRUCTED test line"),))
    w, ws, w1, store, pdf, sha, _clients, refuse = _held_world(pg, tmp_path)
    refuse("binding-failed", w1["work_id"])
    rows_before = pg.one("SELECT count(*) FROM litkb.quarantine_payloads WHERE sha256 = %s", (sha,))[0]

    def fn(work, ctx):
        return {"status": "hash-mismatch", "pdf": pdf, "http_codes": [200], "source_url": "https://osf.example/x",
                "terminal": {"url": "https://osf.example/x", "status_code": 200,
                             "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}}

    other = P2M._admitted(pg, w, ws)
    _acq(pg, w, ws, other, store, {}, routes=("osf",), rungs=[run.Rung("osf", fn, concurrent=True)])
    r = [x for x in _rows(pg, other["work_id"]) if x[1] == "osf"]
    assert [(x[2], x[12].get("known_bad", {}).get("reason"), x[5]) for x in r] == [
        ("hash-mismatch", "binding-failed", sha)], r
    assert "quarantined" not in r[0][12] and not P2M._files_under(store.quarantine)
    assert pg.one("SELECT count(*) FROM litkb.quarantine_payloads WHERE sha256 = %s", (sha,))[0] == rows_before


@pg_only
def test_the_refused_bytes_record_is_its_two_halves_less_what_the_corpus_holds(pg):
    """The lookup's two halves (auditor-C1a F5: mutations A1 and A2 survived round 1), on CONSTRUCTED rows (a
    random sha attached through litkb.attach_file — no bytes; the version's state set by hand where B2's
    withdraw_version will write it): an uncleared classifier row on a bound file matches, and once the
    classifier clears it, it does not; a WITHDRAWN or REJECTED current version matches through the version half
    and is not held."""
    from litkb import quarantine as Q
    from litkb.acquire import ledger as L
    from litkb.db import connect as c

    ws, w = pg.ws(), pg.session("litkb_writer")
    shas = []
    for state in ("withdrawn", "rejected"):
        work = P2M._admitted(pg, w, ws)
        fj = P2M._file(work["title"])
        res = pg.one("SELECT litkb.attach_file(%s, %s, %s, %s, 'c1a', 'c1a-1')",
                     (ws, pg.tokens[ws], work["work_id"], pg.jsonb(fj)), conn=w)[0]
        assert res["outcome"] == "attached", res
        shas.append((fj, res, work, state))
    fj, res, work, _state = shas[0]
    sha = fj["sha256"]
    assert L.held_file(pg.conn, sha, work["work_id"]) and L.rejected_match(pg.conn, sha) is None
    rec = Q.ingest_connect(c.DB_TEST)
    try:
        qid = rec.execute("SELECT litkb.record_quarantine_system(%s, %s, 1000, 'zero-content', 'classifier', %s, %s, "
                          "NULL, '{}'::jsonb)", (fj["rel_path"], sha, work["work_id"], res["file_id"])).fetchone()[0]
        assert L.rejected_match(pg.conn, sha)["source"] == "quarantine_payloads"
        assert Q.clear_system(rec, qid, session="c1a-test", reason="CONSTRUCTED: the classifier cleared its row")
    finally:
        rec.close()
    assert L.rejected_match(pg.conn, sha) is None                       # A1: a CLEARED row is not refused bytes
    for fj, res, owner, state in shas:
        # (a registry work's version is born `promoted`; file_versions_promoted_at ties promoted_at to that state)
        pg.conn.execute("UPDATE litkb.file_versions SET state = %s, promoted_at = NULL WHERE version_id = %s",
                        (state, res["file_version"]))
        m = L.rejected_match(pg.conn, fj["sha256"])
        assert m is not None and (m["source"], m["reason"]) == ("file_versions", state), m    # A2: the version half
        assert not L.held_file(pg.conn, fj["sha256"], owner["work_id"])


def test_a_rung_registers_with_its_own_policy_line_or_not_at_all(monkeypatch):
    """auditor-C1a F4: `register` is the seam a rung module uses without editing the loop, so the rung's
    pre-fetch lines come WITH it (`policy_lines`, into the one `policy.POLICY`); a rung with no line is refused at
    registration — never a rung the policy refuses on every work. A line must be the rung's own route and its
    stage's tier (a shadow front can never be declared legitimate), and a (route, host) is lined once. The rungs
    here are CONSTRUCTED (routes `osf`, `bban`; stub bodies)."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    monkeypatch.setattr(P, "POLICY", P.POLICY)               # restored after the test: registration appends to it
    for line in P.POLICY:                                      # the static lines obey the same tier rule
        assert (line.tier == P.SHADOW) == (P.STAGE_OF[line.route] == "shadow"), line
    mine = []
    osf = run.Rung("osf", lambda work, ctx: {"status": "not-in-archive"}, concurrent=True)
    with pytest.raises(ValueError, match="no litkb.acquire.policy.POLICY line"):
        run.register(osf, mine)
    assert mine == [] and not P.decide("osf").allowed
    with pytest.raises(ValueError, match="own staged route"):
        run.register(osf, mine, policy_lines=(P.PolicyLine("zenodo", "zenodo.org", "legitimate", "CONSTRUCTED"),))
    bban = run.Rung("bban", lambda work, ctx: {"status": "not-in-archive"})
    with pytest.raises(ValueError, match="is not the tier of stage"):
        run.register(bban, mine, policy_lines=(P.PolicyLine("bban", "bban.example", "legitimate", "CONSTRUCTED"),))
    line = P.PolicyLine("osf", "api.osf.io", "legitimate", "CONSTRUCTED test line")
    assert run.register(osf, mine, policy_lines=(line,)) is osf and mine == [osf]
    assert P.decide("osf").allowed and P.decide("osf", "api.osf.io").line == P.POLICY.index(line)
    with pytest.raises(ValueError, match="already in POLICY"):
        P.add_lines((line,), route="osf")


@pg_only
def test_a_scheduled_retry_whose_wait_spends_the_budget_is_not_launched(pg, tmp_path):
    """The budget is checked again AFTER a scheduled retry's wait. On a CONSTRUCTED clock (the pacer's sleep
    advances it; the ladder budget reads it): a 503 with Retry-After 30 against a 10 s budget — the retry would be
    launched at 30 s, past the budget, i.e. the silent overrun `budget_exceeded_silently` counts. It is not
    launched; the original stays `retriable` and unretried; the next rung meets the spent budget as a `budget-stop`."""
    from litkb.acquire import policy as P

    now = [0.0]
    pacer = P2M._nopace()
    pacer.sleep = lambda s: now.__setitem__(0, now[0] + s)
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    frozen = pg.one("SELECT clock_timestamp()")[0]
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                          "oa.example": (503, {"Retry-After": "30"}, b"")}),
            "scihub": P2M.RouteStub({})}                       # asked = raises
    from litkb.acquire import run
    run.acquire(w, ws, pg.tokens[ws], work, store=_store(tmp_path), agent="c1a", session="c1a-1", clients=stub,
                pacer=pacer, printer=lambda *a, **k: None, routes=("open_access", "scihub"), pacing={},
                ladder_budget=P.LadderBudget(seconds=10, clock=lambda: now[0]))
    rows = [(r[1], r[2], r[3], r[9], r[11]) for r in _rows(pg, work["work_id"]) if r[1] != "browser"]
    # (an EMPTY 503 is a server's answer: `bad-file` typed `too_small` from its terminal, retriable — S4.5 decision D15)
    assert rows == [("open_access", "bad-file", "too_small", True, None),
                    ("ladder", "budget-stop", "budget_seconds", None, None)], rows
    m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "ladder_budget": {"seconds": 10, "attempts": None}}
    assert C1A.budget_exceeded_silently(pg.conn, m) == 0
    assert C1A.transient_rows_unretried(pg.conn, m) == 1          # reported, honestly: the retry was not asked


@pg_only
def test_the_budget_stops_the_ladder_and_says_so(pg, tmp_path):
    from litkb.acquire import policy as P

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    out = _acq(pg, w, ws, work, _store(tmp_path), _e13_clients(), routes=("open_access", "scihub"),
               ladder_budget=P.LadderBudget(attempts=1))
    rows = _rows(pg, work["work_id"])
    assert [(r[1], r[2], r[3]) for r in rows][:2] == [("open_access", "blocked", "challenge_or_bot_check"),
                                                      ("ladder", "budget-stop", "budget_attempts")], rows
    assert rows[1][12]["not_asked"] == ["scihub"] and rows[1][12]["budget"]["attempts"] == 1
    assert rows[0][12]["ladder"]["spent_before"] == 0 and rows[0][12]["ladder"]["budget"]["attempts"] == 1
    assert out["outcome"] == "not-acquired"
    clock = iter([0.0, 0.0, 999.0, 999.0, 999.0, 999.0])
    work2 = P2M._admitted(pg, w, ws)
    _acq(pg, w, ws, work2, _store(tmp_path), _e13_clients(), routes=("open_access", "scihub"),
         ladder_budget=P.LadderBudget(seconds=10, clock=lambda: next(clock)))
    assert ("ladder", "budget-stop", "budget_seconds") in [(r[1], r[2], r[3]) for r in _rows(pg, work2["work_id"])]


@pg_only
def test_the_policy_is_one_switch_and_the_shadow_tier_waits_for_every_legitimate_miss(pg, tmp_path, monkeypatch):
    from litkb.acquire import policy as P

    assert not P.decide("not-a-route").allowed and P.decide("scihub", "sci-hub.ru").allowed
    assert not P.decide("scihub", "sci-hub.ru", legit_hit=True).allowed
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    pdf = P2M.paper_pdf(work["title"], "T. Tester")
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                          "oa.example": (200, {}, pdf)})}
    # the archive rung makes no per-host decision of its own, so the ladder's is the only guard here;
    # any archive request would raise (an empty RouteStub)
    out = _acq(pg, w, ws, work, _store(tmp_path), stub, routes=("open_access", "annas"), mode="measure",
               annas_session=(P2M.RouteStub({}), "KEY-c1a"), annas_pacer=P2M._nopace())
    rows = _rows(pg, work["work_id"])
    assert [(r[1], r[2], r[3]) for r in rows] == [("open_access", "measured", None),
                                                  ("annas", "skipped", "policy_refused")], rows
    assert rows[1][12]["policy"]["reason"] == "a legitimate rung already hit in this ladder run"
    assert rows[0][12]["policy"][0]["tier"] == "legitimate" and out["outcome"] == "measured"
    monkeypatch.setattr(P, "SHADOW_TIER_ENABLED", False)
    work2 = P2M._admitted(pg, w, ws)
    _acq(pg, w, ws, work2, _store(tmp_path), {}, routes=("annas",), annas_session=(P2M.RouteStub({}), "KEY-c1a"),
         annas_pacer=P2M._nopace())
    assert [(r[1], r[2], r[3]) for r in _rows(pg, work2["work_id"])][0] == ("annas", "skipped", "policy_refused")


@pg_only
def test_stage_b_rungs_run_concurrently_and_are_recorded_in_registry_order(pg, tmp_path, monkeypatch):
    """Two CONSTRUCTED Stage B rungs (their routes are real 0033 words; the rung bodies are stubs that wait
    0.4 s and miss): wall-clock is the slowest, not the sum, and the rows keep registry order."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    monkeypatch.setattr(P, "POLICY", P.POLICY + (P.PolicyLine("osf", "*", "legitimate", "CONSTRUCTED test line"),
                                                 P.PolicyLine("zenodo", "*", "legitimate", "CONSTRUCTED test line")))

    def slow(route):
        def fn(work, ctx):
            time.sleep(0.4)
            return {"status": "not-in-archive", "http_codes": [404], "tried": [f"{route}:404"],
                    "terminal": {"url": f"https://{route}.example/x", "status_code": 404,
                                 "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}}
        return fn

    rungs = [run.Rung("osf", slow("osf"), concurrent=True), run.Rung("zenodo", slow("zenodo"), concurrent=True)]
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    t0 = time.monotonic()
    _acq(pg, w, ws, work, _store(tmp_path), {}, routes=("osf", "zenodo"), rungs=rungs)
    took = time.monotonic() - t0
    rows = _rows(pg, work["work_id"])
    assert [(r[1], r[2]) for r in rows][:2] == [("osf", "not-in-archive"), ("zenodo", "not-in-archive")], rows
    assert took < 0.75, f"two 0.4 s rungs took {took:.2f} s: they ran one after the other"


@pg_only
def test_a_blocked_answer_is_never_retriable_whatever_the_rung_says(pg, tmp_path, monkeypatch):
    """auditor-C1a r2 F5, CONSTRUCTED rung (route `osf`, stub body): it answers `blocked` and says `retriable: True`.
    The row is written `retriable` FALSE (a challenge is a refusal, guard 3), so a second ask in the same run is
    `skipped/dead_in_run` — never asked again because the rung claimed the refusal might pass."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    monkeypatch.setattr(P, "POLICY", P.POLICY + (P.PolicyLine("osf", "*", "legitimate", "CONSTRUCTED test line"),))
    asked = []

    def fn(work, ctx):
        asked.append(1)
        return {"status": "blocked", "retriable": True, "http_codes": [403], "tried": ["osf.example:403"],
                "terminal": {"url": "https://osf.example/x", "status_code": 403,
                             "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}}

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    for _ in range(2):
        _acq(pg, w, ws, work, _store(tmp_path), {}, routes=("osf",), rungs=[run.Rung("osf", fn, concurrent=True)])
    r = [(x[2], x[3], x[9]) for x in _rows(pg, work["work_id"]) if x[1] == "osf"]
    assert r == [("blocked", "challenge_or_bot_check", False), ("skipped", "dead_in_run", None)], r
    assert len(asked) == 1


@pg_only
@pytest.mark.parametrize("attempts,retries", [(2, 0), (3, 1)])
def test_a_concurrent_stages_retry_counts_the_siblings_launched_beside_it(pg, tmp_path, monkeypatch, attempts,
                                                                           retries):
    """auditor-C1a r2 F2, two CONSTRUCTED concurrent rungs (routes `osf`, `zenodo`; stub bodies that answer a
    transient 503 and opt in to the scheduled retry) under an explicit attempts budget. Both are asked before either
    is settled, so when `osf`'s retry is weighed `zenodo` has already spent its request. attempts=2: no retry at all
    (round 2 launched `osf`'s — 3 spends against 2, recorded `spent_before` 1, invisible to the counter);
    attempts=3: exactly one retry, recording `spent_before` 2. Never more spends than the budget, and
    `budget_exceeded_silently` against the same frozen budget reads 0."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    monkeypatch.setattr(P, "POLICY", P.POLICY + (P.PolicyLine("osf", "*", "legitimate", "CONSTRUCTED test line"),
                                                 P.PolicyLine("zenodo", "*", "legitimate", "CONSTRUCTED test line")))

    def busy(route):
        def fn(work, ctx):
            return {"status": "api-error", "http_codes": [503], "tried": [f"{route}.example:503"],
                    "terminal": {"url": f"https://{route}.example/x", "status_code": 503,
                                 "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}}
        return fn

    rungs = [run.Rung("osf", busy("osf"), concurrent=True, retry_transient=True),
             run.Rung("zenodo", busy("zenodo"), concurrent=True, retry_transient=True)]
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    frozen = pg.one("SELECT clock_timestamp()")[0]
    _acq(pg, w, ws, work, _store(tmp_path), {}, routes=("osf", "zenodo"), rungs=rungs,
         ladder_budget=P.LadderBudget(attempts=attempts))
    rows = [x for x in _rows(pg, work["work_id"]) if x[1] in ("osf", "zenodo")]
    retry_rows = [x for x in rows if x[11] is not None]
    assert len(rows) == 2 + retries and len(rows) <= attempts, [(x[1], x[2], x[11]) for x in rows]
    assert len(retry_rows) == retries
    if retries:
        assert retry_rows[0][1] == "osf" and retry_rows[0][12]["ladder"]["spent_before"] == 2, retry_rows[0][12]
    m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "ladder_budget": {"seconds": None, "attempts": attempts}}
    assert C1A.budget_exceeded_silently(pg.conn, m) == 0


@pg_only
def test_measure_mode_lands_nothing_and_records_every_answer(pg, tmp_path):
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    store = _store(tmp_path)
    pdf = P2M.paper_pdf(work["title"], "T. Tester")
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf", version="acceptedVersion"),
                                          "oa.example": (200, {}, pdf)})}
    out = _acq(pg, w, ws, work, store, stub, routes=("open_access",), mode="measure")
    r = _rows(pg, work["work_id"])[0]
    assert (r[1], r[2], r[5], r[10]) == ("open_access", "measured", hashlib.sha256(pdf).hexdigest(), "pdf"), r
    assert r[12]["not_landed"] == "measure mode" and r[12]["version"] == "acceptedVersion"
    assert out["outcome"] == "measured" and not P2M._files_under(store.staging)
    assert pg.one("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (hashlib.sha256(pdf).hexdigest(),))[0] == 0
    stub2 = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                           "oa.example": (200, {}, P2M.salted_html())})}
    work2 = P2M._admitted(pg, w, ws)
    _acq(pg, w, ws, work2, store, stub2, routes=("open_access",), mode="measure")
    r2 = _rows(pg, work2["work_id"])[0]
    assert (r2[2], r2[3]) == ("bad-file", "html_response") and r2[12]["not_quarantined"] == "measure mode"
    assert not P2M._files_under(store.quarantine)


@pg_only
def test_the_rejected_hash_lookup_matches_by_content_never_by_path(pg, tmp_path):
    """E13's REAL recorded challenge page, refused once (a quarantine row at one path), served again: the
    second attempt names the match and writes nothing; a PDF whose sha is refused is `known-bad`."""
    from litkb.quarantine import ingest_connect
    from litkb.db import connect as c

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    store = _store(tmp_path)
    page = _e13()
    rec = ingest_connect(c.DB_TEST)
    pdf = P2M.paper_pdf(work["title"], "T. Tester")
    try:
        for rel, sha, n in ((f"_quarantine/Lookup_{uuid.uuid4().hex[:8]}__blocked__{C1A.E13_SHA256[:12]}.pdf",
                             C1A.E13_SHA256, len(page)),
                            (f"_quarantine/Lookup_{uuid.uuid4().hex[:8]}__binding-failed__x.pdf",
                             hashlib.sha256(pdf).hexdigest(), len(pdf))):
            rec.execute("SELECT litkb.record_quarantine_system(%s, %s, %s, 'legacy', 'legacy-backfill', NULL, NULL, "
                        "NULL, '{}'::jsonb)", (rel, sha, n))
    finally:
        rec.close()
    _acq(pg, w, ws, work, store, _e13_clients(), routes=("open_access",))
    r = _rows(pg, work["work_id"])[0]
    assert (r[2], r[3], r[5]) == ("blocked", "challenge_or_bot_check", C1A.E13_SHA256), r
    assert r[12]["known_bad"]["source"] == "quarantine_payloads" and "quarantined" not in r[12], r[12]
    assert not P2M._files_under(store.quarantine)
    work2 = P2M._admitted(pg, w, ws)
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                          "oa.example": (200, {}, pdf)})}
    _acq(pg, w, ws, work2, store, stub, routes=("open_access",))
    r2 = _rows(pg, work2["work_id"])[0]
    assert (r2[2], r2[10]) == ("known-bad", "pdf") and not P2M._files_under(store.staging), r2


@pg_only
def test_a_challenge_page_at_200_is_blocked_and_the_old_rule_books_it_a_miss(pg, tmp_path, monkeypatch):
    """The item-2 rule's known-bad: a CONSTRUCTED page in `sci-hub.wf`'s shape (a 200 whose title is "Checking
    your browser…", D1 — not a recording) through the open-access route. With the rule, `blocked/challenge_or_bot_check`; with `is_challenge`
    reverted to the 403/503-only rule, the same page is booked a miss (`bad-file`)."""
    from litkb import netutil

    page = ("<!DOCTYPE html><html><head><title>Checking your browser…</title></head><body>"
            + uuid.uuid4().hex + "</body></html>").encode("utf-8")
    stub = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://mirror.example/x"),
                                          "mirror.example": (200, {}, page)})}
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    _acq(pg, w, ws, work, _store(tmp_path), stub, routes=("open_access",))
    assert _rows(pg, work["work_id"])[0][2:4] == ("blocked", "challenge_or_bot_check")
    old = staticmethod(lambda status, url, body: bool(
        (status == 403 and "check=1" in (url or "")) or (status in (403, 503) and netutil.CHALLENGE_RE.search(body or b""))))
    monkeypatch.setattr(netutil.Client, "is_challenge", old)
    page2 = page.replace(b"</body>", uuid.uuid4().hex.encode() + b"</body>")
    stub2 = {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://mirror.example/x"),
                                           "mirror.example": (200, {}, page2)})}
    work2 = P2M._admitted(pg, w, ws)
    _acq(pg, w, ws, work2, _store(tmp_path), stub2, routes=("open_access",))
    assert _rows(pg, work2["work_id"])[0][2] == "bad-file"


def test_is_challenge_reads_the_title_at_every_other_status():
    from litkb.netutil import Client

    assert Client.is_challenge(200, "https://x/y", b"<html><title>Just a moment...</title></html>")
    assert Client.is_challenge(200, "https://x/y", "<title>Checking your browser…</title>".encode())
    assert not Client.is_challenge(200, "https://x/y", b"<html><title>Record</title><script>ddos-guard</script></html>")
    assert not Client.is_challenge(200, "https://x/y", b"%PDF-1.7 <title>Just a moment</title>")
    assert Client.is_challenge(403, "https://x/y", b"<p>DDoS-Guard</p>")     # 403/503: the whole body, as before
    assert Client.is_challenge(403, "https://x/y?&check=1", b"")
    assert not Client.is_challenge(403, "https://x/y", b"Account not allowed")


@pg_only
def test_every_attempt_carries_its_facts_and_the_unpaywall_email_never_reaches_the_ledger(pg, tmp_path, monkeypatch):
    P2M._need_pdftotext()
    from litkb import netutil
    from litkb.acquire import open_access

    snapshot = list(netutil._SECRETS)
    email = f"c1a-{uuid.uuid4().hex[:10]}@example.invalid"
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: email)
    try:
        ws, w = pg.ws(), pg.session("litkb_writer")
        work = P2M._admitted(pg, w, ws)
        pdf = P2M.paper_pdf(work["title"], "T. Tester")
        stub = P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://pub.example/x.pdf", version="publishedVersion"),
                              "pub.example": (200, {}, pdf)})
        out = _acq(pg, w, ws, work, _store(tmp_path), {"open_access": stub}, routes=("open_access",))
        assert out["outcome"] == "ok", out
        assert urllib.parse.urlencode({"email": email}) in stub.calls[0]           # asked THROUGH the client
        assert "api.unpaywall.org" in stub.calls[0]
        assert netutil.redact(email) == "<KEY>"                                       # registered before it
        r = _rows(pg, work["work_id"])[0]
        assert (r[2], r[5], r[6], r[7], r[9], r[10]) == ("ok", hashlib.sha256(pdf).hexdigest(),
                                                          "https://pub.example/x.pdf", 200, False, "pdf"), r
        assert r[8] is not None
        fv = pg.one("SELECT copy_kind, word_count FROM litkb.file_versions WHERE version_id = %s",
                    (r[12]["attach"]["file_version"],))
        assert fv[0] == "publisher" and fv[1] > 20, fv
        work2 = P2M._admitted(pg, w, ws)
        _acq(pg, w, ws, work2, _store(tmp_path), {"open_access": P2M.RouteStub({"api.unpaywall.org": (404, {}, b"")})},
             routes=("open_access",))
        r2 = _rows(pg, work2["work_id"])[0]
        assert r2[2] == "no-oa-copy" and r2[6].startswith("https://api.unpaywall.org/v2/") and "?" not in r2[6], r2
        blob = json.dumps([_rows(pg, work["work_id"]), _rows(pg, work2["work_id"])], default=str)
        assert email not in blob, "the Unpaywall email reached the ledger"
    finally:
        netutil._SECRETS.clear()
        netutil._SECRETS.extend(snapshot)


# ── typing ───────────────────────────────────────────────────────────────────────────────────────
def test_the_blocked_classifier_on_recorded_and_shaped_pages():
    from litkb.acquire import ledger as L

    assert L.type_blocked([403], _e13()) == ("challenge_or_bot_check", "bytes", "cloudflare")
    # `akamai` and `mdpi` below are CONSTRUCTED in the shape of the kept MDPI pages (not recordings)
    akamai =b"<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY>Reference #18 https://errors.edgesuite.net/x</BODY></HTML>"
    assert L.type_blocked([403, 403], akamai)[:2] == ("challenge_or_bot_check", "bytes")
    assert L.type_blocked([401], b"<html>sign in</html>")[0] == "identity_required"
    assert L.type_blocked([404])[0] == "not_found"
    assert L.type_blocked([200, 200, 403]) == ("html_or_reader", "inferred",
                                               "a 200 answered and served no file (bytes not kept)")
    assert L.type_blocked([403])[:2] == ("challenge_or_bot_check", "inferred")
    assert L.type_blocked([200], None, None, ["sci-hub.ru:200=blocked"])[:2] == ("challenge_or_bot_check", "detail")
    assert L.type_blocked([]) == (None, None, "untypable")
    # the route's own rule: open_access books blocked only when a challenge answered (its kept bytes are the
    # FIRST body served, e.g. a landing page, and need not be the challenging one)
    assert L.type_blocked([200, 403], b"<html><title>Landing</title></html>", route="open_access")[:2] == (
        "challenge_or_bot_check", "detail")
    mdpi = (b"<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>Reference&#32;&#35;18&#46;c7\n"
            b"<P>https&#58;&#47;&#47;errors&#46;edgesuite&#46;net&#47;18&#46;c7</P></BODY></HTML>")
    assert L.type_blocked([403, 403], mdpi) == ("challenge_or_bot_check", "bytes", "akamai")
    # the bad-file typing is THE acceptance test's own word (seam integrator-w1; the interim mapping is gone)
    assert L.bad_file_sub(b"") is None
    assert L.bad_file_sub(P2M.HTML_SERVED_AS_PDF) == "html_response"


@pg_only
def test_the_blocked_typing_reads_the_kept_bytes_and_writes_the_contract_columns(pg, tmp_path):
    from litkb.acquire import ledger as L
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    root = tmp_path / "Lit"
    rel = f"_quarantine/Typing_{uuid.uuid4().hex[:8]}__blocked__{C1A.E13_SHA256[:12]}.pdf"
    (root / rel).parent.mkdir(parents=True)
    (root / rel).write_bytes(_e13())
    aid = run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", None, "blocked",
                             {"quarantined": rel, "sha256": C1A.E13_SHA256}, [403])
    rows = {r["attempt_id"]: r for r in L.blocked_typing_rows(pg.conn, root)}
    assert rows[str(aid)]["sub_status"] == "challenge_or_bot_check" and rows[str(aid)]["basis"] == "bytes", rows[str(aid)]
    out = tmp_path / "blocked.csv"
    L.write_csv(list(rows.values()), out, L.TYPING_COLUMNS)
    assert next(csv.reader(open(out, encoding="utf-8")))[:5] == list(L.TYPING_COLUMNS)


@pg_only
def test_the_backfill_dry_runs_by_default_fills_nulls_and_never_overwrites(pg, tmp_path, capsys):
    from litkb.acquire import ledger as L
    from litkb.acquire import run
    from litkb.db import connect as c
    from litkb.quarantine import ingest_connect

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    tok, wid = pg.tokens[ws], work["work_id"]
    bad = run.record_attempt(w, ws, tok, wid, "open_access", None, "bad-file", {}, [200])
    blk = run.record_attempt(w, ws, tok, wid, "scihub", None, "blocked", {}, [403])
    okr = run.record_attempt(w, ws, tok, wid, "annas", None, "ok", {})
    typed = run.record_attempt(w, ws, tok, wid, "scihub", None, "blocked", {}, [403], sub_status="not_found")
    f = tmp_path / "typing.csv"
    with open(f, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(L.TYPING_COLUMNS)
        wr.writerows([[bad, "html_response", "bytes", "y", "c"], [blk, "challenge_or_bot_check", "detail", "", "c"],
                      [okr, "html_response", "bytes", "", "wrong family"], [typed, "challenge_or_bot_check", "bytes", "", "c"],
                      [str(uuid.uuid4()), "too_small", "bytes", "", "missing"], [bad, "too_small", "guess", "", "bad basis"],
                      [blk, "", "", "", "untypable"]])
    args = ["--db", c.DB_TEST, "--role", "litkb_test", "backfill-sub-status", "--csv", str(f), "--session", "c1a-test"]
    assert L.main(args) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["mode"] == "dry-run" and dry["plan"] == {"would_apply": 2, "missing": 1, "already_typed": 1,
                                                         "wrong_family": 1, "bad_basis": 1}, dry
    assert pg.one("SELECT sub_status FROM litkb.acquisition_attempts WHERE id = %s", (bad,))[0] is None
    rec = ingest_connect(c.DB_TEST)
    try:
        out = L.backfill_sub_status(pg.conn, f, session="c1a-test", apply=True, recorder=rec)
    finally:
        rec.close()
    assert out["applied"]["applied"] == 2 and out["applied"]["already_typed"] == 1, out
    got = dict(pg.conn.execute("SELECT id::text, sub_status || '/' || sub_status_basis FROM litkb.acquisition_attempts "
                               "WHERE id = ANY(%s)", ([str(bad), str(blk), str(okr), str(typed)],)).fetchall())
    assert got == {str(bad): "html_response/bytes", str(blk): "challenge_or_bot_check/detail", str(okr): None,
                   str(typed): "not_found/live"}, got
    log = pg.one("SELECT op, session, offered, applied FROM litkb.acquisition_backfills WHERE id = %s",
                 (out["applied"]["backfill_id"],))
    assert log == ("sub_status", "c1a-test", 6, 2), log


@pg_only
def test_the_word_count_backfill_fills_a_null_and_never_overwrites(pg, tmp_path):
    from litkb.acquire import ledger as L
    from litkb.db import connect as c
    from litkb.quarantine import ingest_connect

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    root = tmp_path / "Lit"
    rel_txt = f"_litkb_staging/filed/wc-{uuid.uuid4().hex[:6]}.txt"
    (root / rel_txt).parent.mkdir(parents=True)
    (root / rel_txt).write_text("one two three four five", encoding="utf-8")
    fj = P2M._file(work["title"]) | {"txt_extract_path": rel_txt}
    res = pg.one("SELECT litkb.attach_file(%s, %s, %s, %s, 'c1a', 'c1a-1')",
                 (ws, pg.tokens[ws], work["work_id"], pg.jsonb(fj)), conn=w)[0]
    assert res["outcome"] == "attached", res
    rows, _unreadable = L.word_count_rows(pg.conn, root)
    mine = [r for r in rows if r["version_id"] == str(res["file_version"])]
    assert mine == [{"version_id": str(res["file_version"]), "word_count": 5}]
    rec = ingest_connect(c.DB_TEST)
    try:
        rec.execute("SELECT litkb.backfill_file_word_count('c1a-test', 'test', %s)", (pg.jsonb(mine),))
        rec.execute("SELECT litkb.backfill_file_word_count('c1a-test', 'test', %s)",
                    (pg.jsonb([dict(mine[0], word_count=999)]),))
    finally:
        rec.close()
    assert pg.one("SELECT word_count FROM litkb.file_versions WHERE version_id = %s", (res["file_version"],))[0] == 5


# ── the counters module and its fires ───────────────────────────────────────────────────────────
@pg_only
def test_the_counters_module_names_the_plans_counters_and_every_one_runs(pg):
    assert set(C1A.COUNTERS) == {"rehunt_route_spends", "known_bad_relands", "bad_file_untyped", "blocked_untyped",
                                 "budget_exceeded_silently"}
    assert set(C1A.REPORTED) == {"transient_rows_unretried", "attempts_without_sha", "attempts_without_terminal",
                                 "files_without_word_count", "hits_without_version"}
    m = {"frozen_at": pg.one("SELECT clock_timestamp()")[0], "run_workstream_ids": [str(pg.ws())]}
    for name, fn in {**C1A.COUNTERS, **C1A.REPORTED}.items():
        assert isinstance(fn(pg.conn, m), int), name
    with pytest.raises(ValueError):
        C1A.rehunt_route_spends(pg.conn, {})                    # a run-scoped counter refuses an unscoped manifest
    for name, fire in C1A.FIRES.items():
        assert fire["counter"] in C1A.COUNTERS and callable(fire["run"]), name


@pg_only
def test_the_budget_counter_grades_a_frozen_threshold_and_a_row_the_ladder_did_not_account_for(pg):
    """auditor-C1a F6 / Codex X2, on CONSTRUCTED rows: the threshold `budget_exceeded_silently` reads is FROZEN
    outside the ladder (the manifest's `ladder_budget`, else the reference seconds), so a ladder that declared
    no budget is still graded; and a spent rung row with no `detail.ladder` escaped the ladder's accounting."""
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    frozen = pg.one("SELECT clock_timestamp()")[0]
    a, b = P2M._admitted(pg, w, ws), P2M._admitted(pg, w, ws)
    none = {"seconds": None, "attempts": None, "concurrency": None}
    for spent, route, status in ((0, "open_access", "no-oa-copy"), (1, "annas", "record-mismatch")):
        # work a: two spent rungs of a ladder that declared NO budget (the budget object removed)
        run.record_attempt(w, ws, pg.tokens[ws], a["work_id"], route, None, status,
                           {"ladder": {"elapsed_s": 1.0, "spent_before": spent, "budget": none}}, [200])
    run.record_attempt(w, ws, pg.tokens[ws], b["work_id"], "open_access", None, "no-oa-copy", {"note": "no ladder"},
                       [200])
    m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)]}
    assert C1A.frozen_budget(m) == {"seconds": 505, "attempts": None}
    assert C1A.budget_exceeded_silently(pg.conn, m) == 1                                  # b: no detail.ladder
    assert C1A.budget_exceeded_silently(pg.conn, m | {"ladder_budget": {"attempts": 1}}) == 2   # + a, past 1


def _fire(pg, tmp_path, name):
    """control then known-bad on the shared worker database: for an ALL-TIME counter the value is compared as
    a delta over the rows before (other tests' untyped rows are not this fire's), for a run-scoped one the
    fire scopes itself to its own workstream."""
    fire = C1A.FIRES[name]
    counter = C1A.COUNTERS[fire["counter"]]
    all_time = fire["counter"] in ("bad_file_untyped", "blocked_untyped")
    before = counter(pg.conn, {}) if all_time else 0
    control = fire["run"](pg.conn, "control", tmp_path / "control") - before
    mid = counter(pg.conn, {}) if all_time else 0
    known_bad = fire["run"](pg.conn, "known_bad", tmp_path / "known_bad") - (mid if all_time else 0)
    return control, known_bad


@pg_only
@pytest.mark.parametrize("name", ["backoff_window_zero", "known_bad_lookup_disabled", "typing_disabled_bad_file",
                                  "typing_disabled_blocked", "budget_removed"])
def test_every_c1a_fire_fires(pg, tmp_path, name):
    control, known_bad = _fire(pg, tmp_path, name)
    assert control == 0, f"{name}: the control arm is outside the bound ({control})"
    assert known_bad > 0, f"{name}: DID NOT FIRE (known-bad {known_bad})"

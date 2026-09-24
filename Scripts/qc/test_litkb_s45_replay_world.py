r"""S4.5 builder-fix8: the replay reproduces the world a recording was made in (S4.5 decisions D42, D46).

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_replay_world.py -q -p no:cacheprovider

WHAT IS UNDER TEST, and the known-bad each test goes red on (rows FX8a-FX8l in qc/instruments/litkb_p2_mutations.py):

  D42   a policy line switched off AFTER a row was recorded (Common Crawl, D39/D40) is switched on for that row's
        replay only, for exactly the routes the row names, and never outside a REPLAY cassette; the replay summary
        names each switch per row                           (`litkb_edge_run._recorded_policy`)
  F3    the replay's pacer reads the row's own virtual clock, so a cool-down started inside a replayed row ends
        where it ended live: one row replayed on a fast and on a slow machine gives identical rows, the recording's
        (`litkb_edge_run._ReplayClock`, `_no_wait_pacer`); the ladder budget is the whole ladder's the live hunt
        resolved, read on that clock (`_replay_budget`)
  Q1    a row whose live answer came from bytes ALREADY ON DISK replays with that file put back in the replay's
        store from the row's own recorded bytes (`replay.world.disk`, `litkb_edge_run._seed_world`); a seed the
        recording does not hold refuses the row, named, before any hunt

Every recording here is CONSTRUCTED: the hosts are a table of answers installed at urllib's opener seam
(`_OpenerWorld`) or a loopback server (`_Server`), so `netutil.Client._raw_get` runs for real, a RECORD cassette
writes exactly what the REAL ladder asked, and no socket leaves the machine. The replays run the REAL ladder through
the replay's own acquirer (`litkb_edge_run._ladder_acquirer`) against those recordings, inside a socket guard that
allows nothing. Nothing here validates the design on real rows: that is the replay referee's (CLAUDE.md §3.4c).
"""
import copy
import email.message
import hashlib
import http.server
import importlib.util
import io
import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

SCRIPTS = Path(__file__).resolve().parent.parent
CONSTRUCTED_DEAD_URL = "https://reports.constructed.invalid/fix8-never-archived.pdf"
JSON_CT = {"Content-Type": "application/json"}
HTML_CT = {"Content-Type": "text/html"}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def E():
    return _load("litkb_edge_run_fix8", "qc/instruments/litkb_edge_run.py")


@pytest.fixture(scope="module")
def HA():
    return _load("litkb_hardening_a_fix8", "qc/instruments/litkb_hardening_a.py")


@pytest.fixture(scope="module")
def C2C():
    return _load("litkb_hardening_c2c_fix8", "qc/instruments/litkb_hardening_c2c.py")


@pytest.fixture(scope="module")
def C():
    from litkb import cassette

    return cassette


def _reset(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


# ── CONSTRUCTED hosts ────────────────────────────────────────────────────────────────────────────

class _Resp:
    """What `OpenerDirector.open` returns to `Client._raw_get`: status, headers, read(), a context manager."""

    def __init__(self, status, headers, body):
        self.status, self.headers, self._body = status, headers, body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _OpenerWorld:
    """CONSTRUCTED hosts at urllib's opener seam: every `OpenerDirector.open` is answered by `answer(url)` ->
    (status, headers, body); a status >= 400 is raised as urllib's HTTPError, exactly what `_raw_get` catches."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def install(self, monkeypatch):
        world = self

        def open_(opener, req, data=None, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            world.asked.append(url)
            st, hd, body = world.answer(url)
            msg = email.message.Message()
            for k, v in (hd or {}).items():
                msg[k] = v
            if st >= 400:
                raise urllib.error.HTTPError(url, st, "CONSTRUCTED", msg, io.BytesIO(body))
            return _Resp(st, msg, body)
        monkeypatch.setattr(urllib.request.OpenerDirector, "open", open_)
        return self


class _Server:
    """A loopback HTTP server with a fixed route table {path: (status, content_type, body)} (the shape of
    qc/test_litkb_hardening.py's): the only host a loopback 'mirror' recording asks."""

    def __init__(self, routes):
        table = routes

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                status, ctype, body = table.get(self.path.split("?", 1)[0], (404, "text/html", b"not here"))
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        return False


class _FakeClient:
    def __init__(self):
        import http.cookiejar

        self.cj = http.cookiejar.CookieJar()


class _LiveClock:
    """The LIVE shape of the ladder's clock for a CONSTRUCTED recording: it moves exactly when the ladder sleeps (a
    live pacer's sleep passes real time). Independent of the replay's own `_ReplayClock` on purpose."""

    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += float(s or 0)

    def pacer(self):
        from litkb.netutil import Pacer

        return Pacer(interval=0, sleep=self.sleep, clock=self)


def _fixed_work(world, ws, doi, title="A constructed replay-world work (builder-fix8)", author="Fixeight", year=2020):
    """A CONSTRUCTED registry admission with a FIXED DOI — the IA search and every Stage E key carry it, so a
    recording and its replays must admit the same one (the database is reset between them) — and the CONSTRUCTED
    dead URL Stage E is asked about (`C2C.World.dead_link`). -> run.work_record's dict."""
    from psycopg.types.json import Jsonb

    from litkb.acquire import run

    ev = {"registry": "crossref", "registry_title": title, "registry_first_author": author, "registry_year": year,
          "claimed": {"title": title, "first_author": author, "year": year, "title_ratio": 1.0, "author_match": True}}
    tok = world.tokens[ws]
    cand = world.writer.execute("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, "
                                "NULL)", (ws, tok, title)).fetchone()[0]
    res = world.writer.execute(
        "SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, 'fix8', 'fix8-1')",
        (ws, tok, cand, f"{author}_{year}_constructed-fix8",
         Jsonb({"type": "article", "title": title, "authors": [{"family": author, "given": "W."}], "year": year}),
         Jsonb([{"scheme": "doi", "value": doi, "verified_by": "crossref", "evidence": ev}]), Jsonb({}))).fetchone()[0]
    assert res.get("outcome") == "admitted", res
    work = run.work_record(world.writer, work_id=res["work_id"])
    world.dead_link(ws, work, CONSTRUCTED_DEAD_URL)
    return work


def _attempts(world, work):
    """The ladder's rows for one work as the replay referee compares them: route, status, sub_status, codes,
    retriable — never ids or timestamps. The CONSTRUCTED dead-link row (route s2) and the ladder's closing
    `browser/manual-step` note (not a rung) are left out."""
    rows = world.owner.execute(
        "SELECT route, status, sub_status, http_codes, retriable FROM litkb.acquisition_attempts WHERE work_id = %s "
        "AND route NOT IN ('s2', 'browser') ORDER BY at, id", (work["work_id"],)).fetchall()
    return [(r[0], r[1], r[2], list(r[3] or []), r[4]) for r in rows]


def _stage_e_world(state):
    """CONSTRUCTED Stage E hosts: the Wayback availability API answers 503 Retry-After 1 ONCE (a slow-down: it cools
    archive.org for 1 s, S4.5 decisions D41/D45), then that nothing is archived; the CDX index is empty; the Internet
    Archive search finds nothing."""
    def answer(url):
        if "archive.org/wayback/available" in url:
            state["avail"] = state.get("avail", 0) + 1
            if state["avail"] == 1:
                return 503, {"Retry-After": "1", **HTML_CT}, b"<html>CONSTRUCTED 503: slow down</html>"
            return 200, JSON_CT, json.dumps({"url": CONSTRUCTED_DEAD_URL, "archived_snapshots": {}}).encode()
        if "/cdx/search/cdx" in url:
            return 200, JSON_CT, b"[]"
        if "archive.org/advancedsearch" in url:
            return 200, JSON_CT, json.dumps({"response": {"numFound": 0, "docs": []}}).encode()
        return 404, HTML_CT, b"<html>CONSTRUCTED 404</html>"
    return answer


def _cc_world(url):
    """CONSTRUCTED Common Crawl: a crawl list naming one crawl, whose index holds no capture (404)."""
    if url.endswith("/collinfo.json"):
        return 200, JSON_CT, json.dumps([{"id": "CC-MAIN-CONSTRUCTED", "cdx-api":
                                         "https://index.commoncrawl.org/CC-MAIN-CONSTRUCTED-index"}]).encode()
    return 404, HTML_CT, b"<html>CONSTRUCTED: no capture</html>"


def _cas_file(C, path, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "replay" and not path.is_file():
        path.write_text(json.dumps({"kind": C.INDEX_KIND, "version": C.INDEX_VERSION}) + "\n", encoding="utf-8")
    return C.Cassette(path, mode, bodies=path.parent / "bodies")


# ── F3: the replay's clock (auditor-fix7 F3, S4.5 decision D46) ──────────────────────────────────────

def test_f3_the_replay_clock_moves_only_by_what_the_ladder_slept_and_is_the_pacers(E):
    """The replay's pacer never waits; its clock is the row's own virtual clock, moved by exactly each sleep; the
    ladder budget of a replayed row reads that clock."""
    clock = E._ReplayClock()
    p = E._no_wait_pacer(clock)
    t0 = clock()
    p.sleep(2.0)
    p.backoff(5)
    assert p.clock is clock and clock() - t0 == 7.0 and clock.slept == [2.0, 5.0]
    p.wait()                                            # interval 0: never sleeps
    assert clock() - t0 == 7.0
    assert E._replay_budget(clock).clock is clock


@pg_only
def test_f3_one_recorded_row_replays_identically_on_a_fast_and_a_slow_machine(C, E, C2C, tmp_path, litkb_pg_base,
                                                                              monkeypatch):
    """CONSTRUCTED recording, LIVE shape: routes (wayback, ia), both on archive.org; the availability API answers
    503 Retry-After 1 once — archive.org cools 1 s, the ladder sits out its 2 s retry wait (exempt), retries, and the
    IA rung then ASKS archive.org. The same row is replayed TWICE through the replay's acquirer: at full speed, and
    with a real 1.5 s stall before the IA rung (a slow machine). Identical answers must give identical rows, and the
    rows the recording shows. On the real clock (the pre-fix pacer, row FX8b) the fast replay refuses IA as
    `skipped/backoff_window` and the slow one asks it; on a clock that never moves (row FX8a) both refuse it."""
    from litkb.acquire import ia
    from litkb.acquire import run as R

    _psycopg, conn, _ran = litkb_pg_base
    doi = tag = "10.5555/constructed-fix8-f3"
    idx, bodies = tmp_path / "cas" / "index.jsonl", tmp_path / "bodies"
    arms = {}
    try:
        _reset(conn)
        with monkeypatch.context() as mp:
            _OpenerWorld(_stage_e_world({})).install(mp)
            w = C2C.World(conn, tmp_path / "rec")
            try:
                ws = w.ws("fix8-f3-rec")
                work = _fixed_work(w, ws, doi)
                rec = C.Cassette(idx, "record", bodies=bodies)
                rec.begin_row(tag)
                with C.use(rec):
                    R.acquire(w.writer, ws, w.tokens[ws], work, store=w.store, agent="fix8", session="fix8-rec",
                              pacer=_LiveClock().pacer(), printer=lambda *a, **k: None, routes=("wayback", "ia"),
                              pacing={})
                arms["recorded"] = _attempts(w, work)
            finally:
                w.close()
        real_client = ia._client
        for speed in ("fast", "slow"):
            _reset(conn)
            with monkeypatch.context() as mp:
                if speed == "slow":
                    def slow_client():
                        time.sleep(1.5)               # a slow machine: real time passes before IA is asked
                        return real_client()
                    mp.setattr(ia, "_client", slow_client)
                w = C2C.World(conn, tmp_path / speed)
                try:
                    ws = w.ws(f"fix8-f3-{speed}")
                    work = _fixed_work(w, ws, doi)
                    rep = C.Cassette(idx, "replay", bodies=bodies)
                    rep.begin_row(tag)
                    with C.use(rep), C.SocketGuard(allow_hosts=(), label="fix8 F3 replay"):
                        E._ladder_acquirer({"routes": ["wayback", "ia"]})(
                            w.writer, ws, w.tokens[ws], work, store=w.store, agent="fix8", session=f"fix8-{speed}")
                    arms[speed] = _attempts(w, work)
                    arms[speed + "-stale"] = rep.stale()
                finally:
                    w.close()
    finally:
        _reset(conn)
    rec_rows = arms["recorded"]
    assert [a[:2] for a in rec_rows if a[0] == "wayback"] == [("wayback", "api-error"), ("wayback", "blocked")], rec_rows
    assert [a[:2] for a in rec_rows if a[0] == "ia"] == [("ia", "not-in-archive")], ("the recording asks IA", rec_rows)
    assert arms["fast"] == arms["slow"] == rec_rows, arms
    assert arms["fast-stale"] == arms["slow-stale"] == {"unplayed": [], "misses": []}, arms


# ── D42: the policy a recording was made under, for its own row only ─────────────────────────────────

def test_d42_the_replay_budget_is_the_whole_ladders_the_live_hunt_resolved(E):
    """The live hunt asked the WHOLE ladder (`hunt._default_acquire`), so its budget's attempts and concurrency were
    resolved over every registered rung — every ladder-1 register row recorded 48 / 8 / 505 s. A replay asks only
    its row's routes and must not shrink the budget to them."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    whole = P.LadderBudget().resolved(R.ladder_rungs(R.ladder_routes()))
    b = E._replay_budget(E._ReplayClock()).resolved(R.ladder_rungs(("eartharxiv", "arxiv")))
    assert (b.seconds, b.attempts, b.concurrency) == (whole.seconds, whole.attempts, whole.concurrency), b
    narrow = P.LadderBudget().resolved(R.ladder_rungs(("eartharxiv", "arxiv")))
    assert narrow.attempts < b.attempts                 # what resolving over the row's routes alone gives


def test_d42_a_switched_off_line_is_switched_on_only_for_a_replayed_row_that_asked_its_route(C, E, tmp_path):
    """`_recorded_policy` switches on EXACTLY the lines of the routes the row names that carry an `off_why`, and
    ONLY under a REPLAY cassette. No cassette (a live hunt), a RECORD cassette (the live pass) or a replayed row that
    does not name the route: today's table, unchanged, nothing named. The module table is never edited."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R  # noqa: F401 — the rungs' own lines are in the table first

    table = P.POLICY
    off = [(p.route, p.host) for p in table if p.off_why]
    assert ("commoncrawl", "index.commoncrawl.org") in off and ("commoncrawl", "data.commoncrawl.org") in off
    assert E._recorded_policy(("commoncrawl",)) == (table, [])                                   # no cassette
    with C.use(_cas_file(C, tmp_path / "rec" / "index.jsonl", "record")):
        assert E._recorded_policy(("commoncrawl",)) == (table, [])                               # the live pass
    with C.use(_cas_file(C, tmp_path / "rep" / "index.jsonl", "replay")):
        assert E._recorded_policy(("wayback", "ia")) == (table, [])                              # not named
        policy, on = E._recorded_policy(("wayback", "commoncrawl"))
    assert [(s["route"], s["host"]) for s in on] == [x for x in off if x[0] == "commoncrawl"], on
    assert all(s["off_why"] == P.COMMONCRAWL_OFF_WHY and "D42" in s["ruling"] for s in on), on
    assert [p for p in policy if p.off_why] == [p for p in table if p.off_why and p.route != "commoncrawl"]
    assert [(p.route, p.host, p.tier, p.why) for p in policy] == [(p.route, p.host, p.tier, p.why) for p in table]
    assert P.POLICY is table


@pg_only
def test_d42_a_replayed_row_asks_what_its_recording_asked_and_a_live_decision_still_refuses(
        C, E, C2C, HA, tmp_path, litkb_pg_base, monkeypatch):
    """On the REAL ladder. A CONSTRUCTED recording made while Common Crawl was ON (the world of E07's and E20's
    takes, before D39/D40's mid-run switch): the rung asked the crawl list and the index. Replayed through the
    replay's acquirer the route is asked again from the cassette (not `skipped/policy_refused`), nothing is left
    unplayed, and both of its lines are named as switched on for THIS row. After it, a live PolicyDecision for
    Common Crawl still refuses with the measured reason, the same acquirer under a RECORD cassette (a live pass) is
    refused before any request, and the replay summary names the switch per row."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    _psycopg, conn, _ran = litkb_pg_base
    doi = tag = "10.5555/constructed-fix8-d42"
    idx, bodies = tmp_path / "cas" / "index.jsonl", tmp_path / "bodies"
    table = P.POLICY
    world = _OpenerWorld(_cc_world).install(monkeypatch)
    try:
        # the recording: Common Crawl ON (the live pass before the switch)
        _reset(conn)
        w = C2C.World(conn, tmp_path / "rec")
        try:
            ws = w.ws("fix8-d42-rec")
            work = _fixed_work(w, ws, doi)
            rec = C.Cassette(idx, "record", bodies=bodies)
            rec.begin_row(tag)
            with C.use(rec), C2C.route_switched_on("commoncrawl"):
                R.acquire(w.writer, ws, w.tokens[ws], work, store=w.store, agent="fix8", session="fix8-rec",
                          pacer=_LiveClock().pacer(), printer=lambda *a, **k: None, routes=("commoncrawl",),
                          pacing={})
            recorded = _attempts(w, work)
        finally:
            w.close()
        assert recorded == [("commoncrawl", "not-in-archive", "not_in_corpus", [200, 404], False)], recorded
        assert len(rec.recorded) == 2

        # the replay: switched on for this row, answered from the recording, no host asked
        _reset(conn)
        asked = len(world.asked)
        w = C2C.World(conn, tmp_path / "rep")
        try:
            ws = w.ws("fix8-d42-rep")
            work = _fixed_work(w, ws, doi)
            rep = C.Cassette(idx, "replay", bodies=bodies)
            rep.begin_row(tag)
            acq = E._ladder_acquirer({"routes": ["commoncrawl"]})
            with C.use(rep), C.SocketGuard(allow_hosts=(), label="fix8 D42 replay"):
                acq(w.writer, ws, w.tokens[ws], work, store=w.store, agent="fix8", session="fix8-rep")
            replayed = _attempts(w, work)
        finally:
            w.close()
        assert replayed == recorded, replayed
        assert rep.stale() == {"unplayed": [], "misses": []}, rep.stale()
        assert len(world.asked) == asked
        assert [(s["route"], s["host"]) for s in acq.switched] == [
            ("commoncrawl", "index.commoncrawl.org"), ("commoncrawl", "data.commoncrawl.org")], acq.switched
        # never global: the table is today's again, and a live decision refuses with the measured reason
        assert P.POLICY is table
        d = P.decide("commoncrawl", "index.commoncrawl.org")
        assert (d.allowed, d.reason) == (False, P.COMMONCRAWL_OFF_WHY), d

        # never reachable from a live run: the same acquirer under a RECORD cassette is refused before any request
        _reset(conn)
        asked = len(world.asked)
        w = C2C.World(conn, tmp_path / "live")
        try:
            ws = w.ws("fix8-d42-live")
            work = _fixed_work(w, ws, doi)
            live_acq = E._ladder_acquirer({"routes": ["commoncrawl"]})
            with C.use(C.Cassette(tmp_path / "cas2" / "index.jsonl", "record", bodies=bodies)):
                live_acq(w.writer, ws, w.tokens[ws], work, store=w.store, agent="fix8", session="fix8-live")
            live = _attempts(w, work)
        finally:
            w.close()
        assert live == [("commoncrawl", "skipped", "policy_refused", [], None)], live
        assert live_acq.switched == [] and len(world.asked) == asked

        # the replay summary names the switch, per row. A hunt-driven replay: the fresh work names no dead URL, so
        # the switched-on rung skips `no_identifier` (asked nothing) — never `policy_refused`
        _reset(conn)
        row = {"id": "CCREC", "class": "constructed-d42", "ref": doi, "ref_scheme": "doi",
               "expected": {"state": "held", "reason": "not-acquired"}, "live": {"mode": "replay-only", "spend": False},
               "replay": {"inputs": {"spend": True, "extract": False}, "seed": None,
                          "registry": {"kind": "record", "title": "A constructed D42 work", "author": "Fixeight",
                                       "year": 2020},
                          "fetch": {"kind": "explode"}, "extract": {"kind": "off"},
                          "routes": {"kind": "ladder", "routes": ["commoncrawl"], "cassette": str(idx),
                                     "bodies": str(bodies)}}}
        s = HA.build_replay_summary(conn, register={"kind": "litkb-hunt-edge-cases", "rows": [row]},
                                    register_path=None, db=conn.info.dbname, workdir=tmp_path / "sum",
                                    guard=C.SocketGuard(allow_hosts=(), label="fix8 D42 summary"))
        assert [(p["row"], p["route"], p["host"]) for p in s["policy_switches"]] == [
            ("CCREC", "commoncrawl", "index.commoncrawl.org"), ("CCREC", "commoncrawl", "data.commoncrawl.org")], s
        csv_row = E.existing_rows(s["replay_csv"])[0]
        assert '"route":"commoncrawl","status":"skipped","sub_status":"no_identifier"' in csv_row["route_detail"], \
            csv_row["route_detail"]
        assert P.POLICY is table
    finally:
        _reset(conn)


# ── Q1: the world the live row met on disk (register-editor Q1) ──────────────────────────────────────

def _world_row(doi, title, author, mirrors, world=None):
    return {"id": "WORLD", "class": "constructed-replay-world", "ref": doi, "ref_scheme": "doi",
            "expected": {"state": "held", "reason": "duplicate-held"}, "live": {"mode": "replay-only", "spend": False},
            "replay": {"inputs": {"spend": True, "extract": False}, "seed": None,
                       "registry": {"kind": "record", "title": title, "author": author, "year": 2026},
                       "fetch": {"kind": "explode"}, "extract": {"kind": "off"},
                       "routes": {"kind": "ladder", "routes": ["scihub"], "mirrors": list(mirrors)},
                       **({"world": world} if world is not None else {})}}


def _landing(doi):
    return (f'<html><head><meta name="citation_pdf_url" content="/files/{doi}.pdf"></head>'
            "<body>a constructed mirror page</body></html>").encode()


@pg_only
def test_q1_a_row_whose_bytes_were_on_disk_replays_duplicate_held_only_with_its_world(C, E, HA, tmp_path,
                                                                                    litkb_pg_base):
    """CONSTRUCTED on a loopback 'mirror', the shape of E03: the LIVE world already held the paper on disk (an
    unbound topic-folder file), so the recorded row answered held/duplicate-held. Replayed with no world, the fresh
    store lacks the file and the same bytes land and bind (the disagreement Q1 predicted, measured here); replayed
    with `replay.world.disk` naming that file, the replay's store holds it again — written from the row's recorded
    bytes — and the row answers held/duplicate-held with the same attempts, the seed named in the summary."""
    _psycopg, conn, _ran = litkb_pg_base
    title, author = "A replay world work for S4.5 builder-fix8", "Worldseed"
    doi = "10.5555/constructed-fix8-world"
    pdf = E._pdf_bytes(title, author, salt="fix8-world")
    sha = hashlib.sha256(pdf).hexdigest()
    idx, bodies = tmp_path / "cas" / "index.jsonl", tmp_path / "bodies"
    rel = "Validation/held-copy-fix8.pdf"
    try:
        _reset(conn)
        with _Server({f"/{doi}": (200, "text/html", _landing(doi)),
                      f"/files/{doi}.pdf": (200, "application/pdf", pdf)}) as srv:
            row = _world_row(doi, title, author, [srv.base])
            held = tmp_path / "t1" / "lit_WORLD" / rel         # CONSTRUCTED: the live disk held the paper already
            held.parent.mkdir(parents=True, exist_ok=True)
            held.write_bytes(pdf)
            (live,) = E.run_replay({"kind": "litkb-hunt-edge-cases", "rows": [row]}, tmp_path / "live.csv",
                                   db=conn.info.dbname, tmp=str(tmp_path / "t1"), conn=conn,
                                   cassette=C.Cassette(idx, "record", bodies=bodies))[2]
        assert (live["observed_state"], live["observed_reason"]) == ("held", "duplicate-held"), live

        def replay(r, wd):
            _reset(conn)
            return HA.build_replay_summary(conn, register={"kind": "litkb-hunt-edge-cases", "rows": [r]},
                                           register_path=None, db=conn.info.dbname, workdir=tmp_path / wd,
                                           cassette=C.Cassette(idx, "replay", bodies=bodies),
                                           guard=C.SocketGuard(allow_hosts=(), label="fix8 Q1 replay"))
        s0 = replay(row, "t2")
        (r0,) = s0["rows"]
        assert (r0["observed_state"], r0["observed_reason"]) == ("bound-unextracted", "fresh-bound"), r0
        assert s0["world_seeds"] == []
        with_world = copy.deepcopy(row)
        with_world["replay"]["world"] = {"disk": [{"rel_path": rel, "sha256": sha, "evidence": "CONSTRUCTED"}]}
        s1 = replay(with_world, "t3")
        (r1,) = s1["rows"]
        assert (r1["observed_state"], r1["observed_reason"], r1["traceback"]) == ("held", "duplicate-held", "0"), r1
        assert s1["world_seeds"] == [{"row": "WORLD", "rel_path": rel, "sha256": sha, "bytes": len(pdf)}], s1
        assert (HA.count_network(s1), HA.count_stale(s1), HA.count_disagreeing(s1)) == (0, 0, 0), s1
        replayed = E.existing_rows(s1["replay_csv"])[0]
        assert replayed["attempt_statuses"] == live["attempt_statuses"], (replayed, live)
    finally:
        _reset(conn)


@pg_only
@pytest.mark.parametrize("case", ["another-rows-bytes", "outside-the-store", "body-missing"])
def test_q1_a_world_the_recording_does_not_hold_refuses_the_row_before_any_hunt(C, E, HA, tmp_path, litkb_pg_base,
                                                                              case):
    """Fail-closed: a `replay.world.disk` seed whose bytes THIS ROW'S recording did not serve (another row's body
    stored under that sha256), whose rel_path leaves the replay's store, or whose stored body is gone REFUSES the row
    — a named traceback, nothing written outside the store, nothing hunted."""
    _psycopg, conn, _ran = litkb_pg_base
    title, author = "A replay world refusal work for S4.5 builder-fix8", "Worldseed"
    doi = "10.5555/constructed-fix8-world-refused"
    pdf = E._pdf_bytes(title, author, salt="fix8-world-refused")
    other = E._pdf_bytes("Another row's paper", "Other", salt="fix8-other")
    idx, bodies = tmp_path / "cas" / "index.jsonl", tmp_path / "bodies"
    try:
        _reset(conn)
        with _Server({f"/{doi}": (200, "text/html", _landing(doi)),
                      f"/files/{doi}.pdf": (200, "application/pdf", pdf)}) as srv:
            row = _world_row(doi, title, author, [srv.base])
            E.run_replay({"kind": "litkb-hunt-edge-cases", "rows": [row]}, tmp_path / "live.csv",
                         db=conn.info.dbname, tmp=str(tmp_path / "t1"), conn=conn,
                         cassette=C.Cassette(idx, "record", bodies=bodies))
        # ANOTHER row of the same index served other bytes (a PDF: stored under its sha256)
        o = C.Cassette(idx, "record", bodies=bodies)
        o.begin_row("10.5555/constructed-fix8-another-row")
        o.record(_FakeClient(), "http://127.0.0.1:9/other.pdf", {"Accept": "application/pdf"}, True, None,
                 (200, {"Content-Type": "application/pdf"}, other))
        _reset(conn)
        store = bodies
        seed = {"rel_path": "Validation/seeded-fix8.pdf", "sha256": hashlib.sha256(pdf).hexdigest()}
        if case == "another-rows-bytes":
            seed["sha256"] = hashlib.sha256(other).hexdigest()
        elif case == "outside-the-store":
            seed["rel_path"] = "../escaped-fix8.pdf"
        else:
            store = tmp_path / "bodies-copy"
            shutil.copytree(bodies, store)
            (store / seed["sha256"][:2] / f"{seed['sha256']}.bin").unlink()
        row["replay"]["world"] = {"disk": [dict(seed, evidence="CONSTRUCTED")]}
        s = HA.build_replay_summary(conn, register={"kind": "litkb-hunt-edge-cases", "rows": [row]},
                                    register_path=None, db=conn.info.dbname, workdir=tmp_path / "t2",
                                    cassette=C.Cassette(idx, "replay", bodies=store),
                                    guard=C.SocketGuard(allow_hosts=(), label="fix8 Q1 refusal"))
        (r,) = s["rows"]
        assert r["traceback"] == "1" and "the replay world could not be seeded" in r["message"], r
        csv_row = E.existing_rows(s["replay_csv"])[0]
        assert csv_row["attempt_statuses"] == "" and csv_row["work_id"] == "", csv_row      # never hunted
        assert s["world_seeds"] == [] and HA.count_disagreeing(s) == 1
        assert not (tmp_path / "t2" / "escaped-fix8.pdf").exists()
        if case == "body-missing":
            assert "CassetteBodyMissing" in r["message"] and HA.count_stale(s) >= 1, (r, s["stale"])
    finally:
        _reset(conn)

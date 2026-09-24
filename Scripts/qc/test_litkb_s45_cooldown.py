"""litkb S4.5 decisions D41 + D44 + D45 (builder-fix7): the ladder's IN-RUN cool-down per HOST, shared by every route,
and no row sits out a long wait.

Measured cause (the live ladder-1 run, 2026-09-24, read back as litkb_reader: the ledger's wayback rows and the
RECORD-mode cassette): after ~45 rows archive.org answered 429 (9 times, none with Retry-After); the in-run AIMD
delay doubled to its 300 s ceiling, and every later work's wayback ask first SLEPT that delay (`run._pace`) and then
again before its scheduled retry, which the 505 s ladder budget refused — ~10 min a row, a host that asked us to slow
down asked again by every work.

What these tests hold, on the REAL ladder (`litkb.acquire.run.acquire` / `measure` / `hunt._default_acquire`) on a
WORKER database with stub clients and a CONTROLLABLE clock (the pacer's: it advances only by the pacer's own sleeps
and by the test):
  * a 429 cools the HOST that answered it (D44), for EVERY route (D45: Wayback's 429 on archive.org gates the IA
    rung's archive.org request; another host is not gated): for a single-host rung (Wayback's availability API) the
    next work's rung is one `skipped/backoff_window` row whose `detail.cooldown` names the host, the route whose
    answer cooled it, the triggering
    attempt, its status and code, and cool_until — and NO request reaches the stub; after cool_until the host is
    asked again and a success decays the AIMD delay (Retry-After honoured, capped at 300 s);
  * a MULTI-host rung keeps asking its other hosts (D44): landing skips only the cooling host's candidate (recorded
    in `detail.landing.cooled` and `detail.cooldown_skipped`) and asks the other host's, and its row keeps the answering
    host's status but is `retriable` (D45: never a permanent miss while a candidate was untried); with every
    candidate on a cooling host it is a retriable `api-error`; Stage B's candidate loop and open access's locations
    skip the same way;
  * a 503 cools it too (no Retry-After: the AIMD delay; the short in-row retry is taken and ITS answer is the trigger);
  * a 403 never cools a route (guard 29), nor does a bot challenge served at 503 (guard 3: a refusal of one work);
  * no row sits out a long wait: a scheduled retry whose wait is over `backoff.IN_ROW_WAIT_MAX_S` is not taken (the
    original stays `retriable`, unretried) and the route cools instead; a pacing wait is capped at the same threshold;
  * a FOLLOWED redirect (auditor-fix7 F1): every hop is asked of the gate — a hop to a cooling host is not followed —
    and the answer is credited to the host at the END of the chain, never the redirector (a loopback server);
  * a bot challenge never cools its host by EITHER cause (auditor-fix7 F2: the long-wait cause too);
  * the independent auditor's own checks (auditor-fix7, adopted below): both directions of the cross-route gate
    through the real `netutil.Client`, a partly-cooled open access row, a longer cool-down kept, the 2 s floor, a
    gate-stopped landing that already had an answer, the in-row boundary, the long-wait host;
  * the state is the run's process state: the run driver's hunt rows and measure rows share `run.PACING` — through
    the REAL `netutil.Client.get`, which consults the request gate — and a new process (a fresh `PACING`) starts cold.

Every input here is CONSTRUCTED (salted admissions, a never-archived URL, stub answers, AIMD states standing in for the
measured live ones). Each guard has a mutation row in qc/instruments/litkb_p2_mutations.py (C1A44-C1A78) that turns
this file red by a WORSE ANSWER. No test touches the network.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_cooldown.py -q
"""
import datetime
import http.server
import importlib.util
import json
import threading
import types
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
INSTR = SCRIPTS / "qc" / "instruments"
pg_only = pytest.mark.requires_litkb_pg


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C2C = _load("_litkb_hardening_c2c_for_cooldown", INSTR / "litkb_hardening_c2c.py")
OA_URL = "https://oa.constructed.invalid/paper.pdf"


class Clock:
    """CONSTRUCTED: the ladder's pacer clock. It moves only when the pacer sleeps (every sleep is recorded in
    `slept`) or when the test advances it — so a cool-down's expiry is the test's to decide."""

    def __init__(self, t=1000.0):
        self.t, self.slept = t, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(float(s))
        self.t += s

    def pacer(self):
        from litkb.netutil import Pacer

        return Pacer(interval=0, sleep=self.sleep, clock=self)


class FailingClient:
    """CONSTRUCTED: FAILS on any request — a cooling route must never be asked. The call is recorded BEFORE it
    raises, so a request the ladder's route boundary swallowed (`run._call_rung`) is still seen."""
    base = ""

    def __init__(self):
        self.calls = []

    def get(self, url, *a, **k):
        self.calls.append(url)
        raise AssertionError(f"a request reached a cooling route: {url}")


def _answers(status, retry_after=None, body=b"CONSTRUCTED answer"):
    """CONSTRUCTED: every Wayback host (the availability API and the CDX server) answers `status`."""
    hd = {"Content-Type": "text/html", **({"Retry-After": retry_after} if retry_after else {})}
    return C2C.StubClient({"archive.org": (status, hd, b"<html><body>" + body + b"</body></html>")})


def _unpaywall(url):
    return 200, {"Content-Type": "application/json"}, json.dumps(
        {"is_oa": True, "oa_status": "bronze", "best_oa_location": {"url": url, "host_type": "publisher"},
         "oa_locations": [{"url": url, "host_type": "publisher"}]}).encode()


@pytest.fixture
def world(litkb_pg_base, tmp_path):
    _psycopg, conn, _ran = litkb_pg_base
    w = C2C.World(conn, tmp_path)
    yield w
    w.close()


def _works(world, ws, n):
    out = []
    for _ in range(n):
        work = world.work(ws)
        world.dead_link(ws, work, C2C.CONSTRUCTED_DEAD_URL)      # the dead URL Stage E1 is asked about
        out.append(work)
    return out


def _ladder(world, ws, work, clients, clock, pacing, *, routes=("wayback",), **kw):
    from litkb.acquire import run

    return run.acquire(world.writer, ws, world.tokens[ws], work, store=world.store, agent="fix7", session="fix7-1",
                       clients=clients, pacer=clock.pacer(), printer=lambda *a, **k: None, routes=routes,
                       pacing=pacing, **kw)


def _rows(world, work, route="wayback"):
    return world.owner.execute(
        "SELECT id::text, status, sub_status, http_codes, retriable, retry_of::text, detail "
        "FROM litkb.acquisition_attempts WHERE work_id = %s AND route = %s ORDER BY at, id",
        (work["work_id"], route)).fetchall()


def _one(world, work, route="wayback"):
    """-> the work's ONE row on `route` — asserted, so a second row (a retry the ladder should not have taken) is a
    red ANSWER, never an unpacking error."""
    rows = _rows(world, work, route)
    assert len(rows) == 1, ("expected exactly one row", rows)
    return rows[0]


def _hosts(pacing):
    """-> the run's ONE host table (S4.5 decision D45) — asserted, so a ladder that kept none (or one per route) is a
    red ANSWER, never a KeyError."""
    from litkb.acquire import backoff

    assert backoff.HOSTS_KEY in pacing, ("no run-wide host table in the ladder's pacing state",
                                         sorted(str(k) for k in pacing))
    return pacing[backoff.HOSTS_KEY]


def _skip(world, work, route="wayback"):
    """-> the work's ONE row on `route`, asserted to be the cool-down's skip: its `detail.cooldown`."""
    rows = _rows(world, work, route)
    assert [(r[1], r[2]) for r in rows] == [("skipped", "backoff_window")], rows
    return rows[0][6]["cooldown"]


# ── a 429 ───────────────────────────────────────────────────────────────────────────────────

@pg_only
@pytest.mark.parametrize("retry_after,wait_s,source", [("120", 120.0, "retry-after"),
                                                        ("3600", 300.0, "retry-after-capped")])
def test_a_429_cools_the_route_and_the_next_work_asks_nothing_until_cool_until(world, retry_after, wait_s, source):
    """Work 1's Wayback answers 429 with Retry-After: ONE row (`api-error`, retriable) and no in-row retry — the wait is
    over the in-row threshold and is not sat out (no sleep at all). Work 2, same run, same clock: `skipped/
    backoff_window`, the detail naming the route, work 1's attempt, its status and code, the wait and cool_until — and
    its FAILING client saw no request. Past cool_until, work 3 asks the route again (paced by the AIMD delay alone) and
    its answer decays that delay. A Retry-After over the 300 s ceiling is capped at it."""
    from litkb.acquire import backoff

    clock, pacing = Clock(), {}
    ws = world.ws("fix7-429")
    w1, w2, w3 = _works(world, ws, 3)
    limited = _answers(429, retry_after, b"CONSTRUCTED 429 Too Many Requests")
    _ladder(world, ws, w1, {"wayback": limited}, clock, pacing)
    r1 = _one(world, w1)
    assert (r1[1], list(r1[3]), r1[4], r1[5]) == ("api-error", [429], True, None), r1
    assert len(limited.calls) == 1 and clock.slept == [], (limited.calls, clock.slept)
    failing = FailingClient()
    _ladder(world, ws, w2, {"wayback": failing}, clock, pacing)
    assert failing.calls == []
    cd = _skip(world, w2)
    assert (cd["trigger_route"], cd["host"], cd["trigger_attempt_id"], cd["trigger_status"], cd["status_code"],
            cd["cause"]) == ("wayback", "archive.org", r1[0], "api-error", 429, "rate-limit"), cd
    assert (cd["wait_s"], cd["wait_source"], cd["retry_after_s"]) == (wait_s, source, float(retry_after)), cd
    span = datetime.datetime.fromisoformat(cd["cool_until"]) - datetime.datetime.fromisoformat(cd["cooled_at"])
    assert span.total_seconds() == wait_s and "D41" in cd["ruling"], cd
    clock.t += wait_s                                           # cool_until has passed
    never = C2C.constructed_never_archived()
    _ladder(world, ws, w3, {"wayback": never}, clock, pacing)
    r3 = _one(world, w3)
    assert never.calls and (r3[1], r3[2]) == ("blocked", "not_found"), (r3, never.calls)
    # the AIMD pace (2 s) before work 2's launch and before work 3's: the rung is launched and its request gate —
    # not a route-level skip — stops the request to the cooling host (D44)
    assert clock.slept == [backoff.AIMD_DECAY_S * backoff.AIMD_MULTIPLIER] * 2, clock.slept
    assert pacing["wayback"].delay_s == 1.0 and _hosts(pacing).cooling("archive.org") is None   # decayed


# ── a 503 ───────────────────────────────────────────────────────────────────────────────────

@pg_only
def test_a_503_cools_the_host_too_and_its_retry_s_answer_is_the_trigger(world):
    """A 503 with Retry-After 5: the wait (5 s) is under the in-row threshold, so the ONE scheduled retry is taken
    (after 5 s); it answers 503 again and cools the host for another 5 s from then — the trigger the next work's
    skip names is the RETRY's attempt (work 2's AIMD pace, 4 s, ends inside it). Past cool_until the host is asked
    again."""
    clock, pacing = Clock(), {}
    ws = world.ws("fix7-503")
    w1, w2, w3 = _works(world, ws, 3)
    _ladder(world, ws, w1, {"wayback": _answers(503, "5", b"CONSTRUCTED 503 busy")}, clock, pacing)
    rows = _rows(world, w1)
    assert [(r[1], list(r[3]), r[4]) for r in rows] == [("api-error", [503], True)] * 2 and rows[1][5] == rows[0][0]
    assert clock.slept == [5.0], clock.slept
    failing = FailingClient()
    _ladder(world, ws, w2, {"wayback": failing}, clock, pacing)
    assert failing.calls == []
    cd = _skip(world, w2)
    assert (cd["host"], cd["trigger_attempt_id"], cd["status_code"], cd["wait_s"], cd["wait_source"],
            cd["retry_after_s"]) == ("archive.org", rows[1][0], 503, 5.0, "retry-after", 5.0), cd
    clock.t += 5.0
    never = C2C.constructed_never_archived()
    _ladder(world, ws, w3, {"wayback": never}, clock, pacing)
    assert never.calls and _rows(world, w3)[0][1] == "blocked", _rows(world, w3)


# ── what never cools a route ────────────────────────────────────────────────────────────────

@pg_only
def test_a_403_never_cools_the_route(world):
    """Guard 29: a 403 is a refusal about ONE work (MDPI answers 403 per article) and climbs that work's own refusal
    ladder only. Work 1's Wayback hosts answer 403 — with a CONSTRUCTED Retry-After, so a cool-down wrongly started
    would be visible for 120 s — and work 2, same run, same clock, IS asked."""
    clock, pacing = Clock(), {}
    ws = world.ws("fix7-403")
    w1, w2 = _works(world, ws, 2)
    _ladder(world, ws, w1, {"wayback": _answers(403, "120", b"CONSTRUCTED 403 Forbidden")}, clock, pacing)
    r1 = _one(world, w1)
    assert (r1[1], list(r1[3])[-1], r1[4]) == ("api-error", 403, False), r1
    never = C2C.constructed_never_archived()
    _ladder(world, ws, w2, {"wayback": never}, clock, pacing)
    assert never.calls, "a 403 cooled the route: work 2 never asked it"
    assert [(r[1], r[2]) for r in _rows(world, w2)] == [("blocked", "not_found")]

    assert not _hosts(pacing).hosts


@pg_only
def test_a_bot_challenge_served_at_503_never_cools_the_route(world, monkeypatch):
    """Guard 3: a bot challenge is a refusal of THIS work (`blocked`, dead for the route within the run), not a rate
    limit — whatever its code. Open access (a multi-host route: Unpaywall and every publisher) is served a CONSTRUCTED
    "Just a moment..." page at 503 with a CONSTRUCTED Retry-After of 120 s; the next work's open access IS asked."""
    from litkb.acquire import open_access

    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "fix7-test@example.invalid")

    def challenge():
        page = (b"<html><head><title>Just a moment...</title></head><body>CONSTRUCTED challenge "
                + uuid.uuid4().hex.encode() + b"</body></html>")
        return C2C.StubClient({"api.unpaywall.org": _unpaywall(OA_URL),
                               "oa.constructed.invalid": (503, {"Content-Type": "text/html", "Retry-After": "120"},
                                                          page)})

    clock, pacing = Clock(), {}
    ws = world.ws("fix7-challenge")
    w1, w2 = world.work(ws), world.work(ws)
    _ladder(world, ws, w1, {"open_access": challenge()}, clock, pacing, routes=("open_access",))
    r1 = _one(world, w1, "open_access")
    assert (r1[1], r1[2], list(r1[3])[-1]) == ("blocked", "challenge_or_bot_check", 503), r1
    second = challenge()
    _ladder(world, ws, w2, {"open_access": second}, clock, pacing, routes=("open_access",))
    assert any("oa.constructed.invalid" in u for u in second.calls), \
        ("a challenge cooled its host: work 2 never asked it", second.calls)
    assert [r[1] for r in _rows(world, w2, "open_access")] == ["blocked"]


# ── no row sits out a long wait ─────────────────────────────────────────────────────────────

@pg_only
def test_an_in_row_retry_never_sits_out_a_long_wait_and_the_route_cools_instead(world):
    """A CONSTRUCTED AIMD state standing in for the live Marsan_2008 row (Wayback's CDX answered 504 after the delay
    had reached ~57 s): the route is paced for the in-row threshold only (10 s, not 57), answers 504, the delay
    doubles to 114 s — over the threshold, so NO retry is scheduled (no second row, no 114 s sleep; the original stays
    `retriable`) and the route cools for 114 s instead (cause `long-wait`). Work 2 — asked with `retry_dead`, which
    re-asks a dead route for ONE work and never lifts a host's cool-down — is skipped. After 114 s, work 3 asks."""
    from litkb.acquire import backoff

    clock = Clock()
    pacing = {"wayback": backoff.Aimd(delay_s=57.0)}
    ws = world.ws("fix7-long")
    w1, w2, w3 = _works(world, ws, 3)
    _ladder(world, ws, w1, {"wayback": _answers(504, None, b"CONSTRUCTED 504 gateway timeout")}, clock, pacing)
    rows = _rows(world, w1)
    assert [(r[1], list(r[3]), r[4], r[5]) for r in rows] == [("api-error", [504], True, None)], rows
    assert clock.slept == [backoff.IN_ROW_WAIT_MAX_S], clock.slept
    failing = FailingClient()
    _ladder(world, ws, w2, {"wayback": failing}, clock, pacing, retry_dead=True)
    assert failing.calls == []
    cd = _skip(world, w2)
    assert (cd["cause"], cd["status_code"], cd["wait_s"], cd["wait_source"], cd["trigger_attempt_id"]) == \
        ("long-wait", 504, 114.0, "aimd", rows[0][0]), cd
    clock.t += 114.0
    never = C2C.constructed_never_archived()
    _ladder(world, ws, w3, {"wayback": never}, clock, pacing)
    # paced 10 s before each of the three launches (work 2's gate-stopped one included), never 57 or 114
    assert never.calls and clock.slept == [backoff.IN_ROW_WAIT_MAX_S] * 3, (never.calls, clock.slept)


@pg_only
def test_a_pacing_wait_is_never_sat_out_past_the_in_row_threshold(world):
    """A CONSTRUCTED AIMD state standing in for the live Liu_2019 row (its wayback ask launched at elapsed 236.7 s,
    after a 224 s pace, and was answered 200): the ask is paced for the in-row threshold, never the whole delay."""
    from litkb.acquire import backoff

    clock = Clock()
    pacing = {"wayback": backoff.Aimd(delay_s=224.0)}
    ws = world.ws("fix7-pace")
    (w1,) = _works(world, ws, 1)
    never = C2C.constructed_never_archived()
    _ladder(world, ws, w1, {"wayback": never}, clock, pacing)
    assert never.calls and clock.slept == [backoff.IN_ROW_WAIT_MAX_S], clock.slept
    assert pacing["wayback"].delay_s == 223.0 and not _hosts(pacing).hosts


# ── where the state lives ───────────────────────────────────────────────────────────────────

@pg_only
def test_the_run_driver_s_hunt_and_measure_rows_share_the_cooldown_and_a_new_process_starts_cold(world, monkeypatch):
    """The live path. The ladder-1 run driver runs every row in ONE process: a hunt row spends through the hunt's own
    acquirer (`hunt._default_acquire`), a measure row through `run.measure`; neither passes `pacing` nor clients, so
    both read the process's `run.PACING` and the rung builds its OWN `netutil.Client` — whose `get` consults the
    request gate (D44). A 429 met by a hunt row cools archive.org for the measure row after it (no request reaches the
    client's transport); a NEW process — a fresh `run.PACING` — starts cold and asks at once. The ladder is narrowed
    to E1; the client's transport (`Client._raw_get`), the pacer and the process state are patched (no socket; this
    test never touches the real process state)."""
    from litkb import hunt as H
    from litkb import netutil
    from litkb.acquire import run, wayback

    clock = Clock()
    sent, answer = [], {"now": None}

    def raw_get(self, url, accept, timeout, follow, data=None, headers=None):
        sent.append(url)
        return answer["now"](url)

    monkeypatch.setattr(netutil.Client, "_raw_get", raw_get)
    monkeypatch.setattr(wayback, "_client", lambda: netutil.Client(base=""))
    monkeypatch.setattr(run, "Pacer", lambda *a, **k: clock.pacer())
    monkeypatch.setattr(run, "PACING", {})
    monkeypatch.setattr(run, "ladder_routes", lambda rungs=None: ("wayback",))
    ws = world.ws("fix7-driver")
    w1, w2, w3 = _works(world, ws, 3)
    kw = {"store": world.store, "agent": "fix7", "session": "fix7-1"}
    answer["now"] = lambda url: (429, {"Retry-After": "120"}, b"<html>CONSTRUCTED 429</html>")
    H._default_acquire(world.writer, ws, world.tokens[ws], w1, **kw)                   # a hunt row
    assert len(sent) == 1 and _rows(world, w1)[0][1] == "api-error", (sent, _rows(world, w1))
    out = run.measure(world.writer, ws, world.tokens[ws], w2, **kw)                    # a measure row after it
    assert len(sent) == 1 and out["outcome"] == "measured", (sent, out)
    cd = _skip(world, w2)
    assert (cd["host"], cd["trigger_attempt_id"]) == ("archive.org", _rows(world, w1)[0][0]), cd
    monkeypatch.setattr(run, "PACING", {})                                             # a new process: cold
    never = C2C.constructed_never_archived()
    answer["now"] = lambda url: never.get(url)
    run.measure(world.writer, ws, world.tokens[ws], w3, **kw)
    assert len(sent) > 1 and _rows(world, w3)[0][1] == "blocked", (sent, _rows(world, w3))


# ── D44: a multi-host rung keeps asking its other hosts ─────────────────────────────────────

HOST_A, HOST_B = "hosta.constructed.invalid", "hostb.constructed.invalid"


def _landing_page(*pdf_urls):
    """CONSTRUCTED: a landing page with citation metadata, pointing at `pdf_urls` (a citation_pdf_url meta for the
    first, a PDF alternate link for each other)."""
    head = '<meta name="citation_title" content="A constructed paper">'
    head += f'<meta name="citation_pdf_url" content="{pdf_urls[0]}">'
    head += "".join(f'<link rel="alternate" type="application/pdf" href="{u}">' for u in pdf_urls[1:])
    return (f"<!DOCTYPE html><html><head><title>A constructed paper</title>{head}</head><body></body></html>").encode()


@pg_only
def test_a_multi_host_rung_skips_only_the_cooling_host_and_asks_the_others(world):
    """S4.5 decision D44 on the REAL ladder, route `landing` (Stage C). Work 1's DOI page points at host A, which
    answers 429 with Retry-After 120: host A cools (not the route). Work 2's DOI page points at host A AND host B: the
    DOI page is read (doi.org is not cooling), host A's candidate is NOT asked — recorded in `detail.landing.cooled`
    and in `detail.cooldown_skipped` naming host A and work 1's attempt — and host B's IS asked (it answers 404: the
    row is that refusal, `blocked/not_found` — marked `retriable`, S4.5 decision D45: a candidate was untried). Work 3's
    only candidate is on host A: nothing about the file could be asked, so the row is a retriable `api-error`, never a
    miss."""
    clock, pacing = Clock(), {}
    ws = world.ws("fix7-hosts")
    w1, w2, w3 = world.work(ws), world.work(ws), world.work(ws)
    a1, a2, a3 = (f"https://{HOST_A}/{uuid.uuid4().hex[:8]}.pdf" for _ in range(3))
    b2 = f"https://{HOST_B}/{uuid.uuid4().hex[:8]}.pdf"
    html = {"Content-Type": "text/html; charset=utf-8"}
    stub = C2C.StubClient({
        f"doi.org/{w1['doi']}": (200, html, _landing_page(a1)),
        f"doi.org/{w2['doi']}": (200, html, _landing_page(a2, b2)),
        f"doi.org/{w3['doi']}": (200, html, _landing_page(a3)),
        HOST_A: (429, {"Content-Type": "text/html", "Retry-After": "120"}, b"<html>CONSTRUCTED 429</html>"),
        HOST_B: (404, {"Content-Type": "text/html"}, b"")})
    _ladder(world, ws, w1, {"landing": stub}, clock, pacing, routes=("landing",))
    r1 = _one(world, w1, "landing")
    assert (r1[1], list(r1[3])[-1]) == ("api-error", 429) and any(HOST_A in u for u in stub.calls), (r1, stub.calls)

    hosts = _hosts(pacing)
    cool = hosts.cooling(HOST_A)
    assert cool is not None and cool["trigger_route"] == "landing" and hosts.cooling("doi.org") is None, cool
    before = len(stub.calls)
    _ladder(world, ws, w2, {"landing": stub}, clock, pacing, routes=("landing",))
    asked = stub.calls[before:]
    assert any(b2 in u for u in asked), ("host B was not asked while host A cooled", asked)
    assert not any(HOST_A in u for u in asked), ("the cooling host A was asked", asked)
    r2 = _one(world, w2, "landing")
    # D45: B's own answer is the row's status, but a candidate was untried — retriable, never a permanent miss
    assert (r2[1], r2[2], r2[4]) == ("blocked", "not_found", True), r2
    cooled = r2[6]["landing"].get("cooled") or []
    assert [c["host"] for c in cooled] == [HOST_A], r2[6]["landing"]
    skipped = r2[6].get("cooldown_skipped") or []
    assert [(s["host"], s["cooldown"]["trigger_attempt_id"], s["cooldown"]["status_code"]) for s in skipped] == \
        [(HOST_A, r1[0], 429)], skipped
    before = len(stub.calls)
    _ladder(world, ws, w3, {"landing": stub}, clock, pacing, routes=("landing",))
    assert not any(HOST_A in u for u in stub.calls[before:]), stub.calls[before:]
    r3 = _one(world, w3, "landing")
    assert (r3[1], r3[4]) == ("api-error", True) and r3[6]["cooldown_skipped"][0]["host"] == HOST_A, r3


def _gate(route, host, seconds=120.0):
    """CONSTRUCTED: a request gate whose route has `host` cooling for `seconds` on a controllable clock."""
    from litkb.acquire import backoff

    clock = Clock()
    hosts = backoff.HostCooldowns()
    hosts.cool(clock, seconds, {"trigger_route": route, "status_code": 429, "trigger_attempt_id": "constructed"}, host)
    return backoff.Gate(route, hosts, clock)


def _under(gate, fn):
    from litkb import netutil

    token = netutil.REQUEST_GATE.set(gate)
    try:
        return fn()
    finally:
        netutil.REQUEST_GATE.reset(token)


def test_a_stage_b_candidate_loop_skips_only_the_cooling_host():
    """Stage B's one candidate loop (`stage_b.fetch_candidates`, every Stage B rung's publisher URLs): under a gate
    with host A cooling, host A's candidate is not asked and host B's is; with host A's alone, nothing is asked and the
    answer is a retriable `api-error`, never `no-oa-copy` (a miss)."""
    from litkb.acquire import stage_b
    from litkb.netutil import Pacer

    a, b = f"https://{HOST_A}/x.pdf", f"https://{HOST_B}/x.pdf"
    stub = C2C.StubClient({HOST_B: (404, {}, b"")})
    ctx = types.SimpleNamespace(clients={"openalex": stub}, pacer=Pacer(interval=0, sleep=lambda s: None))
    gate = _gate("openalex", HOST_A)
    r = _under(gate, lambda: stage_b.fetch_candidates("openalex", [(a, {}), (b, {})], ctx, {}))
    assert stub.calls == [b] and r["http_codes"] == [404], (stub.calls, r)
    assert [x["host"] for x in gate.refused] == [HOST_A] and "cooling" in r["detail"], (gate.refused, r)
    stub2 = C2C.StubClient({})
    ctx2 = types.SimpleNamespace(clients={"openalex": stub2}, pacer=ctx.pacer)
    r2 = _under(_gate("openalex", HOST_A), lambda: stage_b.fetch_candidates("openalex", [(a, {})], ctx2, {}))
    assert stub2.calls == [] and (r2["status"], r2.get("retriable")) == ("api-error", True), r2


def test_open_access_skips_only_the_cooling_host_s_location():
    """Open access's locations (Unpaywall's list: many publisher hosts): under a gate with host A cooling, host A's
    location is not asked (`tried` says `=cooling`) and host B's is; with host A's alone, the answer is a retriable
    `api-error`, never a `bad-file` (nothing about the file was asked)."""
    from litkb.acquire import open_access
    from litkb.netutil import Pacer

    a, b = f"https://{HOST_A}/x.pdf", f"https://{HOST_B}/x.pdf"
    pacer = Pacer(interval=0, sleep=lambda s: None)
    stub = C2C.StubClient({HOST_B: (404, {"Content-Type": "text/html"}, b"<html>CONSTRUCTED 404</html>")})
    r = _under(_gate("open_access", HOST_A), lambda: open_access.fetch_open_access(
        "10.5555/fix7-oa", None, pacer, client=stub, locations=lambda d: ([a, b], "CONSTRUCTED lookup")))
    assert stub.calls == [b] and f"{HOST_A}=cooling" in r["tried"], (stub.calls, r["tried"])
    stub2 = C2C.StubClient({})
    r2 = _under(_gate("open_access", HOST_A), lambda: open_access.fetch_open_access(
        "10.5555/fix7-oa", None, pacer, client=stub2, locations=lambda d: ([a], "CONSTRUCTED lookup")))
    assert stub2.calls == [] and (r2["status"], r2.get("retriable")) == ("api-error", True), r2


# ── D45: one host table for the run — a host cooled by ONE route is cooled for EVERY route ────────

@pg_only
def test_a_host_cooled_by_one_route_is_cooled_for_every_route_and_another_host_is_not(world):
    """S4.5 decision D45, the run's concrete case: the Wayback availability API and the Internet Archive rung both ask
    archive.org. Work 1's Wayback meets a 429 (Retry-After 120) on archive.org. Work 2, same run, asks Stage C
    (`landing`, host doi.org) and Stage E3 (`ia`, host archive.org): landing IS asked (another host is not gated); ia
    is ONE `skipped/backoff_window` row whose `detail.cooldown` names the host archive.org AND the route whose answer
    cooled it (`wayback`) and work 1's attempt — and its FAILING client saw no request."""

    clock, pacing = Clock(), {}
    ws = world.ws("fix7-cross")
    w1, w2 = _works(world, ws, 2)
    _ladder(world, ws, w1, {"wayback": _answers(429, "120", b"CONSTRUCTED 429 Too Many Requests")}, clock, pacing)
    r1 = _one(world, w1)
    assert (r1[1], list(r1[3])) == ("api-error", [429]), r1
    cool = _hosts(pacing).cooling("archive.org")
    assert cool is not None and cool["trigger_route"] == "wayback", cool
    landing = C2C.StubClient({f"doi.org/{w2['doi']}": (200, {"Content-Type": "text/html; charset=utf-8"},
                                                        _landing_page(f"https://{HOST_B}/w2.pdf")),
                              HOST_B: (404, {"Content-Type": "text/html"}, b"")})
    ia = FailingClient()
    _ladder(world, ws, w2, {"landing": landing, "ia": ia}, clock, pacing, routes=("landing", "ia"))
    assert ia.calls == [], ("the IA rung asked archive.org while Wayback's 429 cooled it", ia.calls)
    assert any("doi.org" in u for u in landing.calls), ("another host was gated", landing.calls)
    assert _one(world, w2, "landing")[1] != "skipped"
    cd = _skip(world, w2, "ia")
    assert (cd["host"], cd["trigger_route"], cd["trigger_attempt_id"], cd["status_code"]) == \
        ("archive.org", "wayback", r1[0], 429), cd


# ── auditor-fix7 F1: a FOLLOWED redirect — the host that answered, and every hop gated (a LOOPBACK server) ────────

class _Redirector(http.server.BaseHTTPRequestHandler):
    """CONSTRUCTED loopback server (the independent auditor's redirect demo, auditor-fix7 F1): `/r` 302s to
    `http://localhost:<port>/pdf`, which answers 429 with Retry-After 120. Two host NAMES reach it — `127.0.0.1` and
    `localhost` — so the gate sees two hosts. Every request's Host header is logged in `SEEN`."""
    SEEN = []

    def do_GET(self):
        self.SEEN.append((self.headers.get("Host", "").split(":")[0], self.path))
        port = self.server.server_address[1]
        if self.path == "/r":
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{port}/pdf")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"<html>CONSTRUCTED 429</html>"
        self.send_response(429)
        self.send_header("Retry-After", "120")
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def redirector():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Redirector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Redirector.SEEN = []
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _ask_through(port, hosts, clock):
    """The REAL `netutil.Client.get` (follow=True, its default) under a REAL `backoff.Gate`, as `run._call_rung`
    sets it. -> (status, the gate's summary)."""
    from litkb import netutil
    from litkb.acquire import backoff

    gate = backoff.Gate("open_access", hosts, clock)
    token = netutil.REQUEST_GATE.set(gate)
    try:
        st, _hd, _body = netutil.Client(base="").get(f"http://127.0.0.1:{port}/r", timeout=10)
    finally:
        netutil.REQUEST_GATE.reset(token)
    return st, gate.summary()


def test_a_followed_redirect_credits_the_host_that_answered_not_the_redirector(redirector):
    """auditor-fix7 F1, case A. 127.0.0.1 302s to localhost, which answers 429 Retry-After 120: the gate credits the
    302 to 127.0.0.1 (a hop) and the 429 to LOCALHOST — the host `_cool_after` cools — never the redirector."""
    from litkb.acquire import backoff

    st, summ = _ask_through(redirector, backoff.HostCooldowns(), Clock())
    assert st == 429 and _Redirector.SEEN == [("127.0.0.1", "/r"), ("localhost", "/pdf")], (st, _Redirector.SEEN)
    got = [(o["host"], o["status"], bool(o.get("hop"))) for o in summ["observed"]]
    assert got == [("127.0.0.1", 302, True), ("localhost", 429, False)], got
    cools = [o["host"] for o in summ["observed"] if backoff.is_rate_limit(o["status"], o["challenge"])]
    assert cools == ["localhost"], ("the redirector was credited with the 429", cools)


def test_a_followed_redirect_into_a_cooling_host_is_never_followed(redirector):
    """auditor-fix7 F1, case B. With localhost cooling, the same request stops at the 302: the server sees NO request
    for localhost, the 302 is the answer, and the refusal is on the gate naming localhost."""
    from litkb.acquire import backoff

    clock = Clock()
    hosts = backoff.HostCooldowns()
    hosts.cool(clock, 120.0, {"trigger_route": "constructed", "status_code": 429}, "localhost")
    st, summ = _ask_through(redirector, hosts, clock)
    assert _Redirector.SEEN == [("127.0.0.1", "/r")], ("a request reached the cooling host", _Redirector.SEEN)
    assert st == 302 and [r["host"] for r in summ["refused"]] == ["localhost"], (st, summ["refused"])


# ── the independent auditor's checks (auditor-fix7), adopted: each turns red under its own mutation row ─────────

JSON_CT, HTML_CT = {"Content-Type": "application/json"}, {"Content-Type": "text/html"}


def _never_archived(url):
    """CONSTRUCTED: Wayback's availability API and CDX, and the IA search, all answer "nothing here"."""
    if "archive.org/wayback/available" in url:
        return 200, JSON_CT, json.dumps({"url": C2C.CONSTRUCTED_DEAD_URL, "archived_snapshots": {}}).encode()
    if "/cdx/search/cdx" in url:
        return 200, JSON_CT, b"[]"
    if "archive.org/advancedsearch" in url:
        return 200, JSON_CT, json.dumps({"response": {"numFound": 0, "docs": []}}).encode()
    return 404, {}, b""


class Spy:
    """The socket seam `netutil.Client._raw_get`, replaced (the auditor's spy): every request that REACHES it is
    recorded (host, url, clock) and answered by `self.answer(url)`; the Stage E rungs build the REAL client."""

    def __init__(self, clock):
        self.sent, self.clock, self.answer = [], clock, _never_archived

    def install(self, monkeypatch):
        from litkb import netutil
        from litkb.acquire import backoff, ia, wayback

        spy = self

        def raw_get(client, url, accept, timeout, follow, data=None, headers=None):
            spy.sent.append((backoff.host_of(url), url, spy.clock()))
            return spy.answer(url)

        monkeypatch.setattr(netutil.Client, "_raw_get", raw_get)
        monkeypatch.setattr(wayback, "_client", lambda: netutil.Client(base=""))
        monkeypatch.setattr(ia, "_client", lambda: netutil.Client(base=""))
        return self


def _dead(world, ws):
    return _works(world, ws, 1)[0]


@pg_only
@pytest.mark.parametrize("first,second", [("ia", "wayback"), ("wayback", "ia")])
def test_a_429_on_archive_org_by_either_route_gates_the_other_and_nothing_else(world, monkeypatch, first, second):
    """auditor-fix7's D45 check, both directions, through the REAL client: a 429 Retry-After 60 on archive.org by one
    route cools archive.org alone; the next work's BOTH routes are `skipped/backoff_window` naming archive.org, the
    first route and its attempt, and no request reaches archive.org; after 60 s the other route asks it again."""
    from litkb.acquire import backoff

    clock = Clock()
    spy = Spy(clock).install(monkeypatch)
    pacing = {}
    ws = world.ws(f"fix7-aud-d45-{first}")
    w1, w2, w3 = _dead(world, ws), _dead(world, ws), _dead(world, ws)
    spy.answer = lambda url: (429, {"Retry-After": "60", **HTML_CT}, b"<html>CONSTRUCTED 429</html>") \
        if backoff.host_of(url) == "archive.org" else _never_archived(url)
    _ladder(world, ws, w1, {}, clock, pacing, routes=(first,))
    r1 = _rows(world, w1, first)
    assert [(r[1], list(r[3])) for r in r1] == [("api-error", [429])], r1
    assert set(_hosts(pacing).hosts) == {"archive.org"}, _hosts(pacing).hosts          # nothing else cools
    n = len(spy.sent)
    spy.answer = _never_archived                                                        # would answer if asked
    _ladder(world, ws, w2, {}, clock, pacing, routes=(first, second))
    to_archive = [s for s in spy.sent[n:] if s[0] == "archive.org"]
    assert to_archive == [], ("a request reached the cooling host archive.org", to_archive)
    for route in (first, second):
        rows = _rows(world, w2, route)
        assert [(r[1], r[2]) for r in rows] == [("skipped", "backoff_window")], (route, rows)
        cd = rows[0][6]["cooldown"]
        assert (cd["host"], cd["trigger_route"], cd["trigger_attempt_id"], cd["status_code"]) == \
            ("archive.org", first, r1[0][0], 429), (route, cd)
    clock.t += 60.0
    n = len(spy.sent)
    _ladder(world, ws, w3, {}, clock, pacing, routes=(second,))
    assert any(s[0] == "archive.org" for s in spy.sent[n:]), spy.sent[n:]


_CHALLENGE = (b"<html><head><title>Just a moment...</title></head><body>CONSTRUCTED challenge "
              b"<div id='cf-challenge'></div></body></html>")


@pg_only
def test_a_bot_challenge_at_503_never_cools_its_host_by_the_long_wait_cause(world, monkeypatch):
    """auditor-fix7 F2 (its measurement, as a test). Wayback books ANY transient code `api-error` (it runs no
    challenge detector); the gate marks the body a challenge, so the rate-limit cause is off — and with the route's
    AIMD delay over the in-row threshold (CONSTRUCTED 16 s: after a 2-4-8-16 streak) the LONG-WAIT cause must not cool
    it either (it cooled archive.org 32 s before the fix)."""
    from litkb.acquire import backoff

    clock = Clock()
    spy = Spy(clock).install(monkeypatch)
    spy.answer = lambda url: (503, HTML_CT, _CHALLENGE) if "archive.org/wayback/available" in url \
        else _never_archived(url)
    pacing = {"wayback": backoff.Aimd(delay_s=16.0)}
    ws = world.ws("fix7-aud-chal-long")
    w1 = _dead(world, ws)
    _ladder(world, ws, w1, {}, clock, pacing, routes=("wayback",))
    rows = _rows(world, w1, "wayback")
    assert [(r[1], list(r[3])) for r in rows] == [("api-error", [503])], rows
    facts = _hosts(pacing).cooling("archive.org")
    assert facts is None, ("a bot challenge cooled its host", facts)


@pg_only
@pytest.mark.parametrize("retry_after", ["60", None])
def test_a_bot_challenge_at_429_never_cools_its_host(world, monkeypatch, retry_after):
    """auditor-fix7 F2 and its AM1: a challenge page served at 429 on the IA search — with Retry-After 60 (a long wait:
    it cooled archive.org on the FIRST answer before the fix) and without (the rate-limit cause alone: the gate must
    read a 429's body for a challenge) — never cools archive.org."""
    clock = Clock()
    spy = Spy(clock).install(monkeypatch)
    hd = {**HTML_CT, **({"Retry-After": retry_after} if retry_after else {})}
    spy.answer = lambda url: (429, hd, _CHALLENGE) if "advancedsearch" in url else _never_archived(url)
    pacing = {}
    ws = world.ws("fix7-aud-chal-429")
    w1 = _dead(world, ws)
    _ladder(world, ws, w1, {}, clock, pacing, routes=("ia",))
    assert list(_rows(world, w1, "ia")[0][3]) == [429]
    facts = _hosts(pacing).cooling("archive.org")
    assert facts is None, ("a challenge at 429 cooled its host", facts)


@pg_only
def test_open_access_through_the_ladder_records_the_cooled_location_and_is_retriable(world, monkeypatch):
    """auditor-fix7's check (2): open access's locations, with host A cooling (CONSTRUCTED, cooled by `landing`): A is
    not asked, B is; the one row is retriable and names A — and the route that cooled it — in `cooldown_skipped`."""
    from litkb.acquire import backoff, open_access

    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "fix7-aud@example.invalid")
    a, b = f"https://{HOST_A}/a.pdf", f"https://{HOST_B}/b.pdf"
    up = json.dumps({"is_oa": True, "oa_status": "bronze", "best_oa_location": {"url": a, "host_type": "publisher"},
                     "oa_locations": [{"url": a, "host_type": "publisher"}, {"url": b, "host_type": "publisher"}]})
    stub = C2C.StubClient({"api.unpaywall.org": (200, JSON_CT, up.encode()),
                           HOST_B: (404, HTML_CT, b"<html>CONSTRUCTED 404</html>")})
    clock = Clock()
    hosts = backoff.HostCooldowns()
    hosts.cool(clock, 120.0, {"trigger_route": "landing", "status_code": 429, "trigger_attempt_id": "CONSTRUCTED"},
               HOST_A)
    pacing = {backoff.HOSTS_KEY: hosts}
    ws = world.ws("fix7-aud-oa")
    w1 = world.work(ws)
    _ladder(world, ws, w1, {"open_access": stub}, clock, pacing, routes=("open_access",))
    assert not any(HOST_A in u for u in stub.calls) and any(HOST_B in u for u in stub.calls), stub.calls
    row = _one(world, w1, "open_access")
    skipped = row[6].get("cooldown_skipped") or []
    assert row[4] is True and [s["host"] for s in skipped] == [HOST_A], row
    assert skipped[0]["cooldown"]["trigger_route"] == "landing", skipped


def test_a_longer_running_cool_down_is_kept_when_a_shorter_one_starts():
    """auditor-fix7 AM2: a host that said Retry-After 120 is not asked after 2 s because another answer cooled it 2 s."""
    from litkb.acquire import backoff

    clock = Clock()
    hosts = backoff.HostCooldowns()
    hosts.cool(clock, 120.0, {"trigger_route": "ia", "status_code": 429}, "h.constructed.invalid")
    hosts.cool(clock, 2.0, {"trigger_route": "wayback", "status_code": 429}, "h.constructed.invalid")
    clock.t += 3.0
    facts = hosts.cooling("h.constructed.invalid")
    assert facts is not None and facts["trigger_route"] == "ia", ("the 120 s cool-down was cut to 2 s", facts)


def test_a_429_without_retry_after_in_a_row_that_moved_no_delay_still_cools_2_s():
    """auditor-fix7 AM4: the no-Retry-After cool-down is floored at the AIMD's first step (2 s), never 0 s."""
    from litkb.acquire import backoff

    assert backoff.cooldown_seconds(None, 0.0) == (2.0, "aimd"), backoff.cooldown_seconds(None, 0.0)


@pg_only
def test_a_landing_hop_to_a_cooling_host_keeps_the_answer_already_received(world):
    """auditor-fix7 AM3: landing's DOI page 302s to host A, which is cooling: the walk is stopped before host A, and
    the row keeps the 302 it received (`api-error`, retriable, `detail.cooldown` naming host A) — never a non-spend
    skip that drops an answer."""
    from litkb.acquire import backoff

    clock = Clock()
    hosts = backoff.HostCooldowns()
    hosts.cool(clock, 120.0, {"trigger_route": "open_access", "status_code": 429, "trigger_attempt_id": "CONSTRUCTED"},
               HOST_A)
    pacing = {backoff.HOSTS_KEY: hosts}
    ws = world.ws("fix7-aud-hop")
    w1 = world.work(ws)
    stub = C2C.StubClient({f"doi.org/{w1['doi']}": (302, {"Location": f"https://{HOST_A}/landing"}, b"")})
    _ladder(world, ws, w1, {"landing": stub}, clock, pacing, routes=("landing",))
    assert not any(HOST_A in u for u in stub.calls), stub.calls
    row = _one(world, w1, "landing")
    assert (row[1], list(row[3] or []), row[4]) == ("api-error", [302], True), row
    assert row[6]["cooldown"]["host"] == HOST_A, row[6]


@pg_only
def test_a_retry_after_of_exactly_the_in_row_threshold_is_retried(world, monkeypatch):
    """auditor-fix7 AM5: a 502 with Retry-After 10 (= `IN_ROW_WAIT_MAX_S`) is sat out and retried — the boundary is
    inclusive. (A 502, not a 503: a 429 / 503 cools by the rate-limit cause whatever the wait.)"""
    clock = Clock()
    spy = Spy(clock).install(monkeypatch)
    state = {"n": 0}

    def answer(url):
        if "archive.org/wayback/available" in url and state["n"] == 0:
            state["n"] += 1
            return 502, {"Retry-After": "10", **HTML_CT}, b"<html>CONSTRUCTED 502</html>"
        return _never_archived(url)

    spy.answer = answer
    pacing = {}
    ws = world.ws("fix7-aud-ra10")
    w1 = _dead(world, ws)
    _ladder(world, ws, w1, {}, clock, pacing, routes=("wayback",))
    rows = _rows(world, w1, "wayback")
    assert len(rows) == 2 and rows[1][5] == rows[0][0] and clock.slept == [10.0], \
        ("a Retry-After of 10 s was not sat out and retried", [(r[1], r[5]) for r in rows], clock.slept)


@pg_only
def test_the_long_wait_cause_cools_the_host_that_answered_not_the_doi_resolver(world):
    """auditor-fix7 AM6/AM8: landing reads the DOI page (doi.org, 200), then its candidate on host X answers 502 with
    the route's AIMD at 16 s (CONSTRUCTED): the long-wait cause cools X — the host that gave the transient answer —
    and never doi.org, the first host the call asked."""
    from litkb.acquire import backoff

    clock = Clock()
    ws = world.ws("fix7-aud-lw")
    w1 = world.work(ws)
    x = f"https://{HOST_B}/x.pdf"
    stub = C2C.StubClient({f"doi.org/{w1['doi']}": (200, {"Content-Type": "text/html; charset=utf-8"},
                                                     _landing_page(x)),
                           HOST_B: (502, HTML_CT, b"<html>CONSTRUCTED 502</html>")})
    pacing = {"landing": backoff.Aimd(delay_s=16.0)}
    _ladder(world, ws, w1, {"landing": stub}, clock, pacing, routes=("landing",))
    hosts = _hosts(pacing)
    assert hosts.cooling("doi.org") is None, ("the DOI resolver cooled", hosts.hosts)
    cool = hosts.cooling(HOST_B)
    assert cool is not None and cool["cause"] == "long-wait", hosts.hosts

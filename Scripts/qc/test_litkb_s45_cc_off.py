"""litkb S4.5 decision D39 (builder-fix6): Stage E5's two Common Crawl hosts are switched OFF through the pre-fetch
policy — `litkb.acquire.policy.PolicyLine.off_why`, guard 21's "a tier is an auditable switch" for one line — with the
orchestrator's measured reason (`policy.COMMONCRAWL_OFF_WHY`) carried into every recorded skip: never silence, never a
deleted line. Measured by the orchestrator in the live run hardening-1 (2026-09-24): the index answered 502/504 on every
request, each only after ~270 s, and closed a direct probe's connection in 0.3 s.

S4.5 decision D53 (2026-09-24 ~14:40; integrator-w4): the index was measured serving again and E5 is back ON for
hardening-2 — the module table's two lines carry no `off_why` now. The SWITCH stays (it is how the orchestrator turns
E5 off again if the index fails again), so every test below of the switch itself runs against hardening-1's table,
installed for its block only by `litkb_hardening_c2c.route_switched_off("commoncrawl", policy.COMMONCRAWL_OFF_WHY)`
(the module table is never edited); the first test holds D53 itself — both lines ON in the module table.

What these tests hold:
  * D53: the module table's two E5 lines are ON (no `off_why`), `decide` allows both hosts and the ladder's host-less
    pre-check; no line of the table is switched off; the hardening-1 reason is kept as history;
  * under hardening-1's table: the two lines stay IN the table, switched off, and `decide` refuses each with the
    reason; every line WITHOUT
    `off_why` is decided exactly as before (Wayback, IA and every legitimate line still allowed);
  * the off switch is read BEFORE the shadow checks, whatever the line's tier (CONSTRUCTED line);
  * the rung itself asks nothing and carries the reason when handed the real policy;
  * on the REAL ladder (a worker database), in MEASURE mode and through the hunt's own acquirer (acquire mode), E5 is
    recorded `skipped/policy_refused` with the reason and NO request reaches a client that FAILS on any request — and,
    under the test's explicit override (`litkb_hardening_c2c.route_switched_on`), the same setup DOES reach that client,
    so the no-request assertion is not vacuous.

Every input here is CONSTRUCTED (a salted admission, a never-archived URL, stub clients). No test touches the network.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_cc_off.py -q
"""
import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
INSTR = SCRIPTS / "qc" / "instruments"
pg_only = pytest.mark.requires_litkb_pg
CC_HOSTS = ("index.commoncrawl.org", "data.commoncrawl.org")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C2C = _load("_litkb_hardening_c2c_for_cc_off", INSTR / "litkb_hardening_c2c.py")


class FailingClient:
    """CONSTRUCTED: a client that FAILS the test on any request — a switched-off host must never be asked. The call
    is recorded BEFORE it raises, so a request the ladder's route boundary swallowed (`run._call_rung` books a rung
    that raised as an api-error attempt) is still seen by the assertion on `calls`."""
    base = ""

    def __init__(self):
        self.calls = []

    def get(self, url, *a, **k):
        self.calls.append(url)
        raise AssertionError(f"a request reached a switched-off host: {url}")


def _policy():
    from litkb.acquire import policy as P
    from litkb.acquire import run  # noqa: F401 — the registry's rungs add their own lines to POLICY at import

    return P


def _hardening_1_table():
    """hardening-1's table after D39 (E5's two lines off with the measured reason), for the with-block only."""
    P = _policy()
    return C2C.route_switched_off("commoncrawl", P.COMMONCRAWL_OFF_WHY)


def test_d53_the_commoncrawl_lines_are_on_again_and_no_line_is_switched_off():
    """S4.5 decision D53: E5's two lines are in the module table, ON — `decide` allows each host and the ladder's
    host-less pre-check — and no line of the table carries an `off_why`. D39's measured reason stays as history (the
    text the switch would carry again)."""
    P = _policy()
    lines = [(i, p) for i, p in enumerate(P.POLICY) if p.route == "commoncrawl"]
    assert [p.host for _i, p in lines] == list(CC_HOSTS), lines
    for i, p in lines:
        assert (p.off_why, p.tier) == ("", P.LEGITIMATE), p
        d = P.decide("commoncrawl", p.host)
        assert (d.allowed, d.line, d.tier) == (True, i, P.LEGITIMATE), d
    assert P.decide("commoncrawl").allowed        # the ladder's own pre-check (`run._skip_reason`) names no host
    assert [p for p in P.POLICY if p.off_why] == [], "D53: no line of the table is switched off"
    assert "2026-09-24" in P.COMMONCRAWL_OFF_WHY and "D39" in P.COMMONCRAWL_OFF_WHY


# ── the table and decide ────────────────────────────────────────────────────────────────────

def test_the_commoncrawl_lines_stay_in_the_table_switched_off_with_the_measured_reason():
    """Under hardening-1's table (D39's switch; D53 put the module table back ON)."""
    P = _policy()
    with _hardening_1_table():
        lines = [(i, p) for i, p in enumerate(P.POLICY) if p.route == "commoncrawl"]
        assert [p.host for _i, p in lines] == list(CC_HOSTS), lines
        for i, p in lines:
            assert (p.off_why, p.tier) == (P.COMMONCRAWL_OFF_WHY, P.LEGITIMATE), p
            d = P.decide("commoncrawl", p.host)
            assert (d.allowed, d.reason, d.line, d.tier) == (False, P.COMMONCRAWL_OFF_WHY, i, P.LEGITIMATE), d
            assert P.measure_decision(d) == d, "MEASURE mode keeps the refusal and its reason"
        d = P.decide("commoncrawl")                    # the ladder's own pre-check (`run._skip_reason`) names no host
        assert (d.allowed, d.reason) == (False, P.COMMONCRAWL_OFF_WHY), d
        assert {(p.route, p.host) for p in P.POLICY if p.off_why} == {("commoncrawl", h) for h in CC_HOSTS}, \
            "D39 switches off E5's two hosts and nothing else"


def test_a_line_without_off_why_is_decided_as_before():
    P = _policy()
    assert P.decide("wayback", "archive.org").allowed and P.decide("wayback", "web.archive.org").allowed
    assert P.decide("ia", "archive.org").allowed
    checked = 0
    for p in P.POLICY:
        if p.off_why:
            continue
        d = P.decide(p.route, p.host, shadow_enabled=True)
        hit = P.POLICY[d.line]
        assert d.allowed and d.tier == p.tier and (hit.route, hit.host, hit.off_why) == (p.route, p.host, ""), (p, d)
        checked += 1
    assert checked == len(P.POLICY)           # S4.5 decision D53: no line of the module table is switched off


def test_the_off_switch_is_read_before_the_shadow_checks_whatever_the_tier():
    """CONSTRUCTED lines (passed as `policy=`, never the module table): a switched-off SHADOW line is refused with its
    own reason whether the shadow switch is on or off and whether a legitimate rung hit; the same line switched on is
    allowed again."""
    P = _policy()
    off = P.PolicyLine("scihub", "constructed.invalid", P.SHADOW, "CONSTRUCTED shadow line",
                       P.SHADOW_CORPUS_FROZEN_AT, off_why="CONSTRUCTED: switched off")
    for enabled in (True, False):
        for hit in (True, False):
            d = P.decide("scihub", "constructed.invalid", shadow_enabled=enabled, legit_hit=hit, policy=(off,))
            assert (d.allowed, d.reason, d.tier) == (False, "CONSTRUCTED: switched off", P.SHADOW), d
    on = dataclasses.replace(off, off_why="")
    assert P.decide("scihub", "constructed.invalid", shadow_enabled=True, policy=(on,)).allowed


# ── the rung ────────────────────────────────────────────────────────────────────────────────

def _cc_answers():
    """CONSTRUCTED: a crawl list naming one crawl, whose index has no capture (404)."""
    return C2C.StubClient({
        "collinfo.json": (200, {"Content-Type": "application/json"}, json.dumps(
            [{"id": "CC-CONSTRUCTED", "cdx-api": "https://index.commoncrawl.org/CC-CONSTRUCTED-index"}]).encode()),
        "index.commoncrawl.org/CC-CONSTRUCTED-index": (404, {}, b"")})


def test_the_rung_asks_nothing_and_carries_the_reason_when_its_hosts_are_off():
    from litkb.acquire import commoncrawl

    P = _policy()
    stub = FailingClient()
    with _hardening_1_table():
        r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], stub, decide=lambda h: P.decide("commoncrawl", h))
    assert stub.calls == [] and (r["status"], r.get("sub_status")) == ("skipped", "policy_refused"), r
    assert [x["reason"] for x in r["policy"]] == [P.COMMONCRAWL_OFF_WHY] and r["tried"] == ["collinfo=policy-refused"]
    # the test's explicit override (CONSTRUCTED answers): the rung asks again, so the refusal above is the switch
    live = _cc_answers()
    with _hardening_1_table(), C2C.route_switched_on("commoncrawl"):
        r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], live, decide=lambda h: P.decide("commoncrawl", h),
                                          indexes_asked=1)
    assert len(live.calls) == 2 and (r["status"], r.get("sub_status")) == ("not-in-archive", "not_in_corpus"), r


def test_the_override_is_the_test_s_alone_and_lifts_after_its_block():
    P = _policy()
    table = P.POLICY
    with _hardening_1_table():
        before = P.POLICY
        with C2C.route_switched_on("commoncrawl"):
            assert P.decide("commoncrawl", CC_HOSTS[0]).allowed and P.decide("commoncrawl", CC_HOSTS[1]).allowed
            assert len(P.POLICY) == len(before)
        assert P.POLICY is before and not P.decide("commoncrawl", CC_HOSTS[0]).allowed
    assert P.POLICY is table and P.decide("commoncrawl", CC_HOSTS[0]).allowed   # the D53 table again
    for py in (SCRIPTS / "pipeline" / "litkb").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "route_switched_on" not in text and "policy_with_route_on" not in text, py
        assert "route_switched_off" not in text and "policy_with_route_off" not in text, py


# ── the real ladder on a worker database ────────────────────────────────────────────────────

@pytest.fixture
def world(litkb_pg_base, tmp_path):
    _psycopg, conn, _ran = litkb_pg_base
    w = C2C.World(conn, tmp_path)
    yield w
    w.close()


def _cc_rows(world, work):
    return C2C._rows(world.owner, work["work_id"], "commoncrawl")


@pg_only
def test_measure_mode_records_the_skip_with_the_reason_and_asks_nothing(world):
    """MEASURE mode (the run driver's hook for a work that holds a file, S4.5 decision D9): a work with a dead URL, so
    Stage E is asked. E1 (no `off_why`) is asked; E5 is one `skipped/policy_refused` row carrying the reason, and its
    FAILING client saw no request. The control, under the test's override on a second work: the same ladder reaches
    that client."""
    P = _policy()
    ws = world.ws("cc-off-measure")
    work = world.work(ws)
    world.dead_link(ws, work, C2C.CONSTRUCTED_DEAD_URL)
    cc, wb = FailingClient(), C2C.constructed_never_archived()
    with _hardening_1_table():
        out = world.ladder(ws, work, {"wayback": wb, "commoncrawl": cc}, routes=("wayback", "commoncrawl"))
    rows = _cc_rows(world, work)
    assert out["outcome"] == "measured" and [(s, sub) for s, sub, _d in rows] == [("skipped", "policy_refused")], rows
    policy = rows[0][2]["policy"]
    assert (policy["allowed"], policy["reason"], policy["tier"]) == (False, P.COMMONCRAWL_OFF_WHY, P.LEGITIMATE), policy
    assert cc.calls == []
    (s, sub, _d), = C2C._rows(world.owner, work["work_id"], "wayback")
    assert wb.calls and (s, sub) == ("blocked", "not_found"), (s, sub)
    # control: the rung ACTIVE under the explicit override -> the failing client IS reached
    work2 = world.work(ws)
    world.dead_link(ws, work2, C2C.CONSTRUCTED_DEAD_URL)
    cc2 = FailingClient()
    with _hardening_1_table(), C2C.route_switched_on("commoncrawl"):
        world.ladder(ws, work2, {"commoncrawl": cc2}, routes=("commoncrawl",))
    assert cc2.calls and all(s != "skipped" for s, _sub, _d in _cc_rows(world, work2)), cc2.calls


@pg_only
def test_the_hunt_s_acquirer_records_the_skip_with_the_reason_and_asks_nothing(world, monkeypatch):
    """Acquire mode through the hunt's OWN acquirer (`hunt._default_acquire`, what a hunt spends through: the whole
    ladder, `run.ladder_routes`). This test narrows the ladder to E5 (no socket: every other rung would build a real
    client) and hands the rung, when it builds its client, one that FAILS on any request. E5 is one
    `skipped/policy_refused` row carrying the reason; nothing was requested. The control under the override: reached."""
    from litkb import hunt as H
    from litkb.acquire import commoncrawl, run
    from litkb.netutil import Pacer

    P = _policy()
    cc = FailingClient()
    monkeypatch.setattr(commoncrawl, "_client", lambda: cc)
    monkeypatch.setattr(run, "ladder_routes", lambda rungs=None: ("commoncrawl",))
    # the hunt's acquirer passes no pacer and no pacing: a pacer that never sleeps, and a fresh in-run AIMD state so
    # the control arm's answer never paces a later test in this process (`run.PACING` is process-wide)
    monkeypatch.setattr(run, "Pacer", lambda *a, **k: Pacer(interval=0, sleep=lambda s: None))
    monkeypatch.setattr(run, "PACING", {})
    ws = world.ws("cc-off-hunt")
    work = world.work(ws)
    world.dead_link(ws, work, C2C.CONSTRUCTED_DEAD_URL)
    with _hardening_1_table():
        out = H._default_acquire(world.writer, ws, world.tokens[ws], work, store=world.store, agent="cc-off",
                                 session="cc-off-1")
    rows = _cc_rows(world, work)
    assert [(s, sub) for s, sub, _d in rows] == [("skipped", "policy_refused")], rows
    assert rows[0][2]["policy"]["reason"] == P.COMMONCRAWL_OFF_WHY
    assert cc.calls == [] and out["outcome"] == "not-acquired" and ("commoncrawl", "skipped") in out["attempts"], out
    # control: the rung ACTIVE under the explicit override -> the failing client IS reached
    work2 = world.work(ws)
    world.dead_link(ws, work2, C2C.CONSTRUCTED_DEAD_URL)
    with _hardening_1_table(), C2C.route_switched_on("commoncrawl"):
        H._default_acquire(world.writer, ws, world.tokens[ws], work2, store=world.store, agent="cc-off",
                           session="cc-off-1")
    assert cc.calls and all(s != "skipped" for s, _sub, _d in _cc_rows(world, work2)), cc.calls

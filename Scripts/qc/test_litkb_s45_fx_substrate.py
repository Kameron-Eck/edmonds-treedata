"""litkb S4.5 fix wave, builder FX-S — the substrate (S4.5 decision D51; referee-substrate notes N1, N2, N3).

  the backfill   `litkb.acquire.backoff.backfill_plan` / `backfill` + migration 0036's `litkb.backfill_route_backoff`:
                 the persisted refusal ladder (`route_backoff`, what `run._skip_reason` reads) is seeded from the
                 ledger's history so it equals the REFERENCE replay the gated counter `rehunt_route_spends` runs. The
                 REAL rows: the 31 live pairs that disagreed on 2026-09-24 (qc/fixtures/litkb_fxs_backoff_real_pairs.json,
                 read from live as litkb_reader — every attempt's recorded status, http codes and `at`), rebuilt on the
                 worker database with the run's own enforcement (`run._move_backoff`) producing the stored rows, then
                 planned, reviewed and applied; and one of them (open_access, the work live holds as 01a0c716…) shifted
                 in time so its run refusal was an hour ago: a re-hunt now is ALLOWED by the enforcement and COUNTED by
                 the gate (the referee's N1, reproduced), and after the backfill it is skipped and counted by nobody.
                 CONSTRUCTED rows (named so): an unexplained stored state, a plan the ledger has moved past, an edited
                 CSV row, a non-latest attempt and two bad states — each refused, never written.
  the pacer      ONE arXiv pacer per process (`resolver.process_arxiv_pacer`): three real admissions (rows L010-L012,
                 each building its own registry pacer, as `hunt` does) meet one 3 s gate on the real clock; a pacer on
                 an injected clock keeps its own.
  the booking    export.arxiv.org's REAL recorded 406s for L010-L017 (qc/fixtures/litkb_cassettes/fxs_arxiv_406/, the
                 ladder-1 cassette's own lines, byte for byte): `api-error/registry-transient` (the closed pair: not a
                 verdict on the record, nothing written) booked `retryable` False with the evidence — one request
                 each, no in-call retry — at the admission and at the hunt; a transient answer stays retriable.

Each guard has a mutation row in qc/instruments/litkb_p2_mutations.py (FXS1-FXS9) that turns this file red by a WORSE
ANSWER. No test touches the network.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_fx_substrate.py -q
"""
import base64
import csv
import datetime
import hashlib
import importlib.util
import json
import time
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
FIX = SCRIPTS / "qc" / "fixtures"
PAIRS = FIX / "litkb_fxs_backoff_real_pairs.json"
CASSETTE = FIX / "litkb_cassettes" / "fxs_arxiv_406"
E13_PAGE = FIX / "litkb_e13_challenge_b65a33b17354.html"
pg_only = pytest.mark.requires_litkb_pg
#: the real open_access pair the ladder-level tests re-hunt (live work id; its two recorded refusals, 2026-09-21
#: 20:09 PDT in workstream ruled-hunts-1 and 2026-09-24 10:01 PDT in ladder-1)
REHUNT_PAIR = ("open_access", "01a0c716-f0db-78b6-9d71-3c1674d7ba3e")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2M = _load("_litkb_p2_for_fxs", SCRIPTS / "qc" / "test_litkb_p2.py")
C1A = _load("_litkb_hardening_c1a_for_fxs", SCRIPTS / "qc" / "instruments" / "litkb_hardening_c1a.py")


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
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "fxs-test@example.invalid")


def _inst(v):
    """An instant from an ISO string (any offset) or a datetime; '' and None are None."""
    if isinstance(v, datetime.datetime):
        return v
    return datetime.datetime.fromisoformat(v) if v else None


def _key(state):
    """A ladder state as the enforcement reads it: (refusals, window start, next allowed)."""
    s = state or {}
    k = int(s.get("refusals") or 0)
    return (k, _inst(s.get("window_started_at")) if k else None, _inst(s.get("next_allowed_at")) if k else None)


def _pairs():
    return json.loads(PAIRS.read_text(encoding="utf-8"))["pairs"]


def _insert(pg, work_id, route, a, ws, at=None):
    """One recorded attempt, as the ledger recorded it (status, sub-status, http codes, `at`, retriable), written by
    the owner into a worker workstream standing in for the recorded one. -> its new id."""
    return pg.one(
        "INSERT INTO litkb.acquisition_attempts (work_id, route, status, sub_status, sub_status_basis, http_codes, at, "
        "retriable, workstream_id) VALUES (%s, %s, %s, %s, %s, %s::integer[], %s::timestamptz, %s, %s) "
        "RETURNING id::text",
        (work_id, route, a["status"], a["sub_status"], a["sub_status_basis"], list(a["http_codes"] or []),
         at if at is not None else a["at"], a["retriable"], ws))[0]


def _rebuild(pg, p, wss, shift=None):
    """Rebuild ONE recorded pair on the worker database: a synthetic admitted work, every recorded attempt (moved by
    `shift` when given, the gaps as recorded), and — where live holds a row — the stored state produced the way the
    run produced it: the ladder's own writer (`run._move_backoff`) moved by the run's attempt, the table holding no
    earlier row (the earlier refusals predate 0033). -> (work, {live attempt id: new id})."""
    from litkb.acquire import backoff as B
    from litkb.acquire import run

    def ws_for(slug):
        if slug not in wss:
            wss[slug] = pg.ws()
        return wss[slug]

    w = pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws_for("*admit*"))
    ids = {}
    for a in p["attempts"]:
        ws = ws_for(a["workstream"])
        at = (_inst(a["at"]) + shift) if shift is not None else None
        ids[a["id"]] = _insert(pg, work["work_id"], p["route"], a, ws, at)
    if p["stored"]:
        live = next(a for a in p["attempts"] if a["id"] == p["stored"]["last_attempt_id"])
        ws = wss[live["workstream"]]
        run._move_backoff(w, ws, pg.tokens[ws], work, p["route"],
                          {"id": ids[live["id"]], "status": live["status"], "codes": list(live["http_codes"])},
                          B.BackoffPolicy())
    return work, ids


def _gate_state(pg, route, work_id):
    """The state the GATE replays for a pair: `rehunt_route_spends`'s own query and the reference policy."""
    from litkb.acquire import backoff as B
    prior = pg.conn.execute(
        "SELECT id, status, coalesce(http_codes, '{}'), at, retry_of FROM litkb.acquisition_attempts "
        " WHERE route = %s AND work_id = %s ORDER BY at, id", (route, work_id)).fetchall()
    return B.BackoffPolicy().replay(prior)


def _apply(pg, work_ids, tmp_path, *, edit=None, before_apply=None, apply=True, recorder=None):
    """The reviewed op on the worker database: plan (limited to `work_ids`) -> the plan CSV -> [edit it] ->
    [`before_apply`] -> `backoff.backfill` with the CSV (the ingest login applies). -> (plan, result)."""
    from litkb.acquire import backoff as B
    from litkb.quarantine import ingest_connect

    plan = B.backfill_plan(pg.conn, work_ids=work_ids)
    path = tmp_path / f"plan-{uuid.uuid4().hex[:8]}.csv"
    B.write_plan_csv(plan["rows"], path)
    if edit:
        rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
        rows = [edit(r) for r in rows]
        with path.open("w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(B.BACKFILL_COLUMNS))
            wr.writeheader()
            wr.writerows(rows)
    if before_apply:
        before_apply()
    rec = recorder or (ingest_connect(pg.conn.info.dbname) if apply else None)
    try:
        return plan, B.backfill(pg.conn, session="fxs-test", csv_path=str(path), apply=apply, recorder=rec)
    finally:
        if rec is not None and recorder is None:
            rec.close()


# ── the backfill on the 31 real pairs ─────────────────────────────────────────────────────────────────────────
@pg_only
def test_the_31_real_pairs_are_planned_as_measured_and_seeded_to_the_gate_s_replay(pg, tmp_path):
    """REAL rows. Rebuilt with their recorded facts, the 10 open_access pairs' stored rows come out exactly as live
    holds them (1 refusal / 15 min: the enforcement never saw the pre-0033 refusal) and the 21 scihub pairs have none;
    the plan offers all 31 with the cause that explains each and the reference replay's state; applied, every pair's
    stored state IS the gate's replay, and a second plan offers nothing."""
    from litkb.acquire import backoff as B

    wss, built = {}, []
    for p in _pairs():
        work, ids = _rebuild(pg, p, wss)
        built.append((p, work, ids))
    for p, work, _ids in built:            # the reproduction: the run's writer computes live's stored row
        assert _key(B.load(pg.conn, p["route"], work["work_id"])) == _key(p["stored"]), (p["work_id"], p["stored"])
    mine = [str(w["work_id"]) for _p, w, _i in built]
    plan = B.backfill_plan(pg.conn, work_ids=mine)
    assert plan["unexplained"] == [], plan["unexplained"]
    by = {(r["route"], r["work_id"]): r for r in plan["rows"]}
    assert len(by) == 31 == len(built), sorted(by)
    for p, work, ids in built:
        r = by[(p["route"], str(work["work_id"]))]
        assert r["cause"] == (B.CAUSE_BLIND if p["stored"] else B.CAUSE_NO_ROW), (p["work_id"], r)
        if p["stored"]:
            assert r["unseen_attempts"] == 1, (p["work_id"], r)       # one pre-0033 refusal each
        assert r["attempt_id"] == ids[p["attempts"][-1]["id"]], (p["work_id"], r)
        assert _key(r) == _key(p["reference"]), (p["work_id"], r, p["reference"])
    _plan, res = _apply(pg, mine, tmp_path)
    assert res["would_apply"] == 31 and res["refused"] == [], res
    assert res["applied"]["applied"] == 31 and res["applied"]["offered"] == 31, res
    assert {k: res["applied"][k] for k in ("missing", "not_latest", "bad_state", "newer_row")} == \
        {"missing": 0, "not_latest": 0, "bad_state": 0, "newer_row": 0}, res
    for p, work, _ids in built:
        stored = B.load(pg.conn, p["route"], work["work_id"])
        gate = _gate_state(pg, p["route"], work["work_id"])
        assert _key(stored) == _key(gate) == _key(p["reference"]), (p["work_id"], stored, gate)
        nxt = _key(gate)[2]
        for probe in (nxt - datetime.timedelta(seconds=1), nxt + datetime.timedelta(seconds=1)):
            # the in-run skip rule and the gate's criterion (`at < next_allowed_at`) at the same instant
            assert (B.in_window(stored, probe) is not None) == (probe < gate["next_allowed_at"]), (p["work_id"], probe)
    assert B.backfill_plan(pg.conn, work_ids=mine)["rows"] == []
    log = pg.one("SELECT op, offered, applied, source FROM litkb.acquisition_backfills WHERE id = %s",
                 (res["applied"]["backfill_id"],))
    assert log[:3] == ("route_backoff", 31, 31) and "sha256=" in log[3], log
    # S4.5 decision D56 (integrator-w4; auditor-FX-S F2): every row's `last_*` is the attempt that last MOVED it — the
    # ORACLE here is the recorded history read directly: the last attempt that is neither a skip nor an original its
    # retry superseded — never the pair's latest attempt when that is a skip (13 of the 21 no_row pairs on live)
    skips = {"skipped", "budget-stop", "manual-step", "quota-stop"}
    latest_is_skip = 0
    for p, work, ids in built:
        retried = {a.get("retry_of") for a in p["attempts"] if a.get("retry_of")}
        movers = [a for a in p["attempts"] if a["status"] not in skips and a["id"] not in retried]
        last = pg.one("SELECT last_attempt_id::text, last_status, last_at FROM litkb.route_backoff WHERE route = %s "
                      "AND work_id = %s", (p["route"], work["work_id"]))
        assert last[0] == ids[movers[-1]["id"]] and last[1] == movers[-1]["status"], (p["work_id"], last)
        assert last[1] not in skips, (p["work_id"], last)
        latest_is_skip += p["attempts"][-1]["status"] in skips
    assert latest_is_skip == 13, latest_is_skip


def _shifted_rehunt_world(pg):
    """The REAL open_access pair REHUNT_PAIR, its recorded gap kept, moved so its run refusal was ONE HOUR ago: the
    stored window (15 min) has lapsed, the replayed one (6 h) has five hours to run."""
    p = next(x for x in _pairs() if (x["route"], x["work_id"]) == REHUNT_PAIR)
    now = pg.one("SELECT clock_timestamp()")[0]
    shift = (now - datetime.timedelta(hours=1)) - _inst(p["attempts"][-1]["at"])
    work, _ids = _rebuild(pg, p, {}, shift=shift)
    return p, work


def _rehunt(pg, work, tmp_path):
    """A second hunt of the work in a NEW workstream (the ladder's open access rung). Its answers are CONSTRUCTED
    (auditor-FX-S F5, S4.5 decision D58): the Unpaywall answer (`is_oa`, one doi.org location) is written here, and the
    doi.org answer is a 403 carrying E13's REAL recorded Cloudflare page — served for THIS pair's work, which is not
    E13's. The pair's attempt history is real; only these two answers are not.
    -> (rehunt_route_spends for it, its open_access rows, the stub)."""
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    frozen = pg.one("SELECT clock_timestamp()")[0]
    page = E13_PAGE.read_bytes()
    assert hashlib.sha256(page).hexdigest() == C1A.E13_SHA256
    stub = P2M.RouteStub({"api.unpaywall.org": (200, {}, json.dumps({
        "is_oa": True, "oa_status": "bronze",
        "oa_locations": [{"url": f"https://doi.org/{work['doi']}", "host_type": "publisher"}]}).encode()),
        "doi.org/": (403, {}, page)})
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    run.acquire(w, ws, pg.tokens[ws], run.work_record(w, work_id=work["work_id"]),
                store=Store(root, index_cache=tmp_path / "index.json"), agent="fxs", session="fxs-rehunt",
                clients={"open_access": stub}, pacer=P2M._nopace(), printer=lambda *a, **k: None,
                routes=("open_access",), pacing={})
    rows = pg.conn.execute("SELECT status, sub_status FROM litkb.acquisition_attempts WHERE work_id = %s AND "
                           "workstream_id = %s AND route = 'open_access' ORDER BY at, id",
                           (work["work_id"], ws)).fetchall()
    n = C1A.rehunt_route_spends(pg.conn, {"frozen_at": frozen, "run_workstream_ids": [str(ws)]})
    return n, rows, stub


@pg_only
def test_without_the_backfill_a_re_hunt_inside_the_replayed_window_is_asked_and_counted(pg, tmp_path):
    """REPRODUCTION of referee-substrate N1 on a REAL pair (green on main 411c3ce and here: it pins the failure the
    backfill exists for): the enforcement's stored window lapsed 45 min ago, so the re-hunt ASKS open access, and
    the gate — replaying the whole history — counts that spend inside its 6 h window."""
    _p, work = _shifted_rehunt_world(pg)
    n, rows, stub = _rehunt(pg, work, tmp_path)
    assert [r[0] for r in rows] == ["blocked"] and any("doi.org/" in u for u in stub.calls), (rows, stub.calls)
    assert n == 1, n


@pg_only
def test_after_the_backfill_a_re_hunt_inside_the_replayed_window_is_skipped_and_counted_by_nobody(pg, tmp_path):
    """The fix, on the same REAL pair: the reviewed backfill seeds the replayed state (2 refusals, the 6 h rung), and
    the re-hunt an hour after the run's refusal is `skipped/backoff_window` — no request — and the gate counts 0."""
    from litkb.acquire import backoff as B

    p, work = _shifted_rehunt_world(pg)
    assert _key(B.load(pg.conn, p["route"], work["work_id"]))[0] == 1          # what the run stored
    _plan, res = _apply(pg, [str(work["work_id"])], tmp_path)
    assert res["applied"]["applied"] == 1, res
    assert B.load(pg.conn, p["route"], work["work_id"])["refusals"] == 2
    n, rows, stub = _rehunt(pg, work, tmp_path)
    assert rows == [("skipped", "backoff_window")] and stub.calls == [], (rows, stub.calls)
    assert n == 0, n


# ── what the backfill refuses (CONSTRUCTED) ───────────────────────────────────────────────────────────────────
def _constructed_refusal(pg, ws, hours_ago, status="blocked", codes=(403,)):
    """A CONSTRUCTED work with one `blocked` attempt `hours_ago` hours ago, written by the owner (a pre-0033 row:
    no back-off move). -> (work, attempt id, at)."""
    w = pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    at = pg.one("SELECT clock_timestamp() - make_interval(hours => %s)", (hours_ago,))[0]
    aid = _insert(pg, work["work_id"], "open_access",
                  {"status": status, "sub_status": None, "sub_status_basis": None, "http_codes": list(codes),
                   "retriable": None}, ws, at)
    return work, aid, at


@pg_only
def test_the_backfill_refuses_what_it_cannot_explain_or_what_the_ledger_has_moved_past(pg, tmp_path):
    """CONSTRUCTED. (a) a stored 3-refusal state over a history of ONE refusal: unexplained, never offered, left as
    it is; (b) a reviewed row the ledger has moved past (a newer attempt arrived after the review) and (c) a reviewed
    row edited after the plan: refused by the op; (d) at the database, a row citing a non-latest attempt, a reset
    state and a window that starts after its attempt: refused per row, nothing written."""
    from litkb.acquire import backoff as B
    from litkb.quarantine import ingest_connect
    from psycopg.types.json import Jsonb

    ws_old, ws_run = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    a, a_aid, a_at = _constructed_refusal(pg, ws_run, 2)
    B.save(w, ws_run, pg.tokens[ws_run], a_aid, {"refusals": 3, "window_started_at": a_at,
                                                  "next_allowed_at": a_at + datetime.timedelta(hours=48)})
    b, b_aid, b_at = _constructed_refusal(pg, ws_old, 3)
    c, _c_aid, _c_at = _constructed_refusal(pg, ws_old, 4)
    ids = [str(x["work_id"]) for x in (a, b, c)]
    plan = B.backfill_plan(pg.conn, work_ids=ids)
    assert [u["work_id"] for u in plan["unexplained"]] == [str(a["work_id"])], plan["unexplained"]
    assert sorted(r["work_id"] for r in plan["rows"]) == sorted(ids[1:]), plan["rows"]
    before = pg.one("SELECT count(*) FROM litkb.acquisition_backfills")[0]

    def edit(r):
        return dict(r, refusals="2") if r["work_id"] == str(c["work_id"]) else r

    def newer():            # (b): the ledger moves past the reviewed plan — a newer attempt, a neutral miss
        _insert(pg, b["work_id"], "open_access", {"status": "no-oa-copy", "sub_status": None,
                                                  "sub_status_basis": None, "http_codes": [], "retriable": False},
                ws_old, pg.one("SELECT clock_timestamp()")[0])

    _plan, res = _apply(pg, ids, tmp_path, edit=edit, before_apply=newer)
    assert res["would_apply"] == 0 and sorted(x["work_id"] for x in res["refused"]) == sorted(ids[1:]), res
    assert res["applied"]["applied"] == 0, res
    assert _key(B.load(pg.conn, "open_access", a["work_id"]))[0] == 3            # (a) untouched
    assert B.load(pg.conn, "open_access", b["work_id"]) is None
    assert B.load(pg.conn, "open_access", c["work_id"]) is None
    assert pg.one("SELECT count(*) FROM litkb.acquisition_backfills")[0] == before + 1
    # (d) the database's own per-row checks
    c_latest = pg.one("SELECT id::text, at FROM litkb.acquisition_attempts WHERE work_id = %s ORDER BY at DESC, id "
                      "DESC LIMIT 1", (c["work_id"],))
    later = (c_latest[1] + datetime.timedelta(hours=1)).isoformat()
    rows = [{"attempt_id": b_aid, "refusals": 1, "window_started_at": b_at.isoformat(),
             "next_allowed_at": (b_at + datetime.timedelta(minutes=15)).isoformat()},        # not b's latest
            {"attempt_id": c_latest[0], "refusals": 0, "window_started_at": None, "next_allowed_at": None},
            {"attempt_id": c_latest[0], "refusals": 1, "window_started_at": later,
             "next_allowed_at": (c_latest[1] + datetime.timedelta(hours=2)).isoformat()},
            {"attempt_id": str(uuid.uuid4()), "refusals": 1, "window_started_at": later, "next_allowed_at": later}]
    rec = ingest_connect(pg.conn.info.dbname)
    try:
        got = rec.execute("SELECT litkb.backfill_route_backoff('fxs-test', 'CONSTRUCTED rows', %s)",
                          (Jsonb(rows),)).fetchone()[0]
    finally:
        rec.close()
    assert {k: got[k] for k in ("offered", "applied", "missing", "not_latest", "bad_state", "newer_row")} == \
        {"offered": 4, "applied": 0, "missing": 1, "not_latest": 1, "bad_state": 2, "newer_row": 0}, got
    assert B.load(pg.conn, "open_access", b["work_id"]) is None
    assert B.load(pg.conn, "open_access", c["work_id"]) is None
    # (e)-(h) S4.5 decision D56 (integrator-w4; auditor-FX-S F2): c's latest attempt is now a SKIP; a good refusal state
    # citing it whose `moved_attempt_id` is (e) absent, (f) another pair's attempt (b's), (g) that skip: refused per
    # row (`bad_mover`); (h) c's own blocked refusal: applied, and the row's `last_*` are THAT attempt's, never the skip.
    # (f2) S4.5 decision D61 (auditor-cand4 N2): a mover of the SAME work on ANOTHER route (c's `hal` refusal, before
    # the skip) is refused `bad_mover` too — the route clause of 0036's mover guard, which (f) alone never reaches
    c_hal = _insert(pg, c["work_id"], "hal", {"status": "blocked", "sub_status": None, "sub_status_basis": None,
                                              "http_codes": [403], "retriable": None},
                    ws_old, pg.one("SELECT clock_timestamp()")[0])
    c_skip = _insert(pg, c["work_id"], "open_access", {"status": "skipped", "sub_status": "policy_refused",
                                                      "sub_status_basis": "live", "http_codes": [], "retriable": None},
                     ws_old, pg.one("SELECT clock_timestamp()")[0])
    c_now = pg.one("SELECT at FROM litkb.acquisition_attempts WHERE id = %s", (c_skip,))[0]
    good = {"attempt_id": c_skip, "refusals": 1, "window_started_at": (c_now - datetime.timedelta(hours=4)).isoformat(),
            "next_allowed_at": (c_now + datetime.timedelta(hours=2)).isoformat()}
    movers = [dict(good), dict(good, moved_attempt_id=b_aid), dict(good, moved_attempt_id=c_skip),
              dict(good, moved_attempt_id=c_hal), dict(good, moved_attempt_id=_c_aid)]
    rec = ingest_connect(pg.conn.info.dbname)
    try:
        got2 = rec.execute("SELECT litkb.backfill_route_backoff('fxs-test', 'CONSTRUCTED mover rows', %s)",
                           (Jsonb(movers),)).fetchone()[0]
    finally:
        rec.close()
    assert {k: got2[k] for k in ("offered", "applied", "missing", "not_latest", "bad_state", "bad_mover",
                                 "newer_row")} == \
        {"offered": 5, "applied": 1, "missing": 0, "not_latest": 0, "bad_state": 0, "bad_mover": 4, "newer_row": 0}, got2
    last = pg.one("SELECT last_attempt_id::text, last_status FROM litkb.route_backoff WHERE route = 'open_access' "
                  "AND work_id = %s", (c["work_id"],))
    assert last == (_c_aid, "blocked"), last


def test_d61_last_mover_never_counts_an_original_its_retry_superseded():
    """S4.5 decision D61 (auditor-cand4 N3). CONSTRUCTED chains, one (route, work) pair, replayed by
    `BackoffPolicy.last_mover` (the backfill's `moved_attempt_id`, D56):
      * original `blocked` 403, retried in-run and the retry `ok`: the chain's final row is a success with no refusal
        before or after it, so the ladder's writer never moved the persisted row -> None. Counting the superseded
        original would make it a refusal, and the retry the "mover" of a row nothing wrote;
      * original `blocked`, its retry `blocked` again: the retry — the chain's final row — is the mover;
      * `replay` of the first chain agrees: no refusal stands (the original's refusal was superseded)."""
    from litkb.acquire import backoff as B

    t0 = datetime.datetime(2026, 9, 24, 8, 0, tzinfo=datetime.timezone.utc)
    t1 = t0 + datetime.timedelta(seconds=40)
    pol = B.BackoffPolicy()
    healed = [("orig-1", "blocked", [403], t0, None), ("retry-1", "ok", [200], t1, "orig-1")]
    assert pol.last_mover(healed) is None
    assert (pol.replay(healed) or {}).get("refusals", 0) == 0, pol.replay(healed)
    again = [("orig-2", "blocked", [403], t0, None), ("retry-2", "blocked", [403], t1, "orig-2")]
    assert pol.last_mover(again) == "retry-2"
    assert pol.replay(again)["refusals"] == 1, pol.replay(again)


@pg_only
def test_the_dry_run_writes_nothing_even_when_handed_the_ingest_login(pg, tmp_path, capsys):
    """The op is a DRY RUN unless `--apply`: handed a reviewed CSV and even the ingest login, it reports what would
    apply and writes nothing; the CLI writes the plan and nothing else; `--apply` without the reviewed CSV refuses."""
    from litkb.acquire import backoff as B
    from litkb.quarantine import ingest_connect

    ws = pg.ws()
    work, _aid, _at = _constructed_refusal(pg, ws, 2)
    before = pg.one("SELECT count(*) FROM litkb.acquisition_backfills")[0]
    rec = ingest_connect(pg.conn.info.dbname)
    try:
        _plan, res = _apply(pg, [str(work["work_id"])], tmp_path, apply=False, recorder=rec)
    finally:
        rec.close()
    assert res["mode"] == "dry-run" and res["would_apply"] == 1 and "applied" not in res, res
    assert B.load(pg.conn, "open_access", work["work_id"]) is None
    assert pg.one("SELECT count(*) FROM litkb.acquisition_backfills")[0] == before
    out = tmp_path / "cli-plan.csv"
    rc = B.main(["--db", pg.conn.info.dbname, "--role", "litkb_test", "backfill", "--session", "fxs-cli",
                 "--out", str(out)])
    said = json.loads(capsys.readouterr().out)
    assert rc == 0 and said["mode"] == "dry-run" and out.exists(), said
    assert str(work["work_id"]) in out.read_text(encoding="utf-8")
    assert B.load(pg.conn, "open_access", work["work_id"]) is None
    assert pg.one("SELECT count(*) FROM litkb.acquisition_backfills")[0] == before
    with pytest.raises(ValueError):
        B.backfill(pg.conn, session="fxs-test", apply=True, recorder=None)


@pg_only
def test_only_the_ingest_login_may_run_the_backfill(pg):
    for role in ("litkb_writer", "litkb_reader"):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            pg.session(role).execute("SELECT litkb.backfill_route_backoff('s', 'x', '[]'::jsonb)")


# ── export.arxiv.org: the recorded 406s, the pacer, the booking ───────────────────────────────────────────────
def _recorded_406():
    """-> {arXiv id: (row id, status, headers, body)} from the ladder-1 cassette's own lines (checked against the
    provenance's index sha256 and every body's recorded sha256)."""
    prov = json.loads((CASSETTE / "provenance.json").read_text(encoding="utf-8"))
    data = (CASSETTE / "index.jsonl").read_bytes()
    assert hashlib.sha256(data).hexdigest() == prov["index_sha256"], "the recorded index is not the bytes copied"
    rows = {e["arxiv_id"]: e["row"] for e in prov["entries"]}
    out = {}
    for ln in data.split(b"\n")[1:]:
        if not ln.strip():
            continue
        e = json.loads(ln)
        body = base64.b64decode(e["response"]["body"]["inline_b64"])
        assert hashlib.sha256(body).hexdigest() == e["response"]["body"]["sha256"]
        aid = e["key"]["url"].split("id_list=", 1)[1]
        out[aid] = (rows[aid], e["response"]["status"], e["response"]["headers"], body)
    assert sorted(r[0] for r in out.values()) == [f"L0{n}" for n in range(10, 18)], out
    return out


class RecordedArxiv:
    """export.arxiv.org as the run met it: every id_list URL answered with its RECORDED answer (status, headers,
    body). Records the process clock (`time.monotonic`) of every request. Any other URL fails the test."""
    base = ""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append((time.monotonic(), url, accept))
        assert url.startswith("http://export.arxiv.org/api/query?id_list="), url
        _row, st, hd, body = self.answers[url.split("id_list=", 1)[1]]
        return st, dict(hd), body


def _admit_arxiv(aid, client, pacer=None):
    """The admission `hunt` makes for an arXiv reference (`front.admit_registry`, no claim); a registry answer that
    is not a record returns before the database is touched."""
    from litkb.admit import front
    return front.admit_registry(None, None, None, arxiv=aid, agent="fxs", session="fxs-1", client=client, pacer=pacer)


def test_three_real_admissions_each_with_its_own_registry_pacer_meet_one_3_s_arxiv_gate():
    """REAL answers, rows L010-L012. Each admission builds its OWN registry pacer (pacer=None, exactly as `hunt` and
    the run driver call it); the run's 8 requests went 0.41-0.62 s apart (referee-substrate N3). On the process clock
    the three requests now meet ONE arXiv gate: at least ARXIV_MIN_INTERVAL apart."""
    from litkb.admit import resolver as R

    rec = _recorded_406()
    stub = RecordedArxiv(rec)
    for aid in list(rec)[:3]:
        _admit_arxiv(aid, stub)
    t = [c[0] for c in stub.calls]
    gaps = [b - a for a, b in zip(t, t[1:])]
    assert len(t) == 3 and all(g >= R.ARXIV_MIN_INTERVAL - 0.05 for g in gaps), gaps


def test_a_pacer_on_an_injected_clock_or_pacing_nothing_keeps_an_arxiv_pacer_of_its_own():
    """Only production pacers share the process gate: a test's or a replay's injected clock, and a pacer of interval 0
    (`stage_b.pacer_for`'s "paces nothing"), keep their own (so they never sleep on the wall clock for it)."""
    from litkb.admit import resolver as R
    from litkb.netutil import Pacer

    shared = R.process_arxiv_pacer()
    assert shared.interval == R.ARXIV_MIN_INTERVAL and R.process_arxiv_pacer() is shared
    real_a, real_b = Pacer(interval=R.REGISTRY_MIN_INTERVAL), Pacer(interval=R.REGISTRY_MIN_INTERVAL)
    assert R.arxiv_pacer_for(real_a) is shared and R.arxiv_pacer_for(real_b) is shared
    t = [0.0]
    fake = Pacer(interval=R.REGISTRY_MIN_INTERVAL, sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
    zero = Pacer(interval=0)
    for p in (fake, zero):
        own = R.arxiv_pacer_for(p)
        assert own is not shared and R.arxiv_pacer_for(p) is own and own.interval == R.ARXIV_MIN_INTERVAL


def test_the_recorded_l010_l017_406s_are_booked_not_retriable_with_the_evidence():
    """REAL answers, all 8 rows. Each 406 is `registry-transient` (no admission written: not a verdict on the
    record), asked ONCE (no in-call retry), and booked `retryable` False with the evidence — the host, the status and
    what was measured — and a message that does not say "hunt the reference again"."""
    from litkb.admit import resolver as R

    rec = _recorded_406()
    stub = RecordedArxiv(rec)
    for aid, (row, st, _hd, _body) in rec.items():
        assert st == 406
        res = _admit_arxiv(aid, stub, pacer=P2M._nopace())
        assert res["outcome"] == "registry-transient" and res["retryable"] is False, (row, res)
        (f,) = res["client_refusal"]
        assert (f["host"], f["registry"], f["status"]) == ("export.arxiv.org", "arxiv", 406), (row, f)
        assert "32 of 32" in f["measured"] and "2026-09-24T23:56Z" in f["measured"], f
        assert "not retriable in this run" in res["message"] and "hunt the reference again" not in res["message"]
    assert [u for _t, u, _a in stub.calls] == [R.ARXIV_ID_LIST.format(id=aid) for aid in rec]


def test_a_transient_registry_answer_stays_retriable():
    """CONSTRUCTED: a 503 from export.arxiv.org and a 406 from Crossref (the S3 shape) are transient answers and stay
    `retryable` with no client-refusal facts — the booking is export.arxiv.org's 406 alone."""
    from litkb.admit import front, registry

    class Status:
        base = ""

        def __init__(self, st):
            self.st = st

        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            return self.st, {}, b""

    res = _admit_arxiv("2501.15377", Status(503), pacer=P2M._nopace())
    assert res["retryable"] is True and "client_refusal" not in res, res
    res = front.admit_registry(None, None, None, doi="10.5555/fxs-constructed", agent="fxs", session="fxs-1",
                               client=Status(406), pacer=P2M._nopace())
    assert res["outcome"] == "registry-transient" and res["retryable"] is True and "client_refusal" not in res, res
    assert registry.retriable("crossref", 406) is True and registry.retriable("arxiv", 406) is False


def test_d56_a_mixed_doi_and_arxiv_admission_is_retriable_when_any_registry_answer_is():
    """S4.5 decision D56 (integrator-w4; auditor-FX-S F1), CONSTRUCTED (a stub, no database, no network): an admission
    naming BOTH a DOI and an arXiv id — `admit --doi --arxiv`, the MCP `litkb_admit` — where Crossref and DataCite
    answer 503 (retriable) and export.arxiv.org 406 (the client refusal). An immediate re-ask could confirm the DOI
    through Crossref, so the admission is `retryable` True; the arXiv refusal's facts stay attached. arXiv alone: not
    retriable (the recorded rows' case, above)."""
    from litkb.admit import front

    class Mixed:
        base = ""

        def __init__(self):
            self.calls = []

        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            self.calls.append(url)
            return (406, {}, b"") if "arxiv.org" in url else (503, {}, b"")

    stub = Mixed()
    res = front.admit_registry(None, None, None, doi="10.5555/fxs-d56-constructed", arxiv="1906.02530", agent="fxs",
                               session="fxs-1", client=stub, pacer=P2M._nopace())
    assert res["outcome"] == "registry-transient" and res["retryable"] is True, res
    assert [(c["registry"], c["status"]) for c in res["transient"]] == [("crossref", 503), ("datacite", 503),
                                                                       ("arxiv", 406)], res["transient"]
    assert [(f["registry"], f["status"]) for f in res["client_refusal"]] == [("arxiv", 406)], res
    alone = front.admit_registry(None, None, None, arxiv="1906.02530", agent="fxs", session="fxs-1", client=Mixed(),
                                 pacer=P2M._nopace())
    assert alone["retryable"] is False and alone["client_refusal"], alone


def test_the_plan_csv_is_never_written_over_an_existing_file(tmp_path):
    """auditor-FX-S F3 (S4.5 decision D58): `write_plan_csv` "never overwrites a file" — an `--out` naming an existing
    path raises and leaves that file byte-identical (CONSTRUCTED rows)."""
    from litkb.acquire import backoff as B

    p = tmp_path / "plan.csv"
    p.write_bytes(b"a reviewed plan already here\r\n")
    before = p.read_bytes()
    with pytest.raises(FileExistsError):
        B.write_plan_csv([{"route": "open_access", "work_id": "CONSTRUCTED"}], p)
    assert p.read_bytes() == before


@pytest.fixture
def hunt_env(tmp_path, monkeypatch, litkb_pg_base):
    """A literature root, a worktree with a real workstream, and the worker database (qc/test_litkb_hunt.py's env)."""
    from litkb import workstream
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    workstream.open_workstream(conn, f"fxs-{uuid.uuid4().hex[:8]}", "test", "FX-S hunt test", directory=wt)
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt), "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "fxs-test", "LITKB_SESSION": f"fxs-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    return {"conn": conn, "root": root, "wt": wt, "db": c.DB_TEST, "tmp": tmp_path}


@pg_only
def test_the_hunt_books_the_recorded_l010_406_as_api_error_not_retriable_and_writes_nothing(hunt_env):
    """REAL answer, row L010, through the hunt the run driver called: `api-error/registry-transient` (the closed
    vocabulary does not grow), `retryable` False with the client-refusal facts, and no admission row."""
    from litkb import hunt as H
    from litkb.acquire.store import Store

    rec = _recorded_406()
    stub = RecordedArxiv(rec)
    n = lambda: hunt_env["conn"].execute("SELECT count(*) FROM litkb.admissions").fetchone()[0]  # noqa: E731
    before = n()
    res = H.hunt("1906.02530", ref_scheme="arxiv", db=hunt_env["db"], worktree=hunt_env["wt"], agent="fxs-test",
                 session="fxs-hunt", reader_role="litkb_test", writer_role="litkb_test",
                 store=Store(root=hunt_env["root"], index_cache=hunt_env["tmp"] / "index.json"),
                 derived=str(hunt_env["tmp"] / "derived"), registry_client=stub, spend=False)
    assert (res["state"], res["reason"]) == ("api-error", "registry-transient"), res
    assert res["retryable"] is False and res["client_refusal"][0]["host"] == "export.arxiv.org", res
    assert n() == before and len(stub.calls) == 1, (n(), stub.calls)

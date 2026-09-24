"""litkb S4.5 — the SEAMS between builders A (hardening, replay), C1a (the ledger, the ladder) and C1b (THE
acceptance test, the sidecars), on the merged candidate (integrator-w1). Each test names the two builders whose
code meets at it; every one failed, or could not have been written, on any one builder's branch alone.

  C1a x C1b  one bad-file vocabulary and one byte classifier: the ledger's `sub_status` for a `bad-file` row is
             THE acceptance test's own word — on the live typing and on C1b's item-8 CSV through C1a's backfill;
             every rung's bytes go through the acceptance test before they bind (`run._land`); the route header
             checks are the test's `quick_magic`; every quarantine the ladder makes carries its sidecar, and
             MEASURE mode quarantines nothing
  A x C1a    the run driver's MEASURE hook is the ladder's; MEASURE mode asks a route whose earlier answer was a
             terminal miss; the cassette at `Client._raw_get` records and replays the Unpaywall lookup C1a routed
             through the client, and the tracked index never carries the account email
  A x C1a/C1b  `hardening` loads C1a's and C1b's counter modules and every counter they own reads a value; every
             fire they define has a bound the harness can read

No test touches the network (loopback only, inside the suite's socket guard) or the live store.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_seams.py -q
"""
import csv
import hashlib
import http.server
import importlib.util
import json
import threading
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
pg_only = pytest.mark.requires_litkb_pg
BADFILE_CSV = REPO / "phase4" / "qc" / "litkb_acq_probe_badfile.csv"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2M = _load("_litkb_p2_for_seams", SCRIPTS / "qc" / "test_litkb_p2.py")
INSTR = SCRIPTS / "qc" / "instruments"


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
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "seams-test@example.invalid")


def _store(tmp_path):
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def _unpaywall(*urls):
    loc = [{"url": u, "host_type": "publisher", "version": "publishedVersion"} for u in urls]
    return 200, {}, json.dumps({"is_oa": True, "oa_status": "bronze", "best_oa_location": loc[0],
                                "oa_locations": loc}).encode()


def _oa(body, headers=None):
    """The open-access route asked through a stub client: Unpaywall lists one location, which serves `body`."""
    return {"open_access": P2M.RouteStub({"api.unpaywall.org": _unpaywall("https://oa.example/p.pdf"),
                                          "oa.example": (200, headers or {}, body)})}


def _acq(pg, w, ws, work, store, clients, **kw):
    from litkb.acquire import run
    kw.setdefault("pacing", {})
    kw.setdefault("routes", ("open_access",))
    return run.acquire(w, ws, pg.tokens[ws], work, store=store, agent="seams", session="seams-1", clients=clients,
                       pacer=P2M._nopace(), printer=lambda *a, **k: None, **kw)


def _rows(pg, wid):
    return pg.conn.execute("SELECT route, status, sub_status, detail FROM litkb.acquisition_attempts "
                           "WHERE work_id = %s ORDER BY at, id", (wid,)).fetchall()


#: CONSTRUCTED: Elsevier's first-page-only TDM answer is announced ONLY in this header (H2-RG); the VALUE is
#: invented here, as in builder C1b's CONSTRUCTED negative — the acceptance test reads any non-OK value.
STUB_HEADERS = {"Content-Type": "application/pdf", "X-ELS-Status": "CONSTRUCTED first page only"}


# ── C1a x C1b: one vocabulary, one byte classifier ────────────────────────────────────────────

def test_the_bad_file_vocabulary_has_one_home():
    from litkb.acquire import accept as A
    from litkb.acquire import policy as P

    assert A.SUB_STATUSES is P.BAD_FILE_SUBS


def test_the_bad_file_typing_is_the_acceptance_tests_word():
    """The ledger's live typing (`ledger.sub_status_for`) and C1b's item-8 instrument (`type_kept`) give every
    byte string the sub-status `accept.accept` gives it: one classifier for the live rows and the backfill."""
    from litkb.acquire import accept as A
    from litkb.acquire import ledger as L

    badfile = _load("_badfile_for_seams", INSTR / "litkb_acq_probe_badfile.py")
    whole = P2M.paper_pdf("A seam paper", "T. Tester")
    cases = {"html": P2M.salted_html(), "dns string": b"URLError: <urlopen error [Errno 11001] getaddrinfo failed>",
             "cut before the trailer": whole[:whole.rindex(b"trailer")], "empty": b"",
             "a small pdf": P2M.make_pdf(["a one-line page"])}
    want = {"html": "html_response", "dns string": "too_small", "cut before the trailer":
            "early_eof_with_trailing_payload", "empty": None, "a small pdf": "too_small"}
    for name, data in cases.items():
        verdict = A.accept(data, metadata_fetched=False) if data else None
        own = verdict.sub_status if verdict is not None else None
        assert L.sub_status_for("bad-file", "open_access", [200], data)[0] == own == want[name], name
        if data:
            assert badfile.type_kept(data)[0] == own, name
    assert L.bad_file_sub(whole) is None, "a whole paper is no bad file: the typing must not invent a word"


def test_the_route_header_checks_are_the_acceptance_tests(tmp_path):
    """A PDF served after a byte-order mark is a PDF to the acceptance test (repair before magic); the routes'
    own early sniff must agree, or a route refuses what the gate would accept (C1b's list: open_access, scihub)."""
    from litkb.acquire import open_access, scihub

    bom = b"\xef\xbb\xbf" + P2M.paper_pdf("A byte-order-marked paper", "T. Tester")
    oa = open_access.fetch_open_access("10.5555/seams-bom", None, None, client=_oa(bom)["open_access"])
    assert oa["status"] == "downloaded" and oa["pdf"] == bom, oa["status"]
    page = b'<html><head><meta name="citation_pdf_url" content="/files/x.pdf"></head></html>'
    sh = scihub.fetch_scihub("10.5555/seams-bom", None, mirrors=("https://mirror.example",),
                             client=P2M.RouteStub({"mirror.example/10.5555": (200, {}, page),
                                                   "mirror.example/files/x.pdf": (200, {}, bom)}))
    assert sh["status"] == "downloaded", sh
    for rel in ("pipeline/litkb/acquire/open_access.py", "pipeline/litkb/acquire/scihub.py",
                "pipeline/litkb/acquire/run.py", "pipeline/litkb/acquire/ledger.py"):
        src = (SCRIPTS / rel).read_text(encoding="utf-8")
        assert 'startswith(b"%PDF-")' not in src and '[:5] == b"%PDF-"' not in src, rel


# ── C1a x C1b: the ladder's landing IS the acceptance test ────────────────────────────────────

@pg_only
def test_the_ladder_binds_a_rungs_bytes_only_through_the_acceptance_test(pg, tmp_path):
    """A whole, binding paper served with a first-page-only header (CONSTRUCTED): the acceptance test refuses it
    `stub_not_article` before the bind; the attempt row stores that word and the verdict; the bytes are kept with
    a sidecar that carries both; nothing is filed; C1b's `stubs_bound` reads 0 on the run. With the landing guard
    removed (`run._land`, mutation row INT1) the same bytes BIND and `stubs_bound` reads 1."""
    P2M._need_pdftotext()
    from litkb import quarantine as Q

    c1b = _load("_c1b_for_seams", INSTR / "litkb_hardening_c1b.py")
    frozen = pg.one("SELECT clock_timestamp()")[0]
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    pdf = P2M.paper_pdf(work["title"], "T. Tester")
    out = _acq(pg, w, ws, work, store, _oa(pdf, STUB_HEADERS))
    assert out["outcome"] == "not-acquired", out
    (route, status, sub, detail), = [r for r in _rows(pg, work["work_id"]) if r[0] == "open_access"]
    assert (status, sub) == ("bad-file", "stub_not_article"), (status, sub, detail)
    assert detail["acceptance"]["facts"]["stub_signals"] == ["x_els_status"], detail["acceptance"]
    assert P2M._files_under(store.filed) == [], "a stub was filed"
    side = json.loads((store.root / detail["quarantine_reason"]).read_text(encoding="utf-8"))
    assert side["sub_status"] == "stub_not_article" and side["acceptance"]["verdict"] == "refuse", side
    assert Q.without_reason(store.root) == (0, [])
    m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "literature_root": str(store.root)}
    assert c1b.stubs_bound(pg.conn, m) == 0


def _short_page(title, author):
    """CONSTRUCTED: a one-page PDF whose text is a title, an author and two body lines (under 3,000 characters,
    no reference heading: the acceptance test's `chars_no_refs` stub), padded past the 5,000-byte floor by a
    long /Subject in its document information — so the stub is visible in the BYTES, where C1b's `stubs_bound`
    re-detects it (a header-only stub bound with the guard off leaves no evidence the counter can read)."""
    lines = ["Journal of Synthetic Studies 1 (2020) 1-10", title, f"{author} and A. Coauthor", "",
             "Preview: the first page only.", f"id {uuid.uuid4().hex}"]
    return P2M.make_pdf(lines, info={"Subject": "p" * 5000})


@pg_only
@pytest.mark.parametrize("arm", ["control", "known_bad"])
def test_stubs_bound_fires_through_the_ladder(pg, tmp_path, monkeypatch, arm):
    """The plan's (c) "the constructed TDM stub ... -> stubs_bound=1 if either binds", through the LADDER the live
    run lands with (builder C1b's own fires offer the stub to `offer_to_bind` directly, which the ladder did not
    call before the merge). Control: refused `stub_not_article`, `stubs_bound`=0. Known-bad: the landing's
    acceptance test removed in-process (`run._land` falls back to the bind alone) — the stub BINDS and
    `stubs_bound`=1."""
    P2M._need_pdftotext()
    from litkb.acquire import accept

    c1b = _load(f"_c1b_for_seams_{arm}", INSTR / "litkb_hardening_c1b.py")
    frozen = pg.one("SELECT clock_timestamp()")[0]
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    if arm == "known_bad":
        monkeypatch.setattr(accept, "offer_to_bind", None)
    _acq(pg, w, ws, work, store, _oa(_short_page(work["title"], "T. Tester")))
    (_route, status, sub, _detail), = [r for r in _rows(pg, work["work_id"]) if r[0] == "open_access"]
    m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "literature_root": str(store.root)}
    if arm == "control":
        assert (status, sub, c1b.stubs_bound(pg.conn, m)) == ("bad-file", "stub_not_article", 0)
    else:
        assert (status, c1b.stubs_bound(pg.conn, m)) == ("ok", 1)


@pg_only
def test_a_refused_download_is_typed_by_the_acceptance_test_and_keeps_what_it_read(pg, tmp_path):
    """A landing page served where the PDF was expected (the route refuses it; the ladder keeps it): the row's
    sub-status is the acceptance test's `html_response`, and the page's PDF pointer (what Stage C and the
    `landing_pages_booked_bad_file` counter read) is on the attempt row, not lost with the verdict."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    page = (b'<!DOCTYPE html><html><head><meta name="citation_pdf_url" content="https://oa.example/real.pdf">'
            b'<title>Landing</title></head><body>' + uuid.uuid4().hex.encode() + b"</body></html>")
    _acq(pg, w, ws, work, store, _oa(page))
    (route, status, sub, detail), = [r for r in _rows(pg, work["work_id"]) if r[0] == "open_access"]
    assert (status, sub) == ("bad-file", "html_response"), (status, sub)
    assert detail["acceptance"]["facts"]["landing"]["pdf_pointer"] is True, detail["acceptance"]
    assert detail["quarantined"] and (store.root / detail["quarantine_reason"]).is_file(), detail


@pg_only
def test_every_quarantine_the_ladder_makes_has_its_sidecar_and_measure_mode_makes_none(pg, tmp_path):
    """Three refusals through the rewritten loop — a route-refused page, a paper that does not bind, a stub the
    acceptance test refuses — each quarantined WITH its sidecar (`quarantine.without_reason` = 0). The same three
    in MEASURE mode: recorded, typed, and nothing in _quarantine/ at all."""
    P2M._need_pdftotext()
    from litkb import quarantine as Q
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    for mode in ("acquire", "measure"):
        store = _store(tmp_path / mode)
        works = [P2M._admitted(pg, w, ws) for _ in range(3)]
        serve = [_oa(P2M.salted_html()),
                 _oa(P2M.paper_pdf("Tidal mixing fronts in the Irish Sea", "J. Simpson")),
                 _oa(P2M.paper_pdf(works[2]["title"], "T. Tester"), STUB_HEADERS)]
        for work, clients in zip(works, serve):
            if mode == "measure":
                run.measure(w, ws, pg.tokens[ws], work, store=store, agent="seams", session="seams-1",
                            clients=clients, routes=("open_access",), pacer=P2M._nopace(),
                            printer=lambda *a, **k: None, pacing={})
            else:
                _acq(pg, w, ws, work, store, clients)
        got = [[(r[1], r[2]) for r in _rows(pg, wk["work_id"]) if r[0] == "open_access"] for wk in works]
        if mode == "acquire":
            assert got == [[("bad-file", "html_response")], [("binding-failed", None)],
                           [("bad-file", "stub_not_article")]], got
            assert len(Q.payloads(store.root)) == 3 and Q.without_reason(store.root) == (0, [])
        else:
            assert got == [[("bad-file", "html_response")], [("measured", None)],
                           [("bad-file", "stub_not_article")]], got
            assert Q.payloads(store.root) == [] and P2M._files_under(store.staging) == []


# ── A x C1a: the run driver's MEASURE hook ─────────────────────────────────────────────────────

def test_the_run_drivers_measure_hook_is_the_ladders():
    from litkb.acquire import run

    lr = _load("_ladder_run_for_seams", INSTR / "litkb_ladder_run.py")
    assert lr.measure_hook() is run.measure


@pg_only
def test_measure_mode_asks_a_route_whose_earlier_answer_was_a_miss(pg, tmp_path):
    """A work whose open-access route answered `no-oa-copy` before (a DEAD_STATUSES miss): the ladder in acquire
    mode skips it `dead_route`; the MEASURE hook asks it (S4.5 decision D9, "every rung is asked") and records
    the answer, landing nothing. A `blocked` answer in the run still skips it in MEASURE mode."""
    P2M._need_pdftotext()
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", work["doi"], "no-oa-copy", {}, [404])
    _acq(pg, w, ws, work, store, _oa(P2M.paper_pdf(work["title"], "T. Tester")))
    oa = [(r[1], r[2]) for r in _rows(pg, work["work_id"]) if r[0] == "open_access"]
    assert oa == [("no-oa-copy", None), ("skipped", "dead_route")], oa
    out = run.measure(w, ws, pg.tokens[ws], work, store=store, agent="seams", session="seams-1",
                      clients=_oa(P2M.paper_pdf(work["title"], "T. Tester")), routes=("open_access",),
                      pacer=P2M._nopace(), printer=lambda *a, **k: None, pacing={})
    last = [r for r in _rows(pg, work["work_id"]) if r[0] == "open_access"][-1]
    assert out["outcome"] == "measured" and last[1] == "measured", (out, last)
    assert last[3]["acceptance"]["verdict"] == "accept", last[3]
    assert P2M._files_under(store.filed) == []
    work2 = P2M._admitted(pg, w, ws)
    run.record_attempt(w, ws, pg.tokens[ws], work2["work_id"], "open_access", work2["doi"], "blocked", {}, [403],
                       sub_status="challenge_or_bot_check")
    run.measure(w, ws, pg.tokens[ws], work2, store=store, agent="seams", session="seams-1", clients={},
                routes=("open_access",), pacer=P2M._nopace(), printer=lambda *a, **k: None, pacing={})
    assert [(r[1], r[2]) for r in _rows(pg, work2["work_id"]) if r[0] == "open_access"][-1] == (
        "skipped", "dead_in_run")


# ── A x C1a: the cassette sees the Unpaywall lookup ────────────────────────────────────────────

class _Server:
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


def test_the_unpaywall_lookup_is_recorded_and_replayed_and_its_email_never_reaches_the_index(tmp_path, monkeypatch):
    """C1a routed Unpaywall through `netutil.Client` (decision D3) so A's cassette at `Client._raw_get` would see
    it: the whole open-access route is RECORDED against a loopback 'Unpaywall' and its location, then REPLAYED
    with the server down inside a guard that allows nothing — the same PDF, no socket. The account email the
    lookup carries is in neither the tracked index nor the body store."""
    from litkb import cassette as C
    from litkb.acquire import open_access
    from litkb.netutil import Client

    email = f"seams-{uuid.uuid4().hex[:8]}@example.invalid"
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: email)
    doi = "10.5555/seams-unpaywall"
    pdf = P2M.paper_pdf("A recorded open-access paper", "T. Tester")
    idx, bodies = tmp_path / "cas" / "index.jsonl", tmp_path / "bodies"
    table = {}                          # filled once the port is known: the location URL carries it
    with _Server(table) as srv:
        loc = f"{srv.base}/files/paper.pdf"
        record = json.dumps({"is_oa": True, "oa_status": "green", "best_oa_location": {"url": loc, "version": "acceptedVersion"},
                             "oa_locations": [{"url": loc, "version": "acceptedVersion"}]}).encode()
        table.update({f"/v2/{doi}": (200, "application/json", record),
                      "/files/paper.pdf": (200, "application/pdf", pdf)})
        monkeypatch.setattr(open_access, "UNPAYWALL_API", srv.base + "/v2/{doi}")
        rec = C.Cassette(idx, "record", bodies=bodies)
        rec.begin_row(doi)
        live = open_access.fetch_open_access(doi, None, None, client=Client(base="", cassette=rec))
    assert live["status"] == "downloaded" and live["pdf"] == pdf and live["version"] == "acceptedVersion", live
    assert len(rec.recorded) == 2, rec.recorded
    rep = C.Cassette(idx, "replay", bodies=bodies)
    rep.begin_row(doi)
    guard = C.SocketGuard(allow_hosts=(), label="seams replay")
    with guard:
        again = open_access.fetch_open_access(doi, None, None, client=Client(base="", cassette=rep))
    assert (again["status"], again["pdf"]) == ("downloaded", pdf) and guard.attempts == [], guard.attempts
    assert rep.stale() == {"unplayed": [], "misses": []}
    tracked = idx.read_bytes() + b"".join(p.read_bytes() for p in Path(bodies).rglob("*") if p.is_file())
    assert email.encode() not in tracked, "the Unpaywall account email reached the tracked cassette"
    assert b"/v2/" + doi.encode() in idx.read_bytes(), "the Unpaywall lookup was not recorded"


# ── C1a x C1b: C1b's typing CSV is C1a's backfill input ────────────────────────────────────────

def test_the_committed_badfile_csv_is_a_typing_csv_the_backfill_offers_whole():
    """phase4/qc/litkb_acq_probe_badfile.csv (C1b, item 8) carries C1a's TYPING_COLUMNS under their own names,
    and C1a's reader offers every row of it: none refused, every sub-status a `bad-file` word, every basis one the
    backfill function accepts."""
    from litkb.acquire import ledger as L
    from litkb.acquire import policy as P

    with open(BADFILE_CSV, encoding="utf-8-sig", newline="") as fh:
        header = csv.DictReader(fh).fieldnames
        n = sum(1 for _ in fh)
    assert set(L.TYPING_COLUMNS) <= set(header), header
    rows, refused = L.read_typing_csv(BADFILE_CSV)
    assert refused == [] and len(rows) == n and n > 0, refused
    assert {r["sub_status"] for r in rows} <= set(P.BAD_FILE_SUBS)
    assert {r["basis"] for r in rows} <= set(P.SUB_STATUS_BASES) - {"live"}


@pg_only
def test_c1bs_typing_applied_by_c1as_backfill_types_the_rows(pg, tmp_path):
    """Untyped `bad-file` rows on a worker database, typed by C1b's instrument (`type_kept` = the acceptance
    test) into a CSV written under C1b's own COLUMNS, applied by C1a's backfill: every row is typed with the
    acceptance test's word and the instrument's basis."""
    from litkb.acquire import ledger as L
    from litkb.acquire import run
    from litkb.db import connect as c
    from litkb.quarantine import ingest_connect

    badfile = _load("_badfile_for_seams2", INSTR / "litkb_acq_probe_badfile.py")
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    kept = {"html": P2M.salted_html(), "dns": b"URLError: <urlopen error getaddrinfo failed> " + uuid.uuid4().hex.encode()}
    ids = {k: run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", None, "bad-file",
                                 {"sha256": hashlib.sha256(v).hexdigest()}, [200]) for k, v in kept.items()}
    f = tmp_path / "litkb_acq_probe_badfile.csv"
    with open(f, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=badfile.COLUMNS)
        wr.writeheader()
        for k, data in kept.items():
            st, cause, free, _grade, _fix, _reason, _ptr = badfile.type_kept(data)
            wr.writerow({"attempt_id": str(ids[k]), "sub_status": st, "basis": "bytes", "cause": cause,
                         "free_to_fix": free})
    rec = ingest_connect(c.DB_TEST)
    try:
        out = L.backfill_sub_status(pg.conn, f, session="seams", apply=True, recorder=rec)
    finally:
        rec.close()
    assert out["applied"]["applied"] == 2, out
    got = dict(pg.conn.execute("SELECT id::text, sub_status || '/' || sub_status_basis FROM litkb.acquisition_attempts "
                               "WHERE id = ANY(%s)", ([str(i) for i in ids.values()],)).fetchall())
    assert got == {str(ids["html"]): "html_response/bytes", str(ids["dns"]): "too_small/bytes"}, got


# ── A x C1a/C1b: the hardening loader ──────────────────────────────────────────────────────────

@pg_only
def test_hardening_reads_every_counter_c1a_and_c1b_own(pg, tmp_path):
    """`hardening` loads litkb_hardening_c1a.py and litkb_hardening_c1b.py by path, and every gated and reported
    counter they define reads a VALUE (never `unread`) on a manifest shaped the way `--freeze` writes it."""
    acc = _load("_acceptance_for_seams", INSTR / "litkb_acceptance.py")
    c1a = _load("_c1a_for_seams", INSTR / "litkb_hardening_c1a.py")
    c1b = _load("_c1b_for_seams2", INSTR / "litkb_hardening_c1b.py")
    mods = acc._hardening_modules()
    assert mods["failed"] == [], mods["failed"]
    assert {s for s, _p in mods["loaded"]} >= {"litkb_hardening_a", "litkb_hardening_c1a", "litkb_hardening_c1b"}
    (tmp_path / "Lit" / "_quarantine").mkdir(parents=True)
    m = {"frozen_at": pg.one("SELECT clock_timestamp()")[0], "workstream_id": str(pg.ws()), "repo": str(tmp_path),
         "literature_root": str(tmp_path / "Lit"), "report_path": "absent.md", "referee_reports": {}}
    m["run_workstream_ids"] = [m["workstream_id"]]
    gated, reported, offences, _mods = acc.check_hardening(m, conn=pg.conn)
    for name in (*c1a.COUNTERS, *c1b.COUNTERS):
        assert isinstance(gated.get(name), int), (name, [o for o in offences if o.startswith(name)])
    for name in (*c1a.REPORTED, *c1b.REPORTED):
        assert isinstance(reported.get(name), int), (name, [o for o in offences if o.startswith(name)])


def test_every_fire_has_a_bound_the_harness_reads():
    """A fire's bound is the gated counter's, or its own `bound` in the harness's grammar (`=N` / `>=N`): C1b's
    `bom_repair` carried the int 0, which the harness read as "no bound" (DID-NOT-FIRE, whatever it measured)."""
    acc = _load("_acceptance_for_seams2", INSTR / "litkb_acceptance.py")
    mods = acc._hardening_modules()
    gated = dict(acc.HARDENING_GATED)
    for name, (spec, stem) in mods["fires"].items():
        bound = spec.get("bound") or gated.get(spec["counter"])
        assert isinstance(bound, str) and acc._bound_ok(0, bound) in (True, False), (stem, name, bound)
    res = acc.hardening_fire("bom_repair", db="unused", conn=object(), reset=lambda conn: None)
    assert res["verdict"] == "FIRED", res["lines"]

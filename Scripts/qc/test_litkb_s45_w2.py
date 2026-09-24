"""litkb S4.5 — integrator-w2: the orchestrator's rulings D15-D22 and the auditor notes, on the final merged candidate
(A + C1a + C1b + B1 + B2 + C2b + C2c on integrator-w1's seams). Each test names the ruling or finding it holds and
fails when that ruling's code is reverted (a mutation row in qc/instruments/litkb_p2_mutations.py, block
"integrator-w2", names each one).

  D15   a no-byte `bad-file` whose DECLARED length is under the byte floor is `too_small`; an archive answer whose
        every partner request failed in transport carries its codes (so the ladder books it `api-error`) and never
        keeps the client's own error text as served bytes
  D17   the hunt URL path runs THE acceptance test (a first-page stub is refused, kept, and never admitted);
        `--from-file` runs it too, records the verdict on the PROPOSAL, and refuses only a hard byte failure
  D18   MEASURE mode asks the legitimate tiers only: the archive and the shadow stage are recorded skips
  D19   the Stage B counter accepts an `identifiers:` line for a rung the registry marks metadata-only, and
        `hunt` / the MEASURE hook reach every registered rung
  D20   the replay's pinned-mirror policy widening never leaks into a live PolicyDecision
  D22   every attempt that was served bytes records the stub-relevant headers itself (D21's ladder fires rest on it)
  auditor-C2c r3 F1  Stage E3/E5's transient stops: a 503 is `api-error`, retriable, the rung stops, Retry-After kept
  auditor-C1b r3 F2/F4  `Verdict.complete` on every documented incomplete step; the 2,999/3,000-character edge; the
        evidence URLs carry no userinfo, path parameter or query
  auditor-C1a r3 F1/F2  the round-3 guards' sub-conditions (its P1-P4: R9, R10, R11, R16) and open access's no-byte
        terminal (the server that answered, never the client's status 0)
  B1 x C2b  the PII B1's Crossref harvest writes reaches Stage C's Elsevier rule through `run.work_record`

No test touches the network (loopback only, inside the suite's socket guard) or the live store.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_w2.py -q
"""
import importlib.util
import json
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


P2M = _load("_litkb_p2_for_w2", SCRIPTS / "qc" / "test_litkb_p2.py")
C1B = _load("_litkb_hardening_c1b_for_w2", INSTR / "litkb_hardening_c1b.py")
HA = _load("_litkb_hardening_a_for_w2", INSTR / "litkb_hardening_a.py")
C2C = _load("_litkb_hardening_c2c_for_w2", INSTR / "litkb_hardening_c2c.py")


@pytest.fixture
def pg(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    h = P2M.P2(psycopg, conn)
    yield h
    while h.opened:
        h.opened.pop().close()


@pytest.fixture
def owner(litkb_pg_base):
    return litkb_pg_base[1]


def _store(tmp_path):
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def _rows(pg, wid):
    return pg.conn.execute("SELECT route, status, sub_status, detail, retriable FROM litkb.acquisition_attempts "
                           "WHERE work_id = %s ORDER BY at, id", (wid,)).fetchall()


def _short_page(title, author):
    """CONSTRUCTED: a one-page PDF (title, author, two body lines: under 3,000 characters, no reference heading —
    the acceptance test's `chars_no_refs` stub), padded past the 5,000-byte floor by a long /Subject."""
    lines = ["Journal of Synthetic Studies 1 (2020) 1-10", title, f"{author} and A. Coauthor", "",
             "Preview: the first page only.", f"id {uuid.uuid4().hex}"]
    return P2M.make_pdf(lines, info={"Subject": "p" * 5000})


def _mojibake_header(pdf):
    """CONSTRUCTED: a whole paper whose %PDF header's version is U+FFFD (a binary file passed through a text
    decode). `store.pdf_shape` passes it (magic + trailer) and pdfium opens it and binds it (measured,
    scratch/integrator-w2/probe_hard.py); THE acceptance test refuses it `corrupt_pdf_header` at the header step —
    a HARD byte failure."""
    return pdf.replace(b"%PDF-1.", b"%PDF-\xef\xbf\xbd", 1)


# ── D15 ───────────────────────────────────────────────────────────────────────────────────────

def test_a_no_byte_answer_declaring_a_length_under_the_floor_is_too_small():
    """S4.5 decision D15 ("length under the floor -> `too_small`"): the floor is the acceptance test's own
    (`accept.MIN_PDF_BYTES`), which builder C1a's branch did not hold. Under it: `too_small`; at or above it the
    answer stays untyped and counted (a server declared a PDF's worth of bytes no rung handed back)."""
    from litkb.acquire import accept as A
    from litkb.acquire import ledger as L

    assert L.no_byte_bad_file_sub({"Content-Length": "1200"})[0] == "too_small"
    assert L.no_byte_bad_file_sub({"content-length": str(A.MIN_PDF_BYTES - 1)})[0] == "too_small"
    assert L.no_byte_bad_file_sub({"Content-Length": str(A.MIN_PDF_BYTES)})[0] is None
    assert L.no_byte_bad_file_sub({"Content-Length": "48213"})[0] is None
    assert L.no_byte_bad_file_sub({"Content-Length": "0"})[0] == "too_small"


def test_an_archive_answer_whose_every_partner_request_failed_in_transport_carries_its_codes():
    """D15 for the archive route (builder-C1a round 3 Q4): every partner request answered status 0 — the client's
    own transport failure, whose BODY is the client's error text (`netutil.Client._raw_get`) — so the answer
    carries `http_codes` all 0 (the ladder then books `api-error`, retriable) and keeps no `rejected` bytes. A
    partner that ANSWERED (403) keeps its page and adds no codes: the route's refusal rules are unchanged."""
    from litkb.acquire import annas

    pdf = b"%PDF-1.4 the record"
    _md5, routes = P2M._annas_routes(pdf, "10.1/transport")
    routes["partner.example"] = (0, {}, b"URLError: <urlopen error CONSTRUCTED transport failure>")
    r = annas.fetch_for_litkb(P2M.RouteStub(routes), "SEKRIT", "10.1/transport", P2M._nopace())
    assert r["status"] == "bad-file" and r["http_codes"] and set(r["http_codes"]) == {0}, r
    assert r["rejected"] is None, "the client's own transport-error text was kept as served bytes"
    page = b"<html><body>CONSTRUCTED partner refusal</body></html>"
    routes["partner.example"] = (403, {}, page)
    r = annas.fetch_for_litkb(P2M.RouteStub(routes), "SEKRIT", "10.1/transport", P2M._nopace())
    assert (r["status"], r["http_codes"], r["rejected"]) == ("bad-file", [], page), r


@pg_only
def test_the_ladder_books_an_all_transport_archive_answer_api_error(pg, tmp_path):
    """The two halves together, through the LADDER: a CONSTRUCTED rung on route `annas` answering exactly what
    `annas.fetch_for_litkb` answers when every partner request fails in transport -> `api-error`, retriable, no
    quarantine, no untyped `bad-file`."""
    from litkb.acquire import annas, run

    C1A = _load("_litkb_hardening_c1a_for_w2", INSTR / "litkb_hardening_c1a.py")
    _md5, routes = P2M._annas_routes(b"%PDF-1.4 the record", "10.1/transport")
    routes["partner.example"] = (0, {}, b"URLError: <urlopen error CONSTRUCTED transport failure>")

    def fn(work, ctx):
        return annas.fetch_for_litkb(P2M.RouteStub(routes), "SEKRIT", "10.1/transport", P2M._nopace())

    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    before = C1A.bad_file_untyped(pg.conn, {})
    run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=("annas",), rungs=[run.Rung("annas", fn)],
                agent="w2", session="w2-1", pacer=P2M._nopace(), printer=lambda *a, **k: None, pacing={})
    got = [(r[1], r[2], r[4]) for r in _rows(pg, work["work_id"]) if r[0] == "annas"]
    assert got == [("api-error", None, True)], got
    assert C1A.bad_file_untyped(pg.conn, {}) == before and not P2M._files_under(store.quarantine)


# ── D17: the hunt URL path ────────────────────────────────────────────────────────────────────

@pytest.fixture
def henv(tmp_path, monkeypatch, litkb_pg_base):
    """A literature root, a worktree with a real workstream, the throwaway database (qc/test_litkb_hunt.py's
    `env`, the same shape)."""
    from litkb import workstream
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws_id = workstream.open_workstream(conn, f"w2-{uuid.uuid4().hex[:8]}", "test", "integrator-w2 tests",
                                       directory=wt)
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt), "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "w2-test", "LITKB_SESSION": f"w2-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    return {"conn": conn, "root": root, "wt": wt, "ws_id": str(ws_id), "db": c.DB_TEST, "tmp": tmp_path}


class _NoRegistry:
    base = ""

    def get(self, url, *a, **kw):
        return 404, {}, b""


def _hunt(henv, ref, **kw):
    from litkb import hunt as H
    from litkb.acquire.store import Store

    return H.hunt(ref, db=henv["db"], worktree=henv["wt"], agent="w2-test", session="w2-test-session",
                  reader_role="litkb_test", writer_role="litkb_test",
                  store=Store(root=henv["root"], index_cache=henv["tmp"] / "index.json"),
                  derived=str(henv["tmp"] / "derived"), registry_client=_NoRegistry(), extract=False, **kw)


@pg_only
def test_a_url_hunt_of_a_first_page_stub_is_refused_by_the_acceptance_test(henv):
    """S4.5 decision D17: the hunt URL path runs THE acceptance test. A CONSTRUCTED first-page stub served as a
    PDF (magic, trailer, past the floor — `pdf_shape` passes it) is refused `stub_not_article` before anything
    reads it as a document: `refused/admission-refused` (the closed REASONS), the bytes kept in _quarantine/ with
    the verdict in the sidecar and a `quarantine_payloads` row, no work admitted. A whole paper still binds."""
    P2M._need_pdftotext()
    from litkb import hunt as H

    title = f"A constructed hunted stub {uuid.uuid4().hex[:8]}"
    stub = _short_page(title, "T. Tester")
    res = _hunt(henv, f"https://example.org/{uuid.uuid4().hex}/paper.pdf",
                fetch=lambda u, timeout=180: (200, stub, "application/pdf"), title=title, author="T. Tester",
                year=2020)
    assert (res["state"], res["reason"]) == ("refused", "admission-refused"), res
    assert H.reason_ok(res["state"], res["reason"]) and res["sub_status"] == "stub_not_article", res
    side = json.loads((henv["root"] / res["quarantine_reason"]).read_text(encoding="utf-8"))
    assert side["acceptance"]["verdict"] == "refuse" and side["sub_status"] == "stub_not_article", side
    assert (henv["root"] / res["quarantined"]).read_bytes() == stub
    got = henv["conn"].execute("SELECT reason, origin FROM litkb.quarantine_payloads WHERE rel_path = %s",
                               (res["quarantined"],)).fetchone()
    assert got == ("bad-file", "hunt-url"), got           # the payload's label, never the hunt's refusal code
    n = henv["conn"].execute("SELECT count(*) FROM litkb.work_versions WHERE title = %s", (title,)).fetchone()[0]
    assert n == 0, "the stub was admitted as a work"
    whole_title = f"A constructed hunted paper {uuid.uuid4().hex[:8]}"
    whole = P2M.paper_pdf(whole_title, "T. Tester")
    ok = _hunt(henv, f"https://example.org/{uuid.uuid4().hex}/paper.pdf",
               fetch=lambda u, timeout=180: (200, whole, "application/pdf"), title=whole_title, author="T. Tester",
               year=2020)
    assert ok["state"] == "bound-unextracted", ok


# ── D17: --from-file ──────────────────────────────────────────────────────────────────────────

def _from_file(pg, w, ws, work, store, path):
    from litkb.acquire import run

    return run.acquire(w, ws, pg.tokens[ws], work, store=store, from_file=path, agent="w2", session="w2-ff",
                       pacer=P2M._nopace(), printer=lambda *a, **k: None)


@pg_only
def test_a_from_file_stub_binds_as_a_proposal_that_carries_the_acceptance_verdict(pg, tmp_path):
    """S4.5 decision D17: `--from-file` RUNS the acceptance test and records its verdict on the PROPOSAL for the
    second-session approver; a stub verdict is the approver's to weigh, never a refusal of the operator's file.
    The CONSTRUCTED stub binds (check 3 passes: its first page is the work's) as a `proposed` file version whose
    `binding.acceptance` says `refuse` / `stub_not_article`, visible in `front.pending_file_proposals`; the
    attempt row carries the verdict too."""
    P2M._need_pdftotext()
    from litkb.admit import front

    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    src = tmp_path / "hand" / "stub.pdf"
    src.parent.mkdir()
    src.write_bytes(_short_page(work["title"], "T. Tester"))
    out = _from_file(pg, w, ws, work, store, src)
    assert out["outcome"] == "ok", out
    (route, status, sub, detail, _r), = [r for r in _rows(pg, work["work_id"]) if r[0] == "browser"]
    assert (status, sub) == ("ok", None) and detail["acceptance"]["sub_status"] == "stub_not_article", detail
    state, acc = pg.one("SELECT fv.state, fv.binding->'acceptance' FROM litkb.file_versions fv "
                        "WHERE fv.work_id = %s", (work["work_id"],))
    assert state == "proposed" and (acc["verdict"], acc["sub_status"]) == ("refuse", "stub_not_article"), acc
    mine = [p for p in front.pending_file_proposals(w) if p["work_id"] == str(work["work_id"])]
    assert [(p["acceptance_verdict"], p["acceptance_sub_status"]) for p in mine] == [("refuse", "stub_not_article")]


@pg_only
def test_a_from_file_hard_byte_failure_is_refused_and_never_bound(pg, tmp_path):
    """D17's one enforced refusal: a HARD byte failure. The CONSTRUCTED paper with a mojibake %PDF header passes
    the old shape check and pdfium binds it (measured) — the acceptance test refuses it `corrupt_pdf_header` at the
    header step, so the operator's file is refused (typed, not bound; a file outside staging stays where it lies)."""
    P2M._need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    src = tmp_path / "hand" / "mojibake.pdf"
    src.parent.mkdir()
    src.write_bytes(_mojibake_header(P2M.paper_pdf(work["title"], "T. Tester")))
    before = src.read_bytes()
    out = _from_file(pg, w, ws, work, store, src)
    assert out["outcome"] == "bad-file", out
    (route, status, sub, detail, _r), = [r for r in _rows(pg, work["work_id"]) if r[0] == "browser"]
    assert (status, sub) == ("bad-file", "corrupt_pdf_header"), (status, sub, detail)
    assert detail["acceptance"]["verdict"] == "refuse", detail
    assert pg.one("SELECT count(*) FROM litkb.file_versions WHERE work_id = %s", (work["work_id"],))[0] == 0
    assert src.read_bytes() == before


# ── D18 ───────────────────────────────────────────────────────────────────────────────────────

def test_measure_decision_refuses_every_tier_but_the_legitimate():
    from litkb.acquire import policy as P

    shadow = P.decide("annas", "annas-archive.gl")
    assert shadow.allowed and shadow.tier == P.SHADOW
    m = P.measure_decision(shadow)
    assert (m.allowed, m.reason, m.line) == (False, P.MEASURE_REFUSAL, shadow.line), m
    legit = P.decide("open_access", "api.unpaywall.org")
    assert P.measure_decision(legit) is legit and legit.allowed
    refused = P.decide("scihub", "sci-hub.ru", legit_hit=True)
    assert P.measure_decision(refused) is refused


@pg_only
def test_measure_mode_never_asks_the_archive_or_the_shadow_stage(pg, tmp_path):
    """S4.5 decision D18: MEASURE mode (a work that already holds a file) asks the LEGITIMATE tiers only. With a
    CONSTRUCTED registry of a legitimate rung that misses and two shadow rungs (`annas`, `scihub`) that record
    every call: in acquire mode both shadow rungs are asked; in MEASURE mode neither is — each is a recorded
    `skipped/policy_refused` row naming D18, and no archive download is spent."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    asked = []

    def rung(route, status):
        def fn(work, ctx):
            asked.append(route)
            return {"status": status, "http_codes": [404]}
        return run.Rung(route, fn, needs=("doi",), concurrent=route == "open_access")

    rungs = [rung("open_access", "no-oa-copy"), rung("annas", "not-in-archive"), rung("scihub", "not-in-archive")]
    ws, w = pg.ws(), pg.session("litkb_writer")
    for mode in ("acquire", "measure"):
        asked.clear()
        work = P2M._admitted(pg, w, ws)
        run.acquire(w, ws, pg.tokens[ws], work, store=_store(tmp_path / mode), routes=("open_access", "annas",
                    "scihub"), rungs=rungs, mode=mode, agent="w2", session="w2-1", pacer=P2M._nopace(),
                    printer=lambda *a, **k: None, pacing={}, retry_dead=True)
        got = {r[0]: (r[1], r[2], (r[3].get("policy") or {}).get("reason") if isinstance(r[3].get("policy"), dict)
                      else None) for r in _rows(pg, work["work_id"])}
        if mode == "acquire":
            assert asked == ["open_access", "annas", "scihub"], asked
        else:
            assert asked == ["open_access"], asked
            for route in ("annas", "scihub"):
                assert got[route] == ("skipped", "policy_refused", P.MEASURE_REFUSAL), got


# ── D19 ───────────────────────────────────────────────────────────────────────────────────────

def test_a_metadata_only_rung_is_measured_by_an_identifiers_line_and_a_pdf_rung_is_not(tmp_path):
    """S4.5 decision D19: `identifiers: <route>=<works gaining>/<asked>` measures a Stage B rung the registry marks
    metadata-only (a rung object carrying `metadata_only`: builder C2a's `run.Rung` field, CONSTRUCTED here); for a
    PDF rung it answers nothing, and it follows the yield line's rules (`=0/0` asked nobody)."""
    from litkb.acquire import policy as P

    rungs = [types.SimpleNamespace(route="opencitations", metadata_only=True),
             types.SimpleNamespace(route="ncbi-idconv", metadata_only=True),
             types.SimpleNamespace(route="osf", metadata_only=False),
             types.SimpleNamespace(route="hal")]
    built, unbuilt = HA.stage_b_rungs(rungs)
    assert HA.metadata_only_routes(rungs) == {"opencitations", "ncbi-idconv"}
    lines = ["identifiers: opencitations=3/35", "identifiers: ncbi-idconv=0/0", "identifiers: osf=1/2",
             "yield: hal=0/35"] + [f"not-built: {r} CONSTRUCTED: no key" for r in unbuilt]
    p = tmp_path / "LITKB_LADDER1_CONSTRUCTED.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert HA.stage_b_unmeasured_detail({"repo": str(tmp_path), "report_path": str(p)}, rungs) == [
        "ncbi-idconv", "osf"]
    assert set(built) == {"opencitations", "ncbi-idconv", "osf", "hal"} and P.STAGE_OF["opencitations"] == "B"


def test_hunt_and_the_measure_hook_reach_every_registered_rung(monkeypatch):
    """D19's "a rung that registers by import but is never imported is invisible to `hunt`" has a second half: a
    rung the registry holds must also be ASKED. `hunt`'s default acquirer and the run driver's MEASURE hook pass
    the WHOLE ladder (`run.ladder_routes`: every registered rung, stage order), never today's three alone."""
    from litkb import hunt as H
    from litkb.acquire import policy as P
    from litkb.acquire import run

    everything = run.ladder_routes()
    assert set(everything) == {r.route for r in run.RUNGS}
    assert {"landing", "wayback", "ia", "commoncrawl"} <= set(everything), everything
    order = [P.STAGES.index(P.STAGE_OF[r]) for r in everything]
    assert order == sorted(order), everything
    seen = {}
    monkeypatch.setattr(run, "acquire", lambda *a, **kw: seen.update(kw) or {"outcome": "not-acquired"})
    H._default_acquire(None, "ws", "tok", {"work_id": "w"}, store=None, agent="a", session="s")
    assert tuple(seen["routes"]) == everything, seen
    seen.clear()
    run.measure(None, "ws", "tok", {"work_id": "w"}, store=None, agent="a", session="s")
    assert tuple(seen["routes"]) == everything and seen["mode"] == "measure", seen


# ── D20 ───────────────────────────────────────────────────────────────────────────────────────

def test_the_replays_pinned_mirror_widening_never_reaches_a_live_policy_decision(monkeypatch):
    """S4.5 decision D20 (integrator-w1 Q6): the replay names each PINNED recorded mirror to the pre-fetch policy
    for that replay only. A host it does not pin is still refused inside the replay; after the replay the one
    module POLICY is the object it was and the pinned host is refused again; and no pipeline module holds the
    widening (it lives in the replay instrument alone)."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    E = _load("_litkb_edge_run_for_w2", INSTR / "litkb_edge_run.py")
    pinned, unpinned = "https://pinned.constructed.invalid", "unpinned.constructed.invalid"
    widened = E._pinned_mirror_policy((pinned,))
    assert P.decide("scihub", "pinned.constructed.invalid", policy=widened).allowed
    assert not P.decide("scihub", unpinned, policy=widened).allowed
    assert [line for line in widened if line not in P.POLICY] == [
        line for line in widened if line.host == "pinned.constructed.invalid"]
    live_before = P.POLICY
    seen = {}

    def fake_acquire(*a, **kw):
        seen["inside"] = (P.decide("scihub", "pinned.constructed.invalid").allowed, P.decide("scihub", unpinned).allowed)
        return {"outcome": "not-acquired", "attempts": [], "route_detail": []}

    monkeypatch.setattr(R, "acquire", fake_acquire)
    acq = E._ladder_acquirer({"routes": ["scihub"], "mirrors": [pinned]})
    acq(None, "ws", "tok", {"work_id": "w"}, store=None, agent="a", session="s")
    assert seen["inside"] == (True, False), seen
    assert P.POLICY is live_before
    assert not P.decide("scihub", "pinned.constructed.invalid").allowed
    for py in (SCRIPTS / "pipeline" / "litkb").rglob("*.py"):
        assert "_pinned_mirror_policy" not in py.read_text(encoding="utf-8"), py


# ── D22 (and D21's ladder-level fires) ────────────────────────────────────────────────────────

@pg_only
def test_every_attempt_that_was_served_bytes_records_the_stub_headers_itself(pg, tmp_path):
    """S4.5 decision D22: the ladder records Content-Type, Content-Length, X-ELS-Status and Content-Disposition on
    EVERY attempt that was served bytes — a landing, a refusal, a MEASURE hit — in `detail.served_headers`, written
    by the ladder, not by the acceptance test (so a landing the test did not judge still leaves them)."""
    P2M._need_pdftotext()
    from litkb.acquire import run

    headers = {"Content-Type": "application/pdf", "Content-Length": "12345", "X-ELS-Status": "OK",
               "Content-Disposition": "inline; filename=paper.pdf", "Server": "not kept"}
    want = {"content-type": "application/pdf", "content-length": "12345", "x-els-status": "OK",
            "content-disposition": "inline; filename=paper.pdf"}
    ws, w = pg.ws(), pg.session("litkb_writer")
    for mode, body_of in (("acquire", lambda wk: P2M.paper_pdf(wk["title"], "T. Tester")),
                          ("acquire", lambda wk: P2M.salted_html()),
                          ("measure", lambda wk: P2M.paper_pdf(wk["title"], "T. Tester"))):
        work, store = P2M._admitted(pg, w, ws), _store(tmp_path / uuid.uuid4().hex[:6])
        body = body_of(work)

        def fn(wk, ctx, body=body):
            return {"status": "downloaded", "pdf": body, "source_url": "https://oa.example/p.pdf",
                    "http_codes": [200], "terminal": {"url": "https://oa.example/p.pdf", "status_code": 200,
                                                      "headers": headers}}
        run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=("open_access",),
                    rungs=[run.Rung("open_access", fn, needs=("doi",))], mode=mode, agent="w2", session="w2-1",
                    pacer=P2M._nopace(), printer=lambda *a, **k: None, pacing={})
        (row,) = [r for r in _rows(pg, work["work_id"]) if r[0] == "open_access"]
        assert row[3]["served_headers"] == want, (mode, row[1], row[3].get("served_headers"))


@pg_only
@pytest.mark.parametrize("headers", [{"X-ELS-Status": "WARNING - CONSTRUCTED first page only"},
                                     {"Content-Disposition": "attachment; filename=CONSTRUCTED-preview.pdf"}])
def test_a_header_only_stub_bound_unjudged_is_counted_on_disk_and_off_it(owner, tmp_path, headers):
    """auditor-C1b round 3 F3 (its Z1, Z2, Z6 survived), now through D22's record: a WHOLE article announced as a
    stub only by a header (X-ELS-Status, or a preview named in Content-Disposition), bound through the ladder with
    the acceptance test switched off. `stubs_bound` counts it from the ladder's own `served_headers` — with the
    file on disk (its bytes carry no stub signal) AND after it is moved off disk, when `bound_files_unreadable`
    reports it and only the recorded headers are left to ask."""
    from litkb.acquire import accept as A
    from litkb.acquire import run
    from litkb.netutil import Pacer

    N = C1B._negatives()
    ws, token, frozen, work, store = C1B._setup(owner, tmp_path, "known_bad", title=N.BOM_TITLE, family="Constructor")
    data = C1B._salted((C1B.NEG_DIR / "CONSTRUCTED_bom_valid_article.pdf").read_bytes()[len(N.BOM):], "w2-f3")
    rungs = C1B._served_by_a_constructed_rung(data, {"Content-Type": "application/pdf", **headers},
                                              "https://constructed.example/ladder/article.pdf")
    with C1B._swap(A, "offer_to_bind", None):
        run.acquire(owner, ws, token, work, store=store, routes=("open_access",), rungs=rungs, agent="w2",
                    session="w2-f3", pacer=Pacer(interval=0), printer=lambda *a, **k: None, pacing={})
    m = C1B._manifest(ws, frozen, store)
    assert (C1B.stubs_bound(owner, m), C1B.bound_files_unreadable(owner, m)) == (1, 0)
    filed = [p for p in store.filed.rglob("*.pdf")]
    assert len(filed) == 1, filed
    filed[0].rename(tmp_path / f"moved-{filed[0].name}")
    assert (C1B.stubs_bound(owner, m), C1B.bound_files_unreadable(owner, m)) == (1, 1)


@pg_only
@pytest.mark.parametrize("fire", ["stub_ladder", "stub_ladder_header_only"])
def test_the_ladder_level_stub_fires_read_zero_then_one(owner, tmp_path, fire):
    """S4.5 decision D21: the ladder-level stub fire is a FIRES entry of builder C1b's module, through `run.acquire`
    with a CONSTRUCTED rung. `stub_ladder_header_only` (a whole article, stub announced only in X-ELS-Status) can
    fire only through D22's `served_headers`: its known-bad binds bytes that carry no stub signal of their own."""
    f = C1B.FIRES[fire]
    assert f["run"](owner, "control", tmp_path) == 0
    assert f["run"](owner, "known_bad", tmp_path) == 1


# ── auditor-C2c round 3 F1: Stage E3 / E5 transient stops (Codex X7, Retry-After) ─────────────

BUSY = (503, {"Retry-After": "40"}, b"busy")


def _j(obj):
    return (200, {"Content-Type": "application/json"}, json.dumps(obj).encode())


def _ia_hit():
    return [{"identifier": "constructed-item", "title": "x", "external-identifier": [f"urn:doi:{C2C.CENSUS_DOI}"]}]


def _assert_transient_stop(r, stub, calls):
    from litkb.acquire import backoff

    assert (r["status"], r["retriable"]) == ("api-error", True), r
    assert r["http_codes"][-1] == 503, r
    assert len(stub.calls) == calls, ("the rung went on asking after a 503", stub.calls)
    assert backoff.retry_after_s(r["terminal"]["headers"]) == 40.0
    assert backoff.classify(r["status"], r["http_codes"]) == "transient"


def test_an_ia_search_503_stops_the_rung_and_keeps_its_retry_after():
    from litkb.acquire import ia

    stub = C2C.StubClient({ia.SEARCH: BUSY})
    _assert_transient_stop(ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub), stub, 1)


def test_an_ia_download_503_stops_the_rung_and_keeps_its_retry_after():
    """Without the stop the 503 was walked past and booked `not-in-archive/not_in_corpus`, not retriable: a
    transient answer recorded as a permanent absence (auditor-C2c r3 A12)."""
    from litkb.acquire import ia

    stub = C2C.StubClient({ia.SEARCH: _j({"response": {"numFound": 1, "docs": _ia_hit()}}),
                           "/metadata/constructed-item": _j({"metadata": {"collection": ["texts"]},
                                                             "files": [{"name": "x.pdf", "source": "original"},
                                                                       {"name": "y.pdf", "source": "original"}]}),
                           "/download/constructed-item/": BUSY})
    _assert_transient_stop(ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub), stub, 3)


def test_a_commoncrawl_index_503_stops_the_rung_and_keeps_its_retry_after():
    """Without the stop a crawl index's 503 read as "no capture in this crawl" and the row ended
    `not-in-archive/not_in_corpus`, not retriable (auditor-C2c r3 A13)."""
    from litkb.acquire import commoncrawl

    stub = C2C.StubClient({"collinfo.json": _j([{"id": "CC-A", "cdx-api": "https://index.commoncrawl.org/CC-A-index"},
                                                {"id": "CC-B", "cdx-api": "https://index.commoncrawl.org/CC-B-index"}]),
                           "CC-A-index": BUSY, "CC-B-index": (404, {}, b"No Captures found")})
    _assert_transient_stop(commoncrawl.fetch_commoncrawl(["https://dead.example/r.pdf"], stub, indexes_asked=2),
                           stub, 2)


def test_a_commoncrawl_range_503_stops_the_rung_and_keeps_its_retry_after():
    from litkb.acquire import commoncrawl

    rec = {"url": C2C.CENSUS_URL, "mime": "application/pdf", "status": "200",
           "filename": "crawl-data/CONSTRUCTED/x.warc.gz", "offset": "1000", "length": "900",
           "timestamp": "20200101000000"}
    stub = C2C.StubClient({"collinfo.json": _j([{"id": "CC-A", "cdx-api": "https://index.commoncrawl.org/CC-A-index"}]),
                           "CC-A-index": (200, {}, json.dumps(rec).encode() + b"\n"),
                           "data.commoncrawl.org/": BUSY})
    _assert_transient_stop(commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], stub, indexes_asked=1), stub, 3)


# ── auditor-C1b round 3 F2 / F4 ───────────────────────────────────────────────────────────────

def test_every_documented_incomplete_step_makes_the_verdict_incomplete():
    """auditor-C1b r3 F2 (its Z3, Z4 survived): `Verdict.complete` is false on `qpdf-unavailable`, `unreadable`,
    `encrypted` and any `qpdf-error:*` — each held ALONE, on a verdict whose other steps passed."""
    from litkb.acquire import accept as A

    ok = [("text", "pass"), ("stub", "pass")]
    for step in (("qpdf", "qpdf-unavailable"), ("text", "unreadable"), ("qpdf", "encrypted"), ("qpdf", "qpdf-error:7")):
        assert A.Verdict(steps=[step, *ok]).complete is False, step
    assert A.Verdict(steps=[("qpdf", "clean"), *ok]).complete is True


def test_the_stub_rule_holds_its_edge_at_three_thousand_characters():
    """auditor-C1b r3 F2 (its Z8 survived): the plan says "fewer than 3,000 characters" — 2,999 is a stub, 3,000
    is not (no reference heading, no image page either way)."""
    from litkb.acquire import accept as A

    assert A.STUB_MAX_CHARS == 3000
    assert A.stub_signals(["x" * 2999]) == ["chars_no_refs"]
    assert A.stub_signals(["x" * 3000]) == []


def test_the_recorded_evidence_urls_carry_no_userinfo_path_parameter_or_query():
    """auditor-C1b r3 F4: a planted secret survived `evidence_of` as userinfo, as a `;param` and as the REQUESTED
    URL's query. Both URLs are reduced to scheme, host, port and path; the path the preview rule reads is kept."""
    from litkb.acquire import accept as A

    ev = A.evidence_of({}, "https://h.example/a/preview.pdf?sig=PLANTED#x",
                       "https://user:PLANTED@h.example:8443/o/preview.pdf;jsessionid=PLANTED?token=PLANTED")
    assert "PLANTED" not in json.dumps(ev), ev
    assert ev["url"] == "https://h.example/a/preview.pdf" and ev["terminal_url"] == "https://h.example:8443/o/preview.pdf"
    assert A.evidence_signals(urls=(ev["url"], ev["terminal_url"])) == ["preview_url"]


# ── B1 x C2b: the harvested PII reaches Stage C (seam; brief-INTEGRATE-w2 item 3) ──────────────

@pg_only
def test_b1s_crossref_pii_reaches_stage_cs_elsevier_rule_through_the_work_record(pg):
    """The seam builder B1 and builder C2b meet at: B1's Crossref parser reads Elsevier's PII from `alternative-id`
    (`harvest.from_crossref`), `harvest.record` writes it with its provenance, `run.work_record` hands it to the
    rung as `work["pii"]`, and Stage C's Elsevier rule builds its `/pdfft` URL from `work:pii` — on a page that
    names no PII at all (CONSTRUCTED record, CONSTRUCTED page; the PII is the survey's measured example)."""
    from litkb.acquire import landing as Lm
    from litkb.acquire import run
    from litkb.admit import harvest as H

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    rows, rels, _rej = H.from_crossref({"member": "78", "alternative-id": ["S0034425721005265"]}, work["doi"])
    assert [(r["scheme"], r["value"]) for r in rows] == [("pii", "S0034425721005265")], rows
    H.record(w, ws, pg.tokens[ws], work["work_id"], rows, rels, agent="w2", session="w2-pii")
    rec = run.work_record(w, work_id=work["work_id"])
    assert rec["pii"] == "S0034425721005265", rec
    page_url = "https://www.sciencedirect.com/journal/constructed-no-pii"
    page = Lm.Page(page_url, 200, {}, b"<html><head><title>CONSTRUCTED</title></head><body></body></html>",
                   "doi", "landing")
    rules = [r for r in Lm.TABLE["rules"] if r["id"] == "elsevier"] + [Lm.TABLE["default"]]
    cands, _ = Lm.candidates_for(rec, [page], [page_url], resolved=page_url, rules=rules)
    want = "https://www.sciencedirect.com/science/article/pii/S0034425721005265/pdfft?isDTMRedir=true&download=true"
    assert want in [c.url for c in cands], [c.url for c in cands]


# ── auditor-C1a round 3 F1: the round-3 guards' sub-conditions (its P1-P4, ported) ─────────────

L = _load("_litkb_ledger_for_w2", SCRIPTS / "qc" / "test_litkb_ledger.py")


def _now_iso():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@pg_only
def test_a_version_withdrawn_for_this_work_keeps_the_bytes_known_bad(pg, tmp_path, monkeypatch):
    """auditor-C1a r3 P1 (its R9): W1 holds paper X; a second version of X's file, for W2, is WITHDRAWN (the shape
    B2's withdraw_version / refuse verb writes). Served X in ACQUIRE mode, W2 gets `known-bad` (reason
    `withdrawn`), never `duplicate-held`: the VERSION half of `ledger._HELD_SQL`'s per-work refusal."""
    from litkb.acquire import ledger as LG
    from litkb.acquire import open_access

    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "w2-test@example.invalid")
    w, ws, w1, store, pdf, sha, clients, _refuse = L._held_world(pg, tmp_path)
    w2 = P2M._admitted(pg, w, ws)
    cur = pg.conn.execute("SELECT f.id, f.current_version_id FROM litkb.files f WHERE f.sha256 = %s",
                          (sha,)).fetchone()
    pg.conn.execute(
        "INSERT INTO litkb.file_versions (file_id, version_no, work_id, rel_path, status, state, workstream_id, agent, "
        " session_id, based_on_version_id, change_reason) "
        "SELECT file_id, version_no + 1, %s, rel_path || '.w2', 'superseded', 'withdrawn', workstream_id, agent, "
        "       session_id, version_id, 'CONSTRUCTED withdrawn version for W2' "
        "  FROM litkb.file_versions WHERE version_id = %s", (w2["work_id"], cur[1]))
    assert LG.held_file(pg.conn, sha, w1["work_id"]) and not LG.held_file(pg.conn, sha, w2["work_id"])
    L._acq(pg, w, pg.ws(), w2, store, clients(), routes=("open_access",))
    got = [(r[2], (r[12].get("known_bad") or {}).get("reason")) for r in L._rows(pg, w2["work_id"])
           if r[1] == "open_access"]
    assert got == [("known-bad", "withdrawn")], got


def _busy(route, retry_after=None):
    def fn(work, ctx):
        return {"status": "api-error", "http_codes": [503], "tried": [f"{route}.example:503"],
                "terminal": {"url": f"https://{route}.example/x", "status_code": 503, "at": _now_iso(),
                             **({"headers": {"Retry-After": retry_after}} if retry_after else {})}}
    return fn


def _two_lines(monkeypatch):
    from litkb.acquire import policy as P

    monkeypatch.setattr(P, "POLICY", P.POLICY + (P.PolicyLine("osf", "*", "legitimate", "CONSTRUCTED test line"),
                                                 P.PolicyLine("zenodo", "*", "legitimate", "CONSTRUCTED test line")))


@pg_only
def test_a_concurrent_retry_is_not_suppressed_by_a_sibling_that_spent_nothing(pg, tmp_path, monkeypatch):
    """auditor-C1a r3 P2 (its R10): two concurrent rungs under attempts=2; `osf` answers a transient 503, `zenodo`
    refuses ITSELF on policy (`skipped`, spends nothing). osf's scheduled retry must go out (1 spent + 0 pending < 2):
    the pending count counts only siblings that SPENT."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    _two_lines(monkeypatch)

    def refuses(work, ctx):
        return {"status": "skipped", "sub_status": "policy_refused", "policy": [{"route": "zenodo", "allowed": False}]}

    rungs = [run.Rung("osf", _busy("osf"), concurrent=True, retry_transient=True),
             run.Rung("zenodo", refuses, concurrent=True, retry_transient=True)]
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    L._acq(pg, w, ws, work, L._store(tmp_path), {}, routes=("osf", "zenodo"), rungs=rungs,
           ladder_budget=P.LadderBudget(attempts=2))
    rows = [(r[1], r[2], r[11] is not None) for r in L._rows(pg, work["work_id"]) if r[1] == "osf"]
    assert ("osf", "api-error", True) in rows, rows       # the scheduled retry went out


@pg_only
def test_a_retry_the_budget_refuses_is_never_waited_for(pg, tmp_path, monkeypatch):
    """auditor-C1a r3 P3 (its R11): two concurrent transient rungs under attempts=2 with a RECORDING pacer: no retry
    goes out, and none is WAITED for — the budget check before the wait already counts the pending sibling."""
    from litkb.acquire import policy as P
    from litkb.acquire import run
    from litkb.netutil import Pacer

    _two_lines(monkeypatch)
    slept = []
    rungs = [run.Rung("osf", _busy("osf", "120"), concurrent=True, retry_transient=True),
             run.Rung("zenodo", _busy("zenodo", "120"), concurrent=True, retry_transient=True)]
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    run.acquire(w, ws, pg.tokens[ws], work, store=L._store(tmp_path), agent="w2", session="w2-1", clients={},
                pacer=Pacer(interval=0, sleep=lambda s: slept.append(s)), printer=lambda *a, **k: None,
                routes=("osf", "zenodo"), rungs=rungs, pacing={}, ladder_budget=P.LadderBudget(attempts=2))
    rows = [(r[1], r[2], r[11] is not None) for r in L._rows(pg, work["work_id"]) if r[1] in ("osf", "zenodo")]
    assert not any(r[2] for r in rows) and not [s for s in slept if s and s > 0], (rows, slept)


@pg_only
def test_a_codeless_no_byte_bad_file_is_typed_never_rebooked_api_error(pg, tmp_path, monkeypatch):
    """auditor-C1a r3 P4 (its R16): a rung that books `bad-file`, hands back no byte and records NO http code. D15's
    all-transport rule needs every REQUEST to be status 0; with none recorded it must not fire (a vacuous all()):
    the row stays `bad-file`, typed `too_small`, not retriable."""
    from litkb.acquire import policy as P
    from litkb.acquire import run

    monkeypatch.setattr(P, "POLICY", P.POLICY + (P.PolicyLine("osf", "*", "legitimate", "CONSTRUCTED test line"),))

    def fn(work, ctx):
        return {"status": "bad-file", "http_codes": [], "tried": ["osf.example:?"]}

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    L._acq(pg, w, ws, work, L._store(tmp_path), {}, routes=("osf",), rungs=[run.Rung("osf", fn, concurrent=True)])
    rows = [(r[2], r[3], r[9]) for r in L._rows(pg, work["work_id"]) if r[1] == "osf"]
    assert rows == [("bad-file", "too_small", False)], rows


@pg_only
def test_a_no_byte_open_access_answer_types_from_the_server_that_answered(pg, tmp_path, monkeypatch):
    """auditor-C1a r3 F2 (D15: "the route types from the terminal RESPONSE"; a transport failure is not a response):
    an EMPTY 404 served as text/html, then a transport failure. The row types from the server that answered —
    `html_response` — not from the client's own status 0; its codes and `retriable` are the codes' (the last request
    failed in transport: retried once)."""
    from litkb.acquire import open_access

    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "w2-test@example.invalid")
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    stub = {"open_access": P2M.RouteStub({
        "api.unpaywall.org": L._unpaywall("https://a.example/p.pdf", "https://b.example/p.pdf"),
        "a.example": (404, {"Content-Type": "text/html; charset=utf-8"}, b""),
        "b.example": (0, {}, b"URLError: <urlopen error CONSTRUCTED timed out>")})}
    L._acq(pg, w, ws, work, L._store(tmp_path), stub, routes=("open_access",))
    rows = [(r[2], r[3], r[9], r[7], r[13]) for r in L._rows(pg, work["work_id"]) if r[1] == "open_access"]
    assert rows and rows[0] == ("bad-file", "html_response", True, 404, [404, 0]), rows


# ── A x C2b: a counter reads the manifest's repo-relative paths against the manifest's repo ───────

def test_c2bs_bronze_rows_are_read_from_the_manifests_repo_relative_probe_csv(tmp_path, monkeypatch):
    """The freeze trial on the merged candidate (integrator-w2) read C2b's REPORTED `bronze_landing_unconverted`
    `unread`: the freeze writes `probe_csvs` REPO-RELATIVE (A's manifest shape) and the counter opened that path
    from the grader's working directory. From any directory, the manifest's `repo` is what it resolves against."""
    C2B = _load("_litkb_hardening_c2b_for_w2", INSTR / "litkb_hardening_c2b.py")
    monkeypatch.chdir(tmp_path)
    m = {"repo": str(SCRIPTS.parent), "probe_csvs": {C2B.NO_OA_COPY_CSV: f"phase4/qc/{C2B.NO_OA_COPY_CSV}"}}
    assert tuple(C2B.bronze_dois(m)) == tuple(C2B.bronze_dois())

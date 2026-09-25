"""litkb S4.5 fix wave FX-E — Stage E on the rows referee-stage-e and referee-vocabulary REJECTED (brief-FIXWAVE.md
"FX-E"; Reports/LITKB_REFEREE_S45_STAGE-E_2026-09-24.md; S4.5 decisions D48, D49):

  1. a dead location a rung recorded only as a `host:code` token reaches E1 in full (L007's IIASA 404 that OpenAlex
     named; L054's handle 404 that Unpaywall named) — `litkb.acquire.recovery.asked_urls`, read from the ladder's
     request gate (`litkb.acquire.backoff.Gate.after`'s `asked_url`);
  2. a metadata API's URL is never sent to the Wayback Machine (`recovery.is_api`: `api2.` hosts, a first path
     segment `api`) — the 292 URLs E1/E5 were asked about in hardening-1 — while a document served under an
     API-shaped path stays a candidate (`recovery.API_DOCUMENT_PATHS`: InvenioRDM's file content; auditor-FX-E F1,
     the recorded Zenodo answer of L006 and the Rogue Scholar PDF L063 landed, invenio.jsonl);
  3. a recovered PDF of ANOTHER work is neither landed nor `measured` (`recovery.capture_identity` /
     `checked_capture`): L022's census.gov capture for 10.1002/wics.1317;
  4. an Internet Archive query error is `api-error`, never `not_in_corpus` (`ia.search_error`), and a first author
     carrying a Lucene grouping character no longer breaks the query (`ia.GROUP_CHARS`) — L007.

Inputs, each named for what it is:
  REAL       hardening-1's recorded answers, copied from the ladder-1 cassette into
             qc/fixtures/litkb_cassettes/stage_e_fx/ (provenance.json there: row, index entry, key sha256, body sha256;
             the two large stored bodies kept as their first 4096 bytes, named so) and builder-C2c's tracked Stage E
             recording (qc/fixtures/litkb_cassettes/stage_e/: the census.gov capture; the IIASA capture whose body is
             not kept, so a replay of it fails CLOSED).
  CONSTRUCTED  stub answers no host was asked for, and gate records written by hand — each says so.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_fx_stage_e.py -q
"""
import base64
import hashlib
import importlib.util
import json
import time
import urllib.parse
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
INSTR = SCRIPTS / "qc" / "instruments"
FIX = SCRIPTS / "qc" / "fixtures" / "litkb_cassettes" / "stage_e_fx"
pg_only = pytest.mark.requires_litkb_pg


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C2C = _load("_litkb_hardening_c2c_for_fx_e", INSTR / "litkb_hardening_c2c.py")
PROV = json.loads((FIX / "provenance.json").read_text(encoding="utf-8"))
#: the work records the rungs read (litkb.acquire.run.work_record on live, recorded in provenance.json)
WORKS = PROV["works"]
V1 = "https://pure.iiasa.ac.at/id/eprint/20873/1/CEOS_WGCV_LPV_Land_Cover_protocol_Sept2025_V1.pdf"
V1_0 = "https://pure.iiasa.ac.at/id/eprint/20873/1/CEOS_WGCV_LPV_Land_Cover_protocol_Sept2025_V1.0.pdf"
HANDLE = "http://hdl.handle.net/10810/59883"
#: the ScienceDirect accepted-manuscript page Unpaywall named first for L054, as asked — WITH its query
SD_PAGE = "https://www.sciencedirect.com/science/article/am/pii/S0034425719305115?via%3Dihub"
#: CONSTRUCTED: the contact email the Stage B / Unpaywall URLs carry here (its value is scrubbed to `<KEY>` in every
#: recorded key, so any address matches the recording)
TEST_EMAIL = "fx-e-test@example.invalid"


def _sha(b):
    return hashlib.sha256(b or b"").hexdigest()


def _entries():
    """The fixture's recorded interactions, each with its body resolved and CHECKED against provenance."""
    prov = {(p["key_sha256"], p["index_entry"]): p for p in PROV["entries"]}
    by_key = {p["key_sha256"]: p for p in PROV["entries"]}
    out = []
    for ln in (FIX / "index.jsonl").read_bytes().splitlines()[1:]:
        e = json.loads(ln)
        p = by_key[e["key_sha256"]]
        b = e["response"]["body"]
        if "inline_b64" in b:
            body = base64.b64decode(b["inline_b64"])
            assert _sha(body) == b["sha256"] == p["body_sha256"], p
        else:
            body = (FIX / p["body"]).read_bytes()
            assert len(body) == p["truncated_to"] and _sha(body) == p["head_sha256"], p
        out.append({"row": p["manifest_row"], "url": e["key"]["url"], "accept": e["key"]["accept"],
                    "status": e["response"]["status"], "headers": dict(e["response"]["headers"]), "body": body,
                    "prov": p})
    assert len(out) == len(prov) == len(PROV["entries"])
    return out


class Recorded:
    """Answers a request from hardening-1's recorded entry whose key URL is the request's URL as the recorder
    scrubbed it (`litkb.cassette.scrub_url`); a request no entry recorded goes to `fallback`, else it FAILS the
    test — never the network."""
    base = ""

    def __init__(self, rows, fallback=None):
        self.by = {e["url"]: e for e in _entries() if e["row"] in rows}
        self.fallback, self.calls = fallback, []

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        from litkb.cassette import scrub_url

        e = self.by.get(scrub_url(url))
        if e is None:
            if self.fallback is None:
                raise AssertionError(f"not a recorded request: {url}")
            return self.fallback.get(url, accept=accept, timeout=timeout, follow=follow, data=data, headers=headers)
        self.calls.append(url)
        return e["status"], dict(e["headers"]), e["body"]


def _ctx(clients, mode="acquire", recovery_urls=()):
    from litkb.acquire.run import Budget, RungContext, _gated
    from litkb.netutil import Pacer

    return RungContext(clients=_gated(clients), pacer=Pacer(interval=0, sleep=lambda s: None), budget=Budget(),
                       index={}, printer=lambda *a, **k: None, mode=mode, recovery_urls=list(recovery_urls))


def _call(route, work, ctx):
    """The ladder's own call of one registered rung (`run._call_rung`) under a request gate, as `run.acquire` makes
    it: -> the route dict (with its `cooldown_gate` record)."""
    from litkb.acquire import backoff, run

    rung = next(r for r in run.RUNGS if r.route == route)
    gate = backoff.Gate(route, backoff.HostCooldowns(), time.monotonic)
    r, exc = run._call_rung(rung, dict(work), ctx, gate)
    assert exc is None, exc
    return r


@pytest.fixture
def email(monkeypatch):
    from litkb.acquire import open_access

    monkeypatch.setattr(open_access, "unpaywall_email", lambda: TEST_EMAIL)
    return TEST_EMAIL


# ── the fixture itself ──────────────────────────────────────────────────────────────────────

def test_the_fixture_is_hardening_1s_recording():
    """Every copied line is a ladder-1 index line (row tag = the manifest row's ref) whose body is the recorded one."""
    got = _entries()
    assert {e["row"] for e in got} == {"L007", "L054"}
    assert PROV["source_index"].endswith("_derived/hardening/cassettes/ladder-1/index.jsonl")
    head = json.loads((FIX / "index.jsonl").read_bytes().splitlines()[0])
    assert head["kind"] == "litkb-cassette"
    xip = [v for ln in (FIX / "index.jsonl").read_bytes().splitlines()[1:]
           for k, v in json.loads(ln)["response"]["headers"].items() if k.lower() == "x-ip"]
    assert xip == ["<CLIENT-IP>"], "archive.org's X-IP echo of the client's own address is masked"
    urls = {e["url"] for e in got}
    assert V1 in urls and V1_0 in urls and HANDLE in urls


# ── item 1: every dead location a rung asked reaches E1 in full ────────────────────────────

def test_l007_the_dead_iiasa_location_openalex_recorded_as_a_host_token_reaches_stage_e(email):
    """REAL (L007): OpenAlex's recorded answer names V1 then V1.0; V1 answered 404, V1.0 served the PDF (its first
    4 KiB here). The rung's own dict names V1 only as `pure.iiasa.ac.at:404` — which is all the ledger kept — so on
    411c3ce V1 never reached E1 (referee-stage-e N1). The request gate saw every request in full."""
    from litkb.acquire import recovery

    client = Recorded({"L007"})
    r = _call("openalex", WORKS["L007"], _ctx({"openalex": client}))
    assert r["status"] == "downloaded" and r["source_url"] == V1_0, r.get("tried")
    assert r["tried"] == ["pure.iiasa.ac.at:404", "pure.iiasa.ac.at:200=ok"], "the host tokens the ledger kept"
    assert V1 not in json.dumps({k: v for k, v in r.items() if k not in ("pdf", "cooldown_gate")}, default=str), \
        "the rung's own fields never name V1"
    found = [e["url"] for e in recovery.urls_of("openalex", r, "binding-failed")]
    assert V1 in found, found
    urls, refused = recovery.candidates([{"url": u} for u in found])
    # S4.5 decision D60 (integrator-w4 r2): V1.0 — the rung's own `source_url`, which answered 200 with the PDF the
    # binder then refused — is a location the rung observed answering 2xx: live, not a recovery candidate (before D60
    # it was handed first, and E1 proved it absent from the archive)
    assert V1_0 not in found, found
    assert urls == [V1], (urls, refused)
    # S4.5 decision D54 (integrator-w4): OpenAlex's own query answered 200 — a LIVE location the gate never hands on,
    # so it is not even offered to `eligible` (before D54 it was handed and refused as an API endpoint)
    assert refused == [], refused
    assert not [u for u in recovery.asked_urls(r) if "api.openalex.org" in u], recovery.asked_urls(r)
    assert V1 in recovery.asked_urls(r) and V1_0 not in recovery.asked_urls(r), "V1 answered 404, V1.0 200"


def test_l054_the_dead_handle_unpaywall_recorded_as_a_host_token_reaches_stage_e(email):
    """REAL (L054): Unpaywall's recorded answer names ScienceDirect's accepted-manuscript page then the handle; the page
    answered 403 (its first 4 KiB here) and is the kept body, the handle answered 404 — named on 411c3ce only as
    `hdl.handle.net:404` (and as text inside OpenAIRE's `detail.reason`)."""
    from litkb.acquire import recovery

    r = _call("open_access", WORKS["L054"], _ctx({"open_access": Recorded({"L054"})}))
    assert r["status"] in ("bad-file", "blocked"), r
    assert r["tried"] == ["www.sciencedirect.com:403", "hdl.handle.net:404"], r["tried"]
    assert r.get("rejected_url", "").startswith("https://www.sciencedirect.com/"), "the page is the kept body"
    found = [e["url"] for e in recovery.urls_of("open_access", r, r["status"])]
    assert HANDLE in found, found
    urls, refused = recovery.candidates([{"url": u} for u in found])
    # IN FULL (auditor-FX-E F2): the page the gate saw asked WITH its query is the page the rung kept — one
    # candidate, not a query-bare second one taking a MAX_URLS slot. Unpaywall's own request answered 200: a LIVE
    # location the gate never hands on (S4.5 decision D54, integrator-w4), so it reaches neither the candidates nor
    # `eligible` (before D54 it was handed and refused there as a credential).
    assert r["rejected_url"] == SD_PAGE
    assert urls == [SD_PAGE, HANDLE], (urls, refused)
    assert refused == [], refused
    assert recovery.asked_urls(r) == [SD_PAGE, HANDLE], recovery.asked_urls(r)


def test_l007_e1_asks_the_dead_link_and_reaches_its_recorded_capture(email):
    """REAL, end to end: the openalex answer above feeds E1. V1.0 (it answered 200 in the rung call) is live since S4.5
    decision D60 and is not asked (before D60 it answered from hardening-1's recording: availability `{}`, CDX `[]`);
    V1 from builder-C2c's tracked recording (availability -> capture 20251206182454, the 188-page
    protocol). That capture's body is not in the repository, so reaching it FAILS CLOSED — which is exactly the
    proof that E1 was asked about the dead link. On 411c3ce E1 asked V1.0 alone and ended `blocked/not_found`."""
    from litkb import cassette as CAS
    from litkb.acquire import recovery, wayback

    r = _call("openalex", WORKS["L007"], _ctx({"openalex": Recorded({"L007"})}))
    entries = recovery.urls_of("openalex", r, "binding-failed")
    iiasa, cas = C2C.replay_client(C2C.ROW_IIASA)
    client = Recorded({"L007"}, fallback=iiasa)
    ctx = _ctx({"wayback": client}, recovery_urls=entries)
    with pytest.raises(CAS.CassetteBodyMissing):
        wayback._rung(dict(WORKS["L007"]), ctx)
    assert cas.misses and "not in" in cas.misses[-1]["why"], cas.misses
    assert cas.misses[-1]["key"]["url"] == wayback.capture_url(C2C.IIASA_CAPTURE_TS, V1, "id_"), cas.misses[-1]
    # S4.5 decision D60 (integrator-w4 r2): V1.0 answered 200 in the rung call — live, never asked of the archive
    # (before D60 it was asked, and proven absent, first); V1 is answered by builder-C2c's tracked recording (the
    # fallback client, whose calls `client.calls` does not list) and reaches its capture, the miss above
    assert [urllib.parse.parse_qs(urllib.parse.urlsplit(u).query).get("url", [""])[0]
            for u in client.calls if "/wayback/available" in u] == [], "V1.0 (a 200 location) is not asked (D60)"


def test_the_gate_records_every_request_in_full_and_a_hop_is_not_a_url_of_its_own():
    """CONSTRUCTED: the gate keeps the asked URL WITH its query (its `url`/`asked` stay bare); `asked_urls` skips a
    redirect hop and reads nothing from a dict with no gate record."""
    from litkb.acquire import backoff, recovery

    g = backoff.Gate("openalex", backoff.HostCooldowns(), time.monotonic)
    g.before("https://repo.example/view.cgi?article=12&context=x")
    g.after("https://repo.example/view.cgi?article=12&context=x", 404, {}, b"gone")
    (o,) = g.summary()["observed"]
    assert o["asked_url"] == "https://repo.example/view.cgi?article=12&context=x"
    assert o["asked"] == o["url"] == "https://repo.example/view.cgi", "the gate's own record stays bare"
    r = {"cooldown_gate": {"observed": [
        {"asked_url": "https://a.example/one.pdf", "hop": True},
        {"asked_url": "https://a.example/one.pdf"}, {"asked_url": "https://b.example/two.pdf"},
        {"asked_url": "https://b.example/two.pdf"}]}}
    assert recovery.asked_urls(r) == ["https://a.example/one.pdf", "https://b.example/two.pdf"]
    assert recovery.asked_urls({"cooldown_gate": {"observed": [{"asked_url": "https://h.example/x", "hop": True}]}}) \
        == []
    assert recovery.asked_urls({}) == [] and recovery.asked_urls(None) == []


def test_d54_only_a_location_observed_dead_is_handed_on():
    """S4.5 decision D54 (integrator-w4), CONSTRUCTED gate records: a URL whose every answer was non-2xx (404, 403, a
    transport failure 0, a 503) is handed on; a URL that answered 2xx on ANY of its answers — a 200 alone, or a 503
    then a 200 on the retry — is live and is not; a redirect hop is still no URL of its own. `urls_of` hands the rung's
    own DEAD fields as before (a live one is D60's case: `test_d60_a_rungs_own_location_that_answered_2xx_...`)."""
    from litkb.acquire import recovery

    obs = [{"asked_url": "https://dead.example/404.pdf", "status": 404},
           {"asked_url": "https://live.example/200.pdf", "status": 200},
           {"asked_url": "https://flaky.example/retry.pdf", "status": 503},
           {"asked_url": "https://flaky.example/retry.pdf", "status": 200},
           {"asked_url": "https://wall.example/403", "status": 403},
           {"asked_url": "https://gone.example/t", "status": 0},
           {"asked_url": "https://partial.example/206.pdf", "status": 206},
           {"asked_url": "https://hop.example/x", "status": 301, "hop": True}]
    r = {"cooldown_gate": {"observed": obs}}
    assert recovery.asked_urls(r) == ["https://dead.example/404.pdf", "https://wall.example/403",
                                      "https://gone.example/t"]
    r["terminal"] = {"url": "https://own.example/dead.pdf", "status_code": 404}
    assert [e["url"] for e in recovery.urls_of("openalex", r, "bad-file")] == [
        "https://own.example/dead.pdf", "https://dead.example/404.pdf", "https://wall.example/403",
        "https://gone.example/t"], "the rung's own dead terminal URL is read as before"


#: S4.5 decision D60 — the three 200 pages the whole-run replay showed reaching E1 through a rung's OWN fields after
#: D54 (auditor-cand4 N5), and the REAL hardening-1 ledger rows (live `acquisition_attempts`, read as litkb_reader by
#: integrator-w4 r2: route, status, terminal_url, source_url, rejected_url, tried, terminal_status_code, and — since
#: S4.5 decision D62 — sub_status) that hold them.
D60_BU = "https://open.bu.edu/bitstream/2144/12901/4/Zhu_Zhe_2013_web.pdf"                               # L094, s2
D60_NATURE = "https://www.nature.com/articles/s41586-020-2824-5"                                        # L108, landing
D60_LWW = ("https://journals.lww.com/epidem/fulltext/2000/05000/"
           "the_distributed_lag_between_air_pollution_and.16.aspx")                                     # L125, s2
D60_SD = "https://www.sciencedirect.com/science/article/pii/S0034425714000248?via%3Dihub"               # L094, landing
D60_L094_LEDGER = [
    ("doaj", "unresolved", "https://doaj.org/api/search/articles/doi:10.1016/j.rse.2014.01.011", None, None, None, 200,
     None),
    ("s2", "bad-file", D60_BU, None, None, ["open.bu.edu:200"], 200, "html_response"),
    ("landing", "blocked", D60_SD, None, None, None, 403, "challenge_or_bot_check")]


def test_d60_a_rungs_own_location_that_answered_2xx_is_never_a_recovery_candidate():
    """S4.5 decision D60 (integrator-w4 r2): D54's rule covers every location a rung observed answering 2xx,
    including the rung's OWN rejected / terminal URL. In-run (`urls_of`, CONSTRUCTED route dicts around the REAL
    pages): a terminal that answered 200 (L094's open.bu.edu page on s2, L125's journals.lww.com page on s2, L108's
    nature.com page on the constructing `landing` route) is not handed; the same page named as `rejected_url` and seen
    200 by the gate is not handed; a page reached through a redirect that answered 200 (the gate's `url`) is not
    handed; a DEAD own field (403) still is. From the ledger (`ledger_urls`, L094's REAL recorded rows): the 200 page
    and the 200 API query are live; the 403 ScienceDirect page is the one candidate — also when a later row names the
    live page again under a non-2xx terminal."""
    from litkb.acquire import recovery

    for route, page in (("s2", D60_BU), ("s2", D60_LWW), ("landing", D60_NATURE)):
        r = {"terminal": {"url": page, "status_code": 200}, "rejected_url": page}
        assert recovery.urls_of(route, r, "bad-file") == [], (route, page)
    gate_only = {"rejected_url": D60_BU, "cooldown_gate": {"observed": [
        {"asked_url": D60_BU, "url": D60_BU, "status": 200}]}}
    assert recovery.urls_of("s2", gate_only, "bad-file") == []
    redirected = {"rejected_url": D60_NATURE, "cooldown_gate": {"observed": [
        {"asked_url": "https://doi.org/10.1038/s41586-020-2824-5", "url": "https://doi.org/10.1038/s41586-020-2824-5",
         "status": 302, "hop": True},
        {"asked_url": "https://doi.org/10.1038/s41586-020-2824-5", "url": D60_NATURE, "status": 200}]}}
    assert recovery.urls_of("crossref-link", redirected, "blocked") == []
    dead = {"terminal": {"url": D60_SD, "status_code": 403}}
    assert [e["url"] for e in recovery.urls_of("landing", dead, "blocked")] == [D60_SD]

    class _Conn:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, sql, params):
            assert sql == recovery._LEDGER_SQL and params == ("W",)
            return self

        def fetchall(self):
            return self.rows
    assert [e["url"] for e in recovery.ledger_urls(_Conn(D60_L094_LEDGER), "W")] == [D60_SD]
    again = [*D60_L094_LEDGER, ("openaire", "no-oa-copy", None, None, D60_BU, None, 404, None)]
    assert [e["url"] for e in recovery.ledger_urls(_Conn(again), "W")] == [D60_SD]


#: S4.5 decision D62 — REAL recorded challenges at 2xx. L050's Springer PDF (hardening-1: open_access and crossref-link
#: rows `blocked/challenge_or_bot_check` at 200, whose Wayback capture was `measured` on the replay before D60) and
#: L108's nature.com pages (crossref-link and landing rows, `blocked/challenge_or_bot_check` at 200) beside L108's
#: hal.science pages (open_access / hal / s2 rows `bad-file/html_response` at 200: a real 2xx page). Ledger rows read
#: from live `acquisition_attempts` as litkb_reader by integrator-w4 r2b (the `_LEDGER_SQL` columns, in order).
D62_SPRINGER = "https://link.springer.com/content/pdf/10.1007/s11192-024-05034-y.pdf"                     # L050
D62_SPRINGER_LANDING = "https://link.springer.com/10.1007/s11192-024-05034-y"                             # L050
D62_NATURE_PDF = "https://www.nature.com/articles/s41586-020-2824-5.pdf"                                  # L108
D62_HAL = "https://hal.science/hal-02997632"                                                             # L108
D62_HAL_DOC = "https://hal.science/hal-02997632/document"                                                # L108
D62_L050_LEDGER = [
    ("open_access", "blocked", D62_SPRINGER, None, None, ["link.springer.com:200", "hdl.handle.net:200"], 200,
     "challenge_or_bot_check"),
    ("crossref-link", "blocked", D62_SPRINGER, None, None, ["link.springer.com:200"], 200, "challenge_or_bot_check"),
    ("landing", "blocked", D62_SPRINGER_LANDING, None, None,
     ["doi.org:302=hop", "link.springer.com:200=challenge_or_bot_check", "link.springer.com:200=challenge_or_bot_check"],
     200, "challenge_or_bot_check")]
D62_L108_LEDGER = [
    ("open_access", "bad-file", D62_HAL, None, None, None, 200, "html_response"),
    ("crossref-link", "blocked", D62_NATURE_PDF, None, None, None, 200, "challenge_or_bot_check"),
    ("hal", "bad-file", D62_HAL_DOC, None, None, None, 200, "html_response"),
    ("s2", "bad-file", D62_HAL, None, None, None, 200, "html_response"),
    ("landing", "blocked", D60_NATURE, None, None, None, 200, "challenge_or_bot_check")]
#: THE REAL Springer "Client Challenge" page served at HTTP 200 (qc/fixtures/litkb_landing_pages/springer/hop2.body,
#: recorded by builder-C2b under its grant; recording.json holds its headers).
D62_CHALLENGE_BODY = SCRIPTS / "qc" / "fixtures" / "litkb_landing_pages" / "springer" / "hop2.body"


#: S4.5 fix round 2c (auditor-cand4-r2 F2): L060's REAL answer from the AMS host — the ladder-1 cassette's index entry
#: 1337 (`_derived/hardening/cassettes/ladder-1/index.jsonl`, hardening-1's open_access ask): HTTP 202, EMPTY body
#: (sha256 e3b0c442...), the AWS WAF challenge header. Its headers copied verbatim (the per-request CloudFront ids
#: included). The Wayback capture of this URL is L060's hunt take on the replay.
D62_AMS = "https://journals.ametsoc.org/downloadpdf/view/journals/aies/3/2/AIES-D-22-0055.1.pdf"          # L060
D62_AMS_202_HEADERS = {
    "Cache-Control": "no-store, max-age=0", "Connection": "close", "Content-Length": "0",
    "Content-Security-Policy": "frame-ancestors 'self' https://admin-journals.ametsoc.org",
    "Content-Type": "text/html; charset=UTF-8", "Date": "Thu, 24 Sep 2026 16:53:10 GMT",
    "Referrer-Policy": "no-referrer-when-downgrade", "Server": "CloudFront",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload", "Vary": "Origin",
    "Via": "1.1 d525041695bdb6325f78ebba5c11b8a2.cloudfront.net (CloudFront)",
    "X-Amz-Cf-Id": "NqI7nppEIpwQPs3QyODhy7mnlj-3XkZFu9T7mLsXXA2pNNzfb9EoDQ==", "X-Amz-Cf-Pop": "SEA900-P10",
    "X-Cache": "Error from cloudfront", "X-Content-Type-Options": "nosniff", "X-XSS-Protection": "1; mode=block",
    "x-amzn-waf-action": "challenge"}


def test_d62_l060s_real_202_waf_challenge_is_not_live_and_is_handed_to_e1():
    """S4.5 decision D62 on a 2xx that is NOT 200 (auditor-cand4-r2 F2): the gate asks THE one detector about EVERY 2xx
    answer, so L060's REAL AMS 202 (empty body, `x-amzn-waf-action: challenge`) is recorded `challenge_2xx` and the
    URL stays a Stage E candidate — the one whose Wayback capture is L060's take. A detector asked about 200 alone
    would read this 202 as a live page and drop the URL."""
    import time

    from litkb.acquire import backoff, recovery

    g = backoff.Gate("open_access", backoff.HostCooldowns(), time.monotonic)
    g.before(D62_AMS)
    g.after(D62_AMS, 202, D62_AMS_202_HEADERS, b"")
    (o,) = g.summary()["observed"]
    assert o["status"] == 202 and o["challenge_2xx"] is True, o
    r = {"cooldown_gate": g.summary(), "terminal": {"url": D62_AMS, "status_code": 202}}
    assert recovery.live_urls(r, "challenge_or_bot_check") == set()
    got = recovery.urls_of("open_access", r, "blocked", sub_status="challenge_or_bot_check")
    assert recovery.candidates(got)[0] == [D62_AMS], got


def test_d62_a_terminal_the_gate_called_a_challenge_is_not_live_whatever_the_row_is_typed():
    """S4.5 decision D62, auditor-cand4-r2 N1 (R2M2). CONSTRUCTED: a 200 terminal whose very answer the gate's detector
    called a challenge (`challenge_2xx`) on a row the ladder did NOT type a challenge (`sub_status` None) is not live
    and is handed on; the same terminal with the gate silent (challenge_2xx False) is live and dropped."""
    from litkb.acquire import recovery

    url = "https://constructed.example/article.pdf"
    gate = {"observed": [{"asked_url": url, "url": url, "status": 200, "challenge_2xx": True}]}
    r = {"cooldown_gate": gate, "terminal": {"url": url, "status_code": 200}}
    assert recovery.live_urls(r, None) == set()
    assert [e["url"] for e in recovery.urls_of("publisher-url", r, "bad-file", sub_status=None)] == [url]
    silent = {"cooldown_gate": {"observed": [dict(gate["observed"][0], challenge_2xx=False)]},
              "terminal": {"url": url, "status_code": 200}}
    assert recovery.urls_of("publisher-url", silent, "bad-file", sub_status=None) == []


def test_d62_the_ledger_reads_every_recorded_2xx_as_live_not_200_alone():
    """S4.5 decisions D60/D62, auditor-cand4-r2 N1 (R2M4). CONSTRUCTED ledger rows: a terminal recorded at 202 on a
    row typed `html_response` (a real page) is live and not handed; the same terminal on a row typed
    `challenge_or_bot_check` is handed; a 403 terminal is handed whatever its typing."""
    from litkb.acquire import recovery

    page = "https://constructed.example/landing"
    dead = "https://constructed.example/gone.pdf"

    class _Conn:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, sql, params):
            assert sql == recovery._LEDGER_SQL and params == ("W",)
            return self

        def fetchall(self):
            return self.rows
    real_202 = [("open_access", "bad-file", page, None, None, None, 202, "html_response"),
                ("landing", "blocked", dead, None, None, None, 403, "challenge_or_bot_check")]
    assert [e["url"] for e in recovery.ledger_urls(_Conn(real_202), "W")] == [dead]
    challenge_202 = [("open_access", "blocked", page, None, None, None, 202, "challenge_or_bot_check")]
    assert [e["url"] for e in recovery.ledger_urls(_Conn(challenge_202), "W")] == [page]


def test_d62_a_challenge_served_at_2xx_is_not_live_and_stays_a_recovery_candidate():
    """S4.5 decision D62 (integrator-w4 r2b): "a 2xx answer TYPED a challenge ... is NOT live — its location stays a
    Stage E candidate"; "A 2xx that is a real page (typed html_response or a PDF) stays excluded (D54/D60)".

    Gate (`backoff.Gate.after`): THE one detector reads the REAL Springer Client Challenge page at 200 as a challenge
    (`challenge_2xx`), while `challenge` (the cool-down's word) stays False; CONSTRUCTED PDF bytes at 200 are not.
    In-run (`urls_of`): that gate answer is handed on; the PDF answer is not; a terminal at 200 on a row the ladder
    typed `challenge_or_bot_check` (L050's REAL Springer PDF) is handed on, and the same terminal on a row typed
    `html_response` (L094's REAL open.bu.edu page) is not. Ledger (`ledger_urls`, REAL rows): L050's challenge-typed
    Springer PDF and landing page come back; L108's nature.com PDF and article page come back and its hal.science pages
    (html_response at 200) stay out; L094 still hands only the ScienceDirect page."""
    import time

    from litkb.acquire import backoff, recovery

    body = D62_CHALLENGE_BODY.read_bytes()
    g = backoff.Gate("open_access", backoff.HostCooldowns(), time.monotonic)
    g.before(D62_SPRINGER)
    g.after(D62_SPRINGER, 200, {"content-type": "text/html; charset=utf-8"}, body)
    g.before("https://real.example/paper.pdf")
    g.after("https://real.example/paper.pdf", 200, {"content-type": "application/pdf"}, b"%PDF-1.7 CONSTRUCTED")
    challenge, pdf = g.summary()["observed"]
    assert challenge["challenge_2xx"] is True and challenge["challenge"] is False, challenge
    assert pdf["challenge_2xx"] is False, pdf
    gated = {"cooldown_gate": g.summary()}
    assert [e["url"] for e in recovery.urls_of("open_access", gated, "blocked", sub_status="challenge_or_bot_check")] \
        == [D62_SPRINGER]
    assert recovery.live_urls(gated) == {"https://real.example/paper.pdf"}

    typed = {"terminal": {"url": D62_SPRINGER, "status_code": 200}}
    assert [e["url"] for e in recovery.urls_of("crossref-link", typed, "blocked",
                                               sub_status="challenge_or_bot_check")] == [D62_SPRINGER]
    assert recovery.urls_of("crossref-link", typed, "bad-file", sub_status="html_response") == []
    real_page = {"terminal": {"url": D60_BU, "status_code": 200}}
    assert recovery.urls_of("s2", real_page, "bad-file", sub_status="html_response") == []

    class _Conn:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, sql, params):
            assert sql == recovery._LEDGER_SQL and params == ("W",)
            return self

        def fetchall(self):
            return self.rows
    got = recovery.candidates(recovery.ledger_urls(_Conn(D62_L050_LEDGER), "W"))[0]
    assert got == [D62_SPRINGER, D62_SPRINGER_LANDING], got
    got = recovery.candidates(recovery.ledger_urls(_Conn(D62_L108_LEDGER), "W"))[0]
    assert got == [D62_NATURE_PDF, D60_NATURE], got
    assert [e["url"] for e in recovery.ledger_urls(_Conn(D60_L094_LEDGER), "W")] == [D60_SD]


def test_a_constructed_guess_is_not_read_from_the_gate_but_its_own_fields_are():
    """CONSTRUCTED: Stage C and Stage A's publisher templates CONSTRUCT their URLs (`CONSTRUCTING_ROUTES`), so a guess
    that answered 404 is not a dead document; their terminal / rejected URLs are read as before."""
    from litkb.acquire import recovery

    gate = {"observed": [{"asked_url": "https://cdn.example/guess-1.pdf"}, {"asked_url": "https://x.example/p"}]}
    # The ORACLE is a literal, never `recovery.CONSTRUCTING_ROUTES` itself (auditor-FX-E F3: iterating the constant
    # let a route dropped from it pass): Stage A's templates and Stage C's rules are the two routes that construct
    # their URLs (referee-stage-e §2b; 14 of the 16 dead links E1 missed in hardening-1 were Stage C guesses).
    for route in ("publisher-url", "landing"):
        r = {"terminal": {"url": "https://x.example/p"}, "cooldown_gate": gate}
        assert [e["url"] for e in recovery.urls_of(route, r, "blocked")] == ["https://x.example/p"], route
    r = {"terminal": {"url": "https://x.example/p"}, "cooldown_gate": gate}
    assert [e["url"] for e in recovery.urls_of("openalex", r, "blocked")] == [
        "https://x.example/p", "https://cdn.example/guess-1.pdf", "https://x.example/p"]
    assert recovery.urls_of("openalex", r, "measured") == [], "a success still names none"


# ── item 2: a metadata API's URL is never sent to the Wayback Machine ────────────────────────

#: The three metadata-API URL families among what E1/E5 were asked about in hardening-1 — builder-FX-E's own reading
#: of the 292 URLs (the rungs that build them: stage_b_repos's DOAJ and Zenodo record calls, the `venue` rung's
#: OpenReview search), held here as the ORACLE, independent of `recovery.is_api`.
API_FAMILIES = ("https://api2.openreview.net/notes/search?", "https://doaj.org/api/search/articles/",
                "https://zenodo.org/api/records/")


def test_the_metadata_api_urls_e1_was_asked_about_in_hardening_1_are_never_candidates():
    """REAL: the 292 distinct URLs E1/E5 were asked about (provenance.json). The 143 metadata-API URLs (72 OpenReview
    searches, 70 DOAJ searches, one Zenodo record) cost 264 of E1's 572 requests (referee-stage-e N2); on 411c3ce
    every one was eligible. The other 149 stay eligible."""
    from litkb.acquire import recovery

    urls = json.loads((FIX / "asked_urls.json").read_text(encoding="utf-8"))
    assert len(urls) == 292
    api = [u for u in urls if u.startswith(API_FAMILIES)]
    assert len(api) == 143
    assert [u for u in api if recovery.eligible(u) != (False, "an API endpoint")] == []
    assert [u for u in urls if u not in api and not recovery.eligible(u)[0]] == []


def test_every_service_endpoint_the_ladder_calls_is_an_api_and_no_document_template_is():
    """The request gate hands Stage E EVERY URL a rung asked, a service's own query included, so each Stage A / B /
    open-access endpoint constant must read as an API (none may ever be offered to the Wayback Machine) and each
    DOCUMENT template must not (a dead one is exactly Stage E's input). `API_URL_PREFIXES` are the two endpoints the
    host / first-segment rule misses, held equal to their constants here."""
    import collections

    from litkb.acquire import open_access, recovery, stage_a, stage_b, stage_b_repos

    fill = collections.defaultdict(lambda: "x")

    def f(t):
        return t.format_map(fill)
    endpoints = [stage_b.CROSSREF_WORK, stage_b.OPENALEX_WORK, stage_b.OPENCITATIONS_META, stage_b.DATACITE_WORK,
                 stage_b.NCBI_IDCONV, stage_b.S2_PAPER, stage_b_repos.DOAJ_ARTICLES, stage_b_repos.OPENAIRE_PUBLICATIONS,
                 stage_b_repos.HAL_SEARCH, stage_b_repos.OSF_PREPRINT, stage_b_repos.ZENODO_RECORD,
                 stage_b_repos.FIGSHARE_ARTICLE, stage_b_repos.EUROPEPMC_CORE, stage_b_repos.OPENREVIEW_SEARCH,
                 open_access.UNPAYWALL_API]
    assert [t for t in endpoints if not recovery.is_api(f(t))] == []
    documents = [stage_b_repos.EUROPEPMC_RENDER, stage_b_repos.ACL_PDF, stage_b_repos.OPENREVIEW_PDF,
                 open_access.ARXIV_PDF, *stage_a.PUBLISHER_TEMPLATES.values()]
    assert [t for t in documents if recovery.is_api(f(t))] == []
    assert sorted(recovery.API_URL_PREFIXES) == sorted([f(stage_b.NCBI_IDCONV).split("v1/")[0],
                                                        f(stage_b_repos.EUROPEPMC_CORE).split("search?")[0]])


@pytest.mark.parametrize("url,api", [
    ("https://api.crossref.org/works/10.1/x", True), ("https://api2.openreview.net/notes?id=1", True),
    ("https://API3.example.org/v1/items", True), ("https://doaj.org/api/v4/search/articles/doi:10.1/x", True),
    ("https://zenodo.org/api/records/1", True), ("https://zenodo.org/api/records/1/files", True),
    ("https://zenodo.org/api/records/1/files/paper.pdf", True),
    ("https://zenodo.org/api/records/1/files/paper.pdf/content", False),
    ("https://zenodo.org/records/1/files/paper.pdf", False), ("https://openreview.net/pdf?id=abc", False),
    ("https://repo.example.edu/server/api/core/bitstreams/0f1e/content", False),
    ("https://apis.example.org/paper.pdf", False), ("https://rapid.example.org/api.pdf", False),
    ("https://www.example.org/apidocs/paper.pdf", False)])
def test_what_counts_as_a_metadata_api(url, api):
    """CONSTRUCTED: the host's first label `api` / `api<digits>`, or the path's FIRST segment `api` — a deeper `api`
    segment (a DSpace 7 bitstream) is a document, and so is InvenioRDM's file-content route (a record, its file
    listing and a file's metadata stay APIs)."""
    from litkb.acquire import recovery

    assert recovery.is_api(url) is api
    assert recovery.eligible(url)[0] is (not api)


def _invenio():
    """invenio.jsonl's recorded interactions (hardening-1's ladder-1 index lines, verbatim), each CHECKED against
    provenance.json's "invenio" section: {manifest row: (key url, status, headers, inline body or None)}."""
    prov = {p["key_sha256"]: p for p in PROV["invenio"]}
    out = {}
    for ln in (FIX / "invenio.jsonl").read_bytes().splitlines()[1:]:
        e = json.loads(ln)
        p = prov[e["key_sha256"]]
        assert (e["key"]["url"], e["response"]["status"], e["take"]) == (p["url"], p["status"], p["take"]), p
        b = e["response"]["body"]
        assert (b["sha256"], b["length"]) == (p["body_sha256"], p["body_length"]), p
        body = base64.b64decode(b["inline_b64"]) if "inline_b64" in b else None
        assert body is None or _sha(body) == b["sha256"], p
        out[p["manifest_row"]] = (e["key"]["url"], e["response"]["status"], e["response"]["headers"], body)
    assert sorted(out) == ["L006", "L063"]
    return out


def test_an_invenio_file_content_url_is_a_document_never_an_api():
    """REAL (auditor-FX-E F1). hardening-1's recorded Zenodo answer for L006 (B14 asked zenodo.org/api/records/
    20559202) names each of its files by `links.self`, `/api/records/<id>/files/<key>/content` — the URL B14 downloads
    a PDF from (`stage_b_repos.zenodo_files`) — and crossref-link LANDED L063's PDF from Rogue Scholar's URL of that
    shape (200, %PDF). Each is a document a dead link could name, so each stays a Stage E candidate; the record
    itself stays an API. On b5b8df8 (the first-segment rule without its document route) every file URL read as an
    API; on 411c3ce (the `api.` host prefix) they were eligible."""
    from litkb.acquire import recovery, stage_b_repos

    rec = _invenio()
    record_url, st, _h, body = rec["L006"]
    assert (record_url, st) == (stage_b_repos.ZENODO_RECORD.format(id=20559202), 200)
    assert recovery.eligible(record_url) == (False, "an API endpoint"), "the record answer is metadata"
    selves = [f["links"]["self"] for f in json.loads(body)["files"]]
    assert len(selves) == 48 and all(u.startswith(record_url + "/files/") and u.endswith("/content") for u in selves)
    assert [u for u in selves if recovery.eligible(u) != (True, "")] == []
    landed, st, headers, _b = rec["L063"]
    assert st == 200 and headers["content-disposition"].endswith(".pdf"), headers
    assert recovery.eligible(landed) == (True, "")


def test_a_dead_invenio_file_reaches_stage_e():
    """The REAL Rogue Scholar URL (L063) under a CONSTRUCTED 404 on the rung that landed it: the request gate's record
    hands it to E1 as a candidate — the case F1 names (a dead InvenioRDM file could no longer reach E1)."""
    from litkb.acquire import recovery

    url = _invenio()["L063"][0]
    r = {"status": "blocked", "tried": ["rogue-scholar.org:404"],
         "cooldown_gate": {"observed": [{"asked_url": url, "status": 404}]}}
    found = [e["url"] for e in recovery.urls_of("crossref-link", r, "blocked")]
    assert recovery.candidates([{"url": u} for u in found]) == ([url], [])


# ── item 3: a recovered PDF of another work is neither landed nor measured ─────────────────

def test_l022_the_census_capture_is_never_a_conversion_of_10_1002_wics_1317():
    """REAL (L022): the recorded census.gov capture (Winkler's 1993 Census chapter, 38 pages), asked for its record
    10.1002/wics.1317 (2014) — which the binder's title-and-first-author rule accepts. E1 books it `hash-mismatch`
    with its bytes kept and the contradiction named; on 411c3ce it was `downloaded` and the ladder booked `measured`."""
    from litkb.acquire import wayback

    work = dict(WORKS["L022"])
    assert (work["doi"], work["year"], work["first_author"]) == ("10.1002/wics.1317", 2014, "Winkler")
    client, cas = C2C.replay_client(C2C.ROW_CENSUS)
    r = wayback._rung(work, _ctx({"wayback": client}, mode="measure",
                                 recovery_urls=[{"url": C2C.CENSUS_URL}]))
    assert r["status"] == "hash-mismatch" and _sha(r["pdf"]) == C2C.CENSUS_PDF_SHA256, r.get("detail")
    assert "prints no year after 1993" in r["reason"] and "2014" in r["reason"], r["reason"]
    assert r["reason"] in r["detail"] and cas.misses == []


def test_d55_a_wrong_work_capture_never_ends_e1_before_a_later_candidates_right_copy():
    """S4.5 decision D55 (integrator-w4; auditor-FX-E F3). Two candidate URLs for L022's record (10.1002/wics.1317,
    2014): the FIRST is archived as the REAL census.gov capture (Winkler's 1993 Census chapter — another work), the
    SECOND as a CONSTRUCTED copy of the work printing its own year. E1 judges each capture where it finds it, moves on
    from the wrong work, and lands the second: `downloaded` from the second URL's capture. Before D55 the first PDF
    ended E1 (`fetch_wayback` returned it) and only then was it judged: `hash-mismatch`, the right copy never asked.
    With the second candidate gone, the census capture is `hash-mismatch` with its bytes kept, as before."""
    from litkb.acquire import wayback

    work = dict(WORKS["L022"])
    census = C2C.census_pdf()
    first, second = "https://first.example/constructed-dead.pdf", "https://second.example/constructed-dead.pdf"
    c2a = _load("_litkb_hardening_c2a_for_fx_e_d55", INSTR / "litkb_hardening_c2a.py")
    right = c2a.constructed_pdf("CONSTRUCTED copy of the 2014 overview, printed 2014", "Winkler")
    from litkb.acquire import recovery
    assert recovery.capture_identity(work, right) == "" and recovery.capture_identity(work, census) != ""

    def avail(url, ts):
        return (200, {"Content-Type": "application/json"}, json.dumps(
            {"url": url, "archived_snapshots": {"closest": {"available": True, "status": "200", "timestamp": ts,
                                                            "url": f"http://web.archive.org/web/{ts}/{url}"}}}).encode())
    answers = {
        wayback.availability_url(first): avail(first, "20200101000000"),
        wayback.capture_url("20200101000000", first, "id_"): (200, {"Content-Type": "application/pdf"}, census),
        wayback.availability_url(second): avail(second, "20210101000000"),
        wayback.capture_url("20210101000000", second, "id_"): (200, {"Content-Type": "application/pdf"}, right)}

    class Exact:
        """CONSTRUCTED: answers only the exact URLs above; any other request FAILS the test."""
        base = ""

        def __init__(self, answers):
            self.answers, self.calls = answers, []

        def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
            self.calls.append(url)
            if url not in self.answers:
                raise AssertionError(f"not an expected request: {url}")
            return self.answers[url]

    client = Exact(answers)
    r = wayback._rung(work, _ctx({"wayback": client}, mode="measure",
                                 recovery_urls=[{"url": first}, {"url": second}]))
    assert r["status"] == "downloaded" and r["pdf"] == right, (r.get("status"), r.get("detail"))
    assert r["source_url"] == wayback.capture_url("20210101000000", second, "id_")
    assert client.calls == list(answers), client.calls        # the wrong work's other captures are never asked
    # the first candidate alone: the census capture is booked hash-mismatch, its bytes kept (FX-E item 3)
    alone = Exact({k: v for k, v in answers.items()
                   if k in (wayback.availability_url(first), wayback.capture_url("20200101000000", first, "id_"))})
    r1 = wayback._rung(work, _ctx({"wayback": alone}, mode="measure", recovery_urls=[{"url": first}]))
    assert r1["status"] == "hash-mismatch" and _sha(r1["pdf"]) == C2C.CENSUS_PDF_SHA256, r1.get("detail")
    assert "prints no year after 1993" in r1["reason"] and r1["reason"] in r1["detail"], r1


def test_the_census_capture_for_its_own_identity_is_still_the_work():
    """REAL bytes, the positive control: for a record carrying the capture's OWN year (1993) nothing is contradicted;
    and a record with no year, or a PDF that prints no year, is never judged (the rule abstains)."""
    from litkb.acquire import recovery

    pdf = C2C.census_pdf()
    assert recovery.latest_printed_year(pdf) == (1993, 38)
    assert recovery.capture_identity({"year": 1993}, pdf) == ""
    assert recovery.capture_identity({"year": 1993 + recovery.IDENTITY_YEAR_LEAD}, pdf) == ""
    assert recovery.capture_identity({"year": 1994 + recovery.IDENTITY_YEAR_LEAD}, pdf) != ""
    # LITERAL leads, independent of the constant (auditor-FX-E F4: every case above moves with it). Lead 1 — the
    # largest lead a REAL copy showed in hardening-1 (6 of the 104 accepted (work, bytes) pairs, each bound by the
    # binder; builder-FX-E's `latest_printed_year` census) — is never refused; lead 21 (L022's) is.
    assert recovery.capture_identity({"year": 1994}, pdf) == "", "a lead a real copy shows is never refused"
    assert recovery.capture_identity({"year": 2014}, pdf) != "", "L022's lead"
    assert recovery.capture_identity({"year": None}, pdf) == "" and recovery.capture_identity({}, pdf) == ""
    assert recovery.capture_identity({"year": 2014}, b"not a pdf") == ""


def test_an_internet_archive_pdf_of_another_work_is_never_a_conversion():
    """CONSTRUCTED item metadata around the REAL census bytes: E3's identified item serves a PDF whose own dates
    contradict the record (2014) -> `hash-mismatch`, like E1's."""
    from litkb.acquire import ia

    work = dict(WORKS["L022"])
    pdf = C2C.census_pdf()
    stub = C2C.StubClient({
        "advancedsearch.php": (200, {"Content-Type": "application/json"}, json.dumps({"responseHeader": {"status": 0},
            "response": {"docs": [{"identifier": "constructed-item", "external-identifier": [f"urn:doi:{work['doi']}"]}]}}).encode()),
        "/metadata/constructed-item": (200, {"Content-Type": "application/json"}, json.dumps(
            {"metadata": {"collection": ["opensource"]}, "files": [{"name": "c.pdf", "source": "original"}]}).encode()),
        "/download/constructed-item/c.pdf": (200, {"Content-Type": "application/pdf"}, pdf)})
    r = ia._rung(work, _ctx({"ia": stub}, mode="measure"))
    assert r["status"] == "hash-mismatch" and _sha(r["pdf"]) == C2C.CENSUS_PDF_SHA256, r
    assert "1993" in r["reason"]


# ── item 4: an Internet Archive query error is an api-error, never "no item" ─────────────────

def test_l007_the_recorded_ia_query_error_is_an_api_error_never_not_in_corpus(monkeypatch):
    """REAL (L007): the query 411c3ce built for the corporate first author (its closing parenthesis lost in the record)
    was unbalanced, and archive.org answered 200 `{"error": "a structure was opened but not closed ..."}`; the rung
    read "0 hit(s)" and booked `not-in-archive/not_in_corpus` (referee-vocabulary). Replayed with the 411c3ce query
    builder, so the request is byte-for-byte the recorded one."""
    from litkb.acquire import ia

    monkeypatch.setattr(ia, "_group_body", ia._phrase, raising=False)
    work = dict(WORKS["L007"])
    (rec,) = [e for e in _entries() if e["row"] == "L007" and "advancedsearch" in e["url"]]
    assert ia.search_url(work) == rec["url"], "the recorded request"
    r = ia.fetch_ia(work, Recorded({"L007"}))
    assert (r["status"], r.get("retriable"), r.get("sub_status")) == ("api-error", False, None), r
    assert "a structure was opened but not closed" in r["detail"], r["detail"]


def test_l007_the_query_for_a_corporate_first_author_is_balanced_now():
    """The first author's grouping characters are spaces now: the query is balanced and differs from the recorded
    one ONLY inside the creator group. (CONSTRUCTED check: the fixed query was never sent; no grant covers it.)"""
    from litkb.acquire import ia

    work = dict(WORKS["L007"])
    q = ia.query(work)
    assert q.count("(") == q.count(")"), q
    assert "creator:(Land Product Validation Subgroup Working Group on Calibration and Validation)" in q
    (rec,) = [e for e in _entries() if e["row"] == "L007" and "advancedsearch" in e["url"]]
    old = urllib.parse.parse_qs(urllib.parse.urlsplit(rec["url"]).query)["q"][0]
    assert old.split("creator:(")[0] == q.split("creator:(")[0]


def test_l054_a_name_without_grouping_characters_builds_the_recorded_query_and_no_item_is_still_no_item():
    """REAL (L054): an ordinary surname builds the byte-identical request hardening-1 sent (every one of the run's 99
    searches but L007's is unchanged: builder-FX-E's census, report), and its recorded ANSWER — 0 hits, status 0 —
    is still `not-in-archive/not_in_corpus`."""
    from litkb.acquire import ia

    work = dict(WORKS["L054"])
    (rec,) = [e for e in _entries() if e["row"] == "L054" and "advancedsearch" in e["url"]]
    assert ia.search_url(work) == rec["url"]
    assert ia.search_error(rec["body"]) == ""
    r = ia.fetch_ia(work, Recorded({"L054"}))
    assert (r["status"], r["sub_status"]) == ("not-in-archive", "not_in_corpus"), r


@pytest.mark.parametrize("body,why", [
    (b'{"error": "boom"}', "the search answered an error: boom"), (b"<html>busy</html>", "the body is not JSON"),
    (b'{"responseHeader": {"status": 0}}', "the body carries no `response` object"),
    (b'{"responseHeader": {"status": 400}, "response": {"docs": []}}', "the search's responseHeader.status is 400"),
    (b"[]", "the body is not a JSON object")])
def test_a_search_answer_that_is_not_its_answer_is_named(body, why):
    """CONSTRUCTED bodies: every shape that is not the search's own answer, and why."""
    from litkb.acquire import ia

    assert ia.search_error(body) == why
    stub = C2C.StubClient({"advancedsearch.php": (200, {"Content-Type": "application/json"}, body)})
    r = ia.fetch_ia({"doi": "10.1/constructed", "title": "A constructed title", "first_author": "Doe"}, stub)
    assert (r["status"], r["retriable"]) == ("api-error", False), r


@pytest.mark.parametrize("meta", [(403, b"<html>Forbidden</html>"), (200, b"<html>not json</html>")])
def test_an_identified_item_whose_metadata_is_no_answer_is_an_api_error(meta):
    """CONSTRUCTED: the search identifies an item by DOI, its metadata answer is not one -> `api-error`, never "dark"
    and so never `not_in_corpus` (the metadata API's own `{}` for an item it does not serve still reads dark)."""
    from litkb.acquire import ia

    doi = "10.1/constructed"
    search = (200, {"Content-Type": "application/json"}, json.dumps({"responseHeader": {"status": 0}, "response": {
        "docs": [{"identifier": "item-x", "external-identifier": [f"urn:doi:{doi}"]}]}}).encode())
    work = {"doi": doi, "title": "A constructed title", "first_author": "Doe"}
    r = ia.fetch_ia(work, C2C.StubClient({"advancedsearch.php": search, "/metadata/item-x": (meta[0], {}, meta[1])}))
    assert (r["status"], r["retriable"]) == ("api-error", False) and "without its answer" in r["detail"], r
    r = ia.fetch_ia(work, C2C.StubClient({"advancedsearch.php": search, "/metadata/item-x": (200, {}, b"{}")}))
    assert (r["status"], r["sub_status"]) == ("not-in-archive", "not_in_corpus"), r


# ── through the LADDER, on a worker database ────────────────────────────────────────────────

@pytest.fixture
def world(litkb_pg_base, tmp_path):
    _psycopg, conn, _ran = litkb_pg_base
    w = C2C.World(conn, tmp_path)
    yield w
    w.close()


@pg_only
def test_the_census_capture_is_booked_hash_mismatch_in_measure_mode_and_counts_no_wrong_work(world):
    """REAL recorded capture, CONSTRUCTED admission carrying 10.1002/wics.1317's author and YEAR (2014; a salted DOI
    and title): MEASURE mode books `hash-mismatch` with the served sha, never `measured`, so
    `wayback_wrong_work_counted` reads 0 on it (1 on 411c3ce) and `rung_conversions_wayback` does not count it."""
    since = world.owner.execute("SELECT clock_timestamp()").fetchone()[0]
    ws = world.ws("fx-e-wrong-work")
    work = world.work(ws, year=WORKS["L022"]["year"])
    world.dead_link(ws, work, C2C.CENSUS_URL)
    client, _cas = C2C.replay_client(C2C.ROW_CENSUS)
    world.ladder(ws, work, {"wayback": client}, routes=("wayback",))
    (status, sub, detail), = C2C._rows(world.owner, work["work_id"])
    assert (status, sub) == ("hash-mismatch", None), detail
    assert detail["sha256"] == C2C.CENSUS_PDF_SHA256 and "prints no year after 1993" in detail["reason"], detail
    assert detail.get("not_quarantined") == "measure mode"
    assert C2C.wayback_wrong_work_counted(world.owner, {"wayback_wrong_work_dois": [work["doi"]]}) == 0
    assert C2C.REPORTED["rung_conversions_wayback"](world.owner, {"frozen_at": since,
                                                                 "run_workstream_ids": [str(ws)]}) == 0


@pg_only
def test_the_census_capture_is_quarantined_never_landed_in_acquire_mode(world):
    """The same capture in ACQUIRE mode: `hash-mismatch`, its bytes quarantined under that label with a
    `quarantine_payloads` row (a reason word of `litkb.quarantine.REASONS`), nothing filed, and the binder is never
    reached. What this test does NOT show (auditor-FX-E F10): a wrong landing on 411c3ce — its admission is
    CONSTRUCTED with a salted title, so there the binder refuses it (`binding-failed`), and this test shows only the
    status the identity rule gives instead. That the binder BINDS these bytes to the REAL record 10.1002/wics.1317
    (same title and first author) is builder-FX-E's scratch measurement on the live record (report, item 3), not a
    claim this test carries."""
    ws = world.ws("fx-e-acquire")
    work = world.work(ws, year=WORKS["L022"]["year"])
    world.dead_link(ws, work, C2C.CENSUS_URL)
    client, _cas = C2C.replay_client(C2C.ROW_CENSUS)
    out = world.ladder(ws, work, {"wayback": client}, routes=("wayback",), mode="acquire")
    (status, _sub, detail), = C2C._rows(world.owner, work["work_id"])
    assert status == "hash-mismatch" and "__hash-mismatch__" in detail["quarantined"], detail
    assert "binding" not in detail and out["outcome"] != "ok", out
    (reason,) = [r[0] for r in world.owner.execute(
        "SELECT reason FROM litkb.quarantine_payloads WHERE work_id = %s", (work["work_id"],)).fetchall()]
    assert reason == "hash-mismatch"
    assert not any(world.store.filed.rglob("*.pdf")) if world.store.filed.exists() else True


@pg_only
@pytest.mark.parametrize("name", ["stage_e_wrong_work_capture_credited", "stage_e_dead_location_behind_a_kept_page"])
def test_the_fx_e_fires_hold_their_bound_on_control_and_break_it_on_the_known_bad(world, name, tmp_path):
    """The two FX-E fires as tests, through the harness's own runner (`litkb_acceptance.hardening_fire`: reset,
    control, reset, known-bad, reset — the control arm's refusal of the census bytes would otherwise name them
    `known-bad` in the known-bad arm). They also run in `hardening --fire all`."""
    A = _load("_litkb_acceptance_for_fx_e", INSTR / "litkb_acceptance.py")
    res = A.hardening_fire(name, db=world.owner.info.dbname, conn=world.owner, workroot=tmp_path)
    assert res["fired"], res["lines"]

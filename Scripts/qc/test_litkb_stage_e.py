"""litkb S4.5 Stage E (builder-C2c; LITKB_WORKPLAN.md "### S4.5" item 6): the Wayback Machine (E1, route `wayback`),
Internet Archive items (E3, route `ia`) and the Common Crawl index (E5, route `commoncrawl`), and the ladder seam that
hands them the dead URLs other rungs met (`litkb.acquire.recovery`).

Every input is named for what it is:
  REAL       the answers recorded ONCE on 2026-09-23 through builder A's cassette (qc/fixtures/litkb_cassettes/
             stage_e/, provenance.json there): the census.gov capture, the IIASA row, one IA search, one Common
             Crawl index query. Replayed here with no socket (the suite's guard is on).
  CONSTRUCTED  stub answers no host was asked for: a never-archived URL, a wrapper page, a CDX 503, IA item metadata
             (dark, lending, open), a WARC record envelope (around the REAL census PDF bytes).

What the recording MEASURED, and these tests pin (a re-recording that changes it turns them red, which is the
point): the census capture WITHOUT a raw modifier served the same PDF (the survey's "wrapper" was not seen); that
PDF is Winkler's 1993 Census paper, ANOTHER WORK than 10.1002/wics.1317, the DOI the plan names it for; and the
plan's NEGATIVE — the IIASA copy, "never archived" — IS archived (2025-12-06) and is the work. The grades that
follow (`litkb_hardening_c2c.WAYBACK_ROWS`) are pinned here too.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_stage_e.py -q
"""
import base64
import gzip
import hashlib
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import threading
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


C2C = _load("_litkb_hardening_c2c_for_tests", INSTR / "litkb_hardening_c2c.py")


def _sha(b):
    return hashlib.sha256(b or b"").hexdigest()


def _json(obj):
    return (200, {"Content-Type": "application/json"}, json.dumps(obj).encode())


def _avail(ts=None, status="200", url="https://x.example/r.pdf"):
    """CONSTRUCTED availability answer (the API's own shape, as recorded in the fixture)."""
    snaps = {"closest": {"status": status, "available": True, "timestamp": ts,
                         "url": f"http://web.archive.org/web/{ts}/{url}"}} if ts else {}
    return _json({"url": url, "archived_snapshots": snaps})


def _cdx(*rows):
    """CONSTRUCTED CDX JSON output: the header row, then one row per capture."""
    head = ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]
    return _json([head] + [["k", ts, "https://x.example/r.pdf", "application/pdf", "200", f"D{ts}", "9"]
                           for ts in rows])


# ── registration, policy ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("first", ["litkb.acquire.wayback", "litkb.acquire.ia", "litkb.acquire.commoncrawl",
                                   "litkb.acquire.run"])
def test_the_stage_e_rungs_are_registered_in_order_whatever_is_imported_first(first):
    """D19: `import litkb.acquire.run` registers E1, E3, E5; and the Stage E order is E1, E3, E5 even when a rung
    module is imported BEFORE the ladder (measured before `recovery.register`: wayback first put it last)."""
    code = ("import importlib; importlib.import_module(%r); from litkb.acquire import run; "
            "print([r.route for r in run.ladder_rungs(('commoncrawl', 'ia', 'wayback'))]); "
            "print(sorted({r.stage for r in run.RUNGS if r.route in ('wayback', 'ia', 'commoncrawl')}))" % first)
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS / "pipeline"), PYTHONUTF8="1")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == ["['wayback', 'ia', 'commoncrawl']", "['E']"], out.stdout


def test_every_stage_e_host_has_a_policy_line_and_an_unnamed_host_is_refused():
    from litkb.acquire import policy as P

    for route, host in (("wayback", "archive.org"), ("wayback", "web.archive.org"), ("ia", "archive.org"),
                        ("commoncrawl", "index.commoncrawl.org"), ("commoncrawl", "data.commoncrawl.org")):
        d = P.decide(route, host)
        assert d.allowed and d.tier == P.LEGITIMATE and P.POLICY[d.line].host == host, (route, host, d)
    for route in ("wayback", "ia", "commoncrawl"):
        assert not P.decide(route, "evil.example").allowed
        assert not P.decide(route, "sci.bban.top").allowed
    assert not any(p.host == "*" for p in P.POLICY if p.route in ("wayback", "ia", "commoncrawl"))


# ── the recovery candidates ─────────────────────────────────────────────────────────────────

def test_a_recovery_candidate_is_never_a_shadow_host_a_credential_an_archive_or_an_api():
    from litkb.acquire import recovery as R
    from litkb.netutil import add_secret

    secret = f"PLANTEDc2c{uuid.uuid4().hex}"
    add_secret(secret)
    refused = {
        "https://sci-hub.ru/10.1/x": "a shadow front's host",
        "https://sci.bban.top/pdf/10.1/x.pdf": "a shadow front's host",
        "https://oa.example/p.pdf?email=kam@example.invalid": "carries a credential or its redaction mask",
        f"https://oa.example/{secret}/p.pdf": "carries a credential or its redaction mask",
        "https://oa.example/<KEY>/p.pdf": "carries a credential or its redaction mask",
        "https://web.archive.org/web/2020/https://x.example/p.pdf": "an archive's own URL",
        "https://data.commoncrawl.org/crawl-data/x.warc.gz": "an archive's own URL",
        "https://doi.org/10.1002/wics.1317": "a DOI resolver",
        "https://api.unpaywall.org/v2/10.1002/wics.1317": "an API endpoint",
        "ftp://x.example/p.pdf": "not http(s)",
    }
    for url, why in refused.items():
        assert R.eligible(url) == (False, why), url
    assert R.eligible(C2C.CENSUS_URL) == (True, "")
    urls, out = R.candidates([{"url": C2C.CENSUS_URL}, {"url": C2C.CENSUS_URL}, *[{"url": u} for u in refused]]
                             + [{"url": f"https://x{i}.example/p.pdf"} for i in range(R.MAX_URLS + 2)])
    assert urls[0] == C2C.CENSUS_URL and len(urls) == R.MAX_URLS and len(set(urls)) == len(urls)
    assert sum(1 for x in out if "cap" in x["why"]) == 3


def test_dead_urls_come_from_legitimate_answers_that_did_not_succeed():
    from litkb.acquire import recovery as R

    ans = {"rejected_url": "https://a.example/r.pdf", "source_url": "", "tried": ["h:404", "https://b.example/t.pdf"],
           "terminal": {"url": "https://c.example/p.pdf", "status_code": 404}}
    assert [x["url"] for x in R.urls_of("open_access", ans, "bad-file")] == [
        "https://a.example/r.pdf", "https://c.example/p.pdf", "https://b.example/t.pdf"]
    assert R.urls_of("open_access", ans, "ok") == [] and R.urls_of("open_access", ans, "measured") == []
    assert R.urls_of("scihub", ans, "blocked") == [] and R.urls_of("annas", ans, "bad-file") == []
    assert R.urls_of("wayback", ans, "blocked") == [], "a Stage E answer never feeds Stage E"
    assert [x["url"] for x in R.urls_of("hunt-url", ans, "bad-file")][0] == "https://a.example/r.pdf"


# ── E1 on the REAL recording ────────────────────────────────────────────────────────────────

def test_the_recorded_census_capture_lands_through_the_raw_modifier():
    """REAL: availability names the 2021-03-22 capture (archived status 200); its id_ fetch is the census.gov PDF."""
    from litkb.acquire import wayback

    client, cas = C2C.replay_client(C2C.ROW_CENSUS)
    r = wayback.fetch_wayback([C2C.CENSUS_URL], client)
    assert r["status"] == "downloaded" and _sha(r["pdf"]) == C2C.CENSUS_PDF_SHA256, r.get("tried")
    assert r["tried"] == ["availability:200", f"capture {C2C.CENSUS_CAPTURE_TS}id_:200"]
    assert r["source_url"] == wayback.capture_url(C2C.CENSUS_CAPTURE_TS, C2C.CENSUS_URL, "id_")
    assert r["terminal"]["headers"].get("Content-Type") == "application/pdf"
    assert cas.misses == []


def test_the_raw_modifier_is_not_load_bearing_on_the_recorded_census_capture():
    """MEASURED (the reason the brief's "id_ removed -> refused as HTML" fire cannot fire on the real row): the bare
    capture URL and the if_ capture served the SAME bytes as the id_ capture. If a re-recording ever serves the
    survey's wrapper page instead, this test goes red and the real-row fire becomes possible."""
    from litkb.acquire import wayback

    client, _cas = C2C.replay_client(C2C.ROW_CENSUS_NO_RAW)
    saved = wayback.RAW_MODIFIERS
    wayback.RAW_MODIFIERS = ("",)
    try:
        r = wayback.fetch_wayback([C2C.CENSUS_URL], client)
    finally:
        wayback.RAW_MODIFIERS = saved
    assert r["status"] == "downloaded" and _sha(r["pdf"]) == C2C.CENSUS_PDF_SHA256
    (e,) = C2C.recorded_entries(C2C.ROW_CENSUS_IF)
    assert "if_/" in e["key"]["url"] and e["response"]["body"]["sha256"] == C2C.CENSUS_PDF_SHA256


def test_the_plans_iiasa_negative_is_archived_by_the_recorded_truth():
    """MEASURED 2026-09-23: the IIASA copy the plan names as E1's NEGATIVE ("never archived", PDF-sources survey §M)
    has a 2025-12-06 capture whose id_ fetch is a 188-page PDF (7,689,961 bytes). Its body is not in the repository,
    so a replay of it fails CLOSED — a named miss, never the network."""
    from litkb import cassette as CAS
    from litkb.acquire import wayback

    by = {("avail" if "/wayback/available" in e["key"]["url"] else "capture"): e
          for e in C2C.recorded_entries(C2C.ROW_IIASA)}
    snap = wayback.parse_availability(base64.b64decode(by["avail"]["response"]["body"]["inline_b64"]))
    assert snap == {"timestamp": C2C.IIASA_CAPTURE_TS, "status": "200", "url": snap["url"]}
    cap = by["capture"]["response"]
    assert (cap["status"], cap["headers"].get("Content-Type"), cap["body"]["length"], cap["body"]["sha256"]) == (
        200, "application/pdf", 7689961, C2C.IIASA_PDF_SHA256)
    client, cas = C2C.replay_client(C2C.ROW_IIASA)
    with pytest.raises(CAS.CassetteBodyMissing):
        wayback.fetch_wayback([C2C.IIASA_URL], client)
    assert cas.misses and "not in" in cas.misses[-1]["why"]


# ── E1 on CONSTRUCTED answers ───────────────────────────────────────────────────────────────

def test_a_never_archived_url_is_blocked_not_found():
    """CONSTRUCTED: availability `{}`, CDX `[]` -> `blocked` / `not_found`, not retriable, nothing fetched."""
    from litkb.acquire import wayback

    stub = C2C.constructed_never_archived()
    r = wayback.fetch_wayback([C2C.CONSTRUCTED_DEAD_URL], stub)
    assert (r["status"], r["sub_status"], r["retriable"], r["http_codes"]) == ("blocked", "not_found", False, [200, 200])
    assert [u.split("?")[0] for u in stub.calls] == [wayback.AVAILABILITY, wayback.CDX]


def test_a_wrapper_page_is_kept_as_bad_file_and_never_landed():
    """CONSTRUCTED wrapper (the survey's claim) at the bare capture URL: with no raw modifier the rung hands the page
    back as `rejected` (the ladder keeps and types it); with the shipped modifiers the same world lands the REAL PDF."""
    from litkb.acquire import wayback

    r = wayback.fetch_wayback([C2C.CENSUS_URL], C2C.constructed_wrapper_client())
    assert r["status"] == "downloaded" and _sha(r["pdf"]) == C2C.CENSUS_PDF_SHA256
    saved = wayback.RAW_MODIFIERS
    wayback.RAW_MODIFIERS = ("",)
    try:
        r = wayback.fetch_wayback([C2C.CENSUS_URL], C2C.constructed_wrapper_client())
    finally:
        wayback.RAW_MODIFIERS = saved
    assert r["status"] == "bad-file" and r["rejected"] == C2C.CONSTRUCTED_WRAPPER and "pdf" not in r
    assert r["rejected_url"].endswith(f"/web/{C2C.CENSUS_CAPTURE_TS}/{C2C.CENSUS_URL}")


def test_if_is_tried_when_id_serves_no_pdf():
    """CONSTRUCTED: id_ answers 404, if_ serves the (REAL) PDF — "carry both" (survey §1 E1-CORRECTION)."""
    from litkb.acquire import wayback

    pdf = C2C.census_pdf()
    stub = C2C.StubClient({"wayback/available": _avail("20200101000000", url=C2C.CENSUS_URL),
                           "20200101000000id_/": (404, {}, b"not here"),
                           "20200101000000if_/": (200, {"Content-Type": "application/pdf"}, pdf)})
    r = wayback.fetch_wayback([C2C.CENSUS_URL], stub)
    assert r["status"] == "downloaded" and "if_/" in r["source_url"], r["tried"]


def test_cdx_is_asked_when_the_closest_capture_is_not_a_200_and_a_capture_is_never_fetched_twice():
    """CONSTRUCTED: the closest capture archived a 302; CDX lists two PDF captures, the newer one first."""
    from litkb.acquire import wayback

    pdf = C2C.census_pdf()
    stub = C2C.StubClient({"wayback/available": _avail("20190101000000", status="302", url=C2C.CENSUS_URL),
                           "/cdx/search/cdx": _cdx("20150101000000", "20180101000000"),
                           "20180101000000id_/": (200, {"Content-Type": "application/pdf"}, pdf)})
    r = wayback.fetch_wayback([C2C.CENSUS_URL], stub)
    assert r["status"] == "downloaded" and "20180101000000id_/" in r["source_url"], r["tried"]
    assert not any("20190101000000" in u and "/web/" in u for u in stub.calls), "a 302 capture was fetched"
    stub2 = C2C.StubClient({"wayback/available": _avail("20180101000000", url=C2C.CENSUS_URL),
                            "/cdx/search/cdx": _cdx("20180101000000")})
    r2 = wayback.fetch_wayback([C2C.CENSUS_URL], stub2)
    fetched = [u for u in stub2.calls if "/web/20180101000000" in u]
    assert len(fetched) == len(wayback.RAW_MODIFIERS), fetched
    # an INDEXED capture the archive would not serve (404) is no proof of absence (auditor-C2c-r2 F3)
    assert (r2["status"], r2.get("sub_status"), r2["retriable"]) == ("api-error", None, False), r2


def test_a_cdx_503_stops_the_rung_and_its_retry_after_reaches_the_ladder():
    """CONSTRUCTED: the survey's "CDX gave 503 ... back off hard" (CONTRACTS X7: honour Retry-After). The rung stops
    at the 503 (no capture asked after it), types it transient, and the terminal carries the header the ladder's
    one scheduled retry reads (litkb.acquire.backoff.retry_after_s)."""
    from litkb.acquire import backoff, wayback

    stub = C2C.StubClient({"wayback/available": _avail(None),
                           "/cdx/search/cdx": (503, {"Retry-After": "40"}, b"busy")})
    r = wayback.fetch_wayback([C2C.CENSUS_URL, "https://y.example/q.pdf"], stub)
    assert (r["status"], r["retriable"], r["http_codes"]) == ("api-error", True, [200, 503])
    assert len(stub.calls) == 2, "the rung went on asking after a 503"
    assert backoff.retry_after_s(r["terminal"]["headers"]) == 40.0
    assert backoff.classify(r["status"], r["http_codes"]) == "transient"


def test_a_policy_that_refuses_every_host_is_a_skip_and_asks_nothing():
    from litkb.acquire import policy as P
    from litkb.acquire import wayback

    stub = C2C.StubClient({})

    def refuse(host):
        return P.PolicyDecision("wayback", host, "", False, "CONSTRUCTED refusal")
    r = wayback.fetch_wayback([C2C.CENSUS_URL], stub, decide=refuse)
    # "asked nothing" first, and `.get`: a rung that went on to ask answers with no sub-status at all, and that must
    # read as the worse answer it is, never a KeyError inside the test (auditor-C2c round 3 F7; integrator-w2)
    assert stub.calls == [] and (r["status"], r.get("sub_status")) == ("skipped", "policy_refused"), (r, stub.calls)


def _refuse(route):
    from litkb.acquire import policy as P

    return lambda host: P.PolicyDecision(route, host, "", False, "CONSTRUCTED refusal")


def test_ia_and_commoncrawl_ask_nothing_when_the_policy_refuses_their_hosts():
    from litkb.acquire import commoncrawl, ia

    stub = C2C.StubClient({})
    r = ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub, decide=_refuse("ia"))
    assert (stub.calls, r["status"], r.get("sub_status")) == ([], "skipped", "policy_refused"), r   # (F7, as above)
    stub = C2C.StubClient({})
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], stub, decide=_refuse("commoncrawl"))
    assert (stub.calls, r["status"], r.get("sub_status")) == ([], "skipped", "policy_refused"), r


def test_a_c2c_fire_refuses_a_database_that_is_not_a_worker():
    class _Info:
        dbname = "litkb"

    class _Conn:
        info = _Info()
    with pytest.raises(RuntimeError, match="worker database"):
        C2C.World(_Conn(), ".")


# ── E3 ──────────────────────────────────────────────────────────────────────────────────────

def test_the_recorded_ia_search_finds_no_item_for_the_census_rows_doi():
    """REAL: one advancedsearch request (DOI as external-identifier OR title phrase AND creator), 0 hits."""
    from litkb.acquire import ia

    client, cas = C2C.replay_client(C2C.ROW_IA)
    r = ia.fetch_ia(C2C.CENSUS_ROW_WORK, client)
    assert (r["status"], r["sub_status"], r["tried"]) == ("not-in-archive", "not_in_corpus", ["search:200"])
    assert cas.misses == []


def _ia_world(meta, download=None, hits=None):
    """CONSTRUCTED: an item search answering one hit that carries the work's DOI, its metadata, and a download."""
    from litkb.acquire import ia

    hits = hits if hits is not None else [{"identifier": "constructed-item", "title": "Something else",
                                           "external-identifier": [f"urn:doi:{C2C.CENSUS_DOI}"]}]
    routes = {ia.SEARCH: _json({"response": {"numFound": len(hits), "docs": hits}}),
              "/metadata/constructed-item": _json(meta)}
    if download is not None:
        routes["/download/constructed-item/"] = download
    return C2C.StubClient(routes)


def test_a_dark_item_is_never_downloaded():
    from litkb.acquire import ia

    stub = _ia_world({"is_dark": True, "metadata": {}, "files": [{"name": "x.pdf", "source": "original"}]},
                     download=(200, {}, C2C.census_pdf()))
    r = ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub)
    assert not any("/download/" in u for u in stub.calls), stub.calls
    assert (r["status"], r.get("sub_status")) == ("not-in-archive", "not_in_corpus"), r


@pytest.mark.parametrize("md", [{"access-restricted-item": "true"}, {"collection": ["inlibrary", "texts"]},
                                {"collection": "printdisabled"}])
def test_a_lending_restricted_item_is_blocked_and_never_downloaded(md):
    from litkb.acquire import ia

    stub = _ia_world({"metadata": md, "files": [{"name": "x.pdf", "source": "original"}]},
                     download=(200, {}, C2C.census_pdf()))
    r = ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub)
    # "never downloaded" first, and `.get` (auditor-C2c round 3 F7; integrator-w2)
    assert not any("/download/" in u for u in stub.calls), stub.calls
    assert (r["status"], r.get("sub_status")) == ("blocked", "identity_required"), r


def test_an_open_item_serves_its_original_pdf_and_skips_a_private_file():
    from litkb.acquire import ia

    # "0 private.pdf" sorts before "Scan 1.pdf": without the `private` filter it is the file downloaded (auditor-C2c-r2
    # F5 N1: "a_private.pdf" sorted after it, so the filter was never load-bearing)
    files = [{"name": "0 private.pdf", "source": "original", "private": "true"},
             {"name": "derived.pdf", "source": "derivative"}, {"name": "Scan 1.pdf", "source": "original"}]
    stub = _ia_world({"metadata": {"collection": ["texts"]}, "files": files},
                     download=(200, {"Content-Type": "application/pdf"}, C2C.census_pdf()))
    r = ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub)
    assert r["status"] == "downloaded" and r["source_url"].endswith("/constructed-item/Scan%201.pdf"), r
    assert stub.calls[1].endswith("/metadata/constructed-item"), "metadata must be read before any download"


def test_an_item_is_opened_only_when_it_is_the_work():
    """Identity before any item request: the DOI, or the title AND the first author; a namesake is never opened."""
    from litkb.acquire import ia

    w = dict(C2C.CENSUS_ROW_WORK)
    assert ia.identified({"external-identifier": [f"urn:doi:{w['doi'].upper()}"]}, w) == "doi"
    assert ia.identified({"title": "Matching and Record Linkage", "creator": ["Winkler, William E."]}, w) \
        == "title+creator"
    assert ia.identified({"title": "Matching and Record Linkage", "creator": ["Someone, Else"]}, w) == ""
    assert ia.identified({"title": "Matching and record linkage revisited", "creator": "Winkler"}, w) == ""
    stub = _ia_world({}, hits=[{"identifier": "constructed-item", "title": "Another report", "creator": "Winkler"}])
    r = ia.fetch_ia(w, stub)
    assert r["status"] == "not-in-archive" and len(stub.calls) == 1, stub.calls


# ── E5 ──────────────────────────────────────────────────────────────────────────────────────

def test_the_recorded_commoncrawl_index_has_no_capture_of_the_census_url():
    """REAL: the crawl list (128 crawls) and ONE index query of the newest crawl: 404 "No Captures found"."""
    from litkb.acquire import commoncrawl

    client, cas = C2C.replay_client(C2C.ROW_COMMONCRAWL)
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], client, indexes_asked=1)
    assert (r["status"], r["sub_status"]) == ("not-in-archive", "not_in_corpus"), r
    assert r["tried"] == ["collinfo:200", "index CC-MAIN-2026-39-index:404"] and cas.misses == []


def _warc(payload, *, http_headers=b"Content-Type: application/pdf", truncated=None, status=b"200 OK"):
    """CONSTRUCTED: one gzip member holding one WARC `response` record (the Common Crawl layout)."""
    http = b"HTTP/1.1 " + status + b"\r\n" + http_headers + b"\r\n\r\n" + payload
    head = [b"WARC/1.0", b"WARC-Type: response", b"WARC-Target-URI: " + C2C.CENSUS_URL.encode(),
            b"Content-Type: application/http; msgtype=response", b"Content-Length: " + str(len(http)).encode()]
    if truncated:
        head.append(b"WARC-Truncated: " + truncated)
    return gzip.compress(b"\r\n".join(head) + b"\r\n\r\n" + http + b"\r\n\r\n")


def _cc_world(record_bytes, *, status=206, body=None, mime="application/pdf", archived="200"):
    """CONSTRUCTED: a crawl list of one crawl, an index row (archived status `archived`) pointing at `record_bytes`
    at offset 1000, and a data host answering the byte range."""
    rec = {"url": C2C.CENSUS_URL, "mime": mime, "status": archived, "filename": "crawl-data/CONSTRUCTED/x.warc.gz",
           "offset": "1000", "length": str(len(record_bytes)), "timestamp": "20200101000000"}
    return C2C.StubClient({
        "collinfo.json": _json([{"id": "CC-CONSTRUCTED", "cdx-api": "https://index.commoncrawl.org/CC-CONSTRUCTED-index"}]),
        "CC-CONSTRUCTED-index": (200, {}, json.dumps(rec).encode() + b"\n"),
        "data.commoncrawl.org/": (status, {}, record_bytes if body is None else body)})


class _RangeRecorder(C2C.StubClient):
    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.headers = getattr(self, "headers", []) + [headers]
        return super().get(url, accept, timeout, follow, data, headers)


def test_a_warc_record_by_byte_range_yields_its_pdf():
    """CONSTRUCTED WARC envelope around the REAL census PDF: the range asked is exactly offset..offset+length-1."""
    from litkb.acquire import commoncrawl

    pdf = C2C.census_pdf()
    rec = _warc(pdf)
    stub = _cc_world(rec)
    stub.__class__ = _RangeRecorder
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], stub, indexes_asked=1)
    assert r["status"] == "downloaded" and _sha(r["pdf"]) == C2C.CENSUS_PDF_SHA256, r
    assert stub.headers[-1] == {"Range": f"bytes=1000-{1000 + len(rec) - 1}"}


@pytest.mark.parametrize("status,cut", [(200, 0), (206, 7)])
def test_a_range_the_server_ignored_or_cut_short_is_never_decoded(status, cut):
    from litkb.acquire import commoncrawl

    rec = _warc(C2C.census_pdf())
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], _cc_world(rec, status=status, body=rec[:len(rec) - cut]),
                                      indexes_asked=1)
    assert r["status"] == "api-error" and "pdf" not in r, r
    assert r["retriable"] is (status == 206)


def test_a_truncated_warc_payload_is_kept_as_bad_file_never_offered_whole():
    from litkb.acquire import commoncrawl

    pdf = C2C.census_pdf()
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], _cc_world(_warc(pdf[:60000], truncated=b"length")),
                                      indexes_asked=1)
    assert r["status"] == "bad-file" and r["rejected"] == pdf[:60000] and "truncated" in r["detail"], r


def test_a_chunked_and_gzipped_payload_is_decoded():
    from litkb.acquire import commoncrawl

    pdf = C2C.census_pdf()
    z = gzip.compress(pdf)
    chunked = b"".join(f"{len(z[i:i + 4096]):x}\r\n".encode() + z[i:i + 4096] + b"\r\n"
                       for i in range(0, len(z), 4096)) + b"0\r\n\r\n"
    rec = _warc(chunked, http_headers=b"Content-Type: application/pdf\r\nTransfer-Encoding: chunked\r\n"
                                      b"Content-Encoding: gzip")
    w = commoncrawl.parse_warc_record(rec)
    assert w["payload"] == pdf and w["status"] == 200


def test_a_warc_block_shorter_than_its_content_length_is_never_decoded():
    """CONSTRUCTED: a plain (not chunked) record cut 4,000 bytes short of its declared Content-Length."""
    from litkb.acquire import commoncrawl

    cut = gzip.compress(gzip.decompress(_warc(C2C.census_pdf()))[:-4000])
    with pytest.raises(ValueError, match="bytes of a declared"):
        commoncrawl.parse_warc_record(cut)


def test_the_crawl_list_is_read_once_per_client():
    from litkb.acquire import commoncrawl

    stub = _cc_world(_warc(b"<html>not a pdf</html>"), mime="text/html")
    commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL, "https://y.example/q.pdf"], stub, indexes_asked=1)
    commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], stub, indexes_asked=1)
    assert sum(1 for u in stub.calls if u.endswith("collinfo.json")) == 1, stub.calls
    assert not any("data.commoncrawl.org" in u for u in stub.calls), "a non-PDF capture was fetched"


# ── X7: a planted secret never reaches the recording ────────────────────────────────────────

class _Echo:
    """A loopback server whose every answer ECHOES a planted secret (a hostile server). Its answers keep each API's
    own shape — availability an object with no capture, CDX a header row alone — so E1 reads them as a proven
    absence and records both."""

    def __init__(self, secret):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                shape = ([["urlkey", "timestamp", secret]] if self.path.startswith("/cdx/")
                         else {"archived_snapshots": {}, "echo": secret})
                body = json.dumps(shape).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Echo", secret)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_a_planted_secret_never_reaches_the_stage_e_recording(tmp_path, monkeypatch):
    """CONTRACTS X7 ("a test must prove a planted secret never reaches the index"), through Stage E's own path: a
    candidate URL carrying the secret is never asked at all (`recovery.eligible`), and a server that echoes it in
    its body and headers is recorded with the secret masked."""
    from litkb import cassette as CAS
    from litkb.acquire import recovery, wayback
    from litkb.netutil import Client, add_secret

    secret = f"PLANTEDc2cSECRET{uuid.uuid4().hex}"
    add_secret(secret)
    srv = _Echo(secret)
    try:
        monkeypatch.setattr(wayback, "AVAILABILITY", srv.base + "/wayback/available")
        monkeypatch.setattr(wayback, "CDX", srv.base + "/cdx/search/cdx")
        idx = tmp_path / "cas" / "index.jsonl"
        cas = CAS.Cassette(idx, "record", bodies=tmp_path / "bodies")
        urls, refused = recovery.candidates([{"url": f"https://oa.example/p.pdf?token={secret}"},
                                             {"url": f"https://oa.example/{secret}.pdf"},
                                             {"url": "https://oa.example/plain.pdf"}])
        assert urls == ["https://oa.example/plain.pdf"] and len(refused) == 2
        r = wayback.fetch_wayback(urls, Client(base="", cassette=cas))
        assert r["status"] == "blocked" and len(cas.recorded) == 2
    finally:
        srv.close()
    raw = idx.read_bytes()
    assert secret.encode() not in raw
    for ln in raw.splitlines()[1:]:
        resp = json.loads(ln)["response"]
        assert resp["headers"].get("X-Echo") == "<KEY>", resp["headers"]
        assert secret.encode() not in base64.b64decode(resp["body"].get("inline_b64", "")), "the body kept it"


# ── through the LADDER, on a worker database ────────────────────────────────────────────────

@pytest.fixture
def world(litkb_pg_base, tmp_path):
    _psycopg, conn, _ran = litkb_pg_base
    w = C2C.World(conn, tmp_path)
    yield w
    w.close()


def _manifest(w, since, ws):
    return {"frozen_at": since, "run_workstream_ids": [str(ws)]}


@pg_only
def test_the_recorded_census_capture_is_measured_through_the_ladder(world):
    """REAL answers, the ladder in MEASURE mode (D9): for a CONSTRUCTED admission, a dead link the ledger holds
    (CONSTRUCTED stand-in for Stage B's 404) -> the E1 rung -> THE acceptance test -> `measured`; the counters read
    it: the row converted, E1 asked once and hit once. The acceptance test judges BYTES, not identity — the
    wrong-work assertion at the end is what that means for the census row (auditor-C2c-r2 F1)."""
    since = world.owner.execute("SELECT clock_timestamp()").fetchone()[0]
    ws = world.ws("census-measured")
    work = world.work(ws)
    world.dead_link(ws, work, C2C.CENSUS_URL)
    client, cas = C2C.replay_client(C2C.ROW_CENSUS)
    out = world.ladder(ws, work, {"wayback": client}, routes=("wayback",))
    (status, sub, detail), = C2C._rows(world.owner, work["work_id"])
    assert (out["outcome"], status, sub) == ("measured", "measured", None), (out, detail)
    assert detail["acceptance"]["verdict"] == "accept" and detail["sha256"] == C2C.CENSUS_PDF_SHA256, detail
    assert C2C.CENSUS_URL in detail["detail"] and cas.misses == []
    m = _manifest(world, since, ws)
    assert C2C.wayback_rows_unconverted(world.owner, {"wayback_positive_dois": [work["doi"]]}) == 0
    assert (C2C.REPORTED["rung_asked_wayback"](world.owner, m), C2C.REPORTED["rung_conversions_wayback"](world.owner, m)) \
        == (1, 1)
    # MEASURE mode judged the bytes and no identity: had this row been graded wrong-work (as the census row is for
    # 10.1002/wics.1317), the same `measured` row is the false conversion `wayback_wrong_work_counted` names
    assert C2C.wayback_wrong_work_counted(world.owner, {"wayback_wrong_work_dois": [work["doi"]]}) == 1
    assert C2C.wayback_wrong_work_counted(world.owner, {"wayback_wrong_work_dois": ["10.5555/c2c-never-admitted"]}) == 0
    assert world.store.root.exists() is False or not any(world.store.root.rglob("*.pdf")), "measure mode landed bytes"


@pg_only
def test_a_dead_link_met_in_this_run_reaches_stage_e(world, monkeypatch):
    """The in-run seam (`run._record_result` -> `recovery.urls_of`): Unpaywall (a CONSTRUCTED stub answer) names the
    census.gov URL, the URL answers 404 in this run (CONSTRUCTED), and E1 is asked about it in the SAME pass (the REAL
    recorded capture). No ledger row names the URL beforehand."""
    from litkb.acquire import open_access

    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "c2c-test@example.invalid")
    ws = world.ws("in-run")
    work = world.work(ws)
    oa = C2C.StubClient({"api.unpaywall.org": _json({"is_oa": True, "oa_locations": [{"url": C2C.CENSUS_URL}]}),
                         "www.census.gov": (404, {"Content-Type": "text/html"}, b"<html>Page Not Found</html>")})
    client, _cas = C2C.replay_client(C2C.ROW_CENSUS)
    world.ladder(ws, work, {"open_access": oa, "wayback": client}, routes=("open_access", "wayback"))
    (status, _sub, detail), = C2C._rows(world.owner, work["work_id"])
    assert status == "measured" and C2C.CENSUS_URL in detail["detail"], detail


@pg_only
def test_a_stage_e_rung_with_no_dead_url_is_a_named_skip(world):
    ws = world.ws("no-url")
    work = world.work(ws)
    world.ladder(ws, work, {}, routes=("wayback", "commoncrawl"), mode="acquire")
    rows = [(r[0], r[1]) for r in C2C._rows(world.owner, work["work_id"])] + \
        [(r[0], r[1]) for r in C2C._rows(world.owner, work["work_id"], "commoncrawl")]
    assert rows == [("skipped", "no_identifier")] * 2, rows
    (_s, _sub, detail), = C2C._rows(world.owner, work["work_id"])
    assert "no dead document URL" in detail["detail"], detail


@pg_only
def test_the_recorded_census_capture_lands_and_binds_as_its_own_work_in_acquire_mode(world, litkb_pg_base):
    """REAL bytes through the whole acquire path: a CONSTRUCTED admission carrying the census capture's OWN
    identity (`CENSUS_CAPTURE_IDENTITY`: "Matching and Record Linkage", Winkler, 1993 — a salted DOI) LANDS the
    archived census.gov PDF through the acceptance test and the bind. It is NOT an admission of 10.1002/wics.1317:
    that DOI is the 2014 overview, another work (auditor-C2c-r2 F1; this test used to pin that wrong-work bind as
    success). The database is reset afterwards: `litkb._title_duplicates` is global (brief-COMMON rule 5)."""
    import shutil

    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext is not installed: binding cannot read a first page")
    from litkb.db import migrate

    ident = C2C.CENSUS_CAPTURE_IDENTITY
    try:
        ws = world.ws("lands")
        work = world.work(ws, title=ident["title"], author=ident["first_author"], year=ident["year"])
        assert (work.get("title"), work.get("year")) == (ident["title"], 1993), work
        world.dead_link(ws, work, C2C.CENSUS_URL)
        client, _cas = C2C.replay_client(C2C.ROW_CENSUS)
        out = world.ladder(ws, work, {"wayback": client}, routes=("wayback",), mode="acquire")
        (status, _sub, detail), = C2C._rows(world.owner, work["work_id"])
        assert (out["outcome"], status) == ("ok", "ok"), detail
        assert detail["binding"]["verdict"] == "bound" and detail["filed"].endswith(".pdf"), detail
    finally:
        _psycopg, conn, _ran = litkb_pg_base
        migrate.reset(conn)
        migrate.apply(conn)


@pg_only
@pytest.mark.parametrize("name", sorted(C2C.FIRES))
def test_every_c2c_fire_holds_its_bound_on_control_and_breaks_it_on_the_known_bad(world, name, tmp_path):
    """The FIRES the harness re-fires cold (`litkb_acceptance.py hardening --fire`), run as tests: control inside the
    bound, known-bad outside it."""
    A = _load("_litkb_acceptance_for_c2c", INSTR / "litkb_acceptance.py")
    spec = C2C.FIRES[name]
    got = {arm: int(spec["run"](world.owner, arm, tmp_path / arm)) for arm in ("control", "known_bad")}
    assert A._bound_ok(got["control"], spec["bound"]) and not A._bound_ok(got["known_bad"], spec["bound"]), got


def test_hardening_loads_the_c2c_module_and_every_fire_has_a_bound():
    A = _load("_litkb_acceptance_for_c2c_load", INSTR / "litkb_acceptance.py")
    mods = A._hardening_modules()
    assert ("litkb_hardening_c2c", str(INSTR / "litkb_hardening_c2c.py")) in mods["loaded"], mods["failed"]
    mine = {n for n, (_f, stem) in mods["reported"].items() if stem == "litkb_hardening_c2c"}
    assert {"wayback_rows_unconverted", "wayback_negatives_mistyped", "rung_conversions_wayback",
            "rung_conversions_ia", "rung_conversions_commoncrawl"} <= mine
    for name, (spec, stem) in mods["fires"].items():
        if stem == "litkb_hardening_c2c":
            assert spec.get("bound") and spec["counter"] in mine, name


@pg_only
def test_every_c2c_counter_reads_a_value(world):
    since = world.owner.execute("SELECT clock_timestamp()").fetchone()[0]
    ws = world.ws("counters")
    m = _manifest(world, since, ws)
    for name, fn in C2C.REPORTED.items():
        assert isinstance(fn(world.owner, m), int), name
    # the graded rows on a worker database, which admits none of them: the IIASA positive is unconverted, E1 has no
    # negative row (fail closed: 1), and no wrong-work row holds a hit
    assert C2C.wayback_rows_unconverted(world.owner, m) == 1, "the graded positive holds no wayback hit on a worker db"
    assert C2C.wayback_negatives_mistyped(world.owner, m) == 1
    assert C2C.wayback_wrong_work_counted(world.owner, m) == 0


# ── round 3: the plan's E1 rows re-graded against the recorded truth (auditor-C2c-r2 F1, F2) ──

def test_the_census_capture_is_another_work_than_the_doi_the_plan_names_it_for():
    """MEASURED on the tracked body (REAL): the census capture is Winkler's U.S. Bureau of the Census paper — 38
    pages, "This chapter ...", nothing cited after 1993 — while live holds 10.1002/wics.1317 as the 2014 WIREs
    overview (13 pages, another sha; read as litkb_reader, `WICS_1317_HELD_*`). The grades follow from it: census
    `wrong-work`, IIASA `positive`, and NO negative row. A re-grade by hand that drops this evidence turns this red."""
    import re

    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(C2C.census_pdf())
    try:
        pages = len(doc)
        first = doc[0].get_textpage().get_text_range()
        text = " ".join(doc[i].get_textpage().get_text_range() for i in range(pages))
    finally:
        doc.close()
    assert pages == C2C.CENSUS_CAPTURE_PAGES == 38 and pages != C2C.WICS_1317_HELD_PAGES
    assert "U.S. Bureau of the Census" in first and "This chapter" in first, first[:300]
    years = [int(y) for y in re.findall(r"\b(19[4-9]\d|20[0-2]\d)[ab]?\b", text)]
    assert max(years) == C2C.CENSUS_CAPTURE_IDENTITY["year"] == 1993, sorted(set(years))[-5:]
    assert C2C.CENSUS_PDF_SHA256 != C2C.WICS_1317_HELD_SHA256
    grades = {r[0]: (r[2], r[3]) for r in C2C.WAYBACK_ROWS}
    assert grades == {C2C.CENSUS_DOI: ("positive", "wrong-work"), C2C.IIASA_DOI: ("negative", "positive")}
    assert (C2C.WAYBACK_POSITIVE_DOIS, C2C.WAYBACK_NEGATIVE_DOIS, C2C.WAYBACK_WRONG_WORK_DOIS) == (
        (C2C.IIASA_DOI,), (), (C2C.CENSUS_DOI,))


def test_an_empty_row_list_is_never_a_pass():
    """Fail closed: no positive row, or no negative row, reads 1 — and says why — without asking the database."""
    assert C2C.wayback_rows_unconverted(None, {"wayback_positive_dois": []}) == 1
    assert C2C.wayback_negatives_mistyped(None, {"wayback_negative_dois": []}) == 1
    assert C2C.wayback_negatives_mistyped(None, {}) == 1, "the re-grade leaves E1 no negative row"
    assert C2C.wayback_wrong_work_counted(None, {"wayback_wrong_work_dois": []}) == 0
    (line,) = C2C.DETAILS["wayback_negatives_mistyped"](None, {})
    assert line.startswith("no real NEGATIVE row"), line
    assert C2C.DETAILS["wayback_rows_unconverted"](None, {"wayback_positive_dois": []}) == ["no Wayback POSITIVE row"]


# ── round 3: E1 books `not_found` only on a PROVEN absence (auditor-C2c-r2 F3) ─────────────────

_FORBIDDEN = (403, {"Content-Type": "text/html"}, b"<html><body>Forbidden</body></html>")
_PAGE = (200, {"Content-Type": "text/html"}, b"<html><body>an error page</body></html>")


@pytest.mark.parametrize("case", ["availability 403 and cdx 403", "cdx 403", "availability page",
                                  "cdx page", "indexed capture 404"])
def test_an_answer_that_is_not_an_absence_is_never_booked_not_found(case):
    """CONSTRUCTED: `not_found` says "never archived" and is what grades E1's negative, so an archive that REFUSED this
    client, answered something that is not its API's answer, or indexed a capture it would not serve is an
    `api-error`, not retriable — never `blocked/not_found`."""
    from litkb.acquire import wayback

    routes = {
        "availability 403 and cdx 403": {"wayback/available": _FORBIDDEN, "/cdx/search/cdx": _FORBIDDEN},
        "cdx 403": {"wayback/available": _avail(None), "/cdx/search/cdx": _FORBIDDEN},
        "availability page": {"wayback/available": _PAGE, "/cdx/search/cdx": _json([])},
        "cdx page": {"wayback/available": _avail(None), "/cdx/search/cdx": _PAGE},
        "indexed capture 404": {"wayback/available": _avail(None), "/cdx/search/cdx": _cdx("20180101000000")},
    }[case]
    r = wayback.fetch_wayback([C2C.CENSUS_URL], C2C.StubClient(routes))
    assert (r["status"], r.get("sub_status"), r["retriable"]) == ("api-error", None, False), r
    assert "do not prove" in r["detail"] and C2C.CENSUS_URL in r["detail"], r["detail"]


@pytest.mark.parametrize("cdx_body", [b"[]", b"", b'[["urlkey", "timestamp", "original"]]'])
def test_a_proven_absence_is_blocked_not_found_whichever_no_row_shape_cdx_sends(cdx_body):
    """CONSTRUCTED: availability `{}` plus a CDX answer with no capture row — `[]`, an empty body or a header row
    alone; which one the live server sends was never recorded — is the proof `not_found` needs."""
    from litkb.acquire import wayback

    stub = C2C.StubClient({"wayback/available": _avail(None),
                           "/cdx/search/cdx": (200, {"Content-Type": "application/json"}, cdx_body)})
    r = wayback.fetch_wayback([C2C.CONSTRUCTED_DEAD_URL], stub)
    assert (r["status"], r["sub_status"], r["retriable"]) == ("blocked", "not_found", False), r


def test_one_unproven_url_among_proven_ones_is_no_absence():
    """CONSTRUCTED: two candidates, the second one's availability answer a 403 — "no capture of ANY candidate" is
    then unproven, so the row is not `not_found`."""
    import urllib.parse

    from litkb.acquire import wayback

    def avail(url):
        return _FORBIDDEN if "b.example" in urllib.parse.unquote(url) else _avail(None)
    stub = C2C.StubClient({"wayback/available": avail, "/cdx/search/cdx": _json([])})
    r = wayback.fetch_wayback(["https://a.example/p.pdf", "https://b.example/q.pdf"], stub)
    assert (r["status"], r.get("sub_status")) == ("api-error", None), r
    assert "b.example" in r["detail"] and "a.example" not in r["detail"], r["detail"]


# ── round 3: X7's Retry-After on the availability and capture branches too (auditor-C2c-r2 F4) ──

def test_an_availability_503_stops_the_rung_and_its_retry_after_reaches_the_ladder():
    """CONSTRUCTED: a transient availability answer stops E1 at once — no CDX, no capture, no next URL — typed
    transient, with the header the ladder's one scheduled retry reads (litkb.acquire.backoff.retry_after_s)."""
    from litkb.acquire import backoff, wayback

    stub = C2C.StubClient({"wayback/available": (503, {"Retry-After": "40"}, b"busy")})
    r = wayback.fetch_wayback([C2C.CENSUS_URL, "https://y.example/q.pdf"], stub)
    assert (r["status"], r["retriable"], r["http_codes"]) == ("api-error", True, [503]), r
    assert len(stub.calls) == 1, "the rung went on asking after a 503"
    assert backoff.retry_after_s(r["terminal"]["headers"]) == 40.0
    assert backoff.classify(r["status"], r["http_codes"]) == "transient"


def test_a_capture_503_stops_the_rung_and_its_retry_after_reaches_the_ladder():
    """CONSTRUCTED: a transient answer to a CAPTURE stops E1 at once. Without that stop the 503 was walked past and
    the row ended as a permanent answer (auditor-C2c-r2 N4: `blocked/not_found`)."""
    from litkb.acquire import backoff, wayback

    stub = C2C.StubClient({"wayback/available": _avail("20200101000000", url=C2C.CENSUS_URL),
                           "20200101000000id_/": (503, {"Retry-After": "40"}, b"busy"),
                           "/cdx/search/cdx": _json([])})
    r = wayback.fetch_wayback([C2C.CENSUS_URL], stub)
    assert (r["status"], r["retriable"], r["http_codes"]) == ("api-error", True, [200, 503]), r
    assert len(stub.calls) == 2, "the rung went on asking after a 503"
    assert backoff.retry_after_s(r["terminal"]["headers"]) == 40.0


def test_at_most_captures_per_url_captures_are_fetched():
    """CONSTRUCTED (auditor-C2c-r2 F5 N7): CDX lists three PDF captures and none serves a file -> exactly
    `CAPTURES_PER_URL` (2) are fetched, newest first, each with every raw modifier."""
    from litkb.acquire import wayback

    stub = C2C.StubClient({"wayback/available": _avail(None),
                           "/cdx/search/cdx": _cdx("20150101000000", "20160101000000", "20170101000000")})
    r = wayback.fetch_wayback([C2C.CENSUS_URL], stub)
    caps = [u.split("/web/", 1)[1][:14] for u in stub.calls if "/web/" in u]
    assert sorted(set(caps)) == ["20160101000000", "20170101000000"] and wayback.CAPTURES_PER_URL == 2, stub.calls
    assert len(caps) == 2 * len(wayback.RAW_MODIFIERS) and r["status"] == "api-error", r


# ── round 3: the recovery candidates (auditor-C2c-r2 F5 N5, F10) ──────────────────────────────

def test_the_ledger_offers_only_urls_an_earlier_attempt_did_not_succeed_on():
    """(auditor-C2c-r2 F5 N5) A URL an earlier attempt SUCCEEDED on (`ok`, `measured`) is not dead and is never
    re-asked of the archives. A CONSTRUCTED ledger, read through a stand-in connection."""
    from litkb.acquire import recovery as R

    rows = [("open_access", "ok", "https://ok.example/p.pdf", None, None, None),
            ("open_access", "measured", None, "https://measured.example/p.pdf", None, None),
            ("open_access", "no-oa-copy", "https://dead.example/p.pdf", None, None, ["h:404"]),
            ("scihub", "blocked", "https://sci-hub.ru/10.1/x", None, None, None)]

    class _Cur:
        def fetchall(self):
            return rows

    class _Conn:
        def execute(self, sql, params):
            assert sql == R._LEDGER_SQL and params == ("W",)
            return _Cur()
    assert [x["url"] for x in R.ledger_urls(_Conn(), "W")] == ["https://dead.example/p.pdf"]


@pytest.mark.parametrize("url", [
    "https://bucket.s3.amazonaws.com/p.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc",
    "https://d1.cloudfront.net/p.pdf?Expires=1&Signature=abc&Key-Pair-Id=K",
    "https://acct.blob.core.windows.net/c/p.pdf?sv=2020-01-01&sig=abc",
    "https://storage.googleapis.com/b/p.pdf?X-Goog-Signature=abc",
])
def test_a_signed_url_is_never_a_recovery_candidate(url):
    """CONSTRUCTED signed URLs (auditor-C2c-r2 F10): their signature grants the object, so none is sent to an archive
    — none of them carries a `cassette.SCRUB_PARAMS` name, so only the signed-URL rule refuses them."""
    from litkb import cassette as CAS
    from litkb.acquire import recovery as R

    assert CAS.scrub_url(url) == url
    assert R.eligible(url) == (False, "a signed URL (its signature is a credential)")


# ── round 3: E3 typing (auditor-C2c-r2 F5 N9, F7) ─────────────────────────────────────────────

def test_an_identified_items_listed_pdf_that_answers_404_is_no_pdf_link():
    """CONSTRUCTED: the item is the work, its listed PDF is not served (404) -> `no_pdf_link`, not `not_in_corpus`
    (which says no item was identified)."""
    from litkb.acquire import ia

    stub = _ia_world({"metadata": {"collection": ["texts"]}, "files": [{"name": "x.pdf", "source": "original"}]},
                     download=(404, {}, b"not here"))
    r = ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub)
    assert (r["status"], r.get("sub_status")) == ("not-in-archive", "no_pdf_link"), r


@pytest.mark.parametrize("code,body,sub", [
    (401, b"", "identity_required"),
    (403, b"<html><head><title>Just a moment...</title></head></html>", "challenge_or_bot_check"),
    (403, b"<html><head><title>Forbidden</title></head><body>No access to this item.</body></html>",
     "identity_required"),
])
def test_a_refused_download_is_blocked_and_a_401_is_typed_apart_from_a_403(code, body, sub):
    """CONSTRUCTED (CONTRACTS X7 "do not treat 401 like 403"): the ledger's own rule types the refusing response —
    a 401 is `identity_required`; a 403 is read for a challenge signature first."""
    from litkb.acquire import ia

    stub = _ia_world({"metadata": {"collection": ["texts"]}, "files": [{"name": "x.pdf", "source": "original"}]},
                     download=(code, {"Content-Type": "text/html"}, body))
    r = ia.fetch_ia(C2C.CENSUS_ROW_WORK, stub)
    assert (r["status"], r.get("sub_status"), r["retriable"]) == ("blocked", sub, False), r
    assert r["terminal"]["status_code"] == code


# ── round 3: E5 (auditor-C2c-r2 F5 N2, N8, F6) ───────────────────────────────────────────────

def test_a_crawled_capture_that_is_not_an_archived_200_is_never_fetched():
    """CONSTRUCTED (auditor-C2c-r2 F5 N2): an index row whose ARCHIVED status is 404 — a crawled error page, even under
    a PDF MIME — is never byte-range fetched."""
    from litkb.acquire import commoncrawl

    stub = _cc_world(_warc(C2C.census_pdf()), archived="404")
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], stub, indexes_asked=1)
    assert (r["status"], r.get("sub_status")) == ("not-in-archive", "not_in_corpus"), r
    assert not any("data.commoncrawl.org" in u for u in stub.calls), stub.calls


def test_a_warc_record_that_is_not_a_response_is_never_decoded():
    """CONSTRUCTED (auditor-C2c-r2 F5 N8): a `resource` record at the indexed range is refused, not read as the page."""
    from litkb.acquire import commoncrawl

    rec = gzip.compress(gzip.decompress(_warc(C2C.census_pdf())).replace(b"WARC-Type: response",
                                                                          b"WARC-Type: resource", 1))
    with pytest.raises(ValueError, match="not a response"):
        commoncrawl.parse_warc_record(rec)


def test_a_truncated_gzip_payload_is_kept_as_served_and_never_decoded():
    """CONSTRUCTED (auditor-C2c-r2 F6): a crawler-truncated payload sent `Content-Encoding: gzip` used to raise
    EOFError out of the rung. It is kept as served (`bad-file`) and never decoded."""
    from litkb.acquire import commoncrawl

    z = gzip.compress(C2C.census_pdf())[:50000]
    rec = _warc(z, http_headers=b"Content-Type: application/pdf\r\nContent-Encoding: gzip", truncated=b"length")
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], _cc_world(rec), indexes_asked=1)
    assert r["status"] == "bad-file" and r["rejected"] == z and "truncated" in r["detail"], r


def test_a_payload_that_does_not_decode_is_an_api_error_never_an_exception():
    """CONSTRUCTED (auditor-C2c-r2 F6): a payload whose `Content-Encoding` lies is an `api-error` row, not an
    exception out of the rung."""
    from litkb.acquire import commoncrawl

    rec = _warc(b"these bytes are not gzip", http_headers=b"Content-Type: application/pdf\r\nContent-Encoding: gzip")
    r = commoncrawl.fetch_commoncrawl([C2C.CENSUS_URL], _cc_world(rec), indexes_asked=1)
    assert (r["status"], r["retriable"]) == ("api-error", False) and "does not decode" in r["detail"], r


def test_a_raw_deflate_payload_is_inflated():
    """CONSTRUCTED (auditor-C2c-r2 F6): `Content-Encoding: deflate` carrying a RAW deflate stream (no zlib header)."""
    import zlib

    from litkb.acquire import commoncrawl

    pdf = C2C.census_pdf()
    co = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = co.compress(pdf) + co.flush()
    w = commoncrawl.parse_warc_record(_warc(raw, http_headers=b"Content-Type: application/pdf\r\n"
                                                              b"Content-Encoding: deflate"))
    assert w["payload"] == pdf


# ── round 3: the negative counter reads the LATEST spent attempt (auditor-C2c-r2 F5 N6) ─────────

@pg_only
def test_the_negative_counter_reads_the_latest_spent_wayback_attempt(world):
    """CONSTRUCTED ledger rows on a worker database: an older `blocked/not_found` then a newer `measured` -> the row is
    mistyped (1); the other order -> 0."""
    from litkb.acquire import run

    ws = world.ws("latest")
    tok = world.tokens[ws]
    for rows, want in (((("blocked", "not_found"), ("measured", None)), 1),
                       ((("measured", None), ("blocked", "not_found")), 0)):
        work = world.work(ws)
        for st, sub in rows:
            run.record_attempt(world.writer, ws, tok, work["work_id"], "wayback", work["doi"], st,
                               {"detail": "CONSTRUCTED ledger row (c2c round 3, N6)"}, [200], sub_status=sub)
        assert C2C.wayback_negatives_mistyped(world.owner, {"wayback_negative_dois": [work["doi"]]}) == want, rows

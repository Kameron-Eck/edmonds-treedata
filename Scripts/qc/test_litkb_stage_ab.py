"""S4.5 builder C2a — Stage A (zero network) and Stage B (the metadata fan-out): LITKB_WORKPLAN.md "### S4.5"
items 3 and 4.

  Stage A      A0 flags, never deletes; A1 rejects, never coerces; A2 the work-class router refuses a shadow line
               for a preprint / book / HTML-only work BEFORE any request (and the ladder books the refusal as a
               `skipped/policy_refused` row); A3 the registrant prefixes; A4 the Atypon templates; A7 the offline
               EarthArXiv map; Wave 0 writes the certain derivations and holds the arXiv CANDIDATE for DataCite
  Stage B      the registry order is the wave order; every rung registers by import (S4.5 decision D19) with a
               policy line; B1 `carried_files`; B4's link[] filter; the candidate fetch's typed answers; the closure
               rule's skips and its pass cap; DataCite's returned-DOI guard; the harvest written through B1's one
               path on the attempt that read it, the contact email never reaching the ledger
  recorded     the REAL answers qc/instruments/litkb_stage_ab_record.py recorded under the brief's grant, replayed
               through builder A's cassette with no socket (the FREE-PDF rows' S2 answers, E13's, the OSF preprint's)
  counters     the two gated counters' refusals and definitions; the report lines in builder A's grammar
  fires        every FIRES entry of qc/instruments/litkb_hardening_c2a.py, control inside the bound and the known-bad
               outside it, each arm on a freshly reset worker database (the harness's protocol)

Every answer that is not a recording is CONSTRUCTED and its test says so. No test touches the network.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w6 py -3.12 -m pytest qc/test_litkb_stage_ab.py -q
"""
import base64
import csv
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
pg_only = pytest.mark.requires_litkb_pg


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C2A = _load("_litkb_hardening_c2a", SCRIPTS / "qc" / "instruments" / "litkb_hardening_c2a.py")
HA = _load("_litkb_hardening_a_for_c2a", SCRIPTS / "qc" / "instruments" / "litkb_hardening_a.py")
P2 = _load("_litkb_p2_for_c2a", SCRIPTS / "qc" / "test_litkb_p2.py")
EMAP = _load("_litkb_eartharxiv_map", SCRIPTS / "qc" / "instruments" / "litkb_eartharxiv_map.py")


@pytest.fixture(autouse=True)
def _no_email(monkeypatch):
    """No test reads Kam's configured email: the contact email is a constructed address."""
    from litkb.acquire import open_access
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "c2a-test@example.invalid")


class Ctx:
    """A CONSTRUCTED RungContext stand-in for the pure rung tests: clients by route, a pacer that never sleeps."""

    def __init__(self, clients=None):
        from litkb.netutil import Pacer
        self.clients = clients or {}
        self.pacer = Pacer(interval=0, sleep=lambda s: None)
        self.work_class = ""


class Stub:
    """Answers by URL fragment (CONSTRUCTED); an unknown URL is a 404. Records every URL and Accept asked."""
    base = ""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append((url, accept))
        for frag, resp in self.routes.items():
            if frag in url:
                return resp(url) if callable(resp) else resp
        return 404, {}, b""


def _json(obj, status=200):
    return status, {"Content-Type": "application/json"}, json.dumps(obj).encode()


def _pdf(title="A CONSTRUCTED paper", author="Tester"):
    return P2.paper_pdf(title, author)


def _recorded(row_doi, fragment):
    """The RECORDED answer body for `fragment` under the recording's row tag (the tracked cassette index)."""
    for line in C2A.CASSETTE_INDEX.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if "key" in e and e.get("row") == C2A.row_tag(row_doi).lower() and fragment in e["key"]["url"]:
            return json.loads(base64.b64decode(e["response"]["body"]["inline_b64"]))
    raise AssertionError(f"no recording for {row_doi} {fragment}")


# ── Stage A ──────────────────────────────────────────────────────────────────────────────────────
def test_the_work_class_router_classes_and_the_crossref_salvage():
    from litkb.acquire import stage_a as A

    assert A.work_class({"type": "article", "ids": [("doi", "10.1/x", "own")], "doi": "10.1/x"}) == "paper"
    assert A.work_class({"type": "proceedings"}) == "paper"
    assert A.work_class({"type": "preprint", "doi": "10.48550/arxiv.1"}) == "preprint"
    assert A.work_class({"type": "book"}) == "book"
    assert A.work_class({"type": "chapter"}) == "chapter"
    # a page a URL hunt admitted: a url and no work-level identifier
    assert A.work_class({"type": "report", "ids": [("url", "https://x.example/p", "own")]}) == "html-only"
    # survey A2's salvage (Codex X5): Crossref `other` + ISBN + container title is a book section
    assert A.crossref_class({"type": "other", "ISBN": ["9780387695020"], "container-title": ["C"]}) == "chapter"
    assert A.crossref_class({"type": "other"}) == ""
    assert A.crossref_class({"type": "posted-content"}) == "preprint"
    # a live answer only ever TIGHTENS the router
    assert A.tighten("paper", "preprint") == "preprint"
    assert A.tighten("preprint", "paper") == "preprint"


def test_the_router_refuses_every_shadow_line_for_a_routed_away_class_and_nothing_else():
    from litkb.acquire import policy as P
    from litkb.acquire import stage_a as A

    for cls in ("preprint", "book", "html-only"):
        for route in ("annas", "scihub", "bban"):
            d = A.routed(P.decide(route, shadow_enabled=True), cls)
            assert not d.allowed and "work-class router" in d.reason, (cls, route, d)
    for cls in ("paper", "chapter", "report", "thesis", ""):
        assert A.routed(P.decide("annas", shadow_enabled=True), cls).allowed
    # a legitimate line is never touched, whatever the class
    for route in ("open_access", "arxiv", "osf", "s2"):
        assert A.routed(P.decide(route), "preprint").allowed


def test_the_doi_prefix_router_names_the_registrant_s_native_api():
    from litkb.acquire import stage_a as A

    assert A.native_route("10.48550/arxiv.2104.08663") == ("arxiv", "arxiv")
    assert A.native_route("10.31235/osf.io/cxp4q") == ("osf", "osf")
    assert A.native_route("10.31223/x5ab12") == ("eartharxiv", "eartharxiv")
    assert A.native_route("10.5281/zenodo.123") == ("zenodo", "zenodo")
    assert A.native_route("10.1101/357798") == ("biorxiv", "")
    assert A.native_route("10.1016/j.rse.2020.1") == ("", "")


def test_a1_rejects_a_malformed_identifier_and_never_coerces_it():
    from litkb.acquire import stage_a as A

    kept, rejected = A.canonical_ids([("doi", "10.1016/J.RSE.2020.111723", "own"), ("isbn", "0-306-40615-3", "own"),
                                      ("pmcid", "7391", "own"), ("url", "https://x.example", "own")])
    assert ("doi", "10.1016/j.rse.2020.111723", "own") in kept
    assert ("pmcid", "PMC7391", "own") in kept
    assert [r["scheme"] for r in rejected] == ["isbn"]        # a bad check digit is refused, not re-derived


def test_wave_0_writes_only_the_certain_derivations_and_holds_the_arxiv_candidate():
    from litkb.acquire import stage_a as A

    write, cand, _ = A.derive([("doi", "10.48550/arxiv.2104.08663", "own")])
    assert [(r["scheme"], r["value"], r["asserted_by"]) for r in write] == [("arxiv", "2104.08663", "deterministic")]
    assert cand == []
    write, cand, _ = A.derive([("arxiv", "2206.01062", "own")])
    assert write == [] and [(c["value"], c["evidence"].get("candidate")) for c in cand] == [
        ("10.48550/arxiv.2206.01062", True)]
    write, _cand, _ = A.derive([("isbn", "0306406152", "own")])
    assert [(r["scheme"], r["value"]) for r in write] == [("isbn", "9780306406157")]
    # an identifier reached through an EDITION edge names another edition: nothing is derived from it
    assert A.derive([("doi", "10.48550/arxiv.2206.01062", "has_version")]) == ([], [], {})


def test_a0_flags_and_never_drops():
    from litkb.acquire import stage_a as A

    assert A.record_class(crossref={"update-to": [{"type": "retraction"}]}) == "retracted"
    assert A.record_class(crossref={"update-to": [{"type": "correction"}]}) == "correction"
    assert A.record_class(crossref={"type": "peer-review"}) == "not_an_article"
    assert A.record_class(openalex={"is_paratext": True}) == "paratext"
    assert A.record_class(work_type="article") == ""


def test_a4_builds_only_the_templates_stage_c_does_not():
    from litkb.acquire import stage_a as A

    assert A.publisher_urls("10.1080/01431161.2010.494184") == [
        "https://www.tandfonline.com/doi/pdf/10.1080/01431161.2010.494184"]
    assert A.publisher_urls("10.1145/3534678.3539043") == ["https://dl.acm.org/doi/pdf/10.1145/3534678.3539043"]
    for stage_c in ("10.1007/x", "10.3390/rs15030765", "10.1016/j.x", "10.1371/journal.pone.1", "10.5194/a-1-2-2020"):
        assert A.publisher_urls(stage_c) == []


def test_a7_reads_the_harvested_map_and_asks_nothing_without_one(tmp_path, monkeypatch):
    """CONSTRUCTED map rows (the harvester's columns)."""
    from litkb.acquire import stage_a as A

    monkeypatch.setenv("LITKB_EARTHARXIV_MAP", str(tmp_path / "absent.csv"))
    s = Stub({})
    r = A.rung_eartharxiv({"doi": "10.1029/2020gl000001", "ids": []}, Ctx({"eartharxiv": s}))
    assert r["status"] == "api-error" and r["retriable"] and s.calls == []
    m = tmp_path / "map.csv"
    with open(m, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(A.EARTHARXIV_COLUMNS))
        w.writeheader()
        w.writerow({"published_doi": "10.1029/2020GL000001", "preprint_doi": "10.31223/x5c01", "rights": "CC-BY",
                    "pdf_url": "https://eartharxiv.org/repository/object/1/download/2/", "oai_identifier": "oai:x",
                    "datestamp": "2021-01-01"})
    monkeypatch.setenv("LITKB_EARTHARXIV_MAP", str(m))
    s = Stub({"eartharxiv.org": (200, {}, _pdf())})
    r = A.rung_eartharxiv({"doi": "10.1029/2020gl000001", "ids": []}, Ctx({"eartharxiv": s}))
    assert r["status"] == "downloaded" and r["version"] == "submittedVersion"
    r = A.rung_eartharxiv({"doi": "10.1029/other", "ids": []}, Ctx({"eartharxiv": Stub({})}))
    assert r["status"] == "no-oa-copy"


def test_the_eartharxiv_harvester_parses_an_oai_page():
    """A CONSTRUCTED oai_dc ListRecords page (the OAI-PMH shape; the real feed is the orchestrator's live pass)."""
    page = b"""<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>
    <record><header><identifier>oai:eartharxiv.org:id:1</identifier><datestamp>2021-02-03</datestamp></header>
    <metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
      xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier>https://doi.org/10.31223/X5ABCD</dc:identifier>
    <dc:identifier>https://eartharxiv.org/repository/object/1/download/2/</dc:identifier>
    <dc:relation>https://doi.org/10.1029/2020GL000001</dc:relation><dc:rights>CC-BY</dc:rights></oai_dc:dc>
    </metadata></record>
    <record><header><identifier>oai:eartharxiv.org:id:2</identifier></header><metadata>
    <dc xmlns="http://purl.org/dc/elements/1.1/"><identifier>https://doi.org/10.31223/X5EF</identifier></dc>
    </metadata></record>
    <resumptionToken completeListSize="2">tok-2</resumptionToken></ListRecords></OAI-PMH>"""
    rows, token = EMAP.parse_page(page)
    assert token == "tok-2"
    assert [(r["published_doi"], r["preprint_doi"]) for r in rows] == [("10.1029/2020gl000001", "10.31223/x5abcd")]


# ── Stage B: the registry ────────────────────────────────────────────────────────────────────────
def test_every_stage_ab_rung_registers_by_importing_the_ladder_with_a_policy_line():
    """S4.5 decision D19: `import litkb.acquire.run` registers every rung (fail closed); each route is in the
    0033 vocabulary, staged, and named by a legitimate policy line."""
    import subprocess
    import sys

    code = ("from litkb.acquire import run as R\n"
            "print(','.join(r.route for r in R.RUNGS))\n")
    import os
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=dict(os.environ, PYTHONPATH=str(SCRIPTS / "pipeline")))
    assert out.returncode == 0, out.stderr
    got = out.stdout.strip().split(",")
    from litkb.acquire import policy as P
    from litkb.acquire import stage_b as B

    table = [t[0] for t in B.RUNG_TABLE]
    assert [r for r in got if r in table] == table
    for route in table:
        assert route in P.ROUTES_ALL and route in P.STAGE_OF
        d = P.decide(route)
        assert d.allowed and d.tier == P.LEGITIMATE, (route, d)
    # the wave order: the concurrent Wave-1 rungs, then Wave 2 in the closure rule's dependency order
    from litkb.acquire import run as R
    alone = [r.route for r in R.RUNGS if r.stage == "B" and not r.concurrent]
    assert alone == ["datacite", "zenodo", "figshare", "ncbi-idconv", "s2", "europepmc", "arxiv", "venue"]
    assert {r.route for r in R.RUNGS if r.metadata_only} == {"opencitations", "ncbi-idconv"}
    assert "core" not in got                                   # NOT BUILT: keyless CORE cannot be asked


# ── Stage B: B1 and the candidate fetch ──────────────────────────────────────────────────────────
def test_b1_follows_an_arxiv_id_and_a_real_open_access_pdf_but_never_a_doi_org_url():
    from litkb.acquire import stage_b as B

    got = B.carried_files(["1910.12077"], {"url": "https://hal.science/hal-1/document"})
    assert [u for u, _m in got] == ["https://arxiv.org/pdf/1910.12077", "https://hal.science/hal-1/document"]
    assert got[0][1]["version"] == "submittedVersion"
    # E13's REAL recorded S2 openAccessPdf is a doi.org URL: never a PDF (survey B1 guard)
    e13 = _recorded("10.1145/3534678.3539043", "semanticscholar")
    assert e13["openAccessPdf"]["url"].startswith("https://doi.org/")
    assert B.carried_files([], e13["openAccessPdf"]) == []
    # an arXiv openAccessPdf is its arXiv id's (asked by the arxiv rung, A10's canonicalisation)
    assert B.carried_files([], {"url": "http://arxiv.org/pdf/2103.07534"}) == []
    assert B.canon_arxiv("http://arxiv.org/pdf/2103.07534") == "2103.07534"


def test_the_candidate_fetch_types_every_answer_and_keeps_what_it_was_served():
    """CONSTRUCTED answers, one per outcome."""
    from litkb.acquire import stage_b as B

    pdf = _pdf()
    def run(resp, html_status="bad-file"):
        s = Stub({"x.example": resp})
        return B.fetch_candidates("doaj", [("https://x.example/f", {"version": "publishedVersion"})], Ctx({"doaj": s}),
                                  {}, html_status=html_status), s
    r, s = run((200, {}, pdf))
    assert r["status"] == "downloaded" and r["pdf"] == pdf and r["version"] == "publishedVersion"
    assert s.calls[0][1] == B.PDF_ACCEPT
    r, _ = run((0, {}, b"URLError: getaddrinfo failed"))
    assert r["status"] == "api-error" and r["retriable"] and "rejected" not in r
    page = b"<html><head><title>Just a moment...</title></head></html>"
    r, _ = run((403, {}, page))
    assert (r["status"], r["sub_status"], r["rejected"]) == ("blocked", "challenge_or_bot_check", page)
    landing = b"<html><head><title>An article</title></head><body>abstract</body></html>"
    r, _ = run((200, {}, landing))
    assert r["status"] == "bad-file" and r["rejected"] == landing and "sub_status" not in r
    r, _ = run((200, {}, landing), html_status="blocked")
    assert (r["status"], r["sub_status"]) == ("blocked", "html_or_reader")
    r, _ = run((403, {}, b"<html>no</html>"))
    assert r["status"] == "blocked" and "sub_status" not in r        # typed by the ladder: identity_required
    r, _ = run((404, {}, b""))
    assert (r["status"], r["sub_status"]) == ("blocked", "not_found")


def test_a_legitimate_rung_never_asks_a_shadow_host_or_one_url_twice_in_a_run():
    from litkb.acquire import stage_b as B

    s = Stub({"": (200, {}, _pdf())})
    work = {}
    r = B.fetch_candidates("openalex", [("https://sci-hub.ru/10.1/x", {}), ("https://annas-archive.gl/md5/1", {})],
                           Ctx({"openalex": s}), work)
    assert s.calls == [] and r["status"] == "no-oa-copy" and "shadow host" in r["detail"]
    B.fetch_candidates("openalex", [("https://oa.example/p.pdf", {})], Ctx({"openalex": s}), work)
    r = B.fetch_candidates("doaj", [("https://oa.example/p.pdf", {})], Ctx({"doaj": s}), work)
    assert len(s.calls) == 1 and "already asked" in r["detail"]


def test_b4_reads_link_pdfs_by_content_type_or_path_and_crossref_s_harvest_fields():
    """B4's filter on a CONSTRUCTED MDPI-shaped link[] (B4-RG: content type `unspecified`), then Kats_2019's REAL
    recorded Crossref message."""
    from litkb.acquire import stage_b as B

    msg = {"link": [{"URL": "https://www.mdpi.com/2072-4292/15/3/765/pdf", "content-type": "unspecified",
                     "intended-application": "similarity-checking"},
                    {"URL": "https://x.example/article.xml", "content-type": "text/xml"},
                    {"URL": "https://x.example/tdm", "content-type": "application/pdf", "content-version": "vor"}]}
    assert [u for u, _m in B.link_candidates(msg)] == ["https://www.mdpi.com/2072-4292/15/3/765/pdf",
                                                      "https://x.example/tdm"]
    kats = _recorded("10.1007/978-3-030-32248-9_57", "api.crossref.org")["message"]
    assert [u for u, _m in B.link_candidates(kats)] == [
        "https://link.springer.com/content/pdf/10.1007/978-3-030-32248-9_57"]


# ── Stage B: rungs on recorded and constructed answers ───────────────────────────────────────────
def test_the_s2_rung_on_recorded_answers_harvests_the_arxiv_edge_and_hands_the_id_to_b1():
    """Kats_2019 and E13, their REAL recorded S2 answers (replayed, no socket)."""
    from litkb.acquire import stage_b as B

    for row, doi, arx in (("kats", "10.1007/978-3-030-32248-9_57", "1910.12077"),
                          ("e13", "10.1145/3534678.3539043", "2206.01062")):
        client = C2A.ReplayClient(C2A.row_tag(doi))
        work = {"doi": doi, "ids": [("doi", doi, "own")]}
        r = B.rung_s2(work, Ctx({"s2": client}))
        C2A.no_misses(client)
        edges = [e for e in r["harvest"]["relations"] if e.get("state") == "asserted"]
        assert [(e["relation"], e["target_scheme"], e["target_value"]) for e in edges] == [
            ("has_version", "arxiv", arx)]
        assert ("arxiv", arx, "s2") in work["ids"]
        assert {x["scheme"] for x in r["harvest"]["rows"]} >= {"s2", "mag"} - ({"mag"} if row == "e13" else set())
        # the arXiv copy is B1's (the arxiv rung); S2 itself asked nothing but its record
        assert r["status"] == "no-oa-copy" and [c for c in client.calls if "semanticscholar" not in c] == []


def test_the_osf_rung_walks_the_recorded_two_hops_to_the_file():
    """DelgadoQuiros_2025's REAL recorded OSF answers; the file itself CONSTRUCTED (404)."""
    from litkb.acquire import stage_b_repos as R

    doi = "10.31235/osf.io/cxp4q"
    client = C2A.ReplayClient(C2A.row_tag(doi), stubs={"://osf.io/": (404, {}, b"")})
    r = R.rung_osf({"doi": doi, "ids": [("doi", doi, "own")]}, Ctx({"osf": client}))
    C2A.no_misses(client)
    assert r["http_codes"] == [200, 200, 404] and (r["status"], r["sub_status"]) == ("blocked", "not_found")
    assert any("osf.io/download" in u or "://osf.io/" in u for u in client.calls)
    assert R.osf_id("10.1016/j.x") == "" and R.osf_id(doi) == "cxp4q"


def test_the_metadata_parsers_on_constructed_answers():
    """OpenCitations META, the NCBI converter, Europe PMC, DOAJ, OpenAIRE, HAL, Zenodo, figshare — CONSTRUCTED
    answers in each service's documented shape (none of these hosts was in this builder's grant)."""
    from litkb.acquire import stage_b as B
    from litkb.acquire import stage_b_repos as R

    oc = B.from_opencitations([{"id": "doi:10.1/x omid:br/0612 openalex:W123 pmid:456"}], "10.1/x")
    assert [(r["scheme"], r["value"], r["asserted_by"]) for r in oc] == [("openalex", "W123", "opencitations"),
                                                                          ("pmid", "456", "opencitations")]
    # an `arxiv:` token on an ARTICLE's DOI names its preprint, another edition: never the article's own identifier
    # (auditor-C2a F2; litkb-sibling-edition — builder-B1's harvest.from_s2 makes it an edge)
    oc2 = B.from_opencitations([{"id": "doi:10.1145/3534678.3539043 arxiv:2206.01062 openalex:W4285219853"}],
                               "10.1145/3534678.3539043")
    assert [r["scheme"] for r in oc2] == ["openalex"]
    ic = B.from_idconv({"records": [{"doi": "10.1/x", "pmcid": "PMC77", "pmid": "88"}]}, "10.1/x")
    assert {(r["scheme"], r["value"]) for r in ic} == {("pmcid", "PMC77"), ("pmid", "88")}
    assert B.from_idconv({"records": [{"doi": "10.1/x", "status": "error", "errmsg": "not found"}]}, "10.1/x") == []
    res = {"pmid": "1", "pmcid": "PMC2", "hasPDF": "Y", "fullTextUrlList": {"fullTextUrl": [
        {"documentStyle": "pdf", "availabilityCode": "OA", "url": "https://e.example/a.pdf"},
        {"documentStyle": "pdf", "availabilityCode": "S", "url": "https://e.example/sub.pdf"},
        {"documentStyle": "html", "availabilityCode": "OA", "url": "https://e.example/a.html"}]}}
    assert [u for u, _m in R.europepmc_pick(res)] == ["https://e.example/a.pdf"]
    assert R.europepmc_pick(dict(res, hasPDF="N")) == []
    assert {(r["scheme"], r["value"]) for r in R.from_europepmc(res, "10.1/x")} == {("pmid", "1"), ("pmcid", "PMC2")}
    assert [u for u, _m in R.doaj_links({"results": [{"bibjson": {"link": [
        {"type": "fulltext", "url": "https://j.example/a"}, {"type": "other", "url": "https://j.example/b"}]}}]})] == [
        "https://j.example/a"]
    pdf, other = R.openaire_urls(b"<r><instance><webresource><url>https://r.example/a.pdf</url></webresource>"
                                 b"</instance><url>https://r.example/landing</url></r>")
    assert pdf == ["https://r.example/a.pdf"] and other == ["https://r.example/landing"]
    assert R.openaire_urls(b"not xml") == ([], [])
    assert [u for u, _m in R.hal_files({"response": {"docs": [{"fileMain_s": "https://hal.science/x/document"}]}})] == [
        "https://hal.science/x/document"]
    assert [u for u, _m in R.zenodo_files({"files": [{"key": "a.pdf", "links": {"self": "https://z/a.pdf"}},
                                                     {"key": "b.csv", "links": {"self": "https://z/b"}}]})] == ["https://z/a.pdf"]
    assert R.figshare_id("10.6084/m9.figshare.123.v2") == "123"


def test_the_venue_ladder_needs_title_author_and_year_to_agree():
    """OpenReview notes CONSTRUCTED in API v2's shape; ACL ids from a DOI and from S2."""
    from litkb.acquire import stage_b_repos as R

    work = {"title": "Verified Uncertainty Calibration", "first_author": "Kumar", "year": 2019, "ids": []}
    good = {"id": "n1", "pdate": 1569888000000, "content": {"title": {"value": "Verified uncertainty calibration"},
                                                            "authors": {"value": ["Ananya Kumar", "P. Liang"]}}}
    assert R.openreview_match([good], work)["id"] == "n1"
    assert R.openreview_match([dict(good, content={**good["content"], "authors": {"value": ["Someone Else"]}})],
                              work) is None
    assert R.openreview_match([dict(good, pdate=1700000000000)], work) is None         # 2023: the year disagrees
    # the surname agrees as WHOLE tokens, never as a substring (auditor-C2a F15): "Kumar" is not "Kumaran"
    assert R.openreview_match([dict(good, content={**good["content"], "authors": {"value": ["Oliver Kumaran"]}})],
                              work) is None
    li = dict(work, first_author="Li")
    assert R.openreview_match([dict(good, content={**good["content"], "authors": {"value": ["Oliver Smith"]}})],
                              li) is None
    assert R.openreview_match([dict(good, content={**good["content"], "authors": {"value": ["Fei-Fei Li"]}})],
                              li)["id"] == "n1"
    assert R.surname_agrees("Delgado-Quiros", "Lorena Delgado-Quir\u00f3s")          # accents fold
    assert R.acl_id({"ids": [("doi", "10.18653/v1/p18-1031", "own")]}) == "P18-1031"
    assert R.acl_id({"ids": [("acl", "2020.acl-main.1", "s2")]}) == "2020.acl-main.1"


def test_datacite_refuses_an_answer_for_another_doi_and_confirms_the_arxiv_candidate():
    """CONSTRUCTED DataCite answers."""
    from litkb import identifiers as I
    from litkb.acquire import stage_b as B

    cand = I.arxiv_to_doi("2206.01062")
    work = {"doi": None, "arxiv": "2206.01062", "ids": [("arxiv", "2206.01062", "own")], "candidates": [cand]}
    other = Stub({"api.datacite.org": _json({"data": {"id": "10.48550/arxiv.9999.00001",
                                                      "attributes": {"doi": "10.48550/arxiv.9999.00001"}}})})
    r = B.rung_datacite(dict(work), Ctx({"datacite": other}))
    assert r["status"] == "unresolved" and "harvest" not in r
    ok = Stub({"api.datacite.org": _json({"data": {"id": "10.48550/arxiv.2206.01062", "attributes": {
        "doi": "10.48550/arxiv.2206.01062", "identifiers": [{"identifier": "2206.01062", "identifierType": "arXiv"}]}}})})
    r = B.rung_datacite(dict(work), Ctx({"datacite": ok}))
    confirmed = [x for x in r["harvest"]["rows"] if x["scheme"] == "doi"]
    assert confirmed and confirmed[0]["verified_by"] == "datacite" and confirmed[0]["evidence"]["candidate"]
    # a Crossref DOI with no 404 in this run is not DataCite's to ask
    assert B.rung_datacite({"doi": "10.1016/j.x", "ids": []}, Ctx())["status"] == "skipped"


def test_the_closure_rule_skips_a_wave_2_call_whose_scheme_is_held_and_reports_the_pass_cap():
    from litkb.acquire import stage_b as B
    from litkb.acquire import stage_b_repos as R

    held = {"doi": "10.1/x", "ids": [("pmid", "1", "openalex"), ("pmcid", "PMC2", "s2")]}
    r = B.rung_ncbi_idconv(held, Ctx())
    assert (r["status"], r["sub_status"]) == ("skipped", "policy_refused") and "closure" in r["policy"]
    assert R.rung_europepmc({"doi": "10.1/x", "ids": []}, Ctx())["sub_status"] == "no_identifier"
    assert B.rung_arxiv({"doi": "10.1/x", "ids": []}, Ctx())["sub_status"] == "no_identifier"
    # a DOI found by DataCite (Wave 2) for a work that had none: the Wave-1 rungs keyed on a DOI cannot be asked again
    # in this run -> recorded as pending, never dropped
    work = {"doi": None, "ids": [("arxiv", "1", "own")]}
    B.gained(work, [{"scheme": "doi", "value": "10.48550/arxiv.1"}], "datacite")
    assert "crossref-link" in work["closure_pending"]["datacite"]


# ── the ladder, on a worker database ─────────────────────────────────────────────────────────────
#: A REAL arXiv-DOI row's fields (Thakur_2021 on live), admitted as a CONSTRUCTED registry admission.
THAKUR = {"key": "Thakur_2021_beir-heterogenous-benchmark-zero", "doi": "10.48550/arxiv.2104.08663",
          "type": "preprint", "title": "BEIR: A Heterogenous Benchmark for Zero-shot Evaluation", "author": "Thakur",
          "year": 2021}
#: A CONSTRUCTED work (10.5555 is Crossref's test prefix): typed `article` by admission, `posted-content` by the
#: CONSTRUCTED Crossref answer or crosswalk CSV row a test gives it — the plan's second preprint definition.
ARTICLE_POSTED = {"key": "Tester_2024_constructed-article-crossref-calls", "doi": "10.5555/c2a.constructed.posted",
                  "type": "article", "title": "A CONSTRUCTED article-typed work Crossref calls posted content",
                  "author": "Tester", "year": 2024}

def _reset_and_migrate(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


@pytest.fixture(scope="module")
def pgc(litkb_pg_base):
    """The shared worker database, RESET AND MIGRATED before this module's first database test and after its last
    (brief-COMMON rule 5: these tests admit REAL keys and DOIs — Kats_2019, DelgadoQuiros_2025, E13)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset_and_migrate(conn)
    yield conn
    _reset_and_migrate(conn)


@pg_only
@pytest.mark.parametrize("name", sorted(C2A.FIRES))
def test_every_c2a_fire_fires(pgc, tmp_path, name):
    """The harness's protocol: control on a fresh database inside the counter's bound, known-bad on a fresh
    database outside it (=0 gated counters: control 0, known-bad > 0)."""
    fire = C2A.FIRES[name]
    got = {}
    for arm in ("control", "known_bad"):
        _reset_and_migrate(pgc)
        got[arm] = fire["run"](pgc, arm, tmp_path / arm)
    assert got["control"] == 0 and got["known_bad"] > 0, got


@pg_only
def test_the_ladder_writes_each_rung_s_harvest_on_its_attempt_and_the_router_s_refusal_as_a_skip(pgc, tmp_path):
    """E13's REAL recorded S2 answer through the real ladder: the attempt row carries the harvest summary and the
    `stage_b` facts; a preprint's shadow rung is a `skipped/policy_refused` row naming the router; the contact
    email never reaches the ledger."""
    from litkb.acquire import run as R

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("ladder")
        work = w.admit(ws, C2A.ROWS["e13"])
        client = C2A.ReplayClient(C2A.row_tag(C2A.ROWS["e13"]["doi"]))
        w.acquire(ws, work, {"s2": client}, routes=("s2",))
        C2A.no_misses(client)
        row = pgc.execute("SELECT status, detail FROM litkb.acquisition_attempts WHERE work_id = %s AND route = 's2'",
                          (work["work_id"],)).fetchone()
        assert row[0] == "no-oa-copy" and row[1]["harvest"]["relations"] >= 1 and "gained" in row[1]["stage_b"]
        # the ladder's first row for the work carries Stage A's record (auditor-C2a F1; a rung's answer, here)
        assert row[1]["stage_a"]["class"] == "paper" and row[1]["stage_a"]["rejected_ids"] == []
        edge = pgc.execute("SELECT relation, target_scheme, target_value_norm, asserted_by FROM litkb.work_relations "
                           "WHERE work_id = %s AND state = 'asserted'", (work["work_id"],)).fetchall()
        assert ("has_version", "arxiv", "2206.01062", "s2") in edge
        pre = w.admit(ws, C2A.ROWS["preprint"])
        rungs = [next(r for r in R.RUNGS if r.route == "osf"), R.Rung("annas", C2A._stub_annas, needs=("doi",))]
        osf = C2A.ReplayClient(C2A.row_tag(C2A.ROWS["preprint"]["doi"]), stubs={"://osf.io/": (404, {}, b"")})
        from litkb.acquire import policy as P
        with C2A.shadow_tier_on(P):          # the router is graded, not the shadow tier's switch (auditor-C2a F3)
            w.acquire(ws, pre, {"osf": osf}, routes=("osf", "annas"), rungs=rungs)
        skip = pgc.execute("SELECT status, sub_status, detail FROM litkb.acquisition_attempts WHERE work_id = %s "
                           "AND route = 'annas'", (pre["work_id"],)).fetchone()
        assert skip[0] == "skipped" and skip[1] == "policy_refused" and "work-class router" in json.dumps(skip[2])
        ledger = pgc.execute("SELECT string_agg(coalesce(detail::text, '') || coalesce(terminal_url, ''), ' ') "
                             "FROM litkb.acquisition_attempts").fetchone()[0]
        assert "c2a-test@example.invalid" not in ledger and "c2a-fire@example.invalid" not in ledger
    finally:
        w.close()


@pg_only
def test_stage_a_writes_the_certain_wave_0_row_with_deterministic_provenance(pgc, tmp_path):
    """A CONSTRUCTED arXiv-DOI work (Thakur_2021's real DOI shape): prepare() writes its arXiv id as a
    `deterministic` identifier and classifies it a preprint."""
    from litkb.acquire import stage_a as A

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("wave0")
        work = w.admit(ws, THAKUR)
        summary = A.prepare(w.writer, ws, w.tokens[ws], work, None, agent="c2a", session="c2a-1")
        assert work["class"] == "preprint" and summary["derived"] == ["arxiv:2104.08663"]
        row = pgc.execute("SELECT v.asserted_by, v.derived_from_scheme FROM litkb.identifier_versions v JOIN "
                          "litkb.identifiers i ON i.id = v.identifier_id WHERE v.work_id = %s AND i.scheme = 'arxiv'",
                          (work["work_id"],)).fetchone()
        assert row == ("deterministic", "doi")
    finally:
        w.close()


@pg_only
def test_the_counters_refuse_a_manifest_that_cannot_answer_them(pgc):
    with pytest.raises(ValueError):
        C2A.preprints_sent_to_shadow(pgc, {"probe_csvs": {}})
    with pytest.raises(ValueError):
        C2A.preprints_sent_to_shadow(pgc, {"frozen_at": "2026-01-01", "run_workstream_ids": ["x"]})
    with pytest.raises(ValueError):
        C2A.free_ceiling_measured_unconverted(pgc, {})
    # the tracked head CSV carries the RE-GRADED Wayback row (S4.5 decision D23: C2c's IIASA positive), so the default
    # reads it (integrator-w3)
    rows = C2A.free_ceiling_rows({"repo": str(REPO), "probe_csvs": {C2A.HEAD_PROBE: f"phase4/qc/{C2A.HEAD_PROBE}"}})
    assert C2A._wayback_positive()[0] in rows and "10.1007/978-3-030-32248-9_57" in rows and len(rows) == 5


@pg_only
def test_the_report_lines_speak_builder_a_s_grammar_and_measure_every_built_rung(pgc, tmp_path):
    """The LITKB_LADDER1 lines over a run that asked every printed route ONCE (CONSTRUCTED `no-oa-copy` attempt rows
    on one admitted work): builder A's parser reads a yield line for every route, `not-built: core`, D19's
    identifiers line, the kill lines and the kill note — and builder A's counter reads every built Stage B rung
    measured. Every route is asked because builder A's final rule (auditor-A round 1 F3, on the merged candidate)
    reads a line that asked NOBODY (`=0/0`) as unmeasured."""
    from litkb.acquire import run as R

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("report")
        work = w.admit(ws, C2A.ROWS["kats"])
        frozen = w.now()
        routes = C2A.built_routes() + [r.route for r in R.RUNGS if r.stage == "B" and r.route not in C2A.built_routes()]
        for route in routes:
            R.record_attempt(w.writer, ws, w.tokens[ws], work["work_id"], route, work["doi"], "no-oa-copy",
                             {"note": "CONSTRUCTED"}, [200])
        manifest = {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "repo": str(REPO),
                    "probe_csvs": {C2A.CROSSWALK_PROBE: f"phase4/qc/{C2A.CROSSWALK_PROBE}"}}
        lines = C2A.report_lines(pgc, manifest)
    finally:
        w.close()
    text = "\n".join(lines) + "\n"
    ys, nb = HA.yields(text), HA.not_built(text)
    assert set(ys) == set(routes) and all(v == (0, 1) for v in ys.values()) and "core" in nb, (ys, nb)
    assert "identifiers: opencitations=0/1" in lines and "identifiers: ncbi-idconv=0/1" in lines
    assert [ln.split(":")[0] for ln in lines if ln.startswith("kill")].count("kill") == len(C2A.KILL_SCHEMES)
    assert any(ln.startswith("kill-note: md5 is structurally 0") for ln in lines)
    rep = tmp_path / "LITKB_LADDER1_constructed.md"
    rep.write_text(text, encoding="utf-8")
    # builder A's counter reads every BUILT Stage B rung measured (the registry has no unbuilt Stage B route but core)
    assert HA.stage_b_rungs_unmeasured(pgc, {"report_path": str(rep)}) == 0


@pg_only
def test_the_contact_email_is_registered_before_the_request_and_never_reaches_the_ledger(pgc, tmp_path, monkeypatch):
    """A UNIQUE constructed email (the redaction list is process-wide, so a shared address could have been
    registered by an earlier test): the crossref-link rung asks with it as `mailto`, and neither the attempt's
    terminal URL nor its detail holds it. CONSTRUCTED Crossref answer (a 404)."""
    import uuid

    from litkb.acquire import open_access

    email = f"c2a-{uuid.uuid4().hex[:10]}@example.invalid"
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: email)
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("email")
        work = w.admit(ws, C2A.ROWS["kats"])
        s = Stub({"api.crossref.org": (404, {}, b"")})
        w.acquire(ws, work, {"crossref-link": s}, routes=("crossref-link",))
        assert any("mailto=" in u for u, _a in s.calls)        # the email WAS sent, where the service asks for one
        row = pgc.execute("SELECT status, coalesce(terminal_url, ''), detail::text FROM litkb.acquisition_attempts "
                          "WHERE work_id = %s AND route = 'crossref-link'", (work["work_id"],)).fetchone()
        assert row[0] == "unresolved"
        assert email not in row[1] and email not in row[2] and email.replace("@", "%40") not in row[1]
    finally:
        w.close()


def test_a_transport_failure_is_no_answer_and_a_scheduled_retry_may_ask_the_url_again():
    """CONSTRUCTED: the first ask of a candidate fails in transport (status 0), so the URL is not marked asked and
    the rung's one scheduled retry (C1a) reaches it; an ANSWERED URL is never asked twice in the run."""
    from litkb.acquire import stage_b as B

    work = {}
    down = Stub({"x.example": (0, {}, b"URLError: timed out")})
    r = B.fetch_candidates("hal", [("https://x.example/f.pdf", {})], Ctx({"hal": down}), work)
    assert r["status"] == "api-error" and r["retriable"]
    up = Stub({"x.example": (200, {}, _pdf())})
    r = B.fetch_candidates("hal", [("https://x.example/f.pdf", {})], Ctx({"hal": up}), work)
    assert r["status"] == "downloaded" and len(up.calls) == 1
    r = B.fetch_candidates("doaj", [("https://x.example/f.pdf", {})], Ctx({"doaj": up}), work)
    assert len(up.calls) == 1 and "already asked" in r["detail"]

# ── fix round 2 (auditor-C2a round 1: F1-F4 fix-before-landing; notes F7, F14, F15, F17) ─────────────────────
@pg_only
def test_stage_a_s_record_reaches_the_first_attempt_row_even_when_its_wave_0_write_fails(pgc, tmp_path):
    """auditor-C2a F1: `stage_a.prepare`'s summary (A1's rejections, Wave 0, a write failure, the class) rides on
    the FIRST attempt row the ladder writes for the work — a skip, a budget stop, the manual-step row, whichever
    comes first — and in acquire()'s answer; never only on the work dict. CONSTRUCTED: B1's `harvest.record`
    raising inside prepare() only, for a CONSTRUCTED admission of Thakur_2021's arXiv DOI (Wave 0 derives and
    WRITES its arXiv id); the one rung asked (`osf`) skips a non-OSF DOI, so the first row is that skip."""
    from unittest import mock

    from litkb.acquire import policy as P
    from litkb.acquire import stage_a as A
    from litkb.admit import harvest as H

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("stage-a-record")
        work = w.admit(ws, THAKUR)
        real = A.prepare

        def failing(*a, **k):
            with mock.patch.object(H, "record", side_effect=RuntimeError("CONSTRUCTED Wave-0 write failure")):
                return real(*a, **k)

        with mock.patch.object(A, "prepare", failing):
            res = w.acquire(ws, work, {}, routes=("osf",))
        rows = pgc.execute("SELECT route, status, detail FROM litkb.acquisition_attempts WHERE work_id = %s",
                           (work["work_id"],)).fetchall()
        carried = [(r[0], r[1]) for r in rows if "stage_a" in (r[2] or {})]
        assert carried == [("osf", "skipped")] and ("browser", "manual-step") in [(r[0], r[1]) for r in rows], rows
        sa = next(r[2]["stage_a"] for r in rows if r[0] == "osf")
        assert "CONSTRUCTED Wave-0 write failure" in sa["write_error"], sa
        assert sa["class"] == "preprint" and sa["derived"] == ["arxiv:2104.08663"] and sa["native"] == "arxiv"
        assert res["stage_a"]["write_error"] == sa["write_error"]
        # no rung row at all: the manual-step row is the first, and carries it
        k = w.admit(ws, C2A.ROWS["kats"])
        res = w.acquire(ws, k, {}, routes=())
        got = pgc.execute("SELECT route, status, detail FROM litkb.acquisition_attempts WHERE work_id = %s",
                          (k["work_id"],)).fetchall()
        assert [(r[0], r[1]) for r in got] == [("browser", "manual-step")], got
        assert got[0][2]["stage_a"]["class"] == "chapter" and res["stage_a"]["class"] == "chapter"
        # a ladder whose budget is spent before its first rung: the budget-stop row is the first, and carries it
        e = w.admit(ws, C2A.ROWS["e13"])
        w.acquire(ws, e, {}, routes=("osf",), ladder_budget=P.LadderBudget(attempts=0))
        got = pgc.execute("SELECT route, status, detail FROM litkb.acquisition_attempts WHERE work_id = %s AND "
                          "detail ? 'stage_a'", (e["work_id"],)).fetchall()
        assert [(r[0], r[1]) for r in got] == [("ladder", "budget-stop")], got
        assert got[0][2]["stage_a"]["class"] == "paper"
    finally:
        w.close()


@pg_only
def test_the_router_fire_grades_the_router_with_the_shadow_tier_switched_off(pgc, tmp_path, monkeypatch):
    """auditor-C2a F3 (its OWN9): the live run switches the shadow tier OFF (`policy.SHADOW_TIER_ENABLED`, the scope
    ruling). With the process's switch off, the router fire still reads control 0 and known-bad 1 — it pins the tier
    on for its arms (`shadow_tier_on`), so it grades the router and not the switch."""
    from litkb.acquire import policy as P

    monkeypatch.setattr(P, "SHADOW_TIER_ENABLED", False)
    fire = C2A.FIRES["router_disabled_preprint"]
    got = {}
    for arm in ("control", "known_bad"):
        _reset_and_migrate(pgc)
        got[arm] = fire["run"](pgc, arm, tmp_path / arm)
    assert got == {"control": 0, "known_bad": 1}, got
    assert P.SHADOW_TIER_ENABLED is False                    # the pin is the fire's own, never left behind


@pg_only
def test_a_crossref_posted_content_answer_keeps_an_article_typed_work_off_the_shadow_tier(pgc, tmp_path):
    """auditor-C2a F4, the ROUTER's half of the plan's second preprint definition: a CONSTRUCTED `article`-typed
    work whose CONSTRUCTED Crossref answer is `posted-content`, hunted through `crossref-link` then a CONSTRUCTED
    shadow stub on route `annas`: the live answer tightens the class to preprint, and the shadow row is
    `skipped/policy_refused` naming the router (the tier pinned on: the router is graded)."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("posted")
        work = w.admit(ws, ARTICLE_POSTED)
        cr = Stub({"api.crossref.org": _json({"message": {"DOI": ARTICLE_POSTED["doi"], "type": "posted-content",
                                                          "title": [ARTICLE_POSTED["title"]]}})})
        rungs = [next(r for r in R.RUNGS if r.route == "crossref-link"),
                 R.Rung("annas", C2A._stub_annas, needs=("doi",))]
        with C2A.shadow_tier_on(P):
            w.acquire(ws, work, {"crossref-link": cr}, routes=("crossref-link", "annas"), rungs=rungs)
        rows = {r[0]: r[1:] for r in pgc.execute(
            "SELECT route, status, sub_status, detail FROM litkb.acquisition_attempts WHERE work_id = %s",
            (work["work_id"],)).fetchall()}
        assert rows["crossref-link"][2]["stage_a"]["class"] == "paper"            # Stage A read `article`
        assert rows["crossref-link"][2]["stage_b"]["work_class"] == "preprint"    # Crossref's answer tightened it
        assert rows["annas"][:2] == ("skipped", "policy_refused"), rows["annas"]
        assert "work-class router" in json.dumps(rows["annas"][2])
    finally:
        w.close()


@pg_only
def test_the_preprint_counter_reads_the_crosswalk_csv_s_posted_content_half(pgc, tmp_path):
    """auditor-C2a F4, the COUNTER's half: a CONSTRUCTED `article`-typed work with one shadow SPEND recorded after
    frozen_at in the run's workstream, graded against CONSTRUCTED crosswalk CSVs: one typing the work
    `posted-content` by its key -> 1; by its DOI alone -> 1; one naming only another work, or typing this one
    `journal-article` -> 0 (main_works.type alone says article)."""
    from litkb.acquire import run as R

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("counter")
        work = w.admit(ws, ARTICLE_POSTED)
        frozen = w.now()
        R.record_attempt(w.writer, ws, w.tokens[ws], work["work_id"], "annas", work["doi"], "not-in-archive",
                         {"note": "CONSTRUCTED shadow spend"}, [200], sub_status="not_in_corpus")

        def count(name, rows):
            p = tmp_path / f"{name}.csv"
            with open(p, "w", encoding="utf-8", newline="") as f:
                wr = csv.DictWriter(f, fieldnames=["key", "doi", "cr_type"])
                wr.writeheader()
                wr.writerows(rows)
            return C2A.preprints_sent_to_shadow(pgc, {"frozen_at": frozen, "run_workstream_ids": [ws],
                                                      "repo": str(REPO), "probe_csvs": {C2A.CROSSWALK_PROBE: str(p)}})

        assert count("other", [{"key": "Other_2020_x", "doi": "10.5555/other", "cr_type": "posted-content"}]) == 0
        assert count("by_key", [{"key": work["key"], "doi": "", "cr_type": "posted-content"}]) == 1
        assert count("by_doi", [{"key": "", "doi": work["doi"].upper(), "cr_type": "posted-content"}]) == 1
        assert count("article", [{"key": work["key"], "doi": work["doi"], "cr_type": "journal-article"}]) == 0
    finally:
        w.close()


def test_the_ncbi_converter_is_asked_while_either_pmid_or_pmcid_is_absent():
    """auditor-C2a F7 (OWN4): the closure rule skips the converter only when BOTH are held. CONSTRUCTED answers."""
    from litkb.acquire import stage_b as B

    for held in ([("pmid", "1", "openalex")], [("pmcid", "PMC2", "s2")], []):
        s = Stub({"pmc.ncbi.nlm.nih.gov": _json({"records": [{"doi": "10.1/x", "pmid": "1", "pmcid": "PMC2"}]})})
        r = B.rung_ncbi_idconv({"doi": "10.1/x", "ids": list(held)}, Ctx({"ncbi-idconv": s}))
        assert r["status"] != "skipped" and len(s.calls) == 1, (held, r)
        # the rung asks the URL its one builder makes (auditor-C2a F17): the tool name and the contact email
        assert s.calls[0][0] == B.ncbi_url("10.1/x", "c2a-test@example.invalid"), s.calls


def test_datacite_is_asked_for_a_doi_crossref_answered_404_for():
    """auditor-C2a F7 (OWN5): LINKAGE §2.3 Wave 2, "Crossref 404 -> DataCite". CONSTRUCTED answers."""
    from litkb.acquire import stage_b as B

    work = {"doi": "10.1016/j.x", "ids": []}
    r = B.rung_crossref_link(work, Ctx({"crossref-link": Stub({})}))           # the Stub answers 404
    assert r["status"] == "unresolved" and work["crossref_status"] == 404
    assert B.datacite_targets(work) == [("10.1016/j.x", None)]
    assert B.datacite_targets({"doi": "10.1016/j.x", "crossref_status": 200}) == []
    s = Stub({"api.datacite.org": _json({"data": {"id": "10.1016/j.x", "attributes": {"doi": "10.1016/j.x"}}})})
    r = B.rung_datacite(work, Ctx({"datacite": s}))
    assert len(s.calls) == 1 and r["status"] != "skipped", r


@pg_only
def test_a_rung_s_conversions_count_measured_hits_as_well_as_landed_ones(pgc, tmp_path):
    """auditor-C2a F7 (OWN7): the run's works WITH a file are asked in MEASURE mode, whose hits are `measured` rows —
    `rung_conversions_<route>` counts them beside `ok`. CONSTRUCTED attempt rows on three admitted works."""
    from litkb.acquire import run as R

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("conv")
        works = [w.admit(ws, C2A.ROWS[k]) for k in ("kats", "preprint", "e13")]
        frozen = w.now()
        for work, status in zip(works, ("ok", "measured", "no-oa-copy")):
            R.record_attempt(w.writer, ws, w.tokens[ws], work["work_id"], "arxiv", work["doi"], status,
                             {"note": "CONSTRUCTED"}, [200])
        assert C2A.rung_counts(pgc, {"frozen_at": frozen, "run_workstream_ids": [ws]}, "arxiv") == (2, 3)
    finally:
        w.close()


_OAI_PAGE = ("""<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>
    <record><header><identifier>oai:eartharxiv.org:id:{n}</identifier></header><metadata>
    <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier>https://doi.org/10.31223/X5000{n}</dc:identifier>
    <dc:identifier>https://eartharxiv.org/repository/object/{n}/download/1/</dc:identifier>
    <dc:relation>https://doi.org/10.1029/2020GL00000{n}</dc:relation></oai_dc:dc></metadata></record>
    {token}</ListRecords></OAI-PMH>""")


def test_the_eartharxiv_harvester_writes_the_map_only_on_a_complete_walk(tmp_path):
    """auditor-C2a F14: a CONSTRUCTED two-page feed whose second page answers 503 -> exit 1 and NO map at the map
    path (the rows read so far go to a `.partial.csv` no rung reads); the same feed answered in full -> the map."""
    page1 = _OAI_PAGE.format(n=1, token="<resumptionToken>tok-2</resumptionToken>").encode()
    page2 = _OAI_PAGE.format(n=2, token="").encode()

    class Feed:
        def __init__(self, second):
            self.second, self.calls = second, []

        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            self.calls.append(url)
            return (200, {}, page1) if "metadataPrefix" in url else self.second

    out = tmp_path / "map.csv"

    def quiet(*a, **k):
        return None

    assert EMAP.run_live(out, client=Feed((503, {}, b"")), pace_s=0, printer=quiet) == 1
    assert not out.exists() and (tmp_path / "map.partial.csv").is_file()
    assert EMAP.run_live(out, client=Feed((200, {}, page2)), pace_s=0, printer=quiet) == 0
    with open(out, encoding="utf-8", newline="") as f:
        assert [r["preprint_doi"] for r in csv.DictReader(f)] == ["10.31223/x50001", "10.31223/x50002"]


def test_concurrent_rungs_never_ask_one_url_twice():
    """auditor-C2a F17: the Wave-1 rungs run concurrently and share the run's asked-URL set; the check and the
    reservation are one step, so two rungs meeting one URL at once ask it ONCE. CONSTRUCTED slow answer."""
    import threading
    import time

    from litkb.acquire import stage_b as B

    class Slow(Stub):
        def get(self, url, **k):
            time.sleep(0.2)
            return super().get(url, **k)

    s, work = Slow({"x.example": (200, {}, b"<html>a page</html>")}), {}
    gate = threading.Barrier(2)

    def ask(route):
        gate.wait()
        B.fetch_candidates(route, [("https://x.example/same.pdf", {})], Ctx({route: s}), work)

    threads = [threading.Thread(target=ask, args=(r,)) for r in ("openalex", "doaj")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(s.calls) == 1, s.calls


# ── fix round 3 (auditor-C2a round 2: F1-F3 fix-before-landing; notes F4-F7, F10) ─────────────────────────────
class Seq(Stub):
    """CONSTRUCTED answers IN ORDER for one URL fragment (the last repeats); every other URL is a 404."""

    def __init__(self, frag, answers):
        super().__init__({})
        self.frag, self.answers, self.n = frag, list(answers), 0

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append((url, accept))
        if self.frag in url:
            a = self.answers[min(self.n, len(self.answers) - 1)]
            self.n += 1
            return a
        return 404, {}, b""


_CHALLENGE = b"<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"


def test_a_transient_pdf_answer_releases_its_url_and_an_answered_one_names_its_asker():
    """auditor-C2a round 2 F1 (pure half): a 429 and a 5xx are TRANSIENT answers (C1a's in-run retry rule,
    `backoff.classify`), so the URL is released and the rung's scheduled retry asks it again; a 403 is an answer and
    stays asked. A challenge served at 503 is released only if that same rule retries a `blocked` row (C1a's final
    rule never does — a challenge is a refusal — so on the merged candidate its URL stays asked). F7: the note names
    the rung that asked. CONSTRUCTED answers."""
    from litkb.acquire import stage_b as B

    pdf = _pdf()
    url = "https://x.example/f.pdf"
    for first in ((429, {}, b"Too Many Requests"), (502, {}, b"")):
        s, work = Seq("x.example", [first, (200, {}, pdf)]), {}
        r = B.fetch_candidates("hal", [(url, {})], Ctx({"hal": s}), work)
        assert r["status"] == "api-error" and url not in work["asked_urls"], (first[0], r)
        r = B.fetch_candidates("hal", [(url, {})], Ctx({"hal": s}), work)
        assert r["status"] == "downloaded" and len(s.calls) == 2, (first[0], r)
    retried = B._backoff.classify("blocked", [503]) == "transient"
    s, work = Seq("x.example", [(503, {}, _CHALLENGE), (200, {}, pdf)]), {}
    r = B.fetch_candidates("hal", [(url, {})], Ctx({"hal": s}), work)
    assert (r["status"], r["sub_status"]) == ("blocked", "challenge_or_bot_check"), r
    assert (url in work["asked_urls"]) is (not retried), (retried, work)
    r = B.fetch_candidates("hal", [(url, {})], Ctx({"hal": s}), work)
    assert len(s.calls) == (2 if retried else 1) and (r["status"] == "downloaded") is retried, (retried, r)
    s, work = Seq("x.example", [(403, {}, b"<html>no</html>"), (200, {}, pdf)]), {}
    B.fetch_candidates("openalex", [("https://x.example/f.pdf", {})], Ctx({"openalex": s}), work)
    r = B.fetch_candidates("doaj", [("https://x.example/f.pdf", {})], Ctx({"doaj": s}), work)
    assert len(s.calls) == 1 and "already asked in this ladder run by openalex" in r["detail"], r


@pg_only
def test_the_ladder_s_scheduled_retry_asks_a_transient_pdf_again_and_books_what_it_is_served(pgc, tmp_path):
    """auditor-C2a round 2 F1 through the REAL ladder (its reproduction, as a test): a CONSTRUCTED article whose `hal`
    deposit's PDF answers 429 once, then a CONSTRUCTED PDF of the work -> the retry ASKS the PDF again and the file
    lands (the final row is the retry's `ok`, never a `no-oa-copy` over the 429); a CONSTRUCTED T&F-prefixed work
    whose A4 `publisher-url` serves a challenge at 503 every time -> the chain's FINAL row is `blocked` /
    `challenge_or_bot_check` (the plan's typed negative), never a false miss: C1a's in-run rule either retries the
    `blocked` row (this branch's base: the retry asks the page again) or never does (C1a's final rule: one row)."""
    work_row = {"key": "Tester_2024_constructed-retry-probe", "doi": "10.5555/c2a.r3.retry", "type": "article",
                "title": "A CONSTRUCTED article whose PDF host answers 429 once", "author": "Tester", "year": 2024}
    tf_row = {"key": "Tester_2024_constructed-challenge-probe", "doi": "10.1080/c2a.r3.challenge", "type": "article",
              "title": "A CONSTRUCTED article whose publisher PDF URL serves a challenge at 503", "author": "Tester",
              "year": 2024}
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("retry")
        work = w.admit(ws, work_row)
        search = _json({"response": {"numFound": 1, "docs": [{"halId_s": "hal-0",
                                                             "fileMain_s": "https://hal.example/hal-0/document"}]}})

        class Hal(Seq):
            """HAL's search API answers one deposit (every time); its file answers in order."""

            def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
                if "api.archives-ouvertes.fr" in url:
                    self.calls.append((url, accept))
                    return search
                return super().get(url, accept=accept, timeout=timeout, follow=follow, data=data, headers=headers)

        hal = Hal("hal.example", [(429, {"Retry-After": "0"}, b"Too Many Requests"),
                                  (200, {"Content-Type": "application/pdf"},
                                   C2A.constructed_pdf(work_row["title"], work_row["author"]))])
        res = w.acquire(ws, work, {"hal": hal}, routes=("hal",))
        rows = pgc.execute("SELECT route, status, http_codes, retry_of IS NOT NULL FROM litkb.acquisition_attempts "
                           "WHERE work_id = %s AND route = 'hal' ORDER BY at, id", (work["work_id"],)).fetchall()
        assert [(r[1], list(r[2] or []), r[3]) for r in rows][0] == ("api-error", [429], False), rows
        assert rows[-1][1] == "ok" and rows[-1][3], rows
        assert hal.n == 2 and res["outcome"] == "ok", (hal.calls, res)
        tf = w.admit(ws, tf_row)
        ch = Seq("tandfonline.com", [(503, {"Content-Type": "text/html"}, _CHALLENGE)])
        w.acquire(ws, tf, {"publisher-url": ch}, routes=("publisher-url",))
        got = pgc.execute("SELECT status, sub_status, retry_of IS NOT NULL FROM litkb.acquisition_attempts "
                          "WHERE work_id = %s AND route = 'publisher-url' ORDER BY at, id", (tf["work_id"],)).fetchall()
        from litkb.acquire import backoff as BO
        want = [("blocked", "challenge_or_bot_check", False)]
        if BO.classify("blocked", [503]) == "transient":                # C1a's rule retries it: the retry re-asks
            want.append(("blocked", "challenge_or_bot_check", True))
        assert got == want and ch.n == len(want), (got, ch.calls)
    finally:
        w.close()


@pg_only
def test_the_preprint_counter_s_type_half_its_run_scope_and_every_shadow_route(pgc, tmp_path):
    """auditor-C2a round 2 F2 (the plan's FIRST preprint definition alone), F5 (S4.5 decision D1's two scope halves)
    and F6 / OWN9 (scihub and bban read, not only annas). CONSTRUCTED admissions of two REAL preprint rows' fields
    (Thakur_2021 in the run's workstream, DelgadoQuiros_2025 in ANOTHER), CONSTRUCTED attempt rows, graded against a
    CONSTRUCTED crosswalk CSV that names neither work — so every count here comes from `main_works.type` alone:
    a spend BEFORE frozen_at and a spend in another workstream -> 0; a spend on each shadow route after frozen_at in
    the run -> 1, 2, 3; a recorded pre-fetch skip is never a spend (Codex X5)."""
    from litkb.acquire import run as R

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws, other = w.ws("scope"), w.ws("other")
        pre = w.admit(ws, THAKUR)
        elsewhere = w.admit(other, C2A.ROWS["preprint"])
        assert pgc.execute("SELECT array_agg(DISTINCT type) FROM litkb.main_works WHERE work_id = ANY(%s)",
                           ([pre["work_id"], elsewhere["work_id"]],)).fetchone()[0] == ["preprint"]

        def spend(on, work, route, status="not-in-archive", sub="not_in_corpus"):
            R.record_attempt(w.writer, on, w.tokens[on], work["work_id"], route, work["doi"], status,
                             {"note": "CONSTRUCTED shadow spend"}, [200], sub_status=sub)

        spend(ws, pre, "annas")                                   # BEFORE frozen_at: history, not the run
        frozen = w.now()
        spend(other, elsewhere, "annas")                          # after frozen_at, but ANOTHER workstream's
        p = tmp_path / "crosswalk.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=["key", "doi", "cr_type"])
            wr.writeheader()
            wr.writerow({"key": "Other_2020_x", "doi": "10.5555/other", "cr_type": "posted-content"})
        m = {"frozen_at": frozen, "run_workstream_ids": [ws], "repo": str(REPO),
             "probe_csvs": {C2A.CROSSWALK_PROBE: str(p)}}
        assert C2A.preprints_sent_to_shadow(pgc, m) == 0
        spend(ws, pre, "annas", "skipped", "policy_refused")      # a pre-fetch refusal spent nothing
        assert C2A.preprints_sent_to_shadow(pgc, m) == 0
        for n, route in enumerate(("annas", "scihub", "bban"), start=1):
            spend(ws, pre, route)
            assert C2A.preprints_sent_to_shadow(pgc, m) == n, route
        assert sorted(r[1] for r in C2A.preprints_sent_detail(pgc, m)) == ["annas", "bban", "scihub"]
    finally:
        w.close()


@pg_only
def test_a_quarantined_or_withdrawn_file_is_no_conversion_of_the_free_ceiling(pgc, tmp_path):
    """auditor-C2a round 2 F6 (OWN7): Kats_2019's file lands through the b1 fire's CONTROL arm (its REAL recorded S2
    answer; the arXiv PDF CONSTRUCTED) -> 0; then the landed file's version is CONSTRUCTED into `quarantined` status
    (an owner UPDATE on the worker database: no write function makes one today) -> 1; back to `active` but in state
    `withdrawn` -> 1; restored -> 0."""
    _reset_and_migrate(pgc)
    assert C2A.fire_b1_disabled_kats(pgc, "control", tmp_path) == 0
    m = {"repo": str(REPO), "probe_csvs": {C2A.HEAD_PROBE: str(tmp_path / C2A.HEAD_PROBE)}, "wayback_positive_dois": []}
    vid = pgc.execute("SELECT f.version_id FROM litkb.main_files f JOIN litkb.main_identifiers i ON i.work_id = "
                      "f.work_id WHERE i.scheme = 'doi' AND i.value_norm = %s", (C2A.ROWS["kats"]["doi"],)).fetchone()[0]
    state, at = pgc.execute("SELECT state, promoted_at FROM litkb.file_versions WHERE version_id = %s",
                            (vid,)).fetchone()
    assert C2A.free_ceiling_measured_unconverted(pgc, m) == 0
    # (a `promoted_at` is carried only by a promoted version: the table's own check)
    # auditor-C2a round 3 F2 (OWN12, integrator-w3): B2's refuse verb leaves `status` active and sets state `rejected`
    for status, st, when, want in (("quarantined", state, at, 1), ("active", state, at, 0),
                                   ("active", "withdrawn", None, 1), ("active", "rejected", None, 1),
                                   ("active", state, at, 0)):
        pgc.execute("UPDATE litkb.file_versions SET status = %s, state = %s, promoted_at = %s WHERE version_id = %s",
                    (status, st, when, vid))
        assert C2A.free_ceiling_measured_unconverted(pgc, m) == want, (status, st)


def test_a2_tightens_on_a_crossref_book_answer_too():
    """auditor-C2a round 2 F6 (OWN10): the plan's router stops "a preprint or a book" — a Crossref `book` /
    `monograph` answer moves an article-typed work to `book`, off the shadow tier; nothing moves it back."""
    from litkb.acquire import policy as P
    from litkb.acquire import stage_a as A

    for t in ("book", "monograph", "edited-book"):
        assert A.tighten("paper", A.crossref_class({"type": t})) == "book", t
    assert A.tighten("book", "paper") == "book"
    assert not A.routed(P.decide("annas", shadow_enabled=True), A.tighten("paper", "book")).allowed


def test_the_asked_url_dedupe_is_by_url_never_by_host():
    """auditor-C2a round 2 F6 (OWN5): two candidate URLs on ONE host, the first serving a page, the second the PDF
    -> both asked, the second lands. CONSTRUCTED answers."""
    from litkb.acquire import stage_b as B

    s = Stub({"x.example/landing": (200, {}, b"<html><head><title>An article</title></head></html>"),
              "x.example/file.pdf": (200, {}, _pdf())})
    r = B.fetch_candidates("openalex", [("https://x.example/landing", {}), ("https://x.example/file.pdf", {})],
                           Ctx({"openalex": s}), {})
    assert r["status"] == "downloaded" and [u for u, _a in s.calls] == ["https://x.example/landing",
                                                                        "https://x.example/file.pdf"]


def test_the_arxiv_rung_never_re_asks_the_pdf_the_open_access_rung_asked():
    """auditor-C2a round 2 F10: C1a's `open_access` asks arxiv.org/pdf/<the work's own arXiv id> first; the `arxiv`
    rung later in the same ladder run books that URL as asked by it and asks only the OTHER arXiv ids it holds (an
    edition edge's). Without an allowed open_access decision in the run it asks the own id. CONSTRUCTED answers."""
    from litkb.acquire import stage_b as B

    work = {"doi": "10.48550/arxiv.2104.08663", "arxiv": None,
            "ids": [("arxiv", "2104.08663", "own"), ("arxiv", "2206.01062", "has_version")]}
    ctx = Ctx({"arxiv": Stub({"arxiv.org": (404, {}, b"")})})
    ctx.decisions = {"open_access": {"route": "open_access", "allowed": True}}
    r = B.rung_arxiv(dict(work), ctx)
    assert [u for u, _a in ctx.clients["arxiv"].calls] == ["https://arxiv.org/pdf/2206.01062"]
    assert "already asked in this ladder run by open_access" in r["detail"], r
    ctx = Ctx({"arxiv": Stub({"arxiv.org": (404, {}, b"")})})
    ctx.decisions = {"open_access": {"route": "open_access", "allowed": False}}
    B.rung_arxiv(dict(work), ctx)
    assert len(ctx.clients["arxiv"].calls) == 2


def test_an_oai_pmh_error_served_at_200_leaves_the_eartharxiv_walk_incomplete(tmp_path):
    """auditor-C2a round 2 F4 (its reproduction): OAI-PMH 2.0 §3.6 carries a protocol error INSIDE an HTTP 200 —
    a CONSTRUCTED feed whose second page is `<error code="badResumptionToken">` -> exit 1, no map; an unparseable 200
    -> exit 1; `noRecordsMatch` on the FIRST page is the empty list -> a complete walk (a map with no row)."""
    page1 = _OAI_PAGE.format(n=1, token="<resumptionToken>tok-2</resumptionToken>").encode()
    err = (b'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
           b'<error code="%s">CONSTRUCTED</error></OAI-PMH>')

    class Feed:
        def __init__(self, first, second):
            self.first, self.second = first, second

        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            return self.first if "metadataPrefix" in url else self.second

    def quiet(*a, **k):
        return None

    for n, second in enumerate(((200, {}, err % b"badResumptionToken"), (200, {}, b"<html>not xml"))):
        out = tmp_path / f"map{n}.csv"
        assert EMAP.run_live(out, client=Feed((200, {}, page1), second), pace_s=0, printer=quiet) == 1
        assert not out.exists() and (tmp_path / f"map{n}.partial.csv").is_file()
    out = tmp_path / "empty.csv"
    assert EMAP.run_live(out, client=Feed((200, {}, err % b"noRecordsMatch"), None), pace_s=0, printer=quiet) == 0
    with open(out, encoding="utf-8", newline="") as f:
        assert list(csv.DictReader(f)) == []
    assert EMAP.oai_error(err % b"badArgument") == "badArgument" and EMAP.oai_error(page1) == ""


@pg_only
def test_a_conditional_rung_its_condition_skipped_on_every_row_prints_a_not_asked_line(pgc, tmp_path):
    """auditor-C2a round 2 F3 (C2a's half): on live 0 works hold a zenodo or a figshare DOI or a PMCID, so those rungs
    ask nobody and their yield lines read `=0/0`. Kats_2019 (a 10.1007 DOI, CONSTRUCTED admission) through the REAL
    ladder on `zenodo`, `europepmc` and `figshare` -> each rung's own ask condition skips it; `osf` gets one
    CONSTRUCTED `no-oa-copy` attempt; `figshare` ALSO one CONSTRUCTED back-off skip on the E13 work (a skip for
    another reason). The lines: `zenodo` and `europepmc` print `not-asked: <route> 1 <the registry's condition>`
    beside a `=0/0` yield line (a skip is never counted as asked — OWN4); `figshare` prints none (one row skipped
    for another reason); `osf` prints none (it asked a row); a rung no row reached (`hal`) prints none."""
    from litkb.acquire import run as R
    from litkb.acquire import stage_b as B

    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("not-asked")
        kats, e13 = w.admit(ws, C2A.ROWS["kats"]), w.admit(ws, C2A.ROWS["e13"])
        frozen = w.now()
        w.acquire(ws, kats, {}, routes=("zenodo", "europepmc", "figshare"))
        R.record_attempt(w.writer, ws, w.tokens[ws], kats["work_id"], "osf", kats["doi"], "no-oa-copy",
                         {"note": "CONSTRUCTED"}, [200])
        R.record_attempt(w.writer, ws, w.tokens[ws], e13["work_id"], "figshare", e13["doi"], "skipped",
                         {"next_allowed_at": "CONSTRUCTED", "refusals": 1}, sub_status="backoff_window")
        m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "repo": str(REPO),
             "probe_csvs": {C2A.CROSSWALK_PROBE: f"phase4/qc/{C2A.CROSSWALK_PROBE}"}}
        lines = C2A.report_lines(pgc, m)
        assert C2A.condition_skips(pgc, m, "zenodo") == (1, 0) and C2A.condition_skips(pgc, m, "figshare") == (1, 1)
    finally:
        w.close()
    reg = {r.route: r for r in R.RUNGS}
    assert "yield: zenodo=0/0" in lines and "yield: europepmc=0/0" in lines and "yield: osf=0/1" in lines
    assert [ln for ln in lines if ln.startswith("not-asked: ")] == [
        f"not-asked: zenodo 1 {B.ASK_CONDITIONS['zenodo']}", f"not-asked: europepmc 1 {B.ASK_CONDITIONS['europepmc']}"]
    assert reg["zenodo"].ask_condition == B.ASK_CONDITIONS["zenodo"] and reg["hal"].ask_condition == ""
    assert set(B.ASK_CONDITIONS) <= {t[0] for t in B.RUNG_TABLE}


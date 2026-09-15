"""The Anna's Archive gates, ported with litkb.acquire.annas from D:\\tools\\annas-mcp\\test_aa_fetch.py (2026-09-13;
design §10: "its test file moves with it"). Stubbed HTTP throughout.

    py -3.12 -m pytest qc/test_litkb_annas.py

Port changes, and only these: the module under test is litkb.acquire.annas; the three live tests are resolve-only
(the ported fetch_one refuses to write into a literature folder, and running the suite never spends a download)
and run only with LITKB_LIVE=1 (or AA_LIVE=1); one test is added for that destination guard. The original file
defines 80 tests; this one defines 95 — the port's 81, plus TestRedactionSites, one test per netutil.redact /
add_secret call site outside litkb.acquire.run (2026-09-14, closing DEFERRED_HELPERS).
Nothing here writes under D:\\edmonds-pipeline\\Literture.
"""
import contextlib
import csv
import hashlib
import io
import json
import os
import tempfile
import unittest
import urllib.parse
import uuid

import pytest

import litkb.acquire.annas as A
import litkb.netutil as N


def isolate_secrets(tc):
    """A fake key nothing else has registered, and a cleanup that puts netutil._SECRETS back.

    _SECRETS is a module-level list that annas.py imports BY NAME, so it is one shared object: a key registered by
    an earlier test would redact this one's plant, and a stripped call site would then look guarded. The list is
    restored in place (cleared and refilled), never rebound, so the name annas.py holds keeps pointing at it.
    The key carries a '+' so redact()'s URL-quoted alias (%2B) is exercised, and no '/' so it is filename-safe."""
    snapshot = list(N._SECRETS)

    def restore():
        N._SECRETS.clear()
        N._SECRETS.extend(snapshot)
    tc.addCleanup(restore)
    return "FAKEKEY" + uuid.uuid4().hex + "+z"


DOI = "10.1198/016214504000000692"
MD5 = "6dbfc27b03a0a0a255aa667a27640621"
TITLE = "The Estimation of Prediction Error: Covariance Penalties and Cross-Validation"


def make_pdf(body=b"x"):
    return b"%PDF-1.4\n" + body + b"\n%%EOF\n"


def scidb_html(md5=MD5):
    return (f'<html><body><ul><li>- <a href="/md5/{md5}">Record in Anna\u2019s Archive</a>'
            f'</li></ul></body></html>').encode()


def record_json(doi=DOI, ext="pdf", size=0, title=TITLE):
    return json.dumps({"id": f"md5:{MD5}", "file_unified_data": {
        "identifiers_unified": {"doi": [doi], "md5": [MD5]},
        "extension_best": ext, "filesize_best": size, "title_best": title,
        "author_best": "Efron, B.", "year_best": "2004",
        "edition_varia_best": "JASA, 99, 619-632"}}).encode()


class StubClient:
    """Routes by URL substring.  Each route is (status, headers, body) or a callable."""

    base = A.BASE

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        self.calls.append((url, follow))
        for frag, resp in self.routes.items():
            if frag in url:
                return resp(url) if callable(resp) else resp
        raise AssertionError(f"no stub route for {url}")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.paths = {"dest": os.path.join(d, "dest"), "quarantine": os.path.join(d, "quar"),
                      "staging": os.path.join(d, "stage"),
                      "manifest": os.path.join(d, "dest", "manifest.csv")}
        os.makedirs(self.paths["dest"])
        with open(self.paths["manifest"], "w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=A.MANIFEST_FIELDS).writeheader()
        self.pacer = A.Pacer(interval=0, sleep=lambda s: None)
        self.addCleanup(self.tmp.cleanup)

    def quarantined(self):
        q = self.paths["quarantine"]
        return sorted(os.listdir(q)) if os.path.isdir(q) else []

    def run_job(self, routes, stem="Efron_2004_test", doi=DOI, meta=None):
        return A.fetch_one(StubClient(routes), "SEKRIT", doi, stem, meta or {},
                           self.paths, self.pacer)

    def _stub_extract(self, text):
        """Force a deterministic -layout dump instead of shelling out to pdftotext."""
        real = A.subprocess.run

        def fake(cmd, *a, **k):
            if cmd and cmd[0] == "pdftotext":
                open(cmd[-1], "w", encoding="utf-8").write(text)
                return None
            return real(cmd, *a, **k)
        A.subprocess.run = fake
        self.addCleanup(lambda: setattr(A.subprocess, "run", real))


# ------------------------------------------------------------------ gate 1

class TestResolve(Base):
    def test_redirect_to_search_is_not_in_archive(self):
        loc = '/search?index=journals&q="doi:10.1016/j.isprsjprs.2024.07.028"'
        r = self.run_job({"/scidb/": (302, {"Location": loc}, b""),
                          "/search?": (200, {}, b"<html>no results</html>")},
                         doi="10.1016/j.isprsjprs.2024.07.028")
        self.assertEqual(r["status"], "not-in-archive")
        self.assertEqual(r["md5"], "")
        self.assertIn("/search", r["location"])

    def test_absolute_search_location_also_not_in_archive(self):
        loc = A.BASE + '/search?index=journals&q="doi:x"'
        r = self.run_job({"/scidb/": (302, {"Location": loc}, b""),
                          "/search?": (200, {}, b"<html>no results</html>")})
        self.assertEqual(r["status"], "not-in-archive")

    def test_benign_308_is_followed_then_resolved(self):
        seen = []

        def scidb(url):
            seen.append(url)
            if len(seen) == 1:
                return 308, {"Location": A.BASE + f"/scidb/{DOI}/"}, b""
            return 200, {}, scidb_html()
        r = self.run_job({"/scidb/": scidb,
                          "/db/aarecord_elasticsearch/": (200, {}, record_json()),
                          "fast_download": (200, {}, json.dumps({}).encode())})
        self.assertEqual(r["md5"], MD5)
        self.assertEqual(r["status"], "api-error")

    def test_non_md5_record_id_is_unresolved(self):
        html = b'<a href="/nexusstc_download/abc123def">Record in Anna\xe2\x80\x99s Archive</a>'
        r = self.run_job({"/scidb/": (200, {}, html)})
        self.assertEqual(r["status"], "unresolved")

    def test_doi_without_10_prefix_makes_no_request(self):
        r = self.run_job({}, doi="not-a-doi")
        self.assertEqual(r["status"], "unresolved")

    def test_normalize_doi(self):
        self.assertEqual(A.normalize_doi(" https://doi.org/10.1/AB "), "10.1/ab")
        self.assertEqual(A.normalize_doi("nope"), "")


# ------------------------------------------------------------------ gate 1b: search fallback

OTHER = "a" * 32


def search_html(*md5s):
    cards = "".join(f'<div class="card"><a href="/md5/{m}">x</a><a href="/md5/{m}">y</a></div>'
                    for m in md5s)
    return f"<html><body>{cards}</body></html>".encode()


class TestSearchFallback(Base):
    def test_first_candidate_is_rejected_and_the_matching_one_wins(self):
        def rec(url):
            if OTHER in url:
                return 200, {}, record_json(doi="10.9999/unrelated")
            return 200, {}, record_json()
        r = self.run_job({"/scidb/": (302, {"Location": "/search?index=journals&q=x"}, b""),
                          "/search?": (200, {}, search_html(OTHER, MD5)),
                          "/db/aarecord_elasticsearch/": rec,
                          "fast_download": (200, {}, b"{}")})
        self.assertEqual(r["md5"], MD5)
        self.assertIn("via=search", r["detail"])

    def test_no_candidate_matches_stays_not_in_archive(self):
        r = self.run_job({"/scidb/": (302, {"Location": "/search?index=journals&q=x"}, b""),
                          "/search?": (200, {}, search_html(OTHER)),
                          "/db/aarecord_elasticsearch/":
                              (200, {}, record_json(doi="10.9999/unrelated"))})
        self.assertEqual(r["status"], "not-in-archive")
        self.assertEqual(r["md5"], "")

    EMPTY_200 = (f'<html><body><a href="/scidb/{DOI}/">reload</a>'
                 f'<p>No results</p></body></html>').encode()

    def test_scidb_200_without_anchors_falls_through_to_search(self):
        def rec(url):
            if OTHER in url:
                return 200, {}, record_json(doi="10.9999/unrelated")
            return 200, {}, record_json()
        stub = StubClient({"/scidb/": (200, {}, self.EMPTY_200),
                           "/search?": (200, {}, search_html(OTHER, MD5)),
                           "/db/aarecord_elasticsearch/": rec,
                           "fast_download": (200, {}, b"{}")})
        r = A.fetch_one(stub, "SEKRIT", DOI, "Cohen_2018_test", {}, self.paths, self.pacer)
        self.assertTrue(any("/search?" in u for u, _ in stub.calls))
        self.assertEqual(r["md5"], MD5)
        self.assertIn("via=scidb-empty+search", r["detail"])

    def test_scidb_200_without_anchors_and_no_match_is_not_in_archive(self):
        stub = StubClient({"/scidb/": (200, {}, self.EMPTY_200),
                           "/search?": (200, {}, search_html(OTHER)),
                           "/db/aarecord_elasticsearch/":
                               (200, {}, record_json(doi="10.9999/unrelated"))})
        r = A.fetch_one(stub, "SEKRIT", DOI, "Cohen_2018_test", {}, self.paths, self.pacer)
        self.assertTrue(any("/search?" in u for u, _ in stub.calls))
        self.assertEqual(r["status"], "not-in-archive")
        self.assertEqual(r["md5"], "")
        self.assertIn("via=scidb-empty+search", r["detail"])

    def test_candidate_list_is_deduped_in_page_order_and_capped(self):
        stub = StubClient({"/scidb/": (302, {"Location": "/search?q=x"}, b""),
                           "/search?": (200, {}, search_html(*[f"{i:032x}" for i in range(20)])),
                           "/db/aarecord_elasticsearch/":
                               (200, {}, record_json(doi="10.9999/unrelated"))})
        A.fetch_one(stub, "SEKRIT", DOI, "s", {}, self.paths, self.pacer)
        recs = [u for u, _ in stub.calls if "aarecord_elasticsearch" in u]
        self.assertEqual(len(recs), A.SEARCH_CANDIDATE_CAP)
        self.assertIn(f"md5:{0:032x}.json", recs[0])


# ------------------------------------------------------------------ gate 2

class TestRecord(Base):
    def test_record_doi_mismatch(self):
        r = self.run_job({"/scidb/": (200, {}, scidb_html()),
                          "/db/aarecord_elasticsearch/": (200, {}, record_json(doi="10.9/other"))})
        self.assertEqual(r["status"], "record-mismatch")
        self.assertEqual(r["record_doi"], "10.9/other")
        self.assertEqual(self.quarantined(), [])

    def test_non_pdf_extension_is_mismatch(self):
        r = self.run_job({"/scidb/": (200, {}, scidb_html()),
                          "/db/aarecord_elasticsearch/": (200, {}, record_json(ext="djvu"))})
        self.assertEqual(r["status"], "record-mismatch")

    def test_exists_short_circuits_before_download(self):
        open(os.path.join(self.paths["dest"], "Efron_2004_test.pdf"), "wb").write(make_pdf())
        stub = StubClient({"/scidb/": (200, {}, scidb_html()),
                           "/db/aarecord_elasticsearch/": (200, {}, record_json())})
        r = A.fetch_one(stub, "SEKRIT", DOI, "Efron_2004_test", {}, self.paths, self.pacer)
        self.assertEqual(r["status"], "exists")
        self.assertFalse(any("fast_download" in u for u, _ in stub.calls))


# ------------------------------------------------------------------ gate 3

class TestFile(Base):
    def routes(self, pdf, size=0, title=TITLE):
        return {"/scidb/": (200, {}, scidb_html()),
                "/db/aarecord_elasticsearch/": (200, {}, record_json(size=size, title=title)),
                "fast_download": (200, {}, json.dumps(
                    {"download_url": "https://p.example/x.pdf",
                     "account_fast_download_info": {"downloads_left": 997}}).encode()),
                "p.example": (200, {}, pdf)}

    def test_hash_mismatch_quarantines(self):
        r = self.run_job(self.routes(make_pdf(b"wrong paper")))
        self.assertEqual(r["status"], "hash-mismatch")
        self.assertEqual(self.quarantined(), [f"Efron_2004_test__hash-mismatch__"
                                              f"{hashlib.md5(make_pdf(b'wrong paper')).hexdigest()}.pdf"])
        self.assertFalse(os.path.exists(os.path.join(self.paths["dest"], "Efron_2004_test.pdf")))

    def test_bad_file_header(self):
        r = self.run_job(self.routes(b"<html>not a pdf</html>"))
        self.assertEqual(r["status"], "bad-file")
        self.assertEqual(self.quarantined(), [])

    def test_content_mismatch_quarantines(self):
        pdf = make_pdf(b"z")
        md5 = hashlib.md5(pdf).hexdigest()
        routes = self.routes(pdf, title="A Totally Different Paper About Bees")
        routes["/scidb/"] = (200, {}, scidb_html(md5))
        routes["/db/aarecord_elasticsearch/"] = (
            200, {}, json.dumps({"file_unified_data": {
                "identifiers_unified": {"doi": [DOI]}, "extension_best": "pdf",
                "filesize_best": 0, "title_best": "A Totally Different Paper About Bees"}}).encode())
        self._stub_extract(
            "Tidal mixing fronts in the Irish Sea and their seasonal persistence\n"
            "J. H. Simpson and R. D. Pingree\n\n"
            "ABSTRACT  Observations from six summer cruises show that the position of the\n"
            "shelf-sea front is controlled by the ratio of water depth to the cube of the\n"
            "tidal stream amplitude, and that the front migrates only weakly between years.\n"
            "Vertical profiles of temperature and salinity are presented for each section.\n")
        r = A.fetch_one(StubClient(routes), "SEKRIT", DOI, "Efron_2004_test", {},
                        self.paths, self.pacer)
        self.assertEqual(r["status"], "content-mismatch")
        self.assertTrue(any("content-mismatch" in n for n in self.quarantined()))

    def test_content_match_writes_everything(self):
        pdf = make_pdf(b"z")
        md5 = hashlib.md5(pdf).hexdigest()
        routes = self.routes(pdf, size=len(pdf))
        routes["/scidb/"] = (200, {}, scidb_html(md5))
        self._stub_extract(
            "Journal of the American Statistical Association          Vol. 99, No. 467\n\n"
            + TITLE + "\n\nBradley EFRON\n\n"
            "Having estimated a regression model by some fitting procedure, the statistician\n"
            "wishes to know how well it will predict future observations drawn from the same\n"
            "population. Cross-validation and covariance penalties are two families of answers.\n")
        r = A.fetch_one(StubClient(routes), "SEKRIT", DOI, "Efron_2004_test", {},
                        self.paths, self.pacer)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["downloads_left"], 997)
        self.assertTrue(os.path.exists(os.path.join(self.paths["dest"], "Efron_2004_test.pdf")))
        rows = list(csv.DictReader(open(self.paths["manifest"], encoding="utf-8")))
        self.assertEqual(rows[-1]["doi"], DOI)
        self.assertEqual(rows[-1]["source_route"], A.SOURCE_ROUTE)
        self.assertEqual(rows[-1]["verified_against_extract"], "title")

    def test_scanned_pdf_with_no_text_layer_is_accepted_as_indeterminate(self):
        pdf = make_pdf(b"z")
        md5 = hashlib.md5(pdf).hexdigest()
        routes = self.routes(pdf, title="A Natural Identity for Exponential Families")
        routes["/scidb/"] = (200, {}, scidb_html(md5))
        routes["/db/aarecord_elasticsearch/"] = (200, {}, json.dumps({"file_unified_data": {
            "identifiers_unified": {"doi": [DOI]}, "extension_best": "pdf", "filesize_best": 0,
            "title_best": "A Natural Identity for Exponential Families"}}).encode())
        self._stub_extract("\f\f\f\f\fInstitute of Mathematical Statistics\f\f\f")
        r = A.fetch_one(StubClient(routes), "SEKRIT", DOI, "Efron_2004_test", {},
                        self.paths, self.pacer)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(self.quarantined(), [])
        rows = list(csv.DictReader(open(self.paths["manifest"], encoding="utf-8")))
        self.assertEqual(rows[-1]["verified_against_extract"], "record (no text layer)")

    def test_duplicate_hash_quarantines(self):
        pdf = make_pdf(b"z")
        md5 = hashlib.md5(pdf).hexdigest()
        with open(self.paths["manifest"], "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=A.MANIFEST_FIELDS)
            w.writerow({k: "" for k in A.MANIFEST_FIELDS} |
                       {"stem": "already", "sha256": hashlib.sha256(pdf).hexdigest()})
        routes = self.routes(pdf)
        routes["/scidb/"] = (200, {}, scidb_html(md5))
        r = A.fetch_one(StubClient(routes), "SEKRIT", DOI, "Efron_2004_test", {},
                        self.paths, self.pacer)
        self.assertEqual(r["status"], "duplicate-hash")
        self.assertTrue(any("duplicate-hash" in n for n in self.quarantined()))

    def test_fetch_one_refuses_a_literature_folder(self):
        """litkb port: fetch_one never files into Validation/ (or any topic folder); the guard runs before any
        request, so the stub client (which raises on any call) is never reached."""
        paths = dict(self.paths, dest=A.DEST, manifest=os.path.join(A.DEST, "manifest.csv"))
        with self.assertRaises(A.DestinationRefused):
            A.fetch_one(StubClient({}), "SEKRIT", DOI, "Efron_2004_test", {}, paths, self.pacer)


# ------------------------------------------------------------------ gate 3: empty title_best

JSTOR_DOI = "10.2307/2333009"
JSTOR_TITLE = "Some Statistical Problems Connected with Crystal Lattices"
JSTOR_BODY = ("Biometrika Trust\n\n" + JSTOR_TITLE + "\nAuthor(s): A. N. Other\n"
              "Source: Biometrika, Vol. 41, No. 1/2 (Jun., 1954), pp. 1-20\n"
              "Published by: Oxford University Press on behalf of Biometrika Trust\n"
              "Your use of the JSTOR archive indicates your acceptance of the Terms & Conditions\n"
              "of Use, available at the publisher's site, and applies to this copy only.\n")


class TestTitleFallback(Base):
    def routes(self, pdf, doi=JSTOR_DOI, title=""):
        md5 = hashlib.md5(pdf).hexdigest()
        r = {"/scidb/": (200, {}, scidb_html(md5)),
             "/db/aarecord_elasticsearch/": (200, {}, json.dumps({"file_unified_data": {
                 "identifiers_unified": {"doi": [doi]}, "extension_best": "pdf",
                 "filesize_best": len(pdf), "title_best": title}}).encode()),
             "fast_download": (200, {}, json.dumps(
                 {"download_url": "https://p.example/x.pdf",
                  "account_fast_download_info": {"downloads_left": 981}}).encode()),
             "p.example": (200, {}, pdf)}
        return r

    def job(self, text, meta=None, crossref=(404, {}, b""), doi=JSTOR_DOI, record_title=""):
        pdf = make_pdf(b"jstor")
        self._stub_extract(text)
        registry = StubClient({"api.crossref.org/works/": crossref})
        r = A.fetch_one(StubClient(self.routes(pdf, doi=doi, title=record_title)), "SEKRIT", doi,
                        "Other_1954_test", meta or {}, self.paths, self.pacer, registry, self.pacer)
        return r, registry

    def test_empty_title_best_uses_the_job_title(self):
        r, reg = self.job(JSTOR_BODY, meta={"title": JSTOR_TITLE})
        self.assertEqual(r["status"], "ok", A.log_line(r))
        self.assertIn("verified_against_extract=title; title_src=job", r["detail"])
        self.assertEqual(reg.calls, [])
        rows = list(csv.DictReader(open(self.paths["manifest"], encoding="utf-8")))
        self.assertEqual(rows[-1]["title"], JSTOR_TITLE)

    def test_empty_title_best_and_no_job_title_asks_crossref_by_doi(self):
        cr = (200, {}, json.dumps({"message": {"title": [JSTOR_TITLE]}}).encode())
        r, reg = self.job(JSTOR_BODY, crossref=cr)
        self.assertEqual(r["status"], "ok", A.log_line(r))
        self.assertIn("title_src=crossref", r["detail"])
        self.assertEqual(len(reg.calls), 1)
        self.assertTrue(reg.calls[0][0].endswith("/works/" + JSTOR_DOI))

    def test_record_title_wins_when_present(self):
        r, reg = self.job(JSTOR_BODY, meta={"title": "Unrelated Job Title About Bees"},
                          record_title=JSTOR_TITLE)
        self.assertEqual(r["status"], "ok", A.log_line(r))
        self.assertIn("title_src=record", r["detail"])
        self.assertEqual(reg.calls, [])

    def test_jstor_stable_url_satisfies_a_10_2307_doi(self):
        text = "This content downloaded from 1.2.3.4\nhttps://www.jstor.org/stable/2333009\n" \
               + "glyph soup " * 40
        r, reg = self.job(text)
        self.assertEqual(r["status"], "ok", A.log_line(r))
        self.assertIn("verified_against_extract=doi", r["detail"])
        self.assertEqual(reg.calls, [])

    def test_no_title_anywhere_is_indeterminate_not_a_rejection(self):
        r, reg = self.job("unrelated words about tidal fronts " * 20)
        self.assertEqual(r["status"], "ok", A.log_line(r))
        self.assertIn("verified_against_extract=record (no title available); title_src=none",
                      r["detail"])
        self.assertEqual(self.quarantined(), [])
        rows = list(csv.DictReader(open(self.paths["manifest"], encoding="utf-8")))
        self.assertEqual(rows[-1]["verified_against_extract"], "record (no title available)")

    def test_a_real_mismatch_with_a_job_title_still_quarantines(self):
        r, _ = self.job("Tidal mixing fronts in the Irish Sea and their seasonal persistence\n" * 8,
                        meta={"title": JSTOR_TITLE})
        self.assertEqual(r["status"], "content-mismatch")
        self.assertIn("title_src=job", r["detail"])
        self.assertTrue(any("content-mismatch" in n for n in self.quarantined()))

    def test_bad_file_log_line_carries_rec_size(self):
        pdf = make_pdf(b"jstor")
        routes = self.routes(pdf)
        routes["p.example"] = (404, {}, b"<html>404</html>")
        self.pacer.sleep = lambda s: None
        r = A.fetch_one(StubClient(routes), "SEKRIT", JSTOR_DOI, "Other_1954_test", {},
                        self.paths, self.pacer)
        line = A.log_line(r)
        self.assertEqual(r["status"], "bad-file")
        self.assertIn(f" | bytes=0 | left=981 | rec_size={len(pdf)} | ", line)
        self.assertNotIn("SEKRIT", line)


# ------------------------------------------------------------------ download ladder

class TestDownloadLadder(Base):
    def test_partner_404_retries_domain_index_then_record_options(self):
        pdf = make_pdf(b"z")
        md5 = hashlib.md5(pdf).hexdigest()
        hits = []

        def api(url):
            hits.append(url)
            di = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("domain_index", [""])[0]
            return 200, {}, json.dumps({
                "download_url": f"https://p{di}.example/x.pdf",
                "account_fast_download_info": {"downloads_left": 900}}).encode()
        routes = {"/scidb/": (200, {}, scidb_html(md5)),
                  "/db/aarecord_elasticsearch/": (200, {}, json.dumps({
                      "file_unified_data": {"identifiers_unified": {"doi": [DOI]},
                                            "extension_best": "pdf", "filesize_best": 0,
                                            "title_best": TITLE},
                      "additional": {"download_urls": [
                          ["IPFS", "/ipfs_downloads/md5:x", ""],
                          ["Sci-Hub", "https://sci-hub.ru/" + DOI, ""]]}}).encode()),
                  "fast_download": api,
                  "p0.example": (404, {}, b"<html>404</html>"),
                  "p1.example": (404, {}, b"<html>404</html>"),
                  "p2.example": (404, {}, b"<html>404</html>"),
                  "/ipfs_downloads/": (500, {}, b"nope"),
                  "sci-hub.ru": (200, {}, pdf)}
        self._no_sleep()
        self._stub_extract("Journal of the American Statistical Association\n" + TITLE +
                           "\nBradley EFRON\nAbstract: covariance penalties and cross validation "
                           "are compared for estimating prediction error in regression models.\n")
        r = A.fetch_one(StubClient(routes), "SEKRIT", DOI, "Efron_2004_test", {},
                        self.paths, self.pacer)
        self.assertEqual(r["status"], "ok")
        dis = [urllib.parse.parse_qs(urllib.parse.urlparse(u).query)["domain_index"][0]
               for u in hits]
        self.assertEqual(dis, ["0", "1", "2"])
        self.assertNotIn("path_index", hits[0])
        self.assertIn("sci-hub.ru", r["detail"])

    def test_all_hosts_fail_reports_bad_file_with_hosts_tried(self):
        pdf = make_pdf(b"z")
        md5 = hashlib.md5(pdf).hexdigest()
        routes = {"/scidb/": (200, {}, scidb_html(md5)),
                  "/db/aarecord_elasticsearch/": (200, {}, record_json()),
                  "fast_download": (200, {}, json.dumps(
                      {"download_url": "https://p.example/x.pdf",
                       "account_fast_download_info": {"downloads_left": 5}}).encode()),
                  "p.example": (404, {}, b"<html>404</html>")}
        self._no_sleep()
        r = A.fetch_one(StubClient(routes), "SEKRIT", DOI, "Efron_2004_test", {},
                        self.paths, self.pacer)
        self.assertEqual(r["status"], "bad-file")
        self.assertEqual(r["detail"].count("p.example:404"), 3)
        self.assertEqual(self.quarantined(), [])

    def test_download_options_reads_both_lists_in_order(self):
        opts = A.download_options({
            "download_urls": [["Nexus/STC", "https://libstc.cc/#/x", "note"], ["bad"], ["N", ""]],
            "ipfs_urls": [{"name": "filebase", "url": "https://ipfs.filebase.io/ipfs/q"}]})
        self.assertEqual([n for n, _ in opts], ["Nexus/STC", "ipfs/filebase"])

    def _no_sleep(self):
        self.pacer.sleep = lambda s: None


# ------------------------------------------------------------------ FlareSolverr (optional)

class TestFlareSolverr(unittest.TestCase):
    def test_challenge_detection(self):
        self.assertTrue(A.Client.is_challenge(403, "https://x/y?&check=1", b""))
        self.assertTrue(A.Client.is_challenge(403, "https://x/y", b"<h1>Just a moment...</h1>"))
        self.assertTrue(A.Client.is_challenge(503, "https://x/y", b"DDoS-Guard"))
        self.assertTrue(A.Client.is_challenge(403, "https://x/y", b"Checking your browser"))
        self.assertFalse(A.Client.is_challenge(200, "https://x/y", b"<html>fine</html>"))
        self.assertFalse(A.Client.is_challenge(403, "https://x/y", b"Account not allowed"))

    def test_cookies_and_ua_are_adopted_and_the_request_is_retried_once(self):
        c = A.Client(flaresolverr="http://localhost:8191")
        c._flare_post = lambda payload: {"solution": {
            "userAgent": "FlareUA/1.0",
            "cookies": [{"name": "cf_clearance", "value": "tok3n",
                         "domain": "annas-archive.gl", "path": "/"}]}}
        seen = []

        def raw(url, accept, timeout, follow, data):
            seen.append(c.ua)
            if len(seen) == 1:
                return 403, {}, b"<html>Just a moment...</html>"
            return 200, {}, b"<html>ok</html>"
        c._raw_get = raw
        st, _, body = c.get(A.BASE + "/scidb/x/")
        self.assertEqual((st, body), (200, b"<html>ok</html>"))
        self.assertEqual(seen, [A.UA, "FlareUA/1.0"])
        self.assertIn("cf_clearance", [ck.name for ck in c.cj])

    def test_without_flaresolverr_the_challenge_is_returned_unchanged(self):
        c = A.Client(flaresolverr="")
        c._raw_get = lambda *a: (403, {}, b"Just a moment")
        c._flare_post = lambda p: self.fail("must not call FlareSolverr when unconfigured")
        self.assertEqual(c.get(A.BASE + "/x")[0], 403)

    def test_flaresolverr_failure_is_not_fatal(self):
        c = A.Client(flaresolverr="http://localhost:8191")

        def boom(payload):
            raise OSError("connection refused")
        c._flare_post = boom
        c._raw_get = lambda *a: (403, {}, b"Just a moment")
        self.assertEqual(c.get(A.BASE + "/x")[0], 403)


# ------------------------------------------------------------------ --audit (read-only)

class TestAudit(Base):
    def _pdf(self, stem, body=b"z"):
        pdf = make_pdf(body)
        os.makedirs(self.paths["dest"], exist_ok=True)
        with open(os.path.join(self.paths["dest"], stem + ".pdf"), "wb") as fh:
            fh.write(pdf)
        return pdf, hashlib.md5(pdf).hexdigest()

    def _txt(self, stem, text):
        with open(os.path.join(self.paths["dest"], stem + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_audit_flags_a_size_mismatch_and_moves_nothing(self):
        stem = "Bad_2001_x"
        pdf, md5 = self._pdf(stem)
        self._txt(stem, "irrelevant " * 60)
        stub = StubClient({"/scidb/": (200, {}, scidb_html(md5)),
                           "/db/aarecord_elasticsearch/":
                               (200, {}, record_json(size=len(pdf) + 999))})
        r = A.audit_one(stub, {"stem": stem, "doi": DOI}, self.paths, self.pacer)
        self.assertEqual(r["status"], "audit-fail")
        self.assertIn("filesize_best", r["detail"])
        self.assertTrue(os.path.exists(os.path.join(self.paths["dest"], stem + ".pdf")))
        self.assertEqual(self.quarantined(), [])

    def test_audit_flags_a_content_mismatch(self):
        stem = "Garbled_2002_x"
        pdf, md5 = self._pdf(stem)
        self._txt(stem, "§¶ garbled glyph soup " * 40)
        stub = StubClient({"/scidb/": (200, {}, scidb_html(md5)),
                           "/db/aarecord_elasticsearch/": (200, {}, record_json(size=len(pdf)))})
        r = A.audit_one(stub, {"stem": stem, "doi": DOI}, self.paths, self.pacer)
        self.assertEqual(r["status"], "audit-fail")
        self.assertIn("content", r["detail"])

    def test_audit_passes_a_good_file(self):
        stem = "Good_2004_x"
        pdf, md5 = self._pdf(stem)
        self._txt(stem, f"Some front matter\nDOI: {DOI}\n" + "body " * 60)
        stub = StubClient({"/scidb/": (200, {}, scidb_html(md5)),
                           "/db/aarecord_elasticsearch/": (200, {}, record_json(size=len(pdf)))})
        # the manifest spells it as a padded URL; the audit compares the CANONICAL DOI against the record and
        # the extract, and reports that (per-call-site rule, row S20)
        r = A.audit_one(stub, {"stem": stem, "doi": f" https://doi.org/{DOI}/ "}, self.paths, self.pacer)
        self.assertEqual(r["status"], "audit-ok")
        self.assertEqual(r["doi"], DOI)

    def _jstor_stub(self, md5, size):
        return StubClient({"/scidb/": (200, {}, scidb_html(md5)),
                           "/db/aarecord_elasticsearch/": (200, {}, json.dumps({"file_unified_data": {
                               "identifiers_unified": {"doi": [JSTOR_DOI]}, "extension_best": "pdf",
                               "filesize_best": size, "title_best": ""}}).encode())})

    def test_audit_empty_title_best_uses_the_manifest_title(self):
        stem = "Other_1954_x"
        pdf, md5 = self._pdf(stem)
        self._txt(stem, JSTOR_BODY)
        reg = StubClient({})
        r = A.audit_one(self._jstor_stub(md5, len(pdf)),
                        {"stem": stem, "doi": JSTOR_DOI, "title": JSTOR_TITLE},
                        self.paths, self.pacer, reg, self.pacer)
        self.assertEqual(r["status"], "audit-ok", r["detail"])
        self.assertIn("title_src=job", r["detail"])
        self.assertIn(f"rec_size={len(pdf)}", A.log_line(r))

    def test_audit_empty_title_best_falls_back_to_crossref(self):
        stem = "Other_1954_y"
        pdf, md5 = self._pdf(stem)
        self._txt(stem, JSTOR_BODY)
        reg = StubClient({"api.crossref.org/works/": (200, {}, json.dumps(
            {"message": {"title": [JSTOR_TITLE]}}).encode())})
        r = A.audit_one(self._jstor_stub(md5, len(pdf)), {"stem": stem, "doi": JSTOR_DOI},
                        self.paths, self.pacer, reg, self.pacer)
        self.assertEqual(r["status"], "audit-ok", r["detail"])
        self.assertIn("title_src=crossref", r["detail"])

    def test_audit_reports_a_missing_file_without_network(self):
        r = A.audit_one(StubClient({}), {"stem": "Nope_1999_x", "doi": DOI},
                        self.paths, self.pacer)
        self.assertEqual(r["status"], "audit-missing-file")

    def test_audit_error_is_logged_under_the_canonical_doi(self):
        """run_audit's except branch is the ONE place an audit row is logged without audit_one having normalised
        its DOI first, so it must normalise the manifest spelling itself. (Per-call-site rule, row S21 of
        qc/instruments/litkb_p2_mutations.py: nothing reached this line before.)"""
        with open(self.paths["manifest"], "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=A.MANIFEST_FIELDS)
            w.writeheader()
            w.writerow({"stem": "Boom_1999_x", "doi": " https://doi.org/10.4171/JEMS/179/ "})
        real = A.audit_one

        def boom(*a, **k):
            raise RuntimeError("stub blew up")
        A.audit_one = boom
        self.addCleanup(lambda: setattr(A, "audit_one", real))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            A.run_audit(StubClient({}), self.paths, self.pacer)
        out = buf.getvalue()
        self.assertIn("| 10.4171/jems/179 |", out)
        self.assertNotIn("JEMS", out)
        self.assertNotIn("doi.org", out)
        self.assertIn("audit-error=1", out)


# ------------------------------------------------------------------ gate 0: DOI resolver

CR = "api.crossref.org"
S2 = "api.semanticscholar.org"
AX = "export.arxiv.org"
EMPTY_FEED = b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'


def crossref_json(*items):
    return json.dumps({"message": {"items": list(items)}}).encode()


def cr_item(doi=DOI, title="The Estimation of Prediction Error",
            subtitle="Covariance Penalties and Cross-Validation", family="Efron", year=2004):
    return {"DOI": doi, "title": [title], "subtitle": [subtitle] if subtitle else [],
            "author": [{"family": family, "given": "Bradley"}],
            "issued": {"date-parts": [[year, 9]]}}


def s2_json(*items):
    return json.dumps({"data": list(items)}).encode()


class FakeClock:
    """Injectable monotonic clock; sleep() advances it."""

    def __init__(self, t=1000.0):
        self.t, self.slept = t, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class TestResolveDoi(unittest.TestCase):
    STEM = "Efron_2004_test"

    def setUp(self):
        self.slept = []
        self.pacer = A.Pacer(interval=0, sleep=self.slept.append, backoff=A.REGISTRY_BACKOFF)

    def resolve(self, routes, year=2004, surname="Efron", title=TITLE):
        stub = StubClient(routes)
        return stub, A.resolve_doi(title, surname, year, stub, self.pacer)

    def test_i_crossref_exact_hit(self):
        stub, (doi, src, ev) = self.resolve({CR: (200, {}, crossref_json(cr_item()))})
        self.assertEqual((doi, src), (DOI, "crossref"))
        self.assertEqual(ev, "via=crossref; ratio=1.00; year=2004")
        self.assertFalse(any(S2 in u for u, _ in stub.calls))
        self.assertEqual(A.resolution_log_line("resolved-doi", self.STEM, TITLE, doi, ev),
                         f"resolved-doi | {self.STEM} | {TITLE[:60]} | {DOI} | "
                         f"via=crossref; ratio=1.00; year=2004")

    def test_resolve_only_logs_the_job_doi_canonicalised(self):
        """run_jobs' own calls of normalize_doi (per-call-site rule, row S24): a job that already carries a DOI
        is logged — and later fetched — under the canonical spelling, not the one typed on the command line."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            A.run_jobs([(f" https://doi.org/{DOI}/ ", self.STEM, {"title": TITLE})], None, "", None, None,
                       resolve_only=True)
        self.assertIn(f"resolved-doi | {self.STEM} | {TITLE[:60]} | {DOI} | via=given", buf.getvalue())

    def test_a_candidate_doi_is_canonicalised_and_one_without_a_doi_resolves_to_nothing(self):
        """resolve_doi's own two calls of normalize_doi (per-call-site rule, row S12 of
        qc/instruments/litkb_p2_mutations.py). The registry search hands back Crossref's DOI field verbatim, so
        the resolver is what canonicalises it; and a candidate that matches the title but carries no '10.'
        resolves to nothing rather than to its junk identifier."""
        _stub, (doi, src, _ev) = self.resolve({CR: (200, {}, crossref_json(
            cr_item(doi=f" https://doi.org/{DOI}. ")))})
        self.assertEqual((doi, src), (DOI, "crossref"))
        _stub, (doi2, src2, ev2) = self.resolve({CR: (200, {}, crossref_json(cr_item(doi="not-a-doi")))})
        self.assertEqual((doi2, src2), (None, None))
        self.assertIn("not-a-doi", ev2)

    def test_ii_crossref_near_miss_falls_to_semanticscholar(self):
        near = "The Estimation of Prediction Error in Nonlinear Mixed Models"
        self.assertLess(A.title_match_ratio(TITLE, near), A.RESOLVE_TITLE_RATIO)
        stub, (doi, src, ev) = self.resolve({
            CR: (200, {}, crossref_json(cr_item(doi="10.9/near", title=near, subtitle=""))),
            S2: (200, {}, s2_json({"title": TITLE, "year": 2004,
                                   "externalIds": {"DOI": DOI.upper()},
                                   "authors": [{"name": "Bradley Efron"}]}))})
        self.assertEqual((doi, src), (DOI, "semanticscholar"))
        self.assertTrue(ev.startswith("via=semanticscholar; ratio=1.00; year=2004"))
        self.assertEqual(len(self.slept), 0)

    def test_iii_all_miss_is_no_doi_and_gate_1_is_never_called(self):
        near = "The Estimation of Prediction Error in Nonlinear Mixed Models"
        registry = StubClient({CR: (200, {}, crossref_json(cr_item(doi="10.9/near", title=near,
                                                                    subtitle=""))),
                               S2: (200, {}, s2_json()), AX: (200, {}, EMPTY_FEED)})
        archive = StubClient({})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            A.run_jobs([("", self.STEM, {"title": TITLE, "authors": "Efron, B.", "year": "2004"})],
                       archive, "SEKRIT", {}, self.pacer, registry, self.pacer)
        self.assertEqual(archive.calls, [])
        ratio = A.title_match_ratio(TITLE, near)
        self.assertEqual(buf.getvalue().strip(),
                         f"no-doi | {self.STEM} | {TITLE[:60]} | - | best=crossref:{ratio:.2f}:10.9/near")
        self.assertEqual({u.split("/")[2] for u, _ in registry.calls}, {CR, S2, AX})

    def test_iv_year_beyond_one_is_rejected_but_one_off_is_accepted_and_logged(self):
        _, (doi, src, ev) = self.resolve({CR: (200, {}, crossref_json(cr_item(year=2001))),
                                          S2: (200, {}, s2_json()), AX: (200, {}, EMPTY_FEED)})
        self.assertIsNone(doi)
        self.assertEqual(ev, f"best=crossref:1.00:{DOI}")
        _, (doi, src, ev) = self.resolve({CR: (200, {}, crossref_json(cr_item(year=2005)))})
        self.assertEqual(doi, DOI)
        self.assertIn("year=2005 (requested 2004; +/-1 accepted as online-first vs print)", ev)

    def test_v_resolve_only_prints_and_never_touches_key_or_archive(self):
        real = A.KEY_FILE
        A.KEY_FILE = os.path.join(tempfile.gettempdir(), "definitely_not_a_key_file.txt")
        self.addCleanup(setattr, A, "KEY_FILE", real)
        registry = StubClient({CR: (200, {}, crossref_json(cr_item()))})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = A.main(["--resolve-only", "--title", TITLE, "--author", "Efron",
                         "--year", "2004", "--stem", self.STEM],
                        registry_client=registry, registry_pacer=self.pacer)
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(),
                         f"resolved-doi | {self.STEM} | {TITLE[:60]} | {DOI} | "
                         f"via=crossref; ratio=1.00; year=2004")
        self.assertTrue(all(CR in u for u, _ in registry.calls))

    def test_arxiv_stage_hit_is_manifest_only_and_reports_no_doi(self):
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                b'<id>http://arxiv.org/abs/2401.01234v2</id><title>' + TITLE.encode() +
                b'</title><published>2004-01-03T00:00:00Z</published>'
                b'<author><name>Bradley Efron</name></author></entry></feed>')
        _, (doi, src, ev) = self.resolve({CR: (200, {}, crossref_json()),
                                          S2: (200, {}, s2_json()), AX: (200, {}, feed)})
        self.assertIsNone(doi)
        self.assertEqual(ev, "best=arxiv:1.00:10.48550/arXiv.2401.01234")

    def test_semanticscholar_arxiv_only_uses_the_arxiv_doi(self):
        _, (doi, src, _) = self.resolve({
            CR: (200, {}, crossref_json()),
            S2: (200, {}, s2_json({"title": TITLE, "year": 2004, "externalIds": {"ArXiv": "2401.01234"},
                                   "authors": [{"name": "B. Efron"}]}))})
        self.assertEqual((doi, src), ("10.48550/arXiv.2401.01234", "semanticscholar"))

    def test_429_backs_off_ten_seconds_once_then_retries(self):
        n = []

        def cr(url):
            n.append(url)
            return (429, {}, b"") if len(n) == 1 else (200, {}, crossref_json(cr_item()))
        _, (doi, _, _) = self.resolve({CR: cr})
        self.assertEqual(doi, DOI)
        self.assertEqual(len(n), 2)
        self.assertEqual(self.slept, [A.REGISTRY_BACKOFF])

    def test_arxiv_pacer_spaces_calls_at_least_three_seconds(self):
        clock = FakeClock()
        pacer = A.Pacer(interval=A.REGISTRY_MIN_INTERVAL, sleep=clock.sleep,
                        backoff=A.REGISTRY_BACKOFF, clock=clock)
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title></entry></feed>')
        at = []

        def ax(url):
            at.append(clock.t)
            return (200, {}, feed)
        stub = StubClient({AX: ax, CR: (200, {}, crossref_json())})
        for _ in range(3):
            self.assertEqual(A.arxiv_title(stub, "1901.11365", pacer), ("T", 200))
            A.search_crossref(stub, TITLE, pacer)
        gaps = [b - a for a, b in zip(at, at[1:])]
        self.assertEqual(len(gaps), 2)
        self.assertTrue(all(g >= 3.0 for g in gaps), gaps)
        self.assertEqual(pacer.interval, 1.0)

    def test_arxiv_429_then_no_response_then_success_on_second_retry(self):
        clock = FakeClock()
        pacer = A.Pacer(interval=A.REGISTRY_MIN_INTERVAL, sleep=clock.sleep,
                        backoff=A.REGISTRY_BACKOFF, clock=clock)
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>'
                + TITLE.encode() + b'</title></entry></feed>')
        seq = [(429, {}, b""), (0, {}, b"URLError: refused"), (200, {}, feed)]
        n = []

        def ax(url):
            n.append(clock.t)
            return seq[len(n) - 1]
        self.assertEqual(A.arxiv_title(StubClient({AX: ax}), "2401.01234", pacer), (TITLE, 200))
        self.assertEqual(len(n), 3)
        self.assertEqual(clock.slept, [15.0, 30.0])
        self.assertEqual([b - a for a, b in zip(n, n[1:])], [15.0, 30.0])

    def test_wrong_first_author_is_rejected(self):
        _, (doi, _, ev) = self.resolve({CR: (200, {}, crossref_json(cr_item(family="Tibshirani"))),
                                        S2: (200, {}, s2_json()), AX: (200, {}, EMPTY_FEED)})
        self.assertIsNone(doi)

    def test_family_name_forms(self):
        self.assertEqual(A.family_name("Efron, B.; Tibshirani, R."), "efron")
        self.assertEqual(A.family_name("Bradley Efron and Rob Tibshirani"), "efron")
        self.assertTrue(A.family_matches("Müller", "MULLER"))
        self.assertTrue(A.family_matches("O'Neil-Dunne", "ONeilDunne"))
        self.assertTrue(A.family_matches("Van Den Hout", "VanDenHout"))
        self.assertFalse(A.family_matches("Hwang", "Wang"))

    def test_csv_row_without_doi_resolves_then_enters_gate_1_with_it(self):
        registry = StubClient({CR: (200, {}, crossref_json(cr_item()))})
        archive = StubClient({"/scidb/": (302, {"Location": "/search?q=x"}, b""),
                              "/search?": (200, {}, b"<html></html>")})
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        paths = {k: os.path.join(tmp.name, k) for k in ("dest", "quarantine", "staging")}
        paths["manifest"] = os.path.join(tmp.name, "manifest.csv")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            A.run_jobs([("", self.STEM, {"title": TITLE, "authors": "Efron", "year": "2004"})],
                       archive, "SEKRIT", paths, self.pacer, registry, self.pacer)
        self.assertIn(f"/scidb/{DOI}/", archive.calls[0][0])
        lines = buf.getvalue().strip().splitlines()
        self.assertTrue(lines[0].startswith("resolved-doi | "))
        self.assertTrue(lines[1].startswith("not-in-archive"))


class TestHelpers(unittest.TestCase):
    def test_title_similarity_matches_a_layout_dump(self):
        text = ("  Journal of the American Statistical Association          Vol. 99\n\n"
                "   The Estimation of Prediction Error: Covariance\n"
                "   Penalties and Cross-Validation\n\n   Bradley EFRON\n")
        self.assertGreaterEqual(A.title_similarity(TITLE, text), A.TITLE_RATIO)

    def test_title_similarity_rejects_an_unrelated_paper(self):
        text = "Tidal mixing fronts in the Irish Sea\nJ. H. Simpson\nAbstract ...\n"
        self.assertLess(A.title_similarity(TITLE, text), A.TITLE_RATIO)

    def test_redaction(self):
        A.add_secret("sup3rsecret")
        self.assertNotIn("sup3rsecret", A.redact("key=sup3rsecret&md5=x"))
        self.assertNotIn("sup3rsecret", A.log_line(
            A.result("api-error", "s", "10.1/x", detail="url key=sup3rsecret")))

    def test_log_line_shape(self):
        r = A.result("ok", "St_2020_x", "10.1/x", record_doi="10.1/x", md5="a" * 32,
                     sha256="b" * 64, bytes=123, downloads_left=9)
        parts = [p.strip() for p in A.log_line(r).split(" | ")]
        self.assertEqual(parts, ["ok", "St_2020_x", "10.1/x", "10.1/x",
                                 "a" * 32, "b" * 12, "bytes=123", "left=9"])
        r = A.result("bad-file", "St_2020_x", "10.1/x", md5="a" * 32, bytes=0,
                     downloads_left=981, rec_size="812345", detail="via=scidb; no %PDF-")
        parts = [p.strip() for p in A.log_line(r).split(" | ")]
        self.assertEqual(parts[5:], ["-", "bytes=0", "left=981", "rec_size=812345",
                                     "via=scidb; no %PDF-"])

    def test_jstor_stable_url_counts_as_doi_evidence(self):
        self.assertTrue(A.doi_in_extract("https://www.jstor.org/stable/2333009\n", "10.2307/2333009"))
        self.assertFalse(A.doi_in_extract("jstor.org/stable/23330091", "10.2307/2333009"))
        self.assertFalse(A.doi_in_extract("jstor.org/stable/2333010", "10.2307/2333009"))
        self.assertFalse(A.doi_in_extract("jstor.org/stable/2333009", "10.1198/2333009"))


# ------------------------------------------------------------------ --audit-fast (tiered)

AX_ID = "1901.11365"
AX_TITLE = "Noise2Self: Blind Denoising by Self-Supervision"
BODY_OTHER = ("Tidal mixing fronts in the Irish Sea and their seasonal persistence\n"
              "J. H. Simpson and R. D. Pingree\n"
              "Observations from six summer cruises show that the position of the shelf-sea front\n"
              "is controlled by the ratio of water depth to the cube of the tidal stream amplitude.\n") * 3


def cr_work(title):
    return (200, {}, json.dumps({"message": {"title": [title]}}).encode())


class TestAuditFast(Base):
    def setUp(self):
        super().setUp()
        self.slept = []
        self.reg_pacer = A.Pacer(interval=0, sleep=self.slept.append, backoff=A.REGISTRY_BACKOFF)
        self.t2 = A.Pacer(interval=1.0, sleep=self.slept.append, backoff=A.T2_BACKOFF)
        self.t3 = A.Pacer(interval=0, sleep=self.slept.append)
        self.out = os.path.join(self.tmp.name, "audit_fast.csv")

    def put(self, stem, text, pdf_body=b"z", raw=None):
        pdf = make_pdf(pdf_body)
        open(os.path.join(self.paths["dest"], stem + ".pdf"), "wb").write(pdf)
        if text is not None:
            open(os.path.join(self.paths["dest"], stem + ".txt"), "w", encoding="utf-8").write(text)
        if raw is not None:
            open(os.path.join(self.paths["dest"], stem + ".raw.txt"), "w", encoding="utf-8").write(raw)
        return hashlib.md5(pdf).hexdigest()

    def manifest(self, *rows):
        with open(self.paths["manifest"], "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=A.MANIFEST_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: "" for k in A.MANIFEST_FIELDS} | r)

    def run_fast(self, registry, archive=None):
        logins = []

        def get_archive():
            logins.append(1)
            return archive
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            res = A.run_audit_fast(self.paths, self.out, registry, self.reg_pacer, get_archive,
                                   t2_pacer=self.t2, t3_pacer=self.t3)
        self.log = buf.getvalue()
        return {r["stem"]: r for r in res}, logins

    def test_t1_doi_in_footer_passes_without_archive(self):
        self.put("S_2004_a", "Some header\n" + "body text words " * 300 + f"\nDOI: {DOI.upper()}\n")
        self.manifest({"stem": "S_2004_a", "doi": DOI, "title": TITLE})
        res, logins = self.run_fast(StubClient({"api.crossref.org/works/": cr_work(TITLE)}))
        self.assertEqual(res["S_2004_a"]["verdict"], "ok")
        self.assertEqual(logins, [])

    def test_t1_jstor_stable_url_counts_for_10_2307(self):
        self.put("O_1954_a", "https://www.jstor.org/stable/2333009\n" + "glyph soup " * 40)
        self.manifest({"stem": "O_1954_a", "doi": JSTOR_DOI})
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": cr_work("Unrelated")}))
        self.assertEqual(res["O_1954_a"]["verdict"], "ok")
        self.assertIn("doi in extract", res["O_1954_a"]["notes"])

    def test_t1_arxiv_id_counts_and_arxiv_api_supplies_title(self):
        self.put("B_2019_a", f"arXiv:{AX_ID}v2 [cs.CV] 8 Jun 2019\n" + "words " * 80)
        self.manifest({"stem": "B_2019_a", "arxiv": AX_ID})
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>' + AX_TITLE.encode()
                + b'</title></entry></feed>')
        reg = StubClient({"export.arxiv.org/api/query?id_list=": (200, {}, feed)})
        res, _ = self.run_fast(reg)
        self.assertEqual(res["B_2019_a"]["verdict"], "ok")
        self.assertEqual(res["B_2019_a"]["registered_title"], AX_TITLE)
        self.assertIn("arxiv in extract", res["B_2019_a"]["notes"])
        self.assertFalse(A.id_in_extract("arXiv:1901.113651", "", AX_ID))

    def test_arxiv_three_failures_fall_back_to_manifest_title(self):
        self.put("B_2019_b", AX_TITLE + "\n" + "words " * 60)
        self.manifest({"stem": "B_2019_b", "arxiv": AX_ID, "title": AX_TITLE})
        seq = [(429, {}, b""), (0, {}, b"URLError: timed out"), (429, {}, b"")]
        n = []

        def ax(url):
            n.append(url)
            return seq[len(n) - 1]
        res, _ = self.run_fast(StubClient({"export.arxiv.org/api/query?id_list=": ax}))
        r = res["B_2019_b"]
        self.assertEqual(len(n), 3)
        self.assertEqual((r["title_src"], r["registered_title"]), ("manifest", AX_TITLE))
        self.assertIn("arxiv 429; title=manifest", r["notes"])
        self.assertEqual(r["verdict"], "ok")
        self.assertEqual([s for s in self.slept if s >= 15.0], [15.0, 30.0])

    def test_t1_title_match_passes(self):
        self.put("E_2004_a", "JASA\n" + TITLE + "\nBradley EFRON\n" + "words " * 60)
        self.manifest({"stem": "E_2004_a", "doi": DOI})
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": cr_work(TITLE)}))
        self.assertEqual(res["E_2004_a"]["verdict"], "ok")

    def test_crossref_404_falls_back_to_manifest_title(self):
        self.put("E_2004_b", TITLE + "\n" + "words " * 60)
        self.manifest({"stem": "E_2004_b", "doi": DOI, "title": TITLE})
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": (404, {}, b"")}))
        self.assertEqual(res["E_2004_b"]["verdict"], "ok")
        self.assertEqual(res["E_2004_b"]["title_src"], "manifest")

    def test_no_identifier_row_checks_manifest_title_only(self):
        self.put("N_1985_a", TITLE + "\n" + "words " * 60)
        self.manifest({"stem": "N_1985_a", "title": TITLE})
        res, logins = self.run_fast(StubClient({}))
        self.assertEqual(res["N_1985_a"]["verdict"], "no-identifier")
        self.assertIn("registry-none", A._csv_row(res["N_1985_a"])["notes"])
        self.assertEqual(logins, [])

    def test_fail_candidate_archive_vouches_for_our_md5(self):
        md5 = self.put("E_2004_c", BODY_OTHER)
        self.manifest({"stem": "E_2004_c", "doi": DOI})
        arch = StubClient({f"md5:{md5}.json": (200, {}, record_json())})
        res, logins = self.run_fast(StubClient({"api.crossref.org/works/": cr_work(TITLE)}), arch)
        r = res["E_2004_c"]
        self.assertEqual((r["tier1"], r["verdict"], r["tier"]), ("FAIL-CANDIDATE", "ok-archive", "2"))
        self.assertIn("Tidal mixing fronts", r["best_extract_line"] + r["extract_head"])
        self.assertEqual(logins, [1])
        self.assertFalse(any("/scidb/" in u for u, _ in arch.calls))

    def test_fail_candidate_record_with_other_dois_is_misfile(self):
        md5 = self.put("E_2004_d", BODY_OTHER)
        self.manifest({"stem": "E_2004_d", "doi": DOI})
        arch = StubClient({f"md5:{md5}.json": (200, {}, record_json(doi="10.9/tidal", title="Tidal"))})
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": cr_work(TITLE)}), arch)
        r = A._csv_row(res["E_2004_d"])
        self.assertEqual(r["verdict"], "misfile")
        self.assertEqual((r["archive_dois"], r["archive_title"]), ("10.9/tidal", "Tidal"))
        self.assertIn("MISFILE-EVIDENCE", r["notes"])

    def test_tier2_429_backs_off_60s_and_halves_the_rate(self):
        md5 = self.put("E_2004_e", BODY_OTHER)
        self.manifest({"stem": "E_2004_e", "doi": DOI})
        n = []

        def rec(url):
            n.append(url)
            return (429, {}, b"") if len(n) == 1 else (200, {}, record_json())
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": cr_work(TITLE)}),
                               StubClient({f"md5:{md5}.json": rec}))
        self.assertEqual(res["E_2004_e"]["verdict"], "ok-archive")
        self.assertIn(60.0, self.slept)
        self.assertEqual(self.t2.interval, 2.0)
        self.assertEqual(len(n), 2)

    def test_registry_429_backs_off_ten_seconds_once(self):
        self.put("E_2004_f", TITLE + "\n" + "words " * 60)
        self.manifest({"stem": "E_2004_f", "doi": DOI})
        n = []

        def cr(url):
            n.append(url)
            return (429, {}, b"") if len(n) == 1 else cr_work(TITLE)
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": cr}))
        self.assertEqual(res["E_2004_f"]["verdict"], "ok")
        self.assertEqual(self.slept, [A.REGISTRY_BACKOFF])

    def _t3(self, stem, text, scidb, record_for_archive_md5=None):
        md5 = self.put(stem, text)
        self.manifest({"stem": stem, "doi": DOI})
        routes = {f"md5:{md5}.json": (404, {}, b"not found"), "/scidb/": scidb}
        if record_for_archive_md5:
            routes["/db/aarecord_elasticsearch/"] = (200, {}, record_json())
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": cr_work(TITLE)}),
                               StubClient(routes))
        return res[stem], md5

    def test_indeterminate_same_file_at_scidb_is_ok_archive(self):
        md5 = hashlib.md5(make_pdf(b"z")).hexdigest()
        r, _ = self._t3("I_1972_a", "\f\f\f", (200, {}, scidb_html(md5)))
        self.assertEqual((r["tier1"], r["verdict"], r["tier"]), ("INDETERMINATE", "ok-archive", "3"))
        self.assertIn("tier3: SAME-FILE", r["notes"])

    def test_indeterminate_different_copy(self):
        r, _ = self._t3("I_1972_b", "\f\f\f", (200, {}, scidb_html(OTHER)), True)
        self.assertEqual(r["verdict"], "different-copy")
        self.assertEqual(r["archive_md5"], OTHER)

    def test_indeterminate_not_in_archive(self):
        r, _ = self._t3("I_1972_c", "\f\f\f", (302, {"Location": "/search?q=x"}, b""))
        self.assertEqual(r["verdict"], "indeterminate")

    def test_fail_candidate_with_no_vouching_is_misfile(self):
        r, _ = self._t3("F_2000_a", BODY_OTHER, (200, {}, scidb_html(OTHER)), True)
        self.assertEqual((r["tier1"], r["verdict"]), ("FAIL-CANDIDATE", "misfile"))
        r, _ = self._t3("F_2000_b", BODY_OTHER, (302, {"Location": "/search?q=x"}, b""))
        self.assertEqual(r["verdict"], "misfile")

    def test_raw_txt_used_when_txt_has_no_text_layer(self):
        self.put("R_2004_a", "\f\f", raw=TITLE + "\n" + "words " * 60)
        # the manifest spelling is a URL with padding: tier 1 reports the CANONICAL DOI, whatever was typed
        # (per-call-site rule, row S22 of qc/instruments/litkb_p2_mutations.py)
        self.manifest({"stem": "R_2004_a", "doi": f" https://doi.org/{DOI}/ "})
        res, _ = self.run_fast(StubClient({"api.crossref.org/works/": cr_work(TITLE)}))
        self.assertEqual(res["R_2004_a"]["verdict"], "ok")
        self.assertEqual(res["R_2004_a"]["doi"], DOI)

    def test_truncated_doi_is_repaired_in_memory_and_manifest_untouched(self):
        good = "10.1016/0038-0121(77)90015-5"
        title = "Markov analysis of land use change: Continuous time and stationary processes"
        self.put("Bell_1977_a", "Socio-Econ. Plan. Sci.\n" + title + f"\n{good}\n" + "words " * 60)
        # both spellings are URLs: the truncated prefix in the manifest and Crossref's candidate. The repair
        # compares them CANONICALISED, never as typed (per-call-site rule, row S23)
        self.manifest({"stem": "Bell_1977_a", "doi": "https://doi.org/10.1016/0038-0121(77", "title": title,
                       "authors": "Bell & Hinojosa", "year": "1977"})
        before = open(self.paths["manifest"], "rb").read()
        reg = StubClient({"api.crossref.org/works?": (200, {}, crossref_json(
                              cr_item(doi=f"https://doi.org/{good}", title=title, subtitle="", family="Bell",
                                      year=1977))),
                          "api.crossref.org/works/": cr_work(title)})
        res, _ = self.run_fast(reg)
        self.assertEqual(res["Bell_1977_a"]["doi"], good)
        self.assertEqual(res["Bell_1977_a"]["verdict"], "ok")
        self.assertIn(f"DOI-REPAIR Bell_1977_a | https://doi.org/10.1016/0038-0121(77 -> {good}", self.log)
        self.assertEqual(open(self.paths["manifest"], "rb").read(), before)

    def test_truncated_doi_with_no_extending_candidate_is_not_repaired(self):
        rows = [{"stem": "L", "doi": "10.1890/0012-9658(1998", "title": TITLE,
                 "authors": "Efron, B.", "year": "2004"}]
        reps = A.repair_truncated_dois(rows, StubClient({CR: (200, {}, crossref_json(cr_item()))}),
                                       self.reg_pacer)
        self.assertEqual(reps[0][2], "")
        self.assertEqual(rows[0]["doi"], "10.1890/0012-9658(1998")

    def test_csv_and_log_are_redacted(self):
        """The two audit-fast sinks: the CSV rows (_csv_row) and the T1/T2/T3 + SUMMARY lines on stdout
        (run_audit_fast). The key is planted in the manifest title, which reaches the CSV, AND in the stem, which
        reaches the printed tier lines — nothing else redacts either, so each call site is asserted on its own."""
        k = isolate_secrets(self)
        self.assertEqual(A.redact(k), k)              # negative control: not registered until the next line
        A.add_secret(k)
        stem = "K_2004_" + k
        self.put(stem, TITLE + "\n" + "words " * 60)
        self.manifest({"stem": stem, "doi": DOI, "title": k})
        self.run_fast(StubClient({"api.crossref.org/works/": (404, {}, b"")}))
        self.assertNotIn(k, open(self.out, encoding="utf-8").read())
        self.assertNotIn(k, self.log)
        self.assertIn("<KEY>", self.log)
        self.assertTrue(os.path.exists(os.path.join(self.paths["dest"], stem + ".pdf")))


# ------------------------------------------------------------------ the redaction call sites

class LoginStub(StubClient):
    """A StubClient that also answers login(), so open_session()/main() can be driven without the network."""

    def __init__(self, routes=None, ok=True):
        super().__init__(routes or {})
        self.ok, self.keys = ok, []

    def login(self, key):
        self.keys.append(key)
        return self.ok, 200


class TestRedactionSites(Base):
    """One test per netutil.redact / add_secret call site outside litkb.acquire.run (those are in
    qc/test_litkb_p2.py, where the database is). Each plants a fake key where THAT site is the only thing
    standing between it and a sink, and asserts the sink is clean; the harness rows in
    qc/instruments/litkb_p2_mutations.py strip each call and must fail this set."""

    def setUp(self):
        super().setUp()
        self.key = isolate_secrets(self)
        self.pacer.sleep = lambda s: None

    def register(self):
        self.assertEqual(N.redact(self.key), self.key)   # the plant is not redacted by something else
        A.add_secret(self.key)

    def assertClean(self, *blobs):
        for b in blobs:
            s = str(b)
            self.assertNotIn(self.key, s)
            self.assertNotIn(urllib.parse.quote(self.key, safe=""), s)

    # -- annas.result / annas.log_line -------------------------------------------------

    def test_result_redacts_a_key_inside_a_download_url(self):
        """annas.result. The fast_download URL carries the key URL-quoted; the attempt detail built from it
        must not — the stored and logged form of that URL is redacted."""
        self.register()
        url = (f"{A.BASE}/dyn/api/fast_download.json?md5={MD5}"
               f"&key={urllib.parse.quote(self.key)}&domain_index=0")
        r = A.result("api-error", "S_2020_a", DOI, detail=f"no download_url from {url}")
        self.assertClean(r["detail"])
        self.assertIn("<KEY>", r["detail"])

    def test_log_line_redacts_a_field_result_does_not(self):
        """annas.log_line. result() redacts `detail` only, so the key is planted in the stem — the printed line
        is the only place it is removed."""
        self.register()
        r = A.result("ok", f"S_2020_{self.key}", DOI, md5="a" * 32, sha256="b" * 64)
        self.assertIn(self.key, r["stem"])
        self.assertClean(A.log_line(r))

    # -- annas.download_pdf / annas.fetch_for_litkb ------------------------------------

    def test_download_pdf_redacts_an_api_error_that_echoes_the_key(self):
        """annas.download_pdf. The archive's own error text is the realistic leak: it quotes the key it refused."""
        self.register()
        body = json.dumps({"error": f"invalid key {self.key}"}).encode()
        client = StubClient({"fast_download": (200, {}, body)})
        pdf, left, tried, last = A.download_pdf(client, self.key, MD5, {}, self.pacer)
        self.assertIsNone(pdf)
        self.assertTrue(any("invalid key" in t for t in tried), tried)
        self.assertClean(" | ".join(tried))

    def test_fetch_for_litkb_redacts_a_redirect_location(self):
        """annas.fetch_for_litkb's done(). resolve() builds its detail from the Location header without
        redacting; done() is the only guard before that detail becomes an acquisition_attempts row."""
        self.register()
        loc = f"/search?index=journals&q=x&key={urllib.parse.quote(self.key)}"
        r = A.fetch_for_litkb(StubClient({"/scidb/": (302, {"Location": loc}, b""),
                                          "/search": (200, {}, b"<html>no results</html>")}),
                              self.key, DOI, self.pacer, known_md5=set())
        self.assertEqual(r["status"], "not-in-archive")
        self.assertIn("<KEY>", r["detail"])
        self.assertClean(r["detail"])

    # -- the other routes and the resolver ---------------------------------------------

    def test_open_access_detail_redacts_the_lookup_note(self):
        """open_access.fetch_open_access. The Unpaywall note is built from a URL that carries Kam's email as a
        query parameter; that parameter is a registered secret."""
        from litkb.acquire import open_access
        self.register()
        r = open_access.fetch_open_access("10.1/x", None, None, client=StubClient({}),
                                          locations=lambda doi: ([], f"unpaywall: no record for email={self.key}"))
        self.assertEqual(r["status"], "no-oa-copy")
        self.assertClean(r["detail"])

    def test_scihub_detail_redacts_a_mirror_that_carries_credentials(self):
        """scihub.fetch_scihub. `tried` is built from the mirror's netloc, which carries userinfo when a mirror
        is reached through credentials; the detail is the only place it is removed."""
        from litkb.acquire import scihub
        self.register()
        r = scihub.fetch_scihub("10.1/x", None, client=StubClient({"sci-hub.ru": (404, {}, b"nope")}),
                                mirrors=(f"https://kam:{self.key}@sci-hub.ru",))
        self.assertEqual(r["status"], "bad-file")
        self.assertClean(r["detail"])

    def test_resolution_log_line_redacts_its_evidence(self):
        """resolver.resolution_log_line — printed by annas.run_jobs for every resolve-only row."""
        from litkb.admit import resolver
        self.register()
        line = resolver.resolution_log_line("no-doi", "S_2020_a", TITLE, "",
                                            f"crossref error: key={self.key}")
        self.assertClean(line)

    def test_a_transport_error_never_returns_the_url_it_failed_on(self):
        """netutil.Client._raw_get. urllib puts the failing URL — key and all — in the exception text, and that
        text is what get() hands back as the body."""
        self.register()
        url = f"{A.BASE}/dyn/api/fast_download.json?key={urllib.parse.quote(self.key)}"

        def boom(req, timeout=None):
            raise OSError(f"[Errno 11001] getaddrinfo failed for {url}")
        c = N.Client()
        c._follow = c._nofollow = type("Op", (), {"open": staticmethod(boom)})()
        st, _hd, body = c.get(url)
        self.assertEqual(st, 0)
        self.assertIn(b"<KEY>", body)
        self.assertClean(body.decode())

    # -- add_secret: the registration the other 19 sites depend on ---------------------

    def _assert_key_reaches_a_sink_unless_registered(self):
        """The shared proof for an add_secret site: a later log line built from the key is clean only because
        the key was registered. With the add_secret call stripped, this line carries it."""
        self.assertClean(A.log_line(A.result("api-error", "S_2020_a", DOI,
                                             detail=f"invalid key {self.key}")))

    def test_open_session_registers_the_key_it_read(self):
        kf = os.path.join(self.tmp.name, "key.txt")
        open(kf, "w", encoding="utf-8").write(self.key + "\n")
        self.assertEqual(N.redact(self.key), self.key)
        c, key = A.open_session(key_file=kf, client=LoginStub())
        self.assertIsNotNone(c)
        self.assertEqual(key, self.key)
        self._assert_key_reaches_a_sink_unless_registered()

    def test_the_audit_cli_registers_the_key_it_read(self):
        """annas.main --audit reads the key file itself; the manifest is empty, so nothing is requested."""
        kf = os.path.join(self.tmp.name, "key.txt")
        open(kf, "w", encoding="utf-8").write(self.key + "\n")
        self._patch(KEY_FILE=kf, DEST=self.paths["dest"], QUARANTINE=self.paths["quarantine"])
        self.assertEqual(N.redact(self.key), self.key)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = A.main(["--audit"], client=LoginStub(), registry_client=StubClient({}), pacer=self.pacer)
        self.assertEqual(rc, 0)
        self.assertIn("AUDIT SUMMARY", buf.getvalue())
        self._assert_key_reaches_a_sink_unless_registered()

    def test_audit_fast_registers_the_key_before_tiers_2_and_3(self):
        """annas.main_audit_fast.get_archive — the archive login that audit-fast makes lazily, once."""
        kf = os.path.join(self.tmp.name, "key.txt")
        open(kf, "w", encoding="utf-8").write(self.key + "\n")
        out = os.path.join(self.tmp.name, "fast.csv")
        real_pacer = A.Pacer

        def fast_pacer(*a, **kw):
            return real_pacer(interval=0, sleep=lambda s: None, backoff=0)
        self._patch(KEY_FILE=kf, DEST=self.paths["dest"], QUARANTINE=self.paths["quarantine"],
                    Pacer=fast_pacer)
        pdf = make_pdf(b"z")
        open(os.path.join(self.paths["dest"], "K_2004_a.pdf"), "wb").write(pdf)
        open(os.path.join(self.paths["dest"], "K_2004_a.txt"), "w", encoding="utf-8").write(
            "Tidal mixing fronts in the Irish Sea\nJ. H. Simpson\n")
        with open(self.paths["manifest"], "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=A.MANIFEST_FIELDS)
            w.writeheader()
            w.writerow({k: "" for k in A.MANIFEST_FIELDS}
                       | {"stem": "K_2004_a", "doi": DOI, "title": TITLE, "authors": "Efron, B.", "year": "2004"})
        archive = LoginStub({"/db/aarecord_elasticsearch/": (404, {}, b""), "/scidb/": (404, {}, b""),
                             "/search": (404, {}, b""), "/md5/": (404, {}, b"")})
        self.assertEqual(N.redact(self.key), self.key)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = A.main_audit_fast(["--out", out], client=archive,
                                   registry_client=StubClient({"api.crossref.org/works/": (404, {}, b"")}),
                                   registry_pacer=fast_pacer())
        self.assertEqual(rc, 0)
        self.assertEqual(archive.keys, [self.key], "the archive was never logged in to")
        self._assert_key_reaches_a_sink_unless_registered()

    def _patch(self, **attrs):
        for name, value in attrs.items():
            old = getattr(A, name)
            setattr(A, name, value)
            self.addCleanup(setattr, A, name, old)


# ------------------------------------------------------------------ live smoke (read-only)

@pytest.mark.litkb_live
@unittest.skipUnless(os.environ.get("LITKB_LIVE") == "1" or os.environ.get("AA_LIVE") == "1",
                     "set LITKB_LIVE=1 for the live smoke test")
class TestLive(unittest.TestCase):
    """Read-only against the real site, resolve-only: it never spends a download and never writes."""

    @classmethod
    def setUpClass(cls):
        cls.client, cls.key = A.open_session()
        if cls.client is None:
            raise unittest.SkipTest("login failed")
        cls.pacer = A.Pacer()

    def test_a_known_hit_resolves_to_its_md5_and_record(self):
        doi = "10.1198/016214504000000692"
        md5, status, detail, _ = A.resolve(self.client, doi, self.pacer)
        if not md5:
            md5, fud, _add, rec_doi, _d = A.resolve_via_search(self.client, doi, self.pacer)
        else:
            fud, _add, rec_doi, _s, _d = A.verify_record(self.client, md5, doi, self.pacer)
        print(f"live | {doi} | {md5} | {rec_doi}")
        self.assertEqual(md5, MD5)
        self.assertEqual(rec_doi, doi)
        self.assertEqual(fud.get("extension_best"), "pdf")

    def test_b2_search_fallback_resolves_a_doi_scidb_misses(self):
        doi = "10.1016/j.bioelechem.2022.108270"
        md5, status, detail, loc = A.resolve(self.client, doi, self.pacer)
        self.assertIn(md5, (None, "bf696bae5cdfb8a552c6d6cebb9c88de"))
        md5, fud, add, rec_doi, sdetail = A.resolve_via_search(self.client, doi, self.pacer)
        print(f"search-resolver | {doi} | {rec_doi} | {md5} | {sdetail}")
        self.assertEqual(md5, "bf696bae5cdfb8a552c6d6cebb9c88de")
        self.assertEqual(rec_doi, doi)
        self.assertEqual(fud.get("extension_best"), "pdf")
        self.assertTrue(A.download_options(add))

    def test_b_missing_doi_reports_not_in_archive(self):
        doi = "10.1016/j.isprsjprs.2024.07.028"
        md5, status, detail, loc = A.resolve(self.client, doi, self.pacer)
        print(f"live | {doi} | {status} | {loc}")
        self.assertIsNone(md5)
        self.assertIn(status, A.SEARCH_MISS_STATES)
        smd5, *_ = A.resolve_via_search(self.client, doi, self.pacer)
        self.assertIsNone(smd5)

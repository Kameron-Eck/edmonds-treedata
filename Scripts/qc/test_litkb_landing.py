"""litkb S4.5 builder-C2b: Stage C (route `landing`, litkb.acquire.landing) — the declarative per-publisher rule
table and its interpreter, the C2 pointer extraction, the 4 KB Range probe's typing, guards 9 / 24 / 25, the
recorded example page of every rule (qc/fixtures/litkb_landing_pages/, recorded 2026-09-23 under this builder's
one-landing-page-per-rule grant), the recorder's secret and client-address scrub, and the four known-bads of this
builder's counters (qc/instruments/litkb_hardening_c2b.py) — each fire run here as a test, control AND known-bad.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_landing.py -q -p no:cacheprovider

No test here touches the network: every client is a stub that serves recorded bytes or a CONSTRUCTED answer (each
named so), and every Store is rooted in a pytest tmp dir."""
import base64
import gzip
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
FIX = SCRIPTS / "qc" / "fixtures"
pg_only = pytest.mark.requires_litkb_pg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_{name}_for_landing_tests",
                                                  SCRIPTS / "qc" / "instruments" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("litkb_hardening_c2b")
REC = _load("litkb_landing_record")

#: The publishers plan item 5 / brief-C2b names for this corpus's rule table.
PUBLISHERS = ("mdpi", "elsevier", "springer", "wiley", "ieee", "iop", "cambridge", "oup", "copernicus", "frontiers",
              "plos", "usfs-treesearch")


def L():
    from litkb.acquire import landing
    return landing


def _ctx(clients, leads=None):
    from litkb.acquire.run import Budget, RungContext
    return RungContext(clients=clients, pacer=None, budget=Budget(), index={}, printer=lambda *a, **k: None,
                       leads=list(leads or []))


def _page(meta="", body="", title="A page"):
    """A CONSTRUCTED landing page."""
    return (f"<!DOCTYPE html><html><head><title>{title}</title>{meta}</head><body>{body}</body></html>").encode()


PAPER_META = '<meta name="citation_title" content="A constructed paper">'


def _pdf(n=9000):
    """CONSTRUCTED PDF-shaped bytes (the rung only sniffs; the acceptance test is the loop's, not exercised here)."""
    return b"%PDF-1.4\n" + b"0" * n + b"\n%%EOF\n"


# ── the rule table ───────────────────────────────────────────────────────────────────────────
def test_the_rule_table_is_well_formed_and_every_rule_names_its_source_and_freshness():
    t = L().TABLE
    assert L().check_rules(t) == []
    ids = [r["id"] for r in t["rules"]]
    assert tuple(ids) == PUBLISHERS
    for rule in t["rules"] + [t["default"]]:
        src = rule["source"]
        assert src["translator"] and src["survey"], rule["id"]
        assert "lastUpdated" in src, rule["id"]
        assert rule.get("challenge_signature") is not None or rule.get("challenge_note"), rule["id"]
    # the survey characterised no challenge for Cambridge: the rule says so rather than inventing one
    cam = next(r for r in t["rules"] if r["id"] == "cambridge")
    assert cam["challenge_signature"] is None and "NOT characterised" in cam["challenge_note"]


def test_a_malformed_rule_table_is_refused_whole(tmp_path):
    t = json.loads(L().RULES_PATH.read_text(encoding="utf-8"))
    del t["rules"][0]["source"]["lastUpdated"]
    t["rules"][1]["candidates"][0]["technique"] = "scrape-anything"
    bad = tmp_path / "rules.json"
    bad.write_text(json.dumps(t), encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        L().load_rules(bad)


def test_every_rule_example_is_a_recorded_page_or_says_why_not():
    for rule in L().TABLE["rules"]:
        ex = rule["example"]
        if ex["fixture"] is None:
            assert "NO REAL FIXTURE" in ex["why"], rule["id"]
            continue
        rec = H.load_recording(ex["fixture"])          # every body re-checked against its sha256
        assert rec["doi"] == ex["doi"] and rec["rule"] == rule["id"]
        assert rec["hops"] and rec["grant"]
    without = [r["id"] for r in L().TABLE["rules"] if r["example"]["fixture"] is None]
    assert without == ["usfs-treesearch"]


def test_a_recorded_body_that_changed_is_refused(tmp_path):
    shutil.copytree(H.LANDING_FIXTURES / "plos", tmp_path / "plos")
    body = tmp_path / "plos" / "hop3.body"
    data = bytearray(body.read_bytes())
    data[100] ^= 1
    body.write_bytes(bytes(data))
    with pytest.raises(RuntimeError, match="is not the recorded"):
        H.load_recording("plos", root=tmp_path)


@pytest.mark.parametrize("rid", [r for r in PUBLISHERS if r != "usfs-treesearch"])
def test_each_recorded_page_reproduces_its_rules_expectations(rid):
    """The table is its own regression suite (survey C4 / C4-RG): the recorded page, replayed through the rung's own
    walk and classifier, types as the rule's `example.expect` says, and the interpreter derives exactly the
    candidate URLs pinned there."""
    Lm = L()
    rule = next(r for r in Lm.TABLE["rules"] if r["id"] == rid)
    ex = rule["example"]
    rec = H.load_recording(ex["fixture"])
    fc = H.FixtureClient(H.recorded_answers(rec))
    hops = Lm.walk(fc, Lm.doi_url(ex["doi"]), accept=Lm.PAGE_ACCEPT)
    final = hops[-1]
    verdict, why = Lm.classify(final.status, final.headers, final.body, final.url,
                               rules=Lm.rules_for(ex["doi"], [h.url for h in hops]), purpose="page",
                               chain=[h.url for h in hops])
    assert (verdict, why) == (ex["expect"]["page"], ex["expect"]["page_cause"])
    page = Lm.Page(final.url, final.status, final.headers, final.body, "doi", verdict, why)
    work = {"doi": ex["doi"], **ex["expect"]["work"]}
    cands, _rules = Lm.candidates_for(work, [page], [h.url for h in hops], resolved=final.url)
    assert [c.url for c in cands] == ex["expect"]["candidates"]
    # every request the walk made carried the page Accept and asked no redirect of the client
    assert all(c["accept"] == Lm.PAGE_ACCEPT and c["follow"] is False for c in fc.calls)


def test_the_fixtures_hold_no_client_address():
    """The recorder masks the recording machine's public address (MEASURED echoed by three hosts on the first
    recording): nothing an address detector can see remains in any tracked fixture file."""
    for d in sorted(H.LANDING_FIXTURES.iterdir()):
        rec = H.load_recording(d.name)
        log = [{"url": h["request"]["url"], "body": h["body"], "response_headers": h["response"]["headers"]}
               for h in rec["hops"]]
        # the recorder's own detector, over the recording as it was recorded (each hop under its own host)
        assert REC.client_ips(REC._blobs(log)) == set(), d.name
    iop = (H.LANDING_FIXTURES / "iop" / "hop2.body").read_bytes()
    assert b"ssr=" + REC.B64_MASK in iop                          # the one found inside a redirect parameter


def test_the_recorder_masks_a_planted_secret_and_a_planted_address(tmp_path):
    """X7 (S4.5 CONTRACTS, Codex): a secret planted in a recorded URL, header or body never reaches the files, and
    neither does a client address echoed in plain text by two hosts or inside base64. Everything CONSTRUCTED; no
    request leaves the process."""
    from litkb import netutil

    secret = "PLANTEDSECRETc2b0123456789"
    netutil.add_secret(secret)
    ip = "8.8.4.4"                                 # a public address, CONSTRUCTED as this test's "client"
    b64 = base64.b64encode(f"session-9f$${ip}".encode()).decode()

    class Fake:
        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            if url.startswith("https://doi.org/"):
                return 302, {"Location": f"https://pub.example/a?key={secret}&n=1"}, f"moved {ip}".encode()
            return 200, {"Set-Cookie": "s=1", "X-Echo": secret}, _page(
                PAPER_META, f"<p>your address {ip}</p><script>var u=\"{b64}\";</script><p>{secret}</p>")

    rule = {"id": "planted", "example": {"doi": "10.5555/c2b-recorder-test", "work_key": None}}
    rec = REC.record_rule(rule, client_factory=Fake, out_root=tmp_path)
    for p in (tmp_path / "planted").iterdir():
        data = p.read_bytes()
        assert secret.encode() not in data and ip.encode() not in data and b64.encode() not in data, p.name
    assert all("Set-Cookie" not in h["response"]["headers"] for h in rec["hops"])
    assert any(h["response"]["scrubbed"] for h in rec["hops"])


def test_the_recorder_never_requests_without_live(monkeypatch, capsys):
    from litkb import netutil

    def refuse(*a, **k):
        raise AssertionError("the recorder made a request without --live")
    monkeypatch.setattr(netutil, "Client", refuse)
    assert REC.main([]) == 0
    out = capsys.readouterr().out
    assert "recorded already" in out or "would GET" in out


def test_the_rescrub_is_idempotent_on_the_committed_fixtures(tmp_path):
    shutil.copytree(H.LANDING_FIXTURES, tmp_path / "pages")
    for d in sorted((tmp_path / "pages").iterdir()):
        before = {p.name: p.read_bytes() for p in d.iterdir()}
        rec, n = REC.rescrub(d.name, out_root=tmp_path / "pages")
        after = {p.name: p.read_bytes() for p in d.iterdir()}
        assert n == 0 and before == after, d.name


# ── C2: the pointers ─────────────────────────────────────────────────────────────────────────
def test_pointers_match_name_and_property_by_suffix_in_head_and_body_and_resolve_against_the_base():
    Lm = L()
    html = _page(
        '<meta property="citation_pdf_url" content="https://pub.example/prop.pdf">'
        '<meta name="bepress_citation_pdf_url" content="/bp.pdf">'
        '<base href="https://cdn.example/root/">',
        '<meta name="eprints.citation_pdf_url" content="rel/ep.pdf">'
        '<meta name="og:pdf" content="https://og.example/og.pdf">'
        '<meta itemprop="fulltext_pdf_url" content="https://ft.example/ft.pdf?a=1&amp;b=2">'
        '<meta name="eprints.document_url" content="https://ep.example/doc">'
        '<link rel="alternate" type="application/pdf" href="https://alt.example/alt.pdf">'
        '<iframe src="/viewer/file.pdf"></iframe>'
        '<script>var PDFViewerApplicationOptions={defaultUrl: "https://js.example/pdfjs.pdf"};</script>'
        '<a data-pdf-url="https://data.example/d.pdf">pdf</a>'
        '<meta name="citation_pdf_url" content="javascript:void(0)">')
    got = dict(Lm.pointers(html, "https://pub.example/article/1"))
    assert got["https://pub.example/prop.pdf"] == "meta:citation_pdf_url"
    assert got["https://cdn.example/bp.pdf"] == "meta:bepress_citation_pdf_url"          # root-relative, the <base>
    assert got["https://cdn.example/root/rel/ep.pdf"] == "meta:eprints.citation_pdf_url"  # in <body>, relative
    assert "https://og.example/og.pdf" in got and "https://ep.example/doc" in got
    assert got["https://ft.example/ft.pdf?a=1&b=2"] == "meta:fulltext_pdf_url"         # entity-decoded
    assert got["https://alt.example/alt.pdf"] == "link:alternate"
    assert got["https://cdn.example/viewer/file.pdf"] == "iframe:src"
    assert got["https://js.example/pdfjs.pdf"] == "pdfjs:defaultUrl"
    assert got["https://data.example/d.pdf"] == "data-pdf-url"
    assert not any(u.startswith("javascript:") for u in got)


def test_a_relative_pointer_on_a_slashless_page_is_tried_both_ways():
    """C2-RG: append `/` to a base with no trailing slash (the PMC case) — kept AFTER the browser's reading, because
    a page URL like /article/view/123 is where the survey's rule is wrong."""
    Lm = L()
    assert Lm.resolve("https://h.example/pmc/articles/PMC123", "pdf/x.pdf") == [
        "https://h.example/pmc/articles/pdf/x.pdf", "https://h.example/pmc/articles/PMC123/pdf/x.pdf"]
    assert Lm.resolve("https://h.example/a/page.html", "x.pdf") == ["https://h.example/a/x.pdf"]
    assert Lm.resolve("https://h.example/a/", "x.pdf") == ["https://h.example/a/x.pdf"]


def test_query_unwrap_adds_the_file_a_viewer_url_names():
    got = [u for u, _s in L().pointers(_page('<meta name="citation_pdf_url" '
                                               'content="https://v.example/viewer?file=%2Fstore%2Fa.pdf">'),
                                         "https://v.example/landing")]
    assert got == ["https://v.example/viewer?file=%2Fstore%2Fa.pdf", "https://v.example/store/a.pdf"]


def test_every_page_the_acceptance_test_says_carries_a_pointer_gives_stage_c_one():
    """accept.landing_signals is the fact landing_pages_booked_bad_file reads; the landing rung's extractor must see a
    pointer wherever that fact says one exists (on every recorded page, and on the CONSTRUCTED shapes above)."""
    from litkb.acquire import accept
    seen = 0
    for d in sorted(H.LANDING_FIXTURES.iterdir()):
        rec = H.load_recording(d.name)
        for h in rec["hops"]:
            if accept.landing_signals(h["body"])["pdf_pointer"]:
                seen += 1
                assert L().pointers(h["body"], h["request"]["url"]), (d.name, h["n"])
    assert seen >= 4          # cambridge, copernicus, frontiers, plos


# ── the classifier (the Range probe's seven answers) ─────────────────────────────────────────
def _classify(status, body=b"", headers=None, purpose="candidate", url="https://pub.example/x", chain=()):
    return L().classify(status, headers or {"Content-Type": "text/html"}, body, url, purpose=purpose,
                        rules=L().rules_for(None, [url]), chain=chain)[0]


@pytest.mark.parametrize("status,expected", [(0, "transient"), (408, "transient"), (429, "transient"),
                                             (503, "transient"), (500, "transient"), (404, "not_found"),
                                             (410, "not_found"), (401, "identity_required"),
                                             (403, "identity_required"), (202, "challenge_or_bot_check"),
                                             (400, "unexpected")])
def test_the_status_alone_types_the_answer(status, expected):
    assert _classify(status, b"<html><body>no</body></html>") == expected


def test_recorded_challenges_type_as_challenges():
    e13 = (FIX / "litkb_e13_challenge_b65a33b17354.html").read_bytes()
    akamai = (FIX / "litkb_mdpi_pdf_akamai_a3b93f589df6.html").read_bytes()
    springer = H.load_recording("springer")["hops"][-1]["body"]            # 200 "Client Challenge", 3,038 B
    assert _classify(403, e13) == "challenge_or_bot_check"
    assert _classify(403, akamai, url="https://www.mdpi.com/2072-4292/15/3/765/pdf") == "challenge_or_bot_check"
    assert _classify(200, springer, url="https://link.springer.com/article/10.1007/BF00531768",
                     purpose="page") == "challenge_or_bot_check"
    assert _classify(200, springer, url="https://link.springer.com/content/pdf/x.pdf") == "challenge_or_bot_check"


def test_a_real_landing_page_is_never_a_challenge_because_of_its_scripts():
    page = _page(PAPER_META, '<script src="https://www.google.com/recaptcha/api.js"></script> just a moment')
    assert _classify(200, page, purpose="page") == "landing"
    assert _classify(200, page) == "html_or_reader"


def test_an_html_page_with_no_citation_metadata_is_a_plain_page_never_the_landing_page():
    """C6-RG's marker-free rule ("no citation metadata = an interstitial") was REMOVED by builder-FX-V (S4.5 fix wave:
    it decided 5 real DOI pages of the ladder-1 run and 0 was an interstitial — referee-stage-c, referee-vocabulary
    class C; the recorded pages are pinned in qc/test_litkb_s45_typing.py). Such a page is a `plain_page`: read for its
    pointers, never THE landing page, never a challenge. This test pinned the removed rule; it now pins its
    replacement on the same CONSTRUCTED page."""
    Lm = L()
    page = _page("", "<p>Please wait</p>")
    assert _classify(200, page, purpose="page") == "plain_page"
    assert Lm.Page("https://x.example/p", 200, {}, page, "doi", "plain_page").readable
    assert _classify(200, page) == "html_or_reader"


def test_a_login_wall_on_the_chain_is_identity_required_even_with_a_captcha_on_it():
    login = _page("", '<form>institutional login <div class="g-recaptcha"></div></form>')
    assert _classify(200, login, url="https://idp.example/sso/login",
                     chain=["https://pub.example/x.pdf", "https://login.openathens.net/auth?x"]) == "identity_required"
    assert _classify(302, b"", headers={"Location": "https://wayf.springernature.com/?redirect=x"}) == \
        "identity_required"


def test_a_paywall_marker_in_an_html_answer_to_a_pdf_candidate_is_identity_required():
    assert _classify(200, _page("", "<p>Access through your institution</p>")) == "identity_required"


def test_a_redirect_into_a_bot_check_is_a_challenge_and_is_never_followed():
    Lm = L()
    rec = H.load_recording("iop")
    fc = H.FixtureClient(H.recorded_answers(rec))
    hops = Lm.walk(fc, Lm.doi_url(rec["doi"]), accept=Lm.PAGE_ACCEPT)
    assert [h.status for h in hops] == [302, 302]
    assert not any("perfdrive" in c["url"] for c in fc.calls)
    assert Lm.classify(hops[-1].status, hops[-1].headers, hops[-1].body, hops[-1].url,
                       purpose="page")[0] == "challenge_or_bot_check"


def test_pdf_bytes_and_wrapped_pdfs_are_pdf_at_2xx_only():
    assert _classify(206, _pdf()[:4096], headers={"Content-Type": "application/pdf"}) == "pdf"
    assert _classify(200, gzip.compress(_pdf()), headers={"Content-Type": "application/gzip"}) == "pdf"
    assert _classify(403, _pdf(), headers={"Content-Type": "application/pdf"}) == "identity_required"


# ── guards 9, 24 and the shadow tier ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", ["http://localhost/x.pdf", "http://127.0.0.1/x.pdf", "http://10.0.0.5/x.pdf",
                                 "http://169.254.169.254/latest", "http://[::1]/x.pdf", "file:///etc/passwd",
                                 "http://printer.local/x.pdf", "ftp://pub.example/x.pdf"])
def test_guard_9_refuses_private_loopback_and_link_local_addresses(url):
    assert L().public_url(url)[0] is False


def test_guard_9_passes_a_public_name_and_address():
    assert L().public_url("https://www.mdpi.com/x")[0] and L().public_url("https://8.8.8.8/x")[0]


def test_the_referer_is_the_landing_page_if_same_origin_else_its_origin_never_a_search_engine():
    Lm = L()
    page = "https://www.cambridge.org/core/journals/x/article/abs/y/ID"
    assert Lm.referer_for(page, "https://www.cambridge.org/core/services/z.pdf") == page
    assert Lm.referer_for("https://www.mdpi.com/2072-4292/15/3/765", "https://mdpi-res.com/d.pdf") == \
        "https://www.mdpi.com/"
    assert Lm.referer_for("https://www.google.com/search?q=x", "https://pub.example/a.pdf") is None
    assert Lm.referer_for(None, "https://pub.example/a.pdf") is None


def test_a_candidate_on_a_shadow_host_is_never_asked():
    Lm = L()
    page = Lm.Page("https://pub.example/a", 200, {}, _page(
        PAPER_META + '<meta name="citation_pdf_url" content="https://sci-hub.ru/10.5555/x">'), "doi", "landing")
    cands, _ = Lm.candidates_for({"doi": "10.5555/x"}, [page], [page.url], resolved=page.url)
    assert cands == [] and Lm.shadow_host("https://sci.bban.top/pdf/10.5555/x.pdf")


# ── identity (C10), score (C9), rewrites (C3), de-dup (A10), templates ───────────────────────
def _cands(rule_id, page_url, meta, doi, urls=None, work=None):
    Lm = L()
    page = Lm.Page(page_url, 200, {}, _page(PAPER_META + meta), "doi", "landing")
    rules = [r for r in Lm.TABLE["rules"] if r["id"] == rule_id] + [Lm.TABLE["default"]]
    cands, _ = Lm.candidates_for(dict(work or {}, doi=doi), [page], urls or [page_url], resolved=page_url,
                                 rules=rules)
    return [c.url for c in cands]


def test_a_springer_page_pointing_at_nature_or_a_supplement_is_refused():
    got = _cands("springer", "https://link.springer.com/article/10.1007/abc",
                 '<meta name="citation_pdf_url" content="https://www.nature.com/articles/other.pdf">'
                 '<meta name="citation_pdf_url" content="https://static-content.springer.com/esm/suppl_file_1.pdf">',
                 "10.1007/abc")
    assert not any("nature.com" in u or "suppl" in u for u in got)


def test_an_elsevier_pointer_to_another_pii_is_refused():
    got = _cands("elsevier", "https://www.sciencedirect.com/science/article/pii/S0034425721005265",
                 '<meta name="citation_pdf_url" content="https://www.sciencedirect.com/science/article/pii/'
                 'S0000000000000000/pdf">', "10.1016/j.rse.2021.112806",
                 urls=["https://linkinghub.elsevier.com/retrieve/pii/S0034425721005265"])
    assert got == ["https://www.sciencedirect.com/science/article/pii/S0034425721005265/pdfft?isDTMRedir=true&download=true"]


def test_a_supplementary_candidate_scores_below_zero_and_is_never_tried():
    got = _cands("plos", "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.1",
                 '<meta name="citation_pdf_url" content="https://journals.plos.org/plosone/supplementary/s1.pdf">',
                 "10.1371/journal.pone.1")
    assert not any("supplementary" in u for u in got)


def test_the_mdpi_cdn_slug_comes_from_the_venue_and_the_doi_code_and_the_article_is_padded():
    # the volume is padded too (S4.5 fix wave, builder-FX-C): this test pinned `sensors-8-02161`, the exact URL the
    # real L074 row saw the CDN answer 404 in the live run; qc/test_litkb_s45_fx_stage_c.py holds the evidence
    got = _cands("mdpi", "https://www.mdpi.com/1424-8220/8/4/2161", "", "10.3390/s8042161",
                 work={"venue": "Sensors"})
    assert got[:2] == ["https://mdpi-res.com/d_attachment/sensors/sensors-08-02161/article_deploy/sensors-08-02161.pdf",
                       "https://mdpi-res.com/d_attachment/s/s-08-02161/article_deploy/s-08-02161.pdf"]


def test_the_c3_rewrites_and_the_dedupe_key():
    Lm = L()
    assert [u for u, _i, _v in Lm.rewrites_of("https://onlinelibrary.wiley.com/doi/epdf/10.1002/x")] == [
        "https://onlinelibrary.wiley.com/doi/pdf/10.1002/x"]
    assert Lm.rewrites_of("https://www.sciencedirect.com/science/article/pii/S1/x")[0][2] == "acceptedVersion"
    assert Lm._dedupe_key("https://a.example/x.pdf?version=1") == Lm._dedupe_key("https://a.example/x.pdf")
    assert Lm._dedupe_key("https://a.example/x?download=true") != Lm._dedupe_key("https://a.example/x")
    signed = "https://s3.example/x.pdf?X-Amz-Signature=abc&X-Amz-Security-Token=t"
    assert Lm._dedupe_key(signed) == signed and Lm.evidence_url(signed) == "https://s3.example/x.pdf"


# ── the rung, end to end (no database) ───────────────────────────────────────────────────────
DOI = "10.5555/c2b-rung"
LANDING = "https://pub.example/article/1"
POINTER = "https://pub.example/article/1/file.pdf"


def _world(pointer_answer, *, page=None, extra=None):
    """A CONSTRUCTED publisher: doi.org 302 -> a landing page carrying citation_pdf_url -> `pointer_answer`."""
    Lm = L()
    answers = {Lm.doi_url(DOI): (302, {"Location": LANDING}, b""),
               LANDING: (200, {"Content-Type": "text/html"},
                         page or _page(PAPER_META + f'<meta name="citation_pdf_url" content="{POINTER}">')),
               POINTER: pointer_answer, **(extra or {})}
    return H.FixtureClient(answers)


def test_a_pdf_pointer_is_probed_with_4kb_then_fetched_whole_with_the_pdf_accept_and_the_referer():
    fc = _world(H._pdf_answer(_pdf()))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded" and r["pdf"] == _pdf() and r["kind"] == "pdf"
    probe, whole = [c for c in fc.calls if c["url"] == POINTER]
    assert probe["headers"] == {"Referer": LANDING, "Range": "bytes=0-4095"} and probe["accept"] == L().PDF_ACCEPT
    assert whole["headers"] == {"Referer": LANDING} and whole["accept"] == L().PDF_ACCEPT
    assert r["landing"]["landing_page"] == LANDING and r["landing"]["terminal_headers"]["content-type"] == \
        "application/pdf"
    assert r["landing"]["rules"][-1]["id"] == "default"


def test_a_server_that_ignores_the_range_is_not_asked_twice():
    fc = _world((200, {"Content-Type": "application/pdf"}, _pdf()))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded" and [c["url"] for c in fc.calls].count(POINTER) == 1


def test_a_paywalled_answer_is_typed_by_one_ranged_request_and_kept():
    """CONSTRUCTED paywall page at the pointer: typed identity_required from the 4 KB probe; the answer is kept as
    `rejected` (nothing downloaded is discarded) and no whole GET is spent."""
    paywall = _page("", "<h1>Buy PDF</h1><p>Access through your institution</p>")
    fc = _world((200, {"Content-Type": "text/html"}, paywall))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert (r["status"], r["sub_status"]) == ("blocked", "identity_required")
    asked = [c for c in fc.calls if c["url"] == POINTER]
    assert len(asked) == 1 and asked[0]["headers"]["Range"] == "bytes=0-4095"
    assert r["rejected"] == paywall and r["terminal"]["status_code"] == 200


def test_a_transient_answer_stops_the_rung_as_a_retriable_api_error_with_its_retry_after():
    fc = _world((429, {"Retry-After": "7"}, b"slow down"),
                page=_page(PAPER_META + f'<meta name="citation_pdf_url" content="{POINTER}">'
                           '<meta name="citation_pdf_url" content="https://pub.example/second.pdf">'))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert (r["status"], r["retriable"]) == ("api-error", True)
    assert r["terminal"]["headers"]["Retry-After"] == "7" and r["http_codes"][-1] == 429
    assert not any("second.pdf" in c["url"] for c in fc.calls)


def test_a_transient_landing_page_stops_the_rung():
    Lm = L()
    fc = H.FixtureClient({Lm.doi_url(DOI): (503, {}, b"")})
    r = Lm.fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert (r["status"], r["retriable"]) == ("api-error", True)


def test_a_pdf_looking_probe_whose_whole_answer_is_not_a_pdf_is_a_bad_file():
    def answer(url, headers):
        if headers.get("Range"):
            return 206, {"Content-Type": "application/pdf"}, _pdf()[:4096]
        return 200, {"Content-Type": "text/html"}, _page("", "<p>session expired</p>")
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": _world(answer)}))
    assert r["status"] == "bad-file" and r["rejected"].startswith(b"<!DOCTYPE html>")


def test_a_real_page_with_no_pointer_and_no_rule_is_no_pdf_link():
    fc = _world((404, {}, b""), page=_page(PAPER_META, "<p>abstract only</p>"))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert (r["status"], r["sub_status"]) == ("not-in-archive", "no_pdf_link")


def test_a_rewrite_is_tried_only_after_its_original_failed():
    Lm = L()
    epdf = "https://onlinelibrary.wiley.com/doi/epdf/10.5555/c2b-rung"
    answers = {Lm.doi_url(DOI): (302, {"Location": LANDING}, b""),
               LANDING: (200, {"Content-Type": "text/html"},
                         _page(PAPER_META + f'<meta name="citation_pdf_url" content="{epdf}">')),
               "https://onlinelibrary.wiley.com/doi/pdf/10.5555/c2b-rung": H._pdf_answer(_pdf())}
    fc = H.FixtureClient(answers)
    r = Lm.fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    urls = [c["url"] for c in fc.calls]
    assert r["status"] == "downloaded"
    assert urls.index(epdf) < urls.index("https://onlinelibrary.wiley.com/doi/pdf/10.5555/c2b-rung")


def test_the_ieee_two_hop_reads_the_stamp_shell_again():
    """C12, CONSTRUCTED shell: stampPDF answers a WAF 202 (the recorded IEEE shape), stamp.jsp an HTML shell whose
    iframe names the PDF."""
    Lm = L()
    rec = H.load_recording("ieee")
    answers = H.recorded_answers(rec)
    pdf_url = "https://ieeexplore.ieee.org/ielx8/34/1/10752992.pdf?tp=&arnumber=10752992"
    answers.update({
        "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&isnumber=&arnumber=10752992": (202, {}, b"<html>waf</html>"),
        "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=10752992":
            (200, {"Content-Type": "text/html"}, f'<html><iframe src="{pdf_url}"></iframe></html>'.encode()),
        pdf_url: H._pdf_answer(_pdf())})
    fc = H.FixtureClient(answers)
    r = Lm.fetch_landing({"doi": rec["doi"]}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded" and r["landing"]["source"] == "ieee.stamp-two-hop>then"


def test_the_elsevier_pdfft_candidate_walks_the_intermediate_refresh_page_to_the_signed_file():
    """The REAL recorded Elsevier row (the PII comes from the linkinghub URL the DOI resolves to), then a CONSTRUCTED
    ScienceDirect intermediate page at /pdfft that meta-refreshes to a signed asset (survey §2.1: every hop through
    parseIntermediatePDFPage). The signed URL reaches the ledger without its query."""
    Lm = L()
    rec = H.load_recording("elsevier")
    pdfft = ("https://www.sciencedirect.com/science/article/pii/S0034425721005265/pdfft?isDTMRedir=true"
             "&download=true")
    asset = ("https://pdf.sciencedirectassets.com/271745/1-s2.0-S0034425721005265/main.pdf"
             "?X-Amz-Security-Token=CONSTRUCTED&X-Amz-Signature=CONSTRUCTED")
    answers = H.recorded_answers(rec)
    answers[pdfft] = (200, {"Content-Type": "text/html"},
                      f'<html><head><meta http-equiv="refresh" content="0;URL=\'{asset}\'"></head></html>'.encode())
    answers[asset] = H._pdf_answer(_pdf())
    fc = H.FixtureClient(answers)
    r = Lm.fetch_landing({"doi": rec["doi"]}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded" and r["landing"]["source"] == "elsevier.pdfft"
    assert [c["headers"].get("Range") for c in fc.calls if c["url"] == asset] == ["bytes=0-4095", None]
    assert r["terminal"]["url"] == "https://pdf.sciencedirectassets.com/271745/1-s2.0-S0034425721005265/main.pdf"


def test_a_doi_that_resolves_straight_to_a_pdf_is_downloaded():
    Lm = L()
    fc = H.FixtureClient({Lm.doi_url(DOI): (302, {"Location": "https://repo.example/a.pdf"}, b""),
                          "https://repo.example/a.pdf": (200, {"Content-Type": "application/pdf"}, _pdf())})
    r = Lm.fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded" and r["landing"]["source"] == "doi.resolves-to-pdf"


def test_a_lead_page_is_followed_and_a_lead_url_feeds_the_publisher_rule():
    """The loop's leads: a page an earlier rung was served (the REAL recorded Cambridge page) is read for its pointer;
    an earlier rung's refused URL (MDPI's /pdf, answered by the REAL kept Akamai page) feeds the MDPI template."""
    Lm = L()
    cam = H.load_recording("cambridge")
    page_url = cam["final"]["url"]
    pointer = Lm.pointers(cam["hops"][-1]["body"], page_url)[0][0]
    fc = H.FixtureClient({pointer: H._pdf_answer(_pdf())})
    r = Lm.fetch_landing({"doi": "10.5555/c2b-lead"}, _ctx({"landing": fc}, leads=[
        {"route": "open_access", "url": page_url, "status": 200, "headers": {"Content-Type": "text/html"},
         "body": cam["hops"][-1]["body"]}]))
    assert r["status"] == "downloaded" and r["landing"]["leads"][0]["verdict"] == "landing"
    akamai = (FIX / "litkb_mdpi_pdf_akamai_a3b93f589df6.html").read_bytes()
    lead = {"route": "open_access", "url": "https://www.mdpi.com/2072-4292/15/3/765/pdf?version=1",
            "status": 403, "headers": {}, "body": akamai}
    cands, rules = Lm.candidates_for({"doi": "10.5555/c2b-lead", "venue": "Remote Sensing"},
                                     [Lm.Page(lead["url"], 403, {}, akamai, "lead:open_access",
                                              "challenge_or_bot_check")], [lead["url"]])
    assert "mdpi" in rules and cands[0].url.endswith("remotesensing-15-00765.pdf")


def test_the_rung_never_requests_a_private_address_a_page_names():
    fc = _world((404, {}, b""), page=_page(PAPER_META + '<meta name="citation_pdf_url" '
                                           'content="http://127.0.0.1:5433/x.pdf">'))
    L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert not any("127.0.0.1" in c["url"] for c in fc.calls)


def test_each_attempt_carries_its_rules_freshness_prior():
    r = L().fetch_landing({"doi": "10.3390/c2b-fresh"}, _ctx({"landing": H.FixtureClient({})}))
    mdpi = next(x for x in r["landing"]["rules"] if x["id"] == "mdpi")
    assert mdpi["lastUpdated"] == "2022-01-24" and mdpi["age_days"] > 365


# ── netutil: the FlareSolverr retry keeps the caller's headers ───────────────────────────────
def test_the_challenge_retry_keeps_the_callers_headers():
    from litkb import netutil

    seen = []

    class C(netutil.Client):
        def _raw_get(self, url, accept, timeout, follow, data, headers=None):
            seen.append(dict(headers or {}))
            return (403, {}, b"<title>Just a moment...</title>") if len(seen) == 1 else (200, {}, b"%PDF-1.4")

        def solve_challenge(self, url):
            return True

    C(flaresolverr="http://flaresolverr.invalid").get("https://pub.example/x.pdf",
                                                      headers={"Referer": "https://pub.example/", "Range": "bytes=0-9"})
    assert seen == [{"Referer": "https://pub.example/", "Range": "bytes=0-9"}] * 2


# ── the registry and the policy ──────────────────────────────────────────────────────────────
def test_importing_the_ladder_registers_the_landing_rung_as_stage_c_behind_a_legitimate_policy_line():
    out = subprocess.run([sys.executable, "-c",
                          "import litkb.acquire.run as r, litkb.acquire.policy as p;"
                          "g=[x for x in r.RUNGS if x.route=='landing'];"
                          "print(len(g), g[0].stage, g[0].needs, p.decide('landing').allowed, p.decide('landing').tier)"],
                         capture_output=True, text=True, check=True, cwd=SCRIPTS,
                         env={**__import__("os").environ, "PYTHONPATH": str(SCRIPTS / "pipeline")})
    assert out.stdout.split() == ["1", "C", "('doi',", "'arxiv')", "True", "legitimate"]


def test_the_counter_module_names_only_plan_counters_and_every_fire_has_a_bound():
    """Every gated counter is a plan (b) name; every reported one is a plan name or one of the module's NAMED
    additions, each with its reason (round 3: `landing_pages_after_stage_c`; S4.5 decision D50, builder-FX-C:
    `landing_pages_excused_bound_in_run`), never both."""
    acc = _load("litkb_acceptance")
    gated, reported = dict(acc.HARDENING_GATED), set(acc.HARDENING_REPORTED)
    beyond = set(H.REPORTED_BEYOND_PLAN)
    assert set(H.COUNTERS) <= set(gated) and set(H.REPORTED) <= reported | beyond
    assert beyond == {"landing_pages_after_stage_c", "landing_pages_excused_bound_in_run"}
    assert not beyond & (reported | set(gated))
    assert all(H.REPORTED_BEYOND_PLAN[n] for n in beyond) and beyond <= set(H.DETAILS)
    for name, f in H.FIRES.items():
        assert callable(f["run"]) and (f.get("bound") or gated.get(f["counter"])), name


def test_the_bronze_rows_are_read_from_the_probe_csv():
    assert tuple(H.bronze_dois()) == H.BRONZE_DOIS


# ── on a worker database ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def owner(litkb_pg_base):
    return litkb_pg_base[1]


@pg_only
def test_work_record_carries_what_the_url_rules_read(owner, tmp_path):
    w = H.World(owner, tmp_path)
    try:
        work = w.work(title="A constructed work with a venue", author="Venuist", venue="Remote Sensing")
        assert work["venue"] == "Remote Sensing" and "pii" in work and {"volume", "issue", "pages"} <= set(work)
    finally:
        w.close()


@pg_only
def test_stage_c_follows_the_page_open_access_was_served(owner, tmp_path):
    """The ladder: open_access books the REAL Cambridge page bad-file/html_response with the pointer fact, and the
    landing rung asks THAT page's citation_pdf_url (a lead), after the DOI's own walk."""
    from litkb.acquire import landing as Lm

    rec = H.load_recording("cambridge")
    page_url = rec["final"]["url"]
    pointer = Lm.pointers(rec["hops"][-1]["body"], page_url)[0][0]
    w = H.World(owner, tmp_path)
    try:
        with H._no_email():
            work = w.work(title="A constructed article on a recorded Cambridge page", author="Enamorado")
            answers = H._salted_answers(H.recorded_answers(rec, rewrite_doi=(rec["doi"], work["doi"])))
            oa = H.FixtureClient(answers, prefixes={"https://api.unpaywall.org/": H._unpaywall([page_url])})
            landing = H.FixtureClient(answers)
            w.acquire(work, {"open_access": oa, "landing": landing}, ("open_access", "landing"))
        rows = w.rows(work)
        assert (rows[0][0], rows[0][1], rows[0][2]) == ("open_access", "bad-file", "html_response")
        assert rows[0][3]["acceptance"]["facts"]["landing"]["pdf_pointer"] is True
        assert rows[1][0] == "landing" and any(c["url"] == pointer for c in landing.calls)
        assert [x["route"] for x in rows[1][3]["landing"]["leads"]] == ["open_access"]
        assert H.landing_pages_booked_bad_file(owner, w.manifest()) == 0
        assert H.manual_step_rows(owner, w.manifest()) == 1
    finally:
        w.close()


@pg_only
def test_the_mdpi_cdn_rule_lands_the_recorded_row(owner, tmp_path):
    """The positive fact behind fire `mdpi_cdn_rule_disabled`'s control: the paper is BOUND, through route
    `landing`, from the CDN candidate, asked with the Range probe then whole, with the cross-origin Referer."""
    w = H.World(owner, tmp_path)
    try:
        with H._no_email():
            work, clients = H._mdpi_world(w, akamai=H.MDPI_AKAMAI_PDF.read_bytes())
            w.acquire(work, clients, ("open_access", "landing"))
        rows = w.rows(work)
        # open_access books the Akamai 403 blocked/challenge_or_bot_check (S4.5 decision D24, integrator-w3: THE one
        # detector reads its `edgesuite` marker; it was bad-file/html_response before), and the page is a lead
        assert (rows[0][0], rows[0][1], rows[0][2]) == ("open_access", "blocked", "challenge_or_bot_check")
        assert (rows[1][0], rows[1][1]) == ("landing", "ok") and rows[1][3]["landing"]["source"] == "mdpi.cdn"
        assert w.holds_file(work)
        cdn = [c for c in clients["landing"].calls if "mdpi-res.com" in c["url"] and "remotesensing" in c["url"]]
        assert [c["headers"].get("Range") for c in cdn] == ["bytes=0-4095", None]
        assert all(c["headers"]["Referer"] == "https://www.mdpi.com/" for c in cdn)
    finally:
        w.close()


@pg_only
def test_the_paywalled_cambridge_row_is_typed_by_the_probe_and_never_bound(owner, tmp_path):
    w = H.World(owner, tmp_path)
    try:
        work, clients = H._cambridge_paywall_world(w)
        w.acquire(work, clients, ("landing",))
        rows = [r for r in w.rows(work) if r[0] == "landing"]
        assert [(r[1], r[2]) for r in rows] == [("blocked", "html_or_reader")]
        assert not w.holds_file(work)
    finally:
        w.close()


@pg_only
def test_e13s_recorded_challenge_is_typed_challenge_on_the_landing_route(owner, tmp_path):
    from litkb.acquire import landing as Lm

    w = H.World(owner, tmp_path)
    try:
        work = w.work(title="A constructed paper behind E13's challenge", author="Pfitzmann")
        fc = H.FixtureClient({Lm.doi_url(work["doi"]): (403, {"Content-Type": "text/html"},
                                                         H.salted(H.E13_FIXTURE.read_bytes()))})
        w.acquire(work, {"landing": fc}, ("landing",))
        rows = [r for r in w.rows(work) if r[0] == "landing"]
        assert [(r[1], r[2]) for r in rows] == [("blocked", "challenge_or_bot_check")]
        assert rows[0][3]["landing"]["landing_page"] is None           # an interstitial is never the landing page
    finally:
        w.close()


@pg_only
def test_the_bronze_counter_reads_attempt_rows_not_file_state(owner, tmp_path):
    w = H.World(owner, tmp_path)
    try:
        rows = H.bronze_rows(owner, w.manifest())
        assert [r["doi"] for r in rows] == list(H.BRONZE_DOIS) and not any(r["in_main"] for r in rows)
        assert H.bronze_landing_unconverted(owner, w.manifest()) == 4
    finally:
        w.close()


@pg_only
@pytest.mark.parametrize("fire", ["stage_c_disabled", "mdpi_cdn_rule_disabled", "paywalled_probe_disabled",
                                  "e13_challenge_rule_disabled"])
def test_each_c2b_fire_holds_its_bound_on_control_and_breaks_it_with_its_guard_off(owner, tmp_path, fire):
    """This builder's known-bads as gates: the control arm holds its counter at 0 and the known-bad arm — ONE guard
    switched off in this process — moves it to 1. Run-scoped to each arm's own workstream and clock."""
    f = H.FIRES[fire]
    assert f["run"](owner, "control", tmp_path / "control") == 0
    assert f["run"](owner, "known_bad", tmp_path / "known_bad") == 1


# ── round 2 (auditor-C2b F1-F13): the rung ────────────────────────────────────────────────────
def _probe_then(whole_answer):
    """A CONSTRUCTED pointer that answers the 4 KB Range probe with the PDF magic and the whole GET with
    `whole_answer`."""
    def answer(url, headers):
        if headers.get("Range"):
            return 206, {"Content-Type": "application/pdf"}, _pdf()[:4096]
        return whole_answer
    return answer


def test_the_whole_get_after_a_pdf_probe_is_walked_hop_by_hop():
    """F4: the whole GET follows its redirect BY HAND (no `follow=True` request), and the ledger names the URL that
    served the file, not the pre-redirect one."""
    cdn = "https://cdn.pub.example/signed/file.pdf"
    fc = _world(_probe_then((302, {"Location": cdn}, b"")), extra={cdn: (200, {"Content-Type": "application/pdf"},
                                                                          _pdf())})
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded" and r["pdf"] == _pdf() and r["terminal"]["url"] == cdn
    whole = [c for c in fc.calls if c["url"] in (POINTER, cdn) and not c["headers"].get("Range")]
    assert [c["url"] for c in whole] == [POINTER, cdn] and all(c["follow"] is False for c in whole)


def test_the_whole_gets_redirect_to_a_private_address_is_never_asked():
    """F4 + guard 9: a redirect on the WHOLE GET is a hop like any other."""
    fc = _world(_probe_then((302, {"Location": "http://169.254.169.254/latest/meta-data"}, b"")))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert r["status"] != "downloaded" and not any("169.254" in c["url"] for c in fc.calls)
    assert "guard 9" in r["landing"]["candidates"][0]["why"]


def test_the_whole_gets_redirect_into_a_bot_check_is_a_typed_refusal_not_a_bad_file():
    """F4: the walk stops at a redirect into a bot check on the whole GET, and that refusal is typed (a challenge),
    never booked as a bad file."""
    radware = "https://validate.perfdrive.com/?ssa=CONSTRUCTED"
    fc = _world(_probe_then((302, {"Location": radware, "Content-Type": "text/html"}, b"<html>moved</html>")))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert (r["status"], r["sub_status"]) == ("blocked", "challenge_or_bot_check")
    assert not any("perfdrive" in c["url"] for c in fc.calls)


def test_a_range_the_server_refuses_with_416_gets_the_whole_file():
    """F7 (M2): a 416 to the probe is not a refusal of the article — the whole file is asked once, without Range."""
    def answer(url, headers):
        if headers.get("Range"):
            return 416, {"Content-Range": "bytes */9000"}, b""
        return 200, {"Content-Type": "application/pdf"}, _pdf()
    fc = _world(answer)
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded"
    assert [c["headers"].get("Range") for c in fc.calls if c["url"] == POINTER] == ["bytes=0-4095", None]


def test_a_two_hop_shell_naming_a_shadow_host_is_never_followed_there():
    """F7 (M6): a candidate a two-hop shell yields is queued WITHOUT `candidates_for`'s filter, so `_try`'s own
    shadow-host check is the only one it meets. CONSTRUCTED shell on the REAL recorded IEEE row."""
    Lm = L()
    rec = H.load_recording("ieee")
    answers = H.recorded_answers(rec)
    answers["https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=10752992"] = (
        200, {"Content-Type": "text/html"}, b'<html><iframe src="https://sci-hub.ru/10.1109/x.pdf"></iframe></html>')
    fc = H.FixtureClient(answers)
    r = Lm.fetch_landing({"doi": rec["doi"]}, _ctx({"landing": fc}))
    assert not any("sci-hub" in c["url"] for c in fc.calls) and r["status"] != "downloaded"
    assert any(c["url"].startswith("https://sci-hub.ru/") and "shadow" in c["why"] for c in r["landing"]["candidates"])


def test_a_work_without_a_doi_follows_its_leads_and_otherwise_asks_nothing():
    """F11: the ladder asks Stage C for an arXiv-only work (its `needs`), which follows a lead an earlier rung was
    served; with no lead there is nothing to follow and no request is made."""
    from litkb.acquire import run

    Lm = L()
    rung = next(x for x in run.RUNGS if x.route == "landing")
    assert run._identifier(rung, {"doi": None, "arxiv": "2206.01062"}) == "2206.01062"
    fc = H.FixtureClient({})
    r = Lm.fetch_landing({"doi": None, "arxiv": "2206.01062"}, _ctx({"landing": fc}))
    assert (r["status"], r["sub_status"]) == ("not-in-archive", "no_pdf_link") and fc.calls == []
    cam = H.load_recording("cambridge")
    page_url = cam["final"]["url"]
    pointer = Lm.pointers(cam["hops"][-1]["body"], page_url)[0][0]
    fc = H.FixtureClient({pointer: H._pdf_answer(_pdf())})
    r = Lm.fetch_landing({"doi": None, "arxiv": "2206.01062"}, _ctx({"landing": fc}, leads=[
        {"route": "open_access", "url": page_url, "status": 200, "headers": {"Content-Type": "text/html"},
         "body": cam["hops"][-1]["body"]}]))
    assert r["status"] == "downloaded" and not any(c["url"].startswith("https://doi.org/") for c in fc.calls)


def test_the_fall_through_says_a_landing_page_was_read_when_every_candidate_answered_untyped():
    """F13: a page WAS read and its one candidate answered a 400 (nothing the probe types): html_or_reader by
    default, and the note says which case it is."""
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": _world((400, {}, b"bad request"))}))
    assert (r["status"], r["sub_status"]) == ("blocked", "html_or_reader")
    assert r["detail"].startswith("a landing page was read") and "unexpected" in r["detail"]


def test_the_survey_rules_not_built_are_named_in_the_table():
    """F3: every survey §2.1 rule of a publisher in the table that is not built is named in `not_built` with why
    (OUP's /article-pdf/ rewrite and /doi/epdf/, MDPI's ISSN-table rule and browser step, Wiley's ?download=true,
    IEEE's API), and IEEE's stampPDF template is the survey's verbatim."""
    rules = {r["id"]: r for r in L().TABLE["rules"]}
    named = {rid: " ".join(r.get("not_built") or []) for rid, r in rules.items()}
    assert "article-pdf" in named["oup"] and "/doi/epdf/" in named["oup"]
    assert "ISSN table" in named["mdpi"] and "browser" in named["mdpi"]
    assert "download=true" in named["wiley"] and "/doi/epdf/" in named["wiley"]
    assert "ieeexploreapi" in named["ieee"]
    stamp = next(c for c in rules["ieee"]["candidates"] if c["name"] == "stamp-pdf")
    assert stamp["template"] == "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&isnumber=&arnumber={arnumber}"
    for rid, r in rules.items():
        assert all(isinstance(x, str) and len(x) > 30 for x in r.get("not_built") or []), rid


# ── round 2: the recorder's visitor-address mask (F9) ────────────────────────────────────────
def test_the_recorder_masks_a_visitor_address_a_page_names_under_an_address_key(tmp_path):
    """F9: a page's server-rendered state naming OTHER visitors' addresses (Cambridge Core's `remoteAddress`,
    MEASURED by auditor-C2b) — one host, plain text, so neither client-address rule sees them. CONSTRUCTED public
    addresses (IPv4 and IPv6) under three keys; a private one is left as it is."""
    v4, v6 = "9.9.9.9", "2620:fe::fe"

    class Fake:
        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            return 200, {}, _page(PAPER_META, '<script>{"remoteAddress":"%s","x":1};var clientIp = \'%s\';'
                                              'ip_address=%s;{"remoteAddress":"10.1.2.3"}</script>' % (v4, v6, v4))

    rule = {"id": "visitor", "example": {"doi": "10.5555/c2b-visitor-test", "work_key": None}}
    REC.record_rule(rule, client_factory=Fake, out_root=tmp_path)
    body = (tmp_path / "visitor" / "hop0.body").read_bytes()
    assert v4.encode() not in body and v6.encode() not in body and body.count(REC.KEYED_MASK) == 3
    assert b'"remoteAddress":"10.1.2.3"' in body


def test_the_fixtures_name_no_public_address_under_an_address_key():
    for d in sorted(H.LANDING_FIXTURES.iterdir()):
        for h in H.load_recording(d.name)["hops"]:
            left = [m.group(2) for m in REC._KEYED_IP.finditer(h["body"]) if REC._public(m.group(2))]
            assert left == [], (d.name, h["response"]["body_file"])
    assert (H.LANDING_FIXTURES / "cambridge" / "hop3.body").read_bytes().count(b'"remoteAddress":"<PAGE-IP>"') == 4


# ── round 2: the gated counter (F1, F2) and the bronze counter (F5) ──────────────────────────
def test_the_gated_counter_resolves_a_pointer_fact_in_order(tmp_path):
    """F1, pure: the row's own fact, then a same-bytes row's, then the bytes (only when they ARE the served bytes),
    else unreadable (None, which the gate counts); a row served no bytes had no page (False)."""
    import hashlib

    page = H.load_recording("cambridge")["hops"][-1]["body"]
    sha = hashlib.sha256(page).hexdigest()
    (tmp_path / "q.html").write_bytes(page)

    def row(own, sha_, same, refused, own_copy):
        return ("id", "work", "open_access", None, "key", own, sha_, same, refused, own_copy)
    fact = H._pointer_fact
    assert fact(row("false", sha, "true", "q.html", None), tmp_path)[0] is False
    assert fact(row(None, sha, "true", None, None), tmp_path)[0] is True
    assert fact(row(None, sha, None, "q.html", None), tmp_path)[0] is True
    assert fact(row(None, sha, None, None, "q.html"), tmp_path)[0] is True
    assert fact(row(None, "0" * 64, None, "q.html", None), tmp_path)[0] is None
    assert fact(row(None, sha, None, "gone.html", None), tmp_path)[0] is None
    assert fact(row(None, None, None, None, None), tmp_path)[0] is False


def _oa_serves(w, work, answers, rec, page_url, *, stage_c):
    """open_access is served `page_url` as the work's one OA location (a CONSTRUCTED Unpaywall record); the DOI walks
    the recording's hops. `stage_c` False hands the ladder a registry without the landing rung."""
    from litkb.acquire import landing as Lm
    from litkb.acquire import run

    answers = dict(answers)
    first = answers.get(Lm.doi_url(rec["doi"])) if rec else None
    if first is not None:
        answers[Lm.doi_url(work["doi"])] = first
    oa = H.FixtureClient(answers, prefixes={"https://api.unpaywall.org/": H._unpaywall([page_url])})
    if stage_c:
        return w.acquire(work, {"open_access": oa, "landing": H.FixtureClient(answers)}, ("open_access", "landing"))
    return w.acquire(work, {"open_access": oa}, ("open_access",), rungs=[r for r in run.RUNGS if r.route != "landing"])


def _details(owner, w):
    return H.DETAILS["landing_pages_booked_bad_file"](owner, w.manifest())


@pg_only
def test_a_refused_page_served_again_still_counts_when_stage_c_did_not_follow(owner, tmp_path):
    """F1 (auditor-C2b §2.4 reproduced): the REAL recorded Cambridge page (salted ONCE, so both runs are served the
    same bytes) to open_access with Stage C disabled, in two runs with their own workstreams AND literature roots.
    Run 2 meets the rejected-hash lookup, so its row carries no pointer fact of its own; the gate reads it from
    run 1's row of the same bytes and stays 1."""
    rec = H.load_recording("cambridge")
    answers = H._salted_answers(H.recorded_answers(rec))
    got = []
    for n in (1, 2):
        w = H.World(owner, tmp_path / f"run{n}")
        try:
            with H._no_email():
                work = w.work(title="A constructed article served a refused Cambridge page", author="Enamorado")
                _oa_serves(w, work, answers, rec, rec["final"]["url"], stage_c=False)
            row = w.rows(work)[0]
            got.append((H.landing_pages_booked_bad_file(owner, w.manifest()), row[1], row[2], "known_bad" in row[3],
                        " ".join(_details(owner, w))))
        finally:
            w.close()
    assert got[0][:4] == (1, "bad-file", "html_response", False)
    assert got[1][:4] == (1, "bad-file", "html_response", True)
    assert "a row served the same bytes" in got[1][4]


@pg_only
def test_a_refused_page_with_no_fact_anywhere_is_read_from_its_bytes_or_counted(owner, tmp_path):
    """F1, the other two sources: run 1's row is stripped of its acceptance fact (CONSTRUCTED: the live history's
    pre-S4.5 rows carry none), so run 2's refused row is typed from the refused BYTES under the literature root;
    with those bytes gone too, the gate cannot read the page and FAILS CLOSED (still 1, named unreadable)."""
    rec = H.load_recording("cambridge")
    answers = H._salted_answers(H.recorded_answers(rec))
    shared = tmp_path / "shared"                       # one literature root for both runs
    w1 = H.World(owner, shared)
    try:
        with H._no_email():
            work1 = w1.work(title="A constructed article whose refused page lost its fact", author="Enamorado")
            _oa_serves(w1, work1, answers, rec, rec["final"]["url"], stage_c=False)
        aid, rel = owner.execute("SELECT id, detail ->> 'quarantined' FROM litkb.acquisition_attempts "
                                 "WHERE work_id = %s AND route = 'open_access'", (work1["work_id"],)).fetchone()
        owner.execute("UPDATE litkb.acquisition_attempts SET detail = detail - 'acceptance' WHERE id = %s", (aid,))
    finally:
        w1.close()
    w2 = H.World(owner, shared)
    try:
        with H._no_email():
            work2 = w2.work(title="A constructed article served the same refused page", author="Enamorado")
            _oa_serves(w2, work2, answers, rec, rec["final"]["url"], stage_c=False)
        assert "known_bad" in w2.rows(work2)[0][3]
        assert H.landing_pages_booked_bad_file(owner, w2.manifest()) == 1
        assert "read from the refused bytes" in " ".join(_details(owner, w2))
        (w2.store.root / rel).unlink()
        assert H.landing_pages_booked_bad_file(owner, w2.manifest()) == 1
        assert "unreadable (counted: the gate fails closed)" in " ".join(_details(owner, w2))
    finally:
        w2.close()


@pg_only
def test_a_refused_page_without_a_pointer_served_again_is_not_counted(owner, tmp_path):
    """F1, the negative: the REAL kept MDPI Akamai page (no PDF pointer; salted ONCE) served twice with Stage C
    disabled. Run 2's refused row resolves to "no pointer" from run 1's row — the fail-closed rule never counts a
    page whose fact CAN be read.

    S4.5 decision D24 (integrator-w3): the REAL page is now a bot challenge to THE one detector (its `edgesuite`
    marker) and is booked `blocked`, which this negative cannot use — so it runs on a CONSTRUCTED copy of the real
    page with that one marker renamed: still a refused HTML page with no pointer, no longer a challenge."""
    from litkb.netutil import Client

    page_url = "https://www.mdpi.com/2072-4292/15/3/765/pdf?version=1675838087"
    real = H.MDPI_AKAMAI_PDF.read_bytes()
    constructed = real.replace(b"edgesuite", b"example-host")
    assert Client.is_challenge(403, page_url, real) and not Client.is_challenge(403, page_url, constructed)
    answers = {page_url: (403, {"Content-Type": "text/html"}, H.salted(constructed))}
    got = []
    for n in (1, 2):
        w = H.World(owner, tmp_path / f"run{n}")
        try:
            with H._no_email():
                work = w.work(title="A constructed MDPI article refused by Akamai", author="Chen")
                _oa_serves(w, work, answers, None, page_url, stage_c=False)
            row = w.rows(work)[0]
            got.append((H.landing_pages_booked_bad_file(owner, w.manifest()), row[1], row[2], "known_bad" in row[3]))
        finally:
            w.close()
    assert got == [(0, "bad-file", "html_response", False), (0, "bad-file", "html_response", True)]


@pg_only
def test_a_landing_row_on_another_work_does_not_follow_the_page(owner, tmp_path):
    """F2 (M1): the gate's "followed" is per WORK. Work A is served the REAL Cambridge page with Stage C disabled;
    work B, later in the same workstream, gets a landing row. A's page is still unfollowed (1); a landing row on A
    itself follows it (0)."""
    from litkb.acquire import landing as Lm

    rec = H.load_recording("cambridge")
    answers = H._salted_answers(H.recorded_answers(rec))
    w = H.World(owner, tmp_path)
    try:
        with H._no_email():
            work_a = w.work(title="A constructed article served a Cambridge page", author="Enamorado")
            _oa_serves(w, work_a, answers, rec, rec["final"]["url"], stage_c=False)
            work_b = w.work(title="Another constructed article asked of Stage C", author="Otherson")
            w.acquire(work_b, {"landing": H.FixtureClient({})}, ("landing",))
            assert "landing" in [r[0] for r in w.rows(work_b)]
            assert H.landing_pages_booked_bad_file(owner, w.manifest()) == 1
            fc = H.FixtureClient({**answers, Lm.doi_url(work_a["doi"]): answers[Lm.doi_url(rec["doi"])]})
            w.acquire(work_a, {"landing": fc}, ("landing",))
        assert H.landing_pages_booked_bad_file(owner, w.manifest()) == 0
    finally:
        w.close()


@pg_only
def test_a_page_served_again_is_still_a_lead_for_stage_c(owner, tmp_path):
    """F6 (M4): the lead seam reads a served page BEFORE the rejected-hash lookup, so the same page (salted ONCE)
    served in a second run — refused bytes by then — is still followed by that run's Stage C."""
    from litkb.acquire import landing as Lm

    rec = H.load_recording("cambridge")
    answers = H._salted_answers(H.recorded_answers(rec))
    pointer = Lm.pointers(rec["hops"][-1]["body"], rec["final"]["url"])[0][0]
    for n in (1, 2):
        w = H.World(owner, tmp_path / f"run{n}")
        try:
            with H._no_email():
                work = w.work(title="A constructed article whose Cambridge page is served twice", author="Enamorado")
                _oa_serves(w, work, answers, rec, rec["final"]["url"], stage_c=True)
            rows = w.rows(work)
            assert (rows[0][0], rows[0][1], "known_bad" in rows[0][3]) == ("open_access", "bad-file", n == 2)
            assert rows[1][0] == "landing" and [x["route"] for x in rows[1][3]["landing"]["leads"]] == ["open_access"]
            assert any(c["url"] == pointer for c in rows[1][3]["landing"]["candidates"])
        finally:
            w.close()


@pg_only
def test_the_bronze_counter_counts_a_measured_landing_as_converted(owner, tmp_path):
    """F5 (M3): in MEASURE mode (3 of the 4 bronze works already hold a file) a Stage C hit is `measured`, and that
    is a conversion. CONSTRUCTED: a probe CSV naming this test's own work as a bronze row; its DOI resolves straight
    to a CONSTRUCTED paper of its own title."""
    from litkb.acquire import landing as Lm

    w = H.World(owner, tmp_path)
    try:
        work = w.work(title="A constructed bronze article measured by Stage C", author="Stehman")
        csv_path = tmp_path / H.NO_OA_COPY_CSV
        csv_path.write_text(f"doi,unpaywall_url\n{work['doi']},https://doi.org/{work['doi']}\n", encoding="utf-8")
        manifest = dict(w.manifest(), probe_csvs={H.NO_OA_COPY_CSV: str(csv_path)})
        assert H.bronze_landing_unconverted(owner, manifest) == 1
        paper = H.constructed_paper(work["title"], "Stehman", salt="bronze")
        fc = H.FixtureClient({Lm.doi_url(work["doi"]): (302, {"Location": "https://repo.example/b.pdf"}, b""),
                              "https://repo.example/b.pdf": H._pdf_answer(paper)})
        w.acquire(work, {"landing": fc}, ("landing",), mode="measure")
        assert [(r[0], r[1]) for r in w.rows(work) if r[0] == "landing"] == [("landing", "measured")]
        assert H.bronze_landing_unconverted(owner, manifest) == 0 and not w.holds_file(work)
    finally:
        w.close()


# ── round 3 (auditor-C2b round 2 F1-F4) ──────────────────────────────────────────────────────────
def test_a_404_to_the_whole_get_after_a_pdf_probe_is_not_found_never_a_bad_file():
    """F3 (N3): the probe saw the PDF magic and the whole GET answered 404 — the server refused the file, it did not
    serve a wrong one: blocked/not_found, never bad-file with the 404 page kept as the work's bad file."""
    fc = _world(_probe_then((404, {"Content-Type": "text/html"}, _page("", "<h1>Not Found</h1>"))))
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert (r["status"], r["sub_status"]) == ("blocked", "not_found")


def test_the_whole_get_follows_no_meta_refresh():
    """F4 (N4), the builder's stated choice pinned: the probe already reached the URL that answered the PDF magic, so
    an HTML answer to the whole GET there is a bad file, never a hop — its meta refresh is not walked (CONSTRUCTED:
    a refresh page naming a CDN file that would answer a PDF)."""
    cdn = "https://cdn.pub.example/refreshed/file.pdf"
    refresh = _page(f'<meta http-equiv="refresh" content="0; url={cdn}">', "<p>redirecting</p>")
    fc = _world(_probe_then((200, {"Content-Type": "text/html"}, refresh)),
                extra={cdn: (200, {"Content-Type": "application/pdf"}, _pdf())})
    r = L().fetch_landing({"doi": DOI}, _ctx({"landing": fc}))
    assert r["status"] == "bad-file" and r["rejected"] == refresh
    assert not any(c["url"] == cdn for c in fc.calls)


def test_a_work_without_a_doi_whose_lead_was_read_is_never_nothing_to_follow():
    """F4 (N6): "nothing to follow" needs no DOI AND no lead. An arXiv-only work whose lead (the REAL recorded
    Cambridge page) WAS read and whose candidates answered something the probe cannot type (a CONSTRUCTED 400) is the
    fall-through `blocked/html_or_reader` saying a page was read — not `not-in-archive` claiming nothing was there."""
    Lm = L()
    cam = H.load_recording("cambridge")
    page_url = cam["final"]["url"]
    pointer = Lm.pointers(cam["hops"][-1]["body"], page_url)[0][0]
    fc = H.FixtureClient(prefixes={"https://": (400, {}, b"bad request")})     # every candidate: an untyped 400
    r = Lm.fetch_landing({"doi": None, "arxiv": "2206.01062"}, _ctx({"landing": fc}, leads=[
        {"route": "open_access", "url": page_url, "status": 200, "headers": {"Content-Type": "text/html"},
         "body": cam["hops"][-1]["body"]}]))
    assert (r["status"], r["sub_status"]) == ("blocked", "html_or_reader")
    assert r["detail"].startswith("a landing page was read") and any(c["url"] == pointer for c in fc.calls)


def test_the_gate_reads_pages_served_before_stage_c_and_reports_the_later_stages():
    """F1 (C2B33, C2B34), pure: the routes the gate leaves out are exactly those of the stages the ladder runs AFTER
    Stage C; a Stage A / Stage B route (open_access among them) and a route no stage names stay gated."""
    from litkb.acquire import policy

    later = set(H._routes_after_stage_c())
    assert {"wayback", "ia", "commoncrawl", "bban", "scihub", "annas"} <= later
    assert all(policy.STAGE_OF[r] in ("E", "shadow") for r in later)
    assert not later & {"open_access", "eartharxiv", "publisher-url", "arxiv", "landing", "hunt-url", "browser"}


def _stage_e_capture(page, capture_url):
    """A CONSTRUCTED Stage E rung (route `wayback`, a real Stage E route of litkb.acquire.policy.STAGE_OF) answering
    builder-C2c's `bad-file` capture shape: `rejected` = the capture body (the bytes given, salted per call),
    `rejected_url` = a CONSTRUCTED capture URL (auditor-C2b round 2 §2.4's stub, as a test)."""
    from litkb.acquire import landing as Lm

    def rung(work, ctx):
        return {"status": "bad-file", "pdf": None, "source_url": "", "tried": ["web.archive.org:200=page"],
                "http_codes": [200], "rejected": H.salted(page), "rejected_url": capture_url,
                "terminal": {"url": capture_url, "status_code": 200, "at": Lm._now(),
                             "headers": {"Content-Type": "text/html"}},
                "detail": "CONSTRUCTED stub: the archive served a page, not the PDF"}
    return rung


@pg_only
def test_a_page_served_after_stage_c_is_reported_never_gated_with_whether_stage_c_asked_its_pointer(owner, tmp_path):
    """F1 (auditor-C2b round 2 §2.4 as a gate). Stage C runs on the paywalled Cambridge world (REAL recorded hops; it
    asks the page's own pointer and books blocked), THEN a CONSTRUCTED Stage E rung is served a page carrying a
    pointer (policy line for `wayback` added IN THIS PROCESS; this branch has none):
      work 1  the capture is the REAL Cambridge page -> Stage C asked its pointer: asked_by_stage_c=yes
      work 2  the capture is the REAL recorded Frontiers page -> Stage C asked none of its pointers: no
      work 3  as work 1, in MEASURE mode (no bytes kept) -> unknown
    The gate reads 0 throughout (the ladder never asks Stage C after Stage E); the report counts all three."""
    from unittest import mock

    from litkb.acquire import policy as P
    from litkb.acquire import run

    cam = H.load_recording("cambridge")["hops"][-1]["body"]
    fro_rec = H.load_recording("frontiers")
    fro = fro_rec["hops"][-1]["body"]
    landing_rung = next(r for r in run.RUNGS if r.route == "landing")
    wayback = P.POLICY + (P.PolicyLine("wayback", "*", "legitimate", "CONSTRUCTED: this test's stub Stage E rung"),)
    w = H.World(owner, tmp_path)
    try:
        for page, url, mode in ((cam, H.load_recording("cambridge")["final"]["url"], "acquire"),
                                (fro, fro_rec["final"]["url"], "acquire"),
                                (cam, H.load_recording("cambridge")["final"]["url"], "measure")):
            work, clients = H._cambridge_paywall_world(w)
            rungs = [landing_rung, run.Rung("wayback", _stage_e_capture(page, "https://web.archive.org/web/"
                                                                               "20200101000000id_/" + url))]
            with mock.patch.object(P, "POLICY", wayback):
                w.acquire(work, clients, ("landing", "wayback"), rungs=rungs, mode=mode)
            ladder = [(r[0], r[1]) for r in w.rows(work) if r[0] in ("landing", "wayback")]
            assert ladder == [("landing", "blocked"), ("wayback", "bad-file")]
        m = w.manifest()
        assert H.landing_pages_booked_bad_file(owner, m) == 0
        assert H.landing_pages_after_stage_c(owner, m) == 3
        details = H.DETAILS["landing_pages_after_stage_c"](owner, m)
        assert [d.split("asked_by_stage_c=")[1].split(" ")[0] for d in details] == ["yes", "no", "unknown"]
        assert all("route wayback" in d for d in details)
    finally:
        w.close()


@pg_only
def test_a_landing_row_before_the_page_does_not_follow_it(owner, tmp_path):
    """F1 (N1): "followed" is a landing row AT OR AFTER the page. Stage C asks first (the DOI answers a CONSTRUCTED
    404: blocked/not_found); open_access is then served the REAL Cambridge page with Stage C disabled -> 1. A later
    ladder in the same run whose Stage C is skipped `dead_in_run` (it DID look, earlier in the run) follows it -> 0."""
    rec = H.load_recording("cambridge")
    answers = H._salted_answers(H.recorded_answers(rec))
    w = H.World(owner, tmp_path)
    try:
        with H._no_email():
            work = w.work(title="A constructed article Stage C asked before its page was served", author="Enamorado")
            w.acquire(work, {"landing": H.FixtureClient({})}, ("landing",))
            _oa_serves(w, work, answers, rec, rec["final"]["url"], stage_c=False)
            ladder = [(r[0], r[1]) for r in w.rows(work) if r[0] in ("landing", "open_access")]
            assert ladder == [("landing", "blocked"), ("open_access", "bad-file")]
            assert H.landing_pages_booked_bad_file(owner, w.manifest()) == 1
            _oa_serves(w, work, answers, rec, rec["final"]["url"], stage_c=True)
        last = [(r[1], r[2]) for r in w.rows(work) if r[0] == "landing"][-1]
        assert last == ("skipped", "dead_in_run")
        assert H.landing_pages_booked_bad_file(owner, w.manifest()) == 0
    finally:
        w.close()


@pg_only
def test_a_stage_c_skip_that_never_looked_does_not_follow_the_page(owner, tmp_path):
    """F2 (N2): open_access is served the REAL Cambridge page and Stage C is REFUSED by the pre-fetch policy (its line
    removed IN THIS PROCESS): a `skipped/policy_refused` landing row follows the page in time but never looked -> 1."""
    from unittest import mock

    from litkb.acquire import policy as P

    rec = H.load_recording("cambridge")
    answers = H._salted_answers(H.recorded_answers(rec))
    w = H.World(owner, tmp_path)
    try:
        with H._no_email(), mock.patch.object(P, "POLICY", tuple(x for x in P.POLICY if x.route != "landing")):
            work = w.work(title="A constructed article whose Stage C the policy refused", author="Enamorado")
            _oa_serves(w, work, answers, rec, rec["final"]["url"], stage_c=True)
        ladder = [(r[0], r[1], r[2]) for r in w.rows(work) if r[0] in ("open_access", "landing")]
        assert ladder == [("open_access", "bad-file", "html_response"), ("landing", "skipped", "policy_refused")]
        assert H.landing_pages_booked_bad_file(owner, w.manifest()) == 1
    finally:
        w.close()

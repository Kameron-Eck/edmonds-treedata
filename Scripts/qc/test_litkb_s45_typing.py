"""litkb S4.5 fix wave — builder-FX-V: THE TYPING (the referee-vocabulary REJECT; referee-stage-c's C6-RG REJECT).

Every test here reads the REAL recorded bytes of the ladder-1 live run (manifest hardening-1, 2026-09-24): the fixture
`qc/fixtures/litkb_cassettes/typing_fx_v/` holds, for each attempt the referees named wrong, every response its REAL rung
consumed when replayed from its own recorded take (provenance.json: the run row, the attempt id, the ladder-1 entry,
the cassette key, the recorded and the fixture sha256 of every body — the client's public address masked). Nothing
here is constructed except where a test says CONSTRUCTED.

  A1-A4  the ONE challenge detector (`netutil.Client.challenge_cause`, S4.5 decision D24) names the bot checks the run
         met and missed: Anubis at 200, AWS WAF's 202 (`x-amzn-waf-action: challenge`), Incapsula's untitled block
         page at 200, a reCAPTCHA gate at 404
  B      ScienceDirect's 832 KB Cloudflare block page: its block-page token sits past guard 3's 64 KB window and the
         detector reads it, so the Stage B rungs (openalex, doaj) agree with the landing rung
  C      C6-RG's marker-free rule is REMOVED: an ordinary page with no citation metadata is a `plain_page` (read for
         its pointers, never THE landing page, never a challenge); every recorded real interstitial is still one
  D      a 429 whose page states a rate limit (bioRxiv) is the rate limit — the D45 cool-down's — never a challenge;
         a challenge page served at 429 that states none stays a challenge (auditor-fix7 AM1)
  F      a Wayback `id_` capture that kept the origin's `Content-Encoding: gzip` is the HTML page it is
         (`html_response`), never `compressed_or_archived_payload`
  U      L092's bare 403 is pinned as recorded, never graded (the plan's word for it is open)

The route tests replay each attempt's REAL rung through `litkb.acquire.run.acquire` on the worker database (the
ladder's own typing, `run._record_result`), from the fixture through `litkb.cassette` in replay mode: no request
leaves the process. Each of them fails on main 411c3ce with the word the live run wrote.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_typing.py -q
"""
import base64
import gzip
import hashlib
import importlib.util
import json
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
FIX = SCRIPTS / "qc" / "fixtures" / "litkb_cassettes" / "typing_fx_v"
LANDING_FIX = SCRIPTS / "qc" / "fixtures" / "litkb_landing_pages"
PROV = json.loads((FIX / "provenance.json").read_text(encoding="utf-8"))
CASES = PROV["cases"]
pg_only = pytest.mark.requires_litkb_pg

#: The run rows brief-FIXWAVE.md's FX-V section names (referee-vocabulary), plus L092 (undetermined).
BRIEF_ROWS = {"L007", "L019", "L037", "L040", "L044", "L045", "L052", "L054", "L059", "L060", "L061", "L064", "L065",
              "L066", "L090", "L108", "L113", "L114", "L134", "L135", "L136", "L166", "L167", "L193", "L092"}
CHALLENGE = ["blocked", "challenge_or_bot_check"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2M = _load("_litkb_p2_for_fxv", SCRIPTS / "qc" / "test_litkb_p2.py")
REC = _load("_litkb_landing_record_for_fxv", SCRIPTS / "qc" / "instruments" / "litkb_landing_record.py")


def _entries():
    """{case tag: [entry, ...]} from the fixture index, in file order."""
    out = {}
    for ln in (FIX / "index.jsonl").read_bytes().splitlines()[1:]:
        if ln.strip():
            e = json.loads(ln)
            out.setdefault(e["row"], []).append(e)
    return out


ENTRIES = _entries()


def _body(e):
    b = e["response"]["body"]
    if "inline_b64" in b:
        return base64.b64decode(b["inline_b64"])
    return (FIX / "bodies" / b["sha256"][:2] / f"{b['sha256']}.bin").read_bytes()


def _answers(cls, host=None, status=None):
    """Every recorded answer of the class's cases: [(status, headers, body, url)], de-duplicated by body, optionally
    only those of one host (the URL's host or a subdomain of it) / status."""
    out, seen = [], set()
    for c in CASES:
        if c["class"] != cls:
            continue
        for e in ENTRIES[c["case"]]:
            st, url = e["response"]["status"], e["key"]["url"]
            netloc = url.split("/")[2]
            if (host and not (netloc == host or netloc.endswith("." + host))) or (status is not None and st != status):
                continue
            key = (url, e["response"]["body"]["sha256"])
            if key not in seen:
                seen.add(key)
                out.append((st, e["response"]["headers"], _body(e), url))
    assert out, (cls, host, status)
    return out


def _case(prefix):
    return next(c for c in CASES if c["attempt"].startswith(prefix))


# ── the fixture ─────────────────────────────────────────────────────────────────────────────────

def test_the_fixture_holds_the_briefs_rows_as_recorded_with_no_client_address():
    """Every run row FX-V names is in the fixture (and no other), every entry provenance names is in the index under its
    case, every stored body hashes to its name, and no public address two hosts echo is left anywhere — the fixture
    is TRACKED (Codex X7: a recorded body is a leak surface), so the recorder's own inference must find nothing."""
    assert {c["run_row"] for c in CASES} == BRIEF_ROWS
    assert not [c for c in CASES if c["route"] == "ia"]          # class E (the IA query error) is FX-E's
    blobs = []
    for c in CASES:
        got = {(e["key_sha256"], e["seq"]) for e in ENTRIES[c["case"]]}
        assert got == {(x["key_sha256"], x["seq"]) for x in c["entries"]}, c["case"]
        for e in ENTRIES[c["case"]]:
            body = _body(e)
            assert hashlib.sha256(body).hexdigest() == e["response"]["body"]["sha256"], (c["case"], e["key"]["url"])
            blobs.append((e["key"]["url"].split("/")[2], body))
            blobs.append((e["key"]["url"].split("/")[2], json.dumps(e["response"]["headers"]).encode("utf-8")))
            if body[:2] == b"\x1f\x8b":
                blobs.append(("gzip", gzip.decompress(body)))
    assert REC.client_ips(blobs) == set()


# ── the one detector, on the recorded bytes (no database) ────────────────────────────────────────

@pytest.mark.parametrize("cls,host,status,cause", [
    ("A1", "hal.science", 200, "anubis"),                           # Anubis's proof-of-work page
    ("A2", None, 202, "header:x-amzn-waf-action"),                  # AWS WAF: an empty 202 + its header
    ("A3", "projecteuclid.org", 200, "incapsula"),                  # Incapsula's untitled block page
    ("A4", "hdl.handle.net", 404, "captcha"),                       # a reCAPTCHA gate at 404
    ("B", "www.sciencedirect.com", 403, "cloudflare"),              # ScienceDirect's 832 KB block page
])
def test_the_one_detector_names_each_bot_check_the_run_met(cls, host, status, cause):
    """referee-vocabulary classes A1-A4 and B: plan item 2 ("a challenge page is a challenge at ANY status") and
    D24's one detector, on every recorded answer of the class. Main 411c3ce answered '' on each."""
    from litkb.netutil import Client

    for st, hd, body, url in _answers(cls, host, status):
        assert Client.challenge_cause(st, url, body, hd) == cause, (url, st)


def test_sciencedirects_block_token_sits_past_guard_3s_window_and_is_read():
    """Class B, the window itself (the referee's M2: nothing held MARKER_WINDOW): the recorded page's block-page
    token lies past the first MARKER_WINDOW bytes, the window alone finds no marker, and the detector still names it —
    at the refusal status AND for the page kept with its status unknown (the ledger's typing, status None)."""
    from litkb import netutil
    from litkb.netutil import Client

    for st, hd, body, url in _answers("B", "www.sciencedirect.com", 403):
        at = body.lower().find(b"cloudflare_error")
        assert at > netutil.MARKER_WINDOW, at
        assert Client.challenge_cause(st, url, body[:netutil.MARKER_WINDOW], hd) == ""
        assert Client.challenge_cause(st, url, body, hd) == "cloudflare"
        assert Client.challenge_cause(None, None, body) == "cloudflare"


def test_wileys_article_page_at_403_stays_no_challenge():
    """The negative the whole-page read must not break (MEASURED by builder-FX-V on the same run): Wiley served the
    ARTICLE's own 227 KB page at 403 (its title, 'institution', 'log in'); Cloudflare's injected challenge-platform
    script and a login form's captcha sit at its end. Only a BLOCK-PAGE token is read past the window, so this page
    is no challenge (the ladder typed it identity_required). The page is CONSTRUCTED from its recorded shape: the
    article head, then the two strings past MARKER_WINDOW (the recorded page is not kept in this fixture)."""
    from litkb import netutil
    from litkb.netutil import Client

    head = (b"<html><head><title>Matching and record linkage - Winkler - 2014 - WIREs Computational Statistics - "
            b"Wiley Online Library</title></head><body>CONSTRUCTED institution log in ")
    page = head + b"x" * netutil.MARKER_WINDOW + (b"<div class='captcha'></div><script>s.src='/cdn-cgi/challenge-"
                                                 b"platform/scripts/precursor/main.js'</script></body></html>")
    assert Client.challenge_cause(403, "https://wires.onlinelibrary.wiley.com/doi/pdf/10.1002/wics.1317", page) == ""


def test_the_429_that_states_a_rate_limit_is_no_challenge_and_a_challenge_at_429_still_is():
    """Class D: bioRxiv's recorded 429 ('Attention Required | Cloudflare', 'a high number of requests from this
    session') is the rate limit, not a challenge — so the D45 gate records it as a rate limit (it may cool the host)
    — while a CONSTRUCTED challenge page at 429 that states no rate limit stays a challenge (auditor-fix7 AM1)."""
    from litkb.acquire import backoff
    from litkb.netutil import Client

    challenge = (b"<html><head><title>Just a moment...</title></head><body>CONSTRUCTED challenge "
                 b"<div id='cf-challenge'></div></body></html>")
    for st, hd, body, url in _answers("D", "www.biorxiv.org", 429):
        assert Client.challenge_cause(st, url, body, hd) == ""
        assert Client.challenge_cause(st, url, challenge, hd) == "cloudflare"
        gate = backoff.Gate("openaire", backoff.HostCooldowns(), lambda: 0.0)
        gate.after(url, st, hd, body)
        gate.after(url, st, hd, challenge)
        assert [o["challenge"] for o in gate.observed] == [False, True], gate.observed


def test_the_rate_limit_rule_is_a_429s_alone_and_never_outranks_a_challenge_header():
    """auditor-FX-V F5 (the rule's two edges, neither of which any recorded answer has): (1) a challenge page that
    mentions a rate limit is still a challenge at any status but 429 — the rule is keyed by the 429; (2) a 429 that
    carries a challenge HEADER is a challenge whatever its page says, so it never starts a cool-down (S4.5 decision
    D46 F2: a bot challenge never cools a host). Both pages CONSTRUCTED; bioRxiv's recorded 429 (no challenge header)
    is still the rate limit, with the answer's own recorded headers."""
    from litkb.acquire import backoff
    from litkb.netutil import Client

    says = (b"<html><head><title>Just a moment...</title></head><body>CONSTRUCTED challenge that mentions a "
            b"rate limit <div id='cf-challenge'></div></body></html>")
    for st in (403, 503, 200):
        assert Client.challenge_cause(st, "https://x.example/p", says) == "cloudflare", st
    (st, hd, body, url), *_ = _answers("D", "www.biorxiv.org", 429)
    assert Client.challenge_cause(st, url, body, hd) == ""
    flagged = dict(hd, **{"cf-mitigated": "challenge"})          # CONSTRUCTED: the recorded headers + the header
    assert Client.challenge_cause(st, url, body, flagged) == "header:cf-mitigated"
    gate = backoff.Gate("openaire", backoff.HostCooldowns(), lambda: 0.0)
    gate.after(url, st, flagged, body)
    assert [o["challenge"] for o in gate.observed] == [True], gate.observed


def test_every_caller_of_the_one_detector_agrees_on_the_recorded_bot_checks():
    """D24: the landing rung's probe, the acceptance test and the ledger's typing of a KEPT page (status unknown) each
    call every recorded bot check of classes A1-A4 and B a challenge — one detector, one word."""
    from litkb.acquire import accept, landing, ledger

    for cls, host, status in (("A1", "hal.science", 200), ("A1", "hal.inrae.fr", 200), ("A2", None, 202), ("A3", "projecteuclid.org", 200),
                              ("A4", "hdl.handle.net", 404), ("B", "www.sciencedirect.com", 403)):
        for st, hd, body, url in _answers(cls, host, status):
            assert landing.classify(st, hd, body, url, purpose="candidate")[0] == "challenge_or_bot_check", (cls, url)
            v = accept.accept(body, headers=hd, url=url, terminal_url=url, status=st, metadata_fetched=False)
            assert v.challenge, (cls, url, v.summary())
            assert ledger.type_blocked([st], body, hd)[0] == "challenge_or_bot_check", (cls, url)


# ── C6-RG removed (no database) ──────────────────────────────────────────────────────────────────

def test_the_five_c6rg_pages_are_plain_pages_and_every_recorded_interstitial_is_still_a_challenge():
    """Class C: the five DOI pages C6-RG's marker-free rule typed interstitials (NASA's LPV index, three Crossref blog
    posts, OSF's app shell) are `plain_page` — readable, never THE landing page, never a refusal. And a real
    interstitial still types as one: every recorded vendor page of the landing fixtures and this fixture (Springer's
    Client Challenge at 200, E13's Cloudflare 403, MDPI's Akamai 403, AWS WAF's 202s, ScienceDirect's 403)."""
    from litkb.acquire import landing

    pages = [e for c in CASES if c["class"] == "C" for e in ENTRIES[c["case"]] if e["response"]["status"] == 200]
    assert len(pages) == 5
    for e in pages:
        verdict, _why = landing.classify(200, e["response"]["headers"], _body(e), e["key"]["url"], purpose="page")
        assert verdict == "plain_page", e["key"]["url"]
        p = landing.Page(e["key"]["url"], 200, e["response"]["headers"], _body(e), "doi", verdict, "")
        assert p.readable
    springer = json.loads((LANDING_FIX / "springer" / "recording.json").read_text(encoding="utf-8"))
    interstitials = [
        (200, {}, (LANDING_FIX / "springer" / springer["hops"][-1]["response"]["body_file"]).read_bytes(),
         "https://link.springer.com/article/10.1007/BF00531768"),
        (403, {}, (SCRIPTS / "qc" / "fixtures" / "litkb_e13_challenge_b65a33b17354.html").read_bytes(),
         "https://x.example/e13"),
        (403, {}, (SCRIPTS / "qc" / "fixtures" / "litkb_mdpi_pdf_akamai_a3b93f589df6.html").read_bytes(),
         "https://www.mdpi.com/2072-4292/15/3/765/pdf"),
    ] + _answers("A2", None, 202) + _answers("B", "www.sciencedirect.com", 403)[:1]
    for st, hd, body, url in interstitials:
        assert landing.classify(st, hd, body, url, purpose="page")[0] == "challenge_or_bot_check", url


# ── a transport encoding is not a wrapper (no database) ────────────────────────────────────────────

def test_a_gzip_coded_wayback_capture_is_the_html_page_it_is():
    """Class F: each recorded Wayback `id_` capture served `Content-Encoding: gzip` is decoded before the byte rules
    read it — `html_response`, the coding recorded as a fact. The same bytes with NO declared coding are still C18's
    wrapper case (`compressed_or_archived_payload`): the decode follows the header, never the magic alone."""
    from litkb.acquire import accept

    caps = _answers("F", "web.archive.org", 200)
    assert len(caps) == 7
    for st, hd, body, url in caps:
        assert body[:2] == b"\x1f\x8b" and accept._header(hd, "content-encoding") == "gzip", url
        v = accept.accept(body, headers=hd, url=url, terminal_url=url, status=st, metadata_fetched=False)
        assert (v.verdict, v.sub_status, v.facts.get("content_encoding")) == ("refuse", "html_response", "gzip"), url
        bare = accept.accept(body, url=url, terminal_url=url, status=st, metadata_fetched=False)
        assert (bare.verdict, bare.sub_status) == ("refuse", "compressed_or_archived_payload"), url


def test_a_pdf_under_a_gzip_transport_coding_is_still_the_pdf():
    """The decode never loses a file: a CONSTRUCTED one-page PDF served gzip-coded is accepted as that PDF."""
    from litkb.acquire import accept

    pdf = P2M.make_pdf([f"CONSTRUCTED transport-coded PDF line {i} {uuid.uuid4().hex}" for i in range(120)])
    assert len(pdf) > 5000
    v = accept.accept(gzip.compress(pdf), headers={"Content-Encoding": "gzip"}, url="https://x.example/p.pdf",
                      metadata_fetched=False)
    assert v.verdict == "accept" and v.pdf == pdf and v.facts["content_encoding"] == "gzip", v.summary()


# ── the round-2 edges the recorded answers do not reach (no database; CONSTRUCTED, each says so) ──────

class _Seq:
    """CONSTRUCTED answers, in order, for every URL (the last repeats) — a Stage B client stand-in."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        return self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]


class _Ctx:
    """A CONSTRUCTED rung context: clients by route, a pacer that never sleeps."""

    def __init__(self, clients):
        from litkb.netutil import Pacer
        self.clients, self.pacer, self.work_class = clients, Pacer(interval=0, sleep=lambda s: None), ""


def test_stage_bs_transient_decision_reads_the_headers_so_a_header_only_challenge_stays_asked():
    """auditor-FX-V F4: Stage B asks the one detector TWICE per answer — first to decide whether the answer is
    transient (a transient URL is released for the ladder's scheduled retry), then to type it. A 503 whose only
    challenge signature is its header (`cf-mitigated: challenge`; the page names no check) is a challenge on BOTH
    calls: booked blocked/challenge_or_bot_check and its URL stays asked — a challenge is never retried (C1a's rule,
    `backoff.classify`). Read without the headers the first call calls it a transient 503 and releases the URL.
    CONSTRUCTED answer: no recorded answer has this shape."""
    from litkb.acquire import stage_b as B

    url = "https://x.example/f.pdf"
    s, work = _Seq([(503, {"cf-mitigated": "challenge"}, b"<html><body>CONSTRUCTED</body></html>")]), {}
    r = B.fetch_candidates("hal", [(url, {})], _Ctx({"hal": s}), work)
    assert (r["status"], r.get("sub_status")) == tuple(CHALLENGE), r
    assert url in work["asked_urls"], work


def test_a_rules_own_challenge_signature_still_types_a_page_the_one_detector_is_silent_on():
    """auditor-FX-V F2: the rule table's host-specific signatures (`landing._challenge`, each selected rule's
    `challenge_signature`) speak where the one detector is silent. Every RECORDED ScienceDirect block page is now named
    first by the detector's block-page token, so this CONSTRUCTED 403 page carries ONLY the Elsevier rule's own
    marker — the survey 2.1 wording "CPE00001 / There was a problem providing the content you requested" — and no
    generic marker, no block-page token: the detector answers '', the Elsevier rule types it a challenge, and with no
    rule selected it is a 403 about the article (identity_required)."""
    from litkb.acquire import landing
    from litkb.netutil import Client

    url = "https://www.sciencedirect.com/science/article/pii/S0034425721005265/pdfft"
    page = (b"<html><head><title>ScienceDirect</title></head><body>CONSTRUCTED CPE00001 There was a problem providing "
            b"the content you requested</body></html>")
    assert Client.challenge_cause(403, url, page) == ""
    rules = landing.rules_for("10.1016/j.rse.2021.112806", [url])
    assert any(r["id"] == "elsevier" for r in rules), [r["id"] for r in rules]
    assert landing.classify(403, {}, page, url, rules=rules, purpose="candidate") == \
        ("challenge_or_bot_check", "elsevier:cpe00001")
    assert landing.classify(403, {}, page, url, purpose="candidate")[0] == "identity_required"
    # auditor-FX-V r2 N-2 (S4.5 decision D58, integrator-w4): the rule's signature is read in the WHOLE body — the
    # loop's stated reason (ScienceDirect's wording sits ~770 KB in) — so the same CONSTRUCTED page padded past the
    # generic window before its marker is still the Elsevier rule's challenge
    from litkb import netutil
    far = page.replace(b"<body>", b"<body>" + b"<p>CONSTRUCTED padding</p>" * (netutil.MARKER_WINDOW // 20 + 1), 1)
    assert far.index(b"CPE00001") > netutil.MARKER_WINDOW and Client.challenge_cause(403, url, far) == ""
    assert landing.classify(403, {}, far, url, rules=rules, purpose="candidate") == \
        ("challenge_or_bot_check", "elsevier:cpe00001")


def test_d58_the_detectors_unpinned_edges_hold():
    """auditor-FX-V r2 N-1 and N-3 (S4.5 decision D58, integrator-w4) — guards no recorded answer reaches, each pinned
    on a CONSTRUCTED input (named so):
      * the title reader folds the typographic apostrophe: Anubis's title spelled with U+2019 is still Anubis;
      * CHALLENGE_TITLES are read in the TITLE only (survey G0d: a solved page names its guard elsewhere, never in its
        title): a page whose title is ordinary and whose BODY quotes Anubis's words is no challenge;
      * step 0's inflation cap: a gzip-coded body that inflates past UNWRAP_MAX_BYTES is left as it came (step 1
        judges it), never typed on a truncated inflation;
      * TRANSPORT_GZIP's `x-gzip` alias (RFC 9110 §8.4.1.3) decodes like `gzip`."""
    from litkb import netutil
    from litkb.acquire import accept
    from litkb.netutil import Client

    url = "https://hal.science/CONSTRUCTED"
    curly = "<html><head><title>Making sure you’re not a bot!</title></head><body></body></html>".encode("utf-8")
    assert Client.challenge_cause(200, url, curly) == "anubis"
    solved = (b"<html><head><title>CONSTRUCTED article page</title></head><body><p>This site checks by making sure "
              b"you're not a bot; the check is done.</p></body></html>")
    assert Client.challenge_cause(200, url, solved) == "" and netutil.challenge_words(solved) == ""
    big = gzip.compress(b"\0" * 4096)
    orig = accept.UNWRAP_MAX_BYTES
    try:
        accept.UNWRAP_MAX_BYTES = 1024             # CONSTRUCTED cap: the real one is 128 MiB
        assert accept.decode_transport(big, {"Content-Encoding": "gzip"}) == (big, None)
    finally:
        accept.UNWRAP_MAX_BYTES = orig
    assert accept.decode_transport(big, {"Content-Encoding": "gzip"}) == (b"\0" * 4096, "gzip")
    assert accept.decode_transport(gzip.compress(b"CONSTRUCTED"), {"Content-Encoding": "x-gzip"}) == \
        (b"CONSTRUCTED", "x-gzip")


# ── the named rows, through the ladder, on the worker database ─────────────────────────────────────

@pytest.fixture
def pg(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    h = P2M.P2(psycopg, conn)
    yield h
    while h.opened:
        h.opened.pop().close()


def _store(tmp_path):
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def _rows(pg, wid, route):
    return pg.conn.execute("SELECT status, sub_status, retriable, detail FROM litkb.acquisition_attempts "
                           "WHERE work_id = %s AND route = %s ORDER BY at, id", (wid, route)).fetchall()


def _ladder(pg, tmp_path, monkeypatch, case, rungs=None, clients=None):
    """ONE ladder run of the case's route for a CONSTRUCTED admitted work carrying the attempt's real DOI, every
    request answered from the fixture (the case's own cassette row). -> the route's attempt rows."""
    from litkb import cassette as CAS
    from litkb.acquire import open_access, run
    from litkb.netutil import Client

    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "fxv-test@example.invalid")   # scrubbed from keys
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = dict(P2M._admitted(pg, w, ws), doi=case["doi"])
    cas = CAS.Cassette(FIX / "index.jsonl", "replay", bodies=FIX / "bodies")
    cas.begin_row(case["case"])
    run.acquire(w, ws, pg.tokens[ws], work, store=_store(tmp_path), routes=(case["route"],), rungs=rungs,
                clients=clients or {case["route"]: Client(cassette=cas)}, agent="fx-v", session="fx-v-1",
                pacer=P2M._nopace(), printer=lambda *a, **k: None, pacing={}, mode="measure" if case["mode"] == "measure" else "acquire")
    return _rows(pg, work["work_id"], case["route"])


LADDER_CASES = [c for c in CASES if c["route"] != "wayback"]


@pg_only
@pytest.mark.parametrize("case", [c for c in LADDER_CASES if c["class"] != "U"],
                         ids=lambda c: f"{c['run_row']}-{c['class']}-{c['route']}-{c['attempt'][:13]}")
def test_the_named_row_is_retyped_by_the_ladder_on_its_recorded_bytes(pg, tmp_path, monkeypatch, case):
    """The referee's REAL row, end to end: the attempt's REAL rung replayed from its recorded answers through
    `run.acquire` (the ladder's own `_record_result` typing). The first row of the route carries the referees' word;
    on main 411c3ce it carried the word in `recorded` (provenance.json)."""
    rows = _ladder(pg, tmp_path, monkeypatch, case)
    assert rows, case["case"]
    status, sub, retriable, detail = rows[0]
    assert [status, sub] == case["expected"], (case["case"], case["recorded"], status, sub, detail.get("detail"))
    assert retriable is (status == "api-error"), (case["case"], retriable)
    if case["class"] == "C":
        # C6-RG's surviving half (auditor-FX-V F1): the DOI page is a plain page — READ for its pointers, never
        # recorded as THE landing page (`detail.landing.landing_page` is a page with citation metadata only)
        land = detail["landing"]
        assert land["doi_page"]["verdict"] == "plain_page", (case["case"], land["doi_page"])
        assert land["landing_page"] is None, (case["case"], land["landing_page"])
        assert any(t.endswith("=plain_page") for t in detail["tried"]), (case["case"], detail["tried"])


@pg_only
@pytest.mark.parametrize("case", [c for c in LADDER_CASES if c["class"] == "U"], ids=lambda c: c["attempt"][:13])
def test_l092s_bare_403_is_pinned_as_recorded_and_never_graded(pg, tmp_path, monkeypatch, case):
    """Class U (referee-vocabulary: UNDETERMINED — the plan text does not say which word a bare 403 takes): the fix
    changes neither of L092's two rows. Pinned so a change is a decision, not an accident; never a grade."""
    rows = _ladder(pg, tmp_path, monkeypatch, case)
    assert [rows[0][0], rows[0][1]] == case["recorded"], (case["case"], rows[0][:3])


def _wayback_rung(case):
    """The Wayback rung's answer for the case, rebuilt from its RECORDED capture (the rung itself needs the run's
    dead-URL input, which a constructed work does not hold): the shape `litkb.acquire.wayback` returns for a capture
    that was not a PDF — the kept body, its URL and its terminal response with the recorded headers."""
    from litkb.acquire import run

    e = next(x for x in ENTRIES[case["case"]] if x["response"]["status"] == 200)

    def fn(work, ctx):
        term = {"url": e["key"]["url"], "status_code": 200, "headers": dict(e["response"]["headers"])}
        return {"status": "bad-file", "rejected": _body(e), "rejected_url": e["key"]["url"], "http_codes": [200],
                "tried": ["web.archive.org:200"], "terminal": term}
    return run.Rung("wayback", fn, needs=("doi",))


@pg_only
@pytest.mark.parametrize("case", [c for c in CASES if c["route"] == "wayback"],
                         ids=lambda c: f"{c['run_row']}-{c['attempt'][:13]}")
def test_the_named_wayback_capture_is_booked_html_response(pg, tmp_path, monkeypatch, case):
    """Class F through the ladder: the recorded gzip-coded capture, with its recorded headers, is typed by the
    acceptance test the ladder runs (`ledger.bad_file_verdict`) — `bad-file/html_response`, the coding in the facts."""
    rows = _ladder(pg, tmp_path, monkeypatch, case, rungs=[_wayback_rung(case)], clients={})
    status, sub, _retriable, detail = rows[0]
    assert [status, sub] == case["expected"], (case["case"], status, sub)
    assert detail["acceptance"]["facts"]["content_encoding"] == "gzip", detail["acceptance"]

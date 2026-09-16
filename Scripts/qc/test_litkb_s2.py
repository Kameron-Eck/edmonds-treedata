"""The Semantic Scholar leg: batching, backoff, the versioned cache, and the four kills.

No database, no network: every test drives a stub client whose answers are written in the test, and a
stub sleep that records what the ladder would have waited rather than waiting it.

THE KILLS THIS FILE OWNS (each is shown firing on a known-bad input, CLAUDE.md 3.4c):
  * a 429 storm backs off, is COUNTED, and ends as a recorded rate-limit error — never as a silent
    skip and never as an empty, cacheable answer;
  * a batch response missing an id marks THAT id unresolved and shifts nothing;
  * a batch response of the wrong length is refused whole, because alignment is the only thing
    attaching a record to an id;
  * a cache entry written under an older schema version is not served to the newer parser;
  * the P6 near-miss kills (wrong DOI, wrong title, wrong year) still fire with the S2 leg on.
"""
import json

import pytest

from litkb.admit import resolver as RES
from litkb.admit import s2 as S
from litkb.extract import references as R


class StubClient:
    """Answers from a list of (status, headers, body) turns, recording every request."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def get(self, url, accept="application/json", timeout=60, data=None, headers=None, **kw):
        self.calls.append({"url": url, "data": data, "headers": headers or {}})
        st, hd, body = self.turns.pop(0) if self.turns else (200, {}, b"[]")
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        return st, hd, body


class MemCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def put(self, key, status, body):
        self.store[key] = (status, body if isinstance(body, bytes) else json.dumps(body).encode())


def paper(doi, title, family, year):
    return {"externalIds": {"DOI": doi}, "title": title, "year": year,
            "authors": [{"name": family}]}


def client_with(turns, sleeps=None, cache=None):
    c = StubClient(turns)
    s = S.S2Client(client=c, cache=cache, sleep=(sleeps.append if sleeps is not None else lambda _s: None),
                   jitter=lambda: 0.0)
    return c, s


# ── the batch endpoint ──────────────────────────────────────────────────────────────────

def test_a_batch_posts_json_with_the_ids_in_the_body_and_the_fields_in_the_query():
    c, s = client_with([(200, {}, [paper("10.1/a", "A", "Alpha", 2001)])])
    got, err = s.batch(["DOI:10.1/a"])
    assert err == ""
    assert got["DOI:10.1/a"]["title"] == "A"
    call = c.calls[0]
    assert call["url"].startswith(S.BATCH_URL + "?fields=")
    assert "abstract" not in call["url"] and "tldr" not in call["url"]   # narrowest field list
    assert json.loads(call["data"].decode()) == {"ids": ["DOI:10.1/a"]}
    assert call["headers"]["Content-Type"] == "application/json"


def test_a_missing_id_in_a_batch_marks_that_id_and_shifts_nothing():
    """THE KILL: S2 answers with a null in place, positionally. If the null were dropped rather than
    kept, every record after it would attach to the wrong reference."""
    c, s = client_with([(200, {}, [paper("10.1/a", "A", "Alpha", 2001), None,
                                   paper("10.1/c", "C", "Gamma", 2003)])])
    got, err = s.batch(["DOI:10.1/a", "DOI:missing", "DOI:10.1/c"])
    assert err == ""
    assert got["DOI:missing"] is None
    assert got["DOI:10.1/a"]["title"] == "A" and got["DOI:10.1/c"]["title"] == "C"


def test_a_batch_response_of_the_wrong_length_is_refused_whole():
    """THE ALIGNMENT KILL. Two records for three ids: the alignment is gone, so nothing is used."""
    c, s = client_with([(200, {}, [paper("10.1/a", "A", "Alpha", 2001),
                                   paper("10.1/c", "C", "Gamma", 2003)])])
    got, err = s.batch(["DOI:10.1/a", "DOI:missing", "DOI:10.1/c"])
    assert "length mismatch" in err
    assert set(got.values()) == {None}


def test_ids_are_deduplicated_before_the_call_and_mapped_back():
    c, s = client_with([(200, {}, [paper("10.1/a", "A", "Alpha", 2001)])])
    got, err = s.batch(["DOI:10.1/a", "DOI:10.1/a", ""])
    assert err == "" and json.loads(c.calls[0]["data"].decode())["ids"] == ["DOI:10.1/a"]
    assert got["DOI:10.1/a"]["title"] == "A"


def test_more_than_the_maximum_is_chunked(monkeypatch):
    monkeypatch.setattr(S, "BATCH_MAX", 2)
    c, s = client_with([(200, {}, [paper("10.1/a", "A", "Alpha", 2001), None]),
                        (200, {}, [paper("10.1/c", "C", "Gamma", 2003)])])
    got, err = s.batch(["DOI:a", "DOI:b", "DOI:c"])
    assert err == "" and len(c.calls) == 2
    assert [len(json.loads(x["data"].decode())["ids"]) for x in c.calls] == [2, 1]
    assert got["DOI:b"] is None and got["DOI:c"]["title"] == "C"


# ── the 429 ladder ──────────────────────────────────────────────────────────────────────

def test_a_429_storm_backs_off_is_counted_and_ends_as_a_recorded_error():
    """THE KILL the phase is built around: the pool answers 429 to everything. The ladder must sleep,
    count, and hand back an error the breaker can read — not an empty candidate list, which would be
    indistinguishable from 'asked and found nothing'."""
    sleeps = []
    c, s = client_with([(429, {}, b'{"message":"Too Many Requests"}')] * 9, sleeps=sleeps)
    cands, err = s.match("a title")
    assert cands == [] and "429" in err
    # Concrete numbers, not `len(BACKOFFS)`: written against the ladder, a mutant that EMPTIES the
    # ladder satisfies its own arithmetic and the test goes quiet (measured — P7-G4 fired on one
    # test only until these were pinned).
    assert len(c.calls) == 5 and sleeps == [5.0, 10.0, 20.0, 40.0]     # jitter stubbed to 0.0
    assert s.stats.rate_limited == 5 and s.stats.requests == 5
    assert s.stats.seconds_sleeping == 75.0


def test_the_error_from_an_exhausted_ladder_trips_the_breaker_rather_than_being_skipped_silently():
    _c, s = client_with([(429, {}, b"{}")] * 40)
    b = R.StageBreaker()
    for _ in range(R.StageBreaker.TRIP_AFTER):
        _cands, err = s.match("a title")
        b.record("semanticscholar", err)
    assert b.is_open("semanticscholar")
    assert "429" in b.report()["semanticscholar"]


def test_a_retry_after_header_is_honoured_instead_of_the_ladder():
    sleeps = []
    c, s = client_with([(429, {"Retry-After": "3"}, b"{}"),
                        (200, {}, {"data": [paper("10.1/a", "A", "Alpha", 2001)]})], sleeps=sleeps)
    cands, err = s.match("A")
    assert err == "" and cands[0]["doi"] == "10.1/a"
    assert sleeps == [3.0] and s.stats.retry_after_seen == 1


def test_a_retry_after_longer_than_a_measurement_can_hold_gives_up_rather_than_waiting():
    sleeps = []
    _c, s = client_with([(429, {"retry-after": "3600"}, b"{}")] * 9, sleeps=sleeps)
    _cands, err = s.match("A")
    assert "429" in err and sleeps == []


def test_jitter_spreads_the_wait_without_shortening_it():
    sleeps = []
    c = StubClient([(429, {}, b"{}")] * 9)
    s = S.S2Client(client=c, cache=None, sleep=sleeps.append, jitter=lambda: 1.0)
    s.match("A")
    assert sleeps == [b * (1 + S.JITTER) for b in S.BACKOFFS]


def test_every_wire_request_is_paced_and_a_cache_hit_is_not():
    """The pool is shared and measured as exhausted; unpaced bursts manufacture the 429s the ladder
    then waits out. A cache hit must still cost nothing, or caching buys no wall clock."""
    waits = []

    class P:
        def wait(self):
            waits.append(1)

    cache = MemCache()
    c = StubClient([(200, {}, {"data": [paper("10.1/a", "A", "Alpha", 2001)]}),
                    (200, {}, {"data": [paper("10.1/b", "B", "Beta", 2002)]})])
    s = S.S2Client(client=c, cache=cache, sleep=lambda _x: None, jitter=lambda: 0.0, pacer=P())
    s.match("A")
    s.match("B")
    assert len(waits) == 2
    s.match("A")                                  # served from the cache
    assert len(waits) == 2 and s.stats.cache_hits == 1


def test_each_retry_in_the_ladder_is_paced_too():
    waits = []

    class P:
        def wait(self):
            waits.append(1)

    c = StubClient([(429, {}, b"{}")] * 40)
    s = S.S2Client(client=c, cache=None, sleep=lambda _x: None, jitter=lambda: 0.0, pacer=P())
    s.match("A")
    assert len(waits) == 5 == len(c.calls)


def test_nothing_is_cached_about_a_429():
    cache = MemCache()
    _c, s = client_with([(429, {}, b"{}")] * 9, cache=cache)
    s.match("A")
    assert cache.store == {}


def test_a_transport_failure_does_not_put_a_registered_secret_in_the_error(monkeypatch):
    """The status-0 branch is the ONE place in s2.py that embeds response bytes in a string.

    Found at the P6 merge, not on either branch: `s2.py::request::redact` is a call site of the
    redaction family, whose per-call-site rule (RD1-RD18) landed on the OTHER side of this merge,
    so neither branch's own `--sites` run could see the site. Harness row P7-RD19.
    """
    from litkb import netutil
    monkeypatch.setattr(netutil, "_SECRETS", [])
    netutil.add_secret("hunter2-archive-key")
    _c, s = client_with([(0, {}, b'{"detail": "connect failed for key=hunter2-archive-key"}')])
    st, parsed, err = s.request("GET", S.MATCH_URL + "?query=A")
    assert (st, parsed) == (0, None)
    assert "hunter2-archive-key" not in err
    assert "<KEY>" in err


# ── the cache ───────────────────────────────────────────────────────────────────────────

def test_a_settled_answer_is_served_from_the_cache_without_a_request():
    cache = MemCache()
    c, s = client_with([(200, {}, {"data": [paper("10.1/a", "A", "Alpha", 2001)]})], cache=cache)
    s.match("A")
    assert len(c.calls) == 1
    c2, s2 = client_with([], cache=cache)
    cands, err = s2.match("A")
    assert err == "" and cands[0]["doi"] == "10.1/a"
    assert c2.calls == [] and s2.stats.requests == 0 and s2.stats.cache_hits == 1


def test_a_404_is_a_settled_answer_and_caches():
    cache = MemCache()
    c, s = client_with([(404, {}, b'{"error":"Title match not found"}')], cache=cache)
    assert s.match("nothing like this") == ([], "")
    c2, s2 = client_with([], cache=cache)
    assert s2.match("nothing like this") == ([], "")
    assert c2.calls == []


def test_the_cache_does_not_serve_an_entry_written_under_an_older_schema(monkeypatch):
    """THE STALE-SCHEMA KILL. The stored body is whatever the old parser wanted; bumping the version
    must make it a miss, not a silently half-parsed hit."""
    cache = MemCache()
    c, s = client_with([(200, {}, {"data": [paper("10.1/a", "A", "Alpha", 2001)]})], cache=cache)
    s.match("A")
    assert len(cache.store) == 1
    monkeypatch.setattr(S, "CACHE_SCHEMA", "s2-999")
    c2, s2 = client_with([(200, {}, {"data": [paper("10.1/a", "A", "Alpha", 2001)]})], cache=cache)
    s2.match("A")
    assert len(c2.calls) == 1 and s2.stats.cache_hits == 0
    assert len(cache.store) == 2                  # both versions present, neither served to the other


def test_the_cache_key_separates_two_batches_that_differ_only_in_their_body():
    a = S.cache_key("POST", S.BATCH_URL, json.dumps({"ids": ["DOI:a"]}))
    b = S.cache_key("POST", S.BATCH_URL, json.dumps({"ids": ["DOI:b"]}))
    assert a != b and S.CACHE_SCHEMA in a


# ── identifiers and the candidate shape ─────────────────────────────────────────────────

def test_a_doi_and_an_arxiv_reference_take_their_documented_prefixes():
    assert S.paper_id_for({"doi": "10.1/A"}) == "DOI:10.1/a"
    assert S.paper_id_for({"doi": R.ARXIV_DOI_PREFIX + "1901.00001"}) == "ARXIV:1901.00001"
    assert S.paper_id_for({"arxiv": "1901.00002"}) == "ARXIV:1901.00002"
    assert S.paper_id_for({}) == ""


def test_a_candidate_doi_is_normalised_and_an_arxiv_only_record_keeps_its_doi_form():
    assert S.to_candidate(paper("10.1/ABC", "A", "Alpha", 2001))["doi"] == "10.1/abc"
    c = S.to_candidate({"externalIds": {"ArXiv": "1901.00001"}, "title": "A", "year": 2001,
                        "authors": [{"name": "Alpha"}]})
    assert c["doi"] == R.ARXIV_DOI_PREFIX + "1901.00001"


# ── the leg, wired into the resolver ────────────────────────────────────────────────────

REF = {"title": "Similarity measures of remotely sensed multi-sensor images",
       "first_author": "Alberga", "year": "2009"}
HIT = paper("10.3390/rs1030122", REF["title"], "V. Alberga", 2009)


def crossref_silent():
    """A Crossref stage that answers nothing, so the S2 leg is the one under test."""
    return lambda _client, _title, _pacer: ([], "")


class ConfirmingCrossref:
    """A Crossref ``/works/{doi}`` door that CONFIRMS whatever DOI it is asked, answering with the
    reference under test's own title, first author and year.

    It exists because "S2 proposes, Crossref confirms" means the S2 leg can no longer resolve
    anything with ``client=None``: every acceptance now costs a Crossref lookup. The tests below are
    about the leg's PLUMBING — batching, the prefill, ambiguity, the unchanged rules — so the
    confirmation is made to succeed here, and the confirmation itself is killed separately at the
    bottom of this file, on the real cached bodies of the three review cases.
    """

    def __init__(self, ref=None, rtype="journal-article"):
        self.ref = REF if ref is None else ref
        self.rtype = rtype
        self.asked = []

    def get(self, url, accept="application/json", timeout=60, **kw):
        import urllib.parse
        doi = urllib.parse.unquote(url.split("/works/", 1)[1])
        self.asked.append(doi)
        return 200, {}, json.dumps({"message": {
            "DOI": doi, "type": self.rtype, "title": [self.ref["title"]],
            "container-title": ["Remote Sensing"],
            "issued": {"date-parts": [[int(self.ref["year"])]]},
            "author": [{"family": self.ref["first_author"], "sequence": "first"}]}}).encode()


@pytest.fixture
def only_s2(monkeypatch):
    monkeypatch.setattr(R, "REGISTRY_STAGES", (("crossref", crossref_silent()),
                                               ("semanticscholar", RES.search_semanticscholar),
                                               ("arxiv", lambda *a: ([], ""))))


def test_the_s2_leg_resolves_a_real_reference_through_the_unchanged_rules(only_s2):
    _c, s = client_with([(200, {}, {"data": [HIT]})])
    res = R.resolve_reference(dict(REF), client=ConfirmingCrossref(), s2=s)
    assert res.state == "resolved" and res.doi == "10.3390/rs1030122"
    assert res.source == "semanticscholar" and s.stats.match_calls == 1


def test_a_wrong_title_from_the_s2_leg_is_still_refused(only_s2):
    """The P6 `title-wrong` kill with the new leg on: the registry hands back a real but different
    work and `judge_candidate` refuses it."""
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", "Rain forest fragmentation and the "
                                                   "structure of Amazonian liana communities",
                                                   "Laurance", 2009)]})])
    res = R.resolve_reference(dict(REF), client=ConfirmingCrossref(), s2=s)
    assert res.state == "unresolved" and "best=semanticscholar" in res.reason


def test_a_wrong_first_author_from_the_s2_leg_is_still_refused(only_s2):
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", REF["title"], "Efron", 2009)]})])
    assert R.resolve_reference(dict(REF), client=ConfirmingCrossref(), s2=s).state == "unresolved"


def test_a_year_three_out_from_the_s2_leg_is_still_refused(only_s2):
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", REF["title"], "V. Alberga", 2012)]})])
    assert R.resolve_reference(dict(REF), client=ConfirmingCrossref(), s2=s).state == "unresolved"


def test_two_accepted_works_from_the_s2_leg_are_still_ambiguous(only_s2):
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", REF["title"], "V. Alberga", 2009),
                                             paper("10.1/y", REF["title"], "Alberga", 2009)]})])
    res = R.resolve_reference(dict(REF), client=ConfirmingCrossref(), s2=s)
    assert res.state == "ambiguous" and len(res.candidates) == 2


def test_a_reference_carrying_a_doi_never_reaches_the_s2_leg(only_s2):
    """The §14 P6 headline kill, restated with the new leg present: the DOI decides, so a corrupted
    DOI cannot be rescued by a title match here."""
    _c, s = client_with([(200, {}, {"data": [HIT]})])
    calls = []
    R.resolve_by_doi = _spy(R.resolve_by_doi, calls)
    try:
        res = R.resolve_reference(dict(REF, doi="10.3390/rs1030123"), client=_CrossrefMiss(), s2=s)
    finally:
        R.resolve_by_doi = R.resolve_by_doi.__wrapped__
    assert calls and s.stats.match_calls == 0
    assert res.state == "unresolved" and "doi_not_registered" in res.reason


def _spy(fn, calls):
    def wrapper(*a, **kw):
        calls.append(a)
        return fn(*a, **kw)
    wrapper.__wrapped__ = fn
    return wrapper


class _CrossrefMiss:
    def get(self, url, accept="application/json", timeout=60, **kw):
        return 404, {}, b"{}"


# ── batch first, per-item for the stragglers ────────────────────────────────────────────

def test_the_prefill_answers_an_identified_reference_without_a_second_request(only_s2):
    ref = dict(REF, arxiv="1901.00001")
    rec = {"externalIds": {"ArXiv": "1901.00001", "DOI": "10.3390/rs1030122"},
           "title": REF["title"], "year": 2009, "authors": [{"name": "V. Alberga"}]}
    c, s = client_with([(200, {}, [rec])])
    S.batch_prefill([ref], s)
    res = R.resolve_reference(ref, client=ConfirmingCrossref(), s2=s)
    assert res.state == "resolved" and res.doi == "10.3390/rs1030122"
    assert s.stats.match_calls == 0 and s.stats.prefill_hits == 1
    assert len(c.calls) == 1                       # the batch, and nothing else


def test_a_prefill_miss_is_an_answer_and_still_costs_no_second_request(only_s2):
    ref = dict(REF, arxiv="1901.00001")
    c, s = client_with([(200, {}, [None])])
    S.batch_prefill([ref], s)
    res = R.resolve_reference(ref, client=ConfirmingCrossref(), s2=s)
    assert res.state == "unresolved" and s.stats.match_calls == 0 and len(c.calls) == 1


def test_a_failed_batch_leaves_the_prefill_empty_so_every_reference_falls_back(only_s2):
    """A batch that errored must not look like a batch full of misses — that would turn one transport
    failure into a run-wide 'not found'."""
    ref = dict(REF, arxiv="1901.00001")
    c, s = client_with([(500, {}, b"boom"), (200, {}, {"data": [HIT]})])
    _got, err = S.batch_prefill([ref], s)
    assert err and s.prefill == {}
    assert R.resolve_reference(ref, client=ConfirmingCrossref(), s2=s).state == "resolved"
    assert s.stats.match_calls == 1


def test_a_doi_bearing_reference_takes_no_batch_slot():
    """It is decided by its DOI above this leg, so the answer would never be read."""
    c, s = client_with([])
    got, err = S.batch_prefill([dict(REF, doi="10.3390/rs1030122"), dict(REF, arxiv="")], s)
    assert got == {} and err == "" and s.stats.batch_calls == 0 and c.calls == []


def test_references_without_an_identifier_cost_no_batch_slot():
    _c, s = client_with([])
    got, err = S.batch_prefill([dict(REF)], s)
    assert got == {} and err == "" and s.stats.batch_calls == 0


# ── the stage list ──────────────────────────────────────────────────────────────────────

def test_the_stage_names_are_unchanged_so_every_per_stage_number_stays_comparable():
    _c, s = client_with([])
    assert [n for n, _f in R.registry_stages(s)] == [n for n, _f in R.REGISTRY_STAGES]
    assert R.registry_stages(None) is R.REGISTRY_STAGES


def test_without_an_s2_client_the_legacy_search_stage_is_still_the_one_used():
    assert dict(R.registry_stages(None))["semanticscholar"] is RES.search_semanticscholar


# ── the netutil fix the batch POST needs ────────────────────────────────────────────────

class _CapturingOpener:
    """Stands in for the real opener, so the header under test is the one `_raw_get` actually built."""

    def __init__(self):
        self.req = None

    def open(self, req, timeout=None):
        self.req = req
        raise _Done()

    class _Resp:
        pass


class _Done(Exception):
    pass


def _header_built_by(data, headers):
    from litkb import netutil
    c = netutil.Client()
    op = _CapturingOpener()
    c._follow = c._nofollow = op
    c.get("https://example.org", data=data, headers=headers)
    return {k.lower(): v for k, v in op.req.headers.items()}


def test_a_caller_supplied_content_type_survives_a_request_body():
    """The batch POST sends JSON. Before the fix, `_raw_get` assigned the urlencoded Content-Type
    AFTER merging the caller's headers, so the header the caller had just set was overwritten."""
    assert _header_built_by(b"{}", {"Content-Type": "application/json"})["content-type"] \
        == "application/json"


def test_a_body_with_no_caller_header_still_gets_the_urlencoded_default():
    """The annas routes post urlencoded forms and must keep that default."""
    assert _header_built_by(b"a=1", None)["content-type"] == "application/x-www-form-urlencoded"


# -- "S2 proposes, Crossref confirms" ----------------------------------------------------
#
# THE DEFECT CLASS. A review of a book carries the reviewed book's exact title, and Semantic
# Scholar's record for such a DOI carries the title AND the BOOK's authorship - so the ratio filter,
# the first-author discriminator and the +/-1 year rule all agree while the DOI points at a
# different work. Measured: 3 of 33 new S2 resolutions on the P6 corpus, plus a sibling edition
# (`Reports/LITKB_S2_BATCHING_2026-09-15.md` 4). The rules did not fail; the registry merged a book
# with its review. So the fix is a SECOND REGISTRY, not a new threshold.
#
# THE BODIES BELOW ARE REAL, trimmed to the fields `parse_crossref` reads, taken verbatim from the
# `/works/{doi}` responses in the P6 disk cache (0 network) - the same cached bodies the report is
# written from. Replaying them is what makes these kills evidence about the archive, not about a stub.

CROSSREF_CACHED = {
    # Alwan 1988 b13 - the reference is Wadsworth's BOOK; this DOI is Sylwester's review of it.
    "10.2307/1269348": {
        "type": "journal-article", "title": ["Modern Methods for Quality Control and Improvement"],
        "subtitle": [], "container-title": ["Technometrics"],
        "issued": {"date-parts": [[1987, 8]]}, "publisher": "JSTOR",
        "author": [{"family": "Sylwester", "given": "David", "sequence": "first"},
                   {"family": "Wadsworth", "given": "Harrison M.", "sequence": "additional"},
                   {"family": "Stephens", "given": "Kenneth S.", "sequence": "additional"},
                   {"family": "Godfrey", "given": "A. Blanton", "sequence": "additional"}]},
    # Burnicki 2011 b23 - Getis's book; this DOI is Semple's review.
    "10.2307/214811": {
        "type": "journal-article",
        "title": ["Models of Spatial Processes: An Approach to the Study of Point, Line and Area "
                  "Patterns"],
        "subtitle": [], "container-title": ["Geographical Review"],
        "issued": {"date-parts": [[1979, 10]]}, "publisher": "JSTOR",
        "author": [{"family": "Semple", "given": "R. Keith", "sequence": "first"},
                   {"family": "Getis", "given": "Arthur", "sequence": "additional"},
                   {"family": "Boots", "given": "Barry", "sequence": "additional"}]},
    # Hall 1985 b10 - Serra's book; this DOI is Diggle's review.
    "10.2307/2531038": {
        "type": "journal-article", "title": ["Image Analysis and Mathematical Morphology."],
        "subtitle": [], "container-title": ["Biometrics"],
        "issued": {"date-parts": [[1983, 6]]}, "publisher": "JSTOR",
        "author": [{"family": "Diggle", "given": "P. J.", "sequence": "first"},
                   {"family": "Serra", "given": "J.", "sequence": "additional"}]},
    # Foody 2010 b58 - the sibling edition: Magidson & Vermunt 2004, offered as Vermunt 2010.
    "10.1016/b978-0-08-044894-7.01340-3": {
        "type": "book-chapter", "title": ["Latent Class Models"], "subtitle": [],
        "container-title": ["International Encyclopedia of Education"],
        "issued": {"date-parts": [[2010]]}, "publisher": "Elsevier",
        "author": [{"family": "Vermunt", "given": "J.K.", "sequence": "first"}]},
    # The control: a genuine S2 proposal that Crossref confirms. Its `issued` carries no year, which
    # is why `_year_from` falls through to `created` - kept as the registry serves it, because a
    # fixture that quietly fixed that would not be the record the resolver actually sees.
    "10.1109/cvpr.2005.177": {
        "type": "proceedings-article",
        "title": ["Histograms of Oriented Gradients for Human Detection"], "subtitle": [],
        "container-title": ["2005 IEEE Computer Society Conference on Computer Vision and Pattern "
                            "Recognition (CVPR05)"],
        "issued": {"date-parts": [[None]]}, "created": {"date-parts": [[2005, 7, 27]]},
        "publisher": "IEEE",
        "author": [{"family": "Dalal", "given": "N.", "sequence": "first"},
                   {"family": "Triggs", "given": "B.", "sequence": "additional"}]},
}

#: The parsed references, verbatim from `{DERIVED}/p6/references.jsonl` (the fields the rule reads).
REFS_CACHED = {
    "Alwan_1988:b13": {
        "title": "Modern Methods for Quality Control and Improvement", "first_author": "Wadsworth",
        "year": "1986", "journal": "", "publisher": "John Wiley",
        "authors": [{"family": "Wadsworth"}, {"family": "Stephens"}, {"family": "Kenneth"},
                    {"family": "Godfrey"}, {"family": "Blanton"}],
        "raw": "Wadsworth, Harrison M.. Stephens. Kenneth S., and Godfrey, Blan- ton A . (1986), "
               "Modern Methods for Quality Control and Improve- ment, New York: John Wiley."},
    "Burnicki_2011:b23": {
        "title": "Models of Spatial Processes: An Approach to the Study of Point, Line and Area "
                 "Patterns",
        "first_author": "Getis", "year": "1978", "journal": "",
        "publisher": "Cambridge University Press",
        "authors": [{"family": "Getis"}, {"family": "Boots"}],
        "raw": "GETIS, A. and BOOTS, B., 1978, Models of Spatial Processes."},
    "Hall_1985:b10": {
        "title": "Image Analysis and Mathematical Morphology", "first_author": "Serra",
        "year": "1982", "journal": "", "publisher": "Academic Press",
        "authors": [{"family": "Serra"}],
        "raw": "J. Serra, Image Analysis and Mathematical Morphology (Academic Press, 1982)."},
    "Foody_2010:b58": {
        "title": "Latent class models", "first_author": "Magidson", "year": "2004",
        "journal": "The SAGE Handbook of Quantitative Methodology for the Social Sciences",
        "publisher": "Sage",
        "authors": [{"family": "Magidson"}, {"family": "Vermunt"}],
        "raw": "Magidson, J., & Vermunt, J. K. (2004). Latent class models."},
    "Benedek_2015:b19": {
        "title": "Histograms of oriented gradients for human detection", "first_author": "Dalal",
        "year": "2005", "journal": "CVPR", "publisher": "",
        "authors": [{"family": "Dalal"}, {"family": "Triggs"}],
        "raw": "N. Dalal and B. Triggs, Histograms of oriented gradients, CVPR 2005."},
}


class CrossrefReplay:
    """Serves the cached `/works/{doi}` bodies and nothing else. A DOI not in the table is a 404, so
    a test can never accidentally reach past the replay."""

    def __init__(self, table=None):
        self.table = dict(CROSSREF_CACHED if table is None else table)
        self.asked = []

    def get(self, url, accept="application/json", timeout=60, **kw):
        import urllib.parse
        doi = urllib.parse.unquote(url.split("/works/", 1)[1])
        self.asked.append(doi)
        msg = self.table.get(doi)
        if msg is None:
            return 404, {}, b"{}"
        return 200, {}, json.dumps({"message": dict(msg, DOI=doi)}).encode()


def _confirm(ref_key, doi, table=None):
    client = CrossrefReplay(table)
    verdict, reason, _rec = RES.confirm_s2_candidate({"doi": doi}, REFS_CACHED[ref_key], client, None)
    return verdict, reason, client


@pytest.mark.parametrize("ref_key,doi", [("Alwan_1988:b13", "10.2307/1269348"),
                                         ("Burnicki_2011:b23", "10.2307/214811"),
                                         ("Hall_1985:b10", "10.2307/2531038")])
def test_a_review_of_the_cited_book_is_refused_as_review_record(ref_key, doi):
    """THE KILL, on the three real cases. All three of the resolver's own rules pass on S2's record
    for these DOIs; Crossref, asked the same DOI, names the REVIEWER first and the reference's own
    first author after him. The reason is pinned BY NAME: refusing them as a plain author mismatch
    would make the class invisible again, and would let the mutation that deletes the review
    detector go quiet (the P7-G4 lesson - a test written against the thing it tests says nothing)."""
    verdict, reason, client = _confirm(ref_key, doi)
    assert verdict == "refused"
    assert reason.startswith("review_record ("), reason
    assert client.asked == [doi]          # Crossref was actually consulted, not guessed at


def test_the_sibling_edition_is_ambiguous_not_resolved():
    """Foody 2010 b58: Magidson & Vermunt 2004, offered as Vermunt 2010 under the same title. Same
    work, another edition - ambiguous, never resolved to the wrong year's DOI."""
    verdict, reason, _ = _confirm("Foody_2010:b58", "10.1016/b978-0-08-044894-7.01340-3")
    assert verdict == "ambiguous"
    assert reason.startswith("edition_mismatch ("), reason


def test_a_genuine_s2_proposal_that_crossref_confirms_still_resolves():
    """The other half of the kill: the rule must not simply refuse everything S2 proposes."""
    verdict, reason, _ = _confirm("Benedek_2015:b19", "10.1109/cvpr.2005.177")
    assert verdict == "confirmed", reason


def test_a_book_reference_never_takes_a_journal_article_record():
    """Type compatibility, independent of the author signature: the same Serra book against a
    journal-article whose author list gives nothing away still refuses - as `type_mismatch`."""
    table = dict(CROSSREF_CACHED)
    table["10.2307/2531038"] = dict(table["10.2307/2531038"],
                                    author=[{"family": "Serra", "given": "J.", "sequence": "first"}])
    verdict, reason, _ = _confirm("Hall_1985:b10", "10.2307/2531038", table)
    assert verdict == "refused"
    assert reason.startswith("type_mismatch ("), reason


def test_a_doi_crossref_does_not_know_is_refused_by_name():
    verdict, reason, _ = _confirm("Hall_1985:b10", "10.9999/not.registered")
    assert verdict == "refused"
    assert reason.startswith("crossref_not_registered ("), reason


def test_a_one_letter_crossref_family_is_not_read_as_a_reviewer():
    """Crossref's first author for 10.2307/2529186 comes back as the family name `D.` - one
    letter. WHAT THAT IS is not measurable from the record: a truncated surname and a given name in
    the family slot look identical here. It has the exact shape of a prepended reviewer, so the
    detector must NOT claim it; a reviewer's surname is not one letter. The row is still refused -
    it is a Wiley book against a journal-article record - but under a name that asserts only what
    was measured."""
    table = dict(CROSSREF_CACHED)
    table["10.2307/2529186"] = {
        "type": "journal-article", "title": ["Statistical Methods for Rates and Proportions."],
        "subtitle": [], "container-title": ["Biometrics"],
        "issued": {"date-parts": [[1973, 9]]}, "publisher": "JSTOR",
        "author": [{"family": "D.", "given": "F. N.", "sequence": "first"},
                   {"family": "Fleiss", "given": "J. L.", "sequence": "additional"}]}
    ref = dict(REFS_CACHED["Hall_1985:b10"],
               title="Statistical methods for rates and proportions", first_author="Fleiss",
               year="1973", authors=[{"family": "Fleiss"}])
    verdict, reason, _rec = RES.confirm_s2_candidate(
        {"doi": "10.2307/2529186"}, ref, CrossrefReplay(table), None)
    assert verdict == "refused"
    assert not reason.startswith("review_record"), reason


def _confirm_rec(msg, ref, doi="10.2307/9999999"):
    return RES.confirm_s2_candidate({"doi": doi}, ref, CrossrefReplay({doi: msg}), None)


#: The round-2 plant, verbatim in shape: a JSTOR-style review of a book whose REVIEWER happens to
#: carry the book's first author's surname. Every rule the resolver has agrees with it — S2's record
#: for a review DOI carries the book's title, the book's authorship and the book's year — and the
#: reviewed reference parses NEITHER a journal NOR a publisher, so `type_mismatch` is blind to it.
#: Before the round-2 fix this came back `confirmed` and the review resolved as the book.
_SAME_SURNAME_REVIEW = {
    "type": "journal-article", "title": ["Remote Sensing and Image Interpretation"],
    "subtitle": [], "container-title": ["Technometrics"],
    "issued": {"date-parts": [[1988, 5]]}, "publisher": "JSTOR",
    "author": [{"family": "Lillesand", "given": "Roger", "sequence": "first"},
               {"family": "Lillesand", "given": "Thomas M.", "sequence": "additional"},
               {"family": "Kiefer", "given": "Ralph W.", "sequence": "additional"}]}

_SAME_SURNAME_REF = {
    "title": "Remote sensing and image interpretation", "first_author": "Lillesand",
    "year": "1987", "journal": "", "publisher": "",
    "authors": [{"family": "Lillesand"}, {"family": "Kiefer"}],
    "raw": "T. M. Lillesand and R. W. Kiefer, Remote sensing and image interpretation, 1987."}


def test_a_same_surname_reviewer_no_longer_walks_past_the_review_detector():
    """THE ROUND-2 KILL (`Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md` §4). The old detector
    fired only when the head of Crossref's author list was NOT the reference's first author, so a
    reviewer who shares that surname was invisible to it; with no journal and no publisher parsed —
    61 of the 658 P6 references, 9.3 % — the type test could not speak either, and the record was
    CONFIRMED. The decision no longer looks at whether the names match: the record's list is exactly
    one longer than the reference's own and contains it as a suffix, which is what "the reviewer,
    then the work" looks like whatever the reviewer is called."""
    verdict, reason, _ = _confirm_rec(_SAME_SURNAME_REVIEW, _SAME_SURNAME_REF)
    assert verdict == "refused", reason
    assert reason.startswith("review_record ("), reason
    assert "exactly one extra name" in reason, reason


def test_a_same_surname_genuine_article_is_still_confirmed():
    """The other half of the kill, and why the fix is a SIGNATURE and not a surname ban: the same
    authorship, the same missing journal and publisher, an ordinary record — and it resolves. A rule
    that refused this would have closed the hole by closing the door."""
    genuine = dict(_SAME_SURNAME_REVIEW,
                   author=[{"family": "Lillesand", "given": "Thomas M.", "sequence": "first"},
                           {"family": "Kiefer", "given": "Ralph W.", "sequence": "additional"}])
    genuine["container-title"] = ["Photogrammetric Engineering and Remote Sensing"]
    verdict, reason, _ = _confirm_rec(genuine, _SAME_SURNAME_REF)
    assert verdict == "confirmed", reason


def test_the_type_blind_class_refuses_a_review_marked_record_under_its_own_name():
    """The second net, named separately so the reason histogram still says which test spoke: for a
    reference with neither a journal nor a publisher, ANY review signal in the record withholds
    confirmation — here a review marker inside the title rather than at its head, which the strong
    detector deliberately does not read, on a single-author record that no author-count signature
    would catch either."""
    rec = dict(_SAME_SURNAME_REVIEW,
               title=["Remote Sensing and Image Interpretation: a review of the third edition"],
               author=[{"family": "Lillesand", "given": "Thomas M.", "sequence": "first"}])
    verdict, reason, _ = _confirm_rec(rec, _SAME_SURNAME_REF)
    assert verdict == "refused", reason
    assert reason.startswith("review_suspected ("), reason


def test_two_authors_of_the_same_surname_are_not_read_as_a_reviewer():
    """The control on the SECOND net, and the reason its author clause counts people rather than
    comparing names. A genuine paper by two authors who share a surname gives Crossref the list
    ['wang', 'wang'] with the reference's first author sitting at position 1 — the exact shape the
    broad net looks for. There is no EXTRA person, so there is no reviewer, and it resolves. This
    matters at gate 0 in particular: `resolve_doi`'s reference dict carries no journal and no
    publisher, so every candidate at the acquisition door is judged by this net."""
    rec = {"type": "journal-article", "title": ["A dual-polarimetric canopy index"], "subtitle": [],
           "container-title": ["Remote Sensing of Environment"],
           "issued": {"date-parts": [[2015, 4]]},
           "author": [{"family": "Wang", "given": "Lei", "sequence": "first"},
                      {"family": "Wang", "given": "Hui", "sequence": "additional"}]}
    ref = {"title": "A dual-polarimetric canopy index", "first_author": "Wang", "year": "2015",
           "journal": "", "publisher": "", "authors": [{"family": "Wang"}, {"family": "Wang"}],
           "raw": "L. Wang and H. Wang, A dual-polarimetric canopy index, 2015."}
    verdict, reason, _ = _confirm_rec(rec, ref)
    assert verdict == "confirmed", reason


def test_crossrefs_own_review_type_is_believed_without_an_author_list():
    """`raw_subtype`, the completeness half: a registry that SAYS the record is a review is taken at
    its word, even where the author list gives nothing away."""
    rec = dict(_SAME_SURNAME_REVIEW, subtype="book-review",
               author=[{"family": "Lillesand", "given": "Thomas M.", "sequence": "first"},
                       {"family": "Kiefer", "given": "Ralph W.", "sequence": "additional"}])
    verdict, reason, _ = _confirm_rec(rec, dict(_SAME_SURNAME_REF, journal="Technometrics"))
    assert verdict == "refused", reason
    assert reason.startswith("review_record ("), reason
    assert "subtype" in reason, reason


def _resolve_with_stages(ref, stages, client):
    import unittest.mock
    with unittest.mock.patch.object(R, "registry_stages", lambda s2=None, ref=None: stages):
        return R.resolve_by_search(ref, client, None)


def test_the_stage_6_resolver_refuses_the_review_and_keeps_the_reason():
    """End to end through `resolve_by_search`: S2 proposes the review DOI, `judge_candidate` accepts
    it on all three rules (asserted here, so the test fails if the premise ever stops holding), and
    the reference still comes back unresolved with the named reason. This is the path the 293
    references actually take."""
    ref = dict(REFS_CACHED["Alwan_1988:b13"])
    s2_cand = {"doi": "10.2307/1269348",
               "titles": ["Modern Methods for Quality Control and Improvement"],
               "family": "H. Wadsworth", "year": 1986}
    assert RES.judge_candidate(s2_cand, ref["title"], ref["first_author"], ref["year"])[0] is True
    stages = (("crossref", lambda *a: ([], "")),
              ("semanticscholar", lambda *a: ([s2_cand], "")),
              ("arxiv", lambda *a: ([], "")))
    res = _resolve_with_stages(ref, stages, CrossrefReplay())
    assert res.state == "unresolved"
    assert res.reason.startswith("review_record ("), res.reason


def test_a_confirmed_s2_candidate_still_resolves_through_stage_6():
    """And the control, end to end: the confirmation must not close the S2 leg it guards."""
    ref = dict(REFS_CACHED["Benedek_2015:b19"])
    s2_cand = {"doi": "10.1109/cvpr.2005.177",
               "titles": ["Histograms of Oriented Gradients for Human Detection"],
               "family": "Navneet Dalal", "year": 2005}
    stages = (("crossref", lambda *a: ([], "")),
              ("semanticscholar", lambda *a: ([s2_cand], "")),
              ("arxiv", lambda *a: ([], "")))
    res = _resolve_with_stages(ref, stages, CrossrefReplay())
    assert res.state == "resolved", res.reason
    assert res.doi == "10.1109/cvpr.2005.177"

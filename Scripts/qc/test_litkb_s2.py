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


@pytest.fixture
def only_s2(monkeypatch):
    monkeypatch.setattr(R, "REGISTRY_STAGES", (("crossref", crossref_silent()),
                                               ("semanticscholar", RES.search_semanticscholar),
                                               ("arxiv", lambda *a: ([], ""))))


def test_the_s2_leg_resolves_a_real_reference_through_the_unchanged_rules(only_s2):
    _c, s = client_with([(200, {}, {"data": [HIT]})])
    res = R.resolve_reference(dict(REF), client=None, s2=s)
    assert res.state == "resolved" and res.doi == "10.3390/rs1030122"
    assert res.source == "semanticscholar" and s.stats.match_calls == 1


def test_a_wrong_title_from_the_s2_leg_is_still_refused(only_s2):
    """The P6 `title-wrong` kill with the new leg on: the registry hands back a real but different
    work and `judge_candidate` refuses it."""
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", "Rain forest fragmentation and the "
                                                   "structure of Amazonian liana communities",
                                                   "Laurance", 2009)]})])
    res = R.resolve_reference(dict(REF), client=None, s2=s)
    assert res.state == "unresolved" and "best=semanticscholar" in res.reason


def test_a_wrong_first_author_from_the_s2_leg_is_still_refused(only_s2):
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", REF["title"], "Efron", 2009)]})])
    assert R.resolve_reference(dict(REF), client=None, s2=s).state == "unresolved"


def test_a_year_three_out_from_the_s2_leg_is_still_refused(only_s2):
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", REF["title"], "V. Alberga", 2012)]})])
    assert R.resolve_reference(dict(REF), client=None, s2=s).state == "unresolved"


def test_two_accepted_works_from_the_s2_leg_are_still_ambiguous(only_s2):
    _c, s = client_with([(200, {}, {"data": [paper("10.1/x", REF["title"], "V. Alberga", 2009),
                                             paper("10.1/y", REF["title"], "Alberga", 2009)]})])
    res = R.resolve_reference(dict(REF), client=None, s2=s)
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
    res = R.resolve_reference(ref, client=None, s2=s)
    assert res.state == "resolved" and res.doi == "10.3390/rs1030122"
    assert s.stats.match_calls == 0 and s.stats.prefill_hits == 1
    assert len(c.calls) == 1                       # the batch, and nothing else


def test_a_prefill_miss_is_an_answer_and_still_costs_no_second_request(only_s2):
    ref = dict(REF, arxiv="1901.00001")
    c, s = client_with([(200, {}, [None])])
    S.batch_prefill([ref], s)
    res = R.resolve_reference(ref, client=None, s2=s)
    assert res.state == "unresolved" and s.stats.match_calls == 0 and len(c.calls) == 1


def test_a_failed_batch_leaves_the_prefill_empty_so_every_reference_falls_back(only_s2):
    """A batch that errored must not look like a batch full of misses — that would turn one transport
    failure into a run-wide 'not found'."""
    ref = dict(REF, arxiv="1901.00001")
    c, s = client_with([(500, {}, b"boom"), (200, {}, {"data": [HIT]})])
    _got, err = S.batch_prefill([ref], s)
    assert err and s.prefill == {}
    assert R.resolve_reference(ref, client=None, s2=s).state == "resolved"
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

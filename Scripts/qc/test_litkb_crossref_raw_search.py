"""Item 2 (2026-09-19): Crossref SEARCH as a second proposer for the title/author-blind class --
references GROBID left with no parsed title or no parsed first author, where `resolve_by_search`'s
own title+author+year ladder has nothing to hand `judge_candidate` at all.

Design source (read-only, another worktree): `Reports/LITKB_REFMATCHER_2026-09-15.md` section 9,
"Integration point, named, not implemented" -- Crossref bibliographic search on the RAW citation
string, top hit only, handed to the UNCHANGED `resolver.confirm_s2_candidate`. Its own recommendation
was, in its words, "an argument for a design, not an adopted design" until this class was measured.

No live network here: `besag_b11`/`besag_b32` replay REAL Crossref responses this session fetched
live and recorded into `qc/fixtures/litkb_crossref_raw_search_item2.json` -- see that file's own
`_provenance` block -- independent of the design report's own numbers and of
`litkb_derived/refmatch/cache_crossref_search.jsonl` (CLAUDE.md 3.4c: a design is not validated on
its own reported output). The routing/synthetic cases use a small stub client, same shape as
`qc/test_litkb_references.py`'s.
"""
import json
import urllib.parse
from pathlib import Path

import pytest

from litkb.extract import references as R

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "litkb_crossref_raw_search_item2.json")
                     .read_text(encoding="utf-8"))


class _ReplayClient:
    """Answers `query.bibliographic` with the fixture's real search body and `/works/{doi}` with
    its real work body -- the two calls `resolve_by_raw_search` -> `confirm_s2_candidate` makes,
    and no others; the review/ratio rungs never reach Semantic Scholar or arXiv."""

    def __init__(self, case):
        self.search_body = json.dumps(case["crossref_search_body"]).encode("utf-8")
        self.work_body = json.dumps(case["crossref_work_body"]).encode("utf-8")
        self.urls = []

    def get(self, url, accept="application/json", timeout=60, **kw):
        self.urls.append(url)
        if "query.bibliographic" in url:
            return 200, {}, self.search_body
        if "api.crossref.org/works/" in url:
            return 200, {}, self.work_body
        return 200, {}, b"{}"


# ── real reviews: refused, but by title-blindness, not by the review detector ──────────────────

@pytest.mark.parametrize("key", ["besag_b11", "besag_b32"])
def test_a_real_review_in_the_blind_class_is_still_refused(key):
    case = FIXTURE[key]
    client = _ReplayClient(case)
    res = R.resolve_by_raw_search(case["reference_input"], client)
    assert res.state == "unresolved", (key, res)
    # MEASURED (module docstring): the review detector needs ref["first_author"] to run its
    # author-position signature, and neither of these two real records spells "review" in its own
    # Crossref title -- so the refusal that actually fires is title-blindness, not discrimination.
    assert res.reason.startswith("crossref_title_ratio ("), (key, res.reason)


@pytest.mark.parametrize("key", ["besag_b11", "besag_b32"])
def test_the_real_review_fixture_top_hit_is_the_doi_this_session_measured(key):
    """Pins the fixture itself: if a future edit swaps in a different cached body, this fails
    loudly rather than silently changing what the test above exercises."""
    case = FIXTURE[key]
    top = case["crossref_search_body"]["message"]["items"][0]["DOI"]
    assert top == case["expected_top_doi"]


# ── routing: the gate reaches raw search only for the title/author-blind class ──────────────────

def _search_json(recs):
    return json.dumps({"message": {"items": [
        dict({"DOI": r["doi"], "title": [r["title"]], "issued": {"date-parts": [[r["year"]]]}},
             **({"author": [{"family": r["family"]}]} if r.get("family") else {}))
        for r in recs]}}).encode()


def _work_json(rec):
    msg = {"DOI": rec["doi"], "title": [rec["title"]], "type": "journal-article",
           "issued": {"date-parts": [[rec["year"]]]}}
    if rec.get("family"):
        msg["author"] = [{"family": rec["family"], "sequence": "first"}]
    return json.dumps({"message": msg}).encode()


class _RoutingClient:
    """`search=` answers `query.bibliographic`, `work=` answers `/works/{doi}`, everything else
    200-empty. Records every URL asked for."""

    def __init__(self, search=None, work=None):
        self.search, self.work = search or [], work or {}
        self.urls = []

    def get(self, url, accept="application/json", timeout=60, **kw):
        self.urls.append(url)
        if "query.bibliographic" in url:
            return 200, {}, _search_json(self.search)
        if "api.crossref.org/works/" in url:
            doi = urllib.parse.unquote(url.rsplit("/works/", 1)[1])
            rec = self.work.get(R.normalize_doi(doi))
            if rec is None:
                return 404, {}, b"{}"
            return 200, {}, _work_json(rec)
        return 200, {}, b"{}"


#: SYNTHETIC (CLAUDE.md 3.4c): built to reach the one shape of the class the two real fixture cases
#: above do not -- a reference where only `first_author` is blind (title IS parsed) and the proposed
#: record is genuinely authorless, so `confirm_s2_candidate`'s "MISSING vs CONTRADICTED" branch
#: (referee task 3) is what finally admits it. Title must be present here: the title-ratio rung
#: runs unconditionally, before the author rung, and cannot pass on an empty title (that is exactly
#: what refuses both real reviews above) -- this is the only shape of the class that can reach
#: "confirmed" at all, and the module docstring says so.
_HAPPY_REF = {"title": "A dual-polarimetric canopy index for wetland monitoring", "first_author": "",
             "year": "2015", "journal": "", "publisher": "", "authors": [],
             "raw": "Some incompletely parsed citation, dual-polarimetric canopy index, 2015."}


def test_the_one_reachable_happy_path_confirms_through_the_unchanged_gate():
    client = _RoutingClient(
        search=[{"doi": "10.9/x", "title": _HAPPY_REF["title"], "family": "", "year": 2015}],
        work={"10.9/x": {"doi": "10.9/x", "title": _HAPPY_REF["title"], "family": "", "year": 2015}})
    res = R.resolve_reference(_HAPPY_REF, client)
    assert res.state == "resolved" and res.doi == "10.9/x" and res.source == "crossref_raw_search"
    assert "crossref carries no author" in res.reason


def test_resolve_by_search_routes_the_blind_class_to_the_raw_string_query():
    """The routing property itself: the query that reaches Crossref is the RAW string, not the
    (empty) title -- `resolve_by_search` cannot build a `query.bibliographic=` request from nothing
    else."""
    ref = dict(_HAPPY_REF, title="", first_author="")
    client = _RoutingClient(search=[], work={})
    R.resolve_reference(ref, client)
    bib_urls = [u for u in client.urls if "query.bibliographic" in u]
    assert bib_urls, client.urls
    assert ref["raw"] in urllib.parse.unquote(bib_urls[0])


def test_a_titled_and_authored_reference_never_reaches_the_raw_search_leg():
    ref = {"title": "Some real title", "first_author": "Smith", "year": "2010", "raw": "irrelevant"}
    client = _RoutingClient(search=[])
    R.resolve_reference(ref, client)
    assert not any("irrelevant" in u for u in client.urls)
    assert any("query.bibliographic" in u for u in client.urls), "the ordinary title search must still run"


def test_no_raw_string_is_unresolved_without_a_network_call():
    client = _RoutingClient()
    res = R.resolve_by_raw_search({"title": "", "first_author": "", "raw": ""}, client)
    assert res.state == "unresolved" and "raw_search_no_raw_string" in res.reason
    assert not client.urls, "nothing to search on must not spend a request"


def test_a_confirmed_doi_is_normalised_to_lower_case():
    """Per-call-site pin (P6-S7): `resolve_by_raw_search` normalises the DOI it returns, exactly
    as every other stage 6 leg does -- an upper-case candidate DOI must not surface unfolded."""
    client = _RoutingClient(
        search=[{"doi": "10.9/ABC", "title": _HAPPY_REF["title"], "family": "", "year": 2015}],
        work={"10.9/abc": {"doi": "10.9/ABC", "title": _HAPPY_REF["title"], "family": "", "year": 2015}})
    res = R.resolve_by_raw_search(_HAPPY_REF, client)
    assert res.state == "resolved" and res.doi == "10.9/abc"


_EDITION_REF = {"title": "Some Book Title", "first_author": "", "year": "2000",
               "journal": "", "publisher": "", "authors": [{"family": "Smith"}],
               "raw": "Smith, Some Book Title, an old printing, 2000."}


def test_a_sibling_edition_is_ambiguous_with_its_doi_normalised():
    """The `ambiguous` branch (edition_mismatch), reached through a SINGLE top-hit candidate --
    the raw leg never sees a second candidate, so this is `confirm_s2_candidate`'s own edition
    check, not the two-candidate ambiguity of the ordinary ladder. Also the second per-call-site
    normalize_doi pin, in the branch the confirmed-path test above does not exercise."""
    client = _RoutingClient(
        search=[{"doi": "10.9/EDITION", "title": _EDITION_REF["title"], "family": "Smith", "year": 2010}],
        work={"10.9/edition": {"doi": "10.9/EDITION", "title": _EDITION_REF["title"],
                               "family": "Smith", "year": 2010}})
    res = R.resolve_by_raw_search(_EDITION_REF, client)
    assert res.state == "ambiguous", res
    assert "edition_mismatch" in res.reason
    assert res.candidates and res.candidates[0]["doi"] == "10.9/edition"


def test_a_tripped_crossref_breaker_skips_the_raw_leg_too():
    """The raw leg is the SAME registry as the ordinary crossref stage, so a breaker already
    tripped on crossref (from the 608 references ahead of this one in a real run) must also stop
    the raw leg from spending a request, not just the normal ladder."""
    b = R.StageBreaker(trip_after=1)
    b.record("crossref", "crossref status 429")
    client = _RoutingClient(search=[{"doi": "10.9/x", "title": "x", "family": "", "year": 2015}])
    res = R.resolve_by_raw_search({"title": "", "first_author": "", "raw": "some raw text"},
                                  client, breaker=b)
    assert res.state == "unresolved" and not client.urls

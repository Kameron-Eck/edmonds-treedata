"""litkb P6 — stage 6 (references): TEI parsing, resolution states, the graph, and the kills.

No database and no network: every registry answer comes from :class:`StubClient`, so the whole file
runs inside `qc/check.py`. The LIVE numbers (658 references over 18 papers) are the instrument's,
`qc/instruments/litkb_p6_references.py`, and live in `Reports/LITKB_REFERENCES_2026-09-15.md`.

The mutation-sensitivity tests at the bottom are the ones the harness
(`qc/instruments/litkb_p6_mutations.py`) drives: each pins ONE guard so that weakening it in the
real source turns this file red.
"""
import json
import urllib.parse

import pytest

from litkb.extract import references as R

# ── a TEI with everything stage 6 reads ────────────────────────────────────────────────

TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
 <teiHeader><fileDesc><sourceDesc><biblStruct>
   <analytic><title level="a" type="main">The citing paper itself</title>
     <author><persName><surname>Citing</surname></persName></author></analytic>
   <monogr><imprint><date type="published" when="2020"/></imprint></monogr>
 </biblStruct></sourceDesc></fileDesc></teiHeader>
 <text>
  <body>
   <p coords="1,10,10,100,10">
    <s coords="1,10,10,100,10">A first sentence citing <ref type="bibr" coords="1,20,10,8,8"
      target="#b0">[1]</ref> and <ref type="bibr" coords="1,30,10,8,8" target="#b1">[2]</ref>.</s>
    <s coords="2,10,20,100,10">A second one citing <ref type="bibr" coords="2,40,20,8,8;2,50,20,8,8"
      target="#b0">[1]</ref> twice over a line break.</s>
   </p>
  </body>
  <back><div type="references"><listBibl>
   <biblStruct xml:id="b0" coords="9,32,200,250,7">
     <analytic><title level="a" type="main">Change detection in optical aerial images</title>
       <author><persName><forename type="first">C</forename><surname>Benedek</surname></persName></author>
       <idno type="DOI">10.1109/TGRS.2009.1234567</idno></analytic>
     <monogr><title level="j">IEEE TGRS</title>
       <imprint><date type="published" when="2009"/><biblScope unit="volume">47</biblScope>
        <biblScope unit="page">1234</biblScope></imprint></monogr>
     <note type="raw_reference">C. Benedek, Change detection in optical aerial images, IEEE TGRS 47 (2009) 1234.</note>
   </biblStruct>
   <biblStruct xml:id="b1">
     <analytic><title level="a" type="main">A wholly different study of something else</title>
       <author><persName><surname>Other</surname></persName></author></analytic>
     <monogr><imprint><date type="published" when="1998"/></imprint></monogr>
   </biblStruct>
  </listBibl></div></back>
 </text>
</TEI>""".encode()


# ── the stub registry ──────────────────────────────────────────────────────────────────

BENEDEK = {"doi": "10.1109/tgrs.2009.1234567", "title": "Change detection in optical aerial images",
           "family": "Benedek", "year": 2009}


def _crossref_work(rec):
    return json.dumps({"message": {"DOI": rec["doi"], "title": [rec["title"]],
                                   "author": [{"family": rec["family"], "sequence": "first"}],
                                   "issued": {"date-parts": [[rec["year"]]]},
                                   "type": "journal-article",
                                   "container-title": ["IEEE TGRS"]}}).encode()


def _crossref_search(recs):
    return json.dumps({"message": {"items": [
        {"DOI": r["doi"], "title": [r["title"]], "author": [{"family": r["family"]}],
         "issued": {"date-parts": [[r["year"]]]}} for r in recs]}}).encode()


class StubClient:
    """`get(url, accept=, timeout=)` -> (status, {}, body). Records every URL it was asked for."""

    def __init__(self, work=None, search=None, work_status=200, search_status=200):
        self.work = work                       # DOI -> record, for /works/{doi}
        self.search = search or []             # records returned by every search stage
        self.work_status, self.search_status = work_status, search_status
        self.urls = []

    def get(self, url, accept="application/json", timeout=60, **kw):
        self.urls.append(url)
        if "query.bibliographic" in url:
            return self.search_status, {}, _crossref_search(self.search)
        if "api.crossref.org/works/" in url:
            doi = urllib.parse.unquote(url.rsplit("/works/", 1)[1])
            rec = (self.work or {}).get(R.normalize_doi(doi))
            if rec is None or self.work_status != 200:
                return (self.work_status if self.work_status != 200 else 404), {}, b"{}"
            return 200, {}, _crossref_work(rec)
        if "datacite" in url:
            return 404, {}, b"{}"
        if "semanticscholar" in url:
            return 200, {}, json.dumps({"data": []}).encode()
        return 200, {}, b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"


def searched(client):
    return [u for u in client.urls if "query.bibliographic" in u or "semanticscholar" in u
            or "export.arxiv.org" in u]


# ── parsing ────────────────────────────────────────────────────────────────────────────

def test_only_the_back_matter_reference_list_is_parsed():
    """The header's own biblStruct describes the CITING paper. Counting it as a reference would
    make every paper cite itself and inflate the resolution denominator by one."""
    refs = R.parse_references(TEI)
    assert [r["ref_key"] for r in refs] == ["b0", "b1"]
    assert all(r["title"] != "The citing paper itself" for r in refs)


def test_a_reference_carries_its_fields_its_raw_string_and_its_boxes():
    b0 = R.parse_references(TEI)[0]
    assert b0["title"] == "Change detection in optical aerial images"
    assert b0["first_author"] == "Benedek" and b0["year"] == "2009"
    assert b0["journal"] == "IEEE TGRS" and b0["volume"] == "47" and b0["pages"] == "1234"
    assert b0["doi_norm"] == "10.1109/tgrs.2009.1234567"
    assert b0["raw_source"] == "grobid-raw" and b0["raw"].startswith("C. Benedek")
    assert b0["boxes"] == [{"page": 9, "bbox": [32.0, 200.0, 282.0, 207.0]}]
    assert b0["confidence"] is None, "GROBID publishes no biblStruct confidence; it must not be invented"


def test_a_reference_with_no_raw_note_falls_back_and_says_so():
    b1 = R.parse_references(TEI)[1]
    assert b1["raw_source"] == "tei-itertext" and b1["raw"]


def test_a_mention_carries_its_page_box_sentence_and_target():
    ms = R.citation_mentions(TEI)
    assert [m["target"] for m in ms] == ["b0", "b1", "b0", "b0"]
    assert ms[0]["page"] == 1 and ms[0]["sentence"].startswith("A first sentence")
    assert ms[2]["page"] == 2 and ms[2]["box_index"] == 0 and ms[3]["box_index"] == 1, \
        "a wrapped <ref> carries one box per line; collapsing them drops half the region"


def test_mention_counts_reach_the_reference_rows():
    """A MENTION IS AN ELEMENT, NOT A BOX. b0 is cited twice in TEI and the second marker wraps
    across a line, so it carries two boxes and three mention ROWS. Counting rows said "cited 3
    times" — the F1 defect of the P6 referee, which inflated 139 of 658 live rows and re-ordered
    the most-cited table. The rows stay per-box (geometry); the count is per element."""
    out = R.process_tei(TEI, "citing", StubClient(), resolve=False)
    counts = {r["ref_key"]: r["mention_count"] for r in out["references"]}
    assert counts == {"b0": 2, "b1": 1}
    assert len(out["citation_mentions"]) == 4, "the per-box rows must not be collapsed"


def test_the_three_mention_totals_are_reported_separately():
    """Box rows, elements and untargeted elements are three different numbers, and a report that
    quotes one for another is wrong by construction (F1)."""
    tot = R.mention_totals(R.citation_mentions(TEI))
    assert tot == {"mention_box_rows": 4, "mention_elements": 3,
                   "mentions_without_target": 0, "mentions_verifiable": 3}


# ── resolution ─────────────────────────────────────────────────────────────────────────

def test_a_reference_with_a_doi_resolves_by_that_doi():
    c = StubClient(work={BENEDEK["doi"]: BENEDEK})
    res = R.resolve_reference(R.parse_references(TEI)[0], c)
    assert res.state == "resolved" and res.doi == BENEDEK["doi"] and res.source == "doi"
    assert not searched(c), "a reference with a DOI must not be title-searched at all"


def test_a_doi_pointing_at_a_different_work_is_unresolved_not_resolved():
    """The Averkov class (§14 P2): the DOI is registered, but to another paper. Reporting that as
    resolved would silently attach a reference to the wrong work."""
    wrong = dict(BENEDEK, title="Heegaard Floer invariants of Legendrian knots", family="Ozsvath")
    res = R.resolve_reference(R.parse_references(TEI)[0], StubClient(work={BENEDEK["doi"]: wrong}))
    assert res.state == "unresolved" and res.doi is None
    assert "doi_title_mismatch" in res.reason


def test_an_unregistered_doi_is_unresolved_with_its_reason():
    res = R.resolve_reference(R.parse_references(TEI)[0], StubClient(work={}))
    assert res.state == "unresolved" and "doi_not_registered" in res.reason


def test_a_reference_with_no_doi_resolves_by_title_author_year():
    ref = R.parse_references(TEI)[1]
    hit = {"doi": "10.1000/other", "title": ref["title"], "family": "Other", "year": 1998}
    res = R.resolve_reference(ref, StubClient(search=[hit]))
    assert res.state == "resolved" and res.doi == "10.1000/other" and res.source == "crossref"


def test_two_accepted_works_are_ambiguous_not_resolved():
    """`resolver.resolve_doi` returns the FIRST acceptance and so cannot see the second. Stage 6
    must, or a reference matching two records is silently attached to whichever came back first."""
    ref = R.parse_references(TEI)[1]
    a = {"doi": "10.1000/a", "title": ref["title"], "family": "Other", "year": 1998}
    b = {"doi": "10.1000/b", "title": ref["title"] + " (part II)", "family": "Other", "year": 1999}
    res = R.resolve_reference(ref, StubClient(search=[a, b]))
    assert res.state == "ambiguous" and res.doi is None
    assert {c["doi"] for c in res.candidates} == {"10.1000/a", "10.1000/b"}


def test_nothing_acceptable_is_unresolved_with_the_best_seen():
    ref = R.parse_references(TEI)[1]
    res = R.resolve_reference(ref, StubClient(search=[
        {"doi": "10.1000/x", "title": "An entirely unrelated paper", "family": "Nobody", "year": 1998}]))
    assert res.state == "unresolved" and res.reason.startswith("best=")


# ── the kills (§14 P6) ─────────────────────────────────────────────────────────────────

def test_kill_a_doi_one_digit_off_does_not_resolve_to_the_similar_work():
    """THE §14 P6 KILL. The registry HAS the real paper and would return it on a title search; the
    only thing standing between a corrupted DOI and a confident wrong edge is the no-fallback rule."""
    ref = dict(R.parse_references(TEI)[0])
    ref["doi"] = ref["doi_norm"] = "10.1109/tgrs.2009.1234568"        # last digit +1
    c = StubClient(work={BENEDEK["doi"]: BENEDEK}, search=[BENEDEK])
    res = R.resolve_reference(ref, c)
    assert res.state != "resolved" and res.doi != BENEDEK["doi"]
    assert not searched(c), "the DOI path fell through to a title search and re-found the real work"


def test_kill_a_year_three_years_out_does_not_resolve():
    ref = dict(R.parse_references(TEI)[1], year="2001")               # registry says 1998
    hit = {"doi": "10.1000/other", "title": ref["title"], "family": "Other", "year": 1998}
    assert R.resolve_reference(ref, StubClient(search=[hit])).state == "unresolved"


def test_kill_a_wrong_title_with_the_real_author_and_year_does_not_resolve():
    ref = dict(R.parse_references(TEI)[1],
               title="Rain forest fragmentation and the dynamics of Amazonian tree communities")
    hit = {"doi": "10.1000/other", "title": "A wholly different study of something else",
           "family": "Other", "year": 1998}
    assert R.resolve_reference(ref, StubClient(search=[hit])).state == "unresolved"


def test_kill_a_different_author_with_the_real_title_and_year_does_not_resolve():
    ref = dict(R.parse_references(TEI)[1], first_author="Nobodyatall")
    hit = {"doi": "10.1000/other", "title": ref["title"], "family": "Other", "year": 1998}
    assert R.resolve_reference(ref, StubClient(search=[hit])).state == "unresolved"


def test_a_fabricated_reference_does_not_resolve():
    ref = {"title": "Quantised chlorophyll telemetry of municipal streetlamps under vacuum",
           "first_author": "Quimbly", "year": "2011", "doi": "", "doi_norm": "", "raw": ""}
    assert R.resolve_reference(ref, StubClient(search=[])).state == "unresolved"


# ── cache ──────────────────────────────────────────────────────────────────────────────

class _Flaky:
    def __init__(self, statuses):
        self.statuses, self.n = list(statuses), 0

    def get(self, url, accept=None, timeout=None, **kw):
        st = self.statuses[min(self.n, len(self.statuses) - 1)]
        self.n += 1
        return st, {}, f"body{self.n}".encode()


@pytest.mark.parametrize("status,cached", [(200, True), (404, True), (429, False), (0, False),
                                           (500, False), (503, False)])
def test_only_a_settled_registry_answer_is_cached(tmp_path, status, cached):
    """A cached 429 or a cached 0 turns one transient failure into a permanent phantom miss, and a
    resolution rate measured over such a cache measures the cache."""
    c = R.CachedClient(client=_Flaky([status]), cache=R.DiskCache(root=str(tmp_path)))
    c.get("https://api.crossref.org/works/10.1/x")
    assert c.cached("https://api.crossref.org/works/10.1/x") is cached


def test_a_cache_hit_costs_no_network_call_and_no_pace(tmp_path):
    inner = _Flaky([200])
    cache = R.DiskCache(root=str(tmp_path))
    slept = []
    pacer = R.deferred_pacer(type("P", (), {"wait": lambda s: slept.append(1),
                                            "backoff": lambda s, n=None: None})())
    c = R.CachedClient(client=inner, cache=cache, pacer=pacer)
    for _ in range(3):
        pacer.wait()
        c.get("https://api.crossref.org/works/10.1/y")
    assert c.network_calls == 1 and inner.n == 1
    assert len(slept) == 1, ("three paced reads, one real request: the pacer must sleep for that "
                             "one and for neither cache hit")
    assert cache.hits == 2, "the second and third reads must come from disk"


# ── the graph and the candidates ───────────────────────────────────────────────────────

def test_an_in_corpus_doi_becomes_an_edge_and_anything_else_a_candidate():
    idx = {BENEDEK["doi"]: {"key": "Benedek_2009_change-detection", "title": "", "source": "manifest.csv"}}
    out = R.process_tei(TEI, "citing", StubClient(work={BENEDEK["doi"]: BENEDEK},
                                                 search=[]), index=idx)
    assert out["edges"] == [{"citing_work_key": "citing", "cited_work_key": "Benedek_2009_change-detection",
                             "cited_doi": BENEDEK["doi"], "ref_key": "b0", "mention_count": 2,
                             "in_corpus": True}]
    assert [c["citing_reference"][:5] for c in out["candidates"]]          # b1 became a lead
    assert len(out["candidates"]) == 1


def test_a_citation_candidate_is_never_admitted():
    out = R.process_tei(TEI, "citing", StubClient(), index={}, resolve=False)
    for c in out["candidates"]:
        assert c["state"] == "new" and c["admitted_work_id"] is None and c["source"] == "citation"


def test_the_corpus_index_joins_on_the_normalised_doi(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("stem,title,doi\nX_2000_y,A title,https://doi.org/10.1109/TGRS.2009.1234567/\n",
                 encoding="utf-8")
    assert R.corpus_index([str(p)])[BENEDEK["doi"]]["key"] == "X_2000_y"


def test_a_row_whose_only_key_column_is_a_row_number_is_not_indexed():
    """The bibliography CSV's `id` is a row number. Taking it as the work key put edges into the
    first graph run whose cited work was "14" and "34" (2026-09-15); a row with no stem is no join."""
    import tempfile, pathlib                                             # noqa: E401
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "b.csv").write_text("id,title,doi,filed_stem\n"
                             "14,A title,10.1000/a,\n"
                             "15,Another,10.1000/b,Real_2000_stem\n", encoding="utf-8")
    idx = R.corpus_index([str(d / "b.csv")])
    assert "10.1000/a" not in idx
    assert idx["10.1000/b"]["key"] == "Real_2000_stem"


def test_the_summary_reports_every_state_and_the_rate():
    rows = R.process_tei(TEI, "citing", StubClient(work={BENEDEK["doi"]: BENEDEK}))["references"]
    s = R.resolution_summary(rows)
    assert s["references"] == 2 and s["resolved"] + s["ambiguous"] + s["unresolved"] == 2
    assert 0.0 <= s["resolved_rate"] <= 1.0 and s["reasons"]


# ── mutation sensitivity: the harness drives these ─────────────────────────────────────

def test_the_title_ratio_rule_is_the_projects_one_rule():
    """Pins `RESOLVE_TITLE_RATIO`: lowering it admits a title that should have been refused."""
    ref = dict(R.parse_references(TEI)[1],
               title="A wholly different study of something else again, in detail")
    hit = {"doi": "10.1000/other", "title": "A wholly different study of something else",
           "family": "Other", "year": 1998}
    ratio = R.title_match_ratio(ref["title"], hit["title"])
    assert 0.80 < ratio < R.RESOLVE_TITLE_RATIO, ratio     # close enough that a lowered bar admits it
    assert R.resolve_reference(ref, StubClient(search=[hit])).state == "unresolved"


def test_the_year_rule_admits_plus_or_minus_one_and_refuses_two():
    ref = R.parse_references(TEI)[1]
    for delta, want in ((0, "resolved"), (1, "resolved"), (-1, "resolved"),
                        (2, "unresolved"), (-2, "unresolved")):
        hit = {"doi": "10.1000/other", "title": ref["title"], "family": "Other",
               "year": 1998 + delta}
        assert R.resolve_reference(ref, StubClient(search=[hit])).state == want, delta


def test_a_hand_built_reference_with_only_a_raw_doi_still_takes_the_doi_path():
    """Pins `normalize_doi` at the DOI-path decision: a caller (the near-miss harness, P5's ingest)
    may hand in a reference with `doi` and no precomputed `doi_norm`. Without the normalisation
    there, a `https://doi.org/...` form is falsy-in-effect and the reference silently falls through
    to a title search — the exact fallback the §14 P6 kill forbids."""
    c = StubClient(work={BENEDEK["doi"]: BENEDEK}, search=[BENEDEK])
    ref = {"title": BENEDEK["title"], "first_author": "Benedek", "year": "2009",
           "doi": " https://doi.org/10.1109/TGRS.2009.1234567/ ", "raw": ""}
    res = R.resolve_reference(ref, c)
    assert res.state == "resolved" and res.doi == BENEDEK["doi"]
    assert not searched(c)


def test_a_doi_field_that_holds_no_doi_does_not_hijack_the_doi_path():
    """Pins `normalize_doi` at the decision itself. GROBID's `<idno type="DOI">` is whatever the
    printed line held — "in press", a bare "doi:", a URL fragment. Deciding the path on the RAW
    string's truthiness would send such a reference down the DOI path, where it can only fail,
    instead of resolving it by title; normalising first is what makes "no 10." mean "no DOI"."""
    ref = dict(R.parse_references(TEI)[1], doi="doi: (in press)", doi_norm="")
    hit = {"doi": "10.1000/other", "title": ref["title"], "family": "Other", "year": 1998}
    c = StubClient(search=[hit])
    res = R.resolve_reference(ref, c)
    assert res.state == "resolved" and res.doi == "10.1000/other" and searched(c)


def test_two_candidates_that_are_the_same_doi_in_different_case_are_one_work():
    """Pins `normalize_doi` inside the search path: DOIs are case-insensitive for ASCII, so the
    same work returned twice must not be reported as an ambiguity."""
    ref = R.parse_references(TEI)[1]
    a = {"doi": "10.1000/Other", "title": ref["title"], "family": "Other", "year": 1998}
    b = {"doi": "10.1000/other", "title": ref["title"], "family": "Other", "year": 1998}
    res = R.resolve_reference(ref, StubClient(search=[a, b]))
    assert res.state == "resolved" and res.doi == "10.1000/other"


def test_a_crossref_deposited_reference_list_comes_back_normalised():
    """Pins `normalize_doi` in the gate's comparator: the deposited list is compared with our own
    resolved DOIs, and an unnormalised one would never join."""
    class _Dep:
        def get(self, url, accept=None, timeout=None, **kw):
            return 200, {}, json.dumps({"message": {"reference-count": 2, "reference": [
                {"DOI": "10.1109/TGRS.2009.1234567", "key": "r1"},
                {"unstructured": "no doi here", "key": "r2"}]}}).encode()
    n, refs, st = R.crossref_reference_list(_Dep(), "10.1/x")
    assert (n, st) == (2, 200)
    assert [r["doi"] for r in refs] == [BENEDEK["doi"], ""]


# ── the rate-limit breaker ─────────────────────────────────────────────────────────────

def test_a_rate_limited_stage_trips_and_is_then_skipped():
    b = R.StageBreaker(trip_after=2)
    b.record("semanticscholar", "semanticscholar status 429")
    assert not b.is_open("semanticscholar")
    b.record("semanticscholar", "semanticscholar status 429")
    assert b.is_open("semanticscholar") and "semanticscholar" in b.report()
    assert not b.is_open("crossref")


def test_one_good_answer_resets_the_streak():
    """A single 429 between healthy answers is a blip, not an outage; tripping on it would drop a
    working stage for the rest of a run and silently lower the resolution rate."""
    b = R.StageBreaker(trip_after=2)
    b.record("crossref", "crossref status 429")
    b.record("crossref", "")
    b.record("crossref", "crossref status 429")
    assert not b.is_open("crossref")


def test_a_tripped_stage_is_named_in_the_unresolved_reason():
    ref = R.parse_references(TEI)[1]
    b = R.StageBreaker(trip_after=1)
    b.record("semanticscholar", "semanticscholar status 429")
    b.record("arxiv", "arxiv status 429")
    res = R.resolve_reference(ref, StubClient(search=[]), None, b)
    assert res.state == "unresolved" and "skipped=semanticscholar,arxiv" in res.reason


def test_a_doi_with_no_parsed_title_still_needs_its_author_and_year():
    ref = dict(R.parse_references(TEI)[0], title="")
    ok = R.resolve_reference(ref, StubClient(work={BENEDEK["doi"]: BENEDEK}))
    assert ok.state == "resolved"
    bad = dict(ref, first_author="Nobodyatall")
    assert R.resolve_reference(bad, StubClient(work={BENEDEK["doi"]: BENEDEK})).state == "unresolved"


# ── the no-parsed-title branch of the DOI path (P6 referee §4) ──────────────────────────

#: Steenberg 2017 `b5`, the live row that exposed this branch: the DOI printed in the paper is
#: registered to a DIFFERENT Boone 2010, and the parsed title (ratio 0.245) is the only thing that
#: refuses it. With the title stripped, first author and year are all that is left — and they agree.
BOONE_REGISTERED = {"doi": "10.1080/19463138.2010.513772", "family": "Boone", "year": 2010,
                    "title": "Environmental justice, sustainability and vulnerability"}


def _boone_ref(**kw):
    ref = dict(R.parse_references(TEI)[0], first_author="Boone", year="2010", title="",
               doi=BOONE_REGISTERED["doi"], doi_norm=R.normalize_doi(BOONE_REGISTERED["doi"]))
    ref.update(kw)
    return ref


def _boone_client():
    return StubClient(work={R.normalize_doi(BOONE_REGISTERED["doi"]): BOONE_REGISTERED})


def test_steenberg_b5_with_no_parsed_title_is_accepted_on_author_and_year():
    """NOT a happy path — the documented hole, pinned so it cannot move silently. The registered
    work is a different Boone 2010, and with no parsed title the branch has nothing that separates
    them, so it resolves. The design says so in those words (§7 stage 6); the title ratio is what
    refuses this row in the live corpus."""
    res = R.resolve_reference(_boone_ref(), _boone_client())
    assert res.state == "resolved" and res.source == "doi"
    assert "basis=author+year (no parsed title)" in res.reason


def test_a_planted_wrong_doi_with_no_parsed_title_is_doi_unverifiable():
    """The same shape with the author and year the reference actually prints: a DOI that resolves
    to somebody else's work is refused, not accepted on the DOI alone."""
    res = R.resolve_reference(_boone_ref(first_author="Heynen", year="2003"), _boone_client())
    assert res.state == "unresolved" and res.doi is None
    assert "doi_unverifiable" in res.reason


def test_with_no_parsed_title_the_year_must_be_exact_not_plus_or_minus_one():
    """decisions.yaml litkb-p0-foundation §15.15: the +/-1 arm is allowed only when the title AND
    the first author both match. With no parsed title the title arm cannot match, so a year one out
    is not a near-miss to forgive — it is the last discriminator there is."""
    res = R.resolve_reference(_boone_ref(year="2011"), _boone_client())
    assert res.state == "unresolved" and "doi_unverifiable" in res.reason


def test_with_no_parsed_title_and_no_author_the_doi_is_unverifiable():
    res = R.resolve_reference(_boone_ref(first_author="", authors=[]), _boone_client())
    assert res.state == "unresolved" and "doi_unverifiable" in res.reason


# ── the contained-title label (P6 referee §4) ───────────────────────────────────────────

def test_a_truncated_parsed_title_is_labelled_contained_and_still_unresolved():
    """GROBID truncates a title at a comma; the registry title then CONTAINS the parsed one. That is
    a parse artefact, not a wrong DOI — but the row stays unresolved, because accepting on
    containment would let a stub match anything that contains it. Only the label changes."""
    longer = dict(BENEDEK, title=BENEDEK["title"] + " over the Budapest site")
    res = R.resolve_reference(R.parse_references(TEI)[0], StubClient(work={BENEDEK["doi"]: longer}))
    assert res.state == "unresolved" and res.doi is None
    assert "doi_title_contained" in res.reason


def test_a_genuinely_wrong_doi_is_still_doi_title_mismatch_not_contained():
    wrong = dict(BENEDEK, title="Heegaard Floer invariants of Legendrian knots", family="Ozsvath")
    res = R.resolve_reference(R.parse_references(TEI)[0], StubClient(work={BENEDEK["doi"]: wrong}))
    assert "doi_title_mismatch" in res.reason and "contained" not in res.reason


def test_a_short_generic_parsed_title_is_not_called_contained():
    """"Introduction" sits inside a hundred registry titles. The word floor and the length fraction
    are what stop containment becoming an acceptance rule by the back door."""
    assert R.title_containment("Introduction", BENEDEK["title"]) is None
    assert R.title_containment("Change detection in", BENEDEK["title"]) is None
    res = R.resolve_reference(dict(R.parse_references(TEI)[0], title="Introduction"),
                              StubClient(work={BENEDEK["doi"]: BENEDEK}))
    assert "doi_title_mismatch" in res.reason


def test_containment_sees_through_a_curly_apostrophe():
    """The shared `_norm_text` strips `string.punctuation`, which does NOT contain U+2019, so
    "Residents\u2019" and "Residents'" differ under it. Measured on Guo 2018 `b5`: without the
    quote fold a real parse artefact reads as a wrong DOI."""
    reg = "Tending their urban forest: Residents\u2019 motivations for tree planting and removal"
    parsed = ("Tending their urban forest: Residents' motivations for tree planting and removal. "
              "Urban Forestry and Urban Greening")
    assert R.title_containment(parsed, reg) is not None

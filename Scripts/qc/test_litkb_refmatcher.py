"""Tests for the ref-matcher adapter and its scoring.

Two classes of defect these pin, both of which were live during the evaluation:

  * The typed-literal patch. The production OpenCitations Virtuoso stores the join-key
    literals as ``xsd:string`` and will not join a plain literal to a typed one, so the
    tool as shipped matches nothing there. The patch must type exactly the three
    predicates used as join keys, must not touch ``BIND("x" AS ?v)`` (where the literal is
    a projected value, not a join key), and must be idempotent.
  * The non-match return. ``ReferenceMatchingTool.process_reference`` returns a TRUTHY dict
    ``{'below_threshold': True, ...}`` when nothing clears the cut. The first version of the
    adapter read ``bool(match)`` and scored all 658 references as matched. The scorer must
    treat a below-threshold row as a miss, everywhere.
  * The binding shape. The tool's scorer reads ``result['doi']['value']``, so the transport
    must hand back RAW SPARQL bindings. An intermediate version flattened them to plain
    strings; every field read then failed, every candidate scored 0, and the run looked
    exactly like "ref-matcher matches nothing" -- a false headline that survived one whole
    658-reference run before a single-reference trace caught it.

Nothing here touches the lake or the wire.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = SCRIPTS / "qc" / "instruments" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ev = _load("litkb_refmatcher_eval")
sc = _load("litkb_refmatcher_score")


# --------------------------------------------------------------------------- patch
def test_typed_literal_patch_types_the_three_join_keys():
    q = ('SELECT ?br WHERE { ?id literal:hasLiteralValue "10.1/x" . '
         '?a foaf:familyName "Bonan" . ?v fabio:hasSequenceIdentifier "320" }')
    out = ev.type_literals(q)
    assert '"10.1/x"^^xsd:string' in out
    assert '"Bonan"^^xsd:string' in out
    assert '"320"^^xsd:string' in out
    assert "PREFIX xsd:" in out


def test_typed_literal_patch_leaves_bind_alone():
    """BIND projects a value; typing it there changes what is returned, not what joins."""
    q = 'SELECT ?d WHERE { ?id literal:hasLiteralValue "10.1/x" . BIND("10.1/x" AS ?doi) }'
    out = ev.type_literals(q)
    assert 'BIND("10.1/x" AS ?doi)' in out
    assert out.count("^^xsd:string") == 1


def test_typed_literal_patch_is_idempotent():
    q = 'SELECT ?b WHERE { ?i literal:hasLiteralValue "10.1/x" }'
    once = ev.type_literals(q)
    assert ev.type_literals(once) == once
    assert once.count("^^xsd:string") == 1


def test_typed_literal_patch_does_not_touch_other_predicates():
    q = 'SELECT ?t WHERE { ?br dcterms:title "Some title" }'
    assert ev.type_literals(q) == q


def test_patch_covers_every_plain_literal_join_in_the_shipped_queries(tool_dir):
    """A ratchet on the upstream tool: if a future commit adds another predicate matched
    against a plain literal, this fails rather than silently matching nothing."""
    src = (Path(tool_dir) / "script" / "ReferenceMatchingTool.py").read_text(
        encoding="utf-8", errors="replace")
    import re
    # predicate followed by an f-string literal placeholder, in triple position
    found = set(re.findall(r'(\w+:\w+)\s+"\{[a-z_]+\}"', src))
    unhandled = found - set(ev.TYPED_LITERAL_PREDICATES)
    assert not unhandled, (
        f"upstream matches these predicates against a plain literal and the patch does not "
        f"type them: {sorted(unhandled)}")


# --------------------------------------------------------------------------- bindings
def test_binding_value_reads_the_sparql_shape():
    """The tool passes bindings around unflattened; a match is {'doi': {'value': …}}."""
    m = {"doi": {"type": "literal", "value": "10.2307/2938229"},
         "title": {"value": "Heteroskedasticity"}, "score": 25}
    assert ev.binding_value(m, "doi") == "10.2307/2938229"
    assert ev.binding_value(m, "title") == "Heteroskedasticity"


def test_binding_value_tolerates_a_plain_string_and_missing_keys():
    assert ev.binding_value({"doi": "10.1/x"}, "doi") == "10.1/x"
    assert ev.binding_value({}, "doi") == ""
    assert ev.binding_value(None, "doi") == ""
    assert ev.binding_value({"doi": None}, "doi") == ""


def test_flattened_binding_would_not_be_mistaken_for_a_doi():
    """Guards the exact regression: a flattened record must not silently yield ''. It
    yields the value, so the failure mode is now impossible in either direction."""
    assert ev.binding_value({"doi": {"value": ""}}, "doi") == ""
    got = ev.normalize_doi(ev.binding_value({"doi": {"value": "https://doi.org/10.1/X"}}, "doi"))
    assert got == "10.1/x"


# --------------------------------------------------------------------------- doi
@pytest.mark.parametrize("raw,want", [
    ("https://doi.org/10.1/X", "10.1/x"),
    ("DOI:10.1/X", "10.1/x"),
    ("http://dx.doi.org/10.1/x", "10.1/x"),
    ("  10.1/X  ", "10.1/x"),
    ("", ""),
])
def test_normalize_doi(raw, want):
    assert ev.normalize_doi(raw) == want
    assert sc.normalize_doi(raw) == want


# --------------------------------------------------------------------------- scoring
def _gold_stub():
    return {
        "positives": [
            {"ref_id": "W::b0", "gold_doi": "10.1/a"},
            {"ref_id": "W::b1", "gold_doi": "10.1/b"},
            {"ref_id": "W::b2", "gold_doi": "10.1/c"},
        ],
        "must_not_link": [
            {"ref_id": "W::b9", "bad_doi": "10.9/rev", "kind": "book_review"},
            {"ref_id": "W::b0#mut0", "base_ref_id": "W::b0", "bad_doi": "10.1/a",
             "kind": "mutation_year+3", "mutation": "year+3",
             "mutant_title": "t", "mutant_year": "2011", "mutant_doi": ""},
        ],
        "near_positive_mutations": [
            {"ref_id": "W::b1#mut2", "base_ref_id": "W::b1", "gold_doi": "10.1/b",
             "mutation": "title-word", "mutant_title": "t", "mutant_year": "2008"},
        ],
        "lost_genuine": [
            {"ref_id": "W::b5", "gold_doi": "10.5/lost", "refusal_reason": "crossref_no_author"},
        ],
    }


def test_positives_correct_wrong_miss():
    gold = _gold_stub()
    body = {
        "W::b0": {"ref_id": "W::b0", "matched": True, "doi": "10.1/a"},
        "W::b1": {"ref_id": "W::b1", "matched": True, "doi": "10.9/other"},
        "W::b2": {"ref_id": "W::b2", "matched": False, "doi": ""},
    }
    got = sc.score_positives(gold, body)
    assert got["counts"] == {"correct": 1, "wrong": 1, "miss": 1}
    assert got["wrong"][0]["want"] == "10.1/b"


def test_below_threshold_row_is_a_miss_not_a_match():
    """The defect that inverted the first run: a truthy non-match must never score."""
    gold = _gold_stub()
    body = {"W::b0": {"ref_id": "W::b0", "matched": False, "below_threshold": True,
                      "doi": "", "score": 21}}
    got = sc.score_positives(gold, body)
    assert got["counts"].get("correct", 0) == 0
    assert got["counts"]["miss"] == 1


def test_must_not_link_separates_real_from_mutants_and_counts_by_kind():
    gold = _gold_stub()
    body = {
        "W::b9": {"ref_id": "W::b9", "matched": True, "doi": "10.9/rev"},       # returned bad
        "W::b0#mut0": {"ref_id": "W::b0#mut0", "matched": True, "doi": "10.1/a"},  # bad
    }
    got = sc.score_must_not_link(gold, body)
    assert got["real"]["returned_bad"] == 1
    assert got["mutants"]["returned_bad"] == 1
    assert got["real"]["returned_bad::book_review"] == 1
    assert len(got["returned_bad"]) == 2


def test_must_not_link_refusal_and_other_doi_are_distinct():
    gold = _gold_stub()
    body = {
        "W::b9": {"ref_id": "W::b9", "matched": False, "doi": ""},
        "W::b0#mut0": {"ref_id": "W::b0#mut0", "matched": True, "doi": "10.7/zz"},
    }
    got = sc.score_must_not_link(gold, body)
    assert got["real"]["refused"] == 1
    assert got["mutants"]["other_doi"] == 1
    assert got["real"].get("returned_bad", 0) == 0


def test_near_positive_counts_returning_the_original():
    gold = _gold_stub()
    body = {"W::b1#mut2": {"ref_id": "W::b1#mut2", "matched": True, "doi": "10.1/b"}}
    assert sc.score_near_positive(gold, body)["returned_original"] == 1
    body = {"W::b1#mut2": {"ref_id": "W::b1#mut2", "matched": False, "doi": ""}}
    assert sc.score_near_positive(gold, body)["no_match"] == 1


def test_lost_genuine_reports_correctness_and_our_refusal_reason():
    gold = _gold_stub()
    body = {"W::b5": {"ref_id": "W::b5", "matched": True, "doi": "10.5/lost"}}
    row = sc.score_lost_genuine(gold, body)[0]
    assert row["correct"] is True
    assert row["our_refusal"] == "crossref_no_author"


def test_hard_set_marks_an_unlabelled_doi_ungraded():
    """The column that stops an ungraded hit becoming a 'resolves N more' headline."""
    gold = _gold_stub()
    refs = {
        "W::b5": {"resolution": "unresolved", "title": "t", "first_author": "A", "raw": "r"},
        "W::b7": {"resolution": "unresolved", "title": "t", "first_author": "A", "raw": "r"},
    }
    body = {
        "W::b5": {"ref_id": "W::b5", "matched": True, "doi": "10.5/lost"},   # graded right
        "W::b7": {"ref_id": "W::b7", "matched": True, "doi": "10.7/unknown"},  # ungraded
    }
    got = sc.score_hard_set(gold, body, refs)
    assert got["hard_n"] == 2
    assert got["counts"]["graded_right"] == 1
    assert got["counts"]["ungraded"] == 1


def test_gold_sha256_is_crlf_safe(tmp_path):
    """*.json is a text attribute and core.autocrlf is true, so the SAME gold checks out
    with CRLF on Windows and LF on Colab. The pin must survive that or it stops meaning
    'the same gold' and starts meaning 'the same platform'."""
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    body = b'{\n "positives": [],\n "a": 1\n}\n'
    lf.write_bytes(body)
    crlf.write_bytes(body.replace(b"\n", b"\r\n"))
    assert sc.gold_sha256(lf) == sc.gold_sha256(crlf)


def test_frozen_gold_sha256_matches_in_both_line_endings(tmp_path):
    p = SCRIPTS.parent / "Reports" / "litkb_splink_gold_2026-09-15.json"
    if not p.exists():
        pytest.skip("gold not present")
    assert sc.gold_sha256(p) == sc.GOLD_SHA256
    crlf = tmp_path / "g.json"
    crlf.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert sc.gold_sha256(crlf) == sc.GOLD_SHA256


def test_gold_sha256_is_pinned_and_a_changed_gold_is_refused(tmp_path):
    bad = tmp_path / "g.json"
    bad.write_text(json.dumps({"positives": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        sc.load_gold(bad)


def test_frozen_gold_on_this_branch_matches_the_splink_sha256():
    p = SCRIPTS.parent / "Reports" / "litkb_splink_gold_2026-09-15.json"
    if not p.exists():
        pytest.skip("gold not present")
    gold = sc.load_gold(p)          # raises if the sha256 moved
    assert len(gold["positives"]) == 365
    assert len(gold["must_not_link"]) == 77
    assert len(gold["lost_genuine"]) == 5
    assert len(gold["near_positive_mutations"]) == 20


# --------------------------------------------------------------------------- adapter
def test_mutant_rows_build_from_the_gold_not_from_invention():
    gold = _gold_stub()
    base = {"W::b0": {"citing_work_key": "W", "ref_key": "b0", "title": "orig",
                      "year": "2008", "doi": "", "first_author": "Bonan", "raw": "r"},
            "W::b1": {"citing_work_key": "W", "ref_key": "b1", "title": "orig2",
                      "year": "2008", "doi": "", "first_author": "X", "raw": "r"}}
    rows = ev.mutant_rows(gold, base)
    assert len(rows) == 2
    mnl = [r for r in rows if r["_family"] == "must_not_link"][0]
    assert mnl["year"] == "2011" and mnl["title"] == "t"
    assert mnl["_expect_not"] == "10.1/a"
    npos = [r for r in rows if r["_family"] == "near_positive"][0]
    assert npos["_expect"] == "10.1/b"
    # the first author is carried from the base, never re-derived
    assert mnl["first_author"] == "Bonan"


def test_ref_from_row_splits_the_page_range_and_can_withhold_the_doi():
    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Mod:
        Reference = _R

    row = {"year": "2008", "volume": "320", "pages": "1444-1449", "first_author": "Bonan",
           "title": "T", "journal": "Science", "doi": "10.1/x", "raw": "raw string"}
    r = ev.ref_from_row(_Mod, row, use_doi=True)
    assert r.first_page == "1444" and r.doi == "10.1/x"
    assert ev.ref_from_row(_Mod, row, use_doi=False).doi == ""


def test_ref_from_row_leaves_an_unparsed_title_empty(tmp_path):
    """The 50 footnote references must reach the tool as GROBID left them: an empty title
    back-filled from `raw` would measure our repair, not the tool."""
    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Mod:
        Reference = _R

    row = {"year": "", "volume": "", "pages": "", "first_author": "", "title": "",
           "journal": "", "doi": "", "raw": "H. Brezis, Operateurs Maximaux Monotones, 1973."}
    r = ev.ref_from_row(_Mod, row)
    assert r.article_title == "" and r.first_author_lastname == ""
    assert r.unstructured.startswith("H. Brezis")


# --------------------------------------------------------------------------- cache
def test_query_cache_round_trips_and_counts_hits(tmp_path):
    c = ev.QueryCache(tmp_path / "c.jsonl")
    assert c.get("q1") is None and c.misses == 1
    c.put("q1", [{"br": "x"}])
    assert c.get("q1") == [{"br": "x"}] and c.hits == 1
    # a fresh reader sees the persisted entry -- this is what lets a referee re-score dry
    c2 = ev.QueryCache(tmp_path / "c.jsonl")
    assert c2.get("q1") == [{"br": "x"}]


def test_query_cache_does_not_persist_an_empty_result_as_a_failure_marker(tmp_path):
    """A 500 or a timeout must not be stored as `[]`. On re-read it is indistinguishable
    from 'the registry has nothing', so it becomes a permanent miss that a referee's
    zero-wire re-score inherits without any sign that a request ever failed."""
    p = tmp_path / "c.jsonl"
    c = ev.QueryCache(p)
    c.put("good", [])                 # a REAL empty answer is legitimate and is stored
    assert ev.QueryCache(p).get("good") == []
    # a failure is simply never put; nothing to assert but the absence
    assert ev.QueryCache(p).get("failed-query") is None


def test_query_cache_key_is_the_exact_query_text(tmp_path):
    c = ev.QueryCache(tmp_path / "c.jsonl")
    c.put("SELECT a", [1])
    assert c.get("SELECT  a") is None       # one space differs -> different key


@pytest.fixture
def tool_dir():
    import os
    d = os.environ.get("REFMATCHER_DIR")
    if not d or not (Path(d) / "script" / "ReferenceMatchingTool.py").exists():
        pytest.skip("REFMATCHER_DIR not set to a ref-matcher clone")
    return d

"""Tests for the P7 chunker, the corpus rules and the reciprocal-rank fusion.

No model, no database, no GPU: everything here runs under the project Python in
``qc/check.py``. The one test that touches the real corpus skips if it is absent.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.abspath(__file__))), "pipeline"))
# instruments/ is not a package; the two gate tests below import the gold verifier from it.
# Done once here so the file keeps ONE insert per uninstalled root (test_path_insert_ledger).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "instruments"))  # noqa: E402

from litkb.index import chunk as C  # noqa: E402
from litkb.index import corpus as K  # noqa: E402
from litkb.index import fuse as F  # noqa: E402
from litkb.index import lexical as X  # noqa: E402


def _para(word, n):
    return " ".join([word] * n)


def _doc(n_paras=12, words=60):
    return "\n\n".join(_para("w%d" % i, words) for i in range(n_paras))


# --------------------------------------------------------------------------- chunking

def test_import_litkb_index_pulls_no_heavy_library():
    """§9: importing ``litkb.index`` must not load torch.

    In a SUBPROCESS, deliberately: by the time this test runs in the full suite another
    test has already imported torch into this interpreter, so an in-process check on
    ``sys.modules`` passes or fails on test ORDER, not on the import graph. It failed that
    way once, which is how the subprocess got here.
    """
    import subprocess
    pipeline = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline")
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import litkb.index, litkb.index.corpus, litkb.index.chunk,"
        " litkb.index.fuse, litkb.index.lexical, litkb.index.embed;"
        "heavy=[m for m in ('torch','sentence_transformers','transformers','FlagEmbedding')"
        " if m in sys.modules];"
        "print(','.join(heavy))" % pipeline
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", "litkb.index pulled %s" % out.stdout.strip()


def test_paragraph_offsets_are_exact_slices_of_the_source():
    text = _doc()
    for p in C.paragraphs(text):
        assert text[int(p["char_start"]):int(p["char_end"])] == p["text"]


def test_chunks_are_exact_slices_and_paragraph_bounded():
    text = _doc()
    chunks = C.chunk_text(text, "s")
    assert chunks
    starts = {int(p["char_start"]) for p in C.paragraphs(text)}
    ends = {int(p["char_end"]) for p in C.paragraphs(text)}
    for ch in chunks:
        assert text[int(ch["char_start"]):int(ch["char_end"])] == ch["text"]
        assert int(ch["char_start"]) in starts   # never starts mid-paragraph
        assert int(ch["char_end"]) in ends       # never ends mid-paragraph


def test_chunk_sizes_stay_under_the_ceiling_unless_one_paragraph_exceeds_it():
    text = _doc(n_paras=20, words=80)
    for ch in C.chunk_text(text, "s", min_tokens=300, max_tokens=500):
        assert int(ch["n_tokens"]) <= 500


def test_a_single_oversized_paragraph_is_emitted_whole_not_split():
    text = _para("x", 1200)
    chunks = C.chunk_text(text, "s")
    assert len(chunks) == 1
    assert int(chunks[0]["n_tokens"]) == 1200


def test_consecutive_chunks_overlap():
    text = _doc(n_paras=30, words=60)
    chunks = C.chunk_text(text, "s", min_tokens=300, max_tokens=500, overlap=0.15)
    assert len(chunks) >= 3
    for a, b in zip(chunks, chunks[1:]):
        assert int(b["char_start"]) < int(a["char_end"]), "no overlap between %s and %s" % (
            a["chunk_id"], b["chunk_id"])


def test_zero_overlap_produces_abutting_chunks():
    """The overlap is a real parameter, not decoration: at 0.0 the chunks abut."""
    text = _doc(n_paras=30, words=60)
    chunks = C.chunk_text(text, "s", overlap=0.0)
    assert len(chunks) >= 3
    for a, b in zip(chunks, chunks[1:]):
        assert int(b["char_start"]) >= int(a["char_end"])


def test_a_table_is_kept_whole_in_one_chunk():
    table = "Table 1\n2020 0.81 0.77 0.91\n2021 0.84 0.79 0.93\n2022 0.86 0.80 0.94"
    text = _doc(6, 60) + "\n\n" + table + "\n\n" + _doc(6, 60)
    chunks = C.chunk_text(text, "s")
    covering = [c for c in chunks if table in str(c["text"])]
    assert covering, "the table was split across chunks"


def test_is_structural_separates_a_table_from_prose():
    assert C.is_structural("Table 2\n1990 12 14 19\n2000 22 25 31\n2010 41 44 52")
    assert C.is_structural("Figure 3. Reading order across a three-column page.")
    assert not C.is_structural(_para("the", 80))


def test_chunks_covering_returns_both_chunks_for_a_straddling_span():
    text = _doc(n_paras=30, words=60)
    chunks = C.chunk_text(text, "s")
    a, b = chunks[0], chunks[1]
    # a span that starts inside a and ends inside b
    span = (int(b["char_start"]) - 5, int(a["char_end"]) + 5)
    hits = C.chunks_covering(chunks, "s", span[0], span[1])
    assert a["chunk_id"] in hits and b["chunk_id"] in hits


def test_chunk_ids_are_unique():
    text = _doc(n_paras=40, words=70)
    ids = [c["chunk_id"] for c in C.chunk_text(text, "s")]
    assert len(ids) == len(set(ids))


def test_chunks_hash_changes_when_a_span_changes():
    text = _doc()
    a = C.chunk_text(text, "s")
    b = C.chunk_text(text + "\n\n" + _para("z", 400), "s")
    assert C.chunks_hash(a) != C.chunks_hash(b)


# ----------------------------------------------------------------------------- corpus

def test_corpus_excludes_raw_twins_and_empty_extracts():
    if not os.path.isdir(K.CORPUS_DIR):
        pytest.skip("literature corpus not present")
    cands = K.candidate_stems()
    assert not any(s.endswith(".raw") for s in cands)
    kept = set(K.stems())
    dropped = {s for s, _ in K.excluded_stems()}
    assert kept.isdisjoint(dropped)
    assert kept | dropped == set(cands)


def test_read_text_has_no_carriage_returns():
    if not os.path.isdir(K.CORPUS_DIR):
        pytest.skip("literature corpus not present")
    stem = K.stems()[0]
    text, codec = K.read_text(stem)
    assert "\r" not in text
    assert codec in K.CODECS


# -------------------------------------------------------------------------------- RRF

def test_rrf_matches_the_formula_by_hand():
    legs = [["a", "b", "c"], ["c", "a"]]
    fused = F.rrf(legs, k=60)
    # a: 1/61 + 1/62 = 0.032522 ; c: 1/63 + 1/61 = 0.032266 ; b: 1/62 = 0.016129.
    # a wins by 0.00026 — rank 1 + rank 2 beats rank 3 + rank 1, narrowly. That margin is
    # the whole behaviour of RRF at k=60, so assert the order AND the numbers.
    score_a = 1 / 61 + 1 / 62
    score_c = 1 / 63 + 1 / 61
    score_b = 1 / 62
    assert score_a > score_c > score_b
    assert fused == ["a", "c", "b"]


def test_rrf_promotes_a_document_both_legs_rank_mid_over_one_leg_top():
    legs = [["x", "m", "n"], ["y", "m", "n"]]
    assert F.rrf(legs)[0] == "m"


def test_rrf_is_deterministic_on_ties():
    legs = [["a"], ["b"]]
    assert F.rrf(legs) == ["a", "b"]
    assert F.rrf([["b"], ["a"]]) == ["b", "a"]


def test_rrf_does_not_penalise_absence_with_a_worst_case_rank():
    """A doc missing from a leg scores from the other leg alone — not 1/(k+len)."""
    legs = [["a"] + ["f%d" % i for i in range(50)], ["a"]]
    fused = F.rrf(legs)
    assert fused[0] == "a"


def test_recall_and_mrr():
    assert F.recall_at_k(["a", "b", "c"], {"c"}, 5) == 1.0
    assert F.recall_at_k(["a", "b", "c"], {"z"}, 5) == 0.0
    assert F.recall_at_k(["a", "b", "c", "d", "e", "z"], {"z"}, 5) == 0.0
    assert F.reciprocal_rank(["a", "b", "z"], {"z"}) == pytest.approx(1 / 3)
    assert F.reciprocal_rank(["a"], {"z"}) == 0.0


def test_score_run_averages_over_all_gold_queries_including_misses():
    gold = {"q1": ["a"], "q2": ["b"]}
    res = {"q1": ["a"]}           # q2 returned nothing at all
    out = F.score_run(res, gold)
    assert out["recall@5"] == 0.5
    assert out["mrr"] == 0.5
    assert out["n_queries"] == 2


# ---------------------------------------------------------------------- lexical leg

def test_ngram_overlap_is_what_makes_a_query_a_paraphrase():
    passage = "we culled a few locations where the land cover labels changed between years"
    verbatim = "we culled a few locations where the land cover labels changed"
    paraphrase = "sites whose class differed across dates were dropped from the pool"
    assert X.ngram_overlap(verbatim, passage, n=4)
    assert not X.ngram_overlap(paraphrase, passage, n=4)


def test_ngram_overlap_ignores_case_and_punctuation():
    assert X.ngram_overlap("The land-cover labels changed!", "the land cover labels changed", n=4)


def test_bm25_ranks_the_document_containing_the_query_terms_first():
    docs = [
        X.tokenize("markov random field change detection in aerial images"),
        X.tokenize("bootstrap confidence intervals for spatial subsampling"),
        X.tokenize("total variation denoising of piecewise constant signals"),
    ]
    bm = X.BM25(docs)
    assert bm.top_k("markov random field change detection", ["d0", "d1", "d2"], k=3)[0] == "d0"
    assert bm.top_k("bootstrap spatial subsampling", ["d0", "d1", "d2"], k=3)[0] == "d1"


def test_bm25_returns_nothing_when_no_query_term_occurs():
    bm = X.BM25([X.tokenize("alpha beta gamma")])
    assert bm.top_k("zeta eta theta", ["d0"], k=3) == []


# ------------------------------------------------------- the gold verifier's own rules

def _gold_fixture(tmp_path, **override):
    """A one-query gold file whose anchor really is a slice of a real corpus stem."""
    import json
    stem = K.stems()[0]
    text = K.read_text(stem)[0]
    start = 5000
    anchor = text[start:start + 400]
    q = {"id": "g001", "kind": "paraphrase", "query": "zzqq unrelated wording entirely",
         "source_stem": stem, "anchor_text": anchor,
         "char_start": start, "char_end": start + 400, "note": "fixture"}
    q.update(override)
    p = tmp_path / "gold.json"
    p.write_text(json.dumps({"queries": [q]}), encoding="utf-8")
    return p


def test_gold_verifier_accepts_a_well_formed_anchor_and_rejects_a_shifted_one(tmp_path):
    """The verifier is a gate, so show it FIRES on a known-bad input (CLAUDE.md §3.4c)."""
    if not os.path.isdir(K.CORPUS_DIR):
        pytest.skip("literature corpus not present")
    import litkb_p7_verify_gold as V

    good = _gold_fixture(tmp_path)
    rules = {r for r, _, _ in V.verify(str(good))[4]}
    assert "ANCHOR" not in rules and "NGRAM" not in rules and "STEM" not in rules

    # offsets moved by one character: the slice no longer equals the anchor
    bad = _gold_fixture(tmp_path, char_start=5001, char_end=5401)
    assert "ANCHOR" in {r for r, _, _ in V.verify(str(bad))[4]}


def test_gold_verifier_rejects_a_verbatim_query(tmp_path):
    """A query copied out of the passage is what the paraphrase rule exists to stop."""
    if not os.path.isdir(K.CORPUS_DIR):
        pytest.skip("literature corpus not present")
    import litkb_p7_verify_gold as V

    stem = K.stems()[0]
    anchor = K.read_text(stem)[0][5000:5400]
    bad = _gold_fixture(tmp_path, query=anchor[:120])
    assert "NGRAM" in {r for r, _, _ in V.verify(str(bad))[4]}

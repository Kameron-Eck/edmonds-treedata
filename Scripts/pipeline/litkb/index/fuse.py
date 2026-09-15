"""Reciprocal rank fusion and the retrieval metrics (design §8).

Kept separate from any model so the fusion and the scoring can be tested without a GPU,
a download or a database.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

#: Cormack et al.'s constant. Named so the report can state what was used.
RRF_K = 60


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> List[str]:
    """Fuse ranked id lists by reciprocal rank: score(d) = sum 1/(k + rank(d)), rank 1-based.

    Ids absent from a leg contribute nothing from that leg (they are not given a worst-case
    rank — that would let a long leg dominate). Ties break by first appearance, so the
    output is deterministic.
    """
    score: Dict[str, float] = {}
    order: Dict[str, int] = {}
    seq = 0
    for leg in rankings:
        for i, doc in enumerate(leg):
            score[doc] = score.get(doc, 0.0) + 1.0 / (k + i + 1)
            if doc not in order:
                order[doc] = seq
                seq += 1
    return sorted(score, key=lambda d: (-score[d], order[d]))


def recall_at_k(retrieved: Sequence[str], gold: Iterable[str], k: int) -> float:
    """1.0 if ANY gold id is in the top k, else 0.0.

    A gold passage may map to more than one chunk (an anchor straddling a boundary); the
    question asked is "did the top k surface the passage", so any gold chunk is a hit.
    """
    gold = set(gold)
    return 1.0 if any(d in gold for d in retrieved[:k]) else 0.0


def reciprocal_rank(retrieved: Sequence[str], gold: Iterable[str]) -> float:
    """1/rank of the FIRST gold id, 0.0 if none is retrieved."""
    gold = set(gold)
    for i, doc in enumerate(retrieved):
        if doc in gold:
            return 1.0 / (i + 1)
    return 0.0


def score_run(results: Dict[str, Sequence[str]], gold: Dict[str, Sequence[str]], ks=(5, 20)) -> Dict[str, float]:
    """Mean recall@k and MRR over the query set. ``results``/``gold`` keyed by query id."""
    out: Dict[str, float] = {}
    qids = sorted(gold)
    n = len(qids) or 1
    for k in ks:
        out["recall@%d" % k] = sum(recall_at_k(results.get(q, []), gold[q], k) for q in qids) / n
    out["mrr"] = sum(reciprocal_rank(results.get(q, []), gold[q]) for q in qids) / n
    out["n_queries"] = float(len(qids))
    return out

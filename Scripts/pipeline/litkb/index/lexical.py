"""The lexical leg of the hybrid (design §8).

Postgres `tsvector` + `pg_trgm` is the production leg. For the P7 bake-off the leg is run
DB-free with Okapi BM25 over the same chunk set, because what P7 has to decide is which
DENSE model to use: the lexical leg is present only as the comparator and as the other
half of the fusion. Swapping BM25 for `tsvector` would change the lexical numbers but not
which embedding model wins, and that limitation is stated in the report rather than
papered over.

The tokeniser is deliberately plain: lowercase, split on non-alphanumerics, drop
single characters. It is the SAME tokeniser used by the gold set's n-gram overlap check,
so "the query shares no 4-token run with the passage" is a statement about these tokens.
"""
from __future__ import annotations

import re
from typing import List, Sequence

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 1]


def ngram_overlap(a: str, b: str, n: int = 4) -> bool:
    """True if ``a`` and ``b`` share a run of ``n`` consecutive tokens.

    The gold-set rule (design §8: the queries must be PARAPHRASED, or the lexical leg
    finds them and the vectors are never tested) is checked with this.
    """
    ta, tb = tokenize(a), tokenize(b)
    if len(ta) < n or len(tb) < n:
        return False
    grams = {tuple(tb[i:i + n]) for i in range(len(tb) - n + 1)}
    return any(tuple(ta[i:i + n]) in grams for i in range(len(ta) - n + 1))


class BM25:
    """Okapi BM25. Built here rather than pulled in so the leg has no extra dependency."""

    def __init__(self, corpus: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [list(d) for d in corpus]
        self.n = len(self.docs)
        self.lens = [len(d) for d in self.docs]
        self.avgdl = (sum(self.lens) / self.n) if self.n else 0.0
        self.tf: List[dict] = []
        df: dict = {}
        for doc in self.docs:
            counts: dict = {}
            for tok in doc:
                counts[tok] = counts.get(tok, 0) + 1
            self.tf.append(counts)
            for tok in counts:
                df[tok] = df.get(tok, 0) + 1
        import math
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.postings: dict = {}
        for i, counts in enumerate(self.tf):
            for tok in counts:
                self.postings.setdefault(tok, []).append(i)

    def scores(self, query_tokens: Sequence[str]) -> dict:
        out: dict = {}
        for tok in query_tokens:
            idf = self.idf.get(tok)
            if idf is None:
                continue
            for i in self.postings[tok]:
                freq = self.tf[i][tok]
                denom = freq + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avgdl)
                out[i] = out.get(i, 0.0) + idf * freq * (self.k1 + 1) / denom
        return out

    def top_k(self, query: str, ids: Sequence[str], k: int = 50) -> List[str]:
        scored = self.scores(tokenize(query))
        order = sorted(scored, key=lambda i: (-scored[i], i))[:k]
        return [ids[i] for i in order]

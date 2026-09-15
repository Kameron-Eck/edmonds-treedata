"""Dense embedding backends for the P7 bake-off — bge-m3 and nomic-embed-text-v1.5.

Every heavy import lives inside a function (design §9). Importing this module loads
nothing but numpy-free stdlib, so ``qc/check.py`` never pulls torch.

Two model-card facts shape the code. They are AUTHORED here from the model cards (fetched
2026-09-15; the URLs are cited in the phase report) — :func:`describe` prints them back
alongside what the loaded model reports about itself, which is a consistency check, not an
independent reading of the card:

* **nomic-embed-text-v1.5 requires task prefixes.** Its card specifies ``search_query:``
  for queries and ``search_document:`` for passages. Embedding both sides with the same
  prefix (or none) is the single easiest way to quietly halve its recall, so the prefix is
  part of the backend, not the caller's problem. It also needs ``trust_remote_code=True``.
* **bge-m3 takes NO instruction.** Its card: "the BGE-M3 model no longer requires adding
  instructions to the queries" (fetched 2026-09-15). Adding one would be wrong. The card
  does not state whether its dense output is already normalised, so this module normalises
  explicitly rather than assuming.

Both are scored with cosine similarity on L2-normalised vectors — ``normalize_embeddings``
is passed for both, so the metric is identical across models and the random-vector kill is
an exactly comparable substitution (same dims, same metric, same code path).
"""
from __future__ import annotations

from typing import Dict, List, Sequence

#: model key -> (HuggingFace id, dims, licence, query prefix, passage prefix)
MODELS: Dict[str, Dict[str, object]] = {
    "bge-m3": {
        "hf_id": "BAAI/bge-m3",
        "dims": 1024,
        "licence": "MIT",
        "query_prefix": "",
        "passage_prefix": "",
        "trust_remote_code": False,
        "max_tokens": 8192,
    },
    "nomic-v1.5": {
        "hf_id": "nomic-ai/nomic-embed-text-v1.5",
        "dims": 768,
        "licence": "Apache-2.0",
        "query_prefix": "search_query: ",
        "passage_prefix": "search_document: ",
        "trust_remote_code": True,
        "max_tokens": 8192,
    },
}


def load(model_key: str, device: str = "cpu"):
    """Load a SentenceTransformer. Heavy import is deliberately inside the function."""
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    spec = MODELS[model_key]
    return SentenceTransformer(
        str(spec["hf_id"]),
        device=device,
        trust_remote_code=bool(spec["trust_remote_code"]),
    )


def encode(model, model_key: str, texts: Sequence[str], is_query: bool,
           batch_size: int = 16, max_seq_length: int = 512):
    """Encode with the model's own prefix rule; returns L2-normalised float32 vectors.

    ``max_seq_length`` is capped well below the models' 8192 because the chunks are
    300-500 tokens — paying for 8192 positions would measure padding, not retrieval.
    """
    spec = MODELS[model_key]
    prefix = str(spec["query_prefix"] if is_query else spec["passage_prefix"])
    model.max_seq_length = max_seq_length
    return model.encode(
        [prefix + t for t in texts],
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )


def search(query_vecs, chunk_vecs, chunk_ids: Sequence[str], top_k: int = 50) -> List[List[str]]:
    """Cosine top-k per query. Vectors are already normalised, so this is a dot product."""
    import numpy as np  # noqa: PLC0415

    sims = np.asarray(query_vecs, dtype="float32") @ np.asarray(chunk_vecs, dtype="float32").T
    out = []
    for row in sims:
        idx = np.argpartition(-row, min(top_k, len(row) - 1))[:top_k]
        idx = idx[np.argsort(-row[idx])]
        out.append([chunk_ids[i] for i in idx])
    return out


def random_vectors(n: int, dims: int, seed: int = 20260915):
    """The KILL substitution: same count, same dims, same normalisation, no information.

    Used in place of the real chunk AND query vectors. If the vector leg still scores,
    the score was never coming from the vectors.
    """
    import numpy as np  # noqa: PLC0415

    rng = np.random.default_rng(seed)
    vecs = rng.standard_normal((n, dims)).astype("float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs


def describe(model, model_key: str) -> Dict[str, object]:
    """What the loaded model actually reports about itself — for the report's fact rows."""
    spec = dict(MODELS[model_key])
    try:
        spec["reported_dims"] = model.get_sentence_embedding_dimension()
    except Exception:  # pragma: no cover - backend-dependent
        spec["reported_dims"] = None
    spec["reported_max_seq_length"] = getattr(model, "max_seq_length", None)
    return spec

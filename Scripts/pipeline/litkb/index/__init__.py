"""Stage 7: chunks, embeddings, hybrid retrieval (design §7 stage 7, §8).

Nothing heavy is imported at module level. ``import litkb.index`` must not pull torch,
sentence-transformers or FlagEmbedding — the embedding backends are imported inside the
functions that use them (design §9, "Dependencies stay out of the engine's environment").
"""

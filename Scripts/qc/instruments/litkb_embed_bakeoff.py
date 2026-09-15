"""The P7 embedding bake-off: throughput, recall on the vector leg, the lexical leg, the
hybrid, and the random-vector kill.

    # (in the dedicated venv, D:\\edmonds-pipeline\\venv-embed)
    PYTHONUTF8=1 python qc/instruments/litkb_embed_bakeoff.py \
        --chunks D:\\edmonds-pipeline\\_tmp\\litkb_p7\\chunks.jsonl \
        --gold ../Reports/litkb_p7_gold_2026-09-15.json \
        --thresholds ../Reports/litkb_p7_thresholds_2026-09-15.json \
        --model bge-m3 --device cpu \
        --csv ../Reports/litkb_p7_results_2026-09-15.csv \
        --harness ../Reports/litkb_p7_harness_2026-09-15.csv

Three legs are scored SEPARATELY, because §8 requires it: the vector leg alone must carry
the paraphrased queries on its own, and the lexical leg would otherwise rescue a scrambled
index. The kill re-runs the vector leg with random vectors of the same dims through the
same code path.

Gold passages are anchored on SOURCE char offsets, so the set of correct chunks for a
query is derived here (chunks whose span overlaps the anchor). Anchors that straddle a
chunk boundary have more than one correct chunk, and the count of those is reported: it is
a fact about the chunker, not about the models.
"""
import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.index import chunk as C  # noqa: E402
from litkb.index import fuse as F  # noqa: E402
from litkb.index import lexical as L  # noqa: E402

TOP_K = 50


def load_chunks(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def gold_chunks(gold, chunks):
    """query id -> list of correct chunk ids; plus the straddle count."""
    out, straddle, empty = {}, 0, []
    for q in gold["queries"]:
        hits = C.chunks_covering(chunks, q["source_stem"], int(q["char_start"]), int(q["char_end"]))
        out[q["id"]] = hits
        if len(hits) > 1:
            straddle += 1
        if not hits:
            empty.append(q["id"])
    return out, straddle, empty


def peak_rss_bytes():
    try:
        import psutil  # noqa: PLC0415
        return psutil.Process().memory_info().peak_wset  # Windows
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--thresholds", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-seq-length", type=int, default=512)
    ap.add_argument("--limit-chunks", type=int, default=0, help="debug only; 0 = all")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--harness", default=None)
    ap.add_argument("--cache-dir", default=r"D:\edmonds-pipeline\_tmp\litkb_p7")
    args = ap.parse_args(argv)

    from litkb.index import embed as E  # heavy; imported only when the bake-off runs

    chunks = load_chunks(args.chunks)
    if args.limit_chunks:
        chunks = chunks[: args.limit_chunks]
    ids = [str(c["chunk_id"]) for c in chunks]
    texts = [str(c["text"]) for c in chunks]

    with open(args.gold, encoding="utf-8") as fh:
        gold = json.load(fh)
    with open(args.thresholds, encoding="utf-8") as fh:
        thresholds = json.load(fh)
    gmap, straddle, empty = gold_chunks(gold, chunks)
    if empty:
        print("WARNING: %d gold queries have NO covering chunk: %s" % (len(empty), empty))
    queries = [q["query"] for q in gold["queries"]]
    qids = [q["id"] for q in gold["queries"]]

    print("model %s on %s | %d chunks | %d queries | %d anchors straddle a chunk boundary"
          % (args.model, args.device, len(chunks), len(qids), straddle))

    # ------------------------------------------------------------------ dense embedding
    model = E.load(args.model, device=args.device)
    spec = E.describe(model, args.model)
    print("model card: dims=%s reported=%s licence=%s prefix=%r"
          % (spec["dims"], spec["reported_dims"], spec["licence"], spec["query_prefix"]))

    cache = os.path.join(args.cache_dir, "vecs_%s_%s.npy" % (args.model, args.device))
    import numpy as np
    t0 = time.perf_counter()
    if os.path.exists(cache):
        chunk_vecs = np.load(cache)
        embed_s = None
        print("chunk vectors loaded from cache (throughput not re-measured)")
    else:
        chunk_vecs = E.encode(model, args.model, texts, is_query=False,
                              batch_size=args.batch_size, max_seq_length=args.max_seq_length)
        embed_s = time.perf_counter() - t0
        os.makedirs(args.cache_dir, exist_ok=True)
        np.save(cache, chunk_vecs)
    rate = (len(texts) / embed_s) if embed_s else None
    peak = peak_rss_bytes()
    index_bytes = chunk_vecs.nbytes
    if embed_s:
        print("embedded %d chunks in %.1f s = %.2f chunks/s | index %.1f MB | peak RSS %s"
              % (len(texts), embed_s, rate, index_bytes / 1e6,
                 ("%.1f GB" % (peak / 1e9)) if peak else "n/a"))

    q_vecs = E.encode(model, args.model, queries, is_query=True,
                      batch_size=args.batch_size, max_seq_length=args.max_seq_length)

    # ----------------------------------------------------------------------- three legs
    vec_rank = E.search(q_vecs, chunk_vecs, ids, top_k=TOP_K)
    vector = {qid: r for qid, r in zip(qids, vec_rank)}

    bm25 = L.BM25([L.tokenize(t) for t in texts])
    lexical = {qid: bm25.top_k(q, ids, k=TOP_K) for qid, q in zip(qids, queries)}

    hybrid = {qid: F.rrf([vector[qid], lexical[qid]]) for qid in qids}

    # ------------------------------------------------------------------------- the kill
    rnd_chunk = E.random_vectors(len(ids), int(spec["dims"]), seed=20260915)
    rnd_query = E.random_vectors(len(qids), int(spec["dims"]), seed=20260916)
    killed = {qid: r for qid, r in zip(qids, E.search(rnd_query, rnd_chunk, ids, top_k=TOP_K))}

    legs = {
        "vector": vector,
        "lexical": lexical,
        "hybrid": hybrid,
        "vector_random_KILL": killed,
    }
    rows = []
    for leg, res in legs.items():
        s = F.score_run(res, gmap)
        rows.append({
            "model": args.model, "device": args.device, "leg": leg,
            "n_chunks": len(chunks), "dims": spec["dims"],
            "recall@5": round(s["recall@5"], 4), "recall@20": round(s["recall@20"], 4),
            "mrr": round(s["mrr"], 4), "n_queries": int(s["n_queries"]),
            "chunks_per_s": round(rate, 3) if rate else "",
            "index_mb": round(index_bytes / 1e6, 2),
            "batch_size": args.batch_size, "max_seq_length": args.max_seq_length,
        })
        print("%-20s recall@5=%.3f recall@20=%.3f mrr=%.3f" % (leg, s["recall@5"], s["recall@20"], s["mrr"]))
        # per-kind breakdown
        for kind in ("paraphrase", "conceptual", "structural"):
            sub = {q["id"]: gmap[q["id"]] for q in gold["queries"] if q["kind"] == kind}
            ss = F.score_run(res, sub)
            print("    %-12s recall@5=%.3f recall@20=%.3f mrr=%.3f (n=%d)"
                  % (kind, ss["recall@5"], ss["recall@20"], ss["mrr"], ss["n_queries"]))
            rows.append({
                "model": args.model, "device": args.device, "leg": "%s/%s" % (leg, kind),
                "n_chunks": len(chunks), "dims": spec["dims"],
                "recall@5": round(ss["recall@5"], 4), "recall@20": round(ss["recall@20"], 4),
                "mrr": round(ss["mrr"], 4), "n_queries": int(ss["n_queries"]),
                "chunks_per_s": "", "index_mb": "", "batch_size": args.batch_size,
                "max_seq_length": args.max_seq_length,
            })

    # ------------------------------------------------------------------- harness verdict
    kill_cfg = thresholds["kill"]
    kill_score = F.score_run(killed, gmap)[kill_cfg["metric"]]
    real_score = F.score_run(vector, gmap)[kill_cfg["metric"]]
    fired = kill_score < float(kill_cfg["must_fall_below"])
    harness = [{
        "row_id": "P7K1", "model": args.model, "device": args.device,
        "mutation": "chunk AND query vectors replaced by random unit vectors, same dims, same code path",
        "leg": "vector_alone", "metric": kill_cfg["metric"],
        "threshold": kill_cfg["must_fall_below"],
        "real": round(real_score, 4), "mutated": round(kill_score, 4),
        "expected": "FIRE", "observed": "FIRE" if fired else "DID NOT FIRE",
    }]
    print("\nKILL  %s vector-alone %s: real %.3f -> random %.3f (must fall below %s) => %s"
          % (args.model, kill_cfg["metric"], real_score, kill_score,
             kill_cfg["must_fall_below"], harness[0]["observed"]))

    for leg_name, key in (("vector", "vector_leg"), ("hybrid", "hybrid")):
        s = F.score_run(legs[leg_name], gmap)
        for metric, floor in thresholds[key].items():
            verdict = "PASS" if s[metric] >= float(floor) else "FAIL"
            print("GATE  %-6s %-10s %.3f vs floor %s  %s" % (leg_name, metric, s[metric], floor, verdict))

    if args.csv:
        new = not os.path.exists(args.csv)
        with open(args.csv, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            if new:
                w.writeheader()
            w.writerows(rows)
    if args.harness:
        new = not os.path.exists(args.harness)
        with open(args.harness, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(harness[0].keys()))
            if new:
                w.writeheader()
            w.writerows(harness)
    return 0 if fired else 1


if __name__ == "__main__":
    raise SystemExit(main())

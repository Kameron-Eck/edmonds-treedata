"""How long are the P7 chunks in each model's OWN subword tokens, and how many gold
passages would a given ``max_seq_length`` truncate away?

    (in the venv) python qc/instruments/litkb_p7_token_census.py --model bge-m3

This runs BEFORE any recall is scored, and it decides ``max_seq_length`` — because a gold
anchor sitting past the truncation point is a chunk the model never saw, and the miss
would be charged to the encoder instead of to the cap. Choosing the cap after seeing
recall would be fitting to the gold.

It loads only the TOKENIZER, not the model weights.
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.index import chunk as C  # noqa: E402
from litkb.index import embed as E  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(E.MODELS))
    ap.add_argument("--chunks", default=r"D:\edmonds-pipeline\_tmp\litkb_p7\chunks.jsonl")
    ap.add_argument("--gold", default=None)
    ap.add_argument("--caps", default="512,1024,2048")
    args = ap.parse_args(argv)

    from transformers import AutoTokenizer  # noqa: PLC0415

    spec = E.MODELS[args.model]
    tok = AutoTokenizer.from_pretrained(str(spec["hf_id"]),
                                        trust_remote_code=bool(spec["trust_remote_code"]))

    with open(args.chunks, encoding="utf-8") as fh:
        chunks = [json.loads(line) for line in fh if line.strip()]
    lens = [len(tok.encode(str(c["text"]), add_special_tokens=True)) for c in chunks]
    qs = statistics.quantiles(lens, n=100)
    print("model %s | %d chunks" % (args.model, len(chunks)))
    print("subword tokens  min %d  median %d  p90 %d  p99 %d  max %d"
          % (min(lens), statistics.median(lens), qs[89], qs[98], max(lens)))
    print("subword / whitespace-word ratio (median) %.2f"
          % (statistics.median(lens) / statistics.median([int(c["n_tokens"]) for c in chunks])))

    gold_idx = None
    if args.gold:
        with open(args.gold, encoding="utf-8") as fh:
            gold = json.load(fh)
        gold_ids = set()
        for q in gold["queries"]:
            gold_ids.update(C.chunks_covering(chunks, q["source_stem"],
                                              int(q["char_start"]), int(q["char_end"])))
        gold_idx = [i for i, c in enumerate(chunks) if str(c["chunk_id"]) in gold_ids]
        print("gold chunks     %d" % len(gold_idx))

    for cap in [int(c) for c in args.caps.split(",")]:
        n = sum(1 for x in lens if x > cap)
        line = "cap %5d  truncates %5d chunks (%.1f%%)" % (cap, n, 100.0 * n / len(lens))
        if gold_idx is not None:
            g = sum(1 for i in gold_idx if lens[i] > cap)
            line += "  |  %d of %d GOLD chunks (%.1f%%)" % (g, len(gold_idx), 100.0 * g / max(len(gold_idx), 1))
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

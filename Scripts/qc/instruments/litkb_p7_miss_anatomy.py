"""Why did a P7 gold query miss? Separate corpus damage from encoder failure.

    (in the venv) python qc/instruments/litkb_p7_miss_anatomy.py \
        --model bge-m3 --chunks D:\\edmonds-pipeline\\_tmp\\litkb_p7\\chunks.jsonl \
        --gold ../Reports/litkb_p7_gold_2026-09-15.json \
        --thresholds ../Reports/litkb_p7_thresholds_2026-09-15.json \
        --per-query ../Reports/litkb_p7_perquery_2026-09-15.csv \
        --max-seq-length 1024 --out ../Reports/litkb_p7_miss_anatomy_2026-09-15.csv

A recall number alone cannot say whether the model failed or the text did. This joins the
bake-off's per-query ranks to three MEASURED properties of each gold query's chunks, so a
reader can attribute every miss:

* ``anchor_beyond_cap`` — the anchor text begins past the ``max_seq_length`` cutoff in
  EVERY one of its gold chunks, so the encoder never read it. That is the cap's miss.
* ``subword_per_word`` — subwords per whitespace word in the gold chunk. Text that lost
  its inter-word spaces or interleaved two columns shatters into subwords, so this rises
  well above the corpus median. It is a PROXY for extraction damage, not a diagnosis.
* ``referee_damaged`` — the query ids the referee flagged as extraction-damaged, read out
  of the committed thresholds file (never retyped here).

It changes nothing and scores nothing; the gold, the chunker and the thresholds are
untouched. It only explains the misses the bake-off already recorded.
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.index import chunk as C  # noqa: E402
from litkb.index import embed as E  # noqa: E402


def referee_damaged_ids(thresholds):
    """The flagged ids, read out of the referee's own file rather than restated here."""
    note = str(thresholds.get("rationale", {}).get("extraction_quality", ""))
    return sorted(set(re.findall(r"\bg\d{3}\b", note)))


def char_cutoff(tok, text, cap):
    """First character index the encoder does NOT read at ``cap`` subword tokens."""
    enc = tok(text, add_special_tokens=True, return_offsets_mapping=True,
              truncation=False)
    offsets = enc["offset_mapping"]
    if len(offsets) <= cap:
        return len(text)
    for start, end in offsets[cap:]:
        if end > start:          # skip the special tokens, which map to (0, 0)
            return start
    return len(text)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(E.MODELS))
    ap.add_argument("--chunks", default=r"D:\edmonds-pipeline\_tmp\litkb_p7\chunks.jsonl")
    ap.add_argument("--gold", required=True)
    ap.add_argument("--thresholds", required=True)
    ap.add_argument("--per-query", required=True)
    ap.add_argument("--max-seq-length", type=int, default=1024)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    from transformers import AutoTokenizer  # noqa: PLC0415

    spec = E.MODELS[args.model]
    tok = AutoTokenizer.from_pretrained(str(spec["hf_id"]),
                                        trust_remote_code=bool(spec["trust_remote_code"]))
    prefix = str(spec["passage_prefix"])

    with open(args.chunks, encoding="utf-8") as fh:
        chunks = [json.loads(line) for line in fh if line.strip()]
    by_id = {str(c["chunk_id"]): c for c in chunks}
    with open(args.gold, encoding="utf-8") as fh:
        gold = json.load(fh)
    with open(args.thresholds, encoding="utf-8") as fh:
        thresholds = json.load(fh)
    flagged = set(referee_damaged_ids(thresholds))

    ranks = {}
    with open(args.per_query, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["model"] == args.model:
                ranks[row["query_id"]] = row

    rows, ratios = [], []
    for q in gold["queries"]:
        qid = q["id"]
        gids = C.chunks_covering(chunks, q["source_stem"], int(q["char_start"]), int(q["char_end"]))
        beyond, subw, ratio, ntok = [], [], [], []
        for cid in gids:
            ch = by_id[cid]
            text = prefix + str(ch["text"])
            enc_len = len(tok.encode(text, add_special_tokens=True))
            subw.append(enc_len)
            ntok.append(int(ch["n_tokens"]))
            ratio.append(enc_len / max(int(ch["n_tokens"]), 1))
            # where does the anchor sit inside this chunk, in chunk-local chars?
            local = max(int(q["char_start"]) - int(ch["char_start"]), 0) + len(prefix)
            beyond.append(local >= char_cutoff(tok, text, args.max_seq_length))
        r = ranks.get(qid, {})
        rv, rl = r.get("rank_vector", ""), r.get("rank_lexical", "")
        rows.append({
            "model": args.model, "query_id": qid, "kind": q["kind"],
            "source_stem": q["source_stem"], "n_gold_chunks": len(gids),
            "gold_chunk_words_max": max(ntok) if ntok else "",
            "gold_chunk_subwords_max": max(subw) if subw else "",
            "subword_per_word_max": round(max(ratio), 2) if ratio else "",
            "anchor_beyond_cap": int(bool(beyond) and all(beyond)),
            "referee_damaged": int(qid in flagged),
            "rank_vector": rv, "rank_lexical": rl,
            "vector_miss_at_20": int(not (rv and int(rv) <= 20)),
            "lexical_miss_at_20": int(not (rl and int(rl) <= 20)),
        })
        ratios.extend(ratio)

    med = statistics.median(ratios)
    print("model %s | cap %d | %d gold queries | median subword/word over gold chunks %.2f"
          % (args.model, args.max_seq_length, len(rows), med))
    print("referee-flagged damaged ids (read from the thresholds file): %s"
          % ", ".join(sorted(flagged)))

    misses = [r for r in rows if r["vector_miss_at_20"]]
    cap_only = [r for r in misses if r["anchor_beyond_cap"]]
    dmg = [r for r in misses if r["referee_damaged"] and not r["anchor_beyond_cap"]]
    both_legs = [r for r in misses if r["lexical_miss_at_20"] and not r["anchor_beyond_cap"]
                 and not r["referee_damaged"]]
    rest = [r for r in misses if r not in cap_only and r not in dmg and r not in both_legs]
    print("\nvector misses at 20: %d of %d" % (len(misses), len(rows)))
    print("  anchor never read (beyond the %d-token cap)  %2d  %s"
          % (args.max_seq_length, len(cap_only), [r["query_id"] for r in cap_only]))
    print("  referee-flagged extraction damage            %2d  %s"
          % (len(dmg), [r["query_id"] for r in dmg]))
    print("  also missed by BM25 (no leg found it)        %2d  %s"
          % (len(both_legs), [r["query_id"] for r in both_legs]))
    print("  encoder failure, unexplained                 %2d  %s"
          % (len(rest), [r["query_id"] for r in rest]))

    if args.out:
        new = not os.path.exists(args.out)
        with open(args.out, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            if new:
                w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

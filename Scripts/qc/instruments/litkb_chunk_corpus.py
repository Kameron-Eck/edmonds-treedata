"""Build the P7 chunk corpus from the ``.txt`` extracts and report its size distribution.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_chunk_corpus.py \
        --out D:\\edmonds-pipeline\\_tmp\\litkb_p7\\chunks.jsonl \
        --csv Reports/litkb_p7_chunks_2026-09-15.csv

Model-free by construction: it imports only :mod:`litkb.index.corpus` and
:mod:`litkb.index.chunk`, neither of which touches torch. It is run and its outputs frozen
BEFORE any embedding model is installed (design §14 P7: gold and thresholds are committed
before the tool being measured first runs).
"""
import argparse
import csv
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.index import chunk as C  # noqa: E402
from litkb.index import corpus as K  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", default=K.CORPUS_DIR)
    ap.add_argument("--out", required=True, help="chunks.jsonl (local, not the repo)")
    ap.add_argument("--csv", default=None, help="tracked per-stem summary")
    ap.add_argument("--manifest", default=None, help="tracked corpus manifest CSV")
    args = ap.parse_args(argv)

    rows = K.manifest(args.corpus_dir)
    chash = K.corpus_hash(rows)
    dropped = K.excluded_stems(args.corpus_dir)
    for stem, n in dropped:
        print("excluded (empty extract, %d chars): %s" % (n, stem))
    chunks = C.build_corpus_chunks([r["stem"] for r in rows], lambda s: K.read_text(s, args.corpus_dir))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for ch in chunks:
            fh.write(json.dumps(ch, ensure_ascii=False) + "\n")

    toks = [int(c["n_tokens"]) for c in chunks]
    over = [c for c in chunks if int(c["n_tokens"]) > 500]
    struct = [c for c in chunks if c["kind"] == "structural"]
    print("corpus_sha256   %s" % chash)
    print("chunks_sha256   %s" % C.chunks_hash(chunks))
    print("files           %d" % len(rows))
    print("chunks          %d" % len(chunks))
    print("tokens min/p25/median/p75/max  %d / %d / %d / %d / %d" % (
        min(toks), statistics.quantiles(toks, n=4)[0], statistics.median(toks),
        statistics.quantiles(toks, n=4)[2], max(toks)))
    print("mean tokens     %.1f" % statistics.mean(toks))
    print("structural      %d (%.1f%%)" % (len(struct), 100.0 * len(struct) / len(chunks)))
    print("over 500 tok    %d (single oversized paragraphs)" % len(over))

    if args.manifest:
        with open(args.manifest, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["stem", "codec", "n_chars", "sha256"])
            w.writeheader()
            w.writerows(rows)
    if args.csv:
        per = {}
        for ch in chunks:
            d = per.setdefault(ch["stem"], {"stem": ch["stem"], "n_chunks": 0, "n_structural": 0, "tokens": 0})
            d["n_chunks"] += 1
            d["n_structural"] += 1 if ch["kind"] == "structural" else 0
            d["tokens"] += int(ch["n_tokens"])
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["stem", "n_chunks", "n_structural", "tokens"])
            w.writeheader()
            for k in sorted(per):
                w.writerow(per[k])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

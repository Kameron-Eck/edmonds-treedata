"""Mechanically re-check the referee's gold set. The builder never EDITS it.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_p7_verify_gold.py \
        --gold ../Reports/litkb_p7_gold_2026-09-15.json

Every rule the referee was given is re-checked here, because a gold set that has not been
verified mechanically is an assertion. If a row fails, the failure is sent back to the
referee — the builder editing gold would put the proposer back in the scorer's chair
(CLAUDE.md §3.4c).

It also prints the file's sha256, which is the number quoted in the phase report.
"""
import argparse
import collections
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.index import corpus as K  # noqa: E402
from litkb.index import lexical as L  # noqa: E402

EXPECTED_KINDS = {"paraphrase": 30, "conceptual": 15, "structural": 15}


def verify(gold_path):
    with open(gold_path, "rb") as fh:
        raw = fh.read()
    sha = hashlib.sha256(raw).hexdigest()
    gold = json.loads(raw.decode("utf-8"))
    queries = gold["queries"]
    stems = set(K.stems())
    failures = []

    kinds = collections.Counter(q["kind"] for q in queries)
    if len(queries) != 60:
        failures.append(("COUNT", "-", "%d queries, expected 60" % len(queries)))
    for kind, want in EXPECTED_KINDS.items():
        if kinds.get(kind, 0) != want:
            failures.append(("KIND", kind, "%d, expected %d" % (kinds.get(kind, 0), want)))

    ids = [q["id"] for q in queries]
    if len(set(ids)) != len(ids):
        failures.append(("ID", "-", "duplicate ids"))

    cache = {}
    for q in queries:
        qid = q["id"]
        stem = q["source_stem"]
        if stem not in stems:
            failures.append(("STEM", qid, "%s is not in the corpus" % stem))
            continue
        if stem not in cache:
            cache[stem] = K.read_text(stem)[0]
        text = cache[stem]
        s, e = int(q["char_start"]), int(q["char_end"])
        if text[s:e] != q["anchor_text"]:
            failures.append(("ANCHOR", qid, "text[%d:%d] != anchor_text (stem %s)" % (s, e, stem)))
            continue
        n = len(q["anchor_text"])
        if not (200 <= n <= 2000):
            failures.append(("LENGTH", qid, "anchor is %d chars, want 200-2000" % n))
        if L.ngram_overlap(q["query"], q["anchor_text"], n=4):
            failures.append(("NGRAM", qid, "query shares a 4-token run with the anchor"))

    n_stems = len({q["source_stem"] for q in queries})
    if n_stems < 25:
        failures.append(("SPREAD", "-", "%d distinct stems, want >= 25" % n_stems))

    return sha, gold, kinds, n_stems, failures


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    args = ap.parse_args(argv)
    sha, _gold, kinds, n_stems, failures = verify(args.gold)
    print("gold sha256     %s" % sha)
    print("kinds           %s" % dict(sorted(kinds.items())))
    print("distinct stems  %d" % n_stems)
    if failures:
        print("\nFAILURES (%d) — send back to the referee, do not edit:" % len(failures))
        for rule, qid, msg in failures:
            print("  %-8s %-6s %s" % (rule, qid, msg))
        return 1
    print("\nALL RULES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

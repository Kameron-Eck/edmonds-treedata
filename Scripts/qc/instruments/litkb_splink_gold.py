"""Freeze the gold sets the Splink evaluation is scored against (CLAUDE.md 3.4b/3.4c).

The gold is frozen and hashed BEFORE any Splink run, so no number in
Reports/LITKB_SPLINK_2026-09-15.md can be a design validating itself: the evaluator
reads this file, it never rebuilds it.

Every row here is DERIVED from a tracked or measured file, never typed from a report's
prose except where the report IS the human judgement (the review/edition cases and the
five "lost genuine" rows, each carried with the report line that names it).

Sources, all read-only, none of them a database:
  D:\\edmonds-pipeline\\litkb_derived\\p6\\references.jsonl   658 P6 references + resolutions
  D:\\edmonds-pipeline\\litkb_derived\\p6\\kills.json          the P6 near-miss mutations
  treedata-litkb\\Reports\\litkb_export\\literature_tracker.csv  460 tracker rows
  treedata-litkb\\Reports\\litkb_export\\manifest.csv            207 manifest rows

Usage:
  py -3.12 qc/instruments/litkb_splink_gold.py            # write + print sha256
  py -3.12 qc/instruments/litkb_splink_gold.py --check    # rebuild, compare, exit 1 on drift
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

DERIVED = Path(r"D:\edmonds-pipeline\litkb_derived")
P6 = DERIVED / "p6"
EXPORT = Path(r"D:\edmonds-pipeline\treedata-litkb\Reports\litkb_export")
OUT = Path(__file__).resolve().parents[2].parent / "Reports" / "litkb_splink_gold_2026-09-15.json"

# The three book-review cases and the four sibling-edition cases.
# Home: Reports/LITKB_S2_BATCHING_2026-09-15.md, the §8 refusal table (lines 378-380).
# These are the HUMAN judgement the batching referee measured; there is no machine-readable
# file that carries them, so they are quoted with the line that names each one.
REVIEW_CASES = [
    # (citing stem prefix, ref_key, the DOI that must NOT be linked, what it actually is)
    ("Alwan", "b13", "10.2307/1269348", "journal-article review of the cited book"),
    ("Burnicki", "b23", "10.2307/214811", "Geographical Review review; authors Semple, Getis, Boots"),
    ("Hall", "b10", "10.2307/2531038", "journal-article review of the cited book"),
]
EDITION_CASES = [
    ("Foody", "b58", "10.1016/b978-0-08-044894-7.01340-3", "2010 record vs 2004 reference"),
    ("Efron", "b0", "10.1007/978-1-4612-0919-5_38", "1992 record vs 1973 reference"),
    ("Foody", "b76", "10.1142/9789814329804_0014", "2011 record vs 2002 reference"),
    ("Goodchild", "b1", "10.4324/9780203303245_chapter_one", "2010 record vs 2002 reference"),
]
# The five correct resolutions the rule refuses because Crossref's record is thin.
# Home: Reports/LITKB_S2_BATCHING_2026-09-15.md §8 lines 393-399, upheld by
# Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md §3 ("5 of 5 are Crossref's record being thin").
LOST_GENUINE = [
    ("Abercrombie", "b16", "10.1109/tsmc.1978.4309889", "crossref_no_author"),
    ("Burnicki", "b12", "10.1201/b12612-12", "crossref_no_author"),
    ("Foody", "b14", "10.1093/oxfordjournals.aje.a120609", "crossref_title_ratio"),
    ("Foody", "b38", "10.1093/oxfordjournals.aje.a120610", "crossref_title_ratio"),
    ("Burnicki", "b43", "10.14358/pers.69.3.289", "crossref_title_ratio"),
]
# Referee-verified NON-duplicate, carried so a duplicate model can be scored on it.
# Home: Reports/LITKB_P3_REPORT_2026-09-15.md, "303/60 is a preprint and its journal version,
# two distinct DOIs and therefore two works under the rules as written".
RELATED_NOT_DUPLICATE = [("303", "60", "preprint and its journal version; two works, one paper")]


def _norm_doi(d):
    d = (d or "").strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d


def _refs():
    return [json.loads(line) for line in (P6 / "references.jsonl").open(encoding="utf-8")]


def _ref_id(row):
    return f"{row['citing_work_key']}::{row['ref_key']}"


def _match(refs, stem_prefix, ref_key):
    """Resolve a (stem prefix, ref_key) pair from the report's prose to exactly one reference.

    Refuses on 0 or >1 hits rather than silently picking one: a gold row that cannot be
    pinned to a single reference is a defect in the gold, not something to average over.
    """
    hits = [r for r in refs if r["citing_work_key"].startswith(stem_prefix) and r["ref_key"] == ref_key]
    if len(hits) != 1:
        raise SystemExit(f"gold: {stem_prefix}/{ref_key} matched {len(hits)} references, expected 1")
    return hits[0]


def build():
    refs = _refs()
    kills = json.loads((P6 / "kills.json").read_text(encoding="utf-8"))

    # --- positives: every reference the P6 resolver CONFIRMED, with its DOI -------------
    positives = [
        {"ref_id": _ref_id(r), "citing_work_key": r["citing_work_key"], "ref_key": r["ref_key"],
         "gold_doi": _norm_doi(r["resolved_doi"]),
         "resolver_reason": (r.get("resolution_detail") or {}).get("reason", "")}
        for r in refs if r["resolution"] == "resolved" and r.get("resolved_doi")
    ]

    # --- must-not-link ------------------------------------------------------------------
    mnl = []
    for group, cases in (("book_review", REVIEW_CASES), ("edition", EDITION_CASES)):
        for stem, key, doi, why in cases:
            r = _match(refs, stem, key)
            mnl.append({"kind": group, "ref_id": _ref_id(r), "bad_doi": _norm_doi(doi), "why": why,
                        "source": "Reports/LITKB_S2_BATCHING_2026-09-15.md §8 refusal table"})
    # the P6 near-miss mutations that are TRUE kills: the mutated reference must not link
    # back to the original DOI. is_kill is false for the 20 title-word rows, which are
    # deliberately still the same paper -- those are near-POSITIVES, kept separately.
    near = kills["near_miss"]
    for i, k in enumerate(near):
        rec = {"kind": f"mutation_{k['mutation']}", "ref_id": f"{k['stem']}::{k['ref_key']}#mut{i}",
               "base_ref_id": f"{k['stem']}::{k['ref_key']}", "mutation": k["mutation"],
               "mutant_title": k["mutant_title"], "mutant_year": k["mutant_year"],
               "mutant_doi": _norm_doi(k["mutant_doi"]), "bad_doi": _norm_doi(k["original_doi"]),
               "source": "litkb_derived/p6/kills.json near_miss"}
        if k["is_kill"]:
            mnl.append(rec)
    near_positives = [
        {"ref_id": f"{k['stem']}::{k['ref_key']}#mut{i}", "base_ref_id": f"{k['stem']}::{k['ref_key']}",
         "mutation": k["mutation"], "mutant_title": k["mutant_title"], "mutant_year": k["mutant_year"],
         "gold_doi": _norm_doi(k["original_doi"])}
        for i, k in enumerate(near) if not k["is_kill"]
    ]

    # --- lost genuine (Task C) ----------------------------------------------------------
    lost = []
    for stem, key, doi, why in LOST_GENUINE:
        r = _match(refs, stem, key)
        lost.append({"ref_id": _ref_id(r), "gold_doi": _norm_doi(doi), "refusal_reason": why,
                     "source": "Reports/LITKB_S2_BATCHING_2026-09-15.md §8; REFEREE2 §3"})

    # --- duplicate gold, from the tracker's own column -----------------------------------
    trk = list(csv.DictReader((EXPORT / "literature_tracker.csv").open(encoding="utf-8-sig")))
    man = list(csv.DictReader((EXPORT / "manifest.csv").open(encoding="utf-8-sig")))
    by_id = {r["ID"]: r for r in trk}
    dup_pairs = []
    for r in trk:
        other = (r.get("Duplicate of") or "").strip()
        if not other:
            continue
        o = by_id.get(other)
        rel = any(r["ID"] == a and other == b for a, b, _ in RELATED_NOT_DUPLICATE)
        dup_pairs.append({
            "left_id": r["ID"], "right_id": other,
            "left_key": r["litkb_key"], "right_key": o["litkb_key"] if o else "",
            "left_title": r["Title"], "right_title": o["Title"] if o else "",
            "left_state": r["litkb_state"], "right_state": o["litkb_state"] if o else "",
            "verdict": "related_not_duplicate" if rel else "duplicate",
            "note": next((w for a, b, w in RELATED_NOT_DUPLICATE if r["ID"] == a and other == b), ""),
        })

    admitted = sorted({r["litkb_key"] for r in trk + man
                       if r["litkb_state"] == "admitted" and r["litkb_key"]})

    return {
        "built": "2026-09-15",
        "purpose": "frozen gold for the Splink candidate-scoring evaluation",
        "sources": {
            "references_jsonl": str(P6 / "references.jsonl"),
            "kills_json": str(P6 / "kills.json"),
            "tracker_csv": str(EXPORT / "literature_tracker.csv"),
            "manifest_csv": str(EXPORT / "manifest.csv"),
        },
        "counts": {
            "references_total": len(refs),
            "positives": len(positives),
            "must_not_link": len(mnl),
            "near_positive_mutations": len(near_positives),
            "lost_genuine": len(lost),
            "duplicate_pairs": len(dup_pairs),
            "admitted_works": len(admitted),
        },
        "positives": positives,
        "must_not_link": mnl,
        "near_positive_mutations": near_positives,
        "lost_genuine": lost,
        "duplicate_pairs": dup_pairs,
        "admitted_work_keys": admitted,
    }


def _canon(obj):
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="rebuild and compare against the frozen file")
    args = ap.parse_args(argv)

    blob = _canon(build())
    digest = hashlib.sha256(blob).hexdigest()
    if args.check:
        if not OUT.exists():
            print(f"MISSING {OUT}")
            return 1
        # CRLF-safe: .gitattributes carries `* text=auto`, so the tracked file is LF in the
        # repository and CRLF in this Windows working copy. Hash the LF form either way, or
        # the check reports drift on every fresh checkout.
        have = hashlib.sha256(OUT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        print(f"frozen  {have}\nrebuilt {digest}")
        if have != digest:
            print("GOLD DRIFT")
            return 1
        print("GOLD MATCH")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(blob)
    print(f"wrote {OUT}")
    print(f"sha256 {digest}")
    print(json.dumps(json.loads(blob)["counts"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

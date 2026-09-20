"""Item 2 (2026-09-19) -- run the Crossref raw-string second proposer over the 50 title/author-blind
references, and dump one row per reference for hand-scoring.

    cd Scripts && PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_crossref_raw_search_eval.py

No manual sys.path surgery here (that ledger is closed): run with `PYTHONPATH=pipeline` set, exactly
as `litkb_p6_references.py`'s own docstring does.

MEASUREMENT CONTRACT (CLAUDE.md 3.4b): this is the instrument. Its output is the tracked CSV
`Reports/LITKB_CROSSREF_RAWSEARCH_2026-09-19.csv`; a human then fills the `hand_verdict`/
`hand_notes` columns by reading each raw citation against the proposal, and that filled sheet --
not this script's own say-so -- is what precision/recall are computed from (CLAUDE.md 3.4c: the
proposer never scores its own proposal).

REF LIST, DERIVED NOT REMEMBERED: read straight from `litkb_derived/p6/references.jsonl`, the P6
stage-6 run's own tracked-outside-git output (2026-09-15, `qc/instruments/litkb_p6_references.py
--resolve`), filtered to exactly the condition that reaches `resolve_by_raw_search`
(`references.resolve_by_search`): no `doi_norm` AND (no `title` or no `first_author`). This is NOT
assumed to be 50; the count actually found is printed to stdout before any row is written.

NETWORK: real Crossref calls (bibliographic search + one `/works/{doi}` per proposal), 1/s, disk-
cached under its own root `LITKB_DERIVED/item2_rawsearch/registry` -- a fresh cache, not
`litkb_derived/refmatch/cache_crossref_search.jsonl` (CLAUDE.md 3.4c: not the design's own reported
output). No litkb database is touched; P6 is DB-free by construction and this instrument writes no
database row.
"""
import argparse
import csv
import json
import os
import pathlib
import sys

from litkb.admit.resolver import search_crossref
from litkb.extract import references as R
from litkb.netutil import Client, Pacer

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1]
REPO = SCRIPTS.parent

DERIVED = pathlib.Path(os.environ.get("LITKB_DERIVED") or (pathlib.Path(R.DERIVED_ROOT)))
REF_LIST = DERIVED / "p6" / "references.jsonl"
OUT_CSV = REPO / "Reports" / "LITKB_CROSSREF_RAWSEARCH_2026-09-19.csv"
CACHE_ROOT = DERIVED / "item2_rawsearch"


def blind_refs(rows):
    """Exactly the condition `resolve_by_search` uses to route into `resolve_by_raw_search`."""
    return [r for r in rows
            if not (r.get("doi_norm") or "").strip()
            and (not (r.get("title") or "").strip() or not (r.get("first_author") or "").strip())]


def reason_name(reason):
    return (reason or "").split(" (", 1)[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="cap the number of refs (debugging only)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)

    rows = [json.loads(line) for line in REF_LIST.read_text(encoding="utf-8").splitlines() if line.strip()]
    blind = blind_refs(rows)
    print(f"{len(rows)} total references in {REF_LIST}; {len(blind)} title/author-blind "
          f"(no doi_norm, no title or no first_author)")
    if a.limit:
        blind = blind[:a.limit]

    cache = R.DiskCache(root=str(CACHE_ROOT))
    pacer = R.deferred_pacer(Pacer(interval=1.0))
    client = R.CachedClient(client=Client(), cache=cache, pacer=pacer)

    out_rows = []
    for i, ref in enumerate(blind, 1):
        ref_id = f"{ref.get('citing_work_key')}::{ref.get('ref_key')}"
        pacer.wait()
        try:
            cands, err = search_crossref(client, ref.get("raw") or "", pacer)
        except Exception as e:
            cands, err = [], f"{type(e).__name__}: {e}"
        top = cands[0] if cands else None
        pacer.wait()
        res = R.resolve_by_raw_search(ref, client, pacer)
        out_rows.append({
            "ref_id": ref_id,
            "raw": ref.get("raw") or "",
            "parsed_title": ref.get("title") or "",
            "parsed_first_author": ref.get("first_author") or "",
            "proposed_doi": (top or {}).get("doi") or "",
            "proposed_title": ((top or {}).get("titles") or [""])[0],
            "proposed_family": (top or {}).get("family") or "",
            "proposed_year": (top or {}).get("year") or "",
            "search_error": err or "",
            "gate_state": res.state,
            "gate_source": res.source or "",
            "gate_reason": res.reason,
            "gate_reason_name": reason_name(res.reason),
            "gate_doi": res.doi or "",
            "hand_verdict": "",     # filled by hand: correct | incorrect | no_proposal | uncertain
            "hand_notes": "",
        })
        print(f"  [{i}/{len(blind)}] {ref_id}: proposed={out_rows[-1]['proposed_doi'] or '-'} "
              f"gate={res.state}/{out_rows[-1]['gate_reason_name']}", flush=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()) if out_rows else [])
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {len(out_rows)} rows to {OUT_CSV}")
    print(f"cache: {cache.hits} hits, {cache.misses} misses, {cache.stores} stores; "
          f"{client.network_calls} live network calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

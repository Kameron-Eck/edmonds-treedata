"""P3's gate, as an instrument (CLAUDE.md 3.4b): today's tracker and manifest against the regenerated ones.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p3_diff.py --db litkb --workstream <id>

The design's §14 P3 gate is "regenerated tracker and manifest match today's content (reviewed diff)". Today's
content is not word-for-word what the database holds, and is not meant to be: identity comes from the registry
record, so a row whose claim the registry contradicted prints the registry's words. The gate is therefore not
"no differences" but **no UNEXPLAINED differences**. Every changed cell falls in exactly one bucket:

  explained  a `discrepancies` record names this source, this row and this field — the review can see both
             values and the comparator's ratio
  format     the two cells normalise equal (`export_shape.norm_cell`): case, punctuation, `&`/`and`, a
             trailing full stop, `D.J.` against `D. J.`. Same content, different type
  held       the row was never admitted (no verified file, or no resolvable identity), so the export printed
             the legacy row back verbatim — these cells cannot differ, and a difference here is a BUG
  structural a whole-column change the design makes on purpose and states once, not per row: the manifest's
             `stem` is now `works.key` (referee note M7), and `verified_against_extract` is now the binding
             verdict rather than a hand-entered word
  UNEXPLAINED anything else. The gate fails while this count is above zero.

Writes `phase4/qc/litkb_p3_diff.csv` (one row per changed cell) and prints the counts per field. Read-only
against the database; it writes nothing but that CSV.
"""
import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))     # ledger: qc/test_status_discovery.py::test_path_insert_ledger

OUT = REPO / "phase4" / "qc" / "litkb_p3_diff.csv"
#: columns the design changes wholesale, with the reason stated once (never per row)
STRUCTURAL = {("manifest", "stem"): "M7: works.key is authoritative and the file stem is derived from it",
              ("manifest", "verified_against_extract"):
                  "now the admission binding verdict, not a hand-entered yes/no/loose",
              ("manifest", "source_route"): "now the route the file version records; 'unknown (pre-manifest)' "
                                            "rows are files bound in place by P3"}
DIFF_COLUMNS = ["source", "row", "field", "bucket", "today", "exported", "ratio", "explanation"]


def _index(rows, key):
    return {str(r[key]): r for r in rows}


def compare(source, today, exported, key, columns, explained, held_rows):
    """One row per cell that changed. `explained` is {(source, row, field): (claimed, registry, ratio)}."""
    from litkb.migrate_legacy.export_shape import norm_cell

    out, t_idx, e_idx = [], _index(today, key), _index(exported, key)
    for rid, t in t_idx.items():
        e = e_idx.get(rid)
        if e is None:
            out.append({"source": source, "row": rid, "field": "(whole row)", "bucket": "UNEXPLAINED",
                        "today": t.get(columns[0], ""), "exported": "", "ratio": "",
                        "explanation": "the row is not in the export"})
            continue
        for field in columns:
            a, b = (t.get(field) or "").strip(), (e.get(field) or "").strip()
            if a == b:
                continue
            hit = explained.get((source, rid, _FIELD_ALIAS.get(field, field)))
            if (source, field) in STRUCTURAL:
                bucket, why = "structural", STRUCTURAL[(source, field)]
            elif norm_cell(a) == norm_cell(b):
                bucket, why = "format", "the two cells normalise equal"
            elif hit:
                bucket, why = "explained", f"discrepancies: claimed={hit[0]!r} registry={hit[1]!r}"
            elif rid in held_rows:
                bucket, why = "UNEXPLAINED", "the row was HELD: the export must print it back verbatim"
            else:
                bucket, why = "UNEXPLAINED", "no discrepancy record names this cell"
            out.append({"source": source, "row": rid, "field": field, "bucket": bucket,
                        "today": a[:300], "exported": b[:300], "ratio": (hit[2] if hit else ""),
                        "explanation": why})
    for rid in e_idx.keys() - t_idx.keys():
        out.append({"source": source, "row": rid, "field": "(whole row)", "bucket": "UNEXPLAINED",
                    "today": "", "exported": rid, "ratio": "", "explanation": "the export added a row"})
    return out


#: the tracker's column heading -> the discrepancy `field` name that explains it
_FIELD_ALIAS = {"Title": "title", "Author(s)": "authors", "Year": "year", "Journal/Source": "journal",
                "DOI/URL": "doi", "File stem": "legacy_stem", "title": "title", "authors": "authors",
                "year": "year", "venue": "journal", "doi": "doi", "sha256": "sha256"}


def run(conn, ws, root=None):
    from litkb import export as ex
    from litkb.migrate_legacy import sources

    explained, held = {}, set()
    for r in conn.execute("SELECT source, source_row, field, claimed_value, registry_value, ratio "
                          "FROM litkb.discrepancies WHERE workstream_id = %s", (ws,)).fetchall():
        explained[(r[0], r[1], r[2])] = (r[3], r[4], r[5])
    # HELD is "no work at all", not "state <> admitted": a `duplicate` candidate HAS a work — the one it
    # duplicates — and the export rightly prints that work's registry record for it
    for r in conn.execute("SELECT raw_record ->> 'ID', state FROM litkb.candidates "
                          "WHERE workstream_id = %s AND admitted_work_id IS NULL", (ws,)).fetchall():
        if r[0]:
            held.add(r[0])
    rows = compare("tracker", sources.tracker_rows(), ex.tracker_rows(conn, ws), "ID",
                   sources.TRACKER_COLUMNS[1:], explained, held)
    rows += compare("manifest", sources.manifest_rows(root=root), ex.manifest_rows(conn, ws), "stem",
                    sources.MANIFEST_COLUMNS[1:], explained, held)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=os.environ.get("LITKB_DB", "litkb"))
    ap.add_argument("--workstream", required=True)
    ap.add_argument("--role", default=None)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--root")
    a = ap.parse_args(argv)
    from litkb.db import connect as c

    conn = c.connect(a.db, a.role or ("litkb_reader" if a.db == "litkb" else "litkb_test"), autocommit=True)
    rows = run(conn, a.workstream, root=a.root)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DIFF_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    buckets = Counter(r["bucket"] for r in rows)
    per_field = Counter((r["source"], r["field"], r["bucket"]) for r in rows)
    print(f"{len(rows)} changed cells -> {a.out}")
    for b, n in buckets.most_common():
        print(f"  {b:<11} {n}")
    print("\nper field:")
    for (src, field, bucket), n in sorted(per_field.items()):
        print(f"  {src:<9} {field:<28} {bucket:<11} {n}")
    bad = buckets.get("UNEXPLAINED", 0)
    print(f"\nGATE: {'PASS' if bad == 0 else f'FAIL — {bad} unexplained cells'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

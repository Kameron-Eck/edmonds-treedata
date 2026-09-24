r"""THE REVIEWED BACKFILL of identifier provenance (S4.5 item 1; S4.5 decision D1: `identifiers_without_provenance`
is an ALL-TIME counter, "B1 backfills provenance for existing rows, marked as backfilled").

Every identifier_versions row written before migration 0032 has `asserted_by` NULL (survey-data §8: 526 rows with
`verified_by` NULL alone on 2026-09-23 — tracker 369, legacy_stem 157 — and every other row NULL-asserted too).
`litkb.backfill_identifier_provenance` (migration 0032, SECURITY DEFINER, EXECUTE to litkb_ingest) FILLS each NULL
from what the row itself says — `tracker` for a tracker row, `legacy` for a legacy_stem row, `manual` for a row
verified by a manual admitter, `caller` for every other admitted identifier — sets `provenance_backfilled`, and
overwrites nothing. A DRY RUN is the default: it prints the plan (scheme -> source: rows) and changes nothing.

    # dry run (default) against the live base, as the ingest login:
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_identifier_provenance_backfill.py
    # the live write — the ORCHESTRATOR's, after reading the dry run:
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_identifier_provenance_backfill.py --apply --session <label>

Exit 0 on success (a dry run included). Prints one JSON object: {apply, plan, updated, session}.

THE CONNECTION is `litkb.extract.references_ingest.connect` — the ONE rule for the ingest login: `litkb` through
`litkb.ingest.connect()` (its own passfile; `litkb.db.connect.connect()` refuses that login by design), a
worker database through its owner login + `SET ROLE litkb_ingest`. Until auditor-B1 F2 this driver called
`db.connect.connect(db, "litkb_ingest")`, which that guard refuses before any driver import — neither the dry
run nor `--apply` could ever connect.
"""
import argparse
import json
import sys


def backfill(conn, *, apply, session):
    """-> the function's JSON result on `conn` (a connection that may EXECUTE the function: litkb_ingest)."""
    return conn.execute("SELECT litkb.backfill_identifier_provenance(%s, %s)", (bool(apply), session)).fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default="litkb", help="litkb (the ingest login) or a litkb_test* worker database")
    ap.add_argument("--apply", action="store_true", help="WRITE the fill (default: a dry run that changes nothing)")
    ap.add_argument("--session", default=None,
                    help="the session label recorded in the result; REQUIRED with --apply (a dry run is labelled "
                         "provenance-backfill-dry-run)")
    from phase4seg.names import clean_argv

    a = ap.parse_args(clean_argv() if argv is None else argv)
    # auditor-B1 round 2 N8 (integrator-w2): a live write run as `--apply` alone was labelled a dry run
    if a.apply and not (a.session or "").strip():
        raise SystemExit("--apply writes: name the session that ran it (--session <label>)")
    a.session = a.session or "provenance-backfill-dry-run"
    from litkb.extract.references_ingest import connect as ingest_connect

    conn = ingest_connect(a.db)
    try:
        res = backfill(conn, apply=a.apply, session=a.session)
    finally:
        conn.close()
    print(json.dumps(res, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

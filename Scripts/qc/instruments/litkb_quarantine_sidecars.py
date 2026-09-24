"""Write a `.reason.json` sidecar for every quarantined payload that has none (LITKB_WORKPLAN.md "### S4.5"
item 8; counter `quarantines_without_reason`). DRY RUN BY DEFAULT: without `--apply` nothing is written.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_quarantine_sidecars.py            # dry run
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_quarantine_sidecars.py --apply    # write them

It reads the database as litkb_reader (the `quarantine_payloads` row of each payload and the attempt that row
names) and writes ONLY new sidecar files under `<root>/_quarantine/`, create-only through
`Store.write_reason` (`litkb.quarantine.backfill_sidecars`). Every sidecar it writes carries
`"backfilled": true` and its `reason_source`. The orchestrator runs it on the live store; the builder ran it
only on a COPY (D:\\tools\\claude-config\\jobs\\litkb-s4-5\\builder-C1b.md).
"""
import argparse
import sys
from pathlib import Path

DSN = "host=localhost port=5433 dbname={db} user=litkb_reader"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    from litkb.acquire.store import LITERATURE_ROOT     # the store's one home for the root (auditor-C1b r2 F10)

    ap.add_argument("--root", default=str(LITERATURE_ROOT), help="the literature root (default: %(default)s)")
    ap.add_argument("--db", default="litkb", help="the database read as litkb_reader (default: %(default)s)")
    ap.add_argument("--apply", action="store_true", help="write the sidecars (default: a dry run, nothing written)")
    ap.add_argument("--rows", action="store_true", help="print every planned sidecar")
    a = ap.parse_args(argv)
    import psycopg

    from litkb import quarantine as Q

    conn = psycopg.connect(DSN.format(db=a.db))
    if conn.execute("SELECT current_user").fetchone()[0] != "litkb_reader":
        raise SystemExit("litkb_quarantine_sidecars reads the database as litkb_reader only")
    out = Q.backfill_sidecars(conn, root=Path(a.root), apply=a.apply)
    print(f"{'APPLIED' if out['applied'] else 'DRY RUN (nothing written)'} root={out['root']} "
          + " ".join(f"{k}={v}" for k, v in out["counters"].items()))
    for it in out["rows"] if a.rows else ():
        print(f"  {it['action']:20s} {it['rel_path']}  <- {it['body']['reason_source']}")
    for e in out["errors"]:
        print(f"  ERROR {e['rel_path']}: {e['error']}")
    print(f"quarantines_without_reason={Q.without_reason(Path(a.root))[0]}")
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

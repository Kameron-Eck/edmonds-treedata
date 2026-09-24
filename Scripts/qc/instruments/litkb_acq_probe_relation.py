r"""litkb acquisition probe (read-only): THE CROSSREF `relation` PROBE — S4.5 item 1's "the Crossref `relation`
probe first" (LITKB_WORKPLAN.md "### S4.5"; the 2026-09-21 plan revision: "FIRST a sampled live probe over the
base's DOIs, recorded as a measured CSV under phase4/qc/ by an instrument ... absence of the field is not
evidence of absence").

For every DOI-bearing work in main, ask Crossref `works/{doi}` and record what its `relation` object says, parsed
by the SAME function admission's harvest uses (`litkb.admit.harvest.crossref_relations`): one row per relation
edge, or ONE `none_returned` row when the field came back empty (the third state), or one `unanswered` row when
Crossref did not answer 200 (a DataCite DOI answers 404 there — that is "not asked of the right registry", not a
relation verdict). Metadata calls only; nothing is downloaded, nothing is written to the database.

    # LIVE (the orchestrator runs it; ~1 request per DOI through litkb.netutil.Client, paced 1 s — the
    # registry resolver's own REGISTRY_MIN_INTERVAL):
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acq_probe_relation.py
    # HERMETIC (tests, replay): Crossref answers read from recorded JSON files, one per DOI, no socket:
    ... litkb_acq_probe_relation.py --responses <dir> --dois 10.1101/357798,10.1111/2041-210x.13107 --out <csv>

Writes phase4/qc/litkb_acq_probe_relation.csv (columns: :data:`COLUMNS`; docs/SCHEMAS.md "S4.5 builder B1").
Its data rows are the gated counter `relation_probe_rows` (qc/instruments/litkb_hardening_b1.py). The file name
matches `litkb_acceptance.PROBE_GLOB` (`litkb_acq_probe_*`), so `hardening --freeze` names it in the manifest.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS.parent / "phase4" / "qc" / "litkb_acq_probe_relation.csv"

COLUMNS = ("key", "doi", "cr_status", "state", "relation", "source_relation", "target_scheme", "target_value",
           "crossref_asserted_by")


def response_file(directory, doi):
    """The recorded answer for `doi` under `directory`: the DOI with every character outside [a-z0-9.-]
    replaced by `_`, plus `.json`. Its content is Crossref's whole response ({"message": ...})."""
    safe = "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in doi.lower())
    return Path(directory) / f"{safe}.json"


def recorded_crossref(directory):
    """-> fetch(doi) -> (status, message | None), reading `response_file`s; a missing file is status 404."""
    def fetch(doi):
        p = response_file(directory, doi)
        if not p.is_file():
            return 404, None
        body = json.loads(p.read_text(encoding="utf-8"))
        return 200, (body or {}).get("message")
    return fetch


def live_crossref():
    """-> fetch(doi) through the registry resolver's own call (`litkb.admit.registry.crossref_record` on a
    `litkb.netutil.Client`, paced by REGISTRY_MIN_INTERVAL) — the path the cassette layer sees."""
    from litkb.admit import registry as R
    from litkb.admit.resolver import REGISTRY_BACKOFF, REGISTRY_MIN_INTERVAL
    from litkb.netutil import Client, Pacer

    client, pacer = Client(), Pacer(interval=REGISTRY_MIN_INTERVAL, backoff=REGISTRY_BACKOFF)

    def fetch(doi):
        rec, st = R.crossref_record(client, doi, pacer)
        return st, (rec or {}).get("_raw")
    return fetch


def probe_rows(pairs, fetch):
    """[(key, doi)] -> the CSV rows. Pure given `fetch`."""
    from litkb.admit import harvest as H

    out = []
    for key, doi in pairs:
        st, msg = fetch(doi)
        base = {"key": key, "doi": doi, "cr_status": st}
        if st != 200 or not isinstance(msg, dict):
            out.append(base | {"state": "unanswered"})
            continue
        for e in H.crossref_relations(msg, doi):
            out.append(base | {"state": e["state"], "relation": e.get("relation") or "",
                               "source_relation": e.get("source_relation") or "",
                               "target_scheme": e.get("target_scheme") or "", "target_value": e.get("target_value") or "",
                               "crossref_asserted_by": (e.get("evidence") or {}).get("crossref_asserted_by") or ""})
    return out


def write_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    return path


def base_dois(db="litkb", role="litkb_reader"):
    """Every DOI-bearing work in main, as the reader sees it: [(key, doi)] ordered by key."""
    from litkb.db import connect as c

    conn = c.connect(db, role, autocommit=True)
    try:
        return conn.execute("SELECT w.key, i.value FROM litkb.main_identifiers i JOIN litkb.main_works w "
                            "ON w.work_id = i.work_id WHERE i.scheme = 'doi' AND i.active ORDER BY 1, 2").fetchall()
    finally:
        conn.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--responses", help="read Crossref answers from recorded JSON files here (no network)")
    ap.add_argument("--dois", help="comma-separated DOIs (keys are then the DOIs themselves) instead of the base")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--db", default="litkb")
    from phase4seg.names import clean_argv

    a = ap.parse_args(clean_argv() if argv is None else argv)
    pairs = ([(d.strip(), d.strip()) for d in a.dois.split(",") if d.strip()] if a.dois else base_dois(a.db))
    fetch = recorded_crossref(a.responses) if a.responses else live_crossref()
    rows = probe_rows(pairs, fetch)
    p = write_csv(rows, a.out)
    states = {}
    for r in rows:
        states[r["state"]] = states.get(r["state"], 0) + 1
    print(f"dois={len(pairs)} rows={len(rows)} states={dict(sorted(states.items()))} -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Run stage 5 over the gate set and report what it produced — the §3.4b instrument.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_stage5_run.py
    ... --only Alwan_1988 --csv Reports/litkb_stage5_2026-09-15.csv

It reads ARTIFACTS that already exist — a TEI under ``--tei-dir`` and a DoclingDocument under
``--docling-dir`` — and never starts either tool. A file with no TEI is reconciled from Docling
alone (that is what happens to a scan: GROBID refuses a file with no text layer outright, and a
partial one with ``NoTextBlocks``), and the report says which.

Blocks per kind, coverage per page TYPE (stage 0's page class), disagreement counts and the
wall-clock of the reconciliation itself. The coverage denominator is the page's native layer, so
an image-only page reports N/A — never 0 %, which would claim a measurement of a page with
nothing to measure.
"""
import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.extract import docling as D  # noqa: E402
from litkb.extract import inventory as I  # noqa: E402
from litkb.extract import reconcile as R  # noqa: E402

LIT = r"D:\edmonds-pipeline\Literture\Validation"
TEI_DIR = r"D:\edmonds-pipeline\_tmp\litkb_tei"
DOC_DIR = r"D:\edmonds-pipeline\_tmp\litkb_docling"

#: (tag, pdf, docling artifact). The five referee gate papers, then Ogata 1998 — the scan that
#: routes to OCR — and Almon 1965, a JSTOR cover-sheet file.
FILES = [
    ("Benedek_2015", "Benedek_2015_multilayer-markov-random-field-models.pdf", "Benedek_2015__cpu-t4.docling.json"),
    ("Alwan_1988", "Alwan_1988_time-series-modeling-statistical-process.pdf", "Alwan_1988__cpu-t4.docling.json"),
    ("Anderson_1957", "Anderson_1957_statistical-inference-about-markov.pdf", "Anderson_1957__ocr-t4.docling.json"),
    ("Bellettini_2002", "Bellettini_2002_total-variation-flow.pdf", "Bellettini_2002__cpu-t4.docling.json"),
    ("Schneider_2008", "Schneider_2008_stochastic-integral-geometry.pdf", "Schneider_2008__cpu-t4-book.docling.json"),
    ("Ogata_1998", "Ogata_1998_space-time-point-process-models.pdf", "Ogata__stage5.docling.json"),
    ("Almon_1965", "Almon_1965_distributed-lag-between-capital.pdf", "Almon__stage5.docling.json"),
]

FIELDS = ["tag", "file", "pages", "route", "tei", "docling", "seconds", "blocks",
          "matched", "grobid_only", "docling_only", "partial_overlap", "disagreements",
          "skipped_rotated", "by_kind", "coverage_by_page_type", "coverage_failures",
          "figures", "region_recall", "region_recall_missing", "ingested_blocks", "run_id"]

#: The frozen referee gold (Reports/gold/stage5_gold_2026-09-15.json). Read-only, always.
GOLD = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "Reports", "gold", "stage5_gold_2026-09-15.json")


def gold_regions(gold, pdf_name):
    """-> {page: [(n, snippet)]} for this file, TEXT-bearing regions only.

    The bracketed placeholders — "[figure: …]", "[table: …]", "[display equation: …]" — carry no
    printed words, so no block can BEGIN at one and recall cannot score them.
    """
    out = {}
    for p in gold.get("pages", []):
        if p["file"] != pdf_name:
            continue
        out[p["page"]] = [(b["n"], b["snippet"]) for b in p["body_order"]
                          if not b["snippet"].startswith("[")]
    return out


#: The body kinds. The kill removes these from one page and leaves the furniture, which is what
#: a reconciliation that failed to region a page's BODY produces.
BODY_KINDS = ("paragraph", "heading", "caption", "footnote", "equation", "reference")


def drop_catch_all(canonical, page):
    """Remove the body regions of `page` — the planted-page coverage kill (§14).

    MEASURED, and the reason this is not "drop the largest block": on ``Alwan_1988`` p4 the
    single biggest block is a 491x659 pt paragraph covering nearly the whole page, and removing
    it drops that page's coverage only from 1.0000 to 0.9723 — nowhere near the 0.80 floor. The
    canonical blocks OVERLAP (a GROBID-only region and a Docling-only region over the same
    prose), and coverage asks whether SOME block is responsible for a character, so one lost
    region among overlapping ones is invisible to it. That is a true limit of the design's
    metric and it is recorded in the report rather than hidden by a kinder kill: the metric
    detects a page whose body went unassigned, not a single dropped paragraph.

    A real page of a real file, not a fixture.
    """
    on_page = [c for c in canonical if c.page == page]
    if not on_page:
        raise SystemExit(f"no canonical block on page {page}")
    dropped = [c for c in on_page if c.kind in BODY_KINDS]
    keep = [c for c in canonical if c.page != page or c.kind not in BODY_KINDS]
    return keep, dropped


def one(tag, pdf_name, doc_name, tei_dir, doc_dir, drop_page=None, gold=None, db=None):
    pdf = os.path.join(LIT, pdf_name)
    tei_path = os.path.join(tei_dir, pdf_name.split("_")[0] + ".tei.xml")
    doc_path = os.path.join(doc_dir, doc_name)
    record = I.probe_file(pdf)
    tei = None
    if os.path.exists(tei_path):
        with open(tei_path, "rb") as fh:
            tei = fh.read()
    doc = D.load(doc_path) if os.path.exists(doc_path) else None
    t0 = time.monotonic()
    canonical, dis, stats = R.reconcile(pdf, tei, doc, record, ocr_pages=record.get("ocr_pages") or ())
    classes = {i + 1: d.get("scan", "unknown") for i, d in enumerate(record.get("page_detail") or [])}
    regions = gold_regions(gold or {}, pdf_name)
    dropped = None
    if drop_page:
        before = R.coverage(pdf, canonical, classes)[drop_page]["share"]
        before_recall = _recall_on(canonical, regions, drop_page)
        canonical, dropped = drop_catch_all(canonical, drop_page)
        print(f"  planted: dropped {len(dropped)} body regions on page {drop_page} "
              f"(furniture kept); that page's coverage was {before:.4f}, recall {before_recall}")
    cov = R.coverage(pdf, canonical, classes)
    if drop_page:
        fails = R.coverage_failures(cov)
        after_recall = _recall_on(canonical, regions, drop_page)
        print(f"  after:   page {drop_page} coverage {cov[drop_page]['share']:.4f}, "
              f"floor {R.COVERAGE_FLOOR}, failures {fails}; recall {after_recall}")
        # §14's page gate is PER-REGION RECALL (referee 2026-09-15 §6). The character share is
        # kept beside it as the catastrophe detector it measurably is — on the referee's plant
        # it did not move by one character, because the removed paragraph's ink lay entirely
        # inside two surviving overlapping blocks.
        fired = False
        if regions.get(drop_page) and after_recall[0] < before_recall[0]:
            print(f"  KILL FIRED (recall): page {drop_page} lost regions "
                  f"{after_recall[2]}")
            fired = True
        if any(p == drop_page for p, _ in fails):
            print("  KILL FIRED (share): the coverage floor refuses the planted page")
            fired = True
        if not fired:
            raise SystemExit(f"KILL DID NOT FIRE: page {drop_page} passes both gates")
    seconds = round(time.monotonic() - t0, 2)
    recall = {}
    for page, regs in sorted(regions.items()):
        h, n, miss = _recall_on(canonical, regions, page)
        recall[page] = [h, n, miss]
    kinds = {}
    for d in dis:
        kinds[d.kind] = kinds.get(d.kind, 0) + 1
    row = {
        "tag": tag, "file": pdf_name, "pages": record.get("pages"), "route": record.get("route"),
        "tei": bool(tei), "docling": bool(doc), "seconds": seconds,
        "blocks": stats["blocks"], "matched": stats["matched"],
        "grobid_only": stats["grobid_only"], "docling_only": stats["docling_only"],
        "partial_overlap": kinds.get("partial_overlap", 0),
        "disagreements": stats["disagreements"], "skipped_rotated": stats["skipped_rotated"],
        "by_kind": json.dumps(stats["by_kind"], sort_keys=True),
        "coverage_by_page_type": json.dumps(
            {k: (None if v["share"] is None else round(v["share"], 4))
             for k, v in sorted(R.coverage_by_page_type(cov).items())}),
        "coverage_failures": len(R.coverage_failures(cov)),
        "figures": stats["by_kind"].get("figure", 0),
        "region_recall": json.dumps({p: f"{v[0]}/{v[1]}" for p, v in recall.items()}),
        "region_recall_missing": json.dumps({p: v[2] for p, v in recall.items() if v[2]}),
        "ingested_blocks": "", "run_id": "",
    }
    if db:
        res = _ingest_into(db, pdf, canonical, dis, stats, cov)
        row["ingested_blocks"] = res["blocks"]
        row["run_id"] = str(res["run_id"])
        row["disagreements"] = res["disagreements"]
    return row


def _recall_on(canonical, regions, page):
    regs = regions.get(page) or []
    return R.region_recall([c for c in canonical if c.page == page], regs)


def _ingest_into(db, pdf, canonical, dis, stats, cov):
    """Reconcile -> ingest into ONE database, as the stage-5 worker does (fix 9's re-run).

    A work and a file row are created for the PDF if it has none — this is a TEST database, and
    the point is the end-to-end path, not the admission. Never point this at `litkb`.
    """
    import uuid

    from psycopg.types.json import Jsonb

    from psycopg import sql

    from litkb.db import connect as c
    from litkb.extract import ingest as ing

    if not c.is_test_db(db):
        raise SystemExit(f"refusing to ingest into {db}: this instrument writes to litkb_test only")
    # the test database's own login, SET ROLE'd to litkb_ingest — exactly as the suite's harness
    # opens it (qc/test_litkb_p1.py::_PG.session). The real ingest login's passfile names `litkb`
    # and this instrument must never reach that database.
    setup = c.connect(db, "litkb_test", autocommit=True)
    conn = c.connect(db, "litkb_test", autocommit=True)
    conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier("litkb_ingest")))
    ws = setup.execute(
        "SELECT workstream_id FROM litkb.open_workstream(%s, 'work/stage5', NULL, "
        "'stage 5 re-run after the referee', NULL)",
        (f"s5-{uuid.uuid4().hex[:12]}",)).fetchone()[0]
    work_id = setup.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, "
        "'stage5', 'stage5')",
        (Jsonb({"key": f"Stagefive_2020_{uuid.uuid4().hex[:8]}-paper"}),
         Jsonb({"type": "article", "title": os.path.basename(pdf), "authors": []}), ws)
    ).fetchone()[0]
    file_id = setup.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, "
        "'stage5', 'stage5')",
        (Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         Jsonb({"work_id": str(work_id), "rel_path": "Validation/" + os.path.basename(pdf),
                "status": "active"}), ws)).fetchone()[0]
    pages = [{"page_no": p, "page_class": r["page_class"], "native_chars": r["chars"],
              "covered_chars": r["covered"], "coverage_share": r["share"]}
             for p, r in sorted(cov.items())]
    return ing.ingest_file(conn, file_id, canonical, dis, stats, pages=pages)


def main(argv=None):
    from phase4seg.names import clean_argv

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated tags")
    ap.add_argument("--tei-dir", default=TEI_DIR)
    ap.add_argument("--docling-dir", default=DOC_DIR)
    ap.add_argument("--csv")
    ap.add_argument("--drop-catch-all", type=int, metavar="PAGE",
                    help="the coverage KILL: remove the largest canonical block on this page of "
                         "the chosen file and require the gate to refuse the page")
    ap.add_argument("--gold", default=GOLD, help="the frozen referee gold, read-only")
    ap.add_argument("--db", help="also INGEST each file into this database (litkb_test* only)")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    gold = {}
    if a.gold and os.path.exists(a.gold):
        with open(a.gold, encoding="utf-8") as fh:
            gold = json.load(fh)

    chosen = set(a.only.split(",")) if a.only else None
    rows = []
    for tag, pdf_name, doc_name in FILES:
        if chosen and tag not in chosen:
            continue
        rows.append(one(tag, pdf_name, doc_name, a.tei_dir, a.docling_dir, a.drop_catch_all,
                        gold=gold, db=a.db))
        r = rows[-1]
        print(f"{r['tag']:<16} pages={r['pages']:<4} route={r['route']:<11} "
              f"tei={'y' if r['tei'] else 'n'} blocks={r['blocks']:<6} "
              f"matched={r['matched']:<5} dis={r['disagreements']:<6} {r['seconds']}s")
        print(f"{'':<16} kinds={r['by_kind']}")
        print(f"{'':<16} coverage={r['coverage_by_page_type']} failures={r['coverage_failures']}")
        print(f"{'':<16} figures={r['figures']} region_recall={r['region_recall']} "
              f"missing={r['region_recall_missing']}")
        if r["run_id"]:
            print(f"{'':<16} ingested blocks={r['ingested_blocks']} run={r['run_id']}")
    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)), exist_ok=True)
        with open(a.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

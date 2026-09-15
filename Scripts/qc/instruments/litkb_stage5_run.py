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
          "skipped_rotated", "by_kind", "coverage_by_page_type", "coverage_failures"]


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


def one(tag, pdf_name, doc_name, tei_dir, doc_dir, drop_page=None):
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
    dropped = None
    if drop_page:
        before = R.coverage(pdf, canonical, classes)[drop_page]["share"]
        canonical, dropped = drop_catch_all(canonical, drop_page)
        print(f"  planted: dropped {len(dropped)} body regions on page {drop_page} "
              f"(furniture kept); that page's coverage was {before:.4f}")
    cov = R.coverage(pdf, canonical, classes)
    if drop_page:
        fails = R.coverage_failures(cov)
        print(f"  after:   page {drop_page} coverage {cov[drop_page]['share']:.4f}, "
              f"floor {R.COVERAGE_FLOOR}, failures {fails}")
        if not any(p == drop_page for p, _ in fails):
            raise SystemExit(f"KILL DID NOT FIRE: page {drop_page} still passes the coverage gate")
        print("  KILL FIRED: the coverage gate refuses the planted page")
    seconds = round(time.monotonic() - t0, 2)
    kinds = {}
    for d in dis:
        kinds[d.kind] = kinds.get(d.kind, 0) + 1
    return {
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
    }


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
    a = ap.parse_args(clean_argv() if argv is None else argv)

    chosen = set(a.only.split(",")) if a.only else None
    rows = []
    for tag, pdf_name, doc_name in FILES:
        if chosen and tag not in chosen:
            continue
        rows.append(one(tag, pdf_name, doc_name, a.tei_dir, a.docling_dir, a.drop_catch_all))
        r = rows[-1]
        print(f"{r['tag']:<16} pages={r['pages']:<4} route={r['route']:<11} "
              f"tei={'y' if r['tei'] else 'n'} blocks={r['blocks']:<6} "
              f"matched={r['matched']:<5} dis={r['disagreements']:<6} {r['seconds']}s")
        print(f"{'':<16} kinds={r['by_kind']}")
        print(f"{'':<16} coverage={r['coverage_by_page_type']} failures={r['coverage_failures']}")
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

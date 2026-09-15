"""The equation-density census — one row per page of the literature corpus.

Kam's decision A (2026-09-15): formula enrichment is 160x slower than layout, so it runs on
EQUATION-DENSE PAGES ONLY. This instrument computes
:func:`litkb.extract.docling.equation_density` over every page of every PDF in the corpus and
writes the distribution the threshold is chosen from (CLAUDE.md §3.4b: a finding needs the
script that produced it).

    py -3.12 qc/instruments/litkb_equation_density.py            # census + histogram
    py -3.12 qc/instruments/litkb_equation_density.py --cut 0.12 # what that cut selects

SCOPE, stated because the corpus has more directories than the census reads: ``ASPP``,
``Labeling``, ``Validation`` and ``other`` under ``D:\\edmonds-pipeline\\Literture``.
``_litkb_staging`` and ``_quarantine`` are EXCLUDED — staging is a copy of files that are
already counted and quarantine is files that failed ingest, so both would double-count or
poison the distribution.

``D:\\edmonds-pipeline\\Literture`` is READ-ONLY to this instrument; the CSV is written to
``Reports/``.

WHAT IT REFUSES: a PDF that pypdfium2 cannot open is recorded as a row with ``status`` set
to the error and no pages — never skipped silently, because a corpus census with files
quietly missing from it is not a census.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.extract import docling as D  # noqa: E402

LIT = os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture")
SUBDIRS = ("ASPP", "Labeling", "Validation", "other")

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
CSV_PATH = os.path.join(_REPO, "Reports", "litkb_equation_density_2026-09-15.csv")

FIELDS = ["subdir", "file", "page", "pages_in_file", "page_chars", "density", "status"]

#: Histogram edges. Fine below 0.2 because that is where the prose/maths boundary sits and
#: the cut has to be read off it; coarse above, where everything is display maths anyway.
EDGES = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20,
         0.30, 0.50, 0.75, 1.01]


def corpus_pdfs(root=LIT, subdirs=SUBDIRS):
    """[(subdir, path)] for every PDF in the census scope, sorted."""
    out = []
    for sub in subdirs:
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for dirpath, _dirnames, files in os.walk(d):
            for f in sorted(files):
                if f.lower().endswith(".pdf"):
                    out.append((sub, os.path.join(dirpath, f)))
    return sorted(out)


def census(root=LIT, subdirs=SUBDIRS, progress=None):
    rows = []
    pdfs = corpus_pdfs(root, subdirs)
    for i, (sub, path) in enumerate(pdfs, 1):
        name = os.path.basename(path)
        if progress:
            progress(i, len(pdfs), name)
        try:
            dens = D.page_densities(path)
        except Exception as e:  # noqa: BLE001 - the failure IS part of the census
            rows.append({"subdir": sub, "file": name, "page": "", "pages_in_file": "",
                         "page_chars": "", "density": "",
                         "status": f"{type(e).__name__}: {e}"})
            continue
        for page, d, chars in dens:
            rows.append({"subdir": sub, "file": name, "page": page,
                         "pages_in_file": len(dens), "page_chars": chars,
                         "density": round(d, 5), "status": "ok"})
    return rows


def histogram(values, edges=EDGES):
    """[(lo, hi, count)] — closed-open bins over the density values."""
    out = []
    for lo, hi in zip(edges, edges[1:]):
        out.append((lo, hi, sum(1 for v in values if lo <= v < hi)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--cut", type=float, default=D.EQUATION_DENSITY_CUT)
    ap.add_argument("--root", default=LIT)
    a = ap.parse_args(argv)

    def prog(i, n, name):
        print(f"[{i}/{n}] {name}", flush=True)

    rows = census(a.root, progress=prog)
    os.makedirs(os.path.dirname(os.path.abspath(a.csv)), exist_ok=True)
    with open(a.csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if r["status"] == "ok"]
    vals = [float(r["density"]) for r in ok]
    bad = [r for r in rows if r["status"] != "ok"]
    notext = [v for r, v in zip(ok, vals) if not r["page_chars"]]
    print(f"\n{len(set((r['subdir'], r['file']) for r in rows))} PDFs, {len(ok)} pages, "
          f"{len(bad)} unreadable, {len(notext)} pages with no text layer")
    print(f"\n{'bin':>14}  {'pages':>7}  {'%':>6}")
    for lo, hi, n in histogram(vals):
        print(f"[{lo:.2f},{hi:.2f})  {n:7d}  {100 * n / max(1, len(vals)):6.2f}")
    sel = [v for v in vals if v > a.cut]
    print(f"\ncut {a.cut}: {len(sel)} of {len(vals)} pages selected "
          f"({100 * len(sel) / max(1, len(vals)):.2f}%)")
    for r in bad:
        print("UNREADABLE", r["file"], r["status"])
    print(a.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

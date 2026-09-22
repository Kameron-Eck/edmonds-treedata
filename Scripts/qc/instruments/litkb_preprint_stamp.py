"""litkb S4 carry-in — the bioRxiv/medRxiv stamp strip (`binding._PREPRINT_STAMP`), measured per page
on the base's real bioRxiv file.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_preprint_stamp.py

WHY. `litkb.admit.binding.title_text` strips a LEADING preprint stamp off each printed line before
a title window is scored (register E25, Kam's ruling 2026-09-21). Its arXiv branch was measured on
the two refused arXiv files; the bioRxiv/medRxiv branch (`_PREPRINT_STAMP`) had been tested on
CONSTRUCTED lines only (`qc/test_litkb_binding_stamps.py`). The S4 block names the measurement:
E21's preprint (`litkb-sibling-edition`) is the base's ONE bioRxiv file — the census query under
the block's "Test-set commands" (DOI prefix ``10.1101/``) — and this reads its ``main_files.rel_path``
from the live database (as ``litkb_reader``) rather than composing it.

WHAT IS MEASURED, PER PAGE:

  * ``stamp_present`` — an INDEPENDENT detector. The page's text as **pypdfium2** reads it (a
    different extractor from the binding's `pdftotext -layout`, and no line structure at all),
    whitespace collapsed and casefolded, contains BOTH the word ``biorxiv``/``medrxiv`` AND the
    file's own ``10.1101/`` DOI as the database holds it. Nothing about the regex's grammar
    (line-anchored, "preprint … this version posted <Month> <d>, <yyyy>") enters it.
  * ``regex_hit`` — the page read the way the binding reads page 1 (`pdftotext -f N -l N -layout`,
    the arguments of `binding.first_page_text`, then `binding.page_lines`), and ``_PREPRINT_STAMP``
    matched at the START of at least one line — exactly where `title_text` applies it.
    ``chars_stripped`` is what `title_text` removed from those lines; ``regex_search_anywhere`` is
    the same regex searched over the whole page, so a miss can be told apart as "the stamp is not at
    a line start" vs "the stamp's words differ from the grammar".
  * page 1 only: the best 1-3 line title window against the work's registry title, scored on the
    STRIPPED lines (`binding.best_window`) and on the PRINTED lines, so the strip's effect on this
    file's own binding ratio is a number, not an inference.

THE READER DEPENDS ON PATH. `binding.first_page_text` runs a bare ``pdftotext``; on this machine
two different programs answer to that name (xpdf 4.00 under Git's ``mingw64/bin`` and poppler
25.07 from winget), and which one a litkb process gets depends on the PATH it was launched with.
So every page is read by EVERY distinct ``pdftotext`` on PATH and each row names its program and
version. The ratio is reported per program.

Output: ``phase4/qc/litkb_preprint_stamp.csv`` (columns :data:`COLUMNS`); the finding paragraph
lives in the S4 run-3 builder-D1 report. Reads only: the PDF is never moved or written, page text
goes to a temporary directory, and the database is read as ``litkb_reader``.
"""
import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
OUT = REPO / "phase4" / "qc" / "litkb_preprint_stamp.csv"

COLUMNS = ["rel_path", "pdftotext", "pdftotext_version", "page", "stamp_present",
           "detector_word", "detector_doi", "regex_hit", "regex_hit_lines", "chars_stripped",
           "regex_search_anywhere", "lines_on_page", "first_line_printed", "first_line_scored",
           "p1_best_ratio_scored", "p1_best_ratio_printed"]


def pdftotext_programs():
    """Every distinct `pdftotext` on PATH, in PATH order (the first is the one a bare call gets)."""
    seen, out = set(), []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = shutil.which("pdftotext", path=d) if d else None
        if p:
            real = os.path.normcase(os.path.realpath(p))
            if real not in seen:
                seen.add(real)
                out.append(p)
    return out


def pdftotext_path():
    """The program a bare ``pdftotext`` resolves to — what `binding.first_page_text` runs."""
    return shutil.which("pdftotext")


def program_version(prog):
    try:
        r = subprocess.run([prog, "-v"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "?"
    text = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"pdftotext version (\S+)", text)
    return m.group(1) if m else "?"


def page_text(pdf, page, prog="pdftotext"):
    """`pdftotext -f N -l N -layout` — `binding.first_page_text`'s arguments, for page N."""
    with tempfile.TemporaryDirectory(prefix="litkb_stamp_") as d:
        out = Path(d) / "p.txt"
        subprocess.run([prog, "-f", str(page), "-l", str(page), "-layout", str(pdf), str(out)],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""


def pdfium_texts(pdf):
    """Every page's text as pypdfium2 reads it — the independent detector's input."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    out = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            tp = page.get_textpage()
            try:
                out.append(tp.get_text_range())
            finally:
                tp.close()
                page.close()
    finally:
        doc.close()
    return out


def page_count(pdf):
    from litkb.extract.probe import probe_pages

    return probe_pages(pdf)


def detect(text, doi):
    """The independent detector: -> (present, word_found, doi_found)."""
    flat = " ".join((text or "").split()).casefold()
    word = ("biorxiv" in flat) or ("medrxiv" in flat)
    doi_found = bool(doi) and doi.casefold() in flat
    return word and doi_found, word, doi_found


def _best_printed(title, lines):
    from litkb.admit.resolver import title_match_ratio

    best = 0.0
    for i in range(len(lines)):
        for n in (1, 2, 3):
            if i + n > len(lines):
                break
            best = max(best, title_match_ratio(title, " ".join(lines[i:i + n])))
    return best


def measure(pdf, *, doi, title=None, rel_path="", programs=None):
    """-> one row per (pdftotext program, page) for `pdf`."""
    from litkb.admit import binding as B

    programs = programs or [pdftotext_path() or "pdftotext"]
    detector = pdfium_texts(pdf)
    rows = []
    for prog in programs:
        version = program_version(prog)
        for page in range(1, len(detector) + 1):
            text = page_text(pdf, page, prog)
            lines = B.page_lines(text)
            collapsed = [" ".join(ln.split()) for ln in lines]
            hits = [ln for ln in collapsed if B._PREPRINT_STAMP.match(ln)]
            stripped = sum(len(ln) - len(B.title_text(ln)) for ln in hits)
            present, word, doi_found = detect(detector[page - 1], doi)
            row = {"rel_path": rel_path, "pdftotext": prog, "pdftotext_version": version,
                   "page": page, "stamp_present": present, "detector_word": word,
                   "detector_doi": doi_found, "regex_hit": bool(hits), "regex_hit_lines": len(hits),
                   "chars_stripped": stripped,
                   "regex_search_anywhere": bool(B._PREPRINT_STAMP.search(" ".join(collapsed))),
                   "lines_on_page": len(lines),
                   "first_line_printed": (collapsed[0] if collapsed else "")[:160],
                   "first_line_scored": (B.title_text(collapsed[0]) if collapsed else "")[:160],
                   "p1_best_ratio_scored": "", "p1_best_ratio_printed": ""}
            if page == 1 and title:
                row["p1_best_ratio_scored"] = round(B.best_window(title, text)[0], 4)
                row["p1_best_ratio_printed"] = round(_best_printed(title, collapsed), 4)
            rows.append(row)
    return rows


def summarise(rows):
    """-> {program: {"stamped", "stripped", "ratio", "misses": [page, ...], "false_hits": [...]}}."""
    out = {}
    for r in rows:
        s = out.setdefault(r["pdftotext"], {"version": r["pdftotext_version"], "pages": 0,
                                            "stamped": 0, "stripped": 0, "misses": [],
                                            "false_hits": []})
        s["pages"] += 1
        if r["stamp_present"]:
            s["stamped"] += 1
            if r["regex_hit"]:
                s["stripped"] += 1
            else:
                s["misses"].append(r["page"])
        elif r["regex_hit"]:
            s["false_hits"].append(r["page"])
    return out


def _live_target(db):
    """(rel_path, doi, title) of the base's bioRxiv file(s), read as litkb_reader."""
    from litkb.db import connect as c

    conn = c.connect(db, "litkb_reader", autocommit=True)
    try:
        return conn.execute(
            "SELECT f.rel_path, i.value_norm, w.title FROM litkb.main_identifiers i "
            "JOIN litkb.main_works w ON w.work_id = i.work_id "
            "JOIN litkb.main_files f ON f.work_id = w.work_id AND f.status = 'active' "
            "WHERE i.scheme = 'doi' AND i.active AND i.status = 'active' "
            "AND i.value_norm LIKE %s ORDER BY f.rel_path", ("10.1101/%",)).fetchall()
    finally:
        conn.close()


def main(argv=None):
    from litkb.acquire.store import LITERATURE_ROOT
    from litkb.db import connect as c

    ap = argparse.ArgumentParser(description="measure the bioRxiv stamp strip per page")
    ap.add_argument("--db", default=c.DB_MAIN)
    ap.add_argument("--root", default=str(LITERATURE_ROOT))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    targets = _live_target(a.db)
    if not targets:
        print("no bioRxiv/medRxiv (10.1101/) file is held in main")
        return 1
    programs = pdftotext_programs()
    rows = []
    for rel, doi, title in targets:
        pdf = Path(a.root) / rel.replace("/", os.sep)
        rows += measure(pdf, doi=doi, title=title, rel_path=rel, programs=programs)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"files={len(targets)} programs={len(programs)} rows={len(rows)} -> {a.out}")
    for prog, s in summarise(rows).items():
        print(f"  {prog} (pdftotext {s['version']}): pages carrying the stamp={s['stamped']}/{s['pages']}  "
              f"stripped by the regex={s['stripped']}/{s['stamped']}  misses={s['misses']}  "
              f"regex hits with no stamp={s['false_hits']}")
    p1 = [r for r in rows if r["page"] == 1 and r["p1_best_ratio_scored"] != ""]
    for r in p1:
        print(f"  page 1 best title window ({r['pdftotext_version']}): scored {r['p1_best_ratio_scored']}  "
              f"printed {r['p1_best_ratio_printed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

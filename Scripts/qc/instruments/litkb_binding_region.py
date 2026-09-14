"""litkb P2 referee fix D2: where, on REAL first pages, the title window and the first author sit.

The referee (Reports/LITKB_P2_REFEREE_2026-09-14.md, D2) showed binding accepts a title found anywhere on page 1
(a reference list, a "please cite" cover) and an author found as any substring. The fix restricts the title to
the page's title region and requires the surname as a whole token near the title. The two constants that rule
needs (how many lines count as the title region, how far the author may sit from the title) are MEASURED here,
on every held paper whose title and first author are recorded, never assumed.

Inputs, read only (nothing under the literature root is written; pdftotext writes to a temporary directory):
  * Validation/manifest.csv rows with a PDF on disk (title, first author from `authors`);
  * the files filed by the P2 gate (_litkb_staging/filed/<key>.pdf) with their registry title and first author
    from litkb main_works, opened as litkb_reader with default_transaction_read_only.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_binding_region.py

Writes Reports/litkb_binding_region_2026-09-14.csv (one row per PDF) and prints the distribution.
"""
import csv
import os
import re
import sys
from pathlib import Path

from litkb.admit import binding
from litkb.admit.front import first_author_of
from litkb.admit.resolver import _ascii_fold, _norm_text, family_name, strip_tags, title_match_ratio

SCRIPTS = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture"))
OUT = SCRIPTS.parent / "Reports" / "litkb_binding_region_2026-09-14.csv"


def rows():
    with open(ROOT / "Validation" / "manifest.csv", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            pdf = ROOT / "Validation" / f"{r['stem']}.pdf"
            if pdf.exists() and r.get("title") and r.get("authors"):
                yield "Validation", pdf, r["title"], first_author_of(r["authors"])
    try:
        from litkb.db import connect as c
        conn = c.connect(c.DB_MAIN, "litkb_reader", autocommit=True)
    except Exception as e:  # the database is optional for this measurement
        print(f"litkb not readable ({type(e).__name__}); filed papers skipped", file=sys.stderr)
        return
    conn.execute("SET default_transaction_read_only = on")
    for key, title, authors in conn.execute("SELECT key, title, authors FROM litkb.main_works ORDER BY key").fetchall():
        pdf = ROOT / "_litkb_staging" / "filed" / f"{key}.pdf"
        if pdf.exists():
            first = (authors[0].get("family") or "") if authors else ""
            yield "filed", pdf, title, first
    conn.close()


def old_rule(title, first, text, info):
    """The P2 rule the referee refused (b2e10a7 binding.py), kept here only to count what the fix changes: the
    best window anywhere on page 1 or the PDF Title, and the surname as a substring of the squashed page."""
    fam = family_name(first) if first else ""

    def on(s):
        folded = _ascii_fold(strip_tags(s)).lower()
        if not fam:
            return False
        if len(fam) >= 4:
            return fam in re.sub(r"[^0-9a-z]+", "", folded)
        return re.search(r"(?<![0-9a-z])" + re.escape(fam) + r"(?![0-9a-z])", _norm_text(folded)) is not None
    ratio, _w = binding.best_window(title, text)
    if info.get("Title"):
        ratio = max(ratio, title_match_ratio(title, info["Title"]))
    ok = ratio >= binding.BIND_RATIO and (on(text) or on(info.get("Author") or ""))
    return {"verdict": "bound" if ok else "not-bound"}


def main():
    out = []
    for src, pdf, title, first in rows():
        text = binding.first_page_text(pdf)
        info = binding.pdf_info(pdf)
        lines = binding.page_lines(text)
        ratio, i, n = 0.0, -1, 0
        for s in range(len(lines)):
            for k in (1, 2, 3):
                if s + k > len(lines):
                    break
                r = title_match_ratio(title, " ".join(lines[s:s + k]))
                if r > ratio:
                    ratio, i, n = r, s, k
        meta_ratio = title_match_ratio(title, info.get("Title") or "") if info.get("Title") else 0.0
        fam = binding.surname_tokens(first)
        author_lines = [j for j, ln in enumerate(lines) if binding.tokens_contain(binding.fold_tokens(ln), fam)]
        dist = ""
        if i >= 0 and author_lines:
            dist = min(0 if i <= j < i + n else (i - j if j < i else j - (i + n - 1)) for j in author_lines)
        old = old_rule(title, first, text, info)
        new = binding.bind(pdf, title, first, page_text=text, info=info)
        out.append({"source": src, "pdf": pdf.name, "first_author": first, "n_lines": len(lines),
                    "page_ratio": round(ratio, 4), "title_line": i, "title_lines": n,
                    "meta_title_ratio": round(meta_ratio, 4),
                    "author_line_first": author_lines[0] if author_lines else "",
                    "author_title_distance": dist, "meta_author_token": binding.tokens_contain(
                        binding.fold_tokens(info.get("Author") or ""), fam),
                    "old_verdict": old["verdict"], "new_verdict": new["verdict"], "new_reason": new.get("reason", "")})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    bound_old = [r for r in out if r["old_verdict"] == "bound"]
    print(f"{len(out)} PDFs; bound under the old rule: {len(bound_old)}; under the new rule: "
          f"{sum(r['new_verdict'] == 'bound' for r in out)}")
    page = [r for r in bound_old if r["page_ratio"] >= binding.BIND_RATIO]
    print("old-bound with a page-1 title window: title_line max", max((r["title_line"] for r in page), default=None),
          "| distribution", sorted(r["title_line"] for r in page))
    d = sorted(r["author_title_distance"] for r in page if r["author_title_distance"] != "")
    print("author distance from the title window:", d)
    lost = [(r["pdf"], r["new_reason"]) for r in bound_old if r["new_verdict"] != "bound"]
    print(f"bound before, not bound now: {len(lost)}")
    for x in lost:
        print("  ", x)


if __name__ == "__main__":
    main()

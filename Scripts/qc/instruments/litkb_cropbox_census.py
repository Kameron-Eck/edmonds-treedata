"""Every page's cropbox shift, RAW and clamped — the measurement behind `inventory._frame`'s clamp.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_cropbox_census.py
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_cropbox_census.py --only Higham_2011,Efron_1986

WHY THIS EXISTS. `page_frames` reports `dy = media.y1 - crop.y1`, and a `/CropBox` that extends PAST
the `/MediaBox` makes that NEGATIVE. No renderer shows that region — PDF 32000-1 §14.11.2 has a
viewer intersect the two boxes — so the page pypdfium2 measures characters on, and the page Docling
lays out, is the intersection: the effective shift is 0 and the raw negative moves every block off
its own text. `Reports/LITKB_P5_BULK_2026-09-16.md` §6.2 traced all sixteen cropped-page coverage
failures of the 225-document bulk pass to that one line, and blocker #2 asked for the clamp.

A clamp is a claim about the CORPUS, not about two files: "no page needs a negative shift, and the
269 pages that are already fine are untouched." This instrument is what makes that checkable, and
it is also the evidence for the half of the fix that was deliberately NOT made — `dx` is not
clamped, because no page with a negative `dx` has been measured and a gate with no failing input
behind it has never been shown to fire (CLAUDE.md §3.4c).

Reads the frozen stage-0 census (`inventory.load_census`) so the population is the same one every
pinned stage-0 number was measured over, not a walk that drifts. Opens PDFs read-only; writes one
CSV; touches no database.

Output: `phase4/qc/litkb_cropbox_census.csv`, one row per FILE —

    relpath, pages, cropped_pages, rotated_pages, min_dx_raw, min_dy_raw, max_dy_raw,
    pages_dx_negative, pages_dy_negative, dy_clamped_pages, worst_dy_page

`*_raw` are computed here from the mediabox and cropbox `page_frames` returns, not from its `dy`:
the point is the difference between what the arithmetic gives and what the clamp stores, and a
census that read the clamped value could not see it.
"""
import argparse
import csv
import os
import pathlib
import sys
import time

#: parents[2] is `Scripts` (this file is qc/instruments/…), so parents[3] is the repo root that
#: holds the tracked `phase4/qc/` measured-text directory.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2]
OUT_DEFAULT = SCRIPTS.parent / "phase4" / "qc" / "litkb_cropbox_census.csv"

COLUMNS = ["relpath", "pages", "cropped_pages", "rotated_pages", "min_dx_raw", "min_dy_raw",
           "max_dy_raw", "pages_dx_negative", "pages_dy_negative", "dy_clamped_pages",
           "worst_dy_page"]


def _raw_shift(frame):
    """(dx, dy) as the arithmetic gives them, from the boxes the frame reader returned."""
    media, crop = frame["mediabox"], frame["cropbox"]
    return round(crop[0] - media[0], 4), round(media[3] - crop[3], 4)


def measure(pdf_path, relpath, page_frames):
    frames = page_frames(pdf_path)
    dxs, dys, cropped, rotated = [], [], 0, 0
    worst_page, worst_dy = None, 0.0
    for page, f in sorted(frames.items()):
        dx, dy = _raw_shift(f)
        dxs.append(dx)
        dys.append(dy)
        if dx or dy:
            cropped += 1
        if f["rotation"]:
            rotated += 1
        if dy < worst_dy:
            worst_dy, worst_page = dy, page
    return {
        "relpath": relpath, "pages": len(frames), "cropped_pages": cropped,
        "rotated_pages": rotated,
        "min_dx_raw": min(dxs) if dxs else "", "min_dy_raw": min(dys) if dys else "",
        "max_dy_raw": max(dys) if dys else "",
        "pages_dx_negative": sum(1 for d in dxs if d < 0),
        "pages_dy_negative": sum(1 for d in dys if d < 0),
        "dy_clamped_pages": sum(1 for d in dys if d < 0),
        "worst_dy_page": worst_page if worst_page is not None else "",
    }


def run(only=None, root=None):
    from litkb.extract import inventory

    root = root or inventory.DEFAULT_ROOT
    rows, skipped = [], []
    for _sha, relpath in inventory.load_census():
        if only and not any(o.lower() in relpath.lower() for o in only):
            continue
        path = os.path.join(str(root), relpath.replace("\\", os.sep))
        if not os.path.exists(path):
            skipped.append(relpath)
            continue
        try:
            rows.append(measure(path, relpath, inventory.page_frames))
        except Exception as e:                        # noqa: BLE001 — a census records the refusal
            skipped.append(f"{relpath}: {type(e).__name__}: {e}")
    return rows, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description="per-page cropbox shift census, raw vs clamped")
    ap.add_argument("--only", default="", help="comma-separated substrings of relpaths to measure")
    ap.add_argument("--root", default=None, help="literature root (default: the module's)")
    ap.add_argument("--out", default=None, help="output CSV (default phase4/qc/…)")
    a = ap.parse_args(argv)

    t0 = time.time()
    rows, skipped = run([s.strip() for s in a.only.split(",") if s.strip()] or None, a.root)
    out = a.out or str(OUT_DEFAULT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    neg_dy = [r for r in rows if r["pages_dy_negative"]]
    neg_dx = [r for r in rows if r["pages_dx_negative"]]
    print(f"{len(rows)} files, {sum(r['pages'] for r in rows)} pages, "
          f"{sum(r['cropped_pages'] for r in rows)} cropped, "
          f"{sum(r['rotated_pages'] for r in rows)} rotated, {time.time() - t0:.1f} s")
    print(f"negative dy: {len(neg_dy)} files, "
          f"{sum(r['pages_dy_negative'] for r in neg_dy)} pages "
          f"-> clamped to 0 by inventory._frame")
    for r in sorted(neg_dy, key=lambda r: r["min_dy_raw"]):
        print(f"    {r['relpath']}  pages {r['pages_dy_negative']}/{r['pages']}  "
              f"min dy {r['min_dy_raw']}  worst page {r['worst_dy_page']}")
    print(f"negative dx: {len(neg_dx)} files "
          f"({sum(r['pages_dx_negative'] for r in neg_dx)} pages) — dx is NOT clamped")
    if skipped:
        print(f"skipped {len(skipped)}: {skipped[:5]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Render the 20 gold-equation crops from source PDFs for the pix2tex evaluation.

Runs in the MAIN worktree venv (has psycopg + pypdfium2 already). Queries litkb (live DB,
read-only, litkb_reader) for each gold equation_id's block_id to fetch the real source
rel_path, page_no, canonical bbox and the stored CodeFormula latex -- exactly what
Reports/gold/p5_gold_2026-09-16.json's block_id + inventory.page_frames need, no guessing.

Crop convention: canonical bbox is TOP-LEFT-of-MEDIABOX frame (gold's own _selection note).
inventory.page_frames() gives the per-page (dx, dy) cropbox shift the SAME frame reader the
rest of litkb uses. Render the page with pypdfium2 at scale S; pixel rect =
((l-dx)*S, (t-dy)*S, (r-dx)*S, (b-dy)*S), expanded by 18% of box width/height on each side
(the same expansion_factor formula_crop_worker.py documents for the real CodeFormula crop),
clamped to the rendered image bounds.
"""
import json
import os
import sys

REPO = r"D:\edmonds-pipeline\treedata-pix2tex"
sys.path.insert(0, os.path.join(REPO, "Scripts", "pipeline"))

import psycopg
import pypdfium2 as pdfium
from PIL import Image

from litkb.extract.inventory import page_frames

LIT_ROOT = r"D:\edmonds-pipeline\Literture"
GOLD_PATH = os.path.join(REPO, "Reports", "gold", "p5_gold_2026-09-16.json")
OUT_DIR = os.path.join(REPO, "Scripts", "scratch", "pix2tex_eval", "crops_gold")
SCALE = 4.0
EXPAND = 0.18


def conn():
    return psycopg.connect("host=localhost port=5433 dbname=litkb user=litkb_reader", autocommit=True)


def main():
    gold = json.load(open(GOLD_PATH, encoding="utf-8"))
    eq = gold["equation_ids"]
    c = conn()
    rows = []
    for eid, v in eq.items():
        bid = v["block_id"]
        row = c.execute(
            """SELECT mf.rel_path, b.page_no, b.bbox, b.latex, e.latex_status
                 FROM litkb.blocks b
                 JOIN litkb.extraction_runs er ON er.id = b.run_id
                 JOIN litkb.main_files mf ON mf.file_id = er.file_id
                 LEFT JOIN litkb.equations e ON e.block_id = b.id
                WHERE b.id = %s""", (bid,)).fetchone()
        if row is None:
            print(f"{eid}: NO DB ROW for block_id {bid}")
            continue
        rel_path, page_no, bbox, cf_latex, latex_status = row
        pdf_path = os.path.join(LIT_ROOT, rel_path.replace("/", os.sep))
        if not os.path.exists(pdf_path):
            print(f"{eid}: PDF NOT FOUND {pdf_path}")
            continue
        frames = page_frames(pdf_path)
        fr = frames[page_no]
        dx, dy = fr["dx"], fr["dy"]
        l, t, r, b = bbox
        dw = (r - l) * EXPAND
        dh = (b - t) * EXPAND
        l2, t2, r2, b2 = l - dw, t - dh, r + dw, b + dh
        doc = pdfium.PdfDocument(pdf_path)
        page = doc[page_no - 1]
        bitmap = page.render(scale=SCALE)
        pil = bitmap.to_pil()
        px = ((l2 - dx) * SCALE, (t2 - dy) * SCALE, (r2 - dx) * SCALE, (b2 - dy) * SCALE)
        px = (max(0, px[0]), max(0, px[1]), min(pil.width, px[2]), min(pil.height, px[3]))
        crop = pil.crop(tuple(round(v_) for v_ in px))
        os.makedirs(OUT_DIR, exist_ok=True)
        out_path = os.path.join(OUT_DIR, f"{eid}.png")
        crop.save(out_path)
        doc.close()
        rows.append({
            "id": eid, "block_id": bid, "rel_path": rel_path, "page": page_no,
            "bbox": bbox, "dx": dx, "dy": dy, "codeformula_latex": cf_latex,
            "latex_status": latex_status, "gold_reading": v["reading"],
            "crop_path": out_path, "crop_size": list(crop.size),
        })
        print(f"{eid}: {rel_path} p{page_no} dx={dx} dy={dy} crop={crop.size} -> {out_path}")
    c.close()
    out_json = os.path.join(OUT_DIR, "..", "gold_equations_joined.json")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False, default=str)
    print(f"\nwrote {len(rows)} rows -> {out_json}")


if __name__ == "__main__":
    main()

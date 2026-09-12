"""One-off OCR helper for the two scanned Laserfiche PDFs the lidar-records investigation needs
read: ila-1462454 (2021 Edmonds/Snohomish orthoimagery ILA) and kc2015-aerials-ila-1465848
(2015 King County regional aerials ILA). Both are images-only PDFs; pypdf/PyMuPDF text
extraction returns near-nothing because there is no text layer.

Renders each page with PyMuPDF (pymupdf) at ~220 DPI (Windows.Media.Ocr's OcrEngine has a
MaxImageDimension around 2600-4000px depending on Windows build; 220 DPI keeps a US Letter page
under that) and OCRs each page image with the built-in Windows OCR engine via `winocr`
(winocr.recognize_pil_sync). No Tesseract install needed.

Usage: py -3.12 qc/ocr_scanned_pdf.py <raw-pdf-path> <output-txt-path>
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import winocr


def ocr_pdf(pdf_path: Path, out_path: Path, dpi: int = 220) -> None:
    doc = pymupdf.open(pdf_path)
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    pages_text = []
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(png_bytes))
        result = winocr.recognize_pil_sync(img, lang="en-US")
        text = result.get("text", "") if isinstance(result, dict) else str(result)
        pages_text.append(f"=== PAGE {i} ===\n{text}")
        print(f"  page {i}/{len(doc)}: {len(text)} chars", flush=True)
    out_path.write_text("\n\n".join(pages_text), encoding="utf-8")
    print(f"wrote {out_path} ({sum(len(p) for p in pages_text)} chars total)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: py -3.12 qc/ocr_scanned_pdf.py <raw-pdf-path> <output-txt-path>")
    ocr_pdf(Path(sys.argv[1]), Path(sys.argv[2]))

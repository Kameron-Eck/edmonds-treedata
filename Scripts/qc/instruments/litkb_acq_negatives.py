"""The S4.5 acceptance test's CONSTRUCTED negatives (LITKB_WORKPLAN.md "### S4.5", Test set: "NEGATIVE,
CONSTRUCTED — ... because the base holds none of them"). Every file this writes is CONSTRUCTED, says so in
its name, and is described in qc/testdata/litkb_acq_negatives/README.md.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acq_negatives.py --check   # committed == built
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acq_negatives.py --write   # (re)write them

The bytes are DETERMINISTIC (no timestamp, no random id), so `--check` — and qc/test_litkb_accept.py — can
prove each committed fixture is exactly what this file builds. `--write` refuses to replace a file whose bytes
differ from the build unless `--force`: a fixture that changes changes every verdict recorded against it.

The four negatives and the verdict each must get from `litkb.acquire.accept.accept`:
  CONSTRUCTED_bom_valid_article.pdf        a valid 3-page article PDF behind a UTF-8 byte-order mark -> ACCEPT
                                            after the header repair (and `missing_pdf_header` without it)
  CONSTRUCTED_tdm_stub_first_page.pdf      a one-page first-page-only response, padded past the 5,000-byte
                                            floor, served with the CONSTRUCTED header in its .headers.json
                                            -> `stub_not_article` (chars_no_refs + x_els_status)
  CONSTRUCTED_proceedings_volume_60p.pdf   60 pages whose first 12 are the requested paper, offered for a
                                            record whose page range is VOLUME_RECORD_PAGES (12 pages)
                                            -> `volume_not_article`
  CONSTRUCTED_cites_requested_doi.pdf      a 5-page report whose bibliography (page 5) prints CITED_DOI
                                            -> `cited_document_not_this_article` when CITED_DOI is requested
  CONSTRUCTED_scan_no_text_layer.pdf       a scanned article as an archive serves one: a text cover sheet, then
                                            SCAN_IMAGE_PAGES image-only pages (no text layer; <3,000
                                            characters, no reference heading) -> ACCEPT: the stub rule
                                            abstains on image pages (decision D13; auditor-C1b F1 — the shape
                                            of Anderson_1957 / Hudson_1978 / Hwang_1982, and of Ogata_1998
                                            without its cover)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS / "qc" / "testdata" / "litkb_acq_negatives"

BOM = b"\xef\xbb\xbf"
TDM_TITLE = "CONSTRUCTED negative: a first-page TDM stub of a canopy article"
TDM_AUTHOR = "Stubauthor"
#: A CONSTRUCTED header value: H2-RG says Elsevier announces a first-page-only PDF in X-ELS-Status, and the
#: real wording was never recorded by litkb, so this value is invented and says so.
TDM_HEADERS = {"X-ELS-Status": "WARNING - CONSTRUCTED value: first page only (the real wording is unrecorded)",
               "Content-Type": "application/pdf"}
VOLUME_TITLE = "CONSTRUCTED negative: the opening paper of a proceedings volume"
VOLUME_AUTHOR = "Volumeauthor"
VOLUME_RECORD_PAGES = "101-112"
CITED_DOI = "10.5555/litkb-constructed-requested-0001"
CITING_TITLE = "CONSTRUCTED negative: a municipal tree report that cites the requested article"
BOM_TITLE = "CONSTRUCTED negative: a valid article PDF served after a byte-order mark"
SCAN_TITLE = "CONSTRUCTED negative: a scanned article with no text layer after its cover sheet"
SCAN_AUTHOR = "Scanauthor"
#: Image-only pages after the cover (MEASURED by builder-C1b 2026-09-23 through the acceptance test: the real
#: scans hold 10, 11, 21 and 24 image pages; five is enough to be a document, small enough to stay a fixture).
#: One raster image per page, like the scans' 1-18 (`litkb.extract.probe`'s docstring, decision D13).
SCAN_IMAGE_PAGES = 5
#: Pixels per side of each page's image (8-bit gray, uncompressed so the bytes never depend on a zlib build).
SCAN_IMAGE_SIDE = 64

_PROSE = ("Canopy cover was mapped from leaf-on aerial imagery and checked against field plots; the "
          "constructed sentence repeats so the page carries text.")


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(pages, *, pad=0, note=""):
    """A hand-written PDF: one page per list of lines, Helvetica 9 pt, one xref, no timestamp. `pad` adds an
    UNREFERENCED stream object of that many filler bytes (no page shows it); `note` a comment after %%EOF."""
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    kids, n = [], 4
    for lines in pages:
        content = ("BT /F1 9 Tf 40 760 Td 11 TL " + " ".join(f"({_esc(ln)}) '" for ln in lines) + " ET")
        data = content.encode("latin-1")
        objs[n] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                   b"/Contents " + f"{n + 1} 0 R".encode() + b" >>")
        objs[n + 1] = b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream"
        kids.append(f"{n} 0 R")
        n += 2
    if pad:
        filler = (b"% CONSTRUCTED padding: an unreferenced stream no page shows.\n" * (pad // 60 + 1))[:pad]
        objs[n] = b"<< /Length " + str(len(filler)).encode() + b" >>\nstream\n" + filler + b"\nendstream"
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for k in sorted(objs):
        offsets[k] = len(out)
        out += f"{k} 0 obj\n".encode() + objs[k] + b"\nendobj\n"
    xref, size = len(out), max(objs) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for k in range(1, size):
        out += (f"{offsets[k]:010d} 00000 n \n" if k in offsets else "0000000000 65535 f \n").encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    if note:
        out += f"% {note}\n".encode()
    return bytes(out)


def scan_pdf(cover_lines, n_images, *, side=SCAN_IMAGE_SIDE, note=""):
    """A hand-written PDF: page 1 a text cover sheet (Helvetica 9 pt), then `n_images` pages that each draw ONE
    uncompressed 8-bit gray image over the whole page and carry no text at all — the shape of a scanned article
    an archive serves. One xref, no timestamp; the pixels are a fixed arithmetic pattern."""
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    content = ("BT /F1 9 Tf 40 760 Td 11 TL " + " ".join(f"({_esc(ln)}) '" for ln in cover_lines) + " ET")
    data = content.encode("latin-1")
    objs[4] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
               b"/Contents 5 0 R >>")
    objs[5] = b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream"
    kids, n = ["4 0 R"], 6
    draw = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
    for k in range(n_images):
        pixels = bytes((x * 7 + y * 13 + k * 29) % 256 for y in range(side) for x in range(side))
        objs[n] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 "
                   + f"{n + 2} 0 R".encode() + b" >> >> /Contents " + f"{n + 1} 0 R".encode() + b" >>")
        objs[n + 1] = b"<< /Length " + str(len(draw)).encode() + b" >>\nstream\n" + draw + b"\nendstream"
        objs[n + 2] = (b"<< /Type /XObject /Subtype /Image /Width " + str(side).encode() + b" /Height "
                       + str(side).encode() + b" /ColorSpace /DeviceGray /BitsPerComponent 8 /Length "
                       + str(len(pixels)).encode() + b" >>\nstream\n" + pixels + b"\nendstream")
        kids.append(f"{n} 0 R")
        n += 3
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for k in sorted(objs):
        offsets[k] = len(out)
        out += f"{k} 0 obj\n".encode() + objs[k] + b"\nendobj\n"
    xref, size = len(out), max(objs) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for k in range(1, size):
        out += f"{offsets[k]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    if note:
        out += f"% {note}\n".encode()
    return bytes(out)


def _body(tag, n):
    return [f"{tag} {i + 1}. {_PROSE}" for i in range(n)]


def _refs(extra=()):
    return (["", "References", ""] + [f"[{i}] Author{i}, A. ({2000 + i}). A constructed reference number {i}. "
                                     f"J. Constructed Studies {i}, {i}-{i + 9}." for i in range(1, 11)]
            + list(extra))


def bom_article():
    """CONSTRUCTED: a valid 3-page article (>3,000 characters, a References section) behind a UTF-8 BOM."""
    p1 = ["Journal of Constructed Studies 1 (2099) 1-3", BOM_TITLE, "A. Constructor and B. Fixture", "",
          "Abstract"] + _body("Page one sentence", 30)
    p2 = _body("Page two sentence", 45)
    p3 = _body("Page three sentence", 10) + _refs()
    return BOM + text_pdf([p1, p2, p3], note="CONSTRUCTED litkb_acq_negatives bom_valid_article")


def tdm_stub():
    """CONSTRUCTED: one first page (title, authors, abstract; <3,000 characters, no references), padded past
    the 5,000-byte floor the way a real publisher first page is by its fonts."""
    p1 = ["Remote Sensing of Constructed Environments 999 (2099) 101-112", TDM_TITLE,
          f"C. {TDM_AUTHOR} and D. Firstpage", "", "Abstract"] + _body("Abstract sentence", 8)
    return text_pdf([p1], pad=8000, note="CONSTRUCTED litkb_acq_negatives tdm_stub_first_page")


def proceedings_volume():
    """CONSTRUCTED: a 60-page proceedings volume whose first 12 pages are the requested paper."""
    pages = [["Proceedings of the CONSTRUCTED Workshop on Canopy Mapping 2099, pages 101-112", VOLUME_TITLE,
              f"E. {VOLUME_AUTHOR} and F. Proceedings", ""] + _body("Opening paper page 1 sentence", 30)]
    pages += [_body(f"Opening paper page {k} sentence", 40) for k in range(2, 12)]
    pages += [_body("Opening paper page 12 sentence", 10) + _refs()]
    for k in range(13, 61):
        pages.append([f"CONSTRUCTED other paper opening on volume page {k}", ""]
                     + _body(f"Other paper page {k} sentence", 38))
    return text_pdf(pages, note="CONSTRUCTED litkb_acq_negatives proceedings_volume_60p")


def cites_requested_doi():
    """CONSTRUCTED: a 5-page report whose only print of CITED_DOI is in its bibliography on page 5."""
    p1 = ["City of Constructed Falls, Urban Forestry Division, 2099", CITING_TITLE, "G. Citingauthor", ""] \
        + _body("Report page 1 sentence", 30)
    mid = [_body(f"Report page {k} sentence", 40) for k in (2, 3, 4)]
    p5 = _body("Report page 5 sentence", 8) + _refs(
        [f"[11] Requested, R. (2020). The requested article. J. Constructed 1, 1-10. https://doi.org/{CITED_DOI}"])
    return text_pdf([p1, *mid, p5], note="CONSTRUCTED litkb_acq_negatives cites_requested_doi")


def scan_no_text_layer():
    """CONSTRUCTED: a scanned article — a JSTOR-style text cover sheet (under 200 characters, like the real
    scans' 147-160) and SCAN_IMAGE_PAGES image-only pages; under 3,000 characters, no reference heading."""
    cover = ["CONSTRUCTED cover sheet", SCAN_TITLE, f"Author(s): H. {SCAN_AUTHOR}",
             "Source: The Annals of Constructed Statistics, Vol. 1 (2099), pp. 89-94"]
    return scan_pdf(cover, SCAN_IMAGE_PAGES, note="CONSTRUCTED litkb_acq_negatives scan_no_text_layer")


BUILDERS = {"CONSTRUCTED_bom_valid_article.pdf": bom_article,
            "CONSTRUCTED_tdm_stub_first_page.pdf": tdm_stub,
            "CONSTRUCTED_proceedings_volume_60p.pdf": proceedings_volume,
            "CONSTRUCTED_cites_requested_doi.pdf": cites_requested_doi,
            "CONSTRUCTED_scan_no_text_layer.pdf": scan_no_text_layer}
HEADERS = {"CONSTRUCTED_tdm_stub_first_page.headers.json": TDM_HEADERS}


def built():
    """{file name: bytes} for every negative (the PDFs, and the TDM stub's header record as JSON text)."""
    out = {name: fn() for name, fn in BUILDERS.items()}
    for name, h in HEADERS.items():
        out[name] = (json.dumps(h, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="write the negatives into qc/testdata/litkb_acq_negatives/")
    ap.add_argument("--force", action="store_true", help="with --write: replace a fixture whose bytes differ")
    ap.add_argument("--check", action="store_true", help="compare the committed PDFs with a fresh build")
    a = ap.parse_args(argv)
    bad = 0
    for name, data in built().items():
        p = OUT / name
        sha = hashlib.sha256(data).hexdigest()
        if a.write:
            if p.exists() and p.read_bytes() != data and not a.force and name.endswith(".pdf"):
                print(f"REFUSED {name}: the committed bytes differ from the build (pass --force)")
                bad += 1
                continue
            OUT.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            print(f"wrote {name} {len(data)} bytes sha256={sha}")
        elif name.endswith(".pdf"):
            same = p.exists() and p.read_bytes() == data
            bad += not same
            print(f"{'OK  ' if same else 'DIFF'} {name} {len(data)} bytes sha256={sha}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

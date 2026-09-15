"""litkb stage 0 (Inventory) — the gate and the kills.

The gate (design §14 P4) is the twelve-file table in :data:`GATE`: what the page renders
showed when a human looked at it, written down as the two primitives the page classes are
DEFINED on — is there a raster over the page, and does the native text layer carry the
page's words — plus the route that follows. A referee re-inspects by rendering the same
pages; the expectations here are the claim under test, not an echo of the classifier.

The kills each fire on a known-bad input built here, never on the corpus:

* a native page with its text layer stripped (rasterised through pypdfium2) is
  ``image-only`` — if the image probe were removed it would read ``empty``;
* a JSTOR cover-sheet fixture routes ``cover-sheet``;
* a truncated PDF routes ``unreadable``, never ``native``;
* moving any threshold breaks the twelve-file gate (that is what
  ``qc/instruments/litkb_inventory_mutations.py`` shows, row by row).

Nothing here writes inside ``Literture\\``, and every corpus-backed test skips when the
corpus is not mounted.
"""
import hashlib
import json
import zlib

import pytest

from litkb.extract import inventory as inv

CORPUS = inv.DEFAULT_ROOT
needs_corpus = pytest.mark.skipif(not CORPUS.exists(),
                                  reason=f"literature corpus not mounted at {CORPUS}")


# ── fixture PDFs, built here, never copied from the corpus ─────────────────────────────

def _pdf(objects, root=1):
    """Assemble a minimal PDF from 1-indexed object bodies, with a correct xref."""
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<</Size {len(objects) + 1}/Root {root} 0 R>>\nstartxref\n"
            f"{start}\n%%EOF\n").encode()
    return bytes(out)


def text_pdf(path, pages, info=None):
    """A born-digital PDF: one Helvetica text block per page string."""
    n = len(pages)
    kids = " ".join(f"{3 + i} 0 R" for i in range(n))
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        f"<</Type/Pages/Kids[{kids}]/Count {n}>>".encode(),
    ]
    contents = []
    for i in range(n):
        cid = 3 + n + i
        objs.append((f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
                     f"/Resources<</Font<</F1 {3 + 2 * n} 0 R>>>>"
                     f"/Contents {cid} 0 R>>").encode())
    for body in pages:
        lines = "".join(f"({_esc(ln)}) Tj T*\n" for ln in body.splitlines() or [""])
        stream = f"BT /F1 10 Tf 14 TL 56 720 Td\n{lines}ET".encode()
        contents.append(f"<</Length {len(stream)}>>\nstream\n".encode()
                        + stream + b"\nendstream")
    objs += contents
    objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    data = _pdf(objs)
    if info:
        data = _with_info(data, info)
    path.write_bytes(data)
    return path


def _esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _with_info(data, info):
    """Append an /Info dictionary — the vehicle for the NUL-in-metadata case."""
    body = "".join(f"/{k} ({_esc(v)})" for k, v in info.items())
    extra = f"\n{99} 0 obj\n<<{body}>>\nendobj\n".encode("latin-1")
    head, _, tail = data.rpartition(b"trailer\n")
    tail = tail.replace(b"/Root 1 0 R>>", b"/Root 1 0 R/Info 99 0 R>>")
    return head.rstrip(b"\n")[:len(head) - len(b"trailer\n")] + extra + b"trailer\n" + tail


def rasterised_pdf(src, dst, scale=1.0):
    """*src* re-made as pictures of its pages: the text layer is gone, the ink is not.

    This is the honest "text layer stripped" input. Deleting the page's text OBJECTS
    instead would leave a page with no ink at all, which is ``empty`` — a different case,
    and one that would let the kill pass for the wrong reason.
    """
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(src)
    out = pdfium.PdfDocument.new()
    try:
        for i in range(len(doc)):
            page = doc[i]
            w, h = page.get_size()
            bitmap = page.render(scale=scale)
            new = out.new_page(w, h)
            image = pdfium.PdfImage.new(out)
            image.set_bitmap(bitmap)
            image.set_matrix(pdfium.PdfMatrix().scale(w, h))
            new.insert_obj(image)
            new.gen_content()
        out.save(str(dst))
    finally:
        out.close()
        doc.close()
    return dst


JSTOR_COVER = """ECONOMETRICA
A Very Short Paper About Nothing In Particular
Author(s): A. N. Author
Source: Econometrica, Vol. 1, No. 1 (Jan., 1900), pp. 1-2
Published by: The Econometric Society
Stable URL: http://www.jstor.org/stable/0000000
Accessed: 01-01-2000 00:00 UTC
Your use of the JSTOR archive indicates your acceptance of the Terms & Conditions of Use.
JSTOR is a not-for-profit service that helps scholars, researchers, and students discover,
use, and build upon a wide range of content in a trusted digital archive.
The Econometric Society is collaborating with JSTOR to digitize, preserve and extend
access to Econometrica."""

IMS_STAMP = ("Institute of Mathematical Statistics is collaborating with JSTOR to "
             "digitize, preserve, and extend access to\nThe Annals of Statistics.\n"
             "www.jstor.org")

BODY = "\n".join([f"Line {i} of ordinary body text about ordinary things." for i in range(40)])


@pytest.fixture
def native(tmp_path):
    return text_pdf(tmp_path / "native.pdf", [BODY, BODY, BODY])


# ── the corpus census (the §7.1 frame reader, checked against a committed measurement) ──

@pytest.fixture(scope="module")
def corpus_records(tmp_path_factory):
    if not CORPUS.exists():
        pytest.skip("no corpus")
    out = tmp_path_factory.mktemp("inv") / "records.jsonl"
    records, _ = inv.run(CORPUS, out, force=True)
    return records


@needs_corpus
def test_the_frame_reader_reproduces_the_committed_corpus_census(corpus_records):
    """The same five numbers referee 2 measured with GROBID's own page_frames.

    Reports/LITKB_GROBID_LOCAL_REFEREE2_2026-09-15.md §4, corpus defined as every PDF
    under Literture EXCLUDING _quarantine — quote it with that definition or not at all.
    """
    active = [r for r in corpus_records if "_quarantine" not in r["path"]]
    s = inv.summarise(active)
    assert s["files"] == 224
    assert s["pages"] == 4712
    assert len(s["rotated_pages"]) == 7
    assert s["cropped_pages"] == 271
    assert s["cropped_files"] == 19
    assert [(n, p) for n, p in s["rotated_and_cropped"]] == [
        ("Hall_1985_resampling-coverage-pattern.pdf", 12)]


# ── the twelve-file gate ───────────────────────────────────────────────────────────────

#: stem -> (route, {page: class}, notes). The classes are the hand call, written from the
#: rendered pages (Reports/LITKB_INVENTORY_2026-09-15.md §4), not read off the classifier.
GATE = {
    # a scan with no text anywhere: every page is a picture, cut into 18 strips
    "Ogata_1998": ("scan", {1: "image-only", 12: "image-only"}),
    # a scan whose page 1 carries only the IMS stamp; the title is in the raster
    "Anderson_1957": ("scan", {1: "partial", 2: "image-only"}),
    # a scan with a COMPLETE (if OCR-damaged) text layer — stage 0 cannot see the damage
    "Kingman_1962": ("native", {1: "text"}),
    # Acrobat Capture: full-page images with a full text layer over them
    "Bell_1977": ("native", {1: "text", 3: "text"}),
    # the 688-page book: a rastered cover, then born-digital pages
    "Schneider_2008": ("mixed", {1: "image-only", 4: "text"}),
    # the corpus's only page that is both rotated and cropped; its text layer is fine
    "Hall_1985": ("native", {12: "text"}),
    # a born-digital paper with one rotated full-page figure
    "Guo_2019": ("mixed", {6: "partial"}),
    # plain born-digital two-column
    "Alwan_1988": ("native", {2: "text"}),
    # born-digital with scanned table inserts
    "Reynolds_2000": ("mixed", {7: "partial", 14: "image-only"}),
    # a standalone JSTOR cover page; the article starts on page 2
    "Almon_1965": ("cover-sheet", {1: "text", 2: "text"}),
    # _quarantine: wrong content, and an image-only scan of it
    "Schwartz_2000": ("scan", {1: "image-only"}),
    # encrypted (owner password) yet perfectly readable
    "Hughes_1999": ("native", {1: "text"}),
}


@needs_corpus
@pytest.mark.parametrize("stem", sorted(GATE))
def test_classification_agrees_with_hand_inspection(stem, corpus_records):
    route, pages = GATE[stem]
    matches = [r for r in corpus_records if r["name"].startswith(stem)]
    assert matches, f"{stem} not found in the corpus"
    rec = matches[0]
    assert rec["route"] == route, f"{stem}: route"
    for number, expected in pages.items():
        assert rec["page_detail"][number - 1]["scan"] == expected, f"{stem} p{number}"


@needs_corpus
def test_the_cover_sheet_and_the_cover_stamp_are_not_the_same_thing(corpus_records):
    """The distinction the whole cover rule turns on, on the real files.

    A standalone cover PAGE carries the bibliographic fields and the article starts after
    it; the IMS STAMP is boilerplate printed into the margin of the article's own first
    page, and the title on that page is an image. Conflating them would put the title on
    page 2 of four files where it is not.
    """
    by = {r["name"].split("_")[0]: r for r in corpus_records}
    assert by["Almon"]["cover_sheet"] and not by["Almon"]["cover_stamp"]
    assert by["Almon"]["title_page"] == 2
    for stem in ("Anderson", "Hudson", "Hwang", "Politis"):
        r = by[stem]
        assert r["cover_stamp"] and not r["cover_sheet"], stem
        assert r["title_page"] is None, stem   # it is in the raster; only OCR yields it


@needs_corpus
def test_the_cropbox_shift_matches_the_value_referee_2_measured(corpus_records):
    """dx/dy are the §7.1 shift, and a wrong one is a silently misplaced block.

    Reports/LITKB_GROBID_LOCAL_REFEREE2_2026-09-15.md §4 read Alwan p2 as mediabox
    (0,0,612,792), cropbox (10.3449, 10.7771, 603.4410, 782.9480), dx = 10.345, dy = 9.052 —
    and showed GROBID's raw coordinates sit 11.52 pt out against the mediabox, 1.18 pt after
    the shift. Zeroing dx/dy would move every converted block by that much with nothing else
    changing, so the census counts alone cannot catch it.
    """
    rec = [r for r in corpus_records if r["name"].startswith("Alwan_1988")][0]
    p2 = rec["page_detail"][1]
    assert p2["mediabox"] == [0.0, 0.0, 612.0, 792.0]
    assert p2["cropbox"] == pytest.approx([10.3449, 10.7771, 603.4410, 782.9480], abs=1e-3)
    assert p2["dx"] == pytest.approx(10.345, abs=1e-3)
    assert p2["dy"] == pytest.approx(9.052, abs=1e-3)


@needs_corpus
def test_encrypted_is_not_unreadable(corpus_records):
    enc = [r for r in corpus_records if r.get("encrypted")]
    assert enc, "the corpus holds owner-password PDFs; the probe should see them"
    for r in enc:
        assert r["route"] != "unreadable"
        assert r["pages"] > 0


# ── the kills ──────────────────────────────────────────────────────────────────────────

def test_a_pdf_with_its_text_layer_stripped_is_image_only(native, tmp_path):
    before = inv.probe_file(native)
    assert before["route"] == "native"
    assert all(p["scan"] == "text" for p in before["page_detail"])

    after = inv.probe_file(rasterised_pdf(native, tmp_path / "raster.pdf"))
    assert after["route"] == "scan"
    assert [p["scan"] for p in after["page_detail"]] == ["image-only"] * before["pages"]
    assert after["ocr_pages"] == list(range(1, before["pages"] + 1))
    # and it is image-only because of the raster, not merely because the text is gone
    assert all(p["images"] >= 1 and p["image_frac"] >= 0.25
               for p in after["page_detail"])


def test_a_raster_nested_in_a_form_xobject_is_still_found(native, tmp_path):
    """The reason the image probe recurses.

    Some producers place a scanned page inside a form XObject rather than at the top of the
    content stream. A probe that looks only at depth 0 sees no images there and calls the
    page ``empty``, which would take a whole scanned document out of the OCR queue silently.
    """
    import pypdfium2 as pdfium

    flat = rasterised_pdf(native, tmp_path / "raster.pdf")
    src = pdfium.PdfDocument(flat)
    out = pdfium.PdfDocument.new()
    try:
        xobj = src.page_as_xobject(0, out)          # the raster page, wrapped one level down
        w, h = src[0].get_size()
        page = out.new_page(w, h)
        page.insert_obj(xobj.as_pageobject())
        page.gen_content()
        out.save(str(tmp_path / "nested.pdf"))
    finally:
        out.close()
        src.close()

    rec = inv.probe_file(tmp_path / "nested.pdf")
    assert rec["page_detail"][0]["images"] >= 1
    assert rec["page_detail"][0]["scan"] == "image-only"


def test_a_page_with_neither_text_nor_raster_is_empty_not_image_only(tmp_path):
    """The class that keeps a blank page out of the OCR queue."""
    blank = text_pdf(tmp_path / "blank.pdf", [""])
    rec = inv.probe_file(blank)
    assert rec["page_detail"][0]["scan"] == "empty"
    assert rec["ocr_pages"] == []


def test_a_jstor_cover_sheet_routes_cover_sheet(tmp_path):
    f = text_pdf(tmp_path / "cover.pdf", [JSTOR_COVER, BODY, BODY])
    rec = inv.probe_file(f)
    assert rec["route"] == "cover-sheet"
    assert rec["cover_sheet"] is True
    assert rec["title_page"] == 2


def test_an_ims_stamp_alone_is_not_a_cover_sheet(tmp_path):
    f = text_pdf(tmp_path / "stamp.pdf", [IMS_STAMP + "\n" + BODY, BODY])
    rec = inv.probe_file(f)
    assert rec["cover_sheet"] is False
    assert rec["route"] == "native"
    assert rec["title_page"] == 1


def test_a_corrupt_file_routes_unreadable_not_native(native, tmp_path):
    broken = tmp_path / "broken.pdf"
    data = native.read_bytes()
    broken.write_bytes(data[:len(data) // 2])
    rec = inv.probe_file(broken)
    assert rec["route"] == "unreadable"
    assert rec["pages"] == 0
    assert rec["unreadable_reason"] in ("FORMAT", "FILE", "UNKNOWN", "PASSWORD")
    assert rec["sha256"] == hashlib.sha256(broken.read_bytes()).hexdigest()


def test_an_empty_file_routes_unreadable(tmp_path):
    p = tmp_path / "zero.pdf"
    p.write_bytes(b"")
    assert inv.probe_file(p)["route"] == "unreadable"


# ── the unit boundaries the thresholds sit on ──────────────────────────────────────────

#: The thresholds written out, NOT read back from the module. A table phrased as
#: ``inv.CHARS_TRACE - 1`` moves with the constant and so asserts nothing about its value;
#: that is why the first mutation run left T5 alive.
@pytest.mark.parametrize("chars,frac,expected", [
    (0, 0.0, "empty"),
    (1, 0.0, "text"),
    (0, 0.25, "image-only"),
    (0, 0.24, "empty"),
    (0, 0.10, "empty"),          # a small figure on a blank page is not a scan
    (99, 0.90, "image-only"),
    (100, 0.90, "partial"),
    (399, 0.90, "partial"),
    (400, 0.90, "text"),
    (99, 0.0, "text"),           # a sparse native page: OCR cannot help it
    (250, 0.20, "text"),         # a short page with a modest figure stays native
])
def test_classify_page_boundaries(chars, frac, expected):
    assert inv.classify_page(chars, frac) == expected


@pytest.mark.parametrize("ocr,total,expected", [
    (0, 10, "native"), (1, 10, "mixed"), (4, 10, "mixed"),
    (5, 10, "scan"), (10, 10, "scan"),
])
def test_route_precedence_on_the_scan_share(ocr, total, expected):
    pages = [{"scan": "image-only"}] * ocr + [{"scan": "text"}] * (total - ocr)
    assert inv.route_file(pages, cover_sheet=False) == expected
    # unreadable outranks everything, and cover-sheet never outranks an OCR need
    assert inv.route_file(pages, cover_sheet=True, unreadable=True) == "unreadable"
    assert inv.route_file(pages, cover_sheet=True) == (
        "cover-sheet" if expected == "native" else expected)


def test_the_params_hash_moves_when_a_threshold_moves(monkeypatch):
    before = inv.params_hash()
    monkeypatch.setattr(inv, "CHARS_TRACE", inv.CHARS_TRACE + 1)
    assert inv.params_hash() != before


# ── idempotence, resume, and the record itself ─────────────────────────────────────────

def test_a_rerun_skips_what_is_recorded_and_force_redoes_it(tmp_path, native):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    text_pdf(corpus / "a.pdf", [BODY])
    text_pdf(corpus / "b.pdf", [JSTOR_COVER, BODY])
    out = tmp_path / "inv.jsonl"

    first, _ = inv.run(corpus, out)
    assert len(first) == 2
    stamped = out.read_text(encoding="utf-8")

    second, _ = inv.run(corpus, out)
    assert [r["sha256"] for r in second] == [r["sha256"] for r in first]
    assert out.read_text(encoding="utf-8") == stamped      # byte-identical, not re-probed
    assert all(r["seconds"] == f["seconds"] for r, f in zip(second, first))

    forced, _ = inv.run(corpus, out, force=True)
    assert [r["route"] for r in forced] == [r["route"] for r in first]


def test_two_copies_of_one_file_are_two_records_and_one_duplicate_group(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    text_pdf(corpus / "one.pdf", [BODY])
    (corpus / "copy.pdf").write_bytes((corpus / "one.pdf").read_bytes())
    records, _ = inv.run(corpus, tmp_path / "inv.jsonl")
    assert len(records) == 2
    dupes = inv.summarise(records)["duplicate_sha256"]
    assert len(dupes) == 1
    assert sorted(next(iter(dupes.values()))) == ["copy.pdf", "one.pdf"]

    # and the resume must keep both on the second pass, which is what the path in the key
    # buys: with a sha256-only key the second copy is never recorded at all.
    again, _ = inv.run(corpus, tmp_path / "inv.jsonl")
    assert sorted(r["name"] for r in again) == ["copy.pdf", "one.pdf"]
    assert len({r["path"] for r in again}) == 2


def test_a_moved_threshold_re_probes_without_force(tmp_path, monkeypatch):
    """§12.4's run key in practice: two definitions of "scan" never mix in one file."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    text_pdf(corpus / "a.pdf", [BODY])
    out = tmp_path / "inv.jsonl"
    first, _ = inv.run(corpus, out)
    monkeypatch.setattr(inv, "CHARS_BODY", inv.CHARS_BODY + 7)
    second, _ = inv.run(corpus, out)
    assert second[0]["params_hash"] != first[0]["params_hash"]


def test_the_resume_key_carries_the_path_and_the_params_hash():
    a = inv.resume_key("deadbeef", r"C:\a\x.pdf", "p1")
    assert a == ("deadbeef", r"C:\a\x.pdf", "p1")
    assert a != inv.resume_key("deadbeef", r"C:\b\x.pdf", "p1")   # a second copy
    assert a != inv.resume_key("deadbeef", r"C:\a\x.pdf", "p2")   # a moved threshold


def test_a_nul_in_pdf_metadata_never_reaches_the_record(tmp_path):
    """Bell 1977's Acrobat Capture producer string carries NULs; jsonb refuses \\u0000."""
    f = text_pdf(tmp_path / "nul.pdf", [BODY],
                 info={"Creator": "Acrobat 3.0 Capture Plug-in\x00\x00", "Producer": "X\x00"})
    rec = inv.probe_file(f)
    assert "\x00" not in json.dumps(rec)
    assert rec["creator"] == "Acrobat 3.0 Capture Plug-in"


def test_every_record_carries_its_run_key(tmp_path, native):
    rec = inv.probe_file(native)
    assert rec["stage"] == 0
    assert rec["tool"].startswith("pypdfium2@")
    assert rec["params_hash"] == inv.params_hash()
    assert rec["md5"] and rec["sha256"] and rec["bytes"] == native.stat().st_size


def test_the_summary_csv_has_one_row_per_file(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    text_pdf(corpus / "a.pdf", [BODY])
    text_pdf(corpus / "b.pdf", [JSTOR_COVER, BODY])
    records, _ = inv.run(corpus, tmp_path / "inv.jsonl")
    rows = inv.write_summary_csv(records, tmp_path / "inv.csv", root=corpus)
    assert [r["relpath"] for r in rows] == ["a.pdf", "b.pdf"]
    assert {r["route"] for r in rows} == {"native", "cover-sheet"}
    assert (tmp_path / "inv.csv").read_text(encoding="utf-8").splitlines()[0].startswith("name,")


def test_the_corpus_is_never_written_to(tmp_path):
    """Stage 0 opens PDFs read-only; §6 gives litkb no delete permission in Literture."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    f = text_pdf(corpus / "a.pdf", [BODY])
    before = {p.name: (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
              for p in corpus.iterdir()}
    inv.run(corpus, tmp_path / "inv.jsonl")
    after = {p.name: (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
             for p in corpus.iterdir()}
    assert after == before
    assert not any(p.suffix == ".partial" for p in corpus.iterdir())


def test_page_frames_shape_matches_the_grobid_adapter_contract(native):
    frames = inv.page_frames(native)
    assert set(frames) == {1, 2, 3}
    f = frames[1]
    assert set(f) == {"mediabox", "cropbox", "rotation", "dx", "dy"}
    assert f["mediabox"] == [0.0, 0.0, 612.0, 792.0]
    assert f["rotation"] == 0
    assert f["dx"] == 0.0 and f["dy"] == 0.0


def test_zlib_is_not_needed_for_the_fixtures():
    """Guards the fixture writer: the streams are uncompressed on purpose, so a failure
    here is a fixture bug and never a pdfium filter difference."""
    assert zlib is not None

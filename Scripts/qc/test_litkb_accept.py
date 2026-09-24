"""litkb S4.5 builder-C1b: THE acceptance test (litkb.acquire.accept), its CONSTRUCTED negatives and E20's REAL
preview, a sidecar on every quarantine, the sidecar backfill, and the four (c) known-bads of this builder's
counters (qc/instruments/litkb_hardening_c1b.py) — each fire run here as a test, control arm AND known-bad arm.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_accept.py -q -p no:cacheprovider

No test here touches the network or the live store: every Store is rooted in a pytest tmp dir."""
import gzip
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
NEG = SCRIPTS / "qc" / "testdata" / "litkb_acq_negatives"
FIX = SCRIPTS / "qc" / "fixtures"
pg_only = pytest.mark.requires_litkb_pg

#: The S4.5 CONTRACTS `bad-file` list, in its order (D:\tools\claude-config\jobs\litkb-s4-5\brief-CONTRACTS.md,
#: "The sub_status vocabulary"). accept.SUB_STATUSES must be exactly this.
CONTRACTS_BAD_FILE = ("html_response", "too_small", "missing_pdf_header", "corrupt_pdf_header",
                      "early_eof_with_trailing_payload", "stub_not_article", "volume_not_article",
                      "cited_document_not_this_article", "compressed_or_archived_payload")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "qc" / "instruments" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


N = _load("litkb_acq_negatives")
H = _load("litkb_hardening_c1b")


def _neg(name):
    return (NEG / name).read_bytes()


def _e20():
    prov = json.loads((FIX / "litkb_e20_preview.provenance.json").read_text(encoding="utf-8"))
    return (FIX / "litkb_e20_preview.pdf").read_bytes(), prov


def _article(extra_lines=(), doi_line=None):
    """A valid article PDF with no BOM: the CONSTRUCTED BOM article's own builder, BOM stripped."""
    data = N.bom_article()[len(N.BOM):]
    if doi_line:
        pages = [["Journal of Constructed Studies 1 (2099) 1-3", N.BOM_TITLE, doi_line, ""] + N._body("p1", 30),
                 N._body("p2", 45), N._body("p3", 10) + N._refs()]
        data = N.text_pdf(pages)
    return data


# ── the vocabulary, the fixtures ──────────────────────────────────────────────────────────

def test_the_sub_statuses_are_the_contracts_bad_file_list():
    from litkb.acquire import accept as A
    assert A.SUB_STATUSES == CONTRACTS_BAD_FILE


def test_store_and_quarantine_read_the_same_sidecar_suffix():
    from litkb import quarantine as Q
    from litkb.acquire import store as S
    assert S.SIDECAR_SUFFIX == Q.SIDECAR_SUFFIX == ".reason.json"


def test_the_constructed_negatives_are_exactly_what_their_builder_makes():
    """Deterministic bytes: every committed negative is its builder's output, and says CONSTRUCTED in its name
    (and its builder's docstring). A fixture that changed would change every verdict recorded against it."""
    built = N.built()
    on_disk = sorted(p.name for p in NEG.iterdir() if p.suffix in (".pdf", ".json"))
    assert on_disk == sorted(built), on_disk
    for name, data in built.items():
        assert name.startswith("CONSTRUCTED_"), name
        if name.endswith(".pdf"):
            assert _neg(name) == data, name
            assert "CONSTRUCTED" in N.BUILDERS[name].__doc__
        else:
            assert json.loads(_neg(name)) == json.loads(data)
    assert (NEG / "README.md").is_file()


def test_the_e20_fixture_is_the_recorded_real_bytes():
    data, prov = _e20()
    assert hashlib.sha256(data).hexdigest() == prov["sha256"] and len(data) == prov["bytes"]
    assert data.startswith(b"%PDF-1.4") and prov["status"] == 200 and prov["content_type"] == "application/pdf"
    assert "?" not in prov["terminal_url"], "the signed query (an AWS session token) must not be recorded"


# ── the verdict on each negative (the plan's Test set) ─────────────────────────────────────

def test_a_valid_pdf_behind_a_bom_passes_after_the_repair():
    from litkb.acquire import accept as A
    v = A.accept(_neg("CONSTRUCTED_bom_valid_article.pdf"))
    assert (v.verdict, v.sub_status) == ("accept", None), v.summary()
    assert v.facts["repaired_offset"] == 3 and v.pdf.startswith(b"%PDF-1.4") and v.pdf == _neg(
        "CONSTRUCTED_bom_valid_article.pdf")[3:]
    assert v.facts["served_bytes"] == len(v.pdf) + 3


def test_the_bom_caveat_fires_with_the_repair_removed(monkeypatch):
    """(c) known-bad: the header repair removed -> the BOM PDF is refused missing_pdf_header, because
    bytes.lstrip() does not strip a byte-order mark (survey-design "Item 5"). Control AND known-bad arms."""
    assert H.fire_bom_repair(None, "control", None) == 0
    assert H.fire_bom_repair(None, "known_bad", None) == 1
    from litkb.acquire import accept as A
    assert A.accept(_neg("CONSTRUCTED_bom_valid_article.pdf")).verdict == "accept", "the fire did not restore"


def test_a_first_page_tdm_stub_is_stub_not_article_by_both_signals():
    from litkb.acquire import accept as A
    hdr = json.loads(_neg("CONSTRUCTED_tdm_stub_first_page.headers.json"))
    v = A.accept(_neg("CONSTRUCTED_tdm_stub_first_page.pdf"), headers=hdr)
    assert (v.verdict, v.sub_status) == ("refuse", "stub_not_article"), v.summary()
    assert v.facts["stub_signals"] == ["chars_no_refs", "x_els_status"]
    assert len(_neg("CONSTRUCTED_tdm_stub_first_page.pdf")) >= A.MIN_PDF_BYTES, "the stub must reach the stub rule"


def test_the_x_els_status_header_alone_marks_a_stub_and_ok_does_not():
    """A full article (the char rule passes) served with a non-OK X-ELS-Status is a stub; `OK` — the value the
    Elsevier probe MEASURED on a normal 200 — is not."""
    from litkb.acquire import accept as A
    art = _article()
    assert A.accept(art).verdict == "accept"
    v = A.accept(art, headers={"x-els-status": "WARNING - CONSTRUCTED"})
    assert (v.sub_status, v.facts["stub_signals"]) == ("stub_not_article", ["x_els_status"])
    assert A.accept(art, headers={"X-ELS-Status": "OK"}).verdict == "accept"


def test_e20s_real_preview_is_stub_not_article_by_its_terminal_url_and_not_by_its_bytes():
    """The plan's NEGATIVE, REAL row: E20's own citation_pdf_url serves a 47-page preview of the book. Its bytes
    alone are a well-formed 47-page document with a bibliography — no byte rule here refuses it (a stated limit);
    the terminal URL the server redirected to (`.../relatedobjects/preview.pdf`) is what types it."""
    from litkb.acquire import accept as A
    data, prov = _e20()
    v = A.accept(data, url=prov["url_requested"], terminal_url=prov["terminal_url"])
    assert (v.verdict, v.sub_status, v.facts["stub_signals"]) == ("refuse", "stub_not_article", ["preview_url"])
    assert v.facts["pages"] == 47
    assert A.accept(data).verdict == "accept"
    assert A.accept(data, headers={"Content-Disposition": 'attachment; filename="x_previewpdf.pdf"'}).sub_status \
        == "stub_not_article"


def test_a_sixty_page_volume_for_a_twelve_page_record_is_volume_not_article():
    from litkb.acquire import accept as A
    data = _neg("CONSTRUCTED_proceedings_volume_60p.pdf")
    v = A.accept(data, record_pages=N.VOLUME_RECORD_PAGES)
    assert (v.verdict, v.sub_status, v.facts["rests_on_metadata"]) == ("refuse", "volume_not_article", True)
    assert A.accept(data, record_pages=None).facts["volume"] == "absent"
    assert A.accept(data, record_pages="C1-C68").facts["volume"] == "unparsed"
    assert A.accept(data, record_pages="101\u2013112").facts["volume"] == "unparsed", "a-b ASCII digits ONLY"
    assert A.accept(data, record_pages="1-60").facts["volume"] == "article"


def test_a_pdf_whose_bibliography_carries_the_requested_doi_is_cited_document_not_this_article():
    from litkb.acquire import accept as A
    data = _neg("CONSTRUCTED_cites_requested_doi.pdf")
    v = A.accept(data, doi=N.CITED_DOI)
    assert (v.verdict, v.sub_status) == ("refuse", "cited_document_not_this_article"), v.summary()
    assert A.accept(data, doi="10.5555/some-other-doi").facts["doi_position"] == "absent"
    own = A.accept(_article(doi_line=f"https://doi.org/{N.CITED_DOI}"), doi=N.CITED_DOI.upper())
    assert (own.verdict, own.facts["doi_position"]) == ("accept", "first-pages")


def test_guard_18_a_verdict_never_rests_on_metadata_that_could_not_be_fetched():
    """The volume and cited rules read the RECORD: told it could not be fetched, they abstain — whatever stale
    range or DOI came along — and the file is accepted, never refused on it."""
    from litkb.acquire import accept as A
    for name, kw in (("CONSTRUCTED_proceedings_volume_60p.pdf", {"record_pages": N.VOLUME_RECORD_PAGES}),
                     ("CONSTRUCTED_cites_requested_doi.pdf", {"doi": N.CITED_DOI})):
        v = A.accept(_neg(name), metadata_fetched=False, **kw)
        assert (v.verdict, v.facts["metadata"]) == ("accept", "unfetched"), (name, v.summary())
        assert ("volume", "unfetched") in v.steps and ("cited", "unfetched") in v.steps


def test_a_scanned_article_is_not_a_stub_for_having_no_text_layer(monkeypatch):
    """auditor-C1b F1: a scan carries its words as pixels, so `chars_no_refs` (<3,000 characters, no reference
    heading) is not asked of a document holding an IMAGE page (decision D13's rule). The CONSTRUCTED scan — a
    200-character cover and 5 image-only pages — is ACCEPTED; with the abstention switched off (the known-bad,
    in this process) the same bytes are refused stub_not_article, which is what live's four scans got."""
    from litkb.acquire import accept as A
    scan = _neg("CONSTRUCTED_scan_no_text_layer.pdf")
    v = A.accept(scan)
    assert (v.verdict, v.sub_status, v.facts["stub_signals"]) == ("accept", None, []), v.summary()
    assert (v.facts["pages"], v.facts["image_pages"]) == (1 + N.SCAN_IMAGE_PAGES, N.SCAN_IMAGE_PAGES)
    assert v.facts["chars"] < A.STUB_MAX_CHARS and not v.facts["has_reference_section"], "the rule WOULD fire"
    monkeypatch.setattr(A, "image_pages_of", lambda texts, images: [])
    off = A.accept(scan)
    assert (off.verdict, off.sub_status, off.facts["stub_signals"]) == ("refuse", "stub_not_article", ["chars_no_refs"])


def test_the_abstention_needs_an_image_page_not_just_a_short_text():
    """THE CONTROL: the first-page TDM stub has a text layer and no image page, so the abstention never covers
    it — `chars_no_refs` still fires on it without its header (the image rule is not a hole in the stub rule)."""
    from litkb.acquire import accept as A
    v = A.accept(_neg("CONSTRUCTED_tdm_stub_first_page.pdf"))
    assert (v.sub_status, v.facts["stub_signals"], v.facts["image_pages"]) == ("stub_not_article",
                                                                               ["chars_no_refs"], 0)
    texts, images, err = A.page_facts(_neg("CONSTRUCTED_scan_no_text_layer.pdf"))
    assert err is None and A.image_pages_of(texts, images) == list(range(2, 2 + N.SCAN_IMAGE_PAGES))
    assert A.image_pages_of(texts, None) == [], "no image counts read -> nothing abstains"


#: MEASURED by builder-C1b, 2026-09-23 (scratch r2/corpus_sweep_r2.py, live read as litkb_reader): the four scans
#: P2 made bind on OCR, as live holds them — rel_path: (sha256, pages, characters, image pages). Before the
#: abstention every one was refused `stub_not_article` by `chars_no_refs` (auditor-C1b F1, the same sweep).
REAL_SCANS = {
    "Validation/Anderson_1957_statistical-inference-about-markov.pdf":
        ("9b43ee6ab770abfae2a613e7c5cb61a347de583948842f85dd0cb7d7c43f523c", 22, 163, 21),
    "Validation/Hudson_1978_natural-identity-exponential-families.pdf":
        ("9abd180eb0589b82b345eb25b1e5643a2e49a327882e15a77849d768d2d16307", 12, 150, 11),
    "Validation/Hwang_1982_improving-upon-standard-estimators.pdf":
        ("750c25c3b3ab74e2988bfb134a57daf3f52e57db713488a621d4b31cc3581372", 11, 150, 10),
    "Validation/Ogata_1998_space-time-point-process-models.pdf":
        ("d65c39c8f473c97a564d6024c4faa36902c24659f62326d53ae34e22f0a0832e", 24, 0, 24),
}


@pytest.mark.parametrize("rel", sorted(REAL_SCANS))
def test_the_four_real_scans_on_live_are_accepted_by_the_stub_rule(rel, tmp_path):
    """The REAL regression rows of F1, pinned to their measured facts. The corpus is read-only: each file is
    COPIED into the pytest tmp dir first. Skips when the corpus is not mounted, or holds other bytes today."""
    from litkb.acquire import accept as A
    from litkb.acquire.store import LITERATURE_ROOT
    src = Path(LITERATURE_ROOT) / rel
    if not src.is_file():
        pytest.skip(f"literature corpus file not present: {src}")
    copy = tmp_path / src.name
    shutil.copyfile(src, copy)
    data = copy.read_bytes()
    sha, pages, chars, img = REAL_SCANS[rel]
    if hashlib.sha256(data).hexdigest() != sha:
        pytest.skip(f"{rel} holds other bytes than the ones measured (sha256 {sha[:12]})")
    v = A.accept(data)
    assert (v.verdict, v.facts["stub_signals"]) == ("accept", []), v.summary()
    assert (v.facts["pages"], v.facts["chars"], v.facts["image_pages"]) == (pages, chars, img)


def test_the_doi_pages_boundary_is_page_three():
    """T14's DOI_PAGES=3, exactly: a DOI first printed on page 3 is the document's own; on page 4 it is only a
    citation (auditor-C1b F5: `<` read as `<=` survived — the constructed negative prints it on page 5)."""
    from litkb.acquire import accept as A
    doi = "10.5555/litkb-constructed-boundary"
    assert A.doi_position(["a", "b", f"doi {doi}"], doi) == "first-pages"
    assert A.doi_position(["a", "b", "c", f"doi {doi}"], doi) == "only-after"


# ── the byte rules, one by one ─────────────────────────────────────────────────────────────

LANDING = (b'<!DOCTYPE html><html><head><meta property="citation_pdf_url" content="/a.pdf">'
           b'<meta name="bepress_citation_pdf_url" content="/b.pdf">'
           b'<link type="application/pdf" rel="alternate" href="/c.pdf"></head><body>x</body></html>')


def test_an_html_page_is_html_response_and_its_pdf_pointers_are_recorded():
    from litkb.acquire import accept as A
    v = A.accept(LANDING)
    assert v.sub_status == "html_response"
    assert v.facts["landing"] == {"citation_pdf_url": True, "bepress": True, "eprints": False,
                                  "link_alternate_pdf": True, "pdf_pointer": True}
    bare = A.accept(b"<html><head><title>403</title></head><body>no</body></html>")
    assert bare.sub_status == "html_response" and bare.facts["landing"]["pdf_pointer"] is False


@pytest.mark.parametrize("data, sub, step", [
    (b"URLError: <urlopen error [Errno 11002] getaddrinfo failed>", "too_small", "magic"),  # E13's 58 bytes, CONSTRUCTED copy
    (b"x" * 6000, "missing_pdf_header", "magic"),
    (b"", "too_small", "magic"),
    (b"%PDF-x.y\n" + b"0" * 6000 + b"\n%%EOF\n", "corrupt_pdf_header", "header"),
    (b"%PDF-1.4\n%\xef\xbf\xbd\xef\xbf\xbd\n" + b"0" * 6000 + b"\n%%EOF\n", "corrupt_pdf_header", "header"),
])
def test_the_byte_rules_name_what_the_bytes_are(data, sub, step):
    """Each byte rule refuses at ITS step: since libqpdf joined as step 8 (decision D14) the two header cases
    would also be refused `corrupt_pdf_header` by qpdf further down, so the step is asserted too — without it the
    mojibake/version rule's own mutation survived (fix round 2, row C1B9)."""
    from litkb.acquire import accept as A
    v = A.accept(data)
    assert (v.verdict, v.sub_status, v.steps[-1]) == ("refuse", sub, (step, "fail")), v.summary()


def test_a_whole_pdf_under_the_floor_is_too_small_and_a_cut_one_is_early_eof():
    from litkb.acquire import accept as A
    small = N.text_pdf([["one short page"]])
    assert len(small) < A.MIN_PDF_BYTES and A.accept(small).sub_status == "too_small"
    art = _article()
    cut = art[: len(art) - 200]                         # the trailer (and %%EOF) cut off
    assert A.accept(cut).sub_status == "early_eof_with_trailing_payload"
    tail = art + b"%" + b"t" * (A.EOF_TAIL + 10) + b"\n"    # %%EOF followed by more than 8 KiB of payload
    assert A.accept(tail).sub_status == "early_eof_with_trailing_payload"


def _pdf_of_length(n):
    """CONSTRUCTED: a one-page PDF padded (unreferenced stream) to EXACTLY n bytes."""
    for pad in range(0, n):
        data = N.text_pdf([["one short page"]], pad=pad)
        if len(data) == n:
            return data
        if len(data) > n:
            break
    raise AssertionError(f"no pad reaches {n} bytes exactly")


def test_the_floor_is_five_thousand_bytes_exactly():
    """C1-RG (b)'s floor, at its edge: 4,999 bytes are too_small, 5,000 pass the floor step (auditor-C1b F5:
    `<` read as `<=` survived). The qpdf step is stubbed so the edge is all that is read."""
    from litkb.acquire import accept as A
    under, at = _pdf_of_length(A.MIN_PDF_BYTES - 1), _pdf_of_length(A.MIN_PDF_BYTES)
    assert A.accept(under, qpdf_runner=lambda p: 0).sub_status == "too_small"
    v = A.accept(at, qpdf_runner=lambda p: 0)
    assert ("floor", "pass") in v.steps and v.sub_status != "too_small", v.summary()


def test_a_gzip_that_inflates_past_the_ceiling_is_refused_not_inflated(monkeypatch):
    """The decompression-bomb ceiling (UNWRAP_MAX_BYTES), lowered here so a CONSTRUCTED article crosses it: the
    wrapper is `compressed_or_archived_payload`, named for the ceiling — never the truncated inflate judged as a
    PDF (auditor-C1b F5: the ceiling check deleted survived)."""
    from litkb.acquire import accept as A
    art = _article()
    monkeypatch.setattr(A, "UNWRAP_MAX_BYTES", len(art) // 2)
    v = A.accept(gzip.compress(art))
    assert (v.verdict, v.sub_status) == ("refuse", "compressed_or_archived_payload"), v.summary()
    assert "inflates past" in v.reason


def test_the_archive_route_takes_a_bom_prefixed_pdf_on_both_download_paths():
    """`annas.download_pdf`'s two header checks are `quick_magic` (the acceptance test's header rule): a PDF
    behind a byte-order mark is taken from fast_download AND from the record's own download options (auditor-C1b
    F5: reverting the first check to `startswith(b"%PDF-")` survived — no test offered the route a BOM PDF).
    A stub client, no network."""
    from litkb.acquire import annas
    bom_pdf = _neg("CONSTRUCTED_bom_valid_article.pdf")

    class Client:
        base = annas.BASE

        def __init__(self, routes):
            self.routes = routes

        def get(self, url, accept="text/html", timeout=120, **_kw):
            for frag, resp in self.routes.items():
                if frag in url:
                    return resp
            raise AssertionError(f"no stub route for {url}")

    class Pacer:
        def sleep(self, s):
            pass

        def backoff(self):
            pass

    fast = json.dumps({"download_url": "https://partner.constructed.example/file.pdf"}).encode()
    pdf, _left, tried, _st = annas.download_pdf(Client({"fast_download": (200, {}, fast),
                                                        "partner.constructed": (200, {}, bom_pdf)}),
                                                "k-CONSTRUCTED", "a" * 32, {}, Pacer())
    assert pdf == bom_pdf and tried[-1].endswith("=ok"), tried
    none = json.dumps({"error": "no download_url (CONSTRUCTED)"}).encode()
    add = {"download_urls": [["mirror", "https://mirror.constructed.example/file.pdf"]]}
    pdf, _left, tried, _st = annas.download_pdf(Client({"fast_download": (200, {}, none),
                                                        "mirror.constructed": (200, {}, bom_pdf)}),
                                                "k-CONSTRUCTED", "a" * 32, add, Pacer())
    assert pdf == bom_pdf and tried[-1].endswith("=ok"), tried


def _tar(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def test_gzip_and_tar_payloads_are_unwrapped_and_an_empty_wrapper_is_compressed_or_archived():
    """C18: a good PDF inside gzip, tar, or tar.gz is accepted and the INNER bytes are what lands; a wrapper
    with no PDF (or two) is `compressed_or_archived_payload`; a zip is recognised and never unwrapped."""
    from litkb.acquire import accept as A
    art = _article()
    for wrapped, how in ((gzip.compress(art), "gzip"), (_tar([("paper.pdf", art), ("meta.xml", b"<x/>")]),
                                                        "tar:paper.pdf"),
                         (gzip.compress(_tar([("a/paper.pdf", art)])), "gzip+tar:a/paper.pdf")):
        v = A.accept(wrapped)
        assert (v.verdict, v.facts["unwrapped"], v.pdf) == ("accept", how, art), v.summary()
    for bad in (gzip.compress(b"<html>not a pdf</html>"), _tar([("a.pdf", art), ("b.pdf", art)]),
                _tar([("x.txt", b"text")])):
        assert A.accept(bad).sub_status == "compressed_or_archived_payload"
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("paper.pdf", art)
    assert A.accept(z.getvalue()).sub_status == "compressed_or_archived_payload"


def test_qpdf_codes_are_read_and_an_absent_qpdf_is_never_clean(monkeypatch):
    """exit 0 clean, 3 recoverable (accepted), 2 damaged (refused corrupt_pdf_header); neither pikepdf nor the
    qpdf CLI -> `qpdf-unavailable` and an INCOMPLETE verdict, never `clean`."""
    from litkb.acquire import accept as A
    art = _article()
    assert A.accept(art, qpdf_runner=lambda p: 0).complete is True
    assert A.accept(art, qpdf_runner=lambda p: 0).facts["qpdf"] == "clean"
    assert A.accept(art, qpdf_runner=lambda p: 3).facts["qpdf"] == "recoverable"
    assert A.accept(art, qpdf_runner=lambda p: 3).verdict == "accept"
    assert A.accept(art, qpdf_runner=lambda p: 2).sub_status == "corrupt_pdf_header"
    assert A.accept(art, qpdf_runner=lambda p: 7).facts["qpdf"] == "qpdf-error:7"
    monkeypatch.setitem(sys.modules, "pikepdf", None)            # `import pikepdf` now raises ImportError
    monkeypatch.setattr(A.shutil, "which", lambda name: None)
    v = A.accept(art)
    assert (v.verdict, v.facts["qpdf"], v.complete) == ("accept", "qpdf-unavailable", False)
    assert v.facts["qpdf_checker"] == "none"


def _pdf_of(objs):
    """CONSTRUCTED: a PDF from {object number: body}, with one correct xref (so the only fault is the planted one)."""
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
    return bytes(out)


def _stream(data, extra=b""):
    return b"<< /Length " + str(len(data)).encode() + extra + b" >>\nstream\n" + data + b"\nendstream"


def _undecodable_pdf():
    """CONSTRUCTED: one page whose content stream says FlateDecode and holds bytes that do not inflate, padded
    past the 5,000-byte floor by an unreferenced stream — damage qpdf cannot repair."""
    return _pdf_of({1: b"<< /Type /Catalog /Pages 2 0 R >>", 2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                    3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R >>",
                    4: _stream(b"\x78\x9c" + b"\xff" * 64, b" /Filter /FlateDecode"),
                    5: _stream(b"% CONSTRUCTED padding: an unreferenced stream.\n" * 120)})


def test_libqpdf_through_pikepdf_answers_clean_recoverable_and_damaged():
    """Decision D14: step 8's checker is libqpdf through pikepdf (`check_pdf_syntax`). CONSTRUCTED inputs, one
    per outcome: the clean article; the same article with its `startxref` broken (qpdf reconstructs the xref:
    warnings only -> recoverable, ACCEPTED); a content stream that does not inflate, and a body with no trailer
    dictionary (qpdf raises -> damaged, REFUSED corrupt_pdf_header); a password-protected file (the check
    cannot run -> encrypted, an incomplete verdict, never refused here)."""
    pikepdf = pytest.importorskip("pikepdf")
    from litkb.acquire import accept as A
    art = _article()
    i = art.rfind(b"startxref")
    broken = art[:i] + b"startxref\n999999\n%%EOF\n"
    assert A.libqpdf_check(art) == "clean"
    assert A.libqpdf_check(broken) == "recoverable"
    assert A.libqpdf_check(_undecodable_pdf()) == "damaged"
    assert A.libqpdf_check(b"%PDF-1.4\n" + b"x" * 6000 + b"\n%%EOF\n") == "damaged"
    v = A.accept(broken)
    assert (v.verdict, v.facts["qpdf"], v.complete) == ("accept", "recoverable", True), v.summary()
    assert v.facts["qpdf_checker"].startswith("libqpdf ") and "pikepdf" in v.facts["qpdf_checker"]
    bad = A.accept(_undecodable_pdf())
    assert (bad.verdict, bad.sub_status, bad.facts["qpdf"]) == ("refuse", "corrupt_pdf_header", "damaged")
    assert ("qpdf", "fail") in bad.steps
    buf = io.BytesIO()
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        pdf.save(buf, encryption=pikepdf.Encryption(user="u-CONSTRUCTED", owner="o-CONSTRUCTED"))
    assert A.libqpdf_check(buf.getvalue()) == "encrypted"
    notes = []
    assert A.libqpdf_check(art, notes) == "clean" and notes == []


def test_the_page_probes_unopenable_constructed_file_is_refused_by_libqpdf_first():
    """`readability._constructed_unopenable_pdf` (a catalog whose /Pages is not a dictionary) was made to pass
    the header+trailer shape and be stopped only by the bind's page probe. Through the acceptance test with
    libqpdf wired it is refused earlier, at step 8, `corrupt_pdf_header` — the ladder's landing never reaches the
    probe with it (qc/test_litkb_quarantine.py stubs step 8 to test the probe itself)."""
    pytest.importorskip("pikepdf")
    from litkb import readability as R
    from litkb.acquire import accept as A
    data = R._constructed_unopenable_pdf(salt="c1b " + "p" * A.MIN_PDF_BYTES)
    v = A.accept(data)
    assert (v.verdict, v.sub_status, v.steps[-1]) == ("refuse", "corrupt_pdf_header", ("qpdf", "fail")), v.summary()


def _encrypted_article():
    """CONSTRUCTED: the BOM article's builder (no BOM) re-saved by pikepdf with a USER password, streams left
    uncompressed so it stays past the 5,000-byte floor. Neither libqpdf nor pdfium opens it without the password.
    Not deterministic (the encryption salts are random), so every call is a new sha256."""
    pikepdf = pytest.importorskip("pikepdf")
    buf = io.BytesIO()
    with pikepdf.open(io.BytesIO(_article())) as pdf:
        pdf.save(buf, encryption=pikepdf.Encryption(user="u-CONSTRUCTED", owner="o-CONSTRUCTED"),
                 compress_streams=False)
    return buf.getvalue()


def test_an_encrypted_answer_alone_makes_the_verdict_incomplete():
    """auditor-C1b round 2 F4 (its Y3 survived): SCHEMAS says `complete` is false on `encrypted`. End to end the
    CONSTRUCTED password-protected article is ACCEPTED here (the bind's probe refuses what it cannot open — one
    refusal, one home) and incomplete; its steps also read `unreadable`, so the `encrypted` outcome is held ALONE
    too, on a verdict whose every other step passed."""
    from litkb.acquire import accept as A
    enc = _encrypted_article()
    assert len(enc) >= A.MIN_PDF_BYTES and A.libqpdf_check(enc) == "encrypted"
    v = A.accept(enc)
    assert (v.verdict, v.facts["qpdf"], v.complete) == ("accept", "encrypted", False), v.summary()
    assert ("qpdf", "encrypted") in v.steps and ("text", "unreadable") in v.steps
    assert A.Verdict(steps=[("qpdf", "encrypted"), ("text", "pass"), ("stub", "pass")]).complete is False
    assert A.Verdict(steps=[("qpdf", "clean"), ("text", "pass"), ("stub", "pass")]).complete is True


def test_a_signed_terminal_urls_query_never_reaches_the_recorded_evidence():
    """auditor-C1b round 2 F2 (its Y10 survived; Codex X7): E20's terminal URL is a SIGNED S3 URL carrying a
    session token, and `detail.acceptance` (the verdict's summary) reaches the ledger row and the quarantine
    sidecar. A PLANTED token in the query and the fragment of a CONSTRUCTED terminal URL must appear nowhere in
    the summary, on the accept path AND on the refuse path; the path the preview rule reads is kept."""
    from litkb.acquire import accept as A
    planted = ("https://cdn.constructed.example/objects/o.pdf?X-Amz-Security-Token=PLANTED-TOKEN"
               "&X-Amz-Signature=PLANTED-SIG#PLANTED-FRAGMENT")
    ok = A.accept(_article(), terminal_url=planted)
    bad = A.accept(b"%PDF-1.4\n% under the floor\n%%EOF\n", terminal_url=planted)
    assert (ok.verdict, bad.verdict, bad.sub_status) == ("accept", "refuse", "too_small")
    for v in (ok, bad):
        assert "PLANTED" not in json.dumps(v.summary()), v.summary()["facts"]["evidence"]
        assert v.facts["evidence"]["terminal_url"] == "https://cdn.constructed.example/objects/o.pdf"


#: The auditor's CONSTRUCTED first-page stub (auditor-C1b round 2, scratch probe_a2.py): 25 lines, 2,189 characters
#: as the acceptance test counts them, no reference heading.
STUB_LINES = [f"CONSTRUCTED stub line {i}: the first page of an article, served alone by a TDM endpoint." for i in range(25)]


def test_the_stub_rule_abstains_on_any_document_with_an_image_page_its_stated_limit():
    """auditor-C1b round 2 F1 — THE STATED LIMIT, pinned as today's behaviour (a limit, not an endorsement): the
    abstention covers ANY document holding at least one image page, not only a scan. The auditor's CONSTRUCTED stub
    followed by ONE image-only page (a cover, an advertisement, a full-page figure) is ACCEPTED with no stub signal;
    the same page alone is refused stub_not_article [chars_no_refs]; the evidence signals still reach the mixed
    document. A referee ruling that narrows the abstention must change this test."""
    from litkb.acquire import accept as A
    mixed = N.scan_pdf(STUB_LINES, 1, note="CONSTRUCTED stub_plus_one_image_page")
    v = A.accept(mixed)
    assert (v.verdict, v.facts["stub_signals"], v.facts["image_pages"], v.facts["chars"]) == ("accept", [], 1, 2189)
    assert not v.facts["has_reference_section"], "the text signal WOULD fire without the image page"
    alone = A.accept(N.text_pdf([STUB_LINES], pad=4000, note="CONSTRUCTED stub_only"))
    assert (alone.verdict, alone.sub_status, alone.facts["stub_signals"]) == ("refuse", "stub_not_article",
                                                                             ["chars_no_refs"])
    hdr = A.accept(mixed, headers={"X-ELS-Status": "WARNING - CONSTRUCTED value"})
    assert (hdr.sub_status, hdr.facts["stub_signals"]) == ("stub_not_article", ["x_els_status"])


def test_the_image_page_rule_counts_the_probes_normalised_characters_not_the_raw_text():
    """Decision D13 counts NORMALISED native characters (`resolver._norm_text`, what `probe.page_text_chars`
    counts): a page whose text layer is only whitespace and punctuation and that draws an image IS an image page
    (auditor-C1b round 2 F6: raw length survived as its Y7). CONSTRUCTED text lists and image counts."""
    from litkb.acquire import accept as A
    assert A.image_pages_of([" -- \r\n", "x", ""], [1, 1, 0]) == [1]


def test_libmagic_absent_is_labelled_as_the_fallback_sniff():
    from litkb.acquire import accept as A
    mime, source = A.mime_of(_article())
    assert mime == "application/pdf" and source in ("libmagic", "fallback-sniff")


def test_quick_magic_is_the_header_rule_and_shape_keeps_pdf_shapes_contract():
    from litkb.acquire import accept as A
    from litkb.acquire.store import pdf_shape
    art = _article()
    assert A.quick_magic(art) and A.quick_magic(b"\xef\xbb\xbf" + art) and A.quick_magic(b"\r\n  " + art)
    assert not A.quick_magic(None) and not A.quick_magic(b"<html><body>%PDF-1.4 quoted</body></html>")
    assert not A.quick_magic(b"x" * 1100 + art), "a signature past the 1,024-byte window is not a header"
    assert pdf_shape(b"\xef\xbb\xbf" + art) == ("pdf", "")
    assert pdf_shape(art[: len(art) - 200])[0] == "truncated-pdf"
    shape, why = pdf_shape(b"<!DOCTYPE html><html>x</html>")
    assert shape == "not-a-pdf" and "look like HTML" in why
    assert pdf_shape(N.text_pdf([["one short page"]])) == ("pdf", ""), \
        "pdf_shape keeps its contract: the floor is the full test's, not the thin caller's"


# ── the sidecar on every quarantine ────────────────────────────────────────────────────────

def _store(tmp_path):
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def test_to_quarantine_writes_the_sidecar_itself_with_or_without_a_reason(tmp_path):
    from litkb import quarantine as Q
    from litkb.acquire.store import reason_path
    s = _store(tmp_path)
    a = s.write_new(s.incoming / "A.pdf", b"%PDF-1.4 a")
    qa, _ = s.to_quarantine(a, None, "A_2020_a-b", "binding-failed", "0" * 64)
    assert reason_path(qa).is_file(), "to_quarantine moved the payload and wrote no sidecar"
    body = json.loads(reason_path(qa).read_text(encoding="utf-8"))
    assert (body["status"], body["label"], body["moved_from"]) == ("binding-failed", "binding-failed",
                                                                   "_litkb_staging/incoming/A.pdf")
    b = s.write_new(s.incoming / "B.pdf", b"%PDF-1.4 b")
    qb, _ = s.to_quarantine(b, None, "B_2020_c-d", "probe-error", "1" * 64, reason={"why": "given"})
    assert json.loads(reason_path(qb).read_text(encoding="utf-8")) == {"why": "given"}
    assert Q.without_reason(s.root) == (0, [])


def test_a_stray_sidecar_moves_the_name_on_and_is_never_overwritten(tmp_path):
    from litkb.acquire.store import reason_path
    s = _store(tmp_path)
    stray = s.write_new(s.quarantine / "A_2020_a-b__binding-failed__000000000000.reason.json", b"{}")
    a = s.write_new(s.incoming / "A.pdf", b"%PDF-1.4 a")
    qa, _ = s.to_quarantine(a, None, "A_2020_a-b", "binding-failed", "0" * 64)
    assert qa.name == "A_2020_a-b__binding-failed__000000000000.2.pdf" and reason_path(qa).exists()
    assert stray.read_bytes() == b"{}"


def test_the_legacy_annas_quarantine_writes_a_sidecar(tmp_path):
    from litkb.acquire import annas
    src = tmp_path / "staging" / "X.pdf"
    src.parent.mkdir()
    src.write_bytes(b"%PDF-1.4 x")
    q = annas._quarantine(str(src), "X_2020_a-b", "hash-mismatch", "a" * 32, str(tmp_path / "_quarantine"))
    assert Path(q).is_file() and Path(q[:-4] + ".reason.json").is_file(), "no sidecar beside the payload"
    side = json.loads(Path(q[:-4] + ".reason.json").read_text(encoding="utf-8"))
    assert (side["status"], side["route"]) == ("hash-mismatch", "annas.fetch_one")


def test_without_reason_counts_payloads_and_ignores_sidecars_and_txt_companions(tmp_path):
    from litkb import quarantine as Q
    q = tmp_path / "_quarantine"
    q.mkdir()
    (q / "a.pdf").write_bytes(b"a")
    (q / "a.txt").write_bytes(b"t")
    (q / "b.download").write_bytes(b"b")
    (q / "b.reason.json").write_bytes(b"{}")
    (q / "c.txt").write_bytes(b"lone text is a payload")
    assert Q.without_reason(tmp_path) == (2, ["_quarantine/a.pdf", "_quarantine/c.txt"])


# ── the database: backfill, offer_to_bind, and the fires ───────────────────────────────────

@pytest.fixture
def owner(litkb_pg_base):
    return litkb_pg_base[1]


@pg_only
def test_the_sidecar_backfill_is_a_dry_run_by_default_and_marks_what_it_writes(owner, tmp_path):
    """On a COPY: two sidecar-less payloads, one with a quarantine_payloads row, one without. The dry run writes
    nothing; apply writes both, each `"backfilled": true` with its source; a second apply has nothing to do."""
    from litkb import quarantine as Q
    root = tmp_path / "Lit"
    q = root / "_quarantine"
    q.mkdir(parents=True)
    rowed = q / "Rowed_2020_a-b__binding-failed__aaaaaaaaaaaa.pdf"
    rowed.write_bytes(b"%PDF-1.4 rowed " + tmp_path.name.encode())
    bare = q / "Bare_2020_c-d.pdf"
    bare.write_bytes(b"legacy")
    sha, n = Q.sha256_of(rowed)
    Q.record_system(owner, rel_path=Q.rel_of(root, rowed), sha256=sha, nbytes=n, reason="binding-failed",
                    origin="legacy-backfill", detail={"note": "CONSTRUCTED row"})
    dry = Q.backfill_sidecars(owner, root=root)
    assert dry["counters"]["to_write"] == 2 and dry["counters"]["written"] == 0
    assert Q.without_reason(root)[0] == 2
    done = Q.backfill_sidecars(owner, root=root, apply=True)
    assert (done["counters"]["written"], done["errors"]) == (2, [])
    a = json.loads(rowed.with_suffix(".reason.json").read_text(encoding="utf-8"))
    b = json.loads(bare.with_suffix(".reason.json").read_text(encoding="utf-8"))
    assert a["backfilled"] is True and a["reason_source"] == "quarantine_payloads" and a["note"] == "CONSTRUCTED row"
    assert b["backfilled"] is True and b["reason_source"].startswith("name") and b["label"] == "legacy"
    assert Q.without_reason(root) == (0, []) and Q.backfill_sidecars(owner, root=root, apply=True)[
        "counters"]["to_write"] == 0


@pg_only
@pytest.mark.parametrize("fire", ["sidecar", "stub_constructed", "stub_e20", "volume"])
def test_each_c1b_fire_reads_zero_on_control_and_one_with_its_guard_off(owner, tmp_path, fire):
    """The (c) rows of this builder, as gates: the control arm holds its counter at 0 and the known-bad arm —
    ONE guard switched off in this process — moves it to exactly 1. The counters are run-scoped to each arm's
    own workstream and clock, so the arms cannot see each other's rows on this shared worker database."""
    f = H.FIRES[fire]
    assert f["run"](owner, "control", tmp_path) == 0
    assert f["run"](owner, "known_bad", tmp_path) == 1


def test_the_sidecar_fire_switches_off_only_to_quarantines_own_write(tmp_path):
    """auditor-C1b F6: the sidecar fire's known-bad once replaced `Store.write_reason` for every caller, so a
    refusal BEFORE binding (the acceptance test's `quarantine_new` path) raised TypeError inside the arm — a
    DID-NOT-FIRE (error) in the harness. It now shadows the write for `to_quarantine`'s call alone:
    `to_quarantine` leaves no sidecar, `quarantine_new` still writes its own, and nothing stays patched."""
    from litkb.acquire.store import Store, reason_path
    s = _store(tmp_path)
    with H._swap(Store, "to_quarantine", H._to_quarantine_without_its_sidecar(Store.to_quarantine)):
        a = s.write_new(s.incoming / "A.pdf", b"%PDF-1.4 a")
        qa, _ = s.to_quarantine(a, None, "A_2020_a-b", "binding-failed", "0" * 64)
        qb, _t, qwhy = s.quarantine_new(b"<html>not a pdf</html>", "B_2020_c-d", "not-a-pdf", "1" * 64, {"why": "x"})
    assert qa.is_file() and not reason_path(qa).exists(), "the known-bad left a sidecar"
    assert qwhy == reason_path(qb) and qwhy.is_file(), "the known-bad took quarantine_new's sidecar too"
    assert "write_reason" not in vars(s)
    c = s.write_new(s.incoming / "C.pdf", b"%PDF-1.4 c")
    qc, _ = s.to_quarantine(c, None, "C_2020_e-f", "binding-failed", "2" * 64)
    assert reason_path(qc).is_file(), "the swap was not restored"


@pg_only
def test_the_sidecar_fires_known_bad_arm_answers_when_the_acceptance_test_refuses_first(owner, tmp_path):
    """F6 in the fire itself: with the header repair ALSO removed, the BOM article is refused before binding (the
    `quarantine_new` path). The known-bad arm must still answer a number — 0, since `quarantine_new` writes its own
    sidecar — and never raise the TypeError the harness can only print as DID-NOT-FIRE (error)."""
    from litkb.acquire import accept as A
    with H._swap(A, "repair_offset", lambda d: 0):
        assert H.fire_sidecar(owner, "known_bad", tmp_path) == 0


@pg_only
def test_a_scan_bound_in_the_run_is_not_counted_a_stub_and_its_abstention_is_reported(owner, tmp_path):
    """The counter reads what the gate reads (F1 on the counter side): the CONSTRUCTED scan binds (its cover
    sheet carries the title and author), `stubs_bound` reads 0 and `stub_rule_abstained_image_pages` 1 — and with
    the abstention switched off in the COUNTER alone (the known-bad) the same bound file reads as a stub."""
    from litkb.acquire import accept as A
    ws, token, frozen, work, store = H._setup(owner, tmp_path, "scan", title=N.SCAN_TITLE, family=N.SCAN_AUTHOR)
    status, detail = H._offer(owner, ws, token, work, H._salted(_neg("CONSTRUCTED_scan_no_text_layer.pdf"), "scan"),
                              store)
    assert status == "ok", detail
    m = H._manifest(ws, frozen, store)
    assert (H.stubs_bound(owner, m), H.stub_rule_abstained_image_pages(owner, m)) == (0, 1)
    with H._swap(A, "image_pages_of", lambda texts, images: []):
        assert H.stubs_bound(owner, m) == 1


@pg_only
def test_the_stub_counter_joins_the_landing_evidence_by_the_files_sha(owner, tmp_path):
    """auditor-C1b F5 (its X7): E20's preview is bound with the stub detector off, then a LATER `ok` attempt for
    the same work records other bytes and no preview evidence. The counter must read the evidence of the attempt
    that landed THIS file (by sha256), not the work's latest: 1, not 0."""
    from litkb.acquire import accept as A
    from litkb.acquire import run
    data, prov = _e20()
    ws, token, frozen, work, store = H._setup(owner, tmp_path, "join", title="Multi-State Survival Models for "
                                              "Interval-Censored Data", family="van den Hout", work_type="book")
    with H._swap(A, "stub_signals", lambda *a, **k: []):
        st, _d = H._offer(owner, ws, token, work, H._salted(data, "join"), store, source_url=prov["url_requested"],
                          terminal_url=prov["terminal_url"], headers={"Content-Type": prov["content_type"]})
    assert st == "ok", _d
    run.record_attempt(owner, ws, token, work["work_id"], "open_access", work.get("doi"), "ok",
                       {"sha256": "f" * 64, "acceptance": {"facts": {"evidence": {
                           "url": "https://constructed.example/other.pdf", "terminal_url": "", "headers": {}}}}})
    assert H.stubs_bound(owner, H._manifest(ws, frozen, store)) == 1


@pg_only
def test_offer_to_bind_keeps_a_refused_stub_with_its_sub_status_and_lands_a_repaired_bom_pdf(owner, tmp_path):
    from litkb.acquire import accept as A
    ws, token, frozen, work, store = H._setup(owner, tmp_path, "t", title=N.TDM_TITLE, family=N.TDM_AUTHOR)
    hdr = json.loads(_neg("CONSTRUCTED_tdm_stub_first_page.headers.json"))
    status, detail = H._offer(owner, ws, token, work, H._salted(_neg("CONSTRUCTED_tdm_stub_first_page.pdf"), "t"),
                              store, headers=hdr)
    assert (status, detail["sub_status"]) == ("bad-file", "stub_not_article")
    side = json.loads((store.root / detail["quarantine_reason"]).read_text(encoding="utf-8"))
    assert (side["sub_status"], side["label"]) == ("stub_not_article", "bad-file")
    assert side["acceptance"]["facts"]["evidence"]["headers"]["x-els-status"].startswith("WARNING")
    ws2, token2, _f, work2, store2 = H._setup(owner, tmp_path, "u", title=N.BOM_TITLE, family="Constructor")
    status2, detail2 = H._offer(owner, ws2, token2, work2, H._salted(_neg("CONSTRUCTED_bom_valid_article.pdf"), "u"),
                                store2)
    assert status2 == "ok", detail2
    filed = (store2.root / detail2["filed"]).read_bytes()
    assert filed.startswith(b"%PDF-1.4") and detail2["acceptance"]["facts"]["repaired_offset"] == 3
    assert H.stubs_bound(owner, H._manifest(ws, frozen, store)) == 0
    assert A.accept(filed).verdict == "accept"


@pg_only
def test_the_run_scoped_counters_ignore_binds_before_the_freeze_and_outside_the_run(owner, tmp_path):
    """D1 scoping: a stub bound with the detector off BEFORE `frozen_at` (or in another workstream) is history
    the counter does not read; the same bind after it is counted."""
    from litkb.acquire import accept as A
    ws, token, frozen, work, store = H._setup(owner, tmp_path, "s", title=N.TDM_TITLE, family=N.TDM_AUTHOR)
    with H._swap(A, "stub_signals", lambda *a, **k: []):
        assert H._offer(owner, ws, token, work, H._salted(_neg("CONSTRUCTED_tdm_stub_first_page.pdf"), "s"),
                        store)[0] == "ok"
    assert H.stubs_bound(owner, H._manifest(ws, frozen, store)) == 1
    later = owner.execute("SELECT clock_timestamp()").fetchone()[0]
    assert H.stubs_bound(owner, H._manifest(ws, later, store)) == 0
    assert H.stubs_bound(owner, {"frozen_at": frozen, "run_workstream_ids": [], "literature_root": str(store.root)}) == 0


def _propose_file(conn, ws, work, store, data, name):
    """CONSTRUCTED: `data` written into the store's staging (the store writes nowhere else) and a PROPOSED file
    version written for `work` directly (mode `proposal` — what `litkb.admit` writes for a non-registry route, and
    what the hunt URL landing and a `--from-file` bind land, decision D17). No bind, no acceptance test: the
    counters must still read it."""
    from psycopg.types.json import Jsonb
    p = store.write_new(store.incoming / name, data)
    fields = {"work_id": str(work["work_id"]), "rel_path": store.rel(p), "status": "active", "bytes": len(data),
              "source_url": "https://constructed.example/proposed.pdf"}
    conn.execute("SELECT litkb._write_version('proposal', 'file', NULL, %s, NULL, %s, NULL, %s, 'c1b-test', "
                 "'c1b-test')", (Jsonb({"sha256": hashlib.sha256(data).hexdigest()}), Jsonb(fields), ws))
    return p


@pg_only
def test_the_run_scoped_counters_read_a_proposed_file_version(owner, tmp_path):
    """auditor-C1b round 2 F5 (its Y8 survived): every fire binds through `attach_file` (state `promoted`), so the
    counters' `proposed` state was never exercised. A stub landed as a PROPOSAL in the run is counted."""
    ws, _token, frozen, work, store = H._setup(owner, tmp_path, "prop", title=N.TDM_TITLE, family=N.TDM_AUTHOR)
    _propose_file(owner, ws, work, store, H._salted(_neg("CONSTRUCTED_tdm_stub_first_page.pdf"), "prop"),
                  "Proposed_tdm_stub.pdf")
    states = owner.execute("SELECT state FROM litkb.file_versions WHERE work_id = %s", (work["work_id"],)).fetchall()
    assert states == [("proposed",)]
    assert H.stubs_bound(owner, H._manifest(ws, frozen, store)) == 1


@pg_only
def test_the_abstention_report_counts_short_documents_with_an_image_page_only(owner, tmp_path):
    """auditor-C1b round 2 F6 (its Y6 survived): `stub_rule_abstained_image_pages` counts the files the text rule
    did NOT judge — an image page AND a short text. The CONSTRUCTED scan is one; a CONSTRUCTED document with an
    image page and over 3,000 characters is not (the text rule would not have fired on it anyway)."""
    ws, _token, frozen, work, store = H._setup(owner, tmp_path, "abst", title=N.SCAN_TITLE, family=N.SCAN_AUTHOR)
    _propose_file(owner, ws, work, store, H._salted(_neg("CONSTRUCTED_scan_no_text_layer.pdf"), "abst"), "Scan.pdf")
    long_lines = [N.SCAN_TITLE, f"Author(s): H. {N.SCAN_AUTHOR}"] + N._body("Long cover sentence", 30)
    _propose_file(owner, ws, work, store, N.scan_pdf(long_lines, 1, note=f"CONSTRUCTED long_text_plus_one_image "
                                                                          f"{tmp_path.name}"), "Longimg.pdf")
    m = H._manifest(ws, frozen, store)
    rows = sorted((r["image_pages"], r["short_text"]) for r in H.bound_since_freeze(owner, m))
    assert rows == [(1, False), (N.SCAN_IMAGE_PAGES, True)]
    assert (H.stub_rule_abstained_image_pages(owner, m), H.stubs_bound(owner, m)) == (1, 0)


@pg_only
def test_a_bound_file_gone_from_disk_is_still_asked_the_evidence_signals_and_reported(owner, tmp_path):
    """auditor-C1b round 2 F11: a bound file the counter cannot read used to get NO signal at all, the evidence
    ones included, so a moved stub under-counted `stubs_bound` silently. E20's REAL preview is bound with the stub
    detector off; its filed copy is then moved off its path (CONSTRUCTED): the recorded terminal URL still says
    `preview_url`, and `bound_files_unreadable` says one file was not re-read."""
    from litkb.acquire import accept as A
    data, prov = _e20()
    ws, token, frozen, work, store = H._setup(owner, tmp_path, "gone", title="Multi-State Survival Models for "
                                              "Interval-Censored Data", family="van den Hout", work_type="book")
    with H._swap(A, "stub_signals", lambda *a, **k: []):
        st, d = H._offer(owner, ws, token, work, H._salted(data, "gone"), store, source_url=prov["url_requested"],
                         terminal_url=prov["terminal_url"], headers={"Content-Type": prov["content_type"]})
    assert st == "ok", d
    m = H._manifest(ws, frozen, store)
    assert (H.stubs_bound(owner, m), H.bound_files_unreadable(owner, m)) == (1, 0)
    filed = store.root / d["filed"]
    filed.rename(filed.with_name(filed.name + ".moved-by-test"))
    assert (H.stubs_bound(owner, m), H.bound_files_unreadable(owner, m)) == (1, 1)


@pg_only
def test_bytes_libqpdf_does_not_refuse_and_pdfium_cannot_open_reach_the_page_probe_through_the_landing(owner,
                                                                                                       tmp_path):
    """S4.5 decision D16 (a fixture libqpdf does not refuse and pdfium cannot open): the CONSTRUCTED
    password-protected article. libqpdf answers `encrypted` (no refusal) and the acceptance test accepts it, so
    `offer_to_bind` hands it to `run.land_and_attach`, whose page probe refuses it `probe-error` — quarantined with
    its sidecar, never bound. The probe guard keeps a test that reaches it through the ladder's landing, no stub."""
    ws, token, _frozen, work, store = H._setup(owner, tmp_path, "enc", title=N.BOM_TITLE, family="Constructor")
    status, detail = H._offer(owner, ws, token, work, _encrypted_article(), store)
    assert status == "bad-file" and detail.get("probe_error"), detail
    assert (detail["acceptance"]["verdict"], detail["acceptance"]["facts"]["qpdf"]) == ("accept", "encrypted")
    side = json.loads((store.root / detail["quarantine_reason"]).read_text(encoding="utf-8"))
    assert (side["label"], side["status"]) == ("probe-error", "bad-file")
    assert owner.execute("SELECT count(*) FROM litkb.file_versions WHERE work_id = %s",
                         (work["work_id"],)).fetchone()[0] == 0


# ── item 8: the bad-file read (qc/instruments/litkb_acq_probe_badfile.py) ──────────────────

B = _load("litkb_acq_probe_badfile")
BADFILE_CSV = SCRIPTS.parent / "phase4" / "qc" / "litkb_acq_probe_badfile.csv"


def test_the_bad_file_read_refuses_any_login_but_the_reader():
    class Conn:
        def __init__(self, user):
            self.user = user

        def execute(self, q):
            return self

        def fetchone(self):
            return (self.user,)
    assert B.require_reader(Conn("litkb_reader")).user == "litkb_reader"
    with pytest.raises(SystemExit):
        B.require_reader(Conn("litkb_writer"))


def test_the_bad_file_read_types_kept_bytes_through_the_acceptance_test():
    """ONE classifier: kept bytes are typed by accept.accept; the cause rules read only the markers."""
    st, cause, free, grade, *_ = B.type_kept(b"URLError: <urlopen error [Errno 11002] getaddrinfo failed>")
    assert (st, cause, free) == ("too_small", "transport_error_string", "n")
    st, cause, free, grade, *_ = B.type_kept(LANDING)
    assert (st, cause, free, grade) == ("html_response", "landing_page", "y", "measured")
    page = (b'<html><head><title>Redirecting</title></head><body><a href="https://linkinghub.elsevier.com/'
            b'retrieve/articleSelectSinglePerm?Redirect=x">x</a></body></html>')
    assert B.type_kept(page)[1:4] == ("landing_page", "y", "estimated")
    assert B.type_detail("scihub", [200, 522], ["sci-hub.ru:200=no-pdf-link(11350B)"], "10.1/x", 2025)[:3] \
        == ("html_response", "detail", "mirror_miss_page")
    assert B.type_detail("open_access", [202], ["x:202"], "10.1/x", 2020)[2] == "challenge_interstitial"


def test_the_committed_bad_file_csv_is_typed_in_the_contracts_vocabulary():
    """phase4/qc/litkb_acq_probe_badfile.csv is builder-C1a's backfill input: every row carries ONE CONTRACTS
    `bad-file` sub-status (so `bad_file_untyped` can reach 0 on history), a basis of bytes|detail|inferred and
    a cause from the closed list; html_is_the_work is never counted free to fix (decision D12)."""
    import csv
    rows = list(csv.DictReader(BADFILE_CSV.open(encoding="utf-8")))
    assert rows and list(rows[0]) == B.COLUMNS
    # S4.5 decision D29: a MISBOOKED row (its ledger status is wrong) carries NO sub-status and no basis; every
    # other row carries one CONTRACTS word
    typed = [r for r in rows if r["cause"] != "misbooked"]
    assert {r["sub_status"] for r in typed} <= set(CONTRACTS_BAD_FILE) and all(r["sub_status"] for r in typed)
    assert all(r["sub_status"] == "" == r["basis"] for r in rows if r["cause"] == "misbooked")
    assert {r["basis"] for r in typed} <= {"bytes", "detail", "inferred"}
    assert {r["cause"] for r in rows} <= set(B.CAUSES)
    assert all(r["free_to_fix"] == "n" for r in rows if r["cause"] == "html_is_the_work")
    assert all(r["bytes_kept_path"] and r["bytes_kept_length"] for r in rows if r["basis"] == "bytes")


def test_the_fixture_copy_in_a_fire_is_salted_after_the_trailer_only():
    data = _neg("CONSTRUCTED_tdm_stub_first_page.pdf")
    salted = H._salted(data, "x")
    assert salted.startswith(data) and salted[len(data):].startswith(b"\n% x salt ")
    from litkb.acquire import accept as A
    assert A.eof_in_tail(salted)


def test_shutil_is_not_used_to_move_anything_in_the_acceptance_module():
    """accept.py lives in acquire/, inside the no-delete scan; it imports shutil for `which` alone."""
    import ast
    src = (SCRIPTS / "pipeline" / "litkb" / "acquire" / "accept.py").read_text(encoding="utf-8")
    calls = {f"{n.func.value.id}.{n.func.attr}" for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)}
    assert {c for c in calls if c.startswith("shutil.")} == {"shutil.which"}
    assert shutil.which is not None

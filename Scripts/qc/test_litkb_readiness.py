"""litkb S4 — readiness: the fail-closed page probe, the one cap, the scan test, the OCR policy.

WHAT IS UNDER TEST is `litkb.extract.readiness` and the ONE call site in `litkb.admit.binding`
that used to decide the cap for itself. The kills, each on a known-bad input built here:

* a page count that cannot be READ refuses the OCR, where the old guard
  (``if n.isdigit() and int(n) > OCR_BIND_MAX_PAGES``) fell through and ran it uncapped —
  `test_binding_refuses_when_the_probe_cannot_answer`, the row `S4Q2-1` reinstates the old line;
* a truncated, empty, encrypted or page-less PDF raises `ProbeFailed` and never returns a number;
* `ocr_policy` never answers `cuda` on an unknown amount of free VRAM;
* `is_scan` reads the SHARE of a file's pages, so the two `has_text_layer = false` files that are
  fully extracted are not scans and the four real ones are.

NO GPU, NO DOCLING, NO DATABASE, NO CORPUS, NO NETWORK. Every PDF here is assembled in the test
(the shape `qc/test_litkb_inventory.py` uses), and the page-row fixture is
`qc/testdata/litkb_readiness/pages_rows.json`, which carries the read-only query and the stage-0
command that produced each of its rows. Nothing in this file skips: it is the baseline the
mutation ledger `qc/instruments/litkb_s4q2_mutations.py` measures its rows against, and a skipped
test there reads as a failed baseline.
"""
import json
import pathlib
import subprocess

import pytest

from litkb import config
from litkb.admit import binding
from litkb.extract import inventory, readiness

FIXTURES = pathlib.Path(__file__).resolve().parent / "testdata" / "litkb_readiness"


# ── PDFs, assembled here ────────────────────────────────────────────────────────────────

def _pdf(objects, root=1, extra_trailer=""):
    """A minimal PDF from 1-indexed object bodies, with a correct xref (as test_litkb_inventory)."""
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
    out += (f"trailer\n<</Size {len(objects) + 1}/Root {root} 0 R{extra_trailer}>>\nstartxref\n"
            f"{start}\n%%EOF\n").encode()
    return bytes(out)


def _page_objects(n):
    kids = " ".join(f"{3 + i} 0 R" for i in range(n))
    objs = [b"<</Type/Catalog/Pages 2 0 R>>",
            f"<</Type/Pages/Kids[{kids}]/Count {n}>>".encode()]
    objs += [b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>"] * n
    return objs


def pdf_of(path, n_pages):
    path.write_bytes(_pdf(_page_objects(n_pages)))
    return path


def encrypted_pdf(path):
    """A PDF whose /Encrypt dictionary the EMPTY user password does not authenticate.

    pdfium then fails the load with FPDF_ERR_PASSWORD (4), which is the code
    `_pdf_probe.PDFIUM_REASON` maps to `encrypted` — measured 2026-09-21, and the reason this
    fixture is built rather than downloaded: a real encrypted paper would put a copyrighted file
    in the repository to test one integer.
    """
    objs = _page_objects(1)
    objs.append(b"<</Filter/Standard/V 1/R 2/Length 40/O <" + b"AA" * 32
                + b">/U <" + b"BB" * 32 + b">/P -1>>")
    path.write_bytes(_pdf(objs, extra_trailer=f"/Encrypt {len(objs)} 0 R"
                                              f"/ID[<{'01' * 16}><{'01' * 16}>]"))
    return path


def zero_page_pdf(path):
    path.write_bytes(_pdf([b"<</Type/Catalog/Pages 2 0 R>>",
                           b"<</Type/Pages/Kids[]/Count 0>>"]))
    return path


# ── the probe: a number, or a reason — never None ───────────────────────────────────────

def test_probe_reads_a_real_page_count(tmp_path):
    for n in (1, 3, 17):
        assert readiness.probe_pages(pdf_of(tmp_path / f"p{n}.pdf", n)) == n


def test_probe_refuses_a_truncated_pdf(tmp_path):
    """The first 1,000 bytes of a valid 40-page PDF: a %PDF header, real objects, no xref."""
    whole = _pdf(_page_objects(40))
    assert len(whole) > 1000
    p = tmp_path / "truncated.pdf"
    p.write_bytes(whole[:1000])
    with pytest.raises(readiness.ProbeFailed) as e:
        readiness.probe_pages(p)
    assert e.value.reason == "unopenable"


def test_probe_refuses_an_empty_file(tmp_path):
    p = tmp_path / "zero.pdf"
    p.write_bytes(b"")
    with pytest.raises(readiness.ProbeFailed) as e:
        readiness.probe_pages(p)
    assert e.value.reason == "unopenable"


def test_probe_refuses_an_encrypted_pdf(tmp_path):
    with pytest.raises(readiness.ProbeFailed) as e:
        readiness.probe_pages(encrypted_pdf(tmp_path / "enc.pdf"))
    assert e.value.reason == "encrypted"


def test_probe_refuses_a_document_with_no_pages(tmp_path):
    with pytest.raises(readiness.ProbeFailed) as e:
        readiness.probe_pages(zero_page_pdf(tmp_path / "empty.pdf"))
    assert e.value.reason == "zero-pages"


def test_probe_refuses_a_file_that_is_not_there(tmp_path):
    with pytest.raises(readiness.ProbeFailed) as e:
        readiness.probe_pages(tmp_path / "absent.pdf")
    assert e.value.reason == "unopenable"


def test_probe_is_bounded_by_a_deadline(tmp_path):
    """A hostile PDF must not hang the caller: the probe is a child process with a timeout, and
    a timeout is `probe-error` — a refusal — not a number and not a hang."""
    with pytest.raises(readiness.ProbeFailed) as e:
        readiness.probe_pages(pdf_of(tmp_path / "ok.pdf", 2), timeout=0.001)
    assert e.value.reason == "probe-error"


def test_every_probe_failure_carries_a_reason_from_the_closed_set(tmp_path):
    bad = [tmp_path / "a.pdf", tmp_path / "b.pdf", tmp_path / "c.pdf"]
    bad[0].write_bytes(b"")
    bad[1].write_bytes(b"not a pdf at all, just some bytes\n" * 40)
    encrypted_pdf(bad[2])
    for p in bad:
        with pytest.raises(readiness.ProbeFailed) as e:
            readiness.probe_pages(p)
        assert e.value.reason in readiness.PROBE_REASONS


def test_a_probe_failure_cannot_invent_a_reason():
    with pytest.raises(ValueError):
        raise readiness.ProbeFailed("looks-fine-to-me")


def test_the_probe_child_maps_every_pdfium_code(tmp_path):
    """The mapping table itself, so a pdfium upgrade that renumbers is a failing test rather than
    a silent reclassification. The codes are pdfium's (FPDF_GetLastError); the reasons are ours."""
    import importlib.util

    src = pathlib.Path(readiness._PROBE)
    spec = importlib.util.spec_from_file_location("_pdf_probe_undertest", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.classify_load_failure(4) == "encrypted"
    assert mod.classify_load_failure(5) == "encrypted"
    assert mod.classify_load_failure(3) == "unopenable"
    assert mod.classify_load_failure(0) == "zero-pages"
    assert mod.classify_load_failure(99) == "probe-error"
    assert mod.classify_load_failure(None) == "probe-error"
    # the branch no fixture in this repository reaches: a document pdfium DOES open because the
    # empty user password authenticates, encrypted with an OWNER password only. It is a refusal
    # for the same reason the password branch is.
    assert mod.classify_opened(-1, 7) == (7, None)
    assert mod.classify_opened(3, 7) == (None, "encrypted")
    assert mod.classify_opened(-1, 0) == (None, "zero-pages")


# ── the cap: one home, and it refuses what it cannot read ───────────────────────────────

def test_the_cap_has_one_home():
    assert readiness.PAGE_CAP == config.PAGE_CAP == binding.OCR_BIND_MAX_PAGES
    assert binding.OCR_BIND_MAX_PAGES < 688      # the corpus's book, the reason the cap exists


def test_the_cap_override_refuses_junk():
    assert config.page_cap({}) == config.PAGE_CAP_DEFAULT
    assert config.page_cap({"LITKB_PAGE_CAP": ""}) == config.PAGE_CAP_DEFAULT
    assert config.page_cap({"LITKB_PAGE_CAP": "0"}) == config.PAGE_CAP_DEFAULT
    assert config.page_cap({"LITKB_PAGE_CAP": "-5"}) == config.PAGE_CAP_DEFAULT
    assert config.page_cap({"LITKB_PAGE_CAP": "four hundred"}) == config.PAGE_CAP_DEFAULT
    assert config.page_cap({"LITKB_PAGE_CAP": " 50 "}) == 50


def test_cap_check():
    assert readiness.cap_check(1) is None
    assert readiness.cap_check(readiness.PAGE_CAP) is None
    assert readiness.cap_check(readiness.PAGE_CAP + 1) == "over-page-cap"
    for junk in (None, "400", 0, -1, 12.5, True):
        assert readiness.cap_check(junk) == "over-page-cap"


# ── the binding call site: fail closed ──────────────────────────────────────────────────

def _no_docling(monkeypatch):
    """Record whether the OCR route got as far as looking for a docling environment."""
    from litkb.extract import docling as D

    seen = []
    monkeypatch.setattr(D, "worker_available", lambda python=None: bool(seen.append(python)))
    return seen


def test_binding_refuses_when_the_probe_cannot_answer(tmp_path, monkeypatch):
    """THE FAIL-CLOSED KILL. The old line read the count from poppler and refused only
    `if n.isdigit() and int(n) > OCR_BIND_MAX_PAGES` — so a count that could not be read fell
    through the guard and OCR ran uncapped, on exactly the files least likely to survive it."""
    seen = _no_docling(monkeypatch)
    p = tmp_path / "damaged.pdf"
    p.write_bytes(_pdf(_page_objects(40))[:1000])
    refusals = []
    assert binding.ocr_first_pages(p, refusals=refusals) == ""
    assert refusals == ["page-probe-failed"]
    assert seen == [], "the OCR route was entered although the page count was unreadable"


def test_binding_refuses_a_document_over_the_cap(tmp_path, monkeypatch):
    seen = _no_docling(monkeypatch)
    big = pdf_of(tmp_path / "book.pdf", readiness.PAGE_CAP + 1)
    assert readiness.probe_pages(big) == readiness.PAGE_CAP + 1
    refusals = []
    assert binding.ocr_first_pages(big, refusals=refusals) == ""
    assert refusals == ["over-page-cap"]
    assert seen == []


def test_binding_does_not_refuse_a_paper_at_the_cap(tmp_path, monkeypatch):
    """THE CONTROL, without which the two rows above would also pass with the cap set to zero or
    with the probe wired to fail: a readable document inside the cap gets as far as asking whether
    a docling environment exists, which is a different answer from "too big"."""
    seen = _no_docling(monkeypatch)
    ok = pdf_of(tmp_path / "paper.pdf", readiness.PAGE_CAP)
    refusals = []
    assert binding.ocr_first_pages(ok, refusals=refusals) == ""
    assert seen == [None]
    assert refusals == ["no-worker"]


def test_every_binding_refusal_code_is_in_the_closed_set(tmp_path, monkeypatch):
    seen = _no_docling(monkeypatch)
    del seen
    cases = [pdf_of(tmp_path / "a.pdf", 2), pdf_of(tmp_path / "b.pdf", readiness.PAGE_CAP + 1)]
    cases.append(tmp_path / "c.pdf")
    cases[-1].write_bytes(b"")
    for p in cases:
        refusals = []
        binding.ocr_first_pages(p, refusals=refusals)
        assert refusals and refusals[0] in binding.OCR_BIND_REFUSALS


def test_a_refused_ocr_says_which_refusal_in_the_binding_evidence(tmp_path, monkeypatch):
    """`ocr_attempted: True` alone cannot tell a book from a machine with no GPU."""
    monkeypatch.setattr(binding, "first_page_text", lambda _p: "\f")
    monkeypatch.setattr(binding, "pdf_info", lambda _p: {})
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"")
    b = binding.bind_any_with_ocr(p, ["A Title Nobody Prints"], "Nobody")
    assert b["ocr_attempted"] is True
    assert b["ocr_refusal"] == "page-probe-failed"
    assert b["text_layer"] is False


# ── free VRAM: a number, or UNKNOWN ─────────────────────────────────────────────────────

class _Ran:
    def __init__(self, rc=0, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def test_vram_free_is_total_minus_used(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Ran(0, "642, 4096\n"))
    assert readiness.vram_free_mib() == 4096 - 642


@pytest.mark.parametrize("outcome", ["missing", "nonzero", "empty", "junk", "timeout"])
def test_vram_free_is_none_when_nvidia_smi_does_not_answer(monkeypatch, outcome):
    def run(*_a, **_k):
        if outcome == "missing":
            raise FileNotFoundError("nvidia-smi")
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("nvidia-smi", 15)
        return _Ran({"nonzero": 9}.get(outcome, 0),
                    {"empty": "", "junk": "no such device\n"}.get(outcome, "642, 4096\n"))
    monkeypatch.setattr(subprocess, "run", run)
    assert readiness.vram_free_mib() is None


# ── the OCR policy ──────────────────────────────────────────────────────────────────────

def test_unknown_free_vram_is_never_cuda():
    for n in (0, 1, 11, 124, 125, 10_000):
        assert readiness.ocr_policy(n, True, None)[1] != "cuda"


def test_ocr_off_is_a_residue_however_much_vram_is_free():
    for free in (None, 0, 4096, 1_000_000):
        assert readiness.ocr_policy(11, False, free) == ("residue", "scan-needs-ocr")


def test_enough_free_vram_runs_on_cuda():
    need = readiness.OCR_NEED_MIB + readiness.VRAM_MARGIN_MIB
    assert readiness.ocr_policy(11, True, need) == ("run", "cuda")
    assert readiness.ocr_policy(10_000, True, need) == ("run", "cuda")
    assert readiness.ocr_policy(11, True, need - 1) != ("run", "cuda")


def test_below_the_vram_need_the_cpu_runs_only_under_the_measured_page_bound():
    tight = readiness.OCR_NEED_MIB + readiness.VRAM_MARGIN_MIB - 1
    assert readiness.ocr_policy(readiness.CPU_OCR_MAX_PAGES, True, tight) == ("run", "cpu")
    assert readiness.ocr_policy(readiness.CPU_OCR_MAX_PAGES + 1, True, tight) \
        == ("residue", "scan-needs-ocr")
    assert readiness.ocr_policy(readiness.CPU_OCR_MAX_PAGES + 1, True, None) \
        == ("residue", "scan-needs-ocr")


def test_the_cpu_page_bound_is_the_measured_rate_times_the_budget():
    assert readiness.CPU_OCR_MAX_PAGES == int(readiness.CPU_OCR_BUDGET_S
                                              * readiness.CPU_OCR_PAGES_PER_S)
    assert readiness.CPU_OCR_PAGES_PER_S > 0
    assert readiness.OCR_NEED_MIB > 0


# ── per page, and per file ──────────────────────────────────────────────────────────────

def test_page_needs_ocr():
    assert readiness.page_needs_ocr("image-only") is True
    assert readiness.page_needs_ocr("image-only", 1.0) is True
    assert readiness.page_needs_ocr("text", None) is False
    assert readiness.page_needs_ocr("empty", None) is False
    # partial with no coverage evidence is stage 0's answer, exactly
    assert readiness.page_needs_ocr("partial", None) is True
    assert readiness.page_needs_ocr("partial", None) == inventory.needs_ocr("partial")
    assert readiness.page_needs_ocr("partial", 0.95) is False
    assert readiness.page_needs_ocr("partial", readiness.PARTIAL_COVERAGE_MIN) is False
    assert readiness.page_needs_ocr("partial", readiness.PARTIAL_COVERAGE_MIN - 0.01) is True
    assert readiness.page_needs_ocr("partial", "not a number") is True


def _fixture():
    return json.loads((FIXTURES / "pages_rows.json").read_text(encoding="utf-8"))


def test_the_fixture_says_where_every_row_came_from():
    fx = _fixture()
    assert "litkb.pages" in fx["_source"]["db_rows"]
    assert "probe_file" in fx["_source"]["stage0"]
    assert set(fx["files"]) == {
        "Abdulkader_2020_cnn-fpga-implementation-hardware",
        "Crowder_2017_introduction-bernoulli-cusum",
        "Anderson_1957_statistical-inference-about-markov",
        "Hudson_1978_natural-identity-exponential-families",
        "Hwang_1982_improving-upon-standard-estimators",
        "Ogata_1998_space-time-point-process"}


def test_has_text_layer_false_does_not_make_a_file_a_scan():
    """All six files carry `has_text_layer = false`. Two of them hold 18,064 and 1,212 blocks —
    they are extracted, and a classifier that called them scans would send them to the GPU."""
    fx = _fixture()["files"]
    for key in ("Abdulkader_2020_cnn-fpga-implementation-hardware",
                "Crowder_2017_introduction-bernoulli-cusum"):
        assert fx[key]["has_text_layer"] is False
        assert readiness.is_scan(fx[key]["pages"]) is False, key


def test_the_four_real_scans_are_scans():
    fx = _fixture()["files"]
    for key in ("Anderson_1957_statistical-inference-about-markov",
                "Hudson_1978_natural-identity-exponential-families",
                "Hwang_1982_improving-upon-standard-estimators",
                "Ogata_1998_space-time-point-process"):
        assert readiness.is_scan(fx[key]["pages"]) is True, key


def test_is_scan_reads_the_share_not_page_one():
    """Page 1 native over a scanned body — the case `has_text_layer` reads as "has a text layer"."""
    rows = [{"page_no": 1, "page_class": "text", "coverage_share": 1.0}]
    rows += [{"page_no": i, "page_class": "image-only", "coverage_share": None}
             for i in range(2, 12)]
    assert readiness.is_scan(rows) is True
    # and the mirror: one scanned page in a native paper is not a scan
    rows = [{"page_no": 1, "page_class": "image-only", "coverage_share": None}]
    rows += [{"page_no": i, "page_class": "text", "coverage_share": 1.0} for i in range(2, 12)]
    assert readiness.is_scan(rows) is False


def test_is_scan_sits_on_the_threshold():
    half = ([{"page_class": "image-only"}] * 5) + ([{"page_class": "text"}] * 5)
    assert readiness.SCAN_FILE_FRAC == inventory.SCAN_FILE_FRAC == 0.5
    assert readiness.is_scan(half) is True
    assert readiness.is_scan(([{"page_class": "image-only"}] * 4)
                             + ([{"page_class": "text"}] * 6)) is False


def test_is_scan_reads_a_stage_zero_record_too():
    """stage 0 names the class `scan`; the database names it `page_class`. Same vocabulary."""
    assert readiness.is_scan([{"page": i, "scan": "image-only"} for i in range(1, 6)]) is True
    assert readiness.is_scan([{"page": i, "scan": "text"} for i in range(1, 6)]) is False


def test_no_page_rows_is_not_a_scan():
    assert readiness.is_scan([]) is False
    assert readiness.is_scan(None) is False


# ── what an extraction RESULT is ────────────────────────────────────────────────────────

def test_classify_extraction():
    native = [{"page_class": "text", "coverage_share": 1.0} for _ in range(10)]
    scan = [{"page_class": "image-only", "coverage_share": None} for _ in range(10)]
    assert readiness.classify_extraction(native, 1) == "extracted"
    assert readiness.classify_extraction(scan, 1) == "extracted"
    assert readiness.classify_extraction(native, 0) == "zero-content"
    assert readiness.classify_extraction(scan, 0) == "scan-needs-ocr"
    assert readiness.classify_extraction([], 0) == "zero-content"
    assert readiness.classify_extraction(native, None) == "zero-content"


def test_a_real_scan_with_no_blocks_is_scan_needs_ocr_not_zero_content():
    """`Hwang_1982` live: bound, 0 runs, 0 blocks. Before S4 that read `bound-unextracted` with no
    reason; a zero-block run on it would have read `extracted, blocks: 0`."""
    rows = _fixture()["files"]["Hwang_1982_improving-upon-standard-estimators"]["pages"]
    assert readiness.classify_extraction(rows, 0) == "scan-needs-ocr"
    assert readiness.classify_extraction(rows, 148) == "extracted"

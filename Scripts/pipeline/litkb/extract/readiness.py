"""Is this file ready to extract, on what device, and if not — what class of residue is it?

The eight questions S4 asks BEFORE a conversion starts, in one module, because before S4 they were
asked in four places and three of them were too late to act on:

* the page count came from `pdfinfo` at ADMIT time (`litkb.admit.binding.pdf_info`), from pypdfium2
  inside stage 0, and from pypdfium2 inside the docling worker subprocess — the last two after the
  decision to convert had already been taken (S4 survey-code §9);
* the cap was `if n.isdigit() and int(n) > OCR_BIND_MAX_PAGES: return ""`, which FALLS THROUGH when
  the count cannot be read. A probe that fails let a book through; a probe that succeeded stopped
  one. That is fail-open, and it is the hole S4's done-state (c) names;
* "is this a scan" was `files.has_text_layer`, a PAGE-1-ONLY measurement taken at binding
  (`litkb.admit.binding.bind`). Live it is wrong in both directions: 2 of the 6 files with
  `has_text_layer = false` are fully extracted, 18,064 and 1,212 blocks (S4 survey-data §1.4);
* nothing anywhere asked what the GPU had free before handing docling a CUDA device.

WHAT THIS MODULE IS NOT. It runs no tool and writes no row. Every function here is pure except
:func:`probe_pages` (one subprocess) and :func:`vram_free_mib` (one `nvidia-smi`), so a caller can
be tested against it without a GPU, without docling and without a database.

FAIL CLOSED IS THE WHOLE POINT. :func:`probe_pages` never returns ``None`` and never guesses:
either it read a page count or it raises :class:`ProbeFailed` with a reason out of
:data:`PROBE_REASONS`. :func:`ocr_policy` never answers ``cuda`` on an unknown amount of free VRAM.
An answer nobody can act on is a refusal, and a refusal is a classified residue — which is what S4
means by "everything acquired is readable or classified".

THE NUMBERS. `OCR_NEED_MIB` and `CPU_OCR_PAGES_PER_S` are runs, not estimates:
``qc/instruments/litkb_ocr_vram.py`` -> ``Reports/LITKB_OCR_VRAM_2026-09-21.csv``, on the T2000
over the corpus's two real scans. Each constant names its row below.
"""
import os
import pathlib
import subprocess
import sys

from litkb import config
from litkb.extract import inventory, reconcile

#: The largest document litkb converts, in pages. ONE home, `litkb.config.PAGE_CAP`
#: (`LITKB_PAGE_CAP` overrides). `admit.binding.OCR_BIND_MAX_PAGES` reads it from here, so the
#: binding route and the extraction route can no longer answer "too big?" from two constants.
PAGE_CAP = config.PAGE_CAP

#: The closed set of reasons :class:`ProbeFailed` carries. `unopenable` — pdfium would not load
#: the bytes (truncated, empty, not a PDF, not there). `encrypted` — a password or a security
#: handler stands between litkb and the pages. `zero-pages` — the document holds none.
#: `probe-error` — the probe itself did not answer: no pypdfium2, a child that crashed or printed
#: something unreadable, or a deadline. See `_pdf_probe.PDFIUM_REASON` for the measured mapping.
PROBE_REASONS = ("unopenable", "encrypted", "zero-pages", "probe-error")

#: Seconds the page probe is given. It is a page count off an already-open document: the two real
#: scans answer in 0.23 s wall including interpreter start (measured 2026-09-21, five runs on
#: `Hwang_1982`: 0.234 / 0.228 / 0.226 / 0.260 / 0.246 s), so 30 s is two orders of magnitude of
#: room and still a bound. `LITKB_PROBE_TIMEOUT` overrides for a slow or contended disk.
PROBE_TIMEOUT_S = float(os.environ.get("LITKB_PROBE_TIMEOUT") or 30.0)

#: The child: `_pdf_probe.py`, run as a SCRIPT (never imported). Its docstring carries the three
#: reasons it is a separate process run with ``-P`` and importing no litkb.
_PROBE = str(pathlib.Path(__file__).resolve().parent / "_pdf_probe.py")

#: VRAM an OCR conversion needs, over the card's baseline, in MiB. MEASURED: the largest
#: `peak_over_baseline_mib` in `Reports/LITKB_OCR_VRAM_2026-09-21.csv` — row `hwang-cuda-c8`,
#: 1,994 MiB (2,690 of 4,096, 65.7 %). The six CUDA rows span 1,417–1,994 MiB over two files and
#: three chunk sizes, and the LARGEST is the one a policy has to hold. The record this extends is
#: `Reports/LITKB_DOCLING_LOCAL_2026-09-15.md` §8.3's +1,662 MiB for Anderson_1957: that was one
#: conversion, this is a worker PROCESS over a chunk list, which is the shape a queue job has.
#:
#: CHUNKING IS NOT A VRAM KNOB, which is the other thing these rows say. Splitting a 22-page scan
#: into 4-page ranges RAISED the peak (1,780 MiB at chunk 4, 1,490 at 8, 1,417 at one chunk) and
#: cost rate (0.449 / 0.500 / 0.538 pages/s), because the pool is a high-water mark over the
#: process and more jobs mean more allocator churn, not less. Chunking is for page-range control,
#: not for memory.
OCR_NEED_MIB = 1994

#: Headroom, in MiB. Design §12's rule is to leave a fifth of the card free, and the T2000 has
#: 4,096 MiB that also drive this desktop: 20 % is 819. This is a RULE, not a measurement — it is
#: why `Reports/LITKB_P5_BULK_2026-09-16.md` §7's 3,881 MiB / 94.8 % counted as a breach although
#: nothing failed. `LITKB_VRAM_MARGIN_MIB` overrides on a card with a different total.
VRAM_MARGIN_MIB = int(os.environ.get("LITKB_VRAM_MARGIN_MIB") or 819)

#: Pages per second for docling OCR on the CPU. MEASURED: the SLOWEST of the three `hwang-cpu-c4*`
#: rows of `Reports/LITKB_OCR_VRAM_2026-09-21.csv` — 11 pages in 145.45 s, 0.0756 p/s, on the CPU
#: docling venv with the same OCR settings the CUDA rows used (the other two: 0.0765, 0.0782). The
#: slowest row, because a page bound built on the fastest is a bound that times out.
#:
#: HOW TIGHT THIS IS, stated rather than hidden: a fourth pass earlier the same day measured
#: **0.0689 p/s** on the same file and the same venv, and its CSV was replaced by the tracked run.
#: At that rate the 136-page bound below is 1,974 s — past :data:`CPU_OCR_BUDGET_S`, so the job it
#: admits would be killed by the very timeout the bound exists to avoid. The bound is therefore
#: honest about the MEASURED rate and is not a guarantee; what it buys is that a 700-page scan is
#: never started on a CPU, which is the failure it was written for. A second day's runs, or a
#: derate agreed with Kam, is the way to close the remaining ~10 %.
CPU_OCR_PAGES_PER_S = 0.0756

#: How long litkb is willing to spend OCR-ing one file on the CPU. NOT a measurement: it is the
#: timeout `admit.binding.ocr_first_pages` already passes to docling (1,800 s), i.e. the point at
#: which litkb's own code gives up on an OCR conversion. A file that cannot finish inside it would
#: be killed by that timeout anyway, so refusing it up front turns a timeout into a classified
#: residue.
CPU_OCR_BUDGET_S = 1800

#: The CPU page bound, derived from the two above: 1,800 s x 0.0756 p/s = 136 pages.
CPU_OCR_MAX_PAGES = int(CPU_OCR_BUDGET_S * CPU_OCR_PAGES_PER_S)

#: A `partial` page's coverage below which nothing read it. `reconcile.COVERAGE_FLOOR` — the SAME
#: 0.80 the reconciliation already calls "this page's native layer was not covered" — so the floor
#: has one home. Live it splits the 96 `partial` pages 92 above / 4 below (read-only query,
#: 2026-09-21: `SELECT page_class, count(*) FILTER (WHERE coverage_share < 0.8) FROM litkb.pages
#: GROUP BY 1` -> text 15,884 / 52 below, partial 96 / 4 below, image-only 13 / 0 below).
PARTIAL_COVERAGE_MIN = reconcile.COVERAGE_FLOOR

#: The share of OCR-needing pages at which a FILE is a scan. `inventory.SCAN_FILE_FRAC` (0.5) —
#: the rule `inventory.route_file` already applies to stage-0 page records, applied here to a
#: file's page rows whatever produced them.
SCAN_FILE_FRAC = inventory.SCAN_FILE_FRAC


class ProbeFailed(RuntimeError):
    """The page count could not be read. ``.reason`` is one of :data:`PROBE_REASONS`.

    It is an exception rather than a sentinel because every caller of :func:`probe_pages` must
    decide what to do about it, and a ``None`` return is the shape a caller forgets to check —
    which is exactly how the admit-time cap came to fall through on an unreadable count.
    """

    def __init__(self, reason, detail=""):
        # BEGIN guard: a probe failure carries a reason out of the closed set
        if reason not in PROBE_REASONS:
            raise ValueError(f"ProbeFailed: {reason!r} is not one of {PROBE_REASONS}")
        # END guard: a probe failure carries a reason out of the closed set
        self.reason = reason
        self.detail = str(detail or "")
        super().__init__(f"{reason}: {self.detail}" if self.detail else reason)


def probe_pages(path, timeout=None):
    """-> the PDF's page count, or raise :class:`ProbeFailed`. Never returns ``None``.

    pypdfium2 in a child process with a deadline: see `_pdf_probe.py` for why it is a subprocess
    (a C library that hangs cannot be timed out inside this process), why it is run with ``-P``,
    and why it imports no litkb.
    """
    import json

    cmd = [sys.executable, "-P", _PROBE, str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=PROBE_TIMEOUT_S if timeout is None else float(timeout))
    except subprocess.TimeoutExpired:
        raise ProbeFailed("probe-error", f"the page probe did not answer within "
                                         f"{PROBE_TIMEOUT_S if timeout is None else timeout}s") \
            from None
    except OSError as exc:
        raise ProbeFailed("probe-error", f"{type(exc).__name__}: {exc}") from None
    try:
        out = json.loads(proc.stdout or "")
    except ValueError:
        raise ProbeFailed("probe-error",
                          f"the probe exited {proc.returncode} with no readable answer: "
                          f"{(proc.stderr or proc.stdout or '')[-300:]}") from None
    # BEGIN guard: the page probe answers with a count or with a reason, never with neither
    if isinstance(out.get("pages"), int) and out["pages"] > 0:
        return out["pages"]
    reason = out.get("reason")
    raise ProbeFailed(reason if reason in PROBE_REASONS else "probe-error",
                      out.get("error") or "")
    # END guard: the page probe answers with a count or with a reason, never with neither


def cap_check(pages):
    """-> ``'over-page-cap'`` when this document is past :data:`PAGE_CAP`, else ``None``.

    Its only sanctioned input is :func:`probe_pages`'s return, which is always a positive int.
    Anything else is refused rather than passed — a cap that answers "fine" to a page count it
    could not understand is the fail-open shape this module was written to remove — but the
    caller that reaches that branch has skipped the probe, and `page-probe-failed` is the truer
    name for what happened there.
    """
    # BEGIN guard: the cap refuses a count it cannot read, and never passes one
    if not isinstance(pages, int) or isinstance(pages, bool) or pages <= 0:
        return "over-page-cap"
    return "over-page-cap" if pages > PAGE_CAP else None
    # END guard: the cap refuses a count it cannot read, and never passes one


def vram_free_mib():
    """-> free VRAM in MiB, or ``None`` when nvidia-smi is absent, fails or answers unusably.

    ``None`` means UNKNOWN, and :func:`ocr_policy` treats unknown as "not enough" — never as
    "assume it is free". A machine with no NVIDIA driver and a machine whose card is full look the
    same to a policy that guesses, and only one of them is safe to run CUDA on.
    """
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        used, total = (int(x.strip()) for x in lines[0].split(",")[:2])
    except (ValueError, IndexError):
        return None
    return max(0, total - used)


def page_needs_ocr(page_class, coverage_share=None):
    """Does this ONE page need OCR to be read?

    ``image-only`` always: there is a raster over the page and under
    :data:`inventory.CHARS_TRACE` characters of text layer, so nothing but OCR will read it.

    ``partial`` — a raster over at least :data:`inventory.IMAGE_COVER` of the page with some text
    but less than a body's worth — depends on what an extraction made of it. With no coverage
    evidence (``coverage_share`` ``None``, which is every page before a run exists) the answer is
    the one :func:`inventory.needs_ocr` gives stage 0: yes. With coverage evidence, a partial page
    whose native layer the reconciliation DID cover was read, and sending it to OCR would spend
    GPU on a page litkb already has. Live that is 92 of the 96 partial pages.

    THIS IS NOT A SECOND COPY OF :func:`inventory.needs_ocr`. That function answers stage 0's
    ROUTING question, before any run exists and with no coverage to read; this one answers the
    READINESS question with a run's per-page evidence in hand. They agree exactly wherever the
    evidence is absent, which is the only input they share.
    """
    if page_class == "image-only":
        return True
    if page_class == "partial":
        if coverage_share is None:
            return True
        try:
            return float(coverage_share) < PARTIAL_COVERAGE_MIN
        except (TypeError, ValueError):
            return True
    return False


def _page_rows(pages_rows):
    """(page_class, coverage_share) per row, from a DB `pages` row or a stage-0 page record.

    The database calls the class `page_class`; stage 0's `page_detail` entries call the same
    vocabulary `scan` (`inventory.classify_page` -> `_page_measure`'s ``scan=`` field). Both are
    read, so a caller holding either can ask this module the same question — and a stage-0 record
    carries no coverage at all, which is the ``None`` :func:`page_needs_ocr` is written for.
    """
    for r in pages_rows or ():
        if isinstance(r, str):
            yield r, None
        else:
            yield (r.get("page_class", r.get("scan")), r.get("coverage_share"))


def is_scan(pages_rows):
    """Is the WHOLE FILE a scan — at least :data:`SCAN_FILE_FRAC` of its pages needing OCR?

    This replaces `files.has_text_layer` as the classifier. `has_text_layer` stays where it is and
    keeps meaning what it has always meant — "page 1 carried at least
    `binding.MIN_TEXT_CHARS` characters for pdftotext", a BINDING fact — and it is not a scan
    test: live, `Abdulkader_2020` and `Crowder_2017` are `has_text_layer = false` and fully
    extracted (18,064 and 1,212 blocks), while their page rows put only 21 % and 0 % of pages in
    the OCR-needing classes (`qc/testdata/litkb_readiness/pages_rows.json`, which carries the
    query and the stage-0 command behind every row).

    A file with no page rows is NOT a scan: no evidence is not evidence of a scan, and the caller
    that has no rows has a `zero-content` or an unextracted file, not a classified one.
    """
    rows = list(_page_rows(pages_rows))
    if not rows:
        return False
    ocr = sum(1 for cls, share in rows if page_needs_ocr(cls, share))
    # BEGIN guard: a file is a scan on the SHARE of its pages, never on page 1
    return bool(ocr) and (ocr / len(rows)) >= SCAN_FILE_FRAC
    # END guard: a file is a scan on the SHARE of its pages, never on page 1


def ocr_policy(n_ocr_pages, ocr_enabled, free_mib):
    """-> ``('run', 'cuda'|'cpu')`` or ``('residue', 'scan-needs-ocr')``.

    Three refusals and two ways to run, in this order:

    1. OCR off — the caller did not ask for it, or the route says not to — is a residue, not a
       silent native conversion. That is the "extracted, 0 chars" outcome S4 exists to end: with
       OCR off on an image-only page docling succeeds and produces no body block.
    2. Free VRAM at least :data:`OCR_NEED_MIB` + :data:`VRAM_MARGIN_MIB` runs on ``cuda``.
       ``free_mib`` ``None`` is UNKNOWN and never reaches this branch.
    3. Otherwise the CPU, but only under :data:`CPU_OCR_MAX_PAGES` — 136 pages, the most
       0.0756 pages/s finishes inside the 1,800 s litkb already gives a docling OCR call. Above
       it, a residue: a job that will be killed by a timeout is better named before it starts.
    """
    # BEGIN guard: OCR that was not asked for is a residue, never a silent no-OCR conversion
    if not ocr_enabled:
        return ("residue", "scan-needs-ocr")
    # END guard: OCR that was not asked for is a residue, never a silent no-OCR conversion
    # BEGIN guard: cuda only on a KNOWN free amount that covers the need plus the margin
    if isinstance(free_mib, int) and not isinstance(free_mib, bool) \
            and free_mib >= OCR_NEED_MIB + VRAM_MARGIN_MIB:
        return ("run", "cuda")
    # END guard: cuda only on a KNOWN free amount that covers the need plus the margin
    # BEGIN guard: the CPU fallback is bounded by the measured CPU rate
    try:
        n = int(n_ocr_pages)
    except (TypeError, ValueError):
        return ("residue", "scan-needs-ocr")
    if n <= CPU_OCR_MAX_PAGES:
        return ("run", "cpu")
    return ("residue", "scan-needs-ocr")
    # END guard: the CPU fallback is bounded by the measured CPU rate


def classify_extraction(pages_rows, canonical_blocks):
    """What an extraction RESULT is: ``extracted`` / ``zero-content`` / ``scan-needs-ocr``.

    Blocks decide readability; the page rows decide what the absence of blocks MEANS. A native
    document that produced nothing is `zero-content` — a defect to look at. A scan that produced
    nothing is `scan-needs-ocr` — a file waiting for a device, which is a different queue and a
    different next move.
    """
    # BEGIN guard: a run with no canonical block never reads as extracted
    try:
        n = int(canonical_blocks)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return "extracted"
    return "scan-needs-ocr" if is_scan(pages_rows) else "zero-content"
    # END guard: a run with no canonical block never reads as extracted

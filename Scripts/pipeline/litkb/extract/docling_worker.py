"""The Docling side of the stage-3 adapter — runs ONLY in the extraction venv.

This module is executed by ``D:\\edmonds-pipeline\\venv-docling\\Scripts\\python.exe`` as a
subprocess (see :func:`litkb.extract.docling.run`). It imports torch, transformers and
docling, none of which belong in the project's environment (design referee M9), and it
writes its result as a DoclingDocument JSON plus a metrics JSON. Nothing in the project
imports this file; ``qc/check.py`` only compiles it, and a compile needs no docling.

WHY A SUBPROCESS AND NOT AN IMPORT: the heavy venv is 1.4 GB of torch and friends, plus 1.1 GB of downloaded models (measured 2026-09-15). Putting
it on the project's `sys.path` would make the ladder, the preflight and every QC script
depend on it. The subprocess boundary is also where the measurement lives: peak RSS is a
property of the process that ran the model, and this process runs nothing else.

CWD IS LOAD-BEARING. ``D:\\edmonds-pipeline\\secrets\\`` is a directory, and Python puts the
script's directory (or the cwd, for ``-c``) at the head of ``sys.path``: numpy's
``bit_generator`` does ``from secrets import randbits`` and dies with ``ImportError: cannot
import name randbits`` when a directory or file named ``secrets`` shadows the stdlib module
(measured 2026-09-15). The launcher therefore chooses the cwd; never run this from the
pipeline root.

BATCH, NOT ONE-SHOT. The converter's first call loads the layout and TableFormer weights
(measured 2026-09-15: 59.4 s wall for a 2-page convert cold, 3.6 s for a 2-page convert once
warm). A per-file process would pay that on every file and report it as extraction time. So one
process takes a JOB LIST and times each job separately, after a warm-up job that is
excluded from the record.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time

# THIS FILE'S OWN DIRECTORY MUST NOT BE ON sys.path. Beside it sits ``docling.py`` — the
# project's adapter — and Python puts a script's directory at the head of sys.path, so
# ``import docling`` finds the ADAPTER instead of the installed package and dies with
# "No module named 'docling.datamodel'; 'docling' is not a package" (measured 2026-09-15).
# The launcher also passes ``-P``; this scrub is the belt to that suspenders, because a
# human running the worker by hand will not.
_SELF_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path
               if p and os.path.abspath(p) not in (_SELF_DIR, os.path.abspath(os.getcwd()))]

EXTRACTOR_BASE = "docling"


def _accelerator(num_threads, device):
    from docling.datamodel.accelerator_options import AcceleratorOptions
    return AcceleratorOptions(num_threads=num_threads, device=device)


def build_converter(ocr=False, ocr_engine=None, tables=True, formula=False,
                    num_threads=4, device="cpu", ocr_backend=None, page_batch=None):
    """One DocumentConverter, configured once and reused for every job in the batch.

    ``page_batch`` caps how many pages the pipeline holds in flight at once
    (``docling.datamodel.settings.settings.perf.page_batch_size``, default 4). It is the knob
    docling names for VRAM, and MEASURED IT IS NOT ONE: over a real OCR batch the peak is flat
    across 4 / 2 / 1 (3,873 / 3,842 / 3,893 MiB), because what dominates is the resident models
    plus torch's cached pool rather than the per-page activations this governs. The VRAM block
    in :mod:`litkb.extract.docling` carries the five rows and the two knobs that DO move it.
    This pipeline therefore leaves it at docling's default and records it anyway.

    It is a process-wide SETTING rather than a pipeline option in docling 2.127.0, which is why
    it is set here — beside the converter it governs — and recorded in every metrics row: a
    number the run did not record is a number the next reader has to guess at."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.settings import settings
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # BEGIN guard: the page batch is capped before the converter is built
    if page_batch:
        settings.perf.page_batch_size = int(page_batch)
    # END guard: the page batch is capped before the converter is built
    opts = PdfPipelineOptions()
    opts.do_ocr = bool(ocr)
    opts.do_table_structure = bool(tables)
    opts.do_formula_enrichment = bool(formula)
    opts.accelerator_options = _accelerator(num_threads, device)
    if ocr and ocr_engine:
        # docling 2.127.0: the factory's method is create_options(kind=...), and it returns
        # the options INSTANCE, not the class (there is no get_options).
        #
        # BACKEND, not just engine. RapidOcrOptions defaults to backend="onnxruntime", and
        # onnxruntime is NOT installed here, so an explicit `--ocr-engine rapidocr` fails
        # with "ImportError: onnxruntime is not installed" while docling's own `auto` runs
        # happily — auto falls through to rapidocr with the TORCH backend (measured
        # 2026-09-15, log line "Auto OCR model selected rapidocr with torch."). Pinning the
        # engine without pinning the backend therefore does NOT reproduce the auto run.
        from docling.models.factories import get_ocr_factory
        o = get_ocr_factory().create_options(kind=ocr_engine)
        if ocr_backend and hasattr(o, "backend"):
            o.backend = ocr_backend
        opts.ocr_options = o
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return conv, opts


class _RssSampler(threading.Thread):
    """Peak working set of THIS process while one job runs.

    ``psutil.Process().memory_info().peak_wset`` is a LIFETIME high-water mark on Windows, so
    in a batch process it reports the largest job the process ever ran, not this one. The
    per-job number therefore has to be sampled. Both are recorded: ``peak_rss_bytes`` is this
    job's sampled peak, ``lifetime_peak_wset_bytes`` is the process's mark at the end of it.
    """

    def __init__(self, interval=0.2):
        super().__init__(daemon=True)
        self.interval = interval
        self._stopping = threading.Event()
        self.peak = 0
        self.samples = 0

    def run(self):
        import psutil
        p = psutil.Process()
        while not self._stopping.is_set():
            try:
                rss = p.memory_info().rss
            except Exception:  # noqa: BLE001 - a sampler must never kill the run
                rss = 0
            if rss > self.peak:
                self.peak = rss
            self.samples += 1
            self._stopping.wait(self.interval)

    def stop(self):
        self._stopping.set()
        self.join(timeout=5)
        return self.peak


def _page_count(path):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        return len(doc)
    finally:
        doc.close()


def run_job(conv, job, opts, sample_rss=True):
    """Convert one file (optionally a page range) and write its JSON. -> metrics dict."""
    import psutil

    src = job["pdf"]
    page_range = tuple(job["pages"]) if job.get("pages") else (1, sys.maxsize)
    lo, hi = page_range

    proc = psutil.Process()
    cpu0 = proc.cpu_times()
    sampler = _RssSampler() if sample_rss else None
    if sampler is not None:
        sampler.start()
    status, err, doc, conf, conv_status = "ok", None, None, None, None
    total_pages, pages_asked = 0, 0
    t0 = time.time()
    try:
        # The page count comes from the PDF, never from the converted document, and it is
        # INSIDE the try: pypdfium2 is the first thing to refuse a corrupt or zero-byte
        # file, and a file that dies here must still leave a failed metrics ROW rather than
        # killing the batch. Measured 2026-09-15: a 2 KB random body behind a %PDF-1.4
        # header, a zero-byte file and a plain-text file all fail at this call.
        total_pages = _page_count(src)
        pages_asked = max(0, min(hi, total_pages) - lo + 1)
        res = conv.convert(src, page_range=page_range)
        doc = res.document.export_to_dict()
        # Docling reports a confidence GRADE per page and per document on the RESULT, not on
        # any item, and a conversion status that can be PARTIAL_SUCCESS or FAILURE without
        # raising. Both are recorded: a caller that only watched for an exception would
        # score a failed conversion as an ok run.
        conv_status = str(getattr(res, "status", "") or "")
        c = getattr(res, "confidence", None)
        if c is not None:
            try:
                conf = c.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                conf = str(c)
    except Exception as e:  # noqa: BLE001 - the failure IS the measurement
        status, err = "failed", f"{type(e).__name__}: {e}"
    seconds = time.time() - t0
    peak = sampler.stop() if sampler is not None else None
    cpu1 = proc.cpu_times()
    cpu_s = (cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)

    if doc is not None and job.get("out"):
        tmp = job["out"] + ".partial"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, job["out"])

    return {
        "tool": f"{EXTRACTOR_BASE}-{_docling_version()}",
        "stage": "3-layout",
        "status": status,
        "error": err,
        "convert_status": conv_status,
        "confidence": conf,
        "file": os.path.basename(src),
        "pdf": src,
        "pages_in_file": total_pages,
        "page_range": [lo, min(hi, total_pages)],
        "pages": pages_asked,
        "seconds": round(seconds, 3),
        "pages_per_s": round(pages_asked / seconds, 4) if seconds > 0 else None,
        "peak_rss_bytes": peak,
        "peak_rss_scope": "this worker process, sampled at 5 Hz over THIS job",
        "lifetime_peak_wset_bytes": getattr(proc.memory_info(), "peak_wset", None),
        "cpu_seconds": round(cpu_s, 2),
        "cpu_cores_busy": round(cpu_s / seconds, 2) if seconds > 0 else None,
        "rss_samples": sampler.samples if sampler is not None else 0,
        "ocr": bool(opts.do_ocr),
        "ocr_engine": getattr(opts.ocr_options, "kind", None) if opts.do_ocr else None,
        "ocr_backend": getattr(opts.ocr_options, "backend", None) if opts.do_ocr else None,
        "tables": bool(opts.do_table_structure),
        "formula": bool(opts.do_formula_enrichment),
        "num_threads": opts.accelerator_options.num_threads,
        "device": str(opts.accelerator_options.device),
        # The VRAM knob, recorded on every row because the peak it produced is meaningless
        # without it: 3,881 MiB at page_batch_size 4 and a smaller number at 2 are the same
        # pipeline, and a reader comparing two runs has no other way to tell them apart.
        "page_batch_size": _page_batch_size(),
        "out": job.get("out"),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t0)),
        "host": "local-windows",
    }


def _docling_version():
    try:
        from importlib.metadata import version
        return version("docling")
    except Exception:  # noqa: BLE001
        return "unknown"


def _page_batch_size():
    try:
        from docling.datamodel.settings import settings
        return int(settings.perf.page_batch_size)
    except Exception:  # noqa: BLE001 — a metrics field must never kill the run
        return None


def _free_cuda_cache():
    """Return torch's cached-but-unused CUDA blocks to the driver. -> (reserved_before, after).

    torch's caching allocator never gives a block back on its own, so in a batch process the
    reserved pool is a HIGH-WATER MARK of every document the process has converted — which is
    what `nvidia-smi` reports, and what the 20 % headroom rule is written against. Between
    documents nothing in the pool is live, so this is free to call and changes no result."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None, None
        before = torch.cuda.memory_reserved()
        torch.cuda.empty_cache()
        return before, torch.cuda.memory_reserved()
    except Exception:  # noqa: BLE001 — freeing a cache must never kill the run
        return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Docling stage-3 batch worker (extraction venv)")
    ap.add_argument("--jobs", required=True,
                    help="JSON file: [{pdf, out, pages:[lo,hi]}, ...]")
    ap.add_argument("--metrics", required=True, help="JSONL file to append one row per job")
    ap.add_argument("--warmup", default=None,
                    help="PDF converted once before timing starts; its row is NOT recorded")
    ap.add_argument("--warmup-pages", type=int, default=1)
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--ocr-engine", default=None)
    ap.add_argument("--ocr-backend", default=None,
                    help="rapidocr: onnxruntime (absent here) or torch (what auto picks)")
    ap.add_argument("--no-tables", action="store_true")
    ap.add_argument("--formula", action="store_true")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--page-batch", type=int, default=0,
                    help="cap docling's settings.perf.page_batch_size (0 = leave its default of "
                         "4). This is the VRAM knob; see docling.OCR_PAGE_BATCH")
    ap.add_argument("--free-cache", action="store_true",
                    help="return torch's cached CUDA blocks to the driver after each document; "
                         "this is the VRAM knob that moved the peak (see docling.OCR_FREE_CACHE)")
    ap.add_argument("--no-rss", action="store_true")
    a = ap.parse_args(argv)

    with open(a.jobs, encoding="utf-8") as fh:
        jobs = json.load(fh)

    t_load = time.time()
    conv, opts = build_converter(ocr=a.ocr, ocr_engine=a.ocr_engine, tables=not a.no_tables,
                                 formula=a.formula, num_threads=a.threads, device=a.device,
                                 ocr_backend=a.ocr_backend, page_batch=a.page_batch or None)
    build_s = time.time() - t_load

    cold = None
    if a.warmup:
        t0 = time.time()
        conv.convert(a.warmup, page_range=(1, a.warmup_pages))
        cold = round(time.time() - t0, 3)

    with open(a.metrics, "a", encoding="utf-8", newline="\n") as mh:
        for job in jobs:
            m = run_job(conv, job, opts, sample_rss=not a.no_rss)
            m["converter_build_seconds"] = round(build_s, 3)
            m["warmup_seconds"] = cold
            # BEGIN guard: the cached CUDA pool is returned between documents
            if a.free_cache:
                m["cuda_reserved_before_free"], m["cuda_reserved_after_free"] = _free_cuda_cache()
            # END guard: the cached CUDA pool is returned between documents
            mh.write(json.dumps(m, sort_keys=True) + "\n")
            mh.flush()
            print(json.dumps({k: m[k] for k in
                              ("file", "status", "pages", "seconds", "pages_per_s",
                               "peak_rss_bytes", "cpu_cores_busy")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

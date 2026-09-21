"""S4 Q2 — what OCR costs on the T2000, so the readiness policy is set from runs and not from hope.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_ocr_vram.py \
        --out ../Reports/LITKB_OCR_VRAM_2026-09-21.csv

WHAT IT ANSWERS, and why each is a number :mod:`litkb.extract.readiness` cannot do without:

* **Peak VRAM over baseline for an OCR conversion**, per page-range chunk size. `readiness`
  decides `('run','cuda')` only when the free VRAM covers that peak plus the headroom rule's
  margin; a policy written against a guess would either refuse a card that fits or hand docling a
  card that does not, and the second failure is an OOM in the middle of a queue.
* **Pages per second on cuda and on cpu**, because the fallback `('run','cpu')` is only honest
  under a page bound, and a page bound is a rate times a budget.

WHAT IS MEASURED, AND WHAT IS NOT. This runs the two real scans in the corpus — `Hwang_1982`
(11 pp, the file S4's readable-scan proof is about) and `Anderson_1957` (22 pp, the file the
existing OCR record was measured on). Both are image-only bodies, which is the input the policy is
for. It does NOT measure a native document with OCR forced on, a book, or a second GPU: the T2000
is the card litkb has (`Reports/LITKB_DOCLING_LOCAL_2026-09-15.md` §8.3), and 4,096 MiB shared with
the display is what makes the margin matter at all.

HOW THE SAMPLING WORKS. `nvidia-smi --query-gpu=memory.used,memory.total` twice a second on a
thread, from before the worker starts to after it exits, so the peak covers the converter build as
well as the conversion. The number reported is `peak - baseline`, baseline being the median of the
samples taken before the subprocess was launched: the card also drives this desktop, so the
absolute peak is a fact about the machine that day and the RISE is the fact about docling.

WHOLE-PROCESS, NOT WHOLE-CALL. One `docling.run()` per row: one worker process taking the whole
chunk list for one file. That is the shape a queue job has, and it is the shape the VRAM answer
belongs to — `pipeline/litkb/extract/docling.py`'s own measurement block found the peak is driven
by the resident models plus torch's cached pool across a PROCESS, not by anything inside one
conversion.

RUN IT WITH `PYTHONPATH=pipeline`, as the line at the top says. This file does NOT insert the
package root on `sys.path`: litkb is not in the editable install, and every such insert in this
repository has to be argued for a row in `qc/test_status_discovery._PATH_INSERT_LEDGER`. An
instrument the caller runs by hand can be told where the package is instead.

Writes: the CSV named by --out, and docling artifacts under --derived (default
`D:\\edmonds-pipeline\\litkb_derived\\s4q2`, outside the live `litkb_derived` roots any other run
uses). Touches no database.
"""
import argparse
import csv
import json
import os
import pathlib
import statistics
import subprocess
import sys
import threading
import time

SCRIPTS = pathlib.Path(__file__).resolve().parents[2]

LIT = pathlib.Path(os.environ.get("LITKB_LITERATURE_ROOT") or r"D:\edmonds-pipeline\Literture")
HWANG = LIT / "Validation" / "Hwang_1982_improving-upon-standard-estimators.pdf"
ANDERSON = LIT / "Validation" / "Anderson_1957_statistical-inference-about-markov.pdf"

#: The CUDA docling venv, as `qc/instruments/litkb_p5_bulk.py` names it in `CUDA_PY`; the CPU one
#: is the adapter's own default (`litkb.extract.docling.VENV_PYTHON`).
CUDA_PY = os.environ.get("LITKB_EXTRACT_PYTHON_CUDA",
                         r"D:\edmonds-pipeline\venv-docling-cuda\Scripts\python.exe")

DERIVED_DEFAULT = r"D:\edmonds-pipeline\litkb_derived\s4q2"

FIELDS = ("run", "file", "pages_total", "device", "chunk", "n_chunks", "status",
          "baseline_mib", "peak_mib", "peak_over_baseline_mib", "total_mib", "peak_pct",
          "samples", "convert_seconds", "wall_seconds", "pages_done", "pages_per_s",
          "converter_build_s", "page_batch_size", "artifacts")


def gpu_sample():
    """-> (used_mib, total_mib) or None when nvidia-smi is absent or answers unusably."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    line = (r.stdout or "").strip().splitlines()
    if not line:
        return None
    try:
        used, total = (int(x.strip()) for x in line[0].split(",")[:2])
    except (ValueError, IndexError):
        return None
    return used, total


class Sampler(threading.Thread):
    """`nvidia-smi` at 2 Hz for the length of one row. Never raises into the run."""

    def __init__(self, interval=0.5):
        super().__init__(daemon=True)
        self.interval = interval
        # NOT `_stop`: threading.Thread has a private method of that name and shadowing it makes
        # join() raise "'Event' object is not callable" at the end of the row, after the GPU time
        # has already been spent. `_RssSampler` in docling_worker.py calls its flag `_stopping`
        # for the same reason.
        self._stopping = threading.Event()
        self.used = []
        self.total = None

    def run(self):
        while not self._stopping.is_set():
            s = gpu_sample()
            if s:
                self.used.append(s[0])
                self.total = s[1]
            self._stopping.wait(self.interval)

    def stop(self):
        self._stopping.set()
        self.join(timeout=10)
        return self.used


def chunks(n_pages, size):
    """Page ranges [lo, hi], 1-indexed and inclusive — the `pages` field docling_worker reads."""
    if not size or size >= n_pages:
        return [[1, n_pages]]
    return [[lo, min(lo + size - 1, n_pages)] for lo in range(1, n_pages + 1, size)]


def one_row(pdf, n_pages, size, device, derived, timeout, tag):
    """One docling worker process over `pdf`'s chunks, sampled. -> (row, metrics rows)."""
    from litkb.extract import docling as D

    out_dir = pathlib.Path(derived) / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    ranges = chunks(n_pages, size)
    jobs = [{"pdf": str(pdf), "out": str(out_dir / f"p{lo}-{hi}.docling.json"), "pages": [lo, hi]}
            for lo, hi in ranges]
    metrics = out_dir / "metrics.jsonl"
    python = CUDA_PY if device == "cuda" else None

    sampler = Sampler()
    sampler.start()
    time.sleep(2.0)                      # baseline: the card as it is before docling starts
    base = list(sampler.used)
    t0 = time.monotonic()
    status, rows = "ok", []
    try:
        rows = D.run(jobs, str(metrics), python=python, device=device, ocr=True,
                     tables_on=True, timeout=timeout)
    except Exception as exc:             # noqa: BLE001 - an OOM IS the measurement
        status = f"{type(exc).__name__}: {exc}"[:300]
    wall = time.monotonic() - t0
    used = sampler.stop()

    baseline = int(statistics.median(base)) if base else None
    peak = max(used) if used else None
    done = sum(int(r.get("pages") or 0) for r in rows if r.get("status") == "ok")
    secs = sum(float(r.get("seconds") or 0.0) for r in rows if r.get("status") == "ok")
    bad = [r for r in rows if r.get("status") != "ok"]
    if bad and status == "ok":
        status = "worker-failed: " + str(bad[0].get("error"))[:200]
    # A SHORT BATCH IS A FAILURE AND `docling.run` DOES NOT SAY SO. It raises only when the worker
    # exits non-zero AND no metrics row came back, so a process that dies after job 1 of 3 returns
    # one ok row and the caller scores a 22-page file as 8 pages converted "ok" (seen here on
    # 2026-09-21, anderson chunk 8: one row, one artifact, no error anywhere). The count is the
    # only thing that catches it, so it is checked here and carried into the CSV.
    if status == "ok" and len(rows) != len(jobs):
        status = f"short-batch: {len(rows)} metrics rows for {len(jobs)} jobs"
    row = {
        "run": tag, "file": pdf.name, "pages_total": n_pages, "device": device,
        "chunk": size or n_pages, "n_chunks": len(ranges), "status": status,
        "baseline_mib": baseline, "peak_mib": peak,
        "peak_over_baseline_mib": (peak - baseline) if (peak is not None and baseline is not None)
                                  else None,
        "total_mib": sampler.total,
        "peak_pct": round(100.0 * peak / sampler.total, 1) if (peak and sampler.total) else None,
        "samples": len(used),
        "convert_seconds": round(secs, 2), "wall_seconds": round(wall, 2),
        "pages_done": done,
        "pages_per_s": round(done / secs, 4) if secs > 0 else None,
        "converter_build_s": rows[0].get("converter_build_seconds") if rows else None,
        "page_batch_size": rows[0].get("page_batch_size") if rows else None,
        "artifacts": str(out_dir),
    }
    return row, rows


def text_regions_per_page(out_dir):
    """-> {page_no: n text-bearing regions} over every docling JSON a run wrote.

    The readable-scan proof: a scan whose OCR produced regions on its pages is readable, and the
    per-page count is what says so. Reads the artifacts, never a database.
    """
    from litkb.extract import docling as D

    per = {}
    for p in sorted(pathlib.Path(out_dir).glob("*.docling.json")):
        doc = D.load(str(p))
        for b in D.blocks(doc):
            if (b.text or "").strip():
                per[b.page] = per.get(b.page, 0) + 1
    return dict(sorted(per.items()))


def main(argv=None):
    ap = argparse.ArgumentParser(description="OCR VRAM and throughput on the T2000 (S4 Q2)")
    ap.add_argument("--out", default=str(SCRIPTS.parent / "Reports"
                                         / "LITKB_OCR_VRAM_2026-09-21.csv"))
    ap.add_argument("--derived", default=DERIVED_DEFAULT)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--chunks", default="4,8,0", help="page-range chunk sizes; 0 = the whole file")
    ap.add_argument("--skip-cpu", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated run tags to run")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run the whole plan N times, tagging each pass -r1, -r2, …. The CPU rate "
                         "moved 0.0689 -> 0.0756 pages/s between two passes on 2026-09-21, and a "
                         "page bound built on the FASTER of two runs is a bound that times out: "
                         "the constant in litkb.extract.readiness takes the slowest row here.")
    ap.add_argument("--append", action="store_true",
                    help="add rows to an existing CSV instead of replacing it")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)

    missing = [str(p) for p in (HWANG, ANDERSON) if not p.exists()]
    if missing:
        raise SystemExit(f"the corpus scans are not on disk: {missing}")

    sizes = [int(s) for s in a.chunks.split(",") if s.strip()]
    plan = []
    for pdf, n in ((HWANG, 11), (ANDERSON, 22)):
        stem = pdf.name.split("_")[0].lower()
        for size in sizes:
            plan.append((f"{stem}-cuda-c{size or n}", pdf, n, size, "cuda"))
    if not a.skip_cpu:
        plan.append(("hwang-cpu-c4", HWANG, 11, 4, "cpu"))
    if a.only:
        want = {t.strip() for t in a.only.split(",") if t.strip()}
        plan = [p for p in plan if p[0] in want]
    if a.repeat > 1:
        plan = [(f"{tag}-r{i}", *rest) for i in range(1, a.repeat + 1) for tag, *rest in plan]

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if a.append and out.exists():
        with out.open(encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh)]
    for tag, pdf, n, size, device in plan:
        print(f"\n=== {tag}: {pdf.name} {n}pp chunk={size or n} device={device}", flush=True)
        row, _m = one_row(pdf, n, size, device, a.derived, a.timeout, tag)
        rows.append(row)
        print(json.dumps({k: row[k] for k in
                          ("status", "baseline_mib", "peak_mib", "peak_over_baseline_mib",
                           "peak_pct", "convert_seconds", "pages_done", "pages_per_s")}),
              flush=True)
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)

    print(f"\nwrote {out} ({len(rows)} rows)")
    for tag, _pdf, _n, _size, _dev in plan:
        d = pathlib.Path(a.derived) / tag
        if d.exists():
            per = text_regions_per_page(d)
            print(f"{tag}: text regions per page {per} "
                  f"(pages with >0: {sum(1 for v in per.values() if v)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

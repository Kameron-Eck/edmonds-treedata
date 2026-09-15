"""Measure Docling stage 3 on the gate papers — the §14 throughput instrument.

One process per configuration, warmed once on a page before anything is timed, then one
timed job per paper. Every number the report quotes comes from here; nothing is typed by
hand (CLAUDE.md §3.4b).

    py -3.12 qc/instruments/litkb_docling_bench.py --threads 4 --tag cpu-t4
    py -3.12 qc/instruments/litkb_docling_bench.py --threads 8 --tag cpu-t8
    py -3.12 qc/instruments/litkb_docling_bench.py --ocr --only Anderson_1957 --tag ocr
    py -3.12 qc/instruments/litkb_docling_bench.py --formula --only Bellettini --pages 1 10

WHAT IT REFUSES (design §14): a row with no rate or no peak RSS is not a measurement. The
instrument fails loudly on one rather than writing it, because a throughput table with an
empty cell in it gets quoted anyway.

MACHINE LOAD IS PART OF THE MEASUREMENT. Before and after the batch it records the
system-wide CPU percent and the memory in use, so a rate measured while the machine was
busy can be told apart from one measured on a quiet machine. It does not close anything of
Kam's: the load is reported, not removed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.extract import docling as D  # noqa: E402

LIT = r"D:\edmonds-pipeline\Literture\Validation"

#: The five gate papers — the same set the GROBID referee measured (LITKB_GROBID_LOCAL_
#: REFEREE_2026-09-14.md §2), so the two stages' numbers are comparable.
PAPERS = [
    ("Benedek_2015", "Benedek_2015_multilayer-markov-random-field-models.pdf", None),
    ("Alwan_1988", "Alwan_1988_time-series-modeling-statistical-process.pdf", None),
    ("Anderson_1957", "Anderson_1957_statistical-inference-about-markov.pdf", None),
    ("Bellettini_2002", "Bellettini_2002_total-variation-flow.pdf", None),
    ("Schneider_2008", "Schneider_2008_stochastic-integral-geometry.pdf", [1, 100]),
]

OUT_DIR = os.environ.get("LITKB_DOCLING_OUT", r"D:\edmonds-pipeline\_tmp\litkb_docling")
#: Reports/ sits at the REPO root, one level above Scripts/ (qc/instruments -> qc ->
#: Scripts -> repo).
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
CSV_PATH = os.path.join(_REPO, "Reports", "litkb_docling_throughput_2026-09-15.csv")

FIELDS = ["tag", "file", "pages", "seconds", "pages_per_s", "peak_rss_mb", "cpu_seconds",
          "cpu_cores_busy", "num_threads", "device", "ocr", "ocr_engine", "formula",
          "tables", "body_blocks", "tables_found", "figures_found", "status", "tool",
          "warmup_seconds", "converter_build_seconds", "load_cpu_pct_before",
          "load_cpu_pct_after", "load_mem_used_gb_before", "load_mem_used_gb_after",
          "page_range", "started_at"]


def machine_load():
    """(cpu percent over 1 s, memory used GB) — the load the measurement ran against."""
    try:
        import psutil
        return round(psutil.cpu_percent(interval=1.0), 1), round(
            psutil.virtual_memory().used / 2**30, 2)
    except ImportError:
        import subprocess
        ps = ("$c=(Get-CimInstance Win32_Processor).LoadPercentage;"
              "$o=Get-CimInstance Win32_OperatingSystem;"
              "'{0} {1}' -f $c, [math]::Round(($o.TotalVisibleMemorySize-$o.FreePhysicalMemory)/1MB,2)")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=60)
        cpu, mem = (r.stdout or "0 0").split()[:2]
        return float(cpu), float(mem)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", required=True, help="name for this configuration in the CSV")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--ocr-engine", default=None)
    ap.add_argument("--formula", action="store_true")
    ap.add_argument("--only", default=None, help="substring: run just this paper")
    ap.add_argument("--pages", nargs=2, type=int, default=None, help="page range override")
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--timeout", type=int, default=14400)
    ap.add_argument("--replay", action="store_true",
                    help="write the CSV from this tag's existing metrics JSONL instead of "
                         "re-running docling (the measurement is the JSONL; this only "
                         "re-renders it)")
    a = ap.parse_args(argv)

    os.makedirs(OUT_DIR, exist_ok=True)
    jobs, names = [], []
    for name, fn, rng in PAPERS:
        if a.only and a.only.lower() not in name.lower():
            continue
        pages = a.pages if a.pages else rng
        jobs.append({"pdf": os.path.join(LIT, fn),
                     "out": os.path.join(OUT_DIR, f"{name}__{a.tag}.docling.json"),
                     "pages": pages})
        names.append(name)
    if not jobs:
        raise SystemExit("no papers selected")

    metrics_path = os.path.join(OUT_DIR, f"metrics_{a.tag}.jsonl")
    if a.replay:
        rows = D._read_metrics(metrics_path)
        names = [n for n, _, _ in PAPERS if any(
            n in (r.get("out") or "") for r in rows)] or names
        rows = [r for r in rows if any(n in (r.get("out") or "") for n in names)]
        names = [next(n for n in [p[0] for p in PAPERS] if n in (r.get("out") or ""))
                 for r in rows]
        cpu0 = cpu1 = mem0 = mem1 = None
        wall = sum(r["seconds"] for r in rows)
    else:
        cpu0, mem0 = machine_load()
        t0 = time.time()
        rows = D.run(jobs, metrics_path, warmup=jobs[0]["pdf"], warmup_pages=1,
                     ocr=a.ocr, ocr_engine=a.ocr_engine, formula=a.formula,
                     threads=a.threads, device=a.device, timeout=a.timeout)
        wall = time.time() - t0
        cpu1, mem1 = machine_load()

    out = []
    for name, m in zip(names, rows):
        if m["status"] == "ok" and (not m.get("pages_per_s") or not m.get("peak_rss_bytes")):
            raise SystemExit(f"REFUSED: {name} recorded no rate or no peak RSS — "
                             f"a run without both is not a measurement (design §14)")
        doc = D.load(m["out"]) if m["status"] == "ok" and os.path.exists(m["out"]) else None
        row = {
            "tag": a.tag, "file": name, "pages": m["pages"], "seconds": m["seconds"],
            "pages_per_s": m["pages_per_s"],
            "peak_rss_mb": round((m["peak_rss_bytes"] or 0) / 2**20, 1),
            "cpu_seconds": m["cpu_seconds"], "cpu_cores_busy": m["cpu_cores_busy"],
            "num_threads": m["num_threads"], "device": m["device"], "ocr": m["ocr"],
            "ocr_engine": m["ocr_engine"], "formula": m["formula"], "tables": m["tables"],
            "body_blocks": len(D.body_blocks(doc)) if doc else 0,
            "tables_found": len(D.tables(doc)) if doc else 0,
            "figures_found": len(D.figures(doc)) if doc else 0,
            "status": m["status"], "tool": m["tool"],
            "warmup_seconds": m["warmup_seconds"],
            "converter_build_seconds": m["converter_build_seconds"],
            "load_cpu_pct_before": cpu0, "load_cpu_pct_after": cpu1,
            "load_mem_used_gb_before": mem0, "load_mem_used_gb_after": mem1,
            "page_range": "-".join(str(x) for x in m["page_range"]),
            "started_at": m["started_at"],
        }
        out.append(row)
        print(json.dumps({k: row[k] for k in
                          ("file", "pages", "seconds", "pages_per_s", "peak_rss_mb",
                           "cpu_cores_busy", "body_blocks", "status")}))

    new = not os.path.exists(a.csv)
    with open(a.csv, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        if new:
            w.writeheader()
        for row in out:
            w.writerow(row)
    print(f"batch wall {wall:.1f}s -> {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

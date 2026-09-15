"""Measure GROBID stage-2 throughput and write the §14 metrics rows.

The instrument behind every pages/s number in design §12.7 and in
``Reports/LITKB_GROBID_LOCAL_*.md``. It exists because a rate quoted without the script that
produced it is a restatement, not a measurement (CLAUDE.md §3.4b) — the 688-page book's rate
has now been reported three different ways by three parties, and only a committed instrument
settles which run anyone is looking at.

From ``Scripts/``, with the service installed under WSL2::

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_grobid_throughput.py \
        --pdf "D:\\edmonds-pipeline\\Literture\\Validation\\Schneider_2008_stochastic-integral-geometry.pdf" \
        --runs 3 --warm-up "...\\Benedek_2015_multilayer-markov-random-field-models.pdf" \
        --out ..\\phase4\\qc\\litkb_extraction_metrics.jsonl

What it controls for, and why each one is here:

* **Warm, not cold.** The first request of a service's life loads the CRF models (~47 s) and
  is not a throughput measurement. ``--warm-up`` sends a small paper first and discards it.
  A cold run also returns slightly DIFFERENT TEI (measured 2026-09-15 on Benedek: cold
  274,185 B / 3,762 boxes, warm 274,093 B / 3,760), so cold numbers are not comparable.
* **Idle, and it says so.** The whole-system CPU line is printed from inside the distro
  before and after the runs, because "the machine was idle" is otherwise an assertion.
* **Spread, not a single number.** ``(max - min) / median``. Over ``--max-spread`` (default
  20%) the verdict is **UNDETERMINED** — not "slower", not "faster".
* **Every run is recorded**, through :func:`litkb.extract.grobid.extract`, so the rows carry
  the peak RSS the §14 gate refuses a run without. This is the dict P5's ingest persists into
  ``extraction_runs.metrics``; until the P4/P5 job tables exist it is parked as JSONL.

The service is left as it was found: started here only if it was down, and stopped again.
"""
from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys

from litkb.extract import grobid


def cpu_line():
    """The distro's own whole-system CPU and load, as one line."""
    try:
        r = subprocess.run(
            ["wsl.exe", "-d", grobid.WSL_DISTRO, "-u", "root", "--", "bash", "-c",
             "top -bn1 | grep '^%Cpu' ; uptime"],
            capture_output=True, text=True, timeout=120,
            env=dict(os.environ, MSYS_NO_PATHCONV="1"))
        return " | ".join(ln.strip() for ln in r.stdout.splitlines() if ln.strip())
    except Exception as e:                                  # never fail a run over a probe
        return f"(cpu probe failed: {e!r})"


def measure(pdf, runs=3, warm_up=None, out=None, concurrency=None, max_spread=0.20,
            note=""):
    started_here = not grobid.health()
    if started_here and not grobid.start(wait=300):
        raise SystemExit("GROBID did not come up")
    grobid.hold_distro()
    try:
        print(f"CPU before: {cpu_line()}")
        if warm_up:
            grobid.process_pdf(warm_up)                     # discarded: model load, not a rate
            print(f"warm-up: {os.path.basename(warm_up)}")
        rates, rows = [], []
        for i in range(runs):
            _tei, m = grobid.extract(pdf, concurrency=concurrency)
            m["note"] = note or f"run {i + 1}/{runs}, warm service"
            if out:
                grobid.append_metrics(m, out)
            rows.append(m)
            rates.append(m["pages_per_s"])
            print(f"run {i + 1}/{runs}: {m['pages']} pages, {m['seconds']} s, "
                  f"{m['pages_per_s']} pages/s, peak {m['peak_rss_bytes'] / 2 ** 20:.0f} MiB")
        print(f"CPU after:  {cpu_line()}")
    finally:
        if started_here:
            grobid.stop()
        grobid.release_distro()

    med = statistics.median(rates)
    spread = (max(rates) - min(rates)) / med if med else float("inf")
    verdict = "UNDETERMINED" if spread > max_spread else "determined"
    print(f"median {med:.2f} pages/s   spread {spread * 100:.1f}%   "
          f"{verdict} (threshold {max_spread * 100:.0f}%)")
    return {"median_pages_per_s": med, "spread": spread, "verdict": verdict, "runs": rows}


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--warm-up", default=None,
                    help="a small PDF sent first and discarded (the CRF model load)")
    ap.add_argument("--out", default=None, help="JSONL to append each run's metrics to")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="recorded in the row; the service's own pool is set by grobid.sh")
    ap.add_argument("--max-spread", type=float, default=0.20)
    ap.add_argument("--note", default="")
    a = ap.parse_args(clean_argv(argv))
    r = measure(a.pdf, runs=a.runs, warm_up=a.warm_up, out=a.out,
                concurrency=a.concurrency, max_spread=a.max_spread, note=a.note)
    return 0 if r["verdict"] == "determined" else 1


if __name__ == "__main__":
    sys.exit(main())

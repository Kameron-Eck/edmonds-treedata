"""litkb acquisition probe 6 (read-only): THE SCI-HUB CORPUS THROUGH sci.bban.top, over litkb's own pre-freeze
no-file backlog. Population (derived here, not copied): every work in litkb.main_works with an active `doi` identifier,
no row in litkb.main_files (one file row per work; the table has no active flag), and year < 2022 (the corpus froze
2022-02-12). One HEAD per DOI at
`https://sci.bban.top/pdf/<doi>.pdf` as litkb stores it (lower-cased); on a 404 one retry with the DOI's suffix
upper-cased (the host is case-sensitive: survey D2, 2026-09-22). A hit is 200/206 + `application/pdf`; a miss is
404 + `text/html`. On the first SAMPLE hits (default 8) one Range GET of 1024 bytes confirms the `%PDF` magic — no
PDF is ever stored. Serialised, 2.5 s apart. Contact with sci.bban.top is inside Kam's grant (`litkb-shadow-hosts` (b)).

Writes phase4/qc/litkb_acq_probe_bban.csv (one row per DOI) and prints the conversion. This is the orchestrator's
independent re-run of survey D2's headline (73/104 on 2026-09-22) — CLAUDE.md §3.4c: the proposer never scores its
own proposal. Usage: py litkb_acq_probe_bban.py [--sample N] [--sleep S]
"""
import argparse
import csv
import datetime as dt
import pathlib
import sys
import time
import urllib.error
import urllib.request

import psycopg

OUT = pathlib.Path(__file__).resolve().parents[3] / "phase4" / "qc" / "litkb_acq_probe_bban.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) litkb-probe/0.1"
COLS = ["ts_utc", "key", "doi", "year", "tried", "http_status", "content_type", "content_length", "verdict", "pdf_magic"]


def head(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.headers.get("Content-Type") or "", r.headers.get("Content-Length") or ""
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type") or "", e.headers.get("Content-Length") or ""
    except Exception as exc:  # noqa: BLE001 - a probe records the failure, never raises
        return -1, f"exception: {type(exc).__name__}", ""


def magic(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-1023"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read(1024)[:4] == b"%PDF"
    except Exception:  # noqa: BLE001
        return False


def suffix_upper(doi):
    prefix, _, suffix = doi.partition("/")
    return f"{prefix}/{suffix.upper()}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=8, help="hits to Range-confirm with the %PDF magic")
    ap.add_argument("--sleep", type=float, default=2.5)
    a = ap.parse_args()
    c = psycopg.connect("host=localhost port=5433 dbname=litkb user=litkb_reader")
    rows = c.execute("""
        SELECT w.key, i.value, w.year FROM litkb.main_works w
        JOIN litkb.main_identifiers i ON i.work_id = w.work_id AND i.scheme = 'doi' AND i.active
        WHERE w.year < 2022
          AND NOT EXISTS (SELECT 1 FROM litkb.main_files f WHERE f.work_id = w.work_id)
        ORDER BY i.value""").fetchall()
    print(f"population: {len(rows)} pre-2022 no-file DOI works", file=sys.stderr)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    hits = upper_hits = confirmed = 0
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for n, (key, doi, year) in enumerate(rows, 1):
            tried = doi
            status, ctype, clen = head(f"https://sci.bban.top/pdf/{doi}.pdf")
            time.sleep(a.sleep)
            if status == 404 and suffix_upper(doi) != doi:
                tried = suffix_upper(doi)
                status, ctype, clen = head(f"https://sci.bban.top/pdf/{tried}.pdf")
                time.sleep(a.sleep)
            hit = status in (200, 206) and "pdf" in ctype.lower()
            verdict = "served" if hit else ("not-in-corpus" if status == 404 else f"status-{status}")
            pdf_magic = ""
            if hit:
                hits += 1
                upper_hits += tried != doi
                if confirmed < a.sample:
                    pdf_magic = magic(f"https://sci.bban.top/pdf/{tried}.pdf")
                    confirmed += bool(pdf_magic)
                    time.sleep(a.sleep)
            w.writerow(dict(ts_utc=ts, key=key, doi=doi, year=year, tried=tried, http_status=status, content_type=ctype[:40],
                            content_length=clen, verdict=verdict, pdf_magic=pdf_magic))
            f.flush()
            if n % 20 == 0:
                print(f"{n}/{len(rows)} served={hits}", file=sys.stderr)
    share = hits / len(rows) if rows else 0
    print(f"population={len(rows)} served={hits} ({share:.1%}) needed_upper_suffix={upper_hits} "
          f"magic_confirmed={confirmed}/{min(a.sample, hits)} -> {OUT}")


if __name__ == "__main__":
    main()

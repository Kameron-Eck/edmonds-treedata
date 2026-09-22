"""litkb acquisition probe 2 (read-only): HEAD every PDF URL probe 1 found advertised (headers only, never the body)
and record status, content type, length and final URL. A 200 with application/pdf and no login redirect is a free
copy; text/html is a paywall or landing page. Writes phase4/qc/litkb_acq_probe_head.csv and prints the DOIs that
have a genuinely free PDF today — the MEASURED free-ceiling rows S4.5 is scored on.
First run 2026-09-22 from the jobs folder; moved into the repository unchanged except for its paths.
"""
import csv
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

QC = Path(__file__).resolve().parents[3] / "phase4" / "qc"
SRC = QC / "litkb_acq_probe_no_oa_copy.csv"
OUT = QC / "litkb_acq_probe_head.csv"
UA = "Mozilla/5.0 (compatible; litkb-probe/0.1; mailto:chillozone1@gmail.com)"


def head(url):
    for method in ("HEAD", "GET"):
        headers = {"User-Agent": UA, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8"}
        if method == "GET":
            headers["Range"] = "bytes=0-0"
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return method, r.status, r.headers.get("content-type", ""), r.headers.get("content-length", r.headers.get("content-range", "")), r.geturl()
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (405, 403, 404, 400):
                continue
            return method, e.code, e.headers.get("content-type", "") if e.headers else "", "", url
        except Exception as e:  # noqa: BLE001 - a probe records the failure, never raises
            return method, -1, repr(e)[:50], "", url
    return "GET", -2, "", "", url


def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    free = set()
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doi", "resolver", "url", "method", "status", "content_type", "length", "final_url", "verdict"])
        for r in rows:
            for resolver, url in (("openalex", r["openalex_pdf"]), ("crossref_link", r["crossref_pdf_link"]),
                                  ("s2", r["s2_pdf"]), ("citation_pdf_url", r["citation_pdf_url"])):
                if not url:
                    continue
                m, s, ct, ln, fin = head(url)
                is_pdf = s in (200, 206) and "pdf" in ct.lower()
                # A publisher PREVIEW is a valid PDF that is not the work: Taylor & Francis serves
                # `.../relatedobjects/preview.pdf` for a closed book's citation_pdf_url (measured 2026-09-22 on
                # 10.1201/9781315374321). The URL shape is the survey's C19 signal; the acceptance test's
                # stub detector is the gate that catches it after download.
                preview = any(tok in (fin + url).lower() for tok in ("preview", "sample", "previewpdf"))
                verdict = ("PREVIEW-PDF" if (is_pdf and preview) else "FREE-PDF" if is_pdf
                           else "HTML" if "html" in ct.lower() else f"status-{s}")
                if verdict == "FREE-PDF":
                    free.add(r["doi"])
                w.writerow([r["doi"], resolver, url, m, s, ct, ln, fin, verdict])
                f.flush()
                print(f"{r['doi']:38s} {resolver:16s} {s:>4} {ct[:28]:28s} {verdict:10s} {fin[:70]}", file=sys.stderr)
                time.sleep(1.0)
    print(f"dois_with_free_pdf={len(free)} of {len(rows)}: {sorted(free)} -> {OUT}")


if __name__ == "__main__":
    main()

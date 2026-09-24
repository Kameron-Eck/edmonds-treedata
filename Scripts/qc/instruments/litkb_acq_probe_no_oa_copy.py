"""litkb acquisition probe 1 (read-only): for every DOI the ledger marks open_access/no-oa-copy, does a second
resolver advertise a PDF? Asks OpenAlex (pdf_url), Crossref (link[] pdf), Semantic Scholar (openAccessPdf) and the
DOI's landing page (citation_pdf_url). Metadata and landing-page HTML only — never fetches a PDF.

Writes phase4/qc/litkb_acq_probe_no_oa_copy.csv (the measured home; CLAUDE.md 3.4b). The head probe
(litkb_acq_probe_head.py) then HEADs every advertised URL to separate a free copy from a paywall page.
First run 2026-09-22 from the jobs folder (D:\\tools\\claude-config\\jobs\\litkb-acquisition-survey\\probe_no_oa_copy.py);
this is that script moved into the repository unchanged except for its output path.
"""
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "litkb_acq_probe_no_oa_copy.csv"
UA = "litkb-probe/0.1 (mailto:chillozone1@gmail.com)"


def get(url, accept=None, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Accept": accept} if accept else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("content-type", ""), r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", b"", url
    except Exception as e:  # noqa: BLE001 - a probe records the failure, never raises
        return -1, repr(e)[:60], b"", url


def openalex(doi):
    s, _ct, b, _ = get(f"https://api.openalex.org/works/doi:{doi}?mailto=chillozone1@gmail.com")
    if s != 200:
        return s, "", "", 0
    d = json.loads(b)
    oa = d.get("open_access", {}) or {}
    best = d.get("best_oa_location") or {}
    pdfs = [loc.get("pdf_url") for loc in d.get("locations", []) if loc.get("pdf_url")]
    return s, str(oa.get("is_oa")), best.get("pdf_url") or (pdfs[0] if pdfs else ""), len(pdfs)


def crossref_links(doi):
    s, _ct, b, _ = get(f"https://api.crossref.org/works/{doi}")
    if s != 200:
        return s, "", ""
    m = json.loads(b)["message"]
    links = [ln for ln in m.get("link", []) if "pdf" in (ln.get("content-type") or "") or ln.get("URL", "").endswith(".pdf")]
    lic = [x.get("URL") for x in m.get("license", [])]
    return s, links[0]["URL"] if links else "", ";".join(lic[:2])


def s2(doi):
    s, _ct, b, _ = get(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf,isOpenAccess")
    if s != 200:
        return s, ""
    d = json.loads(b)
    return s, ((d.get("openAccessPdf") or {}).get("url") or "")


def landing(doi):
    s, _ct, b, final = get(f"https://doi.org/{doi}", accept="text/html")
    if s != 200:
        return s, "", final, ""
    html = b.decode("utf-8", "replace")
    m = re.search(r'citation_pdf_url"\s+content="([^"]+)"', html) or re.search(r'content="([^"]+)"\s+name="citation_pdf_url"', html)
    alt = re.search(r'<link[^>]+type="application/pdf"[^>]+href="([^"]+)"', html)
    note = "challenge" if re.search(r"cf-browser-verification|Just a moment|captcha", html, re.I) else ""
    return s, (m.group(1) if m else (alt.group(1) if alt else "")), final, note


def unpaywall(doi):
    """litkb's OWN resolver (pipeline/litkb/acquire/open_access.py), in-process, so the column says what the
    open_access route would see today — a landing-page URL for a bronze article, nothing for a paywalled one."""
    try:
        from litkb.acquire.open_access import unpaywall_locations
    except ImportError:
        return "", "litkb not importable (run from Scripts/ with PYTHONPATH=pipeline, or install -e .)"
    urls, note, *_meta = unpaywall_locations(doi)      # (urls, note, meta) since S4.5 C1a (D3)
    return (urls[0] if urls else ""), note


def main():
    c = psycopg.connect("host=localhost port=5433 dbname=litkb user=litkb_reader")
    rows = c.execute("""SELECT DISTINCT identifier_used FROM litkb.acquisition_attempts
                        WHERE route='open_access' AND status='no-oa-copy' AND identifier_used LIKE '10.%' ORDER BY 1""").fetchall()
    dois = [r[0] for r in rows]
    print(len(dois), "distinct no-oa-copy DOIs", file=sys.stderr)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doi", "openalex_status", "openalex_is_oa", "openalex_pdf", "openalex_n_pdf", "crossref_status",
                    "crossref_pdf_link", "crossref_license", "s2_status", "s2_pdf", "landing_status", "citation_pdf_url",
                    "landing_final_url", "landing_note", "unpaywall_url", "unpaywall_note"])
        for i, doi in enumerate(dois, 1):
            oa = openalex(doi)
            cr = crossref_links(doi)
            ss = s2(doi)
            la = landing(doi)
            up = unpaywall(doi)
            w.writerow([doi, *oa, *cr, *ss, *la, *up])
            f.flush()
            print(f"{i:2d} {doi:40s} oa={oa[2][:40]!r} cr={cr[1][:30]!r} s2={ss[1][:30]!r} page={la[1][:40]!r} {la[3]}", file=sys.stderr)
            time.sleep(1.5)
    adv = sum(1 for r in csv.DictReader(OUT.open(encoding="utf-8"))
              if r["openalex_pdf"] or r["crossref_pdf_link"] or r["s2_pdf"] or r["citation_pdf_url"])
    print(f"probed={len(dois)} any_pdf_advertised={adv} -> {OUT}")


if __name__ == "__main__":
    main()

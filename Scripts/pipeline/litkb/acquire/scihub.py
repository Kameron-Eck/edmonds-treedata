"""Sci-Hub route, by DOI only, one bare HTTP GET per request (design §10; the convention's route order puts it
after open access and Anna's Archive; memory `scihub-fetch-method`, Kam 2026-09-12).

First index `sci-hub.ru`, then `sci-hub.ren`: GET <mirror>/<doi>, read the landing page's citation_pdf_url
(or the embedded PDF src), GET that URL. The response must start with %PDF-; binding follows in
litkb.acquire.run like every other route. A bot challenge, a captcha page or a 403 is recorded as `blocked`
and the route moves on: no header, cookie or solver is added to get past a protection. The browser route is
not automated here; litkb.acquire.run records it as a manual step.

-> dict(status, pdf, source_url, tried, detail, http_codes). status: downloaded | not-in-archive (every
landing page answered without a PDF link) | blocked | bad-file | api-error.

Bytes that are not a PDF are handed back in `rejected` (with `rejected_url`, redacted) instead of being dropped,
and litkb.acquire.run quarantines them with a reason beside them
(Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9). Only the answer to a GET of the PDF LINK is handed back: a
landing page is a page this route read, never a file it was offered.
"""
import re
import urllib.parse

from litkb.netutil import Client, redact

MIRRORS = ("https://sci-hub.ru", "https://sci-hub.ren")
_PDF_URL_RES = (re.compile(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']', re.I),
                re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']', re.I),
                re.compile(r'<(?:embed|iframe)[^>]+src=["\']([^"\']+?\.pdf[^"\']*)["\']', re.I))
_CAPTCHA = re.compile(rb"<title>\s*Verification|captcha", re.I)


def pdf_link(html, base):
    for rx in _PDF_URL_RES:
        m = rx.search(html)
        if m:
            u = m.group(1).strip()
            if u.startswith("//"):
                u = "https:" + u
            return urllib.parse.urljoin(base + "/", u)
    return ""


def fetch_scihub(doi, pacer, *, client=None, mirrors=MIRRORS):
    client = client or Client()
    tried, codes = [], []
    rejected, rejected_url = None, ""
    blocked = misses = bad = 0
    for base in mirrors:
        url = f"{base}/{urllib.parse.quote(doi, safe='/:()')}"
        if pacer is not None:
            pacer.wait()
        st, _hd, body = client.get(url, accept="text/html", timeout=60)
        codes.append(int(st or 0))
        host = urllib.parse.urlparse(base).netloc
        if Client.is_challenge(st, url, body) or _CAPTCHA.search(body or b"") or st == 403:
            blocked += 1
            tried.append(f"{host}:{st}=blocked")
            continue
        if st != 200:
            tried.append(f"{host}:{st}")
            bad += 1
            continue
        link = pdf_link((body or b"").decode("utf-8", "replace"), base)
        if not link:
            misses += 1
            tried.append(f"{host}:{st}=no-pdf-link({len(body or b'')}B)")
            continue
        if pacer is not None:
            pacer.wait()
        st2, _hd2, pdf = client.get(link, accept="application/pdf", timeout=300)
        codes.append(int(st2 or 0))
        phost = urllib.parse.urlparse(link).netloc
        if (pdf or b"").startswith(b"%PDF-"):
            return {"status": "downloaded", "pdf": pdf, "source_url": link, "http_codes": codes,
                    "tried": tried + [f"{host}->{phost}:{st2}=ok"], "detail": ""}
        if pdf and rejected is None:          # what the PDF LINK served instead: kept, never dropped
            rejected, rejected_url = pdf, link
        if Client.is_challenge(st2, link, pdf) or st2 == 403:
            blocked += 1
            tried.append(f"{host}->{phost}:{st2}=blocked")
        else:
            bad += 1
            tried.append(f"{host}->{phost}:{st2}")
    status = ("blocked" if blocked and not misses and not bad else
              "not-in-archive" if misses and not bad and not blocked else
              "bad-file" if bad else "blocked" if blocked else "not-in-archive")
    return {"status": status, "pdf": None, "source_url": "", "http_codes": codes, "tried": tried,
            "rejected": rejected, "rejected_url": redact(rejected_url), "detail": redact(", ".join(tried))}

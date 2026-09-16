"""Open-access route: arXiv by id, then every Unpaywall OA location for the DOI (design §10: paper-search is
called as a library from its installed package, never vendored).

Unpaywall needs Kam's email, held only in the untracked D:\\edmonds-pipeline\\secrets\\paper_search.env
(decisions.yaml litkb-p0-foundation §15.5); paper_search_mcp reads that file through PAPER_SEARCH_MCP_ENV_FILE.
The email is never stored, printed or logged by litkb.

-> dict(status, pdf, source_url, tried, detail, http_codes). status: downloaded | no-oa-copy (no location at
all) | bad-file (locations exist, none served a PDF) | blocked (a bot challenge answered) | api-error.

A route that refuses what it was served hands the BYTES back in `rejected` (with `rejected_url`, redacted), and
litkb.acquire.run quarantines them with a reason beside them. Nothing a location served is thrown away: that is
what makes deleting a bad download unnecessary (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9). The bytes handed
back are only ever those fetched from a URL this route believed was the FILE.
"""
import os
import urllib.parse

from litkb.netutil import Client, redact

PAPER_SEARCH_ENV = r"D:\edmonds-pipeline\secrets\paper_search.env"
ARXIV_PDF = "https://arxiv.org/pdf/{id}"


def unpaywall_locations(doi):
    """-> (urls, note). The package's record fetch lists every OA location (its public resolve_best_pdf_url
    returns one URL only)."""
    os.environ.setdefault("PAPER_SEARCH_MCP_ENV_FILE", PAPER_SEARCH_ENV)
    try:
        from paper_search_mcp.academic_platforms.unpaywall import UnpaywallResolver
    except Exception as e:                      # package missing or broken: the route is unavailable
        return [], f"paper_search_mcp unavailable: {type(e).__name__}"
    r = UnpaywallResolver()
    if not r.has_api_access():
        return [], "unpaywall email not configured"
    data = r._fetch_doi_record(doi)
    if not data:
        return [], "unpaywall: no record"
    urls = []
    for loc in [data.get("best_oa_location") or {}] + list(data.get("oa_locations") or []):
        if isinstance(loc, dict):
            for k in ("url_for_pdf", "url"):
                if loc.get(k) and loc[k] not in urls:
                    urls.append(loc[k])
    return urls, f"unpaywall is_oa={bool(data.get('is_oa'))} oa_status={data.get('oa_status', '')}"


def fetch_open_access(doi, arxiv_id, pacer, *, client=None, locations=None):
    client = client or Client()
    locations = locations or unpaywall_locations
    if not arxiv_id and doi and doi.strip().lower().startswith("10.48550/arxiv."):
        # an arXiv DOI names its arXiv id (Scripts/docs/LITERATURE_CONVENTION.md, DOI-first rule 3)
        arxiv_id = doi.strip()[len("10.48550/arxiv."):]
    tried, codes, notes = [], [], []
    urls = []
    if arxiv_id:
        urls.append(ARXIV_PDF.format(id=urllib.parse.quote(arxiv_id, safe="")))
    if doi:
        found, note = locations(doi)
        notes.append(note)
        urls.extend(u for u in found if u not in urls)
    if not urls:
        return {"status": "no-oa-copy", "pdf": None, "source_url": "", "tried": [], "http_codes": [],
                "detail": redact("; ".join(n for n in notes if n) or "no identifier to look up")}
    blocked = False
    rejected, rejected_url = None, ""
    for url in urls:
        if pacer is not None:
            pacer.wait()
        st, _hd, body = client.get(url, accept="application/pdf,*/*;q=0.5", timeout=300)
        codes.append(int(st or 0))
        host = urllib.parse.urlparse(url).netloc
        if (body or b"").startswith(b"%PDF-"):
            return {"status": "downloaded", "pdf": body, "source_url": url, "tried": tried + [f"{host}:{st}=ok"],
                    "http_codes": codes, "detail": redact("; ".join(n for n in notes if n))}
        if body and rejected is None:
            # the first location that served SOMETHING: Unpaywall lists best_oa_location first, so these are the
            # bytes most likely to be what the fetch was for. They are handed back, never dropped.
            rejected, rejected_url = body, url
        if Client.is_challenge(st, url, body):
            blocked = True
        tried.append(f"{host}:{st}")
    return {"status": "blocked" if blocked else "bad-file", "pdf": None, "source_url": "", "tried": tried,
            "http_codes": codes, "rejected": rejected, "rejected_url": redact(rejected_url),
            "detail": redact("; ".join([n for n in notes if n] + [f"no %PDF- from {', '.join(tried)}"]))}

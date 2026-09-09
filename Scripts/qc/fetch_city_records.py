"""Fetch the city/county public records this project cannot reach from a sandboxed session.

WHY THIS EXISTS. The 2026-09-09 lidar-acquisition investigation
(`Reports/LIDAR_ACQUISITION_RECORDS_2026-09-09.md`) established the DATA-CATALOG half of its
answer to machine-verified certainty, because USGS and NOAA publish to AWS S3 and S3 was
reachable. It could not establish the CITY-RECORD half at all: the cloud session's egress proxy
answered HTTP 403 at CONNECT for every city, county, state and news host — edmondswa.gov,
weblink.edmondswa.gov, edmondswa.primegov.com, cdnsm5-hosted.civiclive.com,
snohomishcountywa.gov, dnr.wa.gov, myedmondsnews.com. Four of ten research channels returned
zero citable findings for that reason alone.

So every "no city record exists" statement in that report is search-index-level, not
full-text-verified. This script closes that gap by running the fetch somewhere with ordinary
network access and committing the retrieved TEXT back into the repo, where any later sandboxed
session can read it.

WHAT IT GUARANTEES. Provenance, not just bytes. Every attempt records the final URL after
redirects, HTTP status, declared content type, byte count, sha256 and a UTC timestamp into
`Reports/sources/MANIFEST.tsv`. A failure is recorded AS a failure with its error string and
the list of endpoints tried, never silently skipped — a source that 404s is itself a finding,
and the next reader must be able to tell "checked, absent" from "never checked".

THE PORTAL PROBLEM, AND HOW THIS HANDLES IT. Laserfiche WebLink and PrimeGov are JavaScript
portal applications: a plain GET can return an application shell rather than the document.
Three defences, in order:
  1. Several known WebLink endpoint forms are tried per document (see LASERFICHE_FORMS).
  2. If a response is HTML, its links are HARVESTED and any that look like a document
     (.pdf, edoc, DocDownload, ElectronicFile...) are queued and tried. This beats guessing,
     because the viewer page usually references the real file path.
  3. `--browser` renders the page with Playwright and captures any PDF the page fetches, or
     failing that the rendered text. This is the reliable answer for a portal and is the
     documented fallback when a row comes back FAILED.
An HTML body under MIN_DOC_BYTES is never accepted as a document. Saving a portal shell as if
it were the record would manufacture false evidence, which is worse than a recorded failure.

PROVE IT WORKS BEFORE TRUSTING IT. `--selftest` runs the whole pipeline — fetch, save, extract,
manifest — against two public AWS S3 documents that are known-good and unrelated to the city
servers. If self-test passes, the machinery and this machine's network are fine, and any
subsequent failure is about the target, not the tool. Run it first.

POLITENESS. These are public records servers belonging to a small city. Fetches are serial,
spaced by DELAY_S, identified in the User-Agent, retried at most twice with backoff, and never
parallelised. Do not "speed it up".

USAGE (from the repo's Scripts/ directory):

    py -3.12 qc/fetch_city_records.py --selftest        # prove the pipeline works. Do this first.
    py -3.12 qc/fetch_city_records.py                   # fetch everything not yet fetched
    py -3.12 qc/fetch_city_records.py --status          # print the manifest, fetch nothing
    py -3.12 qc/fetch_city_records.py --retry-failed    # re-attempt prior failures
    py -3.12 qc/fetch_city_records.py --retry-failed --browser   # ...with a real browser
    py -3.12 qc/fetch_city_records.py --only ila-1462454 --browser

Outputs under `Reports/sources/`: raw/<id>.<ext> (untracked bytes), text/<id>.txt (tracked),
MANIFEST.tsv (tracked provenance).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as htmllib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "Reports" / "sources" / "SOURCES.tsv"
OUT = REPO / "Reports" / "sources"
RAW, TEXT = OUT / "raw", OUT / "text"
MANIFEST = OUT / "MANIFEST.tsv"

UA = ("edmonds-treedata-records-fetch/1.1 "
      "(tree canopy research; public records retrieval; contact via repository owner)")
DELAY_S = 2.0
RETRIES = 2
TIMEOUT_S = 90
MIN_DOC_BYTES = 8_000          # an HTML body smaller than this is a shell or an error page
MAX_HARVEST = 6                # bound the link-following so a portal cannot walk us in circles

# Endpoint forms seen across Laserfiche WebLink 9/10 deployments. None is guaranteed for any
# given install, which is exactly why harvest_links() and --browser exist behind them.
LASERFICHE_FORMS = [
    "{base}/WebLink/DocView.aspx?id={id}&dbid={dbid}&repo={repo}",
    "{base}/WebLink/0/edoc/{id}/document.pdf",
    "{base}/WebLink/ElectronicFile.aspx?docid={id}&dbid={dbid}&repo={repo}",
    "{base}/WebLink/DocDownload.aspx?dbid={dbid}&docid={id}&repo={repo}",
]

SELFTEST = [
    ("selftest-pdf",
     "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/"
     "WA_LidarGaps_C22/USGS_WA_LidarGaps_C22_Project_Report.pdf",
     "WA_LidarGaps_C22"),
    ("selftest-xml",
     "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/"
     "WA_3_County_Lidar_2017_B17/WA_3_County_QL1_2017/best_use_xml/"
     "WA_3_Counties_Hydroflattened_Bare_Earth_Metadata.xml",
     "Quantum Spatial"),
]

MANIFEST_COLS = ["id", "status", "http_status", "content_type", "bytes", "sha256",
                 "requested_url", "final_url", "saved_raw", "saved_text",
                 "fetched_at_utc", "method", "note"]


# ── plumbing ──────────────────────────────────────────────────────────────────────────────

def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_sources() -> list[dict]:
    if not SOURCES.exists():
        sys.exit(f"missing source list: {SOURCES}")
    with SOURCES.open(encoding="utf-8") as fh:
        rdr = csv.DictReader((l for l in fh if not l.startswith("#")), delimiter="\t")
        return [{k: (v or "").strip() for k, v in r.items()} for r in rdr if r.get("id")]


def read_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(encoding="utf-8") as fh:
        return {r["id"]: r for r in csv.DictReader(fh, delimiter="\t")}


def write_manifest(recs: dict[str, dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for rid in sorted(recs):
            w.writerow(recs[rid])


def extension_for(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    for needle, ext in (("pdf", "pdf"), ("json", "json"), ("xhtml", "html"),
                        ("html", "html"), ("xml", "xml"), ("plain", "txt")):
        if needle in ct:
            return ext
    tail = url.split("?")[0].rsplit(".", 1)
    if len(tail) == 2 and 1 <= len(tail[1]) <= 5 and tail[1].isalnum():
        return tail[1].lower()
    return "bin"


def fetch(url: str) -> tuple[bytes, str, str, int, str]:
    """Return (body, content_type, final_url, http_status, error). Never raises."""
    last = ""
    for attempt in range(RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.read(), resp.headers.get("Content-Type", ""), resp.geturl(), resp.status, ""
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.reason}"
            if e.code in (400, 401, 403, 404, 410):     # a real answer; don't burn retries
                return b"", "", url, e.code, last
        except Exception as e:                          # noqa: BLE001 - report, never crash
            last = f"{type(e).__name__}: {e}"
        if attempt < RETRIES:
            time.sleep(2 ** (attempt + 1))
    return b"", "", url, 0, last


DOCLIKE = re.compile(
    r"(\.pdf(\?|$)|/edoc/|DocDownload|ElectronicFile|GetDocument|/doc/\d+|download)", re.I)


def harvest_links(body: bytes, base_url: str) -> list[str]:
    """Pull document-looking URLs out of an HTML page. Beats guessing endpoint forms."""
    s = body.decode("utf-8", "replace")
    raw = re.findall(r'(?:href|src|data-url|content)\s*=\s*["\']([^"\']+)["\']', s, re.I)
    raw += re.findall(r'["\'](/[^"\']*?(?:\.pdf|edoc|DocDownload|ElectronicFile)[^"\']*)["\']', s, re.I)
    out, seen = [], set()
    for href in raw:
        href = htmllib.unescape(href.strip())
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        if not DOCLIKE.search(href):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out[:MAX_HARVEST]


def pdf_to_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception:                                   # noqa: BLE001
        pass
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                               capture_output=True, timeout=180)
            return r.stdout.decode("utf-8", "replace")
        except Exception:                               # noqa: BLE001
            pass
    return ""


def html_to_text(body: bytes) -> str:
    s = body.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>|</li>|</h[1-6]>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", s).strip()


def extract(raw_path: Path, body: bytes, ext: str) -> str:
    if ext == "pdf":
        return pdf_to_text(raw_path)
    if ext in ("html", "xml"):
        return html_to_text(body)
    if ext in ("json", "txt", "csv", "tsv"):
        return body.decode("utf-8", "replace")
    return ""


def save(rid: str, body: bytes, ext: str) -> tuple[Path, str]:
    RAW.mkdir(parents=True, exist_ok=True)
    TEXT.mkdir(parents=True, exist_ok=True)
    raw_path = RAW / f"{rid}.{ext}"
    raw_path.write_bytes(body)
    text = extract(raw_path, body, ext)
    text_rel = ""
    if text.strip():
        tp = TEXT / f"{rid}.txt"
        tp.write_text(text, encoding="utf-8")
        text_rel = str(tp.relative_to(REPO)).replace("\\", "/")
    return raw_path, text_rel


def record(rid, status, *, http=0, ct="", body=b"", req="", final="", raw="",
           text="", method="http", note="") -> dict:
    return {"id": rid, "status": status, "http_status": http, "content_type": ct,
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest() if body else "",
            "requested_url": req, "final_url": final, "saved_raw": raw, "saved_text": text,
            "fetched_at_utc": now_utc(), "method": method, "note": note}


# ── browser fallback ──────────────────────────────────────────────────────────────────────

# A rendered search page that reports zero hits with an EMPTY query box did not run the
# search — the URL's searchcommand was not honoured. Recording that as a result would
# manufacture a false negative ("the City has no lidar records"), which is the single most
# damaging error this tool could make. Detected and quarantined, never reported as ok.
UNEXECUTED_SEARCH = re.compile(r"Results\s+0\s*-\s*0\s+of\s+0", re.I)

# 2026-09-09: a SECOND unexecuted-search shape was observed in the wild — the click/type never
# landed at all, so the page rendered with no "Results" line whatsoever (not even 0-0-of-0),
# just the empty form's field labels. That shape has no zero-hit text to match, so it slipped
# past UNEXECUTED_SEARCH above and was recorded as "ok". Any page with no results-count line at
# all, when a term was supplied, gets the same quarantine treatment.
RESULTS_LINE = re.compile(r"Results\s+\d+\s*-\s*\d+\s+of\s+\d+", re.I)


def looks_like_unexecuted_search(text: str, term: str = "") -> bool:
    """True when a page shows no sign of having actually run the query.

    Two shapes, both observed in production against this exact source:
      1. Zero results AND the search term appears nowhere on the rendered page. A page that
         genuinely searched echoes the term — in the query box, a "results for X" heading, or a
         breadcrumb. A page that ignored the URL's searchcommand shows an empty form.
      2. No "Results N - M of K" line at all when a term was supplied — the submit never
         registered, so the page never left its initial empty-form state.
    With no term configured we stay conservative and treat only shape 1 as unproven.
    """
    if UNEXECUTED_SEARCH.search(text):
        if term and term.lower() in text.lower():
            return False     # the term is echoed back: a real zero-hit result
        return True
    if term and not RESULTS_LINE.search(text):
        return True
    return False


def browser_fetch(url: str, search_term: str = "") -> tuple[bytes, str, str, str]:
    """Render with Playwright; capture a PDF the page loads, else the rendered text.

    If `search_term` is given, actually type it into the page's search box and submit,
    rather than trusting a hand-crafted searchcommand URL to run the query.

    Returns (body, content_type, final_url, error). Requires:
        pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return b"", "", url, ("playwright not installed — "
                              "pip install playwright && playwright install chromium")
    captured: list[tuple[bytes, str]] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=UA, accept_downloads=True)

            def on_response(resp):
                try:
                    ct = (resp.headers or {}).get("content-type", "")
                    if "pdf" in ct.lower() and resp.ok:
                        captured.append((resp.body(), ct))
                except Exception:                       # noqa: BLE001
                    pass

            page.on("response", on_response)
            page.goto(url, wait_until="networkidle", timeout=90_000)
            page.wait_for_timeout(3_000)

            if search_term:
                # Drive the form the way a person would. Try the likeliest inputs in order.
                for sel in ('input[type="search"]', "#searchTerms", "#SearchTerms",
                            'input[name*="search" i]', 'input[id*="search" i]',
                            'input[type="text"]'):
                    try:
                        box = page.locator(sel).first
                        if box.count() == 0 or not box.is_visible():
                            continue
                        box.fill(search_term)
                        box.press("Enter")
                        page.wait_for_timeout(6_000)
                        break
                    except Exception:                   # noqa: BLE001 - try the next selector
                        continue

            final = page.url
            text = page.inner_text("body")
            browser.close()
        if captured:
            body, ct = max(captured, key=lambda b: len(b[0]))
            return body, ct, final, ""
        if text and text.strip():
            return text.encode("utf-8"), "text/plain", final, ""
        return b"", "", final, "rendered page had no PDF and no text"
    except Exception as e:                              # noqa: BLE001
        return b"", "", url, f"{type(e).__name__}: {e}"


# ── per-source driver ─────────────────────────────────────────────────────────────────────

def process(src: dict, use_browser: bool) -> dict:
    rid = src["id"]
    queue = [u.strip() for u in src["url"].split("|") if u.strip()]
    tried: list[str] = []
    harvested = 0

    while queue:
        url = queue.pop(0)
        print(f"  -> {url}", flush=True)
        body, ct, final, status, err = fetch(url)
        time.sleep(DELAY_S)

        if err or not body:
            tried.append(f"{url} => {err or 'empty body'}")
            continue

        ext = extension_for(ct, final)
        if ext in ("html", "bin") and len(body) < MIN_DOC_BYTES:
            tried.append(f"{url} => {len(body)}B {ext} (shell/error page)")
            continue

        # An HTML page that is big enough to be real may still be a viewer wrapping the
        # document. Harvest its links and prefer a genuine file over the wrapper.
        if ext == "html" and harvested < MAX_HARVEST:
            found = [u for u in harvest_links(body, final) if u not in tried and u not in queue]
            if found:
                harvested += len(found)
                queue = found + queue
                tried.append(f"{url} => html, harvested {len(found)} candidate link(s)")
                continue

        raw_path, text_rel = save(rid, body, ext)
        return record(rid, "ok" if text_rel else "fetched_no_text", http=status, ct=ct,
                      body=body, req=url, final=final,
                      raw=str(raw_path.relative_to(REPO)).replace("\\", "/"),
                      text=text_rel, method="http", note=src.get("note", ""))

    if use_browser:
        term = src.get("search_term", "")
        for url in [u.strip() for u in src["url"].split("|") if u.strip()][:2]:
            print(f"  -> [browser] {url}" + (f"  (typing '{term}')" if term else ""), flush=True)
            body, ct, final, err = browser_fetch(url, term)
            if body:
                ext = extension_for(ct, final)
                rendered = body.decode("utf-8", "replace") if ext in ("txt", "html") else ""
                if rendered and looks_like_unexecuted_search(rendered, term):
                    # Quarantine: a zero-hit page with an empty query box proves nothing.
                    tried.append(f"[browser] {url} => search form rendered but NOT executed "
                                 f"(empty query box, 'Results 0 - 0 of 0')")
                    continue
                raw_path, text_rel = save(rid, body, ext)
                return record(rid, "ok" if text_rel else "fetched_no_text", http=200, ct=ct,
                              body=body, req=url, final=final,
                              raw=str(raw_path.relative_to(REPO)).replace("\\", "/"),
                              text=text_rel, method="browser", note=src.get("note", ""))
            tried.append(f"[browser] {url} => {err}")

    return record(rid, "FAILED", req=(src["url"].split("|")[0].strip()),
                  method="browser" if use_browser else "http",
                  note=f"{src.get('note','')} || TRIED: " + " ; ".join(tried))


def run_selftest() -> int:
    print("self-test: proving fetch -> save -> extract -> manifest against public S3\n")
    ok = True
    for rid, url, needle in SELFTEST:
        print(f"  {rid}")
        body, ct, final, status, err = fetch(url)
        if err or not body:
            print(f"    FAIL fetch: {err or 'empty'}"); ok = False; continue
        ext = extension_for(ct, final)
        raw_path, text_rel = save(rid, body, ext)
        text = (TEXT / f"{rid}.txt").read_text(encoding="utf-8") if text_rel else ""
        good = needle.lower() in text.lower()
        print(f"    {status} {ct} {len(body)}B -> {ext}; text {len(text)} chars; "
              f"expected marker {'FOUND' if good else 'MISSING'}")
        if not good:
            ok = False
        raw_path.unlink(missing_ok=True)
        (TEXT / f"{rid}.txt").unlink(missing_ok=True)
    print()
    if ok:
        print("SELF-TEST PASSED — network, PDF/XML extraction and file writing all work.")
        print("Any failure from here on is about the target server, not this tool.")
        return 0
    print("SELF-TEST FAILED.")
    print("If fetch failed: this machine cannot reach even public AWS S3 — check the network.")
    print("If text was MISSING: no PDF extractor. Run:  py -3.12 -m pip install pypdf")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", metavar="ID", help="fetch only these source ids")
    ap.add_argument("--retry-failed", action="store_true", help="re-attempt prior failures")
    ap.add_argument("--refetch", action="store_true", help="re-fetch even if already ok")
    ap.add_argument("--status", action="store_true", help="print the manifest and exit")
    ap.add_argument("--selftest", action="store_true", help="prove the pipeline works, then exit")
    ap.add_argument("--browser", action="store_true",
                    help="fall back to Playwright for JS portals (Laserfiche, PrimeGov)")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    recs = read_manifest()

    if args.status:
        if not recs:
            print("no manifest yet — nothing fetched")
            return 0
        w = max(len(r) for r in recs)
        for rid in sorted(recs):
            r = recs[rid]
            print(f"  {rid:<{w}}  {r['status']:<16} {str(r.get('bytes','0')):>9}B  "
                  f"{r.get('method',''):<8} {r.get('saved_text','')}")
        bad = [r["id"] for r in recs.values() if r["status"] == "FAILED"]
        print(f"\n{len(recs)} sources, {len(bad)} failed")
        if bad:
            print("failed: " + ", ".join(sorted(bad)))
        return 0

    todo = []
    for s in read_sources():
        if args.only and s["id"] not in args.only:
            continue
        prev = recs.get(s["id"])
        if args.retry_failed and (not prev or prev["status"] != "FAILED"):
            continue
        if prev and prev["status"] == "ok" and not args.refetch and not args.retry_failed:
            continue
        todo.append(s)

    if not todo:
        print("nothing to do (--refetch to force, --status to inspect)")
        return 0

    print(f"fetching {len(todo)} source(s), {DELAY_S}s apart"
          f"{' (browser fallback ON)' if args.browser else ''}\n")
    for i, s in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {s['id']}  — {s.get('note','')[:70]}")
        rec = process(s, args.browser)
        recs[rec["id"]] = rec
        write_manifest(recs)
        print(f"      {rec['status']}  {rec['bytes']}B  via {rec['method']}  "
              f"{rec['saved_text'] or '(no text)'}\n")

    ok = sum(1 for r in recs.values() if r["status"] == "ok")
    failed = sorted(r["id"] for r in recs.values() if r["status"] == "FAILED")
    print(f"done: {ok}/{len(recs)} with text; {len(failed)} failed")
    if failed:
        print("failed: " + ", ".join(failed))
        if not args.browser:
            print("\nNext: re-run with --browser to render the JS portals:")
            print("  py -3.12 qc/fetch_city_records.py --retry-failed --browser")
        else:
            print("\nThese need a manual save from a browser. Open the URL in MANIFEST.tsv,")
            print("save the PDF, and drop it in Reports/sources/raw/<id>.pdf, then re-run --status.")
    print(f"\nmanifest: {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

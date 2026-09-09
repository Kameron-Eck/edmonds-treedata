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
network access — a desktop on home wifi, or a GitHub Actions runner — and committing the
retrieved text back into the repo, where any later session can read it without egress.

WHAT IT GUARANTEES. Provenance, not just bytes. Every fetch records the final URL after
redirects, the HTTP status, the declared content type, the byte count, a sha256, and the UTC
timestamp, into `Reports/sources/MANIFEST.tsv`. A failed fetch is recorded as a failure with
its error string rather than silently skipped — a source that 404s is itself a finding, and the
next session needs to know the difference between "checked, absent" and "never checked".

WHAT IT DOES NOT DO. It does not drive JavaScript. Laserfiche WebLink and PrimeGov are portal
applications, so a plain GET may return an application shell instead of the document. The
script tries several known WebLink endpoint forms per document and reports which one, if any,
returned a real file; where all of them return HTML too small to be a document, the manifest
says so and the fallback is a browser (Playwright) or a manual save. Nothing here pretends a
portal shell is a record.

POLITENESS. These are public records servers belonging to a small city. The script fetches
serially with a delay between requests, identifies itself in the User-Agent, retries a failure
at most twice with backoff, and never parallelises. Do not "speed it up".

USAGE (from the repo's Scripts/ directory):

    py -3.12 qc/fetch_city_records.py                 # fetch everything not yet fetched
    py -3.12 qc/fetch_city_records.py --retry-failed  # re-attempt only prior failures
    py -3.12 qc/fetch_city_records.py --only rfp-18-26 ufmp-2019
    py -3.12 qc/fetch_city_records.py --status        # print the manifest, fetch nothing

Outputs, all under `Reports/sources/`:
    raw/<id>.<ext>    the bytes exactly as served
    text/<id>.txt     extracted text (PDF via pypdf or pdftotext; HTML via tag-strip)
    MANIFEST.tsv      one row per attempt, the provenance record

Only `text/` and `MANIFEST.tsv` are worth committing; `raw/` is large and is git-ignored by the
repo's whitelist .gitignore unless deliberately re-admitted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "Reports" / "sources" / "SOURCES.tsv"
OUT = REPO / "Reports" / "sources"
RAW = OUT / "raw"
TEXT = OUT / "text"
MANIFEST = OUT / "MANIFEST.tsv"

# Identify the fetcher honestly. A public-records server operator who sees this in a log should
# be able to tell what it is and that it is not hostile traffic.
UA = (
    "edmonds-treedata-records-fetch/1.0 "
    "(tree canopy research; public records retrieval; contact via repository owner)"
)
DELAY_S = 2.0
RETRIES = 2
TIMEOUT_S = 90
# A "document" that is 3 KB of HTML is a portal shell or an error page, not a record.
MIN_DOC_BYTES = 8_000

MANIFEST_COLS = [
    "id", "status", "http_status", "content_type", "bytes", "sha256",
    "requested_url", "final_url", "saved_raw", "saved_text", "fetched_at_utc", "note",
]


def read_sources() -> list[dict]:
    if not SOURCES.exists():
        sys.exit(f"missing source list: {SOURCES}")
    rows = []
    with SOURCES.open(encoding="utf-8") as fh:
        for row in csv.DictReader((l for l in fh if not l.startswith("#")), delimiter="\t"):
            if row.get("id"):
                rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def read_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(encoding="utf-8") as fh:
        return {r["id"]: r for r in csv.DictReader(fh, delimiter="\t")}


def write_manifest(recs: dict[str, dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLS, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        for rid in sorted(recs):
            w.writerow(recs[rid])


def extension_for(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return "pdf"
    if "json" in ct:
        return "json"
    if "html" in ct or "xhtml" in ct:
        return "html"
    if "xml" in ct:
        return "xml"
    tail = url.split("?")[0].rsplit(".", 1)
    if len(tail) == 2 and 1 <= len(tail[1]) <= 5 and tail[1].isalnum():
        return tail[1].lower()
    return "bin"


def fetch_once(url: str) -> tuple[bytes, str, str, int]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        body = resp.read()
        return body, resp.headers.get("Content-Type", ""), resp.geturl(), resp.status


def fetch(url: str) -> tuple[bytes, str, str, int, str]:
    """Return (body, content_type, final_url, http_status, error). Never raises."""
    last = ""
    for attempt in range(RETRIES + 1):
        try:
            body, ct, final, status = fetch_once(url)
            return body, ct, final, status, ""
        except urllib.error.HTTPError as e:
            # A 404 is a real answer about the record; do not burn retries on it.
            last = f"HTTP {e.code} {e.reason}"
            if e.code in (400, 401, 403, 404, 410):
                return b"", e.headers.get("Content-Type", "") if e.headers else "", url, e.code, last
        except Exception as e:                                   # noqa: BLE001 - report, never crash
            last = f"{type(e).__name__}: {e}"
        if attempt < RETRIES:
            time.sleep(2 ** (attempt + 1))
    return b"", "", url, 0, last


def pdf_to_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception:                                            # noqa: BLE001
        pass
    import shutil
    import subprocess
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                 capture_output=True, timeout=180)
            return out.stdout.decode("utf-8", "replace")
        except Exception:                                        # noqa: BLE001
            pass
    return ""


def html_to_text(body: bytes) -> str:
    s = body.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", s).strip()


def looks_like_portal_shell(body: bytes, ext: str) -> bool:
    return ext in ("html", "bin") and len(body) < MIN_DOC_BYTES


def process(src: dict) -> dict:
    rid = src["id"]
    urls = [u.strip() for u in src["url"].split("|") if u.strip()]
    RAW.mkdir(parents=True, exist_ok=True)
    TEXT.mkdir(parents=True, exist_ok=True)

    attempts: list[str] = []
    for url in urls:
        print(f"  -> {url}", flush=True)
        body, ct, final, status, err = fetch(url)
        time.sleep(DELAY_S)

        if err or not body:
            attempts.append(f"{url} => {err or 'empty body'}")
            continue

        ext = extension_for(ct, final)
        if looks_like_portal_shell(body, ext):
            attempts.append(f"{url} => {len(body)}B {ext} (portal shell or error page)")
            continue

        raw_path = RAW / f"{rid}.{ext}"
        raw_path.write_bytes(body)

        if ext == "pdf":
            text = pdf_to_text(raw_path)
        elif ext in ("html", "xml"):
            text = html_to_text(body)
        else:
            text = body.decode("utf-8", "replace") if ext in ("json", "txt", "csv") else ""

        text_path = ""
        if text.strip():
            tp = TEXT / f"{rid}.txt"
            tp.write_text(text, encoding="utf-8")
            text_path = str(tp.relative_to(REPO)).replace("\\", "/")

        return {
            "id": rid,
            "status": "ok" if text.strip() else "fetched_no_text",
            "http_status": status,
            "content_type": ct,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "requested_url": url,
            "final_url": final,
            "saved_raw": str(raw_path.relative_to(REPO)).replace("\\", "/"),
            "saved_text": text_path,
            "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": src.get("note", ""),
        }

    return {
        "id": rid, "status": "FAILED", "http_status": "", "content_type": "", "bytes": 0,
        "sha256": "", "requested_url": urls[0] if urls else "", "final_url": "",
        "saved_raw": "", "saved_text": "",
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": f"{src.get('note','')} || ATTEMPTS: " + " ; ".join(attempts),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", metavar="ID", help="fetch only these source ids")
    ap.add_argument("--retry-failed", action="store_true",
                    help="re-attempt sources whose last status was FAILED")
    ap.add_argument("--refetch", action="store_true", help="re-fetch even if already ok")
    ap.add_argument("--status", action="store_true", help="print the manifest and exit")
    args = ap.parse_args()

    sources = read_sources()
    recs = read_manifest()

    if args.status:
        if not recs:
            print("no manifest yet — nothing fetched")
            return 0
        w = max(len(r) for r in recs)
        for rid in sorted(recs):
            r = recs[rid]
            print(f"  {rid:<{w}}  {r['status']:<16} {r.get('bytes','0'):>9}B  {r.get('saved_text','')}")
        bad = [r for r in recs.values() if r["status"] == "FAILED"]
        print(f"\n{len(recs)} sources, {len(bad)} failed")
        return 0

    todo = []
    for s in sources:
        if args.only and s["id"] not in args.only:
            continue
        prev = recs.get(s["id"])
        if args.retry_failed and (not prev or prev["status"] != "FAILED"):
            continue
        if prev and prev["status"] == "ok" and not args.refetch and not args.retry_failed:
            continue
        todo.append(s)

    if not todo:
        print("nothing to do (use --refetch to force, --status to inspect)")
        return 0

    print(f"fetching {len(todo)} source(s), {DELAY_S}s apart\n")
    for i, s in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {s['id']}  — {s.get('note','')[:70]}")
        rec = process(s)
        recs[rec["id"]] = rec
        write_manifest(recs)
        print(f"      {rec['status']}  {rec['bytes']}B  {rec['saved_text'] or '(no text)'}\n")

    ok = sum(1 for r in recs.values() if r["status"] == "ok")
    failed = [r["id"] for r in recs.values() if r["status"] == "FAILED"]
    print(f"done: {ok}/{len(recs)} with text; {len(failed)} failed")
    if failed:
        print("failed: " + ", ".join(sorted(failed)))
        print("these likely need a browser (JS portal) or a manual save — see MANIFEST.tsv notes")
    print(f"\nmanifest: {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

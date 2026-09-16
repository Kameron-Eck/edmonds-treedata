"""Anna's Archive member route — ported from D:\\tools\\annas-mcp\\aa_fetch.py (2026-09-13) into litkb
(design §10: "aa_fetch archive route and gates -> litkb.acquire.annas"). Never prints, logs or stores the key.

What changed in the port, and nothing else:
  * the HTTP client, pacer and redaction live in litkb.netutil; the gate-0 resolver in litkb.admit.resolver
    (both re-exported here, so the ported tests address one module);
  * litkb acquisition calls fetch_for_litkb(): gates 1, 1b, 2, the download ladder and gate 3's byte checks
    (%PDF-, md5 = the archive's identity, filesize_best). Filing, sha256 dedupe, binding and the database
    record belong to litkb.acquire.run, which writes acquisition_attempts, never manifest.csv;
  * fetch_one() (the aa_fetch filing path, kept because its tests exercise the gates end to end) refuses a
    destination inside the literature store outside _litkb_staging (Validation/ and the other topic folders
    are never written), and _quarantine() never overwrites;
  * main() keeps --resolve-only, --audit and --audit-fast (all read-only). Its job mode, which filed papers and
    appended manifest rows, is refused: acquisition goes through `py -3.12 -m litkb acquire`.

DOI-first rule (Kam, 2026-09-13; Scripts/docs/LITERATURE_CONVENTION.md): Anna's Archive is queried by DOI ONLY.

Three gates, because following the SciDB redirect filed 10 wrong papers in one batch (2026-09-13):
  1. RESOLVE  GET /scidb/<doi>/ with redirects DISABLED. A 3xx whose Location path starts with /search means
     the DOI is not in the SciDB index -> `not-in-archive`, no download. Other 3xx are followed at most 2 hops,
     same host only. On 200 the md5 is taken from the record's own canonical `/md5/<32hex>` anchor; more than
     one distinct id, or a non-md5 record id, -> `unresolved`. A 200 with NO record anchor is a miss and falls
     through to gate 1b.
  1b. SEARCH FALLBACK  /search?index=journals&q=<doi>; gate 2 on each `/md5/` candidate in page order (cap 10);
     the first record whose OWN DOI matches wins, an unverified first hit never does.
  2. VERIFY RECORD  /db/aarecord_elasticsearch/md5:<md5>.json must list the requested DOI and
     extension_best == "pdf", else `record-mismatch`.
  3. VERIFY FILE  %PDF- header (`bad-file`); md5(bytes) == the requested md5 and the filesize_best
     (`hash-mismatch`). fetch_one() adds its manifest-hash and content checks; litkb adds sha256 dedupe against
     the disk and the database and the first-page binding (litkb.admit.binding).
Downloads retry before giving up: fast_download.json over domain_index 0,1,2 (5 s apart), then each alternate
host the record lists; re-requesting the same md5 is quota-free. Pacing: >= 5 s between SciDB requests; 60 s
back-off on 429 or a rate-limit body.
"""
import csv
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from litkb.admit.resolver import (  # noqa: F401  (re-exported: the ported tests address this module)
    ARXIV_BACKOFFS, ARXIV_DOI_PREFIX, ARXIV_ID_LIST, ARXIV_MIN_INTERVAL, ARXIV_SEARCH, ATOM_NS, CROSSREF_SEARCH,
    CROSSREF_WORK, REGISTRY_BACKOFF, REGISTRY_MIN_INTERVAL, REGISTRY_STAGES, RESOLVE_TITLE_RATIO, S2_SEARCH,
    _ascii_fold, _json, _norm_text, _year_int, arxiv_get, arxiv_pacer_for, family_matches, family_name,
    judge_candidate, normalize_doi, registry_get, resolution_log_line, resolve_doi, search_arxiv, search_crossref,
    search_semanticscholar, title_match_ratio)
from litkb.netutil import (  # noqa: F401
    _SECRETS, BASE, CHALLENGE_RE, RATE_BACKOFF, SCIDB_MIN_INTERVAL, UA, Client, Pacer, _NoRedirect, add_secret,
    redact)

KEY_FILE = r"D:\edmonds-pipeline\secrets\Anna_key.txt"
LITERATURE_ROOT = Path(os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture"))
DEST = str(LITERATURE_ROOT / "Validation")        # read-only here: --audit / --audit-fast read its manifest
# Durable, and deliberately OUTSIDE Validation\ so manifest/corpus checks never see it.
QUARANTINE = str(LITERATURE_ROOT / "_quarantine")
STAGING = str(LITERATURE_ROOT / "_litkb_staging")

TITLE_RATIO = 0.6
MIN_EXTRACT_CHARS = 200   # below this the extract has no text layer -> content check indeterminate
MANIFEST_FIELDS = ["stem", "title", "authors", "year", "venue", "doi", "arxiv", "source_route",
                   "obtained_date", "sha256", "verified_against_extract", "cited_by"]
SOURCE_ROUTE = "annas-archive member API (scidb → record-verified md5 → fast_download)"
RATE_RE = re.compile(rb"rate.?limit|too many requests|slow down", re.I)
MD5_HREF_RE = re.compile(r'href="/md5/([0-9a-f]{32})"')
RECORD_HREF_RE = re.compile(r'href="/([a-z0-9_]+)/([0-9a-zA-Z_.:-]{6,})"')
SEARCH_CANDIDATE_CAP = 10
SCIDB_EMPTY = "scidb-empty"
SEARCH_MISS_STATES = ("not-in-archive", SCIDB_EMPTY)
DOWNLOAD_DOMAIN_INDEXES = (0, 1, 2)
DOWNLOAD_RETRY_GAP = 5.0
JSTOR_PREFIX = "10.2307/"
JSTOR_STABLE_RE = re.compile(r"jstor\.org/stable/(\d+)(?!\d)", re.I)
# The account-wide quota counter (the authority on what this account has spent; per-run counting is only a local
# second guard). GET /account/ (logged in) prints "Fast downloads used (last 18 hours): N / M", and renders any "24"
# in N or M as "<span>2</span>4" (the page's own HTML comment says so), so tags are removed WITHOUT inserting spaces.
ACCOUNT_PATH = "/account/"
QUOTA_RE = re.compile(r"Fast downloads used \(last 18 hours\):\s*(\d+)\s*/\s*(\d+)")
_QUOTA_HIDDEN_RE = re.compile(r"(?is)<!--.*?-->|<(script|style)\b[^>]*>.*?</\1\s*>")


class DestinationRefused(RuntimeError):
    """fetch_one() was pointed at a literature folder it may not write (anything outside _litkb_staging)."""


# ---------------------------------------------------------------- helpers

def title_similarity(title, text):
    """Max difflib ratio of the normalised title against 1-3 consecutive-line windows."""
    import difflib

    t = _norm_text(title)
    if not t:
        return 0.0
    lines = [_norm_text(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    best = 0.0
    for i in range(len(lines)):
        for n in (1, 2, 3):
            if i + n > len(lines):
                break
            w = " ".join(lines[i:i + n])
            best = max(best, difflib.SequenceMatcher(None, t, w).ratio())
    return best


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_fields(manifest):
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8", newline="") as fh:
            hdr = next(csv.reader(fh), None)
        if hdr:
            return hdr
    return list(MANIFEST_FIELDS)


def manifest_hashes(manifest):
    out = set()
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("sha256"):
                    out.add(r["sha256"].strip().lower())
    return out


def result(status, stem, doi, **kw):
    r = {"status": status, "stem": stem, "doi": doi, "record_doi": "", "md5": "",
         "sha256": "", "bytes": "", "downloads_left": "", "location": "", "detail": "",
         "title_best": "", "disk_md5": "", "rec_size": ""}
    r.update(kw)
    r["detail"] = redact(r["detail"])
    return r


def _field(v):
    return "-" if v is None or v == "" else str(v)


def log_line(r):
    """status | stem | doi | record_doi | md5 | sha256[:12] | bytes=<n> | left=<n>
    [| rec_size=<filesize_best>] [| detail].  rec_size appears only when a record was fetched."""
    parts = [f"{r['status']:<15}", r["stem"], r["doi"], r["record_doi"] or "-",
             r["md5"] or "-", (r["sha256"] or "-")[:12],
             f"bytes={_field(r['bytes'])}", f"left={_field(r['downloads_left'])}"]
    if r.get("rec_size") not in (None, ""):
        parts.append(f"rec_size={r['rec_size']}")
    return redact(" | ".join(parts + ([r["detail"]] if r["detail"] else [])))


# ---------------------------------------------------------------- gate 1

def resolve(client, doi, pacer, max_hops=2):
    """-> (md5|None, status, detail, location).  Redirects DISABLED."""
    url = f"{client.base}/scidb/{urllib.parse.quote(doi, safe='/:()')}/"
    seen_loc = ""
    for hop in range(max_hops + 1):
        for attempt in (0, 1):
            pacer.wait()
            st, hd, body = client.get(url, accept="text/html", follow=False)
            # only non-200 bodies are scanned for rate-limit text: a 200 scidb page bundles
            # ~100 KB of JS that could contain those words and would never recover.
            if st == 429 or (st and st != 200 and RATE_RE.search(body or b"")):
                if attempt == 0:
                    pacer.backoff()
                    continue
                return None, "api-error", f"rate limited on scidb (status {st})", seen_loc
            break
        if st in (301, 302, 303, 307, 308):
            loc = (hd.get("Location") or hd.get("location") or "").strip()
            seen_loc = loc
            if not loc:
                return None, "api-error", f"scidb {st} with no Location", seen_loc
            # BEGIN guard: annas gate 1 a redirect to /search is not-in-archive
            if urllib.parse.urlparse(loc).path.startswith("/search"):
                return None, "not-in-archive", f"scidb {st} -> {loc}", seen_loc
            # END guard: annas gate 1 a redirect to /search is not-in-archive
            nxt = urllib.parse.urljoin(url, loc)
            if urllib.parse.urlparse(nxt).netloc != urllib.parse.urlparse(client.base).netloc:
                return None, "api-error", f"scidb {st} -> off-site {loc}", seen_loc
            url = nxt
            continue
        if st != 200:
            return None, "api-error", f"scidb status {st}", seen_loc
        html = (body or b"").decode("utf-8", "replace")
        md5s = sorted(set(MD5_HREF_RE.findall(html)))
        if len(md5s) == 1:
            return md5s[0], "", "", seen_loc
        if not md5s:
            others = sorted({p for p, _ in RECORD_HREF_RE.findall(html)
                             if p.endswith("_download") or p in ("nexusstc", "doi")})
            if others:
                return None, "unresolved", f"non-md5 record id on scidb 200 (saw {others})", seen_loc
            return None, SCIDB_EMPTY, "no record anchor on scidb 200", seen_loc
        return None, "unresolved", f"{len(md5s)} distinct md5 ids on scidb 200", seen_loc
    return None, "api-error", f"more than {max_hops} redirect hops", seen_loc


# ---------------------------------------------------------------- gate 2

def get_json_backoff(client, url, pacer):
    """One 60 s retry on a 429 from the non-scidb JSON endpoints."""
    for attempt in (0, 1):
        st, hd, body = client.get(url, accept="application/json")
        if st == 429 and attempt == 0 and pacer is not None:
            pacer.backoff()
            continue
        return st, hd, body


def verify_record(client, md5, doi, pacer=None):
    """-> (file_unified_data|None, additional, record_doi, status, detail)."""
    url = f"{client.base}/db/aarecord_elasticsearch/md5:{md5}.json"
    st, _, body = get_json_backoff(client, url, pacer)
    if st != 200:
        return None, {}, "", "api-error", f"record json status {st}"
    try:
        j = json.loads((body or b"").decode("utf-8", "replace"))
    except Exception as e:
        return None, {}, "", "api-error", f"record json unparseable: {type(e).__name__}"
    if isinstance(j, list):
        j = j[0] if j else {}
    fud = (j or {}).get("file_unified_data") or {}
    add = (j or {}).get("additional") or {}
    dois = [str(d).strip().lower() for d in
            ((fud.get("identifiers_unified") or {}).get("doi") or [])]
    rec_doi = dois[0] if dois else ""
    # BEGIN guard: annas gate 2 the record carries the requested DOI
    if doi.lower() not in dois:
        return None, add, rec_doi, "record-mismatch", f"record dois {dois or 'none'} != {doi}"
    # END guard: annas gate 2 the record carries the requested DOI
    if (fud.get("extension_best") or "").lower() != "pdf":
        return None, add, rec_doi, "record-mismatch", f"extension_best={fud.get('extension_best')!r}"
    return fud, add, rec_doi, "", ""


# ------------------------------------------------------- gate 1b: search fallback

def resolve_via_search(client, doi, pacer):
    """SciDB missed, but the journals search index may still hold it.  EVERY candidate is verified through
    gate 2 before it can win — taking the first search hit unverified is exactly the original defect."""
    url = f"{client.base}/search?index=journals&q={urllib.parse.quote(doi, safe='')}"
    pacer.wait()
    st, _, body = client.get(url, accept="text/html")
    if st != 200:
        return None, None, "", "", f"search status {st}"
    html = (body or b"").decode("utf-8", "replace")
    seen, cands = set(), []
    for m in MD5_HREF_RE.findall(html):                 # DOM order, deduped
        if m not in seen:
            seen.add(m)
            cands.append(m)
        if len(cands) >= SEARCH_CANDIDATE_CAP:
            break
    for i, md5 in enumerate(cands):
        if i:
            pacer.sleep(1.0)       # /db/ is tolerated, not sanctioned: don't burst 10 hits
        fud, add, rec_doi, status, _ = verify_record(client, md5, doi, pacer)
        if fud is not None:
            return md5, fud, add, rec_doi, f"search candidate {cands.index(md5) + 1}/{len(cands)}"
    return None, None, {}, "", f"{len(cands)} search candidates, none matched the DOI"


# ------------------------------------------------------- download ladder

def download_options(add):
    """Extra hosts from the record we already fetched, in the order AA lists them."""
    out = []
    for entry in (add.get("download_urls") or []):
        if isinstance(entry, (list, tuple)) and len(entry) >= 2 and entry[1]:
            out.append((str(entry[0]), str(entry[1])))
    for entry in (add.get("ipfs_urls") or []):
        if isinstance(entry, dict) and entry.get("url"):
            out.append((f"ipfs/{entry.get('name', '')}", entry["url"]))
    seen, uniq = set(), []
    for name, u in out:
        if u not in seen:
            seen.add(u)
            uniq.append((name, u))
    return uniq


def download_pdf(client, key, md5, add, pacer, issued=None, rejected=None):
    """fast_download over domain_index 0..2, then the record's own options.
    Re-requesting the same md5 is quota-free, so the retries cost nothing.
    `issued`, when a list, receives the domain_index of every fast_download answer that carried a download_url
    (the archive spends a download when it ISSUES a URL for a new md5, whatever the partner host then answers).
    `rejected`, when a list, receives (url, bytes) for the FIRST non-empty answer a download URL served that was
    not a PDF - a partner error page, a login wall. Those bytes are handed back so the caller can quarantine them
    instead of dropping them (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9).
    -> (pdf_bytes|None, downloads_left, tried[list of str], last_status)."""
    tried, left, last = [], "", 0

    def keep(url, body):
        if body and rejected is not None and not rejected:
            rejected.append((url, body))
    for i, di in enumerate(DOWNLOAD_DOMAIN_INDEXES):
        if i:
            pacer.sleep(DOWNLOAD_RETRY_GAP)
        st, _, body = get_json_backoff(
            client, f"{client.base}/dyn/api/fast_download.json?md5={md5}"
                    f"&key={urllib.parse.quote(key)}&domain_index={di}", pacer)
        try:
            j = json.loads((body or b"").decode("utf-8", "replace"))
        except Exception:
            j = {}
        left = (j.get("account_fast_download_info") or {}).get("downloads_left", left)
        url = j.get("download_url")
        if not url:
            tried.append(f"api{di}:{st}/{redact(j.get('error'))}")
            continue
        if issued is not None:
            issued.append(di)
        host = urllib.parse.urlparse(url).netloc
        st, _, pdf = client.get(url, accept="application/pdf", timeout=600)
        last = st
        if (pdf or b"").startswith(b"%PDF-"):
            return pdf, left, tried + [f"{host}:{st}=ok"], st
        keep(url, pdf)
        tried.append(f"{host}:{st}")
    for name, u in download_options(add):
        u = urllib.parse.urljoin(client.base + "/", u)
        host = urllib.parse.urlparse(u).netloc
        pacer.sleep(DOWNLOAD_RETRY_GAP)
        st, _, pdf = client.get(u, accept="application/pdf", timeout=600)
        last = st
        if (pdf or b"").startswith(b"%PDF-"):
            return pdf, left, tried + [f"{name}@{host}:{st}=ok"], st
        keep(u, pdf)
        tried.append(f"{name}@{host}:{st}")
    return None, left, tried, last


def doi_in_extract(head, doi):
    """The DOI itself, or — for a 10.2307/<n> DOI — a JSTOR stable URL carrying the same <n>."""
    low = (head or "").lower()
    if doi and doi in low:
        return True
    if doi and doi.startswith(JSTOR_PREFIX):
        n = doi[len(JSTOR_PREFIX):]
        return n.isdigit() and any(m.lstrip("0") == n.lstrip("0")
                                   for m in JSTOR_STABLE_RE.findall(low))
    return False


def crossref_title(client, doi, pacer):
    """message.title[0] from Crossref's work record for the DOI, or ''.  Never raises."""
    try:
        st, body = registry_get(client, CROSSREF_WORK.format(doi=urllib.parse.quote(doi, safe="/")),
                                pacer)
    except Exception:
        return ""
    j = _json(body) if st == 200 else None
    msg = j.get("message") if isinstance(j, dict) else None
    titles = (msg.get("title") if isinstance(msg, dict) else None) or []
    return next((str(t).strip() for t in titles if t and str(t).strip()), "")


def content_check(head, doi, title, title_getter=None):
    """-> (ok, kind, ratio, title_src).
    kind: doi | title | record (no text layer) | record (no title available) | mismatch."""
    if doi_in_extract(head, doi):
        return True, "doi", 1.0, "none"
    src = "record" if title else "none"
    if not title and title_getter is not None:
        title, src = title_getter()
    if not title:
        return True, "record (no title available)", 0.0, "none"
    ratio = title_similarity(title, head or "")
    if ratio >= TITLE_RATIO:
        return True, "title", ratio, src
    if len(_norm_text(head)) < MIN_EXTRACT_CHARS:
        return True, "record (no text layer)", ratio, src
    return False, "mismatch", ratio, src


def make_title_getter(meta, doi, registry_client, registry_pacer):
    """Fallback titles after an empty record title_best: the job's own title, then Crossref by DOI."""
    def get():
        t = ((meta or {}).get("title") or "").strip()
        if t:
            return t, "job"
        rc = registry_client if registry_client is not None else Client()
        rp = (registry_pacer if registry_pacer is not None
              else Pacer(interval=REGISTRY_MIN_INTERVAL, backoff=REGISTRY_BACKOFF))
        t = crossref_title(rc, doi, rp)
        return (t, "crossref") if t else ("", "none")
    return get


# ---------------------------------------------------------------- the account counter

def parse_quota(page):
    """The account page -> (used, limit), or None when the counter cannot be read unambiguously (fail closed).
    Comments, scripts and styles are dropped, tags are removed without a space, entities unescaped, whitespace
    collapsed; then QUOTA_RE must match, and every match must agree. No match (logged out, the line removed, the
    wording changed), disagreeing matches, or a limit of 0 -> None."""
    import html as _html

    if isinstance(page, (bytes, bytearray)):
        page = bytes(page).decode("utf-8", "replace")
    text = _QUOTA_HIDDEN_RE.sub(" ", page or "")
    text = " ".join(_html.unescape(re.sub(r"<[^>]*>", "", text)).split())
    found = {(int(u), int(m)) for u, m in QUOTA_RE.findall(text)}
    if len(found) != 1:
        return None
    used, limit = found.pop()
    return (used, limit) if limit > 0 else None


def read_quota(client):
    """One GET of the logged-in account page. -> ((used, limit) | None, http status). Never raises."""
    try:
        st, _, body = client.get(client.base + ACCOUNT_PATH, accept="text/html")
    except Exception as e:                        # a stub or a broken client: the counter is unreadable
        return None, f"{type(e).__name__}"
    return (parse_quota(body) if st == 200 else None), st


# ---------------------------------------------------------------- litkb: gates 1-3 without filing

def fetch_for_litkb(client, key, doi_raw, pacer, *, known_md5=(), quota_margin=None):
    """The archive route for litkb.acquire.run: gates 1, 1b, 2, the download ladder and gate 3's byte checks.
    Nothing is written. -> dict(status, pdf, rejected, rejected_url, md5, record_doi, title_best, downloads_left,
    rec_size, via, tried, detail, http_codes, url_issued, quota). `rejected` holds the bytes a download URL served
    when they were not a PDF (with `rejected_url`, redacted): litkb.acquire.run quarantines them rather than
    dropping them (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9).
    status: downloaded | hash-mismatch (pdf kept for quarantine)
    | not-in-archive | unresolved | record-mismatch | api-error | bad-file | partner-404 | duplicate-held (the
    record's md5 is already on disk: no download is spent) | quota-stop (the account counter is unreadable, or
    used >= limit - quota_margin: no download URL was requested).
    quota_margin: litkb.acquire.run always passes one, so the account counter is read before the download request
    and again after it when a URL was issued (quota = {used_before, used_after, limit, margin}). None (the ported
    aa_fetch paths and their tests) does not consult the counter."""
    out = {"status": "", "pdf": None, "md5": "", "record_doi": "", "title_best": "", "downloads_left": "",
           "rec_size": "", "via": "scidb", "tried": [], "detail": "", "http_codes": [], "url_issued": False,
           "rejected": None, "rejected_url": ""}

    def done(status, **kw):
        out.update(kw, status=status)
        out["detail"] = redact(out["detail"])
        out["rejected_url"] = redact(out["rejected_url"])      # a partner URL, handed back beside its bytes
        return out

    doi = normalize_doi(doi_raw)
    if not doi:
        return done("unresolved", detail="no '10.' prefix in DOI; no request made")
    md5, status, detail, loc = resolve(client, doi, pacer)
    add, fud, rec_doi = {}, None, ""
    if not md5:
        if status not in SEARCH_MISS_STATES:
            return done(status or "api-error", detail=detail)
        out["via"] = "scidb-empty+search" if status == SCIDB_EMPTY else "scidb+search"
        md5, fud, add, rec_doi, sdetail = resolve_via_search(client, doi, pacer)
        if not md5:
            return done("not-in-archive", detail=f"via={out['via']}; {detail}; {sdetail}")
    if fud is None:
        fud, add, rec_doi, status, detail = verify_record(client, md5, doi, pacer)
        if fud is None:
            return done(status, md5=md5, record_doi=rec_doi, detail=f"via={out['via']}; {detail}")
    out.update(md5=md5, record_doi=rec_doi, title_best=(fud.get("title_best") or "").strip(),
               rec_size=str(fud.get("filesize_best") or ""))
    # BEGIN guard: annas known md5 spends no download
    if md5 in set(known_md5):
        return done("duplicate-held", detail=f"via={out['via']}; the archive md5 is already on disk; no download spent")
    # END guard: annas known md5 spends no download
    if quota_margin is not None:
        q, qst = read_quota(client)
        out["quota"] = {"used_before": q[0] if q else None, "used_after": None, "limit": q[1] if q else None,
                        "margin": int(quota_margin), "account_status": qst}
    # BEGIN guard: annas the account counter gates every download request
    if quota_margin is not None:
        if q is None:
            return done("quota-stop", detail=f"via={out['via']}; the account counter is unreadable (GET {ACCOUNT_PATH} "
                                             f"status {qst}); no download URL requested")
        if q[0] >= q[1] - int(quota_margin):
            return done("quota-stop", detail=f"via={out['via']}; account counter {q[0]} / {q[1]} is at or past limit - "
                                             f"margin ({q[1] - int(quota_margin)}); no download URL requested")
    # END guard: annas the account counter gates every download request
    issued, refused = [], []
    pdf, left, tried, st = download_pdf(client, key, md5, add, pacer, issued=issued, rejected=refused)
    out.update(downloads_left=left, tried=tried, url_issued=bool(issued))
    if "quota" in out:
        if issued:
            qa, _qst = read_quota(client)
            out["quota"]["used_after"] = qa[0] if qa else None
        else:
            out["quota"]["used_after"] = out["quota"]["used_before"]   # no URL issued: nothing was spent
    if pdf is None:
        reached = [t for t in tried if not t.startswith("api")]
        if not reached:
            return done("api-error", detail=f"via={out['via']}; no download_url: {', '.join(tried) or 'none tried'}")
        status = "partner-404" if all(t.endswith(":404") for t in reached) else "bad-file"
        return done(status, rejected=refused[0][1] if refused else None,
                    rejected_url=refused[0][0] if refused else "",
                    detail=f"via={out['via']}; no %PDF- from any host: {', '.join(tried)}")
    got_md5 = hashlib.md5(pdf).hexdigest()
    size_best = int(fud.get("filesize_best") or 0)
    # BEGIN guard: annas gate 3 bytes are the record's md5 and size
    if got_md5 != md5:
        return done("hash-mismatch", pdf=pdf, detail=f"bytes md5 {got_md5} != {md5}")
    if size_best and len(pdf) != size_best:
        return done("hash-mismatch", pdf=pdf, detail=f"{len(pdf)} bytes != filesize_best {size_best}")
    # END guard: annas gate 3 bytes are the record's md5 and size
    return done("downloaded", pdf=pdf, detail=f"via={out['via']}; {', '.join(tried)}")


def open_session(key_file=None, client=None):
    """Log in with the key read BY PATH (never printed). -> (client, key) or (None, None)."""
    key = open(key_file or KEY_FILE, encoding="utf-8").read().strip()
    add_secret(key)
    c = client if client is not None else Client()
    ok, _st = c.login(key)
    return (c, key) if ok else (None, None)


# ---------------------------------------------------------------- gate 3 + write (aa_fetch filing path)

def _guard_dest(dest):
    """fetch_one writes only outside the literature store, or inside its _litkb_staging."""
    d = Path(dest).resolve()
    root = LITERATURE_ROOT.resolve()
    try:
        d.relative_to(root)
    except ValueError:
        return
    # BEGIN guard: fetch_one never writes a literature topic folder
    try:
        d.relative_to((root / "_litkb_staging").resolve())
    except ValueError:
        raise DestinationRefused(f"{d} is a literature folder; litkb acquisition files only into _litkb_staging "
                                 "(py -3.12 -m litkb acquire)") from None
    # END guard: fetch_one never writes a literature topic folder


def _quarantine(path, stem, status, md5, qdir):
    os.makedirs(qdir, exist_ok=True)
    dst = os.path.join(qdir, f"{stem}__{status}__{md5 or 'nomd5'}.pdf")
    n = 2
    while os.path.exists(dst):
        dst = os.path.join(qdir, f"{stem}__{status}__{md5 or 'nomd5'}.{n}.pdf")
        n += 1
    shutil.move(path, dst)   # store-scan: allow (exists-loop above picks a free name)
    return dst


def fetch_one(client, key, doi_raw, stem, meta, paths, pacer, registry_client=None,
              registry_pacer=None):
    dest, manifest = paths["dest"], paths["manifest"]
    qdir, staging = paths["quarantine"], paths["staging"]
    _guard_dest(dest)
    doi = normalize_doi(doi_raw)
    if not doi:
        return result("unresolved", stem, doi_raw, detail="no '10.' prefix in DOI; no request made")
    # BEGIN guard: gate 0 an arxiv DOI is record-only and is never fetched
    # `10.48550/…` is a DataCite-registered identifier for a preprint that arXiv itself serves; the
    # archive is not its distributor and must never be asked for it. `resolve_doi` already returns no
    # DOI for that form, so this is the belt behind the braces: the refusal holds for ANY caller,
    # including one that reads a 10.48550 DOI out of a manifest column. No request is made.
    if (doi_raw or "").strip().lower().startswith(ARXIV_DOI_PREFIX.lower()):
        return result("unresolved", stem, (doi_raw or "").strip(),
                      detail=f"arxiv_record_only; archive_ok=False; {ARXIV_DOI_PREFIX}* is a "
                             f"record-only key served by arXiv, not the archive; no request made")
    # END guard: gate 0 an arxiv DOI is record-only and is never fetched

    md5, status, detail, loc = resolve(client, doi, pacer)
    via, add, fud, rec_doi = "scidb", {}, None, ""
    if not md5:
        if status not in SEARCH_MISS_STATES:
            return result(status, stem, doi, detail=detail, location=loc)
        via, miss_via = (("scidb-empty+search", "scidb-empty+search")
                         if status == SCIDB_EMPTY else ("search", "scidb+search"))
        md5, fud, add, rec_doi, sdetail = resolve_via_search(client, doi, pacer)
        if not md5:
            return result("not-in-archive", stem, doi, location=loc,
                          detail=f"via={miss_via}; {detail}; {sdetail}")
        detail = sdetail
    if fud is None:
        fud, add, rec_doi, status, detail = verify_record(client, md5, doi, pacer)
        if fud is None:
            return result(status, stem, doi, md5=md5, record_doi=rec_doi, location=loc,
                          detail=f"via={via}; {detail}")
    title_best = (fud.get("title_best") or "").strip()
    size_best = fud.get("filesize_best") or 0
    rec_size = str(size_best)

    final_pdf = os.path.join(dest, stem + ".pdf")
    if os.path.exists(final_pdf):
        dm = file_md5(final_pdf)
        return result("exists", stem, doi, md5=md5, record_doi=rec_doi, title_best=title_best,
                      bytes=os.path.getsize(final_pdf), disk_md5=dm, location=loc,
                      rec_size=rec_size,
                      detail=f"via={via}; " + ("on disk; disk md5 matches the record" if dm == md5
                                               else f"on disk; disk md5 DIFFERS from the record: {dm}"))

    pdf, left, tried, st = download_pdf(client, key, md5, add, pacer)
    nbytes = len(pdf or b"")
    base = dict(stem=stem, doi=doi, md5=md5, record_doi=rec_doi, downloads_left=left,
                title_best=title_best, bytes=nbytes, location=loc, rec_size=rec_size)

    if pdf is None:
        status = "bad-file" if any(not t.startswith("api") for t in tried) else "api-error"
        return result(status, **base,
                      detail=f"via={via}; no %PDF- from any host: {', '.join(tried) or 'none tried'}")

    os.makedirs(staging, exist_ok=True)
    tmp = os.path.join(staging, f"{stem}.pdf")
    with open(tmp, "xb") as fh:
        fh.write(pdf)
    got_md5 = hashlib.md5(pdf).hexdigest()
    sha = hashlib.sha256(pdf).hexdigest()
    base["sha256"] = sha

    if got_md5 != md5:
        q = _quarantine(tmp, stem, "hash-mismatch", got_md5, qdir)
        return result("hash-mismatch", **base, detail=f"bytes md5 {got_md5} != {md5}; -> {q}")
    if size_best and nbytes != int(size_best):
        q = _quarantine(tmp, stem, "hash-mismatch", got_md5, qdir)
        return result("hash-mismatch", **base,
                      detail=f"{nbytes} bytes != filesize_best {size_best}; -> {q}")
    if sha in manifest_hashes(manifest):
        q = _quarantine(tmp, stem, "duplicate-hash", got_md5, qdir)
        return result("duplicate-hash", **base, detail=f"sha256 already in manifest; -> {q}")

    txt = os.path.join(staging, f"{stem}.txt")
    try:
        subprocess.run(["pdftotext", "-layout", tmp, txt], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass
    text = ""
    if os.path.exists(txt):
        with open(txt, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    ok_content, kind, ratio, title_src = content_check(
        text[:3000], doi, title_best, make_title_getter(meta, doi, registry_client, registry_pacer))
    if not ok_content:
        q = _quarantine(tmp, stem, "content-mismatch", got_md5, qdir)
        if os.path.exists(txt):
            shutil.move(txt, q[:-4] + ".txt")   # store-scan: allow (next to a quarantine name the exists-loop chose)
        return result("content-mismatch", **base,
                      detail=f"no DOI in extract, title ratio {ratio:.2f} < {TITLE_RATIO}; "
                             f"title_src={title_src}; -> {q}")

    os.makedirs(dest, exist_ok=True)
    if os.path.exists(final_pdf):
        raise DestinationRefused(f"{final_pdf} appeared during the fetch; it is never overwritten")
    shutil.move(tmp, final_pdf)   # store-scan: allow (refused above if final_pdf exists; _guard_dest keeps dest in staging)
    if os.path.exists(txt) and not os.path.exists(os.path.join(dest, stem + ".txt")):
        shutil.move(txt, os.path.join(dest, stem + ".txt"))   # store-scan: allow (only when that .txt does not exist)
    fields = manifest_fields(manifest)
    row = {k: "" for k in fields}
    row.update({k: v for k, v in {
        "stem": stem,
        "title": title_best or meta.get("title", ""),
        "authors": meta.get("authors") or fud.get("author_best", ""),
        "year": meta.get("year") or fud.get("year_best", ""),
        "venue": meta.get("venue") or fud.get("edition_varia_best", ""),
        "doi": doi, "source_route": SOURCE_ROUTE,
        "obtained_date": datetime.date.today().isoformat(), "sha256": sha,
        "verified_against_extract": kind,
        "cited_by": meta.get("cited_by", ""),
    }.items() if k in fields})
    new = not os.path.exists(manifest)
    with open(manifest, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)
    return result("ok", **base,
                  detail=f"via={via}; verified_against_extract={kind}; title_src={title_src}; "
                         f"{', '.join(tried)}")


# ---------------------------------------------------------------- audit (read-only)

def extract_head(pdf_path, txt_path, staging, chars=3000):
    """Prefer the filed .txt; otherwise run pdftotext into staging. Never writes to DEST."""
    if txt_path and os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8", errors="replace") as fh:
            return fh.read()[:chars]
    os.makedirs(staging, exist_ok=True)
    out = os.path.join(staging, f"audit_extract_{os.getpid()}_{time.monotonic_ns()}.txt")
    try:
        subprocess.run(["pdftotext", "-layout", pdf_path, out], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return ""
    if not os.path.exists(out):
        return ""
    with open(out, encoding="utf-8", errors="replace") as fh:
        return fh.read()[:chars]


def audit_one(client, row, paths, pacer, registry_client=None, registry_pacer=None):
    """Read-only re-check of one filed stem against its record. Moves nothing."""
    stem, doi = row.get("stem", ""), normalize_doi(row.get("doi", ""))
    pdf = os.path.join(paths["dest"], stem + ".pdf")
    if not os.path.exists(pdf):
        return result("audit-missing-file", stem, doi, detail="no <stem>.pdf on disk")
    dm, size = file_md5(pdf), os.path.getsize(pdf)
    if not doi:
        return result("audit-no-doi", stem, doi, disk_md5=dm, bytes=size,
                      detail="manifest row has no DOI; nothing to resolve against")

    md5, status, detail, loc = resolve(client, doi, pacer)
    via, fud, add, rec_doi = "scidb", None, {}, ""
    if not md5 and status in SEARCH_MISS_STATES:
        via = "scidb-empty+search" if status == SCIDB_EMPTY else "search"
        md5, fud, add, rec_doi, detail = resolve_via_search(client, doi, pacer)
    if not md5:
        return result("audit-unresolvable", stem, doi, disk_md5=dm, bytes=size,
                      location=loc, detail=f"via={via}; {detail}")
    if fud is None:
        fud, add, rec_doi, status, detail = verify_record(client, md5, doi, pacer)
        if fud is None:
            return result("audit-record-" + (status or "mismatch"), stem, doi, md5=md5,
                          record_doi=rec_doi, disk_md5=dm, bytes=size, detail=f"via={via}; {detail}")

    title_best = (fud.get("title_best") or "").strip()
    size_best = int(fud.get("filesize_best") or 0)
    ok_content, kind, ratio, title_src = content_check(
        extract_head(pdf, os.path.join(paths["dest"], stem + ".txt"), paths["staging"]),
        doi, title_best, make_title_getter(row, doi, registry_client, registry_pacer))
    bad = []
    if dm != md5:
        bad.append(f"md5 {dm} != record {md5}")
    if size_best and size != size_best:
        bad.append(f"{size} bytes != filesize_best {size_best}")
    if not ok_content:
        bad.append(f"content: no DOI in extract, title ratio {ratio:.2f} < {TITLE_RATIO} "
                   f"vs {title_best[:60] or (row.get('title') or '')[:60]!r}")
    return result("audit-fail" if bad else "audit-ok", stem, doi, md5=md5, record_doi=rec_doi,
                  disk_md5=dm, bytes=size, title_best=title_best, location=loc,
                  rec_size=str(size_best),
                  detail=f"via={via}; title_src={title_src}; "
                         + ("; ".join(bad) if bad else f"verified by {kind}"))


def run_audit(client, paths, pacer, only=(), limit=0, registry_client=None, registry_pacer=None):
    rows = []
    with open(paths["manifest"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if only:
        rows = [r for r in rows if r.get("stem") in set(only)]
    if limit:
        rows = rows[:limit]
    if len(rows) > 50:
        pacer.interval = 61.0
        print(f"AUDIT pacing {len(rows)} rows at 61 s (inferred 60/hour scidb gate); "
              f"~{len(rows)} min. Use --limit or name stems for a quick pass.", flush=True)
    counts = {}
    for r in rows:
        try:
            res = audit_one(client, r, paths, pacer, registry_client, registry_pacer)
        except Exception as e:
            res = result("audit-error", r.get("stem", "?"), normalize_doi(r.get("doi", "")),
                         detail=f"{type(e).__name__}: {redact(e)}")
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        if res["status"] != "audit-ok":
            print(log_line(res), flush=True)
    print("AUDIT SUMMARY " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())), flush=True)
    return 0


# ---------------------------------------------------------------- audit-fast (read-only, tiered)

T2_INTERVAL, T2_BACKOFF = 1.0, 60.0
FAST_FIELDS = ["stem", "doi", "arxiv", "tier", "verdict", "tier1", "registered_title", "title_src",
               "title_ratio", "best_extract_line", "extract_head", "our_md5", "archive_md5",
               "archive_dois", "archive_title", "notes"]


def title_best_window(title, text):
    """-> (ratio, window) — title_similarity's 1-3-line windows, keeping the winning window."""
    import difflib

    t = _norm_text(title)
    raw = [ln.strip() for ln in (text or "").splitlines() if _norm_text(ln)]
    best, win = 0.0, ""
    for i in range(len(raw)):
        for n in (1, 2, 3):
            if i + n > len(raw):
                break
            w = " ".join(raw[i:i + n])
            r = difflib.SequenceMatcher(None, t, _norm_text(w)).ratio() if t else 0.0
            if r > best:
                best, win = r, w
    return best, " ".join(win.split())


def arxiv_id_of(row):
    a = (row.get("arxiv") or "").strip()
    d = (row.get("doi") or "").strip()
    if not a and d.lower().startswith(ARXIV_DOI_PREFIX.lower()):
        a = d[len(ARXIV_DOI_PREFIX):]
    a = re.sub(r"^(arxiv:)", "", a, flags=re.I)
    return re.sub(r"v\d+$", "", a)


def id_in_extract(text, doi, arxiv):
    """DOI (whitespace-free, url-unquoted, lowercased), a JSTOR stable URL for 10.2307/<n>, or the
    arXiv id.  Searches the WHOLE extract: publisher DOIs sit in page footers."""
    low = (text or "").lower()
    squashed = re.sub(r"\s+", "", urllib.parse.unquote(low))
    if doi:
        if doi in squashed or doi_in_extract(low, doi):
            return "doi"
    if arxiv:
        a = arxiv.lower()
        if re.search(r"(?<![\d.])" + re.escape(a) + r"(?!\d)", squashed):
            return "arxiv"
    return ""


def read_extract(dest, stem):
    """<stem>.txt, falling back to <stem>.raw.txt when the .txt is missing or has no text layer."""
    out, src = "", "none"
    for suffix in (".txt", ".raw.txt"):
        p = os.path.join(dest, stem + suffix)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            t = fh.read()
        if len(_norm_text(t[:3000])) > len(_norm_text(out[:3000])):
            out, src = t, suffix
        if len(_norm_text(out[:3000])) >= MIN_EXTRACT_CHARS:
            break
    return out, src


def arxiv_title(client, aid, pacer):
    try:
        st, body = arxiv_get(client, ARXIV_ID_LIST.format(id=urllib.parse.quote(aid, safe="")), pacer)
        if st != 200:
            return "", st
        e = ET.fromstring(body).find(ATOM_NS + "entry")
        t = " ".join(((e.findtext(ATOM_NS + "title") if e is not None else "") or "").split())
        return ("" if t.lower() == "error" else t), st
    except Exception:
        return "", 0


def registered_title(client, pacer, doi, aid):
    """-> (title, src, note).  A registry miss falls back to the manifest title, never a FAIL."""
    if doi and not doi.startswith(ARXIV_DOI_PREFIX.lower()):
        try:
            st, body = registry_get(client, CROSSREF_WORK.format(doi=urllib.parse.quote(doi, safe="/")),
                                    pacer)
        except Exception:
            st, body = 0, b""
        j = _json(body) if st == 200 else None
        msg = j.get("message") if isinstance(j, dict) else None
        titles = (msg.get("title") if isinstance(msg, dict) else None) or []
        t = next((str(x).strip() for x in titles if x and str(x).strip()), "")
        return (t, "crossref", "") if t else ("", "", f"crossref {st}")
    if aid:
        t, st = arxiv_title(client, aid, pacer)
        return (t, "arxiv", "") if t else ("", "", f"arxiv {st}")
    return "", "", "registry-none"


def tier1(row, dest, reg_client, reg_pacer):
    stem = row.get("stem", "")
    doi, aid = normalize_doi(row.get("doi", "")), arxiv_id_of(row)
    if doi.startswith(ARXIV_DOI_PREFIX.lower()):
        doi = ""
    notes = []
    if doi and doi.count("(") != doi.count(")"):
        notes.append("doi looks truncated in manifest (unbalanced paren)")
    text, xsrc = read_extract(dest, stem)
    if xsrc == ".raw.txt":
        notes.append("extract=.raw.txt")
    head = text[:3000]
    title, tsrc, tnote = registered_title(reg_client, reg_pacer, doi, aid)
    if not title:
        title, tsrc = (row.get("title") or "").strip(), "manifest"
        notes.append(f"{tnote}; title=manifest")
    ev = id_in_extract(text, doi, aid)
    ratio, win = title_best_window(title, head) if title else (0.0, "")
    head_lines = " / ".join(" ".join(ln.split()) for ln in head.splitlines()
                            if len(_norm_text(ln)) >= 12)[:200]
    if ev:
        state = "PASS"
        notes.append(f"{ev} in extract")
    elif title and ratio >= TITLE_RATIO:
        state = "PASS"
        notes.append("title match")
    elif len(_norm_text(head)) >= MIN_EXTRACT_CHARS:
        state = "FAIL-CANDIDATE"
    else:
        state = "INDETERMINATE"
    return {"stem": stem, "doi": doi, "arxiv": aid, "tier": "1", "verdict": "", "tier1": state,
            "registered_title": title, "title_src": tsrc, "title_ratio": f"{ratio:.2f}",
            "best_extract_line": win[:200] if state != "PASS" or ev == "" else "",
            "extract_head": head_lines if state == "FAIL-CANDIDATE" else "",
            "our_md5": "", "archive_md5": "", "archive_dois": "", "archive_title": "",
            "notes": notes}


def fetch_record(client, md5, pacer):
    """-> (state, dois, title_best, extension).  state: found | none | error:<status>.
    429 or a non-200 rate-limit body -> back off 60 s, HALVE the rate, retry once."""
    url = f"{client.base}/db/aarecord_elasticsearch/md5:{md5}.json"
    for attempt in (0, 1):
        pacer.wait()
        st, _, body = client.get(url, accept="application/json", timeout=60)
        if st == 429 or (st and st != 200 and RATE_RE.search(body or b"")):
            pacer.interval *= 2
            if attempt == 0:
                pacer.backoff()
                continue
            return f"error:rate-limited {st}", [], "", ""
        break
    if st == 404:
        return "none", [], "", ""
    if st != 200:
        return f"error:{st}", [], "", ""
    j = _json(body)
    if isinstance(j, list):
        j = j[0] if j else None
    fud = (j or {}).get("file_unified_data") if isinstance(j, dict) else None
    if not fud:
        return "none", [], "", ""
    dois = [str(d).strip().lower() for d in ((fud.get("identifiers_unified") or {}).get("doi") or [])]
    return "found", dois, (fud.get("title_best") or "").strip(), (fud.get("extension_best") or "")


def _arxiv_dois(aid):
    return {(ARXIV_DOI_PREFIX + aid).lower()} if aid else set()


def tier2(res, client, pacer):
    """FAIL-CANDIDATE / INDETERMINATE only: does the archive vouch for OUR exact bytes?"""
    res["tier"] = "2"
    state, dois, tb, _ = fetch_record(client, res["our_md5"], pacer)
    want = ({res["doi"]} if res["doi"] else set()) | _arxiv_dois(res["arxiv"])
    if state == "found":
        res["archive_md5"], res["archive_dois"], res["archive_title"] = res["our_md5"], ";".join(dois), tb
        if want & set(dois):
            res["verdict"] = "ok-archive"
            res["notes"].append("tier2: archive record for our md5 carries our DOI")
        elif dois:
            res["verdict"] = "misfile"
            res["notes"].append("tier2: MISFILE-EVIDENCE — our md5's record carries other DOIs")
        else:
            res["notes"].append(f"tier2: record for our md5 has no DOI (title_best={tb[:60]!r}, "
                                f"ratio {title_match_ratio(tb, res['registered_title']):.2f})")
            return "undecided"
        return "decided"
    if state != "none":
        res["notes"].append(f"tier2 {state}")
    else:
        res["notes"].append("tier2: no record for our md5")
    return "undecided"


def tier3(res, client, pacer, rec_pacer):
    res["tier"] = "3"
    t1 = res["tier1"]
    if not res["doi"]:
        res["notes"].append("tier3 skipped: no DOI (archive is never queried by arXiv DOI)")
        res["verdict"] = "misfile" if t1 == "FAIL-CANDIDATE" else "indeterminate"
        return
    md5, status, detail, _ = resolve(client, res["doi"], pacer)
    if md5:
        res["archive_md5"] = md5
        st, dois, tb, _ = fetch_record(client, md5, rec_pacer)
        if st == "found":
            res["archive_dois"], res["archive_title"] = ";".join(dois), tb
        if md5 == res["our_md5"]:
            res["notes"].append("tier3: SAME-FILE")
            res["verdict"] = "ok-archive"
        else:
            res["notes"].append("tier3: DIFFERENT-COPY")
            res["verdict"] = "misfile" if t1 == "FAIL-CANDIDATE" else "different-copy"
        return
    if status in SEARCH_MISS_STATES:
        res["notes"].append("tier3: DOI not in SciDB (search fallback not run)")
    else:
        res["notes"].append(f"tier3 {status}: {detail}")
    res["verdict"] = "misfile" if t1 == "FAIL-CANDIDATE" else "indeterminate"


def doi_truncated(doi):
    d = doi or ""
    return any(d.count(a) != d.count(b) for a, b in ("()", "[]", "<>"))


def first_surname(authors):
    return family_name(re.split(r"&|;| and ", authors or "")[0])


def repair_truncated_dois(rows, reg_client, reg_pacer):
    """Manifest DOIs cut at a parenthesis.  Repaired IN MEMORY ONLY (the manifest is never written) from
    Crossref by the manifest title; the candidate must extend the truncated prefix."""
    out = []
    for r in rows:
        old = (r.get("doi") or "").strip()
        if not old or not doi_truncated(old):
            continue
        prefix = normalize_doi(old)
        cands, err = search_crossref(reg_client, r.get("title", ""), reg_pacer)
        new, ev = "", err or "no crossref candidate"
        for c in cands:
            ok, ratio, note = judge_candidate(c, r.get("title", ""), first_surname(r.get("authors")),
                                              r.get("year"))
            cd = normalize_doi(c.get("doi"))
            if ok and cd.startswith(prefix) and not doi_truncated(cd):
                new, ev = cd, f"crossref ratio={ratio:.2f}; {note}"
                break
            ev = f"best: {cd or '-'} ratio={ratio:.2f} ({note})"
        if new:
            r["doi"] = new
        out.append((r.get("stem", ""), old, new, ev))
    return out


def _csv_row(res):
    out = {k: res.get(k, "") for k in FAST_FIELDS}
    out["notes"] = "; ".join(res.get("notes") or [])
    return {k: redact(v) for k, v in out.items()}


def run_audit_fast(paths, out_csv, reg_client, reg_pacer, get_archive, only=(), limit=0,
                   t2_pacer=None, t3_pacer=None, clock=time.monotonic):
    """get_archive() -> logged-in archive client or None; called lazily, at most once.
    Truncated manifest DOIs are repaired in memory for this audit only; the manifest is read-only."""
    t0 = clock()
    with open(paths["manifest"], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    repairs = repair_truncated_dois(rows, reg_client, reg_pacer)
    for stem, old, new, ev in repairs:
        print(redact(f"DOI-REPAIR {stem} | {old} -> {new or 'NOT REPAIRED'} | {ev}"), flush=True)
    if only:
        rows = [r for r in rows if r.get("stem") in set(only)]
    if limit:
        rows = rows[:limit]
    t2_pacer = t2_pacer or Pacer(interval=T2_INTERVAL, backoff=T2_BACKOFF)
    t3_pacer = t3_pacer or Pacer()
    results, pending = [], []
    for r in rows:
        stem = r.get("stem", "")
        try:
            res = tier1(r, paths["dest"], reg_client, reg_pacer)
            pdf = os.path.join(paths["dest"], stem + ".pdf")
            res["our_md5"] = file_md5(pdf) if os.path.exists(pdf) else ""
            if not res["doi"] and not res["arxiv"]:
                res["verdict"] = "no-identifier"
                res["notes"].insert(0, f"tier1 {res['tier1']} vs manifest title "
                                       f"(ratio {res['title_ratio']})")
            elif res["tier1"] == "PASS":
                res["verdict"] = "ok"
            elif not res["our_md5"]:
                res["verdict"] = "indeterminate"
                res["notes"].append("no <stem>.pdf on disk")
            else:
                pending.append(res)
        except Exception as e:
            res = {"stem": stem, "doi": r.get("doi", ""), "tier": "1", "verdict": "indeterminate",
                   "notes": [f"audit-error {type(e).__name__}: {e}"]}
        results.append(res)
        print(redact(f"T1 {res.get('tier1', '?'):<14} {res['verdict'] or '->tier2':<14} {stem}"),
              flush=True)
    t1_done = clock()
    client = None
    if pending:
        client = get_archive()
        if client is None:
            for res in pending:
                res["verdict"] = "indeterminate"
                res["notes"].append("archive login failed; tiers 2-3 not run")
            pending = []
    still = []
    for res in pending:
        try:
            if tier2(res, client, t2_pacer) == "undecided":
                still.append(res)
        except Exception as e:
            res["notes"].append(f"tier2 error {type(e).__name__}: {e}")
            still.append(res)
        print(redact(f"T2 {res['tier1']:<14} {res['verdict'] or '->tier3':<14} {res['stem']}"),
              flush=True)
    for res in still:
        try:
            tier3(res, client, t3_pacer, t2_pacer)
        except Exception as e:
            res["notes"].append(f"tier3 error {type(e).__name__}: {e}")
            res["verdict"] = res["verdict"] or "indeterminate"
        print(redact(f"T3 {res['tier1']:<14} {res['verdict']:<14} {res['stem']}"), flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:   # store-scan: allow (the audit CSV, outside the store)
        w = csv.DictWriter(fh, fieldnames=FAST_FIELDS)
        w.writeheader()
        for res in results:
            w.writerow(_csv_row(res))
    counts, tiers = {}, {}
    for res in results:
        counts[res["verdict"]] = counts.get(res["verdict"], 0) + 1
        tiers[res["tier"]] = tiers.get(res["tier"], 0) + 1
    el = clock() - t0
    print(redact(f"AUDIT-FAST SUMMARY rows={len(results)} elapsed={el:.0f}s (tier1 {t1_done - t0:.0f}s) "
                 f"tiers " + " ".join(f"t{k}={v}" for k, v in sorted(tiers.items())) + " verdicts "
                 + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                 + f" t2_interval={t2_pacer.interval:g}s csv={out_csv}"), flush=True)
    return results


# ---------------------------------------------------------------- cli (read-only modes)

def run_jobs(jobs, client, key, paths, pacer, registry_client=None, registry_pacer=None,
             resolve_only=False):
    """Gate 0 then gates 1-3 per job (fetch_one; its destination guard applies)."""
    for doi, stem, meta in jobs:
        if not normalize_doi(doi):
            title = meta.get("title", "")
            surname = family_name(meta.get("authors", ""))
            if not (title and surname and meta.get("year")):
                print(resolution_log_line("no-doi", stem, title, "",
                                          "best=none; need title, authors and year"), flush=True)
                continue
            if registry_client is None:
                registry_client = Client()
            rdoi, _, ev = resolve_doi(title, surname, meta.get("year"), registry_client,
                                      registry_pacer)
            if not rdoi:
                print(resolution_log_line("no-doi", stem, title, "", ev), flush=True)
                continue
            print(resolution_log_line("resolved-doi", stem, title, rdoi, ev), flush=True)
            doi, meta = rdoi, dict(meta, doi=rdoi)
        elif resolve_only:
            print(resolution_log_line("resolved-doi", stem, meta.get("title", ""),
                                      normalize_doi(doi), "via=given"), flush=True)
        if resolve_only:
            continue
        try:
            r = fetch_one(client, key, doi, stem, meta, paths, pacer, registry_client,
                          registry_pacer)
        except Exception as e:
            r = result("api-error", stem, normalize_doi(doi),
                       detail=f"{type(e).__name__}: {redact(e)}")
        print(log_line(r), flush=True)
    return 0


def _flag_values(argv, names):
    out, i = {}, 0
    while i < len(argv):
        if argv[i] in names and i + 1 < len(argv):
            out[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return out


def main_audit_fast(argv, client=None, registry_client=None, registry_pacer=None):
    """--audit-fast [--out CSV] [--limit N] [stem ...]   read-only."""
    f = _flag_values(argv, ("--out", "--limit"))
    only, i = [], 0
    while i < len(argv):
        if argv[i] in ("--out", "--limit"):
            i += 2
        else:
            only.append(argv[i])
            i += 1
    out = f.get("out") or os.path.join(tempfile.gettempdir(), "aa_fetch_audit_fast.csv")
    paths = {"dest": DEST, "manifest": os.path.join(DEST, "manifest.csv"),
             "quarantine": QUARANTINE, "staging": os.path.join(tempfile.gettempdir(), "aa_fetch_staging")}
    registry_client = registry_client if registry_client is not None else Client()
    registry_pacer = registry_pacer or Pacer(interval=REGISTRY_MIN_INTERVAL, backoff=REGISTRY_BACKOFF)

    def get_archive():
        key = open(KEY_FILE, encoding="utf-8").read().strip()
        add_secret(key)
        c = client if client is not None else Client()
        ok, st = c.login(key)
        if not ok:
            sys.stderr.write(f"login failed (status {st}); tiers 2-3 not run\n")
            return None
        return c
    run_audit_fast(paths, out, registry_client, registry_pacer, get_archive, only=only,
                   limit=int(f.get("limit") or 0))
    return 0


def main(argv, client=None, registry_client=None, registry_pacer=None, pacer=None):
    audit, limit, resolve_only = False, 0, False
    if argv and argv[0] == "--audit-fast":
        return main_audit_fast(argv[1:], client, registry_client, registry_pacer)
    if argv and argv[0] == "--audit":
        audit, argv = True, argv[1:]
        if argv and argv[0] == "--limit":
            limit, argv = int(argv[1]), argv[2:]
    elif "--resolve-only" in argv:
        resolve_only, argv = True, [a for a in argv if a != "--resolve-only"]
    jobs = []
    if audit:
        pass
    elif "--csv" in argv:
        with open(argv[argv.index("--csv") + 1], encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                jobs.append(((r.get("doi") or "").strip(), r["stem"], r))
    elif "--title" in argv:
        f = _flag_values(argv, ("--title", "--author", "--year", "--stem", "--doi"))
        jobs.append((f.get("doi", ""), f.get("stem", ""),
                     {"title": f.get("title", ""), "authors": f.get("author", ""),
                      "year": f.get("year", "")}))
    else:
        for i in range(0, len(argv) - 1, 2):
            jobs.append((argv[i], argv[i + 1], {}))

    staging = os.path.join(tempfile.gettempdir(), "aa_fetch_staging")
    paths = {"dest": DEST, "manifest": os.path.join(DEST, "manifest.csv"),
             "quarantine": QUARANTINE, "staging": staging}
    if registry_pacer is None:
        registry_pacer = Pacer(interval=REGISTRY_MIN_INTERVAL, backoff=REGISTRY_BACKOFF)
    if resolve_only:           # no key read, no login, no archive request
        return run_jobs(jobs, None, "", paths, None, registry_client, registry_pacer,
                        resolve_only=True)
    if not audit:
        sys.stderr.write("litkb.acquire.annas: job mode files papers and is refused here; "
                         "use py -3.12 -m litkb acquire (--resolve-only, --audit and --audit-fast stay)\n")
        return 2

    key = open(KEY_FILE, encoding="utf-8").read().strip()
    add_secret(key)
    client = client if client is not None else Client()
    ok, st = client.login(key)
    if not ok:
        sys.stderr.write(f"login failed (status {st}); key not accepted or site unreachable\n")
        return 1
    pacer = pacer if pacer is not None else Pacer()
    return run_audit(client, paths, pacer, only=argv, limit=limit,
                     registry_client=registry_client, registry_pacer=registry_pacer)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

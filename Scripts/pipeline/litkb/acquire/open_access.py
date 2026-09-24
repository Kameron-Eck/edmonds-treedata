"""Open-access route: arXiv by id, then every Unpaywall OA location for the DOI (design §10).

Unpaywall is asked THROUGH `litkb.netutil.Client` (S4.5 decision D3; survey-code §1.4 bypass 1): until
S4.5 the lookup went through `paper_search_mcp`'s own `requests.Session`, the one production request on
the acquisition path that litkb's single HTTP seam never saw — so a cassette could not record it and a
socket guard could only refuse it. The package is still where the account email comes from:
`paper_search_mcp` reads Kam's untracked D:\\edmonds-pipeline\\secrets\\paper_search.env through
PAPER_SEARCH_MCP_ENV_FILE (decisions.yaml litkb-p0-foundation §15.5). The email is registered for
redaction BEFORE the request that carries it, and is never stored, printed or logged by litkb: the
attempt's terminal URL for the lookup is the API URL WITHOUT its query.

-> dict(status, pdf, source_url, tried, detail, http_codes, terminal, version, kind). status: downloaded |
no-oa-copy (Unpaywall ANSWERED and lists no location, or there is no identifier) | bad-file (locations
exist and none served a PDF; when none served a byte either, the ladder types the row from its terminal
response and books an all-transport-failure answer `api-error` — S4.5 decision D15, run._type_attempt and
run._record_result, fix round 3) | blocked (a bot challenge answered) | api-error (the Unpaywall lookup did
not answer: no email, a transport failure, a 429 / 5xx, a 422 — never `no-oa-copy`, which is dead for this
route; fix round 2).

`version` is the article version Unpaywall gives the location that served the file
(submittedVersion / acceptedVersion / publishedVersion; submittedVersion for the arXiv copy) — the fact
`file_versions.copy_kind` carries (guard 23, `litkb.acquire.policy.COPY_KIND_OF_VERSION`). `terminal` is
the response that decided the attempt: its URL, HTTP status, arrival time and headers (migration 0033;
the URL is redacted where the attempt is recorded, `run.record_attempt`, and the headers are never
stored — the ladder reads Retry-After from them).

A route that refuses what it was served hands the BYTES back in `rejected` (with `rejected_url`, redacted), and
litkb.acquire.run quarantines them with a reason beside them. Nothing a location served is thrown away: that is
what makes deleting a bad download unnecessary (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9). The bytes handed
back are only ever those fetched from a URL this route believed was the FILE.
"""
import datetime
import json
import os
import urllib.parse

from litkb.acquire import accept as _accept
from litkb.acquire import backoff as _backoff
from litkb.netutil import Client, add_secret, redact

PAPER_SEARCH_ENV = r"D:\edmonds-pipeline\secrets\paper_search.env"
ARXIV_PDF = "https://arxiv.org/pdf/{id}"
#: Unpaywall's v2 record endpoint (paper_search_mcp's UnpaywallResolver.BASE_URL + "/{doi}").
UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"
#: paper_search_mcp's UnpaywallResolver._fetch_doi_record asks with timeout=20; kept.
UNPAYWALL_TIMEOUT = 20
#: the location fields kept per URL: the version (guard 23) and host type the plan's kind/version facts
#: need, plus the licence and Unpaywall's evidence string (survey-code §4.5: all discarded until S4.5).
LOCATION_FIELDS = ("version", "host_type", "license", "evidence")


def unpaywall_email():
    """The account email, read the way paper_search_mcp reads it (its own env file), or ''."""
    os.environ.setdefault("PAPER_SEARCH_MCP_ENV_FILE", PAPER_SEARCH_ENV)
    try:
        from paper_search_mcp.config import get_env
    except Exception:                           # package missing or broken: the route has no email
        return ""
    return (get_env("UNPAYWALL_EMAIL", "") or "").strip()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def unpaywall_locations(doi, client=None, email=None):
    """-> (urls, note, meta). `meta` = {"locations": {url: {version, host_type, license, evidence}},
    "terminal": {url, status_code, at}, "lookup": "answered" | "failed"} — the lookup's own response,
    which is the attempt's terminal when no location is then asked. `lookup` says whether Unpaywall
    ANSWERED about the DOI (a record, or 404 "no record") or did not (no email, a 422, a transport failure,
    a 429 / 5xx, any other code, a body that is not a JSON record): only an answer can be a miss (guard 15;
    fix round 2, auditor-C1a F1). The request goes through `client` (a `netutil.Client`)."""
    email = unpaywall_email() if email is None else email
    if not email:
        return [], "unpaywall email not configured", {"lookup": "failed"}
    # BEGIN guard: the Unpaywall email is registered for redaction before the request that carries it
    add_secret(email)
    # END guard: the Unpaywall email is registered for redaction before the request that carries it
    client = client or Client(base="")
    api = UNPAYWALL_API.format(doi=urllib.parse.quote(doi.strip(), safe="/:()"))
    st, hd, body = client.get(api + "?" + urllib.parse.urlencode({"email": email}),
                              accept="application/json", timeout=UNPAYWALL_TIMEOUT)
    terminal = {"url": api, "status_code": int(st or 0), "at": _now(), "headers": hd or {}}
    if st == 404:
        return [], "unpaywall: no record", {"terminal": terminal, "lookup": "answered"}
    if st == 422:
        return [], "unpaywall rejected the configured email (422)", {"terminal": terminal, "lookup": "failed"}
    if st != 200:
        return [], f"unpaywall answered {int(st or 0)}", {"terminal": terminal, "lookup": "failed"}
    try:
        data = json.loads((body or b"").decode("utf-8", "replace"))
    except ValueError:
        return [], "unpaywall: the record is not JSON", {"terminal": terminal, "lookup": "failed"}
    if not isinstance(data, dict):
        return [], "unpaywall: the record is not a JSON object", {"terminal": terminal, "lookup": "failed"}
    urls, locs = [], {}
    for loc in [data.get("best_oa_location") or {}] + list(data.get("oa_locations") or []):
        if isinstance(loc, dict):
            for k in ("url_for_pdf", "url"):
                if loc.get(k) and loc[k] not in urls:
                    urls.append(loc[k])
                    locs[loc[k]] = {f: loc.get(f) for f in LOCATION_FIELDS if loc.get(f) is not None}
    return (urls, f"unpaywall is_oa={bool(data.get('is_oa'))} oa_status={data.get('oa_status', '')}",
            {"locations": locs, "terminal": terminal, "lookup": "answered"})


def fetch_open_access(doi, arxiv_id, pacer, *, client=None, locations=None):
    """`locations(doi)` -> (urls, note) or (urls, note, meta); the default asks Unpaywall through `client`."""
    client = client or Client()
    if locations is None:
        def locations(d):
            return unpaywall_locations(d, client=client)
    if not arxiv_id and doi and doi.strip().lower().startswith("10.48550/arxiv."):
        # an arXiv DOI names its arXiv id (Scripts/docs/LITERATURE_CONVENTION.md, DOI-first rule 3)
        arxiv_id = doi.strip()[len("10.48550/arxiv."):]
    tried, codes, notes = [], [], []
    urls, meta, terminal = [], {}, None
    lookup = None               # "answered" | "failed" (unpaywall_locations' meta); a 2-value `locations` says neither
    if arxiv_id:
        u = ARXIV_PDF.format(id=urllib.parse.quote(arxiv_id, safe=""))
        urls.append(u)
        meta[u] = {"version": "submittedVersion", "host_type": "repository"}   # arXiv: the submitted version
    if doi:
        found, note, *rest = locations(doi)
        notes.append(note)
        more = (rest[0] if rest else None) or {}
        terminal = more.get("terminal")
        lookup = more.get("lookup")
        for u in found:
            if u not in urls:
                urls.append(u)
                meta[u] = (more.get("locations") or {}).get(u, {})
    if not urls:
        # BEGIN guard: an Unpaywall lookup that did not answer is not a miss
        # `no-oa-copy` is DEAD for this route (run.DEAD_STATUSES): booked on a lookup that never answered — a
        # transport failure, a 429 or 503, a rejected email — it retired open access for the work for ever
        # (auditor-C1a F1; guard 15: dead-ness is a per-attempt `retriable` fact). The lookup's own code is the
        # attempt's http code, so a transient one is `retriable` and gets the ladder's one scheduled retry.
        if lookup == "failed":
            code = (terminal or {}).get("status_code")
            return {"status": "api-error", "pdf": None, "source_url": "", "tried": [],
                    "http_codes": [code] if code is not None else [], "terminal": terminal,
                    "detail": redact("; ".join(n for n in notes if n))}
        # END guard: an Unpaywall lookup that did not answer is not a miss
        return {"status": "no-oa-copy", "pdf": None, "source_url": "", "tried": [], "http_codes": [],
                "terminal": terminal, "detail": redact("; ".join(n for n in notes if n) or "no identifier to look up")}
    blocked = False
    rejected, rejected_url, rejected_at = None, "", None
    answered = None
    client_error = ""
    cooled = []                 # S4.5 decision D44: locations not asked because their host is cooling
    for url in urls:
        # S4.5 decision D44 (builder-fix7): a location on a host cooling down in this run (it answered open access a
        # 429 / 503) is not asked — noted in `tried` and by the request gate on the row (`cooldown_skipped`) — and the
        # locations on the OTHER hosts are asked as before
        # BEGIN guard: a location on a cooling host is skipped and the other hosts are asked
        if _backoff.cooling_url(url) is not None:
            cooled.append(url)
            tried.append(f"{urllib.parse.urlparse(url).netloc}=cooling")
            continue
        # END guard: a location on a cooling host is skipped and the other hosts are asked
        if pacer is not None:
            pacer.wait()
        st, hd, body = client.get(url, accept="application/pdf,*/*;q=0.5", timeout=300)
        codes.append(int(st or 0))
        terminal = {"url": url, "status_code": int(st or 0), "at": _now(), "headers": hd or {}}
        host = urllib.parse.urlparse(url).netloc
        # the acceptance test's header rule (ONE home, litkb.acquire.accept.quick_magic): a PDF behind a
        # byte-order mark is a download, not a refused body (seam integrator-w1, C1a x C1b)
        if _accept.quick_magic(body):
            return {"status": "downloaded", "pdf": body, "source_url": url, "tried": tried + [f"{host}:{st}=ok"],
                    "http_codes": codes, "terminal": terminal, "kind": "pdf",
                    "version": (meta.get(url) or {}).get("version"), "location": meta.get(url) or {},
                    "detail": redact("; ".join(n for n in notes if n))}
        # BEGIN guard: a status-0 body is the client's own error text, never served bytes
        # (netutil.Client._raw_get answers a transport failure as (0, {}, "<Class>: <message>"): E13's
        # three 58-byte `annas/bad-file` payloads were exactly that string, quarantined as if served —
        # survey-data §0.5. It is noted, not kept as a payload.)
        if st == 0:
            client_error = client_error or (body or b"")[:200].decode("utf-8", "replace")
            tried.append(f"{host}:0")
            continue
        # END guard: a status-0 body is the client's own error text, never served bytes
        answered = terminal          # the last SERVER answer: a transport failure is no response (D15, below)
        if body and rejected is None:
            # the first location that served SOMETHING: Unpaywall lists best_oa_location first, so these are the
            # bytes most likely to be what the fetch was for. They are handed back, never dropped.
            rejected, rejected_url, rejected_at = body, url, terminal
        # THE one challenge detector, headers included (S4.5 decision D24: MDPI's Akamai 403 is a challenge here)
        if Client.is_challenge(st, url, body, hd):
            blocked = True
        tried.append(f"{host}:{st}")
    # BEGIN guard: locations skipped for a cooling host make a retriable answer, never a bad file
    if cooled and not codes:
        # every location was on a cooling host: nothing about the file was asked — retriable, never a bad file
        return {"status": "api-error", "retriable": True, "pdf": None, "source_url": "", "tried": tried,
                "http_codes": [], "terminal": terminal,
                "detail": redact("; ".join([n for n in notes if n] + [
                    f"{len(cooled)} location(s) not asked: their host is cooling down in this run "
                    f"(S4.5 decision D44)"]))}
    # END guard: locations skipped for a cooling host make a retriable answer, never a bad file
    return {"status": "blocked" if blocked else "bad-file", "pdf": None, "source_url": "", "tried": tried,
            # this route books `blocked` only when a challenge answered (the `blocked` sub-status it KNOWS)
            **({"sub_status": "challenge_or_bot_check"} if blocked else {}),
            "http_codes": codes, "rejected": rejected, "rejected_url": redact(rejected_url),
            # the terminal is the response whose bytes were kept (so it and served_sha256 describe one
            # answer), else the last one a SERVER answered, else the last one asked. S4.5 decision D15 types a
            # no-byte row "from the terminal response", and the client's own status 0 is not a response
            # (auditor-C1a round 3 F2; seam integrator-w2) — codes and `retriable` are the codes', unchanged
            "terminal": rejected_at or answered or terminal,
            "detail": redact("; ".join([n for n in notes if n] + [f"no %PDF- from {', '.join(tried)}"]
                                + ([f"client error: {client_error}"] if client_error else [])))}

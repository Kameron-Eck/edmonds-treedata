"""Stage E5 — the Common Crawl index: a dead URL's crawled response, fetched as ONE WARC record by byte range
(LITKB_WORKPLAN.md "### S4.5" item 6; S4.5 builder-C2c; route `commoncrawl`).

    r = fetch_commoncrawl(urls, client, pacer=..., decide=...)     # the rung dict (litkb.acquire.run.Rung)

  1. the crawl list, `COLLINFO` (survey §1 E5-RG: "index list from `collinfo.json`"), newest crawl first; read once
     per client and kept on it.
  2. for each candidate URL (`litkb.acquire.recovery`, the same dead URLs Stage E1 is asked about), the newest
     `INDEXES_ASKED` crawls' CDX API (`?url=<url>&output=json`): NDJSON, one capture per line, or 404 for none.
     A capture is taken when its archived status is 200 and its MIME (declared or detected) names a PDF.
  3. THE BYTE RANGE (survey §1 E5 / E5-RG: "bytes via S3 range GET at the WARC offset ... then WARC-decode";
     CONTRACTS X7: "Common Crawl WARC byte-range handling"): `Range: bytes=<offset>-<offset+length-1>` against
     `DATA`. The answer must be 206 and exactly `length` bytes — a 200 means the server ignored the range and a
     short body means the transfer broke; neither is decoded. The bytes are ONE gzip member holding one WARC
     `response` record (`parse_warc_record`), whose HTTP payload is de-chunked and decoded when its headers say so;
     a payload that does not decode is an `api-error`, never an exception out of the rung.
  4. A payload the crawler TRUNCATED (`WARC-Truncated`) is never offered as a whole PDF, and never decoded (a cut
     gzip or chunked stream cannot be): it comes back `bad-file` with the bytes kept as served, for THE acceptance
     test to type (survey §1 E5: "truncated WARC payload -> parse-before-bind").

THE ANSWER: a PDF -> `downloaded`; a crawled 200 that is not a PDF, or a truncated one -> `bad-file`, kept; a
transient answer -> `api-error` at once (Retry-After honoured by the ladder); a range the server did not honour,
or a record that does not decode -> `api-error`, not retriable; no capture -> `not-in-archive`/`not_in_corpus`.

A RELAYED design (CLAUDE.md §3.4c): VERIFIED in the survey as a mechanism (`karust/gogetcrawl`), never run on a
litkb row until this builder's one recorded index query; UNVALIDATED until an independent referee scores it. The
plan names no litkb row for E5: its yield is what the run measures. Stdlib only.
"""
import datetime
import gzip
import json
import urllib.parse
import zlib

from litkb.acquire import accept as _accept
from litkb.acquire import recovery as _recovery
from litkb.acquire import run as _run

ROUTE = "commoncrawl"
COLLINFO = "https://index.commoncrawl.org/collinfo.json"
DATA = "https://data.commoncrawl.org/{filename}"
#: The newest crawls asked per URL (builder-C2c's choice, UNCALIBRATED: the survey calls E5 "low yield, near-zero
#: cost"; each crawl is one index request per URL, and a dead link's live years are unknown).
INDEXES_ASKED = 3
#: At most this many captures are fetched per URL (builder-C2c's choice, UNCALIBRATED).
RECORDS_PER_URL = 1
PDF_ACCEPT = "application/pdf,*/*;q=0.5"
#: where the crawl list is kept on a client (one read per client)
_CACHE_ATTR = "_litkb_commoncrawl_indexes"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def parse_collinfo(body):
    """-> the crawls' CDX API URLs, newest first (collinfo.json lists them so), [] when unreadable."""
    try:
        data = json.loads((body or b"").decode("utf-8", "replace"))
    except ValueError:
        return []
    return [str(c["cdx-api"]) for c in (data if isinstance(data, list) else [])
            if isinstance(c, dict) and c.get("cdx-api")]


def index_url(api, url):
    return api + "?" + urllib.parse.urlencode([("url", url), ("output", "json")])


def parse_index(body):
    """-> the captures of an index answer (NDJSON), [] for none or unreadable lines."""
    out = []
    for line in (body or b"").decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("filename"):
            out.append(rec)
    return out


def is_pdf_capture(rec):
    """An archived 200 whose declared or detected MIME names a PDF."""
    mime = f"{rec.get('mime') or ''} {rec.get('mime-detected') or ''}".lower()
    return str(rec.get("status") or "") == "200" and "pdf" in mime


def byte_range(rec):
    """-> (offset, length) of a capture's WARC record, or None when the index row does not carry both."""
    try:
        off, length = int(rec["offset"]), int(rec["length"])
    except (KeyError, TypeError, ValueError):
        return None
    return (off, length) if off >= 0 and length > 0 else None


def _headers(block):
    out = {}
    for line in block.split(b"\r\n"):
        if b":" in line:
            k, v = line.split(b":", 1)
            out[k.decode("latin-1").strip().lower()] = v.decode("latin-1").strip()
    return out


def _dechunk(data):
    """An HTTP/1.1 chunked body -> its bytes. Raises ValueError when the chunks do not add up."""
    out, i = b"", 0
    while True:
        j = data.find(b"\r\n", i)
        if j < 0:
            raise ValueError("a chunk size line has no end")
        size = int(data[i:j].split(b";", 1)[0].strip() or b"0", 16)
        if size == 0:
            return out
        out += data[j + 2:j + 2 + size]
        if len(data) < j + 2 + size:
            raise ValueError("a chunk is shorter than its size line")
        i = j + 2 + size + 2


def parse_warc_record(data):
    """ONE WARC record from the bytes of a range GET -> {"warc": headers, "status": int, "headers": http headers,
    "payload": bytes, "truncated": str}. The record is a gzip member (Common Crawl stores one per record); its
    HTTP payload is de-chunked and gunzipped/inflated when its own headers say it was sent so. Raises ValueError
    for anything that is not one whole `response` record."""
    try:
        raw = gzip.decompress(data)
    except (OSError, EOFError, zlib.error) as e:
        raise ValueError(f"not a gzip member: {type(e).__name__}") from e
    head, sep, rest = raw.partition(b"\r\n\r\n")
    if not sep or not head.startswith(b"WARC/"):
        raise ValueError("no WARC header block")
    warc = _headers(head.split(b"\r\n", 1)[1] if b"\r\n" in head else b"")
    if warc.get("warc-type") != "response":
        raise ValueError(f"a {warc.get('warc-type')!r} record, not a response")
    try:
        n = int(warc.get("content-length", ""))
    except ValueError as e:
        raise ValueError("the WARC record has no Content-Length") from e
    # BEGIN guard: a WARC record shorter than its Content-Length is never decoded as whole
    if len(rest) < n:
        raise ValueError(f"the WARC block is {len(rest)} bytes of a declared {n}")
    # END guard: a WARC record shorter than its Content-Length is never decoded as whole
    block = rest[:n]
    status_head, sep, payload = block.partition(b"\r\n\r\n")
    if not sep or not status_head.startswith(b"HTTP/"):
        raise ValueError("the WARC block holds no HTTP response")
    first, _, hblock = status_head.partition(b"\r\n")
    try:
        status = int(first.split()[1])
    except (IndexError, ValueError) as e:
        raise ValueError("no HTTP status line") from e
    headers = _headers(hblock)
    truncated = warc.get("warc-truncated", "")
    # BEGIN guard: a payload the crawler truncated is kept as served, never decoded
    if truncated:
        return {"warc": warc, "status": status, "headers": headers, "payload": payload, "truncated": truncated}
    # END guard: a payload the crawler truncated is kept as served, never decoded
    enc = headers.get("content-encoding", "").lower()
    try:
        if "chunked" in headers.get("transfer-encoding", "").lower():
            payload = _dechunk(payload)
        if enc in ("gzip", "x-gzip"):
            payload = gzip.decompress(payload)
        elif enc == "deflate":
            payload = _inflate(payload)
    except (OSError, EOFError, zlib.error) as e:
        raise ValueError(f"the HTTP payload does not decode ({enc or 'identity'}): {type(e).__name__}") from e
    return {"warc": warc, "status": status, "headers": headers, "payload": payload, "truncated": truncated}


def _inflate(data):
    """`Content-Encoding: deflate`: the zlib format RFC 9110 names, else the raw DEFLATE stream some servers send
    under the same name (auditor-C2c-r2 F6 measured a raw one escaping as `zlib.error`)."""
    try:
        return zlib.decompress(data)
    except zlib.error:
        return zlib.decompress(data, -zlib.MAX_WBITS)


class _Ask:
    """One rung call's requests (the same bookkeeping as litkb.acquire.wayback's)."""

    def __init__(self, client, pacer, decide):
        self.client, self.pacer, self.decide = client, pacer, decide
        self.codes, self.tried, self.policy = [], [], []
        self.terminal = None
        self.refused = False

    def get(self, url, accept, token, headers=None):
        host = _recovery.host_of(url)
        if self.decide is not None:
            d = self.decide(host)
            detail = d.as_detail() if hasattr(d, "as_detail") else dict(d)
            if detail not in self.policy:
                self.policy.append(detail)
            # BEGIN guard: a Common Crawl request is asked only when the pre-fetch policy allows its host
            if not detail.get("allowed"):
                self.refused = True
                self.tried.append(f"{token}=policy-refused")
                return None
            # END guard: a Common Crawl request is asked only when the pre-fetch policy allows its host
        if self.pacer is not None:
            self.pacer.wait()
        st, hd, body = (self.client.get(url, accept=accept, headers=headers) if headers
                        else self.client.get(url, accept=accept))
        st = int(st or 0)
        self.codes.append(st)
        self.terminal = {"url": url, "status_code": st, "at": _now(), "headers": hd or {}}
        self.tried.append(f"{token}:{st}")
        return st, hd or {}, body or b""


def _result(ask, **kw):
    out = {"tried": ask.tried, "http_codes": ask.codes, "terminal": ask.terminal, "policy": ask.policy}
    out.update(kw)
    return out


def _transient(st):
    from litkb.acquire import backoff

    return backoff.is_transient_code(st)


def indexes(ask):
    """-> (the crawl list, None) or (None, an api-error rung dict). Read once per client (module docstring)."""
    cached = getattr(ask.client, _CACHE_ATTR, None)
    if cached:
        return cached, None
    got = ask.get(COLLINFO, "application/json", "collinfo")
    if got is None:
        return None, _result(ask, status="skipped", sub_status="policy_refused",
                             detail="the pre-fetch policy refused the Common Crawl index")
    st, _hd, body = got
    if st != 200:
        return None, _result(ask, status="api-error", retriable=_transient(st),
                             detail=f"the crawl list answered {st}")
    found = parse_collinfo(body)
    if not found:
        return None, _result(ask, status="api-error", retriable=False, detail="the crawl list names no crawl")
    try:
        setattr(ask.client, _CACHE_ATTR, found)
    except AttributeError:
        pass
    return found, None


def fetch_record(ask, rec):
    """The byte range of one capture -> ("pdf", bytes) | ("page", bytes, why) | ("error", rung dict)."""
    rng = byte_range(rec)
    if rng is None:
        return "error", _result(ask, status="api-error", retriable=False,
                                detail="the index row carries no usable offset and length")
    off, length = rng
    url = DATA.format(filename=str(rec["filename"]).lstrip("/"))
    got = ask.get(url, "*/*", f"warc {rec.get('timestamp', '')}", headers={"Range": f"bytes={off}-{off + length - 1}"})
    if got is None:
        return "error", _result(ask, status="skipped", sub_status="policy_refused",
                                detail="the pre-fetch policy refused the Common Crawl data host")
    st, _hd, body = got
    if _transient(st):
        return "error", _result(ask, status="api-error", retriable=True, detail=f"the WARC range answered {st}")
    # BEGIN guard: a Common Crawl record is read only from a 206 of exactly the indexed length
    if st != 206 or len(body) != length:
        return "error", _result(ask, status="api-error", retriable=st == 206,
                                detail=f"the WARC range answered {st} with {len(body)} of {length} bytes")
    # END guard: a Common Crawl record is read only from a 206 of exactly the indexed length
    try:
        w = parse_warc_record(body)
    except ValueError as e:
        return "error", _result(ask, status="api-error", retriable=False, detail=f"the WARC record: {e}")
    payload = w["payload"]
    # BEGIN guard: a payload the crawler truncated is never offered as a whole PDF
    if w["truncated"]:
        return "page", payload, f"the crawler truncated the payload ({w['truncated']})"
    # END guard: a payload the crawler truncated is never offered as a whole PDF
    if w["status"] == 200 and _accept.quick_magic(payload):
        return "pdf", payload
    return "page", payload, f"the crawled response was {w['status']}, not a PDF"


def fetch_commoncrawl(urls, client, *, pacer=None, decide=None, indexes_asked=None):
    """-> the rung dict for these candidate URLs (module docstring)."""
    ask = _Ask(client, pacer, decide)
    crawls, err = indexes(ask)
    if err is not None:
        return err
    n = INDEXES_ASKED if indexes_asked is None else indexes_asked
    kept, notes = None, []
    for url in urls:
        taken = 0
        for api in crawls[:n]:
            if taken >= RECORDS_PER_URL:
                break
            got = ask.get(index_url(api, url), "application/json", f"index {api.rsplit('/', 1)[-1]}")
            if got is None:
                continue
            st, _hd, body = got
            if _transient(st):
                return _result(ask, status="api-error", retriable=True, detail=f"the index answered {st}")
            if st != 200:
                continue            # 404: no capture in this crawl
            for rec in [r for r in parse_index(body) if is_pdf_capture(r)][:RECORDS_PER_URL - taken]:
                taken += 1
                out = fetch_record(ask, rec)
                if out[0] == "pdf":
                    return _result(ask, status="downloaded", pdf=out[1], kind="pdf",
                                   source_url=DATA.format(filename=str(rec["filename"]).lstrip("/")),
                                   detail=f"crawled copy of {url} at {rec.get('timestamp', '')}")
                if out[0] == "error":
                    return out[1]
                notes.append(out[2])
                if kept is None:
                    kept = (out[1], DATA.format(filename=str(rec["filename"]).lstrip("/")), dict(ask.terminal))
    if kept is not None and kept[0]:
        body, src, terminal = kept
        return _result(ask, status="bad-file", rejected=body, rejected_url=src, terminal=terminal,
                       detail="; ".join(notes))
    return _result(ask, status="not-in-archive", sub_status="not_in_corpus", retriable=False,
                   detail=f"no PDF capture in the newest {n} crawl(s)")


def _rung(work, ctx):
    urls, refused = _recovery.candidates(ctx.recovery_urls)
    if not urls:
        return _recovery.no_candidates(ROUTE, refused)
    r = fetch_commoncrawl(urls, ctx.clients.get(ROUTE) or _client(), pacer=ctx.pacer,
                          decide=lambda host: ctx.decide(ROUTE, host))
    return _recovery.with_candidates(r, urls, refused)


def _client():
    from litkb.netutil import Client

    return Client(base="")


#: builder-C1a's rung registry (S4.5 decision D19).
RUNG = _recovery.register(_run.Rung(ROUTE, _rung, needs=("doi", "arxiv"), concurrent=False, retry_transient=True))

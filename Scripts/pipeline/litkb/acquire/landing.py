"""Stage C — a landing page to the bytes (route `landing`; LITKB_WORKPLAN.md "### S4.5" item 5, the rungs).

    rung.fn(work, ctx) -> route dict      # litkb.acquire.run.Rung; this module registers `landing` at import

The single highest-yield rung the PDF-sources survey found missing (Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md
§1 Stage C, §2). A RELAYED design (CLAUDE.md §3.4c): every rule and constant below is read in another codebase by
that survey and UNVALIDATED until an independent referee scores it on the rows the plan names. Nothing here says
"validated", and nothing here is calibrated on litkb's own rows unless a comment says MEASURED.

WHAT ONE CALL DOES, in order (one attempt row; the ladder loop records it — a rung never touches the database):

  1  LEADS. Every non-PDF page an earlier rung of THIS ladder run was served (`RungContext.leads`, filled by the
     loop for every refused body: an Unpaywall OA location that answered HTML, a publisher /pdf URL that answered a
     challenge) is a lead: its URL feeds the per-publisher URL rules, and a lead page that is a real landing page
     (citation metadata, no challenge) is read for its PDF pointers. This is what makes `landing_pages_booked_bad_file`
     a statement about Stage C following THAT page, not merely running.
  2  THE DOI's LANDING PAGE. `https://doi.org/<doi>` walked hop by hop (`walk`: redirects followed by hand, so every
     URL of the chain is known; a meta refresh followed like a redirect — Zotero's C8 walk, which is exactly
     ScienceDirect's linkinghub page; guard 9: no hop to a private or loopback address). The final page is typed by
     `classify` with purpose "page": a real landing page carries citation metadata, and C6-RG's marker-free rule
     makes "200 + text/html + no citation metadata at all" an interstitial that is NEVER recorded as the landing page.
  3  CANDIDATES. The per-publisher rules of `landing_rules.json` that the DOI prefix or a seen host selects, each
     rule's candidates in the table's own order, then the default rule — the generic `citation_pdf_url` rung — as a
     fall-through (C8-RG: "run the specific rule, then FALL THROUGH to the generic citation_pdf_url rung"). The
     interpreter's techniques are five: `pointers` (C2/C2-RG), `template` and `rewrite` (URL rules), `page_regex`
     (a URL in the page), `two_hop` (C12). A page-discovered candidate passes the rule's identity check (C10) and a
     score above zero (C9); the list is de-duplicated (A10) and capped (MAX_CANDIDATES).
  4  THE 4 KB RANGE PROBE (C13) before spending: `Range: bytes=0-4095`, `Accept: application/pdf...`, the Referer
     of guard 24. Its seven-way verdict (`classify`, purpose "candidate") types a refusal into the `blocked`
     sub-statuses — identity_required · challenge_or_bot_check · not_found · html_or_reader — without downloading
     the body; only a probe that saw the PDF magic is followed by the full GET (or used whole, when the server
     ignored the Range). A candidate that failed gets the C3 rewrites, ONLY after it failed (oadoi's rule).
  5  THE ANSWER. `downloaded` with the bytes (the loop's acceptance test then judges them — this module never
     binds and never re-implements a byte rule); else `blocked` with the strongest refusal any request met
     (challenge > identity > html_or_reader > not_found: a challenge anywhere means some candidate could not be
     evaluated, the reading open_access's own route rule already takes — builder-C2b's choice, stated); a
     landing page read with no pointer and no rule candidate is `not-in-archive/no_pdf_link`, and so is a work asked
     without a DOI (an arXiv-only work) that no earlier rung was served a page for — nothing to follow; a transient answer
     (0, 408, 429, 5xx) STOPS the rung as `api-error`, retriable, with that response as the terminal one, so the
     ladder's scheduled retry honours its Retry-After (guard 2) and no further candidate is asked of a host that
     just said "slow down" (S4.5 decision D15: an all-transport attempt is never `bad-file`).

NOT BUILT here, each on purpose (named so a referee can see the boundary): the Elsevier keyed API and the embedded
`pdfDownload.urlMetadata` signed URL (landing_rules.json `elsevier.not_built`); Wiley's `/doi/epdf/` PDF.js hop;
the default rule's JS / anchor heuristics (C5, C5-RG) and LLM extraction (C25); a page-level access short-circuit
(Zotero ScienceDirect.js's detector — the Range probe types the refusal instead, so a page never stops a probe);
per-source EMA scoring (guard 6: `lastUpdated` is carried as the freshness PRIOR it names, on every attempt, and
orders nothing yet); the Atypon, Nature, eLife, APS, RSC, Project Euclid, JSTOR and PMC rows of survey §2.1 (not in
this session's publisher list; their pages still get the default rule). Every survey §2.1 rule of a publisher IN the
table that is not built is named, with why, in that rule's `not_built` list (landing_rules.json).
"""
import datetime
import html as _html
import ipaddress
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from litkb.acquire import accept as _accept
from litkb.acquire import backoff as _backoff
from litkb.acquire import ledger as _ledger
from litkb.acquire import policy as _policy

ROUTE = "landing"
RULES_PATH = Path(__file__).with_name("landing_rules.json")

#: C8 (zotero/zotero xpcom/attachments.js, VERIFIED in the survey): `redirectLimit 10`.
MAX_HOPS = 10
#: C8: `maxURLs = 6` per resolver; survey §2.1's default row: "cap the candidates tried".
MAX_CANDIDATES = 6
#: C13 (`WenyuChiou/research-hub@9877f929`, VERIFIED in the survey, 1 implementation): "Range-GET probe bytes=0-4095".
PROBE_RANGE = "bytes=0-4095"
PROBE_BYTES = 4096
#: The landing page is asked for HTML: the head probe's own landing GET (qc/instruments/litkb_acq_probe_no_oa_copy.py
#: `landing`, whose answers phase4/qc/litkb_acq_probe_no_oa_copy.csv MEASURED on this corpus) and `netutil.Client.get`'s
#: default. Not the PDF Accept: doi.org is a content-negotiating resolver, and the page is what is wanted from it.
PAGE_ACCEPT = "text/html"
#: The PDF request's Accept: survey §2.0 "Headers for every row", verbatim — the plan's "an Accept: application/pdf
#: header" with the fallbacks §2.0 gives it.
PDF_ACCEPT = "application/pdf,text/html;q=0.8,*/*;q=0.5"
#: `netutil.Client.get`'s default timeout (seconds) for a page; `open_access.fetch_open_access`'s for a PDF.
PAGE_TIMEOUT_S = 120
PDF_TIMEOUT_S = 300
#: C9's scores (survey C9, from `deathcats4/instsci-workflow@3c3bb4f4` and `Panda-of-Axin/Freepaper@4e7c51b0`):
#: -100 supplementary, -40 rightslink/citation/appendix, +50 belongs-to-article, +80/+120 the exact publisher rule.
SCORE_SUPPLEMENTARY = -100
SCORE_DEMOTE = -40
SCORE_IDENTITY = 50
#: builder-C2b's choice: every candidate starts at this, so a plain page-discovered candidate the identity check has
#: no opinion on still scores above V's `pdf_candidate_score > 0` (survey §2.0), and one supplementary token sinks it.
BASE_SCORE = 10
#: The four headers the stub detector reads (S4.5 decision D22), kept from the terminal response on every attempt.
STUB_HEADERS = ("content-type", "content-length", "x-els-status", "content-disposition")

#: The seven answers of the Range probe (C13 names "a seven-way response classifier"; its code was not re-read here,
#: so the seven are THIS module's: the four `blocked` sub-statuses of the S4.5 vocabulary, plus a PDF, a transient
#: answer, and anything else).
VERDICTS = ("pdf", "challenge_or_bot_check", "identity_required", "not_found", "html_or_reader", "transient",
            "unexpected")
#: The order in which the refusals of one call decide its sub-status (module docstring, step 5).
REFUSAL_ORDER = ("challenge_or_bot_check", "identity_required", "html_or_reader", "not_found")

_REDIRECTS = (301, 302, 303, 307, 308)
_META_REFRESH = re.compile(rb"<meta\b(?=[^>]*http-equiv\s*=\s*[\"']?refresh)[^>]*content\s*=\s*[\"']?\s*\d*\s*;?\s*"
                           rb"url\s*=\s*['\"]?(?P<u>[^'\">\s]+)", re.I)
_ATTR = re.compile(rb"""([a-zA-Z_:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")
_TAGS = {t: re.compile(rb"<%s\b[^>]*>" % t, re.I) for t in (b"meta", b"link", b"iframe", b"embed", b"object", b"base")}
_PDFJS = re.compile(rb"""defaultUrl\s*[:=]\s*["']([^"']+)["']""")
_DATA_PDF = re.compile(rb"""data-pdf-url\s*=\s*["']([^"']+)["']""", re.I)
_JSONLD_ARTICLE = re.compile(rb""""@type"\s*:\s*"ScholarlyArticle\"""")
#: the meta namespaces Zotero's Embedded Metadata reads (survey C2: citation_, bepress_, eprints., wkhealth_; the
#: Dublin Core and PRISM families it also maps) — "citation metadata" for C6-RG's marker-free rule
_CITATION_META_PREFIXES = ("citation_", "dc.", "dcterms.", "prism.", "eprints.", "bepress_citation_", "wkhealth_")
#: query parameters that UNWRAP to the real file (survey §2.1 default step 4)
_UNWRAP_PARAMS = ("file", "pdf", "src", "url")
#: signed-URL parameters: a URL carrying one is kept in the ledger without its query (the acceptance test's own rule
#: for a terminal URL, `accept._strip_query`: E20's preview URL carried an AWS session token)
_SIGNED = re.compile(r"(?i)[?&](?:x-amz-[a-z-]+|signature|expires|policy|key-pair-id|token)=")


# ── the rule table (data; this module is its interpreter) ──────────────────────────────────────
def load_rules(path=RULES_PATH):
    """-> the rule table as a dict, with `problems` (check_rules) raising: a table the interpreter cannot read
    is refused whole rather than half-applied."""
    table = json.loads(Path(path).read_text(encoding="utf-8"))
    bad = check_rules(table)
    if bad:
        raise ValueError(f"{path}: the landing rule table is malformed: {'; '.join(bad[:5])}")
    return table


_TECHNIQUES = ("pointers", "template", "rewrite", "page_regex", "two_hop")
_CHECKS = ("doi_in_url", "same_id", "require_substring")


def check_rules(table):
    """-> a list of problems (empty = the table is well formed). Every rule carries its source and its freshness
    prior (guard 25: `lastUpdated`, or an explicit null with a note), a challenge signature OR a note saying none
    was characterised, and an example (a recorded fixture, or why none)."""
    out = []
    if table.get("kind") != "litkb-landing-rules":
        out.append("kind is not litkb-landing-rules")
    ids = set()
    g = table.get("global") or {}
    for k in ("id_patterns", "login_wall_url_markers", "rewrites", "supplementary_tokens", "demote_tokens"):
        if k not in g:
            out.append(f"global.{k} missing")
    for rx in list((g.get("id_patterns") or {}).values()) + [r.get("match", "") for r in g.get("rewrites") or []]:
        try:
            re.compile(rx)
        except re.error as e:
            out.append(f"global regex {rx!r}: {e}")
    for rule in list(table.get("rules") or []) + [table.get("default") or {}]:
        rid = rule.get("id")
        if not rid or rid in ids:
            out.append(f"rule id {rid!r} missing or repeated")
        ids.add(rid)
        src = rule.get("source") or {}
        if "lastUpdated" not in src or not src.get("translator") or not src.get("survey"):
            out.append(f"{rid}: source needs translator, lastUpdated (null allowed) and survey")
        if src.get("lastUpdated") is None and not src.get("note"):
            out.append(f"{rid}: a null lastUpdated needs a note")
        if rule.get("challenge_signature") is None and not rule.get("challenge_note"):
            out.append(f"{rid}: no challenge signature and no challenge_note saying why")
        ex = rule.get("example")
        if not isinstance(ex, dict) or ("fixture" not in ex) or not ex.get("why"):
            out.append(f"{rid}: example needs fixture (or null) and why")
        for c in rule.get("identity") or []:
            if c.get("check") not in _CHECKS:
                out.append(f"{rid}: unknown identity check {c.get('check')!r}")
            if c.get("check") == "same_id" and c.get("id") not in (g.get("id_patterns") or {}):
                out.append(f"{rid}: same_id names an unknown id {c.get('id')!r}")
        if not rule.get("candidates"):
            out.append(f"{rid}: no candidates")
        for c in rule.get("candidates") or []:
            if c.get("technique") not in _TECHNIQUES:
                out.append(f"{rid}.{c.get('name')}: unknown technique {c.get('technique')!r}")
            if not c.get("why"):
                out.append(f"{rid}.{c.get('name')}: no why (its source)")
            for key in ("match",):
                if c.get(key):
                    try:
                        re.compile(c[key])
                    except re.error as e:
                        out.append(f"{rid}.{c.get('name')}: {key} {e}")
            for rx in c.get("then") or []:
                try:
                    re.compile(rx)
                except re.error as e:
                    out.append(f"{rid}.{c.get('name')}: then {e}")
            if c.get("technique") in ("template", "two_hop") and not c.get("template"):
                out.append(f"{rid}.{c.get('name')}: a template technique with no template")
            if c.get("technique") == "rewrite" and ("replace" not in c or not c.get("match")):
                out.append(f"{rid}.{c.get('name')}: a rewrite needs match and replace")
    return out


TABLE = load_rules()


# ── small pure helpers ─────────────────────────────────────────────────────────────────────────
def header(headers, name):
    """A header value, case-insensitively (a server sends `content-type` or `Content-Type`). -> str or None."""
    for k, v in (headers or {}).items():
        if str(k).lower() == name.lower():
            return str(v)
    return None


def host_of(url):
    return (urllib.parse.urlsplit(url or "").hostname or "").lower()


def public_url(url):
    """(ok, why) — guard 9 (survey §1, round 1): "refuse private / loopback / link-local addresses on EVERY redirect
    hop — candidate URLs come from external indexes". http(s) only; a literal address must be public; a name that
    only resolves on this machine (localhost, *.local, *.internal) is refused. A name that RESOLVES to a private
    address is not caught here (no lookup is made to check it) — a stated limit."""
    parts = urllib.parse.urlsplit(url or "")
    if parts.scheme not in ("http", "https"):
        return False, f"scheme {parts.scheme or 'none'!r} is not http(s)"
    host = (parts.hostname or "").lower()
    if not host:
        return False, "no host"
    # BEGIN guard: no request to a private, loopback or link-local address, on every hop
    if host in ("localhost", "localhost.localdomain", "ip6-localhost") or host.endswith((".localhost", ".local",
                                                                                         ".internal")):
        return False, f"{host} names this machine or a private network"
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
                           or ip.is_unspecified):
        return False, f"{host} is not a public address"
    # END guard: no request to a private, loopback or link-local address, on every hop
    return True, ""


def shadow_host(url, policy=None):
    """True when a SHADOW-tier line of the pre-fetch policy names this URL's host (litkb.acquire.policy.POLICY):
    Stage C is a legitimate rung, and a landing page that links a shadow front must never make it ask one
    (`litkb-shadow-hosts`: the tier runs only after every legitimate rung missed, behind its own switch)."""
    host = host_of(url)
    # BEGIN guard: the legitimate landing rung never asks a shadow host
    if any(p.tier == _policy.SHADOW and p.host.lower() == host for p in (policy or _policy.POLICY)):
        return True
    # END guard: the legitimate landing rung never asks a shadow host
    return False


def evidence_url(url):
    """The URL as the ledger keeps it: a SIGNED URL loses its query (`accept._strip_query`'s reason)."""
    return _accept._strip_query(url) if url and _SIGNED.search(url) else (url or "")


def referer_for(page_url, candidate):
    """Guard 24 (Zotero attachments.js + the connector's itemSaver.js, VERIFIED in the survey): the LANDING PAGE if
    the candidate is same-origin, else the page's ORIGIN — never a search engine. -> the header value or None."""
    if not page_url:
        return None
    p, c = urllib.parse.urlsplit(page_url), urllib.parse.urlsplit(candidate or "")
    if not p.scheme or not p.netloc:
        return None
    ref = page_url                     # the unguarded default: the whole page URL, whatever the candidate's origin
    # BEGIN guard: the Referer is the landing page if same-origin, else its origin, never a search engine
    if (p.scheme.lower(), p.netloc.lower()) != (c.scheme.lower(), c.netloc.lower()):
        ref = f"{p.scheme}://{p.netloc}/"
    if re.search(r"(?i)(^|\.)(google|bing|duckduckgo|yahoo|baidu|yandex)\.", host_of(ref) + "."):
        return None
    # END guard: the Referer is the landing page if same-origin, else its origin, never a search engine
    return ref


def _attrs(tag):
    out = {}
    for m in _ATTR.finditer(tag):
        v = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
        out[m.group(1).decode("latin-1").lower()] = _html.unescape((v or b"").decode("utf-8", "replace")).strip()
    return out


def meta_items(body):
    """[(key, content)] for every <meta> with a name / property / itemprop (C2-RG: `@name` AND `@property`), found
    anywhere in the document (C2-RG: `<body>` as well as `<head>`). Keys lower-cased; content entity-decoded."""
    out = []
    for tag in _TAGS[b"meta"].findall(body or b""):
        a = _attrs(tag)
        key = (a.get("name") or a.get("property") or a.get("itemprop") or "").lower()
        if key and a.get("content"):
            out.append((key, a["content"]))
    return out


def meta_value(body, key):
    return next((v for k, v in meta_items(body) if k == key.lower()), None)


def has_citation_metadata(body):
    """C6-RG's test: does the page carry ANY citation metadata (the Embedded Metadata namespaces, a DOI meta, a
    PDF alternate link, or a JSON-LD ScholarlyArticle)? A challenge interstitial carries none."""
    for key, _v in meta_items(body):
        if key.startswith(_CITATION_META_PREFIXES) or key == "doi":
            return True
    for tag in _TAGS[b"link"].findall(body or b""):
        a = _attrs(tag)
        if "alternate" in a.get("rel", "").lower() and a.get("type", "").lower() == "application/pdf":
            return True
    return bool(_JSONLD_ARTICLE.search(body or b""))


def base_of(body, page_url):
    """The document base: a <base href> when the page declares one, else the page's own URL."""
    for tag in _TAGS[b"base"].findall(body or b""):
        href = _attrs(tag).get("href")
        if href:
            return urllib.parse.urljoin(page_url, href)
    return page_url


def resolve(base, href):
    """[absolute URL, ...] for a pointer found in a page (C2-RG: "the PDF URL is never resolved against the document
    base ... a Python port must urljoin it itself"). An absolute or root-relative pointer resolves once. A
    path-relative pointer against a base whose last segment has no dot and no trailing slash resolves TWICE: the
    browser's reading first, then C2-RG's "append `/` to a base with no trailing slash" (the PMC case) — the survey
    states the second as a rule, and a page URL like `/article/view/123` is exactly where it is wrong, so both are
    kept and the probe decides. -> [] for javascript:, data:, mailto: and fragments."""
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:", "data:", "mailto:")):
        return []
    parts = urllib.parse.urlsplit(href)
    if parts.scheme in ("http", "https"):
        return [href]
    if parts.scheme:
        return []
    first = urllib.parse.urljoin(base, href)
    if href.startswith("/"):
        return [first]
    b = urllib.parse.urlsplit(base)
    last = b.path.rsplit("/", 1)[-1]
    if b.path and not b.path.endswith("/") and "." not in last:
        second = urllib.parse.urljoin(urllib.parse.urlunsplit((b.scheme, b.netloc, b.path + "/", "", "")), href)
        return [first] if second == first else [first, second]
    return [first]


def pointers(body, page_url):
    """The generic C2 rung on one page: [(url, source)] in the order found, de-duplicated (survey §2.1 default
    steps 1-4 and step 5's data-pdf-url):
      1  every meta key ending `pdf_url` on name / property / itemprop — `citation_pdf_url` and its `bepress_` and
         `eprints.` variants by SUFFIX, `wkhealth_pdf_url`, `fulltext_pdf_url` — plus `og:pdf` and
         `eprints.document_url`;
      2  <link rel=alternate type=application/pdf>, and <iframe>/<embed>/<object> naming a PDF by type or path;
      3  a PDF.js viewer's `defaultUrl`;
      4  a query parameter (file= / pdf= / src= / url=) that unwraps to the file, for every URL above."""
    base = base_of(body, page_url)
    found = []
    for key, content in meta_items(body):
        if key.endswith("pdf_url") or key in ("og:pdf", "eprints.document_url"):
            found += [(u, f"meta:{key}") for u in resolve(base, content)]
    for tag in _TAGS[b"link"].findall(body or b""):
        a = _attrs(tag)
        if "alternate" in a.get("rel", "").lower() and a.get("type", "").lower() == "application/pdf":
            found += [(u, "link:alternate") for u in resolve(base, a.get("href"))]
    for name in (b"iframe", b"embed", b"object"):
        for tag in _TAGS[name].findall(body or b""):
            a = _attrs(tag)
            src = a.get("src") or a.get("data") or ""
            if a.get("type", "").lower() == "application/pdf" or urllib.parse.urlsplit(src).path.lower().endswith(".pdf"):
                found += [(u, f"{name.decode()}:src") for u in resolve(base, src)]
    for m in _PDFJS.finditer(body or b""):
        found += [(u, "pdfjs:defaultUrl") for u in resolve(base, _html.unescape(m.group(1).decode("utf-8", "replace")))]
    for m in _DATA_PDF.finditer(body or b""):
        found += [(u, "data-pdf-url") for u in resolve(base, _html.unescape(m.group(1).decode("utf-8", "replace")))]
    unwrapped = []
    for u, src in found:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)
        for p in _UNWRAP_PARAMS:
            for v in q.get(p, []):
                unwrapped += [(w, f"{src}+unwrap:{p}") for w in resolve(u, v)]
    out, seen = [], set()
    for u, src in found + unwrapped:
        if u not in seen:
            seen.add(u)
            out.append((u, src))
    return out


def _lower_unquoted(s):
    return urllib.parse.unquote(s or "").lower()


def ids_in(url, table=None):
    """{id name: value} for every `global.id_patterns` id the URL carries (upper-cased PII, digits for arnumber)."""
    table = table or TABLE
    out = {}
    for name, rx in (table["global"].get("id_patterns") or {}).items():
        m = re.search(rx, urllib.parse.unquote(url or ""), re.I)
        if m:
            out[name] = m.group("v").upper()
    return out


# ── the classifier (the Range probe's seven answers, and the landing page's) ───────────────────
def _pdfish(head):
    """Would the acceptance test even look at these bytes as a PDF (its repair + magic, or a wrapper it unwraps)?"""
    return _accept.quick_magic(head) or _accept.sniff(head) in ("gzip", "tar")


def _looks_like_html(data):
    # ONE home for "do these bytes open as HTML" (litkb.extract.text_snapshot; `acquire` must not import `extract`
    # at module scope - the reason litkb.acquire.accept imports it the same way)
    from litkb.extract.text_snapshot import looks_like_html

    return looks_like_html(data)


def _is_html(headers, body):
    ctype = (header(headers, "content-type") or "").lower()
    return "html" in ctype or _looks_like_html(body or b"")


def _challenge(status, headers, body, url, rules, table, urls=()):
    """-> the challenge family these bytes / headers / URLs carry, or '' (guard 3 + C6 + C6-RG + C7, and each
    selected rule's own signature; the page shapes MEASURED in litkb's own kept bytes are litkb.acquire.ledger's).
    `urls` is every URL of the request's redirect chain, the final answer's Location included."""
    from litkb.netutil import Client

    # BEGIN guard: a challenge or bot check is typed challenge_or_bot_check, never a refusal about the article
    for u in list(urls) + [url]:
        low = _lower_unquoted(u)
        for m in table["global"].get("challenge_url_markers") or []:
            if m in low:
                return f"challenge-url:{m}"
    if Client.is_challenge(status, url, body):
        return "netutil.CHALLENGE_RE"
    cause = _ledger.challenge_cause(body, headers)
    if cause:
        return cause
    if int(status or 0) in (table["global"].get("waf_statuses") or []):
        return f"waf-{int(status)}"
    low = _lower_unquoted(url)
    for m in table["global"].get("cookie_wall_url_markers") or []:
        if m in low:
            return f"cookie-wall:{m}"
    # a rule's own signature is searched in the WHOLE body: it is specific to the rule's hosts, and the one the
    # survey gives for ScienceDirect ("There was a problem providing the content you requested") sits ~770 KB into
    # its 832 KB error page (MEASURED 2026-09-23, qc/fixtures/litkb_landing_pages/elsevier/hop3.body; builder-C1a
    # found the same on Li_2022's kept page), far past guard 3's 64 KB window for the generic markers
    whole = (body or b"").lower()
    host = host_of(url)
    for rule in rules:
        sig = rule.get("challenge_signature") or {}
        if not _claims_host(rule, host):
            continue
        for marker in sig.get("markers") or []:
            if marker.encode("utf-8") in whole:
                return f"{rule['id']}:{marker}"
    # END guard: a challenge or bot check is typed challenge_or_bot_check, never a refusal about the article
    return ""


def _login_marker(urls, table):
    for u in urls:
        low = _lower_unquoted(u)
        for m in table["global"].get("login_wall_url_markers") or []:
            if m in low:
                return m
    return ""


def classify(status, headers, body, url, *, rules=(), purpose="candidate", chain=(), table=None):
    """-> (verdict, why). `purpose` is "page" for the landing page (verdict `landing` for a real one) or
    "candidate" for a PDF candidate's Range probe; `chain` is every URL of the request's redirect walk.

      transient            HTTP 0 / 408 / 429 / 5xx (litkb.acquire.backoff's transient codes)
      pdf                  2xx and the PDF magic (or a gzip / tar wrapper the acceptance test unwraps)
      landing              (page) 2xx HTML carrying citation metadata — a real landing page, whatever its scripts say
      html_or_reader       (candidate) a 2xx page with citation metadata, or plain HTML with no paywall marker
      challenge_or_bot_check  a challenge signature (headers, markers, WAF status, cookie wall), or (page) C6-RG's
                           marker-free rule: 2xx + HTML + no citation metadata at all
      identity_required    401, a login-wall URL anywhere on the chain, a 403 with no challenge signature
                           (litkb.acquire.ledger.type_blocked's rule), or (candidate) a paywall marker in an HTML answer
      not_found            404 / 410
      unexpected           anything else (a 400, a 406, a binary that is not a PDF, a redirect with no Location)"""
    table = table or TABLE
    st = int(status or 0)
    body = body or b""
    loc = header(headers, "Location") if st in _REDIRECTS else None
    chain = list(chain) + ([urllib.parse.urljoin(url, loc.strip())] if loc else [])
    # BEGIN guard: a transient answer is never typed as a refusal about the article
    if _backoff.is_transient_code(st):
        return "transient", f"HTTP {st}"
    # END guard: a transient answer is never typed as a refusal about the article
    if 200 <= st < 300 and _pdfish(body[:_ledger.MARKER_WINDOW]):
        return "pdf", "the PDF magic"
    html = _is_html(headers, body)
    real_page = 200 <= st < 300 and html and has_citation_metadata(body)
    shield = False
    # BEGIN guard: a real landing page is never typed a challenge by a marker in its own scripts
    # (survey G0d via C1a's netutil.Client.is_challenge docstring: a solved page mentions its guard in its scripts)
    shield = real_page
    # END guard: a real landing page is never typed a challenge by a marker in its own scripts
    # a login wall on the chain is the server's own statement about the article; it is read before the body markers,
    # because a login page commonly carries a captcha widget that the marker list would call a challenge
    login = "" if shield else _login_marker(chain + [url], table)
    # BEGIN guard: a login wall on the redirect chain is typed identity_required
    if login:
        return "identity_required", f"a login wall on the redirect chain ({login})"
    # END guard: a login wall on the redirect chain is typed identity_required
    cause = "" if shield else _challenge(st, headers, body, url, rules, table, urls=chain)
    if cause:
        return "challenge_or_bot_check", cause
    if st == 401:
        return "identity_required", "HTTP 401 (a subscription answer about one article, guard 2)"
    if st in (404, 410):
        return "not_found", f"HTTP {st}"
    if st == 403:
        return "identity_required", "HTTP 403 with no challenge signature (litkb.acquire.ledger.type_blocked rule 4)"
    if 200 <= st < 300 and html:
        if purpose == "page" and real_page:
            return "landing", "a page with citation metadata"
        # BEGIN guard: an HTML page with no citation metadata is an interstitial, never recorded as the landing page
        if purpose == "page":
            return "challenge_or_bot_check", "C6-RG: 200 + text/html + no citation metadata at all = an interstitial"
        # END guard: an HTML page with no citation metadata is an interstitial, never recorded as the landing page
        head = body[:_ledger.MARKER_WINDOW].lower()
        # BEGIN guard: a paywall marker in an HTML answer to a PDF candidate is typed identity_required
        for m in (table["global"].get("paywall_body_markers") or []) if not real_page else []:
            if m.encode("utf-8") in head:
                return "identity_required", f"a paywall marker in the HTML answer ({m!r})"
        # END guard: a paywall marker in an HTML answer to a PDF candidate is typed identity_required
        return "html_or_reader", "an HTML page where the file was asked for"
    return "unexpected", f"HTTP {st} {header(headers, 'content-type') or 'no content-type'}"


# ── the network (every request goes through the injected netutil.Client: the cassette sees it) ─────────
@dataclass
class Hop:
    url: str
    status: int
    headers: dict
    body: bytes
    refused: str = ""


def walk(client, url, *, accept, headers=None, timeout=PAGE_TIMEOUT_S, pacer=None, meta_refresh=True,
         max_hops=MAX_HOPS):
    """GET `url` and follow its redirects BY HAND (so every URL of the chain is known; a meta refresh is followed
    like a redirect — C8's walk). Guard 9 on every hop. -> [Hop, ...]; the last one decided."""
    hops, seen, cur = [], set(), url
    for _ in range(max_hops + 1):
        ok, why = public_url(cur)
        if not ok:
            hops.append(Hop(cur, 0, {}, b"", refused=why))
            break
        seen.add(cur)
        if pacer is not None:
            pacer.wait()
        st, hd, body = client.get(cur, accept=accept, timeout=timeout, follow=False, headers=dict(headers or {}))
        hops.append(Hop(cur, int(st or 0), hd or {}, body or b""))
        nxt = None
        if int(st or 0) in _REDIRECTS:
            loc = header(hd, "Location")
            nxt = urllib.parse.urljoin(cur, loc.strip()) if loc else None
            # BEGIN guard: a redirect into a bot check is never followed
            # (it is the answer, typed by `classify` from this hop's Location; MEASURED on IOP: the client cannot even
            # open Radware's URL - it carries spaces - so following it books a transport failure, not the challenge)
            if nxt and any(m in _lower_unquoted(nxt) for m in TABLE["global"].get("challenge_url_markers") or []):
                break
            # END guard: a redirect into a bot check is never followed
        elif meta_refresh and 200 <= int(st or 0) < 300 and _is_html(hd, body) and not has_citation_metadata(body):
            m = _META_REFRESH.search((body or b"")[:_ledger.MARKER_WINDOW])
            if m:
                nxt = urllib.parse.urljoin(cur, _html.unescape(m.group("u").decode("utf-8", "replace")))
        if not nxt or nxt in seen:
            break
        cur = nxt
    return hops


# ── the interpreter ────────────────────────────────────────────────────────────────────────────
@dataclass
class Page:
    """One HTML page this call read (or tried to): the DOI's landing page or a lead."""
    url: str
    status: int
    headers: dict
    body: bytes
    origin: str                              # "doi" | "lead:<route>"
    verdict: str = ""
    why: str = ""
    chain: list = field(default_factory=list)

    @property
    def readable(self):
        return self.verdict in ("landing", "html_or_reader") and bool(self.body)


@dataclass
class Candidate:
    url: str
    source: str                              # "<rule id>.<candidate name>[:<pointer source>]"
    rule: str
    score: int = BASE_SCORE
    version: str = None
    referer: str = None
    two_hop: list = None                     # the page regexes of a two_hop candidate
    verdict: str = ""
    why: str = ""
    status: int = None
    requests: int = 0
    rewritten: bool = False                  # a C3 rewrite of a failed candidate (never rewritten again)


def _claims_host(rule, host):
    d = rule.get("detect") or {}
    return bool(host) and (host in (d.get("hosts") or []) or any(host.endswith(s) for s in d.get("hosts_suffix") or []))


def rules_for(doi, urls, table=None):
    """The specific rules the DOI prefix or a seen host selects (DOI-prefix matches first, then hosts in the order
    seen), then the default rule — C8-RG's fall-through."""
    table = table or TABLE
    chosen = []
    low = (doi or "").lower()
    for rule in table["rules"]:
        if any(low.startswith(p) for p in (rule.get("detect") or {}).get("doi_prefixes") or []):
            chosen.append(rule)
    for u in urls:
        h = host_of(u)
        for rule in table["rules"]:
            if rule not in chosen and _claims_host(rule, h):
                chosen.append(rule)
    return chosen + [table["default"]]


def _transform(v, how):
    if v is None:
        return None
    v = str(v).strip()
    if how == "despace_lower":
        return re.sub(r"[^A-Za-z0-9]", "", v).lower() or None
    if how == "lower":
        return v.lower()
    if how == "upper":
        return v.upper()
    return v


def var_values(rule, work, pages, urls, table=None):
    """{var name: [distinct values in order]} from the rule's `vars` (sources: meta:<key> of any readable page,
    work:<field> of the work record, url:<id> from `global.id_patterns` over every URL seen, doi:<regex>)."""
    table = table or TABLE
    out = {}
    for spec in rule.get("vars") or []:
        vals = out.setdefault(spec["name"], [])
        for src in spec.get("from") or []:
            kind, _, arg = src.partition(":")
            got = []
            if kind == "meta":
                got = [meta_value(p.body, arg) for p in pages if p.readable]
            elif kind == "work":
                got = [(work or {}).get(arg)]
            elif kind == "url":
                got = [ids_in(u, table).get(arg) for u in urls]
            elif kind == "doi":
                m = re.search(arg, (work or {}).get("doi") or "", re.I)
                got = [m.group("v")] if m else []
            for v in got:
                v = _transform(v, spec.get("transform"))
                if v and v not in vals:
                    vals.append(v)
    return out


def _expand(template, fields, variables):
    """Every URL the template makes from `fields` (regex groups + the work's DOI forms) crossed with each
    variable's values; a template naming a field nothing supplies makes none (never a KeyError)."""
    names = set(re.findall(r"{(\w+)(?:[:!][^}]*)?}", template))
    combos = [dict(fields)]
    for n in sorted(names):
        if n in fields:
            continue
        vals = variables.get(n) or []
        if not vals:
            return []
        combos = [dict(c, **{n: v}) for c in combos for v in vals]
    out = []
    for c in combos:
        try:
            u = template.format(**c)
        except (KeyError, ValueError, IndexError):
            continue
        if u not in out:
            out.append(u)
    return out


def _doi_fields(doi):
    doi = doi or ""
    return {"doi": doi, "doi_suffix": doi.split("/", 1)[1] if "/" in doi else ""}


def _identity_ok(rule, url, context_urls, doi, table):
    """C10: does a page-discovered candidate belong to THIS article? -> (ok, why)."""
    low = _lower_unquoted(url)
    # BEGIN guard: a page-discovered candidate must belong to this article
    for bad in rule.get("exclude") or []:
        if bad.lower() in low:
            return False, f"excluded token {bad!r} (the rule's supplementary / wrong-object list)"
    if host_of(url) in [h.lower() for h in rule.get("exclude_hosts") or []]:
        return False, f"host {host_of(url)} is a sibling family's (survey §2.1 cross-family rejection)"
    for check in rule.get("identity") or []:
        kind = check.get("check")
        if kind == "doi_in_url":
            d = (doi or "").lower()
            if d and d not in low and (d.split("/", 1)[-1] not in low):
                return False, "the DOI is not in the candidate's URL"
        elif kind == "same_id":
            want = [ids_in(u, table).get(check["id"]) for u in context_urls]
            want = {w for w in want if w}
            got = ids_in(url, table).get(check["id"])
            if got and want and got not in want:
                return False, f"its {check['id']} {got} is not the article's ({', '.join(sorted(want))})"
        elif kind == "require_substring":
            if check["value"].lower() not in low:
                return False, f"{check['value']!r} is not in the candidate's URL"
    # END guard: a page-discovered candidate must belong to this article
    return True, ""


def score(url, table=None, *, bonus=0, affirmed=False):
    """C9's pdf_candidate_score for one candidate URL."""
    table = table or TABLE
    low = _lower_unquoted(url)
    s = BASE_SCORE + int(bonus or 0) + (SCORE_IDENTITY if affirmed else 0)
    if any(t in low for t in table["global"].get("supplementary_tokens") or []):
        s += SCORE_SUPPLEMENTARY
    if any(t in low for t in table["global"].get("demote_tokens") or []):
        s += SCORE_DEMOTE
    return s


def candidates_for(work, pages, urls, *, resolved=None, table=None, rules=None):
    """-> ([Candidate, ...], [rule ids]) for a work, the pages read and every URL seen: each selected rule's
    candidates in the table's order, the default rule's pointers last; identity-checked (page-discovered ones),
    scored above zero, de-duplicated, capped at MAX_CANDIDATES. Pure: no request is made here."""
    table = table or TABLE
    doi = (work or {}).get("doi")
    rules = rules if rules is not None else rules_for(doi, urls, table)
    readable = [p for p in pages if p.readable]
    context = list(urls)
    landing = _landing_url(pages, resolved)
    out, keys = [], set()

    def add(c):
        k = _dedupe_key(c.url)
        if k in keys or not public_url(c.url)[0] or shadow_host(c.url):
            return
        # BEGIN guard: a candidate scoring zero or less is never tried
        if c.score <= 0:
            return
        # END guard: a candidate scoring zero or less is never tried
        keys.add(k)
        out.append(c)

    specific = [r for r in rules if r["id"] != table["default"]["id"]]

    def belongs(rule, u):
        # the default rule is a FALL-THROUGH over the same pages (C8-RG): what it re-extracts must still pass every
        # selected publisher rule's identity check, or the fall-through would undo C10 (a Springer page's nature.com
        # pointer, refused by the Springer rule, would come back as the default rule's)
        judges = [rule] + (specific if rule["id"] == table["default"]["id"] else [])
        return all(_identity_ok(j, u, context, doi, table)[0] for j in judges)

    for rule in rules:
        variables = var_values(rule, work, pages, urls, table)
        for spec in rule.get("candidates") or []:
            tech, name = spec["technique"], f"{rule['id']}.{spec['name']}"
            bonus, version = spec.get("bonus", 0), spec.get("version")
            if tech == "pointers":
                for p in readable:
                    for u, src in pointers(p.body, p.url):
                        if belongs(rule, u):
                            add(Candidate(u, f"{name}:{src}", rule["id"], score(u, table, affirmed=bool(
                                rule.get("identity"))), referer=referer_for(p.url, u)))
            elif tech == "page_regex":
                for p in readable:
                    for m in re.finditer(spec["match"].encode("utf-8"), p.body):
                        raw = _html.unescape(m.group("url").decode("utf-8", "replace"))
                        for u in resolve(base_of(p.body, p.url), raw):
                            if belongs(rule, u):
                                add(Candidate(u, name, rule["id"], score(u, table, affirmed=bool(rule.get("identity"))),
                                              referer=referer_for(p.url, u)))
            elif tech in ("template", "two_hop", "rewrite"):
                sources = [("doi", doi)] if spec.get("on") == "doi" else (
                    [(u, u) for u in urls] if spec.get("on") == "urls" else [(None, None)])
                for ref_url, subject in sources:
                    fields = _doi_fields(doi)
                    if spec.get("match") and spec.get("on") in ("urls", "doi"):
                        m = re.search(spec["match"], subject or "", re.I)
                        if not m:
                            continue
                        fields.update({k: v for k, v in m.groupdict().items() if v is not None})
                    if tech == "rewrite":
                        made = [re.sub(spec["match"], spec["replace"], subject, count=1, flags=re.I)]
                    else:
                        made = _expand(spec["template"], fields, variables)
                    for u in made:
                        add(Candidate(u, name, rule["id"], score(u, table, bonus=bonus), version=version,
                                      referer=referer_for(ref_url or landing, u),
                                      two_hop=list(spec.get("then") or []) if tech == "two_hop" else None))
    return out[:MAX_CANDIDATES], [r["id"] for r in rules]


def _landing_url(pages, resolved):
    """The URL a Referer names for a candidate a rule built (guard 24): the landing page read, else the URL the
    DOI resolved to (the publisher's article URL, even when its page was an interstitial)."""
    for p in pages:
        if p.origin == "doi" and p.readable:
            return p.url
    return resolved


def _dedupe_key(url):
    """A10: one candidate per resource — every query parameter except `download` dropped for the comparison (Zotero's
    rule), a signed URL compared whole (A10: never strip a signature)."""
    s = urllib.parse.urlsplit(url)
    if _SIGNED.search(url):
        return url
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(s.query, keep_blank_values=True) if k.lower() == "download"]
    return urllib.parse.urlunsplit((s.scheme.lower(), s.netloc.lower(), s.path, urllib.parse.urlencode(keep), ""))


def rewrites_of(url, table=None):
    """C3's rewrites of a FAILED candidate: [(url, rewrite id, version)] for every global rewrite that changes it."""
    table = table or TABLE
    out = []
    for rw in table["global"].get("rewrites") or []:
        new = re.sub(rw["match"], rw["replace"], url, count=1)
        if new != url:
            out.append((new, rw["id"], rw.get("version")))
    return out


# ── the rung ───────────────────────────────────────────────────────────────────────────────────
def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _terminal(hop):
    return {"url": evidence_url(hop.url), "status_code": hop.status, "at": _now(), "headers": dict(hop.headers or {})}


def _stub_headers(hop):
    return {k: header(hop.headers, k) for k in STUB_HEADERS if header(hop.headers, k) is not None} if hop else {}


def _keep_terminal_headers(ev, hop):
    """S4.5 decision D22: every landing attempt records the stub-relevant headers of the response that decided it,
    independent of the acceptance test, so `stubs_bound` can re-read a landing the test did not judge."""
    # BEGIN guard: every landing attempt records the stub-relevant headers of its terminal response
    ev["terminal_headers"] = _stub_headers(hop)
    # END guard: every landing attempt records the stub-relevant headers of its terminal response


def _client(ctx):
    from litkb.netutil import Client

    return (getattr(ctx, "clients", None) or {}).get(ROUTE) or Client()


def fetch_landing(work, ctx):
    """THE RUNG (module docstring). -> the route dict `litkb.acquire.run.Rung` documents."""
    client = _client(ctx)
    pacer = getattr(ctx, "pacer", None)
    table = TABLE
    doi = (work or {}).get("doi")
    tried, codes, pages, urls = [], [], [], []
    ev = {"landing_page": None, "resolved_url": None, "doi_page": None, "leads": [], "candidates": [], "rules": []}
    refusals = []                                  # (verdict, hop) for every typed refusal met
    last = {"hop": None}

    def note(hop, verdict, why):
        codes.append(int(hop.status or 0))
        tried.append(f"{host_of(hop.url)}:{hop.status}={verdict}")
        last["hop"] = hop
        if verdict in REFUSAL_ORDER:
            refusals.append((verdict, hop, why))

    def stop_transient(hop, why):
        ev["stopped"] = f"a transient answer stopped the rung: {why}"
        return _result("api-error", ev, tried, codes, hop=hop, retriable=True,
                       note=f"{host_of(hop.url)} answered {hop.status}: {why}; the ladder's scheduled retry asks again")

    # 1 leads: pages an earlier rung of this run was served
    for lead in list(getattr(ctx, "leads", None) or []):
        u = lead.get("url") or ""
        if not u:
            continue
        urls.append(u)
        verdict, why = classify(lead.get("status") or 0, lead.get("headers"), lead.get("body"), u,
                                rules=rules_for(doi, [u], table), purpose="page", table=table)
        page = Page(u, int(lead.get("status") or 0), lead.get("headers") or {}, lead.get("body") or b"",
                    f"lead:{lead.get('route')}", verdict, why)
        pages.append(page)
        ev["leads"].append({"route": lead.get("route"), "url": evidence_url(u), "verdict": verdict, "why": why})
    # 2 the DOI's landing page
    if doi:
        hops = walk(client, doi_url(doi), accept=PAGE_ACCEPT,
                    timeout=PAGE_TIMEOUT_S, pacer=pacer)
        for h in hops[:-1]:
            codes.append(int(h.status or 0))
            tried.append(f"{host_of(h.url)}:{h.status}=hop")
            urls.append(h.url)
        final = hops[-1]
        urls.append(final.url)
        ev["resolved_url"] = evidence_url(final.url)
        if final.refused:
            verdict, why = "unexpected", f"guard 9: {final.refused}"
        else:
            verdict, why = classify(final.status, final.headers, final.body, final.url,
                                    rules=rules_for(doi, [h.url for h in hops], table), purpose="page",
                                    chain=[h.url for h in hops], table=table)
        ev["doi_page"] = {"url": evidence_url(final.url), "status": final.status, "verdict": verdict, "why": why}
        # BEGIN guard: a transient landing page stops the rung as a retriable api-error
        if verdict == "transient":
            codes.append(int(final.status or 0))
            tried.append(f"{host_of(final.url)}:{final.status}=transient")
            return stop_transient(final, why)
        # END guard: a transient landing page stops the rung as a retriable api-error
        if verdict == "pdf":
            # the DOI resolves straight to a file: the bytes the loop's acceptance test judges
            note(final, "pdf", why)
            return _downloaded(final, final.body, "doi.resolves-to-pdf", None, ev, tried, codes)
        page = Page(final.url, final.status, final.headers, final.body, "doi", verdict, why, [h.url for h in hops])
        if verdict == "landing":
            # never an interstitial: C6-RG — only a page with citation metadata is recorded as the landing page
            ev["landing_page"] = evidence_url(final.url)
            codes.append(int(final.status or 0))
            tried.append(f"{host_of(final.url)}:{final.status}=landing")
            last["hop"] = final
        else:
            note(final, verdict, why)
        pages.insert(0, page)
    # 3 candidates
    urls = list(dict.fromkeys(urls))
    resolved = next((p.url for p in pages if p.origin == "doi"), None)
    cands, rule_ids = candidates_for(work, pages, urls, resolved=resolved, table=table)
    ev["rules"] = [_freshness(r, table) for r in rule_ids]
    queue = list(cands)
    asked = 0
    while queue and asked < MAX_CANDIDATES:
        c = queue.pop(0)
        asked += 1
        out = _try(client, c, pacer, table, rule_ids, note, context=urls, doi=doi)
        ev["candidates"].append({"url": evidence_url(c.url), "source": c.source, "rule": c.rule, "score": c.score,
                                 "verdict": c.verdict, "why": c.why, "status": c.status, "requests": c.requests})
        if out is None:
            # the candidate FAILED (a typed refusal, or an unexpected answer): only now its C3 rewrites (oadoi's
            # rule: "rewrite only AFTER the original URL fails"), and never a rewrite of a rewrite
            if not c.rewritten:
                for new, rid, version in rewrites_of(c.url, table):
                    if not any(_dedupe_key(q.url) == _dedupe_key(new) for q in queue):
                        queue.append(Candidate(new, f"{c.source}+rewrite:{rid}", c.rule, c.score,
                                               version=version or c.version, referer=c.referer, rewritten=True))
            continue
        kind, hop, data = out
        # BEGIN guard: a transient answer to a candidate stops the rung as a retriable api-error
        if kind == "transient":
            return stop_transient(hop, c.why)
        # END guard: a transient answer to a candidate stops the rung as a retriable api-error
        if kind == "pdf":
            return _downloaded(hop, data, c.source, c.version, ev, tried, codes)
        if kind == "bad-file":
            # the probe saw a PDF and the whole answer is not one: the served bytes are a bad file (the loop's
            # acceptance test types them)
            return _result("bad-file", ev, tried, codes, hop=hop, rejected=data,
                           note=f"{c.source}: the Range probe saw the PDF magic and the whole answer was not a PDF")
        if kind == "two_hop":
            queue = data + queue
    # 4 no file
    if refusals:
        best = min(refusals, key=lambda r: REFUSAL_ORDER.index(r[0]))
        return _result("blocked", ev, tried, codes, hop=best[1], sub_status=best[0], rejected=best[1].body,
                       note=f"no candidate served a PDF; the strongest refusal: {best[0]} ({best[2]})")
    if not cands and any(p.readable for p in pages):
        hop = last["hop"]
        return _result("not-in-archive", ev, tried, codes, hop=hop, sub_status="no_pdf_link",
                       rejected=next((p.body for p in pages if p.readable and p.origin == "doi"), None),
                       note="a landing page was read, and neither it nor any rule offered a PDF candidate")
    # asked without a DOI (an arXiv-only work: `needs` in _register) and no earlier rung of this run was served a
    # page: there was nothing to follow. Not a refusal of anything (no request was made): no_pdf_link, and the route
    # has no DEAD status (litkb.acquire.run.DEAD_STATUSES), so a later run with a lead asks again
    # BEGIN guard: a work with no DOI and no lead is nothing to follow, never a refusal
    if not doi and not pages:
        return _result("not-in-archive", ev, tried, codes, hop=None, sub_status="no_pdf_link",
                       note="no DOI to resolve and no page an earlier rung of this run was served: nothing to follow")
    # END guard: a work with no DOI and no lead is nothing to follow, never a refusal
    hop = last["hop"]
    read = any(p.readable for p in pages)
    # the vocabulary has no word for "every candidate answered something the probe could not type" (a 400, a 406, a
    # binary that is not a PDF, a guard-9 refusal): html_or_reader is the default, and the note says which case it is
    return _result("blocked", ev, tried, codes, hop=hop, sub_status="html_or_reader",
                   rejected=(hop.body if hop is not None else None),
                   note=(f"a landing page was read and none of its {len(ev['candidates'])} candidate(s) answered a PDF "
                         f"or a refusal the probe typed (their answers: "
                         f"{', '.join(sorted({x['verdict'] or '?' for x in ev['candidates']})) or 'none'}); typed "
                         f"html_or_reader by default" if read else
                         "no landing page could be read and no candidate answered with a refusal the probe typed"))


def doi_url(doi):
    """The DOI resolver URL this rung asks first (the recorder asks the same one: qc/instruments/litkb_landing_record.py)."""
    return "https://doi.org/" + urllib.parse.quote(doi, safe="/:;()")


def _freshness(rule_id, table):
    rule = next((r for r in table["rules"] if r["id"] == rule_id), table["default"])
    lu = (rule.get("source") or {}).get("lastUpdated")
    age = None
    if lu:
        try:
            age = (datetime.date.today() - datetime.date.fromisoformat(lu)).days
        except ValueError:
            age = None
    return {"id": rule_id, "lastUpdated": lu, "age_days": age}


def _try(client, c, pacer, table, rule_ids, note, context=(), doi=None):
    """Probe one candidate. -> None (a refusal, typed into c), or (kind, hop, data) with kind in
    pdf / bad-file / transient / two_hop."""
    ok, why = public_url(c.url)
    if not ok or shadow_host(c.url):
        c.verdict, c.why = "unexpected", (f"guard 9: {why}" if not ok else "a shadow host: never asked by Stage C")
        return None
    rules = [r for r in list(table["rules"]) + [table["default"]] if r["id"] in rule_ids]
    hdr = {"Referer": c.referer} if c.referer else {}
    if c.two_hop is not None:
        # C12: an HTML shell to read again (IEEE stamp.jsp), fetched as a page
        hops = walk(client, c.url, accept=PAGE_ACCEPT, headers=hdr, timeout=PAGE_TIMEOUT_S, pacer=pacer,
                    meta_refresh=True)
        c.requests += len(hops)
        final = hops[-1]
        verdict, why = classify(final.status, final.headers, final.body, final.url, rules=rules,
                                chain=[h.url for h in hops], table=table)
        c.status, c.verdict, c.why = final.status, verdict, why
        if verdict in ("transient", "pdf"):
            note(final, verdict, why)
            return verdict, final, (final.body if verdict == "pdf" else None)
        found = []
        if 200 <= final.status < 300:
            for rx in c.two_hop:
                for m in re.finditer(rx.encode("utf-8"), final.body or b""):
                    raw = _html.unescape(m.group("url").decode("utf-8", "replace"))
                    for u in resolve(final.url, raw):
                        own = next((r for r in rules if r["id"] == c.rule), None)
                        if own is not None and not _identity_ok(own, u, list(context), doi, table)[0]:
                            continue
                        if all(u != f.url for f in found):
                            found.append(Candidate(u, f"{c.source}>then", c.rule, c.score, version=c.version,
                                                   referer=referer_for(final.url, u), rewritten=True))
        # the shell is an HTML page by design: it is a refusal only when it yielded nothing to follow
        note(final, "two-hop" if found else verdict, why)
        return ("two_hop", final, found) if found else None
    rng = {}
    # BEGIN guard: every candidate is probed with 4 KB before its body is spent
    rng = {"Range": PROBE_RANGE}
    # END guard: every candidate is probed with 4 KB before its body is spent
    # a meta refresh IS followed on the way to a PDF: ScienceDirect's PDF path passes through an intermediate HTML
    # page that refreshes to the signed file (survey §2.1 Elsevier row: "every hop through parseIntermediatePDFPage
    # (meta-refresh)"; C8). The walk follows one only on a page with no citation metadata, so a landing page answering
    # a PDF request is still typed, never walked.
    hops = walk(client, c.url, accept=PDF_ACCEPT, headers=dict(hdr, **rng), timeout=PDF_TIMEOUT_S,
                pacer=pacer, meta_refresh=True)
    c.requests += len(hops)
    final = hops[-1]
    if final.refused:
        c.status, c.verdict, c.why = 0, "unexpected", f"guard 9: {final.refused}"
        return None
    verdict, why = classify(final.status, final.headers, final.body, final.url, rules=rules,
                            chain=[h.url for h in hops], table=table)
    c.status, c.verdict, c.why = final.status, verdict, why
    note(final, verdict, why)
    if verdict == "transient":
        return "transient", final, None
    if verdict != "pdf" and final.status != 416:
        return None
    if final.status == 200 and len(final.body or b"") > PROBE_BYTES:
        # the server ignored the Range header: the whole file is already here
        return "pdf", final, final.body
    # 206 (or 416: the server refused the range) -> the whole file, same Referer. Walked like the probe, hop by hop:
    # guard 9 and "a redirect into a bot check is never followed" hold on the whole GET's redirects too, and the
    # ledger names the URL that actually served the file (auditor-C2b F4: a `follow=True` GET here let its redirects
    # past both, and booked the pre-redirect URL). No meta refresh: the probe already reached the file's URL, and an
    # HTML answer there now is a bad file, not a hop.
    wh = walk(client, final.url, accept=PDF_ACCEPT, headers=dict(hdr), timeout=PDF_TIMEOUT_S, pacer=pacer,
              meta_refresh=False)
    c.requests += len(wh)
    whole = wh[-1]
    if whole.refused:
        c.status, c.verdict, c.why = 0, "unexpected", f"the whole GET's redirect: guard 9: {whole.refused}"
        return None
    wv, wwhy = classify(whole.status, whole.headers, whole.body, whole.url, rules=rules,
                        chain=[h.url for h in wh], table=table)
    note(whole, "pdf" if wv == "pdf" else wv, wwhy)
    if wv == "transient":
        c.why = wwhy
        return "transient", whole, None
    if wv == "pdf":
        return "pdf", whole, whole.body
    c.verdict, c.why = wv, f"the whole answer after a PDF-looking probe: {wwhy}"
    # a REFUSAL the classifier typed (noted above, so it competes in REFUSAL_ORDER): the server refused the whole
    # file, it did not serve a wrong one — e.g. the whole GET redirected into a bot check, which the walk now stops at
    # (builder-C2b round 2, with auditor-C2b F4)
    # BEGIN guard: a refusal of the whole GET is typed as a refusal, never booked as a bad file
    if wv in ("challenge_or_bot_check", "identity_required", "not_found"):
        return None
    # END guard: a refusal of the whole GET is typed as a refusal, never booked as a bad file
    return ("bad-file", whole, whole.body) if whole.body and whole.status else None


def _downloaded(hop, data, source, version, ev, tried, codes):
    _keep_terminal_headers(ev, hop)
    ev["source"] = source
    return {"status": "downloaded", "pdf": data, "source_url": hop.url, "tried": tried, "http_codes": codes,
            "terminal": _terminal(hop), "kind": "pdf", "version": version, "landing": ev,
            "detail": f"a PDF from {source}"}


def _result(status, ev, tried, codes, *, hop, sub_status=None, rejected=None, retriable=None, note=""):
    _keep_terminal_headers(ev, hop)
    r = {"status": status, "pdf": None, "source_url": "", "tried": tried, "http_codes": codes,
         "terminal": _terminal(hop) if hop is not None else {"url": "", "status_code": None, "at": _now()},
         "landing": ev, "detail": note}
    if sub_status:
        r["sub_status"] = sub_status
    if retriable is not None:
        r["retriable"] = retriable
    # nothing downloaded is discarded (litkb.acquire.run's rule): the answer that decided the attempt is kept,
    # unless it is the client's own status-0 error text (litkb.acquire.open_access's guard)
    if rejected and hop is not None and hop.status:
        r["rejected"], r["rejected_url"] = rejected, evidence_url(hop.url)
    return r


# ── registration: the ladder runs this rung as route `landing` (Stage C) ───────────────────────
def _register():
    from litkb.acquire import run as _run

    # `needs`: a DOI (the landing page it resolves to) OR an arXiv id — a work open_access can ask (its own `needs`)
    # may have been served a page with a PDF pointer, and Stage C must be asked to follow that lead even without a
    # DOI (auditor-C2b F11: with `("doi",)` an arXiv-only work's lead met a `no_identifier` skip, which the gated
    # counter rightly reads as "not followed")
    if not any(r.route == ROUTE for r in _run.RUNGS):
        _run.register(_run.Rung(ROUTE, fetch_landing, needs=("doi", "arxiv"), concurrent=False, retry_transient=True))


_register()

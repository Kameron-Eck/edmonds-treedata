"""Stage B of the acquisition ladder, the metadata fan-out (LITKB_WORKPLAN.md "### S4.5" item 4; S4.5 builder
C2a) — the shared plumbing, and the rungs that read an identifier service.

Every rung is asked for every row that reaches it, so its YIELD on this corpus is measured by the run (its
attempt rows) and zero is an allowed answer. The ORDER and the CLOSURE RULE are the linkage survey's
(Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md §2.3), realised in the rung registry's own order
(`litkb.acquire.run`: the concurrent rungs of a stage run together, then its sequential rungs in registry order):

  Wave 1, CONCURRENT (wall-clock = the slowest): `opencitations` (META: several schemes in one GET),
      `crossref-link` (B4: `link[]` AND `alternative-id` AND `issn-type` AND `relation`, never `link[]` alone),
      `openalex` (B3: `best_oa_location` + every `pdf_url`, and `ids` / `pmh_id`) — beside the repository rungs
      of litkb.acquire.stage_b_repos (doaj, openaire, hal, osf) and C1a's `open_access`.
  Wave 2, one conditional call per gap, SEQUENTIAL in this order: `datacite` (B6: a DataCite-prefixed DOI, a
      DOI Crossref answered 404 for, or the arXiv CANDIDATE Stage A derived), `zenodo` / `figshare` (after
      DataCite, whose concept -> version edge they need), `ncbi-idconv` (only while pmid or pmcid is absent),
      `s2` (Semantic Scholar LAST among the services: it 429s in seconds unauthenticated), `europepmc` (only once
      a PMCID has appeared), `arxiv` (B1/B10: every arXiv id the run holds), `venue` (B13).
  THE CLOSURE RULE (from oc_graphenricher@08cd064, via LINKAGE §2.3): a scheme is pursued only if absent (the
      Wave-2 conditions above); the input key is whichever held identifier the service accepts; the
      accumulation runs after whichever resolver won (`stage_a.found`, every rung's discoveries join the run's
      identifier set, which the later rungs read); a repeat uses only identifiers discovered since the last
      pass. THE PASS CAP IS ONE PASS PER LADDER RUN (Codex X5: "<=3 passes" is "in practice", not a bound — a cap
      must be enforced and hitting it reported): the registry order IS the dependency order, so one pass reaches
      every later rung with every earlier discovery; a discovery an EARLIER rung of the same run would have
      accepted is REPORTED on the discovering attempt as `closure_pending` (the next hunt of the work asks with
      it, reading what the harvest wrote) — never a silent stop.
  A Wave-2 rung whose condition fails asks nothing and returns a `skipped` answer the ladder records
  (`no_identifier`: the identifier it keys on is absent; `policy_refused`: the closure rule — every scheme it
  fills is already held), with the condition in the row's `policy` detail.

B1 — "the identifier already carries the file" (`carried_files`): an arXiv id (arxiv.org/pdf/<id>: B10's
export.arxiv.org rewrite MEASURED 406 for a PDF — see ARXIV_PDF), and Semantic Scholar's `openAccessPdf` when it is
not a `doi.org` URL. Every arXiv PDF URL an index lists is canonicalised to its arXiv id (survey A10: candidate
canonicalisation with roles), so the arXiv copy is always asked through B1, by the `arxiv` rung. B1's other
carriers are NOT BUILT as their own rungs: an ACL Anthology id is asked by `venue` (B13); CVF has no identifier
litkb holds (a conference index must be parsed — survey B13); OSTI ids are harvested by no parser of builder B1's.
Nor is a native rung built for the preprint servers Stage A's prefix router names without a 0033 route
(`stage_a.PREFIX_ROUTES` entries whose route is '': bioRxiv 10.1101, Research Square, Authorea, TechRxiv,
ChemRxiv, Preprints.org) — a new route needs a migration (brief-CONTRACTS.md, the route vocabulary).

THE HARVEST (S4.5 decision D2): every identifier a rung reads is handed back in the route dict's `harvest`
(B1's pure parsers: `harvest.from_crossref / from_openalex / from_datacite / from_s2`, and this module's own for
OpenCitations, the NCBI converter and Europe PMC), and the ladder writes it through B1's one write path
(`write_harvest` -> `litkb.admit.harvest.record`, the conflict rule in the database) on the attempt that read it.
A rung never touches the database (the rung interface, litkb.acquire.run).

Politeness: the configured contact email (`open_access.unpaywall_email`, the one litkb holds — never an address
written here) where a service asks for one (Crossref's and OpenAlex's `mailto`, NCBI's `email`), registered for
redaction BEFORE the request that carries it; per-host pacing (`pacer_for`); the ladder's per-route AIMD and
refusal ladder (C1a) around every rung.

Every mechanism is a RELAYED design (CLAUDE.md §3.4c), UNVALIDATED until an independent referee scores it on
the rows the plan names. The endpoints are the linkage survey's edge table (§2.1, VERIFIED live there) and the
PDF-sources survey's Stage B rows; only Crossref, OpenAlex, Semantic Scholar and arXiv were ASKED by this
builder (the grant: the FREE-PDF rows, one preprint, one crosswalk arXiv-id work — qc/instruments/
litkb_stage_ab_record.py); every other rung's parser is tested on CONSTRUCTED answers and says so.
"""
import datetime
import json
import re
import threading
import time
import urllib.parse

from litkb import identifiers as I
from litkb.acquire import accept as _accept
from litkb.acquire import backoff as _backoff
from litkb.acquire import policy as _policy
from litkb.acquire import stage_a as A
from litkb.admit.resolver import ARXIV_MIN_INTERVAL, REGISTRY_MIN_INTERVAL
from litkb.netutil import Client, Pacer, add_secret

#: An identifier service's request timeout: litkb's registry client's (admit/resolver.py::registry_get).
API_TIMEOUT = 60
#: A PDF request's timeout and Accept: the open-access route's (acquire/open_access.py::fetch_open_access).
PDF_TIMEOUT = 300
PDF_ACCEPT = "application/pdf,*/*;q=0.5"
JSON_ACCEPT = "application/json"
#: A browser's Accept (the one Firefox sends for a page): the arXiv API "406s without a browser-ish Accept"
#: (PDF-sources survey B10, VERIFIED at lukasschwab/arxiv.py@09d1b8b).
BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
#: An arXiv id's PDF: arxiv.org, the host the open-access route already asks (ONE home: acquire/open_access.py
#: ARXIV_PDF). B10's host rewrite to export.arxiv.org is NOT applied to the PDF — MEASURED 2026-09-23 (this
#: builder's recording, qc/instruments/litkb_stage_ab_record.py + scratch kats_pdf2.py): export.arxiv.org/pdf/
#: 1910.12077 answered 406 with an empty body TWICE, once with the PDF Accept below and once with BROWSER_ACCEPT,
#: while the live ledger holds 15 `ok` and 3 `binding-failed` open_access attempts on arxiv.org/pdf/<id> with that
#: same PDF Accept (read as litkb_reader). The rewrite is the survey's for the arXiv API, which no rung here calls.
from litkb.acquire.open_access import ARXIV_PDF  # noqa: E402

#: The endpoints (linkage survey §2.1 edge table rows 1, 7, 17, 22, 26, 30 — VERIFIED live there).
CROSSREF_WORK = "https://api.crossref.org/works/{doi}"
OPENALEX_WORK = "https://api.openalex.org/works/doi:{doi}"
OPENCITATIONS_META = "https://api.opencitations.net/meta/v1/metadata/doi:{doi}"
DATACITE_WORK = "https://api.datacite.org/dois/{doi}"
NCBI_IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/?ids={ids}&format=json"
S2_PAPER = "https://api.semanticscholar.org/graph/v1/paper/{key}?fields=externalIds,openAccessPdf,title,year"
#: NCBI's `tool` parameter (edge row 7: "`tool`+`email` warned if absent"): the name this client goes by.
NCBI_TOOL = "litkb"

#: Crossref `link[]` intended applications a PDF candidate may carry (B4; B4-RG MEASURED MDPI's as
#: `similarity-checking` with content-type `unspecified`, which is exactly why the filter is `pdf` in the
#: content type OR the URL path, never the content type alone).
_PDF_IN = re.compile(r"pdf", re.I)


# ── plumbing ─────────────────────────────────────────────────────────────────────────────────────
def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def host_of(url):
    return urllib.parse.urlparse(url or "").netloc.lower()


_PACERS, _LOCK = {}, threading.Lock()
#: guards every ladder run's `asked_urls` map (`fetch_candidates`): one process-wide lock, held for a dict lookup
_ASKED_LOCK = threading.Lock()


def pacer_for(ctx, host):
    """The per-host pacer: arXiv 3 s (admit/resolver.py ARXIV_MIN_INTERVAL, arXiv's API guidance), every other
    service 1 s (REGISTRY_MIN_INTERVAL, litkb's registry pace). A ladder whose own pacer paces nothing
    (interval 0: the tests, a replay) gets that pacer instead, so it never sleeps."""
    base = getattr(ctx, "pacer", None)
    if base is not None and getattr(base, "interval", None) == 0:
        return base
    with _LOCK:
        p = _PACERS.get(host)
        if p is None:
            p = _PACERS[host] = Pacer(interval=ARXIV_MIN_INTERVAL if host.endswith("arxiv.org") else
                                      REGISTRY_MIN_INTERVAL, sleep=getattr(base, "sleep", time.sleep))
        return p


def client_for(ctx, route):
    """The rung's client: the one the caller injected for this route (a test's stub, a replay), else a fresh
    `netutil.Client` — litkb's one socket path, so the cassette layer and the socket guard see every request."""
    clients = getattr(ctx, "clients", None) or {}
    return clients.get(route) or Client(base="")


def contact_email():
    """The configured contact email (the one litkb holds: Unpaywall's, decisions.yaml litkb-p0-foundation
    §15.5), registered for redaction BEFORE any request carries it. '' when none is configured."""
    from litkb.acquire import open_access as _oa

    email = (_oa.unpaywall_email() or "").strip()
    # BEGIN guard: the contact email is registered for redaction before any request carries it
    add_secret(email)
    # END guard: the contact email is registered for redaction before any request carries it
    return email


def get(ctx, route, url, *, accept=JSON_ACCEPT, timeout=API_TIMEOUT, follow=True, headers=None):
    """One paced GET through the rung's client. -> (status, headers, body, terminal)."""
    pacer_for(ctx, host_of(url)).wait()
    c = client_for(ctx, route)
    st, hd, body = c.get(url, accept=accept, timeout=timeout, follow=follow, headers=headers) if headers else \
        c.get(url, accept=accept, timeout=timeout, follow=follow)
    return int(st or 0), hd or {}, body or b"", {"url": url, "status_code": int(st or 0), "at": _now(),
                                                   "headers": hd or {}}


def get_json(ctx, route, url, *, accept=JSON_ACCEPT):
    """-> (status, parsed JSON or None, terminal)."""
    st, _hd, body, term = get(ctx, route, url, accept=accept)
    data = None
    if st == 200:
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            data = None
    return st, data, term


def service_miss(route, st, term, what, *, codes=None):
    """The route dict for a service that did not answer with a usable record: 404 -> `unresolved` (the
    identifier does not resolve at this service); 0 / 429 / 5xx -> `api-error` (transient: the ladder's one
    scheduled retry and the back-off decide, C1a); any other code -> `api-error` with the code."""
    codes = codes or [st]
    if st in (404, 410):
        return {"status": "unresolved", "http_codes": codes, "terminal": term,
                "detail": f"{what}: no record for this identifier ({st})"}
    return {"status": "api-error", "http_codes": codes, "terminal": term,
            "detail": f"{what}: answered {st}" + (" (the client's own transport failure)" if st == 0 else "")}


def _shadow_hosts():
    return {p.host for p in _policy.POLICY if p.tier == _policy.SHADOW}


def canon_arxiv(url):
    """An arXiv PDF / abs URL -> its arXiv id (survey A10: a candidate canonicalised to the identifier whose
    role it is; B1 then fetches it), else ''."""
    m = re.match(r"(?i)^https?://(?:export\.)?arxiv\.org/(?:pdf|abs)/([^?#]+?)(?:\.pdf)?(?:[?#].*)?$", url or "")
    if not m:
        return ""
    a = I.norm("arxiv", m.group(1))
    return a if I.valid("arxiv", a) else ""


def fetch_candidates(route, candidates, ctx, work=None, *, html_status="bad-file"):
    """Ask each candidate URL for the file, in order, until one serves a PDF. -> the route dict.

    `candidates` is [(url, meta)]; meta may carry `version` (Unpaywall's words: submittedVersion / ...). A URL
    already asked by ANY rung of this ladder run is not asked again (survey A10: "stops a 12-index fan-out
    spending six GETs on one file"; the note names the rung that asked it — `work["asked_urls"]` maps each URL
    to its asker, auditor-C2a round 2 F7), and a URL on a host a SHADOW policy line names is never asked by a
    legitimate rung. A TRANSIENT answer is no answer: its URL is released, so the ladder's one scheduled retry of
    the rung asks it again (auditor-C2a round 2 F1). Transient is what C1a's in-run retry rule says it is
    (`backoff.classify`, its one home — the answer read as its own row: a challenge page as `blocked`, anything
    else as `api-error`): a transport failure, 408, 429, a 5xx; a challenge page is transient only if that rule
    retries a `blocked` row (C1a's final rule never does: "waiting longer cannot turn this client into a
    browser"), so a challenge URL stays asked. The answer, strongest first: a PDF -> `downloaded`; every
    request a transport failure -> `api-error` (S4.5 decision D15, retriable); a challenge page -> `blocked`; a
    page served where a file was expected -> `html_status` (`bad-file`, typed by the acceptance test — the plan's
    `html_response`, and a lead for Stage C; A4 passes `blocked`, typed `html_or_reader`); 401/403 -> `blocked`;
    404/410 -> `blocked` (`not_found`); anything else -> `api-error` with its codes. Nothing served is thrown
    away: the first page served is handed back in `rejected`."""
    asked = work.setdefault("asked_urls", {}) if isinstance(work, dict) else {}
    shadow = _shadow_hosts()
    tried, codes, notes = [], [], []
    kept, kept_url, kept_term, last_term = None, "", None, None
    challenge = False
    for url, meta in candidates:
        h = host_of(url)
        # BEGIN guard: a legitimate rung never asks a shadow host, and never asks one URL twice in a run
        if h in shadow:
            notes.append(f"{h}: a shadow host, never asked by a legitimate rung")
            continue
        with _ASKED_LOCK:
            # check AND reserve under one lock: the Wave-1 rungs run concurrently and share the run's map
            # (auditor-C2a F17: a check-then-add after the request let two of them ask one URL)
            if url in asked:
                notes.append(f"{h}: already asked in this ladder run by {asked[url]}")
                continue
            asked[url] = route
        # END guard: a legitimate rung never asks a shadow host, and never asks one URL twice in a run
        st, hd, body, term = get(ctx, route, url, accept=PDF_ACCEPT, timeout=PDF_TIMEOUT)
        # BEGIN guard: a transient answer is no answer, and the scheduled retry may ask its URL again
        own = "blocked" if st and Client.is_challenge(st, url, body) else "api-error"
        if _backoff.classify(own, [st]) == "transient":
            with _ASKED_LOCK:
                asked.pop(url, None)
        # END guard: a transient answer is no answer, and the scheduled retry may ask its URL again
        codes.append(st)
        last_term = term
        if _accept.quick_magic(body):
            return {"status": "downloaded", "pdf": body, "source_url": url, "tried": tried + [f"{h}:{st}=ok"],
                    "http_codes": codes, "terminal": term, "kind": "pdf", "version": (meta or {}).get("version"),
                    "detail": "; ".join(notes)}
        if st == 0:
            tried.append(f"{h}:0")
            continue
        tried.append(f"{h}:{st}")
        if Client.is_challenge(st, url, body):
            challenge = True
        if body and kept is None:
            kept, kept_url, kept_term = body, url, term
    base = {"pdf": None, "source_url": "", "tried": tried, "http_codes": codes,
            "terminal": kept_term or last_term or {"url": "", "status_code": None, "at": _now()}}
    if kept is not None:
        base.update({"rejected": kept, "rejected_url": kept_url})
    if not codes:
        return {**base, "status": "no-oa-copy", "detail": "; ".join(notes) or "no candidate to ask"}
    real = [c for c in codes if c]
    if not real:
        return {**base, "status": "api-error", "retriable": True,
                "detail": "; ".join(notes + ["every request was a transport failure"])}
    note = "; ".join(notes + [f"no %PDF- from {', '.join(tried)}"])
    if challenge:
        return {**base, "status": "blocked", "sub_status": "challenge_or_bot_check", "detail": note}
    if any(c == 200 for c in real) and kept is not None:
        if html_status == "blocked":
            return {**base, "status": "blocked", "sub_status": "html_or_reader", "detail": note}
        return {**base, "status": "bad-file", "detail": note}
    if any(c in (401, 403) for c in real):
        return {**base, "status": "blocked", "detail": note}
    if all(c in (404, 410) for c in real):
        return {**base, "status": "blocked", "sub_status": "not_found", "detail": note}
    return {**base, "status": "api-error", "detail": note}


def answered(route, candidates, ctx, work, *, harvest=None, term=None, detail="", html_status="bad-file",
             extra=None):
    """A service answered: ask its candidates (if any), attach the harvest and the service's own terminal.
    No candidate at all -> `no-oa-copy` (the service knows the work and lists no free copy)."""
    if candidates:
        r = fetch_candidates(route, candidates, ctx, work, html_status=html_status)
        if r.get("status") == "no-oa-copy" and term:
            # every candidate was one this run had asked (or a shadow host's): the service's own answer decides
            r["terminal"], r["http_codes"] = term, [term["status_code"]]
    else:
        r = {"status": "no-oa-copy", "http_codes": [term["status_code"]] if term else [], "terminal": term,
             "tried": []}
    r["detail"] = "; ".join(x for x in (detail, r.get("detail") or "") if x)
    if harvest:
        r["harvest"] = harvest
    if extra:
        r.update(extra)
    pend = ((work or {}).get("closure_pending") or {}).get(route)
    if pend:
        r.setdefault("stage_b", {})["closure_pending"] = pend
    return r


def closure_skip(reason_word, why):
    """A Wave-2 rung whose closure condition fails: it asks nothing (the ladder records the skip)."""
    return {"status": "skipped", "sub_status": reason_word, "policy": {"closure": why}}


#: The schemes each Stage B rung keys on — the closure rule's "input key is whichever held identifier the service
#: accepts" (LINKAGE §2.2's native-key table, for the services built here).
ACCEPTS = {"opencitations": ("doi",), "crossref-link": ("doi",), "openalex": ("doi",), "doaj": ("doi",),
           "openaire": ("doi",), "hal": ("doi",), "osf": ("doi",), "datacite": ("doi",), "zenodo": ("doi",),
           "figshare": ("doi",), "ncbi-idconv": ("doi",), "s2": ("doi", "arxiv"), "europepmc": ("pmcid",),
           "arxiv": ("arxiv",), "venue": ("doi", "acl")}


def gained(work, rows, route, edges=()):
    """Add a rung's harvested identifiers (and the identifier targets of its edition edges) to the run's set;
    -> the NEW (scheme, value) pairs, recorded on the attempt (the fan-out kill criterion's per-scheme gain).
    THE PASS CAP (module docstring): a scheme the work did not hold before, which a rung EARLIER in the registry
    order keys on, cannot be asked again in this run — it is recorded in `work["closure_pending"][route]` (and on
    the attempt, `stage_b.closure_pending`), never dropped in silence."""
    before = {s for s, _v, _via in work.get("ids") or []}
    targets = [{"scheme": e["target_scheme"], "value": e["target_value"]} for e in edges
               if e.get("state") == "asserted" and e.get("target_scheme") and e.get("target_value")]
    new = A.found(work, list(rows) + targets, route)
    order = [t[0] for t in RUNG_TABLE]
    here = order.index(route) if route in order else len(order)
    pend = sorted({r for s, _v in new if s not in before for r in order[:here] if s in ACCEPTS.get(r, ())})
    if pend:
        work.setdefault("closure_pending", {})[route] = pend
    return new


# ── the request URLs (one builder each, so the recorder and the rung ask the SAME URL: a cassette key) ──────
def _q(doi):
    return urllib.parse.quote(I.norm("doi", doi), safe="/()")


def _mailto(email, name="mailto"):
    return f"{name}={urllib.parse.quote(email)}" if email else ""


def crossref_url(doi, email=""):
    m = _mailto(email)
    return CROSSREF_WORK.format(doi=_q(doi)) + (f"?{m}" if m else "")


def openalex_url(doi, email=""):
    m = _mailto(email)
    return OPENALEX_WORK.format(doi=_q(doi)) + (f"?{m}" if m else "")


def opencitations_url(doi):
    return OPENCITATIONS_META.format(doi=_q(doi))


def datacite_url(doi):
    return DATACITE_WORK.format(doi=_q(doi))


def ncbi_url(doi, email=""):
    m = _mailto(email, "email")
    return (NCBI_IDCONV.format(ids=urllib.parse.quote(I.norm("doi", doi), safe="")) + f"&tool={NCBI_TOOL}"
            + (f"&{m}" if m else ""))


def s2_url(work):
    """-> the S2 record URL for `work` (its DOI, else its arXiv id), or '' when it holds neither."""
    doi = work.get("doi")
    if doi:
        return S2_PAPER.format(key="DOI:" + _q(doi))
    arx = A.ids_of(work, "arxiv")
    return S2_PAPER.format(key="ARXIV:" + arx[0]) if arx else ""


# ── B1: the identifier already carries the file ─────────────────────────────────────────────────
def arxiv_pdf(arxiv_id):
    return ARXIV_PDF.format(id=urllib.parse.quote(I.norm("arxiv", arxiv_id), safe="/."))


def carried_files(arxiv_ids=(), open_access_pdf=None):
    """B1 -> [(url, meta)] the identifiers the run holds that ALREADY CARRY the file: every arXiv id (the
    submitted version, at arxiv.org — see ARXIV_PDF for why not export.arxiv.org), and S2's `openAccessPdf` when it is
    neither a `doi.org` URL (not a PDF — survey B1 guard) nor an arXiv URL (that one is its arXiv id's).
    MEASURED between the survey's rounds (§M): S2's `openAccessPdf` names the 4 free arXiv siblings of IEEE /
    Springer / World Scientific papers in litkb's own 35-row miss bucket."""
    out = []
    # BEGIN guard: an identifier that already carries the file is followed (B1)
    for a in arxiv_ids:
        if a:
            out.append((arxiv_pdf(a), {"version": "submittedVersion", "arxiv": a}))
    u = (open_access_pdf or {}).get("url") if isinstance(open_access_pdf, dict) else None
    if u and host_of(u) not in ("doi.org", "dx.doi.org") and not canon_arxiv(u):
        out.append((u, {"version": None, "via": "s2 openAccessPdf"}))
    # END guard: an identifier that already carries the file is followed (B1)
    return out


# ── the harvest's one write (called by the ladder, never by a rung) ──────────────────────────────────
def write_harvest(conn, ws, token, work, route, r, *, agent, session):
    """The rung's harvested identifiers, written through B1's one write path (`harvest.record`: the conflict
    rule in the database) on the attempt that read them. -> the summary the attempt's detail keeps, or None
    when the rung harvested nothing. A failure is RETURNED as `error`, never raised: a harvest never fails an
    acquisition (builder-B1 §1.4). The archive route's `identifiers_unified` (B1's
    `harvest.record_route_identifiers`) is NOT written here: wiring it is builder-B1's open question 1, the
    orchestrator's to rule on — this is the one place it would go."""
    from litkb.admit import harvest as H

    h = (r or {}).get("harvest") if isinstance(r, dict) else None
    try:
        if not h or not (h.get("rows") or h.get("relations")):
            return None
        res = H.record(conn, ws, token, work["work_id"], h.get("rows") or [], h.get("relations") or [],
                       agent=agent, session=session)
        return {"rows": len(h.get("rows") or []), "relations": len(h.get("relations") or []),
                "identifiers": res.get("identifiers"), "edges": res.get("relations")}
    except Exception as e:                      # noqa: BLE001 — a harvest never fails an acquisition
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


# ── Wave 1 ───────────────────────────────────────────────────────────────────────────────────────
def link_candidates(message):
    """B4's filter over Crossref `link[]`: `pdf` in the content type OR in the URL path (MDPI's content type is
    `unspecified` — survey B4, B4-RG MEASURED). -> [(url, meta)]."""
    out = []
    for ln in (message or {}).get("link") or []:
        if not isinstance(ln, dict) or not ln.get("URL"):
            continue
        url = ln["URL"]
        if _PDF_IN.search(str(ln.get("content-type") or "")) or _PDF_IN.search(urllib.parse.urlparse(url).path):
            out.append((url, {"version": {"vor": "publishedVersion", "am": "acceptedVersion"}.get(
                str(ln.get("content-version") or "").lower()), "intended": ln.get("intended-application")}))
    return out


def rung_crossref_link(work, ctx):
    """B4 (route `crossref-link`): Crossref's record for the DOI. Its `link[]` PDF candidates are asked (a TDM
    endpoint that wants a token answers 401/403 and is typed `identity_required` — the plan's paywalled
    remainder), and `alternative-id` (the Elsevier PII), ISBN, ISSN / `issn-type` and `relation` are harvested
    through B1's `harvest.from_crossref`. A 404 marks the DOI for DataCite (LINKAGE §2.3: "Crossref 404 ->
    DataCite"); the live `type` may tighten the A2 router (a `posted-content` answer makes the work a
    preprint), and A0's record-class flag is recorded."""
    from litkb.admit import harvest as H

    doi = work.get("doi")
    st, data, term = get_json(ctx, "crossref-link", crossref_url(doi, contact_email()))
    work["crossref_status"] = st
    msg = (data or {}).get("message") if isinstance(data, dict) else None
    if st != 200 or not isinstance(msg, dict):
        return service_miss("crossref-link", st, term, "Crossref")
    rows, rels, rejected = H.from_crossref(msg, doi)
    new = gained(work, rows, "crossref-link", rels)
    observed = A.crossref_class(msg)
    before = getattr(ctx, "work_class", "")
    after = A.tighten(before, observed)
    if after != before and ctx is not None:
        ctx.work_class = after
    cands = []
    for u, meta in link_candidates(msg):
        a = canon_arxiv(u)
        if a:
            A.found(work, [{"scheme": "arxiv", "value": a}], "crossref-link")
        else:
            cands.append((u, meta))
    return answered("crossref-link", cands, ctx, work, term=term,
                    harvest={"rows": rows, "relations": rels, "rejected": rejected},
                    extra={"stage_b": {"gained": [f"{s}:{v}" for s, v in new], "crossref_class": observed,
                                       "work_class": after, "record_class": A.record_class(crossref=msg)}})


def openalex_candidates(w):
    """B3: `best_oa_location` first, then every location's `pdf_url` (never `best_oa_location` alone)."""
    out, seen = [], set()
    for loc in [(w or {}).get("best_oa_location") or {}] + list((w or {}).get("locations") or []):
        if not isinstance(loc, dict):
            continue
        u = loc.get("pdf_url")
        if u and u not in seen:
            seen.add(u)
            out.append((u, {"version": loc.get("version"), "is_oa": loc.get("is_oa")}))
    return out


def rung_openalex(work, ctx):
    """B3 (route `openalex`): OpenAlex's work for the DOI, ONE call per work (S4.5 decision D2 — litkb never
    called OpenAlex before; the survey's 50-per-call batching needs a pass over the whole queue the per-work
    ladder does not have, and is not built). Its PDF URLs are asked; `ids` and `pmh_id` are harvested through
    B1's `harvest.from_openalex`; OpenAlex's `is_paratext` / `is_retracted` feed A0's flag."""
    from litkb.admit import harvest as H

    doi = work.get("doi")
    st, data, term = get_json(ctx, "openalex", openalex_url(doi, contact_email()))
    if st != 200 or not isinstance(data, dict):
        return service_miss("openalex", st, term, "OpenAlex")
    rows = H.from_openalex(data, doi)
    new = gained(work, rows, "openalex")
    cands = []
    for u, meta in openalex_candidates(data):
        a = canon_arxiv(u)
        if a:
            A.found(work, [{"scheme": "arxiv", "value": a}], "openalex")
        else:
            cands.append((u, meta))
    return answered("openalex", cands, ctx, work, term=term, harvest={"rows": rows, "relations": []},
                    extra={"stage_b": {"gained": [f"{s}:{v}" for s, v in new],
                                       "record_class": A.record_class(openalex=data)}})


#: OpenCitations META `id` prefixes -> litkb schemes. VERIFIED live in LINKAGE §2.1 edge rows 1-6: `doi`,
#: `openalex`, `pmid` (and `omid`, OpenCitations' own, which has no scheme in litkb's registry — left out; `issn`
#: is the `venue`'s, row 3). ASSERTED by OpenCitations' docs, never observed live (LINKAGE §7.2): `pmcid`,
#: `wikidata` (kept: each names the same work; a value B1's validator refuses is dropped). NOT mapped: `arxiv` —
#: no source names it for META, and an arXiv id on a non-arXiv DOI names ANOTHER edition, which
#: `litkb-sibling-edition` makes an edge, never the work's own identifier (builder-B1's `harvest.from_s2` rule;
#: auditor-C2a F2); `isbn` and `jid` (docs-named; a book's ISBN is S4.6's, a journal id is the container's).
_OC_SCHEMES = {"doi": "doi", "pmid": "pmid", "pmcid": "pmcid", "openalex": "openalex", "wikidata": "wikidata"}


def from_opencitations(records, doi):
    """OpenCitations META records -> identifier rows (asserted_by `opencitations`, derived from the DOI asked).
    Pure. The record's `id` is a space-separated `<scheme>:<value>` list (LINKAGE §2.1 edge rows 1-6; the
    prefixes read are `_OC_SCHEMES`'); the requested DOI itself is not a new row; its `venue`'s `[issn:... ]` is
    the container's, not the work's — not harvested; an `arxiv:` token is never a row (`_OC_SCHEMES`)."""
    df = ("doi", I.norm("doi", doi))
    rows = []
    for rec in records if isinstance(records, list) else []:
        for tok in str((rec or {}).get("id") or "").split():
            prefix, _, value = tok.partition(":")
            scheme = _OC_SCHEMES.get(prefix.lower())
            if not scheme or not value:
                continue
            v = I.norm(scheme, value)
            if (scheme == "doi" and v == df[1]) or not I.valid(scheme, v):
                continue
            if not any(r["scheme"] == scheme and r["value"] == v for r in rows):
                rows.append(I.row(scheme, v, asserted_by="opencitations", derived_from=df,
                                  evidence={"field": "id"}))
    return rows


def rung_opencitations(work, ctx):
    """Wave 1 (route `opencitations`, metadata only): OpenCitations META for the DOI — one keyless GET that
    fills several schemes (LINKAGE §2.3 Wave 1 #1). It yields identifiers, never a file; its measure is
    `identifiers: opencitations=<works gaining>/<asked>` (S4.5 decision D19). An empty list is `unresolved`."""
    doi = work.get("doi")
    st, data, term = get_json(ctx, "opencitations", opencitations_url(doi))
    if st != 200 or not isinstance(data, list):
        return service_miss("opencitations", st, term, "OpenCitations META")
    if not data:
        return {"status": "unresolved", "http_codes": [st], "terminal": term,
                "detail": "OpenCitations META holds no record for this DOI"}
    rows = from_opencitations(data, doi)
    new = gained(work, rows, "opencitations")
    return answered("opencitations", [], ctx, work, term=term, harvest={"rows": rows, "relations": []},
                    detail="metadata only", extra={"stage_b": {"gained": [f"{s}:{v}" for s, v in new]}})


# ── Wave 2 ───────────────────────────────────────────────────────────────────────────────────────
def datacite_targets(work):
    """-> [(doi to ask, the candidate row it confirms or None)] under LINKAGE §2.3's Wave-2 condition: a DOI with
    a DataCite prefix, a DOI Crossref answered 404 for in THIS run, or the arXiv CANDIDATE DOI Stage A derived."""
    out = []
    doi = work.get("doi")
    if doi and (A.doi_prefix(doi) in A.DATACITE_PREFIXES or work.get("crossref_status") == 404):
        out.append((I.norm("doi", doi), None))
    for c in work.get("candidates") or []:
        if c.get("scheme") == "doi" and A.doi_prefix(c["value"]) in A.DATACITE_PREFIXES:
            out.append((c["value"], c))
    return out


def rung_datacite(work, ctx):
    """B6 (route `datacite`): DataCite's record — only under the Wave-2 condition (`datacite_targets`), else a
    `no_identifier` skip. The returned DOI is VERIFIED against the one asked (survey B6 guard; Codex X5: the
    digest dropped it) — a record for another DOI is refused, never harvested. Its identifiers and relation
    edges go through B1's `harvest.from_datacite`; an arXiv CANDIDATE DOI it confirms is written with
    `verified_by = 'datacite'` (B1's guard refuses a candidate without it); `contentUrl` PDF links are asked."""
    from litkb.admit import harvest as H

    targets = datacite_targets(work)
    if not targets:
        return closure_skip("no_identifier", "DataCite is asked for a 10.48550 / 10.5281 / 10.6084 DOI, a DOI "
                                             "Crossref answered 404 for, or Stage A's arXiv candidate — none here")
    doi, cand = targets[0]
    st, data, term = get_json(ctx, "datacite", datacite_url(doi), accept="application/vnd.api+json")
    attrs = ((data or {}).get("data") or {}).get("attributes") if isinstance(data, dict) else None
    if st != 200 or not isinstance(attrs, dict):
        return service_miss("datacite", st, term, "DataCite")
    got = I.norm("doi", attrs.get("doi") or ((data.get("data") or {}).get("id") or ""))
    # BEGIN guard: DataCite's answer is for the DOI that was asked
    if got != I.norm("doi", doi):
        return {"status": "unresolved", "http_codes": [st], "terminal": term,
                "detail": f"DataCite answered for {got!r}, not the DOI asked {doi!r}: refused, nothing harvested"}
    # END guard: DataCite's answer is for the DOI that was asked
    rows, rels, rejected = H.from_datacite(attrs, doi)
    if cand is not None:
        rows = [dict(cand, verified_by="datacite")] + rows
    new = gained(work, rows, "datacite", rels)
    cands = []
    for u in attrs.get("contentUrl") or []:
        if isinstance(u, str) and u.startswith("http"):
            a = canon_arxiv(u)
            if a:
                A.found(work, [{"scheme": "arxiv", "value": a}], "datacite")
            else:
                cands.append((u, {"version": None}))
    return answered("datacite", cands, ctx, work, term=term,
                    harvest={"rows": rows, "relations": rels, "rejected": rejected},
                    extra={"stage_b": {"gained": [f"{s}:{v}" for s, v in new],
                                       "confirmed_candidate": cand["value"] if cand else None}})


def from_idconv(data, doi):
    """NCBI's ID Converter JSON -> pmid / pmcid rows (asserted_by `pmc_idconv`, derived from the DOI). Pure.
    A record carrying `status: error` (the converter's "not found") yields nothing."""
    df = ("doi", I.norm("doi", doi))
    rows = []
    for rec in (data or {}).get("records") or [] if isinstance(data, dict) else []:
        if not isinstance(rec, dict) or str(rec.get("status") or "").lower() == "error":
            continue
        for key, scheme in (("pmid", "pmid"), ("pmcid", "pmcid")):
            v = rec.get(key)
            if v not in (None, ""):
                n = I.norm(scheme, str(v))
                if I.valid(scheme, n):
                    rows.append(I.row(scheme, n, asserted_by="pmc_idconv", derived_from=df,
                                      evidence={"field": key}))
    return rows


def rung_ncbi_idconv(work, ctx):
    """Wave 2 (route `ncbi-idconv`, metadata only): the NCBI ID Converter, asked only while `pmid` or `pmcid` is
    absent from the run's identifiers (the closure rule). ONE DOI per call: the survey's batching over the
    whole hunt queue needs a pass the per-work ladder does not have (not built; the cost is one request per
    work instead of one per 200)."""
    held = {s for s, _v, _via in work.get("ids") or []}
    if {"pmid", "pmcid"} <= held:
        return closure_skip("policy_refused", "the closure rule: pmid and pmcid are both already held")
    doi = work.get("doi")
    st, data, term = get_json(ctx, "ncbi-idconv", ncbi_url(doi, contact_email()))
    if st != 200 or not isinstance(data, dict):
        return service_miss("ncbi-idconv", st, term, "NCBI ID Converter")
    rows = from_idconv(data, doi)
    new = gained(work, rows, "ncbi-idconv")
    return answered("ncbi-idconv", [], ctx, work, term=term, harvest={"rows": rows, "relations": []},
                    detail="metadata only", extra={"stage_b": {"gained": [f"{s}:{v}" for s, v in new]}})


def rung_s2(work, ctx):
    """B5 + B1 (route `s2`): Semantic Scholar's record, LAST among the services (it 429s in seconds, no key —
    survey B5; LINKAGE §2.3). `externalIds` are harvested through B1's `harvest.from_s2` (an article's ArXiv is a
    `has_version` EDGE, builder-B1's deviation under `litkb-sibling-edition`) and join the run's identifiers, so
    the `arxiv` rung after it asks the arXiv copy; `openAccessPdf` is followed through B1 (`carried_files`) when
    it is not a doi.org or an arXiv URL. A 429 is an `api-error` the ladder retries once (C1a)."""
    from litkb.admit import harvest as H

    st, data, term = get_json(ctx, "s2", s2_url(work))
    if st != 200 or not isinstance(data, dict):
        return service_miss("s2", st, term, "Semantic Scholar")
    doi = work.get("doi")
    rows, rels = H.from_s2(data, doi) if doi else ([], [])
    new = gained(work, rows, "s2", rels)
    acl = ((data.get("externalIds") or {}).get("ACL") or "") if isinstance(data.get("externalIds"), dict) else ""
    if acl:
        A.found(work, [{"scheme": "acl", "value": acl}], "s2")
    oap = data.get("openAccessPdf")
    a = canon_arxiv((oap or {}).get("url") if isinstance(oap, dict) else "")
    if a:
        A.found(work, [{"scheme": "arxiv", "value": a}], "s2")
    return answered("s2", carried_files((), oap), ctx, work, term=term, harvest={"rows": rows, "relations": rels},
                    extra={"stage_b": {"gained": [f"{s}:{v}" for s, v in new],
                                       "open_access_pdf": (oap or {}).get("url") if isinstance(oap, dict) else None}})


def open_access_arxiv(work, ctx):
    """The arXiv id C1a's `open_access` rung ASKED in this ladder run, or ''. That rung asks arxiv.org/pdf/<id>
    first for the work's own arXiv id, or for the id a `10.48550/arxiv.` DOI names (acquire/open_access.py
    `fetch_open_access`), and it was asked in this run when the ladder recorded an ALLOWED pre-fetch decision for
    it (`RungContext.decisions`, written just before a rung is asked). It runs in Wave 1, before `arxiv`."""
    d = (getattr(ctx, "decisions", None) or {}).get("open_access")
    if not isinstance(d, dict) or not d.get("allowed"):
        return ""
    a = work.get("arxiv") or ""
    doi = str(work.get("doi") or "").strip().lower()
    if not a and doi.startswith("10.48550/arxiv."):
        a = doi[len("10.48550/arxiv."):]
    a = I.norm("arxiv", a) if a else ""
    return a if a and I.valid("arxiv", a) else ""


def rung_arxiv(work, ctx):
    """B1 / B10 (route `arxiv`): every arXiv id the run holds — the work's own, the target of an edition edge
    (`harvest.copy_identifiers`: an article's preprint), or one an earlier rung of this run discovered — asked
    at arxiv.org (`carried_files`). Bound, the copy is the SUBMITTED version (copy_kind `preprint`,
    guard 23), never the article's version of record. No arXiv id at all -> a `no_identifier` skip. The id the
    `open_access` rung already asked in this run is booked as asked by it, never asked a second time
    (`open_access_arxiv`; auditor-C2a round 2 F10)."""
    ids = A.ids_of(work, "arxiv")
    if not ids:
        return closure_skip("no_identifier", "no arXiv id: not the work's own, not an edition edge's, and no "
                                             "earlier rung of this run found one")
    own = open_access_arxiv(work, ctx)
    # BEGIN guard: the arXiv PDF the open_access rung asked in this run is not asked again
    if own in ids and isinstance(work, dict):
        with _ASKED_LOCK:
            work.setdefault("asked_urls", {}).setdefault(arxiv_pdf(own), "open_access")
    # END guard: the arXiv PDF the open_access rung asked in this run is not asked again
    r = fetch_candidates("arxiv", carried_files(ids), ctx, work)
    r["detail"] = "; ".join(x for x in (f"arXiv ids {', '.join(ids)}", r.get("detail") or "") if x)
    return r


#: The Stage A and Stage B rungs this builder adds, in REGISTRY ORDER — which is the wave order (the module
#: docstring): within Stage B the concurrent rungs run together, then the sequential ones in this order.
#: (route, module attribute, needs, concurrent, metadata_only). `open_access` (C1a's, concurrent) is already
#: registered. `core` (B7) is NOT BUILT: CORE_API_KEY is blank and the survey measured the v3 API answering
#: unauthenticated requests 429 / 404 (PDF-sources survey B7-RG) — its report line is `not-built:`.
RUNG_TABLE = (
    # Stage A (zero network; each asks one URL at most)
    ("eartharxiv", "stage_a.rung_eartharxiv", ("doi",), False, False),
    ("publisher-url", "stage_b_repos.rung_publisher_url", ("doi",), False, False),
    # Stage B, Wave 1 and the repository rungs keyed on the DOI alone: CONCURRENT
    ("opencitations", "stage_b.rung_opencitations", ("doi",), True, True),
    ("crossref-link", "stage_b.rung_crossref_link", ("doi",), True, False),
    ("openalex", "stage_b.rung_openalex", ("doi",), True, False),
    ("doaj", "stage_b_repos.rung_doaj", ("doi",), True, False),
    ("openaire", "stage_b_repos.rung_openaire", ("doi",), True, False),
    ("hal", "stage_b_repos.rung_hal", ("doi",), True, False),
    ("osf", "stage_b_repos.rung_osf", ("doi",), True, False),
    # Stage B, Wave 2: SEQUENTIAL, in the closure rule's dependency order
    ("datacite", "stage_b.rung_datacite", ("doi", "arxiv"), False, False),
    ("zenodo", "stage_b_repos.rung_zenodo", ("doi",), False, False),
    ("figshare", "stage_b_repos.rung_figshare", ("doi",), False, False),
    ("ncbi-idconv", "stage_b.rung_ncbi_idconv", ("doi",), False, True),
    ("s2", "stage_b.rung_s2", ("doi", "arxiv"), False, False),
    ("europepmc", "stage_b_repos.rung_europepmc", ("doi",), False, False),
    ("arxiv", "stage_b.rung_arxiv", ("doi", "arxiv"), False, False),
    ("venue", "stage_b_repos.rung_venue", ("doi", "arxiv"), False, False),
)


#: The ASK CONDITION of every rung that asks only under one (the closure rule's Wave-2 conditions and A4's template
#: condition, stated as the rung's own `closure_skip` states it). It is registered as `run.Rung.ask_condition`; a rung
#: skipped by it on EVERY row it reached asked nobody, and the report says so in a `not-asked:` line instead of a
#: yield line that asked no row (auditor-C2a round 2 F3: on live, 0 works hold a zenodo or a figshare DOI or a
#: PMCID). A rung with no entry asks every row that reaches it.
ASK_CONDITIONS = {
    "publisher-url": "a DOI prefix a Stage A publisher template names (stage_a.PUBLISHER_TEMPLATES)",
    "osf": "a DOI under an OSF preprint prefix (10.31219 / 10.31235 / 10.31234 / 10.32942)",
    "datacite": "a 10.48550 / 10.5281 / 10.6084 DOI, a DOI Crossref answered 404 for in the run, or Stage A's arXiv "
                "candidate",
    "zenodo": "a 10.5281/zenodo.<n> DOI (the work's, or a version DataCite named)",
    "figshare": "a 10.6084/m9.figshare.<n> DOI",
    "ncbi-idconv": "pmid or pmcid absent from the run's identifiers",
    "europepmc": "a PMCID held or found in the run",
    "arxiv": "an arXiv id held, reached through an edition edge, or found in the run",
    "venue": "an ACL Anthology id or a title",
}


def _lazy(dotted):
    """A rung function resolved at CALL time (`stage_b_repos.rung_osf`), so the three modules may be imported in any
    order, and a test that replaces a rung function in its module is the one the ladder calls."""
    import importlib

    mod, attr = dotted.rsplit(".", 1)

    def call(work, ctx):
        return getattr(importlib.import_module(f"litkb.acquire.{mod}"), attr)(work, ctx)
    call.__name__ = attr
    call.__qualname__ = dotted
    return call


def register_all(rungs=None):
    """Register every rung of RUNG_TABLE with the ladder (`litkb.acquire.run.register`), once. Called when this
    module is imported — and `litkb.acquire.run` imports it (S4.5 decision D19: a rung registered by import but
    never imported is invisible to `hunt`; fail closed)."""
    from litkb.acquire import run as R

    target = R.RUNGS if rungs is None else rungs
    have = {r.route for r in target}
    for route, fn, needs, concurrent, metadata_only in RUNG_TABLE:
        if route in have:
            continue
        # every rung of this module retries a transient answer once (C1a's scheduled retry): a 429 or a 5xx
        # from an identifier service is the commonest answer an unauthenticated client gets (survey B5)
        R.register(R.Rung(route, _lazy(fn), needs=needs, concurrent=concurrent, retry_transient=True,
                          metadata_only=metadata_only, ask_condition=ASK_CONDITIONS.get(route, "")), target)
    return target


register_all()

"""Stage E's shared half: WHICH dead URLs the recovery rungs are asked about (LITKB_WORKPLAN.md "### S4.5"
item 6; S4.5 builder-C2c). The three rungs are `litkb.acquire.wayback` (E1), `litkb.acquire.ia` (E3) and
`litkb.acquire.commoncrawl` (E5).

WHY A LIST OF URLS. Stage E is "the only rungs that convert a DEAD link" (Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md
§1 Stage E, the E1 row's "fixes" column: blocked, bad-file, no-oa-copy). Its input is therefore a URL some other
route expected a document at and did not get one from: the census.gov author copy Semantic Scholar names for
10.1002/wics.1317 and the IIASA copy OpenAlex names for 10.5067/doc/ceoswgcv/lpv/lc.001 both answered 404
(`phase4/qc/litkb_acq_probe_head.csv`). A rung never touches the database (the rung interface,
`litkb.acquire.run.Rung`), so the LADDER hands the URLs over on `RungContext.recovery_urls`, from two sources:

  * the ledger — `ledger_urls`, read by the loop before the first rung: every URL an earlier attempt on a
    legitimate-tier route (or the hunt's own URL path) recorded for this work and did not succeed on. This is
    what reaches a link an earlier run found dead, whose route this run skips `dead_route`;
  * this ladder run — `urls_of`, called by the loop on every answer it records: the URLs an earlier rung of the
    SAME run asked and did not succeed on (in MEASURE mode every rung is asked, S4.5 decision D9, so a Stage B
    rung's dead link reaches Stage E in the same pass). Every URL the rung ASKED, in full, is read from the
    ladder's request gate (`asked_urls`: `litkb.acquire.backoff.Gate` records each request a rung call makes),
    not only the four fields a rung dict names — a multi-location rung records the locations that failed as
    `host:code` tokens, so the IIASA 404 OpenAlex named for 10.5067/doc/ceoswgcv/lpv/lc.001 and the handle 404
    Unpaywall named for 10.1016/j.rse.2019.111492 never reached E1 in hardening-1 (referee-stage-e N1: L007,
    L054; S4.5 fix wave FX-E item 1).

WHAT IS NEVER A CANDIDATE (`eligible`), each rule for a stated reason:
  * a URL from a SHADOW-tier route, or on a host a shadow POLICY line names (`litkb-shadow-hosts`: the shadow
    tier runs only after every legitimate rung has missed; asking a legitimate archive for a shadow front's page
    would launder that ordering, and an archive's partner download URL can carry a token);
  * a URL that carries a credential (a registered secret or a `litkb.cassette.SCRUB_PARAMS` parameter — the
    Unpaywall email), or the redaction mask a stored row already carries: sending it to a third party is the
    leak X7 (S4.5 CONTRACTS, Codex finding X7) forbids;
  * a SIGNED URL (`SIGNED_URL_PARAMS`: a CDN or object-store link whose query signs it): its signature grants
    whoever holds it the object, so it is a credential too (auditor-C2c-r2 F10);
  * an archive's own URL (archive.org, commoncrawl.org): recovering a recovery URL is a loop;
  * an API endpoint or a DOI resolver (`is_api`, `RESOLVER_HOSTS`): a metadata answer, never a document an
    archive would hold a copy of (builder-C2c's rule; its host test widened by builder-FX-E on the hardening-1
    census of what E1 was asked about, `API_HOST_LABEL` / `API_PATH_FIRST_SEGMENTS` / `API_URL_PREFIXES`) — but a
    route that serves a document's bytes under an API-shaped path is a document (`API_DOCUMENT_PATHS`: InvenioRDM's
    file content, the URL Zenodo names for a file; auditor-FX-E F1);
  * anything but http(s).

WHAT A RECOVERY RUNG'S PDF MUST NOT BE (`capture_identity`, S4.5 fix wave FX-E item 3): a copy of ANOTHER work. An
archive answers for a URL, and the URL a service named can hold another document — the census.gov capture Semantic
Scholar named for 10.1002/wics.1317 is Winkler's 1993 Census chapter of the same title and author, which the binder's
title-and-first-author rule accepts and MEASURE mode credited `measured` (referee-stage-e L022). The Stage E rungs book
such a capture `hash-mismatch` ("a real PDF that is not the record's", `litkb.acquire.run.Rung`) in both modes, with
the contradiction named, so it is neither landed nor counted as a conversion.

A RELAYED design (CLAUDE.md §3.4c): UNVALIDATED until an independent referee scores Stage E on the rows the plan
names. Every constant below is builder-C2c's choice unless it names another source, and none is calibrated.
"""
import re
import urllib.parse

from litkb.acquire import policy as _policy

#: The Stage E routes (CONTRACTS route vocabulary; `policy.STAGE_OF` stages them "E").
ROUTES = ("wayback", "ia", "commoncrawl")

#: Attempt statuses whose URL is NOT dead: a success, or a row that asked nothing. Every other status (a miss,
#: a refusal, a bad file, an api-error) leaves its URLs as recovery candidates. `downloaded` is the rung
#: dict's word for a success before the loop has judged it.
LIVE_STATUSES = frozenset({"ok", "measured", "duplicate-held", "downloaded", "skipped", "budget-stop",
                           "manual-step", "quota-stop"})

#: Routes whose rows are not shadow-tier rungs yet may name a document URL: the hunt's own URL path
#: (a URL the operator or a drop-off gave, `hunt-url`, migration 0028).
EXTRA_ROUTES = ("hunt-url",)

#: An archive's own hosts (suffix match): never recovered from themselves.
ARCHIVE_HOSTS = ("archive.org", "commoncrawl.org")
#: A DOI resolver's answer is a redirect to a landing page, never an archived document (builder-C2c's rule).
RESOLVER_HOSTS = ("doi.org",)
#: A metadata API, by the FIRST LABEL of its host: `api`, or `api` and digits. builder-C2c's rule was the host
#: prefix `api.` (api.unpaywall.org, api.crossref.org, api.openalex.org, api.semanticscholar.org, api.datacite.org,
#: api.openaire.eu, api.opencitations.net, api.archives-ouvertes.fr, a publisher's TDM `api.` host ...); MEASURED on
#: hardening-1 (referee-stage-e N2; builder-FX-E's census of the 292 distinct URLs E1/E5 were asked about, from the
#: attempt rows' "asked about:" notes): 72 were `api2.openreview.net/notes/search?...` (the `venue` rung's query),
#: which that prefix misses. An API answer is not a document an archive would hold a copy of.
API_HOST_LABEL = re.compile(r"^api\d*$")
#: ... or by the FIRST SEGMENT of its path: the same census found 70 `doaj.org/api/search/articles/doi:...` and one
#: `zenodo.org/api/records/...` — a metadata API on a host that also serves pages. The FIRST segment only: a
#: repository can serve a document's bytes from a deeper `api` segment (DSpace 7's `/server/api/core/bitstreams/
#: <uuid>/content` — builder-FX-E's reading of DSpace's REST path, not checked against its documentation this
#: session), and a dead one is exactly what an archive may hold. Those 143 of 292 (49%) cost 264 of E1's 572
#: requests in hardening-1 (referee-stage-e §6) and took slots under MAX_URLS.
API_PATH_FIRST_SEGMENTS = ("api",)
#: ... or it starts with one of the ladder's own service endpoints that neither rule recognises (their hosts also
#: serve pages, and their `api` / REST segment is not the first): the NCBI ID converter
#: (`litkb.acquire.stage_b.NCBI_IDCONV`) and Europe PMC's REST search (`litkb.acquire.stage_b_repos.EUROPEPMC_CORE`).
#: The request gate hands Stage E every URL a rung asked (`asked_urls`), a service's own query included, so each
#: endpoint the ladder calls must read as an API: qc/test_litkb_fx_stage_e.py holds every Stage A/B endpoint constant
#: to `is_api` and these prefixes equal to those two constants.
API_URL_PREFIXES = ("https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/", "https://www.ebi.ac.uk/europepmc/webservices/rest/")
#: EXCEPT a path that serves a DOCUMENT'S BYTES under an API-shaped path — never an API, whatever the rules above
#: read: InvenioRDM's file-content route `api/records/<id>/files/<key>/content` (auditor-FX-E F1). It is the URL
#: Zenodo's record answer names for every file (`links.self`, the URL B14 downloads, `stage_b_repos.zenodo_files`;
#: hardening-1's recorded answer for zenodo.org/api/records/20559202 lists all 48 of its files in that shape) and the
#: Rogue Scholar PDF crossref-link LANDED for 10.64000/e6ey2-wce96 in hardening-1. MEASURED by builder-FX-E-r2: of the
#: 1,786 ladder-1 requests the host / first-segment rules call an API, exactly ONE answered a document (a PDF by type,
#: disposition or first bytes), and it is this route; the live ledger's attempt rows name no other document URL under
#: a first segment `api`. Other file routes (a draft's files; a pre-InvenioRDM Zenodo `api/files/<bucket>/<key>` —
#: builder-FX-E-r2's recollection of the legacy API, NOT checked) are in neither: not recognised, named. The record
#: itself (`api/records/<id>`), its file listing and a file's metadata stay APIs.
API_DOCUMENT_PATHS = (re.compile(r"^/api/records/[^/]+/files/[^/].*/content$"),)
#: Routes whose URLs the LADDER CONSTRUCTS rather than a service naming them: Stage A's publisher templates
#: (`publisher-url`, A4) and Stage C's rewrites and per-publisher rules (`landing`). A guess that answered 404 proves
#: the guess wrong, not a document dead, so the request gate's record of THEIR requests is not read (referee-stage-e
#: §2b: "They are constructed guesses, so leaving them out is defensible"; of the 16 dead links E1 missed in
#: hardening-1, 14 were Stage C's guesses — mdpi-res.com CDN 10, academic.oup.com `/doi/pdf/` 4 — and the other 2 were
#: the service-named L007 and L054). Their own recorded URLs (terminal, rejected, source) are read
#: as before. A LIMIT, named: a `citation_pdf_url` a real landing page asserted, that answered 404, is a page-named
#: dead link this rule also leaves out (builder-FX-E's choice).
CONSTRUCTING_ROUTES = ("publisher-url", "landing")

#: At most this many candidate URLs per work are asked, in the order they were met (builder-C2c's choice,
#: UNCALIBRATED: it bounds a Stage E rung's requests for one work; the plan's rows name ONE dead URL each).
MAX_URLS = 5

#: Query parameters that SIGN a URL (auditor-C2c-r2 F10 named `X-Amz-Signature`, `Signature` / `Policy` /
#: `Key-Pair-Id` and `sig`; the other names are the same vendors' companions: AWS SigV4 `X-Amz-Credential` /
#: `X-Amz-Security-Token`, Google Cloud Storage `X-Goog-Signature` / `X-Goog-Credential`). builder-C2c's reading of
#: those vendors' signed-URL formats, NOT checked against their documentation this session. Matched without case.
SIGNED_URL_PARAMS = frozenset({"x-amz-signature", "x-amz-credential", "x-amz-security-token", "signature", "policy",
                               "key-pair-id", "sig", "x-goog-signature", "x-goog-credential"})

#: A recovered PDF is ANOTHER WORK when the LATEST year its own text prints is more than this many years before the
#: record's year (`capture_identity`). builder-FX-E's choice, UNVALIDATED (a relayed-in-spirit rule: no survey names it;
#: the survey's page-range signal T15 was measured and does NOT separate, see `capture_identity`). What it rests on,
#: MEASURED on hardening-1 by `latest_printed_year` itself (every PDF a rung was served and the acceptance test
#: accepted: 104 (work, bytes) pairs, 97 of them bound by the binder): the census.gov capture served for
#: 10.1002/wics.1317 (2014) prints no year after 1993 (lead 21); each of the other 103 printed a year at most 1 before
#: its record's (6 at 1, 58 at 0, the rest a year at or after it — an arXiv or manuscript copy's lead). Every value
#: from 2 to 20 separates them; 10 leaves a copy a decade's lead over its publication, ten times the largest lead
#: measured, so a preprint posted years before its journal version is not refused. A PDF that prints no year at all
#: is never judged (the rule abstains). One negative row: the referee scores whether it generalises.
IDENTITY_YEAR_LEAD = 10
#: A printed year: four digits 1500-2099 standing alone. A page or volume number in that range can only RAISE the
#: latest year read, which makes the rule abstain — never refuse.
_YEAR_RE = re.compile(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)")

_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.I)
#: the redaction mask litkb.netutil.redact and litkb.cassette.scrub_url write in place of a secret
_MASK = "<KEY>"


def host_of(url):
    return (urllib.parse.urlsplit(url or "").hostname or "").lower()


def signed(url):
    """True when `url`'s query carries a parameter that signs it (`SIGNED_URL_PARAMS`)."""
    names = {k.lower() for k, _v in urllib.parse.parse_qsl(urllib.parse.urlsplit(url or "").query,
                                                          keep_blank_values=True)}
    return bool(names & SIGNED_URL_PARAMS)


def _on(host, suffixes):
    return any(host == s or host.endswith("." + s) for s in suffixes)


def is_api(url):
    """True when `url` is a metadata API endpoint: its host's first label is `api` / `api<digits>`
    (`API_HOST_LABEL`), its path's first segment is one of `API_PATH_FIRST_SEGMENTS`, or it starts with one of
    `API_URL_PREFIXES` — unless its path is a route that serves a document's bytes (`API_DOCUMENT_PATHS`)."""
    parts = urllib.parse.urlsplit(url or "")
    # BEGIN guard: an API-shaped path that serves a document's bytes is a document, never an API
    if any(rx.match(parts.path) for rx in API_DOCUMENT_PATHS):
        return False
    # END guard: an API-shaped path that serves a document's bytes is a document, never an API
    host = (parts.hostname or "").lower()
    first = host.split(".", 1)[0]
    seg = parts.path.lstrip("/").split("/", 1)[0].lower()
    hit = False
    # BEGIN guard: a metadata API's URL is recognised by its host label or its first path segment
    hit = bool(API_HOST_LABEL.match(first)) or seg in API_PATH_FIRST_SEGMENTS
    # END guard: a metadata API's URL is recognised by its host label or its first path segment
    return hit or str(url or "").startswith(API_URL_PREFIXES)


def shadow_hosts(policy=None):
    """Every host a SHADOW-tier POLICY line names (the one home of which hosts are shadow fronts)."""
    return {p.host.lower() for p in (_policy.POLICY if policy is None else policy)
            if p.tier == _policy.SHADOW and p.host not in ("*", "")}


def is_legitimate_route(route):
    """A route whose URLs may be offered to Stage E: a legitimate-tier rung, or the hunt's URL path."""
    return route in EXTRA_ROUTES or (route in _policy.STAGE_OF and _policy.STAGE_OF[route] != "shadow"
                                     and route not in ROUTES)


def eligible(url, policy=None):
    """-> (True, "") when `url` may be sent to an archive, else (False, why). The rules: module docstring."""
    from litkb.cassette import scrub_url

    u = str(url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return False, "not http(s)"
    host = host_of(u)
    if not host:
        return False, "no host"
    # BEGIN guard: a URL carrying a credential is never sent to an archive
    if _MASK in u or scrub_url(u) != u:
        return False, "carries a credential or its redaction mask"
    # END guard: a URL carrying a credential is never sent to an archive
    # BEGIN guard: a signed URL is never sent to an archive
    if signed(u):
        return False, "a signed URL (its signature is a credential)"
    # END guard: a signed URL is never sent to an archive
    # BEGIN guard: a shadow front's URL is never a recovery candidate
    if _on(host, shadow_hosts(policy)):
        return False, "a shadow front's host"
    # END guard: a shadow front's URL is never a recovery candidate
    if _on(host, ARCHIVE_HOSTS):
        return False, "an archive's own URL"
    if _on(host, RESOLVER_HOSTS):
        return False, "a DOI resolver"
    if is_api(u):
        return False, "an API endpoint"
    return True, ""


def _urls_in(value):
    """Every http(s) URL in a route dict value (a string, or a list of `tried` tokens)."""
    if isinstance(value, str):
        return [m.group(0).rstrip(".,;)") for m in _URL_RE.finditer(value)] if value.lower().startswith(
            ("http://", "https://")) else []
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out += [m.group(0).rstrip(".,;)") for m in _URL_RE.finditer(str(v))]
        return out
    return []


def asked_urls(r):
    """Every URL the rung call ASKED, in full and in the order asked, from the ladder's request gate record on the
    route dict (`r["cooldown_gate"]["observed"]`, written by `litkb.acquire.backoff.Gate.after` for each answer; its
    `asked_url`). A redirect hop (`hop`) is part of the request it follows, never a URL of its own. [] when the dict
    carries no gate record (a rung called outside the ladder).

    Only a DEAD location is handed on (S4.5 decision D54, integrator-w4; brief-FIXWAVE FX-E item 1 "pass every dead
    candidate's FULL URL"): a URL the gate observed answering 2xx on ANY of its answers is live — a service's own
    query, a page that served its bytes — and is not a recovery candidate (auditor-FX-E F1 measured 44 of ~110 newly
    handed locations in hardening-1 answering 2xx, on 26 works). A transport failure (status 0) and every non-2xx
    answer are dead. The rung's own fields (`urls_of`: rejected / source / terminal / `tried`) are not filtered here."""
    observed = [o for o in (((r or {}).get("cooldown_gate") or {}).get("observed") or [])
                if isinstance(o, dict) and not o.get("hop")]
    live = set()                # the unguarded default: every asked URL is handed on, live or dead
    # BEGIN guard: a location the rung observed answering 2xx is live, never a recovery candidate
    live = {o.get("asked_url") for o in observed if _live_answer(o)}
    # END guard: a location the rung observed answering 2xx is live, never a recovery candidate
    out = []
    for o in observed:
        u = o.get("asked_url")
        if u and u not in live and u not in out:
            out.append(u)
    return out


def _is_2xx(code):
    try:
        return 200 <= int(code or 0) < 300
    except (TypeError, ValueError):
        return False


CHALLENGE_SUB = "challenge_or_bot_check"


def _live_answer(o):
    """One request-gate answer (`cooldown_gate.observed`) -> did it show a LIVE location? A 2xx answer, unless THE one
    challenge detector called it a challenge (`challenge_2xx`, written by `litkb.acquire.backoff.Gate.after`): S4.5
    decision D62 - "a 2xx answer TYPED a challenge ... is NOT live - its location stays a Stage E candidate (the
    page's content was never reachable to us)". A real 2xx page stays live (D54, D60)."""
    live = _is_2xx(o.get("status"))
    # BEGIN guard: a challenge served at 2xx is not a live location; it stays a Stage E candidate
    live = live and not o.get("challenge_2xx")
    # END guard: a challenge served at 2xx is not a live location; it stays a Stage E candidate
    return live


def live_urls(r, sub_status=None):
    """Every location ONE rung call observed answering 2xx with a real page (S4.5 decisions D54, D60, D62): from the
    request gate's record (`cooldown_gate.observed`, non-hop answers, `_live_answer`) the URL as asked AND, when a
    redirect chain ended elsewhere, the URL that gave the answer (`url`, recorded without its query); and the rung's
    own `terminal` when its `status_code` is 2xx - unless the answer is typed a challenge (`sub_status`: the ladder's
    typing of this answer, the one `run._record_result` writes on the row - never re-read from the rung's dict, so the
    row and the candidate rule cannot disagree) or the gate's detector called that very answer one (D62: a challenge
    at 2xx is not live). A set of strings; empty for a dict with no such record."""
    observed = [o for o in (((r or {}).get("cooldown_gate") or {}).get("observed") or [])
                if isinstance(o, dict) and not o.get("hop")]
    live, challenged = set(), set()
    for o in observed:
        if _live_answer(o):
            live.add(o.get("asked_url"))
            if o.get("url") and o.get("url") != (o.get("asked_url") or "").split("?", 1)[0]:
                live.add(o.get("url"))
        elif _is_2xx(o.get("status")):
            challenged.update({o.get("asked_url"), o.get("url")})
    terminal = (r or {}).get("terminal") or {}
    typed = sub_status
    terminal_live = bool(terminal.get("url") and _is_2xx(terminal.get("status_code")))
    # BEGIN guard: a rung answer typed a challenge leaves its 2xx terminal a Stage E candidate
    terminal_live = terminal_live and typed != CHALLENGE_SUB and terminal.get("url") not in challenged
    # END guard: a rung answer typed a challenge leaves its 2xx terminal a Stage E candidate
    if terminal_live:
        live.add(terminal.get("url"))
    live.discard(None)
    live.discard("")
    return live


def urls_of(route, r, status, sub_status=None):
    """The recovery candidates one ANSWER names: -> [{"url", "route", "status", "origin": "run"}].

    Called by the ladder (`litkb.acquire.run._record_result`) with the rung's route dict and the status the
    loop RECORDED. A success or a skip names none; a shadow-tier or Stage E route names none. The rung's own
    fields first (rejected, source, terminal, URL-shaped `tried` tokens), then every URL the rung ASKED
    (`asked_urls`) unless the route constructs its URLs (`CONSTRUCTING_ROUTES`).

    None of them is a location this rung call observed answering 2xx (`live_urls`; S4.5 decision D60, integrator-w4
    r2): D54's rule covers the rung's OWN rejected / terminal / source URL as well as the gate's — a live 2xx page
    (a bad-file HTML page, a landing page) is not a recovery candidate. Measured on the
    whole-run replay: L094's open.bu.edu page, L108's nature.com article page and L125's journals.lww.com page (each
    recorded answering 200) reached E1 through these fields after D54 (auditor-cand4 N5). A challenge served at
    2xx is NOT live (S4.5 decision D62): `sub_status` is the ladder's typing of this answer
    (`litkb.acquire.run._record_result`), and a row typed `challenge_or_bot_check` keeps its location a candidate."""
    if status in LIVE_STATUSES or not is_legitimate_route(route):
        return []
    terminal = (r or {}).get("terminal") or {}
    found = []
    for value in ((r or {}).get("rejected_url"), (r or {}).get("source_url"), terminal.get("url"),
                  (r or {}).get("tried")):
        found += _urls_in(value)
    # BEGIN guard: every URL a service named and a rung asked reaches Stage E in full
    if route not in CONSTRUCTING_ROUTES:
        found += asked_urls(r)
    # END guard: every URL a service named and a rung asked reaches Stage E in full
    live = set()                # the unguarded default: the rung's own fields are handed on whatever they answered
    # BEGIN guard: a rung's own location that answered 2xx is live, never a recovery candidate
    live = live_urls(r, sub_status)
    # END guard: a rung's own location that answered 2xx is live, never a recovery candidate
    return [{"url": u, "route": route, "status": status, "origin": "run"} for u in found if u not in live]


_LEDGER_SQL = """
SELECT route, status, terminal_url, detail->>'source_url', detail->>'rejected_url', detail->'tried',
       terminal_status_code, sub_status
  FROM litkb.acquisition_attempts
 WHERE work_id = %s
 ORDER BY at, id
"""


def _ledger_live_type(sub_status):
    """An earlier attempt's recorded `sub_status` -> may its 2xx terminal be read as live? Not when the row is typed a
    challenge (S4.5 decision D62: a challenge at 2xx is not live; the ledger carries the typing, 0033)."""
    live = True
    # BEGIN guard: an earlier attempt typed a challenge leaves its 2xx terminal a Stage E candidate
    live = sub_status != CHALLENGE_SUB
    # END guard: an earlier attempt typed a challenge leaves its 2xx terminal a Stage E candidate
    return live


def ledger_urls(conn, work_id):
    """The recovery candidates this work's EARLIER attempts recorded: -> [{"url", "route", "status",
    "origin": "ledger"}], oldest first. Read by the ladder on its own connection (a rung never reads the
    database). The stored URLs were redacted at write (`run.record_attempt`); a masked one is refused by
    `eligible`.

    A URL any earlier attempt of this work RECORDED answering 2xx (`terminal_url` with a 2xx `terminal_status_code`,
    the one answer the ledger keeps) is live and is not a candidate (S4.5 decision D60): hardening-1's own rows hold
    L094's, L108's and L125's 200 pages as terminals of failed attempts, so without this the live hardening-2 run
    would hand them to E1 from the ledger although the in-run rule (`urls_of`) no longer does. A row typed
    `challenge_or_bot_check` is not live whatever its code (S4.5 decision D62)."""
    rows = conn.execute(_LEDGER_SQL, (work_id,)).fetchall()
    live = set()                # the unguarded default: a recorded 2xx terminal is handed on like a dead one
    # BEGIN guard: an earlier attempt's location recorded answering 2xx is live, never a recovery candidate
    live = {row[2] for row in rows if row[2] and _is_2xx(row[6]) and _ledger_live_type(row[7])}
    # END guard: an earlier attempt's location recorded answering 2xx is live, never a recovery candidate
    out = []
    for route, status, terminal_url, source_url, rejected_url, tried, _code, _sub in rows:
        if status in LIVE_STATUSES or not is_legitimate_route(route):
            continue
        for value in (rejected_url, source_url, terminal_url, tried if isinstance(tried, list) else None):
            out += [{"url": u, "route": route, "status": status, "origin": "ledger"} for u in _urls_in(value)
                    if u not in live]
    return out


def candidates(entries, policy=None, limit=None):
    """-> (urls, refused): the distinct eligible URLs among `entries` (the ladder's `recovery_urls`), in the
    order they were met, at most `limit` (MAX_URLS); `refused` names every URL left out and why."""
    limit = MAX_URLS if limit is None else limit
    urls, refused, seen = [], [], set()
    for e in entries or []:
        u = str(e.get("url") if isinstance(e, dict) else e).strip()
        if not u or u in seen:
            continue
        seen.add(u)
        ok, why = eligible(u, policy)
        if not ok:
            refused.append({"url": u, "why": why})
        elif len(urls) >= limit:
            refused.append({"url": u, "why": f"over the {limit}-URL cap (recovery.MAX_URLS)"})
        else:
            urls.append(u)
    return urls, refused


def register(rung):
    """Register a Stage E rung through builder-C1a's registry (`litkb.acquire.run.register`) and keep the Stage E
    rungs in `ROUTES` order (E1, E3, E5) whichever of their modules happened to be imported first — the registry
    orders a stage by registration, and a module imported before `litkb.acquire.run` registers AFTER the ones
    `run` imports itself (measured: importing `litkb.acquire.wayback` first put it last)."""
    from litkb.acquire import run as _run

    _run.register(rung)
    at = [i for i, r in enumerate(_run.RUNGS) if r.route in ROUTES]
    for i, r in zip(at, sorted((_run.RUNGS[i] for i in at), key=lambda r: ROUTES.index(r.route))):
        _run.RUNGS[i] = r
    return rung


def with_candidates(r, urls, refused):
    """The rung dict with the URLs it was asked about (and how many were left out) on its `detail` note — the
    one key of a rung dict the ladder copies into every attempt row (`run.DETAIL_KEYS`)."""
    note = r.get("detail") or ""
    parts = [note] if note else []
    parts.append("asked about: " + ", ".join(urls))
    if refused:
        parts.append(f"{len(refused)} URL(s) not eligible (" + "; ".join(x["why"] for x in refused[:5]) + ")")
    r["detail"] = "; ".join(parts)
    return r


def no_candidates(route, refused):
    """The rung dict for a Stage E rung with nothing to ask: a SKIP (nothing was requested, nothing spent),
    sub-status `no_identifier` — the identifier a recovery rung needs is a dead document URL, and no earlier
    rung or attempt named one (docs/SCHEMAS.md, the Stage E section)."""
    note = ("no dead document URL to recover: no earlier rung of this run and no earlier attempt named one"
            if not refused else "every URL named was refused: " + "; ".join(
                f"{x['why']}" for x in refused[:5]))
    return {"status": "skipped", "sub_status": "no_identifier", "detail": f"{route}: {note}"}


def latest_printed_year(pdf):
    """-> (the latest year the PDF's text prints, pages read), or (None, pages) when it prints none or cannot be
    read. The text is THE acceptance test's reader (`litkb.acquire.accept.page_texts`, pdfium over the bytes in
    memory; nothing written)."""
    from litkb.acquire import accept as _accept

    texts, _err = _accept.page_texts(pdf)
    if not texts:
        return None, 0
    years = [int(y) for t in texts for y in _YEAR_RE.findall(t or "")]
    return (max(years) if years else None), len(texts)


def capture_identity(work, pdf):
    """-> "" when nothing the recovered PDF prints contradicts the work's record, else the contradiction (one
    sentence naming its facts). The one fact read: the LATEST year the PDF prints against the record's year
    (`IDENTITY_YEAR_LEAD`) — a copy of a work, in any version, prints years up to about its own writing, and a
    document whose every printed year is long before the work was published is another document at that URL.

    What was measured and NOT used (hardening-1, the same 104 accepted hits): the binder's title-and-first-author
    rule binds the census capture to 10.1002/wics.1317 (same title, same author: `litkb.admit.binding.bind_any`,
    verdict bound); the acceptance test's page-range fact (T15, `accept.page_range_identity`) reads the census
    capture `long` (38 pages against 313-325) — and reads 13 of the run's `ok` landings, each bound by the binder,
    `long` too (arXiv and manuscript copies, up to 51 pages against a 13-page range), so `long` cannot say another
    work. Abstains (-> "") when the record has no year, the PDF has no readable text, or it prints no year."""
    try:
        year = int((work or {}).get("year") or 0)
    except (TypeError, ValueError):
        year = 0
    if not year or not pdf:
        return ""
    latest, pages = latest_printed_year(pdf)
    if latest is None:
        return ""
    lead = year - latest
    contradicted = False
    # BEGIN guard: a recovered PDF whose printed years all fall long before the record's year is another work
    contradicted = lead > IDENTITY_YEAR_LEAD
    # END guard: a recovered PDF whose printed years all fall long before the record's year is another work
    if not contradicted:
        return ""
    return (f"not the work: the {pages}-page PDF prints no year after {latest}, {lead} years before the record's "
            f"{year} (recovery.capture_identity, IDENTITY_YEAR_LEAD {IDENTITY_YEAR_LEAD})")


def checked_capture(work, r):
    """A Stage E rung's answer with the identity rule applied: a `downloaded` PDF that `capture_identity`
    contradicts becomes `hash-mismatch` — "a real PDF that is not the record's" (`litkb.acquire.run.Rung`), a status
    a route returns WITH bytes (`litkb.quarantine.REASONS`) — with its bytes kept (the ladder quarantines them in
    acquire mode and names their sha in MEASURE mode) and the contradiction as its `reason`. Both modes: neither a
    landing nor a `measured` conversion. Any other answer passes unchanged."""
    if (r or {}).get("status") != "downloaded" or not r.get("pdf"):
        return r
    why = capture_identity(work, r["pdf"])
    if why:
        r["status"] = "hash-mismatch"
        r["reason"] = why
        r["detail"] = "; ".join(x for x in (r.get("detail") or "", why) if x)
    return r

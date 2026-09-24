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
    rung's dead link reaches Stage E in the same pass).

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
  * an API endpoint or a DOI resolver (`API_HOST_PREFIXES`, `RESOLVER_HOSTS`): a metadata answer, never a
    document an archive would hold a copy of (builder-C2c's rule, stated, not measured);
  * anything but http(s).

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
#: Host prefixes of the metadata APIs the ladder asks (api.unpaywall.org, api.crossref.org, api.openalex.org,
#: api.semanticscholar.org, api.datacite.org, a publisher's TDM `api.` host ...): an API answer is not a
#: document. A heuristic on the host NAME (builder-C2c's rule, not measured on litkb's rows).
API_HOST_PREFIXES = ("api.",)

#: At most this many candidate URLs per work are asked, in the order they were met (builder-C2c's choice,
#: UNCALIBRATED: it bounds a Stage E rung's requests for one work; the plan's rows name ONE dead URL each).
MAX_URLS = 5

#: Query parameters that SIGN a URL (auditor-C2c-r2 F10 named `X-Amz-Signature`, `Signature` / `Policy` /
#: `Key-Pair-Id` and `sig`; the other names are the same vendors' companions: AWS SigV4 `X-Amz-Credential` /
#: `X-Amz-Security-Token`, Google Cloud Storage `X-Goog-Signature` / `X-Goog-Credential`). builder-C2c's reading of
#: those vendors' signed-URL formats, NOT checked against their documentation this session. Matched without case.
SIGNED_URL_PARAMS = frozenset({"x-amz-signature", "x-amz-credential", "x-amz-security-token", "signature", "policy",
                               "key-pair-id", "sig", "x-goog-signature", "x-goog-credential"})

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
    if host.startswith(API_HOST_PREFIXES):
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


def urls_of(route, r, status):
    """The recovery candidates one ANSWER names: -> [{"url", "route", "status", "origin": "run"}].

    Called by the ladder (`litkb.acquire.run._record_result`) with the rung's route dict and the status the
    loop RECORDED. A success or a skip names none; a shadow-tier or Stage E route names none."""
    if status in LIVE_STATUSES or not is_legitimate_route(route):
        return []
    terminal = (r or {}).get("terminal") or {}
    found = []
    for value in ((r or {}).get("rejected_url"), (r or {}).get("source_url"), terminal.get("url"),
                  (r or {}).get("tried")):
        found += _urls_in(value)
    return [{"url": u, "route": route, "status": status, "origin": "run"} for u in found]


_LEDGER_SQL = """
SELECT route, status, terminal_url, detail->>'source_url', detail->>'rejected_url', detail->'tried'
  FROM litkb.acquisition_attempts
 WHERE work_id = %s
 ORDER BY at, id
"""


def ledger_urls(conn, work_id):
    """The recovery candidates this work's EARLIER attempts recorded: -> [{"url", "route", "status",
    "origin": "ledger"}], oldest first. Read by the ladder on its own connection (a rung never reads the
    database). The stored URLs were redacted at write (`run.record_attempt`); a masked one is refused by
    `eligible`."""
    out = []
    for route, status, terminal_url, source_url, rejected_url, tried in conn.execute(_LEDGER_SQL,
                                                                                     (work_id,)).fetchall():
        if status in LIVE_STATUSES or not is_legitimate_route(route):
            continue
        for value in (rejected_url, source_url, terminal_url, tried if isinstance(tried, list) else None):
            out += [{"url": u, "route": route, "status": status, "origin": "ledger"} for u in _urls_in(value)]
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

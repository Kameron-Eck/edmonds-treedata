"""Stage E1 — the Wayback Machine: a dead URL's archived capture, as the RAW bytes (LITKB_WORKPLAN.md "### S4.5"
item 6; S4.5 builder-C2c; route `wayback`).

    r = fetch_wayback(urls, client, pacer=..., decide=...)     # the rung dict (litkb.acquire.run.Rung)

For each candidate URL (`litkb.acquire.recovery`, the ladder's `recovery_urls`), in order, until one yields a PDF:

  1. the AVAILABILITY API (`AVAILABILITY`): the closest capture. If its archived status is 200 it is the first
     capture to fetch.
  2. the capture fetched with a RAW-BYTES modifier (`RAW_MODIFIERS`): `id_` first, then `if_` for the same capture.
     WITHOUT a raw modifier the Wayback Machine serves its own HTML page around the archived bytes, and the ladder
     would store that wrapper and book another `bad-file` (survey §1 E1: "the raw-bytes modifier is MANDATORY";
     round 1 gives `id_`, round 2 adds `if_` — Zotero's `Fatcat.js` rewrites `/web/<ts>/` to `/web/<ts>if_/`;
     "carry both").
  3. when the availability capture gave no PDF: the CDX index (`CDX`), filtered to archived status 200 and MIME
     application/pdf, collapsed on digest (the survey's E1 query), newest capture first, skipping one already
     fetched; at most `CAPTURES_PER_URL` captures per URL in all.

THE ANSWER (the rung dict; the ladder records, types, lands or measures it):
  * a PDF                      -> `downloaded` (the bytes go through THE acceptance test, `run._land`) — unless the
                                  PDF's own printed dates contradict the work's record (`identity`,
                                  `recovery.capture_identity`; S4.5 fix wave FX-E item 3, referee-stage-e L022's
                                  census capture): that capture is checked WHERE IT IS FOUND and E1 moves on to the
                                  next candidate URL (S4.5 decision D55, integrator-w4) — a wrong-work capture never
                                  ends E1 before a later candidate's right copy is tried. Only when no candidate
                                  gives the work: `hash-mismatch`, the first wrong-work bytes kept, never landed and
                                  never `measured`
  * a 200 capture that is not a PDF, and no PDF anywhere
                               -> `bad-file`, the first such body KEPT in `rejected` (the ladder quarantines and
                                  the acceptance test types it — the wrapper page is `html_response`)
  * a transient answer (0, 408, 429, 5xx) from any step
                               -> `api-error`, STOPPING at once with that response as the terminal, so the ladder's
                                  one scheduled retry honours its `Retry-After` (backoff.retry_after_s) and the
                                  route's AIMD pacing multiplies (survey §1 E1: "CDX gave 503 and a 40 s timeout —
                                  back off hard"; CONTRACTS X7: honour Retry-After)
  * a PROVEN absence of every URL
                               -> `blocked` / `not_found` (the plan's words for E1's negative: "must end `not_found`
                                  at E1"; `not_found` is a `blocked` sub-status in the 0033 vocabulary, and a
                                  `blocked` row is dead for the route within a run, then back-off governs). PROVEN
                                  means: the availability API answered 200 in its own shape, the CDX index answered
                                  200 with no capture row, and the closest capture was no usable 200 snapshot
                                  (auditor-C2c-r2 F3: a refusal is not an absence). What it proves is NO USABLE
                                  SNAPSHOT — the CDX query is filtered to `statuscode:200` and `mimetype:application/pdf`,
                                  so a URL archived only as a redirect or an HTML page ends here too — never "never
                                  archived" (auditor-C2c round 3 F5; integrator-w2)
  * anything short of that proof (a 401/403/404 from the availability API or CDX, a body that is not their answer,
    an indexed capture the archive would not serve, a host the policy refused for one URL)
                               -> `api-error`, `retriable` false, the detail naming each URL's missing proof. Never
                                  `not_found`: an archive refusing this client must not read as "never archived"
  * every host refused by the pre-fetch policy -> `skipped` / `policy_refused`

A RELAYED design (CLAUDE.md §3.4c): VERIFIED in other codebases by the survey (`jsvine/waybackpack@c5507a0`,
`edgi-govdata-archiving/wayback`, Zotero `Fatcat.js@c830037`), UNVALIDATED here until an independent referee
scores it on the rows `qc/instruments/litkb_hardening_c2c.py` grades (`WAYBACK_ROWS`: the plan's census.gov row is
another work's copy, its IIASA row is archived and E1's real positive). Stdlib only.
"""
import datetime
import json
import urllib.parse

from litkb.acquire import accept as _accept
from litkb.acquire import recovery as _recovery
from litkb.acquire import run as _run

ROUTE = "wayback"
#: The availability API (survey §1 E1: "Availability API answers 200").
AVAILABILITY = "https://archive.org/wayback/available"
#: The CDX server (survey §1 E1's query: statuscode 200, mimetype application/pdf, collapse on digest).
CDX = "https://web.archive.org/cdx/search/cdx"
#: A capture: web.archive.org/web/<14-digit timestamp><modifier>/<original URL>.
CAPTURE = "https://web.archive.org/web/{ts}{mod}/{url}"
#: The raw-bytes modifiers, in the order they are tried (survey §1 E1 + the E1-CORRECTION row: `id_` from round 1,
#: `if_` from round 2; "carry both").
RAW_MODIFIERS = ("id_", "if_")
#: At most this many distinct captures are fetched per URL (the availability API's closest + one CDX capture).
#: builder-C2c's choice, UNCALIBRATED: it bounds the requests one dead URL costs.
CAPTURES_PER_URL = 2
#: The CDX rows asked for (newest are wanted; the server answers oldest first, so `limit=-N` asks for the LAST N,
#: the CDX server's documented negative limit). builder-C2c's choice, UNCALIBRATED.
CDX_ROWS = 5
#: What the capture fetch asks for. The same Accept the open-access route sends for a PDF (litkb.acquire.open_access).
PDF_ACCEPT = "application/pdf,*/*;q=0.5"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def availability_url(url):
    return AVAILABILITY + "?" + urllib.parse.urlencode({"url": url})


def cdx_url(url):
    q = [("url", url), ("output", "json"), ("filter", "statuscode:200"), ("filter", "mimetype:application/pdf"),
         ("collapse", "digest"), ("limit", str(-CDX_ROWS))]
    return CDX + "?" + urllib.parse.urlencode(q)


def capture_url(ts, url, modifier):
    """The capture URL. `modifier` "" is the Wayback Machine's own HTML page around the capture."""
    return CAPTURE.format(ts=ts, mod=modifier, url=url)


def parse_availability(body):
    """-> {"timestamp", "status", "url"} of the closest capture, or None (no capture, or not JSON)."""
    try:
        data = json.loads((body or b"").decode("utf-8", "replace"))
    except ValueError:
        return None
    closest = ((data or {}).get("archived_snapshots") or {}).get("closest") if isinstance(data, dict) else None
    if not isinstance(closest, dict) or not closest.get("timestamp"):
        return None
    return {"timestamp": str(closest["timestamp"]), "status": str(closest.get("status") or ""),
            "url": str(closest.get("url") or "")}


def parse_cdx(body):
    """-> [{"timestamp", "original", "mimetype", "statuscode", "digest"}] from the CDX JSON output (a header row,
    then one row per capture), NEWEST FIRST. [] for an empty or unreadable answer."""
    try:
        rows = json.loads((body or b"").decode("utf-8", "replace") or "[]")
    except ValueError:
        return []
    if not isinstance(rows, list) or len(rows) < 2 or not isinstance(rows[0], list):
        return []
    head = [str(h) for h in rows[0]]
    out = [dict(zip(head, [str(v) for v in r])) for r in rows[1:] if isinstance(r, list)]
    return sorted((c for c in out if c.get("timestamp")), key=lambda c: c["timestamp"], reverse=True)


def availability_answered(body):
    """True when `body` is the availability API's own answer: a JSON object carrying `archived_snapshots` (an
    object, `{}` when the API holds no capture — its documented shape, and the one the recording shows). Anything
    else (an HTML error page, an empty body) proves nothing about the URL."""
    try:
        data = json.loads((body or b"").decode("utf-8", "replace"))
    except ValueError:
        return False
    return isinstance(data, dict) and isinstance(data.get("archived_snapshots"), dict)


def cdx_answered_no_row(body):
    """True when `body` is the CDX server's answer with NO capture row: `[]`, a header row alone, or an empty body.
    Which of those the live server sends for no result was never recorded (no CDX request was: auditor-C2c-r2 F9),
    so all three count; a non-empty body that is not a JSON list proves nothing."""
    text = (body or b"").decode("utf-8", "replace").strip()
    if not text:
        return True
    try:
        rows = json.loads(text)
    except ValueError:
        return False
    return isinstance(rows, list) and len(rows) <= 1


def _transient(st):
    """A transient answer (litkb.acquire.backoff's own rule: 0, 408, 429, every 5xx)."""
    from litkb.acquire import backoff

    return backoff.is_transient_code(st)


class _Ask:
    """One rung call's requests: every status in order, the tokens, the terminal response, the policy decisions."""

    def __init__(self, client, pacer, decide):
        self.client, self.pacer, self.decide = client, pacer, decide
        self.codes, self.tried, self.policy = [], [], []
        self.terminal = None
        self.refused_hosts = set()

    def get(self, url, accept, token, headers=None):
        """-> (status, headers, body), or None when the pre-fetch policy refuses the host (recorded, not asked)."""
        host = _recovery.host_of(url)
        if self.decide is not None:
            d = self.decide(host)
            detail = d.as_detail() if hasattr(d, "as_detail") else dict(d)
            if detail not in self.policy:
                self.policy.append(detail)
            # BEGIN guard: a Stage E request is asked only when the pre-fetch policy allows its host
            if not detail.get("allowed"):
                self.refused_hosts.add(host)
                self.tried.append(f"{token}=policy-refused")
                return None
            # END guard: a Stage E request is asked only when the pre-fetch policy allows its host
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


def fetch_wayback(urls, client, *, pacer=None, decide=None, identity=None):
    """-> the rung dict for these candidate URLs (module docstring). `decide(host)` is the pre-fetch policy
    (`RungContext.decide("wayback", host)`); None asks without one (a unit test's stub client). `identity(pdf)` ->
    "" or the contradiction (`recovery.capture_identity` for the work, S4.5 decision D55): applied to EVERY captured
    PDF where it is found; None judges nothing (a unit test's)."""
    ask = _Ask(client, pacer, decide)
    served_html = None          # (body, capture url, terminal) of the first 200 capture that was not a PDF
    wrong_work = None           # (body, capture url, detail, why, terminal): the first captured PDF of ANOTHER work (D55)
    captures_seen = 0
    unproven = []               # (url, why) for every URL whose answers do not PROVE it was never archived
    for url in urls:
        another_work = False    # this candidate URL's capture was a PDF of another work: move on (D55)
        tried_here = set()
        indexed = set()         # captures the availability API or the CDX index named for this URL
        order = []
        missing = []            # what this URL's proof of absence lacks (empty: proven)
        got = ask.get(availability_url(url), "application/json", "availability")
        if got is None:
            unproven.append((url, "the availability API's host was refused by the policy"))
            continue
        st, _hd, body = got
        if _transient(st):
            return _result(ask, status="api-error", retriable=True,
                           detail=f"the availability API answered {st}: backing off (Retry-After honoured)")
        if st != 200 or not availability_answered(body):
            missing.append(f"the availability API answered {st} without its answer")
        snap = parse_availability(body) if st == 200 else None
        if snap and snap["status"] == "200":
            order.append(snap["timestamp"])
            indexed.add(snap["timestamp"])
        cdx_asked = False
        while True:
            if not order and not cdx_asked:
                cdx_asked = True
                got = ask.get(cdx_url(url), "application/json", "cdx")
                if got is None:
                    missing.append("the CDX host was refused by the policy")
                    break
                st, _hd, body = got
                if _transient(st):
                    return _result(ask, status="api-error", retriable=True,
                                   detail=f"the CDX server answered {st}: backing off (Retry-After honoured)")
                if st != 200 or not (cdx_answered_no_row(body) or parse_cdx(body)):
                    missing.append(f"the CDX server answered {st} without its answer")
                found = [c["timestamp"] for c in parse_cdx(body)] if st == 200 else []
                indexed.update(found)
                order += [ts for ts in found if ts not in tried_here and ts not in order]
            if not order or len(tried_here) >= CAPTURES_PER_URL:
                break
            ts = order.pop(0)
            tried_here.add(ts)
            captures_seen += 1
            for mod in RAW_MODIFIERS:
                cap = capture_url(ts, url, mod)
                got = ask.get(cap, PDF_ACCEPT, f"capture {ts}{mod or '(wrapper)'}")
                if got is None:
                    break
                st, hd, body = got
                if _transient(st):
                    return _result(ask, status="api-error", retriable=True,
                                   detail=f"the capture answered {st}: backing off (Retry-After honoured)")
                if st == 200 and _accept.quick_magic(body):
                    why = ""
                    # BEGIN guard: a recovered capture whose own dates contradict the record is never a conversion
                    # (S4.5 fix wave FX-E item 3; decision D55: judged per candidate, where the capture is found)
                    why = identity(body) if identity is not None else ""
                    # END guard: a recovered capture whose own dates contradict the record is never a conversion
                    if not why:
                        return _result(ask, status="downloaded", pdf=body, source_url=cap, kind="pdf",
                                       detail=f"archived copy of {url} captured {ts}")
                    if wrong_work is None:
                        wrong_work = (body, cap, f"archived copy of {url} captured {ts}: {why}", why,
                                      dict(ask.terminal))
                    another_work = True
                    break
                if st == 200 and body and served_html is None:
                    served_html = (body, cap, dict(ask.terminal))
            if another_work:        # this URL's capture is another work's: its other captures are not asked
                break
        if another_work:
            continue
        if not cdx_asked:
            missing.append("the CDX index was never asked")
        if indexed:
            missing.append(f"{len(indexed)} capture(s) indexed, none served a file")
        if missing:
            unproven.append((url, "; ".join(missing)))
    if wrong_work is not None:
        # no candidate gave the work: the first wrong-work PDF, its bytes kept (the ladder quarantines them in acquire
        # mode and names their sha in MEASURE mode) — "a real PDF that is not the record's" (`run.Rung`)
        body, cap, detail, why, terminal = wrong_work
        return _result(ask, status="hash-mismatch", pdf=body, source_url=cap, kind="pdf", reason=why, detail=detail,
                       terminal=terminal)
    if served_html is not None:
        body, cap, terminal = served_html
        return _result(ask, status="bad-file", rejected=body, rejected_url=cap, terminal=terminal,
                       detail="the archive served a page, not the PDF, for every capture it holds")
    if ask.refused_hosts and not ask.codes:
        return _result(ask, status="skipped", sub_status="policy_refused",
                       detail="the pre-fetch policy refused every Stage E1 host")
    not_proven = []
    # BEGIN guard: only a PROVEN absence is booked not_found
    not_proven = unproven
    # END guard: only a PROVEN absence is booked not_found
    if not_proven:
        return _result(ask, status="api-error", retriable=False,
                       detail="the Wayback answers do not prove the URL was never archived: " + "; ".join(
                           f"{u} ({why})" for u, why in not_proven))
    sub = None
    # BEGIN guard: a URL the Wayback Machine never captured is booked not_found
    sub = "not_found"
    # END guard: a URL the Wayback Machine never captured is booked not_found
    return _result(ask, status="blocked", sub_status=sub, retriable=False,
                   detail=f"no archived capture of {len(urls)} URL(s): the availability API and the CDX index "
                          f"both answered with none ({captures_seen} capture(s) fetched)")


def _rung(work, ctx):
    urls, refused = _recovery.candidates(ctx.recovery_urls)
    if not urls:
        return _recovery.no_candidates(ROUTE, refused)
    # S4.5 fix wave FX-E item 3 (referee-stage-e L022): a capture of ANOTHER work is neither landed nor measured —
    # judged per candidate inside `fetch_wayback` (S4.5 decision D55), so a later candidate's right copy is still tried
    r = fetch_wayback(urls, ctx.clients.get(ROUTE) or _client(), pacer=ctx.pacer,
                      decide=lambda host: ctx.decide(ROUTE, host),
                      identity=lambda pdf: _recovery.capture_identity(work, pdf))
    return _recovery.with_candidates(r, urls, refused)


def _client():
    from litkb.netutil import Client

    return Client(base="")


#: registered through builder-C1a's rung registry (S4.5 decision D19: `litkb.acquire.run` imports this module).
#: Sequential, not concurrent: in acquire mode the first Stage E rung that lands a file stops the others (a
#: builder-C2c choice; in MEASURE mode every rung is asked either way). `retry_transient`: one scheduled in-run
#: retry of a transient answer, after its Retry-After.
RUNG = _recovery.register(_run.Rung(ROUTE, _rung, needs=("doi", "arxiv"), concurrent=False, retry_transient=True))

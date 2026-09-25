"""Stage E3 — Internet Archive items: an archived scan or upload of the work itself (LITKB_WORKPLAN.md "### S4.5"
item 6; S4.5 builder-C2c; route `ia`).

    r = fetch_ia(work, client, pacer=..., decide=...)     # the rung dict (litkb.acquire.run.Rung)

  1. ITEM SEARCH (`SEARCH`, the advancedsearch API): the work's DOI as an `external-identifier` (`urn:doi:<doi>`),
     OR its title as a phrase with the first author's surname as a creator; texts only; `ROWS` hits.
  2. IDENTITY, before anything is fetched from an item: a hit is taken only if it carries the DOI, or its title
     folds to one of the work's title forms AND its creator names the first author (`litkb.admit.binding`'s
     `fold_tokens` / `author_on_page`, the binder's own token rules). The bytes are bound later all the same.
  3. THE ITEM'S METADATA (`METADATA`), BEFORE any download (CONTRACTS X7; survey §1 E3: "reject `is_dark` early;
     treat a lending-restricted item as `blocked`, not `not-found`"):
       `is_dark`                           -> the item is withdrawn: skipped, never downloaded
       lending restriction (`access-restricted-item`, or a lending collection, `LENDING_COLLECTIONS`)
                                           -> `blocked` / `identity_required` (a loan needs a borrower's login),
                                              never downloaded
  4. A PDF FILE of the item (`.pdf`, not `private`; the uploaded original first), downloaded from `DOWNLOAD`.

THE ANSWER: a PDF -> `downloaded`; a 200 download that is not a PDF -> `bad-file`, kept; a transient answer ->
`api-error` at once (Retry-After honoured by the ladder); a lending-restricted item and nothing better ->
`blocked`/`identity_required`; a download REFUSED (401/403) and nothing better -> `blocked`, typed by the ledger's
own rule on that one response (`litkb.acquire.ledger.type_blocked`: a 401 is `identity_required`, a 403 is checked
for a challenge signature first — CONTRACTS X7 "do not treat 401 like 403"); items identified but none holding a
PDF it would serve (no PDF listed, or the listed PDF answered 404/410) -> `not-in-archive`/`no_pdf_link`; no item
identified (or only dark ones) -> `not-in-archive`/`not_in_corpus`. Only the search's own ANSWER can say "no item"
(S4.5 fix wave FX-E item 4): a 200 that is not its answer (`search_error`: the search's `error` object, not JSON, no
`response`), or an identified item whose metadata answer is not one, -> `api-error`, not retriable (the same query
fails the same way), never `not_in_corpus`. A first author carrying a Lucene grouping character is searched with it
made a space (`GROUP_CHARS`), so the query stays balanced. A PDF the item serves is then checked against the record's
dates (`litkb.acquire.recovery.checked_capture`, as E1's).

NOT BUILT here: the `{identifier}_djvu.txt` OCR text the survey lists (ASSERTED there; a text kind, not a PDF),
the full-text search API (`be-api.us.archive.org/ia-pub-fts-api`), and borrowing.

A RELAYED design (CLAUDE.md §3.4c): the client is VERIFIED in the survey (`internetarchive/internetarchive`,
`sea9401/philosophy-mcp@96a3929`), the `is_dark` and lending rules only ASSERTED there, and the lending markers
below are builder-C2c's reading, not checked against any source in this session. UNVALIDATED until an independent
referee scores it. The plan names no litkb row for E3: its yield is what the run measures. Stdlib only.
"""
import datetime
import json
import urllib.parse

from litkb.acquire import accept as _accept
from litkb.acquire import ledger as _ledger
from litkb.acquire import recovery as _recovery
from litkb.acquire import run as _run

ROUTE = "ia"
SEARCH = "https://archive.org/advancedsearch.php"
METADATA = "https://archive.org/metadata/{identifier}"
DOWNLOAD = "https://archive.org/download/{identifier}/{name}"
#: The fields the search returns (what identity needs).
FIELDS = ("identifier", "title", "creator", "year", "mediatype", "external-identifier")
#: Search hits asked for, and at most this many IDENTIFIED items are opened (builder-C2c's choices,
#: UNCALIBRATED: they bound the requests one work costs).
ROWS = 5
ITEMS_OPENED = 2
#: Collections whose items are lent, not downloaded (builder-C2c's reading of the survey's "lending-restricted";
#: NOT verified in source this session). An item in one, or marked `access-restricted-item`, is `blocked`.
LENDING_COLLECTIONS = ("inlibrary", "printdisabled", "lendinglibrary")
PDF_ACCEPT = "application/pdf,*/*;q=0.5"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _phrase(s):
    """A Lucene phrase body: the characters that would end or escape the phrase removed."""
    return " ".join(str(s or "").replace('"', " ").replace("\\", " ").split())


#: The characters that open or close a Lucene group, a range, or a field inside the `creator:( ... )` group
#: (Lucene's classic query syntax: `( )` grouping, `[ ] { }` ranges, `:` a field — builder-FX-E's reading of Lucene's
#: documented special characters, not checked against the Internet Archive's parser this session). A first author
#: that carries one broke the whole query: hardening-1's 10.5067/doc/ceoswgcv/lpv/lc.001 (L007) sent
#: `creator:(Land Product Validation Subgroup (Working Group on Calibration and Validation)` — the record's corporate
#: name lost its closing parenthesis — and the search answered 200 `{"error": "a structure was opened but not closed
#: (group open at position 1)"}` (referee-vocabulary; S4.5 fix wave FX-E item 4). A name without them builds the
#: byte-identical query it always did.
GROUP_CHARS = "()[]{}:"


def _group_body(s):
    """A Lucene group body for a name: `_phrase`'s characters and every `GROUP_CHARS` character made a space."""
    out = _phrase(s)
    # BEGIN guard: a name that carries a Lucene grouping character never unbalances the item search
    out = " ".join(out.translate({ord(c): " " for c in GROUP_CHARS}).split())
    # END guard: a name that carries a Lucene grouping character never unbalances the item search
    return out


def query(work):
    """The advancedsearch query for a work (step 1). '' when the work gives nothing to search by."""
    parts = []
    if work.get("doi"):
        parts.append(f'external-identifier:"urn:doi:{_phrase(work["doi"]).lower()}"')
    titles = [t for t in (work.get("title_forms") or [work.get("title")]) if t]
    if titles:
        t = " OR ".join(f'title:"{_phrase(x)}"' for x in titles)
        surname = _group_body(work.get("first_author"))
        parts.append(f"(({t}) AND creator:({surname}))" if surname else f"({t})")
    if not parts:
        return ""
    return "(" + " OR ".join(parts) + ") AND mediatype:texts"


def search_url(work):
    q = query(work)
    if not q:
        return ""
    params = [("q", q)] + [("fl[]", f) for f in FIELDS] + [("rows", str(ROWS)), ("page", "1"), ("output", "json")]
    return SEARCH + "?" + urllib.parse.urlencode(params)


def _list(v):
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def search_error(body):
    """-> "" when `body` is the item search's own ANSWER — a JSON object carrying a `response` object and no `error`
    (the shape of every one of hardening-1's 98 answered searches: `responseHeader.status` 0, `response.docs`) — else
    why it is not one: not JSON, the search's `error` object (hardening-1's L007: `{"error": "a structure was opened
    but not closed ..."}` at HTTP 200), or no `response`. Only an answer can say "no item" (S4.5 fix wave FX-E item 4:
    an IA query error is `api-error`, never `not_in_corpus`)."""
    try:
        data = json.loads((body or b"").decode("utf-8", "replace"))
    except ValueError:
        return "the body is not JSON"
    if not isinstance(data, dict):
        return "the body is not a JSON object"
    if data.get("error"):
        return f"the search answered an error: {str(data['error'])[:200]}"
    if not isinstance(data.get("response"), dict):
        return "the body carries no `response` object"
    status = (data.get("responseHeader") or {}).get("status") if isinstance(data.get("responseHeader"), dict) else 0
    if status not in (0, None):
        return f"the search's responseHeader.status is {status!r}"
    return ""


def parse_search(body):
    """-> the hits (dicts) of an advancedsearch JSON answer; [] when it is empty or unreadable."""
    try:
        data = json.loads((body or b"").decode("utf-8", "replace"))
    except ValueError:
        return []
    docs = ((data or {}).get("response") or {}).get("docs") if isinstance(data, dict) else None
    return [d for d in (docs or []) if isinstance(d, dict) and d.get("identifier")]


def identified(hit, work):
    """-> the reason this hit IS the work ("doi" / "title+creator"), or "" (step 2)."""
    from litkb.admit.binding import author_on_page, fold_tokens

    doi = str(work.get("doi") or "").strip().lower()
    if doi and any(v.strip().lower() == f"urn:doi:{doi}" for v in _list(hit.get("external-identifier"))):
        return "doi"
    forms = {tuple(fold_tokens(t)) for t in (work.get("title_forms") or [work.get("title")]) if t}
    forms.discard(())
    titles = {tuple(fold_tokens(t)) for t in _list(hit.get("title"))}
    if not forms or not (forms & titles):
        return ""
    first = work.get("first_author") or ""
    if first and not author_on_page(first, " ; ".join(_list(hit.get("creator")))):
        return ""
    return "title+creator"


def restriction(meta):
    """-> why the item may NOT be downloaded ("dark", "lending: ..."), or "" (step 3). `meta` is the metadata
    API's whole answer."""
    if not isinstance(meta, dict) or not meta:
        return "dark"               # the metadata API answers {} for an item it does not serve
    # BEGIN guard: a dark Internet Archive item is never downloaded
    if meta.get("is_dark") in (True, "true", "True"):
        return "dark"
    # END guard: a dark Internet Archive item is never downloaded
    md = meta.get("metadata") or {}
    # BEGIN guard: a lending-restricted Internet Archive item is blocked, never downloaded
    if str(md.get("access-restricted-item") or "").strip().lower() == "true":
        return "lending: access-restricted-item"
    lent = sorted(set(_list(md.get("collection"))) & set(LENDING_COLLECTIONS))
    if lent:
        return "lending: collection " + ",".join(lent)
    # END guard: a lending-restricted Internet Archive item is blocked, never downloaded
    return ""


def pdf_files(meta):
    """The item's PDF files that may be fetched (not `private`), the uploaded original first."""
    files = [f for f in (meta.get("files") or []) if isinstance(f, dict)]
    out = [f for f in files if str(f.get("name") or "").lower().endswith(".pdf")
           and str(f.get("private") or "").lower() != "true"]
    return sorted(out, key=lambda f: (f.get("source") != "original", str(f.get("name"))))


class _Ask:
    """One rung call's requests (the same bookkeeping as litkb.acquire.wayback's)."""

    def __init__(self, client, pacer, decide):
        self.client, self.pacer, self.decide = client, pacer, decide
        self.codes, self.tried, self.policy = [], [], []
        self.terminal = None
        self.refused = False

    def get(self, url, accept, token):
        host = _recovery.host_of(url)
        if self.decide is not None:
            d = self.decide(host)
            detail = d.as_detail() if hasattr(d, "as_detail") else dict(d)
            if detail not in self.policy:
                self.policy.append(detail)
            # BEGIN guard: an Internet Archive request is asked only when the pre-fetch policy allows its host
            if not detail.get("allowed"):
                self.refused = True
                self.tried.append(f"{token}=policy-refused")
                return None
            # END guard: an Internet Archive request is asked only when the pre-fetch policy allows its host
        if self.pacer is not None:
            self.pacer.wait()
        st, hd, body = self.client.get(url, accept=accept)
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


def fetch_ia(work, client, *, pacer=None, decide=None):
    """-> the rung dict (module docstring). `decide(host)` is the pre-fetch policy; None asks without one."""
    ask = _Ask(client, pacer, decide)
    url = search_url(work)
    if not url:
        return {"status": "skipped", "sub_status": "no_identifier", "detail": "no DOI and no title to search by"}
    got = ask.get(url, "application/json", "search")
    if got is None:
        return _result(ask, status="skipped", sub_status="policy_refused",
                       detail="the pre-fetch policy refused archive.org")
    st, _hd, body = got
    if _transient(st):
        return _result(ask, status="api-error", retriable=True, detail=f"the item search answered {st}")
    if st != 200:
        return _result(ask, status="api-error", retriable=False, detail=f"the item search answered {st}")
    # BEGIN guard: an item search that answered no answer is an api-error, never "no item"
    err = search_error(body)
    if err:
        return _result(ask, status="api-error", retriable=False,
                       detail=f"the item search answered 200 without its answer ({err}): nothing is known about "
                              f"the archive's holdings")
    # END guard: an item search that answered no answer is an api-error, never "no item"
    hits = parse_search(body)
    chosen = [(h, why) for h in hits for why in [identified(h, work)] if why][:ITEMS_OPENED]
    notes = [f"{len(hits)} hit(s), {len(chosen)} identified"]
    restricted, refused, served_html, no_pdf = [], [], None, 0
    unread = []                 # identified items whose metadata answer was no answer (FX-E item 4)
    for hit, why in chosen:
        ident = str(hit["identifier"])
        got = ask.get(METADATA.format(identifier=urllib.parse.quote(ident, safe="")), "application/json",
                      f"metadata {ident}")
        if got is None:
            continue
        st, _hd, body = got
        if _transient(st):
            return _result(ask, status="api-error", retriable=True, detail=f"the metadata API answered {st}")
        try:
            meta = json.loads(body.decode("utf-8", "replace")) if st == 200 else None
        except ValueError:
            meta = None
        # BEGIN guard: an identified item whose metadata answer is no answer is never read as dark
        if not isinstance(meta, dict):
            unread.append(ident)
            notes.append(f"{ident} ({why}): the metadata API answered {st} without its answer")
            continue
        # END guard: an identified item whose metadata answer is no answer is never read as dark
        why_not = restriction(meta)
        if why_not:
            notes.append(f"{ident} ({why}): {why_not}")
            if why_not.startswith("lending"):
                restricted.append(ident)
            continue
        files = pdf_files(meta)
        if not files:
            no_pdf += 1
            notes.append(f"{ident} ({why}): no PDF file")
            continue
        name = str(files[0]["name"])
        dl = DOWNLOAD.format(identifier=urllib.parse.quote(ident, safe=""), name=urllib.parse.quote(name))
        got = ask.get(dl, PDF_ACCEPT, f"download {ident}")
        if got is None:
            continue
        st, hd, body = got
        if _transient(st):
            return _result(ask, status="api-error", retriable=True, detail=f"the download answered {st}")
        if st == 200 and _accept.quick_magic(body):
            return _result(ask, status="downloaded", pdf=body, source_url=dl, kind="pdf",
                           detail="; ".join(notes + [f"{ident} ({why}): {name}"]))
        # BEGIN guard: a refused Internet Archive download is booked blocked, typed by the ledger's rule
        if st in (401, 403):
            sub, _basis, cause = _ledger.type_blocked([st], body, hd, None, ROUTE)
            refused.append((sub or "identity_required", dict(ask.terminal)))
            notes.append(f"{ident} ({why}): the download answered {st} ({cause})")
            continue
        # END guard: a refused Internet Archive download is booked blocked, typed by the ledger's rule
        if st == 200 and body and served_html is None:
            served_html = (body, dl, dict(ask.terminal))
        elif st in (404, 410):
            no_pdf += 1
            notes.append(f"{ident} ({why}): its listed PDF {name} answered {st}")
    if served_html is not None:
        body, dl, terminal = served_html
        return _result(ask, status="bad-file", rejected=body, rejected_url=dl, terminal=terminal,
                       detail="; ".join(notes + ["the item served something that is not a PDF"]))
    if restricted:
        return _result(ask, status="blocked", sub_status="identity_required", retriable=False,
                       detail="; ".join(notes))
    if refused:
        sub, terminal = refused[0]
        return _result(ask, status="blocked", sub_status=sub, retriable=False, terminal=terminal,
                       detail="; ".join(notes))
    if ask.refused and not chosen:
        return _result(ask, status="skipped", sub_status="policy_refused", detail="; ".join(notes))
    if unread:
        # an identified item was never read: whether it holds the work's PDF is unknown, so never "no item"
        return _result(ask, status="api-error", retriable=False, detail="; ".join(notes))
    sub = "no_pdf_link" if no_pdf else "not_in_corpus"
    return _result(ask, status="not-in-archive", sub_status=sub, retriable=False, detail="; ".join(notes))


def _rung(work, ctx):
    r = fetch_ia(work, ctx.clients.get(ROUTE) or _client(), pacer=ctx.pacer,
                 decide=lambda host: ctx.decide(ROUTE, host))
    # S4.5 fix wave FX-E item 3: the Stage E identity rule on an item's PDF too (`recovery.checked_capture`)
    # BEGIN guard: an Internet Archive PDF whose own dates contradict the record is never a conversion
    r = _recovery.checked_capture(work, r)
    # END guard: an Internet Archive PDF whose own dates contradict the record is never a conversion
    return r


def _client():
    from litkb.netutil import Client

    return Client(base="")


#: builder-C1a's rung registry (S4.5 decision D19). Asks by the work's DOI or title, so it needs a DOI, an arXiv id
#: or neither — `needs` names the identifier the attempt row is keyed by.
RUNG = _recovery.register(_run.Rung(ROUTE, _rung, needs=("doi", "arxiv"), concurrent=False, retry_transient=True))

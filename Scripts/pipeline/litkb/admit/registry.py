"""Check 1 — confirm an identifier against its registry and compare a claimed record with it.

    rec = crossref_record(client, "10.4171/jems/179", pacer)        # or datacite_record / arxiv_record
    ev = evidence(rec, claimed={"title": ..., "authors": ..., "year": ...})

A registry record is {registry, identifier, titles, title, first_author, authors, year, venue, volume, issue,
pages, publisher, type, url}. The work admitted is the registry's record, never the claimed one; the claimed
record (tracker row, manifest row, the caller's --title/--authors/--year) is only compared with it, by the rule
of litkb.admit.resolver.judge_candidate (title ratio >= 0.85, first-author family, year exact or +/-1).
"""
import re
import urllib.parse

from litkb.admit.resolver import (ARXIV_ID_LIST, ATOM_NS, CROSSREF_WORK, _json, arxiv_get, family_matches,
                                  judge_candidate, registry_get, strip_tags, title_match_ratio)

DATACITE_WORK = "https://api.datacite.org/dois/{doi}"

#: HTTP statuses from a registry that say "ask again later", not "there is no such record" (S3).
#: `0` is what `resolver.registry_get` / `arxiv_get` return when the client never got a response at
#: all — a timeout, a DNS failure, a reset connection. `429` is a rate limit the two getters have
#: already backed off once for; `408` is the server's own timeout; `406` is what arXiv answered for
#: two real admissions on 2026-09-20 (workstream `scout-1`, admissions 01a0c101-af27… and
#: 01a0c102-870a…), which check 1 recorded as terminal `admission-refused` — the same id was
#: admitted 4 minutes 17 seconds later. 5xx is the server saying so itself.
#: NOT here, deliberately: `404` (the registry HAS answered — it holds no such record), and every
#: other 4xx, which says the request was wrong rather than early.
TRANSIENT_STATUSES = (0, 406, 408, 429)


def is_transient(status):
    """Does this registry status mean RETRY, rather than 'no such record'? (S3)

    One reader for a fact two callers need — `litkb.admit.front.admit_registry`, which must not
    write a refused admission row for it, and `litkb.hunt`, which reports it as the retryable
    `api-error/registry-transient` rather than the terminal `refused/admission-refused`."""
    try:
        st = int(status)
    except (TypeError, ValueError):
        # a status nothing could parse is not evidence that the registry answered
        return True
    # BEGIN guard: a registry status that means 'ask again later' is never read as a refusal
    return st in TRANSIENT_STATUSES or 500 <= st <= 599
    # END guard: a registry status that means 'ask again later' is never read as a refusal


#: S4.5 decision D51 (referee-substrate N2; builder FX-S's live A/B): a registry answer that is the registry's HOST
#: REFUSING THIS CLIENT — not an answer about the record, so it stays `is_transient` (check 1 writes no refused
#: admission for it), and not one an immediate re-ask changes, so `retriable` is False and the answer carries the
#: evidence. (registry, status) -> the host and what was measured. arXiv's 406, MEASURED:
#:   * 2026-09-20: two 406s for 2412.05728 (workstream scout-1, admissions 01a0c101…, 01a0c102…), then 200 for the
#:     same id 4 min 17 s later;
#:   * 2026-09-21 to 2026-09-24T08:45Z: 406 to every request (24 of 24 in the ruled run, 8 of 8 in hardening-1 —
#:     rows L010-L017, one request each), an empty body, no Content-Type, no Retry-After (referee-substrate §3);
#:   * 2026-09-24T23:56Z: 200 and the Atom record for litkb's UNCHANGED request (the same User-Agent, Accept and
#:     http:// URL; builder FX-S's live A/B, its request a): the refusal ended with nothing changed on litkb's side,
#:     so neither the User-Agent nor the address was refused for good; which one the episode keyed on is
#:     UNDETERMINED (nothing was refusing when the A/B could ask).
#: A refusal that lasted minutes once and days once, and that no in-run re-ask ever changed: re-hunt after a
#: back-off, never at once.
CLIENT_REFUSALS = {
    ("arxiv", 406): {
        "host": "export.arxiv.org",
        "measured": ("406 to every request 2026-09-21..2026-09-24T08:45Z (32 of 32); 200 again for the unchanged "
                     "request at 2026-09-24T23:56Z; on 2026-09-20 a 406 lifted after 4 min 17 s"),
        "rule": ("the host refusing this client, not a verdict on the record; an immediate re-ask has never changed "
                 "it: re-hunt after a back-off"),
    },
}


def client_refusal(registry, status):
    """-> the facts (host, what was measured, the rule, registry, status) when `registry` answering `status` is its
    host refusing this client (CLIENT_REFUSALS), else None."""
    try:
        st = int(status)
    except (TypeError, ValueError):
        return None
    facts = CLIENT_REFUSALS.get((str(registry), st))
    return dict(facts, registry=str(registry), status=st) if facts else None


def retriable(registry, status):
    """Would asking `registry` again NOW plausibly change this answer? (guard 15's per-attempt fact, for a registry
    call.) A transient status (`is_transient`) is — unless it is the host refusing this client (`client_refusal`),
    which no immediate re-ask has ever changed."""
    again = is_transient(status)
    # BEGIN guard: a registry host refusing this client is never retriable at once
    if client_refusal(registry, status):
        again = False
    # END guard: a registry host refusing this client is never retriable at once
    return again

_CROSSREF_TYPES = {"journal-article": "article", "proceedings-article": "proceedings", "book": "book",
                   "monograph": "book", "edited-book": "book", "reference-book": "book", "book-chapter": "chapter",
                   "book-section": "chapter", "book-part": "chapter", "report": "report", "dissertation": "thesis",
                   "posted-content": "preprint", "dataset": "dataset", "proceedings": "proceedings"}


def _clean(s):
    return " ".join(strip_tags(s).split())


def _year_from(msg):
    for field in ("issued", "published-print", "published-online", "published", "created"):
        parts = ((msg.get(field) or {}).get("date-parts") or [[None]])[0] or [None]
        if parts and parts[0]:
            return int(parts[0])
    return None


def parse_crossref(msg, doi):
    titles = [_clean(t) for t in (msg.get("title") or []) if t and _clean(t)]
    subs = [_clean(t) for t in (msg.get("subtitle") or []) if t and _clean(t)]
    forms = titles + ([f"{titles[0]}: {subs[0]}"] if titles and subs else [])
    authors = []
    for a in msg.get("author") or []:
        fam = a.get("family") or a.get("name") or ""
        if fam:
            authors.append({"family": fam, "given": a.get("given") or ""})
    first = next((a for a in (msg.get("author") or []) if a.get("sequence") == "first"),
                 (msg.get("author") or [{}])[0] if msg.get("author") else {})
    return {"registry": "crossref", "identifier": doi, "titles": forms, "title": forms[0] if forms else "",
            "subtitle": subs[0] if subs else None,
            "first_author": (first or {}).get("family") or (first or {}).get("name") or "",
            "authors": authors, "year": _year_from(msg),
            "venue": next((c for c in (msg.get("container-title") or []) if c), None),
            "volume": msg.get("volume"), "issue": msg.get("issue"), "pages": msg.get("page"),
            "publisher": msg.get("publisher"), "type": _CROSSREF_TYPES.get(msg.get("type") or "", "article"),
            # The registry's OWN spelling, kept beside the mapped one. `type` folds journal-article,
            # proceedings-article and the rest onto "article" — right for a work_versions row, wrong
            # for the type-compatibility check in `resolver.confirm_s2_candidate`, which must be able
            # to ask "is this record a journal-article?" and cannot ask it of the folded value.
            # Never used for admission; only for that discriminator.
            "raw_type": msg.get("type") or "",
            # Crossref's optional review discriminator, kept beside `raw_type` for the same reason.
            # Measured: the three real JSTOR reviews carry NO subtype and type `journal-article`, so
            # this never fires on them — it is here so a registry that DOES say "book-review" is
            # believed rather than having to be inferred from an author list.
            "raw_subtype": msg.get("subtype") or "",
            "url": CROSSREF_WORK.format(doi=doi)}


def crossref_record(client, doi, pacer):
    """-> (record | None, http status)."""
    st, body = registry_get(client, CROSSREF_WORK.format(doi=urllib.parse.quote(doi, safe="/")), pacer)
    j = _json(body) if st == 200 else None
    msg = j.get("message") if isinstance(j, dict) else None
    if not isinstance(msg, dict):
        return None, st
    rec = parse_crossref(msg, doi)
    # The raw message the admission already fetched, kept for the HARVEST (S4.5 item 1; decision D2: its
    # `alternative-id`, `ISBN`, `ISSN`/`issn-type` and `relation` were discarded here until S4.5).
    # `litkb.admit.harvest.from_registry_record` reads it; nothing else does, and no request is added.
    rec["_raw"] = msg
    return (rec if rec["title"] else None), st


def datacite_record(client, doi, pacer):
    st, body = registry_get(client, DATACITE_WORK.format(doi=urllib.parse.quote(doi, safe="/")), pacer,
                            accept="application/vnd.api+json")
    j = _json(body) if st == 200 else None
    attrs = ((j or {}).get("data") or {}).get("attributes") if isinstance(j, dict) else None
    if not isinstance(attrs, dict):
        return None, st
    titles = [_clean(t.get("title")) for t in (attrs.get("titles") or []) if t.get("title")]
    creators = attrs.get("creators") or []
    authors = [{"family": c.get("familyName") or c.get("name") or "", "given": c.get("givenName") or ""}
               for c in creators if c.get("familyName") or c.get("name")]
    rtype = ((attrs.get("types") or {}).get("resourceTypeGeneral") or "").lower()
    return ({"registry": "datacite", "identifier": doi, "titles": titles, "title": titles[0] if titles else "",
             "subtitle": None, "first_author": authors[0]["family"] if authors else "", "authors": authors,
             "year": attrs.get("publicationYear"), "venue": attrs.get("publisher"), "volume": None,
             "issue": None, "pages": None, "publisher": attrs.get("publisher"),
             "type": {"dataset": "dataset", "report": "report", "text": "report", "preprint": "preprint",
                      "dissertation": "thesis", "book": "book"}.get(rtype, "report"),
             "url": DATACITE_WORK.format(doi=doi),
             # the attributes the admission already fetched, for the HARVEST (S4.5 item 1, decision D2):
             # `identifiers`, `alternateIdentifiers` and `relatedIdentifiers` were discarded until S4.5
             "_raw": attrs} if titles else None), st


def arxiv_record(client, arxiv_id, pacer):
    import xml.etree.ElementTree as ET

    aid = re.sub(r"v\d+$", "", re.sub(r"^arxiv:", "", (arxiv_id or "").strip(), flags=re.I))
    st, body = arxiv_get(client, ARXIV_ID_LIST.format(id=urllib.parse.quote(aid, safe="")), pacer)
    if st != 200:
        return None, st
    try:
        e = ET.fromstring(body).find(ATOM_NS + "entry")
    except ET.ParseError:
        return None, st
    if e is None:
        return None, st
    title = " ".join((e.findtext(ATOM_NS + "title") or "").split())
    if not title or title.lower() == "error":
        return None, st
    authors = []
    for au in e.findall(ATOM_NS + "author"):
        name = " ".join((au.findtext(ATOM_NS + "name") or "").split())
        parts = name.split()
        if parts:
            authors.append({"family": parts[-1], "given": " ".join(parts[:-1])})
    year = (e.findtext(ATOM_NS + "published") or "")[:4]
    return ({"registry": "arxiv", "identifier": aid, "titles": [title], "title": title, "subtitle": None,
             "first_author": authors[0]["family"] if authors else "", "authors": authors,
             "year": int(year) if year.isdigit() else None, "venue": "arXiv", "volume": None, "issue": None,
             "pages": None, "publisher": None, "type": "preprint",
             "url": ARXIV_ID_LIST.format(id=aid)}), st


def confirm_doi(client, doi, pacer):
    """Crossref, then DataCite (design §4.6 check 1). -> (record | None, [(registry, status)])."""
    tried = []
    for name, fn in (("crossref", crossref_record), ("datacite", datacite_record)):
        rec, st = fn(client, doi, pacer)
        tried.append((name, st))
        if rec:
            return rec, tried
    return None, tried


def compare_claimed(rec, claimed):
    """The claimed record against the registry record, by judge_candidate. -> dict for the evidence."""
    first = claimed.get("first_author") or claimed.get("authors") or ""
    cand = {"titles": rec["titles"], "family": rec["first_author"], "year": rec["year"]}
    ok, ratio, note = judge_candidate(cand, claimed.get("title") or "", first, claimed.get("year"))
    return {"title": claimed.get("title"), "first_author": first, "year": claimed.get("year"),
            "title_ratio": round(ratio, 4), "author_match": family_matches(rec["first_author"], first),
            "accepted": ok, "note": note}


def evidence(rec, claimed=None):
    ev = {"registry": rec["registry"], "registry_url": rec["url"], "registry_title": rec["title"],
          "registry_titles": rec["titles"], "registry_first_author": rec["first_author"],
          "registry_year": rec["year"]}
    if claimed and (claimed.get("title") or claimed.get("year") or claimed.get("authors")
                    or claimed.get("first_author")):
        ev["claimed"] = compare_claimed(rec, claimed)
    return ev


def work_title(rec):
    """The work's title: the registry's title joined with its subtitle, where it published one.

    `10.14778/2994509.2994535` entered this KB as the work `Konda_2016_magellan-work`, title
    "Magellan", because the stored title was `rec["title"]` — the BARE title — while the subtitle
    "toward building entity matching management systems" sat unused in a field of its own. The key is
    minted from the title, so a bare title mints a truncated key, and `make_key` then pads the
    one-word slug out with "work" to reach its two-word minimum. That is the whole of the defect
    (`Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §7 P4), and this is the one place it is fixed.

    `parse_crossref` already builds this exact form into `rec["titles"]` — the list `judge_candidate`
    and `confirm_s2_candidate` have always taken their max ratio over. So nothing about MATCHING
    changes here; what changes is which of the forms the work is STORED under.
    """
    sub = (rec.get("subtitle") or "").strip()
    title = (rec.get("title") or "").strip()
    if not (title and sub) or title.lower().endswith(sub.lower()):
        return title
    return f"{title}: {sub}"


def title_forms(rec):
    """Every title form the registry published, the work's own first — what a binder may match, and
    what check 1 accepts as "the work is the registry record" (migration 0020)."""
    out = []
    for t in [work_title(rec), *(rec.get("titles") or []), rec.get("title") or ""]:
        t = (t or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def subtitle_discrepancy(rec, claimed):
    """A claim that names the title but not the subtitle -> the discrepancy's fields, else None.

    It is not a refusal, and it was never going to be one: `judge_candidate` takes its max over
    `rec["titles"]`, so a bare-title claim scores 1.0 against the bare form and check 1 passes. What
    it IS, is a disagreement between what the source claimed and what was admitted — and this KB
    keeps those instead of correcting or discarding them (decisions.yaml `litkb-p0-foundation`,
    "P3 load"). Recorded under `discrepancies.source = 'admission'` (migration 0020).
    """
    claim = (claimed or {}).get("title") or ""
    full = work_title(rec)
    if not claim or not (rec.get("subtitle") or "").strip():
        return None
    if title_match_ratio(full, claim) >= 0.999:
        return None                                # the claim carried the subtitle
    if title_match_ratio(rec.get("title") or "", claim) < 0.999:
        return None                                # some other disagreement, not the missing subtitle
    return {"field": "title", "claimed": claim, "registry": full,
            "ratio": round(title_match_ratio(full, claim), 4),
            "detail": {"reason": "the claimed title is the registry title without its subtitle",
                       "registry_title": rec.get("title"), "registry_subtitle": rec.get("subtitle")}}


def work_fields(rec):
    """The work version admitted: the registry's record (design §4.2 work_versions columns)."""
    return {k: v for k, v in {
        "type": rec.get("type") or "article", "title": work_title(rec), "subtitle": rec.get("subtitle"),
        "authors": rec.get("authors") or [], "year": rec.get("year"), "venue": rec.get("venue"),
        "volume": rec.get("volume"), "issue": rec.get("issue"), "pages": rec.get("pages"),
        "publisher": rec.get("publisher")}.items() if v is not None}

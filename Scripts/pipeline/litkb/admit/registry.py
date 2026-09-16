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
                                  judge_candidate, registry_get, strip_tags)

DATACITE_WORK = "https://api.datacite.org/dois/{doi}"

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
             "url": DATACITE_WORK.format(doi=doi)} if titles else None), st


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


def work_fields(rec):
    """The work version admitted: the registry's record (design §4.2 work_versions columns)."""
    return {k: v for k, v in {
        "type": rec.get("type") or "article", "title": rec["title"], "subtitle": rec.get("subtitle"),
        "authors": rec.get("authors") or [], "year": rec.get("year"), "venue": rec.get("venue"),
        "volume": rec.get("volume"), "issue": rec.get("issue"), "pages": rec.get("pages"),
        "publisher": rec.get("publisher")}.items() if v is not None}

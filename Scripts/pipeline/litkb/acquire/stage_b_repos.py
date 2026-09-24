"""Stage B's repository and venue rungs, and Stage A's A4 publisher-URL rung (LITKB_WORKPLAN.md "### S4.5" items 3
and 4; S4.5 builder C2a). The shared plumbing, the wave order and the closure rule are litkb.acquire.stage_b's.

  doaj       B8   DOAJ's article API (never the article page: it 403s with `cf-mitigated: challenge` a second after
                  the API answers — survey B8), `bibjson.link[type=fulltext]`
  openaire   B9   OpenAIRE `search/publications?doi=` (XML), every instance URL that names a PDF
  hal        B14  HAL's search API, `fileMain_s` (survey B14 guard: paper-search-mcp's HAL client accepted any 200
                  as a PDF — the bytes decide here, through the acceptance test)
  osf        B11  OSF APIv2 two-hop: `/v2/preprints/{id}/` -> `primary_file` -> `links.download` (Zotero
                  `OSF Preprints.js@c830037`), for the OSF DOI prefixes Stage A's A3 routes
  zenodo     B14  Zenodo's record API for a `10.5281/zenodo.<n>` DOI or a version DataCite named (a CONCEPT DOI
                  has no file — linkage edge row 24)
  figshare   B14  figshare's article API for a `10.6084/m9.figshare.<n>` DOI
  europepmc  B12  Europe PMC `resultType=core` — asked only once a PMCID has appeared (LINKAGE §2.3); the three-field
                  selection `hasPDF != N`, `documentStyle == pdf`, `availabilityCode == OA` (B12-RG), then the byte
                  route `europepmc.org/articles/{PMCID}?pdf=render` (B21: the pmc.ncbi PDF path serves reCAPTCHA)
  venue      B13  the conference-venue ladder, two members built: ACL Anthology from the ACL id (DOI prefix
                  10.18653 or S2's `externalIds.ACL`), and OpenReview's note search by title, accepted only when the
                  title, the first author's surname AND the year agree (survey B13: title-match false positives are
                  the real risk). CVF, NeurIPS, PMLR, ECVA and AAAI are NOT built (each needs a conference index
                  parsed, and no corpus row was measured against one).
  publisher-url  A4  the Atypon-family `/doi/pdf/{doi}` template for the prefixes Stage C does not construct
                  (`stage_a.publisher_urls`). A page served there is `blocked`, typed `html_or_reader` (survey A4-RG:
                  "pair the template with an identity gate or it manufactures bad-file rows"), and still handed to
                  Stage C as a lead.

`core` (B7) is NOT BUILT: `CORE_API_KEY` is blank (paper_search.env, read 2026-09-23) and the survey measured the
v3 API unauthenticated as 429 / 404 (B7-RG); the report says `not-built: core`.

No rung here was asked live by this builder (the grant named none of these hosts): every parser is tested on
CONSTRUCTED answers built from the documented shapes, and says so; the run measures their yield. Each is a RELAYED
design (CLAUDE.md §3.4c), UNVALIDATED.
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET

from litkb import identifiers as I
from litkb.acquire import stage_a as A
from litkb.acquire import stage_b as B
# the title agreement the venue ladder demands is litkb's own resolver ratio (the bar a registry candidate clears)
from litkb.admit.resolver import RESOLVE_TITLE_RATIO

DOAJ_ARTICLES = "https://doaj.org/api/search/articles/doi:{doi}"
OPENAIRE_PUBLICATIONS = "https://api.openaire.eu/search/publications?doi={doi}&format=xml"
HAL_SEARCH = ("https://api.archives-ouvertes.fr/search/?q=doiId_s:%22{doi}%22"
              "&fl=halId_s,fileMain_s,linkExtUrl_s,doiId_s&wt=json")
OSF_PREPRINT = "https://api.osf.io/v2/preprints/{id}/"
ZENODO_RECORD = "https://zenodo.org/api/records/{id}"
FIGSHARE_ARTICLE = "https://api.figshare.com/v2/articles/{id}"
EUROPEPMC_CORE = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%22{doi}%22"
                  "&format=json&resultType=core")
EUROPEPMC_RENDER = "https://europepmc.org/articles/{pmcid}?pdf=render"
ACL_PDF = "https://aclanthology.org/{id}.pdf"
#: `limit=5` is the BUILDER'S CHOICE, uncalibrated (no survey names a number; auditor-C2a F15): the hits the matcher
#: reads. A match needs all three agreements (`openreview_match`), so the limit bounds the response, never loosens it.
OPENREVIEW_SEARCH = "https://api2.openreview.net/notes/search?term={q}&limit=5"
OPENREVIEW_PDF = "https://openreview.net/pdf?id={id}"


def _q(doi):
    return urllib.parse.quote(I.norm("doi", doi), safe="/()")


# ── B8 DOAJ ──────────────────────────────────────────────────────────────────────────────────────
def doaj_links(data):
    """DOAJ search results -> [(url, meta)] of every `bibjson.link` whose type is `fulltext` (paper-search-mcp
    0.1.4 `DOAJSearcher._parse_doaj_item`'s field reading)."""
    out = []
    for res in (data or {}).get("results") or [] if isinstance(data, dict) else []:
        for ln in ((res or {}).get("bibjson") or {}).get("link") or []:
            if isinstance(ln, dict) and str(ln.get("type") or "").lower() == "fulltext" and ln.get("url"):
                if ln["url"] not in [u for u, _m in out]:
                    out.append((ln["url"], {"version": "publishedVersion", "content_type": ln.get("content_type")}))
    return out


def rung_doaj(work, ctx):
    """B8 (route `doaj`)."""
    st, data, term = B.get_json(ctx, "doaj", DOAJ_ARTICLES.format(doi=_q(work.get("doi"))))
    if st != 200 or not isinstance(data, dict):
        return B.service_miss("doaj", st, term, "DOAJ")
    if not data.get("results"):
        return {"status": "unresolved", "http_codes": [st], "terminal": term,
                "detail": "DOAJ holds no article for this DOI"}
    return B.answered("doaj", doaj_links(data), ctx, work, term=term)


# ── B9 OpenAIRE ──────────────────────────────────────────────────────────────────────────────────
def _local(tag):
    return re.sub(r"^\{[^}]*\}", "", tag or "").lower()


def openaire_urls(xml_bytes):
    """OpenAIRE's XML answer -> (pdf_urls, other_urls): every `url` / `webresource` text that is an http URL
    (paper-search-mcp 0.1.4 `OpenAIRESearcher._extract_rel_data`'s walk), split by whether it names a PDF
    (`.pdf` or `/pdf` in it — the same test that client uses). Unparseable XML -> ([], [])."""
    try:
        root = ET.fromstring(xml_bytes or b"")
    except ET.ParseError:
        return [], []
    pdf, other = [], []
    for el in root.iter():
        if _local(el.tag) in ("url", "webresource") and el.text and el.text.strip().startswith("http"):
            u = el.text.strip()
            bucket = pdf if (u.lower().endswith(".pdf") or "/pdf" in u.lower()) else other
            if u not in bucket:
                bucket.append(u)
    return pdf, other


def rung_openaire(work, ctx):
    """B9 (route `openaire`): the instance URLs that name a PDF are asked; the others (landing pages) are
    recorded for Stage C, not fetched (survey B9: "feed URLs back to Stage C")."""
    st, _hd, body, term = B.get(ctx, "openaire", OPENAIRE_PUBLICATIONS.format(doi=_q(work.get("doi"))),
                                accept="application/xml")
    if st != 200:
        return B.service_miss("openaire", st, term, "OpenAIRE")
    pdf, other = openaire_urls(body)
    cands = []
    for u in pdf:
        a = B.canon_arxiv(u)
        if a:
            A.found(work, [{"scheme": "arxiv", "value": a}], "openaire")
        else:
            cands.append((u, {"version": None}))
    r = B.answered("openaire", cands, ctx, work, term=term)
    if other:
        r["reason"] = "landing URLs for Stage C: " + ", ".join(other[:5])
    return r


# ── B14 HAL ──────────────────────────────────────────────────────────────────────────────────────
def hal_files(data):
    out = []
    for d in ((data or {}).get("response") or {}).get("docs") or [] if isinstance(data, dict) else []:
        u = (d or {}).get("fileMain_s")
        if isinstance(u, str) and u.startswith("http") and u not in [x for x, _m in out]:
            out.append((u, {"version": None, "hal": d.get("halId_s")}))
    return out


def rung_hal(work, ctx):
    """B14 (route `hal`)."""
    st, data, term = B.get_json(ctx, "hal", HAL_SEARCH.format(doi=_q(work.get("doi"))))
    if st != 200 or not isinstance(data, dict):
        return B.service_miss("hal", st, term, "HAL")
    if not ((data.get("response") or {}).get("numFound")):
        return {"status": "unresolved", "http_codes": [st], "terminal": term,
                "detail": "HAL holds no deposit for this DOI"}
    return B.answered("hal", hal_files(data), ctx, work, term=term)


# ── B11 OSF ──────────────────────────────────────────────────────────────────────────────────────
def osf_id(doi):
    """The OSF preprint id of a DOI under one of the OSF prefixes Stage A's A3 routes (`10.31235/osf.io/cxp4q`
    -> `cxp4q`), else ''."""
    d = I.norm("doi", doi or "")
    if A.native_route(d)[1] != "osf":
        return ""
    m = re.search(r"osf\.io/([a-z0-9]+)(?:_v[0-9]+)?$", d)
    return m.group(1) if m else ""


def osf_url(pid):
    return OSF_PREPRINT.format(id=pid)


def rung_osf(work, ctx):
    """B11 (route `osf`): two hops over OSF APIv2, then the file."""
    pid = next((osf_id(d) for d in A.ids_of(work, "doi") if osf_id(d)), "")
    if not pid:
        return B.closure_skip("no_identifier", "OSF is asked for a DOI under an OSF preprint prefix "
                                               "(10.31219 / 10.31235 / 10.31234 / 10.32942) — none here")
    st, data, term = B.get_json(ctx, "osf", osf_url(pid), accept="application/vnd.api+json")
    if st != 200 or not isinstance(data, dict):
        return B.service_miss("osf", st, term, "OSF")
    rel = (((data.get("data") or {}).get("relationships") or {}).get("primary_file") or {})
    href = ((rel.get("links") or {}).get("related") or {}).get("href") if isinstance(rel.get("links"), dict) else None
    if not href:
        return B.answered("osf", [], ctx, work, term=term, detail="OSF: the preprint names no primary file")
    st2, f, term2 = B.get_json(ctx, "osf", href, accept="application/vnd.api+json")
    if st2 != 200 or not isinstance(f, dict):
        return B.service_miss("osf", st2, term2, "OSF (primary file)", codes=[st, st2])
    dl = (((f.get("data") or {}).get("links") or {}).get("download"))
    cands = [(dl, {"version": "submittedVersion"})] if isinstance(dl, str) and dl.startswith("http") else []
    r = B.answered("osf", cands, ctx, work, term=term2)
    r["http_codes"] = [st, st2] + ((r.get("http_codes") or []) if cands else [])
    return r


# ── B14 Zenodo and figshare ──────────────────────────────────────────────────────────────────────
def zenodo_ids(work):
    """Zenodo record ids of the run's DOIs: `10.5281/zenodo.<n>` (the work's own, or a version a DataCite edge
    named — linkage edge row 24: a CONCEPT DOI has no file, the HasVersion edge is what names one)."""
    out = []
    for d in A.ids_of(work, "doi"):
        m = re.fullmatch(r"10\.5281/zenodo\.([0-9]+)", d)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def zenodo_files(rec):
    out = []
    for f in (rec or {}).get("files") or [] if isinstance(rec, dict) else []:
        key = str((f or {}).get("key") or (f or {}).get("filename") or "")
        links = (f or {}).get("links") or {}
        u = links.get("self") or links.get("download")
        if u and key.lower().endswith(".pdf"):
            out.append((u, {"version": None, "file": key}))
    return out


def rung_zenodo(work, ctx):
    """B14 (route `zenodo`)."""
    ids = zenodo_ids(work)
    if not ids:
        return B.closure_skip("no_identifier", "Zenodo is asked for a 10.5281/zenodo.<n> DOI (the work's, or a "
                                               "version DataCite named) — none here")
    st, data, term = B.get_json(ctx, "zenodo", ZENODO_RECORD.format(id=ids[0]))
    if st != 200 or not isinstance(data, dict):
        return B.service_miss("zenodo", st, term, "Zenodo")
    return B.answered("zenodo", zenodo_files(data), ctx, work, term=term)


def figshare_id(doi):
    m = re.fullmatch(r"10\.6084/m9\.figshare\.([0-9]+)(?:\.v[0-9]+)?", I.norm("doi", doi or ""))
    return m.group(1) if m else ""


def figshare_files(rec):
    out = []
    for f in (rec or {}).get("files") or [] if isinstance(rec, dict) else []:
        name = str((f or {}).get("name") or "")
        u = (f or {}).get("download_url")
        if u and name.lower().endswith(".pdf"):
            out.append((u, {"version": None, "file": name}))
    return out


def rung_figshare(work, ctx):
    """B14 (route `figshare`)."""
    fid = next((figshare_id(d) for d in A.ids_of(work, "doi") if figshare_id(d)), "")
    if not fid:
        return B.closure_skip("no_identifier", "figshare is asked for a 10.6084/m9.figshare.<n> DOI — none here")
    st, data, term = B.get_json(ctx, "figshare", FIGSHARE_ARTICLE.format(id=fid))
    if st != 200 or not isinstance(data, dict):
        return B.service_miss("figshare", st, term, "figshare")
    return B.answered("figshare", figshare_files(data), ctx, work, term=term)


# ── B12 Europe PMC ───────────────────────────────────────────────────────────────────────────────
def europepmc_pick(result):
    """B12-RG's three-field selection over one `resultType=core` result: `hasPDF` not `N`, then every
    `fullTextUrl` whose `documentStyle` is `pdf` AND `availabilityCode` is `OA` (ContentMine getpapers
    `lib/eupmc.js@915fc89`; Zotero `Europe PMC.js`). -> [(url, meta)]."""
    if not isinstance(result, dict) or str(result.get("hasPDF") or "").upper() == "N":
        return []
    urls = ((result.get("fullTextUrlList") or {}).get("fullTextUrl") or [])
    out = []
    for u in urls if isinstance(urls, list) else [urls]:
        if isinstance(u, dict) and str(u.get("documentStyle") or "").lower() == "pdf" \
                and str(u.get("availabilityCode") or "").upper() == "OA" and u.get("url"):
            out.append((u["url"], {"version": None, "site": u.get("site")}))
    return out


def from_europepmc(result, doi):
    """One Europe PMC result -> pmid / pmcid rows (asserted_by `europepmc`, derived from the DOI). Pure."""
    df = ("doi", I.norm("doi", doi))
    rows = []
    for key, scheme in (("pmid", "pmid"), ("pmcid", "pmcid")):
        v = (result or {}).get(key) if isinstance(result, dict) else None
        if v not in (None, ""):
            n = I.norm(scheme, str(v))
            if I.valid(scheme, n):
                rows.append(I.row(scheme, n, asserted_by="europepmc", derived_from=df, evidence={"field": key}))
    return rows


def rung_europepmc(work, ctx):
    """B12 / B21 (route `europepmc`): asked only once a PMCID has appeared in the run (LINKAGE §2.3 Wave 2:
    "`pmcid` found -> Europe PMC"); MEASURED ZERO on the survey's controls, kept because a GET costs no quota."""
    pmcids = A.ids_of(work, "pmcid")
    if not pmcids:
        return B.closure_skip("no_identifier", "Europe PMC is asked once a PMCID has appeared — none here")
    doi = work.get("doi")
    st, data, term = B.get_json(ctx, "europepmc", EUROPEPMC_CORE.format(doi=_q(doi)))
    if st != 200 or not isinstance(data, dict):
        return B.service_miss("europepmc", st, term, "Europe PMC")
    results = ((data.get("resultList") or {}).get("result") or [])
    result = results[0] if results else None
    rows = from_europepmc(result, doi) if result else []
    B.gained(work, rows, "europepmc")
    cands = europepmc_pick(result) + [(EUROPEPMC_RENDER.format(pmcid=p), {"version": None, "route": "pdf=render"})
                                      for p in pmcids[:1]]
    return B.answered("europepmc", cands, ctx, work, term=term, harvest={"rows": rows, "relations": []})


# ── B13 the conference-venue ladder ──────────────────────────────────────────────────────────────
def acl_id(work):
    """The ACL Anthology id: from a `10.18653/v1/<id>` DOI, or S2's `externalIds.ACL`. The old-style id's letter
    is upper-case in the Anthology's URLs (`P18-1031`); a stored DOI is lower-cased."""
    for d in A.ids_of(work, "doi"):
        m = re.fullmatch(r"10\.18653/v1/(.+)", d)
        if m:
            return _acl_case(m.group(1))
    for v in A.ids_of(work, "acl"):
        return _acl_case(v)
    return ""


def _acl_case(v):
    v = (v or "").strip()
    return v[0].upper() + v[1:] if re.fullmatch(r"[a-zA-Z][0-9]{2}-[0-9]{4}", v) else v


def _title_ratio(a, b):
    import difflib

    def norm(s):
        return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split())
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def _name_tokens(s):
    """A name's word tokens, case- and accent-folded ("Delgado-Quirós" -> ["delgado", "quiros"])."""
    import unicodedata

    folded = "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(ch))
    return re.findall(r"[^\W\d_]+", folded.casefold())


def surname_agrees(family, author):
    """The work's first-author surname is a WHOLE-TOKEN run in the note's author string (survey B13's guard: author
    surname agreement). Every surname token must appear, in order, as a whole token — never a substring: "Li" is
    not in "Oliver" (auditor-C2a F15)."""
    fam, toks = _name_tokens(family), _name_tokens(author)
    if not fam:
        return False
    return any(toks[i:i + len(fam)] == fam for i in range(len(toks) - len(fam) + 1))


def openreview_match(notes, work):
    """The OpenReview note that IS the work, or None: the title ratio at litkb's resolver bar, the first
    author's surname among the note's authors (`surname_agrees`: whole tokens), and the year within one of the
    work's (survey B13: title-match false positives are the real risk -> author surname AND year agreement; the
    matched title is recorded)."""
    import datetime as _dt

    fam = str(work.get("first_author") or "")
    for n in notes if isinstance(notes, list) else []:
        c = (n or {}).get("content") or {}
        title = c.get("title", {}).get("value") if isinstance(c.get("title"), dict) else c.get("title")
        authors = c.get("authors", {}).get("value") if isinstance(c.get("authors"), dict) else c.get("authors")
        ms = (n or {}).get("pdate") or (n or {}).get("cdate") or (n or {}).get("tcdate")
        year = _dt.datetime.fromtimestamp(ms / 1000, _dt.timezone.utc).year if isinstance(ms, (int, float)) else None
        if _title_ratio(title, work.get("title")) < RESOLVE_TITLE_RATIO:
            continue
        if not fam or not any(surname_agrees(fam, a) for a in (authors or [])):
            continue
        if work.get("year") and (year is None or abs(int(work["year"]) - year) > 1):
            continue
        return {"id": n.get("id"), "title": title, "year": year}
    return None


def rung_venue(work, ctx):
    """B13 (route `venue`): ACL Anthology by id first (deterministic, no search); else OpenReview by title with the
    three agreements (`openreview_match`)."""
    aid = acl_id(work)
    if aid:
        return B.answered("venue", [(ACL_PDF.format(id=urllib.parse.quote(aid, safe=".-")), {"version": None})],
                          ctx, work, detail=f"ACL Anthology id {aid}")
    title = work.get("title") or ""
    if not title:
        return B.closure_skip("no_identifier", "the venue ladder needs an ACL id or a title")
    st, data, term = B.get_json(ctx, "venue", OPENREVIEW_SEARCH.format(q=urllib.parse.quote(title)))
    if st != 200 or not isinstance(data, dict):
        return B.service_miss("venue", st, term, "OpenReview")
    m = openreview_match(data.get("notes") or [], work)
    if m is None:
        return B.answered("venue", [], ctx, work, term=term,
                          detail="OpenReview: no note agrees on title, first author and year")
    return B.answered("venue", [(OPENREVIEW_PDF.format(id=urllib.parse.quote(str(m["id"]), safe="")),
                                 {"version": None})], ctx, work, term=term,
                      detail=f"OpenReview note {m['id']}: {m['title']!r} ({m['year']})")


# ── A4 the publisher URL ─────────────────────────────────────────────────────────────────────────
def rung_publisher_url(work, ctx):
    """A4 (route `publisher-url`, Stage A): the URL built from the DOI alone (`stage_a.publisher_urls`), asked
    once. No template names the prefix -> a `no_identifier` skip that asks nothing."""
    urls = A.publisher_urls(work.get("doi"))
    if not urls:
        return B.closure_skip("no_identifier", "no Stage A publisher template names this DOI prefix (Stage C "
                                               "builds the others from the landing page)")
    return B.fetch_candidates("publisher-url", [(u, {"version": "publishedVersion"}) for u in urls], ctx, work,
                              html_status="blocked")

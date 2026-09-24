"""Stage A of the acquisition ladder: ZERO network at hunt time (LITKB_WORKPLAN.md "### S4.5" item 3;
S4.5 builder C2a).

    stage_a.prepare(conn, ws, token, work, ctx, agent=..., session=...)   # once, before any rung
    ctx.work_class        -> "preprint"  (the A2 router's answer; RungContext.decide consults it)
    work["ids"]           -> [(scheme, value_norm, via), ...]   (the identifiers the rungs ask with)

WHAT RUNS HERE, and where each rule comes from (Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md §1 Stage A,
graded VERIFIED there; Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md §2.3 Wave 0 and §4.1). Every
mechanism is a RELAYED design (CLAUDE.md §3.4c), UNVALIDATED until an independent referee scores it on the
rows the plan names; nothing here has been scored by its builder.

  A0  the record-class filter (`record_class`): FLAG, never delete, and keep `retracted` fetchable. The flag
      is recorded on the attempt row of the rung that saw the evidence (Crossref's `update-to` / `type`,
      OpenAlex's `is_paratext` / `is_retracted`); litkb stores no such field of its own, so at Stage A the
      only evidence is the work's own type.
  A1  identifier canonicalisation (`canonical_ids`): every held identifier through B1's validators
      (litkb.identifiers.norm / valid) — a malformed value is REJECTED (kept aside with the reason), never
      coerced into a plausible one.
  A2  the WORK-CLASS ROUTER (`work_class`, `routed`): paper / preprint / chapter / book / report / thesis /
      html-only. It is what stops a preprint or a book reaching a shadow / scidb-by-DOI route (the routing
      error the survey's §M measured: 5 preprints among Anna's 33 `not-in-archive` DOIs — "shadow libraries
      never index preprints"); a preprint goes to its NATIVE API instead (`native_route`). The router acts
      through the pre-fetch PolicyDecision: a shadow line for a routed-away class is REFUSED before any
      request, and that refusal is the `skipped/policy_refused` attempt row the ladder writes.
  A3  the DOI-prefix router (`native_route`): registrant-owned prefixes -> the server's native API (survey
      A3: "prefixes are registrant-owned, so false positives are near-impossible"), plus the DataCite
      prefixes LINKAGE §2.3 names (10.48550, 10.5281, 10.6084).
  A4  deterministic publisher-URL construction — the rung `publisher-url` in litkb.acquire.stage_b_repos
      (it is a network rung; its URL is built here, `publisher_urls`).
  A7  EarthArXiv's OAI map, published DOI -> preprint PDF — the rung `eartharxiv` below: the map is
      HARVESTED OFFLINE (qc/instruments/litkb_eartharxiv_map.py, the orchestrator's live pass) and read
      locally; at hunt time the rung makes ONE request, the PDF, and only on a map hit.
  Wave 0, the zero-request derivations (`derive`), through B1's functions, each a row with provenance
      `deterministic`: a `10.48550/arxiv.<id>` DOI -> its arXiv id (WRITTEN: the same edition, a certainty);
      an arXiv id -> its `10.48550` DOI as a CANDIDATE (NOT written: litkb.record_identifiers refuses a
      candidate until DataCite confirms it — the `datacite` rung confirms and writes it); ISBN-10 -> ISBN-13.
      The PMCID prefix is A1's, not a Wave-0 row: B1's normaliser (`identifiers.norm("pmcid", ...)`) stores
      every PMCID as `PMC<n>`, so `canonical_ids` already holds it prefixed.
  ISBN-13 -> ISBN-A is NOT BUILT (auditor-C2a F5). B1's `identifiers.isbn_a_doi` needs a HYPHENATED ISBN-13
      (the hyphens carry the registration-group split, which cannot be re-derived without the range table), and
      A1's normaliser strips hyphens, so no identifier Stage A holds can feed it; the one hyphenated form in
      reach is a live Crossref `ISBN` field. And an ISBN-A DOI is a CANDIDATE that only the handle system could
      confirm, which no route of this session asks. Books are S4.6 (Stage F).
  shortDOI: DETECTED here (`identifiers.is_shortdoi`) and never expanded by the ladder. Expanding it is ONE
      request to doi.org's handle API, not zero (LINKAGE §3.6); no route of 0033's vocabulary names that
      host, and no work in the base holds a shortDOI (MEASURED 2026-09-23 on live, litkb_reader: 0 of 466
      DOIs start `10/`). A shortDOI a work carries is reported in `work["stage_a"]["shortdoi"]`.

STAGE A'S RECORD reaches the ledger: `prepare`'s summary (A1's rejected identifiers, the Wave-0 rows written and
the candidates held, a Wave-0 write failure, the shortDOI note, the A0 flag, the A2 class, the A3 server) is
carried in the `detail.stage_a` of the FIRST attempt row the ladder writes for the work (`onto_first_row`, called
by litkb.acquire.run wherever the ladder writes a row) and returned in `acquire()`'s answer (auditor-C2a F1: a
summary left on the work dict alone was thrown away).

NOT BUILT HERE (orchestrator scope ruling 2026-09-23, brief-CONTRACTS.md "Scope ruling"): the offline
Sci-Hub / LibGen membership table of plan item 3.
"""
import csv
import datetime
import os
import urllib.parse
from dataclasses import replace
from pathlib import Path

from litkb import identifiers as I
from litkb.acquire import policy as _policy

# ── A2: the work classes ─────────────────────────────────────────────────────────────────────────
#: The router's classes (plan item 3: "paper · chapter · book · report · thesis · HTML-only"), plus
#: `preprint`, the class the router exists to route (plan item 3; brief C2a item 1).
WORK_CLASSES = ("paper", "preprint", "chapter", "book", "report", "thesis", "html-only")

#: `main_works.type` (litkb's own vocabulary: admit/registry.py `_CROSSREF_TYPES` and DataCite's map) ->
#: the router's class. MEASURED on live 2026-09-23 (litkb_reader): the base holds article 381, preprint 44,
#: proceedings 33, report 16, chapter 11, book 1 — every `posted-content` row of the crosswalk probe CSV
#: (8) is already typed `preprint`, so the plan's two preprint definitions agree on today's base.
#: `dataset` -> `report` is the BUILDER'S CHOICE: the plan's classes name no dataset, admission can type one
#: (admit/registry.py maps Crossref's and DataCite's `dataset`), and `report` (grey literature, shadow-eligible
#: like a paper) changes no routing — the base holds 0 datasets (the same census).
CLASS_OF_TYPE = {"article": "paper", "proceedings": "paper", "preprint": "preprint", "chapter": "chapter",
                 "book": "book", "report": "report", "thesis": "thesis", "dataset": "report"}

#: Crossref `type` -> class, for the live answer a Stage B rung reads (the same map admission uses,
#: admit/registry.py `_CROSSREF_TYPES`, restated in the router's words).
CLASS_OF_CROSSREF_TYPE = {"journal-article": "paper", "proceedings-article": "paper", "posted-content": "preprint",
                          "book": "book", "monograph": "book", "edited-book": "book", "reference-book": "book",
                          "book-chapter": "chapter", "book-section": "chapter", "book-part": "chapter",
                          "report": "report", "dissertation": "thesis"}

#: The classes the router keeps OFF every shadow route. `preprint`: shadow libraries do not index preprints
#: (survey §M: the 5 `posted-content` DOIs among Anna's misses were "a routing error"); plan item 3: the router
#: "stops a preprint or a book being sent to the scidb-by-DOI archive path". `book`: the scidb-by-DOI path is
#: the article path; a book's route is the ISBN namespace (S4.6 Stage F). `html-only`: the work IS a web page
#: (S4.5 decision D12's `html_is_the_work`), which no shadow library holds as a PDF. Chapters, reports and
#: theses stay eligible: nothing in the surveys measured them as a routing error.
SHADOW_REFUSED_CLASSES = ("preprint", "book", "html-only")

#: The identifier schemes whose presence makes a work more than a web page (a work holding none of them and
#: only a `url` is the HTML-only class — a page admitted through a URL hunt).
_WORK_SCHEMES = ("doi", "arxiv", "isbn", "pmid", "pmcid", "handle", "hal", "oai")


def work_class(work):
    """A2 -> the work's class. `work["type"]` (main_works.type) decides; a work that holds a URL and no
    work-level identifier (a page a URL hunt admitted) is `html-only`; an unknown type is a `paper` (admission's
    own default)."""
    ids = work.get("ids") or []
    schemes = {s for s, _v, via in ids if via == "own"}
    if "url" in schemes and not (schemes & set(_WORK_SCHEMES)) and not work.get("doi"):
        return "html-only"
    return CLASS_OF_TYPE.get(str(work.get("type") or "").lower(), "paper")


def crossref_class(message):
    """A2 on Crossref's live answer (the `crossref-link` rung): its `type` in the router's words, with the
    survey's A2 salvage — Crossref `other` + an ISBN + a container title is a book section (Zotero's Crossref
    rule, survey A2 guard; Codex X5). '' when Crossref's type says nothing the router uses."""
    m = message if isinstance(message, dict) else {}
    t = str(m.get("type") or "").lower()
    if t == "other" and m.get("ISBN") and m.get("container-title"):
        return "chapter"
    return CLASS_OF_CROSSREF_TYPE.get(t, "")


def tighten(current, observed):
    """The class a later, live answer may move the router to: ONLY toward a routed-away class (a Crossref
    `posted-content` answer makes an `article` row a preprint; nothing makes a preprint shadow-eligible)."""
    if observed in SHADOW_REFUSED_CLASSES and current not in SHADOW_REFUSED_CLASSES:
        return observed
    return current


def routed(decision, work_class_):
    """The A2 router applied to one pre-fetch PolicyDecision (litkb.acquire.policy.decide): a SHADOW line is
    refused for a routed-away class, with the reason, BEFORE any request; every other decision passes as is."""
    # BEGIN guard: the work-class router keeps a preprint or a book off every shadow route
    if decision.allowed and decision.tier == _policy.SHADOW and work_class_ in SHADOW_REFUSED_CLASSES:
        return replace(decision, allowed=False,
                       reason=f"the work-class router (Stage A2): a {work_class_} is never sent to a shadow route")
    # END guard: the work-class router keeps a preprint or a book off every shadow route
    return decision


# ── A0: the record-class filter ──────────────────────────────────────────────────────────────────
#: Crossref `update-to[].type` -> the A0 flag (survey A0: `withdrawn`, `correction`; `retracted` is FLAGGED
#: and kept fetchable — the survey's guard).
_UPDATE_FLAGS = {"correction": "correction", "erratum": "correction", "corrigendum": "correction",
                 "addendum": "correction", "withdrawal": "withdrawn", "removal": "withdrawn",
                 "retraction": "retracted"}
#: Crossref types that are not an article a PDF of the work could be (survey A0: `not_an_article`).
_NOT_AN_ARTICLE = {"peer-review", "component", "dataset", "database", "grant", "standard", "journal", "journal-issue",
                   "journal-volume", "proceedings", "book-series", "book-set", "report-series"}


def record_class(*, work_type=None, crossref=None, openalex=None):
    """A0 -> the record-class FLAG ('' when nothing flags it). A flag is recorded, never acted on by deleting:
    the plan's "flag, never delete", and a `retracted` work stays fetchable."""
    for u in ((crossref or {}).get("update-to") or []) if isinstance(crossref, dict) else []:
        flag = _UPDATE_FLAGS.get(str((u or {}).get("type") or "").lower())
        if flag:
            return flag
    if isinstance(crossref, dict) and str(crossref.get("type") or "").lower() in _NOT_AN_ARTICLE:
        return "not_an_article"
    if isinstance(openalex, dict):
        if openalex.get("is_retracted"):
            return "retracted"
        if openalex.get("is_paratext"):
            return "paratext"
    if str(work_type or "").lower() == "dataset":
        return "not_an_article"
    return ""


# ── A3: the DOI-prefix router ────────────────────────────────────────────────────────────────────
#: Registrant-owned DOI prefixes -> (server, the 0033 route that is its native API, or '' when no route of
#: this session serves it). Survey A3 (VERIFIED: Zotero `OSF Preprints.js@c830037`) for the preprint servers;
#: LINKAGE §2.3 for the DataCite prefixes 10.5281 (Zenodo) and 10.6084 (figshare).
PREFIX_ROUTES = {
    "10.48550": ("arxiv", "arxiv"),
    "10.31223": ("eartharxiv", "eartharxiv"),
    "10.31219": ("osf", "osf"), "10.31235": ("osf", "osf"), "10.31234": ("osf", "osf"),
    "10.32942": ("osf", "osf"),
    "10.21203": ("researchsquare", ""),
    "10.22541": ("authorea", ""), "10.36227": ("techrxiv", ""),
    "10.26434": ("chemrxiv", ""),
    "10.1101": ("biorxiv", ""),
    "10.5281": ("zenodo", "zenodo"),
    "10.6084": ("figshare", "figshare"),
    "10.20944": ("preprints.org", ""),
}
#: The prefixes whose DOIs DataCite registers (LINKAGE §2.3 Wave 2: "prefix 10.48550, 10.5281, 10.6084, or
#: Crossref 404 -> DataCite").
DATACITE_PREFIXES = ("10.48550", "10.5281", "10.6084")


def doi_prefix(doi):
    return (I.norm("doi", doi or "").split("/", 1) + [""])[0]


def native_route(doi):
    """A3 -> (server, route) for the DOI's registrant prefix, or ('', '')."""
    return PREFIX_ROUTES.get(doi_prefix(doi), ("", ""))


# ── A1 + Wave 0 ──────────────────────────────────────────────────────────────────────────────────
def canonical_ids(rows):
    """A1: [(scheme, value, via)] -> (kept, rejected). Every value through the scheme's normaliser and its
    validator; a value its scheme's shape refuses is rejected with the reason, never coerced."""
    kept, rejected = [], []
    for scheme, value, via in rows:
        v = I.norm(scheme, value)
        # `url`, `tracker` and `legacy_stem` are litkb's own bookkeeping schemes: kept as held, not validated
        if scheme in ("url", "tracker", "legacy_stem") or I.valid(scheme, v):
            if (scheme, v, via) not in kept:
                kept.append((scheme, v, via))
        else:
            rejected.append({"scheme": scheme, "value": value, "via": via,
                             "why": f"not a valid {scheme} (litkb.identifiers.valid); never coerced"})
    return kept, rejected


def derive(ids):
    """Wave 0 -> (rows to WRITE, candidates held for a registry to confirm, notes). Pure. `ids` is
    [(scheme, value_norm, via)] after A1. Only derivations of the SAME edition are written: an identifier
    derived from an edition EDGE (`via` not `own`) names another edition and is left to that edition."""
    own = [(s, v) for s, v, via in ids if via == "own"]
    held = {(s, v) for s, v in own}
    write, cand, notes = [], [], {}
    for s, v in own:
        if s == "doi":
            r = I.doi_to_arxiv(v)
            if r and ("arxiv", r["value"]) not in held:
                write.append(r)
            if I.is_shortdoi(v):
                notes.setdefault("shortdoi", []).append(v)
        elif s == "arxiv":
            r = I.arxiv_to_doi(v)
            if r and not any(x == "doi" for x, _ in own):
                cand.append(r)          # CANDIDATE: written only once DataCite confirms (the datacite rung)
        elif s == "isbn":
            if len(I.isbn_clean(v)) == 10:
                r = I.isbn10_to_13(v)
                if r and ("isbn", r["value"]) not in held:
                    write.append(r)
    return write, cand, notes


def load_ids(conn, work_id):
    """The work's identifiers as the rungs ask with them: its own ACTIVE identifiers and the targets of its
    EDITION edges (B1's `harvest.copy_identifiers`: how Stage A/B reaches an article's arXiv copy — builder-B1's
    deviation, S2's ArXiv on an article is a `has_version` edge, never the article's own identifier)."""
    from litkb.admit import harvest as H

    return [(s, v, via) for s, v, via in H.copy_identifiers(conn, work_id)]


def prepare(conn, ws, token, work, ctx, *, agent, session):
    """Stage A for one work, BEFORE any rung (called once by `litkb.acquire.run.acquire`). Reads the work's
    type and identifiers (A1-canonicalised), classifies it (A2) and routes its DOI prefix (A3), writes the
    Wave-0 rows that are certain through B1's one write path (`harvest.record`, provenance `deterministic`),
    and leaves on `work`: `type`, `ids`, `candidates`, `class`, `native`, `stage_a` (a summary). Sets
    `ctx.work_class`. A failure to write a Wave-0 row is RECORDED in the summary's `write_error` and never fails
    the acquisition (the harvest contract, builder-B1 §1.4); the summary is RECORDED on the first attempt row the
    ladder writes for the work (`onto_first_row`), so the ledger holds it."""
    from litkb.admit import harvest as H

    row = conn.execute("SELECT type FROM litkb.main_works WHERE work_id = %s", (work["work_id"],)).fetchone()
    work["type"] = row[0] if row else work.get("type")
    raw = load_ids(conn, work["work_id"])
    ids, rejected = canonical_ids(raw)
    write, cand, notes = derive(ids)
    summary = {"rejected_ids": rejected, "derived": [f"{r['scheme']}:{r['value']}" for r in write],
               "candidates": [f"{r['scheme']}:{r['value']}" for r in cand], **notes}
    if write:
        try:
            res = H.record(conn, ws, token, work["work_id"], write, (), agent=agent, session=session)
            summary["written"] = res.get("identifiers")
            ids += [(r["scheme"], r["value"], "own") for r in write]
        except Exception as e:                  # noqa: BLE001 — a harvest never fails an acquisition
            summary["write_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    work["ids"] = ids
    work["candidates"] = cand
    work["class"] = work_class(work)
    work["native"] = native_route(work.get("doi"))
    summary.update({"class": work["class"], "native": work["native"][0], "record_class":
                    record_class(work_type=work.get("type"))})
    work["stage_a"] = summary
    work[_UNRECORDED] = summary
    if ctx is not None:
        ctx.work_class = work["class"]
    return summary


#: The work-dict key holding Stage A's summary until an attempt row carries it (popped by `onto_first_row`).
_UNRECORDED = "_stage_a_unrecorded"


def onto_first_row(work, detail):
    """Stage A's summary into `detail` (key `stage_a`) if no attempt row of this ladder run has carried it yet;
    -> `detail`. Called by litkb.acquire.run at every place the ladder writes an attempt row (a rung's answer, a
    skip, a budget stop, the manual-step row), so whichever row is FIRST carries it — and only that one (the
    ladder settles its rows one at a time, in its own thread)."""
    # BEGIN guard: Stage A's record rides on the first attempt row the ladder writes for the work
    pending = work.pop(_UNRECORDED, None) if isinstance(work, dict) else None
    if pending is not None and isinstance(detail, dict):
        detail["stage_a"] = pending
    # END guard: Stage A's record rides on the first attempt row the ladder writes for the work
    return detail


def ids_of(work, *schemes):
    """The values of `schemes` the ladder run holds for `work` — its own, its edition edges', and the ones a
    rung of THIS run discovered (appended to `work["ids"]` with `via` = the route) — in that order, unique."""
    out = []
    for s, v, _via in work.get("ids") or []:
        if s in schemes and v not in out:
            out.append(v)
    if "doi" in schemes and work.get("doi") and I.norm("doi", work["doi"]) not in out:
        out.insert(0, I.norm("doi", work["doi"]))
    if "arxiv" in schemes and work.get("arxiv") and I.norm("arxiv", work["arxiv"]) not in out:
        out.insert(0, I.norm("arxiv", work["arxiv"]))
    return out


def found(work, rows, route):
    """A rung's discovered identifiers, added to the ladder run's set (the closure rule's accumulation step:
    "accumulate after whichever resolver won, unconditionally", LINKAGE §2.3 from oc_graphenricher). Returns
    the (scheme, value) pairs that were NEW. `list.append` is atomic, so concurrent Stage B rungs may call it."""
    held = {(s, v) for s, v, _via in work.setdefault("ids", [])}
    new = []
    for r in rows:
        key = (r["scheme"], I.norm(r["scheme"], r["value"]))
        if key not in held:
            work["ids"].append((key[0], key[1], route))
            held.add(key)
            new.append(key)
    return new


# ── A7: EarthArXiv's OAI map, harvested offline ──────────────────────────────────────────────────
#: The map's columns (qc/instruments/litkb_eartharxiv_map.py writes it; docs/SCHEMAS.md, "S4.5 builder C2A").
EARTHARXIV_COLUMNS = ("published_doi", "preprint_doi", "pdf_url", "oai_identifier", "datestamp", "rights")


def eartharxiv_map_path():
    """The harvested map: `LITKB_EARTHARXIV_MAP`, else config's default (phase4/qc/litkb_eartharxiv_map.csv)."""
    from litkb import config
    return Path(os.environ.get("LITKB_EARTHARXIV_MAP") or config.EARTHARXIV_MAP)


_EARTHARXIV_CACHE = {}


def eartharxiv_map(path=None):
    """{doi (published or preprint): row} of the harvested map, or None when it has not been harvested."""
    p = Path(path) if path else eartharxiv_map_path()
    if not p.is_file():
        return None
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _EARTHARXIV_CACHE:
        out = {}
        with open(p, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                for col in ("published_doi", "preprint_doi"):
                    d = I.norm("doi", r.get(col) or "")
                    if d and r.get("pdf_url"):
                        out.setdefault(d, r)
        _EARTHARXIV_CACHE.clear()
        _EARTHARXIV_CACHE[key] = out
    return _EARTHARXIV_CACHE[key]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def rung_eartharxiv(work, ctx):
    """A7 (route `eartharxiv`): the work's DOI looked up in the harvested map (published DOI or the preprint's
    own); on a hit, ONE request for the preprint PDF it names. No map on disk: an `api-error` that asked
    nothing and says why (retriable — harvesting the map is what changes the answer), never a miss booked as
    if EarthArXiv had been consulted (the survey's A7 guard: "a harvested map cannot record an outage as a
    permanent verdict", and neither can its absence)."""
    from litkb.acquire import stage_b as B

    table = eartharxiv_map()
    if table is None:
        return {"status": "api-error", "retriable": True, "http_codes": [],
                "detail": f"the EarthArXiv map is not harvested ({eartharxiv_map_path().name}: run "
                          "qc/instruments/litkb_eartharxiv_map.py --live); nothing was asked",
                "terminal": {"url": "", "status_code": None, "at": _now()}}
    hit = next((table[d] for d in ids_of(work, "doi") if d in table), None)
    if hit is None:
        return {"status": "no-oa-copy", "http_codes": [], "detail": "no EarthArXiv preprint in the harvested map",
                "terminal": {"url": "", "status_code": None, "at": _now()}}
    # the run's `work` goes WITH the candidate (builder-fix5; auditor-fix4 N6): the PDF URL is checked against and
    # recorded in the run's asked-URL map, so a later rung listing the same EarthArXiv download never asks it again
    # and in MEASURE mode one file never counts toward two rungs' yields (survey A10: never one URL twice in a run)
    r = B.fetch_candidates("eartharxiv", [(hit["pdf_url"], {"version": "submittedVersion",
                                                          "preprint_doi": hit.get("preprint_doi")})], ctx, work)
    r["detail"] = f"EarthArXiv map hit: preprint {hit.get('preprint_doi')}; " + (r.get("detail") or "")
    return r


# ── A4: the deterministic publisher URL (the network rung is stage_b_repos.rung_publisher_url) ───────
#: DOI prefix -> the Atypon-family PDF template (survey A4, VERIFIED: "Atypon `/doi/pdf/{doi}`, ACM
#: `?download=true`"). ONLY hosts builder C2b's Stage C rule table (litkb.acquire.landing, on its own branch)
#: does not already construct from the DOI alone — so one work is never asked the same template twice:
#: Taylor & Francis (21 no-file works on live, MEASURED 2026-09-23), ACM, SAGE. Springer's template is Stage
#: C's (survey A4-RG: it has no access check and needs the identity gate Stage C pairs it with); MDPI's CDN,
#: Elsevier's pdfft, Wiley, IEEE, IOP, OUP, Frontiers, PLOS and Copernicus are Stage C's too.
PUBLISHER_TEMPLATES = {
    "10.1080": "https://www.tandfonline.com/doi/pdf/{doi}",
    "10.1145": "https://dl.acm.org/doi/pdf/{doi}",
    "10.1177": "https://journals.sagepub.com/doi/pdf/{doi}",
}


def publisher_urls(doi):
    """A4 -> the publisher PDF URLs built from the DOI alone ([] when no template names its prefix)."""
    t = PUBLISHER_TEMPLATES.get(doi_prefix(doi))
    if not t:
        return []
    return [t.format(doi=urllib.parse.quote(I.norm("doi", doi), safe="/()"))]

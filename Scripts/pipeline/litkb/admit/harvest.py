"""The HARVEST (S4.5 item 1, S4.5 decision D2): registry and archive answers litkb already receives ->
identifier rows and relation edges WITH PROVENANCE, then one database call that applies the conflict rule.

    rows, rels = from_crossref(message, "10.1111/2041-210x.13107")   # pure: JSON in, rows out
    res = record(conn, ws, token, work_id, rows, rels, agent=..., session=...)

PURE PARSERS, one per source (D2: "costs no new request" is TRUE for Crossref and DataCite on the DOI admission
path and for Anna's `identifiers_unified`, already fetched at gate 2; FALSE for OpenAlex and Semantic Scholar,
whose calls are Stage B's — builder C2a makes them and hands the JSON to `from_openalex` / `from_s2`):

    from_crossref(message, doi)          alternative-id -> pii (Elsevier only), ISBN / isbn-type -> isbn,
                                         ISSN / issn-type -> issn, relation -> edges (or the third state)
    from_datacite(attributes, doi)       identifiers / alternateIdentifiers -> rows, relatedIdentifiers -> edges
    from_annas(identifiers_unified, doi, md5)   md5 isbn sha1 sha256 zlib lgrsnf lgrsfic lgli oclc lccn olid nexusstc
    from_openalex(work, doi)             ids (openalex mag pmid pmcid), pmh_id -> oai
    from_s2(paper, doi)                  externalIds (PubMed PubMedCentral MAG DBLP CorpusId; ArXiv -> an edge
                                         unless the work IS the arXiv edition — see its docstring)

Each row is `litkb.identifiers.row(...)`: {scheme, value, asserted_by, verified_by, evidence, derived_from}.
`asserted_by` is the SOURCE whose answer carried the value; `derived_from` is the INPUT identifier that answer
was asked by (LINKAGE §3.2 items 2-3: Invenio's provider/client split, and the `by_means_of` string
oc_graphenricher computes and throws away). `verified_by` stays NULL: a Crossref record that lists an ISBN
asserts it, it does not verify it against an ISBN agency.

THE CONFLICT RULE lives in the database (`litkb.record_identifiers`, migration 0032), not here, so every caller
gets it: fatcat's merge — a later source fills a null and never overwrites (a row the work already holds is
skipped); fatcat's collision — a distinct-valued identifier another work already holds is DROPPED, a work-level
`is_version_of` / `is_identical_to` edge is asserted with `asserted_by='conflict-resolution'`, and the conflict
is COUNTED in `litkb.identifier_conflicts` (the `conflicts_uncounted` counter reads both).

THE THIRD STATE of a relation (the plan's "edges with a third state"; its source is the 2026-09-21 plan
revision's linkage row "a third state for an empty field", LITKB_WORKPLAN.md f5887a0): a registry asked for a
work's relations answers one of three things — an edge (`asserted`), NOTHING (`none_returned`: the field was
empty, which is not evidence that no relation exists — "absence of the field is not evidence of absence"), or
it was never asked (no row at all). `none_returned` is recorded so the second and third can be told apart.

Citation relations (`references`, `is-referenced-by`, DataCite `Cites`/`IsCitedBy`) are NOT edges here: they
are the citation graph's (stage 6, `litkb.citation_edges`), not identity or grouping facts.
"""
import re

from litkb import identifiers as I

#: `identifier_versions.verified_by` (migration 0032 CHECK; its one home is here, held equal to the CHECK by
#: qc/test_litkb_s45_identity.py). LINKAGE §3.2 item 1's list verbatim — the services a confirmation can
#: come from, so Stage B (C2a) needs no migration to name its own.
VERIFIERS = ("crossref", "datacite", "arxiv", "s2", "openalex", "opencitations", "pubmed", "pmc_idconv",
             "europepmc", "unpaywall", "core", "doaj", "openaire", "ads", "wikidata", "handle", "isbnlib",
             "openlibrary", "internetarchive", "hathitrust", "gbooks", "worldcat", "fatcat", "annas", "libgen",
             "nexusstc", "deterministic", "manual")

#: `identifier_versions.asserted_by` (migration 0032 CHECK): every verifier, plus the three ways an
#: identifier reached an ADMISSION without a service answer: `caller` (the hunt reference, the CLI flag —
#: its registry confirmation is `verified_by`), `tracker` (a literature tracker row), `legacy` (a legacy
#: corpus file stem). The admission default in `litkb.admit` picks one of those four.
ASSERTERS = VERIFIERS + ("caller", "tracker", "legacy")

#: `work_relations.asserted_by` adds the one source that is not a service: the conflict rule itself.
CONFLICT_RESOLUTION = "conflict-resolution"

#: `work_relations.relation` (migration 0032 CHECK): DataCite's relation vocabulary (the one fatcat captures,
#: LINKAGE §3.4) in snake_case, restricted to identity and grouping relations, plus Crossref's own
#: preprint/manuscript/correction words and `other` for a non-citation relation neither names.
RELATIONS = ("is_part_of", "has_part", "is_version_of", "has_version", "is_new_version_of",
             "is_previous_version_of", "is_preprint_of", "has_preprint", "is_manuscript_of", "has_manuscript",
             "is_identical_to", "is_same_as", "is_variant_form_of", "is_original_form_of", "is_supplement_to",
             "is_supplemented_by", "is_correction_of", "has_correction", "is_review_of", "has_review",
             "is_translation_of", "has_translation", "is_replaced_by", "replaces", "is_derived_from",
             "has_derivation", "is_expression_of", "has_expression", "is_manifestation_of", "has_manifestation",
             "other")

_PAIRS = (("is_part_of", "has_part"), ("is_version_of", "has_version"),
          ("is_new_version_of", "is_previous_version_of"), ("is_preprint_of", "has_preprint"),
          ("is_manuscript_of", "has_manuscript"), ("is_variant_form_of", "is_original_form_of"),
          ("is_supplement_to", "is_supplemented_by"), ("is_correction_of", "has_correction"),
          ("is_review_of", "has_review"), ("is_translation_of", "has_translation"), ("is_replaced_by", "replaces"),
          ("is_derived_from", "has_derivation"), ("is_expression_of", "has_expression"),
          ("is_manifestation_of", "has_manifestation"))
#: The inverse of each relation (the SQL twin is `litkb._relation_inverse`, held equal by the test suite):
#: an edge A has_preprint B and an edge B is_preprint_of A are ONE fact, recorded once.
INVERSE = {**{a: b for a, b in _PAIRS}, **{b: a for a, b in _PAIRS},
           "is_identical_to": "is_identical_to", "is_same_as": "is_same_as", "other": "other"}

#: Citation relations: the citation graph's, never an edge here (see the module docstring).
_CITATION = {"references", "is_referenced_by", "cites", "is_cited_by"}

#: Crossref `identifier` types in `relation` targets -> litkb schemes (anything else: the edge keeps the
#: registry's words in evidence and targets no identifier).
_CROSSREF_ID_TYPES = {"doi": "doi", "arxiv": "arxiv", "isbn": "isbn", "issn": "issn", "pmid": "pmid",
                      "pmcid": "pmcid", "uri": "url", "url": "url", "handle": "handle"}

#: DataCite `relatedIdentifierType` / `identifierType` -> litkb schemes.
_DATACITE_ID_TYPES = {"doi": "doi", "arxiv": "arxiv", "isbn": "isbn", "issn": "issn", "pmid": "pmid",
                      "handle": "handle", "url": "url", "bibcode": "bibcode"}

#: Anna's `identifiers_unified` keys -> litkb schemes (LINKAGE §3.1 tier 1-2). NOT mapped, deliberately:
#: `doi` (gate 2 already checked the requested DOI is among them; another DOI in the list is not evidence
#: about THIS work), `ipfs_cid`/`btih`/`server_path`/`torrent` (storage locations of a FILE, not work
#: identifiers — LINKAGE §3.1's line), and keys no scheme in the registry names (asin, goodreads, ...);
#: those are returned in `skipped` so the caller can count them.
_ANNAS_KEYS = {"md5": "md5", "isbn13": "isbn", "isbn10": "isbn", "sha1": "sha1", "sha256": "sha256",
               "zlib": "zlib", "lgrsnf": "lgrsnf", "lgrsfic": "lgrsfic", "lgli": "lgli", "oclc": "oclc",
               "lccn": "lccn", "ol": "olid", "nexusstc": "nexusstc", "ocaid": "ocaid"}

#: Elsevier's Crossref member id (api.crossref.org/members/78) and DOI prefix: the only publisher whose
#: `alternative-id` is a PII (LINKAGE §0.4: 90 of 92 corpus Elsevier DOIs carry one).
_ELSEVIER_MEMBER, _ELSEVIER_PREFIX = "78", "10.1016/"


def snake(word):
    return re.sub(r"[^a-z]+", "_", re.sub(r"(?<=[a-z])(?=[A-Z])", "_", str(word or "")).lower()).strip("_")


def relation_of(word):
    """A registry's relation word (Crossref `has-preprint`, DataCite `IsVersionOf`) -> (relation | None).
    None for a citation relation (not an edge here)."""
    w = snake(word)
    if w in _CITATION:
        return None
    return w if w in RELATIONS else "other"


def _row(scheme, value, source, derived_from, **evidence):
    return I.row(scheme, value, asserted_by=source, derived_from=derived_from,
                 evidence={k: v for k, v in evidence.items() if v not in (None, "", [])})


def _edge(relation, source_relation, target_scheme, target_value, source, derived_from, **evidence):
    e = {"relation": relation, "source_relation": source_relation, "state": "asserted", "asserted_by": source,
         "target_scheme": target_scheme, "target_value": target_value,
         "evidence": {k: v for k, v in evidence.items() if v not in (None, "", [])}}
    if derived_from:
        e["derived_from"] = {"scheme": derived_from[0], "value": derived_from[1]}
    return e


def none_returned(source, derived_from, field):
    """The third state: `source` was asked for this work's relations and its `field` was empty."""
    return {"state": "none_returned", "asserted_by": source, "evidence": {"field": field},
            "derived_from": {"scheme": derived_from[0], "value": derived_from[1]}}


def _isbn_rows(values, source, derived_from, kind=None):
    rows, rejected = [], []
    for v in values:
        thirteen = I.to_isbn13(v)
        if thirteen is None:
            rejected.append({"scheme": "isbn", "value": v, "why": "not a valid ISBN (check digit re-derived)"})
            continue
        rows.append(_row("isbn", thirteen, source, derived_from, as_given=v if v != thirteen else None,
                         isbn_type=kind))
    return rows, rejected


def from_crossref(msg, doi):
    """A Crossref `works/{doi}` message -> (rows, relations, rejected). Pure."""
    msg = msg if isinstance(msg, dict) else {}
    src, df = "crossref", ("doi", I.norm("doi", doi))
    rows, rejected = [], []
    elsevier = str(msg.get("member") or "") == _ELSEVIER_MEMBER or df[1].startswith(_ELSEVIER_PREFIX)
    for alt in msg.get("alternative-id") or []:
        if elsevier and I.valid("pii", alt):
            rows.append(_row("pii", I.norm("pii", alt), src, df, as_given=alt, field="alternative-id"))
    typed = [(t.get("value"), t.get("type")) for t in (msg.get("isbn-type") or [])
             if isinstance(t, dict) and t.get("value")]
    typed13 = {I.to_isbn13(v) for v, _t in typed}
    for v, kind in typed + [(v, None) for v in (msg.get("ISBN") or []) if v and I.to_isbn13(v) not in typed13]:
        r, rej = _isbn_rows([v], src, df, kind=kind)
        rows += [x for x in r if not any(y["scheme"] == "isbn" and y["value"] == x["value"] for y in rows)]
        rejected += rej
    issn_typed = {I.norm("issn", t.get("value")): t.get("type") for t in (msg.get("issn-type") or [])
                  if isinstance(t, dict) and t.get("value")}
    for v in list(issn_typed) + [I.norm("issn", x) for x in (msg.get("ISSN") or [])]:
        if I.valid("issn", v) and not any(x["scheme"] == "issn" and x["value"] == v for x in rows):
            rows.append(_row("issn", v, src, df, issn_type=issn_typed.get(v)))
    return rows, crossref_relations(msg, doi), rejected


def crossref_relations(msg, doi):
    """Crossref's `relation` object -> edges, or ONE `none_returned` row when it is empty or absent."""
    src, df = "crossref", ("doi", I.norm("doi", doi))
    rel = (msg or {}).get("relation") if isinstance(msg, dict) else None
    out = []
    for word, targets in (rel or {}).items() if isinstance(rel, dict) else ():
        relation = relation_of(word)
        if relation is None:
            continue
        for t in targets if isinstance(targets, list) else [targets]:
            if not isinstance(t, dict) or not t.get("id"):
                continue
            scheme = _CROSSREF_ID_TYPES.get(str(t.get("id-type") or "").lower())
            if scheme is None:
                continue
            value = I.norm(scheme, t["id"])
            out.append(_edge(relation, word, scheme, value, src, df, crossref_asserted_by=t.get("asserted-by"),
                             id_type=t.get("id-type")))
    if not out:
        out.append(none_returned(src, df, "relation"))
    return out


def from_datacite(attrs, doi):
    """DataCite `data.attributes` -> (rows, relations, rejected). Pure."""
    attrs = attrs if isinstance(attrs, dict) else {}
    src, df = "datacite", ("doi", I.norm("doi", doi))
    rows, rejected = [], []
    pairs = [(x.get("identifier"), x.get("identifierType")) for x in (attrs.get("identifiers") or [])
             if isinstance(x, dict)]
    pairs += [(x.get("alternateIdentifier"), x.get("alternateIdentifierType"))
              for x in (attrs.get("alternateIdentifiers") or []) if isinstance(x, dict)]
    for value, kind in pairs:
        scheme = _DATACITE_ID_TYPES.get(str(kind or "").lower())
        if not scheme or not value:
            continue
        if scheme == "isbn":
            r, rej = _isbn_rows([value], src, df)
            rows += r
            rejected += rej
            continue
        v = I.norm(scheme, value)
        if scheme == "doi" and v == df[1]:
            continue
        if I.valid(scheme, v):
            rows.append(_row(scheme, v, src, df, field="identifiers"))
    rels = []
    for x in attrs.get("relatedIdentifiers") or []:
        if not isinstance(x, dict):
            continue
        relation = relation_of(x.get("relationType"))
        scheme = _DATACITE_ID_TYPES.get(str(x.get("relatedIdentifierType") or "").lower())
        if relation is None or scheme is None or not x.get("relatedIdentifier"):
            continue
        rels.append(_edge(relation, x.get("relationType"), scheme, I.norm(scheme, x["relatedIdentifier"]), src, df))
    if not rels:
        rels.append(none_returned(src, df, "relatedIdentifiers"))
    return rows, rels, rejected


def from_annas(identifiers_unified, doi, md5):
    """Anna's `file_unified_data.identifiers_unified` (gate 2's record) -> (rows, skipped). Pure.
    The md5 row is derived from the DOI the archive resolved to it; every other row from that md5."""
    iu = identifiers_unified if isinstance(identifiers_unified, dict) else {}
    src = "annas"
    rows, skipped = [], []
    md5n = I.norm("md5", md5 or "")
    if I.valid("md5", md5n):
        rows.append(_row("md5", md5n, src, ("doi", I.norm("doi", doi)), field="aarecord md5"))
    for key, values in iu.items():
        scheme = _ANNAS_KEYS.get(key)
        vals = values if isinstance(values, list) else [values]
        if scheme is None:
            skipped.append({"key": key, "n": len(vals)})
            continue
        for v in vals:
            v = str(v or "")
            if scheme == "isbn":
                r, _rej = _isbn_rows([v], src, ("md5", md5n))
                rows += [x for x in r if not any(y["scheme"] == "isbn" and y["value"] == x["value"] for y in rows)]
                continue
            n = I.norm(scheme, v)
            if scheme == "md5" and n == md5n:
                continue
            if I.valid(scheme, n) and not any(y["scheme"] == scheme and y["value"] == n for y in rows):
                rows.append(_row(scheme, n, src, ("md5", md5n), key=key))
    return rows, skipped


def from_openalex(work, doi):
    """An OpenAlex work (`works/doi:{doi}`) -> rows. Pure; the CALL is Stage B's (S4.5 decision D2)."""
    work = work if isinstance(work, dict) else {}
    src, df = "openalex", ("doi", I.norm("doi", doi))
    ids = work.get("ids") or {}
    rows = []
    for key, scheme in (("openalex", "openalex"), ("mag", "mag"), ("pmid", "pmid"), ("pmcid", "pmcid")):
        v = ids.get(key)
        if v in (None, ""):
            continue
        n = I.norm(scheme, str(v).rstrip("/").rsplit("/", 1)[-1] if scheme in ("pmid", "pmcid") else str(v))
        if I.valid(scheme, n):
            rows.append(_row(scheme, n, src, df, field=f"ids.{key}"))
    locs = [work.get("primary_location") or {}] + list(work.get("locations") or [])
    for loc in locs:
        pmh = (loc or {}).get("pmh_id") if isinstance(loc, dict) else None
        if pmh and I.valid("oai", pmh) and not any(r["scheme"] == "oai" and r["value"] == pmh for r in rows):
            rows.append(_row("oai", pmh, src, df, field="locations[].pmh_id"))
    return rows


def from_s2(paper, doi):
    """A Semantic Scholar paper record (`externalIds`) -> (rows, relations). Pure; the CALL is Stage B's (D2).

    S2 merges a preprint and its article into ONE record, so an article's `externalIds.ArXiv` names its
    PREPRINT, another edition. Stored as the article's own `arxiv` identifier it would be an ALIAS, which
    `litkb-sibling-edition` forbids ("never an alias"), and check 2 would then refuse the preprint's own
    admission as a duplicate of the article. So on a work whose DOI is not arXiv's own it is an EDGE
    (`has_version`, target the arXiv id, asserted by S2) — and on a `10.48550/arxiv.<id>` work, where the id
    names the same edition, it is an identifier row. Every other external id names this edition: a row."""
    ext = ((paper or {}).get("externalIds") or {}) if isinstance(paper, dict) else {}
    src, df = "s2", ("doi", I.norm("doi", doi))
    rows, rels = [], []
    for key, scheme in (("ArXiv", "arxiv"), ("PubMed", "pmid"), ("PubMedCentral", "pmcid"), ("MAG", "mag"),
                        ("DBLP", "dblp"), ("CorpusId", "s2")):
        v = ext.get(key)
        if v in (None, ""):
            continue
        n = I.norm(scheme, str(v))
        if not I.valid(scheme, n):
            continue
        if scheme == "arxiv" and not df[1].startswith(I.ARXIV_DOI_PREFIX):
            rels.append(_edge("has_version", "externalIds.ArXiv", "arxiv", n, src, df, field="externalIds.ArXiv"))
            continue
        rows.append(_row(scheme, n, src, df, field=f"externalIds.{key}"))
    return rows, rels


# ── the one database call ─────────────────────────────────────────────────────────────────────────────

def _db_payload(obj):
    """The ONE place this module hands JSON to the database: NUL removed (textnorm.jsonb_safe)."""
    from psycopg.types.json import Jsonb

    from litkb.textnorm import jsonb_safe

    return Jsonb(jsonb_safe(obj))


def record(conn, ws, token, work_id, rows=(), relations=(), *, agent, session):
    """litkb.record_identifiers then litkb.record_work_relations (migration 0032) for one work.
    -> {"identifiers": ..., "relations": ...}; either half is None when it had nothing to write.

    Both calls run in ONE transaction block (`conn.transaction()`): on an autocommit connection a transaction,
    inside a caller's open transaction a SAVEPOINT — so a failed harvest rolls back only itself and never takes
    a caller's admission with it (auditor-B1 F14)."""
    out = {"identifiers": None, "relations": None}
    if not rows and not relations:
        return out
    with conn.transaction():
        if rows:
            out["identifiers"] = conn.execute(
                "SELECT litkb.record_identifiers(%s, %s, %s, %s, %s, %s)",
                (ws, token, work_id, _db_payload(list(rows)), agent, session)).fetchone()[0]
        if relations:
            out["relations"] = conn.execute(
                "SELECT litkb.record_work_relations(%s, %s, %s, %s, %s, %s)",
                (ws, token, work_id, _db_payload(list(relations)), agent, session)).fetchone()[0]
    return out


def from_registry_record(rec):
    """(rows, relations, rejected) from a registry record `litkb.admit.registry` built (its `_raw` is the
    answer the admission already fetched — no new request). A record without `_raw` harvests nothing."""
    raw, reg, ident = (rec or {}).get("_raw"), (rec or {}).get("registry"), (rec or {}).get("identifier")
    if not isinstance(raw, dict) or not ident:
        return [], [], []
    if reg == "crossref":
        return from_crossref(raw, ident)
    if reg == "datacite":
        return from_datacite(raw, ident)
    return [], [], []


def record_route_identifiers(conn, ws, token, work_id, doi, route, result, *, agent, session):
    """An acquisition route's answer -> its harvest, written. Today: the archive route's
    `identifiers_unified` (returned by `litkb.acquire.annas.fetch_for_litkb` once gate 2 has passed).
    -> the `record` result, or None when the answer carried nothing to harvest. Best-effort by contract: the
    CALLER decides whether a harvest failure matters (an acquisition never fails on one)."""
    if route != "annas" or not isinstance((result or {}).get("identifiers_unified"), dict):
        return None
    rows, skipped = from_annas(result["identifiers_unified"], doi or result.get("record_doi") or "", result.get("md5"))
    if not rows:
        return None
    res = record(conn, ws, token, work_id, rows, (), agent=agent, session=session)
    res["skipped"] = skipped
    return res


#: The relations whose target is ANOTHER EDITION of the same work (a copy a rung may fetch for it, bound as
#: that edition's copy_kind, never as the version of record).
EDITION_RELATIONS = ("has_preprint", "is_preprint_of", "has_version", "is_version_of", "is_new_version_of",
                     "is_previous_version_of", "is_manuscript_of", "has_manuscript", "is_identical_to", "is_same_as")


def copy_identifiers(conn, work_id):
    """-> [(scheme, value_norm, via)] a Stage A/B rung may try to reach a COPY of `work_id` with: the work's own
    active identifiers (`via` = "own"), then the targets of its edition edges (`via` = the relation, e.g.
    `has_version` for S2's arXiv id on an article — see `from_s2`). Read-only; any role that reads litkb."""
    own = conn.execute(
        "SELECT i.scheme, i.value_norm FROM litkb.identifiers i JOIN litkb.identifier_versions v "
        "ON v.identifier_id = i.id WHERE v.work_id = %s AND v.status = 'active' "
        "AND (v.version_id = i.current_version_id OR v.state = 'proposed') ORDER BY 1, 2", (work_id,)).fetchall()
    edges = conn.execute(
        "SELECT target_scheme, target_value_norm, relation FROM litkb.work_relations "
        "WHERE work_id = %s AND state = 'asserted' AND relation = ANY(%s) ORDER BY created_at",
        (work_id, list(EDITION_RELATIONS))).fetchall()
    out = [(s, v, "own") for s, v in own]
    out += [(s, v, rel) for s, v, rel in edges if (s, v) not in {(a, b) for a, b, _ in out}]
    return out

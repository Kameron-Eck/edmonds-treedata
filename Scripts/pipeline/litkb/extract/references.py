"""Stage 6 (design §7, table row 6) — references, citation mentions, resolution, the citation graph.

    parse -> resolve -> link          references / citation_mentions / candidates  (§4.4, §4.3)

DB-FREE BY CONSTRUCTION. Every output is JSONL parked beside the extraction metrics, exactly as
:func:`litkb.extract.grobid.append_metrics` parks a run's metrics: the `references`,
`citation_mentions` and `candidates` tables are written by P5's ingest under the ``litkb_ingest``
login, and the citation-graph columns are applied at merge. Nothing here opens a connection.

WHAT IS PARSED. ``<text><back>//listBibl/biblStruct`` is the reference list; the header's own
``<biblStruct>`` (the paper describing itself) is NOT a reference and is excluded by the subtree —
:func:`litkb.extract.grobid.bibl_structs` returns both and must not be used here. Each
``<ref type="bibr" target="#bN">`` in the body is one mention of ``biblStruct[@xml:id="bN"]``,
carrying its page and box (the §7.1 frame, cropbox unless the caller shifted it) and the text of
its nearest enclosing ``<s>`` — which exists only because requests go out with
``segmentSentences=1``. GROBID emits no per-element confidence (measured, P4 report §5), so
``confidence`` is None here rather than a made-up number; the one confidence GROBID DOES publish
for a reference is the header/consolidation record, which is off.

THE RESOLUTION RULE, and why it is not `resolver.resolve_doi`.

  * **DOI-FIRST, and the DOI DECIDES.** A reference that carries a DOI is resolved by that DOI
    alone: the registry record is fetched (`registry.confirm_doi`, Crossref then DataCite) and its
    title is compared with the reference's by the project's one title rule. Match -> ``resolved``.
    Different work -> ``unresolved`` with ``doi_title_mismatch``, or ``doi_title_contained`` when
    one title contains the other (a GROBID truncation, or the journal name run onto the end) —
    a LABEL for P5's triage, never an acceptance, and the 0.85 threshold is untouched by it. Not
    found -> ``unresolved`` with ``doi_not_registered``. A reference with a DOI and NO parsed title
    is decided by :func:`_doi_without_title_ok` — first-author family plus an EXACT year — and
    refused with ``doi_unverifiable``. **There is no title fallback for a reference that has a
    DOI.** That is
    the §14 P6 kill in mechanism form: a DOI with one digit altered usually still points at a REAL
    work, and a fallback would quietly re-find the intended paper by title and call the bad DOI
    resolved. A wrong DOI in a reference list is the Averkov 2009 class of defect (§14 P2) — a
    thing to surface, never to silently correct.
  * **Otherwise title + first author + year**, through the same `judge_candidate` the admission
    path uses: ratio >= 0.85 AND first-author family AND year equal or +/-1 (the +/-1 arm is only
    reachable after the other two pass, decisions.yaml litkb-p0-foundation §15.15).
  * **S2 PROPOSES, CROSSREF CONFIRMS.** A Semantic Scholar candidate never resolves on S2 data
    alone. Its DOI is looked up at Crossref (`resolver.confirm_s2_candidate`, cached and paced) and
    the CROSSREF record must pass the same 0.85 ratio filter and the same first-author + year
    discriminator against the reference; S2's authorship merges are thereby ignored. On top of that,
    the record must be TYPE-COMPATIBLE: a `journal-article` carrying the reference's exact title
    whose author list begins with someone else and then names the reference's first author is a
    REVIEW of the cited book (``review_record``); a `journal-article` for a reference that presents
    as a book is ``type_mismatch``; the same title and shared authorship at a year more than one out
    is a sibling edition, ``edition_mismatch``, which is **ambiguous, not resolved**. Every other
    refusal keeps its own name — ``crossref_not_registered``, ``crossref_title_ratio``,
    ``crossref_author_mismatch``, ``crossref_year_mismatch``. Nothing is dropped silently. A record
    with NO author at all is **not** one of these refusals (referee task 3, 2026-09-18): it is
    uninformative on authorship rather than contradicting it, so it is admitted on the title ratio
    and year alone, both still independently required — see `resolver.confirm_s2_candidate`, the
    "MISSING vs CONTRADICTED" comment. WHY: measured on this corpus, 3 of 33 new S2 resolutions were
    a review of the cited book and one was a sibling edition — the three rules all agreed because
    the registry had merged a book with its review (`Reports/LITKB_S2_BATCHING_2026-09-15.md` §4).
  * **`ambiguous` is a state this module has and `resolve_doi` does not.** `resolve_doi` returns
    the FIRST accepted candidate, so it can never report that two different works both passed. Here
    every candidate of a stage is judged, and two or more DISTINCT normalised DOIs among the
    accepted ones is ``ambiguous`` — resolved to nothing, with both DOIs recorded. Stages are tried
    in the resolver's own order (Crossref -> Semantic Scholar -> arXiv) and the first stage with any
    acceptance decides.

An arXiv-stage acceptance yields the ``10.48550/arXiv.`` DOI form for the record only and is marked
``archive_ok=False``: the graph may use it as a node key, the acquisition path may never ask the
archive for it (`resolver.resolve_doi`'s rule, kept).

PACING AND CACHE. Registry calls go through `resolver.registry_get`/`arxiv_get` and their pacers
(1 s Crossref/S2, 3 s arXiv), so this module never sets its own rate. Every response is cached on
disk keyed by the URL's sha256 — **only 200 and 404 are cached**: a cached 429 or a cached status 0
(connection refused, DNS, timeout) would turn one transient failure into a permanent phantom miss
on every re-run, and a resolution rate measured over such a cache is a measurement of the cache.

WHERE THE CACHE LIVES. Design §6 names ``<Literture>\\_derived\\<sha256>\\<stage>\\`` — but §15.6
("derived artifacts location") is still **Open** in `decisions.yaml`, and this session's brief holds
``D:\\edmonds-pipeline\\Literture\\`` read-only. So the root is ``$LITKB_DERIVED`` when set, else
``<Literture>/../litkb_derived`` — outside the read-only corpus and outside git. When §15.6 is
decided, change :data:`DERIVED_ROOT`'s default and nothing else.

THE GRAPH. A resolved reference whose DOI is in the corpus index (the manifest's and the
bibliographies' DOI columns, normalised) is an EDGE citing -> cited. Anything else resolved is a
``candidates`` row, source ``citation`` — state ``new``, admitted_work_id null. **This module never
admits anything**: admission is §4.6's one transaction behind the P2 gate, and a candidate found by
citation is a lead, not a work.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET

from litkb.admit.registry import confirm_doi
from litkb.admit.resolver import (ARXIV_DOI_PREFIX, REGISTRY_STAGES, RESOLVE_TITLE_RATIO,
                                  _ascii_fold, _norm_text, _year_int, confirm_s2_candidate,
                                  family_matches, judge_candidate, normalize_doi, strip_tags,
                                  title_match_ratio)
from litkb.extract.grobid import NS, TEI_NS, parse_coords

STAGE = "6-references"
PIPELINE_VERSION = "litkb-p6-1"

#: The reference list, and only it: the header's own biblStruct describes the paper, not a reference.
BACK_LISTBIBL = ".//t:text/t:back//t:listBibl"

_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
_DOI_IN_TEXT = re.compile(r"\b10\.\d{4,9}/[^\s\"<>,;]+", re.I)
_ARXIV_IN_TEXT = re.compile(r"arxiv[:\s]*((?:\d{4}\.\d{4,5})|(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}))", re.I)


def _derived_default():
    lit = os.environ.get("LITKB_LITERATURE", r"D:\edmonds-pipeline\Literture")
    return os.path.join(os.path.dirname(os.path.abspath(lit)), "litkb_derived")


#: Root of the on-disk artifact/cache tree (see the module docstring; §15.6 is Open).
DERIVED_ROOT = os.environ.get("LITKB_DERIVED") or _derived_default()


# ── TEI -> structured references ────────────────────────────────────────────────────────

def _root(tei):
    if isinstance(tei, ET.Element):
        return tei
    if isinstance(tei, bytes):
        return ET.fromstring(tei)
    return ET.fromstring(tei.encode("utf-8") if isinstance(tei, str) else tei)


def _text(el):
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def _author_names(el):
    out = []
    for p in el.iterfind(".//t:author/t:persName", NS):
        fam = _text(p.find("t:surname", NS))
        given = " ".join(_text(f) for f in p.iterfind("t:forename", NS)).strip()
        if fam or given:
            out.append({"family": fam, "given": given})
    if not out:                      # an author with no persName (a corporate name, an editor-only entry)
        for a in el.iterfind(".//t:author", NS):
            t = _text(a)
            if t:
                out.append({"family": t, "given": ""})
    return out


def _idno(el, kind):
    for i in el.iterfind(".//t:idno", NS):
        if (i.get("type") or "").lower() == kind:
            return _text(i)
    return ""


def reference_elements(tei):
    """Every ``<biblStruct>`` of the back-matter reference list, in document order."""
    root = _root(tei)
    out = []
    for lb in root.iterfind(BACK_LISTBIBL, NS):
        out.extend(lb.findall("t:biblStruct", NS))
    return out


def parse_reference(el, index=0):
    """One ``<biblStruct>`` -> the ``references.parsed`` JSON of §4.4 plus its raw string and boxes."""
    analytic = el.find("t:analytic", NS)
    monogr = el.find("t:monogr", NS)
    title = ""
    for path in ("t:analytic/t:title[@type='main']", "t:analytic/t:title", "t:monogr/t:title[@level='m']"):
        title = _text(el.find(path, NS))
        if title:
            break
    journal = _text(el.find("t:monogr/t:title[@level='j']", NS)) or _text(
        el.find("t:monogr/t:title[@level='m']", NS))
    if journal == title:
        journal = ""
    date = el.find(".//t:imprint/t:date", NS)
    year = ""
    if date is not None:
        m = re.search(r"\d{4}", (date.get("when") or "") + " " + _text(date))
        year = m.group() if m else ""
    authors = _author_names(analytic if analytic is not None and _author_names(analytic) else el)
    # A raw string is present only when the request carried includeRawCitations=1; otherwise the
    # element's own text is the best available and is labelled as such by raw_source.
    note = None
    for n in el.iterfind(".//t:note", NS):
        if (n.get("type") or "") == "raw_reference":
            note = n
            break
    raw, raw_source = (_text(note), "grobid-raw") if note is not None else (_text(el), "tei-itertext")
    doi = _idno(el, "doi") or ""
    arxiv = _idno(el, "arxiv") or ""
    if not doi:
        m = _DOI_IN_TEXT.search(raw)
        doi = m.group() if m else ""
    if not arxiv:
        m = _ARXIV_IN_TEXT.search(raw)
        arxiv = m.group(1) if m else ""
    boxes = [{"page": p, "bbox": [x0, y0, x1, y1]} for p, x0, y0, x1, y1 in parse_coords(el.get("coords"))]
    return {
        "ref_key": el.get(_XML_ID) or f"_r{index}",
        "index": index,
        "authors": authors,
        "first_author": authors[0]["family"] if authors else "",
        "year": year,
        "title": title,
        "journal": journal,
        "volume": _text(el.find(".//t:biblScope[@unit='volume']", NS)),
        "issue": _text(el.find(".//t:biblScope[@unit='issue']", NS)),
        "pages": _text(el.find(".//t:biblScope[@unit='page']", NS)),
        "publisher": _text(el.find(".//t:imprint/t:publisher", NS)),
        "doi": doi,
        "doi_norm": normalize_doi(doi),
        "arxiv": arxiv,
        "raw": raw,
        "raw_source": raw_source,
        "boxes": boxes,
        # GROBID's TEI carries no per-element confidence for biblStruct (P4 report §5). None, not 1.0.
        "confidence": _confidence(el),
        "has_monogr": monogr is not None,
    }


def _confidence(el):
    """GROBID's confidence where it exists — it does not for biblStruct in 0.9.1 CRF, so this is
    None unless a future build starts emitting an attribute. Never invented."""
    for attr in ("conf", "confidence", "cert"):
        v = el.get(attr)
        if v:
            try:
                return float(v)
            except ValueError:
                return None
    return None


def parse_references(tei):
    return [parse_reference(el, i) for i, el in enumerate(reference_elements(tei))]


def citation_mentions(tei):
    """Each in-text ``<ref type="bibr">`` -> a mention: target ref_key, page, bbox, sentence."""
    root = _root(tei)
    parents = {c: p for p in root.iter() for c in p}
    body = root.find(".//t:text/t:body", NS)
    out = []
    for el in (body.iter() if body is not None else ()):
        if el.tag != f"{{{TEI_NS}}}ref" or (el.get("type") or "") != "bibr":
            continue
        target = (el.get("target") or "").lstrip("#")
        sentence, page_of_sentence = "", None
        p = parents.get(el)
        while p is not None:
            if p.tag == f"{{{TEI_NS}}}s":
                sentence = _text(p)
                boxes = parse_coords(p.get("coords"))
                page_of_sentence = boxes[0][0] if boxes else None
                break
            p = parents.get(p)
        for i, (pg, x0, y0, x1, y1) in enumerate(parse_coords(el.get("coords")) or [(None,) * 5]):
            out.append({"target": target, "marker": _text(el), "page": pg,
                        "bbox": None if pg is None else [x0, y0, x1, y1],
                        "box_index": i, "sentence": sentence,
                        "sentence_page": page_of_sentence,
                        "resolved_target": bool(target)})
    return out


def mention_totals(mentions):
    """The three numbers a mention count can mean, so a report can never quote the wrong one.

    ``box_rows`` is len(mentions) — one row per bounding box, the geometry. ``elements`` is the
    number of ``<ref type="bibr">`` elements, which is what "cited n times" means.
    ``without_target`` are elements GROBID could not link to any ``biblStruct``; ``verifiable`` is
    the rest, the only mentions that can be checked against a reference.
    """
    els = [m for m in mentions if m["box_index"] == 0]
    untargeted = sum(1 for m in els if not m["target"])
    return {"mention_box_rows": len(mentions), "mention_elements": len(els),
            "mentions_without_target": untargeted, "mentions_verifiable": len(els) - untargeted}


# ── the disk cache ──────────────────────────────────────────────────────────────────────

#: Only these statuses are cached. See the module docstring: a cached 429 or a cached 0 is a
#: permanent phantom miss, and a rate measured over one measures the cache, not the registries.
CACHEABLE_STATUS = (200, 404)


class DiskCache:
    """URL -> (status, body) under ``<root>/registry/<sha256[:2]>/<sha256>.json``."""

    def __init__(self, root=None, enabled=True):
        self.root = os.path.join(root or DERIVED_ROOT, "registry")
        self.enabled = enabled
        self.hits = self.misses = self.stores = 0

    def _path(self, url):
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return os.path.join(self.root, h[:2], h + ".json")

    def get(self, url):
        if not self.enabled:
            return None
        try:
            with open(self._path(url), encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            self.misses += 1
            return None
        self.hits += 1
        return int(rec["status"]), rec["body"].encode("utf-8")

    def put(self, url, status, body):
        # BEGIN guard: p6 only a settled registry answer is cached
        if not self.enabled or status not in CACHEABLE_STATUS:
            return False
        # END guard: p6 only a settled registry answer is cached
        p = self._path(url)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"url": url, "status": status,
                       "body": (body or b"").decode("utf-8", "replace")}, fh)
        os.replace(tmp, p)
        self.stores += 1
        return True


class CachedClient:
    """A `litkb.netutil.Client` face (``get(url, accept=, timeout=)``) with the disk cache in front.

    A cache HIT does not touch the pacer, so a fully cached re-run costs no wall clock — which is
    the point of caching at all. A miss goes to the wrapped client and is stored only if the status
    is settled.
    """

    def __init__(self, client=None, cache=None, pacer=None):
        if client is None:
            from litkb.netutil import Client
            client = Client()
        self.client = client
        self.cache = cache if cache is not None else DiskCache()
        self.pacer = pacer                 # the _Deferred wrapper, when one is in use
        self.network_calls = 0

    def get(self, url, accept="application/json", timeout=120, **kw):
        hit = self.cache.get(url)
        if hit is not None:
            if self.pacer is not None:
                self.pacer.drop()
            return hit[0], {"x-litkb-cache": "hit"}, hit[1]
        if self.pacer is not None:
            self.pacer.consume()
        self.network_calls += 1
        st, hd, body = self.client.get(url, accept=accept, timeout=timeout, **kw)
        self.cache.put(url, st, body)
        return st, hd, body

    def cached(self, url):
        return self.cache.get(url) is not None


class _Deferred:
    """A pacer whose sleep is DEFERRED until the request is known to be a real one.

    `registry_get` and `arxiv_get` call ``wait()`` BEFORE the client, so they cannot know the URL is
    already on disk; without this, a fully cached re-run would still sleep 1 s (3 s for arXiv) per
    reference and cost the same wall clock as the first pass, which defeats the cache. ``wait()``
    here only ARMS the real pacer; :meth:`CachedClient.get` calls :func:`consume` on a cache MISS,
    just before going to the network, and drops the arming on a hit. The arXiv sub-pacer shares one
    arming slot with its parent, so whichever leg is about to make the call is the one that sleeps.
    """

    def __init__(self, inner, state=None):
        self._inner = inner
        self._state = state if state is not None else {"pending": None}

    def wait(self):
        if self._inner is not None:
            self._state["pending"] = self._inner

    def backoff(self, seconds=None):
        self._state["pending"] = None
        if self._inner is not None:
            self._inner.backoff(seconds)

    @property
    def arxiv(self):
        from litkb.admit.resolver import arxiv_pacer_for
        return _Deferred(arxiv_pacer_for(self._inner), self._state)

    def consume(self):
        p = self._state.pop("pending", None)
        self._state["pending"] = None
        if p is not None:
            p.wait()

    def drop(self):
        self._state["pending"] = None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def deferred_pacer(pacer):
    """Wrap a `litkb.netutil.Pacer` so :class:`CachedClient` pays its sleep only on a real call."""
    return _Deferred(pacer)


# ── resolution ──────────────────────────────────────────────────────────────────────────

class StageBreaker:
    """A registry stage that is rate-limiting the whole run is SKIPPED, not retried per reference.

    MEASURED 2026-09-15, unauthenticated, from this laptop: ``api.semanticscholar.org`` answers
    **429 in 0.1 s** and ``export.arxiv.org`` **429 in 0.4 s**, on the first request, at any pace.
    The resolver's ladders then spend 10 s (Crossref/S2 back-off) and 15 + 30 s (arXiv's two) per
    reference before giving up — measured **~82 s per reference** over the first 11 references of
    the live run, against ~1 s for the Crossref leg alone. Over 658 references that is nine hours
    of sleeping in a stage that has answered nothing.

    So: after :data:`TRIP_AFTER` consecutive rate-limit answers, the stage is marked unavailable
    for the rest of the run and every later reference skips it. This CHANGES WHAT THE RATE MEANS
    and must be reported as such — a resolution rate measured with S2 and arXiv tripped is a
    **Crossref-only** rate, and the summary carries `stages_tripped` so it can never be quoted as
    anything else. Nothing is cached about a 429 (see :data:`CACHEABLE_STATUS`): the breaker is
    per-run state, so a later run with a key, or from another network, starts closed.
    """

    TRIP_AFTER = 2

    def __init__(self, trip_after=None):
        self.trip_after = trip_after if trip_after is not None else self.TRIP_AFTER
        self.streak = {}
        self.tripped = {}

    def is_open(self, source):
        return source in self.tripped

    def record(self, source, err):
        """`err` is the search function's error string ('' on success)."""
        rate_limited = bool(err) and (" 429" in err or " 0" in err or " 403" in err)
        if not rate_limited:
            self.streak[source] = 0
            return
        self.streak[source] = self.streak.get(source, 0) + 1
        if self.streak[source] >= self.trip_after and source not in self.tripped:
            self.tripped[source] = err

    def report(self):
        return dict(self.tripped)


@dataclasses.dataclass
class Resolution:
    state: str                      # resolved | ambiguous | unresolved
    doi: str | None = None
    source: str | None = None       # doi | crossref | semanticscholar | arxiv
    ratio: float | None = None
    reason: str = ""
    candidates: list = dataclasses.field(default_factory=list)
    registry_title: str | None = None
    archive_ok: bool = True
    #: RUN-DEPENDENT, AND THEREFORE NOT PERSISTED. Which stages this particular run skipped because
    #: their breaker was open — a property of the wire that day, not of the reference. It used to be
    #: appended to `reason`, which made the committed JSON differ between two runs over the same
    #: cache in 42 of 293 rows with no state and no DOI changed (round 2 of the referee,
    #: `Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md` §1). A reader diffing the artefact could not
    #: tell that from a real change, so it is dropped by `asdict` and read from here by whatever
    #: logs the run.
    transient: str = ""

    #: Fields that describe THE RUN rather than the resolution. Excluded from the persisted form.
    TRANSIENT_FIELDS = ("transient",)

    def asdict(self):
        return {k: v for k, v in dataclasses.asdict(self).items()
                if k not in self.TRANSIENT_FIELDS}


def _judge_all(cands, title, surname, year):
    """Every candidate of one stage judged. -> (accepted, best_ratio). `resolve_doi` keeps only the
    first acceptance and so cannot see a second one; ambiguity is exactly that second one."""
    accepted, best = [], 0.0
    for c in cands:
        ok, ratio, note = judge_candidate(c, title, surname, year)
        best = max(best, ratio)
        if ok:
            accepted.append((c, ratio, note))
    return accepted, best


#: Curly quotes and the Unicode dashes, folded before containment is tested. `_norm_text` strips
#: `string.punctuation`, which does NOT contain U+2019 — so "Residents’" and "Residents" differ
#: under the shared rule and a containment test without this fold misses a real parse artefact
#: (measured: Guo 2018 `b5`, 2026-09-15).
_QUOTES = str.maketrans({**{c: "'" for c in "‘’‛ʼ"},
                         **{c: '"' for c in "“”"},
                         **{c: "-" for c in "‐‑‒–—―"}})

#: A contained title is only a LABEL if the shorter side is a real title in its own right. Both
#: bounds exist to stop a generic stub ("Introduction", "Discussion") being read as a truncation of
#: whatever registry title happens to contain it. The length ratio is measured in CHARACTERS of the
#: normalised strings, per the referee's wording ("60 % of the longer's length").
CONTAINED_MIN_WORDS = 5
CONTAINED_MIN_FRACTION = 0.60


def _norm_title(s):
    return _norm_text(_ascii_fold(strip_tags(str(s or "").translate(_QUOTES))))


def title_containment(parsed, registry):
    """-> (words, fraction) when one normalised title CONTAINS the other and the shorter is a title
    in its own right; else None.

    This is a DISCRIMINATOR, never an acceptance rule. GROBID truncates a title at a comma and runs
    the journal name onto the end of one, and both produce a containment against the registry title;
    a wrong DOI (the Averkov class) does not. Accepting on containment alone would let a three-word
    stub match any registry title that contains it, so the caller uses this only to choose the
    terminal reason — the row stays ``unresolved`` either way and the 0.85 rule is untouched.
    """
    a, b = _norm_title(parsed), _norm_title(registry)
    if not a or not b:
        return None
    sh, lo = (a, b) if len(a) <= len(b) else (b, a)
    if sh not in lo:
        return None
    frac = len(sh) / len(lo)
    if len(sh.split()) < CONTAINED_MIN_WORDS or frac < CONTAINED_MIN_FRACTION:
        return None
    return len(sh.split()), frac


def _doi_without_title_ok(rec, ref):
    """No parsed title to compare: what is left must carry the decision on its own. -> (ok, note).

    decisions.yaml litkb-p0-foundation §15.15 allows the +/-1 year arm ONLY when the title and the
    first author both match the registry record. With no parsed title the title arm cannot match, so
    the year must be EXACT here — this branch deliberately does not go through `judge_candidate`,
    which would have to be handed the registry's own title as the reference's (a self-comparison
    scoring 1.00) and would then unlock a tolerance §15.15 does not grant.

    This is the one place where a wrong DOI can still be accepted: a DOI that resolves to a
    different work by the same first author in the same year passes (measured: Steenberg 2017 `b5`,
    whose printed DOI is Boone 2010 and whose reference is a different Boone 2010). The title ratio
    is what refuses that row in the corpus; strip the title and only author+year remain.
    """
    # BEGIN guard: p6 a DOI with no parsed title is verified on author and year
    family = ref.get("first_author") or ""
    if not family or not family_matches(rec["first_author"], family):
        return False, f"first author {rec['first_author']!r} != {family!r}"
    ry, fy = _year_int(rec["year"]), _year_int(ref.get("year"))
    if ry is None or fy is None or ry != fy:
        return False, f"year {ry} != {fy} (exact match required with no title, decisions.yaml 15.15)"
    # END guard: p6 a DOI with no parsed title is verified on author and year
    return True, "basis=author+year (no parsed title)"


def resolve_by_doi(ref, client, pacer):
    """The DOI path. The DOI decides: there is NO title fallback from here (module docstring)."""
    doi = ref.get("doi_norm") or normalize_doi(ref.get("doi"))
    rec, tried = confirm_doi(client, doi, pacer)
    if rec is None:
        return Resolution("unresolved", reason=f"doi_not_registered ({doi}; "
                          + ", ".join(f"{n}:{s}" for n, s in tried) + ")")
    ratio = max([title_match_ratio(ref.get("title") or "", t) for t in (rec["titles"] or [])] or [0.0])
    # BEGIN guard: p6 a reference DOI must resolve to the reference's own work
    note = f"ratio={ratio:.2f}"
    if ref.get("title"):
        if ratio < RESOLVE_TITLE_RATIO:
            cont = title_containment(ref["title"], rec["title"])
            # BEGIN guard: p6 a contained title is labelled, never resolved
            kind = "doi_title_contained" if cont else "doi_title_mismatch"
            # END guard: p6 a contained title is labelled, never resolved
            detail = (f"; contained {cont[0]} words, {cont[1]:.2f} of the longer" if cont else "")
            return Resolution("unresolved", reason=f"{kind} (ratio {ratio:.2f} < "
                              f"{RESOLVE_TITLE_RATIO}; registry title {rec['title'][:70]!r}{detail})",
                              ratio=ratio, registry_title=rec["title"], doi=None,
                              candidates=[{"doi": doi, "title": rec["title"], "year": rec["year"]}])
    else:
        # No parsed title to compare: the surname and the year must both agree, or the DOI is
        # unverifiable. A DOI accepted on nothing is the Averkov defect with extra steps.
        ok, note = _doi_without_title_ok(rec, ref)
        if not ok:
            return Resolution("unresolved", reason=f"doi_unverifiable (no parsed title; {note})",
                              registry_title=rec["title"])
    # END guard: p6 a reference DOI must resolve to the reference's own work
    return Resolution("resolved", doi=normalize_doi(doi), source="doi", ratio=round(ratio, 4),
                      reason=f"via=doi; registry={rec['registry']}; {note}",
                      registry_title=rec["title"])


def registry_stages(s2=None, ref=None):
    """The stage list, with the Semantic Scholar leg swapped for the batched client when one is given.

    The STAGE NAME is unchanged (`semanticscholar`), so the breaker, the `skipped=` reason tail and
    every per-stage number stay comparable with the run this is measured against. What changes is the
    request: `/paper/search?query=…&limit=3` becomes `/paper/search/match`, one narrow-field request
    per distinct title, cached on disk and backed off instead of retried per reference
    (`litkb.admit.s2`). The ACCEPTANCE RULES DO NOT CHANGE — the same `judge_candidate` judges the
    same candidate shape.
    """
    if s2 is None:
        return REGISTRY_STAGES
    from litkb.admit.s2 import search_semanticscholar_s2
    return tuple((name, search_semanticscholar_s2(s2, ref) if name == "semanticscholar" else fn)
                 for name, fn in REGISTRY_STAGES)


def resolve_by_search(ref, client, pacer, breaker=None, s2=None):
    """Title + first author + year, stage by stage, through `judge_candidate`."""
    title, surname, year = ref.get("title") or "", ref.get("first_author") or "", ref.get("year")
    if not title or not surname:
        return Resolution("unresolved", reason="no_title_or_author (nothing to search on)")
    best_overall = (0.0, "none", "-")
    skipped = []
    for source, search in registry_stages(s2, ref):
        if breaker is not None and breaker.is_open(source):
            skipped.append(source)
            continue
        try:
            cands, err = search(client, title, pacer)
        except Exception as e:                       # a registry outage is not a resolution
            return Resolution("unresolved", reason=f"registry_error {source}: {type(e).__name__}")
        if breaker is not None:
            breaker.record(source, err)
        accepted, best = _judge_all(cands, title, surname, year)
        if best > best_overall[0]:
            best_overall = (best, source, next((c.get("doi") or "-" for c in cands), "-"))
        if not accepted:
            continue
        # BEGIN guard: s2 proposes, crossref confirms
        if source == "semanticscholar":
            # A Semantic Scholar acceptance is a PROPOSAL, never a resolution. Its DOI goes to
            # Crossref and the CROSSREF record must pass the same shared rules against the
            # reference — which is what separates a book from its review, because S2's record for a
            # review DOI carries the BOOK's title and the BOOK's authorship and therefore satisfies
            # all three of our rules while pointing at a different work
            # (`Reports/LITKB_S2_BATCHING_2026-09-15.md` §4, three measured cases).
            kept, refusals, edition = [], [], None
            for c, ratio, note in accepted:
                verdict, why, _rec = confirm_s2_candidate(c, ref, client, pacer)
                if verdict == "confirmed":
                    kept.append((c, ratio, note))
                elif verdict == "ambiguous":
                    if edition is None:
                        edition = (c, ratio, why)
                else:
                    refusals.append(why)
            # Never a silent drop: a refusal is recorded even when another candidate of the
            # same stage confirms. The match endpoint returns one candidate, so this tail is
            # unreachable through `s2.py` today; the legacy `search_semanticscholar` returns three.
            refused_tail = ("; s2_refused=" + "; ".join(refusals)) if refusals else ""
            if not kept:
                # Terminal, and named. Every refusal is carried, never silently dropped.
                if edition is not None:
                    c, ratio, why = edition
                    return Resolution("ambiguous", source=source, ratio=round(ratio, 4), reason=why,
                                      candidates=[{"doi": normalize_doi(c.get("doi") or ""),
                                                   "ratio": round(ratio, 4),
                                                   "title": (c.get("titles") or [""])[0],
                                                   "year": c.get("year")}])
                return Resolution("unresolved", source=source, ratio=round(best, 4),
                                  reason="; ".join(refusals)[:400] or "s2_unconfirmed (no candidate)")
            accepted = kept
        # END guard: s2 proposes, crossref confirms
        dois = []
        for c, ratio, _note in accepted:
            d = (c.get("doi") or "").strip()
            d = d if d.startswith(ARXIV_DOI_PREFIX) else normalize_doi(d)
            if d and d not in [x[0] for x in dois]:
                dois.append((d, ratio, c))
        # BEGIN guard: p6 two accepted works are ambiguous, not a resolution
        if len(dois) > 1:
            return Resolution("ambiguous", source=source, ratio=round(max(r for _d, r, _c in dois), 4),
                              reason=f"{len(dois)} distinct works accepted at {source}",
                              candidates=[{"doi": d, "ratio": round(r, 4),
                                           "title": (c.get("titles") or [""])[0], "year": c.get("year")}
                                          for d, r, c in dois])
        # END guard: p6 two accepted works are ambiguous, not a resolution
        if not dois:
            return Resolution("unresolved", source=source,
                              reason=f"accepted at {source} but the candidate carries no DOI")
        d, ratio, c = dois[0]
        return Resolution("resolved", doi=d, source=source, ratio=round(ratio, 4),
                          reason=f"via={source}; ratio={ratio:.2f}; year={c.get('year')}"
                                 f"{refused_tail if source == 'semanticscholar' else ''}",
                          registry_title=(c.get("titles") or [""])[0],
                          archive_ok=not d.startswith(ARXIV_DOI_PREFIX))
    # The skipped-stage list is a fact about THIS RUN's breakers, not about the reference, so it
    # travels in `transient` and never in the persisted `reason`.
    return Resolution("unresolved",
                      reason=f"best={best_overall[1]}:{best_overall[0]:.2f}:{best_overall[2]}",
                      transient=(f"skipped={','.join(skipped)} (rate-limited)" if skipped else ""))


def resolve_reference(ref, client, pacer=None, breaker=None, s2=None):
    """DOI-first (§10 of the convention). -> :class:`Resolution`.

    `s2` only changes HOW the Semantic Scholar stage asks (see :func:`registry_stages`); it cannot
    reach a reference that carries a DOI, because the DOI still decides above it."""
    # BEGIN guard: p6 a reference with a DOI is decided by that DOI
    if ref.get("doi_norm") or normalize_doi(ref.get("doi")):
        return resolve_by_doi(ref, client, pacer)
    # END guard: p6 a reference with a DOI is decided by that DOI
    return resolve_by_search(ref, client, pacer, breaker, s2)


# ── the corpus index and the graph ──────────────────────────────────────────────────────

#: Columns that hold a work's STEM, in preference order. `id` is deliberately absent: the
#: bibliography CSV's `id` is a row number, and taking it produced graph edges whose cited work was
#: "14" and "34" (measured 2026-09-15, first graph run). A key must be the file-stem convention of
#: LITERATURE_CONVENTION.md or nothing.
KEY_COLUMNS = ("stem", "filed_stem", "file stem", "key")


def corpus_index(paths):
    """{normalised DOI: {"key": stem, "title": …, "source": csv}} from the manifest and the
    bibliography CSVs. The DOI is the join, per LITERATURE_CONVENTION.md (DOI-first)."""
    idx = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                low = {(k or "").strip().lower(): v for k, v in row.items()}
                d = normalize_doi(low.get("doi") or "")
                key = next((low[c].strip() for c in KEY_COLUMNS if (low.get(c) or "").strip()), "")
                if not d or not key:
                    continue
                idx.setdefault(d, {"key": key,
                                   "title": (low.get("title") or "").strip(),
                                   "source": os.path.basename(p)})
    return idx


def candidate_row(citing_key, ref, res):
    """A `candidates` row (§4.3): source `citation`, state `new`. NEVER admitted here."""
    # BEGIN guard: p6 a citation candidate is a lead, never an admission
    return {"source": "citation", "citing_work_key": citing_key, "citing_reference": ref["raw"][:2000],
            "raw_record": {"parsed": {k: ref[k] for k in ("authors", "year", "title", "journal",
                                                          "volume", "pages", "doi", "arxiv")},
                           "resolution": res.asdict()},
            "title": ref.get("title"), "authors": ref.get("authors"), "year": ref.get("year"),
            "doi": res.doi, "state": "new", "reason": res.reason, "admitted_work_id": None}
    # END guard: p6 a citation candidate is a lead, never an admission


# ── the run ─────────────────────────────────────────────────────────────────────────────

def process_tei(tei, citing_key, client, pacer=None, index=None, resolve=True, breaker=None, s2=None):
    """One paper: parsed references + mentions + resolutions + edges + candidates.

    When `s2` is an `litkb.admit.s2.S2Client`, the identifier-bearing references are looked up in ONE
    batch call before any per-item request (`batch_first`), and the S2 stage of the search leg uses
    the match endpoint. Nothing about the decision changes."""
    index = index or {}
    refs = parse_references(tei)
    if s2 is not None and resolve:
        from litkb.admit.s2 import batch_prefill
        batch_prefill(refs, s2)       # batch FIRST, into s2.prefill; per-item only for stragglers
    mentions = citation_mentions(tei)
    by_key = {r["ref_key"]: r for r in refs}
    counts = {}
    for m in mentions:
        # A MENTION IS ONE <ref> ELEMENT. `citation_mentions` emits one row per bounding box, and a
        # marker that wraps across a line carries two — correct as geometry, wrong as a count.
        # Measured 2026-09-15: 1,386 box rows over 1,182 elements, inflating 139 of 658 reference
        # rows and re-ordering the most-cited table. The box rows are unchanged; only this
        # aggregate counts the first box of each element.
        counts[m["target"]] = counts.get(m["target"], 0) + (1 if m["box_index"] == 0 else 0)
    rows, edges, cands = [], [], []
    for r in refs:
        res = (resolve_reference(r, client, pacer, breaker) if resolve
               else Resolution("unresolved", reason="resolution skipped"))
        row = dict(r, citing_work_key=citing_key, stage=STAGE, pipeline_version=PIPELINE_VERSION,
                   mention_count=counts.get(r["ref_key"], 0),
                   resolution=res.state, resolved_doi=res.doi, resolution_detail=res.asdict())
        rows.append(row)
        hit = index.get(res.doi) if (res.state == "resolved" and res.doi) else None
        if hit:
            edges.append({"citing_work_key": citing_key, "cited_work_key": hit["key"],
                          "cited_doi": res.doi, "ref_key": r["ref_key"],
                          "mention_count": counts.get(r["ref_key"], 0), "in_corpus": True})
        else:
            # Everything that is not an in-corpus edge is a lead: resolved-but-absent (a work we
            # could admit), ambiguous, and unresolved alike. The state travels with the row, so
            # P5's ingest can triage; nothing here decides to admit any of them.
            cands.append(candidate_row(citing_key, r, res))
    for m in mentions:
        m["citing_work_key"] = citing_key
        m["reference_title"] = (by_key.get(m["target"]) or {}).get("title", "")
    return {"references": rows, "citation_mentions": mentions, "edges": edges, "candidates": cands}


def write_jsonl(rows, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def resolution_summary(rows):
    out = {"references": len(rows), "resolved": 0, "ambiguous": 0, "unresolved": 0, "reasons": {}}
    for r in rows:
        out[r["resolution"]] = out.get(r["resolution"], 0) + 1
        if r["resolution"] != "resolved":
            key = (r["resolution_detail"]["reason"] or "").split("(")[0].split(";")[0].strip()[:40]
            out["reasons"][key] = out["reasons"].get(key, 0) + 1
    n = out["references"] or 1
    out["resolved_rate"] = round(out["resolved"] / n, 4)
    return out


def crossref_reference_list(client, doi, pacer=None):
    """Crossref's DEPOSITED reference list for a DOI -> (count, [dois/keys], status). The §14 P6
    gate's independent comparator: a publisher that deposits references gives a count our parse can
    be checked against. Many do not deposit; `reference-count` 0 means unknown, not zero."""
    import urllib.parse

    from litkb.admit.resolver import CROSSREF_WORK, _json, registry_get
    st, body = registry_get(client, CROSSREF_WORK.format(doi=urllib.parse.quote(doi, safe="/")), pacer)
    j = _json(body) if st == 200 else None
    msg = (j or {}).get("message") if isinstance(j, dict) else None
    if not isinstance(msg, dict):
        return None, [], st
    refs = msg.get("reference") or []
    return int(msg.get("reference-count") or len(refs)), [
        {"doi": normalize_doi(r.get("DOI") or ""), "unstructured": (r.get("unstructured") or "")[:200],
         "key": r.get("key") or ""} for r in refs], st

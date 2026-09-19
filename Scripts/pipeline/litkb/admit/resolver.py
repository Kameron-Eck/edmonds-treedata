"""Gate 0 — the DOI resolver (registries only, never the archive), and the text rules admission shares.

Ported from D:\\tools\\annas-mcp\\aa_fetch.py (design §10: "aa_fetch resolver -> admission checks 1-3").
Order: Crossref (query.bibliographic) -> Semantic Scholar -> arXiv Atom API. A candidate is accepted only on
normalised-title difflib ratio >= 0.85 AND a matching ASCII-folded first-author family name AND the year:
equal, or +/-1 (decisions.yaml litkb-p0-foundation §15.15 allows +/-1 only when title and first author both
match; judge_candidate tests those two first and refuses otherwise, so a +/-1 acceptance always has both).
An arXiv-stage hit yields the 10.48550 DOI form for the record only, never an archive query.

Every function takes an injected client (anything with .get(url, accept=, timeout=)) and pacer, so tests
never touch the network. Stdlib only.
"""
import difflib
import json
import re
import string
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET

from litkb.netutil import redact

REGISTRY_MIN_INTERVAL = 1.0
REGISTRY_BACKOFF = 10.0
ARXIV_MIN_INTERVAL = 3.0          # arXiv API guidance: no more than one request every 3 s
ARXIV_BACKOFFS = (15.0, 30.0)     # on 429 / no response: two retries, then give up
RESOLVE_TITLE_RATIO = 0.85
ARXIV_DOI_PREFIX = "10.48550/arXiv."
CROSSREF_SEARCH = "https://api.crossref.org/works?query.bibliographic={q}&rows=3"
CROSSREF_WORK = "https://api.crossref.org/works/{doi}"
S2_SEARCH = ("https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=3"
             "&fields=externalIds,title,year,authors")
ARXIV_SEARCH = "http://export.arxiv.org/api/query?search_query={q}&max_results=3"
ARXIV_ID_LIST = "http://export.arxiv.org/api/query?id_list={id}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
_TAG_RE = re.compile(r"<[^>]*>")


# ---------------------------------------------------------------- text rules

def normalize_doi(doi):
    """The canonical DOI: litkb.textnorm.normalize_doi, the Python twin of the database's litkb.norm_identifier."""
    from litkb.textnorm import normalize_doi as _canonical
    return _canonical(doi)


def strip_tags(s):
    """Crossref titles carry JATS/MathML markup (10.1016/j.laa.2010.09.001 does)."""
    return _TAG_RE.sub(" ", str(s or ""))


#: What a PDF text extractor emits where it could not decode a glyph, and where it broke a word.
#: U+FFFD is the replacement character — a ligature or an accented letter the text layer could not
#: render, and Köpcke 2010's first page reads "K<FFFD>pcke"; U+00AD is a soft hyphen; U+FFFE is the
#: noncharacter pypdfium2 emits at a line-break hyphen (measured on Alwan 1988 p3; see
#: extract/reconcile.HYPHEN_NONCHAR, which removes it from stage 5's stored TEXT for the same
#: reason). None of the three carries information, and all three are DROPPED rather than turned into
#: a separator: dropping rejoins a word the extractor split, while a separator would split a word
#: that was never split. `work/20260915-access-layer` applies the same rule to the indexed text and
#: the search query alike (migration 0018, `litkb.norm_search_text`); this is the comparison side of
#: it. Written with escapes, never as literals — two of the three are invisible, and this repository
#: has already committed one guard whose literal nobody could see.
UNDECODABLE = "�­￾"
_UNDECODABLE_RE = re.compile("[" + UNDECODABLE + "]")


def _norm_text(s):
    s = _UNDECODABLE_RE.sub("", s or "").lower()
    s = "".join(" " if c in string.punctuation or c.isspace() else c for c in s)
    return " ".join(s.split())


def _ascii_fold(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c))


def title_match_ratio(a, b):
    ta, tb = _norm_text(_ascii_fold(strip_tags(a))), _norm_text(_ascii_fold(strip_tags(b)))
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb).ratio()


def family_name(name):
    """First-author family name, folded to lowercase alphanumerics.
    'Efron, B.' -> 'efron';  'Bradley Efron' -> 'efron';  'Efron, B.; Tibshirani, R.' -> 'efron'."""
    n = _ascii_fold(name).split(";")[0].split(" and ")[0].strip()
    if "," in n:
        n = n.split(",")[0]
    else:
        parts = n.replace(".", " ").split()
        n = parts[-1] if parts else ""
    return "".join(c for c in n.lower() if c.isalnum())


def family_matches(candidate, requested):
    """Equal after ASCII-fold + lowercase + alnum-only, OR the requested (joined convention) surname
    ends with the registry's last particle ('vandenhout' vs S2's unsplit 'Van Den Hout' -> 'hout').
    One direction only: a requested 'Wang' never accepts a candidate 'Hwang'."""
    a, b = family_name(candidate), family_name(requested)
    if not a or not b:
        return False
    return a == b or (len(a) >= 3 and b.endswith(a))


def _year_int(v):
    m = re.search(r"\d{4}", str(v if v is not None else ""))
    return int(m.group()) if m else None


def judge_candidate(cand, title, surname, year):
    """-> (accepted, ratio, note).  note is `year=<y>` on acceptance (the log carries it)."""
    ratio = max([title_match_ratio(title, t) for t in (cand.get("titles") or [])] or [0.0])
    if ratio < RESOLVE_TITLE_RATIO:
        return False, ratio, f"title ratio {ratio:.2f} < {RESOLVE_TITLE_RATIO}"
    if not family_matches(cand.get("family"), surname):
        return False, ratio, f"first author {cand.get('family')!r} != {surname!r}"
    cy, wy = _year_int(cand.get("year")), _year_int(year)
    if cy is None or wy is None:
        return False, ratio, f"year unknown (candidate {cy}, requested {wy})"
    if cy == wy:
        return True, ratio, f"year={cy}"
    # BEGIN guard: year rule (decisions.yaml §15.15)
    if abs(cy - wy) == 1:
        return True, ratio, f"year={cy} (requested {wy}; +/-1 accepted as online-first vs print)"
    # END guard: year rule (decisions.yaml §15.15)
    return False, ratio, f"year {cy} != requested {wy}"


# ---------------------------------------------------------------- registry HTTP

def arxiv_pacer_for(pacer):
    """arXiv's own 3 s pacer, attached once to the shared registry pacer (same sleep/clock), so
    Crossref/Semantic Scholar keep their 1 s pace and every arXiv call shares one 3 s gate."""
    from litkb.netutil import Pacer

    if pacer is None:
        return None
    ap = getattr(pacer, "arxiv", None)
    if ap is None:
        ap = pacer.arxiv = Pacer(interval=ARXIV_MIN_INTERVAL, sleep=pacer.sleep,
                                 backoff=ARXIV_BACKOFFS[0], clock=pacer.clock)
    return ap


def registry_get(client, url, pacer, accept="application/json"):
    """1 s pacing between registry calls; one 10 s back-off on 429, then give up."""
    for attempt in (0, 1):
        if pacer is not None:
            pacer.wait()
        st, _, body = client.get(url, accept=accept, timeout=60)
        if st == 429 and attempt == 0:
            if pacer is not None:
                pacer.backoff()
            continue
        return st, body or b""


def arxiv_get(client, url, pacer):
    """arXiv only: 3 s pacing; on 429 or no response (status 0) back off 15 s, then 30 s, then
    give up and return the last status.  `pacer` is the registry pacer; its arXiv pacer is used."""
    ap = arxiv_pacer_for(pacer)
    st, body = 0, b""
    for delay in (None,) + ARXIV_BACKOFFS:
        if ap is not None and delay is None:
            ap.wait()
        elif ap is not None:
            ap.backoff(delay)
        st, _, body = client.get(url, accept="application/atom+xml", timeout=60)
        if st and st != 429:
            break
    return st, body or b""


def _json(body):
    try:
        return json.loads((body or b"").decode("utf-8", "replace"))
    except Exception:
        return None


def search_crossref(client, title, pacer):
    """-> (candidates, error).  Crossref splits 'X: Y' into title/subtitle, so both forms are kept."""
    st, body = registry_get(client, CROSSREF_SEARCH.format(q=urllib.parse.quote(title, safe="")), pacer)
    j = _json(body) if st == 200 else None
    if j is None:
        return [], f"crossref status {st}"
    out = []
    for it in ((j.get("message") or {}).get("items") or []):
        titles = [t for t in (it.get("title") or []) if t]
        subs = [t for t in (it.get("subtitle") or []) if t]
        forms = titles + ([f"{titles[0]}: {subs[0]}"] if titles and subs else [])
        auth = (it.get("author") or [{}])[0] or {}
        parts = (((it.get("issued") or {}).get("date-parts") or [[None]])[0] or [None])
        out.append({"doi": it.get("DOI") or "", "titles": forms,
                    "family": auth.get("family") or auth.get("name") or "", "year": parts[0]})
    return out, ""


def search_semanticscholar(client, title, pacer):
    st, body = registry_get(client, S2_SEARCH.format(q=urllib.parse.quote(title, safe="")), pacer)
    j = _json(body) if st == 200 else None
    if j is None:
        return [], f"semanticscholar status {st}"
    out = []
    for it in (j.get("data") or []):
        ext = it.get("externalIds") or {}
        doi = ext.get("DOI") or (ARXIV_DOI_PREFIX + str(ext["ArXiv"]) if ext.get("ArXiv") else "")
        auths = it.get("authors") or []
        out.append({"doi": doi, "titles": [it.get("title") or ""],
                    "family": (auths[0] or {}).get("name", "") if auths else "",
                    "year": it.get("year")})
    return out, ""


def search_arxiv(client, title, pacer):
    q = urllib.parse.quote(f'ti:"{title}"', safe="")
    st, body = arxiv_get(client, ARXIV_SEARCH.format(q=q), pacer)
    if st != 200:
        return [], f"arxiv status {st}"
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return [], "arxiv atom unparseable"
    out = []
    for e in root.findall(ATOM_NS + "entry"):
        aid = re.sub(r"v\d+$", "", (e.findtext(ATOM_NS + "id") or "").rsplit("/abs/", 1)[-1].strip())
        au = e.find(ATOM_NS + "author")
        out.append({"doi": ARXIV_DOI_PREFIX + aid if aid else "",
                    "titles": [" ".join((e.findtext(ATOM_NS + "title") or "").split())],
                    "family": au.findtext(ATOM_NS + "name") if au is not None else "",
                    "year": (e.findtext(ATOM_NS + "published") or "")[:4]})
    return out, ""


REGISTRY_STAGES = (("crossref", search_crossref), ("semanticscholar", search_semanticscholar),
                   ("arxiv", search_arxiv))


# ------------------------------------------------- S2 PROPOSES, CROSSREF CONFIRMS

#: A review of a book carries the REVIEWED BOOK'S TITLE, and Semantic Scholar's record for such a DOI
#: carries the book's title AND the book's authorship — so the ratio filter, the first-author
#: discriminator and the year rule all agree while the DOI points at a different work. Measured on
#: three real references (Alwan 1988 b13, Burnicki 2011 b23, Hall 1985 b10 —
#: `Reports/LITKB_S2_BATCHING_2026-09-15.md` §4). The rules did not fail; the registry merged a book
#: with its review. The fix is therefore not a new threshold but a SECOND REGISTRY: an S2 candidate
#: never resolves on S2 data alone — its DOI is looked up at Crossref and the CROSSREF record must
#: pass the same shared rules against the reference. S2's authorship merges are thereby ignored.
REVIEW_TITLE_MARKERS = ("review of", "book review", "reviewed work", "reviewed works",
                        "review essay", "review article")
#: Crossref's `container-title` for a journal's review section.
REVIEW_CONTAINER_MARKERS = ("book review", "book reviews", "review section", "reviews of books",
                            "new books", "books received")
#: An explicit edition cue in a reference's raw string; with publisher-and-no-journal, the two tests
#: for "this reference is a book".
_EDITION_CUE = re.compile(r"\b(\d+(?:st|nd|rd|th)\s+ed(?:ition|\.)?|"
                          r"(?:second|third|fourth|fifth)\s+edition)\b", re.I)
#: Crossref's OWN spelling for a record that is a review, in `type` or in `subtype`. Measured on the
#: three real cases: JSTOR files its reviews as plain `journal-article` and carries no `subtype`, so
#: this is completeness, not the signal that fires on them.
REVIEW_RECORD_TYPES = ("book-review", "review", "peer-review")
#: A reviewer's surname is not one letter. Crossref parses some records' GIVEN name into the family
#: slot (measured: 10.2307/2529186, Fleiss, comes back as ['d', 'fleiss']), which has the exact shape
#: of a prepended reviewer and is not one — the same work, badly parsed. TWO letters is the floor
#: because "Li" and "Wu" are real surnames; one letter is an initial.
MIN_SURNAME_LEN = 2


def _families(authors):
    """The family names of a registry record's author list, folded by the shared rule."""
    return [family_name(a.get("family") or a.get("given") or a.get("name") or "")
            for a in (authors or []) if isinstance(a, dict)]


def reference_is_book(ref):
    """A parsed reference that presents as a BOOK: a publisher and no journal, or an edition cue."""
    if (ref.get("publisher") or "").strip() and not (ref.get("journal") or "").strip():
        return True
    return bool(_EDITION_CUE.search(str(ref.get("raw") or "")))


def _ref_families(ref):
    """The family names of the REFERENCE's own parsed author list, folded by the shared rule."""
    return [family_name(a.get("family") or "") for a in (ref.get("authors") or [])
            if isinstance(a, dict) and (a.get("family") or "")]


def _record_type_is_review(rec):
    """-> the detail string when Crossref's OWN `type`/`subtype` says review, else ''."""
    for field in ("raw_type", "raw_subtype"):
        v = (rec.get(field) or "").strip().lower()
        if v and v in REVIEW_RECORD_TYPES:
            return f"crossref {field.replace('raw_', '')} is {v!r}"
    return ""


def review_signature(rec, ref):
    """-> the measured detail string when the Crossref record is a REVIEW of the cited work, else ''.

    Every signature here is a measurement about the RECORD, and NONE of them asks whether the
    reviewer happens to share the reference's first author's surname. Round 2 of the referee
    (`Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md` §4) planted exactly that case — a review whose
    reviewer is also called by the book's author's surname — and the old detector, which fired only
    when the head of the list was NOT the reference's first author, was blind to it. On the 9.3 % of
    references that parse neither a journal nor a publisher the type test cannot catch the survivor
    either, so the review resolved as the book. The surname comparison is gone from the decision:

    * Crossref's own `type`/`subtype` says review;
    * the record's title begins with a review marker;
    * its container is a journal's review section;
    * **the author-count signature** — the record's list is exactly ONE longer than the reference's
      own list and the reference's list is that list's SUFFIX. That is Crossref's encoding of "the
      reviewer, then the reviewed work's authors", and it is true whatever the reviewer is called;
    * the original prefix shape, kept unchanged, for references whose own author list did not parse.
    """
    why = _record_type_is_review(rec)
    if why:
        return why
    if (rec.get("raw_type") or "") != "journal-article":
        return ""
    t = _norm_text(_ascii_fold(strip_tags(rec.get("title") or "")))
    for m in REVIEW_TITLE_MARKERS:
        if t.startswith(m):
            return f"crossref title begins {m!r}"
    ven = _norm_text(_ascii_fold(rec.get("venue") or ""))
    if any(m in ven for m in REVIEW_CONTAINER_MARKERS):
        return f"crossref container {rec.get('venue')!r} is a review section"
    fams = _families(rec.get("authors"))
    want = family_name(ref.get("first_author") or "")
    ours = _ref_families(ref)
    # THE NAME-INDEPENDENT TEST. One extra author at the HEAD, the reference's own list underneath
    # it. The extra name must be a plausible surname or this fires on the Fleiss parse artefact
    # (['d', 'fleiss'] against a reference whose only author is Fleiss), which is the same work
    # badly parsed and not a review; that row keeps falling through to `crossref_author_mismatch`.
    if ours and len(fams) == len(ours) + 1 and len(fams[0]) >= MIN_SURNAME_LEN \
            and all(family_matches(g, o) for g, o in zip(fams[1:], ours)):
        return (f"crossref author list {fams} is the reference's own list {ours} with exactly one "
                f"extra name {fams[0]!r} at the head — the reviewer, then the work")
    # The original shape, for a reference whose own author list did not parse: the head is not the
    # reference's first author and that first author appears later. Kept at its own three-letter
    # floor; it is a strictly additional signature, never a relaxation of the one above.
    if want and len(fams) > 1 and len(fams[0]) >= 3 and not family_matches(fams[0], want):
        later = [i for i, f in enumerate(fams[1:], 1) if family_matches(f, want)]
        if later:
            return (f"crossref author list {fams} is prefixed by {fams[0]!r}; the reference's first "
                    f"author {want!r} appears at position {later[0]} — the reviewer, then the work")
    return ""


def reference_has_no_type(ref):
    """A reference that parsed NEITHER a journal NOR a publisher: 61 of the 658 P6 references (9.3 %,
    measured 2026-09-15). `reference_is_book` cannot speak for these, so `type_mismatch` is blind and
    the review detector is the only guard — which is the hole round 2 walked through."""
    return not (ref.get("journal") or "").strip() and not (ref.get("publisher") or "").strip()


def review_hint(rec, ref):
    """-> a detail string for a WEAKER review signal, else ''. Used ONLY for the type-blind class.

    `review_signature` is what refuses a record outright. This is the second net for references that
    carry neither a journal nor a publisher, where nothing else can speak: for those, ANY review
    signal in the record is enough to withhold confirmation. The markers are matched anywhere in the
    title rather than only at its head, and the author shape drops the surname-inequality condition —
    the very condition the planted same-surname reviewer exploited — keeping only the requirement
    that the record carry an EXTRA person, which is the reviewer there has to be.

    **Gate 0 is always in this class.** `resolve_doi` builds its reference dict as
    ``{title, first_author, year}``: no journal, no publisher and no author list, so this net runs on
    every candidate at the acquisition door and `reference_is_book` never can. That is deliberate —
    it is the door that hands a DOI to a fetcher — and it is why the author clause below must not
    refuse an ordinary record.

    It is deliberately NOT applied to references that parsed a journal or a publisher: those already
    have `review_signature` and `reference_is_book` over them, and a broader net there would start
    refusing genuine articles.
    """
    if not reference_has_no_type(ref):
        return ""
    t = _norm_text(_ascii_fold(strip_tags(rec.get("title") or "")))
    for m in REVIEW_TITLE_MARKERS:
        if m in t:
            return f"crossref title contains {m!r}"
    ven = _norm_text(_ascii_fold(rec.get("venue") or ""))
    if any(m in ven for m in REVIEW_CONTAINER_MARKERS):
        return f"crossref container {rec.get('venue')!r} is a review section"
    fams = _families(rec.get("authors"))
    want = family_name(ref.get("first_author") or "")
    ours = _ref_families(ref)
    if not (want and len(fams) > 1 and len(fams[0]) >= MIN_SURNAME_LEN):
        return ""
    # THERE MUST BE AN EXTRA PERSON for there to be a reviewer. Without this count test the net
    # refuses a genuine paper by two authors who share a surname — Crossref ['wang', 'wang'] against
    # a reference whose first author is Wang — for EVERY type-blind reference, and gate 0's reference
    # dict is always type-blind. Where the reference's own list did not parse the count cannot be
    # compared at all, and this net falls back to the original different-surname shape: with nothing
    # to measure against, there is nothing surname-independent left to say.
    if ours:
        if len(fams) <= len(ours):
            return ""
    elif family_matches(fams[0], want):
        return ""
    later = [i for i, f in enumerate(fams[1:], 1) if family_matches(f, want)]
    if later:
        return (f"crossref author list {fams} carries the reference's first author {want!r} at "
                f"position {later[0]}, behind {fams[0]!r}")
    return ""


def _shares_authorship(rec, ref):
    """The record and the reference are plausibly the SAME WORK by authorship: same first author, or
    the record's first author is somewhere in the reference's own author list (a later edition or a
    sibling printing often reorders or drops a co-author). Used ONLY to separate a sibling edition
    from an unrelated work — never to accept anything."""
    first = rec.get("first_author") or ""
    if family_matches(first, ref.get("first_author") or ""):
        return True
    ours = [family_name(a.get("family") or "") for a in (ref.get("authors") or [])
            if isinstance(a, dict)]
    return bool(first) and any(family_matches(first, o) for o in ours if o)


def confirm_s2_candidate(cand, ref, client, pacer=None):
    """S2 PROPOSES, CROSSREF CONFIRMS. -> (verdict, reason, record-or-None).

    verdict is ``confirmed`` (the Crossref record passes the shared rules against the reference),
    ``ambiguous`` (a sibling edition — the same work at another year, resolved to nothing) or
    ``refused``. Every refusal carries its OWN reason, formatted ``name (detail)`` so a reason
    histogram buckets on the name exactly as `doi_title_mismatch` does; nothing is dropped silently.
    The ORDER matters: review first, because a review of a book is also a type mismatch and would
    otherwise be filed under the weaker name; the edition test before the first-author test, because
    a sibling edition is ambiguous rather than refused.
    """
    from litkb.admit.registry import crossref_record

    raw = (cand.get("doi") or "").strip()
    if not raw:
        return "refused", "s2_candidate_has_no_doi (nothing to confirm)", None
    if raw.lower().startswith(ARXIV_DOI_PREFIX.lower()):
        # THE ONE PATH THIS RULE DOES NOT COVER, named rather than hidden. Crossref is not the
        # registry for the 10.48550 form, so there is nothing to confirm it against here. It is a
        # RECORD-ONLY key: stage 6 marks the resolution `archive_ok=False`, gate 0 (`resolve_doi`)
        # returns no DOI for it at all, and `acquire.annas.fetch_one` refuses the form outright, so
        # no caller can turn it into an archive request. Until round 2 of the referee
        # (`Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md` §5) that last sentence was FALSE at
        # gate 0 — there was no flag on that return and its only caller handed the DOI to the
        # fetcher. The class this rule closes — a journal's review of a cited book — cannot occur on
        # an arXiv preprint, so the exposure is stated, not argued away.
        return "confirmed", (f"s2_arxiv_doi_unconfirmed ({raw}; Crossref is not this DOI's registry; "
                             f"kept record-only)"), None
    doi = normalize_doi(raw)
    if not doi:
        return "refused", f"s2_candidate_has_no_doi ({raw!r} is not a DOI)", None
    rec, st = crossref_record(client, doi, pacer)
    if rec is None:
        return "refused", f"crossref_not_registered ({doi}; crossref status {st})", None
    why = review_signature(rec, ref)
    if why:
        return "refused", f"review_record ({doi}; {why})", rec
    # The type-blind class: a reference with neither a journal nor a publisher has no `type_mismatch`
    # over it, so ANY review signal in the record withholds confirmation. Its own name, so the reason
    # histogram keeps saying which test spoke.
    why = review_hint(rec, ref)
    if why:
        return "refused", (f"review_suspected ({doi}; the reference parsed neither a journal nor a "
                           f"publisher, so nothing else can speak for its type; {why})"), rec
    if reference_is_book(ref) and (rec.get("raw_type") or "") == "journal-article":
        return "refused", (f"type_mismatch ({doi}; the reference is a book, publisher "
                           f"{ref.get('publisher')!r}; crossref says journal-article in "
                           f"{rec.get('venue')!r})"), rec
    ratio = max([title_match_ratio(ref.get("title") or "", t) for t in (rec.get("titles") or [])]
                or [0.0])
    if ratio < RESOLVE_TITLE_RATIO:
        return "refused", (f"crossref_title_ratio ({doi}; ratio {ratio:.2f} < {RESOLVE_TITLE_RATIO}; "
                           f"crossref title {(rec.get('title') or '')[:70]!r})"), rec
    cy, wy = _year_int(rec.get("year")), _year_int(ref.get("year"))
    if cy is not None and wy is not None and abs(cy - wy) > 1 and _shares_authorship(rec, ref):
        return "ambiguous", (f"edition_mismatch ({doi}; same title, shared authorship, crossref "
                             f"{cy} vs reference {wy} — a sibling edition, not this one)"), rec
    # MISSING vs CONTRADICTED (referee task 3, 2026-09-18). A Crossref record with NO author at
    # all says nothing about authorship either way -- it is uninformative, not evidence against
    # the reference -- so it is no longer refused on that alone. Before this, `crossref_no_author`
    # fired here for every authorless record, real matches included: Swain 1978 (Abercrombie b16)
    # and Chrisman 1989 (Burnicki b12) both have Crossref records with no `author` array and were
    # lost to it. A PRESENT author that disagrees remains evidence and still refuses, unchanged.
    #
    # Dropping that refusal also removes the ONLY thing standing between an authorless record and
    # `family_matches`, which would otherwise compare against `""`. So an authorless record is
    # admitted ONLY where the two checks that do not depend on authorship both independently
    # clear: the title ratio, already enforced above for every candidate, and the year, enforced
    # below exactly as it always was for an authored record. Neither is relaxed for this branch.
    if rec.get("first_author") or "":
        if not family_matches(rec["first_author"], ref.get("first_author") or ""):
            return "refused", (f"crossref_author_mismatch ({doi}; crossref first author "
                               f"{rec['first_author']!r} != reference {ref.get('first_author')!r})"), rec
    if cy is None or wy is None:
        return "refused", f"crossref_year_unknown ({doi}; crossref {cy}, reference {wy})", rec
    if abs(cy - wy) > 1:
        return "refused", f"crossref_year_mismatch ({doi}; crossref {cy} != reference {wy})", rec
    if not (rec.get("first_author") or ""):
        return "confirmed", (f"crossref_confirmed ({doi}; ratio {ratio:.2f}; year {cy}; crossref "
                             f"carries no author for this record -- admitted on title ratio and "
                             f"year alone)"), rec
    return "confirmed", f"crossref_confirmed ({doi}; ratio {ratio:.2f}; year {cy})", rec


def resolve_doi(title, surname, year, client=None, pacer=None):
    """-> (doi, source, evidence) or (None, None, reason).
    evidence: `via=<source>; ratio=0.xx; year=<y>`;  reason: `best=<source>:<ratio>:<candidate doi>`.
    An accepted hit whose DOI is the ``10.48550/`` arXiv form still returns None — whichever stage
    proposed it, not only the arXiv stage. That DOI is for the record only: it appears in the reason
    as ``arxiv_record_only=…; archive_ok=False``, and the archive is never asked for it.
    `acquire.annas.fetch_one` refuses the form independently, so the property holds even if a future
    caller reaches it another way.

    S2 PROPOSES, CROSSREF CONFIRMS: a Semantic Scholar acceptance is re-checked at Crossref by
    :func:`confirm_s2_candidate` and refused if that record is a review, a type mismatch, a sibling
    edition, or simply fails the shared rules. Each refusal is named in the `s2_refused=` tail."""
    if client is None:
        from litkb.netutil import Client
        client = Client()
    best = None                                   # (ratio, source, doi)
    refused = []                                  # S2 candidates Crossref would not confirm
    for source, search in REGISTRY_STAGES:
        try:
            cands, _ = search(client, title, pacer)
        except Exception:
            cands = []
        for c in cands:
            ok, ratio, note = judge_candidate(c, title, surname, year)
            if best is None or ratio > best[0]:
                best = (ratio, source, c.get("doi") or "-")
            if not ok:
                continue
            # BEGIN guard: s2 proposes, crossref confirms
            if source == "semanticscholar":
                # The same rule the stage-6 resolver applies, at the acquisition door: an S2
                # candidate is a PROPOSAL. Gate 0 hands its DOI straight to the fetcher, so an
                # unconfirmed one downloads the review instead of the book.
                verdict, why, _rec = confirm_s2_candidate(
                    c, {"title": title, "first_author": surname, "year": year}, client, pacer)
                if verdict != "confirmed":
                    refused.append(why)
                    continue
            # END guard: s2 proposes, crossref confirms
            # GATE 0 RETURNS NOTHING THE ARCHIVE MAY BE ASKED FOR. The `source == "arxiv"` half was
            # always here; the DOI-form half is the round-2 fix. An S2 candidate carrying only an
            # arXiv id yields a `10.48550/…` DOI, which `normalize_doi` accepts as truthy, so it used
            # to be RETURNED — and gate 0's only caller hands what it returns straight to `fetch_one`
            # (`Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md` §5). The DOI is for the record only:
            # it appears in the reason, marked `archive_ok=False`, and no DOI is returned.
            cd = (c.get("doi") or "").strip()
            if cd.lower().startswith(ARXIV_DOI_PREFIX.lower()):
                return None, None, (f"arxiv_record_only={cd}; archive_ok=False; "
                                    f"best={source}:{ratio:.2f}:{cd}")
            if source == "arxiv" or not normalize_doi(cd):
                return None, None, f"best={source}:{ratio:.2f}:{cd or '-'}"
            d = normalize_doi(cd)
            # A refusal is kept even when a later candidate confirms: never a silent drop.
            kept_tail = ("; s2_refused=" + "; ".join(refused)) if refused else ""
            return d, source, f"via={source}; ratio={ratio:.2f}; {note}{kept_tail}"
    tail = ("; s2_refused=" + "; ".join(refused)) if refused else ""
    if best is None:
        return None, None, "best=none" + tail
    return None, None, f"best={best[1]}:{best[0]:.2f}:{best[2]}{tail}"


def resolution_log_line(status, stem, title, doi, evidence):
    return redact(" | ".join([status, stem, (title or "")[:60], doi or "-", evidence or ""]))

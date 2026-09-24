"""The identifier model's PURE half (S4.5 item 1, migration 0032): the scheme registry's seed, the
per-scheme normaliser (the Python twin of `litkb.norm_identifier`), the validators, scheme detection,
and the ZERO-REQUEST (Wave 0) derivations Stage A calls. Nothing here makes a request or touches the
database; `litkb.admit.harvest` is the half that writes.

    norm("isbn", "ISBN 0-306-40615-2")      -> "9780306406157"   (a valid ISBN-10 is stored as its ISBN-13)
    norm("pmcid", "7391")                   -> "PMC7391"         (stored WITH the prefix; LINKAGE §3.6 trap 3)
    clean_doi("(doi:10.1234/abc)")          -> "10.1234/abc"     (bracket balance; §3.5 item 1)
    detect_schemes("12345678")              -> ("oclc", "mag", "core", ..., "pmid")   (a SET, PMID last)
    arxiv_to_doi("2206.01062v2")            -> a CANDIDATE row: 10.48550/arxiv.2206.01062, asserted_by 'deterministic'

WHERE EACH RULE COMES FROM (Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md; every mechanism is a
RELAYED design, UNVALIDATED in the CLAUDE.md §3.4c sense until a referee scores it on litkb's rows):
  * §3.5 item 1 — Zotero.Utilities.cleanDOI (zotero/utilities@4051881): a trailing ) ] } is part of the
    DOI only when the DOI itself opened it. AGPL: the RULE is re-implemented here, no code copied.
  * §3.5 item 2 — isbnlib canonical / check_digit13 / to_isbn13 (xlcnd/isbnlib@ddc62f2): canonicalise,
    re-derive the check digit instead of trusting the input's, REJECT rather than coerce, screen the
    all-zero sentinels. LGPL: re-implemented from the published ISBN arithmetic, no code copied.
  * §3.5 items 3-4 — idutils (inveniosoftware/idutils@2623d78) regex SHAPES and
    `detect_identifier_schemes` returning every match; Zotero's discipline on top: PMID last, and only
    when it is the whole string. The shapes are facts about the identifiers; the regexes are written here.
  * §3.5 item 5 — oc_idmanager DOIManager.normalise, the `s[s.index("10."):]` slice, as the SECOND pass
    (it is `litkb.textnorm.normalize_doi`'s own cut, so that function is the pass).
  * DO NOT PORT (§3.5): oc_idmanager's ISBN-13 check digit (`val = 3 if val == 1 else val == 1` assigns
    a boolean; about one arbitrary 13-digit string in ten passes). `isbn13_valid` below uses the ISBN
    standard's alternating 1,3 weights and its test asserts the one-in-ten failure does NOT reproduce.
  * §3.6 — the three normalisation traps: a DOI is lower-cased to key litkb's table and UPPER-cased to
    ask Wikidata (`doi_for_provider`); DataCite lower-cases what it returns (the lower-cased key is
    right); a PMCID is stored WITH `PMC` and asked WITHOUT it (`pmcid_for_provider`).

NOT HERE, and why:
  * `isbnlib.editions(isbn, 'merge')` queries remote services — it is not a zero-request derivation, so it
    is a Stage B/F call (S4.6), not Wave 0.
  * ISBN -> ISBN-A DOI needs the ISBN range table (which digits are the registrant, which the
    publication), a data file from the International ISBN Agency that isbnlib ships and litkb does not.
    `isbn_a_doi` therefore derives it from a HYPHENATED ISBN only and answers None for a bare one —
    never a guessed split.
  * shortDOI expansion is ONE request (Handle HS_ALIAS), not zero: `shortdoi_alias_url` names the call
    and `parse_hs_alias` parses its answer; the call itself is Stage A's (C2a).
"""
import re

from litkb.textnorm import normalize_doi

#: The DataCite prefix arXiv mints its versionless DOIs under (arXiv help pages; LINKAGE §2.3 Wave 0,
#: ASSERTED-BY-PUBLISHER). The same string as `litkb.admit.resolver.ARXIV_DOI_PREFIX`, lower-cased,
#: because a stored DOI is lower-cased (0014 D1) and DataCite returns it lower-cased (§3.6 trap 2).
ARXIV_DOI_PREFIX = "10.48550/arxiv."

#: Provenance a zero-request derivation carries (LINKAGE §3.2 item 1: `deterministic` is a first-class
#: provenance value, beside the services).
DETERMINISTIC = "deterministic"

# ── the scheme registry's seed (the database's `litkb.scheme_registry` is the authority; migration 0032
#    seeds it from the same rows and qc/test_litkb_s45_identity.py holds the two equal) ────────────────
#
# Fields: label, normaliser, distinct (a value belongs to at most ONE work — the partial unique index
# covers only these), strong (a confirmed value that DIFFERS from an existing work's means a different
# record: the title-duplicate review is skipped — 0014's list in litkb.admit less `handle`, which the plan
# makes non-distinct; a strong scheme must be distinct or type-scoped — the registry's CHECK
# `scheme_registry_strong_is_identity` — and counts only where it is the CANDIDATE's identity, so an ISBN
# on a report is not strong for that report), registry (check 1 confirms it against a registry record — today's `doi arxiv isbn` in
# _check_registry, 0020, carried over unchanged), identity_types (a match on this scheme is identity
# only between two works of these types: `isbn` between two books — the plan's "type-scoped ISBN-13"),
# tier (0 = in 0001's CHECK, 1 = a rung cannot fire without it, 2 = cheap, arrives unasked), why.
#
# distinct: TRUE for doi arxiv pmid pmcid openalex s2 mag bibcode and FALSE for isbn issn oai handle md5
# are the PLAN's (S4.5 item 1). The rest are decided here, from the linkage report, and each says why.
SCHEMES = {
    # tier 0 — the twelve 0001's closed CHECK held
    "doi": dict(label="DOI", normaliser="doi", distinct=True, strong=True, registry=True, tier=0,
                url="https://doi.org/{value}", regex=r"^10\.[0-9]{4,9}(\.[0-9]+)*/.+$",
                why="plan: distinct"),
    "arxiv": dict(label="arXiv id", normaliser="arxiv", distinct=True, strong=True, registry=True, tier=0,
                  url="https://arxiv.org/abs/{value}",
                  regex=r"^([0-9]{4}\.[0-9]{4,5}|[a-z-]+(\.[a-z]{2})?/[0-9]{7})$",
                  why="plan: distinct (the 10.48550 DOI is versionless; the id is stored versionless)"),
    "jstor": dict(label="JSTOR stable id", normaliser="trim", distinct=True, strong=True, tier=0,
                  url="https://www.jstor.org/stable/{value}", regex=r"^[0-9]+$",
                  why="decided: a stable id names one JSTOR item; carried over as a strong scheme from 0014"),
    "isbn": dict(label="ISBN-13", normaliser="isbn", distinct=False, strong=True, registry=True, tier=0,
                 identity_types=("book",), url="https://openlibrary.org/isbn/{value}",
                 regex=r"^97[89][0-9]{10}$",
                 why="plan: NOT distinct — a book's ISBN on its chapters is data (fatcat sets it on chapters)"),
    "pmid": dict(label="PubMed id", normaliser="pmid", distinct=True, strong=True, tier=0,
                 url="https://pubmed.ncbi.nlm.nih.gov/{value}/", regex=r"^[0-9]{1,9}$", why="plan: distinct"),
    "pmcid": dict(label="PubMed Central id", normaliser="pmcid", distinct=True, strong=True, tier=0,
                  url="https://www.ncbi.nlm.nih.gov/pmc/articles/{value}/", regex=r"^PMC[0-9]+$",
                  why="plan: distinct; stored WITH the PMC prefix (LINKAGE §3.6 trap 3)"),
    "openalex": dict(label="OpenAlex work id", normaliser="upper_last_segment", distinct=True, tier=0,
                     url="https://openalex.org/{value}", regex=r"^W[0-9]+$", why="plan: distinct"),
    "s2": dict(label="Semantic Scholar id", normaliser="lower", distinct=True, tier=0,
               url="https://www.semanticscholar.org/paper/{value}", regex=r"^([0-9a-f]{40}|[0-9]+)$",
               why="plan: distinct (the 40-hex paperId, or the CorpusId)"),
    "handle": dict(label="Handle", normaliser="handle", distinct=False, tier=0,
                   url="https://hdl.handle.net/{value}", regex=r"^[^/\s]+/\S+$",
                   why="plan: NOT distinct — mirroring repositories share handles; so NOT strong either (0014 "
                       "listed it strong): a value that names no one work cannot show that two records are "
                       "different works"),
    "url": dict(label="URL", normaliser="trim", distinct=True, tier=0, regex=r"^https?://\S+$",
                why="decided: a web source's URL names that source (E06's scheme); 0001's index held it "
                    "distinct and nothing measured contradicts that"),
    "tracker": dict(label="literature tracker row", normaliser="trim", distinct=True, tier=0,
                    regex=r"^[0-9]+$",
                    why="decided: one tracker row is one reference; 0001's index held it distinct"),
    "legacy_stem": dict(label="legacy file stem", normaliser="trim", distinct=True, tier=0,
                        why="decided: one legacy corpus file stem is one work; 0001's index held it distinct"),
    # tier 1 — a rung on litkb's own ladder cannot fire without it (LINKAGE §3.1 table)
    "md5": dict(label="MD5 (shadow-library work address)", normaliser="lower", distinct=False, tier=1,
                regex=r"^[0-9a-f]{32}$",
                why="plan: NOT distinct — one work legitimately has many files (LINKAGE §3.3)"),
    "pii": dict(label="Elsevier PII", normaliser="pii", distinct=True, tier=1,
                url="https://www.sciencedirect.com/science/article/pii/{value}", regex=r"^[SB][0-9X]{16}$",
                why="decided: distinct for practical purposes (LINKAGE §3.1; Elsevier's native key)"),
    "core": dict(label="CORE id", normaliser="trim", distinct=True, tier=1,
                 url="https://core.ac.uk/works/{value}", regex=r"^[0-9]+$",
                 why="decided: distinct (LINKAGE §3.1; the B17 byte rung is keyed on it)"),
    "bibcode": dict(label="ADS bibcode", normaliser="trim", distinct=True, tier=1,
                    url="https://ui.adsabs.harvard.edu/abs/{value}", regex=r"^[0-9]{4}[A-Za-z&.]\S{13}[A-Za-z.]$",
                    why="plan: distinct"),
    "ocaid": dict(label="Internet Archive identifier", normaliser="trim", distinct=True, tier=1,
                  url="https://archive.org/details/{value}", regex=r"^[A-Za-z0-9._-]+$",
                  why="decided: distinct (LINKAGE §3.1: an IA item is one scan)"),
    "oai": dict(label="OAI identifier", normaliser="trim", distinct=False, tier=1, regex=r"^oai:\S+$",
                why="plan: NOT distinct across mirroring repositories"),
    # tier 2 — cheap to carry, arrive unasked (LINKAGE §3.1). distinct FALSE wherever a value can
    # legitimately sit on more than one work of this corpus: every BOOK-level key (a chapter carries its
    # book's), every file digest (one work has many files), every shadow-library RECORD id (a record is a
    # file of an edition, shared by that edition's chapters).
    "issn": dict(label="ISSN", normaliser="issn", distinct=False, tier=2, regex=r"^[0-9]{4}-[0-9]{3}[0-9X]$",
                 url="https://portal.issn.org/resource/ISSN/{value}",
                 why="plan: NOT distinct — a container key shared by every article in the journal"),
    "oclc": dict(label="OCLC number", normaliser="oclc", distinct=False, tier=2, regex=r"^[0-9]+$",
                 url="https://www.worldcat.org/oclc/{value}",
                 why="decided: NOT distinct — a book-level record its chapters share"),
    "lccn": dict(label="LCCN", normaliser="lccn", distinct=False, tier=2, regex=r"^[a-z]{0,3}[0-9]{8,10}$",
                 url="https://lccn.loc.gov/{value}", why="decided: NOT distinct — book-level"),
    "olid": dict(label="Open Library id", normaliser="upper", distinct=False, tier=2, regex=r"^OL[0-9]+[MWA]$",
                 url="https://openlibrary.org/books/{value}", why="decided: NOT distinct — edition-level"),
    "htid": dict(label="HathiTrust volume id", normaliser="trim", distinct=False, tier=2,
                 url="https://hdl.handle.net/2027/{value}", why="decided: NOT distinct — volume-level"),
    "gbooks": dict(label="Google Books id", normaliser="trim", distinct=False, tier=2,
                   url="https://books.google.com/books?id={value}", why="decided: NOT distinct — volume-level"),
    "sha1": dict(label="SHA-1 file digest", normaliser="lower", distinct=False, tier=2, regex=r"^[0-9a-f]{40}$",
                 why="decided: NOT distinct — a file digest, and one work has many files"),
    "sha256": dict(label="SHA-256 file digest", normaliser="lower", distinct=False, tier=2,
                   regex=r"^[0-9a-f]{64}$", why="decided: NOT distinct — a file digest"),
    "zlib": dict(label="Z-Library id", normaliser="trim", distinct=False, tier=2, regex=r"^[0-9]+$",
                 why="decided: NOT distinct — a shadow-library FILE record"),
    "lgrsnf": dict(label="LibGen non-fiction id", normaliser="trim", distinct=False, tier=2, regex=r"^[0-9]+$",
                   why="decided: NOT distinct — a shadow-library FILE record"),
    "lgrsfic": dict(label="LibGen fiction id", normaliser="trim", distinct=False, tier=2, regex=r"^[0-9]+$",
                    why="decided: NOT distinct — a shadow-library FILE record"),
    "lgli": dict(label="LibGen.li id", normaliser="trim", distinct=False, tier=2, regex=r"^[0-9]+$",
                 why="decided: NOT distinct — a shadow-library FILE record"),
    "nexusstc": dict(label="Nexus/STC id", normaliser="trim", distinct=False, tier=2,
                     why="decided: NOT distinct — an STC record carries several files (LINKAGE §3.3)"),
    "wikidata": dict(label="Wikidata QID", normaliser="upper_last_segment", distinct=True, tier=2,
                     url="https://www.wikidata.org/wiki/{value}", regex=r"^Q[0-9]+$",
                     why="decided: distinct — one item per work (Wikidata's own distinct-values constraint on "
                         "its external-id properties is the shape WikidataIntegrator reads, LINKAGE §3.3)"),
    "mag": dict(label="Microsoft Academic id", normaliser="trim", distinct=True, tier=2, regex=r"^[0-9]+$",
                why="plan: distinct"),
    "dblp": dict(label="dblp key", normaliser="trim", distinct=True, tier=2,
                 url="https://dblp.org/rec/{value}", regex=r"^[a-z]+/[A-Za-z0-9_-]+/\S+$",
                 why="decided: distinct — one dblp record per publication"),
    "hal": dict(label="HAL id", normaliser="hal", distinct=True, tier=2, url="https://hal.science/{value}",
                regex=r"^[a-z]+-[0-9]{8}$", why="decided: distinct — one deposit (versions stripped, as arXiv)"),
}


def distinct_schemes():
    return tuple(s for s, d in SCHEMES.items() if d["distinct"])


# ── the normaliser (twin of litkb.norm_identifier, migration 0032) ─────────────────────────────────────

_ISBN_LABEL = re.compile(r"^\s*isbn(?:-1[03])?\s*:?\s*", re.I)


def _norm_doi(value):
    return normalize_doi(value)


def isbn_clean(value):
    """The characters of an ISBN: a leading `ISBN`/`ISBN-10:`/`ISBN-13:` label dropped, every character but
    0-9 and X removed, X upper-cased (isbnlib `canonical`'s job; the label is dropped FIRST so `13` in
    `ISBN-13:` never leaks into the digits)."""
    return re.sub(r"[^0-9X]", "", _ISBN_LABEL.sub("", value or "").upper())


def check_digit10(first9):
    """ISBN-10 check digit of nine digits (weights 10..2, mod 11, 10 -> 'X')."""
    s = sum((10 - i) * int(c) for i, c in enumerate(first9))
    r = (11 - s % 11) % 11
    return "X" if r == 10 else str(r)


def check_digit13(first12):
    """ISBN-13 / EAN-13 check digit of twelve digits: weights 1,3,1,3,... mod 10. THE STANDARD'S weights —
    not oc_idmanager's routine, whose boolean assignment degenerates them to 1,3,0,0,... (LINKAGE §3.5)."""
    s = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(first12))
    return str((10 - s % 10) % 10)


def isbn10_valid(c):
    return bool(re.fullmatch(r"[0-9]{9}[0-9X]", c or "")) and c not in _ISBN_SENTINELS \
        and check_digit10(c[:9]) == c[9]


def isbn13_valid(c):
    return bool(re.fullmatch(r"97[89][0-9]{10}", c or "")) and check_digit13(c[:12]) == c[12]


#: isbnlib screens these: they satisfy the ISBN-10 arithmetic and name no book.
_ISBN_SENTINELS = ("0000000000", "000000000X")


def to_isbn13(value):
    """A valid ISBN (10 or 13, any spelling) -> its ISBN-13; anything else -> None. REJECTS, never
    coerces: an ISBN-10 whose check digit is wrong is not re-computed into a valid ISBN-13, because that
    would launder a mistyped number into a real-looking one."""
    c = isbn_clean(value)
    if isbn13_valid(c):
        return c
    if isbn10_valid(c):
        body = "978" + c[:9]
        return body + check_digit13(body)
    return None


def to_isbn10(value):
    """A valid 978-prefixed ISBN-13 (or a valid ISBN-10) -> its ISBN-10; a 979 ISBN has none -> None."""
    c = isbn_clean(value)
    if isbn10_valid(c):
        return c
    if isbn13_valid(c) and c.startswith("978"):
        return c[3:12] + check_digit10(c[3:12])
    return None


def _norm_isbn(value):
    """Stored form: a valid ISBN-10 becomes its ISBN-13 (so the two spellings of one book are one row,
    LINKAGE §4.5 item 5); anything else is its cleaned characters, UNCHANGED otherwise — an invalid value
    is kept visibly invalid (the registry regex refuses it) rather than coerced."""
    c = isbn_clean(value)
    if isbn10_valid(c):
        body = "978" + c[:9]
        return body + check_digit13(body)
    return c


def _norm_pmcid(value):
    v = (value or "").strip(" ")
    m = re.fullmatch(r"(?i)(?:pmc)?\s*([0-9]+)", v)
    return f"PMC{m.group(1)}" if m else v


def _norm_issn(value):
    c = re.sub(r"[\s-]", "", (value or "").strip(" ").upper())
    return f"{c[:4]}-{c[4:]}" if re.fullmatch(r"[0-9]{7}[0-9X]", c) else c


def _norm_handle(value):
    return re.sub(r"(?i)^(?:hdl:\s*|(?:https?://)?hdl\.handle\.net/)", "", (value or "").strip(" "))


def _norm_oclc(value):
    return re.sub(r"^(?:\(ocolc\)|ocm|ocn|on)", "", (value or "").strip(" ").lower())


def _norm_arxiv(value):
    return re.sub(r"v[0-9]+$", "", re.sub(r"^arxiv:", "", (value or "").strip(" ").lower()))


NORMALISERS = {
    "doi": _norm_doi,
    "arxiv": _norm_arxiv,
    "isbn": _norm_isbn,
    "pmcid": _norm_pmcid,
    "pmid": lambda v: re.sub(r"(?i)^pmid:\s*", "", (v or "").strip(" ")),
    "issn": _norm_issn,
    "pii": lambda v: re.sub(r"[^0-9A-Z]", "", (v or "").upper()),
    "lower": lambda v: (v or "").strip(" ").lower(),
    "upper": lambda v: (v or "").strip(" ").upper(),
    "upper_last_segment": lambda v: (v or "").strip(" ").rstrip("/").rsplit("/", 1)[-1].upper(),
    "handle": _norm_handle,
    "oclc": _norm_oclc,
    "lccn": lambda v: re.sub(r"\s", "", (v or "").lower()),
    "hal": lambda v: re.sub(r"v[0-9]+$", "", (v or "").strip(" ").lower()),
    "trim": lambda v: (v or "").strip(" "),
}


def norm(scheme, value):
    """The stored `value_norm` of (scheme, value) — what `litkb.norm_identifier(scheme, value)` returns
    (qc/test_litkb_s45_identity.py drives both over one table). An unknown scheme is trimmed, as the
    database's ELSE branch does."""
    fn = NORMALISERS.get((SCHEMES.get(scheme) or {}).get("normaliser"), NORMALISERS["trim"])
    return fn(value)


def valid(scheme, value):
    """Does the NORMALISED value have its scheme's shape (the registry regex; ISBN also by check digit)?"""
    spec = SCHEMES.get(scheme)
    if spec is None:
        return False
    v = norm(scheme, value)
    if not v:
        return False
    if scheme == "isbn":
        return isbn13_valid(v)
    rx = spec.get("regex")
    return bool(re.fullmatch(rx, v)) if rx else True


# ── DOIs: the bracket-balanced clean, then the slice ──────────────────────────────────────────────────

_DOI_IN_TEXT = re.compile(r"10\.[0-9]{4,9}(?:\.[0-9]+)*/\S+")
_PAIRS = {")": "(", "]": "[", "}": "{"}


def clean_doi(text):
    """The first DOI in `text`, or "" (Zotero cleanDOI's rule, re-implemented — see the module docstring).

    A DOI runs to the first whitespace; trailing . , ; : are dropped; then a trailing ) ] or } is dropped
    WHILE the DOI holds more of that closer than of its opener — so `(doi:10.1234/x)` loses the ")" the
    reference list wrapped it in, and `10.1061/40794(179)45` keeps the pair it was minted with."""
    m = _DOI_IN_TEXT.search(text or "")
    if not m:
        return ""
    d = m.group(0)
    while True:
        d2 = d.rstrip(".,;:")
        if d2 and d2[-1] in _PAIRS and d2.count(d2[-1]) > d2.count(_PAIRS[d2[-1]]):
            d2 = d2[:-1]
        if d2 == d:
            break
        d = d2
    return _norm_doi(d)


def find_doi(text):
    """clean_doi first; when it finds nothing, the oc_idmanager slice (`normalize_doi` cuts at the first
    `10.`) as the second pass — which survives a wrapper clean_doi's registrant pattern does not."""
    return clean_doi(text) or _norm_doi(text)


# ── detection returns a SET (idutils), PMID last (Zotero) ─────────────────────────────────────────────

#: Shapes checked by `detect_schemes`, in the order they are reported. A bare number is simultaneously a
#: plausible OCLC, MAG, CORE and LibGen id (LINKAGE §3.5 item 4): every match is returned, and the caller
#: disambiguates from data (which service answered, which column it came from).
_DETECT = (
    ("doi", lambda s: bool(clean_doi(s))),
    ("arxiv", lambda s: bool(re.fullmatch(r"(?i)(arxiv:)?([0-9]{4}\.[0-9]{4,5}|[a-z-]+(\.[a-z]{2})?/[0-9]{7})(v[0-9]+)?", s))),
    ("isbn", lambda s: to_isbn13(s) is not None),
    ("issn", lambda s: bool(re.fullmatch(r"[0-9]{4}-?[0-9]{3}[0-9Xx]", s))),
    ("pmcid", lambda s: bool(re.fullmatch(r"(?i)pmc[0-9]+", s))),
    ("openalex", lambda s: bool(re.fullmatch(r"(?i)(https?://openalex\.org/)?w[0-9]+", s))),
    ("wikidata", lambda s: bool(re.fullmatch(r"(?i)(https?://www\.wikidata\.org/(wiki|entity)/)?q[0-9]+", s))),
    ("handle", lambda s: bool(re.fullmatch(r"(?i)(hdl:\s*|(https?://)?hdl\.handle\.net/)[^/\s]+/\S+", s))),
    ("oai", lambda s: s.lower().startswith("oai:")),
    ("md5", lambda s: bool(re.fullmatch(r"[0-9a-fA-F]{32}", s))),
    ("sha1", lambda s: bool(re.fullmatch(r"[0-9a-fA-F]{40}", s))),
    ("sha256", lambda s: bool(re.fullmatch(r"[0-9a-fA-F]{64}", s))),
    ("pii", lambda s: bool(re.fullmatch(r"[SB][0-9X]{16}", re.sub(r"[^0-9A-Z]", "", s.upper())))
     and s.strip()[:1].upper() in "SB"),
    ("bibcode", lambda s: bool(re.fullmatch(r"[0-9]{4}[A-Za-z&.]\S{13}[A-Za-z.]", s))),
    ("hal", lambda s: bool(re.fullmatch(r"(?i)[a-z]+-[0-9]{8}(v[0-9]+)?", s))),
    ("oclc", lambda s: s.isdigit()),
    ("mag", lambda s: s.isdigit()),
    ("core", lambda s: s.isdigit()),
)


def detect_schemes(value):
    """Every scheme `value` could be, as a tuple of unique schemes (a SET in content; ordered only so the
    answer is reproducible), with `pmid` LAST and only when the whole string is digits of PubMed length."""
    s = (value or "").strip()
    if not s:
        return ()
    out = tuple(name for name, test in _DETECT if test(s))
    if re.fullmatch(r"[0-9]{1,9}", s):
        out += ("pmid",)
    return out


# ── provider-side spellings (LINKAGE §3.6) ────────────────────────────────────────────────────────────

def doi_for_provider(doi, provider):
    """The DOI as `provider` must be ASKED: Wikidata stores P356 upper-case; every other provider litkb asks
    takes the lower-cased key (`normalize_doi`)."""
    d = _norm_doi(doi)
    return d.upper() if provider == "wikidata" else d


def pmcid_for_provider(pmcid, provider):
    """A PMCID as `provider` must be asked: Wikidata P932 and NCBI's id converter's numeric form take it
    WITHOUT the prefix; everything else (and litkb's own table) keeps `PMC`."""
    v = _norm_pmcid(pmcid)
    return v[3:] if provider in ("wikidata", "ncbi-numeric") and v.startswith("PMC") else v


# ── Wave 0: the zero-request derivations (LINKAGE §2.3) — each a ROW with deterministic provenance ─────

def row(scheme, value, *, asserted_by, derived_from=None, verified_by=None, evidence=None, candidate=False):
    """An identifier row as `litkb.record_identifiers` (migration 0032) takes it."""
    r = {"scheme": scheme, "value": value, "asserted_by": asserted_by, "verified_by": verified_by,
         "evidence": dict(evidence or {})}
    if derived_from:
        r["derived_from"] = {"scheme": derived_from[0], "value": derived_from[1]}
    if candidate:
        r["evidence"]["candidate"] = True
    return r


def arxiv_to_doi(arxiv_id):
    """An arXiv id -> its versionless `10.48550` DOI, as a CANDIDATE (verified_by NULL) until DataCite
    confirms it (LINKAGE §2.3; plan item 3). None when `arxiv_id` is not an arXiv id."""
    a = _norm_arxiv(arxiv_id)
    if not re.fullmatch(SCHEMES["arxiv"]["regex"], a):
        return None
    return row("doi", ARXIV_DOI_PREFIX + a, asserted_by=DETERMINISTIC, derived_from=("arxiv", a),
               evidence={"rule": "arXiv mints 10.48550/arXiv.<id>, versionless"}, candidate=True)


def doi_to_arxiv(doi):
    """The inverse: a `10.48550/arxiv.<id>` DOI -> the arXiv id it was minted from. None otherwise."""
    d = _norm_doi(doi)
    if not d.startswith(ARXIV_DOI_PREFIX):
        return None
    a = _norm_arxiv(d[len(ARXIV_DOI_PREFIX):])
    if not re.fullmatch(SCHEMES["arxiv"]["regex"], a):
        return None
    return row("arxiv", a, asserted_by=DETERMINISTIC, derived_from=("doi", d),
               evidence={"rule": "the suffix of a 10.48550/arXiv.<id> DOI is the id"})


def isbn10_to_13(isbn10):
    """ISBN-10 -> ISBN-13 (re-derived check digit), or None for an invalid ISBN-10 (rejected)."""
    c = isbn_clean(isbn10)
    if not isbn10_valid(c):
        return None
    return row("isbn", to_isbn13(c), asserted_by=DETERMINISTIC, derived_from=("isbn", c),
               verified_by=DETERMINISTIC, evidence={"rule": "978 + first nine + ISBN-13 check digit"})


def isbn_a_doi(hyphenated_isbn13):
    """ISBN-13 -> its ISBN-A DOI `10.<prefix>.<group><registrant>/<publication><check>`, from a HYPHENATED
    ISBN-13 only (the hyphens carry the range split; see the module docstring). None for a bare or invalid
    ISBN, never a guessed split. A CANDIDATE: an ISBN-A DOI exists only if the agency registered it."""
    parts = re.split(r"[-\s]", (hyphenated_isbn13 or "").strip())
    if len(parts) != 5 or not all(p.isdigit() for p in parts):
        return None
    prefix, group, registrant, publication, check = parts
    if prefix not in ("978", "979") or not isbn13_valid("".join(parts)):
        return None
    return row("doi", f"10.{prefix}.{group}{registrant}/{publication}{check}", asserted_by=DETERMINISTIC,
               derived_from=("isbn", "".join(parts)),
               evidence={"rule": "ISBN-A: 10.<prefix>.<group+registrant>/<publication+check>"}, candidate=True)


def pmcid_forms(pmcid):
    """(stored, asked) for a PMCID: `PMC7391` in litkb's table, `7391` to Wikidata / the numeric converter."""
    return _norm_pmcid(pmcid), pmcid_for_provider(pmcid, "ncbi-numeric")


def is_shortdoi(value):
    return bool(re.fullmatch(r"(?i)(?:https?://doi\.org/)?10/[a-z0-9]+", (value or "").strip()))


def shortdoi_alias_url(shortdoi):
    """The ONE request that expands a shortDOI (doi.org's handle API, HS_ALIAS) — a Stage A CALL, not a
    zero-request derivation (LINKAGE §3.6)."""
    sd = re.sub(r"(?i)^https?://doi\.org/", "", (shortdoi or "").strip())
    return f"https://doi.org/api/handles/{sd}?type=HS_ALIAS"


def parse_hs_alias(shortdoi, answer):
    """doi.org's handle-API answer for a shortDOI -> a row carrying the full DOI, or None. `responseCode`
    1 = found, 100 = no such handle, 200 = no alias value (LINKAGE §3.6)."""
    if not isinstance(answer, dict) or answer.get("responseCode") != 1:
        return None
    for v in answer.get("values") or []:
        if (v or {}).get("type") == "HS_ALIAS":
            full = _norm_doi(str(((v.get("data") or {}).get("value")) or ""))
            if full:
                return row("doi", full, asserted_by="handle", verified_by="handle",
                           derived_from=("doi", (shortdoi or "").strip().lower()),
                           evidence={"rule": "shortDOI expanded through the handle alias; only the full DOI "
                                             "is stored (one work never holds two rows)"})
    return None

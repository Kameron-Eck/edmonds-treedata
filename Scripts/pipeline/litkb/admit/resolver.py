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
    d = (doi or "").strip().lower()
    i = d.find("10.")
    return d[i:].rstrip("/") if i >= 0 else ""


def strip_tags(s):
    """Crossref titles carry JATS/MathML markup (10.1016/j.laa.2010.09.001 does)."""
    return _TAG_RE.sub(" ", str(s or ""))


def _norm_text(s):
    s = (s or "").lower()
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


def resolve_doi(title, surname, year, client=None, pacer=None):
    """-> (doi, source, evidence) or (None, None, reason).
    evidence: `via=<source>; ratio=0.xx; year=<y>`;  reason: `best=<source>:<ratio>:<candidate doi>`.
    An accepted arXiv-stage hit still returns None: its 10.48550 DOI is for the record only and
    appears in the reason, but the archive is never asked for it."""
    if client is None:
        from litkb.netutil import Client
        client = Client()
    best = None                                   # (ratio, source, doi)
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
            if source == "arxiv" or not normalize_doi(c.get("doi")):
                return None, None, f"best={source}:{ratio:.2f}:{c.get('doi') or '-'}"
            d = c["doi"].strip()           # the arXiv DOI form keeps its registered case
            d = d if d.startswith(ARXIV_DOI_PREFIX) else normalize_doi(d)
            return d, source, f"via={source}; ratio={ratio:.2f}; {note}"
    if best is None:
        return None, None, "best=none"
    return None, None, f"best={best[1]}:{best[0]:.2f}:{best[2]}"


def resolution_log_line(status, stem, title, doi, evidence):
    return redact(" | ".join([status, stem, (title or "")[:60], doi or "-", evidence or ""]))

"""OpenCitations ref-matcher, head to head with our own reference resolver.

The question this instrument answers is the one CLAUDE.md 3.4c asks of any adopted design:
did someone else measure better, ON OUR GOLD, with the numbers read off a file rather than
off the proposer's own report. It runs the upstream tool unmodified where that is possible,
records where it is not, and scores every arm against the FROZEN Splink gold
(`Reports/litkb_splink_gold_2026-09-15.json`, sha256 d6dbbac3…) which this instrument never
writes to.

THREE THINGS THE BRIEF ASSUMED THAT THE CODE DOES NOT SUPPORT, named here because the report
is downstream of this file:

  1. ref-matcher does NOT match against Crossref. It matches against **OpenCitations Meta**
     over SPARQL (`script/requirements.txt`: "Async HTTP client for OpenCitations queries").
     Crossref JSON is an INPUT format, not the registry it searches.
  2. ref-matcher has no search-based arm at all. Every one of its six query types is a
     structured field lookup; its "raw string" path is GROBID -> fields -> SPARQL. The
     Crossref search-based claim therefore cannot be tested with this tool, so the raw-string
     arm here calls Crossref `works?query.bibliographic=` directly and is labelled
     CROSSREF-SBM, never "ref-matcher".
  3. The tool's default endpoint `sparql-stg.opencitations.net` does not resolve (NXDOMAIN).
     Production `sparql.opencitations.net` does, and requires `^^xsd:string` typed literals
     that the tool does not emit -- see TYPED_LITERAL_PREDICATES.

Arms (`--arm`):
  parsed          ref-matcher on the GROBID-parsed fields already in references.jsonl
  parsed-unpatched  the same, tool exactly as shipped -- the "as distributed" measurement
  raw-crossref    raw strings -> Crossref query.bibliographic (CROSSREF-SBM, not ref-matcher)
  mutants         ref-matcher on the 90 gold mutants (70 must-not-link + 20 near-positive)
  mutants-noauthor  the kill: the same 90 with the author term's 7 points zeroed

Every registry answer is cached to `litkb_derived/refmatch/` keyed on the exact query, so a
referee re-scores at zero wire. Request counts, 429s and wall-clock are recorded per arm.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Locations. Data resolves under the lake-side derived tree; code under __file__.
# ---------------------------------------------------------------------------
DERIVED = Path(os.environ.get("LITKB_DERIVED", r"D:\edmonds-pipeline\litkb_derived"))
P6 = DERIVED / "p6"
OUT = DERIVED / "refmatch"
REFERENCES_JSONL = P6 / "references.jsonl"

OC_ENDPOINT = "https://sparql.opencitations.net/meta"
OC_ENDPOINT_SHIPPED = "https://sparql-stg.opencitations.net/meta"
CROSSREF_SEARCH = "https://api.crossref.org/works"
USER_AGENT = "litkb-refmatcher-eval/1.0 (mailto:kameron4321@gmail.com)"

# The upstream commit this was measured against. Recorded in every result file.
UPSTREAM_SHA = "dfb0e7c06f2cc1495c1045ee69d22dc1fddbc96b"

# ---------------------------------------------------------------------------
# The patch. Three predicates are matched against a plain literal in a triple
# pattern; the production Virtuoso stores them as xsd:string and will not join a
# plain literal to a typed one. BIND("x" AS ?v) is deliberately NOT touched -- there
# the literal is the value being projected, not a join key.
# ---------------------------------------------------------------------------
TYPED_LITERAL_PREDICATES = (
    "literal:hasLiteralValue",
    "foaf:familyName",
    "fabio:hasSequenceIdentifier",
)
_XSD_PREFIX = "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>"


def type_literals(query: str) -> str:
    """Add ``^^xsd:string`` to the join-key literals of the three affected predicates.

    Idempotent: a literal that already carries a datatype is left alone.
    """
    if not query:
        return query
    out = query
    for pred in TYPED_LITERAL_PREDICATES:
        # predicate, whitespace, a double-quoted literal NOT already followed by ^^
        pattern = re.compile(
            r"(" + re.escape(pred) + r"\s+)"
            r'"((?:[^"\\]|\\.)*)"'
            r"(?!\s*\^\^)"
        )
        out = pattern.sub(lambda m: f'{m.group(1)}"{m.group(2)}"^^xsd:string', out)
    if "^^xsd:string" in out and _XSD_PREFIX not in out and "PREFIX xsd:" not in out:
        out = _XSD_PREFIX + "\n" + out
    return out


# ---------------------------------------------------------------------------
# Disk cache. One JSONL per registry; key is sha256 of the exact query text.
# ---------------------------------------------------------------------------
class QueryCache:
    def __init__(self, path: Path):
        self.path = path
        self.mem: dict[str, object] = {}
        self.hits = 0
        self.misses = 0
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self.mem[rec["k"]] = rec["v"]

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str):
        k = self.key(text)
        if k in self.mem:
            self.hits += 1
            return self.mem[k]
        self.misses += 1
        return None

    def put(self, text: str, value) -> None:
        k = self.key(text)
        self.mem[k] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"k": k, "v": value}, ensure_ascii=False) + "\n")


@dataclass
class WireStats:
    requests: int = 0
    errors: int = 0
    rate_limited: int = 0
    seconds: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    by_status: dict = field(default_factory=dict)

    def asdict(self) -> dict:
        return {
            "requests": self.requests,
            "errors": self.errors,
            "rate_limited_429": self.rate_limited,
            "wire_seconds": round(self.seconds, 1),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "by_status": self.by_status,
        }


# ---------------------------------------------------------------------------
# Loading the upstream tool by path. It is a script repo -- no package, no PyPI
# release -- so it is imported by file location, which is why --tool-dir exists.
# ---------------------------------------------------------------------------
def load_tool(tool_dir: Path):
    script = Path(tool_dir) / "script" / "ReferenceMatchingTool.py"
    if not script.exists():
        raise SystemExit(f"ref-matcher not found at {script}")
    # The tool does `from data.grobid.grobid_client...` at module level, so its own repo
    # root has to be importable. APPEND, never insert: this is a third-party script root
    # (no package, no PyPI release -- see the module docstring), and appending gives it the
    # LOWEST precedence so it can never shadow `lake`, `champion` or anything the editable
    # install provides. That is also why it is not a `sys.path.insert` ledger entry: the
    # ledger exists to stop path hacks reaching OUR modules, which the install already covers.
    root = str(Path(tool_dir).resolve())
    if root not in sys.path:
        sys.path.append(root)
    spec = importlib.util.spec_from_file_location("ReferenceMatchingTool", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ReferenceMatchingTool"] = mod
    spec.loader.exec_module(mod)
    return mod


def binding_value(record, key: str) -> str:
    """Read one field out of a SPARQL binding, which the tool passes around unflattened.

    A match returned by ``process_reference`` is the winning binding with `score` and
    `query_type` added, so a field is ``{'value': …}`` -- never a bare string. Tolerates
    both shapes so a future upstream change does not silently read as an empty DOI.
    """
    if not record:
        return ""
    v = record.get(key)
    if isinstance(v, dict):
        return str(v.get("value", "") or "")
    return str(v or "")


def normalize_doi(doi: str) -> str:
    """The same shape our resolver uses: strip the registrar prefixes, casefold."""
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                "http://dx.doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip()


# ---------------------------------------------------------------------------
# Adapter: our reference row -> the tool's Reference dataclass.
# ---------------------------------------------------------------------------
def ref_from_row(mod, row: dict, use_doi: bool = True):
    """Map one references.jsonl row onto ref-matcher's Reference.

    `journal` carries the container title; the tool distinguishes article/volume/journal
    titles and falls back in that order (`Reference.get_main_title`). A reference whose
    GROBID parse produced no title has an empty article_title -- that is the real input,
    and is left empty rather than back-filled from `raw`, because filling it would measure
    our repair and not the tool.
    """
    pages = (row.get("pages") or "").strip()
    first_page = pages.split("-")[0].strip() if pages else ""
    return mod.Reference(
        year=str(row.get("year") or "").strip(),
        volume=str(row.get("volume") or "").strip(),
        first_page=first_page,
        first_author_lastname=str(row.get("first_author") or "").strip(),
        article_title=str(row.get("title") or "").strip(),
        volume_title="",
        journal_title=str(row.get("journal") or "").strip(),
        doi=(str(row.get("doi") or "").strip() if use_doi else ""),
        unstructured=str(row.get("raw") or "").strip(),
    )


def mutant_rows(gold: dict, base_by_id: dict) -> list[dict]:
    """Build the 90 mutant reference rows from the gold's own mutation fields.

    Nothing is invented here: mutant_title / mutant_year / mutant_doi come from the gold,
    the remaining fields from the base reference it was mutated from. `expect_not` is the
    DOI the mutant must NOT resolve to.
    """
    out = []
    for e in gold["must_not_link"]:
        if "#mut" not in e["ref_id"]:
            continue
        base = base_by_id.get(e["base_ref_id"])
        if base is None:
            continue
        row = dict(base)
        row["title"] = e.get("mutant_title") or base.get("title") or ""
        row["year"] = e.get("mutant_year") or base.get("year") or ""
        row["doi"] = e.get("mutant_doi") or ""
        row["_ref_id"] = e["ref_id"]
        row["_family"] = "must_not_link"
        row["_mutation"] = e.get("mutation") or e.get("kind") or ""
        row["_expect_not"] = normalize_doi(e.get("bad_doi") or "")
        row["_expect"] = ""
        out.append(row)
    for e in gold["near_positive_mutations"]:
        base = base_by_id.get(e["base_ref_id"])
        if base is None:
            continue
        row = dict(base)
        row["title"] = e.get("mutant_title") or base.get("title") or ""
        row["year"] = e.get("mutant_year") or base.get("year") or ""
        row["doi"] = ""
        row["_ref_id"] = e["ref_id"]
        row["_family"] = "near_positive"
        row["_mutation"] = e.get("mutation") or ""
        row["_expect_not"] = ""
        row["_expect"] = normalize_doi(e.get("gold_doi") or "")
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Arm 1/2/4/5: ref-matcher against OpenCitations Meta.
# ---------------------------------------------------------------------------
async def run_refmatcher(mod, rows, *, endpoint, patched, cache, stats, threshold,
                         use_doi, pace, progress_path, label, author_weight=None):
    """Drive the tool's own matching loop, one reference at a time.

    The tool's `process_reference` opens its own session per reference, runs its query
    ladder in its own order, and applies its own 48-point score and threshold. Nothing
    about the scoring is reimplemented here -- only the transport is intercepted, so the
    verdict is the tool's.
    """
    if author_weight is not None:
        mod.SCORING_CONFIG["author_exact_match"] = author_weight

    processor = mod.ReferenceProcessor(use_grobid=False, endpoint=endpoint)

    # Intercept transport: cache + count, and apply the typed-literal patch when asked.
    last_call = [0.0]

    async def query_opencitations(self, sparql_query, query_type="unknown"):
        q = type_literals(sparql_query) if patched else sparql_query
        cached = cache.get(q)
        if cached is not None:
            stats.cache_hits += 1
            return cached
        stats.cache_misses += 1
        wait = pace - (time.time() - last_call[0])
        if wait > 0:
            await asyncio.sleep(wait)
        last_call[0] = time.time()
        url = endpoint + "?" + urllib.parse.urlencode({"query": q})
        req = urllib.request.Request(url, headers={
            "Accept": "application/sparql-results+json", "User-Agent": USER_AGENT})
        t0 = time.time()
        try:
            body = await asyncio.get_event_loop().run_in_executor(
                None, lambda: urllib.request.urlopen(req, timeout=120).read())
            # RETURN THE RAW SPARQL BINDINGS, NOT FLATTENED VALUES. The tool's scorer
            # reads `result['doi']['value']` (ReferenceMatchingTool.py:1208 and around),
            # so flattening `{'doi': {'value': x}}` to `{'doi': x}` makes every field read
            # fail and every candidate score 0 -- which reads exactly like "the tool matched
            # nothing" and is the shape of a false headline.
            out = json.loads(body)["results"]["bindings"]
            stats.requests += 1
            stats.by_status["200"] = stats.by_status.get("200", 0) + 1
        except urllib.error.HTTPError as exc:            # noqa: PERF203 - per-call accounting
            stats.requests += 1
            code = str(exc.code)
            stats.by_status[code] = stats.by_status.get(code, 0) + 1
            if exc.code == 429:
                stats.rate_limited += 1
            stats.errors += 1
            failed = True
            out = []
        except Exception:
            stats.requests += 1
            stats.errors += 1
            stats.by_status["exc"] = stats.by_status.get("exc", 0) + 1
            failed = True
            out = []
        else:
            failed = False
        finally:
            stats.seconds += time.time() - t0
        # NEVER CACHE A FAILURE AS AN EMPTY RESULT. A 500 or a timeout stored as `[]` is
        # indistinguishable on re-read from "the registry has nothing", so it becomes a
        # PERMANENT miss that a referee's zero-wire re-score silently inherits. Only real
        # answers are persisted; a failed query is simply re-asked next run.
        if not failed:
            cache.put(q, out)
        return out

    mod.OpenCitationsMatcherThreadSafe.query_opencitations = query_opencitations

    results = []
    t_start = time.time()
    for i, row in enumerate(rows, 1):
        rid = row.get("_ref_id") or f"{row['citing_work_key']}::{row['ref_key']}"
        ref = ref_from_row(mod, row, use_doi=use_doi)
        try:
            match = await processor.process_reference(ref, threshold=threshold, use_doi=use_doi)
        except Exception as exc:
            match = None
            results.append({"ref_id": rid, "error": f"{type(exc).__name__}: {exc}"})
            continue
        # THE TOOL RETURNS A TRUTHY DICT FOR A NON-MATCH. When nothing clears the
        # (possibly adjusted) threshold it returns {'below_threshold': True, 'score': …}
        # rather than None -- ReferenceMatchingTool.py:1794. Treating `bool(match)` as a
        # match counts every reference as resolved and inverts the whole result, so the
        # flag is read explicitly here and the near-miss score is kept for the report.
        below = bool(match) and bool(match.get("below_threshold"))
        matched = bool(match) and not below
        rec = {
            "ref_id": rid,
            "matched": matched,
            "below_threshold": below,
            "doi": normalize_doi(binding_value(match, "doi")) if matched else "",
            "br": binding_value(match, "br") if matched else "",
            "score": (match or {}).get("score"),
            "query_type": ((match or {}).get("query_type") or "") if matched else "",
            "title": binding_value(match, "title")[:200] if matched else "",
        }
        for k in ("_family", "_mutation", "_expect", "_expect_not"):
            if k in row:
                rec[k] = row[k]
        results.append(rec)
        if i % 10 == 0 or i == len(rows):
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(json.dumps({
                "arm": label, "done": i, "total": len(rows),
                "elapsed_s": round(time.time() - t_start, 1),
                "matched": sum(1 for r in results if r.get("matched")),
                **stats.asdict()}, indent=1), encoding="utf-8")
    return results


# ---------------------------------------------------------------------------
# Arm 3: Crossref search-based matching on the raw strings. NOT ref-matcher.
# ---------------------------------------------------------------------------
def run_crossref_sbm(rows, *, cache, stats, pace, progress_path, rows_returned=5):
    """`works?query.bibliographic=<raw>`, top hit by Crossref's own relevance order.

    This is the method Crossref reported on, applied to our references. No score
    threshold is imposed here: the top hit is recorded with its Crossref relevance
    score so the scoring pass can apply any cut it likes.
    """
    results = []
    t_start = time.time()
    last = 0.0
    for i, row in enumerate(rows, 1):
        rid = row.get("_ref_id") or f"{row['citing_work_key']}::{row['ref_key']}"
        raw = (row.get("raw") or "").strip()
        if not raw:
            results.append({"ref_id": rid, "matched": False, "doi": "", "reason": "no_raw"})
            continue
        params = {"query.bibliographic": raw, "rows": str(rows_returned),
                  "select": "DOI,title,author,issued,score,type,container-title"}
        url = CROSSREF_SEARCH + "?" + urllib.parse.urlencode(params)
        cached = cache.get(url)
        if cached is not None:
            stats.cache_hits += 1
            items = cached
        else:
            stats.cache_misses += 1
            wait = pace - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            t0 = time.time()
            try:
                body = urllib.request.urlopen(req, timeout=60).read()
                items = json.loads(body)["message"]["items"]
                stats.requests += 1
                stats.by_status["200"] = stats.by_status.get("200", 0) + 1
                cache.put(url, items)
            except urllib.error.HTTPError as exc:
                # Not cached -- see the note in run_refmatcher: a failure stored as an empty
                # result is a permanent miss for every later zero-wire re-score.
                stats.requests += 1
                code = str(exc.code)
                stats.by_status[code] = stats.by_status.get(code, 0) + 1
                if exc.code == 429:
                    stats.rate_limited += 1
                stats.errors += 1
                items = []
            except Exception:
                stats.requests += 1
                stats.errors += 1
                stats.by_status["exc"] = stats.by_status.get("exc", 0) + 1
                items = []
            finally:
                stats.seconds += time.time() - t0
        top = items[0] if items else None
        rec = {
            "ref_id": rid,
            "matched": bool(top),
            "doi": normalize_doi((top or {}).get("DOI") or ""),
            "score": (top or {}).get("score"),
            "type": (top or {}).get("type") or "",
            "title": (((top or {}).get("title") or [""])[0])[:200],
            "candidates": [normalize_doi(it.get("DOI") or "") for it in items[:rows_returned]],
        }
        for k in ("_family", "_mutation", "_expect", "_expect_not"):
            if k in row:
                rec[k] = row[k]
        results.append(rec)
        if i % 10 == 0 or i == len(rows):
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(json.dumps({
                "arm": "raw-crossref", "done": i, "total": len(rows),
                "elapsed_s": round(time.time() - t_start, 1),
                **stats.asdict()}, indent=1), encoding="utf-8")
    return results


# ---------------------------------------------------------------------------
def probe_presence(dois, *, cache, stats, pace) -> list[dict]:
    """Is a given DOI in OpenCitations Meta at all?

    A gate that never sees the bad record is not a gate. Before reading ref-matcher's
    silence on a book review as discrimination, this establishes whether the wrong answer
    was even available to it -- and, for the five lost_genuine DOIs, whether the right
    answer was reachable in principle.
    """
    q = ('PREFIX datacite: <http://purl.org/spar/datacite/>\n'
         'PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>\n'
         'PREFIX dcterms: <http://purl.org/dc/terms/>\n'
         'PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n'
         'SELECT ?br ?title WHERE {{ ?id datacite:usesIdentifierScheme datacite:doi ; '
         'literal:hasLiteralValue "{doi}"^^xsd:string . ?br datacite:hasIdentifier ?id . '
         'OPTIONAL{{?br dcterms:title ?title}} }} LIMIT 3')
    out = []
    last = 0.0
    for doi in dois:
        text = q.format(doi=doi)
        cached = cache.get(text)
        if cached is not None:
            stats.cache_hits += 1
            b = cached
        else:
            stats.cache_misses += 1
            wait = pace - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.time()
            url = OC_ENDPOINT + "?" + urllib.parse.urlencode({"query": text})
            req = urllib.request.Request(url, headers={
                "Accept": "application/sparql-results+json", "User-Agent": USER_AGENT})
            t0 = time.time()
            try:
                b = json.loads(urllib.request.urlopen(req, timeout=120).read())["results"]["bindings"]
                stats.requests += 1
                stats.by_status["200"] = stats.by_status.get("200", 0) + 1
                cache.put(text, b)
            except Exception:
                stats.requests += 1
                stats.errors += 1
                b = []
            finally:
                stats.seconds += time.time() - t0
        out.append({"doi": doi, "in_oc_meta": bool(b),
                    "title": binding_value(b[0], "title") if b else ""})
    return out


def load_rows() -> list[dict]:
    with REFERENCES_JSONL.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_gold(path: Path) -> dict:
    # CRLF-safe, matching litkb_splink_eval.py: *.json is a text attribute and
    # core.autocrlf is true, so the raw bytes differ by platform while the gold does not.
    data = path.read_bytes()
    gold = json.loads(data.decode("utf-8-sig"))
    gold["_sha256"] = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    return gold


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True,
                    choices=["parsed", "parsed-unpatched", "raw-crossref",
                             "mutants", "mutants-noauthor", "presence"])
    ap.add_argument("--tool-dir", required=True, help="clone of opencitations/ref-matcher")
    ap.add_argument("--gold", required=True)
    ap.add_argument("--limit", type=int, default=0, help="first N rows (canary)")
    ap.add_argument("--only-unparsed", action="store_true",
                    help="restrict to references GROBID gave no title or no first author")
    ap.add_argument("--threshold", type=int, default=26)
    ap.add_argument("--pace", type=float, default=1.0, help="seconds between wire calls")
    ap.add_argument("--no-doi", action="store_true",
                    help="withhold the reference's own DOI from the tool")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    gold = load_gold(Path(args.gold))
    rows = load_rows()
    by_id = {f"{r['citing_work_key']}::{r['ref_key']}": r for r in rows}

    if args.arm in ("mutants", "mutants-noauthor"):
        work = mutant_rows(gold, by_id)
    else:
        work = rows
        if args.only_unparsed:
            work = [r for r in work
                    if not (r.get("title") or "").strip()
                    or not (r.get("first_author") or "").strip()]
    if args.limit:
        work = work[:args.limit]

    stats = WireStats()
    out_path = Path(args.out) if args.out else OUT / f"results_{args.arm}.jsonl"
    progress = OUT / f"progress_{args.arm}.json"
    t0 = time.time()

    if args.arm == "presence":
        cache = QueryCache(OUT / "cache_oc_presence.jsonl")
        dois = []
        for e in gold["must_not_link"]:
            if "#mut" not in e["ref_id"]:
                dois.append(("must_not_link_bad", e["ref_id"], normalize_doi(e["bad_doi"])))
        for e in gold["lost_genuine"]:
            dois.append(("lost_genuine", e["ref_id"], normalize_doi(e["gold_doi"])))
        probed = probe_presence([d for _, _, d in dois], cache=cache, stats=stats,
                                pace=args.pace)
        results = [{"ref_id": rid, "role": role, **p}
                   for (role, rid, _), p in zip(dois, probed)]
        meta = {"registry": "opencitations-meta", "endpoint": OC_ENDPOINT,
                "note": "is the gold's DOI present in OC Meta at all"}
    elif args.arm == "raw-crossref":
        cache = QueryCache(OUT / "cache_crossref_search.jsonl")
        results = run_crossref_sbm(work, cache=cache, stats=stats, pace=args.pace,
                                   progress_path=progress)
        meta = {"registry": "crossref", "method": "works?query.bibliographic",
                "note": "CROSSREF-SBM, not ref-matcher: the tool has no search-based mode"}
    else:
        mod = load_tool(Path(args.tool_dir))
        patched = args.arm != "parsed-unpatched"
        endpoint = OC_ENDPOINT_SHIPPED if args.arm == "parsed-unpatched-default" else OC_ENDPOINT
        cache = QueryCache(OUT / ("cache_oc_patched.jsonl" if patched
                                  else "cache_oc_unpatched.jsonl"))
        author_weight = 0 if args.arm == "mutants-noauthor" else None
        results = asyncio.run(run_refmatcher(
            mod, work, endpoint=endpoint, patched=patched, cache=cache, stats=stats,
            threshold=args.threshold, use_doi=not args.no_doi, pace=args.pace,
            progress_path=progress, label=args.arm, author_weight=author_weight))
        meta = {"registry": "opencitations-meta", "endpoint": endpoint,
                "typed_literal_patch": patched, "threshold": args.threshold,
                "author_weight": author_weight,
                "upstream_sha": UPSTREAM_SHA}

    meta.update({"arm": args.arm, "rows": len(work), "gold_sha256": gold["_sha256"],
                 "wall_clock_s": round(time.time() - t0, 1), **stats.asdict()})
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"_meta": meta}, ensure_ascii=False) + "\n")
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(meta, indent=1))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

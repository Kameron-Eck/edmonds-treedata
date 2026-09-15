"""The Semantic Scholar leg: batched, field-narrowed, backed off, cached and COUNTED.

WHY THIS EXISTS. P6 measured the unauthenticated pool from this laptop answering **429 in 0.1 s** on
the first request, at any pace (`Reports/LITKB_REFERENCES_2026-09-15.md` §2), so `StageBreaker`
tripped the stage and the 55.5 % resolution rate is a **Crossref-only floor**. Kam decided against an
API key, quoting the vendor's own statement that the pool is public:

    "rate-limited to 1000 requests per second shared among all unauthenticated users"
    — https://www.semanticscholar.org/product/api (fetched 2026-09-15, verbatim)

A shared pool that is already exhausted is not a budget one can pace into; the only lever left is to
ASK LESS. This module is that lever: one request per distinct question, the narrowest field list that
answers it, ≤500 identifiers per call, every settled answer on disk, and a per-run count so the next
report can say what the run actually spent instead of estimating it.

WHAT THE REQUEST COUNT CAN AND CANNOT BUY, stated before any number is quoted. The batch endpoint
keys on IDENTIFIERS (DOI, arXiv, CorpusId); it cannot take titles. A reference that reaches the S2
leg at all is, by construction of `references.resolve_reference`, one that carries NO DOI — the DOI
decides when there is one — so the population this module can batch is small and the population it
must ask about one title at a time is the rest. The floor for N title-only references is N match
requests, and no amount of batching moves it. Measured on the P6 corpus: see
`Reports/LITKB_S2_BATCHING_2026-09-15.md`.

PROVENANCE OF THE PATTERNS (CLAUDE.md 3.4b — say what is harvested, what is documented, what is ours).

  * HARVESTED from https://github.com/spideryzarc/smart-semantic-scholar-mcp (read only, never run or
    installed; commit of 2026-09-15): the `POST /paper/batch` shape with the ids in the JSON body and
    `fields` in the query string; the 500-id chunking (`for i in range(0, len(missing_ids), 500)`);
    the `DOI:` / `ARXIV:` identifier prefixes; the index-aligned response walked as
    `for idx, paper in enumerate(data)` with `if paper and "paperId" in paper` for the misses; the
    "fetch only what is not already cached" pre-pass; and an exponential 429 back-off
    (`await asyncio.sleep(5 * (2 ** attempt))`, 3 retries). Its README declares the MIT licence
    (badge and a link to a LICENSE file) but **the repository ships no LICENSE file** — the clone has
    none. So nothing is copied: every line here is written against these ideas, which are the
    endpoint's documented shape rather than authorship, and the repo is cited for the patterns.
  * FROM THE DOCS: the shared unauthenticated pool, quoted above; and
    "some endpoints have a corresponding batch or bulk endpoint"
    — https://www.semanticscholar.org/product/api/tutorial (fetched 2026-09-15, verbatim).
    The endpoint reference at https://api.semanticscholar.org/api-docs/graph is a JavaScript
    application that serves no prose to a fetcher, so the 500-id cap and the `DOI:`/`ARXIV:` prefixes
    are HARVESTED, not quoted from the vendor: this module therefore treats a length mismatch and an
    unexpected chunk size as errors to be reported rather than assumptions to be trusted.
  * OURS: jitter and the `Retry-After` honour (neither appears in the harvested repo); the versioned
    disk-cache key; the length-mismatch kill; the request accounting; and the conversion into the
    shared candidate shape so `admit.resolver.judge_candidate` — the ratio filter, the first-author
    discriminator and the decisions.yaml §15.15 year rule — decides exactly as it did before.

NOTHING HERE DECIDES A RESOLUTION. This module fetches candidates and converts them; the acceptance
rules are unchanged and live where they already lived.
"""
import hashlib
import json
import random
import time

from litkb.admit.resolver import ARXIV_DOI_PREFIX, normalize_doi
from litkb.netutil import redact

S2_BASE = "https://api.semanticscholar.org/graph/v1"
BATCH_URL = S2_BASE + "/paper/batch"
MATCH_URL = S2_BASE + "/paper/search/match"

#: Harvested, not quoted (see the module docstring): the batch endpoint is documented in the repo's
#: own comment as "limited to 500 IDs at a time". Chunks are never assumed to come back whole —
#: :func:`S2Client.batch` checks the length of every response against the chunk it sent.
BATCH_MAX = 500

#: The narrowest field list that answers stage 6's question. Every extra field is bytes the shared
#: pool pays for: `abstract`, `tldr` and `citationStyles` (which the harvested repo requests) are not
#: asked for, because nothing in resolution reads them.
FIELDS = "externalIds,title,year,authors"

#: Bumped whenever the parsed shape, the field list or the request form changes. It is part of the
#: cache key, so an entry written under an older schema can never be served to a newer parser —
#: the alternative is a stale body silently missing a field the caller now reads.
CACHE_SCHEMA = "s2-1"

#: Exponential, with the vendor's own ladder as the starting shape (harvested: 5·2^n, three retries)
#: flattened at the top so a measurement terminates. Jitter is ours: a fixed ladder puts every client
#: that started together back on the wire together.
BACKOFFS = (5.0, 10.0, 20.0, 40.0)
JITTER = 0.25
#: A `Retry-After` longer than this is not waited out; the ladder gives up and the caller's breaker
#: sees a rate-limit answer. Waiting ten minutes inside one reference is not a resolution strategy.
RETRY_AFTER_CAP = 60.0
RATE_LIMIT_STATUS = (429, 403)
#: Mirrors `extract.references.CACHEABLE_STATUS`, for the same reason: a cached 429 is a permanent
#: phantom miss, and a rate measured over one measures the cache, not the registry.
CACHEABLE_STATUS = (200, 404)


class Stats:
    """What the run spent. Counted here, reported by the caller — never estimated afterwards."""

    def __init__(self):
        self.requests = 0            # HTTP requests actually put on the wire (cache hits excluded)
        self.cache_hits = 0
        self.rate_limited = 0        # answers with a rate-limit status, retries included
        self.retry_after_seen = 0    # how often the server sent a Retry-After header
        self.errors = 0              # transport failures and unparseable bodies
        self.seconds_sleeping = 0.0  # wall clock spent in the back-off ladder
        self.batch_calls = 0
        self.batch_ids = 0
        self.match_calls = 0
        self.prefill_hits = 0        # per-item requests the batch pre-pass made unnecessary

    def asdict(self):
        return {k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in vars(self).items() if not k.startswith("_")}


def cache_key(method, url, body):
    """The versioned request key. The schema version is INSIDE the hashed string, so bumping it
    invalidates every entry at once without touching the cache directory."""
    raw = f"{CACHE_SCHEMA}|{method}|{url}|{hashlib.sha256((body or '').encode('utf-8')).hexdigest()}"
    return raw


def paper_id_for(ref):
    """The identifier form the batch endpoint takes for a reference, or ''. `DOI:`/`ARXIV:` prefixes
    are harvested from the MCP repo (module docstring)."""
    doi = ref.get("doi_norm") or normalize_doi(ref.get("doi"))
    if doi:
        # `normalize_doi` lowercases, so the registered `10.48550/arXiv.` form arrives folded; the
        # prefix test is therefore case-insensitive or every arXiv DOI is sent as an unknown DOI.
        if doi.lower().startswith(ARXIV_DOI_PREFIX.lower()):
            return "ARXIV:" + doi[len(ARXIV_DOI_PREFIX):]
        return "DOI:" + doi
    arx = (ref.get("arxiv") or "").strip()
    return "ARXIV:" + arx if arx else ""


def _retry_after(headers):
    """-> seconds, or None. Delta-seconds only; an HTTP-date form is not honoured (it is not sent by
    this endpoint, and guessing at clock skew is worse than the ladder)."""
    for k, v in (headers or {}).items():
        if str(k).lower() == "retry-after":
            try:
                return max(0.0, float(str(v).strip()))
            except ValueError:
                return None
    return None


def to_candidate(rec):
    """An S2 paper record -> the shared candidate shape `judge_candidate` already reads."""
    ext = (rec or {}).get("externalIds") or {}
    doi = normalize_doi(ext.get("DOI") or "")     # per-call-site row P7-S2
    if not doi and ext.get("ArXiv"):
        doi = ARXIV_DOI_PREFIX + str(ext["ArXiv"])
    auths = (rec or {}).get("authors") or []
    return {"doi": doi, "titles": [(rec or {}).get("title") or ""],
            "family": (auths[0] or {}).get("name", "") if auths else "",
            "year": (rec or {}).get("year")}


class S2Client:
    """Batch + title-match against the public pool, cached, backed off, counted.

    `client` is anything with the `litkb.netutil.Client` face; `cache` anything with
    `get(key)`/`put(key, status, body)` (`extract.references.DiskCache` is the one in use). Both are
    injected, so every test here runs without a socket or a temp directory unless it wants one.
    """

    def __init__(self, client=None, cache=None, fields=FIELDS, backoffs=BACKOFFS,
                 sleep=time.sleep, jitter=None, stats=None):
        if client is None:
            from litkb.netutil import Client
            client = Client()
        self.client = client
        self.cache = cache
        self.fields = fields
        self.backoffs = tuple(backoffs)
        self.sleep = sleep
        self.jitter = random.random if jitter is None else jitter
        self.stats = stats if stats is not None else Stats()
        #: identifier -> record (or None, meaning "asked, unknown"), filled by :func:`batch_prefill`.
        self.prefill = {}

    # ── one request, with the ladder ────────────────────────────────────────────────────

    def _cached(self, key):
        if self.cache is None:
            return None
        hit = self.cache.get(key)
        if hit is None:
            return None
        self.stats.cache_hits += 1
        return hit

    def _store(self, key, status, body):
        # BEGIN guard: s2 only a settled answer is cached
        if self.cache is None or status not in CACHEABLE_STATUS:
            return
        # END guard: s2 only a settled answer is cached
        self.cache.put(key, status, body)

    def request(self, method, url, body=None):
        """-> (status, parsed_json_or_None, error_string). Never raises.

        The ladder: on a rate-limit status, wait `Retry-After` when the server sends one (capped) and
        the jittered backoff otherwise, then retry. When it is exhausted the LAST rate-limit status is
        returned with an error naming it — the caller's `StageBreaker` then trips the stage, which is
        a recorded skip and not a silent one.
        """
        key = cache_key(method, url, body)
        hit = self._cached(key)
        if hit is not None:
            return hit[0], _parse(hit[1]), ""
        last_status, last_err = 0, ""
        for attempt in range(len(self.backoffs) + 1):
            self.stats.requests += 1
            if method == "POST":
                st, hd, raw = self.client.get(
                    url, accept="application/json", timeout=60,
                    data=(body or "").encode("utf-8"),
                    headers={"Content-Type": "application/json"})
            else:
                st, hd, raw = self.client.get(url, accept="application/json", timeout=60)
            last_status = st
            if st in RATE_LIMIT_STATUS:
                self.stats.rate_limited += 1
                last_err = f"semanticscholar status {st}"
                if attempt >= len(self.backoffs):
                    break
                ra = _retry_after(hd)
                if ra is not None:
                    self.stats.retry_after_seen += 1
                delay = self.backoffs[attempt]
                if ra is not None and ra <= RETRY_AFTER_CAP:
                    delay = ra
                elif ra is not None:
                    break            # the server named a wait longer than a measurement can hold
                delay *= (1.0 + JITTER * self.jitter())
                self.stats.seconds_sleeping += delay
                self.sleep(delay)
                continue
            if st == 0:
                self.stats.errors += 1
                return 0, None, redact(f"semanticscholar status 0 ({(raw or b'')[:120]!r})")
            if st not in (200, 404):
                self.stats.errors += 1
                return st, None, f"semanticscholar status {st}"
            self._store(key, st, raw)
            return st, _parse(raw), ""
        return last_status, None, last_err or f"semanticscholar status {last_status}"

    # ── the two endpoints ───────────────────────────────────────────────────────────────

    def batch(self, ids):
        """Up to :data:`BATCH_MAX` identifiers per call -> ({id: record-or-None}, error).

        THE ALIGNMENT KILL. The response is a list positionally aligned with the ids that were sent,
        with a null where the identifier is unknown. If it is the wrong length the alignment is gone
        and zipping it would silently attach one paper's metadata to another reference's id, so the
        whole chunk is reported unresolved with a named error instead. (The harvested repo enumerates
        the response without a length check; that is the one pattern deliberately not reproduced.)
        Ids are de-duplicated before the call and mapped back afterwards, so a reference list that
        cites one work twice still costs one slot.
        """
        uniq, seen = [], set()
        for i in ids:
            if i and i not in seen:
                seen.add(i)
                uniq.append(i)
        out = {i: None for i in uniq}
        if not uniq:
            return out, ""
        for start in range(0, len(uniq), BATCH_MAX):
            chunk = uniq[start:start + BATCH_MAX]
            url = f"{BATCH_URL}?fields={self.fields}"
            self.stats.batch_calls += 1
            self.stats.batch_ids += len(chunk)
            st, data, err = self.request("POST", url, json.dumps({"ids": chunk}))
            if err:
                return out, err
            if not isinstance(data, list):
                return out, f"batch body is {type(data).__name__}, not a list"
            # BEGIN guard: s2 a batch response must align with the ids it answers
            if len(data) != len(chunk):
                return out, (f"batch length mismatch: sent {len(chunk)} ids, got {len(data)} "
                             f"records — the chunk is unaligned and none of it is used")
            # END guard: s2 a batch response must align with the ids it answers
            for pid, rec in zip(chunk, data):
                out[pid] = rec if isinstance(rec, dict) and rec else None
        return out, ""

    def match(self, title):
        """The title-match endpoint -> (candidates, error). 404 is the documented "no match" answer
        and is a settled, cacheable one: it means asked-and-answered, not failed."""
        from urllib.parse import quote
        url = f"{MATCH_URL}?query={quote(title, safe='')}&fields={self.fields}"
        self.stats.match_calls += 1
        st, data, err = self.request("GET", url)
        if err:
            return [], err
        if st == 404 or not isinstance(data, dict):
            return [], ""
        recs = data.get("data") or []
        return [to_candidate(r) for r in recs if isinstance(r, dict)], ""


def _parse(raw):
    try:
        return json.loads((raw or b"").decode("utf-8", "replace"))
    except Exception:
        return None


def search_semanticscholar_s2(s2, ref=None):
    """-> a `REGISTRY_STAGES`-shaped search function backed by this client.

    BATCH FIRST, PER-ITEM ONLY FOR THE STRAGGLERS. If the reference carries an identifier that the
    pre-pass already asked about, the answer is used and NO request is made — including when the
    pre-pass learned the identifier is unknown, which is an answer too (`None` -> no candidates).
    Only a reference the batch could not carry reaches the match endpoint.

    The stage keeps the name `semanticscholar`, so the breaker, the `skipped=` reason tail and every
    per-stage number stay comparable with the P6 run they are measured against.
    """
    def search(_client, title, _pacer):
        pid = paper_id_for(ref) if ref else ""
        if pid and pid in s2.prefill:
            s2.stats.prefill_hits += 1
            rec = s2.prefill[pid]
            return ([to_candidate(rec)] if rec else []), ""
        return s2.match(title)
    return search


def batch_prefill(refs, s2):
    """One batch call covering every reference that carries an identifier -> ({id: record|None}, err).

    The answers land in ``s2.prefill``, which :func:`search_semanticscholar_s2` reads instead of
    asking again. Its LEVERAGE ON THIS CORPUS IS SMALL BY CONSTRUCTION and the report says so — a
    reference with a DOI is decided by that DOI at Crossref and never reaches this leg, so what is
    left to batch is the arXiv-identified references and whatever a future corpus brings. It is
    built, tested and kill-tested here so the next corpus does not pay per item for it. On an error
    the prefill stays empty and every reference falls back to the per-item leg — a failed batch must
    never look like a batch full of misses.
    """
    ids = [pid for pid in (paper_id_for(r) for r in refs) if pid]
    got, err = s2.batch(ids)
    if not err:
        s2.prefill.update({k: v for k, v in got.items()})
    return got, err

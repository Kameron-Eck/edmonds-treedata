r"""Recorded HTTP for litkb: a cassette at the ONE socket path, and a socket guard (S4.5 item 7).

WHY. The edge register was graded against a world the instrument wrote itself: `_acquirer_stub`
(qc/instruments/litkb_edge_run.py) returned the register's own `route_detail` and no route ever ran,
so E13 passed on state while its recorded ladder disagreed in route count, status and every HTTP
code (Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md §1.10). The fix is the order RECORD ->
REPLAY -> REFEREE: one live pass records what every host actually answered, and every replay after
it runs the REAL acquisition ladder against those answers with no socket open.

WHERE IT SITS. `litkb.netutil.Client._raw_get` is the one function every `Client` request goes
through (survey-code §1.1). It asks :func:`active` for the cassette in force and, in REPLAY mode,
answers from it and returns before any opener is touched; in RECORD mode it makes the request and
hands the answer here to be written down. Nothing else in the package changes.

ACTIVATION IS AN ENVIRONMENT VARIABLE, and it has to be: the MCP `litkb_hunt` tool runs the hunt in
a CHILD process (`py -m litkb hunt`, survey-code §1.4 bypass 4), and an in-process patch never
reaches a child, while an environment variable is inherited (`LITKB_REGISTRY_CACHE` works the same
way). :data:`ENV_MODE` is `off` | `record` | `replay`; :data:`ENV_INDEX` names the index file and is
REQUIRED in the two live modes (a cassette with no named home fails closed rather than writing
somewhere); :data:`ENV_BODIES` names the body store; :data:`ENV_ROW` tags a child's requests with
the row it is serving. A test installs one in-process with :func:`use` instead.

THE KEY is what changes the answer: method, URL, the Accept / Range / Referer headers, whether
redirects are followed (the two openers answer one URL differently: `_nofollow` returns the 3xx),
and the sha256 of any request body. The User-Agent is NOT in it: FlareSolverr adoption rewrites it
mid-run, and a key that moved with it would miss on every retry. Secrets never reach the key: the URL
passes through `netutil.redact` and a query-parameter scrub (:data:`SCRUB_PARAMS` — the archive's
`key`, Unpaywall's `email`, the polite pools' `mailto`), and a body is hashed AFTER the registered
secrets are replaced, so the index holds no credential and no value derived from one.

A REQUEST ASKED TWICE is answered in order. Recordings are grouped by the ROW they were made for
(:meth:`Cassette.begin_row` — the run driver passes the reference, so the live pass and the register
replay, which use different row ids for one reference, meet on the same tag) and the n-th request for
one key in a row gets the n-th recording. One more request than was recorded is a MISS: a replay that
retries more than the live run did has diverged, and serving the last answer again would hide it.
A row recorded twice (a resumed run re-running a half-recorded row) is superseded whole: every entry
carries its `take`, and only a row's latest take is replayed.

THE BODY. Inline (base64, in the tracked index) up to :data:`INLINE_MAX_BYTES`; above it, and for
EVERY PDF whatever its size, content-addressed by sha256 in an untracked store under the derived root.
PDFs never enter the repository because they are publishers' articles — the tracked index would be a
redistribution — and because they are large. The threshold is 64 KiB because every non-PDF body
litkb has kept falls under it except one: the Akamai refusals are 409-413 B, the Cloudflare challenge
pages 5,604-5,848 B, sci-hub.wf's 200 page 5,182 B, a Sci-Hub miss page 11,350 B, the census.gov 404
page 25,773 B and the Crossref blog snapshot 56,598 B, while the ScienceDirect error page is 832,805 B
(survey-data §2.5, §2.2, §2.6; qc/fixtures/litkb_web_snapshot_crossref_blog.html) — so the pages a
replay most needs replay from a fresh checkout, and only the one outlier needs the store. A replay
whose stored body is missing, or whose bytes no longer hash to the index's sha, FAILS CLOSED
(:class:`CassetteBodyMissing`, a miss) — never a fall-through to the network.

THE GUARD. :class:`SocketGuard` patches `socket.socket.connect` / `connect_ex`,
`socket.getaddrinfo` and `socket.gethostbyname` / `gethostbyname_ex` for the duration of a `with`
block: a connect to a host outside `allow_hosts`,
or a name lookup of a non-loopback name, is COUNTED and then refused with :class:`NetworkBlocked`
(an OSError, so the calling code sees an offline network, not a new exception class). Counting and
refusing are separate steps on purpose: with the refusal removed the connect goes ahead and is still
counted, which is what `replay_network_calls` needs to be a measurement rather than a promise. libpq
opens PostgreSQL's socket in C, so the guard never sees litkb's own database connection; loopback
names still resolve so psycopg's host lookup keeps working. qc/conftest.py runs every test inside one
that allows loopback as HOST AND PORT (Codex finding X3): PostgreSQL's port, GROBID's, and a port this
process bound itself (a test's own local server, asyncio's self-pipe) — :func:`watch_loopback_binds`
records those — so a loopback port that forwards elsewhere (a proxy, a tunnel, a solver) is not
reachable by a test. The replay runs inside one that allows nothing.

Stdlib only, so `import litkb` stays light (netutil's rule). Every recorded or replayed interaction
is also kept on the object (`served`, `misses`, `recorded`) so an instrument can read what a replay
did without re-reading the file.
"""
import base64
import contextlib
import datetime
import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import uuid
from pathlib import Path

MODES = ("off", "record", "replay")
ENV_MODE = "LITKB_CASSETTE"
ENV_INDEX = "LITKB_CASSETTE_INDEX"
ENV_BODIES = "LITKB_CASSETTE_BODIES"
ENV_ROW = "LITKB_CASSETTE_ROW"

INDEX_KIND = "litkb-cassette"
INDEX_VERSION = 1

#: Bodies above this many bytes go to the content-addressed store; below it they are inlined. The
#: measured body sizes this number was chosen against are in the module docstring.
INLINE_MAX_BYTES = 65536

#: The request headers that change the answer (the brief's list: Accept, Range, Referer). Compared
#: case-insensitively; a header absent from the request is the empty string in the key.
KEY_HEADERS = ("accept", "range", "referer")

#: Query parameters whose VALUE is masked in every recorded URL and header value. `key` is the
#: archive's fast-download key (netutil's `_URL_NAMES`), `email` Unpaywall's, `mailto` the polite
#: pool's (the OpenAlex probe hard-codes Kam's address in one, survey-code §9).
SCRUB_PARAMS = ("key", "email", "mailto", "api_key", "apikey", "token", "access_token",
                "secret", "password")
MASK = "<KEY>"
#: The value group takes an already-masked value WHOLE first, so the mask is IDEMPOTENT: a link the
#: ladder reads out of a replayed (masked) body, or a masked `Location` header it follows, keys to the
#: same URL the recording was keyed on. Without it `?token=<KEY>` became `?token=<KEY><KEY>` (the
#: value class stops at `<`) and the replay MISSED a request the live pass had made (auditor-A round
#: 2, F4, demonstration DS1).
_SCRUB_RE = re.compile(r"(?i)([?&;](?:" + "|".join(SCRUB_PARAMS) + r")=)(" + re.escape(MASK)
                       + r"|[^&#;\s\"'<>]*)")

#: A PDF body is never inlined, whatever its size (module docstring).
_PDF_MAGIC = b"%PDF-"

#: How far into a body the PDF magic is looked for. 1 KiB, the window the auditor-A round-1 note
#: F10 named: a PDF whose `%PDF-` follows a byte-order mark or a short junk prefix (the acceptance
#: test's own REPAIR case, `litkb.acquire.accept`) is still a PDF and still never inlined. Not
#: calibrated on a recording; it only has to be at least as wide as any prefix litkb repairs.
_PDF_SNIFF_BYTES = 1024

#: The query-parameter mask as BYTES, for a small text body the index inlines (a 404 page that echoes
#: its request URL would otherwise carry `mailto=`/`email=` into the tracked file: auditor-A F10).
_SCRUB_RE_B = re.compile(rb"(?i)([?&;](?:" + "|".join(SCRUB_PARAMS).encode() + rb")=)("
                         + re.escape(MASK.encode()) + rb"|[^&#;\s\"'<>]*)")


class CassetteError(RuntimeError):
    """The cassette itself is unusable: no index named, a bad header line, an unknown mode."""


class CassetteMiss(Exception):
    """A replayed request the cassette cannot answer. NEVER a fall-through to the network.

    An `Exception`, so the ladder's own boundaries (a route that raises is an `api-error` attempt;
    an unexpected raise out of a hunt is `crashed` at a named stage) name it rather than dying — and
    the miss is ALSO kept on the cassette (`misses`), which is what the replay grades, so a boundary
    that absorbed it cannot make a missed row look answered."""


class CassetteBodyMissing(CassetteMiss):
    """The index names a stored body that is not on disk, or whose bytes no longer hash to it."""


class NetworkBlocked(OSError):
    """A connect or a name lookup the socket guard refused. An OSError, so urllib and requests see an
    offline network (status 0 through `Client`), which is exactly what a hermetic run must look like."""


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── scrubbing: nothing that identifies a credential reaches the index ─────────────────────────

def scrub_url(url):
    """A URL with every registered secret and every :data:`SCRUB_PARAMS` value masked."""
    from litkb.netutil import redact

    # BEGIN guard: a recorded URL carries no credential
    return _SCRUB_RE.sub(r"\1" + MASK, redact(url or ""))
    # END guard: a recorded URL carries no credential


def scrub_bytes(data):
    """Bytes with every registered secret (raw and URL-quoted, netutil.add_secret's two forms)
    replaced by the mask. -> (bytes, changed)."""
    from litkb import netutil

    if not data:
        return data, False
    out = data
    # BEGIN guard: a recorded body carries no registered secret
    for sec in list(netutil._SECRETS):
        if sec:
            out = out.replace(sec.encode("utf-8"), MASK.encode())
    # END guard: a recorded body carries no registered secret
    return out, out != data


def request_key(method, url, headers, follow, data):
    """(key dict, key sha256). The key is what changes the answer (module docstring)."""
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    body = b"" if data is None else (data if isinstance(data, bytes) else str(data).encode("utf-8"))
    scrubbed, _changed = scrub_bytes(body)
    key = {"method": method, "url": scrub_url(url), "follow": bool(follow),
           "accept": h.get("accept", ""), "range": h.get("range", ""),
           "referer": scrub_url(h.get("referer", "")),
           "body_sha256": hashlib.sha256(scrubbed).hexdigest() if data is not None else ""}
    blob = json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return key, hashlib.sha256(blob).hexdigest()


def _norm_row(tag):
    return str(tag or "").strip().lower()


# ── the cassette ─────────────────────────────────────────────────────────────────────────────

class Cassette:
    """One index file (JSONL: a header line, then one interaction per line) and its body store."""

    def __init__(self, index, mode, bodies=None):
        if mode not in MODES:
            raise CassetteError(f"litkb cassette: unknown mode {mode!r} (one of {', '.join(MODES)})")
        if not index:
            raise CassetteError(f"litkb cassette: mode {mode!r} needs an index file ({ENV_INDEX})")
        self.mode = mode
        self.index = Path(index)
        self.bodies = Path(bodies) if bodies else default_bodies()
        self._lock = threading.Lock()
        self.row = _norm_row(os.environ.get(ENV_ROW, ""))
        self.take = uuid.uuid4().hex[:12]
        self._seq = {}                  # (row, key_sha) -> requests seen in this row
        self.entries = []               # every live interaction (latest take per row)
        self._by = {}                   # (row, key_sha) -> [entry, ...] in seq order
        self.served = set()             # id(entry) of every interaction a replay answered from
        self.misses = []                # {"row", "key", "why"} for every request replay could not answer
        self.recorded = []              # the interactions THIS object recorded
        self.record_errors = []         # a recording that could not be written: "<Exception>: <text>"
        self.replayed_rows = set()      # every row tag a REPLAY began or asked for (the staleness scope)
        if self.index.is_file():
            self._load()
        elif mode == "replay":
            raise CassetteError(f"litkb cassette: replay needs {self.index}, which does not exist")

    # -- the file --

    def _load(self):
        lines = self.index.read_bytes().splitlines()
        if not lines:
            return
        head = json.loads(lines[0])
        if head.get("kind") != INDEX_KIND:
            raise CassetteError(f"litkb cassette: {self.index} is not a {INDEX_KIND} index "
                                f"(first line kind {head.get('kind')!r})")
        raw = [json.loads(ln) for ln in lines[1:] if ln.strip()]
        latest = {}
        for e in raw:
            latest[e.get("row", "")] = e.get("take")
        for e in raw:
            if e.get("take") == latest.get(e.get("row", "")):
                self.entries.append(e)
        for e in sorted(self.entries, key=lambda x: (x.get("row", ""), x["key_sha256"], x["seq"])):
            self._by.setdefault((e.get("row", ""), e["key_sha256"]), []).append(e)

    def _header(self):
        return {"kind": INDEX_KIND, "version": INDEX_VERSION, "inline_max_bytes": INLINE_MAX_BYTES,
                "key_headers": list(KEY_HEADERS), "scrub_params": list(SCRUB_PARAMS),
                "created_at": _now()}

    def _append(self, entry):
        self.index.parent.mkdir(parents=True, exist_ok=True)
        new = not self.index.is_file() or self.index.stat().st_size == 0
        with open(self.index, "ab") as fh:
            if new:
                fh.write(json.dumps(self._header(), sort_keys=True).encode("utf-8") + b"\n")
            fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
            fh.flush()
            os.fsync(fh.fileno())

    def body_path(self, sha):
        return self.bodies / sha[:2] / f"{sha}.bin"

    def _store(self, data):
        sha = hashlib.sha256(data).hexdigest()
        p = self.body_path(sha)
        if not p.is_file():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".partial")
            tmp.write_bytes(data)
            os.replace(tmp, p)
        return sha

    # -- rows --

    def begin_row(self, tag):
        """Every request until the next call belongs to this row (its sequence numbers restart). In
        record mode the row also gets a new take, so a re-recorded row supersedes its old entries."""
        with self._lock:
            self.row = _norm_row(tag)
            self._seq = {k: v for k, v in self._seq.items() if k[0] != self.row}
            self.take = uuid.uuid4().hex[:12]
            # A row the replay BEGAN is in the staleness scope even when it asks the hosts nothing: every
            # route skipped, a budget stop, a route list naming a rung the live pass did not reach. Its
            # recorded entries are then stale, never "a row nobody replayed" (auditor-A round 2, F1).
            # BEGIN guard: a replayed row that asks nothing still owns its recorded entries
            if self.mode == "replay":
                self.replayed_rows.add(self.row)
            # END guard: a replayed row that asks nothing still owns its recorded entries

    # -- the two directions --

    @staticmethod
    def cookie_names(jar):
        return {c.name for c in jar} if jar is not None else set()

    def record(self, client, url, headers, follow, data, result, cookies_before=None):
        """Write what the client just saw. Never raises into the caller: a recording that cannot be
        written is a lost recording (the replay will MISS on it and say so; `record_errors` names it),
        not a failed request — the live answer is returned to the ladder either way."""
        # BEGIN guard: a recording that cannot be written never fails the live request
        try:
            self._record(client, url, headers, follow, data, result, cookies_before)
        except Exception as e:          # noqa: BLE001 — any failure to write is a lost recording, named
            self.record_errors.append(f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}")
        # END guard: a recording that cannot be written never fails the live request

    @staticmethod
    def is_pdf(data):
        """A PDF, for the inline-or-store decision: `%PDF-` inside the first `_PDF_SNIFF_BYTES`."""
        return _PDF_MAGIC in (data or b"")[:_PDF_SNIFF_BYTES]

    def _record(self, client, url, headers, follow, data, result, cookies_before):
        st, hd, body = result
        method = "GET" if data is None else "POST"
        key, ksha = request_key(method, url, headers, follow, data)
        body = body or b""
        stored, scrubbed = scrub_bytes(body)
        pdf = self.is_pdf(stored)
        inline = not pdf and len(stored) <= INLINE_MAX_BYTES
        # BEGIN guard: an inlined body carries no scrubbed query-parameter value
        if inline:
            masked = _SCRUB_RE_B.sub(rb"\1" + MASK.encode(), stored)
            scrubbed = scrubbed or masked != stored
            stored = masked
        # END guard: an inlined body carries no scrubbed query-parameter value
        after = self.cookie_names(getattr(client, "cj", None))
        with self._lock:
            seq = self._seq.get((self.row, ksha), 0)
            self._seq[(self.row, ksha)] = seq + 1
            resp = {"status": int(st or 0),
                    "headers": {str(k): scrub_url(str(v)) for k, v in (hd or {}).items()
                                if str(k).lower() != "set-cookie"},
                    "cookies_set": sorted(after - (cookies_before or set())),
                    "body": {"sha256": hashlib.sha256(stored).hexdigest(), "length": len(stored),
                             "served_sha256": hashlib.sha256(body).hexdigest(), "scrubbed": scrubbed}}
            if inline:
                resp["body"]["inline_b64"] = base64.b64encode(stored).decode("ascii")
            else:
                resp["body"]["stored"] = True
                self._store(stored)
            entry = {"row": self.row, "take": self.take, "seq": seq, "key": key, "key_sha256": ksha,
                     "recorded_at": _now(), "response": resp}
            self._append(entry)
            self.recorded.append(entry)

    def replay(self, client, url, headers, follow, data):
        """-> (status, headers, body) from the index. Raises :class:`CassetteMiss` (and keeps it in
        `misses`) for a request the index cannot answer; never opens a socket."""
        method = "GET" if data is None else "POST"
        key, ksha = request_key(method, url, headers, follow, data)
        with self._lock:
            self.replayed_rows.add(self.row)
            seq = self._seq.get((self.row, ksha), 0)
            self._seq[(self.row, ksha)] = seq + 1
            got = self._by.get((self.row, ksha)) or []
            # BEGIN guard: a replayed request the cassette cannot answer is a named miss
            if seq >= len(got):
                why = ("never recorded" if not got else
                       f"asked {seq + 1} times, recorded {len(got)}")
                self.misses.append({"row": self.row, "key": key, "why": why})
                raise CassetteMiss(f"litkb cassette {self.index.name}: no recording for "
                                   f"{method} {key['url']} (row {self.row!r}, {why})")
            # END guard: a replayed request the cassette cannot answer is a named miss
            entry = got[seq]
            self.served.add(id(entry))
        resp = entry["response"]
        body = self._body(entry)
        jar = getattr(client, "cj", None)
        if jar is not None:
            for name in resp.get("cookies_set") or []:
                _set_cookie(jar, url, name)
        return resp["status"], dict(resp.get("headers") or {}), body

    def _body(self, entry):
        b = entry["response"]["body"]
        if "inline_b64" in b:
            data = base64.b64decode(b["inline_b64"])
        else:
            p = self.body_path(b["sha256"])
            data = p.read_bytes() if p.is_file() else b""
            # BEGIN guard: a stored body that is missing or altered fails closed
            if not p.is_file():
                self.misses.append({"row": entry.get("row", ""), "key": entry["key"],
                                    "why": f"stored body {b['sha256'][:12]} is not in {self.bodies}"})
                raise CassetteBodyMissing(f"litkb cassette: stored body {b['sha256']} is not in "
                                          f"{self.bodies} (record it, or point {ENV_BODIES} at the store)")
            if hashlib.sha256(data).hexdigest() != b["sha256"]:
                self.misses.append({"row": entry.get("row", ""), "key": entry["key"],
                                    "why": f"stored body {b['sha256'][:12]} no longer hashes to its name"})
                raise CassetteBodyMissing(f"litkb cassette: {p} does not hash to {b['sha256']}")
            # END guard: a stored body that is missing or altered fails closed
        return data

    # -- what a replay did --

    def unplayed(self, rows=None):
        """Every live index entry of a replayed row (default: every row tag this object's replay began
        or asked for, `replayed_rows`) that no replay through THIS object answered.

        SCOPED TO THE ROWS REPLAYED, deliberately (auditor-A round 1, F1): the live pass records every
        manifest row into ONE index and a replay grades a subset of them (the register), so an entry of
        a row the replay never began is not a divergence — it is a row nobody replayed, and
        :meth:`rows_not_replayed` lists it separately. Inside a replayed row, an entry nobody asked for
        IS stale: the replay asked the hosts less than the live run did."""
        rows = self.replayed_rows if rows is None else {_norm_row(r) for r in rows}
        # BEGIN guard: only a row this replay began can leave an entry stale
        return [e for e in self.entries if e.get("row", "") in rows and id(e) not in self.served]
        # END guard: only a row this replay began can leave an entry stale

    def rows_not_replayed(self):
        """[{"row", "entries"}] for every recorded row tag this object's replay never began or asked
        for — REPORTED beside the staleness diff, never counted in it."""
        counts = {}
        for e in self.entries:
            r = e.get("row", "")
            if r not in self.replayed_rows:
                counts[r] = counts.get(r, 0) + 1
        return [{"row": r, "entries": n} for r, n in sorted(counts.items())]

    def stale(self):
        """-> {"unplayed": [...], "misses": [...]} — the staleness diff, both halves listed."""
        return {"unplayed": [{"row": e.get("row", ""), "url": e["key"]["url"], "seq": e["seq"]}
                             for e in self.unplayed()],
                "misses": [{"row": m["row"], "url": m["key"]["url"], "why": m["why"]}
                           for m in self.misses]}


def _set_cookie(jar, url, name):
    """Adopt a recorded cookie NAME into a replaying client's jar. The value was never recorded (it
    is a session credential); `Client.login` checks only that the account cookie exists."""
    import http.cookiejar
    import urllib.parse

    host = urllib.parse.urlparse(url).hostname or ""
    jar.set_cookie(http.cookiejar.Cookie(
        version=0, name=name, value=MASK, port=None, port_specified=False, domain=host,
        domain_specified=False, domain_initial_dot=False, path="/", path_specified=True,
        secure=False, expires=None, discard=True, comment=None, comment_url=None, rest={}))


def index_sha256(path):
    """sha256 of the index file's BYTES. The index is recorded bytes (`binary` in .gitattributes),
    so its bytes are its identity; a CRLF fold here would hide an edit to an inline body."""
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def default_bodies():
    """The body store: :data:`ENV_BODIES`, else `cassette_bodies/` under litkb's derived root
    (`litkb.extract.references.DERIVED_ROOT`, `LITKB_DERIVED`) — untracked by construction."""
    env = os.environ.get(ENV_BODIES)
    if env:
        return Path(env)
    from litkb.extract.references import DERIVED_ROOT

    return Path(DERIVED_ROOT) / "cassette_bodies"


# ── which cassette is in force ───────────────────────────────────────────────────────────────

_explicit = []                      # a stack of cassettes installed by use()
_env_cache = {}                     # (mode, index, bodies) -> Cassette


def active():
    """The cassette every `Client` in this process consults, or None. An explicit :func:`use` wins
    over the environment; the environment's cassette is built once per (mode, index, bodies), so
    every client in a process shares one ledger of served requests and misses."""
    if _explicit:
        return _explicit[-1]
    mode = (os.environ.get(ENV_MODE) or "off").strip().lower()
    if mode in ("", "off"):
        return None
    key = (mode, os.environ.get(ENV_INDEX, ""), os.environ.get(ENV_BODIES, ""))
    cas = _env_cache.get(key)
    if cas is None:
        cas = Cassette(key[1], mode, bodies=key[2] or None)
        _env_cache[key] = cas
    return cas


@contextlib.contextmanager
def use(cassette):
    """Install `cassette` for the duration of a `with` block (tests, the replay driver)."""
    _explicit.append(cassette)
    try:
        yield cassette
    finally:
        _explicit.remove(cassette)


# ── the socket guard ─────────────────────────────────────────────────────────────────────────

LOOPBACK = "loopback"

#: Every port a socket of THIS process bound on a loopback or wildcard address, since
#: :func:`watch_loopback_binds` ran (a test's own HTTP server, asyncio's self-pipe socketpair — on
#: Windows `socket.socketpair` is Python's loopback emulation, measured on 3.12.10: it binds
#: 127.0.0.1:0 through `socket.socket.bind`). A loopback connect to one of these reaches this
#: process's own listener; that is what `allow_ports` lets through besides the ports it names.
_LOOPBACK_BOUND = set()
_bind_watch = []


def watch_loopback_binds():
    """Record, for the rest of this process, the port of every bind on a loopback or wildcard address
    into :data:`_LOOPBACK_BOUND`. Idempotent. A process-lifetime patch of `socket.socket.bind` that only
    RECORDS (the bind itself is untouched), so a server a fixture bound before any guard was entered —
    a module-scoped one — is known too. qc/conftest.py calls it at configure time; every
    :class:`SocketGuard` calls it on entry."""
    with SocketGuard._patch_lock:
        if _bind_watch:
            return
        orig = socket.socket.bind

        def bind(sock, address):
            out = orig(sock, address)
            try:
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    host, port = sock.getsockname()[:2]
                    if is_loopback(host):
                        _LOOPBACK_BOUND.add(int(port))
            except (OSError, ValueError, TypeError):
                pass
            return out
        socket.socket.bind = bind
        _bind_watch.append(orig)


def is_loopback(host):
    """localhost, 127.0.0.0/8, ::1 — and the unspecified address, which a connect reaches only on
    this machine."""
    h = str(host or "").strip().strip("[]").lower()
    if h in ("localhost", "localhost.localdomain", "ip6-localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h.split("%", 1)[0])
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


class SocketGuard:
    """Count, then refuse, every connect to a host outside `allow_hosts` and every lookup of a
    non-loopback name (getaddrinfo, gethostbyname, gethostbyname_ex), for the duration of a `with`
    block.

    `allow_hosts` is :data:`LOOPBACK` (loopback addresses) or a tuple of host strings — `()` allows
    nothing (the replay's setting). With :data:`LOOPBACK`, `allow_ports` narrows it to HOST AND PORT
    (Codex finding X3, brief-CONTRACTS.md): a loopback connect is allowed only to a port in
    `allow_ports` or to a port this process bound itself (:data:`_LOOPBACK_BOUND`); `None` allows every
    loopback port. The test suite's setting is loopback + PostgreSQL's and GROBID's ports
    (qc/conftest.py). `refuse=False` counts without refusing (an observer). `attempts` holds one
    {host, port, how, refused} per attempt, allowed ones included with `refused: False` and
    `allowed: True` so a caller can see loopback use too."""

    _patch_lock = threading.RLock()

    def __init__(self, allow_hosts=LOOPBACK, *, allow_ports=None, refuse=True, label="socket guard"):
        self.allow_hosts = allow_hosts
        self.allow_ports = None if allow_ports is None else frozenset(int(p) for p in allow_ports)
        self.refuse = refuse
        self.label = label
        self.attempts = []
        self._saved = None

    def allows(self, host, port=None):
        if self.allow_hosts == LOOPBACK:
            if not is_loopback(host):
                return False
            # BEGIN guard: a loopback connect is allowed only to a named port or one this process bound
            if self.allow_ports is not None and port is not None:
                try:
                    p = int(port)
                except (TypeError, ValueError):
                    return False
                return p in self.allow_ports or p in _LOOPBACK_BOUND
            # END guard: a loopback connect is allowed only to a named port or one this process bound
            return True
        return str(host or "").strip().lower() in {str(h).lower() for h in (self.allow_hosts or ())}

    @property
    def blocked(self):
        """Attempts at a host outside the allow set (refused or not)."""
        return [a for a in self.attempts if not a["allowed"]]

    def _check(self, host, port, how):
        allowed = self.allows(host, port)
        a = {"host": str(host), "port": port, "how": how, "allowed": allowed, "refused": False}
        self.attempts.append(a)
        if allowed:
            return
        # BEGIN guard: a connect outside the allow set is refused
        if self.refuse:
            a["refused"] = True
            raise NetworkBlocked(f"{self.label}: refused {how} to {host}:{port} (a hermetic run opens "
                                 "no socket outside its allow set)")
        # END guard: a connect outside the allow set is refused

    def __enter__(self):
        guard = self
        watch_loopback_binds()
        with self._patch_lock:
            orig_connect = socket.socket.connect
            orig_connect_ex = socket.socket.connect_ex
            orig_gai = socket.getaddrinfo
            orig_ghbn = socket.gethostbyname
            orig_ghbn_ex = socket.gethostbyname_ex
            self._saved = (orig_connect, orig_connect_ex, orig_gai, orig_ghbn, orig_ghbn_ex)

            def _addr(address):
                if isinstance(address, tuple) and len(address) >= 2:
                    return address[0], address[1]
                return address, None

            def connect(sock, address):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    guard._check(*_addr(address), "connect")
                return orig_connect(sock, address)

            def connect_ex(sock, address):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    guard._check(*_addr(address), "connect_ex")
                return orig_connect_ex(sock, address)

            def getaddrinfo(host, port, *a, **kw):
                # a loopback NAME always resolves: psycopg looks its host up in Python, and a lookup
                # of `localhost` sends nothing off the machine. The connect decides for loopback.
                if host is not None and not is_loopback(host if isinstance(host, str)
                                                        else host.decode("ascii", "replace")):
                    guard._check(host, port, "getaddrinfo")
                return orig_gai(host, port, *a, **kw)

            # the resolver's two older entry points, which do not go through getaddrinfo in Python
            # (auditor-A round 1, F11): a lookup through them sends a DNS query all the same
            def gethostbyname(host):
                if not is_loopback(host):
                    guard._check(host, None, "gethostbyname")
                return orig_ghbn(host)

            def gethostbyname_ex(host):
                if not is_loopback(host):
                    guard._check(host, None, "gethostbyname_ex")
                return orig_ghbn_ex(host)

            socket.socket.connect = connect
            socket.socket.connect_ex = connect_ex
            socket.getaddrinfo = getaddrinfo
            # BEGIN guard: a lookup through the older resolver calls is counted and refused too
            socket.gethostbyname = gethostbyname
            socket.gethostbyname_ex = gethostbyname_ex
            # END guard: a lookup through the older resolver calls is counted and refused too
        return self

    def __exit__(self, *exc):
        with self._patch_lock:
            if self._saved is not None:
                (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo,
                 socket.gethostbyname, socket.gethostbyname_ex) = self._saved
                self._saved = None
        return False

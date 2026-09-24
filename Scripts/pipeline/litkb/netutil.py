"""HTTP client, pacer and secret redaction shared by the registry resolver and the acquisition routes.

Ported from D:\\tools\\annas-mcp\\aa_fetch.py (2026-09-13, its verified gates; design §10). Stdlib only, so
`import litkb` stays light. The client never raises and never leaks a registered secret: every string it
returns for an error, and every log line built from it, goes through redact().
"""
import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://annas-archive.gl"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"
CHALLENGE_RE = re.compile(rb"Just a moment|DDoS-Guard|Checking your browser", re.I)

SCIDB_MIN_INTERVAL = 5.0
RATE_BACKOFF = 60.0

_SECRETS = []


def add_secret(s):
    if s and s.strip():
        _SECRETS.append(s.strip())
        _SECRETS.append(urllib.parse.quote(s.strip(), safe=""))


def redact(s):
    s = str(s)
    for sec in _SECRETS:
        if sec:
            s = s.replace(sec, "<KEY>")
    return s


# ── credential SHAPES, for the MCP output boundary (P8 referee F-4) ───────────────────────
#
# redact() above replaces REGISTERED strings: the archive key, the workstream token — whatever
# add_secret() was given. That is a token redactor, and the P8 referee showed what it is not: a
# block holding `localhost:5433:litkb:litkb_writer:<a password>` was planted in the corpus and came
# back through litkb_search verbatim, because nobody had registered that password and nobody could
# have. A credential this process never held still must not travel out through a tool result.
#
# So the rules below match by SHAPE. Two of them are not written here at all — they are read from
# qc/secrets_check.py, the ladder rung that already refuses these shapes in git's index, so that the
# definition of "this is a pgpass line" lives in exactly one file (CLAUDE.md §3.3). That module is
# stdlib-only and imports nothing from litkb, so loading it by path is cheap and cannot cycle; it is
# loaded by PATH rather than by `import qc.secrets_check` because qc/ is not import surface and that
# ledger is closed (qc/test_status_discovery.py::test_path_insert_ledger).
#
# What is deliberately NOT masked, because masking it would break real answers:
#   * a bare 64-hex value. A sha256 is 64 hex, and every file record litkb_work returns carries one.
#     The token rule fires only when the value is ASSIGNED to a token-like NAME (`token=`, `secret:`,
#     `password=`), which is secrets_check's own rule and the reason a file's sha256 still shows.
#   * a field called `key`. In this database `key` is the WORK key (`Rosychuk_2003_…`) and `work_key`
#     is on every search hit. `key=` is masked only inside a URL query, where the archive's
#     fast-download key is the thing that actually leaks.
# Known limit: the pgpass rule is line-anchored, as it is in the rung, so a pgpass line pasted into
# the MIDDLE of a line of prose is matched by none of these. The assignment rule catches the common
# spelling of that (`PGPASSWORD=…`, `password=…`); the shape rules are a boundary, not a proof.
_SHAPE_SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "qc", "secrets_check.py")

#: names whose VALUE is a credential wherever it appears. `key` is absent on purpose (see above).
_SECRET_NAMES = (r"password|passwd|pwd|token|secret|api[_-]?key|apikey|authorization|bearer"
                 r"|access[_-]?token|private[_-]?key|pgpassword")
#: inside a URL query string the name `key` is unambiguous — that is the archive's download key.
_URL_NAMES = _SECRET_NAMES + r"|key"

_URL_PARAM_RE = re.compile(rf"(?i)[?&](?:{_URL_NAMES})=(?P<v>[^&\s\"'<>]+)")
_JSON_FIELD_RE = re.compile(rf"(?i)\"(?:{_SECRET_NAMES})\"\s*:\s*\"(?P<v>[^\"]+)\"")
_ASSIGN_RE = re.compile(rf"(?i)(?<![\w.-])(?:{_SECRET_NAMES})\s*[:=]\s*[\"']?(?P<v>[^\s\"'&;,}}]{{8,}})")
_PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]+-----(?P<v>.*?)-----END [A-Z0-9 ]+-----", re.S)
#: a dict KEY that names a credential; the value under it is masked whole. `key` is absent
#: here for the same reason as above — in this database `key` is the work key.
_SECRET_KEY_RE = re.compile(rf"(?i)(?:{_SECRET_NAMES})")

_shape_rules_cache = []


def shape_rules():
    """[(compiled regex with a group `v`, line_anchored)] — the credential shapes this boundary masks.

    The first two come from qc/secrets_check.py so that the rung and the boundary cannot disagree
    about what a pgpass line or an assigned 64-hex token looks like."""
    if _shape_rules_cache:
        return _shape_rules_cache
    import importlib.util

    spec = importlib.util.spec_from_file_location("_litkb_secret_shapes", _SHAPE_SOURCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _shape_rules_cache.extend([(mod.PGPASS_RE, True), (mod.TOKEN_RE, False),
                               (_URL_PARAM_RE, False), (_JSON_FIELD_RE, False),
                               (_ASSIGN_RE, False), (_PEM_RE, False)])
    return _shape_rules_cache


def _mask(rx, s):
    """Replace only group `v` of every match — the VALUE — and keep the shape around it, so a reader
    can see that something was masked and what kind of thing it was."""
    def repl(m):
        whole, off = m.group(0), m.start()
        if m.group("v") is None:
            return whole
        return whole[:m.start("v") - off] + "<KEY>" + whole[m.end("v") - off:]
    return rx.sub(repl, s)


def redact_shapes(obj):
    """Mask credential SHAPES in every string this object carries, structure unchanged.

    Applied to the OBJECT, not to the JSON text, and that is the whole point: a block's text is one
    JSON string by the time json.dumps has run, and a line-anchored rule can never match inside it
    (the newlines are `\\n` escapes). Non-strings — ints, UUIDs, datetimes — are returned as they are,
    so json.dumps still sees what it saw before."""
    if isinstance(obj, str):
        for rx, line_anchored in shape_rules():
            if line_anchored:
                obj = "\n".join(_mask(rx, line) for line in obj.split("\n"))
            else:
                obj = _mask(rx, obj)
        return obj
    if isinstance(obj, dict):
        # a FIELD NAME is a rule too, not only text that looks like JSON: a value under a key called
        # `password` or `token` is a credential whatever its shape. No tool here builds such a key —
        # the result vocabulary is this server's own — but the boundary must not depend on that.
        return {k: ("<KEY>" if isinstance(v, str) and _SECRET_KEY_RE.fullmatch(str(k))
                    else redact_shapes(v))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_shapes(v) for v in obj]
    return obj


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """One cookie jar, two openers. get() never raises and never leaks the key — with ONE exception,
    and it is deliberate: a REPLAYING client (litkb.cassette, S4.5 item 7) raises `CassetteMiss` for a
    request its cassette cannot answer, because the alternative is a replay that quietly falls through
    to the network or quietly answers "status 0" for a request the live run never made."""

    def __init__(self, base=BASE, ua=UA, flaresolverr=None, cassette=None):
        self.base = base
        self.ua = ua
        self.flaresolverr = (flaresolverr if flaresolverr is not None
                             else os.environ.get("FLARESOLVERR_URL", "")).rstrip("/")
        self.cj = http.cookiejar.CookieJar()
        cp = urllib.request.HTTPCookieProcessor(self.cj)
        self._follow = urllib.request.build_opener(cp)
        self._nofollow = urllib.request.build_opener(cp, _NoRedirect())
        #: An explicitly injected cassette (tests). None means "whatever litkb.cassette.active()
        #: says at request time" — the environment, so an MCP hunt's child process records and
        #: replays like the parent (survey-code §1.4, bypass 4).
        self.cassette = cassette

    # -- bot-challenge handling (optional; without FlareSolverr the login cookie stands) --

    @staticmethod
    def is_challenge(status, url, body):
        """A bot challenge at ANY status (S4.5 item 2; the 2026-09-22 Sci-Hub diagnosis D1 measured
        `sci-hub.wf` answering its Cloudflare "Checking your browser" page at HTTP 200, which the old
        403/503-only rule booked as a miss). At 403/503 the whole body is searched, as before. At any
        other status only the page TITLE is: PDF-sources survey G0d (VERIFIED) — "never detect the
        challenge by searching the body for 'ddos-guard': a solved record page mentions it in its own
        scripts" — and a PDF is never a challenge. The title is read in the first 64 KiB (guard 3's
        "first-64 KB markers")."""
        body = body or b""
        if status == 403 and "check=1" in (url or ""):
            return True
        if status in (403, 503):
            return bool(CHALLENGE_RE.search(body))
        # BEGIN guard: a challenge page is a challenge at ANY status
        head = body[:64 * 1024]
        if head.lstrip()[:5] == b"%PDF-":
            return False
        title = re.search(rb"<title[^>]*>(.*?)</title", head, re.I | re.S)
        return bool(title and CHALLENGE_RE.search(title.group(1)))
        # END guard: a challenge page is a challenge at ANY status

    def _flare_post(self, payload):
        """POST to FlareSolverr /v1. Split out so tests can stub it."""
        req = urllib.request.Request(
            self.flaresolverr + "/v1", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def solve_challenge(self, url):
        """Adopt FlareSolverr's cookies + UA into this session. -> True if adopted."""
        if not self.flaresolverr:
            return False
        try:
            j = self._flare_post({"cmd": "request.get", "url": url, "maxTimeout": 60000})
        except Exception:
            return False
        sol = (j or {}).get("solution") or {}
        cookies = sol.get("cookies") or []
        for ck in cookies:
            try:
                self.cj.set_cookie(http.cookiejar.Cookie(
                    version=0, name=ck["name"], value=ck["value"], port=None, port_specified=False,
                    domain=ck.get("domain") or urllib.parse.urlparse(url).netloc,
                    domain_specified=True, domain_initial_dot=str(ck.get("domain", "")).startswith("."),
                    path=ck.get("path") or "/", path_specified=True,
                    secure=bool(ck.get("secure")), expires=None, discard=False,
                    comment=None, comment_url=None, rest={}))
            except Exception:
                continue
        if sol.get("userAgent"):
            self.ua = sol["userAgent"]
        return bool(cookies or sol.get("userAgent"))

    def _raw_get(self, url, accept, timeout, follow, data, headers=None):
        h = {"User-Agent": self.ua, "Accept": accept}
        if headers:
            h.update(headers)
        if data is not None:
            # BEGIN guard: a caller-supplied Content-Type survives a body
            h.setdefault("Content-Type", "application/x-www-form-urlencoded")
            # END guard: a caller-supplied Content-Type survives a body
            # `setdefault`, not `=`: the annas routes post urlencoded forms and still get that
            # default, but the Semantic Scholar batch endpoint posts JSON and must keep its own
            # header. Assigning here clobbered the header the caller had just passed in `headers`,
            # and the server answered 415 with no hint that the client had overwritten it.
        # THE CASSETTE HOOK (litkb.cassette; S4.5 item 7). This function is litkb's one socket path,
        # so recording here records every Client request and replaying here stops every one of them
        # before an opener is touched. `getattr`: a subclass that never ran Client.__init__ has no
        # attribute, and must behave as a client with no cassette injected.
        from litkb import cassette as _cassette

        cas = getattr(self, "cassette", None) or _cassette.active()
        # BEGIN guard: a replaying client answers from its cassette and never opens a socket
        if cas is not None and cas.mode == "replay":
            return cas.replay(self, url, h, follow, data)
        # END guard: a replaying client answers from its cassette and never opens a socket
        before = cas.cookie_names(self.cj) if cas is not None else None
        req = urllib.request.Request(url, data=data, headers=h)
        op = self._follow if follow else self._nofollow
        try:
            with op.open(req, timeout=timeout) as r:
                res = r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:          # includes the suppressed 3xx
            try:
                body = e.read()
            except Exception:
                body = b""
            res = e.code, dict(e.headers or {}), body
        except Exception as e:                        # URLError, timeout, ssl, ...
            res = 0, {}, redact(f"{type(e).__name__}: {e}").encode()
        if cas is not None and cas.mode == "record":
            cas.record(self, url, h, follow, data, res, cookies_before=before)
        return res

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        if headers:
            st, hd, body = self._raw_get(url, accept, timeout, follow, data, headers)
        else:
            st, hd, body = self._raw_get(url, accept, timeout, follow, data)
        if self.flaresolverr and self.is_challenge(st, url, body) and self.solve_challenge(url):
            again = None
            # BEGIN guard: the challenge retry keeps the caller's headers
            # (S4.5 builder-C2b, survey-code §1.1: the retry used to drop them, so a Stage C request's Referer and
            # Range - guard 24, the C13 probe - were lost on exactly the request a solved challenge let through)
            again = headers
            # END guard: the challenge retry keeps the caller's headers
            if again:
                st, hd, body = self._raw_get(url, accept, timeout, follow, data, again)
            else:
                st, hd, body = self._raw_get(url, accept, timeout, follow, data)
        return st, hd, body

    def login(self, key):
        st, _, _ = self.get(self.base + "/account/", accept="text/html",
                            data=urllib.parse.urlencode({"key": key}).encode())
        return any(c.name == "aa_account_id2" for c in self.cj), st


class Pacer:
    def __init__(self, interval=SCIDB_MIN_INTERVAL, sleep=time.sleep, backoff=RATE_BACKOFF,
                 clock=time.monotonic):
        self.interval, self.sleep, self.last = interval, sleep, 0.0
        self.backoff_s, self.clock = backoff, clock

    def wait(self):
        gap = self.interval - (self.clock() - self.last)
        if self.last and gap > 0:
            self.sleep(gap)
        self.last = self.clock()

    def backoff(self, seconds=None):
        self.sleep(self.backoff_s if seconds is None else seconds)
        self.last = self.clock()

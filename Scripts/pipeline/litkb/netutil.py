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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """One cookie jar, two openers. get() never raises and never leaks the key."""

    def __init__(self, base=BASE, ua=UA, flaresolverr=None):
        self.base = base
        self.ua = ua
        self.flaresolverr = (flaresolverr if flaresolverr is not None
                             else os.environ.get("FLARESOLVERR_URL", "")).rstrip("/")
        self.cj = http.cookiejar.CookieJar()
        cp = urllib.request.HTTPCookieProcessor(self.cj)
        self._follow = urllib.request.build_opener(cp)
        self._nofollow = urllib.request.build_opener(cp, _NoRedirect())

    # -- bot-challenge handling (optional; without FlareSolverr the login cookie stands) --

    @staticmethod
    def is_challenge(status, url, body):
        return bool((status == 403 and "check=1" in (url or ""))
                    or (status in (403, 503) and CHALLENGE_RE.search(body or b"")))

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
        req = urllib.request.Request(url, data=data, headers=h)
        op = self._follow if follow else self._nofollow
        try:
            with op.open(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:          # includes the suppressed 3xx
            try:
                body = e.read()
            except Exception:
                body = b""
            return e.code, dict(e.headers or {}), body
        except Exception as e:                        # URLError, timeout, ssl, ...
            return 0, {}, redact(f"{type(e).__name__}: {e}").encode()

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        if headers:
            st, hd, body = self._raw_get(url, accept, timeout, follow, data, headers)
        else:
            st, hd, body = self._raw_get(url, accept, timeout, follow, data)
        if self.flaresolverr and self.is_challenge(st, url, body) and self.solve_challenge(url):
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

"""HTTP client, pacer and secret redaction shared by the registry resolver and the acquisition routes.

Ported from D:\\tools\\annas-mcp\\aa_fetch.py (2026-09-13, its verified gates; design §10). Stdlib only, so
`import litkb` stays light. The client never raises and never leaks a registered secret: every string it
returns for an error, and every log line built from it, goes through redact().
"""
import contextvars
import html as _html
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

# ── THE challenge signatures: one home (S4.5 decision D24; moved here from litkb.acquire.ledger by
# integrator-w3 — the ledger, the landing rung and the acceptance test read them through
# Client.challenge_cause, never a list of their own) ─────────────────────────────────────────────
#: How far into a served body the markers are looked for: guard 3 (PDF-sources survey §1) reads
#: "first-64 KB markers". The challenge TITLE is read in the same window.
MARKER_WINDOW = 64 * 1024
#: (cause, marker) pairs, lower-cased, searched in the first MARKER_WINDOW bytes. Sources: guard 3 and
#: its C6-RG extension (`just a moment`, `attention required`, `recaptcha`, `_fs-ch-`, `client
#: challenge`, `validate.perfdrive.com`, `_incapsula_resource`, `px-captcha`); CHALLENGE_RE's three;
#: and the page shapes survey-data §2.5 MEASURED in litkb's own kept bytes (Cloudflare
#: `challenge-platform` / `cf_chl_`, ScienceDirect's `CLOUDFLARE_ERROR` box, Akamai's `Access Denied`
#: on `errors.edgesuite.net`, Sci-Hub's `<title>Verification` / captcha page).
CHALLENGE_MARKERS = (
    ("cloudflare", b"just a moment"), ("cloudflare", b"checking your browser"),
    ("cloudflare", b"challenge-platform"), ("cloudflare", b"cf_chl_"), ("cloudflare", b"cf-mitigated"),
    ("cloudflare", b"attention required"), ("cloudflare", b"cloudflare_error"),
    ("ddos-guard", b"ddos-guard"),
    # Akamai's error host; its own pages write it HTML-entity-encoded (`errors&#46;edgesuite&#46;net`, the
    # four MDPI pages kept on the live store), so the marker is the bare name
    ("akamai", b"edgesuite"),
    ("captcha", b"recaptcha"), ("captcha", b"captcha"), ("captcha", b"<title>verification"),
    ("incapsula", b"_incapsula_resource"), ("perimeterx", b"px-captcha"),
    ("perfdrive", b"validate.perfdrive.com"), ("f5", b"_fs-ch-"), ("generic", b"client challenge"),
)
#: guard 3: response headers that ARE the challenge signature. `x-amzn-waf-action: challenge` added by builder-FX-V
#: (S4.5 fix wave; referee-vocabulary class A2): AWS WAF's challenge answers with an EMPTY 202 whose only signature is
#: this header — MEASURED: every one of the 15 202s the ladder-1 run recorded carries it and `Server: CloudFront`
#: (ieeexplore.ieee.org 7 with a 2,055 B script page, doi.org 3 for IEEE DOIs, journals.ametsoc.org 4 — 3 empty, 1 with
#: a 2,228 B script page — and infoscience.epfl.ch 1: 7 of the 15 with an empty body, 8 with a ~2 KB script page;
#: re-measured by builder-FX-V round 2, auditor-FX-V F7), which open access and Stage B booked `bad-file/html_response`
#: or `api-error` while the landing rung's own `waf_statuses` rule called them challenges.
CHALLENGE_HEADERS = (("cf-mitigated", "challenge"), ("x-datadome", "protected"), ("x-amzn-waf-action", "challenge"))
#: The statuses at which the whole refusal page is read for a signature (the pre-S4.5 rule's two). At any
#: other status only the page TITLE is read — survey G0d (VERIFIED): "never detect the challenge by
#: searching the body for 'ddos-guard': a solved record page mentions it in its own scripts".
REFUSAL_STATUSES = (403, 503)
#: Block-page TOKENS read in the WHOLE of a refusal page (REFUSAL_STATUSES, or a kept page of status None;
#: REFUSAL_WINDOW) — a token only a server's own error / block page template prints, never a script a solved page
#: also carries. Builder-FX-V
#: (S4.5 fix wave; referee-vocabulary class B, whose M2 showed nothing held the window): ScienceDirect's Cloudflare
#: block page is 832,805 bytes — the largest 403/503 body of the ladder-1 run, 114 answers, MEASURED over the cassette
#: — and its `::CLOUDFLARE_ERROR_1000S_BOX::` sits at byte 773,838, past guard 3's first MARKER_WINDOW bytes, so the
#: Stage B rungs typed it `identity_required` while the landing rung, which read its own rule's signature over the whole
#: body, typed the same page a challenge. WHY NOT every marker over the whole page (MEASURED, builder-FX-V, the same
#: census): Wiley's two 227 KB 403 answers of the ladder-1 run are the ARTICLE's own page (its title, "institution",
#: "log in") with Cloudflare's injected `/cdn-cgi/challenge-platform/scripts/precursor/main.js` at byte ~226,960 and a
#: login form's `captcha` at ~214,130 — a whole-page read of CHALLENGE_MARKERS calls them challenges, the 64 KB read
#: rightly does not. So the CHALLENGE_MARKERS keep guard 3's window and only these tokens are read whole.
REFUSAL_PAGE_MARKERS = (("cloudflare", b"cloudflare_error"),)
#: How much of a refusal page REFUSAL_PAGE_MARKERS are read in: all of it (None = no bound — the page the client already
#: holds, the reach CHALLENGE_RE has always had at these statuses).
REFUSAL_WINDOW = None
#: Challenge-page TITLES that name the check in WORDS (never a vendor script or resource name — survey G0d's reason
#: for reading only the title at a non-refusal status stands), matched against the title's text with its HTML
#: entities decoded, at ANY status. Builder-FX-V (S4.5 fix wave; referee-vocabulary classes A1 and A4), each MEASURED
#: on a page the ladder-1 run recorded (qc/fixtures/litkb_cassettes/typing_fx_v/provenance.json names the rows):
CHALLENGE_TITLES = (
    # Anubis's proof-of-work page, served at HTTP 200: 16 recorded answers — hal.science, inria.hal.science and
    # hal.inrae.fr (11; the referee's 8 mistyped attempts, 5 works), mediatum.ub.tum.de, www.ssoar.info,
    # macau.uni-kiel.de, www.zora.uzh.ch and one behind hdl.handle.net: `<title>Making sure you&#39;re not a bot!</title>`
    ("anubis", "making sure you're not a bot"),
    # a reCAPTCHA gate served at HTTP 404 behind hdl.handle.net/10810/59883: `<title>Verificación de seguridad` (its
    # body is a form holding only a `g-recaptcha` widget)
    ("captcha", "verificación de seguridad"),
)
#: A vendor BLOCK page's own sentence — words only the block page prints, never a script or resource name (a solved
#: page names its guard in its SCRIPTS, survey G0d; nothing here is one) — read in the first MARKER_WINDOW bytes with
#: HTML entities decoded, at ANY status. Builder-FX-V (referee-vocabulary class A3), MEASURED: Imperva Incapsula's
#: block page, served at HTTP 200 by projecteuclid.org, has no title at all; its one sentence is "Request
#: unsuccessful. Incapsula incident ID: <id>". (Its `/_Incapsula_Resource` script, which a SOLVED Incapsula page also
#: carries, stays a marker read only on a refusal page or in a title.)
CHALLENGE_BLOCK_TEXT = (("incapsula", "incapsula incident id"),)
#: S4.5 fix wave (brief FX-V item 4): a 429 whose page STATES a rate limit is that rate limit — the host cool-down's
#: business (S4.5 decision D45), never a bot challenge, whatever its title says; a challenge page served at 429 that
#: states no rate limit stays a challenge (auditor-fix7 AM1). Read in the first MARKER_WINDOW bytes, lower-cased.
#: MEASURED on bioRxiv's recorded 429 (ladder-1; Cloudflare-branded, titled "Attention Required | Cloudflare", which
#: the marker list calls a challenge): "We have received a high number of requests from this session" and the page's
#: own name for itself, "Cloudflare rate limit screen"; plus 429's reason phrase in RFC 6585 section 4.
RATE_LIMIT_TEXT = (b"high number of requests", b"rate limit", b"too many requests")
_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title", re.I | re.S)


def _decoded(raw):
    """HTML text as a reader sees it: entities decoded, lower-cased, whitespace runs folded, the typographic apostrophe
    folded to ASCII (builder-FX-V's choice: the same title in either spelling is one title)."""
    text = _html.unescape((raw or b"").decode("utf-8", "replace")).lower().replace("\u2019", "'")
    return " ".join(text.split())


def challenge_words(head):
    """-> the challenge family whose page WORDS (CHALLENGE_TITLES in the title, CHALLENGE_BLOCK_TEXT in the window)
    these bytes carry, or ''. Read at any status by `Client.challenge_cause`."""
    title = _TITLE_RE.search(head or b"")
    if title:
        text = _decoded(title.group(1))
        for cause, words in CHALLENGE_TITLES:
            if words in text:
                return cause
    text = _decoded(head)
    for cause, words in CHALLENGE_BLOCK_TEXT:
        if words in text:
            return cause
    return ""


def states_rate_limit(head):
    """Does this page (its first MARKER_WINDOW bytes) state a rate limit (RATE_LIMIT_TEXT)?"""
    low = (head or b"").lower()
    return any(t in low for t in RATE_LIMIT_TEXT)

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


#: S4.5 decision D44 (builder-fix7): the acquisition ladder's REQUEST GATE for the rung call in progress
#: (`litkb.acquire.backoff.Gate`, set by `litkb.acquire.run._call_rung` around ONE rung call, in that call's own
#: thread/context). `Client.get` asks it before every request — a host cooling down in this run is never asked —
#: and tells it every answer, so the ladder knows WHICH host answered a 429 / 503. None (every caller outside a
#: ladder rung) changes nothing.
REQUEST_GATE = contextvars.ContextVar("litkb_request_gate", default=None)


class HostCooling(Exception):
    """S4.5 decision D44: the request gate refused a request to a host that is cooling down in this run (it answered
    429 / 503, or a wait no row sits out). Raised BEFORE any byte is sent; `facts` are what the ledger records."""

    def __init__(self, host, url, facts):
        super().__init__(f"{host} is cooling down in this run until {(facts or {}).get('cool_until')}")
        self.host, self.url, self.facts = host, url, dict(facts or {})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _GatedRedirect(urllib.request.HTTPRedirectHandler):
    """S4.5 decision D44, auditor-fix7 F1: a redirect the client FOLLOWS (`follow=True`) is a request to another host,
    and the ladder's request gate (`REQUEST_GATE`) is asked about EVERY hop: the hop's own answer is credited to the
    host that gave it (a 3xx, which never cools a host), and a hop to a host cooling down in this run is NOT followed —
    the 3xx comes back as the answer and the refusal is on the gate (raising here would be swallowed by `_raw_get`'s
    transport catch as a status 0). Outside a ladder rung call (no gate) it follows exactly as urllib's own handler."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        gate = REQUEST_GATE.get()
        follow = True             # the unguarded default: every hop is followed, whoever it goes to
        # BEGIN guard: every hop of a followed redirect is asked of the request gate
        if gate is not None:
            follow = gate.hop(req.full_url, code, dict(headers or {}), newurl)
        # END guard: every hop of a followed redirect is asked of the request gate
        if not follow:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
        self._follow = urllib.request.build_opener(cp, _GatedRedirect())      # D44 / auditor-fix7 F1: every hop gated
        self._nofollow = urllib.request.build_opener(cp, _NoRedirect())
        #: An explicitly injected cassette (tests). None means "whatever litkb.cassette.active()
        #: says at request time" — the environment, so an MCP hunt's child process records and
        #: replays like the parent (survey-code §1.4, bypass 4).
        self.cassette = cassette

    # -- bot-challenge handling (optional; without FlareSolverr the login cookie stands) --

    @staticmethod
    def challenge_cause(status, url, body, headers=None):
        """-> the challenge family these bytes / headers / URL carry, or ''. THE one challenge detector
        (S4.5 decision D24: the ledger's typing, the open-access and Sci-Hub routes, the landing rung and
        the acceptance test all call it — integrator-w3 folded the ledger's marker list in here, so a page
        one of them calls a challenge the others do too). Evidence, strongest first:

          a header signature (CHALLENGE_HEADERS), at any status             -> header:<name>
          a 429 whose page states a rate limit (RATE_LIMIT_TEXT)            -> '' (the rate limit, never a
            challenge: the host cool-down's business, S4.5 decision D45 — builder-FX-V). AFTER the header
            signatures (builder-FX-V round 2, auditor-FX-V F5): a 429 that carries a challenge header is a
            challenge whatever its page says, so it never starts a cool-down (S4.5 decision D46 F2)
          a 403 on a `check=1` URL (Sci-Hub's challenge redirect)            -> check=1
          PDF magic at the head of the body                                  -> '' (a PDF is never a challenge)
          status 403 / 503 (REFUSAL_STATUSES): a CHALLENGE_MARKERS marker in the first MARKER_WINDOW bytes,
            a REFUSAL_PAGE_MARKERS block-page token anywhere in the page (REFUSAL_WINDOW; builder-FX-V:
            ScienceDirect's 832 KB block page), the page's challenge WORDS (`challenge_words`), or
            CHALLENGE_RE anywhere in the page (the pre-S4.5 rule)            -> the family / `challenge-re`
          status None — a KEPT payload whose answer's status the caller does not hold (the ledger's typing
            of a row already booked, litkb.acquire.ledger.challenge_cause): the markers in the window, a
            block-page token anywhere in it (builder-FX-V), then the page's challenge words
          any other status — a bot challenge at ANY status (S4.5 item 2; the 2026-09-22 Sci-Hub diagnosis
            D1 measured `sci-hub.wf` answering its Cloudflare "Checking your browser" page at HTTP 200):
            the page TITLE only, matched against the markers and CHALLENGE_RE (survey G0d, REFUSAL_STATUSES:
            a solved page names its guard in its own scripts, never in its title); then the page's challenge
            WORDS — a title naming the check (CHALLENGE_TITLES: Anubis at 200, a reCAPTCHA gate at 404) or a
            vendor block page's own sentence (CHALLENGE_BLOCK_TEXT: Incapsula at 200) — builder-FX-V

        MDPI's Akamai "Access Denied" page is served at 403 (qc/fixtures/litkb_mdpi_pdf_akamai_a3b93f589df6.html):
        its `edgesuite` marker makes it a challenge here. The pre-D24 `is_challenge` read CHALLENGE_RE only,
        so the open-access route booked that page `bad-file/html_response` (auditor-C2b F12)."""
        body = body or b""
        head = body[:MARKER_WINDOW]
        for k, v in (headers or {}).items():
            for hk, hv in CHALLENGE_HEADERS:
                if str(k).lower() == hk and hv in str(v).lower():
                    return f"header:{hk}"
        # BEGIN guard: a 429 whose page states a rate limit is the rate limit, never a challenge
        # (after the header signatures: a challenge header outranks the page's words — auditor-FX-V F5; bioRxiv's
        # recorded 429 carries no challenge header, so its answer is unchanged by the order)
        if status == 429 and states_rate_limit(head):
            return ""
        # END guard: a 429 whose page states a rate limit is the rate limit, never a challenge
        if status == 403 and "check=1" in (url or ""):
            return "check=1"
        if head.lstrip()[:5] == b"%PDF-":
            return ""
        if status is None or status in REFUSAL_STATUSES:
            low = head.lower()
            # BEGIN guard: a refusal page is read for every challenge marker, not only CHALLENGE_RE's three
            for cause, marker in CHALLENGE_MARKERS:
                if marker in low:
                    return cause
            # END guard: a refusal page is read for every challenge marker, not only CHALLENGE_RE's three
            # (a KEPT payload, status None, too: this branch already reads it as a refusal page, and the ledger's typing
            # of a kept ScienceDirect page then agrees with the rung that was served it — D24's one detector)
            # BEGIN guard: a refusal page is read whole for a block-page token, never only its first MARKER_WINDOW bytes
            whole = body[:REFUSAL_WINDOW].lower()
            for cause, marker in REFUSAL_PAGE_MARKERS:
                if marker in whole:
                    return cause
            # END guard: a refusal page is read whole for a block-page token, never only its first MARKER_WINDOW bytes
            words = challenge_words(head)
            if words:
                return words
            if status is not None and CHALLENGE_RE.search(body):
                return "challenge-re"
            return ""
        # BEGIN guard: a challenge page is a challenge at ANY status
        # the TITLE decides whether; the window then names which family (Springer's "Client Challenge" page is
        # F5's: its `_fs-ch-` script sits in the body, the generic words in the title)
        title = re.search(rb"<title[^>]*>(.*?)</title", head, re.I | re.S)
        if title and (any(marker in title.group(0).lower() for _c, marker in CHALLENGE_MARKERS)
                      or CHALLENGE_RE.search(title.group(1))):
            low = head.lower()
            return next((cause for cause, marker in CHALLENGE_MARKERS if marker in low), "challenge-re")
        # END guard: a challenge page is a challenge at ANY status
        # BEGIN guard: a page whose own words name the check is a challenge at ANY status
        # (builder-FX-V: Anubis's title at 200, a reCAPTCHA gate's title at 404, Incapsula's untitled block page at 200
        # — each read as `bad-file/html_response` by the title-marker rule above, which knows script names only)
        words = challenge_words(head)
        if words:
            return words
        # END guard: a page whose own words name the check is a challenge at ANY status
        return ""

    @staticmethod
    def is_challenge(status, url, body, headers=None):
        """Is this answer a bot challenge? `Client.challenge_cause`'s yes / no (D24: one detector)."""
        return bool(Client.challenge_cause(status, url, body, headers))

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
        gate = None
        # BEGIN guard: a request to a host cooling down in this run is never sent
        # (S4.5 decision D44, builder-fix7: the ladder's request gate, `REQUEST_GATE`; raises `HostCooling` before any
        # byte leaves, which the ladder's route boundary records as the host's cool-down — never a request)
        gate = REQUEST_GATE.get()
        if gate is not None:
            gate.before(url)
        # END guard: a request to a host cooling down in this run is never sent
        if headers:
            st, hd, body = self._raw_get(url, accept, timeout, follow, data, headers)
        else:
            st, hd, body = self._raw_get(url, accept, timeout, follow, data)
        if self.flaresolverr and self.is_challenge(st, url, body, hd) and self.solve_challenge(url):
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
        if gate is not None:
            # D44: the gate learns which host answered what — the host at the END of a followed redirect chain
            # (`Gate.after` reads the chain `Gate.hop` recorded), never the host that was only asked (auditor-fix7 F1)
            gate.after(url, st, hd, body)
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

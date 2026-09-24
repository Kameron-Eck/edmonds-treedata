"""Per-route back-off for the acquisition ladder (LITKB_WORKPLAN.md "### S4.5" item 1; migration 0033's
`route_backoff`). A RELAYED design (CLAUDE.md §3.4c) — PDF-sources survey §1 guards 2, 11, 13, 15, 29 —
UNVALIDATED until an independent referee scores it on E13 and the ruled run's rows.

Two mechanisms, both keyed on the ATTEMPT's facts (route, status, http codes, at) and never on the
hunt's state word:

  1. the REFUSAL LADDER, per (route, work), PERSISTED in `litkb.route_backoff` (guard 2): a refusal
     opens a window — 15 min, then 6 h, then 48 h for the next refusals inside a 7-day window — and an
     attempt on that route for that work inside the window is SKIPPED (`skipped/backoff_window`), so a
     second hunt does not re-spend. Per WORK, never per host: one 403 must not retire a host (guard 29 —
     MDPI answers 403 per article and is the corpus's largest slice).
  2. AIMD PACING, per route, IN THE RUN (guards 2 and 11, W25): a transient answer (429, 503, a
     transport failure) multiplies the route's delay, every 2xx decays it linearly; a transient answer
     gets ONE scheduled in-run retry after that delay (or after Retry-After), recorded with `retry_of`
     so it is never mistaken for a re-spend. Not persisted: guard 3 records that a challenge state
     "waiting longer cannot turn this client into a browser" and is kept in-run; the delay is a pacing
     state for this process.
  3. THE IN-RUN COOL-DOWN, per HOST, shared by every route (S4.5 decisions D41, D44, D45; builder-fix7): a
     HOST that answered "slow down" (`COOLDOWN_CODES`: 429, 503 — never 403, guard 29; never a bot challenge,
     guard 3) COOLS for the rest of its wait: no later request of ANY route in the run is sent to that host
     until `cool_until` (the request `Gate`, which `netutil.Client.get` consults), while every other host is
     asked as before. A rung whose request to a cooling host cannot be skipped is recorded
     `skipped/backoff_window` (`detail.cooldown` naming the host and the trigger) when it had asked nothing yet —
     for a single-host rung the whole rung, as D41 had it. And NO ROW SITS OUT A LONG WAIT: a scheduled retry,
     or a pacing wait, longer than `IN_ROW_WAIT_MAX_S` is not waited for — the host cools instead. The state
     lives in the run's `HostCooldowns`, kept in the ladder's pacing state under `HOSTS_KEY` (`run.PACING` in
     a live process: it survives across works in one process and a new process starts cold). Measured cause
     (the live ladder-1 run, 2026-09-24, read back as litkb_reader from the ledger and the RECORD-mode
     cassette): after ~45 rows archive.org answered 429 (9 times; none carried Retry-After), the AIMD
     delay doubled to its 300 s ceiling, and each later wayback ask first slept that delay (`run._pace`)
     and then again before its retry, until the row hit the 505 s ladder budget (~10 min a row).

EVERY CONSTANT BELOW IS UNCALIBRATED on litkb's ledger, and the reason is MEASURED (builder-C1a report,
scratch calib.py over the live ledger as litkb_reader, 2026-09-23, 278 attempts):
  * the refusal ladder: 7 (route, work) pairs show a refusal followed by a later attempt, at gaps of
    362 s .. 4.2 days, and ALL 7 were refused again — no recovery was ever observed, so the ladder's
    step lengths are unobservable here (the history says only that re-asking inside 4.2 days changed
    nothing 7 times out of 7);
  * AIMD: the ledger holds no 429 and no 503 at all (codes seen: 0 x1, 200 x136, 202 x2, 403 x47,
    404 x1, 500 x1, 522 x1), so the multiplier, decay and ceiling have nothing to be fitted to.
They are the survey's STARTING values, each with its source.
"""
import datetime
import email.utils
import urllib.parse
from dataclasses import dataclass, field

#: guard 2 (round 1, `http_client.py`-shaped ladders): 15 min -> 6 h -> 48 h. UNCALIBRATED (see above).
REFUSAL_LADDER_S = (15 * 60, 6 * 3600, 48 * 3600)
#: guard 2: "over a 7-day window". UNCALIBRATED.
REFUSAL_WINDOW_S = 7 * 24 * 3600
#: guard 2 RE-GRADE (W25, pypaperretriever http_client.py@04607e9): backoff_decay_s=1.0,
#: backoff_multiplier=2.0, backoff_max_s=300. UNCALIBRATED (no 429/503 in the ledger).
AIMD_DECAY_S = 1.0
AIMD_MULTIPLIER = 2.0
AIMD_CEILING_S = 300.0

#: guard 2: the refusal ladder is triggered on {202, 403, 429, 503}; 401 is deliberately excluded there
#: ("a subscription answer about one article") — but since THIS ladder is per work, not per host, a
#: `blocked` row (whatever its codes) is also a refusal of that work on that route.
REFUSAL_CODES = frozenset({202, 403, 429, 503})
#: guard 13 declares {429, 502, 503, 504} retryable as data; litkb's own registry rule
#: (admit/registry.py::is_transient) adds 0 (the client's transport failure), 408 and every 5xx.
#: 401/403/404 are NEVER retried in-run (guard 2).
TRANSIENT_CODES = frozenset({0, 408, 429})
#: the attempt statuses that are a success for pacing and for the refusal ladder
SUCCESS_STATUSES = frozenset({"ok", "measured", "duplicate-held"})
#: rows that spent nothing: they never move the ladder and are never a re-spend
#: (`quota-stop` asks the archive for nothing: the run cap or the account counter stopped it first)
NON_SPEND_STATUSES = frozenset({"skipped", "budget-stop", "manual-step", "quota-stop"})
#: routes whose rows are not network rungs (an operator's file, an event, a ladder row)
NON_RUNG_ROUTES = frozenset({"browser", "hunt-url", "ladder"})
#: S4.5 decisions D41/D44: the HTTP codes with which a HOST's answer cools that host for the rest of the run — the
#: two "slow down" answers (429 Too Many Requests, RFC 6585 §4; 503 Service Unavailable, RFC 9110 §15.6.4), the
#: ones a server's Retry-After says when to come back after (RFC 9110 §10.2.3). NEVER 403 (guard 29: one refusal
#: must not retire a host — MDPI answers 403 per article); a 403 climbs the per-(route, work) refusal ladder only.
COOLDOWN_CODES = frozenset({429, 503})
#: S4.5 decision D41: the longest wait a row SITS OUT inside itself (the scheduled retry's wait; the pacing wait
#: before a route is asked). Source: litkb's own one-retry convention, `admit/resolver.py::registry_get` ("one 10 s
#: back-off on 429, then give up"), the first of the conventions `policy.IN_RUN_RETRIES` cites; cross-checked on
#: the live run: 505 s ladder budget / 48 attempts (`detail.ladder.budget` of the ladder-1 rows) = 10.5 s, one
#: attempt's share. UNCALIBRATED. A longer wait is never sat out: the route COOLS instead (the cool-down is capped
#: at `AIMD_CEILING_S`, the cap the scheduled retry has always put on a Retry-After).
IN_ROW_WAIT_MAX_S = 10.0


def is_transient_code(code):
    """One HTTP code (0 = the client's transport failure) -> is it TRANSIENT (TRANSIENT_CODES or 5xx)?
    The ONE home of transience: `classify` reads it, so the in-run retry, `retriable` and AIMD pacing do
    (open access's failed Unpaywall lookup carries its code for exactly this reading). The ladder's no-byte
    rule reads status 0 alone, not transience (S4.5 decision D15; fix round 3)."""
    try:
        c = int(code)
    except (TypeError, ValueError):
        return False
    return c in TRANSIENT_CODES or 500 <= c <= 599


def _ints(codes):
    return [int(c) for c in (codes or []) if str(c).lstrip("-").isdigit()]


def classify(status, codes):
    """-> "success" | "transient" | "refusal" | "neutral" for one attempt's (status, http codes), for
    PACING and the in-run retry. The TERMINAL code (the last one) decides transience."""
    codes = _ints(codes)
    if status in SUCCESS_STATUSES:
        return "success"
    # BEGIN guard: a challenge is never transient, whatever its status code
    # (guard 3: "waiting longer cannot turn this client into a browser". Cloudflare serves its challenge at
    # 403 OR 503, and `netutil.Client.is_challenge` books both `blocked`; read by its code alone, a 503
    # challenge was `transient` — retried in the run and, once the dead check reads `retriable` (guard 15),
    # never dead within the run. fix round 2, auditor-C1a F1.)
    if status == "blocked":
        return "refusal"
    # END guard: a challenge is never transient, whatever its status code
    # an `api-error` a route RETURNED (the archive answering "invalid key") is not transient by itself:
    # only its codes can make it so; a route that RAISED is judged by its exception (`retriable`)
    if codes and is_transient_code(codes[-1]):
        return "transient"
    if is_refusal(status, codes):
        return "refusal"
    return "neutral"


def is_refusal(status, codes):
    """For the REFUSAL LADDER: a `blocked` row, or any code in REFUSAL_CODES. A 429 or 503 is a refusal
    here even though it is transient for pacing: the chain's FINAL row is what moves the ladder (an
    original with an in-run retry is superseded by the retry), so a 429 that survived its retry climbs
    the ladder exactly as guard 2 triggers it."""
    return status == "blocked" or any(c in REFUSAL_CODES for c in _ints(codes))


def retriable(status, codes, exception=None):
    """The per-attempt `retriable` fact (guard 15): would asking again soon plausibly change the
    answer? A transient HTTP answer, or a route that raised an OSError (a socket reset, a timeout —
    the transport, not a parser that met a shape it did not expect). A refusal and a miss are not."""
    if exception is not None:
        return isinstance(exception, OSError)
    if status in NON_SPEND_STATUSES:
        return None
    return classify(status, codes) == "transient"


def retry_after_s(headers, now=None):
    """Retry-After (delta-seconds or an HTTP date) -> seconds, or None (guard 2: honour Retry-After)."""
    if not headers:
        return None
    raw = next((v for k, v in headers.items() if str(k).lower() == "retry-after"), None)
    if raw is None:
        return None
    raw = str(raw).strip()
    if raw.isdigit():
        return float(raw)
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return max(0.0, (when - now).total_seconds())


@dataclass
class BackoffPolicy:
    """The constants as ONE object, so a run can carry its own (and a known-bad can set the window to
    zero without touching the reference the counters replay the ledger with)."""
    refusal_ladder_s: tuple = REFUSAL_LADDER_S
    refusal_window_s: float = REFUSAL_WINDOW_S
    aimd_decay_s: float = AIMD_DECAY_S
    aimd_multiplier: float = AIMD_MULTIPLIER
    aimd_ceiling_s: float = AIMD_CEILING_S
    in_row_wait_max_s: float = IN_ROW_WAIT_MAX_S

    def step(self, state, status, codes, at):
        """The refusal ladder's one rule. `state` = {"refusals", "window_started_at", "next_allowed_at"}
        (or None) BEFORE this attempt -> the state AFTER it. A success resets; a refusal inside the
        window climbs one rung (a refusal after the window has lapsed starts again at the first rung);
        anything else leaves the state as it was."""
        state = dict(state or {"refusals": 0, "window_started_at": None, "next_allowed_at": None})
        if status in SUCCESS_STATUSES:
            return {"refusals": 0, "window_started_at": None, "next_allowed_at": None}
        if not is_refusal(status, codes):
            return state
        started = state.get("window_started_at")
        if not state.get("refusals") or started is None or \
                (at - started).total_seconds() > self.refusal_window_s:
            refusals, started = 1, at
        else:
            refusals = state["refusals"] + 1
        wait = self.refusal_ladder_s[min(refusals, len(self.refusal_ladder_s)) - 1]
        return {"refusals": refusals, "window_started_at": started,
                "next_allowed_at": at + datetime.timedelta(seconds=wait)}

    def replay(self, rows):
        """State after replaying ledger rows [(id, status, http_codes, at, retry_of), ...] in `at`
        order: an original attempt whose retry follows it is superseded by the retry (one refusal
        event, not two); skip rows spend nothing and move nothing."""
        retried = {r[4] for r in rows if r[4] is not None}
        state = None
        for rid, status, codes, at, _retry_of in rows:
            if status in NON_SPEND_STATUSES or rid in retried:
                continue
            state = self.step(state, status, codes, at)
        return state


def host_of(url):
    """The host a request goes to (lower-cased, no port): the cool-down's key beside the route (D44)."""
    return (urllib.parse.urlsplit(url or "").hostname or "").lower()


def is_rate_limit(status_code, challenge=False):
    """S4.5 decisions D41/D44: does ONE answer from a host cool that host? Its code is a "slow down" answer
    (`COOLDOWN_CODES`: 429, 503 — never 403, guard 29) and its body is not a bot challenge."""
    # BEGIN guard: a challenge never cools a host
    # (guard 3: "waiting longer cannot turn this client into a browser". A bot challenge served at 503 is a refusal
    # of THIS client for THIS request — the row is booked `blocked`, dead for the route within the run — and says
    # nothing about the host's rate; D44 keys by host, and a challenge must not suppress the host for every work.)
    if challenge:
        return False
    # END guard: a challenge never cools a host
    try:
        return int(status_code) in COOLDOWN_CODES
    except (TypeError, ValueError):
        return False


def long_wait(status, codes, wait_s, policy=None):
    """S4.5 decision D41: is this a transient answer whose next wait (`wait_s`: the AIMD delay or Retry-After,
    capped at the AIMD ceiling) is longer than a row sits out (`IN_ROW_WAIT_MAX_S`)? Then the host that gave it
    cools instead of the row waiting. The TERMINAL code decides, as it does transience (`classify`; a `blocked`
    row is never transient)."""
    policy = policy or BackoffPolicy()
    return classify(status, codes) == "transient" and \
        min(wait_s or 0.0, policy.aimd_ceiling_s) > policy.in_row_wait_max_s


def cooldown_seconds(retry_after, aimd_delay, policy=None):
    """S4.5 decision D41: -> (seconds, source) a route cools for: the server's Retry-After when it sent one,
    capped at the AIMD ceiling (`AIMD_CEILING_S`, 300 s — the cap the scheduled retry has always put on a
    Retry-After), else the route's AIMD delay (already multiplied by the answer that cools it) and at least the
    AIMD's own first step (decay x multiplier = 2 s: a 429 inside a row that was not itself transient moved no
    delay). `source` is `retry-after`, `retry-after-capped` or `aimd`, recorded on every skip the cool-down writes."""
    policy = policy or BackoffPolicy()
    if retry_after is not None:
        # BEGIN guard: a Retry-After is honoured only up to the stated ceiling
        if retry_after > policy.aimd_ceiling_s:
            return float(policy.aimd_ceiling_s), "retry-after-capped"
        # END guard: a Retry-After is honoured only up to the stated ceiling
        return float(retry_after), "retry-after"
    return max(float(aimd_delay or 0.0), policy.aimd_decay_s * policy.aimd_multiplier), "aimd"


@dataclass
class Aimd:
    """In-run pacing for ONE route (guards 2 + 11): multiply on a transient refusal, decay linearly on
    every 2xx, never above the ceiling. `delay()` is how long to wait before the next request. (The in-run
    cool-downs are per HOST and shared by every route: `HostCooldowns`, S4.5 decision D45.)"""
    policy: BackoffPolicy = field(default_factory=BackoffPolicy)
    delay_s: float = 0.0

    def on_answer(self, status, codes):
        kind = classify(status, codes)
        if kind == "transient":
            self.delay_s = min(self.policy.aimd_ceiling_s,
                               max(self.delay_s, self.policy.aimd_decay_s) * self.policy.aimd_multiplier)
        elif kind == "success" or any(200 <= int(c) <= 299 for c in (codes or []) if str(c).isdigit()):
            self.delay_s = max(0.0, self.delay_s - self.policy.aimd_decay_s)
        return self.delay_s


#: The key under which the run's `HostCooldowns` sits in the ladder's `pacing` dict (beside the per-route `Aimd`s,
#: under a name no route can have): one table per run, so a host cooled by ONE route is cooled for EVERY route.
HOSTS_KEY = "*hosts"


@dataclass
class HostCooldowns:
    """The run's IN-RUN COOL-DOWNS, one per HOST, shared ACROSS routes (S4.5 decisions D41, D44, D45): a 429 / 503
    is the host telling this client to slow down, so every route asking that host is gated (the Wayback
    availability API and the Internet Archive rung both ask archive.org). `cool` starts one after a cooling answer,
    `cooling(host)` answers its facts while it runs. Each keeps the clock it was started on (the ladder's pacer
    clock), so a later check reads the same clock."""
    #: host -> (clock, the clock reading until which the host is not asked, the facts the ledger names)
    hosts: dict = field(default_factory=dict, repr=False, compare=False)

    def cool(self, clock, seconds, facts, host):
        """Cool `host` for `seconds` from now on `clock` (a cool-down of that host already running LONGER is kept).
        -> the facts in force."""
        until = clock() + seconds
        if self.cooling(host) is None or until > self.hosts[host][1]:
            self.hosts[host] = (clock, until, dict(facts, host=host))
        return self.hosts[host][2]

    def cooling(self, host):
        """-> the facts of a cool-down of `host` still running now, else None."""
        entry = None
        # BEGIN guard: a cool-down is keyed by the host that answered
        # (S4.5 decision D44: a multi-host rung — landing, open access, a Stage B rung's publisher URLs — keeps asking
        # its OTHER hosts while one host cools)
        entry = self.hosts.get(host)
        # END guard: a cool-down is keyed by the host that answered
        if entry is None:
            return None
        clock, until, facts = entry
        live = True               # the unguarded default: a cool-down, once started, never ends
        # BEGIN guard: a cool-down ends at cool_until
        live = clock() < until
        # END guard: a cool-down ends at cool_until
        return facts if live else None


class Gate:
    """S4.5 decisions D44/D45: ONE rung call's request gate over the run's per-host cool-downs. `litkb.acquire.run`
    sets it as `netutil.REQUEST_GATE` around the call; `netutil.Client.get` (and the ladder's wrapper around an
    injected client) asks `before` each request — raising `netutil.HostCooling` for a cooling host — and tells
    `after` each answer. A multi-host rung asks `cooling(url)` itself first and skips that one URL. Records:
    `refused` (every URL not asked because its host was cooling) and `observed` (every answer: host, status,
    Retry-After, whether its body is a bot challenge) — what the ladder cools hosts from and writes on the row."""

    def __init__(self, route, hosts, clock, exempt=()):
        self.route, self.hosts, self.clock = route, hosts, clock
        #: hosts this call may ask whatever their cool-down: a scheduled retry's, whose wait the ladder has just
        #: sat out for exactly those hosts (`run.acquire.settle`) — on a pacer whose sleep does not move its clock
        #: (a test's, a replay's) the cool-down would otherwise still read as running
        self.exempt = frozenset(exempt or ())
        self.refused, self.observed = [], []
        #: the request in flight: the URL asked, then every redirect hop `hop` let through (auditor-fix7 F1)
        self.chain = []

    def cooling(self, url):
        """-> the cool-down facts of this URL's host (the refusal recorded), or None: the host may be asked."""
        host = host_of(url)
        facts = self.hosts.cooling(host) if (self.hosts is not None and host and host not in self.exempt) else None
        if facts is not None:
            self.refused.append({"host": host, "url": _bare(url), "cooldown": dict(facts)})
        return facts

    def before(self, url):
        from litkb import netutil

        facts = self.cooling(url)
        if facts is not None:
            raise netutil.HostCooling(host_of(url), url, facts)
        self.chain = [url]

    def hop(self, from_url, status, headers, to_url):
        """A redirect `netutil.Client` is about to FOLLOW (auditor-fix7 F1): the hop's own answer is credited to the
        host that gave it; -> False when `to_url`'s host is cooling (the refusal recorded; the 3xx becomes the
        answer), else True (the chain goes on to `to_url`)."""
        self.observed.append({"host": host_of(from_url), "url": _bare(from_url),
                              "asked": _bare(self.chain[0] if self.chain else from_url), "status": int(status or 0),
                              "retry_after_s": retry_after_s(headers), "challenge": False, "hop": True})
        if self.cooling(to_url) is not None:
            return False
        self.chain.append(to_url)
        return True

    def after(self, url, status, headers, body):
        """The answer to a request for `url`: credited to the host that GAVE it — the last hop of a followed redirect
        chain (`hop`), else `url`'s own. `challenge` is THE one detector's word (`netutil.Client.challenge_cause`) on
        every transient answer (a challenge never cools a host, by either cause)."""
        from litkb import netutil

        answered = url
        # BEGIN guard: an answer is credited to the host at the end of the redirect chain
        answered = self.chain[-1] if (self.chain and self.chain[0] == url) else url
        # END guard: an answer is credited to the host at the end of the redirect chain
        self.chain = []
        st = int(status or 0)
        challenge = False
        if st and is_transient_code(st):
            challenge = bool(netutil.Client.challenge_cause(st, answered, body, headers))
        self.observed.append({"host": host_of(answered), "url": _bare(answered), "asked": _bare(url), "status": st,
                              "retry_after_s": retry_after_s(headers), "challenge": challenge})

    def summary(self):
        return {"refused": list(self.refused), "observed": list(self.observed)}


def _bare(url):
    """A URL as the gate records it: without its query (a signed URL's query is a credential)."""
    return (url or "").split("?", 1)[0]


def cooling_url(url):
    """S4.5 decision D44: the pre-check a multi-host rung makes before asking ONE URL: -> the cool-down facts of its
    host in the rung call in progress (the refusal recorded on the gate), or None (ask it; outside a ladder rung
    call there is no gate and every URL may be asked)."""
    from litkb import netutil

    gate = netutil.REQUEST_GATE.get()
    return gate.cooling(url) if gate is not None else None


# ── the persisted state (litkb.route_backoff) ───────────────────────────────────────────────
def load(conn, route, work_id):
    """-> the persisted refusal-ladder state for (route, work), or None."""
    row = conn.execute("SELECT refusals, window_started_at, next_allowed_at FROM litkb.route_backoff "
                       "WHERE route = %s AND work_id = %s", (route, work_id)).fetchone()
    if not row:
        return None
    return {"refusals": row[0], "window_started_at": row[1], "next_allowed_at": row[2]}


def in_window(state, now):
    """-> the next_allowed_at the route is waiting for, when `now` is still inside it; else None."""
    nxt = (state or {}).get("next_allowed_at")
    return nxt if (nxt is not None and now < nxt) else None


def save(conn, ws, token, attempt_id, state):
    """Persist `state` as moved by `attempt_id` (0033 litkb.record_route_backoff: the writer's token, an
    attempt of the caller's own workstream, and an older attempt never rolls the ladder back)."""
    conn.execute("SELECT litkb.record_route_backoff(%s, %s, %s, %s, %s, %s)",
                 (ws, token, attempt_id, int(state.get("refusals") or 0), state.get("window_started_at"),
                  state.get("next_allowed_at")))


def db_now(conn):
    """The database clock (clock_timestamp, not the transaction's start): the ladder compares against
    the same clock the ledger's `at` was written with."""
    return conn.execute("SELECT clock_timestamp()").fetchone()[0]

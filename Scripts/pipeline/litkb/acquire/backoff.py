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


@dataclass
class Aimd:
    """In-run pacing for ONE route (guards 2 + 11): multiply on a transient refusal, decay linearly on
    every 2xx, never above the ceiling. `delay()` is how long to wait before the next request."""
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

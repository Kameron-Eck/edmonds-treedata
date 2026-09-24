"""litkb S4.5 builder C1a — the ledger substrate's counters and fires, for `litkb_acceptance.py hardening`.

Loaded BY PATH by builder A's `hardening` subcommand (qc/instruments is not a package; S4.5 CONTRACTS "Counters
and fires"). It defines exactly three names:

  COUNTERS  {gated counter name: fn(conn, manifest) -> int}     the plan's (b) names, gated
  REPORTED  {reported counter name: fn(conn, manifest) -> int}  (b)'s REPORTED names
  FIRES     {fire name: {"counter": name, "run": fn(conn, arm, workdir) -> int}}

`conn` is a READ-ONLY connection for a counter; a fire's `conn` is an already reset + migrated WORKER-DB
connection (the fire refuses anything else). Nothing here re-implements a rule it grades: the back-off window
is replayed with `litkb.acquire.backoff.BackoffPolicy()` — the REFERENCE constants — so a run that set its
own window to zero is graded against the window it should have kept.

Counter scoping (S4.5 decision D1): RUN-SCOPED counters read attempt rows with `at` after
`manifest["frozen_at"]` in `manifest["run_workstream_ids"]` (the ledger's history holds violations that
predate the rules, and deleting history is not ours); ALL-TIME counters (`bad_file_untyped`,
`blocked_untyped`) read every row, because the reviewed backfill (`python -m litkb.acquire.ledger
backfill-sub-status`) types the history.

Every fire's input is named for what it is. E13's REAL recorded challenge page
(qc/fixtures/litkb_e13_challenge_b65a33b17354.html, the 5,631 bytes Cloudflare served for
10.1145/3534678.3539043 on 2026-09-16, quarantined on the live store as `…__blocked__b65a33b17354.pdf`) is
served by a stub client to a CONSTRUCTED admission (a salted synthetic DOI with E13's title), because a worker
database holds no E13 and a DOI admits once per database. No fire touches the network.
"""
import contextlib
import hashlib
import json
import uuid
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
E13_FIXTURE = SCRIPTS / "qc" / "fixtures" / "litkb_e13_challenge_b65a33b17354.html"
#: the sha256 of the recorded bytes as served (the live quarantine row's sha; the fixture is `binary` in
#: .gitattributes, so no checkout rewrites it)
E13_SHA256 = "b65a33b17354573e464656ae815ccde9261ef6da218935d24eaa928135b282e5"
E13_DOI = "10.1145/3534678.3539043"
E13_TITLE = "DocLayNet: A Large Human-Annotated Dataset for Document-Layout Segmentation"

NETWORK_ROUTES_EXCLUDED = ("browser", "hunt-url", "ladder")


# ── scoping ─────────────────────────────────────────────────────────────────────────────────
def _scope(manifest):
    """-> (frozen_at, [workstream ids]) for a run-scoped counter; a manifest without them is refused (an
    unscoped run counter would grade the whole history and pass or fail for reasons the run did not cause)."""
    frozen = (manifest or {}).get("frozen_at")
    ws = list((manifest or {}).get("run_workstream_ids") or [])
    if not ws and (manifest or {}).get("workstream_id"):
        ws = [manifest["workstream_id"]]
    if not frozen or not ws:
        raise ValueError("a run-scoped counter needs manifest frozen_at and run_workstream_ids (S4.5 decision D1)")
    return frozen, [str(w) for w in ws]


def _non_spend():
    from litkb.acquire import backoff as B
    return sorted(B.NON_SPEND_STATUSES)


# ── gated counters ──────────────────────────────────────────────────────────────────────────
def rehunt_route_spends(conn, manifest):
    """Run-scoped: SPENT attempts on a route, for a work, inside that (route, work)'s refusal window as the
    REFERENCE back-off policy computes it from every earlier attempt (all time, every workstream), that
    are not a scheduled transient retry (`retry_of`)."""
    from litkb.acquire import backoff as B

    frozen, ws = _scope(manifest)
    ref = B.BackoffPolicy()
    rows = conn.execute(
        "SELECT a.id, a.route, a.work_id, a.at FROM litkb.acquisition_attempts a "
        " WHERE a.at > %s AND a.workstream_id::text = ANY(%s) AND a.work_id IS NOT NULL AND a.retry_of IS NULL "
        "   AND a.route <> ALL(%s) AND a.status <> ALL(%s) ORDER BY a.at, a.id",
        (frozen, ws, list(NETWORK_ROUTES_EXCLUDED), _non_spend())).fetchall()
    n = 0
    for aid, route, work_id, at in rows:
        prior = conn.execute(
            "SELECT id, status, coalesce(http_codes, '{}'), at, retry_of FROM litkb.acquisition_attempts "
            " WHERE route = %s AND work_id = %s AND (at < %s OR (at = %s AND id < %s)) ORDER BY at, id",
            (route, work_id, at, at, aid)).fetchall()
        state = ref.replay(prior)
        if state and state.get("next_allowed_at") is not None and at < state["next_allowed_at"]:
            n += 1
    return n


def known_bad_relands(conn, manifest):
    """Run-scoped: route attempts that WROTE their served bytes into the store (landed `ok`, or quarantined)
    although the sha256 matched refused bytes recorded BEFORE the attempt — an uncleared quarantine row, or a
    rejected / withdrawn file version. The operator's `--from-file` (route `browser`) is excluded: re-binding
    a quarantined file by hand is the designed path (run.index_of_held)."""
    frozen, ws = _scope(manifest)
    return conn.execute(
        """
        SELECT count(*) FROM litkb.acquisition_attempts a
         WHERE a.at > %s AND a.workstream_id::text = ANY(%s) AND a.served_sha256 IS NOT NULL
           AND a.route <> 'browser' AND (a.status = 'ok' OR a.detail ? 'quarantined')
           AND (EXISTS (SELECT 1 FROM litkb.quarantine_payloads q
                         WHERE q.sha256 = a.served_sha256 AND q.cleared_at IS NULL AND q.recorded_at < a.at
                           AND q.attempt_id IS DISTINCT FROM a.id)
                OR EXISTS (SELECT 1 FROM litkb.files f JOIN litkb.file_versions fv ON fv.file_id = f.id
                            WHERE f.sha256 = a.served_sha256 AND fv.state IN ('rejected', 'withdrawn')
                              AND fv.created_at < a.at))
        """, (frozen, ws)).fetchone()[0]


def bad_file_untyped(conn, manifest):
    """ALL-TIME: `bad-file` attempts with no sub-status."""
    return conn.execute("SELECT count(*) FROM litkb.acquisition_attempts "
                        "WHERE status = 'bad-file' AND sub_status IS NULL").fetchone()[0]


def blocked_untyped(conn, manifest):
    """ALL-TIME: `blocked` attempts with no sub-status."""
    return conn.execute("SELECT count(*) FROM litkb.acquisition_attempts "
                        "WHERE status = 'blocked' AND sub_status IS NULL").fetchone()[0]


def frozen_budget(manifest):
    """The budget FROZEN outside the ladder that `budget_exceeded_silently` grades against (Codex X2, S4.5
    CONTRACTS: removing the budget object must not remove the threshold the checker reads): the manifest's
    `ladder_budget` ({"seconds", "attempts"}, the run's own budget recorded at freeze), else the REFERENCE
    `policy.LadderBudget()` — its seconds (the attempts default is DERIVED per ladder from the rungs it ran,
    so without a frozen value the attempts are graded against each ladder's own declared budget only)."""
    from litkb.acquire import policy as P

    held = (manifest or {}).get("ladder_budget")
    if held:
        return {"seconds": held.get("seconds"), "attempts": held.get("attempts")}
    return {"seconds": P.LadderBudget().seconds, "attempts": None}


def _past(ladder, budget):
    b = budget or {}
    return ((b.get("attempts") is not None and (ladder.get("spent_before") or 0) >= b["attempts"]) or
            (b.get("seconds") is not None and (ladder.get("elapsed_s") or 0) >= b["seconds"]))


def budget_exceeded_silently(conn, manifest):
    """Run-scoped: ladders (one work in one workstream) that LAUNCHED a rung past their budget with no
    `budget-stop` row before it. Each spent rung attempt records, in `detail.ladder`, the ladder's elapsed
    seconds and spent-attempt count at launch (its MEASUREMENTS) and the budget it declared. The THRESHOLD is
    read twice: the budget frozen outside the ladder (`frozen_budget`: the manifest's `ladder_budget`, else the
    reference seconds) AND the one the ladder declared — past either is counted, so a ladder that dropped its
    budget object (declares none) is still graded (auditor-C1a F6, Codex X2). A spent rung row with NO
    `detail.ladder` escaped the ladder's accounting and is counted too."""
    frozen, ws = _scope(manifest)
    held = frozen_budget(manifest)
    non_spend = set(_non_spend())
    rows = conn.execute(
        "SELECT work_id, workstream_id, route, status, detail->'ladder' FROM litkb.acquisition_attempts "
        " WHERE at > %s AND workstream_id::text = ANY(%s) AND work_id IS NOT NULL ORDER BY at, id",
        (frozen, ws)).fetchall()
    stopped, over = set(), set()
    for work_id, ws_id, route, status, ladder in rows:
        key = (str(work_id), str(ws_id))
        if status == "budget-stop":
            stopped.add(key)
            continue
        if key in stopped or route in NETWORK_ROUTES_EXCLUDED or status in non_spend:
            continue
        if not ladder:
            over.add(key)
            continue
        threshold = None            # the unguarded default: only the budget the ladder declared itself
        # BEGIN guard: the budget counter reads a threshold frozen outside the ladder
        threshold = held
        # END guard: the budget counter reads a threshold frozen outside the ladder
        if _past(ladder, threshold) or _past(ladder, ladder.get("budget")):
            over.add(key)
    return len(over)


# ── reported counters ───────────────────────────────────────────────────────────────────────
def transient_rows_unretried(conn, manifest):
    """Run-scoped: attempts whose `retriable` is true, that are not themselves a retry, and that no scheduled
    retry names (a rung that retries inside itself, or opted out, leaves these)."""
    frozen, ws = _scope(manifest)
    return conn.execute(
        "SELECT count(*) FROM litkb.acquisition_attempts a WHERE a.at > %s AND a.workstream_id::text = ANY(%s) "
        "AND a.retriable AND a.retry_of IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM litkb.acquisition_attempts r WHERE r.retry_of = a.id)",
        (frozen, ws)).fetchone()[0]


def attempts_without_sha(conn, manifest):
    """Run-scoped: attempts that received bytes (a landing, a measured or known-bad hit, a kept payload, a sha
    in the detail) with no `served_sha256`."""
    frozen, ws = _scope(manifest)
    return conn.execute(
        "SELECT count(*) FROM litkb.acquisition_attempts a WHERE a.at > %s AND a.workstream_id::text = ANY(%s) "
        "AND a.served_sha256 IS NULL AND (a.status IN ('ok', 'measured', 'known-bad', 'duplicate-held') "
        "OR a.detail ? 'sha256' OR a.detail ? 'quarantined')", (frozen, ws)).fetchone()[0]


def attempts_without_terminal(conn, manifest):
    """Run-scoped: SPENT rung attempts (not browser / hunt-url / ladder, not a skip or a stop) with no
    terminal status code."""
    frozen, ws = _scope(manifest)
    return conn.execute(
        "SELECT count(*) FROM litkb.acquisition_attempts a WHERE a.at > %s AND a.workstream_id::text = ANY(%s) "
        "AND a.route <> ALL(%s) AND a.status <> ALL(%s) AND a.terminal_status_code IS NULL",
        (frozen, ws, list(NETWORK_ROUTES_EXCLUDED), _non_spend())).fetchone()[0]


def files_without_word_count(conn, manifest):
    """ALL-TIME: files whose CURRENT version is active and carries no word count (the word-count backfill
    drives it down)."""
    return conn.execute(
        "SELECT count(*) FROM litkb.files f JOIN litkb.file_versions fv ON fv.version_id = f.current_version_id "
        "WHERE fv.status = 'active' AND fv.word_count IS NULL").fetchone()[0]


def hits_without_version(conn, manifest):
    """Run-scoped: hits (`ok`, `measured`) whose article version is unknown — neither the landed version's
    copy_kind nor the attempt's `detail.version` (guard 23)."""
    frozen, ws = _scope(manifest)
    return conn.execute(
        "SELECT count(*) FROM litkb.acquisition_attempts a "
        "LEFT JOIN litkb.file_versions fv ON fv.version_id::text = a.detail->'attach'->>'file_version' "
        "WHERE a.at > %s AND a.workstream_id::text = ANY(%s) AND a.status IN ('ok', 'measured') "
        "AND fv.copy_kind IS NULL AND coalesce(a.detail->>'version', '') = ''", (frozen, ws)).fetchone()[0]


COUNTERS = {
    "rehunt_route_spends": rehunt_route_spends,
    "known_bad_relands": known_bad_relands,
    "bad_file_untyped": bad_file_untyped,
    "blocked_untyped": blocked_untyped,
    "budget_exceeded_silently": budget_exceeded_silently,
}
REPORTED = {
    "transient_rows_unretried": transient_rows_unretried,
    "attempts_without_sha": attempts_without_sha,
    "attempts_without_terminal": attempts_without_terminal,
    "files_without_word_count": files_without_word_count,
    "hits_without_version": hits_without_version,
}


# ── the fires' world: a worker database only, stub clients only ────────────────────────────
class StubClient:
    """Answers by URL substring; an unknown URL is a 404 (never the network). Records every URL asked."""
    base = ""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        for frag, resp in self.routes.items():
            if frag in url:
                return resp(url) if callable(resp) else resp
        return 404, {}, b""


def e13_bytes():
    """E13's REAL recorded challenge page, checked against the sha the live quarantine row holds."""
    data = E13_FIXTURE.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != E13_SHA256:
        raise RuntimeError(f"{E13_FIXTURE.name}: sha256 {got} is not the recorded {E13_SHA256}")
    return data


def _unpaywall(urls):
    """A stub Unpaywall record listing `urls` as OA locations (the v2 record's own field names)."""
    return (200, {}, json.dumps({"is_oa": True, "oa_status": "bronze",
                                 "oa_locations": [{"url": u, "host_type": "publisher"} for u in urls]}).encode())


class World:
    """A workstream, an admitted work and a writer session on a WORKER database (never `litkb`)."""

    def __init__(self, conn, workdir):
        from litkb.acquire.store import Store
        from litkb.db import connect as c

        dbname = conn.info.dbname
        # BEGIN guard: a fire runs only on a worker database
        if not c.is_test_db(dbname):
            raise RuntimeError(f"a C1a fire runs only on a litkb_test* worker database, not {dbname!r}")
        # END guard: a fire runs only on a worker database
        self.owner = conn
        self.dbname = dbname
        self.writer = c.connect(dbname, "litkb_test", autocommit=True)
        self.writer.execute("SET ROLE litkb_writer")
        self.workdir = Path(workdir)
        self.store = Store(self.workdir / "Lit", index_cache=self.workdir / "index.json")
        self.tokens = {}

    def close(self):
        self.writer.close()

    def ws(self, slug):
        ws_id, token = self.owner.execute(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/c1a-fire', NULL, %s, NULL)",
            (f"c1a-{slug}-{uuid.uuid4().hex[:10]}", "S4.5 builder C1a fire (worker database)")).fetchone()
        self.tokens[ws_id] = token
        return ws_id

    def now(self):
        return self.owner.execute("SELECT clock_timestamp()").fetchone()[0]

    def work(self, ws, title=E13_TITLE, author="Pfitzmann", year=2022):
        """A CONSTRUCTED registry admission: a salted synthetic DOI carrying `title` (the evidence shape
        qc/test_litkb_p2.py::_good_payload uses). -> run.work_record's dict."""
        from psycopg.types.json import Jsonb

        from litkb.acquire import run

        hexid = uuid.uuid4().hex[:12]
        doi = f"10.5555/c1a-fire-{hexid}"
        title = f"{title} {hexid}"
        ev = {"registry": "crossref", "registry_title": title, "registry_first_author": author, "registry_year": year,
              "claimed": {"title": title, "first_author": author, "year": year, "title_ratio": 1.0,
                          "author_match": True}}
        tok = self.tokens[ws]
        cand = self.writer.execute(
            "SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
            (ws, tok, title)).fetchone()[0]
        res = self.writer.execute(
            "SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, 'c1a-fire', 'c1a-fire-1')",
            (ws, tok, cand, f"{author}_{year}_constructed-{hexid}",
             Jsonb({"type": "proceedings", "title": title, "authors": [{"family": author, "given": "B."}], "year": year}),
             Jsonb([{"scheme": "doi", "value": doi, "verified_by": "crossref", "evidence": ev}]), Jsonb({}))).fetchone()[0]
        if res.get("outcome") != "admitted":
            raise RuntimeError(f"the constructed admission was refused: {res}")
        return run.work_record(self.writer, work_id=res["work_id"])

    def acquire(self, ws, work, clients, **kw):
        from litkb.acquire import run
        from litkb.netutil import Pacer

        return run.acquire(self.writer, ws, self.tokens[ws], work, store=self.store, agent="c1a-fire",
                           session="c1a-fire-1", clients=clients, pacer=Pacer(interval=0, sleep=lambda s: None),
                           printer=lambda *a, **k: None, pacing={}, **kw)


@contextlib.contextmanager
def _no_secrets_read():
    """The fires never read Kam's Unpaywall email: the lookup is asked with a constructed address."""
    from litkb.acquire import open_access
    with mock.patch.object(open_access, "unpaywall_email", lambda: "c1a-fire@example.invalid"):
        yield


def _e13_clients():
    """E13's two answers: open access -> doi.org 403 with the REAL recorded Cloudflare page; every Sci-Hub
    mirror -> a 403 challenge (the register's `blocked/403`) whose body is CONSTRUCTED — a minimal "Just a
    moment..." page, the challenge's title, not a recording."""
    page = e13_bytes()
    oa = StubClient({"api.unpaywall.org": _unpaywall([f"https://doi.org/{E13_DOI}"]), "doi.org/": (403, {}, page)})
    sh = StubClient({"sci-hub": (403, {}, b"<html><head><title>Just a moment...</title></head></html>")})
    return {"open_access": oa, "scihub": sh}


def _manifest(frozen_at, ws_ids):
    return {"frozen_at": frozen_at, "run_workstream_ids": [str(w) for w in ws_ids]}


def fire_backoff_window_zero(conn, arm, workdir):
    """(c): the back-off window set to zero -> E13's second hunt re-spends (none of its statuses is a
    permanent dead status) -> rehunt_route_spends > 0. Hunt 1 in one workstream, hunt 2 in ANOTHER (a new
    run: `blocked` is dead only within a run, so across runs the back-off alone must hold)."""
    from litkb.acquire import backoff as B

    w = World(conn, workdir)
    try:
        with _no_secrets_read():
            # the RUN's policy, for both hunts: the known-bad run keeps a zero window from the first refusal on
            policy = B.BackoffPolicy() if arm == "control" else B.BackoffPolicy(refusal_ladder_s=(0, 0, 0))
            ws1 = w.ws("rehunt-1")
            work = w.work(ws1)
            w.acquire(ws1, work, _e13_clients(), routes=("open_access", "scihub"), backoff=policy)
            frozen = w.now()
            ws2 = w.ws("rehunt-2")
            w.acquire(ws2, w_work_again(w, work), _e13_clients(), routes=("open_access", "scihub"), backoff=policy)
        return rehunt_route_spends(conn, _manifest(frozen, [ws2]))
    finally:
        w.close()


def w_work_again(w, work):
    """The same work, re-read (a second hunt reads main afresh)."""
    from litkb.acquire import run
    return run.work_record(w.writer, work_id=work["work_id"])


def fire_known_bad_lookup_disabled(conn, arm, workdir):
    """(c): E13's bytes re-served with the lookup disabled -> known_bad_relands = 1. The refused-bytes record
    holds E13's recording (a legacy-backfill quarantine row, as the live store holds it); the route serves the
    SAME recording again (a live re-fetch would not: survey-data §0.5, the challenge page's sha changes on
    every serving)."""
    from litkb.acquire import run
    from litkb.quarantine import ingest_connect

    w = World(conn, workdir)
    rec = ingest_connect(w.dbname)
    try:
        rel = f"_quarantine/Constructed_2022_e13-recording-{uuid.uuid4().hex[:8]}__blocked__{E13_SHA256[:12]}.pdf"
        from psycopg.types.json import Jsonb
        rec.execute("SELECT litkb.record_quarantine_system(%s, %s, %s, 'blocked', 'legacy-backfill', NULL, NULL, NULL, %s)",
                    (rel, E13_SHA256, len(e13_bytes()), Jsonb({"fire": "c1a known_bad_relands"})))
        with _no_secrets_read():
            frozen = w.now()
            ws = w.ws("known-bad")
            work = w.work(ws)
            patch = (contextlib.nullcontext() if arm == "control"
                     else mock.patch.object(run, "_known_bad", lambda conn, sha: None))
            with patch:
                w.acquire(ws, work, {"open_access": _e13_clients()["open_access"]}, routes=("open_access",))
        return known_bad_relands(conn, _manifest(frozen, [ws]))
    finally:
        rec.close()
        w.close()


def _typing_world(conn, arm, workdir):
    """Two works, two answers: a 200 HTML page served for a PDF link (bad-file) and E13's 403 challenge
    (blocked). Control: both typed as they are written. Known-bad: the typing step disabled."""
    from litkb.acquire import run

    w = World(conn, workdir)
    try:
        with _no_secrets_read():
            ws = w.ws("typing")
            html = (b"<!DOCTYPE html><html><head><title>Landing page</title></head><body>not the file "
                    + uuid.uuid4().hex.encode() + b"</body></html>")
            a, b = w.work(ws), w.work(ws)
            patch = (contextlib.nullcontext() if arm == "control"
                     else mock.patch.object(run, "_type_attempt", lambda *x, **k: (None, "")))
            with patch:
                w.acquire(ws, a, {"open_access": StubClient({"api.unpaywall.org": _unpaywall(["https://oa.example/a"]),
                                                             "oa.example": (200, {}, html)})}, routes=("open_access",))
                w.acquire(ws, b, {"open_access": _e13_clients()["open_access"]}, routes=("open_access",))
    finally:
        w.close()


def fire_typing_disabled_bad_file(conn, arm, workdir):
    """(c): the typing step disabled -> bad_file_untyped > 0."""
    _typing_world(conn, arm, workdir)
    return bad_file_untyped(conn, {})


def fire_typing_disabled_blocked(conn, arm, workdir):
    """(c): the typing step disabled -> blocked_untyped > 0."""
    _typing_world(conn, arm, workdir)
    return blocked_untyped(conn, {})


#: the fire's FROZEN budget (Codex X2: "freeze a numeric budget and force a known overrun"): one attempt, and
#: the two-rung E13 ladder below misses on both, so a second launch is the known overrun
FIRE_BUDGET = {"seconds": None, "attempts": 1}


def fire_budget_removed(conn, arm, workdir):
    """(c): the budget object removed -> budget_exceeded_silently = 1. The manifest FREEZES a one-attempt budget
    (FIRE_BUDGET) and the run is handed that budget; two rungs both miss. Control: the ladder stops after the
    first with a `budget-stop` row. Known-bad: the budget OBJECT is removed from the ladder (the budget it
    resolves carries no limit at all, so the rows declare none and nothing ever stops it) — the second rung is
    launched silently, and only the frozen threshold can see it (Codex X2; auditor-C1a mutation A13 is this)."""
    from litkb.acquire import policy as P

    w = World(conn, workdir)
    try:
        with _no_secrets_read():
            frozen = w.now()
            ws = w.ws("budget")
            work = w.work(ws)
            patch = (contextlib.nullcontext() if arm == "control"
                     else mock.patch.object(P.LadderBudget, "resolved",
                                            lambda self, rungs: P.LadderBudget(seconds=None, clock=self.clock)))
            with patch:
                w.acquire(ws, work, _e13_clients(), routes=("open_access", "scihub"),
                          ladder_budget=P.LadderBudget(seconds=FIRE_BUDGET["seconds"],
                                                       attempts=FIRE_BUDGET["attempts"]))
        return budget_exceeded_silently(conn, _manifest(frozen, [ws]) | {"ladder_budget": dict(FIRE_BUDGET)})
    finally:
        w.close()


FIRES = {
    "backoff_window_zero": {"counter": "rehunt_route_spends", "run": fire_backoff_window_zero},
    "known_bad_lookup_disabled": {"counter": "known_bad_relands", "run": fire_known_bad_lookup_disabled},
    "typing_disabled_bad_file": {"counter": "bad_file_untyped", "run": fire_typing_disabled_bad_file},
    "typing_disabled_blocked": {"counter": "blocked_untyped", "run": fire_typing_disabled_blocked},
    "budget_removed": {"counter": "budget_exceeded_silently", "run": fire_budget_removed},
}


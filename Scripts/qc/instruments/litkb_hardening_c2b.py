"""builder-C2b's counters and known-bads for `litkb_acceptance.py hardening` (LITKB_WORKPLAN.md "### S4.5" (b)/(c);
the S4.5 CONTRACTS module contract). Loaded BY PATH (qc/instruments is not a package).

    COUNTERS  gated:    landing_pages_booked_bad_file (RUN-SCOPED, S4.5 decision D1)
    REPORTED            bronze_landing_unconverted, manual_step_rows (RUN-SCOPED); and, beyond the plan's (b) names,
                        landing_pages_after_stage_c (the pages the gate leaves to a later stage, auditor-C2b round 2 F1)
    FIRES     stage_c_disabled, mdpi_cdn_rule_disabled, paywalled_probe_disabled, e13_challenge_rule_disabled
    DETAILS             the rows behind each counter, for the report

A counter is `fn(conn, manifest) -> int` on a READ-ONLY connection. Manifest keys read: `frozen_at`,
`run_workstream_ids` (the run scope), `probe_csvs` (for bronze_landing_unconverted's four DOIs: the
`litkb_acq_probe_no_oa_copy.csv` basename; absent, the tracked CSV under phase4/qc/ is read), and
`literature_root` (optional; absent, `litkb.acquire.store.LITERATURE_ROOT`): where the gated counter reads a refused
page's bytes when no row carries its pointer fact, and where the fires' own counters read kept payloads.

A FIRE is `fn(conn, arm, workdir) -> int`: `arm` is "control" or "known_bad", on an already reset + migrated WORKER
database (the owner login). Every fire drives THE REAL LADDER (`litkb.acquire.run.acquire`) with the landing rung
and stub clients that serve the RECORDED landing pages of qc/fixtures/litkb_landing_pages/ (real bytes, recorded
2026-09-23 under this builder's one-page-per-rule grant) and, where a request was never recorded because the grant
covered no PDF endpoint, an answer named CONSTRUCTED in its function's docstring. The known-bad switches ONE guard
off IN THIS PROCESS and restores it before the counter reads. Nothing here touches the network or the live store.

Every mechanism these counters and fires grade is a RELAYED design (CLAUDE.md §3.4c), UNVALIDATED until an
independent referee scores it on the real rows the plan names; nothing here scores it.
"""
import contextlib
import csv
import hashlib
import importlib.util
import json
import uuid
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
LANDING_FIXTURES = SCRIPTS / "qc" / "fixtures" / "litkb_landing_pages"
E13_FIXTURE = SCRIPTS / "qc" / "fixtures" / "litkb_e13_challenge_b65a33b17354.html"
MDPI_AKAMAI_PDF = SCRIPTS / "qc" / "fixtures" / "litkb_mdpi_pdf_akamai_a3b93f589df6.html"
NO_OA_COPY_CSV = "litkb_acq_probe_no_oa_copy.csv"
#: The four Elsevier bronze rows the brief names (survey-data §2.3) — the counter READS them from the probe CSV
#: (`unpaywall_url` a doi.org landing URL, the plan's own command); this tuple is what that read is checked against
#: by a TEST (qc/test_litkb_landing.py::test_the_bronze_rows_are_read_from_the_probe_csv), so a changed CSV turns
#: the suite red. At run time the counter reads the CSV it is handed and does NOT compare it with this tuple: a run
#: given another CSV is re-scoped to that CSV's rows, and its DETAILS name every DOI it read.
BRONZE_DOIS = ("10.1016/j.isprsjprs.2018.06.002", "10.1016/j.rse.2019.111261", "10.1016/j.rse.2021.112806",
               "10.1016/j.ufug.2018.03.006")


# ── recorded pages ───────────────────────────────────────────────────────────────────────────
def load_recording(rule_id, root=LANDING_FIXTURES):
    """-> the recording dict with each hop's `body` bytes attached, every body re-checked against its sha256 (a
    recording whose bytes changed is refused, never served)."""
    d = Path(root) / rule_id
    rec = json.loads((d / "recording.json").read_text(encoding="utf-8"))
    for h in rec["hops"]:
        body = (d / h["response"]["body_file"]).read_bytes()
        got = hashlib.sha256(body).hexdigest()
        # BEGIN guard: a recorded body whose bytes changed is refused, never served
        if got != h["response"]["sha256"]:
            raise RuntimeError(f"{d.name}/{h['response']['body_file']}: sha256 {got} is not the recorded "
                               f"{h['response']['sha256']}")
        # END guard: a recorded body whose bytes changed is refused, never served
        h["body"] = body
    return rec


def recorded_answers(rec, *, rewrite_doi=None):
    """{url: (status, headers, body)} of a recording's hops. `rewrite_doi` = (recorded DOI, another DOI) answers the
    DOI resolver URL of the other DOI with the recorded first hop (a fire's CONSTRUCTED admission carries a salted DOI
    of its own; every other hop is served at its recorded URL)."""
    from litkb.acquire import landing as L

    out = {}
    for h in rec["hops"]:
        out[h["request"]["url"]] = (h["response"]["status"], dict(h["response"]["headers"]), h["body"])
    if rewrite_doi:
        old, new = rewrite_doi
        first = L.doi_url(old)
        if first in out:
            out[L.doi_url(new)] = out[first]
    return out


class FixtureClient:
    """A stub `netutil.Client` for the landing rung: answers an EXACT URL from `answers`, else the first
    `prefixes` entry the URL starts with, else 404 (never the network). Records every request (url, headers)."""
    base = ""

    def __init__(self, answers=None, prefixes=None):
        self.answers, self.prefixes, self.calls = dict(answers or {}), dict(prefixes or {}), []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        from litkb.cassette import scrub_url

        self.calls.append({"url": url, "accept": accept, "follow": follow, "headers": dict(headers or {})})
        # a recorded URL was written through the cassette's scrub (a `key=` parameter masked, as litkb.cassette's
        # request key masks it), so a request is matched after the same scrub
        hit = url if url in self.answers else scrub_url(url)
        if hit in self.answers:
            a = self.answers[hit]
        else:
            a = next((v for k, v in self.prefixes.items() if url.startswith(k)), (404, {}, b""))
        return a(url, headers or {}) if callable(a) else a


def _edge():
    spec = importlib.util.spec_from_file_location("litkb_edge_run_for_c2b", Path(__file__).with_name("litkb_edge_run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def constructed_paper(title, author, salt):
    """A CONSTRUCTED one-page paper the acceptance test accepts and the binder binds to (title, author) — the shape
    of `qc/instruments/litkb_edge_run.py::_pdf_bytes` (one home for the constructed paper; its body-line count is
    the one integrator-w1 MEASURED past the 5,000-byte floor)."""
    return _edge()._pdf_bytes(title, author, salt=salt)


def _pdf_answer(data):
    """A CONSTRUCTED server that honours the Range probe: 206 with the first 4 KB, else 200 with the whole file."""
    def answer(url, headers):
        rng = {k.lower(): v for k, v in (headers or {}).items()}.get("range")
        if rng:
            return 206, {"Content-Type": "application/pdf", "Content-Range": f"bytes 0-4095/{len(data)}"}, data[:4096]
        return 200, {"Content-Type": "application/pdf", "Content-Length": str(len(data))}, data
    return answer


# ── scoping (S4.5 decision D1) ───────────────────────────────────────────────────────────────
def _scope(manifest):
    frozen = (manifest or {}).get("frozen_at")
    ws = [str(w) for w in (manifest or {}).get("run_workstream_ids") or []]
    if not ws and (manifest or {}).get("workstream_id"):
        ws = [str(manifest["workstream_id"])]
    if not frozen or not ws:
        raise ValueError("a run-scoped counter needs manifest frozen_at and run_workstream_ids (S4.5 decision D1)")
    return frozen, ws


# ── the counters ─────────────────────────────────────────────────────────────────────────────
#: A page an earlier rung was served, typed html_response, that carried a PDF pointer (THE acceptance test's fact,
#: `accept.landing_signals`: citation_pdf_url and its bepress_ / eprints. variants by suffix, eprints.document_url, a
#: PDF alternate link), for which NO Stage C attempt of the run followed on the same work. "Followed" = a `landing`
#: row OF THAT WORK at or after it that is not a skip saying Stage C never looked (`policy_refused`,
#: `no_identifier`); a `dead_in_run` / `backoff_window` skip means Stage C DID look earlier. A `landing` row BEFORE
#: the page does not follow it (qc/test_litkb_landing.py::test_a_landing_row_before_the_page_does_not_follow_it).
#: The SQL selects every unfollowed html_response row with what the pointer fact can be read from; `_pointer_fact`
#: decides. A row whose bytes were ALREADY refused (the rejected-hash branch of `litkb.acquire.run._record_result`)
#: is not typed again, so its own detail carries no fact (auditor-C2b F1, MEASURED on litkb_test_w3: the gate read 1,
#: then 0 on the same page served twice with Stage C off) — hence the other two sources below.
#: WHICH rows the gate reads is `_routes_after_stage_c`'s: a page served by a rung the ladder runs AFTER Stage C is
#: reported (`landing_pages_after_stage_c`), never gated (auditor-C2b round 2 F1).
_LANDING_BAD_FILE_SQL = """
SELECT a.id::text, a.work_id::text, a.route, a.at, w.key,
       a.detail -> 'acceptance' -> 'facts' -> 'landing' ->> 'pdf_pointer' AS own_fact,
       a.served_sha256,
       (SELECT s.detail -> 'acceptance' -> 'facts' -> 'landing' ->> 'pdf_pointer'
          FROM litkb.acquisition_attempts s
         WHERE s.served_sha256 = a.served_sha256
           AND (s.detail -> 'acceptance' -> 'facts' -> 'landing' ->> 'pdf_pointer') IS NOT NULL
         ORDER BY s.at, s.id LIMIT 1) AS same_bytes_fact,
       a.detail -> 'known_bad' ->> 'rel_path' AS refused_copy,
       a.detail ->> 'quarantined' AS own_copy,
       coalesce(a.terminal_url, a.detail ->> 'source_url') AS page_url
  FROM litkb.acquisition_attempts a LEFT JOIN litkb.works w ON w.id = a.work_id
 WHERE a.at > %(frozen)s AND a.workstream_id::text = ANY(%(ws)s)
   AND a.status = 'bad-file' AND a.sub_status = 'html_response' AND a.route <> 'landing'
   AND NOT EXISTS (
       SELECT 1 FROM litkb.acquisition_attempts b
        WHERE b.work_id = a.work_id AND b.route = 'landing' AND b.at >= a.at
          AND b.workstream_id::text = ANY(%(ws)s) AND b.status <> 'budget-stop'
          AND NOT (b.status = 'skipped' AND coalesce(b.sub_status, '') IN ('policy_refused', 'no_identifier')))
 ORDER BY a.at, a.id
"""


def _literature_root(manifest):
    from litkb.acquire.store import LITERATURE_ROOT

    return Path((manifest or {}).get("literature_root") or LITERATURE_ROOT)


def _pointer_fact(row, root):
    """-> (carried a PDF pointer: True / False / None when it cannot be read, basis). In order:
      1  the row's own acceptance fact (the ladder typed these bytes here);
      2  the fact of ANY attempt row that was served the same bytes (`served_sha256` is a content hash, so the fact
         is the bytes' own, whichever run wrote it);
      3  the bytes themselves — the refused copy the rejected-hash lookup matched (`detail.known_bad.rel_path`), or
         the row's own quarantined copy — read under the literature root, checked against `served_sha256`, and
         typed by THE acceptance test's own detector (`accept.landing_signals`; the live history's pre-S4.5 rows
         carry no fact at all, auditor-C2b §2.4).
    A row that was served bytes and whose fact none of the three yields is None: the gate cannot show the page
    carried no pointer. A row served NO bytes (typed from the terminal response, S4.5 decision D15) had no page to
    follow: (False, ...)."""
    own, sha, same = row[5], row[6], row[7]
    if own in ("true", "false"):
        return own == "true", "the row's own acceptance fact"
    got = (None, "no pointer fact on the row, on a row served the same bytes, or in a readable copy of the bytes")
    # BEGIN guard: a refused page's pointer fact is read from its same-bytes rows or its bytes, never taken as absent
    if same in ("true", "false"):
        return same == "true", "the acceptance fact of a row served the same bytes"
    from litkb.acquire import accept

    data, rel = _kept_page(row, root)
    if data is not None:
        return bool(accept.landing_signals(data)["pdf_pointer"]), f"read from the refused bytes at {rel}"
    # END guard: a refused page's pointer fact is read from its same-bytes rows or its bytes, never taken as absent
    if not sha:
        return False, "no bytes were served (typed from the terminal response): no page to follow"
    return got


def _kept_page(row, root):
    """-> (bytes, rel path) of the row's page as the literature root keeps it — the refused copy the rejected-hash
    lookup matched (`detail.known_bad.rel_path`), else the row's own quarantined copy — ONLY when its sha256 is the
    row's `served_sha256`; else (None, None). MEASURE mode keeps no copy (`litkb.acquire.run._record_result`)."""
    sha, refused_copy, own_copy = row[6], row[8], row[9]
    for rel in (refused_copy, own_copy):
        p = Path(root) / rel if rel else None
        if p is not None and p.is_file():
            data = p.read_bytes()
            if sha and hashlib.sha256(data).hexdigest() == sha:
                return data, rel
    return None, None


def _routes_after_stage_c():
    """The routes of every stage the ladder runs AFTER Stage C (`litkb.acquire.policy.STAGES` order: Stage E, then
    the shadow tier). The ladder never asks Stage C again after them, so a page one of them was served can never be
    "followed" by Stage C: counting it would turn the gate red for the ladder's stage ORDER, not for a Stage C defect
    (auditor-C2b round 2 F1, MEASURED on litkb_test_w3: 1 with a Stage-E-shaped `bad-file` capture after Stage C had
    asked the very pointer the page carries, 0 without it). Those pages are REPORTED by `landing_pages_after_stage_c`
    with whether Stage C asked their pointer. A route no stage names (`hunt-url`, `browser`) stays GATED: fail closed.
    Option (a) of the auditor's three; the orchestrator's to overrule (builder-C2b round 3 report)."""
    from litkb.acquire import policy

    later = []
    # BEGIN guard: a page served by a rung staged after Stage C is reported, never gated
    later = sorted(r for r, s in policy.STAGE_OF.items() if policy.STAGES.index(s) > policy.STAGES.index("C"))
    # END guard: a page served by a rung staged after Stage C is reported, never gated
    return later


def _unfollowed(conn, manifest):
    """-> [(row, carried, basis, after_c)] for every unfollowed html_response row of the run whose page carried a PDF
    pointer, or whose pointer fact cannot be read (FAIL CLOSED: a page the counter cannot read is not a page it may
    call pointer-free); `after_c` = the row's route is staged after Stage C (`_routes_after_stage_c`)."""
    frozen, ws = _scope(manifest)
    root = _literature_root(manifest)
    later = set(_routes_after_stage_c())
    out = []
    for row in conn.execute(_LANDING_BAD_FILE_SQL, {"frozen": frozen, "ws": ws}).fetchall():
        carried, basis = _pointer_fact(row, root)
        counted = bool(carried)
        # BEGIN guard: a pointer fact that cannot be read counts, the gate fails closed
        counted = carried is not False
        # END guard: a pointer fact that cannot be read counts, the gate fails closed
        if counted:
            out.append((row, carried, basis, row[2] in later))
    return out


def landing_pages_unfollowed(conn, manifest, *, with_basis=False):
    """-> the GATED rows: unfollowed html_response rows served by a rung the ladder runs BEFORE Stage C (or by a
    route no stage names) whose page carried a PDF pointer, or whose pointer fact cannot be read. With `with_basis`,
    each row is (row, carried, basis)."""
    return [(row, carried, basis) if with_basis else row
            for row, carried, basis, after_c in _unfollowed(conn, manifest) if not after_c]


def landing_pages_booked_bad_file(conn, manifest):
    """GATED =0 (run-scoped): html_response attempts whose page carried a PDF pointer (or whose pointer fact cannot
    be read: fail closed) and no Stage C attempt on the same work followed — pages served by a rung staged before
    Stage C only (a later stage's are `landing_pages_after_stage_c`'s)."""
    return len(landing_pages_unfollowed(conn, manifest))


_ASKED_SQL = """
SELECT c ->> 'url'
  FROM litkb.acquisition_attempts b,
       jsonb_array_elements(coalesce(b.detail -> 'landing' -> 'candidates', '[]'::jsonb)) c
 WHERE b.work_id::text = %(work)s AND b.route = 'landing' AND b.at > %(frozen)s AND b.workstream_id::text = ANY(%(ws)s)
"""


def _asked_by_stage_c(conn, manifest, row, root):
    """-> ("yes" | "no" | "unknown", why) for one page served after Stage C: did a `landing` row of the SAME work in
    the run ask one of the PDF pointers the page carries (Stage C's own extractor `landing.pointers` over the kept
    bytes, compared with `detail.landing.candidates[].url` by `landing._dedupe_key` after `landing.evidence_url`)?
    The pointer URLs are read from the page's bytes; MEASURE mode keeps none, so there it is "unknown"."""
    from litkb.acquire import landing as L

    frozen, ws = _scope(manifest)
    data, _rel = _kept_page(row, root)
    if data is None:
        return "unknown", "the page's bytes are not kept (MEASURE mode keeps none) or not readable"
    ptrs = [L.evidence_url(u) for u, _src in L.pointers(data, row[10] or "")]
    if not ptrs:
        return "unknown", "no pointer URL could be read from the page"
    asked = {L._dedupe_key(u) for (u,) in conn.execute(
        _ASKED_SQL, {"work": row[1], "frozen": frozen, "ws": ws}).fetchall() if u}
    hit = bool(asked)
    # BEGIN guard: a later stage's page is asked only when Stage C asked a pointer the page itself carries
    hit = any(L._dedupe_key(p) in asked for p in ptrs)
    # END guard: a later stage's page is asked only when Stage C asked a pointer the page itself carries
    if hit:
        return "yes", "a landing row of this work in the run asked a pointer the page carries"
    return "no", (f"no landing row of this work in the run asked any of the page's {len(ptrs)} pointer(s)"
                  if asked else "no landing row of this work in the run asked a candidate")


def landing_pages_after_stage_c(conn, manifest):
    """REPORTED (run-scoped; beyond the plan's (b) names — auditor-C2b round 2 F1 option (a)): the unfollowed
    html_response rows of a rung staged AFTER Stage C whose page carried a PDF pointer (or whose fact cannot be read).
    The gate leaves them out because the ladder never asks Stage C after those stages; `DETAILS` says, per row,
    whether Stage C asked the page's pointer (`asked_by_stage_c=yes|no|unknown`). A `no` is the ladder-order gap the
    auditor's option (c) — ask Stage C again after Stage E — would close; not built here."""
    return sum(1 for *_x, after_c in _unfollowed(conn, manifest) if after_c)


def _probe_csv(manifest):
    got = ((manifest or {}).get("probe_csvs") or {}).get(NO_OA_COPY_CSV)
    if not got:
        return REPO / "phase4" / "qc" / NO_OA_COPY_CSV
    # the freeze writes `probe_csvs` REPO-RELATIVE (builder A's manifest shape): resolved against the manifest's
    # `repo`, never the grader's working directory (seam integrator-w2, A x C2b: the freeze trial on the merged
    # candidate read this counter `unread` — FileNotFoundError from Scripts/)
    p = Path(got)
    return p if p.is_absolute() else Path((manifest or {}).get("repo") or REPO) / p


def bronze_dois(manifest=None):
    """The bronze landing rows, READ from the no-oa-copy probe CSV exactly as the plan's command reads them
    (`unpaywall_url` starting https://doi.org/)."""
    with open(_probe_csv(manifest), encoding="utf-8", newline="") as fh:
        return [r["doi"] for r in csv.DictReader(fh) if (r.get("unpaywall_url") or "").startswith("https://doi.org/")]


_BRONZE_SQL = """
SELECT i.value, w.key,
       (SELECT string_agg(a.status || coalesce('/' || a.sub_status, ''), ',' ORDER BY a.at)
          FROM litkb.acquisition_attempts a
         WHERE a.work_id = i.work_id AND a.route = 'landing' AND a.at > %(frozen)s
           AND a.workstream_id::text = ANY(%(ws)s)) AS landing,
       EXISTS (SELECT 1 FROM litkb.acquisition_attempts a
                WHERE a.work_id = i.work_id AND a.route = 'landing' AND a.at > %(frozen)s
                  AND a.workstream_id::text = ANY(%(ws)s) AND a.status IN ('ok', 'measured')) AS converted
  FROM litkb.main_identifiers i JOIN litkb.main_works w ON w.work_id = i.work_id
 WHERE i.scheme = 'doi' AND i.active AND i.value_norm = litkb.norm_identifier('doi', %(doi)s)
"""


def bronze_rows(conn, manifest):
    frozen, ws = _scope(manifest)
    out = []
    for doi in bronze_dois(manifest):
        row = conn.execute(_BRONZE_SQL, {"frozen": frozen, "ws": ws, "doi": doi}).fetchone()
        out.append({"doi": doi, "key": row[1] if row else None, "landing": (row[2] if row else None) or "",
                    "converted": bool(row[3]) if row else False, "in_main": row is not None})
    return out


def bronze_landing_unconverted(conn, manifest):
    """REPORTED (run-scoped): the Elsevier bronze landing rows Stage C did NOT convert in the run — read from ATTEMPT
    rows (`landing` ok, or `measured` in MEASURE mode), never from the work's file state (survey-data §0.1: 3 of the
    4 already hold an archive file). ESTIMATED zero conversions by the survey; one that ends
    `challenge_or_bot_check` is S4.6's browser rung."""
    return sum(1 for r in bronze_rows(conn, manifest) if not r["converted"])


_MANUAL_SQL = """
SELECT count(*) FROM litkb.acquisition_attempts
 WHERE status = 'manual-step' AND at > %(frozen)s AND workstream_id::text = ANY(%(ws)s)
"""


def manual_step_rows(conn, manifest):
    """REPORTED (run-scoped): `manual-step` rows the run wrote — the works every automated rung (Stage C included)
    left to the hand-fetch queue. The plan names this counter and does not define it; this definition is
    builder-C2b's."""
    frozen, ws = _scope(manifest)
    return conn.execute(_MANUAL_SQL, {"frozen": frozen, "ws": ws}).fetchone()[0]


COUNTERS = {"landing_pages_booked_bad_file": landing_pages_booked_bad_file}
REPORTED = {"bronze_landing_unconverted": bronze_landing_unconverted, "manual_step_rows": manual_step_rows,
            "landing_pages_after_stage_c": landing_pages_after_stage_c}
#: The REPORTED names this module adds beyond the plan's (b) list (litkb_acceptance.HARDENING_REPORTED), each with its
#: reason; the harness prints a module's own reported counters after the plan's (builder A's `cassette_interactions`
#: is the precedent). Pinned by qc/test_litkb_landing.py::test_the_counter_module_names_only_plan_counters_and_every_fire_has_a_bound.
REPORTED_BEYOND_PLAN = {"landing_pages_after_stage_c": "auditor-C2b round 2 F1: the pages the gate leaves to a "
                                                       "stage the ladder runs after Stage C"}


def _pointer_word(carried):
    return "unreadable (counted: the gate fails closed)" if carried is None else carried


def _details_landing(conn, manifest):
    return [f"landing_pages_booked_bad_file: attempt {r[0]} work {r[4]} route {r[2]} at {r[3]} "
            f"pointer={_pointer_word(carried)} ({basis})"
            for r, carried, basis in landing_pages_unfollowed(conn, manifest, with_basis=True)]


def _details_after_stage_c(conn, manifest):
    root = _literature_root(manifest)
    out = []
    for r, carried, basis, after_c in _unfollowed(conn, manifest):
        if after_c:
            asked, why = _asked_by_stage_c(conn, manifest, r, root)
            out.append(f"landing_pages_after_stage_c: attempt {r[0]} work {r[4]} route {r[2]} at {r[3]} "
                       f"pointer={_pointer_word(carried)} ({basis}) asked_by_stage_c={asked} ({why})")
    return out


def _details_bronze(conn, manifest):
    return [f"bronze_landing: {r['doi']} {r['key']} landing={r['landing'] or 'none'} converted={r['converted']}"
            for r in bronze_rows(conn, manifest)]


DETAILS = {"landing_pages_booked_bad_file": _details_landing, "bronze_landing_unconverted": _details_bronze,
           "landing_pages_after_stage_c": _details_after_stage_c}


# ── the fires' world: a worker database only, recorded pages and CONSTRUCTED answers only ─────────
class World:
    """A workstream, a CONSTRUCTED admission and a writer session on a WORKER database (never `litkb`)."""

    def __init__(self, conn, workdir):
        from litkb.acquire.store import Store
        from litkb.db import connect as c

        dbname = conn.execute("SELECT current_database()").fetchone()[0]
        # BEGIN guard: a C2b fire runs only on a worker database
        if not c.is_test_db(dbname):
            raise RuntimeError(f"a C2b fire runs only on a litkb_test* worker database, not {dbname!r}")
        # END guard: a C2b fire runs only on a worker database
        self.owner, self.dbname = conn, dbname
        self.writer = c.connect(dbname, "litkb_test", autocommit=True)
        self.writer.execute("SET ROLE litkb_writer")
        self.workdir = Path(workdir)
        self.store = Store(self.workdir / "Lit", index_cache=self.workdir / "index.json")
        (self.store.root / "Validation").mkdir(parents=True, exist_ok=True)
        self.ws_id, self.token = conn.execute(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/c2b-fire', NULL, %s, NULL)",
            (f"c2b-{uuid.uuid4().hex[:10]}", "S4.5 builder C2b fire (worker database)")).fetchone()
        self.frozen = conn.execute("SELECT clock_timestamp()").fetchone()[0]

    def close(self):
        self.writer.close()

    def manifest(self):
        return {"frozen_at": self.frozen, "run_workstream_ids": [str(self.ws_id)],
                "literature_root": str(self.store.root)}

    def work(self, *, title, author, year=2023, venue=None, prefix="10.5555"):
        """A CONSTRUCTED registry admission (salted DOI and title; the evidence shape
        qc/test_litkb_p2.py::_good_payload uses) -> run.work_record's dict."""
        from psycopg.types.json import Jsonb

        from litkb.acquire import run

        hexid = uuid.uuid4().hex[:12]
        doi = f"{prefix}/c2b-fire-{hexid}"
        title = f"{title} {hexid}"
        ev = {"registry": "crossref", "registry_title": title, "registry_first_author": author, "registry_year": year,
              "claimed": {"title": title, "first_author": author, "year": year, "title_ratio": 1.0,
                          "author_match": True}}
        fields = {"type": "article", "title": title, "authors": [{"family": author, "given": "C."}], "year": year}
        if venue:
            fields["venue"] = venue
        cand = self.writer.execute(
            "SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
            (self.ws_id, self.token, title)).fetchone()[0]
        res = self.writer.execute(
            "SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, 'c2b-fire', 'c2b-fire-1')",
            (self.ws_id, self.token, cand, f"{author}_{year}_constructed-{hexid}", Jsonb(fields),
             Jsonb([{"scheme": "doi", "value": doi, "verified_by": "crossref", "evidence": ev}]), Jsonb({}))).fetchone()[0]
        if res.get("outcome") != "admitted":
            raise RuntimeError(f"the constructed admission was refused: {res}")
        return run.work_record(self.writer, work_id=res["work_id"])

    def acquire(self, work, clients, routes, **kw):
        from litkb.acquire import run
        from litkb.netutil import Pacer

        return run.acquire(self.writer, self.ws_id, self.token, work, store=self.store, agent="c2b-fire",
                           session="c2b-fire-1", clients=clients, routes=routes,
                           pacer=Pacer(interval=0, sleep=lambda s: None), printer=lambda *a, **k: None, pacing={}, **kw)

    def rows(self, work):
        return self.owner.execute(
            "SELECT route, status, sub_status, detail FROM litkb.acquisition_attempts WHERE work_id = %s ORDER BY at, id",
            (work["work_id"],)).fetchall()

    def holds_file(self, work):
        return self.owner.execute("SELECT count(*) FROM litkb.main_files WHERE work_id = %s AND status = 'active'",
                                  (work["work_id"],)).fetchone()[0] > 0


@contextlib.contextmanager
def _no_email():
    """The fires never read Kam's Unpaywall email: the lookup is asked with a constructed address."""
    from litkb.acquire import open_access
    with mock.patch.object(open_access, "unpaywall_email", lambda: "c2b-fire@example.invalid"):
        yield


def _unpaywall(urls):
    """A CONSTRUCTED Unpaywall v2 record listing `urls` as OA locations (the record's own field names)."""
    return (200, {"Content-Type": "application/json"},
            json.dumps({"is_oa": True, "oa_status": "bronze",
                        "oa_locations": [{"url": u, "host_type": "publisher"} for u in urls]}).encode())


def _world(conn, workdir):
    return World(conn, workdir)


def salted(body):
    """REAL recorded bytes with a trailing HTML comment naming this call (the `queue_fire._salt` precedent): a
    worker database is shared by a pytest session, and litkb's rejected-hash lookup rightly refuses to quarantine
    the same bytes twice, so each arm is served fresh bytes. Nothing a rule or the classifier reads changes."""
    return (body or b"") + f"\n<!-- c2b fire salt {uuid.uuid4().hex} -->\n".encode() if body else body


def _salted_answers(answers):
    return {u: (st, hd, salted(b)) for u, (st, hd, b) in answers.items()}


# ── the fires' own counters (not plan (b) names: each fire carries its bound, the bom_repair precedent) ────
_LANDING_HTML_BAD_FILE_SQL = """
SELECT count(*) FROM litkb.acquisition_attempts
 WHERE route = 'landing' AND status = 'bad-file' AND sub_status = 'html_response'
   AND at > %(frozen)s AND workstream_id::text = ANY(%(ws)s)
"""


def landing_html_booked_bad_file(conn, manifest):
    """`landing` attempts that SPENT an HTML answer and booked it `bad-file/html_response` — a refusal the Range
    probe exists to type as `blocked` before the body is spent (plan item 5: "Before spending anything, the 4 KB
    Range probe types a refusal into the blocked sub-statuses")."""
    frozen, ws = _scope(manifest)
    return conn.execute(_LANDING_HTML_BAD_FILE_SQL, {"frozen": frozen, "ws": ws}).fetchone()[0]


_MDPI_SQL = """
SELECT a.work_id::text,
       bool_or(a.status IN ('ok', 'measured')) AS converted
  FROM litkb.acquisition_attempts a
 WHERE a.route = 'landing' AND a.at > %(frozen)s AND a.workstream_id::text = ANY(%(ws)s)
   AND EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(a.detail -> 'landing' -> 'rules', '[]'::jsonb)) r
                WHERE r ->> 'id' = 'mdpi')
 GROUP BY a.work_id
"""


def mdpi_landings_unconverted(conn, manifest):
    """Works Stage C asked under the MDPI rule in the run that it did not convert (a `landing` ok, or `measured`)."""
    frozen, ws = _scope(manifest)
    return sum(1 for _w, conv in conn.execute(_MDPI_SQL, {"frozen": frozen, "ws": ws}).fetchall() if not conv)


_CHALLENGE_SQL = """
SELECT a.id::text, a.sub_status, a.terminal_status_code, a.terminal_url, a.detail ->> 'quarantined'
  FROM litkb.acquisition_attempts a
 WHERE a.route = 'landing' AND a.status = 'blocked' AND a.at > %(frozen)s AND a.workstream_id::text = ANY(%(ws)s)
   AND a.detail ->> 'quarantined' IS NOT NULL
"""


def landing_challenges_mistyped(conn, manifest):
    """`landing` blocked attempts whose KEPT body carries a challenge signature by an oracle outside the landing
    rung (litkb.acquire.ledger.challenge_cause over the bytes, and netutil.Client.is_challenge) but whose sub-status
    is not `challenge_or_bot_check`. Reads the kept payload under `literature_root` (read-only)."""
    from litkb.acquire import ledger
    from litkb.acquire.store import LITERATURE_ROOT
    from litkb.netutil import Client

    frozen, ws = _scope(manifest)
    root = Path(manifest.get("literature_root") or LITERATURE_ROOT)
    n = 0
    for _id, sub, code, url, rel in conn.execute(_CHALLENGE_SQL, {"frozen": frozen, "ws": ws}).fetchall():
        p = root / rel
        body = p.read_bytes() if p.is_file() else b""
        if (ledger.challenge_cause(body) or Client.is_challenge(code or 0, url or "", body)) \
                and sub != "challenge_or_bot_check":
            n += 1
    return n


# ── the fires ─────────────────────────────────────────────────────────────────────────────────
def fire_stage_c_disabled(conn, arm, workdir):
    """(c) "Stage C disabled on a page with citation_pdf_url -> landing_pages_booked_bad_file=1".
    The page: the REAL recorded Cambridge landing page (qc/fixtures/litkb_landing_pages/cambridge; it carries
    citation_pdf_url), served to open_access as the work's one OA location by a CONSTRUCTED Unpaywall record, so the
    ladder books it bad-file/html_response with the acceptance test's pdf_pointer fact. Control: the ladder WITH
    Stage C (a `landing` row follows it). Known-bad: the same ladder with the landing rung removed from the registry
    it is handed — Stage C disabled."""
    from litkb.acquire import run

    rec = load_recording("cambridge")
    page_url = rec["final"]["url"]
    w = World(conn, workdir)
    try:
        with _no_email():
            work = w.work(title="A constructed article whose landing page is a recorded Cambridge page",
                          author="Enamorado")
            answers = _salted_answers(recorded_answers(rec, rewrite_doi=(rec["doi"], work["doi"])))
            oa = FixtureClient(answers, prefixes={"https://api.unpaywall.org/": _unpaywall([page_url])})
            if arm == "control":
                w.acquire(work, {"open_access": oa, "landing": FixtureClient(answers)}, ("open_access", "landing"))
            else:
                w.acquire(work, {"open_access": oa}, ("open_access",),
                          rungs=[r for r in run.RUNGS if r.route != "landing"])
        return landing_pages_booked_bad_file(conn, w.manifest())
    finally:
        w.close()


def _mdpi_world(w, *, akamai):
    """The recorded MDPI row: Unpaywall's www.mdpi.com /pdf location answers the REAL kept Akamai page
    (qc/fixtures/litkb_mdpi_pdf_akamai_a3b93f589df6.html); the DOI resolves through the REAL recorded hops
    (qc/fixtures/litkb_landing_pages/mdpi: doi.org 302, www.mdpi.com 403 Akamai); the CDN URL answers a
    CONSTRUCTED paper of the work's own title and author (the grant covered no PDF endpoint; survey A6 MEASURED a
    real 200 application/pdf there for another rs DOI), honouring the Range probe (206, then 200)."""
    rec = load_recording("mdpi")
    work = w.work(title="A constructed remote sensing article on an MDPI row", author="Chen", venue="Remote Sensing")
    answers = _salted_answers(recorded_answers(rec, rewrite_doi=(rec["doi"], work["doi"])))
    pdf_url = "https://www.mdpi.com/2072-4292/15/3/765/pdf?version=1675838087"
    cdn = ("https://mdpi-res.com/d_attachment/remotesensing/remotesensing-15-00765/article_deploy/"
           "remotesensing-15-00765.pdf")
    paper = constructed_paper(work["title"], "Chen", salt=uuid.uuid4().hex[:8])
    answers[cdn] = _pdf_answer(paper)
    prefixes = {"https://www.mdpi.com/2072-4292/15/3/765/pdf": (403, {"Content-Type": "text/html"}, salted(akamai))}
    oa = FixtureClient(answers, prefixes=dict(prefixes, **{"https://api.unpaywall.org/": _unpaywall([pdf_url])}))
    return work, {"open_access": oa, "landing": FixtureClient(answers, prefixes=prefixes)}


def _without_candidate(rule_id, name):
    """The loaded rule table with ONE candidate of ONE rule removed (a deep copy; the module's table is restored
    when the patch ends)."""
    import copy

    from litkb.acquire import landing as L

    t = copy.deepcopy(L.TABLE)
    for rule in t["rules"]:
        if rule["id"] == rule_id:
            rule["candidates"] = [c for c in rule["candidates"] if c["name"] != name]
    return mock.patch.object(L, "TABLE", t)


def fire_mdpi_cdn_rule_disabled(conn, arm, workdir):
    """The MDPI CDN rule disabled on the recorded MDPI row -> not landed (counter mdpi_landings_unconverted: the
    control lands the CONSTRUCTED paper through the CDN rule, 0; the known-bad — the rule's `cdn` candidate removed
    from the loaded table — meets only www.mdpi.com's REAL Akamai answer and books blocked, 1)."""
    akamai = MDPI_AKAMAI_PDF.read_bytes()
    w = World(conn, workdir)
    try:
        with _no_email():
            work, clients = _mdpi_world(w, akamai=akamai)
            ctx = contextlib.nullcontext() if arm == "control" else _without_candidate("mdpi", "cdn")
            with ctx:
                w.acquire(work, clients, ("open_access", "landing"))
        return mdpi_landings_unconverted(conn, w.manifest())
    finally:
        w.close()


def _cambridge_paywall_world(w):
    """The paywalled Cambridge row: the DOI resolves through the REAL recorded hops to the REAL recorded landing page
    (it carries citation_pdf_url); the citation_pdf_url answers a 302 to that same landing page — CONSTRUCTED as a
    302, its TARGET MEASURED: phase4/qc/litkb_acq_probe_head.csv followed Enamorado_2019's citation_pdf_url to
    exactly the recorded page's URL (200 text/html). Every other URL is a 404."""
    rec = load_recording("cambridge")
    work = w.work(title="A constructed article on a paywalled Cambridge row", author="Enamorado")
    answers = _salted_answers(recorded_answers(rec, rewrite_doi=(rec["doi"], work["doi"])))
    page_url = rec["final"]["url"]
    pointer = ("https://www.cambridge.org/core/services/aop-cambridge-core/content/view/DB2955F64A1F4E262C5B9B26C6D755"
               "2E/S0003055418000783a.pdf/div-class-title-using-a-probabilistic-model-to-assist-merging-of-large-scale-"
               "administrative-records-div.pdf")
    answers[pointer] = (302, {"Location": page_url, "Content-Type": "text/html"}, b"")
    return work, {"landing": FixtureClient(answers)}


def fire_paywalled_probe_disabled(conn, arm, workdir):
    """A paywalled recorded page -> typed `html_or_reader` (or `identity_required`), never bound, never spent as a
    bad file (counter landing_html_booked_bad_file). Known-bad: the Range probe's typing disabled (every candidate
    answer read as a PDF, so the whole answer is spent) -> the landing page's HTML is booked bad-file/html_response
    by the acceptance test, 1."""
    from litkb.acquire import landing as L

    real = L.classify

    def untyped(*a, **k):
        if k.get("purpose", "candidate") == "candidate":
            return "pdf", "CONSTRUCTED known-bad: the probe's typing is disabled"
        return real(*a, **k)

    w = World(conn, workdir)
    try:
        work, clients = _cambridge_paywall_world(w)
        ctx = contextlib.nullcontext() if arm == "control" else mock.patch.object(L, "classify", untyped)
        with ctx:
            w.acquire(work, clients, ("landing",))
        return landing_html_booked_bad_file(conn, w.manifest())
    finally:
        w.close()


def fire_e13_challenge_rule_disabled(conn, arm, workdir):
    """E13's REAL recorded challenge bytes (qc/fixtures/litkb_e13_challenge_b65a33b17354.html: the 5,631-byte
    Cloudflare 'Just a moment...' page doi.org -> ACM served for 10.1145/3534678.3539043 at 403) as the landing page
    -> `challenge_or_bot_check`. Known-bad: the landing rung's challenge typing disabled -> booked
    `identity_required` (a 403 with no signature); counter landing_challenges_mistyped, whose oracle is C1a's
    ledger.challenge_cause over the kept bytes, not the rung."""
    from litkb.acquire import landing as L

    page = E13_FIXTURE.read_bytes()
    w = World(conn, workdir)
    try:
        work = w.work(title="A constructed proceedings paper behind E13's recorded challenge", author="Pfitzmann")
        landing = FixtureClient({L.doi_url(work["doi"]): (403, {"Content-Type": "text/html; charset=UTF-8"},
                                                           salted(page))})
        ctx = (contextlib.nullcontext() if arm == "control"
               else mock.patch.object(L, "_challenge", lambda *a, **k: ""))
        with ctx:
            w.acquire(work, {"landing": landing}, ("landing",))
        return landing_challenges_mistyped(conn, w.manifest())
    finally:
        w.close()


FIRES = {
    "stage_c_disabled": {"counter": "landing_pages_booked_bad_file", "run": fire_stage_c_disabled},
    "mdpi_cdn_rule_disabled": {"counter": "mdpi_landings_unconverted", "run": fire_mdpi_cdn_rule_disabled,
                               "bound": "=0"},
    "paywalled_probe_disabled": {"counter": "landing_html_booked_bad_file", "run": fire_paywalled_probe_disabled,
                                 "bound": "=0"},
    "e13_challenge_rule_disabled": {"counter": "landing_challenges_mistyped", "run": fire_e13_challenge_rule_disabled,
                                    "bound": "=0"},
}

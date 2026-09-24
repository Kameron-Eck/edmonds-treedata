r"""litkb S4.5 builder C2a — Stage A and Stage B's counters, fires and the run's measurement lines, for
`litkb_acceptance.py hardening` (brief-CONTRACTS.md "Counters and fires").

Loaded BY PATH (qc/instruments is not a package). It defines:

  COUNTERS  {gated counter name: fn(conn, manifest) -> int}     the plan's (b) names
  REPORTED  {reported counter name: fn(conn, manifest) -> int}  per-rung conversions, the kill criterion's gains
  FIRES     {fire name: {"counter": name, "run": fn(conn, arm, workdir) -> int}}

and, run as a script, prints the lines the LITKB_LADDER1 report carries for Stage B (builder A's grammar,
qc/instruments/litkb_hardening_a.py YIELD_LINE / NOT_BUILT_LINE, and S4.5 decision D19's identifiers line):

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_hardening_c2a.py --manifest <frozen manifest> \
        [--db litkb] [--role litkb_reader]
    yield: arxiv=<works converted>/<works asked>          a PDF-yielding Stage B rung
    identifiers: opencitations=<works gaining>/<asked>    a metadata-only rung (the registry's `metadata_only`)
    not-asked: zenodo <works reached> <condition>         a conditional rung its ask condition skipped on EVERY row
    not-built: core <reason>                              a Stage B route no rung registers
    kill: arxiv=<works gaining>/<asked> eligible=<n>      the fan-out's kill criterion, per scheme (below)

WHAT THIS MODULE COUNTS (docs/SCHEMAS.md, "S4.5 builder C2A", is the one home of each definition):

  GATED
  preprints_sent_to_shadow   RUN-SCOPED (S4.5 decision D1; attempts after `frozen_at` in `run_workstream_ids`):
                             attempts on a SHADOW route (`policy.STAGE_OF == "shadow"`: annas, scihub, bban) that
                             SPENT — status outside C1a's `backoff.NON_SPEND_STATUSES` (a recorded pre-fetch skip is
                             never a send: Codex X5) — for a work whose `main_works.type` is `preprint` OR whose
                             key or DOI the crosswalk probe CSV (`litkb_acq_probe_crosswalk.csv`, from the
                             manifest's `probe_csvs`) types `posted-content`. A manifest naming no crosswalk CSV is
                             REFUSED (the plan's definition has two halves; one alone would read low).
  free_ceiling_measured_unconverted  ALL-TIME: of the head probe CSV's `FREE-PDF` rows
                             (`litkb_acq_probe_head.csv`, from `probe_csvs`) and the Wayback positive row, the DOIs
                             whose work holds no HELD file — a `main_files` row whose status is `active` and whose
                             version was neither `rejected` nor `withdrawn` (auditor-C2a round 2 F6: a quarantined or
                             withdrawn file is no file) — a DOI no work holds counts: it holds no file. The
                             Wayback row is builder C2c's RE-GRADED positive (S4.5 decision D23: the plan's census.gov
                             capture of 10.1002/wics.1317 is another work; the IIASA copy of
                             10.5067/doc/ceoswgcv/lpv/lc.001 IS the work), read from C2c's `WAYBACK_ROWS`
                             (:func:`_wayback_positive`); the manifest key `wayback_positive_dois` overrides it. A row
                             the BINDER refused is a NAMED exception only when the report names it with its reason
                             (`exception:` lines, builder A's EXCEPTION_LINE) AND the ledger holds that binding refusal
                             (D11 / D23, integrator-w3); REPORTED `free_ceiling_named_exceptions` counts them.
  REPORTED
  rung_conversions_<route>   RUN-SCOPED: for each Stage A / Stage B route this builder registers, the works with an
                             `ok` (acquire) or `measured` (MEASURE mode, S4.5 decision D9) attempt on it — the
                             rung's yield read from ATTEMPT rows, never from a work's file state (brief-CONTRACTS.md:
                             3 of 4 FREE-PDF rows already hold a file from another route).
  kill_gain_<scheme>         RUN-SCOPED: for each scheme of the re-stated kill criterion (:data:`KILL_SCHEMES`),
                             the works that GAINED it in the run from a Stage B service — an identifier version or
                             an asserted edge whose target is that scheme, `asserted_by` a Stage B service.

THE FAN-OUT KILL CRITERION, re-stated against the schemes this corpus gains (plan item 4; LINKAGE §5.3 names
them: `arxiv pii dblp isbn md5`, NOT pmid/pmcid), as a measurable statement a NON-proposer scores — this builder
does not score it: per scheme, `gained / asked` over the run's asked works, beside `eligible` (the works the
crosswalk probe CSV says a service holds that scheme for: s2_arxiv, cr_alt_id-as-pii for Elsevier, s2_dblp,
cr_isbn; md5 has no probe column and reads eligible=n/a). The survey's S6 bar (LINKAGE §5.3: "if Wave 0 plus one
batched OpenAlex call does not fill ... for a majority of the DOI rows, the fan-out is not worth its
complexity"), re-applied per scheme, is the statement printed: KEEP if for at least one scheme gained exceeds
half of its eligible works; else KILL. That line is the PROPOSER'S bar applied mechanically, NOT a score
(auditor-C2a F13): the referee decides whether the bar is the right one and scores it. `md5` is STRUCTURALLY 0 in
this session — no Stage B service returns an md5 and Anna's `identifiers_unified` is not wired (builder-B1's open
question 1) — and a `kill-note:` line says so beside its `kill:` line.

Every mechanism is a RELAYED design (CLAUDE.md §3.4c), UNVALIDATED until an independent referee scores it on the
rows the plan names. Every fire's input is named for what it is: REAL recorded answers
(qc/fixtures/litkb_cassettes/stage_ab, recorded by qc/instruments/litkb_stage_ab_record.py under the brief's
grant) replayed through A's cassette with no socket, and CONSTRUCTED bytes where a file is needed (a PDF never
enters the repository). No fire touches the network.
"""
import argparse
import contextlib
import csv
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
FIXTURES = SCRIPTS / "qc" / "fixtures"
CASSETTE_INDEX = FIXTURES / "litkb_cassettes" / "stage_ab" / "index.jsonl"
HEAD_PROBE = "litkb_acq_probe_head.csv"
CROSSWALK_PROBE = "litkb_acq_probe_crosswalk.csv"

#: The plan's Wayback positive row (LITKB_WORKPLAN.md "### S4.5" test set; PDF-sources survey §M: "census.gov copy
#: archived 2021"; survey-data §2.2): the DOI, and the dead author copy the head probe CSV records for it.
#: S4.5 decision D23 (integrator-w3): the plan named the census.gov capture of 10.1002/wics.1317, and the recorded
#: truth re-graded it — that capture is ANOTHER work (a 38-page 1993 Census report, not the 13-page 2014 article),
#: and the IIASA copy of 10.5067/doc/ceoswgcv/lpv/lc.001 IS archived and IS the work. The grades have ONE home,
#: builder C2c's `WAYBACK_ROWS` (qc/instruments/litkb_hardening_c2c.py); this is its positive row, read from there.
WAYBACK_POSITIVE = None       # set below from litkb_hardening_c2c (loaded by path: qc/instruments is not a package)

#: The kill criterion's schemes (plan item 4; LINKAGE survey §5.3 via the plan: "arxiv, pii, dblp, isbn, md5").
KILL_SCHEMES = ("arxiv", "pii", "dblp", "isbn", "md5")
#: The crosswalk probe column that says a service HOLDS the scheme for a work (the kill criterion's `eligible`).
#: `pii` is Crossref's `alternative-id` on an Elsevier DOI (harvest.from_crossref's own rule: member 78 / 10.1016).
KILL_ELIGIBLE = {"arxiv": "s2_arxiv", "pii": "cr_alt_id", "dblp": "s2_dblp", "isbn": "cr_isbn"}

#: The Stage B services whose identifier rows and edges count as the fan-out's gain (`asserted_by` values).
STAGE_B_SERVICES = ("crossref", "openalex", "opencitations", "datacite", "pmc_idconv", "s2", "europepmc")


def _stage_b():
    from litkb.acquire import stage_b as B
    return B


def _load(stem):
    spec = importlib.util.spec_from_file_location(stem, SCRIPTS / "qc" / "instruments" / f"{stem}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _resolve(manifest, p):
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else Path((manifest or {}).get("repo") or REPO) / q


def _probe(manifest, name):
    return _resolve(manifest, ((manifest or {}).get("probe_csvs") or {}).get(name))


def _csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _scope(manifest):
    """-> (frozen_at, [workstream ids]) for a run-scoped counter; a manifest without them is refused (S4.5
    decision D1: an unscoped run counter would grade the ledger's whole history)."""
    frozen = (manifest or {}).get("frozen_at")
    ws = [str(w) for w in (manifest or {}).get("run_workstream_ids") or []]
    if not ws and (manifest or {}).get("workstream_id"):
        ws = [str(manifest["workstream_id"])]
    if not frozen or not ws:
        raise ValueError("a run-scoped counter needs manifest frozen_at and run_workstream_ids (S4.5 decision D1)")
    return frozen, ws


def _norm_doi(d):
    from litkb import identifiers as I
    return I.norm("doi", d or "")


# ── gated ────────────────────────────────────────────────────────────────────────────────────────
def shadow_routes():
    from litkb.acquire import policy as P
    return sorted(r for r, s in P.STAGE_OF.items() if s == "shadow")


def posted_content(manifest):
    """(keys, dois) the crosswalk probe CSV types `posted-content`; a manifest naming no such CSV is refused."""
    p = _probe(manifest, CROSSWALK_PROBE)
    if p is None or not p.is_file():
        raise ValueError(f"the manifest names no {CROSSWALK_PROBE}: the plan's preprint definition has two halves")
    rows = [r for r in _csv(p) if (r.get("cr_type") or "") == "posted-content"]
    return sorted({r["key"] for r in rows if r.get("key")}), sorted({_norm_doi(r["doi"]) for r in rows if r.get("doi")})


def preprints_sent_detail(conn, manifest):
    """[(attempt id, route, status, work key)] of the attempts `preprints_sent_to_shadow` counts."""
    from litkb.acquire import backoff as BO

    frozen, ws = _scope(manifest)
    keys, dois = posted_content(manifest)
    return conn.execute(
        "SELECT a.id::text, a.route, a.status, w.key FROM litkb.acquisition_attempts a "
        "  JOIN litkb.main_works w ON w.work_id = a.work_id "
        " WHERE a.at > %s AND a.workstream_id::text = ANY(%s) AND a.route = ANY(%s) AND a.status <> ALL(%s) "
        "   AND (w.type = 'preprint' OR w.key = ANY(%s) OR EXISTS (SELECT 1 FROM litkb.main_identifiers i "
        "        WHERE i.work_id = a.work_id AND i.scheme = 'doi' AND i.value_norm = ANY(%s))) "
        " ORDER BY a.at, a.id",
        (frozen, ws, shadow_routes(), sorted(BO.NON_SPEND_STATUSES), keys, dois)).fetchall()


def preprints_sent_to_shadow(conn, manifest):
    return len(preprints_sent_detail(conn, manifest))


def _wayback_positive():
    """(doi, url) of THE Wayback positive row: builder C2c's re-graded `WAYBACK_ROWS` (S4.5 decision D23)."""
    c2c = _load_sibling("litkb_hardening_c2c")
    (row,) = [r for r in c2c.WAYBACK_ROWS if r[3] == "positive"]
    return row[0], row[1]


def _load_sibling(stem):
    spec = importlib.util.spec_from_file_location(f"_{stem}_for_c2a", Path(__file__).resolve().parent / f"{stem}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def free_ceiling_rows(manifest):
    """The DOIs `free_ceiling_measured_unconverted` is over: the head probe CSV's FREE-PDF rows, then the Wayback
    positive row(s). The head CSV must be named (UNREAD otherwise); the census row must be in it."""
    p = _probe(manifest, HEAD_PROBE)
    if p is None or not p.is_file():
        raise ValueError(f"the manifest names no {HEAD_PROBE}")
    rows = _csv(p)
    free = sorted({_norm_doi(r["doi"]) for r in rows if r.get("verdict") == "FREE-PDF"})
    wayback = (manifest or {}).get("wayback_positive_dois")
    if wayback is None:
        doi, url = WAYBACK_POSITIVE or _wayback_positive()
        if not any(_norm_doi(r.get("doi")) == doi and r.get("url") == url for r in rows):
            raise ValueError(f"{HEAD_PROBE} carries no row for the Wayback positive {doi} {url}")
        wayback = [doi]
    return free + [d for d in (_norm_doi(x) for x in wayback) if d not in free]


def _unconverted(conn, manifest):
    """[(doi, work key or None)] of the free-ceiling DOIs still without a held file (`status` active, the version
    neither rejected nor withdrawn: a second session's refusal or the proposer's own withdrawal unmakes it)."""
    out = []
    for doi in free_ceiling_rows(manifest):
        row = conn.execute(
            "SELECT w.key, EXISTS (SELECT 1 FROM litkb.main_files f WHERE f.work_id = w.work_id AND f.status = 'active' "
            "                        AND f.state NOT IN ('rejected', 'withdrawn')) "
            "  FROM litkb.main_identifiers i JOIN litkb.main_works w ON w.work_id = i.work_id "
            " WHERE i.scheme = 'doi' AND i.value_norm = %s ORDER BY 2 DESC LIMIT 1", (doi,)).fetchone()
        if row is None or not row[1]:
            out.append((doi, row[0] if row else None))
    return out


#: The attempt statuses that are a BINDING refusal (litkb.acquire.run.land_and_attach: the bytes reached the binder and
#: it refused them) — what D11 / D23 make a NAMED exception of this counter, never a silent pass.
BINDING_REFUSALS = ("binding-failed", "binding-pending")

_BINDING_REFUSAL_SQL = """
SELECT a.status, a.route, a.detail->'binding'->'reasons', a.detail->'binding'->>'verdict', a.at
  FROM litkb.acquisition_attempts a JOIN litkb.main_identifiers i ON i.work_id = a.work_id
 WHERE i.scheme = 'doi' AND i.value_norm = %(doi)s AND a.status = ANY (%(st)s)
 ORDER BY a.at DESC, a.id DESC LIMIT 1
"""


def binding_refusal(conn, doi):
    """{status, route, reasons, verdict, at} of the latest BINDING refusal of the work holding `doi`, or None."""
    row = conn.execute(_BINDING_REFUSAL_SQL, {"doi": doi, "st": list(BINDING_REFUSALS)}).fetchone()
    if row is None:
        return None
    return {"status": row[0], "route": row[1], "reasons": row[2] or [], "verdict": row[3], "at": str(row[4])}


def free_ceiling_exceptions(conn, manifest):
    """[(doi, key, the report's reason, the binding refusal)] the counter EXCUSES: the report names the DOI with a
    reason (litkb_hardening_a.EXCEPTION_LINE) AND the database holds a binding refusal of its work (S4.5 decisions
    D11, D23). Integrator-w3."""
    named = _load_sibling("litkb_hardening_a").named_exceptions(manifest, "free_ceiling_measured_unconverted")
    out = []
    for doi, key in _unconverted(conn, manifest):
        refusal = binding_refusal(conn, doi)
        # BEGIN guard: a free-ceiling row is excused only when the report names it AND the binder refused its bytes
        if doi in named and refusal is not None:
            out.append((doi, key, named[doi], refusal))
        # END guard: a free-ceiling row is excused only when the report names it AND the binder refused its bytes
    return out


def free_ceiling_detail(conn, manifest):
    """[(doi, work key or None)] of the free-ceiling DOIs still without an active file and NOT a named exception."""
    excused = {e[0] for e in free_ceiling_exceptions(conn, manifest)}
    return [(doi, key) for doi, key in _unconverted(conn, manifest) if doi not in excused]


def free_ceiling_measured_unconverted(conn, manifest):
    return len(free_ceiling_detail(conn, manifest))


def free_ceiling_named_exceptions(conn, manifest):
    """REPORTED: the free-ceiling rows the counter excused as named binding refusals (never silent)."""
    return len(free_ceiling_exceptions(conn, manifest))


def free_ceiling_exception_lines(conn, manifest):
    """The `exception:` lines the LITKB_LADDER1 report carries for every unconverted free-ceiling DOI whose work the
    BINDER refused (read from the database; the report writer pastes them — it never composes a reason)."""
    lines = []
    for doi, key in _unconverted(conn, manifest):
        r = binding_refusal(conn, doi)
        if r is not None:
            why = "; ".join(str(x) for x in r["reasons"]) or r["verdict"] or r["status"]
            lines.append(f"exception: free_ceiling_measured_unconverted {doi} {r['status']} on {r['route']} "
                         f"({key or 'no key'}): {why}")
    return lines


# ── reported ─────────────────────────────────────────────────────────────────────────────────────
def built_routes():
    """The Stage A / Stage B routes this builder registers (litkb.acquire.stage_b.RUNG_TABLE, its one home)."""
    return [t[0] for t in _stage_b().RUNG_TABLE]


def rung_counts(conn, manifest, route):
    """(converted, asked) works for `route` in the run: asked = a work with an attempt that is not a skip or a
    budget row; converted = a work with an `ok` or `measured` attempt."""
    frozen, ws = _scope(manifest)
    asked, conv = conn.execute(
        "SELECT count(DISTINCT work_id) FILTER (WHERE status NOT IN ('skipped', 'budget-stop')), "
        "       count(DISTINCT work_id) FILTER (WHERE status IN ('ok', 'measured')) "
        "  FROM litkb.acquisition_attempts WHERE at > %s AND workstream_id::text = ANY(%s) AND route = %s",
        (frozen, ws, route)).fetchone()
    return int(conv or 0), int(asked or 0)


#: A skip row the rung's OWN ask condition wrote: the rung answered `skipped` with its condition in
#: `detail.policy.closure` (stage_b.closure_skip), or the ladder found none of the identifiers the rung needs
#: (`skipped/no_identifier` with `detail.needs`, C1a's `_skip_reason`). A skip by the pre-fetch POLICY (a refusal, a
#: back-off window, a dead route) is not one: it says nothing about the condition.
_CONDITION_SKIP = ("coalesce(status = 'skipped' AND ((coalesce(jsonb_typeof(detail -> 'policy'), '') = 'object' "
                   "AND (detail -> 'policy') ? 'closure') OR (sub_status = 'no_identifier' AND detail ? 'needs')), "
                   "false)")


def condition_skips(conn, manifest, route):
    """(works the run's `route` rows skipped by the rung's own ask condition, works it skipped for any OTHER reason)."""
    frozen, ws = _scope(manifest)
    by_cond, other = conn.execute(
        f"SELECT count(DISTINCT work_id) FILTER (WHERE {_CONDITION_SKIP}), "
        f"       count(DISTINCT work_id) FILTER (WHERE status = 'skipped' AND NOT ({_CONDITION_SKIP})) "
        "  FROM litkb.acquisition_attempts WHERE at > %s AND workstream_id::text = ANY(%s) AND route = %s",
        (frozen, ws, route)).fetchone()
    return int(by_cond or 0), int(other or 0)


def gained_works(conn, manifest, scheme):
    """Works that gained `scheme` in the run from a Stage B service (identifier version or asserted edge)."""
    frozen, ws = _scope(manifest)
    return conn.execute(
        "SELECT count(DISTINCT work_id) FROM ("
        "  SELECT v.work_id FROM litkb.identifier_versions v JOIN litkb.identifiers i ON i.id = v.identifier_id "
        "   WHERE i.scheme = %s AND v.created_at > %s AND v.workstream_id::text = ANY(%s) AND v.asserted_by = ANY(%s) "
        "  UNION ALL "
        "  SELECT r.work_id FROM litkb.work_relations r WHERE r.state = 'asserted' AND r.target_scheme = %s "
        "     AND r.created_at > %s AND r.workstream_id::text = ANY(%s) AND r.asserted_by = ANY(%s)) g",
        (scheme, frozen, ws, list(STAGE_B_SERVICES), scheme, frozen, ws, list(STAGE_B_SERVICES))).fetchone()[0]


def stage_b_asked_works(conn, manifest):
    frozen, ws = _scope(manifest)
    from litkb.acquire import policy as P

    b = sorted(r for r, s in P.STAGE_OF.items() if s == "B")
    return conn.execute(
        "SELECT count(DISTINCT work_id) FROM litkb.acquisition_attempts WHERE at > %s AND workstream_id::text = "
        "ANY(%s) AND route = ANY(%s) AND status NOT IN ('skipped', 'budget-stop')", (frozen, ws, b)).fetchone()[0]


def _conv(route):
    return lambda conn, manifest: rung_counts(conn, manifest, route)[0]


def _gain(scheme):
    return lambda conn, manifest: gained_works(conn, manifest, scheme)


# ── the report lines ─────────────────────────────────────────────────────────────────────────────
def eligible(manifest, scheme):
    """Works the crosswalk probe CSV says a service holds `scheme` for, among the run's rows when the manifest
    names them (`rows`), else the whole CSV; None when the CSV has no column for the scheme (md5)."""
    col = KILL_ELIGIBLE.get(scheme)
    p = _probe(manifest, CROSSWALK_PROBE)
    if not col or p is None or not p.is_file():
        return None
    rows = _csv(p)
    keys = {r.get("key") for r in (manifest or {}).get("rows") or [] if r.get("key")}
    if keys:
        rows = [r for r in rows if r.get("key") in keys]
    if scheme == "pii":
        return sum(1 for r in rows if (r.get(col) or "") and _norm_doi(r.get("doi")).startswith("10.1016/"))
    return sum(1 for r in rows if (r.get(col) or "").strip())


def report_lines(conn, manifest):
    """The Stage B lines of the LITKB_LADDER1 report (builder A's grammar + D19's identifiers line), then the kill
    criterion's per-scheme lines and its statement. Stage A routes print a yield line too (not graded by
    `stage_b_rungs_unmeasured`, which reads Stage B only). A rung the registry gives an `ask_condition` that asked
    NO row, reached at least one, and was skipped on every row it reached by that condition (`condition_skips`)
    ALSO prints `not-asked: <route> <works reached> <condition>` (auditor-C2a round 2 F3): its `=0/0` yield line
    asked nobody, and builder A's counter reads such a line as unmeasured — the not-asked line says why, in the
    registry's own words. Reached on no row, or skipped on one for another reason, it prints no such line."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    lines = []
    reg = {r.route: r for r in R.RUNGS}
    # this builder's rungs, then every OTHER registered Stage B rung (C1a's `open_access`): the report must measure
    # every built Stage B rung, whoever built it (builder A's `stage_b_rungs_unmeasured`)
    others = [r.route for r in R.RUNGS if r.stage == "B" and r.route not in built_routes()]
    for route in built_routes() + others:
        conv, asked = rung_counts(conn, manifest, route)
        # every built rung prints its yield line (builder A's `stage_b_rungs_unmeasured` reads that grammar; a
        # metadata-only rung's measured yield is zero files by construction), and a metadata-only rung ALSO its
        # identifiers line (S4.5 decision D19)
        lines.append(f"yield: {route}={conv}/{asked}")
        if getattr(reg.get(route), "metadata_only", False):
            lines.append(f"identifiers: {route}={identifiers_gaining(conn, manifest, route)}/{asked}")
        cond = getattr(reg.get(route), "ask_condition", "")
        if cond and asked == 0:
            reached, other = condition_skips(conn, manifest, route)
            # BEGIN guard: a not-asked line only for a rung its own ask condition skipped on every row it reached
            if reached >= 1 and other == 0:
                lines.append(f"not-asked: {route} {reached} {cond}")
            # END guard: a not-asked line only for a rung its own ask condition skipped on every row it reached
    for route in [r for r in P.ROUTES_ALL if P.STAGE_OF.get(r) == "B" and r not in reg]:
        lines.append(f"not-built: {route} {NOT_BUILT.get(route, 'no rung registers it in this session')}")
    asked = stage_b_asked_works(conn, manifest)
    keep = False
    for scheme in KILL_SCHEMES:
        g, e = gained_works(conn, manifest, scheme), eligible(manifest, scheme)
        lines.append(f"kill: {scheme}={g}/{asked} eligible={'n/a' if e is None else e}")
        keep = keep or (e is not None and e > 0 and g > e / 2)
    lines.append(f"kill-note: {STRUCTURAL_ZERO}")
    lines.append("kill-criterion: " + ("KEEP" if keep else "KILL") + " (the survey's S6 majority bar re-applied per "
                 "scheme: KEEP if gained > eligible/2 for at least one scheme — the proposer's bar applied "
                 "mechanically, NOT a score; a non-proposer scores it)")
    return lines


#: The kill criterion's scheme that cannot move in this session, and why (auditor-C2a F13).
STRUCTURAL_ZERO = ("md5 is structurally 0: no Stage B service returns an md5, and Anna's identifiers_unified (the one "
                   "md5 source, fetched at the archive's gate 2) is not written by the ladder (builder-B1 open question 1)")


def identifiers_gaining(conn, manifest, route):
    """Works that gained ANY identifier or edge from `route`'s service in the run (a metadata-only rung's yield)."""
    frozen, ws = _scope(manifest)
    service = {"opencitations": "opencitations", "ncbi-idconv": "pmc_idconv"}.get(route, route)
    return conn.execute(
        "SELECT count(DISTINCT work_id) FROM ("
        "  SELECT v.work_id FROM litkb.identifier_versions v WHERE v.created_at > %s AND v.workstream_id::text = "
        "ANY(%s) AND v.asserted_by = %s UNION ALL SELECT r.work_id FROM litkb.work_relations r WHERE r.created_at > "
        "%s AND r.workstream_id::text = ANY(%s) AND r.asserted_by = %s) g",
        (frozen, ws, service, frozen, ws, service)).fetchone()[0]


#: The Stage B routes of the vocabulary this builder does NOT register, and why (brief-CONTRACTS.md amendment:
#: "recorded NOT-BUILT with evidence").
NOT_BUILT = {"core": "CORE_API_KEY is blank in D:\\edmonds-pipeline\\secrets\\paper_search.env (read 2026-09-23) and "
                     "the PDF-sources survey measured CORE v3 unauthenticated as 429 / 404 (B7-RG): not askable "
                     "keyless"}


COUNTERS = {
    "preprints_sent_to_shadow": preprints_sent_to_shadow,
    "free_ceiling_measured_unconverted": free_ceiling_measured_unconverted,
}


def _reported():
    out = {"free_ceiling_named_exceptions": free_ceiling_named_exceptions}     # S4.5 D23 (integrator-w3)
    for t in _route_table():
        out[f"rung_conversions_{t}"] = _conv(t)
    for s in KILL_SCHEMES:
        out[f"kill_gain_{s}"] = _gain(s)
    return out


def _route_table():
    try:
        return built_routes()
    except Exception:                               # noqa: BLE001 — the package is not importable here: no rows
        return []


REPORTED = _reported()


# ── fires ────────────────────────────────────────────────────────────────────────────────────────
def no_misses(*clients):
    """A replay that MISSED is not the recorded world: the arm fails (an error, never a quiet api-error row)."""
    for c in clients:
        missed = list(getattr(getattr(c, "cassette", None), "misses", []) or [])
        if missed:
            raise RuntimeError(f"the replay missed {len(missed)} request(s): {missed[:2]}")


class ReplayClient:
    """A `netutil.Client` replaying `CASSETTE_INDEX` under one row tag, with CONSTRUCTED answers for the URLs that
    were never recorded (a PDF never enters the repository): `stubs` maps a URL fragment to (status, headers,
    body). A request neither answers raises the cassette's own CassetteMiss — never the network."""
    base = ""

    def __init__(self, row, stubs=None):
        from litkb import cassette as CAS
        from litkb.netutil import Client

        self.cassette = CAS.Cassette(CASSETTE_INDEX, "replay")
        self.cassette.begin_row(row)
        self.client = Client(base="", cassette=self.cassette)
        self.stubs, self.calls = dict(stubs or {}), []

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        self.calls.append(url)
        for frag, resp in self.stubs.items():
            if frag in url:
                return resp
        return self.client.get(url, accept=accept, timeout=timeout, follow=follow, data=data, headers=headers)


class World:
    """A workstream, REAL-row works admitted as CONSTRUCTED registry admissions, and a writer session, on a WORKER
    database (never `litkb`)."""

    def __init__(self, conn, workdir):
        from litkb.acquire.store import Store
        from litkb.db import connect as c

        dbname = conn.info.dbname
        # BEGIN guard: a C2a fire runs only on a worker database
        if not c.is_test_db(dbname):
            raise RuntimeError(f"a C2a fire runs only on a litkb_test* worker database, not {dbname!r}")
        # END guard: a C2a fire runs only on a worker database
        self.owner, self.dbname = conn, dbname
        self.writer = c.connect(dbname, "litkb_test", autocommit=True)
        self.writer.execute("SET ROLE litkb_writer")
        self.workdir = Path(workdir)
        self.store = Store(self.workdir / "Lit", index_cache=self.workdir / "index.json")
        (self.workdir / "Lit" / "Validation").mkdir(parents=True, exist_ok=True)
        self.tokens = {}

    def close(self):
        self.writer.close()

    def ws(self, slug):
        ws_id, token = self.owner.execute(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/c2a-fire', NULL, %s, NULL)",
            (f"c2a-{slug}-{uuid.uuid4().hex[:10]}", "S4.5 builder C2a fire (worker database)")).fetchone()
        self.tokens[ws_id] = token
        return ws_id

    def now(self):
        return self.owner.execute("SELECT clock_timestamp()").fetchone()[0]

    def admit(self, ws, row):
        """A REAL row's key, DOI, type, title and first author, admitted as a CONSTRUCTED registry admission (the
        registry answer is not asked: its fields are the live work's, :data:`ROWS`). -> run.work_record's dict."""
        from psycopg.types.json import Jsonb

        from litkb.acquire import run

        title, author, year = row["title"], row["author"], row["year"]
        ev = {"registry": "crossref", "registry_title": title, "registry_first_author": author, "registry_year": year,
              "claimed": {"title": title, "first_author": author, "year": year, "title_ratio": 1.0,
                          "author_match": True}}
        tok = self.tokens[ws]
        cand = self.writer.execute(
            "SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
            (ws, tok, title)).fetchone()[0]
        res = self.writer.execute(
            "SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, 'c2a-fire', 'c2a-fire-1')",
            (ws, tok, cand, row["key"],
             Jsonb({"type": row["type"], "title": title, "authors": [{"family": author, "given": "A."}],
                    "year": year}),
             Jsonb([{"scheme": "doi", "value": row["doi"], "verified_by": "crossref", "evidence": ev}]),
             Jsonb({}))).fetchone()[0]
        if res.get("outcome") != "admitted":
            raise RuntimeError(f"the CONSTRUCTED admission of {row['key']} was refused: {res}")
        return run.work_record(self.writer, work_id=res["work_id"])

    def acquire(self, ws, work, clients, **kw):
        from litkb.acquire import run
        from litkb.netutil import Pacer

        return run.acquire(self.writer, ws, self.tokens[ws], work, store=self.store, agent="c2a-fire",
                           session="c2a-fire-1", clients=clients, pacer=Pacer(interval=0, sleep=lambda s: None),
                           printer=lambda *a, **k: None, pacing={}, **kw)


#: The REAL rows the fires use: each work's key, DOI, type, title, first author and year as the LIVE base holds
#: them (read 2026-09-23 as litkb_reader; survey-data §2.1, §2.8, §2.9), admitted on the worker database as a
#: CONSTRUCTED registry admission. Their service answers are the RECORDED ones (CASSETTE_INDEX).
ROWS = {
    "kats": {"key": "Kats_2019_soft-staple-algorithm-combined", "doi": "10.1007/978-3-030-32248-9_57",
             "type": "chapter", "title": "A Soft STAPLE Algorithm Combined with Anatomical Knowledge",
             "author": "Kats", "year": 2019},
    "preprint": {"key": "DelgadoQuiros_2025_research-entity-information-coverage", "doi": "10.31235/osf.io/cxp4q",
                 "type": "preprint", "title": "Research entity information and coverage in eight free access "
                                              "scholarly databases", "author": "Delgado-Quirós", "year": 2025},
    "e13": {"key": "Pfitzmann_2022_doclaynet-large-human-annotated", "doi": "10.1145/3534678.3539043",
            "type": "proceedings", "title": "DocLayNet: A Large Human-Annotated Dataset for Document-Layout "
                                            "Segmentation", "author": "Pfitzmann", "year": 2022},
}


def row_tag(doi):
    """The recording's row tag (qc/instruments/litkb_stage_ab_record.py `tag`)."""
    return f"c2a:{doi}"


@contextlib.contextmanager
def _no_secrets_read():
    """A fire never reads Kam's configured email: the contact email is a constructed address (registered for
    redaction like the real one, so the replayed URL's masked key is the recorded one)."""
    from litkb.acquire import open_access
    with mock.patch.object(open_access, "unpaywall_email", lambda: "c2a-fire@example.invalid"):
        yield


def constructed_pdf(title, author):
    """A CONSTRUCTED one-page PDF whose first page prints `title` and `author` (qc/test_litkb_p2.py's
    `paper_pdf`: 44 body lines clear the acceptance test's 5,000-byte floor — integrator-w1's measurement)."""
    spec = importlib.util.spec_from_file_location("_c2a_p2", SCRIPTS / "qc" / "test_litkb_p2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.paper_pdf(title, author)


def _head_csv(workdir, doi):
    """A fire-local head probe CSV holding ONE real FREE-PDF row (the tracked CSV's own line for `doi`)."""
    src = REPO / "phase4" / "qc" / HEAD_PROBE
    rows = [r for r in _csv(src) if _norm_doi(r["doi"]) == _norm_doi(doi) and r.get("verdict") == "FREE-PDF"]
    if not rows:
        raise RuntimeError(f"{HEAD_PROBE} holds no FREE-PDF row for {doi}")
    out = Path(workdir) / HEAD_PROBE
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return out


# fire: the B1 rung disabled -> Kats_2019 -> free_ceiling_measured_unconverted > 0
def fire_b1_disabled_kats(conn, arm, workdir):
    """Kats_2019 (the one FREE-PDF row with no file) hunted through `s2` and `arxiv`: its RECORDED Semantic
    Scholar answer names arXiv 1910.12077 (openAccessPdf arxiv.org/pdf/1910.12077); the arXiv PDF is CONSTRUCTED
    (Kats' title and first author on its first page). Control: B1 follows the arXiv id and the file lands ->
    0. Known-bad: `stage_b.carried_files` answers nothing (B1 disabled) -> the work holds no file -> 1."""
    B = _stage_b()
    w = World(conn, workdir)
    try:
        with _no_secrets_read():
            ws = w.ws("b1-kats")
            work = w.admit(ws, ROWS["kats"])
            pdf = constructed_pdf(ROWS["kats"]["title"], ROWS["kats"]["author"])
            client = ReplayClient(row_tag(ROWS["kats"]["doi"]), stubs={"arxiv.org/pdf/": (200, {}, pdf)})
            patch = mock.patch.object(B, "carried_files", lambda *a, **k: []) if arm == "known_bad" \
                else contextlib.nullcontext()
            with patch:
                w.acquire(ws, work, {"s2": client, "arxiv": client}, routes=("s2", "arxiv"))
            no_misses(client)
        manifest = {"repo": str(REPO), "probe_csvs": {HEAD_PROBE: str(_head_csv(workdir, ROWS["kats"]["doi"]))},
                    "wayback_positive_dois": []}
        return free_ceiling_measured_unconverted(conn, manifest)
    finally:
        w.close()


def shadow_tier_on(policy_module):
    """The shadow tier's one switch pinned ON for the block (the router fire and its tests grade the ROUTER)."""
    return mock.patch.object(policy_module, "SHADOW_TIER_ENABLED", True)


def _stub_annas(work, ctx):
    """A CONSTRUCTED shadow rung standing in for the archive route: it answers a miss as the archive would, with
    no request — what the fire measures is whether the LADDER asked it at all."""
    return {"status": "not-in-archive", "sub_status": "not_in_corpus", "http_codes": [200],
            "terminal": {"url": "", "status_code": 200, "at": None}, "detail": "CONSTRUCTED shadow stub"}


# fire: the router disabled and a preprint hunted -> preprints_sent_to_shadow = 1
def fire_router_disabled_preprint(conn, arm, workdir):
    """DelgadoQuiros_2025 (a REAL `preprint`, 10.31235/osf.io/cxp4q) hunted through `osf` (its RECORDED OSF APIv2
    answers; the file download answered 404, CONSTRUCTED, so every legitimate rung misses) and a shadow rung (the
    registry's `annas` route with a CONSTRUCTED stub function). Control: Stage A's router refuses the shadow line
    for a preprint -> the annas row is `skipped/policy_refused` -> 0. Known-bad: the router disabled
    (`stage_a.routed` passes every decision) -> the shadow rung is asked -> 1. The shadow tier's switch is pinned
    ON in both arms (`shadow_tier_on`), whatever the process's `policy.SHADOW_TIER_ENABLED` says."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R
    from litkb.acquire import stage_a as A

    w = World(conn, workdir)
    try:
        # the shadow tier is PINNED ON for both arms (auditor-C2a F3): the live run switches it off
        # (`policy.SHADOW_TIER_ENABLED`, the scope ruling), and a fire that reached the shadow line through that
        # switch would grade the switch, not the router — with the tier off both arms read 0 (DID-NOT-FIRE)
        with _no_secrets_read(), shadow_tier_on(P):
            ws = w.ws("router")
            work = w.admit(ws, ROWS["preprint"])
            frozen = w.now()
            client = ReplayClient(row_tag(ROWS["preprint"]["doi"]), stubs={"://osf.io/": (404, {}, b"")})
            osf = next(r for r in R.RUNGS if r.route == "osf")
            rungs = [osf, R.Rung("annas", _stub_annas, needs=("doi",))]
            patch = mock.patch.object(A, "routed", lambda d, c: d) if arm == "known_bad" else contextlib.nullcontext()
            with patch:
                w.acquire(ws, work, {"osf": client}, routes=("osf", "annas"), rungs=rungs)
            no_misses(client)
        manifest = {"repo": str(REPO), "frozen_at": frozen, "run_workstream_ids": [ws],
                    "probe_csvs": {CROSSWALK_PROBE: str(REPO / "phase4" / "qc" / CROSSWALK_PROBE)}}
        return preprints_sent_to_shadow(conn, manifest)
    finally:
        w.close()


# fire: the harvest disabled and a crosswalk arXiv-id work re-hunted -> crosswalk_rows_without_identifier > 0
def fire_harvest_disabled_crosswalk(conn, arm, workdir):
    """E13 (Pfitzmann_2022, a REAL crosswalk arXiv-id work: the crosswalk probe gives it 2206.01062) re-hunted
    through `s2` on its RECORDED Semantic Scholar answer. Control: the ladder writes the harvest (an article's
    ArXiv is a `has_version` edge, builder-B1's `harvest.from_s2`) -> builder B1's
    `crosswalk_rows_without_identifier` over that one row -> 0. Known-bad: the ladder's harvest write disabled
    (`stage_b.write_harvest` writes nothing) -> 1."""
    B = _stage_b()
    B1 = _load("litkb_hardening_b1")
    w = World(conn, workdir)
    try:
        with _no_secrets_read():
            ws = w.ws("harvest")
            work = w.admit(ws, ROWS["e13"])
            client = ReplayClient(row_tag(ROWS["e13"]["doi"]))
            patch = mock.patch.object(B, "write_harvest", lambda *a, **k: None) if arm == "known_bad" \
                else contextlib.nullcontext()
            with patch:
                w.acquire(ws, work, {"s2": client}, routes=("s2",))
            no_misses(client)
        manifest = {"repo": str(REPO),
                    "probe_csvs": {CROSSWALK_PROBE: str(REPO / "phase4" / "qc" / CROSSWALK_PROBE)},
                    "rows": [{"key": ROWS["e13"]["key"], "source": ["crosswalk"]}]}
        return B1.crosswalk_rows_without_identifier(conn, manifest)
    finally:
        w.close()


FIRES = {
    "b1_disabled_kats": {"counter": "free_ceiling_measured_unconverted", "run": fire_b1_disabled_kats},
    "router_disabled_preprint": {"counter": "preprints_sent_to_shadow", "run": fire_router_disabled_preprint},
    "harvest_disabled_crosswalk_c2a": {"counter": "crosswalk_rows_without_identifier",
                                       "run": fire_harvest_disabled_crosswalk},
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="print the Stage A/B lines of the LITKB_LADDER1 report")
    ap.add_argument("--manifest", required=True, help="the frozen hardening manifest (frozen_at, run_workstream_ids)")
    ap.add_argument("--db", default="litkb")
    ap.add_argument("--role", default="litkb_reader")
    a = ap.parse_args(argv)
    import psycopg

    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    with psycopg.connect(f"host=localhost port=5433 dbname={a.db} user={a.role}") as conn:
        for line in report_lines(conn, manifest):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

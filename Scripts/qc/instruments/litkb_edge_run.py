r"""The edge-case run driver: every row of the register, resolved through `hunt`, one CSV row each.

    cd Scripts
    # live, in the worktree that holds the workstream token
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_edge_run.py \
        --manifest <frozen.json> [--only E07] [--redo E07]
    # deterministic, on a WORKER database, nothing reaching the network
    LITKB_TEST_DB=litkb_test_w10 PYTHONUTF8=1 PYTHONPATH=pipeline \
        py -3.12 qc/instruments/litkb_edge_run.py --manifest <frozen.json> --replay

WHAT IT IS, AND WHY IT IS NOT THE SCOUT DRIVER. `litkb_scout_run.py` follows up drop-offs a scout
left: its population is a database query and its ledger records ONE closed word per hunt
(`litkb.hunt.ledger_word`). This one drives a FIXED, adjudicated table —
`qc/fixtures/litkb_hunt_edge_cases.json`, one real carrier per edge class — and its ledger records
the STATE and the REASON as two columns, because the four states S3 added are only legible as a
pair: `api-error/registry-transient` and `api-error/route-raised` are the same word in a
one-column ledger and different problems for the operator (builder-A1.md §7.3).

A RAISE OUT OF `hunt()` IS THE DEFECT, NOT AN ACCIDENT. `hunt` promises a named result for every
reference it is given; the whole of S3 is that promise. So every call here is wrapped, a raise is
written into the row as `traceback=1` with the exception on it, and the grader
(`litkb_acceptance.py edges`) refuses the run for it. A driver that let an exception end the run
would report nothing at all for exactly the case the session exists to remove.

IDEMPOTENT AND RESUMABLE, the scout driver's rule: the CSV is the ledger, a row already in it is
never hunted again unless `--redo <ID>` names it. A live edge run spends on real routes and takes
minutes per row; a driver that redid its work after a crash would make the run unaffordable at
the moment it was already going badly.

`--replay` REPLACES THE WORLD, NOT THE ANSWER. Every row carries a `replay` block: a seed written
as FACTS into a freshly migrated worker database, a registry client, a fetch, an acquisition and
an extractor, each installed at the seam `qc/test_litkb_hunt.py` already uses for it. The hunt
itself is the real `litkb.hunt.hunt` and the state machinery under test is untouched. Nothing here
opens a socket, and the database name is refused if it is `litkb`.

WHERE THE REPLAY'S EXPECTATION MAY DIFFER FROM THE LIVE ONE. A freshly migrated database cannot
hold a precondition that only the live corpus has — E05's live answer turns on a PROPOSED work
admitted in another workstream months ago, which no seed can honestly reproduce. Such a row
carries `replay.expected`, which OVERRIDES `expected` for the replay alone; both are in the
register and both are graded, so the difference is a documented fact rather than a silent pass.

Stdlib plus the litkb package; the heavy imports are lazy. Not run on Colab.
"""
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
ACCEPTANCE = SCRIPTS / "qc" / "instruments" / "litkb_acceptance.py"
FIXTURES = SCRIPTS / "qc" / "fixtures"

#: The edge-run ledger. The scout ledger's shape widened where S3 widened the vocabulary: `state`
#: and `reason` are TWO columns for the observed answer and two for the expected one, and
#: `route_detail` carries what A1 added to `acquire()`'s return so a `blocked/403` row can be told
#: from a `blocked/challenge` row after the fact. Documented in `Scripts/docs/SCHEMAS.md`.
#:
#: ONE COLUMN BEYOND THE BRIEF'S LIST, and it is `report`. Three register rows (E04, E05, E06)
#: turn on facts `state` deliberately does not carry — did the work reach MAIN, and is the
#: admission a PROPOSAL — because A1's deviation 1 made `state` keep saying whether blocks exist
#: (builder-A1.md §5.1). Those facts live in the hunt result (`in_main` from `_report`,
#: `admission.outcome` from `_thin`) and in no other column here, so without `report` the grader
#: could read a row's `asserts` and check nothing: a gate that has never fired.
EDGE_CSV_COLUMNS = ("row_id", "class", "mode", "ref", "ref_scheme",
                    "expected_state", "expected_reason", "observed_state", "observed_reason",
                    "ok", "refusal_codes", "work_id", "admission_id", "file_id", "run_id",
                    "attempt_statuses", "route_detail", "new_admissions", "report", "seconds",
                    "traceback", "started_at", "message")

#: The live modes a register row may declare. `waits-on-migration` is NEVER written in the
#: fixture: it is DECIDED AT FREEZE by measuring `db_migration_tip` against the row's own
#: `needs_migration` (:func:`resolve_mode`). A hard-coded wait is a fact about one morning.
MODES = ("execute", "replay-only", "not-a-hunt", "held-for-ruling", "waits-on-migration")

#: A worker database, never the live one. `--replay` resets and migrates whatever it is given.
FORBIDDEN_REPLAY_DB = "litkb"


def _acceptance():
    """The sibling instrument, by path: `qc/instruments/` is deliberately not a package, so there
    is no import to make. One home for the manifest reader and the closed vocabulary."""
    spec = importlib.util.spec_from_file_location("litkb_acceptance", ACCEPTANCE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── the register ───────────────────────────────────────────────────────────────────────────

def load_register(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows_of(register):
    return list(register.get("rows") or [])


def is_held(row):
    """A row whose expected state only Kam can settle. It is NOT a manifest row."""
    return bool(row.get("held_for_ruling"))


def is_hunt_row(row):
    """Is this row a hunt at all? `not-a-hunt` records an instance the hunt vocabulary does not
    cover (E26, a scout-side tool fault) and must not be counted as one that was never run."""
    return not is_held(row) and (row.get("live") or {}).get("mode") != "not-a-hunt"


def resolve_mode(row, db_tip=None):
    """The mode this row runs in, MEASURED rather than declared where a migration is involved.

    A row that needs migration N is `waits-on-migration` while the database is below N and
    `execute` once it is not — decided here, at freeze, from `db_migration_tip`. An unreadable tip
    (`None`) is treated as unknown and the row WAITS, which is the safe direction: running a row
    whose route CHECK may not exist yet produces `acquisition-event-failed` and grades as a
    mismatch nobody caused."""
    if is_held(row):
        return "held-for-ruling"
    live = row.get("live") or {}
    mode = live.get("mode") or "execute"
    if mode == "not-a-hunt":
        return mode
    need = live.get("needs_migration")
    if need and mode == "execute":
        if db_tip is None or int(db_tip) < int(need):
            return "waits-on-migration"
    return mode


def expected_of(row, *, replay=False):
    """(state, reason) for this row, in this mode. See the module docstring on `replay.expected`."""
    exp = row.get("expected") or {}
    if replay:
        exp = ((row.get("replay") or {}).get("expected")) or exp
    return (exp.get("state") or ""), (exp.get("reason") or "")


# ── the CSV ────────────────────────────────────────────────────────────────────────────────

def existing_rows(path):
    p = Path(path)
    if not p.is_file():
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows):
    """Whole-file rewrite through a temp file, so an interrupted write cannot leave half a row in
    the ledger the next run resumes from (the scout driver's rule)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".partial")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(EDGE_CSV_COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in EDGE_CSV_COLUMNS})
    os.replace(tmp, path)


def read_edge_csv(path):
    """{row_id: row}. Duplicate row_ids keep the LAST, the way a redo replaces in place."""
    return {str(r.get("row_id", "")).strip(): r for r in existing_rows(path)}


def _observed(res):
    """The observed half of a CSV row, out of a hunt result dict."""
    acq = res.get("acquisition") or {}
    rep = {
        "observed_state": str(res.get("state") or ""),
        "observed_reason": str(res.get("reason") or ""),
        "ok": "true" if res.get("ok") else "false",
        "refusal_codes": ";".join(str(r.get("code") or "") for r in (res.get("refusals") or [])),
        "work_id": str(res.get("work_id") or ""),
        "admission_id": str((res.get("admission") or {}).get("admission_id") or ""),
        "file_id": str((res.get("admission") or {}).get("file_id")
                       or ((res.get("files") or [{}])[0] or {}).get("file_id") or ""),
        "run_id": str(res.get("run_id") or ""),
        "attempt_statuses": ";".join(f"{a[0]}:{a[1]}" for a in (acq.get("attempts") or [])
                                     if isinstance(a, (list, tuple)) and len(a) >= 2),
        "route_detail": json.dumps(acq.get("route_detail") or [], separators=(",", ":")),
        "report": json.dumps({"in_main": res.get("in_main"),
                              "admission_state": (res.get("admission") or {}).get("outcome"),
                              "blocks": res.get("blocks")}, separators=(",", ":")),
        "message": str(res.get("message") or "")[:500],
    }
    return rep


def _base_row(row, mode, *, replay=False):
    state, reason = expected_of(row, replay=replay)
    return {"row_id": row["id"], "class": row.get("class") or "", "mode": mode,
            "ref": row.get("ref") or "", "ref_scheme": row.get("ref_scheme") or "",
            "expected_state": state, "expected_reason": reason,
            "observed_state": "", "observed_reason": "", "ok": "", "refusal_codes": "",
            "work_id": "", "admission_id": "", "file_id": "", "run_id": "",
            "attempt_statuses": "", "route_detail": "", "new_admissions": "", "report": "",
            "seconds": "", "traceback": "0", "started_at": "", "message": ""}


def _call(hunt_fn, kwargs):
    """One hunt, with the boundary S3 exists to prove. -> (result_or_None, traceback_message)."""
    # BEGIN guard: a hunt that raises is a written row, never a dead run
    # `hunt` promises a named result for every reference it is given — that promise IS S3 — so a
    # raise out of it is the defect this register exists to catch. A driver that let the exception
    # end the run would report NOTHING for exactly the row that mattered, and the run would read
    # as incomplete rather than as failed.
    try:
        res = hunt_fn(**kwargs)
    except BaseException as e:            # noqa: BLE001 — a raise out of hunt() IS the defect
        return None, f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
    if not isinstance(res, dict):
        return None, f"hunt returned {type(res).__name__}, not a dict"
    return res, ""
    # END guard: a hunt that raises is a written row, never a dead run


# ── live execution ─────────────────────────────────────────────────────────────────────────

def _admission_count(db, role):
    from litkb.db import connect as c

    conn = c.connect(db, role, autocommit=True)
    try:
        return conn.execute("SELECT count(*) FROM litkb.admissions").fetchone()[0]
    finally:
        conn.close()


def run_execute(register, out_csv, *, db, worktree, agent, session, db_tip=None, only=None,
                redo=(), hunt=None, reader_role="litkb_reader", counter=None):
    """Every `execute` row of the register, through the real `hunt`. -> (written, resumed, rows).

    `counter` is the admissions-count reader, injected by the tests; the default opens a reader
    connection. It is what `new_admissions` is measured with — before and after each hunt, never
    an absolute count, because the live database is not this run's alone."""
    if hunt is None:
        import litkb.hunt as H
        hunt = H.hunt
    if counter is None:
        def counter():
            return _admission_count(db, reader_role)

    done = read_edge_csv(out_csv)
    redo = set(redo or ())
    only = set(only or ())
    written, n_new, n_resumed = [], 0, 0
    for row in rows_of(register):
        mode = resolve_mode(row, db_tip)
        if mode != "execute":
            continue
        rid = row["id"]
        if only and rid not in only:
            if rid in done:
                written.append(done[rid])
            continue
        if rid in done and rid not in redo:
            written.append(done[rid])
            n_resumed += 1
            continue
        out = _base_row(row, mode)
        live = row.get("live") or {}
        kwargs = {"ref": row["ref"], "ref_scheme": row.get("ref_scheme") or None,
                  "db": db, "worktree": worktree, "agent": agent, "session": session,
                  "spend": bool(live.get("spend"))}
        kwargs.update({k: v for k, v in ((row.get("live") or {}).get("inputs") or {}).items()})
        before = counter()
        t0 = time.monotonic()
        out["started_at"] = _utc_now_text()
        res, tb = _call(hunt, kwargs)
        out["seconds"] = round(time.monotonic() - t0, 2)
        out["new_admissions"] = max(0, counter() - before)
        if res is None:
            out["traceback"] = "1"
            out["message"] = tb
        else:
            out.update(_observed(res))
        written.append(out)
        n_new += 1
        write_csv(out_csv, written)         # after EVERY hunt: the ledger is the resume
    write_csv(out_csv, written)
    return n_new, n_resumed, written


def _utc_now_text():
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── the replay world ───────────────────────────────────────────────────────────────────────

_SUITE_LOCK = 0x6C6B7473        # "lkts" — qc/conftest.py::litkb_pg_base's lock, so a replay and a pytest session
                                # on the same worker database serialise instead of racing


def _pdf_bytes(title, author, salt="edge"):
    """A one-page text PDF pdftotext reads back — the SHAPE of `qc/test_litkb_p2.py::make_pdf`,
    reimplemented here rather than imported because an instrument that imports a test module
    inherits its fixtures and its collection. Generated rather than shipped as a binary so the
    title on page 1 is always the row's own: check 3 binds the CLAIMED title against that page,
    and one committed PDF could only ever satisfy one row."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = ["Journal of Synthetic Studies 1 (2020) 1-10", title, f"{author} and A. Coauthor", ""]
    lines += [f"Body text line {i} of a synthetic document, id {salt}." for i in range(8)]
    content = "BT /F1 9 Tf 40 760 Td 12 TL " + " ".join(f"({esc(ln)}) '" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1400 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(
        f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return out


HTML_BYTES = (b"<!DOCTYPE html>\n<html><head><title>Sign in</title></head>"
              b"<body>You must sign in to download this file.</body></html>\n" + b"x" * 400)


class _StatusRegistry:
    """A registry client that answers ONE status to everything — `qc/test_litkb_hunt.py`'s
    `_Status`, and `_NoNet` is its 404 twin."""

    base = ""

    def __init__(self, status):
        self.status, self.calls = int(status), []

    def get(self, url, *a, **kw):
        self.calls.append(url)
        return self.status, {}, b""


class _RecordRegistry:
    """Crossref `/works/<doi>` from ONE recorded record, 404 for everything else. The record's
    shape is `qc/test_litkb_p2.py::_synthetic`'s, which is what check 1 reads."""

    base = ""

    def __init__(self, doi, title=None, author="Tester", year=2020):
        self.doi = (doi or "").lower()
        self.record = {"DOI": doi, "title": [title or f"A synthetic registry record for {doi}"],
                       "author": [{"family": author, "given": "T.", "sequence": "first"}],
                       "issued": {"date-parts": [[year, 1]]}, "type": "journal-article",
                       "container-title": ["J. Synth."]}
        self.calls = []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        import urllib.parse

        self.calls.append(url)
        if "api.crossref.org/works/" in url:
            asked = urllib.parse.unquote(url.split("/works/", 1)[1]).lower()
            if asked == self.doi:
                return 200, {}, json.dumps({"message": self.record}).encode()
        return 404, {}, b""


class _BodyRegistry:
    """A frozen search body for `api.crossref.org/works?`, 404 elsewhere — `_CrossrefSearchStub`
    (`qc/test_litkb_hunt.py`), so the title gate is exercised against the response somebody
    actually recorded rather than against Crossref today."""

    base = ""

    def __init__(self, body):
        self.body, self.calls = body, []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        if "api.crossref.org/works?" in url:
            return 200, {}, self.body
        return 404, {}, b""


def _registry_stub(spec, row):
    kind = (spec or {}).get("kind") or "none"
    if kind == "none":
        return _StatusRegistry(404)
    if kind.startswith("status:"):
        return _StatusRegistry(kind.split(":", 1)[1])
    if kind == "record":
        return _RecordRegistry(row.get("ref"), title=f"A synthetic record for {row['id']}")
    if kind == "title_gate":
        fx = json.loads((FIXTURES / "litkb_title_gate_wrong_work.json").read_text(encoding="utf-8"))
        return _BodyRegistry(json.dumps(fx["crossref_search_body"]).encode("utf-8"))
    raise ValueError(f"litkb_edge_run: unknown registry stub {kind!r}")


def _fetch_stub(spec, row):
    kind = (spec or {}).get("kind") or "explode"
    if kind == "explode":
        def _explode(url, timeout=180):
            raise AssertionError(f"row {row['id']} fetched {url}: it was not supposed to reach "
                                 "the network at all")
        return _explode
    if kind == "html":
        return lambda url, timeout=180: (200, HTML_BYTES)
    if kind == "pdf":
        fx = (spec or {}).get("bytes_fixture")
        if fx:
            data = (FIXTURES / fx).read_bytes()
        else:
            inp = (row.get("replay") or {}).get("inputs") or {}
            data = _pdf_bytes(inp.get("title") or f"An edge-case document {row['id']}",
                              inp.get("author") or "Doe", salt=row["id"])
        return lambda url, timeout=180: (200, data)
    if kind.startswith("status:"):
        st = int(kind.split(":", 1)[1])
        return lambda url, timeout=180: (st, b"")
    raise ValueError(f"litkb_edge_run: unknown fetch stub {kind!r}")


def _acquirer_stub(spec):
    """A synthetic `acquire()` return, so the precedence rule is exercised on the route_detail the
    row records rather than on three live route calls."""
    outcome = spec.get("outcome") or "not-acquired"
    detail = list(spec.get("route_detail") or [])

    def _acquire(conn, ws_id, token, work, *, store, agent, session):
        return {"outcome": outcome,
                "attempts": [(d["route"], d["status"]) for d in detail],
                "route_detail": detail}
    return _acquire


def _real_oa_acquirer():
    """The REAL `acquire()` ladder restricted to open access — `qc/test_litkb_hunt.py`'s
    `_acquire_one_route`. Restricted because the other two routes are by DOI and would open a
    session against Anna's Archive: the guard under test is the route BOUNDARY."""
    def _acquire(conn, ws_id, token, work, *, store, agent, session):
        from litkb.acquire.run import acquire

        return acquire(conn, ws_id, token, work, store=store, agent=agent, session=session,
                       routes=("open_access",), printer=lambda *a, **k: None)
    return _acquire


def _extract_stub(spec):
    """-> a replacement for `litkb.hunt.extract_and_ingest`, or None to leave it alone.

    GROBID needs WSL and Docling needs a GPU; neither may run inside the gate, and a replay that
    ran them would be measuring the extractors rather than the state machinery. The stub returns
    the `(res, detail)` PAIR `litkb/hunt.py::_finish` reads, with `tei`/`docling` picking the
    reason — which is how `extracted/docling-only` becomes reachable at all."""
    kind = (spec or {}).get("kind") or "off"
    if kind in ("off", "real"):
        return None
    if kind.startswith("raise:"):
        exc = kind.split(":", 1)[1]

        def _boom(*a, **kw):
            # a two-line message on purpose: `crashed`'s REASON carries the class and the stage,
            # and the second line must never reach the result (hunt's crash boundary)
            raise _exception_class(exc)("the extractor died\n"
                                        "with a second line nobody should read in a result")
        return _boom
    if kind == "stub":
        tei, doc = bool(spec.get("tei", True)), bool(spec.get("docling", True))

        def _fake(db, file_id, pdf_path, *, timing, derived=None, device="cuda",
                  docling_python=None, grobid=True, progress=None):
            if progress is not None:
                progress["stage"] = "ingest"
            res = {"run_id": uuid.uuid4(), "inserted": 3, "blocks": 3, "disagreements": 0}
            detail = {"record": {"route": "native", "pages": 1, "sha256": uuid.uuid4().hex},
                      "stats": {"by_kind": {"paragraph": 3}, "matched": 3},
                      "coverage": {1: {"page_class": "native", "chars": 100, "covered": 95,
                                       "share": 0.95}},
                      "tei": tei, "docling": doc, "canonical": []}
            return res, detail
        return _fake
    raise ValueError(f"litkb_edge_run: unknown extract stub {kind!r}")


def _seed(conn, ws_id, spec, row):
    """A work written as FACTS through `litkb._write_version` — `qc/test_litkb_hunt.py`'s
    `seed_extracted`, and for the same reason it gives: a seed that ADMITTED its way to a rung
    would be testing admission, not the ladder. `state` picks the rung; `also` adds a second
    identifier on the same work (the alias class); `bytes_on_disk` writes real bytes where the
    seeded file row says they are, so a hunt reaches EXTRACTION rather than `file-missing`."""
    from psycopg.types.json import Jsonb

    def j(o):
        return Jsonb(o)

    # `works_key_check` is Author_Year_slug: the row id goes in the SLUG, not the year field
    key = f"Edge_2026_{row['id'].lower()}-{uuid.uuid4().hex[:8]}"
    work_id, _v = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, "
        "%s, NULL, %s, 'edge-seed', 'edge-seed')",
        (j({"key": key}),
         j({"type": "report", "title": f"A seeded edge-case work {row['id']}", "authors": [],
            "year": 2026}), ws_id)).fetchone()
    idents = [{"scheme": spec["scheme"], "value": spec["value"]}] + list(spec.get("also") or [])
    for ident in idents:
        conn.execute(
            "SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, "
            "NULL, %s, 'edge-seed', 'edge-seed')",
            (j({"scheme": ident["scheme"]}),
             j({"work_id": str(work_id), "value": ident["value"], "verified_by": "manual",
                "evidence": {}, "status": "active"}), ws_id))
    if spec.get("state") == "held":
        return {"key": key, "work_id": str(work_id)}
    rel = "Validation/seeded.pdf"
    file_id, _fv = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, "
        "%s, NULL, %s, 'edge-seed', 'edge-seed')",
        (j({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         j({"work_id": str(work_id), "status": "active", "rel_path": rel, "bytes": 2048,
            "pages": 1}), ws_id)).fetchone()
    if spec.get("state") == "bound-unextracted":
        return {"key": key, "work_id": str(work_id), "file_id": str(file_id)}
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, '5-reconcile', 'edge-seed', '0', %s, 'v0', "
        "'local', 'ok') RETURNING id", (file_id, uuid.uuid4().hex[:16])).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                 "VALUES (%s, %s, 1, 'heading', %s)",
                 (file_id, run_id, f"A seeded block for {row['id']}."))
    return {"key": key, "work_id": str(work_id), "file_id": str(file_id), "run_id": str(run_id)}


def replay_row(row, *, conn, db, tmp, hunt=None):
    """One register row, re-run against stubs on the worker database. -> the CSV row dict."""
    from litkb import workstream

    if hunt is None:
        import litkb.hunt as H
        hunt = H.hunt

    rp = row.get("replay") or {}
    inputs = dict(rp.get("inputs") or {})
    out = _base_row(row, "replay", replay=True)

    root = Path(tmp) / f"lit_{row['id']}"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    wt = Path(tmp) / f"wt_{row['id']}"
    wt.mkdir(parents=True, exist_ok=True)
    ws_id = workstream.open_workstream(conn, f"edge-{row['id'].lower()}-{uuid.uuid4().hex[:6]}",
                                       "edge-replay", f"S3 edge replay {row['id']}", directory=wt)

    seed = rp.get("seed")
    if seed:
        _seed(conn, str(ws_id), seed, row)
        if seed.get("bytes_on_disk"):
            (root / "Validation" / "seeded.pdf").write_bytes(
                _pdf_bytes(f"A seeded edge-case work {row['id']}", "Doe", salt=row["id"]))

    from litkb.acquire.store import Store

    kwargs = {"ref": row["ref"], "ref_scheme": row.get("ref_scheme") or None,
              "db": db, "worktree": wt, "agent": "edge-replay",
              "session": f"edge-replay-{row['id']}",
              "reader_role": "litkb_test", "writer_role": "litkb_test",
              "store": Store(root=root, index_cache=Path(tmp) / f"index_{row['id']}.json"),
              "derived": str(Path(tmp) / f"derived_{row['id']}"),
              "registry_client": _registry_stub(rp.get("registry"), row),
              "fetch": _fetch_stub(rp.get("fetch"), row),
              "spend": bool(inputs.get("spend")),
              "pacer": _no_wait_pacer()}
    for k in ("title", "author", "year", "extract", "key"):
        if k in inputs:
            kwargs[k] = inputs[k]

    routes = rp.get("routes") or {}
    rkind = routes.get("kind") or "none"
    if rkind == "acquirer":
        kwargs["acquirer"] = _acquirer_stub(routes)
    elif rkind == "real-oa-raises":
        kwargs["acquirer"] = _real_oa_acquirer()

    # A PROPOSAL IN ANOTHER WORKSTREAM CANNOT BE SEEDED AS A FACT. `_write_version('fact', …)`
    # writes a promoted row every view can see, which is the opposite of what E04 is about. The
    # only honest way to put a PROPOSED identifier in a workstream this hunt is not in is to make
    # one the way the corpus made its own: hunt the same reference there first, with the same
    # stubs. The graded hunt then meets check 2's GLOBAL identifier lookup (0013_admission.sql),
    # exactly as the live row will.
    pre = rp.get("pre_hunt")
    if pre:
        other = Path(tmp) / f"wt_{row['id']}_other"
        other.mkdir(parents=True, exist_ok=True)
        other_root = Path(tmp) / f"lit_{row['id']}_other"
        (other_root / "Validation").mkdir(parents=True, exist_ok=True)
        workstream.open_workstream(
            conn, f"edge-{row['id'].lower()}-other-{uuid.uuid4().hex[:6]}", "edge-replay",
            f"S3 edge replay {row['id']} (the workstream that holds it)", directory=other)
        pre_kwargs = dict(kwargs)
        pre_kwargs.update({
            "worktree": other, "session": f"edge-replay-{row['id']}-other",
            "store": Store(root=other_root,
                           index_cache=Path(tmp) / f"index_{row['id']}_other.json"),
            "registry_client": _registry_stub(rp.get("registry"), row),
            "fetch": _fetch_stub(rp.get("fetch"), row)})
        pre_res, pre_tb = _call(hunt, pre_kwargs)
        want = pre.get("expect_state")
        got = (pre_res or {}).get("state")
        if pre_tb or (want and got != want):
            out["traceback"] = "1"
            out["message"] = (f"the preparatory hunt for {row['id']} ended {got}/"
                              f"{(pre_res or {}).get('reason')} not {want}: {pre_tb}")[:500]
            return out

    patches = []
    extract = _extract_stub(rp.get("extract"))
    if extract is not None:
        patches.append(mock.patch("litkb.hunt.extract_and_ingest", extract))
    if rkind == "real-oa-raises":
        exc = routes.get("exception") or "ConnectionResetError"

        def _raise(*a, **kw):
            raise _exception_class(exc)("the peer reset the connection mid-body")
        patches.append(mock.patch("litkb.acquire.open_access.fetch_open_access", _raise))

    # every admission on this database is this replay's, so before/after is the honest measure
    before = conn.execute("SELECT count(*) FROM litkb.admissions").fetchone()[0]
    t0 = time.monotonic()
    out["started_at"] = _utc_now_text()
    try:
        for p in patches:
            p.start()
        res, tb = _call(hunt, kwargs)
    finally:
        for p in reversed(patches):
            p.stop()
    out["seconds"] = round(time.monotonic() - t0, 2)
    out["new_admissions"] = max(
        0, conn.execute("SELECT count(*) FROM litkb.admissions").fetchone()[0] - before)
    if res is None:
        out["traceback"] = "1"
        out["message"] = tb
    else:
        out.update(_observed(res))
    return out


def _exception_class(name):
    import builtins

    cls = getattr(builtins, name, None)
    return cls if isinstance(cls, type) and issubclass(cls, BaseException) else RuntimeError


def _no_wait_pacer():
    from litkb.netutil import Pacer

    return Pacer(interval=0, sleep=lambda s: None)


def run_replay(register, out_csv, *, db, tmp, only=None, hunt=None, db_tip=None, conn=None):
    """Every non-held, hunt-shaped row, on a WORKER database.

    `conn` IS NOT AN OPTIMISATION — IT IS THE DEADLOCK. `qc/conftest.py`'s `litkb_pg_base` resets
    and migrates the worker database ONCE per pytest session and then HOLDS
    `pg_advisory_lock(0x6C6B7473)` on its own connection for the rest of it. A Postgres advisory
    lock is SESSION-scoped, so this function opening a second connection and asking for the same
    lock waits on a session that will not let go until pytest exits: measured 2026-09-21, a
    combined run of `test_litkb_acceptance.py` and `test_litkb_edges.py` hung with no output and
    had to be killed. Called from a test this takes that fixture's OWN connection and neither
    locks nor resets — the fixture already did both, and a reset mid-session would delete the rows
    every other litkb module had seeded. Called from the CLI it owns the database and does both."""
    # BEGIN guard: the replay refuses the live database before it opens a connection
    # `migrate.reset` DROPS the schema. Pointed at `litkb` this would destroy the knowledge base,
    # and the thing standing between the two is one environment variable an operator sets by hand.
    if str(db).strip().lower() == FORBIDDEN_REPLAY_DB:
        raise SystemExit("litkb_edge_run --replay resets and migrates its database: it refuses "
                         f"{FORBIDDEN_REPLAY_DB!r}. Set LITKB_TEST_DB to a worker database.")
    # END guard: the replay refuses the live database before it opens a connection
    from litkb.db import connect as c
    from litkb.db import migrate

    own = conn is None
    conn = conn or c.connect(db, "litkb_test", autocommit=True)
    written = []
    try:
        if own:
            conn.execute("SELECT pg_advisory_lock(%s)", (_SUITE_LOCK,))
            migrate.reset(conn)
            migrate.apply(conn)
        only = set(only or ())
        for row in rows_of(register):
            if not is_hunt_row(row):
                continue
            if only and row["id"] not in only:
                continue
            written.append(replay_row(row, conn=conn, db=db, tmp=tmp, hunt=hunt))
            write_csv(out_csv, written)
    finally:
        if own:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (_SUITE_LOCK,))
            except Exception:               # noqa: BLE001 — a closed connection unlocks itself
                pass
            conn.close()
    write_csv(out_csv, written)
    return len(written), 0, written


# ── CLI ────────────────────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="drive every row of the edge-case register through hunt, one CSV row each")
    ap.add_argument("--manifest", required=True, help="the manifest frozen before the run")
    ap.add_argument("--only", action="append", default=[], help="run only this row id (repeatable)")
    ap.add_argument("--redo", action="append", default=[],
                    help="hunt this row again although the CSV already holds it (repeatable)")
    ap.add_argument("--replay", action="store_true",
                    help="deterministic re-run on LITKB_TEST_DB with every route stubbed")
    ap.add_argument("--out", default=None,
                    help="the CSV (default: the manifest's own run_csv, or replay_csv)")
    ap.add_argument("--agent", default="edge-run")
    ap.add_argument("--session", default=None)
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)

    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    register = load_register(manifest["fixture"])
    out = a.out or (manifest["replay_csv"] if a.replay else manifest["run_csv"])
    if a.replay:
        import tempfile

        db = os.environ.get("LITKB_TEST_DB") or "litkb_test"
        with tempfile.TemporaryDirectory(prefix="litkb-edge-replay-") as tmp:
            n, skipped, rows = run_replay(register, out, db=db, tmp=tmp, only=a.only)
    else:
        n, skipped, rows = run_execute(
            register, out, db=manifest["db"], worktree=manifest.get("worktree") or manifest["repo"],
            agent=a.agent, session=a.session or f"edge-run-{manifest['frozen_at']}",
            db_tip=manifest.get("db_migration_tip"), only=a.only, redo=a.redo,
            reader_role=manifest.get("reader_role") or "litkb_reader")
    pairs = {}
    for r in rows:
        k = f"{r['observed_state']}/{r['observed_reason']}" if r.get("observed_state") else "TRACEBACK"
        pairs[k] = pairs.get(k, 0) + 1
    print(f"hunted={n} resumed={skipped} rows={len(rows)} out={out}")
    print(" ".join(f"{k}={v}" for k, v in sorted(pairs.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""`litkb hunt` — the four kills the one-shot entry point has to survive.

TARGETED, AND SAID SO. This is not the P5/P8 treatment: there is no gate here, no round trip
through a real MCP session, and no end-to-end hunt of a real document in the suite. Four things
are asserted, each one a guard that has a mutation row beside it
(`qc/instruments/litkb_p2_mutations.py`, rows H1-H3):

  1. a URL that serves HTML is refused `not-a-pdf`, and the bytes are KEPT in `_quarantine/`
     with a `.reason.json` beside them — never deleted, which is what made the 2026-09-15
     incident unrecoverable rather than merely wrong;
  2. a second hunt of the same URL answers `already-extracted` from the database, having
     fetched nothing: the injected fetch RAISES, so a hunt that reached it fails the test;
  3. a hunt in a worktree with no `.litkb-workstream` is refused before any connection opens;
  4. a DOI hunt for a work that is already extracted returns `extracted` with no new run.

2 and 4 are the same guard read through the two kinds of reference, and they are separate tests
because the identifier LOOKUP is the part that differs — `norm_identifier` treats a DOI and a URL
differently, and a ladder that worked for one and not the other would look like a working ladder.

Run:
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w1 py -3.12 -m pytest qc/test_litkb_hunt.py
"""
import json
import uuid
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

HTML = (b"<!DOCTYPE html>\n<html><head><title>Sign in</title></head>"
        b"<body>You must sign in to download this file.</body></html>\n" + b"x" * 400)


def _jsonb(obj):
    from psycopg.types.json import Jsonb
    return Jsonb(obj)


@pytest.fixture
def env(tmp_path, monkeypatch, litkb_pg_base):
    """A literature root, a worktree with a real workstream, and the throwaway database.

    The `litkb_test` login stands in for reader, writer and ingest — it is a member of all three
    WITH INHERIT FALSE, which is how the P1 and P8 suites already exercise every role without a
    second set of credentials — so nothing here can reach `litkb`."""
    from litkb import workstream
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws_id = workstream.open_workstream(conn, f"hunt-{uuid.uuid4().hex[:8]}", "test", "hunt tests",
                                       directory=wt)
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt),
                 "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "hunt-test", "LITKB_SESSION": f"hunt-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    return {"conn": conn, "root": root, "wt": wt, "ws_id": str(ws_id), "db": c.DB_TEST,
            "tmp": tmp_path}


def _store(env):
    from litkb.acquire.store import Store

    return Store(root=env["root"], index_cache=env["tmp"] / "index.json")


def _hunt(env, ref, **kw):
    from litkb import hunt as H

    return H.hunt(ref, db=env["db"], worktree=env["wt"], agent="hunt-test",
                  session="hunt-test-session", reader_role="litkb_test",
                  writer_role="litkb_test", store=_store(env), derived=str(env["tmp"] / "derived"),
                  **kw)


def seed_extracted(conn, ws_id, scheme, value, *, text="A seeded block.", state="extracted"):
    """A work with an identifier, and — at `state="extracted"` — a bound file, an `ok` run and one
    block. `state="held"` stops after the identifier, which is the rung a DOI reaches when it is
    admitted and no PDF has been found for it.

    Written as FACTS through `_write_version`, the way `qc/test_litkb_p8.py::_seed_work_state`
    does: admission is one work per identifier across the whole knowledge base, and a test that
    admitted its way to this state would be testing admission, not the ladder."""
    key = f"Seeded_2026_hunt-{uuid.uuid4().hex[:8]}"
    work_id, _v = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, "
        "NULL, %s, 'hunt-seed', 'hunt-seed')",
        (_jsonb({"key": key}),
         _jsonb({"type": "report", "title": "A seeded hunt target", "authors": [], "year": 2026}),
         ws_id)).fetchone()
    conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, "
        "NULL, %s, 'hunt-seed', 'hunt-seed')",
        (_jsonb({"scheme": scheme}),
         _jsonb({"work_id": str(work_id), "value": value, "verified_by": "manual",
                 "evidence": {}, "status": "active"}), ws_id))
    if state == "held":
        return {"key": key, "work_id": str(work_id), "file_id": None, "run_id": None}
    file_id, _fv = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, "
        "NULL, %s, 'hunt-seed', 'hunt-seed')",
        (_jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         _jsonb({"work_id": str(work_id), "status": "active", "rel_path": "Validation/seeded.pdf",
                 "bytes": 2048, "pages": 3}), ws_id)).fetchone()
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, '5-reconcile', 'hunt-seed', '0', %s, 'v0', "
        "'local', 'ok') RETURNING id", (file_id, uuid.uuid4().hex[:16])).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                 "VALUES (%s, %s, 1, 'heading', %s)", (file_id, run_id, text))
    return {"key": key, "work_id": str(work_id), "file_id": str(file_id), "run_id": str(run_id)}


def _runs(conn):
    return conn.execute("SELECT count(*) FROM litkb.extraction_runs").fetchone()[0]


# ── kill 1: bytes that are not a PDF ──────────────────────────────────────────────────────

@pg_only
def test_a_url_that_serves_html_is_refused_and_the_bytes_are_quarantined(env):
    """Row H1. The shape check is on the BYTES, before anything reads them as a document.

    Without it the HTML lands under a PDF's name and the admission's check 3 tries to bind a
    title against a first page that does not exist — the 2026-09-15 incident, where 295,657 bytes
    of an error page were written as `IFLA_2017_library-reference-model.pdf` and then `rm -f`'d to
    free the name. Nothing is deleted here: the refusal names where the bytes went and why."""
    url = f"https://example.org/{uuid.uuid4().hex}.pdf"
    # BEFORE/after, never an absolute count: `litkb_test` is reset once per pytest SESSION and every
    # module in it shares the database, so `extraction_runs` is not empty when this test starts and
    # asserting it is measures the module order, not the guard.
    before = _runs(env["conn"])
    res = _hunt(env, url, fetch=lambda u, timeout=180: (200, HTML), key="Html_2026_not-a-paper")
    assert res["ok"] is False and res["refused"] == "not-a-pdf", res
    q = env["root"] / "_quarantine"
    kept = sorted(p.name for p in q.glob("Html_2026_not-a-paper__not-a-pdf__*"))
    assert len(kept) == 2, kept                       # the bytes, and the reason beside them
    why = json.loads(next(q.glob("*.reason.json")).read_text(encoding="utf-8"))
    assert why["shape"] == "not-a-pdf" and why["route"] == "hunt", why
    assert "they look like HTML" in why["reason"], why
    # nothing landed under a name a later pass would read as a paper
    assert not list((env["root"] / "_litkb_staging" / "filed").glob("*")), "an HTML body was filed"
    assert _runs(env["conn"]) == before


# ── kill 2 and 4: the database answers before anything is fetched ─────────────────────────

def _explode(url, timeout=180):
    raise AssertionError(f"a second hunt fetched {url}: the ladder did not short-circuit")


class _NoNet:
    """A registry client that opens no socket, so the mutation that removes the ladder's
    short-circuit (row H2) fails this test OFFLINE instead of querying Crossref for a made-up DOI.
    A mutation harness that reaches the network measures the network."""

    base = ""

    def get(self, url, *a, **kw):
        return 404, {}, b""


@pg_only
def test_a_second_hunt_of_the_same_url_is_already_extracted_and_fetches_nothing(env):
    """Row H2, through a URL. The injected fetch RAISES, so "no new run" is not the whole
    assertion: a hunt that got as far as the network fails outright."""
    url = f"https://example.org/{uuid.uuid4().hex}/doc.pdf"
    seeded = seed_extracted(env["conn"], env["ws_id"], "url", url, text="1 Architecture")
    before = _runs(env["conn"])
    res = _hunt(env, url, fetch=_explode)
    assert res["ok"] is True, res
    assert res["state"] == "extracted" and res["outcome"] == "already-extracted", res
    assert res["work_key"] == seeded["key"] and res["run_id"] == seeded["run_id"], res
    assert res["blocks"] == 1 and res["blocks_by_kind"] == {"heading": 1}, res
    assert res["headings"][0]["text"] == "1 Architecture", res
    assert _runs(env["conn"]) == before, "a second hunt opened an extraction run"


@pg_only
def test_a_doi_hunt_for_an_extracted_work_returns_extracted_with_no_new_run(env):
    """Row H2, through a DOI — the other half of the same guard. The lookup normalises through
    `litkb.norm_identifier`, so the hunted form may differ from the stored one (here a doi.org URL
    against a bare DOI) and still reach the same work."""
    doi = f"10.9999/hunt.{uuid.uuid4().hex[:10]}"
    seeded = seed_extracted(env["conn"], env["ws_id"], "doi", doi)
    before = _runs(env["conn"])
    res = _hunt(env, f"https://doi.org/{doi.upper()}", fetch=_explode, registry_client=_NoNet())
    assert res["ok"] is True and res["state"] == "extracted", res
    assert res["outcome"] == "already-extracted" and res["work_key"] == seeded["key"], res
    assert _runs(env["conn"]) == before


@pg_only
def test_a_doi_hunt_for_a_work_already_held_stops_at_held_and_admits_nothing_again(env):
    """The same guard's third rung, and the one that bites hardest if it is missing: a DOI that is
    ADMITTED with no bound file. Falling through re-admits a work the knowledge base already holds,
    and check 2 refuses it as a DUPLICATE — so a session that hunts the same DOI twice would be
    told, on the second call, that its own work belongs to somebody else. The right answer is the
    state it is in, with the next move (`litkb acquire`) in `refusals`.

    Passes spend=False: this row is about the DUPLICATE-ADMISSION guard, not the spend gate (rows
    below cover that), and a default-spending hunt with no acquirer stub would open a socket."""
    doi = f"10.9999/held.{uuid.uuid4().hex[:10]}"
    seeded = seed_extracted(env["conn"], env["ws_id"], "doi", doi, state="held")
    n = lambda: env["conn"].execute("SELECT count(*) FROM litkb.admissions").fetchone()[0]  # noqa: E731
    before = n()
    res = _hunt(env, doi, fetch=_explode, registry_client=_NoNet(), spend=False)
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-no-spend", res
    assert res["work_key"] == seeded["key"] and res["files"] == [], res
    assert [r["code"] for r in res["refusals"]] == ["no-spend"], res
    assert "--no-spend" in res["refusals"][0]["message"], res
    assert n() == before, "a hunt of an already-held DOI admitted it a second time"


# ── the spend rule (Kam, 2026-09-16 night; decisions.yaml litkb-p0-foundation): a hunt that ─────
# reaches `held` proceeds to acquisition BY DEFAULT; --no-spend / spend=False is the explicit
# exception. Row H5 (qc/instruments/litkb_p2_mutations.py): six DOI hunts died stuck at `held` on
# 2026-09-16 for lack of this rule, and it must fire both ways — a hunt told not to spend must
# never call acquisition, and a hunt that says nothing about it must.

def _acquire_explodes(conn, ws_id, token, work, *, store, agent, session):
    raise AssertionError("acquisition was attempted although spend=False")


def _acquire_recording(calls, outcome="not-acquired", attempts=None):
    def _acquire(conn, ws_id, token, work, *, store, agent, session):
        calls.append({"work_id": work["work_id"], "doi": work.get("doi"), "agent": agent,
                      "session": session})
        return {"outcome": outcome,
                "attempts": attempts or [("open_access", "no-oa-copy"),
                                         ("annas", "not-in-archive"),
                                         ("scihub", "not-in-archive")]}
    return _acquire


@pg_only
def test_no_spend_stops_at_held_and_never_calls_acquisition(env):
    """spend=False is a DELIBERATE, distinct stop: `held-no-spend`, code `no-spend` — never the
    same `held`/`no-file` symptom the six stuck 2026-09-16 hunts left behind, and the acquirer is
    never invoked (it would raise if it were)."""
    doi = f"10.9999/nospend.{uuid.uuid4().hex[:10]}"
    seed_extracted(env["conn"], env["ws_id"], "doi", doi, state="held")
    res = _hunt(env, doi, fetch=_explode, registry_client=_NoNet(), spend=False,
               acquirer=_acquire_explodes)
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-no-spend", res
    assert [r["code"] for r in res["refusals"]] == ["no-spend"], res
    assert "acquisition" not in res, res


@pg_only
def test_default_hunt_spends_by_calling_acquisition(env):
    """The DEFAULT (no `spend` kwarg at all — the CLI's own default): a `held` DOI proceeds to
    acquisition without being asked. The stub records that it was called and reports
    `not-acquired`, so the ladder's next rung (`held-spend-exhausted`) is also asserted."""
    doi = f"10.9999/spend.{uuid.uuid4().hex[:10]}"
    seed_extracted(env["conn"], env["ws_id"], "doi", doi, state="held")
    calls = []
    res = _hunt(env, doi, fetch=_explode, registry_client=_NoNet(),
               acquirer=_acquire_recording(calls))
    assert len(calls) == 1, "the default hunt did not spend: acquisition was never called"
    assert calls[0]["doi"] == doi, calls
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-spend-exhausted", res
    assert [r["code"] for r in res["refusals"]] == ["not-acquired"], res
    assert res["acquisition"]["outcome"] == "not-acquired", res
    assert res["acquisition"]["attempts"], res


def _p2_module():
    """qc/test_litkb_p2.py, loaded by path (it is not a package): `RegistryStub` and `_synthetic`
    build a Crossref-shaped record with no network, exactly as the existing web-source test above
    already does for `front`."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_p2", Path(__file__).with_name("test_litkb_p2.py"))
    p2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p2)
    return p2


@pg_only
def test_a_fresh_doi_admission_with_no_file_also_spends_by_default(env):
    """The OTHER place a hunt reaches `held` with no file: a DOI admitted for the FIRST time by
    this very call (not found already-held in the database). Same guard, the other call site."""
    p2 = _p2_module()
    doi, _title, rec = p2._synthetic()
    stub = p2.RegistryStub({doi: rec})
    calls = []
    res = _hunt(env, doi, fetch=_explode, registry_client=stub,
               acquirer=_acquire_recording(calls))
    assert res.get("admission", {}).get("outcome") == "admitted", res
    assert len(calls) == 1, "a freshly-admitted DOI with no file did not spend"
    assert calls[0]["doi"] == doi, calls
    assert res["ok"] is True and res["state"] == "held", res
    assert res["outcome"] == "held-spend-exhausted", res


def test_the_cli_default_spends_and_no_spend_threads_through(monkeypatch):
    """Row H6: the CLI's own default. No Postgres, no network — `commands.cmd_hunt` is exercised
    directly with `litkb.hunt.hunt` monkeypatched to capture the `spend` kwarg it was called
    with, so this is a fast unit test rather than a duplicate of the rows above."""
    from litkb import commands as C
    from litkb import hunt as H

    captured = []

    def fake_hunt(ref, **kw):
        captured.append(kw.get("spend"))
        return {"ok": True, "state": "held", "outcome": "held-spend-exhausted", "refusals": []}

    monkeypatch.setattr(H, "hunt", fake_hunt)
    rc1 = C.main(["hunt", "10.1/x"], connect=lambda db: C._NoConn())
    rc2 = C.main(["hunt", "10.1/x", "--no-spend"], connect=lambda db: C._NoConn())
    assert rc1 == 0 and rc2 == 0, (rc1, rc2)
    assert captured == [True, False], captured


def test_the_mcp_wrapper_threads_spend_to_no_spend_and_omits_it_by_default(tmp_path, monkeypatch):
    """Row H7: the MCP tool never re-decides spend, it threads it to the CLI subprocess it shells
    out to. No Postgres — `.litkb-workstream` is a plain JSON file `_session()` reads off disk,
    and `subprocess.run` is monkeypatched so nothing is ever actually launched."""
    from litkb.mcp import server as S

    # the token is armed process-wide by `_session()` -> `add_secret()` (netutil._SECRETS is a
    # module-level list nothing ever clears): a short, common token like "t" redacts every "t" in
    # EVERY later test's output for the rest of the pytest session, not just this test's. A
    # UUID-length token never collides with ordinary text.
    (tmp_path / ".litkb-workstream").write_text(
        json.dumps({"workstream_id": str(uuid.uuid4()), "token": uuid.uuid4().hex}),
        encoding="utf-8")
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = "{}"
            stderr = ""
        return R()

    monkeypatch.setattr(S.subprocess, "run", fake_run)
    S._hunt(ref="10.1/x")
    S._hunt(ref="10.1/x", spend=False)
    assert "--no-spend" not in calls[0], calls[0]
    assert "--no-spend" in calls[1], calls[1]


# ── kill 3: no workstream token ───────────────────────────────────────────────────────────

def test_a_hunt_with_no_workstream_token_is_refused_before_anything_opens(tmp_path):
    """Row H3. A hunt admits, binds and INGESTS, and all three name an open workstream and present
    its token. The refusal is made before the database, the network and the GPU are touched — the
    order matters, because the other two writes in this package are cheap and this one is not."""
    from litkb import hunt as H

    res = H.hunt("https://example.org/x.pdf", worktree=tmp_path, agent="a", session="s",
                 fetch=_explode, db="litkb_test")
    assert res["ok"] is False and res["refused"] == "no-workstream", res
    assert "ws open" in res["message"], res


@pg_only
@pytest.mark.parametrize("label", ["​​", "﻿", "  ⁠"],
                         ids=["zero_width", "bom", "nbsp_word_joiner"])
def test_a_label_of_invisible_characters_only_is_blank_and_the_hunt_is_refused(env, label):
    """Row H4. Every write records WHICH agent and WHICH session made it, and the manual-admission
    sign-off compares those labels — a web source is exactly such an admission. A label of
    invisible characters is TRUTHY, so a raw check passes it and two sessions can be spelled to
    look like one. The refusal lands before the store, the network and the GPU."""
    from litkb import hunt as H

    res = H.hunt(f"https://example.org/{uuid.uuid4().hex}.pdf", db=env["db"], worktree=env["wt"],
                 agent=label, session=label, reader_role="litkb_test", writer_role="litkb_test",
                 store=_store(env), fetch=_explode)
    assert res["ok"] is False and res["refused"] == "no-labels", res


def test_the_reference_kinds_are_told_apart_by_scheme():
    """A doi.org URL is a DOI, not a web source: the registry can confirm it, and admitting it as a
    manual proposal would put a registry-confirmable work behind a second session's sign-off.

    CHANGED 2026-09-20 (S1): `ref_kind` INFERS and may return None, where it used to CLASSIFY and
    returned 'doi' for anything that was not an http URL. The assertion that moved is
    `http://dx.doi.org/10.1/x`, which this test used to require to be a DOI: `10.1/x` has a
    one-digit registrant prefix and is not a DOI's shape (`^10.\\d{4,9}/\\S+` after normalisation).
    Nothing in the knowledge base carries such a form — it was a stand-in written short. The real
    doi.org form above is asserted unchanged, and the strict shape is what makes `malformed-ref`
    reachable at all."""
    from litkb import hunt as H

    assert H.ref_kind("10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("https://doi.org/10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("http://dx.doi.org/10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("https://raw.githubusercontent.com/a/b/Doc.pdf") == "url"
    assert H.ref_kind("arXiv:2106.15928v2") == "arxiv"
    assert H.ref_kind("math.GT/0309136") == "arxiv"
    assert H.ref_kind("http://dx.doi.org/10.1/x") is None
    assert H.ref_kind("see the attached spreadsheet, row 14") is None


def test_a_web_source_with_a_pdf_binds_the_pdf_and_keeps_the_snapshot(tmp_path):
    """`admit_web(pdf_path=…)` binds the DOCUMENT, not the saved page text.

    The evidence has to arrive with the admission: a manual admission is a proposal, main's
    pointer stays NULL until a second session approves it, and `litkb.attach_file` refuses a work
    that is not in main — so "admit the proposal, then acquire --from-file" cannot complete for a
    web source. This checks the Python half of that (the file JSON the admission is handed); the
    database half is migration 0013's own text."""
    import importlib.util

    from litkb.admit import front

    spec = importlib.util.spec_from_file_location("_p2", Path(__file__).with_name("test_litkb_p2.py"))
    p2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p2)
    root = tmp_path / "Literture"
    (root / "_litkb_staging" / "filed").mkdir(parents=True)
    pdf = root / "_litkb_staging" / "filed" / "Doe_2020_a-hunted-document.pdf"
    pdf.write_bytes(p2.paper_pdf("A Hunted Document", "Doe"))
    ev = front.web_pdf_evidence(pdf, "A Hunted Document", "Doe", url="https://example.org/d.pdf",
                                retrieved="2026-09-16", root=root)
    assert ev["binding"]["verdict"] == "bound", ev["binding"]
    assert ev["has_text_layer"] is True and ev["source_route"] == "web"
    assert ev["source_url"] == "https://example.org/d.pdf"
    assert ev["obtained_at"] == "2026-09-16"
    assert ev["rel_path"].endswith("Doe_2020_a-hunted-document.pdf")
    # 0020's copy_kind vocabulary is publisher / author manuscript / preprint / scan /
    # web snapshot; a PDF served from a project's own repository is none of them, and claiming
    # one would be a claim nothing measured
    assert "copy_kind" not in ev, ev


# ── the reference SHAPES (S1, 2026-09-20): every drop-off ends in a named result ───────────
#
# `ref_kind` used to CLASSIFY — http was a URL, anything else was a DOI — so a title, an ISBN and
# a typo were all handed to `admit_registry` and died at `AdmissionError("… is not a DOI")` or at
# a registry call for a string nobody meant as an identifier. A lit-scout drops off every one of
# those shapes. It now VALIDATES, and `qc/fixtures/litkb_ref_shapes.json` is the table of what
# each shape must end in. Rows HS1-HS6 of qc/instruments/litkb_p2_mutations.py mutate the guards
# these drive.
#
# NOTHING HERE OPENS A SOCKET: `fetch`, `registry_client` and the title resolver's client are all
# injected, and the `explode` fetch fails the test outright if a row reaches the network.

def _fixture(name):
    return json.loads((Path(__file__).with_name("fixtures") / name).read_text(encoding="utf-8"))


def _shapes():
    return _fixture("litkb_ref_shapes.json")["rows"]


def _title_gate():
    return _fixture("litkb_title_gate_wrong_work.json")


class _CrossrefSearchStub:
    """The frozen Crossref SEARCH response for `query.bibliographic`, and 404 for everything else.

    Semantic Scholar and arXiv therefore return no candidates at all, which is what makes an
    assertion about the frozen Crossref candidate an assertion about THAT candidate."""

    base = ""

    def __init__(self, body):
        self.body = body
        self.calls = []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        if "api.crossref.org/works?" in url:
            return 200, {}, self.body
        return 404, {}, b""


def _no_wait_pacer():
    from litkb.netutil import Pacer

    return Pacer(interval=0, sleep=lambda s: None)


def _token(env):
    return json.loads((env["wt"] / ".litkb-workstream").read_text(encoding="utf-8"))["token"]


@pg_only
@pytest.mark.parametrize("row", _shapes(), ids=[r["id"] for r in _shapes()])
def test_ref_shapes_each_end_in_a_named_result(env, row):
    """One row of qc/fixtures/litkb_ref_shapes.json, driven through `hunt()`.

    The fixture's `why` field says what each row protects; it is not repeated here, because a
    restated reason is a reason that rots (CLAUDE.md §3.3)."""
    kw = dict(row.get("inputs") or {})
    if row.get("seed"):
        s = row["seed"]
        seed_extracted(env["conn"], env["ws_id"], s["scheme"], s["value"], state=s["state"])
    if row["fetch"] == "explode":
        kw["fetch"] = _explode
    elif row["fetch"] == "html":
        kw["fetch"] = lambda u, timeout=180: (200, HTML)
    else:
        p2 = _p2_module()
        p2._need_pdftotext()
        pdf = p2.paper_pdf(kw.get("title") or "A Hunted Document", kw.get("author") or "Doe")
        kw["fetch"] = lambda u, timeout=180: (200, pdf)
    if row["registry"] == "title_gate":
        kw["registry_client"] = _CrossrefSearchStub(
            json.dumps(_title_gate()["crossref_search_body"]).encode("utf-8"))
        kw["pacer"] = _no_wait_pacer()
    else:
        kw["registry_client"] = _NoNet()

    res = _hunt(env, row["ref"], ref_scheme=row["ref_scheme"], **kw)

    want = row["expect"]
    assert res["ok"] is want["ok"], res
    assert res["ref_kind"] == want["ref_kind"], res
    if want["ok"]:
        assert res["state"] == want["state"], res
        assert res["outcome"] == want["outcome"], res
        if want.get("resolved_doi"):
            assert res["resolved"]["doi"] == want["resolved_doi"], res
    else:
        assert res["refused"] == want["refused"], res
        assert res["message"], res
        if want.get("message_names"):
            assert want["message_names"] in res["message"], res
        if want.get("ref_scheme"):
            assert res.get("ref_scheme") == want["ref_scheme"], res


@pg_only
def test_ref_shapes_a_garbage_reference_is_malformed_ref_and_never_a_doi(env):
    """(c) item 1, asserted on its own rather than only inside the table above, because what it
    rules out is SILENT: the old code produced a perfectly ordinary-looking result whose
    `ref_kind` read `doi` for a sentence out of a spreadsheet."""
    from litkb import hunt as H

    res = _hunt(env, "see the attached spreadsheet, row 14", fetch=_explode,
                registry_client=_NoNet())
    assert res["ok"] is False and res["refused"] == "malformed-ref", res
    assert res["ref_kind"] is None and res["ref_kind"] != "doi", res
    assert H.ref_kind("see the attached spreadsheet, row 14") is None


@pg_only
def test_ref_shapes_an_isbn_is_unsupported_and_never_a_traceback(env):
    """(c) item 2. `isbn` is IN the recordable vocabulary (a scout may drop one off) and is not a
    scheme a hunt can follow; those are different facts, and the refusal says which."""
    res = _hunt(env, "978-0-13-110362-7", ref_scheme="isbn", fetch=_explode,
                registry_client=_NoNet())
    assert res["ok"] is False and res["refused"] == "unsupported-ref-scheme", res
    assert res["refused"] != "error", "an unsupported scheme became a traceback"
    assert "S3" in res["message"], res


def test_ref_shapes_a_scheme_outside_the_vocabulary_is_named_not_guessed():
    """`unknown-ref-scheme` and `unsupported-ref-scheme` answer different questions: "no such
    scheme" and "a scheme litkb records but cannot chase". No database, no network."""
    from litkb import hunt as H
    from litkb.hunt_request import REF_SCHEMES

    with pytest.raises(H.HuntRefused) as e:
        H.validate_ref("x", "bibtex")
    assert e.value.code == "unknown-ref-scheme", e.value.code
    assert all(s in e.value.message for s in ("doi", "title", "isbn")), e.value.message
    assert set(H.HUNTABLE) < set(REF_SCHEMES), (H.HUNTABLE, REF_SCHEMES)


# ── the identity gate: a WRONG work scoring just under the ratio (S1 done-state (c) item 3) ──

def test_a_wrong_work_scoring_just_under_the_ratio_is_refused():
    """A frozen, real Crossref response whose top candidate scores 0.83 against the title being
    resolved — a WRONG work, a sibling volume — is refused by gate 0.

    THE PROOF IS THE TEST BELOW. A gate that has never been shown to fire is not known to work
    (CLAUDE.md §3.4c): with `RESOLVE_TITLE_RATIO` lowered from 0.85 to 0.80 the identical call
    returns that wrong work's DOI, so this test goes RED.

    THE RATIO IS ISOLATED, deliberately. `judge_candidate` refuses on the title ratio OR the
    first-author family name OR the year, so the surname and year passed in are taken from the
    CANDIDATE'S OWN record (Plackett / 1975): both of those checks PASS and the ratio is the only
    check that can refuse. Without that, lowering the ratio would change nothing and this would
    be a test of the year rule wearing the ratio's name.
    `qc/fixtures/litkb_title_gate_wrong_work.json` carries the capture, its provenance and the one
    deviation from the S1 brief it was frozen under. No network: the frozen body is served for
    Crossref and 404 for Semantic Scholar and arXiv."""
    from litkb.admit import resolver as R

    fx = _title_gate()
    stub = _CrossrefSearchStub(json.dumps(fx["crossref_search_body"]).encode("utf-8"))
    doi, source, evidence = R.resolve_doi(fx["resolved_title"], fx["surname"], fx["year"],
                                          stub, _no_wait_pacer())
    assert doi is None, f"a wrong work scoring under the ratio was admitted: {doi} ({evidence})"
    assert source is None, (source, evidence)
    assert evidence == fx["expected"]["at_ratio_0_85"]["reason"], evidence


def test_the_same_wrong_work_is_admitted_once_the_ratio_is_lowered(monkeypatch):
    """The kill for the test above. If this ever stops holding, that assertion is passing for a
    reason that is not the ratio gate and its RED proof is void."""
    from litkb.admit import resolver as R

    fx = _title_gate()
    monkeypatch.setattr(R, "RESOLVE_TITLE_RATIO", 0.80)
    stub = _CrossrefSearchStub(json.dumps(fx["crossref_search_body"]).encode("utf-8"))
    doi, source, _ev = R.resolve_doi(fx["resolved_title"], fx["surname"], fx["year"],
                                     stub, _no_wait_pacer())
    assert doi == fx["expected"]["at_ratio_0_80"]["doi"], doi
    assert source == fx["expected"]["at_ratio_0_80"]["source"], source


# ── hunt_request precedence: the drop-off's own scheme outranks an explicit one ────────────

@pg_only
def test_the_drop_offs_own_scheme_wins_and_a_disagreeing_one_is_refused(env):
    """A hunt following up a drop-off takes the scheme from the ROW. An explicit `ref_scheme` that
    disagrees is `ref-scheme-mismatch` rather than a silent override: the drop-off is the record
    of what the scout meant, and linking a work to an expectation written about a DIFFERENT
    reference is the one thing migration 0023 exists to prevent."""
    from litkb import hunt_request as HR

    doi = f"10.9999/precedence.{uuid.uuid4().hex[:10]}"
    seeded = seed_extracted(env["conn"], env["ws_id"], "doi", doi)
    hr = HR.record(env["conn"], env["ws_id"], _token(env), ref=doi, ref_scheme="doi",
                   expected_claim="the precedence rule holds", why_relevant="row HS3",
                   agent="hunt-test", session="hunt-test-session")
    bad = _hunt(env, doi, hunt_request_id=str(hr), ref_scheme="url", fetch=_explode,
                registry_client=_NoNet())
    assert bad["ok"] is False and bad["refused"] == "ref-scheme-mismatch", bad
    assert bad["request_ref_scheme"] == "doi" and bad["given_ref_scheme"] == "url", bad

    ok = _hunt(env, doi, hunt_request_id=str(hr), fetch=_explode, registry_client=_NoNet())
    assert ok["ok"] is True and ok["ref_kind"] == "doi", ok
    assert ok["work_key"] == seeded["key"], ok
    assert ok["hunt_request"]["ok"] is True, ok


@pg_only
def test_the_mcp_drop_off_names_an_unknown_scheme_instead_of_raising_the_database_at_the_caller(
        env, monkeypatch):
    """Row HS7. Until 2026-09-20 an unrecognised `ref_scheme` reached the table's CHECK and came
    back as the ordinary `error` shape carrying a raw PL/pgSQL constraint sentence — which an
    unattended scout cannot act on, and which does not say what the vocabulary IS.

    The second half is the half that would rot: the scheme migration 0027 ADDED must be accepted
    here. A Python constant left behind would refuse `title` at the MCP layer against a database
    that accepts it, and the scout's first title drop-off would die of a stale list."""
    from litkb.mcp import server as S

    monkeypatch.setattr(S, "_role", lambda kind: "litkb_test", raising=False)
    res = json.loads(S._hunt_request_add(ref="x", ref_scheme="bibtex", expected_claim="c",
                                         why_relevant="w"))
    assert res["ok"] is False and res["refused"] == "unknown-ref-scheme", res
    assert "title" in res["message"] and "doi" in res["message"], res
    ok = json.loads(S._hunt_request_add(ref="A Title", ref_scheme="title", expected_claim="c",
                                        why_relevant="w"))
    assert ok.get("refused") != "unknown-ref-scheme", ok


@pg_only
def test_the_cli_drop_off_names_an_unknown_scheme_before_it_writes(env):
    """Row HS8, the other entry point. `commands.main` is driven with a `_NoConn`, so the refusal
    must land before anything touches the connection — a scheme that reached `_hr.record` would
    raise RuntimeError from that stub instead of SystemExit."""
    from litkb import commands as C

    with pytest.raises(SystemExit) as e:
        C.main(["--dir", str(env["wt"]), "hunt-request", "add", "--ref", "x",
                "--ref-scheme", "bibtex", "--expected-claim", "c", "--why-relevant", "w"],
               connect=lambda db: C._NoConn())
    assert "bibtex" in str(e.value) and "title" in str(e.value), str(e.value)


def test_the_sql_check_and_the_python_vocabulary_agree():
    """ONE ref-scheme vocabulary (CLAUDE.md §3.3). The SQL CHECK is what ENFORCES it; the Python
    constant is what the CLI and the MCP tool refuse against before the write, so a caller reads a
    named refusal rather than a raw PL/pgSQL sentence. A stale copy in Python would refuse, at the
    MCP layer, a scheme the database accepts — which is exactly how the scout's first `title`
    drop-off would have died.

    The HIGHEST-numbered migration that states the CHECK is the live one: reading only 0023 would
    compare against the list 0027 replaced. Kept here rather than in test_litkb_hunt_request.py so
    that `-k ref_shapes`'s neighbours and this gate move together; the harness runs both files."""
    import re as _re

    from litkb.hunt_request import REF_SCHEMES

    mig = Path(__file__).resolve().parents[1] / "pipeline" / "litkb" / "db" / "migrations"
    pat = _re.compile(r"ref_scheme\s+IN\s*\((?P<body>[^)]*)\)", _re.S | _re.I)
    found = []
    for p in sorted(mig.glob("0*.sql")):
        m = pat.search(p.read_text(encoding="utf-8"))
        if m:
            found.append((p.name, tuple(_re.findall(r"'([a-z0-9_]+)'", m.group("body")))))
    assert found, "no migration states the hunt_requests.ref_scheme CHECK any more"
    live_file, live = found[-1]
    assert set(live) == set(REF_SCHEMES), (live_file, sorted(live), sorted(REF_SCHEMES))
    assert "title" in live, live_file

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
    manual proposal would put a registry-confirmable work behind a second session's sign-off."""
    from litkb import hunt as H

    assert H.ref_kind("10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("https://doi.org/10.1016/j.laa.2010.04.007") == "doi"
    assert H.ref_kind("http://dx.doi.org/10.1/x") == "doi"
    assert H.ref_kind("https://raw.githubusercontent.com/a/b/Doc.pdf") == "url"


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

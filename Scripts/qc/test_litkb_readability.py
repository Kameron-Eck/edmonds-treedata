"""ONE completeness rule for a work's state, and ONE spelling of the current-run join (S4).

`litkb/readability.py` replaced eight hand-written copies of two rules:

  the CURRENT-RUN JOIN, five copies   mcp/server.py::_BLOCK_FROM, mcp/server.py::_work,
                                      use.py::locate_quote, review_check.py::_BLOCK_SQL,
                                      review_context.py::_BLOCK_TEXT_SQL
  the STATE LADDER, three copies      mcp/server.py::_work, mcp/server.py::_absent_kind,
                                      hunt.py::look_up

Both had drifted into something a reader could not check. The ladder said `extracted` as soon as
ONE file had a current run (`any()`), and said `extracted, blocks: 0` for a run that had produced
nothing. Neither case had ever fired on real data — on the 2026-09-21 live corpus 0 works hold
more than one active file and 0 files have a current run with no blocks — so the two cases below
that construct them are the first time either rule has been exercised at all.

  what is tested                                                  name
  the join names the current run AND canonical                    test_the_current_run_join_requires_the_current_run_and_canonical
  main_files joins on file_id, not id                             test_the_join_reads_main_files_by_its_own_file_id_column
  the extracted reason comes from METRICS, not artifacts          test_the_extracted_reason_is_read_from_the_runs_metrics
  the live Maiti_2022 shape                                       test_the_live_maiti_shape_reads_grobid_only_not_fresh
  the hunt's own call site reads metrics, not artifacts           test_the_hunts_extract_stage_reads_the_metrics_not_the_artifacts
  one file, current run, blocks                                   test_a_work_whose_every_file_is_read_is_extracted
  a current run holding no canonical block                        test_a_current_run_with_no_canonical_block_is_zero_content
  one readable file beside one unreadable one                     test_one_extracted_file_beside_one_unread_file_is_partial
  a bound file nothing has run on                                 test_a_bound_file_with_no_run_is_already_bound
  no file at all                                                  test_a_work_with_no_file_is_held
  every acquisition route terminal                                test_a_work_whose_every_attempt_is_terminal_is_no_file_any_route
  the vocabulary is closed                                        test_every_reason_readability_can_return_is_a_hunt_reason
"""
import uuid

import pytest

pg_only = pytest.mark.requires_litkb_pg


# ── the join, with no database ─────────────────────────────────────────────────────────────

def test_the_current_run_join_requires_the_current_run_and_canonical():
    """`b.canonical` is half the rule since migration 0030. Without it a retired run's blocks stay
    searchable, quotable and gradable, which is the whole thing `retire_run` is for."""
    from litkb import readability

    sql = readability.current_run_join()
    assert "f.current_run_id = b.run_id" in sql
    assert "b.canonical" in sql
    assert "JOIN litkb.files f ON f.id = b.file_id" in sql


def test_the_join_reads_main_files_by_its_own_file_id_column():
    """`litkb.main_files` IS files JOIN file_versions and names the file `file_id`; `litkb.files`
    names it `id`. One fragment, two spellings, and the wrong one silently joins nothing."""
    from litkb import readability

    assert "mf.file_id = b.file_id" in readability.current_run_join(
        file="mf", table="litkb.main_files")
    assert "f.id = b.file_id" in readability.current_run_join()


@pytest.mark.parametrize("metrics,fresh,want", [
    ({"grobid_regions": 69, "docling_regions": 0}, True, "grobid-only"),
    ({"grobid_regions": 0, "docling_regions": 40}, True, "docling-only"),
    ({"grobid_regions": 12, "docling_regions": 40}, True, "fresh"),
    ({"grobid_regions": 12, "docling_regions": 40}, False, "already-extracted"),
    ({}, True, "fresh"),
    (None, False, "already-extracted"),
])
def test_the_extracted_reason_is_read_from_the_runs_metrics(metrics, fresh, want):
    """`hunt.py::_finish` derived this from ARTIFACT EXISTENCE — "is there a .docling.json" — and that
    is a different question from "did docling contribute a region"."""
    from litkb import readability

    assert readability.extracted_reason(metrics, fresh=fresh) == want


def test_the_live_maiti_shape_reads_grobid_only_not_fresh():
    """The measured live row (survey-data §3): run 01a0c263, `grobid_regions: 69`,
    `docling_regions: 0`, a `.docling.json` on disk beside it, 113 blocks and not one with
    `source = 'docling'`. The old expression called it `fresh` because the artifact existed."""
    from litkb import readability

    maiti = {"blocks": 113, "grobid_only": 69, "docling_only": 0, "grobid_regions": 69,
             "docling_regions": 0, "merged_regions": 4, "pipeline_version": "stage5-3"}
    assert readability.extracted_reason(maiti, fresh=True) == "grobid-only"


def test_the_hunts_extract_stage_reads_the_metrics_not_the_artifacts(tmp_path):
    """`hunt._finish`'s OWN call site, not just the helper it calls.

    The defect was not that `extracted_reason` was wrong — it did not exist. It was that
    `hunt._finish` decided the reason from `detail["tei"]` and `detail["docling"]`, which are
    "did a file appear on disk". This drives `_finish` with BOTH artifacts present and
    `docling_regions: 0`, which is the live `Maiti_2022` shape exactly, and the old expression
    answers `fresh` for it. `extract_and_ingest` and `_report` are the two seams: neither the
    extractors nor the database is what is under test here.
    """
    from unittest import mock

    from litkb import hunt as H

    pdf = tmp_path / "seeded.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    res = {"run_id": "01a0c263-3977-7483-bdb9-f483890782be", "inserted": 113, "blocks": 113,
           "disagreements": 4}

    def _detail(grobid_regions, docling_regions):
        return {"record": {"route": "native", "pages": 8, "sha256": "0" * 64},
                "stats": {"by_kind": {"paragraph": 52}, "matched": 0,
                          "grobid_regions": grobid_regions,
                          "docling_regions": docling_regions},
                "coverage": {1: {"page_class": "native", "chars": 100, "covered": 95,
                                 "share": 0.95}},
                # BOTH artifacts exist on disk. That is the whole point: the reconciler names its
                # output `<sha>.docling.json` whether docling contributed anything or not.
                "tei": True, "docling": True, "canonical": []}

    def _run(grobid_regions, docling_regions):
        with mock.patch.object(H, "extract_and_ingest",
                               return_value=(res, _detail(grobid_regions, docling_regions))), \
             mock.patch.object(H, "_report", return_value={}):
            return H._finish(None, None, {"work_id": None}, {"rel_path": "seeded.pdf", "file_id": "01a0c261-df48-777c-8ff9-f2012c0edddd"}, {},
                             {}, [], reader_role=None, device="cpu", docling_python=None,
                             derived=None, pdf_path=str(pdf))

    out = _run(69, 0)
    assert (out["state"], out["reason"]) == ("extracted", "grobid-only"), out
    assert out["extraction"]["docling"] is True and out["extraction"]["docling_regions"] == 0
    assert _run(0, 40)["reason"] == "docling-only"
    assert _run(69, 40)["reason"] == "fresh"


def test_every_reason_readability_can_return_is_a_hunt_reason():
    """The vocabulary is `litkb.hunt`'s and this module may not invent one: a reason outside
    `REASONS` reaches `_result` and raises, and reaches a run ledger as `unknown_states`."""
    from litkb import hunt, readability

    bound = set(hunt.REASONS["bound-unextracted"])
    assert set(readability.RESIDUE_CLASSES) <= bound
    assert readability.PARTIAL in bound and readability.ALREADY_BOUND in bound
    assert "no-file-any-route" in hunt.REASONS["held"] and "no-file" in hunt.REASONS["held"]
    for r in ("fresh", "already-extracted", "grobid-only", "docling-only"):
        assert r in hunt.REASONS["extracted"]


# ── the ladder, against Postgres ───────────────────────────────────────────────────────────

class KB:
    """The shared litkb_test connection, one workstream per test — `test_litkb_first_use.KB`'s
    shape, kept to the three things this module needs."""

    def __init__(self, psycopg, conn):
        self.psycopg, self.conn = psycopg, conn
        self.tokens = {}

    def one(self, q, params=()):
        return self.conn.execute(q, params).fetchone()

    def jsonb(self, v):
        from psycopg.types.json import Jsonb
        return Jsonb(v)

    def ws(self):
        ws_id, token = self.one(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/readability', NULL, "
            "'readability test', NULL)", (f"rd-{uuid.uuid4().hex[:12]}",))
        self.tokens[ws_id] = token
        return ws_id


@pytest.fixture
def kb(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    return KB(psycopg, conn)


def _crossref(doi, title, author="Tester", year=2024):
    """A Crossref /works/<doi> message in the shape `registry.parse_crossref` reads — the same
    stub `qc/test_litkb_first_use.py` builds its fixtures from, copied rather than imported
    because a test module importing another test module is an import order nobody controls."""
    return {"DOI": doi, "title": [title], "type": "journal-article",
            "container-title": ["A Journal"],
            "author": [{"family": author, "given": "P.", "sequence": "first"}],
            "issued": {"date-parts": [[year, 1]]}}


class _CrossrefStub:
    base = ""

    def __init__(self, records):
        self.records = {k.lower(): v for k, v in records.items()}

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        import json
        import urllib.parse
        if "api.crossref.org/works/" in url:
            rec = self.records.get(urllib.parse.unquote(url.split("/works/", 1)[1]).lower())
            return (200, {}, json.dumps({"message": rec}).encode()) if rec else (404, {}, b"")
        return 404, {}, b""


class _NoPace:
    def __getattr__(self, _n):
        return lambda *a, **k: None


def _work(kb, ws):
    """An admitted work with no file bound — the `held` rung."""
    from litkb.admit import front

    doi = f"10.5555/rd-{uuid.uuid4().hex[:10]}"
    title = f"A readability fixture {uuid.uuid4().hex[:10]}"
    res = front.admit_registry(kb.conn, ws, kb.tokens[ws], doi=doi,
                               claimed=None, agent="agentR", session="sessR",
                               client=_CrossrefStub({doi: _crossref(doi, title)}), pacer=_NoPace())
    assert res["outcome"] == "admitted", res
    return res["work_id"], title


def _file(kb, ws, work_id, title, *, pages=8):
    fj = {"sha256": (uuid.uuid4().hex + uuid.uuid4().hex)[:64],
          "rel_path": f"_litkb_staging/filed/rd-{uuid.uuid4().hex[:8]}.pdf",
          "bytes": 1024, "pages": pages,
          "binding": {"verdict": "bound", "ratio": 0.99, "matched": title,
                      "registry_title": title, "author_found": True, "author_near_title": True,
                      "text_layer": True, "page": 1, "title_region": True}}
    att = kb.one("SELECT litkb.attach_file(%s, %s, %s, %s, %s, %s)",
                 (ws, kb.tokens[ws], work_id, kb.jsonb(fj), "agentR", "sessR"))[0]
    assert att["outcome"] == "attached", att
    return att["file_id"]


def _run(kb, file_id, *, blocks=1, canonical=True, metrics=None, current=True, text=None):
    run = kb.one("SELECT litkb.open_extraction_run(%s, '5-reconcile', 'litkb-reconcile', 'v1', "
                 "'h1', 'v1', 'local', 'ok', NULL, %s)",
                 (file_id, kb.jsonb(metrics or {})))[0]
    for i in range(blocks):
        kb.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text, canonical, "
               "reading_order) VALUES (%s, %s, 1, 'paragraph', %s, %s, %s) RETURNING id",
               (file_id, run, text or f"block {i} of {run}", canonical, i + 1))
    if current:
        kb.one("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run))
    return run


@pg_only
def test_a_work_whose_every_file_is_read_is_extracted(kb):
    from litkb import readability

    ws = kb.ws()
    w, title = _work(kb, ws)
    f = _file(kb, ws, w, title)
    _run(kb, f, blocks=3, metrics={"grobid_regions": 5, "docling_regions": 7})
    state, reason, files = readability.work_state(kb.conn, w, ws_id=ws)
    assert (state, reason) == ("extracted", "already-extracted")
    assert len(files) == 1 and files[0]["blocks"] == 3 and files[0]["state"] == "extracted"


@pg_only
def test_a_current_run_with_no_canonical_block_is_zero_content(kb):
    """THE CASE THAT HAD NEVER FIRED. The ladder reported `extracted, blocks: 0` and called it
    deliberate; it is a work litkb_search cannot return one word of, told to a caller as readable.
    0 live files are in this state, so this fixture is the only place it has ever been seen."""
    from litkb import readability

    ws = kb.ws()
    w, title = _work(kb, ws)
    f = _file(kb, ws, w, title)
    _run(kb, f, blocks=2, canonical=False)
    state, reason, files = readability.work_state(kb.conn, w, ws_id=ws)
    assert (state, reason) == ("bound-unextracted", "zero-content")
    assert files[0]["blocks"] == 0 and files[0]["current_run_id"] is not None


@pg_only
def test_one_extracted_file_beside_one_unread_file_is_partial(kb):
    """THE OTHER CASE THAT HAD NEVER FIRED. `any(current_run_id)` made this `extracted`: a search
    then answers from the readable file and silently misses everything in the other one. 0 live
    works hold more than one active file."""
    from litkb import readability

    ws = kb.ws()
    w, title = _work(kb, ws)
    good, bad = _file(kb, ws, w, title), _file(kb, ws, w, title)
    _run(kb, good, blocks=4)
    state, reason, files = readability.work_state(kb.conn, w, ws_id=ws)
    assert (state, reason) == ("bound-unextracted", "partial")
    assert {f["state"] for f in files} == {"extracted", "bound-unextracted"}
    assert [f["reason"] for f in files if f["file_id"] == str(bad)] == ["already-bound"]


@pg_only
def test_a_bound_file_with_no_run_is_already_bound(kb):
    from litkb import readability

    ws = kb.ws()
    w, title = _work(kb, ws)
    _file(kb, ws, w, title)
    assert readability.work_state(kb.conn, w, ws_id=ws)[:2] == ("bound-unextracted", "already-bound")


@pg_only
def test_a_work_with_no_file_is_held(kb):
    from litkb import readability

    ws = kb.ws()
    w, _title = _work(kb, ws)
    assert readability.work_state(kb.conn, w, ws_id=ws) == ("held", "no-file", [])


@pg_only
def test_a_work_whose_every_attempt_is_terminal_is_no_file_any_route(kb):
    """`no-file-any-route` needs BOTH halves: at least one attempt, and every attempt terminal
    (`acquire.run.DEAD_STATUSES` for its route, or `blocked`). An `ok` attempt that did not end in
    a bound file is not terminal — the route worked and something downstream did not."""
    from litkb import readability

    ws = kb.ws()
    w, _title = _work(kb, ws)
    for route, status in (("open_access", "no-oa-copy"), ("annas", "not-in-archive"),
                          ("scihub", "blocked")):
        kb.conn.execute("INSERT INTO litkb.acquisition_attempts (work_id, route, status, "
                        "workstream_id) VALUES (%s, %s, %s, %s)", (w, route, status, ws))
    assert readability.held_reason(kb.conn, w) == "no-file-any-route"
    kb.conn.execute("INSERT INTO litkb.acquisition_attempts (work_id, route, status, "
                    "workstream_id) VALUES (%s, 'browser', 'manual-step', %s)", (w, ws))
    assert readability.held_reason(kb.conn, w) == "no-file"

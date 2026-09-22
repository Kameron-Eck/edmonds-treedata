"""litkb — retiring superseded extraction run sets (migration 0031, litkb/ops/retire.py).

S4 run 3 decision D6: retirement MARKS runs, it never deletes them. Every test here seeds its own
file in the worker database (``LITKB_TEST_DB``) and asserts on that file's runs only; the op's
database guards are exercised both through the op (``retire.retire``) and by calling
``litkb.retire_extraction_runs`` directly with a run it must refuse, because the op never HANDS the
function a refused run and a guard that is never handed one is never shown to fire.

The world (``_world``): one file with three ``5-reconcile`` runs A, B, C made current in that
order — so C is current and A and B were superseded by the pointer — and one ``use_evidence`` row
citing a block of A. The op must retire exactly B.
"""
import re
import uuid

import pytest

from litkb.ops import retire as RT

from test_litkb_p1 import _PG  # noqa: E402 - the P1 harness class, not its fixture

pg_only = pytest.mark.requires_litkb_pg


@pytest.fixture(scope="session")
def _rt(litkb_pg_base):
    psycopg, conn, ran = litkb_pg_base
    yield _PG(psycopg, conn, ran)


@pytest.fixture
def pg(_rt):
    yield _rt
    while _rt.opened:
        _rt.opened.pop().close()


#: A stage-6 key as `references_ingest.run_key` shapes it — CONSTRUCTED values, so the tests do
#: not move when the real stage-6 version does (the real one is read by `retire.current_keys`).
_S6_OLD = {"tool": "litkb-references", "tool_version": "t-p6-1", "params_hash": "h1",
           "pipeline_version": "t-p6-1"}
_S6_NEW = {"tool": "litkb-references", "tool_version": "t-p6-2", "params_hash": "h1",
           "pipeline_version": "t-p6-2"}
_KEYS = {"6-references": _S6_NEW}


def _file(pg):
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    file_id, _ = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, "
        "%s, NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         pg.Jsonb({"work_id": str(work_id), "rel_path": "Validation/Test_2020_x-paper.pdf",
                   "status": "active"}), ws))
    return ws, work_id, file_id


def _run(pg, file_id, *, stage="5-reconcile", version="t5-1", params=None, status="ok",
         current=True, age_minutes=0, key=None):
    """An extraction run of `file_id` with one page and one block, as the owner; `current` moves
    the file's pointer to it through set_current_run (which writes the history row)."""
    k = dict(key or {"tool": "litkb-reconcile", "tool_version": version,
                     "params_hash": params or uuid.uuid4().hex[:16], "pipeline_version": version})
    run_id = pg.one(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, 'local', %s, "
        "now() - make_interval(mins => %s)) RETURNING id",
        (file_id, stage, k["tool"], k["tool_version"], k["params_hash"], k["pipeline_version"],
         status, age_minutes))[0]
    block = None
    if stage == "5-reconcile":
        pg.conn.execute("INSERT INTO litkb.pages (file_id, run_id, page_no) VALUES (%s, %s, 1)",
                        (file_id, run_id))
        block = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                       "VALUES (%s, %s, 1, 'paragraph', %s) RETURNING id",
                       (file_id, run_id, "The optimism identity holds under a joint model."))[0]
    if current:
        cur = pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0]
        pg.conn.execute("SELECT litkb.set_current_run(%s, %s, %s)", (file_id, cur, run_id))
    return run_id, block


def _world(pg):
    ws, work_id, file_id = _file(pg)
    a, a_block = _run(pg, file_id)
    b, _ = _run(pg, file_id)
    c, _ = _run(pg, file_id)
    _, uv = pg.proposal(pg.conn, "use", None, {"work_id": str(work_id)}, None,
                        {"statement": "supplies the optimism identity", "kind": "theorem",
                         "status": "supported", "feeds": ["gap row 6"]}, None, ws)
    pg.conn.execute(
        "INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, page, quote, char_start, "
        "char_end, stance) VALUES (%s, %s, %s, 1, 'optimism identity', 4, 21, 'supports')",
        (uv, a_block, a))
    return dict(file=file_id, a=a, b=b, c=c)


def _counts(pg):
    return pg.one("SELECT (SELECT count(*) FROM litkb.run_retirement_ops), "
                  "(SELECT count(*) FROM litkb.run_retirements), "
                  "(SELECT count(*) FROM litkb.extraction_runs), (SELECT count(*) FROM litkb.blocks), "
                  "(SELECT count(*) FROM litkb.pages)")


def _retire_fn(pg, runs, keys=None):
    ingest = pg.session("litkb_ingest")
    return pg.one("SELECT litkb.retire_extraction_runs(%s::uuid[], 'test-session', 'test reason', %s)",
                  ([str(r) for r in runs], pg.Jsonb(keys) if keys is not None else None), conn=ingest)[0]


@pg_only
def test_the_op_retires_exactly_the_superseded_run_nothing_cites(pg):
    """The brief's own case: current C, superseded A (cited by evidence) and B. Exactly B."""
    w = _world(pg)
    reader, ingest = pg.session("litkb_reader"), pg.session("litkb_ingest")
    out = RT.retire(reader, ingest, apply=True, session="s4-run3-test", reason="superseded by C",
                    keys=_KEYS, files=[w["file"]])
    assert out["applied"] and out["eligible"] == [str(w["b"])], out["eligible"]
    rows = pg.conn.execute("SELECT run_id, op_id, superseded_by, blocks, pages FROM litkb.run_retirements "
                           "WHERE file_id = %s", (w["file"],)).fetchall()
    assert [(r[0], r[2], r[3], r[4]) for r in rows] == [(w["b"], w["c"], 1, 1)]
    op = pg.one("SELECT session_label, reason, runs, retired_by FROM litkb.run_retirement_ops "
                "WHERE op_id = %s", (rows[0][1],))
    assert op == ("s4-run3-test", "superseded by C", 1, "litkb_test")
    # MARKING, never deleting: every run row and every block of the file is still there
    assert pg.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s", (w["file"],))[0] == 3
    assert pg.one("SELECT count(*) FROM litkb.blocks WHERE file_id = %s", (w["file"],))[0] == 3
    # and a second op finds nothing left to do for this file
    again = RT.plan(reader, _KEYS, files=[w["file"]])
    assert again["eligible"] == [] and again["excluded_counts"] == {
        "already-retired": 1, "current": 1, "evidence": 1}, again["excluded_counts"]
    assert [e["run_id"] for e in again["excluded_evidence"]] == [str(w["a"])]


@pg_only
def test_the_dry_run_writes_nothing(pg):
    w = _world(pg)
    before = _counts(pg)
    reader = pg.session("litkb_reader")
    out = RT.retire(reader, None, apply=False, keys=_KEYS, files=[w["file"]])
    assert out["applied"] is False and out["op_id"] is None
    assert out["eligible"] == [str(w["b"])]
    assert out["by_stage"]["5-reconcile"]["runs"] == 1 and out["by_stage"]["5-reconcile"]["blocks"] == 1
    assert _counts(pg) == before


@pg_only
def test_kill_the_current_run_is_refused_by_the_database(pg):
    w = _world(pg)
    with pytest.raises(pg.errors.InvalidParameterValue, match="current run"):
        _retire_fn(pg, [w["c"]], _KEYS)
    assert pg.one("SELECT count(*) FROM litkb.run_retirements WHERE file_id = %s", (w["file"],))[0] == 0


@pg_only
def test_kill_an_evidence_cited_run_is_refused_by_the_database(pg):
    w = _world(pg)
    with pytest.raises(pg.errors.InvalidParameterValue, match="cited by use_evidence"):
        _retire_fn(pg, [w["a"]], _KEYS)
    assert pg.one("SELECT count(*) FROM litkb.run_retirements WHERE file_id = %s", (w["file"],))[0] == 0


@pg_only
def test_kill_a_run_that_was_never_superseded_is_refused_by_the_database(pg):
    """A failed run (never current) and a never-current ok run with no newer run at a named key."""
    _, _, file_id = _file(pg)
    _run(pg, file_id)
    failed, _ = _run(pg, file_id, status="failed", current=False)
    orphan, _ = _run(pg, file_id, current=False)
    for r in (failed, orphan):
        with pytest.raises(pg.errors.InvalidParameterValue, match="not superseded"):
            _retire_fn(pg, [r], _KEYS)


@pg_only
def test_kill_the_pointer_never_moves_back_onto_a_retired_run(pg):
    """Orchestrator ruling Q2: 0031 re-creates set_current_run with one more guard. Retire B, then
    ask set_current_run (as the ingest login, the one that may call it) to make B current again:
    refused, and the pointer stays on C. Control: an ok, NOT retired run of the file is still
    accepted by the same call, so the replacement kept 0017's behaviour."""
    w = _world(pg)
    _retire_fn(pg, [w["b"]], _KEYS)
    ingest = pg.session("litkb_ingest")
    with pytest.raises(pg.errors.InvalidParameterValue, match="is retired"):
        ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["c"], w["b"]))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == w["c"]
    d, _ = _run(pg, w["file"], current=False)
    ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["c"], d))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == d


@pg_only
def test_the_two_reported_counters_name_what_is_left(pg):
    """Ruling Q3: both are functions of a connection, and acceptance REPORTS both. For one world:
    the op could retire B; A is superseded but held, and its work is named."""
    w = _world(pg)
    reader = pg.session("litkb_reader")
    work = pg.one("SELECT w.key FROM litkb.main_files mf JOIN litkb.main_works w ON w.work_id = mf.work_id "
                  "WHERE mf.file_id = %s", (w["file"],))[0]
    before = RT.superseded_runs_unretired(reader, _KEYS)
    held = RT.superseded_runs_held_by_evidence(reader, _KEYS)
    assert work in held["works"] and held["count"] == len(held["works"])
    _retire_fn(pg, [w["b"]], _KEYS)
    assert RT.superseded_runs_unretired(reader, _KEYS) == before - 1
    assert RT.superseded_runs_held_by_evidence(reader, _KEYS) == held


@pg_only
def test_a_run_is_retired_once(pg):
    w = _world(pg)
    _retire_fn(pg, [w["b"]], _KEYS)
    with pytest.raises(pg.errors.UniqueViolation, match="already retired"):
        _retire_fn(pg, [w["b"]], _KEYS)


@pg_only
def test_stage6_is_superseded_by_a_newer_run_at_the_current_key_and_listed_apart(pg):
    """Stage 6 never moves the pointer. A 6-references run at the OLD key is superseded by a NEWER
    ok run at the current key (the orchestrator's definition), and the dry run lists it under its
    own stage; the run AT the current key is not."""
    _, _, file_id = _file(pg)
    _run(pg, file_id)                                   # the file's 5-reconcile current run
    old, _ = _run(pg, file_id, stage="6-references", current=False, key=_S6_OLD, age_minutes=60)
    new, _ = _run(pg, file_id, stage="6-references", current=False, key=_S6_NEW)
    reader = pg.session("litkb_reader")
    p = RT.plan(reader, _KEYS, files=[file_id])
    assert p["eligible"] == [str(old)]
    assert p["stage6"]["runs"] == 1 and "5-reconcile" not in p["by_stage"]
    verdict = dict(pg.conn.execute("SELECT run_id, refusal FROM litkb.run_retirement_status(%s) "
                                   "WHERE file_id = %s", (pg.Jsonb(_KEYS), file_id)).fetchall())
    assert verdict[new] == "not-superseded" and verdict[old] is None
    # no key named for the stage: nothing of stage 6 is superseded
    assert RT.plan(reader, {}, files=[file_id])["eligible"] == []
    op = _retire_fn(pg, [old], _KEYS)
    assert pg.one("SELECT superseded_by, stage FROM litkb.run_retirements WHERE run_id = %s", (old,)) \
        == (new, "6-references")
    assert op is not None


@pg_only
def test_kill_a_stale_key_named_as_current_supersedes_nothing(pg):
    """The database's own check on the caller: naming the OLDER key as current does not make the
    NEWER run superseded — "superseded" needs a newer run at the named key."""
    _, _, file_id = _file(pg)
    _run(pg, file_id)
    _run(pg, file_id, stage="6-references", current=False, key=_S6_OLD, age_minutes=60)
    new, _ = _run(pg, file_id, stage="6-references", current=False, key=_S6_NEW)
    stale = {"6-references": _S6_OLD}
    assert RT.plan(pg.session("litkb_reader"), stale, files=[file_id])["eligible"] == []
    with pytest.raises(pg.errors.InvalidParameterValue, match="not superseded"):
        _retire_fn(pg, [new], stale)


@pg_only
def test_only_ingest_may_retire_and_the_reader_may_ask(pg):
    w = _world(pg)
    reader, writer = pg.session("litkb_reader"), pg.session("litkb_writer")
    assert RT.superseded_runs_unretired(reader, _KEYS) >= 1
    for conn in (reader, writer):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            conn.execute("SELECT litkb.retire_extraction_runs(%s::uuid[], 's', 'r', NULL)", ([str(w["b"])],))
    for role in ("litkb_reader", "litkb_writer", "litkb_ingest", "litkb_promoter"):
        k = pg.session(role)
        with pytest.raises(pg.errors.InsufficientPrivilege):
            k.execute("INSERT INTO litkb.run_retirement_ops (session_label, reason, runs) VALUES ('s', 'r', 1)")


@pg_only
def test_the_python_refusal_vocabulary_is_the_sqls(pg):
    """REFUSALS is a READ of the status function's CASE; this pins the two together."""
    src = pg.one("SELECT pg_get_functiondef('litkb.run_retirement_status(jsonb, uuid[])'::regprocedure)")[0]
    tail = src[src.rfind("CASE"):]
    assert tuple(re.findall(r"THEN '([a-z-]+)'", tail)) == RT.REFUSALS


def test_the_cli_is_a_dry_run_unless_told_and_apply_needs_who_and_why(monkeypatch):
    """--apply without a session label and a reason is refused BEFORE any login is opened. The
    database named is the worker one, so a mutant that got past the refusal could never reach
    live (worker databases admit only litkb_test)."""
    from litkb import commands
    from litkb.db import connect as c

    a = commands.build_parser().parse_args(["runs", "retire"])
    assert a.cmd == "runs" and a.runs_cmd == "retire" and a.apply is False
    assert "runs" in commands._OWN_LOGINS
    monkeypatch.delenv("LITKB_SESSION", raising=False)
    with pytest.raises(SystemExit, match="--reason"):
        commands.main(["--db", c.DB_TEST, "runs", "retire", "--apply"])
    with pytest.raises(SystemExit, match="--reason"):
        commands.main(["--db", c.DB_TEST, "--session", "s4", "runs", "retire", "--apply"])


def test_the_op_refuses_to_apply_without_who_and_why():
    with pytest.raises(ValueError, match="session label and a reason"):
        RT.retire(_NoRead(), object(), apply=True, session=" ", reason="r", keys={})


class _NoRead:
    """A reader with nothing in it: the op asks, gets no runs, and must still refuse an --apply
    that names no session before it would hand anything to the database."""

    def execute(self, *a, **kw):
        class _C:
            description = [type("D", (), {"name": n})() for n in
                           ("run_id", "file_id", "stage", "pipeline_version", "status", "is_current",
                            "was_current", "evidence_rows", "superseded_by", "retired_op", "refusal",
                            "work_key")]

            def fetchall(self):
                return []

            def __iter__(self):
                return iter(())
        return _C()

"""litkb P1 "Foundation" — the gate and the kill list of the design's §14 P1 row.

Design: Scripts/LITERATURE_KB_DESIGN_2026-09-13.md. Every KILL here was shown to FIRE (the
test fails when its guard is removed or mutated) by qc/instruments/litkb_p1_mutations.py;
the evidence is Reports/LITKB_P1_REPORT_2026-09-13.md.

  kill (§14 P1)                                                test
  writer role UPDATE on a version table is refused             test_kill_writer_cannot_update_or_delete_version_rows
  two writers on the same base: second refused — fact table    test_kill_fact_second_writer_on_same_base_is_refused
  … and for a proposal                                         test_kill_proposal_second_writer_on_same_base_is_refused
  client quote_verified = true on a non-matching quote → false test_kill_client_quote_verified_is_overwritten
  litkb_test connecting to litkb is refused by the server      test_kill_test_role_is_refused_by_the_server_on_litkb
  promote commit with a merge commit not reachable from main   test_kill_promote_commit_refuses_merge_not_on_main
  a conflicting gap chain is not promoted, nor its dependent   test_kill_conflicting_gap_chain_holds_its_dependent_at_commit
                                                               test_kill_conflicting_gap_chain_holds_its_dependent_at_prepare

Fixes after the independent referee (Reports/LITKB_P1_REFEREE_2026-09-13.md), migration 0007;
each guard below was also shown to fire by the same harness:

  D-1  a write blocked behind promote_commit is refused       test_write_blocked_behind_promote_commit_is_refused
  D-5  evidence only through add_evidence; its four guards    test_writer_has_no_direct_evidence_insert,
                                                              test_evidence_guard_*
       referee bypasses D1, D2, D5                            test_referee_bypass_d1_*, _d2_*, _d5_*
       set_current_run: ok run of this file only              test_set_current_run_refuses_foreign_or_null_run
  D-6  R2 R4 R6 R7                                            test_writer_cannot_insert_version_state_columns,
                                                              test_first_head_proposal_must_be_based_on_main,
                                                              test_quote_verified_checks_offsets_not_presence,
                                                              test_use_whose_gap_is_absent_is_held_at_prepare
  D-7  char_end beyond the block text is refused              test_quote_char_end_beyond_text_is_refused
  D-8  the losing concurrent writer gets 40001                test_losing_concurrent_writer_gets_40001[*]

Kam's decisions on the referee findings (decisions.yaml litkb-p0-foundation), migration 0008;
each guard shown to fire by the same harness:

  D-2  held chains are rebased, then promote                  test_held_chain_is_rebased_and_promotes
       kill: a rebase onto a stale main version is refused    test_kill_rebase_onto_stale_main_is_refused
       rebase guards; evidence carried                        test_rebase_guard_*, test_rebase_carries_evidence
  D-3  reader/writer cannot call any promotion function       test_agent_roles_cannot_call_promotion_functions[*]
       the promoter login only through litkb.promote          test_connect_refuses_the_promoter_login
  D-4  approver needs only a different session                test_admission_approver_must_be_another_session[*]

Isolation: the suite logs in ONLY as litkb_test, to litkb_test, which it resets and migrates
once per session under an advisory lock (parallel worktrees serialise). Role privileges are
exercised with SET ROLE: litkb_test is a member of reader/writer/promoter WITH INHERIT FALSE,
so it inherits none of their privileges — including the writer's CONNECT on litkb.
"""
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
SUITE_LOCK = 0x6C6B7473  # "lkts"
_SKIP_WHEN = ("connection refused", "could not connect", "does not exist",
              "no password supplied", "timeout expired", "is the server running")


# ── no server needed ──────────────────────────────────────────────────────────────────────

def test_import_litkb_pulls_no_heavy_dependency():
    """Design §9 / referee M9: `import litkb` loads no driver or extraction library, so the
    ladder's compile and test sweep never pulls them."""
    code = ("import sys, litkb, litkb.db, litkb.db.connect, litkb.db.migrate, "
            "litkb.db.provision, litkb.promote\n"
            "heavy = {'psycopg', 'torch', 'docling', 'mineru', 'numpy', 'pandas', 'pypdfium2'}\n"
            "pulled = sorted(heavy & {m.split('.')[0] for m in sys.modules})\n"
            "print(pulled)\n"
            "sys.exit(1 if pulled else 0)\n")
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS / "pipeline"))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"import litkb pulled heavy modules: {r.stdout}{r.stderr}"


def test_migration_files_are_named_and_numbered():
    from litkb.db import migrate
    found = migrate.discover()
    assert [v for v, *_ in found] == list(range(1, len(found) + 1))


def test_connect_refuses_the_promoter_login():
    """D-3: the promoter login has one connection path, litkb.promote.connect(). The shared
    connect() that agents' reader and writer connections use refuses it before any driver is
    loaded, and the promote tool's path names the promoter's own passfile."""
    from litkb import promote
    from litkb.db import connect as c
    with pytest.raises(c.PromoterLoginRefused):
        c.connect(c.DB_MAIN, c.PROMOTER)
    info = c.conninfo(c.DB_MAIN, c.PROMOTER, passfile=c.promoter_passfile())
    assert "passfile=" in info and "litkb_promoter" in info
    assert "passfile=" not in c.conninfo(c.DB_MAIN, "litkb_writer")
    assert callable(promote.connect)


# ── harness ───────────────────────────────────────────────────────────────────────────────

class _PG:
    def __init__(self, psycopg, conn, ran):
        from psycopg.types.json import Jsonb
        self.psycopg = psycopg
        self.errors = psycopg.errors
        self.Jsonb = Jsonb
        self.conn = conn          # litkb_test session = the test DB's owner
        self.ran = ran
        self.opened = []

    def session(self, role=None):
        """A new litkb_test connection to litkb_test, optionally SET ROLE'd."""
        from psycopg import sql

        from litkb.db import connect as c
        k = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
        if role:
            k.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        self.opened.append(k)
        return k

    def one(self, query, params=(), conn=None):
        return (conn or self.conn).execute(query, params).fetchone()

    # setup helpers, run as owner
    def ws(self):
        return self.one("SELECT litkb.open_workstream(%s, 'work/test', NULL, 'p1 test', NULL)",
                        (f"t-{uuid.uuid4().hex[:12]}",))[0]

    def work(self, ws):
        key = f"Test_2020_{uuid.uuid4().hex[:8]}-paper"
        return self.one(
            "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, "
            "NULL, %s, NULL, %s, 'setup', 'setup')",
            (self.Jsonb({"key": key}),
             self.Jsonb({"type": "article", "title": "A test work", "authors": []}), ws))

    def main_gap(self, ws):
        return self.one(
            "SELECT entity_id, version_id FROM litkb._write_version('fact', 'gap', NULL, %s, "
            "NULL, %s, NULL, %s, 'setup', 'setup')",
            (self.Jsonb({"slug": f"gap-{uuid.uuid4().hex[:8]}"}),
             self.Jsonb({"question": "q v1", "gap_state": "open"}), ws))

    def proposal(self, conn, entity, entity_id, identity, based_on, fields, reason, ws,
                 agent="agentA", session="sessA"):
        return self.one(
            "SELECT entity_id, version_id FROM litkb.write_proposal(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (entity, entity_id, self.Jsonb(identity) if identity else None, based_on,
             self.Jsonb(fields), reason, ws, agent, session), conn=conn)

    def pointer(self, table, entity_id):
        return self.one(f"SELECT current_version_id FROM litkb.{table} WHERE id = %s", (entity_id,))[0]


@pytest.fixture(scope="session")
def _pg_session():
    psycopg = pytest.importorskip("psycopg", reason="requires_litkb_pg: psycopg is not installed")
    from litkb.db import connect as c
    from litkb.db import migrate
    try:
        conn = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
    except psycopg.OperationalError as e:
        msg = str(e).strip()
        if any(s in msg.lower() for s in _SKIP_WHEN):
            pytest.skip(f"requires_litkb_pg: litkb_test unavailable ({msg.splitlines()[-1][:160]})")
        raise
    conn.execute("SELECT pg_advisory_lock(%s)", (SUITE_LOCK,))
    migrate.reset(conn)
    ran = migrate.apply(conn)
    h = _PG(psycopg, conn, ran)
    yield h
    conn.close()


@pytest.fixture
def pg(_pg_session):
    yield _pg_session
    while _pg_session.opened:
        _pg_session.opened.pop().close()


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=litkb-test",
                        "-c", "user.email=litkb-test@example.invalid", *args],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


@pytest.fixture
def scratch_repo(tmp_path):
    """main at commit A; branch work/x at commit B (the prepared branch head), NOT merged."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "A")
    _git(repo, "checkout", "-q", "-b", "work/x")
    (repo / "b.txt").write_text("b", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "B")
    prepared = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    return repo, prepared


def _merge(repo):
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge work/x", "work/x")
    return _git(repo, "rev-parse", "HEAD")


pg_only = pytest.mark.requires_litkb_pg


# ── gate ──────────────────────────────────────────────────────────────────────────────────

@pg_only
def test_gate_migrations_apply_cleanly_to_an_empty_database(pg):
    from litkb.db import migrate
    names = [n for _v, n, _s, _q in migrate.discover()]
    assert pg.ran == names, "the session reset left the DB empty, so every migration must have run"
    assert migrate.apply(pg.conn) == [], "a second apply must be a no-op"
    n = pg.one("SELECT count(*) FROM litkb_meta.schema_migrations")[0]
    assert n == len(names)


@pg_only
def test_gate_runner_refuses_an_edited_applied_migration(pg, tmp_path):
    from litkb.db import migrate
    for _v, name, _s, sql_text in migrate.discover():
        (tmp_path / name).write_text(sql_text, encoding="utf-8")
    first = sorted(tmp_path.glob("*.sql"))[0]
    first.write_text(first.read_text(encoding="utf-8") + "\n-- edited after apply\n",
                     encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="changed on disk"):
        migrate.apply(pg.conn, tmp_path)


@pg_only
def test_gate_uuidv7_answers(pg):
    u = pg.one("SELECT uuidv7()")[0]
    assert isinstance(u, uuid.UUID) and u.version == 7


@pg_only
def test_gate_extensions_and_tablespace(pg):
    exts = {r[0] for r in pg.conn.execute(
        "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm', 'fuzzystrmatch')")}
    assert exts == {"vector", "pg_trgm", "fuzzystrmatch"}
    assert pg.one("SELECT vector_dims('[1,2,3]'::halfvec)")[0] == 3
    spc = dict(pg.conn.execute(
        "SELECT d.datname, t.spcname FROM pg_database d JOIN pg_tablespace t ON t.oid = d.dattablespace "
        "WHERE d.datname IN ('litkb', 'litkb_test')").fetchall())
    assert spc == {"litkb": "litkb_d", "litkb_test": "litkb_d"}


@pg_only
def test_roles_reach_only_their_functions(pg):
    ws = pg.ws()
    reader = pg.session("litkb_reader")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        pg.proposal(reader, "gap", None, {"slug": f"g-{uuid.uuid4().hex[:8]}"}, None,
                    {"question": "q", "gap_state": "open"}, None, ws)
    writer = pg.session("litkb_writer")
    for call in ("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)",
                 "SELECT litkb.promote_commit(%s, repeat('a', 40))"):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            writer.execute(call, (ws,))
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute("SELECT * FROM litkb._write_version('fact', 'gap', NULL, '{}', NULL, "
                       "'{}', NULL, %s, 'a', 's')", (ws,))
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute("UPDATE litkb.works SET current_version_id = NULL WHERE false")


_PROMOTION_CALLS = {
    "promote_prepare": "SELECT litkb.promote_prepare(%s::uuid, repeat('a', 40), NULL)",
    "promote_commit": "SELECT litkb.promote_commit(%s::uuid, repeat('a', 40))",
    "promote_abandon": "SELECT litkb.promote_abandon(%s::uuid)",
    "promote_rebase": "SELECT litkb.promote_rebase(%s::uuid, gen_random_uuid(), '{}'::jsonb, 'a', 's')",
}


@pg_only
@pytest.mark.parametrize("fn", sorted(_PROMOTION_CALLS))
@pytest.mark.parametrize("role", ["litkb_reader", "litkb_writer"])
def test_agent_roles_cannot_call_promotion_functions(pg, role, fn):
    """D-3: the promoter credential stays in the promote tool, and the agent roles hold no
    EXECUTE on any promotion function. Control: the promoter reaches the function (it is
    refused on the arguments, not on privilege)."""
    agent = pg.session(role)
    with pytest.raises(pg.errors.InsufficientPrivilege):
        agent.execute(_PROMOTION_CALLS[fn], (uuid.uuid4(),))
    promoter = pg.session("litkb_promoter")
    with pytest.raises(pg.psycopg.DatabaseError) as ei:
        promoter.execute(_PROMOTION_CALLS[fn], (uuid.uuid4(),))
    assert not isinstance(ei.value, pg.errors.InsufficientPrivilege), ei.value


@pg_only
@pytest.mark.parametrize("approver_agent, approver_session, allowed", [
    pytest.param("agentA", "sessA", False, id="same_agent_same_session"),
    pytest.param("agentB", "sessA", False, id="other_agent_same_session"),
    pytest.param("agentA", "sessB", True, id="same_agent_other_session"),
    pytest.param("agentB", "sessB", True, id="other_agent_other_session"),
])
def test_admission_approver_must_be_another_session(pg, approver_agent, approver_session, allowed):
    """decisions.yaml litkb-p0-foundation §15.13 as amended after the P1 referee (D-4): the
    approver needs only a different SESSION. Agent names are client-supplied labels, so the same
    name in another session is allowed and another name in the same session is refused
    (migration 0008; the referee's R1/R1b cases are the two mixed rows)."""
    q = ("INSERT INTO litkb.admissions (route, admitter_agent, admitter_session, state, "
         "approver_agent, approver_session, approved_at) VALUES ('manual', 'agentA', 'sessA', "
         "'approved', %s, %s, now())")
    if allowed:
        pg.conn.execute(q, (approver_agent, approver_session))
    else:
        with pytest.raises(pg.errors.CheckViolation, match="admissions_second_session_signs_off"):
            pg.conn.execute(q, (approver_agent, approver_session))


@pg_only
def test_identifier_case_variants_collide(pg):
    """§4.6 check 2: normalised DOIs are unique while active."""
    ws = pg.ws()
    w1, _ = pg.work(ws)
    w2, _ = pg.work(ws)
    q = ("SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, "
         "NULL, %s, 'setup', 'setup')")
    doi = f"10.4171/jems/{uuid.uuid4().hex[:6]}"
    pg.one(q, (pg.Jsonb({"scheme": "doi"}),
               pg.Jsonb({"work_id": str(w1), "value": doi, "status": "active"}), ws))
    with pytest.raises(pg.errors.UniqueViolation):
        pg.one(q, (pg.Jsonb({"scheme": "doi"}),
                   pg.Jsonb({"work_id": str(w2), "value": "https://doi.org/" + doi.upper(),
                             "status": "active"}), ws))


# ── kills ─────────────────────────────────────────────────────────────────────────────────

VERSION_TABLES = ["work_versions", "identifier_versions", "file_versions", "gap_versions",
                  "use_versions"]


@pg_only
@pytest.mark.parametrize("table", VERSION_TABLES)
def test_kill_writer_cannot_update_or_delete_version_rows(pg, table):
    writer = pg.session("litkb_writer")
    writer.execute(f"SELECT count(*) FROM litkb.{table}")   # control: the writer can read it
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(f"UPDATE litkb.{table} SET agent = 'tampered'")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(f"DELETE FROM litkb.{table}")


@pg_only
def test_kill_fact_second_writer_on_same_base_is_refused(pg):
    ws = pg.ws()
    work_id, v1 = pg.work(ws)
    a, b = pg.session("litkb_writer"), pg.session("litkb_writer")
    q = ("SELECT entity_id, version_id FROM litkb.write_fact('work', %s, %s, %s, %s, %s, %s, %s)")
    _, va = pg.one(q, (work_id, v1, pg.Jsonb({"type": "article", "title": "Title fixed by A",
                                              "authors": []}),
                       "title typo", ws, "agentA", "sessA"), conn=a)
    with pytest.raises(pg.errors.SerializationFailure):
        pg.one(q, (work_id, v1, pg.Jsonb({"type": "article", "title": "Title fixed by B",
                                          "authors": []}),
                   "title typo", ws, "agentB", "sessB"), conn=b)
    assert pg.pointer("works", work_id) == va, "main must still point at A's version"
    n = pg.one("SELECT count(*) FROM litkb.work_versions WHERE work_id = %s", (work_id,))[0]
    assert n == 2, "B's refused version must not persist"


@pg_only
def test_kill_proposal_second_writer_on_same_base_is_refused(pg):
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    a, b = pg.session("litkb_writer"), pg.session("litkb_writer")
    use_id, u1 = pg.proposal(a, "use", None, {"work_id": str(work_id)}, None,
                             {"statement": "s v1", "kind": "method", "status": "proposed"}, None, ws)
    _, ua = pg.proposal(a, "use", use_id, None, u1,
                        {"statement": "s v2 by A", "kind": "method", "status": "supported"},
                        "refined", ws)
    with pytest.raises(pg.errors.SerializationFailure):
        pg.proposal(b, "use", use_id, None, u1,
                    {"statement": "s v2 by B", "kind": "method", "status": "refuted"},
                    "refined", ws, agent="agentB", session="sessB")
    head = pg.one("SELECT version_id FROM litkb.ws_heads WHERE workstream_id = %s AND "
                  "entity = 'use' AND entity_id = %s", (ws, use_id))[0]
    assert head == ua, "the workstream head must still be A's version"
    n = pg.one("SELECT count(*) FROM litkb.use_versions WHERE use_id = %s", (use_id,))[0]
    assert n == 2, "B's refused version must not persist"
    assert pg.pointer("uses", use_id) is None, "a proposal never moves main's pointer"


def _evidence_fixture(pg):
    w = _evidence_world(pg)
    return w["uv"], w["block"], w["run"], w["text"]


def _evidence_world(pg):
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    file_id, _ = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, "
        "%s, NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         pg.Jsonb({"work_id": str(work_id), "rel_path": "Validation/Test_2020_x-paper.pdf",
                   "status": "active"}), ws))
    run_id = pg.one(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'test', '0', 'p', 'v0', 'local', "
        "'ok') RETURNING id", (file_id,))[0]
    pg.conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    text = "The optimism identity holds under an arbitrary joint model."
    block_id = pg.one(
        "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES (%s, %s, 1, "
        "'paragraph', %s) RETURNING id", (file_id, run_id, text))[0]
    use_id, uv = pg.proposal(pg.conn, "use", None, {"work_id": str(work_id)}, None,
                             {"statement": "supplies the optimism identity", "kind": "theorem",
                              "status": "supported", "feeds": ["gap row 6"]}, None, ws)
    return dict(ws=ws, work=work_id, file=file_id, run=run_id, block=block_id, text=text,
                use=use_id, uv=uv)


@pg_only
def test_kill_client_quote_verified_is_overwritten(pg):
    uv, block_id, run_id, text = _evidence_fixture(pg)
    q = ("INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, page, quote, "
         "char_start, char_end, stance, quote_verified) VALUES (%s, %s, %s, 1, %s, %s, %s, "
         "'supports', %s) RETURNING quote_verified")
    # as the table owner, so the insert lands and only the trigger stands between the
    # client's value and the stored one
    stored = pg.one(q, (uv, block_id, run_id, "the bootstrap variance", 4, 20, True))[0]
    assert stored is False, "a client-supplied quote_verified=true on a non-matching quote survived"
    stored = pg.one(q, (uv, block_id, run_id, text[4:20], 4, 20, False))[0]
    assert stored is True, "a matching quote must be computed true whatever the client sent"


@pg_only
def test_writer_cannot_name_quote_verified(pg):
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(
            "INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, quote, char_start, "
            "char_end, stance, quote_verified) VALUES (%s, %s, %s, %s, 4, 20, 'supports', true)",
            (w["uv"], w["block"], w["run"], "anything"))
    # control (0007): the writer's way in is add_evidence, which takes no verdict at all
    got = _add_evidence(pg, writer, w, w["ws"], w["uv"], w["text"][4:20], 4, 20)
    assert got[1] is True


@pg_only
def test_kill_test_role_is_refused_by_the_server_on_litkb(pg):
    from litkb.db import connect as c
    with pytest.raises(pg.psycopg.OperationalError) as ei:
        c.connect(c.DB_MAIN, "litkb_test", autocommit=True).close()
    msg = str(ei.value)
    assert "permission denied for database" in msg, (
        "the refusal must come from the server's CONNECT check, not from a missing password "
        f"or an unreachable server: {msg}")
    assert pg.one("SELECT has_database_privilege('litkb_test', 'litkb', 'CONNECT')")[0] is False


@pg_only
def test_kill_promote_commit_refuses_merge_not_on_main(pg, scratch_repo):
    from litkb import promote
    repo, prepared = scratch_repo
    ws = pg.ws()
    writer = pg.session("litkb_writer")
    gap_id, g1 = pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                             {"question": "q", "gap_state": "open"}, None, ws)
    promoter = pg.session("litkb_promoter")
    pid = promote.prepare(promoter, ws, prepared, "Reports/litkb_promotions/test.md")
    with pytest.raises(promote.PromotionRefused, match="not reachable from main"):
        promote.commit(promoter, pid, prepared, repo=repo, fetch_remote=None)
    assert pg.one("SELECT state FROM litkb.promotions WHERE id = %s", (pid,))[0] == "prepared"
    assert pg.pointer("gaps", gap_id) is None, "nothing may move before main has merged"
    # control: once the merge is on main, the same promotion commits
    merge = _merge(repo)
    out = promote.commit(promoter, pid, merge, repo=repo, fetch_remote=None)
    assert out["committed"] == 1 and pg.pointer("gaps", gap_id) == g1
    assert pg.one("SELECT state, merge_commit FROM litkb.workstreams WHERE id = %s", (ws,)) == \
        ("merged", merge)


@pg_only
def test_commit_refuses_a_version_set_changed_after_prepare(pg, scratch_repo):
    from litkb import promote
    repo, prepared = scratch_repo
    ws = pg.ws()
    writer = pg.session("litkb_writer")
    gap_id, g1 = pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                             {"question": "q", "gap_state": "open"}, None, ws)
    promoter = pg.session("litkb_promoter")
    pid = promote.prepare(promoter, ws, prepared, None)
    pg.proposal(writer, "gap", gap_id, None, g1, {"question": "q, sharpened", "gap_state": "open"},
                "sharpened after the report was written", ws)
    merge = _merge(repo)
    with pytest.raises(pg.errors.SerializationFailure, match="changed after promote_prepare"):
        promote.commit(promoter, pid, merge, repo=repo, fetch_remote=None)
    assert pg.pointer("gaps", gap_id) is None


def _dependency_setup(pg):
    """main: work W, gap G at v1. ws1 proposes G v2, use U -> (W, G), use U2 -> (W, no gap)."""
    ws0 = pg.ws()
    work_id, _ = pg.work(ws0)
    gap_id, g1 = pg.main_gap(ws0)
    ws1 = pg.ws()
    writer = pg.session("litkb_writer")
    _, g2 = pg.proposal(writer, "gap", gap_id, None, g1, {"question": "q v2 by ws1", "gap_state": "open"},
                        "sharpened", ws1)
    use_id, _ = pg.proposal(writer, "use", None, {"work_id": str(work_id), "gap_id": str(gap_id)},
                            None, {"statement": "depends on G", "kind": "method", "status": "proposed"},
                            None, ws1)
    use2_id, u2 = pg.proposal(writer, "use", None, {"work_id": str(work_id)}, None,
                              {"statement": "independent", "kind": "context", "status": "proposed"},
                              None, ws1)
    return dict(work=work_id, gap=gap_id, g1=g1, g2=g2, ws1=ws1, use=use_id, use2=use2_id, u2=u2,
                writer=writer)


def _move_main_gap(pg, s, repo, prepared, merge):
    """Another workstream (ws2) promotes its own G v2 first, moving main's pointer."""
    from litkb import promote
    ws2 = pg.ws()
    _, g2b = pg.proposal(s["writer"], "gap", s["gap"], None, s["g1"],
                         {"question": "q v2 by ws2", "gap_state": "open"}, "ws2 got there first",
                         ws2, agent="agentC", session="sessC")
    promoter = pg.session("litkb_promoter")
    pid2 = promote.prepare(promoter, ws2, prepared, None)
    promote.commit(promoter, pid2, merge, repo=repo, fetch_remote=None)
    assert pg.pointer("gaps", s["gap"]) == g2b
    return g2b


@pg_only
def test_kill_conflicting_gap_chain_holds_its_dependent_at_commit(pg, scratch_repo):
    from litkb import promote
    repo, prepared = scratch_repo
    merge = _merge(repo)
    s = _dependency_setup(pg)
    promoter = pg.session("litkb_promoter")
    pid1 = promote.prepare(promoter, s["ws1"], prepared, None)
    counts = pg.one("SELECT counts FROM litkb.promotions WHERE id = %s", (pid1,))[0]
    assert counts["prepared"] == 3, f"all three chains were clean at prepare: {counts}"
    g2b = _move_main_gap(pg, s, repo, prepared, merge)

    out = promote.commit(promoter, pid1, merge, repo=repo, fetch_remote=None)
    held = {h["chain"]: h["reason"] for h in out["held_chains"]}
    assert pg.pointer("gaps", s["gap"]) == g2b, "the conflicting gap chain must not overwrite main"
    assert f"gap:{s['gap']}" in held and held[f"gap:{s['gap']}"].startswith("conflict")
    assert pg.pointer("uses", s["use"]) is None, "the use depending on the held gap chain was promoted"
    assert held.get(f"use:{s['use']}", "").startswith("dependency held"), held
    assert pg.pointer("uses", s["use2"]) == s["u2"], "the independent chain must still be promoted"


@pg_only
def test_kill_conflicting_gap_chain_holds_its_dependent_at_prepare(pg, scratch_repo):
    from litkb import promote
    repo, prepared = scratch_repo
    merge = _merge(repo)
    s = _dependency_setup(pg)
    _move_main_gap(pg, s, repo, prepared, merge)
    promoter = pg.session("litkb_promoter")
    pid1 = promote.prepare(promoter, s["ws1"], prepared, None)
    counts, conflicts = pg.one("SELECT counts, conflicts FROM litkb.promotions WHERE id = %s", (pid1,))
    held = {c["chain"]: c.get("reasons", []) for c in conflicts if "reasons" in c}
    assert f"gap:{s['gap']}" in held, conflicts
    assert f"use:{s['use']}" in held, f"the dependent of a conflicting chain was prepared: {conflicts}"
    states = {r[0] for r in pg.conn.execute(
        "SELECT state FROM litkb.use_versions WHERE use_id = %s", (s["use"],))}
    assert states == {"proposed"}
    assert counts == {"chains": 3, "prepared": 1, "held": 2}


# ── fixes after the referee (migration 0007) ──────────────────────────────────────────────

def _add_evidence(pg, conn, w, ws, uv, quote, start, end):
    return pg.one("SELECT evidence_id, verified FROM litkb.add_evidence(%s, %s, %s, %s, 1, %s, %s, %s, "
                  "'supports')", (ws, uv, w["block"], w["run"], quote, start, end), conn=conn)


def _in_thread(fn):
    box = {}

    def run():
        try:
            box["result"] = fn()
        except BaseException as e:  # handed to the asserting thread
            box["error"] = e
    th = threading.Thread(target=run, daemon=True)
    th.start()
    return th, box


def _wait_blocked(pg, backend_pid, seconds=15.0):
    """True once the backend is observed waiting on another session's lock."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if pg.one("SELECT cardinality(pg_blocking_pids(%s)) > 0", (backend_pid,))[0]:
            return True
        time.sleep(0.05)
    return False


def _holder(pg, role):
    """A SET ROLE'd connection whose transaction stays open until the test commits it."""
    k = pg.session(role)
    k.autocommit = False
    return k


def _backend_pid(pg, conn):
    return pg.one("SELECT pg_backend_pid()", conn=conn)[0]


@pg_only
def test_write_blocked_behind_promote_commit_is_refused(pg):
    """D-1: a writer that waits behind promote_commit must be refused once the workstream is
    merged, not told ok with its version stranded in a closed workstream."""
    ws = pg.ws()
    writer = pg.session("litkb_writer")
    gap_id, g1 = pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                             {"question": "q", "gap_state": "open"}, None, ws)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (ws,), conn=promoter)[0]
    holder = _holder(pg, "litkb_promoter")
    # read the pid BEFORE the thread takes the connection: psycopg serialises use of one
    # connection, so asking it while the thread is blocked in the server would hang here
    writer_pid = _backend_pid(pg, writer)
    try:
        holder.execute("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,))
        th, box = _in_thread(lambda: pg.proposal(
            writer, "gap", gap_id, None, g1, {"question": "q, edited late", "gap_state": "open"},
            "edited while the promotion committed", ws))
        blocked = _wait_blocked(pg, writer_pid)
        holder.commit()
    except BaseException:
        holder.rollback()
        raise
    th.join(30)
    assert blocked, "the writer was never observed waiting behind promote_commit; the race was not exercised"
    assert not th.is_alive()
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (ws,))[0] == "merged"
    assert isinstance(box.get("error"), pg.errors.InvalidParameterValue), (
        f"a write blocked behind promote_commit must be refused (22023), got {box}")
    n = pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (ws,))[0]
    assert n == 0, "a version was stranded in the merged workstream"
    assert pg.one("SELECT count(*) FROM litkb.gap_versions WHERE gap_id = %s", (gap_id,))[0] == 1


@pg_only
@pytest.mark.parametrize("mode", ["fact", "proposal"])
def test_losing_concurrent_writer_gets_40001(pg, mode):
    """D-8: two writers on one base under real concurrency; the loser waits on the identity
    row and is refused with SQLSTATE 40001 (retryable), not 23505."""
    ws = pg.ws()
    work_id, v1 = pg.work(ws)
    b = pg.session("litkb_writer")
    if mode == "fact":
        q = "SELECT entity_id, version_id FROM litkb.write_fact('work', %s, %s, %s, 'fix', %s, %s, %s)"

        def call(conn, who):
            return pg.one(q, (work_id, v1, pg.Jsonb({"type": "article", "title": f"by {who}",
                                                     "authors": []}), ws, who, who), conn=conn)
        entity_id = work_id
    else:
        use_id, u1 = pg.proposal(b, "use", None, {"work_id": str(work_id)}, None,
                                 {"statement": "s v1", "kind": "method", "status": "proposed"}, None, ws)

        def call(conn, who):
            return pg.proposal(conn, "use", use_id, None, u1,
                               {"statement": f"s v2 by {who}", "kind": "method", "status": "proposed"},
                               "refined", ws, agent=who, session=who)
        entity_id = use_id
    a = _holder(pg, "litkb_writer")
    b_pid = _backend_pid(pg, b)   # before the thread takes b (see the D-1 test)
    try:
        _, va = call(a, "agentA")
        th, box = _in_thread(lambda: call(b, "agentB"))
        blocked = _wait_blocked(pg, b_pid)
        a.commit()
    except BaseException:
        a.rollback()
        raise
    th.join(30)
    assert blocked, "writer B was never observed waiting on writer A; the race was not exercised"
    err = box.get("error")
    assert err is not None and getattr(err, "sqlstate", None) == "40001", (
        f"the losing writer must get the retryable 40001, got {box}")
    if mode == "fact":
        assert pg.pointer("works", entity_id) == va
    else:
        head = pg.one("SELECT version_id FROM litkb.ws_heads WHERE workstream_id = %s AND "
                      "entity = 'use' AND entity_id = %s", (ws, entity_id))[0]
        assert head == va


@pg_only
def test_writer_has_no_direct_evidence_insert(pg):
    """D-5: evidence enters only through add_evidence."""
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(
            "INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, quote, char_start, "
            "char_end, stance) VALUES (%s, %s, %s, %s, 4, 20, 'supports')",
            (w["uv"], w["block"], w["run"], w["text"][4:20]))


@pg_only
def test_evidence_guard_workstream_must_be_open(pg):
    w = _evidence_world(pg)
    pg.conn.execute("SELECT litkb.abandon_workstream(%s)", (w["ws"],))
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InvalidParameterValue, match="is not open"):
        _add_evidence(pg, writer, w, w["ws"], w["uv"], w["text"][4:20], 4, 20)


@pg_only
def test_evidence_guard_version_must_belong_to_named_workstream(pg):
    w = _evidence_world(pg)
    other = pg.ws()
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege, match="another workstream"):
        _add_evidence(pg, writer, w, other, w["uv"], w["text"][4:20], 4, 20)
    assert _add_evidence(pg, writer, w, w["ws"], w["uv"], w["text"][4:20], 4, 20)[1] is True


@pg_only
def test_evidence_guard_version_must_be_proposed(pg):
    """A promoted version in a still-open workstream with no promotion: only the state
    guard stands in the way."""
    w = _evidence_world(pg)
    _, promoted = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'use', NULL, %s, NULL, %s, "
        "NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"work_id": str(w["work"])}),
         pg.Jsonb({"statement": "already in main", "kind": "context", "status": "supported"}), w["ws"]))
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="only to a proposed version"):
        _add_evidence(pg, writer, w, w["ws"], promoted, w["text"][4:20], 4, 20)


def _absent_gap_use(pg, w):
    """A use in w's workstream whose gap exists only as another workstream's proposal."""
    writer = pg.session("litkb_writer")
    gap_id, _ = pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                            {"question": "only proposed elsewhere", "gap_state": "open"}, None, pg.ws())
    use_id, uv = pg.proposal(writer, "use", None, {"work_id": str(w["work"]), "gap_id": str(gap_id)},
                             None, {"statement": "needs the absent gap", "kind": "method",
                                    "status": "proposed"}, None, w["ws"])
    return use_id, uv


@pg_only
def test_evidence_guard_refused_while_promotion_prepared(pg):
    """A held chain stays proposed after prepare; evidence on it would change the version-set
    hash and block the prepared commit (the D1 disruption by another route)."""
    w = _evidence_world(pg)
    _, held_uv = _absent_gap_use(pg, w)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)[0]
    assert pg.one("SELECT state FROM litkb.use_versions WHERE version_id = %s", (held_uv,))[0] == "proposed"
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="prepared promotion"):
        _add_evidence(pg, writer, w, w["ws"], held_uv, w["text"][4:20], 4, 20)
    out = pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=promoter)[0]
    assert out["committed"] == 1


@pg_only
def test_referee_bypass_d1_evidence_on_another_workstreams_prepared_version_is_refused(pg):
    w = _evidence_world(pg)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)[0]
    assert pg.one("SELECT state FROM litkb.use_versions WHERE version_id = %s", (w["uv"],))[0] == "prepared"
    writer = pg.session("litkb_writer")
    for named_ws in (pg.ws(), w["ws"]):
        with pytest.raises(pg.psycopg.DatabaseError):
            _add_evidence(pg, writer, w, named_ws, w["uv"], w["text"][4:20], 4, 20)
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(
            "INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, quote, char_start, "
            "char_end, stance) VALUES (%s, %s, %s, %s, 4, 20, 'supports')",
            (w["uv"], w["block"], w["run"], w["text"][4:20]))
    out = pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=promoter)[0]
    assert out["committed"] == 1, f"the victim's commit must still go through: {out}"


@pg_only
def test_referee_bypass_d2_evidence_on_a_promoted_main_version_is_refused(pg):
    w = _evidence_world(pg)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)[0]
    pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=promoter)
    assert pg.pointer("uses", w["use"]) == w["uv"]
    writer = pg.session("litkb_writer")
    for named_ws in (w["ws"], pg.ws()):
        with pytest.raises(pg.psycopg.DatabaseError):
            _add_evidence(pg, writer, w, named_ws, w["uv"], w["text"][4:20], 4, 20)
    n = pg.one("SELECT count(*) FROM litkb.use_evidence WHERE use_version_id = %s", (w["uv"],))[0]
    assert n == 0, "unreviewed evidence entered main"


def _run(pg, conn, file_id, status):
    return pg.one(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'test', '0', %s, 'v0', 'local', %s) "
        "RETURNING id", (file_id, uuid.uuid4().hex, status), conn=conn)[0]


@pg_only
def test_referee_bypass_d5_failed_run_cannot_become_current(pg):
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    _add_evidence(pg, writer, w, w["ws"], w["uv"], w["text"][4:20], 4, 20)
    promotable = ("SELECT count(*) FROM litkb.use_evidence_status WHERE use_version_id = %s "
                  "AND promotable")
    assert pg.one(promotable, (w["uv"],))[0] == 1
    failed = _run(pg, writer, w["file"], "failed")
    with pytest.raises(pg.errors.InvalidParameterValue, match="not an ok extraction run"):
        writer.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], failed))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == w["run"]
    assert pg.one(promotable, (w["uv"],))[0] == 1


@pg_only
def test_set_current_run_refuses_foreign_or_null_run(pg):
    w = _evidence_world(pg)
    other = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    for new_run in (other["run"], None):
        with pytest.raises(pg.errors.InvalidParameterValue, match="not an ok extraction run"):
            writer.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], new_run))
    # control: another ok run of the same file is accepted
    fresh = _run(pg, writer, w["file"], "ok")
    writer.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], fresh))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == fresh


@pg_only
def test_writer_cannot_insert_version_state_columns(pg):
    """D-6 / R2: the writer's direct INSERT on proposal version tables excludes the state and
    promotion columns. Privilege is checked before any constraint, so a NotNullViolation on a
    granted column is the control that the refusal below is the column privilege."""
    writer = pg.session("litkb_writer")
    for table in ("gap_versions", "use_versions"):
        for col in ("state", "promoted_at", "promotion_id"):
            with pytest.raises(pg.errors.InsufficientPrivilege):
                writer.execute(f"INSERT INTO litkb.{table} ({col}) VALUES (NULL)")
        with pytest.raises(pg.errors.NotNullViolation):
            writer.execute(f"INSERT INTO litkb.{table} (agent) VALUES (NULL)")


@pg_only
def test_first_head_proposal_must_be_based_on_main(pg):
    """D-6 / R4: a workstream's FIRST proposal on an entity must be based on main's pointer."""
    ws0 = pg.ws()
    gap_id, g1 = pg.main_gap(ws0)
    _, g2 = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'gap', %s, NULL, %s, %s, "
        "'main moved', %s, 'setup', 'setup')",
        (gap_id, g1, pg.Jsonb({"question": "q v2 in main", "gap_state": "open"}), ws0))
    ws1 = pg.ws()
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.SerializationFailure):
        pg.proposal(writer, "gap", gap_id, None, g1, {"question": "stale", "gap_state": "open"},
                    "based on a version main has left", ws1)
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (ws1,))[0] == 0
    pg.proposal(writer, "gap", gap_id, None, g2, {"question": "fresh", "gap_state": "open"},
                "based on main", ws1)


def _owner_evidence(pg, w, quote, start, end):
    return pg.one(
        "INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, page, quote, char_start, "
        "char_end, stance) VALUES (%s, %s, %s, 1, %s, %s, %s, 'supports') RETURNING quote_verified",
        (w["uv"], w["block"], w["run"], quote, start, end))[0]


@pg_only
def test_quote_verified_checks_offsets_not_presence(pg):
    """D-6 / R6: the quote must sit AT [char_start, char_end), not merely somewhere in the block."""
    w = _evidence_world(pg)
    quote = w["text"][4:20]
    assert _owner_evidence(pg, w, quote, 0, 16) is False, "a quote at the wrong offsets verified"
    assert _owner_evidence(pg, w, quote, 4, 20) is True


@pg_only
def test_quote_char_end_beyond_text_is_refused(pg):
    """D-7: substring() truncates, so char_end past the text let a whole-text quote verify."""
    w = _evidence_world(pg)
    with pytest.raises(pg.errors.CheckViolation, match="beyond"):
        _owner_evidence(pg, w, w["text"], 0, 1_000_000)
    assert _owner_evidence(pg, w, w["text"], 0, len(w["text"])) is True


@pg_only
def test_use_whose_gap_is_absent_is_held_at_prepare(pg):
    """D-6 / R7: a use whose gap is neither in main nor in this promotion is held."""
    w = _evidence_world(pg)
    use_id, _ = _absent_gap_use(pg, w)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)[0]
    counts, conflicts = pg.one("SELECT counts, conflicts FROM litkb.promotions WHERE id = %s", (pid,))
    held = {c["chain"]: c.get("reasons", []) for c in conflicts if "reasons" in c}
    assert any("neither promoted nor in this promotion" in r for r in held.get(f"use:{use_id}", [])), conflicts
    assert counts == {"chains": 2, "prepared": 1, "held": 1}


# ── Kam's decisions on the referee findings (migration 0008) ──────────────────────────────

def _held_world(pg, scratch_repo):
    """The referee's H1: ws1 prepares G v2 + a use depending on G + an independent use; ws2
    promotes its own G v2 first; ws1's commit then holds the gap chain and its dependent."""
    from litkb import promote
    repo, prepared = scratch_repo
    merge = _merge(repo)
    s = _dependency_setup(pg)
    promoter = pg.session("litkb_promoter")
    pid1 = promote.prepare(promoter, s["ws1"], prepared, None)
    g2b = _move_main_gap(pg, s, repo, prepared, merge)
    out = promote.commit(promoter, pid1, merge, repo=repo, fetch_remote=None)
    assert out["committed"] == 1 and out["held"] == 2, out
    s.update(repo=repo, prepared=prepared, merge=merge, promoter=promoter, pid1=pid1, g2b=g2b)
    return s


def _versions(pg, table, fk, entity_id):
    return pg.conn.execute(
        f"SELECT version_id, state, workstream_id, based_on_version_id, rebased_from_version_id "
        f"FROM litkb.{table} WHERE {fk} = %s ORDER BY version_no", (entity_id,)).fetchall()


@pg_only
def test_held_chain_is_rebased_and_promotes(pg, scratch_repo):
    """D-2: replay the referee's stuck case, then rebase the held chains into a fresh workstream
    and promote them on the next prepare and commit."""
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    promoter, writer, ws1 = s["promoter"], s["writer"], s["ws1"]
    # the stuck case, exactly as the referee measured it
    with pytest.raises(pg.errors.InvalidParameterValue):                   # 22023
        promote.prepare(promoter, ws1, s["prepared"], None)
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):            # 55000
        promoter.execute("SELECT litkb.promote_abandon(%s)", (s["pid1"],))
    with pytest.raises(pg.errors.InvalidParameterValue):                   # 22023
        pg.proposal(writer, "gap", s["gap"], None, s["g2"], {"question": "retry", "gap_state": "open"},
                    "retry the held chain", ws1)
    with pytest.raises(pg.errors.InvalidParameterValue):                   # 22023
        writer.execute("SELECT litkb.abandon_workstream(%s)", (ws1,))

    before_gap = _versions(pg, "gap_versions", "gap_id", s["gap"])
    before_use = _versions(pg, "use_versions", "use_id", s["use"])
    onto = promote.held_chains(promoter, ws1)
    assert onto == {f"gap:{s['gap']}": str(s["g2b"]), f"use:{s['use']}": None}, onto
    ws3 = pg.ws()
    out = promote.rebase(promoter, ws1, ws3, onto, "orchestrator", "sess-rebase")
    assert out["rebased"] == 2, out

    # nothing lost: every old version is still there, marked rebased; one new version per chain
    after_gap = _versions(pg, "gap_versions", "gap_id", s["gap"])
    assert [r[0] for r in after_gap[:-1]] == [r[0] for r in before_gap]
    assert {r[1] for r in after_gap if r[0] == s["g2"]} == {"rebased"}, "the held gap version was not marked rebased"
    new_gap = after_gap[-1]
    assert new_gap[1:] == ("proposed", ws3, s["g2b"], s["g2"]), new_gap
    after_use = _versions(pg, "use_versions", "use_id", s["use"])
    assert len(after_use) == len(before_use) + 1
    assert {r[1] for r in after_use[:-1]} == {"rebased"}
    assert after_use[-1][1:] == ("proposed", ws3, None, before_use[-1][0]), after_use[-1]
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (ws1,))[0] == 0, \
        "a rebased chain still heads the merged workstream"
    prov = pg.conn.execute("SELECT entity, source_workstream_id, held_in_promotion_id, old_head_version_id, "
                           "new_version_id FROM litkb.rebases WHERE target_workstream_id = %s ORDER BY entity",
                           (ws3,)).fetchall()
    assert prov == [("gap", ws1, s["pid1"], s["g2"], new_gap[0]),
                    ("use", ws1, s["pid1"], before_use[-1][0], after_use[-1][0])]
    # a second rebase of the same chains finds nothing held
    with pytest.raises(pg.errors.InvalidParameterValue, match="holds no chain"):
        promote.rebase(promoter, ws1, pg.ws(), onto, "orchestrator", "sess-rebase")

    # the next prepare and commit promote them
    pid3 = promote.prepare(promoter, ws3, s["prepared"], None)
    counts = pg.one("SELECT counts FROM litkb.promotions WHERE id = %s", (pid3,))[0]
    assert counts == {"chains": 2, "prepared": 2, "held": 0}, counts
    out = promote.commit(promoter, pid3, s["merge"], repo=s["repo"], fetch_remote=None)
    assert out["committed"] == 2 and out["held"] == 0, out
    assert pg.pointer("gaps", s["gap"]) == new_gap[0]
    assert pg.pointer("uses", s["use"]) == after_use[-1][0]


@pg_only
def test_kill_rebase_onto_stale_main_is_refused(pg, scratch_repo):
    """D-2 kill: the rebase was reviewed against main at g2b; main moved to g3 before it ran."""
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    promoter = s["promoter"]
    onto = promote.held_chains(promoter, s["ws1"])
    pg.one("SELECT entity_id, version_id FROM litkb._write_version('fact', 'gap', %s, NULL, %s, %s, "
           "'main moved again', %s, 'setup', 'setup')",
           (s["gap"], s["g2b"], pg.Jsonb({"question": "q v3 in main", "gap_state": "open"}), pg.ws()))
    n_before = pg.one("SELECT count(*) FROM litkb.gap_versions WHERE gap_id = %s", (s["gap"],))[0]
    ws3 = pg.ws()
    with pytest.raises(pg.errors.SerializationFailure, match="CAS refused"):
        promote.rebase(promoter, s["ws1"], ws3, onto, "orchestrator", "sess-rebase")
    assert pg.one("SELECT count(*) FROM litkb.gap_versions WHERE gap_id = %s", (s["gap"],))[0] == n_before
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (s["ws1"],))[0] == 2
    assert pg.one("SELECT count(*) FROM litkb.rebases WHERE source_workstream_id = %s", (s["ws1"],))[0] == 0
    # control: re-read main, review again, and the rebase goes through
    out = promote.rebase(promoter, s["ws1"], ws3, promote.held_chains(promoter, s["ws1"]),
                         "orchestrator", "sess-rebase")
    assert out["rebased"] == 2


@pg_only
def test_rebase_guard_source_must_be_merged(pg):
    """An open workstream's chains are live; rebasing them would fork them."""
    from litkb import promote
    ws = pg.ws()
    writer = pg.session("litkb_writer")
    pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                {"question": "q", "gap_state": "open"}, None, ws)
    promoter = pg.session("litkb_promoter")
    with pytest.raises(pg.errors.InvalidParameterValue, match="is not merged"):
        promote.rebase(promoter, ws, pg.ws(), promote.held_chains(promoter, ws), "o", "s")


@pg_only
def test_rebase_guard_target_must_be_open(pg, scratch_repo):
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    closed = pg.ws()
    pg.conn.execute("SELECT litkb.abandon_workstream(%s)", (closed,))
    with pytest.raises(pg.errors.InvalidParameterValue, match="target workstream"):
        promote.rebase(s["promoter"], s["ws1"], closed, promote.held_chains(s["promoter"], s["ws1"]), "o", "s")


@pg_only
def test_rebase_guard_target_has_no_prepared_promotion(pg, scratch_repo):
    """A rebase into a workstream with a prepared promotion would change its version set."""
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    target = pg.ws()
    pg.proposal(s["writer"], "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                {"question": "q", "gap_state": "open"}, None, target)
    promote.prepare(s["promoter"], target, s["prepared"], None)
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="prepared promotion"):
        promote.rebase(s["promoter"], s["ws1"], target, promote.held_chains(s["promoter"], s["ws1"]), "o", "s")


@pg_only
def test_rebase_guard_target_has_no_head_for_the_entity(pg, scratch_repo):
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    target = pg.ws()
    pg.proposal(s["writer"], "gap", s["gap"], None, s["g2b"], {"question": "own edit", "gap_state": "open"},
                "the target's own edit", target)
    with pytest.raises(pg.errors.InvalidParameterValue, match="already has a chain"):
        promote.rebase(s["promoter"], s["ws1"], target, promote.held_chains(s["promoter"], s["ws1"]), "o", "s")


@pg_only
def test_rebase_carries_evidence(pg):
    """Nothing is lost: evidence on a held use chain is copied onto the rebased version and
    re-verified by the trigger; the original rows stay on the original version."""
    from litkb import promote
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    _, held_uv = _absent_gap_use(pg, w)
    _add_evidence(pg, writer, w, w["ws"], held_uv, w["text"][4:20], 4, 20)
    promoter = pg.session("litkb_promoter")
    pid = promote.prepare(promoter, w["ws"], "a" * 40, None)
    out = pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=promoter)[0]
    assert out["held"] == 1, out
    target = pg.ws()
    res = promote.rebase(promoter, w["ws"], target, promote.held_chains(promoter, w["ws"]), "o", "s")
    new_uv = res["chains"][0]["new_version"]
    assert res["chains"][0]["evidence_copied"] == 1
    rows = pg.conn.execute("SELECT quote, char_start, char_end, quote_verified FROM litkb.use_evidence "
                           "WHERE use_version_id = %s", (new_uv,)).fetchall()
    assert rows == [(w["text"][4:20], 4, 20, True)]
    assert pg.one("SELECT count(*) FROM litkb.use_evidence WHERE use_version_id = %s", (held_uv,))[0] == 1

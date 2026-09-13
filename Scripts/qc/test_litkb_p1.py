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

Isolation: the suite logs in ONLY as litkb_test, to litkb_test, which it resets and migrates
once per session under an advisory lock (parallel worktrees serialise). Role privileges are
exercised with SET ROLE: litkb_test is a member of reader/writer/promoter WITH INHERIT FALSE,
so it inherits none of their privileges — including the writer's CONNECT on litkb.
"""
import os
import subprocess
import sys
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


@pg_only
def test_admitter_cannot_approve_own_manual_admission(pg):
    """decisions.yaml litkb-p0-foundation §15.13: the database refuses admitter = approver."""
    q = ("INSERT INTO litkb.admissions (route, admitter_agent, admitter_session, state, "
         "approver_agent, approver_session, approved_at) VALUES ('manual', 'agentA', 'sessA', "
         "'approved', %s, %s, now())")
    with pytest.raises(pg.errors.CheckViolation):
        pg.conn.execute(q, ("agentA", "sessA"))
    pg.conn.execute(q, ("agentB", "sessB"))


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
    _, uv = pg.proposal(pg.conn, "use", None, {"work_id": str(work_id)}, None,
                        {"statement": "supplies the optimism identity", "kind": "theorem",
                         "status": "supported", "feeds": ["gap row 6"]}, None, ws)
    return uv, block_id, run_id, text


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
    uv, block_id, run_id, text = _evidence_fixture(pg)
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(
            "INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, quote, char_start, "
            "char_end, stance, quote_verified) VALUES (%s, %s, %s, %s, 4, 20, 'supports', true)",
            (uv, block_id, run_id, "anything"))
    got = writer.execute(
        "INSERT INTO litkb.use_evidence (use_version_id, block_id, run_id, quote, char_start, "
        "char_end, stance) VALUES (%s, %s, %s, %s, 4, 20, 'supports') RETURNING id",
        (uv, block_id, run_id, text[4:20])).fetchone()
    assert got is not None


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

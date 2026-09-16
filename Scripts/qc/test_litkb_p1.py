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

Fixes after the second referee (Reports/LITKB_P1_REFEREE2_2026-09-13.md), migration 0009 and
connect.py; each referee mutation X1-X4, X7-X9 now fails this file (harness rows of the same ids):

  E-1  promote_commit's FOR UPDATE on the workstream (X9)     test_commit_waits_for_a_write_in_flight_and_is_refused
  E-2  promote_rebase's source-row lock (X2)                  test_concurrent_rebases_of_one_workstream_make_one_copy
       … and identity-row lock (X3)                           test_rebase_during_a_commit_that_moves_main_is_refused
  E-3  onto names exactly the held chains (X4)                test_rebase_onto_must_name_exactly_the_held_chains[*]
  E-4  labels non-blank after trim, compared trimmed (X7)     test_admission_approver_must_be_another_session[*]
  E-6  add_evidence's FOR SHARE (X1)                          test_add_evidence_waits_for_a_prepare_in_flight_and_is_refused
  E-7  set_current_run compare-and-set (X8)                   test_set_current_run_refuses_a_stale_expected_run
  E-8  connect() refusal survives injection / whitespace      test_connect_refuses_promoter_login_bypasses[*],
                                                              test_conninfo_quotes_values

Kam's decisions after the second referee (decisions.yaml litkb-p0-foundation), migration 0010;
each guard shown to fire on the WHOLE file by the harness (rows X5, X6, E5a, T*, I*):

  E-5  rebase copies the head's evidence only, column-equal   test_rebase_carries_evidence,
                                                              test_rebase_copies_only_the_head_versions_evidence
  tok  open_workstream returns a token, stores only its hash  test_open_workstream_returns_a_token_stored_only_as_its_hash
       the referee's cross-session add_evidence is refused    test_referee_cross_session_evidence_insert_is_refused
       every writer function naming a workstream needs it    test_every_workstream_write_requires_its_token[*]
       no token-less overload survives                        test_token_functions_have_exactly_one_signature
       the token file is git-ignored and written once         test_workstream_token_file_is_git_ignored,
                                                              test_workstream_module_writes_the_token_file_once
  ing  the writer cannot install a run or make it current     test_writer_cannot_install_a_run_or_make_it_current
       the ingest login can; it cannot write knowledge        test_ingest_installs_a_run_and_makes_it_current,
                                                              test_ingest_cannot_write_knowledge
       connect() refuses the ingest login                     test_connect_refuses_the_ingest_login

The token bypass closed (migration 0011): the writer's direct INSERT on tables that belong to a
workstream is revoked, and every writer path into a workstream is a token-checked function; each
guard shown to fire on the WHOLE file by the harness (rows W*, R2):

  direct INSERT refused, the same row accepted as owner      test_writer_has_no_direct_write_on_workstream_tables[*]
  new functions need the token                               test_every_workstream_write_requires_its_token[*]
  an embedding goes only onto the workstream's own version   test_add_use_embedding_version_must_belong_to_named_workstream
  no agent role gains a direct write later (catalog-built)   test_no_agent_role_holds_a_direct_write_on_a_workstream_table

Fixes after the third referee (Reports/LITKB_P1_REFEREE3_2026-09-13.md), migration 0012, workstream.py and
connect.py; each referee mutation Z1, Z2, Z5-Z10, Z12 now fails this file (harness rows of the same ids):

  F-1  catalog guard: every relkind, workstream_id without FK,  test_no_agent_role_holds_a_direct_write_on_a_workstream_table,
       any FK depth, roles reached by INHERIT or SET, ACLs    test_catalog_guard_fires_on_new_workstream_bearing_relations
  F-2  no abandon while a promotion is prepared (and waits)   test_abandon_refused_while_promotion_prepared,
                                                              test_abandon_waits_for_a_prepare_in_flight_and_is_refused
  F-3  add_use_embedding: open workstream, proposed version   test_add_use_embedding_refuses_a_closed_workstreams_token,
       waits for a commit in flight                           test_add_use_embedding_refuses_a_promoted_or_prepared_version,
                                                              test_add_use_embedding_waits_for_a_commit_in_flight_and_is_refused
  F-4  empty and upper-cased tokens; token not from the slug  test_every_workstream_write_requires_its_token[*],
                                                              test_workstream_token_is_not_derived_from_the_slug_or_id
  F-5  per-role privilege matrix; token hashes via any view   test_role_privilege_matrix,
                                                              test_no_agent_role_reads_token_hashes_through_any_relation
  F-6  rebase copies head evidence of a superseded run        test_rebase_copies_head_evidence_whose_run_was_superseded
  F-7  open_workstream is atomic with its token file          test_open_workstream_race_in_one_directory_leaves_no_orphan,
                                                              test_open_workstream_failure_leaves_no_workstream_and_no_file
  F-8  the token is bound, never in pg_stat_activity.query    test_token_is_bound_never_visible_in_pg_stat_activity
  F-9  connect() refuses postgres and litkb_owner             test_connect_refuses_the_admin_logins,
                                                              test_admin_logins_open_only_through_connect_admin

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
            "litkb.db.provision, litkb.promote, litkb.ingest, litkb.workstream\n"
            "heavy = {'psycopg', 'torch', 'docling', 'mineru', 'numpy', 'pandas', 'pypdfium2'}\n"
            "pulled = sorted(heavy & {m.split('.')[0] for m in sys.modules})\n"
            "print(pulled)\n"
            "sys.exit(1 if pulled else 0)\n")
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS / "pipeline"))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"import litkb pulled heavy modules: {r.stdout}{r.stderr}"


def test_migration_files_are_named_and_numbered():
    """1..N with no gaps — except a number another open branch has RESERVED in `_reserved.txt`.

    The rule catches a migration that went missing. It cannot tell that from a number a concurrent
    branch is about to take, and with several branches open at once the second case is the ordinary
    one: 0020 was written here while 0018 and 0019 were being written on
    `work/20260915-access-layer`. A reserved number is a DECLARED gap; every other gap still fails,
    which the next test is for.
    """
    from litkb.db import migrate
    found = migrate.discover()
    held = migrate.reserved()
    assert [v for v, *_ in found] == [n for n in range(1, len(found) + len(held) + 1) if n not in held]
    assert not (held.keys() & {v for v, *_ in found}), "a number on disk must not also be reserved"
    assert all(why for why in held.values()), "a reserved number says which branch holds it and why"


def test_an_undeclared_gap_in_the_migration_numbering_is_still_refused(tmp_path):
    """The same hole, refused when nothing declares it and allowed when something does.

    The gap is MANUFACTURED here. It used to be borrowed: the test copied the tree's own migrations
    into tmp_path and leaned on 0018/0019 being absent from disk while `work/20260915-access-layer`
    held them. The moment that branch merged (2026-09-16) the numbering went contiguous, nothing was
    refused, and the `pytest.raises` had nothing to catch — the test had been asserting a property of
    the repository's transient state, not of the rule. It now digs its own hole, in the MIDDLE:
    deleting the LAST migration is not a gap at all, it is a shorter list, and `discover` cannot
    distinguish that from a branch that has not written its next migration yet.
    """
    from litkb.db import migrate
    found = migrate.discover()
    for _v, name, _s, sql_text in found:
        (tmp_path / name).write_text(sql_text, encoding="utf-8")
    hole_v, hole_name = found[len(found) // 2][0], found[len(found) // 2][1]
    assert hole_v < found[-1][0], "the hole must be in the middle, not the tail"
    (tmp_path / hole_name).unlink()
    declared = tmp_path / "_reserved.txt"
    with pytest.raises(migrate.MigrationError, match="without gaps"):
        migrate.discover(tmp_path, reserved_path=declared)                       # undeclared: refused
    declared.write_text(f"{hole_v:04d}  a branch that has not merged here yet\n", encoding="utf-8")
    assert len(migrate.discover(tmp_path, reserved_path=declared)) == len(found) - 1   # declared: ok


def test_connect_refuses_the_promoter_login(monkeypatch):
    """D-3: the promoter login has one connection path, litkb.promote.connect(). The shared
    connect() that agents' reader and writer connections use refuses it before any driver is
    loaded, and the promote tool's path names the promoter's own passfile."""
    from litkb import promote
    from litkb.db import connect as c
    with monkeypatch.context() as m:     # no driver importable: the refusal must come first
        m.setitem(sys.modules, "psycopg", None)
        m.setitem(sys.modules, "psycopg.conninfo", None)
        with pytest.raises(c.PromoterLoginRefused):
            c.connect(c.DB_MAIN, c.PROMOTER)
    pytest.importorskip("psycopg")   # conninfo() quotes through psycopg (referee 2, E-8)
    info = c.conninfo(c.DB_MAIN, c.PROMOTER, passfile=c.promoter_passfile())
    assert "passfile=" in info and "litkb_promoter" in info
    assert "passfile=" not in c.conninfo(c.DB_MAIN, "litkb_writer")
    assert callable(promote.connect)


@pytest.mark.parametrize("dbname, user", [
    pytest.param("litkb", "litkb_writer user=litkb_promoter passfile=promoter.pgpass", id="keyword_injection"),
    pytest.param("litkb", "litkb_promoter ", id="trailing_space"),
    pytest.param("litkb", " litkb_promoter", id="leading_space"),
    pytest.param("litkb", "litkb_promoter\t", id="trailing_tab"),
    pytest.param("litkb user=litkb_promoter", "litkb_writer", id="injection_through_dbname"),
    pytest.param("litkb", "", id="empty_user_falls_back_to_PGUSER"),
    # the ingest login (0010) has the same single path
    pytest.param("litkb", "litkb_writer user=litkb_ingest passfile=ingest.pgpass", id="ingest_keyword_injection"),
    pytest.param("litkb", "litkb_ingest ", id="ingest_trailing_space"),
    # third referee F-9: the superuser and owner logins go only through connect_admin()
    pytest.param("litkb", "postgres ", id="superuser_trailing_space"),
    pytest.param("litkb", "litkb_writer user=litkb_owner", id="owner_keyword_injection"),
    pytest.param("litkb", "Postgres", id="superuser_upper_case"),
])
def test_connect_refuses_promoter_login_bypasses(monkeypatch, dbname, user):
    """Referee 2, E-8: the refusal used to be a string compare over an unquoted conninfo, so an
    injected second `user=` keyword, or the promoter's name with a trailing space, connected as the
    promoter. Each bypass must be refused before the driver is reached."""
    from litkb.db import connect as c

    def reached(*_a, **_k):
        raise AssertionError(f"connect() reached the driver for dbname={dbname!r} user={user!r}")
    monkeypatch.setattr(c, "_open", reached)
    with pytest.raises(c.LoginRefused):
        c.connect(dbname, user)


def test_conninfo_quotes_values():
    """E-8: a value is one value. The parsed connection string gives back exactly the string
    passed, never a keyword smuggled inside it."""
    pytest.importorskip("psycopg")
    from psycopg.conninfo import conninfo_to_dict

    from litkb.db import connect as c
    injected = "litkb_writer user=litkb_promoter passfile=promoter.pgpass"
    params = conninfo_to_dict(c.conninfo(c.DB_MAIN, injected))
    assert params["user"] == injected and "passfile" not in params, params
    params = conninfo_to_dict(c.conninfo(c.DB_MAIN, c.PROMOTER, passfile=r"D:\a b\it's.pgpass"))
    assert params["passfile"] == r"D:\a b\it's.pgpass" and params["user"] == c.PROMOTER, params


# ── harness ───────────────────────────────────────────────────────────────────────────────

_OWN = object()   # "use the workstream's own token"


class _PG:
    def __init__(self, psycopg, conn, ran):
        from psycopg.types.json import Jsonb
        self.psycopg = psycopg
        self.errors = psycopg.errors
        self.Jsonb = Jsonb
        self.conn = conn          # litkb_test session = the test DB's owner
        self.ran = ran
        self.opened = []
        self.tokens = {}          # workstream id -> the token open_workstream returned (0010)

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
    def ws(self, conn=None):
        ws_id, token = self.one(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/test', NULL, 'p1 test', NULL)",
            (f"t-{uuid.uuid4().hex[:12]}",), conn=conn)
        self.tokens[ws_id] = token
        return ws_id

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
                 agent="agentA", session="sessA", token=_OWN):
        return self.one(
            "SELECT entity_id, version_id FROM litkb.write_proposal(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (entity, entity_id, self.Jsonb(identity) if identity else None, based_on,
             self.Jsonb(fields), reason, ws, self.token(ws, token), agent, session), conn=conn)

    def token(self, ws, token=_OWN):
        """The workstream's own token unless the test passes another (or None)."""
        return self.tokens.get(ws) if token is _OWN else token

    def pointer(self, table, entity_id):
        return self.one(f"SELECT current_version_id FROM litkb.{table} WHERE id = %s", (entity_id,))[0]


@pytest.fixture(scope="session")
def _pg_session(litkb_pg_base):
    """The reset, migration and suite lock live in qc/conftest.py (litkb_pg_base), shared with the P2 suite:
    two session fixtures each holding the advisory lock on their own connection would deadlock in one run."""
    psycopg, conn, ran = litkb_pg_base
    yield _PG(psycopg, conn, ran)


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
    # the declared gaps travel with the copy, or the copy is a set of files with a hole in it
    (tmp_path / migrate.RESERVED_FILE.name).write_bytes(migrate.RESERVED_FILE.read_bytes())
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


_SIGN_OFF = "admissions_second_session_signs_off"
_ADMITTER = "admissions_admitter_not_blank"


@pg_only
@pytest.mark.parametrize("admitter_agent, admitter_session, approver_agent, approver_session, refused_by", [
    pytest.param("agentA", "sessA", "agentA", "sessA", _SIGN_OFF, id="same_agent_same_session"),
    pytest.param("agentA", "sessA", "agentB", "sessA", _SIGN_OFF, id="other_agent_same_session"),
    pytest.param("agentA", "sessA", "agentA", "sessB", None, id="same_agent_other_session"),
    pytest.param("agentA", "sessA", "agentB", "sessB", None, id="other_agent_other_session"),
    # referee 2, E-4 (migration 0009): labels compare trimmed, and must be non-blank after trim
    pytest.param("agentA", "sessA", "agentB", None, _SIGN_OFF, id="null_approver_session"),
    pytest.param("agentA", "sessA", "agentB", "", _SIGN_OFF, id="empty_approver_session"),
    pytest.param("agentA", "sessA", "agentB", "   ", _SIGN_OFF, id="blank_approver_session"),
    pytest.param("agentA", "sessA", "agentB", "sessA ", _SIGN_OFF, id="approver_session_trailing_space"),
    pytest.param("agentA", "sessA ", "agentB", "sessA", _SIGN_OFF, id="admitter_session_trailing_space"),
    pytest.param("agentA", "sessA", "", "sessB", _SIGN_OFF, id="empty_approver_agent"),
    pytest.param("agentA", "sessA", " \t", "sessB", _SIGN_OFF, id="blank_approver_agent"),
    pytest.param("agentA", "   ", "agentB", "sessB", _ADMITTER, id="blank_admitter_session"),
    pytest.param(" ", "sessA", "agentB", "sessB", _ADMITTER, id="blank_admitter_agent"),
])
def test_admission_approver_must_be_another_session(pg, admitter_agent, admitter_session, approver_agent,
                                                    approver_session, refused_by):
    """decisions.yaml litkb-p0-foundation §15.13 as amended after the P1 referee (D-4): the
    approver needs only a different SESSION. Agent names are client-supplied labels, so the same
    name in another session is allowed and another name in the same session is refused
    (the referee's R1/R1b cases are the two mixed rows). After referee 2 (E-4, migration 0009):
    every label must be non-blank after btrim, and sessions compare after btrim on both sides
    (case-sensitive). The NULL-session row pins the IS NOT NULL clause (a CHECK that is NULL passes)."""
    q = ("INSERT INTO litkb.admissions (route, admitter_agent, admitter_session, state, "
         "approver_agent, approver_session, approved_at) VALUES ('manual', %s, %s, "
         "'approved', %s, %s, now())")
    args = (admitter_agent, admitter_session, approver_agent, approver_session)
    if refused_by is None:
        pg.conn.execute(q, args)
    else:
        with pytest.raises(pg.errors.CheckViolation, match=refused_by):
            pg.conn.execute(q, args)


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
    q = ("SELECT entity_id, version_id FROM litkb.write_fact('work', %s, %s, %s, %s, %s, %s, %s, %s)")
    _, va = pg.one(q, (work_id, v1, pg.Jsonb({"type": "article", "title": "Title fixed by A",
                                              "authors": []}),
                       "title typo", ws, pg.tokens[ws], "agentA", "sessA"), conn=a)
    with pytest.raises(pg.errors.SerializationFailure):
        pg.one(q, (work_id, v1, pg.Jsonb({"type": "article", "title": "Title fixed by B",
                                          "authors": []}),
                   "title typo", ws, pg.tokens[ws], "agentB", "sessB"), conn=b)
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


def _make_promotable(pg, w, uv=None, block=None, run=None):
    """Attach ONE verified quote to a use of w's world, so that a prepare in a test about something
    else is not held by migration 0019.

    0019 holds a use with no promotable evidence row (P8 referee §3.6: a use with no quote at all
    reached `prepared`, which is the convention error). The world itself must stay evidence-free —
    several tests assert `count(*) = 0` on its use to show that a refused write wrote nothing — so
    the row is attached HERE, in the tests that go on to prepare, and the span (21:40) is
    deliberately not the 4:20 / 0:3 the evidence tests use so it cannot collide with a row a test
    adds itself."""
    return pg.one(
        "SELECT evidence_id, verified FROM litkb.add_evidence(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (w["ws"], pg.tokens[w["ws"]], uv or w["uv"], block or w["block"], run or w["run"], 1,
         w["text"][21:40], 21, 40, "supports"))


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
    # Both uses carry a verified quote, for the reason given in _evidence_world: 0019 holds a use
    # with no promotable evidence, and what these tests are about is the DEPENDENCY between a use and
    # its gap. A file and a block are needed to have a quote to verify against, so the setup builds
    # the smallest one that is a real file version of the work.
    file_id, _fv = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, "
        "%s, NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         pg.Jsonb({"work_id": str(work_id), "rel_path": "Validation/Dependency_2020_x.pdf",
                   "status": "active"}), ws0))
    run_id = pg.one(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'test', '0', 'p', 'v0', 'local', "
        "'ok') RETURNING id", (file_id,))[0]
    pg.conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    text = "The dependency between a use and its gap is what this world is about."
    block_id = pg.one(
        "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES (%s, %s, 1, "
        "'paragraph', %s) RETURNING id", (file_id, run_id, text))[0]
    for uv in (pg.one("SELECT version_id FROM litkb.use_versions WHERE use_id = %s", (use_id,))[0],
               u2):
        pg.one("SELECT evidence_id, verified FROM litkb.add_evidence(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
               (ws1, pg.tokens[ws1], uv, block_id, run_id, 1, text[4:30], 4, 30, "supports"))
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

def _add_evidence(pg, conn, w, ws, uv, quote, start, end, *, page=1, stance="supports", token=_OWN):
    return pg.one("SELECT evidence_id, verified FROM litkb.add_evidence(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                  (ws, pg.token(ws, token), uv, w["block"], w["run"], page, quote, start, end, stance),
                  conn=conn)


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


def _wait_blocked(pg, backend_pid, seconds=15.0, thread=None):
    """True once the backend is observed waiting on another session's lock. With `thread`, stop
    early (False) when that thread has finished without ever being seen waiting: a guard whose
    lock is removed does not block, and the test must then fail on the outcome, not time out."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if pg.one("SELECT cardinality(pg_blocking_pids(%s)) > 0", (backend_pid,))[0]:
            return True
        if thread is not None and not thread.is_alive():
            return False
        time.sleep(0.05)
    return False


def _race(pg, holder, hold, waiter, wait):
    """Deterministic two-connection race. `hold(holder)` runs inside the holder's open
    transaction; `wait(waiter)` then starts in a thread on its own connection; the waiter is
    observed blocked on the holder (or seen to finish without blocking); only then does the
    holder commit. Returns (blocked, box) with box["result"] or box["error"] from the waiter."""
    waiter_pid = _backend_pid(pg, waiter)   # before the thread takes the connection
    try:
        hold(holder)
        th, box = _in_thread(lambda: wait(waiter))
        blocked = _wait_blocked(pg, waiter_pid, thread=th)
        holder.commit()
    except BaseException:
        holder.rollback()
        raise
    th.join(30)
    assert not th.is_alive(), "the waiting connection never returned"
    return blocked, box


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
        q = "SELECT entity_id, version_id FROM litkb.write_fact('work', %s, %s, %s, 'fix', %s, %s, %s, %s)"

        def call(conn, who):
            return pg.one(q, (work_id, v1, pg.Jsonb({"type": "article", "title": f"by {who}",
                                                     "authors": []}), ws, pg.tokens[ws], who, who), conn=conn)
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
    pg.conn.execute("SELECT litkb.abandon_workstream(%s, %s)", (w["ws"], pg.tokens[w["ws"]]))
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
    # 0019 holds a use with no verified quote; this test's subject is elsewhere, so the
    # world's use is given one and reaches `prepared` as it did before.
    _make_promotable(pg, w)
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
    # 0019 holds a use with no verified quote; this test's subject is elsewhere, so the
    # world's use is given one and reaches `prepared` as it did before.
    _make_promotable(pg, w)
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
    # 0019 holds a use with no verified quote; this test's subject is elsewhere, so the
    # world's use is given one and reaches `prepared` as it did before.
    _make_promotable(pg, w)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)[0]
    pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=promoter)
    assert pg.pointer("uses", w["use"]) == w["uv"]
    writer = pg.session("litkb_writer")
    for named_ws in (w["ws"], pg.ws()):
        with pytest.raises(pg.psycopg.DatabaseError):
            _add_evidence(pg, writer, w, named_ws, w["uv"], w["text"][4:20], 4, 20)
    n = pg.one("SELECT count(*) FROM litkb.use_evidence WHERE use_version_id = %s", (w["uv"],))[0]
    # 1, not 0: the setup's own verified quote (0019 needs one for this use to promote at all).
    # What the refusals above must not do is ADD to it.
    assert n == 1, "unreviewed evidence entered main"


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
    ingest = pg.session("litkb_ingest")   # 0010: runs and the current-run pointer are ingest's
    failed = _run(pg, ingest, w["file"], "failed")
    with pytest.raises(pg.errors.InvalidParameterValue, match="not an ok extraction run"):
        ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], failed))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == w["run"]
    assert pg.one(promotable, (w["uv"],))[0] == 1


@pg_only
def test_set_current_run_refuses_foreign_or_null_run(pg):
    w = _evidence_world(pg)
    other = _evidence_world(pg)
    ingest = pg.session("litkb_ingest")
    for new_run in (other["run"], None):
        with pytest.raises(pg.errors.InvalidParameterValue, match="not an ok extraction run"):
            ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], new_run))
    # control: another ok run of the same file is accepted
    fresh = _run(pg, ingest, w["file"], "ok")
    ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], fresh))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == fresh


@pg_only
def test_writer_cannot_insert_version_state_columns(pg):
    """D-6 / R2: the writer names no state or promotion column of a proposal version table. Since
    0011 the writer holds no INSERT on those tables at all (proposals go only through
    write_proposal), so the formerly granted `agent` column is refused too; the owner's
    NotNullViolation on the same statement is the control that the refusal is privilege."""
    writer = pg.session("litkb_writer")
    for table in ("gap_versions", "use_versions"):
        for col in ("state", "promoted_at", "promotion_id", "agent", "workstream_id"):
            with pytest.raises(pg.errors.InsufficientPrivilege):
                writer.execute(f"INSERT INTO litkb.{table} ({col}) VALUES (NULL)")
        with pytest.raises(pg.errors.NotNullViolation):
            pg.conn.execute(f"INSERT INTO litkb.{table} (agent) VALUES (NULL)")


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
    # 0019 holds a use with no verified quote; this test's subject is elsewhere, so the
    # world's use is given one and reaches `prepared` as it did before.
    _make_promotable(pg, w)
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
        writer.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws1, pg.tokens[ws1]))

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
    pg.conn.execute("SELECT litkb.abandon_workstream(%s, %s)", (closed, pg.tokens[closed]))
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


_EVIDENCE_COLS = "block_id, run_id, page, quote, char_start, char_end, stance, quote_verified"


def _evidence_rows(pg, version_id):
    return sorted(pg.conn.execute(f"SELECT {_EVIDENCE_COLS} FROM litkb.use_evidence WHERE use_version_id = %s",
                                  (version_id,)).fetchall(), key=repr)


def _hold_and_rebase(pg, w, promotable=True):
    """Prepare and commit w's workstream (its use on an absent gap is held), then rebase what is
    held into a fresh workstream. Returns the rebase result's single chain entry."""
    from litkb import promote
    promoter = pg.session("litkb_promoter")
    # 0019: without a quote the world's own use would be held too, and `held == 1` — the assertion
    # that says the ABSENT-GAP use is the one held — would fail for a reason this test is not about.
    if promotable:
        _make_promotable(pg, w)
    pid = promote.prepare(promoter, w["ws"], "a" * 40, None)
    out = pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=promoter)[0]
    assert out["held"] == 1, out
    res = promote.rebase(promoter, w["ws"], pg.ws(), promote.held_chains(promoter, w["ws"]), "o", "s")
    assert res["rebased"] == 1, res
    return res["chains"][0]


@pg_only
def test_rebase_carries_evidence(pg):
    """E-5: the head's evidence is copied onto the rebased version with every column equal to its
    source (block, run, page, quote, offsets, stance) and quote_verified recomputed by the trigger
    to the same value. The rows include a refutes row on page 7 and an unverified context row, so a
    copy that forces page 1 / 'supports' (referee X6) or shifts an offset cannot pass."""
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    _, held_uv = _absent_gap_use(pg, w)
    _add_evidence(pg, writer, w, w["ws"], held_uv, w["text"][4:20], 4, 20)
    _add_evidence(pg, writer, w, w["ws"], held_uv, w["text"][0:3], 0, 3, page=7, stance="refutes")
    _add_evidence(pg, writer, w, w["ws"], held_uv, "not at these offsets", 10, 30, page=2, stance="context")
    source = _evidence_rows(pg, held_uv)
    assert {r[6] for r in source} == {"supports", "refutes", "context"} and {r[7] for r in source} == {True, False}
    chain = _hold_and_rebase(pg, w)
    assert chain["old_head"] == str(held_uv)
    assert chain["evidence_copied"] == 3
    assert _evidence_rows(pg, chain["new_version"]) == source, "a copied evidence column differs from its source"
    assert _evidence_rows(pg, held_uv) == source, "the original rows must stay on the original version"


@pg_only
def test_rebase_copies_only_the_head_versions_evidence(pg):
    """E-5 (Kam): a rebase carries exactly what promotion would. Evidence attached to v1 and not
    to the head v2 never reaches main on the promote path (main's current version carries only its
    own rows), so the rebased copy of a chain whose head has no evidence has none (referee X5: the
    old copy took every chain version's rows and brought a dropped refutes row back)."""
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    use_id, v1 = _absent_gap_use(pg, w)
    _add_evidence(pg, writer, w, w["ws"], v1, w["text"][0:3], 0, 3, page=7, stance="refutes")
    _, v2 = pg.proposal(writer, "use", use_id, None, v1,
                        {"statement": "restated without the refuting quote", "kind": "method", "status": "proposed"},
                        "dropped the refuting quote", w["ws"])
    assert len(_evidence_rows(pg, v1)) == 1 and _evidence_rows(pg, v2) == []
    chain = _hold_and_rebase(pg, w)
    assert chain["old_head"] == str(v2)
    assert chain["evidence_copied"] == 0, chain
    assert _evidence_rows(pg, chain["new_version"]) == [], "evidence from a non-head chain version was copied"
    assert pg.one("SELECT evidence_copied FROM litkb.rebases WHERE new_version_id = %s",
                  (chain["new_version"],))[0] == 0
    assert len(_evidence_rows(pg, v1)) == 1, "the v1 row must stay where it was"


# ── fixes after the second referee (Reports/LITKB_P1_REFEREE2_2026-09-13.md) ──────────────

@pg_only
def test_commit_waits_for_a_write_in_flight_and_is_refused(pg):
    """E-1 (referee race e2, mutation X9): a writer's write on a NEW entity is held open; then
    promote_commit runs. Its FOR UPDATE on the workstream row waits for the writer's FOR SHARE,
    and after the writer commits it sees a changed version set and refuses (40001), leaving the
    workstream open. Without that lock the commit promotes and marks the workstream merged over
    the writer's new head, stranding it."""
    ws = pg.ws()
    writer_a = pg.session("litkb_writer")
    gap_id, _g1 = pg.proposal(writer_a, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                              {"question": "q", "gap_state": "open"}, None, ws)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (ws,), conn=promoter)[0]
    holder = _holder(pg, "litkb_writer")
    blocked, box = _race(
        pg, holder,
        lambda k: pg.proposal(k, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                              {"question": "written while the commit ran", "gap_state": "open"}, None, ws),
        promoter,
        lambda k: pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=k))
    err = box.get("error")
    assert getattr(err, "sqlstate", None) == "40001", f"commit over a write in flight must be refused 40001, got {box}"
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (ws,))[0] == "open"
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (ws,))[0] == 2, \
        "both chains must still head the open workstream"
    assert pg.pointer("gaps", gap_id) is None
    assert blocked, "the commit was never observed waiting on the writer; the race was not exercised"


def _rebase_count(pg, source_ws):
    return pg.one("SELECT count(*) FROM litkb.rebases WHERE source_workstream_id = %s", (source_ws,))[0]


@pg_only
def test_concurrent_rebases_of_one_workstream_make_one_copy(pg, scratch_repo):
    """E-2 (referee race b1, mutation X2): a rebase of a merged workstream is held open; a second
    rebase of the same workstream into another target waits on the source row's FOR UPDATE, then
    finds nothing held (22023). Without that lock it waits only on the gap identity row and then
    copies every chain a second time."""
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    onto = promote.held_chains(s["promoter"], s["ws1"])
    target_a, target_b = pg.ws(), pg.ws()
    holder = _holder(pg, "litkb_promoter")
    second = pg.session("litkb_promoter")
    blocked, box = _race(
        pg, holder, lambda k: promote.rebase(k, s["ws1"], target_a, onto, "o", "sess-1"),
        second, lambda k: promote.rebase(k, s["ws1"], target_b, onto, "o", "sess-2"))
    assert isinstance(box.get("error"), pg.errors.InvalidParameterValue) and \
        "holds no chain" in str(box["error"]), f"the second rebase must find nothing held, got {box}"
    assert _rebase_count(pg, s["ws1"]) == 2, "each held chain must be copied exactly once"
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (target_b,))[0] == 0
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (target_a,))[0] == 2
    assert blocked, "the second rebase was never observed waiting; the race was not exercised"


@pg_only
def test_rebase_during_a_commit_that_moves_main_is_refused(pg, scratch_repo):
    """E-2 (referee race a1, mutation X3): another workstream's commit that moves main's gap
    pointer is held open; a rebase reviewed against the old pointer waits on the identity row's
    FOR UPDATE, re-reads main after the commit and is refused (40001). Without that lock it reads
    the pre-commit pointer, passes the compare-and-set and copies onto a stale main."""
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    onto = promote.held_chains(s["promoter"], s["ws1"])
    assert onto[f"gap:{s['gap']}"] == str(s["g2b"])
    ws4 = pg.ws()
    _, g3 = pg.proposal(s["writer"], "gap", s["gap"], None, s["g2b"], {"question": "q v3 by ws4", "gap_state": "open"},
                        "ws4 moves main again", ws4, agent="agentD", session="sessD")
    pid4 = promote.prepare(s["promoter"], ws4, s["prepared"], None)
    holder = _holder(pg, "litkb_promoter")
    rebaser = pg.session("litkb_promoter")
    target = pg.ws()
    blocked, box = _race(
        pg, holder, lambda k: pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid4,), conn=k),
        rebaser, lambda k: promote.rebase(k, s["ws1"], target, onto, "o", "sess-rebase"))
    assert getattr(box.get("error"), "sqlstate", None) == "40001", \
        f"a rebase onto the main a concurrent commit just left must be refused 40001, got {box}"
    assert pg.pointer("gaps", s["gap"]) == g3
    assert _rebase_count(pg, s["ws1"]) == 0, "a copy based on the stale main was made"
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (s["ws1"],))[0] == 2
    assert blocked, "the rebase was never observed waiting on the commit; the race was not exercised"


@pg_only
@pytest.mark.parametrize("case", ["missing_key", "extra_key"])
def test_rebase_onto_must_name_exactly_the_held_chains(pg, scratch_repo, case):
    """E-3 (mutation X4), a fresh world per case: an onto that leaves out a held chain would
    rebase that chain unreviewed (here the use chain, whose main pointer is NULL, so the
    per-chain compare-and-set cannot catch the omission); an onto naming a chain the workstream
    does not hold is also refused."""
    from litkb import promote
    s = _held_world(pg, scratch_repo)
    onto = promote.held_chains(s["promoter"], s["ws1"])
    use_key = f"use:{s['use']}"
    assert onto[use_key] is None
    if case == "missing_key":
        del onto[use_key]
    else:
        onto[f"gap:{uuid.uuid4()}"] = None
    target = pg.ws()
    with pytest.raises(pg.errors.InvalidParameterValue, match="exactly the held chains"):
        promote.rebase(s["promoter"], s["ws1"], target, onto, "o", "s")
    assert _rebase_count(pg, s["ws1"]) == 0
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (target,))[0] == 0


@pg_only
def test_add_evidence_waits_for_a_prepare_in_flight_and_is_refused(pg):
    """E-6 (referee race d, mutation X1): promote_prepare is held open; add_evidence on the
    version being prepared waits on the workstream row (FOR SHARE vs prepare's FOR UPDATE), then
    sees the prepared state and is refused (55000) with no row written, and the prepared
    promotion still commits. Without the lock the evidence lands and the commit fails 40001."""
    w = _evidence_world(pg)
    # 0019 holds a use with no verified quote; this test's subject is elsewhere, so the
    # world's use is given one and reaches `prepared` as it did before.
    _make_promotable(pg, w)
    holder = _holder(pg, "litkb_promoter")
    writer = pg.session("litkb_writer")
    prepared = {}

    def hold(k):
        prepared["pid"] = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=k)[0]
    blocked, box = _race(
        pg, holder, hold,
        writer, lambda k: _add_evidence(pg, k, w, w["ws"], w["uv"], w["text"][4:20], 4, 20))
    assert getattr(box.get("error"), "sqlstate", None) == "55000", \
        f"evidence added during a prepare must be refused 55000, got {box}"
    # 1, not 0: the setup's own verified quote (0019). The refused write must add nothing to it.
    assert pg.one("SELECT count(*) FROM litkb.use_evidence WHERE use_version_id = %s", (w["uv"],))[0] == 1
    promoter = pg.session("litkb_promoter")
    out = pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (prepared["pid"],), conn=promoter)[0]
    assert out["committed"] == 1, out
    assert blocked, "add_evidence was never observed waiting on the prepare; the race was not exercised"


@pg_only
def test_set_current_run_refuses_a_stale_expected_run(pg):
    """E-7 (mutation X8): set_current_run is a compare-and-set. A caller that still believes the
    file is at its first run, after another caller moved it, is refused (40001)."""
    w = _evidence_world(pg)
    ingest = pg.session("litkb_ingest")
    moved = _run(pg, ingest, w["file"], "ok")
    ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], moved))
    late = _run(pg, ingest, w["file"], "ok")
    with pytest.raises(pg.errors.SerializationFailure, match="CAS refused"):
        ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], late))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == moved


# ── Kam's decisions after the second referee (migration 0010) ─────────────────────────────

def _tables_containing(pg, needle):
    """(schema, table, rows) for every litkb table whose row text contains needle."""
    hits = []
    for schema, table in pg.conn.execute(
            "SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('litkb', 'litkb_meta') "
            "ORDER BY 1, 2").fetchall():
        n = pg.one(f'SELECT count(*) FROM "{schema}"."{table}" t WHERE strpos(t::text, %s) > 0', (needle,))[0]
        if n:
            hits.append((schema, table, n))
    return hits


@pg_only
def test_open_workstream_returns_a_token_stored_only_as_its_hash(pg):
    """The token comes back once, from open_workstream. The database keeps its sha256 in
    workstream_tokens, which no agent role can read, and the token text is in no table."""
    import hashlib
    import re
    writer = pg.session("litkb_writer")
    ws = pg.ws(conn=writer)
    token = pg.tokens[ws]
    assert re.fullmatch(r"[0-9a-f]{64}", token), "the token must be 64 hex characters"
    other = pg.ws(conn=writer)
    assert pg.tokens[other] != token
    stored = pg.one("SELECT token_hash FROM litkb.workstream_tokens WHERE workstream_id = %s", (ws,))[0]
    assert stored == hashlib.sha256(token.encode("utf-8")).hexdigest(), "the stored value is not the token's sha256"
    assert _tables_containing(pg, token) == [], "the token text was written to a table"
    for role in ("litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest"):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            pg.session(role).execute("SELECT token_hash FROM litkb.workstream_tokens LIMIT 1")


def _refused_by_token(pg, call, token):
    with pytest.raises(pg.errors.InsufficientPrivilege, match="workstream token refused") as ei:
        call(token)
    # "" is a substring of every message, so only a non-empty token can be looked for
    assert not token or token not in str(ei.value), "the refusal message echoes the token"


@pg_only
def test_referee_cross_session_evidence_insert_is_refused(pg):
    """Referee 2, residual gap 1: a second writer connection named another workstream's id and
    add_evidence was accepted. Session B holds only its own workstream's token; naming A's
    workstream with B's token, with no token or with a made-up one is refused, and A's own token
    is accepted."""
    w = _evidence_world(pg)
    session_a, session_b = pg.session("litkb_writer"), pg.session("litkb_writer")
    ws_b = pg.ws(conn=session_b)
    for token in (pg.tokens[ws_b], None, uuid.uuid4().hex + uuid.uuid4().hex):
        _refused_by_token(pg, lambda tok: _add_evidence(pg, session_b, w, w["ws"], w["uv"], w["text"][4:20], 4, 20,
                                                       token=tok), token)
    assert pg.one("SELECT count(*) FROM litkb.use_evidence WHERE use_version_id = %s", (w["uv"],))[0] == 0
    assert _add_evidence(pg, session_a, w, w["ws"], w["uv"], w["text"][4:20], 4, 20)[1] is True


def _token_op(pg, op):
    """(call(token), unchanged()) for one writer function that names a workstream."""
    writer = pg.session("litkb_writer")
    if op == "add_evidence":
        w = _evidence_world(pg)
        ws = w["ws"]

        def call(tok):
            return _add_evidence(pg, writer, w, ws, w["uv"], w["text"][4:20], 4, 20, token=tok)

        def unchanged():
            return pg.one("SELECT count(*) FROM litkb.use_evidence WHERE use_version_id = %s", (w["uv"],))[0] == 0
        return ws, call, unchanged
    ws = pg.ws()
    if op == "write_proposal":
        def call(tok):
            return pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                               {"question": "q", "gap_state": "open"}, None, ws, token=tok)

        def unchanged():
            return pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (ws,))[0] == 0
    elif op == "add_candidate":
        def call(tok):
            return writer.execute("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, "
                                  "'A lead', NULL, NULL, NULL)", (ws, tok))

        def unchanged():
            return pg.one("SELECT count(*) FROM litkb.candidates WHERE workstream_id = %s", (ws,))[0] == 0
    elif op == "record_acquisition_attempt":
        work_id, _ = pg.work(ws)

        def call(tok):
            return writer.execute("SELECT litkb.record_acquisition_attempt(%s, %s, %s, NULL, 'open_access', "
                                  "NULL, 'ok', NULL, NULL)", (ws, tok, work_id))

        def unchanged():
            return pg.one("SELECT count(*) FROM litkb.acquisition_attempts WHERE workstream_id = %s", (ws,))[0] == 0
    elif op == "add_use_embedding":
        work_id, _ = pg.work(ws)
        _, uv = pg.proposal(pg.conn, "use", None, {"work_id": str(work_id)}, None,
                            {"statement": "s", "kind": "method", "status": "proposed"}, None, ws)

        def call(tok):
            return writer.execute("SELECT litkb.add_use_embedding(%s, %s, %s, 'm', 3, '[1,2,3]'::halfvec)",
                                  (ws, tok, uv))

        def unchanged():
            return pg.one("SELECT count(*) FROM litkb.use_embeddings WHERE use_version_id = %s", (uv,))[0] == 0
    elif op == "write_fact":
        work_id, v1 = pg.work(ws)

        def call(tok):
            return pg.one("SELECT entity_id, version_id FROM litkb.write_fact('work', %s, %s, %s, 'fix', %s, %s, 'a', 's')",
                          (work_id, v1, pg.Jsonb({"type": "article", "title": "fixed", "authors": []}), ws, tok),
                          conn=writer)

        def unchanged():
            return pg.pointer("works", work_id) == v1
    else:
        def call(tok):
            return writer.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws, tok))

        def unchanged():
            return pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (ws,))[0] == "open"
    return ws, call, unchanged


@pg_only
@pytest.mark.parametrize("case", ["missing", "empty", "upper_cased_own", "another_workstreams_token"])
@pytest.mark.parametrize("op", ["write_proposal", "write_fact", "add_evidence", "abandon_workstream",
                                "add_candidate", "record_acquisition_attempt", "add_use_embedding"])
def test_every_workstream_write_requires_its_token(pg, op, case):
    """Every writer function that names a workstream refuses (42501, inside the SECURITY DEFINER
    function) a missing token, an empty one (third referee F-4 / Z2), its own token upper-cased, or
    another workstream's token, writes nothing, and accepts the workstream's own token."""
    ws, call, unchanged = _token_op(pg, op)
    token = {"missing": None, "empty": "", "upper_cased_own": pg.tokens[ws].upper(),
             "another_workstreams_token": None}[case]
    if case == "another_workstreams_token":
        token = pg.tokens[pg.ws()]
    _refused_by_token(pg, call, token)
    assert unchanged(), f"{op} wrote something with a refused token"
    call(pg.tokens[ws])
    assert not unchanged(), f"{op} did nothing with the workstream's own token"


@pg_only
def test_token_functions_have_exactly_one_signature(pg):
    """0010 drops the token-less signatures: CREATE with an added parameter makes an OVERLOAD, and
    the old function (with its old grant) would still take writes without a token."""
    rows = dict(pg.conn.execute(
        "SELECT p.proname, array_agg(pg_get_function_identity_arguments(p.oid)) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'litkb' AND p.proname = ANY (%s) "
        "GROUP BY p.proname", (["write_fact", "write_proposal", "add_evidence", "abandon_workstream",
                                "open_workstream", "add_candidate", "record_acquisition_attempt",
                                "add_use_embedding"],)).fetchall())
    assert sorted(rows) == ["abandon_workstream", "add_candidate", "add_evidence", "add_use_embedding",
                            "open_workstream", "record_acquisition_attempt", "write_fact", "write_proposal"]
    for name, sigs in rows.items():
        assert len(sigs) == 1, f"{name} has {len(sigs)} signatures: {sigs}"
        if name != "open_workstream":
            assert "p_ws_token text" in sigs[0], (name, sigs)


def test_workstream_token_file_is_git_ignored():
    """The session's token file never enters a commit, at the worktree root or under Scripts/
    (whose whitelist would otherwise un-ignore it)."""
    repo = SCRIPTS.parent
    if subprocess.run(["git", "-C", str(repo), "rev-parse"], capture_output=True).returncode != 0:
        pytest.skip("not a git checkout")
    for rel in (".litkb-workstream", "Scripts/.litkb-workstream", "Scripts/pipeline/litkb/.litkb-workstream"):
        r = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--no-index", rel], capture_output=True)
        assert r.returncode == 0, f"{rel} is not git-ignored"


@pg_only
def test_workstream_module_writes_the_token_file_once(pg, tmp_path, capsys):
    """litkb.workstream opens a workstream, writes {id, token} to .litkb-workstream, never prints
    the token, refuses to overwrite the file, and the token it wrote is the one the database takes."""
    from litkb import workstream
    writer = pg.session("litkb_writer")
    slug = f"t-{uuid.uuid4().hex[:12]}"
    ws_id = workstream.open_workstream(writer, slug, "work/test", "p1 test", directory=tmp_path)
    got_id, token = workstream.load(tmp_path)
    assert got_id == str(ws_id)
    out = capsys.readouterr()
    assert token not in out.out and token not in out.err
    with pytest.raises(workstream.WorkstreamFileExists):
        workstream.open_workstream(writer, slug + "-2", "work/test", "p1 test", directory=tmp_path)
    assert pg.one("SELECT count(*) FROM litkb.workstreams WHERE slug = %s", (slug + "-2",))[0] == 0
    assert workstream.load(tmp_path) == (got_id, token), "the token file was overwritten"
    pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                {"question": "q", "gap_state": "open"}, None, ws_id, token=token)


@pg_only
def test_writer_cannot_install_a_run_or_make_it_current(pg):
    """Referee 2, residual gap 2: the writer inserted an ok run and made it current, which
    un-promotes that file's evidence. Both steps are now refused to the writer, and so is a block
    insert (a writer-made block whose text matched a quote would verify it)."""
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        _run(pg, writer, w["file"], "ok")
    ingested = _run(pg, pg.session("litkb_ingest"), w["file"], "ok")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], ingested))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == w["run"]
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES (%s, %s, 1, "
                       "'paragraph', 'any quote at all')", (w["file"], w["run"]))


@pg_only
def test_ingest_installs_a_run_and_makes_it_current(pg):
    w = _evidence_world(pg)
    ingest = pg.session("litkb_ingest")
    run2 = _run(pg, ingest, w["file"], "ok")
    ingest.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES (%s, %s, 1, "
                   "'paragraph', 'extracted again')", (w["file"], run2))
    ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], run2))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == run2


@pg_only
def test_ingest_cannot_write_knowledge(pg):
    """The ingest login writes extraction data only: no gaps, uses, evidence or workstreams."""
    w = _evidence_world(pg)
    ingest = pg.session("litkb_ingest")
    attempts = [
        lambda: pg.proposal(ingest, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                            {"question": "q", "gap_state": "open"}, None, w["ws"]),
        lambda: pg.proposal(ingest, "use", w["use"], None, w["uv"],
                            {"statement": "s", "kind": "method", "status": "proposed"}, "r", w["ws"]),
        lambda: _add_evidence(pg, ingest, w, w["ws"], w["uv"], w["text"][4:20], 4, 20),
        lambda: pg.ws(conn=ingest),
        lambda: ingest.execute("SELECT litkb.abandon_workstream(%s, %s)", (w["ws"], pg.tokens[w["ws"]])),
        lambda: ingest.execute("INSERT INTO litkb.gap_versions (agent) VALUES ('x')"),
        lambda: ingest.execute("INSERT INTO litkb.use_versions (agent) VALUES ('x')"),
        lambda: ingest.execute("INSERT INTO litkb.use_evidence (quote) VALUES ('x')"),
    ]
    for i, attempt in enumerate(attempts):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            attempt()
    assert pg.one("SELECT count(*) FROM litkb.use_evidence WHERE use_version_id = %s", (w["uv"],))[0] == 0


def test_connect_refuses_the_ingest_login(monkeypatch):
    """The ingest login has one connection path, litkb.ingest.connect(), with its own passfile;
    the shared connect() refuses it before any driver is loaded."""
    from litkb import ingest
    from litkb.db import connect as c
    with monkeypatch.context() as m:
        m.setitem(sys.modules, "psycopg", None)
        m.setitem(sys.modules, "psycopg.conninfo", None)
        with pytest.raises(c.IngestLoginRefused):
            c.connect(c.DB_MAIN, c.INGEST)
    assert c.ingest_passfile() != c.promoter_passfile()
    assert callable(ingest.connect)
    pytest.importorskip("psycopg")
    from psycopg.conninfo import conninfo_to_dict
    params = conninfo_to_dict(c.conninfo(c.DB_MAIN, c.INGEST, passfile=c.ingest_passfile()))
    assert params["user"] == c.INGEST and params["passfile"] == c.ingest_passfile()


# ── the token bypass closed (migration 0011) ──────────────────────────────────────────────

def _direct_row(pg, table):
    """(sql, params) for one otherwise-valid row of `table` belonging to a fresh workstream."""
    ws = pg.ws()
    work_id, _ = pg.work(ws)
    if table == "gap_versions":
        gap_id, g1 = pg.main_gap(ws)
        return ("INSERT INTO litkb.gap_versions (gap_id, version_no, question, gap_state, based_on_version_id, "
                "change_reason, workstream_id, agent, session_id) VALUES (%s, 99, 'q', 'open', %s, 'direct', %s, "
                "'a', 's')", (gap_id, g1, ws))
    if table in ("use_versions", "use_embeddings"):
        use_id, uv = pg.proposal(pg.conn, "use", None, {"work_id": str(work_id)}, None,
                                 {"statement": "s", "kind": "method", "status": "proposed"}, None, ws)
        if table == "use_embeddings":
            return ("INSERT INTO litkb.use_embeddings (use_version_id, model, dim, vector) "
                    "VALUES (%s, 'm', 3, '[1,2,3]'::halfvec)", (uv,))
        return ("INSERT INTO litkb.use_versions (use_id, version_no, statement, kind, status, based_on_version_id, "
                "change_reason, workstream_id, agent, session_id) VALUES (%s, 99, 's', 'method', 'proposed', %s, "
                "'direct', %s, 'a', 's')", (use_id, uv, ws))
    if table == "candidates":
        return ("INSERT INTO litkb.candidates (source, title, workstream_id) VALUES ('manual', 'lead', %s)", (ws,))
    if table == "admissions":
        # no state column: 0006 never granted it, so naming it would be refused whatever 0011 does
        return ("INSERT INTO litkb.admissions (route, admitter_agent, admitter_session, work_id, workstream_id) "
                "VALUES ('registry', 'a', 's', %s, %s)", (work_id, ws))
    assert table == "acquisition_attempts", table
    return ("INSERT INTO litkb.acquisition_attempts (work_id, route, status, workstream_id) "
            "VALUES (%s, 'open_access', 'ok', %s)", (work_id, ws))


@pg_only
@pytest.mark.parametrize("table", ["gap_versions", "use_versions", "candidates", "admissions",
                                   "acquisition_attempts", "use_embeddings"])
def test_writer_has_no_direct_write_on_workstream_tables(pg, table):
    """0011: every table the writer could INSERT into directly before 0011 and whose rows belong to a
    workstream (the catalog enumeration in the migration's header). The writer's direct INSERT of an
    otherwise-valid row is refused (42501); the owner's identical statement lands, which shows the
    refusal is the privilege and not the row."""
    q, params = _direct_row(pg, table)
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InsufficientPrivilege):
        writer.execute(q, params)
    pg.conn.execute(q, params)


@pg_only
def test_add_use_embedding_version_must_belong_to_named_workstream(pg):
    """A session holding its own workstream's token cannot attach an embedding to a use version
    written in another workstream (the add_evidence ownership rule)."""
    ws_a = pg.ws()
    work_id, _ = pg.work(ws_a)
    _, uv = pg.proposal(pg.conn, "use", None, {"work_id": str(work_id)}, None,
                        {"statement": "s", "kind": "method", "status": "proposed"}, None, ws_a)
    ws_b = pg.ws()
    writer = pg.session("litkb_writer")
    q = "SELECT litkb.add_use_embedding(%s, %s, %s, 'm', 3, '[1,2,3]'::halfvec)"
    with pytest.raises(pg.errors.InsufficientPrivilege, match="another workstream"):
        writer.execute(q, (ws_b, pg.tokens[ws_b], uv))
    assert pg.one("SELECT count(*) FROM litkb.use_embeddings WHERE use_version_id = %s", (uv,))[0] == 0
    writer.execute(q, (ws_a, pg.tokens[ws_a], uv))
    assert pg.one("SELECT count(*) FROM litkb.use_embeddings WHERE use_version_id = %s", (uv,))[0] == 1


# ── the catalog guard, rewritten after the third referee (F-1) ─────────────────────────────
# The agent LOGINS whose reach the guard follows. Every role any of them can use (INHERIT) or SET ROLE
# to is checked, whatever its name, together with PUBLIC and every role named in an ACL of a guarded
# relation.
AGENT_LOGINS = ("litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest", "litkb_test")

# The guarded relations, every relkind (table, partitioned table, view, materialized view, foreign table):
#   seed     litkb.workstreams; every relation with a workstream_id column (with or without a foreign
#            key); every relation with a foreign key to workstreams; every view and materialized view
#            in litkb (a writable view runs with its owner's rights, so any agent write on one is a
#            bypass whatever its columns).
#   closure  every relation with a foreign key to a guarded relation, through any number of hops.
#   stop     the closure does not continue THROUGH a main-owned identity table (one with a created_in_ws
#            column: works, identifiers, files, gaps, uses). Its link to a workstream is creation
#            provenance, and its current_version_id points at a promoted version; following it would
#            pull in every extraction table (blocks -> files), whose INSERT belongs to the ingest login.
#            Identity tables are themselves guarded.
_GUARDED_RELATIONS = """
WITH RECURSIVE provenance AS (
  SELECT a.attrelid AS rel FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
   WHERE c.relnamespace = 'litkb'::regnamespace AND a.attname = 'created_in_ws' AND a.attnum > 0
     AND NOT a.attisdropped),
seed AS (
  SELECT 'litkb.workstreams'::regclass::oid AS rel
  UNION SELECT c.oid FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
         WHERE c.relnamespace = 'litkb'::regnamespace AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
           AND a.attname = 'workstream_id' AND a.attnum > 0 AND NOT a.attisdropped
  UNION SELECT k.conrelid FROM pg_constraint k
         WHERE k.contype = 'f' AND k.confrelid = 'litkb.workstreams'::regclass
  UNION SELECT c.oid FROM pg_class c
         WHERE c.relnamespace = 'litkb'::regnamespace AND c.relkind IN ('v', 'm')),
closure (rel) AS (
  SELECT rel FROM seed
  UNION
  SELECT k.conrelid FROM pg_constraint k JOIN closure cl ON k.confrelid = cl.rel
   WHERE k.contype = 'f' AND cl.rel NOT IN (SELECT rel FROM provenance))
SELECT DISTINCT rel FROM closure
"""

_TABLE_WRITE_PRIVS = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER", "MAINTAIN")
_COLUMN_WRITE_PRIVS = ("INSERT", "UPDATE")


def _guarded_relations(conn):
    return dict(conn.execute(
        f"SELECT c.oid, c.relname FROM pg_class c WHERE c.oid IN ({_GUARDED_RELATIONS})").fetchall())


def _direct_write_offenders(conn, agents=AGENT_LOGINS, *, acl_grantees=True):
    """[(role, relation, privilege, column or None, how the role was found)] for every direct write
    on a guarded relation. Owners and superusers are exempt as grantees; an agent login that can
    reach (INHERIT or SET) a relation's owner or a superuser is itself an offender."""
    rels = _guarded_relations(conn)
    found = conn.execute(
        """
        WITH agent AS (SELECT r.oid, r.rolname FROM pg_roles r WHERE r.rolname = ANY (%(agents)s)),
        reach AS (
          SELECT a.oid, a.rolname, 'agent login ' || a.rolname AS via FROM agent a
          UNION
          SELECT g.oid, g.rolname, 'reachable from ' || a.rolname FROM agent a JOIN pg_roles g ON g.oid <> a.oid
           WHERE pg_has_role(a.oid, g.oid, 'MEMBER') OR pg_has_role(a.oid, g.oid, 'SET')
              OR pg_has_role(a.oid, g.oid, 'USAGE')
          UNION
          SELECT 0::oid, 'public', 'PUBLIC'
          UNION
          SELECT e.grantee, coalesce(g.rolname, 'public'), 'ACL grantee'
            FROM pg_class c
            CROSS JOIN LATERAL aclexplode(c.relacl) e
            LEFT JOIN pg_roles g ON g.oid = e.grantee
           WHERE %(acl)s AND c.oid = ANY (%(rels)s::oid[])
          UNION
          SELECT e.grantee, coalesce(g.rolname, 'public'), 'ACL grantee'
            FROM pg_attribute a
            CROSS JOIN LATERAL aclexplode(a.attacl) e
            LEFT JOIN pg_roles g ON g.oid = e.grantee
           WHERE %(acl)s AND a.attrelid = ANY (%(rels)s::oid[])),
        grantee AS (
          SELECT r.oid, r.rolname, string_agg(DISTINCT r.via, '; ') AS via FROM reach r
            LEFT JOIN pg_roles s ON s.oid = r.oid
           WHERE NOT coalesce(s.rolsuper, false)
           GROUP BY r.oid, r.rolname)
        SELECT g.rolname, c.relname, p.priv, NULL::name, g.via
          FROM grantee g CROSS JOIN pg_class c CROSS JOIN unnest(%(tprivs)s::text[]) AS p(priv)
         WHERE c.oid = ANY (%(rels)s::oid[]) AND g.oid <> c.relowner
           AND has_table_privilege(g.rolname, c.oid, p.priv)
        UNION ALL
        SELECT g.rolname, c.relname, p.priv, a.attname, g.via
          FROM grantee g CROSS JOIN pg_class c CROSS JOIN unnest(%(cprivs)s::text[]) AS p(priv)
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
         WHERE c.oid = ANY (%(rels)s::oid[]) AND g.oid <> c.relowner
           AND NOT has_table_privilege(g.rolname, c.oid, p.priv)
           AND has_column_privilege(g.rolname, c.oid, a.attnum, p.priv)
        UNION ALL
        SELECT a.rolname, c.relname, 'reaches the owner or a superuser', NULL::name, 'agent login ' || a.rolname
          FROM agent a CROSS JOIN pg_class c
         WHERE c.oid = ANY (%(rels)s::oid[]) AND a.oid <> c.relowner
           AND (pg_has_role(a.oid, c.relowner, 'MEMBER') OR pg_has_role(a.oid, c.relowner, 'SET')
                OR EXISTS (SELECT 1 FROM pg_roles s WHERE s.rolsuper AND pg_has_role(a.oid, s.oid, 'MEMBER')))
         ORDER BY 1, 2, 3, 4
        """, dict(agents=list(agents), rels=list(rels), acl=acl_grantees,
                  tprivs=list(_TABLE_WRITE_PRIVS), cprivs=list(_COLUMN_WRITE_PRIVS))).fetchall()
    return found


@pg_only
def test_no_agent_role_holds_a_direct_write_on_a_workstream_table(pg):
    """0011, rewritten after the third referee (F-1): no agent role, no role an agent login can use or
    SET ROLE to, no ACL grantee and not PUBLIC holds INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER or
    MAINTAIN (table level) or INSERT/UPDATE (column level) on a guarded relation, so every write into a
    workstream stays a token-checked function. The relations and roles both come from the catalog
    (_GUARDED_RELATIONS, _direct_write_offenders); the referee's Z6 (workstream_id without a foreign
    key), Z7 (two hops) and Z8 (updatable view) each make this fail."""
    names = set(_guarded_relations(pg.conn).values())
    # the rule is not vacuous, and it does not swallow the extraction tables
    assert {"gap_versions", "use_versions", "candidates", "admissions", "acquisition_attempts", "use_evidence",
            "use_embeddings", "ws_heads", "workstream_tokens", "rebases", "promotions", "works", "files",
            "ws_uses", "main_uses", "use_evidence_status"} <= names, sorted(names)
    assert not names & set(_EXTRACTION_TABLES), sorted(names & set(_EXTRACTION_TABLES))
    offending = _direct_write_offenders(pg.conn)
    assert offending == [], f"direct writes on guarded relations (role, relation, privilege, column, via): {offending}"


_EXTRACTION_TABLES = ("extraction_runs", "file_checks", "pages", "blocks", "tables", "figures", "equations",
                      "references", "citation_mentions", "chunks", "embeddings")


@pg_only
def test_catalog_guard_fires_on_new_workstream_bearing_relations(pg):
    """F-1: the guard is shown to fail on shapes the old one missed, created in litkb_test inside one
    transaction that is rolled back (nothing survives the test): a workstream_id column with no foreign
    key, a table two and three foreign-key hops from workstreams (below use_evidence), a view over
    use_versions without a workstream_id column, a materialized view, a partitioned table granted to
    PUBLIC, and a TRUNCATE held by the ingest login that the guard finds ONLY through litkb_test's
    WITH INHERIT FALSE, SET TRUE membership (the referee's F-1(d) shape). Negative control: a table
    below blocks granted INSERT to ingest is not guarded."""
    k = pg.session()
    k.autocommit = False
    try:
        for ddl in (
            "CREATE TABLE litkb.zz_ws_notes (id uuid PRIMARY KEY DEFAULT uuidv7(), workstream_id uuid, note text)",
            "CREATE TABLE litkb.zz_hop2 (id uuid PRIMARY KEY, evidence_id uuid REFERENCES litkb.use_evidence (id), note text)",
            "CREATE TABLE litkb.zz_hop3 (id uuid PRIMARY KEY, hop2_id uuid REFERENCES litkb.zz_hop2 (id), note text)",
            "CREATE VIEW litkb.zz_inbox AS SELECT version_id, use_id, statement FROM litkb.use_versions",
            "CREATE MATERIALIZED VIEW litkb.zz_mat AS SELECT 1 AS x",
            "CREATE TABLE litkb.zz_part (workstream_id uuid, k integer) PARTITION BY LIST (k)",
            "CREATE TABLE litkb.zz_block_notes (id uuid PRIMARY KEY, block_id uuid REFERENCES litkb.blocks (id))",
            "GRANT INSERT ON litkb.zz_ws_notes TO litkb_writer",
            "GRANT UPDATE (note) ON litkb.zz_hop3 TO litkb_reader",
            "GRANT INSERT ON litkb.zz_inbox TO litkb_writer",
            "GRANT DELETE ON litkb.zz_mat TO litkb_promoter",
            "GRANT INSERT ON litkb.zz_part TO PUBLIC",
            "GRANT TRUNCATE ON litkb.zz_hop2 TO litkb_ingest",
            "GRANT INSERT ON litkb.zz_block_notes TO litkb_ingest"):
            k.execute(ddl)
        names = set(_guarded_relations(k).values())
        assert {"zz_ws_notes", "zz_hop2", "zz_hop3", "zz_inbox", "zz_mat", "zz_part"} <= names, sorted(names)
        assert "zz_block_notes" not in names
        got = {(r[0], r[1], r[2], r[3]) for r in _direct_write_offenders(k)}
        expected = {("litkb_writer", "zz_ws_notes", "INSERT", None), ("litkb_reader", "zz_hop3", "UPDATE", "note"),
                    ("litkb_writer", "zz_inbox", "INSERT", None), ("litkb_promoter", "zz_mat", "DELETE", None),
                    ("public", "zz_part", "INSERT", None), ("litkb_ingest", "zz_hop2", "TRUNCATE", None)}
        assert expected <= got, f"missed: {sorted(expected - got, key=repr)}"
        assert not any(r[1] == "zz_block_notes" for r in got)
        # membership only: name no agent but litkb_test and read no ACL; ingest is reached through SET
        via_set = [r for r in _direct_write_offenders(k, ("litkb_test",), acl_grantees=False)
                   if (r[0], r[1], r[2]) == ("litkb_ingest", "zz_hop2", "TRUNCATE")]
        assert via_set and "reachable from litkb_test" in via_set[0][4], via_set
        assert pg.one("SELECT pg_has_role('litkb_test', 'litkb_ingest', 'USAGE')", conn=k)[0] is False, \
            "the membership must be SET-only for this case to test the SET branch"
    finally:
        k.rollback()
    assert pg.one("SELECT to_regclass('litkb.zz_ws_notes')")[0] is None


_EXPECTED_EXECUTE = {
    # check_ws_token, norm_search_text, any_term_query: P8's access layer (migration 0018,
    # qc/test_litkb_p8.py). check_ws_token is SECURITY DEFINER and returns a BOOLEAN and nothing
    # else — it is how a READ tool presents the workstream token without any role reading
    # litkb.workstream_tokens (referee F-1). The other two are the search normaliser and the
    # any-term query builder: pure functions of their argument, no table in either.
    "litkb_reader": {"norm_identifier", "check_ws_token", "norm_search_text", "any_term_query"},
    # admit, approve_admission, attach_file: P2 admission (migration 0013, qc/test_litkb_p2.py)
    "litkb_writer": {"norm_identifier", "open_workstream", "abandon_workstream", "write_fact", "write_proposal",
                     "admit", "approve_admission", "attach_file",
                     # record_discrepancy: P3 migration (migration 0015, qc/test_litkb_p3.py) — the ONE writer
                     # of litkb.discrepancies, which carries workstream_id and is therefore guarded
                     "record_discrepancy",
                     # hold_candidate: WHY a candidate is held (migration 0016, referee P3 F6). candidates
                     # carries workstream_id and is guarded, and admission never reaches a held row, so the
                     # reason needs its own token-checked writer
                     "hold_candidate",
                     "add_evidence", "add_candidate", "record_acquisition_attempt", "add_use_embedding",
                     # _feeds_token_ok: `litkb use add` checks a feeds token against the DATABASE's
                     # regex before it writes (migration 0020, definition settled in 0021), so the
                     # shape rule has one home and a mistyped token is a refusal at the command
                     # instead of a chain held at prepare. It reads nothing: text in, boolean out,
                     # IMMUTABLE.
                     "_feeds_token_ok",
                     # the writer reaches the same three 0018 functions as the reader: the MCP
                     # server's write tools run on the writer connection and litkb_search's
                     # normaliser must behave identically whichever login asks
                     "check_ws_token", "norm_search_text", "any_term_query"},
    # promotion_chains: the promoter's SECURITY DEFINER read of _ws_chains, so `promote prepare` can
    # write the promotion report (migration 0018, referee F-5). No agent role holds it.
    "litkb_promoter": {"norm_identifier", "promote_prepare", "promote_commit", "promote_abandon",
                       "promote_rebase", "promotion_chains"},
    # open/finish_extraction_run, clear_extraction_rows, add_table_cell, add_disagreement: the P5
    # ingest schema (migration 0017, qc/test_litkb_reconcile.py). 0017's three new tables
    # (table_cells, extraction_disagreements, file_current_run) grant INSERT to NOBODY, so these
    # functions are their only writers and the checks in them cannot be walked around;
    # clear_extraction_rows is the resume path and refuses a run whose status is ok.
    # add_reference, add_citation_mention, add_citation_edge, add_citation_candidate: stage 6's
    # references, their mentions and the citation graph (migration 0020,
    # qc/test_litkb_references_ingest.py). Same shape as 0017: "references", citation_mentions and
    # citation_edges grant INSERT to nobody, so these functions are their only writers.
    "litkb_ingest": {"norm_identifier", "set_current_run",
                     "open_extraction_run", "finish_extraction_run", "clear_extraction_rows",
                     "add_table_cell", "add_disagreement",
                     "add_reference", "add_citation_mention", "add_citation_edge", "add_citation_candidate",
                     # norm_search_text: 0018's expression index on blocks calls it, and an index
                     # expression is evaluated as the role doing the INSERT. Ingest writes blocks.
                     "norm_search_text"},
    "public": set(),
}
_EXPECTED_WRITES = {role: set() for role in _EXPECTED_EXECUTE}
_EXPECTED_WRITES["litkb_ingest"] = {(t, "INSERT") for t in _EXTRACTION_TABLES}


@pg_only
def test_role_privilege_matrix(pg):
    """Third referee F-5: design §4.7 as a matrix, read from the catalog per role (effective privileges,
    so INHERIT memberships count). For every relation of every kind in litkb, litkb_meta and public:
    table-level INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER/REFERENCES/MAINTAIN, and column-level
    INSERT/UPDATE/REFERENCES where the table-level right is not held; EXECUTE on every function in litkb
    and litkb_meta; CREATE on the schemas; CREATE and TEMP on the database. Each agent role holds
    exactly its §4.7 row: ingest INSERT on the 11 extraction tables and EXECUTE on set_current_run and
    norm_identifier; the writer the 9 token functions, open_workstream and norm_identifier, and no write
    on any table; the promoter the four promote functions; the reader norm_identifier; PUBLIC nothing.
    The referee's Z9 (writer UPDATE (text) on blocks) and Z10 (ingest EXECUTE on add_candidate) each
    make this fail. The test login owns every object in litkb_test, inherits no agent role and cannot
    connect to litkb (the server-side refusal is test_kill_test_role_is_refused_by_the_server_on_litkb)."""
    for role in _EXPECTED_EXECUTE:
        writes = {(r[0], r[1]) for r in pg.conn.execute(
            """
            SELECT c.relname, p.priv FROM pg_class c
              CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER', 'REFERENCES', 'MAINTAIN']) p(priv)
             WHERE c.relnamespace IN ('litkb'::regnamespace, 'litkb_meta'::regnamespace, 'public'::regnamespace)
               AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S') AND has_table_privilege(%(r)s, c.oid, p.priv)
            UNION
            SELECT c.relname || '.' || a.attname, p.priv FROM pg_class c
              JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
              CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE', 'REFERENCES']) p(priv)
             WHERE c.relnamespace IN ('litkb'::regnamespace, 'litkb_meta'::regnamespace, 'public'::regnamespace)
               AND c.relkind IN ('r', 'p', 'v', 'm', 'f') AND NOT has_table_privilege(%(r)s, c.oid, p.priv)
               AND has_column_privilege(%(r)s, c.oid, a.attnum, p.priv)
            """, dict(r=role)).fetchall()}
        assert writes == _EXPECTED_WRITES[role], (
            f"{role}: unexpected {sorted(writes - _EXPECTED_WRITES[role])}, missing {sorted(_EXPECTED_WRITES[role] - writes)}")
        execute = {r[0] for r in pg.conn.execute(
            "SELECT p.proname FROM pg_proc p WHERE p.pronamespace IN ('litkb'::regnamespace, 'litkb_meta'::regnamespace) "
            "AND has_function_privilege(%s, p.oid, 'EXECUTE')", (role,)).fetchall()}
        assert execute == _EXPECTED_EXECUTE[role], (
            f"{role}: unexpected EXECUTE {sorted(execute - _EXPECTED_EXECUTE[role])}, "
            f"missing {sorted(_EXPECTED_EXECUTE[role] - execute)}")
        other = pg.one(
            "SELECT has_schema_privilege(%(r)s, 'litkb', 'CREATE') OR has_schema_privilege(%(r)s, 'litkb_meta', 'CREATE') "
            "OR has_schema_privilege(%(r)s, 'public', 'CREATE') OR has_database_privilege(%(r)s, current_database(), 'CREATE') "
            "OR has_database_privilege(%(r)s, current_database(), 'TEMP')", dict(r=role))[0]
        assert other is False, f"{role} holds CREATE on a schema or CREATE/TEMP on the database"
    assert pg.one("SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace AND p.prosecdef")[0] == 0
    # the test login: owner of every object here, inheriting no agent role
    assert pg.one(
        "SELECT count(*) FROM pg_class c WHERE c.relnamespace IN ('litkb'::regnamespace, 'litkb_meta'::regnamespace) "
        "AND c.relowner <> 'litkb_test'::regrole")[0] == 0
    assert pg.one("SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'litkb'::regnamespace "
                  "AND p.proowner <> 'litkb_test'::regrole")[0] == 0
    for role in ("litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest"):
        assert pg.one("SELECT pg_has_role('litkb_test', %s, 'USAGE')", (role,))[0] is False, role
    assert pg.one("SELECT has_database_privilege('litkb_test', 'litkb', 'CONNECT')")[0] is False


@pg_only
def test_no_agent_role_reads_token_hashes_through_any_relation(pg):
    """Third referee Z5: a view over workstream_tokens granted SELECT to an agent role gives the hashes
    back (with a guessable token, Z1, that is the token). No agent role and not PUBLIC may SELECT, at
    table or column level, workstream_tokens, any view that depends on it at any depth (pg_rewrite ->
    pg_depend), or any relation with a token_hash column."""
    offending = pg.conn.execute(
        """
        WITH RECURSIVE dep (rel) AS (
          SELECT 'litkb.workstream_tokens'::regclass::oid
          UNION
          SELECT rw.ev_class FROM pg_rewrite rw
            JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass AND d.objid = rw.oid
                            AND d.refclassid = 'pg_class'::regclass
            JOIN dep ON d.refobjid = dep.rel
           WHERE rw.ev_class <> dep.rel),
        exposed AS (SELECT rel FROM dep
                    UNION SELECT a.attrelid FROM pg_attribute a WHERE a.attname = 'token_hash' AND NOT a.attisdropped)
        SELECT r.name, c.relname FROM pg_class c JOIN exposed e ON e.rel = c.oid
          CROSS JOIN unnest(%s::text[] || ARRAY['public']) AS r(name)
         WHERE c.relowner <> coalesce((SELECT o.oid FROM pg_roles o WHERE o.rolname = r.name), 0)
           AND (has_table_privilege(r.name, c.oid, 'SELECT')
                OR EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                             AND has_column_privilege(r.name, c.oid, a.attnum, 'SELECT')))
         ORDER BY 1, 2
        """, (["litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest"],)).fetchall()
    assert offending == [], f"token hashes readable (role, relation): {offending}"


# ── fixes after the third referee (Reports/LITKB_P1_REFEREE3_2026-09-13.md), migration 0012 ─────

@pg_only
def test_workstream_token_is_not_derived_from_the_slug_or_id(pg):
    """F-4 / Z1: the token is random, not a hash of anything every role can read. The same slug opened
    again after abandoning it (the slug index is partial) gets another id and another token, and no
    token equals the sha256 or md5 of its slug or id."""
    import hashlib
    writer = pg.session("litkb_writer")
    slug = f"t-{uuid.uuid4().hex[:12]}"
    q = "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/test', NULL, 'p1 test', NULL)"
    ws1, tok1 = pg.one(q, (slug,), conn=writer)
    writer.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws1, tok1))
    ws2, tok2 = pg.one(q, (slug,), conn=writer)
    assert ws2 != ws1 and tok2 != tok1, "re-opening the same slug gave the same token"
    for ws, tok in ((ws1, tok1), (ws2, tok2)):
        for material in (slug, str(ws), ws.hex):
            for h in (hashlib.sha256, hashlib.md5):
                assert tok != h(material.encode("utf-8")).hexdigest(), f"the token is {h.__name__} of {material!r}"


@pg_only
def test_rebase_copies_head_evidence_whose_run_was_superseded(pg):
    """F-6 / Z12: E-5's copy takes the head's evidence rows as they are, including a row anchored in a
    run that is no longer the file's current one (ingest moved the file to a new run after the evidence
    was added). One row is copied, with the source's run_id."""
    w = _evidence_world(pg)
    writer = pg.session("litkb_writer")
    _, held_uv = _absent_gap_use(pg, w)
    _add_evidence(pg, writer, w, w["ws"], held_uv, w["text"][4:20], 4, 20)
    ingest = pg.session("litkb_ingest")
    r2 = _run(pg, ingest, w["file"], "ok")
    ingest.execute("SELECT litkb.set_current_run(%s, %s, %s)", (w["file"], w["run"], r2))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (w["file"],))[0] == r2
    source = _evidence_rows(pg, held_uv)
    # 0019, with this test's own twist: evidence anchored in a SUPERSEDED run is not promotable, so
    # the world's use is given its quote in r2 — the run that is current now — and only the
    # absent-gap chain is held. That is the hold this test is about.
    b2 = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES (%s, %s, 1, "
                "'paragraph', %s) RETURNING id", (w["file"], r2, w["text"]))[0]
    _make_promotable(pg, w, block=b2, run=r2)
    chain = _hold_and_rebase(pg, w, promotable=False)
    assert chain["evidence_copied"] == 1, chain
    copied = _evidence_rows(pg, chain["new_version"])
    assert copied == source and copied[0][1] == w["run"], copied


def _prepared_ws(pg):
    ws = pg.ws()
    writer = pg.session("litkb_writer")
    pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                {"question": "q", "gap_state": "open"}, None, ws)
    return ws, writer


@pg_only
def test_abandon_refused_while_promotion_prepared(pg):
    """F-2: a workstream whose promotion is prepared cannot be abandoned (55000); it stays open and the
    promotion still commits. Control: once the promotion is abandoned, the workstream can be."""
    ws, writer = _prepared_ws(pg)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (ws,), conn=promoter)[0]
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="prepared promotion"):
        writer.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws, pg.tokens[ws]))
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (ws,))[0] == "open"
    promoter.execute("SELECT litkb.promote_abandon(%s)", (pid,))
    writer.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws, pg.tokens[ws]))
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (ws,))[0] == "abandoned"
    # a prepared promotion in another workstream commits after its own abandon was refused
    ws2, writer2 = _prepared_ws(pg)
    pid2 = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (ws2,), conn=promoter)[0]
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        writer2.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws2, pg.tokens[ws2]))
    assert pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid2,), conn=promoter)[0]["committed"] == 1


@pg_only
def test_abandon_waits_for_a_prepare_in_flight_and_is_refused(pg):
    """F-2 (the referee's R5): promote_prepare is held open; abandon_workstream waits on the workstream
    row (FOR UPDATE), then sees the prepared promotion and is refused (55000). The workstream stays open
    and the promotion commits. Without the lock the prepared check runs before the prepare commits and
    the abandon lands."""
    ws, _writer = _prepared_ws(pg)
    holder = _holder(pg, "litkb_promoter")
    abandoner = pg.session("litkb_writer")
    prepared = {}

    def hold(k):
        prepared["pid"] = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (ws,), conn=k)[0]
    blocked, box = _race(pg, holder, hold, abandoner,
                         lambda k: k.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws, pg.tokens[ws])))
    assert getattr(box.get("error"), "sqlstate", None) == "55000", f"abandon during a prepare must be refused 55000, got {box}"
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (ws,))[0] == "open"
    promoter = pg.session("litkb_promoter")
    assert pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (prepared["pid"],), conn=promoter)[0]["committed"] == 1
    assert blocked, "the abandon was never observed waiting on the prepare; the race was not exercised"


_EMBED = "SELECT litkb.add_use_embedding(%s, %s, %s, 'm', 3, '[1,2,3]'::halfvec)"


def _embeddings(pg, uv):
    return pg.one("SELECT count(*) FROM litkb.use_embeddings WHERE use_version_id = %s", (uv,))[0]


@pg_only
def test_add_use_embedding_refuses_a_closed_workstreams_token(pg):
    """F-3: a merged workstream's token is refused (22023) even on a version that is still proposed (a
    chain held at commit), so only the open-workstream guard stands in the way; so is an abandoned one's."""
    w = _evidence_world(pg)
    # 0019 holds a use with no verified quote; this test's subject is elsewhere, so the
    # world's use is given one and reaches `prepared` as it did before.
    _make_promotable(pg, w)
    _, held_uv = _absent_gap_use(pg, w)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)[0]
    assert pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=promoter)[0]["held"] == 1
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (w["ws"],))[0] == "merged"
    assert pg.one("SELECT state FROM litkb.use_versions WHERE version_id = %s", (held_uv,))[0] == "proposed"
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.InvalidParameterValue, match="is not open"):
        writer.execute(_EMBED, (w["ws"], pg.tokens[w["ws"]], held_uv))
    assert _embeddings(pg, held_uv) == 0
    ws2 = pg.ws()
    work_id, _ = pg.work(ws2)
    _, uv2 = pg.proposal(writer, "use", None, {"work_id": str(work_id)}, None,
                         {"statement": "s", "kind": "method", "status": "proposed"}, None, ws2)
    writer.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws2, pg.tokens[ws2]))
    with pytest.raises(pg.errors.InvalidParameterValue, match="is not open"):
        writer.execute(_EMBED, (ws2, pg.tokens[ws2], uv2))
    assert _embeddings(pg, uv2) == 0


@pg_only
def test_add_use_embedding_refuses_a_promoted_or_prepared_version(pg):
    """F-3: in an open workstream, a promoted version and a prepared version of its own are refused
    (55000); main's promoted slot is never taken by an unreviewed vector."""
    w = _evidence_world(pg)
    # 0019 holds a use with no verified quote; this test's subject is elsewhere, so the
    # world's use is given one and reaches `prepared` as it did before.
    _make_promotable(pg, w)
    _, promoted = pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'use', NULL, %s, NULL, %s, "
        "NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"work_id": str(w["work"])}),
         pg.Jsonb({"statement": "already in main", "kind": "context", "status": "supported"}), w["ws"]))
    writer = pg.session("litkb_writer")
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="only to a proposed version"):
        writer.execute(_EMBED, (w["ws"], pg.tokens[w["ws"]], promoted))
    assert _embeddings(pg, promoted) == 0
    promoter = pg.session("litkb_promoter")
    pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)
    assert pg.one("SELECT state FROM litkb.use_versions WHERE version_id = %s", (w["uv"],))[0] == "prepared"
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="only to a proposed version"):
        writer.execute(_EMBED, (w["ws"], pg.tokens[w["ws"]], w["uv"]))
    assert _embeddings(pg, w["uv"]) == 0


@pg_only
def test_add_use_embedding_waits_for_a_commit_in_flight_and_is_refused(pg):
    """F-3 (the referee's R4): promote_commit is held open; add_use_embedding on a version the commit
    holds back (still proposed) waits on the workstream row (FOR SHARE against commit's FOR UPDATE),
    then finds the workstream merged and is refused (22023) with no row. Without the lock it reads the
    workstream as open and the embedding lands in a merged workstream."""
    w = _evidence_world(pg)
    _, held_uv = _absent_gap_use(pg, w)
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, repeat('a', 40), NULL)", (w["ws"],), conn=promoter)[0]
    holder = _holder(pg, "litkb_promoter")
    writer = pg.session("litkb_writer")
    blocked, box = _race(
        pg, holder, lambda k: pg.one("SELECT litkb.promote_commit(%s, repeat('b', 40))", (pid,), conn=k),
        writer, lambda k: k.execute(_EMBED, (w["ws"], pg.tokens[w["ws"]], held_uv)))
    assert getattr(box.get("error"), "sqlstate", None) == "22023", f"an embedding during a commit must be refused, got {box}"
    assert _embeddings(pg, held_uv) == 0
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (w["ws"],))[0] == "merged"
    assert blocked, "the embedding was never observed waiting on the commit; the race was not exercised"


@pg_only
def test_open_workstream_race_in_one_directory_leaves_no_orphan(pg, tmp_path):
    """F-7 (the referee's P5): two threads open a workstream in the same directory at once, ten rounds.
    Exactly one succeeds, the other gets WorkstreamFileExists, and exactly one workstream of the two is
    open: the one whose id is in the file. The old order (exists check, database, then the file) left
    an orphan open workstream every round."""
    from litkb import workstream
    for rnd in range(10):
        d = tmp_path / f"round{rnd}"
        d.mkdir()
        conns = [pg.session("litkb_writer"), pg.session("litkb_writer")]
        slugs = [f"t-{uuid.uuid4().hex[:12]}" for _ in conns]
        barrier = threading.Barrier(2)

        def opener(i):
            def run():
                barrier.wait(10)
                return workstream.open_workstream(conns[i], slugs[i], "work/test", "race", directory=d)
            return run
        started = [_in_thread(opener(i)) for i in range(2)]
        for th, _box in started:
            th.join(30)
            assert not th.is_alive()
        outcomes = sorted(type(box["error"]).__name__ if "error" in box else "ok" for _th, box in started)
        assert outcomes == ["WorkstreamFileExists", "ok"], (rnd, outcomes, [b.get("error") for _t, b in started])
        file_ws, _token = workstream.load(d)
        opened = [str(r[0]) for r in pg.conn.execute(
            "SELECT id FROM litkb.workstreams WHERE slug = ANY (%s) AND state = 'open'", (slugs,)).fetchall()]
        assert opened == [file_ws], f"round {rnd}: open workstreams {opened}, file names {file_ws}"
        for k in conns:
            k.close()


@pg_only
def test_open_workstream_failure_leaves_no_workstream_and_no_file(pg, tmp_path, monkeypatch):
    """F-7: a failure after the database call and before the commit (the token write fails) rolls the
    workstream back and removes the claimed file; the directory can then be used again."""
    import json
    import types

    from litkb import workstream
    writer = pg.session("litkb_writer")
    slug = f"t-{uuid.uuid4().hex[:12]}"

    def boom(*_a, **_k):
        raise OSError("token write failed (injected)")
    monkeypatch.setattr(workstream, "json", types.SimpleNamespace(dump=boom, loads=json.loads))
    with pytest.raises(OSError, match="injected"):
        workstream.open_workstream(writer, slug, "work/test", "p1 test", directory=tmp_path)
    assert not (tmp_path / workstream.TOKEN_FILE).exists(), "the claimed token file was left behind"
    assert pg.one("SELECT count(*) FROM litkb.workstreams WHERE slug = %s", (slug,))[0] == 0, \
        "an open workstream was left whose token is in no file"
    monkeypatch.setattr(workstream, "json", json)
    ws_id = workstream.open_workstream(writer, slug, "work/test", "p1 test", directory=tmp_path)
    assert workstream.load(tmp_path)[0] == str(ws_id)


@pg_only
def test_token_is_bound_never_visible_in_pg_stat_activity(pg):
    """F-8: while a writer call carrying the token waits in the server, pg_stat_activity.query for that
    backend shows the call with the token as a bound parameter ($n), never its text. Control (the probe
    can see literals): a query with an inlined marker IS visible to the same viewer, so a client that
    formatted the token into the SQL would fail this test."""
    viewer_q = "SELECT query FROM pg_stat_activity WHERE pid = %s"
    # control: an inlined literal is visible
    probe = pg.session("litkb_writer")
    probe_pid = _backend_pid(pg, probe)
    marker = f"litkb-visibility-marker-{uuid.uuid4().hex}"
    th, box = _in_thread(lambda: probe.execute(f"SELECT '{marker}', pg_sleep(3)"))
    seen = False
    end = time.monotonic() + 10
    while time.monotonic() < end and not seen:
        seen = marker in (pg.one(viewer_q, (probe_pid,))[0] or "")
        if not th.is_alive():
            break
        time.sleep(0.05)
    th.join(30)
    assert seen, "the viewer could not see an inlined literal; the probe below would be vacuous"
    # the real call: write_proposal waits on the workstream row an owner session holds FOR UPDATE
    ws = pg.ws()
    token = pg.tokens[ws]
    holder = pg.session()
    holder.autocommit = False
    writer = pg.session("litkb_writer")
    writer_pid = _backend_pid(pg, writer)
    try:
        holder.execute("SELECT 1 FROM litkb.workstreams WHERE id = %s FOR UPDATE", (ws,))
        th, box = _in_thread(lambda: pg.proposal(writer, "gap", None, {"slug": f"gap-{uuid.uuid4().hex[:8]}"}, None,
                                                 {"question": "q", "gap_state": "open"}, None, ws))
        blocked = _wait_blocked(pg, writer_pid, thread=th)
        query = pg.one(viewer_q, (writer_pid,))[0] or ""
        everywhere = pg.one("SELECT count(*) FROM pg_stat_activity WHERE strpos(query, %s) > 0", (token,))[0]
        holder.commit()
    except BaseException:
        holder.rollback()
        raise
    th.join(30)
    assert blocked, "the writer call was never observed waiting; its query text was not sampled in flight"
    assert "write_proposal" in query, f"sampled the wrong query: {query!r}"
    assert token not in query and everywhere == 0, "the token text is visible in pg_stat_activity"
    assert "error" not in box, box


@pytest.mark.parametrize("user", ["postgres", "litkb_owner"])
def test_connect_refuses_the_admin_logins(monkeypatch, user):
    """F-9: the agents' connect() refuses the superuser and the owner before any driver is loaded."""
    from litkb.db import connect as c
    with monkeypatch.context() as m:
        m.setitem(sys.modules, "psycopg", None)
        m.setitem(sys.modules, "psycopg.conninfo", None)
        with pytest.raises(c.AdminLoginRefused):
            c.connect(c.DB_MAIN, user)


class _Reached(Exception):
    pass


def test_admin_logins_open_only_through_connect_admin(monkeypatch):
    """F-9: connect_admin() opens only postgres and litkb_owner; the migration runner (for litkb) and
    provisioning reach the driver through it and never through connect()."""
    pytest.importorskip("psycopg")
    from psycopg.conninfo import conninfo_to_dict

    from litkb.db import connect as c
    from litkb.db import migrate, provision
    opened = []

    def fake_open(info, autocommit):
        opened.append(conninfo_to_dict(info)["user"])
        raise _Reached()
    monkeypatch.setattr(c, "_open", fake_open)
    for other in ("litkb_writer", "litkb_reader", "litkb_promoter", "litkb_ingest", "litkb_test", "postgres ", ""):
        with pytest.raises(c.LoginRefused):
            c.connect_admin(c.DB_MAIN, other)
    assert opened == []

    def no_connect(*_a, **_k):
        raise AssertionError("connect() was used for an admin login")
    monkeypatch.setattr(c, "connect", no_connect)
    with pytest.raises(_Reached):
        migrate.main(["--db", "litkb"])
    with pytest.raises(_Reached):
        provision.provision()
    assert opened == ["litkb_owner", "postgres"], opened

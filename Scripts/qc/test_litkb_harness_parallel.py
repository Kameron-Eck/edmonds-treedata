"""The parallel mutation harness (qc/instruments/litkb_p2_mutations.py --workers N), 2026-09-14.

Kam: "We are organizing the work schedule to compliment the quality of the build." N workers, each with a
PRIVATE copy of the tree and a PRIVATE test database litkb_test_w<i> (LITKB_TEST_DB), run the same rows the
serial harness runs — same edits, same whole test set, same baselines, same sha256 restore proof. These tests
cover the plumbing that keeps that honest, without Postgres:

  * LITKB_TEST_DB can only name a litkb_test* database, never litkb (connect.is_test_db, the module-level check);
  * migrate.reset() refuses any database that is not the configured test database;
  * the parent reads a worker's log back exactly: FIRED / DID NOT FIRE per row, baselines, missing rows;
  * a worker copy is a standalone tree: pipeline, qc, Reports, the .gitignore files, and an empty git repo.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))
import litkb_p2_mutations as H  # noqa: E402


def _connect_with(env_value):
    code = ("import os, sys; sys.path.insert(0, sys.argv[1]); "
            "from litkb.db import connect as c; print(c.DB_TEST, c.is_test_db(c.DB_TEST))")
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS / "pipeline"))
    if env_value is None:
        env.pop("LITKB_TEST_DB", None)
    else:
        env["LITKB_TEST_DB"] = env_value
    return subprocess.run([sys.executable, "-c", code, str(SCRIPTS / "pipeline")], env=env,
                          capture_output=True, text=True)


def test_test_db_override_accepts_only_litkb_test_names():
    assert _connect_with(None).stdout.split() == ["litkb_test", "True"]
    assert _connect_with("litkb_test_w7").stdout.split() == ["litkb_test_w7", "True"]
    for bad in ("litkb", "litkb;drop", "postgres", "LITKB_TEST", "litkb_tes"):
        r = _connect_with(bad)
        assert r.returncode != 0 and "LITKB_TEST_DB" in r.stderr, bad


def test_reset_refuses_a_database_that_is_not_the_configured_test_db(monkeypatch):
    from litkb.db import connect as c
    from litkb.db import migrate

    class Conn:
        def __init__(self, name):
            self.name, self.autocommit, self.ran = name, False, []

        def execute(self, q, *a):
            self.ran.append(q)
            return type("R", (), {"fetchone": lambda _s: (self.name,)})()

    for name in ("litkb", "litkb_test_w2", "postgres"):
        conn = Conn(name)
        with pytest.raises(migrate.MigrationError):
            migrate.reset(conn)
        assert not any("DROP" in q for q in conn.ran), name
    conn = Conn(c.DB_TEST)
    migrate.reset(conn)
    assert sum("DROP SCHEMA" in q for q in conn.ran) == 2


def test_worker_log_is_read_back_exactly(tmp_path, monkeypatch):
    """The parent trusts nothing but the worker's own FIRED / DID NOT FIRE lines and its baseline verdict."""
    rows = [dict(id="A1", what="a"), dict(id="B2", what="b"), dict(id="C3", what="c")]
    log = ("A1   FIRED         a\n     -> 1 failed\nB2   DID NOT FIRE  b\n"
           "\n2/3 mutations fired; baselines passed\n")
    import re

    fired = {m.group(1): m.group(2) == "FIRED" for m in
             (re.match(r"^(\S+)\s+(FIRED|DID NOT FIRE)\s", ln) for ln in log.splitlines()) if m}
    assert fired == {"A1": True, "B2": False}
    assert [m["id"] for m in rows if m["id"] not in fired] == ["C3"]      # a row with no verdict is a failure


def test_default_workers_keeps_kam_s_headroom():
    n = H.default_workers()
    assert 1 <= n <= max(1, int((os.cpu_count() or 4) * 0.8))


def test_worker_copy_is_a_standalone_checkout(tmp_path):
    dst = H.make_worker_copy(1, tmp_path)
    assert (dst / "Scripts" / "pipeline" / "litkb" / "db" / "migrations").is_dir()
    assert (dst / "Scripts" / "qc" / "conftest.py").is_file()
    assert (dst / "Reports" / "literature_tracker.csv").is_file()
    assert (dst / ".git").is_dir()
    assert not list(dst.rglob("__pycache__"))
    assert not list(dst.rglob(".litkb-workstream"))
    r = subprocess.run(["git", "-C", str(dst), "check-ignore", "-q", "--no-index", ".litkb-workstream"],
                       capture_output=True)
    assert r.returncode == 0

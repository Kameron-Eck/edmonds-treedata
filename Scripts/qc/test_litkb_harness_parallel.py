"""The parallel mutation harness (qc/instruments/litkb_p2_mutations.py --workers N), 2026-09-14.

Kam: "We are organizing the work schedule to compliment the quality of the build." N workers, each with a
PRIVATE copy of the tree and a PRIVATE test database litkb_test_w<i> (LITKB_TEST_DB), run the same rows the
serial harness runs — same edits, same whole test set, same baselines, same sha256 restore proof. These tests
cover the plumbing that keeps that honest, without Postgres:

  * LITKB_TEST_DB can only name a litkb_test* database, never litkb (connect.is_test_db, the module-level check);
  * migrate.reset() refuses any database that is not the configured test database;
  * the parent reads a worker's log back exactly: FIRED / DID NOT FIRE / NO RESULT per row, baselines, staleness;
  * every chosen row reaches exactly one worker, and an empty partition is an error, never "run all rows";
  * a worker whose copy differs from the source tree aborts without reporting a verdict;
  * a worker copy is a standalone tree: pipeline, qc, Reports, the .gitignore files, and an empty git repo.

The harness module is loaded by path (importlib), like qc/test_litkb_harness_sites.py does — the ledger of
sys.path surgery is closed (CLAUDE.md 2.4).
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
FIXTURE = SCRIPTS / "qc" / "fixtures" / "litkb_worker_log.txt"


def _harness():
    spec = importlib.util.spec_from_file_location("litkb_p2_mutations",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_p2_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _harness()


def _connect_with(env_value):
    code = "from litkb.db import connect as c; print(c.DB_TEST, c.is_test_db(c.DB_TEST))"
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS / "pipeline"))
    if env_value is None:
        env.pop("LITKB_TEST_DB", None)
    else:
        env["LITKB_TEST_DB"] = env_value
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)


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

    # E-1 (referee 2): the "foreign" worker name must be chosen RELATIVE to the active LITKB_TEST_DB. It was
    # hard-coded to litkb_test_w2, so under LITKB_TEST_DB=litkb_test_w2 that name IS the configured test db,
    # reset() rightly permitted it, and the test failed on the one worker name someone would naturally use.
    foreign = next(n for n in (f"litkb_test_w{i}" for i in range(1, 100)) if n != c.DB_TEST)
    for name in ("litkb", foreign, "postgres"):
        conn = Conn(name)
        with pytest.raises(migrate.MigrationError):
            migrate.reset(conn)
        assert not any("DROP" in q for q in conn.ran), name
    conn = Conn(c.DB_TEST)
    migrate.reset(conn)
    assert sum("DROP SCHEMA" in q for q in conn.ran) == 2


# ── the parent's reading of a worker (D-3: a committed fixture, never a second copy of the parser) ──

def test_parse_worker_log_against_the_committed_fixture():
    """qc/fixtures/litkb_worker_log.txt is a hand-written worker log. The expected output below is written
    out by hand too: if parse_worker_log's regex changes, this fails. The old test re-implemented the regex
    inline and asserted it against itself, which is the defect 3.4c is about (referee D-3)."""
    fired, base_ok, stale = H.parse_worker_log(FIXTURE.read_text(encoding="utf-8"))
    assert fired == {"A1": True, "B6": False, "S18": True}
    assert base_ok is True
    assert stale == []
    # the lines that must NOT be read as verdicts: the restore proof, the summary, an indented "-> 1 failed"
    assert "restored" not in fired and "2/3" not in fired


def test_parse_worker_log_reports_a_stale_copy_and_a_failed_baseline():
    text = ("STALE COPY: 1 file(s) differ from the source tree, e.g. Scripts/qc/test_litkb_p2.py CHANGED\n"
            "this worker reports NO verdict: a stale copy produces false survivors (referee D-2)\n")
    fired, base_ok, stale = H.parse_worker_log(text)
    assert fired == {} and base_ok is False and len(stale) == 1


def test_a_row_without_a_verdict_is_never_printed_as_a_survivor():
    assert (H.verdict_label(True), H.verdict_label(False), H.verdict_label(None)) == (
        "FIRED", "DID NOT FIRE", "NO RESULT")


# ── the partition (Kill C / D-5) ──

def test_partition_covers_every_row_exactly_once_and_never_leaves_an_empty_part():
    chosen = [dict(id=f"X{i}") for i in range(5)]
    for n in (1, 2, 3, 5, 9):
        parts = H.partition(chosen, n)
        assert all(parts), n
        H.check_partition(parts, chosen)
        assert sorted(m["id"] for p in parts for m in p) == sorted(m["id"] for m in chosen)


def test_a_dropped_row_is_reported_by_name():
    chosen = [dict(id="A1"), dict(id="B6"), dict(id="S18")]
    parts = H.partition(chosen, 2)
    parts[0] = parts[0][1:]                       # the referee's Break C, exactly
    with pytest.raises(RuntimeError) as e:
        H.check_partition(parts, chosen)
    assert "A1" in str(e.value) and "dropped" in str(e.value)


def test_an_empty_partition_is_an_error_not_a_silent_run_of_everything():
    chosen = [dict(id="A1"), dict(id="B6")]
    with pytest.raises(RuntimeError) as e:
        H.check_partition([chosen, []], chosen)
    assert "empty" in str(e.value)
    r = _run_worker(["--worker", "--only", ""])
    assert r.returncode != 0 and "refusing to run" in (r.stdout + r.stderr)
    r = _run_worker(["--worker"])
    assert r.returncode != 0 and "--worker requires --only" in (r.stdout + r.stderr)


def _run_worker(args, cwd=None):
    env = dict(os.environ, PYTHONPATH=str((Path(cwd) if cwd else SCRIPTS) / "pipeline"), PYTHONUTF8="1")
    script = (Path(cwd) if cwd else SCRIPTS) / "qc" / "instruments" / "litkb_p2_mutations.py"
    return subprocess.run([sys.executable, str(script), *args], cwd=str(cwd or SCRIPTS), env=env,
                          capture_output=True, text=True)


# ── the stale-copy kill (D-2) ──

def test_manifest_diff_sees_a_changed_missing_and_extra_file():
    src = {"a": "1", "b": "2"}
    assert H.manifest_diff(src, src) == []
    assert sorted(H.manifest_diff(src, {"a": "9", "c": "3"})) == [
        ("a", "CHANGED"), ("b", "MISSING from the copy"), ("c", "EXTRA in the copy")]


def test_a_stale_worker_copy_aborts_without_reporting_a_verdict(tmp_path):
    """Break B of the referee: a worker copy whose qc/test_litkb_p2.py is a stub baselined 82 tests instead
    of 241 and reported a FALSE SURVIVOR. The copy is now compared to the source before any row runs."""
    dst = H.make_worker_copy(1, tmp_path)
    manifest = tmp_path / "source.manifest.json"
    manifest.write_text(json.dumps(H.tree_manifest(SCRIPTS.parent)), encoding="utf-8")
    assert H.manifest_diff(json.loads(manifest.read_text(encoding="utf-8")), H.tree_manifest(dst)) == []
    (dst / "Scripts" / "qc" / "test_litkb_p2.py").write_text("def test_stub():\n    pass\n", encoding="utf-8")
    r = _run_worker(["--worker", "--manifest", str(manifest), "--only", "B6"], cwd=dst / "Scripts")
    assert r.returncode == 2, r.stdout[-2000:]
    assert "STALE COPY:" in r.stdout and "qc/test_litkb_p2.py CHANGED" in r.stdout
    fired, base_ok, stale = H.parse_worker_log(r.stdout)
    assert fired == {} and not base_ok and stale          # no verdict for B6 — not a survivor


def test_a_stale_root_gitignore_is_caught_by_the_manifest(tmp_path):
    """Referee 2 E-2: make_worker_copy copies the repo-root .gitignore after copytree, but tree_manifest
    walked only COPY_DIRS, so a stale root .gitignore gave manifest_diff == [] — caught only by a baseline,
    and only for the 37 rows that run the P1 set. The manifest's domain now equals the copy's."""
    dst = H.make_worker_copy(1, tmp_path)
    manifest = tmp_path / "source.manifest.json"
    manifest.write_text(json.dumps(H.tree_manifest(SCRIPTS.parent)), encoding="utf-8")
    assert ".gitignore" in json.loads(manifest.read_text(encoding="utf-8"))
    assert H.manifest_diff(json.loads(manifest.read_text(encoding="utf-8")), H.tree_manifest(dst)) == []
    gi = dst / ".gitignore"                                   # the referee's Break E, exactly
    gi.write_text("\n".join(ln for ln in gi.read_text(encoding="utf-8").splitlines()
                            if ".litkb-workstream" not in ln) + "\n", encoding="utf-8")
    r = _run_worker(["--worker", "--manifest", str(manifest), "--only", "B6"], cwd=dst / "Scripts")
    assert r.returncode == 2, r.stdout[-2000:]
    assert "STALE COPY:" in r.stdout and ".gitignore CHANGED" in r.stdout
    fired, base_ok, stale = H.parse_worker_log(r.stdout)
    assert fired == {} and not base_ok and stale


# ── the headroom rule (D-7) ──

def test_default_workers_is_the_hand_written_number_for_a_given_thread_count(monkeypatch):
    for threads, expected in ((12, 9), (8, 6), (4, 3), (2, 1), (1, 1)):
        monkeypatch.setattr(os, "cpu_count", lambda t=threads: t)
        assert H.default_workers() == expected, threads
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    assert H.default_workers() == 3                       # the (os.cpu_count() or 4) fallback


def test_workers_above_the_headroom_rule_is_refused_unless_overridden():
    n = H.default_workers()
    r = _run_worker(["--workers", str(n + 8), "--only", "B6"])
    assert r.returncode != 0 and "exceeds the headroom rule" in (r.stdout + r.stderr)


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

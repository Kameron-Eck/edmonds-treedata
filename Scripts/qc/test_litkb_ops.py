"""litkb operations: the nightly dump (litkb.ops.nightly_dump) and the staged-secrets check
(qc/secrets_check.py). decisions.yaml litkb-p0-foundation; Reports/LITKB_OPS_2026-09-13.md.

Kills, each shown to fire here (CLAUDE.md 3.4c):
  a truncated dump fails verification and is not kept     test_truncated_dump_is_rejected_by_verification,
                                                          test_run_does_not_keep_a_dump_that_fails_verification
  damage at rest is caught by the manifest hash           test_damage_at_rest_is_caught_by_the_manifest_hash
  a restore row-count mismatch is reported as failure     test_count_comparison_sees_one_extra_row,
                                                          test_run_reports_a_restore_count_mismatch_as_failure
  retention deletes only verified dumps this script wrote test_retention_deletes_only_listed_verified_dumps
  a planted pgpass file / .env / pgpass line is refused   test_planted_secrets_are_refused[*]
  the repository itself is clean                          test_repository_index_has_no_secrets

The dump tests log in ONLY as litkb_test, to litkb_test (the P1 suite's isolation rule), and dump
only a throwaway schema of their own with pg_dump -n, so a concurrent reset of the litkb schemas by
another worktree's P1 session cannot break them. The restore itself needs the superuser (CREATE
DATABASE); it is exercised by the real run recorded in the report, and here through its comparison.
"""
import datetime as dt
import secrets
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
CHECK = SCRIPTS / "qc" / "secrets_check.py"
_SKIP_WHEN = ("connection refused", "could not connect", "does not exist",
              "no password supplied", "timeout expired", "is the server running")
# the conftest counts this marker in the "litkb Postgres tests" summary, so a server-down skip is visible
pg_only = pytest.mark.requires_litkb_pg


# ── staged-secrets check ────────────────────────────────────────────────────────────────────────

def _check(repo):
    return subprocess.run([sys.executable, str(CHECK), "--repo", str(repo)], capture_output=True,
                          text=True, errors="replace")


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.fixture
def scratch_git(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "clean")
    return repo


def _plant(repo, rel, text, commit=False):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-f", rel)
    if commit:
        _git(repo, "commit", "-q", "-m", "plant")


def _pw():
    return secrets.token_urlsafe(18)   # 24 chars, generated per run: never a real credential


def test_repository_index_has_no_secrets():
    r = _check(REPO)
    assert r.returncode == 0, r.stdout + r.stderr


def test_clean_scratch_repo_passes(scratch_git):
    r = _check(scratch_git)
    assert r.returncode == 0 and "clean" in r.stdout, r.stdout


@pytest.mark.parametrize("rel,text,commit", [
    ("conn/notes.txt", f"localhost:5433:litkb:litkb_owner:{_pw()}\n", False),      # pgpass line, innocent name
    ("docs/setup.md", f"# setup\n\n    *:5433:*:litkb_writer:{_pw()}\n", True),     # committed = tracked
    (".env", "UNPAYWALL_EMAIL=someone\n", False),
    ("Scripts/tool/paper_search.env", "X=1\n", False),
    ("pgpass.conf", "# empty\n", False),
    ("litkb_promoter.pgpass", "# empty\n", False),
    ("Scripts/.litkb-workstream", "{}\n", False),
    ("secrets/readme.txt", "nothing here\n", False),
    ("cfg/app.yaml", f"api_token: \"{secrets.token_hex(32)}\"\n", False),
    ("cfg/run.py", f"WS_TOKEN = '{secrets.token_hex(32)}'\n", False),
])
def test_planted_secrets_are_refused(scratch_git, rel, text, commit):
    _plant(scratch_git, rel, text, commit=commit)
    r = _check(scratch_git)
    assert r.returncode == 1 and rel.replace("\\", "/") in r.stdout, r.stdout
    value = text.strip().rsplit(":", 1)[-1].strip().strip("'\"")
    if len(value) >= 16:
        assert value not in r.stdout, "the check printed the secret it found"


@pytest.mark.parametrize("rel,text", [
    ("digests.csv", f"file,sha256\na.pdf,{secrets.token_hex(32)}\n"),                # a digest, not a token
    ("run.log", "2026-09-09T12:06:08Z,2026-09-09T15:07:16Z,3.0189,1,,,\n"),
    ("short.txt", "localhost:5433:litkb:litkb_test:short\n"),                        # < 16 chars
    ("rows.csv", "bb50b.csv.prev.1000,,,,,2026-09-09T12:06:08Z,2026-09-09T15:07:16Z,3.0189,1,,,,,\n"),
    ("pgpass_writer.py", "line = f\"{host}:{port}:{db}:{role}:{password}\"\n"),        # code that writes one
    ("allowed.py", f"example_token = \"{'ab' * 32}\"  # secrets-check: allow documented fake value\n"),
])
def test_known_harmless_shapes_pass(scratch_git, rel, text):
    _plant(scratch_git, rel, text)
    r = _check(scratch_git)
    assert r.returncode == 0, r.stdout


def test_allow_pragma_needs_a_reason(scratch_git):
    _plant(scratch_git, "bare.py", f"example_token = \"{secrets.token_hex(32)}\"  # secrets-check: allow\n")
    assert _check(scratch_git).returncode == 1


def test_unstaging_clears_the_refusal(scratch_git):
    _plant(scratch_git, ".env", "A=1\n")
    assert _check(scratch_git).returncode == 1
    _git(scratch_git, "rm", "-q", "--cached", ".env")
    assert _check(scratch_git).returncode == 0


# ── nightly dump ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def opsdb():
    """A throwaway schema in litkb_test with enough rows to span many compressed blocks."""
    psycopg = pytest.importorskip("psycopg", reason="requires_litkb_pg: psycopg is not installed")
    from psycopg import sql

    from litkb.db import connect as c
    try:
        conn = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
    except psycopg.OperationalError as e:
        if any(s in str(e).lower() for s in _SKIP_WHEN):
            pytest.skip(f"requires_litkb_pg: litkb_test unavailable ({str(e).strip().splitlines()[-1][:160]})")
        raise
    schema = f"litkb_opstest_{uuid.uuid4().hex[:10]}"
    ident = sql.Identifier(schema)
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(ident))
    conn.execute(sql.SQL("CREATE TABLE {}.rows (id int PRIMARY KEY, body text)").format(ident))
    conn.execute(sql.SQL("INSERT INTO {}.rows SELECT g, md5(g::text) || md5((g * 7)::text) "
                         "FROM generate_series(1, 20000) g").format(ident))
    conn.execute(sql.SQL("CREATE TABLE {}.empty (id int)").format(ident))
    try:
        yield conn, schema
    finally:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(ident))
        conn.close()


def _nd():
    from litkb.ops import nightly_dump
    return nightly_dump


_T0 = dt.datetime(2026, 9, 13, 2, 30, 0, tzinfo=dt.timezone.utc)


def _dump(out, schema, now=_T0, **kw):
    nd = _nd()
    kw.setdefault("restore", False)
    return nd.run(db="litkb_test", user="litkb_test", out_dir=out, schemas=[schema], dump_schemas=[schema],
                  now=now, **kw)


def _log(out):
    return (Path(out) / "nightly_dump.log").read_text(encoding="utf-8").splitlines()


@pg_only
def test_good_dump_is_verified_listed_and_logged(opsdb, tmp_path):
    _conn, schema = opsdb
    nd = _nd()
    assert _dump(tmp_path, schema) == 0, _log(tmp_path)
    files = sorted(p.name for p in tmp_path.glob("*.dump"))
    assert files == ["litkb_test_20260913T023000Z.dump"]
    m = nd.load_manifest(tmp_path)
    assert [e["name"] for e in m["dumps"]] == files
    assert m["dumps"][0]["sha256"] == nd.sha256_file(tmp_path / files[0])
    assert nd.verify_dump(tmp_path / files[0], expected_sha=m["dumps"][0]["sha256"])[0]
    lines = _log(tmp_path)
    assert len(lines) == 1 and "status=ok" in lines[0] and "restore=skipped" in lines[0], lines
    assert not list(tmp_path.glob("*.partial")) and not list(tmp_path.glob("*.rejected"))


@pg_only
@pytest.mark.parametrize("cut", ["one_byte", "last_200_bytes", "half"])
def test_truncated_dump_is_rejected_by_verification(opsdb, tmp_path, cut):
    """The kill. `pg_restore --list` alone passes a tail cut (it reads only the TOC at the head); the
    full read must catch every cut."""
    _conn, schema = opsdb
    nd = _nd()
    assert _dump(tmp_path, schema) == 0
    good = next(tmp_path.glob("*.dump"))
    data = good.read_bytes()
    n = {"one_byte": len(data) - 1, "last_200_bytes": len(data) - 200, "half": len(data) // 2}[cut]
    bad = tmp_path / "cut.dump"
    bad.write_bytes(data[:n])
    ok, stage, reason = nd.verify_dump(bad)
    assert not ok and stage in ("list", "read"), (stage, reason)


@pg_only
def test_list_stage_alone_would_pass_a_tail_cut(opsdb, tmp_path):
    """Why the read stage exists: the TOC-only check is fooled by a tail cut (control for the kill above)."""
    _conn, schema = opsdb
    nd = _nd()
    assert _dump(tmp_path, schema) == 0
    data = next(tmp_path.glob("*.dump")).read_bytes()
    bad = tmp_path / "cut.dump"
    bad.write_bytes(data[:-200])
    r = subprocess.run([nd._exe("pg_restore"), "--list", str(bad)], capture_output=True)
    assert r.returncode == 0, "pg_restore --list now catches tail cuts; the docstring claim is stale"


@pg_only
def test_run_does_not_keep_a_dump_that_fails_verification(opsdb, tmp_path, monkeypatch):
    """pg_dump 'succeeds' but leaves a truncated file: the run fails, nothing is listed or kept as .dump."""
    _conn, schema = opsdb
    nd = _nd()
    real = nd._pg_dump

    def truncating(db, user, snapshot, path, dump_schemas, passfile):
        r = real(db, user, snapshot, path, dump_schemas, passfile)
        data = Path(path).read_bytes()
        Path(path).write_bytes(data[:len(data) // 2])
        return r
    monkeypatch.setattr(nd, "_pg_dump", truncating)
    assert _dump(tmp_path, schema) == 1
    assert not list(tmp_path.glob("*.dump")), "a dump that failed verification was kept under a good name"
    assert len(list(tmp_path.glob("*.rejected"))) == 1
    assert nd.load_manifest(tmp_path)["dumps"] == []
    lines = _log(tmp_path)
    assert len(lines) == 1 and "status=FAIL" in lines[0] and "kept=no" in lines[0], lines


@pg_only
def test_damage_at_rest_is_caught_by_the_manifest_hash(opsdb, tmp_path):
    _conn, schema = opsdb
    nd = _nd()
    assert _dump(tmp_path, schema) == 0
    good = next(tmp_path.glob("*.dump"))
    data = bytearray(good.read_bytes())
    i = len(data) * 2 // 3
    data[i:i + 28] = b"GARBAGEGARBAGEGARBAGEGARBAGE"
    good.write_bytes(bytes(data))
    sha = nd.load_manifest(tmp_path)["dumps"][0]["sha256"]
    assert not nd.verify_dump(good, expected_sha=sha)[0]
    assert nd.verify_existing(tmp_path) == 1
    assert "status=FAIL" in _log(tmp_path)[-1]


@pg_only
def test_count_comparison_sees_one_extra_row(opsdb):
    """Real counts, before and after one insert, and a dropped table: each is a difference."""
    conn, schema = opsdb
    from psycopg import sql
    nd = _nd()
    before = nd.table_counts(conn, [schema])
    assert before == {f"{schema}.empty": 0, f"{schema}.rows": 20000}
    assert nd.compare_counts(before, dict(before)) == []
    conn.execute(sql.SQL("INSERT INTO {}.empty VALUES (1)").format(sql.Identifier(schema)))
    after = nd.table_counts(conn, [schema])
    assert nd.compare_counts(before, after) == [f"{schema}.empty: source 0 rows, restore 1"]
    conn.execute(sql.SQL("DROP TABLE {}.empty").format(sql.Identifier(schema)))
    assert nd.compare_counts(before, nd.table_counts(conn, [schema])) == [f"{schema}.empty: missing from the restore"]


@pg_only
def test_run_reports_a_restore_count_mismatch_as_failure(opsdb, tmp_path, monkeypatch):
    """The restore step returns counts taken from the live schema AFTER one more row was written (a
    restore that does not match the dump's snapshot): the run exits 1, logs MISMATCH, does not record
    a good restore check, and never lets retention delete that dump."""
    conn, schema = opsdb
    from psycopg import sql
    nd = _nd()

    def mismatching(dump_path, source_db, schemas, passfile):
        conn.execute(sql.SQL("INSERT INTO {}.rows VALUES (-1, 'late')").format(sql.Identifier(schema)))
        return nd.table_counts(conn, schemas)
    monkeypatch.setattr(nd, "restore_and_count", mismatching)
    assert _dump(tmp_path, schema, restore=True) == 1
    lines = _log(tmp_path)
    assert "status=FAIL" in lines[-1] and "restore=MISMATCH" in lines[-1], lines
    m = nd.load_manifest(tmp_path)
    assert m["last_restore_check_utc"] is None
    assert m["dumps"][0]["restore_check"]["ok"] is False
    assert m["dumps"][0]["restore_check"]["differences"] == [f"{schema}.rows: source 20000 rows, restore 20001"]

    # control: the same run with a matching restore passes and records the check
    monkeypatch.setattr(nd, "restore_and_count", lambda d, s, schemas, p: nd.table_counts(conn, schemas))
    assert _dump(tmp_path, schema, now=_T0 + dt.timedelta(days=1), restore=True) == 0
    assert nd.load_manifest(tmp_path)["last_restore_check_utc"] == "2026-09-14T02:30:00Z"


def test_restore_is_due_weekly():
    nd = _nd()
    assert nd.restore_due({"last_restore_check_utc": None}, _T0)
    assert not nd.restore_due({"last_restore_check_utc": "2026-09-07T02:30:01Z"}, _T0)
    assert nd.restore_due({"last_restore_check_utc": "2026-09-06T02:30:00Z"}, _T0)


@pg_only
def test_retention_deletes_only_listed_verified_dumps(opsdb, tmp_path):
    """keep=3 over 6 nightly runs. Survivors: the newest 3; a same-shaped dump the manifest does not
    list (older than all of them); a listed dump whose bytes changed (hash mismatch); a stray file."""
    _conn, schema = opsdb
    nd = _nd()
    stranger = tmp_path / "litkb_test_20000101T000000Z.dump"
    stray = tmp_path / "notes.txt"
    for day in range(6):
        if day == 1:
            shutil.copy(next(tmp_path.glob("litkb_test_20260913*.dump")), stranger)
            stray.write_text("keep me", encoding="utf-8")
            first = tmp_path / "litkb_test_20260913T023000Z.dump"
            first.write_bytes(first.read_bytes() + b"\0")    # listed, but no longer the verified bytes
        assert _dump(tmp_path, schema, now=_T0 + dt.timedelta(days=day), keep=3) == 0, _log(tmp_path)
    names = sorted(p.name for p in tmp_path.glob("*.dump"))
    assert names == ["litkb_test_20000101T000000Z.dump", "litkb_test_20260913T023000Z.dump",
                     "litkb_test_20260916T023000Z.dump", "litkb_test_20260917T023000Z.dump",
                     "litkb_test_20260918T023000Z.dump"], names
    assert stray.exists()
    listed = [e["name"] for e in nd.load_manifest(tmp_path)["dumps"]]
    assert listed == ["litkb_test_20260913T023000Z.dump", "litkb_test_20260916T023000Z.dump",
                      "litkb_test_20260917T023000Z.dump", "litkb_test_20260918T023000Z.dump"], listed
    assert "sha256 differs" in _log(tmp_path)[-1]

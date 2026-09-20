"""The litkb migration runner: plain SQL files, applied in order, each in its own transaction.

    py -3.12 -m litkb.db.migrate --db litkb              apply pending migrations
    py -3.12 -m litkb.db.migrate --db litkb_test --reset drop the schema first (test DB only)

(Until the editable install is re-run from a tree that contains litkb, run with
PYTHONPATH=Scripts/pipeline.)

Rules the runner enforces:
  * files are named NNNN_name.sql and numbered 1..N with no gaps;
  * an applied migration may never change: its sha256 (computed over LF-normalised bytes, so
    a CRLF checkout does not read as an edit) is recorded in litkb_meta.schema_migrations
    and compared on every run; a change is refused, never re-applied;
  * an applied migration missing on disk is refused;
  * concurrent runners serialise on an advisory lock;
  * --reset refuses any database other than litkb_test.

Roles: the runner connects as the database's owner — litkb_owner for litkb, litkb_test for
litkb_test (design §4.7, §9).
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

from . import connect as _c

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
RUNNER_ROLE = {_c.DB_MAIN: "litkb_owner", _c.DB_TEST: "litkb_test"}
LOCK_KEY = 0x6C69746B  # "litk"
_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
RESERVED_FILE = MIGRATIONS_DIR / "_reserved.txt"


class MigrationError(RuntimeError):
    pass


def reserved(path=None):
    """Migration numbers a CONCURRENT branch has claimed but not yet landed here -> {version: why}.

    The gap-free rule below exists to catch a migration that went missing. It cannot tell that from
    a number another branch is about to take, and with several branches open at once the second case
    is the ordinary one: 0020 was written here while 0018 and 0019 were being written on
    `work/20260915-access-layer`, and a branch that cannot even run its own migrations until an
    unrelated branch merges is a branch that will renumber under pressure and collide.

    So a gap is allowed only when it is DECLARED, one line per number, in `_reserved.txt`. A number
    that is missing and not declared is still a lost migration and still refused; a declared number
    that has landed is simply no longer missing, so the line is deleted with the merge that lands it.

    A declaration can also be PERMANENT, which this docstring did not admit until 2026-09-20: a
    branch may merge without ever writing the migration it reserved (0024, work/20260920-web-source-
    gate). Renumbering the files above it is not an option — instruments, mutation rows and reports
    name migrations by number — so the number is retired, the gap stays, and the line stays with it.
    Nothing here treats the two cases differently; both are a `NNNN why` line and both are allowed.
    """
    p = Path(path or RESERVED_FILE)
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        number, _, why = line.partition(" ")
        if not number.isdigit() or len(number) != 4:
            raise MigrationError(f"{p.name}: a reserved line starts with NNNN, got {line!r}")
        out[int(number)] = why.strip()
    return out


def discover(directory=MIGRATIONS_DIR, reserved_path=None):
    """[(version, filename, sha256, sql_text)], validated for naming and contiguity."""
    found = []
    for p in sorted(Path(directory).glob("*.sql")):
        m = _NAME.match(p.name)
        if not m:
            raise MigrationError(f"migration file is not named NNNN_name.sql: {p.name}")
        body = p.read_bytes().replace(b"\r\n", b"\n")
        found.append((int(m.group(1)), p.name, hashlib.sha256(body).hexdigest(),
                      body.decode("utf-8")))
    held = reserved(reserved_path if reserved_path is not None else Path(directory) / "_reserved.txt")
    expected = 1
    for version, name, _sha, _sql in found:
        while expected in held and expected < version:
            expected += 1
        if version != expected:
            raise MigrationError(
                f"migrations must be numbered 1..N without gaps: expected {expected:04d}, found {name}"
                + (f" ({len(held)} reserved: {sorted(held)})" if held else ""))
        expected += 1
    if not found:
        raise MigrationError(f"no migrations found in {directory}")
    return found


def apply(conn, directory=MIGRATIONS_DIR):
    """Apply every pending migration. Returns the filenames applied, in order."""
    migrations = discover(directory)
    conn.autocommit = True
    conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
    try:
        conn.execute("CREATE SCHEMA IF NOT EXISTS litkb_meta")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS litkb_meta.schema_migrations ("
            " version integer PRIMARY KEY,"
            " name text NOT NULL,"
            " sha256 text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now(),"
            " applied_by text NOT NULL DEFAULT current_user)")
        applied = {v: (n, s) for v, n, s in conn.execute(
            "SELECT version, name, sha256 FROM litkb_meta.schema_migrations").fetchall()}
        on_disk = {v: (n, s) for v, n, s, _sql in migrations}
        # BEGIN guard: applied migrations are immutable
        for version, (name, sha) in sorted(applied.items()):
            if version not in on_disk:
                raise MigrationError(
                    f"applied migration {version:04d} ({name}) is missing on disk")
            if on_disk[version] != (name, sha):
                raise MigrationError(
                    f"applied migration {version:04d} ({name}) changed on disk after it was "
                    "applied; write a new migration instead of editing an applied one")
        # END guard: applied migrations are immutable
        ran = []
        for version, name, sha, sql_text in migrations:
            if version in applied:
                continue
            with conn.transaction():
                conn.execute(sql_text)
                conn.execute(
                    "INSERT INTO litkb_meta.schema_migrations (version, name, sha256) "
                    "VALUES (%s, %s, %s)", (version, name, sha))
            ran.append(name)
        return ran
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def runner_connect(db):
    """The runner's login for db: the owner through connect_admin() (connect() refuses it, third
    referee F-9); litkb_test, which owns the test database, through connect()."""
    role = RUNNER_ROLE[db]
    if role in _c.ADMIN_LOGINS:
        return _c.connect_admin(db, role, autocommit=True)
    return _c.connect(db, role, autocommit=True)


def reset(conn):
    """Drop the litkb schemas. Refused anywhere but litkb_test (the server also refuses the
    litkb_test role on litkb; this is the second lock, not the only one)."""
    db = conn.execute("SELECT current_database()").fetchone()[0]
    # BEGIN guard: reset only the test database
    if db != _c.DB_TEST or not _c.is_test_db(db):
        raise MigrationError(f"reset refused: only {_c.DB_TEST} may be reset, this is {db}")
    # END guard: reset only the test database
    conn.autocommit = True
    conn.execute("DROP SCHEMA IF EXISTS litkb CASCADE")
    conn.execute("DROP SCHEMA IF EXISTS litkb_meta CASCADE")


def main(argv=None):
    ap = argparse.ArgumentParser(description="apply litkb SQL migrations")
    ap.add_argument("--db", required=True, choices=sorted(RUNNER_ROLE))
    ap.add_argument("--reset", action="store_true",
                    help=f"drop the litkb schemas first ({_c.DB_TEST} only)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    conn = runner_connect(a.db)
    try:
        if a.reset:
            reset(conn)
            print(f"litkb.migrate: {a.db}: schemas dropped")
        ran = apply(conn)
        total = conn.execute("SELECT count(*) FROM litkb_meta.schema_migrations").fetchone()[0]
    finally:
        conn.close()
    print(f"litkb.migrate: {a.db} as {RUNNER_ROLE[a.db]}: applied {len(ran)} "
          f"({', '.join(ran) or 'none pending'}); {total} recorded")


if __name__ == "__main__":
    main()

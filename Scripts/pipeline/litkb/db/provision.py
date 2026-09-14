"""One-time server provisioning for litkb. Run as the postgres superuser:

    py -3.12 -m litkb.db.provision

What it does (idempotent; safe to re-run):
  1. roles litkb_owner, litkb_reader, litkb_writer, litkb_promoter, litkb_ingest, litkb_test — LOGIN, no
     superuser/createdb/createrole/replication/bypassrls. A role that has no pgpass line gets
     a fresh random password and the line is appended to the pgpass file. Passwords are never
     printed.
  2. litkb_test is a member of reader/writer/promoter WITH INHERIT FALSE, SET TRUE: the test
     suite can SET ROLE to exercise each role's privileges, but inherits none of them — so it
     does not inherit the writer's CONNECT on litkb (design §4.7, §9).
  3. databases litkb (owner litkb_owner) and litkb_test (owner litkb_test), UTF8, in the
     tablespace litkb_d on D: (decisions.yaml litkb-p0-foundation, "Storage").
  4. CONNECT: revoked from PUBLIC on both; litkb granted to owner/reader/writer/promoter,
     litkb_test granted to litkb_test only. The server therefore refuses litkb_test on litkb.
  5. extensions vector, pg_trgm, fuzzystrmatch in both databases. vector is not a trusted
     extension, so it must be created here, as superuser, not by a migration.

Nothing in postgresql.conf or pg_hba.conf is touched.

pgpass lines: localhost:5433:litkb:<role>:<pw> for owner, reader and writer, and
localhost:5433:*:litkb_test:<pw> for the test role, in the shared pgpass file. The wildcard is
deliberate: a test that points the test role at litkb must reach the server and be refused BY
THE SERVER, not fail client-side for want of a password. (Consequence, design §9: the test
login can also open Postgres's empty system databases, which grant CONNECT to PUBLIC; the
property that counts is that litkb refuses it.)

The promoter's line goes to its OWN passfile, connect.promoter_passfile() (decisions.yaml
litkb-p0-foundation D-3), read only by litkb.promote.connect. A promoter whose line is only in
the shared file (P1 provisioning wrote it there) gets a fresh password and a line in its own
file on the next run; the old shared-file line then holds a dead password and can be deleted
by hand.

The ingest login (litkb_ingest, decisions.yaml litkb-p0-foundation after the second P1 referee)
likewise gets its line in its OWN passfile, connect.ingest_passfile() (default
D:\\edmonds-pipeline\\secrets\\litkb_ingest.pgpass), read only by litkb.ingest.connect. It must
exist before migration 0010 applies, because 0010 grants to it.
"""
import os
import secrets
from pathlib import Path

from . import connect as _c

ROLES = ("litkb_owner", "litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest", "litkb_test")
TEST_ROLE = "litkb_test"
TEST_ROLE_SETS = ("litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest")
TABLESPACE = "litkb_d"
DATABASES = {_c.DB_MAIN: "litkb_owner", _c.DB_TEST: TEST_ROLE}
CONNECT = {
    _c.DB_MAIN: ("litkb_owner", "litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest"),
    _c.DB_TEST: (TEST_ROLE,),
}
EXTENSIONS = ("vector", "pg_trgm", "fuzzystrmatch")


def pgpass_path():
    if os.environ.get("PGPASSFILE"):
        return Path(os.environ["PGPASSFILE"])
    if os.name == "nt":
        return Path(os.environ["APPDATA"]) / "postgresql" / "pgpass.conf"
    return Path.home() / ".pgpass"


def pgpass_path_for(role):
    """The passfile that holds this role's line (D-3: the promoter has its own; after the
    second referee, so does the ingest login)."""
    if role == _c.PROMOTER:
        return Path(_c.promoter_passfile())
    if role == _c.INGEST:
        return Path(_c.ingest_passfile())
    return pgpass_path()


def _pgpass_db(role):
    return "*" if role == TEST_ROLE else _c.DB_MAIN


def _pgpass_has(path, role):
    """True when a line for this host/port/role exists. Reads fields, never prints them."""
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        f = line.split(":")
        if (len(f) >= 5 and f[0] in (_c.HOST, "*") and f[1] in (str(_c.PORT), "*")
                and f[3] == role):
            return True
    return False


def _append_pgpass(path, role, password):
    path.parent.mkdir(parents=True, exist_ok=True)
    lead = ""
    if path.exists() and path.stat().st_size and not path.read_bytes().endswith(b"\n"):
        lead = "\n"
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{lead}{_c.HOST}:{_c.PORT}:{_pgpass_db(role)}:{role}:{password}\n")


def provision():
    from psycopg import sql

    su = _c.connect("postgres", "postgres", autocommit=True)
    try:
        # a failed statement carrying a password must never reach the server log
        su.execute("SET log_min_error_statement = panic")
        su.execute("SET log_statement = 'none'")
        for role in ROLES:
            pp = pgpass_path_for(role)
            exists = su.execute("SELECT 1 FROM pg_roles WHERE rolname = %s",
                                (role,)).fetchone() is not None
            has_line = _pgpass_has(pp, role)
            if has_line and not exists:
                raise SystemExit(
                    f"provision: pgpass already has a line for {role} but the role does not "
                    "exist; remove that stale line by hand, then re-run")
            if not (exists and has_line):
                password = secrets.token_urlsafe(32)
                verb = "ALTER" if exists else "CREATE"
                su.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)))
                _append_pgpass(pp, role, password)
                del password
                print(f"  role {role}: {'password reset' if exists else 'created'}, "
                      "pgpass line appended")
            else:
                print(f"  role {role}: exists, pgpass line present")
            su.execute(sql.SQL(
                "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                "NOBYPASSRLS").format(sql.Identifier(role)))
        for member_of in TEST_ROLE_SETS:
            su.execute(sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                sql.Identifier(member_of), sql.Identifier(TEST_ROLE)))
        for db, owner in DATABASES.items():
            if su.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,)).fetchone():
                print(f"  database {db}: exists")
            else:
                su.execute(sql.SQL(
                    "CREATE DATABASE {} OWNER {} TABLESPACE {} TEMPLATE template0 "
                    "ENCODING 'UTF8'").format(sql.Identifier(db), sql.Identifier(owner),
                                              sql.Identifier(TABLESPACE)))
                print(f"  database {db}: created (owner {owner}, tablespace {TABLESPACE})")
            su.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(db)))
            for role in ROLES:
                if role not in CONNECT[db] and role != owner:
                    su.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                        sql.Identifier(db), sql.Identifier(role)))
            for role in CONNECT[db]:
                su.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(db), sql.Identifier(role)))
        for db in DATABASES:
            dbc = _c.connect(db, "postgres", autocommit=True)
            try:
                for ext in EXTENSIONS:
                    dbc.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(
                        sql.Identifier(ext)))
                got = dbc.execute(
                    "SELECT string_agg(extname || ' ' || extversion, ', ' ORDER BY extname) "
                    "FROM pg_extension WHERE extname = ANY (%s)", (list(EXTENSIONS),)).fetchone()[0]
                print(f"  database {db}: extensions {got}")
            finally:
                dbc.close()
        leak = su.execute("SELECT has_database_privilege(%s, %s, 'CONNECT')",
                          (TEST_ROLE, _c.DB_MAIN)).fetchone()[0]
        if leak:
            raise SystemExit(f"provision: {TEST_ROLE} can CONNECT to {_c.DB_MAIN}; refusing")
        print(f"  {TEST_ROLE} CONNECT on {_c.DB_MAIN}: false (server-confined)")
    finally:
        su.close()


if __name__ == "__main__":
    provision()

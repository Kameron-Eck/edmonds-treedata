"""Connection settings for the local litkb server (design §2 decision 4, decisions.yaml
litkb-p0-foundation: PostgreSQL 18 on port 5433).

Passwords are never handled here: libpq reads them from the pgpass file
(%APPDATA%\\postgresql\\pgpass.conf on Windows), written by litkb.db.provision.
psycopg is imported inside conninfo()/connect(), never at module top (import-weight contract).
"""
import os
import re

HOST = os.environ.get("LITKB_PGHOST", "localhost")
PORT = int(os.environ.get("LITKB_PGPORT", "5433"))

DB_MAIN = "litkb"
# The test database. LITKB_TEST_DB lets a parallel mutation-harness worker point the suite at its own
# copy (litkb_test_w1, litkb_test_w2, ...; provisioned by litkb.db.provision --workers N). The name must
# keep the litkb_test prefix: migrate.reset() and every "test only" refusal key on that prefix, so no
# override can aim the suite at litkb or at anything but a throwaway.
TEST_DB_PREFIX = "litkb_test"
DB_TEST = os.environ.get("LITKB_TEST_DB", TEST_DB_PREFIX)
if not DB_TEST.startswith(TEST_DB_PREFIX) or not re.fullmatch(r"[a-z_][a-z0-9_]*", DB_TEST):
    raise RuntimeError(f"LITKB_TEST_DB must be a plain identifier starting with {TEST_DB_PREFIX!r}, got {DB_TEST!r}")


def is_test_db(name):
    """True for the test database and its harness-worker copies, never for litkb."""
    return isinstance(name, str) and name.startswith(TEST_DB_PREFIX) and name != DB_MAIN

# decisions.yaml litkb-p0-foundation, D-3: the promoter login is used ONLY by the promote tool
# (litkb.promote.connect), which reads its password from a passfile of its own. Agents'
# reader and writer connections go through connect() below and never name that passfile.
PROMOTER = "litkb_promoter"
PROMOTER_PASSFILE_DEFAULT = r"D:\edmonds-pipeline\secrets\litkb_promoter.pgpass"

# decisions.yaml litkb-p0-foundation, after the second P1 referee: extraction runs and
# set_current_run belong to a separate ingest login, used ONLY by the ingest tool
# (litkb.ingest.connect), with a passfile of its own. The writer holds neither right.
INGEST = "litkb_ingest"
INGEST_PASSFILE_DEFAULT = r"D:\edmonds-pipeline\secrets\litkb_ingest.pgpass"

# role and database names connect() accepts: plain lower-case identifiers, so no whitespace,
# quote or '=' can reach libpq as a second keyword (referee 2, E-8)
_NAME = re.compile(r"[a-z_][a-z0-9_]*")


def promoter_passfile():
    """Where the promoter's pgpass line lives: LITKB_PROMOTER_PASSFILE, else the secrets folder
    outside the repository (design §4.7). Written by litkb.db.provision, read only by
    litkb.promote.connect. Not the shared pgpass file the other roles use."""
    return os.environ.get("LITKB_PROMOTER_PASSFILE", PROMOTER_PASSFILE_DEFAULT)


def ingest_passfile():
    """Where the ingest login's pgpass line lives: LITKB_INGEST_PASSFILE, else the secrets folder
    outside the repository. Written by litkb.db.provision, read only by litkb.ingest.connect."""
    return os.environ.get("LITKB_INGEST_PASSFILE", INGEST_PASSFILE_DEFAULT)


# the logins connect() refuses, each with the one function allowed to open it
TOOL_LOGINS = {PROMOTER: "litkb.promote.connect()", INGEST: "litkb.ingest.connect()"}

# third referee F-9: the superuser and the schema owner are strictly stronger than every tool login.
# connect(), the agents' path, refuses both; migrations and provisioning open them through
# connect_admin(), which accepts nothing else. Their passwords stay in the shared pgpass file
# (Kam's accepted risk); like the tool-login refusals, this stops a MISTAKE in a caller of connect(),
# not a process that reads that file itself.
SUPERUSER = "postgres"
OWNER = "litkb_owner"
ADMIN_LOGINS = {SUPERUSER: "litkb.db.provision", OWNER: "litkb.db.migrate"}


class LoginRefused(RuntimeError):
    """connect() refused the requested login before any connection was attempted."""


class PromoterLoginRefused(LoginRefused):
    """connect() was asked for the promoter login outside the promote tool."""


class IngestLoginRefused(LoginRefused):
    """connect() was asked for the ingest login outside the ingest tool."""


class AdminLoginRefused(LoginRefused):
    """connect() was asked for the superuser or the owner login, outside migrations and provisioning."""


def conninfo(dbname, user, passfile=None):
    """A libpq connection string with every value quoted by psycopg (make_conninfo), so a value
    can never add a keyword of its own."""
    from psycopg.conninfo import make_conninfo

    kw = dict(host=HOST, port=PORT, dbname=dbname, user=user, connect_timeout=5)
    if passfile is not None:
        kw["passfile"] = str(passfile)
    return make_conninfo(**kw)


def connect(dbname, user, *, autocommit=False):
    """Reader, writer and test logins. Refuses the promoter (D-3) and the ingest login
    (second-referee decision), each of which has its own passfile and its own tool, and the
    superuser and owner logins (third referee F-9), which only connect_admin() opens.

    What this refusal is: it stops a MISTAKE in a caller of this function. It is convention,
    not enforcement, against code that calls _open() or psycopg directly with one of those
    passfiles; see litkb.promote and Reports/LITKB_P1_REFEREE2_2026-09-13.md, "D-3"."""
    def refused(login):
        if login in ADMIN_LOGINS:
            return AdminLoginRefused(f"{login} connects only through connect_admin() ({ADMIN_LOGINS[login]}); "
                                     "agents use litkb_reader or litkb_writer")
        cls = PromoterLoginRefused if login == PROMOTER else IngestLoginRefused
        return cls(f"{login} connects only through {TOOL_LOGINS[login]}; agents use litkb_reader or litkb_writer")

    # BEGIN guard: login names are plain identifiers
    for what, value in (("user", user), ("dbname", dbname)):
        if not isinstance(value, str) or not _NAME.fullmatch(value):
            raise LoginRefused(f"litkb connect: {what} must be a plain lower-case identifier, got {value!r}")
    # END guard: login names are plain identifiers
    # BEGIN guard: promoter login only through the promote tool
    if user == PROMOTER:        # before any driver import
        raise refused(PROMOTER)
    # END guard: promoter login only through the promote tool
    # BEGIN guard: ingest login only through the ingest tool
    if user == INGEST:          # before any driver import
        raise refused(INGEST)
    # END guard: ingest login only through the ingest tool
    # BEGIN guard: admin logins only through connect_admin
    if user in ADMIN_LOGINS:    # before any driver import
        raise refused(user)
    # END guard: admin logins only through connect_admin
    from psycopg.conninfo import conninfo_to_dict

    # second lock: the user exactly as libpq will parse the connection string
    parsed = str(conninfo_to_dict(conninfo(dbname, user)).get("user", "")).strip()
    if parsed in TOOL_LOGINS or parsed in ADMIN_LOGINS:
        raise refused(parsed)
    return _open(conninfo(dbname, user), autocommit)


def connect_admin(dbname, user, *, autocommit=True):
    """The one connection path for the superuser (provisioning) and the owner (migrations).
    Accepts only those two logins, so it can never become a second door for an agent role."""
    # BEGIN guard: connect_admin opens only the admin logins
    if user not in ADMIN_LOGINS:
        raise LoginRefused(f"connect_admin opens only {sorted(ADMIN_LOGINS)}, got {user!r}")
    # END guard: connect_admin opens only the admin logins
    if not isinstance(dbname, str) or not _NAME.fullmatch(dbname):
        raise LoginRefused(f"litkb connect_admin: dbname must be a plain lower-case identifier, got {dbname!r}")
    return _open(conninfo(dbname, user), autocommit)


def _open(info, autocommit):
    import psycopg

    return psycopg.connect(info, autocommit=autocommit)

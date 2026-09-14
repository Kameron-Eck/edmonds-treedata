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
DB_TEST = "litkb_test"

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


class LoginRefused(RuntimeError):
    """connect() refused the requested login before any connection was attempted."""


class PromoterLoginRefused(LoginRefused):
    """connect() was asked for the promoter login outside the promote tool."""


class IngestLoginRefused(LoginRefused):
    """connect() was asked for the ingest login outside the ingest tool."""


def conninfo(dbname, user, passfile=None):
    """A libpq connection string with every value quoted by psycopg (make_conninfo), so a value
    can never add a keyword of its own."""
    from psycopg.conninfo import make_conninfo

    kw = dict(host=HOST, port=PORT, dbname=dbname, user=user, connect_timeout=5)
    if passfile is not None:
        kw["passfile"] = str(passfile)
    return make_conninfo(**kw)


def connect(dbname, user, *, autocommit=False):
    """Reader, writer, owner, test and superuser logins. Refuses the promoter (D-3) and the
    ingest login (second-referee decision): each has its own passfile and its own tool.

    What this refusal is: it stops a MISTAKE in a caller of this function. It is convention,
    not enforcement, against code that calls _open() or psycopg directly with one of those
    passfiles; see litkb.promote and Reports/LITKB_P1_REFEREE2_2026-09-13.md, "D-3"."""
    def refused(login):
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
    from psycopg.conninfo import conninfo_to_dict

    # second lock: the user exactly as libpq will parse the connection string
    parsed = str(conninfo_to_dict(conninfo(dbname, user)).get("user", "")).strip()
    if parsed in TOOL_LOGINS:
        raise refused(parsed)
    return _open(conninfo(dbname, user), autocommit)


def _open(info, autocommit):
    import psycopg

    return psycopg.connect(info, autocommit=autocommit)

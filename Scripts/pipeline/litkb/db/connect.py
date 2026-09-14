"""Connection settings for the local litkb server (design §2 decision 4, decisions.yaml
litkb-p0-foundation: PostgreSQL 18 on port 5433).

Passwords are never handled here: libpq reads them from the pgpass file
(%APPDATA%\\postgresql\\pgpass.conf on Windows), written by litkb.db.provision.
psycopg is imported inside connect(), never at module top (import-weight contract).
"""
import os

HOST = os.environ.get("LITKB_PGHOST", "localhost")
PORT = int(os.environ.get("LITKB_PGPORT", "5433"))

DB_MAIN = "litkb"
DB_TEST = "litkb_test"

# decisions.yaml litkb-p0-foundation, D-3: the promoter login is used ONLY by the promote tool
# (litkb.promote.connect), which reads its password from a passfile of its own. Agents'
# reader and writer connections go through connect() below and never name that passfile.
PROMOTER = "litkb_promoter"
PROMOTER_PASSFILE_DEFAULT = r"D:\edmonds-pipeline\secrets\litkb_promoter.pgpass"


def promoter_passfile():
    """Where the promoter's pgpass line lives: LITKB_PROMOTER_PASSFILE, else the secrets folder
    outside the repository (design §4.7). Written by litkb.db.provision, read only by
    litkb.promote.connect. Not the shared pgpass file the other roles use."""
    return os.environ.get("LITKB_PROMOTER_PASSFILE", PROMOTER_PASSFILE_DEFAULT)


class PromoterLoginRefused(RuntimeError):
    """connect() was asked for the promoter login outside the promote tool."""


def conninfo(dbname, user, passfile=None):
    s = f"host={HOST} port={PORT} dbname={dbname} user={user} connect_timeout=5"
    if passfile is not None:
        s += " passfile='" + str(passfile).replace("\\", "\\\\").replace("'", "\\'") + "'"
    return s


def connect(dbname, user, *, autocommit=False):
    # BEGIN guard: promoter login only through the promote tool
    if user == PROMOTER:
        raise PromoterLoginRefused(
            f"{PROMOTER} connects only through litkb.promote.connect(); agents use "
            "litkb_reader or litkb_writer")
    # END guard: promoter login only through the promote tool
    return _open(conninfo(dbname, user), autocommit)


def _open(info, autocommit):
    import psycopg

    return psycopg.connect(info, autocommit=autocommit)

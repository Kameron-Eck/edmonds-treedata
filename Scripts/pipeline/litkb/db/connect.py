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


def conninfo(dbname, user):
    return f"host={HOST} port={PORT} dbname={dbname} user={user} connect_timeout=5"


def connect(dbname, user, *, autocommit=False):
    import psycopg

    return psycopg.connect(conninfo(dbname, user), autocommit=autocommit)

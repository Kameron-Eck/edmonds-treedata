"""Ingest login (decisions.yaml litkb-p0-foundation, after the second P1 referee).

    conn = connect()          the litkb_ingest login: INSERT on extraction tables, set_current_run

litkb_ingest owns inserting extraction runs (and the derived text tables loaded with them:
pages, blocks, tables, figures, equations, references, citation mentions, chunks, embeddings,
file checks) and moving a file's current run with set_current_run (migration 0010). The writer
holds none of those rights, so an agent's writer connection can neither un-promote a file's
evidence by installing a run of its own nor forge a block whose text matches a quote. The ingest
login cannot write gaps, uses, evidence or workstreams.

Credential: its password lives in its own passfile (litkb.db.connect.ingest_passfile(), outside
the repository, default D:\\edmonds-pipeline\\secrets\\litkb_ingest.pgpass), which only connect()
below names. litkb.db.connect.connect() refuses the ingest login. As with the promoter, the
server cannot tell this module from any other process that reads that file: the credential is
protected by where it is kept.
"""


def connect(dbname=None, *, autocommit=True):
    """The one connection path for the ingest login."""
    from litkb.db import connect as c

    return c._open(c.conninfo(dbname or c.DB_MAIN, c.INGEST, passfile=c.ingest_passfile()),
                   autocommit)

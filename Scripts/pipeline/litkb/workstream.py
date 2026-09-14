"""Workstream tokens (decisions.yaml litkb-p0-foundation, after the second P1 referee).

    ws_id = open_workstream(conn, slug, branch, purpose, directory=worktree_root)
    ws_id, token = load(worktree_root)

litkb.open_workstream() returns a secret token ONCE; the database keeps only its sha256, in a
table no agent role can read (migration 0010). Every writer function that names a workstream
(write_fact, write_proposal, add_evidence, add_candidate, record_acquisition_attempt,
add_use_embedding, abandon_workstream) takes that token and is refused (42501) inside the
SECURITY DEFINER function when it does not hash to the workstream's.

The session keeps the token in the untracked file `.litkb-workstream` in its worktree root
(git-ignored, any depth). This stops a session from writing into another session's workstream
BY MISTAKE; it does not stop a process that reads another worktree's file (same Windows user).

Rule for every client (this module, the future CLI and MCP tools; third referee F-8): the token is
sent ONLY as a bound query parameter (`conn.execute("... %s ...", (..., token, ...))`), never
formatted into the SQL text and never as a psql literal. Another login of the same role can read a
session's `pg_stat_activity.query`, which shows an inlined literal but not a bound parameter.

This module never prints or logs the token.
"""
import json
import os
from pathlib import Path

TOKEN_FILE = ".litkb-workstream"


class WorkstreamFileExists(RuntimeError):
    """A worktree already holds a workstream token file; it is never overwritten."""


def open_workstream(conn, slug, git_branch, purpose, *, directory, brief_path=None):
    """Open a workstream, write {workstream_id, token} to <directory>/.litkb-workstream and
    return the id.

    Atomic with respect to the file (third referee F-7): the file is claimed first with O_EXCL, so
    of two sessions opening in one directory exactly one gets past this point; the workstream is
    then opened inside a transaction, the token written and fsynced, and only then committed. Any
    failure rolls the database back and removes the claimed file, so no open workstream is ever
    left whose token is in no file."""
    from psycopg.pq import TransactionStatus

    if conn.info.transaction_status != TransactionStatus.IDLE:
        # a transaction the caller owns could still roll back after the file is written
        raise RuntimeError("open_workstream needs a connection that is not inside a transaction")
    path = Path(directory) / TOKEN_FILE
    # BEGIN guard: the token file is claimed before the workstream opens
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise WorkstreamFileExists(f"{path} already exists; finish or abandon that workstream first") from None
    # END guard: the token file is claimed before the workstream opens
    fh = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
    try:
        with conn.transaction():
            ws_id, token = conn.execute(
                "SELECT workstream_id, token FROM litkb.open_workstream(%s, %s, %s, %s, %s)",
                (slug, git_branch, str(Path(directory).resolve()), purpose, brief_path)).fetchone()
            json.dump({"workstream_id": str(ws_id), "token": token}, fh)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
            fh.close()
    except BaseException:
        fh.close()
        path.unlink(missing_ok=True)
        raise
    return ws_id


def load(directory):
    """(workstream_id, token) from <directory>/.litkb-workstream."""
    data = json.loads((Path(directory) / TOKEN_FILE).read_text(encoding="utf-8"))
    return data["workstream_id"], data["token"]

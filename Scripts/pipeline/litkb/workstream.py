"""Workstream tokens (decisions.yaml litkb-p0-foundation, after the second P1 referee).

    ws_id = open_workstream(conn, slug, branch, purpose, directory=worktree_root)
    ws_id, token = load(worktree_root)

litkb.open_workstream() returns a secret token ONCE; the database keeps only its sha256, in a
table no agent role can read (migration 0010). Every writer function that names a workstream
(write_fact, write_proposal, add_evidence, abandon_workstream) takes that token and is refused
(42501) inside the SECURITY DEFINER function when it does not hash to the workstream's.

The session keeps the token in the untracked file `.litkb-workstream` in its worktree root
(git-ignored, any depth). This stops a session from writing into another session's workstream
BY MISTAKE; it does not stop a process that reads another worktree's file (same Windows user).

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
    return the id. Refuses before opening anything when the file already exists."""
    path = Path(directory) / TOKEN_FILE
    if path.exists():
        raise WorkstreamFileExists(f"{path} already exists; finish or abandon that workstream first")
    ws_id, token = conn.execute(
        "SELECT workstream_id, token FROM litkb.open_workstream(%s, %s, %s, %s, %s)",
        (slug, git_branch, str(Path(directory).resolve()), purpose, brief_path)).fetchone()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"workstream_id": str(ws_id), "token": token}, fh)
        fh.write("\n")
    return ws_id


def load(directory):
    """(workstream_id, token) from <directory>/.litkb-workstream."""
    data = json.loads((Path(directory) / TOKEN_FILE).read_text(encoding="utf-8"))
    return data["workstream_id"], data["token"]

"""Promotion, git side (design §5; decisions.yaml litkb-p0-foundation §15.7 and "After the P1
referee", D-2 and D-3).

    conn = connect()                                                     the promoter login
    pid = prepare(conn, workstream_id, branch_head_sha, report_path)     on the work branch
    commit(conn, pid, merge_sha, repo=..., fetch_remote="github")        only after Kam merges
    held = held_chains(conn, merged_ws)                                  what a commit held back
    rebase(conn, merged_ws, fresh_ws, onto, agent, session)              carry them forward

The database cannot run git, so THIS TOOL refuses a merge that is not on main: the
reachability rule runs BEFORE litkb.promote_commit() is called — the merge commit must be an
ancestor of (freshly fetched) main, and the commit recorded at prepare must be an ancestor of
the merge commit. The database function then refuses on its own grounds: a version set that
changed since prepare, a chain whose base moved (compare-and-set), and every dependent of a
held chain.

Credential (D-3): only litkb_promoter may EXECUTE promote_prepare / promote_commit /
promote_abandon / promote_rebase (migrations 0006, 0008; reader and writer are refused, tested).
Its password lives in its own passfile (litkb.db.connect.promoter_passfile(), outside the
repository), which only connect() below names. litkb.db.connect.connect() refuses the promoter
login, so an agent's reader or writer connection never carries it. What the database cannot
tell apart is a process that reads that passfile itself: the credential is protected by where
it is kept, not by the server.
"""
import subprocess


class PromotionRefused(RuntimeError):
    """promote commit refused before anything in the database moved."""


def connect(dbname=None, *, autocommit=True):
    """The one connection path for the promoter login.

    Against a THROWAWAY database (`litkb_test`, and the harness workers `litkb_test_wN`) there is no
    promoter line in any passfile — provisioning writes the promoter's password for `litkb` only. So
    the test path is the one qc/test_litkb_p1.py already uses: log in as `litkb_test`, which is a
    member of litkb_promoter WITH INHERIT FALSE, and SET ROLE. That is a weaker credential reaching
    the same rights, which is what a throwaway database is for; `is_test_db()` keys on the
    `litkb_test` prefix and is never true for `litkb`, so this branch cannot be aimed at the real
    database by an environment variable."""
    from litkb.db import connect as c

    if c.is_test_db(dbname):
        conn = c.connect(dbname, "litkb_test", autocommit=autocommit)
        conn.execute("SET ROLE litkb_promoter")
        return conn
    return c._open(c.conninfo(dbname or c.DB_MAIN, c.PROMOTER, passfile=c.promoter_passfile()),
                   autocommit)


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _rev(repo, rev):
    r = _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    if r.returncode != 0 or not r.stdout.strip():
        raise PromotionRefused(f"{rev!r} does not name a commit in {repo}")
    return r.stdout.strip()


def _is_ancestor(repo, ancestor, descendant):
    r = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    if r.returncode not in (0, 1):
        raise PromotionRefused(f"git merge-base failed in {repo}: {r.stderr.strip()}")
    return r.returncode == 0


def fetch_main(repo, remote):
    r = _git(repo, "fetch", "--quiet", remote, "main")
    if r.returncode != 0:
        raise PromotionRefused(f"could not fetch main from {remote}: {r.stderr.strip()}")
    return f"{remote}/main"


def verify_merge(repo, merge_commit, prepared_commit, *, main_ref):
    """Return the full merge sha, or raise PromotionRefused."""
    merge = _rev(repo, merge_commit)
    main = _rev(repo, main_ref)
    prepared = _rev(repo, prepared_commit)
    # BEGIN guard: merge commit reachable from main
    if not _is_ancestor(repo, merge, main):
        raise PromotionRefused(
            f"merge commit {merge} is not reachable from {main_ref} ({main}): main has not "
            "merged this work, so nothing is promoted")
    # END guard: merge commit reachable from main
    if not _is_ancestor(repo, prepared, merge):
        raise PromotionRefused(
            f"the commit recorded at prepare ({prepared}) is not an ancestor of {merge}: "
            "the merge does not contain the branch state whose report was reviewed")
    return merge


def prepare(conn, workstream_id, branch_head, report_path=None):
    return conn.execute("SELECT litkb.promote_prepare(%s, %s, %s)",
                        (workstream_id, branch_head, report_path)).fetchone()[0]


def commit(conn, promotion_id, merge_commit, *, repo, fetch_remote):
    """fetch_remote: the remote to fetch main from first (design §5, "a freshly fetched
    main"). None only for an offline scratch repository whose local main is the truth."""
    row = conn.execute("SELECT branch_head_commit FROM litkb.promotions WHERE id = %s",
                       (promotion_id,)).fetchone()
    if row is None:
        raise PromotionRefused(f"no promotion {promotion_id}")
    main_ref = fetch_main(repo, fetch_remote) if fetch_remote else "main"
    merge = verify_merge(repo, merge_commit, row[0], main_ref=main_ref)
    return conn.execute("SELECT litkb.promote_commit(%s, %s)",
                        (promotion_id, merge)).fetchone()[0]


_IDENT = {"work": "works", "identifier": "identifiers", "file": "files", "gap": "gaps", "use": "uses"}


def held_chains(conn, workstream_id):
    """{"<entity>:<id>": main's current version id} for every chain a workstream still heads.
    For a merged workstream that is exactly what its commit held back. The mapping is the
    `onto` a rebase is reviewed against; if main moves before rebase() runs, the rebase is
    refused (40001) and must be reviewed again."""
    out = {}
    for entity, entity_id in conn.execute(
            "SELECT entity, entity_id FROM litkb.ws_heads WHERE workstream_id = %s "
            "ORDER BY entity, entity_id", (workstream_id,)).fetchall():
        cur = conn.execute(f"SELECT current_version_id FROM litkb.{_IDENT[entity]} WHERE id = %s",
                           (entity_id,)).fetchone()[0]
        out[f"{entity}:{entity_id}"] = None if cur is None else str(cur)
    return out


def rebase(conn, source_workstream, target_workstream, onto, agent, session):
    """D-2: copy a merged workstream's held chains into an open one, onto the main versions
    named in `onto` (see held_chains). The new versions then go through prepare, Kam's
    merge and commit like any other."""
    from psycopg.types.json import Jsonb

    return conn.execute("SELECT litkb.promote_rebase(%s, %s, %s, %s, %s)",
                        (source_workstream, target_workstream, Jsonb(onto), agent,
                         session)).fetchone()[0]

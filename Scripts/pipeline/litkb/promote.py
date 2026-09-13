"""Promotion, git side (design §5; decisions.yaml litkb-p0-foundation §15.7).

    pid = prepare(conn, workstream_id, branch_head_sha, report_path)     on the work branch
    commit(conn, pid, merge_sha, repo=..., fetch_remote="github")        only after Kam merges

The database cannot run git, so the reachability rule lives here and runs BEFORE
litkb.promote_commit() is called: the merge commit must be an ancestor of (freshly
fetched) main, and the commit recorded at prepare must be an ancestor of the merge commit.
The database function then refuses on its own grounds: a version set that changed since
prepare, a chain whose base moved (compare-and-set), and every dependent of a held chain.

Only litkb_promoter may EXECUTE promote_prepare / promote_commit (migration 0006).
"""
import subprocess


class PromotionRefused(RuntimeError):
    """promote commit refused before anything in the database moved."""


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

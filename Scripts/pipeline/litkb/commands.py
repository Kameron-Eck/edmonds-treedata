"""The litkb command line (design §9). Run from a worktree, with PYTHONPATH=Scripts/pipeline until the
editable install is re-run from a tree that contains litkb:

    py -3.12 -m litkb ws open <slug> [--purpose P] [--branch B] [--brief PATH]
    py -3.12 -m litkb ws status
    py -3.12 -m litkb discover "<query>" [--source crossref] [--max 5]
    py -3.12 -m litkb admit --doi D [--title T --authors A --year Y | --tracker-id N] [--key K] [--file PDF]
    py -3.12 -m litkb admit --manual --title T --authors A --year Y --file PDF --source-note "..."
    py -3.12 -m litkb approve <admission-id>
    py -3.12 -m litkb acquire (--key K | --doi D) [--routes open_access,annas,scihub]
                              [--max-archive-downloads N] [--quota-margin M] [--retry-dead] [--from-file PDF]

Every write names the workstream in <worktree>/.litkb-workstream and presents its token, bound as a query
parameter. The token is never printed: `ws open` prints the workstream id only.

Session labels: --agent / --session, or LITKB_AGENT / LITKB_SESSION. A manual admission is approved only from
another session (the database refuses the admitter's own).

Database: --db (default LITKB_DB, else litkb), login litkb_writer through litkb.db.connect.connect().
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
TRACKER_CSV = SCRIPTS.parent / "Reports" / "literature_tracker.csv"


def _git(*args, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 else ""


def _worktree(args):
    return Path(args.dir or _git("rev-parse", "--show-toplevel") or os.getcwd()).resolve()


def _labels(args):
    from litkb.textnorm import norm_label
    agent = norm_label(args.agent or os.environ.get("LITKB_AGENT") or "")
    session = norm_label(args.session or os.environ.get("LITKB_SESSION") or "")
    if not agent or not session:
        raise SystemExit("litkb: an agent and a session label are required (--agent/--session or "
                         "LITKB_AGENT/LITKB_SESSION)")
    return agent, session


def _default_connect(db):
    from litkb.db import connect as c

    return c.connect(db, "litkb_writer", autocommit=True)


def _ws(args):
    from litkb import workstream

    try:
        return workstream.load(_worktree(args))
    except FileNotFoundError:
        raise SystemExit(f"litkb: no {workstream.TOKEN_FILE} in {_worktree(args)}; run `litkb ws open <slug>` first") from None


def _print(obj):
    print(json.dumps(obj, indent=1, default=str, ensure_ascii=False))


def _tracker_row(tracker_id, path=TRACKER_CSV):
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["ID"].strip() == str(tracker_id):
                return r
    raise SystemExit(f"litkb: tracker row {tracker_id} not found in {path}")


def _summary(res):
    keep = {k: res.get(k) for k in ("outcome", "admission_id", "work_id", "file_id", "refused_at", "constraint",
                                    "matches") if res.get(k) is not None}
    checks = res.get("checks") or {}
    for c in ("check1_study_exists", "check3_binding", "check2_duplicate"):
        if c in checks:
            keep[c] = checks[c]
    return keep


def cmd_ws(args, conn):
    from litkb import workstream

    if args.ws_cmd == "open":
        branch = args.branch or _git("rev-parse", "--abbrev-ref", "HEAD", cwd=_worktree(args)) or "unknown"
        ws_id = workstream.open_workstream(conn, args.slug, branch, args.purpose, directory=_worktree(args),
                                           brief_path=args.brief)
        print(f"litkb: workstream {ws_id} open ({args.slug}, branch {branch}); token written to "
              f"{_worktree(args) / workstream.TOKEN_FILE} (never printed)")
        return 0
    ws_id, _token = _ws(args)
    row = conn.execute("SELECT slug, git_branch, state, opened_at FROM litkb.workstreams WHERE id = %s",
                       (ws_id,)).fetchone()
    if not row:
        raise SystemExit(f"litkb: workstream {ws_id} is not in database {args.db}")
    counts = {t: conn.execute(f"SELECT state, count(*) FROM litkb.{t} WHERE workstream_id = %s GROUP BY 1 ORDER BY 1",
                              (ws_id,)).fetchall() for t in ("candidates", "admissions")}
    attempts = conn.execute("SELECT route, status, count(*) FROM litkb.acquisition_attempts WHERE workstream_id = %s "
                            "GROUP BY 1, 2 ORDER BY 1, 2", (ws_id,)).fetchall()
    _print({"workstream_id": ws_id, "slug": row[0], "branch": row[1], "state": row[2], "opened_at": row[3],
            "candidates": dict(counts["candidates"]), "admissions": dict(counts["admissions"]),
            "attempts": [list(a) for a in attempts]})
    return 0


def cmd_discover(args, conn):
    from litkb.admit.front import add_candidate

    ws_id, token = _ws(args)
    if args.source != "crossref":
        raise SystemExit("litkb discover: only --source crossref is wired in P2")
    from paper_search_mcp.academic_platforms.crossref import CrossRefSearcher

    papers = CrossRefSearcher().search(args.query, max_results=args.max)
    out = []
    for p in papers:
        d = p.to_dict()
        year = p.published_date.year if getattr(p, "published_date", None) else None
        cid = add_candidate(conn, ws_id, token, source="paper-search", source_detail="crossref", query=args.query,
                            raw=json.loads(json.dumps(d, default=str)), title=p.title, authors=list(p.authors or []),
                            year=year, ids={"doi": p.doi} if p.doi else {})
        out.append({"candidate_id": cid, "title": p.title, "year": year, "doi": p.doi})
    _print(out)
    return 0


def cmd_admit(args, conn):
    from litkb.admit import front

    ws_id, token = _ws(args)
    agent, session = _labels(args)
    if args.manual:
        if not (args.title and args.authors and args.year and args.file and args.source_note):
            raise SystemExit("litkb admit --manual needs --title, --authors, --year, --file and --source-note")
        res = front.admit_manual(conn, ws_id, token, title=args.title, authors=args.authors, year=int(args.year),
                                file_path=args.file, source_note=args.source_note, work_type=args.type or "report",
                                key=args.key, agent=agent, session=session)
        _print(_summary(res))
        return 0 if res["outcome"] == "proposed" else 1
    claimed, doi, detail = {}, args.doi, None
    if args.tracker_id:
        r = _tracker_row(args.tracker_id)
        claimed = {"title": r["Title"], "authors": r["Author(s)"], "year": r["Year"]}
        detail = f"tracker ID {args.tracker_id}"
        if not doi and "doi.org/" in r["DOI/URL"]:
            doi = r["DOI/URL"].split("doi.org/", 1)[1].strip()
    for k in ("title", "authors", "year"):
        if getattr(args, k):
            claimed[k] = getattr(args, k)
    if not (doi or args.arxiv):
        raise SystemExit("litkb admit needs --doi or --arxiv (or --tracker-id with a DOI), or --manual")
    res = front.admit_registry(conn, ws_id, token, doi=doi, arxiv=args.arxiv, claimed=claimed or None, key=args.key,
                              file_path=args.file, agent=agent, session=session, source_detail=detail,
                              extra_identifiers=([{"scheme": "tracker", "value": str(args.tracker_id),
                                                   "verified_by": None, "evidence": {"source": "Reports/literature_tracker.csv"}}]
                                                 if args.tracker_id else ()))
    _print(_summary(res))
    return 0 if res["outcome"] == "admitted" else 1


def cmd_approve(args, conn):
    from litkb.admit import front

    ws_id, token = _ws(args)
    agent, session = _labels(args)
    _print(front.approve(conn, ws_id, token, args.admission_id, agent, session))
    return 0


def cmd_acquire(args, conn):
    from litkb.acquire import run

    ws_id, token = _ws(args)
    agent, session = _labels(args)
    work = run.work_record(conn, key=args.key, doi=args.doi)
    if not work:
        raise SystemExit("litkb acquire: no admitted work with that key or DOI; admit it first")
    budget = run.Budget(max_archive_downloads=args.max_archive_downloads, quota_margin=args.quota_margin)
    out = run.acquire(conn, ws_id, token, work, routes=tuple(r.strip() for r in args.routes.split(",") if r.strip()),
                      agent=agent, session=session, budget=budget, retry_dead=args.retry_dead,
                      from_file=args.from_file)
    out["archive_downloads_used"] = budget.used
    out["downloads_left"] = budget.downloads_left
    out["account_counter"] = budget.counter
    if budget.stopped:
        out["archive_stopped"] = budget.stopped
    _print({k: v for k, v in out.items() if k != "detail"} | {"key": work["key"]})
    return 0 if out["outcome"] in ("ok", "already-held") else 1


def cmd_migrate(args, conn):
    """P3: the legacy tracker and manifest loaded THROUGH admission (design §13)."""
    from litkb.migrate_legacy import run as mrun

    ws_id, token = _ws(args)
    agent, session = _labels(args)
    ctx = mrun.Loader(conn, ws_id, token, agent=agent, session=session, root=args.root)
    only = [s.strip() for s in (args.only or "").split(",") if s.strip()] or None
    summary = (mrun.load_tracker(ctx, limit=args.limit, only_ids=only) if args.what == "tracker"
               else mrun.load_manifest(ctx, limit=args.limit))
    if args.log:
        Path(args.log).write_text(json.dumps(ctx.log, indent=1, default=str), encoding="utf-8")
    # the labels are printed because they are what the load RECORDS as its admitter, and the approval rule
    # compares them (a manual admission may not be approved from the admitting session). They are the
    # normalised ones, never the raw flags: an invisible character in --session must not make one session
    # look like two. Labels are client-supplied identifiers, not secrets.
    _print(summary | {"agent": ctx.agent, "session": ctx.session,
                      "registry_requests": getattr(ctx.client, "requests", None),
                      "registry_cache_hits": getattr(ctx.client, "hits", None),
                      "log": args.log or "(not written; pass --log)"})
    return 0


def cmd_promote(args, conn):
    """Promotion, the git side (design §5). `prepare` offers this workstream's proposed versions to
    main; `commit` records that Kam merged them.

    The connection `main()` opened is the WRITER's and is deliberately unused here: promote_prepare
    and promote_commit may be executed only by litkb_promoter (design §4.7, D-3), whose password
    lives in a passfile of its own. This command opens that login itself, through
    litkb.promote.connect(), which is the one path to it — and it is a CLI command, not an MCP tool,
    so the credential is never held by a long-lived server (§9)."""
    from litkb import promote

    ws_id, _token = _ws(args)
    pconn = promote.connect(args.db)
    try:
        if args.promote_cmd == "prepare":
            head = _git("rev-parse", "HEAD", cwd=_worktree(args)) or None
            if not head:
                raise SystemExit(f"litkb promote prepare: {_worktree(args)} is not a git worktree; the "
                                 "branch head commit is what the promotion is recorded against")
            try:
                pid = promote.prepare(pconn, ws_id, head, args.report)
            except Exception as e:                       # the database's own refusals are RESULTS here
                _print({"workstream_id": str(ws_id), "outcome": "refused",
                        "refused_by": "database", "error": f"{type(e).__name__}: {e}"})
                return 1
            row = pconn.execute(
                "SELECT state, prepared_at, report_path FROM litkb.promotions WHERE id = %s",
                (pid,)).fetchone()
            chains = pconn.execute(
                "SELECT entity, count(*) FROM litkb.ws_heads WHERE workstream_id = %s GROUP BY 1 ORDER BY 1",
                (ws_id,)).fetchall()
            _print({"workstream_id": str(ws_id), "outcome": "prepared", "promotion_id": str(pid),
                    "branch_head": head, "state": row[0] if row else None,
                    "prepared_at": row[1] if row else None, "report_path": row[2] if row else None,
                    "heads": dict(chains),
                    "next": "Kam reviews the report inside the merge; `promote commit` runs only after "
                            "the merge commit is reachable from main"})
            return 0
        # commit: the reachability rule runs in the TOOL before the database is asked (design §5).
        # --no-fetch is for an offline scratch repository whose local main is the truth; against the
        # real repository main is always freshly fetched.
        res = promote.commit(pconn, args.promotion_id, args.merge_commit,
                             repo=args.repo or _worktree(args),
                             fetch_remote=None if args.no_fetch else args.remote)
        _print({"promotion_id": args.promotion_id, "outcome": "committed", "result": res})
        return 0
    finally:
        pconn.close()


def cmd_export(args, conn):
    """Regenerate the tracker / manifest twins FROM the database (design §10)."""
    from litkb import export as ex

    ws_id = args.workstream
    if not ws_id:
        try:
            ws_id, _token = _ws(args)
        except SystemExit:
            raise SystemExit("litkb export: pass --workstream <id> or run in a worktree with a workstream") from None
    # NEVER the default Reports/ directory: `Reports/literature_tracker.csv` is what the P3 gate reads as
    # "today", and an export written over it would leave the gate comparing the export with itself. Swapping
    # the live files for the exports is Kam's call at promotion.
    out = Path(args.out) if args.out else (SCRIPTS.parent / "Reports" / "litkb_export")
    written = []
    if args.what in ("tracker", "all"):
        rows = ex.tracker_rows(conn, ws_id)
        written.append(ex.write_csv(out / "literature_tracker.csv", ex.TRACKER_EXPORT_COLUMNS, rows))
        phases = _phase_rows()
        x = ex.write_xlsx(out / "Literature_Tracker.xlsx",
                          {"Literature Tracker": (ex.TRACKER_EXPORT_COLUMNS, rows),
                           "Search Phase Reference": (list(phases[0].keys()) if phases else [], phases)})
        if x:
            written.append(x)
    if args.what in ("manifest", "all"):
        rows = ex.manifest_rows(conn, ws_id)
        written.append(ex.write_csv(out / "manifest.csv", ex.MANIFEST_EXPORT_COLUMNS, rows))
    if args.diff:
        d = ex.discrepancy_rows(conn, ws_id)
        written.append(ex.write_csv(out / "litkb_discrepancies.csv",
                                    ["source", "source_row", "field", "claimed_value", "registry_value",
                                     "ratio", "work_key"], d))
    _print({"workstream": ws_id, "written": [str(p) for p in written]})
    return 0


def _phase_rows():
    from litkb.migrate_legacy import sources

    try:
        return sources.phase_rows()
    except FileNotFoundError:
        return []


def build_parser():
    ap = argparse.ArgumentParser(prog="litkb", description="the literature knowledge base")
    ap.add_argument("--db", default=os.environ.get("LITKB_DB", "litkb"))
    ap.add_argument("--dir", help="worktree root holding .litkb-workstream (default: git top level)")
    ap.add_argument("--agent")
    ap.add_argument("--session")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ws = sub.add_parser("ws")
    wsub = ws.add_subparsers(dest="ws_cmd", required=True)
    o = wsub.add_parser("open")
    o.add_argument("slug")
    o.add_argument("--purpose", default="literature workstream")
    o.add_argument("--branch")
    o.add_argument("--brief")
    wsub.add_parser("status")

    d = sub.add_parser("discover")
    d.add_argument("query")
    d.add_argument("--source", default="crossref")
    d.add_argument("--max", type=int, default=5)

    a = sub.add_parser("admit")
    a.add_argument("--doi")
    a.add_argument("--arxiv")
    a.add_argument("--tracker-id", type=int)
    a.add_argument("--title")
    a.add_argument("--authors")
    a.add_argument("--year")
    a.add_argument("--key")
    a.add_argument("--type")
    a.add_argument("--file")
    a.add_argument("--manual", action="store_true")
    a.add_argument("--source-note")

    p = sub.add_parser("approve")
    p.add_argument("admission_id")

    q = sub.add_parser("acquire")
    q.add_argument("--key")
    q.add_argument("--doi")
    q.add_argument("--routes", default="open_access,annas,scihub")
    q.add_argument("--max-archive-downloads", type=int, default=5)
    q.add_argument("--quota-margin", type=int, default=50,
                   help="no archive download URL is requested once the account counter (GET /account/) shows "
                        "used >= limit - margin, or cannot be read (default 50; run.Budget)")
    q.add_argument("--retry-dead", action="store_true")
    q.add_argument("--from-file")

    m = sub.add_parser("migrate", help="P3: load the legacy tracker / manifest through admission")
    m.add_argument("what", choices=["tracker", "manifest"])
    m.add_argument("--limit", type=int)
    m.add_argument("--only", help="comma-separated tracker IDs")
    m.add_argument("--root", help="literature root (default LITKB_LITERATURE_ROOT)")
    m.add_argument("--log", help="write the per-row JSON log here")

    pr = sub.add_parser("promote", help="offer this workstream to main (prepare), or record Kam's merge (commit)")
    prsub = pr.add_subparsers(dest="promote_cmd", required=True)
    pp = prsub.add_parser("prepare")
    pp.add_argument("--report", help="path the promotion report is written to (on the WORK branch)")
    pc = prsub.add_parser("commit")
    pc.add_argument("--promotion-id", dest="promotion_id", required=True)
    pc.add_argument("--merge-commit", dest="merge_commit", required=True)
    pc.add_argument("--repo", help="the git repository to check reachability in (default: the worktree)")
    pc.add_argument("--remote", default="github", help="the remote main is fetched from before the check")
    pc.add_argument("--no-fetch", action="store_true",
                    help="trust the repository's LOCAL main — only for an offline scratch repository")

    e = sub.add_parser("export", help="regenerate the tracker / manifest twins from the database")
    e.add_argument("what", choices=["tracker", "manifest", "all"])
    e.add_argument("--workstream", help="export this workstream's view (default: the worktree's)")
    e.add_argument("--out", help="output directory (default: Reports/litkb_export/ — never over the "
                                           "files the P3 gate reads as 'today')")
    e.add_argument("--diff", action="store_true", help="also write the discrepancy table")
    return ap


class _NoConn:
    """The connection `promote` is handed: it has none. Anything that tried to query through it
    would fail loudly here rather than quietly opening a second credential."""

    def execute(self, *a, **kw):
        raise RuntimeError("litkb promote acts as the promoter, through litkb.promote.connect()")

    def close(self):
        pass


def main(argv=None, connect=None):
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    # `promote` is the one command that does NOT act as the writer: promote_prepare and
    # promote_commit may be executed only by litkb_promoter (design §4.7), and cmd_promote opens
    # that login itself. Opening a writer connection here as well would be a second credential the
    # command never uses — and against a throwaway database, where only the test login has a
    # password, it is a connection that cannot even be made.
    conn = _NoConn() if args.cmd == "promote" and connect is None else (connect or _default_connect)(args.db)
    try:
        return {"ws": cmd_ws, "discover": cmd_discover, "admit": cmd_admit, "approve": cmd_approve,
                "acquire": cmd_acquire, "migrate": cmd_migrate, "export": cmd_export,
                "promote": cmd_promote}[args.cmd](args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

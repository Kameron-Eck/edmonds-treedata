"""The litkb command line (design §9). Run from a worktree, with PYTHONPATH=Scripts/pipeline until the
editable install is re-run from a tree that contains litkb:

    py -3.12 -m litkb ws open <slug> [--purpose P] [--branch B] [--brief PATH]
    py -3.12 -m litkb ws status
    py -3.12 -m litkb admit --doi D [--title T --authors A --year Y | --tracker-id N] [--key K] [--file PDF]
    py -3.12 -m litkb admit --manual --title T --authors A --year Y --file PDF --source-note "..."
    py -3.12 -m litkb admit --web --title T --authors A --year Y --url U --retrieved DATE
                            --snapshot PAGE.txt --source-note "..."
    py -3.12 -m litkb approve <admission-id>
    py -3.12 -m litkb refuse <admission-id> --reason R [--dry-run]          (a SECOND session; migration 0034)
    py -3.12 -m litkb withdraw <version-id> [--entity file] --reason R [--dry-run]   (the proposer's own)
    py -3.12 -m litkb approve-files [<version-id> ...] [--pending] [--reason R] [--dry-run]
    py -3.12 -m litkb refuse-files [<version-id> ...] [--pending] --reason R [--dry-run]
                          (lone proposed file versions on works in main: an `acquire --from-file` bind
                          is one; batched, all or nothing, a SECOND session)
    py -3.12 -m litkb use add (--key K | --doi D) --statement S --kind K [--feeds "tok;tok"]
                              [--quote Q --page N --stance supports] [--rationale R]
                              [--hunt-request ID]
    py -3.12 -m litkb use list
    py -3.12 -m litkb hunt-request add --ref REF --ref-scheme doi --expected-claim C
                                       --why-relevant W [--abstract-passage P] [--claimed-title T]
                                       [--claimed-authors A] [--claimed-year Y] [--gap SLUG]
    py -3.12 -m litkb hunt-request list [--state open|unconfirmed|confirmed|contradicted]
    py -3.12 -m litkb inventory --new [--root R] [--census C] [--json]
    py -3.12 -m litkb acquire (--key K | --doi D) [--routes open_access,annas,scihub]
                              [--max-archive-downloads N] [--quota-margin M] [--retry-dead] [--from-file PDF]
    py -3.12 -m litkb hunt <doi-or-url> [--title T] [--author A] [--year Y] [--no-extract] [--no-spend]
                          [--hunt-request ID]
    py -3.12 -m litkb brief [workstream-id-or-slug] [--out PATH]
    py -3.12 -m litkb review-check <review.md>          (exit 1 on any K1/K2 failure)
    py -3.12 -m litkb review-context <review.md> --out <context.md>   (exit 1 on a block it cannot show)
    py -3.12 -m litkb reap [--min-age-hours 72] [--apply] [--out census.json] [--json]
                          (the staging census; --dry-run is the default and moves nothing)
    py -3.12 -m litkb runs retire [--apply --reason R] [--json] [--out PATH]
                          (superseded extraction runs: MARKED retired, never deleted; dry run default)
    py -3.12 -m litkb [--db D] queue sweep [--workstream W] [--root R] [--no-ocr]
    py -3.12 -m litkb [--db D] queue work [--max-jobs N] [--lease S] [--device auto|cuda|cpu] [--no-ocr]
    py -3.12 -m litkb [--db D] queue status
                          (the extraction queue, migration 0029; runs as litkb_ingest)

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

# The ref-scheme vocabulary, imported rather than restated: the parser's help text and the
# `hunt-request add` refusal both read it, and a hand-typed copy here is exactly the stale list
# that would refuse `title` at the CLI after migration 0027 widened the database's CHECK
# (CLAUDE.md §3.3). The module imports nothing itself, so this costs nothing at CLI start-up.
from litkb.hunt_request import REF_SCHEMES  # noqa: E402


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
    # title_discrepancy: a claim that named the work but not its subtitle is admitted AND recorded as
    # a disagreement (migration 0020). If the command did not print it, the one person who could act
    # on the review row would be the one person who never hears about it.
    keep = {k: res.get(k) for k in ("outcome", "admission_id", "work_id", "file_id", "refused_at", "constraint",
                                    "matches", "title_discrepancy") if res.get(k) is not None}
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


# `cmd_discover` was RETIRED here on 2026-09-20 (LITKB_WORKPLAN.md S1, "cmd_discover retired or
# folded, decided by whether the scout uses it"). It ran a Crossref title search through
# `paper_search_mcp.academic_platforms.crossref.CrossRefSearcher` and wrote `candidates` rows.
#
# WHY IT GOES. S1 gives discovery to the lit-scout, and the scout reaches the paper-search MCP
# SERVER directly (`.mcp.json`) — it never shells out to this CLI. What the command left behind
# was a second, unused route into the same package, with its own `--source crossref` half-wiring
# ("only --source crossref is wired in P2") and its own candidate-writing path that nothing
# exercised. A route nobody calls is a route nobody notices breaking.
#
# CHECKED BEFORE REMOVING, 2026-09-20: `grep -rn "cmd_discover\|litkb discover"` over Scripts/
# found the definition, the parser, the dispatcher entry and this module's own usage line, and
# nothing else — no test, no instrument, no skill, no agent file. The only OTHER mention of the
# command is in LITKB_WORKPLAN.md's dated 2026-09-20 survey appendix, which is explicitly "not
# maintained", so it is left as the record it is. `add_candidate` (admit/front.py) keeps its other
# callers; `paper_search_mcp` remains a dependency of `acquire/open_access.py` (Unpaywall).


def cmd_admit(args, conn):
    from litkb.admit import front

    ws_id, token = _ws(args)
    agent, session = _labels(args)
    if args.web:
        # §8.4: the convention promises that a source with no DOI is recordable as a manual proposal
        # with its URL and retrieval date; check 3 refused every one of them for lacking a PDF text
        # layer. The evidence is now the admitter's saved TEXT of the page, bound by the same binder.
        if not (args.title and args.authors and args.year and args.url and args.retrieved
                and args.snapshot and args.source_note):
            raise SystemExit("litkb admit --web needs --title, --authors, --year, --url, --retrieved, "
                             "--snapshot <page text as .txt> and --source-note")
        res = front.admit_web(conn, ws_id, token, title=args.title, authors=args.authors, year=int(args.year),
                              url=args.url, retrieved=args.retrieved, snapshot_path=args.snapshot,
                              source_note=args.source_note, work_type=args.type or "report", key=args.key,
                              agent=agent, session=session)
        _print(_summary(res))
        return 0 if res["outcome"] == "proposed" else 1
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
                                                 if args.tracker_id else ()),
                              # S4.5 decision D25: the operator's --file is a proposal (migration 0035)
                              operator_file=bool(args.file))
    _print(_summary(res) | front.operator_file_note(conn, res))
    return 0 if res["outcome"] == "admitted" else 1


def cmd_approve(args, conn):
    from litkb.admit import front

    ws_id, token = _ws(args)
    agent, session = _labels(args)
    _print(front.approve(conn, ws_id, token, args.admission_id, agent, session))
    return 0


# ── adjudication (migration 0034; LITKB_WORKPLAN.md S4.5 item 1) ──────────────────────────────
# Second-session verbs, CLI-only like `approve` (the MCP server has none of them). --dry-run reads
# and prints what the verb WOULD do, and the reasons the database would refuse it; it writes nothing.

def cmd_refuse(args, conn):
    """`litkb refuse <admission-id> --reason R [--dry-run]`: a SECOND session declines a proposed manual
    admission (front.refuse). Exit 1 when the dry run finds a reason the database would refuse it."""
    from litkb.admit import front

    agent, session = _labels(args)
    if args.dry_run:
        plan = front.refuse_plan(conn, args.admission_id, session)
        _print(plan | {"dry_run": True})
        return 0 if plan["would"] == "declined" else 1
    ws_id, token = _ws(args)
    _print(front.refuse(conn, ws_id, token, args.admission_id, args.reason, agent, session))
    return 0


def cmd_withdraw(args, conn):
    """`litkb withdraw <version-id> [--entity file] --reason R [--dry-run]`: the proposing workstream retracts
    its own proposal (front.withdraw)."""
    from litkb.admit import front

    agent, session = _labels(args)
    ws_id, token = _ws(args)
    if args.dry_run:
        plan = front.withdraw_plan(conn, ws_id, args.entity, args.version_id)
        _print(plan | {"dry_run": True})
        return 0 if plan["would"] == "withdrawn" else 1
    _print(front.withdraw(conn, ws_id, token, args.entity, args.version_id, args.reason, agent, session))
    return 0


def cmd_decide_files(args, conn):
    """`litkb approve-files` / `litkb refuse-files`: a SECOND session decides lone proposed file versions on
    works already in main, batched and all-or-nothing (front.decide_files). `--pending` names every one not
    proposed by this session; --dry-run lists them with the reasons any would be refused."""
    from litkb.admit import front

    agent, session = _labels(args)
    verb = "approve" if args.cmd == "approve-files" else "refuse"
    ids = list(args.version_ids or [])
    if args.pending:
        ids += [p["version_id"] for p in front.pending_file_proposals(conn)
                if p["version_id"] not in ids]
    if not ids:
        _print({"verb": verb, "decided": [], "note": "no proposed file version named or pending"})
        return 0
    plan = front.decide_plan(conn, ids, session)
    if args.dry_run:
        _print({"dry_run": True, "verb": verb, "versions": plan})
        return 0 if all(p["would"] == "decide" for p in plan) else 1
    # (the batch is all or nothing: one version the plan refuses — this session's own proposal, a closed
    # workstream's — would refuse every other one with it)
    # BEGIN guard: approve-files --pending never sends a version the plan already refuses
    if args.pending:
        ids = [p["version_id"] for p in plan if p["would"] == "decide"]
        if not ids:
            _print({"verb": verb, "decided": [], "skipped": plan})
            return 1
    # END guard: approve-files --pending never sends a version the plan already refuses
    ws_id, token = _ws(args)
    _print(front.decide_files(conn, ws_id, token, verb, ids, args.reason, agent, session))
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
    if args.from_file and out["outcome"] == "ok":
        # the operator-bind gate (migration 0034, `litkb-from-file-version-state`): the file is bound as a
        # PROPOSAL, so main cannot see it until a second session approves it — say so, and name the version
        from litkb.admit import front
        mine = [p for p in front.pending_file_proposals(conn)
                if p["work_id"] == str(work["work_id"]) and p["workstream_id"] == str(ws_id)]
        # (+ the acceptance test's verdict the proposal carries for the approver: S4.5 decision D17, integrator-w2)
        out["proposed"] = [{k: p[k] for k in ("version_id", "file_id", "rel_path", "source_route",
                                              "acceptance_verdict", "acceptance_sub_status")} for p in mine]
        out["next"] = ("a SECOND session approves it: `litkb approve-files <version_id>` (or refuses it: "
                       "`litkb refuse-files <version_id> --reason R`); until then main does not hold this file")
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
            # BEGIN guard: prepare WRITES the promotion report
            # P8 referee F-5: prepare recorded a report path and wrote no file, while the skill and
            # the P8 report both said it wrote one onto the work branch. `promotions.report_path`
            # can only record what the caller named AT prepare — the promotion id does not exist
            # until prepare returns — so with no --report the file is named by the promotion id
            # under `_derived/promotions/` and the payload says where it went. Making the database
            # record that default would need a migration; it is flagged in the P8 report rather
            # than invented here.
            detail = promote.chain_rows(pconn, ws_id)
            # A chain held by the dependency fixpoint carries no problems of its own; its reason is
            # in `promotions.conflicts` (promote.hold_reasons). Read once and used by BOTH renderings
            # below, so the report Kam reviews and the JSON a session reads cannot disagree.
            reasons = promote.hold_reasons(pconn, pid)
            report_at = Path(args.report) if args.report else Path("_derived") / "promotions" / f"{pid}.md"
            if not report_at.is_absolute():
                report_at = _worktree(args) / report_at
            written = promote.write_report(report_at, promote.render_report(
                ws_id, pid, head, detail, prepared_at=row[1] if row else None, reasons=reasons))
            # END guard: prepare WRITES the promotion report
            _print({"workstream_id": str(ws_id), "outcome": "prepared", "promotion_id": str(pid),
                    "branch_head": head, "state": row[0] if row else None,
                    "prepared_at": row[1] if row else None, "report_path": row[2] if row else None,
                    "report_written": written,
                    "prepared": [f"{c['entity']}:{c['entity_id']}" for c in detail
                                 if "prepared" in (c["states"] or [])],
                    "held": [{"chain": f"{c['entity']}:{c['entity_id']}",
                              "why": promote.chain_why(c, reasons)}
                             for c in detail if "prepared" not in (c["states"] or [])],
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


def cmd_inventory(args, conn):
    """Stage 0 reporting: what the corpus holds that the FROZEN census does not pin.

    The census tests used to walk the literature root, so the corpus growing failed them — 224 files
    pinned against 246 on disk, two refereed tests red for a reason that had nothing to do with the
    code they test (Reports/LITKB_P4_MERGE_2026-09-15.md, "The ladder"). They now measure the frozen
    list in `phase4/qc/litkb_inventory_census.sha256`, and this is where the rest of the corpus is
    reported instead of silently breaking a pin.

    DB-FREE: `conn` is opened by main() before dispatch and is deliberately unused here.
    """
    from litkb.extract import inventory as inv

    if not args.new:
        raise SystemExit("litkb inventory: pass --new (the only mode today)")
    root = args.root or os.environ.get("LITKB_LITERATURE_ROOT", str(inv.DEFAULT_ROOT))
    if args.json:
        _print({"root": root, "census": str(inv.census_path(args.census)),
                "rows": inv.new_files(root, args.census)})
        return 0
    return inv.report_new(root, args.census)


def cmd_use(args, conn):
    """Step 4 of the hunt protocol: record what a work supplies, and anchor its quote.

    The convention names five steps; `litkb --help` had commands for three of them, so the first
    session that followed it wrote its 15 uses through psycopg by copying the P3 loader
    (`Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8.1). Everything below goes through the same
    token-checked functions that loader used — `write_proposal` and `add_evidence` — and adds the two
    things a hand-written call could not do for itself: the feeds tokens are checked against the
    database's own validator before anything is written, and a quote is located in an extracted block
    so `quote_verified` is the database's answer rather than a claim in free text. The mechanism, and
    why a missing block is a refusal rather than a fallback, is in litkb/use.py.

    The workstream is not optional: _ws() refuses outside a worktree that holds one, because a use is
    a proposal and a proposal has to belong to something that can be prepared.
    """
    from litkb import use as _use

    ws_id, token = _ws(args)
    if args.use_cmd == "list":
        rows = conn.execute(
            "SELECT w.key, v.statement, v.kind, v.status, v.feeds, v.state, "
            "       (SELECT count(*) FROM litkb.use_evidence e WHERE e.use_version_id = v.version_id), "
            "       (SELECT count(*) FROM litkb.use_evidence e WHERE e.use_version_id = v.version_id "
            "          AND e.quote_verified) "
            "  FROM litkb.use_versions v JOIN litkb.uses u ON u.id = v.use_id "
            "  JOIN litkb.works w ON w.id = u.work_id WHERE v.workstream_id = %s ORDER BY v.created_at",
            (ws_id,)).fetchall()
        _print([{"work": r[0], "statement": r[1], "kind": r[2], "status": r[3], "feeds": r[4], "state": r[5],
                 "evidence": r[6], "verified": r[7]} for r in rows])
        return 0
    agent, session = _labels(args)      # a read needs no labels; a write is signed
    work = _use.work_by(conn, key=args.key, doi=args.doi)
    if not work:
        raise SystemExit("litkb use add: no admitted work with that key or DOI; admit it first "
                         "(never cite a work that is not admitted)")
    feeds = [t.strip().rstrip(".") for t in (args.feeds or "").split(";") if t.strip()]
    # BEGIN guard: feeds tokens are checked before the use is written
    bad = _use.feeds_refused(conn, feeds)
    if bad:
        raise SystemExit(f"litkb use add: {len(bad)} feeds token(s) the database will not accept: {bad}\n"
                         "the seven forms are in Scripts/docs/LITERATURE_CONVENTION.md "
                         "('Feeds token vocabulary'); prepare would hold the chain on these")
    # END guard: feeds tokens are checked before the use is written
    anchor = None
    if args.quote:
        # BEGIN guard: a quote is anchored in an extracted block or the use is refused
        hits = _use.locate_quote(conn, work["work_id"], args.quote, page=args.page)
        if not hits:
            raise SystemExit(
                f"litkb use add: that quote is in no extracted block of {work['key']}"
                + (f" on page {args.page}" if args.page else "")
                + ".\nA use's quote is verified against the file's current extraction run, so it is that run's\n"
                  "characters that must match. Either the text has not been extracted yet (run the extraction\n"
                  "pipeline for this file), the page is wrong, or the quote was retyped rather than copied.\n"
                  "It is NOT written into `rationale` as free text: the database cannot check that, which is\n"
                  "the gap this command exists to close (LITKB_LINKAGE_REVIEW_2026-09-15.md §8.3).")
        anchor = hits[0]
        # END guard: a quote is anchored in an extracted block or the use is refused
    use_id, version_id = _use.write_use(
        conn, ws_id, token, work_id=work["work_id"], statement=args.statement, kind=args.kind,
        status=args.status, feeds=feeds, confidence=args.confidence, rationale=args.rationale,
        agent=agent, session=session, hunt_request_id=args.hunt_request)
    out = {"use_id": use_id, "version_id": version_id, "work": work["key"], "kind": args.kind, "feeds": feeds}
    if anchor:
        ev = _use.attach_quote(conn, ws_id, token, version_id, anchor, args.quote, stance=args.stance)
        out |= {"evidence_id": ev["evidence_id"], "quote_verified": ev["quote_verified"],
                "anchored": {k: anchor[k] for k in ("page", "char_start", "char_end")},
                "other_anchors": len(hits) - 1}
    else:
        out["evidence"] = ("none: this use carries no quote the database can verify "
                           "(pass --quote to anchor one)")
    _print(out)
    return 0


def cmd_hunt_request(args, conn):
    """The review agent's drop-off (migration 0023, litkb/hunt_request.py): a claim, why it
    matters, and the abstract passage it came from, recorded BEFORE the paper is even hunted so a
    later verified use can be checked against the expectation that motivated the hunt.

    `resolution_state` is never typed here or anywhere else — `add` always reports `open`, because
    the database computes it fresh from `litkb.hunt_request_status` on every read, never from a
    column an agent could set."""
    from litkb import hunt_request as _hr

    ws_id, token = _ws(args)
    if args.hunt_request_cmd == "list":
        rows = _hr.list_for_workstream(conn, ws_id, state=args.state, limit=args.limit)
        _print(rows)
        return 0
    agent, session = _labels(args)
    # BEGIN guard: the CLI drop-off's ref_scheme is in the vocabulary before the write is attempted
    # The table's CHECK is what ENFORCES this; the check here is so the caller reads the
    # vocabulary rather than a raw PL/pgSQL constraint-violation sentence, and reads it from the
    # ONE constant the database's CHECK is held equal to (migration 0027).
    if args.ref_scheme not in REF_SCHEMES:
        raise SystemExit(f"litkb hunt-request add: --ref-scheme {args.ref_scheme!r} is not one of "
                         f"{', '.join(REF_SCHEMES)}")
    # END guard: the CLI drop-off's ref_scheme is in the vocabulary before the write is attempted
    gap_id = None
    if args.gap:
        row = conn.execute("SELECT id::text FROM litkb.gaps WHERE slug = %s", (args.gap,)).fetchone()
        if not row:
            raise SystemExit(f"litkb hunt-request add: no gap {args.gap!r}. Open one first "
                             "(litkb use add --gap-question opens one on demand; this command does not).")
        gap_id = row[0]
    hr_id = _hr.record(conn, ws_id, token, ref=args.ref, ref_scheme=args.ref_scheme,
                       expected_claim=args.expected_claim, why_relevant=args.why_relevant,
                       abstract_passage=args.abstract_passage, claimed_title=args.claimed_title,
                       claimed_authors=args.claimed_authors, claimed_year=args.claimed_year,
                       gap_id=gap_id, agent=agent, session=session)
    _print({"hunt_request_id": str(hr_id), "ref": args.ref, "resolution_state": "open",
           "what_next": "litkb hunt <ref> --hunt-request <id> links the resolved work; "
                        "litkb use add --hunt-request <id> is what can confirm or contradict it."})
    return 0


def cmd_brief(args, conn):
    """The per-workstream BRIEF export (Task B, delta 2026-09-18; litkb/brief.py): every
    hunt_request this workstream holds, marked EXPECTED, and every promotable quote it can see,
    marked VERIFIED -- read-only, no new stored state. Accepts a workstream id or slug; with
    neither given, the worktree's own (like `export`).

    Written to `_derived/briefs/<slug>.md` by default -- untracked (.gitignore's `/_derived/*`
    rule), same reasoning as `promote prepare`'s report: this is a generated view for the session
    reading it, not a checked-in artifact.
    """
    from litkb import brief as _brief

    if args.workstream:
        row = conn.execute(
            "SELECT id, slug, state, purpose FROM litkb.workstreams WHERE id::text = %s OR slug = %s",
            (args.workstream, args.workstream)).fetchone()
        if not row:
            raise SystemExit(f"litkb brief: no workstream {args.workstream!r} (id or slug)")
    else:
        ws_id, _token = _ws(args)
        row = conn.execute("SELECT id, slug, state, purpose FROM litkb.workstreams WHERE id = %s",
                           (ws_id,)).fetchone()
        if not row:
            raise SystemExit(f"litkb brief: workstream {ws_id} is not in database {args.db}")
    ws_row = {"id": row[0], "slug": row[1], "state": row[2], "purpose": row[3]}
    expected, verified = _brief.build(conn, ws_row["id"])
    out = Path(args.out) if args.out else Path("_derived") / "briefs" / f"{ws_row['slug']}.md"
    if not out.is_absolute():
        out = _worktree(args) / out
    written = _brief.write(out, ws_row, expected, verified)
    _print({"workstream_id": str(ws_row["id"]), "slug": ws_row["slug"], "n_expected": len(expected),
           "n_verified": len(verified), "written": str(written)})
    return 0


def cmd_review_check(args, conn):
    """The K1/K2 gate on a WRITTEN review (stage 8; litkb/review_check.py, grammar in
    Scripts/docs/LITKB_REVIEW_GRAMMAR.md). Deterministic: no model runs, and the workstream
    graded against is the one the REVIEW declares in its own header, never one named on the
    command line -- a review graded against a workstream it was not written from would pass K2
    by holding no expectations at all.

    `--workstream <id|slug|current>` therefore does NOT choose what is graded: it ASSERTS that the
    workstream the caller means is the one the document declares, and `check` refuses a mismatch
    by name. `current` is this worktree's own, the same source `brief` and `export` default to --
    which is what an unattended loop has to hand, since it knows its workstream and not the
    review's header.

    One JSON object per finding, then a summary; returns 1 when any finding is a `fail`, so
    `py -3.12 -m litkb review-check <review.md>` exits non-zero and can gate an unattended loop.
    """
    from litkb import review_check as _rc

    ws_ref = getattr(args, "workstream", None)
    if ws_ref == "current":
        ws_id, _token = _ws(args)
        ws_ref = str(ws_id)
    findings = _rc.check(conn, args.review, k2_workstream=ws_ref)
    for f in findings:
        _print({"review": str(args.review), **f})
    bad = _rc.fails(findings)
    _print({"review": str(args.review), "findings": len(findings), "fails": len(bad),
            "notices": len(findings) - len(bad), "verdict": "FAIL" if bad else "PASS"})
    return 1 if bad else 0


def cmd_review_context(args, conn):
    """The FULL BLOCK behind every citation of a review, as markdown (litkb/review_context.py).

    It opens its OWN reader login rather than using the writer `main()` would hand it: this
    command only reads blocks, and the review stage that consumes its output is the one part of
    the pipeline that hands a file to a model outside this machine. A read-only credential is the
    honest one for it, and it is also what lets the command run against a worker database, where
    the shared pgpass holds no `litkb_writer` line (LITKB_REVIEW_GRAMMAR.md §8 records the same
    limit for `review-check`).

    Exit 1 when any cited block is not visible to the workstream. The context file still gets
    written, with `BLOCK NOT VISIBLE` in that block's section -- a reviewer must be able to see
    the hole, and a caller must not be able to miss it.
    """
    from litkb.db import connect as _c
    from litkb import review_context as _rx

    # the role is a flag with hunt.py's env default, not a literal: worker databases admit only
    # litkb_test, and a literal here made this command live-only (found 2026-09-20 building the
    # Codex stage; the fix is a flag, NOT a pgpass or GRANT that would put production roles on
    # test databases the provisioner deliberately keeps them off)
    conn = _c.connect(args.db, args.role)
    try:
        out = args.out or str(Path(args.review).with_suffix(".context.md"))
        report = _rx.write(conn, args.review, out)
    finally:
        conn.close()
    _print({"review": str(args.review), **report,
            "missing": [str(m) for m in report["missing"]]})
    return 1 if report["missing"] else 0


def cmd_reap(args, conn):
    """The staging census, and — with --apply — the quarantine move for each orphan
    (litkb/ops/reaper.py).

    It opens its OWN READER login, like `review-context`: the census reads `litkb.files` and
    `litkb.file_versions`, and a reader is also what lets the command run against a worker database,
    where the shared pgpass holds no `litkb_writer` line. With --apply ONLY it also opens the INGEST
    connection (`litkb.quarantine.ingest_connect`), because each move is now followed by a
    `litkb.quarantine_payloads` row (migration 0030) and `record_quarantine_system` is granted to
    litkb_ingest alone. The dry run opens no second login and writes no row.

    --dry-run is the DEFAULT and moves nothing: the census is the product, and quarantining is a
    second, explicit call. Exit 1 when any file could not be read or moved — a census with a hole
    in it must not read as a clean one.
    """
    from litkb.db import connect as _c
    from litkb.ops import reaper as _r

    from litkb import quarantine as _q

    conn = _c.connect(args.db, args.role)
    recorder = _q.ingest_connect(args.db) if args.apply else None
    try:
        out = _r.reap(conn, root=args.root or os.environ.get("LITKB_LITERATURE_ROOT") or None,
                      min_age_hours=args.min_age_hours, apply=bool(args.apply), recorder=recorder)
    finally:
        conn.close()
        if recorder is not None:
            recorder.close()
    doc = _r.as_json(out)
    if args.json:
        _print(doc)
    else:
        for line in _r.table(out):
            print(line)
        print(" ".join(f"{k}={v}" for k, v in out["counters"].items()))
        print(f"mode={'apply' if out['applied'] else 'dry-run'} run_id={out['run_id']} "
              f"root={out['root']}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, default=str, ensure_ascii=False)
    return 1 if out["errors"] else 0


def cmd_hunt(args, conn):
    """The whole hunt protocol in one call (litkb/hunt.py).

    The connection `main()` opened is deliberately unused, like `promote`'s: hunt needs a READER
    for the ladder, a WRITER for the admission and the INGEST login for the run, and it opens each
    where it is used. Handing it a fourth would be a credential held for the length of a
    conversion that takes minutes.

    Exit status is the refusal, not the state: a hunt that ends at `held` because a DOI has no PDF
    did everything it could and exits 0, with the next move in `refusals`.

    SPEND RULE (Kam, 2026-09-16 night; decisions.yaml litkb-p0-foundation): a hunt that reaches
    `held` proceeds to acquisition (open access, then the archive, then Sci-Hub) BY DEFAULT.
    `--no-spend` is the explicit exception."""
    from litkb import hunt as _hunt

    # BEGIN guard: the CLI's --no-spend threads through as spend=False; the default spends
    spend = not args.no_spend
    # END guard: the CLI's --no-spend threads through as spend=False; the default spends
    res = _hunt.hunt(args.ref, db=args.db, worktree=_worktree(args), agent=args.agent,
                     session=args.session, title=args.title, author=args.author, year=args.year,
                     key=args.key, source_note=args.source_note, retrieved=args.retrieved,
                     extract=not args.no_extract, device=args.device,
                     docling_python=args.docling_python, derived=args.derived, spend=spend,
                     hunt_request_id=args.hunt_request, ref_scheme=args.ref_scheme)
    _print(res)
    return 0 if res.get("ok") else 1


def cmd_quarantine(args, conn):
    """`litkb quarantine backfill [--apply]` (S4, migration 0030): every payload already under
    `_quarantine/` gets a `litkb.quarantine_payloads` row (origin `legacy-backfill`).

    The census reads on the READER login (`--role`, like `reap`) and writes NOTHING: the DRY RUN is
    the default and is what a session runs against live. `--apply` additionally opens the INGEST
    connection (`record_quarantine_system` is granted to litkb_ingest alone) and writes each row
    idempotently — a recorded path is skipped. Exit 1 when a row could not be written, or when a
    payload's label is outside the closed vocabulary (it is listed, never defaulted)."""
    from litkb import quarantine as _q
    from litkb.db import connect as _c

    root = args.root or os.environ.get("LITKB_LITERATURE_ROOT") or None
    conn = _c.connect(args.db, args.role)
    recorder = _q.ingest_connect(args.db) if args.apply else None
    try:
        out = _q.backfill(conn, root=root, apply=bool(args.apply), recorder=recorder)
    finally:
        conn.close()
        if recorder is not None:
            recorder.close()
    if args.json:
        _print(out)
    else:
        for r in out["rows"]:
            print(f"{r['action']:<16} {r['reason'] or '(unmapped: ' + str(r['label']) + ')':<16} "
                  f"{r['rel_path']}  attempt={r['attempt_id'] or '-'} file={r['file_id'] or '-'}")
        print(" ".join(f"{k}={v}" for k, v in out["counters"].items()))
        print("by_reason " + " ".join(f"{k}={v}" for k, v in out["by_reason"].items()))
        print(f"mode={'apply' if out['applied'] else 'dry-run'} root={out['root']} "
              f"table_present={out['table_present']}")
    if args.out:
        with open(args.out, "x", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, default=str, ensure_ascii=False)
    return 1 if (out["errors"] or out["counters"]["unmapped"]) else 0


def cmd_readability(args, conn):
    """`litkb readability` (S4): classify every acquired file, staging payload and main work into the
    closed readability classes (litkb/readability.py) and write `Reports/LITKB_READABILITY_<date>.csv`.

    Reads on the READER login (`--role`) and writes the database NOTHING unless `--record`, which opens
    the INGEST connection and records a quarantine row for each bound file the classifier refuses
    (`bad-file`, `zero-content`, `probe-error`) against its current path — the bytes are never moved.
    The CSV is create-only: an existing file is never overwritten (pass `--csv` another path).
    Exit 0 always on a completed classification: `unclassified_acquired_files` is a count the
    acceptance grades, not an error of this command."""
    from litkb import quarantine as _q
    from litkb import readability as _r
    from litkb.db import connect as _c

    conn = _c.connect(args.db, args.role)
    recorder = _q.ingest_connect(args.db) if args.record else None
    try:
        ws = list(args.workstream or [])
        if args.all_workstreams:
            ws = [r[0] for r in conn.execute("SELECT id::text FROM litkb.workstreams ORDER BY opened_at, id").fetchall()]
        res = _r.classify(conn, ws, root=args.root or os.environ.get("LITKB_LITERATURE_ROOT") or None,
                          record=recorder,
                          session=args.session or os.environ.get("LITKB_SESSION") or "litkb-readability")
    finally:
        conn.close()
        if recorder is not None:
            recorder.close()
    path = None
    if not args.no_csv:
        path = _r.write_csv(res, args.csv or _r.default_csv_path())
    print(" ".join(f"{k}={v}" for k, v in res["counters"].items()))
    print(f"csv={path or '-'} workstreams={len(res['workstreams'])} cap={res['cap']} "
          f"quarantine_table={res['quarantine_table']} recorded={len(res['recorded'])} "
          f"cleared={len(res['cleared'])}")
    return 0


def cmd_queue(args, conn):
    """The extraction queue (litkb/extract/queue.py; design §12.3-12.5, LITKB_WORKPLAN.md "### S4").

    It opens its OWN ingest login(s): `sweep`, `work` and `status` run as litkb_ingest through the
    queue's SECURITY DEFINER functions (migration 0029), and `work` opens a second connection for
    the lease heartbeat. Against `litkb` that is `litkb.ingest.connect`; against a worker database
    it is the test owner login + SET ROLE litkb_ingest (`references_ingest.connect`'s rule), which is
    what lets the kill test run this very command as a subprocess.

    Exit status: `work` exits 1 when any job failed or lost its lease; `sweep` and `status` exit 0.
    """
    from litkb.extract import queue as Q

    if args.queue_cmd == "work":
        report = Q.work(lambda: Q.connect(args.db), args.root, worker=args.worker,
                        max_jobs=args.max_jobs, lease=args.lease or Q.LEASE_SECONDS,
                        ocr=Q.ocr_enabled(args.no_ocr), device=args.device,
                        python=args.docling_python, derived=args.derived,
                        extractor=Q.seam_extractor(args.db), files=args.files)
        _print(report)
        bad = sum(n for k, n in report["outcomes"].items()
                  if k.startswith("failed") or k == "lease-lost")
        return 1 if bad else 0
    k = Q.connect(args.db)
    try:
        if args.queue_cmd == "sweep":
            _print(Q.sweep(k, args.root, workstreams=args.workstream or (),
                           ocr=Q.ocr_enabled(args.no_ocr), files=args.files,
                           redo=args.redo))
        else:
            _print(Q.status(k))
    finally:
        k.close()
    return 0


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

    rf = sub.add_parser("refuse", help="a SECOND session declines a proposed manual admission (migration 0034)")
    rf.add_argument("admission_id")
    rf.add_argument("--reason", required=True, help="why: the decision log records it")
    rf.add_argument("--dry-run", action="store_true", help="print what would happen; write nothing")
    wd = sub.add_parser("withdraw", help="the proposing workstream retracts its own proposed version")
    wd.add_argument("version_id")
    wd.add_argument("--entity", default="file", choices=("work", "identifier", "file", "gap", "use"))
    wd.add_argument("--reason", required=True, help="why: the decision log records it")
    wd.add_argument("--dry-run", action="store_true", help="print what would happen; write nothing")
    for name, what in (("approve-files", "approve"), ("refuse-files", "refuse")):
        df = sub.add_parser(name, help=f"a SECOND session {what}s lone proposed file versions on works in main, "
                                       "batched, all or nothing (migration 0034)")
        df.add_argument("version_ids", nargs="*")
        df.add_argument("--pending", action="store_true",
                        help="every lone proposed file version not proposed by this session")
        df.add_argument("--reason", required=(what == "refuse"), help="why: the decision log records it")
        df.add_argument("--dry-run", action="store_true", help="list what would be decided; write nothing")

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

    # ── added 2026-09-15, closing the friction the first real use of the KB exposed ──────────
    # New subparsers and dispatch entries go at the END of each: `work/20260915-access-layer` is
    # adding a `promote` subparser to this same function, and two additions that both land at the
    # bottom merge mechanically, while two that interleave do not.
    a.add_argument("--web", action="store_true",
                   help="a source with no DOI (documentation, a blog post): admitted as a manual "
                        "proposal from its URL, its retrieval date and a saved text snapshot")
    a.add_argument("--url", help="--web: the page's URL")
    a.add_argument("--retrieved", help="--web: the date the snapshot was taken (a page changes under a citation)")
    a.add_argument("--snapshot", help="--web: the page's text, saved as .txt; binding runs against it")

    u = sub.add_parser("use", help="step 4 of the hunt protocol: record what a work supplies")
    usub = u.add_subparsers(dest="use_cmd", required=True)
    ua = usub.add_parser("add")
    ua.add_argument("--key", help="the work's key")
    ua.add_argument("--doi", help="the work's DOI (either this or --key)")
    ua.add_argument("--statement", required=True, help="what the work supplies, in one sentence")
    ua.add_argument("--kind", required=True,
                    help="the database's vocabulary (method, theorem, parameter, empirical evidence, "
                         "negative result, context, contradiction); it refuses anything else")
    ua.add_argument("--status", default="proposed")
    ua.add_argument("--feeds", help="semicolon-separated tokens, checked against litkb._feeds_token_ok "
                                    "BEFORE the write; the seven forms are in LITERATURE_CONVENTION.md")
    ua.add_argument("--quote", help="the exact words, as the extraction has them; verified server-side")
    ua.add_argument("--page", type=int, help="the page the quote is on (narrows the search; optional)")
    ua.add_argument("--stance", default="supports", help="supports | refutes | context")
    ua.add_argument("--confidence")
    ua.add_argument("--rationale", help="why this use reads the work this way — NOT a place for the quote")
    ua.add_argument("--hunt-request", dest="hunt_request",
                    help="a hunt_request id (migration 0023): this use circles back to that drop-off")
    usub.add_parser("list")

    i = sub.add_parser("inventory", help="stage 0: report PDFs the frozen census does not pin")
    i.add_argument("--new", action="store_true")
    i.add_argument("--root", help="literature root (default LITKB_LITERATURE_ROOT)")
    i.add_argument("--census", help="default: <repo>/phase4/qc/litkb_inventory_census.sha256")
    i.add_argument("--json", action="store_true")

    # ── the staging reaper, S3 (litkb/ops/reaper.py) ────────────────────────────────────────
    rp = sub.add_parser("reap", help="census the staging directories: which files the database "
                                     "accounts for, which are too young to judge, and which are "
                                     "orphans. Quarantines an orphan only with --apply; nothing "
                                     "is ever deleted")
    rp.add_argument("--root", help="literature root (default LITKB_LITERATURE_ROOT)")
    rp.add_argument("--min-age-hours", dest="min_age_hours", type=float, default=72.0,
                    help="a file younger than this is reported `young` and left alone (default 72)")
    g = rp.add_mutually_exclusive_group()
    g.add_argument("--dry-run", dest="apply", action="store_false", default=False,
                   help="the default: print the census and move nothing")
    g.add_argument("--apply", dest="apply", action="store_true",
                   help="quarantine each orphan, with a .reason.json beside it")
    rp.add_argument("--out", help="write the census as JSON to this path")
    rp.add_argument("--json", action="store_true", help="print the census as JSON, not a table")
    rp.add_argument("--role", default=os.environ.get("LITKB_READER_ROLE") or "litkb_reader",
                    help="the read login (default: LITKB_READER_ROLE, else litkb_reader). Worker "
                         "databases litkb_test_wN admit ONLY litkb_test, so a run against one "
                         "passes --role litkb_test")

    # ── the one-shot entry point, 2026-09-16 (litkb/hunt.py) ────────────────────────────────
    h = sub.add_parser("hunt", help="one call: resolve a DOI or URL, admit it, bind the PDF, "
                                    "extract it and ingest it")
    h.add_argument("ref", help="a DOI (10.…, or a doi.org URL) or the URL of a document")
    h.add_argument("--title", help="the work's title; a URL source has no registry to ask")
    h.add_argument("--author", help="the first author, as the document's first page prints it")
    h.add_argument("--year", type=int)
    h.add_argument("--key", help="the work key (default: Surname_Year_slug)")
    h.add_argument("--source-note", dest="source_note")
    h.add_argument("--retrieved", help="the retrieval date recorded for a URL source (default: today, UTC)")
    h.add_argument("--no-extract", action="store_true",
                   help="admit and bind only; leave the extraction to a later hunt or the bulk pass")
    h.add_argument("--no-spend", action="store_true",
                   help="stop at `held` (admitted, no PDF) without attempting acquisition; the "
                        "default SPENDS: open access, then the archive, then Sci-Hub "
                        "(decisions.yaml litkb-p0-foundation, SPEND RULE 2026-09-16)")
    h.add_argument("--device", default="cuda",
                   help="the docling device (cuda | cpu | auto); chosen WITH its interpreter by "
                        "litkb.extract.docling.device_pair, and a device the interpreter cannot "
                        "serve is refused before anything runs")
    h.add_argument("--docling-python", dest="docling_python",
                   help="the extraction venv's python (default: litkb.extract.docling.VENV_PYTHON)")
    h.add_argument("--derived", help="where the tool artifacts go (default LITKB_HUNT_DERIVED)")
    h.add_argument("--hunt-request", dest="hunt_request",
                   help="a hunt_request id (migration 0023): link this drop-off to whatever work "
                        "this reference resolves to, cached or fresh")
    h.add_argument("--ref-scheme", dest="ref_scheme",
                   help="what this reference IS, one of " + " | ".join(REF_SCHEMES) + ". "
                        "Omitted, the scheme is inferred from the shape, and a shape nothing "
                        "matches is refused `malformed-ref` (never a DOI by default). With "
                        "--hunt-request the drop-off's own scheme wins, and one that disagrees "
                        "with it is refused `ref-scheme-mismatch`. `title` needs --author and "
                        "--year")

    # ── the drop-off record, 2026-09-18 (migration 0023, litkb/hunt_request.py) ─────────────
    hr = sub.add_parser("hunt-request", help="the review agent's drop-off: a claim, why it "
                                             "matters, and the abstract passage it came from, "
                                             "written before the paper is even hunted")
    hrsub = hr.add_subparsers(dest="hunt_request_cmd", required=True)
    hra = hrsub.add_parser("add")
    hra.add_argument("--ref", required=True, help="the identifier/URL/citation as given")
    hra.add_argument("--ref-scheme", dest="ref_scheme", required=True,
                     help=" | ".join(REF_SCHEMES) + "  (the one vocabulary: "
                          "litkb.hunt_request.REF_SCHEMES, held equal to the table's CHECK)")
    hra.add_argument("--expected-claim", dest="expected_claim", required=True,
                     help="the claim you expect this paper to support")
    hra.add_argument("--why-relevant", dest="why_relevant", required=True)
    hra.add_argument("--abstract-passage", dest="abstract_passage",
                     help="the abstract/snippet you reasoned from — UNVERIFIED, never a quote source")
    hra.add_argument("--claimed-title", dest="claimed_title")
    hra.add_argument("--claimed-authors", dest="claimed_authors")
    hra.add_argument("--claimed-year", dest="claimed_year", type=int)
    hra.add_argument("--gap", help="an existing gap's slug this drop-off is meant to help answer")
    hrl = hrsub.add_parser("list")
    hrl.add_argument("--state", choices=["open", "unconfirmed", "confirmed", "contradicted"])
    hrl.add_argument("--limit", type=int, default=50)

    # ── the per-workstream BRIEF export, 2026-09-18 (litkb/brief.py) ────────────────────────
    br = sub.add_parser("brief", help="every hunt_request (EXPECTED) and every promotable quote "
                                      "(VERIFIED) this workstream holds, as markdown")
    br.add_argument("workstream", nargs="?", help="workstream id or slug (default: this worktree's)")
    br.add_argument("--out", help="output path (default: _derived/briefs/<slug>.md, untracked)")

    # ── the K1/K2 gate on a written review, 2026-09-20 (litkb/review_check.py) ──────────────
    rc = sub.add_parser("review-check", help="grade a written review against its own workstream: "
                                             "every claim traceable to a VERIFIED quote (K1) and "
                                             "every unsupported expectation disclosed (K2)")
    rc.add_argument("review", help="path to the review .md (it names its own workstream in its "
                                   "first line)")
    rc.add_argument("--workstream", help="id, slug, or 'current' (this worktree's): ASSERTS which "
                                         "workstream this review is, and is refused when the "
                                         "review's own header declares another. It never "
                                         "redirects the grade")

    # ── the adversarial reader's INPUT, 2026-09-20 (litkb/review_context.py) ────────────────
    rx = sub.add_parser("review-context",
                        help="the FULL BLOCK behind every citation of a review, as markdown: the "
                             "file an adversarial reader needs to tell a faithful sentence from "
                             "one the quote does not carry. Exits 1 on a block it cannot show")
    rx.add_argument("review", help="path to the review .md (it names its own workstream)")
    rx.add_argument("--out", help="output path (default: <review>.context.md)")
    rx.add_argument("--role", default=os.environ.get("LITKB_READER_ROLE") or "litkb_reader",
                    help="the read login (default: LITKB_READER_ROLE, else litkb_reader). Worker "
                         "databases litkb_test_wN admit ONLY litkb_test (provision_workers), so a "
                         "run against one passes --role litkb_test; the same variable hunt.py reads")

    # ── retiring superseded run sets, 2026-09-22 (migration 0031, litkb/ops/retire.py) ──────
    rn = sub.add_parser("runs", help="extraction runs: retire the superseded ones (MARKING, never "
                                     "deleting; S4 run 3 decision D6)")
    rnsub = rn.add_subparsers(dest="runs_cmd", required=True)
    rr = rnsub.add_parser("retire", help="list what would be retired, what is excluded and why; "
                                         "--apply records ONE op (who, when, why)")
    rrg = rr.add_mutually_exclusive_group()
    rrg.add_argument("--dry-run", dest="apply", action="store_false", default=False,
                     help="the default: report, write nothing")
    rrg.add_argument("--apply", dest="apply", action="store_true",
                     help="record the retirement through the ingest login (litkb.ingest.connect)")
    rr.add_argument("--reason", help="why this op retires these runs (required with --apply)")
    rr.add_argument("--json", action="store_true", help="print the plan as JSON, not a table")
    rr.add_argument("--out", help="write the plan as JSON to this path")
    rr.add_argument("--role", default=os.environ.get("LITKB_READER_ROLE") or "litkb_reader",
                    help="the read login (default: LITKB_READER_ROLE, else litkb_reader)")
    # ── S4: the database-visible quarantine state and the readability classifier ─────────────
    qa = sub.add_parser("quarantine", help="the quarantine state (litkb.quarantine_payloads, migration 0030)")
    qsub = qa.add_subparsers(dest="quarantine_cmd", required=True)
    qb = qsub.add_parser("backfill", help="a row for every payload already in the quarantine directory; dry run by "
                                          "default, --apply writes (ingest login)")
    qb.add_argument("--apply", action="store_true", help="write the rows (default: a dry run that writes nothing)")
    qb.add_argument("--root", help="literature root (default LITKB_LITERATURE_ROOT, else the store's)")
    qb.add_argument("--json", action="store_true")
    qb.add_argument("--out", help="also write the JSON document here (create-only)")
    qb.add_argument("--role", default=os.environ.get("LITKB_READER_ROLE") or "litkb_reader",
                    help="the read login for the census (default: LITKB_READER_ROLE, else litkb_reader)")
    rd = sub.add_parser("readability", help="classify every acquired file into the closed readability "
                                            "classes and write Reports/LITKB_READABILITY_<date>.csv")
    rd.add_argument("--workstream", action="append", help="also classify this workstream's current files "
                                                          "(repeatable; an id)")
    rd.add_argument("--all-workstreams", action="store_true", help="every workstream's current files too")
    rd.add_argument("--csv", help="output path (default Reports/LITKB_READABILITY_<today>.csv; create-only)")
    rd.add_argument("--no-csv", action="store_true", help="print the counters only")
    rd.add_argument("--record", action="store_true",
                    help="record a quarantine row for each bound file refused bad-file/zero-content/"
                         "probe-error (ingest login); default: write nothing")
    rd.add_argument("--root", help="literature root (default LITKB_LITERATURE_ROOT, else the store's)")
    rd.add_argument("--role", default=os.environ.get("LITKB_READER_ROLE") or "litkb_reader",
                    help="the read login (default: LITKB_READER_ROLE, else litkb_reader)")
    # ── the extraction queue, S4 run 3 (litkb/extract/queue.py, migration 0029) ─────────────
    q = sub.add_parser("queue", help="the extraction queue: sweep (enqueue), work (claim, "
                                     "extract, ingest under a lease), status")
    qsub = q.add_subparsers(dest="queue_cmd", required=True)
    qs = qsub.add_parser("sweep", help="enqueue one stage-5 job per active file with no current run "
                                       "(page-range jobs for an OCR-routed file); the guards refuse "
                                       "book, bad-file, probe-error, over-page-cap, scan-needs-ocr")
    qs.add_argument("--workstream", action="append",
                    help="also sweep this workstream's view (id or slug; repeatable)")
    qs.add_argument("--redo", action="store_true",
                    help="with --file: enqueue a stage-5 job at TODAY's run key for a named file "
                         "whose current run sits at an OLDER key (never one already at today's "
                         "key); every guard still applies")
    qw = qsub.add_parser("work", help="claim jobs one at a time until the queue is empty")
    qw.add_argument("--max-jobs", dest="max_jobs", type=int, help="stop after this many claims")
    qw.add_argument("--lease", type=int, default=None,
                    help="lease seconds (default litkb.extract.queue.LEASE_SECONDS, measured); "
                         "the heartbeat renews at half of it")
    qw.add_argument("--worker", help="the worker id recorded on each lease (default host:pid)")
    qw.add_argument("--device", default="auto", help="the docling device: auto | cuda | cpu, "
                                                     "chosen WITH its interpreter (device_pair)")
    qw.add_argument("--docling-python", dest="docling_python",
                    help="the extraction venv's python (default: chosen by device_pair)")
    qw.add_argument("--derived", help="the artifact root (default: references.DERIVED_ROOT)")
    for sp in (qs, qw):
        sp.add_argument("--root", help="the literature root rel_path is relative to (default "
                                       "LITKB_LITERATURE_ROOT, else the store's)")
        sp.add_argument("--no-ocr", dest="no_ocr", action="store_true",
                        help="OCR off (also LITKB_QUEUE_NO_OCR=1): an OCR-routed file is refused "
                             "`scan-needs-ocr` and never started")
        sp.add_argument("--file", dest="files", action="append",
                        help="only this file id (repeatable)")
    qsub.add_parser("status", help="counts by state and refusal, and pages remaining")
    return ap


def cmd_runs(args, conn):
    """`litkb runs retire [--apply]` — litkb/ops/retire.py, migration 0031.

    It opens its OWN logins, like `reap`: the dry run is SELECTs only, so it reads as
    `litkb_reader` (which is also what lets it run against live without a write credential), and
    `--apply` hands the eligible list to `litkb.retire_extraction_runs`, which only the ingest
    login may execute. The session label (--session or LITKB_SESSION) and --reason are recorded
    with the op; nothing is deleted."""
    from litkb.db import connect as _c
    from litkb.ops import retire as _rt
    from litkb.textnorm import norm_label

    session = norm_label(args.session or os.environ.get("LITKB_SESSION") or "")
    if args.apply and (not session.strip() or not (args.reason or "").strip()):
        raise SystemExit("litkb runs retire --apply: a session label (--session or LITKB_SESSION) "
                         "and --reason are both required — the op records who and why")
    reader = _c.connect(args.db, args.role, autocommit=True)
    ingest_conn = None
    try:
        if args.apply:
            from litkb import ingest as _ingest

            ingest_conn = _ingest.connect(args.db)
        out = _rt.retire(reader, ingest_conn, apply=bool(args.apply), session=session,
                         reason=args.reason)
    finally:
        reader.close()
        if ingest_conn is not None:
            ingest_conn.close()
    doc = _rt.as_json(out)
    if args.json:
        _print(doc)
    else:
        for line in _rt.summary_lines(out):
            print(line)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, default=str, ensure_ascii=False)
    return 0


class _NoConn:
    """The connection a command that opens its OWN logins is handed: it has none. Anything that
    tried to query through it would fail loudly here rather than quietly opening a second
    credential."""

    def execute(self, *a, **kw):
        raise RuntimeError("this command opens its own logins (litkb.promote.connect for the "
                           "promoter, litkb.ingest.connect for the ingest login); the shared "
                           "writer connection is deliberately not used")

    def close(self):
        pass


#: Commands that open every login they need for themselves, and must NOT be handed a writer.
#: `review-context`: it reads blocks and nothing else, and the file it writes is handed to a model
#: outside this machine, so it opens `litkb_reader` itself rather than hold a writer for the
#: length of that read.
#: `promote`: promote_prepare and promote_commit may be executed only by litkb_promoter
#: (design §4.7), and cmd_promote opens that login itself. `hunt`: it uses a reader, a writer AND
#: the ingest login, each for the part that needs it, so the one opened here would be a fourth
#: connection nothing reads. Against a throwaway database, where only the test login has a
#: password, it is also a connection that cannot even be made.
#: `reap`: it reads litkb.files and litkb.file_versions on the READER login and writes no row at
#: all, so the writer main() would hand it is a credential it never uses — and a worker database's
#: pgpass has no litkb_writer line, which would make the command test-only.
#: `runs`: the dry run reads on the READER login and `--apply` writes through the ingest login,
#: each opened by cmd_runs; the writer is a credential it never uses.
#: `quarantine` / `readability` (S4): a READER for the census and, only with --apply / --record, the
#: INGEST login for the rows — never the writer, whose record_quarantine needs a workstream token
#: these system operations do not have.
#: `queue`: it runs as litkb_ingest through migration 0029's functions and opens that login itself
#: (plus a second connection for the heartbeat), like `hunt`'s ingest step.
_OWN_LOGINS = ("promote", "hunt", "review-context", "reap", "runs", "quarantine",
               "readability", "queue")


def main(argv=None, connect=None):
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    conn = _NoConn() if args.cmd in _OWN_LOGINS and connect is None else (connect or _default_connect)(args.db)
    try:
        return {"ws": cmd_ws, "admit": cmd_admit, "approve": cmd_approve,
                "refuse": cmd_refuse, "withdraw": cmd_withdraw,
                "approve-files": cmd_decide_files, "refuse-files": cmd_decide_files,
                "acquire": cmd_acquire, "migrate": cmd_migrate, "export": cmd_export,
                "use": cmd_use, "inventory": cmd_inventory, "hunt": cmd_hunt, "reap": cmd_reap,
                "hunt-request": cmd_hunt_request, "brief": cmd_brief,
                "review-check": cmd_review_check, "review-context": cmd_review_context,
                "promote": cmd_promote, "runs": cmd_runs, "quarantine": cmd_quarantine,
                "readability": cmd_readability, "queue": cmd_queue}[args.cmd](args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

"""Retiring superseded extraction run sets — a deliberate op that MARKS runs, never deletes them.

    from litkb.ops import retire
    plan = retire.plan(reader_conn)                                  # the dry run: writes nothing
    out  = retire.retire(reader_conn, ingest_conn, apply=True,
                         session="s4-run3", reason="...")            # records ONE op id
    n    = retire.superseded_runs_unretired(reader_conn)             # the REPORTED counter

S4 run 3 decision D6: retirement is MARKING. Migration 0031 adds a record of which runs a
deliberate op retired, when, by which login and session, and why; the run rows and their
blocks, pages and references stay. Every rule lives in the database —
``litkb.run_retirement_status`` decides which runs are superseded and why any other run is
refused, and ``litkb.retire_extraction_runs`` re-checks the same facts, guard by guard, before it
writes. This module only asks, reports and hands the database the list it was told is eligible.

WHO RUNS WHAT. The dry run needs nothing but ``litkb_reader``: the status function is granted to
it and every count here is a SELECT. ``--apply`` hands the eligible list to
``retire_extraction_runs``, which only ``litkb_ingest`` may execute — the login that owns
extraction runs (``litkb.ingest.connect``).

THE STAGE-6 KEY. Stage 6 (``6-references``) never moves ``files.current_run_id``, so "superseded"
cannot mean "no longer current" there. It means: an ok run whose key is not the CURRENT stage-6
key, for a file that holds a NEWER ok run at the current key (S4 run 3, orchestrator's addition
to D2's scope). The current key is read from :func:`litkb.extract.references_ingest.run_key` —
never a copy — and passed to the database as ``p_keys``; the database refuses to call a run
superseded by an OLDER one, so naming a stale key retires nothing.
"""
import json

#: The refusal vocabulary of ``litkb.run_retirement_status`` (migration 0031), in the order its
#: CASE applies them — closed, and one home: the SQL. This tuple is a READ of it for reports and
#: tests (qc/test_litkb_retire.py pins the two against each other).
REFUSALS = ("current", "evidence", "already-retired", "not-superseded")

#: The stage whose supersession is judged by the current KEY rather than the pointer.
STAGE6 = "6-references"


def current_keys():
    """{stage: {tool, tool_version, params_hash, pipeline_version}} for the stages judged by key.

    Read from the stage's own ``run_key``, so a bump of ``references.PIPELINE_VERSION`` (or of any
    threshold in its params hash) is the new current key without an edit here."""
    from litkb.extract import references_ingest as RI

    k = RI.run_key(None)
    return {k["stage"]: {f: k[f] for f in ("tool", "tool_version", "params_hash", "pipeline_version")}}


def _jsonb(v):
    from psycopg.types.json import Jsonb

    return Jsonb(v)


def status(conn, keys=None, files=None):
    """Every extraction run with its facts and its verdict (``refusal`` None = retirable now).
    ``files`` (ids) narrows the report to those files' runs — the whole database otherwise."""
    keys = current_keys() if keys is None else keys
    cur = conn.execute(
        "SELECT s.*, w.key AS work_key FROM litkb.run_retirement_status(%s) s "
        "LEFT JOIN litkb.main_files mf ON mf.file_id = s.file_id "
        "LEFT JOIN litkb.main_works w ON w.work_id = mf.work_id "
        "ORDER BY s.stage, w.key, s.run_id", (_jsonb(keys),))
    cols = [d.name for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    if files is not None:
        want = {str(f) for f in files}
        rows = [r for r in rows if str(r["file_id"]) in want]
    return rows


def superseded_runs_unretired(conn, keys=None):
    """REPORTED: runs superseded at their stage that no op has retired yet and that nothing
    stops an op from retiring (refusal NULL). An ``--apply`` of the current plan takes it to 0; the
    runs held by evidence are counted apart (:func:`plan`'s ``excluded``), because no op may ever
    retire them and a counter that could never reach 0 would say nothing."""
    keys = current_keys() if keys is None else keys
    return conn.execute("SELECT count(*) FROM litkb.run_retirement_status(%s) WHERE refusal IS NULL",
                        (_jsonb(keys),)).fetchone()[0]


def _row_counts(conn, run_ids):
    """{run_id: (blocks, pages, references)} for the runs named."""
    if not run_ids:
        return {}
    out = {r: [0, 0, 0] for r in run_ids}
    for i, table in enumerate(("blocks", "pages", '"references"')):
        for rid, n in conn.execute(f"SELECT run_id, count(*) FROM litkb.{table} "
                                   "WHERE run_id = ANY(%s) GROUP BY run_id", (list(run_ids),)):
            out[rid][i] = n
    return {k: tuple(v) for k, v in out.items()}


def plan(conn, keys=None, files=None):
    """The dry run. -> a dict: what an op would retire (per stage, with its rows), what is EXCLUDED
    and why (the evidence-bearing runs named by work key), and the counters. Writes nothing."""
    keys = current_keys() if keys is None else keys
    rows = status(conn, keys, files)
    eligible = [r for r in rows if r["refusal"] is None]
    counts = _row_counts(conn, [r["run_id"] for r in eligible])
    by_stage = {}
    for r in eligible:
        b, p, x = counts.get(r["run_id"], (0, 0, 0))
        s = by_stage.setdefault(r["stage"], {"runs": 0, "files": set(), "blocks": 0, "pages": 0,
                                             "references": 0, "pipeline_versions": {}})
        s["runs"] += 1
        s["files"].add(r["file_id"])
        s["blocks"] += b
        s["pages"] += p
        s["references"] += x
        s["pipeline_versions"][r["pipeline_version"]] = s["pipeline_versions"].get(r["pipeline_version"], 0) + 1
    for s in by_stage.values():
        s["files"] = len(s["files"])
    # the refusals of runs that are NOT current: `current` is every file's live run, reported as a
    # count only; the rest are the runs an op would otherwise have looked at
    excluded = {}
    for r in rows:
        if r["refusal"] is None:
            continue
        excluded.setdefault(r["refusal"], []).append(r)
    ev_counts = _row_counts(conn, [r["run_id"] for r in excluded.get("evidence", [])])
    evidence = [{"work_key": r["work_key"], "run_id": str(r["run_id"]), "stage": r["stage"],
                 "pipeline_version": r["pipeline_version"], "evidence_rows": r["evidence_rows"],
                 "superseded_by": str(r["superseded_by"]) if r["superseded_by"] else None,
                 "blocks": ev_counts.get(r["run_id"], (0, 0, 0))[0]}
                for r in excluded.get("evidence", [])]
    return {
        "keys": keys,
        "eligible": [str(r["run_id"]) for r in eligible],
        "by_stage": by_stage,
        "stage6": by_stage.get(STAGE6, {"runs": 0, "files": 0, "blocks": 0, "pages": 0,
                                        "references": 0, "pipeline_versions": {}}),
        "excluded_counts": {k: len(v) for k, v in sorted(excluded.items())},
        "excluded_evidence": evidence,
        "excluded_not_superseded_by_stage": _by_stage(excluded.get("not-superseded", [])),
        "counters": {
            "superseded_runs_unretired": len(eligible),
            "superseded_runs_held_by_evidence": sum(1 for r in excluded.get("evidence", [])
                                                    if r["superseded_by"] is not None),
            "runs_already_retired": len(excluded.get("already-retired", [])),
            "current_runs": len(excluded.get("current", [])),
        },
    }


def _by_stage(rows):
    out = {}
    for r in rows:
        out[r["stage"]] = out.get(r["stage"], 0) + 1
    return dict(sorted(out.items()))


def retire(read_conn, ingest_conn=None, *, apply=False, session=None, reason=None, keys=None,
           files=None):
    """The op. Dry run by default (``apply=False``: ``ingest_conn`` is not touched and may be None).

    With ``apply=True`` the eligible runs of :func:`plan` go to ``litkb.retire_extraction_runs`` in
    ONE call, so they are one op with one id, and the database re-checks every refusal itself
    before it writes. -> the plan, plus ``op_id`` (None on a dry run or when nothing is eligible).
    """
    keys = current_keys() if keys is None else keys
    p = plan(read_conn, keys, files)
    p["applied"] = False
    p["op_id"] = None
    if not apply:
        return p
    if not (session or "").strip() or not (reason or "").strip():
        raise ValueError("litkb runs retire --apply records WHO and WHY: a session label and a "
                         "reason are both required")
    if not p["eligible"]:
        return p
    op = ingest_conn.execute(
        "SELECT litkb.retire_extraction_runs(%s::uuid[], %s, %s, %s)",
        (p["eligible"], session, reason, _jsonb(keys))).fetchone()[0]
    p["applied"] = True
    p["op_id"] = str(op)
    return p


def as_json(p):
    return json.loads(json.dumps(p, default=str))


def summary_lines(p):
    """The human dry-run report."""
    out = [f"mode={'apply' if p.get('applied') else 'dry-run'} op_id={p.get('op_id')}"]
    for stage, s in sorted(p["by_stage"].items()):
        out.append(f"would retire  stage={stage} runs={s['runs']} files={s['files']} "
                   f"blocks={s['blocks']} pages={s['pages']} references={s['references']} "
                   f"versions={json.dumps(s['pipeline_versions'], sort_keys=True)}")
    if STAGE6 not in p["by_stage"]:
        out.append(f"would retire  stage={STAGE6} runs=0 (no file holds a newer ok run at the "
                   f"current key {p['keys'].get(STAGE6, {}).get('pipeline_version')})")
    for k, n in p["excluded_counts"].items():
        out.append(f"excluded      refusal={k} runs={n}")
    for e in p["excluded_evidence"]:
        out.append(f"  evidence    {e['work_key']} run={e['run_id']} stage={e['stage']} "
                   f"version={e['pipeline_version']} evidence_rows={e['evidence_rows']} "
                   f"blocks={e['blocks']}")
    out.append(" ".join(f"{k}={v}" for k, v in p["counters"].items()))
    return out

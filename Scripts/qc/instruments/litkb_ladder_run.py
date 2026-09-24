r"""The ladder-1 run driver (S4.5 decision D9): every row the `hardening` manifest froze, through the
REAL acquisition ladder, one row at a time, with every request RECORDED.

    cd Scripts
    # LIVE — the orchestrator's pass, in the worktree that holds the ladder-1 token. Never a builder's.
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_ladder_run.py \
        --manifest <frozen hardening manifest> [--only L001] [--redo L001]

WHAT IT RUNS. The manifest's `rows` (litkb_acceptance.py `select_run_rows`), in id order:
  * `hunt` rows — the work holds no file — go through `litkb.hunt.hunt` in-process, spend on, the
    ladder `hunt._default_acquire` calls, at its own defaults. A hunt that raises is a written row
    (`traceback=1`), never a dead run: the edge driver's rule, shared through its `_call`.
  * `measure` rows — the work already holds a file — are ASKED of every rung and each answer is
    recorded as an attempt row, and nothing lands twice. This driver calls the HOOK the ladder exposes
    (`litkb.acquire.run` is builder C1a's; the hook was added on the merged candidate, integrator-w1),
    :data:`MEASURE_HOOK` = `litkb.acquire.run.measure`, with the contract in :data:`MEASURE_CONTRACT`,
    and were the hook absent a measure row would be written `skipped / measure-hook-absent` — named,
    counted, never silently hunted instead (a hunt of a work that holds a file stops at the rung it is
    on and asks no route at all).

RECORD MODE IS ON for the whole run (`litkb.cassette`, S4.5 item 7): the driver sets `LITKB_CASSETTE=
record` and the index the manifest names BEFORE the first request, and tags each row with its
reference (`begin_row` in-process, `LITKB_CASSETTE_ROW` for a child process), so the register replay —
which uses register row ids, not these — meets the recording on the same tag.

THE RECORDING REPORT. At the end of every pass (a resumed pass rewrites it) the driver writes the
manifest's `recording_report` (:func:`write_recording_report`): the index's sha256 when the pass
finished, its entries and row tags, and every recording that could not be written. The replay
counters refuse an index that is not that one, so an index edited after the live pass cannot be
graded as the recording.

EXTRACTION is the hunt's own default (extract on, GPU); `--no-extract` passes `extract=False` to every
hunt. Which one the live pass uses is the orchestrator's decision, not this driver's.

RESUMABLE, the scout and edge drivers' rule: the run CSV is the ledger; a row already in it is never
run again unless `--redo` names it. The CSV is rewritten whole after every row. Its columns are
:data:`RUN_CSV_COLUMNS` (docs/SCHEMAS.md, "S4.5 builder A").

`attempts_written` is measured, not reported: the workstream's `acquisition_attempts` count, read on
the reader login before and after the row. A row the run does not own (another session writing in
the same workstream at the same moment) would inflate it; the run is one session's.

It refuses a manifest edited after its freeze (litkb_acceptance.load_hardening_manifest). Stdlib plus
the litkb package, imported lazily. Not run on Colab.
"""
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]

RUN_CSV_COLUMNS = ("row_id", "ref", "ref_scheme", "mode", "source", "state", "reason",
                   "attempts_written", "wall_seconds", "traceback", "started_at", "message")

#: The ladder's measure entry point, by dotted name (`litkb.acquire.run.measure`, builder C1a's module;
#: this driver never defines it).
MEASURE_HOOK = "litkb.acquire.run.measure"

#: What the hook must do. Stated here so the builder who adds it builds to the call this driver makes.
MEASURE_CONTRACT = (
    "measure(conn, ws, token, work, *, store, agent, session) -> {'outcome': 'measured', "
    "'attempts': [(route, status), ...], 'route_detail': [...]}: ask EVERY rung for `work` (a "
    "run.work_record dict whose held_files may be > 0), ignoring DEAD_STATUSES and the held-file "
    "short-circuit; record every rung's answer as an acquisition_attempts row in `ws`; land NOTHING "
    "(a served PDF is hashed into the attempt's detail, never written to staging, never attached) "
    "and bind nothing.")

MEASURE_ABSENT = (f"{MEASURE_HOOK} does not exist yet (litkb.acquire.run is builder C1a's): this "
                  "row holds a file, so it is MEASURED, never hunted; contract: " + MEASURE_CONTRACT)


def _load(stem):
    spec = importlib.util.spec_from_file_location(stem, SCRIPTS / "qc" / "instruments" / f"{stem}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def measure_hook():
    """The ladder's measure entry point, or None while it is not built."""
    from litkb.acquire import run as R

    return getattr(R, MEASURE_HOOK.rsplit(".", 1)[1], None)


def read_run_csv(path):
    p = Path(path)
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8", newline="") as fh:
        return {r["row_id"]: r for r in csv.DictReader(fh)}


def write_run_csv(path, rows):
    """Whole-file rewrite through a temp file (the edge driver's rule)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".partial")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(RUN_CSV_COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RUN_CSV_COLUMNS})
    os.replace(tmp, path)


def start_recording(index, bodies=None):
    """Put every `Client` in this process (and every child it starts) in RECORD mode into `index`."""
    os.environ["LITKB_CASSETTE"] = "record"
    os.environ["LITKB_CASSETTE_INDEX"] = str(index)
    if bodies:
        os.environ["LITKB_CASSETTE_BODIES"] = str(bodies)
    from litkb import cassette as C

    return C.active()


RECORDING_REPORT_KIND = "litkb-hardening-recording"


def write_recording_report(manifest, repo, cas, *, rows_run):
    """The run driver's last word on the recording, written at the end of every pass (a resumed pass
    rewrites it): the recorded index's path and the sha256 of its BYTES now, its live entries and row
    tags, the recordings that could not be written, and a self-hash. `hardening --manifest` refuses a
    replay of an index that is not this one (auditor-A round 1, F6: nothing tied the replayed index to
    the live recording, because the manifest is frozen before the run records anything).
    -> the report path, or None when the manifest promises none (a manifest frozen before this field)."""
    from litkb import cassette as C

    HA = _load("litkb_hardening_a")
    rel = manifest.get("recording_report")
    if not rel:
        return None
    out = Path(rel) if Path(rel).is_absolute() else repo / rel
    idx = Path(manifest["cassette_index"]["path"])
    idx = idx if idx.is_absolute() else repo / idx
    live = C.Cassette(idx, "replay", bodies=idx.parent) if idx.is_file() else None
    report = {"kind": RECORDING_REPORT_KIND, "manifest_sha256": manifest.get("manifest_sha256"),
              "index": str(idx), "index_sha256": C.index_sha256(idx),
              "entries": len(live.entries) if live is not None else 0,
              "rows": sorted({e.get("row", "") for e in live.entries}) if live is not None else [],
              "rows_run_this_pass": rows_run,
              "record_errors": list(cas.record_errors) if cas is not None else [],
              "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    report["recording_sha256"] = HA.summary_sha(report, "recording_sha256")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return out


def _tag_row(ref):
    from litkb import cassette as C

    os.environ["LITKB_CASSETTE_ROW"] = str(ref or "")
    cas = C.active()
    if cas is not None:
        cas.begin_row(ref)


def _default_attempts_counter(db, role, ws_id):
    def count():
        from litkb.db import connect as c

        conn = c.connect(db, role, autocommit=True)
        try:
            return conn.execute("SELECT count(*) FROM litkb.acquisition_attempts WHERE workstream_id = %s",
                                (ws_id,)).fetchone()[0]
        finally:
            conn.close()
    return count


def _default_measure(row, ctx):
    """-> (state, reason, message). The measure hook, or the named skip while it is absent."""
    hook = measure_hook()
    if hook is None:
        return "skipped", "measure-hook-absent", MEASURE_ABSENT
    from litkb import workstream
    from litkb.acquire.run import work_record
    from litkb.acquire.store import Store
    from litkb.db import connect as c

    ws, token = workstream.load(ctx["worktree"])
    conn = c.connect(ctx["db"], ctx["writer_role"], autocommit=True)
    try:
        work = work_record(conn, work_id=row.get("work_id")) if row.get("work_id") else \
            work_record(conn, doi=row["ref"])
        if work is None:
            return "skipped", "work-not-in-main", "the manifest's work is not in main on this database"
        res = hook(conn, ws, token, work, store=ctx.get("store") or Store(), agent=ctx["agent"],
                   session=ctx["session"])
    finally:
        conn.close()
    return "measured", str(res.get("outcome") or ""), json.dumps(res.get("attempts") or [])[:400]


def run_rows(manifest, out_csv, *, db, worktree, agent, session, hunt=None, measure=None,
             attempts_counter=None, only=(), redo=(), reader_role="litkb_reader",
             writer_role="litkb_writer", hunt_kwargs=None, record=True, bodies=None):
    """Every manifest row, one at a time. -> (ran, resumed, rows).

    `hunt`, `measure` (fn(row, ctx) -> (state, reason, message)) and `attempts_counter` are injected
    by the tests; the defaults are the real `litkb.hunt.hunt`, the ladder's measure hook and a reader
    count. `hunt_kwargs` are passed through to every hunt (the tests' registry stub and acquirer)."""
    E = _load("litkb_edge_run")
    if hunt is None:
        import litkb.hunt as H

        hunt = H.hunt
    measure = measure or _default_measure
    if attempts_counter is None:
        attempts_counter = _default_attempts_counter(db, reader_role, manifest.get("workstream_id"))
    repo = Path(manifest.get("repo") or SCRIPTS.parent)
    cas = None
    if record:
        idx = Path(manifest["cassette_index"]["path"])
        cas = start_recording(idx if idx.is_absolute() else repo / idx,
                              bodies or manifest["cassette_index"].get("bodies"))
    ctx = {"db": db, "worktree": worktree, "agent": agent, "session": session,
           "reader_role": reader_role, "writer_role": writer_role}
    done = read_run_csv(out_csv)
    only, redo = set(only or ()), set(redo or ())
    written, ran, resumed = [], 0, 0
    for row in manifest.get("rows") or []:
        rid = row["id"]
        if only and rid not in only:
            if rid in done:
                written.append(done[rid])
            continue
        if rid in done and rid not in redo:
            written.append(done[rid])
            resumed += 1
            continue
        out = {"row_id": rid, "ref": row.get("ref") or "", "ref_scheme": row.get("ref_scheme") or "",
               "mode": row.get("mode") or "", "source": ";".join(row.get("source") or []),
               "traceback": "0", "started_at": E._utc_now_text()}
        if record:
            _tag_row(row.get("ref"))
        before = attempts_counter()
        t0 = time.monotonic()
        if row.get("mode") == "measure":
            try:
                out["state"], out["reason"], out["message"] = measure(row, ctx)
            except Exception as e:          # noqa: BLE001 — a raise is a written row, never a dead run
                out["traceback"] = "1"
                out["message"] = f"{type(e).__name__}: {str(e).splitlines()[0][:300] if str(e) else ''}"
        else:
            kwargs = {"ref": row["ref"], "ref_scheme": row.get("ref_scheme") or None, "db": db,
                      "worktree": worktree, "agent": agent, "session": session, "spend": True,
                      "reader_role": reader_role, "writer_role": writer_role}
            kwargs.update(hunt_kwargs or {})
            res, tb = E._call(hunt, kwargs)
            if res is None:
                out["traceback"] = "1"
                out["message"] = tb
            else:
                out["state"], out["reason"] = str(res.get("state") or ""), str(res.get("reason") or "")
                out["message"] = str(res.get("message") or "")[:500]
        out["wall_seconds"] = round(time.monotonic() - t0, 2)
        out["attempts_written"] = max(0, attempts_counter() - before)
        written.append(out)
        ran += 1
        write_run_csv(out_csv, written)       # after EVERY row: the ledger is the resume
    write_run_csv(out_csv, written)
    if record:
        write_recording_report(manifest, repo, cas, rows_run=ran)
    return ran, resumed, written


def main(argv=None):
    ap = argparse.ArgumentParser(description="drive every frozen ladder-1 row through the real ladder, recording")
    ap.add_argument("--manifest", required=True, help="the hardening manifest frozen before the run")
    ap.add_argument("--only", action="append", default=[], help="run only this row id (repeatable)")
    ap.add_argument("--redo", action="append", default=[], help="run this row again (repeatable)")
    ap.add_argument("--out", default=None, help="the run CSV (default: the manifest's run_csv)")
    ap.add_argument("--agent", default="ladder-run")
    ap.add_argument("--session", default=None)
    ap.add_argument("--no-record", dest="record", action="store_false",
                    help="do NOT record (the run's cassettes are what the replay grades; say why)")
    ap.add_argument("--no-extract", dest="extract", action="store_false",
                    help="hunt with extract=False: a landed PDF is bound and NOT run through GROBID/Docling "
                         "(the hunt's default extracts on the GPU; the orchestrator decides — auditor-A F12)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)

    A = _load("litkb_acceptance")
    manifest = A.load_hardening_manifest(a.manifest)
    repo = Path(manifest["repo"])
    out = Path(a.out or manifest["run_csv"])
    out = out if out.is_absolute() else repo / out
    n, resumed, rows = run_rows(
        manifest, out, db=manifest["db"], worktree=manifest.get("worktree") or str(repo),
        agent=a.agent, session=a.session or f"ladder-run-{manifest['frozen_at']}", only=a.only,
        redo=a.redo, reader_role=manifest.get("reader_role") or "litkb_reader", record=a.record,
        hunt_kwargs=None if a.extract else {"extract": False})
    pairs = {}
    for r in rows:
        k = "TRACEBACK" if r.get("traceback") == "1" else f"{r.get('state')}/{r.get('reason')}"
        pairs[k] = pairs.get(k, 0) + 1
    print(f"ran={n} resumed={resumed} rows={len(rows)} out={out}")
    print(" ".join(f"{k}={v}" for k, v in sorted(pairs.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

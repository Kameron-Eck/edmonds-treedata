"""litkb S4 — stage 6 (references) over every file that owes it, keyed by the file's own rel_path.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_references_stage.py --dry-run
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_references_stage.py --counters
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_references_stage.py [--limit N]

WHY A SECOND DRIVER. `qc/instruments/litkb_p6_references.py` is the P6 MEASUREMENT: it derives a
20-paper set from `Validation/manifest.csv` and posts ``Validation/<stem>.pdf`` (its ``extract``
builds the path from the stem), so the files bound under `_litkb_staging/` — 55 of the 233 with
blocks on 2026-09-22 — are out of its reach, and the stage-5 TEIs under ``p5/tei`` were requested
WITHOUT raw citations (`litkb_p5_bulk.py::_grobid_one` calls ``grobid.extract`` with its defaults).
Kam's ruling under the S4 block's "Test-set commands": the reference stage runs over every file
with blocks, detached. This is that driver. It forks nothing: the selector and the counters are
`litkb.extract.references_coverage` (one predicate for both), GROBID is `litkb.extract.grobid`,
the parse and resolution are `litkb.extract.references.process_tei` with the P6 instrument's own
client + pacer + disk cache (`litkb_p6_references.py::make_client`) and corpus index sources
(`MANIFEST`, `BIBLIOS`), the artifact write is the P5 driver's atomic write + sha256 sidecar
(`litkb_p5_bulk.py::_write_atomic` / `_artifact_ok`), and the ingest is
`litkb.extract.references_ingest.ingest_paper` — one transaction per paper, idempotent per run key,
a killed carcass cleared by its existing path.

KEYED BY rel_path, NEVER BY A KEY. Each file is read at ``<literature root>/<main_files.rel_path>``
of its CURRENT version — the path litkb has, never one composed from a work key or a stem (several
keys are truncated against their own file stems; plan "### S4"). The citing stem stage 6 labels
its rows with is that path's stem, and the ingest is handed THIS file's entry under it (route
``rel-path``), so a stem two files share can never file one paper's references under the other.

RESUMABLE. A rerun asks `references_coverage.pending_files` again; a file whose ok stage-6 run at
the current key committed is not selected. TEIs are cached as ``<derived>/tei/<sha256>.tei.xml``
with a ``.sha256`` sidecar — an artifact whose bytes no longer hash to the sidecar is a killed
writer's leftovers and is redone — and registry answers come from the P6 disk cache (200/404
only), so a resumed run repeats neither GROBID nor the wire for the files it already reached.

DETACHED-FRIENDLY. One JSON line per file is APPENDED to ``<derived>/driver_progress.jsonl``
(`--progress` overrides): rel_path, file_id, sha256, status (ok / already / error), tei
(cached / grobid), seconds, references, resolved, anchored, citation_edges, error. The last line
of a batch is ``{"summary": …}``, the S4 counters included. A session advisory lock
(:data:`DRIVER_LOCK`) keeps a second driver off the same database while one runs; it dies with
the connection, so a killed driver leaves nothing to clean up.

GROBID IS HELD, NEVER STOLEN. The service is started only when a file actually needs a TEI
(nothing on disk), the WSL distro is held for the batch (`grobid.hold_distro`), and at the end it
is stopped ONLY if this driver's own start action launched it: `hunt` stops GROBID after every
file (its ``_finish`` path), and a queue worker may be using the same service at the same time, so
stopping a GROBID someone else brought up would fail their request mid-flight. Ownership comes from
systemd's unit state and the launch's own output, never from a health probe (`GrobidHold`).

THE NETWORK. A real run resolves over Crossref / Semantic Scholar / arXiv at the registries' own
pacing (1 s Crossref) — the wall-clock spend the plan marks as Kam's and Kam ruled on
(2026-09-22). `--dry-run` and `--counters` connect as ``litkb_reader``, touch neither GROBID nor
the wire, and write nothing anywhere.
"""
import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: `pg_try_advisory_lock` key for "a stage-6 driver is running on this database": "lkr6".
#: Distinct from the suite lock (qc/conftest.py `_LITKB_SUITE_LOCK`, "lkts") and the migration
#: lock (`litkb.db.migrate`, "litk"), so it never waits on either.
DRIVER_LOCK = 0x6C6B7236

#: The route word the ingest records on the run's metrics for a paper handed over by rel_path
#: (`references_ingest.held_index` records `file-stem` / `works.key` for the routes it resolves).
ROUTE = "rel-path"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return sys.modules[name]


def _p6():
    return _load("litkb_p6_references")


def _p5():
    return _load("litkb_p5_bulk")


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stem_of(rel_path):
    """The citing stem: the rel_path's own stem, by the loader's one rule (`references_ingest._stem_of`)."""
    from litkb.extract import references_ingest as RI

    return RI._stem_of(rel_path)


def rel_dir(rel_path):
    """The directory a rel_path lives in, for the per-directory split: ``Validation`` or
    ``_litkb_staging/<sub>``."""
    parts = str(rel_path).replace("\\", "/").split("/")
    if parts[0] == "_litkb_staging" and len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0] if len(parts) > 1 else "."


def stage5_origin(artifact_path):
    """Which stage-5 driver made the current run: the directory under ``litkb_derived``
    (``p5`` = the bulk pass, ``hunt`` = `litkb hunt`), or ``?``."""
    parts = str(artifact_path or "").replace("\\", "/").split("/")
    return parts[parts.index("litkb_derived") + 1] if "litkb_derived" in parts[:-1] else "?"


class GrobidUnavailable(RuntimeError):
    """GROBID could not be brought up for a file that needs a TEI. The batch stops: every later
    file would wait out the same start timeout for the same answer."""


class GrobidHold:
    """The service for one batch: started on first need, and stopped at the end ONLY if THIS
    driver's own start action launched it (module header). The callables default to
    `litkb.extract.grobid`'s; a test passes its own.

    OWNERSHIP IS NEVER INFERRED FROM A HEALTH PROBE (S4 run 3 audit of D1, fix 4). `health()` is a
    5 s GET of ``/api/isalive``; a GROBID another worker started and is keeping busy can miss it.
    Reading that miss as "down" and calling `grobid.start()` would be doubly wrong: `grobid.sh
    start` itself re-probes and, on a miss, runs ``systemctl restart grobid`` — killing the other
    worker's requests — and the driver would then think it owned the service and stop it at the
    end. So on a failed probe the driver asks SYSTEMD (`grobid.sh status` -> ``systemctl
    is-active grobid``): a unit that is ``active``/``activating`` belongs to someone else and is
    only waited for, never started. Only when the unit is not running does the driver launch, and
    it takes ownership only if that launch's own output says IT brought the service up
    (``alive after Ns``, `grobid.sh`'s ``do_start``); ``already alive`` (a race another starter
    won) or anything unreadable leaves ``started_here`` False. In doubt, it never stops.
    """

    #: `systemctl is-active` words that mean the unit is running or coming up under someone.
    RUNNING = ("active", "activating", "reloading")

    def __init__(self, url=None, *, health=None, unit_state=None, launch=None, stop=None,
                 process=None, hold=None, wait=240, poll=2.0, sleep=None):
        import time as _time

        from litkb.extract import grobid as G

        self.url = url or G.DEFAULT_URL
        self._hold = hold or G.hold_distro
        self._health = health or G.health
        self._unit_state = unit_state or _unit_state
        self._launch = launch or _launch
        self._stop = stop or G.stop
        self._process = process or G.process_pdf
        self._sleep = sleep or _time.sleep
        self.wait, self.poll = wait, poll
        self.started_here = False
        self.stopped = False

    def _wait_alive(self):
        waited = 0.0
        while waited < self.wait:
            if self._health(self.url):
                return True
            self._sleep(self.poll)
            waited += self.poll
        return self._health(self.url)

    def ensure(self):
        # Hold the WSL distro for as long as this process lives, EVEN when someone else's GROBID
        # is already up: their wsl.exe client may exit mid-batch, and the distro goes with it
        # (`grobid.hold_distro`, measured 2026-09-14). Idempotent; released at interpreter exit.
        self._hold()
        if self._health(self.url):
            return True
        # BEGIN guard: a running GROBID unit someone else started is waited for, never started
        if (self._unit_state() or "").strip().lower() in self.RUNNING:
            if self._wait_alive():
                return True
            raise GrobidUnavailable(f"the GROBID unit is running but {self.url} did not answer "
                                    f"within {self.wait}s; not restarting a service this driver "
                                    "did not start")
        # END guard: a running GROBID unit someone else started is waited for, never started
        ok, launched = self._launch()
        self.started_here = bool(ok and launched)
        if not (ok and self._wait_alive()):
            raise GrobidUnavailable(f"GROBID did not come up at {self.url} within {self.wait}s")
        return True

    def tei(self, pdf_path):
        self.ensure()
        return self._process(str(pdf_path), url=self.url, include_raw_citations=True)

    def close(self):
        # BEGIN guard: the stage-6 driver never stops a GROBID it did not start
        if self.started_here and not self.stopped:
            self._stop()
            self.stopped = True
        # END guard: the stage-6 driver never stops a GROBID it did not start


def _unit_state():
    """`grobid.sh status`'s first line: ``systemctl is-active grobid`` (active / inactive / failed
    / activating …). '' when it cannot be read — which `ensure` treats as NOT running, and the
    launch that follows then decides ownership from its own output."""
    from litkb.extract import grobid as G

    try:
        r = G._manager("status", timeout=60)
    except Exception:  # noqa: BLE001 - an unreadable state is "unknown", never "someone else's"
        return ""
    return ((r.stdout or "").strip().splitlines() or [""])[0]


def _launch():
    """`grobid.sh start` -> (ok, launched_here). ``launched_here`` is True only when the script
    itself brought the service up (``alive after Ns``); ``already alive`` is someone else's."""
    from litkb.extract import grobid as G

    G.hold_distro()
    r = G._manager("start")
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, "alive after" in out


def _sha256(path):
    return _p5()._sha256_file(str(path))


def _tei_for(row, path, derived, grobid):
    """-> (tei bytes, 'cached' | 'grobid'). The cache is keyed by the file ROW's sha256."""
    p5 = _p5()
    tei_path = os.path.join(derived, "tei", f"{row['sha256']}.tei.xml")
    if p5._artifact_ok(tei_path):
        with open(tei_path, "rb") as fh:
            return fh.read(), "cached", tei_path
    # BEGIN guard: the stage-6 driver posts only the bytes its file row names
    if _sha256(path) != row["sha256"]:
        raise _FileRefused("sha-mismatch", f"{row['rel_path']} on disk does not hash to the file row's "
                                           f"sha256 {row['sha256'][:12]}")
    # END guard: the stage-6 driver posts only the bytes its file row names
    tei = grobid.tei(path)
    p5._write_atomic(tei_path, tei, mode="wb")
    return tei, "grobid", tei_path


class _FileRefused(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _park(derived, sha, res):
    """Stage 6's own DB-free output for this file, under ``<derived>/files/<sha256>/`` — the four
    artifact names `references_ingest.ARTIFACTS` reads, so `references_ingest.load` can replay it."""
    from litkb.extract import references as R
    from litkb.extract import references_ingest as RI

    d = os.path.join(derived, "files", sha)
    for key in ("references", "citation_mentions", "edges", "candidates"):
        R.write_jsonl(res[key], os.path.join(d, RI.ARTIFACTS[key]))
    return d


def _anchor_counts(conn, run_id):
    row = conn.execute(
        "SELECT count(*) FILTER (WHERE resolution = 'resolved'), "
        "       count(*) FILTER (WHERE resolved_work_id IS NOT NULL) "
        'FROM litkb."references" WHERE run_id = %s', (run_id,)).fetchone()
    return {"resolved": row[0], "anchored": row[1]}


def run_file(conn, row, *, root, derived, grobid, client, pacer, breaker, corpus_index, held, dois,
             host="local"):
    """One file: TEI -> parse + resolve -> park -> ingest. -> the progress line (no exception
    escapes for a refusal of THIS file; `GrobidUnavailable` does, because it ends the batch)."""
    from litkb.extract import references as R
    from litkb.extract import references_ingest as RI

    t0 = time.monotonic()
    line = {"at": _now(), "rel_path": row["rel_path"], "file_id": str(row["file_id"]),
            "sha256": row["sha256"], "status": "error", "tei": None, "seconds": None,
            "references": None, "resolved": None, "anchored": None, "citation_edges": None,
            "error": None}
    try:
        path = Path(root) / str(row["rel_path"]).replace("/", os.sep)
        if not path.exists():
            raise _FileRefused("file-missing", f"no file at {path}")
        from litkb.extract.grobid import GrobidError
        try:
            tei, line["tei"], tei_path = _tei_for(row, path, derived, grobid)
        except GrobidError as e:
            raise _FileRefused("grobid", f"{type(e).__name__}: {e}"[:300]) from e
        stem = stem_of(row["rel_path"])
        res = R.process_tei(tei, stem, client, pacer, index=corpus_index, resolve=True,
                            breaker=breaker)
        _park(derived, row["sha256"], res)
        paper = {"stem": stem, "references": res["references"],
                 "mentions": res["citation_mentions"], "edges": res["edges"],
                 "candidates": res["candidates"],
                 "log": {"stem": stem, "status": line["tei"], "rel_path": row["rel_path"],
                         "bytes": len(tei), "sha256": row["sha256"]}}
        index = dict(held)
        # BEGIN guard: the citing stem names THIS file, never another file sharing the stem
        index[stem] = {"work_id": row["work_id"], "file_id": row["file_id"], "route": ROUTE,
                       "rel_path": row["rel_path"]}
        # END guard: the citing stem names THIS file, never another file sharing the stem
        out = RI.ingest_paper(conn, paper, index, dois, artifact_path=tei_path, host=host)
        line.update(status="ok" if out["inserted"] else "already",
                    references=out["references"], citation_edges=out["citation_edges"],
                    **_anchor_counts(conn, out["run_id"]))
    except GrobidUnavailable:
        raise
    except _FileRefused as e:
        line["error"] = f"{e.code}: {e}"
    except Exception as e:  # noqa: BLE001 - one paper's failure is a row, never the batch's end
        line["error"] = f"{type(e).__name__}: {e}"[:400]
    line["seconds"] = round(time.monotonic() - t0, 2)
    return line


def _append(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, sort_keys=True, default=str) + "\n")
        fh.flush()


def take_lock(conn):
    return bool(conn.execute("SELECT pg_try_advisory_lock(%s)", (DRIVER_LOCK,)).fetchone()[0])


def run(conn, *, root, derived, progress, grobid=None, client=None, pacer=None, corpus_index=None,
        limit=None, only=None, host="local", _after_file=None, echo=print):
    """The batch. `conn` is an ingest connection (`references_ingest.connect`). -> the summary."""
    from litkb.extract import references as R
    from litkb.extract import references_coverage as RC
    from litkb.extract import references_ingest as RI

    # BEGIN guard: one stage-6 driver per database at a time
    if not take_lock(conn):
        raise SystemExit("another stage-6 driver holds the lock on this database "
                         f"(pg advisory lock {DRIVER_LOCK:#x}); wait for it or stop it")
    # END guard: one stage-6 driver per database at a time
    # `pacer=None` with a client is a legitimate pair (a test's stub needs no pacing): only a
    # MISSING client means "the real one", and then the real pacer comes with it.
    if client is None:
        client, pacer = _p6().make_client()
    if corpus_index is None:
        p6 = _p6()
        corpus_index = R.corpus_index([str(p6.MANIFEST)] + [str(p) for p in p6.BIBLIOS])
    grobid = grobid or GrobidHold()
    breaker = R.StageBreaker()
    rows = RC.pending_files(conn)
    if only:
        rows = [r for r in rows if r["rel_path"] in set(only)]
    if limit is not None:
        rows = rows[:int(limit)]
    held, dois = RI.held_index(conn), RI.doi_index(conn)
    tally = collections.Counter()
    t0, aborted = time.monotonic(), None
    try:
        for i, row in enumerate(rows, 1):
            try:
                line = run_file(conn, row, root=root, derived=derived, grobid=grobid, client=client,
                                pacer=pacer, breaker=breaker, corpus_index=corpus_index, held=held,
                                dois=dois, host=host)
            except GrobidUnavailable as e:
                aborted = f"grobid-unavailable: {e}"
                _append(progress, {"at": _now(), "rel_path": row["rel_path"], "status": "aborted",
                                   "error": aborted})
                break
            _append(progress, line)
            tally[line["status"]] += 1
            for k in ("references", "resolved", "anchored", "citation_edges"):
                tally[k] += line[k] or 0
            echo(f"[{i}/{len(rows)}] {line['status']:7s} {line['seconds']:>7}s "
                 f"refs={line['references']} anchored={line['anchored']} {line['rel_path']}"
                 + (f"  ERROR {line['error']}" if line["error"] else ""))
            if _after_file is not None:
                _after_file(i, line)
    finally:
        grobid.close()
    summary = {"at": _now(), "selected": len(rows), "files": dict(tally),
               "seconds": round(time.monotonic() - t0, 1), "aborted": aborted,
               "grobid_started_here": grobid.started_here, "grobid_stopped": grobid.stopped,
               "stages_tripped": breaker.report(),
               "network_calls": getattr(client, "network_calls", None),
               "counters": RC.reference_counters(conn)}
    _append(progress, {"summary": summary})
    return summary


def dry_run(conn, *, derived):
    """-> {"count", "by_dir", "by_origin", "tei_cached", "rows"} — read-only, no GROBID, no wire."""
    from litkb.extract import references_coverage as RC

    rows = RC.pending_files(conn)
    p5 = _p5()
    cached = [r for r in rows if p5._artifact_ok(os.path.join(derived, "tei", f"{r['sha256']}.tei.xml"))]
    return {"count": len(rows),
            "by_dir": dict(sorted(collections.Counter(rel_dir(r["rel_path"]) for r in rows).items())),
            "by_origin": dict(sorted(collections.Counter(stage5_origin(r["stage5_artifact"])
                                                         for r in rows).items())),
            "tei_cached": len(cached), "rows": rows}


def _reader(db):
    from litkb.db import connect as c

    return c.connect(db, "litkb_reader", autocommit=True)


def main(argv=None):
    from litkb.acquire.store import LITERATURE_ROOT
    from litkb.db import connect as c
    from litkb.extract import references_coverage as RC

    ap = argparse.ArgumentParser(description="stage 6 over every file that owes it, by rel_path")
    ap.add_argument("--db", default=c.DB_MAIN)
    ap.add_argument("--dry-run", action="store_true",
                    help="list the files a run would take (read-only, as litkb_reader)")
    ap.add_argument("--counters", action="store_true",
                    help="print files_without_reference_stage and the anchor rate (read-only)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", action="append", default=None, metavar="REL_PATH",
                    help="run only this rel_path (repeatable; still only if it owes stage 6)")
    ap.add_argument("--root", default=str(LITERATURE_ROOT), help="the literature root")
    ap.add_argument("--derived", default=None, help="the p6 derived directory (default: P6's)")
    ap.add_argument("--progress", default=None,
                    help="progress JSONL (default <derived>/driver_progress.jsonl)")
    ap.add_argument("--list", action="store_true", help="with --dry-run: print every rel_path")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    derived = a.derived or str(_p6().OUT)
    if a.dry_run or a.counters:
        conn = _reader(a.db)
        try:
            if a.dry_run:
                d = dry_run(conn, derived=derived)
                print(f"would run: {d['count']} files  by_dir={json.dumps(d['by_dir'])}  "
                      f"by_stage5_origin={json.dumps(d['by_origin'])}  tei_cached={d['tei_cached']}")
                if a.list:
                    for r in d["rows"]:
                        print(f"  {r['rel_path']}")
            print(RC.format_counters(RC.reference_counters(conn)))
        finally:
            conn.close()
        return 0
    from litkb.extract import references_ingest as RI

    conn = RI.connect(a.db)
    try:
        s = run(conn, root=a.root, derived=derived, limit=a.limit, only=a.only,
                progress=a.progress or os.path.join(derived, "driver_progress.jsonl"))
    finally:
        conn.close()
    print(json.dumps({k: v for k, v in s.items() if k != "counters"}, default=str, sort_keys=True))
    print(RC.format_counters(s["counters"]))
    return 2 if s["aborted"] else (1 if s["files"].get("error") else 0)


if __name__ == "__main__":
    raise SystemExit(main())

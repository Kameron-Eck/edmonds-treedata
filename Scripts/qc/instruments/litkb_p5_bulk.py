"""P5 — the local bulk pass: the whole corpus through stages 0/2/3/5 and into ``litkb``.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p5_bulk.py plan
    ...                                                                      grobid
    ...                                                                      docling
    ...                                                                      ingest
    ...                                                                      gate

Five stages, each **resumable and idempotent by (file sha256, pipeline version)**, each
keyed by sha256 and never by path — a corpus with six duplicate-sha256 groups has fewer
DOCUMENTS than files, and keying on the path would extract the same bytes twice and then
ingest two runs against one ``files`` row.

WHAT THIS IS NOT. Design §12.3-§12.5's ``extraction_jobs`` table, its leased worker and the
sweep are **NOT BUILT**, and this instrument does not build them. The checkpoint here is a
local artifact-plus-sidecar on disk: a stage is resumable because a finished artifact is on
disk with a sha256 beside it, and re-running skips it. That covers §14 P5's kill (a) — a
worker killed mid-file resumes with no duplicate blocks, which the database's own
``clear_extraction_rows`` enforces inside the resuming transaction — and it does NOT cover
kills (c) and (d), which are about two workers leasing one job. Those stay NOT EXERCISED.

THE PIPELINE VERSION. ``reconcile.PIPELINE_VERSION`` names what RECONCILIATION produces and
is unchanged. This pass produces something else: reconciliation PLUS the L4 formula LaTeX
attached to its equation blocks, so a run made here holds rows a plain stage5-2 ingest does
not. It therefore carries its own identity, :data:`P5_PIPELINE_VERSION`, passed to
``ingest_file``. Sharing stage5-2's key would let a file ingested without LaTeX be skipped as
already-done and keep blocks with a NULL ``latex`` for ever — the same trap the stage-5
report's fix 9 describes, one version later.
"""
import argparse
import concurrent.futures
import csv
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

from litkb.extract import docling as D  # noqa: E402
from litkb.extract import grobid as G  # noqa: E402
from litkb.extract import inventory as I  # noqa: E402
from litkb.extract import reconcile as R  # noqa: E402


def reconcile_version():
    """The reconciler's own version string, READ rather than copied (CLAUDE.md §3.3)."""
    return R.PIPELINE_VERSION

#: Derived artifacts live OUTSIDE the repository (they are ~1 GB of tool output).
DERIVED = os.environ.get("LITKB_P5_DERIVED", r"D:\edmonds-pipeline\litkb_derived\p5")
TEI_DIR = os.path.join(DERIVED, "tei")
DOC_DIR = os.path.join(DERIVED, "docling")
CENSUS_JSONL = os.path.join(DERIVED, "inventory_census.jsonl")
#: Stage-0 records for the active files the FROZEN census does not name. Kept in their own
#: file so a census number can never be read off a set the census did not measure.
EXTRA_JSONL = os.path.join(DERIVED, "inventory_extra.jsonl")
PLAN_JSON = os.path.join(DERIVED, "plan.json")
ROWS_CSV = os.path.join(DERIVED, "p5_files.csv")
GROBID_METRICS = os.path.join(DERIVED, "metrics_grobid.jsonl")
DOCLING_METRICS = os.path.join(DERIVED, "metrics_docling.jsonl")
STAGE_LOG = os.path.join(DERIVED, "stage_log.jsonl")

#: The full-corpus L4 pass. `ok` rows only — `unstable` and `degenerate` live in the verify
#: queue beside it and are NEVER attached as text (LITKB_COLAB_L4_FULLPASS_2026-09-16 §4).
LATEX_JSONL = os.environ.get(
    "LITKB_P5_LATEX", r"D:\edmonds-pipeline\litkb_derived\formula\latex_formula_colab_full.jsonl")
VERIFY_JSONL = os.environ.get(
    "LITKB_P5_VERIFY",
    r"D:\edmonds-pipeline\litkb_derived\formula\latex_formula_colab_full_verify_queue.jsonl")

#: Docling on the T2000. `formulas=off` here on purpose: the formula LaTeX comes from the L4
#: pass, and running CodeFormula on this card measured 178 MiB of headroom (DOCLING_LOCAL §8.3).
CUDA_PY = os.environ.get("LITKB_P5_DOCLING_PY",
                         r"D:\edmonds-pipeline\venv-docling-cuda\Scripts\python.exe")

#: One label for the whole corpus, and it is the RECONCILER's own
#: (``reconcile.PIPELINE_VERSION``). It used to be a different string ("stage5-2+l4latex"),
#: because a run made here holds LaTeX rows a plain reconcile ingest does not and sharing the key
#: would let a file ingested without LaTeX be skipped as already-done. The collision is still
#: real and is still refused — but by the PARAMS, not by the version: :data:`P5_PARAMS` goes into
#: ``ingest.params_hash``, which is part of the run key. That buys back the thing the two labels
#: cost, which the final referee named (§4, "the pipeline_version label is mixed (224 vs 5) while
#: the effect is not… a P9 reproducibility pass will have to read two labels for one corpus"):
#: one corpus, one label, and a run key that still tells the two extractions apart.
P5_PIPELINE_VERSION = reconcile_version()

#: What makes this pass a different EXTRACTION of a file from a bare stage-5 reconcile: the L4
#: formula LaTeX, and the word this pass puts on every equation for how far it can be trusted.
#:
#: ``merge_rule`` is the third, and it is here because of something that happened on 2026-09-16
#: rather than because it was designed in. The first stage5-3 ingest ran with a canonical merge
#: that grouped a page's readings into CONNECTED COMPONENTS; containment is not transitive, so on
#: a page where a large block nests several small ones the whole page chained into one group and
#: merged nothing. 213 documents were written that way before migration 0022's trigger stopped
#: the run on Angelopoulos_2022 p7, where 21 exact-duplicate rectangles survived. The rule is now
#: pairwise and greedy. An ``ok`` run's rows cannot be deleted by anyone — that is the design, and
#: it is what protects evidence that cites them — so the repaired ingest has to be a DIFFERENT
#: run, and ``params_hash`` is the field that says which reconciliation a run is: exactly the
#: distinction its docstring names ("a run made at IOU_MATCH 0.5 and one made at 0.6 are
#: different extractions of the same file"). The 213 are superseded, not lost; the corpus label
#: stays `stage5-3` for both.
#: ``merge_rule`` moved once more, in the same campaign and for the same reason: the first
#: pairwise corpus kept the SMALLER of two boxes, and coverage — which asks which of a page's
#: characters lie inside some canonical block — fell on 52 of 229 documents, Guo_2018 from 0.9913
#: to 0.4098. The merged block's box is now the UNION of the two, and an over-merge is dropped
#: only when the characters inside it are held by blocks that are staying. Third value, third set
#: of runs; the two earlier ones are superseded and their rows stand.
P5_PARAMS = {"latex_source": "codeformula-l4", "latex_status": "0022",
             "merge_rule": "pairwise-union-charcover"}

#: Routes GROBID is offered. A scan has no text layer, so GROBID refuses it outright; posting
#: one costs a minute of pdfalto and returns HTTP 500 (stage 5 report §5).
GROBID_ROUTES = ("native", "mixed", "cover-sheet")

#: The bbox join tolerance, in points. `merge_formula_latex` rounds boxes to 1 pt for the same
#: join, so this is that rule at the same grain rather than a second one.
BBOX_TOL = float(os.environ.get("LITKB_P5_BBOX_TOL", "2.0"))

ROW_FIELDS = [
    "sha256", "name", "relpath", "route", "pages", "ocr_pages", "file_id", "work_id",
    "tei", "docling", "blocks", "matched", "disagreements", "figures", "tables",
    "equations", "latex_attached", "latex_rows_for_file", "latex_unmatched",
    "latex_stable", "latex_contaminated", "latex_unstable", "latex_degenerate",
    "latex_unverified",
    "coverage_by_page_type", "coverage_min_share", "coverage_failures",
    "grobid_seconds", "docling_seconds", "reconcile_seconds", "ingest_seconds",
    "run_id", "inserted", "status", "note",
]


# ── small helpers ──────────────────────────────────────────────────────────────────────────

def _sha256_file(path, chunk=1 << 20):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _write_atomic(path, data, mode="w"):
    """`.partial` -> fsync -> rename, then a `.sha256` sidecar. CLAUDE.md §3.9.

    The sidecar is what makes "resumable" checkable rather than assumed: an artifact whose
    bytes do not hash to its sidecar is a killed writer's leftovers and is redone.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".partial"
    kw = {} if "b" in mode else {"encoding": "utf-8", "newline": "\n"}
    with open(tmp, mode, **kw) as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    digest = _sha256_file(path)
    with open(path + ".sha256", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(digest + "\n")
    return digest


def _artifact_ok(path):
    """True when the artifact is on disk AND its bytes still hash to its sidecar."""
    side = path + ".sha256"
    if not (os.path.exists(path) and os.path.exists(side)):
        return False
    with open(side, encoding="utf-8") as fh:
        want = fh.read().strip()
    return bool(want) and _sha256_file(path) == want


def _log(stage, **kw):
    os.makedirs(DERIVED, exist_ok=True)
    kw["stage"] = stage
    kw["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(STAGE_LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(kw, sort_keys=True) + "\n")


def load_plan():
    with open(PLAN_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def census_records():
    """The stage-0 record for every planned document, keyed by sha256 (first path wins)."""
    recs = {}
    for path in (CENSUS_JSONL, EXTRA_JSONL):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                recs.setdefault(r["sha256"], r)
    return recs


# ── stage: plan ────────────────────────────────────────────────────────────────────────────

def cmd_plan(a):
    """The population to extract, and its stage-0 routing. Writes plan.json.

    THE POPULATION IS ``litkb.main_files``, NOT THE CENSUS. §14 P5's gate reads "every ACTIVE
    FILE has a current run with pages and blocks", and an active file is a row in the
    database, not a PDF on disk. The two sets are close and not equal, measured here:

    * the frozen stage-0 census names 241 files (232 distinct sha256). Its routing is the
      pinned measurement and is used verbatim wherever it names a file;
    * a corpus PDF the census names but litkb has never admitted is **skipped and listed** —
      it has no ``files`` row, so there is nothing to attach a run to;
    * an active file the census does NOT name (admitted after the census was frozen, or under
      a path the census walk did not reach) is probed here with the same stage-0 prober. Its
      routing is measured the same way; it is simply not part of the pinned census numbers,
      and ``in_census`` records which is which so no reader mixes them.
    """
    import collections

    t0 = time.monotonic()
    records, seconds = I.run_census(CENSUS_JSONL, force=a.force, progress=not a.quiet)
    census = I.load_census()
    assert {s for s, _ in census} == {r["sha256"] for r in records}, \
        "the probed set is not the frozen census"
    print(f"census: {len(records)} files, {sum(r['pages'] for r in records)} pages, "
          f"{seconds:.1f}s")

    import psycopg
    conn = psycopg.connect(f"host=localhost port=5433 dbname={a.db} user=litkb_reader",
                           autocommit=True)
    active = {r[0]: {"file_id": str(r[1]), "work_id": str(r[2]), "rel_path": r[3],
                     "status": r[4], "pages_db": r[5], "in_main": True}
              for r in conn.execute(
                  "SELECT sha256, file_id, work_id, rel_path, status, pages "
                  "FROM litkb.main_files WHERE status = 'active'").fetchall()}
    # BEGIN guard: a named workstream's own proposed files are planned too
    # R-3's second hole: 14 acquired, bound PDFs sit in OPEN workstreams, which is OUTSIDE
    # main's view and therefore outside this population — so the bulk pass never saw them, and
    # through litkb_search they are indistinguishable from "not held". `ws_files` is the
    # workstream's own view (its proposals on top of main), so the union is scoped to the ONE
    # workstream the caller names; no other workstream's proposals are touched.
    proposed = 0
    if getattr(a, "workstream", None):
        ws = conn.execute("SELECT id::text FROM litkb.workstreams WHERE slug = %s",
                          (a.workstream,)).fetchone()
        if not ws:
            raise SystemExit(f"no workstream {a.workstream!r} in {a.db}")
        for r in conn.execute(
                "SELECT sha256, file_id, work_id, rel_path, status, pages "
                "FROM litkb.ws_files WHERE view_workstream_id = %s AND status = 'active'",
                (ws[0],)).fetchall():
            if r[0] in active:
                continue
            active[r[0]] = {"file_id": str(r[1]), "work_id": str(r[2]), "rel_path": r[3],
                            "status": r[4], "pages_db": r[5], "in_main": False}
            proposed += 1
        print(f"workstream {a.workstream}: {proposed} active files main does not hold yet")
    # END guard: a named workstream's own proposed files are planned too
    conn.close()

    by_sha = collections.OrderedDict()
    for r in sorted(records, key=lambda x: x["path"]):
        by_sha.setdefault(r["sha256"], []).append(r)

    rows, skipped, extra = [], [], []
    for sha, group in by_sha.items():
        rec = group[0]
        b = active.get(sha)
        row = {
            "sha256": sha, "name": rec["name"], "path": rec["path"],
            "copies": [g["name"] for g in group], "route": rec["route"],
            "pages": rec["pages"], "ocr_pages": rec.get("ocr_pages") or [],
            "in_census": True,
            "file_id": b["file_id"] if b else None,
            "work_id": b["work_id"] if b else None,
            "rel_path": b["rel_path"] if b else None,
            # False for a file only the named workstream proposes: its blocks are real and
            # ingested, and they stay invisible to litkb_search until Kam merges the branch.
            "in_main": bool(b and b.get("in_main")),
        }
        (rows if b else skipped).append(row)

    # Active files the frozen census does not name: probed with the same stage-0 prober.
    root = str(I.DEFAULT_ROOT)
    for sha, b in sorted(active.items(), key=lambda kv: kv[1]["rel_path"]):
        if sha in by_sha:
            continue
        p = os.path.join(root, b["rel_path"].replace("/", os.sep))
        if not os.path.exists(p):
            skipped.append({"sha256": sha, "name": os.path.basename(b["rel_path"]),
                            "path": p, "route": None, "pages": b["pages_db"],
                            "ocr_pages": [], "in_census": False, "file_id": b["file_id"],
                            "work_id": b["work_id"], "rel_path": b["rel_path"],
                            "note": "active in litkb, no file at its rel_path"})
            continue
        rec = I.probe_file(p)
        if rec["sha256"] != sha:
            skipped.append({"sha256": sha, "name": rec["name"], "path": p,
                            "route": rec["route"], "pages": rec["pages"], "ocr_pages": [],
                            "in_census": False, "file_id": b["file_id"],
                            "work_id": b["work_id"], "rel_path": b["rel_path"],
                            "note": f"bytes on disk hash {rec['sha256'][:12]}, "
                                    f"litkb holds {sha[:12]}"})
            continue
        extra.append(rec)
        rows.append({"sha256": sha, "name": rec["name"], "path": p, "copies": [rec["name"]],
                     "route": rec["route"], "pages": rec["pages"],
                     "ocr_pages": rec.get("ocr_pages") or [], "in_census": False,
                     "file_id": b["file_id"], "work_id": b["work_id"],
                     "rel_path": b["rel_path"], "in_main": bool(b.get("in_main"))})
    if extra:
        _write_atomic(EXTRA_JSONL, "".join(json.dumps(r, ensure_ascii=False) + "\n"
                                           for r in extra))

    dupes = {s: [g["name"] for g in gs] for s, gs in by_sha.items() if len(gs) > 1}
    plan = {
        "census_files": len(records), "census_pages": sum(r["pages"] for r in records),
        "census_documents": len(by_sha),
        "active_files_in_litkb": len(active),
        "planned": len(rows),
        "planned_from_census": sum(1 for r in rows if r["in_census"]),
        "planned_probed_here": len(extra),
        "planned_pages": sum(r["pages"] for r in rows),
        "skipped": len(skipped),
        "duplicate_groups": dupes,
        "routes": dict(collections.Counter(r["route"] for r in rows)),
        "pipeline_version": P5_PIPELINE_VERSION, "reconcile_version": R.PIPELINE_VERSION,
        "files": rows, "skipped_files": skipped,
        "planned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_atomic(PLAN_JSON, json.dumps(plan, indent=1, sort_keys=True, ensure_ascii=False))
    print(f"census documents {len(by_sha)} (from {len(records)} files; "
          f"{len(dupes)} duplicate sha256 groups)")
    print(f"active files in litkb: {len(active)}")
    print(f"PLANNED {len(rows)} documents, {plan['planned_pages']} pages "
          f"({plan['planned_from_census']} named by the census, "
          f"{len(extra)} probed here)")
    print(f"SKIPPED {len(skipped)} (a corpus PDF litkb has never admitted has no files row)")
    for s in skipped:
        print(f"  skip {s['name'][:62]:<62} ({s['route']}, {s['pages']} pp)"
              f"{'  ' + s['note'] if s.get('note') else ''}")
    print("routes (planned):", plan["routes"])
    print(f"grobid pages: {sum(r['pages'] for r in rows if r['route'] in GROBID_ROUTES)}")
    _log("plan", seconds=round(time.monotonic() - t0, 1), **{
        k: plan[k] for k in ("census_files", "census_pages", "census_documents",
                             "active_files_in_litkb", "planned", "planned_from_census",
                             "planned_probed_here", "planned_pages", "skipped")})
    return 0


# ── stage: grobid ──────────────────────────────────────────────────────────────────────────

def _tei_path(sha):
    return os.path.join(TEI_DIR, sha + ".tei.xml")


def _grobid_one(row):
    """-> (sha, status, metrics|None, error|None). Never raises: one refusal is not a batch."""
    sha, path = row["sha256"], row["path"]
    out = _tei_path(sha)
    if _artifact_ok(out):
        return sha, "cached", None, None
    try:
        tei, metrics = G.extract(path, concurrency=4, sample_rss=False)
    except G.GrobidError as e:
        m = getattr(e, "metrics", None)
        return sha, "no-tei", m, f"{type(e).__name__}: {e}"[:400]
    _write_atomic(out, tei, mode="wb")
    return sha, "ok", metrics, None


def cmd_grobid(a):
    """Stage 2 over every bound native/mixed/cover-sheet document. Scans skip GROBID."""
    plan = load_plan()
    todo = [r for r in plan["files"] if r["route"] in GROBID_ROUTES]
    if a.limit:
        todo = todo[:a.limit]
    os.makedirs(TEI_DIR, exist_ok=True)

    if not G.start(wait=300, hold=True):
        raise SystemExit("GROBID did not come up under WSL; nothing was run")
    print(f"grobid {G.version()} alive; {len(todo)} documents, "
          f"{sum(r['pages'] for r in todo)} pages, {a.workers} client threads")

    counts = {"ok": 0, "cached": 0, "no-tei": 0}
    errors = []
    # ONE cgroup sampler for the WHOLE stage. Per-file peak RSS is not a thing under a pool:
    # GROBID serves every worker from one JVM, so a per-request sampler under 4 concurrent
    # clients would report the pool's memory and label it one file's (grobid._RssSampler).
    t0 = time.monotonic()
    with G._RssSampler() as sampler:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            for n, (sha, status, metrics, err) in enumerate(
                    pool.map(_grobid_one, todo), 1):
                counts[status] = counts.get(status, 0) + 1
                if metrics:
                    metrics["client_threads"] = a.workers
                    G.append_metrics(metrics, GROBID_METRICS)
                if err:
                    errors.append((sha, err))
                if not a.quiet:
                    print(f"{n}/{len(todo)} {status:<7} {sha[:12]} "
                          f"{(metrics or {}).get('seconds', '')}")
    seconds = time.monotonic() - t0
    peak = sampler.peak
    pages = sum(r["pages"] for r in todo)
    print(f"\ngrobid stage: {counts}, {pages} pages in {seconds:.1f}s "
          f"= {pages / seconds:.2f} pages/s (pool 4, {a.workers} client threads)")
    print(f"peak service RSS (whole JVM pool + pdfalto): {peak / 1e6:.0f} MB")
    for sha, err in errors:
        print(f"  no-tei {sha[:12]}: {err.splitlines()[0][:160]}")
    _log("grobid", counts=counts, pages=pages, seconds=round(seconds, 1),
         pages_per_s=round(pages / seconds, 3), peak_rss_bytes=peak,
         client_threads=a.workers, errors=[e for _, e in errors])
    if a.stop:
        G.stop()
        G.release_distro()
        print("grobid stopped, WSL client released")
    return 0


# ── stage: docling ─────────────────────────────────────────────────────────────────────────

def _doc_path(sha):
    return os.path.join(DOC_DIR, sha + ".docling.json")


def _doc_done(sha):
    p = _doc_path(sha)
    if not _artifact_ok(p):
        return False
    try:
        D.load(p)
    except Exception:  # noqa: BLE001 — an unparseable artifact is a killed writer's leftovers
        return False
    return True


class _GpuSampler:
    """`nvidia-smi` on a loop -> peak used VRAM over a batch, in MiB."""

    def __init__(self, interval=5):
        self.interval, self._proc, self.samples = interval, None, []

    def __enter__(self):
        try:
            self._proc = subprocess.Popen(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits", "-l", str(self.interval)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            self._proc = None
        return self

    def __exit__(self, *exc):
        if self._proc is None:
            return False
        self._proc.terminate()
        try:
            out, _ = self._proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            out, _ = self._proc.communicate()
        for ln in (out or "").splitlines():
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) == 2 and parts[0].isdigit():
                self.samples.append((int(parts[0]), int(parts[1])))
        self._proc = None
        return False

    @property
    def peak(self):
        return max((u for u, _ in self.samples), default=None)

    @property
    def total(self):
        return self.samples[0][1] if self.samples else None


def _docling_batch(rows, ocr, chunk, threads, device, timeout, quiet):
    """One converter build per chunk; the worker writes one JSON per job. -> (n, seconds)."""
    pending = [r for r in rows if not _doc_done(r["sha256"])]
    if not pending:
        return 0, 0.0, 0
    t0 = time.monotonic()
    done = 0
    for i in range(0, len(pending), chunk):
        part = pending[i:i + chunk]
        jobs = [{"pdf": r["path"], "out": _doc_path(r["sha256"])} for r in part]
        rows_out = D.run(jobs, DOCLING_METRICS, python=CUDA_PY, ocr=ocr, formula=False,
                         threads=threads, device=device, timeout=timeout, cwd=DERIVED)
        for r in part:
            # The worker writes the JSON itself, so the sidecar is added here: an artifact
            # with no sidecar is indistinguishable from one a kill left half-written.
            p = _doc_path(r["sha256"])
            if os.path.exists(p) and not os.path.exists(p + ".sha256"):
                with open(p + ".sha256", "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(_sha256_file(p) + "\n")
        ok = sum(1 for r in part if _doc_done(r["sha256"]))
        done += ok
        if not quiet:
            print(f"  chunk {i // chunk + 1}: {ok}/{len(part)} converted, "
                  f"{sum(x.get('pages') or 0 for x in rows_out)} pages, "
                  f"{sum(x.get('seconds') or 0 for x in rows_out):.1f}s")
    return done, time.monotonic() - t0, len(pending)


def docling_chunk(chunk, ocr_chunk, ocr):
    """Documents per converter PROCESS for one batch — the VRAM cap that reaches the rule.

    THE knob that gets the OCR pass inside the 20 % headroom rule, and it is not the knob
    docling names for the job. Measured over P5's own batch B (see the VRAM block in
    `litkb.extract.docling`): 15 documents in one process peaks at 3,873 MiB / 94.6 %, because
    torch's caching allocator never returns a block and the reserved pool becomes a high-water
    mark over every document that process converted; 4 documents per process peaks at 2,619 MiB
    / 63.9 %, for 9.7 % of the rate in converter rebuilds. `settings.perf.page_batch_size` is
    flat across 4 / 2 / 1.

    Batch A keeps the caller's big chunk: `ocr=off` peaked at 2,317 MiB / 56.6 %, inside the
    rule already, so capping it would buy nothing and cost rate. `min` and not a bare
    `ocr_chunk`, so `--chunk 2` still means 2 on both batches."""
    # BEGIN guard: the OCR batch runs in short converter processes
    return min(chunk, ocr_chunk) if ocr else chunk
    # END guard: the OCR batch runs in short converter processes


def cmd_docling(a):
    """Stage 3 on the T2000. Two batches, never concurrent: `do_ocr` is converter-wide."""
    plan = load_plan()
    rows = plan["files"]
    if a.limit:
        rows = rows[:a.limit]
    os.makedirs(DOC_DIR, exist_ok=True)

    # Batch A, OCR off: every document whose pages already carry their own words.
    # Batch B, OCR on: the scans, and the `mixed` documents whose partial pages stage 0 put in
    # the OCR queue — except any book-sized one, which is priced per PAGE and would pay OCR on
    # hundreds of born-digital pages to reach a handful of rastered ones.
    a_rows, b_rows = [], []
    for r in rows:
        wants_ocr = r["route"] == "scan" or (r["route"] == "mixed" and r["ocr_pages"])
        if wants_ocr and r["pages"] > a.ocr_max_pages:
            r = dict(r, _ocr_skipped=True)
            a_rows.append(r)
        elif wants_ocr:
            b_rows.append(r)
        else:
            a_rows.append(r)
    big = [r for r in a_rows if r.get("_ocr_skipped")]
    print(f"batch A (ocr off): {len(a_rows)} documents, {sum(r['pages'] for r in a_rows)} pages")
    print(f"batch B (ocr on):  {len(b_rows)} documents, {sum(r['pages'] for r in b_rows)} pages")
    for r in big:
        print(f"  NOT OCR'd (over --ocr-max-pages {a.ocr_max_pages}): {r['name']} "
              f"({r['pages']} pp, {len(r['ocr_pages'])} OCR pages)")

    out = {}
    for tag, batch, ocr in (("A", a_rows, False), ("B", b_rows, True)):
        if not batch:
            continue
        chunk = docling_chunk(a.chunk, a.ocr_chunk, ocr)
        print(f"\nbatch {tag}: ocr={ocr}, device={a.device}, formulas=off, chunk={chunk}")
        with _GpuSampler() as gpu:
            n, seconds, pending = _docling_batch(batch, ocr, chunk, a.threads, a.device,
                                                 a.timeout, a.quiet)
        pages = sum(r["pages"] for r in batch)
        rate = (n and seconds) and round(pages / seconds, 3) or None
        out[tag] = {"documents": len(batch), "converted_now": n, "pending_at_start": pending,
                    "pages": pages, "seconds": round(seconds, 1), "pages_per_s_all_pages": rate,
                    "peak_vram_mib": gpu.peak, "vram_total_mib": gpu.total, "ocr": ocr,
                    "chunk": chunk}
        print(f"batch {tag}: converted {n} of {pending} pending in {seconds:.1f}s; "
              f"peak VRAM {gpu.peak} / {gpu.total} MiB")
    missing = [r["name"] for r in rows if not _doc_done(r["sha256"])]
    print(f"\ndocling: {len(rows) - len(missing)}/{len(rows)} documents have an artifact")
    for m in missing[:20]:
        print(f"  MISSING {m}")
    _log("docling", batches=out, missing=len(missing),
         not_ocred=[r["name"] for r in big])
    return 0


# ── the L4 formula LaTeX ───────────────────────────────────────────────────────────────────

def load_latex(path=None, verify=None):
    """-> ({sha256: [row, …]} for `ok` rows, {sha256: [row, …]} for the verify queue).

    `ok` rows ONLY ever reach `equations.latex`. `unstable` (the decode did not reproduce) and
    `degenerate` (a repetition loop) are read too — they carry `bbox_canonical`, so they join to
    an equation block exactly as an `ok` row does — but their STRING is never attached: writing
    either into `equations.latex` would put a decode the run itself refused to stand behind into
    a field a reader takes as the equation (referee kill R8). What they contribute is the WORD:
    an equation whose only decode was refused is `unstable`/`degenerate`, and one the pass never
    produced a row for at all is `unverified`. Before migration 0022 those two were the same
    NULL and could not be told apart.
    """
    import collections

    ok = collections.defaultdict(list)
    for line in open(path or LATEX_JSONL, encoding="utf-8"):
        r = json.loads(line)
        if r.get("status") not in (None, "ok"):
            continue
        if not (r.get("latex") or "").strip() or not r.get("bbox_canonical"):
            continue
        ok[r["file_sha256"]].append(r)
    held = collections.defaultdict(list)
    vp = verify or VERIFY_JSONL
    if os.path.exists(vp):
        for line in open(vp, encoding="utf-8"):
            r = json.loads(line)
            if r.get("bbox_canonical"):
                held[r.get("file_sha256")].append(r)
    return ok, held


# ── is the decoded string contaminated by text the crop should not have held? ───────────────

#: docling's own crop expansion, read off ``CodeFormulaVlmModel.expansion_factor`` by
#: ``formula_crop_worker._patch_recorder`` and re-stated here because this module has no docling
#: to read it from. The crop is ``bbox.expand_by_scale(0.18, 0.18)`` — each side grown by 0.18 ×
#: the box's own width/height — so the padding is PROPORTIONAL: a one-line display equation 9.8
#: points tall gets 1.8 points of margin and sees nothing, and E01's six-line derivation, 178.3
#: points tall, gets 32.1 points and sees roughly three printed lines above and below. That is
#: the whole mechanism behind the referee's contaminated class, and it is why the class exists at
#: all rather than being a model defect.
CROP_EXPANSION = float(os.environ.get("LITKB_P5_CROP_EXPANSION", "0.18"))

#: A prose run this long, found in the padding ring and NOT in the equation's own box, is text
#: the decoder read off the crop's margin. Shorter runs are the ordinary vocabulary of a formula
#: ("where", "with", "and"), which appear inside real display equations.
CONTAM_MIN_LETTERS = 8

_LATEX_PROSE = re.compile(r"\\(?:text|textrm|textit|textbf|mbox|intertext|mathrm)\s*\{([^{}]*)\}")


def crop_box(bbox, expansion=CROP_EXPANSION):
    """The rectangle CodeFormula was actually shown, from the block's own box."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    return (x0 - w * expansion, y0 - h * expansion, x1 + w * expansion, y1 + h * expansion)


def _letters(s):
    return re.sub(r"[^0-9a-z]+", "", (s or "").lower())


def latex_prose(latex):
    """The WORDS a decode emitted — what ``\\text{}`` and friends wrap, nothing else.

    Only the prose macros. A bare alphabetic run in LaTeX is as likely to be ``\\alpha`` or a
    variable name as a word, and counting those would call every equation contaminated.
    """
    out = []
    for m in _LATEX_PROSE.finditer(latex or ""):
        out.extend(w for w in re.split(r"[^0-9A-Za-z]+", m.group(1)) if w)
    return out


def latex_contamination(layer, bbox, latex, expansion=CROP_EXPANSION):
    """-> (contaminated, detail). Did the decode read words that are NOT in the equation's box?

    Measured, not argued: the padding ring is ``crop_box(bbox) minus bbox``, the characters in it
    come from the page's own native text layer, and the test is whether a run of at least
    :data:`CONTAM_MIN_LETTERS` letters that the decode wrapped in a prose macro appears in the
    RING and not in the equation's own box. Both halves matter — a ring with text in it is
    ordinary and proves nothing (a display equation nearly always has a line above it), and a
    ``\\text{where}`` that also appears inside the box is the equation's own word.

    **This says the CROP was contaminated. It does not say the mathematics is wrong**, and the
    referee's twenty draws show the difference: E03's dropped ``λ_n`` and E05's ``S^d`` for
    ``S^{d-1}`` are mathematically wrong on a clean crop, and no crop geometry can see that.
    Scoring a decode against the page is not attempted here.
    """
    from litkb.extract import reconcile as R

    crop = crop_box(bbox, expansion)
    ring, own = [], []
    for ch, x, y, _i in layer["pts"]:
        if not R._in_box(x, y, crop):
            continue
        (own if R._in_box(x, y, bbox) else ring).append(ch)
    ring_s, own_s = _letters("".join(ring)), _letters("".join(own))
    if not ring_s:
        return False, {"ring_chars": 0}
    words = [w for w in latex_prose(latex) if len(w) >= 3]
    hits = []
    for i in range(len(words)):
        run = ""
        for j in range(i, min(i + 6, len(words))):
            run += _letters(words[j])
            if len(run) >= CONTAM_MIN_LETTERS and run in ring_s and run not in own_s:
                hits.append(run)
                break
    return bool(hits), {"ring_chars": len(ring_s), "hits": hits[:3]}


def _match_crops(canonical, rows, frames, taken, tol=BBOX_TOL):
    """-> ([(block index, row)], unmatched). The bbox join, shared by the ok and the held rows.

    THE FRAME. ``bbox_canonical`` is Docling's own box through ``docling.to_canonical`` — the
    TOPLEFT sense, in the CROPBOX frame, because that is the frame Docling measures in. A
    canonical block has already been through ``to_mediabox``, so the formula box is shifted by
    the same (dx, dy) from the ONE frame reader before it is compared. A page the adapters
    refused keeps ``frame="cropbox"`` and is compared unshifted — the block never moved either.
    """
    by_page = {}
    for i, c in enumerate(canonical):
        if c.kind == "equation":
            by_page.setdefault(c.page, []).append((i, c))
    pairs, unmatched = [], []
    for r in rows:
        page = int(r["page"])
        cands = by_page.get(page) or []
        f = frames.get(page) or {}
        dx, dy = float(f.get("dx") or 0.0), float(f.get("dy") or 0.0)
        x0, y0, x1, y1 = (float(v) for v in r["bbox_canonical"])
        best, best_i = None, None
        for i, c in cands:
            if i in taken:
                continue
            sx, sy = (dx, dy) if c.frame == "mediabox" else (0.0, 0.0)
            d = max(abs(c.x0 - (x0 + sx)), abs(c.y0 - (y0 + sy)),
                    abs(c.x1 - (x1 + sx)), abs(c.y1 - (y1 + sy)))
            if best is None or d < best:
                best, best_i = d, i
        if best is not None and best <= tol:
            taken.add(best_i)
            pairs.append((best_i, r))
        else:
            unmatched.append({"page": page, "crop_id": r.get("crop_id"),
                              "nearest_pt": None if best is None else round(best, 2)})
    return pairs, unmatched


def attach_latex(canonical, rows, frames, tol=BBOX_TOL, held=(), pdf_path=None):
    """Put each `ok` LaTeX string, and a STATUS on every equation block. -> (out, n, unmatched, counts).

    Migration 0022's five words, assigned here because this is where the two halves meet — the
    equation blocks and the L4 pass's own verdicts:

      * an `ok` row whose crop's padding ring holds words the decode emitted -> ``contaminated``,
        LaTeX stored (:func:`latex_contamination`);
      * any other `ok` row -> ``stable``, LaTeX stored;
      * a row the pass itself refused -> ``unstable`` / ``degenerate``, LaTeX **not** stored;
      * an equation block with no row at all -> ``unverified``.

    ``stable`` is a statement about the pass and the crop, NEVER about the mathematics. The
    referee's E03, E05, E07, E12 and E20 are mathematically wrong on clean crops and every one of
    them comes out ``stable`` — that is a limit of what can be measured without scoring a decode
    against the page, and it is written into the column's definition rather than left to be
    discovered.
    """
    import dataclasses

    out = list(canonical)
    taken = set()
    ok_pairs, unmatched = _match_crops(out, rows, frames, taken, tol)
    held_pairs, _held_unmatched = _match_crops(out, list(held), frames, taken, tol)

    layers = {}

    def layer(page):
        if pdf_path is None:
            return None
        if page not in layers:
            from litkb.extract import reconcile as R
            try:
                layers[page] = R.native_chars(pdf_path, page, frames)
            except Exception:  # noqa: BLE001 - a page pdfium cannot read has no ring to test
                layers[page] = {"text": "", "pts": []}
        return layers[page]

    counts = {"stable": 0, "contaminated": 0, "unstable": 0, "degenerate": 0, "unverified": 0}
    for i, r in ok_pairs:
        c = out[i]
        lay = layer(c.page)
        bad, detail = (latex_contamination(lay, c.bbox, r["latex"]) if lay else (False, {}))
        status = "contaminated" if bad else "stable"
        counts[status] += 1
        out[i] = dataclasses.replace(
            c, latex=r["latex"], latex_status=status,
            extractor=dict(c.extractor, latex="codeformula-l4",
                           **({"latex_contamination": detail} if bad else {})))
    for i, r in held_pairs:
        status = "degenerate" if r.get("reason") == "degenerate" else "unstable"
        counts[status] += 1
        out[i] = dataclasses.replace(
            out[i], latex=None, latex_status=status,
            extractor=dict(out[i].extractor, latex="codeformula-l4-refused",
                           latex_refused=r.get("reason") or "unstable"))
    for i, c in enumerate(out):
        if c.kind == "equation" and c.latex_status is None:
            counts["unverified"] += 1
            out[i] = dataclasses.replace(c, latex_status="unverified")
    return out, len(ok_pairs), unmatched, counts


# ── stage: ingest ──────────────────────────────────────────────────────────────────────────

def reconcile_one(row, records, latex_by_sha, held_by_sha=None):
    """Reconcile one document and attach its LaTeX. -> (canonical, dis, stats, cov, extra)."""
    sha, pdf = row["sha256"], row["path"]
    rec = records[sha]
    tei = None
    tp = _tei_path(sha)
    if _artifact_ok(tp):
        with open(tp, "rb") as fh:
            tei = fh.read()
    doc = D.load(_doc_path(sha)) if _doc_done(sha) else None
    if tei is None and doc is None:
        raise ReconcileSkipped(f"{row['name']}: neither a TEI nor a DoclingDocument")
    t0 = time.monotonic()
    frames = I.page_frames(pdf)
    canonical, dis, stats = R.reconcile(pdf, tei, doc, rec, ocr_pages=rec.get("ocr_pages") or (),
                                        frames=frames)
    rows = latex_by_sha.get(sha) or []
    held = (held_by_sha or {}).get(sha) or []
    canonical, attached, unmatched, statuses = attach_latex(
        canonical, rows, frames, held=held, pdf_path=pdf)
    classes = {i + 1: d.get("scan", "unknown")
               for i, d in enumerate(rec.get("page_detail") or [])}
    cov = R.coverage(pdf, canonical, classes, frames=frames)
    extra = {"tei": tei is not None, "docling": doc is not None,
             "latex_attached": attached, "latex_rows_for_file": len(rows),
             "latex_unmatched": len(unmatched),
             "latex_stable": statuses["stable"], "latex_contaminated": statuses["contaminated"],
             "latex_unstable": statuses["unstable"], "latex_degenerate": statuses["degenerate"],
             "latex_unverified": statuses["unverified"],
             "reconcile_seconds": round(time.monotonic() - t0, 2)}
    return canonical, dis, stats, cov, extra


class ReconcileSkipped(RuntimeError):
    pass


def ingest_one(conn, row, canonical, dis, stats, cov, hold=0.0, pipeline_version=None):
    """``hold`` is the kill harness's window, and nothing else ever sets it.

    ``ingest_file``'s ``_after_blocks`` hook fires with every block inserted and the
    transaction still OPEN — the module's own docstring calls that "where the simulated
    mid-file kill is raised". Sleeping there puts the child in exactly the state a killed
    worker is in, for long enough that an outside process can kill it THERE rather than
    somewhere the timing happened to land. It changes no row and no code path.
    """
    from litkb.extract import ingest as ing

    pages = [{"page_no": p, "page_class": r["page_class"], "native_chars": r["chars"],
              "covered_chars": r["covered"], "coverage_share": r["share"]}
             for p, r in sorted(cov.items())]
    version = pipeline_version or P5_PIPELINE_VERSION
    if hold:
        def _hold(conn_, run_id):
            print(f"IN-TRANSACTION {run_id}", flush=True)
            time.sleep(hold)
        return ing.ingest_file(conn, row["file_id"], canonical, dis, stats, pages=pages,
                               artifact_path=_doc_path(row["sha256"]), host="local",
                               pipeline_version=version, params=P5_PARAMS, _after_blocks=_hold)
    # `host` is a two-value CHECK in 0001 ('colab' | 'local'), not free text: the machine's own
    # name lives in the metrics, not in a column the schema constrains.
    return ing.ingest_file(conn, row["file_id"], canonical, dis, stats, pages=pages,
                           artifact_path=_doc_path(row["sha256"]), host="local",
                           pipeline_version=version, params=P5_PARAMS)


def cmd_ingest(a):
    """Stage 5 + the write. One transaction per document, through the litkb_ingest login."""
    from litkb import ingest as ingest_login

    plan = load_plan()
    rows = plan["files"]
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["sha256"] in want or r["name"] in want]
    if a.limit:
        rows = rows[:a.limit]
    records = census_records()
    latex_by_sha, held = load_latex()
    print(f"L4 latex: ok rows for {len(latex_by_sha)} documents; "
          f"{sum(len(v) for v in held.values())} rows held on the verify queue")

    conn = ingest_login.connect(a.db)
    out, t0 = [], time.monotonic()
    for n, row in enumerate(rows, 1):
        r = {k: "" for k in ROW_FIELDS}
        r.update({k: row.get(k) for k in ("sha256", "name", "route", "pages", "file_id",
                                          "work_id")})
        r["relpath"] = row.get("rel_path") or ""
        r["ocr_pages"] = len(row.get("ocr_pages") or [])
        try:
            canonical, dis, stats, cov, extra = reconcile_one(row, records, latex_by_sha, held)
        except ReconcileSkipped as e:
            r["status"], r["note"] = "no-artifact", str(e)[:200]
            out.append(r)
            print(f"{n}/{len(rows)} SKIP {row['name']}: {e}")
            continue
        ti = time.monotonic()
        # The marker the kill harness waits for: everything before it is reconciliation, and
        # killing there proves nothing about the database.
        print(f"INGEST-BEGIN {row['sha256']} blocks={stats['blocks']}", flush=True)
        res = ingest_one(conn, row, canonical, dis, stats, cov, hold=a.hold_in_transaction,
                         pipeline_version=getattr(a, "pipeline_version", None))
        r.update(extra)
        r.update({
            "blocks": stats["blocks"], "matched": stats["matched"],
            "disagreements": res["disagreements"],
            "figures": stats["by_kind"].get("figure", 0),
            "tables": stats["by_kind"].get("table", 0),
            "equations": stats["by_kind"].get("equation", 0),
            "coverage_by_page_type": json.dumps(
                {k: (None if v["share"] is None else round(v["share"], 4))
                 for k, v in sorted(R.coverage_by_page_type(cov).items())}),
            "coverage_min_share": min(
                [v["share"] for v in cov.values() if v["share"] is not None], default=None),
            "coverage_failures": len(R.coverage_failures(cov)),
            "run_id": str(res["run_id"]), "inserted": res["inserted"],
            "ingest_seconds": round(time.monotonic() - ti, 2),
            "status": "ok",
        })
        out.append(r)
        print(f"{n}/{len(rows)} {row['name'][:52]:<52} blocks={r['blocks']:<6} "
              f"eq={r['equations']:<5} latex={r['latex_attached']:<5} "
              f"cov_min={r['coverage_min_share']} {r['reconcile_seconds']}+"
              f"{r['ingest_seconds']}s {'NEW' if res['inserted'] else 'cached'}")
    conn.close()
    _write_rows(out, a.csv or ROWS_CSV, append=bool(a.only or a.limit))
    print(f"\ningest: {len(out)} documents in {time.monotonic() - t0:.1f}s -> "
          f"{a.csv or ROWS_CSV}")
    _log("ingest", documents=len(out), seconds=round(time.monotonic() - t0, 1),
         blocks=sum(int(r["blocks"] or 0) for r in out))
    return 0


def _write_rows(rows, path, append=False):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    have = []
    if append and os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as fh:
            have = [r for r in csv.DictReader(fh)
                    if r["sha256"] not in {x["sha256"] for x in rows}]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ROW_FIELDS)
        w.writeheader()
        w.writerows(have + [{k: r.get(k, "") for k in ROW_FIELDS} for r in rows])


# ── stage: gate ────────────────────────────────────────────────────────────────────────────

def cmd_gate(a):
    """§14 P5's gate, read from the database and from the per-file rows."""
    import psycopg

    plan = load_plan()
    with open(a.csv or ROWS_CSV, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    conn = psycopg.connect(f"host=localhost port=5433 dbname={a.db} user=litkb_reader",
                           autocommit=True)
    q = conn.execute
    counts = {
        "files": q("SELECT count(*) FROM litkb.files").fetchone()[0],
        "files_with_current_run": q(
            "SELECT count(*) FROM litkb.files WHERE current_run_id IS NOT NULL").fetchone()[0],
        "runs_ok": q("SELECT count(*) FROM litkb.extraction_runs WHERE stage = '5-reconcile' "
                     "AND status = 'ok'").fetchone()[0],
        "runs_not_ok": q("SELECT count(*) FROM litkb.extraction_runs WHERE stage = '5-reconcile' "
                         "AND status <> 'ok'").fetchone()[0],
        "pages": q("SELECT count(*) FROM litkb.pages").fetchone()[0],
        "blocks": q("SELECT count(*) FROM litkb.blocks").fetchone()[0],
        "tables": q("SELECT count(*) FROM litkb.tables").fetchone()[0],
        "table_cells": q("SELECT count(*) FROM litkb.table_cells").fetchone()[0],
        "figures": q("SELECT count(*) FROM litkb.figures").fetchone()[0],
        "equations": q("SELECT count(*) FROM litkb.equations").fetchone()[0],
        "equations_with_latex": q(
            "SELECT count(*) FROM litkb.equations WHERE latex IS NOT NULL").fetchone()[0],
        "disagreements": q("SELECT count(*) FROM litkb.extraction_disagreements").fetchone()[0],
        "blocks_outside_ok_run": q(
            "SELECT count(*) FROM litkb.blocks b JOIN litkb.extraction_runs r ON r.id = b.run_id "
            "WHERE r.status <> 'ok'").fetchone()[0],
        "duplicate_runs_per_key": q(
            "SELECT count(*) FROM (SELECT file_id, stage, tool, tool_version, params_hash, "
            "pipeline_version, count(*) c FROM litkb.extraction_runs GROUP BY 1,2,3,4,5,6 "
            "HAVING count(*) > 1) t").fetchone()[0],
    }
    for k, v in counts.items():
        print(f"{k:<28} {v}")

    ok = [r for r in rows if r["status"] == "ok"]
    below = [r for r in ok if r["coverage_min_share"] not in ("", "None")
             and float(r["coverage_min_share"]) < R.COVERAGE_FLOOR]
    print(f"\ncoverage floor {R.COVERAGE_FLOOR}: {len(below)} of {len(ok)} documents have a page "
          f"below it")
    for r in below:
        print(f"  {r['name'][:60]:<60} min share {r['coverage_min_share']} "
              f"route={r['route']} failures={r['coverage_failures']}")
    print(f"\nplanned documents: {plan['planned']}; ingested ok: {len(ok)}; "
          f"no artifact: {sum(1 for r in rows if r['status'] == 'no-artifact')}")
    conn.close()
    _log("gate", **counts)
    return 0


# ── the kill, live ─────────────────────────────────────────────────────────────────────────

def cmd_kill_test(a):
    """§14 P5 kill (a), with a REAL process kill: taskkill /F on a worker mid-file.

    The control is not another run — it is the reconciliation's own block count, which is
    deterministic for a fixed artifact pair, so "the same block count as an uninterrupted
    control run" is checkable without ingesting the file twice on purpose.

    The subject must be a document with NO ``ok`` run yet: killing a worker that is about to
    return "already ingested, wrote nothing" would prove nothing.
    """
    import psycopg

    plan = load_plan()
    ro = psycopg.connect(f"host=localhost port=5433 dbname={a.db} user=litkb_reader",
                         autocommit=True)
    done = {str(r[0]) for r in ro.execute(
        "SELECT file_id FROM litkb.extraction_runs WHERE stage = '5-reconcile' "
        "AND status = 'ok' AND pipeline_version = %s", (P5_PIPELINE_VERSION,)).fetchall()}
    cands = [r for r in plan["files"] if r["file_id"] not in done and _doc_done(r["sha256"])]
    if a.only:
        cands = [r for r in plan["files"] if r["sha256"] == a.only or r["name"] == a.only]
    if not cands:
        raise SystemExit("no document without an ok run at this pipeline version; "
                         "hold one out of the ingest stage and re-run")
    row = max(cands, key=lambda r: r["pages"])
    print(f"subject: {row['name']} ({row['pages']} pp, file_id {row['file_id']})")

    cmd = [sys.executable, os.path.abspath(__file__), "--db", a.db, "ingest",
           "--only", row["sha256"], "--csv", os.path.join(DERIVED, "_killtest.csv"),
           "--hold-in-transaction", str(a.hold)]
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1",
               PYTHONPATH=os.path.join(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__)))), "pipeline"))
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env)
    # readline(), never `for line in proc.stdout`: the iterator reads ahead in 8 KiB blocks,
    # which is how the first two attempts learned about the transaction after it had committed.
    control, run_id = None, None
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        if not a.quiet:
            print("  child:", line.rstrip()[:120])
        if line.startswith("INGEST-BEGIN"):
            control = int(line.strip().split("blocks=")[1])
        if line.startswith("IN-TRANSACTION"):
            run_id = line.split()[1]
            break
    if control is None:
        proc.wait()
        raise SystemExit("the child never reached the ingest; nothing was killed")
    print(f"  the child is INSIDE the open transaction (run {run_id}); "
          f"control block count = {control}")
    # WAIT FOR THE TRANSACTION, do not guess at it. The first attempt used a fixed 1.5 s delay
    # and the child had already COMMITTED by then: the kill landed after the work, the resume
    # found an `ok` run and returned "wrote nothing", and the run passed while proving nothing.
    # A kill that has not been shown to land mid-transaction is not a kill (CLAUDE.md §3.4c).
    # `pg_stat_activity.state` is NULL for another role's backend unless the reader is a
    # superuser or holds pg_read_all_stats, so a `state <> 'idle'` probe run as litkb_reader
    # counts ZERO however live the transaction is — measured here, and it is why the first
    # in-flight check was thrown away rather than believed. What proves the kill landed
    # mid-transaction is the child's own IN-TRANSACTION line (every block inserted, nothing
    # committed) together with the two reads below, taken while it was held there.
    backends = ro.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
                          (a.db,)).fetchone()[0]
    # SCOPED TO THIS PIPELINE VERSION'S RUNS, and that is not a detail. The question the kill
    # asks is "can a reader see any of the killed worker's blocks" — so the population is the
    # runs at the key the worker is writing. Counting every block of the FILE answers a
    # different question, and answers it wrongly the moment the file also carries a SUPERSEDED
    # run at an earlier pipeline version: on 2026-09-16 that read 1,564 committed stage5-2
    # blocks as "visible mid-transaction" and reported the kill FAILED while every property it
    # tests actually held. The same scoping applies to `total` below, for the same reason.
    inflight_blocks = (
        "SELECT count(*) FROM litkb.blocks b JOIN litkb.extraction_runs r ON r.id = b.run_id "
        "WHERE b.file_id = %s AND r.stage = '5-reconcile' AND r.pipeline_version = %s")
    uncommitted = ro.execute(inflight_blocks,
                             (row["file_id"], P5_PIPELINE_VERSION)).fetchone()[0]
    runs_mid = ro.execute(
        "SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s AND stage = '5-reconcile' "
        "AND pipeline_version = %s", (row["file_id"], P5_PIPELINE_VERSION)).fetchone()[0]
    inflight = 1 if run_id else 0
    subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True, text=True)
    rc = proc.wait(timeout=60)
    print(f"  KILLED pid {proc.pid} (exit {rc}). While it was held inside the transaction, an "
          f"independent reader saw: {uncommitted} blocks and {runs_mid} runs for this file "
          f"({backends} backends on {a.db}).")
    if not inflight:
        print("  WARNING: the child never reported IN-TRANSACTION — this kill did NOT "
              "interrupt a transaction and the result below proves nothing")

    time.sleep(2)
    after = ro.execute(
        "SELECT r.id, r.status, (SELECT count(*) FROM litkb.blocks b WHERE b.run_id = r.id) "
        "FROM litkb.extraction_runs r WHERE r.file_id = %s AND r.stage = '5-reconcile' "
        "AND r.pipeline_version = %s", (row["file_id"], P5_PIPELINE_VERSION)).fetchall()
    current = ro.execute("SELECT current_run_id FROM litkb.files WHERE id = %s",
                         (row["file_id"],)).fetchone()[0]
    print(f"  after the kill: runs {[(str(i)[:8], s, n) for i, s, n in after]}, "
          f"current_run_id {current}")

    print("  resuming …")
    r2 = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
    print("  " + "\n  ".join((r2.stdout or "").strip().splitlines()[-3:]))
    runs = ro.execute(
        "SELECT r.id, r.status, (SELECT count(*) FROM litkb.blocks b WHERE b.run_id = r.id) "
        "FROM litkb.extraction_runs r WHERE r.file_id = %s AND r.stage = '5-reconcile' "
        "AND r.pipeline_version = %s", (row["file_id"], P5_PIPELINE_VERSION)).fetchall()
    total = ro.execute(inflight_blocks, (row["file_id"], P5_PIPELINE_VERSION)).fetchone()[0]
    dup = ro.execute(
        "SELECT count(*) FROM (SELECT run_id, page_no, reading_order FROM litkb.blocks "
        "WHERE file_id = %s AND canonical GROUP BY 1,2,3 HAVING count(*) > 1) t",
        (row["file_id"],)).fetchone()[0]
    ok_runs = [r for r in runs if r[1] == "ok"]
    verdict = {
        "runs_at_this_key": len(runs),
        "ok_runs": len(ok_runs),
        "blocks_on_the_ok_run": ok_runs[0][2] if ok_runs else None,
        "control_blocks": control,
        "blocks_at_this_pipeline_version": total,
        "duplicate_page_order_groups": dup,
        "blocks_visible_to_a_reader_mid_transaction": uncommitted,
        "runs_visible_to_a_reader_mid_transaction": runs_mid,
        "seconds": round(time.monotonic() - t0, 1),
    }
    for k, v in verdict.items():
        print(f"  {k:<32} {v}")
    verdict["child_confirmed_in_transaction"] = bool(inflight)
    passed = (bool(inflight) and uncommitted == 0 and len(ok_runs) == 1
              and ok_runs[0][2] == control and total == control and dup == 0)
    print(f"\nKILL (a): {'PASS — killed INSIDE the transaction, one ok run, no duplicate blocks' if passed else 'NOT PROVEN' if not inflight else 'FAILED'}")
    _log("kill_test", subject=row["name"], passed=passed, **verdict)
    ro.close()
    return 0 if passed else 1


# ── CLI ────────────────────────────────────────────────────────────────────────────────────

def main(argv=None):
    from phase4seg.names import clean_argv

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="litkb")
    ap.add_argument("--quiet", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--force", action="store_true", help="re-probe every census file")
    p.add_argument("--workstream", default=None,
                   help="ALSO plan the active files this workstream PROPOSES that main does not "
                        "hold yet (give its slug). Without it the population is main's view, "
                        "which is why 14 acquired PDFs stranded in open workstreams were "
                        "invisible to the bulk pass (LITKB_OPERATIONAL_REFEREE_2026-09-16 R-3)")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("grobid")
    p.add_argument("--workers", type=int, default=4, help="client threads against pool 4")
    p.add_argument("--limit", type=int)
    p.add_argument("--stop", action="store_true", default=True)
    p.add_argument("--no-stop", dest="stop", action="store_false")
    p.set_defaults(fn=cmd_grobid)

    p = sub.add_parser("docling")
    p.add_argument("--device", default="cuda")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--chunk", type=int, default=30, help="documents per converter build")
    p.add_argument("--ocr-chunk", type=int, default=D.OCR_CHUNK,
                   help="documents per converter build on the OCR batch — the measured VRAM cap "
                        "(2,619 MiB / 63.9 %% at 4, against 3,873 / 94.6 %% at 15). "
                        f"Default: {D.OCR_CHUNK}")
    p.add_argument("--timeout", type=int, default=14400)
    p.add_argument("--ocr-max-pages", type=int, default=200,
                   help="a document larger than this is never put in the OCR batch")
    p.add_argument("--limit", type=int)
    p.set_defaults(fn=cmd_docling)

    p = sub.add_parser("ingest")
    p.add_argument("--only", help="comma-separated sha256 or file names")
    p.add_argument("--limit", type=int)
    p.add_argument("--csv")
    p.add_argument("--pipeline-version", default=P5_PIPELINE_VERSION,
                   help="the run identity to ingest under. BUMP IT when reconciliation's own "
                        "arithmetic has changed for these files and the run already on record "
                        "was made by the old one — otherwise `already_ingested` skips the file "
                        "and the stale blocks stand for ever. Default: " + P5_PIPELINE_VERSION)
    p.add_argument("--hold-in-transaction", type=float, default=0.0,
                   help="THE KILL HARNESS ONLY: sit this long inside the open transaction, "
                        "every block inserted and nothing committed, so a kill can land there")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("kill-test")
    p.add_argument("--only", help="sha256 or name; default: the largest document with no ok run")
    p.add_argument("--hold", type=float, default=20.0,
                   help="how long the child sits inside the open transaction")
    p.add_argument("--kill-delay", type=float, default=15.0,
                   help="how long to wait for a backend in flight before killing anyway")
    p.set_defaults(fn=cmd_kill_test)

    p = sub.add_parser("gate")
    p.add_argument("--csv")
    p.set_defaults(fn=cmd_gate)

    a = ap.parse_args(clean_argv() if argv is None else argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())

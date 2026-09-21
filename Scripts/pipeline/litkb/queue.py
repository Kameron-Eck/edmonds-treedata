"""The extraction queue: sweep, claim, work, classify (design §12.3-§12.5, migration 0029).

    py -3.12 -m litkb queue sweep
    py -3.12 -m litkb queue run --worker w1 [--max N] [--ocr on|off] [--device cpu|cuda]
    py -3.12 -m litkb queue status

WHAT THIS IS FOR. Before it, "this file has no text" was one word for six different situations:
nobody has run it yet, it is a scan and OCR was off, it is longer than we are willing to convert,
the bytes are not a PDF, the converter ran and produced nothing, or a worker was killed halfway
and nothing remembers. `qc/instruments/litkb_p5_bulk.py` made the RESUME safe — an artifact plus a
.sha256 sidecar on disk — and its own docstring says it does nothing about two workers leasing one
job, and nothing about recording WHY a file was not read. This module is the database half: every
acquired file gets a row, and every row ends in a state with a name.

THE FOUR RULES IT KEEPS, each of which is a thing that went wrong somewhere else first:

  1. **Nothing starts without a page count.** `probe_pages` runs before GROBID or Docling is
     touched. A probe that RAISES is `bad-file`; a count over `PAGE_CAP` is `over-page-cap`; in
     neither case is a tool invoked. The binding cap this replaces
     (`admit.binding.ocr_first_pages`'s OCR_BIND_MAX_PAGES check) fails OPEN — a non-digit page
     count skips it and OCR runs uncapped — and this one is the other way round: no number, no
     conversion.
  2. **A scan that cannot be OCR'd is classified, not converted.** Running Docling with OCR off
     over an image-only page succeeds and yields no body block, which lands in the database as
     "extracted, 0 chars" and is indistinguishable from a file that has genuinely nothing to say.
     The readiness policy decides, before the tool runs, and a refusal writes NO run row.
  3. **The ingest and the finish are ONE transaction.** `ingest_file(..., commit=False)` and
     `finish_job` commit together, so a kill leaves either a finished unit or no rows at all —
     §12.4's rule, and the reason the job row can be trusted as the ledger.
  4. **The current-run pointer moves only on a run that has blocks.** A reconciliation that
     produced nothing finishes as a `failed` run and the file keeps whatever pointer it had; the
     job is `classified/zero-content`. That guard is in `litkb.extract.ingest.ingest_file`.

THE POLICY OBJECT (`litkb.extract.readiness`, built in parallel by S4's readiness builder) supplies
`PAGE_CAP`, `probe_pages`, `ProbeFailed`, `cap_check`, `vram_free_mib`, `page_needs_ocr` and
`ocr_policy`. When it is not importable the default is :class:`NoReadiness`, which FAILS CLOSED:
every probe raises and every scan is refused, so a queue run made with no policy classifies rather
than converts. Tests inject a fake; `--policy dotted.name` names another.

ARTIFACTS go to ``<derived>/<sha256>/<stage>/<tool>@<version>_<params>/`` (§12.4) and are written
`.partial` → fsync → rename, with a `<name>.sha256` sidecar beside them — the pattern
`litkb.ops.nightly_dump` and the bulk driver already use. An artifact whose bytes still hash to
the sha256 recorded FOR it is not produced again: the sidecar is what survives a kill mid-job, and
`extraction_jobs.artifact_sha256` is what survives the job.
"""
import hashlib
import json
import os
import pathlib
import threading
import time

#: How long a claim holds a job before it returns to the pool. Longer than the longest job, or a
#: live worker's lease expires under it and a second worker starts the same file: the measured
#: worst case on this machine is the 688-page CPU pass at 995.9 s
#: (Reports/LITKB_DOCLING_LOCAL_2026-09-15.md), so 1800 s is that with room, and the heartbeat
#: renews at half of it while a tool runs.
LEASE_SECONDS = int(os.environ.get("LITKB_QUEUE_LEASE_SECONDS", "1800"))

#: §12.3: after this many attempts a job is `dead` and a `failed` run row is written. Three,
#: because a deterministic failure repeated unchanged fails again and the point of the retry is a
#: transient one (a tool that was down, a machine that rebooted).
MAX_ATTEMPTS = int(os.environ.get("LITKB_QUEUE_MAX_ATTEMPTS", "3"))

#: Where this queue's artifacts live. `LITKB_QUEUE_DERIVED` exists so a run against a WORKER
#: database cannot write into — or read a cached artifact out of — the live pass's tree: the
#: artifact is keyed by the file's sha256, which is the same bytes in both databases, so without a
#: separate root a worker-DB run would silently adopt the live corpus's conversions and prove
#: nothing. Default: `<LITKB_DERIVED>/queue`, beside stage 6's own root
#: (`litkb.extract.references.DERIVED_ROOT`), never inside the read-only literature tree.
_DERIVED_ENV = "LITKB_QUEUE_DERIVED"


def derived_root():
    from litkb.extract import references as _ref

    return os.environ.get(_DERIVED_ENV) or os.path.join(_ref.DERIVED_ROOT, "queue")


# ── the readiness policy ─────────────────────────────────────────────────────────────────────

class _NoReadinessProbeFailed(Exception):
    """:class:`NoReadiness`'s ProbeFailed. It carries `reason` because the worker records it."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class NoReadiness:
    """The fail-closed default: no readiness module, so nothing is converted.

    A missing policy must not mean "convert everything with no cap and no OCR decision" — that is
    the state this queue exists to end. Every probe raises, so every job is `bad-file`, and every
    scan is `scan-needs-ocr`. A run made against this policy is a run that classified the queue
    and spent no GPU, which is a visible, correctable outcome rather than a silent one.
    """

    PAGE_CAP = 0
    ProbeFailed = _NoReadinessProbeFailed

    @staticmethod
    def probe_pages(path):
        del path
        raise _NoReadinessProbeFailed("no-readiness-module")

    @staticmethod
    def cap_check(pages):
        del pages
        return "over-page-cap"

    @staticmethod
    def vram_free_mib():
        return None

    @staticmethod
    def page_needs_ocr(page_class, coverage_share):
        del page_class, coverage_share
        return True

    @staticmethod
    def ocr_policy(n_ocr_pages, ocr_enabled, free_mib):
        del n_ocr_pages, ocr_enabled, free_mib
        return ("residue", "scan-needs-ocr")


def load_policy(name=None):
    """The readiness policy: `name` if given, else `litkb.extract.readiness`, else NoReadiness."""
    import importlib

    if name:
        return importlib.import_module(name)
    try:
        return importlib.import_module("litkb.extract.readiness")
    except ImportError:
        return NoReadiness


# ── the tools, behind one seam ───────────────────────────────────────────────────────────────

class Tools:
    """GROBID and Docling, as two calls, so a test can prove a tool was NEVER invoked.

    The cap and the OCR refusal are only as good as "the tool did not run", and an assertion about
    that needs something to count. This class is that something; the default is exactly what
    `litkb.hunt.extract_and_ingest` does.
    """

    def __init__(self, *, docling_python=None):
        self.docling_python = docling_python
        self.calls = []

    def grobid(self, pdf_path):
        """-> TEI text, or None when GROBID refused or was unreachable. That is not fatal: the
        reconciliation runs on whichever tool produced an artifact, every block single-source
        (`reconcile.reconcile`'s docstring; only BOTH missing is a hard refusal)."""
        from litkb.extract import grobid as G

        self.calls.append(("grobid", str(pdf_path)))
        # STOP ONLY WHAT THIS CALL STARTED. `G.start` is idempotent and returns True when the
        # service is ALREADY alive, so `started = G.start(...)` with `finally: G.stop()` — the
        # shape `hunt.extract_and_ingest` uses — stops a GROBID somebody else is holding open, and
        # under WSL that takes the whole pool down in the middle of a queue run. The health check
        # before the start is what tells the two cases apart.
        already = G.health()
        mine = False
        try:
            if not already:
                mine = G.start(wait=300, hold=True)
                if not mine:
                    raise G.GrobidError("GROBID did not come up under WSL")
            tei, _m = G.extract(pdf_path, concurrency=1, sample_rss=False)
            return tei, None
        except G.GrobidError as e:
            return None, f"{type(e).__name__}: {e}"[:300]
        finally:
            if mine:
                G.stop()

    def docling(self, pdf_path, out_json, metrics_path, *, ocr, device, cwd):
        from litkb.extract import docling as D

        self.calls.append(("docling", str(pdf_path)))
        D.run([{"pdf": str(pdf_path), "out": str(out_json)}], str(metrics_path),
              python=self.docling_python, ocr=bool(ocr), formula=False, device=device, cwd=cwd)
        return D.load(out_json) if os.path.exists(out_json) else None


# ── the run key, read from the package ───────────────────────────────────────────────────────

def run_key_fields():
    """(stage, tool, tool_version, params_hash, pipeline_version) for TODAY's corpus.

    Read from `litkb.extract.ingest` and `litkb.extract.reconcile`, never copied: the queue and
    `litkb hunt` and the bulk pass must agree on what "already extracted" means, and a second copy
    of this dict is how a hunted file silently becomes a different extraction from the corpus
    around it (CLAUDE.md §3.3, and the comment on `extract.ingest.CORPUS_PARAMS`)."""
    from litkb.extract import ingest as ing
    from litkb.extract import reconcile as R

    k = ing.run_key(None, R.PIPELINE_VERSION, ing.CORPUS_PARAMS)
    return (k["stage"], k["tool"], k["tool_version"], k["params_hash"], k["pipeline_version"])


# ── active files ─────────────────────────────────────────────────────────────────────────────

ACTIVE_FILES_SQL = """
SELECT DISTINCT ON (v.file_id) v.file_id, v.rel_path, v.pages, v.state
  FROM litkb.file_versions v
 WHERE v.status = 'active' AND v.state IN ('promoted', 'proposed')
 ORDER BY v.file_id, v.version_no DESC
"""


def active_files(conn):
    """Every file the corpus is accountable for -> [{file_id, rel_path, pages, state}].

    `main_files` is NOT the population. It is `files` joined to the PROMOTED head, so a file a
    workstream has proposed and no second session has approved is invisible to it — 13 of the 251
    active file versions today, every one of them with no extraction run. S4's acceptance
    criterion is "all workstreams, not main only", so the sweep reads `file_versions` directly and
    takes the latest ACTIVE version of each file, promoted or proposed.
    """
    return [{"file_id": r[0], "rel_path": r[1], "pages": r[2], "state": r[3]}
            for r in conn.execute(ACTIVE_FILES_SQL).fetchall()]


# ── sweep ────────────────────────────────────────────────────────────────────────────────────

def sweep(conn):
    """Enqueue a stage-5 job for every active file. -> counters. A repeated sweep is a no-op.

    The no-op is the UNIQUE index's, not a Python check: `enqueue_extraction` INSERTs ON CONFLICT
    DO NOTHING on (run key, page range), so two sweeps racing each other cannot both win, and a
    sweep that crashed halfway can simply be run again.
    """
    stage, tool, tool_version, params_hash, pipeline_version = run_key_fields()
    counters = {"files": 0, "new_queued": 0, "new_done": 0, "existing": 0}
    for f in active_files(conn):
        counters["files"] += 1
        _jid, state, was_new = conn.execute(
            "SELECT * FROM litkb.enqueue_extraction(%s, %s, %s, %s, %s, %s, NULL, NULL, %s)",
            (f["file_id"], stage, tool, tool_version, params_hash, pipeline_version,
             f["pages"])).fetchone()
        if not was_new:
            counters["existing"] += 1
        elif state == "done":
            counters["new_done"] += 1
        else:
            counters["new_queued"] += 1
    return counters


# ── status ───────────────────────────────────────────────────────────────────────────────────

def status(conn):
    """Counts by stage x state, residue classes, pages remaining, stale leases. -> counters."""
    out = {}
    for stage, state, n in conn.execute(
            "SELECT stage, state, count(*) FROM litkb.extraction_jobs GROUP BY 1, 2 "
            "ORDER BY 1, 2").fetchall():
        out[f"{stage}/{state}"] = n
    for cls, n in conn.execute(
            "SELECT residue_class, count(*) FROM litkb.extraction_jobs "
            "WHERE residue_class IS NOT NULL GROUP BY 1 ORDER BY 1").fetchall():
        out[f"residue:{cls}"] = n
    out["jobs"] = conn.execute("SELECT count(*) FROM litkb.extraction_jobs").fetchone()[0]
    # pages still to convert: the sum over everything not in a terminal state. A job with an
    # unknown page count contributes 0 to the sum and is counted separately, because a total that
    # silently treated "unknown" as zero would say the queue is smaller than it is.
    row = conn.execute(
        "SELECT coalesce(sum(pages), 0), count(*) FILTER (WHERE pages IS NULL) "
        "FROM litkb.extraction_jobs WHERE state IN ('queued', 'leased')").fetchone()
    out["pages_remaining"] = int(row[0])
    out["pages_unknown_jobs"] = row[1]
    out["stale_leases"] = conn.execute(
        "SELECT count(*) FROM litkb.extraction_jobs "
        "WHERE state = 'leased' AND lease_expires_at <= now()").fetchone()[0]
    return out


def format_counters(counters):
    return " ".join(f"{k}={v}" for k, v in counters.items())


# ── artifacts ────────────────────────────────────────────────────────────────────────────────

def artifact_dir(root, sha256, stage, tool, tool_version, params_hash):
    """`<root>/<sha256>/<stage>/<tool>@<version>_<params>/` — design §12.4/§6."""
    return os.path.join(str(root), sha256, stage, f"{tool}@{tool_version}_{params_hash}")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path, data):
    """`.partial` → flush → fsync → rename, then a `<path>.sha256` sidecar. -> the sha256.

    The sidecar is what makes "resumable" checkable rather than assumed: a `.partial` that was
    being written when the process died is not at `path`, and a file at `path` whose bytes no
    longer hash to its sidecar is a killed writer's leftovers, not a cached artifact.
    """
    tmp = f"{path}.partial"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    digest = hashlib.sha256(data).hexdigest()
    with open(f"{path}.sha256", "w", encoding="utf-8") as fh:
        fh.write(digest)
    return digest


def artifact_ok(path, expect=None):
    """True when `path` exists and its bytes hash to `expect`, else to its own sidecar."""
    if not os.path.exists(path):
        return False
    want = expect
    if want is None:
        side = f"{path}.sha256"
        if not os.path.exists(side):
            return False
        want = open(side, encoding="utf-8").read().strip()
    try:
        return sha256_file(path) == want
    except OSError:
        return False


def seal(path):
    """Write the sidecar for an artifact a tool produced ITSELF (the docling worker writes its own
    JSON, so there is nothing to hand :func:`write_atomic`). -> the sha256, or None."""
    if not os.path.exists(path):
        return None
    digest = sha256_file(path)
    with open(f"{path}.sha256", "w", encoding="utf-8") as fh:
        fh.write(digest)
    return digest


# ── the worker ───────────────────────────────────────────────────────────────────────────────

class _Heartbeat:
    """Renews the lease at half the lease length, from its own connection.

    Its own connection because the main thread is inside the ingest transaction for most of a
    job's life, and a renewal that had to wait for that transaction is a renewal that arrives
    after the lease it was renewing expired.
    """

    def __init__(self, connect, job_id, token, lease_seconds):
        self._connect = connect
        self.job_id, self.token, self.lease = job_id, token, lease_seconds
        self.renewals = 0
        self.errors = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, name="litkb-queue-heartbeat", daemon=True)

    def start(self):
        self._t.start()
        return self

    def _loop(self):
        conn = None
        try:
            while not self._stop.wait(max(self.lease / 2.0, 1.0)):
                try:
                    if conn is None:
                        conn = self._connect()
                    conn.execute("SELECT litkb.renew_lease(%s, %s, %s)",
                                 (self.job_id, self.token, self.lease))
                    self.renewals += 1
                except Exception as e:                     # noqa: BLE001
                    self.errors.append(f"{type(e).__name__}: {e}"[:200])
                    if conn is not None:
                        try:
                            conn.close()
                        finally:
                            conn = None
        finally:
            if conn is not None:
                conn.close()

    def stop(self):
        self._stop.set()
        self._t.join(timeout=5)
        return self.renewals


class Worker:
    """One queue worker. `run()` claims, works and closes jobs until `max_jobs` or an empty queue.

    `connect(autocommit=True)` returns a fresh ingest-login connection; the worker opens THREE
    kinds from it — a control connection in autocommit for the claim and the terminal calls, one
    per job in a transaction for the ingest, and the heartbeat's own.
    """

    def __init__(self, connect, *, worker, policy=None, tools=None, ocr=True, device="cpu",
                 lease_seconds=None, max_attempts=None, derived=None, root=None, grobid=True):
        self.connect, self.worker = connect, worker
        self.policy = policy if policy is not None else load_policy()
        self.tools = tools if tools is not None else Tools()
        self.ocr, self.device, self.grobid = ocr, device, grobid
        self.lease = int(lease_seconds or LEASE_SECONDS)
        self.max_attempts = int(max_attempts or MAX_ATTEMPTS)
        self.derived = str(derived or derived_root())
        self._root = root
        self.counters = {"claimed": 0, "done": 0, "classified": 0, "failed": 0, "dead": 0,
                         "requeued": 0, "artifacts_reused": 0, "lease_renewals": 0}
        self.residue = {}
        self.events = []

    # -- helpers ------------------------------------------------------------------------------

    def _literature_root(self):
        if self._root:
            return self._root
        from litkb.acquire.store import LITERATURE_ROOT

        return LITERATURE_ROOT

    def _path_of(self, ctl, file_id):
        row = ctl.execute(
            "SELECT v.rel_path, f.sha256 FROM litkb.file_versions v JOIN litkb.files f ON f.id = v.file_id "
            "WHERE v.file_id = %s AND v.status = 'active' ORDER BY v.version_no DESC LIMIT 1",
            (file_id,)).fetchone()
        if row is None:
            return None, None
        return (os.path.join(str(self._literature_root()), row[0].replace("/", os.sep)), row[1])

    def _classify(self, ctl, job, cls, detail):
        ctl.execute("SELECT litkb.classify_job(%s, %s, %s, %s)",
                    (job["job_id"], job["lease_token"], cls, detail))
        self.counters["classified"] += 1
        self.residue[cls] = self.residue.get(cls, 0) + 1
        self.events.append({"job": str(job["job_id"]), "outcome": "classified",
                            "residue_class": cls, "detail": detail})

    def _fail(self, ctl, job, error):
        """Record the failure and return the job to the queue (or kill it after max_attempts).

        A LOST LEASE here is not fatal to the worker. The ownership gate refuses a terminal call
        from a worker whose lease expired — correctly, because a second worker may already hold
        the job — and that refusal must not take the whole run down with it: the job is back in
        the pool either way, which is exactly what an expired lease means."""
        try:
            state = ctl.execute(
                "SELECT litkb.fail_job(%s, %s, %s, %s)",
                (job["job_id"], job["lease_token"], error, self.max_attempts)).fetchone()[0]
        except Exception as e:                                     # noqa: BLE001
            self.counters["lease_lost"] = self.counters.get("lease_lost", 0) + 1
            self.events.append({"job": str(job["job_id"]), "outcome": "lease-lost",
                                "detail": f"{type(e).__name__}: {e}"[:200],
                                "while_reporting": error[:200]})
            return "lease-lost"
        self.counters["failed"] += 1
        self.counters["dead" if state == "dead" else "requeued"] += 1
        if state == "dead":
            self._record_dead_run(job, error)
        self.events.append({"job": str(job["job_id"]), "outcome": state, "detail": error[:200]})
        return state

    def _record_dead_run(self, job, error):
        """§12.3: only when a job is dead is an `extraction_runs` row with status `failed` written.

        Its own connection and its own transaction: the job is already dead and committed, and a
        failure to record the run must not un-kill it.
        """
        from psycopg.types.json import Jsonb

        conn = self.connect()
        try:
            conn.execute(
                "SELECT litkb.open_extraction_run(%s, %s, %s, %s, %s, %s, 'local', 'failed', NULL, %s)",
                (job["file_id"], job["stage"], job["tool"], job["tool_version"],
                 job["params_hash"], job["pipeline_version"],
                 Jsonb({"queue": {"job_id": str(job["job_id"]), "worker": self.worker,
                                  "attempts": job["attempts"], "last_error": error[:1000]}})))
        finally:
            conn.close()

    # -- the loop -----------------------------------------------------------------------------

    def run(self, max_jobs=None):
        ctl = self.connect()
        try:
            while max_jobs is None or self.counters["claimed"] < max_jobs:
                row = ctl.execute("SELECT * FROM litkb.claim_jobs(%s, 1, %s)",
                                  (self.worker, self.lease)).fetchone()
                if row is None:
                    break
                cols = ("job_id", "file_id", "stage", "tool", "tool_version", "params_hash",
                        "pipeline_version", "page_start", "page_end", "pages", "attempts",
                        "artifact_sha256", "lease_token", "lease_expires_at")
                job = dict(zip(cols, row))
                self.counters["claimed"] += 1
                self._one(ctl, job)
        finally:
            ctl.close()
        return self.counters

    def _one(self, ctl, job):
        path, sha = self._path_of(ctl, job["file_id"])
        # BEGIN guard: nothing is converted before its pages are counted and capped
        if path is None or not os.path.exists(path):
            return self._classify(ctl, job, "bad-file",
                                  f"no readable file is bound at {path or '(no active version)'}")
        try:
            pages = self.policy.probe_pages(path)
        except getattr(self.policy, "ProbeFailed", Exception) as e:
            return self._classify(ctl, job, "bad-file",
                                  f"page-count probe failed: {getattr(e, 'reason', e)}")
        except Exception as e:                                     # noqa: BLE001
            return self._classify(ctl, job, "bad-file",
                                  f"page-count probe raised {type(e).__name__}: {e}"[:400])
        capped = self.policy.cap_check(pages)
        if capped:
            return self._classify(ctl, job, capped,
                                  f"{pages} pages is over the extraction cap "
                                  f"({getattr(self.policy, 'PAGE_CAP', '?')})")
        # END guard: nothing is converted before its pages are counted and capped
        hb = None
        try:
            hb = _Heartbeat(self.connect, job["job_id"], job["lease_token"], self.lease).start()
            self._convert_and_ingest(ctl, job, path, sha, pages)
        except Exception as e:                                     # noqa: BLE001
            self._fail(ctl, job, f"{type(e).__name__}: {e}"[:1000])
        finally:
            if hb is not None:
                self.counters["lease_renewals"] += hb.stop()

    def _convert_and_ingest(self, ctl, job, path, sha, pages):
        import dataclasses

        from litkb.extract import ingest as ing
        from litkb.extract import inventory as I
        from litkb.extract import reconcile as R

        t_start = time.monotonic()
        rec = I.probe_file(path)
        out = artifact_dir(self.derived, sha or rec["sha256"], job["stage"], job["tool"],
                           job["tool_version"], job["params_hash"])
        os.makedirs(out, exist_ok=True)
        ocr_pages = list(rec.get("ocr_pages") or ())

        # BEGIN guard: a scan the policy will not OCR is classified, never converted blind
        decision, arg = self.policy.ocr_policy(len(ocr_pages), bool(self.ocr),
                                               self.policy.vram_free_mib())
        if decision != "run":
            return self._classify(
                ctl, job, arg,
                f"{len(ocr_pages)} of {pages} pages need OCR and the readiness policy refused "
                f"(ocr={'on' if self.ocr else 'off'}, route={rec['route']})")
        # END guard: a scan the policy will not OCR is classified, never converted blind
        device = arg or self.device
        wants_ocr = bool(ocr_pages) and bool(self.ocr)

        tei_path = os.path.join(out, "grobid.tei.xml")
        doc_json = os.path.join(out, "docling.json")
        tei, grobid_error = None, None
        if self.grobid and rec["route"] in ("native", "mixed", "cover-sheet"):
            # BYTES, not text. `grobid.extract` hands back the response body as it came off the
            # wire, and the TEI carries its own XML declaration and encoding — decoding it here
            # and re-encoding on the way out would make this module a second opinion about the
            # document's encoding. The reconciler's parser takes bytes, so the artifact round
            # trips unchanged and its sha256 is a hash of what GROBID actually said.
            if artifact_ok(tei_path):
                tei = pathlib.Path(tei_path).read_bytes()
                self.counters["artifacts_reused"] += 1
            else:
                tei, grobid_error = self.tools.grobid(path)
                if tei is not None:
                    write_atomic(tei_path,
                                 tei if isinstance(tei, bytes) else tei.encode("utf-8"))
        doc = None
        if artifact_ok(doc_json, job.get("artifact_sha256")):
            from litkb.extract import docling as D

            doc = D.load(doc_json)
            self.counters["artifacts_reused"] += 1
        else:
            doc = self.tools.docling(path, doc_json, os.path.join(out, "metrics_docling.jsonl"),
                                     ocr=wants_ocr, device=device, cwd=out)
        doc_sha = seal(doc_json)
        if tei is None and doc is None:
            raise RuntimeError("neither GROBID nor Docling produced an artifact"
                               + (f" ({grobid_error})" if grobid_error else ""))

        frames = I.page_frames(path)
        canonical, dis, stats = R.reconcile(path, tei, doc, rec,
                                            ocr_pages=rec.get("ocr_pages") or (), frames=frames)
        canonical = [dataclasses.replace(c, latex_status="unverified")
                     if c.kind == "equation" and c.latex_status is None else c
                     for c in canonical]
        classes = {i + 1: d.get("scan", "unknown")
                   for i, d in enumerate(rec.get("page_detail") or [])}
        cov = R.coverage(path, canonical, classes, frames=frames)
        page_rows = [{"page_no": p, "page_class": r["page_class"], "native_chars": r["chars"],
                      "covered_chars": r["covered"], "coverage_share": r["share"]}
                     for p, r in sorted(cov.items())]

        # The queue's own numbers, NEVER over the reconciliation's: `stats` is what the reconciler
        # measured about the document and `setdefault` is what keeps this from quietly redefining
        # one of its keys (`blocks`, `grobid_regions`, `docling_regions`, … — the 909 live runs
        # are read by that vocabulary).
        seconds = round(time.monotonic() - t_start, 2)
        for k, v in (("seconds", seconds), ("pages", pages),
                     ("pages_per_s", round(pages / seconds, 3) if seconds else None),
                     ("device", device), ("ocr_pages", len(ocr_pages)),
                     ("job_id", str(job["job_id"])), ("worker", self.worker),
                     ("lease_renewals", self.counters["lease_renewals"])):
            stats.setdefault(k, v)

        # ONE TRANSACTION: the run row, its text rows and the job's terminal state (§12.4).
        conn = self.connect(autocommit=False)
        try:
            res = ing.ingest_file(conn, job["file_id"], canonical, dis, stats, pages=page_rows,
                                  artifact_path=doc_json, host="local",
                                  pipeline_version=job["pipeline_version"],
                                  params=ing.CORPUS_PARAMS, commit=False,
                                  zero_blocks="failed-run")
            if res["blocks"] > 0:
                conn.execute("SELECT litkb.finish_job(%s, %s, %s, %s)",
                             (job["job_id"], job["lease_token"], res["run_id"], doc_sha))
                self.counters["done"] += 1
                self.events.append({"job": str(job["job_id"]), "outcome": "done",
                                    "blocks": res["blocks"], "run_id": str(res["run_id"])})
            else:
                conn.execute(
                    "SELECT litkb.classify_job(%s, %s, 'zero-content', %s)",
                    (job["job_id"], job["lease_token"],
                     "the reconciliation produced no canonical block; the run is failed and the "
                     "file's current run is unchanged"))
                self.counters["classified"] += 1
                self.residue["zero-content"] = self.residue.get("zero-content", 0) + 1
                self.events.append({"job": str(job["job_id"]), "outcome": "classified",
                                    "residue_class": "zero-content"})
            conn.commit()
        finally:
            conn.close()


# ── the CLI ──────────────────────────────────────────────────────────────────────────────────

def _ingest_connect(db, role=None):
    """-> connect(autocommit=True), the one connection factory the whole module takes.

    `role` is the worker-database door, the same one `reap` and `review-context` have: a
    `litkb_test_wN` database's pgpass carries no `litkb_ingest` line, so the ingest login cannot
    open one at all and a queue run against a restored dump would be impossible. With `--role
    litkb_test` the connection is made as that login and then `SET ROLE litkb_ingest`, so every
    statement below still runs with exactly the ingest role's privileges — the ownership gate,
    the grants and the SECURITY DEFINER functions are the same ones. It is the CREDENTIAL that
    differs, and only a throwaway database has the other one.
    """
    def _c(autocommit=True):
        if not role:
            from litkb import ingest as ingest_login

            return ingest_login.connect(db, autocommit=autocommit)
        from psycopg import sql

        from litkb.db import connect as c

        k = c.connect(db, role, autocommit=autocommit)
        k.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(c.INGEST)))
        if not autocommit:
            k.commit()          # SET ROLE leaves the connection INTRANS; SET survives the commit
        return k

    return _c


def cmd_queue(args, _conn=None):
    """`litkb queue sweep|run|status`. Opens the ingest login itself (see commands._OWN_LOGINS)."""
    connect = _ingest_connect(args.db, getattr(args, "role", None))
    if args.queue_cmd == "sweep":
        conn = connect()
        try:
            counters = sweep(conn)
        finally:
            conn.close()
        print("queue sweep: " + format_counters(counters))
        return 0
    if args.queue_cmd == "status":
        conn = connect()
        try:
            counters = status(conn)
        finally:
            conn.close()
        print("queue status: " + format_counters(counters))
        return 0
    w = Worker(connect, worker=args.worker, policy=load_policy(args.policy),
               ocr=(args.ocr == "on"), device=args.device, lease_seconds=args.lease,
               max_attempts=args.max_attempts, derived=args.derived,
               grobid=not args.no_grobid)
    counters = w.run(max_jobs=args.max)
    line = format_counters(counters)
    if w.residue:
        line += " " + format_counters({f"residue:{k}": v for k, v in sorted(w.residue.items())})
    print("queue run: " + line)
    if args.json:
        print(json.dumps({"counters": counters, "residue": w.residue, "events": w.events},
                         indent=2, default=str))
    return 0


def add_parser(sub):
    """Register `queue` on `litkb.commands.build_parser`'s subparsers."""
    q = sub.add_parser("queue", help="the extraction queue (design §12.3): enqueue every acquired "
                                     "file, work the queue under a lease, and say why any file "
                                     "that produced no text produced none")
    qsub = q.add_subparsers(dest="queue_cmd", required=True)
    sw = qsub.add_parser("sweep", help="enqueue a job for every active file lacking one; a "
                                       "repeated sweep is a no-op")
    st = qsub.add_parser("status", help="counts by stage x state, residue classes, pages "
                                        "remaining, stale leases")
    r = qsub.add_parser("run", help="claim jobs and work them")
    for sp in (sw, st, r):
        sp.add_argument("--role", help="connect as this login and SET ROLE litkb_ingest, instead "
                                       "of opening the ingest login directly. A worker database "
                                       "litkb_test_wN has no litkb_ingest pgpass line, so a run "
                                       "against one passes --role litkb_test; the privileges are "
                                       "the ingest role's either way")
    r.add_argument("--worker", required=True, help="this worker's id; it appears in lease_owner")
    r.add_argument("--max", type=int, help="stop after this many jobs (default: drain the queue)")
    r.add_argument("--ocr", choices=("on", "off"), default="on")
    r.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    r.add_argument("--lease", type=int, default=LEASE_SECONDS,
                   help=f"lease seconds (default {LEASE_SECONDS}, LITKB_QUEUE_LEASE_SECONDS)")
    r.add_argument("--max-attempts", dest="max_attempts", type=int, default=MAX_ATTEMPTS,
                   help=f"attempts before a job is dead (default {MAX_ATTEMPTS})")
    r.add_argument("--derived", help=f"artifact root (default {_DERIVED_ENV}, else "
                                     "<LITKB_DERIVED>/queue)")
    r.add_argument("--policy", help="dotted name of the readiness module (default "
                                    "litkb.extract.readiness, else the fail-closed NoReadiness)")
    r.add_argument("--no-grobid", dest="no_grobid", action="store_true",
                   help="Docling only; the reconciliation runs single-source")
    r.add_argument("--json", action="store_true", help="also print counters and events as JSON")
    return q

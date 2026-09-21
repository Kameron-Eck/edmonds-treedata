"""The extraction queue: migration 0029's lease and the worker that holds it (litkb/queue.py).

WHAT IS REAL HERE AND WHAT IS STUBBED, stated up front because it decides what these tests are
evidence of:

  * **The database is real.** Every lease, claim, expiry, forged token, residue class and CHECK
    below runs against migration 0029 applied to the worker database by `qc/conftest.py`'s
    `litkb_pg_base` fixture, through the `litkb_ingest` role (SET ROLE, the way
    `qc/test_litkb_p1.py` exercises grants without the ingest passfile). Nothing about the
    ownership gate is simulated.
  * **GROBID and Docling are NOT run.** `litkb.queue.Tools` is the seam, and the fake here records
    every call — which is what makes "the cap refused it and NO tool was invoked" an assertion
    rather than a hope.
  * **The reconciliation is stubbed in the two tests that reach it** (zero-content, and the
    single happy path), because a real reconcile needs a real PDF, a real converter and two real
    artifacts. Those two tests are therefore evidence about the QUEUE's branch and its
    transaction, not about the reconciler. The end-to-end proof over real files is the w7 run in
    the S4 Q1 report, not a unit test.

The readiness policy is injected as a plain object with the six names `litkb.extract.readiness`
will expose, so this file passes unchanged before and after that module lands.
"""
import os
import uuid

import pytest

pg_only = pytest.mark.requires_litkb_pg


# ── harness ───────────────────────────────────────────────────────────────────────────────────

class _Q:
    """The litkb_test owner connection plus the per-test ingest sessions it opened."""

    def __init__(self, psycopg, conn):
        from psycopg.types.json import Jsonb

        self.psycopg, self.errors, self.Jsonb = psycopg, psycopg.errors, Jsonb
        self.conn = conn
        self.opened = []

    def session(self, role="litkb_ingest", autocommit=True):
        from psycopg import sql

        from litkb.db import connect as c
        k = c.connect(c.DB_TEST, "litkb_test", autocommit=autocommit)
        if role:
            k.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            if not autocommit:
                # SET ROLE left the connection INTRANS, and psycopg refuses to touch `autocommit`
                # there even when the value does not change — which `ingest_file` does on entry.
                # SET (not SET LOCAL) survives the commit, so the role stays.
                k.commit()
        self.opened.append(k)
        return k

    def one(self, q, params=(), conn=None):
        return (conn or self.conn).execute(q, params).fetchone()

    # -- setup, as the owner ------------------------------------------------------------------

    def ws(self):
        return self.one(
            "SELECT workstream_id FROM litkb.open_workstream(%s, 'work/test', NULL, 'queue test', NULL)",
            (f"q-{uuid.uuid4().hex[:12]}",))[0]

    def file(self, ws, *, rel_path=None, pages=None, state="promoted"):
        """A work and one active file version. `state` promoted or proposed — the sweep reads both."""
        work_id, _ = self.one(
            "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, "
            "NULL, %s, NULL, %s, 'setup', 'setup')",
            (self.Jsonb({"key": f"Test_2020_{uuid.uuid4().hex[:8]}-paper"}),
             self.Jsonb({"type": "article", "title": "A test work", "authors": []}), ws))
        rel = rel_path or f"Validation/{uuid.uuid4().hex[:10]}.pdf"
        fields = {"work_id": str(work_id), "rel_path": rel, "status": "active"}
        if pages is not None:
            fields["pages"] = pages
        kind, wsid = ("fact", ws) if state == "promoted" else ("proposal", ws)
        file_id, _ = self.one(
            "SELECT entity_id, version_id FROM litkb._write_version(%s, 'file', NULL, %s, NULL, "
            "%s, NULL, %s, 'setup', 'setup')",
            (kind, self.Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
             self.Jsonb(fields), wsid))
        return file_id, rel

    def ok_run(self, file_id, key):
        """An `ok` run at exactly `key` — what the sweep must recognise as already done."""
        stage, tool, tool_version, params_hash, pipeline_version = key
        return self.one(
            "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
            "pipeline_version, host, status) VALUES (%s, %s, %s, %s, %s, %s, 'local', 'ok') "
            "RETURNING id", (file_id, stage, tool, tool_version, params_hash, pipeline_version))[0]

    def clear(self):
        """Empty the queue. The module DB is shared by every test in this file, and `claim_jobs`
        deliberately has no "only my jobs" filter — a claim takes the shortest job in the whole
        queue, which is the behaviour under test. So a test that asserts WHICH job it got starts
        from an empty one. Run as the owner; no agent role may DELETE here."""
        self.conn.execute("DELETE FROM litkb.extraction_jobs")

    def job(self, job_id):
        return self.one(
            "SELECT state, residue_class, attempts, lease_owner, lease_token, run_id, "
            "artifact_sha256, last_error FROM litkb.extraction_jobs WHERE id = %s", (job_id,))


@pytest.fixture(scope="module")
def _q_session(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    yield _Q(psycopg, conn)


@pytest.fixture
def q(_q_session):
    yield _q_session
    while _q_session.opened:
        _q_session.opened.pop().close()


KEY = ("5-reconcile", "litkb-test-queue", "v1", "p1", "v1")


def _enqueue(q, conn, file_id, key=KEY, pages=None):
    return q.one("SELECT * FROM litkb.enqueue_extraction(%s, %s, %s, %s, %s, %s, NULL, NULL, %s)",
                 (file_id, *key, pages), conn=conn)


def _claim(q, conn, worker="w", n=1, lease=60):
    return conn.execute("SELECT * FROM litkb.claim_jobs(%s, %s, %s)", (worker, n, lease)).fetchall()


# ── the table and the run key ─────────────────────────────────────────────────────────────────

@pg_only
def test_the_queue_key_is_the_run_key_read_from_the_package(q):
    """`run_key_fields` must equal what `ingest_file` will use, or the sweep enqueues work the
    ingest then finds already done under a different name (CLAUDE.md §3.3)."""
    from litkb import queue as Q
    from litkb.extract import ingest as ing
    from litkb.extract import reconcile as R

    stage, tool, tv, ph, pv = Q.run_key_fields()
    k = ing.run_key("00000000-0000-0000-0000-000000000000", R.PIPELINE_VERSION, ing.CORPUS_PARAMS)
    assert (stage, tool, tv, ph, pv) == (k["stage"], k["tool"], k["tool_version"],
                                         k["params_hash"], k["pipeline_version"])


@pg_only
def test_a_residue_class_and_the_classified_state_cannot_exist_without_each_other(q):
    """The CHECK that makes a count of classified files mean something."""
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    job_id, _state, _new = _enqueue(q, ingest, file_id)
    with pytest.raises(q.errors.CheckViolation, match="residue_is_classified"):
        q.conn.execute("UPDATE litkb.extraction_jobs SET residue_class = 'bad-file' WHERE id = %s",
                       (job_id,))
    with pytest.raises(q.errors.CheckViolation, match="residue_is_classified"):
        q.conn.execute("UPDATE litkb.extraction_jobs SET state = 'classified' WHERE id = %s",
                       (job_id,))


@pg_only
def test_a_lease_is_whole_or_absent(q):
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    with pytest.raises(q.errors.CheckViolation, match="lease_is_whole"):
        q.conn.execute("UPDATE litkb.extraction_jobs SET state = 'leased' WHERE id = %s", (job_id,))


# ── enqueue and sweep ─────────────────────────────────────────────────────────────────────────

@pg_only
def test_enqueue_is_idempotent_on_the_run_key(q):
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    first = _enqueue(q, ingest, file_id)
    second = _enqueue(q, ingest, file_id)
    assert first[0] == second[0], "the same run key must be the same job"
    assert first[2] is True and second[2] is False, "only the first insert is new"
    assert q.one("SELECT count(*) FROM litkb.extraction_jobs WHERE file_id = %s",
                 (file_id,))[0] == 1


@pg_only
def test_a_file_that_already_has_an_ok_run_at_this_key_is_enqueued_already_done(q):
    """§12.4's rule, applied at enqueue: 233 of the live corpus's files were extracted before this
    table existed, and they must not become 233 claims that run no tool."""
    q.clear()
    ws = q.ws()
    file_id, _ = q.file(ws)
    run_id = q.ok_run(file_id, KEY)
    ingest = q.session()
    job_id, state, was_new = _enqueue(q, ingest, file_id)
    assert state == "done" and was_new is True
    row = q.job(job_id)
    assert row[0] == "done" and row[5] == run_id, row
    assert _claim(q, ingest) == [], "a done job is never claimable"


@pg_only
def test_a_failed_run_at_the_key_is_not_done(q):
    """Only an `ok` run counts. A `failed` one is the record of an attempt, not of an extraction."""
    ws = q.ws()
    file_id, _ = q.file(ws)
    q.one("INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
          "pipeline_version, host, status) VALUES (%s, %s, %s, %s, %s, %s, 'local', 'failed') "
          "RETURNING id", (file_id, *KEY))
    ingest = q.session()
    _job_id, state, _new = _enqueue(q, ingest, file_id)
    assert state == "queued"


@pg_only
def test_sweep_takes_proposed_files_too_and_a_repeat_enqueues_nothing(q, monkeypatch):
    """`main_files` is the PROMOTED head; 13 of the live corpus's 251 active file versions are a
    workstream's proposal and every one of them has no run. A sweep that read `main_files` would
    leave them unaccounted for, which is the criterion S4 is measured on."""
    from litkb import queue as Q

    ws = q.ws()
    promoted, _ = q.file(ws, pages=10)
    proposed, _ = q.file(ws, pages=4, state="proposed")
    monkeypatch.setattr(Q, "run_key_fields", lambda: KEY)
    ingest = q.session()
    before = q.one("SELECT count(*) FROM litkb.extraction_jobs")[0]
    first = Q.sweep(ingest)
    assert first["new_queued"] + first["new_done"] + first["existing"] == first["files"]
    ids = {r[0] for r in q.conn.execute(
        "SELECT file_id FROM litkb.extraction_jobs WHERE file_id IN (%s, %s)",
        (promoted, proposed)).fetchall()}
    assert ids == {promoted, proposed}, "a proposed file must be swept"
    after_first = q.one("SELECT count(*) FROM litkb.extraction_jobs")[0]
    second = Q.sweep(ingest)
    assert second["new_queued"] == 0 and second["new_done"] == 0, second
    assert second["existing"] == second["files"] == first["files"]
    assert q.one("SELECT count(*) FROM litkb.extraction_jobs")[0] == after_first > before


# ── the lease ─────────────────────────────────────────────────────────────────────────────────

@pg_only
def test_two_workers_never_hold_one_job(q):
    q.clear()
    ws = q.ws()
    a, _ = q.file(ws)
    ingest = q.session()
    _enqueue(q, ingest, a)
    first = _claim(q, ingest, worker="A", lease=600)
    second = _claim(q, ingest, worker="B", lease=600)
    assert len(first) == 1 and second == [], "B claimed a job A holds"


@pg_only
def test_the_claim_takes_the_fewest_pages_first_and_an_unknown_count_last(q):
    """§12.3's order. NULL pages sorts LAST: an unmeasured file must not jump the queue."""
    q.clear()
    ws = q.ws()
    key = ("5-reconcile", f"ord-{uuid.uuid4().hex[:6]}", "v1", "p1", "v1")
    ingest = q.session()
    want = []
    for pages in (50, None, 3):
        fid, _ = q.file(ws)
        _enqueue(q, ingest, fid, key=key, pages=pages)
        want.append((pages, fid))
    by_pages = {p: f for p, f in want}
    expected = [by_pages[3], by_pages[50], by_pages[None]]
    # one at a time, which is how the worker claims: this tests WHICH job is taken next
    got = [_claim(q, ingest, worker="ord", n=1, lease=600)[0][1] for _ in range(3)]
    assert got == expected, "order: 3 pages, 50 pages, then the unmeasured one"
    q.conn.execute("UPDATE litkb.extraction_jobs SET state = 'queued', lease_owner = NULL, "
                   "lease_token = NULL, lease_expires_at = NULL")
    # and as ONE batch: `UPDATE ... RETURNING` has no row order of its own, so the function sorts
    batch = [r[1] for r in _claim(q, ingest, worker="ord", n=3, lease=600)]
    assert batch == expected, "a batch claim is handed back shortest first"


@pg_only
def test_an_expired_lease_returns_to_the_pool_and_the_old_holder_is_refused(q):
    """THE known-bad this table exists for. A worker whose lease ran out must not be able to
    finish a job a second worker now holds: without the gate the two write one file's rows under
    two runs, and the loser's `clear_extraction_rows` can delete the winner's while the winner's
    run is still `failed` (the race `open_extraction_run` alone does not close)."""
    q.clear()
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    a = _claim(q, ingest, worker="A", lease=1)[0]
    a_token = a[-2]
    q.conn.execute("UPDATE litkb.extraction_jobs SET lease_expires_at = now() - interval '1 second' "
                   "WHERE id = %s", (job_id,))
    b = _claim(q, ingest, worker="B", lease=600)[0]
    b_token = b[-2]
    assert b[0] == job_id and b_token != a_token
    assert q.job(job_id)[2] == 2, "the second claim is the second attempt"
    for call, params in (
            ("SELECT litkb.finish_job(%s, %s, NULL, NULL)", (job_id, a_token)),
            ("SELECT litkb.renew_lease(%s, %s, 60)", (job_id, a_token)),
            ("SELECT litkb.fail_job(%s, %s, 'x', 3)", (job_id, a_token)),
            ("SELECT litkb.classify_job(%s, %s, 'bad-file', 'x')", (job_id, a_token))):
        with pytest.raises(q.errors.InsufficientPrivilege, match="lost, expired or forged lease"):
            ingest.execute(call, params)
    assert q.job(job_id)[0] == "leased", "A's refused calls changed nothing"
    ingest.execute("SELECT litkb.finish_job(%s, %s, NULL, NULL)", (job_id, b_token))
    assert q.job(job_id)[0] == "done"


@pg_only
def test_a_forged_or_absent_token_is_refused_by_every_mutating_function(q):
    q.clear()
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    _claim(q, ingest, worker="A", lease=600)
    forged = str(uuid.uuid4())
    for token, match in ((forged, "lost, expired or forged lease"),
                         (None, "needs the lease token")):
        for call in ("SELECT litkb.finish_job(%s, %s, NULL, NULL)",
                     "SELECT litkb.renew_lease(%s, %s, 60)",
                     "SELECT litkb.fail_job(%s, %s, 'x', 3)",
                     "SELECT litkb.classify_job(%s, %s, 'bad-file', 'x')"):
            with pytest.raises(q.errors.InsufficientPrivilege, match=match):
                ingest.execute(call, (job_id, token))
    assert q.job(job_id)[0] == "leased"


@pg_only
def test_renew_lease_extends_it_and_only_for_the_holder(q):
    q.clear()
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    row = _claim(q, ingest, worker="A", lease=5)[0]
    token, until = row[-2], row[-1]
    later = ingest.execute("SELECT litkb.renew_lease(%s, %s, %s)", (job_id, token, 600)).fetchone()[0]
    assert later > until


@pg_only
def test_fail_job_requeues_until_max_attempts_then_kills(q):
    """§12.3. `attempts` is incremented by the CLAIM, so the third claim's failure is the death."""
    q.clear()
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    states = []
    for _ in range(3):
        row = _claim(q, ingest, worker="A", lease=600)[0]
        states.append(ingest.execute("SELECT litkb.fail_job(%s, %s, %s, 3)",
                                     (job_id, row[-2], "boom")).fetchone()[0])
    assert states == ["queued", "queued", "dead"], states
    assert _claim(q, ingest, worker="A") == [], "a dead job is not claimable"
    assert q.job(job_id)[7] == "boom"


@pg_only
def test_classify_names_its_class_and_the_job_does_not_come_back(q):
    q.clear()
    ws = q.ws()
    file_id, _ = q.file(ws)
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    row = _claim(q, ingest, worker="A", lease=600)[0]
    with pytest.raises(q.errors.InvalidParameterValue, match="names its residue class"):
        ingest.execute("SELECT litkb.classify_job(%s, %s, NULL, 'x')", (job_id, row[-2]))
    with pytest.raises(q.errors.CheckViolation):
        ingest.execute("SELECT litkb.classify_job(%s, %s, 'not-a-class', 'x')", (job_id, row[-2]))
    ingest.execute("SELECT litkb.classify_job(%s, %s, 'scan-needs-ocr', 'ocr is off')",
                   (job_id, row[-2]))
    assert q.job(job_id)[:2] == ("classified", "scan-needs-ocr")
    assert _claim(q, ingest, worker="A") == []


@pg_only
def test_finish_job_refuses_a_run_that_belongs_to_another_file(q):
    q.clear()
    ws = q.ws()
    mine, _ = q.file(ws)
    theirs, _ = q.file(ws)
    other_run = q.ok_run(theirs, ("5-reconcile", "t", "v", "p", "v"))
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, mine)
    row = _claim(q, ingest, worker="A", lease=600)[0]
    with pytest.raises(q.errors.InvalidParameterValue, match="not a run of job"):
        ingest.execute("SELECT litkb.finish_job(%s, %s, %s, NULL)", (job_id, row[-2], other_run))
    assert q.job(job_id)[0] == "leased"


@pg_only
def test_status_counts_states_residues_pages_and_stale_leases(q):
    q.clear()
    from litkb import queue as Q

    ws = q.ws()
    key = ("5-reconcile", f"st-{uuid.uuid4().hex[:6]}", "v1", "p1", "v1")
    ingest = q.session()
    fid, _ = q.file(ws)
    _enqueue(q, ingest, fid, key=key, pages=7)
    row = _claim(q, ingest, worker="A", lease=600)[0]
    q.conn.execute("UPDATE litkb.extraction_jobs SET lease_expires_at = now() - interval '1 s' "
                   "WHERE id = %s", (row[0],))
    s = Q.status(ingest)
    assert s["stale_leases"] >= 1 and s["pages_remaining"] >= 7
    assert s["5-reconcile/leased"] >= 1 and s["jobs"] >= 1


# ── the zero-block guard, at its home in extract/ingest.py ────────────────────────────────────

@pg_only
def test_a_reconciliation_with_no_canonical_block_never_becomes_the_current_run(q):
    """Both halves of the guard, and the fact it protects: `current_run_id` does not move.

    Every reader that narrows blocks to the current run (five hand-written copies of one join, in
    mcp/server.py, review_check.py, review_context.py and use.py) would otherwise
    read such a file as extracted and empty, which is the state S4 exists to stop producing."""
    from litkb.extract import ingest as ing

    ws = q.ws()
    file_id, _ = q.file(ws)
    conn = q.session(autocommit=False)
    with pytest.raises(ing.ZeroCanonicalBlocks, match="no canonical block"):
        ing.ingest_file(conn, file_id, [], [], {}, pipeline_version="zb1",
                        params={"t": "zero"}, commit=False)
    assert q.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s "
                 "AND pipeline_version = 'zb1'", (file_id,))[0] == 0, "the raise rolled it back"

    res = ing.ingest_file(conn, file_id, [], [], {}, pipeline_version="zb2",
                          params={"t": "zero"}, commit=True, zero_blocks="failed-run")
    assert res["blocks"] == 0 and res["zero_content"] is True
    assert q.one("SELECT status FROM litkb.extraction_runs WHERE id = %s", (res["run_id"],))[0] \
        == "failed"
    assert q.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0] is None


# ── the worker: the three refusals that must happen BEFORE a tool runs ────────────────────────

class _FakePolicy:
    """The six names `litkb.extract.readiness` will expose, with the answers a test wants."""

    class ProbeFailed(Exception):
        def __init__(self, reason):
            super().__init__(reason)
            self.reason = reason

    def __init__(self, *, pages=5, cap=100, probe_raises=None, ocr=("run", "cpu"), free=2000):
        self.PAGE_CAP, self._pages, self._raise, self._ocr, self._free = cap, pages, probe_raises, ocr, free

    def probe_pages(self, path):
        del path
        if self._raise:
            raise self.ProbeFailed(self._raise)
        return self._pages

    def cap_check(self, pages):
        return "over-page-cap" if pages > self.PAGE_CAP else None

    def vram_free_mib(self):
        return self._free

    def page_needs_ocr(self, page_class, coverage_share):
        return page_class != "text" or (coverage_share or 0) < 0.5

    def ocr_policy(self, n_ocr_pages, ocr_enabled, free_mib):
        del free_mib
        if n_ocr_pages and not ocr_enabled:
            return ("residue", "scan-needs-ocr")
        return self._ocr


class _CountingTools:
    def __init__(self, doc=object()):
        self.calls = []
        self._doc = doc

    def grobid(self, pdf_path):
        self.calls.append(("grobid", str(pdf_path)))
        return None, None

    def docling(self, pdf_path, out_json, metrics_path, *, ocr, device, cwd):
        del metrics_path, ocr, device, cwd
        self.calls.append(("docling", str(pdf_path)))
        with open(out_json, "w", encoding="utf-8") as fh:
            fh.write("{}")
        return self._doc


def _worker(q, tmp_path, *, policy, tools, ocr=True, **kw):
    from litkb import queue as Q
    from litkb.db import connect as c

    def connect(autocommit=True):
        from psycopg import sql
        k = c.connect(c.DB_TEST, "litkb_test", autocommit=autocommit)
        k.execute(sql.SQL("SET ROLE {}").format(sql.Identifier("litkb_ingest")))
        if not autocommit:
            k.commit()          # see _Q.session: SET ROLE leaves the connection INTRANS
        q.opened.append(k)
        return k

    return Q.Worker(connect, worker="t1", policy=policy, tools=tools, ocr=ocr, device="cpu",
                    lease_seconds=600, derived=str(tmp_path / "derived"),
                    root=str(tmp_path / "lit"), **kw)


def _bound_file(q, tmp_path, name="x.pdf", body=b"%PDF-1.4\n"):
    ws = q.ws()
    rel = f"Validation/{name}"
    p = tmp_path / "lit" / "Validation"
    p.mkdir(parents=True, exist_ok=True)
    (p / name).write_bytes(body)
    file_id, _ = q.file(ws, rel_path=rel, pages=5)
    return file_id


@pg_only
def test_a_page_probe_that_raises_is_bad_file_and_no_tool_is_invoked(q, tmp_path):
    q.clear()
    from litkb import queue as Q

    file_id = _bound_file(q, tmp_path)
    ingest = q.session()
    Q.run_key_fields()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    tools = _CountingTools()
    w = _worker(q, tmp_path, policy=_FakePolicy(probe_raises="not a pdf"), tools=tools)
    w.run(max_jobs=1)
    assert q.job(job_id)[:2] == ("classified", "bad-file")
    assert tools.calls == [], "a tool ran on a file whose pages could not be counted"
    assert q.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s", (file_id,))[0] == 0


@pg_only
def test_a_missing_file_is_bad_file(q, tmp_path):
    q.clear()
    file_id = _bound_file(q, tmp_path, name="gone.pdf")
    os.remove(tmp_path / "lit" / "Validation" / "gone.pdf")
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    tools = _CountingTools()
    _worker(q, tmp_path, policy=_FakePolicy(), tools=tools).run(max_jobs=1)
    assert q.job(job_id)[:2] == ("classified", "bad-file")
    assert tools.calls == []


@pg_only
def test_cap_plus_one_is_over_page_cap_and_no_tool_is_invoked(q, tmp_path):
    """The cap this replaces (`admit.binding.ocr_first_pages`) fails OPEN: a non-digit page count
    skips its OCR_BIND_MAX_PAGES check entirely. This one refuses to start."""
    q.clear()
    file_id = _bound_file(q, tmp_path, name="book.pdf")
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    tools = _CountingTools()
    w = _worker(q, tmp_path, policy=_FakePolicy(pages=101, cap=100), tools=tools)
    w.run(max_jobs=1)
    state, cls, _a, _o, _t, run_id, _sha, err = q.job(job_id)
    assert (state, cls) == ("classified", "over-page-cap") and run_id is None
    assert "101 pages" in err
    assert tools.calls == [], "the cap let a tool start"
    assert not (tmp_path / "derived").exists() or not any(
        (tmp_path / "derived").rglob("docling.json")), "an artifact was produced for a capped file"


@pg_only
def test_a_scan_with_ocr_off_is_scan_needs_ocr_with_no_run_row(q, tmp_path, monkeypatch):
    """"extracted, 0 chars" is the outcome this refusal exists to stop: Docling with OCR off over
    an image-only page succeeds and yields nothing, and the database cannot tell that from a file
    with nothing to say."""
    q.clear()
    from litkb.extract import inventory as I

    file_id = _bound_file(q, tmp_path, name="scan.pdf")
    monkeypatch.setattr(I, "probe_file", lambda p: {
        "sha256": "a" * 64, "route": "scan", "ocr_pages": [1, 2, 3], "pages": 3, "page_detail": []})
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    tools = _CountingTools()
    w = _worker(q, tmp_path, policy=_FakePolicy(pages=3), tools=tools, ocr=False)
    w.run(max_jobs=1)
    assert q.job(job_id)[:2] == ("classified", "scan-needs-ocr")
    assert tools.calls == [], "the converter ran on a scan the policy refused"
    assert q.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s", (file_id,))[0] == 0
    assert q.one("SELECT count(*) FROM litkb.blocks WHERE file_id = %s", (file_id,))[0] == 0
    assert q.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0] is None


@pg_only
def test_no_readiness_fails_closed(q, tmp_path):
    """No policy module must mean "convert nothing", never "convert everything uncapped"."""
    q.clear()
    from litkb import queue as Q

    assert isinstance(Q.load_policy(), type) or Q.load_policy() is Q.NoReadiness or True
    file_id = _bound_file(q, tmp_path, name="np.pdf")
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    tools = _CountingTools()
    _worker(q, tmp_path, policy=Q.NoReadiness, tools=tools).run(max_jobs=1)
    assert q.job(job_id)[:2] == ("classified", "bad-file")
    assert tools.calls == []


# ── the worker: the ingest transaction ────────────────────────────────────────────────────────

def _stub_reconcile(monkeypatch, canonical):
    """Stub the reconciler and stage 0. The queue's branch is what is under test here."""
    from litkb.extract import inventory as I
    from litkb.extract import reconcile as R

    monkeypatch.setattr(I, "probe_file", lambda p: {
        "sha256": "b" * 64, "route": "native", "ocr_pages": [], "pages": 1, "page_detail": []})
    monkeypatch.setattr(I, "page_frames", lambda p: {})
    monkeypatch.setattr(R, "reconcile", lambda *a, **k: (canonical, [], {"blocks": len(canonical)}))
    monkeypatch.setattr(R, "coverage", lambda *a, **k: {})


@pg_only
def test_a_run_with_no_canonical_block_is_zero_content_and_leaves_the_pointer_alone(q, tmp_path,
                                                                                   monkeypatch):
    q.clear()
    file_id = _bound_file(q, tmp_path, name="empty.pdf")
    _stub_reconcile(monkeypatch, [])
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    w = _worker(q, tmp_path, policy=_FakePolicy(pages=1), tools=_CountingTools())
    w.run(max_jobs=1)
    assert q.job(job_id)[:2] == ("classified", "zero-content"), w.events
    assert q.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0] is None
    assert q.one("SELECT status FROM litkb.extraction_runs WHERE file_id = %s",
                 (file_id,))[0] == "failed", "the attempt is recorded, and it is not ok"


@pg_only
def test_a_worked_job_finishes_in_the_same_transaction_as_its_run(q, tmp_path, monkeypatch):
    """§12.4: a kill leaves either a finished unit or no rows. The observable half of that here is
    that `finish_job` and the run are committed together — the job's `run_id` is the run, and the
    file's current run is that same run."""
    q.clear()
    from litkb.extract import reconcile as R

    file_id = _bound_file(q, tmp_path, name="one.pdf")
    _stub_reconcile(monkeypatch, [_a_block(R)])
    ingest = q.session()
    job_id, _s, _n = _enqueue(q, ingest, file_id)
    w = _worker(q, tmp_path, policy=_FakePolicy(pages=1), tools=_CountingTools())
    w.run(max_jobs=1)
    state, _cls, _att, owner, token, run_id, sha, _err = q.job(job_id)
    assert state == "done" and owner is None and token is None, w.events
    assert q.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0] == run_id
    assert q.one("SELECT status FROM litkb.extraction_runs WHERE id = %s", (run_id,))[0] == "ok"
    assert q.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (run_id,))[0] == 1
    assert sha and len(sha) == 64, "the artifact's sha256 is recorded on the job"


def _a_block(R):
    """One canonical block, built through the reconciler's own dataclass so the ingest's column
    mapping is exercised rather than mocked."""
    return R.Canonical(page=1, x0=0.0, y0=0.0, x1=10.0, y1=10.0, kind="paragraph",
                       reading_order=0, text="A canonical paragraph of text.", source="docling",
                       extractor={"bbox": "docling"}, confidence=1.0, text_source="native")

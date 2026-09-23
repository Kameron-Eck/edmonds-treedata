"""litkb S4 — the extraction queue (migration 0029, litkb/extract/queue.py) and its known-bads.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_queue.py -q

Groups:

* **pure** — the guard, the chunking, the digest, the page-range assembly, the device pair. No
  database;
* **the queue on litkb_test** — enqueue guards, claim-time re-checks, the lease gate at every holder
  call, reclaim, the attempt ceiling, the append-only history, the worker end to end with the
  SYNTHETIC extractor (CONSTRUCTED Docling documents) where the claim is about the queue's logic;
* **the known-bads (plan "### S4" (c))** — ``queue_fire.fire_cap / fire_book / fire_scan /
  fire_lease / fire_kill``: each arm GUARDED must leave its counter at baseline and each arm MUTATED
  (the guard switched off in-process) must move it by exactly one;
* **real tools** — GROBID + Docling on real corpus copies (the kill/rerun digest equality, the OCR
  page-range run on CUDA with its VRAM peak). They take minutes and a GPU, so they run only with
  ``LITKB_REAL_EXTRACT=1``; their measured output is recorded in the S4 run 3 builder-A report.

Every PDF a test touches is either CONSTRUCTED here (named so) or a COPY of a corpus file in a
pytest tmp dir; artifacts go under that tmp dir, never ``litkb_derived``.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

import pytest

from litkb.extract import probe as P
from litkb.extract import queue as Q
from litkb.extract import queue_fire as F

from test_litkb_p1 import _PG  # noqa: E402 - the P1 harness class, not its fixture

pg_only = pytest.mark.requires_litkb_pg
REAL = os.environ.get("LITKB_REAL_EXTRACT") == "1"
real_only = pytest.mark.skipif(not REAL, reason="real GROBID/Docling run: set LITKB_REAL_EXTRACT=1")
MIG = pathlib.Path(__file__).resolve().parents[1] / "pipeline" / "litkb" / "db" / "migrations"
CORPUS = F.CORPUS


@pytest.fixture(scope="session")
def _q(litkb_pg_base):
    psycopg, conn, ran = litkb_pg_base
    yield _PG(psycopg, conn, ran)


@pytest.fixture
def pg(_q):
    yield _q
    while _q.opened:
        _q.opened.pop().close()


@pytest.fixture
def root(tmp_path):
    return tmp_path


def _k():
    from litkb.db import connect as c
    return Q.connect(c.DB_TEST)


def _db():
    from litkb.db import connect as c
    return c.DB_TEST


def _file(pg, root, name, pages, *, text=True, work_type="article", note=None, pdf=None):
    ws = F.open_ws(pg.conn)
    pdf = pdf or F.constructed_pdf(root / "Validation" / f"{name}.pdf", pages, text=text,
                                   note=note or uuid.uuid4().hex)
    return F.add_file(pg.conn, ws, F.add_work(pg.conn, ws, work_type), pdf, root), pdf


def _work(root, files, extractor=None, **kw):
    return Q.work(_k, root, extractor=extractor or F.SyntheticExtractor(), derived=root / "_derived",
                  files=files, **kw)


def _sweep(root, files, **kw):
    k = _k()
    try:
        return Q.sweep(k, root, files=files, **kw)
    finally:
        k.close()


def _jobs(pg, fid):
    return F.file_jobs(pg.conn, fid)


# ── pure ────────────────────────────────────────────────────────────────────────────────

def test_the_vocabularies_are_the_migrations():
    """STATES and REFUSALS are the two CHECKs of migration 0029, and the attempt ceiling has ONE home
    (the SQL function): the Python module does not restate it."""
    sql = (MIG / "0029_extraction_jobs.sql").read_text(encoding="utf-8")
    assert "CHECK (state IN ('queued', 'leased', 'staged', 'done', 'dead', 'refused'))" in sql
    assert "CHECK (state IN (" + ", ".join(f"'{s}'" for s in Q.STATES) + "))" in sql
    assert "('" + "', '".join(Q.REFUSALS) + "')" in sql
    assert "RETURNS integer\nLANGUAGE sql IMMUTABLE AS $$ SELECT 3 $$;" in sql
    src = pathlib.Path(Q.__file__).read_text(encoding="utf-8")
    assert "MAX_JOB_ATTEMPTS" not in src and "_job_max_attempts" not in src


def test_guard_decides_every_refusal_on_constructed_files(tmp_path):
    """Each refusal on its own CONSTRUCTED input, and the two routes on clean ones."""
    native = F.constructed_pdf(tmp_path / "native.pdf", 2)
    blank = F.constructed_pdf(tmp_path / "blank.pdf", 3, text=False)
    corrupt = F.corrupt_pdf(tmp_path / "corrupt.pdf")
    html = tmp_path / "page.pdf"
    html.write_bytes(b"<html><body>sign in</body></html>")
    over = F.constructed_pdf(tmp_path / "over.pdf", P.EXTRACT_PAGE_CAP + 1, text=False, raster=False)
    empty = F.constructed_pdf(tmp_path / "empty.pdf", 2, text=False, raster=False)
    mixed = F.constructed_pdf(tmp_path / "mixed.pdf", 4, scan_pages=(3,))
    sha = Q.sha256_file

    def g(path, work_type="article", ocr=True, digest=None):
        return Q.guard_file(path, digest or sha(path), work_type, ocr=ocr)

    assert g(native, "book").refusal == "book"
    assert g(tmp_path / "missing.pdf", digest="0" * 64).refusal == "bad-file"
    assert g(html).refusal == "bad-file"
    assert g(native, digest="f" * 64).refusal == "bad-file"
    assert g(corrupt).refusal == "probe-error"
    f = g(over)
    assert (f.refusal, f.pages) == ("over-page-cap", P.EXTRACT_PAGE_CAP + 1)
    f = g(blank, ocr=False)
    assert (f.refusal, f.route, f.image_pages) == ("scan-needs-ocr", "ocr", [1, 2, 3])
    f = g(blank)
    assert (f.refusal, f.route, f.pages) == (None, "ocr", 3)
    f = g(native)
    assert (f.refusal, f.route, f.image_pages) == (None, "native", [])
    f = g(empty)                                  # D13: a blank page with no raster is NOT an image page
    assert (f.refusal, f.route, f.image_pages) == (None, "native", [])
    f = g(mixed)
    assert (f.refusal, f.route, f.image_pages) == (None, "ocr", [3])
    assert g(mixed, ocr=False).refusal == "scan-needs-ocr"


def test_chunk_ranges_cover_the_file_in_ocr_chunk_pages():
    assert Q.OCR_CHUNK_PAGES == 22
    assert Q.chunk_ranges(22) == [(1, 22)]
    assert Q.chunk_ranges(24) == [(1, 22), (23, 24)]
    assert Q.chunk_ranges(50) == [(1, 22), (23, 44), (45, 50)]


def test_blocks_digest_is_order_free_and_unambiguous():
    a = [(2, 0, "paragraph", "b"), (1, 1, "heading", "a\nx")]
    assert Q.blocks_digest(a) == Q.blocks_digest(list(reversed(a)))
    # a tab or newline inside the text cannot forge a boundary between two blocks
    assert Q.blocks_digest([(1, 0, "p", "x\n[1,1,\"p\",\"y\"]")]) != Q.blocks_digest(
        [(1, 0, "p", "x"), (1, 1, "p", "y")])
    assert Q.blocks_digest([(1, 0, "p", None)]) == Q.blocks_digest([(1, 0, "p", "")])


def test_assemble_keeps_absolute_pages_and_refuses_a_bad_tiling(tmp_path):
    pdf = F.constructed_pdf(tmp_path / "blank.pdf", 5, text=False)
    parts = [(1, 2, F.synthetic_doc(pdf, (1, 2))), (3, 5, F.synthetic_doc(pdf, (3, 5)))]
    doc = Q.assemble(parts, 5)
    assert sorted(int(k) for k in doc["pages"]) == [1, 2, 3, 4, 5]
    assert [t["self_ref"] for t in doc["texts"]] == [f"#/texts/{i}" for i in range(5)]
    assert [c["$ref"] for c in doc["body"]["children"]] == [f"#/texts/{i}" for i in range(5)]
    assert [t["prov"][0]["page_no"] for t in doc["texts"]] == [1, 2, 3, 4, 5]
    with pytest.raises(Q.AssemblyError):                        # a gap
        Q.assemble([parts[0], (4, 5, F.synthetic_doc(pdf, (4, 5)))], 5)
    with pytest.raises(Q.AssemblyError):                        # short of the end
        Q.assemble(parts[:1], 5)
    with pytest.raises(Q.AssemblyError):                        # a range that names another page
        Q.assemble([(1, 2, F.synthetic_doc(pdf, (1, 3))), (3, 5, parts[1][2])], 5)


def test_the_post_condition_reads_the_image_pages_only():
    """Anderson 1957's shape: page 1 is a cover with a native text layer (NOT an image page, D13),
    pages 2-22 are image pages. Text on page 1 alone is not OCR having read anything."""
    img = list(range(2, 23))
    assert Q.ocr_read_nothing(img, [(1, "x" * 158)]) is True
    assert Q.ocr_read_nothing(img, [(1, "x" * 158), (5, "read")]) is False
    assert Q.ocr_read_nothing([], [(1, "")]) is False                   # no image page: not judged
    assert Q.ocr_chars(img, [(1, "abc"), (2, "def"), (30, "zz")]) == 3


def test_the_scan_definition_is_the_majority_of_pages():
    """S4 run 3 ruling on builder-A Q1: a scan is a file whose image pages OUTNUMBER its native-text
    pages. Anderson 1957's shape (21 image pages, one native-text cover) is a scan; a native paper
    with one caption-less picture page is not; a tie is not; blank pages count on neither side."""
    anderson_chars = [158] + [0] * 21
    assert Q.is_scan(anderson_chars, list(range(2, 23))) is True
    assert Q.is_scan([900, 850, 0, 870], [3]) is False                  # one picture among text pages
    assert Q.is_scan([900, 0], [2]) is False                            # 1 against 1: not a majority
    assert Q.is_scan([0, 0, 0], [1, 2]) is True                         # page 3 blank: neither side
    assert Q.native_text_pages([0, 5, None, 1]) == 2
    assert Q.textless_image_pages([2, 3, 4], [(2, "read"), (3, "  "), (1, "x")]) == [3, 4]


def test_a_cuda_request_the_interpreter_cannot_serve_is_refused_by_name(monkeypatch, tmp_path):
    """S4 run 3 decision D4, on a CONSTRUCTED interpreter (a .cmd that answers the CUDA probe "0"):
    `cuda` on it is refused BEFORE anything runs, `auto` resolves to `cpu`, and the queue worker
    refuses at start, before it has even connected. (The project's own py -3.12 carries a CUDA
    torch on this machine, so it cannot stand in.) The real pair (venv-docling, torch +cpu) is
    test_real_cuda_under_the_cpu_venv_is_refused_by_name."""
    from litkb.extract import docling as D

    fake = tmp_path / "no_cuda_python.cmd"
    fake.write_text("@echo off\r\n<nul set /p=0\r\n", encoding="ascii")
    monkeypatch.setattr(D, "run", lambda *a, **k: pytest.fail("docling ran on a refused pair"))
    assert D.interpreter_has_cuda(str(fake)) is False
    with pytest.raises(D.DeviceUnavailable):
        D.device_pair("cuda", str(fake))
    assert D.device_pair("auto", str(fake)) == ("cpu", str(fake))
    assert D.device_pair("cpu", str(fake)) == ("cpu", str(fake))
    with pytest.raises(D.DeviceUnavailable):
        Q.work(lambda: pytest.fail("the worker connected before refusing"), device="cuda",
               python=str(fake))


def test_a_docling_timeout_is_a_docling_error(monkeypatch, tmp_path):
    from litkb.extract import docling as D

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="docling", timeout=1)

    monkeypatch.setattr(D.subprocess, "run", boom)
    with pytest.raises(D.DoclingError, match="timeout"):
        D.run([{"pdf": "x.pdf", "out": str(tmp_path / "o.json")}], str(tmp_path / "m.jsonl"),
              python=sys.executable)


def test_the_cli_parses_the_queue_verbs():
    from litkb import commands

    p = commands.build_parser()
    a = p.parse_args(["--db", "litkb_test_w0", "queue", "work", "--max-jobs", "2", "--no-ocr",
                      "--device", "cpu", "--file", "x"])
    assert (a.cmd, a.queue_cmd, a.max_jobs, a.no_ocr, a.device, a.files) == \
        ("queue", "work", 2, True, "cpu", ["x"])
    assert p.parse_args(["queue", "sweep", "--workstream", "w"]).workstream == ["w"]
    assert p.parse_args(["queue", "status"]).queue_cmd == "status"
    assert "queue" in commands._OWN_LOGINS


def test_the_test_extractor_seam_is_refused_on_litkb(monkeypatch):
    monkeypatch.setenv(Q.TEST_EXTRACTOR_ENV, "synthetic")
    with pytest.raises(RuntimeError, match="test seam"):
        Q.seam_extractor("litkb")
    assert isinstance(Q.seam_extractor("litkb_test_w0"), F.SyntheticExtractor)
    monkeypatch.delenv(Q.TEST_EXTRACTOR_ENV)
    assert Q.seam_extractor("litkb") is None


# ── the queue, against litkb_test ───────────────────────────────────────────────────────

@pg_only
def test_sweep_refuses_every_guard_at_enqueue_and_nothing_refused_is_claimed(pg, root):
    """Enqueue-side guards, all fail-closed, each a `refused` job that claim_jobs never returns."""
    book, _ = _file(pg, root, "Book", 2, work_type="book")
    over, _ = _file(pg, root, "Over", P.EXTRACT_PAGE_CAP + 1, text=False)
    scan, _ = _file(pg, root, "Scan", 3, text=False)
    ws = F.open_ws(pg.conn)
    corrupt = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws),
                         F.corrupt_pdf(root / "Validation" / "Corrupt.pdf", uuid.uuid4().hex), root)
    gone_pdf = F.constructed_pdf(root / "Validation" / "Gone.pdf", 1, note=uuid.uuid4().hex)
    gone = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), gone_pdf, root)
    gone_pdf.unlink()
    files = [book, over, scan, corrupt, gone]
    out = _sweep(root, files, ocr=False)
    assert out["refused"] == {"book": 1, "over-page-cap": 1, "scan-needs-ocr": 1, "probe-error": 1,
                              "bad-file": 1}, out
    want = {book: "book", over: "over-page-cap", scan: "scan-needs-ocr", corrupt: "probe-error",
            gone: "bad-file"}
    for f, why in want.items():
        assert _jobs(pg, f) == [("refused", why, 0, None, None)], (why, _jobs(pg, f))
    rep = _work(root, files)
    assert rep["claimed"] == 0
    assert all(F.blocks_of(pg.conn, f) == 0 for f in files)


@pg_only
def test_a_second_sweep_adds_nothing(pg, root):
    a, _ = _file(pg, root, "Twice", 2)
    b, _ = _file(pg, root, "TwiceScan", 30, text=False)
    first = _sweep(root, [a, b])
    assert first["enqueued"] == 1 + 2 and first["refused"] == {}
    assert _sweep(root, [a, b])["enqueued"] == 0
    assert [r[3] for r in _jobs(pg, b)] == [1, 23]
    _work(root, [a, b])


@pg_only
def test_an_ocr_off_refusal_is_reopened_by_a_sweep_with_ocr_on(pg, root):
    f, _ = _file(pg, root, "Reopen", 3, text=False)
    assert _sweep(root, [f], ocr=False)["refused"] == {"scan-needs-ocr": 1}
    assert _sweep(root, [f], ocr=False)["enqueued"] == 0
    assert _sweep(root, [f], ocr=True)["enqueued"] == 1
    rep = _work(root, [f])
    assert rep["outcomes"] == {"done": 1}
    assert {r[0] for r in _jobs(pg, f)} == {"refused", "done"}


@pg_only
def test_the_claim_rechecks_the_python_guards(pg, root):
    """A job enqueued before a guard changed is still refused AT CLAIM: here the jobs are enqueued
    straight through the SQL function with no refusal, as a sweep made before the guard would have."""
    over, over_pdf = _file(pg, root, "ClaimOver", P.EXTRACT_PAGE_CAP + 1)
    moved, moved_pdf = _file(pg, root, "ClaimMoved", 2)
    k = _k()
    try:
        for f in (over, moved):
            Q.enqueue(k, f, None, None, Q.Facts(route="native", pages=2))
    finally:
        k.close()
    moved_pdf.write_bytes(moved_pdf.read_bytes() + b"% changed on disk after the sweep\n")
    rep = _work(root, [over, moved])
    assert rep["outcomes"] == {"refused": 2}, rep
    assert _jobs(pg, over)[0][:2] == ("refused", "over-page-cap")
    assert _jobs(pg, moved)[0][:2] == ("refused", "bad-file")
    assert F.blocks_of(pg.conn, over) == F.blocks_of(pg.conn, moved) == 0


@pg_only
def test_enqueue_extraction_refuses_a_books_file_in_sql(pg, root):
    """The SQL half of the book guard at enqueue: the caller passes NO refusal and still gets one."""
    f, _ = _file(pg, root, "SqlBook", 2, work_type="book")
    k = _k()
    try:
        Q.enqueue(k, f, None, None, Q.Facts(route="native", pages=2))
    finally:
        k.close()
    assert _jobs(pg, f) == [("refused", "book", 0, None, None)]


@pg_only
def test_claim_jobs_refuses_a_work_retyped_to_book_after_enqueue(pg, root):
    """The SQL half of the book guard at claim: the work became a book after its job was queued."""
    f, _ = _file(pg, root, "Retyped", 2)
    assert _sweep(root, [f])["enqueued"] == 1
    work_id, cur, title = pg.one(
        "SELECT w.work_id, w.version_id, w.title FROM litkb.main_works w JOIN litkb.main_files f "
        "ON f.work_id = w.work_id WHERE f.file_id = %s", (f,))
    ws = F.open_ws(pg.conn)
    pg.one("SELECT litkb._write_version('fact', 'work', %s, NULL, %s, %s, 'retyped a book', %s, "
           "'setup', 'setup')",
           (work_id, cur, pg.Jsonb({"type": "book", "title": title, "authors": []}), ws))
    assert pg.one("SELECT type FROM litkb.main_works WHERE work_id = %s", (work_id,)) == ("book",)
    k = _k()
    try:
        assert Q.claim(k, "w", 5, 60, [f]) == []
    finally:
        k.close()
    assert _jobs(pg, f)[0][:2] == ("refused", "book")


def _ok_run_at_key(k, f, pdf):
    """An ok stage-5 run of file ``f`` at TODAY's run key (a synthetic document), -> its id."""
    from litkb.extract import ingest as ING
    from litkb.extract import reconcile as R

    prep = ING.prepare(str(pdf), None, F.synthetic_doc(pdf))
    return ING.ingest_file(k, f, prep["canonical"], prep["disagreements"], prep["stats"],
                           pages=prep["pages"], pipeline_version=R.PIPELINE_VERSION,
                           params=ING.CORPUS_PARAMS)["run_id"]


_HOLDER_CALLS = {
    "renew_lease": ("SELECT litkb.renew_lease(%s, %s)", ()),
    "record_artifact": ("SELECT litkb.record_artifact(%s, %s, 'x', %s, '{}'::jsonb)", ("0" * 64,)),
    "stage_chunk": ("SELECT litkb.stage_chunk(%s, %s)", ()),
    # an OK run of the job's OWN file at its key (made below), so that with the lease gate gone
    # nothing else refuses the stale finish: the test then fails on its assertion (DID NOT RAISE),
    # not on the own-run check's error (auditor-A F2)
    "finish_job": ("SELECT litkb.finish_job(%s, %s, %s, %s, '{}'::jsonb)", ("RUN", "0" * 64)),
    "fail_job": ("SELECT litkb.fail_job(%s, %s, 'x')", ()),
    "refuse_job": ("SELECT litkb.refuse_job(%s, %s, 'bad-file', 'x', 'claim')", ()),
}


@pg_only
@pytest.mark.parametrize("call", sorted(_HOLDER_CALLS))
def test_every_holder_call_refuses_a_superseded_or_forged_token(pg, root, call):
    """Each of the six lease-holder functions presents the token through its OWN guard block: a
    superseded token (T1 after T2 reclaimed) and a forged one are refused LKL01, and nothing moves."""
    f, pdf = _file(pg, root, f"Holder_{call}", 30, text=False)     # a range job, so stage_chunk applies
    _sweep(root, [f])
    k = _k()
    run = _ok_run_at_key(k, f, pdf) if call == "finish_job" else None
    try:
        (t1,) = Q.claim(k, "T1", 1, 1, [f])
        time.sleep(1.3)
        (t2,) = Q.claim(k, "T2", 1, 60, [f])
        assert t2.job_id == t1.job_id and t2.lease_seq == t1.lease_seq + 1
        sql, extra = _HOLDER_CALLS[call]
        extra = tuple(run if x == "RUN" else x for x in extra)
        before = pg.one("SELECT state, lease_seq, lease_expires_at, artifact_path FROM litkb.extraction_jobs "
                        "WHERE id = %s", (t1.job_id,))
        for token in (t1.token, uuid.uuid4().hex * 2, None):
            with pytest.raises(Q.LeaseLost):
                Q._sql(k, sql, (t1.job_id, token, *extra))
        assert pg.one("SELECT state, lease_seq, lease_expires_at, artifact_path FROM litkb.extraction_jobs "
                      "WHERE id = %s", (t1.job_id,)) == before
        Q._sql(k, "SELECT litkb.fail_job(%s, %s, 'test cleanup')", (t2.job_id, t2.token))
    finally:
        k.close()
    _work(root, [f])


@pg_only
def test_two_claims_never_share_a_job_and_a_live_lease_is_never_reclaimed(pg, root):
    """Design §14 P5 kills (c) and (d). A claims inside an open transaction (its row lock held); B's
    claim SKIPS the locked row at once instead of waiting on it. After A commits, B still gets
    nothing: A's lease is live, and only an EXPIRED lease is reclaimable."""
    f, _ = _file(pg, root, "SkipLocked", 2)
    _sweep(root, [f])
    a, b = _k(), _k()
    try:
        a.autocommit = False
        (ca,) = Q.claim(a, "A", 1, 60, [f])
        b.execute("SET lock_timeout = '2s'")
        t0 = time.monotonic()
        assert Q.claim(b, "B", 1, 60, [f]) == []
        assert time.monotonic() - t0 < 2.0
        a.commit()
        a.autocommit = True
        assert Q.claim(b, "B", 1, 60, [f]) == []
        Q._sql(a, "SELECT litkb.fail_job(%s, %s, 'test cleanup')", (ca.job_id, ca.token))
    finally:
        a.close()
        b.close()
    assert _work(root, [f])["outcomes"] == {"done": 1}


@pg_only
def test_a_job_whose_every_lease_expired_dies_at_the_ceiling(pg, root):
    """A worker that dies on a file every time never calls fail_job: the claim counts the attempts
    and, at the ceiling, the job is `dead` instead of being handed out forever."""
    f, _ = _file(pg, root, "KillsItsWorker", 2)
    _sweep(root, [f])
    ceiling = pg.one("SELECT litkb._job_max_attempts()")[0]
    k = _k()
    try:
        for i in range(ceiling):
            (c,) = Q.claim(k, f"dies-{i}", 1, 1, [f])
            assert c.attempts == i + 1
            time.sleep(1.2)
        assert Q.claim(k, "next", 1, 60, [f]) == []
    finally:
        k.close()
    state, _r, attempts, _s, _run = _jobs(pg, f)[0]
    assert (state, attempts) == ("dead", ceiling)
    assert "lease expired" in pg.one("SELECT last_error FROM litkb.extraction_jobs WHERE file_id = %s", (f,))[0]
    # design §12.3: the death is also a `failed` run at the job's key, never current
    status, m, current = _dead_run(pg, f)
    assert (status, current, m["job_state"]) == ("failed", False, "dead"), m
    assert "lease expired" in m["last_error"] and len(m["dead_jobs"]) == 1, m


def _dead_run(pg, fid):
    """The one run a dead job leaves for its file (migration 0029 ``_job_dead_run``).
    -> (status, metrics, is it the file's current run)."""
    rows = pg.conn.execute(
        "SELECT r.status, r.metrics, f.current_run_id IS NOT DISTINCT FROM r.id "
        "FROM litkb.extraction_runs r JOIN litkb.files f ON f.id = r.file_id WHERE r.file_id = %s",
        (fid,)).fetchall()
    assert len(rows) == 1, rows
    return rows[0]


@pg_only
def test_finish_job_points_a_job_only_at_an_ok_run_of_its_own_file(pg, root):
    """With a VALID token: another file's ok run is refused (22023), and so is no run at all."""
    other, _ = _file(pg, root, "OtherFile", 2)
    _sweep(root, [other])
    _work(root, [other])
    other_run = pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (other,))[0]
    f, _ = _file(pg, root, "OwnRun", 2)
    _sweep(root, [f])
    k = _k()
    try:
        (c,) = Q.claim(k, "w", 1, 60, [f])
        for run in (other_run, None):
            with pytest.raises(pg.errors.InvalidParameterValue):
                Q._sql(k, "SELECT litkb.finish_job(%s, %s, %s, %s, '{}'::jsonb)", (c.job_id, c.token, run, "0" * 64))
        assert _jobs(pg, f)[0][0] == "leased"
        Q._sql(k, "SELECT litkb.fail_job(%s, %s, 'test cleanup')", (c.job_id, c.token))
    finally:
        k.close()
    _work(root, [f])


@pg_only
def test_the_heartbeat_keeps_a_lease_and_an_expired_one_is_reclaimed(pg, root):
    f, _ = _file(pg, root, "Heartbeat", 2)
    _sweep(root, [f])
    k = _k()
    try:
        (c,) = Q.claim(k, "hb", 1, 2, [f])
        hb = Q.Heartbeat(_k, c, 2)
        hb.start()
        time.sleep(3.2)
        assert Q.claim(k, "thief", 1, 60, [f]) == []               # renewed: not expired
        hb.stop()
        assert hb.renewals >= 2 and not hb.lost
        time.sleep(2.3)
        assert Q.stale_leases(k) >= 1                              # expired, nobody reclaimed it
        (c2,) = Q.claim(k, "rescuer", 1, 60, [f])
        assert (c2.job_id, c2.lease_seq, c2.attempts) == (c.job_id, 2, 2)
        hist = pg.conn.execute("SELECT seq, owner, superseded_at IS NOT NULL, released_at FROM "
                               "litkb.extraction_job_leases WHERE job_id = %s ORDER BY seq", (c.job_id,)).fetchall()
        assert [(h[0], h[1], h[2], h[3]) for h in hist] == [(1, "hb", True, None), (2, "rescuer", False, None)]
        assert Q.run_job(k, c2, root=root, extractor=F.SyntheticExtractor(), derived=root / "_d",
                         ocr=True) == "done"
    finally:
        k.close()


@pg_only
def test_a_job_that_keeps_failing_is_dead_at_the_ceiling(pg, root):
    f, _ = _file(pg, root, "Poison", 2)
    _sweep(root, [f])

    def boom(job):
        raise Q.ExtractError("docling produced no artifact: constructed failure")

    rep = _work(root, [f], extractor=boom)
    ceiling = pg.one("SELECT litkb._job_max_attempts()")[0]
    assert rep["outcomes"] == {"failed:queued": ceiling - 1, "failed:dead": 1}, rep
    state, _r, attempts, _s, run = _jobs(pg, f)[0]
    assert (state, attempts, run) == ("dead", ceiling, None)
    assert pg.one("SELECT outcome FROM litkb.extraction_job_leases WHERE job_id = "
                  "(SELECT id FROM litkb.extraction_jobs WHERE file_id = %s) ORDER BY seq DESC LIMIT 1",
                  (f,)) == ("dead",)
    # design §12.3 / builder-A Q2: a `failed` run at the job's key carries the job's last error, and
    # it is never the file's current run (nothing reads a dead file as extracted)
    status, m, current = _dead_run(pg, f)
    assert (status, current) == ("failed", False)
    assert m["job_state"] == "dead" and "constructed failure" in m["last_error"], m
    assert m["dead_jobs"][0]["attempts"] == ceiling, m


@pg_only
def test_a_dead_job_never_touches_an_ok_run_at_its_key(pg, root):
    """The dead-run record is written only where no ok run stands: a job that dies while an ok run
    exists at its key (another route extracted the file meanwhile) leaves that run ok and current."""
    from litkb.extract import ingest as ING
    from litkb.extract import reconcile as R

    f, pdf = _file(pg, root, "DiesBesideAnOkRun", 2)
    _sweep(root, [f])
    k = _k()
    try:
        (c,) = Q.claim(k, "late", 1, 60, [f])
        prep = ING.prepare(str(pdf), None, F.synthetic_doc(pdf))
        ok = ING.ingest_file(k, f, prep["canonical"], prep["disagreements"], prep["stats"],
                             pages=prep["pages"], pipeline_version=R.PIPELINE_VERSION,
                             params=ING.CORPUS_PARAMS)["run_id"]
        pg.conn.execute("UPDATE litkb.extraction_jobs SET attempts = litkb._job_max_attempts() "
                        "WHERE id = %s", (c.job_id,))
        assert Q._sql(k, "SELECT litkb.fail_job(%s, %s, 'late failure')", (c.job_id, c.token)).fetchone()[0] == "dead"
    finally:
        k.close()
    assert pg.one("SELECT status FROM litkb.extraction_runs WHERE id = %s", (ok,)) == ("ok",)
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (f,)) == (ok,)
    assert pg.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s", (f,)) == (1,)


@pg_only
def test_an_extraction_with_no_block_dies_as_zero_content_by_name(pg, root):
    """CONSTRUCTED: two BLANK pages (no text, no raster — native under D13) and an extractor that
    reads nothing. No block: the job fails as ZeroContent on every attempt (each reusing the recorded
    artifact) and dies; its last error and its failed run both name it, which is the evidence the
    readability classifier reads for `zero-content` (litkb.readability, S4 run 3 item 1c)."""
    ws = F.open_ws(pg.conn)
    pdf = F.constructed_pdf(root / "Validation" / "BlankTwo.pdf", 2, text=False, raster=False,
                            note=uuid.uuid4().hex)
    f = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), pdf, root)
    _sweep(root, [f])
    calls = []

    def silent(job):
        calls.append(job.prefix)
        return F.SyntheticExtractor(silent_pages={1, 2})(job)

    rep = _work(root, [f], extractor=silent)
    ceiling = pg.one("SELECT litkb._job_max_attempts()")[0]
    assert rep["outcomes"] == {"failed:queued": ceiling - 1, "failed:dead": 1}, rep
    assert calls == ["whole.s1"], "a retry re-extracted instead of reusing the recorded artifact"
    last = pg.one("SELECT last_error FROM litkb.extraction_jobs WHERE file_id = %s", (f,))[0]
    assert last.startswith(Q.ZERO_CONTENT_ERROR), last
    status, m, _cur = _dead_run(pg, f)
    assert status == "failed" and m["last_error"].startswith(Q.ZERO_CONTENT_ERROR), m


@pg_only
def test_the_lease_history_is_append_only(pg, root):
    f, _ = _file(pg, root, "History", 2)
    _sweep(root, [f])
    _work(root, [f])
    job = pg.one("SELECT id FROM litkb.extraction_jobs WHERE file_id = %s", (f,))[0]
    for sql in ("UPDATE litkb.extraction_job_leases SET outcome = 'failed' WHERE job_id = %s",
                "UPDATE litkb.extraction_job_leases SET owner = 'someone else' WHERE job_id = %s",
                "DELETE FROM litkb.extraction_job_leases WHERE job_id = %s"):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            pg.one(sql, (job,))
    k = _k()
    try:
        for sql in ("INSERT INTO litkb.extraction_jobs (file_id, stage, tool, tool_version, params_hash, "
                    "pipeline_version) VALUES (%s, '5-reconcile', 't', 'v', 'p', 'v')",
                    "UPDATE litkb.extraction_jobs SET state = 'done' WHERE file_id = %s"):
            with pytest.raises(pg.errors.InsufficientPrivilege):
                k.execute(sql, (f,))
    finally:
        k.close()


@pg_only
def test_a_native_file_end_to_end_lands_one_run_with_its_metrics_and_digest(pg, root):
    f, _ = _file(pg, root, "Native", 3)
    _sweep(root, [f])
    rep = _work(root, [f])
    assert rep["outcomes"] == {"done": 1}
    run, digest, jm = pg.one("SELECT run_id, blocks_digest, metrics FROM litkb.extraction_jobs "
                             "WHERE file_id = %s", (f,))
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (f,))[0] == run
    assert digest == Q.blocks_digest(Q.run_rows(pg.conn, run))
    m = pg.one("SELECT metrics FROM litkb.extraction_runs WHERE id = %s", (run,))[0]
    for key in ("seconds", "pages", "pages_per_s", "peak_rss_bytes", "peak_vram_mib", "device",
                "interpreter", "ocr", "ocr_engine", "jobs", "attempts", "chunks", "blocks"):
        assert key in m, key
    assert (m["pages"], m["attempts"], m["chunks"], m["device"]) == (3, 1, [], "synthetic")
    assert m["jobs"][0]["page_start"] is None and jm["lease_seq"] == 1
    assert Q.counters(pg.conn, root)["duplicate_blocks"] == 0


@pg_only
def test_an_ocr_file_is_extracted_in_ranges_and_assembled_into_one_run(pg, root):
    f, _ = _file(pg, root, "Chunked", 50, text=False)
    assert _sweep(root, [f])["enqueued"] == 3
    rep = _work(root, [f])
    assert rep["outcomes"] == {"staged": 2, "done": 1}, rep
    rows = _jobs(pg, f)
    assert [r[0] for r in rows] == ["done"] * 3 and [r[3] for r in rows] == [1, 23, 45]
    assert len({r[4] for r in rows}) == 1
    run = rows[0][4]
    assert pg.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s", (f,))[0] == 1
    pages = [r[0] for r in pg.conn.execute("SELECT DISTINCT page_no FROM litkb.blocks WHERE run_id = %s "
                                           "ORDER BY 1", (run,)).fetchall()]
    assert pages == list(range(1, 51))
    m = pg.one("SELECT metrics FROM litkb.extraction_runs WHERE id = %s", (run,))[0]
    assert m["chunks"] == [[1, 22], [23, 44], [45, 50]] and len(m["jobs"]) == 3 and m["ocr"] is True
    assert m["image_pages"] == 50 and m["ocr_chars_on_image_pages"] > 0
    assert Q.blocks_digest(Q.run_rows(pg.conn, run)) == Q.blocks_digest(F.synthetic_reference(root / "Validation" / "Chunked.pdf"))


@pg_only
def test_an_ok_run_at_the_key_marks_the_job_done_without_running(pg, root):
    from litkb.extract import ingest as ING

    f, pdf = _file(pg, root, "Already", 2)
    k = _k()
    try:
        prep = ING.prepare(str(pdf), None, F.synthetic_doc(pdf))
        from litkb.extract import reconcile as R
        ING.ingest_file(k, f, prep["canonical"], prep["disagreements"], prep["stats"],
                        pages=prep["pages"], pipeline_version=R.PIPELINE_VERSION,
                        params=ING.CORPUS_PARAMS)
        Q.enqueue(k, f, None, None, Q.Facts(route="native", pages=2))
    finally:
        k.close()
    rep = _work(root, [f], extractor=lambda job: pytest.fail("the tool ran on an ok run"))
    assert rep["outcomes"] == {"done-existing": 1}


@pg_only
def test_a_reclaimed_job_reuses_its_recorded_artifact(pg, root):
    """§12.4: an artifact on disk whose sha256 equals the job's is not produced again."""
    f, pdf = _file(pg, root, "Reuse", 2)
    _sweep(root, [f])
    k = _k()
    calls = []

    def counting(job):
        calls.append(job.prefix)
        return F.SyntheticExtractor()(job)

    try:
        (c1,) = Q.claim(k, "dies", 1, 1, [f])
        sha, rel, _t = Q._file_row(k, f)
        Q._extract_or_reuse(k, c1, root / rel, sha, counting, root / "_derived", f)
        time.sleep(1.3)                                       # it dies before ingesting
    finally:
        k.close()
    rep = _work(root, [f], extractor=counting)
    assert rep["outcomes"] == {"done": 1} and calls == ["whole.s1"]


@pg_only
def test_a_scan_whose_image_pages_stay_empty_is_refused_even_with_ocr_on(pg, root):
    """CONSTRUCTED: a SCAN by the majority of its pages (image pages 2-4 of 4, one native-text page),
    OCR on, and the tool reads nothing on the image pages -> refused `scan-needs-ocr`, no run; the
    same shape with the image pages read -> done, with `ocr` true and the image-page characters in
    the run's metrics."""
    ws = F.open_ws(pg.conn)
    silent = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), F.constructed_pdf(
        root / "Validation" / "ScanSilent.pdf", 4, scan_pages=(2, 3, 4), note=uuid.uuid4().hex), root)
    read = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), F.constructed_pdf(
        root / "Validation" / "ScanRead.pdf", 4, scan_pages=(2, 3, 4), note=uuid.uuid4().hex), root)
    assert _sweep(root, [silent, read])["enqueued"] == 2
    rep = _work(root, [silent], extractor=F.SyntheticExtractor(silent_pages={2, 3, 4}))
    assert rep["outcomes"] == {"refused": 1}, rep
    assert _jobs(pg, silent)[0][:2] == ("refused", "scan-needs-ocr")
    assert pg.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s", (silent,))[0] == 0
    assert _work(root, [read])["outcomes"] == {"done": 1}
    m = pg.one("SELECT r.metrics FROM litkb.extraction_runs r JOIN litkb.files f "
               "ON f.current_run_id = r.id WHERE f.id = %s", (read,))[0]
    assert m["ocr"] is True and m["image_pages"] == 3 and m["ocr_chars_on_image_pages"] > 0
    assert m["textless_image_pages"] == []


@pg_only
def test_a_native_paper_with_one_textless_picture_page_is_extracted_not_refused(pg, root):
    """CONSTRUCTED (the new negative of S4 run 3 item 1a): a NATIVE paper — three pages of text and
    ONE image page (page 3) whose picture carries no text — routed to OCR, and OCR reads nothing on
    the picture. It is not a scan (1 image page against 3 native-text pages), so the run FINISHES:
    `done`, one ok current run, the textless page REPORTED in the run's metrics, and
    `scans_ocr_unrouted` does not move. Mutation EQ25 (the majority clause removed) refuses it whole."""
    ws = F.open_ws(pg.conn)
    before = Q.scans_ocr_unrouted(pg.conn)
    f = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), F.constructed_pdf(
        root / "Validation" / "NativeWithPicture.pdf", 4, scan_pages=(3,), note=uuid.uuid4().hex), root)
    assert _sweep(root, [f])["enqueued"] == 1
    assert P.image_page_numbers(root / "Validation" / "NativeWithPicture.pdf") == [3]
    rep = _work(root, [f], extractor=F.SyntheticExtractor(silent_pages={3}))
    assert rep["outcomes"] == {"done": 1}, rep
    m = pg.one("SELECT r.metrics FROM litkb.extraction_runs r JOIN litkb.files f "
               "ON f.current_run_id = r.id WHERE f.id = %s", (f,))[0]
    assert m["textless_image_pages"] == [3] and m["ocr_chars_on_image_pages"] == 0, m
    assert m["image_pages"] == 1 and m["ocr"] is True, m
    assert Q.scans_ocr_unrouted(pg.conn) == before


@pg_only
def test_status_counts_states_refusals_and_pages(pg, root):
    k = _k()
    try:
        s = Q.status(k)
    finally:
        k.close()
    assert set(s["by_state"]) == set(Q.STATES) and set(s["by_refusal"]) == set(Q.REFUSALS)
    assert s["by_state"]["refused"] == sum(s["by_refusal"].values())


# ── the known-bads (plan "### S4" (c)) ──────────────────────────────────────────────────

@pg_only
def test_c3_an_over_cap_pdf_is_refused_and_bound_only_with_the_guard_off(pg, root):
    out = F.fire_cap(pg.conn, root)
    print("FIRE_CAP", json.dumps(out, default=str))
    base = out["baseline"]["over_cap_bound"]
    g, m = out["guarded"], out["mutated"]
    assert g["jobs"] == [("refused", "over-page-cap", 0, None, None)] and g["claimed"] == 0
    assert g["blocks"] == 0 and g["over_cap_bound"] == base
    assert m["blocks"] > 0 and m["over_cap_bound"] == base + 1, m


@pg_only
def test_c6_a_book_is_refused_and_lands_only_with_every_book_guard_off(pg, root):
    out = F.fire_book(pg.conn, root)
    print("FIRE_BOOK", json.dumps(out, default=str))
    base = out["baseline"]["books_extracted"]
    assert out["guarded"]["jobs"] == [("refused", "book", 0, None, None)]
    assert out["guarded"]["books_extracted"] == base
    assert out["mutated"]["blocks"] > 0 and out["mutated"]["books_extracted"] == base + 1
    # the SQL guards were restored: a new book file is refused again
    f, _ = _file(pg, root, "BookAgain", 2, work_type="book")
    k = _k()
    try:
        Q.enqueue(k, f, None, None, Q.Facts(route="native", pages=2))
    finally:
        k.close()
    assert _jobs(pg, f)[0][:2] == ("refused", "book")


@pg_only
@pytest.mark.skipif(not (F.ANDERSON.is_file() and F.ANDERSON_NO_OCR.is_file()),
                    reason="Anderson 1957 or its recorded no-OCR Docling artifact is not on this machine")
def test_c5_a_scan_with_ocr_off_is_refused_and_lands_empty_only_with_both_guards_off(pg, root):
    out = F.fire_scan(pg.conn, root)
    print("FIRE_SCAN", json.dumps(out, default=str))
    base = out["baseline"]["scans_ocr_unrouted"]
    g, m = out["guarded"], out["mutated"]
    assert g["jobs"] == [("refused", "scan-needs-ocr", 0, None, None)]
    assert g["runs_ok"] == 0 and g["blocks"] == 0 and g["scans_ocr_unrouted"] == base
    assert m["runs_ok"] == 1 and m["scans_ocr_unrouted"] == base + 1, m


@pg_only
@pytest.mark.skipif(not (F.ANDERSON.is_file() and F.ANDERSON_NO_OCR.is_file() and F.ANDERSON_OCR.is_file()),
                    reason="Anderson 1957 or its recorded Docling artifacts are not on this machine")
def test_the_scan_postcondition_refuses_an_ocr_pass_that_read_nothing(pg, root):
    """OCR ON, but the extraction's image pages come back with nothing beyond the native layer (the
    REAL no-OCR artifact stands in for an OCR engine that produced nothing) -> refused
    `scan-needs-ocr`, no run. The REAL OCR artifact through the same path -> done."""
    empty = F.real_copy(F.ANDERSON, root / "Validation" / "Anderson_empty.pdf", note="postcondition empty")
    full = F.real_copy(F.ANDERSON, root / "Validation" / "Anderson_full.pdf", note="postcondition full")
    ws = F.open_ws(pg.conn)
    fe = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), empty, root)
    ff = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), full, root)
    _sweep(root, [fe, ff])
    rep = _work(root, [fe], extractor=F.ReplayExtractor({(1, 22): F.ANDERSON_NO_OCR}, ocr=True))
    assert rep["outcomes"] == {"refused": 1}
    assert _jobs(pg, fe)[0][:2] == ("refused", "scan-needs-ocr")
    assert pg.one("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s", (fe,))[0] == 0
    rep = _work(root, [ff], extractor=F.ReplayExtractor({(1, 22): F.ANDERSON_OCR}, ocr=True))
    assert rep["outcomes"] == {"done": 1}


@pg_only
def test_c2_an_expired_workers_finish_lands_nothing_and_lands_with_the_gate_removed(pg, root):
    out = F.fire_lease(pg.conn, root)
    print("FIRE_LEASE", json.dumps(out, default=str))
    base = out["baseline"]["mutated_leases_accepted"]
    g, m = out["guarded"], out["mutated"]
    assert g["raised"] and "lease refused" in g["raised"]
    assert (g["t1_seq"], g["t2_seq"]) == (1, 2)
    assert g["blocks_after_t1"] == 0 and g["mutated_leases_accepted"] == base
    assert g["t2_outcome"] == "done" and g["blocks"] > 0          # the rightful holder lands
    assert m["raised"] is None and m["blocks"] > 0 and m["mutated_leases_accepted"] == base + 1, m
    # the gate was restored: a stale finish is refused again
    f, _ = _file(pg, root, "LeaseAgain", 2)
    _sweep(root, [f])
    k = _k()
    try:
        (t1,) = Q.claim(k, "T1", 1, 1, [f])
        time.sleep(1.3)
        (t2,) = Q.claim(k, "T2", 1, 60, [f])
        with pytest.raises(Q.LeaseLost):
            Q._sql(k, "SELECT litkb.finish_job(%s, %s, NULL, %s, '{}'::jsonb)", (t1.job_id, t1.token, "0" * 64))
        Q._sql(k, "SELECT litkb.fail_job(%s, %s, 'cleanup')", (t2.job_id, t2.token))
    finally:
        k.close()
    _work(root, [f])


@pg_only
def test_c1_kill_the_worker_process_tree_mid_batch_and_rerun_synthetic(pg, root):
    """(c1) on the SYNTHETIC extractor seam, so it needs no GPU: `litkb queue work` as a subprocess,
    its whole tree killed inside the second job after the first committed, the lease let expire, the
    command run again. Every job done, digests equal to an uninterrupted run, 0 duplicates, 0 stale
    leases, 0 resumed mismatches. The REAL-tools twin is test_c1_real_kill_mid_batch_and_rerun."""
    pdfs = [F.constructed_pdf(root / "Validation" / f"Kill_{i}.pdf", 2 + i, note=uuid.uuid4().hex)
            for i in range(3)]
    out = F.fire_kill(pg.conn, root, pdfs, synthetic_delay=4, lease=6, timeout=600,
                      reference=F.synthetic_reference)
    print("FIRE_KILL_SYNTHETIC", json.dumps({k: out[k] for k in (
        "state", "killed_after_s", "worker1_exit", "rerun_exit", "before_rerun", "jobs", "digests",
        "counters", "baseline")}, default=str))
    print("FIRE_KILL_SYNTHETIC_TRACE", json.dumps([(e["event"], e.get("label"), e.get("outcome"),
                                                    e.get("attempts"), e["pid"]) for e in out["trace"]]))
    assert out["state"] == "killed", out
    assert out["rerun_exit"] == 0, (root / "worker2.log").read_text(encoding="utf-8")[-3000:]
    assert all(all(j[0] == "done" for j in js) for js in out["jobs"]), out["jobs"]
    assert any(j[2] > 1 for js in out["jobs"] for j in js), "no job was ever resumed"
    assert all(d["equal"] for d in out["digests"]), out["digests"]
    base = out["baseline"]
    assert out["counters"] == {k: base[k] for k in out["counters"]}, (out["counters"], base)


# ── real tools (LITKB_REAL_EXTRACT=1) ───────────────────────────────────────────────────

#: Three small NATIVE files of the S4 measurement bed (bed-at-start: active main files with no
#: blocks), 6, 9 and 10 pages.
_BED_NATIVE = ["Validation/Vincent_1993_grayscale-area-openings-closings.pdf",
               "Validation/Krahenbuhl_2013_parameter-learning-convergent.pdf",
               "Validation/Platanios_2014_estimating-accuracy-unlabeled-data.pdf"]


def _real_reference(root):
    """An UNINTERRUPTED run of the same real path (GROBID + Docling on the same device), in-process."""
    from litkb.extract import docling as D
    from litkb.extract import ingest as ING

    dev, py = D.device_pair("auto")
    ext = Q.ToolExtractor(dev, py, ocr=True)

    def ref(pdf):
        out = root / "_reference" / pathlib.Path(pdf).stem
        out.mkdir(parents=True, exist_ok=True)
        files, _m = ext(Q.Job(pdf=str(pdf), out_dir=out, prefix="whole.ref", page_range=None,
                              route="native"))
        tei = pathlib.Path(files["tei"]).read_bytes() if files["tei"] else None
        return Q.canonical_rows(ING.prepare(str(pdf), tei, D.load(files["docling"]))["canonical"])
    return ref


@pg_only
@real_only
def test_c1_real_kill_mid_batch_and_rerun(pg, root):
    pdfs = [F.real_copy(CORPUS / rel, root / rel) for rel in _BED_NATIVE]
    out = F.fire_kill(pg.conn, root, pdfs, synthetic_delay=None, lease=30, timeout=1800,
                      reference=_real_reference(root))
    (root / "fire_kill_real.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("state", "killed_after_s", "worker1_exit", "rerun_exit",
                                          "digests", "counters", "baseline", "jobs")},
                     indent=1, default=str))
    assert out["state"] == "killed" and out["rerun_exit"] == 0
    assert all(all(j[0] == "done" for j in js) for js in out["jobs"])
    assert out["counters"]["stale_leases"] == 0 and out["counters"]["duplicate_blocks"] == 0
    assert out["counters"]["resumed_content_hash_mismatches"] == 0
    assert all(d["equal"] for d in out["digests"]), out["digests"]


@pg_only
@real_only
@pytest.mark.parametrize("stem,chunks", [("Anderson_1957_statistical-inference-about-markov", 1),
                                         ("Ogata_1998_space-time-point-process-models", 2)])
def test_real_ocr_scan_in_page_ranges_on_cuda_records_its_vram(pg, root, stem, chunks):
    """The real OCR page-range path on the T2000: one run per file, the VRAM peak in its metrics and
    inside the 20 % rule (<= 3,277 MiB of 4,096; docling.py's VRAM table)."""
    from litkb.extract import docling as D

    pdf = F.real_copy(CORPUS / "Validation" / f"{stem}.pdf", root / "Validation" / f"{stem}.pdf")
    ws = F.open_ws(pg.conn)
    f = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), pdf, root)
    assert _sweep(root, [f])["enqueued"] == chunks
    dev, py = D.device_pair("cuda")
    rep = _work(root, [f], extractor=Q.ToolExtractor(dev, py, ocr=True))
    print(json.dumps(rep, indent=1, default=str))
    assert rep["outcomes"].get("done") == 1, rep
    m = pg.one("SELECT r.metrics FROM litkb.extraction_runs r JOIN litkb.files f ON f.current_run_id = r.id "
               "WHERE f.id = %s", (f,))[0]
    print(json.dumps({k: m.get(k) for k in ("seconds", "pages", "pages_per_s", "peak_rss_bytes",
                                            "peak_vram_mib", "vram_baseline_mib", "device",
                                            "interpreter", "ocr", "ocr_engine", "chunks", "attempts",
                                            "blocks")}, indent=1, default=str))
    assert m["device"] == "cuda" and m["ocr"] is True and len(m["chunks"]) == chunks
    assert m["peak_vram_mib"] is not None and m["peak_vram_mib"] <= 3277, m["peak_vram_mib"]
    assert Q.scans_ocr_unrouted(pg.conn) == 0


@pytest.mark.skipif(not os.path.exists(r"D:\edmonds-pipeline\venv-docling\Scripts\python.exe"),
                    reason="the CPU extraction venv is not on this machine")
def test_real_cuda_under_the_cpu_venv_is_refused_by_name():
    """The Maiti_2022 pair itself: `cuda` under venv-docling (torch +cpu)."""
    from litkb.extract import docling as D

    with pytest.raises(D.DeviceUnavailable):
        D.device_pair("cuda", D.VENV_PYTHON)
    assert D.device_pair("auto", D.VENV_PYTHON)[0] == "cpu"


# ── S4 run 3 round 2 (auditor-A F1, F3, F4, REDO) ───────────────────────────────────────

HUDSON = CORPUS / "Validation" / "Hudson_1978_natural-identity-exponential-families.pdf"


def _reopens(pg, f):
    return pg.conn.execute(
        "SELECT o.actor, o.db_login, o.why, o.refusal, o.refusal_stage, o.refused_error "
        "FROM litkb.extraction_job_reopens o JOIN litkb.extraction_jobs j ON j.id = o.job_id "
        "WHERE j.file_id = %s ORDER BY o.reopened_at", (f,)).fetchall()


@pg_only
@pytest.mark.skipif(not HUDSON.is_file(), reason="Hudson 1978 (a real scan) is not on this machine")
def test_f1_a_hudson_scan_copy_refused_at_claim_by_an_ocr_off_worker_is_reopened_by_ocr_on(pg, root):
    """auditor-A F1, on a REAL scan copy (Hudson 1978: 11 image pages of 12 -> one 22-page range).
    Swept with OCR ON, claimed by an OCR-OFF worker -> refused `scan-needs-ocr` AT CLAIM. A sweep with
    OCR still off leaves it refused (the refusal still holds). A sweep with OCR on reopens it: the
    job is `queued` again, with one audit row saying who, when, why and what was lifted, and the
    next OCR-on worker extracts it."""
    pdf = F.real_copy(HUDSON, root / "Validation" / HUDSON.name)
    ws = F.open_ws(pg.conn)
    f = F.add_file(pg.conn, ws, F.add_work(pg.conn, ws), pdf, root)
    assert _sweep(root, [f], ocr=True)["enqueued"] == 1
    rep = _work(root, [f], ocr=False)
    assert rep["outcomes"] == {"refused": 1}, rep
    assert _jobs(pg, f)[0][:2] == ("refused", "scan-needs-ocr") and _jobs(pg, f)[0][3] == 1
    assert pg.one("SELECT refusal_stage FROM litkb.extraction_jobs WHERE file_id = %s", (f,)) == ("claim",)
    still = _sweep(root, [f], ocr=False)
    assert (still["reopened"], still["enqueued"], still["already"]) == (0, 0, 1), still
    assert [j[:2] for j in _jobs(pg, f)] == [("refused", "scan-needs-ocr")] and _reopens(pg, f) == []
    back = _sweep(root, [f], ocr=True, actor="test-f1")
    assert (back["reopened"], back["enqueued"]) == (1, 0), back
    assert [j[0] for j in _jobs(pg, f)] == ["queued"]
    (actor, login, why, refusal, stage, err), = _reopens(pg, f)
    assert (actor, refusal, stage) == ("test-f1", "scan-needs-ocr", "claim")
    assert login and "no longer holds" in why and "OCR is off" in (err or "")
    assert _work(root, [f], ocr=True)["outcomes"] == {"done": 1}


@pg_only
def test_f1_a_refusal_made_on_the_result_is_never_reopened(pg, root):
    """The scan post-condition's refusal (OCR ran and read nothing) is refused a reopen BY THE
    DATABASE, and the sweep never even asks for one."""
    f, _ = _file(pg, root, "ResultRefused", 3, text=False)
    _sweep(root, [f])
    assert _work(root, [f], extractor=F.SyntheticExtractor(silent_pages={1, 2, 3}))["outcomes"] == {"refused": 1}
    jid, stage = pg.one("SELECT id, refusal_stage FROM litkb.extraction_jobs WHERE file_id = %s", (f,))
    assert stage == "result"
    try:
        out = _sweep(root, [f], ocr=True)
    except Exception as e:  # noqa: BLE001 — the sweep must not even ask
        pytest.fail(f"the sweep asked to reopen a result refusal: {e}")
    assert (out["reopened"], out["enqueued"], out["already"]) == (0, 0, 1)
    k = _k()
    try:
        with pytest.raises(pg.errors.InvalidParameterValue):
            k.execute("SELECT litkb.reopen_job(%s, 'scan-needs-ocr', 'test', 'forced', 'ocr', 3, "
                      "NULL, NULL)", (jid,))
    finally:
        k.close()
    assert _jobs(pg, f)[0][:2] == ("refused", "scan-needs-ocr") and _reopens(pg, f) == []


@pg_only
def test_f1_a_book_is_never_reopened_while_its_work_is_a_book(pg, root):
    f, _ = _file(pg, root, "BookReopen", 2, work_type="book")
    _sweep(root, [f])
    jid = pg.one("SELECT id FROM litkb.extraction_jobs WHERE file_id = %s", (f,))[0]
    k = _k()
    try:
        with pytest.raises(pg.errors.InvalidParameterValue):
            k.execute("SELECT litkb.reopen_job(%s, 'book', 'test', 'forced', 'native', 2, NULL, NULL)",
                      (jid,))
        # a compare-and-set: the wrong refusal changes nothing and answers false
        assert k.execute("SELECT litkb.reopen_job(%s, 'bad-file', 'test', 'x', 'native', 2, NULL, NULL)",
                         (jid,)).fetchone()[0] is False
    finally:
        k.close()
    assert _jobs(pg, f)[0][:2] == ("refused", "book") and _reopens(pg, f) == []


@pg_only
def test_f1_the_reopen_trail_is_append_only_and_reopen_names_who_and_why(pg, root):
    f, pdf = _file(pg, root, "BadThenFixed", 2)
    good = pdf.read_bytes()
    pdf.write_bytes(good + b"% damaged\n")
    assert _sweep(root, [f])["refused"] == {"bad-file": 1}
    pdf.write_bytes(good)                                      # the bytes are the bound file again
    assert _sweep(root, [f], actor="test-trail")["reopened"] == 1
    jid = pg.one("SELECT id FROM litkb.extraction_jobs WHERE file_id = %s", (f,))[0]
    for sql in ("UPDATE litkb.extraction_job_reopens SET why = 'rewritten' WHERE job_id = %s",
                "DELETE FROM litkb.extraction_job_reopens WHERE job_id = %s"):
        with pytest.raises(pg.errors.InsufficientPrivilege):
            pg.one(sql, (jid,))
    k = _k()
    try:
        with pytest.raises(pg.errors.InsufficientPrivilege):
            k.execute("INSERT INTO litkb.extraction_job_reopens (job_id, actor, why, refusal, refusal_stage) "
                      "VALUES (%s, 'x', 'y', 'bad-file', 'enqueue')", (jid,))
        with pytest.raises(pg.errors.InvalidParameterValue):
            k.execute("SELECT litkb.reopen_job(%s, 'bad-file', '', 'why', 'native', 2, NULL, NULL)", (jid,))
    finally:
        k.close()
    assert _work(root, [f])["outcomes"] == {"done": 1}


@pg_only
def test_f4_a_book_found_at_claim_closes_its_leased_siblings_leases(pg, root):
    """auditor-A F4. Worker A holds range 1 of a 3-range file under a LIVE lease; the work is retyped
    to book; worker B's claim of range 2 hits the SQL book guard and refuses the whole file. Range 1's
    lease row is closed (superseded) at that moment — not left looking like a running lease — A can
    move nothing any more, and the counters read correctly: no stale lease, nothing accepted."""
    f, _ = _file(pg, root, "BookMidway", 50, text=False)
    assert _sweep(root, [f])["enqueued"] == 3
    k = _k()
    try:
        before = Q.mutated_leases_accepted(k)
        (a,) = Q.claim(k, "A", 1, 600, [f])
        assert a.page_start == 1
        work_id, cur, title = pg.one(
            "SELECT w.work_id, w.version_id, w.title FROM litkb.main_works w JOIN litkb.main_files f "
            "ON f.work_id = w.work_id WHERE f.file_id = %s", (f,))
        ws = F.open_ws(pg.conn)
        pg.one("SELECT litkb._write_version('fact', 'work', %s, NULL, %s, %s, 'retyped a book', %s, "
               "'setup', 'setup')", (work_id, cur, pg.Jsonb({"type": "book", "title": title, "authors": []}), ws))
        assert Q.claim(k, "B", 1, 60, [f]) == []
        rows = pg.conn.execute("SELECT state, refusal, refusal_stage FROM litkb.extraction_jobs "
                               "WHERE file_id = %s ORDER BY page_start", (f,)).fetchall()
        assert rows == [("refused", "book", "claim")] * 3, rows
        superseded, released = pg.one("SELECT superseded_at IS NOT NULL, released_at IS NOT NULL "
                                      "FROM litkb.extraction_job_leases WHERE job_id = %s AND seq = %s",
                                      (a.job_id, a.lease_seq))
        assert superseded, "range 1's live lease was left open when its job was refused"
        assert released is False                     # the holder never released it: it was cut short
        with pytest.raises(Q.LeaseLost):
            Q.renew(k, a)
        assert Q.stale_leases(k) == 0 or pg.one(
            "SELECT count(*) FROM litkb.extraction_jobs WHERE file_id = %s AND state = 'leased'", (f,))[0] == 0
        assert pg.one("SELECT count(*) FROM litkb.extraction_jobs j WHERE j.file_id = %s AND j.state = 'leased'",
                      (f,))[0] == 0
        assert Q.mutated_leases_accepted(k) == before
    finally:
        k.close()


def test_f3_the_docling_worker_runs_from_a_short_neutral_cwd(monkeypatch, tmp_path):
    """auditor-A F3. However deep the artifact directory, the worker's cwd is the short, empty
    `worker_cwd()`, never the artifact directory (which passed the Windows path limit)."""
    from litkb.extract import docling as D

    seen = {}

    def fake_run(jobs, metrics_path, **kw):
        seen["cwd"] = kw.get("cwd")
        return []

    monkeypatch.setattr(D, "run", fake_run)
    deep = tmp_path / ("d" * 80) / ("e" * 80)
    deep.mkdir(parents=True)
    ext = Q.ToolExtractor("cpu", sys.executable, ocr=True, grobid=False)
    with pytest.raises(Q.ExtractError):
        ext(Q.Job(pdf="x.pdf", out_dir=deep, prefix="p001-001.s1", page_range=(1, 1), route="ocr"))
    assert seen["cwd"] == Q.worker_cwd() and seen["cwd"] != str(deep)
    assert len(seen["cwd"]) < len(str(deep)) and "secrets" not in pathlib.Path(seen["cwd"]).parts


@pg_only
def test_redo_re_extracts_a_file_whose_current_run_is_at_an_older_key_only(pg, root):
    """`queue sweep --file F --redo` (S2's Maiti_2022): a file whose CURRENT run sits at an OLDER key
    gets a job at today's key and a new current run; a file whose current run IS at today's key gets
    nothing; a book with an old-key run is still refused (every guard applies); --redo names files."""
    from litkb.extract import ingest as ING

    old, old_pdf = _file(pg, root, "RedoOld", 2)
    cur, cur_pdf = _file(pg, root, "RedoCurrent", 2)
    book, book_pdf = _file(pg, root, "RedoBook", 2, work_type="book")
    k = _k()
    try:
        for f, pdf, version in ((old, old_pdf, "stage5-old-test"), (book, book_pdf, "stage5-old-test")):
            prep = ING.prepare(str(pdf), None, F.synthetic_doc(pdf))
            ING.ingest_file(k, f, prep["canonical"], prep["disagreements"], prep["stats"],
                            pages=prep["pages"], pipeline_version=version, params=ING.CORPUS_PARAMS)
        now_run = _ok_run_at_key(k, cur, cur_pdf)
        old_run = pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (old,))[0]
        assert _sweep(root, [old, cur, book])["files"] == 0           # without --redo: nothing
        with pytest.raises(ValueError):
            Q.sweep(k, root, redo=True)                               # --redo names its files
    finally:
        k.close()
    out = _sweep(root, [old, cur, book], redo=True)
    assert (out["files"], out["enqueued"], out["refused"]) == (2, 2, {"book": 1}), out  # a refused job is a row too
    assert _jobs(pg, cur) == []
    assert _work(root, [old, cur, book])["outcomes"] == {"done": 1}
    new_run = pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (old,))[0]
    assert new_run != old_run and pg.one("SELECT pipeline_version FROM litkb.extraction_runs WHERE id = %s",
                                         (new_run,))[0] == Q.run_key(old)["pipeline_version"]
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (cur,))[0] == now_run
    assert _sweep(root, [old], redo=True)["files"] == 0               # now at today's key: never again


def test_the_cli_takes_redo():
    from litkb import commands

    a = commands.build_parser().parse_args(["queue", "sweep", "--file", "x", "--redo"])
    assert (a.redo, a.files) == (True, ["x"])


@pg_only
def test_n5_a_workstream_only_book_counts_in_books_extracted(pg, root):
    """auditor-C N5. A work that is a book ONLY in a workstream's view (a proposal main has never
    seen), with a file carrying a block: books_extracted counts it when that workstream is named (the
    manifest's workstreams), and main alone cannot see it."""
    from litkb.extract import ingest as ING
    from litkb.extract import reconcile as R

    ws = F.open_ws(pg.conn)
    # `_write_version` in PROPOSAL mode: the work and its file exist in the workstream only (the
    # readability suite's `_seed(mode='proposal')`), so main_works never names this book
    work_id = pg.one("SELECT entity_id FROM litkb._write_version('proposal', 'work', NULL, %s, NULL, %s, "
                     "NULL, %s, 'setup', 'setup')",
                     (pg.Jsonb({"key": f"Book_2020_{uuid.uuid4().hex[:8]}-ws"}),
                      pg.Jsonb({"type": "book", "title": f"A workstream book {uuid.uuid4().hex}",
                                "authors": []}), ws))[0]
    pdf = F.constructed_pdf(root / "Validation" / "WsBook.pdf", 2, note=uuid.uuid4().hex)
    fid = pg.one("SELECT entity_id FROM litkb._write_version('proposal', 'file', NULL, %s, NULL, %s, NULL, "
                 "%s, 'setup', 'setup')", (pg.Jsonb({"sha256": Q.sha256_file(pdf)}),
                                           pg.Jsonb({"work_id": str(work_id), "rel_path": "Validation/WsBook.pdf",
                                                     "status": "active"}), ws))[0]
    assert pg.one("SELECT count(*) FROM litkb.main_works WHERE work_id = %s", (work_id,))[0] == 0
    k = _k()
    try:
        before_main, before_ws = Q.books_extracted(k), Q.books_extracted(k, [ws])
        prep = ING.prepare(str(pdf), None, F.synthetic_doc(pdf))
        ING.ingest_file(k, fid, prep["canonical"], prep["disagreements"], prep["stats"], pages=prep["pages"],
                        pipeline_version=R.PIPELINE_VERSION, params=ING.CORPUS_PARAMS)
        assert Q.books_extracted(k) == before_main                  # main has no such book
        assert Q.books_extracted(k, [ws]) == before_ws + 1          # the manifest's workstream does
        assert Q.counters(k, root, [ws])["books_extracted"] == before_ws + 1
    finally:
        k.close()


@pg_only
def test_n6_a_lease_the_book_guard_cut_off_cannot_finish_even_with_the_gate_removed(pg, root):
    """auditor-C N6, MEASURED rather than assumed: a `finished` lease row that is superseded with NO
    later claim of its job cannot exist. The only such supersession is a sibling range cut off by a
    whole-file refusal (the book guard at claim, refuse_job), and a refused job cannot become `done`
    even with finish_job's lease gate removed (CREATE OR REPLACE on this worker database, restored
    after): the `extraction_jobs_refusal` CHECK refuses `done` with a refusal still set, the finish
    rolls back, nothing lands, and mutated_leases_accepted stays put. So the counter's `superseded_at`
    clause can never add a job beyond its later-claim clause today; it is kept as the history's own
    reading, and this test is the fire that shows why no fire of it exists."""
    f, pdf = _file(pg, root, "CutOffFinish", 50, text=False)
    _sweep(root, [f])
    k = _k()
    try:
        before = Q.mutated_leases_accepted(k)
        (a,) = Q.claim(k, "A", 1, 600, [f])
        run = _ok_run_at_key(k, f, pdf)
        work_id, cur, title = pg.one(
            "SELECT w.work_id, w.version_id, w.title FROM litkb.main_works w JOIN litkb.main_files f "
            "ON f.work_id = w.work_id WHERE f.file_id = %s", (f,))
        ws = F.open_ws(pg.conn)
        pg.one("SELECT litkb._write_version('fact', 'work', %s, NULL, %s, %s, 'retyped a book', %s, "
               "'setup', 'setup')", (work_id, cur, pg.Jsonb({"type": "book", "title": title, "authors": []}), ws))
        assert Q.claim(k, "B", 1, 60, [f]) == []                     # the book guard refuses the file
        assert pg.one("SELECT superseded_at IS NOT NULL FROM litkb.extraction_job_leases "
                      "WHERE job_id = %s AND seq = %s", (a.job_id, a.lease_seq)) == (True,)
        assert pg.one("SELECT count(*) FROM litkb.extraction_job_leases WHERE job_id = %s AND seq > %s",
                      (a.job_id, a.lease_seq))[0] == 0                # no later claim of A's job
        with F.sql_guard_off(pg.conn, "litkb.finish_job(uuid, text, uuid, text, jsonb)",
                             "guard: finish_job accepts only the job's current, unsuperseded lease"):
            with pytest.raises(pg.errors.CheckViolation, match="extraction_jobs_refusal"):
                Q._sql(k, "SELECT litkb.finish_job(%s, %s, %s, %s, '{}'::jsonb)",
                       (a.job_id, a.token, run, "0" * 64))
        assert pg.one("SELECT state, refusal FROM litkb.extraction_jobs WHERE id = %s", (a.job_id,)) ==             ("refused", "book")
        assert Q.mutated_leases_accepted(k) == before
    finally:
        k.close()

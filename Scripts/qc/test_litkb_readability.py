"""S4 — the readability classifier (`litkb.readability`, decision D8): every acquired file is readable
or classified, from evidence only, and a file with no class is counted, never defaulted.

Real corpus files are COPIED into a temp literature root (the corpus is read-only to tests; a test
whose real file is absent on this machine SKIPS): a scan (Anderson 1957, JSTOR page2pdf), a native
paper (Efron 1986), a `t*.download` staging bind whose stored page-1 flag is wrong (Crowder 2017),
and S2's Copernicus PDF (Maiti 2022, GROBID-only because Docling failed on a device error). The
unopenable PDF, the over-cap PDF and the empty-text run are CONSTRUCTED and say so in their names.

The database is the shared worker DB, so every assertion is PER ROW (by file id) or a before/after
DELTA — other suites' seeded rows are in the same universe and are not this module's to count.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w9 py -3.12 -m pytest qc/test_litkb_readability.py -q
"""
import csv
import hashlib
import shutil
import uuid
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

LIT = Path(r"D:\edmonds-pipeline\Literture")
SCAN = "Validation/Anderson_1957_statistical-inference-about-markov.pdf"
NATIVE = "Validation/Efron_1986_how-biased-apparent-error-rate.pdf"
STAGING_BIND = "_litkb_staging/incoming/t286_Crowder_2017_bernoulli-cusum.download"
MAITI = "_litkb_staging/filed/Maiti_2022_effect-label-noise-semantic.pdf"
FIGURE_PAGE = "Validation/Guo_2019_city-wide-canopy-cover-decline.pdf"   # p6: a figure, caption as native text


def _jsonb(v):
    from psycopg.types.json import Jsonb

    return Jsonb(v)


@pytest.fixture
def env(tmp_path, litkb_pg_base):
    from litkb import workstream

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    root.mkdir()
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws = workstream.open_workstream(conn, f"read-{uuid.uuid4().hex[:8]}", "test", "readability", directory=wt)
    return {"conn": conn, "root": root, "ws": str(ws), "tmp": tmp_path}


def _copy(env, rel):
    """A COPY of a real corpus file under the temp root. -> its rel path there.

    Two things make every copy unique, both forced by the SHARED worker database: `files.sha256` is
    UNIQUE (so the copy is SALTED with one PDF comment line after its trailer — it changes no page,
    no text and no count: readers find the trailer through the LAST `startxref`), and
    `quarantine_payloads.rel_path` is UNIQUE and rows from other tests are path-keyed too (so the copy
    lives under a per-copy directory, keeping the corpus file's own name)."""
    src = LIT / rel
    if not src.exists():
        pytest.skip(f"real corpus file absent on this machine: {src}")
    new = f"{Path(rel).parent.as_posix()}/t{uuid.uuid4().hex[:10]}/{Path(rel).name}"
    dst = env["root"] / new
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    with open(dst, "ab") as fh:
        fh.write(f"\n% builder-B test salt {uuid.uuid4().hex}\n".encode())
    return new


def _put(env, rel, data):
    dst = env["root"] / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return dst


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _seed(env, rel, *, sha=None, wtype="article", copy_kind=None, mode="fact", work_id=None, key=None):
    """A work (unless `work_id`) and a current file version at `rel`, written as FACTS through
    `_write_version` (the way every litkb suite seeds a file). `mode='proposal'` leaves the file in
    the workstream only — the `ws_files` half of the universe."""
    conn, ws = env["conn"], env["ws"]
    if work_id is None:
        key = key or f"Read_2026_seed-{uuid.uuid4().hex[:8]}"
        work_id = conn.execute(
            "SELECT entity_id FROM litkb._write_version(%s, 'work', NULL, %s, NULL, %s, NULL, %s, 'r', 'r')",
            (mode, _jsonb({"key": key}), _jsonb({"type": wtype, "title": "A seeded readability target",
                                                 "authors": [], "year": 2026}), ws)).fetchone()[0]
    p = env["root"] / rel
    fields = {"work_id": str(work_id), "status": "active", "rel_path": rel,
              "bytes": p.stat().st_size if p.exists() else 0}
    if copy_kind:
        fields["copy_kind"] = copy_kind
    file_id = conn.execute(
        "SELECT entity_id FROM litkb._write_version(%s, 'file', NULL, %s, NULL, %s, NULL, %s, 'r', 'r')",
        (mode, _jsonb({"sha256": sha or (_sha(p) if p.exists() else uuid.uuid4().hex * 2)}), _jsonb(fields),
         ws)).fetchone()[0]
    return {"work_id": str(work_id), "file_id": str(file_id), "key": key}


def _run(env, file_id, pages_text, *, metrics=None, stage="5-reconcile"):
    """An ok run made current, with one canonical block per (page, text) pair."""
    conn = env["conn"]
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, pipeline_version, "
        "host, status, metrics) VALUES (%s, %s, 'read-seed', '0', %s, 'v0', 'local', 'ok', %s) RETURNING id",
        (file_id, stage, uuid.uuid4().hex[:16], _jsonb(metrics if metrics is not None else
                                                      {"docling_regions": 5, "grobid_regions": 5}))).fetchone()[0]
    prev = conn.execute("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,)).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, %s, %s)", (file_id, prev, run_id))
    for i, (pg, text) in enumerate(pages_text):
        conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text, canonical, reading_order) "
                     "VALUES (%s, %s, %s, 'paragraph', %s, true, %s)", (file_id, run_id, pg, text, i))
    return str(run_id)


def _classify(env, **kw):
    from litkb import readability as R

    return R.classify(env["conn"], root=env["root"], **kw)


def _row(res, file_id):
    return next(r for r in res["rows"] if r["row_kind"] == "file" and r["file_id"] == file_id)


def _pdf(n_pages, text=None):
    """CONSTRUCTED: an n-page PDF; `text` on page 1 when given, every other page blank."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None]
    kids, content_id = [], None
    if text:
        body = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode()
        objs.append(b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        content_id = 3
    for i in range(n_pages):
        extra = (b" /Contents 3 0 R /Resources << /Font << /F1 4 0 R >> >>" if (text and i == 0) else b"")
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]" + extra + b" >>")
        kids.append(len(objs))
    objs[1] = (b"<< /Type /Pages /Kids [" + b" ".join(f"{k} 0 R".encode() for k in kids)
               + f"] /Count {n_pages} >>".encode())
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    assert content_id in (None, 3)
    return bytes(out)


# ── the vocabulary ────────────────────────────────────────────────────────────────────────────

def test_the_classes_are_decision_d8():
    from litkb import readability as R

    assert R.FILE_CLASSES == ("extracted", "scan-needs-ocr", "over-page-cap", "zero-content", "bad-file",
                              "probe-error", "book", "refused-registry")
    assert R.EXTRACTED_REASONS == ("full", "docling-only", "grobid-only", "ocr", "snapshot")
    assert "no-file-any-route" in R.WORK_CLASSES
    assert "queued" not in R.FILE_CLASSES and "leased" not in R.FILE_CLASSES


# ── real files ────────────────────────────────────────────────────────────────────────────────

@pg_only
def test_a_real_scan_with_no_run_is_scan_needs_ocr_by_the_per_page_probe(env):
    rel = _copy(env, SCAN)
    before = (env["root"] / rel).read_bytes()
    s = _seed(env, rel)
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "scan-needs-ocr" and row["pages"] == 22, row
    assert row["image_pages"] == 21, "D13: the JSTOR cover (page 1) carries native text; pages 2-22 are images"
    assert (env["root"] / rel).read_bytes() == before, "the classifier never writes a file"


@pg_only
def test_a_real_native_file_waits_unclassified_then_is_extracted_full(env):
    """No run and no image page: WAITING — unclassified, never defaulted. With a current run whose
    blocks carry text on its pages and both tools' regions: `extracted` / `full`."""
    s = _seed(env, _copy(env, NATIVE))
    before = _row(_classify(env), s["file_id"])
    assert before["class"] is None and "waiting" in before["evidence"], before
    _run(env, s["file_id"], [(pg, f"page {pg} body text") for pg in range(1, 12)])
    after = _row(_classify(env), s["file_id"])
    assert (after["class"], after["reason"]) == ("extracted", "full"), after
    assert after["blocks"] == 11 and after["text_chars"] > 0, after


@pg_only
def test_the_staging_bind_is_read_per_page_not_by_its_page1_flag(env):
    """Crowder 2017 is bound at `_litkb_staging/incoming/t286_...download` and stored
    `has_text_layer=false` (the binding reads page 1 only, 113 characters). The per-page probe finds
    NO image page (decision D13: every page carries native text), so with no run it WAITS, never
    `scan-needs-ocr`, and with a run it is `extracted` — the per-page fact, never the stored flag."""
    from litkb.extract import probe

    rel = _copy(env, STAGING_BIND)
    p = env["root"] / rel
    assert probe.image_page_numbers(p) == []
    s = _seed(env, rel)
    assert _row(_classify(env), s["file_id"])["class"] is None
    _run(env, s["file_id"], [(pg, f"slide {pg}") for pg in range(1, probe.probe_pages(p) + 1)])
    assert _row(_classify(env), s["file_id"])["class"] == "extracted"


@pg_only
def test_a_figure_page_with_a_native_caption_is_not_an_ocr_page(env):
    """Guo 2019 p6 (135 native characters: a caption under a figure) carries no text block in its
    live run. Under the old 200-character rule the finished extraction read `scan-needs-ocr`; under
    decision D13 the page is not an image page and the file is `extracted`/`full`."""
    rel = _copy(env, FIGURE_PAGE)
    s = _seed(env, rel)
    _run(env, s["file_id"], [(pg, f"page {pg}") for pg in range(1, 10) if pg != 6])
    row = _row(_classify(env), s["file_id"])
    assert (row["class"], row["reason"]) == ("extracted", "full") and row["image_pages"] == 0, row


@pg_only
def test_an_image_page_no_text_block_covers_is_scan_needs_ocr_and_covered_ones_are_ocr(env):
    """The real scan with a run covering every image page but one: `scan-needs-ocr`, naming the
    page. Covering all of them with no `ocr` metric: `extracted`/`ocr` — text on a page with no native
    characters can only have come from OCR."""
    rel = _copy(env, SCAN)
    s = _seed(env, rel)
    _run(env, s["file_id"], [(pg, f"ocr text {pg}") for pg in range(1, 22)])
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "scan-needs-ocr" and "22" in row["evidence"], row
    _run(env, s["file_id"], [(pg, f"ocr text {pg}") for pg in range(1, 23)])
    row = _row(_classify(env), s["file_id"])
    assert (row["class"], row["reason"]) == ("extracted", "ocr"), row


@pg_only
def test_maiti_2022_is_a_classification_grobid_only_never_a_refusal(env):
    """S2's Copernicus PDF: Docling failed on a device error, GROBID carried the file. Its run's
    metrics (live, 2026-09-22) are docling_regions 0, grobid_regions 69 → `extracted` / `grobid-only`."""
    from litkb.extract import probe

    rel = _copy(env, MAITI)
    p = env["root"] / rel
    s = _seed(env, rel)
    _run(env, s["file_id"], [(pg, f"grobid paragraph {pg}") for pg in range(1, probe.probe_pages(p) + 1)],
         metrics={"blocks": 113, "grobid_only": 69, "docling_regions": 0, "grobid_regions": 69})
    row = _row(_classify(env), s["file_id"])
    assert (row["class"], row["reason"]) == ("extracted", "grobid-only"), row


# ── CONSTRUCTED residue ───────────────────────────────────────────────────────────────────────

@pg_only
def test_a_native_file_whose_run_holds_no_text_is_zero_content(env):
    s = _seed(env, _copy(env, NATIVE))
    _run(env, s["file_id"], [(1, ""), (2, None)])          # CONSTRUCTED: blocks with no text
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "zero-content", row


@pg_only
def test_bytes_that_are_not_the_recorded_file_are_bad_file(env):
    wrong = _seed(env, _copy(env, NATIVE), sha=uuid.uuid4().hex * 2)
    missing = _seed(env, "Validation/CONSTRUCTED_missing.pdf")
    _put(env, "Validation/CONSTRUCTED_not_a_pdf.pdf", b"<html>sign in</html>")
    html = _seed(env, "Validation/CONSTRUCTED_not_a_pdf.pdf")
    res = _classify(env)
    assert _row(res, wrong["file_id"])["class"] == "bad-file" and "sha256" in _row(res, wrong["file_id"])["evidence"]
    assert _row(res, missing["file_id"])["class"] == "bad-file"
    assert _row(res, html["file_id"])["class"] == "bad-file"


@pg_only
def test_a_bound_file_whose_page_count_cannot_be_read_is_probe_error(env):
    from litkb import readability as R

    _put(env, "Validation/CONSTRUCTED_unopenable.pdf", R._constructed_unopenable_pdf(salt=uuid.uuid4().hex))
    s = _seed(env, "Validation/CONSTRUCTED_unopenable.pdf")
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "probe-error" and row["pages"] is None, row


@pg_only
def test_a_file_over_the_cap_is_over_page_cap(env):
    """CONSTRUCTED: EXTRACT_PAGE_CAP + 1 pages, built relative to the constant (Kam ruling litkb-extract-page-cap)."""
    from litkb.extract import probe

    rel = "Validation/CONSTRUCTED_over_cap.pdf"
    _put(env, rel, _pdf(probe.EXTRACT_PAGE_CAP + 1, text=f"A long constructed volume {uuid.uuid4().hex}"))
    s = _seed(env, rel)
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "over-page-cap" and row["pages"] == probe.EXTRACT_PAGE_CAP + 1, row
    at = "Validation/CONSTRUCTED_at_cap.pdf"
    _put(env, at, _pdf(probe.EXTRACT_PAGE_CAP, text=f"A volume exactly at the cap {uuid.uuid4().hex}"))
    s2 = _seed(env, at)
    assert _row(_classify(env), s2["file_id"])["class"] != "over-page-cap"


@pg_only
def test_a_current_version_that_is_not_active_is_unclassified_and_says_why(env):
    """`file_versions.status` allows `quarantined` / `superseded` (0001). Such a current version is
    counted UNCLASSIFIED with the reason, never passed through the file rules as if it were live."""
    s = _seed(env, _copy(env, SCAN))
    env["conn"].execute("UPDATE litkb.file_versions SET status = 'quarantined' WHERE file_id = %s", (s["file_id"],))
    row = _row(_classify(env), s["file_id"])
    assert row["class"] is None and "not active" in row["evidence"], row


@pg_only
def test_a_book_is_book(env):
    s = _seed(env, _copy(env, NATIVE), wtype="book")
    assert _row(_classify(env), s["file_id"])["class"] == "book"


@pg_only
def test_a_snapshot_and_an_ocr_run_carry_their_reasons(env):
    rel = "_litkb_staging/web/CONSTRUCTED_snapshot.txt"
    _put(env, rel, b"A saved page of text.\n")
    snap = _seed(env, rel, copy_kind="web snapshot")
    _run(env, snap["file_id"], [(1, "A saved page of text.")], metrics={"blocks": 1}, stage="5-text-snapshot")
    scan = _seed(env, _copy(env, SCAN))
    _run(env, scan["file_id"], [(pg, f"ocr text {pg}") for pg in range(1, 23)],
         metrics={"ocr": True, "docling_regions": 22, "grobid_regions": 0})
    res = _classify(env)
    assert (_row(res, snap["file_id"])["class"], _row(res, snap["file_id"])["reason"]) == ("extracted", "snapshot")
    assert (_row(res, scan["file_id"])["class"], _row(res, scan["file_id"])["reason"]) == ("extracted", "ocr")


@pg_only
def test_a_quarantine_row_is_the_state_of_a_file_nothing_else_classes(env):
    from litkb import quarantine as Q

    rel = _copy(env, NATIVE)
    s = _seed(env, rel)
    ing = _ingest()
    try:
        Q.record_system(ing, rel_path=rel, sha256=_sha(env["root"] / rel), nbytes=1, reason="zero-content",
                        origin="classifier", file_id=s["file_id"])
    finally:
        ing.close()
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "zero-content" and row["quarantine_ids"], row


def _ingest():
    from litkb import quarantine as Q
    from litkb.db import connect as c

    return Q.ingest_connect(c.DB_TEST)


@pg_only
def test_record_mode_refuses_a_bound_file_where_it_lies(env):
    """`record=` (an ingest connection): a bound file classed `bad-file` / `zero-content` gets ONE row
    against its current path with its file_id, origin `classifier`; the bytes are not moved; a second
    classification writes nothing more. The default writes nothing."""
    rel = _copy(env, NATIVE)
    s = _seed(env, rel)
    _run(env, s["file_id"], [(1, "")])
    n = env["conn"].execute("SELECT count(*) FROM litkb.quarantine_payloads").fetchone()[0]
    _classify(env)
    assert env["conn"].execute("SELECT count(*) FROM litkb.quarantine_payloads").fetchone()[0] == n
    ing = _ingest()
    try:
        first = _classify(env, record=ing)
        second = _classify(env, record=ing)
    finally:
        ing.close()
    got = env["conn"].execute("SELECT rel_path, reason, origin, file_id::text FROM litkb.quarantine_payloads "
                              "WHERE file_id = %s", (s["file_id"],)).fetchall()
    assert got == [(rel, "zero-content", "classifier", s["file_id"])], got
    assert _row(first, s["file_id"])["quarantine_row"]["ok"]
    assert "quarantine_row" not in _row(second, s["file_id"]), "a recorded refusal is not written twice"
    assert (env["root"] / rel).exists(), "the bytes are never moved"


# ── the universe: staging, workstreams, works ────────────────────────────────────────────────

@pg_only
def test_bytes_only_a_refused_admission_owns_are_refused_registry(env):
    from litkb import readability as R

    rel = f"_litkb_staging/filed/CONSTRUCTED_refused_{uuid.uuid4().hex[:8]}.pdf"
    _put(env, rel, b"%PDF-1.4 refused bytes " + uuid.uuid4().bytes + b"\n%%EOF\n")
    held = f"_litkb_staging/filed/CONSTRUCTED_copy_{uuid.uuid4().hex[:8]}.pdf"
    native = _copy(env, NATIVE)
    _put(env, held, (env["root"] / native).read_bytes())
    _seed(env, native)                                      # the copy's bytes ARE a files row
    for doc in (rel, held):
        env["conn"].execute(
            "INSERT INTO litkb.admissions (route, admitter_agent, admitter_session, state, checks, workstream_id) "
            "VALUES ('manual', 'r', 'r', 'refused', %s, %s)",
            (_jsonb({"web": {"document": doc, "snapshot": doc + ".txt"}}), env["ws"]))
    res = R.classify(env["conn"], root=env["root"], with_works=False)
    staging = {r["rel_path"]: r for r in res["rows"] if r["row_kind"] == "staging"}
    assert staging[rel]["class"] == "refused-registry", staging
    assert held not in staging and any(s["rel_path"] == held for s in res["skipped_staging"])


@pg_only
def test_a_workstream_file_is_in_the_universe_only_when_its_workstream_is_named(env):
    s = _seed(env, _copy(env, SCAN), mode="proposal")
    main_only = _classify(env, with_works=False)
    assert all(r["file_id"] != s["file_id"] for r in main_only["rows"])
    named = _classify(env, workstreams=[env["ws"]], with_works=False)
    row = _row(named, s["file_id"])
    assert row["scope"] == env["ws"] and row["class"] == "scan-needs-ocr", row


@pg_only
def test_a_work_holding_an_extracted_file_and_a_residue_file_is_mixed(env):
    """PER-FILE COMPLETENESS: the rollup is built from ALL its files."""
    from litkb import readability as R

    a = _seed(env, _copy(env, NATIVE))
    _run(env, a["file_id"], [(pg, f"page {pg}") for pg in range(1, 12)])
    _seed(env, _copy(env, SCAN), work_id=a["work_id"])
    res = R.classify(env["conn"], root=env["root"])
    work = next(r for r in res["rows"] if r["row_kind"] == "work" and r["work_id"] == a["work_id"])
    assert work["class"] == "mixed", work
    per, rollup = R.classify_work_files(env["conn"], a["work_id"], root=env["root"])
    assert rollup == "mixed" and {v["class"] for v in per.values()} == {"extracted", "scan-needs-ocr"}


@pg_only
def test_a_file_less_work_is_no_file_any_route_only_when_every_route_ran(env):
    from litkb import readability as R

    conn, ws = env["conn"], env["ws"]
    tag = uuid.uuid4().hex[:8]
    wid = conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, 'r', 'r')",
        (_jsonb({"key": f"Read_2026_nofile-{tag}"}), _jsonb({"type": "article", "title": "t", "authors": []}),
         ws)).fetchone()[0]
    conn.execute("SELECT litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, NULL, %s, 'r', 'r')",
                 (_jsonb({"scheme": "doi"}), _jsonb({"work_id": str(wid), "value": f"10.5555/read-{tag}",
                                                     "verified_by": "manual", "status": "active"}), ws))

    def work_row():
        res = R.classify(conn, root=env["root"])
        return next(r for r in res["rows"] if r["row_kind"] == "work" and r["work_id"] == str(wid))

    assert work_row()["class"] == R.NOT_ATTEMPTED
    for route, status in (("open_access", "no-oa-copy"), ("annas", "quota-stop"), ("scihub", "blocked")):
        conn.execute("INSERT INTO litkb.acquisition_attempts (work_id, route, status, workstream_id) "
                     "VALUES (%s, %s, %s, %s)", (wid, route, status, ws))
    assert work_row()["class"] == R.NOT_ATTEMPTED, "a quota-stop requested nothing: annas never ran"
    conn.execute("INSERT INTO litkb.acquisition_attempts (work_id, route, status, workstream_id) "
                 "VALUES (%s, 'annas', 'not-in-archive', %s)", (wid, ws))
    assert work_row()["class"] == "no-file-any-route"


# ── the counter, the known-bad, the CSV ──────────────────────────────────────────────────────

@pg_only
def test_fire_unclassified_moves_the_counter_when_a_class_branch_is_removed(env):
    """The design contract's MUTATION at runtime: the `scan-needs-ocr` rule removed, the real scan
    (Anderson 1957, copied) goes unclassified and `unclassified_acquired_files` MOVES."""
    from litkb import readability as R

    rel = _copy(env, SCAN)
    s = _seed(env, rel)
    out = R.fire_unclassified(env["conn"], root=env["root"], drop="scan-needs-ocr")
    assert out["after"] == out["before"] + len(out["moved"]) and rel in out["moved"], out
    n, missing = R.unclassified_acquired_files(env["conn"], root=env["root"])
    assert rel not in missing and n == out["before"]
    assert _row(_classify(env), s["file_id"])["class"] == "scan-needs-ocr"


@pg_only
def test_the_csv_names_its_columns_and_is_never_overwritten(env):
    from litkb import readability as R

    s = _seed(env, _copy(env, SCAN))
    res = _classify(env)
    path = env["tmp"] / "LITKB_READABILITY_test.csv"
    R.write_csv(res, path)
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert tuple(rows[0].keys()) == R.CSV_COLUMNS
    mine = next(r for r in rows if r["file_id"] == s["file_id"])
    assert mine["class"] == "scan-needs-ocr" and mine["row_kind"] == "file" and mine["image_pages"] == "21"
    assert {r["row_kind"] for r in rows} >= {"file", "work"}
    with pytest.raises(FileExistsError):
        R.write_csv(res, path)
    import datetime
    day = datetime.date(2026, 9, 22)
    first = R.default_csv_path(day, reports=env["tmp"])
    assert first.name == "LITKB_READABILITY_2026-09-22.csv"
    R.write_csv(res, first)
    assert R.default_csv_path(day, reports=env["tmp"]).name == "LITKB_READABILITY_2026-09-22_2.csv"


# ── litkb_work shows each file's class and the work's quarantine rows ────────────────────────

@pg_only
def test_litkb_work_shows_each_files_class_and_the_quarantine_rows(env, monkeypatch):
    from litkb import quarantine as Q
    from litkb.db import connect as c
    from litkb.mcp import server

    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_READER_ROLE": "litkb_test",
                 "LITKB_LITERATURE_ROOT": str(env["root"])}.items():
        monkeypatch.setenv(k, v)
    a = _seed(env, _copy(env, NATIVE))
    _run(env, a["file_id"], [(pg, f"page {pg}") for pg in range(1, 12)])
    b = _seed(env, _copy(env, SCAN), work_id=a["work_id"])
    ing = _ingest()
    try:
        Q.record_system(ing, rel_path=f"_quarantine/{a['key']}__staging-orphan__{'f' * 12}.download",
                        sha256="0" * 64, nbytes=1, reason="staging-orphan", origin="reaper", work_id=a["work_id"])
    finally:
        ing.close()
    import json

    res = json.loads(server._work(key=a["key"]))
    assert res["state"] == "extracted", res                  # the ladder is unchanged
    by = {f["file_id"]: f for f in res["files"]}
    assert by[a["file_id"]]["readability"]["class"] == "extracted"
    assert by[b["file_id"]]["readability"]["class"] == "scan-needs-ocr"
    assert res["readability"] == "mixed", res
    assert [q["reason"] for q in res["quarantine"]] == ["staging-orphan"], res["quarantine"]
    for key in ("sha256", "path", "bytes", "pages", "current_run_id", "status", "stem"):
        assert key in by[a["file_id"]], key


@pg_only
def test_the_cli_classifies_every_workstream_and_writes_the_csv(env, capsys):
    """`litkb readability --all-workstreams --csv PATH` on the worker database (reader = the test
    login): the counters line, the CSV, and a workstream-only file in the universe."""
    from litkb import commands

    s = _seed(env, _copy(env, SCAN), mode="proposal")
    out = env["tmp"] / "cli.csv"
    rc = commands.main(["--db", _db(), "readability", "--role", "litkb_test", "--all-workstreams",
                        "--csv", str(out), "--root", str(env["root"])])
    assert rc == 0
    line = capsys.readouterr().out
    assert "unclassified_acquired_files=" in line and f"csv={out}" in line, line
    with open(out, encoding="utf-8", newline="") as fh:
        mine = [r for r in csv.DictReader(fh) if r["file_id"] == s["file_id"]]
    assert [(r["class"], r["scope"]) for r in mine] == [("scan-needs-ocr", env["ws"])], mine


def _db():
    from litkb.db import connect as c

    return c.DB_TEST


# ── clearing: the classifier clears its OWN row once the file is extracted (0030, ruling Q6) ──

def _qrow(env, file_id):
    return env["conn"].execute(
        "SELECT id::text, reason, origin, cleared_at IS NOT NULL, cleared_by, cleared_reason "
        "FROM litkb.quarantine_payloads WHERE file_id = %s ORDER BY recorded_at, id", (file_id,)).fetchall()


@pg_only
def test_the_classifier_clears_its_own_row_once_the_file_is_extracted(env, monkeypatch):
    """A bound file refused `zero-content` (row recorded), then re-extracted with text: a read-only
    classification reports the row STALE; a `record=` run CLEARS it (when, which session, why) and
    `litkb_work` shows it no longer. KNOWN-BAD (mutation C14): clearing disabled -> the file is
    re-classed extracted and the stale row is still shown."""
    import json

    from litkb.db import connect as c
    from litkb.mcp import server

    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_READER_ROLE": "litkb_test",
                 "LITKB_LITERATURE_ROOT": str(env["root"])}.items():
        monkeypatch.setenv(k, v)
    rel = _copy(env, NATIVE)
    s = _seed(env, rel)
    _run(env, s["file_id"], [(1, "")])
    ing = _ingest()
    try:
        _classify(env, record=ing, session="sess-refuse")
        (rid, reason, origin, cleared, _by, _why), = _qrow(env, s["file_id"])
        assert (reason, origin, cleared) == ("zero-content", "classifier", False)
        _run(env, s["file_id"], [(pg, f"page {pg}") for pg in range(1, 12)])
        ro = _classify(env)
        assert _row(ro, s["file_id"])["class"] == "extracted" and _row(ro, s["file_id"])["stale_quarantine"] == 1
        assert ro["counters"]["stale_quarantine_rows"] >= 1
        done = _classify(env, record=ing, session="sess-clear")
    finally:
        ing.close()
    assert _row(done, s["file_id"])["stale_quarantine"] == 0, _row(done, s["file_id"])
    (_rid, _r, _o, cleared, by, why), = _qrow(env, s["file_id"])
    assert cleared and by == "sess-clear" and why.startswith("classified extracted/full"), (cleared, by, why)
    res = json.loads(server._work(key=s["key"]))
    assert res["quarantine"] == [], res["quarantine"]
    assert _row(_classify(env), s["file_id"])["quarantine_ids"] == ""


@pg_only
def test_a_cleared_row_refused_again_is_reopened(env):
    rel = _copy(env, NATIVE)
    s = _seed(env, rel)
    _run(env, s["file_id"], [(1, "")])
    ing = _ingest()
    try:
        _classify(env, record=ing)
        _run(env, s["file_id"], [(1, "text")])
        _classify(env, record=ing)
        assert _qrow(env, s["file_id"])[0][3] is True
        _run(env, s["file_id"], [(1, "")])
        _classify(env, record=ing)
    finally:
        ing.close()
    rows = _qrow(env, s["file_id"])
    assert len(rows) == 1 and rows[0][3] is False and rows[0][4] is None, rows


# ── the queue step (S4 run 3, builder-C item 1c): the classifier reads litkb.extraction_jobs ──────

def _qfile(env, name, pages, **kw):
    """A CONSTRUCTED PDF (litkb.extract.queue_fire.constructed_pdf) under the temp root, seeded as a
    main file. -> (seed dict, rel path)."""
    from litkb.extract import queue_fire as F

    rel = f"Validation/t{uuid.uuid4().hex[:10]}/CONSTRUCTED_{name}.pdf"
    F.constructed_pdf(env["root"] / rel, pages, note=uuid.uuid4().hex, **kw)
    return _seed(env, rel), rel


def _sweep(env, fid, **kw):
    from litkb.extract import queue as Q

    k = Q.connect(_db())
    try:
        return Q.sweep(k, env["root"], files=[fid], **kw)
    finally:
        k.close()


def _qwork(env, fid, extractor, **kw):
    from litkb.extract import queue as Q

    return Q.work(lambda: Q.connect(_db()), env["root"], extractor=extractor,
                  derived=env["root"] / "_derived", files=[fid], **kw)


@pg_only
def test_a_file_waiting_in_the_queue_is_unclassified_never_a_class(env):
    """CONSTRUCTED scan (3 image pages): with no job it is `scan-needs-ocr` (the classifier's own
    evidence); once its OCR range job is QUEUED it is UNCLASSIFIED (waiting — decision D8), flagged
    `waiting`, and the queue step dropped (mutation) would read it as a class again."""
    s, _rel = _qfile(env, "WaitingScan", 3, text=False)
    assert _row(_classify(env), s["file_id"])["class"] == "scan-needs-ocr"
    assert _sweep(env, s["file_id"], ocr=True)["enqueued"] == 1
    row = _row(_classify(env), s["file_id"])
    assert row["class"] is None and row["queue_flag"] == "waiting" and "waiting" in row["evidence"], row
    assert _row(_classify(env, queue=False), s["file_id"])["class"] == "scan-needs-ocr"


@pg_only
def test_a_refused_job_is_its_refusal_when_the_evidence_agrees(env):
    """CONSTRUCTED scan swept with OCR OFF: the queue refuses it `scan-needs-ocr`; the classifier's
    own evidence (no run, image pages) says the same class, so that is the class and the note says
    they agree."""
    s, _rel = _qfile(env, "RefusedScan", 3, text=False)
    assert _sweep(env, s["file_id"], ocr=False)["refused"] == {"scan-needs-ocr": 1}
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "scan-needs-ocr" and row["queue_flag"] is None, row
    assert "evidence agrees" in row["evidence"], row


@pg_only
def test_a_refusal_the_files_evidence_contradicts_is_unclassified_and_says_both(env):
    """CONSTRUCTED native file, fine on disk, with a job REFUSED `bad-file` (a stale refusal: say the
    bytes were repaired after the guard ran). The refusal says bad-file, the evidence says the file is
    readable and waiting: neither is picked — UNCLASSIFIED, flagged `disagreement`. Mutation (the
    agreement check removed) takes the refusal as the class."""
    from litkb.extract import queue as Q

    s, _rel = _qfile(env, "StaleRefusal", 2)
    k = Q.connect(_db())
    try:
        Q.enqueue(k, s["file_id"], None, None, Q.Facts(route="native", pages=2), "bad-file",
                  "CONSTRUCTED stale refusal")
    finally:
        k.close()
    row = _row(_classify(env), s["file_id"])
    assert row["class"] is None and row["queue_flag"] == "disagreement", row
    assert "refused bad-file" in row["evidence"] and "disagree" in row["evidence"], row


@pg_only
def test_a_job_dead_with_no_block_is_zero_content_and_record_mode_writes_its_row(env):
    """CONSTRUCTED: two BLANK pages and an extractor that reads nothing -> the job dies as ZeroContent
    (litkb.extract.queue) -> the file is `zero-content`; `record=` (B's path) writes its classifier
    quarantine row against the bound path."""
    from litkb.extract import queue_fire as F

    s, rel = _qfile(env, "BlankDead", 2, text=False, raster=False)
    _sweep(env, s["file_id"], ocr=True)
    rep = _qwork(env, s["file_id"], F.SyntheticExtractor(silent_pages={1, 2}))
    assert rep["outcomes"].get("failed:dead") == 1, rep
    row = _row(_classify(env), s["file_id"])
    assert row["class"] == "zero-content" and "ZeroContent" in row["evidence"], row
    ing = _ingest()
    try:
        _classify(env, record=ing)
    finally:
        ing.close()
    got = env["conn"].execute("SELECT reason, origin, rel_path FROM litkb.quarantine_payloads "
                              "WHERE file_id = %s", (s["file_id"],)).fetchall()
    assert got == [("zero-content", "classifier", rel)], got


@pg_only
def test_a_job_dead_on_an_extractor_error_stays_unclassified_and_is_counted(env):
    """CONSTRUCTED native file, an extractor that raises every time: the job dies on an extractor
    error. That is a FINDING, never folded into a class: UNCLASSIFIED, flagged `dead-error`, counted
    in `files_queue_dead-error`, the error quoted in the evidence. Mutation (the ZeroContent test
    removed) would call it zero-content."""
    from litkb.extract import queue as Q

    s, _rel = _qfile(env, "ToolDies", 2)
    _sweep(env, s["file_id"], ocr=True)

    def boom(job):
        raise Q.ExtractError("docling produced no artifact: CONSTRUCTED tool failure")

    assert _qwork(env, s["file_id"], boom)["outcomes"].get("failed:dead") == 1
    res = _classify(env)
    row = _row(res, s["file_id"])
    assert row["class"] is None and row["queue_flag"] == "dead-error", row
    assert "CONSTRUCTED tool failure" in row["evidence"], row
    assert res["counters"]["files_queue_dead-error"] >= 1 and res["counters"]["queue_table"] == 1


@pg_only
def test_without_the_queue_table_the_classifier_is_the_pre_queue_one_and_says_so(env, monkeypatch):
    """INJECTED (0029 cannot be dropped alone from a migrated worker db): `queue_present` answering
    False, as the live db does before the orchestrator applies 0029. A file with a queued job then
    classifies exactly as the classifier without its queue step, and `queue_table=0` says so."""
    from litkb import readability as R

    s, _rel = _qfile(env, "NoQueueTable", 3, text=False)
    _sweep(env, s["file_id"], ocr=True)
    monkeypatch.setattr(R, "queue_present", lambda conn: False)
    res = _classify(env)
    row = _row(res, s["file_id"])
    assert row["class"] == "scan-needs-ocr" and row["queue_flag"] is None, row
    assert res["queue_table"] is False and res["counters"]["queue_table"] == 0, res["counters"]


# ── auditor-B fixes (candidate 2cbc551) ──────────────────────────────────────────────────────

@pg_only
def test_a_row_about_other_bytes_at_the_same_path_never_classes_the_file(env):
    """F2, the auditor's reproduction: CONSTRUCTED unopenable bytes refused IN PLACE at a path (a
    `probe-error` / `bind-refusal` row with THEIR sha256), then a good copy of a real native paper
    bound at the SAME path, with no run. The row describes other bytes: the file is UNCLASSIFIED
    (waiting) — never `probe-error` — it counts in `unclassified_acquired_files`, and the row is
    reported in `stale_quarantine_rows`."""
    import hashlib as _h

    from litkb import quarantine as Q
    from litkb import readability as R
    from litkb.db import connect as c

    rel = _copy(env, NATIVE)
    bad = R._constructed_unopenable_pdf(salt=uuid.uuid4().hex)
    w = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
    w.execute("SET ROLE litkb_writer")
    ws2, token = env["conn"].execute(
        "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/f2', NULL, 'f2', NULL)",
        (f"f2-{uuid.uuid4().hex[:8]}",)).fetchone()
    try:
        Q.record(w, ws2, token, rel_path=rel, sha256=_h.sha256(bad).hexdigest(), nbytes=len(bad),
                 reason="probe-error", origin="bind-refusal")
    finally:
        w.close()
    s = _seed(env, rel)
    res = _classify(env)
    row = _row(res, s["file_id"])
    assert row["class"] is None, row
    assert row["stale_quarantine"] == 1 and row["stale_quarantine_ids"] and row["quarantine_ids"] == "", row
    assert res["counters"]["stale_quarantine_rows"] >= 1
    n, missing = R.unclassified_acquired_files(env["conn"], root=env["root"])
    assert rel in missing


@pg_only
def test_the_gated_counter_is_the_number_of_unclassified_file_and_staging_rows(env):
    """F3: `counters()["unclassified_acquired_files"]` — the value the CLI prints and the acceptance
    grades — is exactly the unclassified file + staging rows, and a waiting file moves it by one."""
    from litkb import readability as R

    before = _classify(env, with_works=False)
    _seed(env, _copy(env, NATIVE))                     # native, no run: waiting
    after = _classify(env, with_works=False)
    for res in (before, after):
        want = sum(1 for r in res["rows"] if r["row_kind"] in ("file", "staging") and r["class"] is None)
        assert res["counters"]["unclassified_acquired_files"] == want
        assert R.counters(res)["unclassified_acquired_files"] == want
    assert after["counters"]["unclassified_acquired_files"] == before["counters"]["unclassified_acquired_files"] + 1


@pg_only
def test_a_file_with_one_dead_range_takes_the_dead_ranges_class_and_its_staged_sibling_never_assembles(env):
    """Orchestrator ruling Q2 (S4 run 3): `dead` is final for the JOB, and the FILE takes the dead
    range's class. CONSTRUCTED 30-page scan -> two OCR ranges (1-22, 23-30); the extractor fails on
    range 1-22 every time (it dies at the ceiling), range 23-30 extracts and is STAGED — and stays
    staged: its sibling will never be staged, so the file never assembles, holds no ok run, and is
    UNCLASSIFIED with flag `dead-error` (the dead range died on an extractor error), not `waiting`.
    Its failed run names the dead range. Mutation S4C4 (waiting read before dead) reads it `waiting`."""
    from litkb.extract import queue as Q
    from litkb.extract import queue_fire as F

    s, _rel = _qfile(env, "DeadRange", 30, text=False)
    assert _sweep(env, s["file_id"], ocr=True)["enqueued"] == 2

    def picky(job):
        if tuple(job.page_range or ()) == (1, 22):
            raise Q.ExtractError("docling produced no artifact: CONSTRUCTED failure on range 1-22")
        return F.SyntheticExtractor()(job)

    rep = _qwork(env, s["file_id"], picky)
    assert rep["outcomes"].get("failed:dead") == 1 and rep["outcomes"].get("staged") == 1, rep
    states = env["conn"].execute("SELECT page_start, state FROM litkb.extraction_jobs WHERE file_id = %s "
                                 "ORDER BY page_start", (s["file_id"],)).fetchall()
    assert states == [(1, "dead"), (23, "staged")], states
    assert _qwork(env, s["file_id"], picky)["claimed"] == 0, "a staged range is never handed out again"
    runs = env["conn"].execute("SELECT status, metrics FROM litkb.extraction_runs WHERE file_id = %s",
                               (s["file_id"],)).fetchall()
    assert [r[0] for r in runs] == ["failed"] and runs[0][1]["dead_jobs"][0]["page_start"] == 1, runs
    row = _row(_classify(env), s["file_id"])
    assert row["class"] is None and row["queue_flag"] == "dead-error", row
    assert "CONSTRUCTED failure on range 1-22" in row["evidence"], row


@pg_only
def test_litkb_works_per_file_view_reads_the_queue_too(env):
    """`classify_work_files` (what `litkb_work` shows) runs the same queue step: a CONSTRUCTED scan whose
    OCR job is QUEUED is UNCLASSIFIED there, as in `classify`, never `scan-needs-ocr`. Mutation S4C5
    (its jobs argument dropped at that call site) reads it `scan-needs-ocr`."""
    from litkb import readability as R

    s, _rel = _qfile(env, "WorkViewWaiting", 3, text=False)
    before, _roll = R.classify_work_files(env["conn"], s["work_id"], root=env["root"])
    assert before[s["file_id"]]["class"] == "scan-needs-ocr", before
    assert _sweep(env, s["file_id"], ocr=True)["enqueued"] == 1
    per, rollup = R.classify_work_files(env["conn"], s["work_id"], root=env["root"])
    assert per[s["file_id"]]["class"] is None and "waiting" in per[s["file_id"]]["evidence"], per
    assert rollup is None, rollup

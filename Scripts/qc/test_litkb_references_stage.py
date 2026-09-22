"""litkb S4 — the file-keyed stage-6 driver, the two REPORTED counters, and the two carry-in
instruments.

    `qc/instruments/litkb_references_stage.py`       the driver (selection by rel_path, resume)
    `pipeline/litkb/extract/references_coverage.py`  one predicate for the selector AND the counter
    `qc/instruments/litkb_preprint_stamp.py`         the bioRxiv stamp strip, measured per page
    `qc/instruments/litkb_web_title_region.py`       TITLE_REGION_LINES on web snapshots

Everything that touches a database runs on ``LITKB_TEST_DB`` through the P1 harness class; the
driver reaches the ingest role the way `qc/test_litkb_references_ingest.py` does (owner login +
``SET ROLE litkb_ingest``). Nothing reaches the network or GROBID: the TEI is CONSTRUCTED here
(:func:`constructed_tei`, labelled so in its name) or a REAL recorded one COPIED from the P6
derived cache into ``tmp_path`` (skipped when that cache is not on the machine), GROBID is a
:class:`FakeGrobid`, and every registry answer is the P6 suite's ``StubClient``.

The database is reset once per pytest SESSION, so every seeded file carries a uuid in its stem,
every count is scoped to the files a test seeded (``file_ids=``), and the driver is always given
``only=`` its own rel_paths.

  rule                                                              test
  the selector reaches a staging path, by rel_path, not by key      test_the_selector_reads_rel_path_including_staging
  KNOWN-BAD: a file with blocks and no stage-6 run moves the count  test_files_without_reference_stage_counts_what_owes_the_stage
  a run under the previous resolver version (litkb-p6-1) is owed    test_a_run_under_the_previous_resolver_version_is_superseded
  anchor rate = anchored / refs whose DOI is a held work's          test_the_anchor_rate_uses_the_real_denominator
  a rerun is idempotent: nothing re-selected, no duplicate refs     test_the_driver_runs_then_a_rerun_writes_nothing
  a kill between files resumes with the rest                        test_a_kill_between_files_resumes_with_the_rest
  the bytes posted are the bytes the row names                      test_a_file_whose_bytes_changed_is_refused_not_posted
  GROBID is never stopped unless this driver started it             test_grobid_is_stopped_only_when_started_here
  one driver per database                                           test_a_second_driver_is_refused_while_one_holds_the_lock
  a real recorded TEI goes through parse + ingest                   test_a_real_recorded_tei_is_ingested_in_full
  the instruments run on copied real files                          test_preprint_stamp_instrument_smoke / test_web_title_region_instrument_smoke

Mutation rows P6-D1..P6-D7 (`qc/instruments/litkb_p6_mutations.py`) weaken each guard; each must
turn this file red.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import uuid

import pytest

from litkb.extract import references as R
from litkb.extract import references_coverage as RC

from test_litkb_p1 import _PG  # noqa: E402 - the P1 harness class, not its fixture
from test_litkb_references import BENEDEK, StubClient  # noqa: E402 - the P6 registry stub

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
pg_only = pytest.mark.requires_litkb_pg

#: The REAL recorded TEIs (GROBID 0.9.1, includeRawCitations=1) the P6 run cached on 2026-09-15.
P6_TEI = pathlib.Path(os.environ.get("LITKB_DERIVED") or r"D:\edmonds-pipeline\litkb_derived") / "p6" / "tei"
LIT = pathlib.Path(os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture"))


def _instrument(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "qc" / "instruments" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def drv():
    return _instrument("litkb_references_stage")


@pytest.fixture(autouse=True)
def _no_wire_no_real_cache(monkeypatch, tmp_path):
    """No test here may reach a registry or write the real P6 disk cache: the real HTTP client
    raises, and the cache root default points into tmp_path. (A first draft of the driver swapped
    in the real client whenever `pacer` was None; this fixture is what makes that loud.)"""
    from litkb import netutil

    def _refuse(*_a, **_k):
        raise RuntimeError("a test reached the network through litkb.netutil.Client")

    monkeypatch.setattr(netutil.Client, "get", _refuse)
    monkeypatch.setattr(R, "DERIVED_ROOT", str(tmp_path / "derived_guard"))


@pytest.fixture(scope="session")
def _s6d(litkb_pg_base):
    psycopg, conn, ran = litkb_pg_base
    yield _PG(psycopg, conn, ran)


@pytest.fixture
def pg(_s6d):
    yield _s6d
    while _s6d.opened:
        _s6d.opened.pop().close()


# ── the CONSTRUCTED TEI ─────────────────────────────────────────────────────────────────

def constructed_tei(doi_held, doi_other):
    """CONSTRUCTED — not GROBID output. Three references in the shape GROBID emits with
    ``includeRawCitations=1``: b0 carries `doi_held` (the stub registry confirms it), b1 carries
    `doi_other` (confirmed too, but no held work has it), b2 carries no DOI and nothing the stub's
    search returns. Two body mentions of b0 (one wrapping a line: two boxes, ONE element), one of b1."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
 <teiHeader><fileDesc><sourceDesc><biblStruct>
   <analytic><title level="a" type="main">A constructed citing paper</title></analytic>
   <monogr><imprint><date type="published" when="2020"/></imprint></monogr>
 </biblStruct></sourceDesc></fileDesc></teiHeader>
 <text>
  <body><p>
   <s coords="1,10,10,100,10">Constructed text citing <ref type="bibr" coords="1,20,10,8,8"
     target="#b0">[1]</ref> and <ref type="bibr" coords="1,30,10,8,8" target="#b1">[2]</ref>.</s>
   <s coords="2,10,20,100,10">Again <ref type="bibr" coords="2,40,20,8,8;2,50,20,8,8"
     target="#b0">[1]</ref> across a line break.</s>
  </p></body>
  <back><div type="references"><listBibl>
   <biblStruct xml:id="b0" coords="9,32,200,250,7">
     <analytic><title level="a" type="main">{BENEDEK['title']}</title>
       <author><persName><surname>{BENEDEK['family']}</surname></persName></author>
       <idno type="DOI">{doi_held}</idno></analytic>
     <monogr><title level="j">IEEE TGRS</title>
       <imprint><date type="published" when="{BENEDEK['year']}"/></imprint></monogr>
     <note type="raw_reference">C. Benedek, {BENEDEK['title']}, IEEE TGRS ({BENEDEK['year']}). doi:{doi_held}</note>
   </biblStruct>
   <biblStruct xml:id="b1" coords="9,32,210,250,7">
     <analytic><title level="a" type="main">A second constructed cited study</title>
       <author><persName><surname>Otherauthor</surname></persName></author>
       <idno type="DOI">{doi_other}</idno></analytic>
     <monogr><imprint><date type="published" when="2011"/></imprint></monogr>
     <note type="raw_reference">Otherauthor, A second constructed cited study (2011). doi:{doi_other}</note>
   </biblStruct>
   <biblStruct xml:id="b2" coords="9,32,220,250,7">
     <analytic><title level="a" type="main">An unresolvable constructed reference</title>
       <author><persName><surname>Nobody</surname></persName></author></analytic>
     <monogr><imprint><date type="published" when="1999"/></imprint></monogr>
     <note type="raw_reference">Nobody, An unresolvable constructed reference (1999).</note>
   </biblStruct>
  </listBibl></div></back>
 </text>
</TEI>""".encode()


def stub_for(doi_held, doi_other):
    """The P6 StubClient answering /works/{doi} for both DOIs (a search returns nothing)."""
    return StubClient(work={
        R.normalize_doi(doi_held): dict(BENEDEK, doi=R.normalize_doi(doi_held)),
        R.normalize_doi(doi_other): {"doi": R.normalize_doi(doi_other), "family": "Otherauthor",
                                     "title": "A second constructed cited study", "year": 2011}})


class FakeGrobid:
    """The `litkb_references_stage.GrobidHold` face: returns `tei` for every file, records calls."""

    def __init__(self, tei):
        self._tei = tei
        self.posted = []
        self.started_here = False
        self.stopped = False

    def tei(self, path):
        self.posted.append(str(path))
        return self._tei

    def close(self):
        pass


# ── seeding: works, files, a current stage-5 run with blocks, stage-6 runs ──────────────

def _j(pg, obj):
    return pg.Jsonb(obj)


def seed_work(pg, ws, *, doi=None):
    key = f"Seed_2020_{uuid.uuid4().hex[:8]}-refstage"
    work_id = pg.one(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, "
        "'setup', 'setup')",
        (_j(pg, {"key": key}), _j(pg, {"type": "article", "title": key, "authors": []}), ws))[0]
    if doi:
        pg.one("SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, "
               "NULL, %s, 'setup', 'setup')",
               (_j(pg, {"scheme": "doi"}), _j(pg, {"work_id": str(work_id), "value": doi,
                                                   "status": "active"}), ws))
    return work_id, key


def seed_file(pg, ws, rel_path, *, data=None, blocks=True, current=True, doi=None):
    """A held work and its file at `rel_path` (sha256 = that of `data` when given), with a current
    ok 5-reconcile run holding one block unless `blocks`/`current` say otherwise."""
    work_id, key = seed_work(pg, ws, doi=doi)
    sha = hashlib.sha256(data).hexdigest() if data is not None else uuid.uuid4().hex + uuid.uuid4().hex
    file_id = pg.one(
        "SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, "
        "'setup', 'setup')",
        (_j(pg, {"sha256": sha}), _j(pg, {"work_id": str(work_id), "rel_path": rel_path,
                                          "status": "active"}), ws))[0]
    if current:
        run_id = pg.one(
            "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
            "pipeline_version, host, status) VALUES (%s, '5-reconcile', 'seed', '0', %s, 'v0', "
            "'local', 'ok') RETURNING id", (file_id, uuid.uuid4().hex[:16]))[0]
        pg.one("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
        if blocks:
            pg.conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                            "VALUES (%s, %s, 1, 'paragraph', 'A seeded block.')", (file_id, run_id))
    return {"file_id": file_id, "work_id": work_id, "key": key, "rel_path": rel_path, "sha256": sha}


def seed_stage6(pg, file_id, *, status="ok", params_hash=None, version=None):
    """A stage-6 run row at the current key (or at another `params_hash` / `version`), as a
    finished or a killed (`failed`) run would leave it."""
    k = RC.current_key()
    pg.conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, %s, %s, %s, %s, %s, 'local', %s)",
        (file_id, k["stage"], k["tool"], version or k["tool_version"], params_hash or k["params_hash"],
         version or k["pipeline_version"], status))


def uniq(stem):
    return f"{stem}_{uuid.uuid4().hex[:10]}"


def reader(pg):
    return pg.session("litkb_reader")


def ingest(pg):
    return pg.session("litkb_ingest")


def refs_of(conn, file_id):
    return conn.execute('SELECT count(*) FROM litkb."references" WHERE file_id = %s',
                        (file_id,)).fetchone()[0]


def stage6_runs(conn, file_id):
    return conn.execute("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s "
                        "AND stage = '6-references'", (file_id,)).fetchone()[0]


# ── the selector ────────────────────────────────────────────────────────────────────────

@pg_only
def test_the_selector_reads_rel_path_including_staging(pg):
    """The P6 instrument could only post ``Validation/<stem>.pdf``; 55 of the 233 files with
    blocks live under `_litkb_staging/`. The selector returns each file's OWN rel_path — and the
    stem of that path is not derivable from the work key (the key here is a different string)."""
    ws = pg.ws()
    staged = seed_file(pg, ws, f"_litkb_staging/filed/{uniq('Staged_2020_truncated-slug-longer')}.pdf")
    incoming = seed_file(pg, ws, f"_litkb_staging/incoming/{uniq('t999_Incoming_2021')}.download")
    valid = seed_file(pg, ws, f"Validation/{uniq('Valid_2019_plain')}.pdf")
    done = seed_file(pg, ws, f"Validation/{uniq('Done_2018_already')}.pdf")
    seed_stage6(pg, done["file_id"])
    blockless = seed_file(pg, ws, f"Validation/{uniq('Blockless_2017_x')}.pdf", blocks=False)
    unextracted = seed_file(pg, ws, f"Validation/{uniq('Bound_2016_x')}.pdf", current=False)
    ids = [f["file_id"] for f in (staged, incoming, valid, done, blockless, unextracted)]
    got = RC.pending_files(reader(pg), file_ids=ids)
    assert [r["rel_path"] for r in got] == sorted([staged["rel_path"], incoming["rel_path"],
                                                   valid["rel_path"]])
    assert all(r["sha256"] and r["work_id"] for r in got)
    assert staged["key"] not in staged["rel_path"], "the rel_path is not composed from the key"


# ── the counters (the KNOWN-BAD) ────────────────────────────────────────────────────────

@pg_only
def test_files_without_reference_stage_counts_what_owes_the_stage(pg):
    """KNOWN-BAD, CONSTRUCTED rows. Of four files with stage-5 blocks, only the one with an OK
    stage-6 run AT THE CURRENT KEY has had the stage: a killed run left `failed`, and an ok run at
    an older params hash, are both still owed. A fifth file with no blocks is outside the
    denominator. Then ONE more file with blocks and no stage-6 run must move the count by one.

    Mutations that must turn this red: the owed filter broken (P6-D1), the `ok` status dropped
    from "the stage ran" (P6-D2), the params hash dropped from the key (P6-D3)."""
    ws = pg.ws()
    owes = seed_file(pg, ws, f"Validation/{uniq('Owes_2020_x')}.pdf")
    ran = seed_file(pg, ws, f"Validation/{uniq('Ran_2020_x')}.pdf")
    seed_stage6(pg, ran["file_id"])
    killed = seed_file(pg, ws, f"Validation/{uniq('Killed_2020_x')}.pdf")
    seed_stage6(pg, killed["file_id"], status="failed")
    stale = seed_file(pg, ws, f"Validation/{uniq('Stale_2020_x')}.pdf")
    seed_stage6(pg, stale["file_id"], params_hash="0000000000000000")
    noblocks = seed_file(pg, ws, f"Validation/{uniq('Noblocks_2020_x')}.pdf", blocks=False)
    ids = [f["file_id"] for f in (owes, ran, killed, stale, noblocks)]

    c = RC.reference_counters(reader(pg), file_ids=ids)
    assert c["files_without_reference_stage_ratio"] == (3, 4), c
    assert (c["files_with_reference_stage"], c["files_with_stage5_blocks"]) == (1, 4), c
    assert {r["file_id"] for r in RC.pending_files(reader(pg), file_ids=ids)} == \
        {owes["file_id"], killed["file_id"], stale["file_id"]}, "the selector and the counter disagree"

    more = seed_file(pg, ws, f"_litkb_staging/filed/{uniq('More_2020_x')}.pdf")
    c2 = RC.reference_counters(reader(pg), file_ids=ids + [more["file_id"]])
    assert c2["files_without_reference_stage_ratio"] == (4, 5), c2
    line = RC.format_counters(c2)
    assert "files_without_reference_stage=4/5(80.0%)" in line and "reference_anchor_rate=0/0(n/a)" in line


@pg_only
def test_a_run_under_the_previous_resolver_version_is_superseded(pg):
    """S4 run 3 decision D12: `references.PIPELINE_VERSION` moved to litkb-p6-2 because commit
    8829558 changed the resolution ladder after the 17 live litkb-p6-1 runs were made. A file whose
    only stage-6 run is an ok litkb-p6-1 run OWES the stage, and that run's references are NOT in
    the anchor-rate population — only the current key is read, by the counters and the selector."""
    from litkb.extract import references_ingest as RI

    assert RC.current_key()["pipeline_version"] == R.PIPELINE_VERSION == RI._tool_version() != "litkb-p6-1"
    ws = pg.ws()
    old = seed_file(pg, ws, f"Validation/{uniq('Old_2015_resolver')}.pdf")
    seed_stage6(pg, old["file_id"], version="litkb-p6-1")
    c = RC.reference_counters(reader(pg), file_ids=[old["file_id"]])
    assert c["files_without_reference_stage_ratio"] == (1, 1), c
    assert c["references"] == 0 and c["reference_anchor_rate"] == (0, 0), c
    assert [r["file_id"] for r in RC.pending_files(reader(pg), file_ids=[old["file_id"]])] == [old["file_id"]]


@pg_only
def test_the_anchor_rate_uses_the_real_denominator(pg, drv, tmp_path):
    """R4's kill line (Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md §1.2): the rate is
    anchored / references whose resolved DOI is a held work's ACTIVE DOI — never anchored / all
    references. CONSTRUCTED TEI: b0 resolves to a held DOI (anchored, with an in-corpus edge),
    b1 resolves to a DOI no held work has, b2 does not resolve. So the rate is 1/1 and the
    anchored share of all references is 1/3. Mutation P6-D4 (the denominator counts every
    reference) must turn this red."""
    ws = pg.ws()
    tag = uuid.uuid4().hex[:10]
    doi_held, doi_other = f"10.9999/held.{tag}", f"10.9999/other.{tag}"
    cited_id, cited_key = seed_work(pg, ws, doi=doi_held)
    data = b"%PDF-1.4 constructed " + tag.encode()
    root = tmp_path / "lit"
    f = seed_file(pg, ws, f"_litkb_staging/filed/{uniq('Citing_2020_anchor')}.pdf", data=data)
    (root / "_litkb_staging" / "filed").mkdir(parents=True)
    (root / f["rel_path"]).write_bytes(data)
    conn = ingest(pg)
    stub = stub_for(doi_held, doi_other)
    s = drv.run(conn, root=str(root), derived=str(tmp_path / "p6"), progress=str(tmp_path / "prog.jsonl"),
                grobid=FakeGrobid(constructed_tei(doi_held, doi_other)), client=stub, pacer=None,
                corpus_index={R.normalize_doi(doi_held): {"key": cited_key, "title": "", "source": "t"}},
                only=[f["rel_path"]], echo=lambda *_: None)
    assert s["files"].get("ok") == 1, s
    # the INJECTED client answered — a driver that swapped in the real one would reach the wire
    assert any(R.normalize_doi(doi_held) in u for u in stub.urls), stub.urls
    c = RC.reference_counters(reader(pg), file_ids=[f["file_id"]])
    assert c["reference_anchor_rate"] == (1, 1), c
    assert c["references_anchored_ratio"] == (1, 3), c
    assert (c["references_resolved"], c["citation_edges"]) == (2, 1), c
    assert c["anchored_with_citation_edge_ratio"] == (1, 1) and c["anchored_outside_held_doi"] == 0, c
    anchored = conn.execute('SELECT resolved_work_id FROM litkb."references" WHERE file_id = %s '
                            "AND resolved_work_id IS NOT NULL", (f["file_id"],)).fetchall()
    assert anchored == [(cited_id,)]


# ── the driver: run, rerun, resume ──────────────────────────────────────────────────────

def _two_files(pg, tmp_path, tag):
    ws = pg.ws()
    root = tmp_path / "lit"
    files = []
    for rel in (f"_litkb_staging/filed/{uniq('First_2020_' + tag)}.pdf",
                f"Validation/{uniq('Second_2021_' + tag)}.pdf"):
        data = f"%PDF-1.4 constructed {rel}".encode()
        f = seed_file(pg, ws, rel, data=data)
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
        files.append(f)
    return root, sorted(files, key=lambda f: f["rel_path"])     # the driver's order (byte order)


class _NoWire(StubClient):
    """The P6 stub, and proof it was the one used: every URL it answers is recorded, and a test
    asserts `urls` is non-empty after a run that resolved anything."""


def _run(drv, conn, root, tmp_path, files, grobid, client=None, **kw):
    client = client or _NoWire(work={})
    out = drv.run(conn, root=str(root), derived=str(tmp_path / "p6"),
                  progress=str(tmp_path / "progress.jsonl"), grobid=grobid, client=client,
                  pacer=None, corpus_index={}, only=[f["rel_path"] for f in files],
                  echo=lambda *_: None, **kw)
    if out["files"].get("references"):
        assert client.urls, "references were resolved but the injected client saw no request"
    return out


def _progress(tmp_path):
    return [json.loads(ln) for ln in (tmp_path / "progress.jsonl").read_text(encoding="utf-8").splitlines()]


@pg_only
def test_the_driver_runs_then_a_rerun_writes_nothing(pg, drv, tmp_path):
    root, files = _two_files(pg, tmp_path, "rerun")
    tei = constructed_tei("10.9999/x.rerun", "10.9999/y.rerun")
    conn = ingest(pg)
    g = FakeGrobid(tei)
    s1 = _run(drv, conn, root, tmp_path, files, g)
    assert s1["selected"] == 2 and s1["files"]["ok"] == 2 and s1["files"]["references"] == 6, s1
    assert len(g.posted) == 2 and g.posted[0].endswith(os.path.normpath(files[0]["rel_path"]))
    before = [refs_of(conn, f["file_id"]) for f in files]
    assert before == [3, 3]
    lines = _progress(tmp_path)
    assert [ln["status"] for ln in lines[:-1]] == ["ok", "ok"] and "summary" in lines[-1]
    assert all(ln["tei"] == "grobid" and ln["references"] == 3 and ln["error"] is None
               for ln in lines[:-1])
    for f in files:   # the TEI is cached by the file row's sha256, with its sidecar
        assert (tmp_path / "p6" / "tei" / f"{f['sha256']}.tei.xml.sha256").exists()
        assert (tmp_path / "p6" / "files" / f["sha256"] / "references.jsonl").exists()

    g2 = FakeGrobid(tei)
    s2 = _run(drv, conn, root, tmp_path, files, g2)
    assert s2["selected"] == 0 and g2.posted == [], "a rerun re-selected files that already ran"
    assert [refs_of(conn, f["file_id"]) for f in files] == before, "a rerun duplicated references"
    assert [stage6_runs(conn, f["file_id"]) for f in files] == [1, 1]
    assert RC.reference_counters(reader(pg), file_ids=[f["file_id"] for f in files])[
        "files_without_reference_stage_ratio"] == (0, 2)


@pg_only
def test_a_kill_between_files_resumes_with_the_rest(pg, drv, tmp_path):
    """The driver is killed after the first file committed and before the second started. The
    rerun takes only the second, and neither file ends with a duplicate reference list."""
    root, files = _two_files(pg, tmp_path, "resume")
    tei = constructed_tei("10.9999/x.resume", "10.9999/y.resume")
    conn = ingest(pg)

    def kill(i, _line):
        raise KeyboardInterrupt("simulated kill between files")

    with pytest.raises(KeyboardInterrupt):
        _run(drv, conn, root, tmp_path, files, FakeGrobid(tei), _after_file=kill)
    assert [stage6_runs(conn, f["file_id"]) for f in files] == [1, 0]
    assert [ln["rel_path"] for ln in _progress(tmp_path)] == [files[0]["rel_path"]]

    g = FakeGrobid(tei)
    s = _run(drv, conn, root, tmp_path, files, g)
    assert s["selected"] == 1 and s["files"]["ok"] == 1, s
    assert len(g.posted) == 1 and g.posted[0].endswith(os.path.normpath(files[1]["rel_path"]))
    assert [refs_of(conn, f["file_id"]) for f in files] == [3, 3]
    assert [stage6_runs(conn, f["file_id"]) for f in files] == [1, 1]


@pg_only
def test_a_cached_tei_is_reused_and_not_posted_again(pg, drv, tmp_path):
    """The TEI a killed ingest left behind (sidecar intact) is used as is: no second GROBID post."""
    root, files = _two_files(pg, tmp_path, "cached")
    tei = constructed_tei("10.9999/x.cached", "10.9999/y.cached")
    p5 = drv._p5()
    for f in files:
        p5._write_atomic(str(tmp_path / "p6" / "tei" / f"{f['sha256']}.tei.xml"), tei, mode="wb")
    g = FakeGrobid(tei)
    s = _run(drv, ingest(pg), root, tmp_path, files, g)
    assert s["files"]["ok"] == 2 and g.posted == [], s
    assert [ln["tei"] for ln in _progress(tmp_path)[:-1]] == ["cached", "cached"]


@pg_only
def test_a_file_whose_bytes_changed_is_refused_not_posted(pg, drv, tmp_path):
    """KNOWN-BAD, CONSTRUCTED. The bytes at the rel_path no longer hash to the file row's sha256:
    the TEI would be of some other document and would be cached under the row's sha. Refused, never
    posted, and the file stays owed. Mutation P6-D5 must turn this red."""
    root, files = _two_files(pg, tmp_path, "mismatch")
    (root / files[0]["rel_path"]).write_bytes(b"%PDF-1.4 some OTHER document")
    g = FakeGrobid(constructed_tei("10.9999/x.mm", "10.9999/y.mm"))
    conn = ingest(pg)
    s = _run(drv, conn, root, tmp_path, files[:1], g)
    line = _progress(tmp_path)[0]
    assert line["status"] == "error" and line["error"].startswith("sha-mismatch"), line
    assert g.posted == [] and stage6_runs(conn, files[0]["file_id"]) == 0
    assert s["files"] == {"error": 1, "references": 0, "resolved": 0, "anchored": 0, "citation_edges": 0}


@pg_only
def test_a_missing_file_is_an_error_row_and_the_batch_goes_on(pg, drv, tmp_path):
    root, files = _two_files(pg, tmp_path, "missing")
    os.remove(root / files[0]["rel_path"])
    s = _run(drv, ingest(pg), root, tmp_path, files, FakeGrobid(constructed_tei("10.9999/x.mi", "10.9999/y.mi")))
    lines = _progress(tmp_path)
    assert lines[0]["error"].startswith("file-missing") and lines[1]["status"] == "ok", lines
    assert s["files"]["error"] == 1 and s["files"]["ok"] == 1


# ── GROBID and the lock ─────────────────────────────────────────────────────────────────

def test_grobid_is_stopped_only_when_started_here(drv):
    """`hunt` stops GROBID after every file and a queue worker may share the service: a GROBID
    this driver found running is never stopped by it; one it started is stopped once, at the end.
    Mutation P6-D6 (stop whenever not yet stopped) must turn this red."""
    calls = []

    def hold_for(tag):
        return drv.GrobidHold(health=lambda url: tag == "up", start=lambda url, wait: True,
                              stop=lambda: calls.append(("stop", tag)),
                              process=lambda p, url, include_raw_citations: b"<TEI/>",
                              hold=lambda: calls.append(("hold", tag)))

    found = hold_for("up")
    found.tei("x.pdf")
    found.close()
    assert ("stop", "up") not in calls and not found.started_here
    assert ("hold", "up") in calls, "the distro is held even when the service was already up"
    mine = hold_for("down")
    mine.tei("x.pdf")
    mine.tei("y.pdf")
    mine.close()
    mine.close()
    assert calls.count(("stop", "down")) == 1 and mine.started_here


def test_grobid_that_cannot_start_ends_the_batch(drv):
    g = drv.GrobidHold(health=lambda url: False, start=lambda url, wait: False, stop=lambda: None,
                       process=lambda *a, **k: b"", hold=lambda: None, wait=0)
    with pytest.raises(drv.GrobidUnavailable):
        g.tei("x.pdf")
    g.close()
    assert not g.stopped


@pg_only
def test_a_second_driver_is_refused_while_one_holds_the_lock(pg, drv, tmp_path):
    """A detached driver and a second one started by mistake must not race the same files.
    Mutation P6-D7 (the lock not taken) must turn this red."""
    first = ingest(pg)
    assert drv.take_lock(first)
    with pytest.raises(SystemExit, match="another stage-6 driver"):
        drv.run(ingest(pg), root=str(tmp_path), derived=str(tmp_path / "p6"),
                progress=str(tmp_path / "p.jsonl"), grobid=FakeGrobid(b""), client=StubClient(),
                pacer=None, corpus_index={}, only=["nothing"], echo=lambda *_: None)
    first.close()


# ── a REAL recorded TEI ─────────────────────────────────────────────────────────────────

@pg_only
def test_a_real_recorded_tei_is_ingested_in_full(pg, drv, tmp_path):
    """A REAL GROBID TEI (P6's 2026-09-15 cache, includeRawCitations=1), COPIED into tmp_path —
    the smallest one on disk. Every registry answer is a 404 (no network), so every reference is
    unresolved and becomes a candidate; what is asserted is that the driver carries the whole
    parsed reference list into the database, raw strings intact."""
    real = P6_TEI / "Goodchild_2004_general-framework-error-analysis.tei.xml"
    if not real.exists():
        pytest.skip(f"the recorded P6 TEI is not on this machine ({real})")
    shutil.copy(real, tmp_path / real.name)
    tei = (tmp_path / real.name).read_bytes()
    parsed = R.parse_references(tei)
    assert parsed and all(r["raw_source"] == "grobid-raw" for r in parsed)
    ws = pg.ws()
    data = b"%PDF-1.4 stands in for the Goodchild PDF"
    f = seed_file(pg, ws, f"Validation/{uniq('Goodchild_2004_general-framework-error-analysis')}.pdf",
                  data=data)
    (tmp_path / "lit" / "Validation").mkdir(parents=True)
    (tmp_path / "lit" / f["rel_path"]).write_bytes(data)
    conn = ingest(pg)
    stub = StubClient(work={}, work_status=404)
    s = drv.run(conn, root=str(tmp_path / "lit"), derived=str(tmp_path / "p6"),
                progress=str(tmp_path / "progress.jsonl"), grobid=FakeGrobid(tei), client=stub,
                pacer=None, corpus_index={}, only=[f["rel_path"]], echo=lambda *_: None)
    assert s["files"]["ok"] == 1, _progress(tmp_path)
    assert stub.urls, "the stub answered nothing: the driver reached for another client"
    raws = [r[0] for r in conn.execute('SELECT raw_text FROM litkb."references" WHERE file_id = %s '
                                       "ORDER BY ref_index", (f["file_id"],)).fetchall()]
    assert raws == [r["raw"] for r in parsed]


# ── the dry run and the CLI's read-only paths ───────────────────────────────────────────

@pg_only
def test_the_dry_run_splits_by_directory_and_writes_nothing(pg, drv, tmp_path):
    ws = pg.ws()
    a = seed_file(pg, ws, f"_litkb_staging/incoming/{uniq('Dry_2020_x')}.download")
    rd = reader(pg)
    d = drv.dry_run(rd, derived=str(tmp_path / "p6"))
    assert a["rel_path"] in [r["rel_path"] for r in d["rows"]]
    assert d["by_dir"].get("_litkb_staging/incoming", 0) >= 1 and d["count"] == len(d["rows"])
    assert sum(d["by_dir"].values()) == d["count"] == sum(d["by_origin"].values())
    assert not (tmp_path / "p6").exists(), "a dry run wrote under the derived directory"


def test_the_small_path_helpers(drv):
    assert drv.rel_dir("_litkb_staging/filed/X_2020_y.pdf") == "_litkb_staging/filed"
    assert drv.rel_dir("Validation/X_2020_y.pdf") == "Validation"
    assert drv.stage5_origin(r"D:\edmonds-pipeline\litkb_derived\hunt\ab.docling.json") == "hunt"
    assert drv.stage5_origin(None) == "?"
    assert drv.stem_of("_litkb_staging/incoming/t286_Crowder_2017_bernoulli-cusum.download") == \
        "t286_Crowder_2017_bernoulli-cusum"


# ── the two carry-in instruments, on COPIED real files ──────────────────────────────────

def test_preprint_stamp_instrument_smoke(tmp_path):
    """The bioRxiv stamp measurement on a COPY of the base's one bioRxiv file (E21's preprint).
    Skipped when the corpus or pdftotext is absent. Asserts the instrument's own contract — one
    row per page, the independent detector and the regex each stated per page — not the finding."""
    inst = _instrument("litkb_preprint_stamp")
    src = LIT / "_litkb_staging" / "filed" / "Valavi_2018_blockcv-r-package-generating.pdf"
    if not src.exists() or not inst.pdftotext_path():
        pytest.skip("the Valavi bioRxiv PDF or pdftotext is not on this machine")
    pdf = tmp_path / src.name
    shutil.copy(src, pdf)
    rows = inst.measure(pdf, doi="10.1101/357798")
    assert len(rows) == inst.page_count(pdf) and rows[0]["page"] == 1
    for r in rows:
        assert set(inst.COLUMNS) <= set(r)
        if r["regex_hit"]:
            assert r["chars_stripped"] > 0
    assert rows[0]["stamp_present"], "page 1 of the bioRxiv preprint carries its stamp"


def test_web_title_region_instrument_smoke(tmp_path):
    """TITLE_REGION_LINES on a COPY of the one bound web snapshot (Center_2015). Its binding
    recorded line 0 at ratio 1.0 — the instrument, through the binding's own windowing, must agree."""
    inst = _instrument("litkb_web_title_region")
    src = LIT / "_litkb_staging" / "web" / "hunt-20260922T033750.txt"
    if not src.exists():
        pytest.skip("the web snapshot is not on this machine")
    txt = tmp_path / src.name
    shutil.copy(src, txt)
    row = inst.measure_text(txt.read_text(encoding="utf-8"), "ortho_image15c_point - GIS Data Catalog")
    assert row["first_index"] == 0 and row["first_ratio"] == 1.0 and row["within_region"] is True
    none = inst.measure_text("line one\nline two\n", "A title that is nowhere on this page")
    assert none["first_index"] is None and none["within_region"] is None

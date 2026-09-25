r"""S4.5 builder FX-R: the re-run machinery (S4.5 decision D49) — `hardening --freeze --rows-from` and the run
driver's kept register takes.

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_rerun.py -q -p no:cacheprovider

WHAT IS BEING HELD. hardening-2 must re-run hardening-1's OWN 198 row definitions under a new freeze — never a fresh
selector freeze, which on 2026-09-24 picked a different population (S4.5 decision D40: 109 of 198 row ids changed) —
with each row's mode re-read from the file state at the new freeze, and the register rows whose hardening-1 takes are
the register's recorded truth KEPT (carried, not re-run) unless the operator names one (D49: E03, whose outcome the
dedupe fix changes).

THE REAL ROWS. qc/fixtures/litkb_hardening_1_manifest.json and qc/fixtures/litkb_hardening_1_run.csv are byte copies
of the ladder-1 live pass's frozen manifest (198 rows) and its finished run CSV (195 takes); provenance and content
hashes in qc/fixtures/litkb_hardening_1.provenance.json. Every other input here says CONSTRUCTED in its name.

ON MAIN 411c3ce these fail: `--rows-from`, `--run-label`, `rows_from_source`, `kept_register_takes`, `--rerun-kept`
and the run CSV's `take_from` column do not exist there.

KNOWN-BADS (mutation rows FXR1-FXR9 in qc/instruments/litkb_p2_mutations.py), each a WORSE ANSWER, never an error:
  the mode copied from the source, not re-read                      -> a work bound since keeps `hunt`
  the rows-from freeze falls back to a fresh selector freeze (D40)  -> 198 real rows become the selectors' few
  the clash guard removed                                           -> a re-run's run CSV is its source's (resumed)
  a kept take re-run although nobody named it                       -> E13/E20/E07 hunted again
  --rerun-kept ignored                                              -> E03 carried, never re-run under the fix
  a carried take written over this manifest's own take on resume     -> E03's new take lost
  --rerun-kept accepts any id                                        -> a typo re-runs nothing, silently
  an edited source accepted                                          -> rows the source never froze
  every register row with a reference kept                           -> E21's measured take never re-run
Round 2 (auditor-FX-R round 1: F1, N2, N3, N5, AUD1), rows FXR10-FXR15:
  a missing source run CSV read as "no takes" (F1)                  -> E07/E13/E20 hunted again, exit 0
  the default source run CSV resolved against the CWD (AUD8)        -> the source's takes not found
  a kept row named but outside --only dropped from the CSV (N3)      -> E03's take vanishes from the graded CSV
  a carried take treated as this manifest's own (AUD1)               -> E03 named on a later pass never re-run
  a null-work arXiv measure row looked up as a DOI (N2)              -> skipped/work-not-in-main, never measured
  a register row no source row holds left out of kept_missing (N5)  -> silently absent
"""
import csv
import importlib.util
import json
import os
import uuid
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

SCRIPTS = Path(__file__).resolve().parent.parent
FIXTURES = SCRIPTS / "qc" / "fixtures"
H1 = FIXTURES / "litkb_hardening_1_manifest.json"
H1_RUN = FIXTURES / "litkb_hardening_1_run.csv"
REGISTER = FIXTURES / "litkb_hunt_edge_cases.json"

#: hardening-1's own self-hash and the content hash of the tracked copy (provenance file beside it)
H1_MANIFEST_SHA = "3c918f64f16fb41974df24f710f6bbd22e91acd9569112109a840bdbbb3ddc5a"
H1_CONTENT_SHA = "5a813fc6d275201e37e1f535e44819d0eaa1040e7dc83114df3a39ff601b25ae"
H1_RUN_CONTENT_SHA = "ee5cac3b66cbbc37566593dd61ddbded3102955f860abdaf71d417295fdb97a5"

#: the four register rows the ladder-1 pass recorded (register rows graded by `hardening --replay` from the live
#: recording), by their hardening-1 row ids
KEPT = [("L002", "E13"), ("L003", "E20"), ("L005", "E03"), ("L006", "E07")]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def A():
    return _load("litkb_acceptance", "qc/instruments/litkb_acceptance.py")


@pytest.fixture(scope="module")
def LR():
    return _load("litkb_ladder_run", "qc/instruments/litkb_ladder_run.py")


def _h1():
    return json.loads(H1.read_text(encoding="utf-8"))


def _h1_run():
    with open(H1_RUN, encoding="utf-8", newline="") as fh:
        return {r["row_id"]: r for r in csv.DictReader(fh)}


def _register():
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def _reset(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


class _ConstructedLedger:
    """CONSTRUCTED ledger over REAL row definitions: `held` is the set of work ids that hold an active file; no
    reference resolves to a work the row did not already name."""

    def __init__(self, held=()):
        self.held = set(held)

    def work_of(self, scheme, ref):
        return None

    def has_file(self, wid):
        return wid in self.held


def test_the_fixtures_are_hardening_1_as_frozen_and_as_run(A):
    """The copies are what the provenance says: the manifest's own self-hash holds, and both content hashes match."""
    src = _h1()
    assert src["manifest_sha256"] == A._canonical_sha(src) == H1_MANIFEST_SHA
    assert A._register_sha256(H1) == H1_CONTENT_SHA and A._register_sha256(H1_RUN) == H1_RUN_CONTENT_SHA
    assert len(src["rows"]) == 198 and len(_h1_run()) == 195


# ── rows_from_source: the source's rows, each mode re-read ─────────────────────────────────────────

def test_rows_from_source_copies_every_real_row_and_rereads_only_its_mode(A):
    """The 198 REAL rows through `rows_from_source`, against a CONSTRUCTED ledger in which the work L002's hunt
    bound in hardening-1 (Pfitzmann_2022, fresh-bound) now holds a file and the 32 measured works still do: L002
    alone flips hunt -> measure; every row's other fields are the source's, in the source's order."""
    src = _h1()
    by = {r["id"]: r for r in src["rows"]}
    held = {r["work_id"] for r in src["rows"] if r["mode"] == "measure"} | {by["L002"]["work_id"]}
    rows, changes = A.rows_from_source(src, _ConstructedLedger(held))
    assert [r["id"] for r in rows] == [r["id"] for r in src["rows"]]
    for new, old in zip(rows, src["rows"]):
        assert list(new) == list(old), (new["id"], list(new))
        assert {k: v for k, v in new.items() if k != "mode"} == {k: v for k, v in old.items() if k != "mode"}
    assert [(c["id"], c["from"], c["to"], c["work_id"], c["why"]) for c in changes] == [
        ("L002", "hunt", "measure", by["L002"]["work_id"], "the work holds an active file now")]
    assert sum(r["mode"] == "measure" for r in rows) == 33
    assert src["rows"][1]["mode"] == "hunt"            # the source itself is never touched


def test_the_kept_takes_are_exactly_the_register_rows_graded_from_the_recording(A):
    """REAL rows, REAL register, REAL run CSV: the rows whose hardening-1 take the register was converted from (E03
    E07 E13 E20 — `ladder` rows with no cassette of their own) are kept, each with its take verbatim. E21 (L001,
    measured) and E06 (L004, the dropped URL row) are register rows too, graded some other way: not kept."""
    src = _h1()
    run = _h1_run()
    kept, missing = A.kept_register_takes(src["rows"], _register(), run)
    assert [(k["id"], k["register_row"]) for k in kept] == KEPT, kept
    assert missing == []
    for k in kept:
        assert k["take"] == run[k["id"]]
    takes = {k["register_row"]: (k["take"]["mode"], k["take"]["state"], k["take"]["reason"]) for k in kept}
    assert takes == {"E13": ("hunt", "bound-unextracted", "fresh-bound"), "E20": ("hunt", "blocked", "challenge"),
                     "E03": ("hunt", "held", "duplicate-held"), "E07": ("hunt", "blocked", "challenge")}
    # a register row the source run never took is named, and is an ordinary row of the new run
    no_take = {k: v for k, v in run.items() if k != "L006"}
    kept2, missing2 = A.kept_register_takes(src["rows"], _register(), no_take)
    assert [k["id"] for k in kept2] == ["L002", "L003", "L005"]
    assert [(m["id"], m["register_row"]) for m in missing2] == [("L006", "E07")]
    # a recording-graded register row whose reference NO source row holds is named too (id null), never silently
    # absent (auditor-FX-R round 1, N5): L006's REAL row left out of a CONSTRUCTED subset of the rows
    e07 = next(r for r in _register()["rows"] if r["id"] == "E07")
    kept3, missing3 = A.kept_register_takes([r for r in src["rows"] if r["id"] != "L006"], _register(), run)
    assert [k["id"] for k in kept3] == ["L002", "L003", "L005"]
    assert missing3 == [{"id": None, "ref": e07["ref"], "register_row": "E07",
                         "why": "no row of the source manifest holds this reference: not a row of this run"}]


# ── the freeze itself, on a worker database ────────────────────────────────────────────────────────

def _freeze(A, capsys, *argv):
    code = A.main(["hardening", "--freeze", *argv])
    got = capsys.readouterr()
    return code, got.out, got.err


def _ws(conn):
    from litkb.extract import queue_fire as F

    ws = F.open_ws(conn)
    return ws, conn.execute("SELECT slug FROM litkb.workstreams WHERE id = %s", (ws,)).fetchone()[0]


def _common(A, slug, tmp_path, out, *, repo=None, cassette=None, date="2026-09-24"):
    from litkb.db import connect as c

    repo = repo or tmp_path / "repo"
    Path(repo).mkdir(parents=True, exist_ok=True)
    return ["--workstream", slug, "--db", c.DB_TEST, "--role", "litkb_test", "--repo", str(repo), "--out", str(out),
            "--date", date, "--no-admin-read", "--cassette", str(cassette or tmp_path / "cas2" / "index.jsonl"),
            "--bodies", str(tmp_path / "bodies")]


@pg_only
def test_a_rows_from_freeze_reproduces_hardening_1s_198_rows_exactly(A, tmp_path, litkb_pg_base, capsys):
    """THE REAL SOURCE. `hardening --freeze --rows-from` hardening-1 on a worker database: the new manifest's rows are
    hardening-1's 198 row definitions, field for field and in order; each mode re-read HERE (no live work exists on a
    worker database, so the 32 measured rows flip to hunt and are named); `rows_from` pins the source (its self-hash,
    its content hash, its run CSV); on a worker database no work holds a file, so every register row is a HUNT row
    and S4.5 decision D57 re-runs all four register takes (`redo_takes`, each with its source take as history) and
    keeps none; the source's index is pinned for a kept take's replay (`take_cassette`); everything else is a normal
    freeze's (a new frozen_at, the shadow tier OFF, a new cassette with no recording yet, the same promised report)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    try:
        ws, slug = _ws(conn)
        out = tmp_path / "hardening-2.json"
        code, printed, err = _freeze(A, capsys, "--rows-from", str(H1), "--rows-from-run-csv", str(H1_RUN),
                                     "--run-label", "hardening-2", *_common(A, slug, tmp_path, out))
        assert code == 0, err
        m = A.load_hardening_manifest(out)
        src = _h1()
        assert [r["id"] for r in m["rows"]] == [r["id"] for r in src["rows"]] and len(m["rows"]) == 198
        for new, old in zip(m["rows"], src["rows"]):
            assert list(new) == list(old), new["id"]
            assert {k: v for k, v in new.items() if k != "mode"} == {k: v for k, v in old.items() if k != "mode"}
        assert all(r["mode"] == "hunt" for r in m["rows"])
        rf = m["rows_from"]
        measured = [r["id"] for r in src["rows"] if r["mode"] == "measure"]
        assert len(measured) == 32
        assert [(c["id"], c["from"], c["to"], c["why"]) for c in rf["mode_changes"]] == [
            (i, "measure", "hunt", "the work holds no active file now") for i in measured]
        assert (rf["manifest_sha256"], rf["file_sha256"]) == (H1_MANIFEST_SHA, H1_CONTENT_SHA)
        assert rf["run_csv"] == {"path": str(H1_RUN), "sha256": H1_RUN_CONTENT_SHA}
        assert (rf["frozen_at"], rf["db_name"], rf["db_oid"], rf["same_database"]) == (
            src["frozen_at"], "litkb", 30778, False)
        assert rf["cassette_index"] == src["cassette_index"]["path"]
        assert rf["recording_report"] == src["recording_report"]
        run = _h1_run()
        assert rf["kept_takes"] == [] and rf["kept_missing"] == []
        assert [(k["id"], k["register_row"]) for k in rf["redo_takes"]] == KEPT
        assert all(k["take"] == run[k["id"]] and "D57" in k["why"] for k in rf["redo_takes"])
        h1_index = Path(src["repo"]) / src["cassette_index"]["path"]
        assert rf["take_cassette"]["path"] == str(h1_index)
        assert rf["take_cassette"]["bodies"] == src["cassette_index"]["bodies"]
        # the rows' provenance is the source's: the selectors that chose them, and the rows none could hunt
        assert (m["selectors"], m["unhuntable"]) == (src["selectors"], src["unhuntable"])
        # everything else is a normal freeze's, made NOW
        assert m["frozen_at"] > src["frozen_at"] and m["workstream_id"] == str(ws)
        assert m["shadow_tier"]["enabled"] is False and m["cassette_index"]["sha256"] is None
        assert m["report_path"] == src["report_path"] == "Reports/LITKB_LADDER1_2026-09-24.md"
        assert m["run_label"] == "hardening-2"
        assert m["run_csv"] == "_derived/hardening/LITKB_LADDER1_2026-09-24_hardening-2_run.csv"
        assert m["recording_report"] == "_derived/hardening/LITKB_LADDER1_2026-09-24_hardening-2_recording.json"
        for piece in ("rows=198", "hunt=198", "mode_changes=32", "measure->hunt=32", "kept=none",
                      "redo=L002,L003,L005,L006",
                      f"source_sha={H1_MANIFEST_SHA[:12]}", "same_database=False"):
            assert piece in printed, (piece, printed)
    finally:
        _reset(conn)


def _jsonb(obj):
    from psycopg.types.json import Jsonb

    return Jsonb(obj)


def _seed(conn, ws, *, doi=None, arxiv=None, with_file=False):
    """A CONSTRUCTED main work (written as facts, qc/instruments/litkb_hardening_b1.py's `seed_work` way), with one
    identifier and, when asked, one active file. -> work id."""
    tag = uuid.uuid4().hex[:8]
    wid = conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, 'fxr-seed', "
        "'fxr-seed')", (_jsonb({"key": f"Constructed_2020_fxr-{tag}"}),
                        _jsonb({"type": "article", "title": f"CONSTRUCTED FX-R work {tag}", "authors": [],
                                "year": 2020}), ws)).fetchone()[0]
    scheme, value = ("doi", doi) if doi else ("arxiv", arxiv)
    conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, NULL, %s, 'fxr-seed', "
        "'fxr-seed')", (_jsonb({"scheme": scheme}),
                        _jsonb({"work_id": str(wid), "value": value, "verified_by": "crossref" if doi else "arxiv",
                                "asserted_by": "caller", "evidence": {}, "status": "active"}), ws))
    if with_file:
        conn.execute(
            "SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, 'fxr-seed', "
            "'fxr-seed')", (_jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
                            _jsonb({"work_id": str(wid), "status": "active", "rel_path": f"Validation/fxr-{tag}.pdf",
                                    "bytes": 1024, "pages": 1}), ws))
    return str(wid)


def _write_constructed_run(path, takes=()):
    """A CONSTRUCTED source run CSV under hardening-1's REAL header; `takes` = the rows it holds (a REAL take copied,
    or none)."""
    with open(H1_RUN, encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for t in takes:
            w.writerow({k: t.get(k, "") for k in header})


def _constructed_source(A, path, rows, *, repo, takes=(), **extra):
    """A CONSTRUCTED hardening manifest (the fields a rows-from freeze reads), self-hashed like a real one, and its
    CONSTRUCTED run CSV at its own `run_csv` under its `repo` (holding `takes`) — a rows-from freeze refuses a source
    whose run CSV does not exist (auditor-FX-R round 1, F1)."""
    m = {"kind": A.HARDENING_MANIFEST_KIND, "frozen_at": "2026-09-24T00:00:00+00:00", "repo": str(repo),
         "db_name": "constructed", "db_oid": 0, "workstream_slug": "constructed-src",
         "run_csv": "_derived/hardening/LITKB_LADDER1_2026-09-24_run.csv",
         "recording_report": "_derived/hardening/LITKB_LADDER1_2026-09-24_recording.json",
         "replay_csv": "_derived/hardening/LITKB_LADDER1_2026-09-24_replay.csv",
         "replay_report": "_derived/hardening/LITKB_LADDER1_2026-09-24_replay.json",
         "cassette_index": {"path": "_derived/hardening/cassettes/ladder-1/index.jsonl"},
         "gated": [{"name": n, "bound": b} for n, b in A.HARDENING_GATED],
         "selectors": {"constructed": len(rows)}, "unhuntable": [], "rows": rows, **extra}
    m["manifest_sha256"] = A._canonical_sha(m)
    Path(path).write_text(json.dumps(m, indent=1), encoding="utf-8")
    _write_constructed_run(Path(repo) / m["run_csv"], takes)
    return m


def _row(i, ref, scheme, mode, wid):
    return {"id": f"L{i:03d}", "ref": ref, "ref_scheme": scheme, "mode": mode, "source": ["constructed"],
            "why": "constructed: CONSTRUCTED row", "work_id": wid, "key": None}


@pg_only
def test_a_rows_from_freeze_flips_each_mode_by_the_file_state_now(A, LR, tmp_path, litkb_pg_base, capsys,
                                                                  monkeypatch):
    """CONSTRUCTED works on a worker database, a CONSTRUCTED source frozen before their files: a work that holds a
    file now is `measure` whatever the source said; one that does not is `hunt`; a row the source froze with NO work
    (an arXiv reference, as hardening-1's L010-L017 were) is resolved by its reference now — and the run driver's
    measure path resolves it to the SAME work (`work_id_of_row`), and hands THAT work to the measure hook (a
    CONSTRUCTED stub hook; auditor-FX-R round 1, N2: before, the arXiv id was looked up as a DOI and the row was
    skipped/work-not-in-main)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    try:
        ws, slug = _ws(conn)
        wa = _seed(conn, ws, doi="10.5555/fxr-constructed-a", with_file=True)    # bound since: hunt -> measure
        wb = _seed(conn, ws, doi="10.5555/fxr-constructed-b")                    # file gone:    measure -> hunt
        wc = _seed(conn, ws, doi="10.5555/fxr-constructed-c", with_file=True)    # still held:   measure
        wd = _seed(conn, ws, doi="10.5555/fxr-constructed-d")                    # still bare:   hunt
        we = _seed(conn, ws, arxiv="2299.00001", with_file=True)                 # no work at the source's freeze
        rows = [_row(1, "10.5555/fxr-constructed-a", "doi", "hunt", wa),
                _row(2, "10.5555/fxr-constructed-b", "doi", "measure", wb),
                _row(3, "10.5555/fxr-constructed-c", "doi", "measure", wc),
                _row(4, "10.5555/fxr-constructed-d", "doi", "hunt", wd),
                _row(5, "2299.00001", "arxiv", "hunt", None),
                _row(6, "10.5555/fxr-constructed-none", "doi", "hunt", None)]
        src_path = tmp_path / "constructed-source.json"
        _constructed_source(A, src_path, rows, repo=tmp_path / "src-repo")
        out = tmp_path / "rerun.json"
        code, printed, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "h2",
                                     *_common(A, slug, tmp_path, out))
        assert code == 0, err
        m = A.load_hardening_manifest(out)
        assert [r["mode"] for r in m["rows"]] == ["measure", "hunt", "measure", "hunt", "measure", "hunt"]
        assert [(c["id"], c["from"], c["to"], c["work_id"], c["why"]) for c in m["rows_from"]["mode_changes"]] == [
            ("L001", "hunt", "measure", wa, "the work holds an active file now"),
            ("L002", "measure", "hunt", wb, "the work holds no active file now"),
            ("L005", "hunt", "measure", we, "the work holds an active file now")]
        assert m["rows"][4]["work_id"] is None                      # the definition is the source's
        assert m["rows_from"]["kept_takes"] == [] and "hunt->measure=2" in printed and "measure->hunt=1" in printed
        # the driver finds the work the freeze found, by the same rule
        assert LR.work_id_of_row(conn, m["rows"][4]) == we
        assert LR.work_id_of_row(conn, m["rows"][5]) is None
        assert LR.work_id_of_row(conn, m["rows"][0]) == wa
        # ... and the driver's measure path measures the null-work arXiv row on that work (CONSTRUCTED stub hook)
        from litkb import workstream
        from litkb.db import connect as c

        handed = []

        def constructed_hook(_conn, _ws, _token, work, **_kw):
            handed.append(str(work["work_id"]))
            return {"outcome": "measured", "attempts": []}
        monkeypatch.setattr(LR, "measure_hook", lambda: constructed_hook)
        monkeypatch.setattr(workstream, "load", lambda _d: (ws, "constructed-token"))
        ctx = {"db": c.DB_TEST, "writer_role": "litkb_test", "worktree": str(tmp_path), "agent": "t",
               "session": "t", "store": object()}
        assert m["rows"][4]["mode"] == "measure" and m["rows"][4]["ref_scheme"] == "arxiv"
        assert LR._default_measure(m["rows"][4], ctx)[:2] == ("measured", "measured") and handed == [we]
        assert LR._default_measure(m["rows"][0], ctx)[0] == "measured" and handed == [we, wa]
    finally:
        _reset(conn)


def _probe_csvs(repo):
    """CONSTRUCTED probe CSVs (10.5555 DOIs) under <repo>/phase4/qc/ (qc/test_litkb_hardening.py's shape)."""
    q = repo / "phase4" / "qc"
    q.mkdir(parents=True)
    (q / "litkb_acq_probe_no_oa_copy.csv").write_text(
        "doi,unpaywall_url\n10.5555/constructed-noa-1,\n10.5555/constructed-noa-2,https://doi.org/10.5555/constructed-noa-2\n",
        encoding="utf-8")
    (q / "litkb_acq_probe_head.csv").write_text(
        "doi,resolver,verdict,status\n10.5555/constructed-free-1,unpaywall,FREE-PDF,200\n", encoding="utf-8")


@pg_only
def test_a_normal_freeze_is_unchanged(A, tmp_path, litkb_pg_base, capsys):
    """Without `--rows-from` the freeze is what it was: the rows are exactly `select_run_rows`' over the same
    snapshot, the manifest carries neither `rows_from` nor `run_label`, its fields are EXACTLY the ones the pre-FX-R
    code froze into hardening-1 (the REAL manifest's key set) plus `prefetch_policy` (S4.5 decision D53: the freeze
    records the pre-fetch policy — Common Crawl ON, no line switched off) and `pdftotext` (S4.5 decision D59: the
    binary the binder will run from this PATH, its `-v` line and the encoding asked), and its run files carry no
    label."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    try:
        ws, slug = _ws(conn)
        repo = tmp_path / "repo"
        _probe_csvs(repo)
        out = tmp_path / "normal.json"
        code, printed, err = _freeze(A, capsys, *_common(A, slug, tmp_path, out, repo=repo, date="2026-09-23"))
        assert code == 0, err
        m = A.load_hardening_manifest(out)
        assert set(m) == set(_h1()) | {"prefetch_policy", "pdftotext"}, sorted(set(m) ^ set(_h1()))
        from litkb.admit import binding
        assert m["pdftotext"] == binding.pdftotext_version(), m["pdftotext"]         # S4.5 decision D59
        assert m["pdftotext"]["encoding"] == "UTF-8" and "pdftotext=" in printed, printed
        pol = m["prefetch_policy"]
        assert (pol["lines_off"], pol["routes_off"]) == ([], []) and "D53" in pol["ruling"], pol
        assert "rows_from" not in m and "run_label" not in m and "rows_from=" not in printed
        ctx = {"ledger": A._LedgerReader(conn), "register": _register(), "ruled": [],
               "probe": lambda base: A._csv_rows(repo / "phase4" / "qc" / base)}
        rows, unhuntable, counts = A.select_run_rows(ctx)
        assert (m["rows"], m["unhuntable"], m["selectors"]) == (rows, unhuntable, counts)
        assert m["run_csv"] == "_derived/hardening/LITKB_LADDER1_2026-09-23_run.csv"
        assert m["replay_report"] == "_derived/hardening/LITKB_LADDER1_2026-09-23_replay.json"
    finally:
        _reset(conn)


@pg_only
def test_a_rows_from_source_edited_after_its_freeze_is_refused(A, tmp_path, litkb_pg_base, capsys):
    """A source whose content no longer matches its own manifest_sha256 (one real row's reference changed), or that is
    not a hardening manifest, is refused before anything is read or written. A source frozen under another gated list
    is ACCEPTED: only its row definitions are read."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    try:
        _ws_id, slug = _ws(conn)
        edited = _h1()
        edited["rows"][4]["ref"] = "10.5555/constructed-edit"        # CONSTRUCTED edit of a REAL copy
        p = tmp_path / "edited.json"
        p.write_text(json.dumps(edited), encoding="utf-8")
        out = tmp_path / "never.json"
        with pytest.raises(SystemExit, match="edited after its freeze"):
            A.main(["hardening", "--freeze", "--rows-from", str(p), "--run-label", "h2",
                    *_common(A, slug, tmp_path, out)])
        assert not out.exists()
        other = {"kind": "litkb-edges", "rows": _h1()["rows"]}                # CONSTRUCTED: another kind, self-hashed
        other["manifest_sha256"] = A._canonical_sha(other)
        q = tmp_path / "edges-kind.json"
        q.write_text(json.dumps(other), encoding="utf-8")
        with pytest.raises(SystemExit, match="is not a 'litkb-hardening' manifest"):
            A.main(["hardening", "--freeze", "--rows-from", str(q), "--run-label", "h2",
                    *_common(A, slug, tmp_path, out)])
        assert not out.exists()
        regated = _h1()
        regated["gated"] = regated["gated"][:-1]                              # CONSTRUCTED: another gated list
        regated["manifest_sha256"] = A._canonical_sha(regated)
        r = tmp_path / "regated.json"
        r.write_text(json.dumps(regated), encoding="utf-8")
        assert len(A.load_rows_source(r)["rows"]) == 198
    finally:
        _reset(conn)


@pg_only
def test_a_rows_from_freeze_never_writes_over_its_source(A, tmp_path, litkb_pg_base, capsys):
    """A re-run that would share its source's run CSV (read back as DONE: nothing re-run), its recording report, its
    replay files, its cassette index or the source manifest itself is refused, and writes nothing; the same freeze
    with a label, a new index and a new out path succeeds. CONSTRUCTED source under a CONSTRUCTED repo, named the way
    hardening-1 was."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    try:
        _ws_id, slug = _ws(conn)
        repo = tmp_path / "repo"
        repo.mkdir()
        src_path = repo / "hardening-1-constructed.json"
        _constructed_source(A, src_path, [_row(1, "10.5555/fxr-constructed-x", "doi", "hunt", None)], repo=repo)
        src_bytes = src_path.read_bytes()
        out = tmp_path / "h2.json"
        own_index = repo / "_derived" / "hardening" / "cassettes" / "ladder-1" / "index.jsonl"
        new_index = tmp_path / "cas2" / "index.jsonl"

        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path),
                                *_common(A, slug, tmp_path, out, repo=repo, cassette=new_index))
        assert code == 2 and not out.exists(), err
        for f in ("run_csv", "recording_report", "replay_csv", "replay_report"):
            assert f"{f} (" in err, (f, err)
        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "hardening-2",
                                *_common(A, slug, tmp_path, out, repo=repo, cassette=own_index))
        assert code == 2 and not out.exists() and "cassette_index (" in err and "run_csv (" not in err, err
        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "hardening-2",
                                *_common(A, slug, tmp_path, src_path, repo=repo, cassette=new_index))
        assert code == 2 and "out (" in err, err
        assert src_path.read_bytes() == src_bytes
        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "hardening-2",
                                *_common(A, slug, tmp_path, out, repo=repo, cassette=new_index))
        assert code == 0 and out.exists(), err
        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "../escape",
                                *_common(A, slug, tmp_path, tmp_path / "h3.json", repo=repo, cassette=new_index))
        assert code == 2 and "path-safe" in err
    finally:
        _reset(conn)


@pg_only
def test_a_rows_from_freeze_reads_its_source_run_csv_under_the_source_repo_and_refuses_a_missing_one(
        A, tmp_path, litkb_pg_base, capsys):
    """auditor-FX-R round 1, F1. With no `--rows-from-run-csv`, the source's takes are read from its OWN `run_csv`
    under its OWN `repo` (never the working directory): a CONSTRUCTED source holding hardening-1's REAL L005 row
    (E03) beside a CONSTRUCTED row, whose CONSTRUCTED run CSV holds L005's REAL take, finds that take (a hunt row on
    the worker database, so S4.5 decision D57 re-runs it: `redo_takes`); the three
    recording-graded register rows no source row holds are named in `kept_missing` with a null id. The same source
    with its run CSV gone — or a named copy that does not exist — is REFUSED, exit 2, nothing written: read as "no
    takes", every kept register row would become an ordinary row of the new run and be hunted again (D49)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    try:
        _ws_id, slug = _ws(conn)
        src_repo = tmp_path / "src-repo"
        l005 = next(r for r in _h1()["rows"] if r["id"] == "L005")
        take = _h1_run()["L005"]
        # a run CSV name no working directory holds (the default must resolve under the source's repo)
        run_rel = "_derived/hardening/LITKB_LADDER1_2099-01-01_constructed_run.csv"
        src_path = tmp_path / "constructed-source.json"
        _constructed_source(A, src_path, [l005, _row(9, "10.5555/fxr-constructed-y", "doi", "hunt", None)],
                            repo=src_repo, takes=[take], run_csv=run_rel)
        default = src_repo / run_rel
        out = tmp_path / "h2.json"
        code, printed, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "h2",
                                     *_common(A, slug, tmp_path, out))
        assert code == 0, err
        rf = A.load_hardening_manifest(out)["rows_from"]
        assert rf["run_csv"] == {"path": str(default), "sha256": A._register_sha256(default)}
        assert rf["kept_takes"] == []
        assert [(k["id"], k["register_row"], k["take"]) for k in rf["redo_takes"]] == [("L005", "E03", take)]
        assert sorted((k["id"], k["register_row"]) for k in rf["kept_missing"]) == [
            (None, "E07"), (None, "E13"), (None, "E20")]
        assert "kept=none redo=L005 kept_missing=3" in printed, printed

        default.unlink()
        refused = tmp_path / "h2-refused.json"
        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "h2",
                                *_common(A, slug, tmp_path, refused))
        assert code == 2 and not refused.exists(), err
        assert "does not exist" in err and str(default) in err, err
        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path), "--rows-from-run-csv",
                                str(tmp_path / "no-such-run.csv"), "--run-label", "h2",
                                *_common(A, slug, tmp_path, refused))
        assert code == 2 and not refused.exists() and "no-such-run.csv" in err, err
        # auditor-FX-R r2 N1 (S4.5 decision D58, integrator-w4): the refusal's boundary is a FILE — a directory at the
        # run-CSV path (CONSTRUCTED) is refused too, never read as "no takes"
        a_dir = tmp_path / "a-dir.csv"
        a_dir.mkdir()
        code, _o, err = _freeze(A, capsys, "--rows-from", str(src_path), "--rows-from-run-csv", str(a_dir),
                                "--run-label", "h2", *_common(A, slug, tmp_path, refused))
        assert code == 2 and not refused.exists() and "a-dir.csv" in err, err
    finally:
        _reset(conn)


# ── S4.5 decision D57: only a take whose row is `measure` now is kept; a kept take replays from its own index ──────

@pg_only
def test_d57_keeps_only_the_register_take_whose_work_holds_a_file_now(A, LR, tmp_path, litkb_pg_base, capsys):
    """S4.5 decision D57 (integrator-w4). hardening-1's REAL rows L002 (E13, whose hunt fresh-bound its work) and L005
    (E03, duplicate-held: its work holds no file) in a CONSTRUCTED source, each re-pointed at a CONSTRUCTED work on the
    worker database — E13's with an active file (as live holds it since hardening-1), E03's without — and their REAL
    hardening-1 takes in the source run CSV. The freeze KEEPS L002 (a measure row now: a re-run cannot reproduce a
    fresh-bound take) and puts L005 in `redo_takes` (a hunt row the fixed code reproduces), printing
    `kept=L002 redo=L005`. The run driver then CARRIES L002 (take_from = the source's sha) and RE-RUNS L005 without
    being told to (`--rerun-kept` is for a kept take only)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    try:
        ws, slug = _ws(conn)
        src_rows = {r["id"]: r for r in _h1()["rows"]}
        l002, l005 = dict(src_rows["L002"]), dict(src_rows["L005"])
        l002["work_id"] = _seed(conn, ws, doi=l002["ref"], with_file=True)
        l005["work_id"] = _seed(conn, ws, doi=l005["ref"])
        run = _h1_run()
        src_path = tmp_path / "constructed-source.json"
        src = _constructed_source(A, src_path, [l002, l005], repo=tmp_path / "src-repo",
                                  takes=[run["L002"], run["L005"]])
        out = tmp_path / "h2.json"
        code, printed, err = _freeze(A, capsys, "--rows-from", str(src_path), "--run-label", "h2",
                                     *_common(A, slug, tmp_path, out))
        assert code == 0, err
        m = A.load_hardening_manifest(out)
        assert [r["mode"] for r in m["rows"]] == ["measure", "hunt"]
        rf = m["rows_from"]
        assert [(k["id"], k["register_row"], k["take"]) for k in rf["kept_takes"]] == [("L002", "E13", run["L002"])]
        assert [(k["id"], k["register_row"], k["take"]) for k in rf["redo_takes"]] == [("L005", "E03", run["L005"])]
        assert rf["redo_takes"][0]["why"] == A.D57_REDO_WHY
        assert sorted(k["register_row"] for k in rf["kept_missing"]) == ["E07", "E20"]
        assert "kept=L002 redo=L005 kept_missing=2" in printed, printed
        assert rf["take_cassette"]["path"] == str(tmp_path / "src-repo" / src["cassette_index"]["path"])

        calls = []

        def hunt(**kw):
            calls.append(kw["ref"])
            return {"state": "held", "reason": "not-acquired", "message": "CONSTRUCTED hunt"}
        ran, _resumed, rows = LR.run_rows(m, tmp_path / "h2_run.csv", db="unused", worktree=tmp_path, agent="t",
                                          session="t", hunt=hunt, attempts_counter=lambda: 0, record=False)
        got = {r["row_id"]: r for r in rows}
        assert (ran, calls) == (1, [l005["ref"]])
        assert got["L002"]["take_from"] == src["manifest_sha256"] and got["L002"]["state"] == "bound-unextracted"
        assert (got["L005"]["state"], got["L005"]["take_from"]) == ("held", "")
    finally:
        _reset(conn)


def test_d57_split_keeps_a_measure_row_and_redoes_a_hunt_row(A):
    """The rule alone on hardening-1's REAL rows and REAL kept takes: with every row a hunt row (a worker database),
    all four register takes are redone; with L002 alone a measure row (live since hardening-1 bound E13's work), L002
    is kept and L003 L005 L006 are redone — D57's own list (E13 kept; E03 E07 E20 re-run)."""
    src = _h1()
    run = _h1_run()
    rows, _c = A.rows_from_source(src, _ConstructedLedger())
    kept, _missing = A.kept_register_takes(rows, _register(), run)
    keep, redo = A.split_kept_by_mode(kept, rows)
    assert keep == [] and [k["id"] for k in redo] == ["L002", "L003", "L005", "L006"]
    by = {r["id"]: r for r in src["rows"]}
    rows2, _c2 = A.rows_from_source(src, _ConstructedLedger({by["L002"]["work_id"]}))
    keep2, redo2 = A.split_kept_by_mode(A.kept_register_takes(rows2, _register(), run)[0], rows2)
    assert [(k["id"], k["register_row"]) for k in keep2] == [("L002", "E13")]
    assert [(k["id"], k["register_row"]) for k in redo2] == [("L003", "E20"), ("L005", "E03"), ("L006", "E07")]
    assert all(k["why"] == A.D57_REDO_WHY and k["take"] == run[k["id"]] for k in redo2)


def _e13_h2_manifest(A, LR, tmp_path, *, take_from):
    """A CONSTRUCTED hardening-2-shaped manifest around the REAL E13: its register holds the register's REAL E13 row
    alone, its own recorded index does NOT exist (hardening-2 never re-ran E13), its run CSV holds hardening-1's REAL
    L002 take carried with `take_from`, and `rows_from.take_cassette` pins hardening-1's REAL recorded index (read-only,
    resolved under hardening-1's repo exactly as the freeze resolves it)."""
    reg = _register()
    e13 = next(r for r in reg["rows"] if r["id"] == "E13")
    tmp_path.mkdir(parents=True, exist_ok=True)
    reg_path = tmp_path / "register-e13.json"
    reg_path.write_text(json.dumps(dict(reg, rows=[e13])), encoding="utf-8")
    m = {"kind": A.HARDENING_MANIFEST_KIND, "repo": str(tmp_path), "register": {"path": str(reg_path)},
         "cassette_index": {"path": str(tmp_path / "own-cas" / "index.jsonl"), "bodies": str(tmp_path / "own-bodies")},
         "run_csv": "h2_run.csv", "replay_csv": "h2_replay.csv", "replay_report": "h2_replay.json",
         "rows_from": {"manifest_sha256": H1_MANIFEST_SHA, "take_cassette": A._source_take_cassette(_h1())}}
    row = LR.carried_row({"take": _h1_run()["L002"]}, m)
    row["take_from"] = take_from
    with open(tmp_path / "h2_run.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LR.RUN_CSV_COLUMNS)
        w.writeheader()
        w.writerow(row)
    return m


@pg_only
def test_d57_a_kept_take_replays_against_the_index_its_take_was_recorded_in_e13(A, LR, tmp_path, litkb_pg_base):
    """S4.5 decision D57 on the REAL E13 and its RECORDED hardening-1 entries (the ladder-1 index and body store,
    untracked READ-ONLY evidence on this machine — skipped, named, where they are absent). `hardening --replay` of a
    hardening-2-shaped manifest whose own index never recorded E13: the run CSV's `take_from` (hardening-1's sha)
    sends E13 to hardening-1's index, and it replays its recorded pair `bound-unextracted/fresh-bound` with no miss;
    the summary names the index per row (`take_indexes`). The same manifest with the take made HERE (`take_from`
    empty) replays E13 from its own index — none exists — and the row is the named no-cassette traceback; a
    `take_from` naming a manifest this one was not frozen from is REFUSED before anything is replayed."""
    from litkb.db import connect as c

    tc = A._source_take_cassette(_h1())
    if tc["sha256"] is None or not Path(tc["bodies"] or "").is_dir():
        pytest.skip(f"hardening-1's recorded index / body store is not on this machine: {tc}")
    _psycopg, conn, _ran = litkb_pg_base
    try:
        m = _e13_h2_manifest(A, LR, tmp_path / "kept", take_from=H1_MANIFEST_SHA)
        s = A.hardening_replay(m, db=c.DB_TEST, conn=conn)
        (row,) = s["rows"]
        assert (row["row_id"], row["observed_state"], row["observed_reason"]) == (
            "E13", "bound-unextracted", "fresh-bound"), row
        assert str(row["cassette_misses"]) == "0" and row["traceback"] == "0", row
        assert [(t["row"], t["run_row"], t["index"], t["from_manifest_sha256"]) for t in s["take_indexes"]] == [
            ("E13", "L002", tc["path"], H1_MANIFEST_SHA)]
        assert s["take_indexes"][0]["index_sha256"] == tc["sha256"]
        assert s["stale"]["misses"] == [] and s["network_calls"] == 0, s["stale"]

        own = _e13_h2_manifest(A, LR, tmp_path / "own", take_from="")
        s2 = A.hardening_replay(own, db=c.DB_TEST, conn=conn)
        (row2,) = s2["rows"]
        assert row2["traceback"] == "1" and "no cassette" in row2["message"] and s2["take_indexes"] == [], row2

        other = _e13_h2_manifest(A, LR, tmp_path / "other", take_from="0" * 64)
        with pytest.raises(SystemExit, match="pins no index"):
            A.hardening_replay(other, db=c.DB_TEST, conn=conn)
    finally:
        _reset(conn)


def test_d57_a_kept_take_whose_pinned_index_changed_since_the_freeze_is_refused(A, LR, tmp_path):
    """S4.5 decision D61 (auditor-cand4 N1): `take_cassettes` replays a kept take only against the source index the
    freeze pinned, byte for byte. Around the REAL E13 register row and hardening-1's REAL L002 take (carried with
    hardening-1's `take_from`), the pinned index is a CONSTRUCTED one in tmp (so the test needs no recording on this
    machine): pinned sha = its bytes -> E13 is handed that index; the same file edited after the freeze (one byte
    appended) -> REFUSED before anything is replayed; a pin with no sha -> REFUSED."""
    from litkb import cassette as CAS

    m = _e13_h2_manifest(A, LR, tmp_path, take_from=H1_MANIFEST_SHA)
    reg = json.loads((tmp_path / "register-e13.json").read_text(encoding="utf-8"))
    idx = tmp_path / "constructed-take-index" / "index.jsonl"
    idx.parent.mkdir()
    idx.write_bytes(json.dumps({"kind": CAS.INDEX_KIND}).encode("utf-8") + b"\n")
    m["rows_from"]["take_cassette"] = {"path": str(idx), "sha256": CAS.index_sha256(idx),
                                       "bodies": str(tmp_path / "constructed-bodies")}
    got = A.take_cassettes(m, reg, m["repo"])
    assert list(got) == ["E13"] and got["E13"]["index"] == idx and got["E13"]["run_row"] == "L002", got
    with open(idx, "ab") as fh:
        fh.write(b"\n")
    with pytest.raises(SystemExit, match="is not the one the freeze pinned"):
        A.take_cassettes(m, reg, m["repo"])
    m["rows_from"]["take_cassette"]["sha256"] = None
    with pytest.raises(SystemExit, match="is not the one the freeze pinned"):
        A.take_cassettes(m, reg, m["repo"])


# ── the run driver ─────────────────────────────────────────────────────────────────────────────────

def _rerun_manifest(A, tmp_path, n=8):
    """The REAL first `n` rows of hardening-1 as a rows-from manifest would hold them (a CONSTRUCTED ledger in which no
    work holds a file: every row `hunt`), with the REAL kept takes."""
    src = _h1()
    rows, _changes = A.rows_from_source(src, _ConstructedLedger())
    kept, _missing = A.kept_register_takes(rows, _register(), _h1_run())
    return {"repo": str(tmp_path), "workstream_id": None, "shadow_tier": {"enabled": False},
            "cassette_index": {"path": str(tmp_path / "cas" / "index.jsonl"), "bodies": str(tmp_path / "bodies")},
            "recording_report": "_derived/hardening/constructed_h2_recording.json",
            "rows": rows[:n], "rows_from": {"manifest_sha256": H1_MANIFEST_SHA, "kept_takes": kept,
                                            "cassette_index": src["cassette_index"]["path"],
                                            "recording_report": src["recording_report"]}}


def test_the_driver_carries_kept_takes_and_reruns_only_a_named_one(A, LR, tmp_path):
    """hardening-1's REAL rows L001-L008 under a rows-from manifest, `--rerun-kept L005` (E03, whose outcome the dedupe
    fix changes — D49). Pass 1 hunts every row but the three kept takes NOT named (L002 E13, L003 E20, L006 E07), which
    are carried verbatim from the hardening-1 run CSV with `take_from` = hardening-1's sha. Pass 2 (resumed, E03 no
    longer named) keeps E03's NEW take — the carried duplicate-held never overwrites it. Pass 3: `--redo L002` alone
    never re-runs a kept take."""
    m = _rerun_manifest(A, tmp_path)
    run = _h1_run()
    calls = []

    def hunt(**kw):
        calls.append(kw["ref"])
        return {"state": "held", "reason": "not-acquired", "message": "CONSTRUCTED hunt"}
    out = tmp_path / "h2_run.csv"
    ran, resumed, rows = LR.run_rows(m, out, db="unused", worktree=tmp_path, agent="t", session="t", hunt=hunt,
                                     attempts_counter=lambda: 0, record=False, rerun_kept=["L005"])
    by_id = {r["id"]: r for r in m["rows"]}
    assert calls == [by_id[i]["ref"] for i in ("L001", "L004", "L005", "L007", "L008")], calls
    assert (ran, resumed) == (5, 0)
    got = {r["row_id"]: r for r in rows}
    for rid, _reg in KEPT:
        if rid == "L005":
            continue
        want = {k: run[rid].get(k, "") for k in LR.RUN_CSV_COLUMNS}
        want["take_from"] = H1_MANIFEST_SHA
        assert got[rid] == want, rid
    assert (got["L005"]["state"], got["L005"]["reason"], got["L005"]["take_from"]) == ("held", "not-acquired", "")
    with open(out, encoding="utf-8", newline="") as fh:
        on_disk = list(csv.DictReader(fh))
    assert tuple(on_disk[0]) == LR.RUN_CSV_COLUMNS and [r["row_id"] for r in on_disk] == [r["id"] for r in m["rows"]]

    ran2, resumed2, rows2 = LR.run_rows(m, out, db="unused", worktree=tmp_path, agent="t", session="t", hunt=hunt,
                                        attempts_counter=lambda: 0, record=False)
    got2 = {r["row_id"]: r for r in rows2}
    assert (ran2, len(calls)) == (0, 5) and resumed2 == 5
    assert (got2["L005"]["state"], got2["L005"]["reason"], got2["L005"]["take_from"]) == ("held", "not-acquired", "")
    assert got2["L002"]["take_from"] == H1_MANIFEST_SHA

    LR.run_rows(m, out, db="unused", worktree=tmp_path, agent="t", session="t", hunt=hunt,
                attempts_counter=lambda: 0, record=False, redo=["L002"])
    assert len(calls) == 5


def test_a_kept_row_named_outside_only_keeps_its_take_and_one_named_late_is_rerun(A, LR, tmp_path):
    """auditor-FX-R round 1, N3 and AUD1, on hardening-1's REAL rows L001-L008 and REAL kept takes.
    (a) `--only L001 --rerun-kept L005`: E03 is named but not in this pass, so its SOURCE take stays in the CSV
    (carried) — it never drops out of the one CSV the counters read.
    (b) the operator forgets `--rerun-kept` on pass 1 (E03 carried) and names it on pass 2: pass 2 runs E03 under
    this manifest and its new take replaces the carried one — a carried take is never mistaken for this manifest's
    own and resumed."""
    m = _rerun_manifest(A, tmp_path)
    run = _h1_run()
    by_id = {r["id"]: r for r in m["rows"]}
    calls = []

    def hunt(**kw):
        calls.append(kw["ref"])
        return {"state": "held", "reason": "not-acquired", "message": "CONSTRUCTED hunt"}

    def carried(rid):
        want = {k: run[rid].get(k, "") for k in LR.RUN_CSV_COLUMNS}
        want["take_from"] = H1_MANIFEST_SHA
        return want
    # (a)
    out_a = tmp_path / "h2_only_run.csv"
    ran, _resumed, rows = LR.run_rows(m, out_a, db="unused", worktree=tmp_path, agent="t", session="t", hunt=hunt,
                                      attempts_counter=lambda: 0, record=False, only=["L001"], rerun_kept=["L005"])
    got = {r["row_id"]: r for r in rows}
    assert (ran, calls) == (1, [by_id["L001"]["ref"]])
    assert sorted(got) == ["L001", "L002", "L003", "L005", "L006"]
    assert got["L005"] == carried("L005")
    # (b)
    calls.clear()
    out_b = tmp_path / "h2_late_run.csv"
    LR.run_rows(m, out_b, db="unused", worktree=tmp_path, agent="t", session="t", hunt=hunt,
                attempts_counter=lambda: 0, record=False)
    assert by_id["L005"]["ref"] not in calls
    ran2, _resumed2, rows2 = LR.run_rows(m, out_b, db="unused", worktree=tmp_path, agent="t", session="t", hunt=hunt,
                                         attempts_counter=lambda: 0, record=False, rerun_kept=["L005"])
    got2 = {r["row_id"]: r for r in rows2}
    assert ran2 == 1 and calls[-1] == by_id["L005"]["ref"]
    assert (got2["L005"]["state"], got2["L005"]["reason"], got2["L005"]["take_from"]) == ("held", "not-acquired", "")
    assert got2["L002"] == carried("L002")


def test_the_recording_report_names_the_carried_and_the_rerun_takes(A, LR, HA_mod, tmp_path, monkeypatch):
    """A RECORD pass of a rows-from manifest writes `kept_takes` into its recording report: which kept rows the CSV
    carries from the source run and which it re-ran here, and where the carried rows' recordings live (the source's
    index and recording report). A manifest that is not rows-from gets no such key. Every report records the
    pass's `pdftotext` (S4.5 decision D59)."""
    from litkb import cassette as C

    for k in (C.ENV_MODE, C.ENV_INDEX, C.ENV_BODIES, C.ENV_ROW):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(C, "_env_cache", {})
    m = _rerun_manifest(A, tmp_path, n=6)
    try:
        LR.run_rows(m, tmp_path / "h2_run.csv", db="unused", worktree=tmp_path, agent="t", session="t",
                    hunt=lambda **kw: {"state": "held", "reason": "not-acquired"}, attempts_counter=lambda: 0,
                    record=True, rerun_kept=["L005"])
    finally:
        for k in (C.ENV_MODE, C.ENV_INDEX, C.ENV_BODIES, C.ENV_ROW):
            os.environ.pop(k, None)
    rep = json.loads((tmp_path / "_derived" / "hardening" / "constructed_h2_recording.json").read_text(encoding="utf-8"))
    src = _h1()
    assert rep["kept_takes"] == {"from_manifest_sha256": H1_MANIFEST_SHA,
                                 "from_cassette_index": src["cassette_index"]["path"],
                                 "from_recording_report": src["recording_report"],
                                 "carried": ["L002", "L003", "L006"], "rerun": ["L005"]}
    assert rep["recording_sha256"] == HA_mod.summary_sha(rep, "recording_sha256")
    from litkb.admit import binding
    assert rep["pdftotext"] == binding.pdftotext_version(), rep["pdftotext"]         # S4.5 decision D59
    plain = dict(m)
    plain.pop("rows_from")
    plain["recording_report"] = "_derived/hardening/constructed_plain_recording.json"
    LR.write_recording_report(plain, tmp_path, None, rows_run=0, shadow=None)
    rep2 = json.loads((tmp_path / "_derived" / "hardening" / "constructed_plain_recording.json").read_text(
        encoding="utf-8"))
    assert "kept_takes" not in rep2


@pytest.fixture(scope="module")
def HA_mod():
    return _load("litkb_hardening_a", "qc/instruments/litkb_hardening_a.py")


def _constructed_file_manifest(A, tmp_path, rows_from=True):
    """A CONSTRUCTED manifest file (no rows) around ONE REAL take — hardening-1's L005 (E03) as a kept take when
    `rows_from` — for the driver's `--rerun-kept` refusal."""
    m = {"kind": A.HARDENING_MANIFEST_KIND, "frozen_at": "2026-09-24T00:00:00+00:00", "repo": str(tmp_path),
         "db": "unused", "run_csv": "run.csv", "rows": [], "shadow_tier": {"enabled": False},
         "gated": [{"name": n, "bound": b} for n, b in A.HARDENING_GATED]}
    if rows_from:
        m["rows_from"] = {"manifest_sha256": H1_MANIFEST_SHA,
                          "kept_takes": [{"id": "L005", "ref": "10.1007/978-3-030-32248-9_57", "register_row": "E03",
                                          "take": _h1_run()["L005"]}]}
    m["manifest_sha256"] = A._canonical_sha(m)
    p = tmp_path / ("rf.json" if rows_from else "plain.json")
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def test_rerun_kept_names_only_a_kept_register_row(A, LR, tmp_path, monkeypatch, capsys):
    """`--rerun-kept` of a row the manifest does not keep — L001 (E21, not kept), or anything on a manifest that was not
    frozen --rows-from — is refused before anything runs (a typo would re-run nothing and say nothing); a kept row
    is passed to the pass."""
    seen, real_run_rows = [], LR.run_rows
    monkeypatch.setattr(LR, "run_rows", lambda *a, **kw: seen.append(kw.get("rerun_kept")) or (0, 0, []))
    rf, plain = _constructed_file_manifest(A, tmp_path), _constructed_file_manifest(A, tmp_path, rows_from=False)
    assert LR.main(["--manifest", str(rf), "--rerun-kept", "L001", "--no-record"]) == 2
    assert "not a kept register take" in capsys.readouterr().err
    assert LR.main(["--manifest", str(plain), "--rerun-kept", "L005", "--no-record"]) == 2
    assert "not frozen --rows-from" in capsys.readouterr().err
    assert seen == []
    assert LR.main(["--manifest", str(rf), "--rerun-kept", "L005", "--no-record"]) == 0
    assert seen == [["L005"]]
    with pytest.raises(LR.UnknownKeptRow):          # the pass itself refuses too, whoever calls it
        real_run_rows(json.loads(rf.read_text(encoding="utf-8")), tmp_path / "x.csv", db="unused", worktree=tmp_path,
                      agent="t", session="t", hunt=lambda **kw: {}, attempts_counter=lambda: 0, record=False,
                      rerun_kept=["L006"])
    assert not (tmp_path / "x.csv").exists()

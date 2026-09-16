"""litkb stage 6 ingest — the parked references into the database (migration 0020).

`Reports/LITKB_P4_MERGE_2026-09-15.md` ("Migration: none written") measured stage 6's output sitting
as JSONL with no loader and nowhere to put two of the three kinds of row. 0020 built the home;
`litkb.extract.references_ingest` is the loader, and this file is what holds it to its rules.

Everything here runs against ``litkb_test`` (or the worker copy ``LITKB_TEST_DB`` names) through the
P1 harness class, and reaches the ingest role the way every other role test does — log in as the
test database's owner and ``SET ROLE``. Nothing touches `litkb`, and nothing reaches the network:
the artifacts are dicts built in this file, except for the one test at the bottom, which loads the
REAL parked corpus and is skipped when it is not on the machine.

The database is reset once per pytest SESSION, not once per test, so every fixture takes a unique
stem (:func:`uniq`) and every count is scoped to the run under test (:func:`db_counts`). A bare
``count(*)`` here would measure the tests above it.

  rule (module header / 0020)                                  test
  one transaction per paper; a kill leaves nothing             test_a_killed_paper_leaves_nothing
  idempotent: a second load writes nothing                     test_a_second_load_writes_nothing
  ambiguous is a state, not a synonym for candidate            test_ambiguous_survives_the_load
  a mention is one row per <ref> ELEMENT, boxes collected      test_a_mention_is_one_row_per_element_with_every_box
  a mention naming no reference is counted, never guessed      test_a_mention_with_no_reference_is_skipped_and_counted
  an edge to a work litkb does not hold is counted, not made   test_an_edge_to_an_unheld_work_is_skipped_and_counted
  a stem with no held file is refused, never substituted       test_a_stem_with_no_held_file_is_refused
  only litkb_ingest writes the citation rows                   test_only_the_ingest_role_may_write_the_citation_rows
  the stage-6 run never becomes the file's current run         test_the_stage6_run_never_becomes_the_files_current_run
  a dry run writes nothing at all                              test_a_dry_run_writes_nothing

Mutation rows P6-I1 and P6-I2 (`qc/instruments/litkb_p6_mutations.py`) weaken the stem refusal and
the per-element grouping; each must turn this file red.
"""
import json
import pathlib
import sys
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))  # noqa: E402

from litkb.extract import references_ingest as RI  # noqa: E402

from test_litkb_p1 import _PG  # noqa: E402 - the P1 harness class, not its fixture

pg_only = pytest.mark.requires_litkb_pg


@pytest.fixture(scope="session")
def _s6(litkb_pg_base):
    """Our own session fixture over the shared base, as the P2 and stage-5 suites do: importing
    P1's `pg` fixture instead would shadow it in every test signature here (ruff F811)."""
    psycopg, conn, ran = litkb_pg_base
    yield _PG(psycopg, conn, ran)


@pytest.fixture
def pg(_s6):
    yield _s6
    while _s6.opened:
        _s6.opened.pop().close()


# ── fixtures: works, files, identifiers ─────────────────────────────────────────────────

def _work(pg, ws, key):
    return pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, "
        "%s, NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"key": key}),
         pg.Jsonb({"type": "article", "title": key, "authors": []}), ws))[0]


def _file(pg, ws, work_id, stem):
    return pg.one(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, "
        "%s, NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         pg.Jsonb({"work_id": str(work_id), "rel_path": f"Validation/{stem}.pdf",
                   "status": "active"}), ws))[0]


def _doi(pg, ws, work_id, doi):
    return pg.one(
        "SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, "
        "NULL, %s, 'setup', 'setup')",
        (pg.Jsonb({"scheme": "doi"}),
         pg.Jsonb({"work_id": str(work_id), "value": doi, "status": "active"}), ws))[0]


def held(pg, stem, *, key=None, with_file=True, doi=None, ws=None):
    """A work (and normally its file) for `stem`. The KEY defaults to the convention's truncated
    form — four slug words — so the file-stem route is the one that matches, exactly as on `litkb`
    (17 of 18 citing stems there resolve by file stem and only 10 are also a works.key)."""
    ws = ws or pg.ws()
    work_id = _work(pg, ws, key or _truncated_key(stem))
    file_id = _file(pg, ws, work_id, stem) if with_file else None
    if doi:
        _doi(pg, ws, work_id, doi)
    return {"ws": ws, "work_id": work_id, "file_id": file_id, "stem": stem}


def _truncated_key(stem):
    author, year, slug = (stem.split("_", 2) + ["", ""])[:3]
    return f"{author}_{year}_" + "-".join(slug.split("-")[:4])


def uniq(author, year, slug):
    """A stem no other test in this session can collide with — the database is reset once per
    pytest session, not once per test.

    The token is the slug's FIRST word, and it has to be: `works.key` is CHECKed against
    ``^[A-Za-z]+_[0-9]{4}[ab]?_[a-z0-9]+(-[a-z0-9]+){1,4}$`` (0001, the filing convention), so the
    surname may not carry digits — and :func:`_truncated_key` keeps the first four slug words, so a
    token any further along would be cut off and two tests would race for one key.
    """
    return f"{author}_{year}_{uuid.uuid4().hex[:8]}-{slug}"


# ── what the database holds FOR THIS TEST ───────────────────────────────────────────────

def db_counts(conn, stems):
    """The rows these citing stems' stage-6 runs hold, and nobody else's.

    A stage-6 run records its stem on `metrics`, which is what makes this scopeable at all: the
    suite shares one database across the whole session, and a bare ``count(*)`` would grow with
    every test above.
    """
    return dict(zip(("runs", "references", "citation_mentions", "citation_edges", "candidates"),
                    conn.execute(
                        "WITH r AS (SELECT id FROM litkb.extraction_runs "
                        "            WHERE stage = '6-references' AND metrics->>'stem' = ANY(%(s)s)), "
                        '     ref AS (SELECT id FROM litkb."references" WHERE run_id IN (SELECT id FROM r)) '
                        "SELECT (SELECT count(*) FROM r), (SELECT count(*) FROM ref),"
                        "       (SELECT count(*) FROM litkb.citation_mentions "
                        "         WHERE reference_id IN (SELECT id FROM ref)),"
                        "       (SELECT count(*) FROM litkb.citation_edges "
                        "         WHERE run_id IN (SELECT id FROM r)),"
                        "       (SELECT count(*) FROM litkb.candidates "
                        "         WHERE citing_reference_id IN (SELECT id FROM ref))",
                        {"s": list(stems)}).fetchone()))


NOTHING = {"runs": 0, "references": 0, "citation_mentions": 0, "citation_edges": 0, "candidates": 0}


# ── fixtures: the stage-6 artifacts ─────────────────────────────────────────────────────

def ref(stem, ref_key, index, *, title="A cited study", resolution="unresolved", doi=None,
        mention_count=0, raw=None):
    """One `references.jsonl` row, in the shape `references.process_tei` writes."""
    return {"citing_work_key": stem, "ref_key": ref_key, "index": index, "title": title,
            "authors": [{"family": "Cited", "given": "A"}], "first_author": "Cited",
            "year": "2009", "journal": "J", "volume": "1", "issue": "2", "pages": "3-4",
            "publisher": "", "doi": doi or "", "doi_norm": doi or "", "arxiv": "",
            "raw": raw or f"Cited, A., 2009. {title}. J 1 (2), 3-4.", "raw_source": "grobid-raw",
            "boxes": [{"page": 9, "bbox": [1.0, 2.0, 3.0, 4.0]}], "confidence": None,
            "has_monogr": True, "stage": "6-references", "pipeline_version": "litkb-p6-1",
            "mention_count": mention_count, "resolution": resolution,
            "resolved_doi": doi if resolution == "resolved" else None,
            "resolution_detail": {"state": resolution, "doi": doi, "source": "crossref",
                                  "ratio": 1.0, "reason": f"via=crossref ({resolution})",
                                  "candidates": [], "registry_title": title, "archive_ok": True}}


def mention(stem, target, *, page=2, box_index=0, marker="(Cited, 2009)", sentence="A sentence."):
    return {"citing_work_key": stem, "target": target, "marker": marker, "page": page,
            "bbox": [10.0 + box_index, 20.0, 30.0, 40.0], "box_index": box_index,
            "sentence": sentence, "sentence_page": page, "resolved_target": bool(target),
            "reference_title": ""}


def edge(stem, cited_stem, ref_key, doi, mention_count=0):
    return {"citing_work_key": stem, "cited_work_key": cited_stem, "cited_doi": doi,
            "ref_key": ref_key, "mention_count": mention_count, "in_corpus": True}


def candidate(r):
    """The candidate `references.candidate_row` writes for a reference that made no edge."""
    return {"source": "citation", "citing_work_key": r["citing_work_key"],
            "citing_reference": r["raw"][:2000],
            "raw_record": {"parsed": {k: r[k] for k in ("authors", "year", "title", "journal",
                                                        "volume", "pages", "doi", "arxiv")},
                           "resolution": r["resolution_detail"]},
            "title": r["title"], "authors": r["authors"], "year": r["year"],
            "doi": r["resolved_doi"], "state": "new", "reason": r["resolution_detail"]["reason"],
            "admitted_work_id": None}


def artifacts(root, references, mentions=(), edges=(), log=()):
    """Write a p6 artifact directory. The candidates are DERIVED the way stage 6 derives them —
    one per reference that produced no edge, in order — so the loader's positional pairing is
    tested against the shape it will actually meet."""
    d = pathlib.Path(root) / "p6"
    d.mkdir(parents=True, exist_ok=True)
    edged = {(e["citing_work_key"], e["ref_key"]) for e in edges}
    cands = [candidate(r) for r in references if (r["citing_work_key"], r["ref_key"]) not in edged]
    for name, rows in (("references", references), ("citation_mentions", mentions),
                       ("edges", edges), ("candidates", cands), ("extraction_log", log)):
        (d / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8", newline="\n")
    return str(d)


def small(pg, tmp_path, *, citing=None, cited=None, with_file=True):
    """Two held papers and a corpus: 4 references (resolved-and-held, resolved-not-held,
    ambiguous, unresolved), one two-box mention, one untargeted mention, one edge.

    The DOIs are per-call too: a normalised DOI is unique among the ACTIVE identifiers (§4.6 check
    2), so a fixed one would make the second test in a session collide with the first."""
    citing = citing or uniq("Citing", 2015, "a-multilayer-markov-random-field-model")
    cited = cited or uniq("Cited", 2009, "change-detection-in-optical-aerial-images")
    doi_a = f"10.3390/rs{uuid.uuid4().hex[:10]}"       # resolved, and litkb holds no such work
    doi_b = f"10.1109/tgrs.{uuid.uuid4().hex[:10]}"    # resolved, and it IS the cited work's
    ws = pg.ws()
    # with_file=False mirrors `litkb`'s one refusing stem: Chrisman_1982 is a works.key with no
    # held file, so the key must be the stem itself and the stem must satisfy works.key's CHECK.
    a = held(pg, citing, with_file=with_file, ws=ws,
             key=None if with_file else _truncated_key(citing))
    b = held(pg, cited, doi=doi_b, ws=ws)
    refs = [ref(citing, "b0", 0, title="Change detection in optical aerial images",
                resolution="resolved", doi=doi_b, mention_count=1),
            ref(citing, "b1", 1, title="Similarity measures of remotely sensed images",
                resolution="resolved", doi=doi_a, mention_count=1),
            ref(citing, "b2", 2, title="A sibling edition of something", resolution="ambiguous"),
            ref(citing, "b3", 3, title="Nothing the registries know", resolution="unresolved")]
    mentions = [mention(citing, "b0"),
                mention(citing, "b1", page=3),
                mention(citing, "b1", page=3, box_index=1),   # the same element, wrapped
                mention(citing, "", page=4, marker="[7]")]     # GROBID linked it to nothing
    edges = [edge(citing, cited, "b0", doi_b, mention_count=1)]
    root = artifacts(tmp_path, refs, mentions, edges,
                     log=[{"stem": citing, "status": "ok", "bytes": 1234, "seconds": 1.5}])
    return {"ws": ws, "a": a, "b": b, "root": root, "refs": refs, "mentions": mentions,
            "citing": citing, "cited": cited, "doi_a": doi_a, "doi_b": doi_b}


def _load(pg, root, **kw):
    conn = pg.session("litkb_ingest")
    return RI.load(conn, root, **kw), conn


def _run_id(conn, stem):
    row = conn.execute("SELECT id FROM litkb.extraction_runs WHERE stage = '6-references' "
                       "AND metrics->>'stem' = %s", (stem,)).fetchone()
    return row[0] if row else None


# ── the load ────────────────────────────────────────────────────────────────────────────

@pg_only
def test_a_small_corpus_loads_with_every_row_in_its_place(pg, tmp_path):
    w = small(pg, tmp_path)
    report, conn = _load(pg, w["root"])
    assert report["loaded"] == [w["citing"]] and report["refused"] == []
    assert report["routes"] == {"file-stem": 1}, "the key is the truncated form; the file stem matched"
    assert report["counts"] == {"references": 4, "citation_mentions": 2, "citation_edges": 1,
                                "candidates": 3}, report
    assert report["skipped"]["mentions_without_reference"] == 1

    run = pg.one("SELECT id, stage, tool, tool_version, pipeline_version, status, metrics, "
                 "artifact_path, host FROM litkb.extraction_runs WHERE file_id = %s",
                 (w["a"]["file_id"],))
    assert run[1:6] == ("6-references", "litkb-references", "litkb-p6-1", "litkb-p6-1", "ok")
    assert run[6]["stem"] == w["citing"] and run[6]["tei"]["bytes"] == 1234
    assert run[6]["written"] == {"references": 4, "citation_mentions": 2, "citation_edges": 1,
                                 "candidates": 3}
    assert run[8] == "local"

    rows = {r[0]: r for r in conn.execute(
        'SELECT ref_key, ref_index, resolution, resolved_doi, resolved_work_id, citing_work_id, '
        'mention_count, confidence, raw_text, parsed, resolution_detail, pipeline_version, block_id '
        'FROM litkb."references" WHERE run_id = %s', (run[0],))}
    assert sorted(rows) == ["b0", "b1", "b2", "b3"]
    assert [rows[k][1] for k in sorted(rows)] == [0, 1, 2, 3]
    # b0's DOI is a held work's active DOI, so the reference names the work it resolved to
    assert rows["b0"][4] == w["b"]["work_id"] and rows["b0"][3] == w["doi_b"]
    # b1 resolved to a DOI litkb does not hold: recorded, resolved, and pointing at no work
    assert rows["b1"][2] == "resolved" and rows["b1"][3] == w["doi_a"] and rows["b1"][4] is None
    assert all(r[5] == w["a"]["work_id"] for r in rows.values()), "every reference is the citing work's"
    assert rows["b0"][8].startswith("Cited, A., 2009.")
    assert rows["b0"][9]["first_author"] == "Cited" and rows["b0"][9]["doi_norm"] == w["doi_b"]
    assert "citing_work_key" not in rows["b0"][9], "the parse is the parse, not the run's labelling"
    assert rows["b2"][10]["reason"].endswith("(ambiguous)") and rows["b2"][11] == "litkb-p6-1"
    assert rows["b0"][7] is None, "GROBID publishes no per-reference confidence; it is not invented"
    assert all(r[12] is None for r in rows.values()), "stage 6 reads TEI, not stage 5's blocks"


@pg_only
def test_a_second_load_writes_nothing(pg, tmp_path):
    w = small(pg, tmp_path)
    first, conn = _load(pg, w["root"])
    before = db_counts(conn, [w["citing"]])
    again = RI.load(conn, w["root"])
    assert again["loaded"] == [] and again["already"] == [w["citing"]]
    assert again["counts"] == {"references": 0, "citation_mentions": 0, "citation_edges": 0,
                               "candidates": 0}, again
    after = db_counts(conn, [w["citing"]])
    assert after == before, f"a second load changed the rows: {before} -> {after}"
    assert first["counts"]["references"] == 4
    assert before == {"runs": 1, "references": 4, "citation_mentions": 2, "citation_edges": 1,
                      "candidates": 3}


@pg_only
def test_ambiguous_survives_the_load(pg, tmp_path):
    """Stage 6 reports two distinct accepted DOIs as resolved-to-NOTHING. 0002's CHECK refused the
    state and 0020 widened it; mapping it onto `candidate` would erase the difference between one
    plausible match and two we will not choose."""
    w = small(pg, tmp_path)
    report, conn = _load(pg, w["root"])
    assert report["counts"]["references"] == 4
    got = conn.execute('SELECT resolution, resolved_doi, resolved_work_id FROM litkb."references" '
                       "WHERE run_id = %s AND ref_key = 'b2'", (_run_id(conn, w["citing"]),)).fetchone()
    assert got == ("ambiguous", None, None)


@pg_only
def test_a_mention_is_one_row_per_element_with_every_box(pg, tmp_path):
    """b1 is cited once, by a marker that wraps across a line and therefore carries TWO boxes.
    One mention row, two boxes — the geometry kept, the count right."""
    w = small(pg, tmp_path)
    _report, conn = _load(pg, w["root"])
    rows = conn.execute(
        "SELECT r.ref_key, m.mention_index, m.page, m.boxes, m.marker, m.sentence, m.block_id, "
        "       m.char_start, m.char_end "
        'FROM litkb.citation_mentions m JOIN litkb."references" r ON r.id = m.reference_id '
        "WHERE r.run_id = %s ORDER BY r.ref_key, m.mention_index",
        (_run_id(conn, w["citing"]),)).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("b0", 0), ("b1", 0)], rows
    b1 = rows[1]
    assert b1[2] == 3 and len(b1[3]) == 2, f"a two-box element must be one row with two boxes: {b1}"
    assert [b["bbox"][0] for b in b1[3]] == [10.0, 11.0]
    assert b1[4] == "(Cited, 2009)" and b1[5] == "A sentence."
    assert b1[6] is None and b1[7] is None and b1[8] is None, (
        "stage 6 reads TEI, not stage 5's blocks: the mention stands on its page geometry")
    assert conn.execute('SELECT mention_count FROM litkb."references" '
                        "WHERE run_id = %s AND ref_key = 'b1'",
                        (_run_id(conn, w["citing"]),)).fetchone()[0] == 1


@pg_only
def test_a_mention_with_no_reference_is_skipped_and_counted(pg, tmp_path):
    """GROBID emits <ref type="bibr"> elements it could not link to any biblStruct (201 of 1,182 on
    the real corpus). There is nothing to attach them to, and guessing from the marker is exactly
    the fabrication stage 6 refuses."""
    w = small(pg, tmp_path)
    report, conn = _load(pg, w["root"])
    assert report["skipped"]["mentions_without_reference"] == 1
    assert db_counts(conn, [w["citing"]])["citation_mentions"] == 2
    assert conn.execute(
        "SELECT count(*) FROM litkb.citation_mentions m "
        'JOIN litkb."references" r ON r.id = m.reference_id WHERE r.run_id = %s AND m.marker = %s',
        (_run_id(conn, w["citing"]), "[7]")).fetchone()[0] == 0


@pg_only
def test_the_citation_edge_names_both_works_and_its_reference(pg, tmp_path):
    w = small(pg, tmp_path)
    _report, conn = _load(pg, w["root"])
    got = conn.execute(
        "SELECT e.citing_work_id, e.cited_work_id, e.cited_doi, e.mention_count, r.ref_key "
        'FROM litkb.citation_edges e JOIN litkb."references" r ON r.id = e.reference_id '
        "WHERE e.run_id = %s", (_run_id(conn, w["citing"]),)).fetchall()
    assert got == [(w["a"]["work_id"], w["b"]["work_id"], w["doi_b"], 1, "b0")]


@pg_only
def test_an_edge_to_an_unheld_work_is_skipped_and_counted(pg, tmp_path):
    """The edges were made against the corpus INDEX (the manifest and bibliography CSVs), not
    against litkb. A cited work litkb does not hold has no node to point at."""
    w = small(pg, tmp_path)
    absent_doi = f"10.1000/absent.{uuid.uuid4().hex[:8]}"
    extra = ref(w["citing"], "b4", 4, title="A work nobody here holds", resolution="resolved",
                doi=absent_doi)
    root = artifacts(tmp_path / "unheld", w["refs"] + [extra], w["mentions"],
                     [edge(w["citing"], w["cited"], "b0", w["doi_b"], 1),
                      edge(w["citing"], uniq("Absent", 1999, "nobody-holds-this-work"), "b4",
                           absent_doi)])
    report, conn = _load(pg, root)
    assert report["skipped"]["edges_cited_work_not_held"] == 1
    assert report["counts"]["citation_edges"] == 1 and report["counts"]["references"] == 5
    assert db_counts(conn, [w["citing"]])["citation_edges"] == 1
    # the reference itself is still there, resolved, with no work to point at
    assert conn.execute('SELECT resolution, resolved_work_id FROM litkb."references" '
                        "WHERE run_id = %s AND ref_key = 'b4'",
                        (_run_id(conn, w["citing"]),)).fetchone() == ("resolved", None)


@pg_only
def test_the_candidates_are_the_references_that_made_no_edge(pg, tmp_path):
    w = small(pg, tmp_path)
    _report, conn = _load(pg, w["root"])
    rows = conn.execute(
        "SELECT r.ref_key, c.source, c.state, c.title, c.year, c.ids, c.source_detail, "
        "       c.admitted_work_id, c.workstream_id, c.raw_record "
        'FROM litkb.candidates c JOIN litkb."references" r ON r.id = c.citing_reference_id '
        "WHERE r.run_id = %s ORDER BY r.ref_key", (_run_id(conn, w["citing"]),)).fetchall()
    assert [r[0] for r in rows] == ["b1", "b2", "b3"], "b0 became an edge, so it is not a lead"
    assert all(r[1] == "citation" and r[2] == "new" for r in rows)
    assert rows[0][3] == "Similarity measures of remotely sensed images"
    assert rows[0][4] == 2009 and rows[0][5] == {"doi": w["doi_a"]}
    assert rows[0][6] == f"cited by {w['citing']} as b1"
    assert rows[0][9]["resolution"]["state"] == "resolved"
    assert rows[1][5] is None, "an ambiguous reference resolved to no DOI, so the lead carries none"
    assert all(r[7] is None and r[8] is None for r in rows), (
        "a citation candidate is a lead: never admitted here, and it carries no workstream")


@pg_only
def test_a_stem_with_no_held_file_is_refused(pg, tmp_path):
    """`"references".file_id` is NOT NULL, and the one thing a loader must never do to satisfy a
    NOT NULL is pick a file that is not the paper's. MEASURED on litkb: 1 of the 18 citing stems
    (Chrisman_1982) is a works.key with no held file."""
    stem = uniq("Chrisman", 1982, "theory-of-cartographic-error")
    ws = pg.ws()
    _work(pg, ws, stem)                    # the key exists; no file does
    other = held(pg, uniq("Other", 2001, "a-paper-that-is-held"), ws=ws)
    root = artifacts(tmp_path, [ref(stem, f"b{i}", i) for i in range(4)])
    report, conn = _load(pg, root)
    assert report["loaded"] == [] and report["papers"] == 1
    assert [r["stem"] for r in report["refused"]] == [stem]
    assert "holds no active file" in report["refused"][0]["reason"]
    assert report["refused"][0]["references"] == 4
    assert db_counts(conn, [stem]) == NOTHING
    assert conn.execute("SELECT count(*) FROM litkb.extraction_runs WHERE file_id = %s",
                        (other["file_id"],)).fetchone()[0] == 0, (
        "the refused paper was loaded under another work's file")


@pg_only
def test_a_stem_litkb_has_never_heard_of_is_refused(pg, tmp_path):
    ws = pg.ws()
    held(pg, uniq("Someone", 2001, "a-held-paper-about-things"), ws=ws)
    ghost = uniq("Ghost", 1999, "not-in-this-corpus-at-all")
    report, conn = _load(pg, artifacts(tmp_path, [ref(ghost, "b0", 0)]))
    assert [r["stem"] for r in report["refused"]] == [ghost]
    assert "no file with that stem and no work with that key" in report["refused"][0]["reason"]
    assert db_counts(conn, [ghost]) == NOTHING


@pg_only
def test_a_stem_that_is_only_a_works_key_resolves_by_that_key(pg, tmp_path):
    """The fallback leg: a paper whose stem IS the work's key resolves by key, and the route is
    recorded so a reader can tell which rule matched. The stem must satisfy works.key's own CHECK
    here — at most five slug words (0001) — which the unique token is the first of."""
    stem = uniq("Keyed", 2011, "stem-is-the-key")
    ws = pg.ws()
    work_id = _work(pg, ws, stem)
    _file(pg, ws, work_id, uniq("Keyed", 2011, "filed-under-another-stem"))
    report, _conn = _load(pg, artifacts(tmp_path, [ref(stem, "b0", 0)]))
    assert report["loaded"] == [stem] and report["routes"] == {"works.key": 1}


# ── the transaction, the pointer, the roles ─────────────────────────────────────────────

@pg_only
def test_a_killed_paper_leaves_nothing(pg, tmp_path):
    """The §14 P5 rule, on stage 6: a worker killed between the references and the mentions must
    leave NO run row, NO references and no half-built graph — so the resume writes one set of rows,
    not two."""
    w = small(pg, tmp_path)
    conn = pg.session("litkb_ingest")
    index, dois = RI.held_index(conn), RI.doi_index(conn)
    paper = RI.papers(RI.read_artifacts(w["root"]))[0]

    def die(_conn, _run):
        raise KeyboardInterrupt("killed between the references and the mentions")

    with pytest.raises(KeyboardInterrupt):
        RI.ingest_paper(conn, paper, index, dois, _after_references=die)
    assert db_counts(conn, [w["citing"]]) == NOTHING
    # control: the same paper then loads completely, and exactly once
    res = RI.ingest_paper(conn, paper, index, dois)
    assert res["inserted"] and res["references"] == 4 and res["citation_mentions"] == 2
    assert db_counts(conn, [w["citing"]]) == {"runs": 1, "references": 4, "citation_mentions": 2,
                                              "citation_edges": 1, "candidates": 3}


@pg_only
def test_a_half_written_paper_is_invisible_to_another_session(pg, tmp_path):
    """The other half of the same rule: while one session is mid-paper, another sees nothing."""
    w = small(pg, tmp_path)
    conn = pg.session("litkb_ingest")
    watcher = pg.session("litkb_ingest")
    index, dois = RI.held_index(conn), RI.doi_index(conn)
    paper = RI.papers(RI.read_artifacts(w["root"]))[0]
    seen = {}

    def look(_conn, run_id):
        seen["refs"] = watcher.execute(
            'SELECT count(*) FROM litkb."references" WHERE run_id = %s', (run_id,)).fetchone()[0]
        seen["scoped"] = db_counts(watcher, [w["citing"]])

    RI.ingest_paper(conn, paper, index, dois, _after_references=look)
    assert seen["refs"] == 0 and seen["scoped"] == NOTHING, (
        f"another session saw a half-written paper: {seen} — the rows are outside the transaction")


@pg_only
def test_the_stage6_run_never_becomes_the_files_current_run(pg, tmp_path):
    """A file's current run is the run whose BLOCKS are its text. A stage-6 run has none: making it
    current would point search, exports and evidence at a run with zero blocks. 0017's guard checks
    only that the run is ok and belongs to the file, so nothing but this stops it."""
    w = small(pg, tmp_path)
    _report, _conn = _load(pg, w["root"])
    assert pg.one("SELECT current_run_id FROM litkb.files WHERE id = %s",
                  (w["a"]["file_id"],))[0] is None
    assert pg.one("SELECT count(*) FROM litkb.file_current_run WHERE file_id = %s",
                  (w["a"]["file_id"],))[0] == 0


_CITATION_WRITERS = {
    "add_reference": "SELECT litkb.add_reference(%s::uuid, %s::uuid, NULL::uuid, 'b0', 0, 'raw', "
                     "'{}'::jsonb, NULL::uuid, NULL::uuid, NULL::text, 'unresolved', '{}'::jsonb, "
                     "NULL::real, 0, 'v')",
    "add_citation_mention": "SELECT litkb.add_citation_mention(%s::uuid, 0, NULL::uuid, NULL::int, "
                            "NULL::int, 1, '[]'::jsonb, 'm', 's')",
    "add_citation_edge": "SELECT litkb.add_citation_edge(%s::uuid, %s::uuid, %s::uuid, %s::uuid, "
                         "NULL::text, 0)",
    "add_citation_candidate": "SELECT litkb.add_citation_candidate(%s::uuid, 't', '[]'::jsonb, "
                              "2009, '{}'::jsonb, '{}'::jsonb, 'd')",
}


@pg_only
@pytest.mark.parametrize("fn", sorted(_CITATION_WRITERS))
@pytest.mark.parametrize("role", ["litkb_reader", "litkb_writer", "litkb_promoter"])
def test_only_the_ingest_role_may_write_the_citation_rows(pg, role, fn):
    """0020 grants EXECUTE on the four writers to litkb_ingest and revokes it from PUBLIC. Control:
    the ingest role REACHES each function — it is refused on its arguments, not on privilege."""
    q = _CITATION_WRITERS[fn]
    args = tuple(uuid.uuid4() for _ in range(q.count("%s")))
    agent = pg.session(role)
    with pytest.raises(pg.errors.InsufficientPrivilege):
        agent.execute(q, args)
    ingest = pg.session("litkb_ingest")
    with pytest.raises(pg.psycopg.DatabaseError) as ei:
        ingest.execute(q, args)
    assert not isinstance(ei.value, pg.errors.InsufficientPrivilege), ei.value


@pg_only
@pytest.mark.parametrize("table", ["references", "citation_mentions", "citation_edges"])
def test_no_agent_role_holds_a_direct_write_on_the_citation_tables(pg, table):
    """0020's privileges, as its own comment states them: the agent roles get SELECT and nothing
    else on all three; `citation_edges` is NEW, so it takes 0017's stricter shape and the ingest
    login has no direct INSERT on it either; `"references"` and `citation_mentions` keep the direct
    INSERT 0010 granted the ingest login, which 0020 deliberately does not retire."""
    for role in ("litkb_reader", "litkb_writer", "litkb_promoter"):
        for priv in ("INSERT", "UPDATE", "DELETE"):
            assert pg.one("SELECT has_table_privilege(%s, %s, %s)",
                          (role, f"litkb.{table}", priv))[0] is False, f"{role} holds {priv} on {table}"
        assert pg.one("SELECT has_table_privilege(%s, %s, 'SELECT')",
                      (role, f"litkb.{table}"))[0] is (role != "litkb_promoter" or table != "citation_edges")
    ingest_insert = pg.one("SELECT has_table_privilege('litkb_ingest', %s, 'INSERT')",
                           (f"litkb.{table}",))[0]
    assert ingest_insert is (table != "citation_edges"), (
        f"litkb_ingest's INSERT on {table} is not what 0020's privileges section says it is")
    for priv in ("UPDATE", "DELETE"):
        assert pg.one("SELECT has_table_privilege('litkb_ingest', %s, %s)",
                      (f"litkb.{table}", priv))[0] is False


@pg_only
def test_a_dry_run_writes_nothing(pg, tmp_path):
    w = small(pg, tmp_path)
    report, conn = _load(pg, w["root"], dry_run=True)
    assert report["dry_run"] and report["loaded"] == [w["citing"]]
    assert report["counts"] == {"references": 4, "citation_mentions": 2, "citation_edges": 1,
                                "candidates": 3}, report
    assert db_counts(conn, [w["citing"]]) == NOTHING
    # and the real load then agrees with what the dry run promised
    assert RI.load(conn, w["root"])["counts"] == report["counts"]


@pg_only
def test_only_the_named_stem_is_loaded(pg, tmp_path):
    w = small(pg, tmp_path)
    other = uniq("Second", 2018, "another-held-paper-entirely")
    held(pg, other, ws=w["ws"])
    root = artifacts(tmp_path / "two", w["refs"] + [ref(other, "b0", 0)], w["mentions"])
    report, conn = _load(pg, root, only=w["citing"])
    assert report["loaded"] == [w["citing"]] and report["papers"] == 1
    assert db_counts(conn, [other]) == NOTHING


# ── the artifact-consistency refusals (nothing is written on either) ────────────────────

@pg_only
def test_a_candidate_that_is_not_its_references_is_refused(pg, tmp_path):
    """The artifacts carry no ref_key on a candidate, so the pairing is positional — and checked.
    A pairing that is silently wrong would attach every lead to the wrong citation."""
    w = small(pg, tmp_path)
    d = pathlib.Path(w["root"])
    rows = [json.loads(x) for x in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[0], rows[1] = rows[1], rows[0]
    (d / "candidates.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    conn = pg.session("litkb_ingest")
    with pytest.raises(RI.ReferenceIngestError, match="positional pairing"):
        RI.load(conn, w["root"])
    assert db_counts(conn, [w["citing"]]) == NOTHING


@pg_only
def test_mentions_that_do_not_add_up_to_stage_sixs_count_are_refused(pg, tmp_path):
    """`mention_count` is stage 6's own count of ELEMENTS naming a reference. If what is written
    does not add up to it, the grouping is wrong and the database's citation counts would silently
    disagree with the artifact they came from."""
    w = small(pg, tmp_path)
    d = pathlib.Path(w["root"])
    rows = [json.loads(x) for x in (d / "references.jsonl").read_text(encoding="utf-8").splitlines()]
    for r in rows:
        if r["ref_key"] == "b1":
            r["mention_count"] = 2        # stage 6 counted two; the TEI holds one element
    (d / "references.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    conn = pg.session("litkb_ingest")
    with pytest.raises(RI.ReferenceIngestError, match="unlocatable"):
        RI.load(conn, w["root"])
    assert db_counts(conn, [w["citing"]]) == NOTHING


# ── the real parked corpus ──────────────────────────────────────────────────────────────

PARKED = pathlib.Path(RI.artifact_dir())
parked = pytest.mark.skipif(not (PARKED / "references.jsonl").exists(),
                            reason=f"stage 6's parked artifacts are not on this machine ({PARKED})")


@pg_only
@parked
def test_the_parked_corpus_loads_whole(pg):
    """The real 2026-09-15 run, into a throwaway database with a work and a file built for every
    stem it names. The expectations are COUNTED FROM THE ARTIFACTS rather than written down, so
    this measures the loader and not a number that rots the next time stage 6 runs."""
    art = RI.read_artifacts()
    bundles = RI.papers(art)
    ws = pg.ws()
    stems = {b["stem"] for b in bundles} | {e["cited_work_key"] for e in art["edges"]}
    for i, stem in enumerate(sorted(stems)):
        work_id = _work(pg, ws, f"{_truncated_key(stem)}-{i}")
        _file(pg, ws, work_id, stem)
    conn = pg.session("litkb_ingest")
    report = RI.load(conn, host="local")

    keys = {(b["stem"], r["ref_key"]) for b in bundles for r in b["references"]}
    elements = [(b["stem"], e) for b in bundles for e in RI.mention_elements(b["mentions"])]
    want = {"references": len(art["references"]),
            "citation_mentions": sum(1 for s, e in elements if (s, e["target"]) in keys),
            "citation_edges": len(art["edges"]),
            "candidates": len(art["candidates"])}
    assert report["refused"] == [], report["refused"]
    assert sorted(report["loaded"]) == sorted(b["stem"] for b in bundles)
    assert report["counts"] == want, report
    assert report["skipped"]["mentions_without_reference"] == len(elements) - want["citation_mentions"]
    # every mention row is one element, never one bounding box
    assert sum(len(e["boxes"]) for _s, e in elements) == len(art["citation_mentions"])
    got = db_counts(conn, [b["stem"] for b in bundles])
    assert {k: got[k] for k in want} == want, got
    assert got["runs"] == len(bundles)
    # and a second load adds nothing
    again = RI.load(conn)
    assert again["loaded"] == [] and set(again["counts"].values()) == {0}
    assert db_counts(conn, [b["stem"] for b in bundles]) == got

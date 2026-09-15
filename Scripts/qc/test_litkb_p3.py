"""litkb P3 "Migration + exports" — the kills and guards of the design's §14 P3 row.

Design: Scripts/LITERATURE_KB_DESIGN_2026-09-13.md §13 (migration), §10 (exports), §14 P3 row.
Decisions: Scripts/decisions.yaml `litkb-p0-foundation`, "P3 load (Kam, 2026-09-14)" — identity comes
from the registry record and the verified file; every disagreeing tracker/manifest field is kept as a
flagged discrepancy; no correction pass. Evidence: Reports/LITKB_P3_REPORT_2026-09-15.md.

  kill (§14 P3)                                                    test
  a planted DUPLICATE DOI row is rejected at load                  test_kill_a_planted_duplicate_doi_row_is_rejected_at_load
  the planted Averkov WRONG-DOI row is rejected at load            test_kill_the_planted_averkov_wrong_doi_row_is_rejected_at_load
  a planted row whose title disagrees produces a discrepancy       test_kill_a_disagreeing_title_produces_a_discrepancy_record
  loading twice admits nothing new                                 test_kill_loading_twice_admits_nothing_new

  guard                                                            test
  a disagreeing claim with NO file is HELD, never admitted         test_a_disagreeing_claim_with_no_file_is_held_not_admitted
  a disagreeing claim WITH a file admits on the binding            test_a_disagreeing_claim_with_a_file_admits_on_the_binding
  a manifest sha256 that is not the file on disk is flagged        test_a_manifest_sha256_that_is_not_the_file_on_disk_is_flagged
  the writer holds no direct write on discrepancies                test_the_writer_holds_no_direct_write_on_discrepancies
  record_discrepancy needs the workstream token                    test_record_discrepancy_needs_the_workstream_token
  Feeds tokens are parsed per the convention                       test_feeds_tokens_are_parsed_per_the_convention
  the export round-trips every loaded row                          test_the_export_round_trips_every_loaded_row

The real Validation files are read only. Registry answers come from qc/testdata/litkb_p2/crossref_kill_dois.json
and from synthetic records; nothing here touches the network.
"""
import csv
import hashlib
import json
import os
import urllib.parse
import uuid
from pathlib import Path

import pytest

import test_litkb_p2 as _p2mod
from test_litkb_p2 import CROSSREF, KILL, PREFIX_ROWS, _need_file, _nopace, paper_pdf

# the P1/P2 suite's session fixtures, reused so all three files share ONE reset of litkb_test
# (qc/conftest.py::litkb_pg_base: two modules holding the suite lock on their own connection deadlock).
# Bound by assignment, not by `from … import pg`, so a test's `pg` parameter is not a redefinition.
_p2 = _p2mod._p2
pg = _p2mod.pg

SCRIPTS = Path(__file__).resolve().parent.parent
VALIDATION = Path(os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture")) / "Validation"
pg_only = pytest.mark.requires_litkb_pg

TRACKER_COLUMNS = ["ID", "Author(s)", "Year", "Title", "Journal/Source", "Relevance (max 3 sentences)",
                   "Search Phase", "DOI/URL", "Status", "Evidence grade", "Feeds", "Duplicate of",
                   "File stem", "Bib line", "Read date", "Notes"]


# ── helpers ───────────────────────────────────────────────────────────────────────────────

class Registry:
    """Crossref /works/<doi> from a record table; everything else 404. Counts requests, never paces."""
    base = ""

    def __init__(self, records):
        self.records = {k.lower(): v for k, v in records.items()}
        self.calls = []
        self.pacer = _nopace()
        self.requests = 0
        self.hits = 0

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        self.requests += 1
        if "api.crossref.org/works/" in url and "query" not in url:
            rec = self.records.get(urllib.parse.unquote(url.split("/works/", 1)[1]).lower())
            return (200, {}, json.dumps({"message": rec}).encode()) if rec else (404, {}, b"")
        return 404, {}, b""


def synthetic_record(doi, title, author, year, venue="Journal of Synthetic Studies"):
    return {"DOI": doi, "title": [title], "author": [{"family": author, "given": "T.", "sequence": "first"}],
            "issued": {"date-parts": [[year, 1]]}, "type": "journal-article", "container-title": [venue]}


def row(tid, *, title, authors, year, doi="", stem="", relevance="", feeds="", grade="", status="To Read",
        dup="", venue="Journal of Synthetic Studies", notes=""):
    r = {c: "" for c in TRACKER_COLUMNS}
    r.update({"ID": str(tid), "Title": title, "Author(s)": authors, "Year": str(year), "Journal/Source": venue,
              "DOI/URL": f"https://doi.org/{doi}" if doi else "", "File stem": stem, "Status": status,
              "Relevance (max 3 sentences)": relevance, "Feeds": feeds, "Evidence grade": grade,
              "Duplicate of": dup, "Notes": notes})
    return r


def loader(pg, ws, registry, root=None):
    from litkb.migrate_legacy import run as mrun

    conn = pg.session("litkb_writer")
    return mrun.Loader(conn, ws, pg.tokens[ws], agent="claude-p3", session=f"p3-{uuid.uuid4().hex[:8]}",
                       client=registry, root=root)


def plant(tmp_path, title, author):
    """A held file for a work: a real PDF written under a scratch literature root, bound in place."""
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    stem = f"{author}_2020_{uuid.uuid4().hex[:8]}"
    (root / "Validation" / f"{stem}.pdf").write_bytes(paper_pdf(title, author))
    return root, stem


def counts(pg, conn=None):
    q = ("SELECT (SELECT count(*) FROM litkb.works), (SELECT count(*) FROM litkb.identifiers), "
         "(SELECT count(*) FROM litkb.files), (SELECT count(*) FROM litkb.candidates), "
         "(SELECT count(*) FROM litkb.admissions), (SELECT count(*) FROM litkb.discrepancies), "
         "(SELECT count(*) FROM litkb.uses)")
    return pg.one(q, conn=conn)


def discrepancies(pg, ws, conn=None):
    return {(r[0], r[1], r[2]): r for r in pg.conn.execute(
        "SELECT source, source_row, field, claimed_value, registry_value, ratio, work_id, candidate_id "
        "FROM litkb.discrepancies WHERE workstream_id = %s", (ws,)).fetchall()}


# ── no server needed ──────────────────────────────────────────────────────────────────────

def test_feeds_tokens_are_parsed_per_the_convention():
    """LITERATURE_CONVENTION.md: semicolon-separated, doc-qualified. Order kept, blanks and repeats dropped,
    and a token is NEVER dropped for being unresolvable — P3 records what the tracker said."""
    from litkb.migrate_legacy.sources import feeds_tokens

    assert feeds_tokens("framework §13.1; gap row 6 ; ; review §4.18.4; framework §13.1") == \
        ["framework §13.1", "gap row 6", "review §4.18.4"]
    assert feeds_tokens("report LIT_HUNT_FINAL_2026-09-06.md#§5.") == ["report LIT_HUNT_FINAL_2026-09-06.md#§5"]
    assert feeds_tokens("") == [] and feeds_tokens(None) == []
    assert feeds_tokens("decision litkb-p0-foundation") == ["decision litkb-p0-foundation"]


def test_the_case_table_is_the_registry_comparator_not_a_second_rule():
    """plan.compare_row must delegate to registry.compare_claimed (CLAUDE.md 3.3): a claim P2 accepts, P3
    accepts, and a claim P2 refuses, P3 calls a disagreement."""
    from litkb.admit import registry as _registry
    from litkb.migrate_legacy.plan import claim_agrees, compare_row

    rec = _registry.parse_crossref(synthetic_record("10.5555/x", "A title about canopy mapping", "Tester", 2020),
                                   "10.5555/x")
    same = {"title": "A title about canopy mapping", "authors": "Tester, T.", "year": "2020", "venue": ""}
    assert claim_agrees(compare_row(rec, same))
    assert _registry.compare_claimed(rec, same)["accepted"]
    other = dict(same, title="Something else entirely, about hidden Markov chains")
    assert not claim_agrees(compare_row(rec, other))
    assert not _registry.compare_claimed(rec, other)["accepted"]
    # +/-1 year with title AND first author matching is accepted by both (decisions.yaml §15.15)
    assert claim_agrees(compare_row(rec, dict(same, year="2021")))
    assert not claim_agrees(compare_row(rec, dict(same, year="2022")))


def test_a_blank_journal_is_no_claim_and_an_abbreviation_is_a_disagreement():
    from litkb.admit import registry as _registry
    from litkb.migrate_legacy.plan import compare_row

    rec = _registry.parse_crossref(synthetic_record("10.5555/y", "T", "Tester", 2020, venue="IEEE Transactions on "
                                                    "Geoscience and Remote Sensing"), "10.5555/y")
    base = {"title": "T", "authors": "Tester", "year": "2020"}
    assert compare_row(rec, dict(base, venue=""))["journal"]["agrees"]
    assert compare_row(rec, dict(base, venue="IEEE Transactions on Geoscience and Remote Sensing"))["journal"]["agrees"]
    assert not compare_row(rec, dict(base, venue="IEEE TGRS"))["journal"]["agrees"]


def test_the_migration_writes_nothing_but_through_admission():
    """Design §13: "All loaders go through the P2 admission code — migration is admission in bulk, not a
    bypass." No module under migrate_legacy may INSERT, UPDATE or DELETE a litkb table in SQL text."""
    import re
    bad = []
    for p in sorted((SCRIPTS / "pipeline" / "litkb" / "migrate_legacy").glob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(INSERT\s+INTO|UPDATE\s+litkb|DELETE\s+FROM)\b", line, re.I):
                bad.append(f"{p.name}:{i}: {line.strip()}")
    assert not bad, "migrate_legacy writes to a table directly: " + "; ".join(bad)


# ── Postgres ──────────────────────────────────────────────────────────────────────────────

@pg_only
def test_the_writer_holds_no_direct_write_on_discrepancies(pg):
    """0015: discrepancies carries workstream_id, so it is a guarded relation (design §4.7, migration 0011)."""
    for priv in ("INSERT", "UPDATE", "DELETE"):
        got = pg.one("SELECT has_table_privilege(%s, 'litkb.discrepancies', %s)", ("litkb_writer", priv))[0]
        assert got is False, f"litkb_writer holds {priv} on litkb.discrepancies"
    assert pg.one("SELECT has_table_privilege('litkb_writer', 'litkb.discrepancies', 'SELECT')")[0] is True
    assert pg.one("SELECT has_function_privilege('litkb_writer', 'litkb.record_discrepancy(uuid, text, text, "
                  "text, text, text, text, numeric, jsonb, uuid, uuid, text, text)', 'EXECUTE')")[0] is True


@pg_only
def test_record_discrepancy_needs_the_workstream_token(pg):
    ws = pg.ws()
    conn = pg.session("litkb_writer")
    cand = pg.one("SELECT litkb.add_candidate(%s, %s, 'manual', 'x', NULL, NULL, NULL, 't', NULL, NULL, NULL)",
                  (ws, pg.tokens[ws]), conn=conn)[0]
    with pytest.raises(Exception) as e:
        conn.execute("SELECT litkb.record_discrepancy(%s,%s,'tracker','1','title','a','b',NULL,'{}'::jsonb,"
                     "NULL,%s,'a','s')", (ws, "0" * 64, cand))
    assert "token" in str(e.value).lower()
    ok = conn.execute("SELECT litkb.record_discrepancy(%s,%s,'tracker','1','title','a','b',NULL,'{}'::jsonb,"
                      "NULL,%s,'a','s')", (ws, pg.tokens[ws], cand)).fetchone()[0]
    assert ok is not None
    # the same field twice is the same record: the load is idempotent
    again = conn.execute("SELECT litkb.record_discrepancy(%s,%s,'tracker','1','title','a','b',NULL,'{}'::jsonb,"
                         "NULL,%s,'a','s')", (ws, pg.tokens[ws], cand)).fetchone()[0]
    assert again == ok


@pg_only
def test_a_disagreeing_claim_with_a_file_admits_on_the_binding(pg, tmp_path):
    """Case B. The registry record is admitted; the tracker's wrong title survives only as a discrepancy."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)   # needs pdftotext
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3-{hexid}", f"Canopy {hexid} mapping from aerial imagery", "Tester"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, author, 2020)}), root=root)
    r = row(1, title="A completely different title about Markov random fields", authors="Tester, T.",
            year=2020, doi=doi, stem=stem)
    c = mrun.load_tracker(ctx, rows=[r], manifest={stem: {"stem": stem}})
    assert c["admitted"] == 1 and c["bound"] == 1, ctx.log
    assert ctx.log[0]["case"] == "B" and ctx.log[0]["shape"] == "file"
    d = discrepancies(pg, ws)
    assert ("tracker", "1", "title") in d
    assert d[("tracker", "1", "title")][3] == "A completely different title about Markov random fields"
    assert d[("tracker", "1", "title")][4] == title
    assert d[("tracker", "1", "title")][6] is not None, "an admitted row's discrepancy names its work"
    # the work admitted is the REGISTRY record, never the claim (decisions.yaml P3 load)
    assert pg.one("SELECT title FROM litkb.ws_works WHERE view_workstream_id = %s AND title = %s",
                  (ws, title)) is not None


@pg_only
def test_a_disagreeing_claim_with_no_file_is_held_not_admitted(pg):
    """Case C. A DOI alone proves only that SOME work exists (0013 `_check_registry`): admitting it on a claim
    the registry contradicts would bypass check 1. The row is HELD — recorded, flagged, never admitted."""
    from litkb.migrate_legacy import run as mrun

    hexid = uuid.uuid4().hex[:8]
    doi, title = f"10.5555/p3-{hexid}", f"Canopy {hexid} mapping from aerial imagery"
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, "Tester", 2020)}))
    r = row(7, title="A completely different title about Markov random fields", authors="Tester, T.",
            year=2020, doi=doi)
    c = mrun.load_tracker(ctx, rows=[r], manifest={})
    assert c["admitted"] == 0 and c["held_no_file"] == 1, ctx.log
    assert ctx.log[0]["case"] == "C" and ctx.log[0]["outcome"] == "held-needs-file"
    assert pg.one("SELECT count(*) FROM litkb.admissions WHERE workstream_id = %s", (ws,))[0] == 0
    d = discrepancies(pg, ws)
    assert ("tracker", "7", "title") in d
    assert d[("tracker", "7", "title")][7] is not None, "a held row's discrepancy names its candidate"


@pg_only
def test_kill_a_disagreeing_title_produces_a_discrepancy_record(pg, tmp_path):
    """§14 P3 kill: a planted tracker row whose title disagrees with the registry produces a discrepancy
    record. With the discrepancy writer removed (harness row P3-1/P3-2) this assertion fails."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3-{hexid}", f"Total {hexid} variation regularization for denoising", "Allard"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, author, 2007, venue="SIAM J. Math. Anal.")}),
                 root=root)
    r = row(11, title="An unrelated title concerning stochastic matrices", authors="Allard, W.K.", year=2007,
            doi=doi, stem=stem, venue="SIAM Journal on Mathematical Analysis")
    mrun.load_tracker(ctx, rows=[r], manifest={stem: {"stem": stem}})
    d = discrepancies(pg, ws)
    # BEGIN guard: the disagreeing fields are all on the record
    assert ("tracker", "11", "title") in d, f"no title discrepancy was recorded: {sorted(d)}"
    assert ("tracker", "11", "journal") in d, f"no journal discrepancy was recorded: {sorted(d)}"
    got = d[("tracker", "11", "title")]
    assert got[3] == "An unrelated title concerning stochastic matrices" and got[4] == title
    assert got[5] is not None and float(got[5]) < 0.85, "the discrepancy carries the comparator's ratio"
    # END guard: the disagreeing fields are all on the record
    assert pg.one("SELECT count(*) FROM litkb.discrepancies WHERE workstream_id = %s", (ws,))[0] >= 2


@pg_only
def test_kill_a_planted_duplicate_doi_row_is_rejected_at_load(pg, tmp_path):
    """§14 P3 kill: a second tracker row carrying a DOI already admitted is refused as a duplicate — one work,
    two candidates, the second linked to the first's work."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3-{hexid}", f"Canopy {hexid} mapping from aerial imagery", "Tester"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    reg = Registry({doi: synthetic_record(doi, title, author, 2020)})
    ctx = loader(pg, ws, reg, root=root)
    first = row(20, title=title, authors=f"{author}, T.", year=2020, doi=doi, stem=stem)
    # the plant: the SAME DOI in a different spelling, the way the manifest once carried 10.4171/JEMS/183
    second = row(21, title=title, authors=f"{author}, T.", year=2020, doi=doi.upper().replace("10.5555", "10.5555"),
                 dup="20", status="Duplicate")
    c = mrun.load_tracker(ctx, rows=[first, second], manifest={stem: {"stem": stem}})
    assert c["admitted"] == 1, ctx.log
    assert c["duplicate"] == 1, f"the duplicate DOI row was not rejected at load: {ctx.log}"
    assert ctx.log[1]["outcome"] == "duplicate"
    works = pg.one("SELECT count(*) FROM litkb.identifiers WHERE scheme = 'doi' AND value_norm = %s",
                   (doi.lower(),))[0]
    assert works == 1, "the duplicate spelling created a second identifier"
    assert pg.one("SELECT state, admitted_work_id FROM litkb.candidates WHERE workstream_id = %s "
                  "AND source_detail = 'tracker ID 21'", (ws,))[0] == "duplicate"
    # the tracker's own Duplicate-of claim is kept as a flag, not acted on
    assert ("tracker", "21", "duplicate_of") in discrepancies(pg, ws)


@pg_only
def test_kill_the_planted_averkov_wrong_doi_row_is_rejected_at_load(pg):
    """§14 P3 kill, on the REAL pre-fix row: the manifest carried Averkov 2009 under 10.4171/JEMS/183, whose
    Crossref record is a knot-theory paper (ratio 0.36). Loaded as a tracker row with its real file, the load
    must refuse it — at check 1 on the claim, or at binding. It must never reach a work."""
    from litkb.migrate_legacy import run as mrun

    k = KILL["averkov"]
    pre = PREFIX_ROWS[k["stem"]]
    pdf = VALIDATION / f"{k['stem']}.pdf"
    _need_file(pdf)
    ws = pg.ws()
    ctx = loader(pg, ws, Registry(CROSSREF))
    r = row(30, title=pre["title"], authors=pre["authors"], year=pre["year"], doi=pre["doi"], stem=k["stem"],
            venue=pre.get("venue", ""))
    c = mrun.load_tracker(ctx, rows=[r], manifest={k["stem"]: pre})
    assert c["admitted"] == 0, f"the planted wrong DOI was admitted: {ctx.log}"
    assert c["refused"] == 1, ctx.log
    adm = pg.one("SELECT state, checks FROM litkb.admissions WHERE workstream_id = %s", (ws,))
    assert adm[0] == "refused"
    assert adm[1]["check3_binding"]["verdict"] in ("binding-failed", "binding-pending"), adm[1]["check3_binding"]
    assert pg.one("SELECT count(*) FROM litkb.identifiers WHERE scheme = 'doi' AND value_norm = %s",
                  (pre["doi"].lower(),))[0] == 0
    # the wrong DOI is on the record as a discrepancy, so the review can see what the legacy row claimed
    assert ("tracker", "30", "title") in discrepancies(pg, ws)


@pg_only
def test_kill_loading_twice_admits_nothing_new(pg, tmp_path):
    """§14 P3 kill: the load is idempotent. Not "admits no new work" — NOTHING new: no candidate, no
    admission, no discrepancy, no use. A second run must read the first run's candidates and stop."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3-{hexid}", f"Canopy {hexid} mapping from aerial imagery", "Tester"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    reg = Registry({doi: synthetic_record(doi, title, author, 2020)})
    rows = [row(40, title="A disagreeing title about hidden Markov chains", authors=f"{author}, T.", year=2020,
                doi=doi, stem=stem, relevance="Why this matters here.", feeds="gap row 6", grade="PRIMARY"),
            row(41, title="Nothing resolves for this row", authors="Nobody, N.", year=1954)]
    manifest = {stem: {"stem": stem}}
    ctx = loader(pg, ws, reg, root=root)
    first = mrun.load_tracker(ctx, rows=rows, manifest=manifest)
    before = counts(pg)
    ctx2 = loader(pg, ws, reg, root=root)
    second = mrun.load_tracker(ctx2, rows=rows, manifest=manifest)
    after = counts(pg)
    assert second["skipped_already_loaded"] == len(rows), ctx2.log
    assert second["admitted"] == 0 and second["discrepancies"] == 0 and second["uses"] == 0
    assert after == before, f"a second load changed the database: {before} -> {after}"
    assert first["uses"] == 1, "the tracker's Relevance/Feeds became a use version"


@pg_only
def test_the_tracker_use_is_a_proposal_with_the_feeds_tokens_and_no_evidence(pg, tmp_path):
    """Design §4.5 and §14: the tracker's Relevance / grade / Feeds / Notes become a use version, state
    `proposed`. No evidence pointer: a verified quote needs an extracted block, and blocks arrive in P5."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3-{hexid}", f"Canopy {hexid} mapping from aerial imagery", "Tester"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, author, 2020)}), root=root)
    mrun.load_tracker(ctx, rows=[row(50, title=title, authors=f"{author}, T.", year=2020, doi=doi, stem=stem,
                                     relevance="Supplies the crown-delineation baseline.",
                                     feeds="gap row 6; review §4.18", grade="PRIMARY", notes="fetched by DOI")],
                      manifest={stem: {"stem": stem}})
    # scoped to the use WRITTEN here: ws_uses is a workstream's whole view, and a proposal in another
    # workstream is visible in it once `uses.current_version_id` is set
    u = pg.one("SELECT statement, kind, status, feeds, confidence, rationale, state FROM litkb.ws_uses "
               "WHERE view_workstream_id = %s AND workstream_id = %s", (ws, ws))
    assert u[0] == "Supplies the crown-delineation baseline."
    assert u[1] == "context" and u[2] == "proposed" and u[6] == "proposed"
    assert list(u[3]) == ["gap row 6", "review §4.18"]
    assert u[4] == "PRIMARY" and "fetched by DOI" in u[5]
    assert pg.one("SELECT count(*) FROM litkb.use_evidence e JOIN litkb.use_versions v "
                  "ON v.version_id = e.use_version_id WHERE v.workstream_id = %s", (ws,))[0] == 0,         "P3 attaches no unverified evidence"


@pg_only
def test_a_manifest_sha256_that_is_not_the_file_on_disk_is_flagged(pg, tmp_path):
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3-{hexid}", f"Canopy {hexid} mapping from aerial imagery", "Tester"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, author, 2020)}), root=root)
    mrun.load_manifest(ctx, rows=[{"stem": stem, "title": title, "authors": f"{author}, T.", "year": "2020",
                                   "venue": "Journal of Synthetic Studies", "doi": doi, "arxiv": "",
                                   "sha256": "0" * 64, "source_route": "unknown", "obtained_date": "2026-09-12",
                                   "verified_against_extract": "yes", "cited_by": ""}])
    d = discrepancies(pg, ws)
    assert ("manifest", stem, "sha256") in d, sorted(d)
    assert d[("manifest", stem, "sha256")][3] == "0" * 64
    assert d[("manifest", stem, "sha256")][4] == hashlib.sha256(
        (root / "Validation" / f"{stem}.pdf").read_bytes()).hexdigest()


@pg_only
def test_the_export_round_trips_every_loaded_row(pg, tmp_path):
    """Design §10: the tracker is an EXPORT. Every loaded row comes back — the admitted ones with the registry
    record, the held ones verbatim from their candidate — and no row is lost."""
    from litkb import export as ex
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3-{hexid}", f"Canopy {hexid} mapping from aerial imagery", "Tester"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, author, 2020)}), root=root)
    rows = [row(60, title="A disagreeing title", authors=f"{author}, T.", year=2020, doi=doi, stem=stem,
                relevance="Baseline.", feeds="gap row 6", grade="PRIMARY"),
            row(61, title="Nothing resolves for this row", authors="Nobody, N.", year=1954, status="Not Obtained")]
    mrun.load_tracker(ctx, rows=rows, manifest={stem: {"stem": stem}})
    out = ex.tracker_rows(pg.conn, ws)
    assert [r["ID"] for r in out] == ["60", "61"], out
    assert out[0]["litkb_state"] == "admitted", (ctx.log, out[0])
    # row 60 prints the REGISTRY record, not the tracker's claim; the difference is a discrepancy row
    assert out[0]["Title"] == title and out[0]["DOI/URL"] == f"https://doi.org/{doi}"
    assert out[0]["Relevance (max 3 sentences)"] == "Baseline." and out[0]["Feeds"] == "gap row 6"
    assert out[0]["litkb_key"] and out[0]["litkb_state"] == "admitted"
    # row 61 is held: printed verbatim from its candidate, with the state saying so
    assert out[1]["Title"] == "Nothing resolves for this row" and out[1]["Status"] == "Not Obtained"
    assert out[1]["litkb_key"] == "" and out[1]["litkb_state"] == "new"
    assert ("tracker", "60", "title") in discrepancies(pg, ws)
    m = ex.manifest_rows(pg.conn, ws)
    assert len(m) == 1 and m[0]["doi"] == doi and m[0]["verified_against_extract"] == "yes"
    assert m[0]["stem"] == out[0]["litkb_key"], "M7: works.key is authoritative, the stem is derived from it"
    p = ex.write_csv(tmp_path / "t.csv", ex.TRACKER_EXPORT_COLUMNS, out)
    assert [r["ID"] for r in csv.DictReader(open(p, encoding="utf-8", newline=""))] == ["60", "61"]


@pg_only
def test_a_same_surname_year_slug_collision_takes_the_conventions_a_b_suffix(pg, tmp_path):
    """LITERATURE_CONVENTION.md: an `a`/`b` suffix breaks a same-surname, same-year collision. The key's slug
    is the first four non-stopword title words, so a bulk load meets that collision; without the suffix the
    second work is refused as a key collision and the row is lost. `a` and `b` are all `works.key`'s CHECK
    allows, so the FOURTH such work is refused and reported, never renamed into an unconventional key."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    base = "Ridge regression for canopy"           # the same first four slug words for every row
    ws = pg.ws()
    keys, records, rows, manifest = [], {}, [], {}
    for i in range(4):
        doi = f"10.5555/p3col-{uuid.uuid4().hex[:8]}"
        title = f"{base} part {i} {uuid.uuid4().hex[:6]}"
        records[doi] = synthetic_record(doi, title, "Collider", 2019)
        root, stem = plant(tmp_path, title, "Collider")
        manifest[stem] = {"stem": stem}
        rows.append(row(70 + i, title=title, authors="Collider, C.", year=2019, doi=doi, stem=stem))
    ctx = loader(pg, ws, Registry(records), root=root)
    c = mrun.load_tracker(ctx, rows=rows, manifest=manifest)
    keys = [r[0] for r in pg.conn.execute(
        "SELECT key FROM litkb.works WHERE key LIKE 'Collider_2019%%' ORDER BY key").fetchall()]
    assert keys == ["Collider_2019_ridge-regression-canopy-part",
                    "Collider_2019a_ridge-regression-canopy-part",
                    "Collider_2019b_ridge-regression-canopy-part"], keys
    assert c["admitted"] == 3 and c["refused"] == 1, ctx.log
    assert ctx.log[3]["outcome"] == "collided", ctx.log[3]


@pg_only
def test_kill_the_diff_gate_reports_an_unexplained_cell_when_the_discrepancy_is_missing(pg, tmp_path):
    """§14 P3's gate, as `qc/instruments/litkb_p3_diff.py` runs it: a changed cell is explained, format-only,
    structural or UNEXPLAINED, and the gate fails while UNEXPLAINED is above zero.

    This is the kill the design names — "with the discrepancy writer removed the gate test fails". It runs the
    instrument's classifier twice over one real changed cell: with the discrepancy record present (explained,
    gate passes) and with it absent (UNEXPLAINED, gate fails). Harness row P1a removes the writer for real."""
    import sys

    sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))
    import litkb_p3_diff as diff

    today = [{"ID": "80", "Title": "An unrelated title concerning stochastic matrices", "Year": "2007"}]
    exported = [{"ID": "80", "Title": "Total variation regularization for denoising", "Year": "2007"}]
    explained = {("tracker", "80", "title"): ("An unrelated title concerning stochastic matrices",
                                              "Total variation regularization for denoising", 0.31)}
    with_record = diff.compare("tracker", today, exported, "ID", ["Title", "Year"], explained, set())
    assert [r["bucket"] for r in with_record] == ["explained"], with_record
    # BEGIN guard: a changed cell with no discrepancy record is UNEXPLAINED and the gate fails
    without = diff.compare("tracker", today, exported, "ID", ["Title", "Year"], {}, set())
    assert [r["bucket"] for r in without] == ["UNEXPLAINED"], without
    # END guard: a changed cell with no discrepancy record is UNEXPLAINED and the gate fails
    # a cell that only normalises differently is never a gate failure
    fmt = diff.compare("tracker", [{"ID": "81", "Author(s)": "Nowak, D. J. & Greenfield, E. J."}],
                       [{"ID": "81", "Author(s)": "Nowak, D.J. & Greenfield, E.J."}], "ID", ["Author(s)"], {}, set())
    assert [r["bucket"] for r in fmt] == ["format"], fmt
    # a HELD row's cell must never change: the export prints it back verbatim, so a difference is a bug
    held = diff.compare("tracker", today, exported, "ID", ["Title"], {}, {"80"})
    assert held[0]["bucket"] == "UNEXPLAINED" and "HELD" in held[0]["explanation"]
    # a whole column the design changes on purpose is structural, stated once
    # the manifest joins on sha256, so a stem that became the work key is a CHANGED CELL, and a structural one
    st = diff.compare("manifest", [{"sha256": "a" * 64, "stem": "Allard_2007_total-variation"}],
                      [{"sha256": "a" * 64, "stem": "Allard_2007_total-variation-regularization-image"}],
                      "sha256", ["stem"], {}, set())
    assert [r["bucket"] for r in st] == ["structural"], st


@pg_only
def test_a_deduped_row_still_records_its_use_and_a_duplicate_of_row_does_not(pg, tmp_path):
    """A tracker row whose DOI is already admitted is NOT re-admitted — but it still carries the tracker's
    Relevance, grade and Feeds, and that is what a use version is for. The exception is a `Duplicate of` row:
    the tracker keeps the payload on the original row only (LITERATURE_CONVENTION.md), so it gets no use, and
    the export must not paint the original's Relevance onto it."""
    from litkb import export as ex
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3dd-{hexid}", f"Dedupe {hexid} of an already admitted work", "Deduper"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    reg = Registry({doi: synthetic_record(doi, title, author, 2021)})
    ctx = loader(pg, ws, reg, root=root)
    rows = [row(90, title=title, authors=f"{author}, D.", year=2021, doi=doi, stem=stem,
                relevance="The original row's relevance.", feeds="gap row 6", grade="PRIMARY"),
            # the same DOI again, NOT flagged as a tracker duplicate: a dedupe against an existing work
            row(91, title=title, authors=f"{author}, D.", year=2021, doi=doi,
                relevance="A second row's own relevance.", feeds="review §4.18", grade="ABSTRACT"),
            # a tracker `Duplicate of` row: no payload of its own
            row(92, title=title, authors=f"{author}, D.", year=2021, doi=doi, dup="90", status="Duplicate",
                relevance="Duplicate — see [ID 90, Deduper 2021]")]
    c = mrun.load_tracker(ctx, rows=rows, manifest={stem: {"stem": stem}})
    assert c["admitted"] == 1 and c["duplicate"] == 2, ctx.log
    # BEGIN guard: a deduped row's use is recorded
    assert c["uses"] == 2, f"the deduped row's Relevance/Feeds were dropped: {ctx.log}"
    # END guard: a deduped row's use is recorded
    statements = {r[0] for r in pg.conn.execute(
        "SELECT statement FROM litkb.use_versions WHERE workstream_id = %s", (ws,)).fetchall()}
    assert statements == {"The original row's relevance.", "A second row's own relevance."}, statements
    out = {r["ID"]: r for r in ex.tracker_rows(pg.conn, ws)}
    # BEGIN guard: two rows on one work each print their OWN use, never each other's
    assert out["90"]["Relevance (max 3 sentences)"] == "The original row's relevance."
    assert out["90"]["Feeds"] == "gap row 6" and out["90"]["Evidence grade"] == "PRIMARY"
    assert out["91"]["Relevance (max 3 sentences)"] == "A second row's own relevance."
    assert out["91"]["Feeds"] == "review §4.18" and out["91"]["Evidence grade"] == "ABSTRACT"
    # END guard: two rows on one work each print their OWN use, never each other's
    assert out["92"]["Relevance (max 3 sentences)"] == "Duplicate — see [ID 90, Deduper 2021]"
    assert out["92"]["Evidence grade"] == "" and out["92"]["Feeds"] == ""


@pg_only
def test_a_file_the_database_refused_is_still_a_manifest_row(pg, tmp_path):
    """Dropping a refused file would DELETE a row from the manifest. Its legacy row is printed back verbatim,
    with `litkb_state` saying what happened, and `litkb_legacy_stem` carrying the join the diff needs."""
    from litkb import export as ex
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title = f"10.5555/p3rf-{hexid}", f"Refused {hexid} file of a real registry work"
    root, stem = plant(tmp_path, "A totally different paper about something else", "Nobody")
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, "Refusee", 2020)}), root=root)
    mrow = {"stem": stem, "title": title, "authors": "Refusee, R.", "year": "2020", "venue": "J. Synth.",
            "doi": doi, "arxiv": "", "sha256": "", "source_route": "unknown (pre-manifest)",
            "obtained_date": "2026-09-12", "verified_against_extract": "yes", "cited_by": "a_report.md"}
    c = mrun.load_manifest(ctx, rows=[mrow])
    assert c["admitted"] == 0 and c["refused"] == 1, ctx.log
    m = ex.manifest_rows(pg.conn, ws)
    # BEGIN guard: a refused file is still exported as a manifest row
    assert len(m) == 1, f"the refused file was dropped from the manifest: {m}"
    # END guard: a refused file is still exported as a manifest row
    assert m[0]["litkb_legacy_stem"] == stem and m[0]["stem"] == stem
    assert m[0]["litkb_key"] == "" and m[0]["litkb_state"] == "rejected"
    assert m[0]["cited_by"] == "a_report.md" and m[0]["source_route"] == "unknown (pre-manifest)"


@pg_only
def test_a_resumed_load_backfills_a_missing_use_and_only_once(pg, tmp_path):
    """A load interrupted between the admission and the use version leaves the row admitted with no use. The
    resume writes it; a third pass writes nothing, so the idempotency kill still holds."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3bf-{hexid}", f"Backfill {hexid} of an interrupted load", "Resumer"
    root, stem = plant(tmp_path, title, author)
    ws = pg.ws()
    reg = Registry({doi: synthetic_record(doi, title, author, 2020)})
    r = row(95, title=title, authors=f"{author}, R.", year=2020, doi=doi, stem=stem,
            relevance="Recorded on the resume.", feeds="gap row 6")
    ctx = loader(pg, ws, reg, root=root)
    ctx.record_use = lambda *a, **k: None                       # the interruption: admitted, no use written
    mrun.load_tracker(ctx, rows=[r], manifest={stem: {"stem": stem}})
    assert pg.one("SELECT count(*) FROM litkb.use_versions WHERE workstream_id = %s", (ws,))[0] == 0
    second = mrun.load_tracker(loader(pg, ws, reg, root=root), rows=[r], manifest={stem: {"stem": stem}})
    assert second["skipped_already_loaded"] == 1 and second.get("uses_backfilled") == 1
    assert pg.one("SELECT count(*) FROM litkb.use_versions WHERE workstream_id = %s", (ws,))[0] == 1
    third = mrun.load_tracker(loader(pg, ws, reg, root=root), rows=[r], manifest={stem: {"stem": stem}})
    assert third.get("uses_backfilled", 0) == 0, "the backfill wrote a second copy of the same use"
    assert pg.one("SELECT count(*) FROM litkb.use_versions WHERE workstream_id = %s", (ws,))[0] == 1


@pg_only
def test_one_file_two_works_binds_to_one_and_flags_the_other(pg, tmp_path):
    """Stage 0's inventory (Reports/LITKB_INVENTORY_2026-09-15.md): two sha256s are each filed under two
    different works, because the archive served one md5 for two DOIs. One file may never bind to two works —
    the database refuses the second on `files.sha256` — and which work keeps it is decided by BINDING, not by
    tracker order: the file's first page carries one registry title, so the other work fails check 3 whichever
    is tried first. The second work is left unbound with a `sha256_collision` discrepancy naming the work that
    holds the file, so nothing is silently unbound."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    right_doi, right_title, author = f"10.5555/p3col1-{hexid}", f"Collision {hexid} the paper in the file", "Rightful"
    wrong_doi, wrong_title = f"10.5555/p3col2-{hexid}", f"Another {hexid} paper entirely, not in that file"
    root, stem = plant(tmp_path, right_title, author)          # ONE file, carrying the RIGHT title
    ws = pg.ws()
    reg = Registry({right_doi: synthetic_record(right_doi, right_title, author, 2024),
                    wrong_doi: synthetic_record(wrong_doi, wrong_title, "Wrongful", 2026)})
    # the WRONG work is tried FIRST, naming the same stem — order must not decide the outcome
    rows = [row(100, title=wrong_title, authors="Wrongful, W.", year=2026, doi=wrong_doi, stem=stem),
            row(101, title=right_title, authors=f"{author}, R.", year=2024, doi=right_doi, stem=stem)]
    manifest = {stem: {"stem": stem}}
    c = mrun.load_tracker(loader(pg, ws, reg, root=root), rows=rows, manifest=manifest)
    held = pg.conn.execute(
        "SELECT w.key FROM litkb.files f JOIN litkb.file_versions v ON v.version_id = f.current_version_id "
        "JOIN litkb.works w ON w.id = v.work_id WHERE v.workstream_id = %s", (ws,)).fetchall()
    # exactly one work holds the file, and it is the one whose registry title the first page carries
    assert len(held) == 1 and held[0][0].startswith("Rightful_2024"), held
    assert c["bound"] == 1, c
    # the wrong work bound nothing: its admission failed check 3 against a first page that is not its paper
    wrong_state = pg.one("SELECT state, state_reason FROM litkb.candidates WHERE workstream_id = %s "
                         "AND source_detail = 'tracker ID 100'", (ws,))
    assert wrong_state[0] == "rejected" and "binding" in (wrong_state[1] or "")


@pg_only
def test_a_file_already_held_by_another_work_is_recorded_as_a_collision(pg, tmp_path):
    """The second half of the same finding: when the collision surfaces as `file_duplicate` — the same bytes
    offered for a work that WOULD have bound — the row is left unbound with a record naming the holder."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi_a, doi_b = f"10.5555/p3dup1-{hexid}", f"10.5555/p3dup2-{hexid}"
    title = f"Shared {hexid} bytes under two DOIs"
    root, stem_a = plant(tmp_path, title, "Sharer")
    # the SAME bytes filed under a second stem, exactly as the archive's one-md5-two-DOIs hazard produced
    stem_b = f"Sharer_2024_{uuid.uuid4().hex[:8]}"
    (root / "Validation" / f"{stem_b}.pdf").write_bytes((root / "Validation" / f"{stem_a}.pdf").read_bytes())
    ws = pg.ws()
    reg = Registry({doi_a: synthetic_record(doi_a, title, "Sharer", 2024),
                    doi_b: synthetic_record(doi_b, title + " (reissue)", "Sharer", 2025)})
    rows = [row(110, title=title, authors="Sharer, S.", year=2024, doi=doi_a, stem=stem_a),
            row(111, title=title + " (reissue)", authors="Sharer, S.", year=2025, doi=doi_b, stem=stem_b)]
    c = mrun.load_tracker(loader(pg, ws, reg, root=root), rows=rows,
                          manifest={stem_a: {"stem": stem_a}, stem_b: {"stem": stem_b}})
    assert c["bound"] == 1, f"one file bound to two works: {c}"
    d = discrepancies(pg, ws)
    # BEGIN guard: the second work is unbound WITH a record naming the work that holds the file
    assert ("manifest", stem_b, "sha256_collision") in d, sorted(k for k in d if k[2] == "sha256_collision")
    assert (d[("manifest", stem_b, "sha256_collision")][4] or "").startswith("Sharer_2024")
    # END guard: the second work is unbound WITH a record naming the work that holds the file


@pg_only
def test_record_discrepancy_names_a_work_or_a_candidate(pg):
    """0015: a discrepancy with neither a work nor a candidate belongs to nothing and could never be reviewed.
    The front always passes one, so this calls the function directly (harness row P1c)."""
    ws = pg.ws()
    conn = pg.session("litkb_writer")
    with pytest.raises(Exception) as e:
        conn.execute("SELECT litkb.record_discrepancy(%s,%s,'tracker','1','title','a','b',NULL,'{}'::jsonb,"
                     "NULL,NULL,'a','s')", (ws, pg.tokens[ws]))
    assert "work or a candidate" in str(e.value)


@pg_only
def test_record_discrepancy_refuses_another_workstreams_candidate(pg):
    """0015: a discrepancy may not point at a candidate belonging to another workstream (harness row P1d) —
    the same rule admission carries, so a token cannot be used to write onto someone else's row."""
    ws_a, ws_b = pg.ws(), pg.ws()
    conn = pg.session("litkb_writer")
    other = pg.one("SELECT litkb.add_candidate(%s, %s, 'manual', 'x', NULL, NULL, NULL, 't', NULL, NULL, NULL)",
                   (ws_b, pg.tokens[ws_b]), conn=conn)[0]
    with pytest.raises(Exception) as e:
        conn.execute("SELECT litkb.record_discrepancy(%s,%s,'tracker','1','title','a','b',NULL,'{}'::jsonb,"
                     "NULL,%s,'a','s')", (ws_a, pg.tokens[ws_a], other))
    assert "not this workstream" in str(e.value)


def test_a_doi_spelled_differently_is_not_a_discrepancy():
    """`doi_discrepancy` compares CANONICAL DOIs (harness row P6a): `10.4171/JEMS/179` and `10.4171/jems/179`
    are one DOI — the real case from the 2026-09-13 manifest audit — and must not read as a changed DOI."""
    from litkb.migrate_legacy.plan import doi_discrepancy

    assert doi_discrepancy("https://doi.org/10.4171/JEMS/179", "10.4171/jems/179") is None
    assert doi_discrepancy("doi:10.4171/jems/179", "10.4171/jems/179") is None
    assert doi_discrepancy(" 10.4171/jems/179. ", "10.4171/jems/179") is None
    changed = doi_discrepancy("10.4171/jems/183", "10.4171/jems/179")
    assert changed and changed["claimed"] == "10.4171/jems/183" and changed["registry"] == "10.4171/jems/179"
    assert doi_discrepancy("", "10.4171/jems/179")["claimed"] is None


@pg_only
def test_a_nul_in_a_registry_record_reaches_neither_the_discrepancy_nor_the_use(pg, tmp_path):
    """Registry records and scanned PDF metadata carry NUL bytes, and Postgres refuses a NUL inside jsonb
    (UntranslatableCharacter). Both P3 jsonb payloads — the discrepancy's `detail`, which carries the
    registry's author list, and the use version's identity and fields — go through `front._jsonb`, which
    strips them. Harness rows P6d and P6e remove that on each path in turn.

    The NUL is planted in the REGISTRY record, which is where one actually arrives: a text column would
    refuse it outright (psycopg: "PostgreSQL text fields cannot contain NUL"), so only the jsonb payloads can
    carry one this far, and only the guard keeps them writable."""
    from litkb.migrate_legacy import run as mrun

    _need_file(VALIDATION)
    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3nul-{hexid}", f"Nul {hexid} bytes in a registry record", "Nuller"
    root, stem = plant(tmp_path, title, author)
    rec = synthetic_record(doi, title, author, 2020)
    rec["author"] = [{"family": author, "given": "N.\x00", "sequence": "first"},
                     {"family": "Second\x00", "given": "S."}]
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: rec}), root=root)
    r = row(120, title="A different title, so the authors are compared and recorded\x00",
            authors="Someone Else, S.", year=2020, doi=doi, stem=stem,
            relevance="Relevance for the use version.", feeds="gap row 6")
    c = mrun.load_tracker(ctx, rows=[r], manifest={stem: {"stem": stem}})
    assert c["admitted"] == 1 and c["uses"] == 1, ctx.log
    d = discrepancies(pg, ws)
    # BEGIN guard: a NUL in the registry record does not stop the discrepancy or the use being written
    assert ("tracker", "120", "authors") in d, sorted(d)
    detail = pg.one("SELECT detail FROM litkb.discrepancies WHERE workstream_id = %s AND field = 'authors'",
                    (ws,))[0]
    assert "\x00" not in json.dumps(detail)
    assert any("Second" in a for a in detail["registry_authors"]), detail
    stored_registry = pg.one("SELECT registry_value FROM litkb.discrepancies WHERE workstream_id = %s "
                             "AND field = 'authors'", (ws,))[0]
    assert "\x00" not in stored_registry and "Nuller" in stored_registry
    assert "\x00" not in pg.one("SELECT title FROM litkb.candidates WHERE workstream_id = %s", (ws,))[0]
    # END guard: a NUL in the registry record does not stop the discrepancy or the use being written
    stmt = pg.one("SELECT statement FROM litkb.use_versions WHERE workstream_id = %s", (ws,))[0]
    assert stmt == "Relevance for the use version."


@pg_only
def test_litkb_migrate_normalises_its_agent_and_session_labels(pg, tmp_path, monkeypatch):
    """`litkb migrate` records who loaded the rows. The labels go through the ONE normaliser, so an invisible
    character in `--session` cannot make a second session look like a third (harness row P6f)."""
    from litkb import commands

    conn = pg.session("litkb_writer")
    ws = pg.ws()
    wt = tmp_path / "wt"
    (wt).mkdir()
    (wt / ".litkb-workstream").write_text(json.dumps({"workstream_id": str(ws), "token": pg.tokens[ws]}),
                                          encoding="utf-8")
    rc = commands.main(["--db", "litkb_test", "--dir", str(wt), "--agent", "claude​-p3",
                        "--session", "p3-labels ", "migrate", "tracker", "--limit", "0"],
                       connect=lambda _db: conn)
    assert rc == 0
    # the load was empty, so assert on what the labels became: no workstream row carries the raw spelling
    from litkb.textnorm import norm_label
    assert norm_label("p3-labels ") == "p3-labels"
    assert norm_label("claude​-p3") == "claude-p3"


@pg_only
def test_a_legacy_row_naming_a_file_the_store_does_not_hold_is_recorded(pg, tmp_path):
    """Two kinds of row name a file that is not in the topic folder: one whose file was never there (Matheron
    1986) and one whose file was QUARANTINED because the bytes are a different paper — Stage 0's inventory
    found two sha256s each claimed by two manifest rows, and its referee read the first pages: both files are
    a third paper, so neither claimant may bind. Either way the work is admitted UNBOUND, and the row says so
    rather than being silently fileless (harness row P7h)."""
    from litkb.migrate_legacy import run as mrun

    hexid = uuid.uuid4().hex[:8]
    doi, title, author = f"10.5555/p3miss-{hexid}", f"Missing {hexid} file for a real registry work", "Claimant"
    ws = pg.ws()
    ctx = loader(pg, ws, Registry({doi: synthetic_record(doi, title, author, 2024)}), root=tmp_path / "Literture")
    stem = f"{author}_2024_quarantined-not-this-paper"
    r = row(130, title=title, authors=f"{author}, C.", year=2024, doi=doi, stem=stem)
    c = mrun.load_tracker(ctx, rows=[r], manifest={stem: {"stem": stem, "sha256": "bb14fdbc" + "0" * 56,
                                                          "source_route": "annas"}})
    # the work IS admitted — its registry record is not in doubt — and it holds no file
    assert c["admitted"] == 1 and c["bound"] == 0, ctx.log
    d = discrepancies(pg, ws)
    assert ("manifest", stem, "file_missing") in d, sorted(d)
    assert d[("manifest", stem, "file_missing")][3] == "bb14fdbc" + "0" * 56
    assert pg.one("SELECT count(*) FROM litkb.file_versions WHERE workstream_id = %s", (ws,))[0] == 0


def test_a_year_cell_with_the_conventions_suffix_does_not_stop_the_load():
    """Tracker rows 327 and 329 carry `2019a` and `2019b` — the filename convention's same-year suffix written
    into the YEAR column. There is no correction pass, so the cell is carried as it is and read leniently;
    `int('2019a')` raises, and on the live run of 2026-09-15 one such cell ended the pass at row 336."""
    from litkb.migrate_legacy.export_shape import year_int

    assert year_int("2019a") == 2019 and year_int("2019b") == 2019
    assert year_int("2019") == 2019 and year_int(2020) == 2020
    assert year_int("") is None and year_int(None) is None and year_int("n.d.") is None

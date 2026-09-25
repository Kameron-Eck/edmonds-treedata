"""litkb S4.5 fix wave (S4.5 decision D48), builder-FX-C: referee-stage-c's REJECT findings on the live run hardening-1,
reproduced on the run's own RECORDED bytes (qc/fixtures/litkb_fxc_rows/, provenance per hop in each recording.json).

  1  The MDPI CDN template padded the article number but not the volume: 12/12 two-digit-volume rows converted,
     0/5 one-digit-volume rows (L071 L074 L147 L155 L156; each CDN URL a real 404). The template now pads the
     volume to two digits (pipeline/litkb/acquire/landing_rules.json, rule `mdpi`, candidate `cdn`).
  2  S4.5 decision D50: `landing_pages_booked_bad_file` excuses a page of a work BOUND IN THE SAME RUN (the ruling's
     case: L062 L139 L146, `doaj` pages beside an `open_access` binding in one concurrent Stage B wave).

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_fx_stage_c.py -q -p no:cacheprovider

No test here touches the network: every client is a stub serving recorded bytes, or an answer named CONSTRUCTED."""
import importlib.util
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
pg_only = pytest.mark.requires_litkb_pg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_{name}_for_fxc_tests", SCRIPTS / "qc" / "instruments" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("litkb_hardening_c2b")

#: The CDN URLs the live run asked (the ladder-1 cassette, every request to mdpi-res.com that the MDPI rule's `cdn`
#: candidate built from the de-spaced venue): the 12 that answered 206 %PDF (two-digit volumes) and the 5 rows'
#: first slug that answered 404 (one-digit volumes). Read by builder-FX-C from the recording, 2026-09-24.
RUN_CDN_HITS = (
    "plants/plants-14-01677", "remotesensing/remotesensing-15-00765", "remotesensing/remotesensing-10-00581",
    "remotesensing/remotesensing-11-01309", "remotesensing/remotesensing-12-01505",
    "remotesensing/remotesensing-12-03815", "remotesensing/remotesensing-13-01749",
    "remotesensing/remotesensing-13-01789", "remotesensing/remotesensing-13-05084", "sensors/sensors-17-02427",
    "sensors/sensors-20-05500", "remotesensing/remotesensing-14-01777")
RUN_CDN_MISSES = {          # row: (the recorded 404 slug, the www.mdpi.com path the doi.org redirect named)
    "L071": ("geomatics/geomatics-4-00022", "2673-7418/4/4/22"),
    "L074": ("sensors/sensors-8-02161", "1424-8220/8/4/2161"),
    "L147": ("isprsinternationaljournalofgeoinformation/isprsinternationaljournalofgeoinformation-6-00292",
             "2220-9964/6/10/292"),
    "L155": ("remotesensing/remotesensing-2-02240", "2072-4292/2/9/2240"),
    "L156": ("remotesensing/remotesensing-2-02369", "2072-4292/2/10/2369"),
}
CDN = "https://mdpi-res.com/d_attachment/{slug}/article_deploy/{name}.pdf"


def _cdn(slug):
    return CDN.format(slug=slug, name=slug.split("/", 1)[1])


def _mdpi_rule():
    from litkb.acquire import landing as L
    return next(r for r in L.TABLE["rules"] if r["id"] == "mdpi")


def _cdn_built(journal, path):
    """What the loaded rule table's `cdn` candidate builds for www.mdpi.com/<path> with the journal slug given."""
    from litkb.acquire import landing as L

    spec = next(c for c in _mdpi_rule()["candidates"] if c["name"] == "cdn")
    import re
    m = re.search(spec["match"], f"https://www.mdpi.com/{path}")
    return L._expand(spec["template"], {k: v for k, v in m.groupdict().items() if v is not None},
                     {"journal": [journal]})


# ── 1. the MDPI CDN template ──────────────────────────────────────────────────────────────────
def test_the_cdn_template_rebuilds_every_url_the_run_converted():
    """The 12 recorded 206 conversions (two-digit volumes) are rebuilt EXACTLY by the fixed template: padding the
    volume to two digits changes nothing for them. The www.mdpi.com path is re-derived from the CDN name (volume,
    article), with issue 1 CONSTRUCTED — the template never reads the issue."""
    for slug in RUN_CDN_HITS:
        journal, name = slug.split("/")
        _j, vol, art = name.rsplit("-", 2)
        assert _cdn_built(journal, f"0000-0000/{int(vol)}/1/{int(art)}") == [_cdn(slug)], slug


@pytest.mark.parametrize("row", sorted(RUN_CDN_MISSES))
def test_the_cdn_template_pads_a_one_digit_volume_the_run_missed(row):
    """The 5 recorded one-digit-volume misses: the template no longer builds the URL the CDN answered 404 for, and
    builds the volume padded to two digits (MEASURED for L074 by the FX-C live probe; MDPI's own origin file names
    for L155/L156 are remotesensing-02-02240-v2.pdf / remotesensing-02-02369.pdf in the recording's Wayback
    captures; L071/L147 follow the same scheme, INFERRED)."""
    miss, path = RUN_CDN_MISSES[row]
    journal = miss.split("/")[0]
    got = _cdn_built(journal, path)
    assert got != [_cdn(miss)]
    _j, vol, art = miss.split("/")[1].rsplit("-", 2)
    assert got == [_cdn(f"{journal}/{journal}-{int(vol):02d}-{art}")]


def test_the_coulter_rows_candidates_are_padded_for_both_slugs():
    """The builder-C2b unit test pinned `sensors-8-02161` — the exact URL the real L074 row saw 404. Both slugs (the
    de-spaced venue and the DOI code) are now padded."""
    from litkb.acquire import landing as L

    page = L.Page("https://www.mdpi.com/1424-8220/8/4/2161", 403, {}, b"", "doi", "challenge_or_bot_check")
    cands, rules = L.candidates_for({"doi": "10.3390/s8042161", "venue": "Sensors"}, [page], [page.url],
                                    resolved=page.url)
    assert "mdpi" in rules
    assert [c.url for c in cands][:2] == [
        "https://mdpi-res.com/d_attachment/sensors/sensors-08-02161/article_deploy/sensors-08-02161.pdf",
        "https://mdpi-res.com/d_attachment/s/s-08-02161/article_deploy/s-08-02161.pdf"]


def _coulter():
    rec = H.load_recording("L074_coulter_mdpi", root=H.ROW_FIXTURES)       # every body re-checked by sha256
    assert rec["row"] == "L074" and rec["doi"] == "10.3390/s8042161"
    return rec


def test_the_coulter_fixture_is_the_run_recording_and_the_live_probe_is_the_files_first_4k():
    rec = _coulter()
    by_line = {h["provenance"].get("cassette_line"): h for h in rec["hops"]}
    assert set(by_line) >= {1601, 1602, 1603, 1604, 1605, 1609}
    assert [by_line[n]["response"]["status"] for n in (1601, 1602, 1603, 1604, 1605)] == [302, 403, 404, 404, 403]
    probe, whole = rec["hops"][5], rec["hops"][6]
    assert probe["response"]["status"] == 206 and "FX-C network grant" in probe["provenance"]["recorded_by"]
    assert probe["body"] == whole["body"][:4096] and len(whole["body"]) == 370175
    assert "PLACED" in whole["provenance"]["note"]


def _ctx(clients):
    from litkb.acquire.run import Budget, RungContext
    return RungContext(clients=clients, pacer=None, budget=Budget(), index={}, printer=lambda *a, **k: None)


def test_the_real_coulter_row_converts_through_the_landing_rung():
    """L074 (MEASURE row, Sensors vol 8) on its RECORDED answers: the doi.org 302, www.mdpi.com's Akamai 403, the two
    unpadded CDN 404s, the /pdf Akamai 403 — and at the padded CDN URL the FX-C live probe (206) and the whole file.
    On main 411c3ce the rung asks only the 404s and the 403 and ends blocked; here it downloads from the CDN."""
    from litkb.acquire import landing as L

    rec = _coulter()
    fc = H.FixtureClient(H.row_answers(rec))
    r = L.fetch_landing({"doi": rec["doi"], "venue": rec["venue"]}, _ctx({"landing": fc}))
    assert r["status"] == "downloaded", (r["status"], r.get("tried"))
    assert r["landing"]["source"] == "mdpi.cdn"
    assert r["pdf"] == rec["hops"][6]["body"]
    asked = [c["url"] for c in fc.calls]
    assert not any("sensors-8-02161" in u or "/s-8-02161" in u for u in asked)


# ── on a worker database ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def owner(litkb_pg_base):
    return litkb_pg_base[1]


@pg_only
def test_the_real_coulter_row_is_measured_through_the_ladder(owner, tmp_path):
    """L074 was a MEASURE row of the run (the work held a file): through THE REAL LADDER in MEASURE mode, route
    `landing` only, on the recorded answers (the CONSTRUCTED admission's salted DOI resolves through the row's own
    doi.org hop). Main 411c3ce: `landing` blocked/challenge_or_bot_check and mdpi_landings_unconverted=1 — the run's
    outcome; here: `landing` measured (the acceptance test judged MDPI's real file) and 0."""
    rec = _coulter()
    w = H.World(owner, tmp_path)
    try:
        work = w.work(title="A constructed Sensors article on the recorded Coulter row", author="Coulter",
                      venue=rec["venue"])
        fc = H.FixtureClient(H.row_answers(rec, rewrite_doi=(rec["doi"], work["doi"]), salt=True))
        w.acquire(work, {"landing": fc}, ("landing",), mode="measure")
        rows = [r for r in w.rows(work) if r[0] == "landing"]
        assert [(r[1], r[2]) for r in rows] == [("measured", None)], [(r[1], r[2]) for r in rows]
        assert rows[0][3]["landing"]["source"] == "mdpi.cdn"
        assert H.mdpi_landings_unconverted(owner, w.manifest()) == 0
        assert not w.holds_file(work)                                   # MEASURE mode lands nothing
    finally:
        w.close()


# ── 2. S4.5 decision D50 ──────────────────────────────────────────────────────────────────────
def _miller():
    rec = H.load_recording("L139_miller_doaj", root=H.ROW_FIXTURES)
    assert rec["row"] == "L139"
    return rec


def _doaj_client(rec):
    """doaj's two recorded answers: the DOAJ record (answered for any DOI asked — the admission is CONSTRUCTED) and
    the article page its fulltext link names, salted (a fresh sha per call: the rejected-hash lookup)."""
    api, page = rec["hops"]
    return H.FixtureClient({page["request"]["url"]: (page["response"]["status"], dict(page["response"]["headers"]),
                                                     H.salted(page["body"]))},
                           prefixes={"https://doaj.org/api/": (api["response"]["status"],
                                                               dict(api["response"]["headers"]), api["body"])})


def _binding_open_access(work, author):
    """A CONSTRUCTED Unpaywall record whose one location serves a CONSTRUCTED paper of the work's own title and
    author (binds: the `_mdpi_world` precedent) — the stand-in for the real row's PLOS printable PDF, which a
    CONSTRUCTED admission would refuse."""
    url = f"https://oa.example.org/{uuid.uuid4().hex[:8]}.pdf"
    paper = H.constructed_paper(work["title"], author, salt=uuid.uuid4().hex[:8])
    return H.FixtureClient({url: H._pdf_answer(paper)}, prefixes={"https://api.unpaywall.org/": H._unpaywall([url])})


@pg_only
def test_d50_a_page_beside_a_binding_in_the_same_run_is_excused_and_one_without_is_counted(owner, tmp_path):
    """The ruling's case on the REAL recorded doaj page of L139 (Miller_2013: the PLOS article page, carrying
    citation_pdf_url). Work A: open_access BINDS in the same concurrent Stage B wave as doaj, so the ladder stops
    before Stage C — the live run's shape. Work B, same run: the same page to doaj, Stage C disabled, nothing bound.
    Main 411c3ce counts both (2); the ruling counts B only (1), and the REPORTED landing_pages_excused_bound_in_run
    counts and names A (1)."""
    from litkb.acquire import run

    rec = _miller()
    w = H.World(owner, tmp_path)
    try:
        with H._no_email():
            a = w.work(title="A constructed article bound beside a recorded doaj page", author="Miller")
            w.acquire(a, {"open_access": _binding_open_access(a, "Miller"), "doaj": _doaj_client(rec),
                          "landing": H.FixtureClient({})}, ("open_access", "doaj", "landing"))
            b = w.work(title="A constructed article served only a recorded doaj page", author="Miller")
            w.acquire(b, {"doaj": _doaj_client(rec)}, ("doaj",), rungs=[g for g in run.RUNGS if g.route != "landing"])
        ra, rb = w.rows(a), w.rows(b)
        assert ("open_access", "ok") in [(r[0], r[1]) for r in ra] and w.holds_file(a)
        assert ("doaj", "bad-file", "html_response") in [(r[0], r[1], r[2]) for r in ra]
        assert not any(r[0] == "landing" for r in ra)                   # the ladder stopped at the binding
        assert ("doaj", "bad-file", "html_response") in [(r[0], r[1], r[2]) for r in rb] and not w.holds_file(b)
        assert not any(r[0] == "landing" for r in rb)                   # Stage C disabled for B
        assert all(r[3]["acceptance"]["facts"]["landing"]["pdf_pointer"] is True
                   for r in ra + rb if r[0] == "doaj")
        m = w.manifest()
        assert H.landing_pages_booked_bad_file(owner, m) == 1
        (counted,) = H.DETAILS["landing_pages_booked_bad_file"](owner, m)
        assert b["key"] in counted and a["key"] not in counted
        # the excused page is COUNTED and NAMED by its own reported counter, never silent
        assert H.landing_pages_excused_bound_in_run(owner, m) == 1
        (excused,) = H.DETAILS["landing_pages_excused_bound_in_run"](owner, m)
        assert a["key"] in excused and "S4.5 decision D50" in excused
    finally:
        w.close()


@pg_only
def test_d50_a_binding_before_the_run_does_not_excuse_a_page(owner, tmp_path):
    """The ruling excuses a binding IN THE RUN only: the work bound by open_access, THEN the run frozen, THEN the
    recorded doaj page served with Stage C disabled — the page is counted (1)."""
    from litkb.acquire import run

    rec = _miller()
    w = H.World(owner, tmp_path)
    try:
        with H._no_email():
            a = w.work(title="A constructed article bound before the run froze", author="Miller")
            w.acquire(a, {"open_access": _binding_open_access(a, "Miller")}, ("open_access",))
            assert w.holds_file(a)
            w.frozen = owner.execute("SELECT clock_timestamp()").fetchone()[0]
            w.acquire(a, {"doaj": _doaj_client(rec)}, ("doaj",), rungs=[g for g in run.RUNGS if g.route != "landing"])
        assert ("doaj", "bad-file", "html_response") in [(r[0], r[1], r[2]) for r in w.rows(a)]
        assert H.landing_pages_booked_bad_file(owner, w.manifest()) == 1
        assert H.landing_pages_excused_bound_in_run(owner, w.manifest()) == 0
    finally:
        w.close()


@pg_only
def test_d50_only_the_runs_own_live_binding_excuses_a_page(owner, tmp_path):
    """auditor-FX-C F1 (S4.5 decision D58, integrator-w4): the exclusion's two clauses no test held (their AUD4, AUD5).
    Work A is bound by open_access in the same run as its RECORDED doaj page (L139's), so the page is excused (0
    counted). Then CONSTRUCTED edits of A's binding, by the owner on the worker database: (a) the file version moved to
    ANOTHER workstream (a binding after the freeze that is not the run's) -> the page counts (1); (b) back in the run's
    workstream but `rejected` -> counts (1); (c) its own state but `quarantined` (not active) -> counts (1)."""
    rec = _miller()
    w = H.World(owner, tmp_path)
    try:
        with H._no_email():
            a = w.work(title="A constructed article bound beside a recorded doaj page", author="Miller")
            w.acquire(a, {"open_access": _binding_open_access(a, "Miller"), "doaj": _doaj_client(rec),
                          "landing": H.FixtureClient({})}, ("open_access", "doaj", "landing"))
        assert w.holds_file(a)
        m = w.manifest()
        assert (H.landing_pages_booked_bad_file(owner, m), H.landing_pages_excused_bound_in_run(owner, m)) == (0, 1)
        (fv_id, state, status, promoted_at) = owner.execute(
            "SELECT version_id, state, status, promoted_at FROM litkb.file_versions WHERE work_id = %s "
            "AND created_at > %s",
            (a["work_id"], w.frozen)).fetchone()
        other = owner.execute("SELECT workstream_id FROM litkb.open_workstream(%s, 'work/c2b-fire', NULL, %s, NULL)",
                              (f"fxc-other-{uuid.uuid4().hex[:8]}", "CONSTRUCTED: another workstream")).fetchone()[0]
        for sets, args in (("workstream_id = %s", (other,)),
                           ("workstream_id = %s, state = 'rejected', promoted_at = NULL", (w.ws_id,)),
                           ("workstream_id = %s, state = %s, promoted_at = %s, status = 'quarantined'",
                            (w.ws_id, state, promoted_at))):
            owner.execute(f"UPDATE litkb.file_versions SET {sets} WHERE version_id = %s", (*args, fv_id))
            assert H.landing_pages_booked_bad_file(owner, m) == 1, sets
            assert H.landing_pages_excused_bound_in_run(owner, m) == 0, sets
        owner.execute("UPDATE litkb.file_versions SET workstream_id = %s, state = %s, promoted_at = %s, status = %s "
                      "WHERE version_id = %s", (w.ws_id, state, promoted_at, status, fv_id))
        assert H.landing_pages_booked_bad_file(owner, m) == 0                # restored: excused again
    finally:
        w.close()


def test_d50_the_gate_reads_the_bound_flag_the_sql_selects():
    """Pure: the gate's `_gated` split is the SQL's `bound_in_run` column and nothing else (a CONSTRUCTED row pair,
    the column layout `_LANDING_BAD_FILE_SQL` selects)."""
    assert "AS bound_in_run" in H._LANDING_BAD_FILE_SQL
    cols = H._LANDING_BAD_FILE_SQL.split("FROM litkb.acquisition_attempts a")[0]
    assert cols.rstrip().endswith("AS bound_in_run")                     # the 12th column, row[11]

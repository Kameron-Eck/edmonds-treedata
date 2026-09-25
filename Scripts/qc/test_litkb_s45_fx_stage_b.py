"""litkb S4.5 fix wave, builder FX-B — Stage B's three REJECT findings of referee-stage-b (brief-FIXWAVE.md "FX-B";
Reports/LITKB_REFEREE_S45_STAGE-B_2026-09-24.md N1, N2, N3), each reproduced on the ladder-1 run's RECORDED bytes:

  item 1  B9 `openaire` took PDF candidates from the answer's `<rels>` subtree — OTHER works OpenAIRE relates to the
          asked one (`IsAmongTopNSimilarDocuments`, `hasAuthorInstitution`) — and asked them FIRST: rows L074 L090 L150
          L080 L102 L168 L170 (and L161, the eighth such answer, whose `<rels>` arXiv URL the rung turned into an arXiv
          id for the work). Replayed: the eight recorded OpenAIRE answers.
  item 2  `crosswalk_rows_without_identifier=17`: the ladder's first-landing stop cut Stage B's Wave 2 short, so the
          identifier services after a Wave-1 landing (S2 among them) were never asked. Replayed: L082 Polunchenko_2011's
          whole recorded take (Unpaywall named the arXiv copy and open_access landed it at Wave 1).
  item 3  Kats_2019 (L005, register E03): the right arXiv bytes were refused `duplicate-held` by the disk dedupe
          against a copy NO `files` row holds (`Validation/Kats_2019b_soft-staple-algorithm-combined.pdf`). Replayed:
          L005's recorded Semantic Scholar answer; the arXiv PDF's REAL bytes from the untracked cassette body store
          when this machine holds them (a PDF never enters the repository), and a CONSTRUCTED twin that always runs.

The recordings are `qc/fixtures/litkb_cassettes/stage_b_fx/` (index lines and stored bodies copied BYTE FOR BYTE from
the run's index and body store; `provenance.json` names each entry's run row, cassette key sha256, take and body
sha256). Every answer that is not a recording is CONSTRUCTED and says so. No test touches the network.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w3 py -3.12 -m pytest qc/test_litkb_s45_fx_stage_b.py -q
"""
import base64
import csv
import hashlib
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
FIX = SCRIPTS / "qc" / "fixtures" / "litkb_cassettes" / "stage_b_fx"
INDEX, BODIES = FIX / "index.jsonl", FIX / "bodies"
pg_only = pytest.mark.requires_litkb_pg


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C2A = _load("_litkb_hardening_c2a_fxb", SCRIPTS / "qc" / "instruments" / "litkb_hardening_c2a.py")
B1 = _load("_litkb_hardening_b1_fxb", SCRIPTS / "qc" / "instruments" / "litkb_hardening_b1.py")


@pytest.fixture(autouse=True)
def _no_email(monkeypatch):
    """No test reads Kam's configured email: the contact email is a constructed address."""
    from litkb.acquire import open_access
    monkeypatch.setattr(open_access, "unpaywall_email", lambda: "fxb-test@example.invalid")


# ── the recordings ─────────────────────────────────────────────────────────────────────────────────
def _entries():
    """The fixture's recorded interactions (index lines after the header), each with its body bytes, sha-checked."""
    out = []
    for ln in INDEX.read_bytes().splitlines()[1:]:
        e = json.loads(ln)
        b = e["response"]["body"]
        body = base64.b64decode(b["inline_b64"]) if "inline_b64" in b else \
            (BODIES / b["sha256"][:2] / (b["sha256"] + ".bin")).read_bytes()
        assert hashlib.sha256(body).hexdigest() == b["sha256"], e["key"]["url"]
        out.append((e, body))
    return out


def _recorded(row, url_prefix):
    got = [(e, body) for e, body in _entries() if e["row"] == row and e["key"]["url"].startswith(url_prefix)]
    assert len(got) == 1, (row, url_prefix, len(got))
    return got[0]


def ReplayClient(row, stubs=None):
    """Builder C2a's replay client (`litkb_hardening_c2a.ReplayClient`: builder A's cassette under one row tag, the
    request key the live run recorded) over THIS fixture's index and bodies; `stubs` are CONSTRUCTED answers for URLs
    never recorded or PDFs. A request neither answers is the cassette's own CassetteMiss, never the network."""
    return C2A.ReplayClient(row, stubs=stubs, index=INDEX, bodies=BODIES)


class Ctx:
    """A CONSTRUCTED RungContext stand-in for the rung tests: clients by route, a pacer that never sleeps."""

    def __init__(self, clients=None, harvest_only=False):
        from litkb.netutil import Pacer
        self.clients = clients or {}
        self.pacer = Pacer(interval=0, sleep=lambda s: None)
        self.work_class = ""
        self.harvest_only = harvest_only


class Stub:
    """Answers by URL fragment (CONSTRUCTED); an unknown URL is a 404. Records every URL asked."""
    base = ""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        for frag, resp in self.routes.items():
            if frag in url:
                return resp
        return 404, {}, b""


# ── item 1: B9 OpenAIRE never takes another work's URL ────────────────────────────────────────────────
#: referee-stage-b N1's seven rows and the eighth recorded answer with a PDF under <rels> (L161 Ro_2020: an arXiv URL
#: there is ANOTHER work's arXiv id), by the row tag the run recorded under -> (run row, what the run did with it)
OPENAIRE_ROWS = {
    "10.3390/s8042161": ("L074", "measured: another work's PDF (Narendran et al. 2014) credited as a conversion"),
    "10.1016/j.isprsjprs.2021.10.008": ("L090", "measured: another paper by the same authors credited"),
    "10.3390/rs12091505": ("L150", "binding-failed: MacGregor et al. 2020 quarantined"),
    "10.1007/s10661-021-08898-2": ("L080", "blocked: a bioRxiv preprint of another work"),
    "10.1016/j.rse.2020.112244": ("L102", "blocked: another MDPI article"),
    "10.48550/arxiv.0710.3980": ("L168", "blocked: a Hindawi AAA 2007 article"),
    "10.48550/arxiv.1909.10155": ("L170", "blocked: a Kiel technical report"),
    "10.48550/arxiv.2002.06048": ("L161", "arXiv 1908.02735 (another work) held as the work's arXiv id in the run"),
}
#: The control: L092 Canty_2008, whose own OpenAIRE PDF the run bound (referee-stage-b: CORRECT, 12 pp).
OPENAIRE_CONTROL = "10.1016/j.rse.2007.07.013"


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _oracle(xml):
    """THE TEST'S OWN READING of an OpenAIRE answer, written independently of the rung (referee X9: a gate is never
    scored by its own detector): -> (the asked result's own http URLs in document order, the URLs that appear ONLY
    under a `rels` element — other works)."""
    own, rel = [], []

    def walk(el, in_rels):
        in_rels = in_rels or _local(el.tag) == "rels"
        if _local(el.tag) in ("url", "webresource") and (el.text or "").strip().startswith("http"):
            (rel if in_rels else own).append(el.text.strip())
        for ch in el:
            walk(ch, in_rels)
    walk(ET.fromstring(xml), False)
    return list(dict.fromkeys(own)), [u for u in dict.fromkeys(rel) if u not in set(own)]


def _pdfish(u):
    return u.lower().endswith(".pdf") or "/pdf" in u.lower()


def test_the_fixture_is_the_run_s_recording():
    """The fixture's provenance names the run it was copied from, and every entry's body hashes to its recorded
    sha256 (`_entries` checks each); the eight N1 answers and the control are all there, 200 each."""
    prov = json.loads((FIX / "provenance.json").read_text(encoding="utf-8"))
    assert prov["source_index"].endswith("ladder-1\\index.jsonl") or prov["source_index"].endswith("ladder-1/index.jsonl")
    rows = {e["row"] for e, _b in _entries() if e["key"]["url"].startswith("https://api.openaire.eu/")}
    assert rows == set(OPENAIRE_ROWS) | {OPENAIRE_CONTROL, POLUNCHENKO["doi"]}, rows
    assert {p["run_row"] for p in prov["entries"]} == {v[0] for v in OPENAIRE_ROWS.values()} | {"L092", "L082", "L005"}
    assert [p["url"] for p in prov["entries"] if p.get("skipped")] == ["https://arxiv.org/pdf/1109.2938"]
    assert all(e["response"]["status"] == 200 for e, _b in _entries())


@pytest.mark.parametrize("row", sorted(OPENAIRE_ROWS))
def test_openaire_takes_no_url_from_the_rels_subtree_of_a_recorded_answer(row):
    """The parser returns none of the URLs the answer lists ONLY under `<rels>` (other works), and loses none of the
    asked result's own PDF URLs."""
    from litkb.acquire import stage_b_repos as R

    _e, xml = _recorded(row, "https://api.openaire.eu/")
    own, rels = _oracle(xml)
    assert [u for u in rels if _pdfish(u)], f"{row}: the recording has no <rels> PDF — not the N1 case"
    pdf, other = R.openaire_urls(xml)
    leaked = sorted(set(pdf + other) & set(rels))
    assert leaked == [], f"{row} ({OPENAIRE_ROWS[row][0]}): another work's URL taken from <rels>: {leaked[:3]}"
    assert [u for u in own if _pdfish(u)] == pdf, (row, pdf)


@pytest.mark.parametrize("row", sorted(OPENAIRE_ROWS))
def test_the_openaire_rung_never_asks_another_work_s_pdf_on_the_recorded_answer(row):
    """The rung on the RECORDED answer (every PDF request answered 404, CONSTRUCTED): no request goes to a URL the
    answer lists only under `<rels>`, the work's own PDFs are asked first, and no arXiv id is taken from `<rels>`."""
    from litkb.acquire import stage_a as A
    from litkb.acquire import stage_b_repos as R

    entry, xml = _recorded(row, "https://api.openaire.eu/")
    own, rels = _oracle(xml)
    stub = Stub({"api.openaire.eu/": (200, entry["response"]["headers"], xml)})
    work = {"doi": row, "ids": [], "asked_urls": {}}
    r = R.rung_openaire(work, Ctx({"openaire": stub}))
    asked = [u for u in stub.calls if "api.openaire.eu/" not in u]
    assert not set(asked) & set(rels), f"{row} ({OPENAIRE_ROWS[row]}): asked {sorted(set(asked) & set(rels))}"
    own_pdfs = [u for u in own if _pdfish(u) and "arxiv.org/" not in u]
    assert asked == own_pdfs, (row, asked, own_pdfs)
    rel_arxiv = {a for a in (C2A._stage_b().canon_arxiv(u) for u in rels) if a}
    assert not rel_arxiv & set(A.ids_of(work, "arxiv")), (row, A.ids_of(work, "arxiv"))
    if not own_pdfs:
        assert r["status"] == "no-oa-copy", (row, r)


def test_the_openaire_rung_still_asks_the_pdf_it_converted_in_the_run():
    """The control, L092 Canty_2008: the rung still asks the asked result's own PDF (the one the run bound)."""
    from litkb.acquire import stage_b_repos as R

    entry, xml = _recorded(OPENAIRE_CONTROL, "https://api.openaire.eu/")
    own, _rels = _oracle(xml)
    stub = Stub({"api.openaire.eu/": (200, entry["response"]["headers"], xml)})
    R.rung_openaire({"doi": OPENAIRE_CONTROL, "ids": [], "asked_urls": {}}, Ctx({"openaire": stub}))
    asked = [u for u in stub.calls if "api.openaire.eu/" not in u]
    assert asked and asked == [u for u in own if _pdfish(u)], asked


# ── item 2: the identifier waves complete after a landing; the file rungs still stop ────────────────
def test_a_harvest_only_call_asks_no_candidate_and_says_which_it_left():
    """CONSTRUCTED: a Stage B rung asked in HARVEST-ONLY mode (after the ladder landed the file) hands back its
    service's answer, asks none of its PDF candidates, and names every one it did not ask — never a silent miss; a
    candidate another rung already asked in the run is named as that rung's, as in a full ask."""
    from litkb.acquire import stage_b as B

    stub = Stub({"x.invalid": (200, {}, b"%PDF-1.4 CONSTRUCTED")})
    work = {"doi": "10.5555/fxb.constructed", "ids": [], "asked_urls": {"https://y.invalid/a.pdf": "open_access"}}
    term = {"url": "https://api.example.invalid/record", "status_code": 200, "at": None}
    r = B.answered("s2", [("https://x.invalid/b.pdf", {}), ("https://y.invalid/a.pdf", {})],
                   Ctx({"s2": stub}, harvest_only=True), work, term=term)
    assert stub.calls == [], stub.calls
    assert r["status"] == "no-oa-copy" and r["http_codes"] == [200] and r["retriable"] is True, r
    assert r["harvest_only"]["not_asked"] == ["https://x.invalid/b.pdf"], r
    assert "already asked in this ladder run by open_access" in r["detail"], r
    full = B.answered("s2", [("https://x.invalid/b.pdf", {})], Ctx({"s2": stub}), dict(work, asked_urls={}), term=term)
    assert stub.calls == ["https://x.invalid/b.pdf"] and full["status"] == "downloaded", full


def test_the_registry_marks_exactly_the_harvesting_rungs():
    """The rungs asked after a landing are the Stage B rungs whose answer carries a harvest, and no other: never a
    Stage A, C, E or shadow rung, never a rung that only fetches files."""
    from litkb.acquire import run as R
    from litkb.acquire import stage_b as B

    marked = {r.route for r in R.RUNGS if r.harvests}
    assert marked == set(B.HARVESTS) == {"opencitations", "crossref-link", "openalex", "datacite", "ncbi-idconv",
                                         "s2", "europepmc"}, marked
    assert {r.stage for r in R.RUNGS if r.harvests} == {"B"}


def _reset_and_migrate(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


@pytest.fixture(scope="module")
def pgc(litkb_pg_base):
    """The shared worker database, RESET AND MIGRATED before this module's first database test and after its last
    (brief-COMMON rule 5: these tests admit REAL keys and DOIs — Polunchenko_2011, Kats_2019)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset_and_migrate(conn)
    yield conn
    _reset_and_migrate(conn)


#: L082 as the LIVE base holds it (read 2026-09-24 as litkb_reader), admitted on the worker database as a
#: CONSTRUCTED registry admission (C2A.World.admit).
POLUNCHENKO = {"key": "Polunchenko_2011_state-art-sequential-change", "doi": "10.1007/s11009-011-9256-5",
               "type": "article", "title": "State-of-the-Art in Sequential Change-Point Detection",
               "author": "Polunchenko", "year": 2011}
#: CONSTRUCTED: an open-access PDF URL no recording holds, for the S2 answer below — a candidate the harvest-only call
#: must NOT ask.
S2_CANDIDATE = "https://fxb.example.invalid/constructed-open-access.pdf"


def _crosswalk_row(key):
    with open(REPO / "phase4" / "qc" / "litkb_acq_probe_crosswalk.csv", encoding="utf-8", newline="") as f:
        return next(r for r in csv.DictReader(f) if r["key"] == key)


def _constructed_s2(row):
    """CONSTRUCTED: Semantic Scholar's answer for L082, built from the crosswalk probe CSV's MEASURED S2 values for
    that work (2026-09-22: `s2_arxiv`, `s2_corpus`, `s2_mag`) — the run never asked S2 for it (the defect), so no
    recording exists. Its openAccessPdf is a CONSTRUCTED non-arXiv URL."""
    cw = _crosswalk_row(row["key"])
    return {"paperId": "CONSTRUCTED-fxb-l082",
            "externalIds": {"ArXiv": cw["s2_arxiv"], "DOI": row["doi"], "CorpusId": int(cw["s2_corpus"]),
                            "MAG": cw["s2_mag"]},
            "title": row["title"], "year": row["year"],
            "openAccessPdf": {"url": S2_CANDIDATE, "status": "GREEN", "license": None}}


def _json(obj):
    return 200, {"Content-Type": "application/json"}, json.dumps(obj).encode()


def _stage_ab_routes():
    from litkb.acquire import policy as P
    from litkb.acquire import run as R
    return tuple(r for r in R.ladder_routes() if P.STAGE_OF[r] in ("A", "B"))


def _manifest(ws, frozen, key):
    return {"repo": str(REPO), "frozen_at": frozen, "run_workstream_ids": [ws],
            "probe_csvs": {"litkb_acq_probe_crosswalk.csv": str(REPO / "phase4" / "qc" / "litkb_acq_probe_crosswalk.csv")},
            "rows": [{"key": key, "source": ["crosswalk"]}]}


@pg_only
def test_a_wave_1_landing_still_completes_the_identifier_waves_on_l082(pgc, tmp_path):
    """L082 Polunchenko_2011, one of referee-stage-b N2's 17 rows, on its RECORDED ladder-1 take (Unpaywall, Crossref,
    OpenAlex, OpenCitations, DOAJ, HAL, OpenAIRE and the Springer pages, byte for byte). Unpaywall names the arXiv copy,
    open_access lands it at Wave 1 (the PDF's bytes CONSTRUCTED: a PDF never enters the repository). The run then
    stopped: S2 was never asked and the crosswalk's arXiv 1109.2938 never arrived. Now the identifier services after
    the landing are asked in HARVEST-ONLY mode — S2 (CONSTRUCTED answer from the probe CSV's measured values) and the
    NCBI converter (CONSTRUCTED 'not found') — and the file rungs are not: no `arxiv`, `venue` or other file request
    after the landing, and S2's own PDF candidate is named, never asked."""
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("fxb-l082")
        work = w.admit(ws, POLUNCHENKO)
        frozen = w.now()
        pdf = C2A.constructed_pdf(POLUNCHENKO["title"], "A. S. Polunchenko")
        client = ReplayClient(POLUNCHENKO["doi"], stubs={
            "arxiv.org/pdf/1109.2938": (200, {"Content-Type": "application/pdf"}, pdf),
            "api.semanticscholar.org/": _json(_constructed_s2(POLUNCHENKO)),
            "pmc.ncbi.nlm.nih.gov/tools/idconv/": _json({"status": "ok", "records": [
                {"doi": POLUNCHENKO["doi"], "status": "error", "errmsg": "CONSTRUCTED: invalid article id"}]})})
        routes = _stage_ab_routes()
        out = w.acquire(ws, work, {r: client for r in routes}, routes=routes)
        C2A.no_misses(client)
        assert out["outcome"] == "ok", out
        rows = pgc.execute("SELECT route, status, detail FROM litkb.acquisition_attempts WHERE work_id = %s "
                           "ORDER BY at, id", (work["work_id"],)).fetchall()
        by = {}
        for route, status, detail in rows:
            by.setdefault(route, []).append((status, detail))
        assert [s for s, _d in by["open_access"]] == ["ok"], by["open_access"]
        s2 = by.get("s2") or []
        assert [s for s, _d in s2] == ["no-oa-copy"], f"S2 never asked after the Wave-1 landing: {sorted(by)}"
        assert s2[0][1]["harvest_only"]["not_asked"] == [S2_CANDIDATE], s2[0][1]
        assert s2[0][1]["harvest"]["relations"] >= 1, s2[0][1]
        assert S2_CANDIDATE not in client.calls, client.calls
        assert "ncbi-idconv" in by and "arxiv" not in by and "venue" not in by, sorted(by)
        after = client.calls[client.calls.index("https://arxiv.org/pdf/1109.2938") + 1:]
        assert not [u for u in after if "arxiv.org/pdf/" in u], after
        m = _manifest(ws, frozen, POLUNCHENKO["key"])
        assert B1.crosswalk_missing(pgc, m) == [], B1.crosswalk_missing(pgc, m)
        # the yield lines: a harvest-only row that left a candidate unasked is no ask of the rung's FILE; one that was
        # listed none is a full answer (a metadata-only rung's row is one)
        assert C2A.rung_counts(pgc, m, "s2") == (0, 0), C2A.rung_counts(pgc, m, "s2")
        assert C2A.rung_counts(pgc, m, "ncbi-idconv") == (0, 1), C2A.rung_counts(pgc, m, "ncbi-idconv")
        assert C2A.rung_counts(pgc, m, "open_access") == (1, 1), C2A.rung_counts(pgc, m, "open_access")
    finally:
        w.close()
        _reset_and_migrate(pgc)


@pg_only
def test_a_ladder_that_lands_at_wave_2_never_asks_a_rung_twice(pgc, tmp_path):
    """CONSTRUCTED world, Kats_2019's RECORDED S2 answer: S2 is asked BEFORE the arXiv rung lands, so the landing
    leaves no identifier rung unvisited — nothing is asked a second time, and the ledger holds one row per rung."""
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("fxb-once")
        work = w.admit(ws, C2A.ROWS["kats"])
        pdf = C2A.constructed_pdf(C2A.ROWS["kats"]["title"], C2A.ROWS["kats"]["author"])
        client = ReplayClient(C2A.ROWS["kats"]["doi"], stubs={"arxiv.org/pdf/1910.12077": (200, {}, pdf)})
        out = w.acquire(ws, work, {"s2": client, "arxiv": client, "ncbi-idconv": client}, routes=("s2", "arxiv"))
        C2A.no_misses(client)
        assert out["outcome"] == "ok", out
        got = pgc.execute("SELECT route, status FROM litkb.acquisition_attempts WHERE work_id = %s ORDER BY at, id",
                          (work["work_id"],)).fetchall()
        assert got == [("s2", "no-oa-copy"), ("arxiv", "ok")], got
    finally:
        w.close()
        _reset_and_migrate(pgc)


@pg_only
def test_a_harvest_rung_the_loop_skipped_is_never_reached_again_by_the_pass(pgc, tmp_path):
    """auditor-FX-B r2 N-A (S4.5 decision D58, integrator-w4): "a rung the loop reached, asked OR SKIPPED, is never
    asked twice" — the skipped half. CONSTRUCTED world, Kats_2019's RECORDED S2 answer, the ladder narrowed to
    DataCite, S2, Europe PMC and arXiv: DataCite and Europe PMC skip `no_identifier` (Kats holds no DataCite DOI, no
    PMID/PMCID) before the arXiv rung lands at Wave 2. The post-landing pass must not reach them again: one row per
    route, the two skips written once."""
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("fxb-skipped-once")
        work = w.admit(ws, C2A.ROWS["kats"])
        pdf = C2A.constructed_pdf(C2A.ROWS["kats"]["title"], C2A.ROWS["kats"]["author"])
        client = ReplayClient(C2A.ROWS["kats"]["doi"], stubs={"arxiv.org/pdf/1910.12077": (200, {}, pdf)})
        routes = ("datacite", "s2", "europepmc", "arxiv")
        out = w.acquire(ws, work, {r: client for r in routes + ("ncbi-idconv",)}, routes=routes)
        C2A.no_misses(client)
        assert out["outcome"] == "ok", out
        got = pgc.execute("SELECT route, status, sub_status FROM litkb.acquisition_attempts WHERE work_id = %s "
                          "ORDER BY at, id", (work["work_id"],)).fetchall()
        by = {}
        for route, st, sub in got:
            by.setdefault(route, []).append((st, sub))
        assert by.get("datacite") == [("skipped", "no_identifier")], got
        assert by.get("europepmc") == [("skipped", "no_identifier")], got
        assert all(len(v) == 1 for v in by.values()) and by.get("arxiv") == [("ok", None)], got
    finally:
        w.close()
        _reset_and_migrate(pgc)


# ── item 2, fix round 2 (auditor-FX-B F2): the pass's skip, budget and duplicate-held branches, each reached ────
# The pass runs through the ladder's OWN stage loop (`run_stages` in run.acquire) since round 2 — round 1 had a copy
# of it that no test reached. These three pin what the pass does under each branch on L082's recorded take.
#: the harvest rungs L082's ladder had not reached at its Wave-1 landing, in registry order (the pass's rungs)
L082_PASS = ["datacite", "ncbi-idconv", "s2", "europepmc"]


def _l082_client(pdf):
    """L082's RECORDED take, plus the CONSTRUCTED answers the run never had (the arXiv PDF, S2, NCBI)."""
    return ReplayClient(POLUNCHENKO["doi"], stubs={
        "arxiv.org/pdf/1109.2938": (200, {"Content-Type": "application/pdf"}, pdf),
        "api.semanticscholar.org/": _json(_constructed_s2(POLUNCHENKO)),
        "pmc.ncbi.nlm.nih.gov/tools/idconv/": _json({"status": "ok", "records": [
            {"doi": POLUNCHENKO["doi"], "status": "error", "errmsg": "CONSTRUCTED: invalid article id"}]})})


def _ladder_rows(pgc, work):
    """(route, status, sub_status, detail) of every attempt row of the work, in the order written."""
    return pgc.execute("SELECT route, status, sub_status, detail FROM litkb.acquisition_attempts WHERE work_id = %s "
                       "ORDER BY at, id", (work["work_id"],)).fetchall()


def _need_pdftotext():
    import shutil
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext is not installed: binding cannot read a first page")


@pg_only
def test_the_post_landing_pass_skips_a_harvest_rung_blocked_earlier_in_the_run(pgc, tmp_path):
    """auditor-FX-B F2 (a). L082 on its recorded take, with S2 `blocked` EARLIER IN THIS RUN (a CONSTRUCTED
    challenge row in the same workstream, not retriable). After the Wave-1 landing the pass reaches S2 and its skip
    reason stands: S2 is written `skipped/dead_in_run`, stamped `harvest_only`, and asked NOTHING; the pass's other
    rungs are asked as without it (NCBI answers)."""
    from litkb.acquire import run as R
    from litkb.acquire import stage_b as B

    _need_pdftotext()
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("fxb-l082-dead")
        work = w.admit(ws, POLUNCHENKO)
        R.record_attempt(w.writer, ws, w.tokens[ws], work["work_id"], "s2", POLUNCHENKO["doi"], "blocked",
                         {"note": "CONSTRUCTED: a challenge page earlier in this run"}, [403],
                         sub_status="challenge_or_bot_check", retriable=False)
        client = _l082_client(C2A.constructed_pdf(POLUNCHENKO["title"], "A. S. Polunchenko"))
        routes = _stage_ab_routes()
        out = w.acquire(ws, work, {r: client for r in routes}, routes=routes)
        rows = _ladder_rows(pgc, work)
        s2 = [(st, sub, d) for route, st, sub, d in rows if route == "s2"]
        assert [(st, sub) for st, sub, _d in s2] == [("blocked", "challenge_or_bot_check"), ("skipped", "dead_in_run")], \
            f"S2, blocked earlier in the run, must be reached by the pass and skipped dead_in_run: " \
            f"{[(st, sub) for st, sub, _d in s2]}"
        assert (s2[1][2].get("harvest_only") or {}).get("why") == B.HARVEST_ONLY_WHY, s2[1][2]
        assert not [u for u in client.calls if "api.semanticscholar.org/" in u], client.calls
        assert [(route, st) for route, st, _s, _d in rows if route == "ncbi-idconv"] == [("ncbi-idconv", "no-oa-copy")]
        C2A.no_misses(client)
        assert out["outcome"] == "ok", out
    finally:
        w.close()
        _reset_and_migrate(pgc)


@pg_only
@pytest.mark.parametrize("extra", [0, 1])
def test_the_post_landing_pass_stops_at_the_ladder_budget(pgc, tmp_path, extra):
    """auditor-FX-B F2 (b). L082 on its recorded take, the ladder's attempts budget set to what the ladder SPENT up
    to its Wave-1 landing (MEASURED here on the same take, unbudgeted, first) plus `extra`. extra=0: the budget is spent
    at the landing — the pass writes ONE `budget-stop` naming every harvest rung it had left (stamped `harvest_only`)
    and makes no request. extra=1: DataCite skips itself on L082 (not a 10.48550 / 10.5281 / 10.6084 DOI: no spend),
    NCBI spends the last attempt, and the stop names S2 and Europe PMC, which are never asked. The landing stands."""
    from litkb.acquire import backoff as BO
    from litkb.acquire import policy as P
    from litkb.acquire import stage_b as B

    _need_pdftotext()
    pdf = C2A.constructed_pdf(POLUNCHENKO["title"], "A. S. Polunchenko")
    routes = _stage_ab_routes()

    def take(slug, **kw):
        _reset_and_migrate(pgc)
        w = C2A.World(pgc, tmp_path / slug)
        try:
            ws = w.ws(slug)
            work = w.admit(ws, POLUNCHENKO)
            client = _l082_client(pdf)
            out = w.acquire(ws, work, {r: client for r in routes}, routes=routes, **kw)
            C2A.no_misses(client)
            return out, _ladder_rows(pgc, work), client
        finally:
            w.close()

    try:
        out, rows, _c = take("fxb-l082-unbudgeted")
        assert out["outcome"] == "ok", out
        loop = [r for r in rows if "harvest_only" not in (r[3] or {})]
        assert [r[0] for r in rows if "harvest_only" in (r[3] or {})] == L082_PASS, \
            f"the pass's rows cannot be told from the loop's: {[(r[0], r[1], 'harvest_only' in (r[3] or {})) for r in rows]}"
        spent = sum(1 for r in loop if r[1] not in BO.NON_SPEND_STATUSES)
        out, rows, client = take("fxb-l082-budget", ladder_budget=P.LadderBudget(attempts=spent + extra))
        assert out["outcome"] == "ok", out
        stops = [r for r in rows if r[1] == "budget-stop"]
        left = L082_PASS if extra == 0 else ["s2", "europepmc"]
        assert [(r[0], r[2], r[3].get("not_asked")) for r in stops] == [("ladder", "budget_attempts", left)], \
            f"the pass went past the ladder budget: {[(r[0], r[1], r[2]) for r in rows]}"
        assert (stops[0][3].get("harvest_only") or {}).get("why") == B.HARVEST_ONLY_WHY, stops[0][3]
        assert not {r[0] for r in rows} & set(left), [(r[0], r[1]) for r in rows]
        assert not [u for u in client.calls if "api.semanticscholar.org/" in u], client.calls
        assert ("idconv" in " ".join(client.calls)) == (extra == 1), client.calls
    finally:
        _reset_and_migrate(pgc)


@pg_only
def test_a_duplicate_held_stop_still_completes_the_identifier_waves(pgc, tmp_path):
    """auditor-FX-B F2 (c) / N3. L082 on its recorded take, the arXiv bytes open_access downloads already HELD by a
    `files` row of ANOTHER work (a CONSTRUCTED twin record: same title and first author, its own key and DOI, the
    bytes bound to it first). The ladder stops at `duplicate-held` as it did; the identifier waves still complete —
    S2 is asked HARVEST-ONLY (its candidate named, never requested) and the crosswalk's arXiv id arrives. The pass
    runs on this stop by builder-FX-B's choice (the orchestrator may rule it `ok`-only; this test then flips)."""
    from litkb.acquire import run as R

    _need_pdftotext()
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws("fxb-l082-dup")
        frozen = w.now()
        pdf = C2A.constructed_pdf(POLUNCHENKO["title"], "A. S. Polunchenko")
        twin = w.admit(ws, dict(POLUNCHENKO, key="Polunchenko_2011_fxb-constructed-twin",
                                doi="10.5555/fxb.constructed.polunchenko-twin"))
        st, _d = R.land_and_attach(w.writer, ws, w.tokens[ws], twin, pdf, route="open_access",
                                   source_url="CONSTRUCTED twin's copy", store=w.store,
                                   index=R.index_of_held(w.store, w.store.disk_index()), agent="fxb", session="fxb-twin")
        assert st == "ok", (st, _d)
        work = w.admit(ws, POLUNCHENKO)
        client = _l082_client(pdf)
        routes = _stage_ab_routes()
        out = w.acquire(ws, work, {r: client for r in routes}, routes=routes)
        C2A.no_misses(client)
        assert out["outcome"] == "duplicate-held" and out["detail"]["held_for_work"] == str(twin["work_id"]), out
        rows = _ladder_rows(pgc, work)
        s2 = [(st, d) for route, st, _s, d in rows if route == "s2"]
        assert [st for st, _d in s2] == ["no-oa-copy"], \
            f"S2 never asked after the duplicate-held stop: {[(r[0], r[1]) for r in rows]}"
        assert s2[0][1]["harvest_only"]["not_asked"] == [S2_CANDIDATE], s2[0][1]
        assert S2_CANDIDATE not in client.calls, client.calls
        m = _manifest(ws, frozen, POLUNCHENKO["key"])
        assert B1.crosswalk_missing(pgc, m) == [], B1.crosswalk_missing(pgc, m)
    finally:
        w.close()
        _reset_and_migrate(pgc)


# ── item 3: only bytes a `files` row holds make a duplicate ──────────────────────────────────────────
KATS_SHA = "d54e42ec8dee5e3f0193afe7c168fa2247d8fd6a9ab8c6a627d01cac672d8ae7"
#: the live run's unowned copy (ladder-1 attempt 01a0d28f-6533's `on_disk`, read as litkb_reader 2026-09-24)
KATS_ON_DISK = "Validation/Kats_2019b_soft-staple-algorithm-combined.pdf"


def _kats_bytes(kind):
    if kind == "constructed":
        return C2A.constructed_pdf(C2A.ROWS["kats"]["title"], C2A.ROWS["kats"]["author"])
    from litkb import cassette as CAS
    p = CAS.default_bodies() / KATS_SHA[:2] / f"{KATS_SHA}.bin"
    if not p.is_file():
        pytest.skip(f"the recorded arXiv PDF of L005 is in the untracked cassette body store, not on this machine: {p}")
    data = p.read_bytes()
    assert hashlib.sha256(data).hexdigest() == KATS_SHA
    return data


@pg_only
@pytest.mark.parametrize("kind", ["recorded", "constructed"])
def test_bytes_on_disk_that_no_files_row_holds_are_not_a_duplicate(pgc, tmp_path, kind):
    """L005 Kats_2019 (register E03) on its RECORDED S2 answer: the arXiv rung is served the work's own bytes while an
    UNOWNED copy of them lies at the live run's path (`Validation/Kats_2019b_...`; no `files` row holds it). The run
    booked `duplicate-held` and the work stayed without a file. Now the bytes land and bind, the unowned copy is named
    on the attempt and left exactly where it lies, and bytes a `files` row DOES hold are still `duplicate-held` for a
    second work. `recorded`: the REAL arXiv PDF from the untracked body store (skipped where it is absent);
    `constructed`: a CONSTRUCTED PDF printing Kats' title and first author."""
    import shutil

    from litkb.acquire import run as R
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext is not installed: binding cannot read a first page")
    data = _kats_bytes(kind)
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws(f"fxb-kats-{kind}")
        work = w.admit(ws, C2A.ROWS["kats"])
        unowned = w.store.root / KATS_ON_DISK
        unowned.write_bytes(data)
        before = (hashlib.sha256(unowned.read_bytes()).hexdigest(), unowned.stat().st_mtime_ns)
        client = ReplayClient(C2A.ROWS["kats"]["doi"], stubs={
            "arxiv.org/pdf/1910.12077": (200, {"Content-Type": "application/pdf"}, data)})
        out = w.acquire(ws, work, {"s2": client, "arxiv": client, "ncbi-idconv": client}, routes=("s2", "arxiv"))
        C2A.no_misses(client)
        row = pgc.execute("SELECT status, detail FROM litkb.acquisition_attempts WHERE work_id = %s AND route = 'arxiv'",
                          (work["work_id"],)).fetchone()
        assert (out["outcome"], row[0]) == ("ok", "ok"), (out, row)
        assert row[1]["unowned_on_disk"] == [KATS_ON_DISK], row[1]
        assert (hashlib.sha256(unowned.read_bytes()).hexdigest(), unowned.stat().st_mtime_ns) == before
        sha = hashlib.sha256(data).hexdigest()
        assert pgc.execute("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (sha,)).fetchone()[0] == 1
        # the corpus guard is untouched: bytes a files row holds are still a duplicate for another work
        other = w.admit(ws, dict(C2A.ROWS["kats"], key="Kats_2019_fxb-constructed-second-work",
                                 doi="10.5555/fxb.constructed.kats-second"))
        status, detail = R.land_and_attach(w.writer, ws, w.tokens[ws], other, data, route="arxiv",
                                           source_url="CONSTRUCTED second offer", store=w.store,
                                           index=R.index_of_held(w.store, w.store.disk_index()), agent="fxb",
                                           session="fxb-second")
        assert status == "duplicate-held" and detail["held_for_work"] == str(work["work_id"]), (status, detail)
    finally:
        w.close()
        _reset_and_migrate(pgc)


@pg_only
@pytest.mark.parametrize("where", ["incoming-from-file", "quarantine-download"])
def test_a_copy_in_staging_or_quarantine_is_never_named_an_unowned_copy(pgc, tmp_path, where):
    """auditor-FX-B F1 (fix round 2). Since item 3 the disk index decides no outcome: `run.index_of_held` (acquire's
    guard "the dedupe asks what the corpus HOLDS, and staging and quarantine hold nothing"; mutation row F5d) now
    decides only which copies `unowned_on_disk` names — and a copy in `_litkb_staging/incoming/` or `_quarantine/` is
    never one: neither folder holds anything. CONSTRUCTED Kats_2019 bytes:
      incoming-from-file   `acquire --from-file _litkb_staging/incoming/<a file>`: the file being bound is not an
                           unowned copy of itself (F5d's original case: it was once `duplicate-held` against itself);
      quarantine-download  the arXiv rung downloads bytes a quarantined copy also holds (a refusal's record, e.g.
                           under a wrong record): the landing does not name the quarantined copy.
    Both land (`ok`) and leave the other copy untouched."""
    _need_pdftotext()
    data = _kats_bytes("constructed")
    _reset_and_migrate(pgc)
    w = C2A.World(pgc, tmp_path)
    try:
        ws = w.ws(f"fxb-f1-{where}")
        work = w.admit(ws, C2A.ROWS["kats"])
        if where == "incoming-from-file":
            copy = w.store.incoming / "Kats_2019_handed-by-curl.pdf"
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(data)
            before = (hashlib.sha256(copy.read_bytes()).hexdigest(), copy.stat().st_mtime_ns)
            out = w.acquire(ws, work, {}, from_file=copy)
            route = "browser"
        else:
            sha12 = hashlib.sha256(data).hexdigest()[:12]
            copy = w.store.quarantine / f"{C2A.ROWS['kats']['key']}__binding-failed__{sha12}.pdf"
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(data)
            before = (hashlib.sha256(copy.read_bytes()).hexdigest(), copy.stat().st_mtime_ns)
            client = ReplayClient(C2A.ROWS["kats"]["doi"], stubs={
                "arxiv.org/pdf/1910.12077": (200, {"Content-Type": "application/pdf"}, data)})
            out = w.acquire(ws, work, {"s2": client, "arxiv": client, "ncbi-idconv": client}, routes=("s2", "arxiv"))
            C2A.no_misses(client)
            route = "arxiv"
        rows = [(st, d) for r, st, _s, d in _ladder_rows(pgc, work) if r == route]
        assert out["outcome"] == "ok" and [st for st, _d in rows] == ["ok"], (out, rows)
        assert rows[0][1].get("unowned_on_disk") is None, \
            f"{where}: a copy staging/quarantine holds named as an unowned copy: {rows[0][1].get('unowned_on_disk')}"
        assert (hashlib.sha256(copy.read_bytes()).hexdigest(), copy.stat().st_mtime_ns) == before
    finally:
        w.close()
        _reset_and_migrate(pgc)

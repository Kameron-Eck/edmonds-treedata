"""litkb S4.5 builder-fix4 — the fixes that blocked the ladder-1 live run (one more, auditor-cand3 N4, is a case in
qc/test_litkb_s45_not_asked.py):

  1. the EarthArXiv harvester's ONE repair: an XML-1.0-illegal character (the MEASURED defect on the REAL page 7,
     a literal U+FFFE) is replaced, counted and printed, and the record kept; nothing else is repaired
  2. auditor-cand3 N1 (the orchestrator's ruling): an open-access `blocked` row whose kept bytes the one detector
     does NOT call a challenge is typed on basis `inferred`, never `detail`
  3. auditor-cand3 F1's note: a row on which a rung made no request is not ASKED in `rung_counts`, in the kill
     criterion's denominator, nor claimed by a not-asked line
  +  referee-badfile-read N2 (S4.5 decision D36): the item-8 instrument's 403 + transport-0 rule (`type_detail` ->
     `blocked_not_bad_file`, a MISBOOKED row) had no unit test; the tracked CSV is NOT regenerated (it is the recorded
     source of an applied live backfill) — the test reproduces its real Olofsson_2020 row from that row's own inputs

builder-fix5 (auditor-fix4's notes): N1 the repair's LEGAL side pinned (XML 1.0 §2.2 `Char` as the test's own oracle
over every code point, and a page of legal edge characters untouched); N2 the INCOMPLETE line carries the repair
counts; N6 the EarthArXiv rung books the PDF URL it asked in the run's asked-URL map, so a later rung never asks it
again and in MEASURE mode one file counts toward ONE rung's yield (section 4). N5 (D32's byte-equality refuses any
prefix or suffix) is in qc/test_litkb_s45_not_asked.py.

Every page, row and body that is not a recording is CONSTRUCTED and its test says so. No test touches the network.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w3 py -3.12 -m pytest qc/test_litkb_s45_prerun.py -q
"""
import ast
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
FIX = SCRIPTS / "qc" / "fixtures"
pg_only = pytest.mark.requires_litkb_pg


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EMAP = _load("_litkb_eartharxiv_map_prerun", SCRIPTS / "qc" / "instruments" / "litkb_eartharxiv_map.py")
C2A = _load("_litkb_hardening_c2a_prerun", SCRIPTS / "qc" / "instruments" / "litkb_hardening_c2a.py")

#: The REAL page (provenance beside it): EarthArXiv's ListRecords page 7, captured by builder-fix4 under the
#: orchestrator's grant — the page the live walk stopped on twice. Recorded bytes (`binary` in .gitattributes).
PAGE7 = FIX / "litkb_eartharxiv_oai_page7_37129fe75ccb.xml"
PAGE7_SHA = "37129fe75ccb7ef5894bad0f9680c29782a77ebbaa49fce34fd49f092b82bbdd"
#: The record whose dc:description carries the page's one U+FFFE (MEASURED: byte offset 165432).
PAGE7_DEFECT_RECORD = "oai:EA:id:1336"

#: A CONSTRUCTED last page of the feed (no resumption token): the walk around the real page must end somewhere.
CONSTRUCTED_LAST = (b'<?xml version="1.0" encoding="UTF-8"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
                    b"<ListRecords><record><header><identifier>oai:CONSTRUCTED:last</identifier></header><metadata>"
                    b'<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
                    b'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    b"<dc:identifier>https://doi.org/10.31223/X5LAST</dc:identifier>"
                    b"<dc:identifier>https://eartharxiv.org/repository/object/9/download/1/</dc:identifier>"
                    b"</oai_dc:dc></metadata></record></ListRecords></OAI-PMH>")


def _constructed_page(description):
    """A CONSTRUCTED one-record, one-page feed (no resumption token) whose dc:description is `description` (bytes)."""
    return (b'<?xml version="1.0" encoding="UTF-8"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
            b"<ListRecords><record><header><identifier>oai:CONSTRUCTED:1</identifier></header><metadata>"
            b'<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
            b'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            b"<dc:identifier>https://doi.org/10.31223/X5CONS</dc:identifier>"
            b"<dc:identifier>https://eartharxiv.org/repository/object/7/download/1/</dc:identifier>"
            b"<dc:description>" + description + b"</dc:description>"
            b"</oai_dc:dc></metadata></record></ListRecords></OAI-PMH>")


class Feed:
    """Answers the walk's requests in order (CONSTRUCTED client); records every URL asked."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        return self.answers.pop(0)


def _walk(tmp_path, name, *pages):
    """run_live over a feed of 200 answers -> (exit, the printed line, the map rows or None)."""
    out = tmp_path / f"{name}.csv"
    said = []
    rc = EMAP.run_live(out, client=Feed(*[(200, {}, p) for p in pages]), pace_s=0, printer=said.append)
    rows = None
    if out.is_file():
        with open(out, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    return rc, said[-1], rows


# ── 1. the EarthArXiv harvester ─────────────────────────────────────────────────────────────────
def test_the_real_page_7_is_repaired_counted_printed_and_every_record_kept(tmp_path):
    """The REAL page the live walk stopped on (sha pinned): unparseable as served — one literal U+FFFE inside record
    oai:EA:id:1336's description, MEASURED — and after the repair every one of its 50 records reaches the map, the
    defective one included, with exactly that one character changed (to U+FFFD). The walk goes on past it to a
    CONSTRUCTED last page, completes, and prints `repaired_pages=1 repaired_chars=1`."""
    body = PAGE7.read_bytes()
    assert hashlib.sha256(body).hexdigest() == PAGE7_SHA
    assert EMAP.oai_error(body) == "unparseable"                       # the live walk's stop, reproduced
    assert body.count(b"\xef\xbf\xbe") == 1                            # U+FFFE, UTF-8 encoded, once
    fixed, n = EMAP.repair_xml10(body)
    assert n == 1 and fixed == body.replace(b"\xef\xbf\xbe", b"\xef\xbf\xbd")
    assert EMAP.oai_error(fixed) == ""
    rows, token = EMAP.parse_page(fixed)
    assert len(rows) == 50 and token                                   # the page's own 50 records, and page 8's token
    rc, line, got = _walk(tmp_path, "real", body, CONSTRUCTED_LAST)
    assert rc == 0, line
    assert "repaired_pages=1 repaired_chars=1" in line and "complete" in line, line
    assert got is not None and len(got) == 51
    assert PAGE7_DEFECT_RECORD in {r["oai_identifier"] for r in got}


def test_constructed_pages_only_the_illegal_character_class_is_repaired(tmp_path):
    """CONSTRUCTED pages, one per case. Repaired and kept: a C0 control (U+000B) and a U+FFFF in one description ->
    `repaired_pages=1 repaired_chars=2`, the record in the map. Clean: a well-formed page -> `repaired_pages=0
    repaired_chars=0`. NOT repaired, the walk still stops INCOMPLETE and writes no map: a page that is not UTF-8
    (a Latin-1 byte) even when it ALSO carries an illegal character; a character REFERENCE to U+FFFE; an illegal
    character beside a malformed tag (the repair is counted, the page is still refused). The INCOMPLETE line carries
    the counts too (auditor-fix4 N2, its A15: the counts dropped from that line alone survived): 1 and 1 for the
    malformed page, 0 and 0 for the two pages the repair never touches."""
    rc, line, got = _walk(tmp_path, "c0", _constructed_page(b"basin\x0bmargin \xef\xbf\xbf end"))
    assert rc == 0 and "repaired_pages=1 repaired_chars=2" in line, line
    assert [r["oai_identifier"] for r in got] == ["oai:CONSTRUCTED:1"]
    rc, line, got = _walk(tmp_path, "clean", _constructed_page(b"a clean description"))
    assert rc == 0 and "repaired_pages=0 repaired_chars=0" in line and len(got) == 1, line
    for name, desc, counts in (("latin1", b"caf\xe9 \x01 not UTF-8", "repaired_pages=0 repaired_chars=0"),
                               ("charref", b"basin&#xFFFE;margin", "repaired_pages=0 repaired_chars=0"),
                               ("malformed", b"basin\x01margin <unclosed>", "repaired_pages=1 repaired_chars=1")):
        rc, line, got = _walk(tmp_path, name, _constructed_page(desc))
        assert rc == 1 and "INCOMPLETE" in line and got is None, (name, line)
        assert f"{counts} INCOMPLETE" in line, (name, line)
        assert (tmp_path / f"{name}.partial.csv").is_file()
    assert EMAP.repair_xml10(b"caf\xe9 \x01") == (b"caf\xe9 \x01", 0)       # not UTF-8: returned untouched


def _xml10_char(cp):
    """XML 1.0 (Fifth Edition) §2.2, production [2] `Char`, written out as the TEST's own oracle (never the module's
    regex): #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]."""
    return cp in (0x9, 0xA, 0xD) or 0x20 <= cp <= 0xD7FF or 0xE000 <= cp <= 0xFFFD or 0x10000 <= cp <= 0x10FFFF


#: CONSTRUCTED: the LEGAL edges of the class, each one a character XML 1.0 allows and the repair must never touch —
#: TAB, LF, CR; DEL and the C1 controls (U+007F, U+0080, U+0085, U+009F: legal in XML 1.0, unlike 1.1's restricted
#: set); U+00A0; the edges of the BMP ranges (U+D7FF, U+E000, U+FFFD itself); astral (U+10000, U+1D6FC MATHEMATICAL
#: ITALIC SMALL ALPHA — the kind of character an abstract carries — and U+10FFFF).
LEGAL_EDGES = "\t|\n|\r|\x7f|\x80|\x85|\x9f|\xa0|퟿||�|\U00010000|\U0001d6fc|\U0010ffff"


def test_the_repair_never_touches_a_legal_character(tmp_path):
    """auditor-fix4 N1 (its A2 TAB, A3 every astral character and A4 DEL + C1 widened into the class all SURVIVED: page
    7 carries only LF / CR / BMP text and the other pages are ASCII, so a repair rewriting real abstract text would have
    shown only in the printed count). Over EVERY code point the class matches exactly the complement of the `Char`
    production (the test's oracle, `_xml10_char`): 2,079 illegal (29 C0, 2,048 surrogates, U+FFFE, U+FFFF). A
    CONSTRUCTED page of the legal edges (`LEGAL_EDGES`) comes back byte-identical with 0 repaired, and its walk
    completes, prints `repaired_pages=0 repaired_chars=0` and keeps the record."""
    every = "".join(map(chr, range(0x110000)))
    hits = [m.start() for m in EMAP.XML10_ILLEGAL.finditer(every)]
    want = [cp for cp in range(0x110000) if not _xml10_char(cp)]
    assert len(want) == 2079 and hits == want, (len(hits), [hex(c) for c in sorted(set(hits) ^ set(want))][:8])
    page = _constructed_page(LEGAL_EDGES.encode("utf-8"))
    assert EMAP.repair_xml10(page) == (page, 0)
    rc, line, got = _walk(tmp_path, "legal", page)
    assert rc == 0 and "repaired_pages=0 repaired_chars=0 complete" in line, line
    assert got is not None and [r["oai_identifier"] for r in got] == ["oai:CONSTRUCTED:1"]


# ── 2. auditor-cand3 N1: kept bytes that are no challenge leave the route's rule inferred ────────
def test_an_open_access_row_whose_kept_bytes_are_no_challenge_is_typed_inferred():
    """The orchestrator's ruling on auditor-cand3 N1 (D30's intent): open access books `blocked` only when the one
    detector fired on SOME location, and keeps the FIRST body served — Li_2022's is a ScienceDirect reader page the
    detector finds no challenge in. Such bytes are no evidence for the rule: basis `inferred`, as with no bytes kept.
    A kept body the detector DOES call a challenge keeps basis `bytes`. The bodies are CONSTRUCTED; the tracked CSV,
    regenerated read-only from live, types attempt 01a0c71a (Li_2022) `inferred` and holds no `detail` row."""
    from litkb.acquire import ledger as L

    reader = b"<html><head><title>Identification of undocumented buildings</title></head><body>CONSTRUCTED</body></html>"
    assert L.type_blocked([403, 403, 200], reader, route="open_access")[:2] == ("challenge_or_bot_check", "inferred")
    assert L.type_blocked([403, 403, 200], None, route="open_access")[:2] == ("challenge_or_bot_check", "inferred")
    cf = b"<html><head><title>Just a moment...</title></head><body>CONSTRUCTED challenge-platform</body></html>"
    assert L.type_blocked([403], cf, route="open_access") == ("challenge_or_bot_check", "bytes", "cloudflare")
    blocked = REPO / "phase4" / "qc" / "litkb_acq_probe_blocked.csv"
    rows = {r["attempt_id"]: r for r in csv.DictReader(blocked.open(encoding="utf-8"))}
    li = rows["01a0c71a-7cae-7907-87d6-4f48e00912c7"]
    assert (li["route"], li["basis"], li["kept_bytes"]) == ("open_access", "inferred", "832805")
    assert len(rows) == 39 and not [a for a, r in rows.items() if r["basis"] == "detail"]



def test_the_item8_403_plus_transport_0_rule_types_the_real_olofsson_row_misbooked():
    """referee-badfile-read N2 / its M1 (the rule removed left the whole suite green while the instrument re-typed the
    real row `html_response`/`other`, and the backfill dry run would have written it): a `bad-file` attempt with no
    bytes kept whose codes are only 403 and the client's transport failure (0) — no host answered 200 — is
    MISBOOKED (`blocked_not_bad_file`: it was a block, not a bad file), never typed inside the bad-file family. The
    REAL row is attempt 01a0a071 (Olofsson_2020, open_access, codes [403, 0]) in the TRACKED item-8 CSV, which stays
    as applied (S4.5 decision D36): its own recorded route, codes, hosts, DOI and year, re-typed by `type_detail`
    and `finalize`, reproduce every typing cell the CSV holds. The CONSTRUCTED shapes pin the rule's edges."""
    import json

    B = _load("_litkb_acq_probe_badfile_prerun", SCRIPTS / "qc" / "instruments" / "litkb_acq_probe_badfile.py")
    tracked = REPO / "phase4" / "qc" / "litkb_acq_probe_badfile.csv"
    row = next(r for r in csv.DictReader(tracked.open(encoding="utf-8"))
               if r["attempt_id"] == "01a0a071-bb1c-7909-8a1c-52de2f504388")
    assert (row["work_key"], row["route"], row["http_codes"], row["bytes_kept"]) == (
        "Olofsson_2020_mitigating-effects-omission-errors", "open_access", "[403, 0]", "n")
    st, basis, cause, free, grade, fix, why = B.type_detail(row["route"], json.loads(row["http_codes"]),
                                                            row["tried"].split(" | "), row["identifier"],
                                                            int(row["year"]))
    assert cause == "blocked_not_bad_file", (cause, why)
    got = B.finalize({"sub_status": st, "basis": basis, "cause": cause, "free_to_fix": free, "fix_grade": grade,
                      "fix": fix, "reason": why})
    keys = ("sub_status", "basis", "cause", "free_to_fix", "fix_grade", "fix", "reason")
    assert {k: got[k] for k in keys} == {k: row[k] for k in keys}
    assert (row["sub_status"], row["cause"]) == ("", "misbooked") and row["reason"].startswith("blocked_not_bad_file:")
    for codes in ([403], [403, 403, 0], [0, 403]):                      # CONSTRUCTED: no host answered 200
        assert B.type_detail("open_access", codes, ["x:403"], "10.1/x", 2020)[2] == "blocked_not_bad_file", codes
    assert B.type_detail("open_access", [403, 200], ["x:403", "y:200"], "10.1/x", 2020)[2] == "landing_page"


# ── 3. a row on which the rung made no request is not asked ──────────────────────────────────────
def _reset_and_migrate(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


@pytest.fixture(scope="module")
def pgp(litkb_pg_base):
    """The worker database, RESET AND MIGRATED before this module's database test and after it (brief-COMMON rule 5:
    it admits REAL keys and DOIs — Kats_2019 and E13, builder C2a's ROWS)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset_and_migrate(conn)
    yield conn
    _reset_and_migrate(conn)


@pg_only
def test_a_row_on_which_the_rung_made_no_request_is_never_asked(pgp, tmp_path, monkeypatch):
    """auditor-cand3 F1: with no EarthArXiv map on disk the REAL `eartharxiv` rung, run through the REAL ladder,
    writes `api-error` "nothing was asked" (no HTTP code, no terminal status) — counted asked, the live run would
    have printed `yield: eartharxiv=0/~187`. Beside it (CONSTRUCTED rows): a harvested-map MISS on E13 (the map is
    the source's answer: asked); an `osf` transport failure on E13 (code 0: a request left: asked); an `openalex`
    rung that raised before asking on Kats (no request: not asked); a `zenodo` no-request row on E13 beside the
    REAL zenodo condition skip on Kats (the condition did not decide E13, so no not-asked line may claim it)."""
    from litkb.acquire import run as R
    from litkb.acquire import stage_a as A

    monkeypatch.setenv("LITKB_EARTHARXIV_MAP", str(tmp_path / "not-harvested.csv"))
    assert A.eartharxiv_map() is None
    w = C2A.World(pgp, tmp_path)
    try:
        ws = w.ws("prerun")
        kats, e13 = w.admit(ws, C2A.ROWS["kats"]), w.admit(ws, C2A.ROWS["e13"])
        tok = w.tokens[ws]
        frozen = w.now()
        w.acquire(ws, kats, {}, routes=("eartharxiv", "zenodo"))
        R.record_attempt(w.writer, ws, tok, e13["work_id"], "eartharxiv", e13["doi"], "no-oa-copy",
                         {"note": "CONSTRUCTED: no EarthArXiv preprint in the harvested map"}, None)
        R.record_attempt(w.writer, ws, tok, e13["work_id"], "osf", e13["doi"], "api-error",
                         {"note": "CONSTRUCTED: the client's own transport failure"}, [0],
                         terminal={"url": "https://api.osf.io/CONSTRUCTED", "status_code": 0, "at": None})
        R.record_attempt(w.writer, ws, tok, kats["work_id"], "openalex", kats["doi"], "api-error",
                         {"exception": "RuntimeError", "message": "CONSTRUCTED: raised before any request"}, None)
        R.record_attempt(w.writer, ws, tok, e13["work_id"], "zenodo", e13["doi"], "api-error",
                         {"exception": "RuntimeError", "message": "CONSTRUCTED: raised before any request"}, None)
        real = pgp.execute(
            "SELECT status, http_codes, terminal_status_code, detail::text FROM litkb.acquisition_attempts "
            "WHERE work_id = %s AND route = 'eartharxiv'", (kats["work_id"],)).fetchall()
        m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "repo": str(REPO),
             "probe_csvs": {C2A.CROSSWALK_PROBE: f"phase4/qc/{C2A.CROSSWALK_PROBE}"}}
        counts = {r: C2A.rung_counts(pgp, m, r) for r in ("eartharxiv", "osf", "openalex", "zenodo")}
        asked_b = C2A.stage_b_asked_works(pgp, m)
        zenodo_skips = C2A.condition_skips(pgp, m, "zenodo")
        lines = C2A.report_lines(pgp, m)
    finally:
        w.close()
    assert real and all(s == "api-error" and not codes and t is None and "nothing was asked" in d
                        for s, codes, t, d in real), real
    assert counts == {"eartharxiv": (0, 1), "osf": (0, 1), "openalex": (0, 0), "zenodo": (0, 0)}, counts
    assert asked_b == 1                                 # E13's osf transport failure; not Kats's raised openalex row
    assert zenodo_skips == (1, 1), zenodo_skips
    assert "yield: eartharxiv=0/1" in lines and "yield: openalex=0/0" in lines, lines
    assert not [ln for ln in lines if ln.startswith("not-asked: zenodo")], lines
    assert [ln for ln in lines if ln.startswith("kill: arxiv=")][0].startswith("kill: arxiv=0/1 "), lines


# ── 4. auditor-fix4 N6: the EarthArXiv rung's PDF URL is booked in the run's asked-URL map ───────
#: CONSTRUCTED: an EarthArXiv download URL the harvested map names for Kats_2019's DOI (C2a's REAL row).
EA_URL = "https://eartharxiv.org/repository/object/CONSTRUCTED/download/1/"


class _Stub:
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


class _Ctx:
    """A CONSTRUCTED RungContext stand-in for the pure rung test: clients by route, a pacer that never sleeps."""

    def __init__(self, clients):
        from litkb.netutil import Pacer
        self.clients = clients
        self.pacer = Pacer(interval=0, sleep=lambda s: None)
        self.work_class = ""


def _ea_map(tmp_path, monkeypatch, doi):
    """A CONSTRUCTED harvested map (the harvester's columns) naming EA_URL for `doi`, made the rung's map."""
    from litkb.acquire import stage_a as A

    m = tmp_path / "eartharxiv_map.csv"
    with open(m, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(A.EARTHARXIV_COLUMNS))
        w.writeheader()
        w.writerow({"published_doi": doi, "preprint_doi": "10.31223/x5cons", "pdf_url": EA_URL,
                    "oai_identifier": "oai:CONSTRUCTED:1", "datestamp": "2021-01-01", "rights": "CC-BY"})
    monkeypatch.setenv("LITKB_EARTHARXIV_MAP", str(m))
    assert A.eartharxiv_map() is not None


def test_the_eartharxiv_rung_books_the_url_it_asked_and_a_later_rung_never_asks_it(tmp_path, monkeypatch):
    """auditor-fix4 N6 (the pure half): the REAL `rung_eartharxiv` on a map hit asks the PDF URL once AND records it
    in the run's asked-URL map under its own name; a later rung (`doaj`) handed the same URL does not ask it again and
    its note names the asker. Before the fix the rung called `fetch_candidates` without the run's `work`, so the map
    stayed empty and the second GET went out. CONSTRUCTED map row, PDF and work."""
    from litkb.acquire import stage_a as A
    from litkb.acquire import stage_b as B

    doi = C2A.ROWS["kats"]["doi"]
    _ea_map(tmp_path, monkeypatch, doi)
    s = _Stub({"eartharxiv.org": (200, {}, C2A.constructed_pdf(C2A.ROWS["kats"]["title"], C2A.ROWS["kats"]["author"]))})
    ctx, work = _Ctx({"eartharxiv": s, "doaj": s}), {"doi": doi, "ids": []}
    r = A.rung_eartharxiv(work, ctx)
    assert r["status"] == "downloaded" and s.calls == [EA_URL], (r.get("status"), s.calls)
    assert work.get("asked_urls") == {EA_URL: "eartharxiv"}, work.get("asked_urls")      # (a) booked by that rung
    r2 = B.fetch_candidates("doaj", [(EA_URL, {})], ctx, work)
    assert s.calls == [EA_URL] and r2["status"] == "no-oa-copy", (s.calls, r2.get("status"))
    assert "already asked in this ladder run by eartharxiv" in r2["detail"], r2["detail"]


def test_every_fetch_candidates_call_in_the_ladder_passes_the_run_s_work():
    """auditor-fix4 N6 (the class): `fetch_candidates(route, candidates, ctx, work=None)` falls back to a FRESH asked-URL
    map when it is not handed the run's `work` — silently. Every call of it under pipeline/litkb (outside its own
    definition) passes a 4th positional argument or `work=`; the census the scan reads is non-empty and holds the
    EarthArXiv rung (today: stage_a.rung_eartharxiv, stage_b.answered, stage_b.rung_arxiv,
    stage_b_repos.rung_publisher_url)."""
    sites, missing = [], []
    for path in sorted((SCRIPTS / "pipeline" / "litkb").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for call in [n for n in ast.walk(fn) if isinstance(n, ast.Call)]:
                name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
                if name != "fetch_candidates":
                    continue
                where = f"{path.stem}.{fn.name}"
                sites.append(where)
                if len(call.args) < 4 and not any(k.arg == "work" for k in call.keywords):
                    missing.append(where)
    assert "stage_a.rung_eartharxiv" in sites and len(set(sites)) >= 4, sites
    assert missing == [], missing


@pg_only
def test_in_measure_mode_one_eartharxiv_file_counts_toward_one_rung_s_yield(pgp, tmp_path, monkeypatch):
    """auditor-fix4 N6 through the REAL ladder in MEASURE mode (S4.5 decision D9: every rung asked, nothing landed) on
    Kats_2019 (C2a's REAL row, CONSTRUCTED admission): the harvested map (CONSTRUCTED) names an EarthArXiv PDF for its
    DOI, and DOAJ's answer (CONSTRUCTED) lists the SAME download URL as a fulltext link. The PDF (CONSTRUCTED, Kats'
    title and first author) is asked ONCE — by `eartharxiv` (Stage A), whose row is `measured`; `doaj` (Stage B) books
    it as already asked by eartharxiv and answers `no-oa-copy`. So `rung_counts` gives eartharxiv 1/1 and doaj 0/1 —
    before the fix DOAJ asked the URL again and ONE file counted toward TWO rungs' yields (doaj 1/1)."""
    _reset_and_migrate(pgp)
    doi = C2A.ROWS["kats"]["doi"]
    _ea_map(tmp_path, monkeypatch, doi)
    pdf = C2A.constructed_pdf(C2A.ROWS["kats"]["title"], C2A.ROWS["kats"]["author"])
    doaj = {"results": [{"bibjson": {"link": [{"type": "fulltext", "url": EA_URL, "content_type": "PDF"}]}}]}
    s = _Stub({"eartharxiv.org": (200, {"Content-Type": "application/pdf"}, pdf),
               "doaj.org": (200, {"Content-Type": "application/json"}, json.dumps(doaj).encode())})
    w = C2A.World(pgp, tmp_path)
    try:
        ws = w.ws("fix5-n6")
        kats = w.admit(ws, C2A.ROWS["kats"])
        frozen = w.now()
        out = w.acquire(ws, kats, {"eartharxiv": s, "doaj": s}, routes=("eartharxiv", "doaj"), mode="measure")
        rows = pgp.execute("SELECT route, status, coalesce(detail ->> 'detail', '') FROM litkb.acquisition_attempts "
                           "WHERE work_id = %s AND route IN ('eartharxiv', 'doaj') ORDER BY at, id",
                           (kats["work_id"],)).fetchall()
        m = {"frozen_at": frozen, "run_workstream_ids": [str(ws)]}
        counts = {r: C2A.rung_counts(pgp, m, r) for r in ("eartharxiv", "doaj")}
    finally:
        w.close()
    assert out.get("outcome") == "measured", out
    assert [u for u in s.calls if "eartharxiv.org" in u] == [EA_URL], s.calls         # asked ONCE in the run
    assert [(r, st) for r, st, _d in rows] == [("eartharxiv", "measured"), ("doaj", "no-oa-copy")], rows
    assert "already asked in this ladder run by eartharxiv" in rows[1][2], rows          # (a) booked by that rung
    assert counts == {"eartharxiv": (1, 1), "doaj": (0, 1)}, counts                      # (b) one file, one rung

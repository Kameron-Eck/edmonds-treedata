"""litkb P2 "Admission + acquisition" — the kills and guards of the design's §14 P2 row.

Design: Scripts/LITERATURE_KB_DESIGN_2026-09-13.md §4.6, §4.7, §10, §14. Decisions: Scripts/decisions.yaml
litkb-p0-foundation. Every guard here is mutated by qc/instruments/litkb_p2_mutations.py, which runs this whole
file (and qc/test_litkb_annas.py) under each mutation; the evidence is Reports/LITKB_P2_REPORT_2026-09-14.md.

  kill (§14 P2)                                                    test
  Averkov 2009 / Higham 2011 with their pre-fix DOIs and REAL      test_kill_prefix_wrong_doi_is_refused_at_binding[*]
  files are refused at binding (fixture: the two pre-fix rows)     test_prefix_wrong_doi_with_the_manifest_claim_is_refused[*]
  the corrected DOIs admit the same files, and a case variant      test_kill_corrected_doi_admits_the_same_file_and_its_case_variant_collides[*]
  of the corrected DOI collides
  two concurrent admissions of one DOI leave one work              test_kill_concurrent_admissions_of_one_doi_leave_one_work
  a Duplicate-of pair re-entered without identifiers -> review     test_kill_duplicate_pair_without_identifiers_goes_to_duplicate_review
  an admitter approving its own manual admission is refused        test_kill_admitter_cannot_approve_its_own_manual_admission

The real Validation files are read only: no test moves, renames or writes them (their sha256, size and mtime
are compared before and after). Registry answers come from qc/testdata/litkb_p2/crossref_kill_dois.json,
captured live from api.crossref.org on 2026-09-14; the live comparison is test_live_crossref_matches_the_fixture
(LITKB_LIVE=1). Every other file this module writes lives under pytest's tmp_path.
"""
import ast
import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
PIPELINE = SCRIPTS / "pipeline"
FIX = SCRIPTS / "qc" / "testdata" / "litkb_p2"
VALIDATION = Path(os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture")) / "Validation"
KEY_RE = r"^[A-Za-z]+_[0-9]{4}[ab]?_[a-z0-9]+(-[a-z0-9]+){1,4}$"
pg_only = pytest.mark.requires_litkb_pg
live = pytest.mark.litkb_live

CROSSREF = json.loads((FIX / "crossref_kill_dois.json").read_text(encoding="utf-8"))["records"]
PREFIX_ROWS = {r["stem"]: r for r in csv.DictReader(open(FIX / "manifest.pre-auditfix.rows.csv", encoding="utf-8",
                                                          newline=""))}
KILL = {
    "averkov": dict(stem="Averkov_2009_confirmation-matheron-s-conjecture", right="10.4171/jems/179",
                    variant="10.4171/JEMS/179"),
    "higham": dict(stem="Higham_2011_pth-roots-stochastic-matrices", right="10.1016/j.laa.2010.04.007",
                   variant="10.1016/J.LAA.2010.04.007"),
}


# ── helpers ───────────────────────────────────────────────────────────────────────────────

class RegistryStub:
    """Crossref /works/<doi> from recorded records; everything else 404. Never touches the network."""
    base = ""

    def __init__(self, records=None):
        self.records = {k.lower(): v for k, v in (CROSSREF | (records or {})).items()}
        self.calls = []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        if "api.crossref.org/works/" in url:
            rec = self.records.get(urllib.parse.unquote(url.split("/works/", 1)[1]).lower())
            return (200, {}, json.dumps({"message": rec}).encode()) if rec else (404, {}, b"")
        return 404, {}, b""


class RouteStub:
    """Routes by URL substring; each route is (status, headers, body) or a callable; unknown URLs raise."""
    base = "https://annas-archive.gl"

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        for frag, resp in self.routes.items():
            if frag in url:
                return resp(url) if callable(resp) else resp
        raise AssertionError(f"no stub route for {url}")


def _nopace():
    from litkb.netutil import Pacer
    return Pacer(interval=0, sleep=lambda s: None)


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines):
    """A one-page text PDF (Helvetica, one line per entry) that pdftotext reads back."""
    content = "BT /F1 9 Tf 40 760 Td 12 TL " + " ".join(f"({_esc(ln)}) '" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1400 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(
        f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def paper_pdf(title, author, salt=None):
    salt = salt or uuid.uuid4().hex
    filler = [f"Body text line {i} of a synthetic paper about canopy mapping and validation, id {salt}." for i in range(8)]
    return make_pdf(["Journal of Synthetic Studies 1 (2020) 1-10", title, f"{author} and A. Coauthor", ""] + filler)


def _need_pdftotext():
    import shutil
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext is not installed: binding cannot read a first page")


def _need_file(p):
    if not Path(p).exists():
        pytest.skip(f"{p} is not on this machine")
    _need_pdftotext()


def _file_state(p):
    st = Path(p).stat()
    return hashlib.sha256(Path(p).read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns


# ── no server needed ──────────────────────────────────────────────────────────────────────

def test_p2_import_pulls_no_heavy_dependency():
    """Design §9: importing the P2 modules loads no driver, HTTP stack or extraction library."""
    code = ("import sys, litkb.commands, litkb.admit.front, litkb.admit.binding, litkb.admit.registry, "
            "litkb.admit.resolver, litkb.acquire.run, litkb.acquire.annas, litkb.acquire.open_access, "
            "litkb.acquire.scihub, litkb.acquire.store, litkb.netutil\n"
            "heavy = {'psycopg', 'requests', 'paper_search_mcp', 'torch', 'docling', 'numpy', 'pandas'}\n"
            "pulled = sorted(heavy & {m.split('.')[0] for m in sys.modules})\n"
            "print(pulled)\nsys.exit(1 if pulled else 0)\n")
    r = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONPATH=str(PIPELINE)),
                       capture_output=True, text=True)
    assert r.returncode == 0, f"P2 imports pulled heavy modules: {r.stdout}{r.stderr}"


_DELETE_CALLS = {"remove", "unlink", "rmtree", "rmdir", "removedirs"}
_MODULE_DELETE_CALLS = {"replace", "truncate", "move"}     # os.replace / os.truncate: only on the os module


def _delete_offenders(paths):
    """Calls that delete or overwrite: any .remove/.unlink/.rmtree/.rmdir/.removedirs, os.replace/os.truncate,
    and open() with a "w" mode. (str.replace is not a call on the os module, so it is not flagged.)"""
    found = []
    for path in paths:
        src = Path(path).read_text(encoding="utf-8")
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            owner = getattr(getattr(node.func, "value", None), "id", "")
            bad = name in _DELETE_CALLS or (name in _MODULE_DELETE_CALLS and owner == "os")
            if name == "open":
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
                bad = isinstance(mode, ast.Constant) and isinstance(mode.value, str) and mode.value.startswith("w")
            if bad and "store-scan: allow" not in lines[node.lineno - 1]:
                found.append(f"{Path(path).name}:{node.lineno}: {lines[node.lineno - 1].strip()}")
    return found


def test_acquisition_and_admission_code_hold_no_delete_path():
    """The 2026-09-12 loss of 149 PDFs: no acquisition or admission module may delete, truncate or overwrite a
    file (os.remove/unlink/rmtree/rmdir/os.replace/truncate, open(..., "w*")). Two lines carry an explicit
    `store-scan: allow` because they write outside the literature store (the hash-index cache, the audit CSV)."""
    files = sorted((PIPELINE / "litkb" / "acquire").glob("*.py")) + sorted((PIPELINE / "litkb" / "admit").glob("*.py"))
    assert len(files) >= 8, files
    assert _delete_offenders(files) == []
    allowed = [ln for f in files for ln in f.read_text(encoding="utf-8").splitlines() if "store-scan: allow" in ln]
    assert len(allowed) == 2, allowed
    # the scan itself fires on a planted delete
    probe = Path(__file__).with_name("_litkb_p2_scan_probe.txt")
    assert _delete_offenders([_write_probe(probe)]) != []


def _write_probe(probe):
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="litkb_scan_"))
    p = d / "probe.py"
    p.write_text("import os\nos.remove('x')\n", encoding="utf-8")
    return p


def test_store_writes_only_new_files_into_staging_or_quarantine(tmp_path):
    from litkb.acquire.store import Store, StoreRefused
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True)
    held = root / "Validation" / "Held_2020_some-paper.pdf"
    held.write_bytes(b"%PDF-1.4 held")
    s = Store(root, index_cache=tmp_path / "cache.json")
    with pytest.raises(StoreRefused, match="outside"):
        s.write_new(root / "Validation" / "New_2020_other-paper.pdf", b"%PDF-1.4 x")
    with pytest.raises(StoreRefused, match="outside"):
        s.write_new(root / "x.pdf", b"%PDF-1.4 x")
    p = s.write_new(s.incoming / "A_2020_a-b.pdf", b"%PDF-1.4 a")
    with pytest.raises(StoreRefused, match="already exists"):
        s.write_new(p, b"%PDF-1.4 overwrite")
    assert p.read_bytes() == b"%PDF-1.4 a"
    with pytest.raises(StoreRefused, match="not created by acquisition"):
        s.move_new(held, s.quarantine / "Held_2020_some-paper__x.pdf")
    q = s.move_new(p, s.quarantine / "A_2020_a-b__binding-failed__0.pdf")
    assert q.exists() and not p.exists() and held.read_bytes() == b"%PDF-1.4 held"
    idx = s.disk_index()
    assert hashlib.sha256(b"%PDF-1.4 held").hexdigest() in idx["sha256"]


@pytest.mark.parametrize("case", sorted(KILL))
def test_binding_reads_the_real_first_page(case):
    """Check 3 on the real Validation files: the pre-fix registry titles are not on the first page and the
    pre-fix first authors (Lisca, De la Cruz) are not there either; the corrected ones are. Read-only."""
    from litkb.admit import binding
    from litkb.admit.registry import parse_crossref
    k = KILL[case]
    row = PREFIX_ROWS[k["stem"]]
    pdf = VALIDATION / f"{k['stem']}.pdf"
    _need_file(pdf)
    before = _file_state(pdf)
    wrong = parse_crossref(CROSSREF[row["doi"]], row["doi"])
    right = parse_crossref(CROSSREF[k["right"]], k["right"])
    bw = binding.bind(pdf, wrong["title"], wrong["first_author"])
    br = binding.bind(pdf, right["title"], right["first_author"])
    assert bw["verdict"] == "binding-failed" and bw["ratio"] < 0.85 and not bw["author_found"], bw
    assert br["verdict"] == "bound" and br["ratio"] >= 0.85 and br["author_found"], br
    assert before[0] == row["sha256"] and _file_state(pdf) == before


def test_binding_needs_the_first_author_as_well_as_the_title(tmp_path):
    """Check 3 is two conditions: the registry title on the first page AND its first author. A page carrying the
    title under another author's name does not bind (a same-titled paper by someone else)."""
    _need_pdftotext()
    from litkb.admit import binding
    title = f"Estimating canopy change from repeated aerial surveys {uuid.uuid4().hex[:6]}"
    pdf = tmp_path / "same-title.pdf"
    pdf.write_bytes(paper_pdf(title, "Q. Someone-Else"))
    b = binding.bind(pdf, title, "Tester")
    assert b["ratio"] >= 0.85 and not b["author_found"] and b["verdict"] == "binding-failed", b
    pdf2 = tmp_path / "right-author.pdf"
    pdf2.write_bytes(paper_pdf(title, "T. Tester"))
    assert binding.bind(pdf2, title, "Tester")["verdict"] == "bound"


def test_year_rule_allows_one_year_only_with_title_and_author():
    from litkb.admit.resolver import judge_candidate
    t = "Confirmation of Matheron's conjecture on the covariogram of a planar convex body"
    cand = {"titles": [t], "family": "Averkov", "year": 2009}
    assert judge_candidate(cand, t, "Averkov", 2009)[0]
    assert judge_candidate(cand, t, "Averkov", 2010)[0]
    assert not judge_candidate(cand, t, "Averkov", 2011)[0]
    assert not judge_candidate(cand, t, "Bianchi", 2010)[0]
    assert not judge_candidate(cand, "Heegard Floer invariants of Legendrian knots", "Averkov", 2010)[0]


def test_make_key_follows_the_convention():
    import re
    from litkb.admit.front import make_key
    for author, year, title in [("Averkov", 2009, "Confirmation of Matheron's conjecture on the covariogram"),
                                ("O'Neil-Dunne", 2014, "An object-based system for LiDAR data fusion"),
                                ("De la Cruz", 2011, "The ϕS polar decomposition of matrices"),
                                ("Müller", 2020, "A"), ("Van Den Hout", 2017, "Multi-State Survival Models for Interval-"
                                                                             "Censored Data with a very long subtitle")]:
        key = make_key(author, year, title)
        assert re.match(KEY_RE, key) and len(key) < 60, key
    assert make_key("O'Neil-Dunne", 2014, "x y").startswith("ONeilDunne_2014_")


def test_scihub_challenge_is_recorded_blocked_and_not_bypassed():
    from litkb.acquire import scihub
    stub = RouteStub({"sci-hub.ru": (403, {}, b"<html><title>Just a moment...</title></html>"),
                      "sci-hub.ren": (200, {}, b"<html><title>Verification</title>captcha</html>")})
    r = scihub.fetch_scihub("10.1/x", _nopace(), client=stub)
    assert r["status"] == "blocked" and r["pdf"] is None
    assert len(stub.calls) == 2, stub.calls          # one GET per mirror, no retry with extra headers


def test_scihub_follows_citation_pdf_url_and_needs_pdf_bytes():
    from litkb.acquire import scihub
    page = b'<html><meta name="citation_pdf_url" content="//sci-hub.red/storage/x.pdf"></html>'
    stub = RouteStub({"sci-hub.ru/10.1": (200, {}, page), "sci-hub.red/storage": (200, {}, b"%PDF-1.4 ok")})
    r = scihub.fetch_scihub("10.1/x", _nopace(), client=stub)
    assert r["status"] == "downloaded" and r["source_url"] == "https://sci-hub.red/storage/x.pdf"


def test_open_access_takes_the_first_location_serving_a_pdf():
    from litkb.acquire import open_access
    stub = RouteStub({"landing.example": (200, {}, b"<html>landing</html>"), "pdf.example": (200, {}, b"%PDF-1.5 ok")})
    r = open_access.fetch_open_access("10.1/x", None, _nopace(), client=stub,
                                      locations=lambda d: (["https://landing.example/a", "https://pdf.example/b"], "stub"))
    assert r["status"] == "downloaded" and r["source_url"] == "https://pdf.example/b"
    r = open_access.fetch_open_access("10.1/x", None, _nopace(), client=stub, locations=lambda d: ([], "no record"))
    assert r["status"] == "no-oa-copy"
    ax = RouteStub({"arxiv.org/pdf/2303.07334": (200, {}, b"%PDF-1.5 arxiv")})
    r = open_access.fetch_open_access("10.48550/arXiv.2303.07334", None, _nopace(), client=ax,
                                      locations=lambda d: ([], "no record"))
    assert r["status"] == "downloaded" and r["source_url"] == "https://arxiv.org/pdf/2303.07334"


def _annas_routes(pdf, doi, left=900, error=None):
    md5 = hashlib.md5(pdf).hexdigest()
    fd = {"account_fast_download_info": {"downloads_left": left}}
    fd.update({"error": error} if error else {"download_url": "https://partner.example/f.pdf"})
    return md5, {"/scidb/": (200, {}, f'<a href="/md5/{md5}">record</a>'.encode()),
                 "/db/aarecord_elasticsearch/": (200, {}, json.dumps({"file_unified_data": {
                     "identifiers_unified": {"doi": [doi]}, "extension_best": "pdf",
                     "filesize_best": len(pdf), "title_best": "t"}}).encode()),
                 "fast_download": (200, {}, json.dumps(fd).encode()),
                 "partner.example": (200, {}, pdf)}


def test_annas_known_md5_spends_no_download():
    from litkb.acquire import annas
    pdf = b"%PDF-1.4 known"
    md5, routes = _annas_routes(pdf, "10.1/known")
    stub = RouteStub(routes)
    r = annas.fetch_for_litkb(stub, "SEKRIT", "10.1/known", _nopace(), known_md5={md5})
    assert r["status"] == "duplicate-held"
    assert not any("fast_download" in u for u in stub.calls)
    r = annas.fetch_for_litkb(RouteStub(routes), "SEKRIT", "10.1/known", _nopace(), known_md5=set())
    assert r["status"] == "downloaded" and r["pdf"] == pdf and r["downloads_left"] == 900


def test_annas_bytes_must_be_the_record_md5():
    from litkb.acquire import annas
    md5, routes = _annas_routes(b"%PDF-1.4 the record", "10.1/m")
    routes["partner.example"] = (200, {}, b"%PDF-1.4 other bytes")
    r = annas.fetch_for_litkb(RouteStub(routes), "SEKRIT", "10.1/m", _nopace())
    assert r["status"] == "hash-mismatch" and r["pdf"] == b"%PDF-1.4 other bytes"


# ── Postgres ──────────────────────────────────────────────────────────────────────────────

class P2:
    def __init__(self, psycopg, conn):
        self.psycopg, self.errors, self.conn = psycopg, psycopg.errors, conn
        self.opened, self.tokens = [], {}

    def session(self, role=None):
        from psycopg import sql
        from litkb.db import connect as c
        k = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
        if role:
            k.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        self.opened.append(k)
        return k

    def one(self, q, params=(), conn=None):
        return (conn or self.conn).execute(q, params).fetchone()

    def ws(self):
        ws_id, token = self.one("SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/p2', NULL, 'p2 test', NULL)",
                                (f"p2-{uuid.uuid4().hex[:12]}",))
        self.tokens[ws_id] = token
        return ws_id

    def jsonb(self, v):
        from psycopg.types.json import Jsonb
        return Jsonb(v)


@pytest.fixture(scope="session")
def _p2(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    return P2(psycopg, conn)


@pytest.fixture
def pg(_p2):
    yield _p2
    while _p2.opened:
        _p2.opened.pop().close()


def _synthetic(hexid=None, year=2020, author="Tester"):
    hexid = hexid or uuid.uuid4().hex[:12]
    doi = f"10.5555/litkb-{hexid}"
    title = f"A synthetic registry record for litkb admission {hexid}"
    rec = {"DOI": doi, "title": [title], "author": [{"family": author, "given": "T.", "sequence": "first"}],
           "issued": {"date-parts": [[year, 1]]}, "type": "journal-article", "container-title": ["J. Synth."]}
    return doi, title, rec


def _good_payload(hexid=None, year=2020, claimed=None, author="Tester"):
    hexid = hexid or uuid.uuid4().hex[:12]
    doi, title, _rec = _synthetic(hexid, year, author)
    ev = {"registry": "crossref", "registry_title": title, "registry_first_author": author, "registry_year": year}
    if claimed is not False:
        ev["claimed"] = {"title": title, "first_author": author, "year": year, "title_ratio": 1.0,
                         "author_match": True} | (claimed or {})
    work = {"type": "article", "title": title, "authors": [{"family": author, "given": "T."}], "year": year}
    return hexid, work, [{"scheme": "doi", "value": doi, "verified_by": "crossref", "evidence": ev}]


def _cand(pg, conn, ws, title="lead"):
    return pg.one("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
                  (ws, pg.tokens[ws], title), conn=conn)[0]


_OWN = object()   # "use the workstream's own token"


def _admit_sql(pg, conn, ws, work, identifiers, file_json=None, route="registry", key=None, token=_OWN,
               candidate=None, agent="agentA", session="sessA"):
    candidate = candidate or _cand(pg, conn, ws)
    key = key or f"Tester_2020_synthetic-{uuid.uuid4().hex[:10]}"
    return pg.one("SELECT litkb.admit(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                  (ws, pg.tokens[ws] if token is _OWN else token, candidate, route, key, pg.jsonb(work),
                   pg.jsonb(identifiers), pg.jsonb(file_json) if file_json is not None else None, pg.jsonb({}),
                   agent, session), conn=conn)[0]


def _binding(title, ratio=0.97, author_found=True, text_layer=True, matched=None):
    return {"verdict": "bound", "ratio": ratio, "matched": title if matched is None else matched,
            "registry_title": title, "author_found": author_found, "text_layer": text_layer, "page": 1}


def _file(title, **kw):
    return {"sha256": hashlib.sha256(uuid.uuid4().bytes).hexdigest(), "rel_path": f"_litkb_staging/filed/x-{uuid.uuid4().hex[:6]}.pdf",
            "binding": _binding(title, **kw)}


# ── the Averkov/Higham replay ─────────────────────────────────────────────────────────────

@pg_only
@pytest.mark.parametrize("case", sorted(KILL))
def test_kill_prefix_wrong_doi_is_refused_at_binding(pg, case):
    """KILL. The pre-fix manifest row's DOI, trusted as-is with its real file (no claimed record to compare, so
    the file's binding IS the comparison): Crossref's record for that DOI is another paper, whose title and first
    author are not on the file's first page. Refused at check 3; nothing but the refused admission is written;
    the file is untouched."""
    from litkb.admit import front
    k = KILL[case]
    row = PREFIX_ROWS[k["stem"]]
    pdf = VALIDATION / f"{k['stem']}.pdf"
    _need_file(pdf)
    before = _file_state(pdf)
    ws, w = pg.ws(), pg.session("litkb_writer")
    key = f"{k['stem']}-r{uuid.uuid4().hex[:6]}"
    res = front.admit_registry(w, ws, pg.tokens[ws], doi=row["doi"], key=key, file_path=pdf, root=VALIDATION.parent,
                              agent="replay", session="replay-1", client=RegistryStub(), pacer=_nopace())
    b = res["checks"]["check3_binding"]
    assert (res["outcome"], res["refused_at"]) == ("refused", "check3_binding"), res
    assert b["verdict"] == "binding-failed" and float(b["ratio"]) < 0.85, b
    assert pg.one("SELECT count(*) FROM litkb.works WHERE key = %s", (key,))[0] == 0
    assert pg.one("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (row["sha256"],))[0] == 0
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (res["admission_id"],))[0] == "refused"
    assert _file_state(pdf) == before


@pg_only
@pytest.mark.parametrize("case", sorted(KILL))
def test_prefix_wrong_doi_with_the_manifest_claim_is_refused(pg, case):
    """The same row with its claimed title/authors/year: check 1 refuses (the registry record is another paper)
    and the binding verdict recorded beside it is binding-failed."""
    from litkb.admit import front
    k = KILL[case]
    row = PREFIX_ROWS[k["stem"]]
    pdf = VALIDATION / f"{k['stem']}.pdf"
    _need_file(pdf)
    ws, w = pg.ws(), pg.session("litkb_writer")
    res = front.admit_registry(w, ws, pg.tokens[ws], doi=row["doi"], key=f"{k['stem']}-c{uuid.uuid4().hex[:6]}",
                              claimed={"title": row["title"], "authors": row["authors"], "year": row["year"]},
                              file_path=pdf, root=VALIDATION.parent, agent="replay", session="replay-2",
                              client=RegistryStub(), pacer=_nopace())
    assert res["outcome"] == "refused", res
    assert res["checks"]["check1_study_exists"]["verdict"] == "fail"
    assert res["checks"]["check3_binding"]["verdict"] == "binding-failed"


@pg_only
@pytest.mark.parametrize("case", sorted(KILL))
def test_kill_corrected_doi_admits_the_same_file_and_its_case_variant_collides(pg, case):
    """KILL. The corrected DOI admits the same real file in place (rel_path under Validation/, sha256 = the
    manifest's, binding bound, nothing moved). Then the case variant of that DOI collides: the second admission
    returns the first one's work and writes no second work."""
    from litkb.admit import front
    k = KILL[case]
    row = PREFIX_ROWS[k["stem"]]
    pdf = VALIDATION / f"{k['stem']}.pdf"
    _need_file(pdf)
    before = _file_state(pdf)
    ws, w = pg.ws(), pg.session("litkb_writer")
    res = front.admit_registry(w, ws, pg.tokens[ws], doi=k["right"], key=k["stem"], file_path=pdf,
                              root=VALIDATION.parent, agent="replay", session="replay-3", client=RegistryStub(),
                              pacer=_nopace())
    assert res["outcome"] == "admitted", res
    fv = pg.one("SELECT f.sha256, v.rel_path, v.binding->>'verdict', v.work_id FROM litkb.files f "
                "JOIN litkb.file_versions v ON v.version_id = f.current_version_id WHERE f.id = %s", (res["file_id"],))
    assert fv[0] == row["sha256"] and fv[1] == f"Validation/{k['stem']}.pdf" and fv[2] == "bound"
    assert str(fv[3]) == str(res["work_id"])
    assert pg.one("SELECT title FROM litkb.main_works WHERE work_id = %s", (res["work_id"],))[0] == \
        CROSSREF[k["right"]]["title"][0]

    again = front.admit_registry(w, ws, pg.tokens[ws], doi=k["variant"], key=f"{k['stem']}-v{uuid.uuid4().hex[:6]}",
                                claimed={"title": row["title"], "authors": row["authors"], "year": row["year"]},
                                agent="replay", session="replay-3", client=RegistryStub(), pacer=_nopace())
    assert again["outcome"] == "duplicate", again
    assert str(again["work_id"]) == str(res["work_id"])
    n = pg.one("SELECT count(DISTINCT v.work_id) FROM litkb.identifiers i JOIN litkb.identifier_versions v "
               "ON v.identifier_id = i.id WHERE i.scheme = 'doi' AND i.value_norm = %s", (k["right"].lower(),))[0]
    assert n == 1
    assert _file_state(pdf) == before


# ── concurrency ───────────────────────────────────────────────────────────────────────────

def _in_thread(fn):
    box = {}

    def run():
        try:
            box["result"] = fn()
        except BaseException as e:  # handed to the asserting thread
            box["error"] = e
    th = threading.Thread(target=run, daemon=True)
    th.start()
    return th, box


def _wait_blocked(pg, pid, thread, seconds=15.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if pg.one("SELECT cardinality(pg_blocking_pids(%s)) > 0", (pid,))[0]:
            return True
        if not thread.is_alive():
            return False
        time.sleep(0.05)
    return False


@pg_only
def test_kill_concurrent_admissions_of_one_doi_leave_one_work(pg):
    """KILL. Two sessions admit one DOI at once, on two connections, under different keys. The holder's
    transaction stays open; the waiter is seen blocked on it; the holder commits. The waiter returns the holder's
    work as a clean `duplicate` (the identifier lock and lookup, not the unique index, decided it) and exactly
    one work carries the DOI."""
    from litkb.admit import front
    doi, title, rec = _synthetic()
    stub = RegistryStub({doi: rec})
    ws = pg.ws()
    holder, waiter = pg.session("litkb_writer"), pg.session("litkb_writer")
    holder.autocommit = False
    waiter_pid = pg.one("SELECT pg_backend_pid()", conn=waiter)[0]
    claimed = {"title": title, "authors": "Tester, T.", "year": 2020}

    def admit(conn, key):
        return front.admit_registry(conn, ws, pg.tokens[ws], doi=doi, claimed=claimed, key=key, agent="racer",
                                   session=f"race-{key[-4:]}", client=stub, pacer=_nopace())
    try:
        first = admit(holder, f"Tester_2020_race-a{uuid.uuid4().hex[:6]}")
        th, box = _in_thread(lambda: admit(waiter, f"Tester_2020_race-b{uuid.uuid4().hex[:6]}"))
        blocked = _wait_blocked(pg, waiter_pid, th)
        holder.commit()
    except BaseException:
        holder.rollback()
        raise
    th.join(30)
    assert not th.is_alive(), "the waiting admission never returned"
    assert "error" not in box, box.get("error")
    assert first["outcome"] == "admitted", first
    second = box["result"]
    assert second["outcome"] == "duplicate", second
    assert str(second["work_id"]) == str(first["work_id"])
    assert pg.one("SELECT count(*) FROM litkb.works w JOIN litkb.main_identifiers i ON i.work_id = w.id "
                  "WHERE i.scheme = 'doi' AND i.value_norm = %s", (doi.lower(),))[0] == 1
    assert blocked, "the second admission did not wait for the first"


# ── duplicates without identifiers ────────────────────────────────────────────────────────

def _tracker():
    return {r["ID"]: r for r in csv.DictReader(open(SCRIPTS.parent / "Reports" / "literature_tracker.csv",
                                                    encoding="utf-8", newline=""))}


def _seed_work(pg, ws, title, year):
    key = f"Seed_{year}_seeded-work-{uuid.uuid4().hex[:8]}"
    return pg.one("SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, 'seed', 'seed')",
                  (pg.jsonb({"key": key}), pg.jsonb({"type": "article", "title": title, "year": year, "authors": []}), ws))[0]


def _manual(pg, w, ws, title, authors, year, root, *, session="sessA", identifiers=(), token=None):
    from litkb.admit import front
    first = front.first_author_of(authors)
    pdf = root / "_litkb_staging" / "filed" / f"manual-{uuid.uuid4().hex[:8]}.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(paper_pdf(title, first))
    return front.admit_manual(w, ws, pg.tokens[ws] if token is None else token, title=title, authors=authors, year=year,
                             file_path=pdf, source_note="p2 test", root=root, agent="agentA", session=session,
                             identifiers=identifiers)


@pg_only
def test_kill_duplicate_pair_without_identifiers_goes_to_duplicate_review(pg, tmp_path):
    """KILL. Tracker rows 94 and 199 are a `Duplicate of` pair (Reports/literature_tracker.csv). Row 94 is held as
    a work; row 199, re-entered with no identifier, is sent to duplicate review (pg_trgm similarity of the
    normalised titles >= the calibrated 0.70, years within one), not admitted. Control: tracker rows 107/110 (the
    highest-scoring NON-duplicate pair in the calibration, 0.683) are not held back."""
    _need_pdftotext()
    t = _tracker()
    assert t["199"]["Duplicate of"].strip() == "94"
    ws, w = pg.ws(), pg.session("litkb_writer")
    seeded = _seed_work(pg, ws, t["94"]["Title"], int(t["94"]["Year"]))
    res = _manual(pg, w, ws, t["199"]["Title"], t["199"]["Author(s)"], int(t["199"]["Year"]), tmp_path)
    assert res["outcome"] == "duplicate-review", res
    assert str(seeded) in {str(m["work_id"]) for m in res["matches"]}
    cand = pg.one("SELECT c.state FROM litkb.admissions a JOIN litkb.candidates c ON c.id = a.candidate_id WHERE a.id = %s",
                  (res["admission_id"],))[0]
    assert cand == "duplicate-review"

    _seed_work(pg, ws, t["107"]["Title"], int(t["107"]["Year"]))
    ctl = _manual(pg, w, ws, t["110"]["Title"], t["110"]["Author(s)"], int(t["110"]["Year"]), tmp_path)
    assert ctl["outcome"] == "proposed", ctl


# ── manual admission: approval ────────────────────────────────────────────────────────────

@pg_only
def test_kill_admitter_cannot_approve_its_own_manual_admission(pg, tmp_path):
    """KILL. A manual admission is a proposal: main cannot see it. Its admitter's session approving it is refused
    by the database (admissions_second_session_signs_off, migration 0009), and nothing moves. Another session,
    in its own workstream, approves it: main's pointers move for the work, its identifier and its file."""
    _need_pdftotext()
    from litkb.admit import front
    title = f"A regional report nobody registered {uuid.uuid4().hex[:8]}"
    ws_a, ws_b = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    res = _manual(pg, w, ws_a, title, "Reporter, R.", 1987, tmp_path, session="sess-admit",
                  identifiers=[{"scheme": "url", "value": f"https://example.invalid/{uuid.uuid4().hex}"}])
    assert res["outcome"] == "proposed", res
    wid = res["work_id"]
    assert pg.one("SELECT current_version_id FROM litkb.works WHERE id = %s", (wid,))[0] is None
    with pytest.raises(pg.errors.CheckViolation, match="admissions_second_session_signs_off"):
        front.approve(w, ws_a, pg.tokens[ws_a], res["admission_id"], "agentA", "sess-admit")
    with pytest.raises(pg.errors.CheckViolation):
        front.approve(w, ws_b, pg.tokens[ws_b], res["admission_id"], "another-agent", " sess-admit ")
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (res["admission_id"],))[0] == "proposed"
    assert pg.one("SELECT count(*) FROM litkb.main_works WHERE work_id = %s", (wid,))[0] == 0
    ok = front.approve(w, ws_b, pg.tokens[ws_b], res["admission_id"], "agentA", "sess-approve")
    assert ok["outcome"] == "approved" and len(ok["moved"]) == 3, ok
    assert pg.one("SELECT count(*) FROM litkb.main_works WHERE work_id = %s", (wid,))[0] == 1
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (wid,))[0] == 1
    assert pg.one("SELECT count(*) FROM litkb.main_identifiers WHERE work_id = %s AND active", (wid,))[0] == 1
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (ws_a,))[0] == 0


@pg_only
def test_an_unapproved_manual_admission_is_held_at_promote_prepare(pg, tmp_path):
    """Check 4 cannot be walked round by promotion: prepare holds every work/identifier/file chain."""
    _need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    res = _manual(pg, w, ws, f"An unregistered proceedings paper {uuid.uuid4().hex[:8]}", "Speaker, S.", 1979, tmp_path)
    assert res["outcome"] == "proposed", res
    promoter = pg.session("litkb_promoter")
    pid = pg.one("SELECT litkb.promote_prepare(%s, %s, NULL)", (ws, "a" * 40), conn=promoter)[0]
    counts, conflicts = pg.one("SELECT counts, conflicts FROM litkb.promotions WHERE id = %s", (pid,))
    assert counts["prepared"] == 0 and counts["held"] == 2, counts
    assert all(any("admission:" in r for r in c["reasons"]) for c in conflicts if "reasons" in c), conflicts
    assert pg.one("SELECT current_version_id FROM litkb.works WHERE id = %s", (res["work_id"],))[0] is None


@pg_only
def test_approving_twice_or_a_registry_admission_is_refused(pg, tmp_path):
    _need_pdftotext()
    from litkb.admit import front
    ws_a, ws_b = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    res = _manual(pg, w, ws_a, f"A one-off technical note {uuid.uuid4().hex[:8]}", "Writer, W.", 1990, tmp_path)
    front.approve(w, ws_b, pg.tokens[ws_b], res["admission_id"], "b", "sess-b")
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        front.approve(w, ws_b, pg.tokens[ws_b], res["admission_id"], "b", "sess-b2")
    _h, work, ids = _good_payload()
    reg = _admit_sql(pg, w, ws_a, work, ids)
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        front.approve(w, ws_b, pg.tokens[ws_b], reg["admission_id"], "b", "sess-b3")


# ── the database's own checks, with evidence a client would never send ───────────────────

@pg_only
def test_db_admits_a_consistent_registry_record(pg):
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    res = _admit_sql(pg, w, ws, work, ids)
    assert res["outcome"] == "admitted", res
    assert pg.one("SELECT state FROM litkb.work_versions WHERE work_id = %s", (res["work_id"],))[0] == "promoted"


@pg_only
@pytest.mark.parametrize("case", ["claimed_ratio_low", "claimed_author_mismatch", "claimed_year_two_off",
                                  "not_registry_verified", "work_title_not_registry", "work_year_not_registry",
                                  "doi_only_no_claim_no_file", "no_registry_identifier"])
def test_db_check1_refuses_evidence_that_does_not_hold(pg, case):
    ws, w = pg.ws(), pg.session("litkb_writer")
    claimed = {"claimed_ratio_low": {"title_ratio": 0.5}, "claimed_author_mismatch": {"author_match": False},
               "claimed_year_two_off": {"year": 2022}}.get(case)
    _h, work, ids = _good_payload(claimed=False if case == "doi_only_no_claim_no_file" else claimed)
    if case == "not_registry_verified":
        ids[0]["verified_by"] = None
    elif case == "work_title_not_registry":
        work["title"] = "Heegard Floer invariants of Legendrian knots in contact three-manifolds"
    elif case == "work_year_not_registry":
        work["year"] = 2019
    elif case == "no_registry_identifier":
        ids = [{"scheme": "tracker", "value": "999", "verified_by": None, "evidence": {}}]
    res = _admit_sql(pg, w, ws, work, ids)
    assert (res["outcome"], res["refused_at"]) == ("refused", "check1_study_exists"), res
    assert res.get("work_id") is None


@pg_only
def test_db_year_rule_allows_one_year_when_title_and_author_match(pg):
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload(claimed={"year": 2021})
    assert _admit_sql(pg, w, ws, work, ids)["outcome"] == "admitted"


@pg_only
@pytest.mark.parametrize("case", ["ratio_low", "author_missing", "no_text_layer", "other_title", "no_matched_line"])
def test_db_check3_refuses_a_file_that_does_not_bind(pg, case):
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    kw = {"ratio_low": dict(ratio=0.36), "author_missing": dict(author_found=False),
          "no_text_layer": dict(ratio=0.0, text_layer=False), "no_matched_line": dict(matched="")}.get(case, {})
    f = _file(work["title"], **kw)
    if case == "other_title":
        f["binding"]["registry_title"] = "Some other paper entirely"
    res = _admit_sql(pg, w, ws, work, ids, file_json=f)
    assert (res["outcome"], res["refused_at"]) == ("refused", "check3_binding"), res
    assert res["checks"]["check3_binding"]["verdict"] == ("binding-pending" if case == "no_text_layer" else "binding-failed")
    assert pg.one("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (f["sha256"],))[0] == 0


@pg_only
def test_db_manual_admission_needs_a_bound_file(pg):
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = {"type": "report", "title": f"An unfiled report {uuid.uuid4().hex[:8]}", "year": 1980, "authors": []}
    res = _admit_sql(pg, w, ws, work, [], route="manual")
    assert (res["outcome"], res["refused_at"]) == ("refused", "check4_manual"), res
    res = _admit_sql(pg, w, ws, work, [{"scheme": "doi", "value": "10.5555/x", "verified_by": "crossref", "evidence": {}}],
                     route="manual", file_json=_file(work["title"]))
    assert (res["outcome"], res["refused_at"]) == ("refused", "check1_study_exists"), res


@pg_only
def test_db_candidate_must_belong_to_the_admitting_workstream(pg):
    ws_a, ws_b = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    cand = _cand(pg, w, ws_a)
    _h, work, ids = _good_payload()
    with pytest.raises(pg.errors.InsufficientPrivilege, match="another workstream"):
        _admit_sql(pg, w, ws_b, work, ids, candidate=cand)
    assert pg.one("SELECT state FROM litkb.candidates WHERE id = %s", (cand,))[0] == "new"


@pg_only
@pytest.mark.parametrize("case", ["missing", "another_workstreams_token"])
@pytest.mark.parametrize("op", ["admit", "approve_admission", "attach_file"])
def test_every_p2_write_requires_its_token(pg, op, case):
    ws, w = pg.ws(), pg.session("litkb_writer")
    token = None if case == "missing" else pg.tokens[pg.ws()]
    _h, work, ids = _good_payload()
    before = pg.one("SELECT (SELECT count(*) FROM litkb.admissions WHERE workstream_id = %(w)s) + "
                    "(SELECT count(*) FROM litkb.file_versions WHERE workstream_id = %(w)s)", {"w": ws})[0]
    with pytest.raises(pg.errors.InsufficientPrivilege, match="token refused"):
        if op == "admit":
            _admit_sql(pg, w, ws, work, ids, token=token, candidate=_cand(pg, w, ws))
        elif op == "approve_admission":
            pg.one("SELECT litkb.approve_admission(%s, %s, %s, 'a', 's')", (ws, token, uuid.uuid4()), conn=w)
        else:
            pg.one("SELECT litkb.attach_file(%s, %s, %s, %s, 'a', 's')", (ws, token, uuid.uuid4(), pg.jsonb(_file("t"))), conn=w)
    after = pg.one("SELECT (SELECT count(*) FROM litkb.admissions WHERE workstream_id = %(w)s) + "
                   "(SELECT count(*) FROM litkb.file_versions WHERE workstream_id = %(w)s)", {"w": ws})[0]
    assert after == before


@pg_only
def test_attach_file_binds_dedupes_and_needs_an_admitted_work(pg):
    ws, w = pg.ws(), pg.session("litkb_writer")
    q = "SELECT litkb.attach_file(%s, %s, %s, %s, 'agentA', 'sessA')"
    _h, work, ids = _good_payload()
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        pg.one(q, (ws, pg.tokens[ws], uuid.uuid4(), pg.jsonb(_file(work["title"]))), conn=w)
    wid = _admit_sql(pg, w, ws, work, ids)["work_id"]
    bad = _file(work["title"], ratio=0.4)
    assert pg.one(q, (ws, pg.tokens[ws], wid, pg.jsonb(bad)), conn=w)[0]["outcome"] == "refused"
    assert pg.one("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (bad["sha256"],))[0] == 0
    good = _file(work["title"])
    assert pg.one(q, (ws, pg.tokens[ws], wid, pg.jsonb(good)), conn=w)[0]["outcome"] == "attached"
    assert pg.one(q, (ws, pg.tokens[ws], wid, pg.jsonb(good)), conn=w)[0]["outcome"] == "duplicate-file"
    assert pg.one("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (good["sha256"],))[0] == 1


@pg_only
def test_attempt_statuses_cover_the_routes(pg):
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    wid = _admit_sql(pg, w, ws, work, ids)["work_id"]
    q = "SELECT litkb.record_acquisition_attempt(%s, %s, %s, NULL, %s, NULL, %s, NULL, NULL)"
    for route, status in [("annas", "quota-stop"), ("browser", "manual-step"), ("scihub", "blocked"),
                          ("open_access", "no-oa-copy"), ("annas", "duplicate-held")]:
        pg.one(q, (ws, pg.tokens[ws], wid, route, status), conn=w)
    with pytest.raises(pg.errors.CheckViolation):
        pg.one(q, (ws, pg.tokens[ws], wid, "annas", "made-up"), conn=w)


# ── acquisition end to end (stub routes, a temporary literature root) ────────────────────

def _admitted(pg, w, ws):
    from litkb.acquire import run
    hexid, work, ids = _good_payload()
    res = _admit_sql(pg, w, ws, work, ids, key=f"Tester_2020_synthetic-{hexid}")
    assert res["outcome"] == "admitted", res
    return run.work_record(w, work_id=res["work_id"])


def _store(tmp_path):
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def _oa(monkeypatch, url="https://oa.example/paper.pdf"):
    from litkb.acquire import open_access
    monkeypatch.setattr(open_access, "unpaywall_locations", lambda doi: ([url], "stub"))


def _acquire(pg, w, ws, work, store, pdf_bytes, routes=("open_access",), **kw):
    from litkb.acquire import run
    clients = {"open_access": RouteStub({"oa.example": (200, {}, pdf_bytes)})}
    return run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=routes, agent="acq", session="acq-1",
                       clients=clients, pacer=_nopace(), printer=lambda *a: None, **kw)


def _attempts(pg, wid):
    return pg.conn.execute("SELECT route, status, detail FROM litkb.acquisition_attempts WHERE work_id = %s ORDER BY at, id",
                           (wid,)).fetchall()


def _files_under(p):
    return sorted(x.name for x in Path(p).rglob("*") if x.is_file()) if Path(p).exists() else []


@pg_only
def test_acquire_files_a_download_that_binds(pg, tmp_path, monkeypatch):
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    _oa(monkeypatch)
    out = _acquire(pg, w, ws, work, store, paper_pdf(work["title"], "T. Tester"))
    assert out["outcome"] == "ok", out
    rel = pg.one("SELECT rel_path, binding->>'verdict', source_route FROM litkb.main_files WHERE work_id = %s",
                 (work["work_id"],))
    assert rel[0] == f"_litkb_staging/filed/{work['key']}.pdf" and rel[1] == "bound" and rel[2] == "open_access"
    assert (store.root / rel[0]).exists() and (store.root / rel[0]).with_suffix(".txt").exists()
    assert _files_under(store.incoming) == [] and _files_under(store.quarantine) == []
    assert [(a[0], a[1]) for a in _attempts(pg, work["work_id"])] == [("open_access", "ok")]
    again = _acquire(pg, w, ws, run.work_record(w, work_id=work["work_id"]), store, b"%PDF-1.4 unused")
    assert again["outcome"] == "already-held"


@pg_only
def test_acquire_quarantines_a_download_that_does_not_bind(pg, tmp_path, monkeypatch):
    _need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    _oa(monkeypatch)
    out = _acquire(pg, w, ws, work, store, paper_pdf("Tidal mixing fronts in the Irish Sea", "J. Simpson"))
    assert out["outcome"] == "not-acquired", out
    rows = _attempts(pg, work["work_id"])
    assert [(a[0], a[1]) for a in rows] == [("open_access", "binding-failed"), ("browser", "manual-step")]
    assert "attach" not in rows[0][2], "a file that did not bind was offered to the database"
    q = _files_under(store.quarantine)
    assert len(q) == 2 and any("__binding-failed__" in n for n in q), q
    assert _files_under(store.filed) == [] and _files_under(store.incoming) == []
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work["work_id"],))[0] == 0


@pg_only
def test_acquire_recognises_a_file_already_on_disk(pg, tmp_path, monkeypatch):
    _need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    data = paper_pdf(work["title"], "T. Tester")
    held = store.root / "Validation" / "Tester_2020_held-copy.pdf"
    held.write_bytes(data)
    _oa(monkeypatch)
    out = _acquire(pg, w, ws, work, store, data)
    assert out["outcome"] == "duplicate-held", out
    assert out["detail"]["on_disk"] == ["Validation/Tester_2020_held-copy.pdf"]
    assert _files_under(store.staging) == [] and _files_under(store.quarantine) == []
    assert held.read_bytes() == data


@pg_only
def test_acquire_recognises_a_file_already_in_the_database(pg, tmp_path, monkeypatch):
    _need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    data = paper_pdf(work["title"], "T. Tester")
    other = _admitted(pg, w, ws)
    fj = {"sha256": hashlib.sha256(data).hexdigest(), "rel_path": "Validation/elsewhere.pdf",
          "binding": _binding(other["title"])}
    assert pg.one("SELECT litkb.attach_file(%s, %s, %s, %s, 'a', 's')",
                  (ws, pg.tokens[ws], other["work_id"], pg.jsonb(fj)), conn=w)[0]["outcome"] == "attached"
    _oa(monkeypatch)
    out = _acquire(pg, w, ws, work, store, data)
    assert out["outcome"] == "duplicate-held", out
    assert out["detail"]["held_for_work"] == str(other["work_id"])
    assert _files_under(store.staging) == [] and _files_under(store.quarantine) == []


@pg_only
def test_acquire_does_not_retry_a_dead_route(pg, tmp_path):
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "annas", work["doi"], "not-in-archive", {"detail": "earlier"})
    stub = RouteStub({})                              # any archive request would raise
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=("annas",), agent="acq", session="acq-2",
                      annas_session=(stub, "SEKRIT"), pacer=_nopace(), printer=lambda *a: None)
    assert stub.calls == []
    assert [(a[0], a[1]) for a in _attempts(pg, work["work_id"])] == [("annas", "not-in-archive"), ("browser", "manual-step")]
    assert out["outcome"] == "not-acquired"


@pg_only
def test_archive_stops_at_the_quota_margin_and_redacts_the_key(pg, tmp_path):
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    store = _store(tmp_path)
    first, second = _admitted(pg, w, ws), _admitted(pg, w, ws)
    data = paper_pdf(first["title"], "T. Tester")
    _md5, routes = _annas_routes(data, first["doi"].lower(), left=10)
    stub = RouteStub(routes)
    budget = run.Budget(max_archive_downloads=5, quota_margin=50)
    key = f"SEKRIT-{uuid.uuid4().hex}"
    out = run.acquire(w, ws, pg.tokens[ws], first, store=store, routes=("annas",), agent="acq", session="acq-3",
                      budget=budget, annas_session=(stub, key), annas_pacer=_nopace(), pacer=_nopace(),
                      printer=lambda *a: None)
    assert out["outcome"] == "ok", out
    assert budget.used == 1 and budget.downloads_left == [10] and "safety margin" in budget.stopped
    n_calls = len(stub.calls)
    out2 = run.acquire(w, ws, pg.tokens[ws], second, store=store, routes=("annas",), agent="acq", session="acq-3",
                       budget=budget, annas_session=(stub, key), annas_pacer=_nopace(), pacer=_nopace(),
                       printer=lambda *a: None)
    assert len(stub.calls) == n_calls, "the archive was asked again after the quota margin was reached"
    assert [(a[0], a[1]) for a in _attempts(pg, second["work_id"])][0] == ("annas", "quota-stop")
    assert out2["outcome"] == "not-acquired"
    # a failed download whose API error echoes the key: the stored attempt never carries it
    third = _admitted(pg, w, ws)
    _m, eroutes = _annas_routes(b"%PDF-1.4 x", third["doi"].lower(), error=f"invalid key {key}")
    run.acquire(w, ws, pg.tokens[ws], third, store=store, routes=("annas",), agent="acq", session="acq-3",
                budget=run.Budget(), annas_session=(RouteStub(eroutes), key), annas_pacer=_nopace(), pacer=_nopace(),
                printer=lambda *a: None)
    rows = _attempts(pg, third["work_id"])
    assert rows[0][1] == "api-error", rows
    assert all(key not in json.dumps(r[2]) for r in rows)
    assert "<KEY>" in json.dumps(rows[0][2])


# ── the command line ──────────────────────────────────────────────────────────────────────

@pg_only
def test_cli_ws_open_and_status_never_print_the_token(pg, tmp_path, capsys):
    from litkb import commands, workstream
    slug = f"p2-cli-{uuid.uuid4().hex[:8]}"
    conn = lambda db: pg.session("litkb_writer")  # noqa: E731
    assert commands.main(["--dir", str(tmp_path), "ws", "open", slug, "--branch", "work/p2-cli"], connect=conn) == 0
    ws_id, token = workstream.load(tmp_path)
    assert commands.main(["--dir", str(tmp_path), "ws", "status"], connect=conn) == 0
    out = capsys.readouterr()
    assert token not in out.out + out.err
    assert str(ws_id) in out.out and slug in out.out
    with pytest.raises(workstream.WorkstreamFileExists):
        commands.main(["--dir", str(tmp_path), "ws", "open", slug + "-2"], connect=conn)


# ── live (LITKB_LIVE=1) ───────────────────────────────────────────────────────────────────

@live
def test_live_crossref_matches_the_fixture():
    from litkb.admit import registry
    from litkb.admit.resolver import REGISTRY_BACKOFF, REGISTRY_MIN_INTERVAL
    from litkb.netutil import Client, Pacer
    pacer = Pacer(interval=REGISTRY_MIN_INTERVAL, backoff=REGISTRY_BACKOFF)
    for doi, msg in CROSSREF.items():
        live_rec, st = registry.crossref_record(Client(), doi, pacer)
        fix = registry.parse_crossref(msg, doi)
        assert st == 200 and live_rec, (doi, st)
        assert (live_rec["title"], live_rec["first_author"], live_rec["year"]) == \
            (fix["title"], fix["first_author"], fix["year"]), doi


@live
def test_live_unpaywall_lists_an_open_access_copy():
    from litkb.acquire import open_access
    urls, note = open_access.unpaywall_locations("10.1371/journal.pone.0326562")
    assert urls, note

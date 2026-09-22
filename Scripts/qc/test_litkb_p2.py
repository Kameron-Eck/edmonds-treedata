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
import unicodedata
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


def make_pdf(lines, info=None):
    """A one-page text PDF (Helvetica, one line per entry) that pdftotext reads back. `info` writes a document
    information dictionary (/Creator, /Producer, ...) that pdfinfo reads back VERBATIM — NUL bytes included,
    which is how a scanned paper's metadata reaches litkb (the NUL tests below)."""
    content = "BT /F1 9 Tf 40 760 Td 12 TL " + " ".join(f"({_esc(ln)}) '" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1400 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    if info:
        objs.append("<< " + " ".join(f"/{k} ({_esc(v)})" for k, v in info.items()) + " >>")
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(
        f"{o:010d} 00000 n \n".encode() for o in offsets)
    trailer = f"<< /Size {len(objs) + 1} /Root 1 0 R" + (f" /Info {len(objs)} 0 R" if info else "") + " >>"
    out += f"trailer\n{trailer}\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def paper_pdf(title, author, salt=None, info=None):
    salt = salt or uuid.uuid4().hex
    filler = [f"Body text line {i} of a synthetic paper about canopy mapping and validation, id {salt}." for i in range(8)]
    return make_pdf(["Journal of Synthetic Studies 1 (2020) 1-10", title, f"{author} and A. Coauthor", ""] + filler,
                    info=info)


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


_DELETE_CALLS = {"remove", "unlink", "rmtree", "rmdir", "removedirs", "truncate"}   # on any owner
_SHUTIL_CALLS = {"move", "copy", "copy2", "copyfile", "copytree"}                   # shutil.X, or a bare X()
_WRITE_CALLS = {"write_bytes", "write_text"}                                         # Path.write_*: overwrite


def _delete_offenders(paths):
    """Calls that delete, move over, or overwrite a file (referee fix D6):
      * any .remove/.unlink/.rmtree/.rmdir/.removedirs/.truncate (os.*, Path.unlink, shutil.rmtree);
      * shutil.move/copy/copy2/copyfile/copytree, also imported bare (`from shutil import move`);
      * os.replace, and Path.replace(target) / Path.rename(target): a .replace/.rename call with exactly ONE
        positional argument (str.replace always takes two, and os.rename(src, dst) is the store's own move,
        which refuses an existing target on Windows and runs behind guard_new);
      * Path.write_bytes / Path.write_text, and open() with a "w" mode.
    A line carrying `store-scan: allow` is exempt; each such line states why."""
    found = []
    for path in paths:
        src = Path(path).read_text(encoding="utf-8")
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                name, owner, bare = func.attr, getattr(func.value, "id", ""), False
            elif isinstance(func, ast.Name):
                name, owner, bare = func.id, "", True
            else:
                continue
            one_target = len(node.args) == 1 and not node.keywords
            if name == "open":
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
                bad = isinstance(mode, ast.Constant) and isinstance(mode.value, str) and mode.value.startswith("w")
            elif name in _DELETE_CALLS and not bare:
                bad = True
            elif name in _SHUTIL_CALLS:
                bad = owner == "shutil" or bare
            elif name in _WRITE_CALLS:
                bad = not bare
            elif name == "replace":
                bad = not bare and (owner == "os" or one_target)
            elif name == "rename":
                bad = not bare and owner != "os" and one_target
            else:
                bad = False
            if bad and "store-scan: allow" not in lines[node.lineno - 1]:
                found.append(f"{Path(path).name}:{node.lineno}: {lines[node.lineno - 1].strip()}")
    return found


def test_acquisition_and_admission_code_hold_no_delete_path():
    """The 2026-09-12 loss of 149 PDFs: no module that can write in the literature store may delete, move over,
    truncate or overwrite a file. Eight lines carry an explicit `store-scan: allow`: the hash-index cache's write
    and replace and the audit CSV (outside the literature store), the four shutil.move calls of the ported aa_fetch
    filing path in annas.py (each behind an exists-loop or an exists-refusal, and fetch_one refuses any destination
    outside _litkb_staging), and hunt.py's page-1 snapshot, written into the DERIVED directory outside the
    literature root and then landed under _litkb_staging/web/ by the store itself."""
    files = _scanned_sources()
    assert len(files) >= 9, files
    assert _delete_offenders(files) == []
    allowed = [ln for f in files for ln in f.read_text(encoding="utf-8").splitlines() if "store-scan: allow" in ln]
    assert len(allowed) == 8, allowed


_SCAN_PROBES = {
    "os.remove": "import os\nos.remove('x')\n",
    "os.unlink": "import os\nos.unlink('x')\n",
    "os.replace": "import os\nos.replace('a', 'b')\n",
    "shutil.move": "import shutil\nshutil.move('a', 'b')\n",
    "bare move": "from shutil import move\nmove('a', 'b')\n",
    "shutil.rmtree": "import shutil\nshutil.rmtree('d')\n",
    "shutil.copyfile": "import shutil\nshutil.copyfile('a', 'b')\n",
    "Path.rename": "from pathlib import Path\nPath('a').rename('b')\n",
    "Path.replace": "from pathlib import Path\nPath('a').replace('b')\n",
    "Path.unlink": "from pathlib import Path\nPath('a').unlink()\n",
    "Path.write_bytes": "from pathlib import Path\nPath('a').write_bytes(b'x')\n",
    "open wb": "open('a', 'wb')\n",
}


@pytest.mark.parametrize("form", sorted(_SCAN_PROBES))
def test_the_no_delete_scan_fires_on_every_forbidden_form(tmp_path, form):
    """The scan is a gate only if it fires: each forbidden call planted in a probe module is reported."""
    p = tmp_path / "probe.py"
    p.write_text(_SCAN_PROBES[form], encoding="utf-8")
    assert _delete_offenders([p]) != [], form
    ok = tmp_path / "clean.py"
    ok.write_text("import os\n'abc'.replace('a', 'b')\nos.rename('a', 'b')\nopen('a', 'rb')\n", encoding="utf-8")
    assert _delete_offenders([ok]) == []


# ── the store's own writers: the scan above is a gate only while its file list is complete ──

_SCANNED_DIRS = ("acquire", "admit")          # the globs test_acquisition_and_admission_code_hold_no_delete_path reads
#: Modules OUTSIDE those directories that can write in the store, and are therefore read by the same scan.
#: `hunt.py` (2026-09-16) lands a download in `_litkb_staging/incoming`, moves it to `filed/` and quarantines
#: bytes that are not a whole PDF — every one of those through the Store, and every one of them a place the
#: next `rm -f` could go. A file here is scanned; a file that reaches the store and is in NEITHER list fails
#: the census below, which is what makes this a gate rather than a habit.
#: `ops/reaper.py` (S3, 2026-09-21) is the module whose whole PURPOSE is to act on files in staging that no
#: database row accounts for — the one place a delete would look most reasonable and be most final. It moves
#: them through Store.to_quarantine and writes a .reason.json, and it is scanned here so that stays true.
_SCANNED_FILES = ("hunt.py", "ops/reaper.py")
_STORE_READ_ONLY = {
    "migrate_legacy/sources.py":
        "imports LITERATURE_ROOT to BUILD READ paths under the topic folders (<topic>/manifest.csv, "
        "<topic>/<stem>.pdf) for the legacy loader. It opens nothing for writing and _delete_offenders reports no "
        "call in it at all, so no delete path can hide there.",
    "extract/queue.py":
        "the extraction queue (S4 run 3, migration 0029). It imports LITERATURE_ROOT in literature_root() "
        "to BUILD READ paths to bound PDFs (root / files.rel_path), which it opens only to hash and probe. "
        "Everything it writes goes under derived_root() — references.DERIVED_ROOT, outside Literture\\ — "
        "through write_atomic, whose one os.replace renames an artifact's own .partial onto that artifact; "
        "it never names _litkb_staging or _quarantine and never moves, renames or deletes a corpus file.",
}


def _scanned_sources():
    """The one file list both halves of the gate read: the scanned directories plus the named files."""
    pkg = PIPELINE / "litkb"
    return (sorted(p for d in _SCANNED_DIRS for p in (pkg / d).glob("*.py"))
            + sorted(pkg / f for f in _SCANNED_FILES))


def _store_strings_and_imports(path):
    """True when a module reaches the literature store IN CODE: it imports one of the store's path names, or names
    a store directory in a string that is not a docstring.

    Docstrings and --help text are excluded deliberately: litkb/commands.py names LITKB_LITERATURE_ROOT in an
    argparse help string and litkb/extract/inventory.py names _quarantine in its module docstring, and neither can
    write a byte. What cannot be excluded is the reverse — nothing can write into _litkb_staging without either
    constructing a Store or naming the directory — which is what makes this a completeness test."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("litkb.acquire.store"):
            if {a.name for a in n.names} & {"Store", "LITERATURE_ROOT", "STAGING", "QUARANTINE"}:
                return True
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = (n.body or [None])[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(
                    first.value.value, str):
                docs.add(id(first.value))
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
               and ("_litkb_staging" in n.value or "_quarantine" in n.value) for n in ast.walk(tree))


def test_the_no_delete_scan_reads_every_module_that_can_write_in_the_store():
    """The scan above reads litkb/acquire/*.py and litkb/admit/*.py, and that list is a gate only while it is
    COMPLETE: a module that landed, filed or quarantined a download from anywhere else in the package would sit
    outside it and could hold the next rm. Measured here, from the sources: the only modules reaching the store's
    own paths in code are acquire/{store,run,annas}.py, admit/front.py and hunt.py — all scanned — plus
    migrate_legacy/sources.py, which builds read paths and writes nothing. The _litkb_staging/incoming handlers
    are store.land / store.quarantine_new and run.land_and_attach / run.acquire in acquire/, and hunt.land_download
    / hunt.file_under_key, which is why hunt.py is in _SCANNED_FILES and not merely explained here."""
    pkg = PIPELINE / "litkb"
    scanned = {p.resolve() for p in _scanned_sources()}
    outside = [p for p in sorted(pkg.rglob("*.py"))
               if p.resolve() not in scanned and _store_strings_and_imports(p)]
    rel = sorted(p.relative_to(pkg).as_posix() for p in outside)
    unexplained = [r for r in rel if r not in _STORE_READ_ONLY]
    assert unexplained == [], ("these modules reach the literature store, and the no-delete scan does not read "
                               f"them: {unexplained}")
    assert rel == sorted(_STORE_READ_ONLY), ("_STORE_READ_ONLY names a module that no longer reaches the store: "
                                             f"{sorted(set(_STORE_READ_ONLY) - set(rel))}")


def test_the_store_writer_census_fires_on_a_module_that_reaches_the_store(tmp_path):
    """The census is a gate only if it fires (CLAUDE.md 3.4c): an import of Store, and a bare string naming the
    staging directory, are both reported; the same words inside a docstring are not."""
    def probe(src):
        p = tmp_path / f"probe{abs(hash(src))}.py"
        p.write_text(src, encoding="utf-8")
        return _store_strings_and_imports(p)
    assert probe("from litkb.acquire.store import Store\ndef f():\n    return Store()\n")
    assert probe("from litkb.acquire.store import LITERATURE_ROOT as R\nR\n")
    assert probe('import os\ndef f(root):\n    return os.path.join(root, "_litkb_staging", "incoming")\n')
    assert not probe('"""Counted 224 files excluding _quarantine (a docstring)."""\nimport os\n')
    assert not probe("from litkb.acquire.store import file_facts\nfile_facts\n")


def _harness():
    """The mutation harness as a module. It lives in qc/instruments/ and imports nothing from litkb."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("litkb_p2_mutations",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_p2_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_mutation_harness_holds_one_campaign_per_tree(tmp_path):
    """Measured 2026-09-15: a second campaign started while the first had a mutant applied died with "F5f:
    mutation target occurs 0 times" — a sound row, reported as broken, and the whole table aborted. The silent
    version is worse: make_worker_copy() copies the tree AS IT IS, so a mutant applied at that moment is inherited
    by every worker copy and every verdict from it is wrong while saying nothing.

    (This test lives here rather than in qc/test_litkb_harness_sites.py because qc/test_litkb_p2.py is the file
    this task owns; the harness's other self-checks are over there.)"""
    h = _harness()
    lock = tmp_path / "campaign.lock"
    held = h.take_lock(lock)
    assert held == lock and lock.exists()
    assert f"pid {os.getpid()}" in lock.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        h.take_lock(lock)
    assert "another mutation campaign holds" in str(e.value) and f"pid {os.getpid()}" in str(e.value)
    h.release_lock(lock)
    assert not lock.exists()
    h.release_lock(lock)                     # releasing a lock that is already gone is not an error
    h.release_lock(h.take_lock(lock))        # and it can be taken again afterwards
    assert not lock.exists()
    assert ".litkb-harness.lock" in h.COPY_IGNORE, "a worker copy would carry (and hash) the parent's lock"


def test_a_second_harness_run_refuses_and_mutates_nothing(tmp_path):
    """The gate where it counts: main() takes the lock BEFORE it pre-flights any row, so a second run leaves every
    source byte-for-byte untouched instead of half-mutating one."""
    lock = tmp_path / "campaign.lock"
    lock.write_text("pid 999999 started 2026-09-15T00:00:00\n", encoding="utf-8")
    run_py = PIPELINE / "litkb" / "acquire" / "run.py"
    before = hashlib.sha256(run_py.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, str(SCRIPTS / "qc" / "instruments" / "litkb_p2_mutations.py"),
                        "--only", "F5a"], cwd=str(SCRIPTS), capture_output=True, text=True,
                       env=dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(PIPELINE),
                                LITKB_HARNESS_LOCK=str(lock)))
    assert r.returncode != 0, r.stdout[-2000:]
    assert "another mutation campaign holds" in (r.stderr + r.stdout), (r.stderr or r.stdout)[-2000:]
    assert "pid 999999" in (r.stderr + r.stdout), "the refusal does not say who holds it"
    assert hashlib.sha256(run_py.read_bytes()).hexdigest() == before, "a refused campaign still touched a source"
    assert lock.read_text(encoding="utf-8").startswith("pid 999999"), "the refused run took the holder's lock"


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


HTML_SERVED_AS_PDF = (b"<!DOCTYPE html>\n<html><head><title>404 Not Found</title></head>\n"
                      b"<body><h1>Not Found</h1><p>The requested repository item does not exist.</p>"
                      b"</body></html>\n")


@pytest.mark.parametrize("case, shape, needle", [
    ("whole", "pdf", ""),
    ("html", "not-a-pdf", "look like HTML"),
    ("empty", "not-a-pdf", "0 bytes"),
    ("truncated", "truncated-pdf", "no %%EOF")])
def test_pdf_shape_tells_a_whole_pdf_from_html_and_from_a_truncated_one(case, shape, needle):
    """The one place that decides whether downloaded bytes are a PDF (litkb.acquire.store.pdf_shape). An HTML
    error page served under a .pdf name is the shape of the 2026-09-15 incident
    (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9); a header with no %%EOF near the end is a transfer that
    stopped before the trailer, which is a different fault with a different cause and gets its own name."""
    from litkb.acquire.store import pdf_shape
    whole = paper_pdf("A paper about canopy", "T. Tester")
    data = {"whole": whole, "html": HTML_SERVED_AS_PDF, "empty": b"", "truncated": whole[:len(whole) // 2]}[case]
    got, why = pdf_shape(data)
    assert got == shape, (got, why)
    assert needle in why, why
    assert not data or data[:40].decode("latin-1") not in why, \
        "the reason quotes the bytes: a served error page can echo a request URL, key and all"


def test_store_move_new_never_overwrites_and_never_leaves_staging(tmp_path):
    """D6 / R12: a move onto an existing file is refused and both files keep their bytes; a move into a topic
    folder is refused and the source stays where it was."""
    from litkb.acquire.store import Store, StoreRefused
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True)
    s = Store(root, index_cache=tmp_path / "cache.json")
    a = s.write_new(s.incoming / "A_2020_a-b.pdf", b"%PDF-1.4 a")
    b = s.write_new(s.quarantine / "B_2020_c-d.pdf", b"%PDF-1.4 b")
    with pytest.raises(StoreRefused, match="already exists"):
        s.move_new(a, b)
    assert a.read_bytes() == b"%PDF-1.4 a" and b.read_bytes() == b"%PDF-1.4 b"
    with pytest.raises(StoreRefused, match="outside"):
        s.move_new(a, root / "Validation" / "A_2020_a-b.pdf")
    assert a.exists() and not (root / "Validation" / "A_2020_a-b.pdf").exists()


@pytest.mark.parametrize("folder", ["_quarantine", "_litkb_staging/filed", "_litkb_staging/incoming", "ASPP",
                                    "Labeling/older", "other"])
def test_disk_index_covers_every_folder_of_the_store(tmp_path, folder):
    """D6 / R10: dedupe against the disk sees staging, quarantine and every topic folder, not only Validation."""
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True)
    data = b"%PDF-1.4 held in " + folder.encode() + uuid.uuid4().hex.encode()
    p = root / folder / "Held_2020_some-paper.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    idx = Store(root, index_cache=tmp_path / "cache.json").disk_index()
    assert idx["sha256"].get(hashlib.sha256(data).hexdigest()) == [f"{folder}/Held_2020_some-paper.pdf"]
    assert idx["md5"].get(hashlib.md5(data).hexdigest()) == [f"{folder}/Held_2020_some-paper.pdf"]


# ── D1: one DOI normaliser; D7: one label normaliser ─────────────────────────────────────

DOI_FORMS = [(r["form"].encode("ascii").decode("unicode_escape"), r["canonical"], r["note"])
             for r in csv.DictReader(open(FIX / "doi_forms.csv", encoding="utf-8", newline=""))]


def _invisible_codepoints():
    return [c for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF
            and (unicodedata.category(chr(c)) in ("Zs", "Zl", "Zp", "Cf") or chr(c).isspace())]


def test_doi_forms_python():
    """D1: every form in the shared table normalises to its canonical DOI in Python (the resolver's name is the
    same function)."""
    from litkb.admit.resolver import normalize_doi as resolver_normalize
    from litkb.textnorm import normalize_doi
    assert len(DOI_FORMS) >= 35
    assert [(n, f, normalize_doi(f)) for f, c, n in DOI_FORMS if normalize_doi(f) != c] == []
    assert all(resolver_normalize(f) == normalize_doi(f) for f, _c, _n in DOI_FORMS)


def test_every_invisible_character_is_removed_python():
    """D7 / D1: every whitespace or Zs/Zl/Zp/Cf code point is removed from a label and from a DOI, wherever it sits;
    visible characters are kept, and case is kept for labels."""
    from litkb.textnorm import norm_label, normalize_doi
    cps = _invisible_codepoints()
    assert len(cps) >= 190
    assert [hex(c) for c in cps if norm_label(f"a{chr(c)}b{chr(c)}") != "ab"] == []
    assert [hex(c) for c in cps if normalize_doi(f"{chr(c)}10.1/x{chr(c)}Y") != "10.1/xy"] == []
    assert norm_label("Sess-A_1.é/[x]") == "Sess-A_1.é/[x]"


@pytest.mark.parametrize("family, page_word", [
    ("Ward", "Towards wards"), ("Hall", "shall halls"), ("Long", "along belonging"), ("Park", "parks and parking"),
    ("Chen", "kitchen"), ("Wang", "Hwang wangs"), ("Li", "Li-ion lie lithium"), ("Rose", "arose roses")])
def test_binding_matches_the_surname_as_a_whole_token(family, page_word):
    """D2: the title under ANOTHER author's name, with a word containing the registry surname right beside it, does
    not bind; the same page under the registry author does."""
    from litkb.admit import binding
    title = f"Estimating urban canopy change from repeated aerial surveys of the city {family.lower()}x"
    other = _page(title, "Q. Someone-Else and R. Other", after_author=[f"with remarks {page_word} on the method"])
    b = binding.bind(None, title, family, page_text=other, info={})
    assert b["ratio"] >= 0.85 and not b["author_near_title"] and b["verdict"] == "binding-failed", b
    right = _page(title, f"T. {family} and A. Coauthor", after_author=[f"with remarks {page_word} on the method"])
    assert binding.bind(None, title, family, page_text=right, info={})["verdict"] == "bound"


@pytest.mark.parametrize("family, author_line, bound", [
    ("Pengra", "Bruce W. Pengraa,∗, Stephen V. Stehmanb", True),      # glued affiliation letter, 6-letter surname
    ("Geyer", "By CHARLES J. GEYERt and ELIZABETH A. THOMPSON", True),  # an OCR'd dagger
    ("Park", "J. Parka, K. Leeb", False),                               # 4 letters: no glued marker accepted
    ("De la Cruz", "Maria De La Cruz and P. Other", True),
    ("De la Cruz", "Maria DelaCruz and P. Other", True),
    ("O'Neil-Dunne", "Jarlath O’Neil-Dunne and S. MacFaden", True),
    ("Müller", "K. MULLER and J. Smith", True),
    ("Muller", "K. Müller and J. Smith", True)])
def test_binding_surname_forms(family, author_line, bound):
    from litkb.admit import binding
    title = "Quality control and assessment of interpreter consistency of annual land cover reference data"
    b = binding.bind(None, title, family, page_text=_page(title, author_line), info={})
    assert (b["verdict"] == "bound") is bound, b


def _page(title_line, author_line, *, before=(), after_author=(), filler=8, tail=()):
    body = [f"Body text line {i} of a synthetic paper about tree canopy mapping and its validation." for i in range(filler)]
    return "\n".join(["Journal of Synthetic Studies 1 (2020) 1-10", *before, title_line, author_line, *after_author, "",
                      *body, *tail])


_REF_TITLE = "Estimating urban canopy change from repeated aerial surveys of a mid-sized coastal city"


@pytest.mark.parametrize("case", ["heading", "bracketed", "author_year"])
def test_binding_refuses_a_title_that_appears_only_in_a_reference_list(case):
    """D2 (b): page 1 is another paper's reference list that cites the registry title on its own line, next to the
    registry author's name. It does not bind."""
    from litkb.admit import binding
    entries = {
        "heading": ["References", "Jones, K., 2011. A study of forests. J. Ecol. 3, 1-2.", "Smith, J., 2010.",
                    _REF_TITLE, "Journal of Synthetic Studies 4, 5-9."],
        "bracketed": ["[11] K. Jones, A study of forests, J. Ecol. 3 (2011) 1-2.", "[12] J. Smith,", _REF_TITLE,
                      "[13] A. Brown, Canopy things, Remote Sens. 1 (2012) 2-3."],
        "author_year": ["Jones, K., Brown, A., 2011. A study of forests. J. Ecol. 3, 1-2.", "Smith, J., Lee, K., 2010.",
                        _REF_TITLE, "Brown, A., 2012. Canopy things. Remote Sens. 1, 2-3."]}[case]
    page = "\n".join(["Remote Sensing Letters 9 (2018) 100-110", "A different paper on tidal mixing fronts",
                      "J. Simpson and K. Other", "", *[f"Body text line {i} about fronts and mixing." for i in range(6)],
                      *entries, "Further text of the other paper."])
    b = binding.bind(None, _REF_TITLE, "Smith", page_text=page, info={})
    assert b["best_any_ratio"] >= 0.85 and b["verdict"] != "bound", b


@pytest.mark.parametrize("n_ref, bound", [(2, False), (1, True)])
def test_binding_reference_list_rule_at_its_boundary(n_ref, bound):
    """Acceptance V2b (Reports/LITKB_P2_ACCEPTANCE_2026-09-14.md): the reference-list rule refuses a title window with
    EXACTLY 2 reference-shaped lines within REF_NEIGHBOURHOOD of it (one entry just above, one just below, no
    References heading, so only this rule can refuse). The control carries 1 such line and binds: one "Surname, I.,
    year" line beside a title is an author line, not a list."""
    from litkb.admit import binding
    above = "Jones, K., Brown, A., 2011. A study of forests. J. Ecol. 3, 1-2."
    below = "Smith, J., Lee, K., 2010. Canopy things. Remote Sens. 1, 2-3."
    entries = ([above] if n_ref == 2 else []) + [_REF_TITLE, below]
    page = "\n".join(["Remote Sensing Letters 9 (2018) 100-110", "A different paper on tidal mixing fronts",
                      "J. Simpson and K. Other", "", *[f"Body text line {i} about fronts and mixing." for i in range(6)],
                      *entries, "Further text of the other paper."])
    flags = binding._line_flags(binding.page_lines(page))
    assert sum(flags[1]) == n_ref and not any(flags[0]), flags
    b = binding.bind(None, _REF_TITLE, "Smith", page_text=page, info={})
    assert b["best_any_ratio"] == 1.0 and b["author_found"], b
    if bound:
        assert b["verdict"] == "bound", b
    else:
        assert b["verdict"] == "binding-failed" and "inside a reference list" in b.get("refused_windows", {}), b


@pytest.mark.parametrize("case", ["title_after_instruction", "title_on_instruction_line"])
def test_binding_refuses_a_please_cite_cover_over_another_paper(case):
    """D2 (c): a cover sheet's citation carries the registry title and author; the paper under it is another one."""
    from litkb.admit import binding
    cite = (["Please cite this article as:", f"Smith, J. (2010) {_REF_TITLE}.", "Journal of Synthetic Studies 1, 1-10."]
            if case == "title_after_instruction" else [f"Please cite: Smith, J. (2010) {_REF_TITLE}"])
    page = "\n".join([*cite, "", "Tidal mixing fronts in the Irish Sea", "J. Simpson and K. Other", "",
                      *[f"Body text line {i} about fronts and mixing in shelf seas." for i in range(8)]])
    b = binding.bind(None, _REF_TITLE, "Smith", page_text=page, info={})
    assert b["best_any_ratio"] >= 0.85 and b["verdict"] != "bound", b


def test_binding_keeps_a_same_paper_cover_whose_title_precedes_the_citation():
    """The Taylor & Francis download cover (measured on 9 held papers): its title and authors head the sheet ABOVE
    'To cite this article:'. That header window is admissible; the citation below it is not."""
    from litkb.admit import binding
    page = "\n".join(["Journal of Business & Economic Statistics", "Publication details:", _REF_TITLE,
                      "Layth C. Smith & Harry V. Roberts", "To cite this article: Layth C. Smith & Harry V. Roberts "
                      f"(1988) {_REF_TITLE}, Journal of X, 6:1, 87-95",
                      *[f"Taylor & Francis makes every effort line {i} to ensure the accuracy of the content." for i in range(6)]])
    b = binding.bind(None, _REF_TITLE, "Smith", page_text=page, info={})
    assert b["verdict"] == "bound" and b["line"] == 2, b


def test_binding_refuses_a_title_outside_the_title_region():
    from litkb.admit import binding
    filler = [f"Body text line {i} of the previous article, continued on this page." for i in range(binding.TITLE_REGION_LINES + 2)]
    page = "\n".join([*filler, _REF_TITLE, "T. Tester and A. Coauthor", "Abstract text of the new article."])
    b = binding.bind(None, _REF_TITLE, "Tester", page_text=page, info={})
    assert b["best_any_ratio"] >= 0.85 and b["verdict"] == "binding-failed", b
    near_top = "\n".join([*filler[:5], _REF_TITLE, "T. Tester and A. Coauthor", *filler[5:]])
    assert binding.bind(None, _REF_TITLE, "Tester", page_text=near_top, info={})["verdict"] == "bound"


def test_binding_needs_the_author_near_the_title():
    """The surname only far below the title (an acknowledgement, a correspondence line) is not an author line."""
    from litkb.admit import binding
    far = binding.AUTHOR_NEAR_LINES + 5
    page = _page(_REF_TITLE, "Q. Someone-Else and R. Other", filler=far,
                 tail=["Correspondence to T. Tester, who kindly read the draft."])
    b = binding.bind(None, _REF_TITLE, "Tester", page_text=page, info={})
    assert b["author_found"] and not b["author_near_title"] and b["verdict"] == "binding-failed", b


def test_binding_by_pdf_title_needs_the_author_in_the_metadata_or_the_title_region():
    from litkb.admit import binding
    page = "\n".join([f"Body text line {i} with no title on it at all, about canopy mapping." for i in range(10)])
    info = {"Title": _REF_TITLE, "Author": "Tester, T.; Coauthor, A."}
    b = binding.bind(None, _REF_TITLE, "Tester", page_text=page, info=info)
    assert b["verdict"] == "bound" and b["source"] == "pdf-title", b
    b = binding.bind(None, _REF_TITLE, "Tester", page_text=page, info={"Title": _REF_TITLE, "Author": "Someone Else"})
    assert b["verdict"] == "binding-failed", b


@pytest.mark.parametrize("n, k, ratio, verdict", [(23, 17, 0.85, "bound"), (29, 21, 0.84, "binding-failed")])
def test_binding_threshold_boundary_python(n, k, ratio, verdict):
    """D2 boundary: a page whose best title window scores EXACTLY 0.85 binds; exactly 0.84 does not. difflib's
    ratio is 2M/T: a 23-character title against its first 17 characters is 34/40, a 29-character title against its
    first 21 is 42/50."""
    from litkb.admit import binding
    title = "abcde fghij klmno pqrst uvwxy zabcd"[:n]
    b = binding.bind(None, title, "Tester", page_text=_page(title[:k], "T. Tester and A. Coauthor"), info={})
    assert b["ratio"] == ratio and b["author_near_title"], b
    assert b["verdict"] == verdict
    assert binding.verdict(0.85, True, True) == "bound" and binding.verdict(0.84, True, True) == "binding-failed"


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


@pytest.mark.parametrize("registry_family, expected", [
    ("PAGE", "Page"), ("HAWKES", "Hawkes"), ("BROOK", "Brook"), ("O'NEIL-DUNNE", "ONeilDunne"),
    ("DE LA CRUZ", "DeLaCruz"), ("DelaCruz", "DelaCruz"), ("McRoberts", "McRoberts"), ("O", "O")])
def test_make_key_is_the_same_whatever_case_the_registry_prints_the_surname_in(registry_family, expected):
    """Edge-pre1990 D-key: Crossref prints some older authors in capitals (Page 1954 under its OUP DOI is 'PAGE',
    under its JSTOR DOI 'Page'). The convention's surname is capitalised, so both give Page_1954_...; an all-capitals
    part keeps only its first capital, and mixed-case parts are left alone."""
    from litkb.admit.front import make_key
    assert make_key(registry_family, 1954, "CONTINUOUS INSPECTION SCHEMES") == f"{expected}_1954_continuous-inspection-schemes"


def test_scihub_challenge_is_recorded_blocked_and_not_bypassed():
    """`mirrors=` is passed EXPLICITLY since S3: the list moved to `litkb.config` and is four long
    (Kam's operating note names all four), and this row is about what the route DOES with a 403 and
    a captcha — one GET each, no retry with extra headers — not about how many mirrors exist. The
    list itself is covered by qc/test_litkb_hunt.py, `..._four_kams_note_names_and_the_env_...`."""
    from litkb.acquire import scihub
    stub = RouteStub({"sci-hub.ru": (403, {}, b"<html><title>Just a moment...</title></html>"),
                      "sci-hub.ren": (200, {}, b"<html><title>Verification</title>captcha</html>")})
    r = scihub.fetch_scihub("10.1/x", _nopace(), client=stub,
                            mirrors=("https://sci-hub.ru", "https://sci-hub.ren"))
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


ACCOUNT_PAGE = (FIX / "account_counter.html").read_text(encoding="utf-8")


def _account(used, limit=1000):
    """The saved account page with its counter set to used / limit (tags inside the numbers, as the site renders)."""
    return ACCOUNT_PAGE.replace("<strong>4 / 1000</strong>", f"<strong>{used} / {limit}</strong>").encode()


def _annas_routes(pdf, doi, left=900, error=None, used=4):
    md5 = hashlib.md5(pdf).hexdigest()
    fd = {"account_fast_download_info": {"downloads_left": left}}
    fd.update({"error": error} if error else {"download_url": "https://partner.example/f.pdf"})
    return md5, {"/account/": (200, {}, _account(used)),
                 "/scidb/": (200, {}, f'<a href="/md5/{md5}">record</a>'.encode()),
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
    # the route canonicalises the DOI itself before it asks the archive anything, so a URL spelling reaches the
    # archive — and gate 2's record comparison — as 10.1/known (per-call-site rule, row S18)
    stub2 = RouteStub(routes)
    r = annas.fetch_for_litkb(stub2, "SEKRIT", " https://doi.org/10.1/KNOWN/ ", _nopace(), known_md5=set())
    assert r["status"] == "downloaded", r
    assert any("10.1/known" in u for u in stub2.calls), stub2.calls


@pytest.mark.parametrize("page, expected", [
    ("account_counter.html", (4, 1000)),
    ("span_split", (24, 1000)),              # the site writes 24 as <span>2</span>4
    ("entities_and_newlines", (7, 1000)),
    ("account_counter_missing.html", None),  # the counter only in a comment and a script: never read
    ("account_counter_wording.html", None),  # "last 24 hours" / "left today": not the counter
    ("two_counters_disagree", None),
    ("limit_zero", None),
    ("empty", None)])
def test_account_counter_parser_reads_only_the_counter(page, expected):
    """Job 2: the account-wide quota counter is parsed from saved HTML; anything ambiguous fails closed (None)."""
    from litkb.acquire import annas
    base = ACCOUNT_PAGE
    html_ = {"span_split": base.replace("<strong>4 / 1000</strong>", "<strong><span>2</span>4 / 1000</strong>"),
             "entities_and_newlines": base.replace("<strong>4 / 1000</strong>", "<strong>7&nbsp;/\n  1000</strong>"),
             "two_counters_disagree": base + "<div>Fast downloads used (last 18 hours): <strong>9 / 1000</strong></div>",
             "limit_zero": base.replace("<strong>4 / 1000</strong>", "<strong>0 / 0</strong>"),
             "empty": ""}.get(page)
    if html_ is None:
        html_ = (FIX / page).read_text(encoding="utf-8")
    assert annas.parse_quota(html_) == expected
    assert annas.parse_quota(html_.encode("utf-8")) == expected


def test_read_quota_fails_closed_on_a_bad_answer():
    from litkb.acquire import annas
    assert annas.read_quota(RouteStub({"/account/": (200, {}, _account(12))})) == ((12, 1000), 200)
    assert annas.read_quota(RouteStub({"/account/": (302, {}, _account(12))}))[0] is None
    assert annas.read_quota(RouteStub({"/account/": (200, {}, b"<html>login</html>")}))[0] is None
    assert annas.read_quota(RouteStub({}))[0] is None                  # the stub raises: unreadable, never a crash


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


def _binding(title, ratio=0.97, author_found=True, text_layer=True, matched=None, author_near=True, region=True):
    b = {"verdict": "bound", "ratio": ratio, "matched": title if matched is None else matched,
         "registry_title": title, "author_found": author_found, "author_near_title": author_near,
         "text_layer": text_layer, "page": 1}
    if region:
        b["title_region"] = True
    return b


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
@pytest.mark.parametrize("second", ["same_spelling", "trailing_slash"])
def test_kill_concurrent_admissions_of_one_doi_leave_one_work(pg, second):
    """KILL. Two sessions admit one DOI at once, on two connections, under different keys. The holder's
    transaction stays open; the waiter is seen blocked on it; the holder commits. The waiter returns the holder's
    work as a clean `duplicate` (the identifier lock and lookup, not the unique index, decided it) and exactly
    one work carries the DOI. D1: the waiter's spelling may be a sibling (a trailing slash) of the holder's."""
    from litkb.admit import front
    doi, title, rec = _synthetic()
    stub = RegistryStub({doi: rec})
    ws = pg.ws()
    holder, waiter = pg.session("litkb_writer"), pg.session("litkb_writer")
    holder.autocommit = False
    waiter_pid = pg.one("SELECT pg_backend_pid()", conn=waiter)[0]
    claimed = {"title": title, "authors": "Tester, T.", "year": 2020}

    def admit(conn, key, spelling):
        return front.admit_registry(conn, ws, pg.tokens[ws], doi=spelling, claimed=claimed, key=key, agent="racer",
                                   session=f"race-{key[-4:]}", client=stub, pacer=_nopace())
    try:
        first = admit(holder, f"Tester_2020_race-a{uuid.uuid4().hex[:6]}", doi)
        th, box = _in_thread(lambda: admit(waiter, f"Tester_2020_race-b{uuid.uuid4().hex[:6]}",
                                           doi if second == "same_spelling" else doi + "/"))
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
    q = "SELECT litkb.approve_admission(%s, %s, %s, %s, %s)"
    with pytest.raises(pg.errors.CheckViolation, match="admissions_second_session_signs_off"):
        pg.one(q, (ws_a, pg.tokens[ws_a], res["admission_id"], "agentA", "sess-admit"), conn=w)
    with pytest.raises(pg.errors.CheckViolation):
        pg.one(q, (ws_b, pg.tokens[ws_b], res["admission_id"], "another-agent", " sess-admit "), conn=w)
    with pytest.raises(front.AdmissionError, match="own session"):
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
@pytest.mark.parametrize("ratio, outcome", [(0.84, "refused"), (0.8499, "refused"), (0.85, "admitted")])
def test_db_check3_threshold_boundary(pg, ratio, outcome):
    """D2 boundary in the database: binding evidence at ratio 0.84 is refused, at 0.85 admitted."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    res = _admit_sql(pg, w, ws, work, ids, file_json=_file(work["title"], ratio=ratio))
    assert res["outcome"] == outcome, res
    if outcome == "refused":
        assert res["refused_at"] == "check3_binding"


@pg_only
@pytest.mark.parametrize("case", ["ratio_low", "author_missing", "no_text_layer", "other_title", "no_matched_line",
                                  "author_not_near_title", "no_title_region_evidence"])
def test_db_check3_refuses_a_file_that_does_not_bind(pg, case):
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    kw = {"ratio_low": dict(ratio=0.36), "author_missing": dict(author_found=False),
          "no_text_layer": dict(ratio=0.0, text_layer=False), "no_matched_line": dict(matched=""),
          "author_not_near_title": dict(author_near=False), "no_title_region_evidence": dict(region=False)}.get(case, {})
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

def _admitted(pg, w, ws, title=None):
    """An admitted work. `title` gives it ANOTHER work's title, for the tests that offer one held file to two
    works: without it the second work's title is a fresh random one and the file's BINDING — not the sha256
    dedupe under test — decides the outcome. That made
    test_acquire_from_file_binds_an_unheld_file_in_a_topic_folder_in_place flake about one run in three: the
    synthetic titles differ only in a 12-hex tail, so their difflib ratio falls either side of BIND_RATIO by
    chance. Measured 2026-09-14 on an unmodified tree (1 of 4 runs), before any change in this commit."""
    from litkb.acquire import run
    hexid, work, ids = _good_payload()
    if title:                       # the registry record, the claim and the work all say the same title
        work = dict(work, title=title)
        ev = dict(ids[0]["evidence"], registry_title=title)
        if "claimed" in ev:
            ev["claimed"] = dict(ev["claimed"], title=title)
        ids = [dict(ids[0], evidence=ev), *ids[1:]]
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
@pytest.mark.parametrize("case, label, shape, needle", [
    ("html_served_as_pdf", "bad-file", "not-a-pdf", "look like HTML"),
    ("truncated_pdf", "truncated-pdf", "truncated-pdf", "no %%EOF")])
def test_acquire_keeps_a_bad_download_in_quarantine_and_never_deletes_it(pg, tmp_path, monkeypatch, case, label,
                                                                        shape, needle):
    """Friction 5 (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9): a link that answers with an HTML error page,
    and a transfer that stops before the trailer. Neither is a paper and neither is thrown away — the bytes are
    written into _quarantine/ under a name that says what they are, with a .reason.json beside them, and the run
    moves on. Nothing reaches a topic folder, filed/ or incoming/; the bytes are still readable afterwards, so the
    re-fetch never needs the file deleted to free the name."""
    _need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    whole = paper_pdf(work["title"], "T. Tester")
    planted = HTML_SERVED_AS_PDF if case == "html_served_as_pdf" else whole[:len(whole) // 2]
    _oa(monkeypatch)
    out = _acquire(pg, w, ws, work, store, planted)
    assert out["outcome"] == "not-acquired", out
    rows = _attempts(pg, work["work_id"])
    assert [(a[0], a[1]) for a in rows] == [("open_access", "bad-file"), ("browser", "manual-step")]
    kept = sorted(Path(store.quarantine).glob("*.pdf"))
    assert len(kept) == 1, _files_under(store.quarantine)
    assert f"__{label}__" in kept[0].name, kept[0].name
    assert kept[0].read_bytes() == planted, "the bad download's bytes were not kept as they were served"
    why = json.loads(kept[0].with_suffix(".reason.json").read_text(encoding="utf-8"))
    assert (why["status"], why["label"], why["shape"]) == ("bad-file", label, shape), why
    assert (why["sha256"], why["bytes"]) == (hashlib.sha256(planted).hexdigest(), len(planted)), why
    assert (why["work_key"], why["route"]) == (work["key"], "open_access"), why
    assert why["source_url"] == "https://oa.example/paper.pdf" and needle in why["reason"], why
    assert why["at"].endswith("+00:00") and why["at"].startswith("20"), why
    assert rows[0][2]["quarantined"] == store.rel(kept[0]), rows[0][2]
    assert rows[0][2]["quarantine_reason"] == store.rel(kept[0].with_suffix(".reason.json")), rows[0][2]
    assert _files_under(store.filed) == [] and _files_under(store.incoming) == []
    assert _files_under(store.root / "Validation") == [], "a bad download reached a topic folder"
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work["work_id"],))[0] == 0


@pg_only
@pytest.mark.parametrize("where", ["staging", "outside"])
def test_acquire_from_file_quarantines_a_bad_file_of_its_own_and_refuses_anyone_elses(pg, tmp_path, where):
    """§8.9 itself. The reviewer's curl answered with an HTML error page, it landed as
    _litkb_staging/incoming/IFLA_2017_library-reference-model.pdf, and it was removed with `rm -f` to free the name
    for the re-fetch — a delete inside the tree that exists because 149 PDFs were lost on 2026-09-12. Acquisition
    now takes the name off it by MOVING it into _quarantine with a reason beside it: it is acquisition's own tree,
    the bytes stay, and no delete is needed. A file anywhere else is the user's own and is neither moved nor
    copied — the refusal is recorded and the file is left exactly as it was."""
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    src = ((store.incoming if where == "staging" else tmp_path / "Downloads")
           / "IFLA_2017_library-reference-model.pdf")
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(HTML_SERVED_AS_PDF)
    before = _file_state(src)
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, from_file=src, agent="acq", session="acq-ff",
                      pacer=_nopace(), printer=lambda *a: None)
    assert out["outcome"] == "bad-file", out
    rows = _attempts(pg, work["work_id"])
    assert [(a[0], a[1]) for a in rows] == [("browser", "bad-file")]
    detail = rows[0][2]
    if where == "staging":
        kept = sorted(Path(store.quarantine).glob("*.pdf"))
        assert len(kept) == 1 and "__not-a-pdf__" in kept[0].name, _files_under(store.quarantine)
        assert kept[0].read_bytes() == HTML_SERVED_AS_PDF and not src.exists()
        why = json.loads(kept[0].with_suffix(".reason.json").read_text(encoding="utf-8"))
        assert why["moved_from"] == "_litkb_staging/incoming/IFLA_2017_library-reference-model.pdf", why
        assert (why["status"], why["shape"], why["work_key"]) == ("bad-file", "not-a-pdf", work["key"]), why
        assert detail["quarantined"] == store.rel(kept[0]) and detail["shape"] == "not-a-pdf", detail
    else:
        assert _file_state(src) == before, "a file acquisition did not create was moved, copied or rewritten"
        assert _files_under(store.quarantine) == [] and _files_under(store.staging) == []
        assert "left exactly where it lies" in detail["note"], detail
    assert _files_under(store.filed) == []
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
def test_acquire_from_file_binds_an_unheld_file_in_a_topic_folder_in_place(pg, tmp_path):
    """Edge-pre1990 D-inplace: a work admitted by DOI whose paper already sits in Validation/, held by no work. Before
    the fix `acquire --from-file` landed a copy, found the original in the disk index and stopped at duplicate-held,
    so the work could never get its file. Now the file is bound where it lies: rel_path is its own path, nothing is
    copied, moved or written; a second work offered the same file is duplicate-held; a file that does not bind stays
    put and is not attached."""
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    held = store.root / "Validation" / "Tester_2020_held-in-place.pdf"
    held.write_bytes(paper_pdf(work["title"], "T. Tester"))
    before = _file_state(held)
    kw = dict(store=store, agent="acq", session="acq-inplace", pacer=_nopace(), printer=lambda *a: None)
    out = run.acquire(w, ws, pg.tokens[ws], work, from_file=held, **kw)
    assert out["outcome"] == "ok", out
    row = pg.one("SELECT rel_path, binding->>'verdict', source_route FROM litkb.main_files WHERE work_id = %s",
                 (work["work_id"],))
    assert row == ("Validation/Tester_2020_held-in-place.pdf", "bound", "held-in-place"), row
    assert _files_under(store.staging) == [] and _files_under(store.quarantine) == [] and _file_state(held) == before
    assert [(a[0], a[1]) for a in _attempts(pg, work["work_id"])] == [("browser", "ok")]
    other = _admitted(pg, w, ws, title=work["title"])   # the same paper, a second work: the sha256 dedupe decides
    assert run.acquire(w, ws, pg.tokens[ws], other, from_file=held, **kw)["outcome"] == "duplicate-held"
    stray = store.root / "Validation" / "Someone_1999_other-paper.pdf"
    stray.write_bytes(paper_pdf("Tidal mixing fronts in the Irish Sea", "J. Simpson"))
    third, sb = _admitted(pg, w, ws), _file_state(stray)
    assert run.acquire(w, ws, pg.tokens[ws], third, from_file=stray, **kw)["outcome"] == "binding-failed"
    assert _file_state(stray) == sb and _files_under(store.quarantine) == []
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (third["work_id"],))[0] == 0


def _subtitled_payload(hexid=None, year=2020, author="Tester"):
    """A registry record that publishes a title AND a subtitle. Since migration 0020 the WORK is stored under the
    joined form and `registry_titles` lists every form the registry published, which is what check 1 compares the
    work's title against."""
    hexid = hexid or uuid.uuid4().hex[:12]
    doi, bare, _rec = _synthetic(hexid, year, author)
    sub = f"toward building entity matching management systems {hexid}"
    joined = f"{bare}: {sub}"
    ev = {"registry": "crossref", "registry_title": bare, "registry_titles": [joined, bare],
          "registry_first_author": author, "registry_year": year,
          "claimed": {"title": joined, "first_author": author, "year": year, "title_ratio": 1.0,
                      "author_match": True}}
    work = {"type": "article", "title": joined, "subtitle": sub, "authors": [{"family": author, "given": "T."}],
            "year": year}
    return hexid, bare, joined, work, [{"scheme": "doi", "value": doi, "verified_by": "crossref", "evidence": ev}]


@pg_only
def test_acquire_from_file_takes_a_pdf_that_already_lies_in_incoming(pg, tmp_path):
    """Found live 2026-09-15: `acquire --from-file _litkb_staging/incoming/X.pdf` deduplicated the file against
    ITSELF. acquire() hashes every *.pdf under the literature root before the from-file branch, staging included,
    so the handed-in file's own hash was in the index, land_and_attach answered `duplicate-held` and binding never
    ran — the work could never get its file, and the workaround in the field was to rename it to `.download`.
    incoming/ is a landing area and holds nobody's file yet, so it is dropped from the index the from-file branch
    uses. The guard that protects the CORPUS is untouched: bytes already held in the database are still refused."""
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    handed = store.incoming / "Handed_2020_by-curl.pdf"
    handed.parent.mkdir(parents=True, exist_ok=True)
    data = paper_pdf(work["title"], "T. Tester")
    handed.write_bytes(data)
    kw = dict(store=store, agent="acq", session="acq-incoming", pacer=_nopace(), printer=lambda *a: None)
    out = run.acquire(w, ws, pg.tokens[ws], work, from_file=handed, **kw)
    assert out["outcome"] == "ok", out
    row = pg.one("SELECT rel_path, binding->>'verdict' FROM litkb.main_files WHERE work_id = %s",
                 (work["work_id"],))
    assert row == (f"_litkb_staging/filed/{work['key']}.pdf", "bound"), row
    assert (store.root / row[0]).read_bytes() == data
    assert _files_under(store.quarantine) == []
    # and a GENUINE duplicate is still refused: the same bytes, already held for another work
    other = _admitted(pg, w, ws, title=work["title"])
    second = store.incoming / "Handed_2020_by-curl-again.pdf"
    second.write_bytes(data)
    again = run.acquire(w, ws, pg.tokens[ws], other, from_file=second, **kw)
    assert again["outcome"] == "duplicate-held", again
    held = _attempts(pg, other["work_id"])[0][2]
    assert held["held_for_work"] == str(work["work_id"]), held
    assert second.read_bytes() == data, "the refused file was moved or rewritten"


@pg_only
def test_acquire_binds_a_first_page_that_prints_only_the_bare_title_of_a_subtitled_work(pg, tmp_path):
    """Since migration 0020 a work is stored under the registry title joined with its subtitle ("Magellan: toward
    building entity matching management systems"), while a PDF's first page prints whichever form the publisher
    chose — usually the bare one. Binding the acquire path against the stored title ALONE would start refusing
    papers it bound the day before, on a change that was about keys and not about files. The admission path
    already tries every form (binding.bind_any); the acquire path now does the same, and records which form
    matched while keeping registry_title = the work's own title, which is what the database compares."""
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    hexid, bare, joined, payload, ids = _subtitled_payload()
    res = _admit_sql(pg, w, ws, payload, ids, key=f"Tester_2020_subtitled-{hexid[:8]}")
    assert res["outcome"] == "admitted", res
    work, store = run.work_record(w, work_id=res["work_id"]), _store(tmp_path)
    assert work["title"] == joined and work["title_forms"] == [joined, bare], work["title_forms"]
    handed = tmp_path / "Downloads" / "paper.pdf"
    handed.parent.mkdir(parents=True, exist_ok=True)
    handed.write_bytes(paper_pdf(bare, "T. Tester"))      # the first page prints the BARE title only
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, from_file=handed, agent="acq", session="acq-sub",
                      pacer=_nopace(), printer=lambda *a: None)
    assert out["outcome"] == "ok", out
    row = pg.one("SELECT binding->>'registry_title', binding->>'matched_title_form', binding->>'verdict' "
                 "FROM litkb.main_files WHERE work_id = %s", (work["work_id"],))
    assert row == (joined, bare, "bound"), row
    assert _files_under(store.quarantine) == []


@pytest.mark.parametrize("title, subtitle, forms", [
    ("Magellan: toward building entity matching management systems", "toward building entity matching management "
     "systems", ["Magellan: toward building entity matching management systems", "Magellan"]),
    ("Magellan", "", ["Magellan"]),
    ("Magellan", None, ["Magellan"]),
    ("A study - of fronts", "of fronts", ["A study - of fronts", "A study"]),
    ("Already the whole title", "a subtitle it does not end with", ["Already the whole title"]),
])
def test_the_title_forms_of_a_work_keep_its_stored_title_first(title, subtitle, forms):
    """forms[0] must stay the WORK's stored title: bind_any records it as registry_title and migration 0016's
    _check_binding refuses a binding measured against any other title than the work's."""
    from litkb.acquire.run import _title_forms
    assert _title_forms(title, subtitle) == forms


@pg_only
def test_acquire_binds_a_held_in_place_file_by_any_title_form(pg, tmp_path):
    """The SECOND call site of the same rule (the harness's per-call-site rule, and the reason it exists): a file
    already held in a topic folder is bound by front.file_evidence, not by land_and_attach. A work stored under
    "title: subtitle" whose held PDF prints only the bare title must bind there too."""
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    hexid, bare, joined, payload, ids = _subtitled_payload()
    res = _admit_sql(pg, w, ws, payload, ids, key=f"Tester_2020_subtitled-place-{hexid[:6]}")
    assert res["outcome"] == "admitted", res
    work, store = run.work_record(w, work_id=res["work_id"]), _store(tmp_path)
    held = store.root / "Validation" / "Tester_2020_held-bare-title.pdf"
    held.write_bytes(paper_pdf(bare, "T. Tester"))        # the page prints the BARE title only
    before = _file_state(held)
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, from_file=held, agent="acq", session="acq-place",
                      pacer=_nopace(), printer=lambda *a: None)
    assert out["outcome"] == "ok", out
    row = pg.one("SELECT rel_path, binding->>'registry_title', binding->>'matched_title_form' "
                 "FROM litkb.main_files WHERE work_id = %s", (work["work_id"],))
    assert row == ("Validation/Tester_2020_held-bare-title.pdf", joined, bare), row
    assert _file_state(held) == before and _files_under(store.staging) == []


@pg_only
def test_a_quarantined_file_can_bind_once_the_record_is_corrected(pg, tmp_path, monkeypatch):
    """Found live 2026-09-15 by the archive job: quarantine locked a file out for ever. A file that fails binding
    moves to _quarantine/, and the disk index hashes every *.pdf under the literature root — quarantine included —
    so the same bytes then read as "already on disk" and could never be offered again. Correcting the record
    changed nothing: `duplicate-held`, permanently (Konda_2016, Kopcke_2010 and Enamorado_2019 were locked this
    way in the live store). _quarantine/ holds exactly the files that are NOT held, so it is not part of the
    dedupe's corpus, and re-binding one is `acquire --from-file <the quarantined path>`. Nothing is deleted: the
    quarantined copy and its reason stay where they are."""
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    store = _store(tmp_path)
    # `right` gets a title of its own rather than a second synthetic one: two synthetic titles differ only in a
    # 12-hex tail, so whether the file binds to the WRONG work is decided by a difflib ratio that falls either
    # side of BIND_RATIO by chance (the flake _admitted's docstring records, met here on the first run).
    right = _admitted(pg, w, ws, title="Tidal mixing fronts in the Irish Sea")
    wrong = _admitted(pg, w, ws)
    data = paper_pdf(right["title"], "T. Tester")        # the paper of the SECOND work, offered to the first
    _oa(monkeypatch)
    out = _acquire(pg, w, ws, wrong, store, data)
    assert out["outcome"] == "not-acquired", out         # binding-failed: it is not that work's paper
    q = sorted(Path(store.quarantine).glob("*.pdf"))
    assert len(q) == 1 and "__binding-failed__" in q[0].name, _files_under(store.quarantine)
    before = _file_state(q[0])
    # the corrected record: the work whose paper this actually is, re-binding the quarantined bytes by hand
    fixed = run.acquire(w, ws, pg.tokens[ws], right, store=store, from_file=q[0], agent="acq", session="acq-requar",
                        pacer=_nopace(), printer=lambda *a: None)
    assert fixed["outcome"] == "ok", fixed
    row = pg.one("SELECT rel_path, binding->>'verdict' FROM litkb.main_files WHERE work_id = %s",
                 (right["work_id"],))
    assert row == (f"_litkb_staging/filed/{right['key']}.pdf", "bound"), row
    assert (store.root / row[0]).read_bytes() == data
    assert _file_state(q[0]) == before, "the quarantined copy was moved, rewritten or deleted"
    # and a GENUINE duplicate is still refused: the same bytes, now ACTIVE on that work
    third = _admitted(pg, w, ws, title=right["title"])
    again = run.acquire(w, ws, pg.tokens[ws], third, store=store, from_file=q[0], agent="acq", session="acq-requar",
                        pacer=_nopace(), printer=lambda *a: None)
    assert again["outcome"] == "duplicate-held", again
    assert _attempts(pg, third["work_id"])[0][2]["held_for_work"] == str(right["work_id"])


def test_the_dedupe_index_drops_staging_and_quarantine_only(tmp_path):
    """index_of_held is the whole of that rule, so it is worth pinning on its own: incoming/ and _quarantine/ go,
    every topic folder and filed/ stay, and the ARGUMENT is not modified (the archive's quota short-circuit reads
    the full index afterwards and must still see the quarantined md5)."""
    from litkb.acquire.run import index_of_held
    full = {"sha256": {"a": ["Validation/held.pdf", "_quarantine/held__binding-failed__a.pdf"],
                       "b": ["_litkb_staging/incoming/x.pdf"],
                       "c": ["_quarantine/only-here.pdf"],
                       "d": ["_litkb_staging/filed/f.pdf"]},
            "md5": {"m": ["_quarantine/only-here.pdf"]}}
    kept = index_of_held(None, full)
    assert kept["sha256"] == {"a": ["Validation/held.pdf"], "d": ["_litkb_staging/filed/f.pdf"]}, kept["sha256"]
    assert kept["md5"] == {}
    assert full["sha256"]["c"] == ["_quarantine/only-here.pdf"] and full["md5"]["m"], "the argument was modified"


@pg_only
def test_work_record_is_acquired_by_the_doi_it_was_reached_by(pg):
    """Edge-pre1990 G2: Page 1954 carries two DOIs (OUP and JSTOR). work_record kept whichever identifier row came
    back last, so `acquire --doi <the JSTOR one>` ran the archive on the OUP DOI and stored that as identifier_used."""
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    hexid, work, ids = _good_payload()
    second = dict(ids[0], value=f"10.2307/{int(hexid, 16) % 10 ** 7}")
    res = _admit_sql(pg, w, ws, work, ids + [second])
    assert res["outcome"] == "admitted", res
    for d in (ids[0]["value"], second["value"]):
        rec = run.work_record(w, doi=d)
        assert rec and rec["doi"] == d, (d, rec)
        assert run.work_record(w, doi=f"https://doi.org/{d.upper()}")["doi"] == d
    assert sorted(run.work_record(w, work_id=res["work_id"])["dois"]) == sorted([ids[0]["value"], second["value"]])


def test_jsonb_safe_removes_every_nul_character():
    from litkb.textnorm import jsonb_safe
    obj = {"Creator": "Acrobat 3.0 Capture Plug-in\x00\x00", "list": ["a\x00b", {"k\x00": "\x00"}], "n": 3, "t": True,
           "none": None}
    assert jsonb_safe(obj) == {"Creator": "Acrobat 3.0 Capture Plug-in", "list": ["ab", {"k": ""}], "n": 3, "t": True,
                               "none": None}


@pg_only
def test_a_nul_character_in_pdf_metadata_never_breaks_an_attach(pg, tmp_path, monkeypatch):
    """Edge-pre1990 D-nul: Bell 1977's held PDF reports Creator 'Acrobat 3.0 Capture Plug-in' followed by NUL bytes.
    Postgres jsonb refuses \\u0000, so binding that file in place raised UntranslatableCharacter and nothing was
    recorded. Every JSON document litkb sends now has its NUL characters removed first."""
    _need_pdftotext()
    from litkb.acquire import run
    from litkb.admit import binding
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    held = store.root / "Validation" / "Tester_2020_nul-metadata.pdf"
    held.write_bytes(paper_pdf(work["title"], "T. Tester"))
    real = binding.pdf_info
    monkeypatch.setattr(binding, "pdf_info", lambda p: dict(real(p), Creator="Acrobat 3.0 Capture Plug-in\x00\x00"))
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, agent="acq", session="acq-nul", pacer=_nopace(),
                      printer=lambda *a: None, from_file=held)
    assert out["outcome"] == "ok", out
    assert pg.one("SELECT pdf_metadata->>'Creator' FROM litkb.main_files WHERE work_id = %s",
                  (work["work_id"],))[0] == "Acrobat 3.0 Capture Plug-in"


@pytest.mark.parametrize("cmd", ["admit", "approve", "acquire"])
def test_the_cli_normalises_its_labels_before_any_write(tmp_path, monkeypatch, cmd):
    """Every litkb write carries an agent and a session label, and the sign-off rule compares them with their
    invisible characters removed (referee fix D7). The CLI is where a label enters, so `litkb admit/approve/
    acquire --session 'sess<ZWSP>'` must reach front/run already normalised — the third and fourth call sites of
    norm_label, which nothing exercised before the per-call-site rule
    (qc/instruments/litkb_p2_mutations.py, S25-S28)."""
    from litkb import commands
    from litkb.acquire import run
    from litkb.admit import front
    (tmp_path / ".litkb-workstream").write_text(json.dumps({"workstream_id": str(uuid.uuid4()), "token": "t" * 40}),
                                                encoding="utf-8")
    seen = {}

    def grab(*a, **kw):
        seen["labels"] = (kw.get("agent", a[-2] if len(a) > 1 else None), kw.get("session", a[-1]))
        return {"outcome": "admitted"}

    monkeypatch.setattr(front, "admit_registry", grab)
    monkeypatch.setattr(front, "approve", grab)
    monkeypatch.setattr(run, "acquire", grab)
    monkeypatch.setattr(run, "work_record", lambda conn, **kw: {"work_id": uuid.uuid4(), "key": "K_2020_x"})
    argv = {"admit": ["admit", "--doi", "10.5555/x"], "approve": ["approve", str(uuid.uuid4())],
            "acquire": ["acquire", "--key", "K_2020_x"]}[cmd]
    commands.main(["--dir", str(tmp_path), "--agent", "agent​", "--session", "sess​", *argv],
                  connect=lambda db: _NoConn())
    assert seen["labels"] == ("agent", "sess"), seen


class _NoConn:
    """A connection the CLI opens and closes and never queries (every command below is stubbed)."""

    def close(self):
        pass


def _nul_registry_case(tmp_path, nul="\x00\x00"):
    """A registry admission whose every JSON channel carries a NUL: the file's PDF metadata (p_file), the
    registry record's publisher (p_work) and a claimed field nothing compares (p_checks). Bell 1977's real shape
    is copied, not its bytes: Creator 'Acrobat 3.0 Capture Plug-in' followed by NULs."""
    hexid = uuid.uuid4().hex[:12]
    doi, title, rec = _synthetic(hexid, 2020, "Tester")
    rec = dict(rec, publisher=f"Synthetic Society Press{nul}")
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    pdf = root / "Validation" / f"Tester_2020_nul-front-{hexid}.pdf"
    pdf.write_bytes(paper_pdf(title, "T. Tester", info={"Creator": f"Acrobat 3.0 Capture Plug-in{nul}",
                                                        "Producer": f"Capture 3.0{nul}"}))
    claimed = {"title": title, "authors": "Tester, T.", "year": 2020, "scan_note": f"microfilm{nul}"}
    return doi, title, rec, root, pdf, claimed


@pg_only
def test_a_nul_in_pdf_metadata_never_breaks_a_registry_admission(pg, tmp_path):
    """E3f (Reports/LITKB_P2_ACCEPTANCE2_2026-09-14.md): the NUL-safe guard is textnorm.jsonb_safe, and it is
    called from TWO _jsonb helpers — litkb.acquire.run's and litkb.admit.front's. The acquisition side is covered
    by test_a_nul_character_in_pdf_metadata_never_breaks_an_attach; this covers the `admit --file` side, where
    front.file_evidence carries binding.pdf_info into litkb.admit()'s p_file. Without the guard psycopg raises
    UntranslatableCharacter and nothing is admitted."""
    _need_pdftotext()
    from litkb.admit import binding, front
    doi, title, rec, root, pdf, claimed = _nul_registry_case(tmp_path)
    assert "\x00" in binding.pdf_info(pdf).get("Creator", ""), "the fixture must really carry NULs in its metadata"
    ws, w = pg.ws(), pg.session("litkb_writer")
    res = front.admit_registry(w, ws, pg.tokens[ws], doi=doi, claimed=claimed, file_path=pdf, root=root,
                               agent="nul", session="nul-front", client=RegistryStub({doi: rec}), pacer=_nopace())
    assert res["outcome"] == "admitted", res
    meta, pub = pg.one("SELECT f.pdf_metadata, w.publisher FROM litkb.main_files f JOIN litkb.main_works w "
                       "ON w.work_id = f.work_id WHERE f.work_id = %s", (res["work_id"],))
    assert meta["Creator"] == "Acrobat 3.0 Capture Plug-in" and meta["Producer"] == "Capture 3.0", meta
    assert pub == "Synthetic Society Press", pub
    assert pg.one("SELECT checks->'claimed'->>'scan_note' FROM litkb.admissions WHERE id = %s",
                  (res["admission_id"],))[0] == "microfilm"


@pg_only
def test_an_attempt_detail_carrying_a_nul_is_still_recorded(pg):
    """A route's detail is whatever the far end said — an upstream error body can carry a NUL. record_attempt is
    the third _jsonb call site (per-call-site rule, row S3); without the guard the attempt is lost, and with it
    the reason the acquisition failed."""
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    wid = _admit_sql(pg, w, ws, work, ids)["work_id"]
    run.record_attempt(w, ws, pg.tokens[ws], wid, "open_access", ids[0]["value"], "no-oa-copy",
                       {"body": "unpaywall returned\x00\x00", "tried": ["oa.example\x00"]})
    row = pg.one("SELECT detail->>'body', detail->'tried'->>0 FROM litkb.acquisition_attempts WHERE work_id = %s",
                 (wid,))
    assert row == ("unpaywall returned", "oa.example"), row


@pg_only
def test_a_downloaded_file_with_nul_metadata_is_filed(pg, tmp_path, monkeypatch):
    """The download path's own copy of the guard (row S4): land_and_attach builds the file JSON from the
    downloaded PDF's own metadata, so a scanned paper fetched from a route carries the NULs too."""
    _need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    _oa(monkeypatch)
    out = _acquire(pg, w, ws, work, store,
                   paper_pdf(work["title"], "T. Tester", info={"Creator": "Acrobat 3.0 Capture Plug-in\x00\x00"}))
    assert out["outcome"] == "ok", out
    assert pg.one("SELECT pdf_metadata->>'Creator' FROM litkb.main_files WHERE work_id = %s",
                  (work["work_id"],))[0] == "Acrobat 3.0 Capture Plug-in"


@pg_only
def test_add_candidate_sends_no_nul_to_the_database(pg):
    """The same guard on front.add_candidate's three JSON arguments (raw, authors, ids), the one _jsonb call site
    an admission reaches before litkb.admit()."""
    from litkb.admit import front
    ws, w = pg.ws(), pg.session("litkb_writer")
    cid = front.add_candidate(w, ws, pg.tokens[ws], source="manual", title="A scanned report",
                              raw={"Creator": "Acrobat 3.0 Capture Plug-in\x00"},
                              authors=[{"family": "Tester\x00", "given": "T."}], year=1977,
                              ids={"note": "from microfilm\x00"})
    row = pg.one("SELECT raw_record->>'Creator', authors->0->>'family', ids->>'note' FROM litkb.candidates "
                 "WHERE id = %s",
                 (cid,))
    assert row == ("Acrobat 3.0 Capture Plug-in", "Tester", "from microfilm"), row


@pg_only
@pytest.mark.xfail(strict=True, reason="edge-pre1990 gap G1 (Reports/LITKB_EDGE_PRE1990_2026-09-14.md): a second DOI "
                                       "of an admitted work (Page 1954: OUP and JSTOR) admitted alone makes a second "
                                       "work; check 2 looks up identifiers only, and title review runs only without "
                                       "a strong identifier. Proposal, not fixed.")
def test_a_second_doi_of_an_admitted_work_does_not_make_a_second_work(pg):
    ws, w = pg.ws(), pg.session("litkb_writer")
    hexid, work, ids = _good_payload()
    assert _admit_sql(pg, w, ws, work, ids)["outcome"] == "admitted"
    alias = [dict(ids[0], value=f"10.2307/{int(hexid, 16) % 10**7}")]
    second = _admit_sql(pg, w, ws, work, alias)
    n = pg.one("SELECT count(*) FROM litkb.main_works WHERE title = %s", (work["title"],))[0]
    assert second["outcome"] in ("duplicate", "duplicate-review") and n == 1, (second, n)


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


def _plant_secret():
    """A fake key nothing else registered, and the undo for netutil._SECRETS (a shared module-level list: a key
    left registered by an earlier test would redact a later plant and make a stripped call site look guarded)."""
    from litkb import netutil
    snapshot = list(netutil._SECRETS)
    key = "FAKEKEY" + uuid.uuid4().hex + "+z"
    assert netutil.redact(key) == key, "the plant is already registered — the assertion below proves nothing"
    netutil.add_secret(key)

    def restore():
        netutil._SECRETS.clear()
        netutil._SECRETS.extend(snapshot)
    return key, restore


@pg_only
def test_a_secret_in_a_nested_attempt_detail_never_reaches_the_database(pg):
    """run.record_attempt -> run._redacted (and its own recursion). acquisition_attempts.detail is jsonb built
    from whatever a route reports; a key can sit inside a dict, inside a list, or inside a URL's query."""
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    work = _admitted(pg, w, ws)
    key, restore = _plant_secret()
    try:
        detail = {"reason": f"invalid key {key}",
                  "tried": [f"api0:401/invalid key {key}",
                            {"url": f"https://annas-archive.gl/dyn/api/fast_download.json?md5=x"
                                    f"&key={urllib.parse.quote(key)}&domain_index=0"}],
                  "downloads_left": 9}
        run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "annas", work["doi"], "api-error", detail)
        blob = json.dumps(_attempts(pg, work["work_id"]))
        assert key not in blob and urllib.parse.quote(key) not in blob, blob
        assert blob.count("<KEY>") == 3, blob
    finally:
        restore()


@pg_only
def test_a_key_in_a_source_url_is_redacted_before_the_file_row_is_written(pg, tmp_path, monkeypatch):
    """run.acquire's redact() around source_url. The open-access route returns the URL it fetched verbatim, and
    that URL is stored on the file version; acquire is the only place it passes through redact()."""
    _need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = _admitted(pg, w, ws), _store(tmp_path)
    key, restore = _plant_secret()
    try:
        _oa(monkeypatch, url=f"https://oa.example/paper.pdf?key={urllib.parse.quote(key)}")
        out = _acquire(pg, w, ws, work, store, paper_pdf(work["title"], "T. Tester"))
        assert out["outcome"] == "ok", out
        stored = pg.conn.execute(
            "SELECT fv.source_url FROM litkb.file_versions fv WHERE fv.work_id = %s", (work["work_id"],)).fetchall()
        blob = json.dumps(stored) + json.dumps(_attempts(pg, work["work_id"]))
        assert key not in blob and urllib.parse.quote(key) not in blob, blob
        assert "<KEY>" in json.dumps(stored), stored
    finally:
        restore()


# ── referee fixes (Reports/LITKB_P2_REFEREE_2026-09-14.md) ────────────────────────────────

@pg_only
def test_doi_forms_sql_equal_the_table_and_python(pg):
    """D1: the database's norm_identifier gives the canonical form for every row of the shared table."""
    from litkb.textnorm import normalize_doi
    got = pg.conn.execute("SELECT f, litkb.norm_identifier('doi', f) FROM unnest(%s::text[]) WITH ORDINALITY u(f, n) "
                          "ORDER BY n", ([f for f, _c, _n in DOI_FORMS],)).fetchall()
    assert [(n, f, g) for (f, c, n), (_f, g) in zip(DOI_FORMS, got) if g != c] == []
    assert all(g == normalize_doi(f) for f, g in got)


@pg_only
def test_every_invisible_character_is_removed_sql(pg):
    """D7 / D1: the database removes every code point the Python twin removes, from labels and from DOIs."""
    cps = _invisible_codepoints()
    rows = pg.conn.execute("SELECT c, litkb.norm_label('a' || chr(c) || 'b' || chr(c)), "
                           "litkb.norm_identifier('doi', chr(c) || '10.1/x' || chr(c) || 'Y') FROM unnest(%s::int[]) c",
                           (cps,)).fetchall()
    assert [hex(c) for c, lab, doi in rows if (lab, doi) != ("ab", "10.1/xy")] == []
    assert pg.one("SELECT litkb.norm_label(%s)", ("Sess-A_1.é/[x]",))[0] == "Sess-A_1.é/[x]"


@pg_only
def test_doi_sibling_spellings_admit_one_work(pg):
    """D1 (the referee's probe: 6 works for one DOI): every sibling spelling after the first is a duplicate of the
    first work, and the stored identifier value is the canonical DOI."""
    from litkb.admit import front
    doi, title, rec = _synthetic()
    stub = RegistryStub({doi: rec})
    ws, w = pg.ws(), pg.session("litkb_writer")
    claimed = {"title": title, "authors": "Tester, T.", "year": 2020}
    spellings = [doi, doi + "/", "doi: " + doi, "DOI:" + doi.upper(), "doi.org/" + doi, "https://www.doi.org/" + doi,
                 "urn:doi:" + doi, " " + doi + ".", "http://dx.doi.org/" + doi.upper() + "/"]
    res = [front.admit_registry(w, ws, pg.tokens[ws], doi=s, claimed=claimed, key=f"Tester_2020_sibling-{uuid.uuid4().hex[:8]}",
                                agent="sib", session="sib-1", client=stub, pacer=_nopace()) for s in spellings]
    assert [r["outcome"] for r in res] == ["admitted"] + ["duplicate"] * (len(spellings) - 1), res
    assert {str(r["work_id"]) for r in res} == {str(res[0]["work_id"])}
    assert pg.one("SELECT count(DISTINCT v.work_id), min(v.value), min(i.value_norm) FROM litkb.identifiers i "
                  "JOIN litkb.identifier_versions v ON v.identifier_id = i.id WHERE i.scheme = 'doi' "
                  "AND i.value_norm = %s", (doi,)) == (1, doi, doi)
    with pytest.raises(front.AdmissionError, match="not a DOI"):
        front.admit_registry(w, ws, pg.tokens[ws], doi="doi: none", agent="sib", session="sib-1", client=stub,
                             pacer=_nopace())


@pg_only
def test_db_stores_the_canonical_doi_and_refuses_a_non_doi(pg):
    """D1, the database as the authority: a client that sends a raw spelling still stores the canonical DOI."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    canonical = ids[0]["value"]
    ids[0]["value"] = "https://www.doi.org/" + canonical.upper() + "/"
    res = _admit_sql(pg, w, ws, work, ids)
    assert res["outcome"] == "admitted", res
    assert pg.one("SELECT v.value, i.value_norm FROM litkb.identifier_versions v JOIN litkb.identifiers i "
                  "ON i.id = v.identifier_id WHERE v.work_id = %s AND i.scheme = 'doi'", (res["work_id"],)) == \
        (canonical, canonical)
    _h, work2, ids2 = _good_payload()
    ids2[0]["value"] = "doi: not-a-doi"
    with pytest.raises(pg.errors.InvalidParameterValue, match="not a DOI"):
        _admit_sql(pg, w, ws, work2, ids2)


@pg_only
def test_admit_refuses_a_file_already_held_by_its_sha256(pg):
    """D6 / R9: a second work offering a file whose sha256 is already held is refused at file_duplicate (the unique
    index would only report `collided`)."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    _h, work, ids = _good_payload()
    f = _file(work["title"])
    first = _admit_sql(pg, w, ws, work, ids, file_json=f)
    assert first["outcome"] == "admitted", first
    _h2, work2, ids2 = _good_payload()
    res = _admit_sql(pg, w, ws, work2, ids2, file_json=dict(_file(work2["title"]), sha256=f["sha256"]))
    assert (res["outcome"], res.get("refused_at")) == ("refused", "file_duplicate"), res
    assert str(res["file_id"]) == str(first["file_id"])
    assert pg.one("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (f["sha256"],))[0] == 1


def _letters(n=8):
    return "".join(chr(97 + int(c, 16) % 26) for c in uuid.uuid4().hex[:n])


@pg_only
def test_a_key_collision_between_different_works_takes_the_a_then_b_suffix(pg):
    """D5: three different works (different DOIs) whose default keys coincide are admitted as <Surname>_2020_...,
    <Surname>_2020a_... and <Surname>_2020b_... (Scripts/docs/LITERATURE_CONVENTION.md); a fourth collides."""
    import re
    from litkb.admit import front
    surname = "Collide" + _letters()
    ws, w = pg.ws(), pg.session("litkb_writer")
    res = []
    for i in range(4):
        doi, _t, rec = _synthetic()
        rec["title"] = [f"Canopy mapping urban forests, variant {i} {uuid.uuid4().hex[:6]}"]
        rec["author"] = [{"family": surname, "given": "T.", "sequence": "first"}]
        claimed = {"title": rec["title"][0], "authors": f"{surname}, T.", "year": 2020}
        res.append(front.admit_registry(w, ws, pg.tokens[ws], doi=doi, claimed=claimed, agent="keys", session="keys-1",
                                        client=RegistryStub({doi: rec}), pacer=_nopace()))
    assert [r["outcome"] for r in res] == ["admitted", "admitted", "admitted", "collided"], res
    keys = [pg.one("SELECT key FROM litkb.works WHERE id = %s", (r["work_id"],))[0] for r in res[:3]]
    slug = "canopy-mapping-urban-forests"
    assert keys == [f"{surname}_2020_{slug}", f"{surname}_2020a_{slug}", f"{surname}_2020b_{slug}"], keys
    assert all(re.match(KEY_RE, k) for k in keys) and res[1]["key"] == keys[1]


@pg_only
def test_approve_refuses_an_admission_whose_workstream_was_abandoned(pg, tmp_path):
    """D3 (a): abandon the admitter's workstream, then approve its proposal from another: refused, nothing moves."""
    _need_pdftotext()
    from litkb.admit import front
    ws_a, ws_b = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    res = _manual(pg, w, ws_a, f"An abandoned county report {uuid.uuid4().hex[:8]}", "Reporter, R.", 1988, tmp_path,
                  session="sess-admit")
    assert res["outcome"] == "proposed", res
    pg.one("SELECT litkb.abandon_workstream(%s, %s)", (ws_a, pg.tokens[ws_a]), conn=w)
    with pytest.raises(pg.errors.InvalidParameterValue, match="not open"):
        front.approve(w, ws_b, pg.tokens[ws_b], res["admission_id"], "agentB", "sess-approve")
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (res["admission_id"],))[0] == "proposed"
    assert pg.one("SELECT count(*) FROM litkb.main_works WHERE work_id = %s", (res["work_id"],))[0] == 0


@pg_only
@pytest.mark.parametrize("first", ["approve", "abandon"])
def test_approve_and_abandon_of_the_admitters_workstream_wait_for_each_other(pg, tmp_path, first):
    """D3 (b, c), on two connections. Approve first: abandon waits for the approval, then abandons; the work is in
    main. Abandon first: approval waits for the abandon, then refuses; nothing moves."""
    _need_pdftotext()
    from litkb.admit import front
    ws_a, ws_b = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    res = _manual(pg, w, ws_a, f"A raced county report {uuid.uuid4().hex[:8]}", "Reporter, R.", 1989, tmp_path,
                  session="sess-admit")
    assert res["outcome"] == "proposed", res
    holder, waiter = pg.session("litkb_writer"), pg.session("litkb_writer")
    holder.autocommit = False
    waiter_pid = pg.one("SELECT pg_backend_pid()", conn=waiter)[0]

    def approve(conn):
        return front.approve(conn, ws_b, pg.tokens[ws_b], res["admission_id"], "agentB", "sess-approve")

    def abandon(conn):
        return pg.one("SELECT litkb.abandon_workstream(%s, %s)", (ws_a, pg.tokens[ws_a]), conn=conn)
    hold, wait = (approve, abandon) if first == "approve" else (abandon, approve)
    try:
        hold(holder)
        th, box = _in_thread(lambda: wait(waiter))
        blocked = _wait_blocked(pg, waiter_pid, th)
        holder.commit()
    except BaseException:
        holder.rollback()
        raise
    th.join(30)
    assert not th.is_alive(), "the waiting call never returned"
    state = pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (res["admission_id"],))[0]
    in_main = pg.one("SELECT count(*) FROM litkb.main_works WHERE work_id = %s", (res["work_id"],))[0]
    assert pg.one("SELECT state FROM litkb.workstreams WHERE id = %s", (ws_a,))[0] == "abandoned"
    if first == "approve":
        assert "error" not in box, box.get("error")
        assert (state, in_main) == ("approved", 1)
    else:
        assert isinstance(box.get("error"), pg.errors.InvalidParameterValue), box
        assert (state, in_main) == ("proposed", 0)
    assert blocked, f"the {'abandon' if first == 'approve' else 'approval'} did not wait"


@pg_only
def test_archive_cap_counts_every_issued_download_url_even_when_the_partner_404s(pg, tmp_path):
    """D4 / R11: the archive spends a download when it issues a URL. Seven works whose partner host answers 404,
    cap 5: five attempts end partner-404 and spend the cap, the sixth and seventh are quota-stop and never call
    fast_download."""
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    store = _store(tmp_path)
    works = [_admitted(pg, w, ws) for _ in range(7)]
    budget = run.Budget(max_archive_downloads=5, quota_margin=50)
    calls = []
    for work in works:
        _m, routes = _annas_routes(b"%PDF-1.4 never served " + uuid.uuid4().bytes, work["doi"].lower(), left=900)
        routes["partner.example"] = (404, {}, b"")
        stub = RouteStub(routes)
        run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=("annas",), agent="acq", session="acq-cap",
                    budget=budget, annas_session=(stub, "SEKRIT"), annas_pacer=_nopace(), pacer=_nopace(),
                    printer=lambda *a: None)
        calls.append(sum("fast_download" in u for u in stub.calls))
    assert [_attempts(pg, wk["work_id"])[0][1] for wk in works] == ["partner-404"] * 5 + ["quota-stop"] * 2
    assert budget.used == 5
    assert all(c >= 1 for c in calls[:5]) and calls[5:] == [0, 0], calls


@pg_only
@pytest.mark.parametrize("case", ["at_margin", "past_limit", "unreadable", "below_margin"])
def test_archive_reads_the_account_counter_before_every_download_request(pg, tmp_path, case):
    """Job 2: the account counter, not this run's count, decides. At used >= limit - margin, or with no readable
    counter, the route records quota-stop and never asks fast_download for a URL, and the run stops there. Below the
    margin it downloads, and the attempt's detail records the counter before and after."""
    _need_pdftotext()
    from litkb.acquire import run
    ws, w = pg.ws(), pg.session("litkb_writer")
    store = _store(tmp_path)
    work, nxt = _admitted(pg, w, ws), _admitted(pg, w, ws)
    margin = 50
    used = {"at_margin": 1000 - margin, "past_limit": 1003, "unreadable": 4, "below_margin": 1000 - margin - 1}[case]
    data = paper_pdf(work["title"], "T. Tester")
    _m, routes = _annas_routes(data, work["doi"].lower(), used=used)
    stub = RouteStub(routes)
    if case == "unreadable":
        routes["/account/"] = (200, {}, (FIX / "account_counter_wording.html").read_bytes())
    else:
        # the counter moves by one once a download URL has been issued
        routes["/account/"] = lambda url: (200, {}, _account(used + any("fast_download" in u for u in stub.calls)))
    budget = run.Budget(max_archive_downloads=5, quota_margin=margin)
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=("annas",), agent="acq", session="acq-quota",
                      budget=budget, annas_session=(stub, "SEKRIT"), annas_pacer=_nopace(), pacer=_nopace(),
                      printer=lambda *a: None)
    rows = _attempts(pg, work["work_id"])
    fast = sum("fast_download" in u for u in stub.calls)
    if case == "below_margin":
        assert out["outcome"] == "ok" and fast >= 1, (out, stub.calls)
        assert rows[0][1] == "ok" and rows[0][2]["quota"] == {"used_before": used, "used_after": used + 1,
                                                             "limit": 1000, "margin": margin, "account_status": 200}, rows
        assert not budget.stopped and budget.counter == [rows[0][2]["quota"]]
        return
    assert fast == 0, stub.calls
    assert [(a[0], a[1]) for a in rows][0] == ("annas", "quota-stop"), rows
    assert "no download URL requested" in rows[0][2]["detail"] and budget.stopped
    assert rows[0][2]["quota"]["used_before"] == (None if case == "unreadable" else used)
    n = len(stub.calls)
    run.acquire(w, ws, pg.tokens[ws], nxt, store=store, routes=("annas",), agent="acq", session="acq-quota",
                budget=budget, annas_session=(stub, "SEKRIT"), annas_pacer=_nopace(), pacer=_nopace(),
                printer=lambda *a: None)
    assert len(stub.calls) == n and _attempts(pg, nxt["work_id"])[0][1] == "quota-stop"


_LABEL_VARIANTS = {"nbsp": "sess-admit ", "zero_width_space": "sess-admit​", "bom": "﻿sess-admit",
                   "ideographic_space_inside": "sess　-admit", "word_joiner_inside": "sess-⁠admit",
                   "tab_inside": "sess-\tadmit"}


@pg_only
@pytest.mark.parametrize("variant", sorted(_LABEL_VARIANTS))
def test_self_approval_is_refused_whatever_invisible_characters_decorate_the_session(pg, tmp_path, variant):
    """D7: the admitter's session decorated with NBSP, a zero-width character, a BOM or an inner space is still the
    admitter's session, in Python (front.approve) and in the database (the raw function call)."""
    _need_pdftotext()
    from litkb.admit import front
    ws_a, ws_b = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    res = _manual(pg, w, ws_a, f"A decorated report {uuid.uuid4().hex[:8]}", "Reporter, R.", 1986, tmp_path,
                  session="sess-admit")
    label = _LABEL_VARIANTS[variant]
    with pytest.raises(front.AdmissionError, match="own session"):
        front.approve(w, ws_b, pg.tokens[ws_b], res["admission_id"], "another-agent", label)
    with pytest.raises(pg.errors.CheckViolation, match="admissions_second_session_signs_off"):
        pg.one("SELECT litkb.approve_admission(%s, %s, %s, %s, %s)",
               (ws_b, pg.tokens[ws_b], res["admission_id"], "another-agent", label), conn=w)
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (res["admission_id"],))[0] == "proposed"
    # and from the other side: a decorated ADMITTER label is normalised before the write, so the plain spelling
    # of it is still the admitter's own session (per-call-site rule, row S7 — admit's own call of _labels)
    other = _manual(pg, w, ws_a, f"A decorated report {uuid.uuid4().hex[:8]}", "Reporter, R.", 1986, tmp_path,
                    session=label)
    assert pg.one("SELECT admitter_session FROM litkb.admissions WHERE id = %s",
                  (other["admission_id"],))[0] == "sess-admit"
    with pytest.raises(front.AdmissionError, match="own session"):
        front.approve(w, ws_b, pg.tokens[ws_b], other["admission_id"], "another-agent", "sess-admit")


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


# ── check 3, the scan: OCR only where there is no text layer to read ────────────────────────

def _bind_env(monkeypatch, page_text, ocr_text, pages="22"):
    """binding with pdftotext, pdfinfo and Docling's OCR all stubbed, so the RULE is what is tested."""
    from litkb.admit import binding

    calls = []
    monkeypatch.setattr(binding, "first_page_text", lambda _p: page_text)
    monkeypatch.setattr(binding, "pdf_info", lambda _p: {"Pages": pages})

    def _ocr(pdf_path, **kw):
        calls.append(kw)
        return ocr_text
    monkeypatch.setattr(binding, "ocr_first_pages", _ocr)
    return binding, calls


def test_a_scan_with_no_text_layer_binds_on_its_ocr(monkeypatch):
    """The four scans have sat at `binding-pending` since P2: `pdftotext` reads nothing off a
    scan, so the title the rule needs is not there. Measured on the corpus after this fix,
    Anderson_1957, Hudson_1978, Hwang_1982 and Ogata_1998 all bind; Kingman_1962 does not, and
    that one is not this path's case — its page 1 HAS 2,219 characters of text."""
    title = "Statistical Inference about Markov Chains"
    ocr = _page(title, "T. W. ANDERSON AND LEO A. GOODMAN")
    binding, calls = _bind_env(monkeypatch, "\f", ocr)
    b = binding.bind_any_with_ocr("scan.pdf", [title], "Anderson")
    assert b["verdict"] == "bound" and len(calls) == 1, b
    assert b["page_text_source"].startswith("docling-ocr"), b
    # and the PDF's own fact is not rewritten by having read it another way: `text_layer` is what
    # stage 0 routes on, and a scan that OCR bound is still a scan
    assert b["text_layer"] is False, b


def test_a_page_that_has_text_is_never_re_read_by_ocr(monkeypatch):
    """THE CONTROL, and the half that keeps this from being a second oracle: a first page with a
    real text layer that does not bind is a `binding-failed`, and asking OCR the same question
    would let a paper bind on a reading nobody could reproduce from the file."""
    title = "The imbedding problem for finite Markov chains"
    printed = _page(title, "By J. F. Co KINGMkN")          # the publisher's own OCR, as stored
    truth = _page(title, "By J. F. C. KINGMAN")
    binding, calls = _bind_env(monkeypatch, printed, truth)
    b = binding.bind_any_with_ocr("kingman.pdf", [title], "Kingman")
    assert b["verdict"] == "binding-failed" and calls == [], b
    assert b["page_text_source"] == "pdftotext", b


def test_ocr_is_not_offered_for_a_book(monkeypatch):
    """`OCR_BIND_MAX_PAGES`: the corpus's 688-page book would spend an hour of GPU to answer a
    question its first page already answers, and whether to extract a book at all is not this
    function's decision to make."""
    from litkb.admit import binding

    monkeypatch.setattr(binding, "pdf_info", lambda _p: {"Pages": "688"})
    assert binding.ocr_first_pages("book.pdf") == ""
    assert binding.OCR_BIND_MAX_PAGES < 688
    # THE CONTROL: the same call on a paper-sized document is not refused HERE. It gets as far as
    # asking whether a Docling environment exists on this machine, which is a different answer
    # from "too big" — without this the test would also pass with the cap set to zero.
    from litkb.extract import docling as D

    seen = []
    monkeypatch.setattr(binding, "pdf_info", lambda _p: {"Pages": "22"})
    monkeypatch.setattr(D, "worker_available", lambda python=None: bool(seen.append(python)))
    assert binding.ocr_first_pages("paper.pdf") == "" and seen == [None]

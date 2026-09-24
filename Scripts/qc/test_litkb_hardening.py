r"""S4.5 builder A: the `hardening` subcommand, the ladder-1 run driver, and the hermetic-replay layer.

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_hardening.py -q -p no:cacheprovider

WHAT THE KNOWN-BADS ARE (the plan's "### S4.5" (c), builder A's rows, each shown to FIRE):

  a referee report dropped from the manifest                 -> unvalidated_items=1
  a Stage B rung's yield line deleted from the report         -> stage_b_rungs_unmeasured=1
  a cassette's 403 edited to 200 (CONSTRUCTED)                -> the replay disagrees with the register
  a socket opened during a replay                             -> refused, replay_network_calls=1
  the synthetic acquirer reinstated for a replayed row        -> replay_rows_graded_against_stubs=1
  a manifest edited after its freeze                          -> refused, nothing graded
  a gated counter no module defines                           -> `unread`, and the exit fails

Every CONSTRUCTED input says so in its name. No test here opens a socket to anything but loopback:
the recorded interactions come from a local HTTP server the test starts, or from the CONSTRUCTED
cassette under qc/fixtures/litkb_cassettes/.
"""
import http.server
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

SCRIPTS = Path(__file__).resolve().parent.parent
REGISTER = SCRIPTS / "qc" / "fixtures" / "litkb_hunt_edge_cases.json"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def A():
    return _load("litkb_acceptance", "qc/instruments/litkb_acceptance.py")


@pytest.fixture(scope="module")
def E():
    return _load("litkb_edge_run", "qc/instruments/litkb_edge_run.py")


@pytest.fixture(scope="module")
def HA():
    return _load("litkb_hardening_a", "qc/instruments/litkb_hardening_a.py")


@pytest.fixture(scope="module")
def LR():
    return _load("litkb_ladder_run", "qc/instruments/litkb_ladder_run.py")


@pytest.fixture(scope="module")
def C():
    from litkb import cassette

    return cassette


class _FakeClient:
    def __init__(self):
        import http.cookiejar

        self.cj = http.cookiejar.CookieJar()


# ── a local HTTP server: the only "host" these tests ever record ────────────────────────────

class _Server:
    """A loopback HTTP server with a fixed route table {path: (status, content_type, body)}."""

    def __init__(self, routes):
        table = routes

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                status, ctype, body = table.get(self.path.split("?", 1)[0], (404, "text/html", b"not here"))
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        return False


# ── the cassette: keys, scrubbing, bodies ────────────────────────────────────────────────────

def test_a_recorded_url_header_and_body_carry_no_credential(C, tmp_path):
    """The index is TRACKED: a registered secret, the archive's `key=`, Unpaywall's `email=` and a
    session cookie's value must reach none of its bytes — not the URL, not a header, not the body."""
    from litkb.netutil import add_secret

    secret = "s45a-constructed-secret-Q7Z"
    add_secret(secret)
    cas = C.Cassette(tmp_path / "idx.jsonl", "record", bodies=tmp_path / "bodies")
    cas.begin_row("row-1")
    # the secret also sits in a PATH segment, where only `netutil.redact` (not the query scrub) finds it
    url = f"https://h.constructed.invalid/files/{secret}/x?key={secret}&email=someone@constructed.invalid&x=1"
    cas.record(_FakeClient(), url, {"Accept": "text/html"}, True, f"key={secret}".encode(),
               (200, {"Set-Cookie": "sess=cookievalue123", "Location": f"https://h.invalid/?key={secret}"},
                f"your key is {secret}".encode()))
    raw = (tmp_path / "idx.jsonl").read_bytes()
    for leaked in (secret.encode(), b"someone@constructed.invalid", b"cookievalue123"):
        assert leaked not in raw, leaked
    e = json.loads(raw.splitlines()[1])
    assert "key=<KEY>" in e["key"]["url"] and "email=<KEY>" in e["key"]["url"], e["key"]["url"]
    assert e["response"]["body"]["scrubbed"] is True


def test_small_bodies_inline_while_pdfs_and_large_bodies_go_to_the_store(C, tmp_path):
    """64 KiB threshold (module docstring); a PDF is never inlined whatever its size."""
    cas = C.Cassette(tmp_path / "idx.jsonl", "record", bodies=tmp_path / "bodies")
    small, pdf, big = b"<html>small</html>", b"%PDF-1.4 tiny", b"x" * (C.INLINE_MAX_BYTES + 1)
    for i, body in enumerate((small, pdf, big)):
        cas.record(_FakeClient(), f"http://127.0.0.1/{i}", {"Accept": "*/*"}, True, None, (200, {}, body))
    got = [json.loads(ln)["response"]["body"] for ln in (tmp_path / "idx.jsonl").read_bytes().splitlines()[1:]]
    assert "inline_b64" in got[0] and not got[0].get("stored")
    assert got[1].get("stored") and "inline_b64" not in got[1]
    assert got[2].get("stored") and "inline_b64" not in got[2]
    for b in got[1:]:
        assert cas.body_path(b["sha256"]).is_file()


def test_record_then_replay_through_the_client_against_a_local_server(C, tmp_path):
    """RECORD through `netutil.Client` against a loopback server, stop the server, REPLAY: the same
    (status, body) come back and no socket is opened — the guard around the replay allows nothing."""
    from litkb.netutil import Client

    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    with _Server({"/a": (200, "text/plain", b"alpha"), "/b": (403, "text/html", b"Just a moment...")}) as srv:
        rec = C.Cassette(idx, "record", bodies=bodies)
        rec.begin_row("r1")
        c = Client(base="", cassette=rec)
        live = [c.get(f"{srv.base}/a")[::2], c.get(f"{srv.base}/b")[::2]]
    rep = C.Cassette(idx, "replay", bodies=bodies)
    rep.begin_row("r1")
    guard = C.SocketGuard(allow_hosts=(), label="replay")
    with guard:
        c2 = Client(base="", cassette=rep)
        replayed = [c2.get(f"{srv.base}/a")[::2], c2.get(f"{srv.base}/b")[::2]]
    assert replayed == live == [(200, b"alpha"), (403, b"Just a moment...")]
    assert guard.attempts == [], guard.attempts
    assert rep.stale() == {"unplayed": [], "misses": []}


def test_a_request_the_cassette_never_saw_is_a_named_miss_never_the_network(C, tmp_path):
    """A replay MISS is `CassetteMiss`, kept in `misses` — and a request asked once more than the live
    run asked it is a miss too (a replay that retries more has diverged)."""
    from litkb.netutil import Client

    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    with _Server({"/a": (200, "text/plain", b"alpha")}) as srv:
        rec = C.Cassette(idx, "record", bodies=bodies)
        rec.begin_row("r1")
        Client(base="", cassette=rec).get(f"{srv.base}/a")
    rep = C.Cassette(idx, "replay", bodies=bodies)
    rep.begin_row("r1")
    c = Client(base="", cassette=rep)
    assert c.get(f"{srv.base}/a")[2] == b"alpha"
    with pytest.raises(C.CassetteMiss, match="asked 2 times, recorded 1"):
        c.get(f"{srv.base}/a")
    with pytest.raises(C.CassetteMiss, match="never recorded"):
        c.get(f"{srv.base}/never")
    assert [m["why"] for m in rep.misses] == ["asked 2 times, recorded 1", "never recorded"]


def test_a_stored_body_that_is_missing_or_altered_fails_closed(C, tmp_path):
    from litkb.netutil import Client

    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    with _Server({"/p.pdf": (200, "application/pdf", b"%PDF-1.4 a stored body")}) as srv:
        rec = C.Cassette(idx, "record", bodies=bodies)
        Client(base="", cassette=rec).get(f"{srv.base}/p.pdf")
    sha = rec.recorded[0]["response"]["body"]["sha256"]
    p = rec.body_path(sha)
    p.write_bytes(b"%PDF-1.4 ALTERED")
    rep = C.Cassette(idx, "replay", bodies=bodies)
    with pytest.raises(C.CassetteBodyMissing, match="does not hash"):
        Client(base="", cassette=rep).get(f"{srv.base}/p.pdf")
    p.unlink()
    rep2 = C.Cassette(idx, "replay", bodies=bodies)
    with pytest.raises(C.CassetteBodyMissing, match="is not in"):
        Client(base="", cassette=rep2).get(f"{srv.base}/p.pdf")
    assert rep2.misses and "is not in" in rep2.misses[0]["why"]


def test_a_rerecorded_row_supersedes_its_old_take(C, tmp_path):
    """A resumed run that re-records a row replaces the row's old recording whole."""
    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    for body in (b"first take", b"second take"):
        cas = C.Cassette(idx, "record", bodies=bodies)
        cas.begin_row("r1")
        cas.record(_FakeClient(), "http://127.0.0.1/a", {"Accept": "*/*"}, True, None, (200, {}, body))
    rep = C.Cassette(idx, "replay", bodies=bodies)
    rep.begin_row("r1")
    assert len(rep.entries) == 1
    from litkb.netutil import Client

    assert Client(base="", cassette=rep).get("http://127.0.0.1/a", accept="*/*")[2] == b"second take"


def test_unplayed_entries_and_misses_are_the_staleness_diff(C, HA, tmp_path):
    from litkb.netutil import Client

    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    with _Server({"/a": (200, "text/plain", b"a"), "/b": (200, "text/plain", b"b")}) as srv:
        rec = C.Cassette(idx, "record", bodies=bodies)
        c = Client(base="", cassette=rec)
        c.get(f"{srv.base}/a")
        c.get(f"{srv.base}/b")
    rep = C.Cassette(idx, "replay", bodies=bodies)
    c = Client(base="", cassette=rep)
    c.get(f"{srv.base}/a")
    with pytest.raises(C.CassetteMiss):
        c.get(f"{srv.base}/c")
    st = rep.stale()
    assert [u["url"].rsplit("/", 1)[1] for u in st["unplayed"]] == ["b"]
    assert [m["url"].rsplit("/", 1)[1] for m in st["misses"]] == ["c"]
    assert HA.count_stale({"stale": st}) == 2


# ── the socket guard ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def listener():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(4)
    yield s.getsockname()[1]
    s.close()


def test_the_guard_counts_and_refuses_a_connect_outside_its_allow_set(C, listener):
    """CONSTRUCTED: a guard that allows NOTHING (the replay's setting) treats this process's own
    loopback listener as the outside world, so the refusal is shown without a packet leaving."""
    g = C.SocketGuard(allow_hosts=(), label="constructed")
    with g, socket.socket() as s:
        with pytest.raises(C.NetworkBlocked, match="refused connect to 127.0.0.1"):
            s.connect(("127.0.0.1", listener))
    assert [(a["host"], a["refused"]) for a in g.blocked] == [("127.0.0.1", True)]


def test_with_the_refusal_off_the_connect_still_counts(C, listener):
    """Counting and refusing are separate steps: the plan's `replay_network_calls=1 if it connects`."""
    g = C.SocketGuard(allow_hosts=(), refuse=False, label="observer")
    with g, socket.socket() as s:
        s.connect(("127.0.0.1", listener))
    assert [(a["host"], a["refused"]) for a in g.blocked] == [("127.0.0.1", False)]


def test_the_default_guard_allows_loopback_and_refuses_a_remote_lookup(C, listener):
    g = C.SocketGuard(label="default")
    with g:
        with socket.socket() as s:
            s.connect(("127.0.0.1", listener))
        with pytest.raises(C.NetworkBlocked, match="getaddrinfo"):
            socket.getaddrinfo("192.0.2.1", 80)       # numeric (TEST-NET-1): no DNS query either way
    assert [a["host"] for a in g.blocked] == ["192.0.2.1"]
    assert any(a["allowed"] and a["host"] == "127.0.0.1" for a in g.attempts)


def test_the_conftest_guard_fails_a_test_that_reaches_for_the_network(tmp_path):
    """The autouse fixture in qc/conftest.py, run for real: a COPY of it beside two constructed tests,
    one that looks up a non-loopback address and one that does not. The first must ERROR at teardown
    with the finding; the second must pass. The lookup is numeric, so no DNS query leaves either way."""
    (tmp_path / "conftest.py").write_bytes((SCRIPTS / "qc" / "conftest.py").read_bytes())
    (tmp_path / "test_constructed_net.py").write_text(
        "import socket\n\n"
        "def test_reaches():\n"
        "    try:\n"
        "        socket.getaddrinfo('192.0.2.1', 80)\n"
        "    except OSError:\n"
        "        pass\n\n"
        "def test_does_not():\n"
        "    assert True\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("LITKB_LIVE", "PYTEST_ADDOPTS")}
    env["PYTHONPATH"] = str(SCRIPTS / "pipeline")
    env["PYTHONUTF8"] = "1"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert "TEST REACHED FOR THE NETWORK" in out and "test_reaches" in out, out
    # the reaching test's CALL passes and its teardown errors, so pytest counts it under both
    assert "1 error" in out and "ERROR at teardown of test_reaches" in out, out
    assert "test_does_not" not in out.split("short test summary info")[-1], out


# ── builder A's counters, and their fires ────────────────────────────────────────────────────

def _nine(tmp_path, HA):
    reports = {}
    for cls in HA.REFEREE_CLASSES:
        p = tmp_path / f"LITKB_REFEREE_S45_{cls.upper()}_CONSTRUCTED.md"
        p.write_text(f"# {cls}\n\nfired: c=1 on a constructed input\n", encoding="utf-8")
        reports[cls] = str(p)
    return reports


def test_unvalidated_items_names_every_failing_class(HA, tmp_path):
    reports = _nine(tmp_path, HA)
    Path(reports["stage-a"]).unlink()
    Path(reports["stage-e"]).write_text("# no evidence line here\nfired:not-the-grammar\n", encoding="utf-8")
    reports.pop("replay")
    m = {"repo": str(tmp_path), "referee_reports": reports}
    assert HA.unvalidated_items(None, m) == 3
    assert [c for c, _w in HA.unvalidated_detail(m)] == ["stage-a", "stage-e", "replay"]


def test_a_measured_zero_is_measured_and_a_malformed_yield_is_not(HA, tmp_path):
    """The rung REGISTRY decides which Stage B routes owe a yield line (a registered rung) and which a
    not-built line (no rung registers it) — never a list kept in the counter module (brief-CONTRACTS.md
    amendment 2026-09-23; seam integrator-w1). The registry here is CONSTRUCTED: four Stage B rungs."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    rungs = [R.Rung(r, lambda work, ctx: {"status": "no-oa-copy"}, concurrent=True)
             for r in ("osf", "hal", "figshare", "zenodo")]
    built, unbuilt = HA.stage_b_rungs(rungs)
    assert built == ["osf", "hal", "figshare", "zenodo"]
    assert set(unbuilt) == {r for r in P.ROUTES_ALL if P.STAGE_OF.get(r) == "B"} - set(built)
    assert "open_access" in HA.stage_b_rungs()[0], "the real registry's Stage B rung is not read"
    lines = ["yield: zenodo=0/35", "yield: hal=5/3", "yield: osf = 1/2", "  yield: figshare=1/2"]
    lines += [f"not-built: {r} CONSTRUCTED: no key" for r in unbuilt if r not in ("core", "doaj")]
    lines += ["yield: core=1/2",                    # a yield line for a route no rung registers
              "not-built: doaj",                     # a not-built line with no reason
              "not-built: zenodo CONSTRUCTED"]       # a not-built line for a BUILT rung (zenodo is measured anyway)
    p = tmp_path / "LITKB_LADDER1_CONSTRUCTED.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    m = {"repo": str(tmp_path), "report_path": str(p)}
    assert HA.stage_b_unmeasured_detail(m, rungs) == ["osf", "hal", "figshare", "core", "doaj"]
    absent = {"repo": str(tmp_path), "report_path": "absent.md"}
    assert len(HA.stage_b_unmeasured_detail(absent, rungs)) == len(built) + len(unbuilt) == sum(
        1 for r in P.ROUTES_ALL if P.STAGE_OF.get(r) == "B")


@pytest.mark.parametrize("name", ["referee_report_dropped", "yield_line_deleted"])
def test_the_file_fires_fire_through_the_harness(A, name):
    """The plan's (c) rows for `unvalidated_items` and `stage_b_rungs_unmeasured`, through the SAME
    harness `hardening --fire` runs (its reset replaced: these two read files, not the database)."""
    res = A.hardening_fire(name, db="unused", conn=object(), reset=lambda conn: None)
    assert res["verdict"] == "FIRED", res["lines"]


def test_the_replay_summary_is_refused_when_its_register_or_index_changed(HA, tmp_path):
    reg = tmp_path / "reg.json"
    reg.write_text('{"rows": []}', encoding="utf-8")
    summary = {"kind": HA.REPLAY_SUMMARY_KIND, "register_sha256": HA._content_sha(reg), "index_sha256": None,
               "rows": [{"row_id": "X", "acquirer": "stub"}], "network_calls": 0,
               "stale": {"unplayed": [], "misses": []}, "edges": {}}
    summary["summary_sha256"] = HA.summary_sha(summary)      # as `hardening --replay` writes it
    s = tmp_path / "summary.json"
    s.write_text(json.dumps(summary), encoding="utf-8")
    m = {"repo": str(tmp_path), "replay_report": str(s), "register": {"path": str(reg)}}
    assert HA.replay_rows_graded_against_stubs(None, m) == 1
    reg.write_text('{"rows": [1]}', encoding="utf-8")
    with pytest.raises(HA.Unread, match="replayed a register"):
        HA.replay_rows_graded_against_stubs(None, m)
    with pytest.raises(HA.Unread, match="no replay summary"):
        HA.replay_network_calls(None, {"repo": str(tmp_path), "replay_report": "absent.json"})


def test_every_synthetic_acquirer_row_carries_a_pending_recording_marker(HA):
    """A row stays on the stub, marked, until the live pass records it; the counter REPORTS the marked rows.
    The ladder-1 live pass recorded E03 E07 E13 E20, and the register-editor converted them to `ladder` rows
    with no marker (S4.5 run-plan §4); E16 can never be recorded live (replay-only, run-plan §8 Q2), and its
    marker says so."""
    rows = json.loads(REGISTER.read_text(encoding="utf-8"))["rows"]
    stub = {r["id"] for r in rows if ((r.get("replay") or {}).get("routes") or {}).get("kind") == "acquirer"}
    marked = {r["id"] for r in rows if ((r.get("replay") or {}).get("routes") or {}).get("pending_recording")}
    assert stub == marked == {"E16"}
    ladder = {r["id"] for r in rows if ((r.get("replay") or {}).get("routes") or {}).get("kind") == "ladder"}
    assert ladder == {"E03", "E07", "E13", "E20"}, ladder
    m = {"repo": str(SCRIPTS.parent), "register": {"path": str(REGISTER)}}
    assert HA.replay_rows_pending_recording(None, m) == 1


# ── the hardening command: modules, unread, the manifest, the harness ────────────────────────

def _module(dirpath, stem, body):
    p = Path(dirpath) / f"litkb_hardening_{stem}.py"
    p.write_text(body, encoding="utf-8")
    return p


def _all_gated_module(A, skip=()):
    names = [(n, 1 if b.startswith(">=") else 0) for n, b in A.HARDENING_GATED if n not in skip]
    return ("COUNTERS = {" + ", ".join(f"{n!r}: (lambda conn, m: {v})" for n, v in names) + "}\n"
            "REPORTED = {'a_reported_one': lambda conn, m: 7}\n")


def test_an_unread_gated_counter_fails_the_exit(A, tmp_path):
    """The rule the whole command rests on: a gated counter no module defines prints `unread` and
    FAILS. Control: every gated counter defined and inside its bound -> the exit passes."""
    _module(tmp_path, "zz", _all_gated_module(A))
    gated, reported, offences, _mods = A.check_hardening({}, conn=object(), module_dir=tmp_path)
    assert A.hardening_ok(gated), offences
    assert reported["a_reported_one"] == 7 and reported["promotions_committed"] is None
    _module(tmp_path, "zz", _all_gated_module(A, skip=("cassettes_stale",)))
    gated, reported, offences, _mods = A.check_hardening({}, conn=object(), module_dir=tmp_path)
    assert gated["cassettes_stale"] is None and not A.hardening_ok(gated)
    assert "cassettes_stale=unread" in A.hardening_line(gated, reported)
    assert any("cassettes_stale: unread" in o for o in offences), offences


def test_a_counter_that_raises_or_a_module_that_fails_to_load_is_unread(A, tmp_path):
    _module(tmp_path, "zz", _all_gated_module(A, skip=("stubs_bound",))
            + "def _boom(conn, m):\n    raise RuntimeError('cannot read')\nCOUNTERS['stubs_bound'] = _boom\n")
    _module(tmp_path, "broken", "raise ImportError('this module does not load')\n")
    gated, _r, offences, mods = A.check_hardening({}, conn=object(), module_dir=tmp_path)
    assert gated["stubs_bound"] is None and not A.hardening_ok(gated)
    assert [s for s, _e in mods["failed"]] == ["litkb_hardening_broken"]
    assert any("module failed to load: litkb_hardening_broken" in o for o in offences)


def test_two_modules_defining_one_counter_is_refused(A, tmp_path):
    _module(tmp_path, "x1", "COUNTERS = {'stubs_bound': lambda c, m: 0}\n")
    _module(tmp_path, "x2", "REPORTED = {'stubs_bound': lambda c, m: 0}\n")
    with pytest.raises(SystemExit, match="ONE home"):
        A.check_hardening({}, conn=object(), module_dir=tmp_path)


def _frozen(A, **extra):
    m = {"kind": A.HARDENING_MANIFEST_KIND, "frozen_at": "2026-09-23T00:00:00+00:00",
         "gated": [{"name": n, "bound": b} for n, b in A.HARDENING_GATED], "rows": [], **extra}
    m["manifest_sha256"] = A._canonical_sha(m)
    return m


def test_a_manifest_edited_after_its_freeze_is_refused(A, tmp_path):
    p = tmp_path / "m.json"
    m = _frozen(A)
    p.write_text(json.dumps(m), encoding="utf-8")
    assert A.load_hardening_manifest(p)["kind"] == A.HARDENING_MANIFEST_KIND
    m["rows"] = [{"id": "L001", "ref": "10.1/x", "mode": "hunt"}]
    p.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(SystemExit, match="edited after its freeze"):
        A.load_hardening_manifest(p)
    wrong = _frozen(A)
    wrong["kind"] = "litkb-edges"
    wrong["manifest_sha256"] = A._canonical_sha(wrong)
    p.write_text(json.dumps(wrong), encoding="utf-8")
    with pytest.raises(SystemExit, match="is not a 'litkb-hardening' manifest"):
        A.load_hardening_manifest(p)
    other = _frozen(A)
    other["gated"] = other["gated"][:-1]
    other["manifest_sha256"] = A._canonical_sha(other)
    p.write_text(json.dumps(other), encoding="utf-8")
    with pytest.raises(SystemExit, match="gated list is not this code's"):
        A.load_hardening_manifest(p)


def test_the_harness_verdicts(A, tmp_path):
    """FIRED only when the control holds the bound and the known-bad breaks it; an arm that raises is
    `DID-NOT-FIRE (error)`, never FIRED."""
    _module(tmp_path, "zz",
            "def good(conn, arm, wd):\n    return 1 if arm == 'known_bad' else 0\n"
            "def dead(conn, arm, wd):\n    return 0\n"
            "def boom(conn, arm, wd):\n    raise ValueError('an invalid mutation')\n"
            "def loud(conn, arm, wd):\n    return 1\n"
            "FIRES = {'good': {'counter': 'x', 'bound': '=0', 'run': good},\n"
            "         'dead': {'counter': 'x', 'bound': '=0', 'run': dead},\n"
            "         'loud': {'counter': 'x', 'bound': '=0', 'run': loud},\n"
            "         'boom': {'counter': 'x', 'bound': '=0', 'run': boom}}\n")
    verdicts = {n: A.hardening_fire(n, db="unused", conn=object(), module_dir=tmp_path,
                                    reset=lambda conn: None)["verdict"] for n in ("good", "dead", "loud", "boom")}
    # `loud`: its CONTROL already breaks the bound, so the known-bad proves nothing
    assert verdicts == {"good": "FIRED", "dead": "DID-NOT-FIRE", "loud": "DID-NOT-FIRE",
                        "boom": "DID-NOT-FIRE (error)"}


@pytest.mark.parametrize("db,why", [("litkb", "named explicitly"), ("litkb_test", "named explicitly"),
                                    ("litkb_test_wmatching", "named explicitly"),
                                    # every RESERVED worker, not one: an off-by-one over the reserved
                                    # list let litkb_test_w2 through (auditor-A round 1, OM6)
                                    ("litkb_test_w2", "RESERVED"), ("litkb_test_w8", "RESERVED"),
                                    ("litkb_test_w10", "RESERVED"), ("litkb_test_w11", "RESERVED"),
                                    ("", "named explicitly")])
def test_hardening_never_resets_the_live_a_shared_or_a_reserved_database(A, db, why, monkeypatch):
    monkeypatch.setenv("LITKB_TEST_DB", os.environ.get("LITKB_TEST_DB", "litkb_test"))
    with pytest.raises(SystemExit, match=why):
        A._hardening_fire_db(db)


# ── --freeze: the run rows ───────────────────────────────────────────────────────────────────

class _FakeLedger:
    """CONSTRUCTED ledger: two works, one holding a file."""

    works = {("doi", "10.1/held"): ("w-held", "Held_2020_a-work"), ("doi", "10.1/bare"): ("w-bare", "Bare_2021_b-work")}
    refs = {"w-held": ("10.1/held", "doi", "Held_2020_a-work"), "w-bare": ("10.1/bare", "doi", "Bare_2021_b-work"),
            "w-noid": (None, None, "Noid_2019_c-work")}

    def work_of(self, scheme, ref):
        return self.works.get((scheme, (ref or "").lower()))

    def ref_of(self, wid):
        return self.refs[wid]

    def has_file(self, wid):
        return wid == "w-held"

    def attempt_works(self, status, route=None, work_type=None):
        return {"w-bare": {"open_access": 2}, "w-noid": {"annas": 1}} if status == "bad-file" else {}

    def works_with_file_keys(self):
        return {"Held_2020_a-work"}


def test_run_rows_are_deduplicated_by_work_and_keep_every_selector(A):
    ctx = {"ledger": _FakeLedger(), "register": {"rows": []}, "ruled": [],
           "probe": lambda base: {"litkb_acq_probe_no_oa_copy.csv": [{"doi": "10.1/HELD", "unpaywall_url": ""},
                                                                     {"doi": "10.1/bare", "unpaywall_url": ""}],
                                  "litkb_acq_probe_bban.csv": [{"doi": "10.9/nowork", "verdict": "served"}]}.get(base, [])}
    sels = [s for s in A.RUN_SELECTORS if s[0] in ("no-oa-copy", "bad-file", "bban")]
    rows, unhuntable, counts = A.select_run_rows(ctx, sels)
    assert counts == {"no-oa-copy": 2, "bad-file": 2, "bban": 1}
    by = {r["ref"]: r for r in rows}
    assert [r["id"] for r in rows] == ["L001", "L002", "L003"]
    assert by["10.1/held"]["mode"] == "measure" and by["10.1/bare"]["mode"] == "hunt"
    assert by["10.1/bare"]["source"] == ["no-oa-copy", "bad-file"]
    assert by["10.9/nowork"]["work_id"] is None and by["10.9/nowork"]["mode"] == "hunt"
    assert [u["key"] for u in unhuntable] == ["Noid_2019_c-work"]


@pg_only
def test_the_ledger_reader_sql_runs_on_a_migrated_database(A, litkb_pg_base):
    """The selectors' SQL against the real schema (the tests above hand them a CONSTRUCTED ledger)."""
    _psycopg, conn, _ran = litkb_pg_base
    L = A._LedgerReader(conn)
    assert L.work_of("doi", "10.5555/no-such-work-s45a") is None
    assert isinstance(L.attempt_works("bad-file"), dict)
    assert isinstance(L.attempt_works("not-in-archive", route="annas", work_type="preprint"), dict)
    assert isinstance(L.works_with_file_keys(), set)
    assert L.ref_of("01a0a000-0000-7000-8000-000000000000") == (None, None, None)
    assert L.has_file("01a0a000-0000-7000-8000-000000000000") is False


# ── the run driver ───────────────────────────────────────────────────────────────────────────

def _run_manifest(tmp_path):
    # the switch `hardening --freeze` records (S4.5 decision D27): the driver refuses a manifest without it
    return {"repo": str(tmp_path), "workstream_id": None, "shadow_tier": {"enabled": False},
            "cassette_index": {"path": str(tmp_path / "cas" / "index.jsonl"), "bodies": str(tmp_path / "bodies")},
            "rows": [{"id": "L001", "ref": "10.5555/constructed-a", "ref_scheme": "doi", "mode": "hunt",
                      "source": ["no-oa-copy"]},
                     {"id": "L002", "ref": "10.5555/constructed-b", "ref_scheme": "doi", "mode": "measure",
                      "source": ["free-pdf", "bban"]},
                     {"id": "L003", "ref": "10.5555/constructed-c", "ref_scheme": "doi", "mode": "hunt",
                      "source": ["bban"]}]}


def test_the_run_driver_resumes_and_names_an_absent_measure_hook(LR, tmp_path, monkeypatch):
    monkeypatch.setattr(LR, "measure_hook", lambda: None)
    calls, n = [], iter(range(100))

    def hunt(**kw):
        calls.append(kw["ref"])
        if kw["ref"].endswith("-c"):
            raise RuntimeError("a hunt that raises")
        return {"state": "held", "reason": "not-acquired"}
    out = tmp_path / "run.csv"
    ran, resumed, rows = LR.run_rows(_run_manifest(tmp_path), out, db="unused", worktree=tmp_path,
                                     agent="t", session="t", hunt=hunt, attempts_counter=lambda: next(n),
                                     record=False)
    assert (ran, resumed) == (3, 0) and calls == ["10.5555/constructed-a", "10.5555/constructed-c"]
    by = {r["row_id"]: r for r in rows}
    assert (by["L001"]["state"], by["L001"]["reason"]) == ("held", "not-acquired")
    assert (by["L002"]["state"], by["L002"]["reason"]) == ("skipped", "measure-hook-absent")
    assert LR.MEASURE_HOOK in by["L002"]["message"]
    assert by["L003"]["traceback"] == "1" and "RuntimeError" in by["L003"]["message"]
    import csv as _csv

    with open(out, encoding="utf-8", newline="") as fh:
        assert tuple(_csv.DictReader(fh).fieldnames) == LR.RUN_CSV_COLUMNS
    ran2, resumed2, _ = LR.run_rows(_run_manifest(tmp_path), out, db="unused", worktree=tmp_path, agent="t",
                                    session="t", hunt=hunt, attempts_counter=lambda: 0, record=False)
    assert (ran2, resumed2, len(calls)) == (0, 3, 2)
    LR.run_rows(_run_manifest(tmp_path), out, db="unused", worktree=tmp_path, agent="t", session="t",
                hunt=hunt, attempts_counter=lambda: 0, record=False, redo=["L001"])
    assert calls[-1] == "10.5555/constructed-a" and len(calls) == 3


def test_the_run_driver_records_every_request_under_the_rows_reference(LR, C, tmp_path, monkeypatch):
    """RECORD MODE IS ON: a `Client` the hunt builds itself — no cassette passed to it — records into
    the manifest's index, tagged with the row's reference."""
    for k in (C.ENV_MODE, C.ENV_INDEX, C.ENV_BODIES, C.ENV_ROW):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(C, "_env_cache", {})
    with _Server({"/x": (200, "text/plain", b"recorded by the driver")}) as srv:
        def hunt(**kw):
            from litkb.netutil import Client

            Client(base="").get(f"{srv.base}/x")
            return {"state": "held", "reason": "not-acquired"}
        m = _run_manifest(tmp_path)
        m["rows"] = m["rows"][:1]
        try:
            LR.run_rows(m, tmp_path / "run.csv", db="unused", worktree=tmp_path, agent="t", session="t",
                        hunt=hunt, attempts_counter=lambda: 0, record=True)
        finally:
            for k in (C.ENV_MODE, C.ENV_INDEX, C.ENV_BODIES, C.ENV_ROW):
                os.environ.pop(k, None)
    lines = (tmp_path / "cas" / "index.jsonl").read_bytes().splitlines()
    e = json.loads(lines[1])
    assert e["row"] == "10.5555/constructed-a" and e["key"]["url"].endswith("/x")
    assert e["response"]["status"] == 200


# ── the replay through the REAL ladder (worker database) ─────────────────────────────────────

def _reset(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


@pg_only
def test_the_constructed_rows_replay_through_the_real_ladder(E, HA, tmp_path, litkb_pg_base):
    """CONSTRUCTED cassettes, REAL ladder — the plan's item-7 rows (auditor-A round 1, F2): C403's
    blocked/403 comes out of `litkb.acquire.scihub.fetch_scihub` reading the cassette's 403; CTRUNC's
    PDF cut inside its content stream and CHTML's HTML page with no Content-Type each come out as a
    `bad-file` Sci-Hub attempt and held/not-acquired — none out of a dict the register wrote."""
    _psycopg, conn, _ran = litkb_pg_base
    try:
        s = HA._replay_constructed(conn, tmp_path, HA._constructed_register())
    finally:
        _reset(conn)
    got = {r["row_id"]: (r["observed_state"], r["observed_reason"], r["acquirer"]) for r in s["rows"]}
    assert got == {"C403": ("blocked", "403", "ladder"), "CTRUNC": ("held", "not-acquired", "ladder"),
                   "CHTML": ("held", "not-acquired", "ladder")}, s["rows"]
    attempts = {r["row_id"]: r["attempt_statuses"] for r in E.existing_rows(s["replay_csv"])}
    assert attempts["CTRUNC"].startswith("scihub:bad-file") and attempts["CHTML"].startswith("scihub:bad-file")
    assert (HA.count_disagreeing(s), HA.count_network(s), HA.count_stale(s), HA.count_stubs(s)) == (0, 0, 0, 0)


@pg_only
def test_a_ladder_row_with_no_cassette_is_a_named_traceback(C, E, HA, tmp_path, litkb_pg_base):
    """A `ladder` row is answered by a recorded cassette or not at all: with neither its own nor the
    run's, the row is a traceback naming why — never a live ladder run."""
    _psycopg, conn, _ran = litkb_pg_base
    reg = HA._constructed_register()
    reg["rows"] = reg["rows"][:1]                     # C403 alone
    reg["rows"][0]["replay"]["routes"].pop("cassette")
    guard = C.SocketGuard(allow_hosts=(), label="replay")
    try:
        s = HA.build_replay_summary(conn, register=reg, register_path=None, db=conn.info.dbname,
                                    workdir=tmp_path, cassette=None, guard=guard)
    finally:
        _reset(conn)
    (r,) = s["rows"]
    assert r["traceback"] == "1" and "no cassette" in r["message"], r
    assert HA.count_network(s) == 0


@pg_only
@pytest.mark.parametrize("name", ["cassette_403_edited_to_200", "socket_opened_during_replay",
                                  "synthetic_acquirer_reinstated"])
def test_the_replay_fires_fire_on_a_worker_database(A, name, litkb_pg_base):
    """The plan's (c) replay rows through `hardening --fire`'s own harness: reset, control, reset,
    known-bad, reset — on the fixture's worker database."""
    _psycopg, conn, _ran = litkb_pg_base
    res = A.hardening_fire(name, db=conn.info.dbname, conn=conn)
    assert res["verdict"] == "FIRED", res["lines"]


@pg_only
def test_record_against_a_local_server_then_replay_with_it_down(C, E, HA, tmp_path, litkb_pg_base):
    """The mechanism end to end on a recording (ii): the REAL ladder lands a PDF a loopback 'mirror'
    serves, in RECORD mode; the server stops; the REAL ladder replays the same row and ends in the same
    state with the same attempts, no socket, no miss and nothing unplayed. Then the stored PDF body is
    deleted and the same replay FAILS CLOSED."""
    _psycopg, conn, _ran = litkb_pg_base
    title, author = "A locally served replay work for S4.5", "Localserver"
    doi = "10.5555/constructed-s45a-local"
    pdf = E._pdf_bytes(title, author, salt="s45a-local")
    landing = (f'<html><head><meta name="citation_pdf_url" content="/files/{doi}.pdf"></head>'
               "<body>a constructed mirror page</body></html>").encode()
    row = {"id": "LOCAL", "class": "constructed-local-server", "ref": doi, "ref_scheme": "doi",
           "expected": {"state": "bound-unextracted", "reason": "fresh-bound"},
           "live": {"mode": "replay-only", "spend": False},
           "replay": {"inputs": {"spend": True, "extract": False}, "seed": None,
                      "registry": {"kind": "record", "title": title, "author": author, "year": 2026},
                      "fetch": {"kind": "explode"}, "extract": {"kind": "off"},
                      "routes": {"kind": "ladder", "routes": ["scihub"]}}}
    idx, bodies = tmp_path / "cas" / "index.jsonl", tmp_path / "bodies"
    try:
        with _Server({f"/{doi}": (200, "text/html", landing),
                      f"/files/{doi}.pdf": (200, "application/pdf", pdf)}) as srv:
            row["replay"]["routes"]["mirrors"] = [srv.base]
            reg = {"kind": "litkb-hunt-edge-cases", "rows": [row]}
            rec = C.Cassette(idx, "record", bodies=bodies)
            (live,) = E.run_replay(reg, tmp_path / "live.csv", db=conn.info.dbname, tmp=str(tmp_path / "t1"),
                                   conn=conn, cassette=rec)[2]
        assert (live["observed_state"], live["observed_reason"]) == ("bound-unextracted", "fresh-bound"), live
        assert len(rec.recorded) == 2
        # A SECOND ROW in the same index, which this register does not carry: the live pass records
        # every manifest row into one index and the replay grades a subset (auditor-A round 1, F1).
        # Its entry is REPORTED as a row not replayed, never counted stale.
        other = C.Cassette(idx, "record", bodies=bodies)
        other.begin_row("10.5555/constructed-s45a-other-row")
        other.record(_FakeClient(), "http://127.0.0.1:9/other", {"Accept": "text/html"}, True, None,
                     (200, {}, b"a row the register does not carry"))
        _reset(conn)
        rep = C.Cassette(idx, "replay", bodies=bodies)
        s = HA.build_replay_summary(conn, register=reg, register_path=None, db=conn.info.dbname,
                                    workdir=tmp_path / "t2", cassette=rep,
                                    guard=C.SocketGuard(allow_hosts=(), label="replay"))
        (r,) = s["rows"]
        assert (r["observed_state"], r["observed_reason"], r["acquirer"]) == (live["observed_state"],
                                                                             live["observed_reason"], "ladder")
        assert (HA.count_network(s), HA.count_stale(s), HA.count_disagreeing(s)) == (0, 0, 0), s
        assert s["rows_not_replayed"] == [{"row": "10.5555/constructed-s45a-other-row", "entries": 1}], s
        assert HA.count_rows_not_replayed(s) == 1
        replayed = E.existing_rows(s["replay_csv"])[0]
        assert replayed["attempt_statuses"] == live["attempt_statuses"]
        assert replayed["route_detail"] == live["route_detail"]
        _reset(conn)
        rep.body_path(rec.recorded[1]["response"]["body"]["sha256"]).unlink()
        s2 = HA.build_replay_summary(conn, register=reg, register_path=None, db=conn.info.dbname,
                                     workdir=tmp_path / "t3", cassette=C.Cassette(idx, "replay", bodies=bodies),
                                     guard=C.SocketGuard(allow_hosts=(), label="replay"))
        (r2,) = s2["rows"]
        assert r2["traceback"] == "1" and "CassetteMiss" in r2["message"], r2
        assert HA.count_stale(s2) >= 1 and HA.count_disagreeing(s2) == 1
    finally:
        _reset(conn)


# ── fix round 2 (auditor-A round 1: F1-F6, F8-F12, OM2-OM6) ───────────────────────────────────

def test_a_request_key_moves_with_each_component_that_changes_the_answer(C):
    """OM2: two requests that differ ONLY in one key component must not share a recording — the Range
    probe (C2b) and the full GET of one URL, above all. Each component alone moves the key sha."""
    base = dict(method="GET", url="https://h.constructed.invalid/a.pdf",
                headers={"Accept": "application/pdf"}, follow=True, data=None)
    variants = {
        "range": dict(base, headers={"Accept": "application/pdf", "Range": "bytes=0-4095"}),
        "referer": dict(base, headers={"Accept": "application/pdf", "Referer": "https://h.constructed.invalid/"}),
        "accept": dict(base, headers={"Accept": "text/html"}),
        "follow": dict(base, follow=False),
        "body": dict(base, method="POST", data=b"q=1"),
        "url": dict(base, url="https://h.constructed.invalid/b.pdf"),
    }
    _k, sha0 = C.request_key(**base)
    for name, v in variants.items():
        _k, sha = C.request_key(**v)
        assert sha != sha0, f"a request differing only in {name} shares the base request's recording"
    k2, _ = C.request_key("POST", base["url"], base["headers"], True, b"q=2")
    assert k2["body_sha256"] != C.request_key("POST", base["url"], base["headers"], True, b"q=1")[0]["body_sha256"]


def test_a_recording_that_cannot_be_written_never_fails_the_live_request(C, tmp_path):
    """F9: RECORD mode with a body store that cannot be written (a FILE where the store's folder must
    go). `Client.get` still returns the live answer — the ladder never sees a disk error as a route
    that raised — and the lost recording is NAMED in `record_errors`."""
    from litkb.netutil import Client

    blocker = tmp_path / "bodies"
    blocker.write_bytes(b"a file where the body store's folder must go")
    rec = C.Cassette(tmp_path / "idx.jsonl", "record", bodies=blocker)
    rec.begin_row("r1")
    with _Server({"/p.pdf": (200, "application/pdf", b"%PDF-1.4 a body the store cannot take")}) as srv:
        st, _hd, body = Client(base="", cassette=rec).get(f"{srv.base}/p.pdf", accept="application/pdf")
    assert (st, body) == (200, b"%PDF-1.4 a body the store cannot take")
    assert len(rec.record_errors) == 1 and rec.recorded == [], rec.record_errors


def test_an_inlined_body_carries_no_query_secret_and_a_prefixed_pdf_is_stored(C, tmp_path):
    """F10: a small text body is inlined into the TRACKED index, so a 404 page that echoes its request
    URL must not carry `mailto=`/`email=`/`key=` values into it; and a PDF whose `%PDF-` follows a
    byte-order mark is still a PDF — stored, never inlined."""
    cas = C.Cassette(tmp_path / "idx.jsonl", "record", bodies=tmp_path / "bodies")
    cas.begin_row("r1")
    echo = (b"<html><body>404: /works?mailto=someone@constructed.invalid&email=other@constructed.invalid"
            b"&key=K3Yv4lue&x=1 was not found</body></html>")
    cas.record(_FakeClient(), "http://127.0.0.1/404", {"Accept": "text/html"}, True, None, (404, {}, echo))
    bom_pdf = b"\xef\xbb\xbf%PDF-1.4 a byte-order-marked PDF"
    cas.record(_FakeClient(), "http://127.0.0.1/bom.pdf", {"Accept": "application/pdf"}, True, None,
               (200, {}, bom_pdf))
    raw = (tmp_path / "idx.jsonl").read_bytes()
    lines = [json.loads(ln) for ln in raw.splitlines()[1:]]
    inlined = __import__("base64").b64decode(lines[0]["response"]["body"]["inline_b64"])
    for leaked in (b"someone@constructed.invalid", b"other@constructed.invalid", b"K3Yv4lue"):
        assert leaked not in inlined and leaked not in raw, leaked
    assert b"mailto=<KEY>" in inlined and lines[0]["response"]["body"]["scrubbed"] is True
    assert lines[1]["response"]["body"].get("stored") and "inline_b64" not in lines[1]["response"]["body"]


def test_the_guard_counts_a_lookup_through_gethostbyname(C):
    """F11: the resolver's older entry points are guarded like getaddrinfo (numeric address: no DNS
    query leaves either way)."""
    g = C.SocketGuard(label="constructed")
    with g:
        with pytest.raises(C.NetworkBlocked, match="gethostbyname"):
            socket.gethostbyname("192.0.2.1")
        with pytest.raises(C.NetworkBlocked, match="gethostbyname_ex"):
            socket.gethostbyname_ex("192.0.2.2")
        assert socket.gethostbyname("localhost")                 # loopback resolves
    assert [a["host"] for a in g.blocked] == ["192.0.2.1", "192.0.2.2"]


def _run_conftest_copy(tmp_path, tests, env_extra=None, pythonpath=None):
    (tmp_path / "conftest.py").write_bytes((SCRIPTS / "qc" / "conftest.py").read_bytes())
    (tmp_path / "test_constructed_env.py").write_text(tests, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("LITKB_LIVE", "PYTEST_ADDOPTS")}
    env["PYTHONPATH"] = str(pythonpath or SCRIPTS / "pipeline")
    env["PYTHONUTF8"] = "1"
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def test_the_conftest_guard_runs_every_test_with_no_proxy_and_no_solver(tmp_path):
    """F11: a proxy or a solver on a loopback port would carry a test's request OFF the machine through
    an allowed connect. The conftest, run for real in a child pytest whose environment sets both,
    must hand every test an environment with neither (and NO_PROXY=*)."""
    code, out = _run_conftest_copy(tmp_path, (
        "import os\n\n"
        "def test_no_proxy_no_solver():\n"
        "    for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'FLARESOLVERR_URL'):\n"
        "        assert os.environ.get(k) in (None, ''), k\n"
        "    assert os.environ.get('NO_PROXY') == '*'\n"),
        env_extra={"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
                   "FLARESOLVERR_URL": "http://127.0.0.1:8191"})
    assert code == 0 and "1 passed" in out, out


def test_the_conftest_guard_fails_closed_when_litkb_imports_without_its_cassette(tmp_path):
    """F11: a CONSTRUCTED `litkb` package with no `cassette` module (what a worktree run without
    PYTHONPATH=pipeline imports from main before the merge) — every test ERRORS, named; the guard is
    never silently off."""
    pkg = tmp_path / "constructed_pkg" / "litkb"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""CONSTRUCTED: a litkb with no cassette module."""\n', encoding="utf-8")
    tests = tmp_path / "t"
    tests.mkdir()
    code, out = _run_conftest_copy(tests, "def test_anything():\n    assert True\n",
                                   pythonpath=tmp_path / "constructed_pkg")
    assert code != 0 and "cannot import litkb.cassette" in out and "1 error" in out, out


def test_staleness_is_scoped_to_the_rows_the_replay_began(C, tmp_path):
    """F1, at the cassette: one index holding two rows (r1 two requests, r2 one). A replay that begins
    r1 and asks one of its two leaves THAT entry stale; r2, never begun, is a row not replayed —
    listed, never stale. Asking r1's second request as well empties the diff."""
    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    rec = C.Cassette(idx, "record", bodies=bodies)
    for row, paths in (("r1", ("/a", "/b")), ("r2", ("/c",))):
        rec.begin_row(row)
        for p in paths:
            rec.record(_FakeClient(), f"http://127.0.0.1{p}", {"Accept": "*/*"}, True, None, (200, {}, p.encode()))
    rep = C.Cassette(idx, "replay", bodies=bodies)
    rep.begin_row("r1")
    from litkb.netutil import Client

    Client(base="", cassette=rep).get("http://127.0.0.1/a", accept="*/*")
    assert [u["url"].rsplit("/", 1)[1] for u in rep.stale()["unplayed"]] == ["b"]
    assert rep.rows_not_replayed() == [{"row": "r2", "entries": 1}]
    Client(base="", cassette=rep).get("http://127.0.0.1/b", accept="*/*")
    assert rep.stale() == {"unplayed": [], "misses": []}
    assert rep.rows_not_replayed() == [{"row": "r2", "entries": 1}]


def test_a_yield_line_that_asked_nobody_is_not_a_measurement(HA):
    """F3: `=0/0` asked no row — not measured; `=0/1` is a measured zero."""
    assert HA.yields("yield: core=0/0\nyield: doaj=0/1\nyield: hal=0/35\n") == {"doaj": (0, 1), "hal": (0, 35)}


def test_cassettes_stale_is_unread_when_the_recorded_index_does_not_exist(HA):
    """F1: a replay whose manifest names a recorded index that is not on disk replayed no recording —
    its staleness is UNREAD, never a vacuous 0. A summary naming no index (the fires' CONSTRUCTED
    rows, each on its own cassette) is graded on what it replayed."""
    s = {"cassette_index": "qc/fixtures/litkb_cassettes/ladder-1/index.jsonl", "index_sha256": None,
         "stale": {"unplayed": [], "misses": []}, "row_cassette_misses": 0}
    with pytest.raises(HA.Unread, match="does not exist"):
        HA.count_stale(s)
    assert HA.count_stale(dict(s, cassette_index=None)) == 0
    # the REPORTED list of recorded rows the replay never began: unread for the same reason (round 2, F5)
    with pytest.raises(HA.Unread, match="does not exist"):
        HA.count_rows_not_replayed(dict(s, rows_not_replayed=[]))
    assert HA.count_rows_not_replayed(dict(s, cassette_index=None, rows_not_replayed=[{"row": "r", "entries": 1}])) == 1


def _summary_files(HA, tmp_path, *, index_bytes=b'{"kind": "litkb-cassette"}\n', recording=True,
                   constructed=False, record_errors=()):
    """A CONSTRUCTED replay summary, its register, its index, (optionally) the run driver's recording
    report and (optionally) a CONSTRUCTED register it replayed, all consistent. -> (manifest, paths)."""
    from litkb import cassette as CAS

    tmp_path.mkdir(parents=True, exist_ok=True)
    reg = tmp_path / "reg.json"
    reg.write_text('{"rows": []}', encoding="utf-8")
    con = tmp_path / "constructed_reg.json"
    if constructed:
        con.write_text('{"_what": "CONSTRUCTED", "rows": []}', encoding="utf-8")
    idx = tmp_path / "index.jsonl"
    idx.write_bytes(index_bytes)
    s = {"kind": HA.REPLAY_SUMMARY_KIND, "register_sha256": HA._content_sha(reg),
         "constructed_register": str(con) if constructed else None,
         "constructed_register_sha256": HA._content_sha(con) if constructed else None,
         "cassette_index": str(idx), "index_sha256": CAS.index_sha256(idx),
         "rows": [{"row_id": "X", "acquirer": "stub"}], "network_calls": 0,
         "stale": {"unplayed": [], "misses": []}, "rows_not_replayed": [], "edges": {}}
    s["summary_sha256"] = HA.summary_sha(s)
    sp = tmp_path / "summary.json"
    sp.write_text(json.dumps(s), encoding="utf-8")
    m = {"repo": str(tmp_path), "replay_report": str(sp), "register": {"path": str(reg)},
         "cassette_index": {"path": str(idx)}}
    if constructed:
        m["constructed_register"] = {"path": str(con), "sha256": HA._content_sha(con)}
    rp = tmp_path / "recording.json"
    if recording:
        r = {"kind": "litkb-hardening-recording", "index": str(idx), "index_sha256": CAS.index_sha256(idx),
             "record_errors": list(record_errors)}
        r["recording_sha256"] = HA.summary_sha(r, "recording_sha256")
        rp.write_text(json.dumps(r), encoding="utf-8")
    m["recording_report"] = str(rp)
    return m, {"summary": sp, "index": idx, "recording": rp, "constructed": con}


def test_the_replay_summary_is_refused_when_its_index_changed_edited_or_unrecorded(HA, tmp_path):
    """OM3 + F6: the replay counters read a summary ONLY while (a) the index it replayed is the index
    on disk, (b) the summary is as the replay wrote it (`summary_sha256`), and (c) that index is the one
    the live pass finished recording (the run driver's recording report). Control first: consistent
    files read."""
    m, p = _summary_files(HA, tmp_path / "a")
    assert HA.replay_rows_graded_against_stubs(None, m) == 1
    # (a) the index changed after the replay
    p["index"].write_bytes(p["index"].read_bytes() + b'{"row": "a late entry"}\n')
    with pytest.raises(HA.Unread, match="replayed a cassette index"):
        HA.replay_rows_graded_against_stubs(None, m)
    # (b) the summary hand-edited: stubs 1 -> 0, network 3 -> 0 (auditor-A's D3)
    m, p = _summary_files(HA, tmp_path / "b")
    s = json.loads(p["summary"].read_text(encoding="utf-8"))
    s["rows"][0]["acquirer"] = "ladder"
    p["summary"].write_text(json.dumps(s), encoding="utf-8")
    with pytest.raises(HA.Unread, match="edited after"):
        HA.replay_rows_graded_against_stubs(None, m)
    # (c1) the index and the summary agree, but the live pass recorded a different index
    m, p = _summary_files(HA, tmp_path / "c")
    r = json.loads(p["recording"].read_text(encoding="utf-8"))
    r["index_sha256"] = "0" * 64
    r["recording_sha256"] = HA.summary_sha(r, "recording_sha256")
    p["recording"].write_text(json.dumps(r), encoding="utf-8")
    with pytest.raises(HA.Unread, match="not the index the live pass"):
        HA.replay_rows_graded_against_stubs(None, m)
    # (c2) an index with no recording report at all
    m, _p = _summary_files(HA, tmp_path / "d", recording=False)
    with pytest.raises(HA.Unread, match="no recording report"):
        HA.replay_rows_graded_against_stubs(None, m)


def test_a_ge_bound_counter_below_its_bound_fails_the_exit(A, tmp_path):
    """OM4: `relation_probe_rows>=1` and `promotions_prepared>=1` are the two `>=` bounds; a value of 0
    must FAIL the exit (a `>=N` check read as `>=0` would pass every value)."""
    body = _all_gated_module(A, skip=("promotions_prepared",)) + \
        "COUNTERS['promotions_prepared'] = lambda conn, m: 0\n"
    _module(tmp_path, "zz", body)
    gated, _r, _o, _m = A.check_hardening({}, conn=object(), module_dir=tmp_path)
    assert gated["promotions_prepared"] == 0 and not A.hardening_ok(gated)
    assert A._bound_ok(1, ">=1") and not A._bound_ok(0, ">=1") and A._bound_ok(0, "=0")


def test_the_run_driver_writes_the_recording_report(LR, HA, C, tmp_path, monkeypatch):
    """F6: at the end of a pass the driver writes the manifest's `recording_report` — the index's
    sha256 as the pass left it, its row tags, the recordings it could not write, and a self-hash —
    which the replay counters hold every later replay to."""
    for k in (C.ENV_MODE, C.ENV_INDEX, C.ENV_BODIES, C.ENV_ROW):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(C, "_env_cache", {})
    m = _run_manifest(tmp_path)
    m["rows"] = m["rows"][:1]
    m["recording_report"] = "_derived/hardening/constructed_recording.json"
    with _Server({"/x": (200, "text/plain", b"recorded by the driver")}) as srv:
        def hunt(**kw):
            from litkb.netutil import Client

            Client(base="").get(f"{srv.base}/x")
            return {"state": "held", "reason": "not-acquired"}
        try:
            LR.run_rows(m, tmp_path / "run.csv", db="unused", worktree=tmp_path, agent="t", session="t",
                        hunt=hunt, attempts_counter=lambda: 0, record=True)
        finally:
            for k in (C.ENV_MODE, C.ENV_INDEX, C.ENV_BODIES, C.ENV_ROW):
                os.environ.pop(k, None)
    rep = json.loads((tmp_path / "_derived" / "hardening" / "constructed_recording.json").read_text(encoding="utf-8"))
    assert rep["index_sha256"] == C.index_sha256(tmp_path / "cas" / "index.jsonl") and rep["entries"] == 1
    assert rep["rows"] == ["10.5555/constructed-a"] and rep["record_errors"] == []
    assert rep["recording_sha256"] == HA.summary_sha(rep, "recording_sha256")


def test_the_run_driver_passes_no_extract_to_every_hunt(LR, A, tmp_path, monkeypatch):
    """F12: `--no-extract` reaches the hunt as `extract=False`; without it the hunt keeps its own default
    (the orchestrator decides which the live pass uses)."""
    m = {"kind": A.HARDENING_MANIFEST_KIND, "frozen_at": "2026-09-23T00:00:00+00:00", "repo": str(tmp_path),
         "db": "unused", "run_csv": "run.csv", "rows": [],
         "gated": [{"name": n, "bound": b} for n, b in A.HARDENING_GATED]}
    m["manifest_sha256"] = A._canonical_sha(m)
    p = tmp_path / "m.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    seen = []
    monkeypatch.setattr(LR, "run_rows", lambda *a, **kw: seen.append(kw.get("hunt_kwargs")) or (0, 0, []))
    assert LR.main(["--manifest", str(p), "--no-extract", "--no-record"]) == 0
    assert LR.main(["--manifest", str(p), "--no-record"]) == 0
    assert seen == [{"extract": False}, None]


def test_the_freeze_selects_every_execute_row_pending_a_recording(A):
    """F8: every register row still on the synthetic acquirer whose live mode is `execute` is a run
    row by name — not by the luck of a probe selector; E16 (replay-only) is not. The ladder-1 live pass
    recorded the four it selected (E03 E07 E13 E20, converted by the register-editor, S4.5 run-plan §4), so
    the REAL register selects none; the rule is held on a CONSTRUCTED copy with E03's marker put back."""
    reg = json.loads(REGISTER.read_text(encoding="utf-8"))
    assert A._sel_pending_recording({"register": reg}) == []
    constructed = json.loads(json.dumps(reg))            # CONSTRUCTED: E03 back on the stub, marked
    by_id = {r["id"]: r for r in constructed["rows"]}
    by_id["E03"]["replay"]["routes"] = {"kind": "acquirer", "outcome": "not-acquired", "route_detail": [],
                                        "pending_recording": {"why": "CONSTRUCTED", "until": "CONSTRUCTED"}}
    got = A._sel_pending_recording({"register": constructed})
    by_ref = {r["ref"]: r for r in constructed["rows"]}
    assert sorted(by_ref[c["ref"]]["id"] for c in got) == ["E03"]       # E16 is marked too, and replay-only
    assert ("pending-recording", A._sel_pending_recording) in A.RUN_SELECTORS


@pg_only
def test_an_unplayed_entry_of_a_rows_own_cassette_is_stale(C, HA, tmp_path, litkb_pg_base):
    """F1: a row replayed from a cassette of its OWN (a CONSTRUCTED fixture) leaves its unplayed entries
    in the staleness diff too — round 1 read only the run cassette's. A copy of C403's index gains one
    more entry for the same row, at a URL the ladder never asks: stale = 1."""
    _psycopg, conn, _ran = litkb_pg_base
    reg = HA._constructed_register()
    reg["rows"] = reg["rows"][:1]
    src = HA.FIXTURES / reg["rows"][0]["replay"]["routes"]["cassette"]
    dst = tmp_path / "c403_plus_one" / "index.jsonl"
    dst.parent.mkdir(parents=True)
    lines = src.read_bytes().splitlines()
    extra = json.loads(lines[1])
    key, ksha = C.request_key("GET", "https://scihub-a.constructed.invalid/never-asked", {"Accept": "text/html"},
                              True, None)
    extra.update(key=key, key_sha256=ksha)
    dst.write_bytes(b"\n".join(lines + [json.dumps(extra, sort_keys=True, separators=(",", ":")).encode()]) + b"\n")
    reg["rows"][0]["replay"]["routes"]["cassette"] = str(dst)
    try:
        s = HA._replay_constructed(conn, tmp_path, reg)
    finally:
        _reset(conn)
    assert HA.count_stale(s) == 1, s["stale"]
    assert [u["url"] for u in s["stale"]["unplayed"]] == ["https://scihub-a.constructed.invalid/never-asked"]
    assert HA.count_disagreeing(s) == 0


@pg_only
def test_hardening_replay_counts_a_socket_its_guard_allows_nothing(A, HA, tmp_path, litkb_pg_base):
    """OM5: `hardening --replay` runs inside a guard that allows NOTHING, loopback included. A route
    that opens a loopback connection mid-replay (the fire's `_StraySocket`) is counted; the same replay
    without it counts 0. Control first."""
    _psycopg, conn, _ran = litkb_pg_base
    m = {"repo": str(tmp_path), "register": {"path": str(HA.CONSTRUCTED_REGISTER)},
         "cassette_index": {"path": str(tmp_path / "no_recording" / "index.jsonl")},
         "replay_csv": "replay.csv", "replay_report": "replay.json"}
    try:
        control = A.hardening_replay(m, db=conn.info.dbname, conn=conn)
        with HA._StraySocket():
            stray = A.hardening_replay(m, db=conn.info.dbname, conn=conn)
    finally:
        _reset(conn)
    assert HA.count_network(control) == 0 and HA.count_disagreeing(control) == 0, control["edges_offences"]
    assert HA.count_network(stray) == 1, stray["network_attempts"]
    assert all(a["host"] == "127.0.0.1" and a["refused"] for a in stray["network_attempts"])


def _probe_csvs(repo):
    """CONSTRUCTED probe CSVs (10.5555 DOIs) under <repo>/phase4/qc/, the shape the selectors read."""
    q = repo / "phase4" / "qc"
    q.mkdir(parents=True)
    (q / "litkb_acq_probe_no_oa_copy.csv").write_text(
        "doi,unpaywall_url\n10.5555/constructed-noa-1,\n10.5555/constructed-noa-2,https://doi.org/10.5555/constructed-noa-2\n",
        encoding="utf-8")
    (q / "litkb_acq_probe_head.csv").write_text(
        "doi,resolver,verdict,status\n10.5555/constructed-free-1,unpaywall,FREE-PDF,200\n"
        "10.5555/constructed-dead-1,unpaywall,DEAD,404\n", encoding="utf-8")
    (q / "litkb_acq_probe_bban.csv").write_text(
        "doi,verdict,tried,http_status\n10.5555/constructed-bban-1,served,as-stored,200\n", encoding="utf-8")
    (q / "litkb_acq_probe_crosswalk.csv").write_text(
        "key,doi,cr_type,s2_arxiv,cr_isbn,cr_relation_types\n"
        "Constructed_2020_x,10.5555/constructed-cw-1,journal-article,2206.00001,,\n", encoding="utf-8")


@pg_only
def test_freeze_grade_and_replay_on_a_worker_database(A, HA, tmp_path, litkb_pg_base, capsys):
    """F4 (+ F1, F2, F8): `hardening --freeze` on a worker database (a CONSTRUCTED repo of probe CSVs,
    the real register), the manifest round-tripping through `load_hardening_manifest`; the CLI grade
    before any replay (every replay counter unread, the exit failing); `hardening_replay` over the
    register AND the CONSTRUCTED register (the plan's raise cases E14 E15 E17 and the C rows among
    them); the CLI grade after it — `cassettes_stale` still UNREAD, because no recording exists.

    THE GATE STAYS FAIL-CLOSED (S4.5 run-plan §8 Q3): the four rows the ladder-1 live pass recorded (E03 E07
    E13 E20, `ladder` rows with no cassette of their own since the register-editor's conversion) replay here
    with NO recorded index, so each is the named no-cassette traceback and the replay counts all four
    disagreeing — never `graded-by-hardening-replay`, the edges pytest's word, which the gate does not write."""
    from litkb.db import connect as c
    from litkb.extract import queue_fire as F

    _psycopg, conn, _ran = litkb_pg_base
    _reset(conn)
    repo = tmp_path / "repo"
    _probe_csvs(repo)
    ws = F.open_ws(conn)
    slug = conn.execute("SELECT slug FROM litkb.workstreams WHERE id = %s", (ws,)).fetchone()[0]
    out = tmp_path / "hardening.json"
    try:
        code = A.main(["hardening", "--freeze", "--workstream", slug, "--db", c.DB_TEST, "--role", "litkb_test",
                       "--repo", str(repo), "--out", str(out), "--date", "2026-09-23", "--no-admin-read",
                       "--cassette", str(tmp_path / "cas" / "index.jsonl"), "--bodies", str(tmp_path / "bodies")])
        frozen_line = capsys.readouterr().out
        assert code == 0, frozen_line
        m = A.load_hardening_manifest(out)
        assert (m["kind"], m["frozen_at_source"], m["db_name"], m["workstream_id"]) == (
            A.HARDENING_MANIFEST_KIND, "db", c.DB_TEST, str(ws))
        assert m["db_migration_tip"] is None and "--no-admin-read" in m["db_migration_tip_note"]
        assert set(m["probe_csvs"]) == {"litkb_acq_probe_no_oa_copy.csv", "litkb_acq_probe_head.csv",
                                        "litkb_acq_probe_bban.csv", "litkb_acq_probe_crosswalk.csv"}
        assert m["report_path"] == "Reports/LITKB_LADDER1_2026-09-23.md"
        # the ladder budget frozen outside the ladder, what C1a's budget_exceeded_silently grades against
        # (auditor-C1a r2 F6 / r3 F4; integrator-w2)
        from litkb.acquire import policy as LP
        assert m.get("ladder_budget") == {"seconds": LP.LADDER_SECONDS_DEFAULT, "attempts": None}, m.get("ladder_budget")
        assert m["shadow_tier"]["enabled"] is False, m.get("shadow_tier")      # S4.5 decision D27
        assert m["referee_reports"]["replay"] == "Reports/LITKB_REFEREE_S45_REPLAY_2026-09-23.md"
        assert m["recording_report"].endswith("_recording.json") and m["constructed_register"]["sha256"]
        assert m["cassette_index"]["sha256"] is None
        sel = m["selectors"]
        # pending-recording selects nothing: the live pass recorded every execute row it named (run-plan §4)
        assert (sel["register"], sel["pending-recording"], sel["post-freeze-probe"], sel["no-oa-copy"],
                sel["bronze-landing"], sel["free-pdf"], sel["wayback"], sel["bban"], sel["crosswalk"]) == (
            4, 0, 1, 2, 1, 1, 1, 1, 1), sel
        assert all(r["mode"] == "hunt" and r["id"].startswith("L") and r["source"] for r in m["rows"])
        pending = {r["ref"] for r in m["rows"] if "pending-recording" in r["source"]}
        assert len(pending) == 0, pending

        code = A.main(["hardening", "--manifest", str(out)])
        before = capsys.readouterr()
        assert code == 1 and "replay_rows_graded_against_stubs=unread" in before.out, before
        assert "unvalidated_items=9" in before.out and "modules: litkb_hardening_a" in before.err

        s = A.hardening_replay(m, db=c.DB_TEST, conn=conn)
        rows = {r["row_id"]: r for r in s["rows"]}
        for rid in ("E14", "E15", "E17", "C403", "CTRUNC", "CHTML"):
            r = rows[rid]
            assert (r["observed_state"], r["observed_reason"]) == (r["expected_state"], r["expected_reason"]), r
        recorded = {"E03", "E07", "E13", "E20"}
        for rid in sorted(recorded):
            r = rows[rid]
            assert (r["acquirer"], r["traceback"]) == ("ladder", "1"), r
            assert "is a `ladder` row with no cassette" in r["message"], r
        assert {o.split(":", 1)[0] for o in s["edges_offences"]} == recorded, s["edges_offences"]
        assert (HA.count_stubs(s), HA.count_network(s), HA.count_disagreeing(s)) == (1, 0, 4), s["edges_offences"]

        code = A.main(["hardening", "--manifest", str(out)])
        after = capsys.readouterr()
        assert code == 1
        # no recording exists yet: the staleness diff, the rows-not-replayed list and the recording's
        # lost writes are all UNREAD, never a vacuous 0 (auditor-A round 2, F5)
        for piece in ("replay_rows_graded_against_stubs=1", "replay_network_calls=0",
                      "replay_rows_disagreeing=4", "cassettes_stale=unread", "cassette_rows_not_replayed=unread",
                      "cassette_record_errors=unread", "replay_rows_pending_recording=1"):
            assert piece in after.out, (piece, after.out)
        assert "does not exist" in after.err
    finally:
        _reset(conn)


# ── fix round 3 (auditor-A round 2: F1, F2, F3; notes F4, F5, F6) ─────────────────────────────

def test_a_replayed_row_that_asks_nothing_leaves_its_entries_stale(C, tmp_path):
    """F1: a replay that BEGINS a recorded row and asks the hosts nothing (every route skipped, a budget
    stop, a rung the live pass never reached) has diverged completely: the row's recorded entry is
    STALE, and the row is not listed as one nobody replayed. Control: asking the request empties it."""
    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    rec = C.Cassette(idx, "record", bodies=bodies)
    rec.begin_row("10.5555/constructed-asks-nothing")
    rec.record(_FakeClient(), "http://127.0.0.1/only", {"Accept": "*/*"}, True, None, (200, {}, b"only"))
    rep = C.Cassette(idx, "replay", bodies=bodies)
    rep.begin_row("10.5555/constructed-asks-nothing")
    assert [u["url"].rsplit("/", 1)[1] for u in rep.stale()["unplayed"]] == ["only"]
    assert rep.rows_not_replayed() == []
    from litkb.netutil import Client

    Client(base="", cassette=rep).get("http://127.0.0.1/only", accept="*/*")
    assert rep.stale() == {"unplayed": [], "misses": []}


def test_an_edited_recording_report_or_a_changed_constructed_register_is_refused(HA, tmp_path):
    """F2: (c3) a recording report edited WITHOUT its self-hash — its `index_sha256` rewritten to the
    index the replay read, so the index check alone agrees — is refused as edited; (e) a replay summary
    of a CONSTRUCTED register that has changed since is refused. Controls first."""
    m, p = _summary_files(HA, tmp_path / "c3", index_bytes=b'{"kind": "litkb-cassette"}\n{"row": "r"}\n')
    assert HA.replay_rows_graded_against_stubs(None, m) == 1
    r = json.loads(p["recording"].read_text(encoding="utf-8"))
    true_sha = r["index_sha256"]
    r["index_sha256"] = "0" * 64                            # what the live pass really recorded
    r["recording_sha256"] = HA.summary_sha(r, "recording_sha256")
    r["index_sha256"] = true_sha                            # ...rewritten afterwards, the self-hash left
    p["recording"].write_text(json.dumps(r), encoding="utf-8")
    with pytest.raises(HA.Unread, match="was itself edited"):
        HA.replay_rows_graded_against_stubs(None, m)
    with pytest.raises(HA.Unread, match="was itself edited"):
        HA.cassette_record_errors(None, m)
    m, p = _summary_files(HA, tmp_path / "e", constructed=True)
    assert HA.replay_rows_graded_against_stubs(None, m) == 1
    p["constructed"].write_text('{"_what": "CONSTRUCTED", "rows": [{"id": "CNEW"}]}', encoding="utf-8")
    with pytest.raises(HA.Unread, match="CONSTRUCTED register"):
        HA.replay_rows_graded_against_stubs(None, m)


def test_cassette_record_errors_reads_the_recording_report(HA, tmp_path):
    """F5: the recordings the live pass lost are REPORTED from the recording report; with no report the
    counter is unread."""
    m, _p = _summary_files(HA, tmp_path / "a", record_errors=("OSError: the store is a file",))
    assert HA.cassette_record_errors(None, m) == 1
    assert HA.DETAILS["cassette_record_errors"](None, m) == [
        "a recording the live pass could not write: OSError: the store is a file"]
    m, _p = _summary_files(HA, tmp_path / "b", recording=False)
    with pytest.raises(HA.Unread, match="no recording report"):
        HA.cassette_record_errors(None, m)
    assert HA.REPORTED["cassette_record_errors"] is HA.cassette_record_errors


def test_a_recording_that_raises_a_non_os_error_is_named_too(C, tmp_path):
    """F6: the lost-recording boundary is `Exception`, not `OSError`: a response the recorder cannot
    encode (a CONSTRUCTED non-numeric status) is named in `record_errors`, never raised into the
    ladder's live request."""
    rec = C.Cassette(tmp_path / "idx.jsonl", "record", bodies=tmp_path / "bodies")
    rec.begin_row("r1")
    rec.record(_FakeClient(), "http://127.0.0.1/x", {"Accept": "*/*"}, True, None,
               ("constructed-not-a-status", {}, b"body"))
    assert len(rec.record_errors) == 1 and rec.record_errors[0].startswith("ValueError"), rec.record_errors
    assert rec.recorded == []


def test_a_link_read_out_of_a_masked_body_replays(C, tmp_path):
    """F4 (demonstration DS1): the ladder reads a link out of a landing page whose query carries a
    scrubbed name (`?token=`). The index inlines the page with the value masked, so the REPLAYED link
    reads `?token=<KEY>`; the mask must be idempotent for that request to key to the recording's
    `?token=<KEY>` and be ANSWERED — not a miss the live pass never made. Control: the live pass."""
    import re

    from litkb.netutil import Client

    idx, bodies = tmp_path / "idx.jsonl", tmp_path / "bodies"
    landing = b'<html><body><a href="/file?token=constructed-abc123">the file</a></body></html>'

    def link_of(body):
        return re.search(rb'href="([^"]+)"', body).group(1).decode()
    with _Server({"/landing": (200, "text/html", landing), "/file": (200, "text/plain", b"the linked file")}) as srv:
        rec = C.Cassette(idx, "record", bodies=bodies)
        rec.begin_row("r1")
        c = Client(base="", cassette=rec)
        assert c.get(srv.base + link_of(c.get(f"{srv.base}/landing")[2]))[2] == b"the linked file"
    rep = C.Cassette(idx, "replay", bodies=bodies)
    rep.begin_row("r1")
    c2 = Client(base="", cassette=rep)
    body = c2.get(f"{srv.base}/landing")[2]
    assert b"constructed-abc123" not in body and link_of(body) == "/file?token=<KEY>"
    assert c2.get(srv.base + link_of(body))[2] == b"the linked file"
    assert rep.stale() == {"unplayed": [], "misses": []}
    # both masks are idempotent: applying one twice changes nothing
    u = "https://h.constructed.invalid/p?token=abc&key=<KEY>"
    assert C.scrub_url(u) == "https://h.constructed.invalid/p?token=<KEY>&key=<KEY>" == C.scrub_url(C.scrub_url(u))
    b = b"/p?token=abc&key=<KEY>&mailto=x@constructed.invalid"
    once = C._SCRUB_RE_B.sub(rb"\1" + C.MASK.encode(), b)
    assert once == b"/p?token=<KEY>&key=<KEY>&mailto=<KEY>" and C._SCRUB_RE_B.sub(rb"\1" + C.MASK.encode(), once) == once


def test_a_loopback_connect_is_allowed_only_to_a_named_port_or_one_this_process_bound(C, listener):
    """F3 (Codex X3: host AND port): a guard allowing loopback on port 5433 lets a connect through to a
    listener THIS process bound (`listener`, recorded by the bind watcher), and counts and refuses one to
    loopback port 1, which nothing in this process bound (a port that could forward off the machine)."""
    g = C.SocketGuard(allow_ports=(5433,), label="constructed")
    with g:
        with socket.socket() as s:
            s.connect(("127.0.0.1", listener))
        with socket.socket() as s:
            with pytest.raises(C.NetworkBlocked, match=r"refused connect to 127\.0\.0\.1:1 "):
                s.connect(("127.0.0.1", 1))
        # auditor-A round 3 F1 (integrator-w2): a HIGH unprivileged port is refused too — FlareSolverr's default
        # 8191 (the carrier `_PROXY_ENV` names), a port `bind(0)` never hands out (Windows' ephemeral range starts
        # at 49152). Port 1 alone let "allow every loopback port >= 1024" (auditor's NM6) pass unseen.
        with socket.socket() as s:
            with pytest.raises(C.NetworkBlocked, match=r"refused connect to 127\.0\.0\.1:8191 "):
                s.connect(("127.0.0.1", 8191))
    assert [(a["host"], a["port"], a["refused"]) for a in g.blocked] == [("127.0.0.1", 1, True),
                                                                         ("127.0.0.1", 8191, True)]
    assert g.allows("localhost", 5433) and g.allows("::1", listener)
    assert not g.allows("127.0.0.1", 1) and not g.allows("192.0.2.1", 5433) and not g.allows("127.0.0.1", "x")
    assert not g.allows("127.0.0.1", 8191) and not g.allows("127.0.0.1", 3128) and not g.allows("127.0.0.1", 1080)
    assert C.SocketGuard().allows("127.0.0.1", 1)            # allow_ports=None: every loopback port


def test_the_suites_named_ports_are_exactly_postgres_and_a_loopback_grobid():
    """auditor-A round 3 F1 (integrator-w2): `qc/conftest.py::_suite_ports` is PINNED to its two homes —
    `litkb.db.connect.PORT` and the port of `litkb.extract.grobid.DEFAULT_URL` when its host is loopback — so the
    list cannot be widened to make a test pass (the auditor's NM12: FlareSolverr's 8191 added to it survived the
    whole suite). Read from a copy of the module's own function, loaded by path (qc is not a package)."""
    import importlib.util
    from urllib.parse import urlsplit

    from litkb.cassette import is_loopback
    from litkb.db.connect import PORT
    from litkb.extract.grobid import DEFAULT_URL

    spec = importlib.util.spec_from_file_location("_conftest_ports_pin", Path(__file__).with_name("conftest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    u = urlsplit(DEFAULT_URL)
    want = {int(PORT)} | ({int(u.port or (443 if u.scheme == "https" else 80))} if is_loopback(u.hostname) else set())
    assert set(mod._suite_ports()) == want, (sorted(mod._suite_ports()), sorted(want))
    assert 8191 not in mod._suite_ports()


def test_the_conftest_guard_allows_loopback_only_on_its_ports(tmp_path):
    """F3, the suite's own guard run for real: a COPY of qc/conftest.py beside two CONSTRUCTED tests —
    one connecting to loopback port 1 (bound by nobody in the child) must ERROR at teardown with the
    finding; one connecting to a listener it bound itself must pass."""
    code, out = _run_conftest_copy(tmp_path, (
        "import socket\n\n"
        "def test_reaches_an_unbound_loopback_port():\n"
        "    s = socket.socket()\n"
        "    try:\n"
        "        s.settimeout(5)\n"
        "        s.connect(('127.0.0.1', 1))\n"
        "    except OSError:\n"
        "        pass\n"
        "    finally:\n"
        "        s.close()\n\n"
        "def test_reaches_its_own_listener():\n"
        "    with socket.socket() as srv:\n"
        "        srv.bind(('127.0.0.1', 0))\n"
        "        srv.listen(1)\n"
        "        with socket.socket() as c:\n"
        "            c.connect(srv.getsockname())\n\n"
        # CONSTRUCTED (auditor-A round 3 F1, integrator-w2): FlareSolverr's default port, a high port bound by
        # nobody in the child — the suite's guard must refuse it as it refuses port 1
        "def test_reaches_a_solver_port():\n"
        "    s = socket.socket()\n"
        "    try:\n"
        "        s.settimeout(5)\n"
        "        s.connect(('127.0.0.1', 8191))\n"
        "    except OSError:\n"
        "        pass\n"
        "    finally:\n"
        "        s.close()\n"))
    assert code != 0, out
    assert "TEST REACHED FOR THE NETWORK" in out and "connect 127.0.0.1:1" in out, out
    assert "connect 127.0.0.1:8191" in out and "ERROR at teardown of test_reaches_a_solver_port" in out, out
    assert "2 errors" in out and "ERROR at teardown of test_reaches_an_unbound_loopback_port" in out, out
    assert "test_reaches_its_own_listener" not in out.split("short test summary info")[-1], out

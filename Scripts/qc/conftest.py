"""No test may write to the data lake. Enforced, not asked for.

WHY THIS EXISTS (2026-08-29, and it is not hypothetical).

`test_verify_tile_reads_the_tagged_index_not_the_legacy_one` monkeypatched
`phase4_train_queue.BASE` to a tmp_path and believed that redirected the module.
It does not. The queue binds its paths at IMPORT time:

    BASE    = ...                                  lake.py::BASE (imported by the queue)
    QC_DIR  = BASE / "phase4" / "qc"               ::QC_DIR
    STATUS  = QC_DIR / "train_queue_status.csv"    ::STATUS

`QC_DIR` and `STATUS` are already-computed Path objects. Rebinding `BASE`
afterwards leaves them pointing at the real lake. `_status_write` then resolves
`out = STATUS_OUT if STATUS_OUT is not None else STATUS`
(queue_ledger.py::_status_write), and `STATUS_OUT`
is None outside `main()` — so the test wrote a fixture row to

    G:/My Drive/treedata/phase4/qc/train_queue_status.csv

through the absent-destination publish helper, replacing 69 rows of real queue
history (2026-08-18..22, including the hand-written closure rows for the
interrupted 2024/2019 runs) with one row reading `j1,2009,mytag,...`. The repo's
harvested copy was the only surviving version, and `harvest_results.py` compares
size+sha and copies lake→repo — so the next session-end harvest would have
committed the deletion over the backup.

The test suite is the one thing that runs constantly, unattended, against a
module whose real paths are one attribute away. A convention ("remember to patch
_status_write") is not a control; several tests here do remember, and one did not.

WHAT THIS DOES. Fingerprints the real lake artifacts once, before any test can
patch anything, then fails any test that changed them. It does not redirect
writes — redirecting module globals for every test would change behaviour the
tests are there to measure. It detects, loudly, and names the test.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))


def _real_targets():
    """The lake paths a test could plausibly reach, resolved BEFORE any patching.

    Imported lazily and tolerantly: this file must not break collection on a
    machine with no lake mounted, or without torch/pandas available.
    """
    targets = []
    try:
        import phase4_train_queue as q
        targets += [q.STATUS, q.QC_DIR, q.MASKS]
    except Exception:                                            # noqa: BLE001
        pass
    return [p for p in targets if p is not None]


_TARGETS = _real_targets()


# ── litkb: the Postgres-backed tests (design LITERATURE_KB_DESIGN_2026-09-13.md §9) ────────
# Tests that need the local litkb server carry @pytest.mark.requires_litkb_pg and SKIP when
# the server, the litkb_test role or psycopg is absent, so the ladder still runs on a
# machine without Postgres. A skip must never be silent: the summary below counts them.
_LITKB_MARK = "requires_litkb_pg"


_LITKB_LIVE = "litkb_live"


def pytest_configure(config):
    # the no-network guard's port list includes every port this process binds on loopback; record them
    # from the start, so a server a module-scoped fixture binds before any test's guard is known too
    try:
        from litkb.cassette import watch_loopback_binds
        watch_loopback_binds()
    except Exception:                                            # noqa: BLE001 — `_no_network` fails closed
        pass
    config.addinivalue_line(
        "markers",
        f"{_LITKB_MARK}: needs the local litkb PostgreSQL server (localhost:5433, role "
        "litkb_test); skipped when absent, and the skip count is printed")
    config.addinivalue_line(
        "markers",
        f"{_LITKB_LIVE}: reaches the network (registries, archives); skipped unless LITKB_LIVE=1, "
        "so the ladder never depends on a remote service (litkb P2)")


_LITKB_SUITE_LOCK = 0x6C6B7473  # "lkts"
_LITKB_SKIP_WHEN = ("connection refused", "could not connect", "does not exist",
                    "no password supplied", "timeout expired", "is the server running")


@pytest.fixture(scope="session")
def litkb_pg_base():
    """(psycopg, conn, applied) — ONE reset and migration of litkb_test per pytest session, shared by the P1 and
    P2 suites (qc/test_litkb_p1.py, qc/test_litkb_p2.py). It lived in the P1 module; two modules each holding the
    suite's advisory lock on their own connection in one process would wait on each other forever. The suite
    logs in ONLY as litkb_test, to litkb_test, under the advisory lock (parallel worktrees serialise)."""
    psycopg = pytest.importorskip("psycopg", reason="requires_litkb_pg: psycopg is not installed")
    from litkb.db import connect as c
    from litkb.db import migrate
    try:
        conn = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
    except psycopg.OperationalError as e:
        msg = str(e).strip()
        if any(s in msg.lower() for s in _LITKB_SKIP_WHEN):
            pytest.skip(f"requires_litkb_pg: litkb_test unavailable ({msg.splitlines()[-1][:160]})")
        raise
    conn.execute("SELECT pg_advisory_lock(%s)", (_LITKB_SUITE_LOCK,))
    migrate.reset(conn)
    ran = migrate.apply(conn)
    yield psycopg, conn, ran
    conn.close()


def pytest_collection_modifyitems(config, items):
    import os

    if os.environ.get("LITKB_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason=f"{_LITKB_LIVE}: network test; run with LITKB_LIVE=1")
    for item in items:
        if _LITKB_LIVE in item.keywords:
            item.add_marker(skip)


def pytest_terminal_summary(terminalreporter):
    counts = {}
    for outcome in ("passed", "failed", "error", "skipped"):
        n = sum(1 for r in terminalreporter.stats.get(outcome, [])
                if _LITKB_MARK in getattr(r, "keywords", {}))
        if n:
            counts[outcome] = n
    if counts:
        line = "litkb Postgres tests: " + ", ".join(f"{n} {k}" for k, n in counts.items())
        if "skipped" in counts:
            line += (f"  <- {counts['skipped']} SKIPPED: litkb server/role/psycopg absent, "
                     "so those guards were NOT tested")
        terminalreporter.write_line(line)
    # BEGIN guard: a register row the edges pytest did not replay is named in the summary
    # S4.5 run-plan §8 Q3: the rows the live pass recorded are graded by `hardening --replay` only. The edges
    # pytest names and counts them (`qc/test_litkb_edges.py`); this line says so on every run that reached
    # them, the way the skip count above says which guards were NOT tested.
    for note in getattr(terminalreporter.config, "_litkb_named_outcomes", None) or ():
        terminalreporter.write_line(note)
    # END guard: a register row the edges pytest did not replay is named in the summary


# ── no test reaches the network (S4.5 item 7; brief-COMMON rule 11) ──────────────────────────
# S4 found a test that had written 22 real registry-cache files: it had reached Crossref, and nothing
# in the suite could have said so, because litkb's client never raises — an unreachable host is
# `status 0` and a test built on a stub-shaped answer can pass either way. So every test now runs
# inside `litkb.cassette.SocketGuard` (the one home of the guard; the replay runs inside the same
# class), which COUNTS and refuses every connect to a non-loopback host and every lookup of a
# non-loopback name, and this fixture FAILS the test at teardown when the count is not zero —
# a test that reached for the network is a finding even when it passed.
#
# ALLOWED: loopback as HOST AND PORT (Codex finding X3, brief-CONTRACTS.md; auditor-A round 2, F3),
# never "every loopback port": a loopback port can forward off the machine (a proxy, an SSH tunnel, a
# solver), and a connect to it would be allowed and uncounted. The ports (`_suite_ports`):
#   * PostgreSQL's, `litkb.db.connect.PORT` (LITKB_PGPORT, 5433). libpq opens that socket in C, so the
#     guard never sees it; the port is listed so the allowlist says what the suite may reach.
#   * GROBID's, the port of `litkb.extract.grobid.DEFAULT_URL` (GROBID_URL, http://localhost:8070) when
#     its host is loopback — a local service. The tests that need it are `litkb_live` and skip without
#     LITKB_LIVE=1; measured (builder-A round 1, LITKB_SOCKET_GUARD_LOG over the whole suite): no
#     non-live test touched it. A remote GROBID_URL is the network and is not listed.
#   * every port THIS process bound on loopback (`litkb.cassette.watch_loopback_binds`, installed at
#     configure time): a test's own local HTTP server, and asyncio's self-pipe, which on Windows is a
#     loopback socketpair (the p8 and web-gate MCP tests' ports in that measurement).
# Loopback NAMES resolve so psycopg's own host lookup still works. A test that needs a port nothing
# listens on binds one itself and does not listen (`test_process_pdf_raises_when_unreachable`).
# EXCEPTED: a `litkb_live` test while LITKB_LIVE=1 — reaching the network is what it is for.
# NOT COVERED: a SUBPROCESS a test starts (`py -m litkb …`) — the patch lives in this interpreter.
# NOT COVERED: an asyncio connect on Windows' Proactor loop (`asyncio.open_connection`): it connects through
# `_overlapped.ConnectEx` in C, below the Python-level patches (auditor-A round 3 F2, DS2: measured on loopback).
# Latent — no litkb module and no test opens an asyncio network connection (grep, same audit); the ladder is
# urllib. The REPLAY guard fails closed on it (the loop's own self-pipe connect is refused). Integrator-w2.
# Set LITKB_SOCKET_GUARD_LOG=<file> to append every loopback port a test touched (a measurement).
#
# NO PROXY, NO SOLVER (auditor-A round 1, F11). Loopback is allowed, so a proxy on a loopback port
# (HTTP(S)_PROXY / ALL_PROXY, or a Windows system proxy urllib reads from the registry) or a local
# FlareSolverr (FLARESOLVERR_URL) would carry a test's request OFF the machine through an allowed
# connect, uncounted. Every test therefore runs with the proxy variables and FLARESOLVERR_URL unset and
# NO_PROXY=* (which also makes urllib ignore the registry proxy): every request connects directly, where
# the guard sees its real host. A test that needs one of them sets it itself (monkeypatch).
# FAIL CLOSED: when the litkb package imports but `litkb.cassette` does not, the run is on the wrong
# code (a worktree without PYTHONPATH=pipeline reaches MAIN's install) and every test fails, named —
# the guard is never silently off. Only a tree with no litkb package at all runs unguarded.
_PROXY_ENV = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY",
              "http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "FLARESOLVERR_URL")
_SUITE_PORTS = []


def _suite_ports():
    """The named loopback ports every test may reach (the comment above): PostgreSQL's and a loopback
    GROBID's, each read from its one home. A home that cannot be read adds nothing — the guard is then
    STRICTER (only this process's own ports), never wider."""
    if _SUITE_PORTS:
        return _SUITE_PORTS[0]
    from urllib.parse import urlsplit

    from litkb.cassette import is_loopback
    ports = set()
    try:
        from litkb.db.connect import PORT
        ports.add(int(PORT))
    except Exception:                                            # noqa: BLE001
        pass
    try:
        from litkb.extract.grobid import DEFAULT_URL
        u = urlsplit(DEFAULT_URL)
        if is_loopback(u.hostname):
            ports.add(int(u.port or (443 if u.scheme == "https" else 80)))
    except Exception:                                            # noqa: BLE001
        pass
    _SUITE_PORTS.append(frozenset(ports))
    return _SUITE_PORTS[0]


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    import importlib.util
    import os

    if os.environ.get("LITKB_LIVE") == "1" and _LITKB_LIVE in request.keywords:
        yield
        return
    try:
        from litkb.cassette import SocketGuard
    except Exception as e:                                       # noqa: BLE001
        # BEGIN guard: the no-network guard fails closed when litkb imports without it
        if importlib.util.find_spec("litkb") is not None:
            pytest.fail(f"qc/conftest.py cannot import litkb.cassette ({type(e).__name__}: {e}) although "
                        "the litkb package imports: this run is on the wrong litkb (from a worktree, set "
                        "PYTHONPATH=pipeline). The no-network guard fails closed.", pytrace=False)
        # END guard: the no-network guard fails closed when litkb imports without it
        yield            # a tree without the litkb package has nothing of litkb's to guard
        return
    # BEGIN guard: no test reaches the network through a proxy or a solver
    for name in _PROXY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    # END guard: no test reaches the network through a proxy or a solver
    guard = SocketGuard(allow_ports=_suite_ports(), label=f"qc/conftest.py no-network guard ({request.node.name})")
    with guard:
        yield
    log = os.environ.get("LITKB_SOCKET_GUARD_LOG")
    if log:
        local = sorted({f"{a['host']}:{a['port']}" for a in guard.attempts
                        if a["allowed"] and a["port"] is not None})
        if local:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"{request.node.nodeid}\t{' '.join(local)}\n")
    reached = guard.blocked
    # BEGIN guard: a test that reached for the network fails
    if reached:
        seen = "\n  ".join(f"{a['how']} {a['host']}:{a['port']}" for a in reached[:10])
        pytest.fail(f"TEST REACHED FOR THE NETWORK: {request.node.nodeid}\n  {seen}\n\n"
                    "Give it a stub or a recorded cassette (litkb.cassette); never widen the guard. "
                    "A test that needs the real network is marked litkb_live.", pytrace=False)
    # END guard: a test that reached for the network fails


def _fingerprint(p):
    """(exists, size, mtime) for a file; (exists, entry count) for a directory."""
    try:
        if p.is_dir():
            return ("dir", sum(1 for _ in p.iterdir()))
        st = p.stat()
        return ("file", st.st_size, st.st_mtime_ns)
    except OSError:
        return ("absent",)


@pytest.fixture(autouse=True)
def _lake_is_read_only(request):
    if not _TARGETS:
        yield
        return
    before = {p: _fingerprint(p) for p in _TARGETS}
    yield
    changed = [p for p in _TARGETS if _fingerprint(p) != before[p]]
    # 2026-09-05: the "rare check.py flicker" root cause. QC_DIR and MASKS are
    # fingerprinted as DIRECTORIES (entry count) — a live Colab queue landing a
    # status CSV / mask mid-test changes the count and this guard blamed the
    # test. Attribution: if every changed target is a directory whose count
    # only GREW, and a fresh VM heartbeat (<20 min) exists on the lake, demote
    # to a warning. File targets (q.STATUS — the 2026-08-29 69-row disaster
    # class) still hard-fail unconditionally.
    if changed:
        import time as _time
        import warnings as _warnings
        dirs_only = all(before[p][0] == "dir" for p in changed)
        grew_only = dirs_only and all(
            _fingerprint(p)[1] >= before[p][1] for p in changed)
        live_vm = False
        try:
            hb_dir = _TARGETS[0].parent.parent / "logs"
            live_vm = any(
                _time.time() - f.stat().st_mtime < 1200
                for f in hb_dir.glob("heartbeat_*.json"))
        except Exception:                                        # noqa: BLE001
            pass
        if grew_only and live_vm:
            _warnings.warn(
                f"lake directories grew during {request.node.name} while a "
                f"live VM heartbeat is fresh — attributed to the running "
                f"campaign, not the test: "
                + ", ".join(str(p) for p in changed))
            changed = []
    if changed:
        names = "\n  ".join(str(p) for p in changed)
        pytest.fail(
            f"TEST WROTE TO THE DATA LAKE: {request.node.name}\n  {names}\n\n"
            "Patching `BASE` does not redirect QC_DIR/STATUS/MASKS — those are bound "
            "at import from the ORIGINAL BASE. Patch the path you actually write "
            "through (STATUS_OUT, QC_DIR, STATUS), or stub `_status_write`.\n"
            "This guard exists because a test destroyed 69 rows of queue history "
            "on 2026-08-29 exactly this way.")

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

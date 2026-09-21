"""A hunt stops GROBID only when the hunt started it (`litkb/hunt.py::extract_and_ingest`, S4).

THE DEFECT. `litkb.extract.grobid.start` is IDEMPOTENT and answers True at once when `health()`
says the service is already up — so its return value means "it is up", not "I brought it up". The
hunt's `finally` read it as the second and called `G.stop()` on every hunt, which stops a service
somebody else is holding open: an operator with a `wsl.exe` client open for a batch, or the run
that is about to hunt the next reference. GROBID was found DOWN at the start of S4 after S3's
hunts, and this is the likely reason (found by builder Q1, 2026-09-21).

NO NETWORK, NO DATABASE, NO WSL. Every seam `extract_and_ingest` reaches out through is replaced:
the GROBID adapter's `health`/`start`/`stop`/`extract`, the inventory probe, Docling, the
reconciler and the ingest login. What is under test is six lines of lifecycle logic, so nothing
else is allowed to run.
"""
import types
from unittest import mock

import pytest


class _Calls:
    def __init__(self):
        self.stopped = 0
        self.started = 0


def _drive(tmp_path, *, alive_before, start_returns=True):
    """Run `extract_and_ingest` over a stubbed world. -> (timing, calls)."""
    from litkb import hunt as H

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    calls = _Calls()

    def _start(**_kw):
        calls.started += 1
        return start_returns

    def _stop():
        calls.stopped += 1

    rec = {"route": "native", "sha256": "0" * 64, "pages": 3, "ocr_pages": (), "page_detail": []}
    stats = {"by_kind": {"paragraph": 2}, "matched": 2, "grobid_regions": 5, "docling_regions": 5}
    cov = {1: {"page_class": "native", "chars": 100, "covered": 95, "share": 0.95}}
    res = {"run_id": "01a0c263-3977-7483-bdb9-f483890782be", "inserted": 2, "blocks": 2,
           "disagreements": 0}
    conn = types.SimpleNamespace(close=lambda: None)
    timing = {}

    from litkb import ingest as ingest_login
    from litkb.extract import docling as D
    from litkb.extract import grobid as G
    from litkb.extract import ingest as ing
    from litkb.extract import inventory as I
    from litkb.extract import reconcile as R

    with mock.patch.object(G, "health", return_value=alive_before), \
         mock.patch.object(G, "start", _start), \
         mock.patch.object(G, "stop", _stop), \
         mock.patch.object(G, "extract", return_value=(b"<TEI/>", {})), \
         mock.patch.object(I, "probe_file", return_value=rec), \
         mock.patch.object(I, "page_frames", return_value={}), \
         mock.patch.object(D, "extract", return_value=({}, {})), \
         mock.patch.object(R, "reconcile", return_value=([], [], stats)), \
         mock.patch.object(R, "coverage", return_value=cov), \
         mock.patch.object(ing, "ingest_file", return_value=res), \
         mock.patch.object(ingest_login, "connect", return_value=conn):
        _res, _detail = H.extract_and_ingest(None, "f", str(pdf), timing=timing, derived=str(tmp_path),
                                             device="cpu")
    return timing, calls


def test_a_hunt_against_an_already_running_grobid_leaves_it_running(tmp_path):
    """THE KILL. `start` returned True because the service was already alive; stopping it here
    takes down somebody else's service."""
    pytest.importorskip("litkb", reason="litkb imports only with PYTHONPATH=pipeline")
    timing, calls = _drive(tmp_path, alive_before=True)
    assert calls.started == 1
    assert calls.stopped == 0, "the hunt stopped a GROBID it did not start"
    assert timing["grobid_was_already_running"] is True


def test_a_hunt_that_brought_grobid_up_stops_it_again(tmp_path):
    """The other half, and the reason the `finally` exists at all: a hunt that started the
    service must not leave it running — otherwise the fix would be a leak."""
    pytest.importorskip("litkb", reason="litkb imports only with PYTHONPATH=pipeline")
    timing, calls = _drive(tmp_path, alive_before=False)
    assert calls.started == 1 and calls.stopped == 1
    assert timing["grobid_was_already_running"] is False


def test_a_grobid_that_never_came_up_is_not_stopped_and_does_not_fail_the_hunt(tmp_path):
    """`start` returning False is "it never came up". There is nothing to stop, and the hunt
    carries on with Docling alone — a GROBID failure is a weaker extraction, not a failed hunt."""
    pytest.importorskip("litkb", reason="litkb imports only with PYTHONPATH=pipeline")
    timing, calls = _drive(tmp_path, alive_before=False, start_returns=False)
    assert calls.stopped == 0
    assert "GROBID did not come up" in timing["grobid_error"]

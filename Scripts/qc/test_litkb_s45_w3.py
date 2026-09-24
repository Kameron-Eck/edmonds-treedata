"""litkb S4.5 — integrator-w3: the orchestrator's rulings D23-D28 on the w3 candidate. Each test names the ruling it
holds and fails when that ruling's code is reverted (a mutation row in qc/instruments/litkb_p2_mutations.py, block
"integrator-w3", names each one).

  D24   ONE challenge detector (`netutil.Client.challenge_cause` / `is_challenge`): MDPI's REAL recorded Akamai
        "Access Denied" 403 is a challenge to it, to the ledger's typing, to the landing rung and to the acceptance
        test; a live host's challenge bytes are booked `blocked/challenge_or_bot_check` by the ladder (first sight
        and served again), a Stage E capture of one stays the bad file; survey G0d's title-only rule at a 200 stays
  D25   `litkb admit --file` and the MCP `litkb_admit(file=)` land the operator's file as a PROPOSAL (migration
        0035); the work stays a registry fact; other callers of `admit_registry` are unchanged
  D27   the ladder-1 run driver switches the shadow tier OFF for the live pass when the manifest records it off,
        refuses a manifest that does not (unless explicitly overridden), and restores the code default after
  D23   the report grammar's named-exception line (`exception: <counter> <item> <reason>`)
  D28   a pending file PROPOSAL does not make a work held: the ladder still asks it (decided and justified in
        integrator-w3's report; pinned here so a change is a decision, not an accident)

No test touches the network (loopback only, inside the suite's socket guard) or the live store. Every PDF is
CONSTRUCTED; the Akamai page is the REAL recorded fixture `qc/fixtures/litkb_mdpi_pdf_akamai_a3b93f589df6.html`.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 -m pytest qc/test_litkb_s45_w3.py -q
"""
import importlib.util
import json
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
INSTR = SCRIPTS / "qc" / "instruments"
AKAMAI = SCRIPTS / "qc" / "fixtures" / "litkb_mdpi_pdf_akamai_a3b93f589df6.html"
MDPI_PDF_URL = "https://www.mdpi.com/2072-4292/15/3/765/pdf"
pg_only = pytest.mark.requires_litkb_pg


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2M = _load("_litkb_p2_for_w3", SCRIPTS / "qc" / "test_litkb_p2.py")
HA = _load("_litkb_hardening_a_for_w3", INSTR / "litkb_hardening_a.py")
B2H = _load("_litkb_hardening_b2_for_w3", INSTR / "litkb_hardening_b2.py")
LR = _load("_litkb_ladder_run_for_w3", INSTR / "litkb_ladder_run.py")


@pytest.fixture
def pg(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    h = P2M.P2(psycopg, conn)
    yield h
    while h.opened:
        h.opened.pop().close()


def _store(tmp_path):
    from litkb.acquire.store import Store
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def _rows(pg, wid):
    return pg.conn.execute("SELECT route, status, sub_status, detail, retriable FROM litkb.acquisition_attempts "
                           "WHERE work_id = %s ORDER BY at, id", (wid,)).fetchall()


def _akamai():
    """The REAL recorded MDPI Akamai page, salted with an HTML comment so its sha is new to this database."""
    return AKAMAI.read_bytes().replace(b"</BODY>", f"<!-- {uuid.uuid4().hex} --></BODY>".encode())


# ── D24: one challenge detector ─────────────────────────────────────────────────────────────────

def test_the_one_detector_reads_mdpis_real_akamai_403_and_every_caller_agrees():
    """D24: `netutil.Client.challenge_cause` is the home. The ledger's names are the SAME objects (one list), the
    ledger's typing, the landing rung and the acceptance test all call it, and each calls the REAL Akamai 403 a
    challenge. The pre-D24 `is_challenge` read CHALLENGE_RE only and did not."""
    from litkb import netutil
    from litkb.acquire import accept, landing, ledger
    from litkb.netutil import Client

    page = AKAMAI.read_bytes()
    assert Client.challenge_cause(403, MDPI_PDF_URL, page) == "akamai"
    assert Client.is_challenge(403, MDPI_PDF_URL, page)
    assert not netutil.CHALLENGE_RE.search(page)          # why the old rule missed it
    assert ledger.CHALLENGE_MARKERS is netutil.CHALLENGE_MARKERS and ledger.MARKER_WINDOW == netutil.MARKER_WINDOW
    assert ledger.challenge_cause(page) == "akamai"
    assert ledger.type_blocked([403], page)[:2] == ("challenge_or_bot_check", "bytes")
    assert landing.classify(403, {}, page, MDPI_PDF_URL, purpose="candidate") == ("challenge_or_bot_check", "akamai")
    v = accept.accept(page, url=MDPI_PDF_URL, status=403, metadata_fetched=False)
    assert (v.verdict, v.sub_status, v.challenge) == ("refuse", "html_response", "akamai"), v.summary()
    assert "a bot challenge (akamai)" in v.reason
    # a header signature is a challenge at any status, before the body is read
    assert Client.challenge_cause(200, "https://x.example/p", b"<html>ok</html>", {"CF-Mitigated": "challenge"}) \
        == "header:cf-mitigated"


def test_open_access_itself_books_mdpis_akamai_403_blocked():
    """D24 at the route: open access's own rule (it books `blocked` only when a location's answer is a challenge)
    now reads the REAL Akamai 403 as one — before the ladder's re-book, which is a second line and is tested apart.
    Unpaywall's locations are CONSTRUCTED (one MDPI PDF URL); no request leaves the stub."""
    from litkb.acquire import open_access as OA

    client = P2M.RouteStub({"www.mdpi.com": (403, {"Content-Type": "text/html"}, AKAMAI.read_bytes())})
    r = OA.fetch_open_access("10.3390/rs15030765", None, None, client=client,
                             locations=lambda d: ([MDPI_PDF_URL], "CONSTRUCTED Unpaywall locations"))
    assert (r["status"], r.get("sub_status")) == ("blocked", "challenge_or_bot_check"), r
    assert r["rejected"] and r["http_codes"] == [403], r


def test_the_title_rule_at_a_200_stays_the_one_detectors():
    """Survey G0d (VERIFIED), kept by D24's merge of the two lists: at a status that is not a refusal only the TITLE
    decides — a solved page naming its guard in its scripts is no challenge; a challenge TITLE is one, and the
    window then names the family (Springer's recorded Client Challenge page is F5's)."""
    from litkb.netutil import Client

    solved = b"<html><head><title>Record</title></head><script>ddos-guard challenge-platform recaptcha</script></html>"
    assert Client.challenge_cause(200, "https://x.example/r", solved) == ""
    assert Client.challenge_cause(403, "https://x.example/r", solved) == "cloudflare"     # a refusal page is read whole
    assert Client.challenge_cause(None, None, solved) == "cloudflare"                     # a kept payload, status unknown
    springer = (SCRIPTS / "qc" / "fixtures" / "litkb_landing_pages" / "springer" / "hop2.body").read_bytes()
    assert Client.challenge_cause(200, "https://link.springer.com/x", springer) == "f5"
    assert Client.challenge_cause(200, "https://x.example/p", b"%PDF-1.7 <title>Just a moment</title>") == ""


def _rung_serving(route, body, status=403):
    from litkb.acquire import run

    def fn(work, ctx):
        return {"status": "bad-file", "rejected": body, "rejected_url": MDPI_PDF_URL, "http_codes": [status],
                "tried": [f"www.mdpi.com:{status}"],
                "terminal": {"url": MDPI_PDF_URL, "status_code": status, "headers": {"Content-Type": "text/html"}}}
    return run.Rung(route, fn, needs=("doi",))


def _ask(pg, w, ws, work, store, route, body):
    from litkb.acquire import run

    run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=(route,), rungs=[_rung_serving(route, body)],
                agent="w3", session="w3-1", pacer=P2M._nopace(), printer=lambda *a, **k: None, pacing={})
    return [r for r in _rows(pg, work["work_id"]) if r[0] == route]


@pg_only
def test_a_live_hosts_challenge_bytes_are_booked_blocked_first_seen_and_served_again(pg, tmp_path):
    """D24 at the ladder: a rung (here on route `open_access`, CONSTRUCTED) that books the REAL Akamai 403 page `bad-file` has
    it re-booked `blocked/challenge_or_bot_check` — the acceptance test named the challenge — and the same bytes
    served again to another work (the rejected-hash lookup: never re-judged by the acceptance test) are re-booked
    by the one detector directly."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    body = _akamai()
    store = _store(tmp_path)
    first = _ask(pg, w, ws, P2M._admitted(pg, w, ws), store, "open_access", body)
    assert [(r[1], r[2], r[4]) for r in first] == [("blocked", "challenge_or_bot_check", False)], first
    assert first[0][3]["challenge"] == "akamai" and first[0][3]["acceptance"]["facts"]["challenge"] == "akamai"
    again = _ask(pg, w, ws, P2M._admitted(pg, w, ws), store, "open_access", body)
    assert [(r[1], r[2]) for r in again] == [("blocked", "challenge_or_bot_check")], again
    assert again[0][3]["known_bad"] and again[0][3]["challenge"] == "akamai", again[0][3]


@pg_only
def test_an_archive_capture_of_a_challenge_page_stays_the_bad_file(pg, tmp_path):
    """D24's one exception, by design: a Stage E route (`wayback`) replaying a challenge page it once captured did
    not refuse this client — the capture is the bad file, typed by the acceptance test, the challenge recorded."""
    ws, w = pg.ws(), pg.session("litkb_writer")
    rows = _ask(pg, w, ws, P2M._admitted(pg, w, ws), _store(tmp_path), "wayback", _akamai())
    assert [(r[1], r[2]) for r in rows] == [("bad-file", "html_response")], rows
    assert rows[0][3]["acceptance"]["facts"]["challenge"] == "akamai" and "challenge" not in rows[0][3]


# ── D25: the operator's file through admission is a proposal ─────────────────────────────────────

def _operator_case(tmp_path):
    hexid = uuid.uuid4().hex[:12]
    doi, title, rec = P2M._synthetic(hexid, 2020, "Tester")
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    pdf = root / "Validation" / f"Tester_2020_operator-file-{hexid}.pdf"
    pdf.write_bytes(P2M.paper_pdf(title, "T. Tester"))
    return doi, title, rec, root, pdf


def _key():
    """A key no other synthetic work holds (the derived one is shared by every `_synthetic` record)."""
    return f"Tester_2020_operator-file-{uuid.uuid4().hex[:12]}"


def _file_state(pg, file_id):
    """(the file's version state, is it in main_files) — read on the owner connection."""
    st = pg.one("SELECT v.state FROM litkb.file_versions v WHERE v.file_id = %s ORDER BY v.created_at DESC LIMIT 1",
                (file_id,))[0]
    in_main = pg.one("SELECT count(*) FROM litkb.main_files WHERE file_id = %s", (file_id,))[0]
    return st, in_main


@pg_only
@pytest.mark.parametrize("operator", [True, False])
def test_an_operators_file_admitted_with_its_work_is_a_proposal(pg, tmp_path, operator):
    """D25 / migration 0035: `admit_registry(operator_file=True)` — what `admit --file` and the MCP `file=` pass —
    admits the registry-confirmed WORK as a fact and writes the operator's FILE as a proposal (in-place route
    `held-in-place`): main holds the work and not the file, the approver's listing shows it, and
    `operator_binds_unproposed` (the gated counter) reads 0. The control (`operator_file=False`, the legacy loader
    and every other caller) is unchanged: the file is main's."""
    P2M._need_pdftotext()
    from litkb.admit import front

    doi, _title, rec, root, pdf = _operator_case(tmp_path)
    ws, w = pg.ws(), pg.session("litkb_writer")
    frozen = pg.one("SELECT now() - interval '1 second'")[0]
    res = front.admit_registry(w, ws, pg.tokens[ws], doi=doi, file_path=pdf, root=root, agent="w3", key=_key(),
                               session="w3-admit", client=P2M.RegistryStub({doi: rec}), pacer=P2M._nopace(),
                               operator_file=operator)
    assert res["outcome"] == "admitted" and res["file_id"], res
    assert pg.one("SELECT count(*) FROM litkb.main_works WHERE work_id = %s", (res["work_id"],))[0] == 1
    unproposed = B2H.operator_binds_unproposed(pg.conn, {"frozen_at": str(frozen), "run_workstream_ids": [str(ws)]})
    if operator:
        assert res["file_state"] == "proposed", res
        assert _file_state(pg, res["file_id"]) == ("proposed", 0)
        pend = [p for p in front.pending_file_proposals(pg.conn) if p["file_id"] == str(res["file_id"])]
        assert [(p["source_route"], p["rel_path"]) for p in pend] == [(front.OPERATOR_ADMIT_ROUTE, f"Validation/{pdf.name}")]
        note = front.operator_file_note(pg.conn, res)
        assert note["file_state"] == "proposed" and note["proposed"][0]["version_id"] and "SECOND session" in note["next"]
        assert unproposed == 0
    else:
        assert res["file_state"] == "promoted", res
        assert _file_state(pg, res["file_id"]) == ("promoted", 1)
        assert front.operator_file_note(pg.conn, res) == {"file_state": "promoted"}


@pytest.fixture
def cenv(tmp_path, monkeypatch, litkb_pg_base):
    """The CLI's and the MCP server's environment on the throwaway database (qc/test_litkb_s3_server.py's `env`):
    `litkb_test` stands in for reader and writer, a worktree holding a real workstream token, and a literature
    root under tmp_path that `front` reads instead of the store's."""
    from litkb import workstream
    from litkb.admit import front
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt), "LITKB_READER_ROLE": "litkb_test",
                 "LITKB_WRITER_ROLE": "litkb_test", "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "w3", "LITKB_SESSION": f"w3-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(front, "LITERATURE_ROOT", root)
    ws_id = str(workstream.open_workstream(conn, f"w3-{uuid.uuid4().hex[:6]}", "test", "D25", directory=wt))

    def writer():
        """A writer session the way the suite makes one (P2.session): the test login, SET ROLE litkb_writer."""
        from psycopg import sql

        k = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
        k.execute(sql.SQL("SET ROLE {}").format(sql.Identifier("litkb_writer")))
        return k
    return {"conn": conn, "wt": wt, "root": root, "ws": ws_id, "writer": writer}


def _operator_pdf(root):
    hexid = uuid.uuid4().hex[:12]
    doi, title, rec = P2M._synthetic(hexid, 2020, "Tester")
    pdf = root / "Validation" / f"Tester_2020_operator-entry-{hexid}.pdf"
    pdf.write_bytes(P2M.paper_pdf(title, "T. Tester"))
    return doi, rec, pdf


@pg_only
def test_litkb_admit_file_at_the_cli_lands_the_file_as_a_proposal(cenv, monkeypatch, capsys):
    """D25 at the CLI: `litkb admit --doi D --file F` — the registry answer stubbed, nothing reaches the network —
    admits the work and PROPOSES the file, and says so (the version a second session decides, and how)."""
    P2M._need_pdftotext()
    from litkb import commands, netutil

    doi, rec, pdf = _operator_pdf(cenv["root"])
    monkeypatch.setattr(netutil, "Client", lambda *a, **k: P2M.RegistryStub({doi: rec}))
    rc = commands.main(["--dir", str(cenv["wt"]), "admit", "--doi", doi, "--file", str(pdf), "--key", _key()],
                       connect=lambda db: cenv["writer"]())
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["outcome"] == "admitted" and out["file_state"] == "proposed", out
    assert out["proposed"][0]["source_route"] == "held-in-place" and "approve-files" in out["next"], out
    st = cenv["conn"].execute("SELECT state FROM litkb.file_versions WHERE file_id = %s", (out["file_id"],)).fetchone()
    assert st == ("proposed",), st


@pg_only
def test_the_mcp_admit_with_a_file_lands_the_file_as_a_proposal(cenv, monkeypatch):
    """D25 at the MCP tool: `litkb_admit(doi=, file=)` (the server's `_admit`, as qc/test_litkb_s3_server.py calls
    them) admits the work and PROPOSES the file, and its answer says so."""
    P2M._need_pdftotext()
    from litkb.mcp import server

    doi, rec, pdf = _operator_pdf(cenv["root"])
    monkeypatch.setattr(server, "_registry_client", lambda: P2M.RegistryStub({doi: rec}))
    monkeypatch.setattr(server, "_conn", lambda kind: cenv["writer"]())
    out = json.loads(server._admit(doi=doi, file=str(pdf), key=_key()))
    assert out["ok"] is True and out["file_state"] == "proposed", out
    assert out["proposed"] and "SECOND session" in out["next"], out
    st = cenv["conn"].execute("SELECT state FROM litkb.file_versions WHERE file_id = %s", (out["file_id"],)).fetchone()
    assert st == ("proposed",), st


# ── D27: the live pass runs with the shadow tier OFF ─────────────────────────────────────────────

def _manifest(tmp_path, shadow):
    m = {"repo": str(tmp_path), "workstream_id": None,
         "cassette_index": {"path": str(tmp_path / "cas" / "index.jsonl"), "bodies": str(tmp_path / "bodies")},
         "rows": [{"id": "L001", "ref": "10.5555/constructed-shadow", "ref_scheme": "doi", "mode": "hunt",
                   "source": ["no-oa-copy"]}]}
    if shadow is not None:
        m["shadow_tier"] = shadow
    return m


def _hunt_seeing(seen):
    def hunt(**kw):
        from litkb.acquire import policy as P

        seen.append((P.SHADOW_TIER_ENABLED, P.decide("scihub").allowed))
        return {"state": "held", "reason": "not-acquired"}
    return hunt


def test_the_live_pass_runs_with_the_shadow_tier_off_and_restores_the_default(tmp_path):
    """D27: a manifest that records `shadow_tier.enabled` false runs its rows with `policy.SHADOW_TIER_ENABLED`
    False — the shadow stage is refused by the ladder's own policy decision — and the code default comes back
    after the pass (the code default stays as merged)."""
    from litkb.acquire import policy as P

    before, seen = P.SHADOW_TIER_ENABLED, []
    ran, _resumed, _rows = LR.run_rows(_manifest(tmp_path, {"enabled": False}), tmp_path / "run.csv", db="unused",
                                       worktree=tmp_path, agent="t", session="t", hunt=_hunt_seeing(seen),
                                       attempts_counter=lambda: 0, record=False)
    assert ran == 1 and seen == [(False, False)], seen
    assert P.SHADOW_TIER_ENABLED is before is True


@pytest.mark.parametrize("shadow", [None, {"enabled": True}])
def test_a_pass_whose_manifest_does_not_switch_the_shadow_tier_off_is_refused_unless_overridden(tmp_path, shadow):
    """D27: a manifest without the switch recorded off (none recorded, or recorded ON) is REFUSED before any row
    runs or anything is recorded; `allow_shadow=True` (the CLI's --allow-shadow-tier) is the explicit override,
    and then the pass runs with the switch on."""
    seen = []
    with pytest.raises(LR.ShadowTierRefused, match="shadow tier"):
        LR.run_rows(_manifest(tmp_path, shadow), tmp_path / "run.csv", db="unused", worktree=tmp_path, agent="t",
                    session="t", hunt=_hunt_seeing(seen), attempts_counter=lambda: 0, record=False)
    assert seen == [] and not (tmp_path / "run.csv").exists()
    ran, _r, _rows = LR.run_rows(_manifest(tmp_path, shadow), tmp_path / "run.csv", db="unused", worktree=tmp_path,
                                 agent="t", session="t", hunt=_hunt_seeing(seen), attempts_counter=lambda: 0,
                                 record=False, allow_shadow=True)
    assert ran == 1 and seen == [(True, True)], seen


def test_the_driver_cli_refuses_and_the_freeze_records_the_switch_off(tmp_path):
    """D27 at the CLI: a hardening manifest frozen without the switch exits 2 and names the override; the freeze's
    own record of it is `enabled: false` with the ruling."""
    A = _load("_litkb_acceptance_for_w3", INSTR / "litkb_acceptance.py")
    m = {"kind": A.HARDENING_MANIFEST_KIND, "frozen_at": "2026-09-23T00:00:00+00:00", "repo": str(tmp_path),
         "db": "unused", "run_csv": "run.csv", "rows": [],
         "gated": [{"name": n, "bound": b} for n, b in A.HARDENING_GATED]}
    m["manifest_sha256"] = A._canonical_sha(m)
    p = tmp_path / "m.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    assert LR.main(["--manifest", str(p), "--no-record"]) == 2
    rec = A._frozen_shadow_tier()
    assert rec["enabled"] is False and "D27" in rec["ruling"], rec


# ── D23: the named-exception line of the report grammar ──────────────────────────────────────────

def test_the_report_names_an_exception_with_its_reason_and_nothing_else_excuses(tmp_path):
    """D23 (the D11 rule): `exception: <counter> <item> <reason>` names one item of one counter; a line without a
    reason, another counter's line, and a report that is not there name nothing (fail closed)."""
    report = tmp_path / "Reports" / "LITKB_LADDER1_CONSTRUCTED.md"
    report.parent.mkdir(parents=True)
    report.write_text("exception: free_ceiling_measured_unconverted 10.5067/doc/ceoswgcv/lpv/lc.001 binding-failed: "
                      "first author not a whole token near the title (a corporate author)\n"
                      "exception: free_ceiling_measured_unconverted 10.5555/no-reason\n"
                      "exception: bban_probe_hits_not_landed 10.5555/other binding-failed\n", encoding="utf-8")
    m = {"repo": str(tmp_path), "report_path": "Reports/LITKB_LADDER1_CONSTRUCTED.md"}
    got = HA.named_exceptions(m, "free_ceiling_measured_unconverted")
    assert got == {"10.5067/doc/ceoswgcv/lpv/lc.001":
                   "binding-failed: first author not a whole token near the title (a corporate author)"}, got
    assert HA.named_exceptions({"repo": str(tmp_path), "report_path": "Reports/absent.md"},
                               "free_ceiling_measured_unconverted") == {}


# ── D28: a pending proposal is not a held file ───────────────────────────────────────────────────

@pg_only
def test_a_pending_file_proposal_does_not_make_its_work_held(pg, tmp_path):
    """D28, decided (integrator-w3's report): `run.work_record.held_files` reads MAIN only. A work whose only file is
    an operator's PROPOSAL is not held — the ladder still asks it — because the proposal's identity is exactly what
    a second session has not confirmed yet (`litkb-from-file-version-state`)."""
    P2M._need_pdftotext()
    from litkb.acquire import run
    from litkb.admit import front

    doi, _title, rec, root, pdf = _operator_case(tmp_path)
    ws, w = pg.ws(), pg.session("litkb_writer")
    res = front.admit_registry(w, ws, pg.tokens[ws], doi=doi, file_path=pdf, root=root, agent="w3", key=_key(),
                               session="w3-admit", client=P2M.RegistryStub({doi: rec}), pacer=P2M._nopace(),
                               operator_file=True)
    assert res["file_state"] == "proposed", res
    work = run.work_record(w, work_id=res["work_id"])
    assert work["held_files"] == 0, work


# ── D29: the misbooked historical bad-file rows are named, never typed ───────────────────────────

C1AH = _load("_litkb_hardening_c1a_for_w3", INSTR / "litkb_hardening_c1a.py")
BADFILE = _load("_litkb_acq_probe_badfile_for_w3", INSTR / "litkb_acq_probe_badfile.py")
BADFILE_CSV = SCRIPTS.parent / "phase4" / "qc" / "litkb_acq_probe_badfile.csv"
BLOCKED_CSV = SCRIPTS.parent / "phase4" / "qc" / "litkb_acq_probe_blocked.csv"


def test_the_item8_instrument_writes_a_misbooked_row_with_no_sub_status():
    """D29 (auditor-cand2 N2): a row the item-8 instrument's own cause calls MISBOOKED carries NO bad-file sub-status
    and no basis (never `too_small` on basis `bytes` for the client's own transport-error text); `cause` reads
    `misbooked` and the finer cause leads `reason`. Every other row is untouched. The TRACKED CSV holds exactly the
    seven the auditor named, each so."""
    import csv

    st, cause, free, grade, fix, reason, _ptr = BADFILE.type_kept(b"URLError: <urlopen error getaddrinfo failed>")
    row = BADFILE.finalize({"attempt_id": "a", "sub_status": st, "basis": "bytes", "cause": cause, "reason": reason})
    assert (row["sub_status"], row["basis"], row["cause"]) == ("", "", "misbooked"), row
    assert row["reason"].startswith("transport_error_string: ") and "misbooked" in BADFILE.CAUSES
    keep = {"attempt_id": "b", "sub_status": "html_response", "basis": "bytes", "cause": "landing_page", "reason": "r"}
    assert BADFILE.finalize(dict(keep)) == keep
    rows = list(csv.DictReader(BADFILE_CSV.open(encoding="utf-8")))
    mis = [r for r in rows if r["cause"] == "misbooked"]
    assert len(mis) == 7 and all(r["sub_status"] == "" == r["basis"] for r in mis), mis
    assert sorted(r["reason"].split(":")[0] for r in mis) == sorted(
        ["transport_error_string"] * 3 + ["challenge_interstitial"] * 2 + ["blocked_not_bad_file", "mirror_miss_page"])
    assert not [r for r in rows if r["basis"] == "bytes" and r["reason"].startswith("transport_error_string")]


def test_the_typing_reader_refuses_a_misbooked_row_by_name(tmp_path):
    """D29 at C1a's backfill reader: a `misbooked` row is refused BY NAME even if a stale file still carries a
    sub-status on it — the fill-null backfill never writes it."""
    import csv

    from litkb.acquire import ledger as L

    f = tmp_path / "typing.csv"
    with open(f, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(L.TYPING_COLUMNS))
        w.writeheader()
        w.writerow({"attempt_id": "a1", "sub_status": "html_response", "basis": "bytes", "cause": "landing_page"})
        w.writerow({"attempt_id": "a2", "sub_status": "too_small", "basis": "bytes", "cause": L.MISBOOKED_CAUSE})
    rows, refused = L.read_typing_csv(f)
    assert [r["attempt_id"] for r in rows] == ["a1"], rows
    assert [(x["attempt_id"], "D29" in x["why"]) for x in refused] == [("a2", True)], refused


@pg_only
def test_bad_file_untyped_excuses_exactly_the_rows_the_item8_csv_names_misbooked(pg, tmp_path):
    """D29 at the gate: `bad_file_untyped` leaves out exactly the attempt ids the manifest's item-8 CSV names
    `misbooked` and REPORTS them as `bad_file_misbooked`; a manifest naming no CSV (or one that is not there)
    excuses nothing. The rows are CONSTRUCTED on the worker database; the counts are deltas (the counter is
    all-time over a shared worker database)."""
    import csv

    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    before = C1AH.bad_file_untyped(pg.conn, {})
    ids = [str(run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "open_access", None, "bad-file",
                                  {"note": "CONSTRUCTED"}, [200])) for _ in range(3)]
    f = tmp_path / "phase4" / "qc" / C1AH.BADFILE_CSV
    f.parent.mkdir(parents=True)
    with open(f, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=BADFILE.COLUMNS, extrasaction="ignore")
        wr.writeheader()
        wr.writerow(BADFILE.finalize({"attempt_id": ids[0], "sub_status": "too_small", "basis": "bytes",
                                      "cause": "transport_error_string", "reason": "CONSTRUCTED"}))
        wr.writerow({"attempt_id": ids[1], "sub_status": "html_response", "basis": "inferred", "cause": "landing_page"})
    m = {"repo": str(tmp_path), "probe_csvs": {C1AH.BADFILE_CSV: f"phase4/qc/{C1AH.BADFILE_CSV}"}}
    assert C1AH.bad_file_untyped(pg.conn, {}) == before + 3
    assert C1AH.bad_file_untyped(pg.conn, m) == before + 2
    assert C1AH.bad_file_misbooked(pg.conn, m) == 1 and C1AH.bad_file_misbooked(pg.conn, {}) == 0
    gone = {"repo": str(tmp_path), "probe_csvs": {C1AH.BADFILE_CSV: "phase4/qc/absent.csv"}}
    assert C1AH.bad_file_untyped(pg.conn, gone) == before + 3


# ── D30: a blocked row typed from the route's own word alone is `inferred` ───────────────────────

def test_a_blocked_row_typed_from_the_routes_own_word_alone_is_inferred():
    """D30 (auditor-cand2 N3): Sci-Hub's `=blocked` token (written for a challenge, a captcha OR a bare 403 alike) and
    open access's own rule with NO bytes kept are `inferred`; open access's rule over its kept first body keeps
    `detail`. The TRACKED blocked CSV carries no row on basis `detail` without kept bytes."""
    import csv

    from litkb.acquire import ledger as L

    assert L.type_blocked([200], None, None, ["sci-hub.ru:200=blocked"])[:2] == ("challenge_or_bot_check", "inferred")
    assert L.type_blocked([200, 403], None, route="open_access")[:2] == ("challenge_or_bot_check", "inferred")
    assert L.type_blocked([200, 403], b"<html><title>Landing</title></html>", route="open_access")[:2] == (
        "challenge_or_bot_check", "detail")
    rows = list(csv.DictReader(BLOCKED_CSV.open(encoding="utf-8")))
    assert rows and not [r for r in rows if r["basis"] == "detail" and not r["kept"]], rows
    assert sum(1 for r in rows if r["basis"] == "inferred") == 27


# ── D23: a free-ceiling row the BINDER refused is a named exception, never a silent pass ──────────

C2AH = _load("_litkb_hardening_c2a_for_w3", INSTR / "litkb_hardening_c2a.py")


@pg_only
def test_free_ceiling_excuses_a_binding_refusal_only_when_the_report_names_it(pg, tmp_path):
    """D23 (the D11 rule) on builder C2a's gated counter: a FREE-PDF row whose work holds no file is counted; a
    BINDING refusal of its bytes in the ledger does not excuse it alone, nor does an `exception:` line alone — both
    together do, and the row is then REPORTED as a named exception with the report's reason. The row, the head CSV
    and the report are CONSTRUCTED (a synthetic DOI on the worker database)."""
    import csv

    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work, bare = P2M._admitted(pg, w, ws), P2M._admitted(pg, w, ws)
    doi = work["doi"]
    head = tmp_path / "phase4" / "qc" / C2AH.HEAD_PROBE
    head.parent.mkdir(parents=True)
    with open(head, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["doi", "resolver", "url", "method", "status", "content_type", "length",
                                            "final_url", "verdict"])
        wr.writeheader()
        for d in (doi, bare["doi"]):
            wr.writerow({"doi": d, "resolver": "openalex", "url": "https://x.example/p.pdf", "method": "GET",
                         "status": 200, "content_type": "application/pdf", "verdict": "FREE-PDF"})
    report = tmp_path / "Reports" / "LITKB_LADDER1_CONSTRUCTED.md"
    report.parent.mkdir(parents=True)
    report.write_text("no exception lines yet\n", encoding="utf-8")
    m = {"repo": str(tmp_path), "probe_csvs": {C2AH.HEAD_PROBE: f"phase4/qc/{C2AH.HEAD_PROBE}"},
         "wayback_positive_dois": [], "report_path": "Reports/LITKB_LADDER1_CONSTRUCTED.md"}
    assert C2AH.free_ceiling_measured_unconverted(pg.conn, m) == 2
    run.record_attempt(w, ws, pg.tokens[ws], work["work_id"], "wayback", doi, "binding-failed",
                       {"binding": {"verdict": "binding-failed",
                                    "reasons": ["first author not a whole token near the title (CONSTRUCTED)"]}},
                       [200])
    assert C2AH.free_ceiling_measured_unconverted(pg.conn, m) == 2          # the refusal alone excuses nothing
    lines = C2AH.free_ceiling_exception_lines(pg.conn, m)
    assert len(lines) == 1 and lines[0].startswith(f"exception: free_ceiling_measured_unconverted {doi} binding-failed")
    # the report names BOTH; only the one the binder refused is excused (the line alone excuses nothing)
    report.write_text(lines[0] + "\n" + f"exception: free_ceiling_measured_unconverted {bare['doi']} a reason\n",
                      encoding="utf-8")
    assert C2AH.free_ceiling_measured_unconverted(pg.conn, m) == 1
    assert C2AH.free_ceiling_named_exceptions(pg.conn, m) == 1
    assert [d for d, _k in C2AH.free_ceiling_detail(pg.conn, m)] == [bare["doi"]]


def test_the_wayback_positive_is_c2cs_regraded_row():
    """D23: the free ceiling's Wayback row is builder C2c's re-graded positive (the IIASA copy), read from its one home,
    never the plan's census row (another work)."""
    C2C = _load("_litkb_hardening_c2c_for_w3", INSTR / "litkb_hardening_c2c.py")
    assert C2AH._wayback_positive() == (C2C.IIASA_DOI, C2C.IIASA_URL)
    rows = C2AH.free_ceiling_rows({"repo": str(SCRIPTS.parent),
                                   "probe_csvs": {C2AH.HEAD_PROBE: f"phase4/qc/{C2AH.HEAD_PROBE}"}})
    assert C2C.IIASA_DOI in rows and C2C.CENSUS_DOI not in rows, rows


# ── item 6: the report's Stage B lines print from the run driver ─────────────────────────────────

def test_the_run_driver_prints_the_reports_stage_b_lines_after_the_pass(tmp_path, monkeypatch, capsys):
    """brief-INTEGRATE-w3 item 6: after its pass the ladder-1 driver prints the LITKB_LADDER1 report's Stage A/B lines
    and the free ceiling's exception lines (`report_lines`); a read that fails is said on stderr and the pass still
    exits 0. The pass itself and the lines are stubbed here (CONSTRUCTED)."""
    A = _load("_litkb_acceptance_for_w3_lines", INSTR / "litkb_acceptance.py")
    m = {"kind": A.HARDENING_MANIFEST_KIND, "frozen_at": "2026-09-23T00:00:00+00:00", "repo": str(tmp_path),
         "db": "unused", "run_csv": "run.csv", "rows": [], "shadow_tier": {"enabled": False},
         "gated": [{"name": n, "bound": b} for n, b in A.HARDENING_GATED]}
    m["manifest_sha256"] = A._canonical_sha(m)
    p = tmp_path / "m.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    monkeypatch.setattr(LR, "run_rows", lambda *a, **kw: (0, 0, []))
    monkeypatch.setattr(LR, "report_lines", lambda manifest: ["yield: arxiv=0/1", "not-built: core CONSTRUCTED"])
    assert LR.main(["--manifest", str(p), "--no-record"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-2:] == ["yield: arxiv=0/1", "not-built: core CONSTRUCTED"], out

    def boom(manifest):
        raise RuntimeError("CONSTRUCTED read failure")
    monkeypatch.setattr(LR, "report_lines", boom)
    assert LR.main(["--manifest", str(p), "--no-record"]) == 0
    assert "report lines unread: RuntimeError" in capsys.readouterr().err


@pg_only
def test_the_run_drivers_report_lines_are_builder_c2as_on_the_real_registry(pg):
    """The lines `report_lines` reads for an (empty) run on the worker database: a `yield:` line for every built Stage B
    rung of the real registry and `not-built: core`, in builder A's grammar (the counter parses every one)."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    ws = pg.ws()
    qc = "phase4/qc"
    m = {"frozen_at": str(pg.one("SELECT clock_timestamp()")[0]), "run_workstream_ids": [str(ws)],
         "repo": str(SCRIPTS.parent),
         "probe_csvs": {"litkb_acq_probe_crosswalk.csv": f"{qc}/litkb_acq_probe_crosswalk.csv",
                        "litkb_acq_probe_head.csv": f"{qc}/litkb_acq_probe_head.csv"}}
    lines = LR.report_lines(m, conn=pg.conn)
    built = [r.route for r in R.RUNGS if P.STAGE_OF.get(r.route) == "B"]
    assert {ln.split("=")[0][len("yield: "):] for ln in lines if ln.startswith("yield: ")} >= set(built), lines
    assert any(ln.startswith("not-built: core ") for ln in lines), lines
    assert set(HA.not_built("\n".join(lines))) == {"core"}

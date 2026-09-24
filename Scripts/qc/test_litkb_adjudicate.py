"""litkb S4.5 builder-B2 — adjudication: the refuse verb, the decision log, withdraw_version, the batched
approval of lone file versions, the operator-bind gate, the refused-duplicate landing and the promote proof
(migration 0034; LITKB_WORKPLAN.md "### S4.5" item 1 and its (b)/(c) lines).

  guard / rule                                                     test
  the refuse verb declines a proposal, rejects its versions,       test_refuse_declines_a_proposal_and_rejects_its_versions
  and moves nothing in main
  what refuse does NOT move — the admitter's uses of the work —    test_a_refusal_names_the_admitters_uses_it_leaves_proposed
  is named (`left_proposed`) with the proposer's withdraw
  BOTH guards refuse the proposing session (Python label check     test_the_proposing_session_cannot_refuse_its_own_admission
  and adjudications_second_session_decides), invisible chars too
  refuse walks a (CONSTRUCTED, owner-level) chain head -> base     test_refuse_rejects_a_constructed_proposal_chain_from_its_head_to_its_base
  refuse is refused on an approved, a registry, a machine-refused  test_refuse_takes_only_a_proposed_manual_admission
  admission (and its dry run says so); an empty reason; an         test_refuse_needs_a_reason_and_an_open_admitter_workstream
  abandoned admitter workstream (D3)
  withdraw: only the proposer, only a proposed head, never an      test_withdraw_retracts_only_the_proposers_own_head
  open admission's version; the head falls back down its chain     test_withdraw_walks_a_chain_down_from_its_head
  to its own proposal only — an edit of main's version removes     test_withdrawing_an_edit_of_mains_version_removes_the_head_and_the_view_follows_main
  the head and the view follows main
  a --from-file bind (browser / held-in-place) and a web landing   test_an_operator_bind_is_a_proposal_never_the_version_of_record
  are PROPOSALS; every automated route stays a fact
  acquire --from-file end to end lands a proposal main cannot see  test_acquire_from_file_end_to_end_is_a_proposal_a_second_session_approves
  (and, approved by a second session, operator_binds_unproposed
  stays 0: the gate's pass path)
  batched approve / refuse of lone file versions, all or nothing,  test_approve_files_is_batched_and_second_session_only
  both guards on the proposing session; a named version that does test_refuse_files_rejects_and_a_batch_with_one_bad_version_moves_nothing
  not exist refuses the whole batch                                test_decide_files_naming_a_version_that_does_not_exist_moves_nothing
  `approve-files --pending` never sends what the plan refuses      test_approve_files_pending_never_sends_what_the_plan_refuses
  the promotion report holds a lone file proposal naming           test_a_lone_file_proposal_is_held_naming_the_verb_that_decides_it
  `approve-files <head>`, never approve_admission
  a file version whose work is not in main is an admission         test_decide_files_refuses_a_version_whose_work_is_not_in_main
  the decision log is append-only for every role, owner included   test_the_decision_log_is_append_only
  the refused-duplicate landing: pass -> proposal, fail ->         test_a_refused_duplicate_landing_is_offered_to_its_work_and_becomes_a_proposal
  quarantine + row + sidecar, bytes held -> duplicate-held          test_a_refused_duplicate_landing_that_does_not_bind_is_quarantined_with_a_row
                                                                   test_a_landing_whose_bytes_are_held_is_quarantined_duplicate_held
  the landing tries the most similar work first; its quarantine    test_a_refused_duplicate_landing_is_offered_to_the_most_similar_work_first
  reason is what the offers said (pending stays pending)           test_the_landing_quarantine_reason_is_what_the_offers_said
  unowned_landings counts a filed PDF no files / quarantine row    test_unowned_landings_counts_only_a_filed_pdf_no_row_holds
  holds, and nothing else
  187's REAL filed PDF, re-served through the URL path, is never   test_187s_real_filed_pdf_is_never_left_unowned
  left unowned (its outcome is MEASURED, not asserted: the report)
  the Python mirrors equal the one home in SQL                     test_the_python_mirrors_equal_the_database
  every new token function has one signature and refuses a bad     test_adjudication_functions_have_one_signature_and_need_their_token
  token
  FIRES (qc/instruments/litkb_hardening_b2.py, each arm pair):     test_every_b2_fire_fires[*]
    refuse verb removed -> proposals_unadjudicated 0 -> 1      (a post-freeze proposal in both arms)
    operator-bind gate deleted -> operator_binds_unproposed 0 -> 1   (a pre-freeze fact bind in both arms)
    run prepares nothing, history does -> promotions_prepared 1 -> 0 (the run's pre-freeze and another
      workstream's post-freeze promotion: each scoping clause alone is load-bearing)
    the proposer refuses itself, constraint dropped -> self_adjudications 0 -> 1
    writer UPDATE granted + trigger disabled -> decision_log_unguarded 0 -> 2
  the promote proof (D6): self-approve refused by both guards,     test_the_constructed_promote_proof
  prepare writes the report, commit refused without a merge

Every row a test writes is CONSTRUCTED except 187's PDF, which is COPIED into pytest's tmp_path (the corpus is
read-only). No test touches the network: every hunt is handed a fetch stub and a registry client that opens no
socket. All of it runs on LITKB_TEST_DB (a worker database); nothing reaches `litkb`.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w12 py -3.12 -m pytest qc/test_litkb_adjudicate.py -q
"""
import hashlib
import importlib.util
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
pg_only = pytest.mark.requires_litkb_pg
LIT = Path(os.environ.get("LITKB_LITERATURE_ROOT_REAL", r"D:\edmonds-pipeline\Literture"))
REAL_187 = LIT / "_litkb_staging" / "filed" / "Tyukavina_2025_land-cover-change-map.pdf"
#: 187's filed PDF, measured 2026-09-21 (Reports/LITKB_RULED_HUNTS_2026-09-21.csv row 187, URL leg)
REAL_187_SHA = "94d8fbed9c8e38d7509b0df438e0c79f9a5c0d6df5433267255dabb4dee3888f"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2M = _load("_litkb_p2_for_adjudicate", SCRIPTS / "qc" / "test_litkb_p2.py")
B2 = _load("_litkb_hardening_b2", SCRIPTS / "qc" / "instruments" / "litkb_hardening_b2.py")


@pytest.fixture
def pg(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    h = P2M.P2(psycopg, conn)
    yield h
    while h.opened:
        h.opened.pop().close()


def _proposal(pg, w, ws, *, session="constructed-proposer", tag="194-shaped"):
    """A CONSTRUCTED 194-shaped manual proposal through `litkb.admit` (litkb_hardening_b2.constructed_proposal,
    the one builder the fires use too). -> the admit result."""
    res = B2.constructed_proposal(pg.conn, ws, pg.tokens[ws], session=session, tag=tag)
    assert res["outcome"] == "proposed", res
    return res


def _heads(pg, ws):
    return pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s", (ws,))[0]


def _versions(pg, work_id):
    """{entity: [state, ...]} of every version of the work, its identifiers and its files."""
    out = {}
    for ent, sql in (("work", "SELECT state FROM litkb.work_versions WHERE work_id = %s"),
                     ("identifier", "SELECT state FROM litkb.identifier_versions WHERE work_id = %s"),
                     ("file", "SELECT state FROM litkb.file_versions WHERE work_id = %s")):
        out[ent] = sorted(r[0] for r in pg.conn.execute(sql, (work_id,)).fetchall())
    return out


def _decisions(pg, **where):
    col, val = next(iter(where.items()))
    return pg.conn.execute(f"SELECT verb, reason, session_id, proposer_session, versions, entity, version_id::text "
                           f"FROM litkb.adjudications WHERE {col} = %s ORDER BY decided_at, id", (val,)).fetchall()


# ── the refuse verb ──────────────────────────────────────────────────────────────────────────

@pg_only
def test_refuse_declines_a_proposal_and_rejects_its_versions(pg):
    """194's shape: a manual proposal from ANOTHER session, adjudicated by a second session. The admission
    becomes `declined` (not `refused`: that word is the machine's), every version it proposed becomes
    `rejected`, the admitter's heads are gone, main never saw it, and ONE decision row says who, what, why."""
    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p)
    assert _heads(pg, ws_p) == 3
    res = front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "CONSTRUCTED: not the document the claim names",
                       "reviewer", "second-session")
    assert res["outcome"] == "declined" and len(res["rejected"]) == 3, res
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (prop["admission_id"],))[0] == "declined"
    assert _versions(pg, prop["work_id"]) == {"work": ["rejected"], "identifier": ["rejected"], "file": ["rejected"]}
    assert _heads(pg, ws_p) == 0
    assert pg.one("SELECT current_version_id FROM litkb.works WHERE id = %s", (prop["work_id"],))[0] is None
    assert pg.one("SELECT count(*) FROM litkb.main_works WHERE work_id = %s", (prop["work_id"],))[0] == 0
    rows = _decisions(pg, admission_id=prop["admission_id"])
    assert len(rows) == 1 and rows[0][0] == "refuse" and rows[0][2] == "second-session", rows
    assert rows[0][3] == "constructed-proposer" and len(rows[0][4]) == 3, rows
    assert {v["to"] for v in rows[0][4]} == {"rejected"}, rows
    assert res.get("left_proposed") == [] and "next" not in res, res          # nothing else depended on it
    # decided once: neither verb takes it again, and the machine's `refused` count did not move
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "again", "reviewer", "second-session")
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        front.approve(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "reviewer", "second-session")


@pg_only
def test_a_refusal_names_the_admitters_uses_it_leaves_proposed(pg):
    """What a refusal does NOT move (auditor-B2 round 2 F5). The admitter's workstream also proposed a gap and a
    USE of the proposed work. The refusal rejects the admission's own work / identifier / file chains and nothing
    else: the use is the proposer's own claim and stays `proposed` — and `promote_prepare` would hold it for ever
    ("the work is not admitted in main", which a declined work never will be). So the dry run and the result
    NAME it as `left_proposed` with the verb that clears it, and the proposer's `withdraw` clears it."""
    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p, tag="with-use")
    q = ("SELECT entity_id, version_id FROM litkb.write_proposal(%s, NULL, %s, NULL, %s, NULL, %s, %s, 'constructed', "
         "'constructed-proposer')")
    gid, _gv = pg.one(q, ("gap", pg.jsonb({"slug": f"constructed-left-{uuid.uuid4().hex[:8]}"}),
                          pg.jsonb({"question": "CONSTRUCTED: a gap the declined work's use feeds", "gap_state": "open"}),
                          ws_p, pg.tokens[ws_p]), conn=w)
    uid, uv = pg.one(q, ("use", pg.jsonb({"work_id": str(prop["work_id"]), "gap_id": str(gid)}),
                         pg.jsonb({"statement": "CONSTRUCTED: a use of the proposed work", "kind": "context",
                                   "status": "proposed", "feeds": [], "rationale": None}),
                         ws_p, pg.tokens[ws_p]), conn=w)
    left = [{"entity": "use", "id": str(uid), "version": str(uv)}]
    plan = front.refuse_plan(w, prop["admission_id"], "second-session")
    assert plan["would"] == "declined" and plan.get("left_proposed") == left, plan
    res = front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "CONSTRUCTED: declined with a use on it",
                       "reviewer", "second-session")
    assert res["outcome"] == "declined" and len(res["rejected"]) == 3, res
    assert res.get("left_proposed") == left and "withdraw" in res.get("next", ""), res
    assert pg.one("SELECT state FROM litkb.use_versions WHERE version_id = %s", (uv,))[0] == "proposed"
    wd = front.withdraw(w, ws_p, pg.tokens[ws_p], "use", uv, "CONSTRUCTED: its work was declined", "constructed",
                        "constructed-proposer")
    assert wd["outcome"] == "withdrawn" and wd["head"] is None, wd
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity = 'use'", (ws_p,))[0] == 0


@pg_only
def test_the_proposing_session_cannot_refuse_its_own_admission(pg):
    """BOTH guards (plan item 1, survey §1.8 R2 N1): the Python label check, invisible characters ignored, and —
    called past it — the database's `adjudications_second_session_decides`. Nothing moves either way."""
    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p, session="sess-admit")
    for label in ("sess-admit", " sess-admit ", "sess\u200b-admit"):
        with pytest.raises(front.AdmissionError, match="own session"):
            front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "self", "other-agent", label)
    q = "SELECT litkb.refuse_admission(%s, %s, %s, 'self', 'other-agent', %s)"
    for label in ("sess-admit", " sess-admit "):
        with pytest.raises(pg.errors.CheckViolation, match="adjudications_second_session_decides"):
            pg.one(q, (ws_r, pg.tokens[ws_r], prop["admission_id"], label), conn=w)
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (prop["admission_id"],))[0] == "proposed"
    assert _versions(pg, prop["work_id"]) == {"work": ["proposed"], "identifier": ["proposed"], "file": ["proposed"]}
    assert _heads(pg, ws_p) == 3 and _decisions(pg, admission_id=prop["admission_id"]) == []


@pg_only
def test_refuse_rejects_a_constructed_proposal_chain_from_its_head_to_its_base(pg):
    """The walk head -> base (auditor-B2 F4). No API writes a second proposed version of an admission's work in
    its workstream today (write_proposal takes gap/use; admit and attach_file write version 1), so this chain is
    CONSTRUCTED at the owner level with `litkb._write_version` (the hunt/P8 seeding shape): v2 of the proposed
    work, based on v1, in the admitter's workstream. The refusal rejects BOTH work versions (the head and its
    base), and the decision row lists both — a head-only walk would leave v1 `proposed`."""
    from psycopg.types.json import Jsonb

    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p, tag="chain")
    v1, fields = pg.one("SELECT version_id, jsonb_build_object('type', type, 'title', title, 'authors', authors, "
                        "'year', year) FROM litkb.work_versions WHERE work_id = %s", (prop["work_id"],))
    v2 = pg.one("SELECT version_id FROM litkb._write_version('proposal', 'work', %s, NULL, %s, %s, "
                "'CONSTRUCTED: a second version of the proposed work', %s, 'constructed-proposer', "
                "'constructed-proposer')",
                (prop["work_id"], v1, Jsonb(fields | {"venue": "CONSTRUCTED chain v2"}), ws_p))[0]
    assert pg.one("SELECT version_id FROM litkb.ws_heads WHERE workstream_id = %s AND entity = 'work'",
                  (ws_p,))[0] == v2
    res = front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "CONSTRUCTED: a refused chain", "reviewer",
                       "second-session")
    assert res["outcome"] == "declined", res
    assert _versions(pg, prop["work_id"]) == {"work": ["rejected", "rejected"], "identifier": ["rejected"],
                                              "file": ["rejected"]}
    moved = {(m["entity"], m["version"]) for m in res["rejected"]}
    assert {("work", str(v1)), ("work", str(v2))} <= moved and len(res["rejected"]) == 4, res["rejected"]
    logged = _decisions(pg, admission_id=prop["admission_id"])[0][4]
    assert {v["version"] for v in logged if v["entity"] == "work"} == {str(v1), str(v2)}, logged
    assert _heads(pg, ws_p) == 0


@pg_only
def test_refuse_takes_only_a_proposed_manual_admission(pg, tmp_path):
    """N2/N4/P3 of survey §1.8: an APPROVED admission, a REGISTRY admission and a MACHINE-refused manual
    admission are each refused 55000, and none gains a decision row."""
    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    approved = _proposal(pg, w, ws_p)
    front.approve(w, ws_r, pg.tokens[ws_r], approved["admission_id"], "reviewer", "approver-session")
    _h, work, ids = P2M._good_payload()
    registry = P2M._admit_sql(pg, w, ws_p, work, ids)
    assert registry["outcome"] == "admitted", registry
    machine = P2M._admit_sql(pg, w, ws_p, {"type": "report", "title": "CONSTRUCTED machine-refused proposal",
                                            "authors": [], "year": 2015},
                             [{"scheme": "url", "value": f"https://constructed.invalid/{uuid.uuid4().hex}",
                               "verified_by": "manual", "evidence": {}}], file_json=None, route="manual")
    assert machine["outcome"] == "refused" and machine["refused_at"] == "check4_manual", machine
    for adm in (approved["admission_id"], registry["admission_id"], machine["admission_id"]):
        # the dry run says so first (auditor-B2 F5: advisory, but it is what the reviewer reads)
        plan = front.refuse_plan(w, adm, "second-session")
        assert plan["would"] == "refused", plan
        assert any("only a proposed manual admission is refused" in x for x in plan["why"]), plan
        with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
            front.refuse(w, ws_r, pg.tokens[ws_r], adm, "CONSTRUCTED: should not apply", "reviewer", "second-session")
        assert _decisions(pg, admission_id=adm) == []
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (machine["admission_id"],))[0] == "refused"


@pg_only
def test_refuse_needs_a_reason_and_an_open_admitter_workstream(pg):
    """N6 (an empty or invisible reason: the Python check, then `adjudications_reason_given` past it) and D3 for
    refuse as it is for approve: an admitter workstream abandoned first leaves the call refused, nothing written."""
    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p)
    with pytest.raises(front.AdmissionError, match="needs a reason"):
        front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "  ", "reviewer", "second-session")
    for reason in ("", "\u200b", None):
        with pytest.raises(pg.errors.CheckViolation, match="adjudications_reason_given"):
            pg.one("SELECT litkb.refuse_admission(%s, %s, %s, %s, 'reviewer', 'second-session')",
                   (ws_r, pg.tokens[ws_r], prop["admission_id"], reason), conn=w)
    w.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws_p, pg.tokens[ws_p]))
    with pytest.raises(pg.errors.InvalidParameterValue, match="not open"):
        front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "CONSTRUCTED: D3", "reviewer", "second-session")
    assert pg.one("SELECT state FROM litkb.admissions WHERE id = %s", (prop["admission_id"],))[0] == "proposed"
    assert _decisions(pg, admission_id=prop["admission_id"]) == []


# ── the operator-bind gate ───────────────────────────────────────────────────────────────────

def _attach(pg, w, ws, work_id, fjson, session="op-1"):
    return pg.one("SELECT litkb.attach_file(%s, %s, %s, %s, 'operator', %s)",
                  (ws, pg.tokens[ws], work_id, pg.jsonb(fjson), session), conn=w)[0]


def _registry_work(pg, ws):
    work_id, title = B2.constructed_registry_work(pg.conn, ws, pg.tokens[ws])
    return work_id, title


@pg_only
@pytest.mark.parametrize("route", ["browser", "held-in-place", "web"])
def test_an_operator_bind_is_a_proposal_never_the_version_of_record(pg, route):
    """`litkb-from-file-version-state`: a `--from-file` bind (`browser`, `held-in-place`) and a refused-duplicate
    web landing (`web`) are written `proposed` — main cannot see them, the workstream's head holds them — and
    `operator_binds_unproposed` stays 0. The counter over the same rows with the gate absent is the fire's."""
    ws = pg.ws()
    w = pg.session("litkb_writer")
    work_id, title = _registry_work(pg, ws)
    frozen = pg.one("SELECT clock_timestamp()")[0]
    res = _attach(pg, w, ws, work_id, B2._file_json(title, source_route=route, tag=route))
    assert res["outcome"] == "attached" and res["state"] == "proposed", res
    assert pg.one("SELECT state FROM litkb.file_versions WHERE version_id = %s", (res["file_version"],))[0] == "proposed"
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work_id,))[0] == 0
    assert str(pg.one("SELECT version_id FROM litkb.ws_heads WHERE workstream_id = %s AND entity = 'file'",
                      (ws,))[0]) == res["file_version"]
    assert B2.operator_binds_unproposed(pg.conn, {"frozen_at": frozen, "run_workstream_ids": [str(ws)]}) == 0


@pg_only
@pytest.mark.parametrize("route", [None, "open_access", "annas", "scihub", "hunt-url"])
def test_every_automated_route_still_binds_the_version_of_record(pg, route):
    """The gate names the operator's routes and nothing else: a file an automated route landed (or one with no
    route at all, the P2 suite's shape) is still a fact, exactly as before migration 0034."""
    ws = pg.ws()
    w = pg.session("litkb_writer")
    work_id, title = _registry_work(pg, ws)
    res = _attach(pg, w, ws, work_id, B2._file_json(title, source_route=route, tag=str(route)))
    assert res["outcome"] == "attached" and res["state"] == "promoted", res
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work_id,))[0] == 1


@pg_only
def test_acquire_from_file_end_to_end_is_a_proposal_a_second_session_approves(pg, tmp_path):
    """The whole `acquire --from-file` path (acquire.run.land_and_attach, UNCHANGED): the attempt is `ok`, the
    PDF is filed, and the file is a PROPOSAL — the work still holds no file in main — until a SECOND session
    approves it with `approve-files`; then main holds it, and the decision log says who approved it.

    It is also the gate's PASS path during a run (auditor-B2 F1): a `--from-file` bind made after the freeze by
    the run's workstream and APPROVED by a second session is `promoted` — the raw shape the gated counter
    `operator_binds_unproposed` looks for — and is exempt by its `approve` row, so the counter stays 0. The
    other half (the gate off -> 1) is the fire `operator_bind_as_version_of_record`."""
    P2M._need_pdftotext()
    from litkb.acquire import run
    from litkb.admit import front

    ws, ws2 = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    work = P2M._admitted(pg, w, ws)
    store = P2M._store(tmp_path)
    src = tmp_path / "handed.pdf"
    src.write_bytes(P2M.paper_pdf(work["title"], "T. Tester"))
    frozen = pg.one("SELECT clock_timestamp()")[0]
    run_manifest = {"frozen_at": frozen, "run_workstream_ids": [str(ws)]}
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, from_file=src, agent="acq", session="acq-ff",
                      printer=lambda *a: None)
    assert out["outcome"] == "ok" and out["attempts"] == [("browser", "ok")], out
    assert run.work_record(w, work_id=work["work_id"])["held_files"] == 0
    pending = [p for p in front.pending_file_proposals(w) if p["work_id"] == str(work["work_id"])]
    assert len(pending) == 1 and pending[0]["source_route"] == "browser" and pending[0]["is_head"], pending
    assert pending[0]["rel_path"].startswith("_litkb_staging/filed/"), pending
    assert (store.root / pending[0]["rel_path"]).is_file()
    assert B2.operator_binds_unproposed(pg.conn, run_manifest) == 0          # a proposal: not the version of record
    ok = front.decide_files(w, ws2, pg.tokens[ws2], "approve", [pending[0]["version_id"]], None, "reviewer",
                            "second-session")
    assert ok["outcome"] == "approved" and len(ok["decided"]) == 1, ok
    assert run.work_record(w, work_id=work["work_id"])["held_files"] == 1
    assert [r[0] for r in _decisions(pg, version_id=pending[0]["version_id"])] == ["approve"]
    # the approved bind has every property the counter selects on (route, state, after the freeze, the run's
    # workstream) — so the 0 below is the approval exemption's doing, not a scoping miss
    raw = pg.one("SELECT count(*) FROM litkb.file_versions WHERE version_id = %s AND source_route = 'browser' "
                 "AND state = 'promoted' AND created_at > %s AND workstream_id = %s",
                 (pending[0]["version_id"], frozen, ws))[0]
    assert raw == 1, raw
    assert B2.operator_binds_unproposed(pg.conn, run_manifest) == 0


@pg_only
def test_approve_files_is_batched_and_second_session_only(pg):
    """`litkb-from-file-version-state`: approvals BATCHED — one call clears several lone file proposals — and
    both guards refuse the proposing session (Python first; the database past it), with nothing moved."""
    from litkb.admit import front

    ws, ws2 = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    versions = []
    for i in range(3):
        work_id, title = _registry_work(pg, ws)
        versions.append(_attach(pg, w, ws, work_id, B2._file_json(title, source_route="browser", tag=f"b{i}"),
                                session="op-batch")["file_version"])
    plan = front.decide_plan(w, versions, "op-batch")
    assert {p["would"] for p in plan} == {"refused"}, plan
    with pytest.raises(front.AdmissionError, match="proposing session"):
        front.decide_files(w, ws2, pg.tokens[ws2], "approve", versions, None, "reviewer", " op-batch ")
    with pytest.raises(pg.errors.CheckViolation, match="adjudications_second_session_decides"):
        pg.one("SELECT litkb.decide_file_versions(%s, %s, 'approve', %s::uuid[], NULL, 'reviewer', 'op-batch')",
               (ws2, pg.tokens[ws2], versions), conn=w)
    assert {r[0] for r in pg.conn.execute("SELECT state FROM litkb.file_versions WHERE version_id = ANY (%s::uuid[])",
                                           (versions,)).fetchall()} == {"proposed"}
    assert [p["would"] for p in front.decide_plan(w, versions, "second-session")] == ["decide"] * 3
    ok = front.decide_files(w, ws2, pg.tokens[ws2], "approve", versions, "CONSTRUCTED batch", "reviewer",
                            "second-session")
    assert ok["outcome"] == "approved" and len(ok["decided"]) == 3, ok
    assert {r[0] for r in pg.conn.execute("SELECT state FROM litkb.file_versions WHERE version_id = ANY (%s::uuid[])",
                                           (versions,)).fetchall()} == {"promoted"}
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity = 'file'", (ws,))[0] == 0
    assert pg.one("SELECT count(*) FROM litkb.adjudications WHERE verb = 'approve' AND version_id = ANY (%s::uuid[])",
                  (versions,))[0] == 3


@pg_only
def test_approve_files_pending_never_sends_what_the_plan_refuses(pg, tmp_path, monkeypatch, capsys):
    """`litkb approve-files --pending` (auditor-B2 round 2 F7, N6) from a session that ITSELF proposed one of the
    pending versions. The batch is all or nothing, so sending that one would refuse every other with it: the CLI
    sends only what the plan decides — the other session's proposal is approved, its own stays proposed — and the
    dry run exits 1 because the plan refuses one. The pending list is the WHOLE database's; this test scopes it to
    its own CONSTRUCTED workstream (the real query, filtered) so the shared worker database's other proposals are
    never decided here."""
    from litkb import commands
    from litkb.admit import front

    ws, ws_dec = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    (a_work, a_title), (b_work, b_title) = _registry_work(pg, ws), _registry_work(pg, ws)
    mine = _attach(pg, w, ws, a_work, B2._file_json(a_title, source_route="browser", tag="pend-own"),
                   session="cli-decider")["file_version"]
    theirs = _attach(pg, w, ws, b_work, B2._file_json(b_title, source_route="browser", tag="pend-other"),
                     session="op-pending")["file_version"]
    real = front.pending_file_proposals
    monkeypatch.setattr(front, "pending_file_proposals", lambda conn, version_ids=None: [
        p for p in real(conn, version_ids) if p["workstream_id"] == str(ws)])
    (tmp_path / ".litkb-workstream").write_text(json.dumps({"workstream_id": str(ws_dec), "token": pg.tokens[ws_dec]}),
                                                encoding="utf-8")
    argv = ["--dir", str(tmp_path), "--agent", "reviewer", "--session", "cli-decider", "approve-files", "--pending"]
    assert commands.main(argv + ["--dry-run"], connect=lambda db: pg.session("litkb_writer")) == 1
    capsys.readouterr()
    try:
        rc = commands.main(argv, connect=lambda db: pg.session("litkb_writer"))
    except front.AdmissionError as e:
        pytest.fail(f"--pending sent a version the plan refuses, and the all-or-nothing batch refused: {e}")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["outcome"] == "approved", out
    assert [d["version"] for d in out["decided"]] == [str(theirs)], out
    states = dict(pg.conn.execute("SELECT version_id::text, state FROM litkb.file_versions "
                                  "WHERE version_id = ANY (%s::uuid[])", ([mine, theirs],)).fetchall())
    assert states == {str(mine): "proposed", str(theirs): "promoted"}, states


@pg_only
def test_a_lone_file_proposal_is_held_naming_the_verb_that_decides_it(pg):
    """The promotion report for a LONE file proposal (auditor-B2 round 2 F1). `promote prepare` holds every file
    chain with `_ws_chains`' sentence "enters main only through litkb.approve_admission" — true for an
    ADMISSION's file, false for an `acquire --from-file` bind on a work main already holds: approve_admission
    refuses that (55000). So for the lone chain the report and the prepare JSON (`promote.chain_why`) name
    `litkb approve-files <head>` and not approve_admission, and that verb moves it; the admission's own file
    chain in the same workstream keeps the admission sentence."""
    from litkb import promote
    from litkb.admit import front

    ws, ws2 = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    work_id, title = _registry_work(pg, ws)
    v = _attach(pg, w, ws, work_id, B2._file_json(title, source_route="browser", tag="lone"))["file_version"]
    _proposal(pg, w, ws, tag="lone-beside")
    head = "e" * 40
    pconn = promote.connect(pg.conn.info.dbname)
    try:
        pid = promote.prepare(pconn, ws, head, None)
        chains = promote.chain_rows(pconn, ws)
        reasons = promote.hold_reasons(pconn, pid)
    finally:
        pconn.close()
    files = {c["head"]: c for c in chains if c["entity"] == "file"}
    lone = files[str(v)]
    assert lone["lone_file"] is True and "prepared" not in lone["states"], lone
    why = promote.chain_why(lone, reasons)
    assert any(f"litkb approve-files {v}" in x for x in why), why
    assert not any("approve_admission" in x for x in why), why
    # auditor-B2 round 3 F6 (its R6: without `dict.fromkeys` the sentence printed twice) and F2 (decide BEFORE commit;
    # integrator-w2)
    assert sum(1 for x in why if x.startswith("lone-file:")) == 1, why
    assert any("BEFORE `promote commit`" in x for x in why), why
    (adm_file,) = [c for h, c in files.items() if h != str(v)]
    assert adm_file["lone_file"] is False and any("approve_admission" in x for x in promote.chain_why(adm_file, reasons))
    report = promote.render_report(ws, pid, head, chains, reasons=reasons)
    row = next(ln for ln in report.splitlines() if f"`{lone['entity_id']}`" in ln)
    assert f"litkb approve-files {v}" in row and "approve_admission" not in row, row
    ok = front.decide_files(w, ws2, pg.tokens[ws2], "approve", [v], None, "reviewer", "second-session")
    assert ok["outcome"] == "approved", ok
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work_id,))[0] == 1


@pg_only
def test_refuse_files_rejects_and_a_batch_with_one_bad_version_moves_nothing(pg):
    """refuse-files: `rejected`, main untouched, a reason required. ALL OR NOTHING: a batch naming one version
    that cannot be decided (already decided) refuses the whole call and leaves the good one proposed."""
    from litkb.admit import front

    ws, ws2 = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    (a_work, a_title), (b_work, b_title) = _registry_work(pg, ws), _registry_work(pg, ws)
    va = _attach(pg, w, ws, a_work, B2._file_json(a_title, source_route="browser", tag="ra"))["file_version"]
    vb = _attach(pg, w, ws, b_work, B2._file_json(b_title, source_route="held-in-place", tag="rb"))["file_version"]
    with pytest.raises(front.AdmissionError, match="needs a reason"):
        front.decide_files(w, ws2, pg.tokens[ws2], "refuse", [va], "", "reviewer", "second-session")
    res = front.decide_files(w, ws2, pg.tokens[ws2], "refuse", [va], "CONSTRUCTED: wrong file", "reviewer",
                             "second-session")
    assert res["outcome"] == "refused", res
    assert pg.one("SELECT state FROM litkb.file_versions WHERE version_id = %s", (va,))[0] == "rejected"
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (a_work,))[0] == 0
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        front.decide_files(w, ws2, pg.tokens[ws2], "approve", [vb, va], None, "reviewer", "second-session")
    assert pg.one("SELECT state FROM litkb.file_versions WHERE version_id = %s", (vb,))[0] == "proposed"
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (b_work,))[0] == 0


@pg_only
def test_decide_files_naming_a_version_that_does_not_exist_moves_nothing(pg):
    """ALL OR NOTHING, the other half (auditor-B2 F2): `approve-files <good> <typo>`. The loop meets only the
    versions that exist, so without the database's count check the typo is skipped and the good version is
    approved with success; the Python front does not look (the CLI sends explicit ids as given). Refused
    P0002, the good version still `proposed`, out of main, with no decision row. The dry run names the typo.
    Naming the SAME existing version twice is one version, not a missing one."""
    from litkb.admit import front

    ws, ws2 = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    work_id, title = _registry_work(pg, ws)
    good = _attach(pg, w, ws, work_id, B2._file_json(title, source_route="browser", tag="typo"))["file_version"]
    typo = str(uuid.uuid4())
    plan = {p["version_id"]: p["would"] for p in front.decide_plan(w, [good, typo], "second-session")}
    assert plan == {str(good): "decide", typo: "refused"}, plan
    for verb, reason in (("approve", None), ("refuse", "CONSTRUCTED: a batch with a typo")):
        with pytest.raises(pg.errors.NoDataFound, match="1 of the 2 distinct file versions named exist"):
            front.decide_files(w, ws2, pg.tokens[ws2], verb, [good, typo], reason, "reviewer", "second-session")
        assert pg.one("SELECT state FROM litkb.file_versions WHERE version_id = %s", (good,))[0] == "proposed"
        assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work_id,))[0] == 0
        assert _decisions(pg, version_id=str(good)) == []
    ok = front.decide_files(w, ws2, pg.tokens[ws2], "approve", [good, good], None, "reviewer", "second-session")
    assert ok["outcome"] == "approved" and len(ok["decided"]) == 1, ok
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work_id,))[0] == 1


@pg_only
def test_decide_files_refuses_a_version_whose_work_is_not_in_main(pg):
    """A proposed file version whose WORK is itself a proposal belongs to an admission: approve_admission or
    refuse_admission decide it, never the lone-file verb (which would put a file in main for no work)."""
    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p)
    fv = pg.one("SELECT version_id FROM litkb.file_versions WHERE work_id = %s", (prop["work_id"],))[0]
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="not in main"):
        pg.one("SELECT litkb.decide_file_versions(%s, %s, 'approve', %s::uuid[], NULL, 'reviewer', 'second-session')",
               (ws_r, pg.tokens[ws_r], [fv]), conn=w)
    assert pg.one("SELECT state FROM litkb.file_versions WHERE version_id = %s", (fv,))[0] == "proposed"


# ── withdraw_version ─────────────────────────────────────────────────────────────────────────

@pg_only
def test_withdraw_retracts_only_the_proposers_own_head(pg):
    """The proposer's retraction: another workstream is refused (`adjudications_withdraw_is_the_proposers`), an
    open admission's version is refused (a second session refuses that), a decided version is refused; the
    proposer's own lone file proposal becomes `withdrawn`, leaves the view, and one decision row says so."""
    from litkb.admit import front

    ws, other = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    work_id, title = _registry_work(pg, ws)
    v = _attach(pg, w, ws, work_id, B2._file_json(title, source_route="browser", tag="wd"))["file_version"]
    with pytest.raises(pg.errors.CheckViolation, match="adjudications_withdraw_is_the_proposers"):
        front.withdraw(w, other, pg.tokens[other], "file", v, "CONSTRUCTED: not mine", "a", "s")
    plan = front.withdraw_plan(w, other, "file", v)
    assert plan["would"] == "refused" and any("only the proposer" in x for x in plan["why"]), plan
    assert front.withdraw_plan(w, ws, "file", v)["would"] == "withdrawn"
    res = front.withdraw(w, ws, pg.tokens[ws], "file", v, "CONSTRUCTED: bound the wrong copy", "operator", "op-2")
    assert res["outcome"] == "withdrawn" and res["head"] is None, res
    assert pg.one("SELECT state FROM litkb.file_versions WHERE version_id = %s", (v,))[0] == "withdrawn"
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity = 'file'", (ws,))[0] == 0
    assert [r[0] for r in _decisions(pg, version_id=str(v))] == ["withdraw"]
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState):
        front.withdraw(w, ws, pg.tokens[ws], "file", v, "again", "operator", "op-2")
    prop = _proposal(pg, w, ws)
    fv = pg.one("SELECT version_id FROM litkb.file_versions WHERE work_id = %s", (prop["work_id"],))[0]
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="proposed manual admission"):
        front.withdraw(w, ws, pg.tokens[ws], "file", fv, "CONSTRUCTED: retract", "operator", "op-2")
    with pytest.raises(front.AdmissionError, match="needs a reason"):
        front.withdraw(w, ws, pg.tokens[ws], "file", fv, " ", "operator", "op-2")


@pg_only
def test_withdraw_walks_a_chain_down_from_its_head(pg):
    """A two-version gap proposal: the lower version is refused (withdraw the head first); the head is
    withdrawn and the workstream's head falls back to the version it was based on; that one then withdraws
    and the view falls back to main (nothing)."""
    from litkb.admit import front

    ws = pg.ws()
    w = pg.session("litkb_writer")
    q = "SELECT entity_id, version_id FROM litkb.write_proposal(%s, %s, %s, %s, %s, %s, %s, %s, 'a', 's')"
    gid, v1 = pg.one(q, ("gap", None, pg.jsonb({"slug": f"constructed-chain-{uuid.uuid4().hex[:8]}"}), None,
                         pg.jsonb({"question": "CONSTRUCTED v1", "gap_state": "open"}), None, ws, pg.tokens[ws]), conn=w)
    _g, v2 = pg.one(q, ("gap", gid, None, v1, pg.jsonb({"question": "CONSTRUCTED v2", "gap_state": "open"}),
                        "CONSTRUCTED edit", ws, pg.tokens[ws]), conn=w)
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="head"):
        front.withdraw(w, ws, pg.tokens[ws], "gap", v1, "CONSTRUCTED", "a", "s")
    assert front.withdraw_plan(w, ws, "gap", v2)["head_falls_back_to"] == str(v1)
    res = front.withdraw(w, ws, pg.tokens[ws], "gap", v2, "CONSTRUCTED: back to v1", "a", "s")
    assert res["head"] == str(v1), res
    assert pg.one("SELECT version_id FROM litkb.ws_heads WHERE workstream_id = %s AND entity_id = %s",
                  (ws, gid))[0] == v1
    front.withdraw(w, ws, pg.tokens[ws], "gap", v1, "CONSTRUCTED: all of it", "a", "s")
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity_id = %s", (ws, gid))[0] == 0
    assert {r[0] for r in pg.conn.execute("SELECT state FROM litkb.gap_versions WHERE gap_id = %s", (gid,))} == \
        {"withdrawn"}


@pg_only
def test_withdrawing_an_edit_of_mains_version_removes_the_head_and_the_view_follows_main(pg):
    """The documented "else the head is removed" branch (auditor-B2 round 2 F3). A workstream proposes an EDIT of
    a gap whose main version is `promoted` (another workstream's, written owner-level: CONSTRUCTED, the P8/hunt
    seeding shape). Withdrawing the edit REMOVES the workstream's head — it never pins it to main's version, which
    is not this workstream's to hold: pinned, the workstream's view would stay at that version after main moves
    on. So after main moves to v2, the workstream sees v2. The dry run says the same (no fallback)."""
    from litkb.admit import front

    ws, other = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    gid, v_main = pg.one("SELECT entity_id, version_id FROM litkb._write_version('fact', 'gap', NULL, %s, NULL, %s, "
                         "NULL, %s, 'constructed', 'constructed')",
                         (pg.jsonb({"slug": f"constructed-main-gap-{uuid.uuid4().hex[:8]}"}),
                          pg.jsonb({"question": "CONSTRUCTED main v1", "gap_state": "open"}), other))
    _g, v_edit = pg.one("SELECT entity_id, version_id FROM litkb.write_proposal('gap', %s, NULL, %s, %s, "
                        "'CONSTRUCTED edit', %s, %s, 'a', 's')",
                        (gid, v_main, pg.jsonb({"question": "CONSTRUCTED ws edit", "gap_state": "open"}), ws,
                         pg.tokens[ws]), conn=w)
    view = "SELECT question FROM litkb.ws_gaps WHERE view_workstream_id = %s AND gap_id = %s"
    assert pg.one(view, (ws, gid))[0] == "CONSTRUCTED ws edit"
    plan = front.withdraw_plan(w, ws, "gap", v_edit)
    assert plan["would"] == "withdrawn" and plan["head_falls_back_to"] is None, plan
    res = front.withdraw(w, ws, pg.tokens[ws], "gap", v_edit, "CONSTRUCTED: retract the edit", "a", "s")
    assert res["outcome"] == "withdrawn" and res["head"] is None, res
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity_id = %s", (ws, gid))[0] == 0
    assert pg.one("SELECT state FROM litkb.gap_versions WHERE version_id = %s", (v_main,))[0] == "promoted"
    assert pg.one(view, (ws, gid))[0] == "CONSTRUCTED main v1"
    # main moves on (another workstream's promotion, modelled owner-level): this workstream's view follows it
    pg.one("SELECT litkb._write_version('fact', 'gap', %s, NULL, %s, %s, 'CONSTRUCTED main v2', %s, 'constructed', "
           "'constructed')", (gid, v_main, pg.jsonb({"question": "CONSTRUCTED main v2", "gap_state": "open"}), other))
    assert pg.one("SELECT question FROM litkb.main_gaps WHERE gap_id = %s", (gid,))[0] == "CONSTRUCTED main v2"
    assert pg.one(view, (ws, gid))[0] == "CONSTRUCTED main v2"


@pg_only
def test_withdraw_refuses_a_prepared_head(pg):
    """A version `promote prepare` has taken is `prepared`, and it is STILL its workstream's head: the head rule
    alone would let the proposer withdraw it out from under the promotion its report describes. The state rule
    refuses it (55000) and nothing moves."""
    from litkb.admit import front

    ws = pg.ws()
    w = pg.session("litkb_writer")
    gid, v1 = pg.one("SELECT entity_id, version_id FROM litkb.write_proposal('gap', NULL, %s, NULL, %s, NULL, %s, "
                     "%s, 'a', 's')", (pg.jsonb({"slug": f"constructed-prepared-{uuid.uuid4().hex[:8]}"}),
                                       pg.jsonb({"question": "CONSTRUCTED prepared", "gap_state": "open"}), ws,
                                       pg.tokens[ws]), conn=w)
    pg.one("SELECT litkb.promote_prepare(%s, %s, NULL)", (ws, "b" * 40), conn=pg.session("litkb_promoter"))
    assert pg.one("SELECT state FROM litkb.gap_versions WHERE version_id = %s", (v1,))[0] == "prepared"
    with pytest.raises(pg.errors.ObjectNotInPrerequisiteState, match="not proposed"):
        front.withdraw(w, ws, pg.tokens[ws], "gap", v1, "CONSTRUCTED: pull it from the promotion", "a", "s")
    assert pg.one("SELECT state FROM litkb.gap_versions WHERE version_id = %s", (v1,))[0] == "prepared"
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity_id = %s", (ws, gid))[0] == 1


@pg_only
def test_decide_files_refuses_when_the_proposers_workstream_is_closed(pg):
    """D3 for the lone-file verb as for approve_admission: a proposal whose workstream was abandoned is not
    decided (22023), and nothing moves."""
    from litkb.admit import front

    ws, ws2 = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    work_id, title = _registry_work(pg, ws)
    v = _attach(pg, w, ws, work_id, B2._file_json(title, source_route="browser", tag="d3"))["file_version"]
    w.execute("SELECT litkb.abandon_workstream(%s, %s)", (ws, pg.tokens[ws]))
    with pytest.raises(pg.errors.InvalidParameterValue, match="not open"):
        front.decide_files(w, ws2, pg.tokens[ws2], "approve", [v], None, "reviewer", "second-session")
    assert pg.one("SELECT state FROM litkb.file_versions WHERE version_id = %s", (v,))[0] == "proposed"
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work_id,))[0] == 0


@pg_only
def test_every_verb_records_its_labels_without_invisible_characters(pg):
    """The D7 rule at every new call site (the per-call-site rule, qc/instruments/litkb_p2_mutations.py B2
    rows): refuse, withdraw, decide_files and offer_file store the labels with invisible characters removed, and
    the two dry runs compare them that way — so `' sess\\u200b '` can never pass for another session, nor be
    recorded as one."""
    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p, session="sess-plan")
    assert front.refuse_plan(w, prop["admission_id"], " sess-plan​ ")["would"] == "refused"
    assert front.refuse_plan(w, prop["admission_id"], "another")["would"] == "declined"
    front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "CONSTRUCTED", "agent​", " refuser​ ")
    assert _decisions(pg, admission_id=prop["admission_id"])[0][2] == "refuser"

    work_id, title = _registry_work(pg, ws_p)
    fj = B2._file_json(title, source_route="browser", tag="labels")
    fj["pdf_metadata"] = {"Creator": "Acrobat 3.0 Capture Plug-in\x00\x00"}
    off = front.offer_file(w, ws_p, pg.tokens[ws_p], work_id, fj, "op​", " op-labels​ ")
    assert off["outcome"] == "attached", off
    row = pg.one("SELECT agent, session_id, pdf_metadata->>'Creator' FROM litkb.file_versions WHERE version_id = %s",
                 (off["file_version"],))
    assert row == ("op", "op-labels", "Acrobat 3.0 Capture Plug-in"), row
    assert [p["would"] for p in front.decide_plan(w, [off["file_version"]], "​op-labels ")] == ["refused"]
    front.decide_files(w, ws_r, pg.tokens[ws_r], "approve", [off["file_version"]], None, "rev​", " decider​ ")
    assert _decisions(pg, version_id=off["file_version"])[0][2] == "decider"

    work2, title2 = _registry_work(pg, ws_p)
    v2 = _attach(pg, w, ws_p, work2, B2._file_json(title2, source_route="browser", tag="wd-labels"))["file_version"]
    front.withdraw(w, ws_p, pg.tokens[ws_p], "file", v2, "CONSTRUCTED", "op​", " withdrawer​ ")
    assert _decisions(pg, version_id=v2)[0][2] == "withdrawer"


class _NoConn:
    """A connection the CLI opens and closes and never queries (every front call below is stubbed)."""

    def close(self):
        pass


@pytest.mark.parametrize("argv", [["refuse", "ADM", "--reason", "r"],
                                  ["withdraw", "VER", "--reason", "r"],
                                  ["approve-files", "VER"],
                                  ["refuse-files", "VER", "--reason", "r"]])
def test_the_new_verbs_normalise_their_labels_at_the_cli(tmp_path, monkeypatch, argv):
    """`litkb refuse / withdraw / approve-files / refuse-files --session 'sess<ZWSP>'` reach the front already
    normalised (commands._labels, the CLI's call site of norm_label; qc/test_litkb_p2.py pins the older verbs)."""
    from litkb import commands
    from litkb.admit import front

    (tmp_path / ".litkb-workstream").write_text(json.dumps({"workstream_id": str(uuid.uuid4()), "token": "t" * 40}),
                                                encoding="utf-8")
    seen = {}

    def grab(*a, **kw):
        seen["labels"] = (a[-2], a[-1])
        return {"outcome": "stub"}

    monkeypatch.setattr(front, "refuse", grab)
    monkeypatch.setattr(front, "withdraw", grab)
    monkeypatch.setattr(front, "decide_files", grab)
    monkeypatch.setattr(front, "decide_plan", lambda conn, ids, session: [{"version_id": i, "would": "decide"}
                                                                          for i in ids])
    ids = {"ADM": str(uuid.uuid4()), "VER": str(uuid.uuid4())}
    commands.main(["--dir", str(tmp_path), "--agent", "agent​", "--session", "sess​",
                   *[ids.get(x, x) for x in argv]], connect=lambda db: _NoConn())
    assert seen["labels"] == ("agent", "sess"), seen


# ── the decision log ─────────────────────────────────────────────────────────────────────────

@pg_only
def test_the_decision_log_is_append_only(pg):
    """No agent role holds INSERT/UPDATE/DELETE/TRUNCATE on it (the writer's UPDATE is refused 42501), and the
    trigger refuses UPDATE, DELETE and TRUNCATE to the OWNER too: a decision is corrected by a new one."""
    from litkb.admit import front

    ws_p, ws_r = pg.ws(), pg.ws()
    w = pg.session("litkb_writer")
    prop = _proposal(pg, w, ws_p)
    did = front.refuse(w, ws_r, pg.tokens[ws_r], prop["admission_id"], "CONSTRUCTED: a row to rewrite", "r",
                       "second-session")["decision_id"]
    assert B2.decision_log_unguarded(pg.conn, {}) == 0
    with pytest.raises(pg.errors.InsufficientPrivilege):
        w.execute("UPDATE litkb.adjudications SET reason = 'rewritten' WHERE id = %s", (did,))
    with pytest.raises(pg.errors.InsufficientPrivilege):
        w.execute("DELETE FROM litkb.adjudications WHERE id = %s", (did,))
    for stmt in ("UPDATE litkb.adjudications SET reason = 'rewritten' WHERE id = %s",
                 "DELETE FROM litkb.adjudications WHERE id = %s"):
        with pytest.raises(pg.errors.InsufficientPrivilege, match="append-only"):
            pg.conn.execute(stmt, (did,))
    with pytest.raises(pg.errors.InsufficientPrivilege, match="append-only"):
        pg.conn.execute("TRUNCATE litkb.adjudications")
    assert pg.one("SELECT reason FROM litkb.adjudications WHERE id = %s", (did,))[0] == "CONSTRUCTED: a row to rewrite"


# ── the refused-duplicate landing (hunt's URL path) ──────────────────────────────────────────

def _hunt_env(tmp_path, monkeypatch, conn):
    from litkb import workstream
    from litkb.db import connect as c

    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws_id = workstream.open_workstream(conn, f"b2-hunt-{uuid.uuid4().hex[:8]}", "test", "b2 hunt tests",
                                       directory=wt)
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt), "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "b2-hunt", "LITKB_SESSION": f"b2-hunt-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    return {"conn": conn, "root": root, "wt": wt, "ws_id": str(ws_id), "db": c.DB_TEST, "tmp": tmp_path}


class _NoNet:
    """A registry client that opens no socket (qc/test_litkb_hunt.py's shape)."""
    base = ""

    def get(self, url, *a, **kw):
        return 404, {}, b""


def _hunt_pdf(env, data, *, title, author, year):
    from litkb import hunt as H
    from litkb.acquire.store import Store

    url = f"https://constructed.invalid/{uuid.uuid4().hex}/paper.pdf"
    store = Store(root=env["root"], index_cache=env["tmp"] / "index.json")
    res = H.hunt(url, ref_scheme="url", db=env["db"], worktree=env["wt"], agent="b2-hunt", session="b2-hunt-session",
                 reader_role="litkb_test", writer_role="litkb_test", store=store,
                 derived=str(env["tmp"] / "derived"), fetch=lambda u, timeout=180: (200, data), extract=False,
                 title=title, author=author, year=year, registry_client=_NoNet())
    return url, res


def _seed_main_work(conn, ws, title, authors, year, *, sha=None):
    """A work in MAIN (a fact, the P8/hunt suites' seeding shape), optionally holding a file with `sha`."""
    from psycopg.types.json import Jsonb

    key = f"Seeded_{year}_b2-landing-{uuid.uuid4().hex[:8]}"
    wid = conn.execute("SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, "
                       "'b2-seed', 'b2-seed')",
                       (Jsonb({"key": key}), Jsonb({"type": "report", "title": title, "authors": authors,
                                                    "year": year}), ws)).fetchone()[0]
    if sha:
        conn.execute("SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, "
                     "'b2-seed', 'b2-seed')",
                     (Jsonb({"sha256": sha}), Jsonb({"work_id": str(wid), "rel_path": f"Validation/{key}.pdf",
                                                     "status": "active"}), ws))
    return str(wid)


def _assert_owned(env, sha):
    """Never left unowned: a `files` row or a `quarantine_payloads` row holds the landed bytes."""
    conn = env["conn"]
    held = conn.execute("SELECT count(*) FROM litkb.files WHERE sha256 = %s", (sha,)).fetchone()[0]
    q = conn.execute("SELECT count(*) FROM litkb.quarantine_payloads WHERE sha256 = %s", (sha,)).fetchone()[0]
    assert held + q >= 1, "the landing is owned by no files row and no quarantine row"
    assert B2.unowned_landing_paths(conn, env["root"]) == []


@pg_only
def test_unowned_landings_counts_only_a_filed_pdf_no_row_holds(pg, tmp_path):
    """The REPORTED counter's positive (auditor-B2 F3; on live it reads 3). CONSTRUCTED bytes under a tmp
    literature root's `_litkb_staging/filed/`: a PDF whose sha256 a `files` row holds, one a
    `quarantine_payloads` row holds, one NO row holds (in a sub-folder, `.PDF`), and a non-PDF no row holds.
    Only the third is unowned — by its bytes, whatever its name — and the counter reads the root from the
    manifest."""
    from litkb import quarantine as Q

    ws = pg.ws()
    w = pg.session("litkb_writer")
    root = tmp_path / "Literture"
    filed = root / B2.FILED_DIR
    (filed / "sub").mkdir(parents=True)

    def constructed_pdf(name):
        data = b"%PDF-1.4\n% CONSTRUCTED unowned-landing bytes " + uuid.uuid4().hex.encode()
        (filed / name).write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    held_sha = constructed_pdf("CONSTRUCTED-held.pdf")
    q_sha = constructed_pdf("CONSTRUCTED-quarantined.pdf")
    constructed_pdf("sub/CONSTRUCTED-unowned.PDF")
    (filed / "CONSTRUCTED-notes.txt").write_bytes(b"CONSTRUCTED: not a PDF, never counted")
    assert len(B2.unowned_landing_paths(pg.conn, root)) == 3          # before any row holds them
    _seed_main_work(pg.conn, ws, f"CONSTRUCTED holder of filed bytes {uuid.uuid4().hex}", [], 2001, sha=held_sha)
    Q.record(w, ws, pg.tokens[ws], rel_path=f"_quarantine/CONSTRUCTED__binding-failed__{q_sha[:12]}.pdf",
             sha256=q_sha, nbytes=60, reason="binding-failed", origin="hunt-url")
    assert B2.unowned_landing_paths(pg.conn, root) == ["_litkb_staging/filed/sub/CONSTRUCTED-unowned.PDF"]
    assert B2.unowned_landings(pg.conn, {"literature_root": str(root)}) == 1


@pg_only
def test_a_refused_duplicate_landing_is_offered_to_its_work_and_becomes_a_proposal(tmp_path, monkeypatch,
                                                                                    litkb_pg_base):
    """A PDF URL whose claim is title-near a work ALREADY in main: its own admission is refused
    `duplicate-review` (unchanged: E06's lesson), and the file is offered to that work through check 3 — it binds,
    so it becomes a PROPOSED file version of that work (`source_route='web'`) with its acquisition event, the
    hunt still ends `refused/admission-refused`, and a second session's approval puts it in main."""
    P2M._need_pdftotext()
    from litkb.admit import front

    _psycopg, conn, _ran = litkb_pg_base
    env = _hunt_env(tmp_path, monkeypatch, conn)
    title = f"A Seeded Survey of Constructed Canopy Landings {uuid.uuid4().hex[:8]}"
    wid = _seed_main_work(conn, env["ws_id"], title, [{"family": "Doe", "given": "J."}], 2020)
    data = P2M.paper_pdf(title, "Doe")
    _url, res = _hunt_pdf(env, data, title=title, author="Doe", year=2020)
    assert (res["state"], res["reason"]) == ("refused", "admission-refused"), res
    assert res["admission"]["outcome"] == "duplicate-review", res
    off = res["offered"]
    assert off["outcome"] == "proposed" and off["work_id"] == wid and off["state"] == "proposed", off
    sha = hashlib.sha256(data).hexdigest()
    row = conn.execute("SELECT fv.state, fv.source_route, fv.work_id::text, fv.rel_path FROM litkb.file_versions fv "
                       "JOIN litkb.files f ON f.id = fv.file_id WHERE f.sha256 = %s", (sha,)).fetchone()
    assert row[:3] == ("proposed", "web", wid), row
    assert (env["root"] / row[3]).is_file() and res["landed"] == row[3], (row, res)
    assert res["acquisition_event"]["ok"] is True, res
    assert conn.execute("SELECT count(*) FROM litkb.acquisition_attempts WHERE work_id = %s AND route = 'hunt-url' "
                        "AND status = 'ok' AND detail->>'sha256' = %s", (wid, sha)).fetchone()[0] == 1
    _assert_owned(env, sha)
    ws2, tok2 = conn.execute("SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/b2', NULL, 'b2', NULL)",
                             (f"b2-approver-{uuid.uuid4().hex[:8]}",)).fetchone()
    front.decide_files(conn, ws2, tok2, "approve", [off["file_version"]], None, "reviewer", "second-session")
    assert conn.execute("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (wid,)).fetchone()[0] == 1


@pg_only
def test_a_refused_duplicate_landing_that_does_not_bind_is_quarantined_with_a_row(tmp_path, monkeypatch,
                                                                                  litkb_pg_base):
    """The same landing, offered to a work whose FIRST AUTHOR the page does not carry: check 3 refuses it, so it
    is moved to _quarantine/ under `binding-failed` with a `.reason.json` and a `quarantine_payloads` row (origin
    `hunt-url`, the work named) — never left in filed/ with no row, the state 187's PDF is in on live."""
    P2M._need_pdftotext()
    _psycopg, conn, _ran = litkb_pg_base
    env = _hunt_env(tmp_path, monkeypatch, conn)
    title = f"A Seeded Survey of Constructed Canopy Refusals {uuid.uuid4().hex[:8]}"
    wid = _seed_main_work(conn, env["ws_id"], title, [{"family": "Quimby", "given": "Q."}], 2020)
    data = P2M.paper_pdf(title, "Doe")
    _url, res = _hunt_pdf(env, data, title=title, author="Doe", year=2020)
    assert (res["state"], res["reason"]) == ("refused", "admission-refused"), res
    off = res["offered"]
    assert off["outcome"] == "quarantined" and off["reason"] == "binding-failed", off
    assert off["offers"][0]["work_id"] == wid and off["offers"][0]["outcome"] == "refused", off
    assert "landed" not in res and res["quarantined"] == off["quarantined"], res
    q = env["root"] / off["quarantined"]
    assert q.is_file() and q.with_suffix(".reason.json").is_file()
    # the landing's own sidecar (the admission, the offers, the source) — never a generic one (auditor-B2 F7)
    side = json.loads(q.with_suffix(".reason.json").read_text(encoding="utf-8"))
    assert side.get("reason") == "binding-failed" and side.get("route") == "hunt-url", side
    assert side.get("offers") and side["offers"][0]["work_id"] == wid and side.get("source_url") == _url, side
    sha = hashlib.sha256(data).hexdigest()
    qr = conn.execute("SELECT reason, origin, work_id::text FROM litkb.quarantine_payloads WHERE sha256 = %s",
                      (sha,)).fetchone()
    assert qr == ("binding-failed", "hunt-url", wid), qr
    assert not list((env["root"] / "_litkb_staging" / "filed").glob("*.pdf"))
    assert conn.execute("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (wid,)).fetchone()[0] == 0
    _assert_owned(env, sha)


@pg_only
def test_a_landing_whose_bytes_are_held_is_quarantined_duplicate_held(tmp_path, monkeypatch, litkb_pg_base):
    """A landing whose BYTES another work already holds (admission refused at `file_duplicate`): nothing to
    offer; the stray copy in filed/ is quarantined `duplicate-held` with its row."""
    P2M._need_pdftotext()
    _psycopg, conn, _ran = litkb_pg_base
    env = _hunt_env(tmp_path, monkeypatch, conn)
    title = f"A Constructed Paper Whose Bytes Are Held {uuid.uuid4().hex[:8]}"
    data = P2M.paper_pdf(title, "Doe")
    sha = hashlib.sha256(data).hexdigest()
    _seed_main_work(conn, env["ws_id"], f"An unrelated seeded holder {uuid.uuid4().hex}", [], 1990, sha=sha)
    _url, res = _hunt_pdf(env, data, title=title, author="Doe", year=2020)
    assert res["admission"].get("refused_at") == "file_duplicate", res
    off = res["offered"]
    assert off["outcome"] == "quarantined" and off["reason"] == "duplicate-held" and off["offers"] == [], off
    assert conn.execute("SELECT reason, origin FROM litkb.quarantine_payloads WHERE rel_path = %s",
                        (off["quarantined"],)).fetchone() == ("duplicate-held", "hunt-url")
    side = json.loads((env["root"] / off["quarantined"]).with_suffix(".reason.json").read_text(encoding="utf-8"))
    assert side.get("reason") == "duplicate-held" and side.get("offers") == [], side
    assert side.get("admission", {}).get("refused_at") == "file_duplicate", side
    assert not list((env["root"] / "_litkb_staging" / "filed").glob("*.pdf"))


def test_a_refused_duplicate_landing_is_offered_to_the_most_similar_work_first(tmp_path, monkeypatch):
    """The offer ORDER (auditor-B2 round 2 F7, N5). Check 2 lists the title-near works in its own order; the
    landing offers the file to the MOST similar first, and the first work that binds it takes it. CONSTRUCTED:
    every database call is stubbed (no connection), and both works would take the file — so the order alone
    decides which work gets it, and the more similar one must, even when check 2 listed it second."""
    from litkb import hunt as H
    from litkb.acquire import run as R
    from litkb.admit import front

    low, high = str(uuid.uuid4()), str(uuid.uuid4())
    tried = []

    def offer(conn, ws, token, wid, fjson, agent, session):
        tried.append(wid)
        return {"outcome": "attached", "file_id": "CONSTRUCTED-file", "file_version": "CONSTRUCTED-version",
                "state": "proposed", "binding": {"verdict": "bound"}}

    monkeypatch.setattr(R, "work_record", lambda conn, work_id: {"title": f"CONSTRUCTED work {work_id}",
                                                                 "first_author": "Doe", "key": f"K-{work_id[:8]}"})
    monkeypatch.setattr(front, "file_evidence", lambda *a, **kw: {"binding": {"verdict": "bound"}})
    monkeypatch.setattr(front, "offer_file", offer)
    monkeypatch.setattr(H, "_record_acquisition_event", lambda *a, **kw: None)

    class _Store:
        root = tmp_path

        def rel(self, p):
            return "_litkb_staging/filed/CONSTRUCTED.pdf"

    res = {"outcome": "duplicate-review", "matches": [{"work_id": low, "similarity": 0.71},
                                                      {"work_id": high, "similarity": 0.93}]}
    out = H._offer_refused_landing(None, "CONSTRUCTED-ws", "CONSTRUCTED-token", res, tmp_path / "x.pdf",
                                   tmp_path / "x.txt", {}, [], sha="0" * 64, data=b"%PDF-1.4 CONSTRUCTED",
                                   store=_Store(), stem="x", url="https://constructed.invalid/x.pdf", http_status=200,
                                   agent="a", session="s")
    assert out["outcome"] == "proposed" and out["work_id"] == high, out
    assert tried == [high], tried


@pytest.mark.parametrize("offers, reason", [
    ([{"outcome": "refused", "binding": "binding-pending"}], "binding-pending"),
    ([{"outcome": "refused", "binding": "binding-pending"}, {"outcome": "refused", "binding": "binding-failed"}],
     "binding-failed"),
    ([{"outcome": "refused", "binding": "binding-failed"}], "binding-failed"),
    ([{"outcome": "refused", "binding": "binding-failed"}, {"outcome": "duplicate-file"}], "duplicate-held"),
    ([{"outcome": "probe-error"}], "probe-error"),
    ([{"outcome": "not-in-main"}], "duplicate-held"),
    ([], "duplicate-held"),
])
def test_the_landing_quarantine_reason_is_what_the_offers_said(offers, reason):
    """The quarantine REASON a landing no work took (auditor-B2 round 2 F7, N10): check 3 left every offer
    PENDING (no text layer — OCR can still bind it) -> `binding-pending`, never `binding-failed`; any refusal on
    the evidence -> `binding-failed`; the bytes already held -> `duplicate-held`; an unreadable page count ->
    `probe-error`; no work in main to offer to -> `duplicate-held` (documented in SCHEMAS)."""
    from litkb import hunt as H

    assert H._offer_reason(offers) == reason


@pg_only
def test_187s_real_filed_pdf_is_never_left_unowned(tmp_path, monkeypatch, litkb_pg_base):
    """REAL ROW: 187's protocol PDF (7,623,037 bytes, sha 94d8fbed…) COPIED from its live filed/ path into a
    tmp literature root, and re-served through the URL path with the URL leg's own inputs (the registry title,
    `Tyukavina`, 2025) against 187's registry record seeded in main (DataCite's corporate creator, 2025). Live,
    this landing was refused `duplicate-review` and left in filed/ with no row. Asserted: the admission is still
    refused `duplicate-review` and the landing is OWNED afterwards (a proposal or a quarantine row). NOT asserted:
    which of the two — whether check 3 binds 187's page against a corporate first author is the measurement the
    report records and the referee scores (CLAUDE.md §3.4c: the builder does not score its own design)."""
    P2M._need_pdftotext()
    if not REAL_187.is_file():
        pytest.skip(f"187's filed PDF is not on this machine ({REAL_187})")
    data = REAL_187.read_bytes()
    assert hashlib.sha256(data).hexdigest() == REAL_187_SHA
    _psycopg, conn, _ran = litkb_pg_base
    env = _hunt_env(tmp_path, monkeypatch, conn)
    title = "Land Cover and Change Map Accuracy Assessment and Area Estimation Good Practices Protocol"
    authors = [{"family": "Land Product Validation Subgroup (Working Group on Calibration and Validation",
                "given": " Committee on Earth Observation Satellites)"}]
    already = conn.execute("SELECT f.id FROM litkb.files f WHERE f.sha256 = %s", (REAL_187_SHA,)).fetchone()
    if already:
        pytest.skip("187's bytes are already held in this session's database (a rerun inside one session)")
    wid = _seed_main_work(conn, env["ws_id"], title, authors, 2025)
    _url, res = _hunt_pdf(env, data, title=title, author="Tyukavina", year=2025)
    assert (res["state"], res["reason"]) == ("refused", "admission-refused"), res
    assert res["admission"]["outcome"] == "duplicate-review", res
    assert res["offered"]["offers"][0]["work_id"] == wid, res["offered"]
    assert res["offered"]["outcome"] in ("proposed", "quarantined"), res["offered"]
    _assert_owned(env, REAL_187_SHA)
    (tmp_path / "187_outcome.json").write_text(json.dumps(res["offered"], default=str, indent=1), encoding="utf-8")


# ── mirrors, signatures, tokens ──────────────────────────────────────────────────────────────

@pg_only
def test_the_python_mirrors_equal_the_database(pg):
    """One home each: the gate's route list is `litkb._proposal_source_routes()` (front.PROPOSAL_SOURCE_ROUTES
    mirrors it); the operator routes the counters read are `litkb_acceptance.MANUAL_FILE_ROUTES`."""
    from litkb.admit import front

    assert tuple(pg.one("SELECT litkb._proposal_source_routes()")[0]) == front.PROPOSAL_SOURCE_ROUTES
    acc = _load("_litkb_acceptance_for_b2", SCRIPTS / "qc" / "instruments" / "litkb_acceptance.py")
    assert tuple(acc.MANUAL_FILE_ROUTES) == B2.OPERATOR_ROUTES
    assert set(B2.OPERATOR_ROUTES) <= set(front.PROPOSAL_SOURCE_ROUTES)


_TOKEN_FNS = {"refuse_admission": 6, "withdraw_version": 7, "decide_file_versions": 7}


@pg_only
@pytest.mark.parametrize("case", ["missing", "another_workstreams_token"])
@pytest.mark.parametrize("fn", sorted(_TOKEN_FNS))
def test_adjudication_functions_have_one_signature_and_need_their_token(pg, fn, case):
    """The token-function rule (qc/test_litkb_p1.py::test_token_functions_have_exactly_one_signature, for the
    three new ones): one signature carrying `p_ws_token text`; a missing or foreign token is refused 42501
    before anything is read, and nothing is written."""
    sigs = pg.conn.execute("SELECT pg_get_function_identity_arguments(p.oid) FROM pg_proc p WHERE p.pronamespace = "
                           "'litkb'::regnamespace AND p.proname = %s", (fn,)).fetchall()
    assert len(sigs) == 1 and "p_ws_token text" in sigs[0][0], sigs
    ws = pg.ws()
    w = pg.session("litkb_writer")
    token = None if case == "missing" else pg.tokens[pg.ws()]
    before = pg.one("SELECT count(*) FROM litkb.adjudications")[0]
    args = {"refuse_admission": (ws, token, uuid.uuid4(), "r", "a", "s"),
            "withdraw_version": (ws, token, "file", uuid.uuid4(), "r", "a", "s"),
            "decide_file_versions": (ws, token, "approve", [uuid.uuid4()], "r", "a", "s")}[fn]
    with pytest.raises(pg.errors.InsufficientPrivilege, match="token refused"):
        pg.one(f"SELECT litkb.{fn}({', '.join(['%s'] * _TOKEN_FNS[fn])})", args, conn=w)
    assert pg.one("SELECT count(*) FROM litkb.adjudications")[0] == before


# ── the fires and the promote proof ──────────────────────────────────────────────────────────

@pg_only
@pytest.mark.parametrize("name", sorted(B2.FIRES))
def test_every_b2_fire_fires(pg, name, tmp_path):
    """Each fire's two arms on this worker database: control within its bound, known-bad outside it. The arms
    scope their counters to their own rows (`scope_workstream_ids` / `run_workstream_ids`), so a shared test
    database cannot move them; every in-transaction mutation is rolled back before the arm returns."""
    f = B2.FIRES[name]
    control = f["run"](pg.conn, "control", tmp_path / "control")
    bad = f["run"](pg.conn, "known_bad", tmp_path / "known_bad")
    assert B2.within(control, f["bound"]), (name, "control", control)
    assert not B2.within(bad, f["bound"]), (name, "known_bad", bad)
    # the rolled-back mutations left the real guards in place
    assert pg.one("SELECT to_regprocedure('litkb.refuse_admission(uuid, text, uuid, text, text, text)') IS NOT NULL")[0]
    assert pg.one("SELECT count(*) FROM pg_constraint WHERE conname = 'adjudications_second_session_decides'")[0] == 1
    assert B2.decision_log_unguarded(pg.conn, {}) == 0


@pg_only
def test_the_constructed_promote_proof(pg, tmp_path):
    """D6, on the worker database only (no CONSTRUCTED row enters `litkb`): the proposing session's approval of
    its own CONSTRUCTED chain is refused by BOTH guards; `promote prepare` prepares the gap chain, holds the
    admission's fact chains, and WRITES the report; `promote commit` is refused by `verify_merge` because main
    has not merged the branch."""
    ws = pg.ws()
    out = B2.constructed_promote_proof(pg.conn.info.dbname, ws, pg.tokens[ws], tmp_path)
    assert set(out["refusals"]) == {"python", "database", "commit"}, out["refusals"]
    assert "own session" in out["refusals"]["python"]
    assert "admissions_second_session_signs_off" in out["refusals"]["database"]
    assert "not reachable from main" in out["refusals"]["commit"]
    counts = pg.one("SELECT counts, state FROM litkb.promotions WHERE id = %s", (out["promotion_id"],))
    assert counts[1] == "prepared" and counts[0]["prepared"] == 1 and counts[0]["held"] == 3, counts
    text = Path(out["report"]).read_text(encoding="utf-8")
    assert out["promotion_id"] in text and "## Held" in text and "admission:" in text
    shutil.rmtree(tmp_path, ignore_errors=True)


@pg_only
def test_withdrawing_an_edit_of_a_prepared_version_falls_back_to_it(pg):
    """auditor-B2 round 3 F1 (integrator-w2): a version `promote prepare` has taken is still this workstream's own
    chain (0019's `_ws_chains` walks `proposed` AND `prepared`). Prepare v1, propose an edit v2 on it, withdraw v2:
    the head falls back to v1 — it stays in the workstream's view and its promotion's chain — instead of being
    removed and orphaning the prepared version (the auditor measured it in no view, no chain and no head, its
    promotion unable to commit or be re-prepared). The dry run names the same fallback."""
    from litkb.admit import front

    ws = pg.ws()
    w = pg.session("litkb_writer")
    gid, v1 = pg.one("SELECT entity_id, version_id FROM litkb.write_proposal('gap', NULL, %s, NULL, %s, NULL, %s, "
                     "%s, 'a', 's')", (pg.jsonb({"slug": f"constructed-prepared-edit-{uuid.uuid4().hex[:8]}"}),
                                       pg.jsonb({"question": "CONSTRUCTED prepared v1", "gap_state": "open"}), ws,
                                       pg.tokens[ws]), conn=w)
    pg.one("SELECT litkb.promote_prepare(%s, %s, NULL)", (ws, "b" * 40), conn=pg.session("litkb_promoter"))
    _g, v2 = pg.one("SELECT entity_id, version_id FROM litkb.write_proposal('gap', %s, NULL, %s, %s, "
                    "'CONSTRUCTED edit of the prepared version', %s, %s, 'a', 's')",
                    (gid, v1, pg.jsonb({"question": "CONSTRUCTED edit v2", "gap_state": "open"}), ws,
                     pg.tokens[ws]), conn=w)
    plan = front.withdraw_plan(w, ws, "gap", v2)
    assert plan["would"] == "withdrawn" and plan["head_falls_back_to"] == str(v1), plan
    res = front.withdraw(w, ws, pg.tokens[ws], "gap", v2, "CONSTRUCTED: retract the edit", "a", "s")
    assert res["outcome"] == "withdrawn" and res["head"] == str(v1), res
    assert pg.one("SELECT version_id FROM litkb.ws_heads WHERE workstream_id = %s AND entity_id = %s",
                  (ws, gid))[0] == v1
    assert pg.one("SELECT state FROM litkb.gap_versions WHERE version_id = %s", (v1,))[0] == "prepared"
    assert pg.one("SELECT question FROM litkb.ws_gaps WHERE view_workstream_id = %s AND gap_id = %s",
                  (ws, gid))[0] == "CONSTRUCTED prepared v1"


@pg_only
def test_withdrawing_an_edit_of_this_workstreams_promoted_version_removes_the_head(pg):
    """auditor-B2 round 3 F5 (integrator-w2): the fallback's STATE conjunct. A base that is this workstream's own
    but PROMOTED (an owner-level fact written in the same workstream: CONSTRUCTED, the P8/hunt seeding shape) is
    main's version, not this workstream's to hold: withdrawing an edit of it REMOVES the head (the dry run: no
    fallback). Only the workstream conjunct was tested before; this holds the state one."""
    from litkb.admit import front

    ws = pg.ws()
    w = pg.session("litkb_writer")
    gid, v_main = pg.one("SELECT entity_id, version_id FROM litkb._write_version('fact', 'gap', NULL, %s, NULL, %s, "
                         "NULL, %s, 'constructed', 'constructed')",
                         (pg.jsonb({"slug": f"constructed-own-promoted-{uuid.uuid4().hex[:8]}"}),
                          pg.jsonb({"question": "CONSTRUCTED own promoted", "gap_state": "open"}), ws))
    assert tuple(map(str, pg.one("SELECT state, workstream_id FROM litkb.gap_versions WHERE version_id = %s",
                                 (v_main,)))) == ("promoted", str(ws))
    _g, v_edit = pg.one("SELECT entity_id, version_id FROM litkb.write_proposal('gap', %s, NULL, %s, %s, "
                        "'CONSTRUCTED edit', %s, %s, 'a', 's')",
                        (gid, v_main, pg.jsonb({"question": "CONSTRUCTED own edit", "gap_state": "open"}), ws,
                         pg.tokens[ws]), conn=w)
    assert front.withdraw_plan(w, ws, "gap", v_edit)["head_falls_back_to"] is None
    res = front.withdraw(w, ws, pg.tokens[ws], "gap", v_edit, "CONSTRUCTED: retract the edit", "a", "s")
    assert res["outcome"] == "withdrawn" and res["head"] is None, res
    assert pg.one("SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity_id = %s", (ws, gid))[0] == 0

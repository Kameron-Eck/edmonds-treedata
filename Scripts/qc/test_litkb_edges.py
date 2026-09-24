r"""The edge-case register, its driver and the `edges` grader (litkb S3).

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w10 py -3.12 -m pytest qc/test_litkb_edges.py

WHAT THE KNOWN-BADS ARE. `edges` exists because the scout's counter could not tell a hunt that
ended in the RIGHT named state from one that merely ended in SOME named state. So every guard here
is shown to fire on an input that a membership check would wave through:

  (c1) an expectation swapped for another VALID pair          -> state_or_reason_mismatches=1
  (c2) a hunt that RAISES                                     -> tracebacks=1, and the row is still written
  (c3) a register edited after the freeze (sha256 differs)    -> refused BEFORE anything is graded
  (c4) `--replay` pointed at the live database                -> refused
  (c5) a CSV missing one manifest row                         -> skipped=1

Rows c1, c3, c4 and c5 need no database at all: the grader reads through injected `rows` and an
injected CSV path, the way `check_first_work` reads through `DB_READS`. The replay rows that DO
need Postgres carry `requires_litkb_pg` and skip loudly (qc/conftest.py's terminal summary).
"""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

SCRIPTS = Path(__file__).resolve().parent.parent
FIXTURE = SCRIPTS / "qc" / "fixtures" / "litkb_hunt_edge_cases.json"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def E():
    return _load("litkb_edge_run", "qc/instruments/litkb_edge_run.py")


@pytest.fixture(scope="module")
def A():
    return _load("litkb_acceptance", "qc/instruments/litkb_acceptance.py")


@pytest.fixture(scope="module")
def register():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ── the register itself ────────────────────────────────────────────────────────────────────

def test_the_register_vocabulary_is_hunts_own(register):
    """The fixture copies `litkb.hunt`'s vocabulary so a reader of the register never has to open
    the module — and the copy is PINNED here, because a copy nobody checks is the second home
    CLAUDE.md §3.3 forbids. A state or a reason added to hunt.py without this file fails here."""
    from litkb import hunt as H

    voc = register["vocabulary"]
    assert list(H.STATES) == voc["states"], (H.STATES, voc["states"])
    for state in H.STATES:
        assert list(H.REASONS[state]) == voc["reasons"][state], state
    assert voc["reasons"]["crashed"] == [], "crashed's reason is a SHAPE, never a list"


def test_every_expected_pair_is_a_pair_hunt_can_emit(E, register):
    """An expectation outside the vocabulary is a register row that can never pass, and it would
    look exactly like a defect in the code."""
    from litkb import hunt as H

    for row in E.rows_of(register):
        if not E.is_hunt_row(row):
            continue
        for replay in (False, True):
            state, reason = E.expected_of(row, replay=replay)
            assert state in H.STATES, (row["id"], state)
            assert H.reason_ok(state, reason), (row["id"], state, reason)


def test_every_row_cites_where_it_came_from(E, register):
    """`Every row is a REAL row from the surveys (cite its source in the row)` — the brief's rule,
    enforced. A register row with no provenance is an invented edge case, which is the one thing
    an adjudicated table must not contain."""
    for row in E.rows_of(register):
        if E.is_held(row):
            ev = (row.get("held_for_ruling") or {})
            assert ev.get("question"), row["id"]
            assert ev.get("evidence"), row["id"]
        else:
            assert (row.get("source") or "").strip(), row["id"]
            assert (row.get("adjudication") or {}).get("builder"), row["id"]


def test_no_two_rows_admit_the_same_identifier_in_one_replay(E, register):
    """`identifiers_active_scheme_value` is UNIQUE and the replay resets the database ONCE for the
    whole run, so two rows that seed or admit the same identifier make the second unrunnable. It
    happened twice while this register was being written (E08/E17 and E03/E15, both measured), and
    the symptom was a psycopg UniqueViolation out of the driver rather than a graded row."""
    claimed = {}
    for row in E.rows_of(register):
        if not E.is_hunt_row(row):
            continue
        rp = row.get("replay") or {}
        refs = []
        seed = rp.get("seed")
        if seed:
            refs += [(seed["scheme"], seed["value"])]
            refs += [(i["scheme"], i["value"]) for i in (seed.get("also") or [])]
        if (rp.get("registry") or {}).get("kind") == "record":
            refs.append((row.get("ref_scheme") or "doi", row["ref"]))
        for ref in refs:
            assert ref not in claimed, f"{row['id']} and {claimed[ref]} both write {ref}"
            claimed[ref] = row["id"]


# ── the mode rule ──────────────────────────────────────────────────────────────────────────

def test_waits_on_migration_is_measured_and_never_written_in_the_fixture(E, register):
    """`waits-on-migration` is a fact about a DATABASE at an INSTANT. 0028 was unapplied when S3
    opened and applied by 00:07 the same night; a row that hard-coded the wait would still be
    waiting. So no row may declare it, and the same row must resolve both ways as the tip moves."""
    rows = E.rows_of(register)
    for row in rows:
        assert (row.get("live") or {}).get("mode") != "waits-on-migration", row["id"]
    need = [r for r in rows if (r.get("live") or {}).get("needs_migration")]
    assert need, "no row exercises the migration rule"
    for row in need:
        n = int(row["live"]["needs_migration"])
        assert E.resolve_mode(row, n) == "execute", row["id"]
        assert E.resolve_mode(row, n - 1) == "waits-on-migration", row["id"]
        # an UNREADABLE tip waits: running a row whose route CHECK may be absent produces
        # `acquisition-event-failed` and grades as a mismatch nobody caused
        assert E.resolve_mode(row, None) == "waits-on-migration", row["id"]


# ── the grader, without a database ─────────────────────────────────────────────────────────

def _row(rid, cls="c", ref="10.1/x", scheme="doi", state="held", reason="no-spend", **live):
    return {"id": rid, "class": cls, "ref": ref, "ref_scheme": scheme,
            "source": "a test", "adjudication": {"builder": "a test"},
            "expected": {"state": state, "reason": reason},
            "live": {"mode": live.pop("mode", "execute"), "why": "a test", "spend": False, **live}}


def _csv(E, path, rows):
    path = Path(path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(E.EDGE_CSV_COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in E.EDGE_CSV_COLUMNS})
    return str(path)


def _observed(rid, state, reason, **over):
    return {"row_id": rid, "observed_state": state, "observed_reason": reason,
            "ok": "true", "traceback": "0", "report": "{}", **over}


def _manifest(tmp_path, rows, csv_path, **over):
    m = {"kind": "litkb-edges", "db": "litkb", "db_migration_tip": 28,
         "fixture": str(FIXTURE), "fixture_sha256": "deadbeef",
         "rows": [{"id": r["id"], "mode": r["live"]["mode"]} for r in rows],
         "run_csv": csv_path, "replay_csv": csv_path}
    m.update(over)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return m, str(p)


def test_a_clean_run_counts_every_row_and_exits_zero(A, E, tmp_path):
    rows = [_row("X1"), _row("X2", state="extracted", reason="fresh")]
    path = _csv(E, tmp_path / "run.csv",
                [_observed("X1", "held", "no-spend"), _observed("X2", "extracted", "fresh")])
    manifest, _p = _manifest(tmp_path, rows, path)
    counters, offences = A.check_edges(manifest, rows=rows, csv_path=path)
    assert counters == {"executed": 2, "skipped": 0, "state_or_reason_mismatches": 0,
                        "tracebacks": 0, "held_for_ruling": 0, "waits_on_migration": 0}, counters
    assert offences == []
    assert A.edges_ok(counters, A.edges_manifest_rows(manifest, counters))


def test_kill_an_expectation_swapped_for_another_valid_pair_is_a_mismatch(A, E, tmp_path):
    """KNOWN-BAD (c1). `extracted/already-extracted` is a PERFECTLY VALID pair — it is what E01
    and E02 answer — so a checker that only asked whether the observed state was in the closed
    vocabulary would pass this run. The register says E11 is `refused/admission-refused` and the
    grader compares the PAIR, which is the whole difference between this command and `scout`."""
    row = _row("E11", ref="10.3390/rs17112050", state="refused", reason="admission-refused")
    path = _csv(E, tmp_path / "run.csv", [_observed("E11", "refused", "admission-refused")])
    manifest, _p = _manifest(tmp_path, [row], path)

    clean, _o = A.check_edges(manifest, rows=[row], csv_path=path)
    assert clean["state_or_reason_mismatches"] == 0, clean

    mutated = json.loads(json.dumps(row))
    mutated["expected"] = {"state": "extracted", "reason": "already-extracted"}
    from litkb import hunt as H
    assert H.reason_ok(*mutated["expected"].values()), "the mutation must be a VALID pair"

    counters, offences = A.check_edges(manifest, rows=[mutated], csv_path=path)
    assert counters["state_or_reason_mismatches"] == 1, counters
    assert any("!= expected extracted/already-extracted" in o for o in offences), offences
    assert not A.edges_ok(counters, 1)


def test_kill_a_hunt_that_raises_is_a_traceback_row_and_the_row_is_still_written(A, E, tmp_path):
    """KNOWN-BAD (c2). `hunt` promises a named result for every reference — the whole of S3. A
    raise out of it is the defect, so the driver writes the row anyway (a dead run reports nothing
    about exactly the case that matters) and the grader refuses the run for it."""
    row = _row("X1")
    register = {"kind": "litkb-hunt-edge-cases", "rows": [row]}
    path = tmp_path / "run.csv"

    def _boom(**kw):
        raise RuntimeError("the hunt fell over\nand a second line nobody should read")

    n, resumed, written = E.run_execute(register, path, db="none", worktree=tmp_path,
                                        agent="t", session="t", db_tip=28, hunt=_boom,
                                        counter=lambda: 0)
    assert n == 1 and resumed == 0
    assert written[0]["traceback"] == "1" and written[0]["message"].startswith("RuntimeError:")
    assert "\n" not in written[0]["message"], written[0]["message"]
    assert path.is_file(), "the CSV was not written for a hunt that raised"

    manifest, _p = _manifest(tmp_path, [row], str(path))
    counters, offences = A.check_edges(manifest, rows=[row], csv_path=str(path))
    assert counters["tracebacks"] == 1 and counters["executed"] == 1, counters
    assert any("RAISED" in o for o in offences), offences
    assert not A.edges_ok(counters, 1)


def test_kill_a_register_edited_after_the_freeze_is_refused_before_anything_is_graded(
        A, E, tmp_path):
    """KNOWN-BAD (c3), and it is MUTATION-PROOFING the grader itself: the register is what the run
    is graded against, so a register edited after the freeze grades a different question. The
    refusal is a SystemExit raised before a single row is read."""
    path = _csv(E, tmp_path / "run.csv", [])
    manifest, _p = _manifest(tmp_path, [], path, fixture_sha256="0" * 64)
    with pytest.raises(SystemExit) as e:
        A.check_edges(manifest, csv_path=path)
    assert "sha256" in str(e.value) and "Nothing was graded" in str(e.value), str(e.value)

    # and the same manifest with the file's REAL hash grades normally
    good, _p2 = _manifest(tmp_path, [], path, fixture_sha256=A._register_sha256(FIXTURE))
    counters, _off = A.check_edges(good, csv_path=path)
    # the grade ran over the REAL register: with an empty run CSV every executable row is
    # `skipped` and every held row is counted — either proves the file was read. It used to
    # assert held_for_ruling >= 1, which broke the day the last ruling landed (2026-09-21).
    assert counters["skipped"] + counters["held_for_ruling"] >= 1, counters


def test_kill_the_register_hash_is_content_not_bytes_crlf_passes_one_edit_refuses(
        A, E, tmp_path):
    """KNOWN-BAD (c3b), the guard's blind spot found 2026-09-21: the register is `* text=auto`,
    so the same commit is CRLF on a Windows checkout and LF on Linux. The byte hash refused S3's
    own frozen manifest on a fresh checkout with NOTHING edited. The guard hashes CONTENT: a CRLF
    rewrite of the register hashes the same and grades; a single edited expectation hashes
    differently and is refused before anything is graded."""
    # Independent of what git handed THIS checkout: the freeze happens on an LF copy (a Linux
    # checkout), the grade on a CRLF copy (a Windows one). The first version of this test froze
    # on the working copy and passed under mutation to a byte hash, because the working copy was
    # already CRLF and so was byte-identical to the "CRLF copy".
    lf = FIXTURE.read_bytes().replace(b"\r\n", b"\n")
    assert b"\r\n" not in lf
    lf_path = tmp_path / "register_lf.json"
    lf_path.write_bytes(lf)
    frozen = A._register_sha256(lf_path)
    path = _csv(E, tmp_path / "run.csv", [])

    crlf = tmp_path / "register_crlf.json"
    crlf.write_bytes(lf.replace(b"\n", b"\r\n"))
    assert crlf.read_bytes() != lf, "the CRLF copy must differ as bytes"
    assert A._sha256(crlf) != A._sha256(lf_path), "the byte hashes must differ"
    assert A._register_sha256(crlf) == frozen, "a newline rewrite is not an edit"
    m, _p = _manifest(tmp_path, [], path, fixture=str(crlf), fixture_sha256=frozen)
    counters, _off = A.check_edges(m, csv_path=path)
    # the grade ran over the REAL register: with an empty run CSV every executable row is
    # `skipped` and every held row is counted — either proves the file was read. It used to
    # assert held_for_ruling >= 1, which broke the day the last ruling landed (2026-09-21).
    assert counters["skipped"] + counters["held_for_ruling"] >= 1, counters

    edited = tmp_path / "register_edited.json"
    reg = json.loads(lf.decode("utf-8"))
    target = next(r for r in reg["rows"] if r.get("expected"))
    target["expected"]["state"] = "extracted"
    target["expected"]["reason"] = "already-extracted"
    edited.write_bytes(json.dumps(reg, indent=1).encode("utf-8"))
    assert A._register_sha256(edited) != frozen, "one edited expectation must change the hash"
    m2, _p2 = _manifest(tmp_path, [], path, fixture=str(edited), fixture_sha256=frozen)
    with pytest.raises(SystemExit) as e:
        A.check_edges(m2, csv_path=path)
    assert "Nothing was graded" in str(e.value), str(e.value)


def test_kill_a_replay_pointed_at_the_live_database_is_refused(E, tmp_path):
    """KNOWN-BAD (c4). `--replay` RESETS and MIGRATES its database. Pointed at `litkb` it would
    destroy the knowledge base, so the name is refused by the driver before a connection is
    opened — not by a convention, and not by the operator remembering."""
    register = {"kind": "litkb-hunt-edge-cases", "rows": [_row("X1")]}
    with pytest.raises(SystemExit) as e:
        E.run_replay(register, tmp_path / "replay.csv", db="litkb", tmp=str(tmp_path))
    assert "refuses 'litkb'" in str(e.value), str(e.value)
    with pytest.raises(SystemExit):
        E.run_replay(register, tmp_path / "replay.csv", db="LITKB", tmp=str(tmp_path))
    assert not (tmp_path / "replay.csv").exists(), "a refused replay still wrote a CSV"


def test_kill_a_csv_missing_one_manifest_row_is_skipped_not_silence(A, E, tmp_path):
    """KNOWN-BAD (c5). A run that hunted nineteen of twenty rows and got them all right has not
    graded the register. `skipped` counts the absence and `executed == manifest_rows` refuses it."""
    rows = [_row("X1"), _row("X2", state="extracted", reason="fresh")]
    path = _csv(E, tmp_path / "run.csv", [_observed("X1", "held", "no-spend")])
    manifest, _p = _manifest(tmp_path, rows, path)
    counters, offences = A.check_edges(manifest, rows=rows, csv_path=path)
    assert counters["skipped"] == 1 and counters["executed"] == 1, counters
    assert any("no row in the driver CSV" in o for o in offences), offences
    assert not A.edges_ok(counters, A.edges_manifest_rows(manifest, counters))


def test_an_assert_the_grader_cannot_evaluate_is_named_never_silently_passed(A, E, tmp_path):
    """A gate that has never fired is not known to work (CLAUDE.md §3.4c), and an `asserts` key no
    column can answer is exactly that. It is reported as a mismatch rather than ignored."""
    row = _row("X1")
    row["asserts"] = {"snapshot": True}
    path = _csv(E, tmp_path / "run.csv", [_observed("X1", "held", "no-spend")])
    manifest, _p = _manifest(tmp_path, [row], path)
    counters, offences = A.check_edges(manifest, rows=[row], csv_path=path)
    assert counters["state_or_reason_mismatches"] == 1, counters
    assert any("not checkable from the edge-run CSV" in o for o in offences), offences


def test_replay_asserts_are_read_in_replay_mode_and_the_live_ones_otherwise(A, E, tmp_path):
    """`replay.asserts` is the twin of `replay.expected` (S3 live run, E06): a held work in main
    makes the page a `duplicate-review` refusal live, while the empty replay database makes it a
    proposal with blocks. Each mode grades its own asserts; the grader reading the wrong set is
    exactly the mismatch this test plants — and with the override removed, it fails."""
    row = _row("X1")
    row["expected"] = {"state": "refused", "reason": "admission-refused"}
    row["asserts"] = {"admission_state": "duplicate-review"}
    row["replay"] = {"expected": {"state": "extracted", "reason": "fresh"},
                     "asserts": {"admission_state": "proposed"}}
    live = _observed("X1", "refused", "admission-refused", ok="false",
                     report=json.dumps({"admission_state": "duplicate-review"}))
    path = _csv(E, tmp_path / "run.csv", [live])
    manifest, _p = _manifest(tmp_path, [row], path)
    counters, offences = A.check_edges(manifest, rows=[row], csv_path=path)
    assert counters["state_or_reason_mismatches"] == 0, offences

    rep = _observed("X1", "extracted", "fresh",
                    report=json.dumps({"admission_state": "proposed", "in_main": False}))
    rpath = _csv(E, tmp_path / "replay.csv", [rep])
    manifest, _p = _manifest(tmp_path, [row], path, replay_csv=rpath)
    counters, offences = A.check_edges(manifest, rows=[row], csv_path=rpath, replay=True)
    assert counters["state_or_reason_mismatches"] == 0, offences
    # and the live asserts against the replay's facts would NOT pass — the override is load-bearing
    assert A._asserts_offences(row, rep) != [], "the live asserts must disagree with the replay row"


def test_a_held_for_ruling_row_is_counted_and_never_executed(A, E, tmp_path):
    """D2: a row whose expected state needs Kam is NOT a manifest row. It is counted so the
    register's own coverage is visible, and it is never hunted."""
    held = {"id": "E20", "class": "book", "ref": "10.1201/9781315374321", "ref_scheme": "doi",
            "held_for_ruling": {"question": "what state?", "evidence": "one book, no file"},
            "live": {"mode": "held-for-ruling", "why": "the ruling", "spend": False}}
    path = _csv(E, tmp_path / "run.csv", [])
    manifest, _p = _manifest(tmp_path, [], path)
    counters, offences = A.check_edges(manifest, rows=[held], csv_path=path)
    assert counters == {"executed": 0, "skipped": 0, "state_or_reason_mismatches": 0,
                        "tracebacks": 0, "held_for_ruling": 1, "waits_on_migration": 0}, counters
    assert offences == []
    assert E.resolve_mode(held, 28) == "held-for-ruling"


def test_a_not_a_hunt_row_is_excluded_from_executed(A, E, tmp_path):
    """E26 records a SCOUT-side tool fault (`search_unpaywall` empty for gold-OA DOIs). The hunt
    vocabulary does not cover it, so it is kept and excluded rather than forced into a state."""
    row = _row("E26", mode="not-a-hunt")
    path = _csv(E, tmp_path / "run.csv", [])
    manifest, _p = _manifest(tmp_path, [], path)
    counters, offences = A.check_edges(manifest, rows=[row], csv_path=path)
    assert counters["executed"] == 0 and counters["skipped"] == 0, counters
    assert offences == []


def test_a_waiting_row_is_skipped_live_and_executed_in_replay(A, E, tmp_path):
    """The replay's worker database is migrated by the driver, so the migration the live run waits
    on is present there by construction — a waiting row is proven in `--replay` (D2)."""
    row = _row("X1", needs_migration=99)
    path = _csv(E, tmp_path / "run.csv", [_observed("X1", "held", "no-spend")])
    manifest, _p = _manifest(tmp_path, [row], path)
    live, _o = A.check_edges(manifest, rows=[row], csv_path=path)
    assert live["waits_on_migration"] == 1 and live["executed"] == 0, live
    replay, _o2 = A.check_edges(manifest, rows=[row], csv_path=path, replay=True)
    assert replay["waits_on_migration"] == 0 and replay["executed"] == 1, replay


def test_the_replay_expectation_may_override_and_both_are_recorded(E, register):
    """A freshly migrated database cannot hold a precondition only the live corpus has (E05's
    answer turns on a PROPOSED work admitted months ago). Such a row carries `replay.expected`,
    which overrides for the replay ALONE — both are in the register, and both are graded.

    A row the live pass RECORDED is the opposite case (S4.5 run-plan §4; decision D10's rule): its replay
    replays that recording, so its `replay.expected` IS the live pair — the run CSV's — and an override that
    differed would be a register expecting the replay to contradict the recording it replays."""
    over = [r for r in E.rows_of(register) if (r.get("replay") or {}).get("expected")]
    assert over, "no row exercises the override"
    assert [r for r in over if not E.graded_by_hardening_replay(r)], "no row exercises a DIFFERING override"
    for row in over:
        if E.graded_by_hardening_replay(row):
            assert E.expected_of(row) == E.expected_of(row, replay=True), row["id"]
        else:
            assert E.expected_of(row) != E.expected_of(row, replay=True), row["id"]
        assert (row["replay"].get("_why") or "").strip(), row["id"]


# ── the rows the live pass recorded: graded by `hardening --replay` only (S4.5 run-plan §8 Q3) ─────────────

#: The register rows the ladder-1 live pass RECORDED, converted from the synthetic acquirer by the register-editor
#: from the run CSV (run-plan §4). E16 stays on the synthetic acquirer: it is replay-only and no live recording of
#: it can exist (run-plan §8 Q2). Pinned HERE, not derived from `litkb_edge_run.graded_by_hardening_replay`: a
#: predicate that widened or narrowed would move a derived set with it.
RECORDED_BY_LADDER_1 = {"E03", "E07", "E13", "E20"}


class _UntouchableConn:
    """A connection a row named `graded-by-hardening-replay` never reaches: the replay decides that before any
    database work, so ANY use of this object means the row went on to be hunted."""

    def __getattr__(self, name):
        raise AssertionError(f"the replay touched the database ({name}): the row was hunted, not named")


def _no_hunt(**kw):
    raise AssertionError(f"hunt() was called for {kw.get('ref')}: the row was hunted, not named")


def _routes(row):
    return (row.get("replay") or {}).get("routes") or {}


def test_the_register_holds_exactly_the_rows_ladder_1_recorded(E, register):
    """The conversion, read off the register's own structure: the four rows are `ladder` rows with no cassette of
    their own, carry the routes the live pass reached, and carry no pending marker; E16 alone stays on the stub."""
    rows = E.rows_of(register)
    ladder_no_cassette = {r["id"] for r in rows if _routes(r).get("kind") == "ladder" and not _routes(r).get("cassette")}
    assert ladder_no_cassette == RECORDED_BY_LADDER_1, ladder_no_cassette
    assert {r["id"] for r in rows if E.graded_by_hardening_replay(r)} == RECORDED_BY_LADDER_1
    assert {r["id"] for r in rows if _routes(r).get("kind") == "acquirer"} == {"E16"}
    for r in rows:
        if r["id"] in RECORDED_BY_LADDER_1:
            assert not _routes(r).get("pending_recording"), r["id"]
            assert _routes(r).get("routes"), r["id"]
            assert (r["replay"].get("registry") or {}).get("title"), r["id"]
            assert (r["live"].get("superseded_expected") or {}).get("state"), r["id"]
            assert (r["adjudication"].get("orchestrator_2026-09-24") or {}).get("run_row"), r["id"]


def test_a_recorded_row_replayed_with_no_run_index_is_named_and_never_hunted(E, register, tmp_path):
    """Q3's outcome, on the four REAL rows: with no run index handed to the replay, each is written
    `graded-by-hardening-replay` with an EMPTY observed pair — no database touched, no hunt called, no
    synthetic acquirer — and its message says who grades it."""
    by_id = {r["id"]: r for r in E.rows_of(register)}
    for rid in sorted(RECORDED_BY_LADDER_1):
        out = E.replay_row(by_id[rid], conn=_UntouchableConn(), db="litkb_test_unused", tmp=str(tmp_path),
                           hunt=_no_hunt, defer_recorded=True)
        assert out["acquirer"] == E.GRADED_BY_HARDENING_REPLAY, out
        assert (out["traceback"], out["observed_state"], out["observed_reason"], out["attempt_statuses"],
                out["seconds"]) == ("0", "", "", "", ""), out
        assert "hardening --replay" in out["message"], out


def test_only_the_edges_flag_defers_and_only_a_recorded_row_with_no_index(E, register, tmp_path):
    """Every case here must go on to be HUNTED — the untouchable connection says so: the gate's call (no flag),
    a replay handed the run's index, the stub row E16, and a CONSTRUCTED copy of E13 carrying a cassette of its
    own (a fixture index, the way the constructed register's rows do)."""
    by_id = {r["id"]: r for r in E.rows_of(register)}
    own = json.loads(json.dumps(by_id["E13"]))
    own["id"] = "E13-CONSTRUCTED-OWN-CASSETTE"
    own["replay"]["routes"]["cassette"] = "litkb_cassettes/constructed_scihub_403/index.jsonl"
    cases = [("the gate's call, no flag", by_id["E13"], None, False),
             ("the run's index handed over", by_id["E13"], object(), True),
             ("a synthetic-acquirer row", by_id["E16"], None, True),
             ("a ladder row with its own cassette", own, None, True)]
    for what, row, cassette, flag in cases:
        with pytest.raises(AssertionError, match="the row was hunted, not named"):
            E.replay_row(row, conn=_UntouchableConn(), db="litkb_test_unused", tmp=str(tmp_path / row["id"]),
                         hunt=_no_hunt, cassette=cassette, defer_recorded=flag)
            pytest.fail(f"{what}: {row['id']} was named graded-by-hardening-replay")


def test_a_named_row_that_reaches_the_grader_is_a_mismatch_never_a_pass(A, E, register, tmp_path):
    """FAIL-CLOSED at the grader: the gate never defers, but a CSV row carrying the word that reached the
    `edges` grader anyway (what `hardening --replay` grades with) compares an EMPTY observed pair with the
    register's and is refused — the word is not an answer."""
    row = {r["id"]: r for r in E.rows_of(register)}["E07"]
    out = E.replay_row(row, conn=_UntouchableConn(), db="litkb_test_unused", tmp=str(tmp_path), hunt=_no_hunt,
                       defer_recorded=True)
    path = _csv(E, tmp_path / "replay.csv", [out])
    manifest, _p = _manifest(tmp_path, [row], path)
    counters, offences = A.check_edges(manifest, rows=[row], csv_path=path, replay=True)
    assert counters["executed"] == 1 and counters["state_or_reason_mismatches"] == 1, counters
    assert any(o.startswith("E07: observed /") for o in offences), offences
    assert not A.edges_ok(counters, 1)


def test_the_named_rows_are_printed_in_the_terminal_summary(E):
    """Never silent: the note the register replay leaves on the config is written by the suite's terminal
    summary (qc/conftest.py, loaded by path — qc is not a package), and nothing is written without one."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_conftest_named_outcomes", Path(__file__).with_name("conftest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class _Reporter:
        def __init__(self, notes):
            self.stats, self.lines = {}, []
            self.config = type("Cfg", (), {})()
            if notes is not None:
                self.config._litkb_named_outcomes = notes

        def write_line(self, line):
            self.lines.append(line)

    note = f"litkb edges: {E.GRADED_BY_HARDENING_REPLAY}=4 (E03 E07 E13 E20)"
    rep = _Reporter([note])
    mod.pytest_terminal_summary(rep)
    assert rep.lines == [note], rep.lines
    quiet = _Reporter(None)
    mod.pytest_terminal_summary(quiet)
    assert quiet.lines == [], quiet.lines


# ── the driver's resume rule ───────────────────────────────────────────────────────────────

def test_a_row_already_in_the_csv_is_never_hunted_again_unless_redone(E, tmp_path):
    """The scout driver's rule, and for its reason: a live edge run spends on real routes and
    takes minutes per row, so a driver that redid its work after a crash would be unaffordable at
    the moment it was already going badly."""
    register = {"kind": "litkb-hunt-edge-cases", "rows": [_row("X1"), _row("X2")]}
    calls = []

    def _hunt(**kw):
        calls.append(kw["ref"])
        return {"ok": True, "state": "held", "reason": "no-spend", "in_main": True}

    path = tmp_path / "run.csv"
    E.run_execute(register, path, db="none", worktree=tmp_path, agent="t", session="t",
                  db_tip=28, hunt=_hunt, counter=lambda: 0)
    assert len(calls) == 2
    n, resumed, _rows = E.run_execute(register, path, db="none", worktree=tmp_path, agent="t",
                                      session="t", db_tip=28, hunt=_hunt, counter=lambda: 0)
    assert (n, resumed, len(calls)) == (0, 2, 2)
    n2, _r, _rows2 = E.run_execute(register, path, db="none", worktree=tmp_path, agent="t",
                                   session="t", db_tip=28, hunt=_hunt, counter=lambda: 0,
                                   redo=["X2"])
    assert (n2, len(calls)) == (1, 3), calls


def test_a_replay_handed_a_connection_neither_locks_nor_resets(E, tmp_path):
    """THE DEADLOCK, pinned. `litkb_pg_base` holds `pg_advisory_lock(0x6C6B7473)` for the whole
    pytest session and a Postgres advisory lock is session-scoped, so a replay that opened its own
    connection and asked for the same lock waited forever — measured 2026-09-21, a combined run of
    the acceptance and edges modules produced no output at all and had to be killed. Handed the
    fixture's connection, the replay must not lock and must not reset: it is the fixture that did
    both, and a reset mid-session would delete every other litkb module's seeded rows.

    No mutation row targets this one. Breaking it does not make a test FAIL, it makes the whole
    suite HANG, and a harness row whose failure mode is an unbounded wait cannot be run."""
    seen = []

    class _Conn:
        def execute(self, sql, params=None):
            seen.append(str(sql))
            raise AssertionError("the replay touched the connection it was handed")

    E.run_replay({"kind": "litkb-hunt-edge-cases", "rows": []}, tmp_path / "replay.csv",
                 db="litkb_test_w10", tmp=str(tmp_path), conn=_Conn())
    assert seen == [], seen


# ── the replay, end to end on the worker database ──────────────────────────────────────────

@pg_only
def test_the_register_replays_on_a_worker_database(A, E, register, tmp_path, litkb_pg_base, request):
    """EVERY non-held row of the real register, re-run against its own stubs on LITKB_TEST_DB.

    This is the proof the register is adjudicated rather than asserted: each row's expected pair
    is produced by the real `litkb.hunt.hunt` with the world replaced at the seams the hunt suite
    already uses. Every row must match — E06 included, since builder B's HTML branch landed.

    EXCEPT THE ROWS THE LIVE PASS RECORDED (S4.5 run-plan §8 Q3). E03 E07 E13 E20 replay the ladder-1
    recorded index, which is not in the repository, so here they are written `graded-by-hardening-replay`
    (`defer_recorded=True`) — NAMED in the CSV, COUNTED against `RECORDED_BY_LADDER_1`, printed in the
    terminal summary, never hunted and never put on the synthetic acquirer — and `hardening --replay`, which
    is handed the index, grades them (fail-closed there: with no index they are its named tracebacks).

    THE FIXTURE'S CONNECTION IS PASSED IN, and it has to be: `litkb_pg_base` holds the suite's
    advisory lock for the whole pytest session, so a replay that opened its own connection would
    wait on it forever (`run_replay`'s docstring records the measurement). The fixture has already
    reset and migrated this database before the replay.

    AND THE DATABASE IS RESET AGAIN AFTERWARDS. The replay admits real works — E06 admits the
    Crossref article under its plain title — into the session-shared worker database, and
    `litkb._title_duplicates` is GLOBAL over every work_versions row (any workstream, any state,
    0.70). `qc/test_litkb_hunt.py`'s page hunts admit the same page under a suffixed title and
    went `duplicate-review` → `refused/admission-refused` whenever this module ran first (the
    S3 phase-2 audit: 4 red with `edges,hunt`, 85 passed reversed). A test whose result depends
    on collection order is not a test; the reset puts the database back the way the fixture
    hands it to everyone else."""
    import os

    db = os.environ.get("LITKB_TEST_DB") or "litkb_test"
    if db == "litkb":
        pytest.skip("LITKB_TEST_DB is the live database")
    _psycopg, conn, _ran = litkb_pg_base
    out = tmp_path / "replay.csv"
    try:
        E.run_replay(register, out, db=db, tmp=str(tmp_path), conn=conn, defer_recorded=True)
    finally:
        from litkb.db import migrate

        migrate.reset(conn)
        migrate.apply(conn)
    written = E.existing_rows(out)
    hunt_rows = [r for r in E.rows_of(register) if E.is_hunt_row(r)]

    # Q3: the recorded rows — named, counted, printed; never hunted, never on the stub
    named = sorted(r["row_id"] for r in written if r["acquirer"] == E.GRADED_BY_HARDENING_REPLAY)
    assert set(named) == RECORDED_BY_LADDER_1, named
    for r in written:
        if r["row_id"] in RECORDED_BY_LADDER_1:
            assert (r["traceback"], r["observed_state"], r["attempt_statuses"]) == ("0", "", ""), r
            assert "hardening --replay" in r["message"], r
    stubs = {r["row_id"] for r in written if r["acquirer"] == "stub"}
    assert stubs == {r["id"] for r in hunt_rows if _routes(r).get("kind") == "acquirer"} == {"E16"}, stubs
    request.config._litkb_named_outcomes = list(getattr(request.config, "_litkb_named_outcomes", None) or []) + [
        f"litkb edges: {E.GRADED_BY_HARDENING_REPLAY}={len(named)} ({' '.join(named)}) <- recorded by the "
        "ladder-1 live pass: NOT replayed here; `hardening --replay` grades them against the recorded index"]

    graded = [r for r in E.rows_of(register) if r["id"] not in RECORDED_BY_LADDER_1]
    manifest = {"kind": "litkb-edges", "db": db, "db_migration_tip": 28,
                "fixture": str(FIXTURE), "fixture_sha256": A._register_sha256(FIXTURE),
                "rows": [{"id": r["id"], "mode": E.resolve_mode(r, 28)} for r in graded],
                "run_csv": str(out), "replay_csv": str(out)}
    counters, offences = A.check_edges(manifest, rows=graded, csv_path=str(out), replay=True)
    assert counters["tracebacks"] == 0, offences
    assert counters["skipped"] == 0, offences
    assert counters["state_or_reason_mismatches"] == 0, offences
    assert offences == [], offences
    assert counters["executed"] == len(hunt_rows) - len(named), counters
    assert counters["executed"] + len(named) == len(written), (counters, len(written))

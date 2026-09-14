"""litkb P1 — show each kill FIRE (CLAUDE.md 3.4c: a kill must be shown to fire on a known-bad
input before it counts as a gate).

For every mutation below: remove or weaken ONE guard in the real source (or in the cluster's
role grants), run the kill test that should catch it, record whether it FAILED, and restore
the guard. Source files are restored byte-for-byte and verified by sha256; cluster changes are
reverted in a finally block and the confinement re-checked. Before and after the mutations the
unmutated kill tests are run and must pass, so a "fired" result cannot be a broken baseline.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_p1_mutations.py

Needs the litkb server and psql on the machine (the postgres superuser via pgpass, -w) for the
two cluster mutations. Prints one row per mutation; exit 0 only if every mutation fired and
both baselines passed.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
MIG = "pipeline/litkb/db/migrations"
TEST = "qc/test_litkb_p1.py"
PSQL = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"

MUTATIONS = [
    dict(id="M1", kill="writer UPDATE on a version table is refused",
         test="test_kill_writer_cannot_update_or_delete_version_rows[use_versions]",
         kind="replace", file=f"{MIG}/0006_grants.sql",
         old="-- end of grants\n",
         new="GRANT UPDATE, DELETE ON litkb.use_versions TO litkb_writer;\n-- end of grants\n",
         what="grant UPDATE, DELETE on use_versions to litkb_writer"),
    # M2a/M2b target 0007 since the referee fixes: 0007 REPLACES _write_version, so a mutation
    # of the 0003 body would be dead code and report DID NOT FIRE.
    dict(id="M2a", kill="second writer on the same base refused (fact table)",
         test="test_kill_fact_second_writer_on_same_base_is_refused",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old=" AND current_version_id IS NOT DISTINCT FROM $3', t.ident)",
         new="', t.ident)",
         what="drop the base predicate from the fact pointer UPDATE"),
    dict(id="M2b", kill="second writer on the same base refused (proposal)",
         test="test_kill_proposal_second_writer_on_same_base_is_refused",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="\n         AND h.version_id = p_based_on;",
         new=";",
         what="drop the base predicate from the ws_heads UPDATE"),
    dict(id="M3", kill="client quote_verified=true on a non-matching quote is stored false",
         test="test_kill_client_quote_verified_is_overwritten",
         kind="block", file=f"{MIG}/0003_write_functions.sql",
         marker="guard: quote_verified trigger",
         what="remove the CREATE TRIGGER that computes quote_verified"),
    dict(id="M4a", kill="litkb_test connecting to litkb is refused by the server",
         test="test_kill_test_role_is_refused_by_the_server_on_litkb",
         kind="cluster",
         apply="GRANT litkb_writer TO litkb_test WITH INHERIT TRUE;",
         revert="GRANT litkb_writer TO litkb_test WITH INHERIT FALSE;",
         what="membership in litkb_writer with INHERIT TRUE (inherits the writer's CONNECT)"),
    dict(id="M4b", kill="litkb_test connecting to litkb is refused by the server",
         test="test_kill_test_role_is_refused_by_the_server_on_litkb",
         kind="cluster",
         apply="GRANT CONNECT ON DATABASE litkb TO litkb_test;",
         revert="REVOKE CONNECT ON DATABASE litkb FROM litkb_test;",
         what="grant CONNECT on litkb to litkb_test directly"),
    dict(id="M5", kill="promote commit with a merge commit not reachable from main is refused",
         test="test_kill_promote_commit_refuses_merge_not_on_main",
         kind="block", file="pipeline/litkb/promote.py",
         marker="guard: merge commit reachable from main",
         what="remove the is-ancestor-of-main check in verify_merge"),
    dict(id="M6a", kill="a conflicting gap chain's dependent is not promoted (commit)",
         test="test_kill_conflicting_gap_chain_holds_its_dependent_at_commit",
         kind="block", file=f"{MIG}/0005_promotion.sql",
         marker="guard: dependency hold (commit)",
         what="remove the dependency hold in promote_commit"),
    dict(id="M6b", kill="a conflicting gap chain's dependent is not prepared (prepare)",
         test="test_kill_conflicting_gap_chain_holds_its_dependent_at_prepare",
         kind="block", file=f"{MIG}/0005_promotion.sql",
         marker="guard: dependency hold (prepare)",
         what="remove the dependency-hold fixpoint in promote_prepare"),
    dict(id="M7", kill="(runner) an edited applied migration is refused",
         test="test_gate_runner_refuses_an_edited_applied_migration",
         kind="block", file="pipeline/litkb/db/migrate.py",
         marker="guard: applied migrations are immutable",
         what="remove the applied-migration checksum comparison"),
    # ── fixes after the independent referee (Reports/LITKB_P1_REFEREE_2026-09-13.md) ──
    dict(id="D1", kill="(D-1) a write blocked behind promote_commit is refused",
         test="test_write_blocked_behind_promote_commit_is_refused",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="AND w.state = 'open' FOR SHARE;", new="AND w.state = 'open';",
         what="drop FOR SHARE on the workstream row in _write_version"),
    dict(id="D8", kill="(D-8) the losing concurrent writer gets 40001",
         test="test_losing_concurrent_writer_gets_40001[fact]",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="WHERE id = $1 FOR UPDATE', t.ident)", new="WHERE id = $1', t.ident)",
         what="drop the identity-row FOR UPDATE in _write_version"),
    dict(id="D5a", kill="(D-5) writer has no direct INSERT on use_evidence",
         test="test_writer_has_no_direct_evidence_insert",
         kind="block", file=f"{MIG}/0007_referee_fixes.sql",
         marker="guard: writer has no direct evidence INSERT",
         what="remove the REVOKE INSERT ON use_evidence FROM litkb_writer"),
    dict(id="D5b", kill="(D-5) add_evidence: workstream must be open",
         test="test_evidence_guard_workstream_must_be_open",
         kind="block", file=f"{MIG}/0007_referee_fixes.sql",
         marker="guard: evidence workstream open",
         what="remove the open-workstream check in add_evidence"),
    dict(id="D5c", kill="(D-5) add_evidence: version belongs to the named workstream",
         test="test_evidence_guard_version_must_belong_to_named_workstream",
         kind="block", file=f"{MIG}/0007_referee_fixes.sql",
         marker="guard: evidence version belongs to the workstream",
         what="remove the ownership check in add_evidence"),
    dict(id="D5d", kill="(D-5) add_evidence: version must be proposed",
         test="test_evidence_guard_version_must_be_proposed",
         kind="block", file=f"{MIG}/0007_referee_fixes.sql",
         marker="guard: evidence version is proposed",
         what="remove the proposed-state check in add_evidence"),
    dict(id="D5e", kill="(D-5) add_evidence: refused while a promotion is prepared",
         test="test_evidence_guard_refused_while_promotion_prepared",
         kind="block", file=f"{MIG}/0007_referee_fixes.sql",
         marker="guard: no evidence while a promotion is prepared",
         what="remove the prepared-promotion check in add_evidence"),
    dict(id="D5f", kill="(D-5) set_current_run refuses a failed run",
         test="test_referee_bypass_d5_failed_run_cannot_become_current",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="\n     AND r.status = 'ok';", new=";",
         what="drop the status = 'ok' predicate in set_current_run"),
    dict(id="D5g", kill="(D-5) set_current_run refuses another file's run (guard, before the FK)",
         test="test_set_current_run_refuses_foreign_or_null_run",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="\n     AND r.file_id = p_file", new="",
         what="drop the file_id predicate in set_current_run"),
    dict(id="R2", kill="(D-6) writer has no INSERT on version state columns",
         test="test_writer_cannot_insert_version_state_columns",
         kind="replace", file=f"{MIG}/0006_grants.sql",
         old="NOT IN ('state', ", new="NOT IN (",
         what="grant the writer column INSERT on state"),
    dict(id="R4", kill="(D-6) a first-head proposal must be based on main",
         test="test_first_head_proposal_must_be_based_on_main",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="\n       WHERE p_based_on IS NOT DISTINCT FROM v_main;", new=";",
         what="drop the base check on the first ws_heads insert"),
    dict(id="R6", kill="(D-6) quote_verified checks the offsets, not mere presence",
         test="test_quote_verified_checks_offsets_not_presence",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="substring(b.text FROM NEW.char_start + 1 FOR NEW.char_end - NEW.char_start) = NEW.quote",
         new="position(NEW.quote IN b.text) > 0",
         what="verify by 'quote anywhere in the block'"),
    dict(id="R7", kill="(D-6) a use whose gap is absent is held at prepare",
         test="test_use_whose_gap_is_absent_is_held_at_prepare",
         kind="replace", file=f"{MIG}/0005_promotion.sql",
         old=("        ELSIF NOT EXISTS (SELECT 1 FROM gaps g WHERE g.id = v_gap AND g.current_version_id IS NOT NULL) THEN\n"
              "          v_probs := v_probs || 'dependency: the gap is neither promoted nor in this promotion'::text;\n"),
         new="",
         what="drop the 'gap neither promoted nor in this promotion' problem"),
    dict(id="D7", kill="(D-7) char_end beyond the block text is refused",
         test="test_quote_char_end_beyond_text_is_refused",
         kind="block", file=f"{MIG}/0007_referee_fixes.sql",
         marker="guard: char_end within the block text",
         what="remove the char_end <= length(text) check"),
    # ── Kam's decisions on the referee findings (migration 0008) ──
    # K4a/K4b target 0009 since the second referee's fixes: 0009 REPLACES the 0008 constraint, so a
    # mutation of the 0008 text is dead code and reports DID NOT FIRE (measured).
    dict(id="K4a", kill="(D-4) another agent in the SAME session cannot approve (referee R1)",
         test="test_admission_approver_must_be_another_session[other_agent_same_session]",
         kind="replace", file=f"{MIG}/0009_referee2_fixes.sql",
         old="\n      AND btrim(approver_session, E' \\t\\n\\r\\f\\x0b') <> btrim(admitter_session, E' \\t\\n\\r\\f\\x0b')));",
         new="));",
         what="drop the approver session <> admitter session clause (live constraint, 0009)"),
    dict(id="K4b", kill="(D-4) the same agent name in ANOTHER session may approve (referee R1b)",
         test="test_admission_approver_must_be_another_session[same_agent_other_session]",
         kind="replace", file=f"{MIG}/0009_referee2_fixes.sql",
         old="<> btrim(admitter_session, E' \\t\\n\\r\\f\\x0b')));",
         new="<> btrim(admitter_session, E' \\t\\n\\r\\f\\x0b') AND approver_agent <> admitter_agent));",
         what="re-add the agent-name clause (the pre-0008 AND form, live constraint 0009)"),
    dict(id="K2a", kill="(D-2) a rebase onto a stale main version is refused",
         test="test_kill_rebase_onto_stale_main_is_refused",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: rebase onto main's current version",
         what="remove the onto = main's current compare-and-set"),
    dict(id="K2b", kill="(D-2) only a merged workstream's chains are rebased",
         test="test_rebase_guard_source_must_be_merged",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: rebase source is merged",
         what="remove the source-merged check"),
    dict(id="K2c", kill="(D-2) the rebase target must be open",
         test="test_rebase_guard_target_must_be_open",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: rebase target is open",
         what="remove the target-open check"),
    dict(id="K2d", kill="(D-2) no rebase into a workstream with a prepared promotion",
         test="test_rebase_guard_target_has_no_prepared_promotion",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: rebase target has no prepared promotion",
         what="remove the target prepared-promotion check"),
    dict(id="K2e", kill="(D-2) no rebase onto a target that already heads the entity",
         test="test_rebase_guard_target_has_no_head_for_the_entity",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: rebase target has no head for the entity",
         what="remove the target-head check (the ws_heads primary key is the second lock)"),
    dict(id="K2f", kill="(D-2) the held originals are marked rebased",
         test="test_held_chain_is_rebased_and_promotes",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: rebased originals are marked",
         what="remove the UPDATE that marks the old chain versions rebased"),
    dict(id="K2g", kill="(D-2) a rebased chain leaves the merged workstream's heads",
         test="test_held_chain_is_rebased_and_promotes",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: held chain leaves the source workstream",
         what="remove the DELETE of the source ws_heads row"),
    dict(id="K2h", kill="(D-2) evidence is carried onto the rebased version",
         test="test_rebase_carries_evidence",
         kind="block", file=f"{MIG}/0008_kam_referee_decisions.sql",
         marker="guard: rebase carries evidence",
         what="remove the evidence copy"),
    dict(id="K3a", kill="(D-3) the writer cannot call promote_rebase",
         test="test_agent_roles_cannot_call_promotion_functions[litkb_writer-promote_rebase]",
         kind="replace", file=f"{MIG}/0008_kam_referee_decisions.sql",
         old="-- end of 0008\n",
         new="GRANT EXECUTE ON FUNCTION litkb.promote_rebase(uuid, uuid, jsonb, text, text) TO litkb_writer;\n-- end of 0008\n",
         what="grant EXECUTE on promote_rebase to litkb_writer"),
    dict(id="K3b", kill="(D-3) the reader cannot call promote_commit",
         test="test_agent_roles_cannot_call_promotion_functions[litkb_reader-promote_commit]",
         kind="replace", file=f"{MIG}/0008_kam_referee_decisions.sql",
         old="-- end of 0008\n",
         new="GRANT EXECUTE ON FUNCTION litkb.promote_commit(uuid, text) TO litkb_reader;\n-- end of 0008\n",
         what="grant EXECUTE on promote_commit to litkb_reader"),
    dict(id="K3c", kill="(D-3) the shared connect() refuses the promoter login",
         test="test_connect_refuses_the_promoter_login",
         kind="block", file="pipeline/litkb/db/connect.py",
         marker="guard: promoter login only through the promote tool",
         what="remove the promoter refusal in connect()"),
    # ── the second referee's mutations (Reports/LITKB_P1_REFEREE2_2026-09-13.md), exact strings ──
    # X5/X6 (E-5, rebase evidence semantics) are NOT here: Kam is deciding them.
    dict(id="X1", kill="(E-6) add_evidence waits for a prepare in flight (FOR SHARE)",
         test="test_add_evidence_waits_for_a_prepare_in_flight_and_is_refused",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="ws.state = 'open' FOR SHARE;", new="ws.state = 'open';",
         what="drop FOR SHARE on the workstream row in add_evidence"),
    dict(id="X2", kill="(E-2) two rebases of one workstream make one copy (source FOR UPDATE)",
         test="test_concurrent_rebases_of_one_workstream_make_one_copy",
         kind="replace", file=f"{MIG}/0008_kam_referee_decisions.sql",
         old="w.id = p_source_ws AND w.state = 'merged' FOR UPDATE;",
         new="w.id = p_source_ws AND w.state = 'merged';",
         what="drop FOR UPDATE on the rebase source workstream row"),
    dict(id="X3", kill="(E-2) a rebase during a commit that moves main is refused (identity FOR UPDATE)",
         test="test_rebase_during_a_commit_that_moves_main_is_refused",
         kind="replace", file=f"{MIG}/0008_kam_referee_decisions.sql",
         old="'SELECT current_version_id FROM %s WHERE id = $1 FOR UPDATE'",
         new="'SELECT current_version_id FROM %s WHERE id = $1'",
         what="drop FOR UPDATE on the identity row in promote_rebase"),
    dict(id="X4a", kill="(E-3) onto missing a held chain is refused",
         test="test_rebase_onto_must_name_exactly_the_held_chains[missing_key]",
         kind="replace", file=f"{MIG}/0008_kam_referee_decisions.sql",
         old=("  IF (SELECT array_agg(j ORDER BY j) FROM jsonb_object_keys(p_onto) j) IS DISTINCT FROM v_keys THEN\n"
              "    RAISE EXCEPTION 'litkb: onto must name exactly the held chains %', v_keys USING ERRCODE = '22023';\n"
              "  END IF;\n"),
         new="",
         what="delete the onto-keys = held-chains check"),
    dict(id="X4b", kill="(E-3) onto naming an unheld chain is refused",
         test="test_rebase_onto_must_name_exactly_the_held_chains[extra_key]",
         kind="replace", file=f"{MIG}/0008_kam_referee_decisions.sql",
         old=("  IF (SELECT array_agg(j ORDER BY j) FROM jsonb_object_keys(p_onto) j) IS DISTINCT FROM v_keys THEN\n"
              "    RAISE EXCEPTION 'litkb: onto must name exactly the held chains %', v_keys USING ERRCODE = '22023';\n"
              "  END IF;\n"),
         new="",
         what="delete the onto-keys = held-chains check"),
    # X7 targets 0009: 0009 REPLACES the 0008 constraint, so the referee's literal 0008 mutation is
    # dead code now. This is the same edit on the live definition.
    dict(id="X7", kill="(E-4) a NULL approver session is refused",
         test="test_admission_approver_must_be_another_session[null_approver_session]",
         kind="replace", file=f"{MIG}/0009_referee2_fixes.sql",
         old="approver_session IS NOT NULL AND ", new="",
         what="drop approver_session IS NOT NULL (live constraint, 0009)"),
    dict(id="X8", kill="(E-7) set_current_run refuses a stale expected run",
         test="test_set_current_run_refuses_a_stale_expected_run",
         kind="replace", file=f"{MIG}/0007_referee_fixes.sql",
         old="WHERE f.id = p_file AND f.current_run_id IS NOT DISTINCT FROM p_expected_run;",
         new="WHERE f.id = p_file;",
         what="drop the compare-and-set predicate in set_current_run"),
    dict(id="X9", kill="(E-1) a commit over a write in flight is refused (workstream FOR UPDATE)",
         test="test_commit_waits_for_a_write_in_flight_and_is_refused",
         kind="replace", file=f"{MIG}/0005_promotion.sql",
         old="w.id = p.workstream_id AND w.state = 'open' FOR UPDATE;",
         new="w.id = p.workstream_id AND w.state = 'open';",
         what="drop FOR UPDATE on the workstream row in promote_commit"),
    dict(id="E4a", kill="(E-4) sessions compare trimmed",
         test="test_admission_approver_must_be_another_session[approver_session_trailing_space]",
         kind="replace", file=f"{MIG}/0009_referee2_fixes.sql",
         old="btrim(approver_session, E' \\t\\n\\r\\f\\x0b') <> btrim(admitter_session, E' \\t\\n\\r\\f\\x0b')",
         new="approver_session <> admitter_session",
         what="compare the raw sessions"),
    dict(id="E4b", kill="(E-4) a blank approver agent is refused",
         test="test_admission_approver_must_be_another_session[empty_approver_agent]",
         kind="replace", file=f"{MIG}/0009_referee2_fixes.sql",
         old="      AND btrim(approver_agent, E' \\t\\n\\r\\f\\x0b') <> ''\n", new="",
         what="drop the non-blank approver agent clause"),
    dict(id="E4c", kill="(E-4) a blank approver session is refused",
         test="test_admission_approver_must_be_another_session[empty_approver_session]",
         kind="replace", file=f"{MIG}/0009_referee2_fixes.sql",
         old="      AND btrim(approver_session, E' \\t\\n\\r\\f\\x0b') <> ''\n", new="",
         what="drop the non-blank approver session clause"),
    dict(id="E4d", kill="(E-4) a blank admitter session is refused",
         test="test_admission_approver_must_be_another_session[blank_admitter_session]",
         kind="block", file=f"{MIG}/0009_referee2_fixes.sql",
         marker="guard: admitter labels non-blank after trim",
         what="remove the admitter non-blank constraint"),
    dict(id="E4e", kill="(E-4) blank means any whitespace, not only spaces",
         test="test_admission_approver_must_be_another_session[blank_approver_agent]",
         kind="replace", file=f"{MIG}/0009_referee2_fixes.sql",
         old="      AND btrim(approver_agent, E' \\t\\n\\r\\f\\x0b') <> ''\n",
         new="      AND btrim(approver_agent) <> ''\n",
         what="trim spaces only (btrim's default)"),
    dict(id="E8a", kill="(E-8) connect() refuses a user carrying a second keyword",
         test="test_connect_refuses_promoter_login_bypasses[keyword_injection]",
         kind="block", file="pipeline/litkb/db/connect.py",
         marker="guard: login names are plain identifiers",
         what="remove the plain-identifier check on user and dbname"),
    dict(id="E8b", kill="(E-8) conninfo quotes every value",
         test="test_conninfo_quotes_values",
         kind="replace", file="pipeline/litkb/db/connect.py",
         old="    return make_conninfo(**kw)\n",
         new="    return ' '.join(f'{k}={v}' for k, v in kw.items())\n",
         what="build the conninfo unquoted (the pre-fix form)"),
]


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _pytest(nodes):
    """Run the named nodes of the test file, or the WHOLE file when nodes is empty."""
    targets = [f"{TEST}::{n}" for n in nodes] or [TEST]
    r = subprocess.run([sys.executable, "-m", "pytest", *targets,
                        "-q", "-p", "no:cacheprovider"],
                       cwd=str(SCRIPTS), capture_output=True, text=True, errors="replace")
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines) if " in " in ln and
                    any(w in ln for w in ("passed", "failed", "error", "skipped"))), "?")
    return r.returncode, summary.strip("= ").strip(), r.stdout


def _psql(sql):
    r = subprocess.run([PSQL, "-w", "-h", "localhost", "-p", "5433", "-U", "postgres",
                        "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-Atc", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _mutate_text(m):
    path = SCRIPTS / m["file"]
    original = path.read_bytes()
    text = original.decode("utf-8")
    if m["kind"] == "replace":
        n = text.count(m["old"])
        if n != 1:
            raise RuntimeError(f"{m['id']}: mutation target occurs {n} times in {m['file']}")
        mutated = text.replace(m["old"], m["new"])
    else:
        begin, end = f"BEGIN {m['marker']}", f"END {m['marker']}"
        lines = text.splitlines(keepends=True)
        bi = [i for i, ln in enumerate(lines) if begin in ln]
        ei = [i for i, ln in enumerate(lines) if end in ln]
        if len(bi) != 1 or len(ei) != 1 or ei[0] <= bi[0] + 1:
            raise RuntimeError(f"{m['id']}: markers not found exactly once in {m['file']}")
        mutated = "".join(lines[:bi[0] + 1] + lines[ei[0]:])
    if mutated == text:
        raise RuntimeError(f"{m['id']}: mutation changed nothing")
    return path, original, mutated.encode("utf-8")


def run_one(m, whole_file=False):
    nodes = [] if whole_file else [m["test"]]
    if m["kind"] == "cluster":
        _psql(m["apply"])
        try:
            rc, summary, out = _pytest(nodes)
        finally:
            _psql(m["revert"])
        leak = _psql("SELECT has_database_privilege('litkb_test', 'litkb', 'CONNECT')")
        if leak != "f":
            raise RuntimeError(f"{m['id']}: revert failed, litkb_test CONNECT on litkb = {leak}")
    else:
        path, original, mutated = _mutate_text(m)
        before = _sha(original)
        path.write_bytes(mutated)
        try:
            rc, summary, out = _pytest(nodes)
        finally:
            path.write_bytes(original)
        if _sha(path.read_bytes()) != before:
            raise RuntimeError(f"{m['id']}: {m['file']} was not restored byte-for-byte")
        print(f"     restored {m['file']} sha256 {before[:16]}… match: True")
    failed_word = "failed" if whole_file else "1 failed"
    fired = rc != 0 and failed_word in summary and "skipped" not in summary
    reason = ""
    if fired:
        err = [ln for ln in out.splitlines() if ln.startswith("E ")]
        reason = err[0][2:].strip()[:140] if err else ""
    return fired, summary, reason


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="show each litkb P1 kill fire")
    ap.add_argument("--only", help="comma-separated mutation ids (default: all)")
    ap.add_argument("--whole-file", action="store_true",
                    help=f"run the whole {TEST} under each mutation instead of its one kill test")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    chosen = MUTATIONS
    if a.only:
        wanted = [s.strip() for s in a.only.split(",") if s.strip()]
        unknown = sorted(set(wanted) - {m["id"] for m in MUTATIONS})
        if unknown:
            raise SystemExit(f"unknown mutation ids: {unknown}")
        chosen = [m for m in MUTATIONS if m["id"] in wanted]
    kills = [] if a.whole_file else list(dict.fromkeys(m["test"] for m in chosen))
    rc, summary, _ = _pytest(kills)
    print(f"baseline (unmutated, {'whole file' if a.whole_file else f'{len(kills)} tests'}): {summary}")
    baseline_ok = rc == 0 and "skipped" not in summary and "failed" not in summary
    rows = []
    for m in chosen:
        fired, summ, reason = run_one(m, a.whole_file)
        rows.append((m, fired, summ, reason))
        print(f"{m['id']:<4} {'FIRED' if fired else 'DID NOT FIRE':<13} {m['what']}")
        print(f"     test: {m['test']}  ->  {summ}")
        if reason:
            print(f"     first assertion line: {reason}")
    rc2, summary2, _ = _pytest(kills)
    print(f"baseline again (restored): {summary2}")
    baseline2_ok = rc2 == 0 and "skipped" not in summary2 and "failed" not in summary2
    all_fired = all(f for _m, f, _s, _r in rows)
    print(f"\n{sum(f for _m, f, _s, _r in rows)}/{len(rows)} mutations fired; "
          f"baselines {'passed' if baseline_ok and baseline2_ok else 'FAILED'}")
    sys.exit(0 if (all_fired and baseline_ok and baseline2_ok) else 1)


if __name__ == "__main__":
    main()

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
    dict(id="M2a", kill="second writer on the same base refused (fact table)",
         test="test_kill_fact_second_writer_on_same_base_is_refused",
         kind="replace", file=f"{MIG}/0003_write_functions.sql",
         old=" AND current_version_id IS NOT DISTINCT FROM $3', t.ident)",
         new="', t.ident)",
         what="drop the base predicate from the fact pointer UPDATE"),
    dict(id="M2b", kill="second writer on the same base refused (proposal)",
         test="test_kill_proposal_second_writer_on_same_base_is_refused",
         kind="replace", file=f"{MIG}/0003_write_functions.sql",
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
]


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _pytest(nodes):
    r = subprocess.run([sys.executable, "-m", "pytest", *[f"{TEST}::{n}" for n in nodes],
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


def run_one(m):
    if m["kind"] == "cluster":
        _psql(m["apply"])
        try:
            rc, summary, out = _pytest([m["test"]])
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
            rc, summary, out = _pytest([m["test"]])
        finally:
            path.write_bytes(original)
        if _sha(path.read_bytes()) != before:
            raise RuntimeError(f"{m['id']}: {m['file']} was not restored byte-for-byte")
    fired = rc != 0 and "1 failed" in summary and "skipped" not in summary
    reason = ""
    if fired:
        err = [ln for ln in out.splitlines() if ln.startswith("E ")]
        reason = err[0][2:].strip()[:140] if err else ""
    return fired, summary, reason


def main():
    kills = list(dict.fromkeys(m["test"] for m in MUTATIONS))
    rc, summary, _ = _pytest(kills)
    print(f"baseline (unmutated, {len(kills)} tests): {summary}")
    baseline_ok = rc == 0 and "skipped" not in summary and "failed" not in summary
    rows = []
    for m in MUTATIONS:
        fired, summ, reason = run_one(m)
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

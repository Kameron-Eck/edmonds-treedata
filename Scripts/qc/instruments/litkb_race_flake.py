"""litkb race tests: how reliable are they? (Kam, 2026-09-13; Reports/LITKB_OPS_2026-09-13.md)

A race test holds one connection's transaction open, starts a second call on another connection,
watches pg_blocking_pids until that call is seen waiting (or finishing without waiting), and only then
commits. A test like that can be unreliable in two directions:
  * FLAKY PASS-SIDE: the unmutated code fails some runs (a timing window the test does not control);
  * FLAKY KILL-SIDE: with the guard (a lock) removed, some runs still pass, so one green run of a
    mutation says little.
This instrument runs each race test REPS times in one pytest session per state and counts both.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_race_flake.py                 all tests, 30 reps
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_race_flake.py --tests D1,D8f --reps 30 --csv out.csv

States: the unmutated baseline for the chosen tests, then each mutation that targets them (the rows of
qc/instruments/litkb_p1_mutations.py by id, plus the acceptance verifier's N1, which is not a harness
row; the verifier's N2a is byte-identical to harness row F3b and is run once, as F3b). Source files are
restored after every mutation and checked by sha256. Everything runs against litkb_test only, through the
P1 suite's own fixtures (it resets and migrates litkb_test from the files on disk at session start, so a
mutated migration is live for exactly that session). Do not edit litkb files or run the P1 suite in this
worktree while it runs.
"""
import argparse
import csv
import datetime as dt
import importlib.util
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
MIG = "pipeline/litkb/db/migrations"


def _harness():
    spec = importlib.util.spec_from_file_location("litkb_p1_mutations", Path(__file__).with_name("litkb_p1_mutations.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# key: (wrapper call, extra fixtures, mutation ids that target this test's guard)
RACE_TESTS = {
    "D1": ("test_write_blocked_behind_promote_commit_is_refused(pg)", "", ["D1"]),
    "D8f": ("test_losing_concurrent_writer_gets_40001(pg, 'fact')", "", ["D8"]),
    "D8p": ("test_losing_concurrent_writer_gets_40001(pg, 'proposal')", "", ["D8"]),
    "X9": ("test_commit_waits_for_a_write_in_flight_and_is_refused(pg)", "", ["X9"]),
    "X2": ("test_concurrent_rebases_of_one_workstream_make_one_copy(pg, scratch_repo)", ", scratch_repo", ["X2"]),
    "X3": ("test_rebase_during_a_commit_that_moves_main_is_refused(pg, scratch_repo)", ", scratch_repo", ["X3"]),
    "X1": ("test_add_evidence_waits_for_a_prepare_in_flight_and_is_refused(pg)", "", ["X1"]),
    "F2b": ("test_abandon_waits_for_a_prepare_in_flight_and_is_refused(pg)", "", ["F2b", "N1"]),
    "F3b": ("test_add_use_embedding_waits_for_a_commit_in_flight_and_is_refused(pg)", "", ["F3b"]),
    "F7b": ("test_open_workstream_race_in_one_directory_leaves_no_orphan(pg, tmp_path)", ", tmp_path", ["F7b"]),
    "F8": ("test_token_is_bound_never_visible_in_pg_stat_activity(pg)", "", []),
}

_LOCK = "  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream FOR UPDATE;\n"
_CHECK_END = "  -- END guard: no abandon while a promotion is prepared\n"
EXTRA = {
    # acceptance verifier's N1: check-then-lock. The lock and the check both stay; only their order changes.
    "N1": dict(id="N1", file=f"{MIG}/0012_referee3_fixes.sql",
               steps=[(_LOCK + "  -- END guard: abandon locks the workstream row\n",
                       "  -- END guard: abandon locks the workstream row\n"),
                      (_CHECK_END, _CHECK_END + _LOCK)],
               what="abandon_workstream: move the FOR UPDATE row lock after the prepared-promotion check"),
}


def _apply(m, harness):
    """(path, original bytes, mutated bytes), every replaced string asserted to occur exactly once."""
    if "steps" not in m:
        return harness._mutate_text(m)
    path = SCRIPTS / m["file"]
    original = path.read_bytes()
    text = original.decode("utf-8")
    for old, new in m["steps"]:
        n = text.count(old)
        if n != 1:
            raise RuntimeError(f"{m['id']}: step target occurs {n} times in {m['file']}")
        text = text.replace(old, new)
    return path, original, text.encode("utf-8")


def _wrapper(keys, reps, directory):
    lines = ["import pytest", "import test_litkb_p1 as T",
             "from test_litkb_p1 import _pg_session, pg, scratch_repo  # noqa: F401  (fixtures)", ""]
    for k in keys:
        call, extra, _m = RACE_TESTS[k]
        lines += [f"@pytest.mark.parametrize('rep', range({reps}))",
                  f"def test_{k}(pg{extra}, rep):", f"    T.{call}", ""]
    p = Path(directory) / "test_race_flake_wrapper.py"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _session(keys, reps, tmp):
    """One pytest session over the chosen wrappers. Returns {key: {'passed','failed','skipped','first'}}."""
    wrapper = _wrapper(keys, reps, tmp)
    xml = Path(tmp) / "junit.xml"
    env = dict(os.environ, PYTHONUTF8="1",
               PYTHONPATH=os.pathsep.join([str(SCRIPTS / "qc"), str(SCRIPTS / "pipeline")]))
    r = subprocess.run([sys.executable, "-m", "pytest", str(wrapper), "-q", "-p", "no:cacheprovider",
                        f"--junitxml={xml}", "--rootdir", str(tmp)],
                       cwd=str(SCRIPTS), capture_output=True, text=True, errors="replace", env=env)
    out = {k: {"passed": 0, "failed": 0, "skipped": 0, "first": ""} for k in keys}
    if not xml.exists():
        raise RuntimeError(f"pytest wrote no junit xml: {(r.stdout + r.stderr)[-800:]}")
    for case in ET.parse(xml).getroot().iter("testcase"):
        key = case.get("name").split("[")[0][len("test_"):]
        bad = case.find("failure") if case.find("failure") is not None else case.find("error")
        if case.find("skipped") is not None:
            out[key]["skipped"] += 1
        elif bad is not None:
            out[key]["failed"] += 1
            if not out[key]["first"]:
                msg = (bad.get("message") or "").strip().splitlines()
                out[key]["first"] = (msg[0] if msg else "")[:160]
        else:
            out[key]["passed"] += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="measure litkb race-test reliability")
    ap.add_argument("--tests", default=",".join(RACE_TESTS))
    ap.add_argument("--reps", type=int, default=30)
    ap.add_argument("--no-mutations", action="store_true")
    ap.add_argument("--csv", default=None, help="append one row per (state, test) here")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    keys = [k.strip() for k in a.tests.split(",") if k.strip()]
    unknown = sorted(set(keys) - set(RACE_TESTS))
    if unknown:
        raise SystemExit(f"unknown race tests: {unknown}")
    harness = _harness()
    rows_by_id = {m["id"]: m for m in harness.MUTATIONS} | EXTRA
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results, ok = [], True

    def record(state, what, res, expect):
        nonlocal ok
        for k, v in res.items():
            good = (v["failed"] == 0 and v["skipped"] == 0 and v["passed"] == a.reps) if expect == "pass" \
                else (v["passed"] == 0 and v["skipped"] == 0 and v["failed"] == a.reps)
            ok &= good
            results.append(dict(utc=stamp, state=state, test=k, expect=expect, reps=a.reps, passed=v["passed"],
                                failed=v["failed"], skipped=v["skipped"], reliable=int(good), mutation=what,
                                first_failure=v["first"]))
            print(f"{state:<9} {k:<4} expect {expect:<4} passed {v['passed']:>3} failed {v['failed']:>3} "
                  f"skipped {v['skipped']:>2}  {'RELIABLE' if good else 'UNRELIABLE'}"
                  + (f"  | {v['first']}" if v["first"] else ""))

    with tempfile.TemporaryDirectory() as tmp:
        record("baseline", "", _session(keys, a.reps, tmp), "pass")
        if not a.no_mutations:
            for mid in dict.fromkeys(m for k in keys for m in RACE_TESTS[k][2]):
                m = rows_by_id[mid]
                targets = [k for k in keys if mid in RACE_TESTS[k][2]]
                path, original, mutated = _apply(m, harness)
                before = harness._sha(original)
                path.write_bytes(mutated)
                try:
                    res = _session(targets, a.reps, tmp)
                finally:
                    path.write_bytes(original)
                if harness._sha(path.read_bytes()) != before:
                    raise RuntimeError(f"{mid}: {m['file']} was not restored byte-for-byte")
                record(mid, m["what"], res, "fail")
    if a.csv:
        new = not Path(a.csv).exists()
        with open(a.csv, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0]))
            if new:
                w.writeheader()
            w.writerows(results)
    print(f"\n{'ALL RELIABLE' if ok else 'SOME UNRELIABLE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

r"""The acceptance instrument's own known-bads — one per check, each a real mutation.

`qc/instruments/litkb_acceptance.py` is what lets a cold session verify a work-plan session it
did not run. That makes its own trustworthiness the load-bearing thing: an acceptance gate that
passes a broken plan is worse than no gate, because it is quoted as evidence. CLAUDE.md 3.4c —
a kill criterion must be shown to FIRE on a known-bad input before it counts as a gate — so every
row below is an input the check must REFUSE, not an assertion about the code's shape.

  check                        the known-bad that makes it fire                test
  sessions_missing_abc         a `- (c)` bullet deleted from one session       test_a_missing_c_*
                               (a) (b) (c) present only under Work, no        test_work_bullets_*
                                 Done-state line
                               two letters missing from one block -> the      test_the_counter_is_*
                                 counter is 1 and stderr is 2 lines
  unresolved_decision_ids      a `litkb-nonexistent` id outside the dated     test_an_unknown_id_*
                                 region
  the dated exemption          the SAME id inside the dated region -> 0       test_the_same_id_*
  CRLF normalisation           a registry written with \r\n line endings      test_a_crlf_registry_*
  unexpected_worktrees         a checkout git reports, absent from the        test_a_checkout_the_*
                                 manifest
  branches_not_at_parity       a branch whose local and github hashes differ  test_a_branch_whose_*
  missing_evidence             a promised report that is not on disk          test_a_promised_report_*
  token_vault_mismatches       a token whose vault file is absent             test_a_token_whose_*
  guard-checkout               a checkout holding an un-vaulted token         test_the_guard_refuses_*
  dropoffs (scout)             a manifest frozen AFTER every drop-off         test_a_manifest_frozen_*
  missing_required_fields      a drop-off with no abstract_passage            test_a_dropoff_with_no_*
  ref_scheme_outside_set       an `isbn` drop-off                             test_an_isbn_dropoff_*
  missing_hunt_results         a drop-off with no row in the driver CSV       test_a_dropoff_with_no_csv_*
  unknown_states               a CSV row whose state is `banana`              test_a_csv_state_outside_*
  human_input_events           a permission denial / an AskUserQuestion /     test_a_permission_denial_*
                                 a result subtype that is not success         test_an_ask_user_*
                                                                              test_a_result_subtype_*
  stated_reason                a final message with no SCOUT-STOP line        test_a_log_with_no_stop_*
  the scout prompt template    a DOI, an arXiv id or a work key in it         test_a_prompt_naming_*
  the soak row writer          a CSV path outside the repository              test_a_soak_csv_outside_*
                               a search smoke that fails                      test_a_failing_search_still_*

The git queries are injected (`_worktree_list`, `_rev_parse` on the module), so parity is
exercised with no second remote and no network. The scout counters read a real worker database
(`LITKB_TEST_DB`), because the three DB-side checks are about REAL rows: a drop-off with a null
`abstract_passage` and a drop-off with `ref_scheme = 'isbn'` are both rows the table's own CHECKs
accept, and a fixture that mocked them would prove only that the mock was built to fail.

Nothing here writes outside tmp_path and the throwaway database, no `.litkb-workstream*` file is
ever committed — the token fixtures are created at run time, hold six bytes of non-secret filler,
and live only in tmp_path — and no test touches `Reports/LITKB_SOAK.csv`, the live tracked log.

Run:
  cd Scripts && PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN \
      py -3.12 -m pytest qc/test_litkb_acceptance.py -q
"""
import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
INSTRUMENT = SCRIPTS / "qc" / "instruments" / "litkb_acceptance.py"
DRIVER = SCRIPTS / "qc" / "instruments" / "litkb_scout_run.py"
DATA = SCRIPTS / "qc" / "testdata" / "litkb_acceptance"
SCOUT_DATA = SCRIPTS / "qc" / "testdata" / "litkb_scout"
PROMPT_DOC = SCRIPTS / "docs" / "LITKB_SCOUT_PROMPT.md"
GOOD_PLAN = DATA / "good_plan.md"
FIXTURE_DECISIONS = DATA / "decisions_fixture.yaml"

#: the plan's home once S0 lands, and the staged copy the instrument was built against. Neither
#: is required for this suite: the real-document test skips when both are absent (CI).
REAL_PLAN = SCRIPTS / "LITKB_WORKPLAN.md"
STAGED_PLAN = Path(r"D:\tools\claude-config\jobs\litkb-s0\LITKB_WORKPLAN.md")

TOKEN_BYTES = b"dummy\n"          # never a real token, never 64 hex characters


@pytest.fixture(scope="module")
def mod():
    """The instrument by path — qc/instruments/ is not a package and this repo does not make it
    one (pyproject: `pipeline` and `qc` are deliberately not packages)."""
    spec = importlib.util.spec_from_file_location("litkb_acceptance", INSTRUMENT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(mod, capsys, argv):
    """(exit code, stdout, stderr) for one in-process invocation."""
    code = mod.main(argv)
    cap = capsys.readouterr()
    return code, cap.out.strip(), cap.err.strip()


def plan_on(mod, capsys, text, decisions=None, tmp_path=None):
    """Score `text` as a plan, against the fixture registry unless another is given."""
    path = tmp_path / "plan.md"
    path.write_text(text, encoding="utf-8")
    return run(mod, capsys, ["plan", "--file", str(path),
                             "--decisions", str(decisions or FIXTURE_DECISIONS)])


# ── plan: the good input, then one mutation at a time ─────────────────────────────────────

def test_the_good_plan_scores_zero_and_exits_zero(mod, capsys):
    code, out, err = run(mod, capsys, ["plan", "--file", str(GOOD_PLAN),
                                       "--decisions", str(FIXTURE_DECISIONS)])
    assert out == "sessions_missing_abc=0 unresolved_decision_ids=0", out
    assert err == "", err
    assert code == 0


def test_a_missing_c_bullet_is_counted_and_named(mod, capsys, tmp_path):
    """The mutation the plan's own S0 (c) bullet promises: delete one `- (c)`."""
    text = GOOD_PLAN.read_text(encoding="utf-8").replace(
        "- (c) the known-bad this session's gate refuses\n", "")
    code, out, err = plan_on(mod, capsys, text, tmp_path=tmp_path)
    assert out == "sessions_missing_abc=1 unresolved_decision_ids=0", out
    assert "S1: missing (c)" in err, err
    assert code == 1


def test_work_bullets_do_not_satisfy_the_done_state(mod, capsys, tmp_path):
    """(a)/(b)/(c) under Work with no `Done-state` line at all: a session block can otherwise
    look complete while promising nothing a cold session can run."""
    text = ("## L\n\n### S4 — no done-state\n\nWork\n"
            "- (a) an artifact\n- (b) a command\n- (c) a known-bad\n")
    code, out, err = plan_on(mod, capsys, text, tmp_path=tmp_path)
    assert out == "sessions_missing_abc=1 unresolved_decision_ids=0", out
    assert [ln for ln in err.splitlines()] == [
        "S4: missing (a)", "S4: missing (b)", "S4: missing (c)"], err
    assert code == 1


def test_the_counter_is_sessions_not_bullets(mod, capsys, tmp_path):
    """Two letters missing from ONE block is one broken session and two offences. If the counter
    counted bullets, a single session could report 3 and a reader would hunt three sessions."""
    text = GOOD_PLAN.read_text(encoding="utf-8")
    for gone in ("- (b) a command\n",       # S1's; S0's reads "a command that prints counters"
                 "- (c) the known-bad this session's gate refuses\n"):
        text = text.replace(gone, "")
    code, out, err = plan_on(mod, capsys, text, tmp_path=tmp_path)
    assert out == "sessions_missing_abc=1 unresolved_decision_ids=0", out
    assert err.splitlines() == ["S1: missing (b)", "S1: missing (c)"], err
    assert code == 1


def test_an_unknown_id_outside_the_dated_region_is_unresolved(mod, capsys, tmp_path):
    text = GOOD_PLAN.read_text(encoding="utf-8").replace(
        "- the second thing, ruled by `litkb-fixture-two`",
        "- the second thing, ruled by `litkb-fixture-two` and `litkb-nonexistent`")
    code, out, err = plan_on(mod, capsys, text, tmp_path=tmp_path)
    assert out == "sessions_missing_abc=0 unresolved_decision_ids=1", out
    assert err == "unresolved id: litkb-nonexistent", err
    assert code == 1


def test_the_same_id_inside_the_dated_region_is_not_checked(mod, capsys, tmp_path):
    """The exemption, proven against the SAME id the previous test failed on — otherwise the
    region marker could be doing nothing and both tests would still pass."""
    text = GOOD_PLAN.read_text(encoding="utf-8").replace(
        "`litkb-dated-only` is cited here",
        "`litkb-nonexistent` and `litkb-dated-only` are cited here")
    code, out, err = plan_on(mod, capsys, text, tmp_path=tmp_path)
    assert out == "sessions_missing_abc=0 unresolved_decision_ids=0", out
    assert code == 0


def test_an_unclosed_dated_marker_blanks_to_end_of_file(mod, capsys, tmp_path):
    text = GOOD_PLAN.read_text(encoding="utf-8").replace("<!-- drift-gate:dated-end -->", "")
    code, out, _ = plan_on(mod, capsys, text, tmp_path=tmp_path)
    assert out == "sessions_missing_abc=0 unresolved_decision_ids=0", out
    assert code == 0


def test_a_session_inside_the_dated_region_is_not_graded(mod, capsys, tmp_path):
    text = ("### S0 — graded\n\nDone-state\n- (a) x\n- (b) y\n- (c) z\n\n"
            "<!-- drift-gate:dated-begin -->\n### S9 — a dated record\n\nWork\n- nothing\n"
            "<!-- drift-gate:dated-end -->\n")
    code, out, _ = plan_on(mod, capsys, text, tmp_path=tmp_path)
    assert out == "sessions_missing_abc=0 unresolved_decision_ids=0", out
    assert code == 0


def test_a_crlf_registry_still_resolves_its_ids(mod, capsys, tmp_path):
    r"""decisions.yaml is CRLF on this machine. A scan that kept the trailing `\r` would report
    every id in the plan unresolved — a gate that fires on everything is as useless as one that
    never fires, and it would fire on the day someone re-saved the registry."""
    crlf = tmp_path / "decisions_crlf.yaml"
    crlf.write_bytes(FIXTURE_DECISIONS.read_text(encoding="utf-8").replace(
        "\n", "\r\n").encode("utf-8"))
    code, out, _ = run(mod, capsys, ["plan", "--file", str(GOOD_PLAN), "--decisions", str(crlf)])
    assert out == "sessions_missing_abc=0 unresolved_decision_ids=0", out
    assert code == 0
    # and the mutation that proves the assertion above is not vacuous: an id absent from the
    # CRLF registry is still reported
    crlf.write_bytes(b"decisions:\r\n  - id: litkb-fixture-one\r\n")
    code, out, err = run(mod, capsys,
                         ["plan", "--file", str(GOOD_PLAN), "--decisions", str(crlf)])
    assert out == "sessions_missing_abc=0 unresolved_decision_ids=1", out
    assert err == "unresolved id: litkb-fixture-two", err


# ── disposition ───────────────────────────────────────────────────────────────────────────

def manifest_for(tmp_path, **over):
    """A manifest whose every promise is met, plus the files that meet them."""
    repo = tmp_path / "repo"
    (repo / "Reports").mkdir(parents=True, exist_ok=True)
    (repo / "Reports" / "LITKB_WORKTREE_DISPOSITION.md").write_text("x", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    (vault / "op-test-1.token").write_bytes(TOKEN_BYTES)
    m = {"repo": str(repo),
         "expected_worktrees": [str(tmp_path / "wt-kept")],
         "disposed_branches": ["work/20260915-access-layer"],
         "evidence": ["Reports/LITKB_WORKTREE_DISPOSITION.md"],
         "vault": str(vault),
         "tokens": [{"slug": "op-test-1", "vault_file": "op-test-1.token"}]}
    m.update(over)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(m), encoding="utf-8")
    return m, path


def patch_git(mod, monkeypatch, worktrees, hashes):
    """Inject the two git queries: `hashes` maps a ref to the commit it resolves to."""
    monkeypatch.setattr(mod, "_worktree_list", lambda repo: list(worktrees))
    monkeypatch.setattr(mod, "_rev_parse", lambda repo, ref: hashes.get(ref))


ONE_HASH = {"work/20260915-access-layer": "a" * 40, "github/work/20260915-access-layer": "a" * 40}


def test_a_met_manifest_scores_zero(mod, capsys, tmp_path, monkeypatch):
    m, path = manifest_for(tmp_path)
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")], ONE_HASH)
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert out == ("unexpected_worktrees=0 branches_not_at_parity=0 missing_evidence=0 "
                   "token_vault_mismatches=0"), out
    assert err == "" and code == 0


def test_the_main_checkout_never_counts_as_unexpected(mod, capsys, tmp_path, monkeypatch):
    """The manifest lists the worktrees that MAY survive; the repo itself is not one of them and
    listing it would be noise. A checker that demanded it would fire on every correct run."""
    m, path = manifest_for(tmp_path, expected_worktrees=[])
    patch_git(mod, monkeypatch, [m["repo"]], ONE_HASH)
    code, out, _ = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "unexpected_worktrees=0" in out and code == 0


def test_a_checkout_the_manifest_omits_is_unexpected(mod, capsys, tmp_path, monkeypatch):
    m, path = manifest_for(tmp_path)
    patch_git(mod, monkeypatch,
              [m["repo"], str(tmp_path / "wt-kept"), str(tmp_path / "wt-should-be-gone")],
              ONE_HASH)
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "unexpected_worktrees=1" in out, out
    assert "wt-should-be-gone" in err and code == 1


def test_path_shape_alone_does_not_make_a_checkout_unexpected(mod, capsys, tmp_path, monkeypatch):
    """git's porcelain prints forward slashes; a Windows manifest holds backslashes. Comparing
    the raw strings would report every surviving checkout as unexpected.

    The separator swap is checked everywhere; the CASE fold only on Windows, because
    `os.path.normcase` is the identity on POSIX and CI runs ubuntu-latest — where `C:/X` and
    `C:/x` really are two different checkouts and folding them would be the bug.
    """
    m, path = manifest_for(tmp_path)
    odd = str(tmp_path / "wt-kept").replace(os.sep, "/")
    if os.name == "nt":
        odd = odd.upper()
    patch_git(mod, monkeypatch, [m["repo"], odd], ONE_HASH)
    code, out, _ = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "unexpected_worktrees=0" in out, out
    assert code == 0


def test_a_branch_whose_hashes_differ_is_not_at_parity(mod, capsys, tmp_path, monkeypatch):
    m, path = manifest_for(tmp_path)
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")],
              {"work/20260915-access-layer": "a" * 40,
               "github/work/20260915-access-layer": "b" * 40})
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "branches_not_at_parity=1" in out, out
    assert "work/20260915-access-layer" in err and code == 1


def test_an_unresolvable_ref_is_not_at_parity(mod, capsys, tmp_path, monkeypatch):
    """A branch never pushed resolves locally and not remotely. Treating a missing remote ref as
    "nothing to compare, so fine" would green-light removing the only copy of the work."""
    m, path = manifest_for(tmp_path)
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")],
              {"work/20260915-access-layer": "a" * 40})
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "branches_not_at_parity=1" in out, out
    assert "unresolved" in err and code == 1


def test_a_promised_report_that_is_absent_is_missing_evidence(mod, capsys, tmp_path, monkeypatch):
    m, path = manifest_for(tmp_path, evidence=["Reports/LITKB_NOT_ARCHIVED.md"])
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")], ONE_HASH)
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "missing_evidence=1" in out, out
    assert "LITKB_NOT_ARCHIVED.md" in err and code == 1


def test_a_token_whose_vault_file_is_absent_is_a_mismatch(mod, capsys, tmp_path, monkeypatch):
    m, path = manifest_for(tmp_path, tokens=[{"slug": "held-queue",
                                              "vault_file": "held-queue.token"}])
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")], ONE_HASH)
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "token_vault_mismatches=1" in out, out
    assert "held-queue" in err and code == 1


def test_an_empty_vault_file_is_a_mismatch(mod, capsys, tmp_path, monkeypatch):
    """`touch`-ing the vault file is exactly the shape a hurried disposition takes."""
    m, path = manifest_for(tmp_path)
    (Path(m["vault"]) / "op-test-1.token").write_bytes(b"")
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")], ONE_HASH)
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "token_vault_mismatches=1" in out, out
    assert "empty" in err and code == 1


def test_a_vault_file_escaping_the_vault_is_a_mismatch(mod, capsys, tmp_path, monkeypatch):
    m, path = manifest_for(tmp_path, tokens=[{"slug": "escape",
                                              "vault_file": "../repo/Reports/"
                                                            "LITKB_WORKTREE_DISPOSITION.md"}])
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")], ONE_HASH)
    code, out, err = run(mod, capsys, ["disposition", "--manifest", str(path)])
    assert "token_vault_mismatches=1" in out, out
    assert "escapes the vault" in err and code == 1


def test_disposition_never_reads_a_token(mod, tmp_path, monkeypatch):
    """Existence, size and containment only. The instrument holds no code path that opens a
    vault file, so a secret cannot reach stdout, a log or a traceback through it.

    BOTH names are patched. `builtins.open` alone is not enough and looks like it is: pathlib's
    `read_bytes`/`read_text`/`open` go through `io.open`, a separate binding of the same
    function, so a watcher on builtins sees nothing pathlib does and reports a clean run no
    matter what the instrument reads. Both variants were RUN against one mutation — a
    `path.read_bytes()` added inside `check_disposition`, which makes the instrument genuinely
    read the vault file:

        builtins only, no `assert opened`  (the shape this test first had)  ->  1 passed
        both names patched, `assert opened`                                 ->  1 failed,
                                                                                naming the
                                                                                .token file

    The instrument was restored after each and re-verified against its committed blob. The first
    row is why `assert opened` is here: a watcher that sees no file at all now fails loudly
    instead of certifying a clean run.
    """
    import io

    m, path = manifest_for(tmp_path)
    opened = []
    real_builtin, real_io = open, io.open

    def watch(real):
        def watched(file, *a, **k):
            opened.append(str(file))
            return real(file, *a, **k)
        return watched

    monkeypatch.setattr("builtins.open", watch(real_builtin))
    monkeypatch.setattr("io.open", watch(real_io))
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")], ONE_HASH)
    mod.main(["disposition", "--manifest", str(path)])
    assert opened, "the watcher saw no file at all — it is not watching the read path"
    assert not [f for f in opened if f.endswith(".token")], opened


# ── guard-checkout ────────────────────────────────────────────────────────────────────────

def test_the_guard_refuses_an_unvaulted_token_and_prints_no_content(mod, capsys, tmp_path):
    root, vault = tmp_path / "wt", tmp_path / "vault"
    root.mkdir()
    vault.mkdir()
    (root / ".litkb-workstream").write_bytes(TOKEN_BYTES)
    code, out, err = run(mod, capsys, ["guard-checkout", "--path", str(root),
                                       "--vault", str(vault)])
    assert code == 2
    assert err == "refused: .litkb-workstream not vaulted", err
    assert TOKEN_BYTES.decode().strip() not in (out + err)
    # not the hash either: a sha256 of a secret is still derived from the secret
    assert not re.search(r"[0-9a-f]{64}", out + err), (out, err)


def test_the_guard_passes_when_the_same_bytes_are_in_the_vault(mod, capsys, tmp_path):
    root, vault = tmp_path / "wt", tmp_path / "vault"
    root.mkdir()
    vault.mkdir()
    (root / ".litkb-workstream").write_bytes(TOKEN_BYTES)
    (vault / "linkage-review.token").write_bytes(TOKEN_BYTES)   # vaulted under another NAME
    code, _, err = run(mod, capsys, ["guard-checkout", "--path", str(root), "--vault",
                                     str(vault)])
    assert code == 0, err


def test_the_guard_compares_bytes_not_names(mod, capsys, tmp_path):
    """A vault file with the right name and the wrong bytes is the failure mode a name check
    cannot see — a stale copy vaulted before the workstream was reopened."""
    root, vault = tmp_path / "wt", tmp_path / "vault"
    root.mkdir()
    vault.mkdir()
    (root / ".litkb-workstream").write_bytes(TOKEN_BYTES)
    (vault / ".litkb-workstream").write_bytes(b"other\n")
    code, _, err = run(mod, capsys, ["guard-checkout", "--path", str(root), "--vault",
                                     str(vault)])
    assert code == 2 and "not vaulted" in err


def test_a_missing_vault_directory_fails_closed(mod, capsys, tmp_path):
    root = tmp_path / "wt"
    root.mkdir()
    (root / ".litkb-workstream").write_bytes(TOKEN_BYTES)
    code, _, err = run(mod, capsys, ["guard-checkout", "--path", str(root),
                                     "--vault", str(tmp_path / "no-such-vault")])
    assert code == 2 and "not vaulted" in err


def test_a_checkout_with_no_token_is_allowed(mod, capsys, tmp_path):
    root, vault = tmp_path / "wt", tmp_path / "vault"
    root.mkdir()
    vault.mkdir()
    (root / "README.md").write_text("no token here", encoding="utf-8")
    code, _, _ = run(mod, capsys, ["guard-checkout", "--path", str(root), "--vault", str(vault)])
    assert code == 0


def test_a_suffixed_token_file_is_guarded_too(mod, capsys, tmp_path):
    """`.litkb-workstream.bak` is still a token. The glob is the point of the rule."""
    root, vault = tmp_path / "wt", tmp_path / "vault"
    root.mkdir()
    vault.mkdir()
    (root / ".litkb-workstream.bak").write_bytes(TOKEN_BYTES)
    code, _, err = run(mod, capsys, ["guard-checkout", "--path", str(root), "--vault",
                                     str(vault)])
    assert code == 2 and ".litkb-workstream.bak" in err


def test_a_checkout_that_does_not_exist_is_neither_refusal_nor_pass(mod, capsys, tmp_path):
    """Exit 1, not 0: "the path is gone" must not read as "safe to remove"."""
    code, _, err = run(mod, capsys, ["guard-checkout", "--path", str(tmp_path / "gone"),
                                     "--vault", str(tmp_path)])
    assert code == 1 and "no such checkout" in err


# ── the wiring, and the real document ─────────────────────────────────────────────────────

def test_the_defaults_resolve_from_the_instrument_not_the_cwd(mod):
    assert mod.PLAN_DEFAULT == SCRIPTS / "LITKB_WORKPLAN.md"
    assert mod.DECISIONS_DEFAULT == SCRIPTS / "decisions.yaml"


def test_the_script_runs_as_a_script_from_another_directory(tmp_path):
    """`__main__` wiring plus the decisions DEFAULT, exercised from a foreign cwd: the run below
    passes no --decisions, so it can only resolve the registry from the instrument's own
    location. The fixture's ids are absent from the project registry, which is what proves the
    project registry — not the fixture one — was read."""
    r = subprocess.run([sys.executable, str(INSTRUMENT), "plan", "--file", str(GOOD_PLAN)],
                       cwd=str(tmp_path), capture_output=True, text=True, errors="replace")
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout.strip() == "sessions_missing_abc=0 unresolved_decision_ids=2", r.stdout
    assert "unresolved id: litkb-fixture-one" in r.stderr, r.stderr


def test_the_real_plan_is_graded_and_its_sessions_are_complete(mod, capsys):
    """The staged document the instrument was built against, or the tracked one once S0 lands.

    The exit code is NOT asserted to be 1: three of its ids are the owner's to add to
    decisions.yaml, and an assertion of "still broken" would go red on the day it is fixed.
    What is asserted is the part the instrument owns — every session block carries (a)(b)(c) —
    and that the exit code follows the counters.
    """
    path = REAL_PLAN if REAL_PLAN.exists() else STAGED_PLAN
    if not path.exists():
        pytest.skip("no LITKB_WORKPLAN.md tracked here and no staged copy on this machine")
    code, out, _ = run(mod, capsys, ["plan", "--file", str(path)])
    missing, unresolved = (int(f.split("=")[1]) for f in out.split())
    assert missing == 0, out
    assert code == (0 if unresolved == 0 else 1)


# ── scout: the counters, on a real worker database ────────────────────────────────────────
#
# WHY A REAL DATABASE AND NOT A FIXTURE. Three of the six scout counters read `hunt_requests`
# rows, and the two known-bads for them — a null `abstract_passage`, `ref_scheme = 'isbn'` — are
# rows the table's own CHECK constraints ACCEPT. That is the whole point: the contract is
# narrower than the schema, and only a real row can show the gate enforcing the difference. A
# mocked row would demonstrate that a mock built to fail fails.

pg_only = pytest.mark.requires_litkb_pg

GOOD_DROPOFF = {
    "ref": "10.1109/tgrs.2017.2719738",
    "ref_scheme": "doi",
    "claimed_title": "Learning Aerial Image Segmentation From Online Maps",
    "claimed_authors": "Kaiser",
    "claimed_year": 2017,
    "expected_claim": "CNN aerial segmentation tolerates noisy training labels.",
    "why_relevant": "Projected 2020 labels are label noise. confidence: medium",
    "abstract_passage": "training with large amounts of noisy labels is possible",
}

BEFORE = "2000-01-01T00:00:00Z"        # every seeded row is created after this
AFTER = "2999-01-01T00:00:00Z"         # and before this


@pytest.fixture
def scout_ws(tmp_path, litkb_pg_base):
    """A throwaway workstream on the worker DB, plus the seeding helper.

    `litkb_test` stands in for reader, writer and ingest (it is a member of all three WITH
    INHERIT FALSE), which is how every other litkb suite exercises the roles without a second
    set of credentials — so nothing here can reach the live `litkb`."""
    from litkb import hunt_request, workstream
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws_id = workstream.open_workstream(conn, f"scout-{uuid.uuid4().hex[:8]}", "test",
                                       "scout acceptance tests", directory=wt)
    _ws, token = workstream.load(wt)

    def seed(n=10, **over):
        ids = []
        for _i in range(n):
            fields = dict(GOOD_DROPOFF, **over)
            fields["ref"] = f"{fields['ref']}/{uuid.uuid4().hex[:8]}"
            ids.append(str(hunt_request.record(conn, ws_id, token, agent="scout-test",
                                               session="scout-test-session", **fields)))
        return ids

    return {"conn": conn, "ws_id": str(ws_id), "wt": wt, "db": c.DB_TEST, "seed": seed}


def scout_manifest(tmp_path, scout_ws, *, frozen_at, run_csv, log):
    """A frozen manifest pointing at the throwaway workstream. `frozen_at` is the only knob the
    frozen-manifest mutation needs: moving it past every row is what makes `dropoffs` zero."""
    m = {"kind": "litkb-scout",
         "frozen_at": frozen_at,
         "repo": str(SCRIPTS.parent),
         "repo_head": "0" * 40,
         "db": scout_ws["db"],
         "reader_role": "litkb_test",
         "workstream_slug": "scout-test",
         "workstream_id": scout_ws["ws_id"],
         "baseline_hunt_requests": 0,
         "topic": "a topic",
         "launch_cmd": "claude -p ...",
         "log": str(log),
         "run_csv": str(run_csv),
         "worktree": str(scout_ws["wt"]),
         "spend": False}
    p = tmp_path / "scout_manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return m, p


def write_run_csv(mod, path, hr_ids, *, state="extracted", omit=(), states=None):
    """A driver CSV covering `hr_ids`. `omit` drops rows; `states` overrides per id."""
    states = states or {}
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(mod.RUN_CSV_COLUMNS))
        w.writeheader()
        for hr in hr_ids:
            if hr in omit:
                continue
            w.writerow({"hr_id": hr, "ref": "10.x/y", "ref_scheme": "doi",
                        "claimed_title": "t", "claimed_year": 2017, "fields_missing": "",
                        "hunt_ok": "true", "hunt_state_or_refusal": states.get(hr, state),
                        "message": "", "seconds": 0.4})
    return path


def scout_run(mod, capsys, manifest_path):
    return run(mod, capsys, ["scout", "--manifest", str(manifest_path)])


def counters_of(out):
    return dict(f.split("=", 1) for f in out.split())


@pg_only
def test_a_full_clean_scout_run_scores_its_bounds_and_exits_zero(mod, capsys, tmp_path, scout_ws):
    ids = scout_ws["seed"](10)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids)
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, err = scout_run(mod, capsys, path)
    assert counters_of(out) == {"dropoffs": "10", "missing_required_fields": "0",
                                "ref_scheme_outside_set": "0", "missing_hunt_results": "0",
                                "unknown_states": "0", "human_input_events": "0",
                                "stated_reason": "1"}, out
    assert err == "", err
    assert code == 0


@pg_only
def test_a_manifest_frozen_after_every_dropoff_counts_none(mod, capsys, tmp_path, scout_ws):
    """The frozen-manifest mutation. A manifest written AFTER the run grades nothing, and the
    counter that says so is `dropoffs=0` — not a silent pass with nothing to check."""
    ids = scout_ws["seed"](10)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids)
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=AFTER, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, _ = scout_run(mod, capsys, path)
    assert counters_of(out)["dropoffs"] == "0", out
    assert code == 1


@pg_only
def test_a_dropoff_with_no_abstract_passage_is_a_missing_required_field(mod, capsys, tmp_path,
                                                                       scout_ws):
    """The schema leaves `abstract_passage` nullable; the scout's contract does not. This is a
    row the database accepts without complaint."""
    ids = scout_ws["seed"](9) + scout_ws["seed"](1, abstract_passage=None)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids)
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, err = scout_run(mod, capsys, path)
    assert counters_of(out)["missing_required_fields"] == "1", out
    assert "missing abstract_passage" in err, err
    assert code == 1


@pg_only
def test_a_blank_field_counts_as_missing_not_present(mod, capsys, tmp_path, scout_ws):
    """`claimed_authors = "   "` passes every CHECK the table has and tells the resolver nothing."""
    ids = scout_ws["seed"](9) + scout_ws["seed"](1, claimed_authors="   ")
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids)
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, err = scout_run(mod, capsys, path)
    assert counters_of(out)["missing_required_fields"] == "1", out
    assert "claimed_authors" in err and code == 1


@pg_only
def test_an_isbn_dropoff_is_outside_the_allowed_scheme_set(mod, capsys, tmp_path, scout_ws):
    """`isbn` is in the DATABASE's vocabulary and outside the scout's. The gate is the difference."""
    ids = scout_ws["seed"](9) + scout_ws["seed"](1, ref_scheme="isbn", ref="978-0-13-235088-4")
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids)
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, err = scout_run(mod, capsys, path)
    assert counters_of(out)["ref_scheme_outside_set"] == "1", out
    assert "'isbn' outside" in err, err
    assert code == 1


@pg_only
def test_a_csv_state_outside_the_closed_vocabulary_is_unknown(mod, capsys, tmp_path, scout_ws):
    ids = scout_ws["seed"](10)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids, states={ids[3]: "banana"})
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, err = scout_run(mod, capsys, path)
    assert counters_of(out)["unknown_states"] == "1", out
    assert "'banana' outside the closed vocabulary" in err, err
    assert code == 1


@pg_only
def test_a_generic_error_refusal_is_also_unknown(mod, capsys, tmp_path, scout_ws):
    """hunt() returns `refused: "error"` for any unexpected exception. If `error` were inside the
    vocabulary, a driver that crashed on every row would report a full set of known states."""
    ids = scout_ws["seed"](10)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids, state="error")
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, _ = scout_run(mod, capsys, path)
    assert counters_of(out)["unknown_states"] == "10", out
    assert code == 1


@pg_only
def test_a_dropoff_with_no_csv_row_is_a_missing_hunt_result(mod, capsys, tmp_path, scout_ws):
    ids = scout_ws["seed"](10)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids, omit={ids[0], ids[1]})
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, err = scout_run(mod, capsys, path)
    assert counters_of(out)["missing_hunt_results"] == "2", out
    assert "no row in the driver CSV" in err and code == 1


@pg_only
def test_a_missing_driver_csv_names_every_dropoff_rather_than_throwing(mod, capsys, tmp_path,
                                                                      scout_ws):
    """"the driver never ran" must land on a counter that names the rows, not on a traceback."""
    ids = scout_ws["seed"](10)
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE,
                              run_csv=tmp_path / "never-written.csv",
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, _ = scout_run(mod, capsys, path)
    assert counters_of(out)["missing_hunt_results"] == str(len(ids)), out
    assert code == 1


@pg_only
def test_ten_is_the_floor_and_nine_fails(mod, capsys, tmp_path, scout_ws):
    """`dropoffs` is the one counter that is a FLOOR. Nine clean drop-offs is still a refusal."""
    ids = scout_ws["seed"](9)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids)
    _m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                              log=SCOUT_DATA / "clean_log.jsonl")
    code, out, _ = scout_run(mod, capsys, path)
    assert counters_of(out)["dropoffs"] == "9" and code == 1, out


@pg_only
def test_a_manifest_cannot_widen_its_own_vocabulary(mod, capsys, tmp_path, scout_ws):
    """The manifest is written by the session being graded. A checker that read its vocabulary
    out of it would let that session pass itself by listing `banana`."""
    ids = scout_ws["seed"](10)
    csv_path = write_run_csv(mod, tmp_path / "run.csv", ids, state="banana")
    m, path = scout_manifest(tmp_path, scout_ws, frozen_at=BEFORE, run_csv=csv_path,
                             log=SCOUT_DATA / "clean_log.jsonl")
    m["closed_states"] = list(mod.CLOSED_STATES) + ["banana"]
    m["allowed_ref_schemes"] = list(mod.ALLOWED_SCHEMES) + ["isbn"]
    path.write_text(json.dumps(m), encoding="utf-8")
    code, out, _ = scout_run(mod, capsys, path)
    assert counters_of(out)["unknown_states"] == "10", out
    assert code == 1


# ── scout: the log half, which needs no database ──────────────────────────────────────────

def test_a_clean_log_has_no_human_input_and_a_stated_reason(mod):
    assert mod.read_log(SCOUT_DATA / "clean_log.jsonl") == (0, 1, [])


def test_a_permission_denial_is_a_human_input_event(mod):
    events, stated, offences = mod.read_log(SCOUT_DATA / "denied_log.jsonl")
    assert events == 1 and stated == 1
    assert "1 permission denial(s)" in offences[0], offences


def test_an_ask_user_question_is_a_human_input_event(mod):
    events, stated, _ = mod.read_log(SCOUT_DATA / "ask_user_log.jsonl")
    assert events == 1 and stated == 1


def test_a_result_subtype_that_is_not_success_is_a_human_input_event(mod):
    """`error_max_turns` is the shape an unattended run dies in. This fixture still carries a
    SCOUT-STOP line, so `stated_reason` alone would call it a clean stop."""
    events, stated, offences = mod.read_log(SCOUT_DATA / "error_max_turns_log.jsonl")
    assert events == 1 and stated == 1
    assert "not 'success'" in offences[0], offences


def test_a_log_with_no_stop_line_states_no_reason(mod):
    assert mod.read_log(SCOUT_DATA / "no_reason_log.jsonl")[:2] == (0, 0)


def test_a_missing_log_is_an_event_not_a_crash(mod, tmp_path):
    events, stated, offences = mod.read_log(tmp_path / "no-such.jsonl")
    assert events == 1 and stated == 0 and "missing" in offences[0]


def test_a_log_with_no_result_message_is_an_event(mod, tmp_path):
    """A run killed before its result message leaves a truncated log. Counting zero events on it
    would report the cleanest possible sheet for the least complete possible run."""
    p = tmp_path / "truncated.jsonl"
    p.write_text('{"type":"system","subtype":"init"}\n', encoding="utf-8")
    events, stated, offences = mod.read_log(p)
    assert events == 1 and stated == 0 and "no final `result` message" in offences[0]


def test_an_unparseable_line_does_not_stop_the_count(mod, tmp_path):
    p = tmp_path / "noisy.jsonl"
    p.write_text("a banner the CLI never printed\n" +
                 (SCOUT_DATA / "clean_log.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    assert mod.read_log(p) == (0, 1, [])


# ── scout: the vocabulary and the field set are the module's, not the manifest's ───────────

def test_the_closed_vocabulary_matches_hunts_own(mod):
    """`CLOSED_STATES` stays pinned to `litkb.hunt.STATES`. If hunt gained a ladder state and this
    constant did not, every run carrying it would be refused as `unknown_states`."""
    pytest.importorskip("litkb", reason="litkb imports only with PYTHONPATH=pipeline")
    from litkb.hunt import REF_REFUSALS, STATES
    assert mod.CLOSED_STATES[:len(STATES)] == tuple(STATES)
    assert "error" not in mod.CLOSED_STATES
    # pinned to hunt's own closed tuple, not to a list retyped here: the merge of the two S1
    # builders found this constant one code short (`unknown-ref-scheme`)
    assert set(mod.CLOSED_STATES) - set(STATES) == {"held-no-spend", *REF_REFUSALS}
    assert len(mod.CLOSED_STATES) == len(STATES) + 1 + len(REF_REFUSALS)


def test_the_required_field_set_is_the_eight_the_skill_names(mod):
    assert mod.REQUIRED_FIELDS == ("ref", "ref_scheme", "claimed_title", "claimed_authors",
                                   "claimed_year", "expected_claim", "why_relevant",
                                   "abstract_passage")
    assert mod.ALLOWED_SCHEMES == ("doi", "arxiv", "url", "title")
    assert mod.MIN_DROPOFFS == 10


# ── the scout prompt template may not seed ────────────────────────────────────────────────

#: A DOI, an arXiv id, a work key. `decisions.yaml` -> `litkb-k2-no-seeding`: the scout's
#: expectations must be its own, so its prompt may not name the paper it is supposed to find.
SEED_SHAPES = {
    "a DOI": re.compile(r"10\.\d{4,}/\S+"),
    "an arXiv id": re.compile(r"\b\d{4}\.\d{4,5}(v\d+)?\b"),
    "a work key": re.compile(r"\b[A-Z][a-z]+_\d{4}_[a-z0-9-]+"),
}


def _seeds_in(text):
    return [name for name, rx in SEED_SHAPES.items() if rx.search(text)]


def test_the_scout_prompt_template_names_no_work():
    assert PROMPT_DOC.exists(), PROMPT_DOC
    found = _seeds_in(PROMPT_DOC.read_text(encoding="utf-8"))
    assert not found, f"{PROMPT_DOC.name} seeds the scout with {', '.join(found)}"


@pytest.mark.parametrize("seed", [
    "  a. ref: 10.1109/tgrs.2017.2719738 - expect robustness to noisy labels",
    "  a. ref: arXiv 1706.05587 - expect atrous convolution helps",
    "  a. work key Kaiser_2017_learning-aerial-image-segmentation",
])
def test_a_prompt_naming_a_work_is_refused(seed):
    """The mutation, proven to FIRE. The real document passing is not evidence that the check
    works; three seeded copies of it failing is. Each line is the shape proving run 2's prompt
    actually used (Scripts/scratch/proving_run2_prompt.md, STEP 2)."""
    mutated = PROMPT_DOC.read_text(encoding="utf-8") + "\n" + seed + "\n"
    assert _seeds_in(mutated), f"the guard did not fire on {seed!r}"


# ── the run driver ────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def driver():
    spec = importlib.util.spec_from_file_location("litkb_scout_run", DRIVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fake_rows(n=3, **over):
    out = []
    for i in range(n):
        r = dict(GOOD_DROPOFF, **over)
        r["id"] = f"hr-{i}"
        r["ref"] = f"10.1/{i}"
        out.append(r)
    return out


def fake_manifest(tmp_path, **over):
    m = {"db": "litkb_test", "reader_role": "litkb_test", "frozen_at": BEFORE,
         "repo": str(tmp_path), "worktree": str(tmp_path), "spend": False,
         "workstream_slug": "scout-test", "workstream_id": "ws-1",
         "run_csv": str(tmp_path / "run.csv"), "log": str(tmp_path / "log.jsonl")}
    m.update(over)
    return m


def test_the_driver_passes_the_scheme_and_the_request_id_through(driver, tmp_path):
    """The scheme travels from the drop-off ROW. A driver that re-classified the string would be
    a second home for the fact the `ref-scheme-mismatch` refusal exists to surface."""
    seen = []

    def hunt(ref, **kw):
        seen.append((ref, kw))
        return {"ok": True, "state": "extracted"}

    driver.run(fake_manifest(tmp_path), tmp_path / "run.csv", hunt=hunt, rows=fake_rows(3))
    assert [r for r, _ in seen] == ["10.1/0", "10.1/1", "10.1/2"]
    assert [kw["ref_scheme"] for _, kw in seen] == ["doi"] * 3
    assert [kw["hunt_request_id"] for _, kw in seen] == ["hr-0", "hr-1", "hr-2"]
    assert all(kw["spend"] is False for _, kw in seen)
    # the row's claimed_* fields are NOT re-sent: given the id, hunt fills them from the row
    # itself (`litkb.hunt.fill_from_request`), and an explicit kwarg would override that path
    # and bypass the blank-column guard (merge of the S1 builders, 2026-09-20)
    assert all(not ({"title", "author", "year"} & kw.keys()) for _, kw in seen)


def test_the_driver_never_spends_even_when_the_manifest_omits_the_key(driver, tmp_path):
    """`spend` defaults to False when the key is absent: a manifest missing the field must not
    fall through to hunt's own default, which is True and acquires."""
    seen = []
    m = fake_manifest(tmp_path)
    m.pop("spend")

    def hunt(ref, **kw):
        seen.append(kw)
        return {"ok": True, "state": "extracted"}

    driver.run(m, tmp_path / "run.csv", rows=fake_rows(1), hunt=hunt)
    assert seen[0]["spend"] is False


def test_the_driver_is_resumable_and_does_not_rehunt(driver, tmp_path):
    calls = []

    def hunt(ref, **kw):
        calls.append(ref)
        return {"ok": True, "state": "extracted"}

    rows, out = fake_rows(3), tmp_path / "run.csv"
    driver.run(fake_manifest(tmp_path), out, hunt=hunt, rows=rows, limit=2)
    assert len(calls) == 2
    n_new, n_resumed, written = driver.run(fake_manifest(tmp_path), out, hunt=hunt, rows=rows)
    assert (n_new, n_resumed, len(written)) == (1, 2, 3)
    assert len(calls) == 3, calls
    assert [r["hr_id"] for r in written] == ["hr-0", "hr-1", "hr-2"]


def test_a_raising_hunt_becomes_an_error_row_not_a_dead_run(driver, tmp_path):
    def hunt(ref, **kw):
        raise RuntimeError("the database went away")

    _n, _s, written = driver.run(fake_manifest(tmp_path), tmp_path / "run.csv",
                                 hunt=hunt, rows=fake_rows(2))
    assert [r["hunt_state_or_refusal"] for r in written] == ["error", "error"]
    assert [r["hunt_ok"] for r in written] == ["false", "false"]
    assert "the database went away" in written[0]["message"]


def test_a_refusal_is_recorded_as_its_code(driver, tmp_path):
    def hunt(ref, **kw):
        return {"ok": False, "refused": "malformed-ref", "message": "not a DOI"}

    _n, _s, written = driver.run(fake_manifest(tmp_path), tmp_path / "run.csv",
                                 hunt=hunt, rows=fake_rows(1))
    assert written[0]["hunt_state_or_refusal"] == "malformed-ref"
    assert written[0]["hunt_ok"] == "false"


def test_the_driver_records_the_fields_a_dropoff_is_missing(driver, tmp_path):
    rows = fake_rows(1, abstract_passage=None, claimed_authors="")
    _n, _s, written = driver.run(fake_manifest(tmp_path), tmp_path / "run.csv",
                                 hunt=lambda ref, **kw: {"ok": True, "state": "extracted"},
                                 rows=rows)
    assert written[0]["fields_missing"] == "claimed_authors;abstract_passage"


def test_the_driver_writes_the_header_even_with_no_dropoffs(driver, mod, tmp_path):
    """A run that discovered nothing still leaves a readable ledger, so `missing_hunt_results`
    can be zero-of-zero rather than a missing file."""
    out = tmp_path / "run.csv"
    driver.run(fake_manifest(tmp_path), out, hunt=lambda *a, **k: {}, rows=[])
    assert out.read_text(encoding="utf-8").strip() == ",".join(mod.RUN_CSV_COLUMNS)


# ── the nightly soak ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def soak():
    pytest.importorskip("litkb", reason="litkb imports only with PYTHONPATH=pipeline")
    from litkb.ops import nightly_soak
    return nightly_soak


SOAK_ROW = {"ts_utc": "2026-09-20T03:17:00Z", "host": "h", "repo_head": "0" * 40,
            "migration_tip": "26", "search_ok": "true", "search_ms": 12, "search_hits": 5,
            "hunt_ok": "true", "hunt_ms": 30, "hunt_state": "extracted", "hunt_key": "K",
            "doctor_ok": "", "doctor_detail": "", "error": ""}


def test_the_soak_csv_path_is_inside_the_repo(soak):
    """`parents[4]` is counted by the code and asserted here, not counted in a comment."""
    assert soak.SOAK_CSV == SCRIPTS.parent / "Reports" / "LITKB_SOAK.csv"
    assert (soak.REPO_ROOT / "Scripts").is_dir(), "REPO_ROOT is not the repository root"


def test_the_row_writer_appends_exactly_one_row_with_the_fixed_header(soak, tmp_path):
    p = tmp_path / "Reports" / "LITKB_SOAK.csv"
    soak.append_row(SOAK_ROW, path=p, repo=tmp_path)
    soak.append_row(dict(SOAK_ROW, ts_utc="2026-09-21T03:17:00Z"), path=p, repo=tmp_path)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == ",".join(soak.COLUMNS)
    assert len(lines) == 3, lines
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["ts_utc"] for r in rows] == ["2026-09-20T03:17:00Z", "2026-09-21T03:17:00Z"]


def test_the_header_carries_the_doctor_columns_s7_will_fill(soak):
    """S7's `soak` subcommand reads every night from S1 onward. A column added later would split
    the log in two, and the first nights would be the unreadable half."""
    assert soak.COLUMNS == ("ts_utc", "host", "repo_head", "migration_tip", "search_ok",
                            "search_ms", "search_hits", "hunt_ok", "hunt_ms", "hunt_state",
                            "hunt_key", "doctor_ok", "doctor_detail", "error")


def test_a_soak_csv_outside_the_repo_is_refused(soak, tmp_path):
    """`--csv` would otherwise be an unbounded write primitive in a job that runs unattended
    every night as the logged-in user."""
    outside = tmp_path.parent / "elsewhere.csv"
    with pytest.raises(SystemExit) as e:
        soak.append_row(SOAK_ROW, path=outside)
    assert "outside the repository" in str(e.value)
    assert not outside.exists()


@pytest.fixture
def soak_env(tmp_path, monkeypatch):
    """Contain `run()`'s environment writes.

    `nightly_soak.run()` sets LITKB_DB and LITKB_WORKTREE in `os.environ` on purpose — it is a
    scheduled entry point, and `_search` and `hunt` read both — but a TEST that let those writes
    escape would hand them to every later test in the session, INCLUDING the ones that spawn a
    real MCP server as a subprocess and inherit the environment. That is not hypothetical: it was
    measured here on 2026-09-20. These two tests leaked `LITKB_DB=litkb_test`, and
    `qc/test_litkb_p8.py::test_a_tool_result_is_json_over_a_real_session` — green on its own —
    failed inside the full `check.py` suite with `fe_sendauth: no password supplied`, because the
    server it spawned tried to connect as `litkb_reader` to a database pgpass has no line for.
    The refusal looked like a defect in litkb_work and was a defect in this file.

    monkeypatch.setenv records each key's pre-test value, so the teardown undoes `run()`'s later
    overwrite as well as this one. It is the same rule `qc/conftest.py` enforces for the lake.
    """
    monkeypatch.setenv("LITKB_DB", "litkb_test")
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    return tmp_path


def test_a_failing_search_still_writes_a_row_and_exits_non_zero(soak, soak_env, tmp_path,
                                                                monkeypatch):
    p = tmp_path / "Reports" / "soak.csv"
    monkeypatch.setattr(soak, "smoke_search", lambda *a, **k: (False, 41, 0, "no block"))
    monkeypatch.setattr(soak, "smoke_hunt", lambda *a, **k: (True, 12, "extracted", ""))
    monkeypatch.setattr(soak, "migration_tip", lambda *a, **k: "26")
    monkeypatch.setattr(soak, "repo_head", lambda *a, **k: "0" * 40)
    code = soak.run(db="litkb_test", path=p, repo=tmp_path)
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert code == 1
    assert len(rows) == 1
    assert rows[0]["search_ok"] == "false" and rows[0]["error"] == "search: no block"


def test_a_known_extracted_key_coming_back_held_is_not_ok(soak, soak_env, tmp_path, monkeypatch):
    """The regression the soak exists for. `hunt` returns `ok: true` when it correctly reports a
    database that has lost the work, so `hunt_ok` may not simply be `res["ok"]`."""
    import litkb.hunt as H

    p = tmp_path / "Reports" / "soak.csv"
    monkeypatch.setattr(soak, "smoke_search", lambda *a, **k: (True, 10, 5, ""))
    monkeypatch.setattr(soak, "migration_tip", lambda *a, **k: "26")
    monkeypatch.setattr(soak, "repo_head", lambda *a, **k: "0" * 40)
    monkeypatch.setattr(H, "hunt", lambda *a, **k: {"ok": True, "state": "held"})
    code = soak.run(db="litkb_test", path=p, repo=tmp_path)
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert code == 1
    assert rows[0]["hunt_ok"] == "false" and rows[0]["hunt_state"] == "held"
    assert "known-extracted" in rows[0]["error"]


def test_an_unreadable_migration_tip_is_blank_not_the_on_disk_tip(soak):
    """"what the repository holds" and "what the database has applied" are different facts, and
    S7 compares them. Substituting one for the other would make that comparison always pass."""
    assert soak.migration_tip("no_such_database_at_all") == ""

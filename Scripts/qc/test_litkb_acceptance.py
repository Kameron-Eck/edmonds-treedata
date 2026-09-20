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

The git queries are injected (`_worktree_list`, `_rev_parse` on the module), so parity is
exercised with no second remote and no network. Nothing here writes outside tmp_path, and no
`.litkb-workstream*` file is ever committed — the token fixtures are created at run time, hold
six bytes of non-secret filler, and live only in tmp_path.

Run:
  cd Scripts && PYTHONUTF8=1 py -3.12 -m pytest qc/test_litkb_acceptance.py -q
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
INSTRUMENT = SCRIPTS / "qc" / "instruments" / "litkb_acceptance.py"
DATA = SCRIPTS / "qc" / "testdata" / "litkb_acceptance"
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
    the raw strings would report every surviving checkout as unexpected."""
    m, path = manifest_for(tmp_path)
    odd = str(tmp_path / "wt-kept").replace(os.sep, "/").upper()
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
    vault file, so a secret cannot reach stdout, a log or a traceback through it."""
    m, path = manifest_for(tmp_path)
    opened = []
    real_open = open

    def watched(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", watched)
    patch_git(mod, monkeypatch, [m["repo"], str(tmp_path / "wt-kept")], ONE_HASH)
    mod.main(["disposition", "--manifest", str(path)])
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

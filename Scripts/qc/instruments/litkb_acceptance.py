r"""The acceptance instrument for the litkb work plan: a session's "done" is a COMMAND.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py plan
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py plan --file LITKB_WORKPLAN.md
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py disposition --manifest frozen.json
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py guard-checkout --path <wt> --vault <dir>

WHY THIS EXISTS. A multi-session plan whose sessions are graded by their own author's prose is
not graded at all. Every subcommand here reads a document or a manifest FROZEN BEFORE the work,
prints one line of NAMED COUNTERS, and exits 0 only when every counter meets its bound — so a
cold session can verify a session it did not run, without trusting that session's report. The
counters are the contract; the stderr offences are there to make a non-zero count actionable.

CLAUDE.md 3.4c: a gate that has never fired is not a gate. Every check below has a known-bad
input in qc/test_litkb_acceptance.py that makes it fail, and the known-bads are real mutations of
the real fixtures, not assertions about the code.

SUBCOMMANDS THAT EXIST TODAY. `plan` (does the work plan still grade itself) and `disposition`
(did the worktree disposition actually happen), both landing with session S0. `scout`,
`first-work`, `edges`, `readability`, `run`, `synthesis` and `soak` land with their own sessions
and are deliberately absent until then — an acceptance command that cannot fail is worse than no
command. `guard-checkout` is not a session gate: it is the safety interlock the owner runs BEFORE
removing any checkout.

WHAT `plan` COUNTS, and the choices inside each count, because every one of them is a choice:

  SESSION BLOCK. A line matching `### S<n>` starts one; the next markdown heading of level 1-3,
  or end of file, ends it. Deeper headings (`####`) stay inside the block. The session's NAME for
  reporting is `S<n>`.

  DONE-STATE. The (a)/(b)/(c) bullets count only AFTER a line whose text begins `Done-state`
  inside that block — a `- (a)` bullet under Work does not satisfy the done-state. A block with
  no `Done-state` line is missing all three.

  sessions_missing_abc counts SESSIONS, not bullets: a block missing both (b) and (c) adds ONE to
  the counter and TWO lines to stderr.

  unresolved_decision_ids counts DISTINCT ids: a backticked `litkb-…` token anywhere in the file
  that has no `  - id: <id>` line in decisions.yaml. Distinct, because the plan cites the same
  ruling from several sessions on purpose and one missing ruling is one defect.

  THE DATED REGION. Everything between `<!-- drift-gate:dated-begin -->` and its `-end` marker is
  a dated record, not a current claim: it is blanked (line for line, so nothing else shifts)
  before BOTH scans. An unclosed begin marker blanks to end of file — fail-open on ids there
  would be the wrong way round, but a dated appendix that never ends is a document defect the
  drift gate owns, not a reason for this instrument to grade a historical survey.

WHAT `disposition` COUNTS. The manifest is frozen before the disposition runs; the counters ask
whether the world matches it. `unexpected_worktrees` — a checkout `git worktree list --porcelain`
still reports that the manifest does not list (the main checkout always counts as expected).
`branches_not_at_parity` — a disposed branch whose local hash differs from `github/<branch>`, an
unresolvable ref counting as not-at-parity. `missing_evidence` — a repo-relative path the
manifest promises that is not on disk. `token_vault_mismatches` — a workstream token whose vault
file is absent, empty, or resolves outside the vault directory.

TOKENS ARE NEVER READ HERE. Existence, size and containment only; offences name the slug and the
file name, never a byte of content. `guard-checkout` does hash token files, and prints the file
NAME and nothing else — not the hash, which is itself a value derived from a secret.

The git queries are the two module-level functions `_worktree_list` and `_rev_parse`, injected
into the checker so the tests can exercise parity without a second remote.

Stdlib only; reads only; writes no file and touches no database. It is not run on Colab, so it
does not filter an injected `-f` argument (CLAUDE.md 3.10 applies to the Colab entry points).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

#: parents[2] is `Scripts` (this file is qc/instruments/…). Defaults resolve from the
#: instrument's own location, never from the working directory: a gate that grades a different
#: file depending on where it was invoked grades nothing.
SCRIPTS = Path(__file__).resolve().parents[2]
PLAN_DEFAULT = SCRIPTS / "LITKB_WORKPLAN.md"
DECISIONS_DEFAULT = SCRIPTS / "decisions.yaml"

SESSION_HEAD = re.compile(r"^###\s+S(\d+)\b")
#: a markdown heading of level 1-3 closes a session block; `####` and deeper stay inside it
BLOCK_END = re.compile(r"^#{1,3}\s")
DONE_STATE = re.compile(r"^\s*\**Done-state\b")
ABC_BULLET = re.compile(r"^\s*-\s*\(([abc])\)")
DECISION_TOKEN = re.compile(r"`(litkb-[a-z0-9-]+)`")
DECISION_ID_LINE = re.compile(r"^\s{2}-\s+id:\s*(\S+)\s*$")
DATED_BEGIN = "<!-- drift-gate:dated-begin -->"
DATED_END = "<!-- drift-gate:dated-end -->"


def read_text(path):
    """utf-8, universal newlines. decisions.yaml is CRLF on this machine and the plan is not;
    a scan that saw a stray `\\r` on the end of every id would report every id unresolved."""
    return Path(path).read_text(encoding="utf-8")


# ── plan ──────────────────────────────────────────────────────────────────────────────────

def blank_dated_region(text):
    """Replace every line of the dated appendix with an empty line, markers included.

    Line-for-line so the surviving text keeps its line numbers, and so a session heading cannot
    be silently glued to the block above it by the deletion.
    """
    out, inside = [], False
    for line in text.splitlines():
        if DATED_BEGIN in line:
            inside = True
        if inside:
            out.append("")
        else:
            out.append(line)
        if DATED_END in line:
            inside = False
    return "\n".join(out)


def session_blocks(text):
    """[(name, [lines])] — one entry per `### S<n>` heading, in document order."""
    lines = text.splitlines()
    starts = [(i, m.group(1)) for i, line in enumerate(lines)
              if (m := SESSION_HEAD.match(line))]
    blocks = []
    for pos, (i, num) in enumerate(starts):
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if BLOCK_END.match(lines[j]):
                end = j
                break
        if pos + 1 < len(starts):
            end = min(end, starts[pos + 1][0])
        blocks.append((f"S{num}", lines[i + 1:end]))
    return blocks


def missing_abc(block_lines):
    """The (a)/(b)/(c) letters absent from this block's done-state, in order."""
    try:
        start = next(i for i, line in enumerate(block_lines) if DONE_STATE.match(line))
    except StopIteration:
        return ["a", "b", "c"]
    seen = {m.group(1) for line in block_lines[start + 1:] if (m := ABC_BULLET.match(line))}
    return [letter for letter in ("a", "b", "c") if letter not in seen]


def decision_ids(yaml_text):
    """Every `  - id: <id>` in decisions.yaml. Authored registry, read as text on purpose: this
    instrument is stdlib-only and must run on a machine with no yaml package installed."""
    return {m.group(1) for line in yaml_text.splitlines()
            if (m := DECISION_ID_LINE.match(line))}


def cited_ids(text):
    """Distinct backticked `litkb-…` tokens, sorted, so stderr is deterministic."""
    return sorted(set(DECISION_TOKEN.findall(text)))


def check_plan(plan_text, decisions_text):
    """(sessions_missing_abc, unresolved_decision_ids, [offence lines])."""
    text = blank_dated_region(plan_text)
    offences, n_sessions = [], 0
    for name, block in session_blocks(text):
        gaps = missing_abc(block)
        if gaps:
            n_sessions += 1
            offences += [f"{name}: missing ({letter})" for letter in gaps]
    known = decision_ids(decisions_text)
    unresolved = [i for i in cited_ids(text) if i not in known]
    offences += [f"unresolved id: {i}" for i in unresolved]
    return n_sessions, len(unresolved), offences


def cmd_plan(args):
    missing, unresolved, offences = check_plan(read_text(args.file), read_text(args.decisions))
    for line in offences:
        print(line, file=sys.stderr)
    print(f"sessions_missing_abc={missing} unresolved_decision_ids={unresolved}")
    return 0 if missing == 0 and unresolved == 0 else 1


# ── disposition ───────────────────────────────────────────────────────────────────────────

def _git(repo, *argv):
    """stdout of a read-only git query, or None if git failed. Never raises on a bad ref."""
    try:
        r = subprocess.run(["git", "-C", str(repo), *argv],
                           capture_output=True, text=True, errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _worktree_list(repo):
    """Absolute paths of every checkout git reports for this repository. Injection seam."""
    out = _git(repo, "worktree", "list", "--porcelain")
    if out is None:
        return []
    return [line.split(" ", 1)[1].strip()
            for line in out.splitlines() if line.startswith("worktree ")]


def _rev_parse(repo, ref):
    """The commit a ref names, or None when it does not resolve. Injection seam."""
    out = _git(repo, "rev-parse", ref)
    return out.strip() if out else None


def _key(path):
    """Compare checkouts as paths, not as strings: Windows mixes separators and case, and the
    porcelain output is not normalised. No `resolve()` — a manifest is checked against what git
    reports, and resolving would need both sides to exist on this disk."""
    return os.path.normcase(os.path.normpath(str(path)))


def check_disposition(manifest, repo=None, worktree_list=None, rev_parse=None):
    """(counters dict, [offence lines]). The two git queries are parameters so the parity check
    can be exercised without a second remote."""
    worktree_list = worktree_list or _worktree_list
    rev_parse = rev_parse or _rev_parse
    repo = repo or manifest["repo"]
    offences = []

    expected = {_key(p) for p in manifest.get("expected_worktrees", [])}
    expected.add(_key(repo))            # the main checkout is always expected
    unexpected = [w for w in worktree_list(repo) if _key(w) not in expected]
    offences += [f"unexpected worktree: {w}" for w in unexpected]

    not_parity = []
    for branch in manifest.get("disposed_branches", []):
        local, remote = rev_parse(repo, branch), rev_parse(repo, f"github/{branch}")
        if local is None or remote is None or local != remote:
            not_parity.append(branch)
            offences.append(f"not at parity with github: {branch} "
                            f"({local or 'unresolved'} vs {remote or 'unresolved'})")

    missing = [rel for rel in manifest.get("evidence", [])
               if not (Path(repo) / rel).exists()]
    offences += [f"missing evidence: {rel}" for rel in missing]

    vault = Path(manifest.get("vault", ""))
    bad_tokens = []
    for token in manifest.get("tokens", []):
        slug, name = token.get("slug", ""), token.get("vault_file", "")
        path = vault / name
        # containment, then existence, then non-empty. Never opened: the vault holds workstream
        # tokens and this instrument has no reason to read one.
        try:
            inside = _key(path).startswith(_key(vault) + os.sep) or _key(path) == _key(vault)
        except (OSError, ValueError):
            inside = False
        if not inside:
            bad_tokens.append(slug)
            offences.append(f"token vault mismatch: {slug} ({name} escapes the vault)")
        elif not path.is_file():
            bad_tokens.append(slug)
            offences.append(f"token vault mismatch: {slug} ({name} absent from the vault)")
        elif path.stat().st_size == 0:
            bad_tokens.append(slug)
            offences.append(f"token vault mismatch: {slug} ({name} is empty)")

    return ({"unexpected_worktrees": len(unexpected),
             "branches_not_at_parity": len(not_parity),
             "missing_evidence": len(missing),
             "token_vault_mismatches": len(bad_tokens)}, offences)


def cmd_disposition(args):
    manifest = json.loads(read_text(args.manifest))
    counters, offences = check_disposition(manifest)
    for line in offences:
        print(line, file=sys.stderr)
    print(" ".join(f"{k}={v}" for k, v in counters.items()))
    return 0 if not any(counters.values()) else 1


# ── guard-checkout ────────────────────────────────────────────────────────────────────────

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def vault_hashes(vault):
    """sha256 of every file in the vault. A missing vault is an EMPTY set, not an error: the
    guard fails closed, because "the vault is not there" and "the token is not in it" are the
    same fact from the point of view of a checkout about to be removed."""
    vault = Path(vault)
    if not vault.is_dir():
        return set()
    return {_sha256(p) for p in vault.rglob("*") if p.is_file()}


def guard_checkout(path, vault):
    """(ok, [refusal lines]) — refuse unless every `.litkb-workstream*` file at the checkout root
    has its bytes in the vault. Refusals name the FILE and nothing else."""
    root = Path(path)
    tokens = sorted(p for p in root.glob(".litkb-workstream*") if p.is_file())
    if not tokens:
        return True, []
    known = vault_hashes(vault)
    refusals = [f"refused: {p.name} not vaulted" for p in tokens if _sha256(p) not in known]
    return not refusals, refusals


def cmd_guard_checkout(args):
    root = Path(args.path)
    if not root.is_dir():
        print(f"no such checkout: {root}", file=sys.stderr)
        return 1
    ok, refusals = guard_checkout(root, args.vault)
    for line in refusals:
        print(line, file=sys.stderr)
    if ok:
        print(f"guard-checkout: ok {root}")
        return 0
    return 2


# ── cli ───────────────────────────────────────────────────────────────────────────────────

def build_parser():
    ap = argparse.ArgumentParser(
        description="acceptance counters for the litkb work plan (one subcommand per session)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="does the work plan still grade itself")
    p.add_argument("--file", default=str(PLAN_DEFAULT), help="the work plan (default: %(default)s)")
    p.add_argument("--decisions", default=str(DECISIONS_DEFAULT),
                   help="the decision registry (default: %(default)s)")
    p.set_defaults(func=cmd_plan)

    d = sub.add_parser("disposition", help="did the worktree disposition actually happen")
    d.add_argument("--manifest", required=True, help="the manifest frozen before the disposition")
    d.set_defaults(func=cmd_disposition)

    g = sub.add_parser("guard-checkout",
                       help="refuse to remove a checkout whose workstream token is not vaulted")
    g.add_argument("--path", required=True, help="the checkout root about to be removed")
    g.add_argument("--vault", required=True, help="the token vault directory")
    g.set_defaults(func=cmd_guard_checkout)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

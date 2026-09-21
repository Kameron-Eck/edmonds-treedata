r"""The acceptance instrument for the litkb work plan: a session's "done" is a COMMAND.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py plan
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py plan --file LITKB_WORKPLAN.md
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py disposition --manifest frozen.json
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py guard-checkout --path <wt> --vault <dir>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py scout --freeze --workstream scout-1 \
        --topic "…" --launch-cmd "…" --log <run.jsonl> --out <manifest.json>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py scout --manifest <manifest.json>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py first-work --freeze \
        --workstream <slug> [--hunt-request <id>] [--log <run.jsonl>] --out <manifest.json>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py first-work --manifest <manifest.json> \
        [--review <md> --codex-report <report.json>]
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py codex --review <md> --context <md> \
        --report <report.json> [--mutate N]

WHY THIS EXISTS. A multi-session plan whose sessions are graded by their own author's prose is
not graded at all. Every subcommand here reads a document or a manifest FROZEN BEFORE the work,
prints one line of NAMED COUNTERS, and exits 0 only when every counter meets its bound — so a
cold session can verify a session it did not run, without trusting that session's report. The
counters are the contract; the stderr offences are there to make a non-zero count actionable.

CLAUDE.md 3.4c: a gate that has never fired is not a gate. Every check below has a known-bad
input in qc/test_litkb_acceptance.py that makes it fail, and the known-bads are real mutations of
the real fixtures, not assertions about the code.

SUBCOMMANDS THAT EXIST TODAY. `plan` (does the work plan still grade itself) and `disposition`
(did the worktree disposition actually happen), both landing with session S0; `scout` (did the
discovery run actually discover), landing with S1; `codex` (did the adversarial read actually
read every citation), landing between S1 and S2 with the Codex stage it grades; `first-work` (did
ONE genuinely unknown work cross the whole loop unaided), landing with S2. `edges`, `readability`,
`run`, `synthesis` and `soak` land with their own sessions and are deliberately absent until then
— an acceptance command that cannot fail is worse than no command. `guard-checkout` is not a
session gate: it is the safety interlock the owner runs BEFORE removing any checkout. `preflight`
is not one either: it is what a session runs before its FIRST hunt.

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

WHAT `scout` COUNTS, and the two halves it reads. A discovery run is graded against a manifest
FROZEN BEFORE IT (`scout --freeze`): repo HEAD, the migration tips, the workstream, the baseline
`hunt_requests` count in it, the launch command verbatim, the log path and the UTC freeze time.
`scout --manifest` then reads three sources and exits 0 only when every bound holds:

  the DATABASE   `dropoffs` (hunt_requests in that workstream created AFTER the freeze; >= 10),
                 `missing_required_fields` (a drop-off with any of the eight REQUIRED fields null
                 or blank) and `ref_scheme_outside_set` (a scheme outside ALLOWED_SCHEMES).
  the DRIVER CSV `missing_hunt_results` (a drop-off with no row in it) and `unknown_states`
                 (a state outside CLOSED_STATES).
  the LOG        `human_input_events` and `stated_reason`.

THE VOCABULARY AND THE FIELD SET ARE MODULE CONSTANTS, NOT MANIFEST FIELDS, and the manifest
records them only so a reader can see what the run was graded against. The manifest is written by
the session being graded; a gate whose vocabulary that session could widen grades nothing.

`human_input_events` is defined HERE, before any run, from the headless `--output-format
stream-json` log: the `permission_denials` entries on the final `result` message, plus every
`AskUserQuestion` tool_use anywhere in the log, plus 1 when `result.subtype` is not `"success"`.
The three key names were read off a real 1-turn probe of this CLI (`claude -p … --output-format
json`), not assumed. `stated_reason` is 1 when the log's final text carries a `SCOUT-STOP:` line;
it is NOT a bound for a real run — the nonsense-topic run is what reads it, because that run's
whole result is `n=0` with a reason.

Since S3 an unexpected exception is `state: "crashed"` with `reason: "<stage>:<Exception>"` —
a NAMED state, so it is inside `CLOSED_STATES`; the `edges` grader counts it under `tracebacks`
rather than `unknown_states`, so a driver that crashed on every row still cannot pass.

WHAT `first-work` COUNTS (S2), and every choice inside it. S2's claim is that ONE genuinely
unknown work crossed admission, acquisition, extraction, workstream visibility, recording and
review WITH NO OPERATOR REPAIR. `first-work --freeze` writes the baseline BEFORE the run — repo
HEAD, the two migration tips, the workstream, the freeze instant, the optional hunt_request the
run is following up, and six BASELINE COUNTS, each with the SQL text that produced it under the
manifest's `queries` key so a reader can see what was counted rather than trust a number.

THE FREEZE INSTANT IS THE DATABASE'S CLOCK (`baseline_snapshot`, and `frozen_at_source: "db"` in
the manifest says so). It and the six counts are read in ONE repeatable-read transaction, so
`frozen_at` is exactly the moment of the snapshot they were counted from. Every timestamp it is
later compared against — `works.created_at`, `file_versions.created_at`, `use_versions.created_at`
— defaults to that same server's `now()`, and a workstation clock agrees with it only by
coincidence: one seconds ahead would freeze at an instant later than rows the baseline had already
counted, and each of those would then score as a NEW work.

`first-work --manifest` then prints seven counters:

  new_works       works whose identity row was created IN this workstream AFTER the freeze
                  (`litkb.works.created_in_ws` + `created_at`, not a version: a work is admitted
                  once and edited many times, and an edit is not a new work). The bound is `== 1`,
                  NOT `>= 1`. One work is the whole of S2 — a bounded proving run, sized so that
                  every rung below can be read off a single chain — and a run that admitted three
                  is a run whose other two counters no longer describe anything in particular.
  bound           of those, works the workstream sees with an active file. Read through
                  `litkb.hunt.look_up`, by one of the work's own active identifiers, because that
                  function IS the four-state ladder (`absent` / `held` / `bound-unextracted` /
                  `extracted`) and a second copy of it here would be a second definition of
                  "extracted". `litkb_work`'s ladder in `mcp/server.py` is the same three lines
                  over `main_files`; this path must use the workstream's view, because a URL
                  source is a PROPOSAL and main holds nothing for it until a second session
                  approves it.
  extracted       of those, the ones that ladder answers `extracted` for — a file with a current
                  extraction run. A run that produced zero blocks still counts as extracted and
                  falls out at `searchable` instead: "the extractor ran and found nothing" and
                  "the extractor never ran" are different problems.
  searchable      of those, works with at least one block VISIBLE TO SEARCH from this workstream.
                  The predicate is `mcp/server._BLOCK_FROM` itself — the fragment the search tool
                  runs, carrying `visibility.FILE_JOIN` and the current-run join — with the
                  server's own `DEFAULT_KINDS`, so a work whose only blocks are running heads and
                  page numbers does NOT count. Nothing here restates that join.
  verified_uses   use versions written in this workstream after the freeze that carry at least one
                  evidence row with `quote_verified` — the DATABASE's verdict, set by the trigger
                  of migrations 0007/0026 when it re-reads the span, never this instrument's and
                  never the session's. Bound `>= 1`: S2 asks for one verified use, and a run that
                  recorded two has not done anything wrong.
  claims_ungraded citations of the review that have no verdict row in the Codex report. The
                  citations come from `litkb.review_check.citations`, the grammar's own parser,
                  by way of the same rule `check_codex` applies: a row counts as a verdict for
                  citation *i* only when the report has a row `n = i` AND that row's `block_id` is
                  the one the citation names. Bound `== 0`. WITH NO REVIEW AND NO REPORT IT IS
                  NOT 0: with a review and no report it is that review's citation count, and with
                  no review at all it is 1, because "nothing was graded" is a RED and a counter
                  that read 0 there would make a missing review look like a clean one.
  operator_interventions   the counter S2 exists for, defined here from FACTS rather than from a
                  session's account of its own run, and it is the SUM of four:
                    1. `human_input_events` from the headless log, when one is given — the same
                       `read_log` the scout uses, so permission denials, `AskUserQuestion` and a
                       `result.subtype` that is not `success` all count. With no log the term is 0
                       and the manifest says no log was read; the other three are database facts
                       and are always counted.
                    2. an `acquisition_attempts` row for the new work with `status = 'manual-step'`
                       (acquisition's own word for "no automated route landed it; fetch it by
                       hand") or `route` in MANUAL_ATTEMPT_ROUTES.
                    3. a file version of the new work whose `source_route` is in
                       MANUAL_FILE_ROUTES — what `acquire --from-file` writes (`browser`) and what
                       a file bound where it already lay writes (`held-in-place`).
                    4. every file this workstream bound after the freeze that
                       `litkb.acquire.events.bound_without_event` returns. A bound file with no
                       acquisition event is unaccounted-for BY DEFINITION, whether a hand put it
                       there or a code path forgot to record it, and those two are the same defect
                       from the point of view of a cold session asking where the file came from.
                  Bound `== 0`.

Exit 0 only when `new_works == 1 and bound == 1 and extracted == 1 and searchable == 1 and
verified_uses >= 1 and claims_ungraded == 0 and operator_interventions == 0`.

THE REPLAY IS THE KILL. A manifest frozen AFTER the work was admitted — the baseline snapshot
already holds it — scores `new_works = 0` and exits 1, which is the workplan's own (c) clause and
the reason the freeze instant is a manifest field rather than a runtime `now()`.

The git queries are the two module-level functions `_worktree_list` and `_rev_parse`, injected
into the checker so the tests can exercise parity without a second remote. The database read is
the module-level `_hunt_request_rows`, injected the same way.

`plan`, `disposition` and `guard-checkout` are stdlib-only, read-only, and touch no database.
`scout --freeze` WRITES its manifest and `scout` READS the litkb database, so psycopg and the
`litkb` package are imported lazily, inside the scout functions only: the other three subcommands
still run on a machine with neither installed, which is what keeps them usable from CI and from a
cold checkout. `first-work` is the same: `--freeze` writes its manifest, the check reads the
database, and psycopg, `litkb.hunt`, `litkb.acquire.events` and `litkb.mcp.server` are all
imported INSIDE the first-work functions. `codex` imports the `litkb` package too -- for the GRAMMAR's own citation parser,
`review_check.citations`, because a second citation regex here would be a second grammar -- and
imports it lazily for the same reason; it touches no database at all. `codex --mutate N` with no
`--report` WRITES the mutated review beside the original and is the one subcommand that writes a
file into a worktree. Nothing here ever writes to a database. It is not run on Colab, so it does not
filter an injected `-f` argument (CLAUDE.md 3.10 applies to the Colab entry points).
"""
import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
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


# ── scout ─────────────────────────────────────────────────────────────────────────────────

#: The eight fields a drop-off MUST carry. The database leaves `abstract_passage` nullable; the
#: scout's contract does not (.claude/skills/literature/SKILL.md, "Stage 1 — discover"), and this
#: is where that difference is enforced. Blank counts as missing: `claimed_authors = ""` passes
#: every CHECK the table has and tells the resolver nothing.
REQUIRED_FIELDS = ("ref", "ref_scheme", "claimed_title", "claimed_authors", "claimed_year",
                   "expected_claim", "why_relevant", "abstract_passage")

#: Narrower than `hunt_requests.ref_scheme`'s own CHECK (doi, arxiv, jstor, isbn, pmid, pmcid,
#: openalex, s2, handle, url, tracker, legacy_stem, other). These four are what the hunt that
#: follows a drop-off can resolve; the rest come back `unsupported-ref-scheme`.
ALLOWED_SCHEMES = ("doi", "arxiv", "url", "title")

#: Every value `hunt_state_or_refusal` may take — the word `litkb.hunt.ledger_word` writes for a
#: result. Since S3 it is DERIVED from the hunt's own vocabulary rather than retyped here:
#: `litkb.hunt.STATES` (the three ladder rungs plus the four ways a hunt stops short of one) and
#: every enumerable member of `litkb.hunt.REASONS`, which is where `REF_REFUSALS` and
#: `HUNT_REFUSALS` now live, as the reason classes of the `refused` state.
#:
#: `held-no-spend` is the one word that is neither: a deliberate no-spend stop is recorded as the
#: STOP, not as the rung it happens to be standing on, and the ledgers already written carry it.
#: `crashed` needs no reason added — its reason is a SHAPE (`<stage>:<ExceptionClass>`) that no
#: closed list can hold, so `ledger_word` records the state itself for it.
#: `absent` LEFT this list with S3: it is `litkb_work`'s miss rung and `hunt()` has never returned
#: it, so a checker accepting it held a slot no run could fill. `error` was never here and no
#: longer exists — the generic boundary answers `crashed` at a NAMED stage.
#:
#: `test_the_closed_vocabulary_matches_hunts_own` pins this against the module so it cannot drift.
#: It already had, twice: the S1 builders worked in parallel and left it one code short
#: (`unknown-ref-scheme`), and the first scout run (2026-09-20) found it ten short — every pre-S1
#: code, e.g. the `admission-refused` that arXiv's transient 406 produced.
def _closed_states():
    from litkb.hunt import REASONS, STATES

    words = list(STATES) + ["held-no-spend"]
    for state in STATES:
        words += [r for r in REASONS.get(state, ()) if r not in words]
    return tuple(words)


try:
    CLOSED_STATES = _closed_states()
except Exception:                   # noqa: BLE001 — importable without PYTHONPATH=pipeline
    # Five of the six subcommands need no litkb import, and the doc tests import this module only
    # to read its constants; a checker that refused to import would take those down with it. The
    # scout checker itself cannot run without litkb on the path in any case.
    CLOSED_STATES = ()

#: The CSV the driver (qc/instruments/litkb_scout_run.py) writes, and this checker reads.
RUN_CSV_COLUMNS = ("hr_id", "ref", "ref_scheme", "claimed_title", "claimed_year",
                   "fields_missing", "hunt_ok", "hunt_state_or_refusal", "message", "seconds")

STOP_LINE = "SCOUT-STOP:"


def _utc_now():
    return dt.datetime.now(dt.timezone.utc)


def _parse_utc(text):
    """An ISO-8601 instant as an AWARE datetime. `hunt_requests.created_at` is timestamptz, and a
    naive/aware comparison raises — or, worse, a naive one silently compares wall clocks and zeroes
    `dropoffs` on a machine that is not on UTC."""
    s = str(text).strip().replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _repo_root():
    """The repository root: `Scripts`'s parent. Resolved from this file, never from the cwd."""
    return SCRIPTS.parent


def _repo_head(repo):
    return (_rev_parse(repo, "HEAD") or "unresolved")


def repo_migration_tip():
    """The highest migration version ON DISK. Always readable; needs no credential."""
    try:
        from litkb.db import migrate
        found = migrate.discover()
    except Exception:                       # noqa: BLE001 — a tip we cannot read is recorded as null
        return None
    return max((row[0] for row in found), default=None)


def db_migration_tip(db, passfile=None):
    """(tip, note). The highest version APPLIED to `db`.

    `litkb_meta` is readable by `litkb_owner` alone — measured: litkb_reader and litkb_writer both
    get `permission denied for schema litkb_meta`, and litkb_ingest refuses the login outright. So
    this is an ADMIN read and it is allowed to fail: an unreadable tip is recorded as null with the
    reason beside it, never silently replaced by the on-disk tip, which is a different fact.
    """
    try:
        from litkb.db import connect as c
        if passfile:
            os.environ["PGPASSFILE"] = str(passfile)
        conn = c.connect_admin(db, c.OWNER, autocommit=True)
        try:
            return conn.execute("SELECT max(version) FROM litkb_meta.schema_migrations").fetchone()[0], None
        finally:
            conn.close()
    except Exception as e:                  # noqa: BLE001 — the reason is the useful half
        return None, f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"


def _connect(db, role, autocommit=True):
    from litkb.db import connect as c
    return c.connect(db, role, autocommit=autocommit)


def resolve_workstream(db, role, slug):
    """The OPEN workstream with this slug, or None. `workstreams_open_slug` is a UNIQUE index on
    slug WHERE state = 'open', so an open slug names exactly one row — which is why this resolves
    by slug at all rather than demanding the id be frozen."""
    conn = _connect(db, role)
    try:
        row = conn.execute("SELECT id FROM litkb.workstreams WHERE slug = %s AND state = 'open'",
                           (slug,)).fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()


def count_hunt_requests(db, role, ws_id):
    conn = _connect(db, role)
    try:
        return conn.execute("SELECT count(*) FROM litkb.hunt_requests WHERE workstream_id = %s",
                            (ws_id,)).fetchone()[0]
    finally:
        conn.close()


def _hunt_request_rows(db, role, ws_id, since):
    """[dict] — every drop-off in `ws_id` created strictly after `since` (an AWARE datetime),
    oldest first. Module-level so the tests can inject it; the real one opens a reader connection.
    """
    conn = _connect(db, role)
    try:
        cols = ("id", "ref", "ref_scheme", "claimed_title", "claimed_authors", "claimed_year",
                "expected_claim", "why_relevant", "abstract_passage", "created_at")
        rows = conn.execute(
            "SELECT id, ref, ref_scheme, claimed_title, claimed_authors, claimed_year, "
            "       expected_claim, why_relevant, abstract_passage, created_at "
            "  FROM litkb.hunt_requests WHERE workstream_id = %s AND created_at > %s "
            " ORDER BY created_at, id", (ws_id, since)).fetchall()
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def missing_fields(row):
    """The REQUIRED fields this drop-off leaves null or blank, in contract order."""
    out = []
    for f in REQUIRED_FIELDS:
        v = row.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            out.append(f)
    return out


def read_run_csv(path):
    """{hr_id: row} from the driver's CSV. A missing file is an EMPTY mapping, not an error: "the
    driver never ran" and "the driver skipped every row" must both land on `missing_hunt_results`,
    which names the drop-offs, rather than on a traceback that names nothing."""
    p = Path(path)
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8", newline="") as fh:
        return {str(r.get("hr_id", "")).strip(): r for r in csv.DictReader(fh)}


def read_log(path):
    """(human_input_events, stated_reason, [offence lines]) from a stream-json log.

    Definition fixed BEFORE any run (module docstring). Unparseable lines are skipped: the CLI
    interleaves nothing else on stdout today, but a log that gained a banner must not make the
    gate throw — it must still count what it can and say the log was unreadable if it found no
    result message at all.
    """
    p = Path(path)
    if not p.is_file():
        return 1, 0, [f"scout log missing: {p}"]
    events, stated, offences, saw_result = 0, 0, [], False
    # utf-8-sig: a log redirected by PowerShell's `>` starts with a BOM, which made the FIRST line
    # (the `system/init` message) unparseable and was silently skipped (S1, 2026-09-20). The
    # launch recipe now says bash, but the reader must not depend on it.
    for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(msg, dict):
            continue
        events += _ask_user_questions(msg)
        if msg.get("type") == "result":
            saw_result = True
            denials = msg.get("permission_denials") or []
            if denials:
                events += len(denials)
                offences.append(f"scout log: {len(denials)} permission denial(s)")
            subtype = msg.get("subtype")
            if subtype != "success":
                events += 1
                offences.append(f"scout log: result.subtype={subtype!r}, not 'success'")
            text = msg.get("result") or ""
            stated = 1 if any(ln.strip().startswith(STOP_LINE)
                              for ln in str(text).splitlines()) else 0
    if not saw_result:
        events += 1
        offences.append(f"scout log: no final `result` message in {p}")
    return events, stated, offences


def _ask_user_questions(msg):
    """Every AskUserQuestion tool_use in one stream-json message. The shape is
    {"message": {"content": [{"type": "tool_use", "name": …}, …]}} on an assistant message; this
    walks defensively because the gate must not depend on one CLI version's envelope."""
    content = (msg.get("message") or {}).get("content")
    if not isinstance(content, list):
        return 0
    return sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
               and b.get("name") == "AskUserQuestion")


def check_scout(manifest, rows=None, run_csv=None, log=None):
    """(counters dict, stated_reason, [offence lines]).

    `rows` is injected by the tests; the default reads the database the manifest names.
    """
    db = manifest["db"]
    role = manifest.get("reader_role") or "litkb_reader"
    ws_id = manifest.get("workstream_id")
    since = _parse_utc(manifest["frozen_at"])
    offences = []

    if rows is None:
        if not ws_id:
            ws_id = resolve_workstream(db, role, manifest["workstream_slug"])
        if not ws_id:
            offences.append(f"no OPEN workstream with slug {manifest['workstream_slug']!r} in {db}")
            rows = []
        else:
            rows = _hunt_request_rows(db, role, ws_id, since)

    # The drop-offs are the rows created AFTER the freeze. A manifest frozen after the run grades
    # nothing, and says so by counting zero.
    n_missing, n_scheme = 0, 0
    for r in rows:
        gaps = missing_fields(r)
        if gaps:
            n_missing += 1
            offences.append(f"drop-off {r.get('id')}: missing {', '.join(gaps)}")
        scheme = (r.get("ref_scheme") or "").strip()
        if scheme not in ALLOWED_SCHEMES:
            n_scheme += 1
            offences.append(f"drop-off {r.get('id')}: ref_scheme {scheme!r} outside "
                            f"{{{', '.join(ALLOWED_SCHEMES)}}}")

    results = read_run_csv(run_csv or manifest["run_csv"])
    n_noresult, n_unknown = 0, 0
    for r in rows:
        hit = results.get(str(r.get("id")))
        if hit is None:
            n_noresult += 1
            offences.append(f"drop-off {r.get('id')}: no row in the driver CSV")
            continue
        state = (hit.get("hunt_state_or_refusal") or "").strip()
        if state not in CLOSED_STATES:
            n_unknown += 1
            offences.append(f"drop-off {r.get('id')}: state {state!r} outside the closed vocabulary")

    events, stated, log_offences = read_log(log or manifest["log"])
    offences += log_offences

    return ({"dropoffs": len(rows),
             "missing_required_fields": n_missing,
             "ref_scheme_outside_set": n_scheme,
             "missing_hunt_results": n_noresult,
             "unknown_states": n_unknown,
             "human_input_events": events}, stated, offences)


#: The bounds. `dropoffs` is the only one that is a FLOOR; every other counter must be zero.
MIN_DROPOFFS = 10


def scout_ok(counters):
    return (counters["dropoffs"] >= MIN_DROPOFFS
            and not any(v for k, v in counters.items() if k != "dropoffs"))


def cmd_scout(args):
    if args.freeze:
        return _scout_freeze(args)
    manifest = json.loads(read_text(args.manifest))
    counters, stated, offences = check_scout(manifest, run_csv=args.csv, log=args.log)
    for line in offences:
        print(line, file=sys.stderr)
    print(" ".join(f"{k}={v}" for k, v in counters.items()) + f" stated_reason={stated}")
    return 0 if scout_ok(counters) else 1


def _scout_freeze(args):
    for required in ("workstream", "topic", "launch_cmd", "log", "out"):
        if not getattr(args, required):
            print(f"scout --freeze needs --{required.replace('_', '-')}", file=sys.stderr)
            return 2
    repo = Path(args.repo or _repo_root())
    role = args.role
    frozen_at = _utc_now()
    ws_id = resolve_workstream(args.db, role, args.workstream)
    baseline = count_hunt_requests(args.db, role, ws_id) if ws_id else 0
    db_tip, db_tip_note = db_migration_tip(args.db, args.passfile)
    run_csv = args.csv or str(
        repo / "Reports" / f"LITKB_SCOUT_RUN_{frozen_at.strftime('%Y-%m-%d')}.csv")
    manifest = {
        "kind": "litkb-scout",
        "frozen_at": frozen_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(repo),
        "repo_head": _repo_head(repo),
        "db": args.db,
        "reader_role": role,
        "repo_migration_tip": repo_migration_tip(),
        "db_migration_tip": db_tip,
        "db_migration_tip_note": db_tip_note,
        "workstream_slug": args.workstream,
        "workstream_id": ws_id,
        "baseline_hunt_requests": baseline,
        "topic": args.topic,
        "launch_cmd": args.launch_cmd,
        "log": str(args.log),
        "run_csv": run_csv,
        "worktree": str(args.worktree or repo),
        "spend": False,
        # recorded for the READER of the manifest; the checker uses the module constants, because
        # the session being graded writes this file (module docstring).
        "allowed_ref_schemes": list(ALLOWED_SCHEMES),
        "closed_states": list(CLOSED_STATES),
        "required_fields": list(REQUIRED_FIELDS),
        "min_dropoffs": MIN_DROPOFFS,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"frozen {out} workstream={args.workstream} id={ws_id} baseline={baseline} "
          f"head={manifest['repo_head'][:12]} repo_tip={manifest['repo_migration_tip']} "
          f"db_tip={db_tip}")
    return 0


# ── first-work: did ONE unknown work cross the whole loop unaided (S2) ────────────────────

#: An `acquisition_attempts.route` that means a HUMAN fetched the file and handed it in
#: (`litkb acquire --from-file`, and the `manual-step` instruction row acquisition writes when no
#: automated route landed anything). `hunt-url` is deliberately NOT here: it is the automated URL
#: fetch, and folding it in would make every hunted web source read as an intervention.
MANUAL_ATTEMPT_ROUTES = ("browser",)

#: A `file_versions.source_route` that means the same at the FILE. `browser` is what
#: `acquire --from-file` writes through `land_and_attach`; `held-in-place` is what
#: `acquire.run.attach_in_place` writes for a file that was already lying in a topic folder. Both
#: are a hand putting a file where the pipeline then found it.
MANUAL_FILE_ROUTES = ("browser", "held-in-place")

#: The baseline counts `--freeze` records, as {name: SQL}. The SQL TEXT goes into the manifest
#: (its `queries` key) with the number, because a baseline count whose query nobody can see is a
#: number a reader has to take on trust. Every one binds `%(ws)s` and nothing else.
BASELINE_QUERIES = {
    # main's works plus THIS workstream's proposals — `ws_works` is that view (migration 0004)
    "works": "SELECT count(*) FROM litkb.ws_works WHERE view_workstream_id = %(ws)s",
    "files": "SELECT count(*) FROM litkb.ws_files WHERE view_workstream_id = %(ws)s",
    # versions WRITTEN BY this workstream, which is what `bound_without_event` later scans
    "file_versions": "SELECT count(*) FROM litkb.file_versions WHERE workstream_id = %(ws)s",
    "blocks": ("SELECT count(*) FROM litkb.blocks b "
               "  JOIN litkb.ws_files f ON f.file_id = b.file_id AND f.current_run_id = b.run_id "
               " WHERE f.view_workstream_id = %(ws)s"),
    "uses": "SELECT count(*) FROM litkb.use_versions WHERE workstream_id = %(ws)s",
    "hunt_requests": "SELECT count(*) FROM litkb.hunt_requests WHERE workstream_id = %(ws)s",
}

#: Works ADMITTED in this workstream after the freeze. The identity row, not a version: a work is
#: admitted once and edited many times, and `works.created_in_ws` + `created_at` is the one place
#: that says when this workstream first brought it into existence.
NEW_WORKS_SQL = """
SELECT w.id::text, w.key, w.created_at
  FROM litkb.works w
 WHERE w.created_in_ws = %(ws)s AND w.created_at > %(since)s
 ORDER BY w.created_at, w.id
"""

VERIFIED_USES_SQL = """
SELECT count(*) FROM litkb.use_versions uv
 WHERE uv.workstream_id = %(ws)s AND uv.created_at > %(since)s
   AND EXISTS (SELECT 1 FROM litkb.use_evidence e
                WHERE e.use_version_id = uv.version_id AND e.quote_verified)
"""

MANUAL_ATTEMPTS_SQL = """
SELECT a.id::text, a.route, a.status
  FROM litkb.acquisition_attempts a
 WHERE a.work_id = ANY(%(works)s::uuid[])
   AND (a.status = 'manual-step' OR a.route = ANY(%(routes)s))
 ORDER BY a.at
"""

MANUAL_FILES_SQL = """
SELECT fv.version_id::text, fv.file_id::text, fv.source_route
  FROM litkb.file_versions fv
 WHERE fv.work_id = ANY(%(works)s::uuid[]) AND fv.source_route = ANY(%(routes)s)
 ORDER BY fv.created_at
"""


def baseline_snapshot(db, role, ws_id):
    """(frozen_at, {name: count}) — the freeze instant AND the baseline, from ONE clock and ONE
    snapshot.

    THE FREEZE INSTANT IS THE DATABASE'S, not this process's. `frozen_at` and every count it is
    compared against are read from the same server in the same REPEATABLE READ transaction, so
    `now()` (which in PostgreSQL is the transaction's start time) is exactly the instant the
    snapshot the counts were taken from was established. A client clock cannot be used for this:
    `works.created_at` defaults to the server's `now()`, and the two clocks agree only by
    coincidence — a workstation seconds ahead of its database server would freeze at an instant
    later than rows the baseline had already counted, and every one of those would then score as a
    NEW work. The test fixtures had read `SELECT now()` for exactly this reason since the day they
    were written; the freeze had not.

    REPEATABLE READ rather than the default READ COMMITTED, because under READ COMMITTED each
    count takes a fresh snapshot: a row inserted while the six queries run is in a later count and
    not in an earlier one, and it is after `now()` in either case. One snapshot makes "the baseline"
    a single fact about a single moment, which is what the word means.
    """
    conn = _connect(db, role, autocommit=False)
    try:
        from psycopg import IsolationLevel

        conn.isolation_level = IsolationLevel.REPEATABLE_READ
        with conn.transaction():
            at = conn.execute("SELECT now()").fetchone()[0]
            counts = ({name: conn.execute(sql, {"ws": ws_id}).fetchone()[0]
                       for name, sql in BASELINE_QUERIES.items()} if ws_id
                      else dict.fromkeys(BASELINE_QUERIES))
        return at, counts
    finally:
        conn.close()


def _new_works(db, role, ws_id, since):
    """[{work_id, key, created_at}] — the works this workstream admitted after the freeze."""
    conn = _connect(db, role)
    try:
        rows = conn.execute(NEW_WORKS_SQL, {"ws": ws_id, "since": since}).fetchall()
        return [dict(zip(("work_id", "key", "created_at"), r)) for r in rows]
    finally:
        conn.close()


def _work_states(db, role, ws_id, work_ids):
    """{work_id: {"state", "identifier"}} through `litkb.hunt.look_up` — THE ladder, not a copy.

    `look_up` starts from an identifier, so each work is reached by one of its own active ones
    (every admission writes at least one: a DOI, an arXiv id, or the URL `admit_web` records). A
    work with none is reported with `state = None` and an offence naming it rather than silently
    counted as unbound — that would be a different defect wearing this one's name.
    """
    from litkb import hunt as H

    conn = _connect(db, role)
    try:
        out = {}
        for wid in work_ids:
            row = conn.execute(
                "SELECT scheme, value FROM litkb.ws_identifiers "
                " WHERE view_workstream_id = %s AND work_id = %s AND status = 'active' "
                " ORDER BY scheme, value LIMIT 1", (ws_id, wid)).fetchone()
            if not row:
                out[wid] = {"state": None, "identifier": None}
                continue
            held = H.look_up(conn, ws_id, row[1], row[0])
            out[wid] = {"state": (held or {}).get("state"), "identifier": f"{row[0]}:{row[1]}"}
        return out
    finally:
        conn.close()


def _searchable_work_ids(db, role, ws_id, work_ids):
    """The subset of `work_ids` with at least one block litkb_search can return from here.

    The predicate is the SERVER's own `_BLOCK_FROM` fragment with the server's `DEFAULT_KINDS`:
    the blocks/files/current-run join plus `visibility.FILE_JOIN`, which is what widens a search
    to this workstream's own proposals (decisions.yaml litkb-web-source-gate). Restating it here
    would be a second answer to "what can this session read".
    """
    from litkb.mcp import server as S

    sql = "SELECT DISTINCT fv.work_id::text" + S._BLOCK_FROM + \
          "   AND fv.work_id = ANY(%(works)s::uuid[])"
    conn = _connect(db, role)
    try:
        rows = conn.execute(sql, {"ws": ws_id, "kinds": list(S.DEFAULT_KINDS),
                                  "works": list(work_ids)}).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def _verified_uses(db, role, ws_id, since):
    conn = _connect(db, role)
    try:
        return conn.execute(VERIFIED_USES_SQL, {"ws": ws_id, "since": since}).fetchone()[0]
    finally:
        conn.close()


def _manual_traces(db, role, work_ids):
    """([manual attempt rows], [manual file-version rows]) for the new works."""
    conn = _connect(db, role)
    try:
        works = list(work_ids)
        attempts = conn.execute(MANUAL_ATTEMPTS_SQL,
                                {"works": works,
                                 "routes": list(MANUAL_ATTEMPT_ROUTES)}).fetchall()
        files = conn.execute(MANUAL_FILES_SQL,
                             {"works": works, "routes": list(MANUAL_FILE_ROUTES)}).fetchall()
        return ([dict(zip(("attempt_id", "route", "status"), r)) for r in attempts],
                [dict(zip(("version_id", "file_id", "source_route"), r)) for r in files])
    finally:
        conn.close()


def _unaccounted_files(db, role, ws_id, since):
    """`litkb.acquire.events.bound_without_event`, opened on a reader connection. The verifier
    lives in the litkb package beside the acquisition code that writes the events; this is only
    where the acceptance run reads it."""
    from litkb.acquire import events

    conn = _connect(db, role)
    try:
        return events.bound_without_event(conn, ws_id, since)
    finally:
        conn.close()


#: The database reads, in ONE injectable place (the scout's `_hunt_request_rows` seam, widened to
#: six calls). The tests replace entries here to exercise the counting rules with no server.
DB_READS = {"new_works": _new_works, "work_states": _work_states,
            "searchable": _searchable_work_ids, "verified_uses": _verified_uses,
            "manual_traces": _manual_traces, "unaccounted_files": _unaccounted_files}


def review_citations(path):
    """The review's citations, through the GRAMMAR's own parser. One grammar, one parser."""
    return _citations(_read_review(path))


def count_claims_ungraded(review, report_path):
    """(claims_ungraded, [offence lines]) for one review against one Codex report.

    The same rule `check_codex` applies for `citations_unreviewed`: citation *i* is graded only
    when the report carries a row `n = i` whose `block_id` is the block that citation names. A row
    for a citation the review does not have grades nothing; a row pointing at another block grades
    another sentence.
    """
    if not review:
        return 1, ["no --review was named: nothing was graded, which is a RED and not a 0"]
    cits = review_citations(review)
    if not report_path:
        return len(cits), [f"no --codex-report was named: all {len(cits)} citation(s) of "
                           f"{Path(review).name} are ungraded"]
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    by_n = {}
    for r in report.get("citations", []):
        if isinstance(r, dict):
            by_n.setdefault(r.get("n"), r)
    ungraded, offences = 0, []
    for i, c in enumerate(cits, start=1):
        r = by_n.get(i)
        if r is None:
            ungraded += 1
            offences.append(f"citation {i} (#{c['block_id']}) has no verdict row in the report")
        elif r.get("block_id") != c["block_id"]:
            ungraded += 1
            offences.append(f"citation {i} names block {c['block_id']}, the report's row {i} "
                            f"names {r.get('block_id')!r}")
    return ungraded, offences


def check_first_work(manifest, *, reads=None, review=None, codex_report=None, log=None):
    """(counters dict, [offence lines]). Every database read goes through `reads` (DB_READS)."""
    reads = reads or DB_READS
    db = manifest["db"]
    role = manifest.get("reader_role") or "litkb_reader"
    ws_id = manifest.get("workstream_id")
    since = _parse_utc(manifest["frozen_at"])
    review = review or manifest.get("review")
    codex_report = codex_report or manifest.get("codex_report")
    log = log or manifest.get("log")
    offences = []

    if not ws_id:
        ws_id = resolve_workstream(db, role, manifest["workstream_slug"])
    if not ws_id:
        offences.append(f"no OPEN workstream with slug {manifest.get('workstream_slug')!r} "
                        f"in {db}")
        works = []
    else:
        works = reads["new_works"](db, role, ws_id, since)

    # a NOTE, not an offence: which chain the counters below are about. A clean run still prints
    # it, because a gate that says only "1" leaves the reader unable to check anything by hand.
    for w in works:
        offences.append(f"graded: {w['key']} ({w['work_id']})")
    ids = [w["work_id"] for w in works]
    keys = {w["work_id"]: w["key"] for w in works}

    states = reads["work_states"](db, role, ws_id, ids) if ids else {}
    bound, extracted = [], []
    for wid in ids:
        state = (states.get(wid) or {}).get("state")
        if state in ("bound-unextracted", "extracted"):
            bound.append(wid)
        else:
            offences.append(f"{keys[wid]}: no bound file (ladder says {state!r})")
        if state == "extracted":
            extracted.append(wid)
        elif state == "bound-unextracted":
            offences.append(f"{keys[wid]}: bound and never extracted — litkb_search cannot see it")

    searchable = reads["searchable"](db, role, ws_id, extracted) if extracted else set()
    for wid in extracted:
        if wid not in searchable:
            offences.append(f"{keys[wid]}: extracted with no block visible to search from this "
                            f"workstream")

    verified = reads["verified_uses"](db, role, ws_id, since) if ws_id else 0
    if not verified:
        offences.append("no use recorded after the freeze carries a database-verified quote")

    ungraded, claim_offences = count_claims_ungraded(review, codex_report)
    offences += claim_offences

    # BEGIN guard: operator_interventions sums four independent traces, never one
    # Each names a different way a human or an unrecorded hand can have moved the run along, and
    # three of the four are database facts that hold whether or not a log was kept. A counter
    # built on the log alone would read 0 for a run nobody logged, which is the reading S2 must
    # not be able to produce.
    interventions, log_note = 0, "no log named: human_input_events not read"
    if log:
        events_n, _stated, log_offences = read_log(log)
        interventions += events_n
        offences += log_offences
        log_note = f"log {Path(log).name}: human_input_events={events_n}"
    attempts, manual_files = reads["manual_traces"](db, role, ids) if ids else ([], [])
    interventions += len(attempts) + len(manual_files)
    for a in attempts:
        offences.append(f"manual acquisition attempt {a['attempt_id']}: route={a['route']} "
                        f"status={a['status']}")
    for f in manual_files:
        offences.append(f"file version {f['version_id']} arrived by the manual route "
                        f"{f['source_route']!r}")
    unaccounted = reads["unaccounted_files"](db, role, ws_id, since) if ws_id else []
    interventions += len(unaccounted)
    for u in unaccounted:
        offences.append(f"file {u['file_id']} (sha256 {u['sha256'][:12]}…) is bound with NO "
                        f"acquisition event — unaccounted-for provenance")
    # END guard: operator_interventions sums four independent traces, never one
    offences.append(log_note)

    return ({"new_works": len(works), "bound": len(bound), "extracted": len(extracted),
             "searchable": len(searchable), "verified_uses": verified,
             "claims_ungraded": ungraded, "operator_interventions": interventions}, offences)


def first_work_ok(counters):
    """S2's bounds. `new_works == 1`, not `>= 1`: one work is the whole point (module docstring)."""
    return (counters["new_works"] == 1 and counters["bound"] == 1
            and counters["extracted"] == 1 and counters["searchable"] == 1
            and counters["verified_uses"] >= 1 and counters["claims_ungraded"] == 0
            and counters["operator_interventions"] == 0)


def cmd_first_work(args):
    if args.freeze:
        return _first_work_freeze(args)
    if not args.manifest:
        print("litkb_acceptance first-work needs --manifest (or --freeze --out)", file=sys.stderr)
        return 2
    manifest = json.loads(read_text(args.manifest))
    counters, offences = check_first_work(manifest, review=args.review,
                                          codex_report=args.codex_report, log=args.log)
    for line in offences:
        print(line, file=sys.stderr)
    print(" ".join(f"{k}={v}" for k, v in counters.items()))
    return 0 if first_work_ok(counters) else 1


def _first_work_freeze(args):
    for required in ("workstream", "out"):
        if not getattr(args, required):
            print(f"first-work --freeze needs --{required}", file=sys.stderr)
            return 2
    repo = Path(args.repo or _repo_root())
    role = args.role
    ws_id = resolve_workstream(args.db, role, args.workstream)
    frozen_at, baseline = baseline_snapshot(args.db, role, ws_id)
    db_tip, db_tip_note = db_migration_tip(args.db, args.passfile)
    manifest = {
        "kind": "litkb-first-work",
        # FULL PRECISION, and UTC. Not the scout's `%Y-%m-%dT%H:%M:%SZ`: truncating to the second
        # moves the instant EARLIER, which is the unsafe direction — a row written in the truncated
        # fraction is before the freeze and would score as a new work.
        "frozen_at": frozen_at.astimezone(dt.timezone.utc).isoformat(),
        # WHICH CLOCK. Recorded because "the freeze instant" is meaningless without it, and because
        # a later manifest written by some other hand can be read for this field and disbelieved.
        "frozen_at_source": "db",
        "repo": str(repo),
        "repo_head": _repo_head(repo),
        "db": args.db,
        "reader_role": role,
        "repo_migration_tip": repo_migration_tip(),
        "db_migration_tip": db_tip,
        "db_migration_tip_note": db_tip_note,
        "workstream_slug": args.workstream,
        "workstream_id": ws_id,
        "hunt_request_id": args.hunt_request,
        "log": str(args.log) if args.log else None,
        # Recorded when they are already known; the command line WINS at grade time, because the
        # Codex report is produced after the freeze and naming it should not mean rewriting a
        # frozen file.
        "review": str(args.review) if args.review else None,
        "codex_report": str(args.codex_report) if args.codex_report else None,
        "baseline": baseline,
        "queries": dict(BASELINE_QUERIES),
        # recorded for the READER; the checker uses the module constants (the scout's rule)
        "manual_attempt_routes": list(MANUAL_ATTEMPT_ROUTES),
        "manual_file_routes": list(MANUAL_FILE_ROUTES),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"frozen {out} workstream={args.workstream} id={ws_id} "
          f"baseline={baseline} head={manifest['repo_head'][:12]} "
          f"repo_tip={manifest['repo_migration_tip']} db_tip={db_tip}")
    return 0


# ── preflight: the checks a session runs BEFORE its first hunt ────────────────────────────
#
# Every one of these was a chat-prompt "tip" after S1 (2026-09-20) — and a tip in a prompt is
# a fact with no home. Each became a counter here because each was a real hazard that day:
#   stray_tokens        a scout opened its workstream IN THE MAIN TREE ROOT; a standing token there
#                       widens every later hunt from that tree to the wrong workstream
#   migration_mismatch  the MCP server runs main's code; a migration on disk but not applied
#                       refuses the first drop-off that needs it (0027 / `title`)
#   mcp_servers_missing a headless run under --strict-mcp-config sees ONLY what .mcp.json names
#   main_not_at_parity  a session starting from a main that github does not have
#   soak_stale          the seven-night clock: a night that did not run, or ran red, is found
#                       the next morning, not at S7
# The MCP server of an OPEN session is stale after any merge until `/mcp` reconnect; that is
# not measurable from here, so preflight prints the HEAD it checked and says so.

SOAK_MAX_AGE_H = 26            # a nightly task at 03:17; one missed night is > 24 h
MCP_REQUIRED = ("litkb", "paper-search-mcp")


def _soak_last_row(csv_path):
    """The last row of the soak CSV, or None."""
    p = Path(csv_path)
    if not p.is_file():
        return None
    import csv as _csv
    rows = list(_csv.DictReader(p.read_text(encoding="utf-8-sig").splitlines()))
    return rows[-1] if rows else None


def check_preflight(repo, *, db="litkb", passfile=None, now=None, soak_csv=None, mcp_json=None):
    """-> (counters dict, [detail lines]). Pure over its inputs except the DB tip read."""
    repo = Path(repo)
    now = now or _utc_now()
    counters, detail = {}, []

    tokens = sorted(p.name for p in repo.glob(".litkb-workstream*"))
    counters["stray_tokens"] = len(tokens)
    for t in tokens:
        detail.append(f"stray token in the tree root: {t} — vault it, then remove it")

    r_tip = repo_migration_tip()
    d_tip, note = db_migration_tip(db, passfile)
    counters["migration_mismatch"] = 0 if (r_tip is not None and r_tip == d_tip) else 1
    if counters["migration_mismatch"]:
        detail.append(f"migration tip: repo={r_tip} db={d_tip} ({note or 'mismatch'}) — Kam applies")

    mcp = Path(mcp_json or repo / ".mcp.json")
    try:
        servers = set((json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers") or {}).keys())
    except (OSError, ValueError):
        servers = set()
    missing = [s for s in MCP_REQUIRED if s not in servers]
    counters["mcp_servers_missing"] = len(missing)
    for s in missing:
        detail.append(f".mcp.json does not name {s}: a --strict-mcp-config run will not see it")

    local, remote = _rev_parse(repo, "main"), _rev_parse(repo, "github/main")
    counters["main_not_at_parity"] = 0 if (local and local == remote) else 1
    if counters["main_not_at_parity"]:
        detail.append(f"main {str(local)[:12]} != github/main {str(remote)[:12]} (fetch first?)")

    row = _soak_last_row(soak_csv or repo / "Reports" / "LITKB_SOAK.csv")
    stale, why = 1, "no soak row at all"
    if row:
        try:
            age_h = (now - _parse_utc(row.get("ts_utc", ""))).total_seconds() / 3600
            ok = (row.get("search_ok") == "true" and row.get("hunt_ok") == "true")
            stale = 0 if (age_h <= SOAK_MAX_AGE_H and ok) else 1
            why = (f"last soak row {row.get('ts_utc')} ({age_h:.1f} h old) search_ok="
                   f"{row.get('search_ok')} hunt_ok={row.get('hunt_ok')} error={row.get('error') or '-'}")
        except (ValueError, TypeError):
            why = f"last soak row has an unreadable ts_utc: {row.get('ts_utc')!r}"
    counters["soak_stale"] = stale
    detail.append(("SOAK STALE: " if stale else "soak ok: ") + why)

    detail.append(f"checked HEAD {_repo_head(repo)[:12]}; an OPEN session's MCP server is stale "
                  f"after a merge until `/mcp` reconnect — not measurable here")
    return counters, detail


# ── codex: did the adversarial read actually read (the review stage's gate) ────────────────
#
# WHAT THIS GRADES, and what it deliberately does not. The Codex stage returns a JSON report with
# one verdict per citation (qc/fixtures/litkb_codex_report.schema.json, written by
# qc/instruments/litkb_codex_review.py). Three of its counters are GATES, because each names a way
# the stage can look complete and be empty:
#
#   citations_unreviewed  a citation of the review with no row in the report. THE silent pass: a
#                         reviewer that skipped what it could not decide returns a report whose
#                         every row says SUPPORTED, and nothing in the prose would say otherwise.
#   verdict_outside_set   a verdict outside SUPPORTED/OVERREACH/UNSUPPORTED. A free-text verdict
#                         is one a counter cannot read, which is how run 1's prose came to say
#                         7/12 over a table holding 6 (codex-review-proving-run.md).
#   hash_mismatch         the report's stamped digests are not this review's and this context's.
#                         A report and a review edited between them look exactly like a report
#                         about the review.
#
# `overreach` and `unsupported` are FINDINGS, not failures. A review with an overreaching citation
# is a review to fix; the stage did its job by finding it, and a gate that failed on a finding
# would pay the reviewer to find nothing. The orchestrator decides.
#
# `--mutate n` IS THE KILL. A gate that has never been shown to fire is not known to work
# (CLAUDE.md 3.4c), and what this stage must be shown to do is FLAG a claim its quote does not
# carry. So: take citation n's sentence, rewrite it to assert CAUSATION while leaving its quote
# byte-identical, and require the report for the MUTATED review to flag n. A run in which the
# reviewer passed the planted overreach is `mutation_not_flagged=1`, and that IS a failure.
#
# THE MUTATION IS DETERMINISTIC AND IDEMPOTENT: the same review and the same n give the same
# bytes, so the file the wrapper reviewed and the file this gate hashes are one file without
# either command passing the other a path. Two rules, in this order, applied to the region of
# citation n's sentence BEFORE its quote's opening delimiter:
#
#   1. `is associated with` -> `causes`  (first occurrence; only when that region holds no quote
#      delimiter at all, so an EARLIER citation's quote in the same sentence cannot be touched)
#   2. otherwise, insert `Because of this, ` at the start of the sentence
#
# and then the check that makes the rule safe rather than merely careful: every citation of the
# mutated text must carry the same (work_key, page, block_id, quote) as the original's. A rewrite
# that moved one byte of one quote is refused, not reported.

#: The verdicts the report's schema allows. Restated here because this gate must be able to say
#: "outside the set" about a report the schema validator never saw -- a hand-written one, or one
#: from a future wrapper.
CODEX_VERDICTS = ("SUPPORTED", "OVERREACH", "UNSUPPORTED")
#: What `--mutate` writes when `--mutated-out` is not given: beside the review, never over it.
MUTATED_SUFFIX = ".mutated.md"
_ASSOC = "is associated with"
_CAUSES = "causes"
_BECAUSE = "Because of this, "
#: The quote delimiters the grammar accepts (LITKB_REVIEW_GRAMMAR.md §2). A region holding one of
#: these is a region rule 1 will not touch.
_QUOTE_CHARS = '"“”'


def _read_review(path):
    """The review's text with NEWLINE TRANSLATION OFF -- `review_check._read`'s rule. A reader
    that rewrote a CRLF would hash a file nobody has."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return fh.read()


def _citations(text):
    """The grammar's citations, from the grammar's own parser. Imported, never re-implemented."""
    from litkb.review_check import citations

    return citations(text)


def mutate_review(text, n):
    """(mutated text, what was done) for citation `n` of a review, or raise SystemExit.

    See the block comment above for the two rules and for why the quote-identity check below is
    what makes them safe rather than merely careful.
    """
    from litkb.review_check import _SENTENCE_SPLIT

    cits = _citations(text)
    if not 1 <= n <= len(cits):
        raise SystemExit(f"litkb_acceptance codex --mutate {n}: the review has "
                         f"{len(cits)} citation(s)")
    c = cits[n - 1]
    # The opening delimiter of THIS citation's quote: back over spaces/tabs to the closing
    # delimiter, then back to the opener. The same walk as `review_check._quote_before`.
    j = c["start"] - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] not in _QUOTE_CHARS:
        raise SystemExit(f"litkb_acceptance codex --mutate {n}: citation {n} carries no quote, so "
                         "there is no sentence to rewrite around it")
    k = j - 1
    while k >= 0 and text[k] not in _QUOTE_CHARS:
        k -= 1
    q_open = k
    # The sentence start: the latest of the last sentence break and the start of the line the
    # quote opens on. `_SENTENCE_SPLIT` is the splitter K1 itself uses.
    head = text[:q_open]
    starts = [m.end() for m in _SENTENCE_SPLIT.finditer(head)]
    s = max([0] + starts + [head.rfind("\n") + 1])
    region = text[s:q_open]
    if _ASSOC in region and not any(ch in region for ch in _QUOTE_CHARS):
        new_region = region.replace(_ASSOC, _CAUSES, 1)
        done = f"replaced {_ASSOC!r} with {_CAUSES!r}"
    else:
        new_region = _BECAUSE + region
        done = f"prefixed {_BECAUSE!r}"
    out = text[:s] + new_region + text[q_open:]

    # BEGIN guard: the mutation leaves every citation and every quote byte-identical
    before = [(x["work_key"], x["page"], x["block_id"], x["quote"]) for x in cits]
    after = [(x["work_key"], x["page"], x["block_id"], x["quote"]) for x in _citations(out)]
    if before != after:
        raise SystemExit(
            f"litkb_acceptance codex --mutate {n}: the rewrite changed a citation or a quote and "
            "was not written. The planted claim must be the ONLY difference -- a mutated quote "
            "would make the reviewer right to flag it and would prove nothing about the claim")
    # END guard: the mutation leaves every citation and every quote byte-identical
    return out, done


def write_mutation(review, n, out_path=None):
    """Write the mutated review beside the original; (path, what was done)."""
    mutated, done = mutate_review(_read_review(review), n)
    p = Path(out_path) if out_path else Path(str(review) + MUTATED_SUFFIX)
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(mutated)
    return p, done


def check_codex(review, context, report_path, *, mutate=None):
    """(counters, offences) for one Codex report against the review it claims to be about."""
    from litkb.review_context import sha256_file

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    cits = _citations(_read_review(review))
    counters = {"citations_unreviewed": 0, "verdict_outside_set": 0, "hash_mismatch": 0,
                "overreach": 0, "unsupported": 0}
    offences = []

    rows, by_n = report.get("citations", []), {}
    for r in rows:
        if isinstance(r, dict):
            by_n.setdefault(r.get("n"), r)
    # BEGIN guard: every citation of the review carries a verdict row of its own
    # Without this the gate counts verdicts and never asks which citations HAVE one, so a report
    # that omitted the citation its reviewer could not decide passes with every remaining row
    # SUPPORTED. It is the one failure of this stage that looks exactly like success (row CX6).
    for i, c in enumerate(cits, start=1):
        r = by_n.get(i)
        if r is None:
            counters["citations_unreviewed"] += 1
            offences.append(f"citation {i} (#{c['block_id']}) has no verdict -- a missing row "
                            "reads as a pass")
        elif r.get("block_id") != c["block_id"]:
            counters["citations_unreviewed"] += 1
            offences.append(f"citation {i} names block {c['block_id']}, the report's row {i} "
                            f"names {r.get('block_id')!r}")
    # END guard: every citation of the review carries a verdict row of its own
    # BEGIN guard: every verdict is one of the three, and the findings are counted
    # Without this a free-text verdict is neither refused nor counted, and `overreach` and
    # `unsupported` stay 0 whatever the report says -- so the gate reads green over a reviewer
    # answering in prose, which is how run 1's summary came to say 7/12 over a table that held
    # 6 (row CX7).
    for r in rows:
        v = r.get("verdict") if isinstance(r, dict) else None
        if v not in CODEX_VERDICTS:
            counters["verdict_outside_set"] += 1
            offences.append(f"row n={r.get('n') if isinstance(r, dict) else r!r}: verdict "
                            f"{v!r} is outside {CODEX_VERDICTS}")
        elif v == "OVERREACH":
            counters["overreach"] += 1
        elif v == "UNSUPPORTED":
            counters["unsupported"] += 1
    # END guard: every verdict is one of the three, and the findings are counted

    # BEGIN guard: the report's digests are recomputed from the two files it names
    # Without this the gate never re-reads the files, so a review edited after it was reviewed --
    # or a report carried over from a different review entirely -- grades clean. A report and a
    # review edited between them look exactly like a report about the review (row CX8).
    for name, path in (("review", review), ("context", context)):
        want = sha256_file(path)
        got = report.get(f"{name}_sha256")
        if got != want:
            counters["hash_mismatch"] += 1
            offences.append(f"{name}_sha256 in the report is {got!r}; {Path(path).name} hashes "
                            f"to {want}")
    # END guard: the report's digests are recomputed from the two files it names

    if mutate is not None:
        r = by_n.get(mutate)
        # The defaults below are what the guard REPLACES, and they are deliberately the
        # permissive ones: with the guard removed this command still runs and still exits 0,
        # which is the defect row CX10 plants rather than a crash any test would catch.
        flagged, counters["mutation_not_flagged"] = True, 0
        # BEGIN guard: the planted causation must come back flagged
        # This is the stage's own kill. Without it `--mutate N` plants a claim the quote does not
        # carry, hands it to the reviewer, and never asks what came back -- so the command that
        # exists to prove the reviewer catches an overreach passes whatever it says (row CX10).
        flagged = bool(r) and r.get("verdict") in CODEX_VERDICTS and r.get("verdict") != "SUPPORTED"
        counters["mutation_not_flagged"] = 0 if flagged else 1
        # END guard: the planted causation must come back flagged
        if not flagged:
            offences.append(
                f"citation {mutate} of the MUTATED review asserts a causation its quote does not "
                f"carry, and the report returned {(r or {}).get('verdict')!r}. A reviewer that "
                "passes a planted overreach has not been shown to catch a real one")
    return counters, offences


def codex_ok(counters):
    """Exit 0 only when the three GATE counters are 0, and the mutation when one was planted.
    `overreach` and `unsupported` are findings and never fail this command."""
    return not any(counters.get(g, 0) for g in
                   ("citations_unreviewed", "verdict_outside_set", "hash_mismatch",
                    "mutation_not_flagged"))


def cmd_codex(args):
    if args.mutate is not None and not args.report:
        # PREPARE MODE: write the mutated review for the wrapper to review, and nothing else.
        # Deterministic and idempotent, so the file graded below is the file reviewed.
        path, done = write_mutation(args.review, args.mutate, args.mutated_out)
        print(f"mutated citation {args.mutate} of {args.review}: {done} -> {path}")
        return 0
    if not args.report:
        print("litkb_acceptance codex needs --report (or --mutate N alone, to prepare the "
              "mutated review)", file=sys.stderr)
        return 2
    review = args.review
    if args.mutate is not None:
        review = str(Path(args.mutated_out) if args.mutated_out
                     else Path(str(args.review) + MUTATED_SUFFIX))
        if not Path(review).exists():
            print(f"litkb_acceptance codex --mutate {args.mutate}: {review} does not exist -- run "
                  "this command with --mutate and no --report first", file=sys.stderr)
            return 2
    counters, offences = check_codex(review, args.context, args.report, mutate=args.mutate)
    for line in offences:
        print(line, file=sys.stderr)
    print(" ".join(f"{k}={v}" for k, v in counters.items()))
    return 0 if codex_ok(counters) else 1


def cmd_preflight(args):
    repo = Path(args.repo or _repo_root())
    counters, detail = check_preflight(repo, db=args.db, passfile=args.passfile,
                                       soak_csv=args.soak_csv, mcp_json=args.mcp_json)
    for line in detail:
        print(line, file=sys.stderr)
    print(" ".join(f"{k}={v}" for k, v in counters.items()))
    return 0 if not any(counters.values()) else 1


# ── edges: does EVERY edge class end in the state the register adjudicated (S3) ───────────
#
# The scout counted whether a drop-off ended in SOME closed word. This counts whether it ended in
# the RIGHT one: the register (`qc/fixtures/litkb_hunt_edge_cases.json`) names the (state, reason)
# pair for each class and cites the code and the attempts history that decide it, and this command
# compares the pair the run observed against it. Membership alone cannot pass — that is the whole
# difference, and the mutation row that proves it swaps one row's expectation for another VALID
# pair and requires a mismatch.

#: The register file's `kind`, and this command's manifest `kind`.
EDGES_FIXTURE_KIND = "litkb-hunt-edge-cases"
EDGES_MANIFEST_KIND = "litkb-edges"

#: The migration the URL branch's acquisition-event route waits on (`hunt-url` in
#: `acquisition_attempts_route_check`). Rows that need it declare `live.needs_migration`; the mode
#: is MEASURED at freeze against `db_migration_tip`, never hard-coded — 0028 was unapplied on the
#: morning S3 opened and applied by the afternoon.
EDGES_URL_MIGRATION = 28


def _edge_run():
    """The sibling driver, by path (the scout checker's rule): one home for the CSV columns, the
    mode rule and the expectation rule, never a second copy here."""
    spec = importlib.util.spec_from_file_location(
        "litkb_edge_run", SCRIPTS / "qc" / "instruments" / "litkb_edge_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _edge_rows(fixture_path):
    return json.loads(read_text(fixture_path))


def _asserts_offences(row, csv_row, *, replay=False):
    """The register's extra `asserts`, checked against the CSV row. -> [offence lines].

    These are the facts `state` deliberately does NOT carry — whether the work reached main,
    whether the admission is a proposal, how many admissions the hunt wrote, what the route
    attempt recorded — and a row that got the pair right by writing a second admission has not
    passed."""
    out = []
    a = row.get("asserts") or {}
    if replay and "asserts" in (row.get("replay") or {}):
        # the replay's twin of `replay.expected`: a freshly migrated database and the live corpus
        # can give one row two right answers (E06: a held work in main makes the page a
        # duplicate live; the empty replay database makes it a proposal with blocks), and the
        # facts `state` does not carry differ with them
        a = row["replay"]["asserts"] or {}
    rid = row["id"]
    try:
        report = json.loads(csv_row.get("report") or "{}")
    except ValueError:
        report = {}
    for key in ("in_main", "admission_state"):
        if key in a:
            if report.get(key) != a[key]:
                out.append(f"{rid}: {key} {report.get(key)!r} != {a[key]!r}")
    if "new_admissions" in a and a["new_admissions"] is not None:
        got = str(csv_row.get("new_admissions") or "").strip()
        if got != str(a["new_admissions"]):
            out.append(f"{rid}: new_admissions {got!r} != {a['new_admissions']}")
    if a.get("attempt_status"):
        statuses = [s.split(":", 1)[-1] for s in
                    (csv_row.get("attempt_statuses") or "").split(";") if s]
        detail = csv_row.get("route_detail") or "[]"
        if a["attempt_status"] not in statuses and f'"{a["attempt_status"]}"' not in detail:
            out.append(f"{rid}: no route attempt with status {a['attempt_status']!r} "
                       f"(attempts={statuses})")
    # BEGIN guard: an assert this grader cannot evaluate is named, never silently passed
    # A gate that has never fired is not a gate (CLAUDE.md §3.4c). The register may carry an
    # assert about a fact no column holds; saying so is a mismatch, because the alternative is a
    # row that reads as checked and is not.
    unknown = sorted(set(a) - {"in_main", "admission_state", "new_admissions", "attempt_status"})
    for key in unknown:
        out.append(f"{rid}: assert {key!r} is not checkable from the edge-run CSV — add a column "
                   "or drop the assert; it is NOT being checked")
    # END guard: an assert this grader cannot evaluate is named, never silently passed
    return out


def check_edges(manifest, *, rows=None, csv_path=None, replay=False, fixture_sha=None):
    """(counters dict, [offence lines]).

    `rows` and `fixture_sha` are injected by the tests; the defaults read the fixture named in the
    manifest and its sha256 on disk. THE SHA IS CHECKED BEFORE ANYTHING IS GRADED: the register is
    what the run is graded against, so a register edited after the freeze grades a different
    question, and a mutation of the fixture that the grader then passed would make this command
    unable to catch its own known-bad."""
    E = _edge_run()
    offences = []
    fixture = manifest.get("fixture")
    if rows is None:
        if fixture_sha is None:
            fixture_sha = _sha256(fixture)
        want = manifest.get("fixture_sha256")
        # BEGIN guard: the register graded is the register frozen
        if want and fixture_sha != want:
            raise SystemExit(f"litkb_acceptance edges: {fixture} has sha256 {fixture_sha}, the "
                             f"manifest froze {want}. The register was edited after the freeze; "
                             "re-freeze it or restore the file. Nothing was graded.")
        # END guard: the register graded is the register frozen
        register = _edge_rows(fixture)
        if register.get("kind") != EDGES_FIXTURE_KIND:
            offences.append(f"{fixture}: kind {register.get('kind')!r} is not "
                            f"{EDGES_FIXTURE_KIND!r}")
        rows = E.rows_of(register)

    results = E.read_edge_csv(csv_path or (manifest["replay_csv"] if replay
                                           else manifest["run_csv"]))
    db_tip = manifest.get("db_migration_tip")

    executed = skipped = mismatches = tracebacks = held = waiting = 0
    for row in rows:
        rid = row["id"]
        mode = E.resolve_mode(row, db_tip)
        if mode == "held-for-ruling":
            held += 1
            if not (row.get("held_for_ruling") or {}).get("question"):
                offences.append(f"{rid}: held_for_ruling with no question")
            continue
        if mode == "not-a-hunt":
            continue
        # in --replay a waiting row IS executed: the worker database is migrated by the driver, so
        # the migration the live run waits on is present there by construction
        if mode == "waits-on-migration" and not replay:
            waiting += 1
            continue
        if mode == "replay-only" and not replay:
            continue
        hit = results.get(rid)
        if hit is None:
            skipped += 1
            offences.append(f"{rid}: no row in the driver CSV")
            continue
        executed += 1
        if str(hit.get("traceback") or "0").strip() not in ("", "0", "false"):
            tracebacks += 1
            offences.append(f"{rid}: hunt() RAISED — {hit.get('message')}")
            continue
        want_state, want_reason = E.expected_of(row, replay=replay)
        got_state = (hit.get("observed_state") or "").strip()
        got_reason = (hit.get("observed_reason") or "").strip()
        row_offences = []
        # BEGIN guard: the pair is compared, and membership alone cannot pass
        if (got_state, got_reason) != (want_state, want_reason):
            row_offences.append(f"{rid}: observed {got_state}/{got_reason} != expected "
                                f"{want_state}/{want_reason}")
        # END guard: the pair is compared, and membership alone cannot pass
        if got_state not in CLOSED_STATES:
            row_offences.append(f"{rid}: state {got_state!r} outside the closed vocabulary")
        row_offences += _asserts_offences(row, hit, replay=replay)
        if row_offences:
            mismatches += 1
            offences += row_offences

    return ({"executed": executed, "skipped": skipped,
             "state_or_reason_mismatches": mismatches, "tracebacks": tracebacks,
             "held_for_ruling": held, "waits_on_migration": waiting}, offences)


def edges_ok(counters, manifest_rows):
    """`executed` must equal the rows the manifest expected to run — a run that hunted half the
    register and got them all right has not graded the register."""
    return (counters["executed"] == manifest_rows and counters["skipped"] == 0
            and counters["state_or_reason_mismatches"] == 0 and counters["tracebacks"] == 0)


def edges_manifest_rows(manifest, counters, *, replay=False):
    """How many rows this mode was supposed to execute: the manifest's own row list, minus the
    held and the not-a-hunt rows, minus (outside --replay) the rows waiting on a migration."""
    rows = [r for r in (manifest.get("rows") or [])
            if r.get("mode") not in ("held-for-ruling", "not-a-hunt")]
    if not replay:
        rows = [r for r in rows if r.get("mode") != "waits-on-migration"]
        rows = [r for r in rows if r.get("mode") != "replay-only"]
    return len(rows)


def cmd_edges(args):
    if args.freeze:
        return _edges_freeze(args)
    if not args.manifest:
        print("litkb_acceptance edges needs --manifest (or --freeze --out)", file=sys.stderr)
        return 2
    manifest = json.loads(read_text(args.manifest))
    if args.replay and not args.no_execute:
        # `--replay` EXECUTES the replay first, then grades it: two commands that could disagree
        # about which CSV they meant is the failure mode the scout's `--out`/`--csv` split already
        # produced once. `--no-execute` grades a replay CSV somebody else wrote.
        E = _edge_run()
        import tempfile

        db = os.environ.get("LITKB_TEST_DB") or "litkb_test"
        register = E.load_register(manifest["fixture"])
        with tempfile.TemporaryDirectory(prefix="litkb-edge-replay-") as tmp:
            E.run_replay(register, args.csv or manifest["replay_csv"], db=db, tmp=tmp)
    counters, offences = check_edges(manifest, csv_path=args.csv, replay=args.replay)
    for line in offences:
        print(line, file=sys.stderr)
    print(" ".join(f"{k}={v}" for k, v in counters.items()))
    return 0 if edges_ok(counters, edges_manifest_rows(manifest, counters,
                                                       replay=args.replay)) else 1


def _edges_freeze(args):
    for required in ("workstream", "fixture", "out"):
        if not getattr(args, required):
            print(f"edges --freeze needs --{required}", file=sys.stderr)
            return 2
    E = _edge_run()
    repo = Path(args.repo or _repo_root())
    role = args.role
    ws_id = resolve_workstream(args.db, role, args.workstream)
    frozen_at, _baseline = baseline_snapshot(args.db, role, ws_id)
    db_tip, db_tip_note = db_migration_tip(args.db, args.passfile)
    register = E.load_register(args.fixture)
    # THE MODE IS MEASURED HERE AND NOWHERE ELSE. `waits-on-migration` is a fact about this
    # database at this instant; a row that hard-coded it would still be waiting the morning after
    # Kam applied the migration (0028, applied live 2026-09-21 00:07).
    rows = [{"id": r["id"], "mode": E.resolve_mode(r, db_tip)} for r in E.rows_of(register)]
    stem = f"LITKB_EDGE_RUN_{frozen_at.strftime('%Y-%m-%d')}"
    manifest = {
        "kind": EDGES_MANIFEST_KIND,
        "frozen_at": frozen_at.astimezone(dt.timezone.utc).isoformat(),
        "frozen_at_source": "db",
        "repo": str(repo),
        "repo_head": _repo_head(repo),
        "db": args.db,
        "reader_role": role,
        "repo_migration_tip": repo_migration_tip(),
        "db_migration_tip": db_tip,
        "db_migration_tip_note": db_tip_note,
        "url_route_migration": EDGES_URL_MIGRATION,
        "workstream_slug": args.workstream,
        "workstream_id": ws_id,
        "worktree": str(args.worktree or repo),
        "log": str(args.log) if args.log else None,
        "fixture": str(args.fixture),
        "fixture_sha256": _sha256(args.fixture),
        "rows": rows,
        "run_csv": args.csv or str(repo / "Reports" / f"{stem}.csv"),
        "replay_csv": args.replay_csv or str(repo / "Reports" / f"{stem}_replay.csv"),
        # recorded for the READER; the checker uses the module constants (the scout's rule)
        "closed_states": list(CLOSED_STATES),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    modes = {}
    for r in rows:
        modes[r["mode"]] = modes.get(r["mode"], 0) + 1
    print(f"frozen {out} workstream={args.workstream} id={ws_id} rows={len(rows)} "
          f"head={manifest['repo_head'][:12]} repo_tip={manifest['repo_migration_tip']} "
          f"db_tip={db_tip} " + " ".join(f"{k}={v}" for k, v in sorted(modes.items())))
    return 0


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

    s = sub.add_parser("scout", help="did the discovery run actually discover (S1)")
    s.add_argument("--freeze", action="store_true",
                   help="write the manifest BEFORE the run instead of checking one")
    s.add_argument("--manifest", help="the manifest frozen before the run (check mode)")
    s.add_argument("--workstream", help="the workstream slug the run opens (freeze)")
    s.add_argument("--topic", help="the topic the scout is launched on (freeze)")
    s.add_argument("--launch-cmd", dest="launch_cmd", help="the launch command, verbatim (freeze)")
    s.add_argument("--log", help="the stream-json log (freeze records it; check reads it)")
    s.add_argument("--csv", help="the driver's run CSV (default: the manifest's run_csv)")
    s.add_argument("--out", help="where to write the frozen manifest (freeze)")
    s.add_argument("--db", default="litkb", help="the database (default: %(default)s)")
    s.add_argument("--role", default="litkb_reader", help="read role (default: %(default)s)")
    s.add_argument("--repo", help="repository root (default: this instrument's own)")
    s.add_argument("--worktree", help="the worktree the run and the driver use")
    s.add_argument("--passfile", help="pgpass file for the admin read of the DB migration tip")
    s.set_defaults(func=cmd_scout)

    fw = sub.add_parser("first-work",
                        help="did ONE unknown work cross the whole loop unaided (S2)")
    fw.add_argument("--freeze", action="store_true",
                    help="write the manifest BEFORE the run instead of checking one")
    fw.add_argument("--manifest", help="the manifest frozen before the run (check mode)")
    fw.add_argument("--workstream", help="the workstream slug the run works in (freeze)")
    fw.add_argument("--hunt-request", dest="hunt_request",
                    help="the drop-off this run is following up (freeze; recorded, not graded)")
    fw.add_argument("--log", help="the headless stream-json log; absent, operator_interventions "
                                  "is computed from the database alone")
    fw.add_argument("--review", help="the review whose citations Codex graded")
    fw.add_argument("--codex-report", dest="codex_report", help="the Codex report JSON")
    fw.add_argument("--out", help="where to write the frozen manifest (freeze)")
    fw.add_argument("--db", default="litkb", help="the database (default: %(default)s)")
    fw.add_argument("--role", default="litkb_reader", help="read role (default: %(default)s)")
    fw.add_argument("--repo", help="repository root (default: this instrument's own)")
    fw.add_argument("--passfile", help="pgpass file for the admin read of the DB migration tip")
    fw.set_defaults(func=cmd_first_work)

    e = sub.add_parser("edges",
                       help="did EVERY edge class end in the state the register adjudicated (S3)")
    e.add_argument("--freeze", action="store_true",
                   help="write the manifest BEFORE the run instead of checking one")
    e.add_argument("--manifest", help="the manifest frozen before the run (check mode)")
    e.add_argument("--workstream", help="the workstream slug the run works in (freeze)")
    e.add_argument("--fixture", help="the edge-case register (freeze); its sha256 is frozen with it")
    e.add_argument("--log", help="the stream-json log (freeze records it)")
    e.add_argument("--csv", help="the run CSV (default: the manifest's run_csv, or replay_csv "
                                 "with --replay)")
    e.add_argument("--replay-csv", dest="replay_csv", help="the replay CSV (freeze)")
    e.add_argument("--replay", action="store_true",
                   help="EXECUTE the deterministic replay on LITKB_TEST_DB and grade it")
    e.add_argument("--no-execute", dest="no_execute", action="store_true",
                   help="with --replay: grade a replay CSV somebody else wrote, run nothing")
    e.add_argument("--out", help="where to write the frozen manifest (freeze)")
    e.add_argument("--db", default="litkb", help="the database (default: %(default)s)")
    e.add_argument("--role", default="litkb_reader", help="read role (default: %(default)s)")
    e.add_argument("--repo", help="repository root (default: this instrument's own)")
    e.add_argument("--worktree", help="the worktree the run and the driver use")
    e.add_argument("--passfile", help="pgpass file for the admin read of the DB migration tip")
    e.set_defaults(func=cmd_edges)

    c = sub.add_parser("codex", help="did the adversarial read actually read every citation")
    c.add_argument("--review", required=True, help="the review the report claims to be about")
    c.add_argument("--context", required=True, help="the block context that was sent with it")
    c.add_argument("--report", help="the wrapper's JSON report. Omit it, with --mutate N, to "
                                    "PREPARE the mutated review instead of grading one")
    c.add_argument("--mutate", type=int, metavar="N",
                   help="plant a CAUSATION claim on citation N, leaving its quote byte-identical, "
                        "and require the report for the mutated review to flag it")
    c.add_argument("--mutated-out", dest="mutated_out",
                   help=f"where the mutated review goes (default: <review>{MUTATED_SUFFIX})")
    c.set_defaults(func=cmd_codex)

    f = sub.add_parser("preflight", help="the checks a session runs BEFORE its first hunt")
    f.add_argument("--db", default="litkb", help="the database (default: %(default)s)")
    f.add_argument("--repo", help="repository root (default: this instrument's own)")
    f.add_argument("--passfile", help="pgpass file for the admin read of the DB migration tip")
    f.add_argument("--soak-csv", dest="soak_csv", help="(tests) a soak CSV other than Reports/LITKB_SOAK.csv")
    f.add_argument("--mcp-json", dest="mcp_json", help="(tests) an .mcp.json other than the repo's")
    f.set_defaults(func=cmd_preflight)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

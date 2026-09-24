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
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py readability --freeze \
        --workstream <slug> [--workstream <slug> ...] --out <manifest.json>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py readability --manifest <manifest.json>
    PYTHONUTF8=1 LITKB_TEST_DB=litkb_test_wN py -3.12 qc/instruments/litkb_acceptance.py readability \
        --fire <kill|lease|cap|probe|scan|book|quarantine> [--manifest <manifest.json>]
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acceptance.py hardening --freeze \
        --workstream ladder-1 --out <manifest.json> [--date YYYY-MM-DD]
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acceptance.py hardening --manifest <m>
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 qc/instruments/litkb_acceptance.py \
        hardening --fire <name|all> --db litkb_test_wN
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_wN py -3.12 qc/instruments/litkb_acceptance.py \
        hardening --replay --manifest <m> --db litkb_test_wN

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
ONE genuinely unknown work cross the whole loop unaided), landing with S2; `edges` (did every edge
class end in the state the register adjudicated), landing with S3; `readability` (is everything
acquired readable or classified, and do the (c) known-bads still fire), landing with S4; `hardening`
(the acquisition ladder's gated counters, each owned by a `litkb_hardening_<builder>.py` module and
only loaded here; its freeze, grade, fire and replay are documented where the section begins), landing
with S4.5. `run`,
`synthesis` and `soak` land with their own sessions and are deliberately absent until then
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

WHAT `readability` COUNTS (S4; docs/SCHEMAS.md "LITKB readability acceptance manifest" is the one
home of each counter's definition). `--freeze` writes, BEFORE the drain: the database's own clock,
the database's name AND oid, the repo head and whether the grading code is committed, both migration
tips, the reader role, main plus the named workstreams (slug -> id), the code constants
(`EXTRACT_PAGE_CAP`, `OCR_CHUNK_PAGES`, the lease seconds), the literature, quarantine and artifact
roots, the BED (every active current file with no block, measured by the page probe), and a
`manifest_sha256` over all of it. `--manifest` REFUSES a manifest edited after that (the hash), one
frozen under other constants, one from another database (name or oid), and a workstream id that no
longer names its slug — nothing is graded then. Otherwise it prints ONE line: the nine GATED counters
in the plan's order (each imported from the module that owns it — this file re-implements none), then
the REPORTED ones, and exits 0 only when every gated counter is 0 and `waits_on_migration` is 0. A
database without 0029/0030/0031 WAITS: the counters those relations carry print `unread` and it exits
1. `--fire <name>` re-runs one (c) known-bad on a WORKER database through builder A's and B's fire
functions (it owns that database: suite lock, reset, migrate — and refuses `litkb`), prints the
guard-ON control and the known-bad, and exits 0 only when the control reads 0 and the named counter
moved to its known-bad value.

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
file into a worktree. Nothing here writes to a database except `readability --fire`, `hardening --fire`
and `hardening --replay`, and those only to a WORKER database (`litkb_test*`; `litkb` is refused before
a connection opens, and `hardening` also refuses the RESERVED workers and never defaults to a shared one). It is not run on Colab, so it does not
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


def _register_sha256(path):
    """sha256 of the edge register's CONTENT: bytes with every CRLF folded to LF.

    The register is an authored JSON file under `* text=auto`, so git hands a Windows checkout
    CRLF bytes and a Linux checkout LF bytes for the same commit. S3's manifest froze the LF
    hash; the first re-run after a fresh checkout (2026-09-21) was refused as "edited after the
    freeze" with nothing edited — the byte guard could not tell an edit from a newline rewrite.
    Folding CRLF before hashing makes the guard about what is graded (the parsed rows) and keeps
    every manifest frozen on LF bytes valid. A real edit still changes the hash (test_litkb_edges
    c3/c3b). NOT for the HTML fixtures: those are recorded bytes, marked `binary` in
    .gitattributes, and hash as bytes on purpose."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()


def _fixture_committed(repo, fixture):
    """True when the register on disk equals HEAD's copy (git's own eol-normalised diff), False
    when it carries uncommitted edits, None when git cannot say. S3 froze a re-adjudicated
    register from the working tree fourteen minutes before it was committed, so `repo_head` in
    that manifest names a commit whose register hashes differently; this flag says so at freeze."""
    try:
        rel = os.path.relpath(Path(fixture).resolve(), Path(repo).resolve())
        rc = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--", rel],
                            capture_output=True).returncode
    except (OSError, ValueError):
        return None
    return {0: True, 1: False}.get(rc)


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
            fixture_sha = _register_sha256(fixture)
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
        "fixture_sha256": _register_sha256(args.fixture),
        "fixture_committed": _fixture_committed(repo, args.fixture),
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


# ── readability: everything acquired is readable or classified (S4) ───────────────────────
#
# The plan's "### S4" (b) is a COMMAND and (c) is a set of known-bads a cold session can re-fire.
# `--freeze` writes the manifest BEFORE the drain; `--manifest` prints one line of gated then
# reported counters and exits 0 only when every gated counter is 0 and nothing waits on a migration;
# `--fire <name>` runs one (c) known-bad on a WORKER database and says whether it FIRED.
#
# NOTHING HERE RE-IMPLEMENTS A COUNTER. Each is the function that owns it, imported:
# `litkb.readability.classify` (unclassified_acquired_files and the per-class counts, with the queue
# step), `litkb.extract.queue` (stale_leases, duplicate_blocks, resumed_content_hash_mismatches,
# books_extracted, over_cap_bound, scans_ocr_unrouted, mutated_leases_accepted),
# `litkb.quarantine.quarantined_without_db_state`, `litkb.extract.references_coverage`
# (files_without_reference_stage, reference_anchor_rate) and `litkb.ops.retire` (the two superseded-run
# counts). A second copy of any of them here would be a second definition of the thing graded.

READABILITY_MANIFEST_KIND = "litkb-readability"

#: The GATED counters, in the plan's own order ("### S4" (b)). Every one must read 0.
READABILITY_GATED = ("unclassified_acquired_files", "stale_leases", "duplicate_blocks",
                     "resumed_content_hash_mismatches", "books_extracted",
                     "quarantined_without_db_state", "over_cap_bound", "scans_ocr_unrouted",
                     "mutated_leases_accepted")

#: The relations the gated counters read, and the migration that creates each. A database missing
#: any of them WAITS ON MIGRATION: its counters cannot be read, and the command exits 1 saying so.
#: This is "the db tip is below 31" measured by the READER itself (`to_regclass`), because the tip
#: (`litkb_meta.schema_migrations`) is readable by the owner login alone.
READABILITY_RELATIONS = (("litkb.extraction_jobs", 29), ("litkb.quarantine_payloads", 30),
                         ("litkb.run_retirements", 31))

#: Which gated counters each migration's relation is the substrate of (the rest read without it).
_NEEDS = {29: ("stale_leases", "duplicate_blocks", "resumed_content_hash_mismatches",
               "books_extracted", "over_cap_bound", "scans_ocr_unrouted", "mutated_leases_accepted"),
          30: ("quarantined_without_db_state",)}

#: The (c) known-bads `--fire` re-runs, by name (plan "### S4" (c), in its order).
FIRE_NAMES = ("kill", "lease", "cap", "probe", "scan", "book", "quarantine")

#: `--fire` writes, resets and migrates its database: it refuses this name (the `--replay` rule).
FORBIDDEN_FIRE_DB = "litkb"

#: The manifest fields that are the CODE's constants at freeze. They are recorded for the reader
#: and REFUSED at grading when the code now says otherwise: a manifest frozen under a different page
#: cap grades a different question (the scout's rule — the vocabulary is the module's, never the
#: manifest's). The counters always use the module constants.
def _readability_constants():
    from litkb.extract import probe as P
    from litkb.extract import queue as Q

    return {"extract_page_cap": P.EXTRACT_PAGE_CAP, "ocr_chunk_pages": Q.OCR_CHUNK_PAGES,
            "lease_seconds": Q.LEASE_SECONDS}


def _canonical_sha(manifest):
    """sha256 of the manifest's CONTENT without its own `manifest_sha256`: sorted keys, compact
    separators, UTF-8. What `--manifest` recomputes to refuse a field edited after the freeze."""
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _code_committed(repo):
    """True when the grading code (the litkb package and this instrument) has no uncommitted change
    at freeze — `git status --porcelain` over those paths is empty; False when it has one; None when
    git cannot say. `repo_head` names the commit; this says whether the code that ran IS that commit
    (the `fixture_committed` lesson of S3)."""
    try:
        r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--",
                            "Scripts/pipeline/litkb", "Scripts/qc/instruments/litkb_acceptance.py"],
                           capture_output=True, text=True)
    except OSError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() == ""


def _db_identity(conn):
    """(name, oid) of the database this connection is on. The oid is what a DROP + CREATE of a
    database with the same name changes, so a manifest names ONE database, not a name."""
    name, oid = conn.execute("SELECT current_database(), (SELECT oid FROM pg_database "
                             "WHERE datname = current_database())").fetchone()
    return name, int(oid)


def _missing_relations(conn):
    """[(relation, migration)] the gated counters need that this database does not have."""
    return [(rel, mig) for rel, mig in READABILITY_RELATIONS
            if not conn.execute("SELECT to_regclass(%s) IS NOT NULL", (rel,)).fetchone()[0]]


#: THE BED: every current, active file version in main and in each named workstream holding no
#: block at all — the plan's own "Test-set commands" query, widened to the manifest's workstreams.
_BED_SQL = """
SELECT f.file_id::text, f.rel_path, f.sha256, 'main' AS scope
  FROM litkb.main_files f
 WHERE f.status = 'active' AND NOT EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id = f.file_id)
UNION ALL
SELECT f.file_id::text, f.rel_path, f.sha256, f.view_workstream_id::text
  FROM litkb.ws_files f
 WHERE f.view_workstream_id = ANY(%(ws)s::uuid[]) AND f.status = 'active'
   AND NOT EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id = f.file_id)
 ORDER BY 2, 1"""


def _bed(conn, ws_ids, root):
    """[{file_id, rel_path, sha256, scope, pages, image_pages, probe_error}] — one row per file (main's
    scope wins). pages / image_pages are measured NOW from the bytes (`litkb.extract.probe`), never the
    stored page count or page-1 flag; a probe that raises is recorded as its error, never guessed."""
    from litkb.extract import probe as P

    out, seen = [], set()
    for fid, rel, sha, scope in conn.execute(_BED_SQL, {"ws": list(ws_ids)}).fetchall():
        if fid in seen:
            continue
        seen.add(fid)
        row = {"file_id": fid, "rel_path": rel, "sha256": sha, "scope": scope,
               "pages": None, "image_pages": None, "probe_error": None}
        p = Path(root) / str(rel)
        if not p.is_file():
            row["probe_error"] = "not on disk"
        else:
            try:
                row["pages"] = P.probe_pages(p)
                if row["pages"] <= P.EXTRACT_PAGE_CAP:
                    row["image_pages"] = P.image_page_numbers(p)
            except P.ProbeError as e:
                row["probe_error"] = str(e)[:300]
        out.append(row)
    return out


def _readability_freeze(args):
    if not args.out or not args.workstream:
        print("readability --freeze needs --workstream <slug> (repeatable) and --out", file=sys.stderr)
        return 2
    args.db = args.db or "litkb"
    from litkb.acquire.store import LITERATURE_ROOT
    from litkb.extract import queue as Q
    from litkb.extract import references as REF
    from litkb.quarantine import QUARANTINE_DIR

    repo = Path(args.repo or _repo_root())
    lit = Path(args.root or os.environ.get("LITKB_LITERATURE_ROOT") or LITERATURE_ROOT)
    workstreams = []
    for slug in args.workstream:
        wid = resolve_workstream(args.db, args.role, slug)
        if wid is None:
            print(f"readability --freeze: no open workstream {slug!r} on {args.db}", file=sys.stderr)
            return 2
        workstreams.append({"slug": slug, "id": wid})
    conn = _connect(args.db, args.role, autocommit=False)
    try:
        from psycopg import IsolationLevel

        conn.isolation_level = IsolationLevel.REPEATABLE_READ
        with conn.transaction():
            # THE FREEZE INSTANT IS THE DATABASE'S (first-work's rule), and the bed is read in the
            # same snapshot, so "the bed at freeze" is one fact about one moment
            frozen_at = conn.execute("SELECT now()").fetchone()[0]
            name, oid = _db_identity(conn)
            bed = _bed(conn, [w["id"] for w in workstreams], lit)
    finally:
        conn.close()
    db_tip, db_tip_note = db_migration_tip(args.db, args.passfile)
    manifest = {
        "kind": READABILITY_MANIFEST_KIND,
        "frozen_at": frozen_at.astimezone(dt.timezone.utc).isoformat(),
        "frozen_at_source": "db",
        "repo": str(repo),
        "repo_head": _repo_head(repo),
        "code_committed": _code_committed(repo),
        "db": args.db,
        "db_name": name,
        "db_oid": oid,
        "reader_role": args.role,
        "repo_migration_tip": repo_migration_tip(),
        "db_migration_tip": db_tip,
        "db_migration_tip_note": db_tip_note,
        "required_migration": READABILITY_MIGRATION,
        # main is ALWAYS in the universe; these are the workstreams graded beside it (the plan:
        # "all workstreams in the manifest, not main only")
        "workstreams": [{"slug": "main", "id": None}] + workstreams,
        "literature_root": str(lit),
        "quarantine_root": str(lit / QUARANTINE_DIR),
        # the roots the digest counters read (builder-A Q3): the literature root (the PDFs the clean
        # reference is recomputed from) and the artifact root (job artifacts are recorded by absolute
        # path in extraction_jobs.artifact_path; the root is recorded so a cold reader can find them)
        "derived_root": str(Q.derived_root()),
        "references_derived_root": str(REF.DERIVED_ROOT),
        **_readability_constants(),
        "gated": list(READABILITY_GATED),
        "bed": bed,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(f"frozen {out} db={name} workstreams={len(workstreams)} bed={len(bed)} "
          f"head={manifest['repo_head'][:12]} code_committed={manifest['code_committed']} "
          f"repo_tip={manifest['repo_migration_tip']} db_tip={db_tip}")
    return 0


#: The migration whose relations the gated counters need (the highest in READABILITY_RELATIONS).
READABILITY_MIGRATION = max(m for _r, m in READABILITY_RELATIONS)


def load_readability_manifest(path):
    """The manifest, REFUSED (SystemExit, nothing graded) when its kind is wrong, a field was edited
    after the freeze (`manifest_sha256` no longer matches its content) or a code constant it recorded
    is not the code's now."""
    manifest = json.loads(read_text(path))
    # BEGIN guard: a readability manifest edited after its freeze is refused
    if manifest.get("kind") != READABILITY_MANIFEST_KIND:
        raise SystemExit(f"litkb_acceptance readability: {path} is not a {READABILITY_MANIFEST_KIND!r} "
                         f"manifest (kind {manifest.get('kind')!r}). Nothing was graded.")
    if manifest.get("manifest_sha256") != _canonical_sha(manifest):
        raise SystemExit(f"litkb_acceptance readability: {path} was edited after its freeze "
                         "(manifest_sha256 does not match its content). Re-freeze it. Nothing was graded.")
    # END guard: a readability manifest edited after its freeze is refused
    now = _readability_constants()
    changed = {k: (manifest.get(k), v) for k, v in now.items() if manifest.get(k) != v}
    if changed:
        raise SystemExit("litkb_acceptance readability: the code's constants are not the manifest's "
                         f"({changed}); a manifest frozen under other constants grades a different "
                         "question. Re-freeze it. Nothing was graded.")
    return manifest


def _check_identity(conn, manifest):
    """Refuse (SystemExit) a manifest frozen on another database, or on a database since recreated
    under the same name, and a workstream whose id no longer names its slug."""
    name, oid = _db_identity(conn)
    # BEGIN guard: a manifest is graded only on the database it was frozen on
    if (name, oid) != (manifest.get("db_name"), manifest.get("db_oid")):
        raise SystemExit(f"litkb_acceptance readability: the manifest was frozen on database "
                         f"{manifest.get('db_name')!r} (oid {manifest.get('db_oid')}); this is {name!r} "
                         f"(oid {oid}). Nothing was graded.")
    # END guard: a manifest is graded only on the database it was frozen on
    for w in manifest.get("workstreams") or []:
        if w.get("id") is None:
            continue
        row = conn.execute("SELECT slug FROM litkb.workstreams WHERE id = %s", (w["id"],)).fetchone()
        if row is None or row[0] != w["slug"]:
            raise SystemExit(f"litkb_acceptance readability: workstream id {w['id']} does not name "
                             f"{w['slug']!r} on this database. Nothing was graded.")


def check_readability(manifest, *, conn=None, db=None):
    """(gated {name: int | None}, reported {name: value}, [offence lines]). None = UNREAD: the
    relation the counter reads is absent (`waits_on_migration`). `conn` is injected by the tests."""
    from litkb import quarantine as Qr
    from litkb import readability as R
    from litkb.extract import queue as Q
    from litkb.extract import references_coverage as RC
    from litkb.ops import retire as RT

    own = conn is None
    conn = conn or _connect(db or manifest["db"], manifest["reader_role"])
    offences = []
    try:
        _check_identity(conn, manifest)
        root = Path(manifest["literature_root"])
        ws_ids = [w["id"] for w in manifest.get("workstreams") or [] if w.get("id")]
        missing = _missing_relations(conn)
        absent = {m for _r, m in missing}
        for rel, mig in missing:
            offences.append(f"waits on migration {mig:04d}: {rel} is absent, so the counters that read it "
                            "cannot be read")
        unread = {c for m in absent for c in _NEEDS.get(m, ())}

        gated = dict.fromkeys(READABILITY_GATED)
        res = R.classify(conn, ws_ids, root=root)
        gated["unclassified_acquired_files"] = res["counters"]["unclassified_acquired_files"]
        if "quarantined_without_db_state" not in unread:
            n, paths = Qr.quarantined_without_db_state(conn, root=root)
            gated["quarantined_without_db_state"] = n
            offences += [f"quarantined without a database row: {p}" for p in paths[:20]]
        if 29 not in absent:
            for name, value in Q.counters(conn, root, ws_ids).items():
                gated[name] = value
        offences += [f"unclassified: {r['rel_path']} ({r['evidence'][:160]})" for r in res["rows"]
                     if r["row_kind"] in ("file", "staging") and r["class"] is None][:50]

        reported = {}
        rc = RC.reference_counters(conn)
        reported["files_without_reference_stage"] = rc["files_without_reference_stage_ratio"]
        reported["reference_anchor_rate"] = rc["reference_anchor_rate"]
        for k, v in res["counters"].items():
            if k != "unclassified_acquired_files":
                reported[k] = v
        if 31 not in absent:
            reported["superseded_runs_unretired"] = RT.superseded_runs_unretired(conn)
            reported["superseded_runs_held_by_evidence"] = RT.superseded_runs_held_by_evidence(conn)["count"]
        else:
            reported["superseded_runs_unretired"] = reported["superseded_runs_held_by_evidence"] = None
        bed = {b["file_id"] for b in manifest.get("bed") or []}
        still = {r[0] for r in conn.execute(
            "SELECT f.id::text FROM litkb.files f WHERE f.id = ANY(%s::uuid[]) AND NOT EXISTS "
            "(SELECT 1 FROM litkb.blocks b WHERE b.file_id = f.id)", (list(bed),)).fetchall()}
        reported["bed_files"] = len(bed)
        reported["bed_without_blocks"] = len(still)
        reported["waits_on_migration"] = int(bool(missing))
    finally:
        if own:
            conn.close()
    return gated, reported, offences


def readability_ok(gated, reported):
    """0 on every gated counter, none UNREAD, and nothing waiting on a migration."""
    return (all(v == 0 for v in gated.values()) and reported.get("waits_on_migration") == 0)


def _fmt(v):
    if v is None:
        return "unread"
    if isinstance(v, tuple):
        return f"{v[0]}/{v[1]}"
    return str(v)


def readability_line(gated, reported):
    """ONE line: the gated counters in the plan's order, then the reported ones."""
    return " ".join(f"{k}={_fmt(v)}" for k, v in (*gated.items(), *reported.items()))


#: The worker databases `--fire` may reset: `litkb.db.provision.provision_workers` names them
#: `litkb_test_w<N>`. The shared `litkb_test`, `litkb_test_wmatching` and the rest are not workers.
_FIRE_WORKER_DB = re.compile(r"litkb_test_w\d+")


def reserved_worker_dbs(plan=None):
    """The RESERVED worker databases, read from their ONE home: the per-session protocol line of
    LITKB_WORKPLAN.md ("free: w3, w7, w9; w2, w8, w10 and w11 are RESERVED ..."). Parsed, not copied,
    so the plan and `--fire` cannot disagree. FAIL CLOSED: a plan whose line cannot be read raises."""
    text = Path(plan or PLAN_DEFAULT).read_text(encoding="utf-8")
    m = re.search(r"free:\s*[^;]*;\s*(.*?)\s+are\s+RESERVED", re.sub(r"\s+", " ", text))
    names = re.findall(r"\bw(\d+)\b", m.group(1)) if m else []
    if not names:
        raise SystemExit(f"litkb_acceptance: the RESERVED worker databases could not be read from {plan or PLAN_DEFAULT} "
                         f"(its 'free: …; … are RESERVED' line); --fire refuses to run without that list")
    return tuple(f"litkb_test_w{n}" for n in names)


def _fire_db():
    """The database `--fire` resets: LITKB_TEST_DB, set EXPLICITLY to a worker (`litkb_test_w<N>`).
    Unset, it used to fall back to the SHARED `litkb_test`, which a cold `--fire` would then reset
    under whatever else uses it (auditor-C, DB SAFETY)."""
    db = os.environ.get("LITKB_TEST_DB")
    # BEGIN guard: --fire runs only on an explicitly named worker database
    if not db or not _FIRE_WORKER_DB.fullmatch(db.strip()):
        raise SystemExit(f"litkb_acceptance readability --fire resets its database, so it runs only on a "
                         f"worker database named explicitly: set LITKB_TEST_DB=litkb_test_w<N> (got {db!r}; "
                         f"the shared litkb_test is never reset from here)")
    # END guard: --fire runs only on an explicitly named worker database
    # BEGIN guard: --fire never resets a RESERVED worker database
    if db.strip() in reserved_worker_dbs():
        raise SystemExit(f"litkb_acceptance readability --fire refuses {db.strip()!r}: it is RESERVED "
                         f"(LITKB_WORKPLAN.md, the per-session protocol line: {', '.join(reserved_worker_dbs())}); "
                         f"resetting it breaks whoever holds it (auditor-C reset w10 this way)")
    # END guard: --fire never resets a RESERVED worker database
    return db.strip()


#: What each (c) row's CONTROL arm must also show — the plan's own clause, not only its counter
#: (auditor-C N2): cap "refused with the over-page-cap reason, never started"; scan "`scan-needs-ocr`,
#: never 'extracted, 0 chars'"; book "the `book` class"; lease "the ownership gate goes RED".
def _control_clause(name, g, classes=None):
    """-> (ok, text) for one fire's guarded arm ``g`` (a queue_fire result arm)."""
    jobs = [tuple(j) for j in g.get("jobs") or []]
    refusals = {(j[0], j[1]) for j in jobs}
    if name == "cap":
        # BEGIN guard: the cap fire's control is refused over-page-cap and never started
        ok = refusals == {("refused", "over-page-cap")} and g.get("claimed") == 0 and g.get("blocks") == 0
        # END guard: the cap fire's control is refused over-page-cap and never started
        return ok, f"refusals={sorted(refusals)} claimed={g.get('claimed')} blocks={g.get('blocks')}"
    if name == "scan":
        # BEGIN guard: the scan fire's control is scan-needs-ocr, never an ok run
        ok = refusals == {("refused", "scan-needs-ocr")} and g.get("runs_ok") == 0 and g.get("blocks") == 0
        # END guard: the scan fire's control is scan-needs-ocr, never an ok run
        return ok, f"refusals={sorted(refusals)} runs_ok={g.get('runs_ok')} blocks={g.get('blocks')}"
    if name == "book":
        cls = (classes or {}).get(g.get("file_id"))
        # BEGIN guard: the book fire's control is refused book and classed book
        ok = refusals == {("refused", "book")} and g.get("blocks") == 0 and cls == "book"
        # END guard: the book fire's control is refused book and classed book
        return ok, f"refusals={sorted(refusals)} blocks={g.get('blocks')} class={cls}"
    if name == "lease":
        # BEGIN guard: the lease fire's control is refused by the ownership gate and lands nothing
        ok = "lease refused" in str(g.get("raised") or "") and g.get("blocks_after_t1") == 0
        # END guard: the lease fire's control is refused by the ownership gate and lands nothing
        return ok, f"gate_raised={int(bool(g.get('raised')))} blocks_after_stale_finish={g.get('blocks_after_t1')}"
    return True, ""


def _probe_clause(on, unclassified_before, unclassified_after):
    """The plan's probe row, all three: never bound, classed `probe-error` (its quarantine row's
    reason), `unclassified_acquired_files` unchanged (auditor-C N1)."""
    # BEGIN guard: the probe fire's control is not bound, classed probe-error, and leaves unclassified unchanged
    return (on["probe_refused"] == 1 and on["bound"] == 0 and on.get("quarantine_reason") == "probe-error"
            and unclassified_after == unclassified_before)
    # END guard: the probe fire's control is not bound, classed probe-error, and leaves unclassified unchanged


def _counter_arms(out, counter):
    """(baseline, control, known-bad) of one queue_fire result dict."""
    base = out["baseline"][counter]
    return base, out["guarded"][counter], out["mutated"][counter]


def readability_fire(name, *, db, workdir, conn=None):
    """Run ONE (c) known-bad on a worker database. -> {"name", "lines": [...], "fired": bool}.

    `conn` (the tests pass their fixture's) is the worker database's OWNER login and is used as is;
    without it this function OWNS the database: it takes the suite's advisory lock (so it can never
    run under a pytest session on the same database), resets and migrates it, and the control then
    reads 0 by construction. With a shared connection the verdict reads DELTAS from the fire's own
    baseline, which on a fresh database are the absolute values."""
    try:
        from litkb.db import connect as c
    except RuntimeError as e:     # connect.py itself refuses, at import, an LITKB_TEST_DB outside litkb_test*
        raise SystemExit(f"litkb_acceptance readability --fire refuses {db!r}: {e}") from e

    # BEGIN guard: --fire refuses the live database before it opens a connection
    if str(db).strip().lower() == FORBIDDEN_FIRE_DB or not c.is_test_db(db):
        raise SystemExit(f"litkb_acceptance readability --fire writes, resets and migrates its database: it "
                         f"refuses {db!r}. Set LITKB_TEST_DB to a worker database (litkb_test*).")
    # END guard: --fire refuses the live database before it opens a connection
    if name not in FIRE_NAMES:
        raise SystemExit(f"readability --fire: unknown known-bad {name!r} (one of {', '.join(FIRE_NAMES)})")
    from litkb import quarantine as Qr
    from litkb import readability as R
    from litkb.db import migrate
    from litkb.extract import queue_fire as F

    own = conn is None
    lock = _edge_run()._SUITE_LOCK
    if own:
        conn = c.connect(db, "litkb_test", autocommit=True)
        conn.execute("SELECT pg_advisory_lock(%s)", (lock,))
        migrate.reset(conn)
        migrate.apply(conn)
    work = Path(workdir)
    lines, fired = [], False
    try:
        if name in ("cap", "book", "scan", "lease"):
            fn, counter = {"cap": (F.fire_cap, "over_cap_bound"), "book": (F.fire_book, "books_extracted"),
                           "scan": (F.fire_scan, "scans_ocr_unrouted"),
                           "lease": (F.fire_lease, "mutated_leases_accepted")}[name]
            try:
                out = fn(conn, work)
            except FileNotFoundError as e:
                # fire_scan needs the REAL Anderson 1957 copy and its recorded no-OCR artifact: on a
                # machine without them the known-bad CANNOT RUN — never reported as fired, never a pass
                lines.append(f"fire={name} CANNOT RUN on this machine: {e}")
                return {"name": name, "lines": lines, "fired": False}
            base, control, bad = _counter_arms(out, counter)
            classes = None
            if name == "book":
                all_ws = [r[0] for r in conn.execute("SELECT id FROM litkb.workstreams").fetchall()]
                res = R.classify(conn, all_ws, root=work, with_works=False)
                classes = {r["file_id"]: r["class"] for r in res["rows"] if r["row_kind"] == "file"}
            clause_ok, clause = _control_clause(name, out["guarded"], classes)
            lines.append(f"fire={name} arm=control {counter}={control} baseline={base} "
                         f"blocks={out['guarded'].get('blocks')} {clause}")
            lines.append(f"fire={name} arm=known-bad {counter}={bad} baseline={base} "
                         f"blocks={out['mutated'].get('blocks')}")
            fired = (control - base == 0) and (bad - base == 1) and clause_ok
        elif name == "kill":
            pdfs = [F.constructed_pdf(work / "Validation" / f"Kill_{i}.pdf", 2 + i, note=f"readability fire {i} {F._salt()}")
                    for i in range(3)]
            out = F.fire_kill(conn, work, pdfs, synthetic_delay=4, lease=6, timeout=600,
                              reference=F.synthetic_reference)
            base, after = out["baseline"], out["counters"]
            stale = out["before_rerun"]["stale_leases_after_expiry"]
            equal = all(d["equal"] for d in out["digests"])
            resumed = any(j[2] > 1 for js in out["jobs"] for j in js)
            lines.append("fire=kill arm=control " + " ".join(f"{k}={v}" for k, v in base.items()))
            lines.append(f"fire=kill arm=killed state={out['state']} killed_after_s={out['killed_after_s']} "
                         f"stale_leases={stale} (baseline {base['stale_leases']})")
            lines.append("fire=kill arm=resumed " + " ".join(f"{k}={v}" for k, v in after.items())
                         + f" digests_equal={int(equal)} resumed_jobs={int(resumed)} rerun_exit={out['rerun_exit']}")
            fired = (out["state"] == "killed" and stale - base["stale_leases"] == 1 and equal and resumed
                     and out["rerun_exit"] == 0 and all(after[k] == base[k] for k in after))
        elif name == "probe":
            def unclassified():
                all_ws = [r[0] for r in conn.execute("SELECT id FROM litkb.workstreams").fetchall()]
                return R.unclassified_acquired_files(conn, all_ws, root=work / "guard_on")[0]

            before = unclassified()
            on = R.fire_probe(db, root=work / "guard_on", guard=True)
            after = unclassified()
            off = R.fire_probe(db, root=work / "guard_off", guard=False)
            lines.append(f"fire=probe arm=control probe_refused={on['probe_refused']} bound={on['bound']} "
                         f"class={on.get('quarantine_reason')} unclassified_acquired_files={after} "
                         f"(before {before}) status={on['status']}")
            lines.append(f"fire=probe arm=known-bad bound={off['bound']} bound_pages_null={off['bound_pages_null']} "
                         f"status={off['status']}")
            fired = _probe_clause(on, before, after) and off["bound"] == 1
        else:  # quarantine
            out = Qr.fire_quarantine(conn, root=work)
            lines.append(f"fire=quarantine arm=control quarantined_without_db_state={out['before']}")
            lines.append(f"fire=quarantine arm=known-bad quarantined_without_db_state="
                         f"{out['quarantined_without_db_state']} planted={out['planted']}")
            fired = out["before"] == 0 and out["quarantined_without_db_state"] == 1
    finally:
        if own:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (lock,))
            except Exception:               # noqa: BLE001 — a closed connection unlocks itself
                pass
            conn.close()
    lines.append(f"fire={name} {'FIRED' if fired else 'DID NOT FIRE'}")
    return {"name": name, "lines": lines, "fired": fired}


def cmd_readability(args):
    if args.fire:
        db = _fire_db()
        if args.manifest:
            m = load_readability_manifest(args.manifest)
            print(f"manifest {args.manifest} frozen_at={m['frozen_at']} db={m['db']} (graded constants match)")
        import tempfile

        with tempfile.TemporaryDirectory(prefix="litkb-readability-fire-", ignore_cleanup_errors=True) as tmp:
            out = readability_fire(args.fire, db=db, workdir=tmp)
        for line in out["lines"]:
            print(line)
        return 0 if out["fired"] else 1
    if args.freeze:
        return _readability_freeze(args)
    if not args.manifest:
        print("litkb_acceptance readability needs --manifest (or --freeze, or --fire)", file=sys.stderr)
        return 2
    manifest = load_readability_manifest(args.manifest)
    gated, reported, offences = check_readability(manifest, db=args.db)
    for line in offences:
        print(line, file=sys.stderr)
    print(readability_line(gated, reported))
    return 0 if readability_ok(gated, reported) else 1


# ── hardening: the acquisition ladder, part 1 (S4.5) ──────────────────────────────────────
#
# The plan's "### S4.5" (b) is a COMMAND over counters six builders own. `edges`' and `readability`'s
# shape, with one difference that is the whole of it: NOTHING HERE COMPUTES A COUNTER. Every counter
# is a function in a `qc/instruments/litkb_hardening_<builder>.py` module (brief-CONTRACTS.md,
# "Counters and fires"), loaded BY PATH, and this command only freezes, loads, runs, compares and
# prints. A gated counter no module defines prints `unread` and FAILS — a gate whose module has not
# landed is not a passing gate.
#
#   --freeze   the manifest BEFORE the run: the database's clock and identity, the repo head, the
#              workstream, every probe file the counters read (path + content hash), the promised
#              report and referee paths, the cassette index's identity, the gated and reported lists
#              with bounds, and THE RUN ROWS (S4.5 decision D9) chosen by NAMED selectors.
#   --manifest grade: one line, exit 0 iff every gated counter meets its bound.
#   --fire     one (or every) module FIRE on a worker database: reset, control, reset, known-bad.
#   --replay   the register replayed through the recorded cassette inside a socket guard that allows
#              nothing; writes the replay summary the replay counters read.

HARDENING_MANIFEST_KIND = "litkb-hardening"

#: The GATED counters with their bounds, in the plan's (b) order ("### S4.5" Done-state (b)), then
#: builder A's one addition: `replay_rows_disagreeing` is the gate the plan's (c) row "a cassette's
#: 403 edited to 200 -> the replay disagrees with the register -> RED" needs and (b) does not name
#: (builder-A report, open question). The vocabulary is THIS constant; the manifest records it for the
#: reader and a manifest frozen under a different list is refused (the scout's rule).
HARDENING_GATED = (
    ("rehunt_route_spends", "=0"), ("relation_probe_rows", ">=1"), ("key_derivation_crashes", "=0"),
    ("known_bad_relands", "=0"), ("proposals_unadjudicated", "=0"), ("bad_file_untyped", "=0"),
    ("blocked_untyped", "=0"), ("quarantines_without_reason", "=0"), ("operator_binds_unproposed", "=0"),
    ("preprints_sent_to_shadow", "=0"), ("post_freeze_sent", "=0"), ("shadow_miss_booked_blocked", "=0"),
    ("bban_probe_hits_not_landed", "=0"), ("challenge_at_200_unbooked", "=0"),
    ("landing_pages_booked_bad_file", "=0"), ("stubs_bound", "=0"), ("volumes_bound_as_article", "=0"),
    ("free_ceiling_measured_unconverted", "=0"), ("budget_exceeded_silently", "=0"),
    ("stage_b_rungs_unmeasured", "=0"), ("crosswalk_rows_without_identifier", "=0"),
    ("identifiers_without_provenance", "=0"), ("conflicts_uncounted", "=0"),
    ("nondistinct_schemes_in_unique_index", "=0"), ("unvalidated_items", "=0"),
    ("replay_rows_graded_against_stubs", "=0"), ("replay_network_calls", "=0"), ("cassettes_stale", "=0"),
    ("promotions_prepared", ">=1"),
    ("replay_rows_disagreeing", "=0"),
)

#: The REPORTED counters the plan's (b) names (unbounded), plus decision D8's historical operator binds.
HARDENING_REPORTED = ("promotions_committed", "page_ranges_unparsed", "transient_rows_unretried",
                      "relation_edges_missing", "identifier_first_refusals", "books_without_isbn",
                      "attempts_without_sha", "unowned_landings", "attempts_without_terminal",
                      "files_without_word_count", "hits_without_version", "bronze_landing_unconverted",
                      "manual_step_rows", "operator_binds_historical")

#: Where the counter modules live, and their name pattern (brief-CONTRACTS.md).
HARDENING_MODULE_DIR = SCRIPTS / "qc" / "instruments"
HARDENING_MODULE_GLOB = "litkb_hardening_*.py"

#: The probe files the counters read: every `phase4/qc/litkb_acq_probe_*` on disk at freeze.
PROBE_GLOB = "litkb_acq_probe_*"

#: The ruled run's ledger (the plan's rows 187 and 194, and the `registry-transient` rows item 1 names).
RULED_HUNTS = "Reports/LITKB_RULED_HUNTS_2026-09-21.csv"

#: The register rows the brief names for the run (plan items 1, 5, 7), and the ruled-run rows.
RUN_REGISTER_ROWS = ("E13", "E21", "E06", "E20")
RUN_RULED_ROWS = ("187", "194")

#: The post-freeze row the plan names by value (item 5b NEGATIVE, REAL).
POST_FREEZE_PROBE_DOI = "10.1016/j.rse.2024.114101"

#: The CONSTRUCTED register `hardening --replay` replays beside the edge register (its rows are
#: `C`-prefixed; each replays through the real ladder against its own CONSTRUCTED cassette).
HARDENING_CONSTRUCTED_REGISTER = SCRIPTS / "qc" / "fixtures" / "litkb_hardening_constructed_register.json"


def _bound_ok(value, bound):
    """`=N` or `>=N`; an unread value (None) never meets a bound."""
    if value is None:
        return False
    if bound.startswith(">="):
        return value >= int(bound[2:])
    return value == int(bound.lstrip("="))


def _hardening_modules(directory=None):
    """-> {"loaded": [(stem, path)], "failed": [(stem, error)], "counters": {name: (fn, stem)},
    "reported": {name: (fn, stem)}, "fires": {name: (spec, stem)}}. A module that fails to import is
    NAMED (its counters then print `unread`); two modules defining one name is refused outright —
    a counter with two homes has no definition."""
    directory = Path(directory or HARDENING_MODULE_DIR)
    out = {"loaded": [], "failed": [], "counters": {}, "reported": {}, "fires": {}}
    for path in sorted(directory.glob(HARDENING_MODULE_GLOB)):
        stem = path.stem
        try:
            spec = importlib.util.spec_from_file_location(stem, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:              # noqa: BLE001 — the module is named, its counters unread
            out["failed"].append((stem, f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"))
            continue
        out["loaded"].append((stem, str(path)))
        for attr, key in (("COUNTERS", "counters"), ("REPORTED", "reported"), ("FIRES", "fires")):
            # counters and reported counters share one namespace; fires have their own
            spaces = ("fires",) if key == "fires" else ("counters", "reported")
            for name, value in (getattr(mod, attr, None) or {}).items():
                for other in spaces:
                    if name in out[other]:
                        raise SystemExit(f"litkb_acceptance hardening: {name!r} is defined by both "
                                         f"{out[other][name][1]} and {stem}; a counter has ONE home")
                out[key][name] = (value, stem)
        for name, fn in (getattr(mod, "DETAILS", None) or {}).items():
            out.setdefault("details", {})[name] = fn
    return out


# -- --freeze: the run rows (S4.5 decision D9), chosen by NAMED selectors --------------------

class _LedgerReader:
    """The reads the selectors need, on a READER connection. One object so the tests can hand the
    selectors a fake with the same four methods and no database."""

    def __init__(self, conn):
        self.conn = conn

    def work_of(self, scheme, ref):
        """(work_id, key) of the main work holding this identifier, or None."""
        if scheme not in ("doi", "arxiv") or not ref:
            return None
        row = self.conn.execute(
            "SELECT i.work_id::text, w.key FROM litkb.main_identifiers i "
            "JOIN litkb.main_works w ON w.work_id = i.work_id "
            "WHERE i.scheme = %s AND i.active AND i.value_norm = litkb.norm_identifier(%s, %s) "
            "ORDER BY w.key LIMIT 1", (scheme, scheme, ref)).fetchone()
        return (row[0], row[1]) if row else None

    def ref_of(self, work_id):
        """(ref, scheme, key) a hunt can follow for this work: its DOI, else its arXiv id."""
        rows = self.conn.execute(
            "SELECT i.scheme, i.value, w.key FROM litkb.main_identifiers i "
            "JOIN litkb.main_works w ON w.work_id = i.work_id WHERE i.work_id = %s AND i.active "
            "AND i.scheme IN ('doi', 'arxiv') ORDER BY i.scheme DESC, i.value", (work_id,)).fetchall()
        rows = sorted(rows, key=lambda r: (r[0] != "doi", r[1]))
        if rows:
            return rows[0][1], rows[0][0], rows[0][2]
        key = self.conn.execute("SELECT key FROM litkb.main_works WHERE work_id = %s",
                                (work_id,)).fetchone()
        return None, None, (key[0] if key else None)

    def has_file(self, work_id):
        return bool(self.conn.execute("SELECT count(*) FROM litkb.main_files WHERE work_id = %s "
                                      "AND status = 'active'", (work_id,)).fetchone()[0])

    def attempt_works(self, status, route=None, work_type=None):
        """{work_id: {route: n}} of works with an attempt in this status (optionally on one route,
        optionally of one main_works.type)."""
        sql = ("SELECT a.work_id::text, a.route, count(*) FROM litkb.acquisition_attempts a "
               "JOIN litkb.main_works w ON w.work_id = a.work_id WHERE a.status = %(s)s")
        if route:
            sql += " AND a.route = %(r)s"
        if work_type:
            sql += " AND w.type = %(t)s"
        out = {}
        for wid, rt, n in self.conn.execute(sql + " GROUP BY 1, 2 ORDER BY 1, 2",
                                            {"s": status, "r": route, "t": work_type}).fetchall():
            out.setdefault(wid, {})[rt] = n
        return out

    def works_with_file_keys(self):
        return {r[0] for r in self.conn.execute(
            "SELECT DISTINCT w.key FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id = f.work_id "
            "WHERE f.status = 'active'").fetchall()}


def _csv_rows(path):
    p = Path(path)
    if not p.is_file():
        return []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _sel_register(ctx):
    rows = {r["id"]: r for r in (ctx["register"].get("rows") or [])}
    return [{"ref": rows[i]["ref"], "ref_scheme": rows[i].get("ref_scheme") or "doi",
             "why": f"register row {i} ({rows[i].get('class')})"} for i in RUN_REGISTER_ROWS if i in rows]


def _sel_pending_recording(ctx):
    """Every register row still on the synthetic acquirer (`replay.routes.pending_recording`) whose
    live mode is `execute`: the live pass must RECORD each of them, or it can never come off the stub
    (auditor-A round 1, F8 — E03 and E07 were in the run only because a probe selector happened to
    pick their DOIs). A `replay-only` row (E16) has no live hunt to record and is left out."""
    return [{"ref": r["ref"], "ref_scheme": r.get("ref_scheme") or "doi",
             "why": f"register row {r['id']} is pending a recording ({r.get('class')})"}
            for r in ctx["register"].get("rows") or []
            if ((r.get("replay") or {}).get("routes") or {}).get("pending_recording")
            and (r.get("live") or {}).get("mode") == "execute" and r.get("ref")]


def _sel_ruled(ctx):
    return [{"ref": r["ref"], "ref_scheme": r.get("ref_scheme") or "doi",
             "why": f"ruled run tracker {r['tracker_id']} ({r.get('group')}): ended "
                    f"{r.get('hunt_state')}/{r.get('hunt_reason')}"}
            for r in ctx["ruled"] if r.get("tracker_id") in RUN_RULED_ROWS]


def _sel_ruled_transient(ctx):
    return [{"ref": r["ref"], "ref_scheme": r.get("ref_scheme") or "doi",
             "why": f"ruled run tracker {r['tracker_id']}: api-error/registry-transient (the back-off rows, item 1)"}
            for r in ctx["ruled"] if r.get("hunt_reason") == "registry-transient"]


def _sel_post_freeze(ctx):
    return [{"ref": POST_FREEZE_PROBE_DOI, "ref_scheme": "doi",
             "why": "plan item 5b NEGATIVE, REAL: post-freeze, refused before any shadow request"}]


def _sel_no_oa_copy(ctx):
    return [{"ref": r["doi"], "ref_scheme": "doi", "why": "an open_access/no-oa-copy DOI (Stage B asks every rung)"}
            for r in ctx["probe"]("litkb_acq_probe_no_oa_copy.csv") if r.get("doi")]


def _sel_free_pdf(ctx):
    return [{"ref": r["doi"], "ref_scheme": "doi", "why": f"head probe FREE-PDF via {r.get('resolver')} (must convert)"}
            for r in ctx["probe"]("litkb_acq_probe_head.csv") if r.get("verdict") == "FREE-PDF"]


def _sel_wayback(ctx):
    return [{"ref": r["doi"], "ref_scheme": "doi",
             "why": f"head probe: the {r.get('resolver')} URL answered 404 (Stage E1's input)"}
            for r in ctx["probe"]("litkb_acq_probe_head.csv") if str(r.get("status")) == "404"]


def _sel_bronze(ctx):
    return [{"ref": r["doi"], "ref_scheme": "doi", "why": "Unpaywall answer is a doi.org landing page (Stage C, reported)"}
            for r in ctx["probe"]("litkb_acq_probe_no_oa_copy.csv")
            if (r.get("unpaywall_url") or "").startswith("https://doi.org/")]


def _sel_status(status):
    def sel(ctx):
        return [{"work_id": wid, "why": f"{status} attempts: " + ", ".join(f"{rt}={n}" for rt, n in sorted(by.items()))}
                for wid, by in sorted(ctx["ledger"].attempt_works(status).items())]
    return sel


def _sel_bban(ctx):
    return [{"ref": r["doi"], "ref_scheme": "doi",
             "why": f"bban probe {r.get('verdict')} (tried {r.get('tried')}, {r.get('http_status')})"}
            for r in ctx["probe"]("litkb_acq_probe_bban.csv") if r.get("doi")]


def _sel_preprint_misses(ctx):
    ledger = ctx["ledger"]
    out = {wid: "a preprint (main_works.type) the archive missed"
           for wid in ledger.attempt_works("not-in-archive", route="annas", work_type="preprint")}
    posted = {r["key"] for r in ctx["probe"]("litkb_acq_probe_crosswalk.csv") if r.get("cr_type") == "posted-content"}
    for wid in ledger.attempt_works("not-in-archive", route="annas"):
        _ref, _scheme, key = ledger.ref_of(wid)
        if key in posted:
            out.setdefault(wid, "Crossref type posted-content (crosswalk probe), missed by the archive")
    return [{"work_id": wid, "why": why} for wid, why in sorted(out.items())]


def _sel_crosswalk(ctx):
    have = ctx["ledger"].works_with_file_keys()
    out = []
    for r in ctx["probe"]("litkb_acq_probe_crosswalk.csv"):
        if r.get("key") in have or not r.get("doi"):
            continue
        gains = [f"{c}={r[c]}" for c in ("s2_arxiv", "cr_isbn", "cr_relation_types") if r.get(c)]
        if gains:
            out.append({"ref": r["doi"], "ref_scheme": "doi", "why": "crosswalk, no file: " + "; ".join(gains)})
    return out


#: The NAMED selectors, in the order a row's id is assigned. Each is a small function over the probe
#: CSVs, the ledger (reader role) or the register; the manifest records every selector that chose a row.
RUN_SELECTORS = (
    ("register", _sel_register), ("pending-recording", _sel_pending_recording),
    ("ruled", _sel_ruled), ("ruled-registry-transient", _sel_ruled_transient),
    ("post-freeze-probe", _sel_post_freeze), ("free-pdf", _sel_free_pdf), ("wayback", _sel_wayback),
    ("bronze-landing", _sel_bronze), ("no-oa-copy", _sel_no_oa_copy), ("bad-file", _sel_status("bad-file")),
    ("blocked", _sel_status("blocked")), ("bban", _sel_bban), ("preprint-archive-miss", _sel_preprint_misses),
    ("crosswalk", _sel_crosswalk),
)


def select_run_rows(ctx, selectors=RUN_SELECTORS):
    """-> (rows, unhuntable, counts). Deduplicated BY WORK (a reference no main work holds is its own
    key); every selector that chose a row is kept in `source`. `mode` is `measure` when the work
    already holds an active file (every rung is asked, nothing lands twice), else `hunt`."""
    ledger = ctx["ledger"]
    merged, order, counts = {}, [], {}
    for idx, (name, fn) in enumerate(selectors):
        picked = fn(ctx)
        counts[name] = len(picked)
        for c in picked:
            wid, key = c.get("work_id"), None
            ref, scheme = c.get("ref"), c.get("ref_scheme")
            if not wid:
                hit = ledger.work_of(scheme, ref)
                if hit:
                    wid = hit[0]
            if wid:
                # a resolved work is hunted by its OWN stored identifier (DOI, else arXiv), whatever
                # spelling the probe CSV carried; a work with neither keeps the candidate's reference
                own_ref, own_scheme, key = ledger.ref_of(wid)
                if own_ref or not ref:
                    ref, scheme = own_ref, own_scheme
            dk = wid or f"{scheme}:{str(ref or '').strip().lower()}"
            if dk not in merged:
                merged[dk] = {"ref": ref, "ref_scheme": scheme, "work_id": wid, "key": key,
                              "source": [], "why": [], "_order": (idx, str(ref or ""))}
                order.append(dk)
            m = merged[dk]
            if name not in m["source"]:
                m["source"].append(name)
                m["why"].append(f"{name}: {c.get('why')}")
    rows, unhuntable = [], []
    for dk in sorted(order, key=lambda k: merged[k]["_order"]):
        m = merged.pop(dk)
        m.pop("_order")
        m["why"] = "; ".join(m["why"])
        if not m["ref"]:
            unhuntable.append({**m, "reason": "the work holds no DOI and no arXiv id a hunt can follow"})
            continue
        m["mode"] = "measure" if (m["work_id"] and ledger.has_file(m["work_id"])) else "hunt"
        rows.append(m)
    for n, r in enumerate(rows, 1):
        r["id"] = f"L{n:03d}"
    return [{k: r[k] for k in ("id", "ref", "ref_scheme", "mode", "source", "why", "work_id", "key")}
            for r in rows], unhuntable, counts


def _rel(repo, p):
    try:
        return Path(p).resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        return str(p)


def _frozen_ladder_budget():
    """{"seconds", "attempts"} of the ladder budget the run will declare (`litkb.acquire.policy.LadderBudget()`),
    written into the manifest at freeze so `budget_exceeded_silently` reads a threshold held OUTSIDE the ladder
    (builder C1a's `frozen_budget`; integrator-w2). `attempts` is null: the default is derived per ladder."""
    from litkb.acquire import policy as P

    b = P.LadderBudget()
    return {"seconds": b.seconds, "attempts": b.attempts}


def _frozen_shadow_tier():
    """{"enabled": False, "code_default", "ruling"}: the switch the live pass runs with (S4.5 decision D27; integrator-w3)."""
    from litkb.acquire import policy as P

    return {"enabled": False, "code_default": bool(P.SHADOW_TIER_ENABLED),
            "ruling": "S4.5 decision D27 / Scope ruling 2026-09-23: item 5b not built; the live run runs with the shadow "
                      "tier switched OFF"}


def _hardening_freeze(args):
    for required in ("workstream", "out"):
        if not getattr(args, required):
            print(f"hardening --freeze needs --{required}", file=sys.stderr)
            return 2
    from litkb import cassette as CAS
    from litkb.acquire.store import LITERATURE_ROOT

    HA = _load_instrument("litkb_hardening_a")
    repo = Path(args.repo or _repo_root())
    db = args.db or "litkb"
    ws_id = resolve_workstream(db, args.role, args.workstream)
    if ws_id is None:
        print(f"hardening --freeze: no open workstream {args.workstream!r} on {db}", file=sys.stderr)
        return 2
    probe_dir = repo / "phase4" / "qc"
    probes = sorted(probe_dir.glob(PROBE_GLOB))
    register_path = Path(args.fixture) if args.fixture else SCRIPTS / "qc" / "fixtures" / "litkb_hunt_edge_cases.json"
    constructed_path = Path(args.constructed) if args.constructed else HARDENING_CONSTRUCTED_REGISTER
    ruled_path = repo / RULED_HUNTS
    conn = _connect(db, args.role, autocommit=False)
    try:
        from psycopg import IsolationLevel

        conn.isolation_level = IsolationLevel.REPEATABLE_READ
        with conn.transaction():
            # THE FREEZE INSTANT IS THE DATABASE'S, and the run rows are read in the same snapshot
            frozen_at = conn.execute("SELECT now()").fetchone()[0]
            name, oid = _db_identity(conn)
            ctx = {"ledger": _LedgerReader(conn),
                   "register": json.loads(read_text(register_path)),
                   "ruled": _csv_rows(ruled_path),
                   "probe": lambda base: _csv_rows(probe_dir / base)}
            rows, unhuntable, counts = select_run_rows(ctx)
    finally:
        conn.close()
    # THE ONE ADMIN READ. `litkb_meta` is readable by `litkb_owner` alone (db_migration_tip), so the
    # tip needs the owner login — readability's freeze does the same. `--no-admin-read` records the tip
    # as null with the reason, so a freeze that must stay on the reader login (a builder's trial on
    # live) can (auditor-A round 1, F7: a trial freeze read live as litkb_owner through this call).
    if args.no_admin_read:
        db_tip, db_tip_note = None, "not read: --no-admin-read (litkb_meta needs the owner login)"
    else:
        db_tip, db_tip_note = db_migration_tip(db, args.passfile)
    date = args.date or frozen_at.astimezone().strftime("%Y-%m-%d")
    stem = f"LITKB_LADDER1_{date}"
    index = Path(args.cassette) if args.cassette else SCRIPTS / "qc" / "fixtures" / "litkb_cassettes" / args.workstream / "index.jsonl"
    derived = repo / "_derived" / "hardening"
    manifest = {
        "kind": HARDENING_MANIFEST_KIND,
        "frozen_at": frozen_at.astimezone(dt.timezone.utc).isoformat(),
        "frozen_at_source": "db",
        "repo": str(repo),
        "repo_head": _repo_head(repo),
        "code_committed": _code_committed(repo),
        "db": db, "db_name": name, "db_oid": oid, "reader_role": args.role,
        "repo_migration_tip": repo_migration_tip(),
        "db_migration_tip": db_tip, "db_migration_tip_note": db_tip_note,
        "workstream_slug": args.workstream, "workstream_id": ws_id, "run_workstream_ids": [ws_id],
        "worktree": str(args.worktree or repo),
        # the literature root the counters read the store under (builder C1b's quarantine and bound-file
        # counters name this key; seam integrator-w1) — frozen, so a grade reads the store the run wrote
        "literature_root": str(LITERATURE_ROOT),
        # the run's ladder budget, FROZEN outside the ladder: builder C1a's `budget_exceeded_silently` grades
        # against it (Codex X2: removing the budget object must not remove the threshold the checker reads;
        # auditor-C1a r2 F6 / r3 F4, routed to this file; integrator-w2). `attempts` null = derived per ladder.
        "ladder_budget": _frozen_ladder_budget(),
        # the shadow tier switch the live pass runs with: OFF (S4.5 decision D27, the Scope ruling — item 5b is not
        # built). The run driver (litkb_ladder_run.shadow_switch) refuses a manifest that does not record it off
        # unless explicitly overridden; the code default (policy.SHADOW_TIER_ENABLED) stays as merged. integrator-w3
        "shadow_tier": _frozen_shadow_tier(),
        # CONTRACTS' shape: {basename: path}; the content hash of each beside it (brief-A asked for
        # {path, sha256} under one key — the other builders' counters read the CONTRACTS shape)
        "probe_csvs": {p.name: _rel(repo, p) for p in probes},
        "probe_csvs_sha256": {p.name: _register_sha256(p) for p in probes},
        "register": {"path": _rel(repo, register_path), "sha256": _register_sha256(register_path)},
        # the CONSTRUCTED rows `hardening --replay` replays beside the register (plan item 7: "a
        # cassette's 403 edited to 200, a truncated body, an HTML body"; auditor-A round 1, F2)
        "constructed_register": {"path": _rel(repo, constructed_path),
                                 "sha256": _register_sha256(constructed_path)},
        "ruled_hunts": {"path": _rel(repo, ruled_path),
                        "sha256": _register_sha256(ruled_path) if ruled_path.is_file() else None},
        "report_path": f"Reports/{stem}.md",
        "referee_reports": {cls: f"Reports/LITKB_REFEREE_S45_{cls.upper()}_{date}.md"
                            for cls in HA.REFEREE_CLASSES},
        "cassette_index": {"path": _rel(repo, index), "sha256": CAS.index_sha256(index),
                           "bodies": str(args.bodies or CAS.default_bodies()),
                           "inline_max_bytes": CAS.INLINE_MAX_BYTES},
        "run_csv": _rel(repo, derived / f"{stem}_run.csv"),
        # the run driver's last word on the recording: the index's sha256 when the live pass finished
        # (litkb_ladder_run.write_recording_report); the replay counters refuse an index that is not it
        "recording_report": _rel(repo, derived / f"{stem}_recording.json"),
        "replay_csv": _rel(repo, derived / f"{stem}_replay.csv"),
        "replay_report": _rel(repo, derived / f"{stem}_replay.json"),
        "gated": [{"name": n, "bound": b} for n, b in HARDENING_GATED],
        "reported": list(HARDENING_REPORTED),
        "selectors": counts,
        "rows": rows,
        "unhuntable": unhuntable,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    modes = {}
    for r in rows:
        modes[r["mode"]] = modes.get(r["mode"], 0) + 1
    print(f"frozen {out} db={name} workstream={args.workstream} rows={len(rows)} "
          + " ".join(f"{k}={v}" for k, v in sorted(modes.items()))
          + f" unhuntable={len(unhuntable)} head={manifest['repo_head'][:12]} db_tip={db_tip} "
          f"cassette_sha={str(manifest['cassette_index']['sha256'])[:12]}")
    return 0


def _load_instrument(stem):
    spec = importlib.util.spec_from_file_location(stem, SCRIPTS / "qc" / "instruments" / f"{stem}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_hardening_manifest(path):
    """The manifest, REFUSED (SystemExit, nothing graded) when its kind is wrong, a field was edited
    after the freeze, or its gated list is not this code's."""
    manifest = json.loads(read_text(path))
    # BEGIN guard: a hardening manifest edited after its freeze is refused
    if manifest.get("kind") != HARDENING_MANIFEST_KIND:
        raise SystemExit(f"litkb_acceptance hardening: {path} is not a {HARDENING_MANIFEST_KIND!r} manifest "
                         f"(kind {manifest.get('kind')!r}). Nothing was graded.")
    if manifest.get("manifest_sha256") != _canonical_sha(manifest):
        raise SystemExit(f"litkb_acceptance hardening: {path} was edited after its freeze (manifest_sha256 "
                         "does not match its content). Re-freeze it. Nothing was graded.")
    # END guard: a hardening manifest edited after its freeze is refused
    frozen = [(g.get("name"), g.get("bound")) for g in manifest.get("gated") or []]
    if frozen != list(HARDENING_GATED):
        raise SystemExit("litkb_acceptance hardening: the manifest's gated list is not this code's "
                         "HARDENING_GATED; a manifest frozen under other bounds grades a different "
                         "question. Re-freeze it. Nothing was graded.")
    return manifest


def _read_only_reader(manifest, db=None):
    """A litkb_reader connection to the manifest's database, in READ ONLY session mode, refused when
    the database is not the one frozen (name + oid: readability's rule)."""
    conn = _connect(db or manifest["db"], manifest.get("reader_role") or "litkb_reader")
    conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    name, oid = _db_identity(conn)
    if (name, oid) != (manifest.get("db_name"), manifest.get("db_oid")):
        conn.close()
        raise SystemExit(f"litkb_acceptance hardening: the manifest was frozen on {manifest.get('db_name')!r} "
                         f"(oid {manifest.get('db_oid')}); this is {name!r} (oid {oid}). Nothing was graded.")
    return conn


def check_hardening(manifest, *, conn=None, db=None, module_dir=None):
    """-> (gated {name: int | None}, reported {name: int | None}, offences, modules). None = UNREAD."""
    mods = _hardening_modules(module_dir)
    own = conn is None
    conn = conn or _read_only_reader(manifest, db)
    offences = [f"module failed to load: {stem} ({err})" for stem, err in mods["failed"]]
    gated, reported = {}, {}

    def run(fn, name):
        try:
            return int(fn(conn, manifest))
        except Exception as e:              # noqa: BLE001 — an unreadable counter is UNREAD, named
            offences.append(f"{name}: unread — {type(e).__name__}: {str(e).splitlines()[0][:240] if str(e) else ''}")
            return None
    try:
        for name, _bound in HARDENING_GATED:
            hit = mods["counters"].get(name)
            # BEGIN guard: a gated counter no module defines is unread and fails the exit
            if hit is None:
                offences.append(f"{name}: unread — no loaded litkb_hardening_*.py module defines it")
                gated[name] = None
                continue
            # END guard: a gated counter no module defines is unread and fails the exit
            gated[name] = run(hit[0], name)
        for name, (fn, stem) in mods["counters"].items():
            if name not in gated:
                offences.append(f"{name}: defined by {stem} as a gated counter but not in HARDENING_GATED; "
                                "printed as REPORTED")
                reported[name] = run(fn, name)
        for name in HARDENING_REPORTED:
            hit = mods["reported"].get(name)
            reported[name] = run(hit[0], name) if hit else None
        for name, (fn, _stem) in mods["reported"].items():
            if name not in reported:
                reported[name] = run(fn, name)
        for name, fn in (mods.get("details") or {}).items():
            value = gated.get(name, reported.get(name))
            if value:
                try:
                    offences += [f"{name}: {line}" for line in fn(conn, manifest)][:40]
                except Exception:          # noqa: BLE001 — a detail is a courtesy, never a verdict
                    pass
    finally:
        if own:
            conn.close()
    return gated, reported, offences, mods


def hardening_ok(gated):
    """Every gated counter read and inside its bound."""
    bounds = dict(HARDENING_GATED)
    return all(_bound_ok(gated.get(n), bounds[n]) for n in bounds)


def hardening_line(gated, reported):
    return " ".join(f"{k}={_fmt(v)}" for k, v in (*gated.items(), *reported.items()))


# -- --fire ---------------------------------------------------------------------------------

def _hardening_fire_db(db):
    """The worker database a fire or a replay may reset: named EXPLICITLY, a `litkb_test_w<N>`, not
    RESERVED, and the database litkb's own reset will agree to (LITKB_TEST_DB). `--db` is required:
    LITKB_TEST_DB alone is not a choice made for THIS command."""
    db = (db or "").strip()
    # BEGIN guard: hardening resets only an explicitly named, unreserved worker database
    if db.lower() == FORBIDDEN_FIRE_DB or not _FIRE_WORKER_DB.fullmatch(db):
        raise SystemExit(f"litkb_acceptance hardening resets its database, so it runs only on a worker "
                         f"database named explicitly (--db litkb_test_w<N>); got {db!r}. It never "
                         "defaults to a shared database.")
    if db in reserved_worker_dbs():
        raise SystemExit(f"litkb_acceptance hardening refuses {db!r}: it is RESERVED "
                         f"({', '.join(reserved_worker_dbs())})")
    # END guard: hardening resets only an explicitly named, unreserved worker database
    env = os.environ.get("LITKB_TEST_DB")
    if env and env.strip() != db:
        raise SystemExit(f"litkb_acceptance hardening: --db {db} but LITKB_TEST_DB={env}; litkb's reset "
                         "refuses every database but LITKB_TEST_DB, so set it to the same worker")
    os.environ["LITKB_TEST_DB"] = db
    from litkb.db import connect as c          # DB_TEST is read at import: check what it READ

    if c.DB_TEST != db:
        raise SystemExit(f"litkb_acceptance hardening: litkb.db.connect was imported with DB_TEST="
                         f"{c.DB_TEST}; run with LITKB_TEST_DB={db} set before the command starts")
    return db


def _reset(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


def hardening_fire(name, *, db, conn=None, module_dir=None, workroot=None, reset=None):
    """Run one module fire: reset, control arm, reset, known-bad arm, reset. -> {"name", "lines",
    "fired", "verdict"}. `conn` (tests) is the worker database's owner login, used without the lock;
    `reset` (tests of the verdict alone) replaces the reset + migrate."""
    import tempfile

    _reset_db = reset or _reset
    mods = _hardening_modules(module_dir)
    hit = mods["fires"].get(name)
    if hit is None:
        raise SystemExit(f"hardening --fire: no module defines a fire {name!r} "
                         f"(defined: {', '.join(sorted(mods['fires'])) or 'none'})")
    spec, stem = hit
    counter = spec.get("counter")
    bound = spec.get("bound") or dict(HARDENING_GATED).get(counter)
    lines = []
    if bound is None:
        return {"name": name, "lines": [f"fire={name} ({stem}) counter={counter} has no bound: "
                                        "DID-NOT-FIRE (error)"], "fired": False,
                "verdict": "DID-NOT-FIRE (error)"}
    from litkb.db import connect as c

    own = conn is None
    lock = _edge_run()._SUITE_LOCK
    if own:
        conn = c.connect(db, "litkb_test", autocommit=True)
        conn.execute("SELECT pg_advisory_lock(%s)", (lock,))
    values, error = {}, None
    try:
        for arm in ("control", "known_bad"):
            _reset_db(conn)
            with tempfile.TemporaryDirectory(prefix=f"litkb-hardening-{name}-{arm}-",
                                             ignore_cleanup_errors=True, dir=workroot) as wd:
                try:
                    values[arm] = int(spec["run"](conn, arm, wd))
                except Exception as e:      # noqa: BLE001 — an arm that raised proves nothing
                    error = f"{arm}: {type(e).__name__}: {str(e).splitlines()[0][:240] if str(e) else ''}"
                    break
    finally:
        try:
            _reset_db(conn)
        finally:
            if own:
                try:
                    conn.execute("SELECT pg_advisory_unlock(%s)", (lock,))
                except Exception:          # noqa: BLE001 — a closed connection unlocks itself
                    pass
                conn.close()
    for arm in ("control", "known_bad"):
        if arm in values:
            lines.append(f"fire={name} ({stem}) arm={arm} {counter}={values[arm]} (bound {bound})")
    # BEGIN guard: a fire is FIRED only when the control holds its bound and the known-bad breaks it
    if error:
        verdict = "DID-NOT-FIRE (error)"
        lines.append(f"fire={name} error {error}")
    elif _bound_ok(values["control"], bound) and not _bound_ok(values["known_bad"], bound):
        verdict = "FIRED"
    else:
        verdict = "DID-NOT-FIRE"
    # END guard: a fire is FIRED only when the control holds its bound and the known-bad breaks it
    lines.append(f"fire={name} {verdict}")
    return {"name": name, "lines": lines, "fired": verdict == "FIRED", "verdict": verdict}


# -- --replay -------------------------------------------------------------------------------

def replay_register(manifest, repo):
    """(register dict, register path, constructed path): the manifest's edge register, with the rows
    of its CONSTRUCTED register (`constructed_register`, when the manifest names one) appended — the
    plan's item-7 CONSTRUCTED rows are replayed and graded with the register's, in one summary."""
    def at(p):
        q = Path(p)
        return q if q.is_absolute() else repo / q
    register_path = at(manifest["register"]["path"])
    register = json.loads(read_text(register_path))
    con = (manifest.get("constructed_register") or {}).get("path")
    constructed_path = at(con) if con else None
    if constructed_path is not None:
        extra = json.loads(read_text(constructed_path)).get("rows") or []
        have = {r["id"] for r in register.get("rows") or []}
        clash = sorted(have & {r["id"] for r in extra})
        if clash:
            raise SystemExit(f"hardening --replay: the CONSTRUCTED register reuses register row ids {clash}")
        register = dict(register, rows=list(register.get("rows") or []) + extra)
    return register, register_path, constructed_path


def hardening_replay(manifest, *, db, conn=None, bodies=None):
    """Replay the manifest's register (and its CONSTRUCTED register) through its recorded cassette on
    a worker database, inside a socket guard that allows nothing; write the replay CSV and summary the
    manifest promised. -> the summary dict."""
    import tempfile

    from litkb import cassette as CAS

    HA = _load_instrument("litkb_hardening_a")
    repo = Path(manifest["repo"])

    def at(p):
        q = Path(p)
        return q if q.is_absolute() else repo / q
    register, register_path, constructed_path = replay_register(manifest, repo)
    index = at(manifest["cassette_index"]["path"])
    cas = CAS.Cassette(index, "replay", bodies=bodies or manifest["cassette_index"].get("bodies")) \
        if index.is_file() else None
    guard = CAS.SocketGuard(allow_hosts=(), label="hardening --replay guard")
    from litkb.db import connect as c

    own = conn is None
    lock = _edge_run()._SUITE_LOCK
    if own:
        conn = c.connect(db, "litkb_test", autocommit=True)
        conn.execute("SELECT pg_advisory_lock(%s)", (lock,))
    try:
        _reset(conn)
        with tempfile.TemporaryDirectory(prefix="litkb-hardening-replay-", ignore_cleanup_errors=True) as wd:
            summary = HA.build_replay_summary(
                conn, register=register, register_path=register_path, db=db, workdir=wd, cassette=cas,
                guard=guard, index_path=index, out_csv=at(manifest["replay_csv"]),
                constructed_path=constructed_path)
        _reset(conn)
    finally:
        if own:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (lock,))
            except Exception:              # noqa: BLE001
                pass
            conn.close()
    out = at(manifest["replay_report"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary


def cmd_hardening(args):
    if args.freeze:
        return _hardening_freeze(args)
    if args.fire:
        db = _hardening_fire_db(args.db)
        names = sorted(_hardening_modules()["fires"]) if args.fire == "all" else [args.fire]
        ok = True
        for name in names:
            res = hardening_fire(name, db=db)
            for line in res["lines"]:
                print(line)
            ok = ok and res["fired"]
        return 0 if ok and names else 1
    if not args.manifest:
        print("litkb_acceptance hardening needs --manifest (or --freeze, or --fire)", file=sys.stderr)
        return 2
    manifest = load_hardening_manifest(args.manifest)
    if args.replay:
        db = _hardening_fire_db(args.db)
        s = hardening_replay(manifest, db=db)
        HA = _load_instrument("litkb_hardening_a")
        stale = s["stale"]
        for u in stale["unplayed"][:50]:
            print(f"unplayed: row={u['row']} seq={u['seq']} {u['url']}", file=sys.stderr)
        for m in stale["misses"][:50]:
            print(f"miss: row={m['row']} {m['url']} ({m['why']})", file=sys.stderr)
        for o in s["edges_offences"][:50]:
            print(f"replay: {o}", file=sys.stderr)
        try:
            stale_n = HA.count_stale(s)
        except HA.Unread as e:
            print(f"cassettes_stale: unread — {e}", file=sys.stderr)
            stale_n = "unread"
        for r in s.get("rows_not_replayed") or []:
            print(f"recorded, not replayed: row={r['row']} entries={r['entries']}", file=sys.stderr)
        # S4.5 decision D42 / register-editor Q1: what the replay changed in a row's world, each named
        for p in s.get("policy_switches") or []:
            print(f"policy switched on for the replay: row={p['row']} {p['route']}/{p['host']} (S4.5 decision D42)",
                  file=sys.stderr)
        for w in s.get("world_seeds") or []:
            print(f"world seeded for the replay: row={w['row']} {w['rel_path']} sha256={w['sha256'][:12]} "
                  f"({w['bytes']} B, from the row's recording)", file=sys.stderr)
        try:
            not_replayed_n = HA.count_rows_not_replayed(s)
        except HA.Unread:
            not_replayed_n = "unread"
        print(f"replay_rows_graded_against_stubs={HA.count_stubs(s)} replay_network_calls={s['network_calls']} "
              f"cassettes_stale={stale_n} replay_rows_disagreeing={HA.count_disagreeing(s)} "
              f"cassette_rows_not_replayed={not_replayed_n} "
              f"rows={len(s['rows'])} out={manifest['replay_report']}")
        return 0
    gated, reported, offences, mods = check_hardening(manifest, db=args.db)
    print("modules: " + (", ".join(stem for stem, _p in mods["loaded"]) or "none")
          + (f"; FAILED: {', '.join(s for s, _e in mods['failed'])}" if mods["failed"] else ""),
          file=sys.stderr)
    for line in offences:
        print(line, file=sys.stderr)
    print(hardening_line(gated, reported))
    return 0 if hardening_ok(gated) else 1


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

    r = sub.add_parser("readability",
                       help="is everything acquired readable or classified (S4): freeze, grade, fire")
    r.add_argument("--freeze", action="store_true",
                   help="write the manifest BEFORE the drain instead of grading one")
    r.add_argument("--manifest", help="the manifest frozen before the drain (grade mode; with --fire, "
                                      "checked and named, not graded)")
    r.add_argument("--fire", choices=FIRE_NAMES,
                   help="run one (c) known-bad on LITKB_TEST_DB (never litkb) and say whether it FIRED")
    r.add_argument("--workstream", action="append",
                   help="a workstream slug graded beside main (freeze; repeatable)")
    r.add_argument("--out", help="where to write the frozen manifest (freeze)")
    r.add_argument("--root", help="the literature root (freeze; default: LITKB_LITERATURE_ROOT or the store's)")
    r.add_argument("--db", default=None,
                   help="the database (freeze: default litkb; grade: default the manifest's own)")
    r.add_argument("--role", default="litkb_reader", help="read role (freeze; default: %(default)s)")
    r.add_argument("--repo", help="repository root (default: this instrument's own)")
    r.add_argument("--passfile", help="pgpass file for the admin read of the DB migration tip")
    r.set_defaults(func=cmd_readability)

    h = sub.add_parser("hardening",
                       help="the acquisition ladder, part 1 (S4.5): freeze, grade, fire, replay")
    h.add_argument("--freeze", action="store_true",
                   help="write the manifest BEFORE the run (the run rows included) instead of grading one")
    h.add_argument("--manifest", help="the manifest frozen before the run (grade; or --replay's input)")
    h.add_argument("--fire", help="run one module fire by name, or `all`, on --db (a worker database)")
    h.add_argument("--replay", action="store_true",
                   help="with --manifest: replay the register through the recorded cassette on --db, "
                        "inside a socket guard, and write the replay summary the manifest promised")
    h.add_argument("--workstream", help="the workstream slug the run works in (freeze)")
    h.add_argument("--out", help="where to write the frozen manifest (freeze)")
    h.add_argument("--fixture", help="the edge register (freeze; default qc/fixtures/litkb_hunt_edge_cases.json)")
    h.add_argument("--constructed", help="the CONSTRUCTED register replayed beside it (freeze; default "
                                         "qc/fixtures/litkb_hardening_constructed_register.json)")
    h.add_argument("--no-admin-read", dest="no_admin_read", action="store_true",
                   help="freeze: do NOT open the owner login for the DB migration tip (recorded null, "
                        "with the reason) — every other freeze read is on --role")
    h.add_argument("--cassette", help="the cassette index the run records into (freeze; default "
                                      "qc/fixtures/litkb_cassettes/<workstream>/index.jsonl)")
    h.add_argument("--bodies", help="the cassette body store (freeze; default LITKB_CASSETTE_BODIES or "
                                    "<derived root>/cassette_bodies)")
    h.add_argument("--date", help="the date in the promised report and referee names (freeze; default "
                                  "the freeze instant's local date)")
    h.add_argument("--worktree", help="the worktree holding the workstream token (freeze; recorded)")
    h.add_argument("--db", default=None, help="freeze/grade: the database (default litkb / the manifest's); "
                                              "fire/replay: the WORKER database, named explicitly")
    h.add_argument("--role", default="litkb_reader", help="read role (freeze; default: %(default)s)")
    h.add_argument("--repo", help="repository root (default: this instrument's own)")
    h.add_argument("--passfile", help="pgpass file for the admin read of the DB migration tip")
    h.set_defaults(func=cmd_hardening)

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

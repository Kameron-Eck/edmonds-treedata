r"""The acceptance instrument for the litkb work plan: a session's "done" is a COMMAND.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py plan
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py plan --file LITKB_WORKPLAN.md
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py disposition --manifest frozen.json
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py guard-checkout --path <wt> --vault <dir>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py scout --freeze --workstream scout-1 \
        --topic "…" --launch-cmd "…" --log <run.jsonl> --out <manifest.json>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_acceptance.py scout --manifest <manifest.json>

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
discovery run actually discover), landing with S1. `first-work`, `edges`, `readability`, `run`,
`synthesis` and `soak` land with their own sessions and are deliberately absent until then — an
acceptance command that cannot fail is worse than no command. `guard-checkout` is not a session
gate: it is the safety interlock the owner runs BEFORE removing any checkout.

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

A generic `error` refusal is deliberately OUTSIDE `CLOSED_STATES`. hunt() returns `refused:
"error"` for any unexpected exception, so a driver that crashed on every row would otherwise
report a full set of "known" states and pass.

The git queries are the two module-level functions `_worktree_list` and `_rev_parse`, injected
into the checker so the tests can exercise parity without a second remote. The database read is
the module-level `_hunt_request_rows`, injected the same way.

`plan`, `disposition` and `guard-checkout` are stdlib-only, read-only, and touch no database.
`scout --freeze` WRITES its manifest and `scout` READS the litkb database, so psycopg and the
`litkb` package are imported lazily, inside the scout functions only: the other three subcommands
still run on a machine with neither installed, which is what keeps them usable from CI and from a
cold checkout. Nothing here ever writes to a database. It is not run on Colab, so it does not
filter an injected `-f` argument (CLAUDE.md 3.10 applies to the Colab entry points).
"""
import argparse
import csv
import datetime as dt
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

#: Every value `hunt_state_or_refusal` may take: the ladder states (`litkb.hunt.STATES`), the
#: deliberate no-spend stop, and the six refusal codes the ref-validating `ref_kind` introduces
#: (`litkb.hunt.REF_REFUSALS`). `error` is NOT here, on purpose — see the module docstring.
#: `test_the_closed_vocabulary_matches_hunts_own` pins this against `litkb.hunt.STATES` and
#: `litkb.hunt.REF_REFUSALS` so this constant cannot drift away from the module it describes —
#: it already had, once: the builders worked in parallel and the sixth code (`unknown-ref-scheme`)
#: was added after this list was written.
#: The third group is `litkb.hunt.HUNT_REFUSALS`: the codes hunt could ALREADY refuse with before
#: S1. The first scout run (2026-09-20) scored a real `admission-refused` — arXiv answered a
#: transient 406 and check 1 called it terminal — as `unknown_states`, because this list knew
#: only the six S1 codes. Both tuples are pinned by the test, and hunt.py's own test AST-scans
#: its source so no code can be raised without being listed.
CLOSED_STATES = ("absent", "held", "bound-unextracted", "extracted",
                 "held-no-spend",
                 "malformed-ref", "unknown-ref-scheme", "unsupported-ref-scheme",
                 "ref-scheme-mismatch", "unresolved-title", "ambiguous-title",
                 "admission-refused", "bad-workstream-file", "fetch-failed", "file-missing",
                 "incomplete-record", "no-artifact", "no-labels", "no-workstream",
                 "not-a-pdf", "truncated-pdf")

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


def _connect(db, role):
    from litkb.db import connect as c
    return c.connect(db, role, autocommit=True)


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
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
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
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

"""litkb S4.5 builder-B2 — the adjudication counters and their fires, for `litkb_acceptance.py hardening`.

    COUNTERS  gated   proposals_unadjudicated · operator_binds_unproposed · promotions_prepared
    REPORTED          promotions_committed · unowned_landings · operator_binds_historical ·
                      self_adjudications · decision_log_unguarded
    FIRES             one per gate the plan names in "### S4.5" (c), plus the two guards of the refuse
                      verb that have no gated counter of their own (the proposing session refusing, a
                      decision-log rewrite)

THE MODULE CONTRACT (brief-CONTRACTS.md "Counters and fires"): `hardening` loads every
`litkb_hardening_*.py` BY PATH (qc/instruments is not a package). A counter is `fn(conn, manifest) -> int`
on a READ-ONLY connection; a fire is `{"counter", "run": fn(conn, arm, workdir) -> int, "bound"}` whose
`run` performs ONE arm (`control` or `known_bad`) on an already reset+migrated WORKER database and returns
that counter's value. `bound` ("==0" or ">=1") is an extra key: the gated counters' bounds are the plan's
(b) text, and two of the fired counters here are REPORTED ones the plan gives no bound for.

SCOPING (S4.5 decision D1). RUN-SCOPED — rows after `manifest["frozen_at"]` in
`manifest["run_workstream_ids"]`: `operator_binds_unproposed` (D8: the 17 live historical operator binds are
REPORTED as `operator_binds_historical`, never retro-demoted), `promotions_prepared` and
`promotions_committed` (D6: two prepared promotions already exist on live, so an unscoped count would pass
vacuously). ALL-TIME: `proposals_unadjudicated` (every proposed manual admission older than the run).
`manifest["scope_workstream_ids"]` narrows the all-time counters to named workstreams — the FIRES set it so
an arm counts only its own rows on a shared test database; a run manifest never carries it.

THE DESIGN CONTRACT (CLAUDE.md §3.4c). Everything these counters grade is a RELAYED design
(Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md §1.8) and is UNVALIDATED until an independent referee
scores it on the real rows the plan names (194's proposal; the 17 operator binds; 187's filed PDF). The
builder never scores its own design. Every fire below mutates the REAL guard (in-process, inside a
transaction that is rolled back) or removes the real step, and every constructed row says CONSTRUCTED.
No fire touches the network; every fire refuses a database that is not a `litkb_test*` worker.
"""

import hashlib
import re
import subprocess
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
MIG34 = SCRIPTS / "pipeline" / "litkb" / "db" / "migrations" / "0034_adjudication.sql"

#: The `--from-file` routes the operator-bind gate names (`litkb-from-file-version-state`): `browser`
#: (acquire.run.land_and_attach from `--from-file`) and `held-in-place` (acquire.run.attach_in_place). A
#: MIRROR of `litkb_acceptance.MANUAL_FILE_ROUTES`, held equal by qc/test_litkb_adjudicate.py; the gate's own
#: list (`litkb._proposal_source_routes()`, migration 0034) also holds `web`, which is not an operator bind.
OPERATOR_ROUTES = ("browser", "held-in-place")

#: Where the hunt's URL path files a landed PDF (hunt.file_under_key -> Store.filed).
FILED_DIR = "_litkb_staging/filed"


def _frozen(manifest):
    return manifest["frozen_at"]


def _ws_ids(manifest, key="run_workstream_ids"):
    return [str(w) for w in (manifest.get(key) or [])]


def _has(conn, regclass):
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (regclass,)).fetchone()[0]


# ── gated counters ───────────────────────────────────────────────────────────────────────────

# Each counter's SCOPING clause is its own guard block (auditor-B2 round 2 F2/F4): a scoping clause is what
# makes a run-scoped gate honest (D1/D6/D8), and one deleted alone must turn a fire's arm red — the
# mutation rows (qc/instruments/litkb_p2_mutations.py, the B2 block) delete each one alone.

def proposals_unadjudicated(conn, manifest):
    """ALL-TIME: `proposed` manual admissions older than the run with NEITHER verb applied. Approve moves the
    state to `approved`, refuse to `declined` (migration 0034), so "neither verb" is exactly `state =
    'proposed'`. Live baseline before S4.5: 1 (194's Center_2015 proposal by `s3-wrap-hunts-2`). A proposal
    the run itself makes after the freeze (a URL hunt's `admit_web`) is NOT counted: "older than the run"."""
    scope = _ws_ids(manifest, "scope_workstream_ids")
    where = ["a.route = 'manual'", "a.state = 'proposed'",
             "(%(scope)s::uuid[] IS NULL OR a.workstream_id = ANY (%(scope)s::uuid[]))"]
    # BEGIN guard: proposals_unadjudicated counts only proposals older than the run
    where.append("a.created_at < %(frozen)s")
    # END guard: proposals_unadjudicated counts only proposals older than the run
    return conn.execute("SELECT count(*) FROM litkb.admissions a WHERE " + " AND ".join(where),
                        {"frozen": _frozen(manifest), "scope": scope or None}).fetchone()[0]


def _approved_versions_clause(conn):
    """The SQL that exempts a version a second session APPROVED (litkb.decide_file_versions writes an
    `approve` row per version). Before migration 0034 there is no log and nothing is exempt."""
    # BEGIN guard: a bind a second session approved is not an unproposed bind
    if _has(conn, "litkb.adjudications"):
        return ("AND NOT EXISTS (SELECT 1 FROM litkb.adjudications d "
                "WHERE d.verb = 'approve' AND d.version_id = fv.version_id)")
    # END guard: a bind a second session approved is not an unproposed bind
    return ""


def operator_binds_unproposed(conn, manifest):
    """RUN-SCOPED (D8): `--from-file` binds (source_route browser / held-in-place) created after the freeze by
    the run's workstreams that are the version of record (`promoted`) WITHOUT a second session's approval — a
    bind that skipped the proposal path. The gate (migration 0034 `litkb.attach_file`) writes them `proposed`.
    A bind made at or before the freeze is history (`operator_binds_historical`), never this gate's."""
    where = ["fv.source_route = ANY (%(routes)s)", "fv.state = 'promoted'",
             "fv.workstream_id = ANY (%(ws)s::uuid[])"]
    # BEGIN guard: operator_binds_unproposed counts only binds made after the freeze
    where.append("fv.created_at > %(frozen)s")
    # END guard: operator_binds_unproposed counts only binds made after the freeze
    return conn.execute(
        "SELECT count(*) FROM litkb.file_versions fv WHERE " + " AND ".join(where) + " "
        + _approved_versions_clause(conn),
        {"routes": list(OPERATOR_ROUTES), "frozen": _frozen(manifest), "ws": _ws_ids(manifest)}).fetchone()[0]


def promotions_prepared(conn, manifest):
    """RUN-SCOPED (D6): promotions PREPARED after the freeze for the run's workstreams on this database. The
    live base holds 2 prepared promotions from 2026-09-15/16, which an unscoped count would pass on. Each of
    the two clauses alone is load-bearing: the fire's known-bad arm holds a promotion the RUN's workstream
    prepared BEFORE the freeze and one ANOTHER workstream prepared AFTER it."""
    where = ["true"]
    # BEGIN guard: promotions_prepared counts only promotions prepared after the freeze
    where.append("p.prepared_at > %(frozen)s")
    # END guard: promotions_prepared counts only promotions prepared after the freeze
    # BEGIN guard: promotions_prepared counts only the run's workstreams
    where.append("p.workstream_id = ANY (%(ws)s::uuid[])")
    # END guard: promotions_prepared counts only the run's workstreams
    return conn.execute("SELECT count(*) FROM litkb.promotions p WHERE " + " AND ".join(where),
                        {"frozen": _frozen(manifest), "ws": _ws_ids(manifest)}).fetchone()[0]


# ── reported counters ────────────────────────────────────────────────────────────────────────

def promotions_committed(conn, manifest):
    """REPORTED: promotions COMMITTED after the freeze for the run's workstreams. It cannot move inside S4.5:
    `promote.commit` calls `verify_merge`, and there is no merge commit until Kam merges the branch; the
    session after that merge reports it."""
    return conn.execute(
        "SELECT count(*) FROM litkb.promotions p WHERE p.state = 'committed' AND p.committed_at > %(frozen)s "
        "AND p.workstream_id = ANY (%(ws)s::uuid[])",
        {"frozen": _frozen(manifest), "ws": _ws_ids(manifest)}).fetchone()[0]


def operator_binds_historical(conn, manifest):
    """REPORTED (D8): operator binds that became the version of record at or before the freeze with no
    second-session approval — the binds made before the gate existed. Live 2026-09-23: 17 (6 `browser`,
    11 `held-in-place`, survey-data §5). Never retro-demoted."""
    return conn.execute(
        "SELECT count(*) FROM litkb.file_versions fv WHERE fv.source_route = ANY (%(routes)s) "
        "AND fv.state = 'promoted' AND fv.created_at <= %(frozen)s " + _approved_versions_clause(conn),
        {"routes": list(OPERATOR_ROUTES), "frozen": _frozen(manifest)}).fetchone()[0]


def unowned_landing_paths(conn, root):
    """[rel_path] of the PDFs under `<root>/_litkb_staging/filed/` whose sha256 is in no `litkb.files` row
    and no `litkb.quarantine_payloads` row: a landing nothing owns (survey-data §0.10: 3 on 2026-09-23 —
    187's protocol PDF and 235's two copies). Every PDF is hashed; a matching path is not trusted."""
    filed = Path(root) / FILED_DIR
    if not filed.is_dir():
        return []
    held = {r[0] for r in conn.execute("SELECT sha256 FROM litkb.files").fetchall()}
    # BEGIN guard: a landing a quarantine row holds is owned
    if _has(conn, "litkb.quarantine_payloads"):
        held |= {r[0] for r in conn.execute("SELECT sha256 FROM litkb.quarantine_payloads").fetchall()}
    # END guard: a landing a quarantine row holds is owned
    out = []
    for p in sorted(filed.rglob("*")):
        if p.is_file() and p.suffix.lower() == ".pdf":
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            # BEGIN guard: a landing no row holds is counted unowned
            if h.hexdigest() not in held:
                out.append(p.relative_to(root).as_posix())
            # END guard: a landing no row holds is counted unowned
    return out


def unowned_landings(conn, manifest):
    """REPORTED: the count `unowned_landing_paths` names. The literature root is `manifest["literature_root"]`
    when the manifest carries one, else `litkb.acquire.store.LITERATURE_ROOT`."""
    root = manifest.get("literature_root")
    if not root:
        from litkb.acquire.store import LITERATURE_ROOT
        root = LITERATURE_ROOT
    return len(unowned_landing_paths(conn, root))


def self_adjudications(conn, manifest):
    """REPORTED: decision rows (`approve`/`refuse`) whose deciding session IS the proposing session once
    invisible characters are removed (litkb.textnorm.norm_label, the Python twin of the database's). The
    constraint `adjudications_second_session_decides` makes this 0 by construction; the fire
    `self_refusal` drops that constraint and shows the counter move. Compared in Python because
    `litkb.norm_label` is granted to no agent role."""
    if not _has(conn, "litkb.adjudications"):
        return 0
    from litkb.textnorm import norm_label

    scope = _ws_ids(manifest, "scope_workstream_ids")
    rows = conn.execute(
        "SELECT session_id, proposer_session FROM litkb.adjudications WHERE verb IN ('approve', 'refuse') "
        "AND (%(scope)s::uuid[] IS NULL OR proposer_workstream = ANY (%(scope)s::uuid[]))",
        {"scope": scope or None}).fetchall()
    return sum(1 for s, p in rows if norm_label(s) == norm_label(p))


#: The two triggers migration 0034 puts on the decision log.
APPEND_ONLY_TRIGGERS = ("adjudications_append_only", "adjudications_no_truncate")
AGENT_ROLES = ("litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest")


def decision_log_unguarded(conn, manifest):
    """REPORTED: how far the decision log is from append-only — every (agent role, privilege) pair holding
    INSERT, UPDATE, DELETE or TRUNCATE on `litkb.adjudications`, plus every one of its two append-only
    triggers that is missing or disabled. 0 is append-only; the fire `decision_log_rewrite` grants and
    disables them and shows the writer's UPDATE land."""
    if not _has(conn, "litkb.adjudications"):
        return 0
    grants = conn.execute(
        "SELECT count(*) FROM unnest(%s::text[]) r(role) CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE', 'DELETE', "
        "'TRUNCATE']) p(priv) WHERE has_table_privilege(r.role, 'litkb.adjudications', p.priv)",
        (list(AGENT_ROLES),)).fetchone()[0]
    live = {r[0] for r in conn.execute(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'litkb.adjudications'::regclass AND tgenabled <> 'D' "
        "AND NOT tgisinternal").fetchall()}
    return grants + sum(1 for t in APPEND_ONLY_TRIGGERS if t not in live)


COUNTERS = {
    "proposals_unadjudicated": proposals_unadjudicated,
    "operator_binds_unproposed": operator_binds_unproposed,
    "promotions_prepared": promotions_prepared,
}
REPORTED = {
    "promotions_committed": promotions_committed,
    "unowned_landings": unowned_landings,
    "operator_binds_historical": operator_binds_historical,
    "self_adjudications": self_adjudications,
    "decision_log_unguarded": decision_log_unguarded,
}


# ── the fires ────────────────────────────────────────────────────────────────────────────────
# Each arm runs on a WORKER database (`litkb_test*`) and logs in as that database's owner login
# `litkb_test`, which reaches the agent roles by SET ROLE (the P1/P2 suites' own pattern) and owns the
# schema, so an in-transaction mutation of a real guard (DROP a function, drop a constraint, re-create a
# function without its guard) is rolled back before the arm returns: nothing is left mutated.

def _worker_db(conn):
    from litkb.db import connect as c

    db = conn.info.dbname
    if not c.is_test_db(db):
        raise RuntimeError(f"litkb_hardening_b2: a fire runs only on a litkb_test* worker database, not {db!r}")
    return db


def _login(db, autocommit=True):
    from litkb.db import connect as c

    return c.connect(db, "litkb_test", autocommit=autocommit)


def _role(k, role):
    from psycopg import sql

    k.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)) if role else sql.SQL("RESET ROLE"))


def _jsonb(v):
    from psycopg.types.json import Jsonb

    return Jsonb(v)


def _open_ws(k, slug):
    """A workstream on the owner login. -> (id, token)."""
    return k.execute("SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/s45-b2-fire', NULL, "
                     "'S4.5 builder-B2 fire (CONSTRUCTED)', NULL)",
                     (f"{slug}-{uuid.uuid4().hex[:10]}",)).fetchone()


def _db_now(k):
    return k.execute("SELECT clock_timestamp()").fetchone()[0]


def _binding(title):
    """A CONSTRUCTED check-3 evidence object that `litkb._check_binding` accepts (the P2 suite's shape)."""
    return {"verdict": "bound", "ratio": 0.97, "matched": title, "registry_title": title, "author_found": True,
            "author_near_title": True, "text_layer": True, "page": 1, "title_region": True}


def _file_json(title, *, source_route=None, tag="constructed"):
    f = {"sha256": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
         "rel_path": f"_litkb_staging/filed/CONSTRUCTED-{tag}-{uuid.uuid4().hex[:8]}.pdf",
         "binding": _binding(title)}
    if source_route:
        f["source_route"] = source_route
    return f


def _unique_title(prefix):
    """A CONSTRUCTED title no other constructed title is title-near. Admission's check 2 sends a work with no
    strong identifier to `duplicate-review` at pg_trgm similarity >= 0.70 (`litkb._title_dup_threshold`),
    GLOBALLY across every work version, and a shared prefix with an 8-hex tail measured 0.78 on this suite's
    own rows (2026-09-23): the random part must dominate the trigrams, so it is three whole uuids."""
    return f"{prefix} {uuid.uuid4().hex} {uuid.uuid4().hex} {uuid.uuid4().hex}"


def _candidate(k, ws, token, title):
    return k.execute("SELECT litkb.add_candidate(%s, %s, 'manual', 'S4.5 B2 fire (CONSTRUCTED)', NULL, NULL, "
                     "NULL, %s, NULL, NULL, NULL)", (ws, token, title)).fetchone()[0]


def constructed_proposal(k, ws, token, *, session, agent="constructed-proposer", tag="194-shaped"):
    """A CONSTRUCTED manual proposal shaped like 194's (a manual admission from ANOTHER session, one `url`
    identifier, one bound file), written through `litkb.admit` on the writer role. -> the admit result."""
    title = _unique_title(f"CONSTRUCTED {tag} proposal")
    _role(k, "litkb_writer")
    try:
        cand = _candidate(k, ws, token, title)
        work = {"type": "report", "title": title, "authors": [{"family": "Constructed", "given": "C."}],
                "year": 2015}
        ids = [{"scheme": "url", "value": f"https://constructed.invalid/{uuid.uuid4().hex}",
                "verified_by": "manual", "evidence": {"constructed": True}}]
        key = f"Constructed_2015_{tag.replace('-', '')}-{uuid.uuid4().hex[:8]}"
        return k.execute("SELECT litkb.admit(%s, %s, %s, 'manual', %s, %s, %s, %s, %s, %s, %s)",
                         (ws, token, cand, key, _jsonb(work), _jsonb(ids), _jsonb(_file_json(title)),
                          _jsonb({"constructed": True}), agent, session)).fetchone()[0]
    finally:
        _role(k, None)


def constructed_registry_work(k, ws, token, *, session="constructed-admitter"):
    """A CONSTRUCTED registry-admitted work in main (the P2 suite's synthetic record). -> (work_id, title)."""
    hexid = uuid.uuid4().hex[:12]
    title = _unique_title("CONSTRUCTED registry work")
    doi = f"10.5555/litkb-s45-b2-{hexid}"
    ev = {"registry": "crossref", "registry_title": title, "registry_first_author": "Constructed",
          "registry_year": 2020, "claimed": {"title": title, "first_author": "Constructed", "year": 2020,
                                              "title_ratio": 1.0, "author_match": True}}
    work = {"type": "article", "title": title, "authors": [{"family": "Constructed", "given": "C."}], "year": 2020}
    _role(k, "litkb_writer")
    try:
        cand = _candidate(k, ws, token, title)
        res = k.execute("SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, 'constructed', %s)",
                        (ws, token, cand, f"Constructed_2020_operator-bind-{hexid}", _jsonb(work),
                         _jsonb([{"scheme": "doi", "value": doi, "verified_by": "crossref", "evidence": ev}]),
                         _jsonb({"constructed": True}), session)).fetchone()[0]
    finally:
        _role(k, None)
    if res.get("outcome") != "admitted":
        raise RuntimeError(f"the constructed registry work was not admitted: {res}")
    return res["work_id"], title


def _refuse_sig():
    return "litkb.refuse_admission(uuid, text, uuid, text, text, text)"


def fire_refuse_verb_removed(conn, arm, workdir):
    """(c): "the refuse verb removed and 194 left -> proposals_unadjudicated=1".

    Both arms: a CONSTRUCTED 194-shaped proposal (a manual admission by session `constructed-proposer` in its
    own workstream), then the freeze, then ANOTHER CONSTRUCTED proposal in the same workstream AFTER the freeze
    (the shape of a proposal the run's own URL hunts make — not older than the run, so never counted; it keeps
    the counter's "older than the run" clause load-bearing, auditor-B2 round 2 F4), then a SECOND session in
    another workstream adjudicates every proposal older than the freeze with the verbs the database has.
    control: `litkb.refuse_admission` exists and the second session refuses it -> 0. known_bad: the verb is
    DROPPED (in a transaction, rolled back before returning) -> the second session has no verb to apply -> 1."""
    from litkb.admit import front

    db = _worker_db(conn)
    k = _login(db)
    try:
        ws_p, tok_p = _open_ws(k, "b2-proposer")
        prop = constructed_proposal(k, ws_p, tok_p, session="constructed-proposer")
        if prop.get("outcome") != "proposed":
            raise RuntimeError(f"the constructed proposal was not proposed: {prop}")
        ws_r, tok_r = _open_ws(k, "b2-refuser")
        frozen = _db_now(k)
        late = constructed_proposal(k, ws_p, tok_p, session="constructed-proposer", tag="post-freeze")
        if late.get("outcome") != "proposed":
            raise RuntimeError(f"the constructed post-freeze proposal was not proposed: {late}")
        manifest = {"frozen_at": frozen, "run_workstream_ids": [str(ws_r)], "scope_workstream_ids": [str(ws_p)]}
        k.autocommit = False
        try:
            if arm == "known_bad":
                k.execute(f"DROP FUNCTION {_refuse_sig()}")
            has_verb = k.execute("SELECT to_regprocedure(%s) IS NOT NULL", (_refuse_sig(),)).fetchone()[0]
            if has_verb:
                _role(k, "litkb_writer")
                front.refuse(k, ws_r, tok_r, prop["admission_id"],
                             "CONSTRUCTED fire: the second session refuses the 194-shaped proposal",
                             "constructed-reviewer", "constructed-second-session")
                _role(k, None)
            return proposals_unadjudicated(k, manifest)
        finally:
            k.rollback()
            k.autocommit = True
    finally:
        k.close()


def _attach_file_without_the_gate():
    """0034's CREATE OR REPLACE of `litkb.attach_file` with the operator-bind guard block DELETED — the real
    text, the real guard, the same mutation the harness row makes. -> SQL."""
    src = MIG34.read_text(encoding="utf-8")
    start = src.index("CREATE OR REPLACE FUNCTION litkb.attach_file(")
    end = src.index("$$;", start) + 3
    body = src[start:end]
    guard = re.compile(r"  -- BEGIN guard: an operator-supplied file is a proposal, never the version of record\n"
                       r".*?  -- END guard: an operator-supplied file is a proposal, never the version of record\n",
                       re.S)
    mutated, n = guard.subn("", body.replace("\r\n", "\n"))
    if n != 1:
        raise RuntimeError("the operator-bind guard block was not found exactly once in 0034")
    return mutated


def fire_operator_bind_as_version_of_record(conn, arm, workdir):
    """(c): "a --from-file bind made the version of record with the proposal path disabled ->
    operator_binds_unproposed=1".

    Both arms: a CONSTRUCTED registry work in main; BEFORE the freeze, a `browser` bind of it written as a FACT
    by the owner in the run's workstream (the shape of the 17 historical pre-gate binds, D8 — history, never this
    gate's; it keeps the counter's "after the freeze" clause load-bearing, auditor-B2 round 2 F4); the freeze;
    then ONE `--from-file`-shaped bind through the real `litkb.attach_file` on the writer role (source_route
    `browser`, a CONSTRUCTED bound file) from the run's workstream. control: the gate writes it `proposed` -> 0.
    known_bad: `attach_file` re-created from 0034's own text with the gate's guard block deleted (in a
    transaction, rolled back) -> `promoted` -> 1."""
    db = _worker_db(conn)
    k = _login(db)
    try:
        ws, tok = _open_ws(k, "b2-operator")
        work_id, title = constructed_registry_work(k, ws, tok)
        historical = _file_json(title, source_route="browser", tag="pre-freeze-fact")
        k.execute("SELECT litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, 'constructed-operator', "
                  "'constructed-op-0')",
                  (_jsonb({"sha256": historical.pop("sha256")}),
                   _jsonb(historical | {"work_id": str(work_id), "status": "active"}), ws))
        frozen = _db_now(k)
        k.autocommit = False
        try:
            if arm == "known_bad":
                k.execute(_attach_file_without_the_gate())
            _role(k, "litkb_writer")
            res = k.execute("SELECT litkb.attach_file(%s, %s, %s, %s, 'constructed-operator', 'constructed-op-1')",
                            (ws, tok, work_id, _jsonb(_file_json(title, source_route="browser", tag="from-file")))
                            ).fetchone()[0]
            _role(k, None)
            if res.get("outcome") != "attached":
                raise RuntimeError(f"the constructed bind did not attach: {res}")
            return operator_binds_unproposed(k, {"frozen_at": frozen, "run_workstream_ids": [str(ws)]})
        finally:
            k.rollback()
            k.autocommit = True
    finally:
        k.close()


def _scratch_repo(workdir):
    """A throwaway git repository: main at M, a work branch at B (the prepared commit) that main has NOT
    merged. -> (repo, B). `promote.commit` against it must refuse (verify_merge)."""
    repo = Path(workdir) / f"b2-promote-repo-{uuid.uuid4().hex[:8]}"
    repo.mkdir(parents=True)

    def git(*a):
        r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
        return r.stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "constructed@invalid")
    git("config", "user.name", "CONSTRUCTED")
    (repo / "m.txt").write_text("main\n", encoding="utf-8")
    git("add", "m.txt")
    git("commit", "-q", "-m", "CONSTRUCTED main")
    git("checkout", "-q", "-b", "work/constructed")
    (repo / "b.txt").write_text("branch\n", encoding="utf-8")
    git("add", "b.txt")
    git("commit", "-q", "-m", "CONSTRUCTED work branch (not merged)")
    head = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    return repo, head


def constructed_promote_proof(db, ws, tok, workdir, *, session="constructed-proposer"):
    """D6's end-to-end proof on a WORKER database, every row CONSTRUCTED: a manual admission and a gap
    proposed by `session` in `ws`; the proposing session tries to approve its own admission and is refused
    by BOTH guards (front.approve's label check, and the database's `admissions_second_session_signs_off`);
    `promote prepare` runs through the promoter login and the report is WRITTEN; `promote commit` is refused
    by `verify_merge` because no merge exists. -> {promotion_id, report, refusals}. Raises if any guard did
    not refuse (a fire reports that as DID-NOT-FIRE, never as FIRED)."""
    import psycopg

    from litkb import promote
    from litkb.admit import front

    k = _login(db)
    refusals = {}
    try:
        prop = constructed_proposal(k, ws, tok, session=session, tag="promote-proof")
        _role(k, "litkb_writer")
        k.execute("SELECT * FROM litkb.write_proposal('gap', NULL, %s, NULL, %s, NULL, %s, %s, 'constructed', %s)",
                  (_jsonb({"slug": f"constructed-promote-proof-{uuid.uuid4().hex[:8]}"}),
                   _jsonb({"question": "CONSTRUCTED: does the promote stage prepare a chain end to end?",
                           "gap_state": "open"}), ws, tok, session))
        try:
            front.approve(k, ws, tok, prop["admission_id"], "constructed-proposer", session)
            raise RuntimeError("front.approve let the proposing session approve its own admission")
        except front.AdmissionError as e:
            refusals["python"] = str(e)
        try:
            k.execute("SELECT litkb.approve_admission(%s, %s, %s, %s, %s)",
                      (ws, tok, prop["admission_id"], "constructed-proposer", session))
            raise RuntimeError("approve_admission let the proposing session approve its own admission")
        except psycopg.errors.CheckViolation as e:
            refusals["database"] = str(e).splitlines()[0]
        _role(k, None)
    finally:
        k.close()
    pconn = promote.connect(db)
    try:
        repo, head = _scratch_repo(workdir)
        pid = promote.prepare(pconn, ws, head, None)
        chains = promote.chain_rows(pconn, ws)
        report = promote.write_report(Path(workdir) / "_derived" / "promotions" / f"{pid}.md", promote.render_report(
            ws, pid, head, chains, reasons=promote.hold_reasons(pconn, pid)))
        try:
            promote.commit(pconn, pid, head, repo=repo, fetch_remote=None)
            raise RuntimeError("promote.commit committed a promotion whose branch main has not merged")
        except promote.PromotionRefused as e:
            refusals["commit"] = str(e)
    finally:
        pconn.close()
    return {"promotion_id": str(pid), "report": report, "refusals": refusals, "admission": prop,
            "chains": chains}


def fire_promotion_prepared_by_the_run(conn, arm, workdir):
    """(c): "the proposing session approving its own CONSTRUCTED chain -> refused, and the chain PREPARED by
    that session -> promotions_prepared=1 (on the worker DB)".

    control: the freeze, then `constructed_promote_proof` in the run's workstream (both approve guards
    refuse, prepare writes the report, commit refuses) -> 1. known_bad: the run prepares nothing after the
    freeze, and history does, in the two shapes each scoping clause exists for (auditor-B2 round 2 F2): the
    RUN's own workstream prepared a promotion BEFORE the freeze, and ANOTHER workstream prepares one AFTER it
    (the live shape: 2 historical prepared promotions in other workstreams) -> must read 0, not pass
    vacuously. Either clause deleted alone reads 1 here."""
    from litkb import promote

    db = _worker_db(conn)
    k = _login(db)
    try:
        ws_other, _tok_other = _open_ws(k, "b2-other")
        ws_run, tok_run = _open_ws(k, "b2-run")
    finally:
        k.close()
    if arm == "known_bad":
        pconn = promote.connect(db)
        try:
            promote.prepare(pconn, ws_run, "0" * 40, None)          # the run's workstream, BEFORE the freeze
        finally:
            pconn.close()
    k = _login(db)
    try:
        frozen = _db_now(k)
    finally:
        k.close()
    if arm == "known_bad":
        pconn = promote.connect(db)
        try:
            promote.prepare(pconn, ws_other, "1" * 40, None)        # another workstream, AFTER the freeze
        finally:
            pconn.close()
    if arm == "control":
        constructed_promote_proof(db, ws_run, tok_run, workdir)
    k = _login(db)
    try:
        return promotions_prepared(k, {"frozen_at": frozen, "run_workstream_ids": [str(ws_run)]})
    finally:
        k.close()


def fire_self_refusal(conn, arm, workdir):
    """The refuse verb's SECOND guard: "the refuse verb applied by the PROPOSING session -> refused".

    Both arms: a CONSTRUCTED proposal by `constructed-proposer`; then `litkb.refuse_admission` is called
    DIRECTLY (past the Python guard) from another workstream with the proposer's own session label.
    control: `adjudications_second_session_decides` refuses it -> `self_adjudications` 0. known_bad: that
    constraint dropped (in a transaction, rolled back) -> the self-refusal lands -> 1."""
    import psycopg

    db = _worker_db(conn)
    k = _login(db)
    try:
        ws_p, tok_p = _open_ws(k, "b2-self-p")
        prop = constructed_proposal(k, ws_p, tok_p, session="constructed-proposer")
        ws_r, tok_r = _open_ws(k, "b2-self-r")
        k.autocommit = False
        try:
            if arm == "known_bad":
                k.execute("ALTER TABLE litkb.adjudications DROP CONSTRAINT adjudications_second_session_decides")
            _role(k, "litkb_writer")
            try:
                with k.transaction():
                    k.execute("SELECT litkb.refuse_admission(%s, %s, %s, %s, %s, %s)",
                              (ws_r, tok_r, prop["admission_id"], "CONSTRUCTED fire: the proposer refuses itself",
                               "constructed-reviewer", "constructed-proposer"))
            except psycopg.errors.CheckViolation:
                pass                                    # the guard refused; the savepoint rolled it back
            _role(k, None)
            return self_adjudications(k, {"frozen_at": None, "scope_workstream_ids": [str(ws_p)]})
        finally:
            k.rollback()
            k.autocommit = True
    finally:
        k.close()


def fire_decision_log_rewrite(conn, arm, workdir):
    """The decision log's append-only guard: "a decision-log UPDATE -> refused".

    Both arms: a CONSTRUCTED proposal refused by a second session (one decision row), then the WRITER tries
    to rewrite that row's reason. control: no grant and the append-only trigger refuse it ->
    `decision_log_unguarded` 0. known_bad: UPDATE granted to the writer and the trigger disabled (in a
    transaction, rolled back) -> the rewrite lands (asserted) -> 2."""
    import psycopg

    from litkb.admit import front

    db = _worker_db(conn)
    k = _login(db)
    try:
        ws_p, tok_p = _open_ws(k, "b2-log-p")
        prop = constructed_proposal(k, ws_p, tok_p, session="constructed-proposer")
        ws_r, tok_r = _open_ws(k, "b2-log-r")
        _role(k, "litkb_writer")
        res = front.refuse(k, ws_r, tok_r, prop["admission_id"], "CONSTRUCTED fire: refused so a row exists",
                           "constructed-reviewer", "constructed-second-session")
        _role(k, None)
        k.autocommit = False
        try:
            if arm == "known_bad":
                k.execute("GRANT UPDATE ON litkb.adjudications TO litkb_writer")
                k.execute("ALTER TABLE litkb.adjudications DISABLE TRIGGER adjudications_append_only")
                # the table's CHECK constraints call litkb.norm_label, which no agent role may EXECUTE (0014), so
                # a writer's UPDATE is ALSO refused there — measured 2026-09-23 on the first run of this arm. That
                # refusal is incidental (it would vanish the day norm_label is granted); the mutation grants it so
                # the arm measures the two guards the log is DESIGNED to have, not a side effect.
                k.execute("GRANT EXECUTE ON FUNCTION litkb.norm_label(text) TO litkb_writer")
            _role(k, "litkb_writer")
            landed = 0
            try:
                with k.transaction():
                    cur = k.execute("UPDATE litkb.adjudications SET reason = 'CONSTRUCTED: rewritten' WHERE id = %s",
                                    (res["decision_id"],))
                    landed = cur.rowcount
            except (psycopg.errors.InsufficientPrivilege, psycopg.errors.RaiseException):
                landed = 0
            _role(k, None)
            if arm == "known_bad" and landed != 1:
                raise RuntimeError("the known-bad arm's rewrite did not land; the fire would measure nothing")
            if arm == "control" and landed != 0:
                raise RuntimeError("the control arm's rewrite LANDED: the decision log is not append-only")
            return decision_log_unguarded(k, {})
        finally:
            k.rollback()
            k.autocommit = True
    finally:
        k.close()


FIRES = {
    "refuse_verb_removed": {"counter": "proposals_unadjudicated", "run": fire_refuse_verb_removed,
                            "bound": "==0"},
    "operator_bind_as_version_of_record": {"counter": "operator_binds_unproposed",
                                           "run": fire_operator_bind_as_version_of_record, "bound": "==0"},
    "promotion_prepared_by_the_run": {"counter": "promotions_prepared", "run": fire_promotion_prepared_by_the_run,
                                      "bound": ">=1"},
    "self_refusal": {"counter": "self_adjudications", "run": fire_self_refusal, "bound": "==0"},
    "decision_log_rewrite": {"counter": "decision_log_unguarded", "run": fire_decision_log_rewrite, "bound": "==0"},
}


def within(value, bound):
    """`bound` is "==0" or ">=1" (the FIRES entries' extra key)."""
    op, n = bound[:2], int(bound[2:])
    return value == n if op == "==" else value >= n


if __name__ == "__main__":                       # a cold re-fire, one arm pair per fire, on LITKB_TEST_DB
    import argparse
    import importlib.util
    import json
    import tempfile

    from litkb.db import connect as c
    from litkb.db import migrate

    # the suite's advisory lock, from the sibling driver that already names it (litkb_edge_run._SUITE_LOCK,
    # itself qc/conftest.py `_LITKB_SUITE_LOCK`), loaded by path as litkb_acceptance._edge_run loads it —
    # never a third copy of the literal
    _spec = importlib.util.spec_from_file_location("litkb_edge_run",
                                                   SCRIPTS / "qc" / "instruments" / "litkb_edge_run.py")
    _edge = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_edge)
    SUITE_LOCK = _edge._SUITE_LOCK

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="comma-separated fire names")
    args = ap.parse_args()
    names = [n for n in FIRES if not args.only or n in args.only.split(",")]
    out = {}
    for name in names:
        f = FIRES[name]
        vals = {}
        for arm in ("control", "known_bad"):
            conn = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
            try:
                # the suite's own advisory lock (qc/conftest.py litkb_pg_base): never reset a database a
                # pytest process is using; the lock is released when this arm's connection closes
                conn.execute("SELECT pg_advisory_lock(%s)", (SUITE_LOCK,))
                migrate.reset(conn)
                migrate.apply(conn)
                with tempfile.TemporaryDirectory() as td:
                    vals[arm] = f["run"](conn, arm, td)
            except Exception as e:                  # noqa: BLE001 — an arm that errors never FIRES
                vals[arm] = f"error: {type(e).__name__}: {e}"
            finally:
                conn.close()
        fired = (isinstance(vals["control"], int) and isinstance(vals["known_bad"], int)
                 and within(vals["control"], f["bound"]) and not within(vals["known_bad"], f["bound"]))
        out[name] = {"counter": f["counter"], "bound": f["bound"], **vals,
                     "verdict": "FIRED" if fired else "DID-NOT-FIRE"}
        print(json.dumps({name: out[name]}, default=str))
    raise SystemExit(0 if all(v["verdict"] == "FIRED" for v in out.values()) else 1)

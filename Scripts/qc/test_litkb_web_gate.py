"""The web-source gate, after Kam MOVED the boundary (decisions.yaml `litkb-web-source-gate`).

A web source is admitted by the manual route, so every version it writes is a PROPOSAL in the
admitting workstream and `files.current_version_id` stays NULL until a second session approves it
(migration 0013, check 4). Until 2026-09-20 `litkb_search` and `litkb_record_use` joined
`litkb.main_files`, so the join itself was the gate: the session that had just proposed a source
could not read one word of it back. The decision keeps the gate where it protects the
AUTHORITATIVE record — promotion — and removes it from search INSIDE the proposing workstream.

Four rows, each against the real database named by LITKB_TEST_DB (never `litkb`), and each one an
end-to-end call of the real MCP tool over a real MCP session:

  (a) VISIBLE from the proposing workstream       the loop can read what it just found
  (b) INVISIBLE from another open workstream      one workstream's proposal is not another's
  (c) INVISIBLE with no open workstream           what every tree saw before this change
  (d) HELD at promote prepare                     the unapproved source cannot reach main

(b), (c) and (d) are the mutation rows: each asserts something the gate must REFUSE, so each fails
if the predicate is widened past the decision. Harness rows W1-W6
(`qc/instruments/litkb_p2_mutations.py`) break each call site in turn and require this file to go
red. (a) is the row that fails if the widening is not there at all. Rows (d2), (e) and (f) carry
the three call sites and the token check that (a)-(d) do not reach on their own.

Run:
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w1 py -3.12 -m pytest qc/test_litkb_web_gate.py
"""
import json
import subprocess
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
pg_only = pytest.mark.requires_litkb_pg

#: The proposed source. The snapshot's first page must carry the title and the first author, because
#: check 3 binds against it exactly as it binds a PDF's first page — a web snapshot is weaker
#: evidence than a publisher PDF, not a weaker CHECK.
#:
#: The TITLE and the URL carry a per-admission tag, for the reason qc/test_litkb_p8.py gives for its
#: CLAIMS table: the database is reset once per pytest session, and admission's check 2 is exactly
#: right to refuse the same source twice — by identifier, and (a URL is not a strong identifier) by
#: title similarity at 0.70. Two rows that each admit "the web source" would be testing that check
#: instead of this one, so each row admits a source of its own rather than the suite weakening a
#: check it depends on. The tag is hex: two tagged titles share only the four words in front of it.
WEB = {"title": "Manual proposal {tag}", "authors": "Ockendon", "year": 2021,
       "url": "https://example.invalid/canopy/{tag}", "retrieved": "2026-09-20"}
#: the sentence the search finds and the use quotes. Deliberately not a phrase from any real work in
#: the lake: the row must pass or fail on visibility, never on what else the corpus happens to hold.
PASSAGE = ("Canopy change detected between two leaf-off acquisitions is dominated by phenology "
           "rather than by growth, and a mask projected across them inherits that difference as "
           "label error.")
QUERY = "canopy change leaf-off acquisitions phenology label error"


# ── the environment ───────────────────────────────────────────────────────────────────────

def _mcp(calls, env):
    """Drive the real server over a real MCP session, with `env` applied to os.environ first.

    A fresh in-memory client/server pair per call list, as qc/test_litkb_p8.py does: the tools read
    LITKB_WORKTREE at call time, so pointing the same server at workstream A and then at workstream
    B is exactly the thing being tested."""
    import os

    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    from litkb.mcp.server import build_server

    old = {k: os.environ.get(k) for k in env}
    os.environ.update({k: str(v) for k, v in env.items()})
    out = []

    async def drive():
        low = build_server()._lowlevel_server
        async with create_client_server_memory_streams() as ((cr, cw), (sr, sw)):
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: low.run(sr, sw, low.create_initialization_options(),
                                              raise_exceptions=True))
                async with ClientSession(cr, cw) as cs:
                    await cs.initialize()
                    for name, args in calls:
                        r = await cs.call_tool(name, args)
                        text = "".join(c.text for c in r.content if getattr(c, "text", None))
                        try:
                            out.append(json.loads(text))
                        except ValueError:
                            out.append({"raw": text})
                tg.cancel_scope.cancel()

    try:
        anyio.run(drive)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return out


def _git_worktree(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@local",
                    "commit", "-q", "--allow-empty", "-m", "base"], check=True)
    return path


@pytest.fixture
def kb(tmp_path, litkb_pg_base):
    """A migrated throwaway database, a literature root, and TWO worktrees each with its own open
    workstream — plus a third with none at all.

    `litkb_test` stands in for reader, writer and ingest (member of all three WITH INHERIT FALSE),
    which is how the P1 and P8 suites already exercise every role; nothing here can reach `litkb`.
    """
    from litkb import workstream
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    tag = uuid.uuid4().hex[:8]
    wt = {n: _git_worktree(tmp_path / n) for n in ("A", "B", "none")}
    ws = {n: str(workstream.open_workstream(conn, f"web-gate-{n}-{tag}", "test",
                                            f"web source gate, workstream {n}", directory=wt[n]))
          for n in ("A", "B")}
    assert not (wt["none"] / workstream.TOKEN_FILE).exists()
    env = {"LITKB_DB": c.DB_TEST, "LITKB_READER_ROLE": "litkb_test",
           "LITKB_WRITER_ROLE": "litkb_test", "LITKB_LITERATURE_ROOT": str(root),
           "LITKB_AGENT": "web-gate-test", "LITKB_SESSION": f"web-gate-{tag}"}
    return {"conn": conn, "root": root, "wt": wt, "ws": ws, "env": env, "db": c.DB_TEST,
            "tmp": tmp_path}


def env_at(kb, which):
    """The server's environment, pointed at one of the three worktrees."""
    return dict(kb["env"], LITKB_WORKTREE=str(kb["wt"][which]))


def propose_web_source(kb):
    """Admit the web source as a manual PROPOSAL in workstream A, extract one block of it, and
    return (work_id, file_id, block_id).

    The admission is the real one — `litkb.admit.front.admit_web`, the path `litkb hunt` takes for
    a URL — so what the rows below measure is the database's own proposal state, not a fixture's
    imitation of one. The extraction run stands in for P5 exactly as `test_litkb_p8._seed_block`
    does; GROBID is not in this test's scope."""
    from litkb import workstream
    from litkb.admit.front import admit_web

    conn = kb["conn"]
    ws_id, token = workstream.load(kb["wt"]["A"])
    tag = uuid.uuid4().hex[:12]
    title, url = WEB["title"].format(tag=tag), WEB["url"].format(tag=tag)
    snap = kb["tmp"] / f"snapshot-{tag}.txt"
    snap.write_text(f"{title}\n{WEB['authors']}, {WEB['year']}\n\n{PASSAGE}\n", encoding="utf-8")
    res = admit_web(conn, ws_id, token, title=title, authors=WEB["authors"],
                    year=WEB["year"], url=url, retrieved=WEB["retrieved"],
                    snapshot_path=snap, source_note="the web-source gate test",
                    root=kb["root"], agent="web-gate-admitter",
                    session=f"admit-{uuid.uuid4().hex[:8]}")
    assert res["outcome"] == "proposed", res
    work_id, file_id = res["work_id"], res["file_id"]
    # BEGIN the property every row below rests on: this is an UNAPPROVED proposal
    main = conn.execute("SELECT (SELECT current_version_id FROM litkb.works WHERE id = %s), "
                        "       (SELECT current_version_id FROM litkb.files WHERE id = %s)",
                        (work_id, file_id)).fetchone()
    assert main == (None, None), ("the admission is not a proposal: main already points at it", main)
    heads = dict(conn.execute("SELECT entity, count(*) FROM litkb.ws_heads WHERE workstream_id = %s "
                              "GROUP BY 1", (ws_id,)).fetchall())
    assert heads.get("work") == 1 and heads.get("file") == 1, heads
    # END
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'web-gate-seed', '0', %s, 'v0', "
        "'local', 'ok') RETURNING id", (file_id, uuid.uuid4().hex)).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    block_id = conn.execute(
        "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
        "VALUES (%s, %s, 1, 'paragraph', %s) RETURNING id",
        (file_id, run_id, PASSAGE)).fetchone()[0]
    return str(work_id), str(file_id), str(block_id)


def block_ids(result):
    return [b["block_id"] for b in result.get("blocks", [])]


def unapproved_hits(kb, result):
    """The returned blocks whose FILE main does not point at — i.e. every unapproved proposal in
    this result, whoever proposed it.

    The rows below assert on this rather than on `blocks == []`, because an empty result is not a
    property this test can own: the any-term leg matches ANY word of the query, so in a database
    other modules have populated ("change", "label", "error") there are always approved hits. That
    is what `qc/check.py` found and a run of this file alone never could — the file sorts last in
    `pytest qc`, so it is the only litkb module that sees the whole session's material."""
    ids = block_ids(result)
    if not ids:
        return []
    return [str(r[0]) for r in kb["conn"].execute(
        "SELECT b.id FROM litkb.blocks b JOIN litkb.files f ON f.id = b.file_id "
        "WHERE b.id = ANY(%s::uuid[]) AND f.current_version_id IS NULL", (ids,)).fetchall()]


# ── (a) visible from the workstream that proposed it ──────────────────────────────────────

@pg_only
def test_a_visible_from_the_proposing_workstream(kb):
    """The decision's whole point: the loop keeps moving. Workstream A proposed the source, so
    workstream A can search it, and the result SAYS the hits include its own proposals."""
    _work, _file, block = propose_web_source(kb)
    r = _mcp([("litkb_search", {"query": QUERY, "limit": 50})], env_at(kb, "A"))[0]
    assert r["ok"], r
    assert block in block_ids(r), r
    hit = [b for b in r["blocks"] if b["block_id"] == block][0]
    assert PASSAGE[:40] in hit["text"], hit
    assert "proposed" in r["proposals"] and "HELD at promote prepare" in r["proposals"], r["proposals"]


# ── (b) invisible from a different workstream ─────────────────────────────────────────────

@pg_only
def test_b_invisible_from_a_different_workstream(kb):
    """MUTATION ROW. Workstream B has its own token and its own worktree, and sees main only. A
    predicate that widened search to "any proposal" instead of "this workstream's" fails here."""
    _work, _file, block = propose_web_source(kb)
    r = _mcp([("litkb_search", {"query": QUERY, "limit": 50})], env_at(kb, "B"))[0]
    assert r["ok"], r
    assert block not in block_ids(r), ("workstream B can read A's unapproved proposal", r)
    assert unapproved_hits(kb, r) == [], ("workstream B read an unapproved proposal", r)


# ── (c) invisible with no workstream at all ───────────────────────────────────────────────

@pg_only
def test_c_invisible_with_no_workstream(kb):
    """MUTATION ROW, and the regression: a tree with no `.litkb-workstream` sees exactly what it saw
    before the change. `ws` binds NULL, the correlated subquery returns NULL, `coalesce` falls back
    to main's pointer and the EXISTS is false — the old join, clause for clause."""
    _work, _file, block = propose_web_source(kb)
    r = _mcp([("litkb_search", {"query": QUERY, "limit": 50})], env_at(kb, "none"))[0]
    assert r["ok"], r
    assert block not in block_ids(r), r
    assert unapproved_hits(kb, r) == [], \
        ("an unapproved proposal is readable from a tree with no workstream", r)
    assert "no open workstream" in r["proposals"], r["proposals"]


@pg_only
def test_c2_the_no_workstream_predicate_is_the_old_one(kb):
    """The regression stated as an identity rather than as a corpus: over EVERY block in the
    database, the new FROM clause with `ws` NULL returns the same (block, work) set as the
    `main_files`/`main_works` join it replaced.

    This is what the brief's live-corpus regression asserts about three named blocks, asserted
    about all of them — on the throwaway database, because a test never touches `litkb`."""
    from litkb import visibility

    propose_web_source(kb)                      # at least one proposal exists to be excluded
    conn = kb["conn"]
    new = set(conn.execute(
        "SELECT b.id::text, w.key FROM litkb.blocks b "
        "JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id "
        + visibility.FILE_JOIN, {"ws": None}).fetchall())
    old = set(conn.execute(
        "SELECT b.id::text, w.key FROM litkb.blocks b "
        "JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id "
        "JOIN litkb.main_files mf ON mf.version_id = f.current_version_id "
        "JOIN litkb.main_works w ON w.work_id = mf.work_id").fetchall())
    assert new == old, (len(new), len(old), sorted(new ^ old)[:5])


@pg_only
def test_the_reader_role_may_read_the_visibility_tables(kb):
    """`litkb_reader` is the login the search tool uses, and the new join reads two tables the old
    one did not name. The grant is 0006's `GRANT SELECT ON ALL TABLES`; this MEASURES it instead of
    trusting it, because a reader that cannot see `ws_heads` would fail closed in production and
    pass here, where the suite logs in as the database's owner.

    `litkb.workstreams` is in the list since the state check (row g): `visibility.is_open` runs on
    the SAME reader connection, and a reader that could not read it would refuse every search in a
    worktree that has a workstream at all."""
    from litkb import visibility

    conn = kb["conn"]
    conn.execute("SET ROLE litkb_reader")
    try:
        rows = conn.execute(
            "SELECT count(*) FROM litkb.blocks b "
            "JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id "
            + visibility.FILE_JOIN, {"ws": None}).fetchone()[0]
        assert rows >= 0
        for t in ("ws_heads", "file_versions", "works", "workstreams"):
            conn.execute(f"SELECT count(*) FROM litkb.{t}").fetchone()
        assert visibility.is_open(conn, kb["ws"]["A"]) is True
    finally:
        conn.execute("RESET ROLE")


# ── (d) the promotion boundary, unchanged ─────────────────────────────────────────────────

@pg_only
def test_d_a_use_quoting_the_proposal_is_held_at_prepare(kb):
    """MUTATION ROW, and the boundary the decision protects. Workstream A may quote its own
    proposal — `litkb_record_use` records the use and the DATABASE verifies the quote — and the
    chain is HELD at `promote prepare`, so nothing unapproved reaches main.

    The reason is read from `litkb.promotions.conflicts`, which is where prepare records the
    dependency holds (the same place qc/test_litkb_p1.py and qc/test_litkb_p2.py read them): the
    use depends on its work, and a manual admission's work chain always carries "a work, identifier
    or file enters main only through litkb.approve_admission"."""
    work_id, _file, block = propose_web_source(kb)
    env = env_at(kb, "A")
    used, offered = _mcp([
        ("litkb_record_use", {
            "statement": "supplies the phenology-over-growth reading of leaf-off change",
            "kind": "context", "quote": PASSAGE[:80], "block_id": block,
            "gap": f"web-gate-{uuid.uuid4().hex[:6]}",
            "gap_question": "does an unapproved web source reach main?",
            "feeds": "decision litkb-web-source-gate"}),
        ("litkb_propose_promotion", {})], env)
    # the quote is recordable and VERIFIED — the half the decision unblocks
    assert used["ok"], used
    assert used["quote_verified"] is True, used
    use_id = used.get("use_id")
    assert use_id, used
    # and the promotion is held — the half the decision keeps
    assert offered["ok"], offered
    pid = offered.get("promotion_id")
    assert pid, offered
    held = {c["chain"]: c for c in offered.get("held", [])}
    assert f"use:{use_id}" in held, ("the use quoting an unapproved proposal was PREPARED", offered)
    assert f"work:{work_id}" in held, offered
    # The GAP the use opened IS prepared, and should be: a question is not a web source. What may
    # not be prepared is anything carrying the unapproved source — its work, its identifier, its
    # file, or the use that quotes it.
    assert [p for p in offered.get("prepared", []) if not p.startswith("gap:")] == [], offered
    conflicts = kb["conn"].execute("SELECT conflicts FROM litkb.promotions WHERE id = %s",
                                   (pid,)).fetchone()[0]
    reasons = {c["chain"]: c.get("reasons", []) for c in conflicts if "reasons" in c}
    assert any("approve_admission" in r for r in reasons.get(f"work:{work_id}", [])), conflicts
    assert any(f"dependency held: work:{work_id}" in r for r in reasons.get(f"use:{use_id}", [])), \
        ("prepare did not hold the use on its unapproved work", conflicts)
    # MUTATION ROW (W10). The reason above must REACH the two places a human reads: the JSON this
    # tool returns and the markdown report the CLI writes into the worktree for Kam's merge. It did
    # not — a chain held only by the dependency fixpoint has no problems of its own, so both
    # rendered `—` on the one chain this decision exists to hold (auditor-2a §7.2). The reason was
    # never missing; `_ws_chains` does not carry it and `promotions.conflicts` does
    # (promote.hold_reasons).
    assert any(f"dependency held: work:{work_id}" in w
               for w in held[f"use:{use_id}"]["why"]), ("the held use carries no reason", offered)
    report = Path(offered["report_written"]).read_text(encoding="utf-8")
    line = [ln for ln in report.splitlines() if f"`{use_id}`" in ln]
    assert len(line) == 1, (offered["report_written"], line)
    assert f"dependency held: work:{work_id}" in line[0], line[0]
    assert "| — |" not in line[0], ("the report renders an em dash for the held use", line[0])
    state = kb["conn"].execute(
        "SELECT state FROM litkb.use_versions WHERE version_id = %s",
        (used["use_version_id"],)).fetchone()[0]
    assert state == "proposed", ("a use quoting an unapproved proposal reached `prepared`", state)


@pg_only
def test_e_a_forged_token_buys_no_proposal(kb):
    """MUTATION ROW at the token check. A workstream id is not a secret — a tracked report prints
    one, `litkb_ws_open` returns one — so the P8 referee's F-1 attack is a `.litkb-workstream` that
    names a REAL workstream with a token of zeros. Widening search on the id alone would hand that
    file the proposals of the session that owns it. The search is refused before a row is read."""
    from litkb import workstream

    _work, _file, block = propose_web_source(kb)
    forged = _git_worktree(kb["tmp"] / "forged")
    (forged / workstream.TOKEN_FILE).write_text(
        json.dumps({"workstream_id": kb["ws"]["A"], "token": "0" * 64}), encoding="utf-8")
    r = _mcp([("litkb_search", {"query": QUERY, "limit": 50})],
             dict(kb["env"], LITKB_WORKTREE=str(forged)))[0]
    assert r["ok"] is False and r["refused"] == "bad-token", r
    assert block not in json.dumps(r), "a forged token read the workstream's proposal"
    assert kb["ws"]["A"] not in json.dumps(r), "the refusal named the workstream"
    # the two halves of the same refusal: row (h) is a token file naming a workstream that does not
    # exist, this one is a REAL workstream with the wrong token, and both must say what to do about
    # the file rather than leaving a tool dark with no reason (audit §7.1).
    assert str(forged / workstream.TOKEN_FILE) in r["message"], r["message"]
    assert "REFUSED" in r["message"], r["message"]


@pg_only
def test_f_locate_quote_is_the_same_predicate(kb):
    """MUTATION ROW at the THIRD call site. `use.locate_quote` is the CLI's half of "where does this
    quote live", and it had its own `main_files` join. One definition now serves both, so the CLI
    cannot end up able to find a quote the MCP path cannot, or the other way round.

    Its default is `ws=None` — the CLI's behaviour is unchanged by this branch, because
    `use.work_by` still resolves a work through `main_works` — so both directions are asserted here
    rather than through the CLI."""
    from litkb import use as _use

    work_id, _file, block = propose_web_source(kb)
    conn = kb["conn"]
    with_ws = _use.locate_quote(conn, work_id, PASSAGE[:80], ws=kb["ws"]["A"])
    assert [str(h["block_id"]) for h in with_ws] == [block], with_ws
    assert _use.locate_quote(conn, work_id, PASSAGE[:80]) == [], "main sees an unapproved proposal"
    assert _use.locate_quote(conn, work_id, PASSAGE[:80], ws=kb["ws"]["B"]) == [], \
        "workstream B sees workstream A's unapproved proposal"


# ── (g) the workstream must still be OPEN ─────────────────────────────────────────────────

@pg_only
def test_g_a_workstream_that_is_no_longer_open_widens_nothing(kb):
    """MUTATION ROW (W7/W8/W9), and the hole the audit found in the first cut of this branch
    (auditor-2a §4a): `litkb.check_ws_token` reads `workstream_tokens` and NOTHING else, so it
    answers TRUE for a workstream that has been merged or abandoned. Nothing deletes
    `.litkb-workstream` at a merge, so a finished worktree kept searching, briefing and quoting
    proposals that never entered main — reads stayed wide open while the writes were refused.

    The state is flipped in the database directly, which is what `promote commit` does at the end
    of a merge (`promote_commit` sets `workstreams.state = 'merged'`, 0005) — the row is about the
    STATE, not about how it got there.

    Search NARROWS (a merged workstream's own main-visible material is still searchable, and the
    result says why); `litkb_brief` and `litkb_record_use` REFUSE, because each is about one
    workstream and a main-only view of somebody else's material is not an answer to either."""
    _work, _file, block = propose_web_source(kb)
    env = env_at(kb, "A")
    before = _mcp([("litkb_search", {"query": QUERY, "limit": 50})], env)[0]
    assert block in block_ids(before), ("the widening was not there to begin with", before)
    # `closed_at` and `merge_commit` alongside the state, because the table's own CHECKs
    # (`workstreams_closed_iff_not_open` and `workstreams_merged_iff_commit`, 0001_core.sql:41-42)
    # tie all three — a merged workstream with a NULL `closed_at` or no merge commit is a row the
    # database would never hold, so the row below is the state `promote commit` actually leaves.
    kb["conn"].execute("UPDATE litkb.workstreams SET state = 'merged', closed_at = now(), "
                       "merge_commit = %s WHERE id = %s",
                       (uuid.uuid4().hex + uuid.uuid4().hex[:8], kb["ws"]["A"]))
    after, briefed, used, mine, cands = _mcp([
        ("litkb_search", {"query": QUERY, "limit": 50}),
        ("litkb_brief", {}),
        ("litkb_record_use", {
            "statement": "quotes a proposal after the workstream was merged",
            "kind": "context", "quote": PASSAGE[:80], "block_id": block,
            "gap": f"web-gate-merged-{uuid.uuid4().hex[:6]}",
            "gap_question": "does a merged workstream still quote its proposal?",
            "feeds": "decision litkb-web-source-gate"}),
        ("litkb_my_uses", {}),
        ("litkb_candidates", {})], env)
    assert after["ok"], after
    assert block not in block_ids(after), ("a merged workstream still reads its proposal", after)
    assert unapproved_hits(kb, after) == [], after
    assert "no longer open" in after["proposals"] and "merged" in after["proposals"], \
        after["proposals"]
    assert briefed["ok"] is False and briefed["refused"] == "workstream-not-open", briefed
    assert used["ok"] is False and used["refused"] == "workstream-not-open", used
    # MUTATION ROWS W12/W13. The same rule at the two other tools that answer ABOUT one workstream
    # from its own `ws_heads`/`candidates`: each already presented the token and neither looked at
    # the state, so a merged worktree read its own proposed versions back as though the branch were
    # still in flight. `litkb_ws_status` is deliberately NOT in this list — reporting the state is
    # its job, and it is the tool that tells a session why the other four now refuse.
    assert mine["ok"] is False and mine["refused"] == "workstream-not-open", mine
    assert cands["ok"] is False and cands["refused"] == "workstream-not-open", cands
    # and nothing was written by the refused call
    assert kb["conn"].execute(
        "SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity = 'use'",
        (kb["ws"]["A"],)).fetchone()[0] == 0, "a merged workstream recorded a use"


# ── (h) a token file that outlived its workstream ─────────────────────────────────────────

@pg_only
def test_h_a_stale_token_file_refuses_search_and_names_the_file(kb):
    """The behaviour change this branch introduced and did not state (auditor-2a §7.1), now
    DECIDED and tested: before it, `_search` never called `_session()`, so a `.litkb-workstream`
    naming a workstream this database does not have was simply ignored and the tree searched main.
    Now the search is REFUSED.

    Failing closed is the choice: a token file that no longer checks out is a configuration error,
    and a tool that quietly narrowed to main would hide it — an unattended loop would read the
    narrowed result as "the corpus does not have this". So the refusal has to say what to do, and
    it names the FILE (the refusal still names nothing about the workstream — row (e) holds that)."""
    from litkb import workstream

    stale = _git_worktree(kb["tmp"] / "stale")
    gone = str(uuid.uuid4())
    (stale / workstream.TOKEN_FILE).write_text(
        json.dumps({"workstream_id": gone, "token": "a" * 64}), encoding="utf-8")
    r = _mcp([("litkb_search", {"query": QUERY, "limit": 50})],
             dict(kb["env"], LITKB_WORKTREE=str(stale)))[0]
    assert r["ok"] is False and r["refused"] == "bad-token", r
    assert "blocks" not in r, ("a refused search returned hits", r)
    assert str(stale / workstream.TOKEN_FILE) in r["message"], r["message"]
    assert "REFUSED" in r["message"], r["message"]
    assert "removed" in r["message"] and "opened" in r["message"], r["message"]
    assert gone not in json.dumps(r), "the refusal named the workstream"


# ── (j) the drop-off tool obeys the same two rules ────────────────────────────────────────

@pg_only
def test_j_hunt_request_add_refuses_a_merged_workstream_and_presents_its_token(kb):
    """MUTATION ROWS (W14, W15). `litkb_hunt_request_add` is the loop's FIRST write — the drop-off
    a review agent makes before any full text exists. On a merged workstream it reached
    `litkb.record_hunt_request`, whose PL/pgSQL RAISE arrived as `refused: error` carrying the
    database's raw sentence: the operational referee's R-1 shape, which an unattended loop cannot
    act on (auditor-2a2). It now refuses like the other four, and names the file.

    The forged-token half is here rather than in a row of its own because it is the same two lines
    in the other order: without the token check the state check answers first, and a caller who
    cannot present the token is told that the workstream is merged."""
    from litkb import workstream

    env = env_at(kb, "A")
    first = _mcp([("litkb_hunt_request_add", {
        "ref": f"10.5555/open-{uuid.uuid4().hex[:8]}", "ref_scheme": "doi",
        "expected_claim": "leaf-off phenology dominates two-date canopy change",
        "why_relevant": "the label-error argument this workstream is testing"})], env)[0]
    assert first["ok"], ("an OPEN workstream cannot drop off a hunt request", first)
    kb["conn"].execute("UPDATE litkb.workstreams SET state = 'merged', closed_at = now(), "
                       "merge_commit = %s WHERE id = %s",
                       (uuid.uuid4().hex + uuid.uuid4().hex[:8], kb["ws"]["A"]))
    drop = {"ref": f"10.5555/merged-{uuid.uuid4().hex[:8]}", "ref_scheme": "doi",
            "expected_claim": "anything at all", "why_relevant": "tests the state gate"}
    after = _mcp([("litkb_hunt_request_add", drop)], env)[0]
    assert after["ok"] is False, after
    assert after["refused"] == "workstream-not-open", \
        ("the database's raw RAISE is still the refusal a caller reads", after)
    assert ".litkb-workstream" in after["message"], after["message"]
    forged = _git_worktree(kb["tmp"] / "forged-hr")
    (forged / workstream.TOKEN_FILE).write_text(
        json.dumps({"workstream_id": kb["ws"]["A"], "token": "0" * 64}), encoding="utf-8")
    bad = _mcp([("litkb_hunt_request_add", drop)],
               dict(kb["env"], LITKB_WORKTREE=str(forged)))[0]
    assert bad["ok"] is False and bad["refused"] == "bad-token", bad
    assert "merged" not in json.dumps(bad), ("a forged token was told the workstream's state", bad)
    assert kb["conn"].execute(
        "SELECT count(*) FROM litkb.hunt_requests WHERE workstream_id = %s",
        (kb["ws"]["A"],)).fetchone()[0] == 1, "a refused drop-off was written"


# ── (i) the quote path presents the token BEFORE it widens ────────────────────────────────

@pg_only
def test_i_record_use_presents_the_token_before_it_widens(kb):
    """MUTATION ROW (W11), and the hole this branch opened at its second call site.

    `litkb_search` widens only after `_require_token` — the P8 referee's F-1 rule, because a
    workstream id is not a secret. `litkb_record_use` resolved its workstream with `_session()` and
    presented that token to nobody: it bound the UNVERIFIED id straight into
    `visibility.FILE_JOIN`, so a `.litkb-workstream` naming a real workstream with a wrong token
    reached that workstream's unapproved proposal blocks. The WRITE was still refused — the
    database checks the token on `write_proposal` — but the refusals on the way there are built
    from the block: `quote-not-in-block` returns the proposal's `work_key`, which is a fact about a
    source no second session has approved and this caller cannot read.

    THE QUOTE IS DELIBERATELY NOT IN THE BLOCK, and that is what lets this row tell the two worlds
    apart. With the guard the call is refused `bad-token` having resolved nothing. Without it the
    block resolves, the quote misses, and the refusal names the work — and a row that asserted only
    `refused == "bad-token"` would pass in both worlds, because the database refuses the write on
    the token either way."""
    from litkb import workstream

    _work, _file, block = propose_web_source(kb)
    key = kb["conn"].execute(
        "SELECT w.key FROM litkb.blocks b JOIN litkb.files f ON f.id = b.file_id "
        "JOIN litkb.file_versions fv ON fv.file_id = f.id "
        "JOIN litkb.works w ON w.id = fv.work_id WHERE b.id = %s LIMIT 1", (block,)).fetchone()[0]
    forged = _git_worktree(kb["tmp"] / "forged-use")
    (forged / workstream.TOKEN_FILE).write_text(
        json.dumps({"workstream_id": kb["ws"]["A"], "token": "0" * 64}), encoding="utf-8")
    r = _mcp([("litkb_record_use", {
        "statement": "tries to quote a proposal with a forged token",
        "kind": "context", "quote": "a sentence that is nowhere in that block at all",
        "block_id": block, "gap": f"web-gate-forged-{uuid.uuid4().hex[:6]}",
        "gap_question": "does a forged token resolve a block?",
        "feeds": "decision litkb-web-source-gate"})],
        dict(kb["env"], LITKB_WORKTREE=str(forged)))[0]
    assert r["ok"] is False and r["refused"] == "bad-token", r
    assert key not in json.dumps(r), ("the refusal named the proposal's work", r)
    assert block not in json.dumps(r), ("the refusal named the block", r)
    assert kb["ws"]["A"] not in json.dumps(r), "the refusal named the workstream"
    # nothing was written: the gap this call would have opened does not exist
    assert kb["conn"].execute(
        "SELECT count(*) FROM litkb.ws_heads WHERE workstream_id = %s AND entity = 'gap'",
        (kb["ws"]["A"],)).fetchone()[0] == 0, "a forged token opened a gap"


@pg_only
def test_d2_another_workstream_cannot_quote_the_proposal(kb):
    """MUTATION ROW at the SECOND call site. `litkb_record_use` has its own block lookup, so search
    could be gated correctly while the quote path was not: workstream B, handed A's block_id
    directly, must still be told there is no such block."""
    _work, _file, block = propose_web_source(kb)
    r = _mcp([("litkb_record_use", {
        "statement": "tries to quote another workstream's unapproved proposal",
        "kind": "context", "quote": PASSAGE[:80], "block_id": block,
        "gap": f"web-gate-b-{uuid.uuid4().hex[:6]}",
        "gap_question": "can B quote A's proposal?",
        "feeds": "decision litkb-web-source-gate"})], env_at(kb, "B"))[0]
    assert r["ok"] is False and r["refused"] == "unknown-block", r

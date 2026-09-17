"""litkb P8 — the access layer: the MCP server, and the mini-hunt that gate §14 P8 asks for.

What each group establishes:

  the protocol   the server answers a real MCP client over a real session: initialize, list_tools,
                 call_tool. Nine tools, no more — `promote commit` and `approve` are absent, and a
                 test asserts their absence rather than trusting the docstring
  the refusals   a write tool called where there is no `.litkb-workstream` is REFUSED, by code, not
                 by convention (gate kill 2); so is one called with no agent/session labels
  redaction      a secret armed by _session() and planted into a tool result comes back `<KEY>`
                 (gate kill 3; harness rows X1, X2 are what show each half of it firing)
  the mini-hunt  open workstream -> admit a real DOI from a cached registry -> acquire -> record a
                 use with a verified quote -> propose promotion. Marked `litkb_live` as the brief
                 asks, so the ladder never runs it; run it with LITKB_LIVE=1
  the kills      a use whose quote the database could not verify is refused at PREPARE (gate kill 1),
                 and `promote commit` is exercised only against a SCRATCH git repository whose main
                 the test merges itself — never the real one

Run:
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w2 py -3.12 -m pytest qc/test_litkb_p8.py
    (add LITKB_LIVE=1 for the mini-hunt and the promotion kills)
"""
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
PIPELINE = SCRIPTS / "pipeline"
FIX = SCRIPTS / "qc" / "testdata" / "litkb_p8"
pg_only = pytest.mark.requires_litkb_pg
live = pytest.mark.litkb_live

#: the one DOI the mini-hunt admits. It is REAL (Higham & Lin 2011, Linear Algebra and its
#: Applications) and its Crossref record in FIX/registry_cache.json is the recorded response, not a
#: hand-written one — the same record P2's kill set captured. The hunt therefore admits a real work
#: with real registry identity and never opens a socket.
HUNT_DOI = "10.1016/j.laa.2010.04.007"
HUNT_TITLE = "On pth roots of stochastic matrices"
#: what an agent holds at step 2 of the hunt: the DOI and the record it believes goes with it.
#: Admission COMPARES the two — check 1 refuses a registry admission that offers neither a claimed
#: record nor a bound file, because then there is nothing for the registry to confirm. That refusal
#: is the DOI-first rule itself, so the hunt satisfies it rather than working round it.
HUNT_CLAIM = {"doi": HUNT_DOI, "title": HUNT_TITLE, "authors": "Higham and Lin", "year": "2011"}

#: The two database tests after the hunt each need a work of their OWN. `litkb_test` is reset once
#: per pytest session (the shared litkb_pg_base fixture), and admission's check 2 is exactly right
#: to refuse the same DOI twice: one identifier, one work, across the whole knowledge base. So each
#: test admits a different real record from the same recorded cache, rather than the suite weakening
#: the check it depends on.
CLAIMS = {
    "quote_kill": {"doi": "10.4171/jems/179", "year": "2009", "authors": "Averkov and Bianchi",
                   "title": "Confirmation of Matheron's conjecture on the covariogram of a planar "
                            "convex body"},
    "commit": {"doi": "10.4171/JEMS/183", "year": "2009",
               "authors": "Lisca and Ozsvath and Stipsicz and Szabo",
               "title": "Heegard Floer invariants of Legendrian knots in contact three-manifolds"},
}


# ── the in-process MCP client ─────────────────────────────────────────────────────────────

def mcp_roundtrip(calls):
    """Drive the real server over a real MCP session and return [(name, parsed result), ...].

    `calls` is [(tool_name, arguments), ...]; a single client session runs them in order, so a tool
    that depends on an earlier one's state (every write tool does) sees it. The transport is the
    SDK's in-memory pair — the same ClientSession, the same initialize handshake, the same
    call_tool envelope a registered stdio server gets, without a subprocess."""
    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    from litkb.mcp.server import build_server

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
                            out.append((name, json.loads(text)))
                        except ValueError:
                            out.append((name, {"raw": text}))
                tg.cancel_scope.cancel()

    anyio.run(drive)
    return out


def one(name, args):
    return mcp_roundtrip([(name, args)])[0][1]


def tool_names():
    import anyio

    from litkb.mcp.server import build_server

    return sorted(t.name for t in anyio.run(build_server().list_tools))


# ── the protocol ──────────────────────────────────────────────────────────────────────────

EXPECTED_TOOLS = {"litkb_search", "litkb_work", "litkb_candidates", "litkb_ws_open",
                  "litkb_ws_status", "litkb_my_uses", "litkb_admit", "litkb_acquire",
                  "litkb_record_use", "litkb_propose_promotion", "litkb_hunt"}


def test_the_server_offers_exactly_the_expected_tools():
    """Eleven since 2026-09-16: `litkb_my_uses` closed friction item 2 of the operational test — a
    session could not read back one thing it had written — and `litkb_hunt` drives the five steps
    of the hunt protocol from one reference. Asserted as a SET, so adding a tool is a deliberate
    edit here and never a silent widening of the surface."""
    assert set(tool_names()) == EXPECTED_TOOLS


def test_promote_commit_and_approve_are_not_tools():
    """Design §9: neither is exposed to agents. `commit` is Kam's step after his merge; `approve`
    belongs to a SECOND session (§15.13, D-4), and a tool on this server would make it this one.
    Asserted on the surface, because a docstring saying so is not a control."""
    names = tool_names()
    assert not [n for n in names if "commit" in n or "approve" in n], names


def test_a_tool_result_is_json_over_a_real_session():
    res = one("litkb_work", {})
    assert res == {"ok": False, "refused": "no-selector",
                   "message": "litkb_work takes a doi or a key"}


def test_the_server_module_imports_neither_mcp_nor_psycopg():
    """The import-weight contract (design §9): `import litkb.mcp.server` must not pull the SDK or
    the driver, so qc/check.py's compile-and-import sweep stays light and the registration line can
    name the module on a machine that has not installed them yet."""
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; import litkb.mcp.server as s; "
         "print(sorted(m for m in sys.modules if m.split('.')[0] in ('mcp', 'psycopg')))"],
        capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(PIPELINE)))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]", r.stdout


# ── the refusals (gate kill 2) ────────────────────────────────────────────────────────────

WRITE_TOOLS = [
    ("litkb_ws_status", {}),
    ("litkb_candidates", {}),
    ("litkb_my_uses", {}),
    ("litkb_admit", {"doi": HUNT_DOI}),
    ("litkb_acquire", {"doi": HUNT_DOI}),
    ("litkb_record_use", {"statement": "s", "kind": "context", "quote": "q",
                          "block_id": str(uuid.uuid4()), "gap": "g"}),
    ("litkb_propose_promotion", {}),
    # a hunt spends a download and a GPU conversion, so its token check is made BEFORE the
    # subprocess runs, in _hunt(), rather than by the CLI it shells out to
    ("litkb_hunt", {"ref": "https://example.org/nothing.pdf"}),
]


@pytest.mark.parametrize("tool,args", WRITE_TOOLS, ids=[t for t, _ in WRITE_TOOLS])
def test_a_tool_without_a_workstream_token_is_refused(tool, args, tmp_path, monkeypatch):
    """KILL: no `.litkb-workstream` in the worktree -> the call is refused before any connection is
    opened. The token is never a tool PARAMETER (a parameter is written into the transcript), so
    this is the only way a caller can present one, and its absence is the only way it can be
    missing."""
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    res = one(tool, args)
    assert res["refused"] == "no-workstream", res
    assert "litkb_ws_open" in res["message"]


LABELLED_TOOLS = [
    ("litkb_admit", {"doi": HUNT_DOI}),
    ("litkb_acquire", {"doi": HUNT_DOI}),
    ("litkb_record_use", {"statement": "s", "kind": "context", "quote": "q",
                          "block_id": str(uuid.uuid4()), "gap": "g"}),
]


@pytest.mark.parametrize("tool,args", LABELLED_TOOLS, ids=[t for t, _ in LABELLED_TOOLS])
def test_a_write_without_agent_and_session_labels_is_refused(tool, args, tmp_path, monkeypatch):
    """Every write records WHICH agent and WHICH session made it, and the manual-admission sign-off
    compares those labels (§15.13, D-4). A write tool that invented them would make two sessions
    look like one. Rows X4/X5/X6 remove the check at each of the three write tools in turn."""
    _plant_token(tmp_path)
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    monkeypatch.setenv("LITKB_AGENT", "")
    monkeypatch.setenv("LITKB_SESSION", "")
    res = one(tool, args)
    assert res["refused"] == "no-labels", res


@pytest.mark.parametrize("label", ["​​", "﻿", "  ⁠"],
                         ids=["zero_width", "bom", "nbsp_word_joiner"])
def test_a_label_of_invisible_characters_only_is_blank_and_refused(label, tmp_path, monkeypatch):
    """Row X3. `norm_label` removes every Unicode invisible (Zs/Zl/Zp/Cf and whitespace) wherever it
    occurs, so a label made of them is blank and refused — here as it is in the CLI, in
    admit.front and in the database's own comparison. Without it such a label is merely truthy, and
    a second session can be spelled to look like the first."""
    _plant_token(tmp_path)
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    monkeypatch.setenv("LITKB_AGENT", label)
    monkeypatch.setenv("LITKB_SESSION", label)
    res = one("litkb_admit", {"doi": HUNT_DOI})
    assert res["refused"] == "no-labels", res


def test_a_manual_admission_is_refused_and_named_to_the_cli(tmp_path, monkeypatch):
    """No MCP tool admits a work no registry can confirm, and none approves one: the approval must
    come from a second session (§15.13). The refusal has to SAY so, or an agent with no route just
    reaches for a web search — the failure mode §9.1 was written against."""
    _plant_token(tmp_path)
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    monkeypatch.setenv("LITKB_AGENT", "p8")
    monkeypatch.setenv("LITKB_SESSION", "p8-1")
    res = one("litkb_admit", {"title": "A report no registry has"})
    assert res["refused"] == "no-identifier", res
    assert "--manual" in res["message"] and "second session" in res["message"]


def _plant_token(directory, token=None):
    token = token or uuid.uuid4().hex + uuid.uuid4().hex
    (Path(directory) / ".litkb-workstream").write_text(
        json.dumps({"workstream_id": str(uuid.uuid4()), "token": token}), encoding="utf-8")
    return token


# ── redaction (gate kill 3) ───────────────────────────────────────────────────────────────

def test_a_planted_secret_is_redacted_in_a_tool_result(tmp_path, monkeypatch):
    """KILL, in the two halves the harness mutates separately.

    _session() ARMS redaction by registering the workstream token with netutil.add_secret (row X2);
    _out() APPLIES it (row X1). Strip either and the planted token reaches the model verbatim. The
    call below is a real tool call that reaches _session() — the arming is a side effect of the
    ordinary path, not something the test does for it — and the boundary is then checked against
    the same token."""
    from litkb.mcp import server

    token = _plant_token(tmp_path)
    monkeypatch.setenv("LITKB_WORKTREE", str(tmp_path))
    monkeypatch.setenv("LITKB_AGENT", "p8")
    monkeypatch.setenv("LITKB_SESSION", "p8-1")
    # `litkb_record_use` reaches _session() (which arms redaction with the token) and then refuses on
    # `kind`, echoing the value it was given — before any connection is opened. Planting the token
    # AS that value is therefore a real tool result, over the real protocol, carrying the secret.
    res = one("litkb_record_use", {"statement": "s", "kind": token, "quote": "q",
                                   "block_id": str(uuid.uuid4()), "gap": "g"})
    assert res["refused"] == "bad-kind", res
    body = json.dumps(res)
    assert token not in body, "the armed token reached the model through a tool result"
    assert "<KEY>" in body, body
    assert server._out({"echo": token}) == '{\n "echo": "<KEY>"\n}'


def test_the_shape_rules_are_the_secrets_rung_s_own(tmp_path):
    """One definition of "this is a pgpass line" (CLAUDE.md §3.3). netutil loads qc/secrets_check.py
    by path and reuses its two compiled patterns; if the rung's rules are edited, the MCP boundary
    moves with them. Asserted on the pattern TEXT, so a copy that merely looks alike fails."""
    import importlib.util

    from litkb import netutil

    spec = importlib.util.spec_from_file_location("_rung", SCRIPTS / "qc" / "secrets_check.py")
    rung = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rung)
    patterns = [rx.pattern for rx, _anchored in netutil.shape_rules()]
    assert rung.PGPASS_RE.pattern in patterns, patterns
    assert rung.TOKEN_RE.pattern in patterns, patterns
    assert "v" in rung.PGPASS_RE.groupindex and "v" in rung.TOKEN_RE.groupindex, (
        "the rung's patterns must name the VALUE group `v`: that is what the boundary masks")


def test_a_planted_credential_shape_is_masked_in_a_tool_result():
    """KILL for P8 referee F-4, in the shape he broke it in: a pgpass line inside a BLOCK's text,
    with prose before and after it, carried out through a tool result.

    `redact()` could never have caught this — it replaces REGISTERED strings, and no process here
    ever held that password. The value is built at runtime rather than written into this file
    because a pgpass-shaped literal in a tracked test is exactly what qc/secrets_check.py refuses,
    and the pgpass rule cannot carry the allow pragma.

    Row X7 strips the redact_shapes() call in _out()."""
    from litkb.mcp import server

    pw = "Zq7" + "v" * 20
    key = uuid.uuid4().hex + uuid.uuid4().hex
    hit = {"block_id": str(uuid.uuid4()), "work_key": "Rosychuk_2003_bias-correction-two-state",
           "text": ("Notes on the staging database follow.\n"
                    f"localhost:5433:litkb:litkb_writer:{pw}\n"
                    "The pilot plot was measured in June.")}
    body = server._out({"ok": True, "blocks": [hit],
                        "note": f"fetched https://example.org/api/download?md5=abc&key={key}",
                        "driver": f'{{"password": "{pw}", "host": "localhost"}}',
                        "pem": "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
                        "password": pw})
    assert pw not in body, "a pgpass password reached the model through a tool result"
    assert key not in body, "a URL's key= reached the model through a tool result"
    assert "MIIabc" not in body, "a PEM body reached the model through a tool result"
    assert "localhost:5433:litkb:litkb_writer:<KEY>" in body, body
    assert "The pilot plot was measured in June." in body, "the block's own words must survive"
    assert '"password": "<KEY>"' in body, "a value under a credential-named KEY reached the model"


def test_a_work_shaped_result_is_returned_byte_for_byte():
    """The positive control the mask needs, and the reason `key` and a bare 64-hex are NOT rules: a
    file's sha256 IS 64 hex, and in this database `key` is the work key. A shape redactor that ate
    those would make litkb_work useless while looking secure."""
    from litkb.mcp import server

    rec = {"ok": True, "key": "Rosychuk_2003_bias-correction-two-state",
           "work": {"title": "Bias correction of two-state latent Markov process parameter "
                             "estimates under misclassification", "authors": "Rosychuk and Islam",
                    "year": 2003},
           "identifiers": [{"scheme": "doi", "value": "10.1002/sim.1473", "active": True}],
           "files": [{"sha256": "3f" * 32, "path": "Validation/Rosychuk_2003.pdf", "pages": 17}],
           "uses": [{"statement": "supplies the naive-estimator bias", "feeds": ["gap row 18"]}]}
    assert json.loads(server._out(rec)) == rec, "a work record must pass the boundary unchanged"


# ── the read tools' token check (F-1) ─────────────────────────────────────────────────────

@pg_only
def test_a_forged_token_reads_nothing_and_a_real_one_reads_its_own_workstream(hunt_env):
    """KILL for F-1. The referee wrote a `.litkb-workstream` naming the REAL workstream id with 64
    zeros as its token and got `litkb_ws_status` -> ok: true, the whole status. Workstream ids are
    not secret — a tracked report prints one — so the attack needed no secret at all.

    Both directions are asserted in one test, because "refuses everything" would satisfy the kill
    just as well as the fix: the real token must still answer, and litkb_candidates must return its
    own workstream's rows (that leg named a column the schema does not have — `identifiers` for
    `ids` — so it had NEVER returned a row; the P8 gate only ever tested it with no workstream)."""
    wt = hunt_env["wt"]
    opened = one("litkb_ws_open", {"slug": f"p8-token-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the read-tool token check"})
    assert opened["ok"], opened
    real = (wt / ".litkb-workstream").read_text(encoding="utf-8")

    status = one("litkb_ws_status", {})
    assert status["ok"] and status["state"] == "open", status
    cands = one("litkb_candidates", {})
    assert cands["ok"], cands
    assert cands["workstream_id"] == opened["workstream_id"], cands

    mine = one("litkb_my_uses", {})
    assert mine["ok"] and mine["workstream_id"] == opened["workstream_id"], mine

    (wt / ".litkb-workstream").write_text(
        json.dumps({"workstream_id": opened["workstream_id"], "token": "0" * 64}), encoding="utf-8")
    for tool in ("litkb_ws_status", "litkb_candidates", "litkb_my_uses"):
        res = one(tool, {})
        assert res["refused"] == "bad-token", (tool, res)
        for leaked in ("slug", "state", "candidates", "promotions", "admissions", "uses"):
            assert leaked not in res, f"{tool} told a wrong token about {leaked}: {res}"
    (wt / ".litkb-workstream").write_text(real, encoding="utf-8")


@pg_only
def test_the_offer_tool_refuses_a_forged_token_before_it_runs_anything(hunt_env):
    """The hole the referee did not test, and the worst of the three: `promote prepare` takes NO
    token — `litkb.promote_prepare(ws, branch_head, report_path)` is authorised by the PROMOTER
    credential — so `litkb_propose_promotion` presented nothing at all. A `.litkb-workstream` naming
    a published workstream id with any string as its token would have prepared THAT workstream's
    proposals, written its chain report into this worktree, and (one prepared promotion per
    workstream) blocked its owner's own prepare.

    Asserted on the side effects as well as the code, because "refused" is cheap: no `_derived/`
    directory appears, and the workstream has no promotion row."""
    conn, wt = hunt_env["conn"], hunt_env["wt"]
    opened = one("litkb_ws_open", {"slug": f"p8-offer-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the offer tool's token check"})
    ws_id = opened["workstream_id"]
    (wt / ".litkb-workstream").write_text(
        json.dumps({"workstream_id": ws_id, "token": "0" * 64}), encoding="utf-8")
    res = one("litkb_propose_promotion", {})
    assert res["refused"] == "bad-token", res
    assert not (wt / "_derived").exists(), "prepare ran: it wrote a report for a forged token"
    assert conn.execute("SELECT count(*) FROM litkb.promotions WHERE workstream_id = %s",
                        (ws_id,)).fetchone()[0] == 0, "a promotion was prepared for a forged token"


@pg_only
def test_a_write_with_a_forged_token_reaches_the_model_as_bad_token(hunt_env):
    """The database already refused this write; what it did not do was SAY so to the model. The
    refusal arrived as `refused: "error"` with a raw psycopg message and a `CONTEXT: PL/pgSQL
    function _require_ws_token(uuid,text) line 1` (referee §3.2). Same refusal, one code."""
    conn, wt = hunt_env["conn"], hunt_env["wt"]
    opened = one("litkb_ws_open", {"slug": f"p8-wtoken-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the write-path token refusal"})
    seeded = _seed_work_file_block(conn, opened["workstream_id"],
                                   "The pilot plot was measured in June.")
    (wt / ".litkb-workstream").write_text(
        json.dumps({"workstream_id": opened["workstream_id"], "token": "0" * 64}), encoding="utf-8")
    res = one("litkb_record_use", {
        "statement": "a claim made with a forged token", "kind": "context",
        "quote": "measured in June", "block_id": seeded["block_id"],
        "gap": f"p8-forged-{uuid.uuid4().hex[:6]}", "gap_question": "is a forged token named?"})
    assert res["refused"] == "bad-token", res
    assert "CONTEXT" not in json.dumps(res) and "PL/pgSQL" not in json.dumps(res), res


# ── prepare: evidence, feeds, and the report (F-3, F-5, §4.1) ─────────────────────────────

FEEDS_VOCABULARY = ["framework §16.2", "narrative §3", "gated-plan gate 4", "review §4.18.4",
                    "gap row 18", "decision litkb-p0-foundation",
                    "report LITKB_P8_REFEREE_2026-09-15.md#§2"]


@pg_only
@pytest.mark.parametrize("token", FEEDS_VOCABULARY)
def test_every_feeds_token_the_convention_names_is_accepted(token, litkb_pg_base):
    """F-3. docs/LITERATURE_CONVENTION.md names seven doc-qualified forms; 0005 enforced three, so a
    session that followed the convention wrote a use that would not promote and found out at
    prepare. Each form is asserted on its own, and so are the shapes that must still be refused."""
    _psycopg, conn, _ran = litkb_pg_base
    assert conn.execute("SELECT litkb._feeds_token_ok(%s)", (token,)).fetchone()[0], token


@pg_only
@pytest.mark.parametrize("token", ["§16.2", "framework §13.1.1", "gap row", "decision Bad-Slug",
                                   "report bad", "nonsense token", ""])
def test_a_feeds_token_outside_the_vocabulary_is_still_refused(token, litkb_pg_base):
    """The other half of F-3: widening the vocabulary must not turn the validator off. A bare `§N`,
    a framework heading two levels deep (the convention allows one), a slug with capitals and a
    `report` token with no `#§loc` are all still invalid."""
    _psycopg, conn, _ran = litkb_pg_base
    assert not conn.execute("SELECT litkb._feeds_token_ok(%s)", (token,)).fetchone()[0], token


@pg_only
def test_a_use_with_no_verified_evidence_is_held_at_prepare_and_the_report_says_why(hunt_env):
    """KILL for the convention error the referee confirmed by running (§3.6, §4.1): a use with ZERO
    use_evidence rows reached `prepared`, because the check counted rows that were NOT promotable
    and zero rows is zero bad rows. Migration 0019 counts the promotable ones instead.

    The verified control in the same prepare is what makes this a kill rather than a tautology — a
    prepare that held everything would satisfy "the zero-evidence use was held" and prove nothing.
    The promotion report (F-5) is asserted here too: prepare used to record a path and write no
    file, while the skill said it wrote one onto the work branch."""
    from psycopg.types.json import Jsonb

    conn, wt = hunt_env["conn"], hunt_env["wt"]
    opened = one("litkb_ws_open", {"slug": f"p8-evid-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the no-evidence hold"})
    ws_id = opened["workstream_id"]
    token = json.loads((wt / ".litkb-workstream").read_text(encoding="utf-8"))["token"]
    text = "The pilot plot was measured in June."
    seeded = _seed_work_file_block(conn, ws_id, text)

    good = one("litkb_record_use", {
        "statement": "supplies the control: a quote the database can verify", "kind": "context",
        "quote": "measured in June", "block_id": seeded["block_id"],
        "gap": f"p8-evid-good-{uuid.uuid4().hex[:6]}", "gap_question": "does a verified use prepare?",
        "feeds": "; ".join(FEEDS_VOCABULARY)})
    assert good["ok"] and good["quote_verified"] is True, good

    gap = conn.execute(
        "SELECT * FROM litkb.write_proposal('gap', NULL, %s, NULL, %s, %s, %s, %s, %s, %s)",
        (Jsonb({"slug": f"p8-evid-zero-{uuid.uuid4().hex[:6]}"}),
         Jsonb({"question": "does a use with no quote reach prepared?", "gap_state": "open"}),
         None, ws_id, token, "p8", "p8-evidence")).fetchone()
    zero = conn.execute(
        "SELECT * FROM litkb.write_proposal('use', NULL, %s, NULL, %s, %s, %s, %s, %s, %s)",
        (Jsonb({"work_id": seeded["work_id"], "gap_id": str(gap[0])}),
         Jsonb({"statement": "a claim with no quote at all", "kind": "context",
                "status": "proposed", "feeds": [], "rationale": None}),
         None, ws_id, token, "p8", "p8-evidence")).fetchone()

    offered = one("litkb_propose_promotion", {})
    assert offered["ok"] and offered["outcome"] == "prepared", offered
    states = dict(conn.execute(
        "SELECT version_id::text, state FROM litkb.use_versions WHERE version_id = ANY(%s)",
        ([str(zero[1]), good["use_version_id"]],)).fetchall())
    assert states[str(zero[1])] == "proposed", (
        f"a use with no evidence at all reached {states[str(zero[1])]}")
    assert states[good["use_version_id"]] == "prepared", (
        "the verified control was held too — this prepare held everything, so the kill above says "
        "nothing about the evidence")

    held = {h["chain"]: h["why"] for h in offered["held"]}
    assert any("no-verified-evidence" in " ".join(w) for w in held.values()), offered["held"]
    report = Path(offered["report_written"])
    assert report.exists(), offered
    assert report.parent.name == "promotions" and report.parent.parent.name == "_derived", report
    body = report.read_text(encoding="utf-8")
    assert "no-verified-evidence" in body and "## Held" in body and "## Prepared" in body, body
    assert offered["promotion_id"] in body, body


@pg_only
def test_search_finds_a_block_the_extractor_mangled(hunt_env):
    """The referee's Q3, in miniature (§2.4): the block holds `misclassi<FFFD>cation` and
    `overesti- mate`, because that is what the PDF's text layer renders, and it says `NEs` where the
    question says `naive estimators`. Under the old statement — one all-terms match, re-sorted by
    trigram — it was reachable only by a caller who already knew how the extractor had mangled the
    word. The full corpus run is in the P8 report; this is the guard's home."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-search-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the mangled-text search"})
    # A paragraph, not a sentence: the trigram leg compares the WHOLE block with the whole query,
    # so on a one-sentence block a query of similar length is similar enough to be returned by
    # trigram alone — and the test would pass with the any-term leg switched off, proving nothing.
    # At paragraph length trigram similarity falls below the threshold and only the any-term leg
    # can reach this block. (The harness found that: row X14 reported DID NOT FIRE on the short one.)
    mangled = ("In the simulation study reported in Section 5 the two-state latent process was "
               "generated with a range of transition intensities, sample sizes and observation "
               "schedules, and the parameter estimates were compared with their true values under "
               "each design. The NEs overestimate the transition probabilities and this overesti- "
               "mate increases as the misclassi�cation probabilities increase. Tables 3 and 4 "
               "give the empirical bias, the standard error and the coverage of the nominal ninety "
               "five per cent intervals for every combination considered, together with the number "
               "of replications in which the maximisation failed to converge.")
    seeded = _seed_work_file_block(conn, opened["workstream_id"], mangled)
    res = one("litkb_search", {"query": "naive estimators overestimate the transition probabilities "
                                        "misclassification", "limit": 5, "scope": "blocks"})
    assert res["ok"], res
    assert seeded["block_id"] in [b["block_id"] for b in res["blocks"]], res
    assert res["legs"] == ["lexical (all terms)", "lexical (any term)", "trigram"], res


@pg_only
def test_search_reads_the_text_through_the_normaliser(hunt_env):
    """The normaliser's own kill, separate from the any-term leg's, because the two fix different
    halves of §2.4 and a test that passes on either proves neither. A word the PDF broke across a
    line — `overesti- mate` — tokenises as two words, so a query for the whole word matches no
    lexeme in it and is too short to reach the trigram threshold. Normalised on both sides, it is
    one word again."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-norm-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the search normaliser"})
    seeded = _seed_work_file_block(
        conn, opened["workstream_id"],
        "The naive estimator's overesti- mate grows with the misclassi�cation rate.")
    res = one("litkb_search", {"query": "overestimate", "limit": 5, "scope": "blocks"})
    assert seeded["block_id"] in [b["block_id"] for b in res.get("blocks", [])], res


@pg_only
def test_a_running_head_is_not_a_passage_and_is_out_of_search_by_default(hunt_env):
    """The final referee's §7, in miniature. A running head is the SAME 42 characters on every
    page of a paper, so a topical query matches it once per page: the referee's cold question
    returned `CONSTRAINED MONTE CARLO MAXIMUM LIKELIHOOD` five times in a ten-row list and the
    answering body passage was not in the top ten at all. The same shape is planted here — one
    body paragraph against six copies of a running head and a bibliography entry that names the
    same words — and the test asserts both halves: the furniture is gone by default, and
    `kinds="all"` still returns it, because a filter that cannot be turned off is a loss of
    recall rather than a ranking fix."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-furniture-{uuid.uuid4().hex[:6]}",
                                   "purpose": "furniture out of search"})
    head = "CONSTRAINED MONTE CARLO MAXIMUM LIKELIHOOD"
    body = ("We derive the constrained Monte Carlo maximum likelihood estimate for a dependent "
            "lattice model whose normalising constant cannot be evaluated, and give conditions "
            "under which the estimate converges as the simulation sample size grows.")
    seeded = _seed_work_file_block(
        conn, opened["workstream_id"], body,
        extra=[(p, "page_header", head) for p in range(2, 8)]
        + [(9, "reference", "Geyer CJ, Thompson EA. 1992. Constrained Monte Carlo maximum "
                            "likelihood for dependent data. J R Stat Soc B 54:657-699.")])
    q = {"query": "constrained Monte Carlo maximum likelihood", "limit": 10, "scope": "blocks"}

    default = one("litkb_search", q)
    assert default["ok"], default
    kinds = [b["block_type"] for b in default["blocks"]]
    assert "page_header" not in kinds and "reference" not in kinds, default
    assert seeded["block_id"] in [b["block_id"] for b in default["blocks"]], default
    assert "NOT searched by default" in default["kinds"], default

    every = one("litkb_search", dict(q, kinds="all"))
    assert "page_header" in [b["block_type"] for b in every["blocks"]], (
        "the planted running heads are unreachable even on request — the filter is not a filter, "
        "it is a deletion")

    named = one("litkb_search", dict(q, kinds="reference"))
    assert [b["block_type"] for b in named["blocks"]] == ["reference"], named

    bad = one("litkb_search", dict(q, kinds="page-header"))
    assert bad.get("refused") == "bad-kinds", bad


@pg_only
def test_a_quote_from_another_work_is_refused(hunt_env):
    """The property the referee called the strongest single one in the file, and the one with no
    row until now (§3.3, §6.1): a use's work is DERIVED from the block, so a quote from B cannot
    evidence a claim about A. Naming the other work is refused `work-mismatch`; naming NOTHING
    records the use against the block's own work, which is the half that makes the refusal honest
    rather than a formality."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-mismatch-{uuid.uuid4().hex[:6]}",
                                   "purpose": "evidence from another work"})
    ws_id = opened["workstream_id"]
    a = _seed_work_file_block(conn, ws_id, "Work A says the pilot plot was measured in June.")
    b = _seed_work_file_block(conn, ws_id, "Work B says the canopy closed in August.")
    key_a = conn.execute("SELECT key FROM litkb.works WHERE id = %s", (a["work_id"],)).fetchone()[0]
    key_b = conn.execute("SELECT key FROM litkb.works WHERE id = %s", (b["work_id"],)).fetchone()[0]

    res = one("litkb_record_use", {
        "statement": "claims A on B's words", "kind": "context", "quote": "canopy closed in August",
        "block_id": b["block_id"], "work_key": key_a,
        "gap": f"p8-mismatch-{uuid.uuid4().hex[:6]}", "gap_question": "whose words are these?"})
    assert res["refused"] == "work-mismatch", res
    assert key_b in res["message"] and key_a in res["message"], res

    named_nothing = one("litkb_record_use", {
        "statement": "records against the block's own work", "kind": "context",
        "quote": "canopy closed in August", "block_id": b["block_id"],
        "gap": f"p8-mismatch2-{uuid.uuid4().hex[:6]}", "gap_question": "whose words are these?"})
    assert named_nothing["ok"] and named_nothing["work_key"] == key_b, named_nothing


# ── litkb_work: the four states (operational referee R-1, R-2, R-3) ───────────────────────

@pg_only
def test_litkb_work_answers_each_of_the_four_states_on_a_work_the_database_holds(hunt_env):
    """THE test that would have caught R-1, and the one the suite had never made.

    `litkb_work` named two columns the schema does not have — `container` for `venue` at line 421
    and `v.path` for `v.rel_path` at 426/428 — so it crashed on every work the database HELD and
    answered only on the miss path, which is why it read as alive. The whole P8 suite called it
    once, as `one("litkb_work", {})` asserting `no-selector`, and the one test whose name promised
    otherwise built a record in Python and handed it to `_out()` without opening a connection
    (LITKB_OPERATIONAL_REFEREE_2026-09-16.md §5). No test had ever put a real work through it.

    The four states are asserted together because they are a LADDER and each rung is only
    meaningful against the next: "absent" and "held" and "bound-unextracted" are three different
    answers to "litkb_search found nothing", they need three different next moves, and the
    operational test had to reach for `psql` twice to tell them apart — which a session without
    database access cannot do at all."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-states-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the four states of litkb_work"})
    ws_id = opened["workstream_id"]

    absent = one("litkb_work", {"key": f"Nobody_1999_no-such-work-{uuid.uuid4().hex[:8]}"})
    assert absent["ok"] and absent["found"] is False, absent
    assert absent["state"] == "absent", absent

    held = _seed_work_state(conn, ws_id, "held")
    res = one("litkb_work", {"key": held["key"]})
    assert res["ok"] and res["found"] is True, res
    assert res["state"] == "held", res
    assert res["files"] == [] and res["file_stems"] == [] and res["blocks"] == 0, res
    assert res["work"]["venue"] is not None, "the venue column is the one `container` was hiding"

    bound = _seed_work_state(conn, ws_id, "bound-unextracted")
    res = one("litkb_work", {"key": bound["key"]})
    assert res["state"] == "bound-unextracted", res
    assert len(res["files"]) == 1 and res["files"][0]["current_run_id"] is None, res
    assert res["file_stems"] == ["seeded"], res
    assert res["blocks"] == 0, res

    extracted = _seed_work_state(conn, ws_id, "extracted",
                                 text="The pilot plot was measured in June.")
    res = one("litkb_work", {"key": extracted["key"]})
    assert res["state"] == "extracted", res
    assert res["files"][0]["current_run_id"] == extracted["run_id"], res
    assert res["blocks"] == 1, res
    assert res["files"][0]["path"] == "Validation/seeded.pdf", res
    assert res["use_count"] == 0, res
    assert res["what_next"] and "litkb_search" in res["what_next"], res


@pg_only
def test_litkb_work_finds_the_same_work_by_doi_and_reports_its_uses(hunt_env):
    """The DOI selector, and the `uses`/`use_count` legs — both reached the two broken statements
    too, so neither had ever run against a work. A use recorded through the tool is `proposed`, so
    it is NOT in main's view and `use_count` is 0 here: that is the honest answer and the reason
    `litkb_my_uses` exists."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-workdoi-{uuid.uuid4().hex[:6]}",
                                   "purpose": "litkb_work by doi"})
    seeded = _seed_work_state(conn, opened["workstream_id"], "extracted",
                             text="The pilot plot was measured in June.")
    doi = f"10.5555/p8-{uuid.uuid4().hex[:10]}"
    conn.execute("SELECT * FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, "
                 "NULL, %s, 'p8-seed', 'p8-seed')",
                 (_jsonb({"scheme": "doi"}),
                  _jsonb({"work_id": seeded["work_id"], "value": doi, "verified_by": "manual",
                          "status": "active"}),
                  opened["workstream_id"]))
    res = one("litkb_work", {"doi": f"https://doi.org/{doi.upper()}"})
    assert res["ok"] and res["found"] is True, res
    assert res["key"] == seeded["key"], res
    assert [i["value"] for i in res["identifiers"]] == [doi], res
    assert res["state"] == "extracted" and res["use_count"] == 0, res


def _jsonb(obj):
    from psycopg.types.json import Jsonb
    return Jsonb(obj)


def _seed_work_state(conn, ws_id, state, text=None):
    """A work seeded to exactly one rung of the `litkb_work` ladder.

    `held` stops after the work, `bound-unextracted` binds a file and never sets a current run,
    `extracted` adds the run and one block. Written as FACTS through `_write_version`, the same way
    `_seed_work_file_block` does and for the same reason (admission is one work per identifier
    across the whole knowledge base, and the recorded registry responses are three)."""
    key = f"Seeded_2026_p8-{uuid.uuid4().hex[:8]}"
    work_id, _v = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, "
        "NULL, %s, 'p8-seed', 'p8-seed')",
        (_jsonb({"key": key}),
         _jsonb({"type": "article", "title": "A seeded work", "authors": [],
                 "venue": "Journal of Seeded Works"}), ws_id)).fetchone()
    out = {"key": key, "work_id": str(work_id), "file_id": None, "run_id": None, "block_id": None}
    if state == "held":
        return out
    file_id, _fv = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, "
        "NULL, %s, 'p8-seed', 'p8-seed')",
        (_jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         _jsonb({"work_id": str(work_id), "status": "active", "rel_path": "Validation/seeded.pdf",
                 "bytes": 1024, "pages": 1}), ws_id)).fetchone()
    out["file_id"] = str(file_id)
    if state == "bound-unextracted":
        return out
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'p8-seed', '0', %s, 'v0', 'local', "
        "'ok') RETURNING id", (file_id, uuid.uuid4().hex)).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    block_id = conn.execute(
        "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
        "VALUES (%s, %s, 1, 'paragraph', %s) RETURNING id",
        (file_id, run_id, text or "A seeded block.")).fetchone()[0]
    out["run_id"], out["block_id"] = str(run_id), str(block_id)
    return out


# ── litkb_my_uses, and the two record_use gates (R-5, R-6) ────────────────────────────────

@pg_only
def test_a_session_can_read_back_the_uses_it_recorded(hunt_env):
    """Friction item 2 of the operational test: recording a use and reading it back were different
    systems. `litkb_ws_status` returned `{"gap": 6, "use": 6}` — counts, no statements, no quotes,
    no work keys — and `litkb_work` reads `litkb.main_uses`, which holds NONE of them until Kam
    merges and `promote commit` runs. The only place a session's own work was legible was the
    promotion report file, written at the very end.

    The quote status is the point: an UNVERIFIED quote is stored and refused at prepare, and before
    this tool nothing showed a session which of its uses were in that state."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-myuses-{uuid.uuid4().hex[:6]}",
                                   "purpose": "reading back my own uses"})
    seeded = _seed_work_state(conn, opened["workstream_id"], "extracted",
                              text="The pilot plot was measured in June.")
    empty = one("litkb_my_uses", {})
    assert empty["ok"] and empty["uses"] == [], empty

    gap = f"p8-myuses-{uuid.uuid4().hex[:6]}"
    used = one("litkb_record_use", {
        "statement": "supplies the measurement date of the pilot plot", "kind": "empirical evidence",
        "quote": "measured in June", "block_id": seeded["block_id"], "gap": gap,
        "gap_question": "when was the pilot plot measured?", "feeds": "gap row 4; narrative §3"})
    assert used["ok"] and used["quote_verified"] is True, used

    mine = one("litkb_my_uses", {})
    assert mine["ok"] and len(mine["uses"]) == 1, mine
    u = mine["uses"][0]
    assert u["use_version_id"] == used["use_version_id"], u
    assert u["work_key"] == seeded["key"] and u["gap"] == gap, u
    assert u["statement"] == "supplies the measurement date of the pilot plot", u
    assert u["feeds"] == ["gap row 4", "narrative §3"], u
    assert u["state"] == "proposed" and u["verified_rows"] == 1, u
    assert u["quote_status"].startswith("verified"), u
    assert mine["promotable"] == 1 and mine["gaps"] == 1, mine
    # and the tool that reads MAIN still cannot see it — which is the honest answer, not a bug
    assert one("litkb_work", {"key": seeded["key"]})["use_count"] == 0


@pg_only
def test_my_uses_names_an_unverified_quote_as_unverified(hunt_env):
    """The state a session most needs to see and could not: a use whose quote the database could
    NOT find at the offsets stored. `promote prepare` refuses its chain, and before this tool the
    first sign of it was the promotion report at the end of the session.

    `char_start`/`char_end` are how the P8 kill reaches this state deliberately (server docstring);
    that route is what makes the unverified case testable at all."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-unver-{uuid.uuid4().hex[:6]}",
                                   "purpose": "an unverified quote, read back"})
    seeded = _seed_work_state(conn, opened["workstream_id"], "extracted",
                              text="The pilot plot was measured in June.")
    bad = one("litkb_record_use", {
        "statement": "claims a quote the database cannot verify", "kind": "context",
        "quote": "measured in June", "block_id": seeded["block_id"],
        "gap": f"p8-unver-{uuid.uuid4().hex[:6]}", "gap_question": "does an unverified quote show?",
        "char_start": 0, "char_end": 5})
    assert bad["quote_verified"] is False, bad
    mine = one("litkb_my_uses", {})
    u = next(x for x in mine["uses"] if x["use_version_id"] == bad["use_version_id"])
    assert u["evidence_rows"] == 1 and u["verified_rows"] == 0, u
    assert u["quote_status"].startswith("UNVERIFIED"), u
    assert mine["promotable"] == 0, mine


@pg_only
@pytest.mark.parametrize("statement", ["", "   ", "​​﻿"],
                         ids=["empty", "spaces", "invisibles"])
def test_a_use_with_a_blank_statement_is_refused_and_nothing_is_written(statement, hunt_env):
    """R-5/R-6. The statement was completely ungated: the database's own CHECK is
    `statement <> ''`, which a single space satisfies, so a use could carry a blank claim beside a
    perfectly verified quote and promote clean. A statement of zero-width joiners is blank in
    exactly the way a LABEL of them is (row X3), so the same normaliser decides both.

    Asserted on the side effect as well as the code: refusing and then writing would satisfy
    `refused == "bad-statement"` and prove nothing."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-blank-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the statement gate"})
    seeded = _seed_work_state(conn, opened["workstream_id"], "extracted",
                              text="The pilot plot was measured in June.")
    gap = f"p8-blank-{uuid.uuid4().hex[:6]}"
    res = one("litkb_record_use", {
        "statement": statement, "kind": "context", "quote": "measured in June",
        "block_id": seeded["block_id"], "gap": gap, "gap_question": "is a blank claim refused?"})
    assert res["refused"] == "bad-statement", res
    assert one("litkb_my_uses", {})["uses"] == [], "a refused use was written anyway"
    assert conn.execute("SELECT count(*) FROM litkb.gaps WHERE slug = %s",
                        (gap,)).fetchone()[0] == 0, "the refused call opened its gap"


@pg_only
def test_a_statement_longer_than_the_cap_is_refused_and_one_at_the_cap_is_not(hunt_env):
    """The cap is a MEASUREMENT, not a preference: the longest of the 391 statements in live
    `litkb` on 2026-09-16 is 798 characters, so 2000 invalidates nothing that exists. Both sides
    are asserted, because a gate that refuses everything would pass the first half alone."""
    from litkb.mcp import server

    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-cap-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the statement cap"})
    seeded = _seed_work_state(conn, opened["workstream_id"], "extracted",
                              text="The pilot plot was measured in June.")
    over = one("litkb_record_use", {
        "statement": "x" * (server.STATEMENT_MAX + 1), "kind": "context",
        "quote": "measured in June", "block_id": seeded["block_id"],
        "gap": f"p8-cap-{uuid.uuid4().hex[:6]}", "gap_question": "is an essay refused?"})
    assert over["refused"] == "bad-statement" and over["cap"] == server.STATEMENT_MAX, over
    at = one("litkb_record_use", {
        "statement": "y" * server.STATEMENT_MAX, "kind": "context", "quote": "measured in June",
        "block_id": seeded["block_id"], "gap": f"p8-cap2-{uuid.uuid4().hex[:6]}",
        "gap_question": "is a statement at the cap accepted?"})
    assert at["ok"] and at["quote_verified"] is True, at
    assert server.STATEMENT_MAX > 798, "the cap must sit above the longest statement measured"


@pg_only
@pytest.mark.parametrize("bad", ["§16.2", "framework §13.1.1", "gap row", "nonsense token",
                                 "decision Bad-Slug"],
                         ids=["bare_section", "too_deep", "no_number", "nonsense", "capitals"])
def test_a_feeds_token_outside_the_vocabulary_is_refused_at_record_use(bad, hunt_env):
    """R-5's structural half. `feeds` was stored unvalidated and first checked at `promote prepare`,
    which is a whole session later — so a use that followed no vocabulary at all recorded clean and
    the author found out at the end, if at all. The check calls the DATABASE's validator
    (`litkb._feeds_token_ok`, migration 0021), not a second regex here: two copies of this rule
    already cost a migration to reconcile.

    The good token in the same call is what makes this a refusal of the BAD one rather than of the
    call: a validator that refused everything would pass this test without it."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-feeds-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the feeds gate at record_use"})
    seeded = _seed_work_state(conn, opened["workstream_id"], "extracted",
                              text="The pilot plot was measured in June.")
    gap = f"p8-feeds-{uuid.uuid4().hex[:6]}"
    res = one("litkb_record_use", {
        "statement": "supplies a claim with one bad feeds token", "kind": "context",
        "quote": "measured in June", "block_id": seeded["block_id"], "gap": gap,
        "gap_question": "is an unknown feeds token refused?", "feeds": f"gap row 4; {bad}"})
    assert res["refused"] == "bad-feeds", res
    assert res["bad_feeds"] == [bad], res
    assert one("litkb_my_uses", {})["uses"] == [], "a use with a bad feeds token was written"
    assert conn.execute("SELECT count(*) FROM litkb.gaps WHERE slug = %s",
                        (gap,)).fetchone()[0] == 0, "the refused call opened its gap"


@pg_only
def test_all_seven_feeds_forms_pass_the_gate_at_record_use(hunt_env):
    """The other half: widening is not the same as turning the check off. Every one of the
    convention's seven doc-qualified forms goes through `litkb_record_use` in one call and the use
    is written."""
    conn = hunt_env["conn"]
    opened = one("litkb_ws_open", {"slug": f"p8-feeds7-{uuid.uuid4().hex[:6]}",
                                   "purpose": "the seven forms through record_use"})
    seeded = _seed_work_state(conn, opened["workstream_id"], "extracted",
                              text="The pilot plot was measured in June.")
    res = one("litkb_record_use", {
        "statement": "supplies a claim carrying every feeds form the convention names",
        "kind": "context", "quote": "measured in June", "block_id": seeded["block_id"],
        "gap": f"p8-feeds7-{uuid.uuid4().hex[:6]}", "gap_question": "do all seven forms pass?",
        "feeds": "; ".join(FEEDS_VOCABULARY)})
    assert res["ok"] and res["quote_verified"] is True, res
    assert one("litkb_my_uses", {})["uses"][0]["feeds"] == FEEDS_VOCABULARY


def _seed_work_file_block(conn, ws_id, text, block_type="paragraph", extra=()):
    """A work, an active file and one block of its current run, written as FACTS.

    Not through litkb_admit: admission is one work per identifier across the whole knowledge base
    (check 2, rightly), the recorded registry responses are three, and the live tests already spend
    them. A fact-written work needs no registry and cannot collide, and what these tests are about
    is the access layer downstream of admission. `_write_version` is the same function the P1 suite
    seeds with."""
    from psycopg.types.json import Jsonb

    work_id, _v = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, "
        "NULL, %s, 'p8-seed', 'p8-seed')",
        (Jsonb({"key": f"Seeded_2026_p8-{uuid.uuid4().hex[:8]}"}),
         Jsonb({"type": "article", "title": "A seeded work", "authors": []}), ws_id)).fetchone()
    file_id, _fv = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, "
        "NULL, %s, 'p8-seed', 'p8-seed')",
        (Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         Jsonb({"work_id": str(work_id), "status": "active", "rel_path": "Validation/seeded.pdf",
                "bytes": 1024, "pages": 1}), ws_id)).fetchone()
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'p8-seed', '0', %s, 'v0', 'local', "
        "'ok') RETURNING id", (file_id, uuid.uuid4().hex)).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run_id))
    block_id = conn.execute(
        "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
        "VALUES (%s, %s, 1, %s, %s) RETURNING id",
        (file_id, run_id, block_type, text)).fetchone()[0]
    # `extra` seeds further blocks of the same run as (page, type, text) — what a search's
    # block-type filter needs in order to be tested against a real competing row rather than
    # against its own SQL.
    others = []
    for page, kind, body in extra:
        others.append(str(conn.execute(
            "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (file_id, run_id, page, kind, body)).fetchone()[0]))
    return {"work_id": str(work_id), "file_id": str(file_id), "run_id": str(run_id),
            "block_id": str(block_id), "extra_ids": others}


# ── the mini-hunt (gate §14 P8) ───────────────────────────────────────────────────────────

@pytest.fixture
def hunt_env(tmp_path, monkeypatch, litkb_pg_base):
    """A worktree, a literature root and a throwaway database, all under tmp_path.

    The server is pointed at the TEST database through LITKB_DB and at the `litkb_test` login
    through LITKB_READER_ROLE / LITKB_WRITER_ROLE: `litkb_test` is a member of reader, writer and
    promoter WITH INHERIT FALSE, which is how the P1 suite already exercises every role without a
    second set of credentials. Nothing here can reach `litkb` — connect.is_test_db() keys on the
    `litkb_test` prefix and migrate.reset() refuses anything else."""
    from litkb.db import connect as c

    psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "base"],
                   check=True, env=_git_env())
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt),
                 "LITKB_READER_ROLE": "litkb_test", "LITKB_WRITER_ROLE": "litkb_test",
                 "LITKB_AGENT": "p8-hunt", "LITKB_SESSION": f"p8-{uuid.uuid4().hex[:8]}",
                 "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_REGISTRY_CACHE": str(FIX / "registry_cache.json")}.items():
        monkeypatch.setenv(k, v)
    return dict(conn=conn, root=root, wt=wt, tmp=tmp_path)


def _git_env():
    return dict(os.environ, GIT_AUTHOR_NAME="p8", GIT_AUTHOR_EMAIL="p8@local",
                GIT_COMMITTER_NAME="p8", GIT_COMMITTER_EMAIL="p8@local")


def _paper_pdf(title, author):
    """P2's one-page test PDF builder, reused rather than copied — the binding check reads the
    first page, and two builders would drift into two different ideas of what a page looks like.

    Loaded by file path through importlib, NOT by putting qc/ on sys.path: that ledger is closed
    (`qc/test_status_discovery.py::test_path_insert_ledger`) and the editable install is the rule.
    A sibling test module is not import surface, so this is the way to reach one."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_litkb_p2_pdf", SCRIPTS / "qc" / "test_litkb_p2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.paper_pdf(title, author)


@pg_only
@live
def test_the_mini_hunt_runs_end_to_end_through_the_mcp_tools(hunt_env):
    """THE P8 GATE. One MCP session, five steps, each one a tool call:

        litkb_ws_open -> litkb_admit -> litkb_acquire -> litkb_record_use -> litkb_propose_promotion

    The extraction step the design's gate names is stood in for by a seeded run and block (the test
    inserts them directly): P5 has not run against this throwaway database, and what P8 is gating is
    the ACCESS layer, not the extractor. That substitution is stated in the report as a limitation,
    not hidden here."""
    conn, root, wt = hunt_env["conn"], hunt_env["root"], hunt_env["wt"]

    opened = one("litkb_ws_open", {"slug": "p8-mini-hunt", "purpose": "the P8 access gate"})
    assert opened["ok"], opened
    assert (wt / ".litkb-workstream").exists()
    assert "token" not in json.dumps(opened).lower() or "never printed" in json.dumps(opened)

    admitted = one("litkb_admit", HUNT_CLAIM)
    assert admitted["ok"], admitted
    key = conn.execute("SELECT key FROM litkb.works WHERE id = %s",
                       (admitted["work_id"],)).fetchone()[0]

    pdf = root / "Validation" / f"{key}.pdf"
    pdf.write_bytes(_paper_pdf(HUNT_TITLE, "N. Higham"))
    acquired = one("litkb_acquire", {"key": key, "from_file": str(pdf)})
    attempts = conn.execute("SELECT route, status FROM litkb.acquisition_attempts "
                            "WHERE work_id = %s", (admitted["work_id"],)).fetchall()
    assert attempts, "an acquisition attempt is recorded whether or not it succeeds"
    assert acquired["outcome"] in ("bound", "in-place", "ok", "already-held"), (acquired, attempts)

    text = "The pth root of a stochastic matrix need not be stochastic."
    block_id = _seed_block(conn, admitted["work_id"], text)

    used = one("litkb_record_use", {
        "statement": "supplies the non-closure of stochasticity under pth roots",
        "kind": "theorem", "quote": text[4:40], "block_id": str(block_id),
        "gap": "p8-gate-question", "gap_question": "does the access layer carry a verified quote?",
        "feeds": "decision litkb-p0-foundation"})
    assert used["ok"] and used["quote_verified"] is True, used

    offered = one("litkb_propose_promotion", {})
    assert offered["ok"], offered
    assert offered["outcome"] == "prepared", offered
    state = conn.execute("SELECT state FROM litkb.promotions WHERE id = %s",
                         (offered["promotion_id"],)).fetchone()[0]
    assert state == "prepared", state


def _seed_block(conn, work_id, text):
    """One extraction run and one block, current for the work's active file. Stands in for P5."""
    file_id = conn.execute("SELECT id FROM litkb.files f JOIN litkb.main_files v "
                           "ON v.version_id = f.current_version_id WHERE v.work_id = %s "
                           "AND v.status = 'active' LIMIT 1", (work_id,)).fetchone()
    assert file_id, "the hunt's acquire step bound no active file"
    run_id = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'p8-seed', '0', %s, 'v0', 'local', "
        "'ok') RETURNING id", (file_id[0], uuid.uuid4().hex)).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id[0], run_id))
    return conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
                        "VALUES (%s, %s, 1, 'paragraph', %s) RETURNING id",
                        (file_id[0], run_id, text)).fetchone()[0]


@pg_only
@live
def test_kill_an_unverifiable_quote_is_refused_at_prepare(hunt_env):
    """GATE KILL 1. The server locates a quote in the block and refuses one that is not there
    (`quote-not-in-block`), so an honest caller cannot record an unverifiable use at all. A caller
    that names offsets ITSELF gets past that — and the database, which recomputes quote_verified in
    a trigger the writer role cannot name, stores false; `promote prepare` then refuses the chain.

    Both halves are asserted, because only the second is the design's kill: the first is ergonomics
    and could be argued away, the second is the control."""
    conn = hunt_env["conn"]
    assert one("litkb_ws_open", {"slug": "p8-quote-kill", "purpose": "the P8 quote kill"})["ok"]
    admitted = one("litkb_admit", CLAIMS["quote_kill"])
    assert admitted["ok"], admitted
    key = conn.execute("SELECT key FROM litkb.works WHERE id = %s",
                       (admitted["work_id"],)).fetchone()[0]
    pdf = hunt_env["root"] / "Validation" / f"{key}.pdf"
    pdf.write_bytes(_paper_pdf(CLAIMS["quote_kill"]["title"], "G. Averkov"))
    one("litkb_acquire", {"key": key, "from_file": str(pdf)})
    text = "The pth root of a stochastic matrix need not be stochastic."
    block_id = _seed_block(conn, admitted["work_id"], text)

    args = {"statement": "claims something the paper does not say", "kind": "context",
            "quote": "a sentence that is nowhere in this block", "block_id": str(block_id),
            "gap": "p8-quote-kill", "gap_question": "is an unverifiable quote refused?"}
    refused = one("litkb_record_use", args)
    assert refused["refused"] == "quote-not-in-block", refused

    forced = one("litkb_record_use", args | {"char_start": 0, "char_end": 20})
    assert forced["quote_verified"] is False, forced
    assert "promote prepare will refuse" in forced["note"]

    # the POSITIVE CONTROL, in the same workstream and the same prepare. Without it, "the chain was
    # not prepared" would also be satisfied by a prepare that silently prepares nothing, and the
    # kill would prove nothing about the quote.
    good = one("litkb_record_use", {
        "statement": "supplies the control: a quote the database can verify", "kind": "context",
        "quote": text[4:40], "block_id": str(block_id), "gap": "p8-quote-kill"})
    assert good["quote_verified"] is True, good

    offered = one("litkb_propose_promotion", {})
    assert offered["ok"] and offered["outcome"] == "prepared", offered
    states = dict(conn.execute(
        "SELECT version_id::text, state FROM litkb.use_versions WHERE version_id = ANY(%s)",
        ([forced["use_version_id"], good["use_version_id"]],)).fetchall())
    # prepare does not fail the whole offer — it HOLDS the offending chain and prepares the rest,
    # which is the design's "all or nothing, per chain" (§5). The kill is that THIS chain is the
    # one held.
    assert states[forced["use_version_id"]] == "proposed", (
        f"an unverified quote reached {states[forced['use_version_id']]}")
    assert states[good["use_version_id"]] == "prepared", (
        "the control chain was not prepared either — this prepare held everything, so the kill "
        "above says nothing about the quote")


@pg_only
@live
def test_promote_commit_runs_only_against_a_scratch_repository(hunt_env):
    """`promote commit` is a CLI command, never a tool. It is exercised here against a SCRATCH git
    repository whose main this test merges itself — the gate's own words — with --no-fetch, so no
    remote is contacted and the real repository's main is never named, never fetched, never moved."""
    conn, wt = hunt_env["conn"], hunt_env["wt"]
    assert one("litkb_ws_open", {"slug": "p8-commit", "purpose": "the scratch-repo commit"})["ok"]
    admitted = one("litkb_admit", CLAIMS["commit"])
    assert admitted["ok"], admitted
    key = conn.execute("SELECT key FROM litkb.works WHERE id = %s",
                       (admitted["work_id"],)).fetchone()[0]
    pdf = hunt_env["root"] / "Validation" / f"{key}.pdf"
    pdf.write_bytes(_paper_pdf(CLAIMS["commit"]["title"], "P. Lisca"))
    one("litkb_acquire", {"key": key, "from_file": str(pdf)})
    text = "The pth root of a stochastic matrix need not be stochastic."
    block_id = _seed_block(conn, admitted["work_id"], text)
    assert one("litkb_record_use", {
        "statement": "supplies the scratch-repo commit's one use", "kind": "theorem",
        "quote": text[4:40], "block_id": str(block_id), "gap": "p8-commit-question",
        "gap_question": "does commit run against a scratch main?"})["quote_verified"] is True

    # the scratch repository: a work branch, and a main that this test merges
    g = _git_env()
    subprocess.run(["git", "-C", str(wt), "checkout", "-q", "-b", "work/p8"], check=True, env=g)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "work"],
                   check=True, env=g)
    offered = one("litkb_propose_promotion", {})
    assert offered["ok"] and offered["outcome"] == "prepared", offered
    head = offered["branch_head"]

    def commit(sha):
        return subprocess.run(
            [sys.executable, "-m", "litkb", "--db", os.environ["LITKB_DB"], "--dir", str(wt),
             "promote", "commit", "--promotion-id", offered["promotion_id"],
             "--merge-commit", sha, "--repo", str(wt), "--no-fetch"],
            capture_output=True, text=True, cwd=str(wt),
            env=dict(g, PYTHONPATH=str(PIPELINE)))

    # KILL (P1's, re-shown through the CLI the tool would call): a commit not reachable from main
    assert commit(head).returncode != 0, "a merge commit not on main was accepted"

    subprocess.run(["git", "-C", str(wt), "checkout", "-q", "master"], env=g,
                   check=subprocess.run(["git", "-C", str(wt), "rev-parse", "--verify", "-q",
                                         "master"], capture_output=True).returncode == 0)
    subprocess.run(["git", "-C", str(wt), "branch", "-f", "main", "work/p8"], check=True, env=g)
    merge = subprocess.run(["git", "-C", str(wt), "rev-parse", "main"], capture_output=True,
                           text=True, check=True).stdout.strip()
    r = commit(merge)
    assert r.returncode == 0, r.stdout + r.stderr
    assert conn.execute("SELECT state FROM litkb.promotions WHERE id = %s",
                        (offered["promotion_id"],)).fetchone()[0] == "committed"


# ── the staged hook ───────────────────────────────────────────────────────────────────────

HOOK = SCRIPTS.parent / ".claude" / "hooks" / "litkb_guard.py"


def _hook(payload, cwd):
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=str(cwd))


@pytest.mark.parametrize("payload", [
    {"tool_name": "mcp__paper-search-mcp__download_scihub", "tool_input": {"doi": "10.1/x"}},
    {"tool_name": "Read", "tool_input": {"file_path": r"D:\edmonds-pipeline\Literture\ASPP\x.pdf"}},
    {"tool_name": "Bash", "tool_input": {"command": "py -3.12 aa_fetch.py --doi 10.1/x"}},
])
def test_the_staged_hook_warns_outside_a_workstream(payload, tmp_path):
    """The hook's own kill, in the form it can take BEFORE installation (design §9.1: the hooks come
    after the gate). With no `.litkb-workstream` in the working directory the hook emits
    additionalContext naming the skill; the tool still runs, because until P8's gate is accepted a
    blocking hook would leave agents no route to literature at all."""
    r = _hook(payload | {"hook_event_name": "PreToolUse", "cwd": str(tmp_path)}, tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "literature" in ctx and "litkb" in ctx
    assert "permissionDecision" not in out["hookSpecificOutput"], "the staged hook must not block"


@pytest.mark.parametrize("payload", [
    {"tool_name": "Read", "tool_input": {"file_path": r"D:\edmonds-pipeline\secrets\Anna_key.txt"}},
    {"tool_name": "Read", "tool_input": {"file_path": r"C:\Users\x\AppData\Roaming\postgresql\pgpass.conf"}},
    {"tool_name": "Read", "tool_input": {"file_path": ".litkb-workstream"}},
    {"tool_name": "Grep", "tool_input": {"pattern": "password", "path": r"D:\x\litkb.pgpass"}},
    {"tool_name": "Glob", "tool_input": {"pattern": "**/*.env"}},
    {"tool_name": "Bash", "tool_input": {"command": "type %APPDATA%\\postgresql\\pgpass.conf"}},
], ids=["secrets_dir", "pgpass", "workstream_token", "grep_pgpass", "glob_env", "shell_pgpass"])
def test_the_hook_warns_on_a_credential_file_even_inside_a_workstream(payload, tmp_path):
    """P8 referee §3.7: the librarian holds Read, Grep and Glob, and nothing told it not to open a
    passfile. This rule fires INSIDE a workstream too — a workstream is a reason to reach literature
    through litkb, never a reason to read a credential, and `.litkb-workstream` is itself the secret
    that is always present there. The negative control is the test below it: an ordinary repository
    file in the same directory produces nothing."""
    _plant_token(tmp_path)
    r = _hook(payload | {"hook_event_name": "PreToolUse", "cwd": str(tmp_path)}, tmp_path)
    assert r.returncode == 0, r.stderr
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "credential file" in ctx, ctx
    assert "permissionDecision" not in json.loads(r.stdout)["hookSpecificOutput"], "warns, not blocks"


def test_the_hook_says_nothing_about_an_ordinary_file(tmp_path):
    _plant_token(tmp_path)
    r = _hook({"hook_event_name": "PreToolUse", "cwd": str(tmp_path), "tool_name": "Read",
               "tool_input": {"file_path": str(SCRIPTS / "docs" / "SCHEMAS.md")}}, tmp_path)
    assert r.returncode == 0 and r.stdout.strip() in ("", "{}"), r.stdout


def test_the_librarian_is_told_not_to_open_credential_files():
    """The brief is the control the hook is not: frontmatter hooks are ignored for plugin subagents,
    skipped by disableAllHooks, and not loaded in an untrusted folder (code.claude.com/docs/en/
    sub-agents). So the four shapes are named in the librarian's own words as well."""
    agent = (SCRIPTS.parent / ".claude" / "agents" / "librarian.md").read_text(encoding="utf-8")
    for shape in ("**/pgpass*", "**/secrets/**", "**/.litkb-workstream", "**/*.env"):
        assert shape in agent, f"the librarian brief does not name {shape}"
    assert "litkb_guard.py" in agent, "the librarian does not carry the credential guard"


def test_the_staged_hook_is_silent_inside_a_workstream(tmp_path):
    _plant_token(tmp_path)
    r = _hook({"hook_event_name": "PreToolUse", "cwd": str(tmp_path),
               "tool_name": "mcp__paper-search-mcp__download_scihub", "tool_input": {}}, tmp_path)
    assert r.returncode == 0 and r.stdout.strip() in ("", "{}"), r.stdout


def test_the_staged_hook_ignores_tools_that_are_not_literature_routes(tmp_path):
    r = _hook({"hook_event_name": "PreToolUse", "cwd": str(tmp_path),
               "tool_name": "Read", "tool_input": {"file_path": str(SCRIPTS / "CLAUDE.md")}}, tmp_path)
    assert r.returncode == 0 and r.stdout.strip() in ("", "{}"), r.stdout


def test_the_hook_is_staged_and_not_installed():
    """Design §9.1: the hook settings change every session's tool calls once merged, so they land
    AFTER the gate and by Kam's hand. This asserts the settings file does not register it yet — if
    it ever does, the promotion report has to list it, and this test is what forces that."""
    for settings in ((SCRIPTS.parent / ".claude" / "settings.json"),
                     (SCRIPTS / ".claude" / "settings.json")):
        if settings.exists():
            assert "litkb_guard" not in settings.read_text(encoding="utf-8"), (
                f"{settings} registers the P8 hook; it is staged, not installed (design §9.1)")


# ── the access-layer files exist and agree with the server ────────────────────────────────

def test_the_skill_and_the_agent_name_the_tools_that_exist():
    """A rule or a skill that names a tool which does not exist blocks work and offers no path
    (design §9.1). So the skill's and the librarian's tool names are checked against the server's
    own list, not against this file's."""
    skill = (SCRIPTS.parent / ".claude" / "skills" / "literature" / "SKILL.md").read_text(encoding="utf-8")
    agent = (SCRIPTS.parent / ".claude" / "agents" / "librarian.md").read_text(encoding="utf-8")
    names = set(tool_names())
    for doc, text in (("SKILL.md", skill), ("librarian.md", agent)):
        # `(?!\.py)` keeps a FILE name out of the tool scan: the librarian now cites the credential
        # guard `litkb_guard.py`, which is a hook on disk, not a tool on this server. The subtracted
        # set is DATABASE ROLES, which share the prefix and are not tools — the skill's re-derive
        # line for the block count names `litkb_reader` (2026-09-16), and a session that cannot run
        # a command it is told to run is the failure this test exists to prevent, in reverse.
        named = (set(re.findall(r"\blitkb_[a-z_]+\b(?!\.py)", text))
                 - {"litkb_test", "litkb_reader", "litkb_writer", "litkb_promoter", "litkb_ingest"})
        assert named <= names, f"{doc} names tools the server does not offer: {sorted(named - names)}"
        assert named, f"{doc} names no litkb tool at all"
    assert "mcp__litkb" in agent, "the librarian must restrict tools to the litkb MCP server"

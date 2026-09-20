"""The friction the FIRST real use of the knowledge base hit, and what closed it.

`Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8 is a defect list measured on one session that tried
to follow `Scripts/docs/LITERATURE_CONVENTION.md` end to end; `Reports/LITKB_P8_REFEREE_2026-09-15.md`
§4 classified each item. This module is the evidence for the half that lives in migration 0020 and
the admission/CLI path. The acquisition half (§8.9, quarantine) is in qc/test_litkb_p2.py and the
census half (corpus growth) in qc/test_litkb_inventory.py.

  friction (§)                                                    test
  8.6 the feeds vocabulary enforced is not the one documented     test_every_feeds_form_the_convention_documents_is_accepted
                                                                  test_a_token_that_is_not_one_of_the_seven_forms_is_refused
  8.1 step 4 has no CLI                                           test_use_add_writes_a_proposal_through_write_proposal
  8.1 a workstream is not optional                                test_use_add_outside_a_worktree_with_a_workstream_refuses
  8.6 a bad token would be found only at prepare                  test_use_add_refuses_a_bad_feeds_token_before_writing
  8.3 a quote goes in rationale because nothing can verify it     test_a_quote_is_anchored_in_a_block_and_verified_by_the_database
                                                                  test_a_quote_in_no_block_is_refused_not_written_as_free_text
                                                                  test_the_database_computes_quote_verified_not_the_client
  8.5 `admit --doi` alone always fails                            test_admit_with_a_doi_and_no_claim_is_admitted_registry_only
  8.5 and the two catches that must survive it                    test_an_admission_that_claims_nothing_and_says_nothing_is_still_refused
                                                                  test_a_claim_that_contradicts_the_registry_is_still_refused
  P4 the work title loses its subtitle                            test_the_work_title_is_the_registry_title_joined_with_its_subtitle
                                                                  test_the_key_is_minted_from_the_joined_title
  P4 a claim without the subtitle                                 test_a_claimed_title_without_the_subtitle_is_a_discrepancy_not_a_refusal
  P4 and the file that prints only the bare title                 test_a_first_page_printing_the_bare_title_still_binds
  8.4 documentation cannot be admitted at all                     test_a_web_source_is_admitted_from_its_snapshot_as_a_proposal
                                                                  test_a_web_admission_still_needs_a_second_session
"""
import json
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
pg_only = pytest.mark.requires_litkb_pg

KONDA_DOI = "10.14778/2994509.2994535"
KONDA_TITLE = "Magellan"
KONDA_SUBTITLE = "toward building entity matching management systems"


# ── fixtures ──────────────────────────────────────────────────────────────────────────────

class KB:
    """A thin handle on the shared litkb_test connection: one workstream per test, its token kept."""

    def __init__(self, psycopg, conn):
        self.psycopg, self.errors, self.conn = psycopg, psycopg.errors, conn
        self.tokens = {}

    def one(self, q, params=()):
        return self.conn.execute(q, params).fetchone()

    def ws(self, directory=None):
        ws_id, token = self.one(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/first-use', %s, 'first-use test', NULL)",
            (f"fu-{uuid.uuid4().hex[:12]}", str(directory) if directory else None))
        self.tokens[ws_id] = token
        if directory:
            (Path(directory) / ".litkb-workstream").write_text(
                json.dumps({"workstream_id": str(ws_id), "token": token}), encoding="utf-8")
        return ws_id

    def jsonb(self, v):
        from psycopg.types.json import Jsonb
        return Jsonb(v)

    def cli_conn(self):
        """The session connection, handed to commands.main() with close() disarmed — main closes the
        connection it was given, and this one is shared by the whole module."""
        conn = self.conn

        class _Kept:
            def __getattr__(self, name):
                return getattr(conn, name)

            def close(self):
                pass

        return _Kept()


@pytest.fixture
def kb(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    return KB(psycopg, conn)


def _crossref(doi, title, subtitle=None, author="Konda", year=2016):
    """A Crossref /works/<doi> message, in the shape registry.parse_crossref reads."""
    msg = {"DOI": doi, "title": [title], "type": "proceedings-article", "container-title": ["PVLDB"],
           "author": [{"family": author, "given": "P.", "sequence": "first"}],
           "issued": {"date-parts": [[year, 1]]}}
    if subtitle:
        msg["subtitle"] = [subtitle]
    return msg


class _CrossrefStub:
    """api.crossref.org/works/<doi> from a dict of messages; everything else 404. No network."""
    base = ""

    def __init__(self, records):
        self.records = {k.lower(): v for k, v in records.items()}

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        import urllib.parse
        if "api.crossref.org/works/" in url:
            rec = self.records.get(urllib.parse.unquote(url.split("/works/", 1)[1]).lower())
            return (200, {}, json.dumps({"message": rec}).encode()) if rec else (404, {}, b"")
        return 404, {}, b""


class _NoPace:
    def wait(self, *a, **k):
        pass

    def penalise(self, *a, **k):
        pass

    def __getattr__(self, _n):
        return lambda *a, **k: None


def _admit(kb, ws, doi, rec, *, claimed=None, agent="agentA", session="sessA", **kw):
    from litkb.admit import front
    return front.admit_registry(kb.conn, ws, kb.tokens[ws], doi=doi, claimed=claimed, agent=agent,
                                session=session, client=_CrossrefStub({doi: rec}), pacer=_NoPace(), **kw)


# ── §8.6: the feeds vocabulary ────────────────────────────────────────────────────────────

# Scripts/docs/LITERATURE_CONVENTION.md, "`Feeds` token vocabulary (doc-qualified, 2026-09-13)".
# Quoted from the table, not from memory: seven rows, one example each.
SEVEN_FORMS = ["framework §13.1", "narrative §4", "gated-plan gate 3", "review §4.18.4", "gap row 6",
               "decision litkb-p0-foundation", "report LIT_HUNT_FINAL_2026-09-06.md#§5"]


@pg_only
@pytest.mark.parametrize("token", SEVEN_FORMS)
def test_every_feeds_form_the_convention_documents_is_accepted(kb, token):
    """§8.6: the validator took three of the seven, so a use that fed a REPORT could carry no valid
    token and all 15 uses of that session were written with an EMPTY feeds array — the KB recording
    that the works were used and not what for. Migration 0020 widened it to the documented seven."""
    assert kb.one("SELECT litkb._feeds_token_ok(%s)", (token,))[0] is True


@pg_only
@pytest.mark.parametrize("token", ["framework 13", "review §", "narrative §4.1", "decision Bad_Slug",
                                   "report notmd#§5", "report X.md#§", "", "gap row", "gate 3"])
def test_a_token_that_is_not_one_of_the_seven_forms_is_refused(kb, token):
    """Widening is not weakening: `narrative §N` is integer-only because that document does not
    subdivide, a decision slug is lowercase, and a report token names a .md file and a location."""
    assert kb.one("SELECT litkb._feeds_token_ok(%s)", (token,))[0] is False


# ── §8.1 and §8.3: recording a use ────────────────────────────────────────────────────────

def _work_with_text(kb, ws, *, page_text, page_no=1):
    """An admitted work, a held file, an extraction run that is the file's CURRENT run, and one block
    carrying `page_text`. The shortest real path from "a paper is in the KB" to "a quote can be
    anchored in it" — which is the path §8.3 says does not exist end to end yet."""
    doi = f"10.5555/fu-{uuid.uuid4().hex[:10]}"
    title = f"Synthetic {uuid.uuid4().hex[:10]} work for the use CLI"
    res = _admit(kb, ws, doi, _crossref(doi, title, author="Tester", year=2021))
    assert res["outcome"] == "admitted", res
    work_id = res["work_id"]
    sha = uuid.uuid4().hex + uuid.uuid4().hex[:0] + uuid.uuid4().hex
    file_json = {"sha256": sha[:64], "rel_path": f"_litkb_staging/filed/fu-{uuid.uuid4().hex[:8]}.pdf",
                 "binding": {"verdict": "bound", "ratio": 0.99, "matched": title, "registry_title": title,
                             "author_found": True, "author_near_title": True, "text_layer": True,
                             "page": 1, "title_region": True}}
    att = kb.one("SELECT litkb.attach_file(%s, %s, %s, %s, %s, %s)",
                 (ws, kb.tokens[ws], work_id, kb.jsonb(file_json), "agentA", "sessA"))[0]
    assert att["outcome"] == "attached", att
    file_id = att["file_id"]
    run = kb.one("SELECT litkb.open_extraction_run(%s, '5-reconcile', 'litkb-reconcile', 'v1', 'h1', 'v1', "
                 "'local', 'ok', NULL, '{}'::jsonb)", (file_id,))[0]
    block = kb.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text, canonical, reading_order) "
                   "VALUES (%s, %s, %s, 'paragraph', %s, true, 1) RETURNING id",
                   (file_id, run, page_no, page_text))[0]
    kb.one("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run))
    return {"work_id": work_id, "key": res["checks"] and None or None, "file_id": file_id, "run_id": run,
            "block_id": block, "doi": doi, "title": title}


@pg_only
def test_use_add_writes_a_proposal_through_write_proposal(kb, tmp_path):
    """§8.1: 15 uses were written with psycopg by copying the P3 loader, because the convention's
    step 4 had no command. This is that command, through the same token-checked function."""
    from litkb import commands

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text="ordinary body text")
    rc = commands.main(["--dir", str(tmp_path), "--agent", "agentB", "--session", "sessB", "use", "add",
                        "--doi", w["doi"], "--statement", "it supplies the comparator", "--kind", "method",
                        "--feeds", "framework §13.1; report LIT_HUNT_FINAL_2026-09-06.md#§5"],
                       connect=lambda _db: kb.cli_conn())
    assert rc == 0
    row = kb.one("SELECT v.statement, v.kind, v.feeds, v.state FROM litkb.use_versions v "
                 "JOIN litkb.uses u ON u.id = v.use_id WHERE u.work_id = %s", (w["work_id"],))
    assert row[0] == "it supplies the comparator" and row[1] == "method" and row[3] == "proposed"
    assert row[2] == ["framework §13.1", "report LIT_HUNT_FINAL_2026-09-06.md#§5"]


@pg_only
def test_the_kind_vocabulary_in_the_help_text_is_the_one_the_database_enforces(kb):
    """`use add --kind` lists the vocabulary so the command is usable without reading SQL — and a list
    written in a help string is exactly the kind of restatement that rots (CLAUDE.md 3.3). This is
    what stops it: the help text is compared with the live CHECK on `use_versions.kind`."""
    import re

    from litkb import commands

    helptext = next(a for a in commands.build_parser()._subparsers._group_actions[0]
                    .choices["use"]._subparsers._group_actions[0].choices["add"]._actions
                    if a.dest == "kind").help
    src = kb.one("SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                 "JOIN pg_namespace n ON n.oid = t.relnamespace WHERE n.nspname = 'litkb' "
                 "AND t.relname = 'use_versions' AND c.conname LIKE '%%kind%%'")[0]
    assert sorted(re.findall(r"'([a-z ]+)'::text", src)) == \
        sorted(re.findall(r"[a-z]+(?: [a-z]+)*", helptext[helptext.index("(") + 1:helptext.index(")")]))


@pg_only
def test_use_add_outside_a_worktree_with_a_workstream_refuses(kb, tmp_path):
    """A use is a proposal, and a proposal belongs to something that can be prepared."""
    from litkb import commands

    empty = tmp_path / "no-workstream-here"
    empty.mkdir()
    with pytest.raises(SystemExit) as e:
        commands.main(["--dir", str(empty), "--agent", "a", "--session", "s", "use", "add",
                       "--key", "Nobody_1900_nothing-at-all", "--statement", "x", "--kind", "context"],
                      connect=lambda _db: kb.cli_conn())
    assert ".litkb-workstream" in str(e.value)


@pg_only
def test_use_add_refuses_a_bad_feeds_token_before_writing(kb, tmp_path):
    """§8.6 again, from the other side: prepare would have HELD the chain on this, long after the
    session had moved on. It is refused at the command, and nothing is written."""
    from litkb import commands

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text="ordinary body text")
    before = kb.one("SELECT count(*) FROM litkb.use_versions WHERE workstream_id = %s", (ws,))[0]
    with pytest.raises(SystemExit) as e:
        commands.main(["--dir", str(tmp_path), "--agent", "a", "--session", "s", "use", "add",
                       "--doi", w["doi"], "--statement", "x", "--kind", "context", "--feeds", "§5; framework §1"],
                      connect=lambda _db: kb.cli_conn())
    assert "§5" in str(e.value)
    assert kb.one("SELECT count(*) FROM litkb.use_versions WHERE workstream_id = %s", (ws,))[0] == before


@pg_only
def test_a_quote_is_anchored_in_a_block_and_verified_by_the_database(kb, tmp_path):
    """§8.3: `use_evidence` needs a block and a run, and there was no path from an acquired PDF to
    them, so the quotes went into `rationale` — free text the database does not check."""
    from litkb import commands

    ws = kb.ws(tmp_path)
    quote = "the noise floor is what an effect must clear"
    w = _work_with_text(kb, ws, page_text=f"Some preamble. {quote}. Some more.", page_no=7)
    rc = commands.main(["--dir", str(tmp_path), "--agent", "a", "--session", "s", "use", "add",
                        "--doi", w["doi"], "--statement", "it states the noise-floor rule",
                        "--kind", "method", "--quote", quote, "--page", "7"],
                       connect=lambda _db: kb.cli_conn())
    assert rc == 0
    ev = kb.one("SELECT e.quote, e.page, e.quote_verified, e.block_id, e.run_id FROM litkb.use_evidence e "
                "JOIN litkb.use_versions v ON v.version_id = e.use_version_id "
                "JOIN litkb.uses u ON u.id = v.use_id WHERE u.work_id = %s", (w["work_id"],))
    assert ev[0] == quote and ev[1] == 7 and ev[2] is True
    assert ev[3] == w["block_id"] and ev[4] == w["run_id"]


@pg_only
def test_a_quote_in_no_block_is_refused_not_written_as_free_text(kb, tmp_path):
    """The refusal IS the fix. A fallback into `rationale` would recreate §8.3 inside the command
    that exists to close it, and would do it silently."""
    from litkb import commands

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text="nothing like the quote")
    with pytest.raises(SystemExit) as e:
        commands.main(["--dir", str(tmp_path), "--agent", "a", "--session", "s", "use", "add",
                       "--doi", w["doi"], "--statement", "x", "--kind", "context",
                       "--quote", "words that are in no block at all"],
                      connect=lambda _db: kb.cli_conn())
    assert "no extracted block" in str(e.value)
    assert kb.one("SELECT count(*) FROM litkb.use_versions v JOIN litkb.uses u ON u.id = v.use_id "
                  "WHERE u.work_id = %s", (w["work_id"],))[0] == 0


@pg_only
def test_the_page_narrows_which_block_the_quote_is_anchored_to(kb, tmp_path):
    """A sentence that occurs twice in a paper has two candidate anchors, and `--page` is how the
    caller says which one the use is about. Without it the anchor is whichever block the ordering
    returns first, and the evidence points at a passage the reader never meant."""
    from litkb import use as _use

    ws = kb.ws(tmp_path)
    quote = "the same sentence twice over"
    w = _work_with_text(kb, ws, page_text=f"first occurrence: {quote}.", page_no=3)
    kb.conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text, canonical, reading_order) "
                    "VALUES (%s, %s, 9, 'paragraph', %s, true, 2)",
                    (w["file_id"], w["run_id"], f"second occurrence: {quote}."))
    assert [h["page"] for h in _use.locate_quote(kb.conn, w["work_id"], quote)] == [3, 9]
    assert [h["page"] for h in _use.locate_quote(kb.conn, w["work_id"], quote, page=9)] == [9]


@pg_only
def test_a_quote_only_in_a_superseded_run_is_not_evidence(kb, tmp_path):
    """`use_evidence_status.promotable` compares an evidence row's run with the file's CURRENT run, so
    a quote anchored in a superseded extraction is held at prepare. Refusing it here means the caller
    finds out at the command, and never records evidence about text that is no longer the file's."""
    from litkb import use as _use

    ws = kb.ws(tmp_path)
    quote = "a line the second extraction lost"
    w = _work_with_text(kb, ws, page_text=f"preamble {quote} tail")
    assert _use.locate_quote(kb.conn, w["work_id"], quote)          # the current run has it
    run2 = kb.one("SELECT litkb.open_extraction_run(%s, '5-reconcile', 'litkb-reconcile', 'v2', 'h2', 'v2', "
                  "'local', 'ok', NULL, '{}'::jsonb)", (w["file_id"],))[0]
    kb.conn.execute("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text, canonical, reading_order) "
                    "VALUES (%s, %s, 1, 'paragraph', 'the second extraction read something else', true, 1)",
                    (w["file_id"], run2))
    kb.one("SELECT litkb.set_current_run(%s, %s, %s)", (w["file_id"], w["run_id"], run2))
    assert _use.locate_quote(kb.conn, w["work_id"], quote) == []    # and now nothing does


@pg_only
def test_a_use_statement_carrying_a_nul_still_writes(kb, tmp_path):
    """Postgres jsonb refuses \\u0000, so every JSON document litkb sends has its NULs removed first
    (`textnorm.jsonb_safe`, behind `front._jsonb`). A statement typed from a PDF extract can carry
    one — Bell 1977's Creator field is how this was found — and the use must still be recordable."""
    from litkb import use as _use

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text="ordinary body text")
    _uid, vid = _use.write_use(kb.conn, ws, kb.tokens[ws], work_id=w["work_id"],
                               statement="it supplies the compar\x00ator", kind="context",
                               rationale="from a scan\x00ned extract", agent="a", session="s")
    row = kb.one("SELECT statement, rationale FROM litkb.use_versions WHERE version_id = %s", (vid,))
    assert row[0] == "it supplies the comparator" and row[1] == "from a scanned extract"


@pg_only
def test_a_discrepancy_detail_carrying_a_nul_still_writes(kb, tmp_path):
    """Same guard, the other new call site: a discrepancy's detail is built from a CLAIMED value, and
    a claim read out of a scanned tracker row is exactly where a NUL comes from."""
    from litkb.admit import front

    ws = kb.ws(tmp_path)
    cand = kb.one("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
                  (ws, kb.tokens[ws], "a candidate"))[0]
    did = front.record_discrepancy(kb.conn, ws, kb.tokens[ws], source="admission", source_row="10.5555/nul",
                                   field="title", claimed="Magellan", registry="Magellan: toward",
                                   ratio=0.24, detail={"raw": "Magel\x00lan"}, candidate_id=cand,
                                   agent="a", session="s")
    assert kb.one("SELECT detail FROM litkb.discrepancies WHERE id = %s", (did,))[0] == {"raw": "Magellan"}


@pg_only
def test_use_add_normalises_its_agent_and_session_labels(kb, tmp_path):
    """Labels are compared, not just stored — the approval rule refuses the admitter's own session —
    so a label decorated with an invisible character must not make one session look like two."""
    from litkb import commands

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text="ordinary body text")
    rc = commands.main(["--dir", str(tmp_path), "--agent", "agentB​", "--session", " sessB ",
                        "use", "add", "--doi", w["doi"], "--statement", "x", "--kind", "context"],
                       connect=lambda _db: kb.cli_conn())
    assert rc == 0
    row = kb.one("SELECT v.agent, v.session_id FROM litkb.use_versions v JOIN litkb.uses u ON u.id = v.use_id "
                 "WHERE u.work_id = %s", (w["work_id"],))
    assert row == ("agentB", "sessB")


@pg_only
def test_a_reference_cannot_claim_a_resolution_it_does_not_show(kb, tmp_path):
    """Stage 6's rows reach the table two ways — `litkb.add_reference`, and the direct INSERT the
    ingest login has held since 0010 — so the rule that a resolution must be SHOWN is a trigger, not
    a check inside the function. An edge is drawn from exactly this row (migration 0020)."""
    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text="ordinary body text")
    ins = ("INSERT INTO litkb.\"references\" (file_id, run_id, raw_text, resolution, resolved_doi, "
           "resolved_work_id, ref_key) VALUES (%s, %s, 'Someone 2001.', %s, %s, %s, %s)")
    with pytest.raises(kb.errors.CheckViolation):
        kb.conn.execute(ins, (w["file_id"], w["run_id"], "resolved", None, None, "b1"))
    with pytest.raises(kb.errors.CheckViolation):
        kb.conn.execute(ins, (w["file_id"], w["run_id"], "unresolved", None, w["work_id"], "b2"))
    kb.conn.execute(ins, (w["file_id"], w["run_id"], "resolved", "10.5555/shown", None, "b3"))
    assert kb.one("SELECT resolution FROM litkb.\"references\" WHERE run_id = %s AND ref_key = 'b3'",
                  (w["run_id"],))[0] == "resolved"


@pg_only
def test_the_database_computes_quote_verified_not_the_client(kb, tmp_path):
    """The 0007 trigger re-reads the block at [char_start, char_end) and overwrites the column, so a
    correct-looking quote at the wrong offsets is recorded as NOT verified rather than as evidence."""
    from litkb import use as _use

    ws = kb.ws(tmp_path)
    quote = "a sentence that is really there"
    w = _work_with_text(kb, ws, page_text=f"prefix {quote} suffix")
    _uid, vid = _use.write_use(kb.conn, ws, kb.tokens[ws], work_id=w["work_id"], statement="s",
                               kind="context", agent="a", session="s")
    good = _use.locate_quote(kb.conn, w["work_id"], quote)[0]
    bad = dict(good, char_start=good["char_start"] + 3, char_end=good["char_end"] + 3)
    assert _use.attach_quote(kb.conn, ws, kb.tokens[ws], vid, good, quote)["quote_verified"] is True
    assert _use.attach_quote(kb.conn, ws, kb.tokens[ws], vid, bad, quote)["quote_verified"] is False


# ── a quote that crosses a stored line break (2026-09-20, migration 0026) ─────────────────
#
# THE DEFECT, from the operational proving run. 48.9 % of current-run blocks store `\r\n` and 7
# of the project's 8 verified spans cross one, while the review writer is an LLM emitting JSON:
# the transport carries `\r\n` perfectly well (measured), but no LLM has been observed emitting a
# raw CR, so every multi-line quote it sent was refused as "in no extracted block" and it answered
# by quoting single LINES -- 33 characters at the longest inside a real verified span -- which an
# adversarial reviewer then found half the review's sentences overreaching. The grader had already
# solved the same comparison (`textnorm.canonical_newlines` + its SQL half); the recording path
# had not. These four rows are the relaxation and the three refusals that bound it.

CRLF_BLOCK = ("Canopy cover was measured on eleven plots in June.\r\n"
              "The same plots were flown again in October of the same year.\r\n"
              "\r\n"
              "A second paragraph begins here and says something else entirely.\r\n")
CRLF_SPAN = "measured on eleven plots in June.\r\nThe same plots were flown again"


def test_locate_in_text_maps_canonical_offsets_back_to_the_stored_bytes():
    """The arithmetic on its own, with no database: a `\\r\\n` is ONE canonical character and TWO
    stored ones, so every offset after a break would be short by one per break if the mapping were
    dropped. Each case asserts the SLICE, not just the numbers, so an off-by-one cannot pass."""
    from litkb.textnorm import canonical_newlines
    from litkb.use import locate_in_text

    for text, quote in [(CRLF_BLOCK, canonical_newlines(CRLF_SPAN)),        # LF quote, CRLF block
                        (CRLF_BLOCK, CRLF_SPAN),                            # the stored bytes
                        ("a\rb\r\nc\nd", "b\nc"),                           # a lone CR counts as one
                        ("x\r\n\r\ny", "x\n\n"),                            # a blank line is two breaks
                        ("no breaks at all", "breaks at")]:
        span = locate_in_text(text, quote)
        assert span is not None, (text, quote)
        assert canonical_newlines(text[span[0]:span[1]]) == canonical_newlines(quote), (text, quote, span)
    # and the offsets are the STORED ones, not the canonical ones
    s, e = locate_in_text(CRLF_BLOCK, canonical_newlines(CRLF_SPAN))
    assert CRLF_BLOCK[s:e] == CRLF_SPAN, (s, e, CRLF_BLOCK[s:e])
    assert (s, e) == (CRLF_BLOCK.index(CRLF_SPAN), CRLF_BLOCK.index(CRLF_SPAN) + len(CRLF_SPAN))
    assert locate_in_text(CRLF_BLOCK, "a quote that is not there") is None


@pg_only
def test_a_quote_spanning_a_stored_line_break_is_located_and_verified(kb, tmp_path):
    """ROW 1. The quote a writer can actually emit -- LF only -- against a block that stores
    `\\r\\n`. It is located; the offsets recorded are the STORED text's own, so the trigger cuts
    the same characters; the DATABASE sets quote_verified; and the quote stored is the caller's
    own string. That last assertion is the one that keeps the verdict meaningful: substituting the
    block's bytes for what the caller said would make the trigger's comparison a tautology."""
    from litkb import use as _use
    from litkb.textnorm import canonical_newlines

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text=CRLF_BLOCK)
    lf = canonical_newlines(CRLF_SPAN)
    assert "\r" not in lf and "\r\n" in CRLF_SPAN
    hits = _use.locate_quote(kb.conn, w["work_id"], lf)
    assert len(hits) == 1, hits
    assert (hits[0]["char_start"], hits[0]["char_end"]) == (
        CRLF_BLOCK.index(CRLF_SPAN), CRLF_BLOCK.index(CRLF_SPAN) + len(CRLF_SPAN))
    _uid, vid = _use.write_use(kb.conn, ws, kb.tokens[ws], work_id=w["work_id"], statement="s",
                               kind="context", agent="a", session="s")
    ev = _use.attach_quote(kb.conn, ws, kb.tokens[ws], vid, hits[0], lf)
    assert ev["quote_verified"] is True, ev
    stored, cut = kb.one(
        "SELECT e.quote, substring(b.text FROM e.char_start + 1 FOR e.char_end - e.char_start) "
        "  FROM litkb.use_evidence e JOIN litkb.blocks b ON b.id = e.block_id WHERE e.id = %s",
        (ev["evidence_id"],))
    assert stored == lf, "the stored quote is not the caller's own string"
    assert cut == CRLF_SPAN, "the offsets do not cut the stored CRLF span"


@pg_only
def test_a_quote_that_differs_in_one_character_is_still_refused(kb, tmp_path):
    """ROW 2, the reverse guarantee. `canonical_newlines` rewrites line ENDINGS and nothing else,
    so the relaxation cannot reach a single letter: one changed word is in no block, and the
    trigger says so too when a caller names the offsets itself."""
    from litkb import use as _use
    from litkb.textnorm import canonical_newlines

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text=CRLF_BLOCK)
    altered = canonical_newlines(CRLF_SPAN).replace("eleven", "twelve")
    assert altered not in CRLF_BLOCK and altered not in canonical_newlines(CRLF_BLOCK)
    assert _use.locate_quote(kb.conn, w["work_id"], altered) == []
    good = _use.locate_quote(kb.conn, w["work_id"], canonical_newlines(CRLF_SPAN))[0]
    _uid, vid = _use.write_use(kb.conn, ws, kb.tokens[ws], work_id=w["work_id"], statement="s",
                               kind="context", agent="a", session="s")
    assert _use.attach_quote(kb.conn, ws, kb.tokens[ws], vid, good, altered)["quote_verified"] is False


@pg_only
def test_a_quote_that_joins_two_paragraphs_by_dropping_a_blank_line_is_refused(kb, tmp_path):
    """ROW 3, and the reason `canonical_newlines` is NOT a run collapse. Dropping a blank line
    changes the NUMBER of breaks, which is a change of CONTENT: it makes the end of one paragraph
    and the start of the next read as one sentence. `a\\r\\n\\r\\nb` becomes `a\\n\\nb`, never
    `a\\nb`, so this quote is in no block -- in Python and in the database's own function."""
    from litkb import use as _use
    from litkb.textnorm import canonical_newlines

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text=CRLF_BLOCK)
    real = "flown again in October of the same year.\r\n\r\nA second paragraph begins"
    assert real in CRLF_BLOCK, "the fixture no longer holds the paragraph break"
    joined = canonical_newlines(real).replace("\n\n", "\n")
    assert _use.locate_quote(kb.conn, w["work_id"], joined) == []
    assert kb.one("SELECT position(%s in litkb.canonical_newlines(text)) FROM litkb.blocks WHERE id = %s",
                  (joined, w["block_id"]))[0] == 0
    assert _use.locate_quote(kb.conn, w["work_id"], canonical_newlines(real)), \
        "the same span WITH its blank line must still locate"


@pg_only
def test_an_exact_raw_crlf_quote_still_locates_at_its_own_bytes(kb, tmp_path):
    """ROW 4, the existing behaviour. 7 of the project's 8 verified `use_evidence` rows store a
    CR, so a caller that sends the block's own bytes -- every row written before 2026-09-20 --
    must still locate at exactly those bytes and still verify."""
    from litkb import use as _use

    ws = kb.ws(tmp_path)
    w = _work_with_text(kb, ws, page_text=CRLF_BLOCK)
    hits = _use.locate_quote(kb.conn, w["work_id"], CRLF_SPAN)
    assert len(hits) == 1 and (hits[0]["char_start"], hits[0]["char_end"]) == (
        CRLF_BLOCK.index(CRLF_SPAN), CRLF_BLOCK.index(CRLF_SPAN) + len(CRLF_SPAN))
    _uid, vid = _use.write_use(kb.conn, ws, kb.tokens[ws], work_id=w["work_id"], statement="s",
                               kind="context", agent="a", session="s")
    assert _use.attach_quote(kb.conn, ws, kb.tokens[ws], vid, hits[0],
                             CRLF_SPAN)["quote_verified"] is True


# ── §8.5: a DOI with no claim ─────────────────────────────────────────────────────────────

@pg_only
def test_admit_with_a_doi_and_no_claim_is_admitted_registry_only(kb, tmp_path):
    """§8.5: three DOIs were refused at check 1 for having "no claimed record to compare with the
    registry and no bound file", and the message did not say what to do. The rule is about a CLAIM;
    with no claim there is nothing to contradict, and the identity is the registry record — which the
    admission now RECORDS as such on the identifier's evidence."""
    ws = kb.ws(tmp_path)
    doi = f"10.5555/fu-{uuid.uuid4().hex[:10]}"
    res = _admit(kb, ws, doi, _crossref(doi, f"A work admitted on its registry record alone {uuid.uuid4().hex[:8]}",
                                        author="Solo", year=2019))
    assert res["outcome"] == "admitted", res["checks"]["check1_study_exists"]
    ev = kb.one("SELECT v.evidence FROM litkb.identifier_versions v JOIN litkb.identifiers i ON i.id = v.identifier_id "
                "WHERE i.scheme = 'doi' AND i.value_norm = litkb.norm_identifier('doi', %s)", (doi,))[0]
    assert ev["registry_only"] is True


@pg_only
def test_an_admission_that_claims_nothing_and_says_nothing_is_still_refused(kb, tmp_path):
    """The relaxation is a DECLARATION, not a hole: a caller that sends no claim, no bound file and
    no `registry_only` on the identifier's evidence is refused exactly as it was before 0020. What
    changed is that the case is sayable and, once said, recorded — not that check 1 stopped asking."""
    ws = kb.ws(tmp_path)
    doi = f"10.5555/fu-{uuid.uuid4().hex[:10]}"
    title = f"A work admitted by nobody in particular {uuid.uuid4().hex[:8]}"
    cand = kb.one("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
                  (ws, kb.tokens[ws], title))[0]
    ident = [{"scheme": "doi", "value": doi, "verified_by": "crossref",
              "evidence": {"registry": "crossref", "registry_title": title,
                           "registry_first_author": "Nobody", "registry_year": 2020}}]
    res = kb.one("SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, '{}'::jsonb, 'a', 's')",
                 (ws, kb.tokens[ws], cand, f"Nobody_2020_{uuid.uuid4().hex[:10]}",
                  kb.jsonb({"type": "article", "title": title, "year": 2020}), kb.jsonb(ident)))[0]
    assert res["outcome"] == "refused" and res["refused_at"] == "check1_study_exists"
    assert any("registry_only" in r for r in res["checks"]["check1_study_exists"]["reasons"])


@pg_only
def test_a_claim_that_contradicts_the_registry_is_still_refused(kb, tmp_path):
    """The catch §8.5 praised in the same breath: a claimed first author of Papadakis against a
    registry record whose first author is Mandilaras caught a real error in the reviewer's own input.
    Relaxing the no-claim case must not relax the claim case, and does not."""
    ws = kb.ws(tmp_path)
    doi = f"10.5555/fu-{uuid.uuid4().hex[:10]}"
    title = f"An entity resolution survey {uuid.uuid4().hex[:8]}"
    rec = _crossref(doi, title, author="Mandilaras", year=2021)
    res = _admit(kb, ws, doi, rec, claimed={"title": title,
                                            "authors": "Papadakis, G.", "year": "2021"})
    assert res["outcome"] == "refused" and res["refused_at"] == "check1_study_exists"
    assert any("first author" in r for r in res["checks"]["check1_study_exists"]["reasons"])


# ── P4: the title and its subtitle ────────────────────────────────────────────────────────

def test_the_work_title_is_the_registry_title_joined_with_its_subtitle():
    """`10.14778/2994509.2994535` entered this KB as `Konda_2016_magellan-work`, title "Magellan".
    Crossref publishes the subtitle in its own field and `parse_crossref` already built the joined
    form into `titles`; only the STORED title was the bare one."""
    from litkb.admit import registry

    rec = registry.parse_crossref(_crossref(KONDA_DOI, KONDA_TITLE, KONDA_SUBTITLE), KONDA_DOI)
    assert rec["title"] == KONDA_TITLE and rec["subtitle"] == KONDA_SUBTITLE
    assert registry.work_fields(rec)["title"] == f"{KONDA_TITLE}: {KONDA_SUBTITLE}"
    assert registry.work_fields(rec)["subtitle"] == KONDA_SUBTITLE       # kept in its own field too
    bare = registry.parse_crossref(_crossref(KONDA_DOI, KONDA_TITLE), KONDA_DOI)
    assert registry.work_fields(bare)["title"] == KONDA_TITLE            # no subtitle, no change


def test_the_key_is_minted_from_the_joined_title():
    """The size of the defect: a one-word slug that `make_key` has to pad out with "work" to reach
    its two-word minimum, against a slug that says what the paper is."""
    from litkb.admit import registry
    from litkb.admit.front import make_key

    rec = registry.parse_crossref(_crossref(KONDA_DOI, KONDA_TITLE, KONDA_SUBTITLE), KONDA_DOI)
    assert make_key(rec["first_author"], rec["year"], KONDA_TITLE) == "Konda_2016_magellan-work"
    assert make_key(rec["first_author"], rec["year"], registry.work_title(rec)) == \
        "Konda_2016_magellan-building-entity-matching"


@pg_only
def test_a_claimed_title_without_the_subtitle_is_a_discrepancy_not_a_refusal(kb, tmp_path):
    """`judge_candidate` takes its max over `rec["titles"]`, so a bare-title claim scores 1.0 against
    the bare form and check 1 passes — it always did. What is new is that the disagreement is KEPT
    (decisions.yaml litkb-p0-foundation, "P3 load"), under `discrepancies.source = 'admission'`."""
    ws = kb.ws(tmp_path)
    doi = f"10.14778/fu-{uuid.uuid4().hex[:10]}"
    rec = _crossref(doi, KONDA_TITLE, KONDA_SUBTITLE)
    res = _admit(kb, ws, doi, rec, claimed={"title": KONDA_TITLE, "authors": "Konda, P.", "year": "2016"})
    assert res["outcome"] == "admitted", res["checks"]["check1_study_exists"]
    assert kb.one("SELECT title FROM litkb.main_works WHERE work_id = %s",
                  (res["work_id"],))[0] == f"{KONDA_TITLE}: {KONDA_SUBTITLE}"
    d = kb.one("SELECT source, field, claimed_value, registry_value FROM litkb.discrepancies "
               "WHERE work_id = %s", (res["work_id"],))
    assert d[0] == "admission" and d[1] == "title"
    assert d[2] == KONDA_TITLE and d[3] == f"{KONDA_TITLE}: {KONDA_SUBTITLE}"


def test_the_extractors_own_damage_is_dropped_before_any_comparison():
    """A PDF text layer that could not render a glyph emits U+FFFD; a soft hyphen (U+00AD) and the
    U+FFFE pypdfium2 writes at a line-break hyphen are the same class. All three are DROPPED, so the
    halves of a split word rejoin — the rule `litkb.norm_search_text` applies to the indexed text and
    the query alike (migration 0018, `work/20260915-access-layer`), here on the comparison side.

    **And what it does NOT fix, measured rather than assumed.** U+FFFD stands for a LETTER, not a
    joiner, so dropping it turns "K<FFFD>pcke" into the token "kpcke" — closer to the truth than the
    two tokens "k" and "pcke" it used to produce, and still not "kopcke". Köpcke 2010's first page
    therefore still fails check 3's author rule, and the file stays in quarantine. The precise fix is
    to treat U+FFFD as a ONE-CHARACTER WILDCARD in `tokens_contain` (a ratio wants it dropped, a
    token equality wants it matched) — a change to a refereed guard with three mutation rows on it,
    which is not something to make on the way past.
    """
    from litkb.admit.binding import fold_tokens, surname_tokens, tokens_contain
    from litkb.admit.resolver import title_match_ratio

    assert fold_tokens("misclassi­cation") == ["misclassication"]     # soft hyphen: rejoined
    assert fold_tokens("spe￾cial") == ["special"]                      # U+FFFE: rejoined
    assert fold_tokens("K�pcke") == ["kpcke"]                          # one token, not two
    assert title_match_ratio("Evaluation of entity resolution approaches",
                             "Evaluation of entity resoluti�n approaches") > 0.98
    # the residual, pinned so it cannot be quietly believed fixed
    assert tokens_contain(fold_tokens("K�pcke, H. and Rahm, E."), surname_tokens("Köpcke")) is False
    assert tokens_contain(fold_tokens("Köpcke, H. and Rahm, E."), surname_tokens("Köpcke")) is True


def test_a_first_page_printing_the_bare_title_still_binds():
    """Storing the joined title must not start refusing files that used to bind: a publisher prints
    whichever form it chose, so the binder tries every form the registry published and records which
    one matched, while `registry_title` stays the WORK's title (check 3 compares against that)."""
    from litkb.admit import binding, registry

    rec = registry.parse_crossref(_crossref(KONDA_DOI, KONDA_TITLE, KONDA_SUBTITLE), KONDA_DOI)
    page = "Magellan\nPradap Konda, Sanjib Das, Paul Suganthan G. C.\nPVLDB 2016\n\nABSTRACT\n" + \
           "\n".join(f"line {i} of the paper" for i in range(30))
    forms = registry.title_forms(rec)
    assert forms[0] == f"{KONDA_TITLE}: {KONDA_SUBTITLE}"
    b = binding.bind_any(None, forms, "Konda", page_text=page, info={})
    assert b["verdict"] == "bound" and b["matched_title_form"] == KONDA_TITLE
    assert b["registry_title"] == forms[0]        # what _check_binding compares with the work's title


# ── §8.4: a source with no PDF ────────────────────────────────────────────────────────────

def _web_page(title, authors):
    """The admitter's saved text of the page: its heading, its author line, then its prose. Exactly
    what `pdftotext` gives for a PDF's first page, which is why the same binder reads both."""
    return (f"{title}\n{authors} Documentation\n\nRetrieved for the litkb linkage review.\n\n"
            + "\n".join(f"Paragraph {i} of the documentation page, describing relationship types."
                        for i in range(20)))


def _web_admit(kb, ws, tmp_path, *, title=None, authors="Crossref", agent="agentA", session="sessA"):
    from litkb.acquire.store import Store
    from litkb.admit import front

    slug = uuid.uuid4().hex[:10]
    title = title or f"Crossref {slug} relationships and versioning"
    root = tmp_path / "lit"
    (root / "_litkb_staging").mkdir(parents=True)
    snap = tmp_path / "snapshot.txt"
    snap.write_text(_web_page(title, authors), encoding="utf-8")
    # the URL is an identifier, so two tests sharing one would be check 2's duplicate, not a bug
    return front.admit_web(kb.conn, ws, kb.tokens[ws], title=title, authors=authors, year=2025,
                           url=f"https://www.crossref.org/documentation/relationships/{slug}",
                           retrieved="2026-09-15", snapshot_path=snap, source_note="the documentation page itself",
                           store=Store(root=root), agent=agent, session=session), Store(root=root)


@pg_only
def test_a_web_source_is_admitted_from_its_snapshot_as_a_proposal(kb, tmp_path):
    """§8.4: `admit --manual` requires `--file`, and check 3 binds against a PDF's first-page text
    layer, so the Crossref relationships page was refused at `check4_manual` — "no text layer on the
    first page and no PDF title match" — and six load-bearing sources ended up cited outside the KB.
    The snapshot IS the text layer; nothing in the database was relaxed to take it."""
    ws = kb.ws(tmp_path)
    res, store = _web_admit(kb, ws, tmp_path)
    assert res["outcome"] == "proposed", res
    assert res["checks"]["check3_binding"]["verdict"] == "bound"
    f = kb.one("SELECT rel_path, copy_kind, source_url, obtained_at, has_text_layer, txt_extract_path "
               "FROM litkb.file_versions WHERE file_id = %s", (res["file_id"],))
    assert f[0].startswith("_litkb_staging/web/") and f[1] == "web snapshot"
    assert f[2].startswith("https://") and f[3] is not None and f[4] is True and f[5] == f[0]
    assert (store.staging / "web").exists()


@pg_only
def test_a_web_admission_still_needs_a_second_session(kb, tmp_path):
    """It is a manual proposal, not a new class of admission: check 4's sign-off is untouched."""
    from litkb.admit import front

    ws = kb.ws(tmp_path)
    res, _store = _web_admit(kb, ws, tmp_path, agent="agentA", session="sessA")
    with pytest.raises(front.AdmissionError):
        front.approve(kb.conn, ws, kb.tokens[ws], res["admission_id"], "agentA", "sessA")
    out = front.approve(kb.conn, ws, kb.tokens[ws], res["admission_id"], "agentB", "sessB")
    assert out["outcome"] in ("approved", "admitted"), out

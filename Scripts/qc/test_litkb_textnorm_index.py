r"""litkb 0025 — the index-only ligature repair, driven on REAL corpus text.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w2 py -3.12 -m pytest qc/test_litkb_textnorm_index.py

WHAT THESE TESTS RUN ON. `qc/testdata/litkb_textnorm/real_blocks.json` holds four blocks copied
VERBATIM out of the corpus — block id, file id, run id, page, type, sha256 and the text exactly as
the extractor wrote it, control bytes and all (they appear in the JSON as \u0001 / \u001d escapes,
so no control byte is typed into a tracked file). They are not invented strings, and the rule they
exercise was derived from the whole corpus, not from them (CLAUDE.md 3.4c):

  conflict-ff  01a0abc7-429d-7a0d-b7fb-252dab0c32ec  'Modelling covariate e<0x01>ects'  -> ff
  conflict-fi  01a0abc7-42ad-7050-b607-63aacd8a50c8  'in<0x01>nitely long'              -> fi
  floating     01a0ad5b-1765-7e08-89cc-5342a879f416  '<0x1d>oating point'               -> fl
  hyphenated   01a0abc8-4a18-7ca5-88e5-6dac9bf744f0  'abund- ant', and `di<0x81> culties`

The first two are the SAME FILE and the SAME BYTE resolving to two different ligatures, which is why
migration 0025 carries no byte->ligature table: `test_a_fixed_byte_table_cannot_repair_both` is that
argument executed rather than asserted.

Each test inserts the recorded text into `litkb.blocks` on the worker database the suite already
resets and migrates (qc/conftest.py `litkb_pg_base`), so leg 1 of litkb_search runs against a real
row through the real expression index, not against a string literal in a SELECT.

The full-corpus half of the proof — 372,192 blocks, the md5 of every block's text and the
quote_verified set identical across the migration, and the REINDEX timings — is
`qc/instruments/litkb_norm_index_proof.py`, which cannot run inside the ladder because it needs a
restore of the nightly dump. Its numbers are in Reports/litkb_norm_index_proof_2026-09-19.csv.
"""
import hashlib
import json
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
FIX = SCRIPTS / "qc" / "testdata" / "litkb_textnorm" / "real_blocks.json"
pg_only = pytest.mark.requires_litkb_pg

#: leg 1 of litkb_search (pipeline/litkb/mcp/server.py, `_SEARCH_BLOCKS_ALL`): the all-terms lexical
#: leg, text and query through the same normaliser. The main_files/main_works joins there decide
#: which blocks are VISIBLE; this is the part that decides what MATCHES.
LEG1 = ("SELECT to_tsvector('english', litkb.norm_search_text(b.text)) "
        "       @@ plainto_tsquery('english', litkb.norm_search_text(%s)) "
        "  FROM litkb.blocks b WHERE b.id = %s")


@pytest.fixture(scope="module")
def recorded():
    """The four recorded blocks, each re-hashed against the sha256 the capture wrote."""
    blocks = json.loads(FIX.read_text(encoding="utf-8"))
    for name, b in blocks.items():
        got = hashlib.sha256(b["text"].encode("utf-8")).hexdigest()
        assert got == b["sha256"], f"{name}: recorded text does not match its recorded sha256"
    return blocks


@pytest.fixture(scope="module")
def loaded(litkb_pg_base, recorded):
    """The recorded text, inserted into litkb.blocks -> {name: block id}. One file and one
    extraction run stand in for the corpus's; the TEXT is what is under test and it is verbatim."""
    from psycopg.types.json import Jsonb

    _psycopg, conn, _ran = litkb_pg_base
    ws = conn.execute(
        "SELECT workstream_id FROM litkb.open_workstream(%s, 'work/20260920-index-normaliser', "
        "NULL, 'the 0025 ligature-expansion tests', NULL)",
        (f"t-norm-{uuid.uuid4().hex[:8]}",)).fetchone()[0]
    work = conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, "
        "'setup', 'setup')",
        (Jsonb({"key": f"Textnorm_2026_{uuid.uuid4().hex[:8]}-paper"}),
         Jsonb({"type": "article", "title": "A recorded-text work", "authors": []}), ws)).fetchone()[0]
    file_id = conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, "
        "'setup', 'setup')",
        (Jsonb({"sha256": uuid.uuid4().hex + uuid.uuid4().hex}),
         Jsonb({"work_id": str(work), "rel_path": "Validation/Textnorm_2026_x-paper.pdf",
                "status": "active"}), ws)).fetchone()[0]
    run = conn.execute(
        "INSERT INTO litkb.extraction_runs (file_id, stage, tool, tool_version, params_hash, "
        "pipeline_version, host, status) VALUES (%s, 'native', 'test', '0', 'p', 'v0', 'local', "
        "'ok') RETURNING id", (file_id,)).fetchone()[0]
    conn.execute("SELECT litkb.set_current_run(%s, NULL, %s)", (file_id, run))
    ids = {}
    for name, b in recorded.items():
        ids[name] = conn.execute(
            "INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (file_id, run, b["page_no"], b["type"], b["text"])).fetchone()[0]
    return conn, ids


def leg1(conn, query, block_id):
    return conn.execute(LEG1, (query, block_id)).fetchone()[0]


# ── (i) the recall the repair exists for ──────────────────────────────────────────────────

@pg_only
@pytest.mark.parametrize("name, query", [
    ("floating", "floating point"),          # <0x1d>oating — the word-initial case
    ("conflict-ff", "covariate effects"),    # e<0x01>ects  — 0x01 as ff
    ("conflict-fi", "infinitely long"),      # in<0x01>nitely — 0x01 as fi, SAME FILE
    ("conflict-fi", "misclassification"),    # misclassi<0x01>cation, the P8 referee's Q3 word
])
def test_a_ligature_eaten_by_the_extractor_is_still_found(loaded, name, query):
    """The query is spelled the way a reader spells it; the block is spelled the way the PDF's text
    layer mangled it. Leg 1 must join them."""
    conn, ids = loaded
    assert leg1(conn, query, ids[name]), f"{query!r} did not reach the recorded block {name}"


@pg_only
def test_a_fixed_byte_table_cannot_repair_both(loaded, recorded):
    """Why 0025 expands instead of mapping. `replace(text, chr(1), 'fi')` is the measured MAJORITY
    for byte 0x01 (Reports/litkb_ligature_c0_2026-09-19.csv) and therefore the best a fixed table
    could do. In one file it recovers `infinitely` and silently fails `effects`; the expansion
    recovers both."""
    conn, ids = loaded
    table = ("SELECT to_tsvector('english', litkb.norm_search_text(replace(b.text, chr(1), 'fi'))) "
             "       @@ plainto_tsquery('english', litkb.norm_search_text(%s)) "
             "  FROM litkb.blocks b WHERE b.id = %s")
    assert conn.execute(table, ("infinitely long", ids["conflict-fi"])).fetchone()[0]
    assert not conn.execute(table, ("covariate effects", ids["conflict-ff"])).fetchone()[0]
    assert leg1(conn, "infinitely long", ids["conflict-fi"])
    assert leg1(conn, "covariate effects", ids["conflict-ff"])


# ── (ii) the property option (c) was chosen for ───────────────────────────────────────────

@pg_only
def test_the_stored_text_is_the_recorded_text_byte_for_byte(loaded, recorded):
    """0025 repairs RETRIEVAL. The row still holds what the PDF said, control bytes included, which
    is what keeps a recorded quote verifiable against it (decisions.yaml litkb-ligature-repair)."""
    conn, ids = loaded
    for name, b in recorded.items():
        stored = conn.execute("SELECT text FROM litkb.blocks WHERE id = %s", (ids[name],)).fetchone()[0]
        assert hashlib.sha256(stored.encode("utf-8")).hexdigest() == b["sha256"]
    damaged = {n: conn.execute("SELECT text FROM litkb.blocks WHERE id = %s", (ids[n],)).fetchone()[0]
               for n in ("conflict-ff", "conflict-fi", "floating")}
    for name, stored in damaged.items():
        assert chr(1) in stored or chr(29) in stored, f"{name}: the recorded damage IS the fixture"


@pg_only
def test_the_new_normalisation_only_adds(loaded, recorded):
    """Additive by construction: the match is re-emitted unchanged before the expansions, so every
    lexeme the pre-0025 normalisation produced is still produced. Checked here against 0018's body
    spelled out, so the property is tested rather than trusted."""
    conn, _ids = loaded
    old = ("regexp_replace(regexp_replace(translate(coalesce(%s, ''), chr(65533) || chr(173), ''), "
           "'-[ \t\r\n]+', '', 'g'), '[ \t\r\n]+', ' ', 'g')")
    for name, b in recorded.items():
        missing = conn.execute(
            f"SELECT tsvector_to_array(to_tsvector('english', {old})) "
            f"       <@ tsvector_to_array(to_tsvector('english', litkb.norm_search_text(%s)))",
            (b["text"], b["text"])).fetchone()[0]
        assert missing, f"{name}: 0025 dropped a lexeme 0018 produced"


# ── (iii) the over-matching kill ──────────────────────────────────────────────────────────

@pg_only
@pytest.mark.parametrize("name, query", [
    ("floating", "parachute deployment"),   # a genuinely different subject
    ("conflict-ff", "photosynthesis"),      # a genuinely different word
    ("floating", "gloating"),               # one letter from the repaired word
    ("conflict-fi", "fix"),                 # the one-letter trap: <0x05>x would spell this
])
def test_the_normaliser_does_not_manufacture_a_match(loaded, name, query):
    """Expansion adds five spellings of ONE word, not a wildcard. A query that shares no word with
    the block must still miss it — otherwise the recall above is bought with noise."""
    conn, ids = loaded
    assert not leg1(conn, query, ids[name]), f"{query!r} should not match the recorded block {name}"


@pg_only
def test_a_query_with_no_control_byte_is_left_alone(litkb_pg_base):
    """The normaliser runs on both sides of every comparison, so a clean query must come out of it
    unchanged but for the whitespace collapse 0018 already did."""
    _psycopg, conn, _ran = litkb_pg_base
    for q in ("floating point", "multi-state Markov model", "Robust Statistics"):
        assert conn.execute("SELECT litkb.norm_search_text(%s)", (q,)).fetchone()[0] == q


@pg_only
def test_line_break_hyphenation_is_still_joined(loaded):
    """De-hyphenation is 0018's, carried through unchanged: decisions.yaml litkb-ligature-repair
    folds it into "the same normalisation pass", and the measurement says it was already there.
    Driven on a fourth recorded block — 01a0abc8-4a18-7ca5-88e5-6dac9bf744f0 reads `abund- ant`
    across a line break, one of 211 current-run blocks with that shape on 2026-09-19."""
    conn, ids = loaded
    assert leg1(conn, "abundant", ids["hyphenated"]), "0018's de-hyphenation must still join it"


@pg_only
@pytest.mark.xfail(strict=True, reason="0025 covers a C0 byte FOLLOWED BY LETTERS; this is a C1 "
                                       "byte with a space after it, and no expansion can bridge "
                                       "the space. Out of scope, recorded so the gap is visible.")
def test_a_c1_byte_with_a_space_is_a_different_defect(loaded):
    """The same recorded block reads `di<0x81> culties` a few words after `abund- ant`. The word a
    reader types is `difficulties`, and nothing in 0025 can reach it: the damage is a C1 byte
    (0x80-0x9f, outside this rule's class) AND a space where the rest of the word should continue.
    Written as a STRICT xfail so that whoever fixes it sees an XPASS and has to update this test,
    rather than a silently absent assertion."""
    conn, ids = loaded
    assert leg1(conn, "abundant difficulties", ids["hyphenated"])

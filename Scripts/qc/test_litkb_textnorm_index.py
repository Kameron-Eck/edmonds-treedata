r"""litkb 0025 — the index-only ligature repair, driven on REAL corpus text.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w2 py -3.12 -m pytest qc/test_litkb_textnorm_index.py

WHAT THESE TESTS RUN ON. `qc/testdata/litkb_textnorm/real_blocks.json` holds six blocks copied
VERBATIM out of the corpus — block id, file id, run id, page, type, sha256 and the text exactly as
the extractor wrote it, control bytes and all (they appear in the JSON as \u0001 / \u001d escapes,
so no control byte is typed into a tracked file). They are not invented strings, and the rule they
exercise was derived from the whole corpus, not from them (CLAUDE.md 3.4c):

  conflict-ff  01a0abc7-429d-7a0d-b7fb-252dab0c32ec  'Modelling covariate e<0x01>ects'  -> ff
  conflict-fi  01a0abc7-42ad-7050-b607-63aacd8a50c8  'in<0x01>nitely long'              -> fi
  floating     01a0ad5b-1765-7e08-89cc-5342a879f416  '<0x1d>oating point'               -> fl
  hyphenated   01a0abc8-4a18-7ca5-88e5-6dac9bf744f0  'abund- ant', and `di<0x81> culties`
  numword-tail 01a0aba2-3d3b-750c-8abb-90b1d39e8f95  'u<0x05>L1(BR(0))'   — the token `L1`
  initial-tail 01a0abc6-d87b-7dc6-b50e-8d1f421020ee  '; <0x05>DwR2\n=OÞ'  — the token `DwR2`

The last two are the ADDITIVITY casualties. The first version of migration 0025 (d6a0a29) wrote the
alternative spellings INTO the text beside the damaged word; the match ended at the last LETTER and
the space it inserted there cut `L1` and `DwR2` in half — a lexeme the PRE-0025 index had is gone,
and a manufactured one (`uffll1`) is in. 570 of 372,192 blocks lost 809 lexemes that way and `L1`
fell from 297 to 280 visible leg-1 hits (audit 2026-09-20, item 6). 0025 now prepends the spellings
and never writes into the text at all, so the pre-0025 string is a literal suffix of the new one.
These two blocks put that property in the LADDER; the corpus-wide count (0 of 372,192) and the
rejected rules it is measured against are qc/instruments/litkb_norm_additivity.py, which cannot run
here because it needs a restore of the dump.

The first two are the SAME FILE and the SAME BYTE resolving to two different ligatures, which is why
migration 0025 carries no byte->ligature table: `test_a_fixed_byte_table_cannot_repair_both` is that
argument executed rather than asserted.

Each test inserts the recorded text into `litkb.blocks` on the worker database the suite already
resets and migrates (qc/conftest.py `litkb_pg_base`), so leg 1 of litkb_search runs against a real
row through the real expression index, not against a string literal in a SELECT.

The full-corpus half of the proof — 372,192 blocks, the md5 of every block's text and the
quote_verified set identical across the migration, and the index rebuild timings — is
`qc/instruments/litkb_norm_index_proof.py`, which cannot run inside the ladder because it needs a
restore of the nightly dump. Its numbers are in Reports/litkb_norm_index_proof_2026-09-20.csv.

The INDEX-VS-FUNCTION agreement check runs in both places and they see different things. The
instrument compares COUNTS on the real corpus; `test_the_expression_indexes_agree_with_the_function`
below compares ID SETS on these six blocks, and its docstring says plainly what a from-scratch test
database makes invisible to it.
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
#: leg 2 of litkb_search (`_SEARCH_BLOCKS_ANY`): the any-term leg, same normaliser, 0018's
#: any_term_query instead of plainto_tsquery. A lexeme destroyed by the normaliser is lost to BOTH,
#: which is why the additivity rows below check both rather than leg 1 alone.
LEG2 = ("SELECT to_tsvector('english', litkb.norm_search_text(b.text)) "
        "       @@ litkb.any_term_query(%s) "
        "  FROM litkb.blocks b WHERE b.id = %s")

#: The same two predicates written WITHOUT a block id, so the planner can serve them from the
#: expression indexes 0025 rebuilds — which is the only way to see what those indexes hold. The
#: first reads blocks_norm_text_fts, the second leg 3's blocks_norm_text_trgm.
IDS_FTS = ("SELECT b.id FROM litkb.blocks b "
           " WHERE to_tsvector('english', litkb.norm_search_text(b.text)) "
           "       @@ plainto_tsquery('english', litkb.norm_search_text(%s))")
IDS_TRGM = ("SELECT b.id FROM litkb.blocks b "
            " WHERE litkb.norm_search_text(b.text) %% litkb.norm_search_text(%s)")

#: The five probes qc/instruments/litkb_norm_index_proof.py runs at corpus scale as a COUNT
#: comparison, run here as an ID-SET comparison. `matches_here` is measured, not assumed
#: (2026-09-20, litkb_test_w2, the six recorded blocks): four of the five return exactly one block
#: and trgm `misclassification` returns none — that row compares two EMPTY sets and can therefore
#: only check that the plan reached the index, which is why it is flagged rather than dropped.
INDEX_PROBES = [
    ("fts", "blocks_norm_text_fts", IDS_FTS, "misclassification", True),
    ("fts", "blocks_norm_text_fts", IDS_FTS, "covariate effects", True),
    ("fts", "blocks_norm_text_fts", IDS_FTS, "floating point", True),
    ("trgm", "blocks_norm_text_trgm", IDS_TRGM, "misclassification", False),
    ("trgm", "blocks_norm_text_trgm", IDS_TRGM, "covariate effects", True),
]


@pytest.fixture(scope="module")
def recorded():
    """Every recorded block, each re-hashed against the sha256 the capture wrote."""
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


def leg2(conn, query, block_id):
    return conn.execute(LEG2, (query, block_id)).fetchone()[0]


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
@pytest.mark.parametrize("name, token", [
    ("numword-tail", "L1"),        # `u<0x05>L1(BR(0))` — a C0 byte with a NUMWORD after it
    ("initial-tail", "DwR2"),      # `; <0x05>DwR2` — a word-initial byte, same numword tail
])
def test_a_token_beside_the_damage_is_not_destroyed(loaded, name, token):
    """The audit's defect, executed. `L1` is a norm, not noise: it was reachable through the
    pre-0025 index and the first version of this rule made it unreachable, because it substituted
    the spellings into the text and the space it inserted cut the token at the letter `L`. Both
    lexical legs lose the token when that happens, so both are asserted. What makes it impossible
    now is that nothing is substituted: the spellings are prepended as their own run and 0018's
    output follows unchanged, so the old string is a literal suffix of the new one."""
    conn, ids = loaded
    assert leg1(conn, token, ids[name]), f"{token!r} no longer reaches {name} on leg 1"
    assert leg2(conn, token, ids[name]), f"{token!r} no longer reaches {name} on leg 2"


@pg_only
def test_the_new_normalisation_only_adds(loaded, recorded):
    """0018's output is carried through byte for byte and the spellings are prepended, so every
    lexeme the pre-0025 normalisation produced is still produced. Checked here against 0018's body
    spelled out, so the property is tested rather than trusted — over every recorded block,
    including the two the first version of the rule broke.

    NOT "by construction", which this docstring said until 2026-09-20. The argument — nothing is
    inserted into the old string, so no token of it can be disturbed — does not hold on its own,
    because this parser's tokens can absorb the whitespace in FRONT of them and the prepended run
    ends in a space. What carries the claim is measurement: six blocks here, and 0 of 372,192 plus
    a byte-suffix check on 372,192/372,192 in qc/instruments/litkb_norm_additivity.py."""
    conn, _ids = loaded
    old = ("regexp_replace(regexp_replace(translate(coalesce(%s, ''), chr(65533) || chr(173), ''), "
           "'-[ \t\r\n]+', '', 'g'), '[ \t\r\n]+', ' ', 'g')")
    for name, b in recorded.items():
        missing = conn.execute(
            f"SELECT tsvector_to_array(to_tsvector('english', {old})) "
            f"       <@ tsvector_to_array(to_tsvector('english', litkb.norm_search_text(%s)))",
            (b["text"], b["text"])).fetchone()[0]
        assert missing, f"{name}: 0025 dropped a lexeme 0018 produced"


@pg_only
@pytest.mark.parametrize("leg, index, sql, query, matches_here", INDEX_PROBES,
                         ids=[f"{leg}-{q}" for leg, _i, _s, q, _m in INDEX_PROBES])
def test_the_expression_indexes_agree_with_the_function(loaded, leg, index, sql, query,
                                                        matches_here):
    """What the expression index HOLDS must equal what the function COMPUTES, as a row set.

    0025 replaces litkb.norm_search_text and rebuilds both of 0018's expression indexes. If a
    rebuild did not see the new body, every leg of litkb_search would silently read pre-0025
    entries, the repair would look like it had not worked, and nothing else in this file would
    notice: every other test here fetches one block by primary key, which never touches these
    indexes. On 2026-09-20 an fts index in that state answered `misclassification` on 722 blocks
    while the function answered 906 — seen once, on the builder's database, and never reproduced.

    Two separate assertions, so a red says which half broke:
      (1) under `enable_seqscan = off` the plan really reaches `index` — this is what goes red if
          the migration drops an index and does not recreate it, or builds it on an expression the
          planner cannot match to the query;
      (2) the ids that plan returns equal the ids returned with index and bitmap scans disabled.
    Ids, not counts: two different sets of 906 pass a count comparison, and the corpus-scale
    instrument only compares counts.

    WHAT THIS ROW CANNOT SEE, and it is most of what the migration's DDL argument is about. The
    suite resets and re-migrates from 0001, so litkb.blocks is EMPTY while 0025 runs and every block
    below is inserted AFTERWARDS — an index entry is computed from whatever body norm_search_text
    has at INSERT time, which here is always the current one. A stale index therefore cannot arise
    in this database at all, and whether 0025 rebuilds the indexes is invisible to the ladder.
    Measured in a scratch clone on 2026-09-20, all three against a baseline of 20 passed, 1 xfailed:

      (c) 0025's whole DROP+CREATE block deleted     20 passed, 1 xfailed — DID NOT FIRE.
          The brief that asked for this row expected this mutation to be the demonstration; it is
          not one, and that is the finding: only qc/instruments/litkb_norm_index_proof.py, on a
          restore with 372,192 pre-existing rows, can see the rebuild happen or not happen.
      (a) `CREATE INDEX blocks_norm_text_fts` deleted from 0025, the DROP kept
          3 failed (the three fts rows), 17 passed — assertion (1), "the plan never reached
          blocks_norm_text_fts". A shipped-code mutation, and nothing else in this file noticed:
          every other test here fetches by primary key.
      (b) the injected defect state, in a clone of the `loaded` fixture — insert the rows, re-point
          norm_search_text at 0018's body, REINDEX both indexes under it, restore 0025's body with
          no rebuild. That is the 722 event's shape exactly.
          3 failed (the three fts rows), 17 passed — assertion (2), e.g. `floating point`: index
          [], sequential scan [01a0be82-…]. A stale index gives FALSE NEGATIVES only, because the
          bitmap heap scan rechecks the qual with the current body.

    So: assertion (1) has been shown to fire on shipped code, assertion (2) only on an injected
    state. Both trgm rows stayed GREEN under (b), so the trigram half of this check has never been
    shown to fire and is not known to work. (INFERRED, not measured: trigram entries built from
    0018's output are probably still similar enough to the query to match. Nobody scored that.)
    The live cutover's index is still the operator's job, with
    qc/instruments/litkb_norm_index_proof.py on a restore of the dump.

    THESE ROWS ARE NOT INDEPENDENT OF THE RECALL ROWS ABOVE, which matters when reading a red. The
    `matches_here` assertion also goes red when a probe stops matching anything at all, so the
    X13a-X13d mutation rows (qc/instruments/litkb_p2_mutations.py) now take 6/2/4/8 tests red
    instead of 4/1/3/6. Measured on X13b, 2026-09-20: `[fts-floating point]` fails on
    "matched no recorded block", NOT on a disagreement between the index and the function. A red
    here means one of three different things and the message says which.
    """
    conn, _ids = loaded
    with conn.transaction():
        conn.execute("SET LOCAL enable_seqscan = off")
        plan = "\n".join(r[0] for r in conn.execute("EXPLAIN (COSTS OFF) " + sql, (query,)))
        assert index in plan, f"{leg} {query!r}: the plan never reached {index}:\n{plan}"
        served = sorted(str(r[0]) for r in conn.execute(sql, (query,)))
    with conn.transaction():
        conn.execute("SET LOCAL enable_indexscan = off")
        conn.execute("SET LOCAL enable_bitmapscan = off")
        plan = "\n".join(r[0] for r in conn.execute("EXPLAIN (COSTS OFF) " + sql, (query,)))
        assert "Seq Scan" in plan, f"{leg} {query!r}: this branch must NOT use an index:\n{plan}"
        scanned = sorted(str(r[0]) for r in conn.execute(sql, (query,)))
    assert served == scanned, (f"{index} disagrees with litkb.norm_search_text on {query!r}: "
                               f"index {served}, sequential scan {scanned}")
    if matches_here:
        assert served, (f"{leg} {query!r} matched no recorded block, so this row compared two "
                        "empty sets — it is no longer checking anything")


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

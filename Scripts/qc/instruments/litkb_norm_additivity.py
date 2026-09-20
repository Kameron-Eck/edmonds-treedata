r"""Migration 0025's ADDITIVITY, measured on every block of the corpus rather than claimed.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w2 \
        py -3.12 qc/instruments/litkb_norm_additivity.py
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w2 \
        py -3.12 qc/instruments/litkb_norm_additivity.py --mutate    # show the gate fire, twice

WHY THIS EXISTS. The first version of 0025 (d6a0a29) stated in two places — the header and the
`COMMENT ON FUNCTION` — that "every lexeme the old function produced is still produced … so no
match on leg 1 or leg 2 can be lost", and offered as evidence "0 of the first 3,000 blocks by scan
order". `LIMIT 3000` with no `ORDER BY` is not a reproducible sample, and the claim was FALSE: the
2026-09-20 audit measured 570 of 372,192 blocks losing 809 lexemes, `L1` falling from 297 to 280
visible leg-1 hits, and the mechanism — the rule wrote the alternative spellings INTO the text
beside the damaged word, the match ended at the last LETTER, and the space it inserted there cut
`u<0x05>L1(BR(0))` in half, destroying the lexeme `l1` and manufacturing `uffll1`.

The obvious repair — carry the match out to the end of the whitespace-delimited run, so the
inserted space can only land where a space already was — was built and measured here too. It gets
570 down to 78 and NOT to 0, because in this database a lexeme can contain a space: `english` over
a UTF-8 corpus with the libc collation `English_United States.1252` turns blocks of mixed-script
equation mojibake into lexemes like `'1 ψ a'` and `'∑ n i'`. Inserting the harmless string ` zzz`
at the same offset loses the same lexemes, so the residual is the parser, not the rule, and no
insertion point inside such a block is safe.

0025 therefore does not write into the text at all: it PREPENDS the spellings as their own run and
carries 0018's output through byte for byte, which makes the old string a literal suffix of the new
one. This instrument is the measurement that says so, and the three-way `--mutate` table is what
makes the number a gate rather than a hope.

WHAT IT COMPARES. Not a reconstruction of the pre-0025 normaliser — the DATABASE's own. Before the
migration is applied it reads `pg_get_functiondef` of the live `litkb.norm_search_text` and installs
that exact body under the name `litkb.audit_norm_pre0025`. Whatever 0018 is running here is what the
"before" column measures.

WHAT --mutate DOES. Installs each REJECTED rule in turn inside a transaction, rescans, and rolls
back. A gate that has never been shown to fire is not known to work (CLAUDE.md 3.4c): the 570 and
the 78 in 0025's header come from this run, not from prose. The two bodies are written out in full
below rather than patched out of the current one, so what is scored is a rule someone can read.
No REINDEX is involved anywhere here — every number is computed as `to_tsvector(norm(text))`
directly on the rows, never read through the expression index, so a mutation costs a scan and
nothing else. The REINDEX timings live in qc/instruments/litkb_norm_index_proof.py.

IT RUNS ON A RESTORE OF THE NIGHTLY DUMP, in a worker database, never on live litkb:

    psql -w -h localhost -p 5433 -U postgres -d litkb_test_w2 \
      -c "DROP SCHEMA IF EXISTS litkb CASCADE; DROP SCHEMA IF EXISTS litkb_meta CASCADE;
          CREATE SCHEMA litkb AUTHORIZATION litkb_test; CREATE SCHEMA litkb_meta AUTHORIZATION litkb_test;"
    pg_restore -w -h localhost -p 5433 -U postgres -d litkb_test_w2 --no-owner --no-tablespaces \
      --role=litkb_test --schema=litkb --schema=litkb_meta \
      D:\edmonds-pipeline\pgdump\litkb\litkb_20260919T093002Z.dump

The CREATE SCHEMA line is not optional: the schema-filtered dump carries no `CREATE SCHEMA`, so a
restore into a worker DB whose litkb schema has been dropped fails without it.

Output: Reports/litkb_norm_additivity_2026-09-20.csv and the stdout below.
"""
import csv
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS.parent / "Reports" / "litkb_norm_additivity_2026-09-20.csv"

C0 = "chr(1) || '-' || chr(8) || chr(11) || chr(12) || chr(14) || '-' || chr(31)"

#: The rejected rule, in full: the spellings written INTO the text beside the damaged word. @TAIL@
#: is what distinguishes the two versions — empty is d6a0a29 (the match ends at the last letter),
#: `[^ \t\r\n]*` carries it to the end of the whitespace-delimited run. Everything else is identical
#: to what d6a0a29 committed, so a reader can check this against that commit line for line.
_INLINE = r"""
CREATE OR REPLACE FUNCTION litkb.norm_search_text(p_text text) RETURNS text
LANGUAGE sql IMMUTABLE AS $m$
  SELECT regexp_replace(
           regexp_replace(
             regexp_replace(
               regexp_replace(
                 translate(coalesce(p_text, ''), chr(65533) || chr(173), ''),
                 '-[ \t\r\n]+', '', 'g'),
               '([A-Za-z]+)[' || k.c0 || ']([A-Za-z]+)@TAIL@',
               '\& \1\2 \1ff\2 \1fi\2 \1fl\2 \1ffi\2 \1ffl\2', 'g'),
             '(^|[^A-Za-z])[' || k.c0 || ']([A-Za-z]{2,})@TAIL@',
             '\& \2 ff\2 fi\2 fl\2 ffi\2 ffl\2', 'g'),
           '[ \t\r\n]+', ' ', 'g')
    FROM (SELECT @C0@ AS c0) k
$m$
"""


def _inline(tail):
    return _INLINE.replace("@TAIL@", tail).replace("@C0@", C0)


REJECTED = [("d6a0a29: spellings written in, match ends at the last letter", _inline("")),
            ("same, match carried to the end of the whitespace run", _inline(r"[^ \t\r\n]*"))]

#: ONE pass over every block, materialised: the pre-0025 lexemes, the post-0025 lexemes and both
#: normalised lengths. `OFFSET 0` is an optimisation fence — without it the planner inlines the
#: subquery and calls each normaliser twice per row. Everything else here is an aggregate over this
#: table, so the expensive work (the regexp pipelines and two to_tsvector calls per block) is done
#: exactly once per stage rather than once per question.
SNAPSHOT = """
DROP TABLE IF EXISTS cmp;
CREATE TEMP TABLE cmp AS
  SELECT tsvector_to_array(to_tsvector('english', s.o)) AS ov,
         tsvector_to_array(to_tsvector('english', s.n)) AS nv,
         length(s.o) AS lo, length(s.n) AS ln
    FROM (SELECT litkb.audit_norm_pre0025(b.text) AS o, litkb.norm_search_text(b.text) AS n
            FROM litkb.blocks b OFFSET 0) s
"""
#: old ⊆ new, per block. `<@` on the lexeme arrays: every lexeme the pre-0025 function produced is
#: still produced. The population is EVERY block — no sampling, no LIMIT. The per-lexeme count is
#: wrapped in a CASE so the O(n·m) membership scan runs only on the blocks that actually lost one.
AGG = """
SELECT count(*), count(*) FILTER (WHERE NOT (ov <@ nv)),
       coalesce(sum(CASE WHEN ov <@ nv THEN 0 ELSE
                 (SELECT count(*) FROM unnest(ov) x WHERE NOT x = ANY(nv)) END), 0),
       sum(lo)::bigint, sum(ln)::bigint
  FROM cmp
"""

#: The audit's named casualties, by FULL id: block, the token that must survive, what damaged it.
#: Full ids and not the audit's prefixes — `01a0abb4-5276` and `01a0abc6-d87b` each name more than
#: one block in this corpus, and a LIKE prefix silently probes whichever the scan returns first.
PROBE_BLOCKS = [("01a0aba2-3d3b-750c-8abb-90b1d39e8f95", "L1", "mid-word byte, numword tail"),
                ("01a0abcb-2c40-724e-bb16-cdd3461a01ca", "Tv2c", "mid-word byte, numword tail"),
                ("01a0abb4-5276-7b7f-ac48-f6a9a290074b", "k2", "mid-word byte, numword tail"),
                ("01a0abc6-d87b-7dc6-b50e-8d1f421020ee", "DwR2", "word-initial byte, numword tail")]
#: corpus-wide and VISIBLE hit counts for the same tokens. Visible = what litkb_search can reach.
PROBE_QUERIES = ["L1", "k2", "misclassification", "covariate effects"]
#: the two the rejected rules are scored on as well: one the repair is FOR, one it must not lose
RECALL_QUERIES = ["misclassification", "L1"]


def _visible_sql(fn):
    """Leg 1's matching clause under the tool's own visibility joins, read from server.py rather
    than copied: `_BLOCK_FROM` is the files -> main_files -> main_works chain that decides which
    blocks litkb_search can see at all, and DEFAULT_KINDS is the furniture filter."""
    from litkb.mcp.server import _BLOCK_FROM
    return ("SELECT count(*) " + _BLOCK_FROM +
            f"   AND to_tsvector('english', litkb.{fn}(b.text))"
            f"       @@ plainto_tsquery('english', litkb.{fn}(%(q)s))")


def _scan(conn):
    """(blocks, blocks losing >=1 lexeme, lexemes lost, old chars, new chars, seconds) — one pass
    against whatever litkb.norm_search_text currently is."""
    t0 = time.time()
    conn.execute(SNAPSHOT)
    row = conn.execute(AGG).fetchone()
    return (*row, time.time() - t0)


def main(argv):
    mutate = "--mutate" in argv
    from litkb.db import connect as c
    from litkb.db import migrate
    from litkb.mcp.server import DEFAULT_KINDS, _BLOCK_FROM

    db = c.DB_TEST
    # BEGIN guard: the additivity scan runs on a worker database, never on live litkb
    if not c.is_test_db(db) or db == c.DB_MAIN:
        raise SystemExit(f"refusing: {db} is not a worker/test database (set LITKB_TEST_DB)")
    # END guard: the additivity scan runs on a worker database, never on live litkb
    conn = c.connect(db, "litkb_test", autocommit=True)
    # the corpus has words past the parser's 2047-character limit; its NOTICE is per row and drowns
    # everything this prints. The limit is not this migration's business either way.
    conn.execute("SET client_min_messages = warning")
    # EVERY number below is computed from the FUNCTION, never read through an expression index.
    # That is not tidiness: on 2026-09-20 an index rebuilt inside migrate.apply() answered
    # `misclassification` on 722 blocks while the function answered 906, and a recall number taken
    # through it would have been a fact about a stale index. Whether the index agrees with the
    # function is a separate question with its own instrument (litkb_norm_index_proof.py).
    conn.execute("SET enable_indexscan = off; SET enable_bitmapscan = off; "
                 "SET enable_indexonlyscan = off")
    print(f"database: {db} ({conn.execute('SELECT current_database()').fetchone()[0]})")
    coll = conn.execute("SELECT datcollate, datctype FROM pg_database "
                        "WHERE datname = current_database()").fetchone()
    print(f"collation / ctype: {coll[0]} / {coll[1]}")

    applied = {v for (v,) in conn.execute(
        "SELECT version FROM litkb_meta.schema_migrations").fetchall()}
    if 25 in applied:
        raise SystemExit("0025 is already applied here; restore the dump again for a before/after")
    n_blocks = conn.execute("SELECT count(*) FROM litkb.blocks").fetchone()[0]
    print(f"migrations applied before: {max(applied)} ({len(applied)} recorded); "
          f"blocks: {n_blocks}")

    # the pre-0025 normaliser, taken from the database rather than rewritten
    src = conn.execute("SELECT pg_get_functiondef('litkb.norm_search_text(text)'::regprocedure)"
                       ).fetchone()[0]
    pre = src.replace("litkb.norm_search_text", "litkb.audit_norm_pre0025", 1)
    assert "audit_norm_pre0025" in pre and pre.count("norm_search_text") == 0, pre[:200]
    conn.execute(pre)
    print("installed litkb.audit_norm_pre0025 from pg_get_functiondef(norm_search_text)")

    kinds = {"kinds": list(DEFAULT_KINDS)}
    vis_total = conn.execute("SELECT count(*) " + _BLOCK_FROM, kinds).fetchone()[0]
    print(f"blocks visible to litkb_search (DEFAULT_KINDS + main_files/main_works): {vis_total}")

    rows = []

    def probe(stage, fn):
        for bid, token, why in PROBE_BLOCKS:
            got = conn.execute(
                f"SELECT to_tsvector('english', litkb.{fn}(b.text)) "
                f"       @@ plainto_tsquery('english', litkb.{fn}(%s)),"
                f"       to_tsvector('english', litkb.{fn}(b.text)) @@ litkb.any_term_query(%s) "
                f"  FROM litkb.blocks b WHERE b.id = %s",
                (token, token, bid)).fetchone()
            assert got is not None, f"{bid} is not in this corpus"
            rows.append(dict(stage=stage, metric="block_probe", subject=f"{bid[:13]} {token}",
                             value=f"leg1={got[0]} leg2={got[1]}", note=why))
            print(f"  {stage:9} block {bid[:13]} {token!r:8} leg1={got[0]} leg2={got[1]}  ({why})")
        for q in PROBE_QUERIES:
            all_n = conn.execute(
                f"SELECT count(*) FROM litkb.blocks b WHERE to_tsvector('english', litkb.{fn}(b.text))"
                f" @@ plainto_tsquery('english', litkb.{fn}(%s))", (q,)).fetchone()[0]
            vis_n = conn.execute(_visible_sql(fn), {**kinds, "q": q}).fetchone()[0]
            rows.append(dict(stage=stage, metric="leg1_hits", subject=q,
                             value=f"corpus={all_n} visible={vis_n}", note=""))
            print(f"  {stage:9} leg1 {q!r:26} corpus={all_n:6} visible={vis_n}")

    probe("before", "audit_norm_pre0025")

    t0 = time.time()
    ran = migrate.apply(conn)
    print(f"migration applied: {ran} in {time.time() - t0:.1f}s (includes both index rebuilds)")

    seen, lost_b, lost_l, old_chars, new_chars, scan = _scan(conn)
    assert seen == n_blocks, f"scanned {seen} of {n_blocks} blocks"
    growth = 100.0 * (new_chars - old_chars) / old_chars
    print(f"ADDITIVITY, full scan of all {n_blocks} blocks, no sampling ({scan:.0f}s):")
    print(f"  blocks losing >=1 lexeme: {lost_b}   lexemes lost: {lost_l}")
    print(f"  normalised text: {old_chars} -> {new_chars} chars ({growth:+.2f}%)")
    rows += [dict(stage="after", metric="blocks_losing_a_lexeme", subject=f"all {n_blocks} blocks",
                  value=lost_b, note="must be 0"),
             dict(stage="after", metric="lexemes_lost", subject=f"all {n_blocks} blocks",
                  value=lost_l, note="must be 0"),
             dict(stage="after", metric="norm_text_chars", subject="old -> new",
                  value=f"{old_chars} -> {new_chars}", note=f"{growth:+.2f}%")]
    probe("after", "norm_search_text")

    fired = []
    if mutate:
        for why, body in REJECTED:
            # BEGIN guard: a rejected rule is scored inside a transaction and rolled back
            conn.execute("BEGIN")
            try:
                conn.execute(body)
                installed = conn.execute(
                    "SELECT pg_get_functiondef('litkb.norm_search_text(text)'::regprocedure)"
                ).fetchone()[0]
                assert "regexp_replace" in installed and "string_agg" not in installed, \
                    "the rejected body did not replace the function; the mutation did nothing"
                _, mb, ml, _, _, msecs = _scan(conn)
                fired.append((why, mb, ml))
                print(f"MUTATION  {why}\n          blocks losing >=1 lexeme: {mb}   "
                      f"lexemes lost: {ml}  ({msecs:.0f}s)")
                # What each rejected rule COSTS in recall, measured under the same seq-scan rule as
                # every other number here. This is the row that decides whether the inline design
                # lost hits or only lost lexemes — it must not be read through an index.
                for q in RECALL_QUERIES:
                    n = conn.execute(_visible_sql("norm_search_text"),
                                     {**kinds, "q": q}).fetchone()[0]
                    rows.append(dict(stage="mutated", metric="leg1_hits_visible", subject=q,
                                     value=n, note=why))
                    print(f"          leg1 visible {q!r:22} {n}")
            finally:
                conn.execute("ROLLBACK")
            # END guard: a rejected rule is scored inside a transaction and rolled back
            rows.append(dict(stage="mutated", metric="blocks_losing_a_lexeme", subject=why,
                             value=mb, note=f"{ml} lexemes — the gate firing"))
        back_b = _scan(conn)[1]
        print(f"rolled back; blocks losing a lexeme under 0025 again: {back_b}")
        rows.append(dict(stage="restored", metric="blocks_losing_a_lexeme", subject="after ROLLBACK",
                         value=back_b, note="must be 0 again"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["stage", "metric", "subject", "value", "note"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT}")
    conn.close()
    ok = lost_b == 0 and lost_l == 0
    if mutate:
        ok = ok and back_b == 0 and all(mb > 0 for _w, mb, _l in fired) and len(fired) == 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

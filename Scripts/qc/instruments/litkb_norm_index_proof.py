r"""Migration 0025's proof on the REAL corpus: the index-only ligature repair works, and it does
not touch a single stored byte.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w2 \
        py -3.12 qc/instruments/litkb_norm_index_proof.py

It runs ONLY against a worker database (`connect.is_test_db`, checked below and refused otherwise).
The corpus it measures is a restore of the nightly dump of live litkb into that worker database:

    pg_restore -w -h localhost -p 5433 -U postgres -d litkb_test_w2 --no-owner --no-tablespaces \
        --role=litkb_test --schema=litkb --schema=litkb_meta \
        D:\edmonds-pipeline\pgdump\litkb\litkb_20260919T093002Z.dump

so every block, every extraction run and every use_evidence row below is the real thing, verbatim.
The `--schema` flags are not cosmetic: a whole-dump restore stops on `COMMENT ON EXTENSION
fuzzystrmatch` (the restoring role does not own the extensions the worker DB was provisioned with).

What it establishes, in the order the launch delta asks for them:

  (i)   RECALL. The three demonstration blocks are real current-run blocks. Leg 1 of litkb_search
        (`to_tsvector('english', norm(text)) @@ plainto_tsquery('english', norm(q))`, server.py
        _SEARCH_BLOCKS_ALL) is run verbatim as a predicate on each one, before and after. Two of the
        three carry byte 0x01 in the SAME file and expand to DIFFERENT ligatures, so the run also
        scores the counterfactual a byte table would give: `replace(text, chr(1), 'fi')`, the
        measured 0x01 majority, which recovers one of them and fails the other.

  (ii)  BYTES UNTOUCHED. md5 of `string_agg(text, '' ORDER BY id)` over litkb.blocks, the block
        count, the count of use_evidence rows with quote_verified, and the md5 of their id set, all
        taken before and after the migration. Identical means the repair changed no byte any
        recorded quote points at — which is the whole reason option (c) was chosen over (b).

  (iii) NO OVER-MATCHING. Queries that must NOT match: a genuinely different word, and the
        neighbouring-word trap `fix` (a one-letter neighbourhood like `<0x05>x` — a minus sign, not
        a ligature — would spell it if the rule had no two-letter floor).

Output: Reports/litkb_norm_index_proof_2026-09-20.csv plus the stdout below. Nothing is written to
live litkb, and nothing at all is written to litkb.blocks.
"""
import csv
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS.parent / "Reports" / "litkb_norm_index_proof_2026-09-20.csv"

#: Real current-run blocks, named by id. The first two are the measured same-file, same-byte
#: conflict (file 01a0a4d6-6db4-7343-965a-aca7b3c090d4, byte 0x01); the third is the delta's own
#: `floating point` case (byte 0x1d), in a different file.
CASES = [
    ("conflict-ff", "01a0abc7-429d-7a0d-b7fb-252dab0c32ec", "covariate effects", True),
    ("conflict-fi", "01a0abc7-42ad-7050-b607-63aacd8a50c8", "infinitely long", True),
    ("floating", "01a0ad5b-1765-7e08-89cc-5342a879f416", "floating point", True),
    # (iii) the same blocks, with queries that MUST NOT match
    ("overmatch-word", "01a0ad5b-1765-7e08-89cc-5342a879f416", "parachute deployment", False),
    ("overmatch-word", "01a0abc7-429d-7a0d-b7fb-252dab0c32ec", "photosynthesis", False),
    ("overmatch-short", "01a0abc7-42ad-7050-b607-63aacd8a50c8", "fix", False),
    # one letter from the word the expansion repairs. It was in the job report's table and NOT in
    # this script, which is the difference between a measurement and a claim about one (audit
    # 2026-09-20 §2): expansion adds five spellings of ONE word, not a neighbourhood.
    ("overmatch-near", "01a0ad5b-1765-7e08-89cc-5342a879f416", "gloating", False),
]

#: leg 1 of litkb_search, verbatim from pipeline/litkb/mcp/server.py `_SEARCH_BLOCKS_ALL` (the
#: main_files/main_works joins there are the VISIBILITY filter, not the matching; this is the
#: matching). `%(f)s` is the function under test, never user input.
LEG1 = ("SELECT to_tsvector('english', litkb.{f}(b.text)) "
        "       @@ plainto_tsquery('english', litkb.{f}(%s)) "
        "  FROM litkb.blocks b WHERE b.id = %s")
#: the counterfactual a fixed byte table would produce for byte 0x01 (its measured majority, fi)
LEG1_TABLE = ("SELECT to_tsvector('english', litkb.norm_search_text(replace(b.text, chr(1), 'fi'))) "
              "       @@ plainto_tsquery('english', litkb.norm_search_text(%s)) "
              "  FROM litkb.blocks b WHERE b.id = %s")

#: the same leg-1 predicate as a COUNT over the whole table, so it can be served from the
#: expression index — which is the only way to see whether that index agrees with the function
COUNT_Q = ("SELECT count(*) FROM litkb.blocks b "
           " WHERE to_tsvector('english', litkb.norm_search_text(b.text)) "
           "       @@ plainto_tsquery('english', litkb.norm_search_text(%s))")
#: the same for leg 3's `%` operator, which reads the OTHER expression index
#: (blocks_norm_text_trgm, gin_trgm_ops) — rebuilt by the same statements and just as able to go
#: stale, and invisible to a check that only exercises the tsvector one
COUNT_TRGM = ("SELECT count(*) FROM litkb.blocks b "
              " WHERE litkb.norm_search_text(b.text) %% litkb.norm_search_text(%s)")

STATE = ("SELECT (SELECT count(*) FROM litkb.blocks),"
         "       (SELECT md5(string_agg(text, '' ORDER BY id)) FROM litkb.blocks),"
         "       (SELECT count(*) FROM litkb.use_evidence),"
         "       (SELECT count(*) FROM litkb.use_evidence WHERE quote_verified),"
         "       (SELECT md5(string_agg(id::text, ',' ORDER BY id)) FROM litkb.use_evidence"
         "         WHERE quote_verified)")


def leg1(conn, fn, query, block_id):
    row = conn.execute(LEG1.format(f=fn), (query, block_id)).fetchone()
    return None if row is None else row[0]


def main():
    from litkb.db import connect as c
    from litkb.db import migrate

    db = c.DB_TEST
    # BEGIN guard: the 0025 proof runs on a worker database, never on live litkb
    if not c.is_test_db(db) or db == c.DB_MAIN:
        raise SystemExit(f"refusing: {db} is not a worker/test database (set LITKB_TEST_DB)")
    # END guard: the 0025 proof runs on a worker database, never on live litkb
    conn = c.connect(db, "litkb_test", autocommit=True)
    print(f"database: {db} ({conn.execute('SELECT current_database()').fetchone()[0]})")

    applied = {v for (v,) in conn.execute(
        "SELECT version FROM litkb_meta.schema_migrations").fetchall()}
    if 25 in applied:
        raise SystemExit("0025 is already applied here; restore the dump again for a before/after")
    print(f"migrations applied before: {max(applied)} ({len(applied)} recorded)")

    before = conn.execute(STATE).fetchone()
    print(f"BEFORE  blocks={before[0]}  md5(text)={before[1]}  use_evidence={before[2]}  "
          f"quote_verified={before[3]}  md5(verified ids)={before[4]}")

    rows = []
    for name, block_id, query, want in CASES:
        old = leg1(conn, "norm_search_text", query, block_id)
        table = conn.execute(LEG1_TABLE, (query, block_id)).fetchone()[0]
        rows.append(dict(case=name, block_id=block_id, query=query, must_match=want,
                         leg1_old=old, leg1_byte_table_0x01_fi=table, leg1_new=None))
        print(f"  BEFORE {name:16} {query!r:24} old={old}  byte-table(0x01->fi)={table}")

    t0 = time.time()
    ran = migrate.apply(conn)
    secs = time.time() - t0
    print(f"migration applied: {ran} in {secs:.1f}s (includes both index rebuilds)")

    # BEGIN guard: the search index agrees with the function it is built from
    # The migration replaces the function and rebuilds both expression indexes. If the rebuild does
    # not see the new body, every leg silently reads pre-0025 entries and NOTHING else here would
    # notice: the leg-1 probes below fetch one block by primary key and never touch this index.
    # Measured 2026-09-20: CREATE OR REPLACE + REINDEX through migrate.apply() left the fts index
    # answering `misclassification` on 722 blocks, while the function answered 906 and the PRE-0025
    # function answered 612 — it agreed with neither, and the mechanism was never identified. The
    # migration drops and recreates instead; this is the check that says so on every run. BOTH
    # expression indexes are checked: the trigram one was rebuilt the same way and a guard that
    # looked only at the tsvector one would have said "ok" about half the search layer.
    agree = {}
    for label, sql, qs in (("fts ", COUNT_Q, ("misclassification", "covariate effects",
                                              "floating point")),
                           ("trgm", COUNT_TRGM, ("misclassification", "covariate effects"))):
        for q in qs:
            served = conn.execute(sql, (q,)).fetchone()[0]
            conn.execute("SET enable_indexscan = off; SET enable_bitmapscan = off")
            scanned = conn.execute(sql, (q,)).fetchone()[0]
            conn.execute("RESET enable_indexscan; RESET enable_bitmapscan")
            agree[f"{label} {q}"] = (served, scanned)
            print(f"  {label} index vs function {q!r:22} index={served} seqscan={scanned} "
                  f"{'ok' if served == scanned else 'STALE INDEX'}")
    index_agrees = all(a == b for a, b in agree.values())
    # END guard: the search index agrees with the function it is built from

    # the rebuild, timed on its own: the same two statements the migration ran
    times = {}
    for idx, ddl in (("blocks_norm_text_fts",
                      "CREATE INDEX blocks_norm_text_fts ON litkb.blocks "
                      "USING gin (to_tsvector('english', litkb.norm_search_text(text)))"),
                     ("blocks_norm_text_trgm",
                      "CREATE INDEX blocks_norm_text_trgm ON litkb.blocks "
                      "USING gin (litkb.norm_search_text(text) gin_trgm_ops)")):
        t1 = time.time()
        conn.execute(f"DROP INDEX litkb.{idx}")
        conn.execute(ddl)
        times[idx] = time.time() - t1
        size = conn.execute("SELECT pg_size_pretty(pg_relation_size(%s))", (f"litkb.{idx}",)).fetchone()[0]
        print(f"  DROP+CREATE {idx}: {times[idx]:.1f}s, {size}")

    after = conn.execute(STATE).fetchone()
    print(f"AFTER   blocks={after[0]}  md5(text)={after[1]}  use_evidence={after[2]}  "
          f"quote_verified={after[3]}  md5(verified ids)={after[4]}")
    identical = before == after
    print(f"(ii) stored bytes and verified quotes identical before/after: {identical}")

    ok = identical
    for r in rows:
        r["leg1_new"] = leg1(conn, "norm_search_text", r["query"], r["block_id"])
        verdict = (r["leg1_new"] is r["must_match"])
        ok = ok and verdict
        r["verdict"] = "ok" if verdict else "FAILED"
        print(f"  AFTER  {r['case']:16} {r['query']!r:24} old={r['leg1_old']} new={r['leg1_new']} "
              f"(must match: {r['must_match']}) {r['verdict']}")

    # the planner still reaches the rebuilt index rather than scanning
    plan = "\n".join(p for (p,) in conn.execute(
        "EXPLAIN SELECT b.id FROM litkb.blocks b WHERE to_tsvector('english', "
        "litkb.norm_search_text(b.text)) @@ plainto_tsquery('english', "
        "litkb.norm_search_text('floating point'))").fetchall())
    print("plan uses blocks_norm_text_fts:", "blocks_norm_text_fts" in plan)
    print(f"index agrees with the function on every probe: {index_agrees}")
    ok = ok and index_agrees

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case", "block_id", "query", "must_match", "leg1_old",
                                           "leg1_byte_table_0x01_fi", "leg1_new", "verdict"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
        w.writerow(dict(case="state-before", block_id=str(before[0]), query="md5(blocks.text)",
                        must_match="", leg1_old=before[1], leg1_byte_table_0x01_fi=before[3],
                        leg1_new=before[4], verdict=""))
        w.writerow(dict(case="state-after", block_id=str(after[0]), query="md5(blocks.text)",
                        must_match="", leg1_old=after[1], leg1_byte_table_0x01_fi=after[3],
                        leg1_new=after[4], verdict="identical" if identical else "CHANGED"))
        for idx, s in times.items():
            w.writerow(dict(case="reindex", block_id=idx, query=f"{s:.1f}s", must_match="",
                            leg1_old="", leg1_byte_table_0x01_fi="", leg1_new="", verdict=""))
    print(f"wrote {OUT}")
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

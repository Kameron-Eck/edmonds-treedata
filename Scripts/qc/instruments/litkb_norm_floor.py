r"""The numbers migration 0025 uses to justify its TWO-LETTER FLOOR, derived rather than restated.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w2 \
        py -3.12 qc/instruments/litkb_norm_floor.py

WHY THIS EXISTS. Until 2026-09-20 the floor's numbers (1,418 / 0 / 1,244 and 1,542 / 343), the
38,595-word vocabulary and the rejected alternative's 181 / 386 / 93 lived ONLY as prose in the
migration header and in a job report. The 2026-09-20 audit reproduced them from its own SQL and
said the obvious thing: under CLAUDE.md 3.4b that is a restatement, not a measurement — nothing
regenerates them and nothing would notice if they rotted. This is the script they come from.

THE DEFINITIONS, spelled out, because every one of them is a choice:

  VOCABULARY. Distinct `lower()` runs of letters from `regexp_split_to_table(text, '[^A-Za-z]+')`
  over CURRENT-RUN blocks that contain NO C0 control byte — the corpus's own clean words, so a
  candidate spelling is checked against what these papers actually say rather than a dictionary.
  Two of them: 4-25 letters (`vocab4`, the one the header quotes) and 1-25 letters (`vocab_any`,
  which is what makes the short-word injection visible at all — `fix` is three letters).

  OCCURRENCE. A C0 control byte followed by at least one letter, in a current-run block. For each
  one: `prefix` = the letters immediately before the byte, `tail` = the letters immediately after.

  BUCKET. ONE-letter means no letter in front AND a one-letter tail (`<0x05>x`). Everything else is
  the >=2 bucket. The buckets partition the occurrences.

  CANDIDATE. prefix || lig || tail for each of ff / fi / fl / ffi / ffl — what the index would gain
  if the rule fired here.

WHAT THE SPLIT DOES AND DOES NOT SHOW, stated here because the header's table used to read as two
independent measurements and is one. Both buckets are scored against the SAME vocabularies with the
SAME question. In the >=2 bucket every candidate is at least four letters, so its "spells a word of
any length" count and its "spells a word of 4+ letters" count are the same number BY CONSTRUCTION —
that bucket cannot show injection. The finding is entirely in the one-letter bucket's asymmetry:
it recovers no long word at all while spelling a real short word in over a thousand places.

THE REJECTED ALTERNATIVE. "Tolerate the missing ligature": delete ffi|ffl|ff|fi|fl from both the
stored word and the query, so `floating` and `<0x1d>oating` meet at `oating`. Scored on vocab4:
how many keys are shared by two or more distinct words, how many distinct words that covers, and
how many words collapse to two characters or fewer.

Runs only against a worker database holding a restore of the nightly dump (see
qc/instruments/litkb_norm_additivity.py for the restore command). Reads only; writes no table.

Output: Reports/litkb_norm_floor_2026-09-20.csv and the stdout below.
"""
import csv
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS.parent / "Reports" / "litkb_norm_floor_2026-09-20.csv"

C0 = "chr(1) || '-' || chr(8) || chr(11) || chr(12) || chr(14) || '-' || chr(31)"

SETUP = f"""
CREATE TEMP TABLE cur AS
  SELECT b.id, b.text FROM litkb.blocks b
    JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id;

CREATE TEMP TABLE vocab AS
  SELECT DISTINCT lower(w) AS w
    FROM cur, LATERAL regexp_split_to_table(cur.text, '[^A-Za-z]+') w
   WHERE cur.text !~ ('[' || {C0} || ']')
     AND w ~ '^[A-Za-z]{{1,25}}$';
CREATE INDEX ON vocab (w);

-- every C0 byte followed by letters, with the letters on each side of it
CREATE TEMP TABLE occ AS
  SELECT m[1] AS prefix, m[2] AS tail
    FROM cur, LATERAL regexp_matches(cur.text,
         '([A-Za-z]*)[' || {C0} || ']([A-Za-z]+)', 'g') m;
"""

COUNTS = """
SELECT (SELECT count(*) FROM vocab WHERE length(w) BETWEEN 4 AND 25),
       (SELECT count(*) FROM vocab),
       (SELECT count(*) FROM occ)
"""

#: one row per OCCURRENCE, never per distinct (prefix, tail): the floor is a count of places in the
#: corpus where the rule would fire, and the same damaged word occurring twice is two places.
BUCKETS = """
WITH cand AS (
  SELECT (o.prefix = '' AND length(o.tail) = 1) AS one_letter,
         EXISTS (SELECT 1 FROM vocab v, (VALUES ('ff'),('fi'),('fl'),('ffi'),('ffl')) lig(l)
                  WHERE v.w = lower(o.prefix || lig.l || o.tail)
                    AND length(v.w) BETWEEN 4 AND 25) AS spells_len4plus,
         EXISTS (SELECT 1 FROM vocab v, (VALUES ('ff'),('fi'),('fl'),('ffi'),('ffl')) lig(l)
                  WHERE v.w = lower(o.prefix || lig.l || o.tail)) AS spells_anylen
    FROM occ o)
SELECT one_letter, count(*), count(*) FILTER (WHERE spells_len4plus),
       count(*) FILTER (WHERE spells_anylen)
  FROM cand GROUP BY one_letter ORDER BY one_letter DESC
"""

ALTERNATIVE = """
WITH w AS (SELECT v.w, regexp_replace(v.w, 'ffi|ffl|ff|fi|fl', '', 'g') AS key
             FROM vocab v WHERE length(v.w) BETWEEN 4 AND 25),
g AS (SELECT key, count(DISTINCT w) AS n FROM w GROUP BY key)
SELECT (SELECT count(*) FROM g WHERE n > 1),
       (SELECT coalesce(sum(n), 0) FROM g WHERE n > 1),
       (SELECT count(*) FROM w WHERE length(key) <= 2)
"""


def main():
    from litkb.db import connect as c

    db = c.DB_TEST
    # BEGIN guard: the floor derivation runs on a worker database, never on live litkb
    if not c.is_test_db(db) or db == c.DB_MAIN:
        raise SystemExit(f"refusing: {db} is not a worker/test database (set LITKB_TEST_DB)")
    # END guard: the floor derivation runs on a worker database, never on live litkb
    conn = c.connect(db, "litkb_test", autocommit=True)
    # the corpus has words past the parser's 2047-character limit; its NOTICE is per row.
    conn.execute("SET client_min_messages = warning")
    print(f"database: {db} ({conn.execute('SELECT current_database()').fetchone()[0]})")

    t0 = time.time()
    conn.execute(SETUP)
    n_cur = conn.execute("SELECT count(*) FROM cur").fetchone()[0]
    vocab4, vocab_any, n_occ = conn.execute(COUNTS).fetchone()
    print(f"current-run blocks: {n_cur}   vocabulary 4-25 letters: {vocab4}   "
          f"any length: {vocab_any}   expansion-shape occurrences: {n_occ}  "
          f"({time.time() - t0:.0f}s)")

    rows = [dict(metric="current_run_blocks", bucket="", occurrences=n_cur,
                 spells_word_len4plus="", spells_word_anylen="", note=""),
            dict(metric="vocabulary", bucket="4-25 letters", occurrences=vocab4,
                 spells_word_len4plus="", spells_word_anylen="",
                 note="distinct clean words, C0-free current-run blocks"),
            dict(metric="vocabulary", bucket="any length", occurrences=vocab_any,
                 spells_word_len4plus="", spells_word_anylen="",
                 note="the short words the one-letter bucket would inject"),
            dict(metric="occurrences", bucket="all", occurrences=n_occ,
                 spells_word_len4plus="", spells_word_anylen="",
                 note="a C0 byte followed by >=1 letter")]

    total = 0
    for one_letter, n, len4, anylen in conn.execute(BUCKETS).fetchall():
        total += n
        bucket = "1 letter (no prefix, one-letter tail)" if one_letter else ">=2 letters"
        note = ("excluded by the floor: recovers nothing long, injects short words" if one_letter
                else "included. Its two columns are ONE event: every candidate here is already "
                     "4+ letters, so len4plus == anylen by construction")
        print(f"  bucket {bucket:40} n={n:5}  spells 4+ letter word: {len4:5}  "
              f"spells any word: {anylen:5}")
        rows.append(dict(metric="floor_bucket", bucket=bucket, occurrences=n,
                         spells_word_len4plus=len4, spells_word_anylen=anylen, note=note))
    assert total == n_occ, f"buckets {total} do not partition the {n_occ} occurrences"

    keys, words, short = conn.execute(ALTERNATIVE).fetchone()
    print("rejected alternative (delete ffi|ffl|ff|fi|fl both sides), on the 4-25 vocabulary:")
    print(f"  colliding keys: {keys}   distinct words they cover: {words}   "
          f"words collapsing to <=2 chars: {short}")
    rows += [dict(metric="alternative_collision_keys", bucket="delete the ligature both sides",
                  occurrences=keys, spells_word_len4plus="", spells_word_anylen="",
                  note="keys shared by 2+ distinct words"),
             dict(metric="alternative_words_collided", bucket="delete the ligature both sides",
                  occurrences=words, spells_word_len4plus="", spells_word_anylen="", note=""),
             dict(metric="alternative_words_to_2_chars", bucket="delete the ligature both sides",
                  occurrences=short, spells_word_len4plus="", spells_word_anylen="", note="")]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "bucket", "occurrences",
                                           "spells_word_len4plus", "spells_word_anylen", "note"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

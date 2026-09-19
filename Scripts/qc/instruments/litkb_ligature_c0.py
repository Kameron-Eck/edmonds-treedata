r"""Item 1(a) measurement: does a PDF-extraction C0 control byte identify WHICH ligature
(ff/fi/fl/ffi/ffl) it stands in for -- read-only against live litkb, current-run blocks only.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_ligature_c0.py

Mechanism (found while orienting on this instrument, not asserted from memory): PDF subset fonts
number their custom (non-base) glyphs starting from 1 in the font's own Differences/encoding
array; ligature glyphs (ff, fi, fl, ffi, ffl) that have no ToUnicode entry come out of extraction
as that raw glyph code -- a C0 control byte -- instead of the ligature's letters. Because font
subsets are built per embedded font (body vs. heading vs. italic can each subset separately), the
SAME byte can name a DIFFERENT glyph in a different subset, even inside one file: this instrument
found file 01a0a4d6-6db4-7343-965a-aca7b3c090d4 emitting `\x01` for "fi" in "in\x01nitely"
(infinitely) AND for "ff" in "e\x01ects" (effects, in a different heading-style block of the same
file). A fixed byte -> ligature table would therefore silently write a wrong ligature into some
fraction of occurrences; this instrument measures how often that ambiguity actually shows up
before any normaliser is built (CLAUDE.md 3.2 "never invent"; 3.4c "the proposer never scores its
own proposal" -- Kam sees this measurement before any fixed table is proposed).

Method: for each CURRENT-RUN block matching `letters + C0-byte + letters` (a byte sitting inside
what reads as one word), try each of the five ligatures in the gap and check whether the resulting
word already exists, spelled out in full, somewhere in a CLEAN (no C0 byte) current-run block
ANYWHERE in the corpus -- the corpus's own vocabulary (38,595 distinct clean words 4-25 letters,
built in ~4s: cheap enough to use whole) is the dictionary, so no word list is invented. A per-file
version of this dictionary was tried first and resolved almost nothing (most files never spell the
same word clean elsewhere in the SAME file), so it is corpus-wide; the tradeoff, reported honestly,
is that a short prefix/suffix can coincidentally match more than one ligature's corpus word (that
shows up as `ambiguous`, not as false confidence). A byte resolves if exactly one of the five
expansions is attested; it is ambiguous if more than one is, and unresolved if none is.

Output: Reports/litkb_ligature_c0_2026-09-19.csv, one row per occurrence, plus a stdout summary:
the byte -> ligature distribution among resolved occurrences, and the count of (file, byte) pairs
where the SAME byte resolves to more than one ligature in the SAME file (the direct measurement of
the hazard above).
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS.parent / "Reports" / "litkb_ligature_c0_2026-09-19.csv"

C0 = "\x01-\x08\x0b\x0c\x0e-\x1f"
MIDWORD = re.compile(f"([A-Za-z]+)([{C0}])([A-Za-z]+)")
LIGATURES = ("ff", "fi", "fl", "ffi", "ffl")


def main():
    from litkb.db import connect as c   # PYTHONPATH=pipeline; the path-hack ledger allows no new site

    conn = c.connect(c.DB_MAIN, "litkb_reader", autocommit=True)

    total_current = conn.execute(
        "SELECT count(*) FROM litkb.blocks b JOIN litkb.files f "
        "ON f.id = b.file_id AND f.current_run_id = b.run_id").fetchone()[0]
    affected = conn.execute(
        f"SELECT count(*), count(DISTINCT b.file_id) FROM litkb.blocks b JOIN litkb.files f "
        f"ON f.id = b.file_id AND f.current_run_id = b.run_id WHERE b.text ~ '[{C0}]'").fetchone()
    print(f"measured (current-run only): {total_current} blocks total; "
          f"{affected[0]} blocks / {affected[1]} files carry a C0 byte in [{C0}] "
          f"(delta's relayed 16,315/106 spans superseded runs too -- not the same count)")

    rows = conn.execute(
        f"SELECT b.file_id, b.id, b.text FROM litkb.blocks b JOIN litkb.files f "
        f"ON f.id = b.file_id AND f.current_run_id = b.run_id "
        f"WHERE b.text ~ '[A-Za-z]+[{C0}][A-Za-z]+'").fetchall()
    print(f"measured: {len(rows)} current-run blocks carry a letters-C0-letters span")

    occurrences = []  # (file_id, block_id, byte, prefix, suffix)
    files_needed = set()
    for file_id, block_id, text in rows:
        for m in MIDWORD.finditer(text):
            occurrences.append((file_id, block_id, m.group(1), m.group(2), m.group(3)))
            files_needed.add(file_id)
    print(f"measured: {len(occurrences)} letters-C0-letters occurrences across {len(files_needed)} files")

    # the corpus-wide dictionary: every word (4-25 letters) spelled out in full in a CLEAN (no C0)
    # current-run block anywhere in the corpus
    clean_words = {w for (w,) in conn.execute(
        f"SELECT DISTINCT lower(w) FROM litkb.blocks b "
        f"JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id "
        f"CROSS JOIN LATERAL regexp_split_to_table(b.text, '[^A-Za-z]+') AS w "
        f"WHERE b.text !~ '[{C0}]' AND length(w) BETWEEN 4 AND 25").fetchall()}
    print(f"measured: corpus-wide clean-word dictionary has {len(clean_words)} distinct words")

    results = []
    for file_id, block_id, prefix, byte, suffix in occurrences:
        hits = [lig for lig in LIGATURES if (prefix + lig + suffix).lower() in clean_words]
        status = "resolved" if len(hits) == 1 else ("ambiguous" if len(hits) > 1 else "unresolved")
        results.append(dict(file_id=file_id, block_id=block_id, byte_hex=hex(ord(byte)),
                            prefix=prefix, suffix=suffix, status=status,
                            resolved_ligature=hits[0] if status == "resolved" else "",
                            all_hits="|".join(hits)))

    by_byte_ligature = Counter((r["byte_hex"], r["resolved_ligature"]) for r in results if r["status"] == "resolved")
    status_counts = Counter(r["status"] for r in results)
    print(f"status counts: {dict(status_counts)}")
    print("byte -> resolved-ligature distribution (resolved occurrences only):")
    for (byte_hex, lig), n in sorted(by_byte_ligature.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {byte_hex} -> {lig}: {n}")

    # the direct measurement of the hazard: same (file, byte) resolving to >1 distinct ligature
    per_file_byte = defaultdict(set)
    for r in results:
        if r["status"] == "resolved":
            per_file_byte[(r["file_id"], r["byte_hex"])].add(r["resolved_ligature"])
    conflicts = {k: v for k, v in per_file_byte.items() if len(v) > 1}
    print(f"within-file byte conflicts (same file, same byte, >1 distinct resolved ligature): {len(conflicts)}")
    for (file_id, byte_hex), ligs in list(conflicts.items())[:10]:
        print(f"  file {file_id} byte {byte_hex}: {sorted(ligs)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file_id", "block_id", "byte_hex", "prefix", "suffix",
                                           "status", "resolved_ligature", "all_hits"])
        w.writeheader()
        for r in sorted(results, key=lambda r: (r["file_id"], r["block_id"], r["byte_hex"])):
            w.writerow(r)
    print(f"wrote {OUT} ({len(results)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

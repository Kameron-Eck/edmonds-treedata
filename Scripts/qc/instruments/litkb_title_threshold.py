"""Calibrate the no-identifier duplicate threshold of litkb admission check 2 (design §4.6, §14 P2 gate).

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_title_threshold.py

Gold: the tracker's `Duplicate of` column (Reports/literature_tracker.csv, read-only), the only human-marked
duplicate pairs in the project. Every other pair of tracker rows is treated as a NON-duplicate, which is an
assumption: an unmarked duplicate would count as a false positive here (the top-scoring non-duplicate pairs
are written out so they can be read).

Metric: exactly the database's own rule, computed by the database: pg_trgm similarity() of litkb.norm_title()
(migration 0013) with the year window of litkb._title_duplicates (|year difference| <= 1). Runs on litkb_test
as litkb_test (the migrations must be applied there; the P1/P2 suites do that), in a temporary table.

Output: Reports/litkb_title_threshold_2026-09-14.csv — one row per scored pair at similarity >= 0.30 plus every
gold pair whatever its score — and a threshold table on stdout (recall on gold pairs, false positives among
non-duplicate pairs inside the year window). Choice rule, fixed here before reading the numbers: the LOWEST
threshold on a 0.05 grid with zero false positives in the year window, provided every gold pair whose titles
are the same work's title (not a DOI-only duplicate) is caught.
"""
import csv
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
TRACKER = SCRIPTS.parent / "Reports" / "literature_tracker.csv"
OUT = SCRIPTS.parent / "Reports" / "litkb_title_threshold_2026-09-14.csv"


def main():
    from litkb.db import connect as c   # run with PYTHONPATH=pipeline (the path-hack ledger allows no new site)

    rows = list(csv.DictReader(open(TRACKER, encoding="utf-8", newline="")))
    gold = {(int(r["ID"]), int(r["Duplicate of"])) for r in rows if r["Duplicate of"].strip()}
    gold = {tuple(sorted(p)) for p in gold}
    conn = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
    conn.execute("CREATE TEMP TABLE tr (id int PRIMARY KEY, year int, title text)")
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO tr VALUES (%s, %s, %s)",
                        [(int(r["ID"]), int(r["Year"][:4]) if r["Year"][:4].isdigit() else None, r["Title"])
                         for r in rows])
    pairs = conn.execute(
        """SELECT a.id, b.id, a.year, b.year, similarity(litkb.norm_title(a.title), litkb.norm_title(b.title)) s,
                  (a.year IS NULL OR b.year IS NULL OR abs(a.year - b.year) <= 1) AS in_window, a.title, b.title
             FROM tr a JOIN tr b ON a.id < b.id""").fetchall()
    conn.close()
    scored = [dict(a=p[0], b=p[1], ya=p[2], yb=p[3], sim=float(p[4]), in_window=p[5], ta=p[6], tb=p[7],
                   gold=(p[0], p[1]) in gold) for p in pairs]
    gold_rows = [s for s in scored if s["gold"]]
    print(f"tracker rows {len(rows)}; pairs {len(scored)}; gold pairs {len(gold_rows)}; "
          f"non-duplicate pairs in the year window {sum(1 for s in scored if s['in_window'] and not s['gold'])}")
    for g in sorted(gold_rows, key=lambda s: s["sim"]):
        print(f"  gold {g['a']}/{g['b']} years {g['ya']}/{g['yb']} sim {g['sim']:.3f} window {g['in_window']}: "
              f"{g['ta'][:50]!r} | {g['tb'][:50]!r}")
    print("  top non-duplicate pairs in the year window:")
    for s in sorted((s for s in scored if s["in_window"] and not s["gold"]), key=lambda s: -s["sim"])[:10]:
        print(f"    {s['a']}/{s['b']} sim {s['sim']:.3f}: {s['ta'][:50]!r} | {s['tb'][:50]!r}")
    # title-level gold: the pair's titles name the same work (a DOI-only duplicate with different titles is not
    # something a title rule can or should catch); decided from the titles themselves, printed above
    title_gold = [g for g in gold_rows if g["sim"] >= 0.5 and g["in_window"]]
    print(f"title-level gold pairs (sim >= 0.5 and in the year window): {len(title_gold)} of {len(gold_rows)}")
    print("threshold | gold caught (of all) | title-level gold caught | false positives in window")
    chosen = None
    for k in range(6, 21):
        t = k * 0.05
        caught = sum(1 for g in gold_rows if g["in_window"] and g["sim"] >= t)
        tcaught = sum(1 for g in title_gold if g["sim"] >= t)
        fp = sum(1 for s in scored if s["in_window"] and not s["gold"] and s["sim"] >= t)
        print(f"  {t:.2f}   | {caught}/{len(gold_rows)} | {tcaught}/{len(title_gold)} | {fp}")
        if chosen is None and fp == 0 and tcaught == len(title_gold):
            chosen = t
    print(f"chosen threshold (lowest with 0 false positives and every title-level gold pair): {chosen}")
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id_a", "id_b", "year_a", "year_b", "similarity", "in_year_window", "duplicate_of_pair",
                    "title_a", "title_b"])
        for s in sorted(scored, key=lambda s: (-s["sim"], s["a"], s["b"])):
            if s["sim"] >= 0.30 or s["gold"]:
                w.writerow([s["a"], s["b"], s["ya"], s["yb"], f"{s['sim']:.4f}", int(bool(s["in_window"])),
                            int(s["gold"]), s["ta"], s["tb"]])
    print(f"wrote {OUT}")
    return 0 if chosen is not None else 1


if __name__ == "__main__":
    sys.exit(main())

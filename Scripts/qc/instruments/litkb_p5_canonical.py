"""Canonical-block census and gold scorer — the BEFORE/AFTER instrument for the P5 final referee.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p5_canonical.py census
    ...                                                                          gold
    ...                                                                          latex
    ...                                                                          local --only NAME[,NAME]

The final referee (Reports/LITKB_P5_FINAL_REFEREE_2026-09-16.md §4) measured three duplicate
classes with ad-hoc SQL and scored eight gold pages by hand. Both numbers are the acceptance
criterion for the canonical-block fix, so BOTH SIDES OF THE COMPARISON MUST COME FROM THE SAME
SCRIPT — a hand-run "after" against a hand-run "before" measures the two readers as much as the
two corpora. That is the whole reason this file exists rather than a second ad-hoc pass.

The three classes, exactly as §4 names them:

  * ``exact``     duplicate ``(current run, page, bbox)`` among canonical blocks.
  * ``near``      duplicate ``(current run, page, normalised text)`` where the normalised text is
                  at least :data:`NEAR_MIN` characters.
  * ``contained`` a canonical block whose normalised text (>= :data:`CONTAIN_MIN` characters) is a
                  PROPER substring of another block's on the same page.

Normalisation is whitespace-collapsed and cased down — ``_norm`` in the reconciler, spelled here
in SQL so the census reads the stored bytes and not a Python re-derivation of them.

``local`` runs the reconciliation from the stored artifacts with NO database at all, and reports
the same three counts over the blocks it produced. That is the iteration loop: a change to
``reconcile.py`` is measured on the referee's worst files in seconds, and only a change that has
already moved these numbers is worth a corpus re-ingest.

``gold`` scores ``Reports/gold/p5_gold_2026-09-16.json`` — FROZEN, authored by the referee before
any block was read — on the four dimensions its ``_scoring`` key defines: presence, kind, reading
order (within-band inversions only, which is what the gold charges as a defect) and text equality
at the STRICT and OPERATING grades. It reads the database; it never writes.
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)))), "pipeline"))

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
GOLD_P5 = os.path.join(REPO, "Reports", "gold", "p5_gold_2026-09-16.json")
GOLD_S5 = os.path.join(REPO, "Reports", "gold", "stage5_gold_2026-09-15.json")

#: The two length floors §4 used. They are not thresholds on behaviour — nothing is refused for
#: being short — they are the referee's reporting cut, kept so the two columns are comparable.
NEAR_MIN = 40
CONTAIN_MIN = 80

#: whitespace-collapsed, cased down: the SQL twin of reconcile._norm.
_NORM_SQL = "lower(btrim(regexp_replace(b.text, '\\s+', ' ', 'g')))"


def _conn(db, role="litkb_reader"):
    import psycopg

    return psycopg.connect(f"host=localhost port=5433 dbname={db} user={role}", autocommit=True)


# ── the three duplicate classes ────────────────────────────────────────────────────────────

_CUR = ("FROM litkb.blocks b JOIN litkb.files f ON f.current_run_id = b.run_id "
        "WHERE b.canonical")

Q_EXACT = f"""
SELECT count(*) AS groups, coalesce(sum(c - 1), 0)::bigint AS extra, count(DISTINCT run_id) AS runs
  FROM (SELECT b.run_id, b.page_no, b.bbox, count(*) c {_CUR}
         GROUP BY 1,2,3 HAVING count(*) > 1) t
"""

Q_NEAR = f"""
SELECT count(*) AS groups, coalesce(sum(c - 1), 0)::bigint AS extra, count(DISTINCT run_id) AS runs
  FROM (SELECT b.run_id, b.page_no, {_NORM_SQL} n, count(*) c {_CUR}
          AND length({_NORM_SQL}) >= {NEAR_MIN}
         GROUP BY 1,2,3 HAVING count(*) > 1) t
"""

#: The containment class. Self-join on the page, `<>` on the id so a block is never its own
#: container, and `length(a) < length(b)` so a PROPER substring is what is counted (an equal pair
#: is the `near` class and must not be counted twice).
Q_CONTAINED = f"""
WITH n AS (SELECT b.id, b.run_id, b.page_no, {_NORM_SQL} t {_CUR}
             AND length({_NORM_SQL}) >= {CONTAIN_MIN})
SELECT count(*) AS blocks, count(DISTINCT a.run_id) AS runs
  FROM n a
 WHERE EXISTS (SELECT 1 FROM n b2
                WHERE b2.run_id = a.run_id AND b2.page_no = a.page_no AND b2.id <> a.id
                  AND length(b2.t) > length(a.t) AND position(a.t in b2.t) > 0)
"""

Q_BY_KIND = f"""
SELECT b.type, count(*) {_CUR} GROUP BY 1 ORDER BY 2 DESC
"""

Q_TOTALS = """
SELECT (SELECT count(*) FROM litkb.files WHERE current_run_id IS NOT NULL),
       (SELECT count(*) FROM litkb.blocks b JOIN litkb.files f ON f.current_run_id = b.run_id),
       (SELECT count(*) FROM litkb.extraction_runs WHERE stage = '5-reconcile' AND status <> 'ok'),
       (SELECT count(*) FROM litkb.pages p JOIN litkb.files f ON f.current_run_id = p.run_id)
"""


def cmd_census(a):
    conn = _conn(a.db)
    files, blocks, not_ok, pages = conn.execute(Q_TOTALS).fetchone()
    ex = conn.execute(Q_EXACT).fetchone()
    ne = conn.execute(Q_NEAR).fetchone()
    co = conn.execute(Q_CONTAINED).fetchone()
    kinds = conn.execute(Q_BY_KIND).fetchall()
    vers = conn.execute(
        "SELECT r.pipeline_version, count(*) FROM litkb.extraction_runs r "
        "JOIN litkb.files f ON f.current_run_id = r.id GROUP BY 1 ORDER BY 1").fetchall()
    conn.close()

    out = {
        "files_with_current_run": files, "blocks_in_current_runs": blocks,
        "pages_in_current_runs": pages, "runs_not_ok": not_ok,
        "pipeline_versions": {k: v for k, v in vers},
        "exact_bbox": {"groups": ex[0], "extra_rows": ex[1], "runs": ex[2]},
        "near_text": {"groups": ne[0], "extra_rows": ne[1], "runs": ne[2], "min_chars": NEAR_MIN},
        "contained": {"blocks": co[0], "runs": co[1], "min_chars": CONTAIN_MIN},
        "by_kind": {k: v for k, v in kinds},
    }
    print(json.dumps(out, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        print(f"-> {a.out}")
    return 0


# ── the same three classes over an IN-MEMORY reconciliation (no database) ───────────────────

def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def dup_classes(canonical):
    """-> the three counts for a list of Canonical blocks. The local twin of the SQL above."""
    import collections

    exact = collections.Counter((c.page, tuple(round(v, 6) for v in c.bbox)) for c in canonical)
    near = collections.Counter()
    for c in canonical:
        n = _norm(c.text)
        if len(n) >= NEAR_MIN:
            near[(c.page, n)] += 1
    by_page = collections.defaultdict(list)
    for c in canonical:
        n = _norm(c.text)
        if len(n) >= CONTAIN_MIN:
            by_page[c.page].append(n)
    contained = 0
    for page, texts in by_page.items():
        for i, t in enumerate(texts):
            if any(len(o) > len(t) and t in o for j, o in enumerate(texts) if j != i):
                contained += 1
    return {
        "exact_bbox": {"groups": sum(1 for v in exact.values() if v > 1),
                       "extra_rows": sum(v - 1 for v in exact.values() if v > 1)},
        "near_text": {"groups": sum(1 for v in near.values() if v > 1),
                      "extra_rows": sum(v - 1 for v in near.values() if v > 1)},
        "contained": {"blocks": contained},
    }


def cmd_local(a):
    """Reconcile from the stored artifacts and report the three classes. No database."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import litkb_p5_bulk as B

    plan = B.load_plan()
    rows = plan["files"]
    if a.only:
        want = [w.strip() for w in a.only.split(",") if w.strip()]
        rows = [r for r in rows
                if any(w == r["sha256"] or w.lower() in r["name"].lower() for w in want)]
    if a.limit:
        rows = rows[:a.limit]
    records = B.census_records()
    latex_by_sha, _held = B.load_latex() if a.latex else ({}, {})

    totals = {"exact_bbox": 0, "near_text": 0, "contained": 0, "blocks": 0}
    per_file = []
    for row in rows:
        canonical, dis, stats, cov, extra = B.reconcile_one(row, records, latex_by_sha)
        d = dup_classes(canonical)
        kinds = {}
        for c in canonical:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
        rec = {"name": row["name"], "blocks": len(canonical),
               "exact_extra": d["exact_bbox"]["extra_rows"],
               "near_extra": d["near_text"]["extra_rows"],
               "contained": d["contained"]["blocks"],
               "disagreements": len(dis), "by_kind": kinds}
        per_file.append(rec)
        totals["exact_bbox"] += rec["exact_extra"]
        totals["near_text"] += rec["near_extra"]
        totals["contained"] += rec["contained"]
        totals["blocks"] += rec["blocks"]
        print(f"{row['name'][:58]:<58} blocks={rec['blocks']:<6} exact={rec['exact_extra']:<5} "
              f"near={rec['near_extra']:<5} contained={rec['contained']:<5} "
              f"kinds={json.dumps(kinds)}")
    print(f"\nTOTAL over {len(per_file)} documents: {json.dumps(totals)}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"totals": totals, "files": per_file}, fh, indent=1)
        print(f"-> {a.out}")
    return 0


# ── the gold scorer ────────────────────────────────────────────────────────────────────────

#: The gold's OPERATING grade, step (4): Unicode punctuation folded to ASCII.
_FOLD = {"‘": "'", "’": "'", "“": '"', "”": '"',
         "–": "-", "—": "-", " ": " "}


def _flat(s):
    """The gold's OPERATING grade, verbatim from ``_scoring.text_equality``: (1) CRLF/LF to a
    space, (2) whitespace runs collapsed, (3) a hyphen at a line break joined, (4) Unicode
    punctuation folded to ASCII, (5) ends stripped."""
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"(\w)[-­‐‑]\n(\w)", r"\1\2", s)      # (3), before (1) eats the \n
    for a, b in _FOLD.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _blocks_for(conn, sha256, page):
    return conn.execute(
        "SELECT b.id::text, b.type, b.reading_order, b.text, b.bbox, b.page_no "
        "  FROM litkb.blocks b JOIN litkb.files f ON f.current_run_id = b.run_id "
        " WHERE f.sha256 = %s AND b.page_no = %s ORDER BY b.reading_order",
        (sha256, page)).fetchall()


def _text_equality(items, want):
    """-> (strict, operating, split_n), the gold's two grades plus its ``split-N`` case.

    ``_scoring.text_equality``: "A gold paragraph that the live extraction SPLIT across more than
    one block is reported as 'split-N', and the operating grade is then run against the
    concatenation of the covering blocks in reading order." So a single block is tried first and,
    failing that, the shortest run of consecutive blocks (by reading order) whose concatenation
    covers the paragraph.
    """
    head = _norm(want)[:60]
    for r in items:
        if head and head in _norm(r[3]):
            if r[3] == want:
                return True, True, 0
            if _flat(r[3]) == _flat(want):
                return False, True, 0
            break
    ordered = sorted(items, key=lambda r: r[2])
    target = _flat(want)
    for i in range(len(ordered)):
        joined = ""
        for j in range(i, min(i + 8, len(ordered))):
            joined = (joined + " " + ordered[j][3]) if joined else ordered[j][3]
            if _flat(joined) == target:
                return False, True, j - i + 1
            if len(_flat(joined)) > len(target) + 200:
                break
    return False, False, 0


def _match(items, snippet):
    """The gold's own snippet rule: whitespace-normalised, case-insensitive, IN the block text."""
    want = _norm(snippet)
    for r in items:
        if want and want in _norm(r[3]):
            return r
    return None


def _local_blocks(sha256, page):
    """The same five columns ``_blocks_for`` returns, from a reconciliation of the ARTIFACTS.

    The gold's acceptance criteria have to be readable BEFORE a corpus re-ingest, or the only way
    to find out whether a reconciler change helped is to spend the ingest and look afterwards.
    Same scorer, same rows, no database.
    """
    import litkb_p5_bulk as B

    cache = _local_blocks.__dict__.setdefault("_cache", {})
    if sha256 not in cache:
        plan = B.load_plan()
        row = next(r for r in plan["files"] if r["sha256"] == sha256)
        canonical, _dis, _stats, _cov, _extra = B.reconcile_one(row, B.census_records(), {})
        cache[sha256] = canonical
    out = []
    for c in cache[sha256]:
        if c.page != page:
            continue
        out.append((c.element_id or "", c.db_type(), c.reading_order, c.text, list(c.bbox), c.page))
    return sorted(out, key=lambda r: r[2])


def cmd_gold(a):
    gold = json.load(open(a.gold, encoding="utf-8"))
    conn = None
    if a.local:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    else:
        conn = _conn(a.db)
    rows, tot = [], {"items": 0, "present": 0, "kind_ok": 0, "within_bad": 0, "cross_bad": 0,
                     "strict": 0, "operating": 0, "verbatim": 0, "page_ok": 0, "page_items": 0}
    for g in gold["pages"]:
        items = (_local_blocks(g["sha256"], g["page"]) if a.local
                 else _blocks_for(conn, g["sha256"], g["page"]))
        # a cross-page paragraph may now be split, so the gold page's items can also be reached
        # from the sibling fragment: the page the gold names is the page the quote is PRINTED on,
        # which is the whole point of fix 2, so nothing outside that page is consulted here.
        matched, present, kind_ok = [], 0, 0
        for it in g["body_order"]:
            hit = _match(items, it["snippet"])
            if hit is None:
                matched.append((it, None))
                continue
            present += 1
            want = set(it.get("kind_any") or [it["kind"]])
            kind_ok += 1 if hit[1] in want else 0
            matched.append((it, hit))
        # reading order, by the gold's rule: within-band inversions are defects, cross-column
        # ones are reported and not charged.
        within = cross = 0
        got = [(it, hit) for it, hit in matched if hit is not None]
        for i in range(len(got)):
            for j in range(i + 1, len(got)):
                (ia, ha), (ib, hb) = got[i], got[j]
                if ha[2] <= hb[2]:
                    continue
                same_band = (ia.get("col") or "-") == (ib.get("col") or "-")
                within += 1 if same_band else 0
                cross += 0 if same_band else 1
        v = g.get("verbatim_paragraph")
        strict = operating = None
        split = 0
        if v:
            strict, operating, split = _text_equality(items, v["text"])
            tot["verbatim"] += 1
            tot["strict"] += 1 if strict else 0
            tot["operating"] += 1 if operating else 0
        page_ok = all(hit is None or hit[5] == g["page"] for _it, hit in matched)
        tot["page_items"] += 1
        tot["page_ok"] += 1 if page_ok else 0
        rows.append({"id": g["id"], "file": os.path.basename(g["file"]), "page": g["page"],
                     "items": len(g["body_order"]), "present": present, "kind_ok": kind_ok,
                     "within_band_violations": within, "cross_band": cross,
                     "strict": strict, "operating": operating, "split": split,
                     "blocks_on_page": len(items),
                     "missing": [it["snippet"][:50] for it, hit in matched if hit is None]})
        tot["items"] += len(g["body_order"])
        tot["present"] += present
        tot["kind_ok"] += kind_ok
        tot["within_bad"] += within
        tot["cross_bad"] += cross
    if conn is not None:
        conn.close()
    print(f"{'id':<4} {'file':<44} {'pg':>3} {'items':>5} {'pres':>5} {'kind':>5} "
          f"{'within':>6} {'cross':>5} {'strict':>6} {'oper':>5}")
    for r in rows:
        print(f"{r['id']:<4} {r['file'][:44]:<44} {r['page']:>3} {r['items']:>5} "
              f"{r['present']:>5} {r['kind_ok']:>5} {r['within_band_violations']:>6} "
              f"{r['cross_band']:>5} {str(r['strict']):>6} {str(r['operating']):>5}"
              + (f"  split-{r['split']}" if r["split"] else "")
              + ("".join(f"\n       MISS {m}" for m in r["missing"]) if a.verbose else ""))
    print(f"\nTOTAL {json.dumps(tot)}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"gold": os.path.basename(a.gold), "pages": rows, "total": tot}, fh, indent=1)
        print(f"-> {a.out}")
    return 0


# ── latex_status corpus counts ─────────────────────────────────────────────────────────────

def cmd_latex(a):
    conn = _conn(a.db)
    have = conn.execute(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'litkb' "
        "AND table_name = 'equations' AND column_name = 'latex_status'").fetchone()[0]
    if not have:
        print("litkb.equations has no latex_status column (migration 0022 not applied here)")
        conn.close()
        return 1
    rows = conn.execute(
        "SELECT coalesce(e.latex_status, '(null)'), count(*), "
        "       count(*) FILTER (WHERE e.latex IS NOT NULL) "
        "  FROM litkb.equations e JOIN litkb.blocks b ON b.id = e.block_id "
        "  JOIN litkb.files f ON f.current_run_id = b.run_id GROUP BY 1 ORDER BY 2 DESC").fetchall()
    conn.close()
    print(f"{'latex_status':<14} {'equations':>9} {'with latex':>11}")
    for s, n, withl in rows:
        print(f"{s:<14} {n:>9} {withl:>11}")
    print(f"{'TOTAL':<14} {sum(r[1] for r in rows):>9} {sum(r[2] for r in rows):>11}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=os.environ.get("LITKB_DB", "litkb"))
    ap.add_argument("--out")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("census")
    p = sub.add_parser("gold")
    p.add_argument("--gold", default=GOLD_P5)
    p.add_argument("--verbose", action="store_true", help="list every uncovered gold item")
    p.add_argument("--local", action="store_true",
                   help="score a reconciliation of the stored artifacts, not the database")
    sub.add_parser("latex")
    p = sub.add_parser("local")
    p.add_argument("--only")
    p.add_argument("--limit", type=int)
    p.add_argument("--latex", action="store_true", help="attach the L4 LaTeX before counting")
    a = ap.parse_args(argv)
    return {"census": cmd_census, "gold": cmd_gold, "latex": cmd_latex,
            "local": cmd_local}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())

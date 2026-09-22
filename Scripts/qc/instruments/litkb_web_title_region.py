"""litkb S4 carry-in — `binding.TITLE_REGION_LINES = 45` on WEB text snapshots, measured.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_web_title_region.py

WHY. `TITLE_REGION_LINES` was MEASURED on PDF first pages (`binding.py`'s comment above the
constant: 188 held papers, title window at line <= 12 on 186, then 26 and 43). S3 then bound web
pages through the SAME binder (`admit.front.web_snapshot_evidence` calls `binding.bind_any` on the
snapshot's text), which makes 45 a ceiling on web pages that nobody measured — the S3 carry-in the
S4 block names. `litkb.extract.text_snapshot`'s SKIP_TOKENS comment is the one data point so far:
the Crossref blog page, whole, put its article title at line 84, and dropping the site furniture is
what brought it inside the region. This instrument measures where the title lands on every real
snapshot on disk. It does NOT change the constant; a row past it is reported, never absorbed.

THE SET. Every ``*.txt`` under ``_litkb_staging/web/`` plus every ``file_versions`` row whose
``copy_kind`` is ``web snapshot`` (read as ``litkb_reader``). Each row says its ``kind``:
``html-snapshot`` when the `litkb.extract.text_snapshot` sidecar (``<name>.snapshot.json``) sits
beside it — a page's saved text — and ``page1-text`` when it does not (the short files there are a
PDF's page-1 text, named like the `litkb_derived/hunt/*.page1.txt` copies, S4 run 3 data survey
D5). Both are measured; only ``html-snapshot`` rows speak to the web ceiling.

THE TITLE, derived per row and its source named (``title_source``), never typed in:
  1. ``binding.registry_title`` of a ``file_versions`` row bound at this rel_path — the title the
     binder itself measured against (its recorded ``line`` is kept beside, as a cross-check);
  2. else a DOI PRINTED in the snapshot that a main work holds as an ACTIVE DOI -> that work's title
     (the refused Crossref-blog hunts print the DOI of `Tkaczyk_2024_how-good-your-matching`);
  3. else a main file whose rel_path stem equals the snapshot's stem -> its work's title;
  4. else a work whose key equals the snapshot's stem -> its title (main works only);
  5. else no title: the row is written with ``title_source = none`` and no index.

THE WINDOWING is the binder's own: `binding.page_lines` (non-empty lines, whitespace collapsed),
`binding.scored_lines` (the stamp/URL strip), 1-3 consecutive lines joined as
`binding._window_text` joins them, scored by `resolver.title_match_ratio` against
`binding.BIND_RATIO`. ``first_index`` is the smallest window START at which any 1-3 line window
reaches the ratio — the number `window_refusal` compares with ``TITLE_REGION_LINES``.
``refusal_at_first`` is what `binding.window_refusal` says of that window (the region rule, the
reference-list rule, the citation-instruction rule), so a title inside the region that would still
be refused for another reason is visible too.

Output: ``phase4/qc/litkb_web_title_region.csv`` (columns :data:`COLUMNS`). Reads only.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
OUT = REPO / "phase4" / "qc" / "litkb_web_title_region.csv"
WEB_DIR = ("_litkb_staging", "web")

COLUMNS = ["rel_path", "kind", "bytes", "sha256_12", "title_source", "title", "n_lines",
           "first_index", "first_window_lines", "first_ratio", "within_region", "refusal_at_first",
           "best_index", "best_ratio", "binding_line", "binding_ratio", "title_region_lines"]

_DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"<>,;]+", re.I)


def measure_text(text, title):
    """-> {"n_lines", "first_index", "first_window_lines", "first_ratio", "within_region",
    "refusal_at_first", "best_index", "best_ratio"} for one snapshot's text against `title`."""
    from litkb.admit import binding as B
    from litkb.admit.resolver import title_match_ratio

    lines = B.page_lines(text)
    scored = B.scored_lines(lines)
    flags = B._line_flags(lines)
    first = None                      # (index, n, ratio) of the first window start that reaches it
    best = (None, 0.0)
    for i in range(len(lines)):
        at_i = None
        for n in (1, 2, 3):
            if i + n > len(lines):
                break
            r = title_match_ratio(title, B._window_text(scored, i, n))
            if r > best[1]:
                best = (i, r)
            if r >= B.BIND_RATIO and (at_i is None or r > at_i[2]):
                at_i = (i, n, r)
        if at_i and first is None:
            first = at_i
    out = {"n_lines": len(lines), "first_index": None, "first_window_lines": None,
           "first_ratio": None, "within_region": None, "refusal_at_first": None,
           "best_index": best[0], "best_ratio": round(best[1], 4)}
    if first is not None:
        i, n, r = first
        out.update(first_index=i, first_window_lines=n, first_ratio=round(r, 4),
                   within_region=i < B.TITLE_REGION_LINES,
                   refusal_at_first=B.window_refusal(lines, i, n, flags) or "")
    return out


def _stem(rel):
    return os.path.splitext(os.path.basename(rel.replace("\\", "/")))[0]


def title_for(conn, rel, text):
    """-> (title, source, binding_line, binding_ratio) per the module header's order."""
    row = conn.execute(
        "SELECT binding FROM litkb.file_versions WHERE rel_path = %s AND binding IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 1", (rel,)).fetchone()
    if row and (row[0] or {}).get("registry_title"):
        b = row[0]
        return b["registry_title"], "binding.registry_title", b.get("line"), b.get("ratio")
    from litkb.admit.resolver import normalize_doi

    for m in _DOI.finditer(text or ""):
        hit = conn.execute(
            "SELECT w.title FROM litkb.main_identifiers i JOIN litkb.main_works w "
            "ON w.work_id = i.work_id WHERE i.scheme = 'doi' AND i.active AND i.status = 'active' "
            "AND i.value_norm = %s", (normalize_doi(m.group().rstrip(".)")),)).fetchone()
        if hit:
            return hit[0], "printed-doi", None, None
    stem = _stem(rel)
    for rel2, title in conn.execute(
            "SELECT f.rel_path, w.title FROM litkb.main_files f JOIN litkb.main_works w "
            "ON w.work_id = f.work_id WHERE f.status = 'active'").fetchall():
        if _stem(rel2) == stem:
            return title, "file-stem", None, None
    hit = conn.execute("SELECT title FROM litkb.main_works WHERE key = %s", (stem,)).fetchone()
    if hit:
        return hit[0], "works.key", None, None
    return None, "none", None, None


def snapshot_set(conn, root):
    """rel_paths: every *.txt under _litkb_staging/web/ plus every `web snapshot` row's path."""
    web = Path(root).joinpath(*WEB_DIR)
    rels = {f"{'/'.join(WEB_DIR)}/{p.name}" for p in web.glob("*.txt")} if web.is_dir() else set()
    rels |= {r[0] for r in conn.execute(
        "SELECT DISTINCT rel_path FROM litkb.file_versions WHERE copy_kind = 'web snapshot'").fetchall()}
    return sorted(rels)


def measure_all(conn, root):
    from litkb.admit import binding as B

    rows = []
    for rel in snapshot_set(conn, root):
        path = Path(root) / rel.replace("/", os.sep)
        base = {"rel_path": rel, "title_region_lines": B.TITLE_REGION_LINES}
        if not path.exists():
            rows.append(dict(base, kind="missing-on-disk", title_source="none"))
            continue
        data = path.read_bytes()
        text = data.decode("utf-8", "replace")
        kind = "html-snapshot" if Path(str(path) + ".snapshot.json").exists() else "page1-text"
        title, source, bline, bratio = title_for(conn, rel, text)
        row = dict(base, kind=kind, bytes=len(data), sha256_12=hashlib.sha256(data).hexdigest()[:12],
                   title_source=source, title=(title or "")[:200], binding_line=bline,
                   binding_ratio=bratio)
        if title:
            row.update(measure_text(text, title))
        else:
            row["n_lines"] = len(B.page_lines(text))
        rows.append(row)
    return rows


def main(argv=None):
    from litkb.acquire.store import LITERATURE_ROOT
    from litkb.db import connect as c

    ap = argparse.ArgumentParser(description="where the title lands on every web snapshot")
    ap.add_argument("--db", default=c.DB_MAIN)
    ap.add_argument("--root", default=str(LITERATURE_ROOT))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    conn = c.connect(a.db, "litkb_reader", autocommit=True)
    try:
        rows = measure_all(conn, a.root)
    finally:
        conn.close()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    measured = [r for r in rows if r.get("first_index") is not None]
    html = [r for r in measured if r["kind"] == "html-snapshot"]
    over = [r for r in measured if not r["within_region"]]
    print(f"snapshots={len(rows)} with_title={sum(1 for r in rows if r.get('title_source') not in (None, 'none'))} "
          f"title_found={len(measured)} (html-snapshot {len(html)}) -> {a.out}")
    print(f"max first_index: all={max((r['first_index'] for r in measured), default=None)} "
          f"html-snapshot={max((r['first_index'] for r in html), default=None)}  "
          f"TITLE_REGION_LINES={rows[0]['title_region_lines'] if rows else '?'}  "
          f"rows past the ceiling={len(over)}")
    for r in rows:
        print("  " + json.dumps({k: r.get(k) for k in ("rel_path", "kind", "title_source",
                                                        "first_index", "first_ratio",
                                                        "within_region", "best_ratio",
                                                        "refusal_at_first", "binding_line")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""litkb acquisition probe 3 (read-only): the baselines the coverage target is measured against — the tracker's
denominator and identifier mix, the corpus's coverage today, and the Crossref work-class of every archive miss,
every Sci-Hub-blocked DOI and every open-access bad-file DOI (so a preprint sent to a shadow route, or a chapter
sent to the paper namespace, is visible as a routing error). Writes phase4/qc/litkb_acq_probe_baselines.md.
First run 2026-09-22 from the jobs folder; moved into the repository unchanged except for its paths.
"""
import collections
import csv
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
TRACKER = ROOT / "Reports" / "literature_tracker.csv"
OUT = ROOT / "phase4" / "qc" / "litkb_acq_probe_baselines.md"
UA = "litkb-probe/0.1 (mailto:chillozone1@gmail.com)"


def crossref_type(doi):
    req = urllib.request.Request(f"https://api.crossref.org/works/{doi}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            m = json.load(r)["message"]
            return m.get("type"), (m.get("container-title") or [""])[0][:40], m.get("publisher", "")[:30], bool(m.get("ISBN"))
    except urllib.error.HTTPError as e:
        return f"http-{e.code}", "", "", False
    except Exception:  # noqa: BLE001 - a probe records the failure, never raises
        return "err", "", "", False


def main():
    out = []
    rows = list(csv.DictReader(TRACKER.open(encoding="utf-8-sig")))
    cols = list(rows[0].keys())
    idcol = next((c for c in cols if "doi" in c.lower() or "url" in c.lower()), None)
    out.append(f"## 1. Tracker denominator\n- rows: {len(rows)}; columns: {cols}; identifier column used: {idcol!r}")
    mix = collections.Counter()
    for r in rows:
        v = (r.get(idcol) or "").strip() if idcol else ""
        if re.search(r"10\.\d{4,9}/", v):
            mix["doi"] += 1
        elif re.search(r"arxiv\.org|\b\d{4}\.\d{4,5}\b", v, re.I):
            mix["arxiv"] += 1
        elif v.startswith("http"):
            mix["url"] += 1
        elif v:
            mix["other-text"] += 1
        else:
            mix["empty"] += 1
    out.append(f"- identifier mix: {dict(mix)}")

    c = psycopg.connect("host=localhost port=5433 dbname=litkb user=litkb_reader")
    n_works = c.execute("SELECT count(*) FROM litkb.main_works").fetchone()[0]
    n_file = c.execute("SELECT count(DISTINCT work_id) FROM litkb.main_files WHERE status='active'").fetchone()[0]
    n_blocks = c.execute("SELECT count(DISTINCT f.work_id) FROM litkb.main_files f WHERE f.status='active' AND EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id=f.file_id)").fetchone()[0]
    types = c.execute("SELECT type, count(*) FROM litkb.main_works GROUP BY 1 ORDER BY 2 DESC").fetchall()
    out.append(f"## 2. Corpus coverage today\n- main_works: {n_works}; with an active file: {n_file} ({100 * n_file / max(n_works, 1):.0f} %); with blocks: {n_blocks}\n- work types: {types}")

    classes = (("annas not-in-archive", "annas", "not-in-archive"), ("scihub blocked", "scihub", "blocked"), ("open_access bad-file", "open_access", "bad-file"))
    for label, route, status in classes:
        ids = [r[0] for r in c.execute("SELECT DISTINCT identifier_used FROM litkb.acquisition_attempts WHERE route=%s AND status=%s ORDER BY 1", (route, status)).fetchall()]
        kinds = collections.Counter()
        detail = []
        for i in ids:
            if not i.startswith("10."):
                kinds["non-doi"] += 1
                detail.append((i[:50], "non-doi"))
                continue
            typ, cont, pub, isbn = crossref_type(i)
            time.sleep(0.7)
            kinds[typ] += 1
            detail.append((i, typ, cont, pub, isbn))
        out.append(f"## 3. Work-class of {label} ({len(ids)} identifiers)\n- Crossref types: {dict(kinds)}\n" + "\n".join(f"  - {d}" for d in detail))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n\n".join(out) + "\n", encoding="utf-8")
    print("\n\n".join("\n".join(o.split("\n")[:3]) for o in out))
    print("->", OUT)


if __name__ == "__main__":
    main()

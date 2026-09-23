"""Cross-page fragments of TOOL text: re-run reconcile on stored artifacts, before vs after stage5-4.

    PYTHONUTF8=1 PYTHONPATH=<tree>/Scripts/pipeline py -3.12 qc/instruments/litkb_fragment_text.py \
        --label before|after --out <rows.jsonl>
    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_fragment_text.py --compare <before.jsonl> <after.jsonl> \
        --csv ../Reports/LITKB_FRAGMENT_TEXT_2026-09-22.csv

CORPUS-WIDE (auditor-D2 F5/F6): ``--corpus --out <rows.jsonl>`` re-runs reconcile on EVERY stored P5
artifact pair (TEI + Docling JSON + the PDF the census names), one JSON line per file, and
``--compare-corpus BEFORE AFTER --csv ../Reports/LITKB_FRAGMENT_TEXT_CORPUS_2026-09-22.csv`` counts,
per file and in a TOTAL row, the blocks, the merges, the empty-text blocks and fragments, and the
boxes that exist after and not before.

WHICH CODE is measured is the ``PYTHONPATH`` the caller gives: the same instrument run once over
main's ``pipeline/`` (``stage5-3``) and once over the branch's (``stage5-4``), on the SAME inputs,
is the before/after. The instrument records ``reconcile.PIPELINE_VERSION`` in every row, so a row
cannot be read under the wrong label. Nothing needs a GPU or a tool: the inputs are the
ARTIFACTS the live runs were made from (the Docling JSON the run row names, the P5 TEI keyed by
the file's sha256) plus the PDF, and reconcile is a pure function of them.

THE POPULATION is read from ``litkb`` as ``litkb_reader`` (read-only), from CURRENT runs only:

* ``identical`` — survey-code C3's set: fragment blocks (> 40 characters) whose text is
  byte-identical on two or more pages of one run (12 groups in 5 runs on 2026-09-22);
* ``tool-cross-page`` — every fragment block that crosses a page (``continues_from`` /
  ``continues_to``) and whose text came from the TOOL (``text_source`` ``ocr`` or ``tool``): the
  path stage5-4 changes.

Each DB block is found in the re-run by page and box (every coordinate within
:data:`BOX_TOL`); a block with no such partner is reported ``unmatched``, never guessed. What is
compared is the stored text length and whether the text is identical to the text another page of
the same group holds.

A file whose run was made WITH a TEI that is not on disk (``litkb hunt`` never writes its TEI:
``hunt.extract_and_ingest``) cannot be re-run as it was made; its rows say ``tei_missing`` and are
re-run Docling-only, which is a DIFFERENT reconciliation — the compare step reports them apart.
"""
import argparse
import collections
import csv
import json
import os

#: Box agreement for "the same block" between a DB row and a re-run canonical block. Both are
#: floats written from the same arithmetic on the same artifact; 0.01 pt is rounding, not slack.
BOX_TOL = 0.01

P5_DERIVED = os.environ.get("LITKB_P5_DERIVED", r"D:\edmonds-pipeline\litkb_derived\p5")
LIT_ROOT = os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture")
READER = "host=localhost port=5433 dbname=litkb user=litkb_reader"

_TARGETS = """
WITH frag AS (
  SELECT b.id, b.file_id, b.run_id, b.page_no, b.bbox, b.text, b.text_source, b.source,
         b.provenance, md5(b.text) AS h
    FROM litkb.blocks b JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id
   WHERE b.provenance ? 'fragment'),
ident AS (
  SELECT run_id, h FROM frag WHERE length(text) > 40
   GROUP BY run_id, h HAVING count(DISTINCT page_no) >= 2)
SELECT 'identical' AS why, fr.run_id::text || ':' || fr.h AS grp, fr.*
  FROM frag fr JOIN ident i ON i.run_id = fr.run_id AND i.h = fr.h AND length(fr.text) > 40
UNION ALL
SELECT 'tool-cross-page', fr.id::text, fr.*
  FROM frag fr
 WHERE fr.text_source IN ('ocr', 'tool')
   AND (fr.provenance ? 'continues_from' OR fr.provenance ? 'continues_to')
"""


def _census():
    recs = {}
    for name in ("inventory_census.jsonl", "inventory_extra.jsonl"):
        p = os.path.join(P5_DERIVED, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    r = json.loads(line)
                    recs.setdefault(r["sha256"], r)
    return recs


def measure(label):
    import psycopg

    from litkb.extract import docling as D
    from litkb.extract import inventory as I
    from litkb.extract import reconcile as R

    conn = psycopg.connect(READER)
    try:
        cur = conn.execute(_TARGETS)
        cols = [d.name for d in cur.description]
        targets = [dict(zip(cols, r)) for r in cur.fetchall()]
        files = {}
        for fid in {t["file_id"] for t in targets}:
            files[fid] = conn.execute(
                "SELECT w.key, mf.rel_path, f.sha256, r.artifact_path, r.pipeline_version "
                "FROM litkb.files f JOIN litkb.main_files mf ON mf.file_id = f.id "
                "JOIN litkb.main_works w ON w.work_id = mf.work_id "
                "JOIN litkb.extraction_runs r ON r.id = f.current_run_id WHERE f.id = %s",
                (fid,)).fetchone()
    finally:
        conn.close()
    census = _census()
    rows = []
    for fid, (key, rel, sha, artifact, run_version) in sorted(files.items(), key=lambda kv: kv[1][0]):
        pdf = os.path.join(LIT_ROOT, rel)
        tei_path = os.path.join(P5_DERIVED, "tei", sha + ".tei.xml")
        tei = open(tei_path, "rb").read() if os.path.exists(tei_path) else None
        doc = D.load(artifact) if artifact and os.path.exists(artifact) else None
        rec = census.get(sha) or I.probe_file(pdf)
        frames = I.page_frames(pdf)
        canonical, _dis, stats = R.reconcile(pdf, tei, doc, rec,
                                             ocr_pages=rec.get("ocr_pages") or (), frames=frames)
        for t in (t for t in targets if t["file_id"] == fid):
            box = [float(v) for v in t["bbox"]]
            hit = [c for c in canonical if c.page == t["page_no"]
                   and all(abs(a - b) <= BOX_TOL for a, b in zip(c.bbox, box))]
            c = hit[0] if len(hit) == 1 else None
            rows.append({
                "label": label, "reconcile_version": R.PIPELINE_VERSION, "work_key": key,
                "run_version": run_version, "why": t["why"], "group": t["grp"],
                "block_id": str(t["id"]), "page": t["page_no"], "source": t["source"],
                "db_text_source": t["text_source"], "db_len": len(t["text"]), "db_md5": t["h"],
                "tei_on_disk": tei is not None, "docling_on_disk": doc is not None,
                "match": "matched" if c is not None else ("ambiguous" if hit else "unmatched"),
                "rerun_len": len(c.text) if c is not None else None,
                "rerun_text_source": c.text_source if c is not None else None,
                "rerun_page_text": (c.extractor or {}).get("page_text") if c is not None else None,
                "rerun_text": c.text if c is not None else None,
                "rerun_blocks_in_file": stats["blocks"],
                "rerun_fragment_page_text": stats.get("fragment_page_text"),
            })
    return rows


def compare(before_path, after_path, csv_path):
    def load(p):
        with open(p, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    before, after = load(before_path), load(after_path)
    a_by = {(r["why"], r["block_id"]): r for r in after}
    out = []
    for b in before:
        a = a_by.get((b["why"], b["block_id"]))
        out.append({
            "why": b["why"], "work_key": b["work_key"], "group": b["group"], "page": b["page"],
            "source": b["source"], "db_text_source": b["db_text_source"], "db_len": b["db_len"],
            "tei_on_disk": b["tei_on_disk"],
            "before_version": b["reconcile_version"], "before_match": b["match"],
            "before_len": b["rerun_len"], "before_page_text": b["rerun_page_text"],
            "before_reproduces_db": (b["rerun_text"] is not None
                                     and len(b["rerun_text"]) == b["db_len"]),
            "after_version": a["reconcile_version"] if a else None,
            "after_match": a["match"] if a else None,
            "after_len": a["rerun_len"] if a else None,
            "after_page_text": a["rerun_page_text"] if a else None,
            "before_blocks_in_file": b["rerun_blocks_in_file"],
            "after_blocks_in_file": a["rerun_blocks_in_file"] if a else None,
        })
    # identical-across-pages, per group, before and after (the defect's own test)
    for label, rows in (("before", before), ("after", after)):
        grp = collections.defaultdict(set)
        for r in rows:
            if r["rerun_text"] is not None:
                grp[(r["why"], r["group"])].add(r["rerun_text"])
        for o in out:
            key = (o["why"], o["group"])
            members = [r for r in rows if (r["why"], r["group"]) == key]
            o[f"{label}_group_identical"] = (len(members) > 1 and len(grp[key]) == 1
                                             and all(r["rerun_text"] is not None for r in members))
    cols = list(out[0].keys()) if out else []
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    return out


# ── corpus-wide (auditor-D2 F5/F6): every stored P5 artifact pair, not only the cross-page set ──

#: Block kinds that carry TEXT. A table's or a figure's `text` is empty or a caption by design, so an
#: empty one is not a fragment that lost its words.
TEXT_KINDS = ("paragraph", "heading", "caption", "footnote", "reference", "equation", "furniture",
              "title", "author", "affiliation")


def _box(c):
    return f"{c.page}:" + ",".join(f"{v:.2f}" for v in c.bbox)


def _one_file(args):
    """Reconcile ONE stored P5 artifact pair (TEI + Docling JSON + the PDF) with whatever `litkb` is on
    the path. -> a summary row, or {"sha", "error"}; never raises (one bad file is not a run)."""
    sha, rec = args
    from litkb.extract import docling as D
    from litkb.extract import inventory as I
    from litkb.extract import reconcile as R

    try:
        pdf = rec["path"]
        tei_path = os.path.join(P5_DERIVED, "tei", sha + ".tei.xml")
        tei = open(tei_path, "rb").read() if os.path.exists(tei_path) else None
        doc = D.load(os.path.join(P5_DERIVED, "docling", sha + ".docling.json"))
        canonical, _dis, st = R.reconcile(pdf, tei, doc, rec, ocr_pages=rec.get("ocr_pages") or (),
                                          frames=I.page_frames(pdf))
        empty = [c for c in canonical if c.kind in TEXT_KINDS and not (c.text or "").strip()]
        return {"sha": sha, "name": os.path.basename(pdf), "version": R.PIPELINE_VERSION,
                "blocks": len(canonical), "merged_regions": st["merged_regions"],
                "dropped_overmerges": st["dropped_overmerges"],
                "fragment_page_text": st.get("fragment_page_text") or {},
                "empty_text_blocks": len(empty),
                "empty_text_fragments": sum(1 for c in empty if (c.extractor or {}).get("fragment")),
                "empty_sentence_fragments": sum(1 for c in empty
                                                if (c.extractor or {}).get("page_text") == "sentence"),
                "boxes": sorted(_box(c) for c in canonical),
                "empty_boxes": sorted(_box(c) for c in empty)}
    except Exception as e:  # noqa: BLE001 - reported per file, never a dead run
        return {"sha": sha, "error": f"{type(e).__name__}: {e}"[:300]}


def measure_corpus(workers=4):
    import concurrent.futures

    census = _census()
    shas = sorted(f.split(".")[0] for f in os.listdir(os.path.join(P5_DERIVED, "docling"))
                  if f.endswith(".docling.json"))
    todo = [(s, census[s]) for s in shas if s in census]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_one_file, todo))


def compare_corpus(before_path, after_path, csv_path):
    """-> per-file rows (and a TOTAL row) comparing two corpus runs: blocks, empty-text blocks and
    fragments, and how many of the AFTER boxes did not exist BEFORE (and how many of those are empty)."""
    def load(p):
        with open(p, encoding="utf-8") as fh:
            return {r["sha"]: r for r in (json.loads(line) for line in fh)}

    b, a = load(before_path), load(after_path)
    out = []
    for sha in sorted(set(b) | set(a)):
        x, y = b.get(sha, {}), a.get(sha, {})
        if "error" in x or "error" in y or not x or not y:
            out.append({"name": x.get("name") or y.get("name") or sha, "error": x.get("error") or y.get("error")
                        or "missing on one side"})
            continue
        bb, ab = set(x["boxes"]), set(y["boxes"])
        new = ab - bb
        out.append({
            "name": x["name"], "error": "",
            "before_blocks": x["blocks"], "after_blocks": y["blocks"],
            "before_merged": x["merged_regions"], "after_merged": y["merged_regions"],
            "before_dropped_overmerges": x["dropped_overmerges"],
            "after_dropped_overmerges": y["dropped_overmerges"],
            "before_empty_text_blocks": x["empty_text_blocks"], "after_empty_text_blocks": y["empty_text_blocks"],
            "before_empty_text_fragments": x["empty_text_fragments"],
            "after_empty_text_fragments": y["empty_text_fragments"],
            "after_empty_sentence_fragments": y["empty_sentence_fragments"],
            "new_boxes": len(new), "gone_boxes": len(bb - ab),
            "new_boxes_empty": len(new & set(y["empty_boxes"])),
            "after_page_text": json.dumps(y["fragment_page_text"], sort_keys=True),
        })
    ok = [r for r in out if not r["error"]]
    total = {"name": "TOTAL", "error": f"{len(out) - len(ok)} files errored"}
    for k in ok[0] if ok else []:
        if k not in ("name", "error", "after_page_text"):
            total[k] = sum(r[k] for r in ok)
    total["files_blocks_changed"] = sum(1 for r in ok if r["before_blocks"] != r["after_blocks"])
    out.append(total)
    cols = list(dict.fromkeys(k for r in out for k in r))
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    return total


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", choices=("before", "after"))
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--csv")
    ap.add_argument("--corpus", action="store_true",
                    help="every stored P5 artifact pair (with --out: one JSON line per file)")
    ap.add_argument("--compare-corpus", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if a.compare_corpus:
        total = compare_corpus(a.compare_corpus[0], a.compare_corpus[1], a.csv)
        print(json.dumps(total))
        return 0
    if a.corpus:
        rows = measure_corpus(a.workers)
        with open(a.out, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
        print(f"corpus rows={len(rows)} errors={sum('error' in r for r in rows)} out={a.out}")
        return 0
    if a.compare:
        out = compare(a.compare[0], a.compare[1], a.csv)
        print(f"rows={len(out)} csv={a.csv}")
        return 0
    rows = measure(a.label)
    with open(a.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    print(f"label={a.label} rows={len(rows)} out={a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Everything acquired is readable or classified: the ONE home of the readability classes
(LITKB_WORKPLAN.md "### S4"; S4 run 3 decision D8; docs/SCHEMAS.md "litkb readability classes").

    from litkb import readability as R
    res = R.classify(reader, workstreams=[ws_id, ...], root=LITERATURE_ROOT)
    R.counters(res)                     # unclassified_acquired_files + REPORTED per-class counts
    R.write_csv(res, path)              # Reports/LITKB_READABILITY_<date>.csv

THE CLASSES (closed; decision D8):
  file   `extracted`, with a reason: `full` · `docling-only` · `grobid-only` · `ocr` · `snapshot`
         and the residue classes `scan-needs-ocr` · `over-page-cap` · `zero-content` · `bad-file` ·
         `probe-error` · `book` · `refused-registry`
  work   `no-file-any-route`; plus the per-file ROLLUP of a work that holds files — its one class when
         every file agrees, `mixed` when they do not (a work holding an extracted file AND a residue
         file is `mixed`, never silently `extracted`: per-file completeness)
A file with no class is UNCLASSIFIED — `None` here, an empty cell in the CSV — and is NEVER defaulted
into one. `queued`/`leased` are not classes: a file still waiting counts as unclassified at grading.

THE UNIVERSE (three kinds of row):
  file     every CURRENT file version in main (`litkb.main_files`) and in each NAMED workstream
           (`litkb.ws_files`, deduplicated on (file_id, version_id) against main's).
  staging  unbound bytes in `_litkb_staging/` owned ONLY by a REFUSED admission's checks (the
           reaper's third ownership leg, `ops.reaper.known_rel_paths`): the admission's
           `checks->'web'->>'document'`, or its `->>'snapshot'` when there is no document (then the
           snapshot IS the acquired source). Bytes whose sha256 a `files` row holds, or whose path a
           `file_versions` row names, are owned by that row and are not here. → `refused-registry`.
  work     every admitted work in main. No file → `no-file-any-route` when every route that APPLIES
           to it (`acquire.run.ROUTES`: open_access needs a DOI or an arXiv id, annas and scihub a
           DOI) has an attempt that actually ran (a `quota-stop` requested nothing, so it is not one)
           and no attempt anywhere is `ok`; otherwise `not-attempted`, REPORTED and outside the gated
           universe. With files → the rollup.

PER FILE, FROM EVIDENCE ONLY, in this order (the first rule that answers wins; `RULES` below):
  status     a current version whose status is not `active` is UNCLASSIFIED (and said so)
  bad-file   not on disk · its sha256 is not `files.sha256` · a PDF path without `%PDF-` magic
  snapshot   a text source (`copy_kind = 'web snapshot'`, or a `.txt` path): its current run's text →
             `extracted/snapshot`; a run with no text → `zero-content`; no run → unclassified
  probe      `probe.probe_pages` / `probe.page_text_chars` RAISE → `probe-error` (never the stored
             page count, never the stored page-1 `has_text_layer` flag)
  book       the work's `type` is `book` (`litkb-book-policy`: S4 names it and never extracts it)
  cap        pages > `probe.EXTRACT_PAGE_CAP` → `over-page-cap` (Kam ruling `litkb-extract-page-cap`)
  run        a current run whose canonical blocks carry NO text → `scan-needs-ocr` when the file has
             image pages, else `zero-content`; image pages that no text block covers and no OCR'd run
             covers → `scan-needs-ocr`; otherwise `extracted`, with the reason `snapshot` (stage
             `5-text-snapshot`), `ocr` (the run's metrics say `ocr: true`, or a page with ZERO native
             characters carries text — only OCR puts it there), else from the metrics the reconciler
             writes: `docling_regions` and `grobid_regions` both > 0 → `full`, only docling →
             `docling-only`, only GROBID → `grobid-only`. Missing metrics → unclassified.
  scan       no current run, image pages → `scan-needs-ocr` (the queue routes such a file to OCR)
  row        no class yet, and an UNCLEARED `litkb.quarantine_payloads` row refuses this file (by
             file_id or path) as `bad-file` / `zero-content` / `probe-error` → that class (the row IS
             the state)
An IMAGE page is `probe.image_page_numbers`'s (decision D13): ZERO native characters AND at least one
raster image. It replaced "under 200 characters", which put three figure pages whose captions are
native text (Pauls_2025 p16, Pesonen_2026 p20, Guo_2019 p6) into `scan-needs-ocr` — builder-B's first
live score, 2026-09-22. "Covered" = the page carries at least one canonical text block, or the run's
metrics say `ocr: true`; since an image page has no native text, a text block on one IS OCR evidence.

THE CLASSIFIER CAN REFUSE A BOUND FILE (`record=` an ingest connection): a file it classes `bad-file`,
`zero-content` or `probe-error` gets a `litkb.quarantine_payloads` row against its CURRENT bound path
with its file_id (origin `classifier`) — the bytes are NOT moved; the row is the state. When a later
`record=` run classes that file `extracted`, it CLEARS its own row (`quarantine.clear_system`:
when, by which session, why); a moved-payload row is never cleared. The default writes nothing: a
read-only classification is what the CSV and the acceptance read, and it REPORTS
`stale_quarantine_rows` — uncleared classifier rows on files it now classes `extracted`.
"""
import csv
import datetime
import os
from pathlib import Path

from litkb.extract import probe as _probe

FILE_CLASSES = ("extracted", "scan-needs-ocr", "over-page-cap", "zero-content", "bad-file",
                "probe-error", "book", "refused-registry")
EXTRACTED_REASONS = ("full", "docling-only", "grobid-only", "ocr", "snapshot")
RESIDUE_CLASSES = tuple(c for c in FILE_CLASSES if c != "extracted")
#: the work classes: the one D8 names, and the rollup word for a work whose files disagree
WORK_CLASSES = ("no-file-any-route", "mixed")
#: REPORTED, outside the gated universe: a file-less work some applicable route never ran for
NOT_ATTEMPTED = "not-attempted"
#: the classes the classifier records a quarantine row for when asked (`record=`)
REFUSED_CLASSES = ("bad-file", "zero-content", "probe-error")

TEXT_STAGE = "5-text-snapshot"
RECONCILE_STAGE = "5-reconcile"

CSV_COLUMNS = ("row_kind", "key", "work_id", "file_id", "rel_path", "pages", "image_pages", "class",
               "reason", "evidence", "quarantine_ids", "current_run_id", "blocks", "text_chars", "scope")

REPORTS = Path(__file__).resolve().parents[3] / "Reports"


# ── evidence ──────────────────────────────────────────────────────────────────────────────────

def _sha256(path):
    from litkb.quarantine import sha256_of

    return sha256_of(path)[0]


def _is_text_source(f):
    return f.get("copy_kind") == "web snapshot" or str(f.get("rel_path") or "").lower().endswith(".txt")


def evidence_of(f, *, root, run, pages_blocks, qrows, cap=None):
    """Everything the rules read about ONE file, measured now. `run` is the current run's row (or
    None); `pages_blocks` {page_no: (text_blocks, text_chars)} of its canonical blocks; `qrows` the
    quarantine rows that name this file."""
    cap = _probe.EXTRACT_PAGE_CAP if cap is None else cap
    p = Path(root) / str(f["rel_path"])
    ev = {"status": f.get("status"), "exists": p.is_file(), "text_source": _is_text_source(f),
          "work_type": f.get("work_type"), "cap": cap, "run": run, "pages_blocks": pages_blocks or {},
          "qrows": qrows or [], "pages": None, "chars": None, "image_pages": [], "probe_error": None,
          "sha_ok": None, "magic": None}
    if not ev["exists"]:
        return ev
    ev["sha_ok"] = (_sha256(p) == f.get("sha256"))
    if ev["text_source"]:
        return ev
    ev["magic"] = _probe.is_pdf_magic(p)
    if not ev["magic"]:
        return ev
    try:
        ev["pages"] = _probe.probe_pages(p)
        if ev["pages"] <= cap:
            ev["chars"] = _probe.page_text_chars(p)
            ev["image_pages"] = _probe.image_pages(ev["chars"], _probe.page_raster_images(p))
    except _probe.ProbeError as e:
        ev["probe_error"] = str(e)[:300]
    return ev


def _run_is_ocr(run):
    m = (run or {}).get("metrics") or {}
    return m.get("ocr") is True


def _text_totals(pages_blocks):
    return (sum(n for n, _c in pages_blocks.values()), sum(c for _n, c in pages_blocks.values()))


# ── the rules, in order: each returns (class, reason, note) or None ───────────────────────────

def _r_status(ev):
    if ev["status"] != "active":
        return None, None, f"current version status is {ev['status']!r}, not active"


def _r_bad_file(ev):
    if not ev["exists"]:
        return "bad-file", None, "not on disk at its rel_path"
    if ev["sha_ok"] is False:
        return "bad-file", None, "sha256 on disk differs from files.sha256"
    if not ev["text_source"] and ev["magic"] is False:
        return "bad-file", None, "no %PDF- signature in the first 1,024 bytes"


def _r_snapshot(ev):
    if not ev["text_source"]:
        return None
    run = ev["run"]
    if not run:
        return None, None, "a text source with no current run (waiting)"
    n, chars = _text_totals(ev["pages_blocks"])
    if n and chars:
        return "extracted", "snapshot", f"{n} text blocks, {chars} chars"
    return "zero-content", None, "a text source whose current run holds no text"


def _r_probe(ev):
    if ev["probe_error"]:
        return "probe-error", None, ev["probe_error"]


def _r_book(ev):
    if ev["work_type"] == "book":
        return "book", None, "work type is book (litkb-book-policy: never extracted in S4)"


def _r_cap(ev):
    if ev["pages"] is not None and ev["pages"] > ev["cap"]:
        return "over-page-cap", None, f"{ev['pages']} pages > EXTRACT_PAGE_CAP {ev['cap']}"


def _r_run(ev):
    run = ev["run"]
    if not run:
        return None
    pb, img = ev["pages_blocks"], ev["image_pages"]
    n, chars = _text_totals(pb)
    if not n or not chars:
        if img:
            return "scan-needs-ocr", None, f"current run holds no text; {len(img)} image pages"
        return "zero-content", None, "a text-layer file whose current run holds no text"
    ocr = _run_is_ocr(run)
    uncovered = [pg for pg in img if not (pb.get(pg, (0, 0))[0])]
    if uncovered and not ocr:
        return "scan-needs-ocr", None, f"image pages with no text and no OCR'd run: {_span(uncovered)}"
    if run.get("stage") == TEXT_STAGE:
        return "extracted", "snapshot", f"{n} text blocks"
    zero_with_text = [pg for pg in img if ev["chars"] and ev["chars"][pg - 1] == 0 and pb.get(pg, (0, 0))[0]]
    if ocr or zero_with_text:
        return "extracted", "ocr", ("metrics ocr=true" if ocr else
                                    f"text on zero-native-character pages {_span(zero_with_text)}")
    m = run.get("metrics") or {}
    d, g = m.get("docling_regions"), m.get("grobid_regions")
    if not isinstance(d, int) or not isinstance(g, int):
        return None, None, "current run metrics carry no docling_regions/grobid_regions"
    if d > 0 and g > 0:
        return "extracted", "full", f"docling_regions {d}, grobid_regions {g}"
    if d > 0:
        return "extracted", "docling-only", f"docling_regions {d}, grobid_regions 0"
    if g > 0:
        return "extracted", "grobid-only", f"docling_regions 0, grobid_regions {g}"
    return None, None, "current run metrics show no region from either tool"


def _r_scan(ev):
    if not ev["run"] and ev["image_pages"]:
        return "scan-needs-ocr", None, f"no current run; image pages {_span(ev['image_pages'])}"


def _r_row(ev):
    for q in ev["qrows"]:
        if q["reason"] in REFUSED_CLASSES and not q.get("cleared_at"):
            return q["reason"], None, f"quarantine row {q['id']} ({q['origin']})"


#: (name, rule). `fire_unclassified` drops one by name — the runtime form of the mutation the
#: design contract asks for — and qc/test_litkb_readability.py mutates the SOURCE the same way.
RULES = (("status", _r_status), ("bad-file", _r_bad_file), ("snapshot", _r_snapshot),
         ("probe-error", _r_probe), ("book", _r_book), ("over-page-cap", _r_cap), ("run", _r_run),
         ("scan-needs-ocr", _r_scan), ("quarantine-row", _r_row))


def _span(pages):
    pages = list(pages)
    return ",".join(str(p) for p in pages[:12]) + (f",…(+{len(pages) - 12})" if len(pages) > 12 else "")


def decide(ev, rules=RULES):
    """-> (class | None, reason | None, [notes]). The first rule that answers decides; a rule that
    answers (None, None, note) decides UNCLASSIFIED and says why; no rule answering is unclassified
    with the note 'no rule matched (waiting)'."""
    notes = []
    for _name, rule in rules:
        out = rule(ev)
        if out is None:
            continue
        cls, reason, note = out
        notes.append(note)
        if cls is None:
            # an explicit "unclassified" answer stops at the status rule only; the others (a text
            # source waiting, metrics missing) still let a quarantine row speak
            if _name == "status":
                return None, None, notes
            continue
        return cls, reason, notes
    if not notes:
        notes.append("no rule matched (waiting for extraction)")
    return None, None, notes


# ── the universe ──────────────────────────────────────────────────────────────────────────────

_FILE_COLS = ("file_id", "version_id", "work_id", "key", "work_type", "rel_path", "sha256", "status",
              "current_run_id", "copy_kind", "pages_db", "bytes")


def _main_files(conn, work_id=None):
    rows = conn.execute(
        "SELECT f.file_id::text, f.version_id::text, f.work_id::text, w.key, w.type, f.rel_path, f.sha256, "
        "       f.status, f.current_run_id::text, f.copy_kind, f.pages, f.bytes "
        "  FROM litkb.main_files f LEFT JOIN litkb.main_works w ON w.work_id = f.work_id "
        " WHERE %s::uuid IS NULL OR f.work_id = %s::uuid ORDER BY w.key, f.rel_path",
        (work_id, work_id)).fetchall()
    return [dict(zip(_FILE_COLS, r)) | {"scope": "main"} for r in rows]


def _ws_files(conn, workstreams):
    if not workstreams:
        return []
    rows = conn.execute(
        "SELECT wf.view_workstream_id::text, wf.file_id::text, wf.version_id::text, wf.work_id::text, "
        "       ww.key, ww.type, wf.rel_path, wf.sha256, wf.status, wf.current_run_id::text, wf.copy_kind, "
        "       wf.pages, wf.bytes "
        "  FROM litkb.ws_files wf LEFT JOIN litkb.ws_works ww "
        "       ON ww.view_workstream_id = wf.view_workstream_id AND ww.work_id = wf.work_id "
        " WHERE wf.view_workstream_id = ANY(%s::uuid[]) ORDER BY ww.key, wf.rel_path",
        ([str(w) for w in workstreams],)).fetchall()
    return [dict(zip(_FILE_COLS, r[1:])) | {"scope": r[0]} for r in rows]


def _runs(conn, run_ids):
    if not run_ids:
        return {}
    return {r[0]: {"id": r[0], "stage": r[1], "status": r[2], "metrics": r[3] or {}}
            for r in conn.execute(
                "SELECT id::text, stage, status, metrics FROM litkb.extraction_runs WHERE id = ANY(%s::uuid[])",
                (list(run_ids),)).fetchall()}


def _pages_blocks(conn, run_ids):
    """{run_id: {page_no: (canonical blocks with text, their characters)}}."""
    out = {}
    if not run_ids:
        return out
    for rid, pg, n, chars in conn.execute(
            "SELECT run_id::text, page_no, count(*) FILTER (WHERE coalesce(length(text), 0) > 0), "
            "       coalesce(sum(length(text)), 0) "
            "  FROM litkb.blocks WHERE run_id = ANY(%s::uuid[]) AND canonical GROUP BY 1, 2",
            (list(run_ids),)).fetchall():
        out.setdefault(rid, {})[pg] = (int(n), int(chars))
    return out


def _qrows(conn):
    from litkb import quarantine as Q

    if not Q.table_present(conn):
        return []
    return [{"id": r[0], "rel_path": r[1], "file_id": r[2], "work_id": r[3], "reason": r[4], "origin": r[5],
             "cleared_at": r[6]}
            for r in conn.execute(
                "SELECT id::text, rel_path, file_id::text, work_id::text, reason, origin, cleared_at "
                "  FROM litkb.quarantine_payloads ORDER BY recorded_at, id").fetchall()]


def _is_own_row(q, f):
    """A classifier row on THIS bound file — the only kind of row the classifier may clear."""
    return q["origin"] == "classifier" and q["file_id"] == f["file_id"] and q["rel_path"] == f["rel_path"]


def _refused_staging(conn, root):
    """Universe (ii): bytes in `_litkb_staging/` that ONLY a refused admission's checks own."""
    from litkb import quarantine as Q

    rows = conn.execute(
        "SELECT a.id::text, a.checks->'web'->>'document', a.checks->'web'->>'snapshot', "
        "       a.checks->'claimed'->>'title' "
        "  FROM litkb.admissions a WHERE a.state = 'refused' AND a.checks ? 'web' ORDER BY a.created_at, a.id"
    ).fetchall()
    bound = {r[0] for r in conn.execute(
        "SELECT DISTINCT rel_path FROM litkb.file_versions WHERE rel_path IS NOT NULL").fetchall()}
    shas = {r[0] for r in conn.execute("SELECT sha256 FROM litkb.files").fetchall()}
    out, skipped = [], []
    seen = set()
    for adm, doc, snap, title in rows:
        rel = doc or snap
        if not rel or rel in seen or not rel.startswith("_litkb_staging/"):
            continue
        seen.add(rel)
        p = Path(root) / rel
        if rel in bound:
            skipped.append({"rel_path": rel, "why": "a file_versions row names this path"})
            continue
        if not p.is_file():
            skipped.append({"rel_path": rel, "why": "not on disk"})
            continue
        sha, n = Q.sha256_of(p)
        if sha in shas:
            skipped.append({"rel_path": rel, "why": "its sha256 is a files row (a copy of held bytes)"})
            continue
        out.append({"row_kind": "staging", "key": Path(rel).stem, "work_id": None, "file_id": None,
                    "rel_path": rel, "pages": None, "image_pages": None, "class": "refused-registry",
                    "reason": None, "evidence": (f"refused admission {adm} (claimed title: {title or '-'}); "
                                                 f"sha256 {sha[:12]}; {n} bytes"),
                    "quarantine_ids": "", "current_run_id": None, "blocks": None, "text_chars": None,
                    "scope": "main"})
    return out, skipped


def _work_rows(conn, file_rows):
    from litkb.acquire.run import ROUTES

    works = conn.execute("SELECT work_id::text, key, type FROM litkb.main_works ORDER BY key").fetchall()
    ids = {}
    for wid, scheme in conn.execute(
            "SELECT work_id::text, scheme FROM litkb.main_identifiers WHERE active AND scheme IN ('doi', 'arxiv')"
    ).fetchall():
        ids.setdefault(wid, set()).add(scheme)
    atts = {}
    for wid, route, status in conn.execute(
            "SELECT work_id::text, route, status FROM litkb.acquisition_attempts WHERE work_id IS NOT NULL"
    ).fetchall():
        atts.setdefault(wid, []).append((route, status))
    by_work = {}
    for r in file_rows:
        if r["scope"] == "main" and r["work_id"]:
            by_work.setdefault(r["work_id"], []).append(r)
    out, anomalies = [], []
    for wid, key, wtype in works:
        files = by_work.get(wid, [])
        row = {"row_kind": "work", "key": key, "work_id": wid, "file_id": None, "rel_path": None,
               "pages": None, "image_pages": None, "class": None, "reason": None, "evidence": "",
               "quarantine_ids": "", "current_run_id": None, "blocks": None, "text_chars": None,
               "scope": "main"}
        active = [f for f in files if f.get("status") == "active"]
        if active:
            classes = {f["class"] for f in active}
            if None in classes:
                row["class"], row["evidence"] = None, f"{len(active)} files; one or more unclassified"
            elif len(classes) == 1:
                row["class"] = classes.pop()
                row["reason"] = "+".join(sorted({f["reason"] for f in active if f["reason"]})) or None
                row["evidence"] = f"{len(active)} file(s), all {row['class']}"
            else:
                row["class"] = "mixed"
                row["evidence"] = "files: " + ", ".join(sorted(f"{f['class']}" for f in active))
            out.append(row)
            continue
        sch = ids.get(wid, set())
        applicable = [r for r in ROUTES if (r == "open_access" and sch) or (r != "open_access" and "doi" in sch)]
        ran = {route for route, status in atts.get(wid, []) if status != "quota-stop"}
        any_ok = any(status == "ok" for _r, status in atts.get(wid, []))
        if any_ok:
            anomalies.append(key)
            row["class"], row["evidence"] = NOT_ATTEMPTED, "an attempt says ok and no active file is bound"
        elif applicable and all(r in ran for r in applicable):
            row["class"] = "no-file-any-route"
            row["evidence"] = "attempts: " + ", ".join(sorted(f"{r}:{s}" for r, s in atts.get(wid, [])))
        else:
            row["class"] = NOT_ATTEMPTED
            missing = [r for r in applicable if r not in ran]
            row["evidence"] = ("no route applies (no DOI or arXiv id)" if not applicable
                               else f"never ran: {', '.join(missing)}")
        out.append(row)
    return out, anomalies


def classify(conn, workstreams=(), *, root=None, cap=None, rules=RULES, record=None, with_works=True,
             session="litkb-readability"):
    """The whole universe. -> {"rows": [...], "counters": {...}, "skipped_staging": [...], ...}.

    Reads the database (any role that can read litkb: the reader is enough) and the disk. Writes
    NOTHING unless `record` is an ingest connection, and then only the classifier's quarantine rows:
    a new row for a bound file it refuses, and the CLEARING of its own row on a file it now classes
    `extracted` (`session` is recorded as `cleared_by`)."""
    from litkb import quarantine as Q
    from litkb.acquire.store import LITERATURE_ROOT

    root = Path(root or os.environ.get("LITKB_LITERATURE_ROOT") or LITERATURE_ROOT)
    files = _main_files(conn)
    seen = {(f["file_id"], f["version_id"]) for f in files}
    for f in _ws_files(conn, workstreams):
        if (f["file_id"], f["version_id"]) not in seen:
            seen.add((f["file_id"], f["version_id"]))
            files.append(f)
    run_ids = {f["current_run_id"] for f in files if f["current_run_id"]}
    runs, pblocks, qrows = _runs(conn, run_ids), _pages_blocks(conn, run_ids), _qrows(conn)
    rows, recorded, cleared = [], [], []
    for f in files:
        mine = [q for q in qrows if q["file_id"] == f["file_id"] or q["rel_path"] == f["rel_path"]]
        run = runs.get(f["current_run_id"]) if f["current_run_id"] else None
        pb = pblocks.get(f["current_run_id"], {}) if run else {}
        ev = evidence_of(f, root=root, run=run, pages_blocks=pb, qrows=mine, cap=cap)
        cls, reason, notes = decide(ev, rules)
        n, chars = _text_totals(pb)
        row = {"row_kind": "file", "key": f["key"], "work_id": f["work_id"], "file_id": f["file_id"],
               "rel_path": f["rel_path"], "pages": ev["pages"], "image_pages": len(ev["image_pages"]),
               "class": cls, "reason": reason, "evidence": "; ".join(x for x in notes if x),
               "quarantine_ids": " ".join(q["id"] for q in mine if not q.get("cleared_at")),
               "current_run_id": f["current_run_id"],
               "blocks": n if run else None, "text_chars": chars if run else None, "scope": f["scope"],
               "status": f["status"], "sha256": f["sha256"], "bytes": f["bytes"]}
        if record is not None and cls in REFUSED_CLASSES and not any(
                q["reason"] == cls and not q.get("cleared_at") for q in mine):
            size = f["bytes"] if f["bytes"] is not None else 0
            res = Q.try_record(Q.record_system, record, rel_path=f["rel_path"], sha256=f["sha256"],
                               nbytes=size, reason=cls, origin="classifier", work_id=f["work_id"],
                               file_id=f["file_id"], detail={"evidence": row["evidence"][:500]})
            row["quarantine_row"] = res
            recorded.append(res)
        own_open = [q for q in mine if _is_own_row(q, f) and not q.get("cleared_at")]
        # BEGIN guard: the classifier clears its own row once the file it refused is extracted
        if record is not None and cls == "extracted" and own_open:
            row["cleared"] = [Q.try_clear(record, q["id"], session=session,
                                          reason=f"classified extracted/{reason}: {row['evidence'][:200]}")
                              for q in own_open]
            cleared.extend(row["cleared"])
            own_open = [q for q, c in zip(own_open, row["cleared"]) if not c.get("ok")]
        # END guard: the classifier clears its own row once the file it refused is extracted
        row["stale_quarantine"] = len(own_open) if cls == "extracted" else 0
        rows.append(row)
    staging, skipped = _refused_staging(conn, root)
    works, anomalies = _work_rows(conn, rows) if with_works else ([], [])
    out = {"rows": rows + staging + works, "skipped_staging": skipped, "work_anomalies": anomalies,
           "workstreams": [str(w) for w in workstreams], "root": str(root),
           "cap": _probe.EXTRACT_PAGE_CAP if cap is None else cap, "recorded": recorded, "cleared": cleared,
           "quarantine_table": Q.table_present(conn),
           "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    out["counters"] = counters(out)
    return out


def counters(res):
    """The gated counter and the REPORTED counts (plan "### S4" (b)).

    `unclassified_acquired_files` counts FILE and STAGING rows with no class — never work rows, whose
    `not-attempted` is reported outside the gated universe."""
    rows = res["rows"]
    acq = [r for r in rows if r["row_kind"] in ("file", "staging")]
    out = {"unclassified_acquired_files": sum(1 for r in acq if r["class"] is None),
           "acquired_files": len(acq),
           "stale_quarantine_rows": sum(r.get("stale_quarantine") or 0 for r in acq)}
    for c in FILE_CLASSES:
        out[f"files_{c}"] = sum(1 for r in acq if r["class"] == c)
    for reason in EXTRACTED_REASONS:
        out[f"extracted_{reason}"] = sum(1 for r in acq if r["class"] == "extracted" and r["reason"] == reason)
    works = [r for r in rows if r["row_kind"] == "work"]
    out["works"] = len(works)
    for c in (*WORK_CLASSES, NOT_ATTEMPTED):
        out[f"works_{c}"] = sum(1 for r in works if r["class"] == c)
    out["works_extracted"] = sum(1 for r in works if r["class"] == "extracted")
    out["works_residue"] = sum(1 for r in works if r["class"] in RESIDUE_CLASSES)
    out["works_unclassified"] = sum(1 for r in works if r["class"] is None)
    return out


def unclassified_acquired_files(conn, workstreams=(), *, root=None):
    """The acceptance counter, alone. -> (count, [rel paths])."""
    res = classify(conn, workstreams, root=root, with_works=False)
    miss = [r["rel_path"] for r in res["rows"] if r["row_kind"] in ("file", "staging") and r["class"] is None]
    return len(miss), miss


# ── litkb_work's per-file view ───────────────────────────────────────────────────────────────

def classify_work_files(conn, work_id, *, root=None):
    """{file_id: {"class", "reason", "evidence"}} for one main work's current files, plus the work's
    rollup — what `litkb_work` shows so a refused file is no longer invisible to it."""
    from litkb.acquire.store import LITERATURE_ROOT

    root = Path(root or os.environ.get("LITKB_LITERATURE_ROOT") or LITERATURE_ROOT)
    files = _main_files(conn, str(work_id))
    run_ids = {f["current_run_id"] for f in files if f["current_run_id"]}
    runs, pblocks, qrows = _runs(conn, run_ids), _pages_blocks(conn, run_ids), _qrows(conn)
    out = {}
    for f in files:
        mine = [q for q in qrows if q["file_id"] == f["file_id"] or q["rel_path"] == f["rel_path"]]
        run = runs.get(f["current_run_id"]) if f["current_run_id"] else None
        ev = evidence_of(f, root=root, run=run, pages_blocks=pblocks.get(f["current_run_id"], {}) if run else {},
                         qrows=mine)
        cls, reason, notes = decide(ev)
        out[f["file_id"]] = {"class": cls, "reason": reason, "evidence": "; ".join(x for x in notes if x),
                             "rel_path": f["rel_path"], "status": f["status"]}
    active = [v for v in out.values() if v["status"] == "active"]
    classes = {v["class"] for v in active}
    rollup = (None if not active or None in classes else classes.pop() if len(classes) == 1 else "mixed")
    return out, rollup


# ── the CSV ───────────────────────────────────────────────────────────────────────────────────

def default_csv_path(today=None, reports=None):
    """`Reports/LITKB_READABILITY_<date>.csv`, or `..._<date>_2.csv`, `_3` … when a run already wrote
    today's: the CSV is create-only, so a second run the same day takes the next free name instead of
    failing on the first one."""
    d = (today or datetime.date.today()).isoformat()
    base = Path(reports or REPORTS)
    p, n = base / f"LITKB_READABILITY_{d}.csv", 2
    while p.exists():
        p, n = base / f"LITKB_READABILITY_{d}_{n}.csv", n + 1
    return p


def write_csv(res, path):
    """Write the rows, create-only (`open(..., "x")`): a report is never overwritten. A second run the
    same day passes another path. -> the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in res["rows"]:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in CSV_COLUMNS})
    return path


# ── the known-bads ─────────────────────────────────────────────────────────────────────────────

def fire_unclassified(conn, workstreams=(), *, root=None, drop="scan-needs-ocr"):
    """The design-contract MUTATION, at runtime: the classifier with ONE rule removed (`drop`, by
    name). A real file that rule classes goes unclassified and the counter MOVES.
    -> {"before", "after", "moved": [rel paths]}."""
    base = classify(conn, workstreams, root=root, with_works=False)
    mut = classify(conn, workstreams, root=root, with_works=False,
                   rules=tuple(r for r in RULES if r[0] != drop))
    def unclassified(res):
        # keyed by the file (a staging row by its path): two versions can share one rel_path
        return {(r["file_id"] or r["rel_path"]): r["rel_path"] for r in res["rows"]
                if r["row_kind"] in ("file", "staging") and r["class"] is None}
    b, a = unclassified(base), unclassified(mut)
    return {"before": len(b), "after": len(a), "moved": sorted(a[k] for k in set(a) - set(b)),
            "dropped_rule": drop}


def _constructed_unopenable_pdf(salt=""):
    """CONSTRUCTED: a `%PDF-` header and a `%%EOF` trailer — so `store.pdf_shape` calls it a whole
    PDF — around a catalog whose /Pages is not a dictionary. pypdfium2 5.13.0 refuses to load it
    ("Failed to load document"), and poppler's `pdfinfo` exits 99 with no page count (measured,
    builder-B report). It gets past the shape guard and is stopped only by the page probe. `salt`
    goes in a comment line after the header, so two calls can yield two different sha256s (the
    database holds one `files` row per sha256)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"(not a dict)"]
    out, offs = bytearray(b"%PDF-1.4\n" + (f"% {salt}\n".encode() if salt else b"")), []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return bytes(out)


def fire_probe(db, *, root, guard=True):
    """The acceptance's known-bad for the fail-closed bind probe (plan "### S4" (c)): a CONSTRUCTED
    unopenable PDF through the bind path (`acquire.run.land_and_attach`) on a WORKER database.

    The binder cannot read a file pdfium cannot open either, so on its own it would refuse this file
    `binding-pending` and the probe guard would never be reached; the binding is therefore STUBBED to
    `bound` for this one call, which isolates the one guard under test. `guard=False` is the MUTATION:
    the probe is replaced by one that never raises and reports no count — what the bind path did
    before S4 (`binding.pdf_info`) — and the same file then BINDS with `pages` NULL.
    -> {"probe_refused", "bound", "bound_pages_null", "status"}. Refuses `litkb`."""
    import hashlib
    import uuid

    from psycopg.types.json import Jsonb

    from litkb.acquire import run
    from litkb.acquire.store import Store
    from litkb.admit import binding
    from litkb.db import connect as c
    from litkb.extract import probe

    if not c.is_test_db(db):
        raise RuntimeError(f"fire_probe writes; it runs on a worker database, never {db!r}")
    root = Path(root)
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    owner = c.connect(db, "litkb_test", autocommit=True)
    writer = c.connect(db, "litkb_test", autocommit=True)
    writer.execute("SET ROLE litkb_writer")
    saved_bind, saved_probe = binding.bind_any_with_ocr, probe.probe_pages
    try:
        ws, token = owner.execute(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/fire-probe', NULL, "
            "'fire_probe', NULL)", (f"fire-probe-{uuid.uuid4().hex[:10]}",)).fetchone()
        hexid = uuid.uuid4().hex[:12]
        title = f"A constructed record for the probe known-bad {hexid}"
        ev = {"registry": "crossref", "registry_title": title, "registry_first_author": "Tester",
              "registry_year": 2020, "claimed": {"title": title, "first_author": "Tester", "year": 2020,
                                                 "title_ratio": 1.0, "author_match": True}}
        work = {"type": "article", "title": title, "authors": [{"family": "Tester", "given": "T."}], "year": 2020}
        ids = [{"scheme": "doi", "value": f"10.5555/litkb-fire-{hexid}", "verified_by": "crossref", "evidence": ev}]
        cand = writer.execute("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, "
                              "NULL, NULL)", (ws, token, "fire_probe")).fetchone()[0]
        res = writer.execute("SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, 'fire', 'fire')",
                             (ws, token, cand, f"Tester_2020_fire-{hexid}", Jsonb(work), Jsonb(ids),
                              Jsonb({}))).fetchone()[0]
        w = run.work_record(writer, work_id=res["work_id"])
        stub = {"verdict": "bound", "ratio": 1.0, "matched": title, "registry_title": title, "author_found": True,
                "author_near_title": True, "text_layer": True, "page": 1, "title_region": True,
                "stub": "fire_probe: the binder is bypassed to isolate the probe guard"}
        binding.bind_any_with_ocr = lambda *a, **k: dict(stub)
        if not guard:
            probe.probe_pages = lambda path: None
        data = _constructed_unopenable_pdf(salt=hexid)
        store = Store(root=root, index_cache=root / "fire_probe_index.json")
        status, detail = run.land_and_attach(writer, ws, token, w, data, route="browser",
                                             source_url="CONSTRUCTED fire_probe", store=store,
                                             index={"sha256": {}, "md5": {}}, agent="fire", session="fire")
        got = owner.execute("SELECT count(*), count(*) FILTER (WHERE pages IS NULL) FROM litkb.main_files "
                            "WHERE work_id = %s", (res["work_id"],)).fetchone()
        return {"probe_refused": int(status == "bad-file" and bool(detail.get("probe_error"))),
                "bound": int(got[0]), "bound_pages_null": int(got[1]), "status": status,
                "sha256": hashlib.sha256(data).hexdigest(), "quarantined": detail.get("quarantined")}
    finally:
        binding.bind_any_with_ocr, probe.probe_pages = saved_bind, saved_probe
        writer.close()
        owner.close()

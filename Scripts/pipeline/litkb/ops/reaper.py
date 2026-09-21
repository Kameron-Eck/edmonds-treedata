"""The staging reaper: name the bytes in `_litkb_staging/` that no database row accounts for.

    from litkb.ops import reaper
    out = reaper.reap(conn, root=..., min_age_hours=72, apply=False)   # dry run: moves nothing

NOTHING HERE DELETES, and nothing here writes the database. An orphan is QUARANTINED — moved by
`Store.to_quarantine` under a name that says what it is, with a `.reason.json` beside it naming the
census run, the sha256, the age and the rule that chose it — which is the same shape acquisition
already uses for bytes it refuses (`acquire/store.py`, and the 2026-09-12 loss of 149 PDFs that
made the no-delete rule a rule). A reason file is recoverable; an `rm -f` is not.

WHAT "ORPHAN" MEANS, AND WHY IT IS SHA-KEYED.  A file is OWNED when its sha256 appears in any
`litkb.files` row — any state, any workstream — or when its path appears as any
`file_versions.rel_path`. Path alone is not enough in either direction:

  * four files in `incoming/` on 2026-09-15 were byte-identical to files already recorded under
    `filed/` (S3 data survey §9: Bloch_2023, Culbert_2025, Ortega_2024, Subramanian_2021). A
    path-keyed reaper calls those four orphans and quarantines bytes the corpus holds;
  * the sixteen `t*.download` files in `incoming/` are named by `file_versions.rel_path` while the
    bytes at those paths are what a hunt is still working on, so the path leg is the one that
    catches them.

Both legs are therefore read, and either one owning a file is enough to leave it alone.

AGE.  A file younger than `min_age_hours` (default 72) is reported `young` and never touched,
whatever its sha says. `incoming/` is a WORKING directory: a download in flight has no `files` row
yet and would otherwise be indistinguishable from a week-old orphan. A `.download` beside a
`.part`/`.lock`/`.crdownload`/`.tmp` sibling is `young` at any age for the same reason — something
is holding it open.

SIDECARS.  `Store.land` writes `<stem>.txt` beside every download and `to_quarantine` moves the two
together, so a `.txt` that has a primary sibling is never a candidate of its own: it travels with
the file it belongs to. A `.txt` with no sibling (a `web/` snapshot is one) IS a candidate and is
judged like any other file — the real one is owned by its `rel_path`. `.reason.json` files are
never candidates at all.
"""
import datetime
import hashlib
import uuid
from pathlib import Path

#: the staging directories a reaper looks at, relative to `<root>/_litkb_staging/`. `web/` is
#: `admit.front.WEB_SNAPSHOT_DIR`; the other two are `Store.incoming` and `Store.filed`.
SCAN_DIRS = ("incoming", "filed", "web")
MIN_AGE_HOURS = 72
#: a sibling with one of these suffixes means a writer still holds the file open
LOCK_SUFFIXES = (".part", ".lock", ".crdownload", ".tmp")
#: the word that goes in the quarantined name, between the stem and the sha: <stem>__<this>__<sha12>
QUARANTINE_LABEL = "staging-orphan"
NEVER_A_CANDIDATE = (".reason.json",)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def known_shas(conn):
    """Every sha256 the database holds a file row for — the ownership leg that survives a rename."""
    return {r[0] for r in conn.execute("SELECT sha256 FROM litkb.files").fetchall() if r[0]}


def known_rel_paths(conn):
    """Every `file_versions.rel_path`, any version, any state — the leg that catches a download a
    hunt has already bound and is still working on, whose bytes no `files.sha256` matches yet."""
    return {r[0] for r in conn.execute(
        "SELECT DISTINCT rel_path FROM litkb.file_versions WHERE rel_path IS NOT NULL").fetchall()}


def _candidates(store):
    """The files in the scanned directories that are judged on their own account.

    A `<stem>.txt` with a primary sibling is dropped: it is that file's extract and moves with it.
    """
    out = []
    for name in SCAN_DIRS:
        d = store.staging / name
        if not d.is_dir():
            continue
        here = sorted(p for p in d.iterdir() if p.is_file())
        for p in here:
            if any(p.name.endswith(s) for s in NEVER_A_CANDIDATE):
                continue
            if p.suffix == ".txt" and any(
                    q.stem == p.stem and q.suffix not in (".txt",) and not q.name.endswith(".reason.json")
                    for q in here):
                continue
            out.append(p)
    return out


def _sidecar(path):
    txt = Path(path).with_suffix(".txt")
    return txt if txt.exists() and txt != Path(path) else None


def _locked(path):
    p = Path(path)
    return any((p.with_suffix(s)).exists() or p.with_name(p.name + s).exists() for s in LOCK_SUFFIXES)


def classify(path, *, store, shas, rels, min_age_hours, now):
    """-> a census row for one file: what it is, and the rule that decided.

    Order is ownership, then age. An owned file is left alone whatever its age; an unowned file
    younger than the window (or held open by a lock sibling) is `young`; what is left is an orphan.
    """
    p = Path(path)
    st = p.stat()
    mtime = datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc)
    age_h = (now - mtime).total_seconds() / 3600.0
    rel = store.rel(p)
    row = {"rel_path": rel, "bytes": st.st_size, "mtime": mtime.isoformat(),
           "age_hours": round(age_h, 2), "sha256": None, "verdict": None, "rule": None}
    row["sha256"] = sha256_of(p)
    # BEGIN guard: a file the database accounts for by sha or by path is never reaped
    if row["sha256"] in shas:
        row["verdict"], row["rule"] = "owned", "sha256 is a litkb.files row"
        return row
    if rel in rels:
        row["verdict"], row["rule"] = "owned", "a file_versions.rel_path names this path"
        return row
    # END guard: a file the database accounts for by sha or by path is never reaped
    # BEGIN guard: a file younger than the age window, or held open, is never reaped
    if _locked(p):
        row["verdict"], row["rule"] = "young", f"a sibling {'/'.join(LOCK_SUFFIXES)} holds it open"
        return row
    if age_h < min_age_hours:
        row["verdict"], row["rule"] = "young", f"mtime is {age_h:.2f} h old, under {min_age_hours} h"
        return row
    # END guard: a file younger than the age window, or held open, is never reaped
    row["verdict"] = "orphan"
    row["rule"] = (f"sha256 in no litkb.files row, no file_versions.rel_path names {rel}, "
                   f"and it is {age_h:.2f} h old (>= {min_age_hours} h)")
    return row


def census(conn, *, root=None, store=None, min_age_hours=MIN_AGE_HOURS, now=None):
    """Classify every candidate. Reads the database and the disk; changes neither."""
    from litkb.acquire.store import Store

    store = store or Store(root=root)
    shas, rels, now = known_shas(conn), known_rel_paths(conn), now or _now()
    rows, errors = [], []
    for p in _candidates(store):
        try:
            rows.append(classify(p, store=store, shas=shas, rels=rels,
                                 min_age_hours=min_age_hours, now=now))
        except OSError as e:
            errors.append({"rel_path": str(p), "error": f"{type(e).__name__}: {e}"})
    return {"root": str(store.root), "min_age_hours": min_age_hours, "at": now.isoformat(),
            "rows": rows, "errors": errors, "store": store}


def counters(out):
    """The one line a caller reads: scanned owned young orphans quarantined skipped_errors."""
    rows = out["rows"]
    return {"scanned": len(rows),
            "owned": sum(1 for r in rows if r["verdict"] == "owned"),
            "young": sum(1 for r in rows if r["verdict"] == "young"),
            "orphans": sum(1 for r in rows if r["verdict"] == "orphan"),
            "quarantined": sum(1 for r in rows if r.get("quarantined")),
            "skipped_errors": len(out["errors"])}


def reap(conn, *, root=None, store=None, min_age_hours=MIN_AGE_HOURS, apply=False, now=None):
    """The census, and — only with `apply=True` — the quarantine move for each orphan.

    -> {"root", "min_age_hours", "at", "run_id", "applied", "rows", "errors", "counters"}.
    """
    out = census(conn, root=root, store=store, min_age_hours=min_age_hours, now=now)
    store = out.pop("store")
    run_id = str(uuid.uuid4())
    out["run_id"], out["applied"] = run_id, bool(apply)
    for row in out["rows"]:
        # BEGIN guard: a dry run moves nothing
        if not apply or row["verdict"] != "orphan":
            continue
        # END guard: a dry run moves nothing
        src = store.root / row["rel_path"]
        try:
            dst, _txt = store.to_quarantine(src, _sidecar(src), Path(row["rel_path"]).stem,
                                            QUARANTINE_LABEL, row["sha256"],
                                            suffix=Path(row["rel_path"]).suffix)
            reason = store.write_reason(dst, {
                "why": "the staging reaper found no database row accounting for these bytes",
                "census_run": run_id, "at": out["at"], "rule": row["rule"],
                "sha256": row["sha256"], "bytes": row["bytes"], "mtime": row["mtime"],
                "age_hours": row["age_hours"], "min_age_hours": min_age_hours,
                "was": row["rel_path"],
                "recover": "nothing was deleted: move it back, or bind it with "
                           "`py -3.12 -m litkb acquire --key <key> --from-file <this path>`"})
            row["quarantined"] = store.rel(dst)
            row["reason_path"] = store.rel(reason)
        except (OSError, RuntimeError) as e:
            out["errors"].append({"rel_path": row["rel_path"],
                                  "error": f"{type(e).__name__}: {e}"})
    out["counters"] = counters(out)
    return out


def table(out):
    """The census as lines of text — the caller prints them; this module writes no stream."""
    w = max([len(r["rel_path"]) for r in out["rows"]] + [9])
    lines = [f"{'file':<{w}}  {'verdict':<8} {'age h':>8}  {'bytes':>10}  rule",
             "-" * (w + 40)]
    for r in sorted(out["rows"], key=lambda r: (r["verdict"], r["rel_path"])):
        lines.append(f"{r['rel_path']:<{w}}  {r['verdict']:<8} {r['age_hours']:>8.2f}  "
                     f"{r['bytes']:>10}  {r['rule']}")
    for e in out["errors"]:
        lines.append(f"{e['rel_path']:<{w}}  {'error':<8} {'':>8}  {'':>10}  {e['error']}")
    return lines


def as_json(out):
    """The `--out` document: the census without the live objects, ready for json.dump."""
    return {k: v for k, v in out.items() if k != "store"}
